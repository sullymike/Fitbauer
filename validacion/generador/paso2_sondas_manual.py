#!/usr/bin/env python3
"""Paso 2 — sondas de las capacidades reveladas por el manual (Brand 1990).

Con el manual ya disponible (validacion/sitedistmanual.odt) se sondan las
capacidades del demo que el banco v1 no cubrió por desconocer su semántica:

SITE:  VOIGT/WDLOR (perfil pseudo-Voigt; en sextetes WID pasa a ser anchura
       de distribución de campo en Tesla), NLINE=8 + D73 (octetes),
       BKG(2..5) (fondo no constante), IFSC + BEX/GAX (cristal único),
       NDEX/FACTOR/CONST (ligaduras nativas).
DIST:  DISTRI=3 + DEPSUB (perfil fijo arbitrario), DISTRI=3 + CONC
       (binomial), METHOD=6 + DISTRI=4 (Czjzek), PNEG (gaussiana espejo
       negativa), EXACT=.TRUE. + QUP (correcciones de orden mixto),
       STI (distribución de desplazamiento isomérico).

Cada sonda se archiva en validacion/paso2/<nombre>/ y el análisis imprime la
semántica deducida (ajustes de perfil, conteo de líneas, curvatura del fondo,
tablas de verdad del .RES...).
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
                        ws5_text, _num_blocks)

P2 = VALID_ROOT / "paso2"


# ── Definición de sondas SITE ────────────────────────────────────────────────
# (todas con parámetros fijos: la "teoría" del PLT es el modelo exacto)

def _site_job(comps, extra=None, vmax=10.0):
    return {"comps": comps, "extra": extra or [], "vmax": vmax}


SITE_PROBES: dict[str, dict] = {
    # Voigt paramagnético: ¿qué significan WID y WDLOR con VOIGT=.TRUE.?
    "PV_ref_lor": _site_job([{"nline": 1, "iso": 0.0, "wid": 0.30, "dep": 0.05}],
                            vmax=4.0),
    "PV_voigt_a": _site_job([{"nline": 1, "iso": 0.0, "wid": 0.30, "dep": 0.05,
                              "raw": ["VOIGT(1)=.TRUE.,"]}],
                            extra=["WDLOR=0.194,"], vmax=4.0),
    "PV_voigt_b": _site_job([{"nline": 1, "iso": 0.0, "wid": 0.60, "dep": 0.05,
                              "raw": ["VOIGT(1)=.TRUE.,"]}],
                            extra=["WDLOR=0.10,"], vmax=4.0),
    "PV_voigt_c": _site_job([{"nline": 1, "iso": 0.0, "wid": 0.10, "dep": 0.05,
                              "raw": ["VOIGT(1)=.TRUE.,"]}],
                            extra=["WDLOR=0.30,"], vmax=4.0),
    # Voigt magnético: WID en Tesla = anchura de la distribución de campo
    "PVM_ref": _site_job([{"nline": 6, "iso": 0.0, "bhf": 33.0, "wid": 0.25,
                           "dep": 0.05, "d13": 3.0, "d23": 2.0}]),
    "PVM_t1": _site_job([{"nline": 6, "iso": 0.0, "bhf": 33.0, "wid": 1.0,
                          "dep": 0.05, "d13": 3.0, "d23": 2.0,
                          "raw": ["VOIGT(1)=.TRUE.,"]}],
                        extra=["WDLOR=0.25,"]),
    "PVM_t3": _site_job([{"nline": 6, "iso": 0.0, "bhf": 33.0, "wid": 3.0,
                          "dep": 0.05, "d13": 3.0, "d23": 2.0,
                          "raw": ["VOIGT(1)=.TRUE.,"]}],
                        extra=["WDLOR=0.25,"]),
    # Octetes: NLINE=8 con D73 (líneas 7,8 referidas a 3,4)
    "PO_d73_0": _site_job([{"nline": 8, "iso": 0.0, "bhf": 33.0, "wid": 0.25,
                            "dep": 0.05, "d13": 3.0, "d23": 2.0,
                            "raw": ["D73(1)=0.0,"]}]),
    "PO_d73_std": _site_job([{"nline": 8, "iso": 0.0, "bhf": 33.0, "wid": 0.25,
                              "dep": 0.05, "d13": 3.0, "d23": 2.0,
                              "raw": ["D73(1)=0.4,"]}]),
    # Fondo no constante: 1 + Σ (BKG(i)/1000)·(−V/V1)^(i−1)
    "PB_lin": _site_job([{"nline": 1, "iso": 0.0, "wid": 0.30, "dep": 0.05,
                          "raw": []}],
                        extra=["BKG(2)=30., BKGFIT(2)=.FALSE.,"], vmax=4.0),
    "PB_parab": _site_job([{"nline": 1, "iso": 0.0, "wid": 0.30, "dep": 0.05}],
                          extra=["BKG(3)=50., BKGFIT(3)=.FALSE.,"], vmax=4.0),
    # Cristal único: HAMILT + IFSC con orientación del rayo γ (BEX, GAX)
    "PS_powder": _site_job([{"nline": 6, "iso": 0.0, "qua": 2.0, "bhf": 20.0,
                             "wid": 0.25, "dep": 0.05, "the": 30.0, "eta": 0.5}],
                           extra=["HAMILT=.TRUE.,"]),
    "PS_sc_00": _site_job([{"nline": 6, "iso": 0.0, "qua": 2.0, "bhf": 20.0,
                            "wid": 0.25, "dep": 0.05, "the": 30.0, "eta": 0.5,
                            "raw": ["BEX(1)=0.0, GAX(1)=0.0,"]}],
                          extra=["HAMILT=.TRUE.,", "IFSC=.TRUE.,"]),
    "PS_sc_9090": _site_job([{"nline": 6, "iso": 0.0, "qua": 2.0, "bhf": 20.0,
                              "wid": 0.25, "dep": 0.05, "the": 30.0, "eta": 0.5,
                              "raw": ["BEX(1)=90.0, GAX(1)=90.0,"]}],
                            extra=["HAMILT=.TRUE.,", "IFSC=.TRUE.,"]),
}


def gen_site(force: bool = False) -> None:
    stg = STAGING_ROOT / "paso2S"
    pend = [n for n in SITE_PROBES
            if force or not (P2 / n / "SITE.PLT").exists()]
    if not pend:
        print("[paso2/SITE] nada pendiente")
        return
    if stg.exists():
        shutil.rmtree(stg)
    stg.mkdir(parents=True)
    stems = {}
    for k, name in enumerate(pend):
        spec = SITE_PROBES[name]
        stem = f"P{k:03d}"
        stems[name] = stem
        (stg / f"{stem}.MOS").write_bytes(ws5_text(dummy_counts()).encode())
        plines = site_params(len(spec["comps"]), spec["comps"],
                             extra=spec["extra"])
        jt = job_text(stem, {"VMAX": f"{spec['vmax']}", "PFP": "256.5"},
                      plines, "Paso 2 sondas manual", name[:60])
        (stg / f"{stem}.JOB").write_bytes(jt.encode("ascii"))
    print(f"[paso2/SITE] {run_dosbox_batch(stg, list(stems.values()))}")
    for name, stem in stems.items():
        d = P2 / name
        d.mkdir(parents=True, exist_ok=True)
        for ext in (".JOB", ".RES", ".PLT"):
            f = stg / f"{stem}{ext}"
            if f.exists():
                shutil.copy2(f, d / f"SITE{ext}")


# ── Definición de sondas DIST ────────────────────────────────────────────────

_TRI = np.concatenate([np.linspace(0.05, 1.0, 8),
                       np.linspace(1.0, 0.1, 13)[1:]])   # triángulo asimétrico
_TRI = np.round(_TRI / _TRI.max(), 4)

DIST_PROBES: dict[str, list[str]] = {
    # Perfil fijo arbitrario (DISTRI=3): DEPSUB define la forma
    "QD_fijo_tri": (
        ["NDSS=1,", "METHOD=1,", "DISTRI=3,", "NSB(1)=20,",
         "BHF(1)=20.0, DTB(1)=1.0,", "ISO(1)=0.0, WID(1)=0.30,"]
        + [f"DEPSUB({i + 1})={v}," for i, v in enumerate(_TRI)]),
    # Binomial: DISTRI=3 + CONC>0 (PROB del teorema binomial, 13 subespectros)
    "QB_conc70": (
        ["NDSS=1,", "METHOD=1,", "DISTRI=3,", "CONC=70.0,", "NSB(1)=13,",
         "BHF(1)=8.0, DTB(1)=2.5,", "ISO(1)=0.0, WID(1)=0.30,"]),
    # Czjzek (METHOD=6, DISTRI=4): P(ΔEQ) con solo STG
    "QC_czjzek": (
        ["NDSS=1,", "METHOD=6,", "DISTRI=4,", "NSB(1)=25,",
         "QUA(1)=0.0, DTQ(1)=0.15,", "ISO(1)=0.35, WID(1)=0.25,",
         "STG(1)=0.6,"]),
    # PNEG: gaussiana + espejo negativo (cuadrupolo)
    "QP_pneg": (
        ["NDSS=1,", "METHOD=6,", "DISTRI=2,", "NSB(1)=25,",
         "QUA(1)=0.0, DTQ(1)=0.15,", "ISO(1)=0.35, WID(1)=0.25,",
         "AVG(1)=1.2, STG(1)=0.3,", "PNEG(1)=0.3,"]),
    # EXACT: correcciones de interacción mixta (QUP, octetes con EFG random)
    "QE_exact": (
        ["NDSS=1,", "METHOD=1,", "DISTRI=2,", "EXACT(1)=.TRUE.,",
         "NSB(1)=31,", "BHF(1)=15.0, DTB(1)=1.0,",
         "ISO(1)=0.0, WID(1)=0.30,", "QUP(1)=0.5,",
         "AVG(1)=25.0, STG(1)=3.0,"]),
    "QE_ref": (   # gemela sin EXACT para diferenciar
        ["NDSS=1,", "METHOD=1,", "DISTRI=2,", "NSB(1)=31,",
         "BHF(1)=15.0, DTB(1)=1.0,", "ISO(1)=0.0, WID(1)=0.30,",
         "AVG(1)=25.0, STG(1)=3.0,"]),
    # STI: anchura de la distribución de desplazamiento isomérico
    "QS_sti": (
        ["NDSS=1,", "METHOD=1,", "DISTRI=2,", "NSB(1)=31,",
         "BHF(1)=15.0, DTB(1)=1.0,", "ISO(1)=0.0, WID(1)=0.30,",
         "STI(1)=0.10,", "AVG(1)=25.0, STG(1)=3.0,"]),
}


def gen_dist(force: bool = False) -> None:
    stg = STAGING_ROOT / "paso2D"
    pend = [n for n in DIST_PROBES
            if force or not (P2 / n / "DIST.PLT").exists()]
    if not pend:
        print("[paso2/DIST] nada pendiente")
        return
    if stg.exists():
        shutil.rmtree(stg)
    stg.mkdir(parents=True)
    stems = {}
    for k, name in enumerate(pend):
        stem = f"Q{k:03d}"
        stems[name] = stem
        (stg / f"{stem}.MOS").write_bytes(ws5_text(dummy_counts()).encode())
        jt = job_text(stem, {"VMAX": "10.0", "PFP": "256.5",
                             "SIMULT": ".TRUE."},
                      DIST_PROBES[name], "Paso 2 sondas DIST", name[:60])
        (stg / f"{stem}.JOB").write_bytes(jt.encode("ascii"))
    print(f"[paso2/DIST] {run_dosbox_batch(stg, list(stems.values()), exe='DIST')}")
    for name, stem in stems.items():
        d = P2 / name
        d.mkdir(parents=True, exist_ok=True)
        for ext in (".JOB", ".RES", ".PLT"):
            f = stg / f"{stem}{ext}"
            if f.exists():
                shutil.copy2(f, d / f"DIST{ext}")


# ── Análisis ─────────────────────────────────────────────────────────────────

def _theory(name: str, exe: str = "SITE", np_ch: int = 256):
    plt_f = P2 / name / f"{exe}.PLT"
    if not plt_f.exists():
        return None, None
    if exe == "SITE":
        p = parse_plt(plt_f, np_ch=np_ch)
        return p["velocity"], p["fit"]
    nums = _num_blocks(plt_f.read_text(errors="replace"))
    arr = np.array(nums[:512]).reshape(2, 256)
    return arr[0], -arr[1]


def _fit_voigt(v, absorption):
    """Ajusta perfil Voigt (σ gaussiana, Γ lorentziana FWHM) a una línea."""
    from scipy.optimize import curve_fit
    from scipy.special import voigt_profile

    def model(x, area, x0, sigma, gam_fwhm):
        return area * voigt_profile(x - x0, max(sigma, 1e-6),
                                    max(gam_fwhm, 1e-6) / 2.0)
    a0 = float(np.trapezoid(absorption, v))
    popt, _ = curve_fit(model, v, absorption,
                        p0=[a0, v[np.argmax(absorption)], 0.1, 0.2],
                        maxfev=20000)
    return {"area": popt[0], "x0": popt[1], "sigma": abs(popt[2]),
            "gamma_fwhm": abs(popt[3])}


def analyze() -> None:
    out: dict = {}
    print("\n══ Voigt paramagnético (WID/WDLOR) ══")
    for name in ("PV_ref_lor", "PV_voigt_a", "PV_voigt_b", "PV_voigt_c"):
        v, th = _theory(name)
        if th is None:
            print(f"  {name}: SIN PLT")
            continue
        r = _fit_voigt(v, 1.0 - th)
        out[name] = r
        print(f"  {name}: sigma_G={r['sigma']:.4f}  Gamma_L(FWHM)="
              f"{r['gamma_fwhm']:.4f}  (G_FWHM={2.3548 * r['sigma']:.4f})")

    print("\n══ Voigt magnético (WID en Tesla) ══")
    for name in ("PVM_ref", "PVM_t1", "PVM_t3"):
        v, th = _theory(name)
        if th is None:
            print(f"  {name}: SIN PLT")
            continue
        absn = 1.0 - th
        rows = []
        # líneas 1 y 3 del sexteto (33 T): posiciones nominales −5.33 y −0.84
        for x0, lab, slope in ((-5.329, "L1", 5.329 / 33.0),
                               (-0.839, "L3", 0.839 / 33.0)):
            m = (v > x0 - 1.2) & (v < x0 + 1.2)
            try:
                r = _fit_voigt(v[m], absn[m])
                rows.append((lab, r["sigma"], r["gamma_fwhm"], slope))
            except Exception as e:
                rows.append((lab, np.nan, np.nan, slope))
        out[name] = rows
        for lab, s, g, slope in rows:
            imp = s / slope if slope else np.nan
            print(f"  {name} {lab}: sigma_v={s:.4f} → sigma_B={imp:.3f} T; "
                  f"Gamma_L={g:.4f}")

    print("\n══ Octetes NLINE=8 (D73) ══")
    for name in ("PO_d73_0", "PO_d73_std"):
        v, th = _theory(name)
        if th is None:
            print(f"  {name}: SIN PLT")
            continue
        absn = 1.0 - th
        from scipy.signal import find_peaks
        pk, _ = find_peaks(absn, height=0.05 * absn.max(), distance=3)
        print(f"  {name}: {len(pk)} líneas en {np.round(v[pk], 2).tolist()}")

    print("\n══ Fondo no constante BKG(i) ══")
    for name in ("PB_lin", "PB_parab"):
        v, th = _theory(name)
        if th is None:
            print(f"  {name}: SIN PLT")
            continue
        # fondo en los extremos (lejos de la línea en 0): ajusta polinomio
        m = np.abs(v) > 1.5
        c = np.polyfit(v[m], th[m], 2)
        p = parse_plt(P2 / name / "SITE.PLT", np_ch=256)
        print(f"  {name}: nbloques={p['nblocks']}  th(extremos) ≈ "
              f"{c[0]:+.3e}·v² {c[1]:+.3e}·v {c[2]:+.4f}")

    print("\n══ Cristal único IFSC (BEX, GAX) ══")
    ref = None
    for name in ("PS_powder", "PS_sc_00", "PS_sc_9090"):
        v, th = _theory(name)
        if th is None:
            print(f"  {name}: SIN PLT")
            continue
        absn = 1.0 - th
        if ref is None:
            ref = absn
            print(f"  {name}: referencia (área={np.trapezoid(absn, v):.4f})")
        else:
            d = float(np.max(np.abs(absn - ref)))
            print(f"  {name}: max|Δ| vs powder = {d:.4f} "
                  f"(área={np.trapezoid(absn, v):.4f})")

    print("\n══ DIST: tablas de verdad y espectros ══")
    from serie_J import parse_dist_tables
    for name in DIST_PROBES:
        res_f = P2 / name / "DIST.RES"
        v, prof = _theory(name, exe="DIST")
        if not res_f.exists():
            print(f"  {name}: SIN RES")
            continue
        tabs = parse_dist_tables(res_f.read_text(errors="replace"))
        if tabs:
            t = tabs[0]
            var = np.array(t["var"]); pp = np.maximum(np.array(t["P"]), 0)
            pn = pp / pp.sum() if pp.sum() else pp
            avg = float(np.sum(pn * var))
            std = float(np.sqrt(np.sum(pn * (var - avg) ** 2)))
            print(f"  {name}: tabla {len(var)} ptos, <x>={avg:.3f}, "
                  f"std={std:.3f}, P[:5]={np.round(pp[:5], 2).tolist()}"
                  f"{' | PLT ok' if prof is not None else ' | SIN PLT'}")
        else:
            print(f"  {name}: sin tabla de áreas"
                  f"{' | PLT ok' if prof is not None else ' | SIN PLT'}")
    # STI/EXACT: comparar con la gemela QE_ref
    _, ref_th = _theory("QE_ref", exe="DIST")
    for name in ("QE_exact", "QS_sti"):
        _, th = _theory(name, exe="DIST")
        if th is not None and ref_th is not None:
            num = float(np.max(np.abs(th / th.max() - ref_th / ref_th.max())))
            print(f"  {name}: max|Δ perfil| vs QE_ref = {num:.4f} "
                  f"({'ACTIVO' if num > 1e-3 else 'sin efecto'})")

    (P2 / "analisis_sondas.json").write_text(
        json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    force = "--force" in sys.argv
    gen_site(force=force)
    gen_dist(force=force)
    analyze()
