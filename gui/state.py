"""Estado ligero compartido por la GUI Qt.

Este módulo empieza a separar el estado serializable de la aplicación de los
widgets. ``FileState`` sigue siendo el estado runtime mutable usado por la GUI;
las clases ``*State`` inferiores son snapshots más formales para guardar/cargar
sesiones y para ir reduciendo progresivamente el acoplamiento widget→lógica.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from core.param_overrides import effective_distribution_specs as _eff_dist_specs, effective_fit_init_specs as _eff_fi_specs
_DSPEC = _eff_dist_specs()
_FI = _eff_fi_specs()


@dataclass
class FileState:
    """Estado runtime del espectro cargado en la GUI."""

    path: Path | None = None
    counts: np.ndarray | None = None
    folded: np.ndarray | None = None
    sigma: np.ndarray | None = None
    norm_factor: float = 1.0
    center: float | None = None
    velocity: np.ndarray | None = None
    y_data: np.ndarray | None = None


@dataclass
class ComparisonSpectrum:
    """Espectro cargado solo para comparación visual (sin ajuste)."""
    path: Path
    velocity: np.ndarray
    y_data: np.ndarray
    label: str


@dataclass
class RuntimeResultState:
    """Resultados runtime no serializables de la ventana.

    Agrupa el último ajuste discreto, el último ajuste de distribución y la
    fuente de incertidumbres mostrada en informes/paneles. No forma parte del
    JSON de sesión: se recalcula al ajustar.
    """

    fit_result: Any | None = None
    distribution_result: Any | None = None
    gui_result: Any | None = None
    active_mode: str | None = None
    error_source: str = "covarianza (1σ)"

    def clear(self) -> None:
        self.fit_result = None
        self.distribution_result = None
        self.gui_result = None
        self.active_mode = None
        self.error_source = "covarianza (1σ)"

    def clear_fit(self) -> None:
        """Alias explícito para borrar salidas de ajuste runtime."""
        self.clear()

    def set_discrete_fit(
        self,
        result: Any,
        *,
        error_source: str = "covarianza (1σ)",
        gui_result: Any | None = None,
    ) -> None:
        self.fit_result = result
        self.distribution_result = None
        self.gui_result = gui_result
        self.active_mode = "discrete"
        self.error_source = error_source

    def set_distribution_fit(self, result: Any, *, gui_result: Any | None = None) -> None:
        self.distribution_result = result
        self.gui_result = gui_result
        self.active_mode = "distribution"

    def set_error_source(self, error_source: str) -> None:
        self.error_source = str(error_source)

    def update_discrete_errors(self, errors: dict[str, Any]) -> None:
        if self.fit_result is not None:
            self.fit_result.errors.update(errors)

    def replace_discrete_fit(
        self,
        result: Any,
        *,
        errors: dict[str, Any] | None = None,
        error_source: str | None = None,
    ) -> None:
        self.fit_result = result
        self.distribution_result = None
        self.active_mode = "discrete"
        if errors:
            self.fit_result.errors.update(errors)
        if error_source is not None:
            self.set_error_source(error_source)


@dataclass(frozen=True)
class CalibrationViewState:
    """Snapshot del panel de calibración independiente de widgets."""

    vmax: float
    center: float
    baseline: float
    slope: float
    voigt_sigma: float
    sat_scale: float
    line_profile: str = "Lorentziana"
    absorber_model: str = "thin"
    fit_velocity: bool = False
    fit_center: bool = False
    fit_sigma: bool = False
    fixed: dict[str, bool] = field(default_factory=dict)

    def value(self, name: str, default: float = 0.0) -> float:
        return float(getattr(self, name, default))

    def is_fixed(self, name: str) -> bool:
        return bool(self.fixed.get(name, False))

    def values_dict(self) -> dict[str, float]:
        return {
            "vmax": self.vmax,
            "center": self.center,
            "baseline": self.baseline,
            "slope": self.slope,
            "voigt_sigma": self.voigt_sigma,
            "sat_scale": self.sat_scale,
        }


@dataclass(frozen=True)
class ComponentViewState:
    """Snapshot de una componente de la GUI independiente de sus widgets.

    ``values`` y ``fixed`` usan nombres canónicos sin prefijo (``delta``,
    ``gamma1``...). Los métodos ``prefixed_*`` devuelven el formato plano
    histórico usado por ``core.session.ModelState``.
    """

    idx: int
    enabled: bool
    kind: str
    intensity_mode: str
    quad_treatment: str
    values: dict[str, float] = field(default_factory=dict)
    fixed: dict[str, bool] = field(default_factory=dict)

    def value(self, name: str, default: float = 0.0) -> float:
        return float(self.values.get(name, default))

    def is_fixed(self, name: str) -> bool:
        return bool(self.fixed.get(name, False))

    def prefixed_values(self) -> dict[str, float]:
        prefix = f"s{self.idx}_"
        return {prefix + k: float(v) for k, v in self.values.items()}

    def prefixed_fixed(self) -> dict[str, bool]:
        prefix = f"s{self.idx}_"
        return {prefix + k: bool(v) for k, v in self.fixed.items()}


@dataclass(frozen=True)
class SpectrumState:
    """Snapshot serializable del espectro de entrada.

    De momento conserva el formato histórico de sesión: ruta, nombre y cuentas
    embebidas opcionales. Los arrays calculados (folded/sigma/velocity/y_data)
    se reconstruyen al cargar para no duplicar estado derivado.
    """

    path: Path | None = None
    file_name: str | None = None
    counts: tuple[float, ...] | None = None

    @classmethod
    def from_file_state(cls, file: FileState) -> "SpectrumState":
        return cls(
            path=file.path,
            file_name=file.path.name if file.path else None,
            counts=(
                tuple(float(x) for x in np.asarray(file.counts, dtype=float))
                if file.counts is not None else None
            ),
        )

    def to_session_fragment(self) -> dict[str, Any]:
        return {
            "file_path": str(self.path) if self.path else None,
            "file_name": self.file_name,
            "counts": list(self.counts) if self.counts is not None else None,
        }


@dataclass(frozen=True)
class CalibrationState:
    """Snapshot de la calibración activa de la GUI."""

    info: dict[str, Any] | None = None

    def to_session_fragment(self) -> dict[str, Any] | None:
        return dict(self.info) if isinstance(self.info, dict) else None


@dataclass(frozen=True)
class FitOptionsState:
    """Opciones globales de ajuste que no pertenecen a un componente."""

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

    @classmethod
    def from_model_state(cls, state: dict[str, Any]) -> "FitOptionsState":
        return cls(
            line_profile=str(state.get("line_profile", "Lorentziana")),
            likelihood=str(state.get("likelihood", "gauss")),
            robust_loss=str(state.get("robust_loss", "linear")),
            absorber_model=str(state.get("absorber_model", "thin")),
            propagate_calib=bool(state.get("propagate_calib", False)),
            global_opt=bool(state.get("global_opt", False)),
            fit_velocity=bool(state.get("fit_velocity", False)),
            fit_center=bool(state.get("fit_center", False)),
            fit_sigma=bool(state.get("fit_sigma", False)),
            multistart_n=max(0, min(int(_FI["multistart_n_max"].default), int(state.get("multistart_n", 8)))),
        )

    def apply_to_model_state(self, model_state) -> None:
        """Aplica estas opciones a un ``core.session.ModelState``."""
        model_state.line_profile = self.line_profile
        model_state.likelihood = self.likelihood
        model_state.robust_loss = self.robust_loss
        model_state.absorber_model = self.absorber_model
        model_state.propagate_calib = bool(self.propagate_calib)
        model_state.global_opt = bool(self.global_opt)
        model_state.fit_velocity = bool(self.fit_velocity)
        model_state.fit_center = bool(self.fit_center)
        model_state.fit_sigma = bool(self.fit_sigma)
        model_state.multistart_n = self.multistart_n

    def to_model_state_fragment(self) -> dict[str, Any]:
        return {
            "line_profile": self.line_profile,
            "likelihood": self.likelihood,
            "robust_loss": self.robust_loss,
            "absorber_model": self.absorber_model,
            "propagate_calib": bool(self.propagate_calib),
            "global_opt": bool(self.global_opt),
            "fit_velocity": bool(self.fit_velocity),
            "fit_center": bool(self.fit_center),
            "fit_sigma": bool(self.fit_sigma),
            "multistart_n": self.multistart_n,
        }


@dataclass(frozen=True)
class DistributionViewState:
    """Snapshot del panel de distribución P(BHF) / P(ΔEQ)."""

    use_sharp: bool = False
    shape: str = "Histograma"
    reg_mode: str = "tikhonov"
    fixed_distribution_path: Path | None = None
    variable: str = "BHF"  # "BHF" / "ΔEQ"
    delta:     float = _DSPEC["delta"].default
    quad:      float = _DSPEC["quad"].default
    fixed_bhf: float = _DSPEC["fixed_bhf"].default
    gamma:     float = _DSPEC["gamma"].default
    bmin:      float = _DSPEC["bmin"].default
    bmax:      float = _DSPEC["bmax"].default
    nbins:     int   = int(_DSPEC["nbins"].default)
    log_alpha: float = _DSPEC["log_alpha"].default
    # Correlación δ(H)/ΔEQ(H) (mm/s·T⁻¹) y nº de gaussianas del VBF (opt-in).
    delta_slope: float = 0.0
    quad_slope:  float = 0.0
    vbf_n_components: int = 2
    fixed: dict[str, bool] = field(default_factory=dict)

    @property
    def alpha(self) -> float:
        return 10.0 ** float(self.log_alpha)

    def is_fixed(self, name: str) -> bool:
        return bool(self.fixed.get(name, False))

    @classmethod
    def from_model_state(cls, state: dict[str, Any]) -> "DistributionViewState":
        fixed_path = state.get("fixed_distribution_path")
        return cls(
            use_sharp=bool(state.get("dist_use_sharp", False)),
            shape=str(state.get("dist_shape", "Histograma")),
            reg_mode=str(state.get("dist_reg_mode", "tikhonov")),
            fixed_distribution_path=Path(fixed_path) if fixed_path else None,
            variable=str(state.get("dist_variable", "BHF")),
        )

    def to_model_state_fragment(self) -> dict[str, Any]:
        return {
            "dist_use_sharp": bool(self.use_sharp),
            "dist_shape": self.shape,
            "dist_reg_mode": self.reg_mode,
            "fixed_distribution_path": (
                str(self.fixed_distribution_path)
                if self.fixed_distribution_path is not None else None
            ),
            "dist_variable": self.variable,
        }


@dataclass(frozen=True)
class PlotViewState:
    """Opciones de visualización que forman parte de la sesión."""

    show_residual: bool = True
    show_legend: bool = True
    show_component_fill: bool = True

    @classmethod
    def from_model_state(cls, state: dict[str, Any]) -> "PlotViewState":
        return cls(
            show_residual=bool(state.get("show_residual", True)),
            show_legend=bool(state.get("show_legend", True)),
            show_component_fill=bool(state.get("show_component_fill", True)),
        )

    def to_model_state_fragment(self) -> dict[str, Any]:
        return {
            "show_residual": bool(self.show_residual),
            "show_legend": bool(self.show_legend),
            "show_component_fill": bool(self.show_component_fill),
        }


@dataclass(frozen=True)
class UiActionState:
    """Snapshot runtime de acciones/controles globales de la ventana."""

    n_components: int = 1
    plot: PlotViewState = field(default_factory=PlotViewState)

    @property
    def show_residual(self) -> bool:
        return self.plot.show_residual

    @property
    def show_legend(self) -> bool:
        return self.plot.show_legend

    @property
    def show_component_fill(self) -> bool:
        return self.plot.show_component_fill

    def to_model_state_fragment(self) -> dict[str, Any]:
        return {
            "n_components": int(self.n_components),
            **self.plot.to_model_state_fragment(),
        }


@dataclass(frozen=True)
class UiPreferencesState:
    """Preferencias de interfaz persistidas en ``settings.json``.

    No son estado científico de la sesión: tema, estilo de plot, recientes,
    layout y preferencias visuales globales.
    """

    plot_style: str = "modern"
    color_theme: str = "blue"
    show_residual: bool = True
    recent_files: tuple[str, ...] = ()
    layout_preset: str = "Estándar"
    custom_layouts: dict[str, dict[str, Any]] = field(default_factory=dict)
    ui_language: str | None = None
    qt_style: str | None = None
    custom_shortcuts: dict[str, str] = field(default_factory=dict)
    multistart_n: int = 8

    @classmethod
    def from_settings_dict(cls, data: dict[str, Any]) -> "UiPreferencesState":
        recent = data.get("recent_files")
        custom = data.get("custom_layouts")
        cs = data.get("custom_shortcuts")
        return cls(
            plot_style=str(data.get("plot_style", "modern")),
            color_theme=str(data.get("color_theme", "blue")),
            show_residual=bool(data.get("show_residual", True)),
            recent_files=tuple(str(p) for p in recent) if isinstance(recent, list) else (),
            layout_preset=str(data.get("layout_preset", "Estándar") or "Estándar"),
            custom_layouts={
                str(k): dict(v) for k, v in (custom or {}).items()
                if isinstance(v, dict)
            } if isinstance(custom, dict) else {},
            ui_language=(str(data.get("ui_language")) if data.get("ui_language") else None),
            qt_style=(str(data.get("qt_style")) if data.get("qt_style") else None),
            custom_shortcuts={
                str(k): str(v) for k, v in cs.items() if isinstance(v, str)
            } if isinstance(cs, dict) else {},
            multistart_n=int(data.get("multistart_n", 8)),
        )

    def to_settings_dict(self, *, base: dict[str, Any] | None = None) -> dict[str, Any]:
        out = dict(base or {})
        out.update({
            "plot_style": self.plot_style,
            "color_theme": self.color_theme,
            "show_residual": bool(self.show_residual),
            "recent_files": list(self.recent_files),
            "layout_preset": self.layout_preset,
            "custom_layouts": dict(self.custom_layouts),
            "multistart_n": self.multistart_n,
        })
        if self.ui_language:
            out["ui_language"] = self.ui_language
        if self.qt_style:
            out["qt_style"] = self.qt_style
        if self.custom_shortcuts:
            out["custom_shortcuts"] = dict(self.custom_shortcuts)
        return out


@dataclass(frozen=True)
class ProjectState:
    """Snapshot serializable de alto nivel de una sesión GUI.

    Es una envoltura formal alrededor del payload histórico. La intención es que
    nuevas piezas de la GUI construyan/consuman ``ProjectState`` en vez de leer
    directamente todos los widgets. El método ``to_session_payload`` mantiene la
    compatibilidad exacta con los JSON existentes.
    """

    spectrum: SpectrumState = field(default_factory=SpectrumState)
    calibration: CalibrationState = field(default_factory=CalibrationState)
    model_state: dict[str, Any] = field(default_factory=dict)
    fit_options: FitOptionsState = field(default_factory=FitOptionsState)
    distribution: DistributionViewState = field(default_factory=DistributionViewState)
    plot: PlotViewState = field(default_factory=PlotViewState)
    version: int = 1
    program: str = "mossbauer_qt.py"

    def to_session_payload(self) -> dict[str, Any]:
        model_state = dict(self.model_state)
        model_state.update(self.fit_options.to_model_state_fragment())
        model_state.update(self.distribution.to_model_state_fragment())
        model_state.update(self.plot.to_model_state_fragment())
        payload = {
            "version": int(self.version),
            "program": self.program,
            **self.spectrum.to_session_fragment(),
            "calibration": self.calibration.to_session_fragment(),
            "model_state": model_state,
        }
        return payload

    @classmethod
    def from_session_payload(cls, payload: dict[str, Any]) -> "ProjectState":
        file_path = payload.get("file_path")
        counts = payload.get("counts")
        return cls(
            version=int(payload.get("version", 1)),
            program=str(payload.get("program", "mossbauer_qt.py")),
            spectrum=SpectrumState(
                path=Path(file_path) if file_path else None,
                file_name=payload.get("file_name"),
                counts=tuple(float(x) for x in counts) if counts is not None else None,
            ),
            calibration=CalibrationState(
                payload.get("calibration") if isinstance(payload.get("calibration"), dict) else None
            ),
            model_state=dict(payload.get("model_state") or {}),
            fit_options=FitOptionsState.from_model_state(
                dict(payload.get("model_state") or {})
            ),
            distribution=DistributionViewState.from_model_state(
                dict(payload.get("model_state") or {})
            ),
            plot=PlotViewState.from_model_state(dict(payload.get("model_state") or {})),
        )
