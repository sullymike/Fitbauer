#!/usr/bin/env python3
"""Bloques K (SITE, capacidades del manual + extremos) — definición y flujo.

Series nuevas tras leer el manual (paso 2, sondas en validacion/paso2):

- K1 octetes: NLINE=8 con D73 (líneas ΔmI=±2 en ±1.40108·B/33, valor
  empírico del demo; su patrón sextete implicaría 1.4055 — convención SITE).
  Fitbauer no tiene octete de 1er orden → se modela sexteto + 2 singletes.
- K2 fondo no constante: BKG(k), fondo = 1 + Σ (BKG(k)/1000)·(v/(2·VMAX))^(k−1)
  (convenio medido en paso 2b). Fitbauer: slope (lineal, libre por defecto)
  y curv (parabólico, opt-in). El término cúbico no existe en Fitbauer.
- K3 cristal único: HAMILT + IFSC=.TRUE. (BEX/GAX = orientación del rayo γ en
  el sistema del EFG) y Goldanskii-Karyagin (IFGK + G21/G22). El tratamiento
  hamiltoniano de Fitbauer promedia el haz isotrópicamente (polvo): se espera
  desviación en intensidades, no en posiciones → se comparan δ/ΔEQ/BHF/Γ.
- K4 ligaduras nativas: SITE ajusta con NDEX/FACTOR/CONST (numeración por
  índice global del RES) y Fitbauer con constraints equivalentes; ambos
  contra la verdad.
- K5 extremos y centro en rejillas del banco v1 que quedaron ralas: δ fuera
  de rango con wide_delta, ΔEQ=5, QUA=±0.6, BHF∈{1,60}, D13≠3, W13/W23
  extremos, Γ subnatural, profundidad 40 %.

VOIGT/WDLOR resultó INOPERANTE en el demo (paso 2b: Γ=WID Lorentziana pura en
todos los casos) → el perfil Voigt no es validable round-trip con SITE.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from runner import Case
from series_AB import _sx, _db, _sg
from normos_lib import BHF_SCALE_SITE

# Posición empírica de las líneas 7,8 del demo a 33 T (ajuste 8L, paso 2)
P78_33T = 1.40108


def octet_pair(cid: str, d73: float, bhf: float = 33.0, dep: float = 0.06,
               wid: float = 0.25, d13: float = 3.0, d23: float = 2.0):
    """(caso_generación_SITE, caso_ajuste_Fitbauer) para un octete."""
    gen = Case(cid, [dict(_sx(bhf=bhf, wid=wid, dep=dep, d13=d13, d23=d23),
                          nline=8, d73=d73)],
               vmax=10.0, nota=f"octete D73={d73} B={bhf}")
    tot = d13 + d23 + 1.0 + d73
    p78 = P78_33T * bhf / 33.0
    dep_sx = dep * (d13 + d23 + 1.0) / tot
    dep_sg = dep * d73 / (2.0 * tot)
    fit = Case(cid,
               [_sx(bhf=bhf, wid=wid, dep=dep_sx, d13=d13, d23=d23),
                _sg(iso=-p78, wid=wid, dep=dep_sg),
                _sg(iso=+p78, wid=wid, dep=dep_sg)],
               vmax=10.0, fit_kwargs={"multistart_n": 6},
               nota=f"octete D73={d73}: sexteto + 2 singletes ΔmI=±2")
    return gen, fit


K1_PAIRS = [octet_pair("K1_d73_009", 0.087),
            octet_pair("K1_d73_025", 0.25),
            octet_pair("K1_d73_050", 0.50),
            octet_pair("K1_d73_025_b46", 0.25, bhf=46.0)]


# ── K2: fondo no constante ───────────────────────────────────────────────────

def _bkg_case(cid, coefs: dict[int, float], vmax=4.0, comps=None,
              free_curv=False, nota=""):
    """coefs: {k: BKG(k)} con k≥2. Verdad: slope=BKG2/(1000·2vmax),
    curv=BKG3/(1000·(2vmax)²)."""
    extra = [f"BKG({k})={val}, BKGFIT({k})=.FALSE.," for k, val in coefs.items()]
    truth = {}
    if 2 in coefs:
        truth["slope"] = coefs[2] / 1000.0 / (2 * vmax)
    if 3 in coefs:
        truth["curv"] = coefs[3] / 1000.0 / (2 * vmax) ** 2
    fk = {}
    if free_curv:
        fk["extra_model"] = {"free_curv": True}
    return Case(cid, comps or [_sg(iso=0.3)], vmax=vmax, param_extra=extra,
                truth_override=truth, fit_kwargs=fk, nota=nota)


K2 = [
    _bkg_case("K2_lin_p15", {2: 15.0}, nota="fondo lineal +15 (leve)"),
    _bkg_case("K2_lin_m30", {2: -30.0}, nota="fondo lineal -30 (centro)"),
    _bkg_case("K2_lin_p60", {2: 60.0},
              nota="fondo lineal +60: slope verdadero 7.5e-3 > cota 5e-3"),
    _bkg_case("K2_par_p15", {3: 15.0}, free_curv=True,
              nota="fondo parabolico +15 (leve)"),
    _bkg_case("K2_par_m30", {3: -30.0}, free_curv=True,
              nota="fondo parabolico -30 (centro)"),
    _bkg_case("K2_par_p60", {3: 60.0}, free_curv=True,
              nota="fondo parabolico +60 (fuerte)"),
    _bkg_case("K2_combo", {2: 25.0, 3: 40.0}, free_curv=True,
              nota="fondo lineal+parabolico combinado"),
    _bkg_case("K2_cubico", {4: 60.0}, free_curv=True,
              nota="fondo cubico: Fitbauer no tiene termino v3 (limite)"),
    _bkg_case("K2_sext_parab", {3: 50.0}, vmax=10.0, comps=[_sx()],
              free_curv=True, nota="sexteto 33T con fondo parabolico +50"),
]


# ── K3: cristal único y Goldanskii-Karyagin (HAMILT) ─────────────────────────

def _hc(cid, raw_comp=None, extra=None, nota=""):
    comp = _sx(qua=2.0, bhf=20.0, the=30.0, eta=0.5, dep=0.05)
    if raw_comp:
        comp = dict(comp, raw=raw_comp)
    return Case(cid, [comp],
                param_extra=["HAMILT=.TRUE.,"] + (extra or []),
                fit_kwargs={"quad_treatment": "hamiltonian",
                            "free_intensities": True},
                skip_params=("s1_int1", "s1_int2", "s1_depth"),
                nota=nota)


K3 = [
    _hc("K3_powder", nota="referencia polvo (IFSC=F)"),
    _hc("K3_sc_b0_g0", ["BEX(1)=0.0, GAX(1)=0.0,"], ["IFSC=.TRUE.,"],
        "cristal unico gamma||z_EFG"),
    _hc("K3_sc_b547_g0", ["BEX(1)=54.7, GAX(1)=0.0,"], ["IFSC=.TRUE.,"],
        "cristal unico angulo magico"),
    _hc("K3_sc_b90_g0", ["BEX(1)=90.0, GAX(1)=0.0,"], ["IFSC=.TRUE.,"],
        "cristal unico gamma perp z, phi=0"),
    _hc("K3_sc_b90_g90", ["BEX(1)=90.0, GAX(1)=90.0,"], ["IFSC=.TRUE.,"],
        "cristal unico gamma perp z, phi=90 (extremo eta)"),
    _hc("K3_gk_g21", ["G21(1)=0.5,"], ["IFGK=.TRUE.,"],
        "Goldanskii-Karyagin G21=0.5"),
    _hc("K3_gk_g22", ["G22(1)=-0.4,"], ["IFGK=.TRUE.,"],
        "Goldanskii-Karyagin G22=-0.4"),
]


# ── K5: extremos y centro en rejillas ralas del banco v1 ─────────────────────

K5 = [
    Case("K5_dob_dm25", [_db(iso=-2.5, qua=1.2)], vmax=6.0,
         fit_kwargs={"extra_model": {"wide_delta": True}},
         nota="doblete delta=-2.5 fuera del rango clasico (wide_delta)"),
    Case("K5_dob_dp34", [_db(iso=3.4, qua=1.2)], vmax=6.0,
         fit_kwargs={"extra_model": {"wide_delta": True}},
         nota="doblete delta=+3.4 fuera del rango clasico (wide_delta)"),
    Case("K5_dob_q5", [_db(iso=0.35, qua=5.0)], vmax=10.0,
         nota="doblete DeltaEQ=5.0 (extremo)"),
    Case("K5_sx_quap06", [_sx(qua=0.6)], nota="sexteto QUA=+0.6 (extremo 1er orden)"),
    Case("K5_sx_quam06", [_sx(qua=-0.6)], nota="sexteto QUA=-0.6 (extremo 1er orden)"),
    Case("K5_sx_b60", [_sx(bhf=60.0)], vmax=12.0, nota="sexteto BHF=60 T"),
    Case("K5_sx_b1", [_sx(bhf=1.0)], vmax=4.0,
         fit_kwargs={"multistart_n": 8}, nota="sexteto BHF=1 T (colapso extremo)"),
    Case("K5_sg_deep40", [_sg(iso=0.3, dep=0.40 * np.pi * 0.25 / 2)], vmax=4.0,
         nota="singlete profundidad 40%"),
    Case("K5_sx_d13_15", [_sx(d13=1.5)], fit_kwargs={"free_intensities": True},
         nota="sexteto D13=1.5 (int1 no estandar, extremo bajo)"),
    Case("K5_sx_d13_45", [_sx(d13=4.5)], fit_kwargs={"free_intensities": True},
         nota="sexteto D13=4.5 (int1 no estandar, extremo alto)"),
    Case("K5_sx_w13ext", [_sx(wid=0.22, w13=2.5, w23=0.6)],
         fit_kwargs={"free_widths_common": False, "free_intensities": True},
         nota="anchuras por pares extremas W13=2.5 W23=0.6"),
    Case("K5_sx_gnat", [_sx(wid=0.16)],
         nota="Gamma=0.16 subnatural (WIDNAT=0.194)"),
]


# ── K4: ligaduras nativas de SITE (modo ajuste real) ─────────────────────────

K4_SPECS = [
    {"cid": "K4_lig_delta",
     "comps": [_sx(iso=0.10, dep=0.05), _sx(iso=0.22, bhf=45.0, dep=0.03)],
     "lig_site": ("ISO", 2, "ISO", 1, 1.0, 0.12),
     "constraint": {"target": "s2_delta", "source": "s1_delta",
                    "factor": 1.0, "offset": 0.12},
     "nota": "ligadura nativa delta2=delta1+0.12"},
    {"cid": "K4_lig_areas",
     "comps": [_sx(iso=0.10, dep=0.06), _sx(iso=0.50, bhf=46.0, dep=0.03)],
     "lig_site": ("ARE", 2, "ARE", 1, 0.5, 0.0),
     "constraint": {"target": "s2_depth", "source": "s1_depth", "factor": 0.5},
     "nota": "ligadura nativa areas 2:1"},
]


def parse_index_table(res_text: str) -> dict[tuple[int, str], int]:
    """Tabla 'Index ... Name' del RES → {(subespectro, NOMBRE): índice global}."""
    import re
    out: dict[tuple[int, str], int] = {}
    sub = 0
    in_table = False
    for line in res_text.splitlines():
        if "Index and starting values" in line:
            in_table = True
            continue
        if in_table and "Number of fit variables" in line:
            break
        if not in_table:
            continue
        m = re.match(r"\s*Subspectrum #\s*(\d+)", line)
        if m:
            sub = int(m.group(1))
            continue
        m = re.match(r"\s*(\d+)\s+\d*\s+([A-Z]\w{2})\w*(?:\(\d+\))?\s+=", line)
        if m:
            out[(sub, m.group(2))] = int(m.group(1))
    return out


def run_K4() -> None:
    """Genera, ajusta con SITE (NDEX) y con Fitbauer (constraints)."""
    import json
    import shutil
    import zlib
    from normos_lib import (STAGING_ROOT, VALID_ROOT, dummy_counts, job_text,
                            parse_plt, parse_res, run_dosbox_batch,
                            site_params, unfold_theory, ws5_text)
    from runner import (append_rows, dedupe_resumen, expected_params,
                        fit_case, generate_series, make_v1)

    cases = [Case(s["cid"], s["comps"],
                  fit_kwargs={"constraints": [s["constraint"]]},
                  nota=s["nota"]) for s in K4_SPECS]
    generate_series("K4", cases)
    rows = []
    for case in cases:
        make_v1("K4", case, zlib.crc32(case.cid.encode()) & 0x7FFFFFFF)
        rows += fit_case("K4", case, "v1")
    append_rows(rows)
    print(f"[K4] Fitbauer con constraints: {len(rows)} filas")

    # SITE ajusta su propio espectro con la ligadura nativa
    stg = STAGING_ROOT / "K4fit"
    if stg.exists():
        shutil.rmtree(stg)
    stg.mkdir(parents=True)
    rows = []
    for k, (spec, case) in enumerate(zip(K4_SPECS, cases)):
        cdir = VALID_ROOT / "K4" / case.cid
        raw = np.loadtxt(cdir / "v1.dat")
        stem_a, stem_b = f"F{k}A", f"F{k}B"
        for stem in (stem_a, stem_b):
            (stg / f"{stem}.MOS").write_bytes(ws5_text(raw).encode("ascii"))
        # arranque: verdad perturbada; libres ISO/WID/ARE/BHF (QUA fija=0)
        rng = np.random.default_rng(1000 + k)
        fcomps = []
        for c in case.comps:
            c2 = {kk: vv for kk, vv in c.items()}
            c2["iso"] = round(c["iso"] + rng.uniform(-0.05, 0.05), 3)
            c2["bhf"] = round(c.get("bhf", 33.0) * rng.uniform(0.98, 1.02), 2)
            fcomps.append(c2)
        # libres ISO/WID/ARE/BHF; QUA/D13/D23 fijos en su valor verdadero
        plines = site_params(len(fcomps), fcomps, fit=True)
        plines = [ln.replace("QUAFIT(1)=.TRUE.", "QUAFIT(1)=.FALSE.")
                  .replace("QUAFIT(2)=.TRUE.", "QUAFIT(2)=.FALSE.")
                  .replace("D13FIT(1)=.TRUE.", "D13FIT(1)=.FALSE.")
                  .replace("D13FIT(2)=.TRUE.", "D13FIT(2)=.FALSE.")
                  .replace("D23FIT(1)=.TRUE.", "D23FIT(1)=.FALSE.")
                  .replace("D23FIT(2)=.TRUE.", "D23FIT(2)=.FALSE.")
                  for ln in plines]
        jt = job_text(stem_a, {"VMAX": f"{case.vmax}", "PFP": "256.5"},
                      plines, "K4 paso A", "descubrir indices")
        (stg / f"{stem_a}.JOB").write_bytes(jt.encode("ascii"))
    print(f"[K4/A] {run_dosbox_batch(stg, [f'F{k}A' for k in range(len(K4_SPECS))])}")

    stems_b = []
    for k, (spec, case) in enumerate(zip(K4_SPECS, cases)):
        res_a = (stg / f"F{k}A.RES").read_text(errors="replace")
        idx = parse_index_table(res_a)
        name_t, sub_t, name_s, sub_s, fac, con = spec["lig_site"]
        it, isrc = idx[(sub_t, name_t)], idx[(sub_s, name_s)]
        jt_a = (stg / f"F{k}A.JOB").read_bytes().decode("ascii")
        lig = f" NDEX({it})={isrc}, FACTOR({it})={fac}, CONST({it})={con},"
        jt_b = jt_a.replace(f"F{k}A", f"F{k}B")
        head, tail = jt_b.rsplit(" &END", 1)   # el último &END cierra &PARAM
        jt_b = head + lig + "\r\n &END" + tail
        (stg / f"F{k}B.JOB").write_bytes(jt_b.encode("ascii"))
        stems_b.append(f"F{k}B")
    print(f"[K4/B] {run_dosbox_batch(stg, stems_b)}")

    for k, (spec, case) in enumerate(zip(K4_SPECS, cases)):
        cdir = VALID_ROOT / "K4" / case.cid
        for ext in (".JOB", ".RES", ".PLT"):
            f = stg / f"F{k}B{ext}"
            if f.exists():
                shutil.copy2(f, cdir / f"SITEFIT{ext}")
        # tabla final indexada por nombre+índice global
        import re
        finals: dict[int, float] = {}
        txt = (cdir / "SITEFIT.RES").read_text(errors="replace")
        m = re.search(r"Values of the fit-variables(.*?)\.{10,}", txt, re.S)
        if m:
            for mm in re.finditer(r"^\s*(\d+)\s+\S+\s+([-.\dEe+]+)\s+"
                                  r"([-.\dEe+]+)\s+\+-", m.group(1), re.M):
                finals[int(mm.group(1))] = float(mm.group(3))
        idx = parse_index_table(txt)
        truth = expected_params(case)
        for i, c in enumerate(case.comps, 1):
            wid = c.get("wid", 0.25)
            area_w = np.pi / 2 * wid * 2 * (c.get("d13", 3.0)
                                            + c.get("d23", 2.0) + 1.0)
            for name, key, conv in (
                    ("ISO", f"s{i}_delta", lambda x: x),
                    ("WID", f"s{i}_gamma1", lambda x: x),
                    ("BHF", f"s{i}_bhf", lambda x: x * BHF_SCALE_SITE),
                    ("ARE", f"s{i}_depth", lambda x, aw=area_w: x / aw)):
                gi = idx.get((i, name))
                val = finals.get(gi) if gi else None
                # el parámetro ligado no aparece en la tabla final: derive
                if val is None and name == spec["lig_site"][0] \
                        and i == spec["lig_site"][1]:
                    src_gi = idx.get((spec["lig_site"][3], spec["lig_site"][2]))
                    if src_gi in finals:
                        val = finals[src_gi] * spec["lig_site"][4] \
                            + spec["lig_site"][5]
                if val is None or key not in truth:
                    continue
                fv = conv(val)
                rows.append({"serie": "K4", "caso": case.cid,
                             "version": "v1_site", "parametro": key,
                             "verdadero": f"{truth[key]:.6g}",
                             "ajustado": f"{fv:.6g}",
                             "abs_delta": f"{abs(fv - truth[key]):.3g}",
                             "convergido": "si",
                             "nota": spec["nota"] + " (ajuste del propio SITE)"})
    append_rows(rows)
    dedupe_resumen()
    print(f"[K4] SITE nativo: {len(rows)} filas")


# ── Flujo principal ──────────────────────────────────────────────────────────

def run_K1() -> None:
    from runner import (append_rows, dedupe_resumen, fit_case,
                        generate_series)
    gen_cases = [g for g, _ in K1_PAIRS]
    generate_series("K1", gen_cases)
    rows = []
    for _, fit in K1_PAIRS:
        rows += fit_case("K1", fit, "v0")
    append_rows(rows)
    dedupe_resumen()
    print(f"[K1] {len(rows)} filas")


if __name__ == "__main__":
    from runner import run_series_v0
    only = sys.argv[1:] or ["K1", "K2", "K3", "K4", "K5"]
    if "K1" in only:
        run_K1()
    if "K2" in only:
        run_series_v0("K2", K2)
    if "K3" in only:
        run_series_v0("K3", K3)
    if "K4" in only:
        run_K4()
    if "K5" in only:
        run_series_v0("K5", K5)
