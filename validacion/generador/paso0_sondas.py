#!/usr/bin/env python3
"""Sondas de capacidades de SITE (sin manual): ¿qué hace cada interruptor?

Genera pares de casos mínimos que difieren en un solo parámetro y mide si la
curva teórica cambia y qué eco deja el .RES. Resultados → paso0/sondas.txt.
"""
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from normos_lib import (STAGING_ROOT, VALID_ROOT, dummy_counts, job_text,
                        parse_plt, parse_res, run_dosbox_batch, site_params,
                        ws5_text)

STG = STAGING_ROOT / "sondas"
OUT = VALID_ROOT / "paso0"

SEXT = {"nline": 6, "iso": 0.0, "qua": 1.0, "bhf": 6.2, "wid": 0.25,
        "dep": 0.05, "d13": 3.0, "d23": 2.0}

PROBES: dict[str, tuple[dict, list[str] | None, list[dict] | None]] = {
    # nombre: (&DATA extra, &PARAM extra, comps override)
    "REF":    ({}, None, None),                      # sexteto R=1 sin ángulo
    "THE30":  ({}, None, [dict(SEXT, the=30.0)]),    # ¿THE activa Hamiltoniano?
    "THE0":   ({}, None, [dict(SEXT, the=0.0)]),
    "THE90":  ({}, None, [dict(SEXT, the=90.0)]),
    "HAM30":  ({"HAMILT": ".TRUE."}, None, [dict(SEXT, the=30.0)]),
    "HAMREF": ({"HAMILT": ".TRUE."}, None, None),    # HAMILT sin THE
    "ETA05":  ({"HAMILT": ".TRUE."}, None, [dict(SEXT, the=30.0, eta=0.5)]),
    "ETAPHI": ({"HAMILT": ".TRUE."}, None,
               [dict(SEXT, the=30.0, eta=0.5, phi=45.0)]),
    # anchuras por par e intensidades de doblete
    "W1323":  ({}, None, [dict(SEXT, qua=0.0, bhf=33.0,
                               raw=["W13(1)=1.5, W13FIT(1)=.FALSE.,",
                                    "W23(1)=1.2, W23FIT(1)=.FALSE.,"])]),
    "DOBREF": ({"VMAX": "4.0"}, None,
               [{"nline": 2, "iso": 0.35, "qua": 1.2, "wid": 0.25, "dep": 0.05}]),
    "D21X":   ({"VMAX": "4.0"}, None,
               [{"nline": 2, "iso": 0.35, "qua": 1.2, "wid": 0.25, "dep": 0.05,
                 "raw": ["D21(1)=0.6, D21FIT(1)=.FALSE.,"]}]),
    # transmisión e isótopo
    "IFTRAN": ({"IFTRAN": ".TRUE."}, None,
               [{"nline": 1, "iso": 0.3, "wid": 0.25, "dep": 0.05,
                 "raw": ["TAB(1)=5.0, TABFIT(1)=.FALSE.,"]}]),
    "SN119":  ({"EGAMMA": "23.871", "SG": "0.5", "SEX": "1.5",
                "GFACT": "-1.046"}, None,
               [{"nline": 2, "iso": 2.56, "qua": 1.5, "wid": 0.4, "dep": 0.05}]),
}


def main() -> None:
    if STG.exists():
        shutil.rmtree(STG)
    STG.mkdir(parents=True)
    stems = []
    for k, (name, (dx, px, comps)) in enumerate(PROBES.items()):
        stem = f"S{k:02d}"
        stems.append(stem)
        (STG / f"{stem}.MOS").write_bytes(ws5_text(dummy_counts()).encode("ascii"))
        data = {"VMAX": "10.0", "PFP": "256.5"}
        data.update(dx)
        cc = comps if comps is not None else [dict(SEXT)]
        jt = job_text(stem, data, site_params(len(cc), cc, extra=px),
                      "Sonda", name)
        (STG / f"{stem}.JOB").write_bytes(jt.encode("ascii"))
    print(run_dosbox_batch(STG, stems))

    curves = {}
    lines = []
    for k, name in enumerate(PROBES):
        stem = f"S{k:02d}"
        plt_f = STG / f"{stem}.PLT"
        res = parse_res(STG / f"{stem}.RES") if (STG / f"{stem}.RES").exists() else {}
        if plt_f.exists():
            curves[name] = parse_plt(plt_f)["fit"]
            status = "OK"
        else:
            status = "SIN PLT"
        lines.append(f"{name:8s} {status:8s} avisos={res.get('warnings', [])[:2]}")
    ref = curves.get("REF")
    for name, c in curves.items():
        if ref is not None and name != "REF" and c.size == ref.size:
            d = float(np.max(np.abs(c - ref)))
            lines.append(f"Δmax({name} vs REF) = {d:.3e}")
    for a, b in [("THE30", "HAM30"), ("THE30", "THE0"), ("THE0", "REF"),
                 ("ETA05", "HAM30"), ("ETAPHI", "ETA05"), ("HAMREF", "REF"),
                 ("D21X", "DOBREF")]:
        if a in curves and b in curves and curves[a].size == curves[b].size:
            d = float(np.max(np.abs(curves[a] - curves[b])))
            lines.append(f"Δmax({a} vs {b}) = {d:.3e}")
    txt = "\n".join(lines)
    (OUT / "sondas.txt").write_text(txt + "\n", encoding="utf-8")
    print(txt)
    for f in STG.iterdir():
        if f.suffix in (".RES", ".JOB", ".PLT"):
            shutil.copy2(f, OUT / f"sonda_{f.name}")


if __name__ == "__main__":
    main()
