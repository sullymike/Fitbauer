from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gui.fit_workflow import FitWorkflowMixin, GuiFitRenderState
from gui.state import PlotViewState, UiActionState


class DummyCanvas:
    def __init__(self):
        self.calls = []

    def render(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class DummyWindow(FitWorkflowMixin):
    def __init__(self):
        self.plot_style_name = "classic"
        self.canvas = DummyCanvas()

    def _ui_action_state(self):
        return UiActionState(
            n_components=1,
            plot=PlotViewState(show_residual=False, show_legend=True),
        )

    def statusBar(self):  # pragma: no cover - no se usa en este test
        raise AssertionError("No debería usarse")


def test_render_fit_result_forwards_state_and_ui_flags():
    win = DummyWindow()
    v = np.array([-1.0, 0.0, 1.0])
    y = np.array([1.0, 0.9, 1.0])
    model = np.array([0.99, 0.91, 0.99])
    residual = y - model

    win._render_fit_result(GuiFitRenderState(
        velocity=v,
        y_data=y,
        model=model,
        residual=residual,
        components=[(1, "Singlete", model)],
    ))

    assert len(win.canvas.calls) == 1
    args, kwargs = win.canvas.calls[0]
    assert np.allclose(args[0], v)
    assert np.allclose(args[1], y)
    assert np.allclose(kwargs["model"], model)
    assert kwargs["components"][0][1] == "Singlete"
    assert kwargs["show_residual"] is False
    assert kwargs["show_legend"] is True
    assert kwargs["style_name"] == "classic"
