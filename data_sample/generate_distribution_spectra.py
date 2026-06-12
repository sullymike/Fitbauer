#!/usr/bin/env python3
"""Generates synthetic Mössbauer spectra for distribution fitting tests.

Four cases:
  1. sintetico_dist_bhf_gaussiana  — single Gaussian P(BHF), mean≈32 T, σ≈4 T
     (amorphous / poorly-crystallised iron oxide)
  2. sintetico_dist_bhf_bimodal    — bimodal P(BHF): 48 T (σ=1.5 T) + 28 T (σ=3 T)
     (two overlapping magnetic phases)
  3. sintetico_dist_bhf_nitido     — broad P(BHF) [10–55 T, mean=38 T] + sharp α-Fe sextet
     (nanoparticle distribution + metallic iron reference phase)
  4. sintetico_dist_deq            — Gaussian P(ΔEQ) [mean=0.85 mm/s, σ=0.30 mm/s]
     (paramagnetic Fe³⁺ with quadrupole distribution, e.g. amorphous FeOOH)

Each .adt has 512 channels (Poisson noise, 2 M baseline counts).
Matching _session.json files preset the distribution mode and fit parameters.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.physics import sextet_absorption, doublet_absorption

# ── Global constants (matching calibration.adt / calibration_session.json) ──
VMAX          = 12.007       # mm/s
ISO_REF       = -0.1092      # mm/s  (isomer shift of calibration sample FC210422)
N_CHANNELS    = 512
N_HALF        = N_CHANNELS // 2
BASELINE      = 2_000_000.0  # counts — high statistics, low Poisson noise
RNG           = np.random.default_rng(20260612)

V_HALF = np.linspace(-VMAX, VMAX, N_HALF)


# ── Helpers ──────────────────────────────────────────────────────────────────

def gaussian_weights(centers: np.ndarray, mean: float, sigma: float) -> np.ndarray:
    w = np.exp(-0.5 * ((centers - mean) / sigma) ** 2)
    return w / w.sum()


def bhf_distribution_absorption(
    v: np.ndarray,
    bhf_centers: np.ndarray,
    weights: np.ndarray,
    delta: float,
    quad: float,
    gamma1: float,
    depth_total: float,
) -> np.ndarray:
    """Sum of sextets over a BHF grid weighted by weights (sums to 1)."""
    total = np.zeros_like(v)
    for bhf, w in zip(bhf_centers, weights):
        if w < 1e-9:
            continue
        total += sextet_absorption(
            v, delta, quad, bhf,
            gamma1, 1.0, 1.0,
            depth_total * w, 3.0, 2.0, 1.0,
        )
    return total


def deq_distribution_absorption(
    v: np.ndarray,
    deq_centers: np.ndarray,
    weights: np.ndarray,
    delta: float,
    gamma1: float,
    depth_total: float,
) -> np.ndarray:
    """Sum of doublets over a ΔEQ grid weighted by weights (sums to 1)."""
    total = np.zeros_like(v)
    for deq, w in zip(deq_centers, weights):
        if w < 1e-9:
            continue
        total += doublet_absorption(
            v, delta, deq,
            gamma1, 1.0,
            depth_total * w, 1.0, 1.0,
        )
    return total


def build_raw_counts(absorption: np.ndarray, slope: float = 0.0) -> np.ndarray:
    """Build 512 symmetric raw channels from a 256-point absorption curve."""
    transmission = 1.0 + slope * V_HALF - absorption
    mu = BASELINE * transmission
    raw = np.zeros(N_CHANNELS, dtype=np.int64)
    for j in range(N_HALF):
        raw[255 - j] = RNG.poisson(mu[j])   # left arm
        raw[256 + j] = RNG.poisson(mu[j])   # right arm
    return raw


def write_adt(path: Path, raw: np.ndarray) -> None:
    lines = [f"{int(c):>12}" for c in raw]
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))


def base_session(filename: str, mode_combo_idx: int, dist_variable: str, vars_patch: dict) -> dict:
    """Minimal session skeleton for distribution fitting."""
    vars_default = {
        "vmax": VMAX,
        "center": 256.5,
        "baseline": 1.0,
        "slope": 0.0,
        "voigt_sigma": 0.05,
        "dist_delta": ISO_REF,
        "dist_quad": 0.0,
        "dist_fixed_bhf": 33.0,
        "dist_gamma": 0.18,
        "dist_bmin": 10.0,
        "dist_bmax": 55.0,
        "dist_nbins": 80,
        "dist_log_alpha": -2.0,
        "s1_delta": ISO_REF,  "s1_quad": 0.0,  "s1_bhf": 33.0,
        "s1_gamma1": 0.14, "s1_gamma2": 1.0, "s1_gamma3": 1.0,
        "s1_depth": 0.01,  "s1_int1": 3.0,  "s1_int2": 2.0,  "s1_int3": 1.0,
        "s2_delta": ISO_REF,  "s2_quad": 0.0,  "s2_bhf": 33.0,
        "s2_gamma1": 0.14, "s2_gamma2": 1.0, "s2_gamma3": 1.0,
        "s2_depth": 0.01,  "s2_int1": 3.0,  "s2_int2": 2.0,  "s2_int3": 1.0,
        "s3_delta": ISO_REF,  "s3_quad": 0.0,  "s3_bhf": 33.0,
        "s3_gamma1": 0.14, "s3_gamma2": 1.0, "s3_gamma3": 1.0,
        "s3_depth": 0.01,  "s3_int1": 3.0,  "s3_int2": 2.0,  "s3_int3": 1.0,
    }
    vars_default.update(vars_patch)
    return {
        "version": 2,
        "program": "fitbauer",
        "file_path": filename,
        "file_name": filename,
        "model_state": {
            "vars": vars_default,
            "fixed": {},
            "sextet_enabled": [False, False, False],
            "component_kind": ["Sextete", "Sextete", "Sextete"],
            "fit_velocity": False,
            "fit_center": False,
            "show_residual": True,
            "show_legend": True,
            "fit_mode": "distribution",
            "line_profile": "Lorentziana",
            "dist_variable": dist_variable,
            "dist_shape": "Hesse-Rubartsch",
            "fixed_distribution_path": None,
            "dist_use_sharp": False,
            "info_text": "",
            "constraints": [],
            "mode_combo_idx": mode_combo_idx,
        },
    }


# ── Case 1 — Single Gaussian P(BHF) ─────────────────────────────────────────
#   Mean BHF = 32 T, σ = 4 T  →  amorphous / nanocrystalline iron oxide

def case_gaussiana() -> tuple[np.ndarray, dict]:
    BHF_MEAN, BHF_SIGMA, DEPTH = 32.0, 4.0, 0.020
    DELTA = 0.35 + ISO_REF   # Fe³⁺ in oxide
    bhf_grid = np.linspace(10.0, 55.0, 150)
    w = gaussian_weights(bhf_grid, BHF_MEAN, BHF_SIGMA)
    absorption = bhf_distribution_absorption(V_HALF, bhf_grid, w, DELTA, 0.0, 0.22, DEPTH)
    raw = build_raw_counts(absorption)
    session = base_session(
        "sintetico_dist_bhf_gaussiana.adt", 1, "BHF",
        {
            "dist_delta": DELTA, "dist_gamma": 0.22,
            "dist_bmin": 5.0, "dist_bmax": 55.0, "dist_nbins": 80,
            "dist_log_alpha": -1.5,
        },
    )
    session["description"] = (
        "Synthetic P(BHF): single Gaussian peak at ~32 T (σ≈4 T). "
        "Typical of amorphous or nanocrystalline iron oxide."
    )
    return raw, session


# ── Case 2 — Bimodal P(BHF) ──────────────────────────────────────────────────
#   Phase A: BHF=48 T, σ=1.5 T, area≈40 %   (ordered Fe³⁺, e.g. hematite-like)
#   Phase B: BHF=28 T, σ=3.0 T, area≈60 %   (disordered / reduced field phase)

def case_bimodal() -> tuple[np.ndarray, dict]:
    DELTA = 0.35 + ISO_REF
    bhf_grid = np.linspace(10.0, 60.0, 200)
    wA = gaussian_weights(bhf_grid, 48.0, 1.5) * 0.40
    wB = gaussian_weights(bhf_grid, 28.0, 3.0) * 0.60
    w  = wA + wB
    absorption = bhf_distribution_absorption(V_HALF, bhf_grid, w, DELTA, 0.0, 0.20, 0.022)
    raw = build_raw_counts(absorption)
    session = base_session(
        "sintetico_dist_bhf_bimodal.adt", 1, "BHF",
        {
            "dist_delta": DELTA, "dist_gamma": 0.20,
            "dist_bmin": 10.0, "dist_bmax": 60.0, "dist_nbins": 100,
            "dist_log_alpha": -2.0,
        },
    )
    session["description"] = (
        "Synthetic P(BHF): bimodal distribution — peak A at ~48 T (σ≈1.5 T, 40 %) "
        "and peak B at ~28 T (σ≈3 T, 60 %). Two coexisting magnetic phases."
    )
    return raw, session


# ── Case 3 — Broad P(BHF) + sharp α-Fe sextet ────────────────────────────────
#   Distribution: mean=38 T, σ=6 T   (nanoparticle core, broad)
#   Sharp phase:  BHF=33 T, δ≈0      (metallic iron, ~15 % area)

def case_bhf_nitido() -> tuple[np.ndarray, dict]:
    DELTA_DIST = 0.38 + ISO_REF   # Fe³⁺/Fe²·⁵⁺ mixed
    DELTA_FE0  = 0.00 + ISO_REF   # metallic Fe
    # Distribution part
    bhf_grid = np.linspace(10.0, 60.0, 180)
    w = gaussian_weights(bhf_grid, 38.0, 6.0)
    absorption_dist = bhf_distribution_absorption(
        V_HALF, bhf_grid, w, DELTA_DIST, 0.0, 0.26, 0.018
    )
    # Sharp α-Fe sextet
    absorption_sharp = sextet_absorption(
        V_HALF, DELTA_FE0, 0.0, 33.0,
        0.14, 1.0, 1.0, 0.006, 3.0, 2.0, 1.0,
    )
    raw = build_raw_counts(absorption_dist + absorption_sharp)
    session = base_session(
        "sintetico_dist_bhf_nitido.adt", 1, "BHF",
        {
            "dist_delta": DELTA_DIST, "dist_gamma": 0.25,
            "dist_bmin": 10.0, "dist_bmax": 60.0, "dist_nbins": 90,
            "dist_log_alpha": -1.5,
            # Component 1 preset to α-Fe (sharp)
            "s1_delta": DELTA_FE0, "s1_quad": 0.0, "s1_bhf": 33.0,
            "s1_gamma1": 0.14, "s1_depth": 0.006,
        },
    )
    session["model_state"]["dist_use_sharp"] = True
    session["model_state"]["sextet_enabled"] = [True, False, False]
    session["model_state"]["component_kind"] = ["Sextete", "Sextete", "Sextete"]
    session["description"] = (
        "Synthetic P(BHF): broad distribution (mean≈38 T, σ≈6 T) + sharp α-Fe sextet "
        "(BHF=33 T, δ≈0). Nanoparticle matrix mixed with metallic iron reference phase."
    )
    return raw, session


# ── Case 4 — Gaussian P(ΔEQ) ────────────────────────────────────────────────
#   Mean ΔEQ = 0.85 mm/s, σ = 0.30 mm/s  →  amorphous Fe³⁺ (e.g. ferrihydrite)

def case_deq() -> tuple[np.ndarray, dict]:
    DELTA  = 0.35 + ISO_REF    # Fe³⁺ high-spin
    DEQ_MEAN, DEQ_SIGMA = 0.85, 0.30
    DEPTH  = 0.040
    deq_grid = np.linspace(0.05, 2.0, 120)
    w = gaussian_weights(deq_grid, DEQ_MEAN, DEQ_SIGMA)
    absorption = deq_distribution_absorption(V_HALF, deq_grid, w, DELTA, 0.18, DEPTH)
    raw = build_raw_counts(absorption)
    session = base_session(
        "sintetico_dist_deq.adt", 2, "DEQ",
        {
            "dist_delta": DELTA, "dist_gamma": 0.18,
            "dist_bmin": 0.0, "dist_bmax": 2.5, "dist_nbins": 60,
            "dist_log_alpha": -1.5,
            "dist_quad": DEQ_MEAN,
        },
    )
    session["description"] = (
        "Synthetic P(ΔEQ): Gaussian quadrupole distribution centred at ~0.85 mm/s "
        "(σ≈0.30 mm/s). Typical of amorphous Fe³⁺ phases (ferrihydrite, Fe-oxyhydroxides)."
    )
    return raw, session


# ── Main ─────────────────────────────────────────────────────────────────────

CASES = [
    ("sintetico_dist_bhf_gaussiana", case_gaussiana),
    ("sintetico_dist_bhf_bimodal",   case_bimodal),
    ("sintetico_dist_bhf_nitido",    case_bhf_nitido),
    ("sintetico_dist_deq",           case_deq),
]


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    for name, fn in CASES:
        raw, session = fn()
        adt_path = out_dir / f"{name}.adt"
        write_adt(adt_path, raw)
        session_path = out_dir / f"{name}_session.json"
        session["file_path"] = str(adt_path)
        session["file_name"] = f"{name}.adt"
        session_path.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{name}.adt  →  min={raw.min()}, max={raw.max()}, "
              f"depth≈{(raw.max()-raw.min())/raw.max()*100:.1f} %  ✓")
    print(f"\n{len(CASES)} synthetic spectra written to {out_dir}")


if __name__ == "__main__":
    main()
