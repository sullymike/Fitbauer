"""Presets de layout predefinidos para la aplicación Mössbauer."""
from __future__ import annotations

# Cada preset define qué paneles van en la columna izquierda y cuáles en la
# derecha. Los paneles 'plot' y 'sim_controls' siempre van en la derecha
# (plot ocupa el espacio disponible, sim_controls se ancla abajo) y no son
# reconfigurables por el usuario.
PRESETS: dict[str, dict] = {
    "Estándar": {
        "description": "Controles a la izquierda, gráfica a la derecha.",
        "left": ["header", "file_info", "info_display", "calibration", "reference"],
        "right": [],
        "left_width": 455,
    },
    "Análisis": {
        "description": "Info y referencia a la derecha para más espacio de gráfica.",
        "left": ["header", "file_info", "calibration"],
        "right": ["info_display", "reference"],
        "left_width": 380,
    },
    "Compacto": {
        "description": "Solo calibración a la izquierda, máximo espacio de gráfica.",
        "left": ["header", "calibration"],
        "right": ["file_info", "info_display"],
        "left_width": 340,
    },
    "Gráfica primero": {
        "description": "Gráfica amplia con controles mínimos a la izquierda.",
        "left": ["calibration", "reference"],
        "right": ["header", "file_info", "info_display"],
        "left_width": 310,
    },
}

DEFAULT_PRESET = "Estándar"
