"""Zoom acoplado por α entre las dos figuras del diálogo de L-curve."""
import numpy as np
import pytest

pytest.importorskip("PySide6")
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from gui.distribution_fit import _couple_lcurve_zoom


def _build():
    alphas = np.logspace(-6, 2, 20)
    rough = 1.0 / (alphas ** 0.4) + 0.05        # decrece con α
    resid = 0.01 + alphas ** 0.6                 # crece con α
    rms = resid / np.sqrt(alphas.size)
    fig = Figure()
    cv = FigureCanvasAgg(fig)
    ax1 = fig.add_subplot(1, 2, 1)
    ax1.loglog(rough, resid, "o-")
    ax2 = fig.add_subplot(1, 2, 2)
    ax2.semilogx(alphas, rms, "o-")
    fig.canvas.draw()
    return cv, ax1, ax2, rough, resid, alphas, rms


def test_zoom_on_alpha_axis_limits_the_lcurve():
    cv, ax1, ax2, rough, resid, alphas, rms = _build()
    _couple_lcurve_zoom(cv, ax1, ax2, rough, resid, alphas, rms)
    # Zoom en la figura derecha a una ventana estrecha de α.
    lo, hi = 1e-3, 1e-1
    ax2.set_xlim(lo, hi)  # dispara el callback acoplado
    mask = (alphas >= lo) & (alphas <= hi)
    x0, x1 = sorted(ax1.get_xlim())
    # La figura izquierda debe cubrir (con margen) el rough de esos α y nada más.
    assert x0 <= rough[mask].min() <= rough[mask].max() <= x1
    assert x1 < rough.max()          # se ha recortado respecto al rango completo


def test_zoom_on_lcurve_limits_the_alpha_axis():
    cv, ax1, ax2, rough, resid, alphas, rms = _build()
    _couple_lcurve_zoom(cv, ax1, ax2, rough, resid, alphas, rms)
    lo, hi = sorted((rough[5], rough[12]))
    ax1.set_xlim(lo, hi)
    mask = (rough >= lo) & (rough <= hi)
    a0, a1 = sorted(ax2.get_xlim())
    assert a0 <= alphas[mask].min() <= alphas[mask].max() <= a1


def test_no_infinite_recursion_and_degenerate_guard():
    cv, ax1, ax2, rough, resid, alphas, rms = _build()
    _couple_lcurve_zoom(cv, ax1, ax2, rough, resid, alphas, rms)
    # No debe colgarse (el cerrojo de reentrada corta el ping-pong).
    ax2.set_xlim(1e-4, 1e0)
    ax1.set_xlim(rough.min(), rough.max())
    # Menos de 2 puntos: no engancha callbacks, no lanza.
    _couple_lcurve_zoom(cv, ax1, ax2, rough[:1], resid[:1], alphas[:1], rms[:1])
