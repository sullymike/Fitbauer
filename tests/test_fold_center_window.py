"""Punto de plegado relativo a N/2: vale para 512, 1024 o 256 canales.

El límite del centro era fijo (250–263, solo válido para 512 canales) y con
1024 canales el control de la GUI recortaba el centro (~512) a 263. Ahora el
margen es relativo a N/2 y ajustable en Parámetros (por defecto ±20).
"""
from __future__ import annotations

import json

import numpy as np
import pytest

import core.param_overrides as po
from core.folding import (
    FOLD_CENTER_MARGIN, detect_fold_center, fold_center_window, triangular_velocity_axis,
)
from core.session import HeadlessSession


def _raw(n: int, center: float, seed: int = 5) -> np.ndarray:
    v = triangular_velocity_axis(n, 6.0, center)
    g = 0.15 ** 2
    t = 1 - sum(0.1 * g / ((v - x) ** 2 + g) for x in (-0.1, 0.9))
    return np.random.default_rng(seed).poisson(4e5 * t).astype(float)


@pytest.fixture
def limits(tmp_path, monkeypatch):
    path = tmp_path / "param_limits.json"
    monkeypatch.setattr(po, "PARAM_LIMITS_PATH", path)

    def _write(lo, hi):
        path.write_text(json.dumps({"calibration": {"center": {"lo": lo, "hi": hi}}}))
    return _write


def test_window_scales_with_channels(limits):
    assert fold_center_window(512) == (256 - FOLD_CENTER_MARGIN, 256 + FOLD_CENTER_MARGIN)
    assert fold_center_window(1024) == (492.0, 532.0)
    assert fold_center_window(1024, drive_form="sine") == (0.05 * 1024, 0.45 * 1024)
    limits(-5, 8)                                     # margen ajustable, asimétrico
    assert fold_center_window(1024) == (507.0, 520.0)


def test_old_absolute_limits_are_ignored(limits):
    limits(250.0, 263.0)                              # límites absolutos de antes
    assert fold_center_window(1024) == (492.0, 532.0)
    assert po.effective_calibration_specs()["center"].lo == -20.0


@pytest.mark.parametrize("n, center", [(1024, 512.3), (512, 255.8), (256, 128.4)])
def test_detection_any_channel_count(n, center):
    assert detect_fold_center(_raw(n, center)) == pytest.approx(center, abs=0.15)


def test_headless_1024_fit_center_bounds(tmp_path):
    p = tmp_path / "raw1024.txt"
    p.write_text("\n".join(f"{x:.0f}" for x in _raw(1024, 512.3)))
    s = HeadlessSession()
    s.model.fit_center = True
    s.load_ws5(p)
    assert s.spectrum.center == pytest.approx(512.3, abs=0.15)
    state = s.build_fit_state()
    assert state.bounds["center"] == (492.0, 532.0)


def test_gui_1024_center_not_clipped(qapp, tmp_path):
    pytest.importorskip("pytestqt")
    import mossbauer_qt as mq
    win = mq.MossbauerQtWindow()
    try:
        p = tmp_path / "raw1024.txt"
        p.write_text("\n".join(f"{x:.0f}" for x in _raw(1024, 512.3)))
        win._load_file(p)
        assert win.calib.center.value() == pytest.approx(512.3, abs=0.15)
        assert win.file.center == pytest.approx(win.calib.center.value(), abs=1e-3)
        # Y de vuelta a 512 canales, el rango se adapta.
        p2 = tmp_path / "raw512.txt"
        p2.write_text("\n".join(f"{x:.0f}" for x in _raw(512, 255.8)))
        win._load_file(p2)
        assert win.calib.center.value() == pytest.approx(255.8, abs=0.15)
    finally:
        win.close()
        win.deleteLater()
