#!/usr/bin/env python3
"""Extensión de las series ORIGINALES (A–J) con extremos y centro (3ª tanda).

Las rejillas de la fase 1 eran deliberadamente "centrales"; esta tanda añade
los puntos extremos que faltaban en cada serie ya existente (los casos nuevos
se archivan bajo la MISMA serie para que el análisis los agrupe):

- A1b: Γ=2.0 (línea gigante, vmax ampliado a 6 para no truncar las alas).
- A1c: profundidad 35 %.
- A2: dobletes con δ=−1.0 y δ=+2.0 (×ΔEQ 0.5/2.0) y ΔEQ=0.08 ≪ Γ
  (no resuelto extremo).
- A3a: BHF=0.5 T (colapso más profundo) y 58 T (junto a la cota de 60).
- A3b: QUA=±0.45 (centro entre la rejilla vieja ±0.3 y el extremo ±0.6 de K5).
- A5: η=0.1 (mezcla débil, centro no cubierto; v0 Kündig + v0m hamiltoniano).
- B2: D21=0.3 y 3.0 (asimetría extrema de doblete).
- C1: Γ=0.8 común de sexteto.
- C2: pares invertidos W13=0.7 / W23=1.3 (líneas exteriores más estrechas).
- D3: doblete minoritario del 0.5 % (mitad del límite de detección medido).
- D6: dobletes casi degenerados dΔEQ=0.02 (degeneración práctica).
- J1: gaussianas en los bordes de la malla (⟨B⟩=15 y 45), casi-delta
  (σ=0.8 ≈ paso de malla) y muy ancha (σ=8).
- J4: correlación δ(B) negativa (DTI=−0.01) y fuerte (DTI=0.02).

Cada caso se ajusta en v0 (sin ruido) y v1 (Poisson, semilla CRC32).
"""
from __future__ import annotations

import json
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from runner import (Case, append_rows, dedupe_resumen, fit_case,
                    generate_series, make_v1)
from series_AB import _sx, _db, _sg

VA = 4.0


def seed_for(cid: str, tag: str) -> int:
    return zlib.crc32(f"{cid}|{tag}".encode()) & 0x7FFFFFFF


EXT: dict[str, list[Case]] = {
    "A1b": [Case("A1b_g2.00", [_sg(wid=2.0)], vmax=6.0,
                 nota="singlete Gamma=2.0 (extremo; vmax 6)")],
    "A1c": [Case("A1c_p35pc", [_sg(dep=0.35 * np.pi * 0.25 / 2)], vmax=VA,
                 nota="singlete profundidad 35%")],
    "A2": ([Case(f"A2_d{d:+.2f}_q{q:.2f}", [_db(iso=d, qua=q)], vmax=VA,
                 nota="doblete rejilla ext (delta extremo)")
            for d in (-1.0, 2.0) for q in (0.5, 2.0)]
           + [Case("A2_d0.35_q0.08", [_db(iso=0.35, qua=0.08)], vmax=VA,
                   nota="doblete DEQ=0.08 << Gamma (no resuelto extremo)")]),
    "A3a": [Case("A3a_b0.5", [_sx(bhf=0.5)], nota="sexteto colapsado 0.5 T"),
            Case("A3a_b58", [_sx(bhf=58.0)], vmax=12.0,
                 nota="sexteto 58 T (junto a la cota 60)")],
    "A3b": [Case(f"A3b_e{e:+.2f}", [_sx(qua=e)], nota="sexteto QUA ext")
            for e in (-0.45, 0.45)],
    "A5": [Case("A5_eta0.1_th54.7_ph0",
                [_sx(qua=2.0, bhf=6.19, the=54.7, eta=0.1)],
                param_extra=["HAMILT=.TRUE.,"],
                fit_kwargs={"quad_treatment": "kundig_fixed",
                            "free_intensities": True},
                nota="HC eta=0.1 (mezcla debil)")],
    "B2": [Case(f"B2_r{r:g}", [_db(d21=r)], vmax=VA,
                fit_kwargs={"free_intensities": True},
                nota=f"doblete asimetrico extremo D21={r}")
           for r in (0.3, 3.0)],
    "C1": [Case("C1_g0.80", [_sx(wid=0.8)], nota="sexteto Gamma comun 0.8")],
    "C2": [Case("C2_invertida_b33",
                [_sx(wid=0.30, w13=0.7, w23=1.3)],
                fit_kwargs={"free_widths_common": False,
                            "free_intensities": True},
                nota="anchuras por pares invertidas W13=0.7 W23=1.3")],
    "D3": [Case("D3_f0.5pc",
                [_sx(dep=0.05), _db(iso=0.35, qua=0.7,
                                    dep=round(0.05 * 0.5 / 99.5, 6))],
                nota="doblete minoritario 0.5% del area")],
    "D6": [Case("D6_dq0.02",
                [_db(iso=0.35, qua=1.2, dep=0.03),
                 _db(iso=0.35, qua=1.22, dep=0.03)],
                vmax=VA, fit_kwargs={"multistart_n": 6},
                nota="dobletes casi degenerados dDEQ=0.02 (degeneracion)")],
}


def run_site_ext() -> None:
    for serie, cases in EXT.items():
        generate_series(serie, cases)
        rows = []
        for case in cases:
            rows += fit_case(serie, case, "v0")
            if make_v1(serie, case, seed_for(case.cid, "v1")) is not None:
                rows += fit_case(serie, case, "v1")
        append_rows(rows)
        bad = [r for r in rows if r.get("convergido") != "si"]
        print(f"[{serie}+ext] {len(cases)} casos, {len(rows)} filas, "
              f"no-conv={len(bad)}")
    # A5 ext también con el tratamiento hamiltoniano (v0m, como §13)
    import copy
    rows = []
    for case in EXT["A5"]:
        c2 = copy.deepcopy(case)
        c2.fit_kwargs = dict(c2.fit_kwargs, quad_treatment="hamiltonian",
                             free_intensities=False)
        rows += fit_case("A5", c2, "v0m", data_version="v0")
    append_rows(rows)
    dedupe_resumen()
    print(f"[A5+ext] v0m hamiltoniano: {len(rows)} filas")


# ── Extensión del bloque J (DIST) ────────────────────────────────────────────

def j_ext_cases() -> dict[str, dict]:
    import serie_J
    from serie_J import _bloque
    out = {}
    for avg, stg, nota in ((15.0, 3.0, "gaussiana en el borde bajo de la malla"),
                           (45.0, 3.0, "gaussiana en el borde alto de la malla"),
                           (30.0, 0.8, "casi-delta: sigma ~ paso de malla"),
                           (30.0, 8.0, "gaussiana muy ancha sigma=8")):
        out[f"J1_b{avg:g}_s{stg:g}"] = {
            "plines": ["NDSS=1,", "DISTRI=2,"] + _bloque(5.0, 46, avg, stg),
            "var": "bhf", "truth_avg": avg, "truth_std": stg, "nota": nota}
    for dti in (-0.01, 0.02):
        out[f"J4_dti{dti:g}"] = {
            "plines": ["NDSS=1,", "DISTRI=2,"]
            + _bloque(8.0, 41, 30.0, 3.0, dti=dti),
            "var": "bhf", "truth_avg": 30.0, "truth_std": 3.0, "slope": dti,
            "nota": f"correlacion delta(B) DTI={dti} mm/s/T"}
    return out


def run_j_ext() -> None:
    import serie_J
    new = {cid: spec for cid, spec in j_ext_cases().items()
           if cid not in serie_J.CASES}
    serie_J.CASES.update(new)
    serie_J.generate()          # solo genera lo que falte (v0.dat inexistente)
    rows = []
    for cid, spec in new.items():
        vj = serie_J.JDIR / cid / "verdad.json"
        if not vj.exists():
            rows.append({"serie": "J", "caso": cid, "version": "v0",
                         "parametro": "-", "convergido": "no",
                         "nota": "sin espectro generado"})
            continue
        info = json.loads(vj.read_text())
        mom = info.get("momentos_verdad") or {}
        t_avg, t_std = mom.get("avg"), mom.get("std")
        for version in ("v0", "v1"):
            res = serie_J.fit_case(cid, version)
            base = {"serie": "J", "caso": cid, "version": version,
                    "nota": spec["nota"]}
            if res is None:
                continue
            if "error" in res:
                rows.append(dict(base, parametro="-", convergido="no",
                                 nota=res["error"][:150]))
                continue
            for pname, tval, fval in (("dist_avg", t_avg, res["avg"]),
                                      ("dist_std", t_std, res["std"])):
                if tval is None:
                    continue
                rows.append(dict(base, parametro=pname,
                                 verdadero=f"{tval:.4f}",
                                 ajustado=f"{fval:.4f}",
                                 abs_delta=f"{abs(fval - tval):.4f}",
                                 convergido="si"))
        # DTI: ajuste adicional ignorando la correlación (sesgo esperado)
        if spec.get("slope"):
            res0 = serie_J.fit_case(cid, "v0", extra=["--delta-slope", "0"],
                                    tag="v0_sin_slope")
            if res0 and "error" not in res0 and t_std is not None:
                rows.append({"serie": "J", "caso": cid,
                             "version": "v0_sin_slope",
                             "parametro": "dist_std",
                             "verdadero": f"{t_std:.4f}",
                             "ajustado": f"{res0['std']:.4f}",
                             "abs_delta": f"{abs(res0['std'] - t_std):.4f}",
                             "convergido": "si",
                             "nota": "correlacion delta(B) ignorada"})
    append_rows(rows)
    dedupe_resumen()
    print(f"[J+ext] {len(rows)} filas")


if __name__ == "__main__":
    only = sys.argv[1:] or ["site", "j"]
    if "site" in only:
        run_site_ext()
    if "j" in only:
        run_j_ext()
