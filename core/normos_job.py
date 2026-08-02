"""Interoperabilidad con los ficheros ``.JOB`` de NORMOS-SITE.

Permite abrir en Fitbauer un fichero de trabajo de NORMOS y exportar el modelo
de Fitbauer al mismo formato. **No ejecuta NORMOS ni lo distribuye**: solo lee
y escribe su formato de texto, que no es propietario.

Formato del ``.JOB``::

    C0003.MOS            ← cuatro nombres de fichero (datos, job, res, plt)
    C0003.JOB
    C0003.RES
    C0003.PLT
     &DATA
     NLTEXT=4, TRIANG=.TRUE., VMAX=10.0, PFP=256.5,
     &END
    título 1             ← NLTEXT líneas de texto libre
    título 2
     &PARAM
     NSUB=1,
     NLINE(1)=6, ISO(1)=0.0, ...
     &END

Las conversiones de convenio salen de la revisión del código fuente de NORMOS
(``validacion/informe/COBERTURA_NORMOS.md``) y son la parte delicada:

* ``WID`` es la anchura de las líneas **3,4**; ``gamma1`` la de las **1,6**.
  Por eso ``gamma1 = WID·W13``, ``gamma2 = W23/W13``, ``gamma3 = 1/W13``.
* ``D13``/``D23`` (o ``A13``/``A23`` en el fuente de 1990) son razones de
  **ÁREA**; ``int1``/``int2`` de **PROFUNDIDAD**: ``int1 = D13/W13``,
  ``int2 = D23/W23``.
* ``DEP``/``ARE`` es el **área** del subespectro en mm/s; ``depth`` es la
  profundidad de la línea de referencia.
* ``BHF`` va en la escala de NORMOS, que deriva las posiciones de los momentos
  nucleares. Para reproducirlo exactamente hay que ajustar con
  ``core.constants.sextet_pattern("normos")``; se avisa de ello.
* Los índices de las ligaduras ``NDEX`` son GLOBALES: 5 de fondo + 8 de isótopo
  y luego 15 por subespectro, así que el subespectro *n* empieza en
  ``13 + 15(n−1)``.
"""
from __future__ import annotations

import re

import numpy as np

from core.params import COMPONENT_PARAM_SPECS, component_defaults

#: Posición del bloque de cada subespectro dentro de la numeración global de
#: NORMOS (``MBKG=5`` + ``MISP=8``, luego ``MXLP=15`` por subespectro).
_BLOQUE_GLOBAL = 13
_ANCHO_BLOQUE = 15

#: Desplazamiento de cada parámetro dentro del bloque del subespectro
#: (``PARVAL`` en ``sitecalf.for``). Los nombres alternativos son los del
#: binario de 1994 (``DEP``/``D13``…) frente al fuente de 1990 (``ARE``/``A13``…).
_OFFSET_SITE = {
    "WID": 1, "ARE": 2, "DEP": 2, "ISO": 3, "QUA": 4, "BHF": 5,
    "ETA": 6, "THE": 7, "PHI": 8,
    "W13": 9, "W21": 9, "W23": 10, "W73": 11,
    "A13": 12, "D13": 12, "A21": 12, "D21": 12,
    "A23": 13, "D23": 13, "A73": 14, "D73": 14,
}

#: Globales de NORMOS por índice (1..13).
_GLOBAL_SITE = {
    1: "BKG(1)", 2: "BKG(2)", 3: "BKG(3)", 4: "BKG(4)", 5: "BKG(5)",
    6: "PHS", 7: "MIX", 8: "GFR", 9: "QMR", 10: "AKS", 11: "FSO",
    12: "TAB", 13: "WDS",
}

_TIPO_POR_NLINE = {1: "Singlete", 2: "Doblete", 6: "Sextete", 8: "Sextete"}

_NUM = r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[EeDd][-+]?\d+)?"


class NormosJobError(ValueError):
    """El fichero no es un ``.JOB`` de NORMOS legible."""


# ── Lectura ──────────────────────────────────────────────────────────────────

def parse_job(text: str) -> dict:
    """Descompone un ``.JOB`` en sus bloques, sin interpretar la física.

    Devuelve ``{"files": [...], "data": {...}, "param": {...},
    "titles": [...]}`` con los valores como cadenas tal cual aparecen.
    """
    if "&PARAM" not in text.upper():
        raise NormosJobError("no se encontró el bloque &PARAM")
    lineas = text.replace("\r\n", "\n").split("\n")

    bloques: dict[str, list[str]] = {"DATA": [], "PARAM": []}
    files: list[str] = []
    titles: list[str] = []
    actual: str | None = None
    visto_data = False
    for linea in lineas:
        desnuda = linea.strip()
        alto = desnuda.upper()
        if alto.startswith("&DATA"):
            actual, visto_data = "DATA", True
            continue
        if alto.startswith("&PARAM"):
            actual = "PARAM"
            continue
        if alto.startswith("&END"):
            actual = None
            continue
        if actual:
            bloques[actual].append(desnuda)
        elif not desnuda:
            continue
        elif not visto_data:
            files.append(desnuda)
        else:
            titles.append(desnuda)

    return {"files": files, "titles": titles,
            "data": _pares(bloques["DATA"]), "param": _pares(bloques["PARAM"])}


def _pares(lineas: list[str]) -> dict[str, str]:
    """``CLAVE=valor`` separados por comas, admitiendo ``CLAVE(i)=valor``."""
    texto = " ".join(lineas)
    out: dict[str, str] = {}
    for m in re.finditer(r"([A-Za-z][A-Za-z0-9_]*\s*(?:\(\s*\d+\s*\))?)\s*=\s*"
                         r"([^,]+?)(?=\s*,|\s*$)", texto):
        clave = re.sub(r"\s+", "", m.group(1)).upper()
        out[clave] = m.group(2).strip()
    return out


def _f(valor: str | None, defecto: float = 0.0) -> float:
    if valor is None:
        return defecto
    try:
        return float(valor.replace("D", "E").replace("d", "e"))
    except ValueError:
        return defecto


def _b(valor: str | None, defecto: bool = False) -> bool:
    if valor is None:
        return defecto
    return valor.strip().upper().startswith((".T", "T"))


def _idx(param: dict, nombre: str, i: int) -> str | None:
    """Valor de ``NOMBRE(i)`` admitiendo también la forma escalar."""
    return param.get(f"{nombre}({i})", param.get(nombre))


def job_to_model_state(text: str) -> dict:
    """Convierte un ``.JOB`` en un ``model_state`` de Fitbauer.

    Devuelve ``{"model_state": {...}, "vmax": float|None,
    "center": float|None, "warnings": [...]}``. Los avisos recogen todo lo que
    NO se ha podido trasladar, que es tan importante como lo que sí.
    """
    j = parse_job(text)
    data, param = j["data"], j["param"]
    avisos: list[str] = []

    nsub = int(_f(param.get("NSUB"), 1))
    if nsub < 1:
        raise NormosJobError("NSUB no válido")

    variables: dict[str, float] = {"baseline": 1.0, "slope": 0.0}
    fijos: dict[str, bool] = {}
    tipos: dict[int, str] = {}
    activos: dict[int, bool] = {}
    tratos: dict[int, str] = {}

    # ── Globales ────────────────────────────────────────────────────────────
    aks = _f(param.get("AKS"), 0.0)
    if aks:
        variables["line_asym"] = aks
        fijos["line_asym"] = not _b(param.get("AKSFIT"))
    iftran = _b(param.get("IFTRAN"))
    absorber = "transmission" if iftran else "thin"
    if iftran:
        wds = _f(param.get("WDS"), 0.097)
        variables["src_fwhm"] = wds if wds > 0 else 0.097
        fijos["src_fwhm"] = not _b(param.get("WDSFIT"))
        fso = _f(param.get("FSO"), 1.0)
        variables["src_frac"] = fso if fso > 0 else 1.0
        fijos["src_frac"] = not _b(param.get("FSOFIT"))
    for clave, destino in (("BKG(2)", "slope"), ("BKG(3)", "curv"),
                           ("BKG(4)", "curv3"), ("BKG(5)", "curv4")):
        if clave in param and _f(param[clave]):
            avisos.append(
                f"{clave} = {param[clave]}: el fondo polinómico de NORMOS está "
                f"normalizado a (v/Δv)^k; revisa «{destino}» tras importar.")

    # ── Subespectros ────────────────────────────────────────────────────────
    for i in range(1, nsub + 1):
        nline = int(_f(_idx(param, "NLINE", i), 6))
        kind = _TIPO_POR_NLINE.get(nline)
        if kind is None:
            avisos.append(f"subespectro {i}: NLINE={nline} no soportado; se omite.")
            continue
        if nline == 8:
            avisos.append(
                f"subespectro {i}: octete (NLINE=8) importado como sexteto; "
                "las líneas 7,8 (ΔmI=±2) hay que añadirlas como singletes.")
        tipos[i] = kind
        activos[i] = True
        pref = f"s{i}_"
        for nombre, valor in component_defaults(i).items():
            variables[pref + nombre] = valor

        wid = _f(_idx(param, "WID", i), 0.25) or 0.25
        w13 = _f(_idx(param, "W13", i), 1.0) or 1.0
        w23 = _f(_idx(param, "W23", i), 1.0) or 1.0
        w21 = _f(_idx(param, "W21", i), 1.0) or 1.0
        area = _f(_idx(param, "DEP", i) or _idx(param, "ARE", i), 0.05)

        variables[pref + "delta"] = _f(_idx(param, "ISO", i), 0.0)
        variables[pref + "quad"] = _f(_idx(param, "QUA", i), 0.0)

        if kind == "Sextete":
            d13 = _f(_idx(param, "D13", i) or _idx(param, "A13", i), 3.0)
            d23 = _f(_idx(param, "D23", i) or _idx(param, "A23", i), 2.0)
            # WID es de las líneas 3,4 y gamma1 de las 1,6.
            variables[pref + "gamma1"] = wid * w13
            variables[pref + "gamma2"] = w23 / w13 if w13 else 1.0
            variables[pref + "gamma3"] = 1.0 / w13 if w13 else 1.0
            # D13/D23 son razones de ÁREA; int1/int2 de PROFUNDIDAD.
            variables[pref + "int1"] = d13 / w13 if w13 else d13
            variables[pref + "int2"] = d23 / w23 if w23 else d23
            variables[pref + "bhf"] = _f(_idx(param, "BHF", i), 33.0)
            # Área con depth=1: (π/2)·Σ_j peso_j·Γ_j. NO factoriza como
            # Σpeso · Γ cuando las anchuras difieren, y en unidades de NORMOS
            # se reduce a 2·WID·(D13+D23+1).
            suma = 2.0 * wid * (d13 + d23 + 1.0)
        elif kind == "Doblete":
            d21 = _f(_idx(param, "D21", i) or _idx(param, "A21", i), 1.0)
            variables[pref + "gamma1"] = wid
            variables[pref + "gamma2"] = w21
            variables[pref + "int1"] = 1.0      # la línea 1 es la referencia
            variables[pref + "int2"] = d21 / w21 if w21 else d21
            suma = wid * (1.0 + d21)
        else:
            variables[pref + "gamma1"] = wid
            variables[pref + "int1"] = 1.0
            suma = wid

        # DEP/ARE es el ÁREA del subespectro en mm/s; depth es la profundidad
        # de la línea de referencia.
        denom = (np.pi / 2.0) * suma
        variables[pref + "depth"] = float(area / denom) if denom > 0 else 0.02

        if _b(_idx(param, "HAMILT", i)) or _b(param.get("HAMILT")):
            tratos[i] = "hamiltonian"
            variables[pref + "eta"] = _f(_idx(param, "ETA", i), 0.0)
            variables[pref + "beta"] = np.radians(_f(_idx(param, "THE", i), 0.0))
            variables[pref + "phi"] = np.radians(_f(_idx(param, "PHI", i), 0.0))

        for norm, mio in (("ISO", "delta"), ("QUA", "quad"), ("BHF", "bhf"),
                          ("WID", "gamma1"), ("DEP", "depth")):
            bandera = _idx(param, norm + "FIT", i)
            if bandera is not None:
                fijos[pref + mio] = not _b(bandera)
        if _idx(param, "AREFIT", i) is not None:
            fijos[pref + "depth"] = not _b(_idx(param, "AREFIT", i))

    # ── Ligaduras NDEX/FACTOR/CONST ─────────────────────────────────────────
    constraints: list[dict] = []
    for clave, valor in param.items():
        m = re.fullmatch(r"NDEX\((\d+)\)", clave)
        if not m:
            continue
        destino_i = int(m.group(1))
        fuente_i = int(_f(valor, 0))
        destino = _clave_desde_indice(destino_i, tipos)
        fuente = _clave_desde_indice(fuente_i, tipos)
        if not destino or not fuente:
            avisos.append(
                f"ligadura NDEX({destino_i})={fuente_i}: índice fuera del "
                "modelo importado; se omite.")
            continue
        constraints.append({
            "target": destino, "source": fuente,
            "factor": _f(param.get(f"FACTOR({destino_i})"), 1.0),
            "offset": _f(param.get(f"CONST({destino_i})"), 0.0),
        })

    for clave in ("POLAR", "IFSC", "IFGK", "EFGB", "SRELAX", "IRELAX",
                  "VOIGT", "EMSPEC", "ISTYPE", "NADD", "NDECKS"):
        if clave in param or clave in data:
            avisos.append(f"«{clave}» no se traslada: revisa el modelo a mano.")

    avisos.append(
        "BHF viene en la escala de NORMOS (posiciones derivadas de los momentos "
        "nucleares). Para reproducirla, ajusta con "
        "core.constants.sextet_pattern(\"normos\").")

    estado = {
        "vars": variables, "fixed": fijos,
        "sextet_enabled": {str(k): v for k, v in activos.items()},
        "component_kind": {str(k): v for k, v in tipos.items()},
        "intensity_mode": {str(k): "free" for k in tipos},
        "quad_treatment": {str(k): tratos.get(k, "1st_order") for k in tipos},
        "constraints": constraints,
        "n_components": len(tipos),
        "absorber_model": absorber,
        "drive_form": "triangular" if _b(data.get("TRIANG"), True) else "sine",
    }
    vmax = _f(data.get("VMAX"), 0.0) or None
    pfp = _f(data.get("PFP"), 0.0) or None
    if vmax:
        estado["vars"]["vmax"] = abs(vmax)
    if pfp:
        # NORMOS da el punto de doblado SUPERIOR (~2× el centro interno).
        estado["vars"]["center"] = pfp / 2.0 if pfp >= 400.0 else pfp
    return {"model_state": estado, "vmax": abs(vmax) if vmax else None,
            "center": estado["vars"].get("center"), "warnings": avisos}


def _clave_desde_indice(indice: int, tipos: dict[int, str]) -> str | None:
    """Índice global de NORMOS → clave de parámetro de Fitbauer."""
    if indice in _GLOBAL_SITE:
        return {"AKS": "line_asym", "FSO": "src_frac", "WDS": "src_fwhm",
                "BKG(2)": "slope"}.get(_GLOBAL_SITE[indice])
    if indice <= _BLOQUE_GLOBAL:
        return None
    n, resto = divmod(indice - _BLOQUE_GLOBAL - 1, _ANCHO_BLOQUE)
    sub = n + 1
    if sub not in tipos:
        return None
    kind = tipos[sub]
    por_offset = {1: "gamma1", 2: "depth", 3: "delta", 4: "quad", 5: "bhf",
                  9: "gamma2" if kind == "Doblete" else "gamma2",
                  10: "gamma3", 12: "int2" if kind == "Doblete" else "int1",
                  13: "int2"}
    nombre = por_offset.get(resto + 1)
    return f"s{sub}_{nombre}" if nombre else None


# ── Escritura ────────────────────────────────────────────────────────────────

def model_state_to_job(state: dict, stem: str = "FITBAUER",
                       vmax: float | None = None,
                       center: float | None = None,
                       titles: tuple[str, str] = ("Exportado de Fitbauer", ""),
                       data_extra: dict | None = None) -> str:
    """Exporta un ``model_state`` de Fitbauer al formato ``.JOB`` de NORMOS.

    Aplica las conversiones inversas a :func:`job_to_model_state`. Lo que
    NORMOS no sabe representar (tratamientos hamiltonianos, relajación, formas
    de distribución) se omite: el ``.JOB`` es un punto de partida para NORMOS,
    no una traducción exacta del modelo.
    """
    v = dict(state.get("vars", {}))
    fijos = dict(state.get("fixed", {}))
    tipos = {int(k): x for k, x in (state.get("component_kind", {}) or {}).items()}
    activos = {int(k): bool(x) for k, x in (state.get("sextet_enabled", {}) or {}).items()}
    indices = [i for i in sorted(tipos) if activos.get(i)]

    # NLTEXT NO son los títulos del .JOB: son las líneas de cabecera del
    # fichero de DATOS que NORMOS debe saltarse. 4 es lo que necesita un WS5
    # XML de Wissel; para otros formatos hay que ajustarlo con ``data_extra``.
    data = {"NLTEXT": "4", "TRIANG": ".TRUE.", "MXCFUN": "5000",
            "REMOTE": ".TRUE.", "PLTDAT": ".TRUE.", "PLTSUB": ".TRUE."}
    if data_extra:
        data.update({str(k).upper(): str(x) for k, x in data_extra.items()})
    if vmax is None:
        vmax = v.get("vmax")
    if vmax:
        data["VMAX"] = f"{abs(float(vmax)):g}"
    if center is None:
        center = v.get("center")
    if center:
        data["PFP"] = f"{float(center):g}"

    par: list[str] = [f"NSUB={len(indices)},"]
    for pos, i in enumerate(indices, start=1):
        kind = tipos[i]
        pref = f"s{i}_"
        nline = {"Singlete": 1, "Doblete": 2}.get(kind, 6)
        g1 = float(v.get(pref + "gamma1", 0.25)) or 0.25
        g2 = float(v.get(pref + "gamma2", 1.0)) or 1.0
        g3 = float(v.get(pref + "gamma3", 1.0)) or 1.0
        depth = float(v.get(pref + "depth", 0.02))
        par.append(f"NLINE({pos})={nline},")
        _añade(par, pos, "ISO", v.get(pref + "delta", 0.0), fijos.get(pref + "delta"))
        if kind != "Singlete":
            _añade(par, pos, "QUA", v.get(pref + "quad", 0.0), fijos.get(pref + "quad"))
        if kind == "Sextete":
            i1 = float(v.get(pref + "int1", 3.0))
            i2 = float(v.get(pref + "int2", 2.0))
            # gamma1 es de las líneas 1,6 y WID de las 3,4.
            wid = g1 * g3
            w13 = 1.0 / g3 if g3 else 1.0
            w23 = g2 / g3 if g3 else 1.0
            d13, d23 = i1 * w13, i2 * w23
            suma = 2.0 * wid * (d13 + d23 + 1.0)
            _añade(par, pos, "BHF", v.get(pref + "bhf", 33.0), fijos.get(pref + "bhf"))
            _añade(par, pos, "WID", wid, fijos.get(pref + "gamma1"))
            _añade(par, pos, "W13", w13, None)
            _añade(par, pos, "W23", w23, None)
            _añade(par, pos, "D13", d13, None)
            _añade(par, pos, "D23", d23, None)
        elif kind == "Doblete":
            wid, w21 = g1, g2
            d21 = float(v.get(pref + "int2", 1.0)) * w21
            suma = wid * (1.0 + d21)
            _añade(par, pos, "WID", wid, fijos.get(pref + "gamma1"))
            _añade(par, pos, "W21", w21, None)
            _añade(par, pos, "D21", d21, None)
        else:
            wid, suma = g1, g1
            _añade(par, pos, "WID", wid, fijos.get(pref + "gamma1"))
        # depth (profundidad) → DEP (área del subespectro en mm/s).
        _añade(par, pos, "DEP", (np.pi / 2.0) * suma * depth,
               fijos.get(pref + "depth"))

    if float(v.get("line_asym", 0.0)):
        par.append(f"AKS={float(v['line_asym']):g}, AKSFIT=.FALSE.,")
    if str(state.get("absorber_model", "thin")) == "transmission":
        par.append("IFTRAN=.TRUE.,")
        par.append(f"WDS={float(v.get('src_fwhm', 0.097)):g}, WDSFIT=.FALSE.,")
        frac = float(v.get("src_frac", 1.0))
        if frac != 1.0:
            par.append(f"FSO={frac:g}, FSOFIT=.FALSE.,")

    lineas = [f"{stem}.MOS", f"{stem}.JOB", f"{stem}.RES", f"{stem}.PLT", " &DATA"]
    lineas += _envuelve([f"{k}={x}" for k, x in data.items()])
    lineas += [" &END", titles[0][:70], titles[1][:70], " &PARAM"]
    for ln in par:
        lineas += _envuelve([p for p in ln.rstrip(",").split(", ") if p])
    lineas += [" &END", ""]
    return "\r\n".join(lineas)


def _añade(destino: list[str], i: int, nombre: str, valor, libre) -> None:
    flag = ".TRUE." if libre is False else ".FALSE."
    destino.append(f"{nombre}({i})={float(valor):g}, {nombre}FIT({i})={flag},")


def _envuelve(items: list[str], ancho: int = 70) -> list[str]:
    """Líneas de namelist de ≤72 columnas (límite del lector de NORMOS)."""
    salida, actual = [], " "
    for it in items:
        pieza = it + ","
        if len(actual) + len(pieza) + 1 > ancho:
            salida.append(actual)
            actual = " "
        actual += pieza + " "
    if actual.strip():
        salida.append(actual.rstrip())
    return salida
