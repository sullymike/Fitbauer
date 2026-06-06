"""Funciones puras de física Mössbauer (sin dependencias de GUI)."""
from __future__ import annotations

import numpy as np
from scipy.special import wofz

from .constants import LINE_POS_33T, LINE_QUAD_PATTERN, BHF_DEFAULT_T, E_GAMMA
from .hamiltonian import (
    kundig_sextet_positions,
    kundig_sextet_positions_batch,
    polycrystal_kundig_positions,
)

# Estado global del perfil de línea (modificado por la GUI).
LINE_PROFILE_KIND: str = "Lorentziana"
VOIGT_SIGMA: float = 0.05


def lorentzian(v: np.ndarray, center: float, gamma: float) -> np.ndarray:
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


def relaxation_empirical_absorption(
    v: np.ndarray,
    delta: float, quad: float, bhf: float,
    gamma1: float, gamma2: float, gamma3: float,
    depth: float, int1: float, int2: float, int3: float,
    blocked_fraction: float,
    log10_nu: float | None = None,
) -> np.ndarray:
    """Modelo fenomenológico de relajación magnética/superparamagnética.

    Interpola entre una fracción bloqueada (sextete magnético) y una fracción
    de relajación rápida (doblete superparamagnético aparente). No es un modelo
    Blume–Tjon dinámico: es una componente interpretativa para no tratar el
    doblete de relajación rápida como fase química independiente por defecto.

    Si se da ``log10_nu`` (ν en s⁻¹), se aplica una transición fenomenológica:
    ν lento conserva el sextete, ν intermedio añade ensanchamiento máximo y ν
    rápido colapsa hacia el doblete. ``blocked_fraction`` actúa como fracción
    bloqueada máxima; con su valor por defecto 1, ``log10_nu`` gobierna toda la
    transición.

    La forma de doblete se escala para que su área integrada sea comparable al
    área del sextete de profundidad unitaria en la malla de velocidades usada.
    Así ``depth`` mantiene el papel de amplitud/área total aproximada.
    """
    f_blocked = max(0.0, min(1.0, float(blocked_fraction)))
    gamma_eff = float(gamma1)
    if log10_nu is not None and np.isfinite(float(log10_nu)):
        # Centro en el rango intermedio Mössbauer (~10^8.5 s^-1). No pretende
        # ser Blume–Tjon exacto: sólo reproduce límites y ensanchamiento máximo.
        lognu = float(log10_nu)
        center = 8.5
        width = 0.55
        dynamic_blocked = 1.0 / (1.0 + np.exp((lognu - center) / width))
        broad = np.exp(-0.5 * ((lognu - center) / 0.75) ** 2)
        gamma_eff *= 1.0 + 1.6 * broad
        f_blocked *= float(dynamic_blocked)
    sext = sextet_absorption(
        v, delta, quad, bhf, gamma_eff, gamma2, gamma3,
        1.0, int1, int2, int3,
    )
    doub = doublet_absorption(v, delta, quad, gamma_eff, gamma2, 1.0, int1, int2)
    try:
        area_sext = float(np.trapezoid(np.maximum(sext, 0.0), v))
        area_doub = float(np.trapezoid(np.maximum(doub, 0.0), v))
    except AttributeError:  # compatibilidad NumPy antiguo
        area_sext = float(np.trapz(np.maximum(sext, 0.0), v))
        area_doub = float(np.trapz(np.maximum(doub, 0.0), v))
    if np.isfinite(area_sext) and np.isfinite(area_doub) and abs(area_doub) > 1e-12:
        doub = doub * (area_sext / area_doub)
    return float(depth) * (f_blocked * sext + (1.0 - f_blocked) * doub)


_PLANCK_H = 6.62607015e-34
_K_BOLTZMANN = 1.380649e-23
_RELAX_RATE_PER_MM_S = E_GAMMA / (_PLANCK_H * 299_792_458_000.0)


def lognormal_diameter_distribution(
    mean_d_nm: float,
    sigma_lognormal: float,
    n_bins: int = 20,
) -> tuple[np.ndarray, np.ndarray]:
    """Malla y pesos lognormales de diámetros (nm).

    ``mean_d_nm`` se interpreta como mediana de la lognormal. Los pesos se
    normalizan a suma 1. La malla cubre aproximadamente ±4σ en log(d).
    """
    median = max(float(mean_d_nm), 1e-6)
    sigma = max(float(sigma_lognormal), 1e-6)
    n = max(1, int(round(n_bins)))
    if n == 1:
        return np.array([median], dtype=float), np.array([1.0], dtype=float)
    lo = median * np.exp(-4.0 * sigma)
    hi = median * np.exp(4.0 * sigma)
    d = np.exp(np.linspace(np.log(max(lo, 1e-6)), np.log(max(hi, lo * 1.001)), n))
    mu = np.log(median)
    w = np.exp(-0.5 * ((np.log(d) - mu) / sigma) ** 2) / np.maximum(d * sigma, 1e-300)
    w = np.maximum(w, 0.0)
    s = float(np.sum(w))
    if not np.isfinite(s) or s <= 0.0:
        w = np.ones_like(d) / d.size
    else:
        w = w / s
    return d.astype(float), w.astype(float)


def neel_log10_nu(
    diameter_nm: np.ndarray | float,
    temperature_k: float,
    log10_keff: float,
    log10_tau0: float = -9.0,
) -> np.ndarray:
    """Néel--Arrhenius: log10(ν/s⁻¹) para partículas esféricas."""
    d_m = np.asarray(diameter_nm, dtype=float) * 1e-9
    volume = np.pi * np.maximum(d_m, 0.0) ** 3 / 6.0
    keff = 10.0 ** float(log10_keff)
    temp = max(float(temperature_k), 1e-9)
    barrier = keff * volume / (_K_BOLTZMANN * temp)
    return -float(log10_tau0) - barrier / np.log(10.0)


def neel_blocking_temperature(
    diameter_nm: float,
    log10_keff: float,
    tau_m: float = 1e-8,
    log10_tau0: float = -9.0,
) -> float:
    """Temperatura de bloqueo aproximada para una partícula esférica."""
    d_m = max(float(diameter_nm), 0.0) * 1e-9
    volume = np.pi * d_m ** 3 / 6.0
    keff = 10.0 ** float(log10_keff)
    tau0 = 10.0 ** float(log10_tau0)
    denom = _K_BOLTZMANN * np.log(max(float(tau_m) / max(tau0, 1e-300), 1.0000001))
    return float(keff * volume / denom) if denom > 0 else float("nan")


def neel_size_relaxation_absorption(
    v: np.ndarray,
    delta: float, quad: float, bhf: float,
    gamma1: float, gamma2: float, gamma3: float,
    depth: float, int1: float, int2: float, int3: float,
    temperature_k: float,
    log10_keff: float,
    mean_d_nm: float,
    sigma_lognormal: float,
    log10_tau0: float = -9.0,
    n_bins: int = 20,
) -> np.ndarray:
    """Relajación Néel--Arrhenius integrada sobre distribución lognormal."""
    diam, weights = lognormal_diameter_distribution(mean_d_nm, sigma_lognormal, n_bins)
    lognus = neel_log10_nu(diam, temperature_k, log10_keff, log10_tau0)
    total = np.zeros_like(np.asarray(v, dtype=float), dtype=float)
    for w, lognu in zip(weights, lognus):
        total += float(w) * relaxation_blume_tjon_two_state_absorption(
            v, delta, quad, bhf, gamma1, gamma2, gamma3,
            1.0, int1, int2, int3, float(np.clip(lognu, -50.0, 50.0)),
        )
    return float(depth) * total


def two_state_exchange_profile(
    v: np.ndarray,
    center_a: float,
    center_b: float,
    gamma: float,
    log10_nu: float,
) -> np.ndarray:
    """Línea de intercambio de dos estados con saltos simétricos a tasa ν.

    Implementación de primera aproximación tipo Bloch–McConnell/Kubo para dos
    frecuencias que intercambian con la misma tasa. La tasa se introduce como
    ``log10_nu`` en s⁻¹ y se convierte a unidades de velocidad mediante la
    relación Doppler del 57Fe. En el límite lento devuelve la media de dos
    lorentzianas; en el rápido, una única línea en el centro promedio.
    """
    vv = np.asarray(v, dtype=float)
    g = max(float(gamma), 1e-9)
    try:
        rate_v = (10.0 ** float(log10_nu)) / _RELAX_RATE_PER_MM_S
    except OverflowError:
        rate_v = 1e12 / _RELAX_RATE_PER_MM_S
    k = max(float(rate_v), 0.0)
    z1 = g + 1j * (vv - float(center_a))
    z2 = g + 1j * (vv - float(center_b))
    if k <= 0.0:
        return 0.5 * (np.real(g / z1) + np.real(g / z2))
    det = z1 * z2 + k * (z1 + z2)
    det = np.where(np.abs(det) < 1e-300, 1e-300 + 0j, det)
    resp = 0.5 * g * (z1 + z2 + 4.0 * k) / det
    return np.maximum(np.real(resp), 0.0)


def relaxation_blume_tjon_two_state_absorption(
    v: np.ndarray,
    delta: float, quad: float, bhf: float,
    gamma1: float, gamma2: float, gamma3: float,
    depth: float, int1: float, int2: float, int3: float,
    log10_nu: float,
) -> np.ndarray:
    """Modelo dinámico simplificado de dos estados +BHF ↔ -BHF.

    Es la primera versión tipo Blume–Tjon: cada transición intercambia entre la
    frecuencia calculada con +BHF y la calculada con -BHF. Reproduce los límites
    lento (sextete), intermedio (ensanchamiento/coalescencia) y rápido
    (doblete/singlete promediado) sin interpretar la fracción rápida como fase
    química independiente.
    """
    weights = np.array([int3 * int1, int3 * int2, int3, int3, int3 * int2, int3 * int1], dtype=float)
    gammas = float(gamma1) * np.array([1.0, gamma2, gamma3, gamma3, gamma2, 1.0], dtype=float)
    mag = LINE_POS_33T * (float(bhf) / BHF_DEFAULT_T)
    q = float(quad) * LINE_QUAD_PATTERN
    c_plus = float(delta) + q + mag
    c_minus = float(delta) + q - mag
    out = np.zeros_like(np.asarray(v, dtype=float), dtype=float)
    for ca, cb, g, w in zip(c_plus, c_minus, gammas, weights):
        out += float(w) * two_state_exchange_profile(v, float(ca), float(cb), float(g), float(log10_nu))
    return float(depth) * out


def component_absorption(
    v: np.ndarray, kind: str, p: np.ndarray, *, extras: dict | None = None,
) -> np.ndarray:
    if kind == "Singlete":
        delta, _quad, _bhf, gamma1, _gamma2, _gamma3, depth, int1, _int2, _int3 = p
        return singlet_absorption(v, delta, gamma1, depth, int1)
    if kind == "Doblete":
        delta, quad, _bhf, gamma1, gamma2, _gamma3, depth, int1, int2, _int3 = p
        return doublet_absorption(v, delta, quad, gamma1, gamma2, depth, int1, int2)
    if kind == "Relajacion":
        delta, quad, bhf, gamma1, gamma2, gamma3, depth, int1, int2, int3 = p
        frac = 1.0
        log10_nu = None
        if extras is not None:
            frac = float(extras.get("blocked_fraction", extras.get("relax_fraction", 1.0)))
            if "log10_nu" in extras or "relax_log_nu" in extras:
                log10_nu = float(extras.get("log10_nu", extras.get("relax_log_nu")))
        return relaxation_empirical_absorption(
            v, delta, quad, bhf, gamma1, gamma2, gamma3,
            depth, int1, int2, int3, frac, log10_nu,
        )
    if kind == "BlumeTjon":
        delta, quad, bhf, gamma1, gamma2, gamma3, depth, int1, int2, int3 = p
        log10_nu = 5.0
        if extras is not None:
            log10_nu = float(extras.get("log10_nu", extras.get("relax_log_nu", log10_nu)))
        return relaxation_blume_tjon_two_state_absorption(
            v, delta, quad, bhf, gamma1, gamma2, gamma3,
            depth, int1, int2, int3, log10_nu,
        )
    if kind == "NeelSize":
        delta, quad, bhf, gamma1, gamma2, gamma3, depth, int1, int2, int3 = p
        extras = extras or {}
        return neel_size_relaxation_absorption(
            v, delta, quad, bhf, gamma1, gamma2, gamma3,
            depth, int1, int2, int3,
            temperature_k=float(extras.get("temperature_k", extras.get("neel_temp_k", 300.0))),
            log10_keff=float(extras.get("log10_keff", extras.get("neel_log10_keff", 4.0))),
            mean_d_nm=float(extras.get("mean_d_nm", extras.get("neel_mean_d_nm", 8.0))),
            sigma_lognormal=float(extras.get("sigma_lognormal", extras.get("neel_sigma", 0.25))),
            log10_tau0=float(extras.get("log10_tau0", extras.get("neel_log10_tau0", -9.0))),
            n_bins=int(round(float(extras.get("n_bins", extras.get("neel_bins", 20.0))))),
        )
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
    sat_scale: float | None = None,
) -> np.ndarray:
    """Modelo de transmisión.

    ``components`` es lista de ``(kind, params)`` o ``(kind, params, extras)``.

    Si ``sat_scale`` (C>0) se da, se aplica el modelo de absorbente grueso
    (saturación exponencial):

        T = baseline + slope·v − C·(1 − exp(−A_tot/C)),   A_tot = Σ_c A_c.

    En el límite C→∞ se recupera el modelo delgado lineal
    T = baseline + slope·v − A_tot. C es la amplitud de saturación (≈ f_s·baseline).
    """
    a_tot = np.zeros_like(v, dtype=float)
    for comp in components:
        if isinstance(comp, tuple):
            if len(comp) == 3:
                kind, p, extras = comp
                a_tot += component_absorption(v, kind, p, extras=extras)
            else:
                kind, p = comp
                a_tot += component_absorption(v, kind, p)
        else:
            a_tot += sextet_absorption(v, *comp)
    if sat_scale is not None and np.isfinite(sat_scale) and sat_scale > 0:
        a_eff = sat_scale * (1.0 - np.exp(-a_tot / sat_scale))
    else:
        a_eff = a_tot
    return baseline + slope * v - a_eff
