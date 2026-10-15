"""Constantes físicas y metadatos de la aplicación Fitbauer (Mössbauer Fe-57).

Fuente única de constantes/metadatos/paths compartidos por la interfaz Qt, la
capa headless (core.session) y las utilidades. No importa ninguna GUI.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import numpy as np

# ── Metadatos de la aplicación ────────────────────────────────────────────────
APP_NAME = "Fitbauer"
APP_VERSION = "5.2.4"
APP_AUTHOR = "Jorge Sánchez Marcos, Nieves Menéndez González"
APP_DEPARTMENT = "Departamento de Química Física · UAM"

# ── Rutas del proyecto ────────────────────────────────────────────────────────
# Raíz del repositorio (carpeta padre de core/).
APP_ROOT = Path(__file__).resolve().parent.parent
README_PATH = APP_ROOT / "README.md"
CHANGELOG_PATH = APP_ROOT / "CHANGELOG.md"
APP_ICON_PNG = APP_ROOT / "assets" / "fitbauer_icon.png"
APP_ICON_ICO = APP_ROOT / "assets" / "fitbauer_icon.ico"

# ── Constantes físicas Fe-57 ───────────────────────────────────────────────────
BHF_DEFAULT_T = 33.0
DIST_BHF_RANGE = (0.0, 60.0)
DIST_QUAD_RANGE = (0.0, 7.0)
DIST_RANGE_RESOLUTION = 0.1
# Datos nucleares del Fe-57 (valores de referencia/documentación). La calibración
# NO se hace desde ellos, sino contra el patrón de velocidad de α-Fe (ver abajo).
MU_N = 5.0507837461e-27          # J/T
E_GAMMA = 14.4125e3 * 1.602176634e-19  # J
C_MM_S = 299_792_458_000.0       # mm/s
G_GROUND = 0.09044 / 0.5         # mu/I, estado fundamental I=1/2
G_EXCITED = -0.1549 / 1.5        # mu/I, estado excitado I=3/2

# ── Posiciones del sextete magnético de Fe-57 ─────────────────────────────────
# Patrón HISTÓRICO de Fitbauer (v4.0.3 – v5.2.4), en mm/s a 33 T. NO es una tabla
# publicada: viene de las constantes del software previo del laboratorio, donde
# eran el patrón a 32.95 T; en la v4.0.2 se
# reetiquetaron, sin más, como el de 33.0 T. Su razón g1/g0 (0.5724) no es la de
# ningún par de momentos medido: Violet y Pipkorn (J. Appl. Phys. 42, 4339,
# 1971) dan para α-Fe a 298 K g0 = 3.9098 y g1 = 2.2342 mm/s (0.5714, la misma
# razón que NORMOS). Se conserva para reproducir sesiones y calibraciones
# antiguas; el patrón por defecto es el de NORMOS (abajo).
_LEGACY_POSITIONS = np.array([-10.657, -6.167, -1.677, 1.677, 6.167, 10.657]) * 0.5

def _normos_site_positions() -> np.ndarray:
    """Patrón de NORMOS-SITE a 33 T, derivado de los momentos nucleares.

    Es el desdoblamiento Zeeman de primer orden a partir de los factores g del
    fundamental y del excitado, calculado con las mismas constantes nucleares
    que usa SITE para el ⁵⁷Fe. Se usan esos valores —no los CODATA modernos—
    porque el objetivo es coincidir con SITE, no ser más exacto que él:

        BF  = RMUN·CLIGHT/EGAMMA        (mm/s por magnetón nuclear y Tesla)
        g₁₂ = GFACT,  g₃₂ = g₁₂·GFR·SEX/SG
        AL  = (±g₃₂ ∓ g₁₂)·BF, (±g₃₂/3 ∓ g₁₂)·BF

    Verificado contra el binario demo 27.01.1994 ajustando un sexteto
    sintético del banco de validación: coincide a 6·10⁻⁶ mm/s.
    """
    clight = 2.99792458e11   # mm/s          (PARAMETER CLIGHT de sitecalf.for)
    rmun = 3.152452e-11      # keV/T         (PARAMETER RMUN)
    egamma = 14.4            # keV           (rama INDEX(ISTYPE,'FE'))
    gfact = 0.090604         # g del fundamental
    gfr = -0.5714            # razón de momentos dipolares μ_e/μ_g
    sex, sg = 1.5, 0.5       # espines excitado y fundamental
    bf = rmun * clight / egamma
    g12 = gfact
    g32 = g12 * gfr * sex / sg
    al = np.array([
        (g32 - g12), (g32 / 3.0 - g12), (-g32 / 3.0 - g12),
        (g32 / 3.0 + g12), (-g32 / 3.0 + g12), (-g32 + g12),
    ]) * bf
    return al * BHF_DEFAULT_T


#: Patrones de posiciones del sexteto a 33 T (mm/s), líneas 1..6 ordenadas por
#: velocidad creciente.
#:
#: * ``"normos"`` — derivado de los momentos nucleares, con las constantes de
#:   NORMOS-SITE. Es el patrón por DEFECTO de Fitbauer desde la v5.3.0: tiene
#:   respaldo físico (razón de momentos de Violet y Pipkorn) y hace que Fitbauer
#:   y NORMOS den el mismo BHF.
#: * ``"legacy"`` — el patrón histórico de Fitbauer (ver ``_LEGACY_POSITIONS``).
#:   ``"alpha_fe"``, su nombre anterior, se acepta como alias: así lo guardan
#:   las sesiones y calibraciones hechas hasta la v5.2.4.
#:
#: Los dos no difieren en una simple escala: las líneas 3 y 4 del histórico
#: quedan un 0.30 % dentro y las 1 y 6 un 0.045 % fuera. Sobre el mismo eje de
#: velocidad, el BHF ajustado difiere un ~0.035 %. Calibrar con α-Fe a 33.0 T
#: absorbe casi todo: ver :func:`convert_vmax`.
SEXTET_PATTERNS: dict[str, np.ndarray] = {
    "normos": _normos_site_positions(),
    "legacy": _LEGACY_POSITIONS,
}

#: Nombres anteriores de los patrones (sesiones, preferencias y CLI antiguos).
SEXTET_PATTERN_ALIASES = {"alpha_fe": "legacy"}

#: Patrón por defecto.
DEFAULT_SEXTET_PATTERN = "normos"


def canonical_sextet_pattern(name: str | None) -> str:
    """Nombre canónico de un patrón (resuelve alias). ``None`` → por defecto."""
    if name in (None, ""):
        return DEFAULT_SEXTET_PATTERN
    key = SEXTET_PATTERN_ALIASES.get(str(name), str(name))
    if key not in SEXTET_PATTERNS:
        raise ValueError(
            f"patrón de sexteto desconocido: {name!r} "
            f"(opciones: {sorted(SEXTET_PATTERNS)})")
    return key


#: Escala de velocidad entre patrones. Una calibración con α-Fe a 33.0 T hecha
#: con el patrón histórico da una Vmax que hay que multiplicar por este factor
#: para que el mismo α-Fe dé 33.0 T con el de NORMOS. Calculado ajustando con
#: el patrón de NORMOS (BHF fijo a 33 T, anchura única, 3:2:1, escala libre)
#: un α-Fe generado con el histórico, como hace la calibración: 0.999623, igual
#: a ±4·10⁻⁶ para anchuras de 0.18 a 0.40 mm/s (test en test_patron_sexteto).
#: Con la Vmax convertida, el BHF de una muestra cambia < 0.01 % y δ, ΔEQ un
#: −0.038 %.
_VMAX_LEGACY_TO_NORMOS = 0.999623


def convert_vmax(vmax: float, from_pattern: str | None, to_pattern: str | None) -> float:
    """Vmax de una calibración hecha con ``from_pattern`` para usarla con ``to_pattern``."""
    origen = canonical_sextet_pattern(from_pattern)
    destino = canonical_sextet_pattern(to_pattern)
    if origen == destino:
        return float(vmax)
    if (origen, destino) == ("legacy", "normos"):
        return float(vmax) * _VMAX_LEGACY_TO_NORMOS
    return float(vmax) / _VMAX_LEGACY_TO_NORMOS


#: Convenio activo.
_ACTIVE_SEXTET_PATTERN = DEFAULT_SEXTET_PATTERN


def active_sextet_pattern() -> np.ndarray:
    """Patrón de posiciones a 33 T del convenio activo (mm/s, 6 líneas)."""
    return SEXTET_PATTERNS[_ACTIVE_SEXTET_PATTERN]


def active_sextet_pattern_name() -> str:
    return _ACTIVE_SEXTET_PATTERN


def set_sextet_pattern(name: str) -> str:
    """Fija el convenio de posiciones y devuelve el anterior.

    Cambia la física de TODO el núcleo a la vez (sexteto discreto, kernel de
    distribución, Hamiltoniano completo, Blume-Tjon), porque todos derivan de
    esta única fuente. Para un cambio acotado usa :func:`sextet_pattern`.
    """
    global _ACTIVE_SEXTET_PATTERN
    key = canonical_sextet_pattern(name)
    previous, _ACTIVE_SEXTET_PATTERN = _ACTIVE_SEXTET_PATTERN, key
    return previous


@contextmanager
def sextet_pattern(name: str):
    """Fija el convenio de posiciones durante un bloque y lo restaura al salir.

    Mismo gestor que ``core.physics.line_profile`` para el perfil de línea:
    evita que un cálculo puntual (comparar con NORMOS, generar un banco) deje
    el convenio contaminado para el resto de la sesión.
    """
    previous = set_sextet_pattern(name)
    try:
        yield
    finally:
        set_sextet_pattern(previous)


def fe57_sextet_positions(bhf_t: float = BHF_DEFAULT_T) -> np.ndarray:
    # Escalan linealmente con el campo respecto al patrón activo a 33.0 T.
    return active_sextet_pattern() * (bhf_t / BHF_DEFAULT_T)


#: Patrón por DEFECTO como constante. Lo usan los consumidores que no son
#: física —rótulos de la GUI, heurísticas de detección de mínimos, figuras de
#: los manuales—, que no deben seguir al convenio activo. Todo lo que sea
#: cálculo llama a :func:`active_sextet_pattern`.
LINE_POS_33T = SEXTET_PATTERNS[DEFAULT_SEXTET_PATTERN].copy()
LINE_QUAD_PATTERN = np.array([0.5, -0.5, -0.5, -0.5, -0.5, 0.5], dtype=float)

# ── Nombres y etiquetas de parámetros ─────────────────────────────────────────
GLOBAL_PARAM_NAMES = ["baseline", "slope"]
SEXTET_PARAM_NAMES = [
    "delta", "quad", "bhf", "gamma1", "gamma2", "gamma3", "depth",
    "int1", "int2", "int3",
]
MODEL_PARAM_LABELS = {
    "baseline": "Línea base",
    "slope": "Pendiente",
    "delta": "Desplazamiento isomérico δ",
    "quad": "Cuadrupolo ΔEQ",
    "bhf": "Campo hiperfino BHF (T)",
    "gamma1": "Anchura Γ líneas 1 y 6",
    "gamma2": "Γ relativa líneas 2 y 5",
    "gamma3": "Γ relativa líneas 3 y 4",
    "depth": "Profundidad",
    "int3": "I (líneas 3 y 4)",
    "int2": "I23 (2 = líneas 2,5 / líneas 3,4)",
    "int1": "I13 (3 = líneas 1,6 / líneas 3,4)",
    "relax_fraction": "Fracción bloqueada (relajación)",
    "relax_log_nu": "log10 tasa de relajación ν (s⁻¹)",
    "relax_polarization": "Polarización de poblaciones P (±BHF)",
    "relax_bext": "Campo externo BEXT (T)",
    "neel_temp_k": "Temperatura T (K)",
    "neel_log10_keff": "log10 anisotropía Keff (J/m³)",
    "neel_mean_d_nm": "Diámetro mediano d50 (nm)",
    "neel_sigma": "Sigma lognormal de tamaños",
    "neel_log10_tau0": "log10 tiempo de intento τ0 (s)",
    "neel_bins": "Bins de tamaño",
}
