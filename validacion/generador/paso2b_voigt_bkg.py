#!/usr/bin/env python3
"""Paso 2b — semántica fina de VOIGT/WDLOR, BKG(i) y ligaduras NDEX de SITE.

- VOIGT singlete: rejilla WID×WDLOR → ajuste Voigt (σ_G, Γ_L) por caso para
  deducir el mapeo de parámetros.
- VOIGT sextete: ajuste de modelo completo (6 líneas Voigt, posiciones del
  patrón de 33 T) con dos hipótesis: σ_v común vs σ_B común en Tesla
  (σ_v,i = σ_B·|c_i|); gana la de menor residuo.
- BKG: sondas lineal/parabólica ± a dos amplitudes; el bloque 5 del PLT es la
  función de fondo → ajuste polinómico directo para deducir el convenio.
- Ligaduras: SITE en modo ajuste con NDEX/FACTOR/CONST sobre 2 singletes
  (ISO(2) = ISO(1) + 0.4); el RES dice si el demo las soporta y cómo numera.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from normos_lib import (STAGING_ROOT, VALID_ROOT, dummy_counts, job_text,
                        parse_plt, parse_res, run_dosbox_batch, site_params,
                        unfold_theory, ws5_text)

P2 = VALID_ROOT / "paso2"
POS33 = np.array([-5.329, -3.084, -0.839, 0.839, 3.084, 5.329])
AREA33 = np.array([3, 2, 1, 1, 2, 3], dtype=float)


def _sg_voigt(wid, wdlor, vmax=4.0):
    return {"comps": [{"nline": 1, "iso": 0.0, "wid": wid, "dep": 0.05,
                       "raw": ["VOIGT(1)=.TRUE.,"]}],
            "extra": [f"WDLOR={wdlor},"], "vmax": vmax}


PROBES: dict[str, dict] = {}
for wid in (0.20, 0.40, 0.80):
    for wdl in (0.10, 0.194, 0.40):
        PROBES[f"PV2_w{wid:g}_l{wdl:g}"] = _sg_voigt(wid, wdl)
for amp, tag in ((15.0, "a15"), (60.0, "a60"), (-30.0, "am30")):
    PROBES[f"PB2_lin_{tag}"] = {
        "comps": [{"nline": 1, "iso": 0.0, "wid": 0.30, "dep": 0.05}],
        "extra": [f"BKG(2)={amp}, BKGFIT(2)=.FALSE.,"], "vmax": 4.0}
    PROBES[f"PB2_par_{tag}"] = {
        "comps": [{"nline": 1, "iso": 0.0, "wid": 0.30, "dep": 0.05}],
        "extra": [f"BKG(3)={amp}, BKGFIT(3)=.FALSE.,"], "vmax": 4.0}


def gen(force: bool = False) -> None:
    stg = STAGING_ROOT / "paso2b"
    pend = [n for n in PROBES if force or not (P2 / n / "SITE.PLT").exists()]
    if not pend:
        print("[paso2b] nada pendiente")
        return
    if stg.exists():
        shutil.rmtree(stg)
    stg.mkdir(parents=True)
    stems = {}
    for k, name in enumerate(pend):
        spec = PROBES[name]
        stem = f"B{k:03d}"
        stems[name] = stem
        (stg / f"{stem}.MOS").write_bytes(ws5_text(dummy_counts()).encode())
        plines = site_params(len(spec["comps"]), spec["comps"],
                             extra=spec["extra"])
        jt = job_text(stem, {"VMAX": f"{spec['vmax']}", "PFP": "256.5"},
                      plines, "Paso 2b", name[:60])
        (stg / f"{stem}.JOB").write_bytes(jt.encode("ascii"))
    print(f"[paso2b] {run_dosbox_batch(stg, list(stems.values()))}")
    for name, stem in stems.items():
        d = P2 / name
        d.mkdir(parents=True, exist_ok=True)
        for ext in (".JOB", ".RES", ".PLT"):
            f = stg / f"{stem}{ext}"
            if f.exists():
                shutil.copy2(f, d / f"SITE{ext}")


# ── Ligaduras NDEX (modo ajuste real de SITE) ────────────────────────────────

def probe_ligadura() -> None:
    """Genera un espectro 2-singletes y lo re-ajusta con SITE ligando ISO(2).

    Paso A: teoría fija (ISO=-0.5/-0.1: ligadura verdadera +0.4) → espectro.
    Paso B: SITE ajusta con ISO/DEP/WID libres y NDEX(ISO2)=idx(ISO1),
    CONST=0.4. La numeración NDEX se prueba con el orden del eco del RES.
    """
    stg = STAGING_ROOT / "paso2lig"
    if (P2 / "PL_ndex_fit" / "SITE.RES").exists():
        print("[paso2b] ligadura: ya hecha")
        return
    if stg.exists():
        shutil.rmtree(stg)
    stg.mkdir(parents=True)
    comps = [{"nline": 1, "iso": -0.5, "wid": 0.30, "dep": 0.05},
             {"nline": 1, "iso": -0.1, "wid": 0.30, "dep": 0.08}]
    (stg / "L000.MOS").write_bytes(ws5_text(dummy_counts()).encode())
    jt = job_text("L000", {"VMAX": "4.0", "PFP": "256.5"},
                  site_params(2, comps), "Ligadura paso A", "teoria fija")
    (stg / "L000.JOB").write_bytes(jt.encode("ascii"))
    print(f"[paso2b/lig A] {run_dosbox_batch(stg, ['L000'])}")
    p = parse_plt(stg / "L000.PLT", np_ch=256)
    raw = unfold_theory(p["fit"], 1_000_000,
                        rng=np.random.default_rng(20260801))
    (stg / "L001.MOS").write_bytes(ws5_text(raw).encode("ascii"))
    # Paso B: ajuste con ligadura. Numeración NDEX = índice GLOBAL del
    # parámetro (tabla "Index" del RES): BKG(1)=1, y cada subespectro ocupa
    # 15 índices desde 14: sub1 WID=14, ARE=15, ISO=16; sub2 WID=29, ARE=30,
    # ISO=31. Ligadura: ISO(2) [31] = 1.0 · ISO(1) [16] + 0.4.
    fit_lines = [
        "NSUB=2,",
        "NLINE(1)=1,", "ISO(1)=-0.45, ISOFIT(1)=.TRUE.,",
        "WID(1)=0.30, WIDFIT(1)=.TRUE.,", "DEP(1)=0.04, DEPFIT(1)=.TRUE.,",
        "NLINE(2)=1,", "ISO(2)=-0.45, ISOFIT(2)=.TRUE.,",
        "WID(2)=0.30, WIDFIT(2)=.FALSE.,", "DEP(2)=0.07, DEPFIT(2)=.TRUE.,",
        "NDEX(31)=16, FACTOR(31)=1.0, CONST(31)=0.4,",
    ]
    jt = job_text("L001", {"VMAX": "4.0", "PFP": "256.5"},
                  fit_lines, "Ligadura paso B", "fit con NDEX")
    (stg / "L001.JOB").write_bytes(jt.encode("ascii"))
    print(f"[paso2b/lig B] {run_dosbox_batch(stg, ['L001'])}")
    for stem, name in (("L000", "PL_ndex_teoria"), ("L001", "PL_ndex_fit")):
        d = P2 / name
        d.mkdir(parents=True, exist_ok=True)
        for ext in (".JOB", ".RES", ".PLT"):
            f = stg / f"{stem}{ext}"
            if f.exists():
                shutil.copy2(f, d / f"SITE{ext}")


# ── Análisis ─────────────────────────────────────────────────────────────────

def _fit_voigt_free(v, absorption):
    from scipy.optimize import curve_fit
    from scipy.special import voigt_profile

    def model(x, area, x0, sigma, gam):
        return area * voigt_profile(x - x0, max(sigma, 1e-6),
                                    max(gam, 1e-6) / 2.0)
    popt, _ = curve_fit(model, v, absorption,
                        p0=[0.05, 0.0, 0.05, 0.25], maxfev=40000)
    resid = absorption - model(v, *popt)
    return (abs(popt[2]), abs(popt[3]),
            float(np.sqrt(np.mean(resid ** 2)) / absorption.max()))


def analyze() -> None:
    print("\n══ Voigt singlete: rejilla WID × WDLOR ══")
    print(f"  {'caso':22s} {'sigma_G':>8s} {'G_FWHM':>7s} {'Gam_L':>7s} {'rms%':>6s}")
    for name in PROBES:
        if not name.startswith("PV2"):
            continue
        plt_f = P2 / name / "SITE.PLT"
        if not plt_f.exists():
            continue
        p = parse_plt(plt_f, np_ch=256)
        v, absn = p["velocity"], 1.0 - p["fit"]
        s, g, rms = _fit_voigt_free(v, absn)
        print(f"  {name:22s} {s:8.4f} {2.3548 * s:7.4f} {g:7.4f} {100 * rms:6.2f}")

    print("\n══ Voigt sextete: σ_v común vs σ_B (Tesla) ══")
    from scipy.optimize import curve_fit
    from scipy.special import voigt_profile
    slopes = np.abs(POS33) / 33.0
    for name, wid_T in (("PVM_t1", 1.0), ("PVM_t3", 3.0)):
        plt_f = P2 / name / "SITE.PLT"
        if not plt_f.exists():
            continue
        p = parse_plt(plt_f, np_ch=256)
        v, absn = p["velocity"], 1.0 - p["fit"]

        def mk(model_kind):
            def model(x, amp, gam, w):
                out = np.zeros_like(x)
                for pos, a, sl in zip(POS33, AREA33, slopes):
                    sig = w * sl if model_kind == "B" else w
                    sig = max(sig, 1e-6)
                    out += amp * a * voigt_profile(x - pos, sig,
                                                   max(gam, 1e-6) / 2.0)
                return out
            return model
        for kind in ("v", "B"):
            try:
                popt, _ = curve_fit(mk(kind), v, absn, p0=[0.01, 0.25, 0.3],
                                    maxfev=40000)
                resid = absn - mk(kind)(v, *popt)
                rms = np.sqrt(np.mean(resid ** 2)) / absn.max()
                print(f"  {name} σ_{kind}: w={abs(popt[2]):.4f} "
                      f"Γ={abs(popt[1]):.4f} rms={100 * rms:.2f}%  "
                      f"(WID={wid_T})")
            except Exception as e:
                print(f"  {name} σ_{kind}: fallo {e}")

    print("\n══ BKG: bloque de fondo del PLT ══")
    for name in PROBES:
        if not name.startswith("PB2"):
            continue
        plt_f = P2 / name / "SITE.PLT"
        if not plt_f.exists():
            continue
        p = parse_plt(plt_f, np_ch=256)
        v = p["velocity"]
        bg = p["subspectra"][-1] if p["subspectra"] else p["fit"]
        c = np.polyfit(v, bg, 3)
        print(f"  {name}: nbloques={p['nblocks']} fondo ≈ "
              f"{c[0]:+.2e}v³ {c[1]:+.2e}v² {c[2]:+.2e}v {c[3]:+.4f}")

    print("\n══ Ligadura NDEX (paso B) ══")
    res_f = P2 / "PL_ndex_fit" / "SITE.RES"
    if res_f.exists():
        r = parse_res(res_f)
        print(f"  avisos: {r.get('warnings', [])[:5]}")
        for k, d in r.get("params", {}).items():
            print(f"  {k}: {d['initial']:.4f} → {d['final']:.4f} "
                  f"± {d['error']:.4f}")


if __name__ == "__main__":
    force = "--force" in sys.argv
    gen(force=force)
    probe_ligadura()
    analyze()
