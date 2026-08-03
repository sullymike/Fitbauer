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
APP_VERSION = "5.0.0"
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
# Posiciones PUBLICADAS de α-Fe (patrón de velocidad estándar), en mm/s. Definen
# la calibración: un espectro de α-Fe ajusta a BHF = 33.0 T, igual que NORMOS.
# NO sustituir por valores teóricos desde los momentos nucleares: el cálculo de
# libro da un desdoblamiento ~0,4 % menor (5.309 vs 5.328 mm/s) y haría que el
# BHF saliera ~0,1 T demasiado alto.
_BASE_POSITIONS = np.array([-10.657, -6.167, -1.677, 1.677, 6.167, 10.657]) * 0.5


def _normos_site_positions() -> np.ndarray:
    """Patrón de NORMOS-SITE a 33 T, derivado de los momentos nucleares.

    Reproduce literalmente el cálculo de ``INIFUN`` (``sitecalf.for``, líneas
    361-382) con las constantes que el propio SITE lleva cableadas para el
    ⁵⁷Fe. Se usan sus valores tal cual —no los CODATA modernos— porque el
    objetivo es coincidir con SITE, no ser más exacto que él:

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
#: * ``"alpha_fe"`` — patrón PUBLICADO de α-Fe. Es el de Fitbauer y define la
#:   calibración: un espectro de α-Fe ajusta a BHF = 33.0 T.
#: * ``"normos"``  — el que NORMOS-SITE deriva de los momentos nucleares.
#:
#: Los dos no difieren en una simple escala: la razón g₃₂/g₁₂ de SITE (−1.7142)
#: no es la que implica el patrón de α-Fe (−1.71723), así que las líneas 3 y 4
#: quedan un 0.30 % fuera mientras las 1 y 6 quedan un 0.045 % dentro. Tras el
#: mejor factor de escala queda un residuo IRREDUCIBLE de ±2.8·10⁻³ mm/s a
#: 33 T en las líneas internas: es antisimétrico, así que ni δ ni ΔE_Q lo
#: absorben. Por eso el "factor k" único que se venía usando para comparar con
#: NORMOS depende de las anchuras relativas de las líneas (0.99957…0.99984).
SEXTET_PATTERNS: dict[str, np.ndarray] = {
    "alpha_fe": _BASE_POSITIONS,
    "normos": _normos_site_positions(),
}

#: Convenio activo. NO se cambia por defecto: derivar las posiciones de los
#: momentos nucleares sesga el BHF ~0.1 T (CHANGELOG v4.0.2/v4.0.3).
_ACTIVE_SEXTET_PATTERN = "alpha_fe"


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
    key = str(name)
    if key not in SEXTET_PATTERNS:
        raise ValueError(
            f"patrón de sexteto desconocido: {name!r} "
            f"(opciones: {sorted(SEXTET_PATTERNS)})"
        )
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


#: Patrón por DEFECTO (α-Fe) como constante. Lo usan los consumidores que no
#: son física —rótulos de la GUI, heurísticas de detección de mínimos, figuras
#: de los manuales—, que no deben seguir al convenio activo. Todo lo que sea
#: cálculo llama a :func:`active_sextet_pattern`.
LINE_POS_33T = _BASE_POSITIONS.copy()
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
    "neel_temp_k": "Temperatura T (K)",
    "neel_log10_keff": "log10 anisotropía Keff (J/m³)",
    "neel_mean_d_nm": "Diámetro mediano d50 (nm)",
    "neel_sigma": "Sigma lognormal de tamaños",
    "neel_log10_tau0": "log10 tiempo de intento τ0 (s)",
    "neel_bins": "Bins de tamaño",
}
