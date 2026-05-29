"""Funciones puras de física Mössbauer (sin dependencias de GUI)."""
from __future__ import annotations

import numpy as np
from scipy.special import wofz

from .constants import LINE_POS_33T, LINE_QUAD_PATTERN, BHF_DEFAULT_T
from .hamiltonian import (
    kundig_sextet_positions,
    kundig_sextet_positions_batch,
    polycrystal_kundig_positions,
)

# Estado global del perfil de línea (modificado por la GUI).
LINE_PROFILE_KIND: str = "Lorentziana"
VOIGT_SIGMA: float = 0.05


def lorentzian(v: np.ndarray, center: float, gamma: float) -> np.ndarray:
    if LINE_PROFILE_KIND == "Gaussiana":
        sigma = max(float(VOIGT_SIGMA), 1e-9)
        return np.exp(-0.5 * ((v - center) / sigma) ** 2)
    if LINE_PROFILE_KIND == "Pseudo-Voigt":
        sigma = max(float(VOIGT_SIGMA), 1e-9)
        f_l = 2.0 * gamma
        f_g = 2.0 * np.sqrt(2.0 * np.log(2.0)) * sigma
        f = (f_g ** 5 + 2.69269 * f_g ** 4 * f_l + 2.42843 * f_g ** 3 * f_l ** 2
             + 4.47163 * f_g ** 2 * f_l ** 3 + 0.07842 * f_g * f_l ** 4 + f_l ** 5) ** 0.2
        f = max(f, 1e-12)
        r = f_l / f
        eta = 1.36603 * r - 0.47719 * r ** 2 + 0.11116 * r ** 3
        hwhm = 0.5 * f
        g_sigma = hwhm / np.sqrt(2.0 * np.log(2.0))
        lor = hwhm * hwhm / ((v - center) ** 2 + hwhm * hwhm)
        gauss = np.exp(-0.5 * ((v - center) / g_sigma) ** 2)
        return eta * lor + (1.0 - eta) * gauss
    if LINE_PROFILE_KIND == "Voigt":
        sigma = max(float(VOIGT_SIGMA), 1e-9)
        denom = sigma * np.sqrt(2.0)
        norm = sigma * np.sqrt(2.0 * np.pi)
        prof = np.real(wofz(((v - center) + 1j * gamma) / denom)) / norm
        # Normalización analítica al pico (v=v0): Re[w(iγ/(σ√2))]/(σ√2π).
        # Independiente del muestreo (antes se dividía por el máximo discreto,
        # que subestima el pico si la malla no cae justo en v0).
        peak = float(np.real(wofz(1j * gamma / denom))) / norm
        return prof / max(peak, 1e-12)
    return gamma * gamma / ((v - center) ** 2 + gamma * gamma)


def sextet_absorption(
    v: np.ndarray,
    delta: float, quad: float, bhf: float,
    gamma1: float, gamma2: float, gamma3: float,
    depth: float, int1: float, int2: float, int3: float,
    *,
    treatment: str = "1st_order",
    beta: float = 0.0,
    n_quad: int = 20,
) -> np.ndarray:
    """Absorción del sextete.

    ``treatment``:
      * ``"1st_order"`` (default): patrón rígido aditivo (modelo histórico).
      * ``"kundig_fixed"``: posiciones por diagonalización del Hamiltoniano
        ω_e I_z + (ΔE_Q/6)(3 I_{z'}^2 − I(I+1)) con ángulo β fijo (rad)
        entre B y V_{zz} (EFG axial, η=0). Mejora 8b.
      * ``"kundig_powder"``: promedio policristal por cuadratura
        Gauss–Legendre de ``n_quad`` orientaciones (β ∈ [0, π]).
    """
    i3 = int3
    i2 = int3 * int2
    i1 = int3 * int1
    weights = np.array([i1, i2, i3, i3, i2, i1], dtype=float)
    g1 = gamma1
    g2 = gamma1 * gamma2
    g3 = gamma1 * gamma3
    gammas = np.array([g1, g2, g3, g3, g2, g1], dtype=float)

    if treatment == "kundig_fixed":
        positions = kundig_sextet_positions(bhf, delta, quad, beta)
        absorption = np.zeros_like(v, dtype=float)
        for pos, weight, gamma in zip(positions, weights, gammas):
            absorption += weight * lorentzian(v, pos, gamma)
        return depth * absorption

    if treatment == "kundig_powder":
        pos_grid, w_grid = polycrystal_kundig_positions(bhf, delta, quad, n_quad)
        absorption = np.zeros_like(v, dtype=float)
        for k in range(pos_grid.shape[0]):
            for j in range(6):
                absorption += w_grid[k] * weights[j] * lorentzian(v, pos_grid[k, j], gammas[j])
        return depth * absorption

    # Default: 1er orden (modelo histórico)
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


def component_absorption(
    v: np.ndarray, kind: str, p: np.ndarray, *, extras: dict | None = None,
) -> np.ndarray:
    if kind == "Singlete":
        delta, _quad, _bhf, gamma1, _gamma2, _gamma3, depth, int1, _int2, _int3 = p
        return singlet_absorption(v, delta, gamma1, depth, int1)
    if kind == "Doblete":
        delta, quad, _bhf, gamma1, gamma2, _gamma3, depth, int1, int2, _int3 = p
        return doublet_absorption(v, delta, quad, gamma1, gamma2, depth, int1, int2)
    if extras:
        return sextet_absorption(
            v, *p,
            treatment=str(extras.get("treatment", "1st_order")),
            beta=float(extras.get("beta", 0.0)),
            n_quad=int(extras.get("n_quad", 20)),
        )
    return sextet_absorption(v, *p)


def total_model(
    v: np.ndarray,
    baseline: float,
    slope: float,
    components,
) -> np.ndarray:
    """``components`` es lista de ``(kind, params)`` o ``(kind, params, extras)``."""
    y = baseline + slope * v
    for comp in components:
        if isinstance(comp, tuple):
            if len(comp) == 3:
                kind, p, extras = comp
                y -= component_absorption(v, kind, p, extras=extras)
            else:
                kind, p = comp
                y -= component_absorption(v, kind, p)
        else:
            y -= sextet_absorption(v, *comp)
    return y
