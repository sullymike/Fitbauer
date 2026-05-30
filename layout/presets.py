"""Presets de layout para la aplicación Mössbauer (3 columnas)."""
from __future__ import annotations

# Estructura de cada preset:
#   left   → paneles en columna izquierda  (orden top→bottom)
#   center → paneles encima del gráfico    (orden top→bottom)
#   right  → paneles en columna derecha    (orden top→bottom)
#   left_width  → ancho px de la columna izquierda
#   right_width → ancho px de la columna derecha (0 = columna oculta;
#                 si sim_controls está en right y right_width=0,
#                 se ancla debajo del gráfico)

PRESETS: dict[str, dict] = {
    "Estándar": {
        "description": "Controles izquierda, simulación debajo del gráfico.",
        "left":        ["file_info", "info_display", "calibration", "reference"],
        "center":      [],
        "right":       ["sim_controls"],
        "left_width":  455,
        "right_width": 0,
    },
    "Tres columnas": {
        "description": "Controles izquierda, gráfica centro, simulación derecha.",
        "left":        ["file_info", "info_display", "calibration", "reference"],
        "center":      [],
        "right":       ["sim_controls"],
        "left_width":  380,
        "right_width": 490,
    },
    "Análisis": {
        "description": "Info y referencia en el centro, simulación a la derecha.",
        "left":        ["file_info", "calibration"],
        "center":      ["info_display", "reference"],
        "right":       ["sim_controls"],
        "left_width":  340,
        "right_width": 460,
    },
    "Compacto": {
        "description": "Solo calibración a la izquierda, máximo espacio de gráfica.",
        "left":        ["calibration"],
        "center":      [],
        "right":       ["sim_controls"],
        "left_width":  310,
        "right_width": 0,
    },
}

DEFAULT_PRESET = "Estándar"
