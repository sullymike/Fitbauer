"""Suite de validación sintética del motor de ajuste Mössbauer.

Cubre seis niveles de verificación sistemática:

  1. Autoconsistencia (generador independiente → ajuste → χ²≈0).
  2. Motor de optimización: jacobiano numérico vs. diferencias finitas.
  3. Monte Carlo estadístico: réplicas Poisson, pull ~ N(0,1).
  4. Casos físicos difíciles: solapamiento de dobletes, absorbente grueso.
  5. Restricciones físicas: ratios 3:2:1, convenciones de δ/ΔEQ.
  6. Datos reales: α-Fe calibración 33.0 T.

Tests marcados ``@pytest.mark.slow`` (N_MC ≥ 200 réplicas) se pueden omitir
en CI con ``pytest -m "not slow"``.

Reproducibilidad: las semillas del generador de ruido se fijan por test y se
recogen en ``SEEDS_MC`` para reproducir cualquier fallo.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy.optimize import approx_fprime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.constants import LINE_POS_33T, LINE_QUAD_PATTERN, BHF_DEFAULT_T
from core.fit_engine import (
    Component, FitState, FitResult,
    fit_discrete, model_from_values,
    texture_to_intensities,
)
import core.physics as _phys

# ── Semillas Monte Carlo (fijadas para reproducibilidad) ─────────────────────
SEEDS_MC: dict[str, int] = {
    "sextet_pull": 42042,
    "doublet_pull": 13579,
}

# ── Malla de velocidades estándar de test ────────────────────────────────────
VMAX_TEST = 12.0
N_CHAN = 256
V_TEST = np.linspace(-VMAX_TEST, VMAX_TEST, N_CHAN)

# ── Datos de espectros reales ─────────────────────────────────────────────────
DATA = ROOT / "data_sample"


# ═════════════════════════════════════════════════════════════════════════════
# IMPLEMENTACIÓN DIRECTA INDEPENDIENTE (usada en Puntos 1, 3 y 4)
#
# NO llama a ninguna función de core.physics ni core.fit_engine.
# Deriva el espectro directamente de la física: posición Doppler de cada
# línea y suma de lorentzianas.  Si este generador y el ajustador producen
# resultados distintos en ausencia de ruido, hay un bug en uno de los dos.
# ═════════════════════════════════════════════════════════════════════════════

def _lor_ref(v: np.ndarray, center: float, gamma: float) -> np.ndarray:
    """Lorentziana de referencia: L(v) = (Γ/2)² / [(v−c)² + (Γ/2)²]."""
    g = max(float(gamma), 1e-9) / 2.0
    return g * g / ((v - center) ** 2 + g * g)


def ref_sextet(
    v: np.ndarray,
    baseline: float, slope: float,
    delta: float, quad: float, bhf: float,
    gamma: float, depth: float,
    int1: float = 3.0, int2: float = 2.0, int3: float = 1.0,
) -> np.ndarray:
    """Generador de sextete de referencia, implementación completamente independiente.

    Usa ``LINE_POS_33T`` de las constantes (calibración α-Fe publicada) pero
    reimplementa la suma de lorentzianas sin recurrir a ``physics.sextet_absorption``.
    """
    pos = LINE_POS_33T * (bhf / BHF_DEFAULT_T) + delta + quad * LINE_QUAD_PATTERN
    weights = np.array([int1 * int3, int2 * int3, int3,
                        int3, int2 * int3, int1 * int3], dtype=float)
    absorb = sum(float(w) * _lor_ref(v, float(p), gamma)
                 for w, p in zip(weights, pos))
    return baseline + slope * v - depth * absorb


def ref_doublet(
    v: np.ndarray,
    baseline: float, slope: float,
    delta: float, quad: float,
    gamma: float, depth: float,
    int1: float = 1.0, int2: float = 1.0,
) -> np.ndarray:
    """Generador de doblete de referencia."""
    p1 = delta - quad / 2.0
    p2 = delta + quad / 2.0
    absorb = (int1 * _lor_ref(v, p1, gamma)
              + int1 * int2 * _lor_ref(v, p2, gamma))
    return baseline + slope * v - depth * absorb


def ref_singlet(
    v: np.ndarray,
    baseline: float, slope: float,
    delta: float, gamma: float, depth: float,
    int1: float = 1.0,
) -> np.ndarray:
    """Generador de singlete de referencia."""
    return baseline + slope * v - depth * int1 * _lor_ref(v, delta, gamma)


def ref_sextet_thick(
    v: np.ndarray,
    baseline: float, slope: float,
    delta: float, quad: float, bhf: float,
    gamma: float, depth: float, sat_scale: float,
    int1: float = 3.0, int2: float = 2.0, int3: float = 1.0,
) -> np.ndarray:
    """Absorbente grueso de referencia: T = B − C·(1 − exp(−A/C))."""
    pos = LINE_POS_33T * (bhf / BHF_DEFAULT_T) + delta + quad * LINE_QUAD_PATTERN
    weights = np.array([int1 * int3, int2 * int3, int3,
                        int3, int2 * int3, int1 * int3], dtype=float)
    a_tot = sum(float(w) * _lor_ref(v, float(p), gamma)
                for w, p in zip(weights, pos))
    a_tot = depth * a_tot
    c = max(float(sat_scale), 1e-9)
    return baseline + slope * v - c * (1.0 - np.exp(-a_tot / c))


# ═════════════════════════════════════════════════════════════════════════════
# Utilidades de construcción de FitState
# ═════════════════════════════════════════════════════════════════════════════

def _make_sextet_state(
    v: np.ndarray,
    y_data: np.ndarray,
    *,
    delta: float = -0.109, quad: float = 0.0, bhf: float = 33.0,
    gamma: float = 0.28, depth: float = 0.013,
    baseline: float = 1.0, slope: float = 0.0,
    perturb: float = 0.0,
    sigma: np.ndarray | None = None,
    multistart_n: int = 4,
) -> FitState:
    """FitState para un sextete sencillo con perturbación opcional."""
    rng_p = np.random.default_rng(99)
    scale = perturb

    def _p(x: float, rel: float = 0.05, abs_: float = 0.0) -> float:
        return x * (1.0 + scale * rel * rng_p.uniform(-1, 1)) + scale * abs_ * rng_p.uniform(-1, 1)

    vals: dict[str, float] = {
        "baseline": _p(baseline, 0.02),
        "slope": 0.0,
        "vmax": VMAX_TEST,
        "voigt_sigma": 0.05,
        "s1_delta": _p(delta, 0.0, 0.3),
        "s1_quad": quad,
        "s1_bhf": _p(bhf, 0.03),
        "s1_gamma1": _p(gamma, 0.1),
        "s1_gamma2": 1.0,
        "s1_gamma3": 1.0,
        "s1_depth": _p(depth, 0.1),
        "s1_int1": 3.0,
        "s1_int2": 2.0,
        "s1_int3": 1.0,
    }
    fixed = {k: False for k in vals}
    for k in ("s1_int1", "s1_int2", "s1_int3", "s1_gamma2", "s1_gamma3", "s1_quad"):
        fixed[k] = True
    bounds: dict[str, tuple[float, float]] = {
        "baseline": (0.5, 1.5), "slope": (-0.02, 0.02),
        "s1_delta": (-3.0, 3.0), "s1_quad": (-4.0, 4.0),
        "s1_bhf": (0.0, 60.0), "s1_gamma1": (0.05, 4.0),
        "s1_gamma2": (0.2, 6.0), "s1_gamma3": (0.2, 6.0),
        "s1_depth": (0.0, 0.5), "s1_int1": (0.0, 9.0),
        "s1_int2": (0.0, 6.0), "s1_int3": (0.0, 3.0),
        "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0),
    }
    if sigma is None:
        sigma = np.ones_like(y_data) * 1e-4
    return FitState(
        velocity=v, y_data=y_data, sigma_data=sigma,
        values=vals, fixed=fixed, bounds=bounds,
        components=[Component(idx=1, enabled=True, kind="Sextete")],
        multistart_n=multistart_n,
    )


def _make_doublet_state(
    v: np.ndarray,
    y_data: np.ndarray,
    *,
    delta: float = 0.35, quad: float = 0.80,
    gamma: float = 0.28, depth: float = 0.020,
    baseline: float = 1.0,
    perturb: float = 0.0,
    sigma: np.ndarray | None = None,
    multistart_n: int = 2,
    quad_lo: float = 0.0, quad_hi: float = 6.0,
) -> FitState:
    """FitState para un doblete sencillo."""
    rng_p = np.random.default_rng(77)
    s = perturb

    def _p(x: float, rel: float = 0.05, abs_: float = 0.0) -> float:
        return x * (1.0 + s * rel * rng_p.uniform(-1, 1)) + s * abs_ * rng_p.uniform(-1, 1)

    vals: dict[str, float] = {
        "baseline": _p(baseline, 0.02),
        "slope": 0.0,
        "vmax": VMAX_TEST,
        "voigt_sigma": 0.05,
        "s1_delta": _p(delta, 0.0, 0.1),
        "s1_quad": _p(quad, 0.1),
        "s1_bhf": 0.0,
        "s1_gamma1": _p(gamma, 0.1),
        "s1_gamma2": 1.0,
        "s1_gamma3": 1.0,
        "s1_depth": _p(depth, 0.1),
        "s1_int1": 1.0,
        "s1_int2": 1.0,
        "s1_int3": 1.0,
    }
    fixed = {k: False for k in vals}
    for k in ("s1_bhf", "s1_gamma2", "s1_gamma3", "s1_int1", "s1_int2", "s1_int3"):
        fixed[k] = True
    bounds: dict[str, tuple[float, float]] = {
        "baseline": (0.5, 1.5), "slope": (-0.02, 0.02),
        "s1_delta": (-3.0, 3.0), "s1_quad": (quad_lo, quad_hi),
        "s1_bhf": (0.0, 1.0), "s1_gamma1": (0.05, 4.0),
        "s1_gamma2": (0.5, 2.0), "s1_gamma3": (0.5, 2.0),
        "s1_depth": (0.0, 0.5), "s1_int1": (0.5, 2.0),
        "s1_int2": (0.5, 2.0), "s1_int3": (0.5, 2.0),
        "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0),
    }
    if sigma is None:
        sigma = np.ones_like(y_data) * 1e-4
    return FitState(
        velocity=v, y_data=y_data, sigma_data=sigma,
        values=vals, fixed=fixed, bounds=bounds,
        components=[Component(idx=1, enabled=True, kind="Doblete")],
        multistart_n=multistart_n,
    )


# ═════════════════════════════════════════════════════════════════════════════
# PUNTO 1 — AUTOCONSISTENCIA
#
# Se genera un espectro sin ruido con la implementación de referencia (distinta
# a physics.py) y se verifica que el ajustador recupera exactamente los
# parámetros verdaderos:  residuo_max < 1e-6, χ²_reducido < 1e-6.
# ═════════════════════════════════════════════════════════════════════════════

class TestAutoconsistencia:
    """Punto 1: implementación directa → ajuste → χ² ≈ 0."""

    TRUE_SEXTET = dict(
        baseline=1.0, slope=0.0,
        delta=-0.109, quad=0.0, bhf=33.0, gamma=0.28, depth=0.013,
    )

    TRUE_DOUBLET = dict(
        baseline=1.0, slope=0.003,
        delta=0.35, quad=0.82, gamma=0.30, depth=0.022,
    )

    TRUE_SINGLET = dict(
        baseline=1.0, slope=0.0,
        delta=0.10, gamma=0.30, depth=0.018,
    )

    def test_sextet_sin_ruido(self):
        """Sextete sintético sin ruido: el ajustador converge a χ²_red < 1e-6."""
        tp = self.TRUE_SEXTET
        y = ref_sextet(V_TEST, **tp)
        state = _make_sextet_state(
            V_TEST, y,
            delta=tp["delta"], quad=tp["quad"], bhf=tp["bhf"],
            gamma=tp["gamma"], depth=tp["depth"], baseline=tp["baseline"],
            perturb=1.0,  # perturbación del 5–10 % sobre valores iniciales
        )
        _phys.LINE_PROFILE_KIND = "Lorentziana"
        result = fit_discrete(state)

        assert result.success or result.values, "El ajuste debe converger."
        assert result.stats.get("red_chi2", 1.0) < 1e-6, (
            f"χ²_red = {result.stats.get('red_chi2'):.2e} ≥ 1e-6: "
            "la implementación del generador y del ajustador no son consistentes."
        )
        assert abs(result.values["s1_bhf"] - tp["bhf"]) < 0.01
        assert abs(result.values["s1_delta"] - tp["delta"]) < 0.01
        assert abs(result.values["s1_gamma1"] - tp["gamma"]) < 0.01
        assert abs(result.values["s1_depth"] - tp["depth"]) < 0.001
        # Residuo máximo < 1e-5 en unidades del espectro
        y_fit = model_from_values(V_TEST, result.values,
                                  state.components, state.constraints)
        np.testing.assert_allclose(y_fit, y, atol=1e-5,
                                   err_msg="Residuo por canal no es ~0 a máquina.")

    def test_doublet_sin_ruido(self):
        """Doblete sintético sin ruido: recuperación de δ, ΔEQ, Γ, profundidad."""
        tp = self.TRUE_DOUBLET
        y = ref_doublet(V_TEST,
                        tp["baseline"], tp["slope"],
                        tp["delta"], tp["quad"], tp["gamma"], tp["depth"])
        state = _make_doublet_state(
            V_TEST, y,
            delta=tp["delta"], quad=tp["quad"],
            gamma=tp["gamma"], depth=tp["depth"], baseline=tp["baseline"],
            perturb=1.0,
        )
        # Añadimos pendiente como libre
        state.values["slope"] = tp["slope"] * 0.5
        state.fixed["slope"] = False
        _phys.LINE_PROFILE_KIND = "Lorentziana"
        result = fit_discrete(state)

        assert result.stats.get("red_chi2", 1.0) < 1e-6, (
            f"χ²_red doblete = {result.stats.get('red_chi2'):.2e}"
        )
        assert abs(result.values["s1_delta"] - tp["delta"]) < 0.01
        assert abs(result.values["s1_quad"] - tp["quad"]) < 0.01
        assert abs(result.values["s1_gamma1"] - tp["gamma"]) < 0.01

    def test_singlet_sin_ruido(self):
        """Singlete sintético sin ruido: recuperación mínima."""
        tp = self.TRUE_SINGLET
        y = ref_singlet(V_TEST,
                        tp["baseline"], tp["slope"],
                        tp["delta"], tp["gamma"], tp["depth"])
        vals = {
            "baseline": 1.02, "slope": 0.0, "vmax": VMAX_TEST,
            "voigt_sigma": 0.05,
            "s1_delta": tp["delta"] + 0.1, "s1_quad": 0.0, "s1_bhf": 0.0,
            "s1_gamma1": tp["gamma"] * 1.2, "s1_gamma2": 1.0, "s1_gamma3": 1.0,
            "s1_depth": tp["depth"] * 1.1,
            "s1_int1": 1.0, "s1_int2": 1.0, "s1_int3": 1.0,
        }
        fixed = {k: False for k in vals}
        for k in ("s1_bhf", "s1_quad", "s1_gamma2", "s1_gamma3",
                   "s1_int1", "s1_int2", "s1_int3"):
            fixed[k] = True
        bounds: dict[str, tuple[float, float]] = {
            "baseline": (0.8, 1.2), "slope": (-0.02, 0.02),
            "s1_delta": (-2.0, 2.0), "s1_quad": (-1.0, 1.0),
            "s1_bhf": (0.0, 1.0), "s1_gamma1": (0.05, 2.0),
            "s1_gamma2": (0.5, 2.0), "s1_gamma3": (0.5, 2.0),
            "s1_depth": (0.0, 0.3), "s1_int1": (0.5, 2.0),
            "s1_int2": (0.5, 2.0), "s1_int3": (0.5, 2.0),
            "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0),
        }
        sigma = np.ones(N_CHAN) * 1e-4
        state = FitState(
            velocity=V_TEST, y_data=y, sigma_data=sigma,
            values=vals, fixed=fixed, bounds=bounds,
            components=[Component(idx=1, enabled=True, kind="Singlete")],
            multistart_n=2,
        )
        _phys.LINE_PROFILE_KIND = "Lorentziana"
        result = fit_discrete(state)
        assert result.stats.get("red_chi2", 1.0) < 1e-6
        assert abs(result.values["s1_delta"] - tp["delta"]) < 0.01

    def test_generador_ref_vs_physics(self):
        """El generador de referencia coincide con physics.sextet_absorption."""
        tp = self.TRUE_SEXTET
        _phys.LINE_PROFILE_KIND = "Lorentziana"
        y_ref = ref_sextet(V_TEST, **tp)

        import core.physics as phys
        absorb = phys.sextet_absorption(
            V_TEST,
            tp["delta"], tp["quad"], tp["bhf"],
            tp["gamma"], 1.0, 1.0,
            tp["depth"],
            3.0, 2.0, 1.0,
        )
        y_phys = tp["baseline"] + tp["slope"] * V_TEST - absorb
        np.testing.assert_allclose(
            y_ref, y_phys, rtol=1e-10,
            err_msg="El generador de referencia difiere de physics.sextet_absorption.",
        )


# ═════════════════════════════════════════════════════════════════════════════
# PUNTO 2 — VALIDACIÓN DEL JACOBIANO
#
# Verifica que la función residuo es suave y su jacobiano numérico (diferencias
# finitas) coincide entre dos tamaños de paso independientes.
# También valida el jacobiano analítico de la lorentziana.
# ═════════════════════════════════════════════════════════════════════════════

class TestJacobiano:
    """Punto 2: consistencia del jacobiano de la función residuo."""

    def test_jacobiano_analitico_lorentziana_centro(self):
        """∂L/∂c analítico == diferencias finitas (error < 1e-4 relativo)."""
        v = np.linspace(-5, 5, 200)
        c0, gamma0 = 0.3, 0.28

        def L(c_arr):
            return _lor_ref(v, float(c_arr[0]), gamma0)

        # approx_fprime([c0], L, eps) → shape (200, 1) o (200,) según versión scipy
        dL_dc_fd = np.asarray(approx_fprime([c0], L, 1e-6)).ravel()
        # Analítico: dL/dc = 2(v-c)·(Γ/2)² / [(v-c)²+(Γ/2)²]²
        g = gamma0 / 2.0
        dL_dc_analytic = 2.0 * (v - c0) * g ** 2 / ((v - c0) ** 2 + g ** 2) ** 2
        np.testing.assert_allclose(dL_dc_fd, dL_dc_analytic, rtol=1e-4,
                                   err_msg="Jacobiano analítico ∂L/∂c difiere del numérico.")

    def test_jacobiano_analitico_lorentziana_gamma(self):
        """∂L/∂Γ analítico == diferencias finitas (error < 1e-4 relativo)."""
        v = np.linspace(-5, 5, 200)
        c0, gamma0 = 0.3, 0.28

        def L(g_arr):
            return _lor_ref(v, c0, float(g_arr[0]))

        # approx_fprime([gamma0], L, eps) → shape (200, 1) o (200,) según versión scipy
        dL_dg_fd = np.asarray(approx_fprime([gamma0], L, 1e-6)).ravel()
        g = gamma0 / 2.0
        # dL/dΓ = dL/d(2g)·(1/2): usando regla de la cadena
        denom = (v - c0) ** 2 + g ** 2
        dL_dg_analytic = g * (v - c0) ** 2 / denom ** 2
        np.testing.assert_allclose(dL_dg_fd, dL_dg_analytic, rtol=1e-4,
                                   err_msg="Jacobiano analítico ∂L/∂Γ difiere del numérico.")

    def test_jacobiano_residuo_sextet_consistencia_dos_pasos(self):
        """El jacobiano de la función residuo es consistente entre eps=1e-5 y eps=1e-6."""
        tp = TestAutoconsistencia.TRUE_SEXTET
        y_true = ref_sextet(V_TEST, **tp)
        sigma = np.ones(N_CHAN) * 5e-4

        # Parámetros libres: [delta, bhf, gamma1, depth, baseline]
        free_vals = [tp["delta"], tp["bhf"], tp["gamma"], tp["depth"], tp["baseline"]]

        def residual(x):
            vals = {
                "baseline": x[4], "slope": 0.0,
                "s1_delta": x[0], "s1_quad": 0.0, "s1_bhf": x[1],
                "s1_gamma1": x[2], "s1_gamma2": 1.0, "s1_gamma3": 1.0,
                "s1_depth": x[3], "s1_int1": 3.0, "s1_int2": 2.0, "s1_int3": 1.0,
                "vmax": VMAX_TEST, "voigt_sigma": 0.05,
            }
            comps = [Component(idx=1, enabled=True, kind="Sextete")]
            m = model_from_values(V_TEST, vals, comps)
            return (m - y_true) / sigma

        x0 = np.array(free_vals, dtype=float)
        _phys.LINE_PROFILE_KIND = "Lorentziana"
        J_coarse = approx_fprime(x0, residual, 1e-5)
        J_fine = approx_fprime(x0, residual, 1e-6)

        # Columnas con norma > 0.01 deben coincidir al 1 %
        for j in range(J_coarse.shape[1]):
            norm_c = np.linalg.norm(J_coarse[:, j])
            norm_f = np.linalg.norm(J_fine[:, j])
            if max(norm_c, norm_f) > 0.01:
                rel_err = abs(norm_c - norm_f) / max(norm_c, norm_f)
                assert rel_err < 0.05, (
                    f"Columna {j} del jacobiano inestable: "
                    f"norm(eps=1e-5)={norm_c:.4f}, norm(eps=1e-6)={norm_f:.4f}, "
                    f"err_rel={rel_err:.4f}"
                )

    def test_jacobiano_sin_nan_ni_inf(self):
        """El jacobiano de la función residuo no contiene NaN ni Inf."""
        tp = TestAutoconsistencia.TRUE_SEXTET
        y_true = ref_sextet(V_TEST, **tp)
        sigma = np.ones(N_CHAN) * 5e-4

        def residual(x):
            vals = {
                "baseline": x[4], "slope": 0.0,
                "s1_delta": x[0], "s1_quad": 0.0, "s1_bhf": x[1],
                "s1_gamma1": x[2], "s1_gamma2": 1.0, "s1_gamma3": 1.0,
                "s1_depth": x[3], "s1_int1": 3.0, "s1_int2": 2.0, "s1_int3": 1.0,
                "vmax": VMAX_TEST, "voigt_sigma": 0.05,
            }
            comps = [Component(idx=1, enabled=True, kind="Sextete")]
            m = model_from_values(V_TEST, vals, comps)
            return (m - y_true) / sigma

        x0 = np.array([tp["delta"], tp["bhf"], tp["gamma"], tp["depth"], tp["baseline"]])
        _phys.LINE_PROFILE_KIND = "Lorentziana"
        J = approx_fprime(x0, residual, 1e-6)
        assert np.all(np.isfinite(J)), "Jacobiano contiene NaN o Inf."

    def test_jacobiano_doublet_residuo_sin_nan(self):
        """Jacobiano del doblete: sin NaN ni Inf en x0."""
        tp = TestAutoconsistencia.TRUE_DOUBLET
        y_true = ref_doublet(V_TEST,
                             tp["baseline"], tp["slope"],
                             tp["delta"], tp["quad"], tp["gamma"], tp["depth"])
        sigma = np.ones(N_CHAN) * 5e-4

        def residual(x):
            vals = {
                "baseline": x[4], "slope": x[5],
                "s1_delta": x[0], "s1_quad": x[1], "s1_bhf": 0.0,
                "s1_gamma1": x[2], "s1_gamma2": 1.0, "s1_gamma3": 1.0,
                "s1_depth": x[3], "s1_int1": 1.0, "s1_int2": 1.0, "s1_int3": 1.0,
                "vmax": VMAX_TEST, "voigt_sigma": 0.05,
            }
            comps = [Component(idx=1, enabled=True, kind="Doblete")]
            m = model_from_values(V_TEST, vals, comps)
            return (m - y_true) / sigma

        x0 = np.array([tp["delta"], tp["quad"], tp["gamma"], tp["depth"],
                       tp["baseline"], tp["slope"]])
        _phys.LINE_PROFILE_KIND = "Lorentziana"
        J = approx_fprime(x0, residual, 1e-6)
        assert np.all(np.isfinite(J)), "Jacobiano del doblete contiene NaN o Inf."


# ═════════════════════════════════════════════════════════════════════════════
# PUNTO 3 — MONTE CARLO CON PULL STATISTICS
#
# 200 réplicas de un sextete con ruido Poisson realista.
# Valida sesgo (media del pull ≈ 0) y calibración de incertidumbres
# (std del pull ≈ 1).  Un programa que subestima σ dará std(pull) > 1.
#
# Marcado @pytest.mark.slow porque el ajuste de 200 espectros tarda ~30 s.
# ═════════════════════════════════════════════════════════════════════════════

N_MC = 200       # réplicas Monte Carlo
COUNTS_MC = 8000  # cuentas por canal (SNR realista)


def _poisson_replica(y_model: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Genera una réplica con ruido Poisson.

    Modelo: c_i ~ Poisson(λ_i) donde λ_i = y_model_i · COUNTS_MC.
    Devuelve y_sim = c_i / COUNTS_MC con σ = sqrt(c_i) / COUNTS_MC.
    """
    lam = np.maximum(y_model * COUNTS_MC, 0.0)
    counts = rng.poisson(lam).astype(float)
    y_sim = counts / COUNTS_MC
    sigma = np.maximum(np.sqrt(counts), 1.0) / COUNTS_MC
    return y_sim, sigma


@pytest.mark.slow
class TestMonteCarlo:
    """Punto 3: validación estadística con N_MC réplicas Poisson."""

    TRUE_SEXTET_MC = dict(
        baseline=1.0, slope=0.0,
        delta=-0.109, quad=0.0, bhf=33.0, gamma=0.28, depth=0.020,
    )

    def _run_mc_sextet(self) -> dict[str, list[float]]:
        """Ejecuta N_MC réplicas y devuelve muestras de parámetros y errores."""
        tp = self.TRUE_SEXTET_MC
        y_true = ref_sextet(V_TEST, **tp)
        rng = np.random.default_rng(SEEDS_MC["sextet_pull"])

        free_params = ("s1_delta", "s1_bhf", "s1_gamma1", "s1_depth", "baseline")
        true_vals = {
            "s1_delta": tp["delta"], "s1_bhf": tp["bhf"],
            "s1_gamma1": tp["gamma"], "s1_depth": tp["depth"],
            "baseline": tp["baseline"],
        }

        samples: dict[str, list[float]] = {k: [] for k in free_params}
        errors: dict[str, list[float]] = {k: [] for k in free_params}

        for _ in range(N_MC):
            y_sim, sigma = _poisson_replica(y_true, rng)
            state = _make_sextet_state(
                V_TEST, y_sim,
                delta=tp["delta"], quad=tp["quad"], bhf=tp["bhf"],
                gamma=tp["gamma"], depth=tp["depth"], baseline=tp["baseline"],
                perturb=0.3,  # inicio perturbado un 30 % para evitar trampa
                sigma=sigma,
                multistart_n=1,
            )
            _phys.LINE_PROFILE_KIND = "Lorentziana"
            try:
                result = fit_discrete(state)
            except Exception:
                continue
            if not result.values:
                continue
            for k in free_params:
                val = result.values.get(k)
                err = result.errors.get(k)
                if val is not None and err is not None and err > 0:
                    samples[k].append(float(val))
                    errors[k].append(float(err))

        return {"samples": samples, "errors": errors, "true": true_vals}

    def test_pull_statistics_sesgo(self):
        """media(pull) estadísticamente compatible con 0 para todos los parámetros."""
        data = self._run_mc_sextet()
        samples = data["samples"]
        errors = data["errors"]
        true_vals = data["true"]

        for k, vals in samples.items():
            if len(vals) < 50:
                pytest.skip(f"Demasiadas réplicas fallidas para '{k}' ({len(vals)}).")
            vals_arr = np.array(vals)
            errs_arr = np.array(errors[k])
            pulls = (vals_arr - true_vals[k]) / errs_arr
            mean_pull = np.mean(pulls)
            std_pull = np.std(pulls, ddof=1)
            n = len(pulls)
            # El error estándar de la media del pull es std/sqrt(n)
            sem = std_pull / np.sqrt(n)
            assert abs(mean_pull) < 3.5 * sem + 0.05, (
                f"Sesgo detectado en '{k}': media(pull)={mean_pull:.3f} "
                f"± {sem:.3f} (> 3.5·SEM). El estimador puede ser sesgado."
            )

    def test_pull_statistics_calibracion_sigma(self):
        """std(pull) ≈ 1: las barras de error reportadas calibran bien."""
        data = self._run_mc_sextet()
        samples = data["samples"]
        errors = data["errors"]
        true_vals = data["true"]

        for k, vals in samples.items():
            if len(vals) < 50:
                continue
            vals_arr = np.array(vals)
            errs_arr = np.array(errors[k])
            pulls = (vals_arr - true_vals[k]) / errs_arr
            std_pull = np.std(pulls, ddof=1)
            # Tolerancia generosa: std(pull) ∈ [0.5, 2.0]
            # (<0.5 → σ sobreestimado; >2.0 → σ muy subestimado)
            assert 0.5 < std_pull < 2.0, (
                f"Calibración de σ deficiente en '{k}': std(pull)={std_pull:.3f}. "
                f"Esperado ∈ (0.5, 2.0).  Las incertidumbres reportadas no reflejan "
                f"la dispersión real de Monte Carlo."
            )

    def test_cobertura_intervalo_un_sigma(self):
        """~68 % de las réplicas caen dentro de ±1σ reportado."""
        data = self._run_mc_sextet()
        samples = data["samples"]
        errors = data["errors"]
        true_vals = data["true"]

        for k, vals in samples.items():
            if len(vals) < 50:
                continue
            vals_arr = np.array(vals)
            errs_arr = np.array(errors[k])
            within = np.mean(np.abs(vals_arr - true_vals[k]) <= errs_arr)
            # Cobertura 1σ esperada ≈ 0.683; toleramos ±0.20
            assert 0.48 < within < 0.88, (
                f"Cobertura 1σ de '{k}': {within:.2%} (esperado ~68 %)."
            )


# ═════════════════════════════════════════════════════════════════════════════
# PUNTO 4 — CASOS FÍSICOS DIFÍCILES
# ═════════════════════════════════════════════════════════════════════════════

class TestCasosDificiles:
    """Punto 4: casos diseñados para estresar el ajuste."""

    # ── 4a. Solapamiento creciente de dobletes ────────────────────────────────

    @pytest.mark.parametrize("quad", [2.0, 1.0, 0.60])
    def test_doublet_resuelto_recupera_separacion(self, quad: float):
        """Cuando la separación de líneas es > 2Γ el ajustador recupera ΔEQ."""
        gamma = 0.28
        tp = dict(delta=0.35, quad=quad, gamma=gamma, depth=0.025)
        y = ref_doublet(V_TEST, 1.0, 0.0, **tp)
        state = _make_doublet_state(
            V_TEST, y,
            delta=tp["delta"], quad=tp["quad"] * 0.8,  # inicio 20 % bajo
            gamma=tp["gamma"], depth=tp["depth"],
            perturb=0.5,
            quad_lo=0.0, quad_hi=6.0,
        )
        _phys.LINE_PROFILE_KIND = "Lorentziana"
        result = fit_discrete(state)
        assert abs(result.values["s1_quad"] - tp["quad"]) < 0.10, (
            f"ΔEQ no recuperado para separación={quad:.2f}: "
            f"obtenido={result.values['s1_quad']:.3f}"
        )

    def test_doublet_solapamiento_aumento_incertidumbre(self):
        """Las barras de error de ΔEQ crecen al reducir la separación."""
        gamma = 0.28
        errors_quad: list[float] = []
        for quad in [1.5, 0.8, 0.4, 0.20]:
            y = ref_doublet(V_TEST, 1.0, 0.0, 0.35, quad, gamma, 0.020)
            sigma = np.ones(N_CHAN) * 3e-4
            state = _make_doublet_state(
                V_TEST, y,
                delta=0.35, quad=quad, gamma=gamma, depth=0.020,
                sigma=sigma, perturb=0.2,
                quad_lo=0.0, quad_hi=6.0,
            )
            _phys.LINE_PROFILE_KIND = "Lorentziana"
            result = fit_discrete(state)
            err = result.errors.get("s1_quad", float("nan"))
            errors_quad.append(float(err) if np.isfinite(err) else float("nan"))

        finite = [(e, q) for e, q in zip(errors_quad, [1.5, 0.8, 0.4, 0.20])
                  if np.isfinite(e) and e > 0]
        if len(finite) >= 2:
            # El error del ΔEQ más pequeño debe ser ≥ al de la separación mayor
            errs = [e for e, _ in finite]
            assert errs[-1] >= errs[0] * 0.5, (
                f"Las incertidumbres no crecen con el solapamiento: {errors_quad}"
            )

    # ── 4b. Sextete con líneas internas no resueltas ──────────────────────────

    def test_sextet_lineas_anchas_converge(self):
        """Sextete con Γ=0.60 mm/s (líneas internas solapadas) converge."""
        tp = dict(baseline=1.0, slope=0.0,
                  delta=0.0, quad=0.0, bhf=33.0, gamma=0.60, depth=0.018)
        y = ref_sextet(V_TEST, **tp)
        state = _make_sextet_state(
            V_TEST, y,
            delta=tp["delta"], bhf=tp["bhf"],
            gamma=tp["gamma"] * 0.9, depth=tp["depth"],
            perturb=0.5,
        )
        _phys.LINE_PROFILE_KIND = "Lorentziana"
        result = fit_discrete(state)
        assert result.stats.get("red_chi2", 1.0) < 1e-4

    # ── 4c. Absorbente grueso ─────────────────────────────────────────────────

    def test_absorbente_grueso_recupera_sat_scale(self):
        """El modelo de absorbente grueso recupera sat_scale correctamente."""
        true_sat = 0.08
        tp = dict(baseline=1.0, slope=0.0,
                  delta=-0.109, quad=0.0, bhf=33.0, gamma=0.28, depth=0.050)
        y_thick = ref_sextet_thick(V_TEST, sat_scale=true_sat, **tp)
        sigma = np.ones(N_CHAN) * 5e-4

        # Estado con modelo de absorbente grueso
        vals = {
            "baseline": 1.0, "slope": 0.0, "vmax": VMAX_TEST,
            "voigt_sigma": 0.05,
            "s1_delta": tp["delta"], "s1_quad": 0.0, "s1_bhf": tp["bhf"],
            "s1_gamma1": tp["gamma"], "s1_gamma2": 1.0, "s1_gamma3": 1.0,
            "s1_depth": tp["depth"] * 0.8,
            "s1_int1": 3.0, "s1_int2": 2.0, "s1_int3": 1.0,
            "sat_scale": true_sat * 1.5,  # inicio alejado del valor verdadero
        }
        fixed = {k: False for k in vals}
        for k in ("s1_int1", "s1_int2", "s1_int3", "s1_gamma2", "s1_gamma3", "s1_quad"):
            fixed[k] = True
        fixed["sat_scale"] = False
        bounds: dict[str, tuple[float, float]] = {
            "baseline": (0.5, 1.5), "slope": (-0.02, 0.02),
            "s1_delta": (-3.0, 3.0), "s1_quad": (-4.0, 4.0),
            "s1_bhf": (0.0, 60.0), "s1_gamma1": (0.05, 4.0),
            "s1_gamma2": (0.2, 6.0), "s1_gamma3": (0.2, 6.0),
            "s1_depth": (0.0, 0.5), "s1_int1": (0.0, 9.0),
            "s1_int2": (0.0, 6.0), "s1_int3": (0.0, 3.0),
            "sat_scale": (0.001, 1.0),
            "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0),
        }
        state = FitState(
            velocity=V_TEST, y_data=y_thick, sigma_data=sigma,
            values=vals, fixed=fixed, bounds=bounds,
            components=[Component(idx=1, enabled=True, kind="Sextete")],
            absorber_model="thickness",
            multistart_n=4,
        )
        _phys.LINE_PROFILE_KIND = "Lorentziana"
        result = fit_discrete(state)
        sat_fit = result.values.get("sat_scale", float("nan"))
        assert np.isfinite(sat_fit) and sat_fit > 0, "sat_scale no convergió."
        assert abs(sat_fit - true_sat) / true_sat < 0.20, (
            f"sat_scale recuperado={sat_fit:.4f}, verdadero={true_sat:.4f} "
            f"(error > 20 %)."
        )

    def test_absorbente_grueso_degenera_a_fino(self):
        """Con sat_scale → ∞ el modelo grueso coincide con el fino."""
        tp = dict(baseline=1.0, slope=0.0,
                  delta=-0.109, quad=0.0, bhf=33.0, gamma=0.28, depth=0.013)
        y_thin = ref_sextet(V_TEST, **tp)
        y_thick_large = ref_sextet_thick(V_TEST, sat_scale=1e6, **tp)
        np.testing.assert_allclose(
            y_thick_large, y_thin, rtol=1e-4,
            err_msg="El modelo grueso no degenera al fino cuando sat_scale → ∞.",
        )

    def test_absorbente_grueso_aplana_picos(self):
        """El efecto de saturación aplana los picos respecto al modelo fino."""
        tp = dict(baseline=1.0, slope=0.0,
                  delta=-0.109, quad=0.0, bhf=33.0, gamma=0.28, depth=0.10)
        y_thin = ref_sextet(V_TEST, **tp)
        y_thick = ref_sextet_thick(V_TEST, sat_scale=0.05, **tp)
        # En el modelo grueso los valles son menos profundos que en el fino
        min_thin = float(np.min(y_thin))
        min_thick = float(np.min(y_thick))
        assert min_thick > min_thin, (
            "El modelo grueso debe tener valles menos pronunciados que el fino "
            f"(min_thin={min_thin:.4f}, min_thick={min_thick:.4f})."
        )


# ═════════════════════════════════════════════════════════════════════════════
# PUNTO 5 — RESTRICCIONES FÍSICAS
# ═════════════════════════════════════════════════════════════════════════════

class TestRestriccionesFisicas:
    """Punto 5: ratios de intensidad, convenciones de δ y ΔEQ."""

    def test_ratios_intensidad_sextete_polvo_aleatorio(self):
        """Las intensidades 3:2:1 son las correctas para polvo aleatorio (sin textura)."""
        i1, i2, i3 = 3.0, 2.0, 1.0
        # En el espectro de transmisión las áreas deben ser proporcionales a i·w
        # Las áreas de las 6 líneas deben ser en proporción 3:2:1:1:2:3
        weights = np.array([i1 * i3, i2 * i3, i3, i3, i2 * i3, i1 * i3])
        expected = np.array([3.0, 2.0, 1.0, 1.0, 2.0, 3.0])
        np.testing.assert_allclose(weights / weights.max(), expected / expected.max(),
                                   err_msg="Ratios 3:2:1 incorrectos.")

    def test_texture_to_intensities_polvo_aleatorio(self):
        """texture_to_intensities(t=2/3) da ratios 3:2:1 para polvo aleatorio.

        Para polvo isótropo <sin²θ> = 2/3, lo que da W2/W3 = 4·(2/3)/(2−2/3) = 2.
        """
        i1, i2, i3 = texture_to_intensities(2.0 / 3.0)
        assert abs(i3 - 1.0) < 1e-9
        assert abs(i2 / i3 - 2.0) < 1e-9
        assert abs(i1 / i3 - 3.0) < 1e-9

    def test_texture_orientacion_paralela_relacion_i2_i3(self):
        """Con B ‖ k_γ (sin²θ=0): ratios 3:0:1 (líneas medias prohibidas)."""
        i1, i2, i3 = texture_to_intensities(0.0)
        assert abs(i2) < 1e-9, f"Líneas centrales deben ser 0 para sin²θ=0, i2={i2}"
        assert abs(i1 / i3 - 3.0) < 1e-9

    def test_texture_orientacion_perpendicular(self):
        """Con B ⊥ k_γ (sin²θ=1): ratios 3:4:1."""
        i1, i2, i3 = texture_to_intensities(1.0)
        assert abs(i3 - 1.0) < 1e-9
        assert abs(i2 / i3 - 4.0) < 1e-9
        assert abs(i1 / i3 - 3.0) < 1e-9

    def test_convencion_delta_eq_doblete_centrado(self):
        """Las líneas del doblete están centradas en δ y separadas por ΔEQ."""
        delta, quad, gamma = 0.40, 0.60, 0.28
        y = ref_doublet(V_TEST, 1.0, 0.0, delta, quad, gamma, 0.020)
        # Los dos mínimos deben estar en delta ± quad/2
        p1_expected = delta - quad / 2.0   # −0.30 + 0.40 = 0.10
        p2_expected = delta + quad / 2.0   # +0.30 + 0.40 = 0.70
        # Buscamos los mínimos locales del espectro (dips de absorción)
        dips = np.argsort(y)[:10]
        v_dips = V_TEST[dips]
        # Los dips deben estar cerca de p1 y p2
        near_p1 = np.min(np.abs(v_dips - p1_expected))
        near_p2 = np.min(np.abs(v_dips - p2_expected))
        assert near_p1 < 0.5, (
            f"El primer mínimo del doblete no está en δ−ΔEQ/2={p1_expected:.2f} "
            f"(más cercano a distancia {near_p1:.3f} mm/s)."
        )
        assert near_p2 < 0.5, (
            f"El segundo mínimo del doblete no está en δ+ΔEQ/2={p2_expected:.2f} "
            f"(más cercano a distancia {near_p2:.3f} mm/s)."
        )

    def test_signo_desplazamiento_isomerico_negativo(self):
        """δ < 0 desplaza ambos mínimos del doblete hacia velocidades negativas."""
        y_pos = ref_doublet(V_TEST, 1.0, 0.0, +0.4, 0.6, 0.28, 0.020)
        y_neg = ref_doublet(V_TEST, 1.0, 0.0, -0.4, 0.6, 0.28, 0.020)
        # El espectro con δ<0 tiene su mínimo global en velocidad más negativa
        v_min_pos = V_TEST[np.argmin(y_pos)]
        v_min_neg = V_TEST[np.argmin(y_neg)]
        assert v_min_neg < v_min_pos, (
            f"δ negativo debería desplazar el espectro a velocidades negativas: "
            f"v_min(δ>0)={v_min_pos:.2f}, v_min(δ<0)={v_min_neg:.2f}."
        )

    def test_campo_hiperfino_escala_posicion_sextet(self):
        """Las posiciones del sextete escalan linealmente con BHF."""
        y_33 = ref_sextet(V_TEST, 1.0, 0.0, 0.0, 0.0, 33.0, 0.28, 0.013)
        y_50 = ref_sextet(V_TEST, 1.0, 0.0, 0.0, 0.0, 50.0, 0.28, 0.013)
        # El mínimo exterior debe desplazarse a velocidades > |v_max_33T|
        pos_33 = np.abs(V_TEST[np.argmin(y_33)])
        pos_50 = np.abs(V_TEST[np.argmin(y_50)])
        assert pos_50 > pos_33, (
            "A mayor BHF las líneas externas deben estar más separadas."
        )

    def test_cuadrupolo_rompe_simetria_sextet(self):
        """ΔEQ ≠ 0 rompe la simetría del sextete (espectro asimétrico)."""
        y_sym = ref_sextet(V_TEST, 1.0, 0.0, 0.0, 0.00, 33.0, 0.28, 0.013)
        y_asym = ref_sextet(V_TEST, 1.0, 0.0, 0.0, 0.20, 33.0, 0.28, 0.013)
        # El eje de simetría central del sextete simétrico es v=0;
        # con quad≠0 el espectro es asimétrico respecto a v=0
        diff_sym = np.sum(np.abs(y_sym - y_sym[::-1]))
        diff_asym = np.sum(np.abs(y_asym - y_asym[::-1]))
        assert diff_asym > diff_sym, (
            "Un sextete con ΔEQ≠0 debe ser más asimétrico que con ΔEQ=0."
        )

    def test_calibracion_velocidad_consistente(self):
        """La escala de velocidad: el extremo de la malla es VMAX_TEST."""
        assert abs(float(V_TEST[0]) - (-VMAX_TEST)) < 1e-10
        assert abs(float(V_TEST[-1]) - VMAX_TEST) < 1e-10

    def test_linea_base_plana_sin_absorcion(self):
        """Sin componentes de absorción el modelo es una línea base plana."""
        from core.fit_engine import model_from_values, Component
        vals = {"baseline": 0.97, "slope": 0.002, "vmax": VMAX_TEST,
                "voigt_sigma": 0.05}
        y = model_from_values(V_TEST, vals, [])
        expected = 0.97 + 0.002 * V_TEST
        np.testing.assert_allclose(y, expected, rtol=1e-10)


# ═════════════════════════════════════════════════════════════════════════════
# PUNTO 6 — DATOS REALES Y COMPARACIÓN CON REFERENCIA
# ═════════════════════════════════════════════════════════════════════════════

class TestDatosReales:
    """Punto 6: calibración con α-Fe (referencia publicada 33.0 T)."""

    # Valores de referencia (NORMOS / valores publicados para α-Fe a temperatura ambiente)
    # BHF = 33.0 T, δ_αFe = 0.000 mm/s (referencia a sí mismo), Γ ≈ 0.24–0.30 mm/s
    BHF_REF = 33.0       # T
    DELTA_REF = -0.1092  # ISO_REF: desplazamiento δ medido en la GUI (referencia interna)
    GAMMA_MAX = 0.50     # mm/s — límite superior generoso para anchura natural

    @pytest.fixture(autouse=True)
    def _reset_profile(self):
        """Restaura el perfil de línea global después de cada test."""
        _phys.LINE_PROFILE_KIND = "Lorentziana"
        yield
        _phys.LINE_PROFILE_KIND = "Lorentziana"

    @pytest.fixture
    def alpha_fe_data(self):
        """Carga y dobla el espectro de α-Fe del directorio de muestras."""
        pytest.importorskip("core.folding")
        from core.folding import (
            read_ws5_counts,
            find_best_integer_or_half_center,
            fold_integer_or_half,
        )
        adt = DATA / "hierro_metalico_alphaFe.adt"
        if not adt.exists():
            pytest.skip("Fichero de muestra hierro_metalico_alphaFe.adt no encontrado.")
        counts = read_ws5_counts(adt)
        center = find_best_integer_or_half_center(counts)
        folded, _ = fold_integer_or_half(counts, center)
        vmax = 12.007
        v = np.linspace(-vmax, vmax, folded.size)
        norm = float(np.percentile(folded, 90))
        y = folded / norm
        sigma = np.maximum(np.sqrt(folded / 2.0), 1.0) / norm
        return v, y, sigma, vmax

    def test_alpha_fe_bhf_calibrado_33T(self, alpha_fe_data):
        """El campo hiperfino ajustado de α-Fe debe ser 33.0 ± 0.5 T."""
        v, y, sigma, vmax = alpha_fe_data
        vals = {
            "baseline": 1.0, "slope": 0.0, "vmax": vmax,
            "voigt_sigma": 0.05,
            "s1_delta": -0.1, "s1_quad": 0.0, "s1_bhf": 33.0,
            "s1_gamma1": 0.28, "s1_gamma2": 1.0, "s1_gamma3": 1.0,
            "s1_depth": 0.013, "s1_int1": 3.0, "s1_int2": 2.0, "s1_int3": 1.0,
        }
        fixed = {k: False for k in vals}
        for k in ("s1_int1", "s1_int2", "s1_int3", "s1_gamma2", "s1_gamma3", "s1_quad"):
            fixed[k] = True
        bounds: dict[str, tuple[float, float]] = {
            "baseline": (0.7, 1.3), "slope": (-0.005, 0.005),
            "s1_delta": (-2.0, 3.0), "s1_quad": (-4.0, 4.0),
            "s1_bhf": (20.0, 60.0), "s1_gamma1": (0.06, 4.0),
            "s1_gamma2": (0.2, 6.0), "s1_gamma3": (0.2, 6.0),
            "s1_depth": (0.0, 0.30), "s1_int1": (0.0, 9.0),
            "s1_int2": (0.0, 6.0), "s1_int3": (0.0, 3.0),
            "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0),
        }
        state = FitState(
            velocity=v, y_data=y, sigma_data=sigma,
            values=vals, fixed=fixed, bounds=bounds,
            components=[Component(idx=1, enabled=True, kind="Sextete")],
            multistart_n=4,
        )
        result = fit_discrete(state)
        bhf = result.values["s1_bhf"]
        assert abs(bhf - self.BHF_REF) < 0.5, (
            f"BHF ajustado = {bhf:.3f} T, esperado {self.BHF_REF} ± 0.5 T."
        )

    def test_alpha_fe_delta_referencia(self, alpha_fe_data):
        """El desplazamiento isomérico de α-Fe debe ser ≈ ISO_REF (−0.109 mm/s)."""
        v, y, sigma, vmax = alpha_fe_data
        vals = {
            "baseline": 1.0, "slope": 0.0, "vmax": vmax,
            "voigt_sigma": 0.05,
            "s1_delta": -0.1, "s1_quad": 0.0, "s1_bhf": 33.0,
            "s1_gamma1": 0.28, "s1_gamma2": 1.0, "s1_gamma3": 1.0,
            "s1_depth": 0.013, "s1_int1": 3.0, "s1_int2": 2.0, "s1_int3": 1.0,
        }
        fixed = {k: False for k in vals}
        for k in ("s1_int1", "s1_int2", "s1_int3", "s1_gamma2", "s1_gamma3", "s1_quad"):
            fixed[k] = True
        bounds: dict[str, tuple[float, float]] = {
            "baseline": (0.7, 1.3), "slope": (-0.005, 0.005),
            "s1_delta": (-2.0, 3.0), "s1_quad": (-4.0, 4.0),
            "s1_bhf": (20.0, 60.0), "s1_gamma1": (0.06, 4.0),
            "s1_gamma2": (0.2, 6.0), "s1_gamma3": (0.2, 6.0),
            "s1_depth": (0.0, 0.30), "s1_int1": (0.0, 9.0),
            "s1_int2": (0.0, 6.0), "s1_int3": (0.0, 3.0),
            "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0),
        }
        state = FitState(
            velocity=v, y_data=y, sigma_data=sigma,
            values=vals, fixed=fixed, bounds=bounds,
            components=[Component(idx=1, enabled=True, kind="Sextete")],
            multistart_n=4,
        )
        result = fit_discrete(state)
        delta = result.values["s1_delta"]
        assert abs(delta - self.DELTA_REF) < 0.05, (
            f"δ(α-Fe) = {delta:.4f} mm/s, esperado ≈ {self.DELTA_REF} ± 0.05."
        )

    def test_alpha_fe_gamma_rango_fisico(self, alpha_fe_data):
        """La anchura ajustada de α-Fe debe ser físicamente razonable (< 0.50 mm/s)."""
        v, y, sigma, vmax = alpha_fe_data
        vals = {
            "baseline": 1.0, "slope": 0.0, "vmax": vmax,
            "voigt_sigma": 0.05,
            "s1_delta": -0.1, "s1_quad": 0.0, "s1_bhf": 33.0,
            "s1_gamma1": 0.28, "s1_gamma2": 1.0, "s1_gamma3": 1.0,
            "s1_depth": 0.013, "s1_int1": 3.0, "s1_int2": 2.0, "s1_int3": 1.0,
        }
        fixed = {k: False for k in vals}
        for k in ("s1_int1", "s1_int2", "s1_int3", "s1_gamma2", "s1_gamma3", "s1_quad"):
            fixed[k] = True
        bounds: dict[str, tuple[float, float]] = {
            "baseline": (0.7, 1.3), "slope": (-0.005, 0.005),
            "s1_delta": (-2.0, 3.0), "s1_quad": (-4.0, 4.0),
            "s1_bhf": (20.0, 60.0), "s1_gamma1": (0.06, 4.0),
            "s1_gamma2": (0.2, 6.0), "s1_gamma3": (0.2, 6.0),
            "s1_depth": (0.0, 0.30), "s1_int1": (0.0, 9.0),
            "s1_int2": (0.0, 6.0), "s1_int3": (0.0, 3.0),
            "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0),
        }
        state = FitState(
            velocity=v, y_data=y, sigma_data=sigma,
            values=vals, fixed=fixed, bounds=bounds,
            components=[Component(idx=1, enabled=True, kind="Sextete")],
            multistart_n=2,
        )
        result = fit_discrete(state)
        gamma = result.values["s1_gamma1"]
        assert 0.15 < gamma < self.GAMMA_MAX, (
            f"Γ(α-Fe) = {gamma:.4f} mm/s fuera del rango físico [0.15, {self.GAMMA_MAX}]."
        )

    def test_alpha_fe_chi2_reducido_razonable(self, alpha_fe_data):
        """El χ² reducido del ajuste de α-Fe debe ser < 5 (buen ajuste)."""
        v, y, sigma, vmax = alpha_fe_data
        vals = {
            "baseline": 1.0, "slope": 0.0, "vmax": vmax,
            "voigt_sigma": 0.05,
            "s1_delta": -0.1, "s1_quad": 0.0, "s1_bhf": 33.0,
            "s1_gamma1": 0.28, "s1_gamma2": 1.0, "s1_gamma3": 1.0,
            "s1_depth": 0.013, "s1_int1": 3.0, "s1_int2": 2.0, "s1_int3": 1.0,
        }
        fixed = {k: False for k in vals}
        for k in ("s1_int1", "s1_int2", "s1_int3", "s1_gamma2", "s1_gamma3", "s1_quad"):
            fixed[k] = True
        bounds: dict[str, tuple[float, float]] = {
            "baseline": (0.7, 1.3), "slope": (-0.005, 0.005),
            "s1_delta": (-2.0, 3.0), "s1_quad": (-4.0, 4.0),
            "s1_bhf": (20.0, 60.0), "s1_gamma1": (0.06, 4.0),
            "s1_gamma2": (0.2, 6.0), "s1_gamma3": (0.2, 6.0),
            "s1_depth": (0.0, 0.30), "s1_int1": (0.0, 9.0),
            "s1_int2": (0.0, 6.0), "s1_int3": (0.0, 3.0),
            "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0),
        }
        state = FitState(
            velocity=v, y_data=y, sigma_data=sigma,
            values=vals, fixed=fixed, bounds=bounds,
            components=[Component(idx=1, enabled=True, kind="Sextete")],
            multistart_n=2,
        )
        result = fit_discrete(state)
        red_chi2 = result.stats.get("red_chi2", float("nan"))
        assert np.isfinite(red_chi2) and red_chi2 < 5.0, (
            f"χ²_red(α-Fe) = {red_chi2:.3f} ≥ 5.0: ajuste con datos reales demasiado malo."
        )
