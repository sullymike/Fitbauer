#!/usr/bin/env python3
"""Análisis masivo de trabajos .JOB reales de NORMOS (carpeta jobs/).

Para cada directorio de trabajo (JOB + RES + PLT + espectro):

1. Carga el .JOB con ``core.normos_job.job_to_model_state`` (avisos incluidos).
2. Lee del .RES los parámetros FINALES ajustados por NORMOS (tabla de
   variables por índice global), el punto de doblado y su χ².
3. Sustituye los finales en el JOB y reconvierte → modelo de Fitbauer EN la
   solución de NORMOS.
4. Carga el espectro con la sesión headless (mismo doblado que la GUI) y
   compara: centro detectado vs PFP del RES, curva del modelo de Fitbauer
   vs curva ajustada del PLT (paridad de convenios) y datos doblados vs
   bloque de datos del PLT (paridad de doblado/normalización).
5. Re-ajusta con Fitbauer desde la solución de NORMOS (pulido local) y
   compara parámetros y χ² (en la convención de NORMOS: σ²=modelo,
   DF=NP−1−NVAR, sobre cuentas).

Salidas en ``jobs/_analisis/`` (fuera del repositorio): resultados.csv y
casos problemáticos. El patrón de posiciones "normos" y el convenio de áreas
se activan durante toda la evaluación.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import traceback
from pathlib import Path

import numpy as np

GEN = Path(__file__).resolve().parent
ROOT = GEN.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(GEN))

from core.constants import sextet_pattern
from core.fit_engine import model_from_values
from core.normos_job import job_to_model_state, parse_job
from core.session import HeadlessSession, ModelState

JOBS = ROOT / "jobs"
OUT = JOBS / "_analisis"

_NUM = r"[-+]?[\d.]+(?:[EeDd][-+]?\d+)?"


# ── RES ──────────────────────────────────────────────────────────────────────

def parse_res_full(text: str) -> dict:
    out: dict = {"pfp": None, "chi2": None, "index": {}, "finales": {}}
    m = re.findall(r"Final folding point\s*=\s*(" + _NUM + ")", text)
    if m:
        out["pfp"] = float(m[-1])
    m2 = re.search(r"Chi-square \(normalized\)\s*=\s*(" + _NUM + ")", text)
    if m2:
        out["chi2"] = float(m2.group(1))
    # VMAX que NORMOS usó de verdad (el JOB del directorio puede haberse
    # editado después de generar el RES: caso Fc050723, 11.884 vs 11.810)
    m3 = re.search(r"Maximum velocity input\s+VMAX\s*=\s*(" + _NUM + ")", text)
    out["vmax"] = abs(float(m3.group(1))) if m3 else None
    # tabla de índices (eco inicial): índice global → (sub, NOMBRE, valor).
    # El eco lista TODOS los parámetros no nulos (ligados y defaults
    # incluidos): es más fiable que el propio JOB, que puede estar
    # malformado a mano (caso Ba100124).
    out["eco"] = {}
    sub = 0
    en_tabla = False
    for linea in text.splitlines():
        if "Index and starting values" in linea:
            en_tabla, sub = True, 0
            continue
        if en_tabla and "Number of fit variables" in linea:
            en_tabla = False
            continue
        if not en_tabla:
            continue
        ms = re.match(r"\s*Subspectrum #\s*(\d+)", linea)
        if ms:
            sub = int(ms.group(1))
            continue
        mm = re.match(r"\s*(\d+)\s+\d*\s+([A-Z][A-Z0-9()]*)\s+=\s+("
                      + _NUM + ")", linea)
        if mm:
            out["index"][int(mm.group(1))] = (sub, mm.group(2))
            out["eco"][int(mm.group(1))] = float(
                mm.group(3).replace("D", "E").replace("d", "e"))
    # finales: puede haber varias pasadas; la última gana
    for bloque in re.findall(
            r"Values of the fit-variables(.*?)\.{10,}", text, re.S):
        for mm in re.finditer(r"^\s*(\d+)\s+\S+\s+(" + _NUM + r")\s+(" + _NUM
                              + r")\s+\+-\s+(" + _NUM + ")", bloque, re.M):
            out["finales"][int(mm.group(1))] = (float(mm.group(3)),
                                                float(mm.group(4)))
    return out


def job_con_finales(job_text: str, res: dict) -> str:
    """JOB con los valores finales del RES sustituidos en &PARAM."""
    j = parse_job(job_text)
    param = dict(j["param"])
    canon = {"ARE": "DEP", "A13": "D13", "A23": "D23", "A21": "D21",
             "A73": "D73"}
    valores = {idx: v for idx, v in res.get("eco", {}).items()}
    valores.update({idx: fin for idx, (fin, _e) in res["finales"].items()})
    # Ligaduras NDEX(d)=s: el destino NO aparece en los finales (no es
    # variable libre); su valor real es factor·fuente + const con la fuente
    # FINAL. Sin esto, el destino se quedaría en el valor del eco inicial y
    # la conversión ÁREA→profundidad (que usa WID) saldría desescalada.
    ligaduras = {}
    for k, v in param.items():
        m = re.fullmatch(r"NDEX\((\d+)\)", k)
        if m:
            ligaduras[int(m.group(1))] = int(float(v))
    for _ in range(2):  # dos pasadas por si hay cadenas
        for dest, src in ligaduras.items():
            if src in valores:
                fac = float(param.get(f"FACTOR({dest})", 1.0) or 1.0)
                cte = float(param.get(f"CONST({dest})", 0.0) or 0.0)
                valores[dest] = fac * valores[src] + cte
    for idx, final in valores.items():
        info = res["index"].get(idx)
        if info is None:
            continue
        sub, nombre = info
        nombre = canon.get(nombre, nombre)
        clave = nombre if sub == 0 else f"{nombre}({sub})"
        # BKG(1) es la línea base en cuentas: no forma parte del modelo físico
        if clave.startswith("BKG(1"):
            continue
        param[clave] = f"{final:.7g}"
    lineas = [j["files"][k] if k < len(j["files"]) else f"X.{k}"
              for k in range(4)]
    lineas += [" &DATA"]
    lineas += [f" {k}={v}," for k, v in j["data"].items()]
    lineas += [" &END"] + j["titles"][:2] + [" &PARAM"]
    lineas += [f" {k}={v}," for k, v in param.items()]
    lineas += [" &END", ""]
    return "\n".join(lineas)


# ── PLT ──────────────────────────────────────────────────────────────────────

def parse_plt_auto(path: Path) -> dict | None:
    """Bloques del PLT localizando NP por monotonicidad del eje de velocidad."""
    nums: list[float] = []
    for linea in path.read_text(errors="replace").splitlines():
        try:
            valores = [float(t) for t in linea.split()]
        except ValueError:
            # línea de título: se descarta ENTERA (con extend(generador), un
            # título como «3 sext» colaría el 3 antes de fallar en «sext»)
            continue
        nums.extend(valores)
    n = len(nums)
    for np_ch in (256, 512, 128, 250, 255, 1024):
        if n % np_ch and n // np_ch < 3:
            continue
        nb = n // np_ch
        if nb < 3:
            continue
        v = np.array(nums[:np_ch])
        dv = np.diff(v)
        if np.all(dv > 0) or np.all(dv < 0):
            arr = np.array(nums[: nb * np_ch]).reshape(nb, np_ch)
            return {"v": arr[0], "data": arr[1], "fit": arr[2], "nb": nb}
    return None


# ── Un trabajo ───────────────────────────────────────────────────────────────

def localizar(d: Path) -> dict:
    """Ficheros del trabajo. Algunos directorios mezclan varias medidas
    (p. ej. CF120515 con el RES/PLT/espectro de CF120215): el RES manda, y
    JOB/PLT/espectro se emparejan por raíz de nombre con él; el espectro,
    mejor aún, por el nombre que cita el propio RES («Spectrum: …»)."""
    por_tipo: dict[str, list[Path]] = {}
    for f in sorted(d.iterdir()):
        s = f.suffix.lower()
        clave = {".job": "job", ".res": "res", ".plt": "plt",
                 ".ws5": "spec", ".adt": "spec", ".mos": "spec",
                 ".exp": "spec"}.get(s)
        if clave:
            por_tipo.setdefault(clave, []).append(f)
    files: dict = {}
    if "res" in por_tipo:
        files["res"] = por_tipo["res"][0]
        raiz = files["res"].stem.lower()
        spec_res = None
        m = re.search(r"Spectrum:\s*(\S+)",
                      files["res"].read_text(errors="replace"))
        if m:
            spec_res = m.group(1).lower()
        for clave in ("job", "plt", "spec"):
            cands = por_tipo.get(clave, [])
            if not cands:
                continue
            if clave == "spec" and spec_res:
                exacto = [c for c in cands if c.name.lower() == spec_res]
                if exacto:
                    files[clave] = exacto[0]
                    continue
            mismos = [c for c in cands if c.stem.lower() == raiz]
            files[clave] = mismos[0] if mismos else cands[0]
    else:
        for clave in ("job", "plt", "spec"):
            if clave in por_tipo:
                files[clave] = por_tipo[clave][0]
    return files


def analiza_uno(d: Path) -> dict:
    row: dict = {"trabajo": d.name}
    f = localizar(d)
    if "job" not in f:
        row["estado"] = "sin JOB"
        return row
    job_text = f["job"].read_text(errors="replace")
    j = parse_job(job_text)
    p = j["param"]
    if any(k.split("(")[0] in ("NDSS", "METHOD", "DISTRI") for k in p):
        row["estado"] = "DIST (cargador SITE)"
        return row
    row["nsub"] = int(float(p.get("NSUB", "1")))
    row["vmax_job"] = float(j["data"].get("VMAX", "0") or 0)
    if "spec" not in f:
        row["estado"] = "sin espectro"
        return row
    if "res" not in f:
        row["estado"] = "sin RES"
        return row
    res = parse_res_full(f["res"].read_text(errors="replace"))
    row["chi2_normos"] = res["chi2"]
    row["n_finales"] = len(res["finales"])

    conv = job_to_model_state(job_con_finales(job_text, res))
    row["avisos_carga"] = len(conv["warnings"])
    ms = ModelState.defaults(max(1, row["nsub"]))
    ms.apply_template(conv["model_state"])
    ms.n_components = row["nsub"]
    ms.multistart_n = 0
    ms.auto_global = False
    vmax = res.get("vmax") or conv.get("vmax") or row["vmax_job"] or 12.0
    ms.vars["vmax"] = float(vmax)

    sess = HeadlessSession(ms)
    sess.load_ws5(f["spec"], vmax=float(vmax))
    row["nchan"] = int(sess.spectrum.counts.size)
    row["centro_fitbauer"] = float(sess.spectrum.center)
    row["pfp_res"] = res["pfp"]
    if res["pfp"] is not None:
        # Algunos RES dan el punto de doblado en el convenio SUPERIOR
        # (~2× el centro interno): se compara en el convenio que encaje.
        c = row["centro_fitbauer"]
        row["d_centro"] = min(abs(c - res["pfp"]), abs(c - res["pfp"] / 2.0))

    st = sess.build_fit_state()
    with sextet_pattern("normos"):
        modelo = model_from_values(st.velocity, st.values, st.components,
                                   constraints=st.constraints,
                                   absorber_model=st.absorber_model)
    plt_d = parse_plt_auto(f["plt"]) if "plt" in f else None
    if plt_d is not None:
        v_p = np.asarray(plt_d["v"], float)
        orden = np.argsort(v_p)
        v_ps, fit_ps, dat_ps = v_p[orden], plt_d["fit"][orden], plt_d["data"][orden]
        v_f = np.asarray(st.velocity, float)
        # solo el rango común: fuera del eje de Fitbauer np.interp extrapola
        # plano y el canal extremo del PLT dispararía la métrica sin motivo
        dentro = (v_ps >= v_f.min()) & (v_ps <= v_f.max())
        v_ps, fit_ps, dat_ps = v_ps[dentro], fit_ps[dentro], dat_ps[dentro]
        of = np.argsort(v_f)
        m_i = np.interp(v_ps, v_f[of], modelo[of])
        y_i = np.interp(v_ps, v_f[of], np.asarray(st.y_data)[of])
        prof = max(1e-4, float(1.0 - np.min(dat_ps)))
        row["prof_pico"] = prof
        a = float(np.sum(fit_ps * m_i) / np.maximum(np.sum(m_i * m_i), 1e-12))
        row["dif_curva"] = float(np.max(np.abs(a * m_i - fit_ps))) / prof
        b = float(np.sum(dat_ps * y_i) / np.maximum(np.sum(y_i * y_i), 1e-12))
        resid = b * y_i - dat_ps
        row["dif_datos"] = float(np.max(np.abs(resid))) / prof
        # residuo de DATOS relativo al ruido fotónico por canal del propio
        # PLT: ~1 ⇒ los dos doblados coinciden salvo ruido decorrelado
        ruido = float(np.std(np.diff(dat_ps)) / np.sqrt(2.0))
        if ruido > 0:
            row["dif_datos_vs_ruido"] = float(np.std(resid)) / ruido

    # Re-ajuste desde la solución de NORMOS y χ² en convención NORMOS
    try:
        with sextet_pattern("normos"):
            resultado = sess.run_fit()
        row["chi2red_fitbauer"] = resultado["stats"].get("red_chi2")
        st2 = sess.build_fit_state()
        with sextet_pattern("normos"):
            modelo2 = model_from_values(st2.velocity, st2.values,
                                        st2.components,
                                        constraints=st2.constraints,
                                        absorber_model=st2.absorber_model)
        # χ² convención NORMOS: cuentas dobladas, σ²=modelo, DF=NP−1−NVAR
        cuentas = np.asarray(sess.spectrum.folded, float)
        norma = float(sess.spectrum.norm_factor)
        nvar = len(resultado.get("free_keys", []))
        for etiqueta, mod in (("chi2N_normosfit", modelo), ("chi2N_fitbauer",
                                                           modelo2)):
            yc = mod * norma
            # escala óptima (equivale al BKG1 libre que NORMOS siempre ajusta)
            a = float(np.sum(cuentas * yc) / np.maximum(np.sum(yc * yc), 1.0))
            yc = a * yc
            df = max(1, cuentas.size - 1 - nvar)
            row[etiqueta] = float(np.sum((cuentas - yc) ** 2 / np.maximum(yc, 1))
                                  / df)
        # desplazamiento de parámetros: Fitbauer óptimo vs NORMOS óptimo
        dmax: dict[str, float] = {}
        for k in resultado.get("free_keys", []):
            if not (len(k) > 2 and k[0] == "s" and k[1].isdigit()
                    and "_" in k):
                continue
            ini = st.values.get(k)
            fin = resultado["values"].get(k)
            if ini is None or fin is None:
                continue
            clase = k.split("_", 1)[1]
            dmax[clase] = max(dmax.get(clase, 0.0), abs(fin - ini))
        for clase, val in dmax.items():
            row[f"d_{clase}"] = val
        row["estado"] = "ok"
    except Exception as exc:
        row["estado"] = f"fallo ajuste: {type(exc).__name__}: {exc}"[:120]
    return row


def main() -> None:
    OUT.mkdir(exist_ok=True)
    filas = []
    dirs = sorted(d for d in JOBS.iterdir() if d.is_dir()
                  and not d.name.startswith("_"))
    for k, d in enumerate(dirs, 1):
        try:
            fila = analiza_uno(d)
        except Exception as exc:
            fila = {"trabajo": d.name,
                    "estado": f"EXCEPCION {type(exc).__name__}: {exc}"[:150]}
            (OUT / f"traza_{d.name}.txt").write_text(traceback.format_exc())
        filas.append(fila)
        if k % 25 == 0:
            print(f"  {k}/{len(dirs)}")
    columnas: list[str] = []
    for fila in filas:
        for c in fila:
            if c not in columnas:
                columnas.append(c)
    with (OUT / "resultados.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columnas)
        w.writeheader()
        w.writerows(filas)
    ok = [f for f in filas if f.get("estado") == "ok"]
    print(f"{len(filas)} trabajos; ok={len(ok)}")
    from collections import Counter
    print(Counter(f.get("estado", "?").split(":")[0] for f in filas))


if __name__ == "__main__":
    main()
