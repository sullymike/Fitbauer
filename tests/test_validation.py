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
    assert "[0, 1]" in format_validation_issues(issues)


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


def test_validate_fit_state_accepts_new_component_kinds():
    """Ningún tipo de COMPONENT_KINDS debe disparar la incidencia s1_kind.

    Regresión: la whitelist solo tenía Sextete/Doblete/Singlete.
    """
    from core.params import COMPONENT_KINDS

    v = np.linspace(-6, 6, 512)
    y = np.ones(512)
    for kind in COMPONENT_KINDS:
        state = FitState(
            velocity=v, y_data=y, sigma_data=np.ones(512),
            values={"baseline": 1.0}, fixed={}, bounds={},
            components=[Component(idx=1, enabled=True, kind=kind)],
            constraints=[], line_profile="Lorentziana",
        )
        issues = validate_fit_state(state)
        assert not any(i.key == "s1_kind" for i in issues), \
            f"tipo válido {kind!r} rechazado: {[i.message for i in issues if i.key == 's1_kind']}"


def test_validate_distribution_parameters_accepts_all_shapes():
    """Ninguna forma de DISTRIBUTION_SHAPES debe generar incidencia de forma.

    Regresión: la whitelist no incluía '2D'.
    """
    from core.params import DISTRIBUTION_SHAPES
    from types import SimpleNamespace

    for shape in DISTRIBUTION_SHAPES:
        state = SimpleNamespace(
            delta=0.0, quad=0.0, fixed_bhf=33.0, gamma=0.18,
            bmin=0.0, bmax=50.0, nbins=50, log_alpha=-2.0,
            shape=shape, reg_mode="tikhonov",
        )
        issues = validate_distribution_parameters(state)
        assert not any(i.key == "shape" for i in issues), \
            f"forma válida {shape!r} rechazada"


def test_validate_distribution_vbf_sigma_limits():
    """σ mín/máx de las gaussianas: orden y σ mín sola frente a la anchura."""
    from mossbauer_i18n import tr

    def estado(**kw):
        base = dict(delta=0.0, quad=0.0, fixed_bhf=33.0, gamma=0.18,
                    bmin=0.0, bmax=50.0, qmin=-1.0, qmax=1.0, nbins=50,
                    log_alpha=-2.0, shape="VBF", reg_mode="tikhonov",
                    variable="BHF", vbf_sigma_min=0.0, vbf_sigma_max=0.0,
                    vbf_sigma_min_y=0.0, vbf_sigma_max_y=0.0)
        base.update(kw)
        return SimpleNamespace(**base)

    def claves(**kw):
        return {i.key for i in validate_distribution_parameters(estado(**kw))}

    assert not {"vbf_sigma", "vbf_sigma_y"} & claves()                 # auto
    assert not {"vbf_sigma"} & claves(vbf_sigma_min=1.0, vbf_sigma_max=4.0)
    assert "vbf_sigma" in claves(vbf_sigma_min=4.0, vbf_sigma_max=1.0)
    assert "vbf_sigma" in claves(vbf_sigma_min=60.0)                   # ≥ anchura
    # Solo las formas gaussianas los usan.
    assert "vbf_sigma" not in claves(shape="Histograma", vbf_sigma_min=4.0,
                                     vbf_sigma_max=1.0)
    # En 2D el eje Y se comprueba con su propio rango.
    assert "vbf_sigma_y" in claves(shape="VBF 2D", variable="BHF-ΔEQ",
                                   vbf_sigma_min_y=3.0)
    assert "vbf_sigma_y" not in claves(shape="VBF", vbf_sigma_min_y=3.0)
    issues = validate_distribution_parameters(estado(vbf_sigma_min=4.0, vbf_sigma_max=1.0))
    msg = next(i.message for i in issues if i.key == "vbf_sigma")
    assert msg == tr("valid.vbf_sigma_order", var="BHF", min="4", max="1")

