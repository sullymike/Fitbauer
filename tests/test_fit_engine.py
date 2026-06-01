"""Tests del motor de ajuste puro (core/fit_engine.py).

Verifica que el motor reproduce los parámetros esperados sobre los espectros
sintéticos sin necesidad de instanciar la GUI Tk.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.folding import (  # noqa: E402
    read_ws5_counts, find_best_integer_or_half_center, fold_integer_or_half,
)
from core.fit_engine import (  # noqa: E402
    Component, FitState, fit_discrete, model_from_values,
)

DATA = ROOT / "data_sample"
VMAX = 12.007
ISO_REF = -0.1092


def _load_alpha_fe():
    counts = read_ws5_counts(DATA / "hierro_metalico_alphaFe.adt")
    center = find_best_integer_or_half_center(counts)
    folded, _ = fold_integer_or_half(counts, center)
    v = np.linspace(-VMAX, VMAX, folded.size)
    y = folded / np.percentile(folded, 90)
    sigma = np.sqrt(np.maximum(folded / 2.0, 1.0)) / np.percentile(folded, 90)
    return v, y, sigma


def _alpha_fe_state(v, y, sigma):
    values = {
        "baseline": 1.0,
        "slope": 0.0,
        "vmax": VMAX,
        "voigt_sigma": 0.05,
        "s1_delta": -0.1,
        "s1_quad": 0.0,
        "s1_bhf": 33.0,
        "s1_gamma1": 0.14,
        "s1_gamma2": 1.0,
        "s1_gamma3": 1.0,
        "s1_depth": 0.013,
        "s1_int1": 3.0,
        "s1_int2": 2.0,
        "s1_int3": 1.0,
    }
    fixed = {k: False for k in values}
    # Fijos típicos para α-Fe
    for k in ("s1_int1", "s1_int2", "s1_int3", "s1_gamma2", "s1_gamma3", "s1_quad"):
        fixed[k] = True
    bounds = {
        "baseline": (0.70, 1.30), "slope": (-0.005, 0.005),
        "s1_delta": (-2.0, 3.0), "s1_quad": (-4.0, 4.0),
        "s1_bhf": (0.0, 60.0), "s1_gamma1": (0.03, 2.0),
        "s1_gamma2": (0.2, 3.0), "s1_gamma3": (0.2, 3.0),
        "s1_depth": (0.0, 0.30), "s1_int1": (0.0, 9.0),
        "s1_int2": (0.0, 6.0), "s1_int3": (0.0, 3.0),
        "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0),
    }
    components = [Component(idx=1, enabled=True, kind="Sextete")]
    return FitState(
        velocity=v, y_data=y, sigma_data=sigma,
        values=values, fixed=fixed, bounds=bounds,
        components=components,
    )


def test_model_from_values_returns_baseline_for_disabled_components():
    v = np.linspace(-12, 12, 256)
    state_vals = {"baseline": 1.05, "slope": 0.0}
    out = model_from_values(v, state_vals, components=[])
    assert np.allclose(out, 1.05)


def test_fit_discrete_recovers_alpha_fe():
    v, y, sigma = _load_alpha_fe()
    state = _alpha_fe_state(v, y, sigma)
    result = fit_discrete(state)
    assert result.success or result.values  # debe converger
    bhf = result.values["s1_bhf"]
    delta = result.values["s1_delta"]
    assert abs(bhf - 33.0) < 1.0
    assert abs((delta - ISO_REF) - 0.0) < 0.05    # δ corregido ≈ 0
    assert result.stats["red_chi2"] is not None
    # Errores 1σ disponibles para los parámetros libres
    for k in ("s1_delta", "s1_bhf", "s1_gamma1", "s1_depth"):
        assert k in result.errors and result.errors[k] >= 0.0


def test_fit_discrete_respects_fixed():
    v, y, sigma = _load_alpha_fe()
    state = _alpha_fe_state(v, y, sigma)
    # Fija BHF
    state.fixed["s1_bhf"] = True
    state.values["s1_bhf"] = 35.0  # valor incorrecto
    result = fit_discrete(state)
    # Como BHF está fijo, debe quedarse en 35.0
    assert abs(result.values["s1_bhf"] - 35.0) < 1e-6
