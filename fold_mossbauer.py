#!/usr/bin/env python3
"""Calcula el folding point y genera un fichero de dos columnas: velocidad y cuentas."""
from __future__ import annotations

import re
import sys
from pathlib import Path

INPUT = Path("FC260124.ws5")
SCAN_MIN = 230
SCAN_MAX = 280


def read_ws5_counts(path: Path) -> list[float]:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<data[^>]*>(.*?)</data>", text, re.S | re.I)
    if not m:
        raise ValueError(f"No se encontro bloque <data> en {path}")
    return [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", m.group(1))]


def chi_square(counts: list[float], n0: int) -> tuple[float, int]:
    """Chi-cuadrado para n0 entero con canales numerados 1..N."""
    n = len(counts)
    max_i = min(n0 - 1, n - n0)
    chi = 0.0
    for i in range(1, max_i + 1):
        # indices Python 0-based; canales 1-based: C(canal) = counts[canal-1]
        diff = counts[n0 + i - 1] - counts[n0 - i - 1]
        chi += diff * diff
    return chi, max_i


def parabolic_vertex(x0: int, ym: float, y0: float, yp: float) -> tuple[float, float]:
    """Vertice de parabola usando puntos (x0-1,ym), (x0,y0), (x0+1,yp)."""
    den = ym - 2.0 * y0 + yp
    if den == 0:
        return float(x0), y0
    xv = x0 + 0.5 * (ym - yp) / den
    a = den / 2.0
    b = (yp - ym) / 2.0
    yv = y0 - b * b / (4.0 * a) if a != 0 else y0
    return xv, yv


def interp_linear_1based(counts: list[float], x: float) -> float:
    """Interpolacion lineal C(x), con x en canales 1..N; extrapola solo en los bordes."""
    n = len(counts)
    if x < 1:
        return counts[0] + (x - 1.0) * (counts[1] - counts[0])
    if x > n:
        return counts[-1] + (x - float(n)) * (counts[-1] - counts[-2])
    if x == n:
        return counts[-1]
    i0 = int(x)  # floor para x>=1
    if abs(x - i0) < 1e-12:
        return counts[i0 - 1]
    frac = x - i0
    return (1.0 - frac) * counts[i0 - 1] + frac * counts[i0]


def pedir_velocidad_maxima() -> float:
    """Pide la velocidad maxima; el fichero se escribe de -V a +V."""
    if len(sys.argv) > 1:
        return abs(float(sys.argv[1].replace(",", ".")))

    while True:
        txt = input("Velocidad maxima del doblado (mm/s, por ejemplo 11.8788): ").strip().replace(",", ".")
        try:
            return abs(float(txt))
        except ValueError:
            print("Introduce un numero valido, por ejemplo: 11.8788")


def main() -> None:
    velocidad_maxima = pedir_velocidad_maxima()
    counts = read_ws5_counts(INPUT)
    n = len(counts)

    chis: dict[int, tuple[float, int]] = {n0: chi_square(counts, n0) for n0 in range(SCAN_MIN, SCAN_MAX + 1)}
    best_n0 = min(chis, key=lambda k: chis[k][0])
    fp, chi_min_interp = parabolic_vertex(
        best_n0,
        chis[best_n0 - 1][0],
        chis[best_n0][0],
        chis[best_n0 + 1][0],
    )

    # 256 puntos doblados, con la misma escala de velocidades que el PLT de Normos:
    # -V ... +V. Para fp fraccionario se interpola linealmente; el ultimo punto
    # requiere una extrapolacion muy pequena en el borde derecho (~0.06 canales).
    folded_rows = []
    n_out = n // 2
    for j in range(n_out):
        distance = j + 0.5
        left_ch = fp - distance
        right_ch = fp + distance
        c_left = interp_linear_1based(counts, left_ch)
        c_right = interp_linear_1based(counts, right_ch)
        folded = 0.5 * (c_left + c_right)
        velocidad = -velocidad_maxima + 2.0 * velocidad_maxima * j / (n_out - 1)
        folded_rows.append((velocidad, folded))

    out_dat = INPUT.with_name(INPUT.stem + "_doblado_velocidad_cuentas.dat")
    with out_dat.open("w", encoding="utf-8") as f:
        for velocidad, folded in folded_rows:
            f.write(f"{velocidad:.8f}\t{folded:.6f}\n")

    print(f"Folding point = {fp:.6f} canales")
    print(f"Fichero escrito: {out_dat.name}")
    print("Columnas: velocidad_mm/s  cuentas")


if __name__ == "__main__":
    main()
