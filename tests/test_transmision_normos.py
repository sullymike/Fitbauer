"""Nivel 6 de la revisión del fuente de NORMOS: integral de transmisión.

Dos hallazgos (2026-08-02), ambos en la rama ``IFTRAN`` de ``sitecalf.for``:

* **FSO** — la transmisión de SITE es ``1 − FSO + FSO·(L_fuente ⊗ e^{−τ} + WING)``:
  solo una fracción FSO de los fotones que llegan es resonante, así que la
  absorción satura en FSO y no en 1. Fitbauer no tenía equivalente. Verificado
  contra el binario demo: con FSO=0.7 la base es 1−0.7+0.7·0.996811 = 0.997768
  y el mínimo 1−0.7+0.7·0.239481 = 0.467637, ambos exactos.
* **Kernel de la fuente** — se truncaba a ±20 FWHM y se RENORMALIZABA. La
  Lorentziana tiene colas ~1/v²: a ±20 FWHM falta un 1.6 % del peso, y
  renormalizar lo redistribuye al centro falseando la absorción. El ``WING`` de
  NORMOS hace lo correcto: deja el déficit fuera (allí no hay absorción).
"""
from __future__ import annotations

import numpy as np
import pytest

from core.physics import SOURCE_KERNEL_HALF_WIDTHS, _source_kernel, total_model

V = np.linspace(-4.0, 4.0, 256)


def _singlete(depth: float = 2.5, gamma: float = 0.25, delta: float = 0.0):
    return [("Singlete", np.array([delta, 0.0, 33.0, gamma, 1.0, 1.0,
                                   depth, 1.0, 1.0, 1.0]))]


# ── FSO: fracción resonante de la fuente ─────────────────────────────────────

def test_fso_por_defecto_es_neutro():
    comps = _singlete()
    sin_arg = total_model(V, 1.0, 0.0, comps, transmission_src=0.097)
    con_uno = total_model(V, 1.0, 0.0, comps, transmission_src=0.097,
                          transmission_frac=1.0)
    np.testing.assert_allclose(con_uno, sin_arg, atol=0)


@pytest.mark.parametrize("frac", [0.4, 0.7, 0.95])
def test_fso_escala_la_absorcion_como_en_site(frac):
    """T(f) = 1 − f + f·T(1), la fórmula literal de ``sitecalf.for``."""
    comps = _singlete()
    t1 = total_model(V, 1.0, 0.0, comps, transmission_src=0.097,
                     transmission_frac=1.0)
    tf = total_model(V, 1.0, 0.0, comps, transmission_src=0.097,
                     transmission_frac=frac)
    np.testing.assert_allclose(tf, 1.0 - frac + frac * t1, atol=1e-12)


def test_fso_acota_la_absorcion_maxima():
    """Con absorbente MUY grueso la transmisión satura en 1−f, no en 0."""
    comps = _singlete(depth=200.0)
    for frac in (0.3, 0.6):
        t = total_model(V, 1.0, 0.0, comps, transmission_src=0.0,
                        transmission_frac=frac)
        assert t.min() == pytest.approx(1.0 - frac, abs=5e-3)


def test_fso_no_es_degenerado_con_la_profundidad_en_absorbente_grueso():
    """Si lo fuera, bastaría reescalar τ para imitar cualquier FSO."""
    comps_ref = _singlete(depth=20.0)
    ref = total_model(V, 1.0, 0.0, comps_ref, transmission_src=0.097,
                      transmission_frac=0.5)
    # Ninguna profundidad reproduce esa curva con FSO=1.
    mejor = min(
        float(np.max(np.abs(
            total_model(V, 1.0, 0.0, _singlete(depth=d), transmission_src=0.097,
                        transmission_frac=1.0) - ref)))
        for d in np.linspace(0.05, 200.0, 400))
    assert mejor > 0.02


def test_fso_si_es_degenerado_en_el_limite_fino():
    """Y en absorbente fino sí: es el límite conocido (serie N3 del banco)."""
    ref = total_model(V, 1.0, 0.0, _singlete(depth=0.02), transmission_src=0.097,
                      transmission_frac=0.5)
    mejor = min(
        float(np.max(np.abs(
            total_model(V, 1.0, 0.0, _singlete(depth=d), transmission_src=0.097,
                        transmission_frac=1.0) - ref)))
        for d in np.linspace(0.001, 0.05, 400))
    assert mejor < 1e-4


# ── Kernel de la fuente ──────────────────────────────────────────────────────

def test_kernel_no_se_renormaliza():
    """El déficit de peso es la cola, y equivale al WING de NORMOS."""
    ker = _source_kernel(V, 0.097)
    assert ker is not None
    total = float(ker.sum())
    assert total < 1.0                    # falta la cola...
    assert total > 0.99                   # ...pero poca, con ±200 FWHM


def test_kernel_es_mas_ancho_que_el_historico():
    assert SOURCE_KERNEL_HALF_WIDTHS >= 200.0
    dv = float(np.median(np.diff(V)))
    ker = _source_kernel(V, 0.097)
    half_historico = int(np.ceil(20.0 * 0.097 / dv))
    assert ker.size > 2 * half_historico


def test_kernel_acotado_por_el_tamano_de_la_malla():
    """Una fuente muy ancha no debe generar un kernel desproporcionado."""
    ker = _source_kernel(V, 2.0)
    assert ker is not None
    assert ker.size <= 8 * V.size + 2


def test_kernel_pesos_son_la_integral_exacta_por_canal():
    dv = float(np.median(np.diff(V)))
    fwhm = 0.097
    ker = _source_kernel(V, fwhm)
    centro = ker.size // 2
    # Peso central = integral de la Lorentziana sobre un canal centrado en 0.
    esperado = (2.0 / np.pi) * np.arctan(0.5 * dv / (fwhm / 2.0))
    assert float(ker[centro]) == pytest.approx(esperado, rel=1e-12)


def test_kernel_none_si_la_fuente_es_despreciable():
    assert _source_kernel(V, 0.0) is None
    assert _source_kernel(V[:3], 0.097) is None


# ── Cableado con el motor ────────────────────────────────────────────────────

def test_src_frac_llega_desde_los_valores_del_modelo():
    from core.fit_engine import Component, model_from_values

    comps = [Component(idx=1, enabled=True, kind="Singlete")]
    vals = {"baseline": 1.0, "slope": 0.0, "s1_delta": 0.0, "s1_quad": 0.0,
            "s1_bhf": 33.0, "s1_gamma1": 0.25, "s1_gamma2": 1.0,
            "s1_gamma3": 1.0, "s1_depth": 20.0, "s1_int1": 1.0,
            "s1_int2": 1.0, "s1_int3": 1.0, "src_fwhm": 0.097}
    base = model_from_values(V, dict(vals, src_frac=1.0), comps,
                             absorber_model="transmission")
    medio = model_from_values(V, dict(vals, src_frac=0.5), comps,
                              absorber_model="transmission")
    np.testing.assert_allclose(medio, 1.0 - 0.5 + 0.5 * base, atol=1e-12)


def test_src_frac_solo_participa_en_modo_transmision():
    """Igual que src_fwhm: en otros modos no debe quedar un parámetro muerto."""
    from core.fit_engine import Component, FitState, _fit_discrete_impl

    n = 64
    v = np.linspace(-4.0, 4.0, n)
    y = np.ones(n)
    state = FitState(
        velocity=v, y_data=y, sigma_data=np.full(n, 0.01),
        values={"baseline": 1.0, "slope": 0.0, "src_frac": 1.0,
                "s1_delta": 0.0, "s1_quad": 0.0, "s1_bhf": 33.0,
                "s1_gamma1": 0.25, "s1_gamma2": 1.0, "s1_gamma3": 1.0,
                "s1_depth": 0.01, "s1_int1": 1.0, "s1_int2": 1.0,
                "s1_int3": 1.0},
        fixed={"slope": True, "s1_quad": True, "s1_bhf": True,
               "s1_gamma2": True, "s1_gamma3": True, "s1_int1": True,
               "s1_int2": True, "s1_int3": True},
        bounds={}, components=[Component(idx=1, enabled=True, kind="Singlete")],
        absorber_model="thin", multistart_n=0)
    res = _fit_discrete_impl(state)
    assert "src_frac" not in res.free_keys
