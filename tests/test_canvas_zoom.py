"""Regresión: el canvas no debe quedarse 'congelado' tras un zoom.

Un zoom/desplazamiento con la barra de Matplotlib desactiva el autoescalado.
El refresco incremental (``_update_fast``) reutiliza los ejes, así que un
espectro nuevo con el mismo nº de canales se dibujaba fuera de la vista.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
    from gui.canvas import SpectrumCanvas
    from core.plot_styles import get_style
except Exception as exc:  # pragma: no cover
    pytest.skip(f"PySide6 / canvas no disponible: {exc}", allow_module_level=True)


V = np.linspace(-10, 10, 256)


def _spec(scale: float) -> np.ndarray:
    return scale * (1 - 0.1 * np.exp(-V ** 2))


@pytest.fixture
def canvas(qtbot):
    c = SpectrumCanvas()
    qtbot.addWidget(c)
    tb = NavigationToolbar2QT(c, None)
    c.render(V, _spec(1.0), style=get_style("classic"), style_name="classic")
    c.draw()
    return c, tb


def _zoom(c, tb, ylim):
    tb.push_current()
    c.ax.set_xlim(-2, 2)
    c.ax.set_ylim(*ylim)
    tb.push_current()


def test_new_spectrum_after_zoom_is_visible(canvas):
    c, tb = canvas
    _zoom(c, tb, (0.9, 0.95))
    y = _spec(1e5)
    c.render(V, y, style=get_style("classic"), style_name="classic")
    lo, hi = c.ax.get_ylim()
    assert lo <= y.min() and hi >= y.max()
    assert c.ax.get_xlim()[0] <= V.min()
    assert len(tb._nav_stack) == 0


def test_model_only_update_keeps_user_zoom(canvas):
    c, tb = canvas
    y = _spec(1.0)
    c.render(V, y, model=y * 1.001, style=get_style("classic"), style_name="classic")
    _zoom(c, tb, (0.9, 0.95))
    c.render(V, y, model=y * 1.002, style=get_style("classic"), style_name="classic")
    assert c.ax.get_xlim() == pytest.approx((-2, 2))
    assert c.ax.get_ylim() == pytest.approx((0.9, 0.95))
