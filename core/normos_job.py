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
from pathlib import Path

import numpy as np

from mossbauer_i18n import tr

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
    """El fichero no es un ``.JOB`` de NORMOS-SITE legible."""


#: Claves que solo existen en los ``.JOB`` de NORMOS-**DIST** (distribuciones).
#: Un fichero de DIST tiene la misma pinta que uno de SITE, pero su ``NSUB`` son
#: los puntos de la MALLA de la distribución y no sitios discretos: importarlo
#: como SITE crea decenas de sextetos sin sentido.
_CLAVES_DIST = frozenset({
    "DISTRI", "METHOD", "NSB", "LAMDA", "BETA1", "BETA2", "EXACT",
    "DTB", "DTI", "DTQ", "AREREL", "DEPREL", "H1P", "H2P", "ISP", "QUP",
    "AVG", "STG", "CONC", "PNEG", "NXLS", "NXLL", "S2T", "STI",
})


def es_job_de_dist(param: dict) -> bool:
    """¿El bloque ``&PARAM`` es de NORMOS-DIST en vez de NORMOS-SITE?"""
    raiz = {re.sub(r"\(.*", "", k) for k in param}
    return bool(raiz & _CLAVES_DIST)


#: ``METHOD`` de DIST → variable distribuida en Fitbauer. Ver la cabecera de
#: ``distinif.for``: 1-5 son distribuciones de campo, 6-7 de cuadrupolo y 8 de
#: desplazamiento isomérico.
_VARIABLE_POR_METHOD = {
    1: "bhf", 2: "bhf", 3: "bhf", 4: "bhf", 5: "bhf",
    6: "quad", 7: "quad", 8: "delta",
}

#: ``DISTRI`` de DIST → forma de la distribución en Fitbauer. ``DISTRI=3`` es
#: binomial si ``CONC>0`` y fija si ``CONC=0``; se resuelve en el traductor.
_FORMA_POR_DISTRI = {1: "Histograma", 2: "Gaussiana", 3: "Binomial", 4: None}

#: Índice del modo en el ``mode_combo`` de la GUI para cada variable.
_MODO_GUI = {"bhf": 1, "quad": 2, "delta": 3}

#: Etiqueta de la variable tal y como la guarda la sesión (``dist_variable``).
_ETIQUETA_VARIABLE = {"bhf": "BHF", "quad": "ΔEQ", "delta": "IS"}


# ── Lectura ──────────────────────────────────────────────────────────────────

def parse_job(text: str) -> dict:
    """Descompone un ``.JOB`` en sus bloques, sin interpretar la física.

    Devuelve ``{"files": [...], "data": {...}, "param": {...},
    "titles": [...]}`` con los valores como cadenas tal cual aparecen.
    """
    if "&PARAM" not in text.upper():
        raise NormosJobError(tr("normos.e_no_param"))
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


#: Extensiones que un ``.JOB`` nombra pero que NO son el espectro: son las
#: SALIDAS que NORMOS escribe (resultados, gráfico) y el propio trabajo.
_EXT_DE_SALIDA = frozenset({".job", ".res", ".plt", ".lst", ".dmp"})

#: Extensiones de espectro que se buscan cuando el nombre declarado no aparece.
_EXT_DE_DATOS = (".ws5", ".adt", ".mos", ".csv", ".txt", ".dat", ".exp")


def punto_de_doblado_normos(pfp: float) -> float:
    """Punto en el que NORMOS dobla de verdad, dado el que imprime.

    El ``.RES`` informa de un punto refinado y continuo —lo saca de una
    parábola de mínimos cuadrados sobre 9 puntos del barrido de simetría,
    ``normospr.for:1268``— pero el doblado **no** usa ese valor. La rutina
    final (601-604, «gefaltetes Spektrum ohne Interpolation», Hoersten 1989)
    lo TRUNCA a un canal entero y suma los canales a pares, a la misma
    distancia a cada lado de ese entero, sin interpolar.

    Los índices de cada par suman ``2·⌊PFP⌋+1``, así que el eje de
    simetría cae en el semientero ``⌊PFP⌋ + 0.5``. Por eso un ``Final
    folding point = 257.23656`` dobla en 257.5, y comparar con sus resultados exige doblar
    donde dobla de verdad y no donde dice que dobla.

    (La cuantización con umbral 0.25 de las líneas 1136-1170 es otra cosa:
    afecta solo a la SEMILLA de cada ciclo de barrido, no al doblado final.)
    """
    return float(np.floor(float(pfp))) + 0.5


def resuelve_fichero_de_datos(job: Path, texto: str | None = None) -> Path | None:
    """Espectro al que apunta un ``.JOB``, buscado **junto al propio ``.JOB``**.

    Las cuatro primeras líneas de un ``.JOB`` son nombres de fichero (datos,
    trabajo, resultados, gráfico) sin ruta: NORMOS corría en DOS con todo en el
    mismo directorio. Se busca ahí, sin distinguir mayúsculas —los ficheros
    vienen de DOS y el nombre declarado rara vez coincide en caja con el del
    disco— y cayendo al nombre del propio ``.JOB`` si el declarado no está.

    Devuelve ``None`` si no se encuentra nada; nunca devuelve una salida de
    NORMOS (``.RES``/``.PLT``) ni el ``.JOB`` mismo.
    """
    job = Path(job)
    carpeta = job.parent
    try:
        vecinos = {p.name.lower(): p for p in carpeta.iterdir() if p.is_file()}
    except OSError:
        return None

    def util(p: Path | None) -> Path | None:
        if p is None or p.suffix.lower() in _EXT_DE_SALIDA:
            return None
        return p if p.resolve() != job.resolve() else None

    # 1. El nombre que declara el .JOB (primera línea que no sea una salida).
    if texto is None:
        try:
            texto = job.read_text(encoding="latin-1", errors="replace")
        except OSError:
            texto = ""
    try:
        declarados = parse_job(texto)["files"] if texto else []
    except NormosJobError:
        declarados = []
    for nombre in declarados:
        hallado = util(vecinos.get(Path(nombre).name.lower()))
        if hallado is not None:
            return hallado

    # 2. El nombre del propio trabajo con una extensión de espectro.
    for ext in _EXT_DE_DATOS:
        hallado = util(vecinos.get((job.stem + ext).lower()))
        if hallado is not None:
            return hallado

    # 3. Un único espectro en la carpeta: no hay ambigüedad posible.
    sueltos = [p for n, p in sorted(vecinos.items())
               if Path(n).suffix in _EXT_DE_DATOS and util(p) is not None]
    return sueltos[0] if len(sueltos) == 1 else None


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


#: Banderas FIT de NORMOS que liberan cada parámetro de Fitbauer, por tipo de
#: subespectro. Basta una: ``gamma2``/``gamma3``/``int1``/``int2`` son razones
#: que mezclan dos parámetros de NORMOS (p. ej. int1 = D13/W13), y si
#: cualquiera de los dos se mueve, la razón también.
_BANDERAS_SITE: dict[str, dict[str, tuple[str, ...]]] = {
    "Sextete": {"gamma1": ("WID", "W13"), "gamma2": ("W23", "W13"),
                "gamma3": ("W13",), "int1": ("D13", "A13", "W13"),
                "int2": ("D23", "A23", "W23")},
    "Doblete": {"gamma1": ("WID",), "gamma2": ("W21",),
                "int2": ("D21", "A21", "W21")},
    "Singlete": {"gamma1": ("WID",)},
}
_BANDERAS_COMUNES_SITE: dict[str, tuple[str, ...]] = {
    "delta": ("ISO",), "quad": ("QUA",), "bhf": ("BHF",),
    "depth": ("DEP", "ARE"), "eta": ("ETA",), "beta": ("THE",),
    "phi": ("PHI",), "bex": ("BEX",), "gax": ("GAX",),
    "relax_log_nu": ("OME",),
}
_BANDERAS_DIST_NITIDO: dict[str, tuple[str, ...]] = {
    "delta": ("ISX",), "quad": ("QUX",), "bhf": ("BHX",),
    "gamma1": ("WIX",), "depth": ("DEX", "ARX"),
    "int1": ("D1X", "A1X"), "int2": ("D2X", "A2X"),
}


def _fija_como_normos(fijos: dict, pref: str, i: int, param: dict,
                      banderas: dict[str, tuple[str, ...]]) -> None:
    """Libera solo lo que el ``.JOB`` marca con ``…FIT=.TRUE.``.

    En NORMOS un parámetro sin su bandera FIT a verdadero queda FIJO. Dejar
    el resto como estuviera en la sesión hacía que Fitbauer ajustara con más
    variables que NORMOS (anchuras e intensidades relativas sueltas), y el
    ajuste importado no era el mismo modelo.
    """
    for nombre in component_defaults(i):
        clave = pref + nombre
        normos = banderas.get(nombre)
        if normos is None:
            fijos.setdefault(clave, True)
            continue
        fijos[clave] = not any(_b(_idx(param, n + "FIT", i)) for n in normos)


def _fija_fondo_como_normos(fijos: dict, param: dict) -> None:
    """BKG(1) se ajusta salvo ``BKGFIT(1)=.FALSE.``; el resto, solo si se pide."""
    fijos["baseline"] = not _b(param.get("BKGFIT(1)", param.get("BKGFIT")), True)
    for n, clave in ((2, "slope"), (3, "curv"), (4, "curv3"), (5, "curv4")):
        fijos[clave] = not _b(param.get(f"BKGFIT({n})"))


def job_to_model_state(text: str) -> dict:
    """Convierte un ``.JOB`` en un ``model_state`` de Fitbauer.

    Devuelve ``{"model_state": {...}, "vmax": float|None,
    "center": float|None, "warnings": [...]}``. Los avisos recogen todo lo que
    NO se ha podido trasladar, que es tan importante como lo que sí.
    """
    j = parse_job(text)
    data, param = j["data"], j["param"]
    avisos: list[str] = []

    if es_job_de_dist(param):
        raise NormosJobError(tr("normos.e_dist_job"))
    nsub = int(_f(param.get("NSUB"), 1))
    if nsub < 1:
        raise NormosJobError(tr("normos.e_nsub"))

    variables: dict[str, float] = {"baseline": 1.0, "slope": 0.0}
    fijos: dict[str, bool] = {}
    tipos: dict[int, str] = {}
    activos: dict[int, bool] = {}
    tratos: dict[int, str] = {}

    # ── Globales ────────────────────────────────────────────────────────────
    _fija_fondo_como_normos(fijos, param)
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
                tr("normos.w_bkg", name=clave, value=param[clave], target=destino))

    # ── Subespectros ────────────────────────────────────────────────────────
    denoms: dict[int, float] = {}
    for i in range(1, nsub + 1):
        nline = int(_f(_idx(param, "NLINE", i), 6))
        kind = _TIPO_POR_NLINE.get(nline)
        if kind is None:
            avisos.append(tr("normos.w_nline", i=i, nline=nline))
            continue
        if nline == 8:
            avisos.append(
                tr("normos.w_octet", i=i))
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
        denoms[i] = denom

        if kind == "Sextete" and _b(_idx(param, "IRELAX", i)):
            # Relajación de Ising de SITE = componente Blume–Tjon de dos
            # estados ±BHF. Equivalencias validadas contra el binario demo
            # (validacion/generador/sonda_relajacion*.py): OME (MHz) = 2ν, y
            # momento relativo P = BHF/BSAT (el demo lo llama BH0). BEXT es
            # global en NORMOS y desplaza las líneas de los dos estados.
            tipos[i] = "BlumeTjon"
            ome = _f(_idx(param, "OME", i), 0.0)
            nu = ome * 1.0e6 / 2.0 if ome > 0 else 0.0
            if nu > 0:
                variables[pref + "relax_log_nu"] = float(np.log10(nu))
            bsat = _f(param.get("BSAT"), 0.0) or _f(_idx(param, "BH0", i), 0.0)
            pol = 0.0
            if bsat > 0:
                pol = float(np.clip(variables[pref + "bhf"] / bsat, -1.0, 1.0))
            variables[pref + "relax_polarization"] = pol
            fijos[pref + "relax_polarization"] = True
            bext = _f(param.get("BEXT"), 0.0)
            variables[pref + "relax_bext"] = bext
            fijos[pref + "relax_bext"] = True
            avisos.append(tr("normos.w_irelax", i=i, ome=f"{ome:g}",
                             lognu=f"{np.log10(nu):.3f}" if nu > 0 else "—",
                             pol=f"{pol:.3g}", bext=f"{bext:g}"))

        if _b(_idx(param, "HAMILT", i)) or _b(param.get("HAMILT")):
            tratos[i] = "hamiltonian"
            variables[pref + "eta"] = _f(_idx(param, "ETA", i), 0.0)
            variables[pref + "beta"] = np.radians(_f(_idx(param, "THE", i), 0.0))
            variables[pref + "phi"] = np.radians(_f(_idx(param, "PHI", i), 0.0))

        _fija_como_normos(fijos, pref, i, param,
                          {**_BANDERAS_COMUNES_SITE, **_BANDERAS_SITE[kind]})

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
                tr("normos.w_ndex_out", target=destino_i, source=fuente_i))
            continue
        factor = _f(param.get(f"FACTOR({destino_i})"), 1.0)
        offset = _f(param.get(f"CONST({destino_i})"), 0.0)
        # Las ligaduras de ARE/DEP son entre ÁREAS; en Fitbauer el parámetro
        # es la PROFUNDIDAD (área = depth·(π/2)·ΣΓ_efectiva). Se reescala con
        # los denominadores del propio JOB: ARE_d = f·ARE_s + c ⇒
        # depth_d = f·(den_s/den_d)·depth_s + c/den_d. Exacto en los valores
        # del JOB; si el ajuste mueve las anchuras, la razón deriva.
        if destino.endswith("_depth") and fuente.endswith("_depth"):
            sub_d = int(destino.split("_")[0][1:])
            sub_s = int(fuente.split("_")[0][1:])
            den_d = denoms.get(sub_d, 0.0)
            den_s = denoms.get(sub_s, 0.0)
            if den_d > 0 and den_s > 0:
                factor *= den_s / den_d
                offset /= den_d
                avisos.append(
                    tr("normos.w_area_link", target=destino_i, source=fuente_i))
        constraints.append({
            "target": destino, "source": fuente,
            "factor": factor, "offset": offset,
        })

    for clave in ("POLAR", "IFSC", "IFGK", "EFGB", "SRELAX",
                  "VOIGT", "EMSPEC", "ISTYPE", "NADD", "NDECKS"):
        if clave in param or clave in data:
            avisos.append(tr("normos.w_key_not_carried", name=clave))

    avisos.append(
        tr("normos.w_bhf_scale"))

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
    vmax = _vmax_con_signo(data, avisos)
    if vmax:
        estado["vars"]["vmax"] = vmax
    centro = _centro_desde_pfp(data, avisos)
    return {"model_state": estado, "vmax": vmax,
            "center": centro, "warnings": avisos}


def _vmax_con_signo(data: dict, avisos: list[str]) -> float | None:
    """VMAX del ``&DATA`` CON su signo.

    En NORMOS el signo de VMAX invierte el espectro (manual de WinNormos
    §2.1.1: «the sign of VMAX will determine whether or not the spectrum will
    be reversed»), y Fitbauer hace lo mismo con un vmax negativo (eje de
    velocidad invertido). Antes se tomaba ``abs(VMAX)``: los trabajos con VMAX
    negativo se abrían reflejados y δ salía con el signo cambiado (los 40 del
    banco real con VMAX < 0, todos con PFP ≈ ND/2, lo confirman: invertidos
    coinciden con el doblado de NORMOS a nivel de ruido). Con PFP ≈ ND el
    manual dice que el signo correcto cambia; no hay casos con que
    comprobarlo, así que se avisa.
    """
    vmax = _f(data.get("VMAX"), 0.0) or None
    if vmax and vmax < 0.0:
        pfp = abs(_f(data.get("PFP"), 0.0))
        avisos.append(tr("normos.w_vmax_negative", vmax=f"{vmax:g}")
                      + (" " + tr("normos.w_vmax_negative_upper") if pfp >= 400.0 else ""))
    return vmax


def _centro_desde_pfp(data: dict, avisos: list[str]) -> float | None:
    """Punto de doblado que declara el ``&DATA``, como METADATO.

    A propósito NO se mete en ``vars["center"]``: en NORMOS ``PFP`` es la
    SEMILLA de la búsqueda, no el punto final. ``normospr.for`` la refina en
    dos ciclos y la cuantiza (:func:`punto_de_doblado_normos`), así que
    imponerla congelaría un valor que el propio NORMOS no usó — en varios de
    los trabajos reales el ``.RES`` acaba a más de un canal del ``PFP`` que
    pedía el ``.JOB``. Fitbauer hace su propia búsqueda, que es el análogo.
    """
    pfp = _f(data.get("PFP"), 0.0) or None
    if not pfp:
        return None
    # NORMOS da el punto de doblado SUPERIOR (~2× el centro interno).
    centro = pfp / 2.0 if pfp >= 400.0 else pfp
    avisos.append(
        tr("normos.w_pfp_seed", pfp=f"{pfp:g}"))
    return centro


def job_to_distribution_state(text: str) -> dict:
    """Convierte un ``.JOB`` de NORMOS-**DIST** en un estado de Fitbauer.

    NORMOS-DIST describe la distribución como una MALLA de subespectros: el
    bloque tiene ``NSB`` puntos que arrancan en ``BHF``/``QUA``/``ISO`` y
    avanzan con paso ``DTB``/``DTQ``/``DTI`` (``distcalf.for``: ``RH = BHF +
    PP*DTB`` con ``PP = IP-1``). Aquí eso se traduce a los ``bmin``/``bmax``/
    ``nbins`` del panel de distribución.

    Los subespectros "cristalinos" (``NXLS``/``NXLL``) son los **componentes
    nítidos** de Fitbauer y se devuelven como componentes discretos normales.

    Devuelve la misma forma que :func:`job_to_model_state` — ``model_state``
    lleva además las claves ``dist_*`` y ``mode_combo_idx`` que la carga de
    sesión ya sabe restaurar — más ``edge_anchor`` y ``n_sharp``.
    """
    j = parse_job(text)
    data, param = j["data"], j["param"]
    avisos: list[str] = []

    if not es_job_de_dist(param):
        raise NormosJobError(
            "no es un trabajo de NORMOS-DIST: no aparece ninguna clave de "
            "distribución. Impórtalo como NORMOS-SITE.")

    # ── Bloque de distribución ──────────────────────────────────────────────
    # NBLK = mayor índice con NSB(i) > 0, y NSB(1) cae a NSUB si no se da
    # (``distinif.for`` líneas 327-329).
    nsb1 = int(_f(_idx(param, "NSB", 1), 0)) or int(_f(param.get("NSUB"), 0))
    nblk = max([i for i in range(1, 6)
                if int(_f(_idx(param, "NSB", i), 0)) > 0] or [1])
    if nblk > 1:
        avisos.append(
            tr("normos.w_n_blocks", n=nblk))
    if nsb1 < 2:
        raise NormosJobError(
            "la malla de la distribución tiene menos de 2 puntos "
            f"(NSB=NSUB={nsb1}); revisa el .JOB")

    method = int(_f(_idx(param, "METHOD", 1), 1))
    distri = int(_f(_idx(param, "DISTRI", 1), 1))
    variable = _VARIABLE_POR_METHOD.get(method)
    if variable is None:
        avisos.append(tr("normos.w_method_unknown", method=method))
        variable = "bhf"
    if method == 2:
        avisos.append(
            tr("normos.w_method2"))
    if method == 3:
        avisos.append(
            tr("normos.w_method3"))
    # DISTRI=4 con METHOD=7 es el Le Caër de NORMOS: sextetes en campo cuyos
    # subespectros (espectros de polvo de Blaes, leídos de un fichero spline)
    # Fitbauer calcula él mismo con el Hamiltoniano exacto; ver más abajo.
    lecaer = distri == 4 and method == 7
    if method in (5, 7) and not lecaer:
        # En METHOD=5/7 el fichero spline guarda los SUBESPECTROS (espectros
        # de polvo de Blaes, ``distcalf.for``), no la distribución: P sigue
        # siendo la del DISTRI. Antes se importaba como forma «Fija».
        avisos.append(
            tr("normos.w_method_file", method=method))

    forma = _FORMA_POR_DISTRI.get(distri)
    # DISTRI=4 con METHOD=6 es el Czjzek de NORMOS: la misma P ∝ ΔEQ⁴·
    # exp(−ΔEQ²/2σ²) que la forma «Czjzek» de Fitbauer, con σ² = STG² + DTQ²
    # (sonda del binario DIST 09.09.1993, 2026-10-14: exponente 4.000 y σ al
    # 1e-5 con DTQ de 0.06 a 0.36, independiente de QUA y WID). Con otro
    # METHOD no hay forma equivalente: se importa como histograma.
    czjzek = distri == 4 and method == 6
    if forma is None and czjzek:
        forma = "Czjzek"
    elif forma is None and lecaer:
        forma = "Le Caër"
    elif forma is None:
        avisos.append(
            tr("normos.w_distri4", method=method))
        forma = "Histograma"
    conc = _f(param.get("CONC"), 0.0)
    if distri == 3:
        forma = "Binomial" if conc > 0.0 else "Fija"

    # ── Malla ───────────────────────────────────────────────────────────────
    # El paso por defecto de DTB es 1.0 (``distinif.for``: IF(DTB.LE.0)DTB=1).
    base = {"bhf": "BHF", "quad": "QUA", "delta": "ISO"}[variable]
    paso_clave = {"bhf": "DTB", "quad": "DTQ", "delta": "DTI"}[variable]
    inicio = _f(_idx(param, base, 1), 0.0)
    paso = _f(_idx(param, paso_clave, 1), 0.0)
    if paso <= 0.0:
        paso = 1.0
        avisos.append(
            tr("normos.w_step", name=paso_clave))
    # NORMOS calcula los subespectros EN los nodos inicio + k·paso; la malla
    # de Fitbauer da centros de bins, así que los bordes van medio paso por
    # fuera (antes los nodos quedaban desplazados medio paso y el paso era
    # (NSB−1)/NSB del de NORMOS: 0.173 en vez de 0.18 con NSB = 25).
    bmin = inicio - 0.5 * paso
    bmax = inicio + (nsb1 - 1) * paso + 0.5 * paso

    dti = _f(_idx(param, "DTI", 1), 0.0)
    dtq = _f(_idx(param, "DTQ", 1), 0.0)
    # DTI/DTQ son por PASO de malla; delta_slope/quad_slope de Fitbauer son por
    # unidad de la variable distribuida.
    delta_slope = dti / paso if variable != "delta" else 0.0
    # OJO: en las distribuciones de CAMPO (METHOD 1-5) NORMOS solo aplica DTI.
    # Sus bucles (``distcalf.for``) calculan «RH = BHF+PP*DTB; RI = ISO+PP*DTI»
    # y NO tocan ΔEQ; DTQ solo entra en METHOD 6/7, donde la malla es de
    # cuadrupolo. Trasladar DTQ aquí metería una correlación que NORMOS nunca
    # aplicó — con DTQ=0.03 y 40 puntos, un ΔEQ que se movería > 1 mm/s.
    quad_slope = 0.0
    if variable == "bhf" and dtq:
        avisos.append(
            tr("normos.w_dtq_ignored", dtq=f"{dtq:g}"))

    gamma = _f(_idx(param, "WID", 1), 0.25) or 0.25
    delta = _f(_idx(param, "ISO", 1), 0.0)
    quad = _f(_idx(param, "QUA", 1), 0.0)
    campo_fijo = _f(_idx(param, "BHF", 1), 0.0) if variable != "bhf" else 33.0
    if variable == "delta" and campo_fijo > 0.0:
        avisos.append(
            tr("normos.w_is_field", bhf=f"{campo_fijo:g}"))
        campo_fijo = 0.0

    if czjzek and campo_fijo > 0.0:
        # Czjzek solo se ofrece con dobletes: con sextetes de campo fijo la
        # forma no aplica.
        avisos.append(tr("normos.w_czjzek_field", bhf=f"{campo_fijo:g}"))
        forma = "Histograma"
        czjzek = False
    if method == 7 and not lecaer and campo_fijo <= 0.0:
        # METHOD=7 es cuadrupolo CON campo, pero el campo va en el spline.
        campo_fijo = 33.0
        avisos.append(tr("normos.w_method7_field"))
    if lecaer and campo_fijo <= 0.0:
        # En NORMOS el campo va en el fichero spline de los subespectros, no
        # en el .JOB: sin BHF hay que ponerlo a mano en el panel.
        campo_fijo = 33.0
        avisos.append(tr("normos.w_lecaer_field"))
    if czjzek or lecaer:
        # En el Czjzek y el Le Caër, STG es su anchura (no la de IS); Fitbauer
        # ajusta σ = √(STG² + DTQ²) (``distcalf.for``: misma compensación).
        stg = _f(_idx(param, "STG", 1), 0.0)
        sigma = float(np.hypot(stg, paso))
        avisos.append(tr("normos.w_lecaer" if lecaer else "normos.w_czjzek",
                         stg=f"{stg:g}", dtq=f"{paso:g}", sigma=f"{sigma:.4g}"))
    elif forma == "Gaussiana" and _f(_idx(param, "STG", 1), 0.0):
        # En toda forma fija NORMOS ensancha STG con el paso para que P no sea
        # más estrecha que un bin (manual de WinNormos §2.3.2): la σ real, la
        # que ajusta Fitbauer, es √(STG² + DTX²). Comprobado en el banco J1
        # (DTB = 1 T): σ ajustada 1.801/3.163/5.112 frente a √(STG²+1) =
        # 1.803/3.162/5.099. STG no es la anchura del desplazamiento isomérico.
        stg = _f(_idx(param, "STG", 1), 0.0)
        avisos.append(tr("normos.w_gauss_sigma", stg=f"{stg:g}",
                         step=paso_clave, dt=f"{paso:g}",
                         sigma=f"{float(np.hypot(stg, paso)):.4g}"))
        if _f(_idx(param, "STI", 1), 0.0):
            avisos.append(tr("normos.w_sti"))
    elif _f(_idx(param, "STI", 1), 0.0) or _f(_idx(param, "STG", 1), 0.0):
        avisos.append(
            tr("normos.w_sti"))

    # ── Regularización ──────────────────────────────────────────────────────
    # SMOOTH (``distauxl.for``) construye λ·D₂ᵀD₂ y SUMA BETA1/BETA2 a las dos
    # esquinas diagonales: eso es exactamente el edge_anchor de Fitbauer. La λ
    # de NORMOS es ABSOLUTA y el α de Fitbauer va normalizado por λ_ref, así
    # que el valor no se traslada — la RAZÓN β/λ sí.
    lamda = _f(_idx(param, "LAMDA", 1), 0.0)
    beta1 = _f(_idx(param, "BETA1", 1), 0.0)
    beta2 = _f(_idx(param, "BETA2", 1), 0.0)
    edge_anchor = max(beta1, beta2) / lamda if lamda > 0.0 else 0.0
    if lamda > 0.0:
        avisos.append(
            tr("normos.w_lamda", lamda=f"{lamda:g}"))
    if beta1 != beta2 and (beta1 or beta2):
        avisos.append(
            tr("normos.w_beta12", b1=f"{beta1:g}", b2=f"{beta2:g}", anchor=f"{edge_anchor:g}"))

    forma_reg = "maxent" if _b(param.get("MAXENT")) else "tikhonov"
    exacto = _b(_idx(param, "EXACT", 1))

    estado: dict = {
        "vars": {"baseline": 1.0, "slope": 0.0},
        "fixed": {},
        "sextet_enabled": {}, "component_kind": {},
        "intensity_mode": {}, "quad_treatment": {},
        "constraints": [], "n_components": 0,
        "absorber_model": "thin",
        "drive_form": "triangular" if _b(data.get("TRIANG"), True) else "sine",
        # Panel de distribución
        "mode_combo_idx": _MODO_GUI[variable],
        "dist_variable": _ETIQUETA_VARIABLE[variable],
        "dist_shape": forma,
        "dist_reg_mode": forma_reg,
        "dist_delta": delta,
        "dist_quad": quad,
        "dist_fixed_bhf": campo_fijo,
        # Campo en una distribución de cuadrupolo = opción avanzada del panel.
        "dist_field_enabled": variable == "quad" and campo_fijo > 0.0,
        "dist_gamma": gamma,
        "dist_bmin": bmin,
        "dist_bmax": bmax,
        "dist_nbins": nsb1,
        "dist_delta_slope": delta_slope,
        "dist_quad_slope": quad_slope,
        "dist_kernel_treatment": "hamiltonian" if exacto else "1st_order",
        "dist_kernel_eta": _f(param.get("ETA"), 0.0),
    }
    if forma in ("Czjzek", "Le Caër"):
        # σ equivalente al STG de NORMOS; fijo si el .JOB no lo refina.
        estado["dist_czjzek_sigma"] = sigma
        bandera = _idx(param, "STGFIT", 1)
        if bandera is not None:
            estado["dist_fixed"] = {"czjzek_sigma": not _b(bandera)}
    if forma == "Binomial":
        # DISTRI=3 con CONC>0: 13 subespectros (0…12 vecinos) que empiezan en
        # BHF/QUA/ISO y avanzan DTB/DTQ/DTI por vecino (sonda DIST 2026-10-09).
        estado["dist_binom_conc"] = conc
        estado["dist_binom_neighbors"] = 12
        estado["dist_binom_start"] = inicio
        estado["dist_binom_step"] = paso
        if nsb1 != 13:
            avisos.append(
                tr("normos.w_binomial_nsb", nsb=nsb1))
    if method == 4:
        estado["dist_source_bhf"] = _f(param.get("BHS"), 33.0)
        estado["dist_source_theta"] = _f(param.get("THETAS"), 0.0)
        estado["dist_absorber_theta"] = _f(param.get("BETA"), 0.0)

    # ── Subespectros cristalinos = componentes nítidos ──────────────────────
    nxls = int(_f(param.get("NXLS"), 0))
    n_sharp = 0
    for i in range(1, nxls + 1):
        nxll = int(_f(_idx(param, "NXLL", i), 6))
        if nxll < 0:
            avisos.append(
                tr("normos.w_nxll_spline", i=i, nxll=nxll))
            continue
        kind = _TIPO_POR_NLINE.get(nxll)
        if kind is None:
            avisos.append(tr("normos.w_nxll", i=i, nxll=nxll))
            continue
        n_sharp += 1
        idx = n_sharp
        pref = f"s{idx}_"
        for nombre, valor in component_defaults(idx).items():
            estado["vars"][pref + nombre] = valor
        estado["component_kind"][str(idx)] = kind
        estado["sextet_enabled"][str(idx)] = True
        estado["intensity_mode"][str(idx)] = "free"
        estado["quad_treatment"][str(idx)] = "1st_order"

        wix = _f(_idx(param, "WIX", i), gamma) or gamma
        # DEX/ARX: área resonante en mm/s (``distinif.for``: «ARX is in mm/s
        # resonant area»). El binario de 1994 la llama DEX, igual que renombró
        # ARE→DEP en SITE.
        area = _f(_idx(param, "DEX", i) or _idx(param, "ARX", i), 0.05)
        estado["vars"][pref + "delta"] = _f(_idx(param, "ISX", i), 0.0)
        estado["vars"][pref + "quad"] = _f(_idx(param, "QUX", i), 0.0)
        estado["vars"][pref + "gamma1"] = wix
        if kind == "Sextete":
            d1x = _f(_idx(param, "D1X", i) or _idx(param, "A1X", i), 3.0)
            d2x = _f(_idx(param, "D2X", i) or _idx(param, "A2X", i), 2.0)
            estado["vars"][pref + "int1"] = d1x
            estado["vars"][pref + "int2"] = d2x
            estado["vars"][pref + "bhf"] = _f(_idx(param, "BHX", i), 33.0)
            suma = 2.0 * wix * (d1x + d2x + 1.0)
        elif kind == "Doblete":
            estado["vars"][pref + "int1"] = 1.0
            estado["vars"][pref + "int2"] = 1.0
            suma = 2.0 * wix
        else:
            estado["vars"][pref + "int1"] = 1.0
            suma = wix
        denom = (np.pi / 2.0) * suma
        estado["vars"][pref + "depth"] = float(area / denom) if denom > 0 else 0.02

        # Banderas con el índice del .JOB (i), claves con el del nítido (idx).
        fijos_i: dict = {}
        _fija_como_normos(fijos_i, "", i, param, _BANDERAS_DIST_NITIDO)
        for nombre, fijo in fijos_i.items():
            if nombre in component_defaults(idx):
                estado["fixed"][pref + nombre] = fijo

    _fija_fondo_como_normos(estado["fixed"], param)
    estado["n_components"] = max(1, n_sharp)
    estado["dist_use_sharp"] = n_sharp > 0
    # Desactivar explícitamente lo que el .JOB no define: si no, los
    # componentes que el usuario tuviera abiertos seguirían sumando como
    # nítidos sobre la distribución recién importada.
    for k in range(n_sharp + 1, 4):
        estado["sextet_enabled"][str(k)] = False

    if edge_anchor > 0.0:
        avisos.append(
            tr("normos.w_beta_gui", anchor=f"{edge_anchor:g}"))

    # Claves que el usuario escribió pero que el namelist de DIST no acepta
    # (``distname.for``): NORMOS las lee y las tira sin avisar.
    ignoradas = sorted({re.sub(r"\(.*", "", k) for k in param}
                       & {"NLINE", "DEP", "DEPFIT", "W13", "W23", "W21",
                          "AKS", "PHS", "MIX", "IFTRAN", "WDS", "FSO"})
    if ignoradas:
        avisos.append(
            tr("normos.w_dist_ignored", keys=", ".join(ignoradas)))

    avisos.append(
        tr("normos.w_bhf_scale"))

    vmax = _vmax_con_signo(data, avisos)
    if vmax:
        estado["vars"]["vmax"] = vmax
    centro = _centro_desde_pfp(data, avisos)
    return {"model_state": estado, "vmax": vmax,
            "center": centro, "warnings": avisos,
            "edge_anchor": edge_anchor, "n_sharp": n_sharp,
            "variable": variable}


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
    if kind == "BlumeTjon" and resto + 1 == 9:
        # OME: Fitbauer guarda log10 ν, que no es lineal en OME.
        return None
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
                       titles: tuple[str, str] = ("Exported from Fitbauer", ""),
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
        # Con su signo: negativo = espectro invertido, igual que en NORMOS.
        data["VMAX"] = f"{float(vmax):g}"
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
            _añade(par, pos, "W13", w13, fijos.get(pref + "gamma3", True))
            _añade(par, pos, "W23", w23, fijos.get(pref + "gamma2", True))
            _añade(par, pos, "D13", d13, fijos.get(pref + "int1", True))
            _añade(par, pos, "D23", d23, fijos.get(pref + "int2", True))
        elif kind == "Doblete":
            wid, w21 = g1, g2
            d21 = float(v.get(pref + "int2", 1.0)) * w21
            suma = wid * (1.0 + d21)
            _añade(par, pos, "WID", wid, fijos.get(pref + "gamma1"))
            _añade(par, pos, "W21", w21, fijos.get(pref + "gamma2", True))
            _añade(par, pos, "D21", d21, fijos.get(pref + "int2", True))
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
