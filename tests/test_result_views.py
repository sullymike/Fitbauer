import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.result_views import (
    discrete_result_view,
    distribution_result_view,
    ParameterEstimate,
    ResultMetric,
)


def test_discrete_result_view_metrics_and_parameters():
    result = SimpleNamespace(
        values={"baseline": 1.0, "s1_delta": 0.12},
        errors={"s1_delta": 0.01},
        stats={"chi2": 10.0, "red_chi2": 1.2},
        n_starts=9,
        success=True,
    )

    view = discrete_result_view(result, fixed={"baseline": True})

    assert view.value_for("s1_delta") == 0.12
    assert view.error_for("s1_delta") == 0.01
    assert view.red_chi2() == 1.2
    assert view.has_errors() is True
    assert view.free_keys() == ()
    assert view.n_starts() == 9
    assert view.correlations() == {}
    assert view.stats_dict(keys=("chi2",)) == {"chi2": 10.0}
    metrics = view.metrics()
    assert any(isinstance(m, ResultMetric) and m.key == "red_chi2" for m in metrics)
    assert any(m.key == "n_starts" and m.value == 9 for m in metrics)
    params = view.parameters(keys=("baseline", "s1_delta"))
    assert all(isinstance(p, ParameterEstimate) for p in params)
    assert params[0].fixed is True
    assert params[1].error == 0.01


def test_distribution_result_view_curves_metrics_and_parameters():
    result = SimpleNamespace(
        bhf_centers=np.array([30.0, 31.0]),
        probability=np.array([0.4, 0.6]),
        fitted_curve=np.array([1.0, 0.9]),
        residuals=np.array([0.0, 0.1]),
        sharp_weights=np.array([0.02]),
        baseline=1.0,
        slope=0.0,
        alpha=1e-3,
        rms=0.05,
        success=True,
        message="ok",
        fitted_dist_center=None,
        fitted_dist_sigma=None,
        fitted_dist_p=None,
        effective_dof=12.0,
    )

    view = distribution_result_view(result)
    x, p = view.probability_curve()

    assert np.allclose(x, [30.0, 31.0])
    assert np.allclose(p, [0.4, 0.6])
    assert np.allclose(view.fitted_curve(), [1.0, 0.9])
    assert np.allclose(view.sharp_weights(), [0.02])
    assert any(m.key == "rms" and m.value == 0.05 for m in view.metrics())
    assert [param.key for param in view.parameters()] == ["baseline", "slope", "alpha"]
