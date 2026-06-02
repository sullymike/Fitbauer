#!/usr/bin/env python3
"""Mössbauer Fe-57 — front-end Qt (PySide6).

Estado tras sesión 2: ventana principal con paneles de Calibración y Sextete
en la columna izquierda, plot principal embebido (matplotlib QtAgg),
acción Fit ▸ Run conectada al motor puro core.fit_engine.fit_discrete().

Pendiente: paneles file_info, info_display y reference; diálogos de ajuste
en serie / verosimilitud perfilada / restricciones; estilos QSS; tests.
"""
from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass, field

import numpy as np
if not hasattr(np, "trapezoid"):
    np.trapezoid = np.trapz  # type: ignore[attr-defined]

from PySide6 import QtCore, QtGui, QtWidgets
import matplotlib

matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

MAX_QT_COMPONENTS = 6

# Layout adaptativo del área de componentes (equivalente al panel Tk modular):
# se apilan verticalmente cuando hay sitio y pasan a pestañas cuando no caben.
# Alturas estimadas (px) usadas para decidir el modo, con histéresis.
_COMP_STACK_H = 300      # altura aproximada de un componente apilado
_DIST_STACK_H = 340      # altura aproximada del bloque de distribución
_COMP_OVERHEAD_H = 120   # cabecera + botones + márgenes

# Temas de color de la interfaz. "blue" imita el azul de la GUI Tk; "soft"
# usa varios tonos apagados (no chillones). "system" deja el aspecto nativo.
COLOR_THEMES: dict[str, dict] = {
    "blue": {
        "label": "Azul (clásico)",
        "window": "#eaf4fb", "base": "#ffffff", "alt_base": "#dcebf7",
        "text": "#0f3d5c", "button": "#d8ecf9", "button_text": "#0f3d5c",
        "highlight": "#38bdf8", "highlight_text": "#ffffff",
        "accent": "#075985", "accent_text": "#ffffff", "accent_sub": "#dff6ff",
        "title": "#075985", "disabled_text": "#9bb0bf", "disabled_base": "#eef3f7",
    },
    "soft": {
        "label": "Multicolor suave",
        "window": "#f4f2ec", "base": "#ffffff", "alt_base": "#ece7db",
        "text": "#33302a", "button": "#e7e1d3", "button_text": "#33302a",
        "highlight": "#6f9a8d", "highlight_text": "#ffffff",
        "accent": "#5b6c8f", "accent_text": "#ffffff", "accent_sub": "#eef0f6",
        "title": "#7a6a8f", "disabled_text": "#b3aa99", "disabled_base": "#efece4",
    },
    "teal": {
        "label": "Verde azulado",
        "window": "#eaf3f1", "base": "#ffffff", "alt_base": "#d7e8e4",
        "text": "#173a36", "button": "#d2e8e3", "button_text": "#173a36",
        "highlight": "#2fa39a", "highlight_text": "#ffffff",
        "accent": "#0f5e57", "accent_text": "#ffffff", "accent_sub": "#dff3ef",
        "title": "#0f5e57", "disabled_text": "#9bb5b0", "disabled_base": "#eef4f2",
    },
    "sepia": {
        "label": "Sepia cálido",
        "window": "#efe7d8", "base": "#fbf7ee", "alt_base": "#e6dcc8",
        "text": "#4a3f2e", "button": "#e3d7c0", "button_text": "#4a3f2e",
        "highlight": "#b08968", "highlight_text": "#ffffff",
        "accent": "#8a6d4e", "accent_text": "#ffffff", "accent_sub": "#f3ece0",
        "title": "#7c5e3f", "disabled_text": "#b3a48c", "disabled_base": "#efe9dd",
    },
    "dark": {
        "label": "Oscuro",
        "window": "#2b2f36", "base": "#1f2329", "alt_base": "#333941",
        "text": "#e6e9ee", "button": "#3a414b", "button_text": "#e6e9ee",
        "highlight": "#4f9fd6", "highlight_text": "#ffffff",
        "accent": "#11304a", "accent_text": "#ffffff", "accent_sub": "#cfe6f5",
        "title": "#8ec5e6", "disabled_text": "#6b727b", "disabled_base": "#262a30",
    },
    "system": {
        "label": "Sistema",
    },
}

from mossbauer_i18n import (  # noqa: E402
    tr, get_language, set_language, available_languages,
)
from mossbauer_help import get_help_sections  # noqa: E402
from core.data_io import SETTINGS_PATH, load_credentials, save_credentials  # noqa: E402
from core.constants import (  # noqa: E402
    APP_VERSION, APP_NAME, APP_AUTHOR, APP_DEPARTMENT,
    SEXTET_PARAM_NAMES, LINE_POS_33T, BHF_DEFAULT_T, GLOBAL_PARAM_NAMES,
)
from core.folding import (  # noqa: E402
    read_ws5_counts, find_best_integer_or_half_center, fold_integer_or_half,
)
from core.fit_engine import (  # noqa: E402
    Component, FitState, FitResult, fit_discrete, model_from_values,
)
from core.profile_likelihood import asymmetric_intervals  # noqa: E402
from core.physics import component_absorption  # noqa: E402
from core.plot_styles import get_style, apply_rc  # noqa: E402
from core.batch_fit import extract_metadata, write_results_csv, collect_trend_data  # noqa: E402
from mossbauer_distribution import (  # noqa: E402
    fit_hyperfine_distribution,
    fit_gaussian_hyperfine_distribution,
    fit_binomial_hyperfine_distribution,
    fit_fixed_hyperfine_distribution,
)


# ─────────────────────────────────────────────────────────────────────────
#  Widget reutilizable: parámetro = label + spinbox + (opcional) fijo
# ─────────────────────────────────────────────────────────────────────────


class ParamControl(QtWidgets.QWidget):
    """Una fila: etiqueta + QDoubleSpinBox + casilla 'fijo'.

    Emite ``valueChanged(float)`` cuando cambia el spinbox.
    """
    valueChanged = QtCore.Signal(float)
    fixedChanged = QtCore.Signal(bool)

    def __init__(self, label: str, value: float, lo: float, hi: float,
                 step: float = 0.01, decimals: int = 4, with_fixed: bool = True,
                 parent=None):
        super().__init__(parent)
        self._lo = float(lo)
        self._hi = float(hi)
        self._syncing = False

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 2, 0, 2)
        v.setSpacing(2)

        h = QtWidgets.QHBoxLayout()
        h.setSpacing(4)
        self.label = QtWidgets.QLabel(label)
        self.label.setMinimumWidth(82)
        self.label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.spin = QtWidgets.QDoubleSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(decimals)
        self.spin.setValue(value)
        self.spin.setMinimumWidth(80)
        h.addWidget(self.label, stretch=1)
        h.addWidget(self.spin)
        self.fixed_cb = None
        if with_fixed:
            self.fixed_cb = QtWidgets.QCheckBox(tr("checkbox.fixed"))
            h.addWidget(self.fixed_cb)
            self.fixed_cb.toggled.connect(self.fixedChanged)
        v.addLayout(h)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(25)
        self.slider.setToolTip(label)
        self.slider.setValue(self._value_to_slider(value))
        v.addWidget(self.slider)

        self.spin.valueChanged.connect(self._on_spin_changed)
        self.slider.valueChanged.connect(self._on_slider_changed)

    def value(self) -> float:
        return float(self.spin.value())

    def set_value(self, v: float) -> None:
        self._syncing = True
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(float(v))
        self.slider.setValue(self._value_to_slider(self.spin.value()))
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)
        self._syncing = False

    def _value_to_slider(self, value: float) -> int:
        if self._hi <= self._lo:
            return 0
        frac = (float(value) - self._lo) / (self._hi - self._lo)
        return int(round(max(0.0, min(1.0, frac)) * self.slider.maximum()))

    def _slider_to_value(self, pos: int) -> float:
        if self.slider.maximum() <= 0:
            return self._lo
        frac = float(pos) / float(self.slider.maximum())
        return self._lo + frac * (self._hi - self._lo)

    def _on_spin_changed(self, value: float) -> None:
        if self._syncing:
            return
        self._syncing = True
        self.slider.blockSignals(True)
        self.slider.setValue(self._value_to_slider(value))
        self.slider.blockSignals(False)
        self._syncing = False
        self.valueChanged.emit(float(value))

    def _on_slider_changed(self, pos: int) -> None:
        if self._syncing:
            return
        value = self._slider_to_value(pos)
        self._syncing = True
        self.spin.blockSignals(True)
        self.spin.setValue(value)
        value = float(self.spin.value())
        self.spin.blockSignals(False)
        self._syncing = False
        self.valueChanged.emit(value)

    def is_fixed(self) -> bool:
        return bool(self.fixed_cb.isChecked()) if self.fixed_cb is not None else False

    def set_fixed(self, b: bool) -> None:
        if self.fixed_cb is not None:
            self.fixed_cb.setChecked(bool(b))


# ─────────────────────────────────────────────────────────────────────────
#  Paneles
# ─────────────────────────────────────────────────────────────────────────


class CalibrationPanel(QtWidgets.QGroupBox):
    """Panel de calibración equivalente al de Tk.

    Incluye vmax/center/baseline/slope/σ-Voigt, las casillas de ajuste y el
    selector de modelo de absorbente con ``sat_scale``.
    """

    paramChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(tr("controls.calibration_box"), parent)
        v = QtWidgets.QVBoxLayout(self)
        v.setSpacing(2)

        self.vmax = ParamControl(tr("slider.vmax"), 12.007, -15.0, 15.0, 0.0001, 4, with_fixed=False)
        self.fit_velocity = QtWidgets.QCheckBox(tr("checkbox.fit_vmax"))
        self.center = ParamControl(tr("slider.center"), 256.5, 250.0, 263.0, 0.0001, 4, with_fixed=False)
        self.fit_center = QtWidgets.QCheckBox(tr("checkbox.fit_center"))
        self.baseline = ParamControl(tr("slider.baseline"), 1.0, 0.70, 1.30, 0.0005, 4)
        self.slope = ParamControl(tr("slider.slope"), 0.0, -0.002, 0.002, 1e-5, 6)
        self.voigt_sigma = ParamControl(tr("slider.voigt_sigma"), 0.05, 0.0, 1.0, 0.001, 4, with_fixed=False)
        self.line_profile = "Lorentziana"
        self.fit_sigma = QtWidgets.QCheckBox(tr("checkbox.fit_sigma"))

        # Menú contextual (clic derecho) del perfil de línea: solo sobre el
        # control de σ-Voigt (etiqueta, slider y spinbox). No aparece sobre el
        # resto de la caja de calibración ni sobre la casilla 'Ajustar σ'.
        for w in (self.voigt_sigma, self.voigt_sigma.label,
                  self.voigt_sigma.slider, self.voigt_sigma.spin):
            w.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            w.customContextMenuRequested.connect(self._show_sigma_menu)

        absorber_row = QtWidgets.QHBoxLayout()
        absorber_row.addWidget(QtWidgets.QLabel(tr("absorber.model_label")))
        self.absorber_combo = QtWidgets.QComboBox()
        for value, key in (("thin", "absorber.thin"), ("thickness", "absorber.thickness")):
            self.absorber_combo.addItem(tr(key), value)
        absorber_row.addWidget(self.absorber_combo, stretch=1)
        self.sat_scale = ParamControl(tr("slider.sat_scale"), 5.0, 0.05, 50.0, 0.01, 3)

        for w in (self.vmax, self.fit_velocity, self.center, self.fit_center,
                  self.baseline, self.slope, self.voigt_sigma, self.fit_sigma):
            v.addWidget(w)
        v.addLayout(absorber_row)
        v.addWidget(self.sat_scale)
        self._refresh_absorber_widgets()
        v.addStretch(1)

        for w in (self.vmax, self.center, self.baseline, self.slope, self.voigt_sigma, self.sat_scale):
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())
            w.fixedChanged.connect(lambda *_: self.paramChanged.emit())
        self.absorber_combo.currentIndexChanged.connect(lambda *_: (self._refresh_absorber_widgets(), self.paramChanged.emit()))
        for cb in (self.fit_velocity, self.fit_center, self.fit_sigma):
            cb.toggled.connect(lambda *_: self.paramChanged.emit())

    def _show_sigma_menu(self, pos: QtCore.QPoint) -> None:
        """Menú contextual sobre σ: cambiar perfil Lorentziana/Voigt + Ajustar σ."""
        menu = QtWidgets.QMenu(self)
        title = menu.addAction(tr("context.sigma_profile_title"))
        title.setEnabled(False)
        menu.addSeparator()
        for kind in ("Lorentziana", "Voigt"):
            act = menu.addAction(tr(f"options.profile_{'voigt' if kind == 'Voigt' else 'lorentzian'}"))
            act.setCheckable(True)
            act.setChecked(self.line_profile == kind)
            act.triggered.connect(lambda _checked=False, k=kind: self._set_line_profile(k))
        menu.addSeparator()
        act_fit_sigma = menu.addAction(tr("checkbox.fit_sigma"))
        act_fit_sigma.setCheckable(True)
        act_fit_sigma.setChecked(self.fit_sigma.isChecked())
        act_fit_sigma.setEnabled(self.line_profile == "Voigt")
        act_fit_sigma.triggered.connect(lambda checked: self.fit_sigma.setChecked(bool(checked)))
        sender = self.sender()
        anchor = sender if isinstance(sender, QtWidgets.QWidget) else self.voigt_sigma.spin
        menu.exec(anchor.mapToGlobal(pos))

    @property
    def absorber_model(self) -> str:
        return self.absorber_combo.currentData() or "thin"

    def set_absorber_model(self, model: str) -> None:
        idx = self.absorber_combo.findData(model)
        if idx >= 0:
            self.absorber_combo.setCurrentIndex(idx)
        self._refresh_absorber_widgets()

    def _refresh_absorber_widgets(self) -> None:
        self.sat_scale.setEnabled(self.absorber_model == "thickness")

    def _set_line_profile(self, kind: str) -> None:
        self.line_profile = kind
        self.voigt_sigma.spin.setEnabled(kind == "Voigt")
        self.fit_sigma.setEnabled(kind == "Voigt")
        if kind != "Voigt":
            self.fit_sigma.setChecked(False)
        self.paramChanged.emit()


class ComponentPanel(QtWidgets.QWidget):
    """10 parámetros + selector de tipo (Sextete/Doblete/Singlete) + 'activo'.

    Los parámetros que no aplican al tipo seleccionado se desactivan en gris.
    """

    paramChanged = QtCore.Signal()

    # Qué parámetros usa cada tipo (los demás se agrisan).
    _USED_BY = {
        "Sextete":  {"delta", "quad", "bhf", "gamma1", "gamma2", "gamma3",
                     "depth", "int1", "int2", "int3", "texture", "beta"},
        "Doblete":  {"delta", "quad", "gamma1", "gamma2", "depth", "int1", "int2"},
        "Singlete": {"delta", "gamma1", "depth", "int1"},
    }

    def __init__(self, idx: int, parent=None):
        super().__init__(parent)
        self.idx = idx
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(2)

        # Cabecera: tipo + activo
        row = QtWidgets.QHBoxLayout()
        self.enabled = QtWidgets.QCheckBox(tr("component.enable", idx=idx))
        self.enabled.setChecked(idx == 1)
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["Sextete", "Doblete", "Singlete"])
        row.addWidget(self.enabled)
        row.addStretch(1)
        row.addWidget(QtWidgets.QLabel(tr("component.shape_label")))
        row.addWidget(self.type_combo)
        v.addLayout(row)

        # Orden del GUI Tk clásico, repartido en dos columnas:
        # δ · ΔEQ · BHF · Γ1-Γ3 | profundidad · intensidades · textura · β.
        left_specs = [
            ("delta",  tr("slider.s_delta"),  0.00, -2.0, 3.0, 0.001, 4),
            ("quad",   tr("slider.s_quad"),   0.00, -4.0, 4.0, 0.001, 4),
            ("bhf",    tr("slider.s_bhf"),    BHF_DEFAULT_T, 0.0, 60.0, 0.01, 3),
            ("gamma1", tr("slider.s_gamma1"), 0.15, 0.03, 2.0, 0.001, 4),
            ("gamma2", tr("slider.s_gamma2"), 1.00, 0.2, 3.0, 0.001, 4),
            ("gamma3", tr("slider.s_gamma3"), 1.00, 0.2, 3.0, 0.001, 4),
        ]
        depth_default = 0.020 if idx == 1 else 0.005
        right_specs = [
            ("depth",   tr("slider.s_depth"),   depth_default, 0.0, 0.07, 0.0001, 5),
            ("int1",    tr("slider.s_int1"),    3.0, 0.0, 6.0, 0.01, 3),
            ("int2",    tr("slider.s_int2"),    2.0, 0.0, 4.0, 0.01, 3),
            ("texture", tr("slider.s_texture"), 2.0 / 3.0, 0.0, 1.0, 0.001, 4),
            ("beta",    tr("slider.s_beta"),    0.0, 0.0, 90.0, 0.1, 2),
        ]
        hidden_specs = [
            ("int3", tr("slider.s_int3"), 1.0, 1.0, 1.0, 0.0, 3),
        ]
        self.params: dict[str, ParamControl] = {}
        params_grid = QtWidgets.QGridLayout()
        params_grid.setContentsMargins(0, 0, 0, 0)
        params_grid.setHorizontalSpacing(10)
        params_grid.setVerticalSpacing(2)
        params_grid.setColumnStretch(0, 1)
        params_grid.setColumnStretch(1, 1)
        for col, specs in enumerate((left_specs, right_specs)):
            for row_idx, (name, label, val, lo, hi, step, dec) in enumerate(specs):
                ctl = ParamControl(label, val, lo, hi, step, dec)
                params_grid.addWidget(ctl, row_idx, col)
                self.params[name] = ctl
                ctl.valueChanged.connect(lambda *_: self.paramChanged.emit())
                ctl.fixedChanged.connect(lambda *_: self.paramChanged.emit())
        for name, label, val, lo, hi, step, dec in hidden_specs:
            ctl = ParamControl(label, val, lo, hi, step, dec)
            ctl.hide()
            self.params[name] = ctl
            ctl.valueChanged.connect(lambda *_: self.paramChanged.emit())
            ctl.fixedChanged.connect(lambda *_: self.paramChanged.emit())
        v.addLayout(params_grid)
        self.enabled.toggled.connect(lambda *_: self.paramChanged.emit())
        self.type_combo.currentTextChanged.connect(self._on_type_changed)

        # Estado para los menús contextuales (clic derecho). Ya no hay
        # desplegables: el modo de intensidades y el tratamiento del cuadrupolo
        # se eligen únicamente con el menú contextual, aligerando el panel.
        self.intensity_mode = "free"       # "free" / "texture"
        self.quad_treatment = "1st_order"  # 1st_order / kundig_fixed / kundig_powder

        # Clic derecho sobre intensidades y profundidad → menú Intensity mode
        # (free / textured), igual que el desplegable que sustituye.
        for k in ("int1", "int2", "texture", "depth"):
            ctl = self.params[k]
            for w in (ctl.spin, ctl.label, ctl.slider):
                w.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                w.customContextMenuRequested.connect(
                    lambda pos, c=ctl: self._show_intensity_menu(c, pos))
        self.params["texture"].valueChanged.connect(lambda *_: self._update_texture_intensities())

        # Clic derecho sobre quad → menú Quadrupole treatment
        # (1er orden / Kundig fijo / Kundig polvo).
        ctl_q = self.params["quad"]
        for w in (ctl_q.spin, ctl_q.label, ctl_q.slider):
            w.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            w.customContextMenuRequested.connect(
                lambda pos, c=ctl_q: self._show_quad_menu(c, pos))

        # Fijos típicos para α-Fe (intensidades + gammas relativas + quad).
        for k in ("int1", "int2", "int3", "gamma2", "gamma3", "quad", "texture"):
            self.params[k].set_fixed(True)
        v.addStretch(1)
        self._on_type_changed(self.type_combo.currentText())

    def _show_intensity_menu(self, ctl: "ParamControl", pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        title = menu.addAction(tr("context.intensity_mode_title"))
        title.setEnabled(False)
        menu.addSeparator()
        for val, key in (("free", "context.intensity_mode_free"),
                          ("texture", "context.intensity_mode_texture")):
            act = menu.addAction(tr(key))
            act.setCheckable(True)
            act.setChecked(self.intensity_mode == val)
            act.triggered.connect(lambda _c=False, v=val: self._set_intensity_mode(v))
        sender = self.sender()
        anchor = sender if isinstance(sender, QtWidgets.QWidget) else ctl.spin
        menu.exec(anchor.mapToGlobal(pos))

    def _set_intensity_mode(self, mode: str) -> None:
        if mode not in ("free", "texture"):
            return
        self.intensity_mode = mode
        # En modo textura, fija int1=3 / int2 (configurable via t implícito) /
        # int3=1 manteniéndolos como referencia 3:4t/(2-t):1 (t≈2/3 por defecto).
        if mode == "texture":
            self._update_texture_intensities()
            for k in ("int1", "int2", "int3"):
                self.params[k].set_fixed(True)
        self._on_type_changed(self.kind)
        self.paramChanged.emit()

    def _update_texture_intensities(self) -> None:
        if self.intensity_mode != "texture":
            return
        t = float(self.params["texture"].value())
        denom = max(2.0 - t, 1e-9)
        self.params["int1"].set_value(3.0)
        self.params["int2"].set_value(4.0 * t / denom)
        self.params["int3"].set_value(1.0)

    def _show_quad_menu(self, ctl: "ParamControl", pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        title = menu.addAction(tr("context.quad_treatment_title"))
        title.setEnabled(False)
        menu.addSeparator()
        for val, key in (
            ("1st_order", "context.quad_treatment_1st_order"),
            ("kundig_fixed", "context.quad_treatment_kundig_fixed"),
            ("kundig_powder", "context.quad_treatment_kundig_powder"),
        ):
            act = menu.addAction(tr(key))
            act.setCheckable(True)
            act.setChecked(self.quad_treatment == val)
            act.triggered.connect(lambda _c=False, v=val: self._set_quad_treatment(v))
        sender = self.sender()
        anchor = sender if isinstance(sender, QtWidgets.QWidget) else ctl.spin
        menu.exec(anchor.mapToGlobal(pos))

    def _set_quad_treatment(self, treatment: str) -> None:
        if treatment not in ("1st_order", "kundig_fixed", "kundig_powder"):
            return
        self.quad_treatment = treatment
        self._on_type_changed(self.kind)
        self.paramChanged.emit()

    @property
    def kind(self) -> str:
        return self.type_combo.currentText()

    def _on_type_changed(self, kind: str) -> None:
        used = set(self._USED_BY.get(kind, set()))
        if kind == "Sextete":
            if self.intensity_mode == "texture":
                used.discard("int1")
                used.discard("int2")
            else:
                used.discard("texture")
            if self.quad_treatment != "kundig_fixed":
                used.discard("beta")
        else:
            used.discard("texture")
            used.discard("beta")
        for name, ctl in self.params.items():
            ctl.setEnabled(name in used)
        self.paramChanged.emit()

    def values_dict(self) -> dict[str, float]:
        return {f"s{self.idx}_{k}": ctl.value() for k, ctl in self.params.items()}

    def fixed_dict(self) -> dict[str, bool]:
        return {f"s{self.idx}_{k}": ctl.is_fixed() for k, ctl in self.params.items()}

    def apply_values(self, values: dict[str, float]) -> None:
        for k, ctl in self.params.items():
            v = values.get(f"s{self.idx}_{k}")
            if v is not None:
                ctl.set_value(v)


class InfoPanel(QtWidgets.QGroupBox):
    """Panel de estado y parámetros, equivalente al resumen de la GUI Tk."""

    def __init__(self, parent=None):
        super().__init__(tr("controls.info_box"), parent)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        self.text = QtWidgets.QTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(120)
        self.text.setStyleSheet("QTextEdit { font-family: monospace; font-size: 10pt; }")
        v.addWidget(self.text)

    def set_lines(self, lines: list[str]) -> None:
        self.text.setPlainText("\n".join(lines) if lines else "—")

    def show_result(self, result) -> None:
        """Compatibilidad para llamadas antiguas: muestra sólo el ajuste."""
        lines = []
        s = result.stats or {}
        if s:
            lines.append(
                f"χ²={s.get('chi2', float('nan')):.6g}   "
                f"χ²red={s.get('red_chi2', float('nan')):.4g}   "
                f"dof={int(s.get('dof', 0))}   "
                f"AIC={s.get('aic', float('nan')):.4g}   "
                f"BIC={s.get('bic', float('nan')):.4g}"
            )
            lines.append(f"arranques: {result.n_starts}   params libres: {len(result.free_keys)}")
            lines.append("")
        if result.free_keys:
            for key in result.free_keys:
                val = result.values.get(key, float("nan"))
                err = result.errors.get(key)
                if err is not None and err > 0:
                    lines.append(f"  {key:14s} = {val:.6g}  ± {err:.3g}")
                else:
                    lines.append(f"  {key:14s} = {val:.6g}")
        corr = result.correlations or {}
        pairs = corr.get("high_pairs") or []
        if pairs:
            lines.append("")
            lines.append(tr("info.correlation_warning"))
            for p in pairs[:6]:
                lines.append(f"  {p['param1']} ↔ {p['param2']}: r={float(p['corr']):.3f}")
        self.set_lines(lines)


# ─────────────────────────────────────────────────────────────────────────
#  Canvas
# ─────────────────────────────────────────────────────────────────────────


class SpectrumCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(7.0, 5.0), dpi=100, facecolor="white")
        super().__init__(self.fig)
        self.setParent(parent)
        # Preferencia de mostrar la subgráfica de diferencia (residuos). Se fija
        # al arrancar según los ajustes, de modo que el espacio dedicado se
        # reserva (o no) desde el inicio.
        self.residual_pref = True
        self._gs = self.fig.add_gridspec(2, 1, height_ratios=[4.6, 1.0], hspace=0.08)
        self.ax = self.fig.add_subplot(self._gs[0])
        self.ax_res = self.fig.add_subplot(self._gs[1], sharex=self.ax)
        self.ax.set_ylabel(tr("plot.transmission_ylabel"))
        self.ax_res.set_xlabel(tr("plot.velocity_xlabel"))
        self.ax_res.set_ylabel(tr("plot.residual_ylabel"))
        self.show_no_file()

    def show_no_file(self) -> None:
        # Reconstruye la rejilla según la preferencia: con residuos (2 filas) o
        # sin ellos (1 fila), para que el espacio coincida con la opción ya
        # desde el arranque.
        self.fig.clear()
        if self.residual_pref:
            self._gs = self.fig.add_gridspec(2, 1, height_ratios=[4.6, 1.0], hspace=0.08)
            self.ax = self.fig.add_subplot(self._gs[0])
            self.ax_res = self.fig.add_subplot(self._gs[1], sharex=self.ax)
        else:
            self._gs = self.fig.add_gridspec(1, 1)
            self.ax = self.fig.add_subplot(self._gs[0])
            self.ax_res = None
        self.ax.text(0.5, 0.5, tr("plot.no_file"),
                     transform=self.ax.transAxes, ha="center", va="center",
                     fontsize=13, color="#075985", fontweight="bold")
        self.ax.set_xticks([]); self.ax.set_yticks([])
        if self.ax_res is not None:
            self.ax_res.set_xticks([]); self.ax_res.set_yticks([])
        self.fig.tight_layout()
        self.draw_idle()

    def render(self, v: np.ndarray, y: np.ndarray,
               model: np.ndarray | None = None,
               components: list[tuple[int, str, np.ndarray]] | None = None,
               style: dict | None = None,
               show_residual: bool = True,
               show_legend: bool = True) -> None:
        s = style or get_style("classic")
        self.fig.set_facecolor(s["fig_bg"])
        # El espacio de residuos depende SOLO de la opción 'mostrar diferencia',
        # no de que exista un modelo: así un ajuste no altera la disposición.
        actual_show_residual = bool(show_residual)
        self.residual_pref = actual_show_residual
        self.fig.clear()
        if actual_show_residual:
            self._gs = self.fig.add_gridspec(2, 1, height_ratios=[4.6, 1.0], hspace=0.08)
            self.ax = self.fig.add_subplot(self._gs[0])
            self.ax_res = self.fig.add_subplot(self._gs[1], sharex=self.ax)
        else:
            self._gs = self.fig.add_gridspec(1, 1)
            self.ax = self.fig.add_subplot(self._gs[0])
            self.ax_res = None
        self.ax.set_facecolor(s["ax_bg"])
        if self.ax_res is not None:
            self.ax_res.set_facecolor(s["res_bg"])
        self.ax.plot(v, y, ".", color=s["data"],
                     ms=s.get("data_ms", 3.5), alpha=s.get("data_alpha", 0.7),
                     label=tr("plot.legend_data"))
        if components:
            palette = s.get("components_palette") or ("#10b981", "#f59e0b", "#8b5cf6")
            for idx, kind, comp in components:
                self.ax.plot(v, comp, "--",
                             color=palette[(idx - 1) % len(palette)],
                             lw=s.get("component_lw", 1.4),
                             alpha=s.get("component_alpha", 0.85),
                             label=f"{tr(f'kind.{kind}', default=kind)} {idx}")
        if model is not None:
            self.ax.plot(v, model, "-", color=s["model"],
                         lw=s.get("model_lw", 2.2),
                         label=tr("plot.legend_model"))
            residual = y - model
            if actual_show_residual and self.ax_res is not None:
                self.ax_res.axhline(0, color=s["res_zero"], lw=0.9, alpha=0.9)
                self.ax_res.fill_between(v, residual, 0, color=s["res_fill"],
                                         alpha=s.get("res_fill_alpha", 0.22))
                self.ax_res.plot(v, residual, "-", color=s["res_line"],
                                 lw=s.get("res_line_lw", 1.0))
                lim = max(float(np.nanmax(np.abs(residual))) * 1.18, 1e-6)
                self.ax_res.set_ylim(-lim, lim)
        if not actual_show_residual:
            self.ax.tick_params(labelbottom=True)
            self.ax.set_xlabel(tr("plot.velocity_xlabel"), color=s["lbl"])
        else:
            self.ax.tick_params(labelbottom=False)
            self.ax.set_xlabel("")
        self.ax.set_ylabel(tr("plot.transmission_ylabel"), color=s["lbl"])
        self.ax.set_title(tr("plot.title_discrete"), color=s["title"], pad=10,
                          fontweight=s.get("title_weight", "bold"))
        self.ax.tick_params(colors=s["tick"])
        self.ax.grid(True, color=s["grid"], alpha=s["grid_alpha"],
                     linewidth=s.get("grid_lw", 0.8))
        for name, sp in self.ax.spines.items():
            sp.set_color(s["spine"])
            if name in s.get("spines_hide", ()):
                sp.set_visible(False)
        if self.ax_res is not None:
            self.ax_res.set_xlabel(tr("plot.velocity_xlabel"), color=s["lbl"])
            self.ax_res.set_ylabel(tr("plot.residual_ylabel"), color=s["lbl"])
            self.ax_res.tick_params(colors=s["res_tick"])
            self.ax_res.grid(True, color=s["res_grid"], alpha=0.8, linewidth=0.75)
            for name, sp in self.ax_res.spines.items():
                sp.set_color(s["res_spine"])
                if name in s.get("spines_hide", ()):
                    sp.set_visible(False)
        if show_legend:
            self.ax.legend(loc="lower right", fontsize=9, framealpha=0.85,
                           facecolor=s["leg_face"], edgecolor=s["leg_edge"],
                           labelcolor=s["leg_text"])
        self.fig.tight_layout()
        self.draw_idle()


# ─────────────────────────────────────────────────────────────────────────
#  Ventana principal
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class FileState:
    path: Path | None = None
    counts: np.ndarray | None = None
    folded: np.ndarray | None = None
    sigma: np.ndarray | None = None
    norm_factor: float = 1.0
    center: float | None = None
    velocity: np.ndarray | None = None
    y_data: np.ndarray | None = None


class DistributionPanel(QtWidgets.QGroupBox):
    """Panel para modo distribución P(BHF) / P(ΔEQ).

    Soporta 4 formas (igual que la GUI Tk): Histograma (Hesse-Rübartsch
    no paramétrica), Gaussiana, Binomial y Fija (P cargada desde fichero).
    """

    paramChanged = QtCore.Signal()
    loadFixedRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(tr("tab.distribution_bhf"), parent)
        v = QtWidgets.QVBoxLayout(self)
        v.setSpacing(2)

        cols = QtWidgets.QGridLayout()
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setHorizontalSpacing(12)
        cols.setVerticalSpacing(2)
        cols.setColumnStretch(0, 1)
        cols.setColumnStretch(1, 1)
        left = QtWidgets.QWidget()
        right = QtWidgets.QWidget()
        left_v = QtWidgets.QVBoxLayout(left)
        right_v = QtWidgets.QVBoxLayout(right)
        for lay in (left_v, right_v):
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(2)
        cols.addWidget(left, 0, 0)
        cols.addWidget(right, 0, 1)
        v.addLayout(cols)

        # Columna 1 — forma, regulación y parámetros globales.
        shape_row = QtWidgets.QHBoxLayout()
        shape_row.addWidget(QtWidgets.QLabel(tr("bhf.shape_label") + ":"))
        self.shape_combo = QtWidgets.QComboBox()
        for code, key in (("Histograma", "shape.Histograma"),
                          ("Gaussiana", "shape.Gaussiana"),
                          ("Binomial", "shape.Binomial"),
                          ("Fija", "shape.Fija")):
            self.shape_combo.addItem(tr(key), code)
        self.shape_combo.currentIndexChanged.connect(lambda *_: self.paramChanged.emit())
        shape_row.addWidget(self.shape_combo, stretch=1)
        left_v.addLayout(shape_row)

        reg_row = QtWidgets.QHBoxLayout()
        reg_row.addWidget(QtWidgets.QLabel(tr("bhf.reg_mode_label") + ":"))
        self.reg_mode_combo = QtWidgets.QComboBox()
        self.reg_mode_combo.addItems(["tikhonov", "tv"])
        self.reg_mode_combo.currentIndexChanged.connect(lambda *_: self.paramChanged.emit())
        reg_row.addWidget(self.reg_mode_combo, stretch=1)
        left_v.addLayout(reg_row)

        self.btn_load_fixed = QtWidgets.QPushButton(tr("bhf.load_fixed"))
        self.btn_load_fixed.clicked.connect(self.loadFixedRequested)
        self.btn_load_fixed.setEnabled(False)
        self.shape_combo.currentIndexChanged.connect(
            lambda i: self.btn_load_fixed.setEnabled(self.shape == "Fija"))
        left_v.addWidget(self.btn_load_fixed)

        self.delta = ParamControl(tr("slider.dist_delta"), 0.0, -2.5, 2.5, 0.001, 4)
        self.quad  = ParamControl(tr("slider.dist_quad"),  0.0, -4.0, 4.0, 0.001, 4)
        self.fixed_bhf = ParamControl(tr("slider.dist_fixed_bhf"), BHF_DEFAULT_T, 0.0, 60.0, 0.01, 3, with_fixed=False)
        self.gamma = ParamControl(tr("slider.dist_gamma"), 0.18, 0.03, 1.0, 0.001, 4)
        for w in (self.delta, self.quad, self.fixed_bhf, self.gamma):
            left_v.addWidget(w)
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())
        left_v.addStretch(1)

        # Columna 2 — rango/bins/alfa + presets y opciones avanzadas.
        self.bmin  = ParamControl(tr("slider.dist_bmin"), 0.0,  0.0, 60.0, 0.1, 2, with_fixed=False)
        self.bmax  = ParamControl(tr("slider.dist_bmax"), 50.0, 1.0, 60.0, 0.1, 2, with_fixed=False)
        self.nbins = ParamControl(tr("slider.dist_nbins"), 50.0, 10.0, 100.0, 1.0, 0, with_fixed=False)
        self.log_alpha = ParamControl(tr("slider.dist_log_alpha"), -2.0, -8.0, 4.0, 0.1, 2, with_fixed=False)
        for w in (self.bmin, self.bmax, self.nbins, self.log_alpha):
            right_v.addWidget(w)
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())

        alpha_row = QtWidgets.QHBoxLayout()
        alpha_row.setSpacing(4)
        for text, value in ((tr("bhf.alpha_fine", default="Fina"), -5.0),
                            (tr("bhf.alpha_medium", default="Media"), -2.0),
                            (tr("bhf.alpha_smooth", default="Suave"), 1.0)):
            btn = QtWidgets.QPushButton(text)
            btn.clicked.connect(lambda _=False, val=value: self._set_log_alpha(val))
            alpha_row.addWidget(btn)
        right_v.addLayout(alpha_row)

        self.use_sharp = QtWidgets.QCheckBox(tr("bhf.use_sharp", default="Añadir componentes nítidas activas"))
        self.refine_global = QtWidgets.QCheckBox(tr("bhf.refine_global", default="Refinar δ y Γ globales"))
        self.lcurve_link = QtWidgets.QCommandLinkButton(tr("bhf.lcurve_alpha", default="L-curve α"))
        self.lcurve_link.setDescription(tr("bhf.lcurve_hint", default="Estimar la regularización del histograma"))
        for w in (self.use_sharp, self.refine_global):
            right_v.addWidget(w)
            w.toggled.connect(lambda *_: self.paramChanged.emit())
        right_v.addWidget(self.lcurve_link)
        right_v.addStretch(1)
        v.addStretch(1)
        self.fixed_path: Path | None = None

    def _set_log_alpha(self, value: float) -> None:
        self.log_alpha.set_value(float(value))
        self.paramChanged.emit()

    @property
    def shape(self) -> str:
        return self.shape_combo.currentData() or "Histograma"

    @property
    def reg_mode(self) -> str:
        return self.reg_mode_combo.currentText() or "tikhonov"


class ConstraintsDialog(QtWidgets.QDialog):
    """Editor de restricciones lineales: target = factor·source + offset."""

    def __init__(self, parent: "MossbauerQtWindow"):
        super().__init__(parent)
        self.setWindowTitle(tr("options.constraints"))
        self.resize(660, 380)
        self.parent_win = parent
        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(QtWidgets.QLabel(
            "<i>target = factor · source + offset</i>"))
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["target", "factor", "source", "offset"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        v.addWidget(self.table, stretch=1)
        row = QtWidgets.QHBoxLayout()
        btn_add = QtWidgets.QPushButton("+")
        btn_add.clicked.connect(self._add_row)
        btn_rm = QtWidgets.QPushButton("−")
        btn_rm.clicked.connect(self._remove_row)
        row.addWidget(btn_add); row.addWidget(btn_rm); row.addStretch(1)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self._apply_and_accept)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        v.addLayout(row)
        self._param_keys = self._collect_param_keys()
        self._load_existing()

    def _collect_param_keys(self) -> list[str]:
        """Claves de parámetros disponibles (de las 3 componentes)."""
        keys: list[str] = []
        for cp in self.parent_win.components_panels:
            for name in cp.params:
                keys.append(f"s{cp.idx}_{name}")
        return keys

    def _load_existing(self) -> None:
        constraints = getattr(self.parent_win, "constraints", []) or []
        for c in constraints:
            self._add_row(c)

    def _make_combo(self, current: str = "") -> QtWidgets.QComboBox:
        cb = QtWidgets.QComboBox()
        cb.addItems(self._param_keys)
        if current in self._param_keys:
            cb.setCurrentText(current)
        return cb

    def _make_spin(self, value: float, decimals: int = 4) -> QtWidgets.QDoubleSpinBox:
        s = QtWidgets.QDoubleSpinBox()
        s.setRange(-1e6, 1e6); s.setDecimals(decimals); s.setSingleStep(0.1)
        s.setValue(float(value))
        return s

    def _add_row(self, c: dict | None = None) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setCellWidget(r, 0, self._make_combo((c or {}).get("target", "")))
        self.table.setCellWidget(r, 1, self._make_spin((c or {}).get("factor", 1.0)))
        self.table.setCellWidget(r, 2, self._make_combo((c or {}).get("source", "")))
        self.table.setCellWidget(r, 3, self._make_spin((c or {}).get("offset", 0.0)))

    def _remove_row(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def _apply_and_accept(self) -> None:
        new: list[dict] = []
        for r in range(self.table.rowCount()):
            target = self.table.cellWidget(r, 0).currentText()
            factor = float(self.table.cellWidget(r, 1).value())
            source = self.table.cellWidget(r, 2).currentText()
            offset = float(self.table.cellWidget(r, 3).value())
            if target and source and target != source:
                new.append({"target": target, "factor": factor,
                             "source": source, "offset": offset})
        self.parent_win.constraints = new
        self.parent_win._refresh_plot()
        self.accept()


class BatchFitDialog(QtWidgets.QDialog):
    """Diálogo de ajuste en serie con warm-start secuencial.

    Selecciona N ficheros .ws5/.adt y los ajusta uno tras otro usando el
    modelo activo de la ventana principal como plantilla. El resultado de
    cada uno es la plantilla del siguiente.
    """
    def __init__(self, parent: "MossbauerQtWindow"):
        super().__init__(parent)
        self.parent_win = parent
        self.setWindowTitle(tr("msg.batch_title"))
        self.resize(820, 500)
        self.results: list[dict] = []
        self.entries: list[dict] = []  # cada uno {path, metadata, status, result}

        v = QtWidgets.QVBoxLayout(self)

        # Botones de gestión
        row = QtWidgets.QHBoxLayout()
        btn_add = QtWidgets.QPushButton(tr("batch.add_files"))
        btn_add.clicked.connect(self._add_files)
        btn_rm = QtWidgets.QPushButton(tr("batch.remove"))
        btn_rm.clicked.connect(self._remove_selected)
        row.addWidget(btn_add); row.addWidget(btn_rm)
        row.addStretch(1)
        row.addWidget(QtWidgets.QLabel("<i>" + tr("batch.template_label") + "</i>"))
        v.addLayout(row)

        # Tabla
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([
            tr("batch.col_file"), tr("batch.col_meta"), tr("batch.col_status"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        v.addWidget(self.table, stretch=1)

        # Regex
        rrow = QtWidgets.QHBoxLayout()
        rrow.addWidget(QtWidgets.QLabel(tr("batch.regex_label")))
        self.regex_edit = QtWidgets.QLineEdit(r"(?P<v>[-+]?\d+(?:\.\d+)?)\s*K")
        rrow.addWidget(self.regex_edit, stretch=1)
        btn_apply = QtWidgets.QPushButton(tr("batch.apply_regex"))
        btn_apply.clicked.connect(self._apply_regex)
        rrow.addWidget(btn_apply)
        v.addLayout(rrow)

        # Progreso
        self.progress = QtWidgets.QLabel("")
        v.addWidget(self.progress)

        # Botones de acción
        brow = QtWidgets.QHBoxLayout()
        self.btn_run = QtWidgets.QPushButton(tr("batch.run"))
        self.btn_run.clicked.connect(self._run)
        self.btn_csv = QtWidgets.QPushButton(tr("batch.save_csv"))
        self.btn_csv.clicked.connect(self._save_csv)
        self.btn_csv.setEnabled(False)
        self.btn_trends = QtWidgets.QPushButton(tr("batch.show_trends"))
        self.btn_trends.clicked.connect(self._show_trends)
        self.btn_trends.setEnabled(False)
        brow.addWidget(self.btn_run); brow.addStretch(1)
        brow.addWidget(self.btn_csv); brow.addWidget(self.btn_trends)
        btn_close = QtWidgets.QPushButton(tr("button.close"))
        btn_close.clicked.connect(self.reject)
        brow.addWidget(btn_close)
        v.addLayout(brow)

    def _refresh_table(self):
        self.table.setRowCount(len(self.entries))
        for i, e in enumerate(self.entries):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(e["path"].name))
            meta = e.get("metadata")
            meta_txt = "" if meta is None else (f"{meta:g}" if isinstance(meta, (int, float)) else str(meta))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(meta_txt))
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(tr(f"batch.status_{e['status']}")))

    def _add_files(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, tr("batch.add_files"), str(ROOT),
            "WS5/ADT (*.ws5 *.adt *.WS5 *.ADT);;All (*.*)")
        for p in paths:
            self.entries.append({"path": Path(p), "metadata": None,
                                  "status": "pending", "result": None})
        self._refresh_table()

    def _remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.entries):
                del self.entries[r]
        self._refresh_table()

    def _apply_regex(self):
        pat = self.regex_edit.text().strip()
        for e in self.entries:
            e["metadata"] = extract_metadata(e["path"].name, pat)
        self._refresh_table()

    def _run(self):
        if not self.entries:
            QtWidgets.QMessageBox.information(
                self, tr("msg.batch_title"), tr("msg.batch_no_files"))
            return
        self.btn_run.setEnabled(False)
        self.btn_csv.setEnabled(False); self.btn_trends.setEnabled(False)
        # snapshot del modelo actual de la ventana principal como plantilla
        base_values = dict(self.parent_win.calib.vmax.parent().property("_") or {})  # noop
        ok = fail = 0
        for i, e in enumerate(self.entries, 1):
            self.progress.setText(
                tr("progress.batch_step", i=i, n=len(self.entries), name=e["path"].name))
            QtWidgets.QApplication.processEvents()
            try:
                # Reusar warm-start: aplicamos el estado actual del Qt y
                # cargamos el nuevo espectro (que sobrescribe folding center).
                counts = read_ws5_counts(e["path"])
                center = find_best_integer_or_half_center(counts)
                folded, _ = fold_integer_or_half(counts, center)
                norm = float(np.percentile(folded, 90)) or 1.0
                sigma = np.sqrt(np.maximum(folded / 2.0, 1.0)) / norm
                y = folded / norm
                vmax = self.parent_win.calib.vmax.value()
                v = np.linspace(-vmax, vmax, folded.size)
                # Construir state desde la UI parental
                state = self.parent_win._build_state()
                if state is None:
                    raise RuntimeError("No hay modelo activo")
                state.velocity = v
                state.y_data = y
                state.sigma_data = sigma
                result = fit_discrete(state)
                e["status"] = "ok"
                e["result"] = {
                    "file": e["path"].name,
                    "metadata": e["metadata"],
                    "status": "ok",
                    "values": result.values,
                    "errors": result.errors,
                    "stats": result.stats,
                    "free_keys": result.free_keys,
                }
                ok += 1
                # warm-start: aplicar valores al UI para la siguiente iteración
                self.parent_win._building = True
                for cp in self.parent_win.components_panels:
                    cp.apply_values(result.values)
                self.parent_win.calib.baseline.set_value(
                    result.values.get("baseline", self.parent_win.calib.baseline.value()))
                self.parent_win.calib.slope.set_value(
                    result.values.get("slope", self.parent_win.calib.slope.value()))
                self.parent_win._building = False
            except Exception as exc:
                e["status"] = "failed"
                e["result"] = {"file": e["path"].name, "metadata": e["metadata"],
                                "status": "failed", "error": str(exc),
                                "values": {}, "errors": {}, "stats": {}}
                fail += 1
            self._refresh_table()
            QtWidgets.QApplication.processEvents()
        self.progress.setText(tr("msg.batch_done", ok=ok, fail=fail, n=len(self.entries)))
        self.btn_run.setEnabled(True)
        self.btn_csv.setEnabled(True); self.btn_trends.setEnabled(True)

    def _save_csv(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("batch.save_csv"), str(ROOT),
            "TSV (*.tsv);;CSV (*.csv);;All (*.*)")
        if not path:
            return
        results = [e["result"] for e in self.entries if e.get("result")]
        keys: set[str] = set()
        for r in results:
            keys.update(r.get("free_keys", []) or r.get("values", {}).keys())
        try:
            write_results_csv(Path(path), sorted(keys), results)
            self.progress.setText(f"TSV guardado: {path}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("batch.save_csv"),
                                            f"{type(exc).__name__}: {exc}")

    def _show_trends(self):
        results = [e["result"] for e in self.entries if e.get("result")]
        keys: set[str] = set()
        for r in results:
            keys.update(r.get("values", {}).keys())
        trend = collect_trend_data(results, sorted(keys))
        if not trend:
            QtWidgets.QMessageBox.information(
                self, tr("batch.show_trends"),
                "No hay datos numéricos para representar.")
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("msg.batch_title"))
        dlg.resize(900, 600)
        vv = QtWidgets.QVBoxLayout(dlg)
        vv.addWidget(QtWidgets.QLabel(tr("dialog.batch_trends_subtitle")))
        fig = Figure(figsize=(8.5, 5.0), dpi=96)
        cv = FigureCanvas(fig); vv.addWidget(cv, stretch=1)
        skeys = sorted(trend.keys())
        ncols = 2 if len(skeys) > 1 else 1
        nrows = (len(skeys) + ncols - 1) // ncols
        for i, k in enumerate(skeys, 1):
            ax = fig.add_subplot(nrows, ncols, i)
            xs = [p[0] for p in trend[k]]; ys = [p[1] for p in trend[k]]
            es = [p[2] if p[2] is not None else 0.0 for p in trend[k]]
            ax.errorbar(xs, ys, yerr=es, fmt="o-", color="#2563eb", ms=4)
            ax.set_title(k, fontsize=9); ax.tick_params(labelsize=7)
            ax.grid(alpha=0.3)
        fig.tight_layout(); cv.draw_idle()
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); vv.addWidget(bb)
        dlg.exec()


class MossbauerQtWindow(QtWidgets.QMainWindow):
    def closeEvent(self, event):
        try:
            self._save_settings()
        except Exception:
            pass
        super().closeEvent(event)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}  (Qt)")
        # Icono de la app (mismo que la GUI Tk)
        icon_png = ROOT / "assets" / "mossbauer_icon.png"
        if icon_png.exists():
            self.setWindowIcon(QtGui.QIcon(str(icon_png)))
        self.resize(1400, 900)
        self.file = FileState()
        self._building = False
        self.plot_style_name = "modern"
        self.constraints: list[dict] = []
        self.calibration_info: dict | None = None
        self.recent_files: list[str] = []
        self.layout_preset = "Estándar"
        self.custom_layouts: dict[str, dict] = {}
        self.color_theme = "blue"          # tema de color de la interfaz
        self._show_residual_pref = True    # mostrar subgráfica de diferencia
        # Opciones avanzadas (compartidas con la GUI Tk)
        self.likelihood = "gauss"          # "gauss" / "poisson"
        self.robust_loss = "linear"        # "linear" / "soft_l1" / "huber"
        self.propagate_calib = False
        self.global_opt = False
        self.absorber_model = "thin"       # "thin" / "thickness"
        self._simulate_enabled = False      # igual que Tk: al cargar solo se dibujan datos
        self.last_fit_result: FitResult | None = None
        self.dist_use_sharp = False
        self.dist_refine_global = False
        self._edge_trim = 1
        self._load_settings()
        self._build_ui()
        self._build_menubar()
        self._apply_color_theme(self.color_theme, persist=False)
        # Reserva (o no) el espacio de la subgráfica de diferencia desde el
        # arranque, según la preferencia guardada.
        self.canvas.residual_pref = self._show_residual_pref
        self.canvas.show_no_file()
        self.statusBar().showMessage(tr("plot.no_file"))

    # ── Construcción de la UI ────────────────────────────────────────────
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self); self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central); layout.setContentsMargins(4, 4, 4, 4)
        # El layout central NO debe redimensionar la ventana según su contenido:
        # al añadir/quitar componentes (apilado) el tamaño global se mantiene.
        layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        # Mínimo de ventana fijo e independiente del contenido.
        self.setMinimumSize(900, 520)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal); layout.addWidget(splitter)
        self._main_splitter = splitter

        # ── Columna izquierda: cabecera + file info + calibración + sextete ─
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left); lv.setContentsMargins(6, 6, 6, 6); lv.setSpacing(8)
        self._left_panels_layout = lv

        # Módulo cabecera (igual que en Tk): banner con nombre, subtítulo y autor.
        self.header_box = QtWidgets.QFrame()
        self.header_box.setObjectName("AppHeader")
        hb = QtWidgets.QVBoxLayout(self.header_box)
        hb.setContentsMargins(12, 8, 12, 8); hb.setSpacing(1)
        self.header_title = QtWidgets.QLabel(APP_NAME)
        self.header_title.setObjectName("AppHeaderTitle")
        self.header_title.setWordWrap(True)
        self._header_sub_labels = [
            QtWidgets.QLabel(tr("main.subtitle")),
            QtWidgets.QLabel(APP_AUTHOR),
            QtWidgets.QLabel(APP_DEPARTMENT),
        ]
        hb.addWidget(self.header_title)
        for lbl in self._header_sub_labels:
            lbl.setWordWrap(True)
            hb.addWidget(lbl)
        lv.addWidget(self.header_box)

        self.file_box = QtWidgets.QGroupBox(tr("controls.file_box"))
        fb = QtWidgets.QVBoxLayout(self.file_box)
        self.file_label = QtWidgets.QLabel("—"); self.file_label.setWordWrap(True)
        fb.addWidget(self.file_label)
        self.calib_label = QtWidgets.QLabel("")
        self.calib_label.setWordWrap(True)
        self.calib_label.setStyleSheet("color: #0e7490; font-size: 9pt;")
        fb.addWidget(self.calib_label)
        # Clic derecho sobre el cuadro de fichero → menú "usar como calibración".
        self.file_box.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.file_box.customContextMenuRequested.connect(self._show_file_box_menu)
        self.file_label.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.file_label.customContextMenuRequested.connect(self._show_file_box_menu)
        lv.addWidget(self.file_box)

        # Panel de referencia con las posiciones de las líneas Fe-57 a 33 T.
        ref_box = QtWidgets.QGroupBox(tr("controls.reference_box"))
        rb = QtWidgets.QVBoxLayout(ref_box)
        pos_str = ", ".join(f"{x:+.3f}" for x in LINE_POS_33T)
        ref_lbl = QtWidgets.QLabel(tr("controls.reference_lines", positions=pos_str))
        ref_lbl.setWordWrap(True)
        rb.addWidget(ref_lbl)
        lv.addWidget(ref_box)

        # Selector de modo (discreto / P(BHF)) y controles de simulación.
        self.sim_controls_box = QtWidgets.QGroupBox("Simulación / ajuste")
        sim_lay = QtWidgets.QVBoxLayout(self.sim_controls_box)
        mode_row = QtWidgets.QHBoxLayout()
        mode_row.addWidget(QtWidgets.QLabel(tr("controls.fit_mode_hint").split(":")[0] + ":"))
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems([
            tr("options.discrete_sextets"),
            tr("options.distribution_bhf"),
            "P(ΔEQ)",
        ])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo, stretch=1)
        sim_lay.addLayout(mode_row)

        ncomp_row = QtWidgets.QHBoxLayout()
        ncomp_row.addWidget(QtWidgets.QLabel(tr("sim.n_components", default="Componentes:")))
        self.n_components_spin = QtWidgets.QSpinBox()
        self.n_components_spin.setRange(1, MAX_QT_COMPONENTS)
        self.n_components_spin.setValue(1)
        self.n_components_spin.setToolTip(
            tr("sim.n_components", default="Número de componentes/sextetes activos"))
        self.n_components_spin.valueChanged.connect(self._on_n_components_changed)
        ncomp_row.addWidget(self.n_components_spin)
        ncomp_row.addWidget(QtWidgets.QLabel(f"(máx. {MAX_QT_COMPONENTS})"))
        ncomp_row.addStretch(1)
        sim_lay.addLayout(ncomp_row)

        action_grid = QtWidgets.QGridLayout()
        action_grid.setContentsMargins(0, 0, 0, 0)
        action_grid.setHorizontalSpacing(6)
        action_grid.setVerticalSpacing(4)
        self.btn_sim_fit = QtWidgets.QPushButton(tr("fit.run"))
        self.btn_sim_free_all = QtWidgets.QPushButton(tr("fit.free_all"))
        self.btn_sim_fix_all = QtWidgets.QPushButton(tr("fit.fix_all"))
        self.btn_sim_auto_min = QtWidgets.QPushButton(tr("fit.auto_from_minima"))
        self.btn_sim_ai = QtWidgets.QPushButton(tr("fit.ollama_start"))
        for pos, btn in enumerate((self.btn_sim_fit, self.btn_sim_free_all,
                                   self.btn_sim_fix_all, self.btn_sim_auto_min,
                                   self.btn_sim_ai)):
            action_grid.addWidget(btn, pos // 2, pos % 2)
        self.btn_sim_fit.clicked.connect(self.on_fit)
        self.btn_sim_free_all.clicked.connect(lambda: self._set_all_fixed(False))
        self.btn_sim_fix_all.clicked.connect(lambda: self._set_all_fixed(True))
        self.btn_sim_auto_min.clicked.connect(lambda _checked=False: self.on_auto_fit_from_minima())
        self.btn_sim_ai.clicked.connect(self.on_ai_summary)
        self._set_quick_action_buttons_enabled(False)
        sim_lay.addLayout(action_grid)

        self.calib = CalibrationPanel()
        lv.addWidget(self.calib)

        # Área de componentes con disposición adaptativa, igual que el panel
        # Tk modular: los sextetes se apilan verticalmente cuando hay espacio
        # debajo y solo pasan a pestañas cuando ya no caben. El combo superior
        # conserva la mejora Qt para elegir Discreto / P(BHF) / P(ΔEQ).
        self.dist_panel = DistributionPanel()
        self.components_panels: list[ComponentPanel] = []
        for i in range(1, MAX_QT_COMPONENTS + 1):
            self.components_panels.append(ComponentPanel(idx=i))

        # Contenedor que alberga las dos disposiciones intercambiables.
        self.comp_area = QtWidgets.QWidget()
        comp_area_lay = QtWidgets.QVBoxLayout(self.comp_area)
        comp_area_lay.setContentsMargins(0, 0, 0, 0)
        comp_area_lay.setSpacing(4)

        # Disposición en pestañas (QTabWidget).
        self.comp_tabs = QtWidgets.QTabWidget()
        comp_area_lay.addWidget(self.comp_tabs)

        # Disposición apilada (QVBoxLayout con envolturas tituladas).
        self.comp_stack = QtWidgets.QWidget()
        self._comp_stack_layout = QtWidgets.QVBoxLayout(self.comp_stack)
        self._comp_stack_layout.setContentsMargins(0, 0, 0, 0)
        self._comp_stack_layout.setSpacing(4)
        self._comp_stack_frames: dict[int, QtWidgets.QGroupBox] = {}
        comp_area_lay.addWidget(self.comp_stack)

        self._using_tabs: bool | None = None  # fuerza la primera construcción
        sim_lay.addWidget(self.comp_area)

        self.dist_panel.paramChanged.connect(self._on_model_param_changed)
        self.dist_panel.loadFixedRequested.connect(self._on_load_fixed_distribution)
        self.dist_panel.lcurve_link.clicked.connect(self.on_lcurve)
        self.dist_panel.use_sharp.toggled.connect(self._set_dist_use_sharp)
        self.dist_panel.refine_global.toggled.connect(self._set_dist_refine_global)
        self._rebuild_component_area(use_tabs=False)
        self._sync_component_count(1)
        lv.addWidget(self.sim_controls_box)
        lv.addStretch(1)

        scroll = QtWidgets.QScrollArea(); scroll.setWidget(left); scroll.setWidgetResizable(True)
        self._left_scroll = scroll
        splitter.addWidget(scroll)

        # ── Centro: canvas + toolbar + panel de info ─────────────────────
        center = QtWidgets.QWidget()
        cv = QtWidgets.QVBoxLayout(center); cv.setContentsMargins(0, 0, 0, 0)
        self._center_top_widget = QtWidgets.QWidget(center)
        self._center_top_layout = QtWidgets.QVBoxLayout(self._center_top_widget)
        self._center_top_layout.setContentsMargins(6, 6, 6, 0)
        self._center_top_layout.setSpacing(8)
        self.canvas = SpectrumCanvas(center)
        self.toolbar = NavigationToolbar(self.canvas, center)
        self.info_panel = InfoPanel()
        self._center_bottom_widget = QtWidgets.QWidget(center)
        self._center_bottom_layout = QtWidgets.QVBoxLayout(self._center_bottom_widget)
        self._center_bottom_layout.setContentsMargins(6, 0, 6, 6)
        self._center_bottom_layout.setSpacing(8)
        cv.addWidget(self._center_top_widget)
        cv.addWidget(self.toolbar); cv.addWidget(self.canvas, stretch=1)
        cv.addWidget(self._center_bottom_widget)
        splitter.addWidget(center)

        # ── Columna derecha: la completan los presets de layout ─────────────
        self._right_column = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(self._right_column)
        rv.setContentsMargins(6, 6, 6, 6); rv.setSpacing(8)
        self._right_panels_layout = rv
        rv.addStretch(1)
        splitter.addWidget(self._right_column)

        self._layout_panel_names = {
            "header": "Cabecera",
            "file_info": "Fichero",
            "info_display": "Info",
            "calibration": "Calibración",
            "reference": "Referencia",
            "sim_controls": "Simulación / ajuste",
        }
        self._layout_panel_widgets = {
            "header": self.header_box,
            "file_info": self.file_box,
            "info_display": self.info_panel,
            "calibration": self.calib,
            "reference": ref_box,
            "sim_controls": self.sim_controls_box,
        }

        splitter.setSizes([430, 1000, 0])
        self._apply_layout_preset(self._layout_preset_with_available_space(self.layout_preset))

        # Conectar señales de cambio para refrescar el plot en vivo
        self.calib.paramChanged.connect(self._on_model_param_changed)
        self.calib.center.valueChanged.connect(self._on_center_value_changed)
        self.calib.absorber_combo.currentIndexChanged.connect(self._sync_absorber_model_from_panel)
        # Al activar "Ajustar Vmax", fijar automáticamente todos los BHF (el
        # ajuste de velocidad exige que el campo hiperfino esté fijo).
        self.calib.fit_velocity.toggled.connect(self._on_fit_velocity_toggled)
        for cp in self.components_panels:
            cp.paramChanged.connect(self._on_model_param_changed)

    # ── Menubar (orden igual al de la GUI Tk) ────────────────────────────
    def _build_menubar(self) -> None:
        mb = self.menuBar()

        # ── Archivo ──────────────────────────────────────────────────────
        file_menu = mb.addMenu(tr("menu.file"))
        act_open = QtGui.QAction(tr("file.open"), self)
        act_open.setShortcut(QtGui.QKeySequence.Open)
        act_open.triggered.connect(self.on_open)
        file_menu.addAction(act_open)
        self.recent_menu = file_menu.addMenu("Open Recent")
        self._rebuild_recent_menu()
        web_menu = file_menu.addMenu(tr("file.web"))
        act_web_meas = QtGui.QAction(tr("file.web_measurements"), self)
        act_web_meas.triggered.connect(lambda: self._open_web_dialog("measurements"))
        web_menu.addAction(act_web_meas)
        act_web_calib = QtGui.QAction(tr("file.web_calibrations"), self)
        act_web_calib.triggered.connect(lambda: self._open_web_dialog("calibrations"))
        web_menu.addAction(act_web_calib)
        self.act_upload_session = QtGui.QAction(tr("file.upload_session"), self)
        self.act_upload_session.triggered.connect(self.on_upload_session)
        self.act_upload_session.setEnabled(False)
        web_menu.addAction(self.act_upload_session)
        self.act_use_as_calib = QtGui.QAction(tr("file.use_as_calibration"), self)
        self.act_use_as_calib.triggered.connect(self._use_as_calibration_detailed)
        self.act_use_as_calib.setEnabled(False)
        file_menu.addAction(self.act_use_as_calib)
        file_menu.addSeparator()
        self.act_save_fit = QtGui.QAction(tr("file.save_fit"), self)
        self.act_save_fit.triggered.connect(self.on_save_fit)
        self.act_save_fit.setEnabled(False)
        file_menu.addAction(self.act_save_fit)
        self.act_export_report = QtGui.QAction(tr("file.export_report"), self)
        self.act_export_report.triggered.connect(self.on_export_report)
        self.act_export_report.setEnabled(False)
        file_menu.addAction(self.act_export_report)
        file_menu.addSeparator()
        act_save_session = QtGui.QAction(tr("file.save_session"), self)
        act_save_session.setShortcut("Ctrl+S")
        act_save_session.triggered.connect(self.on_save_session)
        file_menu.addAction(act_save_session)
        act_load_session = QtGui.QAction(tr("file.load_session"), self)
        act_load_session.setShortcut("Ctrl+L")
        act_load_session.triggered.connect(self.on_load_session)
        file_menu.addAction(act_load_session)
        file_menu.addSeparator()
        act_exit = QtGui.QAction(tr("file.exit"), self)
        act_exit.setShortcut(QtGui.QKeySequence.Quit)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # ── Ajuste ───────────────────────────────────────────────────────
        fit_menu = mb.addMenu(tr("menu.fit"))
        self.act_fit = QtGui.QAction(tr("fit.run"), self)
        self.act_fit.setShortcut("Ctrl+R")
        self.act_fit.triggered.connect(self.on_fit)
        self.act_fit.setEnabled(False)
        fit_menu.addAction(self.act_fit)
        fit_menu.addSeparator()
        self.act_find_center = QtGui.QAction(tr("fit.find_center"), self)
        self.act_find_center.triggered.connect(self.on_find_center)
        self.act_find_center.setEnabled(False)
        fit_menu.addAction(self.act_find_center)
        self.act_init = QtGui.QAction(tr("fit.init_from_minima"), self)
        # QAction.triggered emits a checked=False argument.  Use a lambda so it
        # does not override on_init_from_minima(show_message=True).
        self.act_init.triggered.connect(lambda _checked=False: self.on_init_from_minima(show_message=True))
        self.act_init.setEnabled(False)
        fit_menu.addAction(self.act_init)
        self.act_auto_fit = QtGui.QAction(tr("fit.auto_from_minima"), self)
        self.act_auto_fit.triggered.connect(lambda _checked=False: self.on_auto_fit_from_minima())
        self.act_auto_fit.setEnabled(False)
        fit_menu.addAction(self.act_auto_fit)
        self.act_ai = QtGui.QAction(tr("fit.ollama_start"), self)
        self.act_ai.triggered.connect(self.on_ai_summary)
        self.act_ai.setEnabled(False)
        fit_menu.addAction(self.act_ai)
        self.act_bootstrap = QtGui.QAction(tr("fit.bootstrap"), self)
        self.act_bootstrap.triggered.connect(self.on_bootstrap)
        self.act_bootstrap.setEnabled(False)
        fit_menu.addAction(self.act_bootstrap)
        self.act_profile = QtGui.QAction(tr("fit.profile_likelihood"), self)
        self.act_profile.triggered.connect(self.on_profile_likelihood)
        self.act_profile.setEnabled(False)
        fit_menu.addAction(self.act_profile)
        self.act_batch = QtGui.QAction(tr("fit.batch_fit"), self)
        self.act_batch.triggered.connect(self.on_batch_fit)
        fit_menu.addAction(self.act_batch)
        fit_menu.addSeparator()
        # Modos (radio): Discreto / P(BHF) — coincide con el combobox lateral.
        self.mode_action_group = QtGui.QActionGroup(self)
        act_discrete = QtGui.QAction(tr("options.discrete_sextets"), self, checkable=True)
        act_discrete.setChecked(True)
        act_discrete.triggered.connect(lambda _c: self.mode_combo.setCurrentIndex(0))
        fit_menu.addAction(act_discrete); self.mode_action_group.addAction(act_discrete)
        act_pbhf = QtGui.QAction(tr("options.distribution_bhf"), self, checkable=True)
        act_pbhf.triggered.connect(lambda _c: self.mode_combo.setCurrentIndex(1))
        fit_menu.addAction(act_pbhf); self.mode_action_group.addAction(act_pbhf)
        self._mode_menu_actions = [act_discrete, act_pbhf]
        fit_menu.addSeparator()
        # Submenú de opciones avanzadas (igual estructura que la GUI Tk).
        adv_menu = fit_menu.addMenu(tr("options.advanced_fit"))
        # Perfil de línea
        prof_menu = adv_menu.addMenu(tr("options.line_profile"))
        self.profile_action_group = QtGui.QActionGroup(self)
        for kind, key in (("Lorentziana", "options.profile_lorentzian"),
                          ("Voigt", "options.profile_voigt")):
            a = QtGui.QAction(tr(key), self, checkable=True)
            if kind == "Lorentziana":
                a.setChecked(True)
            a.triggered.connect(lambda _c, k=kind: self.calib._set_line_profile(k))
            prof_menu.addAction(a); self.profile_action_group.addAction(a)
        # Verosimilitud
        lik_menu = adv_menu.addMenu(tr("options.likelihood"))
        self.likelihood_action_group = QtGui.QActionGroup(self)
        for val, key in (("gauss", "options.likelihood_gauss"),
                          ("poisson", "options.likelihood_poisson")):
            a = QtGui.QAction(tr(key), self, checkable=True)
            if val == self.likelihood:
                a.setChecked(True)
            a.triggered.connect(lambda _c=False, v=val: setattr(self, "likelihood", v))
            lik_menu.addAction(a); self.likelihood_action_group.addAction(a)
        # Pérdida robusta
        loss_menu = adv_menu.addMenu(tr("options.robust_loss"))
        self.loss_action_group = QtGui.QActionGroup(self)
        for val, key in (("linear", "options.loss_linear"),
                          ("soft_l1", "options.loss_soft_l1"),
                          ("huber", "options.loss_huber")):
            a = QtGui.QAction(tr(key), self, checkable=True)
            if val == self.robust_loss:
                a.setChecked(True)
            a.triggered.connect(lambda _c=False, v=val: setattr(self, "robust_loss", v))
            loss_menu.addAction(a); self.loss_action_group.addAction(a)
        # Propagar σ calibración (check)
        self.act_propagate = QtGui.QAction(tr("options.propagate_calib"), self,
                                            checkable=True)
        self.act_propagate.setChecked(self.propagate_calib)
        self.act_propagate.toggled.connect(
            lambda b: setattr(self, "propagate_calib", bool(b)))
        adv_menu.addAction(self.act_propagate)
        # Optimización global DE (check)
        self.act_global_opt = QtGui.QAction(tr("options.global_opt"), self,
                                             checkable=True)
        self.act_global_opt.setChecked(self.global_opt)
        self.act_global_opt.toggled.connect(
            lambda b: setattr(self, "global_opt", bool(b)))
        adv_menu.addAction(self.act_global_opt)
        # Modelo de absorbente
        abs_menu = adv_menu.addMenu(tr("absorber.model_label"))
        self.absorber_action_group = QtGui.QActionGroup(self)
        for val, key in (("thin", "absorber.thin"),
                          ("thickness", "absorber.thickness")):
            a = QtGui.QAction(tr(key), self, checkable=True)
            if val == self.absorber_model:
                a.setChecked(True)
            a.triggered.connect(lambda _c=False, v=val: setattr(self, "absorber_model", v))
            abs_menu.addAction(a); self.absorber_action_group.addAction(a)
        adv_menu.addSeparator()
        # P(BHF) extras
        self.act_add_sharp = QtGui.QAction(tr("options.add_sharp"), self,
                                            checkable=True)
        self.act_add_sharp.setChecked(self.dist_use_sharp)
        self.act_add_sharp.toggled.connect(self._set_dist_use_sharp)
        adv_menu.addAction(self.act_add_sharp)
        self.act_refine_global = QtGui.QAction(tr("options.refine_global"), self,
                                                checkable=True)
        self.act_refine_global.setChecked(self.dist_refine_global)
        self.act_refine_global.toggled.connect(self._set_dist_refine_global)
        adv_menu.addAction(self.act_refine_global)
        fit_menu.addSeparator()
        act_free_all = QtGui.QAction(tr("fit.free_all"), self)
        act_free_all.triggered.connect(lambda: self._set_all_fixed(False))
        fit_menu.addAction(act_free_all)
        act_fix_all = QtGui.QAction(tr("fit.fix_all"), self)
        act_fix_all.triggered.connect(lambda: self._set_all_fixed(True))
        fit_menu.addAction(act_fix_all)
        fit_menu.addSeparator()
        act_constraints = QtGui.QAction(tr("options.constraints"), self)
        act_constraints.triggered.connect(self.on_constraints)
        fit_menu.addAction(act_constraints)
        act_presets = QtGui.QAction(tr("options.physical_presets"), self)
        act_presets.triggered.connect(self.on_physical_presets)
        fit_menu.addAction(act_presets)
        self.act_lcurve = QtGui.QAction(tr("bhf.lcurve_alpha"), self)
        self.act_lcurve.triggered.connect(self.on_lcurve)
        self.act_lcurve.setEnabled(False)
        fit_menu.addAction(self.act_lcurve)

        # ── Opciones (menú clásico Tk) ───────────────────────────────────
        options_menu = mb.addMenu(tr("menu.options"))
        opt_discrete = QtGui.QAction(tr("options.discrete_sextets"), self, checkable=True)
        opt_discrete.setChecked(True)
        opt_discrete.triggered.connect(lambda _c=False: self.mode_combo.setCurrentIndex(0))
        options_menu.addAction(opt_discrete)
        self.mode_action_group.addAction(opt_discrete)
        opt_pbhf = QtGui.QAction(tr("options.distribution_bhf"), self, checkable=True)
        opt_pbhf.triggered.connect(lambda _c=False: self.mode_combo.setCurrentIndex(1))
        options_menu.addAction(opt_pbhf)
        self.mode_action_group.addAction(opt_pbhf)
        self._mode_menu_actions.extend([opt_discrete, opt_pbhf])
        options_menu.addSeparator()
        self.act_opt_show_residual = QtGui.QAction(tr("options.show_residual"), self,
                                                   checkable=True, checked=self._show_residual_pref)
        self.act_opt_show_residual.toggled.connect(lambda checked: getattr(self, "act_show_residual", self.act_opt_show_residual).setChecked(checked))
        options_menu.addAction(self.act_opt_show_residual)
        self.act_opt_show_legend = QtGui.QAction(tr("options.show_legend"), self, checkable=True, checked=True)
        self.act_opt_show_legend.toggled.connect(lambda checked: getattr(self, "act_show_legend", self.act_opt_show_legend).setChecked(checked))
        options_menu.addAction(self.act_opt_show_legend)
        options_menu.addSeparator()
        opt_profile_menu = options_menu.addMenu(tr("options.line_profile"))
        for kind, key in (("Lorentziana", "options.profile_lorentzian"), ("Voigt", "options.profile_voigt")):
            a = QtGui.QAction(tr(key), self, checkable=True)
            if kind == self.calib.line_profile:
                a.setChecked(True)
            a.triggered.connect(lambda _c=False, k=kind: self.calib._set_line_profile(k))
            opt_profile_menu.addAction(a)
            self.profile_action_group.addAction(a)
        options_menu.addSeparator()
        self.act_opt_add_sharp = QtGui.QAction(tr("options.add_sharp"), self, checkable=True)
        self.act_opt_add_sharp.toggled.connect(self._set_dist_use_sharp)
        options_menu.addAction(self.act_opt_add_sharp)
        self.act_opt_refine_global = QtGui.QAction(tr("options.refine_global"), self, checkable=True)
        self.act_opt_refine_global.toggled.connect(self._set_dist_refine_global)
        options_menu.addAction(self.act_opt_refine_global)
        options_menu.addSeparator()
        opt_constraints = QtGui.QAction(tr("options.constraints"), self)
        opt_constraints.triggered.connect(self.on_constraints)
        options_menu.addAction(opt_constraints)
        opt_presets = QtGui.QAction(tr("options.physical_presets"), self)
        opt_presets.triggered.connect(self.on_physical_presets)
        options_menu.addAction(opt_presets)
        options_menu.addSeparator()
        opt_theme_menu = options_menu.addMenu(tr("options.theme"))
        for style_name in QtWidgets.QStyleFactory.keys():
            a = QtGui.QAction(style_name, self, checkable=True)
            if style_name.lower() == "fusion":
                a.setChecked(True)
            a.triggered.connect(lambda _c=False, s=style_name: self._set_qt_style(s))
            opt_theme_menu.addAction(a)

        # ── Vista ────────────────────────────────────────────────────────
        view_menu = mb.addMenu(tr("menu.view"))
        self.act_show_residual = QtGui.QAction(tr("options.show_residual"), self,
                                                checkable=True, checked=self._show_residual_pref)
        self.act_show_residual.toggled.connect(self._on_show_residual_toggled)
        self.act_show_residual.toggled.connect(lambda _: self._refresh_plot())
        self.act_show_residual.toggled.connect(lambda checked: self.act_opt_show_residual.setChecked(checked) if hasattr(self, "act_opt_show_residual") and self.act_opt_show_residual.isChecked() != checked else None)
        view_menu.addAction(self.act_show_residual)
        self.act_show_legend = QtGui.QAction(tr("options.show_legend"), self,
                                              checkable=True, checked=True)
        self.act_show_legend.toggled.connect(lambda _: self._refresh_plot())
        self.act_show_legend.toggled.connect(lambda checked: self.act_opt_show_legend.setChecked(checked) if hasattr(self, "act_opt_show_legend") and self.act_opt_show_legend.isChecked() != checked else None)
        view_menu.addAction(self.act_show_legend)
        view_menu.addSeparator()
        # Tema UI (QStyle de Qt). Por defecto Fusion.
        theme_menu = view_menu.addMenu(tr("options.theme"))
        self.theme_action_group = QtGui.QActionGroup(self)
        from PySide6 import QtWidgets as _qw
        available_styles = _qw.QStyleFactory.keys()
        for style_name in available_styles:
            a = QtGui.QAction(style_name, self, checkable=True)
            if style_name.lower() == "fusion":
                a.setChecked(True)
            a.triggered.connect(lambda _c=False, s=style_name: self._set_qt_style(s))
            theme_menu.addAction(a); self.theme_action_group.addAction(a)
        style_menu = view_menu.addMenu(tr("options.plot_style"))
        self.style_action_group = QtGui.QActionGroup(self)
        for value, label_key in (
            ("classic", "plot_style.classic"),
            ("modern", "plot_style.modern"),
            ("publication", "plot_style.publication"),
            ("dark", "plot_style.dark"),
        ):
            act = QtGui.QAction(tr(label_key), self, checkable=True)
            if value == self.plot_style_name:
                act.setChecked(True)
            act.triggered.connect(lambda _checked=False, v=value: self._set_plot_style(v))
            style_menu.addAction(act)
            self.style_action_group.addAction(act)

        # Tema de color de la interfaz (paleta de la aplicación).
        color_menu = view_menu.addMenu(tr("options.color_theme", default="Tema de color"))
        self.color_theme_group = QtGui.QActionGroup(self)
        for value, theme in COLOR_THEMES.items():
            act = QtGui.QAction(theme.get("label", value), self, checkable=True)
            if value == self.color_theme:
                act.setChecked(True)
            act.triggered.connect(lambda _checked=False, v=value: self._apply_color_theme(v))
            color_menu.addAction(act)
            self.color_theme_group.addAction(act)
        lang_menu = view_menu.addMenu(tr("menu.language"))
        self.lang_action_group = QtGui.QActionGroup(self)
        current_lang = get_language()
        for code, name in available_languages().items():
            act = QtGui.QAction(name, self, checkable=True)
            act.setChecked(code == current_lang)
            act.triggered.connect(lambda _checked=False, c=code: self._set_language(c))
            lang_menu.addAction(act)
            self.lang_action_group.addAction(act)
        view_menu.addSeparator()
        act_configure_layout = QtGui.QAction(tr("view.configure_layout"), self)
        act_configure_layout.triggered.connect(self.on_configure_layout)
        view_menu.addAction(act_configure_layout)

        # ── Ayuda ────────────────────────────────────────────────────────
        help_menu = mb.addMenu(tr("menu.help"))
        act_help = QtGui.QAction(tr("help.open"), self)
        act_help.setShortcut("F1")
        act_help.triggered.connect(self.on_help)
        help_menu.addAction(act_help)
        act_about = QtGui.QAction(tr("help.about"), self)
        act_about.triggered.connect(self.on_about)
        help_menu.addAction(act_about)
        help_menu.addSeparator()
        act_changelog = QtGui.QAction(tr("help.changelog"), self)
        act_changelog.triggered.connect(self.on_changelog)
        help_menu.addAction(act_changelog)
        act_check_updates = QtGui.QAction(tr("help.check_updates"), self)
        act_check_updates.triggered.connect(self.on_check_updates)
        help_menu.addAction(act_check_updates)
        act_configure_updates = QtGui.QAction(tr("help.configure_updates"), self)
        act_configure_updates.triggered.connect(self.on_configure_updates)
        help_menu.addAction(act_configure_updates)


    def _set_dist_use_sharp(self, enabled: bool) -> None:
        self.dist_use_sharp = bool(enabled)
        for attr in ("act_add_sharp", "act_opt_add_sharp"):
            act = getattr(self, attr, None)
            if act is not None and act.isChecked() != self.dist_use_sharp:
                act.blockSignals(True)
                act.setChecked(self.dist_use_sharp)
                act.blockSignals(False)
        if hasattr(self, "dist_panel") and self.dist_panel.use_sharp.isChecked() != self.dist_use_sharp:
            self.dist_panel.use_sharp.blockSignals(True)
            self.dist_panel.use_sharp.setChecked(self.dist_use_sharp)
            self.dist_panel.use_sharp.blockSignals(False)
        # En distribución, los sextetes solo se ven si se suman como nítidas.
        if hasattr(self, "_using_tabs") and self._using_tabs is not None:
            self._sync_component_count(self.n_components_spin.value())
            self._check_layout()
        self._simulate_enabled = True
        self._refresh_plot()

    def _set_dist_refine_global(self, enabled: bool) -> None:
        self.dist_refine_global = bool(enabled)
        for attr in ("act_refine_global", "act_opt_refine_global"):
            act = getattr(self, attr, None)
            if act is not None and act.isChecked() != self.dist_refine_global:
                act.blockSignals(True)
                act.setChecked(self.dist_refine_global)
                act.blockSignals(False)
        if hasattr(self, "dist_panel") and self.dist_panel.refine_global.isChecked() != self.dist_refine_global:
            self.dist_panel.refine_global.blockSignals(True)
            self.dist_panel.refine_global.setChecked(self.dist_refine_global)
            self.dist_panel.refine_global.blockSignals(False)
        self._simulate_enabled = True
        self._refresh_plot()

    def _set_language(self, code: str) -> None:
        set_language(code)
        # Persistir
        try:
            import json
            current = {}
            if SETTINGS_PATH.exists():
                try:
                    current = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                except Exception:
                    pass
            current["ui_language"] = code
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps(current, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception:
            pass
        QtWidgets.QMessageBox.information(
            self, tr("language.restart_title"), tr("language.restart_message"))

    def _all_presets(self) -> dict[str, dict]:
        """Combina presets Tk + customs del usuario."""
        try:
            from layout.presets import PRESETS
        except Exception:
            PRESETS = {}
        out: dict[str, dict] = dict(PRESETS)
        for name, spec in self.custom_layouts.items():
            out[name] = spec
        return out

    def _insert_panel_widget(self, layout: QtWidgets.QVBoxLayout, widget: QtWidgets.QWidget) -> None:
        """Inserta un panel antes del stretch final de una columna, si existe."""
        widget.setParent(None)
        pos = layout.count()
        if pos and layout.itemAt(pos - 1).spacerItem() is not None:
            pos -= 1
        layout.insertWidget(pos, widget)
        widget.show()

    def _collect_layout_spec(self, columns: dict[str, list[str]],
                             left_width: int, right_width: int,
                             description: str = "Personalizado") -> dict:
        known = set(getattr(self, "_layout_panel_widgets", {}))
        out = {
            "description": description,
            "left": [pid for pid in columns.get("left", []) if pid in known],
            "center": [pid for pid in columns.get("center", []) if pid in known],
            "right": [pid for pid in columns.get("right", []) if pid in known],
            "left_width": int(left_width),
            "right_width": int(right_width),
        }
        # Los paneles no asignados a ninguna columna quedan "apartados" (no se
        # muestran), igual que el pool de Disponibles del configurador Tk.
        return out

    def _apply_panel_layout(self, spec: dict) -> None:
        if not hasattr(self, "_layout_panel_widgets"):
            return
        right_w = int(spec.get("right_width", 0))
        columns = {
            "left": list(spec.get("left", [])),
            "center": list(spec.get("center", [])),
            "right": list(spec.get("right", [])),
        }
        # Los paneles que no estén en ninguna columna quedan apartados: se
        # ocultan (equivalente al pool 'Disponibles' del configurador Tk).
        assigned = set(columns["left"]) | set(columns["center"]) | set(columns["right"])
        for pid, widget in self._layout_panel_widgets.items():
            if pid not in assigned:
                widget.setParent(None)
                widget.hide()
        for pid in columns["left"]:
            if pid in self._layout_panel_widgets:
                self._insert_panel_widget(self._left_panels_layout,
                                          self._layout_panel_widgets[pid])
        for pid in columns["center"]:
            if pid in self._layout_panel_widgets:
                self._insert_panel_widget(self._center_top_layout,
                                          self._layout_panel_widgets[pid])
        right_target = (self._right_panels_layout if right_w > 0
                        else self._center_bottom_layout)
        for pid in columns["right"]:
            if pid in self._layout_panel_widgets:
                self._insert_panel_widget(right_target, self._layout_panel_widgets[pid])
        self._center_top_widget.setVisible(bool(columns["center"]))
        self._center_bottom_widget.setVisible(right_w == 0 and bool(columns["right"]))

        # Igual que el panel Tk modular (_force_tabs en la columna central):
        # si la simulación queda en el centro o anclada debajo del gráfico (poca
        # altura), se fuerzan pestañas; el apilado adaptativo solo se permite en
        # una columna lateral (izquierda o derecha con anchura propia).
        sim_in_center = "sim_controls" in columns["center"]
        sim_below_graph = (right_w == 0 and "sim_controls" in columns["right"])
        self._sim_force_tabs = bool(sim_in_center or sim_below_graph)
        self._check_layout()

    def _layout_preset_with_available_space(self, name: str) -> str:
        """Coloca la simulación a la derecha si no cabe bien debajo del gráfico."""
        if name == "Estándar":
            screen = QtGui.QGuiApplication.primaryScreen()
            width = screen.availableGeometry().width() if screen is not None else self.width()
            if width >= 1450:
                return "Tres columnas"
        return name

    def _apply_layout_preset(self, name: str) -> None:
        """Aplica preset al QSplitter principal usando 3 columnas."""
        spec = self._all_presets().get(name, {})
        self._apply_panel_layout(spec)
        left_w = int(spec.get("left_width", 430))
        right_w = int(spec.get("right_width", 0))
        total_w = max(900, self.width() - 20)
        center_w = max(500, total_w - left_w - right_w)
        sizes = [left_w, center_w, max(0, right_w)]
        if hasattr(self, "_left_scroll"):
            self._left_scroll.setMinimumWidth(left_w)
            self._left_scroll.setMaximumWidth(left_w)
        if hasattr(self, "_right_column"):
            self._right_column.setVisible(right_w > 0)
            self._right_column.setMinimumWidth(right_w if right_w > 0 else 0)
            self._right_column.setMaximumWidth(right_w if right_w > 0 else 0)
        if hasattr(self, "_main_splitter"):
            self._main_splitter.setSizes(sizes)
        self.layout_preset = name
        self._save_settings()

    def on_configure_layout(self) -> None:
        """Editor visual de presets con columnas Izquierda | Centro | Derecha."""
        try:
            from layout.presets import PRESETS, DEFAULT_PRESET
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, tr("view.configure_layout"),
                f"layout.presets no disponible: {exc}")
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("view.configure_layout"))
        dlg.resize(980, 640)
        v = QtWidgets.QVBoxLayout(dlg)
        v.addWidget(QtWidgets.QLabel(
            "<i>Elige un preset o mueve paneles entre <b>Disponibles</b> y las "
            "<b>3 columnas</b>. Los paneles que dejes en <b>Disponibles</b> "
            "quedan apartados (no se muestran). La columna derecha con anchura 0 "
            "se oculta y sus paneles se anclan debajo de la gráfica.</i>"))

        list_w = QtWidgets.QListWidget()
        v.addWidget(list_w, stretch=1)

        left_width_spin = QtWidgets.QSpinBox()
        left_width_spin.setRange(200, 900); left_width_spin.setSuffix("  px izquierda")
        right_width_spin = QtWidgets.QSpinBox()
        right_width_spin.setRange(0, 900); right_width_spin.setSuffix("  px derecha")

        panel_names = dict(getattr(self, "_layout_panel_names", {}))
        panel_lists: dict[str, QtWidgets.QListWidget] = {}

        def clear_selection_except(active: QtWidgets.QListWidget) -> None:
            for lw_col in panel_lists.values():
                if lw_col is not active:
                    lw_col.clearSelection()

        def selected_column() -> tuple[str, QtWidgets.QListWidget] | tuple[None, None]:
            for key, lw_col in panel_lists.items():
                if lw_col.currentItem() is not None:
                    return key, lw_col
            return None, None

        def columns_from_lists() -> dict[str, list[str]]:
            return {
                key: [lw_col.item(i).data(QtCore.Qt.UserRole)
                      for i in range(lw_col.count())]
                for key, lw_col in panel_lists.items()
            }

        def fill_columns(spec: dict) -> None:
            for lw_col in panel_lists.values():
                lw_col.clear()
            used: set[str] = set()
            for key in ("left", "center", "right"):
                for pid in spec.get(key, []):
                    if pid in panel_names and pid not in used:
                        item = QtWidgets.QListWidgetItem(panel_names.get(pid, pid))
                        item.setData(QtCore.Qt.UserRole, pid)
                        panel_lists[key].addItem(item)
                        used.add(pid)
            for pid, label in panel_names.items():
                if pid not in used:
                    item = QtWidgets.QListWidgetItem(label)
                    item.setData(QtCore.Qt.UserRole, pid)
                    panel_lists["available"].addItem(item)
            left_width_spin.setValue(int(spec.get("left_width", 430)))
            right_width_spin.setValue(int(spec.get("right_width", 0)))

        def current_spec(description: str = "Personalizado") -> dict:
            return self._collect_layout_spec(
                columns_from_lists(), left_width_spin.value(), right_width_spin.value(),
                description=description,
            )

        def refresh_list(select_name: str | None = None) -> None:
            list_w.clear()
            all_presets = self._all_presets()
            for name, spec in all_presets.items():
                kind = "(custom)" if name in self.custom_layouts else "(Tk)"
                lw = spec.get("left_width", "—")
                rw = spec.get("right_width", "—")
                txt = (f"{name}  {kind}  ·  izquierda={lw}px  ·  "
                       f"derecha={rw}px  ·  {spec.get('description', '')}")
                item = QtWidgets.QListWidgetItem(txt)
                item.setData(QtCore.Qt.UserRole, name)
                list_w.addItem(item)
                target = select_name or (self.layout_preset if self.layout_preset in all_presets else DEFAULT_PRESET)
                if name == target:
                    list_w.setCurrentItem(item)

        # Editor visual de columnas.
        edit_box = QtWidgets.QGroupBox("Editor de columnas")
        edit_v = QtWidgets.QVBoxLayout(edit_box)
        edit_row = QtWidgets.QHBoxLayout()
        for key, title in (("available", "Disponibles (sin asignar)"),
                           ("left", "Izquierda"), ("center", "Centro"),
                           ("right", "Derecha")):
            col = QtWidgets.QVBoxLayout()
            col.addWidget(QtWidgets.QLabel(f"<b>{title}</b>"))
            lw_col = QtWidgets.QListWidget()
            lw_col.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            lw_col.currentItemChanged.connect(lambda _cur, _prev, lw=lw_col: clear_selection_except(lw))
            col.addWidget(lw_col)
            edit_row.addLayout(col)
            panel_lists[key] = lw_col
        edit_v.addLayout(edit_row)

        move_row = QtWidgets.QHBoxLayout()
        for key, label in (("available", "Apartar"),
                           ("left", "Mover a izquierda"),
                           ("center", "Mover al centro"),
                           ("right", "Mover a derecha")):
            btn = QtWidgets.QPushButton(label)
            def _move(_=False, target=key):
                _src_key, src = selected_column()
                if src is None:
                    return
                item = src.takeItem(src.currentRow())
                panel_lists[target].addItem(item)
                panel_lists[target].setCurrentItem(item)
            btn.clicked.connect(_move)
            move_row.addWidget(btn)
        btn_up = QtWidgets.QPushButton("Subir")
        btn_down = QtWidgets.QPushButton("Bajar")
        def _reorder(delta: int) -> None:
            _key, lw_col = selected_column()
            if lw_col is None:
                return
            row = lw_col.currentRow()
            new_row = row + delta
            if new_row < 0 or new_row >= lw_col.count():
                return
            item = lw_col.takeItem(row)
            lw_col.insertItem(new_row, item)
            lw_col.setCurrentItem(item)
        btn_up.clicked.connect(lambda: _reorder(-1))
        btn_down.clicked.connect(lambda: _reorder(+1))
        move_row.addWidget(btn_up); move_row.addWidget(btn_down)
        edit_v.addLayout(move_row)

        width_row = QtWidgets.QHBoxLayout()
        width_row.addWidget(QtWidgets.QLabel("Anchos:"))
        width_row.addWidget(left_width_spin)
        width_row.addWidget(right_width_spin)
        width_row.addStretch(1)
        edit_v.addLayout(width_row)
        v.addWidget(edit_box, stretch=2)

        def on_preset_changed(item: QtWidgets.QListWidgetItem | None) -> None:
            if item is None:
                return
            spec = self._all_presets().get(item.data(QtCore.Qt.UserRole), {})
            fill_columns(spec)

        list_w.currentItemChanged.connect(lambda cur, _prev: on_preset_changed(cur))
        refresh_list()
        on_preset_changed(list_w.currentItem())

        # Guardar el diseño visual actual en Custom 1 / Custom 2.
        for slot in ("Custom 1", "Custom 2"):
            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel(f"<b>{slot}</b>:"))
            desc_e = QtWidgets.QLineEdit(
                self.custom_layouts.get(slot, {}).get(
                    "description", "Personalizado por el usuario"))
            row.addWidget(desc_e, stretch=1)
            btn = QtWidgets.QPushButton("Guardar diseño mostrado")
            def _save(_=False, _slot=slot, _desc=desc_e):
                self.custom_layouts[_slot] = current_spec(
                    _desc.text().strip() or "Personalizado")
                self._save_settings()
                refresh_list(_slot)
            btn.clicked.connect(_save)
            row.addWidget(btn)
            v.addLayout(row)

        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        item = list_w.currentItem()
        if item is None:
            return
        name = item.data(QtCore.Qt.UserRole)
        shown = current_spec(self._all_presets().get(name, {}).get("description", "Personalizado"))
        selected = self._all_presets().get(name, {})
        comparable = {k: selected.get(k, [] if k in ("left", "center", "right") else 0)
                      for k in ("left", "center", "right", "left_width", "right_width")}
        shown_comp = {k: shown.get(k) for k in comparable}
        if shown_comp != comparable:
            name = name if name in self.custom_layouts else "Custom 1"
            shown["description"] = shown.get("description") or "Personalizado"
            self.custom_layouts[name] = shown
            self._save_settings()
        self._apply_layout_preset(name)

    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.clear()
        if not self.recent_files:
            act = QtGui.QAction("(vacío)", self); act.setEnabled(False)
            self.recent_menu.addAction(act); return
        for p in self.recent_files:
            act = QtGui.QAction(Path(p).name, self)
            act.setStatusTip(p)
            act.triggered.connect(lambda _checked=False, path=p: self._open_recent(path))
            self.recent_menu.addAction(act)

    def _open_recent(self, path: str) -> None:
        try:
            self._load_file(Path(path))
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, tr("file.open"), str(exc))

    def _add_recent(self, path: Path) -> None:
        s = str(path.resolve())
        if s in self.recent_files:
            self.recent_files.remove(s)
        self.recent_files.insert(0, s)
        self.recent_files = self.recent_files[:5]
        self._rebuild_recent_menu()
        self._save_settings()

    def _set_qt_style(self, style_name: str) -> None:
        try:
            QtWidgets.QApplication.instance().setStyle(style_name)
        except Exception:
            return
        self.qt_style = style_name
        try:
            import json
            current = {}
            if SETTINGS_PATH.exists():
                current = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            current["qt_style"] = style_name
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _set_plot_style(self, name: str) -> None:
        self.plot_style_name = name
        apply_rc(name)
        self._save_settings()
        self._refresh_plot()

    def _apply_color_theme(self, name: str, persist: bool = True) -> None:
        """Aplica un tema de color (paleta + acentos) a toda la interfaz."""
        if name not in COLOR_THEMES:
            name = "blue"
        self.color_theme = name
        theme = COLOR_THEMES[name]
        app = QtWidgets.QApplication.instance()

        if name == "system":
            # Aspecto nativo: paleta estándar del estilo y sin hoja de estilos.
            if app is not None:
                app.setPalette(QtWidgets.QApplication.style().standardPalette())
            self.setStyleSheet("")
            accent, accent_text, accent_sub, title = "#075985", "#ffffff", "#dff6ff", "#075985"
        else:
            def c(h: str) -> QtGui.QColor:
                return QtGui.QColor(h)
            pal = QtGui.QPalette()
            pal.setColor(QtGui.QPalette.Window, c(theme["window"]))
            pal.setColor(QtGui.QPalette.WindowText, c(theme["text"]))
            pal.setColor(QtGui.QPalette.Base, c(theme["base"]))
            pal.setColor(QtGui.QPalette.AlternateBase, c(theme["alt_base"]))
            pal.setColor(QtGui.QPalette.Text, c(theme["text"]))
            pal.setColor(QtGui.QPalette.Button, c(theme["button"]))
            pal.setColor(QtGui.QPalette.ButtonText, c(theme["button_text"]))
            pal.setColor(QtGui.QPalette.Highlight, c(theme["highlight"]))
            pal.setColor(QtGui.QPalette.HighlightedText, c(theme["highlight_text"]))
            pal.setColor(QtGui.QPalette.ToolTipBase, c(theme["base"]))
            pal.setColor(QtGui.QPalette.ToolTipText, c(theme["text"]))
            # Grupo "Disabled": los campos no modificables se ven claramente
            # apagados (antes no se distinguían de los editables).
            dis_text = c(theme.get("disabled_text", "#9aa0a6"))
            dis_base = c(theme.get("disabled_base", theme["window"]))
            for role in (QtGui.QPalette.WindowText, QtGui.QPalette.Text,
                         QtGui.QPalette.ButtonText):
                pal.setColor(QtGui.QPalette.Disabled, role, dis_text)
            pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Base, dis_base)
            pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Button, dis_base)
            pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Highlight, dis_base)
            if app is not None:
                app.setPalette(pal)
            accent = theme["accent"]; accent_text = theme["accent_text"]
            accent_sub = theme["accent_sub"]; title = theme["title"]
            dt = theme.get("disabled_text", "#9aa0a6")
            db = theme.get("disabled_base", theme["window"])
            # Refuerzo por hoja de estilos: con stylesheet activa, Qt no aplica
            # el grupo Disabled de la paleta a algunos widgets, así que se
            # explicita el aspecto de los campos deshabilitados.
            self.setStyleSheet(
                "QGroupBox { font-weight: 600; margin-top: 6px; }"
                f"QGroupBox::title {{ color: {title}; subcontrol-origin: margin; left: 8px; }}"
                f"QDoubleSpinBox:disabled, QSpinBox:disabled, QLineEdit:disabled, "
                f"QComboBox:disabled {{ color: {dt}; background: {db}; }}"
                f"QLabel:disabled, QCheckBox:disabled, QRadioButton:disabled {{ color: {dt}; }}"
                f"QSlider:disabled {{ background: transparent; }}"
            )

        # La cabecera siempre con su banner de acento, acorde al tema.
        if hasattr(self, "header_box"):
            self.header_box.setStyleSheet(
                f"#AppHeader {{ background: {accent}; border-radius: 4px; }}"
                f"#AppHeader QLabel {{ background: transparent; color: {accent_sub}; font-size: 9pt; }}"
                f"#AppHeaderTitle {{ color: {accent_text}; font-size: 16pt; font-weight: bold; }}"
            )
        if persist:
            self._save_settings()

    # ── Persistencia mínima ──────────────────────────────────────────────
    def _load_settings(self) -> None:
        try:
            import json
            if SETTINGS_PATH.exists():
                data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                style = data.get("plot_style")
                if style in ("classic", "modern", "publication", "dark"):
                    self.plot_style_name = style
                lang = data.get("ui_language")
                if lang and lang in available_languages():
                    set_language(lang)
                recent = data.get("recent_files")
                if isinstance(recent, list):
                    self.recent_files = [str(p) for p in recent
                                          if isinstance(p, str) and Path(p).exists()][:5]
                ctheme = data.get("color_theme")
                if ctheme in COLOR_THEMES:
                    self.color_theme = ctheme
                if isinstance(data.get("show_residual"), bool):
                    self._show_residual_pref = data["show_residual"]
                preset = data.get("layout_preset")
                if isinstance(preset, str) and preset:
                    self.layout_preset = preset
                custom = data.get("custom_layouts")
                if isinstance(custom, dict):
                    self.custom_layouts = {
                        str(k): v for k, v in custom.items()
                        if isinstance(v, dict) and "left_width" in v
                    }
        except Exception:
            pass

    def _save_settings(self) -> None:
        try:
            import json
            current = {}
            if SETTINGS_PATH.exists():
                try:
                    current = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                except Exception:
                    current = {}
            current["plot_style"] = self.plot_style_name
            current["color_theme"] = self.color_theme
            if hasattr(self, "act_show_residual"):
                current["show_residual"] = bool(self.act_show_residual.isChecked())
            current["recent_files"] = list(self.recent_files)
            current["layout_preset"] = self.layout_preset
            current["custom_layouts"] = dict(self.custom_layouts)
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps(current, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception:
            pass

    # ── Número de componentes ────────────────────────────────────────────
    def _on_n_components_changed(self, n_components: int) -> None:
        self._sync_component_count(n_components)
        self._check_layout()
        self._refresh_plot()

    def _component_visibility(self, n_components: int) -> tuple[bool, list[bool]]:
        """(is_dist, [visible_i…]) para los MAX componentes.

        En modo distribución los sextetes solo se muestran si está marcado
        'sumar componentes nítidas' (dist_use_sharp), igual que en Tk: sin
        nítidas, no aparecen los sextetes.
        """
        is_dist = self.is_distribution_mode if hasattr(self, "mode_combo") else False
        show_components = (not is_dist) or bool(getattr(self, "dist_use_sharp", False))
        vis = [(i <= n_components) and show_components
               for i in range(1, MAX_QT_COMPONENTS + 1)]
        return is_dist, vis

    def _sync_component_count(self, n_components: int) -> None:
        n_components = max(1, min(MAX_QT_COMPONENTS, int(n_components)))
        if hasattr(self, "n_components_spin") and self.n_components_spin.value() != n_components:
            self.n_components_spin.blockSignals(True)
            self.n_components_spin.setValue(n_components)
            self.n_components_spin.blockSignals(False)

        is_dist, vis = self._component_visibility(n_components)
        # El estado 'activo' refleja el número de componentes elegido, aunque el
        # panel esté oculto (en distribución sin nítidas se ocultan pero
        # conservan su estado para cuando se reactiven).
        for i, cp in enumerate(self.components_panels, start=1):
            cp.enabled.blockSignals(True)
            cp.enabled.setChecked(i <= n_components)
            cp.enabled.blockSignals(False)

        if self._using_tabs:
            self.comp_tabs.setTabVisible(0, is_dist)
            for i in range(1, MAX_QT_COMPONENTS + 1):
                self.comp_tabs.setTabVisible(i, vis[i - 1])
            # Al entrar en distribución se selecciona la pestaña de distribución
            # (índice 0); en discreto, la primera componente.
            self.comp_tabs.setCurrentIndex(0 if is_dist else 1)
        else:
            self.dist_panel.setVisible(is_dist)
            for i in range(1, MAX_QT_COMPONENTS + 1):
                frame = self._comp_stack_frames.get(i)
                if frame is not None:
                    frame.setVisible(vis[i - 1])

    def _rebuild_component_area(self, use_tabs: bool) -> None:
        """Reconstruye el área de componentes en modo pestañas o apilado.

        Reutiliza los mismos paneles (conservan su estado) reparentándolos
        entre el QTabWidget y el contenedor apilado.
        """
        if use_tabs == self._using_tabs:
            return
        # Saca todos los paneles de su contenedor actual.
        self.dist_panel.setParent(None)
        for cp in self.components_panels:
            cp.setParent(None)
        # Vacía el QTabWidget.
        while self.comp_tabs.count():
            self.comp_tabs.removeTab(0)
        # Vacía el layout apilado (descarta las envolturas tituladas).
        while self._comp_stack_layout.count():
            item = self._comp_stack_layout.takeAt(0)
            w = item.widget()
            if w is not None and w is not self.dist_panel:
                w.setParent(None)
                w.deleteLater()
        self._comp_stack_frames.clear()

        if use_tabs:
            self.comp_tabs.addTab(self.dist_panel, tr("tab.distribution_bhf"))
            for i, cp in enumerate(self.components_panels, start=1):
                self.comp_tabs.addTab(cp, tr("tab.component", idx=i))
            self.comp_tabs.setVisible(True)
            self.comp_stack.setVisible(False)
        else:
            self._comp_stack_layout.addWidget(self.dist_panel)
            for i, cp in enumerate(self.components_panels, start=1):
                box = QtWidgets.QGroupBox(tr("tab.component", idx=i))
                bl = QtWidgets.QVBoxLayout(box)
                bl.setContentsMargins(4, 4, 4, 4)
                bl.setSpacing(2)
                bl.addWidget(cp)
                cp.setVisible(True)
                self._comp_stack_frames[i] = box
                self._comp_stack_layout.addWidget(box)
            self._comp_stack_layout.addStretch(1)
            self.comp_tabs.setVisible(False)
            self.comp_stack.setVisible(True)

        self._using_tabs = use_tabs
        n = self.n_components_spin.value() if hasattr(self, "n_components_spin") else 1
        self._sync_component_count(n)

    def _check_layout(self) -> None:
        """Cambia entre apilado y pestañas según el espacio vertical disponible.

        Replica el comportamiento del panel Tk modular: apilado cuando cabe,
        pestañas cuando no. La histéresis (0.78 / 0.88) evita oscilaciones.
        """
        if getattr(self, "_using_tabs", None) is None or not hasattr(self, "n_components_spin"):
            return
        if getattr(self, "_in_layout_check", False):
            return
        # Si la simulación está en el centro o debajo del gráfico, siempre
        # pestañas (no hay altura para apilar sin recortar).
        if getattr(self, "_sim_force_tabs", False):
            if not self._using_tabs:
                self._in_layout_check = True
                try:
                    self._rebuild_component_area(use_tabs=True)
                finally:
                    self._in_layout_check = False
            return
        win_h = self.height()
        if win_h < 100:
            return
        n = self.n_components_spin.value()
        is_dist, vis = self._component_visibility(n)
        n_visible = sum(1 for v in vis if v)
        stacked_h = (_COMP_OVERHEAD_H + (_DIST_STACK_H if is_dist else 0)
                     + n_visible * _COMP_STACK_H)
        self._in_layout_check = True
        try:
            if self._using_tabs:
                if stacked_h < win_h * 0.78:
                    self._rebuild_component_area(use_tabs=False)
            else:
                if stacked_h > win_h * 0.88:
                    self._rebuild_component_area(use_tabs=True)
        finally:
            self._in_layout_check = False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._check_layout()

    # ── Cambio de modo ───────────────────────────────────────────────────
    def _on_mode_changed(self, idx: int) -> None:
        is_dist = (idx in (1, 2))
        is_deq = (idx == 2)
        self._sync_component_count(self.n_components_spin.value())
        # La visibilidad de dist_panel/sextetes la fija _sync_component_count
        # según el modo y el contenedor (apilado o pestañas).
        # Sincroniza el radio del menú Fit
        if hasattr(self, "_mode_menu_actions") and 0 <= idx < 2:
            self._mode_menu_actions[idx].setChecked(True)
        # Etiquetas según variable distribuida. P(ΔEQ) usa un BHF fijo
        # independiente, manteniendo ΔEQ como parámetro global para P(BHF).
        if is_dist:
            if is_deq:
                self.dist_panel.bmin.label.setText(tr("slider.dist_bmin_quad"))
                self.dist_panel.bmax.label.setText(tr("slider.dist_bmax_quad"))
                self.dist_panel.fixed_bhf.label.setText(tr("slider.dist_fixed_bhf_active", default="BHF fijo (T)"))
                self.dist_panel.fixed_bhf.setEnabled(True)
            else:
                self.dist_panel.bmin.label.setText(tr("slider.dist_bmin_bhf"))
                self.dist_panel.bmax.label.setText(tr("slider.dist_bmax_bhf"))
                self.dist_panel.fixed_bhf.label.setText(tr("slider.dist_fixed_bhf_inactive", default="BHF fijo (no usado en modo BHF)"))
                self.dist_panel.fixed_bhf.setEnabled(False)
        self._check_layout()
        self._refresh_plot()

    @property
    def is_distribution_mode(self) -> bool:
        return self.mode_combo.currentIndex() in (1, 2)

    @property
    def dist_variable(self) -> str:
        return "quad" if self.mode_combo.currentIndex() == 2 else "bhf"

    def _on_model_param_changed(self, *args) -> None:
        if not self._building:
            self._simulate_enabled = True
        self._sync_absorber_model_from_panel()
        self._refresh_plot()

    def _sync_absorber_model_from_panel(self, *args) -> None:
        if hasattr(self, "calib"):
            self.absorber_model = self.calib.absorber_model

    def _set_quick_action_buttons_enabled(self, enabled: bool) -> None:
        for name in ("btn_sim_fit", "btn_sim_auto_min", "btn_sim_ai"):
            btn = getattr(self, name, None)
            if btn is not None:
                btn.setEnabled(bool(enabled))

    def _on_fit_velocity_toggled(self, checked: bool) -> None:
        """Al activar 'Ajustar Vmax', fija automáticamente todos los BHF.

        El ajuste de velocidad solo es válido con el campo hiperfino fijo, así
        que se marcan como fijos los BHF de todas las componentes.
        """
        if not checked:
            return
        for cp in getattr(self, "components_panels", []):
            ctl = cp.params.get("bhf")
            if ctl is not None:
                ctl.set_fixed(True)
        self.statusBar().showMessage(
            tr("msg.fit_velocity_requires_bhf_fixed",
               default="Ajuste de Vmax: se han fijado los BHF automáticamente."),
            5000)

    def _on_show_residual_toggled(self, checked: bool) -> None:
        """Reserva o libera el espacio de la diferencia y persiste la opción."""
        if hasattr(self, "canvas"):
            self.canvas.residual_pref = bool(checked)
            # Sin fichero cargado, _refresh_plot no redibuja: actualiza el
            # marcador de 'sin fichero' con la nueva disposición.
            if self.file.velocity is None:
                self.canvas.show_no_file()
        self._save_settings()

    # ── Helpers UI ───────────────────────────────────────────────────────
    def _set_all_fixed(self, value: bool) -> None:
        self._building = True
        for ctl in (self.calib.baseline, self.calib.slope, self.calib.sat_scale):
            ctl.set_fixed(value)
        for cp in self.components_panels:
            for ctl in cp.params.values():
                ctl.set_fixed(value)
        self._building = False
        self._refresh_plot()

    def _fold_counts_for_center(self, center: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Dobla las cuentas con el mismo recorte de borde que la GUI Tk modular."""
        if self.file.counts is None:
            raise ValueError("No hay cuentas cargadas")
        folded, _pairs = fold_integer_or_half(self.file.counts, float(center))
        n = int(getattr(self, "_edge_trim", 0))
        if n > 0 and folded.size > 2 * n + 2:
            folded = folded[n:-n]
        norm = float(np.percentile(folded, 90)) if folded.size else 1.0
        norm = norm or 1.0
        sigma = np.sqrt(np.maximum(folded / 2.0, 1.0)) / norm
        y = folded / norm
        return folded, sigma, y

    def _velocity_for_folded(self, n_points: int, trim_edges: bool = True) -> np.ndarray:
        """Crea el eje de velocidad y recorta sus extremos si se recortó el folding."""
        vmax = abs(self.calib.vmax.value())
        if self.file.counts is None:
            return np.array([], dtype=float)
        full_n = self.file.counts.size // 2
        velocity = np.linspace(-vmax, vmax, full_n)
        n = int(getattr(self, "_edge_trim", 0)) if trim_edges else 0
        if n > 0 and velocity.size > 2 * n + 2 and n_points == velocity.size - 2 * n:
            velocity = velocity[n:-n]
        elif velocity.size != n_points:
            velocity = np.linspace(-vmax, vmax, n_points)
        return velocity

    def _refold_current_data(self, center: float) -> None:
        """Recalcula datos normalizados/sigma/eje cuando cambia el folding point."""
        if self.file.counts is None:
            return
        folded, sigma, y = self._fold_counts_for_center(center)
        self.file.folded = folded
        self.file.center = float(center)
        self.file.norm_factor = float(np.percentile(folded, 90)) if folded.size else 1.0
        self.file.norm_factor = self.file.norm_factor or 1.0
        self.file.sigma = sigma
        self.file.y_data = y
        self.file.velocity = self._velocity_for_folded(folded.size)

    def _on_center_value_changed(self, center: float) -> None:
        if self._building or self.file.counts is None:
            return
        self._refold_current_data(float(center))
        if self.file.path is not None:
            self.file_label.setText(f"<b>{self.file.path.name}</b><br>"
                                    f"{self.file.counts.size} canales · centro={float(center):.3f} · "
                                    f"norm={self.file.norm_factor:.4g}")
        self.statusBar().showMessage(f"Datos re-doblados con centro={float(center):.4f}", 3000)
        self._refresh_plot()

    # ── Resumen de estado y parámetros (paridad con la GUI Tk) ───────────
    def _active_components(self) -> list[ComponentPanel]:
        return [cp for cp in self.components_panels if cp.enabled.isChecked()]

    def active_param_keys(self) -> list[str]:
        keys = list(GLOBAL_PARAM_NAMES)
        if self.absorber_model == "thickness":
            keys.append("sat_scale")
        for cp in self._active_components():
            keys.extend(f"s{cp.idx}_{name}" for name in SEXTET_PARAM_NAMES)
            if cp.kind == "Sextete":
                keys.extend((f"s{cp.idx}_texture", f"s{cp.idx}_beta"))
        return keys

    def _fixed_param_keys(self) -> list[str]:
        fixed = []
        if self.calib.baseline.is_fixed():
            fixed.append("baseline")
        if self.calib.slope.is_fixed():
            fixed.append("slope")
        if self.absorber_model == "thickness" and self.calib.sat_scale.is_fixed():
            fixed.append("sat_scale")
        for cp in self._active_components():
            for name, ctl in cp.params.items():
                if ctl.is_fixed() and name in SEXTET_PARAM_NAMES:
                    fixed.append(f"s{cp.idx}_{name}")
        return fixed

    def _component_params_array(self, cp: ComponentPanel, values: dict[str, float] | None = None) -> np.ndarray:
        out = []
        for name in SEXTET_PARAM_NAMES:
            key = f"s{cp.idx}_{name}"
            out.append(float(values.get(key, cp.params[name].value())) if values else cp.params[name].value())
        return np.array(out, dtype=float)

    def component_area_from_params(self, kind: str, p: np.ndarray) -> float:
        if self.file.velocity is not None and self.file.velocity.size > 1:
            vmin = float(np.min(self.file.velocity))
            vmax = float(np.max(self.file.velocity))
            n = max(2000, int(self.file.velocity.size) * 8)
            v = np.linspace(vmin, vmax, n)
        else:
            v = np.linspace(-12.0, 12.0, 4000)
        return float(np.trapezoid(np.maximum(component_absorption(v, kind, p), 0.0), v))

    def component_area_percentages(
        self, values: dict[str, float] | None = None
    ) -> tuple[list[int], np.ndarray, np.ndarray]:
        active: list[int] = []
        areas: list[float] = []
        for cp in self._active_components():
            p_arr = self._component_params_array(cp, values)
            areas.append(max(0.0, self.component_area_from_params(cp.kind, p_arr)))
            active.append(cp.idx)
        area_arr = np.array(areas, dtype=float)
        total = float(np.sum(area_arr))
        pct = 100.0 * area_arr / total if total > 0 else np.zeros_like(area_arr)
        return active, area_arr, pct

    def component_percentage_errors(self) -> dict[int, float]:
        result = self.last_fit_result
        if result is None or result.cov is None or not result.free_keys:
            return {}
        base_values = dict(result.values)
        active, _areas, _pct0 = self.component_area_percentages(base_values)
        if not active:
            return {}
        jac = np.zeros((len(active), len(result.free_keys)), dtype=float)
        for j, key in enumerate(result.free_keys):
            if key not in base_values:
                continue
            x = float(base_values[key])
            step = max(1e-6, abs(x) * 1e-5)
            vals_p = base_values.copy(); vals_m = base_values.copy()
            vals_p[key] = x + step
            vals_m[key] = x - step
            _a, _ar, pct_p = self.component_area_percentages(vals_p)
            _a, _ar, pct_m = self.component_area_percentages(vals_m)
            jac[:, j] = (pct_p - pct_m) / (2.0 * step)
        try:
            cov_pct = jac @ result.cov @ jac.T
        except Exception:
            return {}
        errs = np.sqrt(np.maximum(np.diag(cov_pct), 0.0))
        return {idx: float(err) for idx, err in zip(active, errs)}

    def calibration_iso_ref(self) -> float | None:
        info = self.calibration_info
        if not info:
            return None
        value = info.get("isomer_shift")
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def calibration_uncertainty_text(self) -> str | None:
        if not self.calibration_info:
            return None
        for key in ("velocity_uncertainty", "vmax_uncertainty", "velocity_error", "vmax_error", "sigma_vmax"):
            val = self.calibration_info.get(key)
            if val not in (None, ""):
                try:
                    return tr("info.calib_uncertainty", field=key, value=f"{float(val):.4g}")
                except (TypeError, ValueError):
                    return tr("info.calib_uncertainty_raw", field=key, value=val)
        return tr("info.calib_no_uncertainty")

    def enabled_constraints(self) -> list[dict]:
        keys = {"vmax", "center", "baseline", "slope", "voigt_sigma", "sat_scale"}
        for cp in self.components_panels:
            keys.update(f"s{cp.idx}_{name}" for name in cp.params)
        return [
            c for c in self.constraints
            if c.get("enabled", True) and c.get("target") in keys and c.get("source") in keys
        ]

    def _info_rms(self) -> float:
        if self.file.velocity is None or self.file.y_data is None or not self._simulate_enabled:
            return float("nan")
        state = self._build_state()
        if state is None:
            return float("nan")
        try:
            model = model_from_values(state.velocity, state.values, state.components, state.constraints,
                                      absorber_model=state.absorber_model)
        except Exception:
            return float("nan")
        return float(np.sqrt(np.mean((self.file.y_data - model) ** 2)))

    def _update_info_panel(self) -> None:
        if not hasattr(self, "info_panel"):
            return
        if self.file.counts is None or self.file.folded is None:
            self.info_panel.set_lines([])
            return
        active = [cp.idx for cp in self._active_components()]
        fixed = self._fixed_param_keys()
        pct_active, areas, percentages = self.component_area_percentages()
        pct_errors = self.component_percentage_errors()
        center = float(self.calib.center.value())
        lines = [
            tr("info.file", name=self.file.path.name if self.file.path else "-"),
            tr("info.channels_read", n=self.file.counts.size),
            tr("info.folding_center", center=f"{center:.5f}"),
            tr("info.folding_normos", value=f"{2.0 * center:.5f}"),
            tr("info.folded_pairs", n=int(self.file.folded.size)),
            tr("info.normalization", factor=f"{self.file.norm_factor:.6g}"),
            tr("info.vmax", value=f"{self.calib.vmax.value():.6g}"),
            tr("info.baseline", value=f"{self.calib.baseline.value():.6g}"),
            tr("info.slope", value=f"{self.calib.slope.value():.6g}"),
            tr("info.active_sextets", list=", ".join(map(str, active))),
            tr("info.fit_velocity_yes") if self.calib.fit_velocity.isChecked() else tr("info.fit_velocity_no"),
            tr("info.rms", value=f"{self._info_rms():.6g}"),
        ]
        result = self.last_fit_result
        stats = result.stats if result is not None else {}
        if stats:
            lines.extend([
                tr("info.chi2_line", red_chi2=f"{stats.get('red_chi2', float('nan')):.6g}",
                   chi2=f"{stats.get('chi2', float('nan')):.6g}", dof=f"{stats.get('dof', float('nan')):.0f}"),
                tr("info.aic_bic_line", aic=f"{stats.get('aic', float('nan')):.6g}",
                   bic=f"{stats.get('bic', float('nan')):.6g}", n_params=f"{stats.get('n_params', len(result.free_keys)):.0f}"),
                tr("info.residual_diag", lag1=f"{stats.get('resid_lag1', float('nan')):.3f}",
                   z=f"{stats.get('resid_runs_z', float('nan')):.3f}",
                   antisym=f"{stats.get('resid_antisym_corr', float('nan')):.3f}"),
                tr("info.model_comparison"),
                tr("info.multistart_count", n=f"{result.n_starts:.0f}"),
            ])
            if (abs(stats.get("resid_lag1", 0.0)) > 0.35
                    or abs(stats.get("resid_runs_z", 0.0)) > 2.0
                    or stats.get("resid_antisym_corr", 0.0) > 0.45):
                lines.extend([tr("info.residual_warning_1"), tr("info.residual_warning_2")])
        cal_unc = self.calibration_uncertainty_text()
        if cal_unc:
            lines.append(cal_unc)
        corr = result.correlations if result is not None else {}
        if corr:
            max_pair = corr.get("max_pair") or []
            if max_pair:
                lines.append(tr("info.max_correlation", value=f"{float(corr.get('max_abs_corr', 0.0)):.3f}",
                               p1=max_pair[0], p2=max_pair[1]))
            high_pairs = corr.get("high_pairs") or []
            if high_pairs:
                lines.append(tr("info.correlation_warning"))
                for pair in high_pairs[:6]:
                    lines.append(f"  {pair['param1']} ↔ {pair['param2']}: r={float(pair['corr']):.3f}")
                if len(high_pairs) > 6:
                    lines.append(tr("info.correlation_more", n=len(high_pairs) - 6))
        lines.append("")
        if len(pct_active) > 1:
            lines.append(tr("info.area_percent_header"))
            for idx, area, pct in zip(pct_active, areas, percentages):
                err = pct_errors.get(idx)
                err_txt = f" ± {err:.3g}%" if err is not None else ""
                cp = self.components_panels[idx - 1]
                kind_disp = tr(f"kind.{cp.kind}", default=cp.kind)
                lines.append(tr("info.component_percent_line", idx=idx, kind=kind_disp,
                               pct=pct, err_txt=err_txt, area=area))
            lines.append("")
        iso_ref = self.calibration_iso_ref()
        for cp in self._active_components():
            i3_real = cp.params["int3"].value()
            i2_real = i3_real * cp.params["int2"].value()
            i1_real = i3_real * cp.params["int1"].value()
            g1 = cp.params["gamma1"].value()
            g2 = g1 * cp.params["gamma2"].value()
            g3 = g1 * cp.params["gamma3"].value()
            kind_disp = tr(f"kind.{cp.kind}", default=cp.kind)
            lines.extend([
                tr("info.component_params_line", kind=kind_disp, idx=cp.idx,
                   bhf=cp.params["bhf"].value(), delta=cp.params["delta"].value(), quad=cp.params["quad"].value()),
                tr("info.gamma_hwhm", g1=g1, g2=g2, g3=g3),
                tr("info.fwhm_equiv", f1=2.0 * g1, f2=2.0 * g2, f3=2.0 * g3),
                tr("info.gamma_rel", gamma2=cp.params["gamma2"].value(), gamma3=cp.params["gamma3"].value()),
                tr("info.depth_intensities", depth=cp.params["depth"].value(), i1=i1_real, i2=i2_real, i3=i3_real),
            ])
            if iso_ref is not None:
                lines.append(tr("info.delta_corrected",
                               value=f"{cp.params['delta'].value() - iso_ref:.6g}", ref=f"{iso_ref:.6g}"))
        lines.extend(["", tr("info.fixed_line", fixed=", ".join(fixed) if fixed else tr("info.none"))])
        cons = self.enabled_constraints()
        if cons:
            lines.append("")
            lines.append(tr("info.constraints_header"))
            for c in cons:
                lines.append(tr("info.constraint_line", target=c["target"], factor=float(c.get("factor", 1.0)),
                               source=c["source"], offset=float(c.get("offset", 0.0))))
        self.info_panel.set_lines(lines)

    # ── Construcción del FitState a partir de la UI ───────────────────────
    def _build_state(self) -> FitState | None:
        if self.file.velocity is None or self.file.y_data is None:
            return None
        values: dict[str, float] = {
            "vmax": self.calib.vmax.value(),
            "center": self.calib.center.value(),
            "baseline": self.calib.baseline.value(),
            "slope": self.calib.slope.value(),
            "voigt_sigma": self.calib.voigt_sigma.value(),
            "sat_scale": self.calib.sat_scale.value(),
        }
        fixed: dict[str, bool] = {k: False for k in values}
        fixed.update({k: True for k in ("vmax", "center")})
        fixed["baseline"] = self.calib.baseline.is_fixed()
        fixed["slope"] = self.calib.slope.is_fixed()
        fixed["sat_scale"] = self.calib.sat_scale.is_fixed()
        bounds = {
            "baseline": (0.70, 1.30), "slope": (-0.005, 0.005),
            "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0),
            "sat_scale": (0.05, 50.0),
        }
        param_bounds = (
            ("delta", (-2.0, 3.0)), ("quad", (-4.0, 4.0)),
            ("bhf", (0.0, 60.0)), ("gamma1", (0.03, 2.0)),
            ("gamma2", (0.2, 3.0)), ("gamma3", (0.2, 3.0)),
            ("depth", (0.0, 0.30)), ("int1", (0.0, 9.0)),
            ("int2", (0.0, 6.0)), ("int3", (0.0, 3.0)),
            ("texture", (0.0, 1.0)), ("beta", (0.0, 90.0)),
        )
        components = []
        for cp in self.components_panels:
            values.update(cp.values_dict())
            fixed.update(cp.fixed_dict())
            for name, rng in param_bounds:
                bounds[f"s{cp.idx}_{name}"] = rng
            components.append(Component(idx=cp.idx,
                                        enabled=cp.enabled.isChecked(),
                                        kind=cp.kind,
                                        intensity_mode=cp.intensity_mode,
                                        quad_treatment=cp.quad_treatment))
        return FitState(
            velocity=self.file.velocity, y_data=self.file.y_data,
            sigma_data=self.file.sigma, values=values, fixed=fixed,
            bounds=bounds, components=components,
            fit_velocity=self.calib.fit_velocity.isChecked(),
            fit_center=self.calib.fit_center.isChecked(),
            fit_sigma=self.calib.fit_sigma.isChecked(),
            voigt_sigma=self.calib.voigt_sigma.value(),
            line_profile=self.calib.line_profile,
            constraints=list(self.constraints),
            likelihood=self.likelihood,
            robust_loss=self.robust_loss,
            propagate_calib=self.propagate_calib,
            global_opt=self.global_opt,
            absorber_model=self.absorber_model,
        )

    # ── Acciones ─────────────────────────────────────────────────────────
    def on_open(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, tr("file.open"), str(ROOT),
            "WS5/ADT (*.ws5 *.adt *.WS5 *.ADT);;All (*.*)")
        if not path:
            return
        try:
            self._load_file(Path(path))
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("file.open"),
                                           f"{type(exc).__name__}: {exc}")

    def _load_file(self, path: Path) -> None:
        counts = read_ws5_counts(path)
        center = find_best_integer_or_half_center(counts)
        self.file = FileState(path=path, counts=counts, center=center)
        self._simulate_enabled = False
        folded, sigma, y = self._fold_counts_for_center(center)
        norm = float(np.percentile(folded, 90)) if folded.size else 1.0
        norm = norm or 1.0
        v = self._velocity_for_folded(folded.size)
        self.file.folded = folded
        self.file.sigma = sigma
        self.file.norm_factor = norm
        self.file.velocity = v
        self.file.y_data = y
        # actualiza UI
        self.calib.center.set_value(center)
        self.file_label.setText(f"<b>{path.name}</b><br>"
                                f"{counts.size} canales · centro={center:.3f} · "
                                f"norm={norm:.4g}")
        self.act_fit.setEnabled(True)
        self.act_init.setEnabled(True)
        self.act_auto_fit.setEnabled(True)
        self.act_ai.setEnabled(True)
        self.act_upload_session.setEnabled(True)
        self.act_use_as_calib.setEnabled(True)
        self.act_profile.setEnabled(True)
        self.act_find_center.setEnabled(True)
        self.act_save_fit.setEnabled(True)
        self.act_export_report.setEnabled(True)
        self.act_bootstrap.setEnabled(True)
        self.act_lcurve.setEnabled(True)
        self._set_quick_action_buttons_enabled(True)
        self._add_recent(path)
        self.statusBar().showMessage(
            f"{path.name} · {counts.size} canales · centro={center:.3f}")
        self.last_fit_result = None
        self._refresh_plot()

    def _refresh_plot(self) -> None:
        if self._building or self.file.velocity is None:
            return
        v = self.file.velocity
        y = self.file.y_data
        # Recalcular velocidad si vmax cambia, respetando el recorte de bordes.
        expected_v = self._velocity_for_folded(y.size)
        if v.size and expected_v.size == v.size and not np.allclose(v, expected_v, atol=1e-9, rtol=0.0):
            v = expected_v
            self.file.velocity = v
        state = self._build_state()
        style = get_style(self.plot_style_name)
        show_res = self.act_show_residual.isChecked() if hasattr(self, "act_show_residual") else True
        show_leg = self.act_show_legend.isChecked() if hasattr(self, "act_show_legend") else True
        if state is None or not self._simulate_enabled:
            self.canvas.render(v, y, style=style,
                               show_residual=show_res, show_legend=show_leg)
            self._update_info_panel()
            return
        try:
            model = model_from_values(v, state.values, state.components, state.constraints,
                                      absorber_model=state.absorber_model)
        except Exception:
            self.canvas.render(v, y, style=style,
                               show_residual=show_res, show_legend=show_leg)
            self._update_info_panel()
            return
        # Solo dibujar componentes individuales si hay más de uno activo.
        comps = []
        enabled = [c for c in state.components if c.enabled]
        if len(enabled) >= 2:
            for comp in enabled:
                only_this = model_from_values(v, state.values, [comp], state.constraints,
                                              absorber_model=state.absorber_model)
                comps.append((comp.idx, comp.kind, only_this))
        self.canvas.render(v, y, model=model, components=comps, style=style,
                           show_residual=show_res, show_legend=show_leg)
        self._update_info_panel()

    def _open_progress_dialog(self, title: str, message: str | None = None):
        """Ventana modal de progreso (barra indeterminada), igual que la de Tk.

        Devuelve ``(dialog, update, close)``: ``update(msg)`` cambia el texto y
        ``close()`` la cierra. Mientras está abierta informa de que el cálculo
        sigue activo.
        """
        if message is None:
            message = tr("progress.generic_working", default="Trabajando…")
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setModal(True)
        dlg.setWindowFlags(
            (dlg.windowFlags() | QtCore.Qt.CustomizeWindowHint)
            & ~QtCore.Qt.WindowCloseButtonHint
            & ~QtCore.Qt.WindowContextHelpButtonHint)
        v = QtWidgets.QVBoxLayout(dlg)
        v.setContentsMargins(16, 16, 16, 16)
        label = QtWidgets.QLabel(message)
        label.setWordWrap(True)
        label.setMinimumWidth(420)
        v.addWidget(label)
        bar = QtWidgets.QProgressBar()
        bar.setRange(0, 0)  # indeterminado: barra animada
        bar.setTextVisible(False)
        v.addWidget(bar)
        dlg.show()
        QtWidgets.QApplication.processEvents()

        def update(msg: str) -> None:
            if dlg.isVisible():
                label.setText(msg)
                QtWidgets.QApplication.processEvents()

        def close() -> None:
            dlg.close()
            dlg.deleteLater()

        return dlg, update, close

    def on_fit(self) -> None:
        if self.is_distribution_mode:
            self._simulate_enabled = True
            self.on_fit_distribution()
            return
        self._simulate_enabled = True
        state = self._build_state()
        if state is None:
            return
        # Bloquea acción mientras corre y muestra una ventana de progreso.
        self.act_fit.setEnabled(False)
        _dlg, update_progress, close_progress = self._open_progress_dialog(
            tr("progress.fitting_title", default="Ajustando"),
            tr("progress.fit_prepare", default="Preparando ajuste…"))
        try:
            result = fit_discrete(state, progress_cb=update_progress)
        except Exception as exc:
            close_progress()
            QtWidgets.QMessageBox.critical(self, tr("fit.run"),
                                           f"{type(exc).__name__}: {exc}")
            self.act_fit.setEnabled(True)
            return
        # Aplica resultados
        self._building = True
        self.calib.baseline.set_value(result.values.get("baseline", self.calib.baseline.value()))
        self.calib.slope.set_value(result.values.get("slope", self.calib.slope.value()))
        if state.fit_velocity:
            self.calib.vmax.set_value(result.values.get("vmax", self.calib.vmax.value()))
        if state.fit_sigma:
            self.calib.voigt_sigma.set_value(result.values.get("voigt_sigma", self.calib.voigt_sigma.value()))
        for cp in self.components_panels:
            cp.apply_values(result.values)
        self._building = False
        close_progress()
        red = result.stats.get("red_chi2", float("nan"))
        chi2 = result.stats.get("chi2", float("nan"))
        self.statusBar().showMessage(
            f"χ²={chi2:.4g}  χ²red={red:.4g}  ·  {result.n_starts} arranques")
        self.last_fit_result = result
        self.act_fit.setEnabled(True)
        self._refresh_plot()

    # ── Save / Load session (formato compatible con la GUI Tk) ──────────
    def _session_payload(self) -> dict:
        """Estado completo del Qt en el mismo formato que la GUI Tk."""
        values: dict[str, float] = {
            "vmax": self.calib.vmax.value(),
            "center": self.calib.center.value(),
            "baseline": self.calib.baseline.value(),
            "slope": self.calib.slope.value(),
            "voigt_sigma": self.calib.voigt_sigma.value(),
            "sat_scale": self.calib.sat_scale.value(),
        }
        fixed: dict[str, bool] = {}
        sextet_enabled: dict[str, bool] = {}
        component_kind: dict[str, str] = {}
        intensity_mode: dict[str, str] = {}
        quad_treatment: dict[str, str] = {}
        for cp in self.components_panels:
            values.update(cp.values_dict())
            fixed.update(cp.fixed_dict())
            sextet_enabled[str(cp.idx)] = bool(cp.enabled.isChecked())
            component_kind[str(cp.idx)] = cp.kind
            intensity_mode[str(cp.idx)] = cp.intensity_mode
            quad_treatment[str(cp.idx)] = cp.quad_treatment
        model_state = {
            "vars": values,
            "fixed": fixed,
            "sextet_enabled": sextet_enabled,
            "component_kind": component_kind,
            "intensity_mode": intensity_mode,
            "quad_treatment": quad_treatment,
            "n_components": (
                self.n_components_spin.value() if hasattr(self, "n_components_spin") else 1
            ),
            "likelihood": self.likelihood,
            "robust_loss": self.robust_loss,
            "propagate_calib": self.propagate_calib,
            "global_opt": self.global_opt,
            "absorber_model": self.absorber_model,
            "dist_use_sharp": self.dist_use_sharp,
            "dist_refine_global": self.dist_refine_global,
            "dist_shape": self.dist_panel.shape if hasattr(self, "dist_panel") else "Histograma",
            "dist_reg_mode": self.dist_panel.reg_mode if hasattr(self, "dist_panel") else "tikhonov",
            "fixed_distribution_path": str(self.dist_panel.fixed_path) if hasattr(self, "dist_panel") and self.dist_panel.fixed_path else None,
            "dist_variable": "ΔEQ" if self.dist_variable == "quad" else "BHF",
            "fit_velocity": self.calib.fit_velocity.isChecked(),
            "fit_center": self.calib.fit_center.isChecked(),
            "fit_sigma": self.calib.fit_sigma.isChecked(),
            "show_residual": self.act_show_residual.isChecked() if hasattr(self, "act_show_residual") else True,
            "show_legend": self.act_show_legend.isChecked() if hasattr(self, "act_show_legend") else True,
            "line_profile": self.calib.line_profile,
            "constraints": list(self.constraints),
        }
        return {
            "version": 1,
            "program": "mossbauer_qt.py",
            "file_path": str(self.file.path) if self.file.path else None,
            "file_name": self.file.path.name if self.file.path else None,
            "counts": self.file.counts.tolist() if self.file.counts is not None else None,
            "calibration": self.calibration_info,
            "model_state": model_state,
        }

    def _apply_session_payload(self, data: dict) -> None:
        # 1. Datos: si trae un file_path existente o counts embebidos, los carga.
        file_path = data.get("file_path")
        if file_path and Path(file_path).exists():
            try:
                self._load_file(Path(file_path))
            except Exception:
                pass
        elif data.get("counts") is not None:
            self.file = FileState(
                path=Path(file_path) if file_path else None,
                counts=np.array(data["counts"], dtype=float),
            )
            counts = self.file.counts
            center = find_best_integer_or_half_center(counts)
            self.file.center = center
            folded, sigma, y = self._fold_counts_for_center(center)
            norm = float(np.percentile(folded, 90)) if folded.size else 1.0
            norm = norm or 1.0
            self.file.folded = folded
            self.file.norm_factor = norm
            self.file.sigma = sigma
            self.file.y_data = y
            self.file.velocity = self._velocity_for_folded(folded.size)
            self.file_label.setText(
                f"<b>{data.get('file_name') or '—'}</b><br>"
                f"{counts.size} canales (sesión)")
            self.act_fit.setEnabled(True)
            self._set_quick_action_buttons_enabled(True)

        # 2. Calibración guardada
        calib = data.get("calibration")
        if isinstance(calib, dict):
            self.calibration_info = calib
            self._refresh_calib_label()

        # 3. Modelo: aplicar vars / fixed / sextet_enabled / component_kind.
        state = data.get("model_state", {})
        self._building = True
        try:
            vmap = state.get("vars", {})
            self.calib.vmax.set_value(vmap.get("vmax", self.calib.vmax.value()))
            self.calib.center.set_value(vmap.get("center", self.calib.center.value()))
            self.calib.baseline.set_value(vmap.get("baseline", self.calib.baseline.value()))
            self.calib.slope.set_value(vmap.get("slope", self.calib.slope.value()))
            self.calib.voigt_sigma.set_value(vmap.get("voigt_sigma", self.calib.voigt_sigma.value()))
            self.calib.sat_scale.set_value(vmap.get("sat_scale", self.calib.sat_scale.value()))
            n_saved = state.get("n_components")
            if n_saved is None:
                enabled_map = state.get("sextet_enabled", {})
                enabled_idx = [int(k) for k, v in enabled_map.items()
                               if str(k).isdigit() and bool(v)]
                n_saved = max(enabled_idx, default=1)
            self._sync_component_count(int(n_saved))
            for cp in self.components_panels:
                cp.apply_values(vmap)
                ki = state.get("component_kind", {}).get(str(cp.idx))
                if ki in ("Sextete", "Doblete", "Singlete"):
                    cp.type_combo.setCurrentText(ki)
                en = state.get("sextet_enabled", {}).get(str(cp.idx))
                if en is not None:
                    cp.enabled.setChecked(bool(en))
                im = state.get("intensity_mode", {}).get(str(cp.idx))
                if im in ("free", "texture"):
                    cp.intensity_mode = im
                qt_v = state.get("quad_treatment", {}).get(str(cp.idx))
                if qt_v in ("1st_order", "kundig_fixed", "kundig_powder"):
                    cp.quad_treatment = qt_v
                for name, ctl in cp.params.items():
                    f = state.get("fixed", {}).get(f"s{cp.idx}_{name}")
                    if f is not None:
                        ctl.set_fixed(bool(f))
            self.calib.fit_velocity.setChecked(bool(state.get("fit_velocity", False)))
            self.calib.fit_center.setChecked(bool(state.get("fit_center", False)))
            self.calib.fit_sigma.setChecked(bool(state.get("fit_sigma", False)))
            lp = state.get("line_profile")
            if lp in ("Lorentziana", "Voigt"):
                self.calib._set_line_profile(lp)
            if "show_residual" in state and hasattr(self, "act_show_residual"):
                self.act_show_residual.setChecked(bool(state["show_residual"]))
            if "show_legend" in state and hasattr(self, "act_show_legend"):
                self.act_show_legend.setChecked(bool(state["show_legend"]))
            # Opciones avanzadas
            lk = state.get("likelihood")
            if lk in ("gauss", "poisson"):
                self.likelihood = lk
            rl = state.get("robust_loss")
            if rl in ("linear", "soft_l1", "huber"):
                self.robust_loss = rl
            if "propagate_calib" in state:
                self.propagate_calib = bool(state["propagate_calib"])
            if "global_opt" in state:
                self.global_opt = bool(state["global_opt"])
            am = state.get("absorber_model")
            if am in ("thin", "thickness"):
                self.absorber_model = am
                self.calib.set_absorber_model(am)
            if "dist_use_sharp" in state:
                self.dist_use_sharp = bool(state["dist_use_sharp"])
            if "dist_refine_global" in state:
                self.dist_refine_global = bool(state["dist_refine_global"])
            if "constraints" in state:
                self.constraints = list(state.get("constraints") or [])
            shape_saved = state.get("dist_shape")
            reg_saved = state.get("dist_reg_mode")
            if reg_saved in ("tikhonov", "tv") and hasattr(self, "dist_panel"):
                self.dist_panel.reg_mode_combo.setCurrentText(reg_saved)
            fixed_path = state.get("fixed_distribution_path")
            if fixed_path and hasattr(self, "dist_panel"):
                self.dist_panel.fixed_path = Path(fixed_path)
            if shape_saved in ("Histograma", "Gaussiana", "Binomial", "Fija") and hasattr(self, "dist_panel"):
                idx_shape = self.dist_panel.shape_combo.findData(shape_saved)
                if idx_shape >= 0:
                    self.dist_panel.shape_combo.setCurrentIndex(idx_shape)
            var_saved = state.get("dist_variable")
            if var_saved in ("BHF", "bhf"):
                self.mode_combo.setCurrentIndex(1)
            elif var_saved in ("ΔEQ", "quad"):
                self.mode_combo.setCurrentIndex(2)
            # Sincroniza las acciones del menú avanzado si ya existen
            for grp_attr, val, items in (
                ("likelihood_action_group", self.likelihood, ("gauss", "poisson")),
                ("loss_action_group", self.robust_loss, ("linear", "soft_l1", "huber")),
                ("absorber_action_group", self.absorber_model, ("thin", "thickness")),
            ):
                grp = getattr(self, grp_attr, None)
                if grp is None:
                    continue
                actions = grp.actions()
                for idx_, key_ in enumerate(items):
                    if key_ == val and idx_ < len(actions):
                        actions[idx_].setChecked(True)
            for attr, value in (
                ("act_propagate", self.propagate_calib),
                ("act_global_opt", self.global_opt),
                ("act_add_sharp", self.dist_use_sharp),
                ("act_refine_global", self.dist_refine_global),
            ):
                a = getattr(self, attr, None)
                if a is not None:
                    a.setChecked(bool(value))
            if hasattr(self, "dist_panel"):
                self.dist_panel.use_sharp.setChecked(bool(self.dist_use_sharp))
                self.dist_panel.refine_global.setChecked(bool(self.dist_refine_global))
        finally:
            self._building = False
        self._simulate_enabled = True
        self._refresh_plot()

    def on_save_session(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("file.save_session"), str(ROOT),
            "JSON (*.json);;All (*.*)")
        if not path:
            return
        import json
        try:
            data = self._session_payload()
            Path(path).write_text(
                json.dumps(data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8")
            self.statusBar().showMessage(f"Sesión guardada: {path}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("file.save_session"),
                f"{type(exc).__name__}: {exc}")

    def on_load_session(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, tr("file.load_session"), str(ROOT),
            "JSON (*.json);;All (*.*)")
        if not path:
            return
        import json
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("file.load_session"),
                f"{type(exc).__name__}: {exc}")
            return
        try:
            self._apply_session_payload(data)
            self.statusBar().showMessage(f"Sesión cargada: {path}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("file.load_session"),
                f"{type(exc).__name__}: {exc}")

    # ── Acceso a la API del laboratorio ──────────────────────────────────
    def _get_api_client(self):
        """Devuelve un MatelecLabClient autenticado o None si el usuario cancela."""
        try:
            from mossbauer_api_client import MatelecLabClient, DEFAULT_BASE_URL
        except ImportError as exc:
            QtWidgets.QMessageBox.critical(
                self, "Web", f"Cliente API no disponible: {exc}")
            return None
        creds = load_credentials() or {}
        base = creds.get("api_base") or DEFAULT_BASE_URL
        token = creds.get("token") or ""
        client = MatelecLabClient(base_url=base, token=token)
        if token:
            try:
                if client.token_is_valid():
                    return client
            except Exception:
                pass
        # Token inválido o ausente: pedir credenciales.
        if not self._login_dialog(client, creds):
            return None
        return client

    def _login_dialog(self, client, creds: dict) -> bool:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Login (API laboratorio)")
        form = QtWidgets.QFormLayout(dlg)
        e_user = QtWidgets.QLineEdit(creds.get("username", ""))
        e_pass = QtWidgets.QLineEdit(creds.get("password", ""))
        e_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        cb_remember = QtWidgets.QCheckBox("Recordar usuario y token")
        cb_remember.setChecked(bool(creds.get("username") or creds.get("token")))
        form.addRow("Usuario:", e_user)
        form.addRow("Contraseña:", e_pass)
        form.addRow(cb_remember)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return False
        user = e_user.text().strip(); pwd = e_pass.text()
        if not user or not pwd:
            return False
        try:
            client.login(user, pwd)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Login", f"Login fallido: {exc}")
            return False
        if cb_remember.isChecked():
            creds = dict(creds); creds["username"] = user
            creds["token"] = client.token
            save_credentials(creds)
        return True

    def _open_web_dialog(self, kind: str) -> None:
        """Diálogo Web estilo Tk: server / usuario / contraseña / recordar /
        carpeta destino / buscar / log de depuración. ``kind`` ∈
        {'measurements', 'calibrations'}.
        """
        try:
            from mossbauer_api_client import MatelecLabClient, DEFAULT_BASE_URL
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("msg.web_title") if hasattr(tr, "_d") else "Web",
                f"Cliente API no disponible: {exc}")
            return
        kind_key = "calibraciones" if kind == "calibrations" else "medidas"
        is_calib = (kind == "calibrations")
        creds = load_credentials() or {}
        saved_dirs = creds.get("download_dirs", {}) if isinstance(creds.get("download_dirs"), dict) else {}
        default_dir_name = "calibraciones" if is_calib else "medidas"
        effective_dir = saved_dirs.get(kind_key,
                                        str(Path.home() / "Mossbauer" / default_dir_name))
        base_url = creds.get("api_base") or DEFAULT_BASE_URL

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr(f"dialog.web_download_{'calib' if is_calib else 'meas'}")
                           if hasattr(tr, "_d") else
                           f"{'Calibraciones' if is_calib else 'Medidas'} (web)")
        dlg.resize(820, 600)

        v = QtWidgets.QVBoxLayout(dlg)
        form = QtWidgets.QFormLayout()
        e_server = QtWidgets.QLineEdit(base_url)
        form.addRow(tr("label.server") if hasattr(tr, "_d") else "Servidor:", e_server)
        e_user = QtWidgets.QLineEdit(creds.get("username", ""))
        form.addRow(tr("label.username") if hasattr(tr, "_d") else "Usuario:", e_user)
        pw_row = QtWidgets.QHBoxLayout()
        e_pass = QtWidgets.QLineEdit(creds.get("password", ""))
        e_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        pw_row.addWidget(e_pass, stretch=1)
        cb_remember = QtWidgets.QCheckBox(
            tr("checkbox.remember_credentials") if hasattr(tr, "_d") else
            "Recordar usuario y token")
        cb_remember.setChecked(bool(creds.get("username") or creds.get("token")))
        pw_row.addWidget(cb_remember)
        pw_wrap = QtWidgets.QWidget(); pw_wrap.setLayout(pw_row)
        form.addRow(tr("label.password") if hasattr(tr, "_d") else "Contraseña:", pw_wrap)
        # Carpeta destino + botones
        dest_row = QtWidgets.QHBoxLayout()
        e_dest = QtWidgets.QLineEdit(effective_dir)
        dest_row.addWidget(e_dest, stretch=1)
        btn_choose = QtWidgets.QPushButton(
            tr("button.choose") if hasattr(tr, "_d") else "Elegir...")
        dest_row.addWidget(btn_choose)
        dest_wrap = QtWidgets.QWidget(); dest_wrap.setLayout(dest_row)
        form.addRow(tr("label.dest_folder") if hasattr(tr, "_d") else "Carpeta destino:", dest_wrap)
        cb_with_calib = QtWidgets.QCheckBox(
            tr("checkbox.download_calibration_too") if hasattr(tr, "_d") else
            "Descargar también la calibración asociada")
        if not is_calib:
            cb_with_calib.setChecked(True)
            form.addRow("", cb_with_calib)
        v.addLayout(form)

        # Buscador + tabla
        search_row = QtWidgets.QHBoxLayout()
        search_row.addWidget(QtWidgets.QLabel(
            tr("label.search") if hasattr(tr, "_d") else "Buscar:"))
        e_search = QtWidgets.QLineEdit()
        search_row.addWidget(e_search, stretch=1)
        btn_search = QtWidgets.QPushButton("Buscar/Refrescar")
        search_row.addWidget(btn_search)
        v.addLayout(search_row)
        table = QtWidgets.QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["id", "fichero", "muestra"])
        table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        v.addWidget(table, stretch=1)

        # Log de depuración
        log = QtWidgets.QPlainTextEdit()
        log.setReadOnly(True)
        log.setMaximumHeight(140)
        log.setStyleSheet(
            "QPlainTextEdit { background:#111827; color:#d1fae5; "
            "font-family:monospace; font-size:9pt; }")
        v.addWidget(log)

        def debug(msg: str) -> None:
            log.appendPlainText(msg)
            QtWidgets.QApplication.processEvents()

        def choose_dest():
            current = e_dest.text().strip() or str(Path.home())
            folder = QtWidgets.QFileDialog.getExistingDirectory(
                dlg, tr("dialog.select_folder") if hasattr(tr, "_d") else "Elegir carpeta",
                current)
            if folder:
                e_dest.setText(folder)
        btn_choose.clicked.connect(choose_dest)

        items: list[dict] = []

        def build_client():
            base = e_server.text().strip() or DEFAULT_BASE_URL
            token = creds.get("token")
            client = MatelecLabClient(base_url=base, token=token)
            if token:
                try:
                    if client.token_is_valid():
                        debug("Token guardado válido; reusándolo.")
                        return client
                except Exception:
                    pass
            user = e_user.text().strip(); pwd = e_pass.text()
            if not user or not pwd:
                raise RuntimeError("Falta usuario o contraseña para hacer login.")
            debug(f"Login como '{user}'...")
            client.login(user, pwd)
            creds["token"] = client.token
            debug("Token nuevo recibido.")
            return client

        def persist():
            if not cb_remember.isChecked():
                return
            creds["username"] = e_user.text().strip()
            creds["password"] = e_pass.text()
            creds["api_base"] = e_server.text().strip() or DEFAULT_BASE_URL
            if e_dest.text().strip():
                dirs = creds.setdefault("download_dirs", {})
                if not isinstance(dirs, dict):
                    dirs = {}
                    creds["download_dirs"] = dirs
                dirs[kind_key] = e_dest.text().strip()
            save_credentials(creds)

        def refresh():
            nonlocal items
            try:
                client = build_client()
            except Exception as exc:
                debug(f"ERROR login: {exc}")
                QtWidgets.QMessageBox.critical(dlg, "Login", str(exc))
                return
            persist()
            try:
                if is_calib:
                    items = list(client.iter_calibraciones(
                        search=e_search.text().strip() or None, limit=200))
                else:
                    items = list(client.iter_medidas(
                        search=e_search.text().strip() or None, limit=200))
            except Exception as exc:
                debug(f"ERROR consulta: {exc}")
                return
            table.setRowCount(0)
            for it in items:
                r = table.rowCount(); table.insertRow(r)
                table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(it.get("id", ""))))
                table.setItem(r, 1, QtWidgets.QTableWidgetItem(
                    str(it.get("file_name") or it.get("filename") or "")))
                table.setItem(r, 2, QtWidgets.QTableWidgetItem(
                    str(it.get("muestra") or it.get("sample") or "")))
            debug(f"{len(items)} resultados.")

        btn_search.clicked.connect(refresh)
        e_search.returnPressed.connect(refresh)

        # Filtro local opcional sobre items ya descargados
        def local_filter(_=None):
            q = e_search.text().strip().lower()
            if not q:
                return
            for r in range(table.rowCount()):
                hay = " ".join(table.item(r, c).text().lower() for c in range(3))
                table.setRowHidden(r, q not in hay)
        e_search.textChanged.connect(local_filter)

        # Botones inferiores
        btn_row = QtWidgets.QHBoxLayout()
        btn_list = QtWidgets.QPushButton(tr("button.list") if hasattr(tr, "_d") else "Listar")
        btn_download_only = QtWidgets.QPushButton("Descargar")
        btn_dl = QtWidgets.QPushButton("Descargar y cargar")
        btn_close = QtWidgets.QPushButton(
            tr("button.close") if hasattr(tr, "_d") else "Cerrar")
        btn_row.addStretch(1)
        btn_row.addWidget(btn_list); btn_row.addWidget(btn_download_only)
        btn_row.addWidget(btn_dl); btn_row.addWidget(btn_close)
        v.addLayout(btn_row)

        def download(load_after: bool = True):
            rows = sorted({i.row() for i in table.selectedIndexes()})
            if not rows:
                debug("Selecciona una fila primero.")
                return
            item_id = table.item(rows[0], 0).text()
            dest = Path(e_dest.text().strip() or (Path.home() / "Mossbauer"))
            try:
                dest.mkdir(parents=True, exist_ok=True)
                client = build_client()
                persist()
                if is_calib:
                    p = client.download_calibracion_datafile(item_id, dest_dir=str(dest))
                else:
                    p = client.download_datafile(item_id, dest_dir=str(dest))
                    if cb_with_calib.isChecked():
                        try:
                            calib = client.get_calibracion_de_medida(item_id)
                            if calib and "id" in calib:
                                pc = client.download_calibracion_datafile(
                                    calib["id"], dest_dir=str(dest))
                                debug(f"Calibración asociada → {pc}")
                        except Exception as exc:
                            debug(f"(sin calibración asociada: {exc})")
            except Exception as exc:
                QtWidgets.QMessageBox.critical(dlg, "Descarga", str(exc))
                return
            debug(f"Descargado: {p}")
            if not load_after:
                table.clearSelection()
                return
            try:
                self._load_file(Path(p))
                dlg.accept()
            except Exception as exc:
                QtWidgets.QMessageBox.warning(dlg, "Cargar", str(exc))

        btn_list.clicked.connect(refresh)
        btn_download_only.clicked.connect(lambda: download(False))
        btn_dl.clicked.connect(lambda: download(True))
        btn_close.clicked.connect(dlg.reject)
        dlg.exec()

    # ── Subir sesión al API ──────────────────────────────────────────────
    def on_upload_session(self) -> None:
        if self.file.path is None:
            return
        client = self._get_api_client()
        if client is None:
            return
        # Sugiere el medida_id si ya conocemos el fichero en remoto
        suggested = ""
        try:
            m = client.find_medida_by_filename(self.file.path.name)
            if m and "id" in m:
                suggested = str(m["id"])
        except Exception:
            pass
        medida_id, ok = QtWidgets.QInputDialog.getText(
            self, tr("file.upload_session"), "medida_id:", text=suggested)
        if not ok or not medida_id.strip():
            return
        note, _ = QtWidgets.QInputDialog.getText(
            self, tr("file.upload_session"), "Nota (opcional):", text="")
        try:
            import json
            payload = self._session_payload()
            data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            r = client.upload_analysis(medida_id.strip(), data=data,
                                        filename="qt_session.json", note=note or "")
            self.statusBar().showMessage(
                f"Subido como analysis #{r.get('id', '?')}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("file.upload_session"), str(exc))

    def on_configure_updates(self) -> None:
        """Diálogo mínimo: toggles de check-al-arrancar y descarga de checksum."""
        import json
        cfg = {}
        if SETTINGS_PATH.exists():
            try:
                cfg = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("help.configure_updates"))
        v = QtWidgets.QVBoxLayout(dlg)
        cb_startup = QtWidgets.QCheckBox(
            "Buscar actualizaciones al arrancar (silencioso)")
        cb_startup.setChecked(bool(cfg.get("check_updates_on_startup", False)))
        v.addWidget(cb_startup)
        cb_checksum = QtWidgets.QCheckBox(
            "Verificar checksum SHA-256 al descargar")
        cb_checksum.setChecked(bool(cfg.get("verify_update_checksum", True)))
        v.addWidget(cb_checksum)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        cfg["check_updates_on_startup"] = bool(cb_startup.isChecked())
        cfg["verify_update_checksum"] = bool(cb_checksum.isChecked())
        try:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, tr("help.configure_updates"), str(exc))

    # ── Check for updates ───────────────────────────────────────────────
    def on_check_updates(self) -> None:
        try:
            from mossbauer_updater import latest_release, is_newer
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, tr("help.check_updates"),
                f"Updater no disponible: {exc}")
            return
        self.statusBar().showMessage("Buscando actualizaciones…")
        QtWidgets.QApplication.processEvents()
        try:
            rel = latest_release()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, tr("help.check_updates"),
                f"No se pudo consultar el repositorio: {exc}")
            return
        tag = (rel or {}).get("tag_name", "")
        if rel and is_newer(tag, APP_VERSION):
            QtWidgets.QMessageBox.information(
                self, tr("help.check_updates"),
                f"Nueva versión disponible: {tag}\n"
                f"(versión actual {APP_VERSION})\n\n"
                "Descárgala desde la página de releases en GitHub.")
        else:
            QtWidgets.QMessageBox.information(
                self, tr("help.check_updates"),
                f"Estás en la última versión ({APP_VERSION}).")

    # ── Calibración rápida desde el cuadro de fichero ─────────────────────
    def _show_file_box_menu(self, pos: QtCore.QPoint) -> None:
        if self.file.path is None:
            return
        menu = QtWidgets.QMenu(self)
        act_quick = menu.addAction(tr("context.use_as_calibration_quick"))
        act_detail = menu.addAction(tr("context.use_as_calibration_detailed"))
        chosen = menu.exec(self.file_box.mapToGlobal(pos))
        if chosen == act_quick:
            self._use_as_calibration_quick()
        elif chosen == act_detail:
            self._use_as_calibration_detailed()

    def _use_as_calibration_quick(self) -> None:
        if self.file.path is None:
            return
        vmax = float(self.calib.vmax.value())
        iso = float(self.components_panels[0].params["delta"].value())
        name = self.file.path.stem
        self.calibration_info = {
            "source": "local", "calibration_sample": name,
            "velocity_calibrated": vmax, "isomer_shift": iso,
            "calibration_file_name": self.file.path.name,
            "calibration_file_path": str(self.file.path),
        }
        self._refresh_calib_label()
        QtWidgets.QMessageBox.information(
            self, tr("file.use_as_calibration"),
            tr("msg.use_as_calib_quick_ok",
               name=name, vmax=f"{vmax:.4f}", iso=f"{iso:.4f}"))

    def _use_as_calibration_detailed(self) -> None:
        if self.file.path is None:
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("file.use_as_calibration"))
        form = QtWidgets.QFormLayout(dlg)
        e_name = QtWidgets.QLineEdit(self.file.path.stem)
        e_vmax = QtWidgets.QDoubleSpinBox(); e_vmax.setRange(-30.0, 30.0)
        e_vmax.setDecimals(4); e_vmax.setValue(float(self.calib.vmax.value()))
        e_iso = QtWidgets.QDoubleSpinBox(); e_iso.setRange(-5.0, 5.0)
        e_iso.setDecimals(4)
        e_iso.setValue(float(self.components_panels[0].params["delta"].value()))
        form.addRow("Sample:", e_name)
        form.addRow("Vmax (mm/s):", e_vmax)
        form.addRow("IS (mm/s):", e_iso)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        self.calibration_info = {
            "source": "local",
            "calibration_sample": e_name.text() or self.file.path.stem,
            "velocity_calibrated": float(e_vmax.value()),
            "isomer_shift": float(e_iso.value()),
            "calibration_file_name": self.file.path.name,
            "calibration_file_path": str(self.file.path),
        }
        self._refresh_calib_label()

    def _refresh_calib_label(self) -> None:
        if not self.calibration_info:
            self.calib_label.setText("")
            return
        info = self.calibration_info
        src = info.get("source", "local")
        sample = info.get("calibration_sample", "")
        vmax = info.get("velocity_calibrated")
        iso = info.get("isomer_shift")
        txt = f"Calibración [{src}] {sample}<br>"
        if vmax is not None:
            txt += f"Vmax = {vmax:.4f} mm/s · IS = {iso:.4f} mm/s"
        self.calib_label.setText(txt)

    # ── Bootstrap MC ─────────────────────────────────────────────────────
    def on_bootstrap(self) -> None:
        """Estima errores por remuestreo Monte Carlo (solo modo discreto)."""
        if self.is_distribution_mode:
            QtWidgets.QMessageBox.information(
                self, tr("msg.bootstrap_title"), tr("msg.bootstrap_discrete_only"))
            return
        state = self._build_state()
        if state is None:
            return
        nrep, ok = QtWidgets.QInputDialog.getInt(
            self, tr("msg.bootstrap_title"),
            tr("dialog.bootstrap_prompt") if hasattr(tr, "_dummy") else "Número de réplicas:",
            30, 5, 300, 5)
        if not ok:
            return
        # Ajuste base
        self.statusBar().showMessage("Ajuste base…")
        QtWidgets.QApplication.processEvents()
        try:
            base = fit_discrete(state)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("msg.bootstrap_title"),
                                            f"{type(exc).__name__}: {exc}")
            return
        if not base.free_keys:
            QtWidgets.QMessageBox.information(
                self, tr("msg.bootstrap_title"), tr("msg.bootstrap_no_free"))
            return
        # Modelo base como predicción de los datos sintéticos
        v = state.velocity
        try:
            model0 = model_from_values(v, base.values, state.components, state.constraints)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("msg.bootstrap_title"),
                                            f"{type(exc).__name__}: {exc}")
            return
        sigma = state.sigma_data if state.sigma_data is not None else np.ones_like(model0) * 0.005
        rng = np.random.default_rng(24680)
        samples: dict[str, list[float]] = {k: [] for k in base.free_keys}
        for i in range(nrep):
            self.statusBar().showMessage(f"Bootstrap {i+1}/{nrep}…")
            QtWidgets.QApplication.processEvents()
            y_sim = model0 + rng.normal(0.0, sigma)
            sub = FitState(
                velocity=v, y_data=y_sim, sigma_data=sigma,
                values=dict(base.values), fixed=dict(state.fixed),
                bounds=dict(state.bounds), components=state.components,
                constraints=state.constraints,
                likelihood=state.likelihood, robust_loss=state.robust_loss,
                line_profile=state.line_profile, voigt_sigma=state.voigt_sigma,
                multistart_n=1,
            )
            try:
                r = fit_discrete(sub)
                for k in base.free_keys:
                    samples[k].append(float(r.values.get(k, float("nan"))))
            except Exception:
                continue
        # Resumen
        std = {k: float(np.std(v_list)) if len(v_list) > 1 else 0.0
               for k, v_list in samples.items()}
        msg_lines = [tr("msg.bootstrap_done", ok=len(samples[base.free_keys[0]]),
                        total=nrep)]
        msg_lines.append("")
        for k in base.free_keys:
            msg_lines.append(f"  {k:14s}  σ(MC) = {std[k]:.4g}")
        QtWidgets.QMessageBox.information(
            self, tr("msg.bootstrap_title"), "\n".join(msg_lines))

    def _active_sharp_components_for_distribution(self) -> tuple[list[dict[str, float]] | None, list[int]]:
        if not self.dist_use_sharp:
            return None, []
        components: list[dict[str, float]] = []
        indices: list[int] = []
        for cp in self.components_panels:
            if not cp.enabled.isChecked():
                continue
            vals = cp.values_dict()
            p = f"s{cp.idx}_"
            kind = cp.kind
            int1_gui = float(vals.get(p + "int1", 1.0))
            int2_gui = float(vals.get(p + "int2", 1.0))
            int3_gui = float(vals.get(p + "int3", 1.0))
            if kind == "Sextete":
                engine_int1 = int3_gui * int1_gui
                if abs(int1_gui) > 1e-12:
                    engine_int2_rel = 1.5 * int2_gui / int1_gui
                    engine_int3_rel = 3.0 / int1_gui
                else:
                    engine_int2_rel = 0.0
                    engine_int3_rel = 0.0
            else:
                engine_int1 = int1_gui
                engine_int2_rel = int2_gui
                engine_int3_rel = int3_gui
            comp = {
                "kind": kind,
                "delta": float(vals.get(p + "delta", 0.0)),
                "quad": float(vals.get(p + "quad", 0.0)),
                "bhf": float(vals.get(p + "bhf", 33.0)),
                "gamma": float(vals.get(p + "gamma1", 0.18)),
                "gamma2_rel": float(vals.get(p + "gamma2", 1.0)),
                "gamma3_rel": float(vals.get(p + "gamma3", 1.0)),
                "int1": engine_int1,
                "int2_rel": engine_int2_rel,
                "int3_rel": engine_int3_rel,
            }
            components.append(comp)
            indices.append(cp.idx)
        return (components or None), indices

    # ── L-curve α scanner (modo distribución) ────────────────────────────
    def on_lcurve(self) -> None:
        if not self.is_distribution_mode:
            QtWidgets.QMessageBox.information(
                self, tr("bhf.lcurve_alpha"),
                "Disponible solo en modo distribución P(BHF) / P(ΔEQ).")
            return
        if self.file.velocity is None or self.file.y_data is None:
            return
        d = self.dist_panel
        alphas = np.logspace(-6, 2, 25)
        self.statusBar().showMessage(f"Escaneando α (n={len(alphas)})…")
        QtWidgets.QApplication.processEvents()
        var = self.dist_variable
        bmin = float(d.bmin.value()); bmax = max(bmin + 0.5, float(d.bmax.value()))
        nbins = max(5, int(round(d.nbins.value())))
        sharp_components, _sharp_indices = self._active_sharp_components_for_distribution()
        fit_baseline = not self.calib.baseline.is_fixed()
        fit_slope = not self.calib.slope.is_fixed()
        try:
            common = dict(
                delta=float(d.delta.value()), gamma=float(d.gamma.value()),
                fit_baseline=fit_baseline, fit_slope=fit_slope,
                baseline=float(self.calib.baseline.value()), slope=float(self.calib.slope.value()),
                pmin=bmin, pmax=bmax, nbins=nbins, sigma=self.file.sigma,
                sharp_components=sharp_components,
            )
            if var == "quad":
                fits = [fit_hyperfine_distribution(
                    self.file.velocity, self.file.y_data, variable="quad",
                    bhf=float(d.fixed_bhf.value()), alpha=float(a), reg_mode=d.reg_mode, **common) for a in alphas]
            else:
                fits = [fit_hyperfine_distribution(
                    self.file.velocity, self.file.y_data, variable="bhf",
                    quad=float(d.quad.value()), alpha=float(a), reg_mode=d.reg_mode, **common) for a in alphas]
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("bhf.lcurve_alpha"),
                                            f"{type(exc).__name__}: {exc}")
            return
        # Diálogo: residuo² vs rugosidad
        resid_norm = np.array([float(np.linalg.norm(f.residuals)) for f in fits])
        rough = np.array([float(np.linalg.norm(np.diff(f.weights, 2)))
                          if f.weights.size > 2 else 0.0 for f in fits])
        rms = np.array([f.rms for f in fits])
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("bhf.lcurve_alpha"))
        dlg.resize(820, 540)
        v = QtWidgets.QVBoxLayout(dlg)
        fig = Figure(figsize=(8.0, 5.0), dpi=96)
        cv = FigureCanvas(fig); v.addWidget(cv, stretch=1)
        ax1 = fig.add_subplot(1, 2, 1)
        ax1.loglog(rough, resid_norm, "o-", color="#2563eb", ms=4)
        for i, a in enumerate(alphas):
            ax1.annotate(f"{np.log10(a):+.1f}", (rough[i], resid_norm[i]),
                          fontsize=6, alpha=0.7)
        ax1.set_xlabel(tr("plot.lcurve_xlabel"))
        ax1.set_ylabel(tr("plot.lcurve_ylabel"))
        ax1.set_title(tr("plot.lcurve_title"))
        ax1.grid(True, alpha=0.3, which="both")
        ax2 = fig.add_subplot(1, 2, 2)
        ax2.semilogx(alphas, rms, "o-", color="#ef4444", ms=4)
        ax2.set_xlabel("α")
        ax2.set_ylabel(tr("plot.label_rms"))
        ax2.set_title(tr("plot.alpha_scan_title"))
        ax2.grid(True, alpha=0.3, which="both")
        fig.tight_layout(); cv.draw_idle()
        best_idx = int(np.nanargmin(rms)) if rms.size else 0
        suggest = float(alphas[best_idx]) if alphas.size else 10.0 ** float(d.log_alpha.value())
        buttons = QtWidgets.QHBoxLayout()
        btn_use = QtWidgets.QPushButton(tr("button.use_lcurve", default="Usar α={value}", value=suggest))
        btn_use.clicked.connect(lambda _=False, a=suggest, dialog=dlg: (d.log_alpha.set_value(float(np.log10(a))), dialog.accept()))
        buttons.addWidget(btn_use); buttons.addStretch(1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); buttons.addWidget(bb)
        v.addLayout(buttons)
        dlg.exec()

    # ── Acciones rápidas ─────────────────────────────────────────────────
    def on_find_center(self) -> None:
        if self.file.counts is None:
            return
        center = find_best_integer_or_half_center(self.file.counts)
        # Re-dobla con el nuevo centro y aplica el recorte de bordes de Tk.
        self._refold_current_data(center)
        self._building = True
        self.calib.center.set_value(center)
        self._building = False
        self.statusBar().showMessage(f"Centro detectado: {center:.4f}", 5000)
        self._refresh_plot()

    def on_save_fit(self) -> None:
        """Exporta velocidad / datos / modelo / residuo en TSV."""
        if self.file.velocity is None or self.file.y_data is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("file.save_fit"), str(ROOT),
            "TSV (*.dat *.tsv);;All (*.*)")
        if not path:
            return
        state = self._build_state()
        v = self.file.velocity
        y = self.file.y_data
        try:
            model = model_from_values(v, state.values, state.components, state.constraints,
                                      absorber_model=state.absorber_model) if state else None
        except Exception:
            model = None
        residual = (y - model) if model is not None else np.zeros_like(y)
        cols = ["velocity_mm_s", "data_norm"]
        rows = [v, y]
        if model is not None:
            cols += ["model", "residual"]
            rows += [model, residual]
        if self.file.folded is not None:
            cols.append("folded_counts"); rows.append(self.file.folded)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\t".join(cols) + "\n")
                for i in range(v.size):
                    fh.write("\t".join(f"{rows[j][i]:.8g}" for j in range(len(cols))) + "\n")
            self.statusBar().showMessage(f"Ajuste guardado: {path}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("file.save_fit"),
                                            f"{type(exc).__name__}: {exc}")

    def on_changelog(self) -> None:
        from mossbauer_fe33_gui_v2IA import CHANGELOG_PATH
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("help.changelog"))
        dlg.resize(820, 600)
        v = QtWidgets.QVBoxLayout(dlg)
        text = QtWidgets.QTextBrowser()
        text.setOpenExternalLinks(True)
        if CHANGELOG_PATH.exists():
            content = CHANGELOG_PATH.read_text(encoding="utf-8", errors="replace")
            text.setPlainText(content)
        else:
            text.setPlainText(tr("help.changelog_unavailable"))
        v.addWidget(text, stretch=1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.exec()

    def _load_fixed_distribution(self, path: Path) -> tuple[np.ndarray, np.ndarray]:
        """Lee dos columnas (centers, weights) de un .txt/.dat/.csv."""
        raw = Path(path).read_text(encoding="utf-8", errors="replace").strip().splitlines()
        c, w = [], []
        for line in raw:
            line = line.strip()
            if not line or line.startswith(("#", "//")):
                continue
            parts = line.replace(",", " ").replace(";", " ").split()
            if len(parts) < 2:
                continue
            try:
                c.append(float(parts[0])); w.append(float(parts[1]))
            except ValueError:
                continue
        return np.array(c, dtype=float), np.array(w, dtype=float)

    def _on_load_fixed_distribution(self) -> None:
        """Carga una distribución P fija desde fichero (dos columnas)."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, tr("bhf.load_fixed"), str(ROOT),
            "Texto (*.txt *.dat *.csv *.tsv);;All (*.*)")
        if not path:
            return
        self.dist_panel.fixed_path = Path(path)
        self.statusBar().showMessage(f"P fija: {path}", 5000)

    # ── Ajuste distribución P(BHF) ──────────────────────────────────────
    def on_fit_distribution(self) -> None:
        self._simulate_enabled = True
        if self.file.velocity is None or self.file.y_data is None:
            return
        d = self.dist_panel
        bmin = float(d.bmin.value())
        bmax = max(bmin + 0.5, float(d.bmax.value()))
        nbins = max(5, int(round(d.nbins.value())))
        alpha = 10.0 ** float(d.log_alpha.value())
        var = self.dist_variable
        shape = d.shape
        label = "P(ΔEQ)" if var == "quad" else "P(BHF)"
        self.statusBar().showMessage(f"Ajustando {label} [{shape}]…")
        _dlg, update_progress, close_progress = self._open_progress_dialog(
            tr("progress.distribution_title", default="Distribución hiperfina"),
            tr("progress.distribution_prepare", default="Preparando ajuste de distribución…"))
        sharp_components, sharp_indices = self._active_sharp_components_for_distribution()
        fit_baseline = not self.calib.baseline.is_fixed()
        fit_slope = not self.calib.slope.is_fixed()
        base_delta = float(d.delta.value())
        base_gamma = float(d.gamma.value())
        v_arr = self.file.velocity
        y_arr = self.file.y_data

        def run_fit(delta_value: float, gamma_value: float, sharp_for_fit: list[dict[str, float]] | None):
            common = dict(
                variable=var, delta=delta_value, gamma=gamma_value,
                quad=(0.0 if var == "quad" else float(d.quad.value())),
                bhf=(float(d.fixed_bhf.value()) if var == "quad" else BHF_DEFAULT_T),
                baseline=float(self.calib.baseline.value()), slope=float(self.calib.slope.value()),
                sharp_components=sharp_for_fit,
            )
            if shape == "Histograma":
                return fit_hyperfine_distribution(
                    v_arr, y_arr, pmin=bmin, pmax=bmax, nbins=nbins, alpha=alpha,
                    fit_baseline=fit_baseline, fit_slope=fit_slope,
                    sigma=self.file.sigma, reg_mode=d.reg_mode, **common)
            if shape == "Gaussiana":
                return fit_gaussian_hyperfine_distribution(
                    v_arr, y_arr, pmin=bmin, pmax=bmax, nbins=nbins, **common)
            if shape == "Binomial":
                return fit_binomial_hyperfine_distribution(
                    v_arr, y_arr, pmin=bmin, pmax=bmax, nbins=nbins, **common)
            if shape == "Fija":
                if d.fixed_path is None:
                    raise RuntimeError("Carga primero un fichero de P fija.")
                centers_arr, weights_arr = self._load_fixed_distribution(d.fixed_path)
                return fit_fixed_hyperfine_distribution(
                    v_arr, y_arr, centers_arr, weights_arr, **common)
            raise RuntimeError(f"Forma desconocida: {shape}")

        outer_specs: list[tuple[str, str, float, float]] = []
        if self.dist_refine_global:
            if not d.delta.is_fixed():
                outer_specs.append(("dist_delta", "lin", -2.5, 2.5))
            if not d.gamma.is_fixed():
                outer_specs.append(("dist_gamma", "loggamma", 0.03, 1.0))
        if sharp_components:
            for pos, idx in enumerate(sharp_indices):
                cp = self.components_panels[idx - 1]
                for pname in ("delta", "quad", "bhf", "gamma1"):
                    if pname == "quad" and cp.kind == "Singlete":
                        continue
                    if pname == "bhf" and cp.kind != "Sextete":
                        continue
                    ctl = cp.params[pname]
                    if ctl.is_fixed():
                        continue
                    outer_specs.append((f"sharp:{pos}:{pname}",
                                        "loggamma" if pname == "gamma1" else "lin",
                                        ctl._lo, ctl._hi))

        def x0_bounds() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            x0, lo, hi = [], [], []
            for key, kind, lo_v, hi_v in outer_specs:
                if key == "dist_delta":
                    cur = base_delta
                elif key == "dist_gamma":
                    cur = base_gamma
                else:
                    _sharp, pos_txt, pname = key.split(":")
                    cur = float(sharp_components[int(pos_txt)]["gamma" if pname == "gamma1" else pname])
                if kind == "loggamma":
                    x0.append(np.log(max(cur, lo_v))); lo.append(np.log(lo_v)); hi.append(np.log(hi_v))
                else:
                    x0.append(cur); lo.append(lo_v); hi.append(hi_v)
            return np.array(x0, dtype=float), np.array(lo, dtype=float), np.array(hi, dtype=float)

        def expand(x: np.ndarray) -> tuple[float, float, list[dict[str, float]] | None]:
            delta_value = base_delta
            gamma_value = base_gamma
            local_sharp = [dict(c) for c in sharp_components] if sharp_components else None
            for i, (key, kind, _lo, _hi) in enumerate(outer_specs):
                value = float(np.exp(x[i])) if kind == "loggamma" else float(x[i])
                if key == "dist_delta":
                    delta_value = value
                elif key == "dist_gamma":
                    gamma_value = value
                elif local_sharp is not None:
                    _sharp, pos_txt, pname = key.split(":")
                    local_sharp[int(pos_txt)]["gamma" if pname == "gamma1" else pname] = value
            return delta_value, gamma_value, local_sharp

        fitted_x = None
        try:
            if outer_specs:
                update_progress(tr("progress.distribution_refine",
                                   default="Refinando δ y Γ globales…"))
                x0, lo, hi = x0_bounds()
                x0 = np.clip(x0, lo, hi)
                def residual_outer(x: np.ndarray) -> np.ndarray:
                    dd, gg, ss = expand(x)
                    return run_fit(dd, gg, ss).residuals
                opt = least_squares(residual_outer, x0, bounds=(lo, hi), max_nfev=60)
                fitted_x = opt.x
                delta_final, gamma_final, sharp_final = expand(fitted_x)
                update_progress(tr("progress.distribution_compute_final",
                                   default="Calculando distribución final…"))
                result = run_fit(delta_final, gamma_final, sharp_final)
            else:
                update_progress(tr("progress.distribution_compute", shape=shape,
                                   default=f"Calculando distribución {shape}…"))
                result = run_fit(base_delta, base_gamma, sharp_components)
        except Exception as exc:
            close_progress()
            QtWidgets.QMessageBox.critical(self, tr("fit.run"),
                                            f"{type(exc).__name__}: {exc}")
            return

        self._building = True
        self.calib.baseline.set_value(float(result.baseline))
        self.calib.slope.set_value(float(result.slope))
        if fitted_x is not None:
            for i, (key, kind, _lo, _hi) in enumerate(outer_specs):
                value = float(np.exp(fitted_x[i])) if kind == "loggamma" else float(fitted_x[i])
                if key == "dist_delta":
                    d.delta.set_value(value)
                elif key == "dist_gamma":
                    d.gamma.set_value(value)
                elif key.startswith("sharp:"):
                    _sharp, pos_txt, pname = key.split(":")
                    cp = self.components_panels[sharp_indices[int(pos_txt)] - 1]
                    cp.params[pname].set_value(value)
        if self.dist_use_sharp and result.sharp_weights is not None:
            for idx, weight in zip(sharp_indices, result.sharp_weights):
                self.components_panels[idx - 1].params["depth"].set_value(float(weight))
        self._building = False
        close_progress()

        style = get_style(self.plot_style_name)
        show_res = self.act_show_residual.isChecked() if hasattr(self, "act_show_residual") else True
        show_leg = self.act_show_legend.isChecked() if hasattr(self, "act_show_legend") else True
        self.canvas.render(self.file.velocity, self.file.y_data,
                           model=result.fitted_curve, style=style,
                           show_residual=show_res, show_legend=show_leg)
        msg = (f"{label}: bins={nbins}  α=10^{d.log_alpha.value():.2f}  "
               f"RMS={result.rms:.5g}")
        self.statusBar().showMessage(msg)
        class _R:
            pass
        r = _R()
        r.stats = {"chi2": float(np.sum(result.residuals**2)), "red_chi2": float(result.rms),
                   "dof": 0.0, "aic": 0.0, "bic": 0.0}
        r.free_keys = []
        r.values = {"baseline": result.baseline, "slope": result.slope, "alpha": result.alpha}
        r.errors = {}
        r.correlations = {}
        r.n_starts = 1
        self.info_panel.show_result(r)
        self._show_distribution_dialog(result)

    def _show_distribution_dialog(self, result) -> None:
        var = self.dist_variable
        title = "P(ΔEQ)" if var == "quad" else "P(BHF)"
        xlabel = (tr("plot.distribution_xlabel_deq") if var == "quad"
                  else tr("plot.distribution_xlabel_bhf"))
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(720, 480)
        v = QtWidgets.QVBoxLayout(dlg)
        fig = Figure(figsize=(8.0, 4.5), dpi=96)
        cv = FigureCanvas(fig); v.addWidget(cv, stretch=1)
        ax = fig.add_subplot(111)
        ax.plot(result.bhf_centers, result.probability, "-", color="#2563eb", lw=2.0)
        ax.fill_between(result.bhf_centers, result.probability, 0, color="#93c5fd", alpha=0.45)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(title)
        ax.grid(True, alpha=0.3)
        fig.tight_layout(); cv.draw_idle()
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); v.addWidget(bb)
        dlg.exec()

    # ── Auto-inicialización desde mínimos ───────────────────────────────
    def _smooth_1d(self, values: np.ndarray, window: int) -> np.ndarray:
        """Suavizado de media móvil equivalente al usado por la GUI Tk."""
        window = int(max(3, window))
        if window % 2 == 0:
            window += 1
        if values.size < window:
            return values.astype(float).copy()
        kernel = np.ones(window, dtype=float) / float(window)
        pad = window // 2
        padded = np.pad(values.astype(float), pad, mode="edge")
        return np.convolve(padded, kernel, mode="valid")

    def detect_absorption_minima(self) -> tuple[list[dict[str, float]], float, float]:
        """Detecta mínimos de transmisión como máximos de absorción.

        Qt usaba una detección directa sobre datos sin suavizar y solo miraba la
        primera componente. Esta versión porta la heurística robusta de Tk:
        baseline lineal en la zona alta, umbrales por ruido/prominencia,
        anchuras FWHM aproximadas y eliminación de duplicados cercanos.
        """
        if self.file.velocity is None or self.file.y_data is None or self.file.y_data.size < 7:
            return [], 1.0, 0.0
        v = self.file.velocity
        y = self.file.y_data
        high = y >= np.percentile(y, 70)
        if int(np.sum(high)) >= 4:
            slope, baseline0 = np.polyfit(v[high], y[high], 1)
        else:
            baseline0 = float(np.percentile(y, 90))
            slope = 0.0
        baseline_line = baseline0 + slope * v
        absorption = np.maximum(baseline_line - y, 0.0)

        coarse_smooth = self._smooth_1d(absorption, max(5, absorption.size // 80))
        max_abs = float(np.nanmax(coarse_smooth)) if coarse_smooth.size else 0.0
        if max_abs <= 0:
            return [], float(baseline0), float(slope)
        diff_noise = np.diff(coarse_smooth)
        noise = (1.4826 * float(np.median(np.abs(diff_noise - np.median(diff_noise))))
                 if diff_noise.size else 0.0)

        fine_win = max(3, absorption.size // 120)
        if fine_win % 2 == 0:
            fine_win += 1
        fine_smooth = self._smooth_1d(absorption, fine_win)

        dv = abs(float(v[1] - v[0])) if v.size > 1 else 0.05
        min_dist_ch = max(3, int(0.15 / dv))
        height_thr = max(0.06 * max_abs, 4.0 * noise, 5e-4)
        prom_thr = max(0.05 * max_abs, 2.5 * noise, 3e-4)

        try:
            from scipy.signal import find_peaks as _find_peaks
        except ImportError:
            return [], float(baseline0), float(slope)
        peak_idxs, _ = _find_peaks(fine_smooth, height=height_thr,
                                   prominence=prom_thr, distance=min_dist_ch)

        peaks: list[dict[str, float]] = []
        min_distance = max(0.12, 2.0 * dv)
        for i in peak_idxs:
            half = 0.5 * fine_smooth[i]
            left = int(i)
            while left > 0 and fine_smooth[left] > half:
                left -= 1
            right = int(i)
            while right < fine_smooth.size - 1 and fine_smooth[right] > half:
                right += 1
            width = abs(float(v[right] - v[left])) if right > left else min_distance
            peaks.append({"i": float(i), "pos": float(v[i]),
                          "depth": float(absorption[i]),
                          "smooth_depth": float(fine_smooth[i]),
                          "width": width})

        selected: list[dict[str, float]] = []
        for peak in sorted(peaks, key=lambda p: p["smooth_depth"], reverse=True):
            if all(abs(peak["pos"] - q["pos"]) >= min_distance for q in selected):
                selected.append(peak)
        return sorted(selected[:15], key=lambda p: p["pos"]), float(baseline0), float(slope)

    def _best_sextet_from_peaks(
        self, peaks: list[dict[str, float]]
    ) -> tuple[list[dict[str, float]], float, float, float, float] | None:
        if len(peaks) < 5:
            split = self._try_split_peaks_for_sextet(peaks)
            if split is not None:
                return split
            return None
        from itertools import combinations
        candidates = sorted(peaks, key=lambda p: p["smooth_depth"], reverse=True)[:10]
        best = None
        iterator = combinations(candidates, 6) if len(candidates) >= 6 else [tuple(candidates[:5])]
        for subset in iterator:
            sub = sorted(subset, key=lambda p: p["pos"])
            pos = np.array([p["pos"] for p in sub], dtype=float)
            if len(sub) == 6:
                ref = LINE_POS_33T
            else:
                local_best = None
                for missing in range(6):
                    ref5 = np.delete(LINE_POS_33T, missing)
                    A5 = np.column_stack([np.ones(ref5.size), ref5])
                    delta5, scale5 = np.linalg.lstsq(A5, pos, rcond=None)[0]
                    pred5 = delta5 + scale5 * ref5
                    rms5 = float(np.sqrt(np.mean((pos - pred5) ** 2)))
                    if local_best is None or rms5 < local_best[0]:
                        local_best = (rms5, delta5, scale5, missing)
                if local_best is None:
                    continue
                rms, delta, scale, missing_idx = local_best
                bhf = scale * BHF_DEFAULT_T
                if 10.0 <= bhf <= 60.0 and (best is None or rms < best[0]):
                    weights5 = np.delete(np.array([3.0, 2.0, 1.0, 1.0, 2.0, 3.0]), missing_idx)
                    depths = np.array([p["depth"] for p in sub], dtype=float)
                    depth_est = float(np.median(depths / weights5))
                    best = (rms, list(sub), float(delta), float(bhf),
                            float(np.median([p["width"] for p in sub])), depth_est)
                continue
            A = np.column_stack([np.ones(ref.size), ref])
            delta, scale = np.linalg.lstsq(A, pos, rcond=None)[0]
            pred = delta + scale * ref
            rms = float(np.sqrt(np.mean((pos - pred) ** 2)))
            bhf = scale * BHF_DEFAULT_T
            if not (10.0 <= bhf <= 60.0):
                continue
            if best is None or rms < best[0]:
                weights = np.array([3.0, 2.0, 1.0, 1.0, 2.0, 3.0], dtype=float)
                depths = np.array([p["depth"] for p in sub], dtype=float)
                depth_est = float(np.median(depths / weights))
                best = (rms, list(sub), float(delta), float(bhf),
                        float(np.median([p["width"] for p in sub])), depth_est)
        if best is None:
            return self._try_split_peaks_for_sextet(peaks)
        score, sub, delta, bhf, width, depth = best
        if score > max(0.45, 0.10 * max(1.0, abs(bhf / BHF_DEFAULT_T))):
            return self._try_split_peaks_for_sextet(peaks)
        return sub, delta, bhf, width, depth

    def _try_split_peaks_for_sextet(self, peaks: list[dict[str, float]]) -> tuple | None:
        if len(peaks) < 4 or len(peaks) >= 6:
            return None
        from itertools import combinations as _comb
        median_width = float(np.median([p["width"] for p in peaks]))
        median_depth = float(np.median([p["depth"] for p in peaks]))

        def is_normal(pk: dict) -> bool:
            return pk["width"] <= median_width * 1.25 and pk["depth"] <= median_depth * 1.40

        normal_peaks = [p for p in peaks if is_normal(p)]
        if len(normal_peaks) < 2:
            normal_peaks = sorted(peaks, key=lambda p: p["width"])[:2]
        narrow_tol = max(median_width * 0.5, 0.20)
        next_vid = max(p["i"] for p in peaks) + 1.0
        best_result = None
        best_score = -1
        seen: set[tuple] = set()
        for pk_a, pk_b in _comb(sorted(normal_peaks, key=lambda p: p["pos"]), 2):
            span_obs = abs(pk_b["pos"] - pk_a["pos"])
            if span_obs < 0.5:
                continue
            for la in range(6):
                for lb in range(la + 1, 6):
                    span_ref = LINE_POS_33T[lb] - LINE_POS_33T[la]
                    if abs(span_ref) < 0.3:
                        continue
                    scale = span_obs / span_ref
                    bhf_est = scale * BHF_DEFAULT_T
                    if not (10.0 <= bhf_est <= 60.0):
                        continue
                    delta = pk_a["pos"] - scale * LINE_POS_33T[la]
                    pred_all = delta + scale * LINE_POS_33T
                    if max(abs(pk_a["pos"] - pred_all[la]),
                           abs(pk_b["pos"] - pred_all[lb])) > 0.18:
                        continue
                    key = (round(bhf_est, 1), round(delta, 2))
                    if key in seen:
                        continue
                    seen.add(key)
                    augmented = list(peaks)
                    vid = next_vid
                    virtual_added = 0
                    for pred_pos in pred_all:
                        if any(abs(p["pos"] - pred_pos) < narrow_tol and is_normal(p)
                               for p in peaks):
                            continue
                        for pk in sorted(peaks, key=lambda p: abs(p["pos"] - pred_pos)):
                            if abs(pk["pos"] - pred_pos) > pk["width"] * 0.7:
                                break
                            if not is_normal(pk):
                                augmented.append({
                                    "i": vid, "pos": float(pred_pos),
                                    "depth": pk["depth"] * 0.45,
                                    "smooth_depth": pk["smooth_depth"] * 0.45,
                                    "width": pk["width"] * 0.65,
                                })
                                vid += 1.0
                                virtual_added += 1
                                break
                    if virtual_added == 0:
                        continue
                    result = self._best_sextet_from_peaks(augmented)
                    if result is None:
                        continue
                    _, delta_r, bhf_r, _, _ = result
                    scale_r = bhf_r / BHF_DEFAULT_T
                    pred_r = delta_r + scale_r * LINE_POS_33T
                    score = sum(
                        1 for pk in peaks if not is_normal(pk)
                        and sum(1 for pp in pred_r if abs(pk["pos"] - pp) < pk["width"] * 0.65) >= 2
                    )
                    if score > best_score:
                        best_score = score
                        best_result = result
        return best_result

    def _try_2peak_sextet_estimate(
        self, peaks: list[dict[str, float]]
    ) -> tuple[list[dict[str, float]], float, float, float, float] | None:
        if len(peaks) != 2:
            return None
        from core.constants import _BASE_POSITIONS
        p = sorted(peaks, key=lambda x: x["pos"])
        obs_spacing = p[1]["pos"] - p[0]["pos"]
        if obs_spacing < 0.5:
            return None
        spacing_ref = float(_BASE_POSITIONS[1] - _BASE_POSITIONS[0])
        scale = obs_spacing / spacing_ref
        bhf = scale * BHF_DEFAULT_T
        if not (25.0 <= bhf <= 60.0):
            return None
        best: tuple | None = None
        if p[0]["pos"] < 0 and p[1]["pos"] < 0:
            delta_01 = p[0]["pos"] - scale * float(_BASE_POSITIONS[0])
            if abs(delta_01) <= 1.5:
                best = (delta_01, bhf, (3.0, 2.0))
        if p[0]["pos"] > 0 and p[1]["pos"] > 0:
            delta_45 = p[0]["pos"] - scale * float(_BASE_POSITIONS[4])
            if abs(delta_45) <= 1.5:
                best = (delta_45, bhf, (2.0, 3.0))
        if best is None:
            return None
        delta_est, bhf_est, (w0, w1) = best
        width = float(np.mean([p[0]["width"], p[1]["width"]]))
        depth = float(np.median([p[0]["depth"] / w0, p[1]["depth"] / w1]))
        return list(p), delta_est, bhf_est, width, depth

    def _depth_profile_hint(self, peaks: list[dict[str, float]]) -> tuple[str, list[dict[str, float]]] | None:
        if not peaks:
            return None
        by_d = sorted(peaks, key=lambda p: p["smooth_depth"], reverse=True)
        d0 = by_d[0]["smooth_depth"]
        d1 = by_d[1]["smooth_depth"] if len(by_d) > 1 else 0.0
        d2 = by_d[2]["smooth_depth"] if len(by_d) > 2 else 0.0
        if d0 > 2.5 * max(d1, 1e-10) and abs(by_d[0]["pos"]) < 2.5:
            return "Singlete", [by_d[0]]
        if len(by_d) >= 2 and d1 >= 0.40 * d0 and d2 < 0.30 * d0 and len(peaks) <= 4:
            pair = sorted([by_d[0], by_d[1]], key=lambda p: p["pos"])
            sep = abs(pair[1]["pos"] - pair[0]["pos"])
            if 0.18 <= sep <= 5.0:
                return "Doblete", pair
        return None

    def _rescale_minima_depths(self, params: dict[str, float], component_indices: tuple[int, ...]) -> None:
        if self.file.velocity is None or self.file.y_data is None:
            return
        v = self.file.velocity
        baseline = float(params.get("baseline", self.calib.baseline.value()))
        slope = float(params.get("slope", self.calib.slope.value()))
        comps = []
        depth_keys = []
        for idx in component_indices:
            cp = self.components_panels[idx - 1]
            p = f"s{idx}_"
            vals = {name: params.get(p + name, cp.params[name].value()) for name in cp.params}
            params.update({p + name: float(vals[name]) for name in vals})
            comps.append(Component(idx=idx, enabled=True, kind=cp.kind,
                                   intensity_mode=cp.intensity_mode,
                                   quad_treatment=cp.quad_treatment))
            depth_keys.append(p + "depth")
        if not comps:
            return
        baseline_line = baseline + slope * v
        values = {**params, "baseline": baseline, "slope": slope}
        try:
            model = model_from_values(v, values, comps, self.constraints,
                                      absorber_model=self.absorber_model)
        except Exception:
            return
        model_abs = float(np.max(baseline_line - model)) if v.size else 0.0
        data_abs = float(np.max(baseline_line - self.file.y_data)) if v.size else 0.0
        if model_abs > 1e-6 and data_abs > 0.0 and model_abs > data_abs:
            factor = data_abs / model_abs
            for key in depth_keys:
                if key in params:
                    params[key] = float(params[key] * factor)

    def on_init_from_minima(self, show_message: bool = True) -> bool:
        """Detecta mínimos y configura componentes discretas como en Tk."""
        if self.file.velocity is None or self.file.y_data is None:
            return False
        peaks, baseline, slope = self.detect_absorption_minima()
        if not peaks:
            if show_message:
                QtWidgets.QMessageBox.information(
                    self, tr("fit.init_from_minima"),
                    tr("msg.auto_minima_none", default="No se detectaron mínimos de absorción."))
            return False

        self.mode_combo.setCurrentIndex(0)
        params: dict[str, float] = {
            "baseline": baseline,
            "slope": float(np.clip(slope, -1e-4, 1e-4)),
        }
        for idx in range(1, MAX_QT_COMPONENTS + 1):
            p = f"s{idx}_"
            params.update({
                p + "delta": 0.0, p + "quad": 0.0, p + "bhf": BHF_DEFAULT_T,
                p + "gamma1": 0.15, p + "gamma2": 1.0, p + "gamma3": 1.0,
                p + "depth": 0.005, p + "int1": 3.0, p + "int2": 2.0, p + "int3": 1.0,
            })

        components: list[tuple[int, str, list[dict[str, float]]]] = []
        used_ids: set[int] = set()

        hint = self._depth_profile_hint(peaks)
        if hint is not None:
            kind_h, group_h = hint
            components.append((1, kind_h, group_h))
            pfx = "s1_"
            if kind_h == "Doblete":
                g = group_h
                params[pfx + "delta"] = float(np.mean([g[0]["pos"], g[1]["pos"]]))
                params[pfx + "quad"] = float(abs(g[1]["pos"] - g[0]["pos"]))
                params[pfx + "gamma1"] = float(np.clip(np.mean([x["width"] for x in g]) / 2.0, 0.04, 1.0))
                params[pfx + "gamma2"] = 1.0
                params[pfx + "depth"] = float(np.clip(np.mean([x["depth"] for x in g]), 0.002, 0.25))
                params[pfx + "int1"] = 1.0
                params[pfx + "int2"] = 1.0
            else:
                pk = group_h[0]
                params[pfx + "delta"] = float(pk["pos"])
                params[pfx + "gamma1"] = float(np.clip(pk["width"] / 2.0, 0.04, 1.0))
                params[pfx + "depth"] = float(np.clip(pk["depth"], 0.002, 0.25))
                params[pfx + "int1"] = 1.0
            used_ids.update(int(pk["i"]) for pk in group_h)
        else:
            sext = self._best_sextet_from_peaks(peaks)
            if sext is not None:
                sub, delta, bhf, width, depth = sext
                if len(sub) >= 5 and abs(sub[-1]["pos"] - sub[0]["pos"]) > 3.0:
                    components.append((1, "Sextete", sub))
                    p = "s1_"
                    params[p + "delta"] = float(np.clip(delta, -2.5, 2.5))
                    params[p + "bhf"] = float(np.clip(bhf, 20.0, 60.0))
                    params[p + "quad"] = 0.0
                    params[p + "gamma1"] = float(np.clip(width / 2.0, 0.04, 1.0))
                    params[p + "depth"] = float(np.clip(depth, 0.002, 0.25))
                    used_ids.update(int(pk["i"]) for pk in sub)

        remaining = [p for p in sorted(peaks, key=lambda q: q["smooth_depth"], reverse=True)
                     if int(p["i"]) not in used_ids]
        next_idx = 2 if components else 1
        while next_idx <= min(3, MAX_QT_COMPONENTS) and remaining:
            if len(remaining) >= 5:
                sext_extra = self._best_sextet_from_peaks(remaining)
                if sext_extra is not None:
                    sub_e, delta_e, bhf_e, width_e, depth_e = sext_extra
                    if len(sub_e) >= 5 and abs(sub_e[-1]["pos"] - sub_e[0]["pos"]) > 3.0:
                        pfx = f"s{next_idx}_"
                        components.append((next_idx, "Sextete", sub_e))
                        params[pfx + "delta"] = float(np.clip(delta_e, -2.5, 2.5))
                        params[pfx + "bhf"] = float(np.clip(bhf_e, 20.0, 60.0))
                        params[pfx + "quad"] = 0.0
                        params[pfx + "gamma1"] = float(np.clip(width_e / 2.0, 0.04, 1.0))
                        params[pfx + "depth"] = float(np.clip(depth_e, 0.002, 0.25))
                        sub_ids = {int(pk["i"]) for pk in sub_e}
                        remaining = [p for p in remaining if int(p["i"]) not in sub_ids]
                        next_idx += 1
                        continue
            two_peak_sext = self._try_2peak_sextet_estimate(remaining) if len(remaining) == 2 else None
            if two_peak_sext is not None:
                sub2, delta2, bhf2, width2, depth2 = two_peak_sext
                pfx = f"s{next_idx}_"
                components.append((next_idx, "Sextete", sub2))
                params[pfx + "delta"] = float(np.clip(delta2, -2.5, 2.5))
                params[pfx + "bhf"] = float(np.clip(bhf2, 20.0, 60.0))
                params[pfx + "quad"] = 0.0
                params[pfx + "gamma1"] = float(np.clip(width2 / 2.0, 0.04, 1.0))
                params[pfx + "depth"] = float(np.clip(depth2, 0.002, 0.25))
                remaining.clear()
                next_idx += 1
                continue
            if len(remaining) >= 2:
                pair = sorted(remaining[:2], key=lambda p: p["pos"])
                sep = abs(pair[1]["pos"] - pair[0]["pos"])
                if 0.18 <= sep <= 4.0:
                    kind = "Doblete"
                    group = pair
                    remaining = [p for p in remaining if p not in pair]
                else:
                    kind = "Singlete"
                    group = [remaining.pop(0)]
            else:
                kind = "Singlete"
                group = [remaining.pop(0)]
            components.append((next_idx, kind, group))
            pfx = f"s{next_idx}_"
            if kind == "Doblete":
                g = sorted(group, key=lambda p: p["pos"])
                params[pfx + "delta"] = float(np.mean([g[0]["pos"], g[1]["pos"]]))
                params[pfx + "quad"] = float(abs(g[1]["pos"] - g[0]["pos"]))
                params[pfx + "gamma1"] = float(np.clip(np.mean([x["width"] for x in g]) / 2.0, 0.04, 1.0))
                params[pfx + "gamma2"] = 1.0
                params[pfx + "depth"] = float(np.clip(np.mean([x["depth"] for x in g]), 0.002, 0.25))
                params[pfx + "int1"] = 1.0
                params[pfx + "int2"] = 1.0
            else:
                g = group[0]
                params[pfx + "delta"] = float(g["pos"])
                params[pfx + "gamma1"] = float(np.clip(g["width"] / 2.0, 0.04, 1.0))
                params[pfx + "depth"] = float(np.clip(g["depth"], 0.002, 0.25))
                params[pfx + "int1"] = 1.0
            next_idx += 1

        if not components:
            g = max(peaks, key=lambda p: p["depth"])
            components.append((1, "Singlete", [g]))
            params["s1_delta"] = float(g["pos"])
            params["s1_gamma1"] = float(np.clip(g["width"] / 2.0, 0.04, 1.0))
            params["s1_depth"] = float(np.clip(g["depth"], 0.002, 0.25))

        active_count = max(1, max((idx for idx, _kind, _g in components), default=1))
        self._building = True
        try:
            self._sync_component_count(active_count)
            for cp in self.components_panels:
                match = next(((kind, group) for idx, kind, group in components if idx == cp.idx), None)
                cp.enabled.setChecked(match is not None)
                cp.type_combo.setCurrentText(match[0] if match is not None else "Sextete")
                cp.apply_values(params)
                if match is not None:
                    used = ComponentPanel._USED_BY.get(cp.kind, set())
                    for name in used:
                        cp.params[name].set_fixed(False)
            self.calib.baseline.set_value(params["baseline"])
            self.calib.slope.set_value(params["slope"])
            self.calib.baseline.set_fixed(False)
            self.calib.slope.set_fixed(False)
            self._rescale_minima_depths(params, tuple(idx for idx, _kind, _g in components))
            for cp in self.components_panels:
                cp.apply_values(params)
        finally:
            self._building = False

        # Igual que en Tk: tras inicializar desde mínimos se dibuja ya la
        # simulación propuesta (habilita el trazado del modelo).
        self._simulate_enabled = True
        self._refresh_plot()
        summary = ", ".join(
            tr("text.component_kind_label", idx=idx, kind=tr(f"kind.{kind}", default=kind))
            for idx, kind, _g in components
        )
        msg = tr("msg.auto_minima_detected", n=len(peaks), summary=summary)
        self.statusBar().showMessage(f"{tr('msg.auto_minima_title')}: {summary}", 5000)
        if show_message:
            QtWidgets.QMessageBox.information(self, tr("msg.auto_minima_title"), msg)
        return True

    def on_auto_fit_from_minima(self) -> None:
        """Atajo: inicializa desde mínimos y a continuación ejecuta el ajuste."""
        if self.on_init_from_minima(show_message=False):
            if not self.is_distribution_mode:
                self.on_fit()

    def on_ai_summary(self) -> None:
        """Muestra un resumen JSON del espectro listo para pegar en un LLM."""
        if self.file.velocity is None or self.file.y_data is None:
            return
        peaks_raw, baseline, slope = self.detect_absorption_minima()
        v = self.file.velocity
        y = self.file.y_data
        peaks = [{"v_mm_s": round(float(p["pos"]), 4),
                  "depth": round(float(p["depth"]), 5),
                  "fwhm_mm_s": round(float(p["width"]), 4)}
                 for p in peaks_raw]
        summary = {
            "file": self.file.path.name if self.file.path else None,
            "n_channels": int(self.file.counts.size) if self.file.counts is not None else 0,
            "vmin_mm_s": round(float(np.min(v)), 4),
            "vmax_mm_s": round(float(np.max(v)), 4),
            "y_min": round(float(np.min(y)), 5),
            "y_max": round(float(np.max(y)), 5),
            "baseline_est": round(float(baseline), 5),
            "slope_est": round(float(slope), 7),
            "detected_minima": peaks,
            "ask": "Suggest a discrete Mössbauer Fe-57 fit (sextet/doublet/singlet) with starting δ, ΔEQ, BHF, Γ, depth.",
        }
        import json
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Resumen espectro (para IA/LLM)")
        dlg.resize(640, 480)
        v_lay = QtWidgets.QVBoxLayout(dlg)
        v_lay.addWidget(QtWidgets.QLabel(
            "<i>Copia este JSON en cualquier LLM (Ollama, ChatGPT, Claude, …) "
            "para que sugiera valores iniciales del ajuste.</i>"))
        text = QtWidgets.QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet("QTextEdit { font-family: monospace; font-size: 10pt; }")
        text.setPlainText(json.dumps(summary, indent=2, ensure_ascii=False))
        v_lay.addWidget(text, stretch=1)
        btn_copy = QtWidgets.QPushButton("Copiar al portapapeles")
        btn_copy.clicked.connect(
            lambda: QtWidgets.QApplication.clipboard().setText(text.toPlainText()))
        v_lay.addWidget(btn_copy)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        v_lay.addWidget(bb)
        dlg.exec()

    def on_profile_likelihood(self) -> None:
        """Para cada parámetro libre del último ajuste: perfila Δχ² y muestra los cruces."""
        state = self._build_state()
        if state is None:
            return
        self.statusBar().showMessage("Ajustando antes de perfilar…")
        QtWidgets.QApplication.processEvents()
        try:
            base = fit_discrete(state)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("fit.profile_likelihood"),
                                            f"{type(exc).__name__}: {exc}")
            return
        if not base.free_keys:
            QtWidgets.QMessageBox.information(
                self, tr("fit.profile_likelihood"),
                "No hay parámetros libres para perfilar.")
            return
        chi2_min = float(base.stats.get("chi2", 0.0))

        results: dict[str, dict] = {}
        n = len(base.free_keys)
        for i, key in enumerate(base.free_keys, 1):
            self.statusBar().showMessage(f"Perfilando {key} ({i}/{n})…")
            QtWidgets.QApplication.processEvents()
            best = float(base.values[key])
            sigma_est = float(base.errors.get(key) or max(0.05 * (abs(best) + 1.0), 1e-6))
            sigma_est = max(sigma_est, 1e-6)
            lo_b, hi_b = state.bounds.get(key, (best - 5 * sigma_est, best + 5 * sigma_est))
            grid = np.unique(np.concatenate([
                np.linspace(max(lo_b, best - 3 * sigma_est), best, 7),
                np.linspace(best, min(hi_b, best + 3 * sigma_est), 7),
            ]))
            costs = []
            for val in grid:
                sub = FitState(
                    velocity=state.velocity, y_data=state.y_data,
                    sigma_data=state.sigma_data,
                    values={**base.values, key: float(val)},
                    fixed={**state.fixed, key: True},
                    bounds=state.bounds, components=state.components,
                    constraints=state.constraints,
                    likelihood=state.likelihood, robust_loss=state.robust_loss,
                    line_profile=state.line_profile, voigt_sigma=state.voigt_sigma,
                    multistart_n=2,
                )
                try:
                    r = fit_discrete(sub)
                    costs.append(float(r.stats.get("chi2", float("inf"))))
                except Exception:
                    costs.append(float("inf"))
            d_chi2 = np.array(costs) - chi2_min
            intervals = asymmetric_intervals(grid, d_chi2, best)
            results[key] = {"best": best, "scan_values": grid.tolist(),
                            "d_chi2": d_chi2.tolist(), **intervals}
        self.statusBar().showMessage(f"Verosimilitud perfilada: {n} parámetros", 5000)
        self._show_profile_dialog(results)

    def _show_profile_dialog(self, results: dict) -> None:
        if not results:
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("msg.profile_lik_title"))
        dlg.resize(900, 600)
        v = QtWidgets.QVBoxLayout(dlg)
        v.addWidget(QtWidgets.QLabel(tr("dialog.profile_lik_subtitle")))
        fig = Figure(figsize=(8.5, 5.0), dpi=96)
        canvas = FigureCanvas(fig); v.addWidget(canvas, stretch=1)
        keys = list(results.keys())
        ncols = 2 if len(keys) > 1 else 1
        nrows = (len(keys) + ncols - 1) // ncols
        for i, k in enumerate(keys, 1):
            ax = fig.add_subplot(nrows, ncols, i)
            r = results[k]
            ax.plot(r["scan_values"], r["d_chi2"], "o-", color="#2563eb", ms=3)
            ax.axhline(1.0, color="#888", ls="--", lw=0.8)
            ax.axhline(4.0, color="#bbb", ls=":", lw=0.8)
            ax.axvline(r["best"], color="#ef4444", lw=0.8)
            ax.set_title(k, fontsize=9)
            ax.set_ylabel("Δχ²", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.grid(alpha=0.3)
        fig.tight_layout(); canvas.draw_idle()
        # Resumen como texto
        text_lines = []
        for k, r in results.items():
            best = r["best"]; pl = r.get("plus_1s"); mi = r.get("minus_1s")
            p_txt = f"+{pl:.4g}" if pl is not None else "—"
            m_txt = f"−{mi:.4g}" if mi is not None else "—"
            text_lines.append(f"  {k:14s} = {best:.6g}  ({p_txt} / {m_txt})")
        summary = QtWidgets.QTextEdit(); summary.setReadOnly(True)
        summary.setMaximumHeight(120)
        summary.setStyleSheet("QTextEdit { font-family: monospace; font-size: 10pt; }")
        summary.setPlainText("\n".join(text_lines))
        v.addWidget(summary)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.exec()

    # ── Ajuste en serie (batch) ─────────────────────────────────────────
    def on_batch_fit(self) -> None:
        dlg = BatchFitDialog(self)
        dlg.exec()

    def on_constraints(self) -> None:
        dlg = ConstraintsDialog(self)
        dlg.exec()

    def on_physical_presets(self) -> None:
        """Cuatro botones rápidos para imponer relaciones físicas habituales."""
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("options.physical_presets"))
        dlg.resize(520, 240)
        v = QtWidgets.QVBoxLayout(dlg)
        v.addWidget(QtWidgets.QLabel(
            "Aplica con un clic relaciones físicas sobre las componentes activas."))

        def _apply_321() -> None:
            """3:2:1 fijado en int1=3, int2=2, int3=1."""
            self._building = True
            for cp in self.components_panels:
                if not cp.enabled.isChecked():
                    continue
                cp.params["int1"].set_value(3.0); cp.params["int1"].set_fixed(True)
                cp.params["int2"].set_value(2.0); cp.params["int2"].set_fixed(True)
                cp.params["int3"].set_value(1.0); cp.params["int3"].set_fixed(True)
            self._building = False
            self._refresh_plot()

        def _equal_widths() -> None:
            """Γ2 = Γ3 = 1 (misma anchura)."""
            self._building = True
            for cp in self.components_panels:
                if not cp.enabled.isChecked():
                    continue
                cp.params["gamma2"].set_value(1.0); cp.params["gamma2"].set_fixed(True)
                cp.params["gamma3"].set_value(1.0); cp.params["gamma3"].set_fixed(True)
            self._building = False
            self._refresh_plot()

        def _link_delta() -> None:
            """δ de las componentes 2 y 3 atados al δ del componente 1."""
            for idx in (2, 3):
                cp = self.components_panels[idx - 1]
                if cp.enabled.isChecked():
                    self.constraints = [c for c in self.constraints
                                         if c.get("target") != f"s{idx}_delta"]
                    self.constraints.append({
                        "target": f"s{idx}_delta", "source": "s1_delta",
                        "factor": 1.0, "offset": 0.0,
                    })
            self._refresh_plot()

        def _link_gamma() -> None:
            """Γ1 de componentes 2 y 3 atados a Γ1 del 1."""
            for idx in (2, 3):
                cp = self.components_panels[idx - 1]
                if cp.enabled.isChecked():
                    self.constraints = [c for c in self.constraints
                                         if c.get("target") != f"s{idx}_gamma1"]
                    self.constraints.append({
                        "target": f"s{idx}_gamma1", "source": "s1_gamma1",
                        "factor": 1.0, "offset": 0.0,
                    })
            self._refresh_plot()

        for label, fn in (
            ("Sextetes polvo 3:2:1", _apply_321),
            ("Mismas anchuras (γ2 = γ3 = 1)", _equal_widths),
            ("Ligar δ a componente 1", _link_delta),
            ("Ligar Γ1 a componente 1", _link_gamma),
        ):
            btn = QtWidgets.QPushButton(label)
            btn.clicked.connect(fn)
            v.addWidget(btn)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); v.addWidget(bb)
        dlg.exec()

    def on_export_report(self) -> None:
        """Exporta un informe Markdown del ajuste actual."""
        if self.file.path is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("file.export_report"), str(ROOT),
            "Markdown (*.md);;All (*.*)")
        if not path:
            return
        state = self._build_state()
        if state is None:
            return
        lines: list[str] = []
        lines.append(f"# Mössbauer Fe-57 — Ajuste\n")
        lines.append(f"- Fichero: `{self.file.path.name}`")
        lines.append(f"- Canales: {self.file.counts.size if self.file.counts is not None else 0}")
        lines.append(f"- Centro de folding: {self.file.center:.4f}")
        lines.append(f"- Perfil de línea: {self.calib.line_profile}\n")
        # Calibración en uso (la que se está aplicando al espectro).
        ci = self.calibration_info
        lines.append("## Calibración\n")
        if ci:
            sample = ci.get("calibration_sample") or ci.get("calibration_file_name") or "—"
            lines.append(f"- Origen: {ci.get('source', '?')}")
            lines.append(f"- Muestra de calibración: {sample}")
            if ci.get("calibration_file_name"):
                lines.append(f"- Fichero de calibración: `{ci['calibration_file_name']}`")
            if ci.get("velocity_calibrated") is not None:
                lines.append(f"- Velocidad calibrada (Vmax): {float(ci['velocity_calibrated']):.6g} mm/s")
            if ci.get("isomer_shift") is not None:
                lines.append(f"- Desplazamiento isomérico de referencia: {float(ci['isomer_shift']):.6g} mm/s")
            if ci.get("calibration_date"):
                lines.append(f"- Fecha de calibración: {ci['calibration_date']}")
        else:
            lines.append("- (Sin calibración activa; δ sin corregir)")
        lines.append("")
        # Componentes activos
        lines.append("## Componentes\n")
        for cp in self.components_panels:
            if not cp.enabled.isChecked():
                continue
            lines.append(f"### Componente {cp.idx} — {cp.kind}")
            for k, ctl in cp.params.items():
                fixed = " (fijo)" if ctl.is_fixed() else ""
                lines.append(f"- `s{cp.idx}_{k}` = {ctl.value():.6g}{fixed}")
            lines.append("")
        # Si hay último ajuste, añadir estadísticas
        info_txt = self.info_panel.text.toPlainText().strip()
        if info_txt and info_txt != "—":
            lines.append("## Estadísticos del último ajuste\n")
            lines.append("```")
            lines.append(info_txt)
            lines.append("```\n")
        # Restricciones
        if self.constraints:
            lines.append("## Restricciones\n")
            for c in self.constraints:
                lines.append(f"- `{c['target']}` = {c.get('factor', 1.0):g} · "
                              f"`{c['source']}` + {c.get('offset', 0.0):g}")
            lines.append("")
        # Si hay calibración activa, incluye δ corregido.
        if self.calibration_info and self.calibration_info.get("isomer_shift") is not None:
            ref = float(self.calibration_info["isomer_shift"])
            lines.append(f"## δ corregido (iso_ref = {ref:.6g} mm/s)\n")
            for cp in self.components_panels:
                if not cp.enabled.isChecked():
                    continue
                d = cp.params["delta"].value()
                lines.append(f"- Componente {cp.idx}: δ corregido = {d - ref:.6g} mm/s")
            lines.append("")
        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8")
            self.statusBar().showMessage(f"Informe guardado: {path}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("file.export_report"),
                                            f"{type(exc).__name__}: {exc}")
            return

        # Preguntar si además se quiere un PDF (antes se generaba siempre).
        want_pdf = QtWidgets.QMessageBox.question(
            self, tr("file.export_report"),
            tr("msg.report_ask_pdf",
               default="Informe Markdown guardado. ¿Generar también un PDF?"),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes)
        if want_pdf != QtWidgets.QMessageBox.Yes:
            return
        # PDF: páginas con el texto del informe (monoespaciado) y, al final, la
        # gráfica actual, igual que en Tk.
        try:
            pdf_path = Path(path).with_suffix(".pdf")
            from matplotlib.backends.backend_pdf import PdfPages
            from matplotlib.figure import Figure as _PdfFigure
            import textwrap as _tw

            def _text_page(pdf, text_lines):
                fig = _PdfFigure(figsize=(8.27, 11.69), dpi=100, facecolor="white")
                ax = fig.add_subplot(111); ax.axis("off")
                ax.text(0.04, 0.97, "\n".join(text_lines), va="top", ha="left",
                        family="monospace", fontsize=8.5)
                pdf.savefig(fig, bbox_inches="tight")

            with PdfPages(pdf_path) as pdf:
                page_lines: list[str] = []
                for line in "\n".join(lines).splitlines():
                    for w in (_tw.wrap(line, width=95) or [""]):
                        page_lines.append(w)
                        if len(page_lines) >= 46:
                            _text_page(pdf, page_lines); page_lines = []
                if page_lines:
                    _text_page(pdf, page_lines)
                pdf.savefig(self.canvas.fig, bbox_inches="tight")
            self.statusBar().showMessage(f"Informe + PDF guardados: {path}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, tr("file.export_report"),
                f"No se pudo generar el PDF: {type(exc).__name__}: {exc}")

    def on_help(self) -> None:
        sections = get_help_sections(
            voigt_sigma=self.calib.voigt_sigma.value(),
            settings_path=SETTINGS_PATH,
            lang=get_language(),
        )
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("help.window_title"))
        dlg.resize(960, 640)
        v = QtWidgets.QVBoxLayout(dlg)
        header = QtWidgets.QLabel(f"<h2>{tr('help.header_title')}</h2>")
        header.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(header)
        # Lista lateral + texto: usamos QListWidget + QTextBrowser
        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        list_w = QtWidgets.QListWidget()
        for title, _heading, _content in sections:
            list_w.addItem(title)
        list_w.setMaximumWidth(260)
        split.addWidget(list_w)
        text_w = QtWidgets.QTextBrowser()
        text_w.setOpenExternalLinks(True)
        split.addWidget(text_w)
        split.setSizes([260, 700])
        v.addWidget(split, stretch=1)

        def show_section(idx: int) -> None:
            if 0 <= idx < len(sections):
                title, heading, content = sections[idx]
                html = (f"<h2>{title}</h2><h3 style='color:#475569;'>{heading}</h3>"
                        f"<pre style='white-space:pre-wrap; font-family:sans-serif;'>"
                        f"{content}</pre>")
                text_w.setHtml(html)

        list_w.currentRowChanged.connect(show_section)
        if sections:
            list_w.setCurrentRow(0)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.exec()

    def on_about(self) -> None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("help.about_title", version=APP_VERSION))
        v = QtWidgets.QVBoxLayout(dlg); v.setContentsMargins(24, 20, 24, 20)
        title = QtWidgets.QLabel(f"<h2>{APP_NAME}</h2>"); title.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(title)
        v.addWidget(QtWidgets.QLabel(
            f"<center>{tr('splash.version', version=APP_VERSION)}<br>"
            f"<i>{tr('main.subtitle')}</i></center>"))
        v.addSpacing(8)
        v.addWidget(QtWidgets.QLabel(
            f"<center><i>{tr('splash.click_to_continue')}</i></center>"))
        dlg.mousePressEvent = lambda _e: dlg.accept()
        dlg.exec()


def _show_splash(app: QtWidgets.QApplication, duration_ms: int = 1800) -> None:
    """Splash sencillo con nombre/versión; se cierra al pulsar o al expirar."""
    splash = QtWidgets.QDialog(None, QtCore.Qt.SplashScreen | QtCore.Qt.FramelessWindowHint)
    splash.setStyleSheet(
        "QDialog { background-color: #075985; }"
        "QLabel { color: white; }")
    splash.setFixedSize(440, 220)
    v = QtWidgets.QVBoxLayout(splash); v.setContentsMargins(36, 28, 36, 28)
    title = QtWidgets.QLabel(f"<h1 style='margin:0;'>{APP_NAME}</h1>")
    title.setAlignment(QtCore.Qt.AlignCenter)
    v.addWidget(title)
    ver = QtWidgets.QLabel(
        f"<center><b>{tr('splash.version', version=APP_VERSION)}</b><br>"
        f"<i>{tr('main.subtitle')}</i></center>")
    v.addWidget(ver)
    v.addStretch(1)
    hint = QtWidgets.QLabel(
        f"<center><i>{tr('splash.click_to_continue')}</i></center>")
    v.addWidget(hint)
    splash.mousePressEvent = lambda _e: splash.accept()
    # Cierre automático
    QtCore.QTimer.singleShot(duration_ms, splash.accept)
    splash.exec()


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    # Icono global (taskbar / dock)
    icon_png = ROOT / "assets" / "mossbauer_icon.png"
    if icon_png.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon_png)))
    # Estilo Fusion (Qt nativo, plano y moderno; igual en Win/Linux/macOS).
    try:
        app.setStyle("Fusion")
    except Exception:
        pass
    if "--no-splash" not in sys.argv:
        _show_splash(app)
    win = MossbauerQtWindow(); win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
