"""Validación pura de parámetros y estados de ajuste.

No depende de la GUI. Devuelve incidencias estructuradas para que cada front-end
decida si las muestra como aviso, error CLI, etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np

from core.params import COMPONENT_KINDS, DISTRIBUTION_SHAPES, GAUSSIAN_DISTRIBUTION_SHAPES
from mossbauer_i18n import tr


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
            issues.append(ValidationIssue(str(key), tr("valid.not_finite", name=key)))
            continue
        if key in bounds:
            lo, hi = bounds[key]
            x = float(value)
            if x < float(lo) - tolerance or x > float(hi) + tolerance:
                issues.append(ValidationIssue(
                    str(key),
                    tr("valid.out_of_bounds", name=key, value=f"{x:.6g}",
                       lo=f"{float(lo):.6g}", hi=f"{float(hi):.6g}"),
                ))
    return issues


def validate_fit_state(state: Any) -> list[ValidationIssue]:
    """Valida un ``core.fit_engine.FitState`` o compatible."""
    issues: list[ValidationIssue] = []
    velocity = np.asarray(getattr(state, "velocity", []), dtype=float)
    y_data = np.asarray(getattr(state, "y_data", []), dtype=float)
    sigma = getattr(state, "sigma_data", None)
    if velocity.size == 0:
        issues.append(ValidationIssue("velocity", tr("valid.no_velocity")))
    elif not np.all(np.isfinite(velocity)):
        issues.append(ValidationIssue("velocity", tr("valid.velocity_not_finite")))
    if y_data.size == 0:
        issues.append(ValidationIssue("y_data", tr("valid.no_data")))
    elif not np.all(np.isfinite(y_data)):
        issues.append(ValidationIssue("y_data", tr("valid.data_not_finite")))
    if velocity.size and y_data.size and velocity.size != y_data.size:
        issues.append(ValidationIssue("data_shape", tr("valid.length_mismatch")))
    if sigma is not None:
        sigma_arr = np.asarray(sigma, dtype=float)
        if sigma_arr.size != y_data.size:
            issues.append(ValidationIssue("sigma", tr("valid.sigma_length")))
        elif not np.all(np.isfinite(sigma_arr)) or np.any(sigma_arr <= 0):
            issues.append(ValidationIssue("sigma", tr("valid.sigma_invalid")))
    values = getattr(state, "values", {}) or {}
    bounds = getattr(state, "bounds", {}) or {}
    issues.extend(validate_values_against_bounds(values, bounds))
    for comp in getattr(state, "components", []) or []:
        idx = getattr(comp, "idx", "?")
        kind = getattr(comp, "kind", "")
        if kind not in COMPONENT_KINDS:
            issues.append(ValidationIssue(f"s{idx}_kind", tr("valid.unknown_kind", idx=idx, kind=repr(kind))))
    return issues


def validate_distribution_parameters(state: Any) -> list[ValidationIssue]:
    """Valida un snapshot/objeto con parámetros de distribución."""
    issues: list[ValidationIssue] = []
    numeric_keys = ("delta", "quad", "fixed_bhf", "gamma", "bmin", "bmax", "log_alpha")
    for key in numeric_keys:
        if not _is_finite_number(getattr(state, key, None)):
            issues.append(ValidationIssue(key, tr("valid.not_finite", name=key)))
    nbins = getattr(state, "nbins", None)
    if not _is_finite_number(nbins) or int(nbins) < 5:
        issues.append(ValidationIssue("nbins", tr("valid.nbins_min")))
    if _is_finite_number(getattr(state, "bmin", None)) and _is_finite_number(getattr(state, "bmax", None)):
        if float(state.bmax) <= float(state.bmin):
            issues.append(ValidationIssue("range", tr("valid.range_order")))
    if _is_finite_number(getattr(state, "gamma", None)) and float(state.gamma) <= 0:
        issues.append(ValidationIssue("gamma", tr("valid.gamma_positive")))
    if getattr(state, "shape", "Histograma") not in DISTRIBUTION_SHAPES:
        issues.append(ValidationIssue("shape", tr("valid.unknown_shape", shape=repr(getattr(state, 'shape')))))
    if getattr(state, "reg_mode", "tikhonov") not in {"tikhonov", "tv", "maxent"}:
        issues.append(ValidationIssue("reg_mode", tr("valid.unknown_reg", mode=repr(getattr(state, 'reg_mode')))))
    if getattr(state, "shape", "Histograma") in GAUSSIAN_DISTRIBUTION_SHAPES:
        issues.extend(_validate_vbf_sigma(state))
    return issues


def _validate_vbf_sigma(state: Any) -> list[ValidationIssue]:
    """Límites σ de las gaussianas: σ máx > σ mín y, con σ máx automático,
    σ mín por debajo de la anchura de la malla (el máximo automático).

    0 en cualquiera de los dos es «automático» y no se comprueba.
    """
    issues: list[ValidationIssue] = []
    variable = str(getattr(state, "variable", "BHF"))
    ejes = variable.split("-")
    axes = [("", ejes[0], "bmin", "bmax")]
    if str(getattr(state, "shape", "")).endswith("2D") and len(ejes) == 2:
        axes.append(("_y", ejes[1], "qmin", "qmax"))
    for suffix, var, k_lo, k_hi in axes:
        smin = getattr(state, f"vbf_sigma_min{suffix}", 0.0)
        smax = getattr(state, f"vbf_sigma_max{suffix}", 0.0)
        if not (_is_finite_number(smin) and _is_finite_number(smax)):
            issues.append(ValidationIssue(f"vbf_sigma{suffix}",
                                          tr("valid.not_finite", name=f"σ {var}")))
            continue
        smin, smax = float(smin), float(smax)
        if smin > 0 and smax > 0 and smax <= smin:
            issues.append(ValidationIssue(f"vbf_sigma{suffix}", tr(
                "valid.vbf_sigma_order", var=var, min=f"{smin:g}", max=f"{smax:g}")))
        elif smin > 0 and smax <= 0:
            lo, hi = getattr(state, k_lo, None), getattr(state, k_hi, None)
            if _is_finite_number(lo) and _is_finite_number(hi):
                span = float(hi) - float(lo)
                if span > 0 and smin >= span:
                    issues.append(ValidationIssue(f"vbf_sigma{suffix}", tr(
                        "valid.vbf_sigma_min_span", var=var, min=f"{smin:g}",
                        span=f"{span:g}")))
    return issues


def format_validation_issues(issues: Iterable[ValidationIssue], *, max_items: int = 8) -> str:
    """Formato compacto para CLIs/GUI."""
    items = list(issues)
    shown = items[:max_items]
    text = "\n".join(f"• {issue.message}" for issue in shown)
    if len(items) > len(shown):
        text += "\n• " + tr("valid.more", n=len(items) - len(shown))
    return text
