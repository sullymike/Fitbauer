"""Intervalos de confianza por verosimilitud perfilada.

Funciones puras para encontrar los cruces Δχ² = 1 (1σ) y Δχ² = 4 (2σ)
de una curva de coste perfilada, dado un conjunto de valores escaneados
y sus χ² correspondientes (ya restada la χ²_min, es decir, Δχ²).
"""
from __future__ import annotations

import numpy as np


def find_crossing(scan_values: np.ndarray, d_chi2: np.ndarray,
                  best_value: float, level: float) -> tuple[float | None, float | None]:
    """Localiza los cruces de ``d_chi2 = level`` a izquierda y derecha de ``best_value``.

    Devuelve ``(minus, plus)``: distancias positivas desde el óptimo a los
    cruces (None si la curva no llega al nivel en ese lado).
    """
    v = np.asarray(scan_values, dtype=float)
    d = np.asarray(d_chi2, dtype=float)
    order = np.argsort(v)
    v = v[order]; d = d[order]
    best_idx = int(np.argmin(np.abs(v - best_value)))

    def _interp(i_lo: int, i_hi: int) -> float:
        x0, x1 = v[i_lo], v[i_hi]
        y0, y1 = d[i_lo], d[i_hi]
        if y1 == y0:
            return 0.5 * (x0 + x1)
        f = (level - y0) / (y1 - y0)
        return float(x0 + f * (x1 - x0))

    plus = None
    for i in range(best_idx, len(v) - 1):
        if (d[i] - level) * (d[i + 1] - level) <= 0 and not (d[i] <= level and d[i + 1] <= level and i > best_idx):
            x = _interp(i, i + 1)
            if x > best_value:
                plus = x - best_value
                break

    minus = None
    for i in range(best_idx, 0, -1):
        if (d[i] - level) * (d[i - 1] - level) <= 0 and not (d[i] <= level and d[i - 1] <= level and i < best_idx):
            x = _interp(i, i - 1)
            if x < best_value:
                minus = best_value - x
                break

    return minus, plus


def asymmetric_intervals(scan_values: np.ndarray, d_chi2: np.ndarray,
                         best_value: float) -> dict[str, float | None]:
    """Devuelve los intervalos 1σ (Δχ²=1) y 2σ (Δχ²=4) asimétricos."""
    m1, p1 = find_crossing(scan_values, d_chi2, best_value, 1.0)
    m2, p2 = find_crossing(scan_values, d_chi2, best_value, 4.0)
    return {"minus_1s": m1, "plus_1s": p1, "minus_2s": m2, "plus_2s": p2}
