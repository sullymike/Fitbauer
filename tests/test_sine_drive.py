"""Soporte de drive senoidal (NORMOS TRIANG=.FALSE., FOLD=.FALSE., SIMULT=.TRUE.).

Con drive senoidal no se dobla: cada canal tiene su velocidad real
``v_i = vmax·sin(2π(i−c0)/N)`` y el espectro sin plegar se ajusta completo.
"""
from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

from core.folding import (
    find_sine_symmetry_center,
    normalize_unfolded,
    sine_velocity_axis,
    symmetry_center_to_c0,
)
from core.physics import total_model
from core.session import HeadlessSession, ModelState

SEXTET = np.array([0.0, 0.0, 33.0, 0.30, 1.0, 1.0, 0.30, 3.0, 2.0, 1.0])


def _sine_alpha_fe_counts(n=512, vmax=11.0, c0=0.0, depth=20000.0, seed=0):
    """Cuentas Poisson de un α-Fe sintético medido con drive senoidal."""
    v = sine_velocity_axis(n, vmax, c0)
    t = total_model(v, 1.0, 0.0, [("Sextete", SEXTET)])
    rng = np.random.default_rng(seed)
    return rng.poisson(np.maximum(t, 0.0) * depth).astype(float)


# ── Funciones puras ──────────────────────────────────────────────────────────
def test_sine_velocity_axis_shape_and_values():
    n, vmax = 512, 11.0
    v = sine_velocity_axis(n, vmax, 0.0)
    assert v.size == n                                  # sin doblar
    assert abs(v[n // 4 - 1] - vmax) < 1e-6             # +vmax en i = c0 + N/4
    assert abs(v[0]) < 0.2                              # ~0 en el cruce
    assert not np.all(np.diff(v) > 0)                   # no monótono


def test_symmetry_center_to_c0():
    assert abs(symmetry_center_to_c0(128.0, 512) - 0.0) < 1e-9
    assert abs(symmetry_center_to_c0(200.0, 512) - (200.0 - 128.0)) < 1e-9


def test_normalize_unfolded_baseline_and_sigma():
    counts = _sine_alpha_fe_counts()
    sigma, y, norm = normalize_unfolded(counts)
    assert y.size == counts.size
    assert abs(float(np.percentile(y, 90)) - 1.0) < 0.05
    assert np.all(sigma > 0)


def test_find_sine_symmetry_center_near_quarter():
    counts = _sine_alpha_fe_counts()
    center = find_sine_symmetry_center(counts)
    assert abs(center - 512 / 4) < 5.0                  # ~N/4


# ── Ajuste headless de extremo a extremo ─────────────────────────────────────
def _write_adt(counts) -> str:
    d = tempfile.mkdtemp()
    fp = os.path.join(d, "sine.adt")
    with open(fp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(str(int(c)) for c in counts))
    return fp


def test_sine_fit_recovers_bhf():
    """Un α-Fe senoidal recupera BHF≈33 con el ajuste sin plegar."""
    fp = _write_adt(_sine_alpha_fe_counts(c0=0.0))
    sess = HeadlessSession(ModelState.defaults())
    sess.model.drive_form = "sine"
    sess.load_ws5(fp, vmax=11.0)
    assert sess._velocity().size == 512               # NO doblado (N, no N/2)
    assert abs(sess.spectrum.center - 128.0) < 5.0
    sess.model.vars.update({"s1_bhf": 30.0, "s1_delta": 0.1, "s1_gamma1": 0.35})
    res = sess.run_fit()
    assert abs(res["values"]["s1_bhf"] - 33.0) < 0.4
    assert abs(res["values"]["s1_delta"]) < 0.05


def test_sine_fit_center_refines_phase():
    """Con fit_center (fase c0 libre) el χ² reducido baja a ~1."""
    # Genera con c0=0 pero deja que el ajuste refine la fase.
    fp = _write_adt(_sine_alpha_fe_counts(c0=0.0))
    sess = HeadlessSession(ModelState.defaults())
    sess.model.drive_form = "sine"
    sess.model.fit_center = True
    sess.load_ws5(fp, vmax=11.0)
    sess.model.vars.update({"s1_bhf": 30.0, "s1_delta": 0.1, "s1_gamma1": 0.35})
    res = sess.run_fit()
    assert abs(res["values"]["s1_bhf"] - 33.0) < 0.3
    assert res["stats"]["red_chi2"] < 2.0


def test_triangular_still_default():
    """Sin tocar drive_form, todo sigue siendo triangular (regresión)."""
    ms = ModelState.defaults()
    assert ms.drive_form == "triangular"
