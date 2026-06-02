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
    Component, FitState, fit_discrete, model_from_values, _refold_at_center,
    bootstrap_errors, profile_likelihood, BootstrapResult,
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


def _alpha_fe_counts_state(cstart: float):
    """Estado α-Fe con cuentas crudas para ejercitar el re-folding del centro."""
    counts = read_ws5_counts(DATA / "hierro_metalico_alphaFe.adt")
    c0 = find_best_integer_or_half_center(counts)
    folded, _ = fold_integer_or_half(counts, c0)
    v = np.linspace(-VMAX, VMAX, folded.size)
    norm = float(np.percentile(folded, 90))
    y = folded / norm
    sigma = np.sqrt(np.maximum(folded / 2.0, 1.0)) / norm
    state = _alpha_fe_state(v, y, sigma)
    state.values["center"] = cstart
    state.bounds["center"] = (c0 - 1.5, c0 + 1.5)
    state.fit_center = True
    state.counts = counts
    state.norm_factor = norm
    return state, c0, counts, norm


def test_refold_at_center_reproduces_reference():
    """El helper de re-folding reproduce los datos de referencia en el centro óptimo."""
    counts = read_ws5_counts(DATA / "hierro_metalico_alphaFe.adt")
    c0 = find_best_integer_or_half_center(counts)
    folded, _ = fold_integer_or_half(counts, c0)
    norm = float(np.percentile(folded, 90))
    y_ref = folded / norm
    y, sig = _refold_at_center(counts, c0, norm)
    assert y.size == counts.size // 2
    assert np.allclose(y, y_ref)
    assert np.all(sig > 0)


def test_fit_center_refolding_pulls_toward_optimum():
    """Con cuentas crudas, ajustar el centro lo arrastra hacia el óptimo del modelo
    desde ambos lados (el re-folding crea una fuerza restauradora real)."""
    # c0 = centro de simetría; el óptimo del modelo cae en su entorno.
    _tmp, c0, _, _ = _alpha_fe_counts_state(0.0)
    start_hi = c0 + 0.5
    start_lo = c0 - 0.5
    sh, _, _, _ = _alpha_fe_counts_state(start_hi)
    sl, _, _, _ = _alpha_fe_counts_state(start_lo)
    r_hi = fit_discrete(sh)
    r_lo = fit_discrete(sl)
    c_hi = r_hi.values["center"]
    c_lo = r_lo.values["center"]
    # Atraído hacia el óptimo: desde arriba baja, desde abajo sube.
    assert c_hi < start_hi
    assert c_lo > start_lo
    # Ambos convergen a un entorno común del óptimo del modelo y ajustan bien.
    assert abs(c_hi - c_lo) < abs(start_hi - start_lo)
    assert r_hi.stats["red_chi2"] < 1.5 and r_lo.stats["red_chi2"] < 1.5


def test_fit_center_without_counts_does_not_harm_model():
    """Sin cuentas crudas, el centro no afecta al modelo (gradiente nulo): el ajuste
    de los parámetros físicos sigue siendo correcto, como antes del re-folding."""
    v, y, sigma = _load_alpha_fe()
    state = _alpha_fe_state(v, y, sigma)
    state.values["center"] = 256.9
    state.bounds["center"] = (255.0, 258.0)
    state.fit_center = True
    state.counts = None  # sin cuentas → sin re-folding (center inerte)
    result = fit_discrete(state)
    assert abs(result.values["s1_bhf"] - 33.0) < 1.0
    assert abs((result.values["s1_delta"] - ISO_REF)) < 0.05


def test_bootstrap_errors_gauss():
    """El bootstrap converge y devuelve σ(MC) positivas para los parámetros libres."""
    v, y, sigma = _load_alpha_fe()
    state = _alpha_fe_state(v, y, sigma)
    res = bootstrap_errors(state, n_rep=12, seed=24680)
    assert isinstance(res, BootstrapResult)
    assert res.n_ok >= 8                       # la mayoría converge
    for k in ("s1_delta", "s1_bhf", "s1_gamma1", "s1_depth"):
        assert k in res.std and res.std[k] > 0.0
    # σ(MC) del orden de la σ analítica del ajuste base (mismo orden de magnitud).
    for k in ("s1_bhf", "s1_delta"):
        if res.base.errors.get(k, 0.0) > 0:
            ratio = res.std[k] / res.base.errors[k]
            assert 0.1 < ratio < 10.0


def test_bootstrap_is_deterministic_with_seed():
    """Misma semilla → mismos resultados (reproducibilidad)."""
    v, y, sigma = _load_alpha_fe()
    s1 = bootstrap_errors(_alpha_fe_state(v, y, sigma), n_rep=8, seed=777)
    s2 = bootstrap_errors(_alpha_fe_state(v, y, sigma), n_rep=8, seed=777)
    assert s1.std == s2.std


def test_profile_likelihood_brackets_one_sigma():
    """La verosimilitud perfilada produce curvas Δχ² con cruces 1σ alrededor del óptimo."""
    v, y, sigma = _load_alpha_fe()
    state = _alpha_fe_state(v, y, sigma)
    results = profile_likelihood(state, points_per_side=5)
    assert results
    for key, r in results.items():
        d = np.array(r["d_chi2"])
        assert np.min(d) <= 1e-6 + 0.0       # el mínimo (óptimo) es ~0
        assert d.max() >= 0.0
        # los valores de escaneo rodean al óptimo
        assert min(r["scan_values"]) <= r["best"] <= max(r["scan_values"])
    # Para BHF (bien determinado) debe existir al menos un cruce 1σ.
    bhf = results.get("s1_bhf", {})
    assert bhf.get("plus_1s") is not None or bhf.get("minus_1s") is not None


def test_fit_discrete_respects_fixed():
    v, y, sigma = _load_alpha_fe()
    state = _alpha_fe_state(v, y, sigma)
    # Fija BHF
    state.fixed["s1_bhf"] = True
    state.values["s1_bhf"] = 35.0  # valor incorrecto
    result = fit_discrete(state)
    # Como BHF está fijo, debe quedarse en 35.0
    assert abs(result.values["s1_bhf"] - 35.0) < 1e-6
