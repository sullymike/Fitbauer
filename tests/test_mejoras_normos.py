"""Tests de las mejoras derivadas del banco de validación NORMOS.

Cuatro extensiones de modelo, todas opt-in (el comportamiento por defecto no
cambia): Hamiltoniano completo con intensidades (η, φ), integral de
transmisión, curvatura de base e integración del modelo sobre el canal.
"""
import numpy as np
import pytest

from core.constants import LINE_POS_33T
from core.fit_engine import Component, model_from_values
from core.hamiltonian import full_hamiltonian_lines
from core.params import relevant_params
from core.physics import sextet_absorption, total_model


V = np.linspace(-10.0, 10.0, 254)


def _vals(**over):
    base = {
        "baseline": 1.0, "slope": 0.0,
        "s1_delta": 0.0, "s1_quad": 0.0, "s1_bhf": 33.0,
        "s1_gamma1": 0.30, "s1_gamma2": 1.0, "s1_gamma3": 1.0,
        "s1_depth": 0.02, "s1_int1": 3.0, "s1_int2": 2.0, "s1_int3": 1.0,
    }
    base.update(over)
    return base


def _comp(**over):
    kw = dict(idx=1, enabled=True, kind="Sextete", intensity_mode="free",
              quad_treatment="1st_order")
    kw.update(over)
    return Component(**kw)


# ── Mejora 1: Hamiltoniano completo con intensidades ─────────────────────────

def test_hamiltoniano_limite_primer_orden():
    """θ=0, η=0, ΔEQ pequeño: posiciones 1er orden e intensidades 3:2:1."""
    pos, inten, _ = full_hamiltonian_lines(33.0, 0.1, 0.2, theta=0.0)
    vivos = inten > 1e-9
    assert vivos.sum() == 6              # las ΔmI=±2 tienen intensidad nula
    esperado = LINE_POS_33T + 0.1 + 0.2 * np.array([0.5, -0.5, -0.5, -0.5, -0.5, 0.5])
    assert np.allclose(np.sort(pos[vivos]), np.sort(esperado), atol=1e-9)
    razon = inten[vivos] / inten[vivos].min()
    assert np.allclose(np.sort(razon), [1, 1, 2, 2, 3, 3], atol=1e-9)


def test_hamiltoniano_regla_de_suma():
    """La intensidad total se conserva bajo mezcla (regla de suma)."""
    _, i0, _ = full_hamiltonian_lines(33.0, 0.0, 0.0)
    for th, eta, ph in ((0.5, 0.0, 0.0), (1.2, 0.7, 0.8), (1.57, 1.0, 1.57)):
        _, ik, _ = full_hamiltonian_lines(5.0, 0.0, 2.0, eta=eta, theta=th, phi=ph)
        assert ik.sum() == pytest.approx(i0.sum(), rel=1e-9)


def test_hamiltoniano_invariancia_rotacional():
    """Configuraciones físicamente equivalentes por rotación coinciden.

    (η=1, B∥y) ≡ (η=1, B∥z' con ΔEQ de signo opuesto). NORMOS-SITE demo
    NO cumple esto a η grande (omite la interferencia del fundamental):
    el banco documenta que esta implementación es la exacta.
    """
    pA, iA, _ = full_hamiltonian_lines(6.19, 0.0, 2.0, eta=1.0,
                                       theta=np.pi / 2, phi=np.pi / 2)
    pB, iB, _ = full_hamiltonian_lines(6.19, 0.0, -2.0, eta=1.0,
                                       theta=0.0, phi=0.0)
    assert np.allclose(pA, pB, atol=1e-9)
    assert np.allclose(iA, iB, atol=1e-9)


def test_sextete_hamiltonian_theta0_equivale_1er_orden():
    a1 = sextet_absorption(V, 0.1, 0.2, 33.0, 0.3, 1.0, 1.0, 0.02, 3.0, 2.0, 1.0)
    a2 = sextet_absorption(V, 0.1, 0.2, 33.0, 0.3, 1.0, 1.0, 0.02, 3.0, 2.0, 1.0,
                           treatment="hamiltonian", beta=0.0)
    assert np.allclose(a1, a2, atol=1e-8)


def test_relevant_params_hamiltonian():
    r = relevant_params("Sextete", "free", "hamiltonian")
    assert {"eta", "phi", "beta"} <= r
    r0 = relevant_params("Sextete", "free", "1st_order")
    assert not ({"eta", "phi", "beta"} & r0)


# ── Mejora 2: integral de transmisión ────────────────────────────────────────

def test_transmision_limite_fino():
    """Con τ≪1 y fuente estrecha, la integral de transmisión ≈ modelo fino."""
    comps = [("Singlete", np.array([0.3, 0, 0, 0.25, 1, 1, 0.001, 3, 1, 1]))]
    fino = total_model(V, 1.0, 0.0, comps)
    trans = total_model(V, 1.0, 0.0, comps, transmission_src=0.0)
    assert np.allclose(fino, trans, atol=1e-5)


def test_transmision_saturacion_y_convolucion():
    """Con espesor la línea satura (pico < τ) y la fuente ensancha (FWHM)."""
    comps = [("Singlete", np.array([0.0, 0, 0, 0.25, 1, 1, 1.0, 3, 1, 1]))]
    t = total_model(V, 1.0, 0.0, comps, transmission_src=0.097)
    prof = 1.0 - t
    # saturación: pico < 1−exp(−τ_pico) (la convolución lo rebaja aún más),
    # pero sigue siendo una absorción profunda, nada que ver con τ=3 lineal.
    assert prof.max() < 1.0 - np.exp(-3.0)
    assert prof.max() > 0.75
    half = prof.max() / 2
    anchura = V[prof > half][-1] - V[prof > half][0]
    assert anchura > 0.30                     # ensanchada vs Γ=0.25 del absorbente


# ── Mejoras 3 y 4: curvatura e integración por canal ─────────────────────────

def test_curv_y_channel_sub_identidad_por_defecto():
    vals = _vals()
    comps = [_comp()]
    m0 = model_from_values(V, vals, comps)
    m1 = model_from_values(V, dict(vals, curv=0.0), comps, channel_sub=1)
    assert np.allclose(m0, m1, atol=0)


def test_curvatura():
    vals = _vals(curv=0.001)
    m = model_from_values(V, vals, [_comp()])
    m0 = model_from_values(V, _vals(), [_comp()])
    assert np.allclose(m - m0, 0.001 * V ** 2, atol=1e-12)


def test_channel_sub_reduce_sesgo_de_anchura():
    """Datos integrados por canal ancho: canal_sub>1 modela la media del bin."""
    v_c = np.linspace(-10, 10, 64)           # canal 0.317 ≈ 1.3·Γ
    dv = v_c[1] - v_c[0]
    fine = np.linspace(-10 - dv / 2, 10 + dv / 2, 64 * 40)
    vals = _vals(s1_gamma1=0.25)
    y_fine = model_from_values(fine, vals, [_comp()])
    y_binned = np.array([y_fine[np.abs(fine - c) <= dv / 2].mean() for c in v_c])
    y_center = model_from_values(v_c, vals, [_comp()])
    y_sub = model_from_values(v_c, vals, [_comp()], channel_sub=6)
    assert np.max(np.abs(y_binned - y_sub)) < 0.2 * np.max(np.abs(y_binned - y_center))
