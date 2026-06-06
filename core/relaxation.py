"""Herramientas puras para relajación magnética y ajuste global multi-T.

Este módulo no depende de la GUI. La función principal implementa una primera
fase de ajuste global para espectros medidos a distintas temperaturas usando una
componente Néel--Arrhenius con distribución lognormal de tamaños. Es deliberada-
mente conservadora: comparte los parámetros físicos de la distribución y permite
parámetros locales simples por espectro (base, pendiente, profundidad).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from core.physics import neel_size_relaxation_absorption


@dataclass
class GlobalRelaxationSpectrum:
    velocity: np.ndarray
    y_data: np.ndarray
    temperature_k: float
    sigma_data: np.ndarray | None = None
    label: str = ""


@dataclass
class GlobalRelaxationFitResult:
    shared: dict[str, float]
    local: list[dict[str, float]]
    residuals: np.ndarray
    cost: float
    success: bool
    message: str
    free_keys: list[str]


_SHARED_DEFAULTS = {
    "delta": 0.0,
    "quad": 0.0,
    "bhf": 33.0,
    "gamma1": 0.16,
    "gamma2": 1.0,
    "gamma3": 1.0,
    "int1": 3.0,
    "int2": 2.0,
    "int3": 1.0,
    "neel_log10_keff": 4.0,
    "neel_mean_d_nm": 8.0,
    "neel_sigma": 0.25,
    "neel_log10_tau0": -9.0,
    "neel_bins": 20.0,
}
_SHARED_BOUNDS = {
    "delta": (-2.0, 3.0),
    "quad": (-4.0, 4.0),
    "bhf": (0.0, 60.0),
    "gamma1": (0.03, 2.0),
    "gamma2": (0.2, 3.0),
    "gamma3": (0.2, 3.0),
    "int1": (0.0, 9.0),
    "int2": (0.0, 6.0),
    "int3": (0.0, 3.0),
    "neel_log10_keff": (2.0, 7.0),
    "neel_mean_d_nm": (0.5, 100.0),
    "neel_sigma": (0.01, 1.5),
    "neel_log10_tau0": (-12.0, -6.0),
    "neel_bins": (3.0, 80.0),
}
_LOCAL_DEFAULTS = {"baseline": 1.0, "slope": 0.0, "depth": 0.02}
_LOCAL_BOUNDS = {"baseline": (0.7, 1.3), "slope": (-0.005, 0.005), "depth": (0.0, 0.3)}


def _model_one(v: np.ndarray, temp: float, shared: dict[str, float], local: dict[str, float]) -> np.ndarray:
    absorption = neel_size_relaxation_absorption(
        v,
        delta=float(shared["delta"]),
        quad=float(shared["quad"]),
        bhf=float(shared["bhf"]),
        gamma1=float(shared["gamma1"]),
        gamma2=float(shared["gamma2"]),
        gamma3=float(shared["gamma3"]),
        depth=float(local["depth"]),
        int1=float(shared["int1"]),
        int2=float(shared["int2"]),
        int3=float(shared["int3"]),
        temperature_k=float(temp),
        log10_keff=float(shared["neel_log10_keff"]),
        mean_d_nm=float(shared["neel_mean_d_nm"]),
        sigma_lognormal=float(shared["neel_sigma"]),
        log10_tau0=float(shared["neel_log10_tau0"]),
        n_bins=int(round(float(shared["neel_bins"]))),
    )
    return float(local["baseline"]) + float(local["slope"]) * v - absorption


def fit_neel_size_global(
    spectra: list[GlobalRelaxationSpectrum],
    *,
    shared_initial: dict[str, float] | None = None,
    local_initial: list[dict[str, float]] | None = None,
    fixed_shared: set[str] | None = None,
    fixed_local: set[str] | None = None,
    max_nfev: int = 1200,
) -> GlobalRelaxationFitResult:
    """Ajuste global multi-temperatura de una componente NéelSize.

    Comparte todos los parámetros físicos de ``shared`` entre espectros y deja
    como locales por defecto ``baseline``, ``slope`` y ``depth``. La temperatura
    se toma de cada ``GlobalRelaxationSpectrum``.
    """
    if not spectra:
        raise ValueError("se requiere al menos un espectro")
    shared = dict(_SHARED_DEFAULTS)
    if shared_initial:
        shared.update({k: float(v) for k, v in shared_initial.items()})
    locals_ = [dict(_LOCAL_DEFAULTS) for _ in spectra]
    if local_initial:
        for dst, src in zip(locals_, local_initial):
            dst.update({k: float(v) for k, v in src.items()})

    fixed_shared = set(fixed_shared or {"int3", "neel_bins"})
    fixed_local = set(fixed_local or set())
    shared_free = [k for k in shared if k not in fixed_shared]
    local_free = [(i, k) for i in range(len(spectra)) for k in locals_[i] if k not in fixed_local]
    free_keys = [f"shared:{k}" for k in shared_free] + [f"local:{i}:{k}" for i, k in local_free]

    x0: list[float] = []
    lo: list[float] = []
    hi: list[float] = []
    for k in shared_free:
        x0.append(float(shared[k])); a, b = _SHARED_BOUNDS.get(k, (-np.inf, np.inf)); lo.append(a); hi.append(b)
    for i, k in local_free:
        x0.append(float(locals_[i][k])); a, b = _LOCAL_BOUNDS.get(k, (-np.inf, np.inf)); lo.append(a); hi.append(b)
    x0_arr = np.clip(np.array(x0, dtype=float), np.array(lo, dtype=float), np.array(hi, dtype=float))

    def unpack(x: np.ndarray) -> tuple[dict[str, float], list[dict[str, float]]]:
        sh = dict(shared)
        loc = [dict(d) for d in locals_]
        pos = 0
        for k in shared_free:
            sh[k] = float(x[pos]); pos += 1
        for i, k in local_free:
            loc[i][k] = float(x[pos]); pos += 1
        return sh, loc

    def residual(x: np.ndarray) -> np.ndarray:
        sh, loc = unpack(x)
        parts: list[np.ndarray] = []
        for i, spec in enumerate(spectra):
            v = np.asarray(spec.velocity, dtype=float)
            y = np.asarray(spec.y_data, dtype=float)
            m = _model_one(v, float(spec.temperature_k), sh, loc[i])
            sig = np.asarray(spec.sigma_data, dtype=float) if spec.sigma_data is not None else np.ones_like(y)
            parts.append((m - y) / np.maximum(sig, 1e-12))
        return np.concatenate(parts)

    if x0_arr.size:
        opt = least_squares(residual, x0_arr, bounds=(np.array(lo), np.array(hi)), max_nfev=max_nfev)
        sh, loc = unpack(opt.x)
        res = residual(opt.x)
        return GlobalRelaxationFitResult(sh, loc, res, float(opt.cost), bool(opt.success), str(opt.message), free_keys)
    res = residual(np.array([], dtype=float))
    return GlobalRelaxationFitResult(shared, locals_, res, 0.5 * float(np.dot(res, res)), True, "no free parameters", free_keys)
