#!/usr/bin/env python3
"""Pipeline listo para backend/web para ajuste de distribucion P(BHF).

La idea es que un endpoint pueda llamar a ``fit_ws5_bhf_distribution`` y devolver
el resultado JSON sin conocer detalles de lectura WS5, doblado o sidecars Normos.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from mossbauer_distribution import fit_bhf_distribution, second_difference_matrix
from mossbauer_ws5 import folded_velocity_data, read_normos_sidecar_params


def _as_float(value: float | None, fallback: float) -> float:
    return float(fallback if value is None else value)


def make_sharp_components(
    sharp_bhf: list[float] | tuple[float, ...] | None,
    *,
    delta: float,
    quad: float,
    gamma: float,
    sharp_delta: float | None = None,
    sharp_quad: float | None = None,
    sharp_gamma: float | None = None,
) -> list[dict[str, float]]:
    """Construye componentes nítidos con defaults comunes a la distribución."""
    return [
        {
            "bhf": float(bhf),
            "delta": _as_float(sharp_delta, delta),
            "quad": _as_float(sharp_quad, quad),
            "gamma": _as_float(sharp_gamma, gamma),
        }
        for bhf in (sharp_bhf or [])
    ]


def fit_ws5_bhf_distribution(
    path: str | Path,
    *,
    center: float | None = None,
    vmax: float | None = None,
    norm_percentile: float = 90.0,
    delta: float | None = None,
    quad: float | None = None,
    gamma: float | None = None,
    bmin: float = 0.0,
    bmax: float = 50.0,
    nbins: int = 50,
    alpha: float = 1e-2,
    fit_baseline: bool = True,
    fit_slope: bool = True,
    baseline: float | None = None,
    slope: float | None = 0.0,
    sharp_bhf: list[float] | tuple[float, ...] | None = None,
    sharp_delta: float | None = None,
    sharp_quad: float | None = None,
    sharp_gamma: float | None = None,
    json_ready: bool = True,
) -> dict[str, Any]:
    """Lee un WS5, lo dobla y ajusta P(BHF).

    Devuelve un dict pensado para endpoint web. Si ``json_ready`` es True, los
    arrays se convierten a listas.
    """
    path = Path(path)
    sidecar = read_normos_sidecar_params(path)
    delta_f = float(delta if delta is not None else sidecar.get("delta", 0.0))
    quad_f = float(quad if quad is not None else sidecar.get("quad", 0.0))
    gamma_f = float(gamma if gamma is not None else sidecar.get("gamma", 0.18))

    v, y, folded, center_f, vmax_f, norm = folded_velocity_data(
        path,
        center=center,
        vmax=vmax,
        norm_percentile=norm_percentile,
    )
    sharp_components = make_sharp_components(
        sharp_bhf,
        delta=delta_f,
        quad=quad_f,
        gamma=gamma_f,
        sharp_delta=sharp_delta,
        sharp_quad=sharp_quad,
        sharp_gamma=sharp_gamma,
    )
    fit = fit_bhf_distribution(
        v,
        y,
        delta=delta_f,
        quad=quad_f,
        gamma=gamma_f,
        bmin=bmin,
        bmax=bmax,
        nbins=nbins,
        alpha=alpha,
        fit_baseline=fit_baseline,
        fit_slope=fit_slope,
        baseline=baseline,
        slope=slope,
        sharp_components=sharp_components,
    )

    roughness = float(np.linalg.norm(second_difference_matrix(nbins) @ fit.weights))
    payload: dict[str, Any] = {
        "input": str(path),
        "velocity": v,
        "data": y,
        "folded_counts": folded,
        "BHF_centers": fit.bhf_centers,
        "P": fit.weights,
        "probability": fit.probability,
        "fitted_curve": fit.fitted_curve,
        "residuals": fit.residuals,
        "baseline": fit.baseline,
        "slope": fit.slope,
        "alpha": fit.alpha,
        "rms": fit.rms,
        "roughness_LP": roughness,
        "success": fit.success,
        "message": fit.message,
        "center_internal": center_f,
        "center_normos_equiv": 2.0 * center_f,
        "vmax": vmax_f,
        "norm_factor": norm,
        "delta": delta_f,
        "quad": quad_f,
        "gamma": gamma_f,
        "bmin": float(bmin),
        "bmax": float(bmax),
        "nbins": int(nbins),
        "peak_bhf": float(fit.bhf_centers[int(np.argmax(fit.weights))]),
        "area_weights_trapz": float(np.trapezoid(fit.weights, fit.bhf_centers)),
        "sharp_BHF_centers": np.array([], dtype=float) if fit.sharp_bhf_centers is None else fit.sharp_bhf_centers,
        "sharp_weights": np.array([], dtype=float) if fit.sharp_weights is None else fit.sharp_weights,
    }

    if json_ready:
        return {key: (value.tolist() if isinstance(value, np.ndarray) else value) for key, value in payload.items()}
    return payload
