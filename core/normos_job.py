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
    lo TRUNCA a entero y suma canales enteros, sin interpolar::

        IPFA = PFA + 1.0E-4          ! asignación real→entero: trunca
        IPFP = PFP + 1.0E-4
        DO 602 L=1,NP
          TEMP(L) = Y(IPFA-L+1) + Y(IPFA+L)

    Los pares suman ``2·IPFA+1``, así que el eje de simetría cae en el
    semientero ``⌊PFP⌋ + 0.5``. Por eso un ``Final folding point =
    257.23656`` dobla en 257.5, y comparar con sus resultados exige doblar
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
        raise NormosJobError(
            "es un trabajo de NORMOS-DIST (distribuciones), no de NORMOS-SITE: "
            "su NSUB son los puntos de la malla de la distribución, no sitios "
            "discretos. Configura la distribución desde el panel de Fitbauer.")
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
    denoms: dict[int, float] = {}
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
        denoms[i] = denom

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
                    f"ligadura de área NDEX({destino_i})={fuente_i} reescalada "
                    "a profundidades con las anchuras del JOB; si el ajuste "
                    "cambia las anchuras, revisa la razón de áreas.")
        constraints.append({
            "target": destino, "source": fuente,
            "factor": factor, "offset": offset,
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
    if vmax:
        estado["vars"]["vmax"] = abs(vmax)
    centro = _centro_desde_pfp(data, avisos)
    return {"model_state": estado, "vmax": abs(vmax) if vmax else None,
            "center": centro, "warnings": avisos}


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
        f"PFP={pfp:g} es la SEMILLA de la búsqueda del punto de doblado, no el "
        "punto final: NORMOS lo refina en dos ciclos y lo cuantiza a múltiplos "
        "de medio canal. No se impone — Fitbauer hace su propia búsqueda. Si "
        "quieres forzarlo, ponlo a mano en «Centro».")
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
            f"el trabajo tiene {nblk} bloques de distribución (NSB(2..)>0); "
            "Fitbauer solo maneja uno: se importa el bloque 1.")
    if nsb1 < 2:
        raise NormosJobError(
            "la malla de la distribución tiene menos de 2 puntos "
            f"(NSB=NSUB={nsb1}); revisa el .JOB")

    method = int(_f(_idx(param, "METHOD", 1), 1))
    distri = int(_f(_idx(param, "DISTRI", 1), 1))
    variable = _VARIABLE_POR_METHOD.get(method)
    if variable is None:
        avisos.append(f"METHOD={method} desconocido; se asume distribución de BHF.")
        variable = "bhf"
    if method == 2:
        avisos.append(
            "METHOD=2 (asimetría de primer orden a la Brand): Fitbauer modela "
            "esa asimetría con la correlación δ(H), ya trasladada desde DTI, "
            "pero no con el desarrollo de Brand completo.")
    if method == 3:
        avisos.append(
            "METHOD=3 (suma sobre vecinos de Billard & Chamberod) no está en "
            "Fitbauer: se importa como distribución simple con las mismas "
            "correlaciones δ(H)/ΔEQ(H).")
    if method in (5, 7):
        avisos.append(
            f"METHOD={method} lee la distribución de un fichero externo; en "
            "Fitbauer eso es la forma «Fija»: carga el fichero a mano.")

    forma = _FORMA_POR_DISTRI.get(distri)
    if forma is None:
        avisos.append(
            "DISTRI=4 (Czjzek si METHOD=6, Le Caer si METHOD=7) no está "
            "implementado en Fitbauer: se importa como histograma.")
        forma = "Histograma"
    conc = _f(param.get("CONC"), 0.0)
    if distri == 3:
        forma = "Binomial" if conc > 0.0 else "Fija"
    if method in (5, 7):
        forma = "Fija"

    # ── Malla ───────────────────────────────────────────────────────────────
    # El paso por defecto de DTB es 1.0 (``distinif.for``: IF(DTB.LE.0)DTB=1).
    base = {"bhf": "BHF", "quad": "QUA", "delta": "ISO"}[variable]
    paso_clave = {"bhf": "DTB", "quad": "DTQ", "delta": "DTI"}[variable]
    inicio = _f(_idx(param, base, 1), 0.0)
    paso = _f(_idx(param, paso_clave, 1), 0.0)
    if paso <= 0.0:
        paso = 1.0
        avisos.append(
            f"{paso_clave} no positivo: NORMOS usa 1.0 por defecto y aquí "
            "también, pero comprueba el rango de la malla.")
    bmin, bmax = inicio, inicio + (nsb1 - 1) * paso

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
            f"DTQ={dtq:g} aparece en el .JOB pero NORMOS lo IGNORA en las "
            "distribuciones de campo (METHOD 1-5): solo DTI modula el "
            "subespectro. No se traslada.")

    gamma = _f(_idx(param, "WID", 1), 0.25) or 0.25
    delta = _f(_idx(param, "ISO", 1), 0.0)
    quad = _f(_idx(param, "QUA", 1), 0.0)
    campo_fijo = _f(_idx(param, "BHF", 1), 0.0) if variable != "bhf" else 33.0

    if _f(_idx(param, "STI", 1), 0.0) or _f(_idx(param, "STG", 1), 0.0):
        avisos.append(
            "STI/STG (anchura gaussiana del desplazamiento isomérico) no se "
            "traslada; en Fitbauer la vía equivalente es el perfil Voigt.")

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
            f"LAMDA={lamda:g} no se traslada tal cual: el α de Fitbauer es "
            "adimensional (normalizado por λ_ref) y el de NORMOS absoluto. "
            "Usa la L-curve para fijarlo.")
    if beta1 != beta2 and (beta1 or beta2):
        avisos.append(
            f"BETA1={beta1:g} y BETA2={beta2:g} anclan los dos extremos de la "
            "malla con pesos distintos; Fitbauer usa un solo edge_anchor y se "
            f"toma el mayor ({edge_anchor:g} relativo a λ).")

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
        "dist_gamma": gamma,
        "dist_bmin": bmin,
        "dist_bmax": bmax,
        "dist_nbins": nsb1,
        "dist_delta_slope": delta_slope,
        "dist_quad_slope": quad_slope,
        "dist_kernel_treatment": "hamiltonian" if exacto else "1st_order",
        "dist_kernel_eta": _f(param.get("ETA"), 0.0),
    }
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
                f"sitio cristalino {i}: NXLL={nxll} apunta a un espectro de "
                "spline en fichero; no se importa.")
            continue
        kind = _TIPO_POR_NLINE.get(nxll)
        if kind is None:
            avisos.append(f"sitio cristalino {i}: NXLL={nxll} no soportado; se omite.")
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

        for norm, mio in (("ISX", "delta"), ("QUX", "quad"), ("BHX", "bhf"),
                          ("WIX", "gamma1"), ("DEX", "depth"), ("ARX", "depth")):
            bandera = _idx(param, norm + "FIT", i)
            if bandera is not None:
                estado["fixed"][pref + mio] = not _b(bandera)

    estado["n_components"] = max(1, n_sharp)
    estado["dist_use_sharp"] = n_sharp > 0
    # Desactivar explícitamente lo que el .JOB no define: si no, los
    # componentes que el usuario tuviera abiertos seguirían sumando como
    # nítidos sobre la distribución recién importada.
    for k in range(n_sharp + 1, 4):
        estado["sextet_enabled"][str(k)] = False

    if edge_anchor > 0.0:
        avisos.append(
            f"BETA1/BETA2 anclan los extremos de la malla (β/λ = "
            f"{edge_anchor:g}). El panel de la GUI no expone ese control: si "
            "lo necesitas, pásalo como «edge_anchor» a "
            "fit_hyperfine_distribution.")

    # Claves que el usuario escribió pero que el namelist de DIST no acepta
    # (``distname.for``): NORMOS las lee y las tira sin avisar.
    ignoradas = sorted({re.sub(r"\(.*", "", k) for k in param}
                       & {"NLINE", "DEP", "DEPFIT", "W13", "W23", "W21",
                          "AKS", "PHS", "MIX", "IFTRAN", "WDS", "FSO"})
    if ignoradas:
        avisos.append(
            "NORMOS-DIST IGNORA estas claves del .JOB (no están en su "
            f"namelist &PARAM): {', '.join(ignoradas)}. Si venían de un "
            "trabajo de SITE, ese subespectro no entró en el ajuste.")

    avisos.append(
        "BHF viene en la escala de NORMOS (posiciones derivadas de los "
        "momentos nucleares). Para reproducirla, ajusta con "
        "core.constants.sextet_pattern(\"normos\").")

    vmax = _f(data.get("VMAX"), 0.0) or None
    if vmax:
        estado["vars"]["vmax"] = abs(vmax)
    centro = _centro_desde_pfp(data, avisos)
    return {"model_state": estado, "vmax": abs(vmax) if vmax else None,
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
