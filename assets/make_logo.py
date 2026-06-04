#!/usr/bin/env python3
"""Genera el logo/icono de Fitbauer.

Diseño: insignia cuadrada redondeada (estilo app moderno) con degradado
azul→cian y, encima, la *firma* de un espectro Mössbauer: un sextete de Fe
(6 líneas de absorción) con su curva de ajuste blanca y los puntos de datos
ligeramente dispersos, evocando el "fit" del nombre.

Salidas en este mismo directorio:
  - fitbauer_logo.svg   (fuente vectorial editable)
  - fitbauer_icon.png   (256x256, para iconphoto/QIcon)
  - fitbauer_icon.ico   (multi-tamaño, para Windows/PyInstaller)

Uso:  python assets/make_logo.py
Requiere: cairosvg, Pillow  (solo para regenerar los rasterizados).
"""
from __future__ import annotations

import io
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Geometría del lienzo
SIZE = 256
MARGIN = 34          # margen horizontal del trazo del espectro
BASELINE = 86.0      # y de la línea base (arriba)
MAX_DIP = 196.0      # y del fondo de la línea más profunda (abajo)

# Sextete de Fe-57: posiciones relativas y razón de intensidades 3:2:1:1:2:3
_POS = [-5.33, -3.08, -0.84, 0.84, 3.08, 5.33]
_INT = [3.0, 2.0, 1.0, 1.0, 2.0, 3.0]
_WIDTH = 0.55        # semianchura lorentziana (mm/s)
_VRANGE = 7.0        # rango de velocidad mostrado [-VRANGE, VRANGE]


def _spectrum_y(v: float) -> float:
    """Transmisión (hacia abajo) del sextete en velocidad v."""
    absorption = 0.0
    for pos, inten in zip(_POS, _INT):
        absorption += inten / (1.0 + ((v - pos) / _WIDTH) ** 2)
    norm = max(_INT)  # la línea exterior llega al fondo
    depth = (MAX_DIP - BASELINE) * (absorption / norm)
    return BASELINE + depth


def _fit_path(n: int = 220) -> str:
    pts = []
    for i in range(n + 1):
        v = -_VRANGE + 2 * _VRANGE * i / n
        x = MARGIN + (SIZE - 2 * MARGIN) * (i / n)
        y = _spectrum_y(v)
        pts.append((x, y))
    d = f"M {pts[0][0]:.2f},{pts[0][1]:.2f} "
    d += " ".join(f"L {x:.2f},{y:.2f}" for x, y in pts[1:])
    return d


def _data_dots():
    """Puntos de 'datos' sobre el fit con un ruido leve determinista."""
    dots = []
    n = 30
    for i in range(n + 1):
        v = -_VRANGE + 2 * _VRANGE * i / n
        x = MARGIN + (SIZE - 2 * MARGIN) * (i / n)
        # ruido pseudoaleatorio reproducible y discreto (parte fraccionaria con signo)
        r = math.sin(i * 12.9898 + 4.0) * 43758.5453
        r -= math.floor(r)
        y = _spectrum_y(v) + (r - 0.5) * 3.4
        dots.append((x, y))
    return dots


def build_svg() -> str:
    fit = _fit_path()
    dots = _data_dots()
    dots_svg = "\n".join(
        f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="#dff3ff" '
        f'fill-opacity="0.9"/>'
        for x, y in dots
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}"
     viewBox="0 0 {SIZE} {SIZE}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0"   stop-color="#0c4a6e"/>
      <stop offset="0.55" stop-color="#0284c7"/>
      <stop offset="1"   stop-color="#38bdf8"/>
    </linearGradient>
    <linearGradient id="glow" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.22"/>
      <stop offset="0.5" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    <filter id="soft" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="1.1"/>
    </filter>
  </defs>

  <!-- Insignia redondeada -->
  <rect x="6" y="6" width="244" height="244" rx="56" fill="url(#bg)"/>
  <rect x="6" y="6" width="244" height="244" rx="56" fill="url(#glow)"/>

  <!-- Línea base (eje de transmisión) -->
  <line x1="{MARGIN}" y1="{BASELINE:.1f}" x2="{SIZE - MARGIN}" y2="{BASELINE:.1f}"
        stroke="#bae6fd" stroke-opacity="0.55" stroke-width="2"
        stroke-dasharray="2 5" stroke-linecap="round"/>

  <!-- Datos -->
{dots_svg}

  <!-- Sombra suave del fit -->
  <path d="{fit}" fill="none" stroke="#06283d" stroke-opacity="0.45"
        stroke-width="9" stroke-linejoin="round" stroke-linecap="round"
        filter="url(#soft)"/>
  <!-- Curva de ajuste -->
  <path d="{fit}" fill="none" stroke="#ffffff"
        stroke-width="6.5" stroke-linejoin="round" stroke-linecap="round"/>
</svg>
"""


def main() -> None:
    svg = build_svg()
    svg_path = HERE / "fitbauer_logo.svg"
    svg_path.write_text(svg, encoding="utf-8")
    print("escrito", svg_path)

    try:
        import cairosvg
        from PIL import Image
    except ImportError:
        print("cairosvg/Pillow no disponibles: solo se generó el SVG.")
        return

    png_bytes = cairosvg.svg2png(
        bytestring=svg.encode("utf-8"), output_width=256, output_height=256
    )
    png_path = HERE / "fitbauer_icon.png"
    png_path.write_bytes(png_bytes)
    print("escrito", png_path)

    base = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    ico_path = HERE / "fitbauer_icon.ico"
    base.save(
        ico_path,
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("escrito", ico_path)


if __name__ == "__main__":
    main()
