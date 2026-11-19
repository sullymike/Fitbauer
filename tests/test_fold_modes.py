"""Plegado explícito: doblar, un solo barrido o dos ramas sin doblar.

Los espectros son sintéticos (doblete lorentziano con ruido Poisson),
generados sin pasar por el modelo de Fitbauer.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from core.folding import (
    fold_integer_or_half, prepare_channel_counts, single_sweep_velocity_axis,
    triangular_velocity_axis, velocity_axis,
)
from core.normos_job import job_to_model_state, model_state_to_job
from core.session import HeadlessSession

ROOT = Path(__file__).resolve().parents[1]
VMAX = 6.0
N = 512
CENTER = 256.5
TRUE = {"s1_delta": 0.40, "s1_quad": 1.00, "s1_gamma1": 0.30}


def _transmission(v: np.ndarray) -> np.ndarray:
    g = (TRUE["s1_gamma1"] / 2) ** 2
    lines = (TRUE["s1_delta"] - TRUE["s1_quad"] / 2, TRUE["s1_delta"] + TRUE["s1_quad"] / 2)
    return 1.0 - sum(0.08 * g / ((v - x) ** 2 + g) for x in lines)


def _raw_counts(seed: int = 7, base: float = 2e5) -> np.ndarray:
    v = triangular_velocity_axis(N, VMAX, CENTER)
    return np.random.default_rng(seed).poisson(base * _transmission(v)).astype(float)


def _template() -> dict:
    ms = json.loads((ROOT / "data_sample/template_siderita.json").read_text())["model_state"]
    ms["vars"].update(vmax=VMAX, s1_delta=0.45, s1_quad=0.9, s1_gamma1=0.35, s1_depth=0.08)
    ms["likelihood"] = "poisson"
    return ms


def _fit(path: Path, **model) -> dict:
    s = HeadlessSession()
    s.apply_template_model_state({**_template(), **model})
    s.load_ws5(path)
    out = s.run_fit()
    out["n_points"] = s.spectrum.y_data.size
    return out


def _write(tmp_path: Path, name: str, values: np.ndarray) -> Path:
    p = tmp_path / name
    p.write_text("\n".join(f"{x:.0f}" for x in values))
    return p


# ── core.folding ──────────────────────────────────────────────────────────────

def test_two_branch_axis_matches_folding():
    """Cada canal en su velocidad del triángulo = el punto que le toca al doblar."""
    v = triangular_velocity_axis(N, VMAX, 255.7)
    counts = 1e5 * _transmission(v)
    folded, _ = fold_integer_or_half(counts, 255.7)
    expected = 1e5 * _transmission(velocity_axis(N, VMAX, N // 2))
    assert np.max(np.abs(folded - expected)) / 1e5 < 1e-4


def test_single_sweep_axis_and_reverse():
    v = single_sweep_velocity_axis(256, VMAX)
    assert v[0] == -VMAX and v[-1] == VMAX
    np.testing.assert_array_equal(single_sweep_velocity_axis(256, VMAX, reverse=True), v[::-1])


@pytest.mark.parametrize("mode", ["single_sweep", "two_branches"])
def test_unfolded_data_keep_all_channels_with_poisson_sigma(mode):
    c = _raw_counts()
    data, sigma, y, norm = prepare_channel_counts(c, CENTER, fold_mode=mode)
    assert data.size == N
    np.testing.assert_allclose(sigma, np.sqrt(c) / norm)


# ── Ajuste (headless) ─────────────────────────────────────────────────────────

def test_fold_and_two_branches_agree(tmp_path):
    p = _write(tmp_path, "raw.adt", _raw_counts())
    folded = _fit(p)
    unfolded = _fit(p, fold_mode="two_branches")
    assert folded["n_points"] == N // 2 and unfolded["n_points"] == N
    for k in TRUE:
        err = folded["errors"][k]
        assert abs(folded["values"][k] - unfolded["values"][k]) < 0.5 * err
        assert abs(unfolded["values"][k] - TRUE[k]) < 4 * err
        # Misma información: los errores casi coinciden.
        assert unfolded["errors"][k] == pytest.approx(err, rel=0.1)
    # σ de Poisson sin el ÷2 del promedio de pares: χ²red ≈ 1.
    assert 0.8 < unfolded["stats"]["red_chi2"] < 1.25


def test_two_branches_fits_center(tmp_path):
    p = _write(tmp_path, "raw.adt", _raw_counts())
    r = _fit(p, fold_mode="two_branches", fit_center=True)
    assert abs(r["values"]["center"] - CENTER) < 0.1


def _hardware_folded(seed: int = 3) -> np.ndarray:
    """Un solo barrido de 256 canales, como lo guarda un equipo que ya dobla."""
    v = single_sweep_velocity_axis(N // 2, VMAX)
    return np.random.default_rng(seed).poisson(4e5 * _transmission(v)).astype(float)


def test_single_sweep_fit(tmp_path):
    p = _write(tmp_path, "folded.dat", _hardware_folded())
    r = _fit(p, fold_mode="single_sweep", fit_center=True)   # el centro se ignora
    assert r["n_points"] == N // 2 and "center" not in r["values"]
    for k, true in TRUE.items():
        assert abs(r["values"][k] - true) < 4 * r["errors"][k]
    assert 0.8 < r["stats"]["red_chi2"] < 1.25


def test_single_sweep_reverse(tmp_path):
    c = _hardware_folded()
    straight = _fit(_write(tmp_path, "a.dat", c), fold_mode="single_sweep")
    reversed_ = _fit(_write(tmp_path, "b.dat", c[::-1]), fold_mode="single_sweep",
                     reverse_velocity=True)
    for k in TRUE:
        assert reversed_["values"][k] == pytest.approx(straight["values"][k], abs=1e-6)
    wrong = _fit(_write(tmp_path, "c.dat", c[::-1]), fold_mode="single_sweep")
    assert wrong["values"]["s1_delta"] < 0          # sin invertir, δ cambia de signo


def test_session_payload_keeps_fold_mode(tmp_path):
    s = HeadlessSession()
    s.apply_template_model_state({**_template(), "fold_mode": "single_sweep",
                                  "reverse_velocity": True})
    s.load_ws5(_write(tmp_path, "f.dat", _hardware_folded()))
    ms = s.session_payload()["model_state"]
    assert ms["fold_mode"] == "single_sweep" and ms["reverse_velocity"] is True


def test_velocity_file_rejected_by_channel_loader(tmp_path):
    v = np.linspace(-VMAX, VMAX, 256)
    p = tmp_path / "v.txt"
    p.write_text("\n".join(f"{a:.4f} {b:.0f}" for a, b in zip(v, 1e5 * _transmission(v))))
    with pytest.raises(ValueError):
        HeadlessSession().load_ws5(p)


# ── NORMOS: FOLD=.FALSE. ──────────────────────────────────────────────────────

_JOB = """data.mos
x.job
x.res
x.plt
 &DATA
 NLTEXT=4, TRIANG=.TRUE., FOLD=.FALSE., VMAX=8.0, {extra}
 &END
title 1
title 2
 &PARAM
 NSUB=1, NLINE(1)=2, ISO(1)=0.4, QUA(1)=1.0, WID(1)=0.3, DEP(1)=0.05,
 &END
"""


def test_normos_fold_false_is_single_sweep():
    r = job_to_model_state(_JOB.format(extra=""))
    ms = r["model_state"]
    assert ms["fold_mode"] == "single_sweep" and ms["reverse_velocity"] is False
    assert r["vmax"] == 8.0
    texto = model_state_to_job(ms, vmax=r["vmax"])
    assert "FOLD=.FALSE." in texto and "PFP" not in texto


def test_normos_positive_v1_reverses():
    r = job_to_model_state(_JOB.format(extra="V1=7.5,"))
    ms = r["model_state"]
    assert ms["reverse_velocity"] is True and r["vmax"] == 7.5
    texto = model_state_to_job(ms, vmax=r["vmax"])
    vuelta = job_to_model_state(texto)["model_state"]
    assert vuelta["fold_mode"] == "single_sweep" and vuelta["reverse_velocity"] is True


def test_normos_explicit_delv_warns():
    r = job_to_model_state(_JOB.format(extra="V1=-8.0, DELV=0.06,"))
    assert any("DELV" in w for w in r["warnings"])


def test_normos_folded_job_unchanged():
    r = job_to_model_state(_JOB.replace("FOLD=.FALSE., ", "").format(extra="PFP=256.5,"))
    assert "fold_mode" not in r["model_state"]
