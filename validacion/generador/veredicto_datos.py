#!/usr/bin/env python3
"""Síntesis global del resumen.csv para el informe-veredicto final.

Imprime, por bloque temático y clase de parámetro, la mediana y el p95 de
|Δ| (v0/v0m según toque), el nº de casos fuera de tolerancia del plan y los
peores casos — la base numérica de VEREDICTO.md.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from analisis import load_rows, tol_v0

# bloque temático → (series, versión preferida por caso)
BLOQUES = {
    "1er orden (singletes/dobletes/sextetos)": (
        ["A1a", "A1b", "A1c", "A2", "A3a", "A3b", "A3c"], ("v0",)),
    "Hamiltoniano completo (axial y eta)": (["A4", "A5", "A6"], ("v0m", "v0")),
    "Lineas libres / anchuras": (["A7", "C1", "C2", "C3", "C4"], ("v0",)),
    "Textura e intensidades": (["B1", "B2", "B3"], ("v0m", "v0")),
    "Multisitio y ligaduras": (["D1", "D2", "D3", "D4", "D5", "D6"], ("v0",)),
    "Adquisicion (base, canales, rango)": (["E1", "E2", "E3", "E4", "E5"],
                                           ("v0m", "v0")),
    "Espesor / transmision": (["F1", "F2"], ("v0m", "v0")),
    "Octetes y fondos v2-v4 (manual)": (["K1", "K2"], ("v0m", "v0")),
    "Cristal unico (hamiltonian_sc, v4.19)": (["K3"], ("v0m", "v0")),
    "Ligaduras nativas SITE": (["K4"], ("v1", "v1_site")),
    "Extremos K5": (["K5"], ("v0m", "v0")),
}


def clase(p: str) -> str:
    for tag, c in (("delta", "posicion"), ("quad", "posicion"),
                   ("bhf", "bhf"), ("gamma", "anchura"),
                   ("depth", "area"), ("int", "intensidad"),
                   ("slope", "fondo"), ("curv", "fondo")):
        if tag in p:
            return c
    return "otro"


def resumen_bloques() -> None:
    rows = load_rows()
    by_case: dict = defaultdict(dict)
    for r in rows:
        if r["parametro"] in ("-",) or r["abs_delta"] is None:
            continue
        by_case[(r["serie"], r["caso"], r["version"])].setdefault(
            r["parametro"], r)
    print(f"{'bloque':42s} {'casos':>5s} {'clase':>10s} {'med|Δ|':>9s} "
          f"{'p95|Δ|':>9s} {'fuera_tol':>9s}")
    for bloque, (series, vers) in BLOQUES.items():
        # por caso: la mejor versión disponible en el orden dado
        sel: dict = {}
        for (s, c, v), params in by_case.items():
            if s not in series:
                continue
            if c in sel and vers.index(sel[c][0]) <= (
                    vers.index(v) if v in vers else 99):
                continue
            if v in vers:
                sel[c] = (v, params)
        por_clase: dict = defaultdict(list)
        fuera: dict = defaultdict(int)
        peores: list = []
        for c, (v, params) in sel.items():
            for p, r in params.items():
                cl = clase(p)
                por_clase[cl].append(r["abs_delta"])
                if r["abs_delta"] > 3 * tol_v0(p, r["verdadero"]):
                    fuera[cl] += 1
                    peores.append((r["abs_delta"], c, v, p))
        first = True
        for cl in ("posicion", "bhf", "anchura", "area", "intensidad",
                   "fondo"):
            if cl not in por_clase:
                continue
            a = np.array(por_clase[cl])
            print(f"{bloque if first else '':42s} "
                  f"{len(sel) if first else '':>5} {cl:>10s} "
                  f"{np.median(a):>9.2g} {np.percentile(a, 95):>9.2g} "
                  f"{fuera.get(cl, 0):>9d}")
            first = False
        for d, c, v, p in sorted(peores, reverse=True)[:3]:
            print(f"{'':42s}   peor: {c} [{v}] {p} |Δ|={d:.3g}")


def resumen_J() -> None:
    rows = [r for r in load_rows() if r["serie"] in ("J", "L")
            and r["parametro"] in ("dist_avg", "dist_std", "binom_p")
            and r["abs_delta"] is not None]
    print("\n── Distribuciones (J + L) ──")
    grupos = {
        "J1 gauss (rejilla + bordes + casi-delta)": lambda c: c.startswith("J1"),
        "J2 bimodales": lambda c: c.startswith("J2"),
        "J3 P(DeltaEQ)": lambda c: c.startswith("J3"),
        "J4 correlacion delta(B)": lambda c: c.startswith("J4"),
        "L1 binomial": lambda c: c.startswith("L1"),
        "L2 Czjzek": lambda c: c.startswith("L2"),
        "L3 PNEG": lambda c: c.startswith("L3"),
        "L4 EXACT": lambda c: c.startswith("L4"),
        "L6 textura D23": lambda c: c.startswith("L6"),
    }
    for gname, pred in grupos.items():
        sel = [r for r in rows if pred(r["caso"])]
        if not sel:
            continue
        for par in ("dist_avg", "dist_std", "binom_p"):
            a = [r["abs_delta"] for r in sel if r["parametro"] == par]
            if not a:
                continue
            peor = max((r for r in sel if r["parametro"] == par),
                       key=lambda r: r["abs_delta"])
            print(f"{gname:40s} {par:9s} med={np.median(a):7.3f} "
                  f"max={max(a):7.3f} (peor: {peor['caso']} "
                  f"[{peor['version']}])")


if __name__ == "__main__":
    resumen_bloques()
    resumen_J()
