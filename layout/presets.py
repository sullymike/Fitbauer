"""Presets de layout para la aplicación Mössbauer (3 columnas)."""
from __future__ import annotations

# Estructura de cada preset:
#   left   → paneles en columna izquierda (orden top→bottom)
#   right  → paneles en columna derecha   (orden top→bottom)
#   center → siempre contiene la gráfica (no configurable)
#   left_width / right_width → anchos en píxeles (0 = columna oculta)
#
# Paneles disponibles: header, file_info, info_display, calibration,
#                      reference, sim_controls

PRESETS: dict[str, dict] = {
    "Estándar": {
        "description": "Controles a la izquierda, gráfica en el centro.",
        "left": ["header", "file_info", "info_display", "calibration", "reference"],
        "right": ["sim_controls"],
        "left_width": 455,
        "right_width": 0,  # 0 = sim_controls debajo del gráfico
    },
    "Tres columnas": {
        "description": "Controles izquierda, gráfica centro, simulación derecha.",
        "left": ["header", "file_info", "info_display", "calibration", "reference"],
        "right": ["sim_controls"],
        "left_width": 380,
        "right_width": 480,
    },
    "Análisis": {
        "description": "Info y referencia a la derecha para más espacio de gráfica.",
        "left": ["header", "file_info", "calibration"],
        "right": ["info_display", "reference", "sim_controls"],
        "left_width": 360,
        "right_width": 420,
    },
    "Compacto": {
        "description": "Solo calibración a la izquierda, máximo espacio de gráfica.",
        "left": ["header", "calibration"],
        "right": ["sim_controls"],
        "left_width": 320,
        "right_width": 0,
    },
}

DEFAULT_PRESET = "Estándar"
