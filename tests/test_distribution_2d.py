from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mossbauer_distribution import (  # noqa: E402
    bhf_quad_distribution_diagnostics,
    build_bhf_quad_distribution_kernel,
    fit_bhf_quad_distribution,
    fit_hyperfine_distribution,
    normalize_probability_2d,
    parameter_grid,
    sextet_absorption,
)


def test_bhf_quad_kernel_shape_and_order():
    v = np.linspace(-8.0, 8.0, 64)
    b = np.array([30.0, 33.0, 36.0])
    q = np.array([-0.2, 0.0, 0.2, 0.4])
    k = build_bhf_quad_distribution_kernel(v, b, q, delta=0.0, gamma=0.32)
    assert k.shape == (v.size, b.size * q.size)
    # Orden C: primer índice BHF, segundo ΔEQ.
    expected = sextet_absorption(v, delta=0.0, quad=q[1], bhf=b[0], gamma=0.32)
    assert np.allclose(k[:, 1], expected)


def test_normalize_probability_2d_integrates_to_one():
    b = parameter_grid(20.0, 40.0, 5)
    q = parameter_grid(-1.0, 1.0, 7)
    w = np.ones((b.size, q.size))
    p = normalize_probability_2d(w, b, q)
    area = np.trapezoid(np.trapezoid(p, q, axis=1), b)
    assert np.isclose(area, 1.0)


def test_fit_bhf_quad_distribution_recovers_synthetic_peak():
    v = np.linspace(-8.0, 8.0, 180)
    baseline = 1.0
    true_b = 32.0
    true_q = 0.4
    depth = 0.018
    y = baseline - depth * sextet_absorption(
        v, delta=0.05, quad=true_q, bhf=true_b, gamma=0.32,
        int1=3.0, int2_rel=1.0, int3_rel=1.0,
    )
    res = fit_bhf_quad_distribution(
        v, y,
        delta=0.05, gamma=0.32,
        bmin=28.0, bmax=36.0, nbins_bhf=9,
        qmin=-0.4, qmax=0.8, nbins_quad=7,
        alpha_bhf=1e-8, alpha_quad=1e-8,
        fit_slope=False, baseline=baseline,
        int1=3.0, int2_rel=1.0, int3_rel=1.0,
    )
    assert res.success
    assert res.rms < 5e-4
    ib, iq = np.unravel_index(np.argmax(res.weights), res.weights.shape)
    assert abs(res.bhf_centers[ib] - true_b) <= 1.1
    assert abs(res.quad_centers[iq] - true_q) <= 0.21
    assert res.marginal_bhf is not None
    assert res.marginal_quad is not None
    assert np.isfinite(res.mean_bhf)
    assert np.isfinite(res.mean_quad)


def test_bhf_quad_diagnostics_detect_positive_correlation():
    b = parameter_grid(20.0, 40.0, 25)
    q = parameter_grid(-1.0, 1.0, 21)
    bb, qq = np.meshgrid(b, q, indexing="ij")
    ridge = np.exp(-0.5 * ((qq - (bb - 30.0) / 12.0) / 0.18) ** 2) * np.exp(-0.5 * ((bb - 30.0) / 4.0) ** 2)
    p = normalize_probability_2d(ridge, b, q)
    diag = bhf_quad_distribution_diagnostics(p, b, q)
    assert diag["corr_bhf_quad"] > 0.75


def test_fit_delta_distribution_1d_recovers_isomer_shift():
    v = np.linspace(-5.0, 5.0, 160)
    baseline = 1.0
    true_delta = 0.35
    y = baseline - 0.02 * sextet_absorption(v, delta=true_delta, quad=0.8, bhf=0.0, gamma=0.32)
    res = fit_hyperfine_distribution(
        v, y, variable="delta", delta=0.0, quad=0.8, bhf=0.0, gamma=0.32,
        pmin=-0.2, pmax=0.8, nbins=21, alpha=1e-8,
        fit_slope=False, baseline=baseline,
    )
    assert res.success
    assert res.rms < 5e-4
    peak = res.bhf_centers[int(np.argmax(res.weights))]
    assert abs(peak - true_delta) <= 0.06


def test_fit_is_qs_distribution_2d_recovers_synthetic_peak():
    v = np.linspace(-5.0, 5.0, 180)
    baseline = 1.0
    true_delta = 0.32
    true_q = 0.9
    y = baseline - 0.018 * sextet_absorption(v, delta=true_delta, quad=true_q, bhf=0.0, gamma=0.32)
    res = fit_bhf_quad_distribution(
        v, y, variable_x="delta", variable_y="quad",
        delta=0.0, quad=0.0, bhf=0.0, gamma=0.32,
        bmin=0.0, bmax=0.6, nbins_bhf=13,
        qmin=0.4, qmax=1.2, nbins_quad=9,
        alpha_bhf=1e-8, alpha_quad=1e-8,
        fit_slope=False, baseline=baseline,
    )
    assert res.success
    ix, iy = np.unravel_index(np.argmax(res.weights), res.weights.shape)
    assert abs(res.bhf_centers[ix] - true_delta) <= 0.06
    assert abs(res.quad_centers[iy] - true_q) <= 0.11
    assert res.x_variable == "delta"
    assert res.y_variable == "quad"


def test_fit_bhf_is_distribution_2d_uses_fixed_quadrupole():
    v = np.linspace(-8.0, 8.0, 180)
    baseline = 1.0
    true_b = 32.0
    true_delta = 0.25
    y = baseline - 0.018 * sextet_absorption(v, delta=true_delta, quad=0.2, bhf=true_b, gamma=0.32)
    res = fit_bhf_quad_distribution(
        v, y, variable_x="bhf", variable_y="delta",
        delta=0.0, quad=0.2, bhf=33.0, gamma=0.32,
        bmin=28.0, bmax=36.0, nbins_bhf=9,
        qmin=0.0, qmax=0.5, nbins_quad=11,
        alpha_bhf=1e-8, alpha_quad=1e-8,
        fit_slope=False, baseline=baseline,
    )
    assert res.success
    ix, iy = np.unravel_index(np.argmax(res.weights), res.weights.shape)
    assert abs(res.bhf_centers[ix] - true_b) <= 1.1
    assert abs(res.quad_centers[iy] - true_delta) <= 0.06


def test_fit_bhf_quad_distribution_accepts_fixed_sharp_component():
    v = np.linspace(-8.0, 8.0, 180)
    baseline = 1.0
    sharp_depth = 0.005
    dist_y = baseline - 0.014 * sextet_absorption(v, delta=0.0, quad=0.2, bhf=32.0, gamma=0.32)
    sharp_abs = sharp_depth * sextet_absorption(v, delta=0.0, quad=0.0, bhf=34.0, gamma=0.32)
    y = dist_y - sharp_abs
    res = fit_bhf_quad_distribution(
        v, y, delta=0.0, gamma=0.32,
        bmin=28.0, bmax=36.0, nbins_bhf=9,
        qmin=-0.4, qmax=0.8, nbins_quad=7,
        alpha_bhf=1e-4, alpha_quad=1e-4,
        fit_slope=False, baseline=baseline,
        sharp_components=[{"kind": "Sextete", "bhf": 34.0, "quad": 0.0,
                           "gamma": 0.16, "depth": sharp_depth,
                           "depth_fixed": True}],
    )
    assert res.success
    assert res.sharp_weights is not None
    assert np.isclose(res.sharp_weights[0], sharp_depth)


def test_distribution_voigt_profile_differs_and_restores_global_state():
    """El perfil Voigt en la distribución es explícito y no filtra estado global.

    Verifica (1) que ``profile='Voigt'`` produce un kernel distinto al
    Lorentziano, y (2) que el gestor de perfil restaura las variables globales
    de ``core.physics`` que ``lorentzian`` lee, aunque estuvieran "contaminadas"
    por un ajuste discreto previo.
    """
    import core.physics as _phys

    v = np.linspace(-10.0, 10.0, 300)
    y = 1.0 - 0.2 * sextet_absorption(v, delta=0.0, quad=0.0, bhf=33.0, gamma=0.30)

    # Estado global dejado por un discreto Voigt con sigma grande.
    _phys.LINE_PROFILE_KIND = "Voigt"
    _phys.VOIGT_SIGMA = 0.9
    before = (_phys.LINE_PROFILE_KIND, _phys.VOIGT_SIGMA)

    common = dict(variable="bhf", gamma=0.30, pmin=20.0, pmax=45.0,
                  nbins=40, alpha=1e-3, fit_slope=False)
    fit_lorentz = fit_hyperfine_distribution(v, y, profile="Lorentziana", **common)
    assert (_phys.LINE_PROFILE_KIND, _phys.VOIGT_SIGMA) == before  # restaurado

    fit_voigt = fit_hyperfine_distribution(v, y, profile="Voigt",
                                           voigt_sigma=0.10, **common)
    assert (_phys.LINE_PROFILE_KIND, _phys.VOIGT_SIGMA) == before  # restaurado

    # Los dos perfiles dan curvas distintas.
    assert not np.allclose(fit_lorentz.fitted_curve, fit_voigt.fitted_curve)
    # Los datos son Lorentzianos: el ajuste Lorentz no es peor que el Voigt.
    assert fit_lorentz.rms <= fit_voigt.rms + 1e-9

    # Restaura el default para no afectar a otros tests.
    _phys.LINE_PROFILE_KIND = "Lorentziana"
    _phys.VOIGT_SIGMA = 0.05


def test_distribution_2d_voigt_profile_differs():
    v = np.linspace(-8.0, 8.0, 180)
    y = 1.0 - 0.014 * sextet_absorption(v, delta=0.0, quad=0.2, bhf=32.0, gamma=0.32)
    common = dict(delta=0.0, gamma=0.32, bmin=28.0, bmax=36.0, nbins_bhf=9,
                  qmin=-0.4, qmax=0.8, nbins_quad=7, alpha_bhf=1e-4,
                  alpha_quad=1e-4, fit_slope=False, baseline=1.0)
    res_l = fit_bhf_quad_distribution(v, y, profile="Lorentziana", **common)
    res_v = fit_bhf_quad_distribution(v, y, profile="Voigt", voigt_sigma=0.12, **common)
    assert not np.allclose(res_l.fitted_curve, res_v.fitted_curve)
