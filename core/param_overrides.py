"""Sobreescrituras de usuario para los límites de parámetros de la GUI.

Carga y guarda un fichero JSON en ``~/.config/mossbauer_fe33_gui/param_limits.json``.
Las entradas ausentes se completan con los valores de ``core.params`` (fuente de
defaults de solo lectura). El resto del código usa las funciones ``effective_*``
de este módulo en lugar de leer directamente de ``core.params``.

Formato del fichero:
  {
    "component":    {"delta": {"default": 0.0, "lo": -2.0, "hi": 3.0, "step": 0.001, "decimals": 4}, ...},
    "calibration":  {"vmax":  {...}, ...},
    "distribution": {"gamma": {...}, ...}
  }
Solo los campos presentes en el fichero sobreescriben los defaults.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from core.params import (
    CALIBRATION_PARAM_SPECS,
    COMPONENT_PARAM_SPECS,
    DISTRIBUTION_PARAM_SPECS,
    FIT_INIT_SPECS,
    PEAK_DETECTION_SPECS,
    ParamSpec,
)

CONFIG_DIR = Path.home() / ".config" / "mossbauer_fe33_gui"
PARAM_LIMITS_PATH = CONFIG_DIR / "param_limits.json"

Category = Literal["component", "calibration", "distribution", "fit_init", "peak_detection"]

_DEFAULTS: dict[Category, dict[str, ParamSpec]] = {
    "component":      COMPONENT_PARAM_SPECS,
    "calibration":    CALIBRATION_PARAM_SPECS,
    "distribution":   DISTRIBUTION_PARAM_SPECS,
    "fit_init":       FIT_INIT_SPECS,
    "peak_detection": PEAK_DETECTION_SPECS,
}


def load_raw() -> dict[str, dict[str, dict]]:
    """Devuelve el contenido bruto del fichero de sobreescrituras (o {})."""
    if not PARAM_LIMITS_PATH.is_file():
        return {}
    try:
        data = json.loads(PARAM_LIMITS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_raw(data: dict[str, dict[str, dict]]) -> None:
    """Escribe el fichero de sobreescrituras."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PARAM_LIMITS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def effective_specs(category: Category) -> dict[str, ParamSpec]:
    """Devuelve los specs efectivos para ``category``, mezclando overrides con defaults."""
    defaults = _DEFAULTS[category]
    raw = load_raw().get(category, {})
    result: dict[str, ParamSpec] = {}
    for name, spec in defaults.items():
        override = raw.get(name)
        if (category == "calibration" and name == "center" and isinstance(override, dict)
                and not float(override.get("lo", -1.0)) <= 0.0 <= float(override.get("hi", 1.0))):
            # Límites absolutos de antes (250–263, solo válidos para 512
            # canales): ahora son relativos a N/2; se ignoran.
            override = None
        if isinstance(override, dict):
            result[name] = ParamSpec(
                default=float(override.get("default", spec.default)),
                lo=float(override.get("lo", spec.lo)),
                hi=float(override.get("hi", spec.hi)),
                step=float(override.get("step", spec.step)),
                decimals=int(override.get("decimals", spec.decimals)),
            )
        else:
            result[name] = spec
    return result


def fold_center_offsets() -> tuple[float, float]:
    """Margen del punto de plegado respecto a N/2: ``(desde, hasta)`` en canales."""
    spec = effective_specs("calibration")["center"]
    return float(spec.lo), float(spec.hi)


def effective_component_specs() -> dict[str, ParamSpec]:
    return effective_specs("component")


def effective_calibration_specs() -> dict[str, ParamSpec]:
    return effective_specs("calibration")


def effective_distribution_specs() -> dict[str, ParamSpec]:
    return effective_specs("distribution")


def effective_fit_init_specs() -> dict[str, ParamSpec]:
    return effective_specs("fit_init")


def effective_peak_detection_specs() -> dict[str, ParamSpec]:
    return effective_specs("peak_detection")


def component_fit_bound_overrides() -> dict[str, tuple[float | None, float | None]]:
    """Cotas de ajuste que el usuario cambió en Vista › Límites de parámetros.

    La ventana guarda el rango de las casillas; si un extremo difiere del de
    fábrica, ese extremo pasa a ser también la cota del ajuste (antes solo
    cambiaba la casilla y el ajuste seguía con ``COMPONENT_FIT_BOUNDS``, de
    modo que el aviso «fuera de límites» mostraba otro rango). Los extremos
    sin cambiar devuelven ``None``: se queda la cota del código, que en
    profundidad e intensidades es más amplia que el rango de la casilla.
    """
    from core.params import COMPONENT_FIT_BOUNDS
    raw = load_raw().get("component", {})
    out: dict[str, tuple[float | None, float | None]] = {}
    for name in COMPONENT_FIT_BOUNDS:
        override, spec = raw.get(name), COMPONENT_PARAM_SPECS.get(name)
        if not isinstance(override, dict) or spec is None:
            continue
        lo = hi = None
        try:
            if "lo" in override and float(override["lo"]) != spec.lo:
                lo = float(override["lo"])
            if "hi" in override and float(override["hi"]) != spec.hi:
                hi = float(override["hi"])
        except (TypeError, ValueError):
            continue
        if lo is not None and hi is not None and lo >= hi:
            continue
        if lo is not None or hi is not None:
            out[name] = (lo, hi)
    return out
