#!/usr/bin/env python3
"""Capa de ajuste/sesión headless, sin dependencia de ninguna GUI.

Extrae la orquestación que históricamente vivía en la app Tk
(``MossbauerFe33GUI`` / ``MossbauerApp``) y que usaban el CLI de ajuste por
fichero (``mossbauer_fit_cli.py``) y los tests por lotes. Toda la numérica sigue
delegada en ``core.fit_engine`` y ``core.folding``; aquí solo está el plumbing
``model_state`` ↔ ``FitState`` ↔ ``session_payload``.

Referencia de equivalencia: la interfaz Qt (``mossbauer_qt.py``,
``_build_state`` / ``_session_payload`` / ``_fold_counts_for_center``), que ya
construye exactamente el mismo ``FitState`` sin Tk.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from core.fit_engine import Component, FitState, fit_discrete
from core.folding import (
    find_best_integer_or_half_center,
    fold_and_normalize,
    read_normos_folding_point,
    read_ws5_counts,
    velocity_axis,
)
from core.params import (
    ACTIVE_PARAM_ORDER as _ACTIVE_PARAM_ORDER,
    COMPONENT_KINDS as _COMPONENT_KINDS,
    COMPONENT_FIT_BOUNDS as _PARAM_BOUNDS,
    GLOBAL_FIT_BOUNDS as _GLOBAL_BOUNDS,
    INTENSITY_MODES as _INTENSITY_MODES_TUPLE,
    PARAM_ORDER as _PARAM_ORDER,
    QUAD_TREATMENTS as _QUAD_TREATMENTS_TUPLE,
    BHF_DEFAULT_T,
    component_defaults as _component_defaults,
    relevant_params as _relevant_params,
)

# Recorte de borde del espectro doblado, idéntico a la GUI Tk modular
# (``MossbauerApp._N_EDGE_TRIM``) y a Qt (``_edge_trim``).
_EDGE_TRIM = 1
MAX_COMPONENTS_DEFAULT = 3

_KINDS = set(_COMPONENT_KINDS)
_INTENSITY_MODES = set(_INTENSITY_MODES_TUPLE)
_QUAD_TREATMENTS = set(_QUAD_TREATMENTS_TUPLE)


@dataclass
class ModelState:
    """Estado del modelo de ajuste sin Tk: dicts planos en vez de ``tk.Variable``."""

    vars: dict[str, float]
    fixed: dict[str, bool]
    sextet_enabled: dict[int, bool]
    component_kind: dict[int, str]
    intensity_mode: dict[int, str]
    quad_treatment: dict[int, str]
    constraints: list = field(default_factory=list)
    line_profile: str = "Lorentziana"
    likelihood: str = "gauss"
    robust_loss: str = "linear"
    absorber_model: str = "thin"
    propagate_calib: bool = False
    global_opt: bool = False
    fit_velocity: bool = False
    fit_center: bool = False
    fit_sigma: bool = False
    multistart_n: int = 8
    n_components: int = 1

    @classmethod
    def defaults(cls, n_components: int = MAX_COMPONENTS_DEFAULT) -> "ModelState":
        vars_: dict[str, float] = {
            "vmax": 12.0, "center": 256.0, "baseline": 1.0, "slope": 0.0,
            "voigt_sigma": 0.05, "sat_scale": 1.0,
        }
        fixed: dict[str, bool] = {
            "vmax": True, "center": True, "baseline": False, "slope": False,
            "voigt_sigma": False, "sat_scale": True,
        }
        se: dict[int, bool] = {}
        ck: dict[int, str] = {}
        im: dict[int, str] = {}
        qt: dict[int, str] = {}
        for idx in range(1, n_components + 1):
            for name, val in _component_defaults(idx).items():
                vars_[f"s{idx}_{name}"] = val
                fixed[f"s{idx}_{name}"] = False
            fixed[f"s{idx}_int3"] = True  # int3 es referencia NORMOS, siempre fija
            se[idx] = (idx == 1)
            ck[idx] = "Sextete"
            im[idx] = "free"
            qt[idx] = "1st_order"
        return cls(vars=vars_, fixed=fixed, sextet_enabled=se,
                   component_kind=ck, intensity_mode=im, quad_treatment=qt,
                   n_components=1)

    def apply_template(self, state: dict) -> None:
        """Vuelca un ``model_state`` de plantilla sobre el estado actual.

        Espejo de ``apply_template_model_state``: ignora ``center`` (cada espectro
        detecta el suyo) y valida los enums de tipo/modo/cuadrupolo.
        """
        tvars = dict(state.get("vars", {}))
        tvars.pop("center", None)
        for k, v in tvars.items():
            self.vars[k] = float(v)
        for k, v in state.get("fixed", {}).items():
            self.fixed[k] = bool(v)
        for k, v in state.get("sextet_enabled", {}).items():
            self.sextet_enabled[int(k)] = bool(v)
        for k, v in state.get("component_kind", {}).items():
            if v in _KINDS:
                self.component_kind[int(k)] = v
        for k, v in state.get("intensity_mode", {}).items():
            if v in _INTENSITY_MODES:
                self.intensity_mode[int(k)] = v
        for k, v in state.get("quad_treatment", {}).items():
            if v in _QUAD_TREATMENTS:
                self.quad_treatment[int(k)] = v
        for flag in ("fit_velocity", "fit_center", "fit_sigma",
                     "propagate_calib", "global_opt"):
            if flag in state:
                setattr(self, flag, bool(state[flag]))
        if "multistart_n" in state:
            self.multistart_n = max(0, min(10, int(state["multistart_n"])))
        for skey in ("line_profile", "likelihood", "robust_loss", "absorber_model"):
            if skey in state:
                setattr(self, skey, str(state[skey]))
        if "constraints" in state:
            self.constraints = list(state["constraints"])
        if "n_components" in state:
            self.n_components = int(state["n_components"])
        # int3 sigue siendo referencia fija aunque la plantilla diga otra cosa.
        for idx in self.sextet_enabled:
            key = f"s{idx}_int3"
            if key in self.vars:
                self.fixed[key] = True

    def build_fit_state(self, *, velocity, y_data, sigma_data,
                        counts, norm_factor) -> FitState:
        """Construye el ``FitState`` (espejo Tk-free de ``_build_fit_state``)."""
        values = dict(self.vars)
        fixed = {k: bool(self.fixed.get(k, False)) for k in values}
        # vmax/center se ajustan por separado (fit_velocity/fit_center), nunca como libres.
        fixed["vmax"] = True
        fixed["center"] = True
        components: list[Component] = []
        for idx in sorted(self.sextet_enabled):
            kind = self.component_kind.get(idx, "Sextete")
            imode = self.intensity_mode.get(idx, "free")
            qtreat = self.quad_treatment.get(idx, "1st_order")
            relevant = _relevant_params(kind, imode, qtreat)
            for name in _PARAM_ORDER:
                key = f"s{idx}_{name}"
                if key in values and name not in relevant:
                    fixed[key] = True
            components.append(Component(
                idx=idx, enabled=bool(self.sextet_enabled.get(idx, False)),
                kind=kind, intensity_mode=imode, quad_treatment=qtreat))
        bounds = dict(_GLOBAL_BOUNDS)
        for idx in self.sextet_enabled:
            for name, rng in _PARAM_BOUNDS.items():
                bounds[f"s{idx}_{name}"] = rng
        return FitState(
            velocity=velocity, y_data=y_data, sigma_data=sigma_data,
            values=values, fixed=fixed, bounds=bounds, components=components,
            constraints=list(self.constraints),
            likelihood=self.likelihood, robust_loss=self.robust_loss,
            line_profile=self.line_profile,
            voigt_sigma=float(values.get("voigt_sigma", 0.05)),
            propagate_calib=self.propagate_calib, global_opt=self.global_opt,
            fit_velocity=self.fit_velocity, fit_center=self.fit_center,
            fit_sigma=self.fit_sigma, absorber_model=self.absorber_model,
            multistart_n=self.multistart_n,
            counts=counts, norm_factor=norm_factor)

    def active_param_keys(self) -> list[str]:
        """Claves de modelo de los componentes activos (más baseline/slope)."""
        keys = ["baseline", "slope"]
        for idx in sorted(self.sextet_enabled):
            if not self.sextet_enabled.get(idx):
                continue
            kind = self.component_kind.get(idx, "Sextete")
            imode = self.intensity_mode.get(idx, "free")
            qtreat = self.quad_treatment.get(idx, "1st_order")
            relevant = _relevant_params(kind, imode, qtreat)
            for name in _ACTIVE_PARAM_ORDER:
                key = f"s{idx}_{name}"
                if key in self.vars and name in relevant:
                    keys.append(key)
        return keys

    def to_model_state_dict(self) -> dict:
        """Bloque ``model_state`` del session_payload (mismo formato que la GUI)."""
        return {
            "vars": dict(self.vars),
            "fixed": dict(self.fixed),
            "sextet_enabled": {str(k): bool(v) for k, v in self.sextet_enabled.items()},
            "component_kind": {str(k): v for k, v in self.component_kind.items()},
            "intensity_mode": {str(k): v for k, v in self.intensity_mode.items()},
            "quad_treatment": {str(k): v for k, v in self.quad_treatment.items()},
            "fit_velocity": self.fit_velocity,
            "fit_center": self.fit_center,
            "fit_sigma": self.fit_sigma,
            "fit_mode": "discrete",
            "line_profile": self.line_profile,
            "likelihood": self.likelihood,
            "robust_loss": self.robust_loss,
            "propagate_calib": self.propagate_calib,
            "global_opt": self.global_opt,
            "absorber_model": self.absorber_model,
            "multistart_n": self.multistart_n,
            "n_components": self.n_components,
            "constraints": list(self.constraints),
        }


@dataclass
class LoadedSpectrum:
    path: Path
    counts: np.ndarray
    center: float
    folded: np.ndarray
    y_data: np.ndarray
    sigma: np.ndarray
    norm_factor: float


class HeadlessSession:
    """Orquestador de ajuste sin GUI: cargar → doblar → ajustar → sesión.

    Reemplaza el uso de ``MossbauerApp`` como motor headless en el CLI y los
    tests por lotes.
    """

    def __init__(self, model: ModelState | None = None):
        self.model = model if model is not None else ModelState.defaults()
        self.spectrum: LoadedSpectrum | None = None
        self.calibration_info: dict | None = None
        self.last_fit_free_keys: list[str] = []
        self.last_fit_cov = None
        self.last_fit_param_errors: dict[str, float] = {}
        self.last_fit_stats: dict[str, float] = {}
        self.last_fit_correlations: dict = {}

    def load_ws5(self, path, *, vmax: float | None = None) -> None:
        """Carga un espectro, detecta su centro y lo dobla (espejo de load_ws5+refold)."""
        path = Path(path)
        counts = read_ws5_counts(path)
        center = read_normos_folding_point(path)
        if center is None:
            half = 0.5 * counts.size
            center = find_best_integer_or_half_center(
                counts, max(1.5, half - 20.0), min(counts.size - 0.5, half + 20.0))
        folded, sigma, y, norm = fold_and_normalize(counts, center, _EDGE_TRIM)
        self.spectrum = LoadedSpectrum(
            path=path, counts=counts, center=float(center),
            folded=folded, y_data=y, sigma=sigma, norm_factor=norm)
        self.model.vars["center"] = float(center)
        if vmax is not None:
            self.model.vars["vmax"] = float(vmax)

    def apply_template_model_state(self, state: dict) -> None:
        self.model.apply_template(state)

    def set_vmax(self, vmax: float) -> None:
        self.model.vars["vmax"] = float(vmax)

    def _velocity(self) -> np.ndarray:
        """Eje de velocidad con el mismo recorte de borde que el folding (espejo Qt)."""
        sp = self._require_spectrum()
        vmax = float(self.model.vars.get("vmax", 12.0))
        return velocity_axis(sp.counts.size, vmax, sp.y_data.size, _EDGE_TRIM)

    def build_fit_state(self) -> FitState:
        sp = self._require_spectrum()
        return self.model.build_fit_state(
            velocity=self._velocity(), y_data=sp.y_data, sigma_data=sp.sigma,
            counts=sp.counts, norm_factor=sp.norm_factor)

    def run_fit(self) -> dict:
        """Ejecuta el ajuste discreto y devuelve {values, errors, stats, free_keys}."""
        state = self.build_fit_state()
        result = fit_discrete(state)
        for k, v in result.values.items():
            if k in self.model.vars:
                self.model.vars[k] = float(v)
        self.last_fit_free_keys = list(result.free_keys)
        self.last_fit_cov = result.cov
        self.last_fit_param_errors = dict(result.errors)
        stats = dict(result.stats)
        stats["likelihood"] = self.model.likelihood
        stats["robust_loss"] = self.model.robust_loss
        stats["n_starts"] = float(result.n_starts)
        self.last_fit_stats = stats
        self.last_fit_correlations = dict(result.correlations)
        active = self.model.active_param_keys()
        return {
            "values": {k: float(self.model.vars[k]) for k in active},
            "errors": dict(result.errors),
            "stats": stats,
            "free_keys": list(result.free_keys),
        }

    def session_payload(self) -> dict:
        """Sesión completa, mismo esquema que la GUI (más ``last_fit``)."""
        sp = self.spectrum
        return {
            "version": 1,
            "program": "core.session",
            "file_path": str(sp.path) if sp else None,
            "file_name": sp.path.name if sp else None,
            "counts": sp.counts.tolist() if sp is not None else None,
            "calibration": self.calibration_info,
            "state_and_parameters_text": "",
            "model_state": self.model.to_model_state_dict(),
            "last_fit": {
                "free_keys": list(self.last_fit_free_keys),
                "covariance": self.last_fit_cov.tolist() if self.last_fit_cov is not None else None,
                "parameter_errors": dict(self.last_fit_param_errors),
                "fit_statistics": dict(self.last_fit_stats),
                "correlations": dict(self.last_fit_correlations),
                "info_text": "",
            },
        }

    def batch_fit_sequential(self, files, metadata_list=None,
                             progress_cb=None) -> list[dict]:
        """Ajusta una serie de espectros con warm-start (espejo de batch_fit_sequential).

        Para cada fichero: lo carga, restaura los valores del modelo anterior
        (sin ``center``/``vmax``, que son por-espectro/calibración) y ajusta. Los
        fallos se registran y no detienen la serie.
        """
        files = [Path(f) for f in files]
        if metadata_list is None:
            metadata_list = [None] * len(files)
        results: list[dict] = []
        for i, (file_path, meta) in enumerate(zip(files, metadata_list), 1):
            if progress_cb is not None:
                try:
                    progress_cb(i, len(files), file_path.name)
                except Exception:
                    pass
            saved = {k: self.model.vars[k] for k in self.model.active_param_keys()}
            if "voigt_sigma" in self.model.vars:
                saved["voigt_sigma"] = self.model.vars["voigt_sigma"]
            row = {"file": file_path.name, "metadata": meta,
                   "status": "failed", "values": {}, "errors": {}, "stats": {}}
            try:
                self.load_ws5(file_path)
                for k, v in saved.items():
                    if k in self.model.vars:
                        self.model.vars[k] = v
                fit_result = self.run_fit()
                row.update({
                    "status": "ok",
                    "values": fit_result["values"],
                    "errors": fit_result["errors"],
                    "stats": fit_result["stats"],
                })
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            results.append(row)
        return results

    def _require_spectrum(self) -> LoadedSpectrum:
        if self.spectrum is None:
            raise RuntimeError("No hay espectro cargado: llama a load_ws5() primero.")
        return self.spectrum
