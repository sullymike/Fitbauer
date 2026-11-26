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
    EDGE_TRIM_DEFAULT,
    canonical_fold_mode,
    channel_velocity_axis,
    is_pair_averaged,
    geometry_effect_amplitude,
    fold_and_normalize,
)
from core.spectrum_import import ImportHints
from mossbauer_i18n import tr
from core.params import (
    ACTIVE_PARAM_ORDER as _ACTIVE_PARAM_ORDER,
    COMPONENT_KINDS as _COMPONENT_KINDS,
    COMPONENT_FIT_BOUNDS as _PARAM_BOUNDS,
    COMPONENT_SOFT_BOUNDS as _SOFT_BOUNDS,
    GLOBAL_FIT_BOUNDS as _GLOBAL_BOUNDS,
    INTENSITY_MODES as _INTENSITY_MODES_TUPLE,
    PARAM_ORDER as _PARAM_ORDER,
    QUAD_TREATMENTS as _QUAD_TREATMENTS_TUPLE,
    BHF_DEFAULT_T,
    component_defaults as _component_defaults,
    relevant_params as _relevant_params,
)

# Recorte MÍNIMO de borde del espectro doblado. 0 = se conservan todos los
# canales (como NORMOS) y el recorte real lo decide `core.folding` de forma
# adaptativa, solo si el extremo es un canal muerto. Fuente única con la GUI Qt
# (``mossbauer_qt._edge_trim``).
_EDGE_TRIM = EDGE_TRIM_DEFAULT
MAX_COMPONENTS_DEFAULT = 3

_KINDS = set(_COMPONENT_KINDS)
_INTENSITY_MODES = set(_INTENSITY_MODES_TUPLE)
_QUAD_TREATMENTS = set(_QUAD_TREATMENTS_TUPLE)


def clean_user_bounds(raw) -> dict[str, tuple[float | None, float | None]]:
    """Normaliza las cotas propias de una sesión o plantilla.

    Acepta ``{"s1_gamma1": [mín, máx]}`` con ``None``/``null`` en el lado no
    dado; descarta entradas sin ningún lado o mal formadas y ordena mín ≤ máx.
    """
    out: dict[str, tuple[float | None, float | None]] = {}
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        if not isinstance(val, (list, tuple)) or len(val) != 2:
            continue
        try:
            lo = None if val[0] is None else float(val[0])
            hi = None if val[1] is None else float(val[1])
        except (TypeError, ValueError):
            continue
        if lo is None and hi is None:
            continue
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo
        out[str(key)] = (lo, hi)
    return out


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
    # Convenio de razones de intensidad entre líneas: "depth" (histórico) o
    # "area" (físico / D13-D23 de NORMOS). Ver core.physics.
    intensity_convention: str = "depth"
    # Relajación polarizada: "blume" (físico) o "normos". Ver core.physics.
    relax_convention: str = "blume"
    # Patrón de posiciones del sexteto: "normos" (defecto desde v5.2.5) o
    # "legacy" (el histórico de Fitbauer; "alpha_fe" es su alias).
    sextet_pattern: str = "normos"
    drive_form: str = "triangular"      # "triangular" (aceleración cte) / "sine"
    # Plegado de las cuentas por canal (core.folding.FOLD_MODES) y sentido del
    # eje de velocidad (equipos que barren de + a −).
    fold_mode: str = "fold"
    reverse_velocity: bool = False
    propagate_calib: bool = False
    global_opt: bool = False
    fit_velocity: bool = False
    fit_center: bool = False
    fit_sigma: bool = False
    multistart_n: int = 8
    channel_sub: int = 1
    # "Líneas sueltas": amplía los límites de delta de los componentes a
    # ±(vmax+2) mm/s para usar singletes como líneas Lorentzianas libres en
    # cualquier posición del espectro (banco NORMOS §6.5). Off por defecto:
    # los límites físicos de δ de ⁵⁷Fe son los correctos para ajustes normales.
    wide_delta: bool = False
    # Escalado global automático (DE) si el multistart acaba con χ²red alto.
    # Activo por defecto en la capa de sesión: el banco NORMOS §6.10 midió
    # ~40 % de fallos del multistart local en multisitio solapado y una
    # recuperación del 100 % con la pasada DE.
    auto_global: bool = True
    #: "explore" (multiarranque, por defecto) o "local" (un único ajuste).
    fit_strategy: str = "explore"
    #: Paso máximo por iteración en local (fracción del rango; 0 = sin límite).
    max_step_frac: float = 0.0
    n_components: int = 1
    #: Cotas de ajuste propias por parámetro de componente:
    #: ``{"s2_gamma1": [mín|None, máx|None]}``. Sustituyen a las generales
    #: (``COMPONENT_FIT_BOUNDS``) solo en el lado dado; vacío = las generales.
    user_bounds: dict = field(default_factory=dict)
    #: Cotas generales por nombre de parámetro (``{"delta": (-5, 3)}``) que
    #: sustituyen a ``COMPONENT_FIT_BOUNDS`` en todas las componentes. La GUI
    #: las rellena con lo cambiado en Vista › Límites de parámetros; vacío =
    #: las del código. No se guardan en la sesión: son configuración.
    general_bounds: dict = field(default_factory=dict)

    @classmethod
    def defaults(cls, n_components: int = MAX_COMPONENTS_DEFAULT) -> "ModelState":
        vars_: dict[str, float] = {
            "vmax": 12.0, "center": 256.0, "baseline": 1.0, "slope": 0.0,
            "voigt_sigma": 0.05, "sat_scale": 1.0,
            # curv/src_fwhm: fijos a su valor neutro (curvatura nula; anchura
            # de fuente natural de 57Fe) salvo que el usuario los libere.
            "curv": 0.0, "src_fwhm": 0.097,
            # Fracción resonante de la fuente (FSO de NORMOS): neutra y fija.
            "src_frac": 1.0,
            # Fondo cúbico/cuártico (BKG(4)/BKG(5) de NORMOS): neutro y fijo.
            "curv3": 0.0, "curv4": 0.0,
            # Asimetría de línea (AKS de NORMOS-SITE): neutra y fija.
            "line_asym": 0.0,
        }
        fixed: dict[str, bool] = {
            "vmax": True, "center": True, "baseline": False, "slope": False,
            "voigt_sigma": False, "sat_scale": True,
            "curv": True, "src_fwhm": True, "src_frac": True,
            "curv3": True, "curv4": True,
            "line_asym": True,
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
        def _per_component(value) -> dict:
            # Sesiones antiguas guardaban estos mapas como listas
            # ([v1, v2, v3], índice 0 = componente 1) en vez de dicts.
            if isinstance(value, (list, tuple)):
                return {i + 1: v for i, v in enumerate(value)}
            return dict(value) if isinstance(value, dict) else {}

        tvars = dict(state.get("vars", {}))
        tvars.pop("center", None)
        for k, v in tvars.items():
            self.vars[k] = float(v)
        for k, v in state.get("fixed", {}).items():
            self.fixed[k] = bool(v)
        for k, v in _per_component(state.get("sextet_enabled", {})).items():
            self.sextet_enabled[int(k)] = bool(v)
        for k, v in _per_component(state.get("component_kind", {})).items():
            if v in _KINDS:
                self.component_kind[int(k)] = v
        for k, v in _per_component(state.get("intensity_mode", {})).items():
            if v in _INTENSITY_MODES:
                self.intensity_mode[int(k)] = v
        for k, v in _per_component(state.get("quad_treatment", {})).items():
            if v in _QUAD_TREATMENTS:
                self.quad_treatment[int(k)] = v
        for flag in ("fit_velocity", "fit_center", "fit_sigma",
                     "propagate_calib", "global_opt", "wide_delta",
                     "auto_global"):
            if flag in state:
                setattr(self, flag, bool(state[flag]))
        if "multistart_n" in state:
            self.multistart_n = max(0, min(10, int(state["multistart_n"])))
        if state.get("fit_strategy") in ("explore", "local"):
            self.fit_strategy = str(state["fit_strategy"])
        if state.get("max_step_frac") is not None:
            self.max_step_frac = max(0.0, min(1.0, float(state["max_step_frac"])))
        if "channel_sub" in state:
            self.channel_sub = max(1, min(8, int(state["channel_sub"])))
        for skey in ("line_profile", "likelihood", "robust_loss", "absorber_model",
                     "intensity_convention", "relax_convention", "sextet_pattern",
                     "drive_form"):
            if skey in state:
                setattr(self, skey, str(state[skey]))
        if "fold_mode" in state:
            self.fold_mode = canonical_fold_mode(state["fold_mode"])
        if "reverse_velocity" in state:
            self.reverse_velocity = bool(state["reverse_velocity"])
        if "constraints" in state:
            self.constraints = list(state["constraints"])
        if "n_components" in state:
            self.n_components = int(state["n_components"])
        if "bounds_user" in state:
            self.user_bounds = clean_user_bounds(state["bounds_user"])
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
        soft_bounds: dict[str, tuple[float, float]] = {}
        for idx in self.sextet_enabled:
            for name, rng in _PARAM_BOUNDS.items():
                bounds[f"s{idx}_{name}"] = rng
            for name, rng in _SOFT_BOUNDS.items():
                soft_bounds[f"s{idx}_{name}"] = rng
        if self.absorber_model == "transmission":
            # En transmisión "depth" es profundidad ÓPTICA (τ puede superar 1):
            # se relaja el límite superior solo en este modo.
            for idx in self.sextet_enabled:
                bounds[f"s{idx}_depth"] = (0.0, 5.0)
                soft_bounds.pop(f"s{idx}_depth", None)
        if self.wide_delta:
            vmax_abs = abs(float(self.vars.get("vmax", 12.0)))
            for idx in self.sextet_enabled:
                bounds[f"s{idx}_delta"] = (-(vmax_abs + 2.0), vmax_abs + 2.0)
                # ΔEQ acompaña a δ: un doblete con líneas dentro de ±vmax
                # puede tener |ΔEQ| hasta ~2·vmax (banco NORMOS-2, caso
                # K5_dob_q5: SITE admite ΔEQ=5 y la cota clásica ±4 degeneraba
                # el ajuste).
                bounds[f"s{idx}_quad"] = (-2.0 * (vmax_abs + 2.0),
                                          2.0 * (vmax_abs + 2.0))
        for name, (g_lo, g_hi) in (self.general_bounds or {}).items():
            # Globales (vmax, baseline…): misma clave, sin prefijo de componente.
            if name in _GLOBAL_BOUNDS:
                lo, hi = bounds[name]
                bounds[name] = (lo if g_lo is None else float(g_lo),
                                hi if g_hi is None else float(g_hi))
        for idx in self.sextet_enabled:
            for name, (g_lo, g_hi) in (self.general_bounds or {}).items():
                key = f"s{idx}_{name}"
                if key not in bounds:
                    continue
                lo, hi = bounds[key]
                bounds[key] = (lo if g_lo is None else float(g_lo),
                               hi if g_hi is None else float(g_hi))
                soft_bounds.pop(key, None)
        # Cotas propias del usuario (por componente y parámetro): sustituyen
        # a las generales en el lado dado y son duras (sin cota blanda).
        for key, (u_lo, u_hi) in clean_user_bounds(self.user_bounds).items():
            if key not in values:
                continue
            lo, hi = bounds.get(key, (-np.inf, np.inf))
            bounds[key] = (lo if u_lo is None else float(u_lo),
                           hi if u_hi is None else float(u_hi))
            soft_bounds.pop(key, None)
        # Límites del centro de doblado según el nº de canales real (N/2 ± el
        # margen ajustable; en seno, la fase ~N/4 con su propio rango). Sin
        # esto, fit_center caía al default (250, 263) del motor, válido solo
        # para 512 canales.
        if counts is not None:
            n = int(np.asarray(counts).size)
            if n > 0:
                from core.folding import fold_center_window
                bounds["center"] = fold_center_window(n, drive_form=self.drive_form)
        return FitState(
            velocity=velocity, y_data=y_data, sigma_data=sigma_data,
            values=values, fixed=fixed, bounds=bounds, soft_bounds=soft_bounds,
            components=components, constraints=list(self.constraints),
            likelihood=self.likelihood, robust_loss=self.robust_loss,
            line_profile=self.line_profile,
            voigt_sigma=float(values.get("voigt_sigma", 0.05)),
            propagate_calib=self.propagate_calib, global_opt=self.global_opt,
            fit_velocity=self.fit_velocity, fit_center=self.fit_center,
            fit_sigma=self.fit_sigma, absorber_model=self.absorber_model,
            intensity_convention=self.intensity_convention,
            relax_convention=self.relax_convention,
            sextet_pattern=self.sextet_pattern,
            drive_form=self.drive_form,
            fold_mode=canonical_fold_mode(self.fold_mode),
            reverse_velocity=bool(self.reverse_velocity),
            multistart_n=self.multistart_n,
            channel_sub=max(1, int(self.channel_sub)),
            auto_global=bool(self.auto_global),
            fit_strategy=self.fit_strategy,
            max_step_frac=float(self.max_step_frac),
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
            "intensity_convention": self.intensity_convention,
            "relax_convention": self.relax_convention,
            "sextet_pattern": self.sextet_pattern,
            "drive_form": self.drive_form,
            "fold_mode": self.fold_mode,
            "reverse_velocity": bool(self.reverse_velocity),
            "multistart_n": self.multistart_n,
            "channel_sub": self.channel_sub,
            "wide_delta": self.wide_delta,
            "auto_global": self.auto_global,
            "fit_strategy": self.fit_strategy,
            "max_step_frac": float(self.max_step_frac),
            "n_components": self.n_components,
            "constraints": list(self.constraints),
            "bounds_user": {k: [lo, hi] for k, (lo, hi)
                            in clean_user_bounds(self.user_bounds).items()},
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
        #: Diagnóstico del efecto geométrico del último espectro cargado.
        self.geometry_effect: dict = {"amplitude": 0.0, "relative": 0.0}
        self.calibration_info: dict | None = None
        # Equipo opcional (core.instruments): correcciones de lectura, forma
        # de onda/plegado y calibración vigente en la fecha de cada medida.
        self.instrument = None
        self.instrument_library = None
        self.calibration_warning: str | None = None
        self.last_fit_free_keys: list[str] = []
        self.last_fit_cov = None
        self.last_fit_param_errors: dict[str, float] = {}
        self.last_fit_stats: dict[str, float] = {}
        self.last_fit_correlations: dict = {}

    def load_ws5(self, path, *, vmax: float | None = None,
                 hints: ImportHints | None = None) -> None:
        """Carga cuentas por canal y las dobla o no según ``model.fold_mode``.

        Lee cualquier fichero de texto con :mod:`core.spectrum_import`
        (cabecera y pie incluidos; ``hints`` corrige lo deducido). Los ficheros
        con eje de velocidad no se cargan aquí.
        """
        from core.spectrum_loading import (
            Acquisition, open_spectrum, prepare_spectrum)
        path = Path(path)
        if hints is None and self.instrument is not None:
            hints = self.instrument.import_hints
        with_instrument = vmax is None and self.instrument is not None
        opened = open_spectrum(
            path, hints,
            library=self.instrument_library if with_instrument else None,
            instrument=self.instrument.name if with_instrument else None)
        if opened.has_velocity_axis:
            raise ValueError(tr(
                "load.not_channel_counts", name=path.name,
                default="{name} does not contain counts per channel."))
        acquisition = Acquisition(self.model.drive_form,
                                  canonical_fold_mode(self.model.fold_mode),
                                  bool(self.model.reverse_velocity))
        prep = prepare_spectrum(opened.imported.y, acquisition, None,
                                path=path,
                                edge_trim=_EDGE_TRIM)
        self.spectrum = LoadedSpectrum(
            path=path, counts=prep.counts, center=prep.center,
            folded=prep.folded, y_data=prep.y, sigma=prep.sigma, norm_factor=prep.norm)
        self.geometry_effect = self._geometry_diagnostics(prep.counts, prep.center)
        self.model.vars["center"] = prep.center
        if vmax is not None:
            self.model.vars["vmax"] = float(vmax)
        elif with_instrument:
            self._assign_instrument_calibration(opened)

    # ── Equipo ────────────────────────────────────────────────────────────
    def use_instrument(self, name: str, library=None) -> None:
        """Trabaja con un equipo de la biblioteca (opcional).

        Aplica su forma de onda, plegado y sentido al modelo (lo que se fije
        después, p. ej. por línea de comandos, manda) y, al cargar cada
        espectro, sus correcciones de lectura y la calibración vigente en la
        fecha de medida.
        """
        from core.instruments import InstrumentLibrary
        lib = library if library is not None else InstrumentLibrary()
        profile = lib.get(name)
        if profile is None:
            known = ", ".join(lib.names()) or "—"
            raise KeyError(f"instrument '{name}' not found in {lib.root} (known: {known})")
        self.instrument = profile
        self.instrument_library = lib
        self.model.drive_form = profile.drive_form
        self.model.fold_mode = profile.fold_mode
        self.model.reverse_velocity = bool(profile.reverse_velocity)

    def recognize_instrument(self, path, library=None) -> str:
        """Usa el único equipo que reconoce ``path`` (sus criterios de nombre y
        cabecera); devuelve su nombre. ``KeyError`` si ninguno o varios."""
        from core.instruments import InstrumentLibrary
        lib = library if library is not None else InstrumentLibrary()
        found = [p.name for p in lib.recognize(path)]
        if len(found) != 1:
            detail = ("no instrument recognizes it" if not found
                      else "several instruments recognize it: " + ", ".join(found))
            raise KeyError(f"{Path(path).name}: {detail} (library {lib.root})")
        self.use_instrument(found[0], lib)
        return found[0]

    def instrument_calibration(self, path, imported):
        """:class:`~core.instruments.CalibrationChoice` del equipo para un fichero
        (según la regla del equipo: por fecha de medida o la más reciente)."""
        return self.instrument_library.choose_calibration(
            self.instrument.name, imported, path)

    def _assign_instrument_calibration(self, opened) -> None:
        """Calibración del equipo para el fichero abierto (``OpenedSpectrum``):
        su Vmax en el patrón del modelo, o un aviso si no hay ninguna."""
        from core.spectrum_loading import calibration_vmax, missing_calibration_reason
        choice, path, name = opened.choice, opened.path, self.instrument.name
        if opened.calibration is None:
            # Se mantiene la Vmax que hubiera (plantilla o fichero anterior).
            reason = missing_calibration_reason(choice)
            if reason == "none":
                self.calibration_warning = f"{path.name}: '{name}' has no calibrations"
            elif reason == "no_date":
                self.calibration_warning = (
                    f"{path.name}: no measurement date; no calibration of '{name}' assigned")
            else:
                self.calibration_warning = (
                    f"{path.name}: '{name}' has no calibration on or before "
                    f"{choice.date.isoformat()}")
            return
        self.calibration_warning = None
        self.calibration_info = opened.calibration
        self.model.vars["vmax"] = calibration_vmax(opened.calibration,
                                                   self.model.sextet_pattern)

    @staticmethod
    def _geometry_diagnostics(counts: np.ndarray, center: float) -> dict:
        """Efecto geométrico del espectro sin doblar (diagnóstico, no corrección).

        Mismo diagnóstico que NORMOS (``normospr.for``), que lo imprime en su ``.RES``
        como "Geometry effect" y "Geometry effect/Background". Mide la
        modulación de la tasa de cuentas con la POSICIÓN del transductor: es
        antisimétrica respecto al punto de doblado, así que el propio doblado
        la cancela y NO afecta al ajuste. Una amplitud relativa alta (≳1 %)
        delata un problema de geometría del espectrómetro.
        """
        amp = geometry_effect_amplitude(counts, center)
        base = float(np.median(counts)) if counts.size else 0.0
        return {"amplitude": float(amp),
                "relative": float(amp / base) if base else 0.0}

    def apply_template_model_state(self, state: dict) -> None:
        self.model.apply_template(state)

    def set_vmax(self, vmax: float) -> None:
        self.model.vars["vmax"] = float(vmax)

    def _velocity(self) -> np.ndarray:
        """Eje de velocidad con el mismo recorte de borde que el folding (espejo Qt)."""
        sp = self._require_spectrum()
        vmax = float(self.model.vars.get("vmax", 12.0))
        # Al doblar, el recorte de bordes se deduce del nº de puntos (es
        # adaptativo); sin doblar, eje por canal.
        return channel_velocity_axis(
            sp.counts.size, vmax, sp.y_data.size, center=sp.center,
            fold_mode=self.model.fold_mode, drive_form=self.model.drive_form,
            reverse=self.model.reverse_velocity)

    def build_fit_state(self) -> FitState:
        sp = self._require_spectrum()
        return self.model.build_fit_state(
            velocity=self._velocity(), y_data=sp.y_data, sigma_data=sp.sigma,
            counts=sp.counts, norm_factor=sp.norm_factor)

    def run_fit(self) -> dict:
        """Ejecuta el ajuste discreto y devuelve {values, errors, stats, free_keys}."""
        state = self.build_fit_state()
        start_values = dict(state.values)
        result = fit_discrete(state)
        for k, v in result.values.items():
            if k in self.model.vars:
                self.model.vars[k] = float(v)
        # Con fit_center, re-dobla el espectro con el centro ajustado para que
        # y_data/σ/norm de la sesión queden coherentes con el resultado (espejo
        # del comportamiento de la GUI; en seno no se dobla y el centro es fase).
        sp = self.spectrum
        new_center = float(self.model.vars.get("center", 0.0))
        if (self.model.fit_center and sp is not None
                and abs(new_center - float(sp.center)) > 1e-9):
            if not is_pair_averaged(self.model.fold_mode, self.model.drive_form):
                # Sin doblar (seno o dos ramas): basta actualizar el centro
                # para que _velocity() construya el eje con el ajustado.
                self.spectrum = LoadedSpectrum(
                    path=sp.path, counts=sp.counts, center=new_center,
                    folded=sp.folded, y_data=sp.y_data, sigma=sp.sigma,
                    norm_factor=sp.norm_factor)
            else:
                folded, sigma, y, norm = fold_and_normalize(sp.counts, new_center, _EDGE_TRIM)
                self.spectrum = LoadedSpectrum(
                    path=sp.path, counts=sp.counts, center=new_center,
                    folded=folded, y_data=y, sigma=sigma, norm_factor=norm)
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
        values_out = {k: float(self.model.vars[k]) for k in active}
        # Globales de calibración ajustados: antes eran invisibles en la salida
        # (active_param_keys no los incluye) aunque sí iban a la sesión.
        # En un solo barrido el centro no interviene (el motor no lo ajusta).
        single = (self.model.drive_form != "sine"
                  and canonical_fold_mode(self.model.fold_mode) == "single_sweep")
        for flag, key in (("fit_center", "center"), ("fit_velocity", "vmax"),
                          ("fit_sigma", "voigt_sigma")):
            if key == "center" and single:
                continue
            if getattr(self.model, flag, False) and key in self.model.vars:
                values_out[key] = float(self.model.vars[key])
        # Globales opcionales de modelo (saturación/transmisión/curvatura):
        # se reportan cuando participaron en el ajuste.
        for key in ("sat_scale", "curv", "src_fwhm", "src_frac", "curv3",
                    "curv4", "line_asym"):
            if key in self.model.vars and not self.model.fixed.get(key, True):
                values_out[key] = float(self.model.vars[key])
        # Mismo diagnóstico que la ventana de la GUI (core.fit_diagnostics).
        from core.fit_diagnostics import diagnose_discrete, verdict
        checks = diagnose_discrete(
            result, start_values=start_values,
            kinds={c.idx: c.kind for c in state.components if c.enabled})
        return {
            "values": values_out,
            "errors": dict(result.errors),
            "stats": stats,
            "free_keys": list(result.free_keys),
            "verdict": verdict(checks),
            "diagnostics": [
                {"check": c.key, "status": c.status, "title": c.title, "value": c.value,
                 "threshold": c.threshold, "meaning": c.meaning, "action": c.action}
                for c in checks],
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
            "geometry_effect": dict(self.geometry_effect),
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
                self.calibration_info = None if self.instrument else self.calibration_info
                self.load_ws5(file_path)
                if self.instrument is not None:
                    info = self.calibration_info or {}
                    row["calibration"] = {
                        "measured": info.get("measurement_date") or "",
                        "date": info.get("calibration_date", ""),
                        "vmax": float(self.model.vars.get("vmax", 0.0)),
                    }
                    if self.calibration_warning:
                        row["warning"] = self.calibration_warning
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
