from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.fit_engine import Component, model_from_values  # noqa: E402
from core.physics import (  # noqa: E402
    doublet_absorption,
    lognormal_diameter_distribution,
    neel_log10_nu,
    relaxation_blume_tjon_two_state_absorption,
    relaxation_empirical_absorption,
    sextet_absorption,
)
from core.relaxation import GlobalRelaxationSpectrum, fit_neel_size_global  # noqa: E402


def test_empirical_relaxation_limits_match_sextet_and_area_scaled_doublet():
    v = np.linspace(-12.0, 12.0, 512)
    pars = dict(delta=0.25, quad=0.55, bhf=33.0, gamma1=0.32,
                gamma2=1.0, gamma3=1.0, depth=0.02,
                int1=3.0, int2=2.0, int3=1.0)
    sext = sextet_absorption(v, **pars)
    rel_slow = relaxation_empirical_absorption(v, blocked_fraction=1.0, **pars)
    assert np.allclose(rel_slow, sext)

    rel_fast = relaxation_empirical_absorption(v, blocked_fraction=0.0, **pars)
    doub = doublet_absorption(v, pars["delta"], pars["quad"], pars["gamma1"], pars["gamma2"], 1.0, pars["int1"], pars["int2"])
    assert np.corrcoef(rel_fast, doub)[0, 1] > 0.999
    area_sext = np.trapezoid(np.maximum(sext, 0.0), v)
    area_fast = np.trapezoid(np.maximum(rel_fast, 0.0), v)
    assert abs(area_fast / area_sext - 1.0) < 1e-10


def test_log10_nu_controls_phenomenological_relaxation_limit():
    v = np.linspace(-12.0, 12.0, 512)
    pars = dict(delta=0.25, quad=0.55, bhf=33.0, gamma1=0.32,
                gamma2=1.0, gamma3=1.0, depth=0.02,
                int1=3.0, int2=2.0, int3=1.0, blocked_fraction=1.0)
    slow = relaxation_empirical_absorption(v, log10_nu=5.0, **pars)
    fast = relaxation_empirical_absorption(v, log10_nu=11.0, **pars)
    sext = sextet_absorption(v, pars["delta"], pars["quad"], pars["bhf"],
                             pars["gamma1"], pars["gamma2"], pars["gamma3"],
                             pars["depth"], pars["int1"], pars["int2"], pars["int3"])
    doub = doublet_absorption(v, pars["delta"], pars["quad"], pars["gamma1"],
                              pars["gamma2"], 1.0, pars["int1"], pars["int2"])
    assert np.corrcoef(slow, sext)[0, 1] > 0.999
    assert np.corrcoef(fast, doub)[0, 1] > 0.999
    assert np.max(np.abs(slow - fast)) > 1e-3


def test_blume_tjon_two_state_has_slow_and_fast_limits():
    v = np.linspace(-12.0, 12.0, 512)
    pars = dict(delta=0.25, quad=0.55, bhf=33.0, gamma1=0.32,
                gamma2=1.0, gamma3=1.0, depth=0.02,
                int1=3.0, int2=2.0, int3=1.0)
    slow = relaxation_blume_tjon_two_state_absorption(v, log10_nu=4.0, **pars)
    fast = relaxation_blume_tjon_two_state_absorption(v, log10_nu=12.0, **pars)
    sext = sextet_absorption(v, pars["delta"], pars["quad"], pars["bhf"],
                             pars["gamma1"], pars["gamma2"], pars["gamma3"],
                             pars["depth"], pars["int1"], pars["int2"], pars["int3"])
    doub = doublet_absorption(v, pars["delta"], pars["quad"], pars["gamma1"],
                              pars["gamma2"], 1.0, pars["int1"], pars["int2"])
    assert np.corrcoef(slow, sext)[0, 1] > 0.99
    assert np.corrcoef(fast, doub)[0, 1] > 0.95
    assert np.max(np.abs(slow - fast)) > 1e-3


def test_neel_arrhenius_distribution_and_rate_are_physical():
    d, w = lognormal_diameter_distribution(8.0, 0.25, 15)
    assert d.size == w.size == 15
    assert np.isclose(np.sum(w), 1.0)
    lognu = neel_log10_nu(d, 300.0, 4.0, -9.0)
    # Partículas mayores relajan más despacio.
    assert lognu[0] > lognu[-1]


def test_neel_size_component_changes_with_temperature():
    v = np.linspace(-12.0, 12.0, 256)
    values = {
        "baseline": 1.0, "slope": 0.0,
        "s1_delta": 0.0, "s1_quad": 0.6, "s1_bhf": 33.0,
        "s1_gamma1": 0.32, "s1_gamma2": 1.0, "s1_gamma3": 1.0,
        "s1_depth": 0.02, "s1_int1": 3.0, "s1_int2": 2.0, "s1_int3": 1.0,
        "s1_neel_temp_k": 80.0, "s1_neel_log10_keff": 4.0,
        "s1_neel_mean_d_nm": 8.0, "s1_neel_sigma": 0.25,
        "s1_neel_log10_tau0": -9.0, "s1_neel_bins": 12.0,
    }
    comp = [Component(idx=1, enabled=True, kind="NeelSize")]
    low_t = model_from_values(v, values, comp)
    values["s1_neel_temp_k"] = 500.0
    high_t = model_from_values(v, values, comp)
    assert np.max(np.abs(low_t - high_t)) > 1e-4


def test_global_neel_size_fit_recovers_shared_diameter_from_synthetic_pair():
    v = np.linspace(-12.0, 12.0, 180)
    shared = {
        "delta": 0.0, "quad": 0.6, "bhf": 33.0,
        "gamma1": 0.32, "gamma2": 1.0, "gamma3": 1.0,
        "int1": 3.0, "int2": 2.0, "int3": 1.0,
        "neel_log10_keff": 4.0, "neel_mean_d_nm": 8.0,
        "neel_sigma": 0.25, "neel_log10_tau0": -9.0, "neel_bins": 10.0,
    }
    spectra = []
    for temp in (150.0, 350.0):
        vals = {"baseline": 1.0, "slope": 0.0, "depth": 0.02}
        y = model_from_values(
            v,
            {"baseline": 1.0, "slope": 0.0,
             "s1_delta": shared["delta"], "s1_quad": shared["quad"], "s1_bhf": shared["bhf"],
             "s1_gamma1": shared["gamma1"], "s1_gamma2": shared["gamma2"], "s1_gamma3": shared["gamma3"],
             "s1_depth": vals["depth"], "s1_int1": shared["int1"], "s1_int2": shared["int2"], "s1_int3": shared["int3"],
             "s1_neel_temp_k": temp, "s1_neel_log10_keff": shared["neel_log10_keff"],
             "s1_neel_mean_d_nm": shared["neel_mean_d_nm"], "s1_neel_sigma": shared["neel_sigma"],
             "s1_neel_log10_tau0": shared["neel_log10_tau0"], "s1_neel_bins": shared["neel_bins"]},
            [Component(idx=1, enabled=True, kind="NeelSize")],
        )
        spectra.append(GlobalRelaxationSpectrum(v, y, temp, np.ones_like(v) * 1e-4))
    res = fit_neel_size_global(
        spectra,
        shared_initial={**shared, "neel_mean_d_nm": 7.5},
        fixed_shared={"delta", "quad", "bhf", "gamma1", "gamma2", "gamma3", "int1", "int2", "int3", "neel_log10_keff", "neel_sigma", "neel_log10_tau0", "neel_bins"},
        fixed_local={"baseline", "slope"},
        max_nfev=200,
    )
    assert res.success
    assert abs(res.shared["neel_mean_d_nm"] - 8.0) < 0.2


def test_model_from_values_uses_relaxation_fraction():
    v = np.linspace(-12.0, 12.0, 256)
    values = {
        "baseline": 1.0, "slope": 0.0,
        "s1_delta": 0.0, "s1_quad": 0.6, "s1_bhf": 33.0,
        "s1_gamma1": 0.32, "s1_gamma2": 1.0, "s1_gamma3": 1.0,
        "s1_depth": 0.02, "s1_int1": 3.0, "s1_int2": 2.0, "s1_int3": 1.0,
        "s1_relax_fraction": 1.0, "s1_relax_log_nu": 5.0,
    }
    comp = [Component(idx=1, enabled=True, kind="Relajacion")]
    slow = model_from_values(v, values, comp)
    values["s1_relax_fraction"] = 0.0
    fast = model_from_values(v, values, comp)
    assert np.max(np.abs(slow - fast)) > 1e-3
