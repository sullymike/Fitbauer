"""Correlación δ(H)/ΔEQ(H), VBF multi-gaussiano y regularización MaxEnt."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mossbauer_distribution as md


def _grid():
    return md.parameter_grid(0.0, 50.0, 40)


# ── Hueco 1: correlación δ(H)/ΔEQ(H) ────────────────────────────────────────
def test_kernel_correlation_slope_zero_reproduces_classic():
    v = np.linspace(-10, 10, 250)
    centers = _grid()
    K0 = md.build_bhf_kernel(v, centers, delta=0.15, quad=0.05)
    Kc = md.build_bhf_kernel(v, centers, delta=0.15, quad=0.05,
                             delta_slope=0.0, quad_slope=0.0)
    assert np.allclose(K0, Kc)


def test_kernel_correlation_shifts_column_centroids():
    v = np.linspace(-10, 10, 400)
    centers = _grid()
    href = float(np.mean(centers))
    K0 = md.build_bhf_kernel(v, centers, delta=0.0)
    Ks = md.build_bhf_kernel(v, centers, delta=0.0, delta_slope=0.02, h_ref=href)
    # El centroide (posición ponderada) de una columna de alto campo se desplaza
    # respecto al campo pivote; la columna en H≈href apenas cambia.
    def centroid(col):
        return float(np.sum(v * col) / np.sum(col))
    j_hi = centers.size - 1
    assert abs(centroid(Ks[:, j_hi]) - centroid(K0[:, j_hi])) > 1e-3
    j_ref = int(np.argmin(np.abs(centers - href)))
    assert abs(centroid(Ks[:, j_ref]) - centroid(K0[:, j_ref])) < 5e-2


def test_fit_hyperfine_distribution_accepts_slopes():
    v = np.linspace(-10, 10, 300)
    centers = _grid()
    P = np.exp(-0.5 * ((centers - 33) / 3.0) ** 2)
    K = md.build_bhf_kernel(v, centers, delta=0.0)
    y = 1.0 - K @ (P / P.sum() * 2.0)
    r = md.fit_hyperfine_distribution(v, y, pmin=0, pmax=50, nbins=40, alpha=1e-3,
                                      fit_slope=False, delta_slope=0.003)
    assert r.success and np.all(r.weights >= -1e-9)


# ── Hueco 2: VBF multi-gaussiano ────────────────────────────────────────────
def test_vbf_recovers_two_gaussians():
    v = np.linspace(-10, 10, 400)
    centers = md.parameter_grid(0.0, 50.0, 80)

    def G(mu, s):
        w = np.exp(-0.5 * ((centers - mu) / s) ** 2)
        return w / np.trapezoid(w, centers)

    P_true = 1.0 * G(20.0, 2.0) + 0.6 * G(45.0, 3.0)
    K = md.build_bhf_kernel(v, centers, delta=0.0, gamma=0.25)
    y = 1.0 - K @ (P_true * 0.5)
    rng = np.random.default_rng(1)
    y = y + rng.normal(0, 8e-4, y.size)

    r = md.fit_vbf_hyperfine_distribution(v, y, n_components=2, profile="Lorentziana",
                                          pmin=0, pmax=50, nbins=80, gamma=0.25)
    assert r.success
    assert r.vbf_components is not None and len(r.vbf_components) == 2
    mus = [c[1] for c in r.vbf_components]
    # ordenadas por μ y cerca de los valores verdaderos
    assert mus == sorted(mus)
    assert abs(mus[0] - 20.0) < 2.0
    assert abs(mus[1] - 45.0) < 3.0


def test_vbf_single_component_matches_gaussian_shape():
    v = np.linspace(-10, 10, 300)
    r = md.fit_vbf_hyperfine_distribution(v, np.ones_like(v), n_components=1,
                                          profile="Lorentziana", pmin=0, pmax=50, nbins=60)
    assert r.success and r.vbf_components is not None and len(r.vbf_components) == 1


# ── MaxEnt ──────────────────────────────────────────────────────────────────
def test_maxent_positive_normalized_and_peaked():
    v = np.linspace(-10, 10, 300)
    centers = _grid()
    P = np.exp(-0.5 * ((centers - 33) / 3.0) ** 2)
    K = md.build_bhf_kernel(v, centers, delta=0.0)
    y = 1.0 - K @ (P / P.sum() * 2.0)
    rng = np.random.default_rng(0)
    y = y + rng.normal(0, 2e-3, y.size)

    r = md.fit_hyperfine_distribution(v, y, pmin=0, pmax=50, nbins=40, alpha=1e-3,
                                      reg_mode="maxent", fit_slope=False)
    assert r.success
    assert np.all(r.weights >= -1e-9)
    assert abs(float(np.trapezoid(r.probability, r.bhf_centers)) - 1.0) < 1e-6
    peak = float(r.bhf_centers[int(np.argmax(r.weights))])
    assert 28.0 < peak < 38.0
    assert r.effective_dof is not None and r.effective_dof > 0
