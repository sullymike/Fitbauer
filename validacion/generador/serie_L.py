#!/usr/bin/env python3
"""Bloque L: capacidades de DIST reveladas por el manual (extremos y centro).

- L1 binomial: DISTRI=3 + CONC∈{10,30,50,70,90}% (PROB del teorema binomial,
  13 subespectros, malla 8..38 T). Fitbauer: --shape binomial con la MISMA
  malla (p verdadero = CONC/100) e histograma de control.
- L2 Czjzek: METHOD=6 + DISTRI=4, STG∈{0.3,0.6,1.2}. Fitbauer no tiene forma
  Czjzek → recuperación por histograma P(ΔEQ) (momentos + forma).
- L3 PNEG: gaussiana + espejo negativo en ΔEQ (AVG=0.5 pequeño para que el
  espejo pese); verdad analítica plegada sobre |ΔEQ|.
- L4 EXACT: correcciones de orden mixto (QUP∈{0.2,0.5,1.0}) sobre una
  gaussiana de campo; el kernel 1er orden de Fitbauer debe sesgarse al crecer
  QUP → mapa del dominio de validez.
- L5 re-ajustes de J con formas paramétricas de Fitbauer: J1 con
  --shape gaussiana, J2 bimodales con --shape vbf N=2, y regularizadores
  extremos (tv / maxent) sobre J1_b30_s3 v1.

DEPSUB no existe en el namelist del demo (sonda QD) → el perfil fijo
arbitrario de DISTRI=3 solo es generable vía CONC (binomial).
STI resultó inoperante en la generación (sonda QS): no validable.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from normos_lib import (FITBAUER_ROOT, STAGING_ROOT, VALID_ROOT, dummy_counts,
                        job_text, run_dosbox_batch, ws5_text, _num_blocks,
                        unfold_theory, write_adt)
from runner import append_rows, dedupe_resumen
from serie_J import parse_dist_tables, truth_moments, peaks

LDIR = VALID_ROOT / "L"
DEPTH = 0.05
BASE = 1_000_000

CASES: dict[str, dict] = {}

for conc in (10, 30, 50, 70, 90):
    CASES[f"L1_conc{conc:02d}"] = {
        "plines": ["NDSS=1,", "METHOD=1,", "DISTRI=3,", f"CONC={conc}.0,",
                   "NSB(1)=13,", "BHF(1)=8.0, DTB(1)=2.5,",
                   "ISO(1)=0.0, WID(1)=0.30,"],
        "var": "bhf", "grid": (8.0, 38.0, 13), "p_true": conc / 100.0,
        "fit": {"bmin": 8, "bmax": 38, "nbins": 13, "gamma": 0.30},
        "nota": f"binomial CONC={conc}%"}

for stg in (0.3, 0.6, 1.2):
    CASES[f"L2_czjzek_s{stg:g}"] = {
        "plines": ["NDSS=1,", "METHOD=6,", "DISTRI=4,", "NSB(1)=25,",
                   "QUA(1)=0.0, DTQ(1)=0.18,",
                   "ISO(1)=0.35, WID(1)=0.25,", f"STG(1)={stg},"],
        "var": "quad", "delta": 0.35,
        "fit": {"bmin": 0, "bmax": 4.5, "nbins": 25, "gamma": 0.25},
        "nota": f"Czjzek STG={stg}"}

for pneg in (0.2, 0.5):
    CASES[f"L3_pneg{pneg:g}"] = {
        "plines": ["NDSS=1,", "METHOD=6,", "DISTRI=2,", "NSB(1)=25,",
                   "QUA(1)=-1.8, DTQ(1)=0.15,",
                   "ISO(1)=0.35, WID(1)=0.25,",
                   "AVG(1)=0.5, STG(1)=0.35,", f"PNEG(1)={pneg},"],
        "var": "quad", "delta": 0.35, "pneg": (0.5, 0.35, pneg),
        "fit": {"bmin": 0, "bmax": 2.4, "nbins": 17, "gamma": 0.25},
        "nota": f"gauss AVG=0.5 + espejo PNEG={pneg}"}

# L6: textura en la distribución (D23 de DIST ≠ 2): el kernel de Fitbauer
# fija las intensidades 3:2:1 → hueco documentado (mismo mecanismo que el
# 3:3:1 efectivo de EXACT).
CASES["L6_d23_3"] = {
    "plines": ["NDSS=1,", "METHOD=1,", "DISTRI=2,", "NSB(1)=31,",
               "BHF(1)=10.0, DTB(1)=1.0,", "ISO(1)=0.0, WID(1)=0.30,",
               "D23(1)=3.0,", "AVG(1)=25.0, STG(1)=3.0,"],
    "var": "bhf", "truth_avg": 25.0, "truth_std": 3.0,
    "fit": {"bmin": 5, "bmax": 45, "nbins": 41, "gamma": 0.30},
    "nota": "textura D23=3 en distribucion (kernel Fitbauer fijo 3:2:1)"}
CASES["L6_d23_1"] = {
    "plines": ["NDSS=1,", "METHOD=1,", "DISTRI=2,", "NSB(1)=31,",
               "BHF(1)=10.0, DTB(1)=1.0,", "ISO(1)=0.0, WID(1)=0.30,",
               "D23(1)=1.0,", "AVG(1)=25.0, STG(1)=3.0,"],
    "var": "bhf", "truth_avg": 25.0, "truth_std": 3.0,
    "fit": {"bmin": 5, "bmax": 45, "nbins": 41, "gamma": 0.30},
    "nota": "textura D23=1 en distribucion (kernel Fitbauer fijo 3:2:1)"}

for qup in (0.2, 0.5, 1.0):
    CASES[f"L4_exact_q{qup:g}"] = {
        "plines": ["NDSS=1,", "METHOD=1,", "DISTRI=2,", "EXACT(1)=.TRUE.,",
                   "NSB(1)=31,", "BHF(1)=10.0, DTB(1)=1.0,",
                   "ISO(1)=0.0, WID(1)=0.30,", f"QUP(1)={qup},",
                   "AVG(1)=25.0, STG(1)=3.0,"],
        "var": "bhf", "truth_avg": 25.0, "truth_std": 3.0,
        "fit": {"bmin": 5, "bmax": 45, "nbins": 41, "gamma": 0.30},
        "nota": f"EXACT orden mixto QUP={qup}"}


# ── Generación ───────────────────────────────────────────────────────────────

def generate(force: bool = False) -> None:
    stg = STAGING_ROOT / "L"
    pend = [cid for cid in CASES
            if force or not (LDIR / cid / "v0.dat").exists()]
    if not pend:
        print("[L] generación: nada pendiente")
        return
    if stg.exists():
        shutil.rmtree(stg)
    stg.mkdir(parents=True)
    stems = {}
    for k, cid in enumerate(pend):
        stem = f"L{k:03d}"
        stems[cid] = stem
        (stg / f"{stem}.MOS").write_bytes(ws5_text(dummy_counts()).encode())
        jt = job_text(stem, {"VMAX": "10.0", "PFP": "256.5",
                             "SIMULT": ".TRUE."},
                      CASES[cid]["plines"], "Bloque L", cid[:60])
        (stg / f"{stem}.JOB").write_bytes(jt.encode("ascii"))
    print(f"[L] {run_dosbox_batch(stg, list(stems.values()), exe='DIST')}")
    for cid, stem in stems.items():
        cdir = LDIR / cid
        cdir.mkdir(parents=True, exist_ok=True)
        for ext in (".MOS", ".JOB", ".RES", ".PLT"):
            f = stg / f"{stem}{ext}"
            if f.exists():
                shutil.copy2(f, cdir / f"DIST{ext}")
        info = {k: v for k, v in CASES[cid].items() if k != "plines"}
        info.update({"caso": cid, "serie": "L", "vmax": 10.0,
                     "dist_version": "09.09.1993"})
        plt_f = cdir / "DIST.PLT"
        if plt_f.exists():
            nums = _num_blocks(plt_f.read_text(errors="replace"))
            arr = np.array(nums[:512]).reshape(2, 256)
            prof = -arr[1]
            theory = 1.0 - DEPTH * prof / prof.max()
            np.save(cdir / "teoria_norm.npy", theory)
            write_adt(cdir / "v0.dat", unfold_theory(theory, BASE))
            rng = np.random.default_rng(zlib.crc32(cid.encode()) & 0x7FFFFFFF)
            write_adt(cdir / "v1.dat", unfold_theory(theory, BASE, rng=rng))
            tables = parse_dist_tables(
                (cdir / "DIST.RES").read_text(errors="replace"))
            info["tablas_P"] = tables
            if tables:
                avg, std = truth_moments(tables)
                info["momentos_verdad"] = {"avg": avg, "std": std}
        else:
            info["error"] = "SIN PLT"
        (cdir / "verdad.json").write_text(
            json.dumps(info, indent=1, ensure_ascii=False))


def truth_pneg_moments(avg, stg_w, pneg, grid) -> tuple[float, float]:
    """Momentos analíticos de |Q| para (1−p)·N(avg,σ) + p·N(−avg,σ) plegada."""
    q = np.linspace(0, 6, 4001)
    f = ((1 - pneg) * np.exp(-0.5 * ((q - avg) / stg_w) ** 2)
         + pneg * np.exp(-0.5 * ((q + avg) / stg_w) ** 2)
         + (1 - pneg) * np.exp(-0.5 * ((-q - avg) / stg_w) ** 2)
         + pneg * np.exp(-0.5 * ((-q + avg) / stg_w) ** 2))
    f /= np.trapezoid(f, q)
    m = float(np.trapezoid(f * q, q))
    s = float(np.sqrt(np.trapezoid(f * (q - m) ** 2, q)))
    return m, s


# ── Ajuste Fitbauer ──────────────────────────────────────────────────────────

def fit_one(cid: str, version: str, shape: str | None = None,
            extra: list[str] | None = None, tag: str | None = None) -> dict | None:
    """extra: flags adicionales del CLI (p. ej. --d23 para textura)."""
    spec = CASES[cid]
    cdir = LDIR / cid
    dat = cdir / f"{version}.dat"
    if not dat.exists():
        return None
    prefix = cdir / f"fit_{tag or version}{('_' + shape) if shape else ''}"
    venv_py = FITBAUER_ROOT / ".venv" / "bin" / "python"
    py = str(venv_py) if venv_py.exists() else sys.executable
    fk = spec["fit"]
    cmd = [py, str(FITBAUER_ROOT / "fit_bhf_distribution_cli.py"), str(dat),
           "--out-prefix", str(prefix), "--vmax", "10",
           "--bmin", str(fk["bmin"]), "--bmax", str(fk["bmax"]),
           "--nbins", str(fk["nbins"]), "--gamma", str(fk["gamma"])]
    if spec["var"] == "bhf":
        cmd += ["--variable", "bhf"]
    else:
        cmd += ["--variable", "quad", "--fixed-bhf", "0",
                "--delta", str(spec.get("delta", 0.0))]
    if shape:
        cmd += ["--shape", shape]
        if shape == "vbf":
            cmd += ["--vbf-components", "2"]
    if not (extra and ("--alpha" in extra)) and shape in (None, "histograma"):
        cmd.append("--scan-alpha")
    cmd += extra or []
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900,
                       cwd=str(FITBAUER_ROOT))
    dist_f = Path(f"{prefix}_distribution.dat")
    if r.returncode != 0 or not dist_f.exists():
        return {"error": (r.stderr or r.stdout)[-300:]}
    cols = np.loadtxt(dist_f)
    v, p = cols[:, 0], np.maximum(cols[:, 1], 0.0)
    if p.sum() <= 0:
        return {"error": "P nula"}
    pn = p / p.sum()
    avg = float(np.sum(pn * v))
    std = float(np.sqrt(np.sum(pn * (v - avg) ** 2)))
    out = {"avg": avg, "std": std, "v": v.tolist(), "P": pn.tolist()}
    summ_f = Path(f"{prefix}_summary.json")
    if summ_f.exists():
        try:
            out["summary"] = json.loads(summ_f.read_text())
        except Exception:
            pass
    return out


def _rows_for(cid, version, res, t_avg, t_std, nota) -> list[dict]:
    rows = []
    base = {"serie": "L", "caso": cid, "version": version, "nota": nota}
    if res is None:
        return rows
    if "error" in res:
        return [dict(base, parametro="-", convergido="no",
                     nota=res["error"][:150])]
    for pname, tval, fval in (("dist_avg", t_avg, res["avg"]),
                              ("dist_std", t_std, res["std"])):
        if tval is None:
            continue
        rows.append(dict(base, parametro=pname, verdadero=f"{tval:.4f}",
                         ajustado=f"{fval:.4f}",
                         abs_delta=f"{abs(fval - tval):.4f}",
                         convergido="si"))
    return rows


def fit_all() -> None:
    rows = []
    for cid, spec in CASES.items():
        vj = LDIR / cid / "verdad.json"
        if not vj.exists():
            continue
        info = json.loads(vj.read_text())
        mom = info.get("momentos_verdad") or {}
        t_avg, t_std = mom.get("avg"), mom.get("std")
        if spec.get("pneg"):
            t_avg, t_std = truth_pneg_moments(*spec["pneg"], spec["fit"])
        if spec.get("truth_avg"):
            t_avg, t_std = spec["truth_avg"], spec["truth_std"]
        for version in ("v0", "v1"):
            res = fit_one(cid, version)
            rows += _rows_for(cid, version, res, t_avg, t_std, spec["nota"])
            if res and "error" not in res:
                (LDIR / cid / f"fitbauer_{version}_moments.json").write_text(
                    json.dumps({k: res[k] for k in ("avg", "std")}, indent=1))
        # L1: además forma binomial paramétrica (p libre)
        if cid.startswith("L1"):
            res = fit_one(cid, "v0", shape="binomial", tag="v0_binom")
            rows += _rows_for(cid, "v0_binom", res, t_avg, t_std,
                              spec["nota"] + " (forma binomial)")
            if res and "error" not in res:
                msg = (res.get("summary") or {}).get("message", "")
                m = re.search(r"p=([\d.eE+-]+)", msg)
                if m:
                    pf = float(m.group(1))
                    rows.append({"serie": "L", "caso": cid,
                                 "version": "v0_binom", "parametro": "binom_p",
                                 "verdadero": f"{spec['p_true']:.4f}",
                                 "ajustado": f"{pf:.4f}",
                                 "abs_delta": f"{abs(pf - spec['p_true']):.4f}",
                                 "convergido": "si", "nota": spec["nota"]})
    append_rows(rows)
    dedupe_resumen()
    print(f"[L] {len(rows)} filas")


# ── L5: re-ajustes de J con formas paramétricas y regularizadores ────────────

def fit_L5() -> None:
    import serie_J
    rows = []
    for cid, spec in serie_J.CASES.items():
        vj = serie_J.JDIR / cid / "verdad.json"
        if not vj.exists():
            continue
        info = json.loads(vj.read_text())
        mom = info.get("momentos_verdad") or {}
        t_avg, t_std = mom.get("avg"), mom.get("std")
        if cid.startswith("J1"):
            res = serie_J.fit_case(cid, "v0", extra=["--shape", "gaussiana"],
                                   tag="v0_gauss")
            ver, nota = "v0_gauss", spec["nota"] + " (forma gaussiana)"
        elif cid.startswith("J2"):
            res = serie_J.fit_case(
                cid, "v0", extra=["--shape", "vbf", "--vbf-components", "2"],
                tag="v0_vbf2")
            ver, nota = "v0_vbf2", spec["nota"] + " (VBF N=2)"
        else:
            continue
        base = {"serie": "J", "caso": cid, "version": ver, "nota": nota}
        if res is None or "error" in res:
            rows.append(dict(base, parametro="-", convergido="no",
                             nota=(res or {}).get("error", "sin datos")[:150]))
            continue
        for pname, tval, fval in (("dist_avg", t_avg, res["avg"]),
                                  ("dist_std", t_std, res["std"])):
            if tval is None:
                continue
            rows.append(dict(base, parametro=pname, verdadero=f"{tval:.4f}",
                             ajustado=f"{fval:.4f}",
                             abs_delta=f"{abs(fval - tval):.4f}",
                             convergido="si"))
        if spec.get("bimodal") and "error" not in res:
            pk = peaks(np.array(res["v"]), np.array(res["P"]))
            pk_pos = sorted(x for x, _ in pk)
            for j, tpos in enumerate(spec["bimodal"], 1):
                fpos = (min(pk_pos, key=lambda x: abs(x - tpos))
                        if pk_pos else float("nan"))
                rows.append(dict(base, parametro=f"pico{j}_B",
                                 verdadero=f"{tpos:.2f}", ajustado=f"{fpos:.2f}",
                                 abs_delta=f"{abs(fpos - tpos):.3f}",
                                 convergido="si"))
    # regularizadores extremos sobre J1_b30_s3 v1
    cid = "J1_b30_s3"
    info = json.loads((serie_J.JDIR / cid / "verdad.json").read_text())
    t_avg = info["momentos_verdad"]["avg"]
    t_std = info["momentos_verdad"]["std"]
    for reg in ("tv", "maxent"):
        res = serie_J.fit_case(cid, "v1", extra=["--reg-mode", reg],
                               tag=f"v1_{reg}")
        if res and "error" not in res:
            for pname, tval, fval in (("dist_avg", t_avg, res["avg"]),
                                      ("dist_std", t_std, res["std"])):
                rows.append({"serie": "J", "caso": cid, "version": f"v1_{reg}",
                             "parametro": pname, "verdadero": f"{tval:.4f}",
                             "ajustado": f"{fval:.4f}",
                             "abs_delta": f"{abs(fval - tval):.4f}",
                             "convergido": "si",
                             "nota": f"regularizador {reg}"})
    append_rows(rows)
    dedupe_resumen()
    print(f"[L5] {len(rows)} filas")


if __name__ == "__main__":
    force = "--force" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not only or "gen" in only:
        generate(force=force)
    if not only or "fit" in only:
        fit_all()
    if not only or "L5" in only:
        fit_L5()
