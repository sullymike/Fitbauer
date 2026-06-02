"""Tests for sharp components in Tk P(BHF) distribution mode."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mossbauer_app import MossbauerApp  # noqa: E402
from core.constants import SEXTET_PARAM_NAMES  # noqa: E402


class DummyVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def _dummy_app_with_components(n_components: int = 5):
    app = MossbauerApp.__new__(MossbauerApp)
    app.dist_use_sharp_var = DummyVar(True)
    app.n_components_var = DummyVar(n_components)
    app.sextet_enabled = {
        1: DummyVar(True),
        2: DummyVar(False),
        3: DummyVar(True),
        4: DummyVar(True),
        5: DummyVar(True),
        6: DummyVar(True),
    }
    return app


def test_distribution_sharp_indices_include_visible_components_above_three():
    """P(BHF)+sextets must include all visible active components, not only 1-3."""
    app = _dummy_app_with_components(n_components=5)

    assert app.active_sharp_component_indices_for_bhf() == [1, 3, 4, 5]

    app.dist_use_sharp_var = DummyVar(False)
    assert app.active_sharp_component_indices_for_bhf() == []


def test_distribution_sharp_builder_uses_components_above_three():
    """The sharp kernel payload should be built for enabled sextets above index 3."""
    app = _dummy_app_with_components(n_components=4)
    app.component_kind = {idx: DummyVar("Sextete") for idx in range(1, 7)}
    app.vars = {}
    defaults = {
        "delta": 0.0,
        "quad": 0.0,
        "bhf": 33.0,
        "gamma1": 0.18,
        "gamma2": 1.0,
        "gamma3": 1.0,
        "depth": 0.01,
        "int1": 3.0,
        "int2": 2.0,
        "int3": 1.0,
    }
    for idx in range(1, 7):
        for name in SEXTET_PARAM_NAMES:
            app.vars[f"s{idx}_{name}"] = DummyVar(defaults[name])

    components, indices = app.build_bhf_sharp_components_from_active_components()

    assert indices == [1, 3, 4]
    assert len(components) == 3
    assert components[-1]["bhf"] == 33.0
