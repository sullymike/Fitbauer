"""Integración: folding de ADT + recuperación de parámetros por ajuste.

Usa exclusivamente ``core`` (folding + physics); no depende de ninguna GUI ni
de Tk.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.optimize import curve_fit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.physics as physics  # noqa: E402
from core.folding import (  # noqa: E402
    find_best_integer_or_half_center,
    fold_integer_or_half,
    read_ws5_counts,
)

DATA = ROOT / "data_sample"
VMAX = 12.007
ISO_REF = -0.1092


def _load_folded(name: str):
    counts = read_ws5_counts(DATA / name)
    center = find_best_integer_or_half_center(counts)
    folded, _pairs = fold_integer_or_half(counts, center)
    v = np.linspace(-VMAX, VMAX, folded.size)
    y = folded / np.percentile(folded, 90)
    return v, y, center, counts


def test_adt_has_512_channels():
    counts = read_ws5_counts(DATA / "hierro_metalico_alphaFe.adt")
    assert counts.size == 512


def test_folding_center_near_256_5():
    _v, _y, center, counts = _load_folded("hierro_metalico_alphaFe.adt")
    assert counts.size == 512
    assert abs(center - 256.5) < 0.6


def test_fit_alpha_fe_recovers_bhf_and_corrected_iso():
    v, y, _c, _ = _load_folded("hierro_metalico_alphaFe.adt")
    physics.LINE_PROFILE_KIND = "Lorentziana"

    def model(v, base, delta, bhf, gamma, depth):
        return base - physics.sextet_absorption(
            v, delta, 0.0, bhf, gamma, 1.0, 1.0, depth, 3.0, 2.0, 1.0)

    p0 = [1.0, -0.1, 33.0, 0.15, 0.013]
    bounds = ([0.9, -2.0, 20.0, 0.05, 0.0], [1.1, 3.0, 60.0, 1.0, 0.3])
    popt, _ = curve_fit(model, v, y, p0=p0, bounds=bounds, maxfev=20000)
    delta, bhf = popt[1], popt[2]
    assert abs(bhf - 33.0) < 1.0
    assert abs((delta - ISO_REF) - 0.0) < 0.05   # δ corregido ≈ 0 (α-Fe)


def test_fit_hematite_allows_high_bhf_and_negative_quad():
    v, y, _c, _ = _load_folded("hematita_Fe2O3.adt")
    physics.LINE_PROFILE_KIND = "Lorentziana"

    def model(v, base, delta, quad, bhf, gamma, depth):
        return base - physics.sextet_absorption(
            v, delta, quad, bhf, gamma, 1.0, 1.0, depth, 3.0, 2.0, 1.0)

    p0 = [1.0, 0.26, -0.2, 50.0, 0.16, 0.012]
    bounds = ([0.9, -2.0, -4.0, 20.0, 0.05, 0.0],
              [1.1, 3.0, 4.0, 60.0, 1.0, 0.3])
    popt, _ = curve_fit(model, v, y, p0=p0, bounds=bounds, maxfev=20000)
    delta, quad, bhf = popt[1], popt[2], popt[3]
    assert bhf > 50.0                              # campo alto alcanzable
    assert quad < 0.0                              # cuadrupolo negativo
    assert abs((delta - ISO_REF) - 0.37) < 0.05    # δ corregido ≈ 0.37


def test_voigt_sigma_fit_drives_sigma_small_on_lorentzian_data():
    # Datos sintéticos lorentzianos puros → el σ gaussiano debe quedar pequeño.
    v, y, _c, _ = _load_folded("hematita_Fe2O3.adt")
    physics.LINE_PROFILE_KIND = "Voigt"

    def model(v, base, delta, quad, bhf, gamma, depth, sigma):
        physics.VOIGT_SIGMA = max(sigma, 1e-9)
        return base - physics.sextet_absorption(
            v, delta, quad, bhf, gamma, 1.0, 1.0, depth, 3.0, 2.0, 1.0)

    p0 = [1.0, 0.26, -0.2, 51.0, 0.12, 0.012, 0.10]
    bounds = ([0.9, -2.0, -4.0, 20.0, 0.03, 0.0, 0.0],
              [1.1, 3.0, 4.0, 60.0, 1.0, 0.3, 1.0])
    popt, _ = curve_fit(model, v, y, p0=p0, bounds=bounds, maxfev=20000)
    sigma = popt[6]
    assert sigma < 0.10
    physics.LINE_PROFILE_KIND = "Lorentziana"
