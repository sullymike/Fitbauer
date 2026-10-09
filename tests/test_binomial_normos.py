"""Distribución binomial de vecinos al estilo NORMOS-DIST (DISTRI=3, CONC>0).

NORMOS calcula 13 subespectros (0…12 vecinos) con pesos binomiales de la
concentración CONC y el campo BHF + k·DTB. Los pesos de referencia se leyeron
del binario de DIST (sonda 2026-10-09, CONC=50 %, tabla AREREL del .RES).
"""
from __future__ import annotations

import numpy as np
import pytest

from mossbauer_distribution import (
    BINOMIAL_NEIGHBORS_NORMOS,
    binomial_neighbor_weights,
    build_hyperfine_distribution_kernel,
    fit_binomial_hyperfine_distribution,
)

#: AREREL(1…13) de NORMOS-DIST con CONC=50 (cuatro cifras, como las imprime).
AREREL_CONC50 = [.2441e-3, .2930e-2, .1611e-1, .5371e-1, .1208, .1934, .2256,
                 .1934, .1208, .5371e-1, .1611e-1, .2930e-2, .2441e-3]


def test_pesos_iguales_a_los_de_normos_dist():
    w = binomial_neighbor_weights(0.5, BINOMIAL_NEIGHBORS_NORMOS)
    assert w.size == 13
    np.testing.assert_allclose(w, AREREL_CONC50, rtol=2e-3)
    assert w.sum() == pytest.approx(1.0)


def test_pesos_con_otra_concentracion_y_vecinos():
    w = binomial_neighbor_weights(0.2, 8)
    assert w.size == 9
    assert w[0] == pytest.approx(0.8 ** 8)
    assert int(np.argmax(w)) == 1          # media n·c = 1.6 vecinos


def _espectro_binomial(conc, start, step, variable="bhf", **kw):
    v = np.linspace(-10.0, 10.0, 256)
    centers = start + step * np.arange(13)
    K = build_hyperfine_distribution_kernel(v, centers, variable=variable,
                                            gamma=0.3, h_ref=start, **kw)
    a = K @ binomial_neighbor_weights(conc)
    rng = np.random.default_rng(7)
    return v, 1.0 - 0.08 * a / a.max() + rng.normal(0.0, 5e-4, v.size)


def test_ajuste_recupera_campo_paso_y_concentracion():
    """Aleación tipo Fe-Al: cada vecino de soluto baja el campo 2.5 T."""
    v, y = _espectro_binomial(0.2, 33.0, -2.5)
    fit = fit_binomial_hyperfine_distribution(
        v, y, gamma=0.3, conc=0.3, fit_conc=True, start=31.0, step=-2.0)
    assert fit.success
    assert fit.fitted_dist_p == pytest.approx(0.2, abs=0.01)
    assert fit.binomial_start == pytest.approx(33.0, abs=0.1)
    assert fit.binomial_step == pytest.approx(-2.5, abs=0.05)
    assert fit.binomial_n == 12
    # Malla ascendente y P_k discreta que suma 1 (áreas relativas de NORMOS).
    assert np.all(np.diff(fit.bhf_centers) > 0)
    assert fit.probability.sum() == pytest.approx(1.0)


def test_concentracion_fija_por_defecto_como_conc_de_normos():
    v, y = _espectro_binomial(0.2, 33.0, -2.5)
    fit = fit_binomial_hyperfine_distribution(v, y, gamma=0.3, conc=0.15,
                                              start=33.0, step=-2.5)
    assert fit.fitted_dist_p == pytest.approx(0.15)


def test_binomial_de_desdoblamiento_cuadrupolar():
    """También vale para ΔEQ (DTQ de NORMOS): dobletes con B = 0."""
    v, y = _espectro_binomial(0.3, 0.4, 0.15, variable="quad", bhf=0.0, delta=0.3)
    fit = fit_binomial_hyperfine_distribution(
        v, y, variable="quad", bhf=0.0, delta=0.3, gamma=0.3, conc=0.3,
        start=0.3, step=0.1)
    assert fit.binomial_start == pytest.approx(0.4, abs=0.03)
    assert fit.binomial_step == pytest.approx(0.15, abs=0.01)
