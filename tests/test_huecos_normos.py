"""Los dos huecos de cobertura frente a NORMOS-DIST (2026-08-02).

1. ``METHOD=8`` — distribución de desplazamiento isomérico P(δ). El motor ya
   sabía hacerlo (``build_kernel`` acepta ``variable="delta"``); lo que faltaba
   era exponerlo. Aquí se fija que funciona de punta a punta.
2. ``METHOD=2`` — modelo de Brand: las anchuras de línea no son libres, salen
   de DISPERSIONES físicas (de campo, de isomérico y de cuadrupolo). Nuevo
   ``width_model="dispersion"``.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.physics import dispersion_line_widths, sextet_absorption
from mossbauer_distribution import (
    fit_hyperfine_distribution,
    singlet_absorption,
)

V = np.linspace(-20.0, 20.0, 8001)


# ── 1. P(δ): distribución de desplazamiento isomérico ────────────────────────

def _espectro_p_delta(seed: int = 0):
    """Dos poblaciones de SINGLETES con δ distinto (el caso de METHOD=8)."""
    v = np.linspace(-3.0, 3.0, 512)
    d = np.linspace(-1.0, 1.5, 300)
    p = (np.exp(-0.5 * ((d - 0.15) / 0.10) ** 2)
         + 0.6 * np.exp(-0.5 * ((d - 0.85) / 0.14) ** 2))
    p /= p.sum()
    y = 1.0 - sum(pi * singlet_absorption(v, delta=di, gamma=0.26) * 0.06
                  for di, pi in zip(d, p))
    y = y + np.random.default_rng(seed).normal(0.0, 2e-4, v.size)
    return v, y, d, p


def test_p_delta_recupera_los_momentos():
    v, y, d, p = _espectro_p_delta()
    r = fit_hyperfine_distribution(
        v, y, variable="delta", bhf=0.0, quad=0.0, gamma=0.26,
        pmin=-1.0, pmax=1.5, nbins=60, alpha=0.02)
    centros = np.asarray(r.bhf_centers)
    w = np.asarray(r.weights)
    media = float(np.sum(w * centros) / np.sum(w))
    sigma = float(np.sqrt(np.sum(w * (centros - media) ** 2) / np.sum(w)))
    media_v = float(np.sum(p * d))
    sigma_v = float(np.sqrt(np.sum(p * (d - media_v) ** 2)))
    assert media == pytest.approx(media_v, abs=0.02)
    assert sigma == pytest.approx(sigma_v, abs=0.02)


def test_p_delta_separa_las_dos_poblaciones():
    v, y, _d, _p = _espectro_p_delta()
    r = fit_hyperfine_distribution(
        v, y, variable="delta", bhf=0.0, quad=0.0, gamma=0.26,
        pmin=-1.0, pmax=1.5, nbins=60, alpha=0.02)
    centros = np.asarray(r.bhf_centers)
    w = np.asarray(r.weights)
    picos = centros[w > 0.3 * w.max()]
    assert picos.min() == pytest.approx(0.15, abs=0.12)
    assert picos.max() == pytest.approx(0.85, abs=0.15)


def test_p_delta_admite_kernel_de_sexteto():
    """NORMOS solo distribuye singletes en METHOD=8; aquí el kernel es libre."""
    v = np.linspace(-11.0, 11.0, 512)
    d = np.linspace(-0.2, 0.6, 120)
    p = np.exp(-0.5 * ((d - 0.2) / 0.08) ** 2)
    p /= p.sum()
    from mossbauer_distribution import sextet_absorption as sx
    y = 1.0 - sum(pi * sx(v, delta=di, quad=0.0, bhf=33.0, gamma=0.28) * 0.05
                  for di, pi in zip(d, p))
    r = fit_hyperfine_distribution(
        v, y, variable="delta", bhf=33.0, quad=0.0, gamma=0.28,
        pmin=-0.2, pmax=0.6, nbins=40, alpha=0.02)
    centros = np.asarray(r.bhf_centers)
    w = np.asarray(r.weights)
    assert float(np.sum(w * centros) / np.sum(w)) == pytest.approx(0.2, abs=0.03)


# ── 2. Anchuras por dispersión (modelo de Brand) ─────────────────────────────

def test_sin_dispersion_es_la_anchura_base():
    np.testing.assert_allclose(dispersion_line_widths(0.25), np.full(6, 0.25))


def test_la_dispersion_de_campo_ensancha_mas_las_lineas_externas():
    """Es la firma del desorden químico: 1,6 mucho más anchas que 3,4."""
    g = dispersion_line_widths(0.25, sigma_bhf=1.0)
    assert g[0] == pytest.approx(g[5])          # simétrico
    assert g[1] == pytest.approx(g[4])
    assert g[2] == pytest.approx(g[3])
    assert g[0] > g[1] > g[2]                   # externas > medias > internas
    assert g[0] / g[2] > 1.5


def test_la_dispersion_de_isomerico_ensancha_por_igual():
    g = dispersion_line_widths(0.25, sigma_delta=0.05)
    np.testing.assert_allclose(g, np.full(6, g[0]), rtol=1e-12)
    assert g[0] > 0.25


def test_la_dispersion_de_cuadrupolo_ensancha_por_igual_en_57fe():
    """El patrón cuadrupolar es ±½ en todas, así que |∂v/∂ΔEQ| es constante."""
    g = dispersion_line_widths(0.25, sigma_quad=0.1)
    np.testing.assert_allclose(g, np.full(6, g[0]), rtol=1e-12)


def test_las_dispersiones_suman_en_cuadratura():
    solo_b = dispersion_line_widths(0.25, sigma_bhf=1.0)
    solo_d = dispersion_line_widths(0.25, sigma_delta=0.05)
    juntas = dispersion_line_widths(0.25, sigma_bhf=1.0, sigma_delta=0.05)
    esperado = np.sqrt(solo_b ** 2 + solo_d ** 2 - 0.25 ** 2)
    np.testing.assert_allclose(juntas, esperado, rtol=1e-12)


def test_el_ensanchamiento_conserva_el_area():
    """Una dispersión reparte los mismos átomos; el área de cada línea no cambia."""
    base = float(np.trapezoid(
        sextet_absorption(V, 0.0, 0.0, 33.0, 0.25, 1.0, 1.0,
                          0.05, 3.0, 2.0, 1.0), V))
    for sigma_b in (0.5, 1.0, 2.0):
        area = float(np.trapezoid(
            sextet_absorption(V, 0.0, 0.0, 33.0, 0.25, 1.0, 1.0,
                              0.05, 3.0, 2.0, 1.0,
                              width_model="dispersion", sigma_bhf=sigma_b), V))
        assert area == pytest.approx(base, rel=0.01)


def test_width_model_libre_es_el_comportamiento_historico():
    a = sextet_absorption(V, 0.0, 0.0, 33.0, 0.25, 1.2, 0.9,
                          0.05, 3.0, 2.0, 1.0)
    b = sextet_absorption(V, 0.0, 0.0, 33.0, 0.25, 1.2, 0.9,
                          0.05, 3.0, 2.0, 1.0, width_model="free")
    np.testing.assert_allclose(a, b, atol=0)


def test_width_model_desconocido_lanza():
    with pytest.raises(ValueError, match="width_model desconocido"):
        sextet_absorption(V, 0.0, 0.0, 33.0, 0.25, 1.0, 1.0,
                          0.05, 3.0, 2.0, 1.0, width_model="brand")


def test_dispersion_llega_por_extras():
    from core.physics import component_absorption

    p = np.array([0.0, 0.0, 33.0, 0.25, 1.0, 1.0, 0.05, 3.0, 2.0, 1.0])
    libre = component_absorption(V, "Sextete", p, extras={"treatment": "1st_order"})
    disp = component_absorption(V, "Sextete", p, extras={
        "treatment": "1st_order", "width_model": "dispersion", "sigma_bhf": 1.0})
    assert np.max(np.abs(disp - libre)) > 1e-3
