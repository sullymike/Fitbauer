#!/usr/bin/env python3
"""Validación de las mejoras v4.19 contra el banco (re-ajustes v0m/v0h).

1. K3 cristal único: re-ajuste con quad_treatment="hamiltonian_sc" y los
   ángulos BEX/GAX verdaderos → ¿desaparece el sesgo de intensidades?
2. K2 fondo cúbico + caso nuevo cuártico (BKG(5)): re-ajuste con
   curv3/curv4 libres.
3. L4 EXACT: re-ajuste con --kernel-treatment hamiltoniano (--quad = QUP,
   η=0) y --d23 3 (textura efectiva del demo).
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from runner import (Case, append_rows, dedupe_resumen, fit_case,
                    generate_series)
from series_AB import _sg
from series_KL import K3, K2


def refit_K3() -> None:
    # gax de Fitbauer = GAX de SITE + 90° (convención medida teoría-contra-
    # teoría: el GAX del demo se mide desde el eje y del EFG).
    angles = {"K3_sc_b0_g0": (0.0, 90.0), "K3_sc_b547_g0": (54.7, 90.0),
              "K3_sc_b90_g0": (90.0, 90.0), "K3_sc_b90_g90": (90.0, 180.0)}
    rows = []
    for case in K3:
        if case.cid not in angles:
            continue
        c2 = copy.deepcopy(case)
        bex, gax = angles[case.cid]
        c2.comps = [dict(c2.comps[0], bex=bex, gax=gax)]
        c2.comps[0].pop("raw", None)
        c2.fit_kwargs = dict(c2.fit_kwargs, quad_treatment="hamiltonian_sc",
                             free_intensities=False)
        c2.nota += " [v0m: hamiltonian_sc con BEX/GAX verdaderos]"
        rows += fit_case("K3", c2, "v0m", data_version="v0")
    append_rows(rows)
    ok = [r for r in rows if r.get("convergido") == "si"]
    print(f"[K3] v0m cristal único: {len(rows)} filas ({len(ok)} ok)")
    for r in rows:
        if r["parametro"] in ("s1_bhf", "s1_quad", "s1_delta"):
            print(f"  {r['caso']:16s} {r['parametro']:9s} "
                  f"{r['verdadero']:>9s} -> {r['ajustado']:>9s} "
                  f"|d| {r['abs_delta']} chi2 {r['chi2red']}")


def refit_K2() -> None:
    # caso nuevo: fondo cuártico BKG(5)=60
    vmax = 4.0
    quart = Case("K2_cuartico", [_sg(iso=0.3)], vmax=vmax,
                 param_extra=["BKG(5)=60., BKGFIT(5)=.FALSE.,"],
                 truth_override={"curv4": 60.0 / 1000.0 / (2 * vmax) ** 4},
                 fit_kwargs={"extra_model": {"free_curv4": True}},
                 nota="fondo cuartico BKG(5)=60")
    generate_series("K2", [quart])
    rows = fit_case("K2", quart, "v0")
    # re-ajuste del cúbico con curv3 libre
    cub = copy.deepcopy(next(c for c in K2 if c.cid == "K2_cubico"))
    cub.truth_override = {"curv3": 60.0 / 1000.0 / (2 * vmax) ** 3}
    cub.fit_kwargs = {"extra_model": {"free_curv": True, "free_curv3": True}}
    cub.nota = "fondo cubico BKG(4)=60 [v0m: curv3 libre]"
    rows += fit_case("K2", cub, "v0m", data_version="v0")
    append_rows(rows)
    for r in rows:
        print(f"  {r['caso']:14s} {r['version']:4s} {r['parametro']:9s} "
              f"{r['verdadero']:>11s} -> {r['ajustado']:>11s} "
              f"chi2 {r['chi2red']}")


def refit_L4() -> None:
    from serie_L import CASES, fit_one, _rows_for
    rows = []
    for qup in ("0.2", "0.5", "1"):
        cid = f"L4_exact_q{qup}"
        spec = CASES[cid]
        res = fit_one(cid, "v0", tag="v0h",
                      extra=["--kernel-treatment", "hamiltoniano",
                             "--quad", qup, "--d23", "3.0"])
        rr = _rows_for(cid, "v0h", res, spec["truth_avg"], spec["truth_std"],
                       spec["nota"] + " [v0h: kernel hamiltoniano QUP]")
        rows += rr
        for r in rr:
            print(f"  {r['caso']:16s} {r['parametro']:9s} "
                  f"{r['verdadero']} -> {r['ajustado']} |d| {r['abs_delta']}")
    append_rows(rows)
    dedupe_resumen()


if __name__ == "__main__":
    only = sys.argv[1:] or ["K3", "K2", "L4"]
    if "K3" in only:
        refit_K3()
    if "K2" in only:
        refit_K2()
    if "L4" in only:
        refit_L4()
    dedupe_resumen()
