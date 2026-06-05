"""Registro único de parámetros del modelo Mössbauer Fe-57.

Fuente única de: orden canónico, conjuntos usados por tipo de componente,
relevancia para el ajuste, valores por defecto, rangos/resolución de los
controles de la GUI y límites del ajuste. Lo consumen la interfaz Qt
(construcción de los controles de componente) y ``core.session`` (controlador
headless: valores por defecto y construcción del ``FitState``). No depende de
ninguna GUI.
"""
from __future__ import annotations

from dataclasses import dataclass

BHF_DEFAULT_T = 33.0
MAX_COMPONENTS = 6

# Orden canónico de parámetros de componente (incluye ocultos int3/texture/beta).
PARAM_ORDER = (
    "delta", "quad", "bhf", "gamma1", "gamma2", "gamma3",
    "depth", "int1", "int2", "int3", "texture", "beta",
)
# Parámetros "clásicos" reportados por componente activo en el ajuste por lotes.
ACTIVE_PARAM_ORDER = (
    "delta", "quad", "bhf", "gamma1", "gamma2", "gamma3",
    "depth", "int1", "int2", "int3",
)

# Conjunto de parámetros realmente usados por cada tipo de componente.
USED_BY = {
    "Sextete": {"delta", "quad", "bhf", "gamma1", "gamma2", "gamma3",
                "depth", "int1", "int2", "texture", "beta"},
    "Doblete": {"delta", "quad", "gamma1", "gamma2", "depth", "int1", "int2"},
    "Singlete": {"delta", "gamma1", "depth", "int1"},
}


@dataclass(frozen=True)
class ParamSpec:
    """Rango/resolución/valor por defecto de un control de la GUI."""

    default: float
    lo: float
    hi: float
    step: float
    decimals: int


# Especificación del control de cada parámetro de componente (lo que ve la GUI).
COMPONENT_PARAM_SPECS = {
    "delta":   ParamSpec(0.0, -2.0, 3.0, 0.001, 4),
    "quad":    ParamSpec(0.0, -4.0, 4.0, 0.001, 4),
    "bhf":     ParamSpec(BHF_DEFAULT_T, 0.0, 60.0, 0.01, 3),
    "gamma1":  ParamSpec(0.15, 0.03, 2.0, 0.001, 4),
    "gamma2":  ParamSpec(1.0, 0.2, 3.0, 0.001, 4),
    "gamma3":  ParamSpec(1.0, 0.2, 3.0, 0.001, 4),
    "depth":   ParamSpec(0.020, 0.0, 0.07, 0.0001, 5),
    "int1":    ParamSpec(3.0, 0.0, 6.0, 0.01, 3),
    "int2":    ParamSpec(2.0, 0.0, 4.0, 0.01, 3),
    "texture": ParamSpec(2.0 / 3.0, 0.0, 1.0, 0.001, 4),
    "beta":    ParamSpec(0.0, 0.0, 90.0, 0.1, 2),
    "int3":    ParamSpec(1.0, 1.0, 1.0, 0.0, 3),
}
# Disposición de los controles en la GUI (dos columnas + ocultos).
COMPONENT_PARAM_LAYOUT = {
    "left": ("delta", "quad", "bhf", "gamma1", "gamma2", "gamma3"),
    "right": ("depth", "int1", "int2", "texture", "beta"),
    "hidden": ("int3",),
}
# La profundidad por defecto del primer componente es mayor que la del resto.
DEPTH_DEFAULT_FIRST = 0.020
DEPTH_DEFAULT_OTHERS = 0.005

# Límites del AJUSTE (más amplios que los rangos de los controles de la GUI).
GLOBAL_FIT_BOUNDS = {
    "baseline": (0.70, 1.30), "slope": (-0.005, 0.005),
    "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0), "sat_scale": (0.05, 50.0),
}
COMPONENT_FIT_BOUNDS = {
    "delta": (-2.0, 3.0), "quad": (-4.0, 4.0), "bhf": (0.0, 60.0),
    "gamma1": (0.03, 2.0), "gamma2": (0.2, 3.0), "gamma3": (0.2, 3.0),
    "depth": (0.0, 0.30), "int1": (0.0, 9.0), "int2": (0.0, 6.0),
    "int3": (0.0, 3.0), "texture": (0.0, 1.0), "beta": (0.0, 90.0),
}


def component_default_value(name: str, idx: int = 1) -> float:
    """Valor por defecto de un parámetro de componente (``depth`` depende del índice)."""
    if name == "depth":
        return DEPTH_DEFAULT_FIRST if idx == 1 else DEPTH_DEFAULT_OTHERS
    return COMPONENT_PARAM_SPECS[name].default


def component_defaults(idx: int) -> dict[str, float]:
    """Valores por defecto de todos los parámetros de un componente."""
    return {name: component_default_value(name, idx) for name in PARAM_ORDER}


def relevant_params(kind: str, intensity_mode: str, quad_treatment: str) -> set[str]:
    """Parámetros realmente ajustables según tipo/modo de intensidad/cuadrupolo.

    Los no incluidos (p. ej. ``texture`` en modo libre, ``int1``/``int2`` en modo
    textura, ``beta`` salvo Kündig fijo, ``int3`` siempre) no deben ajustarse.
    """
    used = set(USED_BY.get(kind, set()))
    if kind == "Sextete":
        if intensity_mode == "texture":
            used.discard("int1")
            used.discard("int2")
        else:
            used.discard("texture")
        if quad_treatment != "kundig_fixed":
            used.discard("beta")
    else:
        used.discard("texture")
        used.discard("beta")
    return used
