#!/usr/bin/env python3
"""Bloque J: distribuciones P(BHF)/P(ΔEQ) — NORMOS-DIST genera, Fitbauer ajusta.

Semántica de DIST descifrada por sondas (sin manual):
- Bloques: NDSS, NSB(k) puntos desde BHF(k) con paso DTB(k) (o DTQ para ΔEQ).
- DISTRI=2 → gaussiana con centro AVG(k) y anchura STG(k).
- DTI(k) = incremento de ISO por punto → correlación lineal δ(B) (análogo de
  delta_slope en Fitbauer, en mm/s por punto; con DTB=1 T equivale a mm/s/T).
- SIMULT=.TRUE. genera el espectro (bloque 2 del .PLT = −absorción); la
  amplitud absoluta es arbitraria pero el modelo es lineal en P → se escala en
  Python a profundidad 5 % (exacto).
- La verdad P se lee de la "Table of relative areas" del .RES (por bloque,
  cada bloque normalizado a 100 → bloques de área igual).

Ajuste Fitbauer: fit_bhf_distribution_cli.py (histograma Hesse-Rübartsch,
Tikhonov, α por L-curve --scan-alpha), --variable bhf o quad, --delta-slope
para J4. Métricas comparadas: media y desviación estándar de P (ponderadas),
posiciones/alturas de picos en bimodales.
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

JDIR = VALID_ROOT / "J"
DEPTH = 0.05          # profundidad de pico del v0 (escala libre, modelo lineal)
BASE = 1_000_000


# ── Definición de casos ──────────────────────────────────────────────────────

def _bloque(bhf0, nsb, avg, stg, dtb=1.0, iso=0.0, qua=0.0, wid=0.30,
            dti=0.0, dtq=0.0, k=1):
    ln = [f"NSB({k})={nsb},",
          f"BHF({k})={bhf0}, DTB({k})={dtb},",
          f"ISO({k})={iso}, QUA({k})={qua}, WID({k})={wid},",
          f"AVG({k})={avg}, STG({k})={stg},"]
    if dti:
        ln.append(f"DTI({k})={dti},")
    if dtq:
        ln.append(f"DTQ({k})={dtq},")
    return ln


CASES: dict[str, dict] = {}
for avg in (25.0, 30.0, 35.0):
    for stg in (1.5, 3.0, 5.0):
        CASES[f"J1_b{avg:g}_s{stg:g}"] = {
            "plines": ["NDSS=1,", "DISTRI=2,"] + _bloque(8.0, 41, avg, stg),
            "var": "bhf", "truth_avg": avg, "truth_std": stg,
            "nota": f"gaussiana <B>={avg} sigma={stg}"}
CASES["J2_bimodal_sim"] = {
    "plines": ["NDSS=2,", "DISTRI=2,"]
    + _bloque(18.0, 20, 28.0, 2.0, k=1) + _bloque(36.0, 20, 45.0, 2.0, k=2),
    "var": "bhf", "bimodal": (28.0, 45.0),
    "nota": "bimodal simetrica 28/45 sigma 2/2"}
CASES["J2_bimodal_asim"] = {
    "plines": ["NDSS=2,", "DISTRI=2,"]
    + _bloque(16.0, 20, 26.0, 1.5, k=1) + _bloque(34.0, 21, 44.0, 3.5, k=2),
    "var": "bhf", "bimodal": (26.0, 44.0),
    "nota": "bimodal asimetrica 26/44 sigma 1.5/3.5"}
# J3: P(ΔEQ). El DTQ del demo de DIST está inoperante (sonda K1: efecto
# cero) → se genera con SITE: 10 dobletes con áreas gaussianas (verdad
# discreta exacta de 10 puntos; NSUB≤10 del demo).
_QGRID = np.arange(0.4, 2.66, 0.25)          # 10 puntos
for avg, stg in ((1.0, 0.4), (1.5, 0.5)):
    _P = np.exp(-0.5 * ((_QGRID - avg) / stg) ** 2)
    _P = _P / _P.sum()
    CASES[f"J3_quad_a{avg:g}"] = {
        "site_doublets": [{"nline": 2, "iso": 0.35, "qua": round(float(q), 3),
                           "wid": 0.25, "dep": round(0.20 * float(p), 5)}
                          for q, p in zip(_QGRID, _P)],
        "var": "quad", "delta": 0.35,
        "truth_table": {"var": [float(q) for q in _QGRID],
                        "P": [float(p) for p in _P]},
        "nota": f"P(DeltaEQ) discreta 10 puntos <Q>={avg} sigma={stg} (via SITE)"}
for dti in (0.005, 0.01):
    CASES[f"J4_dti{dti:g}"] = {
        "plines": ["NDSS=1,", "DISTRI=2,"] + _bloque(8.0, 41, 30.0, 3.0, dti=dti),
        "var": "bhf", "truth_avg": 30.0, "truth_std": 3.0, "slope": dti,
        "nota": f"correlacion delta(B) DTI={dti} mm/s/T"}


# ── Generación con DIST ──────────────────────────────────────────────────────

def parse_dist_tables(res_text: str) -> list[dict]:
    """Tablas 'Table of relative areas' por bloque: (var, P, IS)."""
    tables = []
    for chunk in res_text.split("Table of relative areas")[1:]:
        rows = re.findall(
            r"^\s+\d+\s+([-\d.]+)\s+([-\d.]+)\s+[-\d.]+\s+([-\d.]+)\s+I",
            chunk, re.M)
        if rows:
            tables.append({
                "var": [float(r[0]) for r in rows],
                "P": [float(r[1]) for r in rows],
                "IS": [float(r[2]) for r in rows]})
    return tables


def truth_moments(tables: list[dict]) -> tuple[float, float]:
    """Media y std de la variable, bloques con áreas iguales (P a 100 cada uno)."""
    v = np.concatenate([np.array(t["var"]) for t in tables])
    p = np.concatenate([np.array(t["P"]) for t in tables])
    p = np.maximum(p, 0.0)
    p = p / p.sum()
    avg = float(np.sum(p * v))
    std = float(np.sqrt(np.sum(p * (v - avg) ** 2)))
    return avg, std


def generate_J3_site(force: bool = False) -> None:
    """J3 vía SITE: 10 dobletes con pesos gaussianos, todo fijo."""
    from normos_lib import site_params, parse_plt
    stg_dir = STAGING_ROOT / "J3site"
    pend = [cid for cid, s in CASES.items() if "site_doublets" in s
            and (force or not (JDIR / cid / "v0.dat").exists())]
    if not pend:
        return
    if stg_dir.exists():
        shutil.rmtree(stg_dir)
    stg_dir.mkdir(parents=True)
    stems = {}
    for k, cid in enumerate(pend):
        stem = f"Q{k:03d}"
        stems[cid] = stem
        comps = CASES[cid]["site_doublets"]
        (stg_dir / f"{stem}.MOS").write_bytes(
            ws5_text(dummy_counts()).encode("ascii"))
        jt = job_text(stem, {"VMAX": "6.0", "PFP": "256.5"},
                      site_params(len(comps), comps), "Bloque J3", cid[:60])
        (stg_dir / f"{stem}.JOB").write_bytes(jt.encode("ascii"))
    print(f"[J3] {run_dosbox_batch(stg_dir, list(stems.values()), exe='SITE')}")
    for cid, stem in stems.items():
        cdir = JDIR / cid
        cdir.mkdir(parents=True, exist_ok=True)
        for ext in (".MOS", ".JOB", ".RES", ".PLT"):
            f = stg_dir / f"{stem}{ext}"
            if f.exists():
                shutil.copy2(f, cdir / f"SITE{ext}")
        p = parse_plt(cdir / "SITE.PLT", np_ch=256)
        theory = p["fit"]
        np.save(cdir / "teoria_norm.npy", theory)
        write_adt(cdir / "v0.dat", unfold_theory(theory, BASE))
        rng = np.random.default_rng(zlib.crc32(cid.encode()) & 0x7FFFFFFF)
        write_adt(cdir / "v1.dat", unfold_theory(theory, BASE, rng=rng))
        spec = CASES[cid]
        t = spec["truth_table"]
        v = np.array(t["var"]); pp = np.array(t["P"])
        avg = float(np.sum(pp * v))
        std = float(np.sqrt(np.sum(pp * (v - avg) ** 2)))
        info = {"caso": cid, "serie": "J", "vmax": 6.0, "generador": "SITE",
                "comps": spec["site_doublets"], "tablas_P": [t],
                "momentos_verdad": {"avg": avg, "std": std},
                "nota": spec["nota"]}
        (cdir / "verdad.json").write_text(
            json.dumps(info, indent=1, ensure_ascii=False))


def generate(force: bool = False) -> None:
    stg_dir = STAGING_ROOT / "J"
    pend = [cid for cid in CASES if "site_doublets" not in CASES[cid]
            and (force or not (JDIR / cid / "v0.dat").exists())]
    if not pend:
        print("[J] generación: nada pendiente")
        return
    if stg_dir.exists():
        shutil.rmtree(stg_dir)
    stg_dir.mkdir(parents=True)
    stems = {}
    for k, cid in enumerate(pend):
        stem = f"D{k:03d}"
        stems[cid] = stem
        (stg_dir / f"{stem}.MOS").write_bytes(
            ws5_text(dummy_counts()).encode("ascii"))
        jt = job_text(stem, {"VMAX": "10.0", "PFP": "256.5",
                             "SIMULT": ".TRUE."},
                      CASES[cid]["plines"], "Bloque J", cid[:60])
        (stg_dir / f"{stem}.JOB").write_bytes(jt.encode("ascii"))
    print(f"[J] {run_dosbox_batch(stg_dir, list(stems.values()), exe='DIST')}")
    for cid, stem in stems.items():
        cdir = JDIR / cid
        cdir.mkdir(parents=True, exist_ok=True)
        for ext in (".MOS", ".JOB", ".RES", ".PLT"):
            f = stg_dir / f"{stem}{ext}"
            if f.exists():
                shutil.copy2(f, cdir / f"DIST{ext}")
        plt_f = cdir / "DIST.PLT"
        info = dict(CASES[cid])
        info.pop("plines")
        info.update({"caso": cid, "serie": "J", "vmax": 10.0,
                     "dist_version": "09.09.1993", "depth_escalada": DEPTH})
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
            avg, std = truth_moments(tables)
            info["momentos_verdad"] = {"avg": avg, "std": std}
        (cdir / "verdad.json").write_text(
            json.dumps(info, indent=1, ensure_ascii=False))


# ── Ajuste con Fitbauer ──────────────────────────────────────────────────────

def fit_case(cid: str, version: str, extra: list[str] | None = None,
             tag: str | None = None) -> dict | None:
    cdir = JDIR / cid
    dat = cdir / f"{version}.dat"
    if not dat.exists():
        return None
    spec = CASES[cid]
    prefix = cdir / f"fit_{tag or version}"
    # El CLI de distribución requiere numpy>=2 (np.trapezoid): usar el venv
    # del repo, no el python del sistema.
    venv_py = FITBAUER_ROOT / ".venv" / "bin" / "python"
    py = str(venv_py) if venv_py.exists() else sys.executable
    vmax = "6" if "site_doublets" in spec else "10"
    cmd = [py, str(FITBAUER_ROOT / "fit_bhf_distribution_cli.py"),
           str(dat), "--out-prefix", str(prefix), "--vmax", vmax]
    if not (extra and ("--alpha" in extra or "--shape" in extra)):
        cmd.append("--scan-alpha")
    if spec["var"] == "bhf":
        cmd += ["--variable", "bhf", "--bmin", "5", "--bmax", "52",
                "--nbins", "47", "--gamma", "0.30"]
        if spec.get("slope"):
            # delta del kernel FIJO: debe valer el delta verdadero en la
            # referencia H_ref = media de la malla (28.5 T); la verdad de DIST
            # es delta(B) = (B - 8)·DTI.
            cmd += ["--delta", f"{(28.5 - 8.0) * spec['slope']:.4f}"]
    else:
        cmd += ["--variable", "quad", "--fixed-bhf", "0", "--bmin", "0",
                "--bmax", "3.6", "--nbins", "24", "--gamma", "0.25",
                "--delta", str(spec.get("delta", 0.0))]
    if spec.get("slope") and (extra is None or "--delta-slope" not in extra):
        cmd += ["--delta-slope", str(spec["slope"])]
    cmd += extra or []
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                       cwd=str(FITBAUER_ROOT))
    dist_f = Path(f"{prefix}_distribution.dat")
    summ_f = Path(f"{prefix}_summary.json")
    if r.returncode != 0 or not dist_f.exists():
        return {"error": (r.stderr or r.stdout)[-300:]}
    cols = np.loadtxt(dist_f)
    v, p = cols[:, 0], np.maximum(cols[:, 1], 0.0)
    if p.sum() <= 0:
        return {"error": "P ajustada nula"}
    pn = p / p.sum()
    avg = float(np.sum(pn * v))
    std = float(np.sqrt(np.sum(pn * (v - avg) ** 2)))
    out = {"avg": avg, "std": std, "v": v.tolist(), "P": pn.tolist()}
    if summ_f.exists():
        try:
            out["summary"] = json.loads(summ_f.read_text())
        except Exception:
            pass
    return out


def peaks(v: np.ndarray, p: np.ndarray) -> list[tuple[float, float]]:
    from scipy.signal import find_peaks
    idx, _ = find_peaks(p, height=0.15 * p.max(), distance=3)
    return [(float(v[i]), float(p[i])) for i in idx]


def fit_all() -> None:
    rows = []
    for cid, spec in CASES.items():
        info = json.loads((JDIR / cid / "verdad.json").read_text())
        t_avg, t_std = (info.get("momentos_verdad") or {}).get("avg"), \
                       (info.get("momentos_verdad") or {}).get("std")
        for version in ("v0", "v1"):
            res = fit_case(cid, version)
            base_row = {"serie": "J", "caso": cid, "version": version,
                        "nota": spec["nota"]}
            if res is None:
                continue
            if "error" in res:
                rows.append(dict(base_row, parametro="-", convergido="no",
                                 nota=res["error"][:150]))
                continue
            (JDIR / cid / f"fitbauer_{version}_moments.json").write_text(
                json.dumps({k: res[k] for k in ("avg", "std")} |
                           {"n_alpha_scan": True}, indent=1))
            for pname, tval, fval in (("dist_avg", t_avg, res["avg"]),
                                      ("dist_std", t_std, res["std"])):
                if tval is None:
                    continue
                rows.append(dict(base_row, parametro=pname,
                                 verdadero=f"{tval:.4f}",
                                 ajustado=f"{fval:.4f}",
                                 abs_delta=f"{abs(fval - tval):.4f}",
                                 convergido="si"))
            if spec.get("bimodal"):
                pk = peaks(np.array(res["v"]), np.array(res["P"]))
                pk_pos = sorted(x for x, _ in pk)
                for j, tpos in enumerate(spec["bimodal"], 1):
                    fpos = min(pk_pos, key=lambda x: abs(x - tpos)) if pk_pos else float("nan")
                    rows.append(dict(base_row, parametro=f"pico{j}_B",
                                     verdadero=f"{tpos:.2f}",
                                     ajustado=f"{fpos:.2f}",
                                     abs_delta=f"{abs(fpos - tpos):.3f}",
                                     convergido="si",
                                     nota=spec["nota"] + f" ({len(pk)} picos)"))
        # J4: ajuste adicional ignorando la correlación (sesgo esperado)
        if spec.get("slope"):
            res0 = fit_case(cid, "v0", extra=["--delta-slope", "0"],
                            tag="v0_sin_slope")
            if res0 and "error" not in res0:
                rows.append({"serie": "J", "caso": cid,
                             "version": "v0_sin_slope", "parametro": "dist_std",
                             "verdadero": f"{t_std:.4f}",
                             "ajustado": f"{res0['std']:.4f}",
                             "abs_delta": f"{abs(res0['std'] - t_std):.4f}",
                             "convergido": "si",
                             "nota": "correlacion delta(B) ignorada"})
    append_rows(rows)
    dedupe_resumen()
    print(f"[J] {len(rows)} filas de comparación")


def fit_J5_alphas() -> None:
    """J5: sensibilidad al parámetro de regularización (v1 de J1_b30_s3)."""
    rows = []
    cid = "J1_b30_s3"
    info = json.loads((JDIR / cid / "verdad.json").read_text())
    t_avg = info["momentos_verdad"]["avg"]
    t_std = info["momentos_verdad"]["std"]
    for alpha in (0.01, 1.0, 100.0):
        res = fit_case(cid, "v1", extra=["--alpha", str(alpha)],
                       tag=f"v1_a{alpha:g}")
        if res is None or "error" in res:
            continue
        # quitar --scan-alpha no es posible via extra: la CLI ignora --alpha si
        # scan esta activo? se pasa igualmente; se registra el resultado.
        rows.append({"serie": "J", "caso": cid, "version": f"v1_a{alpha:g}",
                     "parametro": "dist_std", "verdadero": f"{t_std:.4f}",
                     "ajustado": f"{res['std']:.4f}",
                     "abs_delta": f"{abs(res['std'] - t_std):.4f}",
                     "convergido": "si",
                     "nota": f"J5 alpha={alpha} (regularizacion)"})
    append_rows(rows)
    dedupe_resumen()
    print(f"[J5] {len(rows)} filas")


if __name__ == "__main__":
    force = "--force" in sys.argv
    generate(force=force)
    generate_J3_site(force=force)
    fit_all()
    fit_J5_alphas()
