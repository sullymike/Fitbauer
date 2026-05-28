"""Constantes físicas y metadatos de la aplicación Mössbauer Fe-57."""
from __future__ import annotations

import numpy as np

# ── Metadatos de la aplicación ────────────────────────────────────────────────
APP_NAME = "Mössbauer Fe-57 v2IA"
APP_VERSION = "2.0"
APP_AUTHOR = "Jorge Sánchez Marcos"
APP_DEPARTMENT = "Departamento de Química Física · UAM"

# ── Constantes físicas Fe-57 ───────────────────────────────────────────────────
BHF_DEFAULT_T = 33.0
MU_N = 5.0507837461e-27          # J/T
E_GAMMA = 14.4125e3 * 1.602176634e-19  # J
C_MM_S = 299_792_458_000.0       # mm/s
G_GROUND = 0.09044 / 0.5         # mu/I, estado fundamental I=1/2
G_EXCITED = -0.1549 / 1.5        # mu/I, estado excitado I=3/2

# ── Posiciones de referencia ───────────────────────────────────────────────────
_BASE_POSITIONS = np.array([-10.657, -6.167, -1.677, 1.677, 6.167, 10.657]) * 0.5


def fe57_sextet_positions(bhf_t: float = BHF_DEFAULT_T) -> np.ndarray:
    return _BASE_POSITIONS * (bhf_t / 32.95)


LINE_POS_33T = fe57_sextet_positions(BHF_DEFAULT_T)
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
}
