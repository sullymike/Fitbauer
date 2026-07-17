"""Tests de equivalencia numérica entre core.physics y mossbauer_distribution.

Fijan el comportamiento EXACTO de los perfiles de absorción antes de unificar
las dos familias (convención core: pesos int1/int2/int3 explícitos; convención
distribución: gamma2_rel/int2_rel con los factores 2/3 y 1/3 horneados). Las
funciones ``_ref_*`` son copias literales de las implementaciones duplicadas
previas a la unificación (v4.14.3): si un refactor cambia la física, estos
tests lo detectan con tolerancia estricta.
"""
from __future__ import annotations

import numpy as np
import pytest

import core.physics as phys
from core.constants import BHF_DEFAULT_T, LINE_POS_33T, LINE_QUAD_PATTERN
from core.physics import lorentzian, two_state_exchange_profile
import mossbauer_distribution as dist


V = np.linspace(-11.0, 11.0, 401)

# Rejilla de parámetros: casos típicos y degenerados (quad<0, bhf=0, pesos 0).
SEXTET_CASES = [
    dict(delta=0.0, quad=0.0, bhf=33.0, gamma=0.25, gamma2_rel=1.0, gamma3_rel=1.0,
         int1=1.0, int2_rel=1.0, int3_rel=1.0),
    dict(delta=0.35, quad=-0.2, bhf=45.7, gamma=0.30, gamma2_rel=1.2, gamma3_rel=0.8,
         int1=0.9, int2_rel=0.7, int3_rel=1.3),
    dict(delta=-0.1, quad=0.6, bhf=12.0, gamma=0.18, gamma2_rel=1.0, gamma3_rel=1.0,
         int1=1.0, int2_rel=0.0, int3_rel=1.0),
    dict(delta=0.0, quad=0.0, bhf=0.0, gamma=0.25, gamma2_rel=1.0, gamma3_rel=1.0,
         int1=1.0, int2_rel=1.0, int3_rel=0.0),
]

DOUBLET_CASES = [
    dict(delta=0.3, quad=0.8, gamma=0.25, gamma2_rel=1.0, int1=1.0, int2_rel=1.0),
    dict(delta=-0.2, quad=1.9, gamma=0.32, gamma2_rel=1.4, int1=0.8, int2_rel=0.6),
    dict(delta=0.0, quad=0.0, gamma=0.20, gamma2_rel=1.0, int1=1.0, int2_rel=0.0),
]

RELAX_CASES = [
    dict(blocked_fraction=1.0, log10_nu=None),
    dict(blocked_fraction=0.5, log10_nu=None),
    dict(blocked_fraction=1.0, log10_nu=5.0),
    dict(blocked_fraction=1.0, log10_nu=8.5),
    dict(blocked_fraction=0.8, log10_nu=12.0),
]


# ── Referencias: copias literales de las implementaciones pre-unificación ─────
def _ref_dist_sextet(v, *, delta, quad, bhf, gamma, gamma2_rel=1.0, gamma3_rel=1.0,
                     int1=1.0, int2_rel=1.0, int3_rel=1.0):
    v = np.asarray(v, dtype=float)
    i1 = float(int1)
    i2 = i1 * (2.0 / 3.0) * float(int2_rel)
    i3 = i1 * (1.0 / 3.0) * float(int3_rel)
    weights = np.array([i1, i2, i3, i3, i2, i1], dtype=float)
    gammas = float(gamma) * np.array([1.0, gamma2_rel, gamma3_rel, gamma3_rel, gamma2_rel, 1.0], dtype=float)
    positions = LINE_POS_33T * (float(bhf) / BHF_DEFAULT_T) + float(delta) + float(quad) * LINE_QUAD_PATTERN
    absorption = np.zeros_like(v, dtype=float)
    for pos, weight, width in zip(positions, weights, gammas):
        absorption += weight * lorentzian(v, float(pos), float(width))
    return absorption


def _ref_dist_doublet(v, *, delta, quad, gamma, gamma2_rel=1.0, int1=1.0, int2_rel=1.0):
    v = np.asarray(v, dtype=float)
    g1 = float(gamma)
    g2 = g1 * float(gamma2_rel)
    i1 = float(int1)
    return (i1 * lorentzian(v, float(delta) - float(quad) / 2.0, g1)
            + i1 * float(int2_rel) * lorentzian(v, float(delta) + float(quad) / 2.0, g2))


def _ref_dist_singlet(v, *, delta, gamma, int1=1.0):
    return float(int1) * lorentzian(np.asarray(v, dtype=float), float(delta), float(gamma))


def _ref_dist_relaxation(v, *, delta, quad, bhf, gamma, gamma2_rel=1.0, gamma3_rel=1.0,
                         int1=1.0, int2_rel=1.0, int3_rel=1.0,
                         blocked_fraction=1.0, log10_nu=None):
    f_blocked = max(0.0, min(1.0, float(blocked_fraction)))
    gamma_eff = float(gamma)
    if log10_nu is not None and np.isfinite(float(log10_nu)):
        lognu = float(log10_nu)
        center = 8.5
        width = 0.55
        dynamic_blocked = 1.0 / (1.0 + np.exp((lognu - center) / width))
        broad = np.exp(-0.5 * ((lognu - center) / 0.75) ** 2)
        gamma_eff *= 1.0 + 1.6 * broad
        f_blocked *= float(dynamic_blocked)
    sext = _ref_dist_sextet(v, delta=delta, quad=quad, bhf=bhf, gamma=gamma_eff,
                            gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel,
                            int1=int1, int2_rel=int2_rel, int3_rel=int3_rel)
    doub = _ref_dist_doublet(v, delta=delta, quad=quad, gamma=gamma_eff,
                             gamma2_rel=gamma2_rel, int1=int1, int2_rel=int2_rel)
    area_sext = float(np.trapezoid(np.maximum(sext, 0.0), v))
    area_doub = float(np.trapezoid(np.maximum(doub, 0.0), v))
    if np.isfinite(area_sext) and np.isfinite(area_doub) and abs(area_doub) > 1e-12:
        doub = doub * (area_sext / area_doub)
    return f_blocked * sext + (1.0 - f_blocked) * doub


def _ref_dist_blume_tjon(v, *, delta, quad, bhf, gamma, gamma2_rel=1.0, gamma3_rel=1.0,
                         int1=1.0, int2_rel=1.0, int3_rel=1.0, log10_nu=5.0):
    i1 = float(int1)
    i2 = i1 * (2.0 / 3.0) * float(int2_rel)
    i3 = i1 * (1.0 / 3.0) * float(int3_rel)
    weights = np.array([i1, i2, i3, i3, i2, i1], dtype=float)
    gammas = float(gamma) * np.array([1.0, gamma2_rel, gamma3_rel, gamma3_rel, gamma2_rel, 1.0], dtype=float)
    mag = LINE_POS_33T * (float(bhf) / BHF_DEFAULT_T)
    q = float(quad) * LINE_QUAD_PATTERN
    c_plus = float(delta) + q + mag
    c_minus = float(delta) + q - mag
    out = np.zeros_like(np.asarray(v, dtype=float), dtype=float)
    for ca, cb, g, w in zip(c_plus, c_minus, gammas, weights):
        out += float(w) * two_state_exchange_profile(v, float(ca), float(cb), float(g), float(log10_nu))
    return out


def _ref_core_sextet_1st(v, delta, quad, bhf, gamma1, gamma2, gamma3,
                         depth, int1, int2, int3):
    i3 = int3
    i2 = int3 * int2
    i1 = int3 * int1
    weights = np.array([i1, i2, i3, i3, i2, i1], dtype=float)
    gammas = np.array([gamma1, gamma1 * gamma2, gamma1 * gamma3,
                       gamma1 * gamma3, gamma1 * gamma2, gamma1], dtype=float)
    positions = LINE_POS_33T * (bhf / BHF_DEFAULT_T) + delta + quad * LINE_QUAD_PATTERN
    absorption = np.zeros_like(v, dtype=float)
    for pos, weight, gamma in zip(positions, weights, gammas):
        absorption += weight * lorentzian(v, pos, gamma)
    return depth * absorption


def _ref_core_blume_tjon(v, delta, quad, bhf, gamma1, gamma2, gamma3,
                         depth, int1, int2, int3, log10_nu):
    weights = np.array([int3 * int1, int3 * int2, int3, int3, int3 * int2, int3 * int1], dtype=float)
    gammas = float(gamma1) * np.array([1.0, gamma2, gamma3, gamma3, gamma2, 1.0], dtype=float)
    mag = LINE_POS_33T * (float(bhf) / BHF_DEFAULT_T)
    q = float(quad) * LINE_QUAD_PATTERN
    c_plus = float(delta) + q + mag
    c_minus = float(delta) + q - mag
    out = np.zeros_like(np.asarray(v, dtype=float), dtype=float)
    for ca, cb, g, w in zip(c_plus, c_minus, gammas, weights):
        out += float(w) * two_state_exchange_profile(v, float(ca), float(cb), float(g), float(log10_nu))
    return float(depth) * out


# ── Equivalencia de la familia distribución ───────────────────────────────────
@pytest.mark.parametrize("case", SEXTET_CASES)
def test_dist_sextet_matches_reference(case):
    np.testing.assert_allclose(
        dist.sextet_absorption(V, **case), _ref_dist_sextet(V, **case),
        rtol=0, atol=1e-12)


@pytest.mark.parametrize("case", DOUBLET_CASES)
def test_dist_doublet_matches_reference(case):
    np.testing.assert_allclose(
        dist.doublet_absorption(V, **case), _ref_dist_doublet(V, **case),
        rtol=0, atol=1e-12)


def test_dist_singlet_matches_reference():
    case = dict(delta=0.25, gamma=0.22, int1=0.9)
    np.testing.assert_allclose(
        dist.singlet_absorption(V, **case), _ref_dist_singlet(V, **case),
        rtol=0, atol=1e-12)


@pytest.mark.parametrize("relax", RELAX_CASES)
def test_dist_relaxation_matches_reference(relax):
    case = dict(delta=0.3, quad=0.1, bhf=33.0, gamma=0.28, gamma2_rel=1.1,
                gamma3_rel=0.9, int1=1.0, int2_rel=0.8, int3_rel=1.1, **relax)
    np.testing.assert_allclose(
        dist.relaxation_empirical_absorption(V, **case),
        _ref_dist_relaxation(V, **case), rtol=0, atol=1e-12)


@pytest.mark.parametrize("log10_nu", [0.0, 5.0, 8.5, 12.0])
def test_dist_blume_tjon_matches_reference(log10_nu):
    case = dict(delta=0.1, quad=-0.05, bhf=48.0, gamma=0.30, gamma2_rel=1.0,
                gamma3_rel=1.0, int1=1.0, int2_rel=0.9, int3_rel=1.0,
                log10_nu=log10_nu)
    np.testing.assert_allclose(
        dist.blume_tjon_two_state_absorption(V, **case),
        _ref_dist_blume_tjon(V, **case), rtol=0, atol=1e-12)


def test_dist_neel_matches_composition():
    """Néel = suma lognormal de Blume-Tjon con la MISMA convención de pesos."""
    kw = dict(delta=0.2, quad=0.05, bhf=50.0, gamma=0.26, gamma2_rel=1.0,
              gamma3_rel=1.0, int1=1.0, int2_rel=1.0, int3_rel=1.0)
    neel_kw = dict(temperature_k=120.0, log10_keff=4.3, mean_d_nm=9.0,
                   sigma_lognormal=0.3, log10_tau0=-9.5, n_bins=12)
    diam, weights = phys.lognormal_diameter_distribution(
        neel_kw["mean_d_nm"], neel_kw["sigma_lognormal"], neel_kw["n_bins"])
    lognus = phys.neel_log10_nu(diam, neel_kw["temperature_k"],
                                neel_kw["log10_keff"], neel_kw["log10_tau0"])
    expected = np.zeros_like(V)
    for w, lognu in zip(weights, lognus):
        expected += float(w) * _ref_dist_blume_tjon(
            V, **kw, log10_nu=float(np.clip(lognu, -50.0, 50.0)))
    np.testing.assert_allclose(
        dist.neel_size_relaxation_absorption(V, **kw, **neel_kw),
        expected, rtol=0, atol=1e-12)


# ── Equivalencia de la familia core (rama 1er orden) ──────────────────────────
def test_core_sextet_first_order_matches_reference():
    args = (0.35, -0.2, 45.7, 0.30, 1.2, 0.8, 0.15, 3.1, 2.2, 0.9)
    np.testing.assert_allclose(
        phys.sextet_absorption(V, *args), _ref_core_sextet_1st(V, *args),
        rtol=0, atol=1e-12)


def test_core_blume_tjon_matches_reference():
    args = (0.1, -0.05, 48.0, 0.30, 1.0, 1.0, 0.2, 3.0, 2.0, 1.0, 7.5)
    np.testing.assert_allclose(
        phys.relaxation_blume_tjon_two_state_absorption(V, *args),
        _ref_core_blume_tjon(V, *args), rtol=0, atol=1e-12)


def test_dist_matches_reference_in_voigt_mode():
    """La equivalencia se mantiene con el perfil global Voigt activo."""
    old_kind, old_sigma = phys.LINE_PROFILE_KIND, phys.VOIGT_SIGMA
    try:
        phys.LINE_PROFILE_KIND = "Voigt"
        phys.VOIGT_SIGMA = 0.08
        case = SEXTET_CASES[1]
        np.testing.assert_allclose(
            dist.sextet_absorption(V, **case), _ref_dist_sextet(V, **case),
            rtol=0, atol=1e-12)
    finally:
        phys.LINE_PROFILE_KIND = old_kind
        phys.VOIGT_SIGMA = old_sigma
