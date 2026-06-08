"""Validación pura de parámetros y estados de ajuste.

No depende de la GUI. Devuelve incidencias estructuradas para que cada front-end
decida si las muestra como aviso, error CLI, etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np


@dataclass(frozen=True)
class ValidationIssue:
    """Incidencia de validación de un parámetro/estado."""

    key: str
    message: str
    severity: str = "error"  # "error" / "warning"


def _is_finite_number(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def validate_values_against_bounds(
    values: Mapping[str, Any],
    bounds: Mapping[str, tuple[float, float]],
    *,
    keys: Iterable[str] | None = None,
    tolerance: float = 1e-12,
) -> list[ValidationIssue]:
    """Comprueba finitud y límites de un mapa plano de parámetros."""
    issues: list[ValidationIssue] = []
    selected = list(keys) if keys is not None else list(values.keys())
    for key in selected:
        if key not in values:
            continue
        value = values[key]
        if not _is_finite_number(value):
            issues.append(ValidationIssue(str(key), f"{key}: valor no finito"))
            continue
        if key in bounds:
            lo, hi = bounds[key]
            x = float(value)
            if x < float(lo) - tolerance or x > float(hi) + tolerance:
                issues.append(ValidationIssue(
                    str(key),
                    f"{key}: {x:.6g} fuera de límites [{float(lo):.6g}, {float(hi):.6g}]",
                ))
    return issues


def validate_fit_state(state: Any) -> list[ValidationIssue]:
    """Valida un ``core.fit_engine.FitState`` o compatible."""
    issues: list[ValidationIssue] = []
    velocity = np.asarray(getattr(state, "velocity", []), dtype=float)
    y_data = np.asarray(getattr(state, "y_data", []), dtype=float)
    sigma = getattr(state, "sigma_data", None)
    if velocity.size == 0:
        issues.append(ValidationIssue("velocity", "No hay eje de velocidad"))
    elif not np.all(np.isfinite(velocity)):
        issues.append(ValidationIssue("velocity", "El eje de velocidad contiene valores no finitos"))
    if y_data.size == 0:
        issues.append(ValidationIssue("y_data", "No hay datos normalizados"))
    elif not np.all(np.isfinite(y_data)):
        issues.append(ValidationIssue("y_data", "Los datos contienen valores no finitos"))
    if velocity.size and y_data.size and velocity.size != y_data.size:
        issues.append(ValidationIssue("data_shape", "Velocidad y datos tienen longitudes distintas"))
    if sigma is not None:
        sigma_arr = np.asarray(sigma, dtype=float)
        if sigma_arr.size != y_data.size:
            issues.append(ValidationIssue("sigma", "Sigma y datos tienen longitudes distintas"))
        elif not np.all(np.isfinite(sigma_arr)) or np.any(sigma_arr <= 0):
            issues.append(ValidationIssue("sigma", "Sigma contiene valores no finitos o no positivos"))
    values = getattr(state, "values", {}) or {}
    bounds = getattr(state, "bounds", {}) or {}
    issues.extend(validate_values_against_bounds(values, bounds))
    for comp in getattr(state, "components", []) or []:
        idx = getattr(comp, "idx", "?")
        kind = getattr(comp, "kind", "")
        if kind not in {"Sextete", "Doblete", "Singlete"}:
            issues.append(ValidationIssue(f"s{idx}_kind", f"Componente {idx}: tipo desconocido {kind!r}"))
    return issues


def validate_distribution_parameters(state: Any) -> list[ValidationIssue]:
    """Valida un snapshot/objeto con parámetros de distribución."""
    issues: list[ValidationIssue] = []
    numeric_keys = ("delta", "quad", "fixed_bhf", "gamma", "bmin", "bmax", "log_alpha")
    for key in numeric_keys:
        if not _is_finite_number(getattr(state, key, None)):
            issues.append(ValidationIssue(key, f"{key}: valor no finito"))
    nbins = getattr(state, "nbins", None)
    if not _is_finite_number(nbins) or int(nbins) < 5:
        issues.append(ValidationIssue("nbins", "nbins debe ser ≥ 5"))
    if _is_finite_number(getattr(state, "bmin", None)) and _is_finite_number(getattr(state, "bmax", None)):
        if float(state.bmax) <= float(state.bmin):
            issues.append(ValidationIssue("range", "El máximo de la distribución debe ser mayor que el mínimo"))
    if _is_finite_number(getattr(state, "gamma", None)) and float(state.gamma) <= 0:
        issues.append(ValidationIssue("gamma", "La anchura Γ debe ser positiva"))
    if getattr(state, "shape", "Histograma") not in {"Histograma", "Gaussiana", "Binomial", "Fija"}:
        issues.append(ValidationIssue("shape", f"Forma de distribución desconocida: {getattr(state, 'shape')!r}"))
    if getattr(state, "reg_mode", "tikhonov") not in {"tikhonov", "tv"}:
        issues.append(ValidationIssue("reg_mode", f"Regularización desconocida: {getattr(state, 'reg_mode')!r}"))
    return issues


def format_validation_issues(issues: Iterable[ValidationIssue], *, max_items: int = 8) -> str:
    """Formato compacto para CLIs/GUI."""
    items = list(issues)
    shown = items[:max_items]
    text = "\n".join(f"• {issue.message}" for issue in shown)
    if len(items) > len(shown):
        text += f"\n• … y {len(items) - len(shown)} más"
    return text
