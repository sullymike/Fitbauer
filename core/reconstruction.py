"""Reconstrucción pura de curvas de modelo para visualización/análisis.

Las funciones de este módulo no dependen de Qt ni de la GUI. Reciben arrays,
resultados de ajuste y descripciones simples de componentes, y devuelven curvas
listas para que cualquier front-end las etiquete/dibuje.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from contextlib import nullcontext

from core.constants import SEXTET_PARAM_NAMES
from core.fit_engine import model_from_values
from core.physics import component_absorption, line_profile


@dataclass(frozen=True)
class ReconstructedCurve:
    """Curva reconstruida asociada a una componente o envolvente."""

    idx: int
    kind: str
    y: np.ndarray


@dataclass(frozen=True)
class DiscreteReconstruction:
    """Reconstrucción de un modelo discreto para visualización."""

    model: np.ndarray
    residual: np.ndarray
    model_v: np.ndarray | None
    model_dense: np.ndarray
    components: list[ReconstructedCurve]


def dense_velocity_grid(v: np.ndarray, *, factor: int = 6,
                        min_points: int = 1200, max_points: int = 6000) -> np.ndarray | None:
    """Rejilla densa para dibujar modelos suaves sin depender de la GUI."""
    arr = np.asarray(v, dtype=float)
    if arr.size < 2:
        return None
    n = int(np.clip(arr.size * factor, min_points, max_points))
    if n <= arr.size:
        return None
    return np.linspace(float(np.min(arr)), float(np.max(arr)), n)


def component_params_array(component: Any, values: Mapping[str, float] | None = None) -> np.ndarray:
    """Vector canónico de parámetros para una componente con ``idx``/``value``."""
    out = []
    for name in SEXTET_PARAM_NAMES:
        key = f"s{int(component.idx)}_{name}"
        if values is not None and key in values:
            out.append(float(values[key]))
        else:
            out.append(float(component.value(name)))
    return np.array(out, dtype=float)


def component_absorption_area(
    kind: str,
    params: np.ndarray,
    velocity: np.ndarray | None = None,
) -> float:
    """Área positiva de absorción de una componente en el rango de velocidad."""
    if velocity is not None and np.asarray(velocity).size > 1:
        arr = np.asarray(velocity, dtype=float)
        vmin = float(np.min(arr))
        vmax = float(np.max(arr))
        n = max(2000, int(arr.size) * 8)
        grid = np.linspace(vmin, vmax, n)
    else:
        grid = np.linspace(-12.0, 12.0, 4000)
    absorption = component_absorption(grid, kind, np.asarray(params, dtype=float))
    return float(np.trapezoid(np.maximum(absorption, 0.0), grid))


def component_area_percentages(
    components: list[Any],
    velocity: np.ndarray | None = None,
    values: Mapping[str, float] | None = None,
) -> tuple[list[int], np.ndarray, np.ndarray]:
    """Áreas y porcentajes de componentes activas descritas por snapshots."""
    active: list[int] = []
    areas: list[float] = []
    for component in components:
        p_arr = component_params_array(component, values)
        areas.append(max(0.0, component_absorption_area(component.kind, p_arr, velocity)))
        active.append(int(component.idx))
    area_arr = np.array(areas, dtype=float)
    total = float(np.sum(area_arr))
    pct = 100.0 * area_arr / total if total > 0 else np.zeros_like(area_arr)
    return active, area_arr, pct


def reconstruct_discrete_model(
    velocity: np.ndarray,
    y_data: np.ndarray,
    values: Mapping[str, float],
    components: list[Any],
    constraints: list[dict] | None,
    *,
    absorber_model: str = "thin",
    line_profile_kind: str | None = None,
    voigt_sigma: float = 0.05,
) -> DiscreteReconstruction:
    """Reconstruye modelo, residuos y subcomponentes de un ajuste discreto.

    ``line_profile_kind`` / ``voigt_sigma`` fijan de forma determinista la forma
    de línea (Lorentziana/Voigt) durante la reconstrucción, para que la
    previsualización refleje el perfil y la σ actuales del panel. Si es ``None``
    se respeta el estado global vigente (retrocompatibilidad).
    """
    v = np.asarray(velocity, dtype=float)
    y = np.asarray(y_data, dtype=float)
    constraints = constraints or []
    ctx = (line_profile(line_profile_kind, voigt_sigma)
           if line_profile_kind is not None else nullcontext())
    with ctx:
        model = model_from_values(v, values, components, constraints,
                                  absorber_model=absorber_model)
        mv = dense_velocity_grid(v)
        if mv is not None:
            model_dense = model_from_values(mv, values, components, constraints,
                                            absorber_model=absorber_model)
        else:
            model_dense = model
        residual = y - model
        curves: list[ReconstructedCurve] = []
        enabled = [c for c in components if getattr(c, "enabled", False)]
        if len(enabled) >= 2:
            grid = mv if mv is not None else v
            for comp in enabled:
                only_this = model_from_values(grid, values, [comp], constraints,
                                              absorber_model=absorber_model)
                curves.append(ReconstructedCurve(int(comp.idx), str(comp.kind), only_this))
    return DiscreteReconstruction(
        model=model,
        residual=residual,
        model_v=mv,
        model_dense=model_dense,
        components=curves,
    )


def sharp_component_params(component: Mapping[str, Any], weight: float | None = None) -> np.ndarray:
    """Convierte una componente nítida de distribución al vector canónico.

    ``component`` usa el formato simple producido por la capa GUI/headless de
    distribución: ``gamma`` e intensidades relativas. Si ``weight`` se indica,
    sustituye la profundidad ajustada.
    """
    depth = float(component.get("depth", 0.0) if weight is None else weight)
    values = {
        "delta": float(component.get("delta", 0.0)),
        "quad": float(component.get("quad", 0.0)),
        "bhf": float(component.get("bhf", 33.0)),
        "gamma1": float(component.get("gamma", component.get("gamma1", 0.18))),
        "gamma2": float(component.get("gamma2_rel", component.get("gamma2", 1.0))),
        "gamma3": float(component.get("gamma3_rel", component.get("gamma3", 1.0))),
        "depth": depth,
        "int1": float(component.get("int1", 1.0)),
        "int2": float(component.get("int2_rel", component.get("int2", 1.0))),
        "int3": float(component.get("int3_rel", component.get("int3", 1.0))),
    }
    return np.array([values[name] for name in SEXTET_PARAM_NAMES], dtype=float)


def reconstruct_distribution_curves(
    velocity: np.ndarray,
    fitted_curve: np.ndarray,
    baseline: float,
    slope: float,
    sharp_components: list[Mapping[str, Any]] | None,
    sharp_indices: list[int] | tuple[int, ...],
    sharp_weights: np.ndarray | None,
    *,
    distribution_kind: str,
) -> list[ReconstructedCurve]:
    """Reconstruye envolvente de distribución y componentes nítidas.

    Devuelve curvas en orden de dibujo: primero la envolvente de distribución
    (idx=0) si hay contribución nítida, después cada componente nítida.
    """
    if not sharp_components or sharp_weights is None or np.asarray(sharp_weights).size == 0:
        return []
    v = np.asarray(velocity, dtype=float)
    baseline_line = float(baseline) + float(slope) * v
    sharp_abs_sum = np.zeros_like(v, dtype=float)
    curves: list[ReconstructedCurve] = []
    for idx, component, weight in zip(sharp_indices, sharp_components, sharp_weights):
        params = sharp_component_params(component, float(weight))
        kind = str(component.get("kind", "Sextete"))
        sharp_abs = component_absorption(v, kind, params)
        sharp_abs_sum += sharp_abs
        curves.append(ReconstructedCurve(int(idx), kind, baseline_line - sharp_abs))
    if np.any(sharp_abs_sum > 0):
        curves.insert(
            0,
            ReconstructedCurve(0, distribution_kind, np.asarray(fitted_curve, dtype=float) + sharp_abs_sum),
        )
    return curves
