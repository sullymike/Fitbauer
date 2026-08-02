"""Nivel 1 de la revisión del fuente de NORMOS: forma de línea e intensidades.

Dos hallazgos del barrido (2026-08-02):

* **AKS** — SITE multiplica cada lorentziana por ``1 − AKS·(v−v₀)/Γ``
  (``LORLIN``, ``siteauxl.for:638``). Fitbauer no tenía equivalente. La sonda
  sobre el binario demo 27.01.1994 confirmó que la fórmula del fuente de 1990
  describe al ejecutable (rms 1.2·10⁻⁴, el suelo de precisión de su ``.PLT``).
* **Área vs profundidad** — D13/D23 de SITE son razones de ÁREA (que es lo que
  son físicamente las probabilidades de transición 3:2:1); ``int1``/``int2`` de
  Fitbauer eran razones de PROFUNDIDAD. Solo se separan si las anchuras
  relativas no son 1.
"""
from __future__ import annotations

import numpy as np
import pytest

from core import physics as phys
from core.physics import (
    doublet_absorption,
    intensity_convention,
    line_asymmetry,
    line_profile,
    lorentzian,
    sextet_absorption,
)

V = np.linspace(-12.0, 12.0, 2401)


def _area(y: np.ndarray) -> float:
    return float(np.trapezoid(y, V))


# ── AKS: asimetría de línea ──────────────────────────────────────────────────

def test_asimetria_neutra_por_defecto():
    assert phys.LINE_ASYM == 0.0
    with line_asymmetry(0.0):
        np.testing.assert_allclose(
            lorentzian(V, 0.3, 0.25), 0.0125 ** 0 * lorentzian(V, 0.3, 0.25))


def test_asimetria_formula_de_site():
    """El perfil es exactamente L(v)·(1 − a·(v−v₀)/Γ)."""
    centro, gamma, a = 0.3, 0.25, 0.4
    base = lorentzian(V, centro, gamma)
    with line_asymmetry(a):
        y = lorentzian(V, centro, gamma)
    esperado = base * (1.0 - a * (V - centro) / gamma)
    np.testing.assert_allclose(y, esperado, rtol=0, atol=1e-15)


def test_asimetria_rompe_la_simetria_y_el_signo_refleja():
    centro, gamma = 0.0, 0.25
    with line_asymmetry(0.3):
        y_pos = lorentzian(V, centro, gamma)
    with line_asymmetry(-0.3):
        y_neg = lorentzian(V, centro, gamma)
    # No es simétrica...
    assert np.max(np.abs(y_pos - y_pos[::-1])) > 1e-3
    # ...y cambiar el signo de AKS es reflejar la línea (como en el binario).
    np.testing.assert_allclose(y_pos, y_neg[::-1], atol=1e-12)


def test_asimetria_conserva_el_area():
    """El término impar integra a cero en un rango simétrico: el área no cambia."""
    base = _area(lorentzian(V, 0.0, 0.25))
    with line_asymmetry(0.5):
        con_asym = _area(lorentzian(V, 0.0, 0.25))
    assert con_asym == pytest.approx(base, rel=1e-9)


def test_asimetria_se_restaura_ante_excepcion():
    with pytest.raises(RuntimeError):
        with line_asymmetry(0.5):
            raise RuntimeError("boom")
    assert phys.LINE_ASYM == 0.0


def test_asimetria_tambien_en_voigt():
    """Divergencia deliberada con SITE: allí GAULIN ignora AKS, aquí no."""
    with line_profile("Voigt", 0.08):
        base = lorentzian(V, 0.0, 0.25)
        with line_asymmetry(0.3):
            y = lorentzian(V, 0.0, 0.25)
    assert np.max(np.abs(y - base)) > 1e-3
    np.testing.assert_allclose(y, base * (1.0 - 0.3 * V / 0.25), atol=1e-12)


def test_asimetria_llega_al_sexteto():
    kw = dict(delta=0.0, quad=0.0, bhf=33.0, gamma1=0.25, gamma2=1.0,
              gamma3=1.0, depth=0.05, int1=3.0, int2=2.0, int3=1.0)
    base = sextet_absorption(V, **kw)
    with line_asymmetry(0.3):
        y = sextet_absorption(V, **kw)
    assert np.max(np.abs(y - base)) > 1e-3
    # Con asimetría el sexteto deja de ser simétrico respecto a δ.
    assert np.max(np.abs(y - y[::-1])) > 1e-3


# ── Convenio de intensidades: área vs profundidad ────────────────────────────

def test_convenio_por_defecto_es_profundidad():
    assert phys.INTENSITY_CONVENTION == "depth"


def test_convenios_coinciden_con_anchuras_iguales():
    kw = dict(delta=0.0, quad=0.0, bhf=33.0, gamma1=0.25, gamma2=1.0,
              gamma3=1.0, depth=0.05, int1=3.0, int2=2.0, int3=1.0)
    y_depth = sextet_absorption(V, **kw)
    with intensity_convention("area"):
        y_area = sextet_absorption(V, **kw)
    np.testing.assert_allclose(y_area, y_depth, atol=1e-15)


@pytest.mark.parametrize("g2,g3", [(1.3, 1.0), (0.7, 1.4), (1.0, 2.0)])
def test_convenio_area_da_razones_de_area_exactas(g2, g3):
    """Con "area", int1/int2 SON A13/A23 aunque las anchuras difieran.

    El área de un perfil normalizado en pico es (π/2)·Γ·peso, así que la
    comprobación se hace sobre los pesos y anchuras exactos y no sobre una
    integral numérica (las colas lorentzianas truncadas sesgarían el área
    justo en función de la anchura, que es lo que se quiere medir).
    """
    int1, int2, int3 = 3.0, 2.0, 1.0
    pesos = np.array([int1, int2, int3, int3, int2, int1], dtype=float)
    gammas = 0.25 * np.array([1.0, g2, g3, g3, g2, 1.0], dtype=float)
    w = phys._area_to_depth_weights(pesos, gammas)
    areas = w * gammas
    assert areas[0] / areas[2] == pytest.approx(int1, rel=1e-12)
    assert areas[1] / areas[2] == pytest.approx(int2, rel=1e-12)


def test_area_to_depth_es_identidad_con_anchuras_iguales():
    pesos = np.array([3.0, 2.0, 1.0, 1.0, 2.0, 3.0])
    gammas = np.full(6, 0.25)
    np.testing.assert_allclose(
        phys._area_to_depth_weights(pesos, gammas), pesos, atol=0)


@pytest.mark.parametrize("g2,g3", [(1.3, 1.0), (0.7, 1.4)])
def test_convenio_depth_da_razones_de_profundidad(g2, g3):
    """Y el histórico sigue dando razones de PROFUNDIDAD (no se ha cambiado)."""
    int1, int2, gamma1 = 3.0, 2.0, 0.20
    # BHF alto y Γ estrecha: las líneas quedan tan separadas que el solape de
    # colas cae por debajo de la tolerancia.
    v = np.linspace(-20.0, 20.0, 20001)
    y = sextet_absorption(v, delta=0.0, quad=0.0, bhf=55.0, gamma1=gamma1,
                          gamma2=g2, gamma3=g3, depth=1.0,
                          int1=int1, int2=int2, int3=1.0)
    from core.physics import sextet_line_positions
    pos = sextet_line_positions(0.0, 0.0, 55.0)
    d16, d25, d34 = (float(np.interp(p, v, y)) for p in pos[:3])
    # Tolerancia dominada por el solape de colas (la línea 3,4 tiene vecinas a
    # ambos lados y la 1,6 solo a uno); el convenio "area" se desviaría un
    # 1/g2 ≈ 23-43 %, muy por encima de este margen.
    assert d16 / d34 == pytest.approx(int1, rel=1.5e-2)
    assert d25 / d34 == pytest.approx(int2, rel=1.5e-2)
    with intensity_convention("area"):
        y_a = sextet_absorption(v, delta=0.0, quad=0.0, bhf=55.0, gamma1=gamma1,
                                gamma2=g2, gamma3=g3, depth=1.0,
                                int1=int1, int2=int2, int3=1.0)
    d25_a = float(np.interp(pos[1], v, y_a))
    d34_a = float(np.interp(pos[2], v, y_a))
    assert d25_a / d34_a == pytest.approx(int2 * g3 / g2, rel=1.5e-2)


def test_convenio_area_en_doblete():
    """Las dos líneas del doblete quedan en razón de ÁREA int2."""
    int1, int2, gamma1, g2 = 1.0, 1.5, 0.25, 1.6
    v = np.linspace(-60.0, 60.0, 240001)
    kw = dict(delta=0.0, quad=1.2, gamma1=gamma1, gamma2=g2, depth=1.0,
              int1=int1, int2=int2)
    with intensity_convention("area"):
        total = float(np.trapezoid(doublet_absorption(v, **kw), v))
        solo1 = float(np.trapezoid(doublet_absorption(v, **dict(kw, int2=0.0)), v))
    # Tolerancia dominada por la cola lorentziana fuera de ±60 mm/s (~Γ/πX).
    assert (total - solo1) / solo1 == pytest.approx(int2, rel=5e-3)


def test_convenio_desconocido_lanza():
    with pytest.raises(ValueError, match="convenio de intensidad desconocido"):
        with intensity_convention("peso"):
            pass
    assert phys.INTENSITY_CONVENTION == "depth"


def test_convenio_llega_al_kernel_de_distribucion():
    import mossbauer_distribution as md

    kw = dict(delta=0.0, quad=0.0, bhf=33.0, gamma=0.25,
              gamma2_rel=1.4, gamma3_rel=0.8)
    y_depth = md.sextet_absorption(V, **kw)
    with intensity_convention("area"):
        y_area = md.sextet_absorption(V, **kw)
    assert np.max(np.abs(y_area - y_depth)) > 1e-3


# ── Cableado con el motor de ajuste ──────────────────────────────────────────

def test_model_from_values_usa_line_asym_y_lo_restaura():
    from core.fit_engine import Component, model_from_values

    comps = [Component(idx=1, enabled=True, kind="Singlete")]
    vals = {"baseline": 1.0, "slope": 0.0, "s1_delta": 0.0, "s1_quad": 0.0,
            "s1_bhf": 33.0, "s1_gamma1": 0.25, "s1_gamma2": 1.0,
            "s1_gamma3": 1.0, "s1_depth": 0.1, "s1_int1": 1.0,
            "s1_int2": 1.0, "s1_int3": 1.0}
    base = model_from_values(V, vals, comps)
    con = model_from_values(V, dict(vals, line_asym=0.4), comps)
    assert np.max(np.abs(con - base)) > 1e-3
    # No debe quedar estado global contaminado.
    assert phys.LINE_ASYM == 0.0
