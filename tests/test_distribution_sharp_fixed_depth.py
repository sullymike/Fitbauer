from __future__ import annotations

import numpy as np

from mossbauer_distribution import (
    build_sharp_kernel_for_fit,
    fit_fixed_hyperfine_distribution,
    singlet_absorption,
)


def test_backend_splits_fixed_and_free_sharp_depths():
    v = np.linspace(-2.0, 2.0, 51)
    components = [
        {"kind": "Singlete", "delta": -0.2, "gamma": 0.15, "depth": 0.012, "depth_fixed": True},
        {"kind": "Singlete", "delta": +0.4, "gamma": 0.20, "depth": 0.034, "depth_fixed": False},
    ]

    k_free, centers, fixed_abs, fixed_mask, fixed_weights = build_sharp_kernel_for_fit(v, components)

    assert k_free is not None
    assert k_free.shape == (v.size, 1)
    assert centers is not None and centers.size == 2
    assert fixed_mask.tolist() == [True, False]
    assert fixed_weights[0] == 0.012
    assert np.isnan(fixed_weights[1])
    expected_fixed = 0.012 * singlet_absorption(v, delta=-0.2, gamma=0.15)
    np.testing.assert_allclose(fixed_abs, expected_fixed)


def test_fixed_sharp_depth_is_not_refitted_in_backend():
    v = np.linspace(-5.0, 5.0, 201)
    # Los datos contienen un singlete de profundidad 0.03, pero el componente se
    # pasa como fijo a 0.01. Si el backend respeta el fijo, debe devolver 0.01;
    # si lo trata como libre, convergería cerca de 0.03.
    y = 1.0 - 0.03 * singlet_absorption(v, delta=0.0, gamma=0.2, int1=1.0)
    centers = np.array([30.0, 40.0])
    weights = np.array([1.0, 1.0])
    sharp = [{"kind": "Singlete", "delta": 0.0, "gamma": 0.2, "int1": 1.0, "depth": 0.01, "depth_fixed": True}]

    res = fit_fixed_hyperfine_distribution(
        v, y, centers, weights, baseline=1.0, slope=0.0, sharp_components=sharp
    )

    assert res.sharp_weights is not None
    np.testing.assert_allclose(res.sharp_weights, [0.01], rtol=0.0, atol=1e-12)


def test_free_sharp_depth_is_still_refitted_in_backend():
    v = np.linspace(-5.0, 5.0, 201)
    y = 1.0 - 0.03 * singlet_absorption(v, delta=0.0, gamma=0.2, int1=1.0)
    centers = np.array([30.0, 40.0])
    weights = np.array([1.0, 1.0])
    sharp = [{"kind": "Singlete", "delta": 0.0, "gamma": 0.2, "int1": 1.0, "depth": 0.01, "depth_fixed": False}]

    res = fit_fixed_hyperfine_distribution(
        v, y, centers, weights, baseline=1.0, slope=0.0, sharp_components=sharp
    )

    assert res.sharp_weights is not None
    assert abs(float(res.sharp_weights[0]) - 0.03) < 1e-4
