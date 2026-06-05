"""Vistas/adaptadores puros para consultar resultados de ajuste.

Estas clases no modifican los resultados originales ni dependen de GUI. Su
objetivo es ofrecer una API estable para informes, exportadores y front-ends,
evitando acceso disperso a ``result.values``, ``result.stats`` o atributos
específicos de distribución.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


@dataclass(frozen=True)
class ResultMetric:
    """Métrica escalar lista para presentar/exportar."""

    key: str
    label: str
    value: float | str | int | bool | None
    unit: str = ""


@dataclass(frozen=True)
class ParameterEstimate:
    """Estimación de un parámetro ajustado o fijo."""

    key: str
    value: float | None
    error: float | None = None
    fixed: bool = False
    unit: str = ""


_DISCRETE_METRIC_LABELS = {
    "chi2": "χ²",
    "red_chi2": "χ² reducido",
    "dof": "Grados de libertad",
    "aic": "AIC",
    "bic": "BIC",
    "n_params": "Nº parámetros",
    "rms": "RMS",
    "resid_lag1": "Autocorrelación lag-1",
    "resid_runs_z": "Runs test (z)",
    "resid_antisym_corr": "Correlación antisimétrica",
}

_DISTRIBUTION_METRIC_LABELS = {
    "rms": "RMS",
    "alpha": "α",
    "baseline": "Línea base",
    "slope": "Pendiente",
    "effective_dof": "Grados efectivos de libertad",
    "fitted_dist_center": "Centro distribución",
    "fitted_dist_sigma": "σ distribución",
    "fitted_dist_p": "p distribución",
    "success": "Éxito",
    "message": "Mensaje",
}


class DiscreteResultView:
    """Adapter de solo lectura para ``core.fit_engine.FitResult``."""

    def __init__(self, result: Any, *, fixed: Mapping[str, bool] | None = None):
        self.result = result
        self.fixed = dict(fixed or {})

    def value_for(self, key: str, default: float | None = None) -> float | None:
        values = getattr(self.result, "values", {}) or {}
        return values.get(key, default)

    def error_for(self, key: str, default: float | None = None) -> float | None:
        errors = getattr(self.result, "errors", {}) or {}
        return errors.get(key, default)

    def stat_for(self, key: str, default: float | None = None) -> float | None:
        stats = getattr(self.result, "stats", {}) or {}
        return stats.get(key, default)

    def has_errors(self) -> bool:
        return bool(getattr(self.result, "errors", {}) or {})

    def red_chi2(self) -> float | None:
        return self.stat_for("red_chi2")

    def free_keys(self) -> tuple[str, ...]:
        return tuple(getattr(self.result, "free_keys", []) or [])

    def n_starts(self) -> int:
        return int(getattr(self.result, "n_starts", 0) or 0)

    def correlations(self) -> Mapping[str, Any]:
        return getattr(self.result, "correlations", {}) or {}

    def stats_dict(self, *, keys: tuple[str, ...] | None = None) -> dict[str, Any]:
        return {metric.key: metric.value for metric in self.metrics(keys=keys)}

    def metrics(self, *, keys: tuple[str, ...] | None = None) -> list[ResultMetric]:
        stats = getattr(self.result, "stats", {}) or {}
        selected = keys or tuple(_DISCRETE_METRIC_LABELS.keys())
        out: list[ResultMetric] = []
        for key in selected:
            if key in stats:
                out.append(ResultMetric(key, _DISCRETE_METRIC_LABELS.get(key, key), stats[key]))
        if (keys is None or "n_starts" in selected) and hasattr(self.result, "n_starts"):
            out.append(ResultMetric("n_starts", "Arranques", getattr(self.result, "n_starts")))
        if (keys is None or "success" in selected) and hasattr(self.result, "success"):
            out.append(ResultMetric("success", "Éxito", bool(getattr(self.result, "success"))))
        return out

    def parameters(self, *, keys: tuple[str, ...] | None = None) -> list[ParameterEstimate]:
        values = getattr(self.result, "values", {}) or {}
        errors = getattr(self.result, "errors", {}) or {}
        selected = keys or tuple(values.keys())
        return [
            ParameterEstimate(
                key=key,
                value=values.get(key),
                error=errors.get(key),
                fixed=bool(self.fixed.get(key, False)),
            )
            for key in selected
            if key in values
        ]


class DistributionResultView:
    """Adapter de solo lectura para resultados de distribución hiperfina."""

    def __init__(self, result: Any):
        self.result = result

    def probability_curve(self) -> tuple[np.ndarray, np.ndarray]:
        return (
            np.asarray(getattr(self.result, "bhf_centers"), dtype=float),
            np.asarray(getattr(self.result, "probability"), dtype=float),
        )

    def fitted_curve(self) -> np.ndarray:
        return np.asarray(getattr(self.result, "fitted_curve"), dtype=float)

    def residuals(self) -> np.ndarray:
        return np.asarray(getattr(self.result, "residuals"), dtype=float)

    def sharp_weights(self) -> np.ndarray | None:
        weights = getattr(self.result, "sharp_weights", None)
        return None if weights is None else np.asarray(weights, dtype=float)

    def metrics(self, *, keys: tuple[str, ...] | None = None) -> list[ResultMetric]:
        selected = keys or tuple(_DISTRIBUTION_METRIC_LABELS.keys())
        out: list[ResultMetric] = []
        for key in selected:
            if hasattr(self.result, key):
                out.append(ResultMetric(key, _DISTRIBUTION_METRIC_LABELS.get(key, key), getattr(self.result, key)))
        return out

    def parameters(self) -> list[ParameterEstimate]:
        keys = ("baseline", "slope", "alpha", "fitted_dist_center", "fitted_dist_sigma", "fitted_dist_p")
        out: list[ParameterEstimate] = []
        for key in keys:
            if hasattr(self.result, key):
                value = getattr(self.result, key)
                if value is not None:
                    out.append(ParameterEstimate(key=key, value=float(value)))
        return out


def discrete_result_view(result: Any, *, fixed: Mapping[str, bool] | None = None) -> DiscreteResultView:
    return DiscreteResultView(result, fixed=fixed)


def distribution_result_view(result: Any) -> DistributionResultView:
    return DistributionResultView(result)
