"""Constantes físicas y metadatos de la aplicación Fitbauer (Mössbauer Fe-57)."""
from __future__ import annotations

import numpy as np

# ── Metadatos de la aplicación ────────────────────────────────────────────────
APP_NAME = "Fitbauer"
APP_VERSION = "4.0.2"
APP_AUTHOR = "Jorge Sánchez Marcos"
APP_DEPARTMENT = "Departamento de Química Física · UAM"

# ── Constantes físicas Fe-57 ───────────────────────────────────────────────────
BHF_DEFAULT_T = 33.0
DIST_BHF_RANGE = (0.0, 60.0)
DIST_QUAD_RANGE = (0.0, 7.0)
DIST_RANGE_RESOLUTION = 0.1
MU_N = 5.0507837461e-27          # J/T
E_GAMMA = 14.4125e3 * 1.602176634e-19  # J
C_MM_S = 299_792_458_000.0       # mm/s
G_GROUND = 0.09044 / 0.5         # mu/I, estado fundamental I=1/2
G_EXCITED = -0.1549 / 1.5        # mu/I, estado excitado I=3/2

# ── Posiciones del sextete magnético de Fe-57 ─────────────────────────────────
# Derivadas de primeros principios (mismos momentos nucleares que NORMOS):
# niveles Zeeman E(m) = -g_n·μ_N·B·m y transiciones dipolares magnéticas M1
# (Δm ∈ {-1, 0, +1}). A 33.0 T (330 kOe) dan ±0.840 / ±3.074 / ±5.309 mm/s.
def _fe57_magnetic_line_positions(bhf_t: float) -> np.ndarray:
    """6 posiciones (mm/s) del sextete magnético puro de Fe-57 (δ=0, ΔEQ=0)."""
    u = MU_N * bhf_t * C_MM_S / E_GAMMA          # mm/s por unidad de g_n
    mg = (0.5, -0.5)                             # estado fundamental I=1/2
    me = (1.5, 0.5, -0.5, -1.5)                  # estado excitado  I=3/2
    pos = [u * (G_GROUND * g - G_EXCITED * e)
           for g in mg for e in me if abs(e - g) <= 1.0 + 1e-9]
    return np.sort(np.array(pos, dtype=float))


_BASE_POSITIONS = _fe57_magnetic_line_positions(BHF_DEFAULT_T)


def fe57_sextet_positions(bhf_t: float = BHF_DEFAULT_T) -> np.ndarray:
    # Las posiciones escalan linealmente con el campo
    # (≡ _fe57_magnetic_line_positions(bhf_t)).
    return _BASE_POSITIONS * (bhf_t / BHF_DEFAULT_T)


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
