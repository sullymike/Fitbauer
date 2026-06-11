#!/usr/bin/env python3
"""Ajuste de distribucion de campo hiperfino P(BHF) para espectros Mossbauer.

Implementa un primer backend independiente tipo Hesse-Ruebartsch: el espectro se
modela como una suma regularizada de sextetes con distintos BHF y pesos no
negativos::

    y(v) = baseline + slope * v - sum_j P_j * sextet(v; delta, quad, gamma, B_j)

La regularizacion penaliza segundas diferencias de P. No hay GUI aqui; este
modulo esta pensado para ser llamado desde pruebas, endpoints web o una futura
interfaz.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import lsq_linear, nnls

# Fuente única de las posiciones del sextete: patrón de velocidad PUBLICADO de
# α-Fe (±0.839 / ±3.084 / ±5.329 mm/s a 33 T), igual que NORMOS. No derivar de
# los momentos nucleares (sesgaría el BHF ~0.1 T; ver CHANGELOG v4.0.2/v4.0.3).
from core.constants import LINE_POS_33T, E_GAMMA

BHF_DEFAULT_T = 33.0
LINE_QUAD_PATTERN = np.array([0.5, -0.5, -0.5, -0.5, -0.5, 0.5], dtype=float)
_PLANCK_H = 6.62607015e-34
_K_BOLTZMANN = 1.380649e-23
_RELAX_RATE_PER_MM_S = E_GAMMA / (_PLANCK_H * 299_792_458_000.0)


@dataclass(frozen=True)
class BhfQuadDistribution2DFit:
    """Resultado de una distribución bidimensional P(BHF, ΔEQ)."""

    bhf_centers: np.ndarray
    quad_centers: np.ndarray
    weights: np.ndarray
    probability: np.ndarray
    fitted_curve: np.ndarray
    residuals: np.ndarray
    baseline: float
    slope: float
    alpha_bhf: float
    alpha_quad: float
    rms: float
    success: bool
    message: str
    x_variable: str = "bhf"
    y_variable: str = "quad"
    effective_dof: float | None = None
    marginal_bhf: np.ndarray | None = None
    marginal_quad: np.ndarray | None = None
    mean_bhf: float | None = None
    mean_quad: float | None = None
    sigma_bhf: float | None = None
    sigma_quad: float | None = None
    corr_bhf_quad: float | None = None
    dof_warning: str | None = None
    sharp_bhf_centers: np.ndarray | None = None
    sharp_weights: np.ndarray | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "BHF_centers": self.bhf_centers.tolist(),
            "quad_centers": self.quad_centers.tolist(),
            "P": self.weights.tolist(),
            "probability": self.probability.tolist(),
            "fitted_curve": self.fitted_curve.tolist(),
            "residuals": self.residuals.tolist(),
            "baseline": self.baseline,
            "slope": self.slope,
            "alpha_bhf": self.alpha_bhf,
            "alpha_quad": self.alpha_quad,
            "rms": self.rms,
            "x_variable": self.x_variable,
            "y_variable": self.y_variable,
            "success": self.success,
            "message": self.message,
            "effective_dof": self.effective_dof,
            "marginal_bhf": [] if self.marginal_bhf is None else self.marginal_bhf.tolist(),
            "marginal_quad": [] if self.marginal_quad is None else self.marginal_quad.tolist(),
            "mean_bhf": self.mean_bhf,
            "mean_quad": self.mean_quad,
            "sigma_bhf": self.sigma_bhf,
            "sigma_quad": self.sigma_quad,
            "corr_bhf_quad": self.corr_bhf_quad,
            "dof_warning": self.dof_warning,
            "sharp_BHF_centers": [] if self.sharp_bhf_centers is None else self.sharp_bhf_centers.tolist(),
            "sharp_weights": [] if self.sharp_weights is None else self.sharp_weights.tolist(),
        }


@dataclass(frozen=True)
class BhfDistributionFit:
    """Resultado del ajuste de distribucion de BHF."""

    bhf_centers: np.ndarray
    weights: np.ndarray
    probability: np.ndarray
    fitted_curve: np.ndarray
    residuals: np.ndarray
    baseline: float
    slope: float
    alpha: float
    rms: float
    success: bool
    message: str
    sharp_bhf_centers: np.ndarray | None = None
    sharp_weights: np.ndarray | None = None
    fitted_dist_center: float | None = None
    fitted_dist_sigma: float | None = None
    fitted_dist_p: float | None = None
    effective_dof: float | None = None
    weight_sigma: np.ndarray | None = None

    def as_dict(self) -> dict[str, Any]:
        """Devuelve un dict serializable en JSON tras convertir arrays a listas."""
        return {
            "BHF_centers": self.bhf_centers.tolist(),
            "P": self.weights.tolist(),
            "probability": self.probability.tolist(),
            "fitted_curve": self.fitted_curve.tolist(),
            "residuals": self.residuals.tolist(),
            "baseline": self.baseline,
            "slope": self.slope,
            "alpha": self.alpha,
            "rms": self.rms,
            "success": self.success,
            "message": self.message,
            "sharp_BHF_centers": [] if self.sharp_bhf_centers is None else self.sharp_bhf_centers.tolist(),
            "sharp_weights": [] if self.sharp_weights is None else self.sharp_weights.tolist(),
            "fitted_dist_center": self.fitted_dist_center,
            "fitted_dist_sigma": self.fitted_dist_sigma,
            "fitted_dist_p": self.fitted_dist_p,
            "effective_dof": self.effective_dof,
            "weight_sigma": [] if self.weight_sigma is None else self.weight_sigma.tolist(),
        }


def lorentzian(v: np.ndarray, center: float, gamma: float) -> np.ndarray:
    """Lorentziana normalizada a altura 1; gamma es HWHM."""
    gamma = max(float(gamma), 1e-9)
    return gamma * gamma / ((v - center) ** 2 + gamma * gamma)


def sextet_absorption(
    v: np.ndarray,
    *,
    delta: float,
    quad: float,
    bhf: float,
    gamma: float,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
) -> np.ndarray:
    """Absorcion positiva de un sextete Fe-57 con profundidad unitaria.

    Las intensidades siguen la convencion del GUI actual:
    int2_rel=1 -> I2=(2/3)*I1; int3_rel=1 -> I3=(1/3)*I1.
    """
    v = np.asarray(v, dtype=float)
    i1 = float(int1)
    i2 = i1 * (2.0 / 3.0) * float(int2_rel)
    i3 = i1 * (1.0 / 3.0) * float(int3_rel)
    weights = np.array([i1, i2, i3, i3, i2, i1], dtype=float)
    gammas = float(gamma) * np.array([1.0, gamma2_rel, gamma3_rel, gamma3_rel, gamma2_rel, 1.0], dtype=float)
    positions = LINE_POS_33T * (float(bhf) / BHF_DEFAULT_T) + float(delta) + float(quad) * LINE_QUAD_PATTERN

    absorption = np.zeros_like(v, dtype=float)
    for pos, weight, width in zip(positions, weights, gammas):
        absorption += weight * lorentzian(v, float(pos), float(width))
    return absorption


def singlet_absorption(v: np.ndarray, *, delta: float, gamma: float, int1: float = 1.0) -> np.ndarray:
    """Absorcion positiva de un singlete con profundidad unitaria."""
    return float(int1) * lorentzian(np.asarray(v, dtype=float), float(delta), float(gamma))


def doublet_absorption(
    v: np.ndarray,
    *,
    delta: float,
    quad: float,
    gamma: float,
    gamma2_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
) -> np.ndarray:
    """Absorcion positiva de un doblete con profundidad unitaria."""
    v = np.asarray(v, dtype=float)
    g1 = float(gamma)
    g2 = g1 * float(gamma2_rel)
    i1 = float(int1)
    return i1 * lorentzian(v, float(delta) - float(quad) / 2.0, g1) + i1 * float(int2_rel) * lorentzian(v, float(delta) + float(quad) / 2.0, g2)


def relaxation_empirical_absorption(
    v: np.ndarray,
    *,
    delta: float,
    quad: float,
    bhf: float,
    gamma: float,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    blocked_fraction: float = 1.0,
    log10_nu: float | None = None,
) -> np.ndarray:
    """Perfil unitario fenomenológico: sextete bloqueado + doblete SPM."""
    f_blocked = max(0.0, min(1.0, float(blocked_fraction)))
    gamma_eff = float(gamma)
    if log10_nu is not None and np.isfinite(float(log10_nu)):
        lognu = float(log10_nu)
        center = 8.5
        width = 0.55
        dynamic_blocked = 1.0 / (1.0 + np.exp((lognu - center) / width))
        broad = np.exp(-0.5 * ((lognu - center) / 0.75) ** 2)
        gamma_eff *= 1.0 + 1.6 * broad
        f_blocked *= float(dynamic_blocked)
    sext = sextet_absorption(
        v, delta=delta, quad=quad, bhf=bhf, gamma=gamma_eff,
        gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel,
        int1=int1, int2_rel=int2_rel, int3_rel=int3_rel,
    )
    doub = doublet_absorption(
        v, delta=delta, quad=quad, gamma=gamma_eff,
        gamma2_rel=gamma2_rel, int1=int1, int2_rel=int2_rel,
    )
    try:
        area_sext = float(np.trapezoid(np.maximum(sext, 0.0), v))
        area_doub = float(np.trapezoid(np.maximum(doub, 0.0), v))
    except AttributeError:
        area_sext = float(np.trapz(np.maximum(sext, 0.0), v))
        area_doub = float(np.trapz(np.maximum(doub, 0.0), v))
    if np.isfinite(area_sext) and np.isfinite(area_doub) and abs(area_doub) > 1e-12:
        doub = doub * (area_sext / area_doub)
    return f_blocked * sext + (1.0 - f_blocked) * doub


def two_state_exchange_profile(
    v: np.ndarray,
    center_a: float,
    center_b: float,
    gamma: float,
    log10_nu: float,
) -> np.ndarray:
    vv = np.asarray(v, dtype=float)
    g = max(float(gamma), 1e-9)
    rate_v = (10.0 ** float(log10_nu)) / _RELAX_RATE_PER_MM_S
    k = max(float(rate_v), 0.0)
    z1 = g + 1j * (vv - float(center_a))
    z2 = g + 1j * (vv - float(center_b))
    if k <= 0.0:
        return 0.5 * (np.real(g / z1) + np.real(g / z2))
    det = z1 * z2 + k * (z1 + z2)
    det = np.where(np.abs(det) < 1e-300, 1e-300 + 0j, det)
    resp = 0.5 * g * (z1 + z2 + 4.0 * k) / det
    return np.maximum(np.real(resp), 0.0)


def blume_tjon_two_state_absorption(
    v: np.ndarray,
    *,
    delta: float,
    quad: float,
    bhf: float,
    gamma: float,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    log10_nu: float = 5.0,
) -> np.ndarray:
    i1 = float(int1)
    i2 = i1 * (2.0 / 3.0) * float(int2_rel)
    i3 = i1 * (1.0 / 3.0) * float(int3_rel)
    weights = np.array([i1, i2, i3, i3, i2, i1], dtype=float)
    gammas = float(gamma) * np.array([1.0, gamma2_rel, gamma3_rel, gamma3_rel, gamma2_rel, 1.0], dtype=float)
    mag = LINE_POS_33T * (float(bhf) / BHF_DEFAULT_T)
    q = float(quad) * LINE_QUAD_PATTERN
    c_plus = float(delta) + q + mag
    c_minus = float(delta) + q - mag
    out = np.zeros_like(np.asarray(v, dtype=float), dtype=float)
    for ca, cb, g, w in zip(c_plus, c_minus, gammas, weights):
        out += float(w) * two_state_exchange_profile(v, float(ca), float(cb), float(g), float(log10_nu))
    return out


def lognormal_diameter_distribution(mean_d_nm: float, sigma_lognormal: float, n_bins: int = 20) -> tuple[np.ndarray, np.ndarray]:
    median = max(float(mean_d_nm), 1e-6)
    sigma = max(float(sigma_lognormal), 1e-6)
    n = max(1, int(round(n_bins)))
    if n == 1:
        return np.array([median]), np.array([1.0])
    d = np.exp(np.linspace(np.log(median * np.exp(-4.0 * sigma)), np.log(median * np.exp(4.0 * sigma)), n))
    mu = np.log(median)
    w = np.exp(-0.5 * ((np.log(d) - mu) / sigma) ** 2) / np.maximum(d * sigma, 1e-300)
    w = np.maximum(w, 0.0)
    w = w / max(float(np.sum(w)), 1e-300)
    return d, w


def neel_log10_nu(diameter_nm: np.ndarray, temperature_k: float, log10_keff: float, log10_tau0: float = -9.0) -> np.ndarray:
    d_m = np.asarray(diameter_nm, dtype=float) * 1e-9
    volume = np.pi * np.maximum(d_m, 0.0) ** 3 / 6.0
    barrier = (10.0 ** float(log10_keff)) * volume / (_K_BOLTZMANN * max(float(temperature_k), 1e-9))
    return -float(log10_tau0) - barrier / np.log(10.0)


def neel_size_relaxation_absorption(
    v: np.ndarray,
    *,
    delta: float,
    quad: float,
    bhf: float,
    gamma: float,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    temperature_k: float = 300.0,
    log10_keff: float = 4.0,
    mean_d_nm: float = 8.0,
    sigma_lognormal: float = 0.25,
    log10_tau0: float = -9.0,
    n_bins: int = 20,
) -> np.ndarray:
    diam, weights = lognormal_diameter_distribution(mean_d_nm, sigma_lognormal, n_bins)
    lognus = neel_log10_nu(diam, temperature_k, log10_keff, log10_tau0)
    total = np.zeros_like(np.asarray(v, dtype=float), dtype=float)
    for w, lognu in zip(weights, lognus):
        total += float(w) * blume_tjon_two_state_absorption(
            v, delta=delta, quad=quad, bhf=bhf, gamma=gamma,
            gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel,
            int1=int1, int2_rel=int2_rel, int3_rel=int3_rel,
            log10_nu=float(np.clip(lognu, -50.0, 50.0)),
        )
    return total


def parameter_grid(pmin: float = 0.0, pmax: float = 50.0, nbins: int = 50) -> np.ndarray:
    """Centros de bins para una distribución 1D genérica."""
    nbins = int(nbins)
    if nbins < 3:
        raise ValueError("nbins debe ser >= 3")
    if not pmax > pmin:
        raise ValueError("el máximo debe ser mayor que el mínimo")
    edges = np.linspace(float(pmin), float(pmax), nbins + 1)
    return 0.5 * (edges[:-1] + edges[1:])


def bhf_grid(bmin: float = 0.0, bmax: float = 50.0, nbins: int = 50) -> np.ndarray:
    """Centros de bins de BHF en teslas."""
    return parameter_grid(bmin, bmax, nbins)


def build_bhf_kernel(
    v: np.ndarray,
    bhf_centers: np.ndarray,
    *,
    delta: float = 0.0,
    quad: float = 0.0,
    gamma: float = 0.18,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
) -> np.ndarray:
    """Matriz K[i,j] = absorcion de un sextete unitario con BHF_j."""
    v = np.asarray(v, dtype=float)
    bhf_centers = np.asarray(bhf_centers, dtype=float)
    cols = [
        sextet_absorption(
            v,
            delta=delta,
            quad=quad,
            bhf=float(bhf),
            gamma=gamma,
            gamma2_rel=gamma2_rel,
            gamma3_rel=gamma3_rel,
            int1=int1,
            int2_rel=int2_rel,
            int3_rel=int3_rel,
        )
        for bhf in bhf_centers
    ]
    return np.column_stack(cols)


def build_bhf_quad_distribution_kernel(
    v: np.ndarray,
    bhf_centers: np.ndarray,
    quad_centers: np.ndarray,
    *,
    variable_x: str = "bhf",
    variable_y: str = "quad",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
) -> np.ndarray:
    """Kernel para una distribución 2D de dos parámetros hiperfinos.

    Por compatibilidad histórica los ejes se llaman ``bhf_centers`` y
    ``quad_centers``. Pueden representar otras variables con ``variable_x`` /
    ``variable_y``: ``bhf``, ``quad`` o ``delta`` (IS). Las columnas se ordenan
    como ``weights.reshape(nx, ny)``.
    """
    v = np.asarray(v, dtype=float)
    x_arr = np.asarray(bhf_centers, dtype=float).reshape(-1)
    y_arr = np.asarray(quad_centers, dtype=float).reshape(-1)
    aliases = {"is": "delta", "isomer": "delta", "isomer_shift": "delta",
               "deq": "quad", "deltaeq": "quad", "qs": "quad",
               "b": "bhf", "field": "bhf"}
    vx = aliases.get(variable_x.lower(), variable_x.lower())
    vy = aliases.get(variable_y.lower(), variable_y.lower())
    if vx == vy:
        raise ValueError("Los dos ejes 2D deben ser variables distintas")
    if vx not in {"bhf", "quad", "delta"} or vy not in {"bhf", "quad", "delta"}:
        raise ValueError("Variables 2D válidas: 'bhf', 'quad' o 'delta'")
    cols: list[np.ndarray] = []
    for x in x_arr:
        for y in y_arr:
            vals = {"delta": float(delta), "quad": float(quad), "bhf": float(bhf)}
            vals[vx] = float(x)
            vals[vy] = float(y)
            cols.append(sextet_absorption(
                v, delta=vals["delta"], quad=vals["quad"], bhf=vals["bhf"], gamma=gamma,
                gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel,
                int1=int1, int2_rel=int2_rel, int3_rel=int3_rel,
            ))
    return np.column_stack(cols) if cols else np.empty((v.size, 0), dtype=float)


def second_difference_matrix_2d(n_bhf: int, n_quad: int) -> tuple[np.ndarray, np.ndarray]:
    """Operadores de curvatura para una malla 2D aplanada en orden C."""
    n_bhf = int(n_bhf)
    n_quad = int(n_quad)
    if n_bhf < 3 or n_quad < 3:
        raise ValueError("n_bhf y n_quad deben ser >= 3 para regularización 2D")
    d_b = second_difference_matrix(n_bhf)
    d_q = second_difference_matrix(n_quad)
    return np.kron(d_b, np.eye(n_quad)), np.kron(np.eye(n_bhf), d_q)


def normalize_probability_2d(weights: np.ndarray, bhf_centers: np.ndarray, quad_centers: np.ndarray) -> np.ndarray:
    """Normaliza P(BHF, ΔEQ) para que su integral bidimensional sea 1."""
    w = np.maximum(np.asarray(weights, dtype=float), 0.0)
    b = np.asarray(bhf_centers, dtype=float)
    q = np.asarray(quad_centers, dtype=float)
    if w.size == 0:
        return w.copy()
    try:
        area_q = np.trapezoid(w, q, axis=1) if q.size > 1 else w[:, 0]
        area = float(np.trapezoid(area_q, b)) if b.size > 1 else float(area_q[0])
    except Exception:
        area = float(np.sum(w))
    if area <= 0 or not np.isfinite(area):
        return np.zeros_like(w)
    return w / area


def bhf_quad_distribution_diagnostics(
    probability: np.ndarray,
    bhf_centers: np.ndarray,
    quad_centers: np.ndarray,
) -> dict[str, float | np.ndarray]:
    """Marginales, medias, sigmas y correlación de una P(BHF, ΔEQ)."""
    p = np.maximum(np.asarray(probability, dtype=float), 0.0)
    b = np.asarray(bhf_centers, dtype=float)
    q = np.asarray(quad_centers, dtype=float)
    if p.shape != (b.size, q.size) or p.size == 0:
        z_b = np.zeros_like(b, dtype=float)
        z_q = np.zeros_like(q, dtype=float)
        return {"marginal_bhf": z_b, "marginal_quad": z_q,
                "mean_bhf": np.nan, "mean_quad": np.nan,
                "sigma_bhf": np.nan, "sigma_quad": np.nan,
                "corr_bhf_quad": np.nan}
    marg_b = np.trapezoid(p, q, axis=1) if q.size > 1 else p[:, 0]
    marg_q = np.trapezoid(p, b, axis=0) if b.size > 1 else p[0, :]
    area_b = float(np.trapezoid(marg_b, b)) if b.size > 1 else float(np.sum(marg_b))
    area_q = float(np.trapezoid(marg_q, q)) if q.size > 1 else float(np.sum(marg_q))
    if area_b > 0 and np.isfinite(area_b):
        marg_b = marg_b / area_b
    if area_q > 0 and np.isfinite(area_q):
        marg_q = marg_q / area_q

    db = np.gradient(b) if b.size > 1 else np.ones_like(b)
    dq = np.gradient(q) if q.size > 1 else np.ones_like(q)
    mass = p * db[:, None] * dq[None, :]
    s = float(np.sum(mass))
    if s <= 0 or not np.isfinite(s):
        return {"marginal_bhf": marg_b, "marginal_quad": marg_q,
                "mean_bhf": np.nan, "mean_quad": np.nan,
                "sigma_bhf": np.nan, "sigma_quad": np.nan,
                "corr_bhf_quad": np.nan}
    mass = mass / s
    bb = b[:, None]
    qq = q[None, :]
    mean_b = float(np.sum(mass * bb))
    mean_q = float(np.sum(mass * qq))
    var_b = float(np.sum(mass * (bb - mean_b) ** 2))
    var_q = float(np.sum(mass * (qq - mean_q) ** 2))
    sig_b = float(np.sqrt(max(var_b, 0.0)))
    sig_q = float(np.sqrt(max(var_q, 0.0)))
    cov = float(np.sum(mass * (bb - mean_b) * (qq - mean_q)))
    corr = cov / (sig_b * sig_q) if sig_b > 0 and sig_q > 0 else float("nan")
    return {"marginal_bhf": marg_b, "marginal_quad": marg_q,
            "mean_bhf": mean_b, "mean_quad": mean_q,
            "sigma_bhf": sig_b, "sigma_quad": sig_q,
            "corr_bhf_quad": float(corr)}


def fit_bhf_quad_distribution(
    v: np.ndarray,
    y: np.ndarray,
    *,
    variable_x: str = "bhf",
    variable_y: str = "quad",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    bmin: float = 0.0,
    bmax: float = 50.0,
    nbins_bhf: int = 30,
    qmin: float = -1.0,
    qmax: float = 1.0,
    nbins_quad: int = 21,
    alpha_bhf: float = 1e-2,
    alpha_quad: float | None = None,
    fit_baseline: bool = True,
    fit_slope: bool = True,
    baseline: float | None = None,
    slope: float | None = None,
    baseline_bounds: tuple[float, float] = (0.0, np.inf),
    slope_bounds: tuple[float, float] = (-np.inf, np.inf),
    sharp_components: list[dict[str, float]] | None = None,
    sigma: np.ndarray | None = None,
    rescale_columns: bool = True,
) -> BhfQuadDistribution2DFit:
    """Ajusta una distribución regularizada bidimensional P(BHF, ΔEQ).

    Es un backend inicial avanzado, deliberadamente sin GUI. El problema es
    lineal en los pesos P_ij y usa restricciones P_ij >= 0 más penalización de
    curvatura en las dos direcciones::

        ||W(y - X z)||² + α_B ||D²_B P||² + α_Q ||D²_Q P||²

    Advertencia: incluso con residuo excelente, la solución 2D puede no ser
    única ni tener sentido físico si la malla es demasiado fina o α demasiado
    pequeño.
    """
    v = _finite_1d("v", v)
    y = _finite_1d("y", y)
    if v.size != y.size:
        raise ValueError("v e y deben tener la misma longitud")
    if alpha_quad is None:
        alpha_quad = alpha_bhf
    if alpha_bhf < 0 or alpha_quad < 0 or not np.isfinite(alpha_bhf) or not np.isfinite(alpha_quad):
        raise ValueError("alpha_bhf y alpha_quad deben ser finitos y >= 0")
    sigma_arr = None
    if sigma is not None:
        sigma_arr = _finite_1d("sigma", sigma)
        if sigma_arr.size != y.size:
            raise ValueError("sigma debe tener la misma longitud que y")
        sigma_arr = np.maximum(sigma_arr, 1e-12)
    if baseline is None:
        baseline = float(np.percentile(y, 90))
    if slope is None:
        slope = 0.0

    bhf_centers = parameter_grid(bmin, bmax, nbins_bhf)
    quad_centers = parameter_grid(qmin, qmax, nbins_quad)
    n_b = bhf_centers.size
    n_q = quad_centers.size
    K = build_bhf_quad_distribution_kernel(
        v, bhf_centers, quad_centers,
        variable_x=variable_x, variable_y=variable_y,
        delta=delta, quad=quad, bhf=bhf, gamma=gamma,
        gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel,
        int1=int1, int2_rel=int2_rel, int3_rel=int3_rel,
    )
    L_b, L_q = second_difference_matrix_2d(n_b, n_q)
    K_sharp, sharp_bhf_centers, fixed_sharp_abs, sharp_fixed_mask, fixed_sharp_weights = build_sharp_kernel_for_fit(
        v,
        sharp_components,
        default_delta=delta,
        default_quad=0.0,
        default_gamma=gamma,
        default_gamma2_rel=gamma2_rel,
        default_gamma3_rel=gamma3_rel,
        default_int1=int1,
        default_int2_rel=int2_rel,
        default_int3_rel=int3_rel,
    )

    y_work = y.astype(float).copy() + fixed_sharp_abs
    columns: list[np.ndarray] = []
    lower: list[float] = []
    upper: list[float] = []
    labels: list[str] = []
    if fit_baseline:
        columns.append(np.ones_like(v)); lower.append(float(baseline_bounds[0])); upper.append(float(baseline_bounds[1])); labels.append("baseline")
    else:
        y_work -= float(baseline)
    if fit_slope:
        columns.append(v); lower.append(float(slope_bounds[0])); upper.append(float(slope_bounds[1])); labels.append("slope")
    else:
        y_work -= float(slope) * v

    dist_start = len(labels)
    for j in range(K.shape[1]):
        columns.append(-K[:, j]); lower.append(0.0); upper.append(np.inf); labels.append(f"P2D{j}")
    dist_end = len(labels)
    sharp_start = len(labels)
    if K_sharp is not None:
        for j in range(K_sharp.shape[1]):
            columns.append(-K_sharp[:, j]); lower.append(0.0); upper.append(np.inf); labels.append(f"sharp{j}")
    sharp_end = len(labels)
    X = np.column_stack(columns)

    scale = np.ones(X.shape[1], dtype=float)
    if rescale_columns and dist_end > dist_start:
        Kw = K / sigma_arr[:, None] if sigma_arr is not None else K
        col_norms = np.linalg.norm(Kw, axis=0)
        col_norms = np.where(np.isfinite(col_norms) & (col_norms > 1e-12), col_norms, 1.0)
        scale[dist_start:dist_end] = col_norms
    Xs = X / scale[None, :]
    L_b_scaled = L_b / scale[None, dist_start:dist_end]
    L_q_scaled = L_q / scale[None, dist_start:dist_end]
    if sigma_arr is not None:
        X_fit = Xs / sigma_arr[:, None]
        y_fit = y_work / sigma_arr
    else:
        X_fit = Xs
        y_fit = y_work

    reg_b = np.zeros((L_b.shape[0], X.shape[1]), dtype=float)
    reg_q = np.zeros((L_q.shape[0], X.shape[1]), dtype=float)
    reg_b[:, dist_start:dist_end] = np.sqrt(float(alpha_bhf)) * L_b_scaled
    reg_q[:, dist_start:dist_end] = np.sqrt(float(alpha_quad)) * L_q_scaled
    X_aug = np.vstack([X_fit, reg_b, reg_q])
    y_aug = np.concatenate([y_fit, np.zeros(reg_b.shape[0] + reg_q.shape[0], dtype=float)])

    lower_arr = np.array(lower)
    upper_arr = np.array(upper)
    result = lsq_linear(X_aug, y_aug, bounds=(lower_arr, upper_arr), lsmr_tol="auto", max_iter=3000)
    params = result.x / scale
    baseline_fit = float(params[labels.index("baseline")]) if fit_baseline else float(baseline)
    slope_fit = float(params[labels.index("slope")]) if fit_slope else float(slope)
    weights_flat = np.maximum(params[dist_start:dist_end], 0.0)
    weights = weights_flat.reshape(n_b, n_q)
    sharp_weights_free = np.maximum(params[sharp_start:sharp_end], 0.0) if sharp_end > sharp_start else None
    sharp_weights = merge_sharp_weights(sharp_weights_free, sharp_fixed_mask, fixed_sharp_weights)
    fitted = baseline_fit + slope_fit * v - K @ weights_flat - fixed_sharp_abs
    if K_sharp is not None and sharp_weights_free is not None:
        fitted = fitted - K_sharp @ sharp_weights_free
    residuals = y - fitted
    rms = float(np.sqrt(np.mean(residuals ** 2)))
    try:
        L_combined = np.vstack([np.sqrt(float(alpha_bhf)) * L_b,
                                np.sqrt(float(alpha_quad)) * L_q])
        eff_dof = tikhonov_effective_dof(X, L_combined, 1.0, dist_start, dist_end, sigma=sigma_arr)
    except Exception:
        eff_dof = None
    probability = normalize_probability_2d(weights, bhf_centers, quad_centers)
    diag = bhf_quad_distribution_diagnostics(probability, bhf_centers, quad_centers)
    n_weights = int(weights.size)
    dof_warning = None
    if eff_dof is not None and eff_dof > 0.7 * max(1, y.size):
        dof_warning = "Grados de libertad efectivos altos frente al número de canales: riesgo de sobreajuste."
    if n_weights > y.size:
        dof_warning = (dof_warning + " " if dof_warning else "") + "La malla 2D tiene más pesos que canales: la solución no es única sin regularización fuerte."
    return BhfQuadDistribution2DFit(
        bhf_centers=bhf_centers,
        quad_centers=quad_centers,
        weights=weights,
        probability=probability,
        fitted_curve=fitted,
        residuals=residuals,
        baseline=baseline_fit,
        slope=slope_fit,
        alpha_bhf=float(alpha_bhf),
        alpha_quad=float(alpha_quad),
        rms=rms,
        success=bool(result.success),
        message=str(result.message),
        x_variable=str(variable_x),
        y_variable=str(variable_y),
        effective_dof=eff_dof,
        marginal_bhf=np.asarray(diag["marginal_bhf"], dtype=float),
        marginal_quad=np.asarray(diag["marginal_quad"], dtype=float),
        mean_bhf=float(diag["mean_bhf"]),
        mean_quad=float(diag["mean_quad"]),
        sigma_bhf=float(diag["sigma_bhf"]),
        sigma_quad=float(diag["sigma_quad"]),
        corr_bhf_quad=float(diag["corr_bhf_quad"]),
        dof_warning=dof_warning,
        sharp_bhf_centers=sharp_bhf_centers,
        sharp_weights=sharp_weights,
    )


def build_hyperfine_distribution_kernel(
    v: np.ndarray,
    centers: np.ndarray,
    *,
    variable: str = "bhf",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
) -> np.ndarray:
    """Kernel de distribución 1D en BHF o ΔEQ.

    variable="bhf": centers son campos BHF y quad queda fijo.
    variable="quad": centers son ΔEQ y BHF queda fijo.
    """
    variable = variable.lower()
    if variable in {"bhf", "b", "field"}:
        return build_bhf_kernel(v, centers, delta=delta, quad=quad, gamma=gamma, gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel, int1=int1, int2_rel=int2_rel, int3_rel=int3_rel)
    if variable in {"quad", "deq", "deltaeq", "qs", "Δeq"}:
        return np.column_stack([
            sextet_absorption(v, delta=delta, quad=float(q), bhf=bhf, gamma=gamma, gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel, int1=int1, int2_rel=int2_rel, int3_rel=int3_rel)
            for q in np.asarray(centers, dtype=float)
        ])
    if variable in {"delta", "is", "isomer", "isomer_shift"}:
        return np.column_stack([
            sextet_absorption(v, delta=float(d), quad=quad, bhf=bhf, gamma=gamma, gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel, int1=int1, int2_rel=int2_rel, int3_rel=int3_rel)
            for d in np.asarray(centers, dtype=float)
        ])
    raise ValueError("variable de distribución no reconocida: usa 'bhf', 'quad' o 'delta'")


def second_difference_matrix(n: int) -> np.ndarray:
    """Operador L de segundas diferencias, dimension (n-2) x n."""
    n = int(n)
    if n < 3:
        raise ValueError("n debe ser >= 3")
    L = np.zeros((n - 2, n), dtype=float)
    rows = np.arange(n - 2)
    L[rows, rows] = 1.0
    L[rows, rows + 1] = -2.0
    L[rows, rows + 2] = 1.0
    return L


def first_difference_matrix(n: int) -> np.ndarray:
    """Operador D de primeras diferencias, dimensión (n-1) x n."""
    n = int(n)
    if n < 2:
        raise ValueError("n debe ser >= 2")
    D = np.zeros((n - 1, n), dtype=float)
    rows = np.arange(n - 1)
    D[rows, rows] = -1.0
    D[rows, rows + 1] = 1.0
    return D


def tikhonov_effective_dof(
    X: np.ndarray,
    L_dist: np.ndarray,
    alpha: float,
    dist_start: int,
    dist_end: int,
    sigma: np.ndarray | None = None,
) -> float:
    """Grados de libertad efectivos del problema Tikhonov bajo restricciones lineales.

    Devuelve  tr A(α)  con  A(α) = X (XᵀWX + α LᵀL)⁻¹ XᵀW,  W = diag(1/σ²).
    El penalizador LᵀL actúa sólo sobre las columnas [dist_start:dist_end].

    La cota de no-negatividad sobre P se ignora aquí: la traza es una buena
    estimación incluso con bordes activos (sólo sobreestima ligeramente).
    """
    X = np.asarray(X, dtype=float)
    L_dist = np.asarray(L_dist, dtype=float)
    if X.size == 0:
        return 0.0
    if sigma is not None:
        sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-12)
        Xw = X / sigma[:, None]
    else:
        Xw = X
    XtWX = Xw.T @ Xw
    LtL = L_dist.T @ L_dist
    H = XtWX.copy()
    H[dist_start:dist_end, dist_start:dist_end] += float(alpha) * LtL
    try:
        return float(np.trace(np.linalg.solve(H, XtWX)))
    except np.linalg.LinAlgError:
        return float(X.shape[1])


def distribution_weight_sigma(
    X: np.ndarray,
    L_dist: np.ndarray,
    alpha: float,
    dist_start: int,
    dist_end: int,
    residuals: np.ndarray,
    eff_dof: float,
    sigma: np.ndarray | None = None,
) -> np.ndarray:
    """Incertidumbre 1σ de los pesos P por covarianza linealizada regularizada.

    Para el estimador Tikhonov  ẑ = H⁻¹ XᵀW y  con  H = XᵀWX + α LᵀL,  W=diag(1/σ²),
    la covarianza es  Cov(ẑ) = H⁻¹ (XᵀWX) H⁻¹.  Se escala por el χ²_ν efectivo
    (igual convención que el ajuste discreto) para reflejar mala especificación
    del modelo. Devuelve σ_P por bin (raíz de la diagonal de la parte de la
    distribución). La no-negatividad no se impone aquí: en bins clavados a 0 la
    σ es una cota superior (la banda se recorta a P≥0 al pintar).
    """
    n_data = X.shape[0]
    if sigma is not None:
        sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-12)
        W = 1.0 / sigma ** 2
        chi2 = float(np.sum((residuals / sigma) ** 2))
    else:
        W = np.ones(n_data)
        chi2 = float(np.sum(residuals ** 2))
    XtWX = X.T @ (W[:, None] * X)
    H = XtWX.copy()
    H[dist_start:dist_end, dist_start:dist_end] += float(alpha) * (L_dist.T @ L_dist)
    try:
        H_inv = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        H_inv = np.linalg.pinv(H)
    cov = H_inv @ XtWX @ H_inv
    var = np.clip(np.diag(cov)[dist_start:dist_end], 0.0, None)
    dof = max(float(n_data) - float(eff_dof), 1.0)
    var = var * (chi2 / dof)
    return np.sqrt(var)


def normalize_probability(weights: np.ndarray, bhf_centers: np.ndarray) -> np.ndarray:
    """Normaliza P para que su integral sobre BHF sea 1 si hay area positiva."""
    weights = np.maximum(np.asarray(weights, dtype=float), 0.0)
    bhf_centers = np.asarray(bhf_centers, dtype=float)
    if weights.size == 0:
        return weights.copy()
    area = float(np.trapezoid(weights, bhf_centers)) if weights.size > 1 else float(weights[0])
    if area <= 0 or not np.isfinite(area):
        return np.zeros_like(weights)
    return weights / area


def _finite_1d(name: str, values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if arr.size == 0 or not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} debe ser un array 1D finito y no vacio")
    return arr


def _component_value(component: dict[str, float], name: str, default: float) -> float:
    value = component.get(name, default)
    if value is None or not np.isfinite(value):
        raise ValueError(f"Componente nítido: {name} no es finito")
    return float(value)


def build_sharp_kernel(
    v: np.ndarray,
    components: list[dict[str, float]] | None,
    *,
    default_delta: float = 0.0,
    default_quad: float = 0.0,
    default_gamma: float = 0.18,
    default_gamma2_rel: float = 1.0,
    default_gamma3_rel: float = 1.0,
    default_int1: float = 1.0,
    default_int2_rel: float = 1.0,
    default_int3_rel: float = 1.0,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Kernel para componentes nítidos opcionales añadidos a la distribución.

    Cada componente puede tener ``kind`` = ``Sextete``, ``Doblete`` o
    ``Singlete``. Para sextetes se devuelve su BHF; para singletes/dobletes se
    devuelve NaN en ``sharp_bhf_centers`` porque no tienen campo hiperfino.

    La amplitud/profundidad no se incluye en el kernel: cada columna es el
    perfil de absorción por profundidad unitaria. El ajuste decide después si
    esa amplitud es libre o fija, según ``depth_fixed`` en el componente.
    """
    if not components:
        return None, None
    cols: list[np.ndarray] = []
    bhf_values: list[float] = []
    for comp in components:
        kind = str(comp.get("kind", "Sextete"))
        delta = _component_value(comp, "delta", default_delta)
        quad = _component_value(comp, "quad", default_quad)
        gamma = _component_value(comp, "gamma", default_gamma)
        gamma2_rel = _component_value(comp, "gamma2_rel", default_gamma2_rel)
        int1 = _component_value(comp, "int1", default_int1)
        int2_rel = _component_value(comp, "int2_rel", default_int2_rel)
        if kind == "Singlete":
            bhf_values.append(float("nan"))
            cols.append(singlet_absorption(v, delta=delta, gamma=gamma, int1=int1))
        elif kind == "Doblete":
            bhf_values.append(float("nan"))
            cols.append(doublet_absorption(v, delta=delta, quad=quad, gamma=gamma, gamma2_rel=gamma2_rel, int1=int1, int2_rel=int2_rel))
        elif kind == "Relajacion":
            if "bhf" not in comp:
                raise ValueError("Cada componente de relajación debe incluir 'bhf'")
            bhf = _component_value(comp, "bhf", np.nan)
            bhf_values.append(bhf)
            cols.append(
                relaxation_empirical_absorption(
                    v,
                    delta=delta,
                    quad=quad,
                    bhf=bhf,
                    gamma=gamma,
                    gamma2_rel=gamma2_rel,
                    gamma3_rel=_component_value(comp, "gamma3_rel", default_gamma3_rel),
                    int1=int1,
                    int2_rel=int2_rel,
                    int3_rel=_component_value(comp, "int3_rel", default_int3_rel),
                    blocked_fraction=_component_value(comp, "relax_fraction", 1.0),
                    log10_nu=_component_value(comp, "relax_log_nu", 5.0),
                )
            )
        elif kind == "BlumeTjon":
            if "bhf" not in comp:
                raise ValueError("Cada componente Blume-Tjon debe incluir 'bhf'")
            bhf = _component_value(comp, "bhf", np.nan)
            bhf_values.append(bhf)
            cols.append(
                blume_tjon_two_state_absorption(
                    v,
                    delta=delta,
                    quad=quad,
                    bhf=bhf,
                    gamma=gamma,
                    gamma2_rel=gamma2_rel,
                    gamma3_rel=_component_value(comp, "gamma3_rel", default_gamma3_rel),
                    int1=int1,
                    int2_rel=int2_rel,
                    int3_rel=_component_value(comp, "int3_rel", default_int3_rel),
                    log10_nu=_component_value(comp, "relax_log_nu", 5.0),
                )
            )
        elif kind == "NeelSize":
            if "bhf" not in comp:
                raise ValueError("Cada componente Néel debe incluir 'bhf'")
            bhf = _component_value(comp, "bhf", np.nan)
            bhf_values.append(bhf)
            cols.append(
                neel_size_relaxation_absorption(
                    v,
                    delta=delta,
                    quad=quad,
                    bhf=bhf,
                    gamma=gamma,
                    gamma2_rel=gamma2_rel,
                    gamma3_rel=_component_value(comp, "gamma3_rel", default_gamma3_rel),
                    int1=int1,
                    int2_rel=int2_rel,
                    int3_rel=_component_value(comp, "int3_rel", default_int3_rel),
                    temperature_k=_component_value(comp, "neel_temp_k", 300.0),
                    log10_keff=_component_value(comp, "neel_log10_keff", 4.0),
                    mean_d_nm=_component_value(comp, "neel_mean_d_nm", 8.0),
                    sigma_lognormal=_component_value(comp, "neel_sigma", 0.25),
                    log10_tau0=_component_value(comp, "neel_log10_tau0", -9.0),
                    n_bins=int(round(_component_value(comp, "neel_bins", 20.0))),
                )
            )
        else:
            if "bhf" not in comp:
                raise ValueError("Cada sextete nítido debe incluir 'bhf'")
            bhf = _component_value(comp, "bhf", np.nan)
            bhf_values.append(bhf)
            cols.append(
                sextet_absorption(
                    v,
                    delta=delta,
                    quad=quad,
                    bhf=bhf,
                    gamma=gamma,
                    gamma2_rel=gamma2_rel,
                    gamma3_rel=_component_value(comp, "gamma3_rel", default_gamma3_rel),
                    int1=int1,
                    int2_rel=int2_rel,
                    int3_rel=_component_value(comp, "int3_rel", default_int3_rel),
                )
            )
    return np.column_stack(cols), np.array(bhf_values, dtype=float)


def _component_depth(component: dict[str, float], default: float = 0.0) -> float:
    """Profundidad/amplitud de un nítido cuando se solicita que sea fija."""
    for name in ("depth", "weight", "amplitude", "amp"):
        if name in component:
            return max(0.0, _component_value(component, name, default))
    return max(0.0, float(default))


def _component_depth_is_fixed(component: dict[str, float]) -> bool:
    """Devuelve si la amplitud del nítido debe tratarse como fija."""
    return bool(
        component.get("depth_fixed", component.get("fixed_depth", component.get("amplitude_fixed", False)))
    )


def build_sharp_kernel_for_fit(
    v: np.ndarray,
    components: list[dict[str, float]] | None,
    *,
    default_delta: float = 0.0,
    default_quad: float = 0.0,
    default_gamma: float = 0.18,
    default_gamma2_rel: float = 1.0,
    default_gamma3_rel: float = 1.0,
    default_int1: float = 1.0,
    default_int2_rel: float = 1.0,
    default_int3_rel: float = 1.0,
) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray, np.ndarray, np.ndarray]:
    """Kernel de nítidos separando amplitudes libres y fijas.

    Returns
    -------
    K_free
        Columnas de los nítidos cuya profundidad se debe ajustar. ``None`` si
        no hay ninguna.
    sharp_bhf_centers
        Centros BHF/NaN de todos los nítidos, en el orden original.
    fixed_absorption
        Absorción positiva total de los nítidos con profundidad fija:
        ``K_fixed @ depth_fixed``. Debe restarse del modelo de transmisión.
    fixed_mask
        Booleano por nítido; True si su profundidad era fija.
    fixed_weights
        Pesos/profundidades en el orden original; NaN en los nítidos libres.
    """
    K_all, sharp_bhf_centers = build_sharp_kernel(
        v,
        components,
        default_delta=default_delta,
        default_quad=default_quad,
        default_gamma=default_gamma,
        default_gamma2_rel=default_gamma2_rel,
        default_gamma3_rel=default_gamma3_rel,
        default_int1=default_int1,
        default_int2_rel=default_int2_rel,
        default_int3_rel=default_int3_rel,
    )
    if K_all is None or not components:
        return None, None, np.zeros_like(v, dtype=float), np.zeros(0, dtype=bool), np.zeros(0, dtype=float)

    fixed_mask = np.array([_component_depth_is_fixed(c) for c in components], dtype=bool)
    fixed_weights = np.full(len(components), np.nan, dtype=float)
    fixed_absorption = np.zeros_like(v, dtype=float)
    if np.any(fixed_mask):
        vals = np.array([_component_depth(c) if fixed else 0.0 for c, fixed in zip(components, fixed_mask)], dtype=float)
        fixed_weights[fixed_mask] = vals[fixed_mask]
        fixed_absorption = K_all[:, fixed_mask] @ vals[fixed_mask]
    K_free = K_all[:, ~fixed_mask] if np.any(~fixed_mask) else None
    return K_free, sharp_bhf_centers, fixed_absorption, fixed_mask, fixed_weights


def merge_sharp_weights(
    free_weights: np.ndarray | None,
    fixed_mask: np.ndarray,
    fixed_weights: np.ndarray,
) -> np.ndarray | None:
    """Combina pesos libres ajustados y pesos fijos en el orden original."""
    if fixed_mask.size == 0:
        return None
    out = np.zeros(fixed_mask.size, dtype=float)
    out[fixed_mask] = np.maximum(fixed_weights[fixed_mask], 0.0)
    if np.any(~fixed_mask):
        if free_weights is None:
            raise ValueError("Faltan pesos libres de nítidos")
        out[~fixed_mask] = np.maximum(np.asarray(free_weights, dtype=float), 0.0)
    return out


def fit_hyperfine_distribution(
    v: np.ndarray,
    y: np.ndarray,
    *,
    variable: str = "bhf",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    pmin: float = 0.0,
    pmax: float = 50.0,
    nbins: int = 50,
    alpha: float = 1e-2,
    fit_baseline: bool = True,
    fit_slope: bool = True,
    baseline: float | None = None,
    slope: float | None = None,
    baseline_bounds: tuple[float, float] = (0.0, np.inf),
    slope_bounds: tuple[float, float] = (-np.inf, np.inf),
    sharp_components: list[dict[str, float]] | None = None,
    sigma: np.ndarray | None = None,
    rescale_columns: bool = True,
    reg_mode: str = "tikhonov",
    tv_iters: int = 8,
) -> BhfDistributionFit:
    """Ajusta una distribución Hesse-Rübartsch de BHF o ΔEQ.

    variable='bhf': centers son campos hiperfinos.
    variable='quad': centers son valores de ΔEQ con BHF fijo en ``bhf``.
    """
    v = _finite_1d("v", v)
    y = _finite_1d("y", y)
    if v.size != y.size:
        raise ValueError("v e y deben tener la misma longitud")
    sigma_arr = None
    if sigma is not None:
        sigma_arr = _finite_1d("sigma", sigma)
        if sigma_arr.size != y.size:
            raise ValueError("sigma debe tener la misma longitud que y")
        sigma_arr = np.maximum(sigma_arr, 1e-12)
    if alpha < 0 or not np.isfinite(alpha):
        raise ValueError("alpha debe ser finito y >= 0")

    if baseline is None:
        baseline = float(np.percentile(y, 90))
    if slope is None:
        slope = 0.0

    centers = parameter_grid(pmin, pmax, nbins)
    K = build_hyperfine_distribution_kernel(
        v,
        centers,
        variable=variable,
        delta=delta,
        quad=quad,
        bhf=bhf,
        gamma=gamma,
        gamma2_rel=gamma2_rel,
        gamma3_rel=gamma3_rel,
        int1=int1,
        int2_rel=int2_rel,
        int3_rel=int3_rel,
    )
    K_sharp, sharp_bhf_centers, fixed_sharp_abs, sharp_fixed_mask, fixed_sharp_weights = build_sharp_kernel_for_fit(
        v,
        sharp_components,
        default_delta=delta,
        default_quad=quad,
        default_gamma=gamma,
        default_gamma2_rel=gamma2_rel,
        default_gamma3_rel=gamma3_rel,
        default_int1=int1,
        default_int2_rel=int2_rel,
        default_int3_rel=int3_rel,
    )
    # Penalizador: Tikhonov L2 (segunda diferencia, suave) o Variación Total
    # (primera diferencia, L1 → picos afilados con bordes). Mejora 5.
    use_tv = str(reg_mode).lower() in ("tv", "total_variation", "variacion_total")
    if use_tv:
        L = first_difference_matrix(centers.size)
    else:
        L = second_difference_matrix(centers.size)

    # Los nítidos con profundidad fija aportan absorción conocida al modelo:
    # y = fondo - K_dist·P - K_sharp_free·q - fixed_sharp_abs.
    # Se pasa al solve como y + fixed_sharp_abs para que sólo queden libres P y q.
    y_work = y.astype(float).copy() + fixed_sharp_abs
    columns: list[np.ndarray] = []
    lower: list[float] = []
    upper: list[float] = []
    labels: list[str] = []

    if fit_baseline:
        columns.append(np.ones_like(v))
        lower.append(float(baseline_bounds[0]))
        upper.append(float(baseline_bounds[1]))
        labels.append("baseline")
    else:
        y_work -= float(baseline)

    if fit_slope:
        columns.append(v)
        lower.append(float(slope_bounds[0]))
        upper.append(float(slope_bounds[1]))
        labels.append("slope")
    else:
        y_work -= float(slope) * v

    # El modelo tiene signo de absorcion: y = fondo - K @ P.
    dist_start = len(labels)
    for j in range(centers.size):
        columns.append(-K[:, j])
        lower.append(0.0)
        upper.append(np.inf)
        labels.append(f"P{j}")
    dist_end = len(labels)

    sharp_start = len(labels)
    if K_sharp is not None:
        for j in range(K_sharp.shape[1]):
            columns.append(-K_sharp[:, j])
            lower.append(0.0)
            upper.append(np.inf)
            labels.append(f"sharp{j}")
    sharp_end = len(labels)

    X = np.column_stack(columns)

    # Mejora 13: preacondicionamiento por escala de columnas de la distribución.
    # Para BHF pequeño el sextete colapsa y las columnas de K se vuelven casi
    # colineales (||K_j|| muy dispares), lo que hace mal condicionado el sistema
    # acotado. Reescalando K_j → K_j/s_j y P_j → P_j·s_j el problema queda mejor
    # condicionado SIN cambiar la solución (reparametrización exacta). El
    # penalizador y los pesos se ajustan en consecuencia.
    scale = np.ones(X.shape[1], dtype=float)
    if rescale_columns and dist_end > dist_start:
        Kw = K / sigma_arr[:, None] if sigma_arr is not None else K
        col_norms = np.linalg.norm(Kw, axis=0)
        col_norms = np.where(np.isfinite(col_norms) & (col_norms > 1e-12), col_norms, 1.0)
        scale[dist_start:dist_end] = col_norms

    Xs = X / scale[None, :]
    L_scaled = L / scale[None, dist_start:dist_end]
    if sigma_arr is not None:
        X_fit = Xs / sigma_arr[:, None]
        y_fit = y_work / sigma_arr
    else:
        X_fit = Xs
        y_fit = y_work
    lower_arr = np.array(lower)
    upper_arr = np.array(upper)

    def _solve(L_pen_scaled: np.ndarray):
        reg = np.zeros((L_pen_scaled.shape[0], X.shape[1]), dtype=float)
        reg[:, dist_start:dist_end] = np.sqrt(float(alpha)) * L_pen_scaled
        X_aug = np.vstack([X_fit, reg])
        y_aug = np.concatenate([y_fit, np.zeros(L_pen_scaled.shape[0], dtype=float)])
        # Las cotas de p̃ = escala·P coinciden con las de P (0 e ∞ invariantes).
        res = lsq_linear(X_aug, y_aug, bounds=(lower_arr, upper_arr), lsmr_tol="auto", max_iter=2000)
        return res, res.x / scale  # deshace el escalado para recuperar P físico

    if use_tv:
        # IRLS para ‖α^{1/2} D P‖₁: en cada iteración se resuelve un Tikhonov
        # ponderado con pesos w_k = 1/√((D P)_k² + ε²). Converge a la solución
        # de variación total, que preserva bordes (picos afilados).
        L_eff = L_scaled.copy()
        result = None
        params = None
        for _ in range(max(1, int(tv_iters))):
            result, params = _solve(L_eff)
            p_phys = params[dist_start:dist_end]
            dp = L @ p_phys  # primera diferencia del P físico
            eps = max(1e-3 * float(np.max(np.abs(p_phys))) if p_phys.size else 1e-6, 1e-9)
            w = 1.0 / np.sqrt(dp ** 2 + eps ** 2)
            L_eff = (np.sqrt(w)[:, None]) * L_scaled
        # Operador efectivo (sin escala) para dof y covarianza: √w · D.
        L_stats = (np.sqrt(w)[:, None]) * L
    else:
        result, params = _solve(L_scaled)
        L_stats = L

    baseline_fit = float(params[labels.index("baseline")]) if fit_baseline else float(baseline)
    slope_fit = float(params[labels.index("slope")]) if fit_slope else float(slope)
    weights = np.maximum(params[dist_start:dist_end], 0.0)
    sharp_weights_free = np.maximum(params[sharp_start:sharp_end], 0.0) if sharp_end > sharp_start else None
    sharp_weights = merge_sharp_weights(sharp_weights_free, sharp_fixed_mask, fixed_sharp_weights)
    fitted = baseline_fit + slope_fit * v - K @ weights - fixed_sharp_abs
    if K_sharp is not None and sharp_weights_free is not None:
        fitted = fitted - K_sharp @ sharp_weights_free
    residuals = y - fitted
    rms = float(np.sqrt(np.mean(residuals**2)))

    try:
        eff_dof = tikhonov_effective_dof(
            X, L_stats, float(alpha), dist_start, dist_end, sigma=sigma_arr
        )
    except Exception:
        eff_dof = float(X.shape[1])

    try:
        weight_sigma = distribution_weight_sigma(
            X, L_stats, float(alpha), dist_start, dist_end, residuals, eff_dof, sigma=sigma_arr
        )
    except Exception:
        weight_sigma = None

    return BhfDistributionFit(
        bhf_centers=centers,
        weights=weights,
        probability=normalize_probability(weights, centers),
        fitted_curve=fitted,
        residuals=residuals,
        baseline=baseline_fit,
        slope=slope_fit,
        alpha=float(alpha),
        rms=rms,
        success=bool(result.success),
        message=str(result.message),
        sharp_bhf_centers=sharp_bhf_centers,
        sharp_weights=sharp_weights,
        effective_dof=eff_dof,
        weight_sigma=weight_sigma,
    )


def fit_gaussian_hyperfine_distribution(
    v: np.ndarray,
    y: np.ndarray,
    *,
    variable: str = "bhf",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    pmin: float = 0.0,
    pmax: float = 50.0,
    nbins: int = 80,
    baseline: float | None = None,
    slope: float | None = None,
    sharp_components: list[dict[str, float]] | None = None,
) -> BhfDistributionFit:
    """Ajuste paramétrico sencillo de una distribución gaussiana 1D.

    Ajusta baseline, slope, amplitud, centro y sigma. La gaussiana se discretiza
    en la misma malla que el histograma para poder dibujar P(parámetro).
    Opcionalmente suma componentes nítidos (sharp_components) con amplitud libre >= 0.
    """
    from scipy.optimize import least_squares
    v = _finite_1d("v", v); y = _finite_1d("y", y)
    centers = parameter_grid(pmin, pmax, nbins)
    K = build_hyperfine_distribution_kernel(v, centers, variable=variable, delta=delta, quad=quad, bhf=bhf, gamma=gamma)
    K_sharp, sharp_bhf_centers, fixed_sharp_abs, sharp_fixed_mask, fixed_sharp_weights = build_sharp_kernel_for_fit(
        v, sharp_components, default_delta=delta, default_quad=quad, default_gamma=gamma)
    n_sharp = K_sharp.shape[1] if K_sharp is not None else 0
    if baseline is None:
        baseline = float(np.percentile(y, 90))
    if slope is None:
        slope = 0.0
    amp0 = max(1e-6, float(np.percentile(y, 90) - np.min(y)))
    center0 = 0.5 * (float(pmin) + float(pmax))
    sigma0 = max((float(pmax) - float(pmin)) / 6.0, 1e-3)

    def gauss_weights(center: float, sigma: float) -> np.ndarray:
        sigma = max(float(sigma), 1e-6)
        w = np.exp(-0.5 * ((centers - center) / sigma) ** 2)
        area = np.trapezoid(w, centers) if w.size > 1 else w[0]
        return w / max(float(area), 1e-12)

    def residual(x: np.ndarray) -> np.ndarray:
        b0, sl, amp, cen, log_sig = x[:5]
        w = amp * gauss_weights(cen, np.exp(log_sig))
        r = b0 + sl * v - K @ w - fixed_sharp_abs - y
        if K_sharp is not None and n_sharp:
            sharp_amps = np.maximum(x[5:5 + n_sharp], 0.0)
            r = r - K_sharp @ sharp_amps
        return r

    lo = np.array([0.0, -np.inf, 0.0, float(pmin), np.log(1e-3)] + [0.0] * n_sharp)
    hi = np.array([np.inf, np.inf, np.inf, float(pmax), np.log(max(float(pmax) - float(pmin), 1e-3))] + [np.inf] * n_sharp)
    x0 = np.array([baseline, slope, amp0, center0, np.log(sigma0)] + [amp0 / max(n_sharp, 1)] * n_sharp)
    res = least_squares(residual, np.clip(x0, lo, hi), bounds=(lo, hi), max_nfev=2000)
    b0, sl, amp, cen, log_sig = res.x[:5]
    w = float(amp) * gauss_weights(float(cen), float(np.exp(log_sig)))
    sharp_weights_free = np.maximum(res.x[5:5 + n_sharp], 0.0) if n_sharp else None
    sharp_weights_arr = merge_sharp_weights(sharp_weights_free, sharp_fixed_mask, fixed_sharp_weights)
    fitted = float(b0) + float(sl) * v - K @ w - fixed_sharp_abs
    if K_sharp is not None and sharp_weights_free is not None:
        fitted = fitted - K_sharp @ sharp_weights_free
    residuals = y - fitted
    return BhfDistributionFit(
        bhf_centers=centers,
        weights=w,
        probability=normalize_probability(w, centers),
        fitted_curve=fitted,
        residuals=residuals,
        baseline=float(b0),
        slope=float(sl),
        alpha=0.0,
        rms=float(np.sqrt(np.mean(residuals**2))),
        success=bool(res.success),
        message=f"Gaussian {variable}: center={cen:.6g}, sigma={np.exp(log_sig):.6g}; {res.message}",
        sharp_bhf_centers=sharp_bhf_centers,
        sharp_weights=sharp_weights_arr,
        fitted_dist_center=float(cen),
        fitted_dist_sigma=float(np.exp(log_sig)),
    )


def fit_binomial_hyperfine_distribution(
    v: np.ndarray,
    y: np.ndarray,
    *,
    variable: str = "bhf",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    pmin: float = 0.0,
    pmax: float = 50.0,
    nbins: int = 30,
    baseline: float | None = None,
    slope: float | None = None,
    sharp_components: list[dict[str, float]] | None = None,
) -> BhfDistributionFit:
    """Ajuste paramétrico sencillo de una distribución binomial sobre la malla.

    Opcionalmente suma componentes nítidos (sharp_components) con amplitud libre >= 0.
    """
    from scipy.optimize import least_squares
    from scipy.special import gammaln
    v = _finite_1d("v", v); y = _finite_1d("y", y)
    centers = parameter_grid(pmin, pmax, nbins)
    K = build_hyperfine_distribution_kernel(v, centers, variable=variable, delta=delta, quad=quad, bhf=bhf, gamma=gamma)
    K_sharp, sharp_bhf_centers, fixed_sharp_abs, sharp_fixed_mask, fixed_sharp_weights = build_sharp_kernel_for_fit(
        v, sharp_components, default_delta=delta, default_quad=quad, default_gamma=gamma)
    n_sharp = K_sharp.shape[1] if K_sharp is not None else 0
    if baseline is None:
        baseline = float(np.percentile(y, 90))
    if slope is None:
        slope = 0.0
    amp0 = max(1e-6, float(np.percentile(y, 90) - np.min(y)))
    n = nbins - 1
    k = np.arange(nbins, dtype=float)
    log_comb = gammaln(n + 1) - gammaln(k + 1) - gammaln(n - k + 1)

    def binom_weights(prob: float) -> np.ndarray:
        prob = min(1.0 - 1e-6, max(1e-6, float(prob)))
        logw = log_comb + k * np.log(prob) + (n - k) * np.log(1.0 - prob)
        w = np.exp(logw - np.max(logw))
        area = np.trapezoid(w, centers) if w.size > 1 else w[0]
        return w / max(float(area), 1e-12)

    def residual(x: np.ndarray) -> np.ndarray:
        b0, sl, amp, logit_p = x[:4]
        pval = 1.0 / (1.0 + np.exp(-logit_p))
        w = amp * binom_weights(pval)
        r = b0 + sl * v - K @ w - fixed_sharp_abs - y
        if K_sharp is not None and n_sharp:
            sharp_amps = np.maximum(x[4:4 + n_sharp], 0.0)
            r = r - K_sharp @ sharp_amps
        return r

    x0 = np.array([baseline, slope, amp0, 0.0] + [amp0 / max(n_sharp, 1)] * n_sharp)
    lo = np.array([0.0, -np.inf, 0.0, -12.0] + [0.0] * n_sharp)
    hi = np.array([np.inf, np.inf, np.inf, 12.0] + [np.inf] * n_sharp)
    res = least_squares(residual, x0, bounds=(lo, hi), max_nfev=2000)
    b0, sl, amp, logit_p = res.x[:4]
    pval = 1.0 / (1.0 + np.exp(-logit_p))
    w = float(amp) * binom_weights(float(pval))
    sharp_weights_free = np.maximum(res.x[4:4 + n_sharp], 0.0) if n_sharp else None
    sharp_weights_arr = merge_sharp_weights(sharp_weights_free, sharp_fixed_mask, fixed_sharp_weights)
    fitted = float(b0) + float(sl) * v - K @ w - fixed_sharp_abs
    if K_sharp is not None and sharp_weights_free is not None:
        fitted = fitted - K_sharp @ sharp_weights_free
    residuals = y - fitted
    return BhfDistributionFit(
        bhf_centers=centers,
        weights=w,
        probability=normalize_probability(w, centers),
        fitted_curve=fitted,
        residuals=residuals,
        baseline=float(b0),
        slope=float(sl),
        alpha=0.0,
        rms=float(np.sqrt(np.mean(residuals**2))),
        success=bool(res.success),
        message=f"Binomial {variable}: p={pval:.6g}; {res.message}",
        sharp_bhf_centers=sharp_bhf_centers,
        sharp_weights=sharp_weights_arr,
        fitted_dist_p=float(pval),
    )


def fit_fixed_hyperfine_distribution(
    v: np.ndarray,
    y: np.ndarray,
    centers: np.ndarray,
    fixed_weights: np.ndarray,
    *,
    variable: str = "bhf",
    delta: float = 0.0,
    quad: float = 0.0,
    bhf: float = BHF_DEFAULT_T,
    gamma: float = 0.18,
    baseline: float | None = None,
    slope: float | None = None,
    sharp_components: list[dict[str, float]] | None = None,
) -> BhfDistributionFit:
    """Ajusta amplitud de una distribución fija dada por centros y pesos.

    Opcionalmente suma componentes nítidos (sharp_components) con amplitud libre >= 0.
    """
    v = _finite_1d("v", v); y = _finite_1d("y", y)
    centers = _finite_1d("centers", centers)
    fixed_weights = _finite_1d("fixed_weights", fixed_weights)
    if centers.size != fixed_weights.size:
        raise ValueError("centers y fixed_weights deben tener la misma longitud")
    K = build_hyperfine_distribution_kernel(v, centers, variable=variable, delta=delta, quad=quad, bhf=bhf, gamma=gamma)
    K_sharp, sharp_bhf_centers, fixed_sharp_abs, sharp_fixed_mask, fixed_sharp_weights = build_sharp_kernel_for_fit(
        v, sharp_components, default_delta=delta, default_quad=quad, default_gamma=gamma)
    n_sharp = K_sharp.shape[1] if K_sharp is not None else 0
    w0 = np.maximum(fixed_weights, 0.0)
    if not np.any(w0 > 0):
        raise ValueError("La distribución fija no contiene pesos positivos")
    area = np.trapezoid(w0, centers) if w0.size > 1 else w0[0]
    shape = w0 / max(float(area), 1e-12)
    profile = K @ shape
    if baseline is None:
        baseline = float(np.percentile(y, 90))
    if slope is None:
        slope = 0.0
    # Columnas: [ones, v, -profile_dist, -sharp_0_libre, -sharp_1_libre, ...]
    # Los nítidos fijos se restan como absorción conocida en el modelo.
    cols = [np.ones_like(v), v, -profile]
    lo = [0.0, -np.inf, 0.0]
    hi = [np.inf, np.inf, np.inf]
    if K_sharp is not None:
        for j in range(n_sharp):
            cols.append(-K_sharp[:, j])
            lo.append(0.0)
            hi.append(np.inf)
    X = np.column_stack(cols)
    result = lsq_linear(X, y + fixed_sharp_abs, bounds=(lo, hi), lsmr_tol="auto")
    b0, sl, amp = result.x[:3]
    sharp_weights_free = np.maximum(result.x[3:3 + n_sharp], 0.0) if n_sharp else None
    sharp_weights_arr = merge_sharp_weights(sharp_weights_free, sharp_fixed_mask, fixed_sharp_weights)
    weights = float(amp) * shape
    fitted = float(b0) + float(sl) * v - K @ weights - fixed_sharp_abs
    if K_sharp is not None and sharp_weights_free is not None:
        fitted = fitted - K_sharp @ sharp_weights_free
    residuals = y - fitted
    return BhfDistributionFit(
        bhf_centers=centers,
        weights=weights,
        probability=normalize_probability(weights, centers),
        fitted_curve=fitted,
        residuals=residuals,
        baseline=float(b0),
        slope=float(sl),
        alpha=0.0,
        rms=float(np.sqrt(np.mean(residuals**2))),
        success=bool(result.success),
        message="Fixed distribution",
        sharp_bhf_centers=sharp_bhf_centers,
        sharp_weights=sharp_weights_arr,
    )


def fit_bhf_distribution(
    v: np.ndarray,
    y: np.ndarray,
    *,
    delta: float = 0.0,
    quad: float = 0.0,
    gamma: float = 0.18,
    gamma2_rel: float = 1.0,
    gamma3_rel: float = 1.0,
    int1: float = 1.0,
    int2_rel: float = 1.0,
    int3_rel: float = 1.0,
    bmin: float = 0.0,
    bmax: float = 50.0,
    nbins: int = 50,
    alpha: float = 1e-2,
    fit_baseline: bool = True,
    fit_slope: bool = True,
    baseline: float | None = None,
    slope: float | None = None,
    baseline_bounds: tuple[float, float] = (0.0, np.inf),
    slope_bounds: tuple[float, float] = (-np.inf, np.inf),
    sharp_components: list[dict[str, float]] | None = None,
    sigma: np.ndarray | None = None,
) -> BhfDistributionFit:
    """Compatibilidad: distribución Hesse-Rübartsch de BHF."""
    return fit_hyperfine_distribution(
        v, y, variable="bhf", delta=delta, quad=quad, gamma=gamma,
        gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel, int1=int1,
        int2_rel=int2_rel, int3_rel=int3_rel, pmin=bmin, pmax=bmax,
        nbins=nbins, alpha=alpha, fit_baseline=fit_baseline,
        fit_slope=fit_slope, baseline=baseline, slope=slope,
        baseline_bounds=baseline_bounds, slope_bounds=slope_bounds,
        sharp_components=sharp_components, sigma=sigma,
    )


def fit_bhf_distribution_nnls_fixed_background(
    v: np.ndarray,
    y: np.ndarray,
    *,
    baseline: float,
    slope: float = 0.0,
    delta: float = 0.0,
    quad: float = 0.0,
    gamma: float = 0.18,
    bmin: float = 0.0,
    bmax: float = 50.0,
    nbins: int = 50,
    alpha: float = 1e-2,
) -> BhfDistributionFit:
    """Variante con fondo fijo resuelta por NNLS puro."""
    v = _finite_1d("v", v)
    y = _finite_1d("y", y)
    centers = bhf_grid(bmin, bmax, nbins)
    K = build_bhf_kernel(v, centers, delta=delta, quad=quad, gamma=gamma)
    L = second_difference_matrix(centers.size)
    rhs = float(baseline) + float(slope) * v - y
    A = np.vstack([K, np.sqrt(float(alpha)) * L])
    b = np.concatenate([rhs, np.zeros(L.shape[0], dtype=float)])
    weights, _rnorm = nnls(A, b)
    fitted = float(baseline) + float(slope) * v - K @ weights
    residuals = y - fitted
    return BhfDistributionFit(
        bhf_centers=centers,
        weights=weights,
        probability=normalize_probability(weights, centers),
        fitted_curve=fitted,
        residuals=residuals,
        baseline=float(baseline),
        slope=float(slope),
        alpha=float(alpha),
        rms=float(np.sqrt(np.mean(residuals**2))),
        success=True,
        message="NNLS terminado",
    )


def scan_alpha(
    v: np.ndarray,
    y: np.ndarray,
    alphas: np.ndarray | list[float],
    **kwargs: Any,
) -> list[BhfDistributionFit]:
    """Ejecuta el ajuste para varios alpha, util para L-curve/inspeccion visual."""
    return [fit_bhf_distribution(v, y, alpha=float(a), **kwargs) for a in alphas]
