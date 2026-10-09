#!/usr/bin/env python3
"""Sonda de la relajación de Ising de SITE, con los parámetros del manual.

La sonda de agosto (serie X1) usaba ``IRELAX=.TRUE.`` escalar y
``BH0(1)=33`` con ``BHF(1)=33``. Según el manual (Brand 1990) ``IRELAX(i)``
es por subespectro y el momento relativo es ``BHF/BSAT``; el binario demo
1994 no reconoce ``BSAT`` pero sí ``BH0``, que hace ese papel. Con
``BHF = BH0`` el momento relativo es 1 (polarización total): un solo estado,
sin intercambio, y el espectro no puede depender de la tasa ``OME``.

Aquí se barre ``OME`` (MHz, según el manual) para tres ``BH0``:
33 T (P=1), 66 T (P=0.5) y 1e4 T (P≈0), y se compara cada curva con el
sextete estático sin relajación (REF).

Salida: ``validacion/sonda_relajacion/`` con las curvas (.npz) y un resumen.
Uso:  python validacion/generador/sonda_relajacion.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from normos_lib import (STAGING_ROOT, VALID_ROOT, dummy_counts, job_text,
                        parse_plt, run_dosbox_batch, site_params, ws5_text)

STG = STAGING_ROOT / "relax"
OUT = VALID_ROOT / "sonda_relajacion"

SEXT = {"nline": 6, "iso": 0.0, "qua": 0.0, "bhf": 33.0, "wid": 0.25,
        "dep": 0.05, "d13": 3.0, "d23": 2.0}
OMES = (0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)
BH0S = (33.0, 66.0, 1.0e4)


def casos() -> dict[str, list[str]]:
    """nombre → líneas &PARAM extra del subespectro 1."""
    out = {"REF": []}
    for bh0 in BH0S:
        for ome in OMES:
            out[f"B{bh0:g}_O{ome:g}"] = ["IRELAX(1)=.TRUE.,", f"OME(1)={ome},",
                                         f"BH0(1)={bh0},"]
    return out


def main() -> None:
    if STG.exists():
        shutil.rmtree(STG)
    STG.mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    nombres = list(casos())
    for k, name in enumerate(nombres):
        stem = f"R{k:03d}"
        (STG / f"{stem}.MOS").write_bytes(ws5_text(dummy_counts()).encode("ascii"))
        comp = dict(SEXT, raw=casos()[name])
        jt = job_text(stem, {"VMAX": "10.0", "PFP": "256.5"},
                      site_params(1, [comp]), "Sonda relajacion", name)
        (STG / f"{stem}.JOB").write_bytes(jt.encode("ascii"))
    print(run_dosbox_batch(STG, [f"R{k:03d}" for k in range(len(nombres))]))

    curvas = {}
    for k, name in enumerate(nombres):
        plt_f = STG / f"R{k:03d}.PLT"
        if plt_f.exists():
            d = parse_plt(plt_f)
            curvas[name] = np.asarray(d["fit"], dtype=float)
            if "v" not in curvas and d.get("velocity") is not None:
                curvas["v"] = np.asarray(d["velocity"], dtype=float)
    np.savez(OUT / "curvas.npz", **curvas)

    ref = curvas.get("REF")
    lineas = []
    for name in nombres[1:]:
        c = curvas.get(name)
        if c is None or ref is None:
            lineas.append(f"{name:14s} SIN PLT")
            continue
        prof = 1.0 - c.min() / np.median(c)
        lineas.append(f"{name:14s} Δmax vs REF = {np.max(np.abs(c - ref)) / np.ptp(ref):.3e}"
                      f"  prof. máx = {prof:.4f}")
    txt = "\n".join(lineas)
    (OUT / "resumen.txt").write_text(txt + "\n", encoding="utf-8")
    print(txt)
    for f in STG.iterdir():
        if f.suffix in (".RES", ".JOB", ".PLT"):
            shutil.copy2(f, OUT / f.name)


if __name__ == "__main__":
    main()
