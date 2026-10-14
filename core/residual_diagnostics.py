"""Diagnósticos de residuos comunes a los ajustes discreto y de distribución.

Funciones puras sobre el vector de residuos (normalizados por σ o no),
ordenado por velocidad: detectan estructura que el modelo no explica.
"""
from __future__ import annotations

import numpy as np


def residual_lag1(residuals: np.ndarray) -> float:
    """Autocorrelación de los residuos a un canal de distancia.

    Ruido blanco da ≈ 0 (±1/√N); valores claramente positivos indican
    estructura que el modelo no explica (líneas mal descritas, fondo).
    """
    r = np.asarray(residuals, dtype=float).ravel()
    r = r - float(np.mean(r)) if r.size else r
    den = float(np.sum(r * r))
    if r.size < 3 or den <= 0.0:
        return float("nan")
    return float(np.sum(r[1:] * r[:-1]) / den)


def residual_runs_z(residuals: np.ndarray) -> float:
    """Test de rachas de Wald–Wolfowitz sobre el signo de los residuos.

    Devuelve z = (rachas − esperadas)/σ. Con ruido blanco |z| < 2 en el 95 %
    de los casos; z muy negativo = pocas rachas = residuos con estructura.
    """
    r = np.asarray(residuals, dtype=float).ravel()
    s = np.sign(r[r != 0.0])
    n1, n2 = int(np.sum(s > 0)), int(np.sum(s < 0))
    n = n1 + n2
    if n1 == 0 or n2 == 0 or n < 3:
        return float("nan")
    runs = 1 + int(np.sum(s[1:] != s[:-1]))
    mu = 2.0 * n1 * n2 / n + 1.0
    var = (mu - 1.0) * (mu - 2.0) / (n - 1.0)
    return float((runs - mu) / np.sqrt(var)) if var > 0 else float("nan")


def residual_diagnostics(residuals: np.ndarray) -> dict[str, float]:
    """Autocorrelación lag-1 y z del test de rachas, con las claves de ``stats``."""
    return {"resid_lag1": residual_lag1(residuals),
            "resid_runs_z": residual_runs_z(residuals)}
