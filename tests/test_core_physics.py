"""Tests de la física pura (core.*), sin dependencias de GUI/Tk."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.physics as physics  # noqa: E402
from core.constants import (  # noqa: E402
    BHF_DEFAULT_T,
    LINE_POS_33T,
    fe57_sextet_positions,
)


@pytest.fixture(autouse=True)
def _reset_profile():
    """Restaura el perfil global tras cada test."""
    kind, sigma = physics.LINE_PROFILE_KIND, physics.VOIGT_SIGMA
    yield
    physics.LINE_PROFILE_KIND, physics.VOIGT_SIGMA = kind, sigma


def _fwhm(v, y):
    half = v[y >= 0.5 * y.max()]
    return float(half[-1] - half[0])


def test_lorentzian_peak_and_fwhm():
    physics.LINE_PROFILE_KIND = "Lorentziana"
    v = np.linspace(-5, 5, 40001)
    y = physics.lorentzian(v, 0.0, 0.4)
    assert abs(y.max() - 1.0) < 1e-9
    assert abs(_fwhm(v, y) - 0.4) < 5e-3  # FWHM = gamma


def test_voigt_peak_normalized_and_broader():
    v = np.linspace(-5, 5, 40001)
    physics.LINE_PROFILE_KIND = "Lorentziana"
    fwhm_lor = _fwhm(v, physics.lorentzian(v, 0.0, 0.4))
    physics.LINE_PROFILE_KIND = "Voigt"
    physics.VOIGT_SIGMA = 0.15
    yv = physics.lorentzian(v, 0.0, 0.4)
    assert abs(yv.max() - 1.0) < 1e-6           # normalizado a pico 1
    assert _fwhm(v, yv) > fwhm_lor               # la gaussiana ensancha


def test_sextet_symmetric_when_quad_zero():
    physics.LINE_PROFILE_KIND = "Lorentziana"
    delta = 0.25
    v = delta + np.linspace(-8, 8, 20001)
    y = physics.sextet_absorption(v, delta, 0.0, 33.0, 0.4, 1.0, 1.0,
                                  0.1, 3.0, 2.0, 1.0)
    assert np.allclose(y, y[::-1], atol=1e-9)    # simétrico respecto a delta


def test_doublet_symmetric_about_delta():
    physics.LINE_PROFILE_KIND = "Lorentziana"
    delta = 0.4
    v = delta + np.linspace(-3, 3, 20001)
    y = physics.doublet_absorption(v, delta, 0.9, 0.4, 1.0, 0.1, 1.0, 1.0)
    assert np.allclose(y, y[::-1], atol=1e-9)


def test_total_model_without_components_is_baseline_plus_slope():
    v = np.linspace(-10, 10, 501)
    y = physics.total_model(v, 1.05, -3e-4, [])
    assert np.allclose(y, 1.05 - 3e-4 * v)


def test_sextet_positions_symmetric_and_scaling():
    pos = fe57_sextet_positions(BHF_DEFAULT_T)
    assert pos.shape == (6,)
    assert np.all(np.diff(pos) > 0)              # ordenadas crecientes
    assert np.allclose(pos, -pos[::-1], atol=1e-9)  # simétricas respecto a 0
    assert np.allclose(LINE_POS_33T, pos)
    # Las posiciones escalan linealmente con el campo.
    assert np.allclose(fe57_sextet_positions(66.0), 2.0 * pos, rtol=1e-6)
