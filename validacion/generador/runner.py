#!/usr/bin/env python3
"""Orquestador del banco: SITE genera (v0) → ruido (v1) → Fitbauer ajusta → CSV.

Cada caso vive en ``validacion/<SERIE>/<case_id>/`` (nombre largo Linux); los
ficheros que toca DOSBox usan nombres 8.3 (``Cnnnn.*``) en un staging por serie
y se archivan después en el directorio del caso.

La verdad del caso es el JSON ``verdad.json`` (parámetros de SITE + metadatos).
Los resultados van a ``validacion/resumen.csv`` (una fila por caso, versión y
parámetro comparado).
"""
from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from normos_lib import (BHF_SCALE_SITE, DEFAULT_BASE, DEFAULT_NCHAN,
                        DEFAULT_VMAX, DEFAULT_WID,
                        DEFAULT_DEP, STAGING_ROOT, VALID_ROOT, dummy_counts,
                        fitbauer_fit, job_text, parse_plt, parse_res,
                        run_dosbox_batch, site_params, unfold_theory,
                        write_adt, ws5_text)

RESUMEN = VALID_ROOT / "resumen.csv"
CSV_COLS = ["serie", "caso", "version", "parametro", "verdadero", "ajustado",
            "sigma", "z", "abs_delta", "chi2red", "convergido", "t_ajuste_s",
            "nota"]


@dataclass
class Case:
    cid: str                       # identificador largo (nombre de directorio)
    comps: list[dict]              # componentes en claves SITE (iso/qua/bhf/...)
    vmax: float = DEFAULT_VMAX
    nchan: int = DEFAULT_NCHAN     # canales SIN doblar
    base: int = DEFAULT_BASE
    data_extra: dict = field(default_factory=dict)   # &DATA adicionales
    param_extra: list[str] = field(default_factory=list)  # &PARAM adicionales
    fit_kwargs: dict = field(default_factory=dict)   # opciones fitbauer_fit
    truth_override: dict = field(default_factory=dict)  # {param: valor} manual
    skip_params: tuple = ()        # parámetros a excluir de la comparación
    nota: str = ""


# ── Verdad esperada en parámetros Fitbauer ───────────────────────────────────

def expected_params(case: Case) -> dict[str, float]:
    """Verdad en claves Fitbauer a partir de los parámetros SITE del caso.

    Convenciones (paso 0/0.6): ISO→delta; WID(FWHM)→gamma1(FWHM); sextete
    QUA→quad (mismo signo, patrón ±QUA/2); doblete: |QUA|→|quad| (el signo es
    degenerado en dobletes simétricos, se compara en valor absoluto vía
    ``abs_params``); BHF→bhf·BHF_SCALE_SITE (escala de conversión T→mm/s de
    SITE, k=0.99962, medida en 0.6); DEP = área total del subespectro en mm/s
    → depth = DEP / (Σw · π · Γ_FWHM/2). ``baseline`` no se compara: la
    normalización P90 de Fitbauer introduce un offset benigno ~1e-4.

    Anchuras por línea (sonda paso0): WID de SITE = FWHM de las líneas
    interiores (3,4); W13/W23 = ratios de las líneas 1,6 / 2,5. Fitbauer usa
    gamma1 = líneas 1,6 y gamma2/gamma3 como ratios respecto a gamma1 →
    gamma1 = WID·W13, gamma2 = W23/W13, gamma3 = 1/W13. Las intensidades de
    SITE (D13/D23/D21) son ratios de ÁREA; las de Fitbauer (int1/int2) son
    pesos de ALTURA → int1 = D13/W13, int2 = D23/W23.
    """
    free_ints = bool(case.fit_kwargs.get("free_intensities"))
    out: dict[str, float] = {}
    for i, c in enumerate(case.comps, 1):
        nline = c.get("nline", 6)
        wid = float(c.get("wid", DEFAULT_WID))
        dep = float(c.get("dep", DEFAULT_DEP))
        out[f"s{i}_delta"] = float(c.get("iso", 0.0))
        if nline == 6:
            w13 = float(c.get("w13", 1.0))
            w23 = float(c.get("w23", 1.0))
            d13 = float(c.get("d13", 3.0))
            d23 = float(c.get("d23", 2.0))
            g1 = wid * w13
            g2r, g3r = w23 / w13, 1.0 / w13
            i1, i2 = d13 / w13, d23 / w23
            out[f"s{i}_quad"] = float(c.get("qua", 0.0))
            out[f"s{i}_bhf"] = float(c.get("bhf", 33.0)) * BHF_SCALE_SITE
            out[f"s{i}_gamma1"] = g1
            if w13 != 1.0 or w23 != 1.0:
                out[f"s{i}_gamma2"] = g2r
                out[f"s{i}_gamma3"] = g3r
            if free_ints:
                out[f"s{i}_int1"] = i1
                out[f"s{i}_int2"] = i2
            area_w = np.pi / 2.0 * g1 * 2.0 * (i1 + i2 * g2r + g3r)
        elif nline == 2:
            # D21 de SITE = área(línea alta velocidad)/área(línea baja). En la
            # rama quad=−QUA de Fitbauer la línea alta-v es la 1 → int2=1/D21;
            # el flip de rama en fit_case invierte a D21 si el ajuste eligió
            # quad=+QUA. El área total es invariante de rama.
            d21 = float(c.get("d21", 1.0))
            out[f"s{i}_quad"] = -float(c.get("qua", 0.0))
            out[f"s{i}_gamma1"] = wid
            if free_ints and d21 != 0:
                out[f"s{i}_int2"] = 1.0 / d21
            area_w = np.pi / 2.0 * 3.0 * wid * (1.0 + (1.0 / d21 if d21 else 1.0))
        else:
            out[f"s{i}_gamma1"] = wid
            area_w = np.pi / 2.0 * 3.0 * wid
        out[f"s{i}_depth"] = dep / area_w
    out.update(case.truth_override)
    return out


def abs_params(case: Case) -> set[str]:
    """Parámetros que se comparan en valor absoluto (signo degenerado)."""
    out = set()
    for i, c in enumerate(case.comps, 1):
        if c.get("nline", 6) == 2:
            out.add(f"s{i}_quad")
    return out


# ── Pipeline por serie ───────────────────────────────────────────────────────

def generate_series(serie: str, cases: list[Case], force: bool = False) -> None:
    """Genera con SITE todos los casos de la serie que falten (v0.dat)."""
    stg = STAGING_ROOT / serie
    pend = [c for c in cases
            if force or not (VALID_ROOT / serie / c.cid / "v0.dat").exists()]
    if not pend:
        print(f"[{serie}] generación: nada pendiente")
        return
    if stg.exists():
        shutil.rmtree(stg)
    stg.mkdir(parents=True)
    stems = []
    for k, case in enumerate(pend):
        stem = f"C{k:04d}"
        stems.append(stem)
        dummy = dummy_counts(case.nchan, case.base)
        (stg / f"{stem}.MOS").write_bytes(ws5_text(dummy).encode("ascii"))
        data = {"VMAX": f"{case.vmax}", "PFP": f"{case.nchan / 2 + 0.5}"}
        data.update(case.data_extra)
        plines = site_params(len(case.comps), case.comps,
                             extra=case.param_extra or None)
        jt = job_text(stem, data, plines, f"Serie {serie}", case.cid[:60])
        (stg / f"{stem}.JOB").write_bytes(jt.encode("ascii"))
    print(f"[{serie}] {run_dosbox_batch(stg, stems)}")
    for stem, case in zip(stems, pend):
        cdir = VALID_ROOT / serie / case.cid
        cdir.mkdir(parents=True, exist_ok=True)
        for ext in (".MOS", ".JOB", ".RES", ".PLT"):
            f = stg / f"{stem}{ext}"
            if f.exists():
                shutil.copy2(f, cdir / f"SITE{ext}")
        plt_f = cdir / "SITE.PLT"
        info = {"caso": case.cid, "serie": serie, "comps": case.comps,
                "vmax": case.vmax, "nchan": case.nchan, "base": case.base,
                "data_extra": case.data_extra, "param_extra": case.param_extra,
                "nota": case.nota, "site_version": "27.01.1994 demo"}
        if plt_f.exists():
            # NP explícito: con 4+NSUB bloques la inferencia es ambigua para
            # NSUB∈{3,5,7,9} (bloques totales divisibles por 512/1024).
            p = parse_plt(plt_f, np_ch=case.nchan // 2)
            r = parse_res(cdir / "SITE.RES")
            info["site_res"] = {k: r.get(k) for k in ("pfp", "chi2")}
            info["site_warnings"] = r.get("warnings", [])[:10]
            raw = unfold_theory(p["fit"], case.base)
            write_adt(cdir / "v0.dat", raw)
            np.save(cdir / "teoria_norm.npy", p["fit"])
        else:
            info["site_error"] = "SIN PLT: revisar SITE.RES"
        (cdir / "verdad.json").write_text(
            json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")


def make_v1(serie: str, case: Case, seed: int, base: int | None = None,
            tag: str = "v1") -> Path | None:
    """Versión con ruido Poisson desde la teoría archivada (sin re-correr SITE)."""
    cdir = VALID_ROOT / serie / case.cid
    th_f = cdir / "teoria_norm.npy"
    if not th_f.exists():
        return None
    theory = np.load(th_f)
    rng = np.random.default_rng(seed)
    raw = unfold_theory(theory, base or case.base, rng=rng)
    out = cdir / f"{tag}.dat"
    write_adt(out, raw)
    return out


def _match_components(case: Case, res: dict) -> dict:
    """Re-etiqueta los componentes ajustados para casarlos con la verdad.

    En ajustes multicomponente el índice del componente de Fitbauer no tiene
    por qué coincidir con el de SITE (label switching): se busca la asignación
    de coste mínimo por tipo (posición delta + BHF escalado + |quad|) y se
    renombran las claves s{i}_* del resultado. Solo afecta a la comparación.
    """
    n = len(case.comps)
    if n < 2 or not res.get("values"):
        return res
    from scipy.optimize import linear_sum_assignment
    vals = res["values"]
    kinds_t = [c.get("nline", 6) for c in case.comps]
    perm = {}
    for kind in set(kinds_t):
        idx_t = [i for i, k in enumerate(kinds_t, 1) if k == kind]
        if len(idx_t) == 1:
            perm[idx_t[0]] = idx_t[0]
            continue
        cost = np.zeros((len(idx_t), len(idx_t)))
        for a, it in enumerate(idx_t):
            c = case.comps[it - 1]
            for b, jf in enumerate(idx_t):
                d = abs(vals.get(f"s{jf}_delta", 0.0) - c.get("iso", 0.0))
                if kind == 6:
                    d += 0.2 * abs(vals.get(f"s{jf}_bhf", 0.0)
                                   - c.get("bhf", 33.0) * BHF_SCALE_SITE)
                    d += 0.5 * abs(vals.get(f"s{jf}_quad", 0.0) - c.get("qua", 0.0))
                elif kind == 2:
                    d += 0.5 * abs(abs(vals.get(f"s{jf}_quad", 0.0))
                                   - abs(c.get("qua", 0.0)))
                cost[a, b] = d
        ra, cb = linear_sum_assignment(cost)
        for a, b in zip(ra, cb):
            perm[idx_t[a]] = idx_t[b]
    if all(k == v for k, v in perm.items()):
        return res
    out = dict(res)
    # values[s{i}_*] de la verdad ← values[s{perm[i]}_*] del ajuste
    for key in ("values", "errors"):
        src = res.get(key, {})
        remapped = dict(src)
        for i, j in perm.items():
            if i == j:
                continue
            for tail in ("delta", "quad", "bhf", "gamma1", "gamma2", "gamma3",
                         "depth", "int1", "int2"):
                kj, ki = f"s{j}_{tail}", f"s{i}_{tail}"
                if kj in src:
                    remapped[ki] = src[kj]
                elif ki in remapped:
                    del remapped[ki]
        out[key] = remapped
    out["component_permutation"] = {str(i): int(j) for i, j in perm.items()}
    return out


def fit_case(serie: str, case: Case, version: str = "v0",
             seed: int | None = None,
             data_version: str | None = None) -> list[dict]:
    """Ajusta una versión del caso con Fitbauer y devuelve filas de resumen.

    ``data_version`` permite etiquetar el resultado como ``version`` pero
    ajustar los datos de otra versión (p. ej. re-ajustes "v0m" con mejoras de
    modelo sobre el espectro v0, sin sobrescribir el ajuste original).
    """
    cdir = VALID_ROOT / serie / case.cid
    dat = cdir / f"{data_version or version}.dat"
    rows: list[dict] = []
    if not dat.exists():
        return [{"serie": serie, "caso": case.cid, "version": version,
                 "parametro": "-", "convergido": "no",
                 "nota": "sin espectro generado"}]
    import zlib
    fseed = seed if seed is not None else zlib.crc32(case.cid.encode()) & 0xFFFFF
    res = fitbauer_fit(dat, case.comps, case.vmax, seed=fseed,
                       **case.fit_kwargs)
    # Escalado: si el ajuste local+multistart queda claramente lejos
    # (chi2red>5), reintento con pre-pasada global DE (global_opt), como haría
    # un usuario ante un ajuste visiblemente malo. Se registra el escalado.
    chi0 = res.get("stats", {}).get("red_chi2")
    if (not res.get("converged")) or (chi0 is not None and chi0 > 2.0):
        kw = dict(case.fit_kwargs)
        kw["multistart_n"] = min(kw.get("multistart_n", 4), 2)
        em = dict(kw.get("extra_model") or {})
        em["global_opt"] = True
        kw["extra_model"] = em
        res2 = fitbauer_fit(dat, case.comps, case.vmax, seed=fseed, **kw)
        chi2 = res2.get("stats", {}).get("red_chi2")
        if res2.get("converged") and (chi0 is None or (chi2 is not None and chi2 < chi0)):
            res2["escalado_DE"] = {"chi2red_intento1": chi0}
            res = res2
    # Nivel 2: arranque fino ±5% (usuario con valores iniciales decentes).
    chi1 = res.get("stats", {}).get("red_chi2")
    if (not res.get("converged")) or (chi1 is not None and chi1 > 2.0):
        kw = dict(case.fit_kwargs)
        kw["perturb"] = 0.05
        kw["multistart_n"] = 8
        res3 = fitbauer_fit(dat, case.comps, case.vmax, seed=fseed, **kw)
        chi3 = res3.get("stats", {}).get("red_chi2")
        if res3.get("converged") and (chi1 is None or (chi3 is not None and chi3 < chi1)):
            res3["escalado_fino"] = {"chi2red_previo": chi1,
                                     "chi2red_intento1": res.get("escalado_DE", {}).get("chi2red_intento1", chi0)}
            if "escalado_DE" in res:
                res3["escalado_DE"] = res["escalado_DE"]
            res = res3
    res = _match_components(case, res)
    (cdir / f"fitbauer_{version}.json").write_text(
        json.dumps(res, indent=1, default=str), encoding="utf-8")
    truth = expected_params(case)
    absset = abs_params(case)
    # Degeneración del doblete asimétrico: (quad, int2) ≡ (−quad, 1/int2).
    # Si el ajuste eligió la rama de signo opuesto, la verdad de int2 se
    # invierte para comparar dentro de la misma rama.
    for i, c in enumerate(case.comps, 1):
        if c.get("nline", 6) != 2:
            continue
        qf = res.get("values", {}).get(f"s{i}_quad")
        qt = truth.get(f"s{i}_quad")
        kint = f"s{i}_int2"
        kdep = f"s{i}_depth"
        if (qf is not None and qt and qf * qt < 0
                and truth.get(kint) not in (None, 0)):
            old = truth[kint]
            truth[kint] = 1.0 / old
            if truth.get(kdep):
                truth[kdep] *= (1.0 + old) / (1.0 + truth[kint])
    stats = res.get("stats", {})
    chi2red = stats.get("red_chi2")
    conv = res.get("converged", False)
    nota_extra = ""
    if res.get("escalado_DE"):
        c1 = res["escalado_DE"].get("chi2red_intento1")
        nota_extra += f" [escalado DE; intento1 chi2red={c1:.1f}]" if c1 else " [escalado DE]"
    if res.get("escalado_fino"):
        nota_extra += " [escalado arranque fino ±5%]"
    for pname, tval in truth.items():
        if pname in case.skip_params:
            continue
        fitted = res.get("values", {}).get(pname)
        err = res.get("errors", {}).get(pname)
        if fitted is None:
            continue
        if pname in absset:
            fitted, tval = abs(fitted), abs(tval)
        z = (fitted - tval) / err if err else None
        rows.append({
            "serie": serie, "caso": case.cid, "version": version,
            "parametro": pname, "verdadero": f"{tval:.6g}",
            "ajustado": f"{fitted:.6g}",
            "sigma": f"{err:.3g}" if err else "",
            "z": f"{z:.2f}" if z is not None else "",
            "abs_delta": f"{abs(fitted - tval):.3g}",
            "chi2red": f"{chi2red:.3f}" if chi2red else "",
            "convergido": "si" if conv else "no",
            "t_ajuste_s": f"{res.get('fit_seconds', 0):.1f}",
            "nota": (case.nota + nota_extra) if conv else res.get("error", "")[:120],
        })
    if not rows:
        rows.append({"serie": serie, "caso": case.cid, "version": version,
                     "parametro": "-", "convergido": "no",
                     "nota": res.get("error", "sin valores")[:160]})
    return rows


def append_rows(rows: list[dict]) -> None:
    new = not RESUMEN.exists()
    with RESUMEN.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CSV_COLS})


def dedupe_resumen() -> None:
    """Deja la última fila por (serie, caso, versión, parámetro)."""
    if not RESUMEN.exists():
        return
    with RESUMEN.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    last: dict = {}
    for r in rows:
        last[(r["serie"], r["caso"], r["version"], r["parametro"])] = r
    with RESUMEN.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS)
        w.writeheader()
        for r in last.values():
            w.writerow({k: r.get(k, "") for k in CSV_COLS})


def refit_series(serie: str, cases: list[Case], version: str = "v0") -> None:
    """Re-ajusta (sin regenerar) y deduplica el resumen."""
    rows = []
    for case in cases:
        rows += fit_case(serie, case, version)
    append_rows(rows)
    dedupe_resumen()
    bad = [r for r in rows if r.get("convergido") != "si"]
    print(f"[{serie}] re-ajuste {version}: {len(cases)} casos, "
          f"no-convergidos={len(bad)}")


def run_series_v0(serie: str, cases: list[Case], force: bool = False) -> None:
    generate_series(serie, cases, force=force)
    all_rows = []
    for case in cases:
        all_rows += fit_case(serie, case, "v0")
    append_rows(all_rows)
    bad = [r for r in all_rows if r.get("convergido") != "si"]
    zs = [abs(float(r["z"])) for r in all_rows if r.get("z")]
    print(f"[{serie}] v0: {len(cases)} casos, {len(all_rows)} filas, "
          f"no-convergidos={len(bad)}, max|z|={max(zs) if zs else 0:.1f}")
