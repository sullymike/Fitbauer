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


BHF_DEFAULT_T = 33.0
# Posiciones usadas en el ajuste existente de la GUI/web, escaladas a 32.95 T.
LINE_POS_33T = np.array([-10.657, -6.167, -1.677, 1.677, 6.167, 10.657], dtype=float) * 0.5 * (BHF_DEFAULT_T / 32.95)
LINE_QUAD_PATTERN = np.array([0.5, -0.5, -0.5, -0.5, -0.5, 0.5], dtype=float)


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
    if variable in {"quad", "deq", "deltaeq", "Δeq"}:
        return np.column_stack([
            sextet_absorption(v, delta=delta, quad=float(q), bhf=bhf, gamma=gamma, gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel, int1=int1, int2_rel=int2_rel, int3_rel=int3_rel)
            for q in np.asarray(centers, dtype=float)
        ])
    raise ValueError("variable de distribución no reconocida: usa 'bhf' o 'quad'")


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
    ``Singlete``. Sus amplitudes se ajustan con restricción >= 0, pero no se
    regularizan. Para sextetes se devuelve su BHF; para singletes/dobletes se
    devuelve NaN en ``sharp_bhf_centers`` porque no tienen campo hiperfino.
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
) -> BhfDistributionFit:
    """Ajusta una distribución Hesse-Rübartsch de BHF o ΔEQ.

    variable='bhf': centers son campos hiperfinos.
    variable='quad': centers son valores de ΔEQ con BHF fijo en ``bhf``.
    """
    v = _finite_1d("v", v)
    y = _finite_1d("y", y)
    if v.size != y.size:
        raise ValueError("v e y deben tener la misma longitud")
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
    K_sharp, sharp_bhf_centers = build_sharp_kernel(
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
    L = second_difference_matrix(centers.size)

    y_work = y.astype(float).copy()
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
    reg = np.zeros((L.shape[0], X.shape[1]), dtype=float)
    reg[:, dist_start:dist_end] = np.sqrt(float(alpha)) * L
    X_aug = np.vstack([X, reg])
    y_aug = np.concatenate([y_work, np.zeros(L.shape[0], dtype=float)])

    result = lsq_linear(X_aug, y_aug, bounds=(np.array(lower), np.array(upper)), lsmr_tol="auto", max_iter=2000)
    params = result.x

    baseline_fit = float(params[labels.index("baseline")]) if fit_baseline else float(baseline)
    slope_fit = float(params[labels.index("slope")]) if fit_slope else float(slope)
    weights = np.maximum(params[dist_start:dist_end], 0.0)
    sharp_weights = np.maximum(params[sharp_start:sharp_end], 0.0) if sharp_end > sharp_start else None
    fitted = baseline_fit + slope_fit * v - K @ weights
    if K_sharp is not None and sharp_weights is not None:
        fitted = fitted - K_sharp @ sharp_weights
    residuals = y - fitted
    rms = float(np.sqrt(np.mean(residuals**2)))

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
    K_sharp, sharp_bhf_centers = build_sharp_kernel(v, sharp_components, default_delta=delta, default_quad=quad, default_gamma=gamma)
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
        r = b0 + sl * v - K @ w - y
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
    sharp_weights_arr = np.maximum(res.x[5:5 + n_sharp], 0.0) if n_sharp else None
    fitted = float(b0) + float(sl) * v - K @ w
    if K_sharp is not None and sharp_weights_arr is not None:
        fitted = fitted - K_sharp @ sharp_weights_arr
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
    K_sharp, sharp_bhf_centers = build_sharp_kernel(v, sharp_components, default_delta=delta, default_quad=quad, default_gamma=gamma)
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
        r = b0 + sl * v - K @ w - y
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
    sharp_weights_arr = np.maximum(res.x[4:4 + n_sharp], 0.0) if n_sharp else None
    fitted = float(b0) + float(sl) * v - K @ w
    if K_sharp is not None and sharp_weights_arr is not None:
        fitted = fitted - K_sharp @ sharp_weights_arr
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
    K_sharp, sharp_bhf_centers = build_sharp_kernel(v, sharp_components, default_delta=delta, default_quad=quad, default_gamma=gamma)
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
    # Columnas: [ones, v, -profile_dist, -sharp_0, -sharp_1, ...]
    cols = [np.ones_like(v), v, -profile]
    lo = [0.0, -np.inf, 0.0]
    hi = [np.inf, np.inf, np.inf]
    if K_sharp is not None:
        for j in range(n_sharp):
            cols.append(-K_sharp[:, j])
            lo.append(0.0)
            hi.append(np.inf)
    X = np.column_stack(cols)
    result = lsq_linear(X, y, bounds=(lo, hi), lsmr_tol="auto")
    b0, sl, amp = result.x[:3]
    sharp_weights_arr = np.maximum(result.x[3:3 + n_sharp], 0.0) if n_sharp else None
    weights = float(amp) * shape
    fitted = float(b0) + float(sl) * v - K @ weights
    if K_sharp is not None and sharp_weights_arr is not None:
        fitted = fitted - K_sharp @ sharp_weights_arr
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
) -> BhfDistributionFit:
    """Compatibilidad: distribución Hesse-Rübartsch de BHF."""
    return fit_hyperfine_distribution(
        v, y, variable="bhf", delta=delta, quad=quad, gamma=gamma,
        gamma2_rel=gamma2_rel, gamma3_rel=gamma3_rel, int1=int1,
        int2_rel=int2_rel, int3_rel=int3_rel, pmin=bmin, pmax=bmax,
        nbins=nbins, alpha=alpha, fit_baseline=fit_baseline,
        fit_slope=fit_slope, baseline=baseline, slope=slope,
        baseline_bounds=baseline_bounds, slope_bounds=slope_bounds,
        sharp_components=sharp_components,
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
