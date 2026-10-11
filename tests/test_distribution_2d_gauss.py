"""Formas paramétricas de la distribución 2D: Gaussiana 2D y VBF 2D.

Gaussianas bivariantes (A, μx, μy, σx, σy, ρ) sobre la malla del histograma 2D.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.params import DISTRIBUTION_SHAPES, is_2d_shape
from mossbauer_distribution import (
    bivariate_gaussian_weights,
    build_bhf_quad_distribution_kernel,
    fit_vbf_2d_distribution,
    parameter_grid,
)


def _espectro(v, xc, yc, w, *, vx, vy, bhf=33.0, gamma=0.25, cuentas=1e6, prof=0.05, seed=0):
    K = build_bhf_quad_distribution_kernel(v, xc, yc, variable_x=vx, variable_y=vy,
                                           bhf=bhf, gamma=gamma)
    m = K @ w.ravel()
    y0 = cuentas * (1.0 - prof * m / m.max())
    return np.random.default_rng(seed).poisson(y0).astype(float)


def test_gaussiana_bivariante_normalizada_y_con_correlacion():
    xc = parameter_grid(-3, 3, 61); yc = parameter_grid(-3, 3, 61)
    w = bivariate_gaussian_weights(xc, yc, 0.0, 0.0, 1.0, 0.5, 0.6)
    assert w.sum() == pytest.approx(1.0)
    X, Y = np.meshgrid(xc, yc, indexing="ij")
    cov = np.sum(w * X * Y)
    assert cov / (1.0 * 0.5) == pytest.approx(0.6, abs=0.02)


def test_gaussiana_estrecha_entre_nodos_no_desaparece():
    xc = parameter_grid(0, 10, 11); yc = parameter_grid(0, 1, 11)
    w = bivariate_gaussian_weights(xc, yc, 4.5, 0.55, 1e-4, 1e-4, 0.0)
    assert w.sum() == pytest.approx(1.0)


@pytest.mark.parametrize("vx,vy,ylim,true", [
    ("bhf", "quad", (-0.4, 0.4), (31.0, 0.05, 1.5, 0.08, 0.6)),
    ("bhf", "delta", (-0.2, 0.6), (31.0, 0.2, 1.5, 0.06, -0.5)),
])
def test_gaussiana_2d_recupera_los_parametros(vx, vy, ylim, true):
    """Con campo, cada línea del sextete ve otra combinación: todo se determina."""
    v = np.linspace(-10, 10, 512)
    xc = parameter_grid(20, 40, 41); yc = parameter_grid(*ylim, 33)
    y = _espectro(v, xc, yc, bivariate_gaussian_weights(xc, yc, *true), vx=vx, vy=vy, seed=1)
    r = fit_vbf_2d_distribution(v, y, n_components=1, variable_x=vx, variable_y=vy,
                                gamma=0.25, bmin=20, bmax=40, nbins_bhf=41,
                                qmin=ylim[0], qmax=ylim[1], nbins_quad=33, sigma=np.sqrt(y))
    assert r.shape == "Gaussiana 2D" and r.success
    (_a, mx, my, sx, sy, rho), = r.vbf2d_components
    np.testing.assert_allclose([mx, my, sx, sy], true[:4], rtol=0.05, atol=0.01)
    assert rho == pytest.approx(true[4], abs=0.1)
    assert r.alpha_bhf == 0.0 and r.probability.shape == (41, 33)
    assert r.dof_warning is None


def test_vbf_2d_separa_dos_sitios_is_deq():
    """Fe²⁺/Fe³⁺ en IS–ΔEQ: fracciones y centros; avisa de la no unicidad."""
    v = np.linspace(-4, 4, 256)
    xc = parameter_grid(-0.5, 1.5, 31); yc = parameter_grid(0, 3.5, 36)
    w = (0.7 * bivariate_gaussian_weights(xc, yc, 1.05, 2.1, 0.08, 0.3, 0.6)
         + 0.3 * bivariate_gaussian_weights(xc, yc, 0.35, 0.9, 0.06, 0.25, 0.0))
    y = _espectro(v, xc, yc, w, vx="delta", vy="quad", bhf=0.0, cuentas=1e5, prof=0.02)
    r = fit_vbf_2d_distribution(v, y, n_components=2, variable_x="delta", variable_y="quad",
                                bhf=0.0, gamma=0.25, bmin=-0.5, bmax=1.5, nbins_bhf=31,
                                qmin=0, qmax=3.5, nbins_quad=36, sigma=np.sqrt(y))
    assert r.shape == "VBF 2D"
    c1, c2 = r.vbf2d_components                      # ordenadas por μx
    frac = c1[0] / (c1[0] + c2[0])
    assert frac == pytest.approx(0.3, abs=0.05)
    assert c1[1] == pytest.approx(0.35, abs=0.1) and c2[1] == pytest.approx(1.05, abs=0.05)
    assert c1[2] == pytest.approx(0.9, abs=0.1) and c2[2] == pytest.approx(2.1, abs=0.1)
    from mossbauer_i18n import tr
    assert tr("bhf.note_is_quad_doublets") in (r.dof_warning or "")
    assert np.sum((r.residuals / np.sqrt(y)) ** 2) / y.size < 1.2


def test_formas_2d_registradas():
    assert {"Gaussiana 2D", "VBF 2D"} <= set(DISTRIBUTION_SHAPES)
    assert is_2d_shape("2D") and is_2d_shape("VBF 2D") and not is_2d_shape("VBF")


def test_vbf_2d_cotas_sigma_por_eje():
    """σ mín/máx de cada eje acotan las anchuras; 0 deja el automático."""
    v = np.linspace(-10, 10, 512)
    xc = parameter_grid(20, 40, 41); yc = parameter_grid(-0.4, 0.4, 33)
    y = _espectro(v, xc, yc, bivariate_gaussian_weights(xc, yc, 31.0, 0.05, 1.5, 0.08, 0.6),
                  vx="bhf", vy="quad", seed=1)
    comun = dict(n_components=1, variable_x="bhf", variable_y="quad", gamma=0.25,
                 bmin=20, bmax=40, nbins_bhf=41, qmin=-0.4, qmax=0.4, nbins_quad=33,
                 sigma=np.sqrt(y))
    auto = fit_vbf_2d_distribution(v, y, **comun)
    (sx_auto, sy_auto) = auto.vbf2d_sigma_bounds
    dx, dy = xc[1] - xc[0], yc[1] - yc[0]
    assert sx_auto == pytest.approx((0.25 * dx, xc[-1] - xc[0]))
    assert sy_auto == pytest.approx((0.25 * dy, yc[-1] - yc[0]))

    r = fit_vbf_2d_distribution(v, y, **comun, sigma_x_max=1.0, sigma_y_min=0.12)
    assert r.success
    (_a, _mx, _my, sx, sy, _rho), = r.vbf2d_components
    assert sx <= 1.0 + 1e-9 and sy >= 0.12 - 1e-9
    assert r.vbf2d_sigma_bounds[0][1] == 1.0 and r.vbf2d_sigma_bounds[1][0] == 0.12

