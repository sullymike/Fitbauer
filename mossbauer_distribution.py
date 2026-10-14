#!/usr/bin/env python3
"""Ajuste de distribucion de campo hiperfino P(BHF) para espectros Mossbauer.

Implementa un primer backend independiente tipo Hesse-Ruebartsch: el espectro se
modela como una suma regularizada de sextetes con distintos BHF y pesos no
negativos::

    y(v) = baseline + slope * v - sum_j P_j * sextet(v; delta, quad, gamma, B_j)

La regularizacion penaliza segundas diferencias de P. No hay GUI aqui; este
modulo esta pensado para ser llamado desde pruebas, endpoints web o una futura
interfaz.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import lsq_linear, nnls

# Los perfiles de absorción de este módulo son adaptadores de convención sobre
# core.physics (posiciones del sextete = patrón PUBLICADO de α-Fe a 33 T, igual
# que NORMOS; ver CHANGELOG v4.0.2/v4.0.3): aquí solo se traduce la convención
# relativa de intensidades del GUI (int2_rel/int3_rel) a pesos por línea.
from core.constants import BHF_DEFAULT_T
from mossbauer_i18n import tr
from core import physics as core_physics
from core.residual_diagnostics import residual_lag1, residual_runs_z  # noqa: F401 (reexport)
from core.physics import (
    line_profile,
    lognormal_diameter_distribution,
    neel_log10_nu,
)


def _rel_weights_gammas(
    gamma: float, gamma2_rel: float, gamma3_rel: float,
    int1: float, int2_rel: float, int3_rel: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Pesos y anchuras por línea de la convención relativa del GUI.

    int2_rel=1 -> I2=(2/3)·I1; int3_rel=1 -> I3=(1/3)·I1 (patrón 3:2:1).

    Respeta el convenio global ``core.physics.INTENSITY_CONVENTION``: con
    ``"area"`` las razones son de ÁREA (lo que significan D13/D23 en NORMOS y
    lo que son físicamente las probabilidades de transición), con ``"depth"``
    de profundidad. Solo se separan si las anchuras relativas no son 1.
    """
    i1 = float(int1)
    i2 = i1 * (2.0 / 3.0) * float(int2_rel)
    i3 = i1 * (1.0 / 3.0) * float(int3_rel)
    weights = np.array([i1, i2, i3, i3, i2, i1], dtype=float)
    gammas = float(gamma) * np.array(
        [1.0, gamma2_rel, gamma3_rel, gamma3_rel, gamma2_rel, 1.0], dtype=float)
    if core_physics.INTENSITY_CONVENTION == "area":
        weights = core_physics._area_to_depth_weights(weights, gammas)
    return weights, gammas


# Calibración del α adimensional del ajuste de distribución (ver
# `fit_hyperfine_distribution`): centra el codo de la L-curve en log α ≈ 0 para
# una configuración típica una vez normalizado el penalizador por λ_ref.
ALPHA_REF_SCALE = 1e-4


@dataclass(frozen=True)
class BhfQuadDistribution2DFit:
    """Resultado de una distribución bidimensional P(BHF, ΔEQ)."""

    bhf_centers: np.ndarray
    quad_centers: np.ndarray
    weights: np.ndarray
    probability: np.ndarray
    fitted_curve: np.ndarray
    residuals: np.ndarray
    baseline: float
    slope: float
    alpha_bhf: float
    alpha_quad: float
    rms: float
    success: bool
    message: str
    x_variable: str = "bhf"
    y_variable: str = "quad"
    effective_dof: float | None = None
    marginal_bhf: np.ndarray | None = None
    marginal_quad: np.ndarray | None = None
    mean_bhf: float | None = None
    mean_quad: float | None = None
    sigma_bhf: float | None = None
    sigma_quad: float | None = None
    corr_bhf_quad: float | None = None
    dof_warning: str | None = None
    sharp_bhf_centers: np.ndarray | None = None
    sharp_weights: np.ndarray | None = None
    shape: str | None = "2D"
    #: Formas paramétricas 2D: (A, μx, μy, σx, σy, ρ) por gaussiana bivariante.
    vbf2d_components: tuple[tuple[float, float, float, float, float, float], ...] | None = None
    #: δ/ΔEQ/Γ globales ajustados junto con las gaussianas 2D (solo los libres).
    fitted_globals: dict[str, float] | None = None
    #: Límites de anchura aplicados a las gaussianas 2D:
    #: ``((σx_mín, σx_máx), (σy_mín, σy_máx))``, en unidades de cada eje.
    vbf2d_sigma_bounds: tuple[tuple[float, float], tuple[float, float]] | None = None
    #: Valores finales de los globales (δ, ΔEQ, Γ, pendientes) y cuáles se
    #: refinaron, y su covarianza {(clave_i, clave_j): cov} (los pone la GUI).
    global_values: dict | None = None
    global_cov: dict | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "shape": self.shape,
            "vbf2d_components": ([] if self.vbf2d_components is None
                                 else [list(c) for c in self.vbf2d_components]),
            "fitted_globals": dict(self.fitted_globals or {}),
            "vbf2d_sigma_bounds": (None if self.vbf2d_sigma_bounds is None
                                   else [list(b) for b in self.vbf2d_sigma_bounds]),
            "BHF_centers": self.bhf_centers.tolist(),
            "quad_centers": self.quad_centers.tolist(),
            "P": self.weights.tolist(),
            "probability": self.probability.tolist(),
            "fitted_curve": self.fitted_curve.tolist(),
            "residuals": self.residuals.tolist(),
            "baseline": self.baseline,
            "slope": self.slope,
            "alpha_bhf": self.alpha_bhf,
            "alpha_quad": self.alpha_quad,
            "rms": self.rms,
            "x_variable": self.x_variable,
            "y_variable": self.y_variable,
            "success": self.success,
            "message": self.message,
            "effective_dof": self.effective_dof,
            "marginal_bhf": [] if self.marginal_bhf is None else self.marginal_bhf.tolist(),
            "marginal_quad": [] if self.marginal_quad is None else self.marginal_quad.tolist(),
            "mean_bhf": self.mean_bhf,
            "mean_quad": self.mean_quad,
            "sigma_bhf": self.sigma_bhf,
            "sigma_quad": self.sigma_quad,
            "corr_bhf_quad": self.corr_bhf_quad,
            "dof_warning": self.dof_warning,
            "sharp_BHF_centers": [] if self.sharp_bhf_centers is None else self.sharp_bhf_centers.tolist(),
            "sharp_weights": [] if self.sharp_weights is None else self.sharp_weights.tolist(),
        }


@dataclass(frozen=True)
class BhfDistributionFit:
    """Resultado del ajuste de distribucion de BHF."""

    bhf_centers: np.ndarray
    weights: np.ndarray
    probability: np.ndarray
    fitted_curve: np.ndarray
    residuals: np.ndarray
    baseline: float
    slope: float
    alpha: float
    rms: float
    success: bool
    message: str
    sharp_bhf_centers: np.ndarray | None = None
    sharp_weights: np.ndarray | None = None
    fitted_dist_center: float | None = None
    fitted_dist_sigma: float | None = None
    fitted_dist_p: float | None = None
    effective_dof: float | None = None
    weight_sigma: np.ndarray | None = None
    #: σ por bin de ``probability`` por Monte Carlo paramétrico (respeta P≥0);
    #: solo si se pidió ``band_replicas``. Es la que se dibuja como banda.
    probability_sigma: np.ndarray | None = None
    # VBF multi-gaussiano: lista de componentes (A_k, μ_k, σ_k) ordenados por μ.
    vbf_components: tuple[tuple[float, float, float], ...] | None = None
    # Metadatos del ajuste (para informes/sesión): forma, regularizador y
    # pendientes de correlación δ(H)/ΔEQ(H) efectivamente aplicadas.
    shape: str | None = None
    reg_mode: str | None = None
    delta_slope: float = 0.0
    quad_slope: float = 0.0
    #: Valor de la variable de la malla en el que δ y ΔEQ valen sus globales:
    #: δ(x) = δ + delta_slope·(x − slope_ref), ídem ΔEQ(x). Es la media de la
    #: malla (o el valor sin vecinos de la binomial).
    slope_ref: float | None = None
    #: Lo rellena quien orquesta el ajuste (la GUI) cuando refina δ/ΔEQ y las
    #: pendientes en una capa externa: variable de la malla, valores finales
    #: de los globales y su covarianza ``{(clave_i, clave_j): cov}``. Solo
    #: en memoria (no van a ``as_dict``).
    fit_variable: str | None = None
    global_values: dict | None = None
    global_cov: dict | None = None
    vbf_n_components: int | None = None
    #: Límites de anchura ``(σ_mín, σ_máx)`` aplicados a las gaussianas del VBF
    #: (y de la Gaussiana), en unidades de la variable distribuida.
    vbf_sigma_bounds: tuple[float, float] | None = None
    #: Binomial de vecinos (NORMOS DISTRI=3): valor sin vecinos, paso por
    #: vecino y nº de vecinos. La concentración ajustada va en fitted_dist_p.
    binomial_start: float | None = None
    binomial_step: float | None = None
    binomial_n: int | None = None
    #: Czjzek (``shape="Czjzek"``/``"Czjzek ext."``): escala σ del desorden
    #: aleatorio y ΔEQ₀ del entorno ordenado (``None`` en el modelo puro),
    #: con sus errores 1σ.
    czjzek_sigma: float | None = None
    czjzek_sigma_err: float | None = None
    czjzek_delta0: float | None = None
    czjzek_delta0_err: float | None = None
    #: Covarianza 2×2 de (media, desviación) de P debida al ruido con los
    #: globales (δ, ΔEQ, Γ, κ) FIJOS: de las réplicas Monte Carlo en el
    #: histograma, de la covarianza de los parámetros en las formas
    #: paramétricas. La GUI le suma la parte que viene de los globales.
    moment_cov: np.ndarray | None = None
    #: Diagnóstico de MALLA INSUFICIENTE: ``max(P[0], P[-1]) / max(P)``.
    #:
    #: Si la distribución real se sale del rango, el histograma de
    #: Hesse–Rübartsch no tiene dónde poner ese peso y lo APILA en el bin
    #: extremo. Un valor alto (≳0.3) significa que hay que ampliar la malla:
    #: en un caso medido, truncar una gaussiana centrada en 45 T a un rango
    #: 0–40 T dejaba el último bin al 100 % del máximo y hundía ⟨B⟩ de 44.9 a
    #: 28.5 T. El anclaje ``edge_anchor`` encarece ese refugio, pero no
    #: sustituye a elegir bien el rango.
    edge_pileup: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """Devuelve un dict serializable en JSON tras convertir arrays a listas."""
        return {
            "BHF_centers": self.bhf_centers.tolist(),
            "P": self.weights.tolist(),
            "probability": self.probability.tolist(),
            "fitted_curve": self.fitted_curve.tolist(),
            "residuals": self.residuals.tolist(),
            "baseline": self.baseline,
            "slope": self.slope,
            "alpha": self.alpha,
            "rms": self.rms,
            "success": self.success,
            "message": self.message,
            "sharp_BHF_centers": [] if self.sharp_bhf_centers is None else self.sharp_bhf_centers.tolist(),
            "sharp_weights": [] if self.sharp_weights is None else self.sharp_weights.tolist(),
            "fitted_dist_center": self.fitted_dist_center,
            "fitted_dist_sigma": self.fitted_dist_sigma,
            "fitted_dist_p": self.fitted_dist_p,
            "effective_dof": self.effective_dof,
            "weight_sigma": [] if self.weight_sigma is None else self.weight_sigma.tolist(),
            "probability_sigma": ([] if self.probability_sigma is None
                                  else self.probability_sigma.tolist()),
            "vbf_components": [] if self.vbf_components is None else [list(c) for c in self.vbf_components],
            "shape": self.shape,
            "reg_mode": self.reg_mode,
            "delta_slope": self.delta_slope,
            "quad_slope": self.quad_slope,
            "slope_ref": self.slope_ref,
            "vbf_n_components": self.vbf_n_components,
            "vbf_sigma_bounds": (None if self.vbf_sigma_bounds is None
                                 else list(self.vbf_sigma_bounds)),
            "binomial_start": self.binomial_start,
            "binomial_step": self.binomial_step,
            "binomial_n": self.binomial_n,
            "czjzek_sigma": self.czjzek_sigma,
            "czjzek_sigma_err": self.czjzek_sigma_err,
            "czjzek_delta0": self.czjzek_delta0,
            "czjzek_delta0_err": self.czjzek_delta0_err,
            "moment_cov": None if self.moment_cov is None else self.moment_cov.tolist(),
        }


def sextet_absorption(
    v: np.ndarray,
    *,
    delta: float,
    quad: float,
    bhf: float,
    gamma: float,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    treatment: str = "1st_order",
    eta: float = 0.0,
    n_orient: int = 12,
) -> np.ndarray:
    """Absorcion positiva de un sextete Fe-57 con profundidad unitaria.

    Las intensidades siguen la convencion del GUI actual:
    int2_rel=1 -> I2=(2/3)*I1; int3_rel=1 -> I3=(1/3)*I1.
    La física (posiciones y suma de líneas) vive en ``core.physics``; aquí
    solo se traduce la convención de pesos.

    ``treatment="hamiltonian"`` (banco NORMOS-2, serie L4): en lugar del
    patrón rígido de 1er orden, cada evaluación es el promedio de polvo del
    Hamiltoniano completo (EFG aleatorio respecto a B): cuadratura
    Gauss-Legendre en cosβ (``n_orient`` nodos) y, si ``eta``>0, promedio en
    φ ∈ [0, π/2]. Es el análogo exacto del EXACT de NORMOS-DIST (orden
    mixto), sin truncar a teoría de perturbaciones.
    """
    v = np.asarray(v, dtype=float)
    weights, gammas = _rel_weights_gammas(gamma, gamma2_rel, gamma3_rel,
                                          int1, int2_rel, int3_rel)
    if str(treatment) == "hamiltonian":
        # Promedio de polvo en el MARCO DEL CAMPO (B∥z, EFG inclinado): los
        # canales q — y la textura int1/int2 — quedan ligados a B, que es lo
        # físico para el análogo del EXACT de DIST (con textura en el marco
        # del EFG el promedio la diluiría a isótropa).
        from core.hamiltonian import full_hamiltonian_lines_field
        w1, w2 = float(weights[0]), float(weights[1])
        x, wq = np.polynomial.legendre.leggauss(max(4, int(n_orient)))
        thetas = np.arccos(np.clip(x, -1.0, 1.0))
        # El término η del EFG tiene simetría C2v: basta φ ∈ [0, π/2].
        phis = ([np.pi / 16, 3 * np.pi / 16, 5 * np.pi / 16, 7 * np.pi / 16]
                if abs(float(eta)) > 1e-9 else [0.0])
        g_by_class = {1: float(gammas[0]), 2: float(gammas[1]),
                      3: float(gammas[2])}
        acc = np.zeros_like(v)
        for th, wt in zip(thetas, 0.5 * wq):
            for ph in phis:
                pos, inten, wcls = full_hamiltonian_lines_field(
                    float(bhf), float(delta), float(quad), eta=float(eta),
                    theta=float(th), phi=float(ph),
                    int1=w1, int2=w2)
                gam8 = np.array([g_by_class[int(c)] for c in wcls])
                acc += (wt / len(phis)) * core_physics.sum_lorentzian_lines(
                    v, pos, inten, gam8)
        return acc
    if str(treatment) == "polarized":
        # Fuente polarizada (METHOD=4 de NORMOS-DIST): los parámetros de la
        # fuente viajan en el propio wrapper vía atributos de módulo para no
        # engordar la cadena de firmas (se fijan en build_bhf_kernel).
        return _POL_STATE["weight_scale"] * polarized_sextet_absorption(
            v, delta=delta, quad=quad, bhf=bhf, gamma=gamma,
            source_bhf=_POL_STATE["source_bhf"],
            source_theta=_POL_STATE["source_theta"],
            absorber_theta=_POL_STATE["absorber_theta"])
    if str(treatment) != "1st_order":
        # Un tratamiento desconocido caía en silencio al 1er orden
        # (auditoría de tests 2026-08-02).
        raise ValueError(f"treatment de kernel desconocido: {treatment!r}")
    positions = core_physics.sextet_line_positions(delta, quad, bhf)
    return core_physics.sum_lorentzian_lines(v, positions, weights, gammas)


# ── Fuente polarizada (paridad NORMOS-DIST METHOD=4, fuente propia) ─────────
# Física de primeros principios, validada contra el binario de DIST:
# la FUENTE es un sexteto emisor con campo B_src formando ángulo θ_s con el
# haz; el ABSORBENTE tiene su campo a ángulo θ_a. Cada línea (transición
# Zeeman pura, canal q = Δm definido) emite/absorbe fotones de helicidad
# λ = ±1 con peso |d¹_{qλ}(θ)|², y la intensidad del par (i, j) es
#
#   I(i,j) ∝ |m_q(i)|² |m_q(j)|² Σ_λ |d¹_{q_i λ}(θ_s)|² |d¹_{q_j λ}(θ_a)|²
#
# con |m_q|² = (1, 2/3, 1/3) (Clebsch-Gordan ⁵⁷Fe). En el caso alineado
# (θ_s = θ_a = 0) esto es la SELECCIÓN DE HELICIDAD pura (solo pares con
# Δm_i = Δm_j = ±1) y reproduce el METHOD=4 de NORMOS-DIST a 0.4 % del pico
# (sonda THETAS=0); con θ_s = 90° a 1.1 %. Posiciones: peine de 36 líneas
# v = AL_j·B − AL_i·B_src + δ + s_j·ΔEQ.

_POL_Q_LINE = (-1, 0, +1, -1, 0, +1)
_POL_MQ2 = np.array([1.0, 2.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0, 2.0 / 3.0, 1.0])
_POL_QUAD = np.array([0.5, -0.5, -0.5, -0.5, -0.5, 0.5])

# Parámetros de la fuente polarizada para las columnas del kernel (los fija
# build_bhf_kernel; weight_scale mantiene la convención de profundidad).
_POL_STATE = {"source_bhf": 33.0, "source_theta": 0.0,
              "absorber_theta": 0.0, "weight_scale": 1.0}


def polarized_pair_intensities(source_theta_deg: float = 0.0,
                               absorber_theta_deg: float = 0.0) -> np.ndarray:
    """Matriz 6×6 de intensidades fuente×absorbente (suma normalizada a 12)."""
    from core.hamiltonian import _d1_matrix
    ds = _d1_matrix(np.deg2rad(float(source_theta_deg))) ** 2
    da = _d1_matrix(np.deg2rad(float(absorber_theta_deg))) ** 2
    qidx = {-1: 0, 0: 1, 1: 2}
    inten = np.zeros((6, 6))
    for i in range(6):
        for j in range(6):
            s = sum(ds[qidx[_POL_Q_LINE[i]], l] * da[qidx[_POL_Q_LINE[j]], l]
                    for l in (0, 2))
            inten[i, j] = _POL_MQ2[i] * _POL_MQ2[j] * s
    tot = inten.sum()
    return inten * (12.0 / tot) if tot > 0 else inten


def polarized_sextet_absorption(
    v: np.ndarray,
    *,
    delta: float,
    quad: float,
    bhf: float,
    gamma: float,
    source_bhf: float = 33.0,
    source_theta: float = 0.0,
    absorber_theta: float = 0.0,
) -> np.ndarray:
    """Absorción de un sextete medido con FUENTE POLARIZADA (peine 36 líneas).

    Análogo del METHOD=4/POLAR de NORMOS-DIST (véase el bloque de arriba).
    ``source_bhf`` en T; ángulos en grados respecto al haz. Profundidad
    unitaria (pesos suman 12, como el sexteto 3:2:1).
    """
    v = np.asarray(v, dtype=float)
    from core.constants import active_sextet_pattern, BHF_DEFAULT_T
    al = active_sextet_pattern() / BHF_DEFAULT_T
    inten = polarized_pair_intensities(source_theta, absorber_theta)
    out = np.zeros_like(v)
    for i in range(6):
        for j in range(6):
            w = inten[i, j]
            if w <= 1e-12:
                continue
            pos = (al[j] * float(bhf) - al[i] * float(source_bhf)
                   + float(delta) + _POL_QUAD[j] * float(quad))
            out += w * core_physics.lorentzian(v, pos, float(gamma))
    return out


def singlet_absorption(v: np.ndarray, *, delta: float, gamma: float, int1: float = 1.0) -> np.ndarray:
    """Absorcion positiva de un singlete con profundidad unitaria."""
    return core_physics.singlet_absorption(
        np.asarray(v, dtype=float), float(delta), float(gamma), 1.0, float(int1))


def doublet_absorption(
    v: np.ndarray,
    *,
    delta: float,
    quad: float,
    gamma: float,
    gamma2_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
) -> np.ndarray:
    """Absorcion positiva de un doblete con profundidad unitaria.

    Mapeo exacto a ``core.physics.doublet_absorption``: la ``int2`` de core es
    multiplicativa sobre ``int1``, igual que ``int2_rel`` aquí.
    """
    return core_physics.doublet_absorption(
        np.asarray(v, dtype=float), float(delta), float(quad),
        float(gamma), float(gamma2_rel), 1.0, float(int1), float(int2_rel))


def relaxation_empirical_absorption(
    v: np.ndarray,
    *,
    delta: float,
    quad: float,
    bhf: float,
    gamma: float,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    blocked_fraction: float = 1.0,
    log10_nu: float | None = None,
) -> np.ndarray:
    """Perfil unitario fenomenológico: sextete bloqueado + doblete SPM.

    El sigmoide de transición y el emparejamiento de áreas viven en
    ``core.physics``; aquí solo se mezclan los perfiles en convención relativa.
    """
    f_dyn, g_factor = core_physics.relaxation_transition_factors(log10_nu)
    f_blocked = max(0.0, min(1.0, float(blocked_fraction))) * f_dyn
    gamma_eff = float(gamma) * g_factor
    sext = sextet_absorption(
        v, delta=delta, quad=quad, bhf=bhf, gamma=gamma_eff,
        gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel,
        int1=int1, int2_rel=int2_rel, int3_rel=int3_rel,
    )
    doub = doublet_absorption(
        v, delta=delta, quad=quad, gamma=gamma_eff,
        gamma2_rel=gamma2_rel, int1=int1, int2_rel=int2_rel,
    )
    doub = core_physics.match_positive_area(doub, sext, v)
    return f_blocked * sext + (1.0 - f_blocked) * doub


def blume_tjon_two_state_absorption(
    v: np.ndarray,
    *,
    delta: float,
    quad: float,
    bhf: float,
    gamma: float,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    log10_nu: float = 5.0,
) -> np.ndarray:
    weights, gammas = _rel_weights_gammas(gamma, gamma2_rel, gamma3_rel,
                                          int1, int2_rel, int3_rel)
    return core_physics.two_state_sextet_absorption(
        v, delta, quad, bhf, weights, gammas, log10_nu)


def neel_size_relaxation_absorption(
    v: np.ndarray,
    *,
    delta: float,
    quad: float,
    bhf: float,
    gamma: float,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    temperature_k: float = 300.0,
    log10_keff: float = 4.0,
    mean_d_nm: float = 8.0,
    sigma_lognormal: float = 0.25,
    log10_tau0: float = -9.0,
    n_bins: int = 20,
) -> np.ndarray:
    diam, weights = lognormal_diameter_distribution(mean_d_nm, sigma_lognormal, n_bins)
    lognus = neel_log10_nu(diam, temperature_k, log10_keff, log10_tau0)
    total = np.zeros_like(np.asarray(v, dtype=float), dtype=float)
    for w, lognu in zip(weights, lognus):
        total += float(w) * blume_tjon_two_state_absorption(
            v, delta=delta, quad=quad, bhf=bhf, gamma=gamma,
            gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel,
            int1=int1, int2_rel=int2_rel, int3_rel=int3_rel,
            log10_nu=float(np.clip(lognu, -50.0, 50.0)),
        )
    return total


def parameter_grid(pmin: float = 0.0, pmax: float = 50.0, nbins: int = 50) -> np.ndarray:
    """Centros de bins para una distribución 1D genérica."""
    nbins = int(nbins)
    if nbins < 3:
        raise ValueError("nbins debe ser >= 3")
    if not pmax > pmin:
        raise ValueError("el máximo debe ser mayor que el mínimo")
    edges = np.linspace(float(pmin), float(pmax), nbins + 1)
    return 0.5 * (edges[:-1] + edges[1:])


def bhf_grid(bmin: float = 0.0, bmax: float = 50.0, nbins: int = 50) -> np.ndarray:
    """Centros de bins de BHF en teslas."""
    return parameter_grid(bmin, bmax, nbins)


def build_bhf_kernel(
    v: np.ndarray,
    bhf_centers: np.ndarray,
    *,
    delta: float = 0.0,
    quad: float = 0.0,
    gamma: float = 0.18,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    delta_slope: float = 0.0,
    quad_slope: float = 0.0,
    h_ref: float | None = None,
    treatment: str = "1st_order",
    eta: float = 0.0,
    n_orient: int = 12,
    source_bhf: float = 33.0,
    source_theta: float = 0.0,
    absorber_theta: float = 0.0,
) -> np.ndarray:
    """Matriz K[i,j] = absorcion de un sextete unitario con BHF_j.

    Correlación δ(H)/ΔEQ(H) (Le Caër–Dubois 1979, Wivel–Mørup 1981): en óxidos y
    aleaciones el desplazamiento isomérico y el desdoblamiento cuadrupolar
    correlacionan linealmente con el campo hiperfino. Con ``delta_slope`` /
    ``quad_slope`` (en mm/s·T⁻¹) cada columna usa
    ``δ_j = delta + delta_slope·(H_j − H_ref)`` y
    ``ΔEQ_j = quad + quad_slope·(H_j − H_ref)`` (``H_ref`` = media de la malla si es
    ``None``). El modelo sigue siendo **lineal en los pesos P_j**: solo cambia la
    construcción de cada columna. Con pendientes = 0 reproduce el kernel clásico.
    """
    v = np.asarray(v, dtype=float)
    bhf_centers = np.asarray(bhf_centers, dtype=float)
    href = float(np.mean(bhf_centers)) if h_ref is None else float(h_ref)
    if str(treatment) == "polarized":
        _POL_STATE.update(source_bhf=float(source_bhf),
                          source_theta=float(source_theta),
                          absorber_theta=float(absorber_theta),
                          weight_scale=float(int1))
    cols = [
        sextet_absorption(
            v,
            delta=float(delta) + float(delta_slope) * (float(bhf) - href),
            quad=float(quad) + float(quad_slope) * (float(bhf) - href),
            bhf=float(bhf),
            gamma=gamma,
            gamma2_rel=gamma2_rel,
            gamma3_rel=gamma3_rel,
            int1=int1,
            int2_rel=int2_rel,
            int3_rel=int3_rel,
            treatment=treatment,
            eta=eta,
            n_orient=n_orient,
        )
        for bhf in bhf_centers
    ]
    return np.column_stack(cols)


def build_bhf_quad_distribution_kernel(
    v: np.ndarray,
    bhf_centers: np.ndarray,
    quad_centers: np.ndarray,
    *,
    variable_x: str = "bhf",
    variable_y: str = "quad",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
) -> np.ndarray:
    """Kernel para una distribución 2D de dos parámetros hiperfinos.

    Por compatibilidad histórica los ejes se llaman ``bhf_centers`` y
    ``quad_centers``. Pueden representar otras variables con ``variable_x`` /
    ``variable_y``: ``bhf``, ``quad`` o ``delta`` (IS). Las columnas se ordenan
    como ``weights.reshape(nx, ny)``.
    """
    v = np.asarray(v, dtype=float)
    x_arr = np.asarray(bhf_centers, dtype=float).reshape(-1)
    y_arr = np.asarray(quad_centers, dtype=float).reshape(-1)
    aliases = {"is": "delta", "isomer": "delta", "isomer_shift": "delta",
               "deq": "quad", "deltaeq": "quad", "qs": "quad",
               "b": "bhf", "field": "bhf"}
    vx = aliases.get(variable_x.lower(), variable_x.lower())
    vy = aliases.get(variable_y.lower(), variable_y.lower())
    if vx == vy:
        raise ValueError("Los dos ejes 2D deben ser variables distintas")
    if vx not in {"bhf", "quad", "delta"} or vy not in {"bhf", "quad", "delta"}:
        raise ValueError("Variables 2D válidas: 'bhf', 'quad' o 'delta'")
    if x_arr.size == 0 or y_arr.size == 0:
        return np.empty((v.size, 0), dtype=float)
    # Vectorizado por línea: las mismas primitivas que ``sextet_absorption``
    # (posiciones de 1er orden y ``lorentzian``), pero con todas las columnas a
    # la vez. Un sextete por columna en Python costaba 0.07 s con la malla por
    # defecto (50×21), y las formas 2D paramétricas reconstruyen el kernel en
    # cada paso al ajustar δ/Γ.
    X, Y = np.meshgrid(x_arr, y_arr, indexing="ij")
    vals = {"delta": np.full(X.size, float(delta)), "quad": np.full(X.size, float(quad)),
            "bhf": np.full(X.size, float(bhf))}
    vals[vx] = X.ravel()
    vals[vy] = Y.ravel()
    positions = (core_physics.active_sextet_pattern()[None, :]
                 * (vals["bhf"] / BHF_DEFAULT_T)[:, None]
                 + vals["delta"][:, None]
                 + vals["quad"][:, None] * core_physics.LINE_QUAD_PATTERN[None, :])
    weights, gammas = _rel_weights_gammas(gamma, gamma2_rel, gamma3_rel,
                                          int1, int2_rel, int3_rel)
    K = np.zeros((v.size, X.size), dtype=float)
    for j in range(6):
        K += weights[j] * core_physics.lorentzian(v[:, None], positions[None, :, j], float(gammas[j]))
    return K


def second_difference_matrix_2d(n_bhf: int, n_quad: int) -> tuple[np.ndarray, np.ndarray]:
    """Operadores de curvatura para una malla 2D aplanada en orden C."""
    n_bhf = int(n_bhf)
    n_quad = int(n_quad)
    if n_bhf < 3 or n_quad < 3:
        raise ValueError("n_bhf y n_quad deben ser >= 3 para regularización 2D")
    d_b = second_difference_matrix(n_bhf)
    d_q = second_difference_matrix(n_quad)
    return np.kron(d_b, np.eye(n_quad)), np.kron(np.eye(n_bhf), d_q)


def normalize_probability_2d(weights: np.ndarray, bhf_centers: np.ndarray, quad_centers: np.ndarray) -> np.ndarray:
    """Normaliza P(BHF, ΔEQ) para que su integral bidimensional sea 1."""
    w = np.maximum(np.asarray(weights, dtype=float), 0.0)
    b = np.asarray(bhf_centers, dtype=float)
    q = np.asarray(quad_centers, dtype=float)
    if w.size == 0:
        return w.copy()
    try:
        area_q = np.trapezoid(w, q, axis=1) if q.size > 1 else w[:, 0]
        area = float(np.trapezoid(area_q, b)) if b.size > 1 else float(area_q[0])
    except Exception:
        area = float(np.sum(w))
    if area <= 0 or not np.isfinite(area):
        return np.zeros_like(w)
    return w / area


def bhf_quad_distribution_diagnostics(
    probability: np.ndarray,
    bhf_centers: np.ndarray,
    quad_centers: np.ndarray,
) -> dict[str, float | np.ndarray]:
    """Marginales, medias, sigmas y correlación de una P(BHF, ΔEQ)."""
    p = np.maximum(np.asarray(probability, dtype=float), 0.0)
    b = np.asarray(bhf_centers, dtype=float)
    q = np.asarray(quad_centers, dtype=float)
    if p.shape != (b.size, q.size) or p.size == 0:
        z_b = np.zeros_like(b, dtype=float)
        z_q = np.zeros_like(q, dtype=float)
        return {"marginal_bhf": z_b, "marginal_quad": z_q,
                "mean_bhf": np.nan, "mean_quad": np.nan,
                "sigma_bhf": np.nan, "sigma_quad": np.nan,
                "corr_bhf_quad": np.nan}
    marg_b = np.trapezoid(p, q, axis=1) if q.size > 1 else p[:, 0]
    marg_q = np.trapezoid(p, b, axis=0) if b.size > 1 else p[0, :]
    area_b = float(np.trapezoid(marg_b, b)) if b.size > 1 else float(np.sum(marg_b))
    area_q = float(np.trapezoid(marg_q, q)) if q.size > 1 else float(np.sum(marg_q))
    if area_b > 0 and np.isfinite(area_b):
        marg_b = marg_b / area_b
    if area_q > 0 and np.isfinite(area_q):
        marg_q = marg_q / area_q

    db = np.gradient(b) if b.size > 1 else np.ones_like(b)
    dq = np.gradient(q) if q.size > 1 else np.ones_like(q)
    mass = p * db[:, None] * dq[None, :]
    s = float(np.sum(mass))
    if s <= 0 or not np.isfinite(s):
        return {"marginal_bhf": marg_b, "marginal_quad": marg_q,
                "mean_bhf": np.nan, "mean_quad": np.nan,
                "sigma_bhf": np.nan, "sigma_quad": np.nan,
                "corr_bhf_quad": np.nan}
    mass = mass / s
    bb = b[:, None]
    qq = q[None, :]
    mean_b = float(np.sum(mass * bb))
    mean_q = float(np.sum(mass * qq))
    var_b = float(np.sum(mass * (bb - mean_b) ** 2))
    var_q = float(np.sum(mass * (qq - mean_q) ** 2))
    sig_b = float(np.sqrt(max(var_b, 0.0)))
    sig_q = float(np.sqrt(max(var_q, 0.0)))
    cov = float(np.sum(mass * (bb - mean_b) * (qq - mean_q)))
    corr = cov / (sig_b * sig_q) if sig_b > 0 and sig_q > 0 else float("nan")
    return {"marginal_bhf": marg_b, "marginal_quad": marg_q,
            "mean_bhf": mean_b, "mean_quad": mean_q,
            "sigma_bhf": sig_b, "sigma_quad": sig_q,
            "corr_bhf_quad": float(corr)}


def fit_bhf_quad_distribution(
    v: np.ndarray,
    y: np.ndarray,
    *,
    variable_x: str = "bhf",
    variable_y: str = "quad",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    bmin: float = 0.0,
    bmax: float = 50.0,
    nbins_bhf: int = 30,
    qmin: float = -1.0,
    qmax: float = 1.0,
    nbins_quad: int = 21,
    alpha_bhf: float = 1e-2,
    alpha_quad: float | None = None,
    fit_baseline: bool = True,
    fit_slope: bool = True,
    baseline: float | None = None,
    slope: float | None = None,
    baseline_bounds: tuple[float, float] = (0.0, np.inf),
    slope_bounds: tuple[float, float] = (-np.inf, np.inf),
    sharp_components: list[dict[str, float]] | None = None,
    sigma: np.ndarray | None = None,
    rescale_columns: bool = True,
    profile: str = "Lorentziana",
    voigt_sigma: float = 0.05,
    compute_effective_dof: bool = True,
) -> BhfQuadDistribution2DFit:
    """Ajusta una distribución regularizada bidimensional P(BHF, ΔEQ).

    ``compute_effective_dof=False`` omite los grados de libertad efectivos (y
    su aviso), que cuestan casi tanto como el propio ajuste: el bucle externo
    de la GUI que refina δ/Γ solo necesita los residuos de cada evaluación.

    Es un backend inicial avanzado, deliberadamente sin GUI. El problema es
    lineal en los pesos P_ij y usa restricciones P_ij >= 0 más penalización de
    curvatura en las dos direcciones::

        ||W(y - X z)||² + α_B ||D²_B P||² + α_Q ||D²_Q P||²

    ``profile`` / ``voigt_sigma`` seleccionan la forma de línea del kernel
    (Lorentziana o Voigt), igual que en la distribución 1D.

    Advertencia: incluso con residuo excelente, la solución 2D puede no ser
    única ni tener sentido físico si la malla es demasiado fina o α demasiado
    pequeño.
    """
    v = _finite_1d("v", v)
    y = _finite_1d("y", y)
    if v.size != y.size:
        raise ValueError("v e y deben tener la misma longitud")
    if alpha_quad is None:
        alpha_quad = alpha_bhf
    if alpha_bhf < 0 or alpha_quad < 0 or not np.isfinite(alpha_bhf) or not np.isfinite(alpha_quad):
        raise ValueError("alpha_bhf y alpha_quad deben ser finitos y >= 0")
    sigma_arr = None
    if sigma is not None:
        sigma_arr = _finite_1d("sigma", sigma)
        if sigma_arr.size != y.size:
            raise ValueError("sigma debe tener la misma longitud que y")
        sigma_arr = np.maximum(sigma_arr, 1e-12)
    if baseline is None:
        baseline = float(np.percentile(y, 90))
    if slope is None:
        slope = 0.0

    bhf_centers = parameter_grid(bmin, bmax, nbins_bhf)
    quad_centers = parameter_grid(qmin, qmax, nbins_quad)
    n_b = bhf_centers.size
    n_q = quad_centers.size
    with line_profile(profile, voigt_sigma):
        K = build_bhf_quad_distribution_kernel(
            v, bhf_centers, quad_centers,
            variable_x=variable_x, variable_y=variable_y,
            delta=delta, quad=quad, bhf=bhf, gamma=gamma,
            gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel,
            int1=int1, int2_rel=int2_rel, int3_rel=int3_rel,
        )
        K_sharp, sharp_bhf_centers, fixed_sharp_abs, sharp_fixed_mask, fixed_sharp_weights = build_sharp_kernel_for_fit(
            v,
            sharp_components,
            default_delta=delta,
            default_quad=0.0,
            default_gamma=gamma,
            default_gamma2_rel=gamma2_rel,
            default_gamma3_rel=gamma3_rel,
            default_int1=int1,
            default_int2_rel=int2_rel,
            default_int3_rel=int3_rel,
        )
    L_b, L_q = second_difference_matrix_2d(n_b, n_q)

    y_work = y.astype(float).copy() + fixed_sharp_abs
    columns: list[np.ndarray] = []
    lower: list[float] = []
    upper: list[float] = []
    labels: list[str] = []
    if fit_baseline:
        columns.append(np.ones_like(v)); lower.append(float(baseline_bounds[0])); upper.append(float(baseline_bounds[1])); labels.append("baseline")
    else:
        y_work -= float(baseline)
    if fit_slope:
        columns.append(v); lower.append(float(slope_bounds[0])); upper.append(float(slope_bounds[1])); labels.append("slope")
    else:
        y_work -= float(slope) * v

    dist_start = len(labels)
    for j in range(K.shape[1]):
        columns.append(-K[:, j]); lower.append(0.0); upper.append(np.inf); labels.append(f"P2D{j}")
    dist_end = len(labels)
    sharp_start = len(labels)
    if K_sharp is not None:
        for j in range(K_sharp.shape[1]):
            columns.append(-K_sharp[:, j]); lower.append(0.0); upper.append(np.inf); labels.append(f"sharp{j}")
    sharp_end = len(labels)
    X = np.column_stack(columns)

    scale = np.ones(X.shape[1], dtype=float)
    if rescale_columns and dist_end > dist_start:
        Kw = K / sigma_arr[:, None] if sigma_arr is not None else K
        col_norms = np.linalg.norm(Kw, axis=0)
        col_norms = np.where(np.isfinite(col_norms) & (col_norms > 1e-12), col_norms, 1.0)
        scale[dist_start:dist_end] = col_norms
    Xs = X / scale[None, :]
    L_b_scaled = L_b / scale[None, dist_start:dist_end]
    L_q_scaled = L_q / scale[None, dist_start:dist_end]
    if sigma_arr is not None:
        X_fit = Xs / sigma_arr[:, None]
        y_fit = y_work / sigma_arr
    else:
        X_fit = Xs
        y_fit = y_work

    # Normalización adimensional de α (igual que en el 1D, ver
    # `fit_hyperfine_distribution`): cada eje se escala por λ_ref = ‖A_dist‖²_F /
    # ‖L_scaled‖²_F y la constante de calibración, de modo que log α ≈ 0 es el
    # balance natural con independencia de N, ruido y profundidad.
    _A_dist = X_fit[:, dist_start:dist_end]
    _data_scale = float(np.sum(_A_dist * _A_dist))
    _pen_b = float(np.sum(L_b_scaled * L_b_scaled))
    _pen_q = float(np.sum(L_q_scaled * L_q_scaled))
    lambda_b = (_data_scale / _pen_b) if _pen_b > 1e-30 else 1.0
    lambda_q = (_data_scale / _pen_q) if _pen_q > 1e-30 else 1.0
    alpha_bhf_eff = float(alpha_bhf) * lambda_b * ALPHA_REF_SCALE
    alpha_quad_eff = float(alpha_quad) * lambda_q * ALPHA_REF_SCALE

    reg_b = np.zeros((L_b.shape[0], X.shape[1]), dtype=float)
    reg_q = np.zeros((L_q.shape[0], X.shape[1]), dtype=float)
    reg_b[:, dist_start:dist_end] = np.sqrt(alpha_bhf_eff) * L_b_scaled
    reg_q[:, dist_start:dist_end] = np.sqrt(alpha_quad_eff) * L_q_scaled
    X_aug = np.vstack([X_fit, reg_b, reg_q])
    y_aug = np.concatenate([y_fit, np.zeros(reg_b.shape[0] + reg_q.shape[0], dtype=float)])

    lower_arr = np.array(lower)
    upper_arr = np.array(upper)
    result = solve_bounded_lsq(X_aug, y_aug, lower_arr, upper_arr, max_iter=3000)
    params = result.x / scale
    baseline_fit = float(params[labels.index("baseline")]) if fit_baseline else float(baseline)
    slope_fit = float(params[labels.index("slope")]) if fit_slope else float(slope)
    weights_flat = np.maximum(params[dist_start:dist_end], 0.0)
    weights = weights_flat.reshape(n_b, n_q)
    sharp_weights_free = np.maximum(params[sharp_start:sharp_end], 0.0) if sharp_end > sharp_start else None
    sharp_weights = merge_sharp_weights(sharp_weights_free, sharp_fixed_mask, fixed_sharp_weights)
    fitted = baseline_fit + slope_fit * v - K @ weights_flat - fixed_sharp_abs
    if K_sharp is not None and sharp_weights_free is not None:
        fitted = fitted - K_sharp @ sharp_weights_free
    residuals = y - fitted
    rms = float(np.sqrt(np.mean(residuals ** 2)))
    eff_dof = None
    if compute_effective_dof:
        try:
            L_combined = np.vstack([np.sqrt(alpha_bhf_eff) * L_b,
                                    np.sqrt(alpha_quad_eff) * L_q])
            eff_dof = tikhonov_effective_dof(X, L_combined, 1.0, dist_start, dist_end, sigma=sigma_arr)
        except Exception:
            eff_dof = None
    probability = normalize_probability_2d(weights, bhf_centers, quad_centers)
    diag = bhf_quad_distribution_diagnostics(probability, bhf_centers, quad_centers)
    n_weights = int(weights.size)
    dof_warning = None
    if eff_dof is not None and eff_dof > 0.7 * max(1, y.size):
        dof_warning = tr("bhf.note_high_dof")
    if n_weights > y.size:
        dof_warning = (dof_warning + " " if dof_warning else "") + tr("bhf.note_2d_underdetermined")
    return BhfQuadDistribution2DFit(
        bhf_centers=bhf_centers,
        quad_centers=quad_centers,
        weights=weights,
        probability=probability,
        fitted_curve=fitted,
        residuals=residuals,
        baseline=baseline_fit,
        slope=slope_fit,
        alpha_bhf=float(alpha_bhf),
        alpha_quad=float(alpha_quad),
        rms=rms,
        success=bool(result.success),
        message=str(result.message),
        x_variable=str(variable_x),
        y_variable=str(variable_y),
        effective_dof=eff_dof,
        marginal_bhf=np.asarray(diag["marginal_bhf"], dtype=float),
        marginal_quad=np.asarray(diag["marginal_quad"], dtype=float),
        mean_bhf=float(diag["mean_bhf"]),
        mean_quad=float(diag["mean_quad"]),
        sigma_bhf=float(diag["sigma_bhf"]),
        sigma_quad=float(diag["sigma_quad"]),
        corr_bhf_quad=float(diag["corr_bhf_quad"]),
        dof_warning=dof_warning,
        sharp_bhf_centers=sharp_bhf_centers,
        sharp_weights=sharp_weights,
    )


#: Formas paramétricas de la distribución 2D (gaussianas bivariantes).
VBF_2D_SHAPES = ("Gaussiana 2D", "VBF 2D")
#: |ρ| máximo: con ρ → ±1 la gaussiana degenera en una recta y el ajuste se
#: vuelve inestable; ese caso límite es la correlación lineal κ del 1D.
VBF_2D_RHO_MAX = 0.95


def vbf_sigma_bounds(auto_lo: float, auto_hi: float,
                     sigma_min: float | None = None,
                     sigma_max: float | None = None) -> tuple[float, float]:
    """Límites ``(σ_mín, σ_máx)`` de las gaussianas de VBF/Gaussiana.

    ``sigma_min``/``sigma_max`` son comunes a todas las gaussianas del ajuste y
    van en unidades de la variable de la malla (T para BHF, mm/s para ΔEQ e
    IS). ``None`` o un valor ≤ 0 deja el límite automático (``auto_lo`` /
    ``auto_hi``: la resolución útil de la malla y su anchura total). Sirven
    para impedir que una gaussiana se ensanche hasta hacer de fondo o se
    estreche por debajo de lo que la malla resuelve. Una σ máx explícita por
    debajo del mínimo automático manda sobre él: el mínimo baja a su mitad.
    """
    user_lo = sigma_min is not None and float(sigma_min) > 0
    user_hi = sigma_max is not None and float(sigma_max) > 0
    hi = float(sigma_max) if user_hi else float(auto_hi)
    if user_lo:
        lo = float(sigma_min)
    elif user_hi:
        lo = min(float(auto_lo), 0.5 * hi)
    else:
        lo = float(auto_lo)
    if not (np.isfinite(lo) and np.isfinite(hi)) or not hi > lo:
        raise ValueError(tr("bhf.vbf_sigma_order", max=f"{hi:g}", min=f"{lo:g}"))
    return lo, hi


def bivariate_gaussian_weights(
    x_centers: np.ndarray,
    y_centers: np.ndarray,
    mu_x: float,
    mu_y: float,
    sigma_x: float,
    sigma_y: float,
    rho: float,
) -> np.ndarray:
    """Gaussiana bivariante sobre la malla (nx, ny), normalizada a suma 1.

    Si es mucho más estrecha que la malla y cae entre nodos, la discretizada
    subdesborda a cero; entonces se colapsa al nodo más próximo (como el VBF 1D).
    """
    x = np.asarray(x_centers, dtype=float)[:, None]
    y = np.asarray(y_centers, dtype=float)[None, :]
    sx = max(float(sigma_x), 1e-9)
    sy = max(float(sigma_y), 1e-9)
    r = float(np.clip(rho, -VBF_2D_RHO_MAX, VBF_2D_RHO_MAX))
    zx = (x - float(mu_x)) / sx
    zy = (y - float(mu_y)) / sy
    w = np.exp(-0.5 * (zx * zx - 2.0 * r * zx * zy + zy * zy) / (1.0 - r * r))
    total = float(np.sum(w))
    if not np.isfinite(total) or total <= 1e-300:
        w = np.zeros((x.size, y.size), dtype=float)
        w[int(np.argmin(np.abs(x[:, 0] - float(mu_x)))),
          int(np.argmin(np.abs(y[0, :] - float(mu_y))))] = 1.0
        return w
    return w / total


def fit_vbf_2d_distribution(
    v: np.ndarray,
    y: np.ndarray,
    *,
    n_components: int = 1,
    variable_x: str = "bhf",
    variable_y: str = "quad",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    bmin: float = 0.0,
    bmax: float = 50.0,
    nbins_bhf: int = 30,
    qmin: float = -1.0,
    qmax: float = 1.0,
    nbins_quad: int = 21,
    fit_baseline: bool = True,
    fit_slope: bool = True,
    baseline: float | None = None,
    slope: float | None = None,
    sharp_components: list[dict[str, float]] | None = None,
    sigma: np.ndarray | None = None,
    profile: str = "Lorentziana",
    voigt_sigma: float = 0.05,
    shape: str | None = None,
    initial_components: list[tuple[float, float, float, float, float, float]] | None = None,
    fit_delta: bool = False,
    fit_quad: bool = False,
    fit_gamma: bool = False,
    delta_bounds: tuple[float, float] = (-3.0, 3.0),
    quad_bounds: tuple[float, float] = (-4.0, 4.0),
    gamma_bounds: tuple[float, float] = (0.05, 3.0),
    sigma_x_min: float | None = None,
    sigma_x_max: float | None = None,
    sigma_y_min: float | None = None,
    sigma_y_max: float | None = None,
    progress=None,
) -> BhfQuadDistribution2DFit:
    """Distribución 2D paramétrica: suma de N gaussianas bivariantes (VBF 2D).

    Cada componente k aporta (A_k, μx, μy, σx, σy, ρ) con P_k normalizada a
    suma 1 sobre la malla, así que A_k/ΣA es la fracción de cada sitio. Con
    ``n_components=1`` es la «Gaussiana 2D».

    ρ generaliza la correlación lineal del 1D: la media condicional de y es
    μy + ρ·σy/σx·(x − μx) (pendiente κ = ρσy/σx) y alrededor de esa recta queda
    una anchura propia σy·√(1−ρ²). Es el caso típico IS–ΔEQ de vidrios y
    materiales desordenados (p. ej. Fe²⁺ y Fe³⁺ como dos gaussianas).

    Usa el mismo kernel que la 2D regularizada (``fit_bhf_quad_distribution``)
    pero solo ajusta 6N parámetros no lineales en lugar de un peso por celda,
    sin α. Devuelve el mismo ``BhfQuadDistribution2DFit`` (mapa, marginales y
    estadísticos), con las gaussianas en ``vbf2d_components`` ordenadas por μx.

    ``initial_components`` (mismo formato que ``vbf2d_components``) sustituye a
    los arranques múltiples por uno solo: el bucle externo de la GUI pasa la
    solución de su primera evaluación y cada evaluación cuesta un arranque.

    ``fit_delta``/``fit_quad``/``fit_gamma`` ajustan esos globales (si no son
    un eje) en el MISMO problema no lineal que las gaussianas, reconstruyendo
    el kernel. Anidarlos en un bucle externo, como en el histograma, no
    funciona aquí: el óptimo interno es iterativo y su ruido de convergencia
    (y los saltos entre mínimos locales) arruinan las diferencias finitas
    externas — en la magnetita, o no se movían o tardaba minutos.

    ``sigma_x_min``/``sigma_x_max`` y ``sigma_y_min``/``sigma_y_max`` limitan
    la anchura de TODAS las gaussianas en cada eje (unidades del eje; ``None``
    o ≤ 0 = automático: de un cuarto de paso de malla a su anchura total). Los
    límites aplicados se devuelven en ``vbf2d_sigma_bounds``.

    ``progress`` (opcional, sin argumentos) se llama en cada evaluación del
    residuo y de la jacobiana; la GUI lo usa para atender «Cancelar», que
    puede lanzar una excepción desde ahí para abortar el ajuste.
    """
    from scipy.optimize import least_squares
    v = _finite_1d("v", v)
    y = _finite_1d("y", y)
    if v.size != y.size:
        raise ValueError("v e y deben tener la misma longitud")
    N = max(1, int(n_components))
    if shape is None:
        shape = "Gaussiana 2D" if N == 1 else "VBF 2D"
    inv_sigma = None
    if sigma is not None:
        sigma_arr = _finite_1d("sigma", sigma)
        if sigma_arr.size != y.size:
            raise ValueError("sigma debe tener la misma longitud que y")
        inv_sigma = 1.0 / np.maximum(sigma_arr, 1e-12)
    if baseline is None:
        baseline = float(np.percentile(y, 90))
    if slope is None:
        slope = 0.0

    xc = parameter_grid(bmin, bmax, nbins_bhf)
    yc = parameter_grid(qmin, qmax, nbins_quad)
    axes = {str(variable_x), str(variable_y)}
    # Globales libres (un eje no puede serlo): (nombre, valor inicial, cotas),
    # Γ en escala logarítmica.
    glob: list[tuple[str, float, float, float]] = []
    if fit_delta and "delta" not in axes:
        glob.append(("delta", float(delta), *map(float, delta_bounds)))
    if fit_quad and "quad" not in axes:
        glob.append(("quad", float(quad), *map(float, quad_bounds)))
    if fit_gamma:
        glob.append(("gamma", float(np.log(gamma)), *np.log(np.asarray(gamma_bounds, dtype=float))))
    n_glob = len(glob)
    kernel_cache: dict[tuple[float, ...], np.ndarray] = {}

    def glob_values(p: np.ndarray) -> dict[str, float]:
        vals = {"delta": float(delta), "quad": float(quad), "gamma": float(gamma)}
        for (name, *_), val in zip(glob, p[p.size - n_glob:] if n_glob else ()):
            vals[name] = float(np.exp(val)) if name == "gamma" else float(val)
        return vals

    def kernel(vals: dict[str, float]) -> np.ndarray:
        key = (vals["delta"], vals["quad"], vals["gamma"])
        K_ = kernel_cache.get(key)
        if K_ is None:
            if len(kernel_cache) > 8:
                kernel_cache.clear()
            with line_profile(profile, voigt_sigma):
                K_ = build_bhf_quad_distribution_kernel(
                    v, xc, yc, variable_x=variable_x, variable_y=variable_y,
                    delta=vals["delta"], quad=vals["quad"], bhf=bhf, gamma=vals["gamma"])
            kernel_cache[key] = K_
        return K_

    K = kernel({"delta": float(delta), "quad": float(quad), "gamma": float(gamma)})
    with line_profile(profile, voigt_sigma):
        K_sharp, sharp_bhf_centers, fixed_sharp_abs, sharp_fixed_mask, fixed_sharp_weights = build_sharp_kernel_for_fit(
            v, sharp_components, default_delta=delta, default_quad=0.0, default_gamma=gamma)
    n_sharp = K_sharp.shape[1] if K_sharp is not None else 0
    x_lo, x_hi = float(xc[0]), float(xc[-1])
    y_lo, y_hi = float(yc[0]), float(yc[-1])
    x_rng = max(x_hi - x_lo, 1e-3)
    y_rng = max(y_hi - y_lo, 1e-3)
    dx = x_rng / max(xc.size - 1, 1)
    dy = y_rng / max(yc.size - 1, 1)
    n_lin = int(fit_baseline) + int(fit_slope)

    def lin_part(p: np.ndarray) -> tuple[float, float]:
        i = 0
        if fit_baseline:
            b0 = float(p[0]); i = 1
        else:
            b0 = float(baseline)
        return b0, (float(p[i]) if fit_slope else float(slope))

    def comp_view(p: np.ndarray) -> np.ndarray:
        return np.asarray(p[n_lin:n_lin + 6 * N]).reshape(N, 6)

    def total_w(comp: np.ndarray) -> np.ndarray:
        w = np.zeros((xc.size, yc.size), dtype=float)
        for A, mx, my, lsx, lsy, r in comp:
            w += max(float(A), 0.0) * bivariate_gaussian_weights(
                xc, yc, mx, my, np.exp(lsx), np.exp(lsy), r)
        return w

    def model(p: np.ndarray) -> np.ndarray:
        b0, sl = lin_part(p)
        Kp = kernel(glob_values(p))
        out = b0 + sl * v - Kp @ total_w(comp_view(p)).ravel() - fixed_sharp_abs
        if n_sharp:
            out = out - K_sharp @ np.maximum(p[n_lin + 6 * N:n_lin + 6 * N + n_sharp], 0.0)
        return out

    def residual(p: np.ndarray) -> np.ndarray:
        if progress is not None:
            progress()
        r = model(p) - y
        return r * inv_sigma if inv_sigma is not None else r

    gx = xc[:, None]
    gy = yc[None, :]

    def jacobian(p: np.ndarray) -> np.ndarray:
        """Jacobiano analítico: con diferencias finitas cada ajuste tardaba
        segundos y su ruido de convergencia confundía al bucle externo."""
        if progress is not None:
            progress()
        J = np.zeros((v.size, p.size), dtype=float)
        K = kernel(glob_values(p))
        i = 0
        if fit_baseline:
            J[:, 0] = 1.0; i = 1
        if fit_slope:
            J[:, i] = v
        for k, (A, mx, my, lsx, lsy, r) in enumerate(comp_view(p)):
            j0 = n_lin + 6 * k
            sx, sy = np.exp(lsx), np.exp(lsy)
            rr = float(np.clip(r, -VBF_2D_RHO_MAX, VBF_2D_RHO_MAX))
            g = bivariate_gaussian_weights(xc, yc, mx, my, sx, sy, rr)
            J[:, j0] = -(K @ g.ravel()) if A > 0 else 0.0
            zx = (gx - mx) / sx
            zy = (gy - my) / sy
            den = 1.0 - rr * rr
            q = (zx * zx - 2.0 * rr * zx * zy + zy * zy) / den
            dq_dzx = 2.0 * (zx - rr * zy) / den
            dq_dzy = 2.0 * (zy - rr * zx) / den
            dqs = (dq_dzx * (-1.0 / sx), dq_dzy * (-1.0 / sy),
                   dq_dzx * (-zx), dq_dzy * (-zy),
                   (-2.0 * zx * zy + 2.0 * rr * q) / den)
            amp = max(float(A), 0.0)
            for m, dq in enumerate(dqs, start=1):
                # g = e/Σe con e = exp(−q/2): ∂g = g·(h − Σ g·h), h = −½·∂q.
                h = -0.5 * dq
                dg = g * (h - float(np.sum(g * h)))
                J[:, j0 + m] = -amp * (K @ dg.ravel())
        if n_sharp:
            ws = p[n_lin + 6 * N:n_lin + 6 * N + n_sharp]
            J[:, n_lin + 6 * N:n_lin + 6 * N + n_sharp] = -K_sharp * (ws > 0.0)[None, :]
        # Globales: diferencia hacia delante reconstruyendo el kernel (uno por
        # global; el kernel es exacto, así que basta un paso pequeño).
        if n_glob:
            m0 = model(p)
            for j in range(n_glob):
                col = p.size - n_glob + j
                h = 1e-6
                pp = p.copy(); pp[col] += h
                J[:, col] = (model(pp) - m0) / h
        return J * inv_sigma[:, None] if inv_sigma is not None else J

    # Área inicial: la profundidad total del espectro repartida entre los
    # componentes, medida con una columna típica del kernel.
    depth = max(1e-6, float(baseline) - float(np.min(y)))
    col_peak = float(np.max(K)) if K.size else 1.0
    amp0 = depth / max(col_peak, 1e-12)
    lo, hi = [], []
    head0 = []
    if fit_baseline:
        lo.append(0.0); hi.append(np.inf); head0.append(float(baseline))
    if fit_slope:
        lo.append(-np.inf); hi.append(np.inf); head0.append(float(slope))
    sx_bounds = vbf_sigma_bounds(0.25 * dx, x_rng, sigma_x_min, sigma_x_max)
    sy_bounds = vbf_sigma_bounds(0.25 * dy, y_rng, sigma_y_min, sigma_y_max)
    ls_x = (np.log(sx_bounds[0]), np.log(sx_bounds[1]))
    ls_y = (np.log(sy_bounds[0]), np.log(sy_bounds[1]))
    for _ in range(N):
        lo += [0.0, x_lo, y_lo, ls_x[0], ls_y[0], -VBF_2D_RHO_MAX]
        hi += [np.inf, x_hi, y_hi, ls_x[1], ls_y[1], VBF_2D_RHO_MAX]
    lo += [0.0] * n_sharp
    hi += [np.inf] * n_sharp
    for _name, _x0, g_lo, g_hi in glob:
        lo.append(g_lo); hi.append(g_hi)
    lo_arr = np.array(lo, dtype=float)
    hi_arr = np.array(hi, dtype=float)
    tail0 = [g[1] for g in glob]

    # Arranques: con N > 1 no se sabe si los sitios se separan en x, en y o en
    # diagonal (Fe²⁺/Fe³⁺ en IS–ΔEQ difieren en ambos), así que se prueban las
    # cuatro direcciones y se queda el de menor coste.
    def start(direction: tuple[float, float]) -> np.ndarray:
        t = (np.linspace(-1.0, 1.0, N) * (N - 1) / (N + 1)) if N > 1 else np.zeros(1)
        sx0 = max(x_rng / (4.0 * N), 2.0 * dx)
        sy0 = max(y_rng / (4.0 * N), 2.0 * dy)
        p0 = list(head0)
        for tk in t:
            p0 += [amp0 / N,
                   0.5 * (x_lo + x_hi) + 0.5 * x_rng * direction[0] * tk,
                   0.5 * (y_lo + y_hi) + 0.5 * y_rng * direction[1] * tk,
                   np.log(sx0), np.log(sy0), 0.0]
        p0 += [amp0 / max(n_sharp, 1)] * n_sharp + tail0
        return np.clip(np.array(p0, dtype=float), lo_arr, hi_arr)

    def warm_start(comps) -> np.ndarray:
        p0 = list(head0)
        for A, mx, my, sx, sy, r in comps:
            p0 += [float(A), float(mx), float(my), np.log(max(float(sx), 1e-12)),
                   np.log(max(float(sy), 1e-12)), float(r)]
        p0 += [amp0 / max(n_sharp, 1)] * n_sharp + tail0
        return np.clip(np.array(p0, dtype=float), lo_arr, hi_arr)

    if initial_components is not None and len(initial_components) == N:
        starts = [warm_start(initial_components)]
    else:
        directions = ([(1.0, 0.0)] if N == 1
                      else [(1.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, -1.0)])
        starts = [start(dv) for dv in directions]
    max_nfev = 200 * (6 * N + n_lin + n_sharp + n_glob)
    # Arranques con los globales congelados (kernel fijo, muy baratos)…
    n_short = lo_arr.size - n_glob
    tail = np.clip(np.asarray(tail0, dtype=float), lo_arr[n_short:], hi_arr[n_short:])

    def full(p_short: np.ndarray) -> np.ndarray:
        return np.concatenate([p_short, tail])

    res = None
    for p0 in starts:
        cand = least_squares(lambda q: residual(full(q)), p0[:n_short],
                             jac=lambda q: jacobian(full(q))[:, :n_short],
                             bounds=(lo_arr[:n_short], hi_arr[:n_short]),
                             x_scale="jac", max_nfev=max_nfev)
        if res is None or cand.cost < res.cost:
            res = cand
    res.x = full(res.x)
    if n_glob:
        # …y después el ajuste conjunto desde el mejor.
        res = least_squares(residual, np.clip(res.x, lo_arr, hi_arr), jac=jacobian,
                            bounds=(lo_arr, hi_arr), x_scale="jac", max_nfev=max_nfev)

    comp = comp_view(res.x)
    w = total_w(comp)
    b0_fit, sl_fit = lin_part(res.x)
    sharp_free = np.maximum(res.x[n_lin + 6 * N:n_lin + 6 * N + n_sharp], 0.0) if n_sharp else None
    sharp_weights = merge_sharp_weights(sharp_free, sharp_fixed_mask, fixed_sharp_weights)
    fitted = model(res.x)
    residuals = y - fitted
    comps = tuple(sorted(
        ((max(float(A), 0.0), float(mx), float(my), float(np.exp(lsx)), float(np.exp(lsy)),
          float(np.clip(r, -VBF_2D_RHO_MAX, VBF_2D_RHO_MAX)))
         for A, mx, my, lsx, lsy, r in comp),
        key=lambda c: (c[1], c[2])))
    area_tot = sum(c[0] for c in comps)
    summary = ", ".join(
        (f"(A={c[0]:.3g}[{100.0 * c[0] / area_tot:.0f}%], " if area_tot > 0 else f"(A={c[0]:.3g}, ")
        + f"μ=({c[1]:.4g}, {c[2]:.4g}), σ=({c[3]:.3g}, {c[4]:.3g}), ρ={c[5]:.2f})"
        for c in comps)
    probability = normalize_probability_2d(w, xc, yc)
    diag = bhf_quad_distribution_diagnostics(probability, xc, yc)
    edge = []
    for c in comps:
        if (min(c[1] - x_lo, x_hi - c[1]) < c[3] or min(c[2] - y_lo, y_hi - c[2]) < c[4]):
            edge.append(c)
    notes = []
    if edge:
        notes.append(tr("bhf.note_gauss_edge"))
    if {str(variable_x), str(variable_y)} == {"delta", "quad"} and float(bhf) == 0.0:
        # Un doblete solo ve δ − ΔEQ/2 y δ + ΔEQ/2: de (σx, σy, ρ) solo se
        # determinan dos combinaciones (las anchuras de las dos líneas).
        notes.append(tr("bhf.note_is_quad_doublets"))
    warning = " ".join(notes) or None
    return BhfQuadDistribution2DFit(
        bhf_centers=xc,
        quad_centers=yc,
        weights=w,
        probability=probability,
        fitted_curve=fitted,
        residuals=residuals,
        baseline=b0_fit,
        slope=sl_fit,
        alpha_bhf=0.0,
        alpha_quad=0.0,
        rms=float(np.sqrt(np.mean(residuals ** 2))),
        success=bool(res.success),
        message=f"{shape} {variable_x}-{variable_y} N={N}: {summary}; {res.message}",
        vbf2d_sigma_bounds=(tuple(sx_bounds), tuple(sy_bounds)),
        x_variable=str(variable_x),
        y_variable=str(variable_y),
        marginal_bhf=np.asarray(diag["marginal_bhf"], dtype=float),
        marginal_quad=np.asarray(diag["marginal_quad"], dtype=float),
        mean_bhf=float(diag["mean_bhf"]),
        mean_quad=float(diag["mean_quad"]),
        sigma_bhf=float(diag["sigma_bhf"]),
        sigma_quad=float(diag["sigma_quad"]),
        corr_bhf_quad=float(diag["corr_bhf_quad"]),
        dof_warning=warning,
        sharp_bhf_centers=sharp_bhf_centers,
        sharp_weights=sharp_weights,
        shape=str(shape),
        vbf2d_components=comps,
        fitted_globals=({name: glob_values(res.x)[name] for name, *_ in glob} or None),
        effective_dof=float(res.x.size),
    )


def build_hyperfine_distribution_kernel(
    v: np.ndarray,
    centers: np.ndarray,
    *,
    variable: str = "bhf",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    delta_slope: float = 0.0,
    quad_slope: float = 0.0,
    h_ref: float | None = None,
    treatment: str = "1st_order",
    eta: float = 0.0,
    n_orient: int = 12,
    source_bhf: float = 33.0,
    source_theta: float = 0.0,
    absorber_theta: float = 0.0,
) -> np.ndarray:
    """Kernel de distribución 1D en BHF o ΔEQ.

    variable="bhf": centers son campos BHF y quad queda fijo.
    variable="quad": centers son ΔEQ y BHF queda fijo.

    ``delta_slope`` / ``quad_slope`` introducen la correlación lineal de δ y ΔEQ
    con la variable de la malla (ver :func:`build_bhf_kernel`). Con
    ``variable="quad"`` la pendiente análoga aplica sobre δ (δ(ΔEQ)); con
    ``variable="delta"`` sobre ΔEQ (ΔEQ(IS)). Pendientes = 0 → kernel clásico.
    """
    variable = variable.lower()
    centers_arr = np.asarray(centers, dtype=float)
    href = float(np.mean(centers_arr)) if h_ref is None else float(h_ref)
    if variable in {"bhf", "b", "field"}:
        return build_bhf_kernel(v, centers_arr, delta=delta, quad=quad, gamma=gamma,
                                gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel,
                                int1=int1, int2_rel=int2_rel, int3_rel=int3_rel,
                                delta_slope=delta_slope, quad_slope=quad_slope, h_ref=href,
                                treatment=treatment, eta=eta, n_orient=n_orient,
                                source_bhf=source_bhf, source_theta=source_theta,
                                absorber_theta=absorber_theta)
    if variable in {"quad", "deq", "deltaeq", "qs", "Δeq"}:
        return np.column_stack([
            sextet_absorption(v, delta=float(delta) + float(delta_slope) * (float(q) - href),
                              quad=float(q), bhf=bhf, gamma=gamma,
                              gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel,
                              int1=int1, int2_rel=int2_rel, int3_rel=int3_rel)
            for q in centers_arr
        ])
    if variable in {"delta", "is", "isomer", "isomer_shift"}:
        return np.column_stack([
            sextet_absorption(v, delta=float(d),
                              quad=float(quad) + float(quad_slope) * (float(d) - href),
                              bhf=bhf, gamma=gamma,
                              gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel,
                              int1=int1, int2_rel=int2_rel, int3_rel=int3_rel)
            for d in centers_arr
        ])
    raise ValueError("variable de distribución no reconocida: usa 'bhf', 'quad' o 'delta'")


def second_difference_matrix(n: int) -> np.ndarray:
    """Operador L de segundas diferencias, dimension (n-2) x n."""
    n = int(n)
    if n < 3:
        raise ValueError("n debe ser >= 3")
    L = np.zeros((n - 2, n), dtype=float)
    rows = np.arange(n - 2)
    L[rows, rows] = 1.0
    L[rows, rows + 1] = -2.0
    L[rows, rows + 2] = 1.0
    return L


def edge_pileup_ratio(weights: np.ndarray) -> float:
    """``max(P[0], P[-1]) / max(P)`` — diagnóstico de malla insuficiente."""
    w = np.asarray(weights, dtype=float)
    if w.size < 3:
        return 0.0
    top = float(np.max(w))
    if not np.isfinite(top) or top <= 0.0:
        return 0.0
    return float(max(w[0], w[-1]) / top)


def edge_anchor_rows(n: int, beta: float) -> np.ndarray:
    """Filas de anclaje que fuerzan P→0 en los EXTREMOS de la malla.

    Paridad con los ``BETA1``/``BETA2`` de NORMOS-DIST (``SMOOTH`` en
    ``distauxl.for``), que los suma a las esquinas diagonales de su matriz de
    suavizado ``λ·D₂ᵀD₂``. Aquí la regularización se resuelve en forma de raíz
    cuadrada (filas apiladas), así que el equivalente son dos filas
    ``√β·e₀ᵀ`` y ``√β·e_{n−1}ᵀ``.

    Para qué sirven: sin anclaje, si la distribución real se sale de la malla
    el histograma de Hesse–Rübartsch APILA todo el peso sobrante en el bin
    extremo — un pico espurio que además arrastra ⟨B⟩. Con anclaje el ajuste
    no puede refugiarse ahí y el desajuste se hace visible.

    Devuelve ``(0, n)`` si ``beta <= 0``.
    """
    n = int(n)
    beta = float(beta)
    if n < 2 or beta <= 0.0:
        return np.zeros((0, n), dtype=float)
    rows = np.zeros((2, n), dtype=float)
    rows[0, 0] = np.sqrt(beta)
    rows[1, -1] = np.sqrt(beta)
    return rows


def first_difference_matrix(n: int) -> np.ndarray:
    """Operador D de primeras diferencias, dimensión (n-1) x n."""
    n = int(n)
    if n < 2:
        raise ValueError("n debe ser >= 2")
    D = np.zeros((n - 1, n), dtype=float)
    rows = np.arange(n - 1)
    D[rows, rows] = -1.0
    D[rows, rows + 1] = 1.0
    return D


def tikhonov_effective_dof(
    X: np.ndarray,
    L_dist: np.ndarray,
    alpha: float,
    dist_start: int,
    dist_end: int,
    sigma: np.ndarray | None = None,
) -> float:
    """Grados de libertad efectivos del problema Tikhonov bajo restricciones lineales.

    Devuelve  tr A(α)  con  A(α) = X (XᵀWX + α LᵀL)⁻¹ XᵀW,  W = diag(1/σ²).
    El penalizador LᵀL actúa sólo sobre las columnas [dist_start:dist_end].

    La cota de no-negatividad sobre P se ignora aquí: la traza es una buena
    estimación incluso con bordes activos (sólo sobreestima ligeramente).
    """
    X = np.asarray(X, dtype=float)
    L_dist = np.asarray(L_dist, dtype=float)
    if X.size == 0:
        return 0.0
    if sigma is not None:
        sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-12)
        Xw = X / sigma[:, None]
    else:
        Xw = X
    XtWX = Xw.T @ Xw
    LtL = L_dist.T @ L_dist
    H = XtWX.copy()
    H[dist_start:dist_end, dist_start:dist_end] += float(alpha) * LtL
    try:
        return float(np.trace(np.linalg.solve(H, XtWX)))
    except np.linalg.LinAlgError:
        return float(X.shape[1])


def distribution_weight_sigma(
    X: np.ndarray,
    L_dist: np.ndarray,
    alpha: float,
    dist_start: int,
    dist_end: int,
    residuals: np.ndarray,
    eff_dof: float,
    sigma: np.ndarray | None = None,
) -> np.ndarray:
    """Incertidumbre 1σ de los pesos P por covarianza linealizada regularizada.

    Para el estimador Tikhonov  ẑ = H⁻¹ XᵀW y  con  H = XᵀWX + α LᵀL,  W=diag(1/σ²),
    la covarianza es  Cov(ẑ) = H⁻¹ (XᵀWX) H⁻¹.  Se escala por el χ²_ν efectivo
    (igual convención que el ajuste discreto) para reflejar mala especificación
    del modelo. Devuelve σ_P por bin (raíz de la diagonal de la parte de la
    distribución). La no-negatividad no se impone aquí: en bins clavados a 0 la
    σ es una cota superior (la banda se recorta a P≥0 al pintar).
    """
    n_data = X.shape[0]
    if sigma is not None:
        sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-12)
        W = 1.0 / sigma ** 2
        chi2 = float(np.sum((residuals / sigma) ** 2))
    else:
        W = np.ones(n_data)
        chi2 = float(np.sum(residuals ** 2))
    XtWX = X.T @ (W[:, None] * X)
    H = XtWX.copy()
    H[dist_start:dist_end, dist_start:dist_end] += float(alpha) * (L_dist.T @ L_dist)
    try:
        H_inv = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        H_inv = np.linalg.pinv(H)
    cov = H_inv @ XtWX @ H_inv
    var = np.clip(np.diag(cov)[dist_start:dist_end], 0.0, None)
    dof = max(float(n_data) - float(eff_dof), 1.0)
    var = var * (chi2 / dof)
    return np.sqrt(var)



def global_parameter_covariance(
    jac: np.ndarray,
    residuals: np.ndarray,
    inner_dof: float = 0.0,
) -> np.ndarray | None:
    """Covarianza linealizada de los parámetros globales del bucle externo.

    ``jac`` es la jacobiana de los residuos respecto a los parámetros externos
    (δ, ΔEQ, Γ, pendientes…) con los pesos de la distribución re-ajustados en
    cada evaluación (proyección de variables), y ``inner_dof`` los grados de
    libertad efectivos que consume la distribución. Cov = s²·(JᵀJ)⁻¹ con
    s² = Σr²/(n − inner_dof − p). Devuelve ``None`` si no quedan grados de
    libertad o la jacobiana no es finita.
    """
    J = np.atleast_2d(np.asarray(jac, dtype=float))
    r = np.asarray(residuals, dtype=float).ravel()
    if J.shape[0] != r.size or not (np.all(np.isfinite(J)) and np.all(np.isfinite(r))):
        return None
    dof = float(r.size) - float(inner_dof) - float(J.shape[1])
    if dof <= 0:
        return None
    s2 = float(np.dot(r, r)) / dof
    return s2 * np.linalg.pinv(J.T @ J)


def distribution_goodness(
    residuals: np.ndarray,
    sigma: np.ndarray | None,
    n_params: float | None,
    n_outer: int = 0,
) -> dict[str, float]:
    """Bondad de un ajuste de distribución, comparable con la del discreto.

    ``n_params`` son los grados de libertad que consume el ajuste interno
    (``effective_dof``: la traza del operador regularizado en el histograma,
    el número de parámetros en las formas paramétricas) y ``n_outer`` los
    globales refinados por el bucle externo (δ, ΔEQ, Γ, pendientes…).
    k = n_params + n_outer; ν = N − k. χ² usa la σ de los datos; AIC y BIC
    siguen la misma definición que el ajuste discreto
    (N·ln(χ²/N) + 2k y N·ln(χ²/N) + k·ln N), así que se pueden comparar
    modelos discretos y de distribución sobre el mismo espectro.
    Sin ``sigma`` solo se devuelven RMS y los diagnósticos de residuos.
    """
    r = np.asarray(residuals, dtype=float).ravel()
    n = int(r.size)
    out: dict[str, float] = {
        "n_points": float(n),
        "rms": float(np.sqrt(np.mean(r ** 2))) if n else float("nan"),
        "resid_lag1": residual_lag1(r),
        "resid_runs_z": residual_runs_z(r),
    }
    if sigma is None or n == 0:
        return out
    s = np.maximum(np.asarray(sigma, dtype=float).ravel(), 1e-300)
    if s.size != n:
        return out
    chi2 = float(np.sum((r / s) ** 2))
    out["chi2"] = chi2
    if n_params is None:
        return out
    k = float(n_params) + float(n_outer)
    nu = float(n) - k
    out["n_params"] = k
    if nu > 0:
        out["dof"] = nu
        out["red_chi2"] = chi2 / nu
    logl = n * np.log(max(chi2 / n, 1e-300))
    out["aic"] = float(logl + 2.0 * k)
    out["bic"] = float(logl + k * np.log(n))
    return out


def distribution_moments(centers: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    """Media, desviación típica y moda de una P(x) 1D sobre su malla.

    Sirve igual para densidades (histograma, gaussianas) que para la binomial
    (P_k que suman 1): solo usa los pesos relativos. Vacío si P es nula.
    """
    x = np.asarray(centers, dtype=float).ravel()
    p = np.clip(np.asarray(probability, dtype=float).ravel(), 0.0, None)
    tot = float(np.sum(p))
    if x.size == 0 or x.size != p.size or tot <= 0.0:
        return {}
    w = p / tot
    mean = float(np.sum(w * x))
    std = float(np.sqrt(max(float(np.sum(w * (x - mean) ** 2)), 0.0)))
    return {"mean": mean, "std": std, "mode": float(x[int(np.argmax(p))])}


def data_weights(sigma: np.ndarray | None, n: int) -> np.ndarray | None:
    """1/σ por canal para ponderar los residuos, o None si no hay σ válida."""
    if sigma is None:
        return None
    s = np.asarray(sigma, dtype=float).ravel()
    if s.size != n or not np.all(np.isfinite(s)):
        return None
    return 1.0 / np.maximum(s, 1e-12)


def moment_samples_cov(samples: list[tuple[np.ndarray, np.ndarray]]) -> np.ndarray | None:
    """Covarianza 2×2 de (media, desviación) sobre muestras ``(centros, P)``."""
    filas = []
    for centers, prob in samples:
        m = distribution_moments(centers, prob)
        if m:
            filas.append((m["mean"], m["std"]))
    if len(filas) < 3:
        return None
    return np.atleast_2d(np.cov(np.asarray(filas, dtype=float), rowvar=False))


def parametric_moment_cov(
    sample_fn,
    x_hat: np.ndarray,
    jac: np.ndarray,
    cost: float,
    n_data: int,
    *,
    weighted: bool,
    n_samples: int = 200,
    seed: int = 0,
) -> np.ndarray | None:
    """Covarianza de (media, desviación) de P en una forma paramétrica.

    Muestrea los parámetros con su covarianza lineal (de la jacobiana; si
    los residuos no van ponderados, escalada por χ²/ν) y calcula los momentos
    de la P de cada muestra: ``sample_fn(x) -> (centros, P)``. Así la
    no linealidad de la forma (σ en log, amplitudes ≥ 0) entra sin derivar.
    """
    try:
        x_hat = np.asarray(x_hat, dtype=float)
        J = np.asarray(jac, dtype=float)
        dof = max(int(n_data) - x_hat.size, 1)
        scale = 1.0 if weighted else float(2.0 * cost / dof)
        cov = scale * np.linalg.pinv(J.T @ J)
        vals, vecs = np.linalg.eigh(0.5 * (cov + cov.T))
        raiz = vecs * np.sqrt(np.clip(vals, 0.0, None))
        rng = np.random.default_rng(int(seed))
        z = rng.standard_normal((int(n_samples), x_hat.size))
        return moment_samples_cov([sample_fn(x_hat + raiz @ zi) for zi in z])
    except Exception:
        return None


#: Nombre de columna de cada variable distribuida en los ficheros de datos.
DATA_COLUMN_NAMES = {"bhf": "BHF_T", "quad": "dEQ_mm_s", "delta": "IS_mm_s"}


def distribution_data_table(
    result: "BhfDistributionFit | BhfQuadDistribution2DFit",
    extra_columns: dict[str, np.ndarray] | None = None,
) -> tuple[list[str], np.ndarray]:
    """Tabla (columnas, filas) con los datos de una distribución ajustada.

    1D: variable, P normalizada, σ de P (si hay banda Monte Carlo), peso sin
    normalizar y las columnas extra (p. ej. la curva δ(x) y su σ).
    2D: formato largo, una fila por celda: x, y, P normalizada y peso.
    """
    if isinstance(result, BhfQuadDistribution2DFit):
        x = np.asarray(result.bhf_centers, dtype=float)
        yv = np.asarray(result.quad_centers, dtype=float)
        p = np.asarray(result.probability, dtype=float)
        w = np.asarray(result.weights, dtype=float).reshape(p.shape)
        gx, gy = np.meshgrid(x, yv, indexing="ij")
        cols = [DATA_COLUMN_NAMES.get(result.x_variable, "x"),
                DATA_COLUMN_NAMES.get(result.y_variable, "y"),
                "P_normalized", "weight"]
        return cols, np.column_stack([gx.ravel(), gy.ravel(), p.ravel(), w.ravel()])
    x = np.asarray(result.bhf_centers, dtype=float)
    cols = [DATA_COLUMN_NAMES.get(result.fit_variable or "bhf", "x"), "P_normalized"]
    data = [x, np.asarray(result.probability, dtype=float)]
    sp = result.probability_sigma
    if sp is not None and np.asarray(sp).size == x.size:
        cols.append("sigma_P")
        data.append(np.asarray(sp, dtype=float))
    cols.append("weight")
    data.append(np.asarray(result.weights, dtype=float))
    for name, col in (extra_columns or {}).items():
        col = np.asarray(col, dtype=float)
        if col.size == x.size:
            cols.append(name)
            data.append(col)
    return cols, np.column_stack(data)


def write_distribution_data(
    path: str | Path,
    result: "BhfDistributionFit | BhfQuadDistribution2DFit",
    *,
    header: list[str] | tuple[str, ...] = (),
    extra_columns: dict[str, np.ndarray] | None = None,
) -> None:
    """Escribe la distribución en texto separado por tabuladores.

    Las líneas de ``header`` van como comentarios ``# …``; después, la fila
    de nombres de columna y los datos (ver :func:`distribution_data_table`).
    """
    cols, rows = distribution_data_table(result, extra_columns)
    with open(path, "w", encoding="utf-8") as fh:
        for line in header:
            fh.write(f"# {line}\n")
        fh.write("\t".join(cols) + "\n")
        for row in rows:
            fh.write("\t".join(f"{v:.8g}" for v in row) + "\n")


def correlation_curve(
    centers: np.ndarray,
    base: float,
    slope: float,
    ref: float,
    *,
    var_base: float = 0.0,
    var_slope: float = 0.0,
    cov_base_slope: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Recta de correlación y(x) = base + slope·(x − ref) y su σ por punto.

    Es la δ(H), ΔEQ(H), δ(ΔEQ) o ΔEQ(IS) que el kernel aplica a cada columna
    de la malla. La σ propaga las varianzas de ``base`` y ``slope`` y su
    covarianza: σ²(x) = σ²_b + (x − ref)²·σ²_k + 2(x − ref)·cov(b, k).
    Con varianzas nulas (parámetros fijos) la banda es cero.
    """
    x = np.asarray(centers, dtype=float)
    dx = x - float(ref)
    curve = float(base) + float(slope) * dx
    var = float(var_base) + dx * dx * float(var_slope) + 2.0 * dx * float(cov_base_slope)
    return curve, np.sqrt(np.clip(var, 0.0, None))


def solve_bounded_lsq(
    A: np.ndarray,
    b: np.ndarray,
    lower,
    upper,
    *,
    max_iter: int | None = None,
):
    """min ‖A·x − b‖² con cotas por columna; devuelve un objeto con x/success/message.

    Las distribuciones solo usan cotas [0, ∞) (pesos, nítidos, línea base) y
    (−∞, ∞) (pendiente). Con ellas el problema es un NNLS si cada columna libre
    se desdobla en x⁺ − x⁻, y Lawson–Hanson (``scipy.optimize.nnls``) da el
    mismo óptimo que ``lsq_linear`` (TRF) mucho más deprisa: en el sistema
    aumentado de P(BHF) 1D (304×52) 0.001 s frente a 0.014 s, y en el de la 2D
    50×21 (2214×1052) 0.5 s frente a 13 s, porque la TRF actualiza su QR
    columna a columna en Python. Con cualquier otra cota, o si NNLS no
    converge, se usa ``lsq_linear`` como antes.
    """
    from types import SimpleNamespace
    A = np.asarray(A, dtype=float)
    b = np.asarray(b, dtype=float)
    lower = np.broadcast_to(np.asarray(lower, dtype=float), (A.shape[1],))
    upper = np.broadcast_to(np.asarray(upper, dtype=float), (A.shape[1],))
    free = np.isneginf(lower) & np.isposinf(upper)
    nonneg = (lower == 0.0) & np.isposinf(upper)

    def _trf():
        return lsq_linear(A, b, bounds=(np.array(lower), np.array(upper)),
                          lsmr_tol="auto", max_iter=max_iter)

    if not np.all(free | nonneg):
        return _trf()
    A2 = np.hstack([A, -A[:, free]]) if np.any(free) else A
    try:
        z, _rnorm = nnls(A2, b, maxiter=max(50, 10 * A2.shape[1]))
    except RuntimeError:
        return _trf()
    n = A.shape[1]
    x = z[:n].copy()
    x[free] -= z[n:]
    return SimpleNamespace(x=x, success=True, message="NNLS (Lawson–Hanson)")


def normalize_probability(weights: np.ndarray, bhf_centers: np.ndarray) -> np.ndarray:
    """Normaliza P para que su integral sobre BHF sea 1 si hay area positiva."""
    weights = np.maximum(np.asarray(weights, dtype=float), 0.0)
    bhf_centers = np.asarray(bhf_centers, dtype=float)
    if weights.size == 0:
        return weights.copy()
    area = float(np.trapezoid(weights, bhf_centers)) if weights.size > 1 else float(weights[0])
    if area <= 0 or not np.isfinite(area):
        return np.zeros_like(weights)
    return weights / area



def _finite_1d(name: str, values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if arr.size == 0 or not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} debe ser un array 1D finito y no vacio")
    return arr


def _component_value(component: dict[str, float], name: str, default: float) -> float:
    value = component.get(name, default)
    if value is None or not np.isfinite(value):
        raise ValueError(f"Componente nítido: {name} no es finito")
    return float(value)


def build_sharp_kernel(
    v: np.ndarray,
    components: list[dict[str, float]] | None,
    *,
    default_delta: float = 0.0,
    default_quad: float = 0.0,
    default_gamma: float = 0.18,
    default_gamma2_rel: float = 1.0,
    default_gamma3_rel: float = 1.0,
    default_int1: float = 1.0,
    default_int2_rel: float = 1.0,
    default_int3_rel: float = 1.0,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Kernel para componentes nítidos opcionales añadidos a la distribución.

    Cada componente puede tener ``kind`` = ``Sextete``, ``Doblete`` o
    ``Singlete``. Para sextetes se devuelve su BHF; para singletes/dobletes se
    devuelve NaN en ``sharp_bhf_centers`` porque no tienen campo hiperfino.

    La amplitud/profundidad no se incluye en el kernel: cada columna es el
    perfil de absorción por profundidad unitaria. El ajuste decide después si
    esa amplitud es libre o fija, según ``depth_fixed`` en el componente.
    """
    if not components:
        return None, None
    cols: list[np.ndarray] = []
    bhf_values: list[float] = []
    for comp in components:
        kind = str(comp.get("kind", "Sextete"))
        delta = _component_value(comp, "delta", default_delta)
        quad = _component_value(comp, "quad", default_quad)
        gamma = _component_value(comp, "gamma", default_gamma)
        gamma2_rel = _component_value(comp, "gamma2_rel", default_gamma2_rel)
        int1 = _component_value(comp, "int1", default_int1)
        int2_rel = _component_value(comp, "int2_rel", default_int2_rel)
        if kind == "Singlete":
            bhf_values.append(float("nan"))
            cols.append(singlet_absorption(v, delta=delta, gamma=gamma, int1=int1))
        elif kind == "Doblete":
            bhf_values.append(float("nan"))
            cols.append(doublet_absorption(v, delta=delta, quad=quad, gamma=gamma, gamma2_rel=gamma2_rel, int1=int1, int2_rel=int2_rel))
        elif kind == "Relajacion":
            if "bhf" not in comp:
                raise ValueError("Cada componente de relajación debe incluir 'bhf'")
            bhf = _component_value(comp, "bhf", np.nan)
            bhf_values.append(bhf)
            cols.append(
                relaxation_empirical_absorption(
                    v,
                    delta=delta,
                    quad=quad,
                    bhf=bhf,
                    gamma=gamma,
                    gamma2_rel=gamma2_rel,
                    gamma3_rel=_component_value(comp, "gamma3_rel", default_gamma3_rel),
                    int1=int1,
                    int2_rel=int2_rel,
                    int3_rel=_component_value(comp, "int3_rel", default_int3_rel),
                    blocked_fraction=_component_value(comp, "relax_fraction", 1.0),
                    log10_nu=_component_value(comp, "relax_log_nu", 5.0),
                )
            )
        elif kind == "BlumeTjon":
            if "bhf" not in comp:
                raise ValueError("Cada componente Blume-Tjon debe incluir 'bhf'")
            bhf = _component_value(comp, "bhf", np.nan)
            bhf_values.append(bhf)
            cols.append(
                blume_tjon_two_state_absorption(
                    v,
                    delta=delta,
                    quad=quad,
                    bhf=bhf,
                    gamma=gamma,
                    gamma2_rel=gamma2_rel,
                    gamma3_rel=_component_value(comp, "gamma3_rel", default_gamma3_rel),
                    int1=int1,
                    int2_rel=int2_rel,
                    int3_rel=_component_value(comp, "int3_rel", default_int3_rel),
                    log10_nu=_component_value(comp, "relax_log_nu", 5.0),
                )
            )
        elif kind == "NeelSize":
            if "bhf" not in comp:
                raise ValueError("Cada componente Néel debe incluir 'bhf'")
            bhf = _component_value(comp, "bhf", np.nan)
            bhf_values.append(bhf)
            cols.append(
                neel_size_relaxation_absorption(
                    v,
                    delta=delta,
                    quad=quad,
                    bhf=bhf,
                    gamma=gamma,
                    gamma2_rel=gamma2_rel,
                    gamma3_rel=_component_value(comp, "gamma3_rel", default_gamma3_rel),
                    int1=int1,
                    int2_rel=int2_rel,
                    int3_rel=_component_value(comp, "int3_rel", default_int3_rel),
                    temperature_k=_component_value(comp, "neel_temp_k", 300.0),
                    log10_keff=_component_value(comp, "neel_log10_keff", 4.0),
                    mean_d_nm=_component_value(comp, "neel_mean_d_nm", 8.0),
                    sigma_lognormal=_component_value(comp, "neel_sigma", 0.25),
                    log10_tau0=_component_value(comp, "neel_log10_tau0", -9.0),
                    n_bins=int(round(_component_value(comp, "neel_bins", 20.0))),
                )
            )
        else:
            if "bhf" not in comp:
                raise ValueError("Cada sextete nítido debe incluir 'bhf'")
            bhf = _component_value(comp, "bhf", np.nan)
            bhf_values.append(bhf)
            cols.append(
                sextet_absorption(
                    v,
                    delta=delta,
                    quad=quad,
                    bhf=bhf,
                    gamma=gamma,
                    gamma2_rel=gamma2_rel,
                    gamma3_rel=_component_value(comp, "gamma3_rel", default_gamma3_rel),
                    int1=int1,
                    int2_rel=int2_rel,
                    int3_rel=_component_value(comp, "int3_rel", default_int3_rel),
                )
            )
    return np.column_stack(cols), np.array(bhf_values, dtype=float)


def _component_depth(component: dict[str, float], default: float = 0.0) -> float:
    """Profundidad/amplitud de un nítido cuando se solicita que sea fija."""
    for name in ("depth", "weight", "amplitude", "amp"):
        if name in component:
            return max(0.0, _component_value(component, name, default))
    return max(0.0, float(default))


def _component_depth_is_fixed(component: dict[str, float]) -> bool:
    """Devuelve si la amplitud del nítido debe tratarse como fija."""
    return bool(
        component.get("depth_fixed", component.get("fixed_depth", component.get("amplitude_fixed", False)))
    )


def build_sharp_kernel_for_fit(
    v: np.ndarray,
    components: list[dict[str, float]] | None,
    *,
    default_delta: float = 0.0,
    default_quad: float = 0.0,
    default_gamma: float = 0.18,
    default_gamma2_rel: float = 1.0,
    default_gamma3_rel: float = 1.0,
    default_int1: float = 1.0,
    default_int2_rel: float = 1.0,
    default_int3_rel: float = 1.0,
) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray, np.ndarray, np.ndarray]:
    """Kernel de nítidos separando amplitudes libres y fijas.

    Returns
    -------
    K_free
        Columnas de los nítidos cuya profundidad se debe ajustar. ``None`` si
        no hay ninguna.
    sharp_bhf_centers
        Centros BHF/NaN de todos los nítidos, en el orden original.
    fixed_absorption
        Absorción positiva total de los nítidos con profundidad fija:
        ``K_fixed @ depth_fixed``. Debe restarse del modelo de transmisión.
    fixed_mask
        Booleano por nítido; True si su profundidad era fija.
    fixed_weights
        Pesos/profundidades en el orden original; NaN en los nítidos libres.
    """
    K_all, sharp_bhf_centers = build_sharp_kernel(
        v,
        components,
        default_delta=default_delta,
        default_quad=default_quad,
        default_gamma=default_gamma,
        default_gamma2_rel=default_gamma2_rel,
        default_gamma3_rel=default_gamma3_rel,
        default_int1=default_int1,
        default_int2_rel=default_int2_rel,
        default_int3_rel=default_int3_rel,
    )
    if K_all is None or not components:
        return None, None, np.zeros_like(v, dtype=float), np.zeros(0, dtype=bool), np.zeros(0, dtype=float)

    fixed_mask = np.array([_component_depth_is_fixed(c) for c in components], dtype=bool)
    fixed_weights = np.full(len(components), np.nan, dtype=float)
    fixed_absorption = np.zeros_like(v, dtype=float)
    if np.any(fixed_mask):
        vals = np.array([_component_depth(c) if fixed else 0.0 for c, fixed in zip(components, fixed_mask)], dtype=float)
        fixed_weights[fixed_mask] = vals[fixed_mask]
        fixed_absorption = K_all[:, fixed_mask] @ vals[fixed_mask]
    K_free = K_all[:, ~fixed_mask] if np.any(~fixed_mask) else None
    return K_free, sharp_bhf_centers, fixed_absorption, fixed_mask, fixed_weights


def merge_sharp_weights(
    free_weights: np.ndarray | None,
    fixed_mask: np.ndarray,
    fixed_weights: np.ndarray,
) -> np.ndarray | None:
    """Combina pesos libres ajustados y pesos fijos en el orden original."""
    if fixed_mask.size == 0:
        return None
    out = np.zeros(fixed_mask.size, dtype=float)
    out[fixed_mask] = np.maximum(fixed_weights[fixed_mask], 0.0)
    if np.any(~fixed_mask):
        if free_weights is None:
            raise ValueError("Faltan pesos libres de nítidos")
        out[~fixed_mask] = np.maximum(np.asarray(free_weights, dtype=float), 0.0)
    return out


# TODO (lejano): corrección de espesor en las distribuciones. Hoy todas suponen
# absorbente delgado (la GUI avisa si «Absorbente» no está en delgado). Plan:
#  - Formas paramétricas (Gaussiana, VBF, binomial, gaussianas 2D): ya van por
#    least_squares; basta saturar la absorción total como total_model() del
#    discreto (sat_scale, o src_fwhm/src_frac en la integral de transmisión).
#  - Histograma (Tikhonov/TV/MaxEnt, 1D y 2D): la exponencial rompe la
#    linealidad en P. Gauss–Newton: reescalar el núcleo con exp(−A_k/C) (o la
#    convolución con la fuente) del paso anterior y repetir el NNLS, 3–6 veces.
#    La banda MC y la L-curve lo heredan; el histograma 2D se encarece igual.
#  - C como global más en el bucle externo de la GUI; sesión, informes, CLI.
#  - Validar: una malla de un solo bin debe reproducir el sextete grueso del
#    discreto; recuperar una P(BHF) sintética gruesa. Fijar C suele ser mejor
#    que liberarlo (una P ancha imita el aplanamiento de las líneas intensas).
#  - Documentación: anexo apx_espesor (sección «Modo distribución») y el aviso
#    «thin-absorber» de la ayuda, que habrá que retirar.
def fit_hyperfine_distribution(
    v: np.ndarray,
    y: np.ndarray,
    *,
    variable: str = "bhf",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    pmin: float = 0.0,
    pmax: float = 50.0,
    nbins: int = 50,
    alpha: float = 1e-2,
    fit_baseline: bool = True,
    fit_slope: bool = True,
    baseline: float | None = None,
    slope: float | None = None,
    baseline_bounds: tuple[float, float] = (0.0, np.inf),
    slope_bounds: tuple[float, float] = (-np.inf, np.inf),
    sharp_components: list[dict[str, float]] | None = None,
    sigma: np.ndarray | None = None,
    rescale_columns: bool = True,
    reg_mode: str = "tikhonov",
    edge_anchor: float = 0.0,
    tv_iters: int = 8,
    profile: str = "Lorentziana",
    voigt_sigma: float = 0.05,
    delta_slope: float = 0.0,
    quad_slope: float = 0.0,
    h_ref: float | None = None,
    kernel_treatment: str = "1st_order",
    kernel_eta: float = 0.0,
    kernel_n_orient: int = 12,
    source_bhf: float = 33.0,
    source_theta: float = 0.0,
    absorber_theta: float = 0.0,
    band_replicas: int = 0,
    band_seed: int = 0,
) -> BhfDistributionFit:
    """Ajusta una distribución Hesse-Rübartsch de BHF o ΔEQ.

    ``band_replicas`` > 0 estima la banda 1σ de la P normalizada por Monte
    Carlo paramétrico (``probability_sigma`` del resultado): se re-resuelve el
    mismo problema acotado (mismo kernel, α y, en TV, los pesos IRLS finales)
    sobre el modelo ajustado más ruido gaussiano de σ·√χ²_ν. A diferencia de la
    covarianza linealizada (``weight_sigma``), respeta P ≥ 0: con picos
    rodeados de bins a cero, la lineal la sobrestima varias veces. MaxEnt no
    la calcula. Cuesta ``band_replicas`` resoluciones NNLS (milisegundos cada
    una), así que conviene pedirla solo en el ajuste final.

    variable='bhf': centers son campos hiperfinos.
    variable='quad': centers son valores de ΔEQ con BHF fijo en ``bhf``.

    ``profile`` selecciona la forma de línea del kernel: ``"Lorentziana"``
    (por defecto) o ``"Voigt"`` (con anchura gaussiana instrumental
    ``voigt_sigma`` en mm/s). El perfil se aplica de forma determinista solo a
    la construcción del kernel, sin heredar ni dejar estado global.

    ``reg_mode`` selecciona el regularizador: ``"tikhonov"`` (curvatura, suave),
    ``"tv"`` (variación total, bordes) o ``"maxent"`` (máxima entropía: la P menos
    comprometida compatible con los datos, positiva y sin oscilaciones espurias).

    ``delta_slope`` / ``quad_slope`` (mm/s·T⁻¹) activan la correlación lineal
    δ(H)/ΔEQ(H) en el kernel (opt-in; 0 = comportamiento clásico).
    """
    v = _finite_1d("v", v)
    y = _finite_1d("y", y)
    if v.size != y.size:
        raise ValueError("v e y deben tener la misma longitud")
    sigma_arr = None
    if sigma is not None:
        sigma_arr = _finite_1d("sigma", sigma)
        if sigma_arr.size != y.size:
            raise ValueError("sigma debe tener la misma longitud que y")
        sigma_arr = np.maximum(sigma_arr, 1e-12)
    if alpha < 0 or not np.isfinite(alpha):
        raise ValueError("alpha debe ser finito y >= 0")

    if baseline is None:
        baseline = float(np.percentile(y, 90))
    if slope is None:
        slope = 0.0

    centers = parameter_grid(pmin, pmax, nbins)
    with line_profile(profile, voigt_sigma):
        K = build_hyperfine_distribution_kernel(
            v,
            centers,
            variable=variable,
            delta=delta,
            quad=quad,
            bhf=bhf,
            gamma=gamma,
            gamma2_rel=gamma2_rel,
            gamma3_rel=gamma3_rel,
            int1=int1,
            int2_rel=int2_rel,
            int3_rel=int3_rel,
            delta_slope=delta_slope,
            quad_slope=quad_slope,
            h_ref=h_ref,
            treatment=kernel_treatment,
            eta=kernel_eta,
            n_orient=kernel_n_orient,
            source_bhf=source_bhf,
            source_theta=source_theta,
            absorber_theta=absorber_theta,
        )
        K_sharp, sharp_bhf_centers, fixed_sharp_abs, sharp_fixed_mask, fixed_sharp_weights = build_sharp_kernel_for_fit(
            v,
            sharp_components,
            default_delta=delta,
            default_quad=quad,
            default_gamma=gamma,
            default_gamma2_rel=gamma2_rel,
            default_gamma3_rel=gamma3_rel,
            default_int1=int1,
            default_int2_rel=int2_rel,
            default_int3_rel=int3_rel,
        )
    # Penalizador: Tikhonov L2 (segunda diferencia, suave), Variación Total
    # (primera diferencia, L1 → picos afilados con bordes) o Máxima Entropía.
    use_tv = str(reg_mode).lower() in ("tv", "total_variation", "variacion_total")
    use_maxent = str(reg_mode).lower() in ("maxent", "max_entropy", "maxima_entropia", "entropia")
    if use_tv:
        L = first_difference_matrix(centers.size)
    else:
        L = second_difference_matrix(centers.size)


    # Los nítidos con profundidad fija aportan absorción conocida al modelo:
    # y = fondo - K_dist·P - K_sharp_free·q - fixed_sharp_abs.
    # Se pasa al solve como y + fixed_sharp_abs para que sólo queden libres P y q.
    y_work = y.astype(float).copy() + fixed_sharp_abs
    columns: list[np.ndarray] = []
    lower: list[float] = []
    upper: list[float] = []
    labels: list[str] = []

    if fit_baseline:
        columns.append(np.ones_like(v))
        lower.append(float(baseline_bounds[0]))
        upper.append(float(baseline_bounds[1]))
        labels.append("baseline")
    else:
        y_work -= float(baseline)

    if fit_slope:
        columns.append(v)
        lower.append(float(slope_bounds[0]))
        upper.append(float(slope_bounds[1]))
        labels.append("slope")
    else:
        y_work -= float(slope) * v

    # El modelo tiene signo de absorcion: y = fondo - K @ P.
    dist_start = len(labels)
    for j in range(centers.size):
        columns.append(-K[:, j])
        lower.append(0.0)
        upper.append(np.inf)
        labels.append(f"P{j}")
    dist_end = len(labels)

    sharp_start = len(labels)
    if K_sharp is not None:
        for j in range(K_sharp.shape[1]):
            columns.append(-K_sharp[:, j])
            lower.append(0.0)
            upper.append(np.inf)
            labels.append(f"sharp{j}")
    sharp_end = len(labels)

    X = np.column_stack(columns)

    # Mejora 13: preacondicionamiento por escala de columnas de la distribución.
    # Para BHF pequeño el sextete colapsa y las columnas de K se vuelven casi
    # colineales (||K_j|| muy dispares), lo que hace mal condicionado el sistema
    # acotado. Reescalando K_j → K_j/s_j y P_j → P_j·s_j el problema queda mejor
    # condicionado SIN cambiar la solución (reparametrización exacta). El
    # penalizador y los pesos se ajustan en consecuencia.
    scale = np.ones(X.shape[1], dtype=float)
    if rescale_columns and dist_end > dist_start:
        Kw = K / sigma_arr[:, None] if sigma_arr is not None else K
        col_norms = np.linalg.norm(Kw, axis=0)
        col_norms = np.where(np.isfinite(col_norms) & (col_norms > 1e-12), col_norms, 1.0)
        scale[dist_start:dist_end] = col_norms

    Xs = X / scale[None, :]
    L_scaled = L / scale[None, dist_start:dist_end]
    if sigma_arr is not None:
        X_fit = Xs / sigma_arr[:, None]
        y_fit = y_work / sigma_arr
    else:
        X_fit = Xs
        y_fit = y_work
    lower_arr = np.array(lower)
    upper_arr = np.array(upper)

    # Normalización adimensional de α: el término de datos es un χ² ~ N y el
    # penalizador α·‖L·P‖² va en unidades de absorción, de modo que el α útil
    # depende de N, del ruido (σ) y de la profundidad de absorción. Escalando el
    # penalizador por λ_ref = ‖A_dist‖²_F / ‖L_scaled‖²_F (operadores blanqueados),
    # α queda adimensional y log α≈0 cae en el codo de la L-curve para cualquier
    # espectro. Con α→0 se recupera el caso sin regularizar (retrocompatible en
    # comportamiento, no en el valor numérico de α).
    _A_dist = X_fit[:, dist_start:dist_end]
    _data_scale = float(np.sum(_A_dist * _A_dist))
    _pen_scale = float(np.sum(L_scaled * L_scaled))
    lambda_ref = (_data_scale / _pen_scale) if _pen_scale > 1e-30 else 1.0
    # Constante de calibración: sitúa el codo de la L-curve cerca de log α ≈ 0
    # (α ≈ 1 = balance datos/suavidad) para una configuración típica. La
    # dependencia residual con nbins/γ mantiene el codo dentro de ~[-2, +2].
    alpha_eff = float(alpha) * lambda_ref * ALPHA_REF_SCALE

    # Anclajes de borde (BETA1/BETA2 de NORMOS-DIST): fuerzan P→0 en el primer
    # y último bin. Van con su PROPIO peso, no multiplicados por α — igual que
    # en NORMOS, que los suma a las esquinas DESPUÉS de escalar por λ. Se
    # normalizan con el mismo λ_ref para que β y α sean comparables.
    _anchor_rows = edge_anchor_rows(centers.size, 1.0)
    _anchor_scaled = (_anchor_rows / scale[None, dist_start:dist_end]
                      if _anchor_rows.size else _anchor_rows)
    _beta_eff = float(edge_anchor) * lambda_ref * ALPHA_REF_SCALE

    def _solve(L_pen_scaled: np.ndarray, y_vec: np.ndarray | None = None):
        blocks = [np.sqrt(alpha_eff) * L_pen_scaled]
        if _anchor_scaled.size and _beta_eff > 0.0:
            blocks.append(np.sqrt(_beta_eff) * _anchor_scaled)
        L_all = np.vstack(blocks)
        reg = np.zeros((L_all.shape[0], X.shape[1]), dtype=float)
        reg[:, dist_start:dist_end] = L_all
        X_aug = np.vstack([X_fit, reg])
        y_aug = np.concatenate([y_fit if y_vec is None else y_vec,
                                np.zeros(L_all.shape[0], dtype=float)])
        # Las cotas de p̃ = escala·P coinciden con las de P (0 e ∞ invariantes).
        res = solve_bounded_lsq(X_aug, y_aug, lower_arr, upper_arr, max_iter=2000)
        return res, res.x / scale  # deshace el escalado para recuperar P físico

    def _solve_maxent():
        """Máxima entropía: minimiza ½‖(y−Xz)/σ‖² − α·S(P), S = −Σ Pⱼ log(Pⱼ/mⱼ).

        La entropía no es cuadrática ⇒ no vale ``lsq_linear``: se usa L-BFGS-B con
        gradiente analítico sobre las variables físicas z=[baseline,slope,P,sharp]
        con cotas P≥0. mⱼ es el modelo por defecto (plano). El óptimo es convexo.
        """
        from scipy.optimize import minimize
        if sigma_arr is not None:
            Xw = X / sigma_arr[:, None]
            yw = y_work / sigma_arr
        else:
            Xw = X
            yw = y_work
        XtWX = Xw.T @ Xw
        # Warm start desde el Tikhonov lineal (fija también la escala de m).
        _res0, params0 = _solve(L_scaled)
        P0 = np.maximum(params0[dist_start:dist_end], 0.0)
        m = max(float(np.mean(P0)), 1e-9)
        x0 = np.clip(np.asarray(params0, dtype=float), lower_arr, upper_arr)
        x0[dist_start:dist_end] = np.maximum(x0[dist_start:dist_end], m * 1e-3)
        idx = np.arange(dist_start, dist_end)

        def phi_grad(z):
            r = yw - Xw @ z
            g = -(Xw.T @ r)
            P = z[dist_start:dist_end]
            Pg = np.maximum(P, 1e-300)
            ent = float(np.sum(P * np.log(Pg / m)))          # −α·S = +α·Σ P log(P/m)
            phi = 0.5 * float(r @ r) + alpha_eff * ent
            g[dist_start:dist_end] += alpha_eff * (np.log(Pg / m) + 1.0)
            return phi, g

        bounds = list(zip(lower_arr.tolist(), upper_arr.tolist()))
        opt = minimize(phi_grad, x0, jac=True, method="L-BFGS-B", bounds=bounds,
                       options={"maxiter": 3000, "ftol": 1e-12, "gtol": 1e-8})
        # dof efectivos con el Hessiano MaxEnt: XᵀWX + α·diag(1/Pⱼ).
        try:
            H = XtWX.copy()
            Pd = np.maximum(opt.x[dist_start:dist_end], 1e-9)
            H[idx, idx] += alpha_eff * (1.0 / Pd)
            eff = float(np.trace(np.linalg.solve(H, XtWX)))
        except Exception:
            eff = float(X.shape[1])
        return opt, opt.x, eff

    def _solve_tv(y_vec: np.ndarray | None = None):
        # IRLS para ‖α^{1/2} D P‖₁: en cada iteración se resuelve un Tikhonov
        # ponderado con pesos w_k = 1/√((D P)_k² + ε²). Converge a la solución
        # de variación total, que preserva bordes (picos afilados).
        L_eff = L_scaled.copy()
        res_tv = None
        p_tv = None
        for _ in range(max(1, int(tv_iters))):
            res_tv, p_tv = _solve(L_eff, y_vec)
            p_phys = p_tv[dist_start:dist_end]
            dp = L @ p_phys  # primera diferencia del P físico
            eps = max(1e-3 * float(np.max(np.abs(p_phys))) if p_phys.size else 1e-6, 1e-9)
            w_tv = 1.0 / np.sqrt(dp ** 2 + eps ** 2)
            L_eff = (np.sqrt(w_tv)[:, None]) * L_scaled
        return res_tv, p_tv, w_tv

    if use_maxent:
        result, params, eff_dof_maxent = _solve_maxent()
        L_stats = None
    elif use_tv:
        result, params, w = _solve_tv()
        # Operador efectivo (sin escala) para dof y covarianza: √w · D.
        L_stats = (np.sqrt(w)[:, None]) * L
    else:
        result, params = _solve(L_scaled)
        L_stats = L

    baseline_fit = float(params[labels.index("baseline")]) if fit_baseline else float(baseline)
    slope_fit = float(params[labels.index("slope")]) if fit_slope else float(slope)
    weights = np.maximum(params[dist_start:dist_end], 0.0)
    sharp_weights_free = np.maximum(params[sharp_start:sharp_end], 0.0) if sharp_end > sharp_start else None
    sharp_weights = merge_sharp_weights(sharp_weights_free, sharp_fixed_mask, fixed_sharp_weights)
    fitted = baseline_fit + slope_fit * v - K @ weights - fixed_sharp_abs
    if K_sharp is not None and sharp_weights_free is not None:
        fitted = fitted - K_sharp @ sharp_weights_free
    residuals = y - fitted
    rms = float(np.sqrt(np.mean(residuals**2)))

    if use_maxent:
        # dof desde el Hessiano MaxEnt; sin covarianza lineal fiable (fallback).
        eff_dof = eff_dof_maxent
        weight_sigma = None
    else:
        try:
            eff_dof = tikhonov_effective_dof(
                X, L_stats, alpha_eff, dist_start, dist_end, sigma=sigma_arr
            )
        except Exception:
            eff_dof = float(X.shape[1])

        try:
            weight_sigma = distribution_weight_sigma(
                X, L_stats, alpha_eff, dist_start, dist_end, residuals, eff_dof, sigma=sigma_arr
            )
        except Exception:
            weight_sigma = None

    prob_sigma = None
    moment_cov = None
    if band_replicas and int(band_replicas) > 1 and not use_maxent:
        # Réplicas del espectro: modelo ajustado (en el espacio de trabajo
        # blanqueado del solve) más ruido de la σ de los datos escalada por el
        # χ²_ν efectivo, como la covarianza lineal y el ajuste discreto.
        sig_w = sigma_arr if sigma_arr is not None else np.full(v.size, max(rms, 1e-12))
        chi2_nu = float(np.sum((residuals / sig_w) ** 2)) / max(v.size - float(eff_dof), 1.0)
        noise = np.sqrt(max(chi2_nu, 0.0))
        model_fit = (X @ params) / (sigma_arr if sigma_arr is not None else 1.0)
        rng = np.random.default_rng(int(band_seed))
        reps = []
        for _ in range(int(band_replicas)):
            y_rep = model_fit + noise * rng.standard_normal(v.size) * (
                1.0 if sigma_arr is not None else sig_w)
            # TV re-itera su IRLS en cada réplica: con los pesos finales
            # congelados la banda salía ~2× estrecha frente a reajustes reales.
            p_rep = _solve_tv(y_rep)[1] if use_tv else _solve(L_scaled, y_rep)[1]
            reps.append(normalize_probability(np.maximum(p_rep[dist_start:dist_end], 0.0), centers))
        prob_sigma = np.std(np.asarray(reps), axis=0, ddof=1)
        moment_cov = moment_samples_cov([(centers, r) for r in reps])

    return BhfDistributionFit(
        bhf_centers=centers,
        weights=weights,
        probability=normalize_probability(weights, centers),
        fitted_curve=fitted,
        residuals=residuals,
        baseline=baseline_fit,
        slope=slope_fit,
        alpha=float(alpha),
        edge_pileup=edge_pileup_ratio(weights),
        rms=rms,
        success=bool(result.success),
        message=str(result.message),
        sharp_bhf_centers=sharp_bhf_centers,
        sharp_weights=sharp_weights,
        effective_dof=eff_dof,
        weight_sigma=weight_sigma,
        probability_sigma=prob_sigma,
        moment_cov=moment_cov,
        shape="Histograma",
        reg_mode=str(reg_mode),
        delta_slope=float(delta_slope),
        quad_slope=float(quad_slope),
        slope_ref=float(np.mean(centers)) if h_ref is None else float(h_ref),
    )


def fit_vbf_hyperfine_distribution(
    v: np.ndarray,
    y: np.ndarray,
    *,
    n_components: int = 2,
    profile: str = "Voigt",
    voigt_sigma: float = 0.05,
    variable: str = "bhf",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    pmin: float = 0.0,
    pmax: float = 50.0,
    nbins: int = 80,
    baseline: float | None = None,
    slope: float | None = None,
    fit_baseline: bool = True,
    fit_slope: bool = True,
    sharp_components: list[dict[str, float]] | None = None,
    delta_slope: float = 0.0,
    quad_slope: float = 0.0,
    h_ref: float | None = None,
    shape: str = "VBF",
    sigma_min: float | None = None,
    sigma_max: float | None = None,
    sigma: np.ndarray | None = None,
) -> BhfDistributionFit:
    """VBF (Voigt-Based Fitting, Rancourt–Ping 1991): P como suma de N gaussianas.

    Con ``sigma`` (σ de los datos por canal) los residuos se ponderan, como en
    el histograma y el Czjzek; sin ella, todos los canales pesan igual.

    Ajusta ``n_components`` gaussianas sobre un kernel Voigt (o Lorentziano). Cada
    componente aporta parámetros con significado físico (A_k, μ_k, σ_k), que se
    **guardan** en ``vbf_components`` (ordenados por μ) — esa es la ventaja del VBF
    frente a Hesse-Rübartsch. Admite correlación δ(H)/ΔEQ(H)
    (``delta_slope``/``quad_slope``) y componentes nítidos.

    El caso ``n_components=1`` con ``profile="Lorentz"`` es la clásica **distribución
    gaussiana** simple: la GUI la ofrece con la etiqueta ``shape="Gaussiana"``, que
    se propaga al resultado mediante el parámetro ``shape``.

    ``sigma_min``/``sigma_max`` limitan la anchura σ de TODAS las gaussianas
    (unidades de la variable; ``None`` o ≤ 0 = automático: de 0.001 a la
    anchura de la malla). Los límites aplicados se devuelven en
    ``vbf_sigma_bounds``.
    """
    from scipy.optimize import least_squares
    v = _finite_1d("v", v); y = _finite_1d("y", y)
    N = max(1, int(n_components))
    centers = parameter_grid(pmin, pmax, nbins)
    with line_profile(profile, voigt_sigma):
        K = build_hyperfine_distribution_kernel(
            v, centers, variable=variable, delta=delta, quad=quad, bhf=bhf, gamma=gamma,
            delta_slope=delta_slope, quad_slope=quad_slope, h_ref=h_ref)
        K_sharp, sharp_bhf_centers, fixed_sharp_abs, sharp_fixed_mask, fixed_sharp_weights = build_sharp_kernel_for_fit(
            v, sharp_components, default_delta=delta, default_quad=quad, default_gamma=gamma)
    n_sharp = K_sharp.shape[1] if K_sharp is not None else 0
    if baseline is None:
        baseline = float(np.percentile(y, 90))
    if slope is None:
        slope = 0.0
    rng = max(float(pmax) - float(pmin), 1e-3)
    amp0 = max(1e-6, float(np.percentile(y, 90) - np.min(y)))

    def gauss_weights(center: float, sigma: float) -> np.ndarray:
        sigma = max(float(sigma), 1e-6)
        w = np.exp(-0.5 * ((centers - center) / sigma) ** 2)
        if w.size and float(np.max(w)) <= 0.0:
            # σ ≪ paso de malla con μ entre nodos: la gaussiana discretizada
            # subdesborda a cero y el componente desaparecería con jacobiano
            # nulo; se colapsa al nodo más próximo (delta discreta).
            w = np.zeros_like(w)
            w[int(np.argmin(np.abs(centers - center)))] = 1.0
        area = np.trapezoid(w, centers) if w.size > 1 else w[0]
        return w / max(float(area), 1e-12)

    # baseline/slope entran en el vector solo si son libres; si están fijos se
    # usan como constantes (antes se ajustaban siempre, ignorando el fijado).
    n_lin = int(fit_baseline) + int(fit_slope)

    def lin_part(x: np.ndarray) -> tuple[float, float]:
        i = 0
        if fit_baseline:
            b0 = float(x[0]); i = 1
        else:
            b0 = float(baseline)
        sl = float(x[i]) if fit_slope else float(slope)
        return b0, sl

    def comp_view(x: np.ndarray) -> np.ndarray:
        return np.asarray(x[n_lin:n_lin + 3 * N]).reshape(N, 3)

    def total_w(comp: np.ndarray) -> np.ndarray:
        w = np.zeros(centers.size, dtype=float)
        for A, mu, log_sig in comp:
            w = w + max(float(A), 0.0) * gauss_weights(float(mu), float(np.exp(log_sig)))
        return w

    pesos = data_weights(sigma, y.size)

    def residual(x: np.ndarray) -> np.ndarray:
        b0, sl = lin_part(x)
        w = total_w(comp_view(x))
        r = b0 + sl * v - K @ w - fixed_sharp_abs - y
        if K_sharp is not None and n_sharp:
            r = r - K_sharp @ np.maximum(x[n_lin + 3 * N:n_lin + 3 * N + n_sharp], 0.0)
        return r * pesos if pesos is not None else r

    sig_lo, sig_hi = vbf_sigma_bounds(1e-3, rng, sigma_min, sigma_max)
    log_sig_lo, log_sig_hi = np.log(sig_lo), np.log(sig_hi)
    sig0 = min(max(rng / (3.0 * N), sig_lo), sig_hi)
    mus0 = (np.linspace(float(pmin) + rng / (N + 1), float(pmax) - rng / (N + 1), N)
            if N > 1 else np.array([0.5 * (float(pmin) + float(pmax))]))
    lo, hi, x0 = [], [], []
    if fit_baseline:
        lo.append(0.0); hi.append(np.inf); x0.append(float(baseline))
    if fit_slope:
        lo.append(-np.inf); hi.append(np.inf); x0.append(float(slope))
    for mu in mus0:
        lo += [0.0, float(pmin), log_sig_lo]
        hi += [np.inf, float(pmax), log_sig_hi]
        x0 += [amp0 / N, float(mu), float(np.log(sig0))]
    lo += [0.0] * n_sharp
    hi += [np.inf] * n_sharp
    x0 += [amp0 / max(n_sharp, 1)] * n_sharp
    lo_arr = np.array(lo); hi_arr = np.array(hi)
    res = least_squares(residual, np.clip(np.array(x0), lo_arr, hi_arr),
                        bounds=(lo_arr, hi_arr), max_nfev=4000)

    comp = comp_view(res.x)
    w = total_w(comp)
    b0_fit, sl_fit = lin_part(res.x)
    sharp_weights_free = np.maximum(res.x[n_lin + 3 * N:n_lin + 3 * N + n_sharp], 0.0) if n_sharp else None
    sharp_weights_arr = merge_sharp_weights(sharp_weights_free, sharp_fixed_mask, fixed_sharp_weights)
    fitted = b0_fit + sl_fit * v - K @ w - fixed_sharp_abs
    if K_sharp is not None and sharp_weights_free is not None:
        fitted = fitted - K_sharp @ sharp_weights_free
    residuals = y - fitted
    # Ordenar por μ (evita el label switching) y guardar (A, μ, σ).
    comps = tuple(sorted(
        ((max(float(A), 0.0), float(mu), float(np.exp(log_sig))) for A, mu, log_sig in comp),
        key=lambda c: c[1]))
    dominant = max(comps, key=lambda c: c[0]) if comps else (0.0, 0.0, 0.0)
    # A_k = área de cada gaussiana (gauss_weights está normalizada a área unidad);
    # el % es la fracción relativa A_k/ΣA (población de cada entorno).
    area_tot = sum(A for A, _, _ in comps)
    summary = ", ".join(
        f"(A={A:.3g}[{100.0 * A / area_tot:.0f}%], μ={mu:.4g}, σ={sg:.3g})"
        if area_tot > 0 else f"(A={A:.3g}, μ={mu:.4g}, σ={sg:.3g})"
        for A, mu, sg in comps)
    return BhfDistributionFit(
        bhf_centers=centers,
        weights=w,
        probability=normalize_probability(w, centers),
        fitted_curve=fitted,
        residuals=residuals,
        baseline=b0_fit,
        slope=sl_fit,
        alpha=0.0,
        rms=float(np.sqrt(np.mean(residuals**2))),
        success=bool(res.success),
        message=f"VBF {variable} N={N}: {summary}; {res.message}",
        sharp_bhf_centers=sharp_bhf_centers,
        sharp_weights=sharp_weights_arr,
        fitted_dist_center=float(dominant[1]),
        fitted_dist_sigma=float(dominant[2]),
        vbf_components=comps,
        shape=str(shape),
        delta_slope=float(delta_slope),
        quad_slope=float(quad_slope),
        slope_ref=float(np.mean(centers)) if h_ref is None else float(h_ref),
        vbf_n_components=int(N),
        vbf_sigma_bounds=(float(sig_lo), float(sig_hi)),
        # Forma paramétrica: los grados de libertad que consume son sus
        # parámetros ajustados (gaussianas, fondo libre y nítidos libres).
        effective_dof=float(res.x.size),
        moment_cov=parametric_moment_cov(
            lambda x: (centers, total_w(comp_view(x))), res.x, res.jac,
            float(res.cost), y.size, weighted=pesos is not None),
    )


#: Grados de libertad del modelo de Czjzek: las 5 componentes independientes
#: del tensor gradiente de campo eléctrico (simétrico y de traza nula).
CZJZEK_DOF = 5


def czjzek_weights(centers: np.ndarray, sigma: float, delta0: float = 0.0) -> np.ndarray:
    """Densidad de ΔEQ del modelo de Czjzek (puro o extendido), de área 1 en la malla.

    Si las cargas que rodean al Fe están distribuidas al azar (vidrios,
    amorfos), las 5 componentes independientes del gradiente de campo
    eléctrico son gaussianas de igual varianza (Czjzek et al. 1981), y
    ΔEQ = (eQ/2)·|Vzz|·√(1 + η²/3) es proporcional a la norma de ese
    vector de 5 componentes. Por tanto ΔEQ/σ sigue una distribución χ de 5
    grados de libertad::

        P(ΔEQ) ∝ ΔEQ⁴ · exp(−ΔEQ²/2σ²)     (moda 2σ, media ≈ 2.13σ)

    En el modelo extendido (Le Caër y Brand 1998) el tensor es la suma de uno
    fijo, el del entorno ordenado, y del aleatorio de Czjzek. Como la parte
    aleatoria es isótropa en las 5 dimensiones, ΔEQ solo depende de la norma
    de la parte fija, ``delta0``: ΔEQ/σ sigue una χ no central de 5 grados de
    libertad y parámetro ΔEQ₀/σ. Con ΔEQ₀ = 0 es el modelo puro; con
    ΔEQ₀ ≫ σ tiende a una gaussiana de centro ΔEQ₀ y anchura σ.

    El ajuste de dobletes no ve η (ni el signo de ΔEQ): solo la marginal de
    |ΔEQ|, que es esta. Los nodos con ΔEQ ≤ 0 pesan cero.
    """
    from scipy.special import ive

    c = np.asarray(centers, dtype=float)
    sigma = max(float(sigma), 1e-9)
    lam = max(float(delta0), 0.0) / sigma
    x = c / sigma
    pos = x > 0.0
    logw = np.full(c.shape, -np.inf)
    k = CZJZEK_DOF
    with np.errstate(divide="ignore", invalid="ignore", under="ignore"):
        if lam < 1e-6:
            logw[pos] = (k - 1) * np.log(x[pos]) - 0.5 * x[pos] ** 2
        else:
            # χ no central: x^{k/2}·λ^{1−k/2}·e^{−(x−λ)²/2}·Ive_{k/2−1}(λx),
            # con la Bessel escalada (Ive = I·e^{−z}) para no desbordar.
            logw[pos] = (0.5 * k * np.log(x[pos]) - 0.5 * (x[pos] - lam) ** 2
                         + np.log(ive(0.5 * k - 1.0, lam * x[pos])))
    w = np.zeros_like(c)
    if np.any(np.isfinite(logw)):
        w = np.exp(logw - np.max(logw[np.isfinite(logw)]))
        w[~np.isfinite(w)] = 0.0
    if not np.any(w > 0.0):
        # σ ≪ paso de malla: toda la densidad en el nodo de la moda.
        moda = max(float(delta0), 2.0 * sigma)
        w = np.zeros_like(c)
        w[int(np.argmin(np.abs(c - moda)))] = 1.0
    area = np.trapezoid(w, c) if w.size > 1 else float(w[0])
    return w / max(float(area), 1e-12)


def fit_czjzek_hyperfine_distribution(
    v: np.ndarray,
    y: np.ndarray,
    *,
    extended: bool = False,
    profile: str = "Lorentz",
    voigt_sigma: float = 0.05,
    variable: str = "quad",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    pmin: float = 0.0,
    pmax: float = 3.0,
    nbins: int = 120,
    baseline: float | None = None,
    slope: float | None = None,
    fit_baseline: bool = True,
    fit_slope: bool = True,
    sharp_components: list[dict[str, float]] | None = None,
    delta_slope: float = 0.0,
    quad_slope: float = 0.0,
    h_ref: float | None = None,
    sigma: np.ndarray | None = None,
    czjzek_sigma: float | None = None,
    fit_czjzek_sigma: bool = True,
    czjzek_delta0: float | None = None,
    fit_czjzek_delta0: bool = True,
) -> BhfDistributionFit:
    """P(ΔEQ) con la forma de Czjzek (``extended=False``) o Czjzek extendida.

    ``czjzek_sigma``/``czjzek_delta0`` son los valores iniciales (o los fijos,
    con ``fit_czjzek_sigma``/``fit_czjzek_delta0`` a False: así se reproduce
    un STG fijo de NORMOS-DIST, con σ = √(STG² + DTQ²)). Sin valor, se prueban
    varios arranques repartidos por la malla.

    Ver :func:`czjzek_weights`. Parámetros ajustados: área A, escala σ y, en
    el modelo extendido, ΔEQ₀ ≥ 0; más fondo y nítidos libres. Admite la
    correlación δ(ΔEQ) (``delta_slope``). Con ``sigma`` (σ de los datos) los
    residuos se ponderan y los errores de σ y ΔEQ₀ son absolutos; sin ella se
    escalan con el χ² reducido.
    """
    from scipy.optimize import least_squares
    v = _finite_1d("v", v); y = _finite_1d("y", y)
    centers = parameter_grid(pmin, pmax, nbins)
    with line_profile(profile, voigt_sigma):
        K = build_hyperfine_distribution_kernel(
            v, centers, variable=variable, delta=delta, quad=quad, bhf=bhf, gamma=gamma,
            delta_slope=delta_slope, quad_slope=quad_slope, h_ref=h_ref)
        K_sharp, sharp_bhf_centers, fixed_sharp_abs, sharp_fixed_mask, fixed_sharp_weights = build_sharp_kernel_for_fit(
            v, sharp_components, default_delta=delta, default_quad=quad, default_gamma=gamma)
    n_sharp = K_sharp.shape[1] if K_sharp is not None else 0
    if baseline is None:
        baseline = float(np.percentile(y, 90))
    if slope is None:
        slope = 0.0
    weights_data = data_weights(sigma, y.size)
    hi_grid = max(float(pmax), 1e-3)
    rng = max(float(pmax) - float(pmin), 1e-3)
    amp0 = max(1e-6, float(np.percentile(y, 90) - np.min(y)))
    n_lin = int(fit_baseline) + int(fit_slope)
    libre_sig = bool(fit_czjzek_sigma) or czjzek_sigma is None
    libre_d0 = extended and (bool(fit_czjzek_delta0) or czjzek_delta0 is None)
    sig_fijo = max(float(czjzek_sigma or 0.0), 1e-9)
    d0_fijo = max(float(czjzek_delta0 or 0.0), 0.0) if extended else 0.0
    n_shape = 1 + int(libre_sig) + int(libre_d0)   # A[, log σ][, ΔEQ₀]

    def lin_part(x: np.ndarray) -> tuple[float, float]:
        i = 0
        if fit_baseline:
            b0 = float(x[0]); i = 1
        else:
            b0 = float(baseline)
        sl = float(x[i]) if fit_slope else float(slope)
        return b0, sl

    def shape_part(x: np.ndarray) -> tuple[float, float, float]:
        k = n_lin
        A = float(x[k]); k += 1
        sg = float(np.exp(x[k])) if libre_sig else sig_fijo
        k += int(libre_sig)
        d0 = float(x[k]) if libre_d0 else d0_fijo
        return max(A, 0.0), sg, max(d0, 0.0)

    def model(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        b0, sl = lin_part(x)
        A, sg, d0 = shape_part(x)
        w = A * czjzek_weights(centers, sg, d0)
        m = b0 + sl * v - K @ w - fixed_sharp_abs
        if K_sharp is not None and n_sharp:
            m = m - K_sharp @ np.maximum(x[n_lin + n_shape:n_lin + n_shape + n_sharp], 0.0)
        return m, w

    def residual(x: np.ndarray) -> np.ndarray:
        r = model(x)[0] - y
        return r * weights_data if weights_data is not None else r

    sig_lo, sig_hi = 1e-3, max(hi_grid, 1e-2)
    lo, hi = [], []
    lin0: list[float] = []
    if fit_baseline:
        lo.append(0.0); hi.append(np.inf); lin0.append(float(baseline))
    if fit_slope:
        lo.append(-np.inf); hi.append(np.inf); lin0.append(float(slope))
    lo.append(0.0); hi.append(np.inf)
    if libre_sig:
        lo.append(np.log(sig_lo)); hi.append(np.log(sig_hi))
    if libre_d0:
        lo.append(0.0); hi.append(hi_grid)
    lo += [0.0] * n_sharp; hi += [np.inf] * n_sharp
    lo_arr, hi_arr = np.array(lo), np.array(hi)
    sharp0 = [amp0 / max(n_sharp, 1)] * n_sharp
    # Varios arranques baratos (el kernel ya está construido): la moda de la
    # χ₅ es 2σ, así que se reparten modas por la malla.
    candidatos: list[tuple[float, float]] = []      # (σ, ΔEQ₀) de arranque
    if czjzek_sigma is not None or czjzek_delta0 is not None:
        candidatos.append((czjzek_sigma if czjzek_sigma is not None else rng / 8.0,
                           czjzek_delta0 if czjzek_delta0 is not None else 0.0))
    for frac in (0.25, 0.45, 0.65):
        moda = float(pmin) + frac * rng
        if extended:
            candidatos.append((rng / 8.0, moda))
            candidatos.append((moda / 2.0, 0.0))
        else:
            candidatos.append((moda / 2.0, 0.0))
    starts = []
    for sg0, d00 in candidatos:
        st = [amp0]
        if libre_sig:
            st.append(np.log(max(float(sg0), sig_lo)))
        if libre_d0:
            st.append(min(max(float(d00), 0.0), hi_grid))
        if st not in starts:
            starts.append(st)
    res = None
    for st in starts:
        x0 = np.clip(np.array(lin0 + st + sharp0, dtype=float), lo_arr, hi_arr)
        cand = least_squares(residual, x0, bounds=(lo_arr, hi_arr), max_nfev=2000)
        if res is None or cand.cost < res.cost:
            res = cand

    fitted, w = model(res.x)
    b0_fit, sl_fit = lin_part(res.x)
    A_fit, sig_fit, d0_fit = shape_part(res.x)
    residuals = y - fitted
    sharp_weights_free = (np.maximum(res.x[n_lin + n_shape:n_lin + n_shape + n_sharp], 0.0)
                          if n_sharp else None)
    sharp_weights_arr = merge_sharp_weights(sharp_weights_free, sharp_fixed_mask, fixed_sharp_weights)
    # Errores 1σ de σ y ΔEQ₀ por la jacobiana (σ en log: dσ = σ·d log σ).
    sig_err = d0_err = None
    try:
        J = np.asarray(res.jac, dtype=float)
        dof = max(y.size - res.x.size, 1)
        scale = 1.0 if weights_data is not None else float(2.0 * res.cost / dof)
        cov = scale * np.linalg.pinv(J.T @ J)
        k = n_lin + 1
        if libre_sig:
            sig_err = float(sig_fit * np.sqrt(max(cov[k, k], 0.0)))
            k += 1
        if libre_d0:
            d0_err = float(np.sqrt(max(cov[k, k], 0.0)))
    except Exception:
        pass
    if libre_d0 and d0_fit <= 1e-6 * hi_grid:
        # En ΔEQ₀ = 0 la densidad solo depende de ΔEQ₀² (jacobiana nula): no
        # hay error lineal que dar; el ajuste equivale al Czjzek puro.
        d0_fit, d0_err = 0.0, None
    label = "Czjzek ext." if extended else "Czjzek"
    resumen = (f"σ={sig_fit:.4g}" + (f", ΔEQ₀={d0_fit:.4g}" if extended else "")
               + f", A={A_fit:.3g}")
    return BhfDistributionFit(
        bhf_centers=centers,
        weights=w,
        probability=normalize_probability(w, centers),
        fitted_curve=fitted,
        residuals=residuals,
        baseline=b0_fit,
        slope=sl_fit,
        alpha=0.0,
        rms=float(np.sqrt(np.mean(residuals ** 2))),
        success=bool(res.success),
        message=f"{label} {variable}: {resumen}; {res.message}",
        sharp_bhf_centers=sharp_bhf_centers,
        sharp_weights=sharp_weights_arr,
        fitted_dist_center=float(d0_fit) if extended else None,
        fitted_dist_sigma=float(sig_fit),
        shape=label,
        delta_slope=float(delta_slope),
        quad_slope=float(quad_slope),
        slope_ref=float(np.mean(centers)) if h_ref is None else float(h_ref),
        effective_dof=float(res.x.size),
        czjzek_sigma=float(sig_fit),
        czjzek_sigma_err=sig_err,
        czjzek_delta0=float(d0_fit) if extended else None,
        czjzek_delta0_err=d0_err,
        moment_cov=parametric_moment_cov(
            lambda x: (centers, model(x)[1]), res.x, res.jac, float(res.cost), y.size,
            weighted=weights_data is not None),
    )


#: Vecinos de la binomial de NORMOS-DIST (``DISTRI=3`` con ``CONC>0``): 13
#: subespectros con 0…12 vecinos y pesos C(12, k)·c^k·(1−c)^(12−k). Comprobado
#: con el binario de DIST (sonda 2026-10-09: CONC=50 % reproduce los 13 pesos).
BINOMIAL_NEIGHBORS_NORMOS = 12


def binomial_neighbor_weights(conc: float, n_neighbors: int = BINOMIAL_NEIGHBORS_NORMOS) -> np.ndarray:
    """Probabilidad de tener k = 0…n vecinos de soluto con concentración ``conc``.

    ``conc`` es la fracción (0–1) de posiciones vecinas ocupadas por el soluto;
    el resultado suma 1.
    """
    from scipy.special import gammaln
    n = max(1, int(n_neighbors))
    c = min(1.0 - 1e-12, max(1e-12, float(conc)))
    k = np.arange(n + 1, dtype=float)
    logw = (gammaln(n + 1) - gammaln(k + 1) - gammaln(n - k + 1)
            + k * np.log(c) + (n - k) * np.log1p(-c))
    w = np.exp(logw - np.max(logw))
    return w / float(np.sum(w))


#: Cotas físicas del valor inicial y del paso por vecino según la variable.
BINOMIAL_BOUNDS = {
    "bhf": ((0.0, 80.0), (-15.0, 15.0)),
    "quad": ((-10.0, 10.0), (-3.0, 3.0)),
    "delta": ((-5.0, 5.0), (-2.0, 2.0)),
}


def fit_binomial_hyperfine_distribution(
    v: np.ndarray,
    y: np.ndarray,
    *,
    variable: str = "bhf",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    conc: float = 0.1,
    n_neighbors: int = BINOMIAL_NEIGHBORS_NORMOS,
    start: float | None = None,
    step: float | None = None,
    fit_conc: bool = False,
    fit_start: bool = True,
    fit_step: bool = True,
    pmin: float = 0.0,
    pmax: float = 50.0,
    nbins: int | None = None,
    baseline: float | None = None,
    slope: float | None = None,
    fit_baseline: bool = True,
    fit_slope: bool = True,
    profile: str = "Lorentz",
    voigt_sigma: float = 0.05,
    sharp_components: list[dict[str, float]] | None = None,
    delta_slope: float = 0.0,
    quad_slope: float = 0.0,
    sigma: np.ndarray | None = None,
) -> BhfDistributionFit:
    """Distribución binomial de vecinos al estilo NORMOS-DIST (``DISTRI=3``).

    Modelo de aleación: cada átomo de Fe tiene ``n_neighbors`` posiciones
    vecinas y cada una está ocupada por el soluto con probabilidad ``conc``
    (fracción 0–1; ``CONC`` de NORMOS en %/100). La configuración con k
    vecinos de soluto pesa C(n, k)·c^k·(1−c)^(n−k) y su subespectro tiene la
    variable distribuida en ``start + k·step`` (``BHF``/``DTB`` de NORMOS para
    campo; ``QUA``/``DTQ`` o ``ISO``/``DTI`` para ΔEQ o δ).

    Ajusta la amplitud y, según los flags, ``conc``, ``start`` y ``step`` (en
    NORMOS ``CONC`` es dato y ``BHF``/``DTB`` pueden variar con ``DISTRI=3``).
    Las pendientes ``delta_slope``/``quad_slope`` se refieren a la
    configuración sin vecinos: δ_k = δ + delta_slope·k·step, que es el ``DTI``
    por subespectro de NORMOS dividido por el paso.

    ``pmin``/``pmax`` solo dan el valor inicial por defecto de ``start`` y
    ``step`` (malla repartida entre los n+1 subespectros); ``nbins`` se ignora.
    """
    from scipy.optimize import least_squares
    v = _finite_1d("v", v); y = _finite_1d("y", y)
    var = str(variable).lower()
    n = max(1, int(n_neighbors))
    k = np.arange(n + 1, dtype=float)
    (start_lo, start_hi), (step_lo, step_hi) = BINOMIAL_BOUNDS.get(var, BINOMIAL_BOUNDS["bhf"])
    start0 = float(pmin if start is None else start)
    step0 = float((float(pmax) - float(pmin)) / n if step is None else step)
    start0 = min(start_hi, max(start_lo, start0))
    step0 = min(step_hi, max(step_lo, step0))
    conc0 = min(1.0 - 1e-6, max(1e-6, float(conc)))

    def centers_for(st: float, sp: float) -> np.ndarray:
        return st + sp * k

    def _binomial_sample(p: dict) -> tuple[np.ndarray, np.ndarray]:
        return centers_for(p["start"], p["step"]), binomial_neighbor_weights(p["conc"], n)

    def kernel(st: float, sp: float) -> np.ndarray:
        # h_ref = start: δ y ΔEQ globales son los de la configuración sin vecinos.
        return build_hyperfine_distribution_kernel(
            v, centers_for(st, sp), variable=var, delta=delta, quad=quad, bhf=bhf,
            gamma=gamma, delta_slope=delta_slope, quad_slope=quad_slope, h_ref=st)

    with line_profile(profile, voigt_sigma):
        K_sharp, sharp_bhf_centers, fixed_sharp_abs, sharp_fixed_mask, fixed_sharp_weights = build_sharp_kernel_for_fit(
            v, sharp_components, default_delta=delta, default_quad=quad, default_gamma=gamma)
        n_sharp = K_sharp.shape[1] if K_sharp is not None else 0
        if baseline is None:
            baseline = float(np.percentile(y, 90))
        if slope is None:
            slope = 0.0
        amp0 = max(1e-6, float(np.percentile(y, 90) - np.min(y)))

        # Vector de parámetros: [baseline] [slope] amp [logit c] [start] [step] nítidos…
        names: list[str] = []
        x0: list[float] = []
        lo: list[float] = []
        hi: list[float] = []

        def add(name: str, val: float, lo_v: float, hi_v: float) -> None:
            names.append(name); x0.append(val); lo.append(lo_v); hi.append(hi_v)

        if fit_baseline:
            add("baseline", float(baseline), 0.0, np.inf)
        if fit_slope:
            add("slope", float(slope), -np.inf, np.inf)
        add("amp", amp0, 0.0, np.inf)
        if fit_conc:
            add("logit_c", float(np.log(conc0 / (1.0 - conc0))), -14.0, 14.0)
        if fit_start:
            add("start", start0, start_lo, start_hi)
        if fit_step:
            add("step", step0, step_lo, step_hi)
        n_head = len(names)
        x0 += [amp0 / max(n_sharp, 1)] * n_sharp
        lo += [0.0] * n_sharp
        hi += [np.inf] * n_sharp
        cache: dict = {}

        def unpack(x: np.ndarray) -> dict:
            p = {"baseline": float(baseline), "slope": float(slope),
                 "conc": conc0, "start": start0, "step": step0}
            for i, name in enumerate(names):
                if name == "logit_c":
                    p["conc"] = float(1.0 / (1.0 + np.exp(-x[i])))
                else:
                    p[name] = float(x[i])
            return p

        def model(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
            p = unpack(x)
            key = (p["start"], p["step"])
            if cache.get("key") != key:
                cache["key"] = key
                cache["K"] = kernel(p["start"], p["step"])
            w = p["amp"] * binomial_neighbor_weights(p["conc"], n)
            fitted = p["baseline"] + p["slope"] * v - cache["K"] @ w - fixed_sharp_abs
            if n_sharp:
                fitted = fitted - K_sharp @ np.maximum(x[n_head:n_head + n_sharp], 0.0)
            return fitted, w, p

        # Residuos ponderados con la σ de los datos, si la hay.
        pesos = data_weights(sigma, y.size)
        res = least_squares(
            lambda x: (model(x)[0] - y) * (pesos if pesos is not None else 1.0),
            np.array(x0, dtype=float), bounds=(np.array(lo), np.array(hi)), max_nfev=2000)
        fitted, w, p = model(res.x)
    sharp_weights_free = np.maximum(res.x[n_head:n_head + n_sharp], 0.0) if n_sharp else None
    sharp_weights_arr = merge_sharp_weights(sharp_weights_free, sharp_fixed_mask, fixed_sharp_weights)
    centers = centers_for(p["start"], p["step"])
    order = np.argsort(centers, kind="stable")
    centers, w = centers[order], w[order]
    total = float(np.sum(w))
    residuals = y - fitted
    return BhfDistributionFit(
        bhf_centers=centers,
        weights=w,
        # Distribución discreta (n+1 configuraciones): P_k suma 1, como la
        # tabla de áreas relativas de NORMOS, no una densidad por unidad.
        probability=(w / total) if total > 0 else np.zeros_like(w),
        fitted_curve=fitted,
        residuals=residuals,
        baseline=float(p["baseline"]),
        slope=float(p["slope"]),
        alpha=0.0,
        rms=float(np.sqrt(np.mean(residuals**2))),
        success=bool(res.success),
        message=(f"Binomial {var}: c={100 * p['conc']:.4g} %, n={n}, "
                 f"inicio={p['start']:.5g}, paso={p['step']:.5g}; {res.message}"),
        sharp_bhf_centers=sharp_bhf_centers,
        sharp_weights=sharp_weights_arr,
        fitted_dist_p=float(p["conc"]),
        shape="Binomial",
        delta_slope=float(delta_slope),
        quad_slope=float(quad_slope),
        slope_ref=float(p["start"]),
        binomial_start=float(p["start"]),
        binomial_step=float(p["step"]),
        binomial_n=n,
        effective_dof=float(res.x.size),
        moment_cov=parametric_moment_cov(
            lambda x: _binomial_sample(unpack(x)), res.x, res.jac, float(res.cost),
            y.size, weighted=pesos is not None),
    )


def fit_fixed_hyperfine_distribution(
    v: np.ndarray,
    y: np.ndarray,
    centers: np.ndarray,
    fixed_weights: np.ndarray,
    *,
    variable: str = "bhf",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    baseline: float | None = None,
    slope: float | None = None,
    fit_baseline: bool = True,
    fit_slope: bool = True,
    profile: str = "Lorentz",
    voigt_sigma: float = 0.05,
    sharp_components: list[dict[str, float]] | None = None,
    sigma: np.ndarray | None = None,
) -> BhfDistributionFit:
    """Ajusta amplitud de una distribución fija dada por centros y pesos.

    Opcionalmente suma componentes nítidos (sharp_components) con amplitud libre >= 0.
    Con ``sigma`` (σ de los datos) el problema lineal se pondera por canal.
    """
    v = _finite_1d("v", v); y = _finite_1d("y", y)
    centers = _finite_1d("centers", centers)
    fixed_weights = _finite_1d("fixed_weights", fixed_weights)
    if centers.size != fixed_weights.size:
        raise ValueError("centers y fixed_weights deben tener la misma longitud")
    # Perfil de línea explícito: sin este contexto el kernel heredaba el estado
    # global que hubiera dejado el último ajuste (p. ej. Voigt de un discreto).
    with line_profile(profile, voigt_sigma):
        K = build_hyperfine_distribution_kernel(v, centers, variable=variable, delta=delta, quad=quad, bhf=bhf, gamma=gamma)
        K_sharp, sharp_bhf_centers, fixed_sharp_abs, sharp_fixed_mask, fixed_sharp_weights = build_sharp_kernel_for_fit(
            v, sharp_components, default_delta=delta, default_quad=quad, default_gamma=gamma)
    n_sharp = K_sharp.shape[1] if K_sharp is not None else 0
    w0 = np.maximum(fixed_weights, 0.0)
    if not np.any(w0 > 0):
        raise ValueError("La distribución fija no contiene pesos positivos")
    area = np.trapezoid(w0, centers) if w0.size > 1 else w0[0]
    shape = w0 / max(float(area), 1e-12)
    profile_dist = K @ shape
    if baseline is None:
        baseline = float(np.percentile(y, 90))
    if slope is None:
        slope = 0.0
    # Columnas: [ones?, v?, -profile_dist, -sharp_0_libre, -sharp_1_libre, ...]
    # baseline/slope solo entran como columnas si son libres; fijos se restan
    # del término independiente. Los nítidos fijos se restan como absorción
    # conocida en el modelo.
    cols, lo, hi = [], [], []
    rhs = y + fixed_sharp_abs
    if fit_baseline:
        cols.append(np.ones_like(v)); lo.append(0.0); hi.append(np.inf)
    else:
        rhs = rhs - float(baseline)
    if fit_slope:
        cols.append(v); lo.append(-np.inf); hi.append(np.inf)
    else:
        rhs = rhs - float(slope) * v
    n_lin = len(cols)
    cols.append(-profile_dist); lo.append(0.0); hi.append(np.inf)
    if K_sharp is not None:
        for j in range(n_sharp):
            cols.append(-K_sharp[:, j])
            lo.append(0.0)
            hi.append(np.inf)
    X = np.column_stack(cols)
    pesos = data_weights(sigma, y.size)
    if pesos is not None:
        X, rhs = X * pesos[:, None], rhs * pesos
    result = solve_bounded_lsq(X, rhs, lo, hi)
    i = 0
    if fit_baseline:
        b0 = result.x[0]; i = 1
    else:
        b0 = float(baseline)
    if fit_slope:
        sl = result.x[i]
    else:
        sl = float(slope)
    amp = result.x[n_lin]
    sharp_weights_free = np.maximum(result.x[n_lin + 1:n_lin + 1 + n_sharp], 0.0) if n_sharp else None
    sharp_weights_arr = merge_sharp_weights(sharp_weights_free, sharp_fixed_mask, fixed_sharp_weights)
    weights = float(amp) * shape
    fitted = float(b0) + float(sl) * v - K @ weights - fixed_sharp_abs
    if K_sharp is not None and sharp_weights_free is not None:
        fitted = fitted - K_sharp @ sharp_weights_free
    residuals = y - fitted
    return BhfDistributionFit(
        bhf_centers=centers,
        weights=weights,
        probability=normalize_probability(weights, centers),
        fitted_curve=fitted,
        residuals=residuals,
        baseline=float(b0),
        slope=float(sl),
        alpha=0.0,
        rms=float(np.sqrt(np.mean(residuals**2))),
        success=bool(result.success),
        message="Fixed distribution",
        sharp_bhf_centers=sharp_bhf_centers,
        sharp_weights=sharp_weights_arr,
        shape="Fija",
        effective_dof=float(result.x.size),
    )


def fit_bhf_distribution(
    v: np.ndarray,
    y: np.ndarray,
    *,
    delta: float = 0.0,
    quad: float = 0.0,
    gamma: float = 0.18,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    bmin: float = 0.0,
    bmax: float = 50.0,
    nbins: int = 50,
    alpha: float = 1e-2,
    fit_baseline: bool = True,
    fit_slope: bool = True,
    baseline: float | None = None,
    slope: float | None = None,
    baseline_bounds: tuple[float, float] = (0.0, np.inf),
    slope_bounds: tuple[float, float] = (-np.inf, np.inf),
    sharp_components: list[dict[str, float]] | None = None,
    sigma: np.ndarray | None = None,
) -> BhfDistributionFit:
    """Compatibilidad: distribución Hesse-Rübartsch de BHF."""
    return fit_hyperfine_distribution(
        v, y, variable="bhf", delta=delta, quad=quad, gamma=gamma,
        gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel, int1=int1,
        int2_rel=int2_rel, int3_rel=int3_rel, pmin=bmin, pmax=bmax,
        nbins=nbins, alpha=alpha, fit_baseline=fit_baseline,
        fit_slope=fit_slope, baseline=baseline, slope=slope,
        baseline_bounds=baseline_bounds, slope_bounds=slope_bounds,
        sharp_components=sharp_components, sigma=sigma,
    )


def fit_bhf_distribution_nnls_fixed_background(
    v: np.ndarray,
    y: np.ndarray,
    *,
    baseline: float,
    slope: float = 0.0,
    delta: float = 0.0,
    quad: float = 0.0,
    gamma: float = 0.18,
    bmin: float = 0.0,
    bmax: float = 50.0,
    nbins: int = 50,
    alpha: float = 1e-2,
) -> BhfDistributionFit:
    """Variante con fondo fijo resuelta por NNLS puro."""
    v = _finite_1d("v", v)
    y = _finite_1d("y", y)
    centers = bhf_grid(bmin, bmax, nbins)
    K = build_bhf_kernel(v, centers, delta=delta, quad=quad, gamma=gamma)
    L = second_difference_matrix(centers.size)
    rhs = float(baseline) + float(slope) * v - y
    A = np.vstack([K, np.sqrt(float(alpha)) * L])
    b = np.concatenate([rhs, np.zeros(L.shape[0], dtype=float)])
    weights, _rnorm = nnls(A, b)
    fitted = float(baseline) + float(slope) * v - K @ weights
    residuals = y - fitted
    return BhfDistributionFit(
        bhf_centers=centers,
        weights=weights,
        probability=normalize_probability(weights, centers),
        fitted_curve=fitted,
        residuals=residuals,
        baseline=float(baseline),
        slope=float(slope),
        alpha=float(alpha),
        rms=float(np.sqrt(np.mean(residuals**2))),
        success=True,
        message="NNLS terminado",
        shape="Histograma",
    )


def scan_alpha(
    v: np.ndarray,
    y: np.ndarray,
    alphas: np.ndarray | list[float],
    **kwargs: Any,
) -> list[BhfDistributionFit]:
    """Ejecuta el ajuste para varios alpha, util para L-curve/inspeccion visual."""
    return [fit_bhf_distribution(v, y, alpha=float(a), **kwargs) for a in alphas]
