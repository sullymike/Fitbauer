#!/usr/bin/env python3
"""Paso 0-bis: verificación de la receta DOSBox+SITE con un singlete trivial.

Comprueba: (1) DOSBox se cierra solo y genera salidas; (2) la curva teórica
del .PLT coincide con una Lorentziana analítica (ISO=0.3, WID=0.25 HWHM,
DEP=5 %); (3) el modo SIMULT y el modo "todo fijo" dan lo mismo; (4) repetir
la ejecución produce salida idéntica (determinismo).
"""
from pathlib import Path
import shutil
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from normos_lib import (DEFAULT_BASE, DEFAULT_VMAX, dummy_counts, job_text,
                        parse_plt, parse_res, run_dosbox_batch, site_params,
                        ws5_text, STAGING_ROOT, VALID_ROOT)

OUT = VALID_ROOT / "paso0"
STG = STAGING_ROOT / "paso0"

ISO, WID, DEP = 0.3, 0.25, 0.05


def build_case(stem: str, extra_data: dict) -> None:
    (STG / f"{stem}.MOS").write_bytes(ws5_text(dummy_counts()).encode("ascii"))
    comps = [{"nline": 1, "iso": ISO, "wid": WID, "dep": DEP}]
    data = {"VMAX": f"{DEFAULT_VMAX:.1f}", "PFP": "256.5"}
    data.update(extra_data)
    txt = job_text(stem, data, site_params(1, comps),
                   "Paso0 singlete trivial", stem)
    (STG / f"{stem}.JOB").write_bytes(txt.encode("ascii"))


def main() -> None:
    if STG.exists():
        shutil.rmtree(STG)
    STG.mkdir(parents=True)
    OUT.mkdir(exist_ok=True)

    build_case("P0FIX", {})                       # todo fijo, modo ajuste
    build_case("P0SIM", {"SIMULT": ".TRUE."})     # modo simulación explícito
    print(run_dosbox_batch(STG, ["P0FIX", "P0SIM"]))

    # Segunda ejecución de P0FIX para determinismo, con otro nombre
    build_case("P0FIX2", {})
    print(run_dosbox_batch(STG, ["P0FIX2"]))

    results = {}
    for stem in ("P0FIX", "P0SIM", "P0FIX2"):
        plt_f = STG / f"{stem}.PLT"
        if not plt_f.exists():
            print(f"[{stem}] SIN PLT — revisar {stem}.RES")
            continue
        p = parse_plt(plt_f)
        r = parse_res(STG / f"{stem}.RES")
        results[stem] = p
        v, fit = p["velocity"], p["fit"]
        # Lorentziana analítica normalizada a baseline 1
        lor = 1.0 - DEP * WID**2 / ((v - ISO) ** 2 + WID**2)
        dmax = float(np.max(np.abs(fit - lor)))
        base_wing = float(np.mean(fit[:10]))
        print(f"[{stem}] NP={p['np']} bloques={p['nblocks']} "
              f"pfp={r.get('pfp')} chi2={r.get('chi2')} "
              f"max|fit-analitica|={dmax:.2e} baseline_ala={base_wing:.6f} "
              f"avisos={r['warnings'][:3]}")

    if "P0FIX" in results and "P0SIM" in results:
        d = np.max(np.abs(results["P0FIX"]["fit"] - results["P0SIM"]["fit"]))
        print(f"FIX vs SIMULT: max|Δfit| = {d:.2e}")
        d2 = np.max(np.abs(results["P0SIM"]["data"] - results["P0SIM"]["fit"]))
        print(f"SIMULT: max|data-fit| = {d2:.2e} (¿data=teoría en simulación?)")
    if "P0FIX" in results and "P0FIX2" in results:
        d = np.max(np.abs(results["P0FIX"]["fit"] - results["P0FIX2"]["fit"]))
        print(f"Determinismo FIX vs FIX2: max|Δfit| = {d:.2e}")

    # Archivar en paso0/
    for f in STG.iterdir():
        if f.suffix != ".EXE":
            shutil.copy2(f, OUT / f.name)
    print(f"Salidas archivadas en {OUT}")


if __name__ == "__main__":
    main()
