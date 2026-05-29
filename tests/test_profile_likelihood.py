"""Tests del módulo de verosimilitud perfilada."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.profile_likelihood import asymmetric_intervals, find_crossing  # noqa: E402


def _parabola(x, x0, sigma):
    """Δχ²(x) = ((x − x0)/σ)²."""
    return ((x - x0) / sigma) ** 2


def test_find_crossing_on_symmetric_parabola():
    x0, sigma = 1.0, 0.2
    x = np.linspace(x0 - 1.0, x0 + 1.0, 401)
    d = _parabola(x, x0, sigma)
    minus, plus = find_crossing(x, d, x0, level=1.0)
    assert abs(plus - sigma) < 5e-3
    assert abs(minus - sigma) < 5e-3


def test_asymmetric_intervals_recover_sigma_and_2sigma():
    x0, sigma = -3.5, 0.05
    x = np.linspace(x0 - 0.4, x0 + 0.4, 801)
    d = _parabola(x, x0, sigma)
    intervals = asymmetric_intervals(x, d, x0)
    assert abs(intervals["plus_1s"] - sigma) < 1e-3
    assert abs(intervals["minus_1s"] - sigma) < 1e-3
    assert abs(intervals["plus_2s"] - 2 * sigma) < 1e-3
    assert abs(intervals["minus_2s"] - 2 * sigma) < 1e-3


def test_one_sided_when_scan_does_not_reach_level():
    # La curva sube a la derecha pero queda plana a la izquierda dentro del barrido.
    x = np.linspace(0.0, 1.0, 201)
    x0 = 0.1
    d = np.where(x > x0, ((x - x0) / 0.2) ** 2, 0.0)
    minus, plus = find_crossing(x, d, x0, level=1.0)
    assert plus is not None and abs(plus - 0.2) < 5e-3
    # Nunca cruza Δχ²=1 a la izquierda dentro del barrido.
    assert minus is None


def test_asymmetric_curve():
    # Curva más empinada por la derecha: σ_izq = 0.30, σ_der = 0.10.
    x = np.linspace(-1.0, 1.0, 1001)
    x0 = 0.0
    d = np.where(x >= x0, ((x - x0) / 0.10) ** 2, ((x - x0) / 0.30) ** 2)
    intervals = asymmetric_intervals(x, d, x0)
    assert abs(intervals["plus_1s"] - 0.10) < 5e-3
    assert abs(intervals["minus_1s"] - 0.30) < 5e-3
