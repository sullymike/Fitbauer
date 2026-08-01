#!/usr/bin/env python3
"""Fase estadística: v1 (ruido Poisson) de todos los bloques + H + I.

- v1 global: ruido Poisson (semilla registrada = hash del caso) sobre la
  teoría archivada; ajuste y filas con z = (ajustado−verdadero)/σ.
  E3 se excluye (su v0.dat lleva post-proceso de base no plana que la teoría
  archivada no contiene).
- H1: 8 casos representativos con base ∈ {1e4, 1e5, 1e6, 3e6}.
- H2: absorción débil 0.5% con bases 1e5/1e6.
- H3: cobertura: 50 réplicas × 3 casos → ¿dispersión compatible con σ?
- I: adversarios (saturación fuerte vía IFTRAN, Γ enorme, protocolo de
  arranques, límite de detección, parámetros en frontera).
"""
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from runner import (Case, VALID_ROOT, append_rows, dedupe_resumen, fit_case,
                    generate_series, make_v1, run_series_v0)
from series_AB import SERIES as SAB, _sx, _db, _sg
from series_CG import SERIES as SCG


def seed_for(cid: str, tag: str) -> int:
    return zlib.crc32(f"{cid}|{tag}".encode()) & 0x7FFFFFFF


ALL_SERIES: dict[str, list[Case]] = {}
ALL_SERIES.update(SAB)
ALL_SERIES.update({k: v for k, v in SCG.items() if k != "E3"})


def fase_v1_global() -> None:
    rows = []
    n = 0
    for serie, cases in ALL_SERIES.items():
        for case in cases:
            if make_v1(serie, case, seed_for(case.cid, "v1")) is None:
                continue
            rows += fit_case(serie, case, "v1")
            n += 1
    append_rows(rows)
    print(f"[v1] {n} casos con ruido ajustados, {len(rows)} filas")


# H1: casos representativos × bases
_H1_SEL = [
    ("A2", "A2_d0.37_q0.70"), ("A3a", "A3a_b33"), ("A4", "A4_R1_th30"),
    ("B1", "B1_x2"), ("D2", "D2_db3"), ("D3", "D3_f5pc"),
    ("D4", "D4_suelo"), ("F1", "F1_t5"),
]


def fase_H1() -> None:
    rows = []
    for serie, cid in _H1_SEL:
        case = next(c for c in ALL_SERIES[serie] if c.cid == cid)
        for base in (10_000, 100_000, 1_000_000, 3_000_000):
            tag = f"v1_b{base:g}"
            if make_v1(serie, case, seed_for(cid, tag), base=base, tag=tag) is None:
                continue
            rows += fit_case(serie, case, tag)
    append_rows(rows)
    print(f"[H1] {len(rows)} filas")


# H2: absorción débil 0.5% (nueva generación SITE)
H2 = [
    Case("H2_dob_debil", [_db(dep=0.005 * np.pi * 0.25 / 2 * 6 / 3)], vmax=4.0,
         nota="doblete absorcion 0.5%"),
    Case("H2_sext_debil", [_sx(dep=0.005 * np.pi * 0.25 / 2 * 12 / 3)],
         nota="sexteto absorcion 0.5%"),
]


def fase_H2() -> None:
    generate_series("H2", H2)
    rows = []
    for case in H2:
        for base in (100_000, 1_000_000):
            tag = f"v1_b{base:g}"
            make_v1("H2", case, seed_for(case.cid, tag), base=base, tag=tag)
            rows += fit_case("H2", case, tag)
    append_rows(rows)
    print(f"[H2] {len(rows)} filas")


# H3: cobertura, 50 réplicas × 3 casos
_H3_SEL = [("A2", "A2_d0.37_q0.70"), ("A3a", "A3a_b33"),
           ("D4", "D4_sext+dob+sing")]


def fase_H3(n_rep: int = 50) -> None:
    rows = []
    for serie, cid in _H3_SEL:
        case = next(c for c in ALL_SERIES[serie] if c.cid == cid)
        for r in range(n_rep):
            tag = f"v1_r{r:02d}"
            make_v1(serie, case, seed_for(cid, tag), tag=tag)
            rows += fit_case(serie, case, tag, seed=seed_for(cid, tag + "fit"))
    append_rows(rows)
    print(f"[H3] {len(rows)} filas ({n_rep} réplicas × {len(_H3_SEL)})")


# I: adversarios
I_CASES = [
    # I1: saturación fuerte (integral de transmisión, ajustada con modelo fino
    # y con modelo de saturación de Fitbauer)
    Case("I1_sat30", [dict(_sg(iso=0.3), tab=30.0)],
         param_extra=["IFTRAN=.TRUE.,"], skip_params=("s1_depth",),
         fit_kwargs={"absorber_model": "thickness"},
         nota="transmision t_a=30 (absorcion ~40%)"),
    Case("I1_sat50_fina", [dict(_sg(iso=0.3), tab=50.0)],
         param_extra=["IFTRAN=.TRUE.,"], skip_params=("s1_depth",),
         nota="transmision t_a=50 ajustada con modelo fino"),
    # I2: Γ enorme
    Case("I2_sext_g1.5", [_sx(wid=1.5, dep=0.15)], nota="sexteto Gamma=1.5"),
    Case("I2_dob_g3", [_db(wid=3.0, dep=0.3)], vmax=10.0, nota="doblete Gamma=3.0"),
    # I4: límite de detección (se ajusta la v1 con base 1e5)
    Case("I4_limite", [_sg(iso=0.3, dep=0.002 * np.pi * 0.25 / 2)], vmax=4.0,
         nota="absorcion 0.2%, base 1e5"),
    # I5: parámetros en frontera
    Case("I5_delta_borde", [_sg(iso=2.9)], vmax=4.0,
         nota="delta=2.9 junto al limite superior de Fitbauer (3.0)"),
    Case("I5_lineas_borde", [_sx()], vmax=5.35,
         nota="lineas 1,6 de 33T (5.329) en los canales extremos"),
]


# X1: relajación de SITE (capacidad extra descubierta: SRELAX/IRELAX en &PARAM).
# Comparación cualitativa con el modelo Blume-Tjon de Fitbauer: no hay mapeo
# de parámetros conocido (OME sin unidades documentadas) → solo delta/bhf
# entran en la comparación numérica.
X1 = [
    Case(f"X1_ising_ome{o:g}",
         [dict(_sx(), raw=[f"OME(1)={o},", "BH0(1)=33.0,"])],
         param_extra=["IRELAX=.TRUE.,"],
         fit_kwargs={"kind_override": {1: "BlumeTjon"}},
         skip_params=("s1_depth", "s1_gamma1", "s1_quad"),
         nota=f"relajacion Ising OME={o} (cualitativo)")
    for o in (0.3, 1.0, 3.0, 10.0)
]


def fase_X1() -> None:
    run_series_v0("X1", X1)


def fase_I() -> None:
    run_series_v0("I", I_CASES)
    rows = []
    case = next(c for c in I_CASES if c.cid == "I4_limite")
    tag = "v1_b100000"
    make_v1("I", case, seed_for(case.cid, tag), base=100_000, tag=tag)
    rows += fit_case("I", case, tag)
    append_rows(rows)
    # I3: protocolo de valores iniciales sobre D4_suelo (sin multistart)
    suelo = next(c for c in SCG["D4"] if c.cid == "D4_suelo")
    rows = []
    for p in (0.05, 0.15, 0.30, 0.50, 0.80):
        import copy
        c2 = copy.deepcopy(suelo)
        c2.fit_kwargs = dict(c2.fit_kwargs, multistart_n=0, perturb=p)
        c2.nota = f"I3 arranque perturbado ±{int(p*100)}% sin multistart"
        rows += fit_case("D4", c2, f"v0_p{int(p*100):02d}",
                         seed=seed_for("I3", f"p{p}"))
    append_rows(rows)
    print(f"[I3] {len(rows)} filas de protocolo de arranque")
    dedupe_resumen()


if __name__ == "__main__":
    fases = sys.argv[1:] or ["v1", "H1", "H2", "H3", "I", "X1"]
    if "v1" in fases:
        fase_v1_global()
    if "X1" in fases:
        fase_X1()
    if "H1" in fases:
        fase_H1()
    if "H2" in fases:
        fase_H2()
    if "H3" in fases:
        fase_H3()
    if "I" in fases:
        fase_I()
    dedupe_resumen()
