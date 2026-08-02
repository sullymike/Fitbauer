"""Nivel 10 de la revisión del fuente de NORMOS: bloque DIST (distribuciones).

Verificado equivalente: la matriz de suavizado. ``SMOOTH`` (``distauxl.for``)
monta ``λ·D`` con diagonal ``[1, 5, 6, …, 6, 5, 1]`` y bandas ``[−2, −4, …]`` y
``[1, …]`` — que es exactamente ``D₂ᵀD₂`` con ``D₂`` la segunda diferencia, el
mismo penalizador Tikhonov que usa ``second_difference_matrix`` aquí.

Lo que NO estaba: los **anclajes de borde** ``BETA1``/``BETA2``, que NORMOS suma
a las esquinas diagonales DESPUÉS de escalar por λ (o sea con peso propio,
independiente de la suavidad) para «forzar la distribución a ir suavemente a
cero en los límites».
"""
from __future__ import annotations

import numpy as np
import pytest

from mossbauer_distribution import (
    edge_anchor_rows,
    edge_pileup_ratio,
    fit_hyperfine_distribution,
    second_difference_matrix,
    sextet_absorption,
)


def _smooth_normos(n: int, lamda: float, beta1: float, beta2: float) -> np.ndarray:
    """Port literal de ``SMOOTH`` (distauxl.for:24), índices 0-based."""
    d = np.zeros((n, n), dtype=float)
    d[0, 0], d[0, 1], d[0, 2] = 1.0, -2.0, 1.0
    d[1, 0], d[1, 1], d[1, 2], d[1, 3] = -2.0, 5.0, -4.0, 1.0
    for l in range(1, n - 3):
        d[l + 1, l - 1] = 1.0
        d[l + 1, l] = -4.0
        d[l + 1, l + 1] = 6.0
        d[l + 1, l + 2] = -4.0
        d[l + 1, l + 3] = 1.0
    d[n - 1, n - 1], d[n - 1, n - 2], d[n - 1, n - 3] = 1.0, -2.0, 1.0
    d[n - 2, n - 1], d[n - 2, n - 2], d[n - 2, n - 3], d[n - 2, n - 4] = \
        -2.0, 5.0, -4.0, 1.0
    d *= lamda
    d[0, 0] += beta1
    d[n - 1, n - 1] += beta2
    return d


@pytest.mark.parametrize("n", [8, 12, 30])
def test_la_matriz_de_suavizado_es_la_misma(n):
    """``λ·D₂ᵀD₂`` de aquí == ``SMOOTH`` de NORMOS sin anclajes."""
    lamda = 0.37
    d2 = second_difference_matrix(n)
    nuestra = lamda * (d2.T @ d2)
    suya = _smooth_normos(n, lamda, 0.0, 0.0)
    np.testing.assert_allclose(nuestra, suya, atol=1e-12)


def test_los_anclajes_reproducen_beta1_beta2():
    """Las filas de anclaje, al formar LᵀL, dan justo las esquinas de NORMOS."""
    n, beta = 12, 2.5
    filas = edge_anchor_rows(n, beta)
    aporte = filas.T @ filas
    esperado = np.zeros((n, n))
    esperado[0, 0] = beta
    esperado[n - 1, n - 1] = beta
    np.testing.assert_allclose(aporte, esperado, atol=1e-12)


def test_sin_anclaje_no_hay_filas():
    assert edge_anchor_rows(20, 0.0).shape == (0, 20)
    assert edge_anchor_rows(20, -1.0).shape == (0, 20)


# ── Diagnóstico de malla insuficiente ────────────────────────────────────────

def _espectro_gaussiano(centro_b: float, sigma_b: float = 3.0):
    v = np.linspace(-11.0, 11.0, 512)
    b = np.linspace(20.0, 60.0, 400)
    p = np.exp(-0.5 * ((b - centro_b) / sigma_b) ** 2)
    p /= p.sum()
    y = 1.0 - sum(
        pi * sextet_absorption(v, delta=0.0, quad=0.0, bhf=bi, gamma=0.28) * 0.05
        for bi, pi in zip(b, p))
    return v, y + np.random.default_rng(0).normal(0.0, 2e-4, v.size)


def test_edge_pileup_detecta_la_malla_corta():
    """Con la distribución fuera de rango, el peso se apila en el bin extremo."""
    v, y = _espectro_gaussiano(45.0)
    amplia = fit_hyperfine_distribution(
        v, y, delta=0.0, quad=0.0, gamma=0.28, pmin=0.0, pmax=60.0,
        nbins=45, alpha=0.01)
    corta = fit_hyperfine_distribution(
        v, y, delta=0.0, quad=0.0, gamma=0.28, pmin=0.0, pmax=40.0,
        nbins=45, alpha=0.01)
    assert amplia.edge_pileup < 0.1
    assert corta.edge_pileup > 0.8
    # Y el sesgo que provoca es enorme: ⟨B⟩ se hunde.
    def media(r):
        w = np.asarray(r.weights)
        return float(np.sum(w * np.asarray(r.bhf_centers)) / np.sum(w))
    assert media(amplia) == pytest.approx(45.0, abs=1.0)
    assert media(corta) < 35.0


def test_edge_pileup_ratio_casos_limite():
    assert edge_pileup_ratio(np.array([0.0, 1.0, 0.0])) == pytest.approx(0.0)
    assert edge_pileup_ratio(np.array([1.0, 0.5, 0.2])) == pytest.approx(1.0)
    assert edge_pileup_ratio(np.array([0.0, 0.0])) == 0.0
    assert edge_pileup_ratio(np.zeros(5)) == 0.0


def test_el_anclaje_no_cambia_nada_con_malla_suficiente():
    """β solo debe actuar en el borde; con la malla bien elegida no molesta."""
    v, y = _espectro_gaussiano(45.0)
    kw = dict(delta=0.0, quad=0.0, gamma=0.28, pmin=0.0, pmax=60.0,
              nbins=45, alpha=0.01)
    sin = fit_hyperfine_distribution(v, y, **kw)
    con = fit_hyperfine_distribution(v, y, edge_anchor=100.0, **kw)
    assert con.rms == pytest.approx(sin.rms, rel=1e-3)
    assert con.edge_pileup <= sin.edge_pileup + 1e-9


def test_el_anclaje_reduce_la_cola_del_borde():
    v, y = _espectro_gaussiano(45.0)
    kw = dict(delta=0.0, quad=0.0, gamma=0.28, pmin=0.0, pmax=60.0,
              nbins=45, alpha=0.01)
    sin = fit_hyperfine_distribution(v, y, **kw)
    con = fit_hyperfine_distribution(v, y, edge_anchor=1e4, **kw)
    assert con.edge_pileup < sin.edge_pileup
