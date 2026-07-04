"""Detección de la esquina de la L-curve (criterio de máxima curvatura)."""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from gui.distribution_fit import _lcurve_corner_index


def test_corner_is_in_the_transition_region():
    """La esquina cae en la zona de transición, no en los extremos del barrido."""
    alphas = np.logspace(-6, 2, 25)
    rough = 1.0 / (alphas ** 0.4) + 0.05          # α chico → mucha rugosidad
    resid = 0.01 + alphas ** 0.6                   # α grande → mucho residuo
    idx = _lcurve_corner_index(rough, resid)
    assert 0 < idx < len(alphas) - 1


def test_sharp_corner_recovered():
    """Una L con codo recto se detecta exactamente en ese codo."""
    # Construida en log-log: primero cae el residuo (rama vertical), luego cae
    # la rugosidad (rama horizontal). El ángulo recto está en el índice 4.
    logx = np.array([0, 0, 0, 0, 0, -1, -2, -3, -4], dtype=float)  # log rugosidad
    logy = np.array([4, 3, 2, 1, 0, 0, 0, 0, 0], dtype=float)      # log residuo
    idx = _lcurve_corner_index(np.exp(logx), np.exp(logy))
    assert idx == 4


def test_degenerate_inputs_return_zero():
    assert _lcurve_corner_index(np.array([]), np.array([])) == 0
    assert _lcurve_corner_index(np.array([1.0, 2.0]), np.array([1.0, 2.0])) == 0


def test_non_positive_points_are_ignored():
    """Ceros/NaN no válidos para el log se descartan sin romper el índice."""
    rough = np.array([0.0, np.nan, 3.0, 2.0, 1.0])
    resid = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    idx = _lcurve_corner_index(rough, resid)
    assert 0 <= idx < rough.size
    assert np.isfinite(rough[idx]) and rough[idx] > 0


from gui.distribution_fit import _lcurve_pick_index


def test_pick_on_alpha_axis_snaps_to_nearest_alpha():
    """Un clic sobre la gráfica α↔RMS elige el α escaneado más cercano."""
    alphas = np.logspace(-4, 4, 9)          # 10^-4 … 10^4
    rough = np.linspace(5, 1, 9)
    resid = np.linspace(1, 5, 9)
    # Clic cerca de α=10^2 → índice 6.
    assert _lcurve_pick_index("alpha", 10 ** 2.1, None, rough, resid, alphas) == 6
    # Clic cerca de α=10^-4 → índice 0.
    assert _lcurve_pick_index("alpha", 10 ** -3.9, None, rough, resid, alphas) == 0


def test_pick_on_lcurve_uses_loglog_distance():
    """Un clic sobre la L elige el punto (rough, resid) más próximo en log-log."""
    alphas = np.logspace(-4, 4, 5)
    rough = np.array([100.0, 30.0, 10.0, 3.0, 1.0])
    resid = np.array([1.0, 1.2, 2.0, 4.0, 8.0])
    # Clic junto al 3er punto (10, 2.0).
    idx = _lcurve_pick_index("lcurve", 11.0, 2.1, rough, resid, alphas)
    assert idx == 2


def test_pick_degenerate_returns_zero():
    assert _lcurve_pick_index("alpha", None, None, [], [], []) == 0
    assert _lcurve_pick_index("lcurve", 1.0, 1.0, [], [], []) == 0
