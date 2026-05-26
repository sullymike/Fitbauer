"""Funciones puras de física Mössbauer (sin dependencias de GUI)."""
from __future__ import annotations

import numpy as np
from scipy.special import wofz

from .constants import LINE_POS_33T, LINE_QUAD_PATTERN, BHF_DEFAULT_T

# Estado global del perfil de línea (modificado por la GUI).
LINE_PROFILE_KIND: str = "Lorentziana"
VOIGT_SIGMA: float = 0.05


def lorentzian(v: np.ndarray, center: float, gamma: float) -> np.ndarray:
    if LINE_PROFILE_KIND == "Voigt":
        sigma = max(float(VOIGT_SIGMA), 1e-9)
        z = ((v - center) + 1j * gamma) / (sigma * np.sqrt(2.0))
        prof = np.real(wofz(z)) / (sigma * np.sqrt(2.0 * np.pi))
        max_prof = float(np.nanmax(prof)) if prof.size else 1.0
        return prof / max(max_prof, 1e-12)
    return gamma * gamma / ((v - center) ** 2 + gamma * gamma)


def sextet_absorption(
    v: np.ndarray,
    delta: float, quad: float, bhf: float,
    gamma1: float, gamma2: float, gamma3: float,
    depth: float, int1: float, int2: float, int3: float,
) -> np.ndarray:
    i3 = int3
    i2 = int3 * int2
    i1 = int3 * int1
    weights = np.array([i1, i2, i3, i3, i2, i1], dtype=float)
    g1 = gamma1
    g2 = gamma1 * gamma2
    g3 = gamma1 * gamma3
    gammas = np.array([g1, g2, g3, g3, g2, g1], dtype=float)
    positions = LINE_POS_33T * (bhf / BHF_DEFAULT_T) + delta + quad * LINE_QUAD_PATTERN
    absorption = np.zeros_like(v, dtype=float)
    for pos, weight, gamma in zip(positions, weights, gammas):
        absorption += weight * lorentzian(v, pos, gamma)
    return depth * absorption


def singlet_absorption(
    v: np.ndarray, delta: float, gamma1: float, depth: float, int1: float,
) -> np.ndarray:
    return depth * int1 * lorentzian(v, delta, gamma1)


def doublet_absorption(
    v: np.ndarray,
    delta: float, quad: float, gamma1: float, gamma2: float,
    depth: float, int1: float, int2: float,
) -> np.ndarray:
    g1 = gamma1
    g2 = gamma1 * gamma2
    return depth * (
        int1 * lorentzian(v, delta - quad / 2.0, g1)
        + int1 * int2 * lorentzian(v, delta + quad / 2.0, g2)
    )


def component_absorption(v: np.ndarray, kind: str, p: np.ndarray) -> np.ndarray:
    if kind == "Singlete":
        delta, _quad, _bhf, gamma1, _gamma2, _gamma3, depth, int1, _int2, _int3 = p
        return singlet_absorption(v, delta, gamma1, depth, int1)
    if kind == "Doblete":
        delta, quad, _bhf, gamma1, gamma2, _gamma3, depth, int1, int2, _int3 = p
        return doublet_absorption(v, delta, quad, gamma1, gamma2, depth, int1, int2)
    return sextet_absorption(v, *p)


def total_model(
    v: np.ndarray,
    baseline: float,
    slope: float,
    components: list[tuple[str, np.ndarray] | np.ndarray],
) -> np.ndarray:
    y = baseline + slope * v
    for comp in components:
        if isinstance(comp, tuple):
            kind, p = comp
            y -= component_absorption(v, kind, p)
        else:
            y -= sextet_absorption(v, *comp)
    return y
