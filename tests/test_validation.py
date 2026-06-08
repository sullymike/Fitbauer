import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.fit_engine import Component, FitState
from core.validation import (
    format_validation_issues,
    validate_distribution_parameters,
    validate_fit_state,
    validate_values_against_bounds,
)


def test_validate_values_against_bounds_reports_nonfinite_and_out_of_range():
    issues = validate_values_against_bounds(
        {"a": 2.0, "b": float("nan")},
        {"a": (0.0, 1.0), "b": (0.0, 1.0)},
    )

    assert {issue.key for issue in issues} == {"a", "b"}
    assert "fuera de límites" in format_validation_issues(issues)


def test_validate_fit_state_checks_shapes_bounds_and_component_kind():
    state = FitState(
        velocity=np.array([0.0, 1.0]),
        y_data=np.array([1.0]),
        sigma_data=np.array([1.0]),
        values={"baseline": 2.0},
        fixed={},
        bounds={"baseline": (0.7, 1.3)},
        components=[Component(idx=1, enabled=True, kind="Raro")],
        constraints=[],
        line_profile="Lorentziana",
    )

    issues = validate_fit_state(state)
    keys = {issue.key for issue in issues}
    assert "data_shape" in keys
    assert "baseline" in keys
    assert "s1_kind" in keys


def test_validate_distribution_parameters():
    state = SimpleNamespace(
        delta=0.0,
        quad=0.0,
        fixed_bhf=33.0,
        gamma=-0.1,
        bmin=10.0,
        bmax=5.0,
        nbins=3,
        log_alpha=0.0,
        shape="Histograma",
        reg_mode="tikhonov",
    )

    issues = validate_distribution_parameters(state)
    keys = {issue.key for issue in issues}
    assert {"gamma", "range", "nbins"}.issubset(keys)
