#!/usr/bin/env python3
"""Mössbauer Fe-57 — front-end Qt (PySide6).

Estado tras sesión 2: ventana principal con paneles de Calibración y Sextete
en la columna izquierda, plot principal embebido (matplotlib QtAgg),
acción Fit ▸ Run conectada al motor puro core.fit_engine.fit_discrete().

Pendiente: paneles file_info, info_display y reference; diálogos de ajuste
en serie / verosimilitud perfilada / restricciones; estilos QSS; tests.
"""
from __future__ import annotations

import html
import json
import os
import sys
import tempfile
import threading
import webbrowser
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
from core.data_io import CONFIG_DIR, SETTINGS_PATH, load_credentials, save_credentials  # noqa: E402
from core.constants import (  # noqa: E402
    APP_VERSION, APP_NAME, APP_AUTHOR, APP_DEPARTMENT,
    SEXTET_PARAM_NAMES, LINE_POS_33T, BHF_DEFAULT_T, GLOBAL_PARAM_NAMES,
    DIST_BHF_RANGE, DIST_QUAD_RANGE, DIST_RANGE_RESOLUTION,
)
from core.folding import (  # noqa: E402
    read_ws5_counts, find_best_integer_or_half_center, fold_integer_or_half,
)
from core.fit_engine import (  # noqa: E402
    Component, FitState, FitResult, fit_discrete, model_from_values,
    bootstrap_errors, profile_likelihood,
)
from core.session import ModelState  # noqa: E402
from core.physics import component_absorption  # noqa: E402
from core.plot_styles import get_style, apply_rc  # noqa: E402
from core.batch_fit import extract_metadata, write_results_csv, collect_trend_data  # noqa: E402
from mossbauer_distribution import (  # noqa: E402
    fit_hyperfine_distribution,
    fit_gaussian_hyperfine_distribution,
    fit_binomial_hyperfine_distribution,
    fit_fixed_hyperfine_distribution,
)
from mossbauer_updater import (  # noqa: E402
    ReleaseInfo, choose_download, download_file, find_release_checksum,
    install_zip_update, is_newer, is_zip_update, latest_release,
    _pip_install_requirements, _update_pip_stamp, check_requirements_if_needed,
    load_update_settings, save_update_settings,
)


# ─────────────────────────────────────────────────────────────────────────
#  Puente thread -> UI para tareas de actualización
# ─────────────────────────────────────────────────────────────────────────
class _UiCallBridge(QtCore.QObject):
    call = QtCore.Signal(object)


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

    def set_range(self, lo: float, hi: float, step: float | None = None) -> None:
        self._lo = float(lo)
        self._hi = float(hi)
        value = max(self._lo, min(self._hi, float(self.spin.value())))
        self._syncing = True
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setRange(self._lo, self._hi)
        if step is not None:
            self.spin.setSingleStep(float(step))
        self.spin.setValue(value)
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
    # 'int3' es la intensidad de referencia (=1, oculta y siempre fija, igual
    # que en Tk): no se incluye aquí para que nunca se libere ni se ajuste.
    _USED_BY = {
        "Sextete":  {"delta", "quad", "bhf", "gamma1", "gamma2", "gamma3",
                     "depth", "int1", "int2", "texture", "beta"},
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

    def relevant_params(self) -> set[str]:
        """Parámetros realmente usados por el tipo y modo actuales.

        Los no incluidos (p. ej. 'texture' en modo libre, 'beta' salvo Kundig
        fijo, int1/int2 en modo textura, int3 siempre) no deben ajustarse.
        """
        used = set(self._USED_BY.get(self.kind, set()))
        if self.kind == "Sextete":
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
        return used

    def _on_type_changed(self, kind: str) -> None:
        used = self.relevant_params()
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
#  Puente JS ↔ Python para la edición de mínimos en Plotly
# ─────────────────────────────────────────────────────────────────────────


class MinimaBridge(QtCore.QObject):
    """Recibe los clics sobre los marcadores de mínimos del gráfico Plotly.

    El gráfico vive en una página web (QWebEngineView); cuando el usuario clica
    un marcador, el JavaScript llama a estos slots a través de QWebChannel, lo
    que mantiene la lista lateral de Qt sincronizada con el gráfico.
    """

    toggled = QtCore.Signal(int)
    added = QtCore.Signal(float)

    @QtCore.Slot(int)
    def toggle(self, index: int) -> None:
        self.toggled.emit(int(index))

    @QtCore.Slot(float)
    def add(self, x: float) -> None:
        self.added.emit(float(x))


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
        self.last_render: dict | None = None
        # Estado para la actualización incremental (evita reconstruir toda la
        # figura en cada refresco: solo se reescriben los datos de las líneas).
        self._artists: dict | None = None
        self._layout_sig: tuple | None = None
        self.show_no_file()

    def show_no_file(self) -> None:
        self.last_render = None
        self._artists = None
        self._layout_sig = None
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
               show_legend: bool = True,
               model_v: np.ndarray | None = None,
               residual: np.ndarray | None = None,
               style_name: str | None = None) -> None:
        s = style or get_style("classic")
        actual_show_residual = bool(show_residual)
        # ``model``/``components`` pueden venir muestreados en una rejilla densa
        # (``model_v``) para que la curva de ajuste salga suave aunque el espectro
        # tenga pocos canales. Los datos y los residuos van en la rejilla ``v``.
        mv = model_v if model_v is not None else v
        if residual is None and model is not None and model_v is None:
            residual = y - model
        # Estado para el gráfico Plotly (y otros consumidores) y para alternar.
        self.last_render = {
            "velocity": np.asarray(v, dtype=float).copy(),
            "y_data": np.asarray(y, dtype=float).copy(),
            "model": None if model is None else np.asarray(model, dtype=float).copy(),
            "model_v": np.asarray(mv, dtype=float).copy(),
            "residual": None if residual is None else np.asarray(residual, dtype=float).copy(),
            "components": [
                (int(idx), str(kind), np.asarray(comp, dtype=float).copy())
                for idx, kind, comp in (components or [])
            ],
            "style": dict(s),
            "show_residual": bool(show_residual),
            "show_legend": bool(show_legend),
        }
        n_comp = len(components or [])
        # Firma de la disposición: si no cambia, se reutilizan los ejes/artistas
        # y solo se reescriben los datos (mucho más rápido, sin reconstruir).
        layout_sig = (actual_show_residual, model is not None, n_comp,
                      bool(show_legend), style_name, int(np.asarray(v).size),
                      int(np.asarray(mv).size))
        if (self._artists is not None and self._layout_sig == layout_sig
                and style_name is not None):
            try:
                self._update_fast(v, y, model, components, residual, mv, s,
                                  actual_show_residual)
                return
            except Exception:
                # Ante cualquier discrepancia, se cae a la reconstrucción total.
                self._artists = None
        self.fig.set_facecolor(s["fig_bg"])
        # El espacio de residuos depende SOLO de la opción 'mostrar diferencia',
        # no de que exista un modelo: así un ajuste no altera la disposición.
        self.residual_pref = actual_show_residual
        self.fig.clear()
        self._artists = None
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
        data_line, = self.ax.plot(v, y, ".", color=s["data"],
                                  ms=s.get("data_ms", 3.5),
                                  alpha=s.get("data_alpha", 0.7),
                                  label=tr("plot.legend_data"))
        comp_lines: list = []
        if components:
            palette = s.get("components_palette") or ("#10b981", "#f59e0b", "#8b5cf6")
            for idx, kind, comp in components:
                label = str(kind) if idx <= 0 else f"{tr(f'kind.{kind}', default=kind)} {idx}"
                color = s.get("dist_line", s.get("model", "#dc2626")) if idx <= 0 else palette[(idx - 1) % len(palette)]
                ln, = self.ax.plot(mv, comp, "--",
                                   color=color,
                                   lw=s.get("component_lw", 1.4),
                                   alpha=s.get("component_alpha", 0.85),
                                   label=label)
                comp_lines.append(ln)
        model_line = None
        res_line = None
        res_fill = None
        if model is not None:
            model_line, = self.ax.plot(mv, model, "-", color=s["model"],
                                       lw=s.get("model_lw", 2.2),
                                       label=tr("plot.legend_model"))
            if residual is not None and actual_show_residual and self.ax_res is not None:
                self.ax_res.axhline(0, color=s["res_zero"], lw=0.9, alpha=0.9)
                res_fill = self.ax_res.fill_between(
                    v, residual, 0, color=s["res_fill"],
                    alpha=s.get("res_fill_alpha", 0.22))
                res_line, = self.ax_res.plot(v, residual, "-", color=s["res_line"],
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
        # Memoriza artistas y disposición para los refrescos incrementales.
        self._artists = {
            "data": data_line,
            "comps": comp_lines,
            "model": model_line,
            "res_line": res_line,
            "res_fill": res_fill,
            "res_color": s["res_fill"],
            "res_alpha": s.get("res_fill_alpha", 0.22),
        }
        self._layout_sig = layout_sig

    def _update_fast(self, v, y, model, components, residual, mv, s,
                     actual_show_residual) -> None:
        """Refresco incremental: reescribe los datos sin reconstruir la figura.

        Se usa cuando la disposición (residuos, nº de componentes, leyenda,
        estilo y tamaños) no ha cambiado respecto al render anterior. Evita el
        coste de ``fig.clear`` + recrear ejes + ``tight_layout`` en cada cambio
        de parámetro, que es lo que hace lento el arrastre de sliders.
        """
        a = self._artists
        a["data"].set_data(v, y)
        comps = components or []
        for ln, (_idx, _kind, comp) in zip(a["comps"], comps):
            ln.set_data(mv, comp)
        if a["model"] is not None and model is not None:
            a["model"].set_data(mv, model)
        self.ax.relim()
        self.ax.autoscale_view()
        if (a["res_line"] is not None and residual is not None
                and actual_show_residual and self.ax_res is not None):
            a["res_line"].set_data(v, residual)
            # ``fill_between`` no admite set_data: se sustituye la colección.
            if a["res_fill"] is not None:
                try:
                    a["res_fill"].remove()
                except Exception:
                    pass
            a["res_fill"] = self.ax_res.fill_between(
                v, residual, 0, color=a["res_color"], alpha=a["res_alpha"])
            lim = max(float(np.nanmax(np.abs(residual))) * 1.18, 1e-6)
            self.ax_res.set_ylim(-lim, lim)
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
        self.bmax  = ParamControl(tr("slider.dist_bmax"), 50.0, 0.0, 60.0, 0.1, 2, with_fixed=False)
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

    def set_distribution_variable(self, variable: str) -> None:
        is_quad = variable == "quad"
        if is_quad:
            self.bmin.label.setText(tr("slider.dist_bmin_quad"))
            self.bmax.label.setText(tr("slider.dist_bmax_quad"))
            self.fixed_bhf.label.setText(tr("slider.dist_fixed_bhf_active", default="BHF fijo (T)"))
            self.fixed_bhf.setEnabled(True)
            # En P(ΔEQ) el ΔEQ ES la magnitud distribuida (rango bmin/bmax), así
            # que el ΔEQ global no tiene sentido y se desactiva.
            self.quad.label.setText(
                tr("slider.dist_quad_inactive", default="ΔEQ global (no usado: distribuido)"))
            self.quad.setEnabled(False)
            max_value = DIST_QUAD_RANGE[1]
        else:
            self.bmin.label.setText(tr("slider.dist_bmin_bhf"))
            self.bmax.label.setText(tr("slider.dist_bmax_bhf"))
            self.fixed_bhf.label.setText(tr("slider.dist_fixed_bhf_inactive", default="BHF fijo (no usado en modo BHF)"))
            self.fixed_bhf.setEnabled(False)
            # En P(BHF) el ΔEQ global sí actúa como desplazamiento común.
            self.quad.label.setText(tr("slider.dist_quad"))
            self.quad.setEnabled(True)
            max_value = DIST_BHF_RANGE[1]
        for ctl in (self.bmin, self.bmax):
            ctl.set_range(0.0, max_value, DIST_RANGE_RESOLUTION)

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
            self._cleanup_plotly_temp_files()
        except Exception:
            pass
        super().closeEvent(event)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}  (Qt)")
        # Icono de la app (mismo que la GUI Tk)
        icon_png = ROOT / "assets" / "fitbauer_icon.png"
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
        self.last_distribution_result = None
        self.last_error_source = "covarianza (1σ)"   # actualizado por bootstrap
        self._plotly_temp_files: list[Path] = []
        self._help_dialog: QtWidgets.QDialog | None = None
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
        self._ui_bridge = _UiCallBridge(self)
        self._ui_bridge.call.connect(lambda fn: fn())
        if self._updates_at_startup_enabled():
            QtCore.QTimer.singleShot(2500, lambda: self.check_for_updates(silent=True))
        QtCore.QTimer.singleShot(4000, self._check_requirements_background)

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
        hb = QtWidgets.QHBoxLayout(self.header_box)
        hb.setContentsMargins(12, 8, 12, 8); hb.setSpacing(10)
        self.header_logo = QtWidgets.QLabel()
        _hpix = _logo_pixmap(54)
        if _hpix is not None:
            self.header_logo.setPixmap(_hpix)
            hb.addWidget(self.header_logo, 0, QtCore.Qt.AlignVCenter)
        _header_text = QtWidgets.QVBoxLayout(); _header_text.setSpacing(1)
        self.header_title = QtWidgets.QLabel(APP_NAME)
        self.header_title.setObjectName("AppHeaderTitle")
        self.header_title.setWordWrap(True)
        self._header_sub_labels = [
            QtWidgets.QLabel(tr("main.subtitle")),
            QtWidgets.QLabel(APP_AUTHOR),
            QtWidgets.QLabel(APP_DEPARTMENT),
        ]
        _header_text.addWidget(self.header_title)
        for lbl in self._header_sub_labels:
            lbl.setWordWrap(True)
            _header_text.addWidget(lbl)
        hb.addLayout(_header_text, 1)
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
        self.btn_sim_auto_min = QtWidgets.QPushButton(tr("fit.auto_from_minima"))
        self.btn_sim_ai = QtWidgets.QPushButton(tr("fit.ollama_start"))
        for pos, btn in enumerate((self.btn_sim_fit, self.btn_sim_free_all,
                                   self.btn_sim_auto_min, self.btn_sim_ai)):
            action_grid.addWidget(btn, pos // 2, pos % 2)
        self.btn_sim_fit.clicked.connect(self.on_fit)
        self.btn_sim_free_all.clicked.connect(lambda: self._set_all_fixed(False))
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

        self.plot_tabs = QtWidgets.QTabWidget(center)
        mpl_tab = QtWidgets.QWidget(self.plot_tabs)
        mpl_lay = QtWidgets.QVBoxLayout(mpl_tab)
        mpl_lay.setContentsMargins(0, 0, 0, 0)
        mpl_lay.addWidget(self.toolbar)
        mpl_lay.addWidget(self.canvas, stretch=1)
        self.plot_tabs.addTab(mpl_tab, tr("plot.tab_matplotlib", default="Matplotlib"))

        self.plotly_tab = QtWidgets.QWidget(self.plot_tabs)
        plotly_lay = QtWidgets.QVBoxLayout(self.plotly_tab)
        plotly_lay.setContentsMargins(6, 6, 6, 6)
        plotly_actions = QtWidgets.QHBoxLayout()
        self.btn_plotly_update = QtWidgets.QPushButton(tr("button.update_plotly", default="Actualizar Plotly"))
        self.btn_plotly_update.clicked.connect(self._update_plotly_view)
        self.btn_plotly_minima = QtWidgets.QPushButton(tr("minima.edit_action", default="Editar mínimos"))
        self.btn_plotly_minima.clicked.connect(lambda _checked=False: self.on_edit_minima())
        self.btn_plotly_export = QtWidgets.QPushButton(tr("file.export_plotly_html"))
        self.btn_plotly_export.clicked.connect(self.on_export_plotly_html)
        self.plotly_status = QtWidgets.QLabel(tr("plotly.initial", default="Abre o actualiza el gráfico interactivo."))
        self.plotly_status.setWordWrap(True)
        plotly_actions.addWidget(self.btn_plotly_update)
        plotly_actions.addWidget(self.btn_plotly_minima)
        plotly_actions.addWidget(self.btn_plotly_export)
        plotly_actions.addWidget(self.plotly_status, stretch=1)
        plotly_lay.addLayout(plotly_actions)
        self.plotly_view = None
        self._plotly_available = False
        # Estado de la página incremental: la plantilla con plotly.js se carga
        # una sola vez; los refrescos usan Plotly.react (no recargan el HTML).
        self._plotly_page_ready = False
        self._plotly_loading = False
        self._plotly_pending: str | None = None
        self._plotly_theme: str | None = None
        # Estado de la edición semi-manual de mínimos.
        self._minima_edit_mode = False
        self._minima_entries: list[dict] = []
        self._minima_rows: list[dict] = []
        self._minima_bridge = None
        # La vista web y el editor de mínimos van lado a lado en un splitter.
        self.plotly_split = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self.plotly_tab)
        self.minima_editor = self._build_minima_editor()
        try:
            from PySide6 import QtWebEngineWidgets as _QtWebEngineWidgets
            self.plotly_view = _QtWebEngineWidgets.QWebEngineView(self.plotly_tab)
            self._plotly_available = True
            self.plotly_view.loadFinished.connect(self._on_plotly_loaded)
            self.plotly_split.addWidget(self.plotly_view)
            self.plotly_split.addWidget(self.minima_editor)
            self.plotly_split.setStretchFactor(0, 1)
            self.plotly_split.setStretchFactor(1, 0)
            self.minima_editor.hide()
            plotly_lay.addWidget(self.plotly_split, stretch=1)
            self._setup_minima_webchannel()
        except Exception:
            self.plotly_placeholder = QtWidgets.QLabel(tr("msg.plotly_webengine_missing"))
            self.plotly_placeholder.setAlignment(QtCore.Qt.AlignCenter)
            self.plotly_placeholder.setWordWrap(True)
            plotly_lay.addWidget(self.plotly_placeholder, stretch=1)
        self.plot_tabs.addTab(self.plotly_tab, tr("plot.tab_plotly", default="Plotly interactivo"))
        self._plotly_update_timer = QtCore.QTimer(self)
        self._plotly_update_timer.setSingleShot(True)
        self._plotly_update_timer.setInterval(0)
        self._plotly_update_timer.timeout.connect(self._update_plotly_view)
        self.plot_tabs.currentChanged.connect(lambda _idx: self._schedule_plotly_update() if self._is_plotly_tab_active() else None)

        cv.addWidget(self._center_top_widget)
        cv.addWidget(self.plot_tabs, stretch=1)
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
        self.act_export_plotly = QtGui.QAction(tr("file.export_plotly_html"), self)
        self.act_export_plotly.triggered.connect(self.on_export_plotly_html)
        self.act_export_plotly.setEnabled(False)
        file_menu.addAction(self.act_export_plotly)
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
        self.act_edit_minima = QtGui.QAction(
            tr("minima.edit_action", default="Editar mínimos (semi-manual)…"), self)
        self.act_edit_minima.triggered.connect(lambda _checked=False: self.on_edit_minima())
        self.act_edit_minima.setEnabled(False)
        fit_menu.addAction(self.act_edit_minima)
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
        self.act_open_plotly = QtGui.QAction(tr("view.open_plotly"), self)
        self.act_open_plotly.triggered.connect(self.on_open_plotly)
        self.act_open_plotly.setEnabled(False)
        view_menu.addAction(self.act_open_plotly)
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
        # Etiquetas y límites según variable distribuida. P(ΔEQ) usa un BHF fijo
        # independiente y restringe el rango de distribución a 0–7 mm/s.
        if is_dist:
            self.dist_panel.set_distribution_variable("quad" if is_deq else "bhf")
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

    def _active_bhf_controls(self) -> list[ParamControl]:
        """Controles BHF que participan en el ajuste de Vmax.

        Igual que en la GUI Tk, el ajuste de velocidad con patrón solo exige
        fijar los BHF de los sextetes activos. Los dobletes/singletes activos
        no tienen patrón hiperfino que fijar para este modo.
        """
        controls: list[ParamControl] = []
        for cp in getattr(self, "components_panels", []):
            if cp.enabled.isChecked() and cp.kind == "Sextete":
                ctl = cp.params.get("bhf")
                if ctl is not None:
                    controls.append(ctl)
        return controls

    def _on_fit_velocity_toggled(self, checked: bool) -> None:
        """Al activar 'Ajustar Vmax', fija BHF y muestra el aviso de Tk."""
        if not checked:
            return
        for ctl in self._active_bhf_controls():
            ctl.set_fixed(True)
        QtWidgets.QMessageBox.information(
            self,
            tr("msg.fit_velocity_title"),
            tr("msg.fit_velocity_info"),
        )

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
            for name, ctl in cp.params.items():
                # int3 (intensidad de referencia = 1) permanece siempre fija,
                # igual que en Tk; no se libera con "Liberar todos".
                if name == "int3":
                    ctl.set_fixed(True)
                    continue
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
        vmax = self.calib.vmax.value()
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

    def texture_derived(self, cp: "ComponentPanel") -> dict | None:
        """Magnitudes derivadas del parámetro de textura t = sin²θ.

        Para un sextete en modo textura, donde I₂/I₃ = 4t/(2-t) se obtienen:
        θ = arcsin(√t) (ángulo entre el campo hiperfino y el rayo γ),
        R₂₃ = I₂/I₃ = 4t/(2-t),
        S = ⟨P₂(cosθ)⟩ = 1 − 3t/2 (orden tipo Hermans: +1 alineado al γ,
        0 isótropo, −½ perpendicular). Devuelve también las σ propagadas.
        """
        if cp.kind != "Sextete" or cp.intensity_mode != "texture":
            return None
        import math
        t = float(cp.params["texture"].value())
        tc = min(max(t, 0.0), 1.0)
        denom = max(2.0 - tc, 1e-9)
        theta_deg = math.degrees(math.asin(math.sqrt(tc)))
        r23 = 4.0 * tc / denom
        s_orient = 1.0 - 1.5 * tc
        sigma_t = None
        if self.last_fit_result is not None:
            sigma_t = self.last_fit_result.errors.get(f"s{cp.idx}_texture")
        sigma_theta_deg = sigma_r23 = sigma_s = None
        if sigma_t is not None and sigma_t > 0:
            if 1e-6 < tc < 1.0 - 1e-6:
                sigma_theta_deg = math.degrees(
                    sigma_t / (2.0 * math.sqrt(tc * (1.0 - tc)))
                )
            sigma_r23 = 8.0 / (denom * denom) * sigma_t
            sigma_s = 1.5 * sigma_t
        return {
            "t": t, "theta_deg": theta_deg, "r23": r23, "s": s_orient,
            "sigma_t": sigma_t, "sigma_theta_deg": sigma_theta_deg,
            "sigma_r23": sigma_r23, "sigma_s": sigma_s,
        }

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
            derived = self.texture_derived(cp)
            if derived is not None:
                def _fmt_err(v: float | None) -> str:
                    return f" ± {v:.3g}" if v is not None and v > 0 else ""
                lines.append(tr(
                    "info.texture_derived",
                    t=f"{derived['t']:.4g}",
                    theta=f"{derived['theta_deg']:.4g}",
                    theta_err=_fmt_err(derived["sigma_theta_deg"]),
                    r23=f"{derived['r23']:.4g}",
                    r23_err=_fmt_err(derived["sigma_r23"]),
                    s=f"{derived['s']:.4g}",
                    s_err=_fmt_err(derived["sigma_s"]),
                ))
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
    def _model_state(self) -> ModelState:
        """Vuelca el estado de los widgets en un ``core.session.ModelState``.

        Fuente única del estado del modelo: a partir de aquí, la construcción del
        ``FitState`` y el ``model_state`` de la sesión se delegan en el
        controlador headless (``core.session``), sin lógica duplicada en la GUI.
        """
        ms = ModelState.defaults(n_components=max(1, len(self.components_panels)))
        ms.vars.update({
            "vmax": self.calib.vmax.value(),
            "center": self.calib.center.value(),
            "baseline": self.calib.baseline.value(),
            "slope": self.calib.slope.value(),
            "voigt_sigma": self.calib.voigt_sigma.value(),
            "sat_scale": self.calib.sat_scale.value(),
        })
        ms.fixed.update({
            "vmax": True, "center": True,
            "baseline": self.calib.baseline.is_fixed(),
            "slope": self.calib.slope.is_fixed(),
            "sat_scale": self.calib.sat_scale.is_fixed(),
        })
        for cp in self.components_panels:
            ms.vars.update(cp.values_dict())
            ms.fixed.update(cp.fixed_dict())
            ms.sextet_enabled[cp.idx] = cp.enabled.isChecked()
            ms.component_kind[cp.idx] = cp.kind
            ms.intensity_mode[cp.idx] = cp.intensity_mode
            ms.quad_treatment[cp.idx] = cp.quad_treatment
        ms.line_profile = self.calib.line_profile
        ms.likelihood = self.likelihood
        ms.robust_loss = self.robust_loss
        ms.absorber_model = self.absorber_model
        ms.propagate_calib = self.propagate_calib
        ms.global_opt = self.global_opt
        ms.fit_velocity = self.calib.fit_velocity.isChecked()
        ms.fit_center = self.calib.fit_center.isChecked()
        ms.fit_sigma = self.calib.fit_sigma.isChecked()
        ms.constraints = list(self.constraints)
        return ms

    def _build_state(self) -> FitState | None:
        if self.file.velocity is None or self.file.y_data is None:
            return None
        return self._model_state().build_fit_state(
            velocity=self.file.velocity, y_data=self.file.y_data,
            sigma_data=self.file.sigma, counts=self.file.counts,
            norm_factor=self.file.norm_factor)

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
        self.act_edit_minima.setEnabled(True)
        self.act_auto_fit.setEnabled(True)
        self.act_ai.setEnabled(True)
        self.act_upload_session.setEnabled(True)
        self.act_use_as_calib.setEnabled(True)
        self.act_profile.setEnabled(True)
        self.act_find_center.setEnabled(True)
        self.act_save_fit.setEnabled(True)
        self.act_export_report.setEnabled(True)
        self.act_export_plotly.setEnabled(True)
        self.act_open_plotly.setEnabled(True)
        self.act_bootstrap.setEnabled(True)
        self.act_lcurve.setEnabled(True)
        self._set_quick_action_buttons_enabled(True)
        self._add_recent(path)
        self.statusBar().showMessage(
            f"{path.name} · {counts.size} canales · centro={center:.3f}")
        self.last_fit_result = None
        self.last_distribution_result = None
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
            self.canvas.render(v, y, style=style, style_name=self.plot_style_name,
                               show_residual=show_res, show_legend=show_leg)
            self._update_info_panel()
            self._schedule_plotly_update()
            return
        try:
            model = model_from_values(v, state.values, state.components, state.constraints,
                                      absorber_model=state.absorber_model)
            # Curva densa para que el ajuste no salga con pocos puntos.
            mv = self._model_grid(v)
            if mv is not None:
                model_dense = model_from_values(mv, state.values, state.components,
                                                state.constraints,
                                                absorber_model=state.absorber_model)
            else:
                mv, model_dense = None, model
        except Exception:
            self.canvas.render(v, y, style=style, style_name=self.plot_style_name,
                               show_residual=show_res, show_legend=show_leg)
            self._update_info_panel()
            self._schedule_plotly_update()
            return
        residual = y - model
        # Solo dibujar componentes individuales si hay más de uno activo.
        comps = []
        enabled = [c for c in state.components if c.enabled]
        if len(enabled) >= 2:
            grid = mv if mv is not None else v
            for comp in enabled:
                only_this = model_from_values(grid, state.values, [comp], state.constraints,
                                              absorber_model=state.absorber_model)
                comps.append((comp.idx, comp.kind, only_this))
        self.canvas.render(v, y, model=model_dense, components=comps, style=style,
                           show_residual=show_res, show_legend=show_leg,
                           model_v=mv, residual=residual, style_name=self.plot_style_name)
        self._update_info_panel()
        self._schedule_plotly_update()

    def _model_grid(self, v: np.ndarray) -> np.ndarray | None:
        """Rejilla densa para dibujar curvas de ajuste suaves.

        El modelo se evalúa en muchos más puntos que los canales del espectro,
        de modo que la línea de ajuste no se vea quebrada cuando hay pocos datos.
        """
        if v is None or v.size < 2:
            return None
        n = int(np.clip(v.size * 6, 1200, 6000))
        if n <= v.size:
            return None
        return np.linspace(float(np.min(v)), float(np.max(v)), n)

    def _current_plotly_figure(self):
        """Construye una figura Plotly a partir de lo último dibujado."""
        render = getattr(self.canvas, "last_render", None)
        if not render:
            raise RuntimeError(tr("msg.plotly_no_plot"))
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except Exception as exc:
            raise RuntimeError(tr("msg.plotly_missing")) from exc

        v = render["velocity"]
        y = render["y_data"]
        model = render.get("model")
        # Rejilla densa del modelo/componentes (curva de ajuste suave). Si no
        # está disponible, se cae a la rejilla de los datos.
        mv = render.get("model_v")
        if mv is None:
            mv = v
        components = render.get("components") or []
        style = render.get("style") or get_style(self.plot_style_name)
        show_residual = bool(render.get("show_residual", True)) and model is not None
        residual = render.get("residual")
        if residual is None and model is not None:
            residual = y - model
        dist_result = self.last_distribution_result if getattr(self, "is_distribution_mode", False) else None
        show_distribution = bool(
            dist_result is not None
            and hasattr(dist_result, "bhf_centers")
            and hasattr(dist_result, "probability")
        )
        rows = 1 + (1 if show_residual else 0) + (1 if show_distribution else 0)
        row_heights = [0.62]
        if show_residual:
            row_heights.append(0.18)
        if show_distribution:
            row_heights.append(0.20)
        fig = make_subplots(
            rows=rows, cols=1, shared_xaxes=False,
            row_heights=row_heights, vertical_spacing=0.055,
        )
        # WebGL (scattergl) para que muchos puntos se dibujen con fluidez.
        fig.add_trace(
            go.Scattergl(
                x=v, y=y, mode="markers", name=tr("plot.legend_data"),
                marker=dict(color=style.get("data", "#2563eb"), size=6),
                hovertemplate="v=%{x:.5g}<br>y=%{y:.6g}<extra></extra>",
            ),
            row=1, col=1,
        )
        palette = style.get("components_palette") or ("#10b981", "#f59e0b", "#8b5cf6")
        for idx, kind, comp in components:
            param_txt = str(kind) if idx <= 0 else self._plotly_component_param_text(idx)
            comp_name = str(kind) if idx <= 0 else f"{tr(f'kind.{kind}', default=kind)} {idx}"
            comp_color = style.get("dist_line", style.get("model", "#dc2626")) if idx <= 0 else palette[(idx - 1) % len(palette)]
            fig.add_trace(
                go.Scattergl(
                    x=mv, y=comp, mode="lines",
                    name=comp_name,
                    line=dict(color=comp_color, width=1.5, dash="dash"),
                    hovertemplate=(
                        f"{html.escape(param_txt)}<br>"
                        "v=%{x:.5g}<br>y=%{y:.6g}<extra></extra>"
                    ),
                ),
                row=1, col=1,
            )
        if model is not None:
            fig.add_trace(
                go.Scattergl(
                    x=mv, y=model, mode="lines", name=tr("plot.legend_model"),
                    line=dict(color=style.get("model", "#dc2626"), width=2.4),
                    hovertemplate="v=%{x:.5g}<br>modelo=%{y:.6g}<extra></extra>",
                ),
                row=1, col=1,
            )
            if show_residual and residual is not None:
                res_row = 2
                fig.add_trace(
                    go.Scattergl(
                        x=v, y=residual, mode="lines", name=tr("plot.residual_ylabel"),
                        line=dict(color=style.get("res_line", "#7c3aed"), width=1.2),
                        fill="tozeroy", fillcolor="rgba(124,58,237,0.18)",
                        hovertemplate="v=%{x:.5g}<br>res=%{y:.6g}<extra></extra>",
                    ),
                    row=res_row, col=1,
                )
                fig.add_hline(y=0, line_width=1, line_color=style.get("res_zero", "#64748b"), row=res_row, col=1)
                fig.update_yaxes(title_text=tr("plot.residual_ylabel"), row=res_row, col=1)
                fig.update_xaxes(title_text=tr("plot.velocity_xlabel"), row=res_row, col=1)
        if show_distribution:
            dist_row = rows
            xdist = np.asarray(dist_result.bhf_centers, dtype=float)
            pdist = np.asarray(dist_result.probability, dtype=float)
            dist_name = "P(ΔEQ)" if self.dist_variable == "quad" else "P(BHF)"
            fig.add_trace(
                go.Scatter(
                    x=xdist, y=pdist, mode="lines", name=dist_name,
                    line=dict(color="#2563eb", width=2.2),
                    fill="tozeroy", fillcolor="rgba(37,99,235,0.22)",
                    hovertemplate="x=%{x:.5g}<br>P=%{y:.6g}<extra></extra>",
                ),
                row=dist_row, col=1,
            )
            xlabel = tr("plot.distribution_xlabel_deq") if self.dist_variable == "quad" else tr("plot.distribution_xlabel_bhf")
            fig.update_xaxes(title_text=xlabel, row=dist_row, col=1)
            fig.update_yaxes(title_text=dist_name, row=dist_row, col=1)
        if not show_residual:
            fig.update_xaxes(title_text=tr("plot.velocity_xlabel"), row=1, col=1)
        template = "plotly_dark" if self.plot_style_name == "dark" or self.color_theme == "dark" else "plotly_white"
        subtitle = self._plotly_subtitle()
        title = tr("plot.title_discrete") + (f"<br><sup>{html.escape(subtitle)}</sup>" if subtitle else "")
        fig.update_layout(
            template=template,
            title=title,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
            margin=dict(l=60, r=24, t=86, b=56),
        )
        fig.update_yaxes(title_text=tr("plot.transmission_ylabel"), row=1, col=1)
        if getattr(self, "_minima_edit_mode", False) and self._minima_entries:
            self._add_minima_overlay(fig, go, v, y)
        return fig

    def _add_minima_overlay(self, fig, go, v, y) -> None:
        """Dibuja los mínimos detectados como marcadores clicables en Plotly.

        Los incluidos van resaltados; los excluidos, atenuados. El número de
        contribuciones (>1) se muestra como una etiqueta ``×n`` sobre el marcador.
        ``customdata`` lleva el índice de cada mínimo para identificarlo al clicar.
        """
        n = int(np.asarray(y).size)
        for included in (False, True):
            xs, ys, texts, custom = [], [], [], []
            for k, e in enumerate(self._minima_entries):
                if bool(e["included"]) is not included:
                    continue
                ch = int(e["i"])
                yv = float(y[ch]) if 0 <= ch < n else float(np.interp(e["pos"], v, y))
                xs.append(float(e["pos"]))
                ys.append(yv)
                texts.append(f"×{int(e['count'])}" if int(e["count"]) > 1 else "")
                custom.append(k)
            if not xs:
                continue
            if included:
                marker = dict(color="#dc2626", size=13, symbol="circle",
                              line=dict(color="#ffffff", width=1.5))
                name = tr("minima.included", default="Mínimos (incluidos)")
            else:
                marker = dict(color="rgba(148,163,184,0.55)", size=11,
                              symbol="circle-open", line=dict(color="#94a3b8", width=1.5))
                name = tr("minima.excluded", default="Mínimos (excluidos)")
            fig.add_trace(
                go.Scatter(
                    x=xs, y=ys, mode="markers+text", name=name,
                    marker=marker, customdata=custom,
                    text=texts, textposition="top center",
                    textfont=dict(color="#dc2626", size=12),
                    hovertemplate="v=%{x:.4f}<extra></extra>",
                ),
                row=1, col=1,
            )

    def _plotly_subtitle(self) -> str:
        parts: list[str] = []
        if self.file.path:
            parts.append(self.file.path.name)
        if self.last_fit_result is not None:
            stats = self.last_fit_result.stats
            if "red_chi2" in stats:
                parts.append(f"χ²red={float(stats['red_chi2']):.5g}")
            if "aic" in stats:
                parts.append(f"AIC={float(stats['aic']):.5g}")
            if "bic" in stats:
                parts.append(f"BIC={float(stats['bic']):.5g}")
        return " · ".join(parts)

    def _plotly_component_param_text(self, idx: int) -> str:
        if idx < 1 or idx > len(self.components_panels):
            return f"Comp. {idx}"
        cp = self.components_panels[idx - 1]
        fields = [f"Comp. {idx} ({tr(f'kind.{cp.kind}', default=cp.kind)})"]
        for name, label in (("delta", "δ"), ("quad", "ΔEQ"), ("bhf", "BHF"), ("gamma1", "Γ"), ("depth", "prof")):
            ctl = cp.params.get(name)
            if ctl is not None:
                fields.append(f"{label}={ctl.value():.5g}")
        return " · ".join(fields)

    def _plotly_metadata_html(self) -> str:
        rows: list[tuple[str, str]] = [
            (tr("report.program", default="Programa"), f"{APP_NAME} v{APP_VERSION} (Qt)"),
        ]
        if self.file.path:
            rows.append((tr("report.file", default="Fichero"), self.file.path.name))
        if self.file.velocity is not None:
            rows.append(("Canales doblados", str(self.file.velocity.size)))
        rows.append(("Modo", "P(ΔEQ)" if self.mode_combo.currentIndex() == 2 else ("P(BHF)" if self.mode_combo.currentIndex() == 1 else "Discreto")))
        rows.append(("Perfil", self.calib.line_profile))
        rows.append(("Verosimilitud", self.likelihood))
        rows.append(("Pérdida", self.robust_loss))
        if self.last_fit_result is not None:
            for key in ("chi2", "red_chi2", "aic", "bic"):
                if key in self.last_fit_result.stats:
                    rows.append((key, f"{float(self.last_fit_result.stats[key]):.6g}"))
        comp_lines = [self._plotly_component_param_text(cp.idx) for cp in self.components_panels if cp.enabled.isChecked()]
        table = "".join(
            f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
            for k, v in rows
        )
        comps = "".join(f"<li>{html.escape(line)}</li>" for line in comp_lines)
        return (
            "<section class='metadata'>"
            f"<h2>{html.escape(tr('plotly.metadata_title', default='Metadatos del ajuste'))}</h2>"
            f"<table>{table}</table>"
            f"<h3>{html.escape(tr('plotly.components_title', default='Componentes activos'))}</h3>"
            f"<ul>{comps}</ul>"
            "</section>"
        )

    def _plotly_html_document(self) -> str:
        fig = self._current_plotly_figure()
        body = fig.to_html(
            include_plotlyjs=True,
            full_html=False,
            config={"responsive": True, "displaylogo": False, "toImageButtonOptions": {"format": "png", "scale": 2}},
        )
        bg = "#111827" if self.color_theme == "dark" else "#ffffff"
        fg = "#e5e7eb" if self.color_theme == "dark" else "#111827"
        border = "#374151" if self.color_theme == "dark" else "#d1d5db"
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{html.escape(tr('plotly.title'))}</title>"
            "<style>"
            f"body{{margin:0;background:{bg};color:{fg};font-family:system-ui,Segoe UI,sans-serif;}}"
            "main{padding:10px 14px 24px 14px;}"
            f".metadata{{margin:12px 8px 4px 8px;padding:12px;border:1px solid {border};border-radius:10px;}}"
            ".metadata h2,.metadata h3{margin:0.2rem 0 0.5rem 0;}"
            ".metadata table{border-collapse:collapse;margin-bottom:0.75rem;}"
            ".metadata th{text-align:left;padding:3px 12px 3px 0;}"
            ".metadata td{padding:3px 0;}"
            "</style></head><body><main>"
            f"{body}"
            "</main></body></html>"
        )

    def _cleanup_plotly_temp_files(self) -> None:
        for path in list(getattr(self, "_plotly_temp_files", [])):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        self._plotly_temp_files = []

    def _load_plotly_html(self, html_text: str) -> None:
        """Carga HTML de Plotly mediante fichero temporal, no con setHtml().

        QWebEngineView.setHtml() convierte el contenido en una URL de datos y
        Qt WebEngine tiene un límite práctico de tamaño. Como plotly.js embebido
        mide varios MB, setHtml() puede terminar en una página en blanco (sin
        datos ni ejes). Cargar un fichero local evita ese límite.
        """
        if self.plotly_view is None:
            return
        tmp_dir = CONFIG_DIR / "plotly"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="plotly_", suffix=".html", dir=str(tmp_dir))
        path = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(html_text)
        self._plotly_temp_files.append(path)
        # Mantén solo unos pocos ficheros vivos para no borrar el que se acaba
        # de pedir al motor web, pero evita acumular muchos en sesiones largas.
        while len(self._plotly_temp_files) > 6:
            old = self._plotly_temp_files.pop(0)
            try:
                old.unlink(missing_ok=True)
            except Exception:
                pass
        self.plotly_view.load(QtCore.QUrl.fromLocalFile(str(path)))

    def _is_plotly_tab_active(self) -> bool:
        return hasattr(self, "plot_tabs") and self.plot_tabs.currentWidget() is getattr(self, "plotly_tab", None)

    def _schedule_plotly_update(self) -> None:
        if self._is_plotly_tab_active() and getattr(self, "_plotly_available", False):
            self._plotly_update_timer.start()

    def _plotly_page_template(self, theme: str) -> str:
        """HTML que se carga UNA sola vez: plotly.js + función de refresco.

        Los datos se inyectan luego con ``window.__render`` (Plotly.react), de
        modo que cada actualización no recarga la página ni vuelve a parsear
        plotly.js — solo redibuja de forma incremental lo que cambia.
        """
        import plotly.offline as _poff
        plotlyjs = _poff.get_plotlyjs()
        bg = "#111827" if theme == "dark" else "#ffffff"
        fg = "#e5e7eb" if theme == "dark" else "#111827"
        border = "#374151" if theme == "dark" else "#d1d5db"
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{html.escape(tr('plotly.title'))}</title>"
            "<style>"
            "html,body{height:100%;}"
            f"body{{margin:0;background:{bg};color:{fg};font-family:system-ui,Segoe UI,sans-serif;}}"
            "main{padding:4px 8px;height:100%;box-sizing:border-box;display:flex;flex-direction:column;}"
            "#plot{width:100%;flex:1 1 auto;min-height:0;}"
            f".metadata{{margin:12px 8px 4px 8px;padding:12px;border:1px solid {border};border-radius:10px;}}"
            ".metadata h2,.metadata h3{margin:0.2rem 0 0.5rem 0;}"
            ".metadata table{border-collapse:collapse;margin-bottom:0.75rem;}"
            ".metadata th{text-align:left;padding:3px 12px 3px 0;}"
            ".metadata td{padding:3px 0;}"
            "</style>"
            "<script src='qrc:///qtwebchannel/qwebchannel.js'></script>"
            "<script>" + plotlyjs + "</script></head>"
            "<body><main><div id='plot'></div></main><script>"
            "var CFG={responsive:true,displaylogo:false,"
            "toImageButtonOptions:{format:'png',scale:2}};"
            "window.__bridge=null;"
            "if(typeof QWebChannel!=='undefined'&&typeof qt!=='undefined'){"
            "new QWebChannel(qt.webChannelTransport,function(ch){"
            "window.__bridge=ch.objects.minima;});}"
            "window.__clickBound=false;"
            "window.__render=function(fig,meta){"
            "var gd=document.getElementById('plot');"
            "Plotly.react(gd,fig.data,fig.layout,CFG);"
            "if(!window.__clickBound){window.__clickBound=true;"
            "gd.on('plotly_click',function(ev){"
            "if(!ev||!ev.points||!ev.points.length)return;"
            "var p=ev.points[0];"
            "if(!window.__bridge)return;"
            "if(p.customdata!==undefined&&p.customdata!==null){"
            "window.__bridge.toggle(p.customdata);return;}"
            "if(p.x!==undefined&&p.x!==null){window.__bridge.add(Number(p.x));}});}"
            "};"
            "</script></body></html>"
        )

    def _on_plotly_loaded(self, ok: bool) -> None:
        self._plotly_loading = False
        self._plotly_page_ready = bool(ok)
        # Al terminar de cargar la plantilla, vuelca el último estado pendiente.
        if ok and self._plotly_pending and self.plotly_view is not None:
            self.plotly_view.page().runJavaScript(self._plotly_pending)
            self._plotly_pending = None

    def _update_plotly_view(self) -> None:
        if not getattr(self, "_plotly_available", False) or self.plotly_view is None:
            if hasattr(self, "plotly_status"):
                self.plotly_status.setText(tr("msg.plotly_webengine_missing"))
            return
        try:
            import plotly.io as _pio
            fig = self._current_plotly_figure()
            fig_json = _pio.to_json(fig)
            payload = f"window.__render({fig_json},null);"
            theme = "dark" if self.color_theme == "dark" else "light"
            if self._plotly_loading and self._plotly_theme == theme:
                # La plantilla aún se está cargando: solo se actualiza el estado
                # pendiente (sin recargar plotly.js otra vez).
                self._plotly_pending = payload
            elif not self._plotly_page_ready or self._plotly_theme != theme:
                # Primera vez (o cambio de tema): carga la plantilla y deja el
                # estado pendiente para aplicarlo cuando termine la carga.
                self._plotly_theme = theme
                self._plotly_page_ready = False
                self._plotly_loading = True
                self._plotly_pending = payload
                self._load_plotly_html(self._plotly_page_template(theme))
            else:
                # Refresco incremental: solo se envían los datos nuevos.
                self.plotly_view.page().runJavaScript(payload)
            if hasattr(self, "plotly_status"):
                self.plotly_status.setText(tr("status.plotly_updated", default="Plotly actualizado."))
        except Exception as exc:
            # Fuerza recargar la plantilla en el próximo intento.
            self._plotly_page_ready = False
            self._plotly_loading = False
            self._plotly_theme = None
            self._plotly_pending = None
            if hasattr(self, "plotly_status"):
                self.plotly_status.setText(str(exc))

    # ── Edición semi-manual de mínimos ──────────────────────────────────
    def _build_minima_editor(self) -> QtWidgets.QWidget:
        """Panel lateral con la lista de mínimos detectados (editable)."""
        box = QtWidgets.QGroupBox(tr("minima.editor_title", default="Mínimos detectados"))
        box.setMinimumWidth(240)
        lay = QtWidgets.QVBoxLayout(box)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        hint = QtWidgets.QLabel(tr(
            "minima.editor_hint",
            default="Marca/desmarca los mínimos a usar e indica cuántas "
                    "contribuciones tiene cada uno. En Plotly, clic sobre el "
                    "espectro añade un mínimo y clic sobre/cerca de un marcador "
                    "lo activa o desactiva."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#64748b;font-size:11px;")
        lay.addWidget(hint)

        self.btn_minima_detect = QtWidgets.QPushButton(
            tr("minima.redetect", default="Volver a detectar"))
        self.btn_minima_detect.clicked.connect(lambda _=False: self.on_edit_minima(redetect=True))
        lay.addWidget(self.btn_minima_detect)

        self._minima_list_container = QtWidgets.QWidget()
        self._minima_list_layout = QtWidgets.QVBoxLayout(self._minima_list_container)
        self._minima_list_layout.setContentsMargins(0, 0, 0, 0)
        self._minima_list_layout.setSpacing(2)
        self._minima_list_layout.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._minima_list_container)
        lay.addWidget(scroll, stretch=1)

        self.minima_count_label = QtWidgets.QLabel("")
        self.minima_count_label.setStyleSheet("font-size:11px;")
        lay.addWidget(self.minima_count_label)

        btns = QtWidgets.QHBoxLayout()
        self.btn_minima_propose = QtWidgets.QPushButton(
            tr("minima.propose", default="Proponer ajuste"))
        self.btn_minima_propose.clicked.connect(lambda _=False: self.on_propose_from_minima())
        self.btn_minima_done = QtWidgets.QPushButton(
            tr("minima.done", default="Cerrar edición"))
        self.btn_minima_done.clicked.connect(lambda _=False: self._exit_minima_edit())
        btns.addWidget(self.btn_minima_propose)
        btns.addWidget(self.btn_minima_done)
        lay.addLayout(btns)
        return box

    def _setup_minima_webchannel(self) -> None:
        """Conecta el puente JS↔Python para clicar marcadores en Plotly."""
        if self.plotly_view is None:
            return
        try:
            from PySide6.QtWebChannel import QWebChannel
            self._minima_bridge = MinimaBridge()
            self._minima_bridge.toggled.connect(self._on_minima_marker_clicked)
            self._minima_bridge.added.connect(self._on_minima_plot_clicked)
            channel = QWebChannel(self.plotly_view.page())
            channel.registerObject("minima", self._minima_bridge)
            self.plotly_view.page().setWebChannel(channel)
        except Exception:
            # Sin QWebChannel la lista lateral sigue siendo plenamente funcional.
            self._minima_bridge = None

    def on_edit_minima(self, redetect: bool = True) -> None:
        """Entra en el modo de edición semi-manual de mínimos."""
        if self.file.velocity is None or self.file.y_data is None:
            QtWidgets.QMessageBox.information(
                self, tr("minima.editor_title", default="Mínimos detectados"),
                tr("msg.no_file", default="Carga primero un espectro."))
            return
        if not getattr(self, "_plotly_available", False):
            # Sin la vista Plotly interactiva no hay edición visual: se recurre
            # a la inicialización automática clásica.
            self.on_init_from_minima(show_message=True)
            return
        if redetect or not self._minima_entries:
            peaks, baseline, slope = self.detect_absorption_minima()
            self._minima_baseline = baseline
            self._minima_slope = slope
            self._minima_entries = [
                {"i": int(p["i"]), "pos": float(p["pos"]), "depth": float(p["depth"]),
                 "width": float(p["width"]), "smooth_depth": float(p.get("smooth_depth", p["depth"])),
                 "included": True, "count": 1}
                for p in peaks
            ]
        if not self._minima_entries:
            QtWidgets.QMessageBox.information(
                self, tr("minima.editor_title", default="Mínimos detectados"),
                tr("msg.auto_minima_none", default="No se detectaron mínimos."))
            return
        self._minima_edit_mode = True
        self._populate_minima_list()
        self.minima_editor.show()
        if hasattr(self, "plot_tabs"):
            self.plot_tabs.setCurrentWidget(self.plotly_tab)
        self._update_plotly_view()

    def _populate_minima_list(self) -> None:
        """Reconstruye las filas de la lista a partir de ``_minima_entries``."""
        # Limpia las filas previas (deja el stretch final).
        while self._minima_list_layout.count() > 1:
            item = self._minima_list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._minima_rows = []
        for k, e in enumerate(self._minima_entries):
            row = QtWidgets.QWidget()
            rl = QtWidgets.QHBoxLayout(row)
            rl.setContentsMargins(2, 0, 2, 0)
            rl.setSpacing(6)
            chk = QtWidgets.QCheckBox(f"v={e['pos']:+.3f}")
            chk.setChecked(bool(e["included"]))
            chk.setToolTip(tr("minima.include_tip", default="Usar este mínimo en la propuesta"))
            chk.toggled.connect(lambda state, idx=k: self._on_minima_row_changed(idx, included=state))
            spin = QtWidgets.QSpinBox()
            spin.setRange(1, 4)
            spin.setValue(int(e["count"]))
            spin.setPrefix("×")
            spin.setToolTip(tr("minima.count_tip", default="Nº de contribuciones bajo este mínimo"))
            spin.valueChanged.connect(lambda val, idx=k: self._on_minima_row_changed(idx, count=val))
            depth = QtWidgets.QLabel(f"{e['depth']*100:.1f}%")
            depth.setStyleSheet("color:#64748b;font-size:11px;")
            rl.addWidget(chk, stretch=1)
            rl.addWidget(depth)
            rl.addWidget(spin)
            self._minima_list_layout.insertWidget(self._minima_list_layout.count() - 1, row)
            self._minima_rows.append({"check": chk, "spin": spin})
        self._update_minima_count_label()

    def _on_minima_row_changed(self, idx: int, included: bool | None = None,
                               count: int | None = None) -> None:
        if idx < 0 or idx >= len(self._minima_entries):
            return
        if included is not None:
            self._minima_entries[idx]["included"] = bool(included)
        if count is not None:
            self._minima_entries[idx]["count"] = int(count)
        self._update_minima_count_label()
        self._update_plotly_view()

    def _on_minima_marker_clicked(self, idx: int) -> None:
        """Clic en un marcador del gráfico: alterna incluir/excluir y sincroniza."""
        if idx < 0 or idx >= len(self._minima_entries):
            return
        new_state = not self._minima_entries[idx]["included"]
        self._minima_entries[idx]["included"] = new_state
        if idx < len(self._minima_rows):
            chk = self._minima_rows[idx]["check"]
            chk.blockSignals(True)
            chk.setChecked(new_state)
            chk.blockSignals(False)
        self._update_minima_count_label()
        self._update_plotly_view()

    def _on_minima_plot_clicked(self, x: float) -> None:
        """Clic sobre el gráfico en modo edición: añade un mínimo manual."""
        if not getattr(self, "_minima_edit_mode", False):
            return
        if self.file.velocity is None or self.file.y_data is None:
            return
        v = np.asarray(self.file.velocity, dtype=float)
        y = np.asarray(self.file.y_data, dtype=float)
        if v.size == 0 or y.size == 0:
            return
        idx = int(np.argmin(np.abs(v - float(x))))
        # Si se clica sobre/cerca de un mínimo existente, alterna incluir/excluir
        # en vez de crear un duplicado. Así basta un clic para desactivarlo.
        if v.size > 1:
            dv = float(np.nanmedian(np.abs(np.diff(np.sort(v)))))
        else:
            dv = 0.05
        tol = max(1.5 * abs(dv), 0.05)
        if self._minima_entries:
            distances = [abs(float(e["pos"]) - float(x)) for e in self._minima_entries]
            nearest = int(np.argmin(distances))
            if distances[nearest] <= tol or abs(int(self._minima_entries[nearest]["i"]) - idx) <= 1:
                self._on_minima_marker_clicked(nearest)
                return
        baseline = float(getattr(self, "_minima_baseline", self.calib.baseline.value()))
        slope = float(getattr(self, "_minima_slope", self.calib.slope.value()))
        depth = max(0.0, baseline + slope * float(v[idx]) - float(y[idx]))
        self._minima_entries.append({
            "i": idx,
            "pos": float(v[idx]),
            "depth": depth,
            "width": 0.2,
            "smooth_depth": depth,
            "included": True,
            "count": 1,
        })
        self._minima_entries.sort(key=lambda e: float(e["pos"]))
        self._populate_minima_list()
        self._update_plotly_view()

    def _update_minima_count_label(self) -> None:
        if not hasattr(self, "minima_count_label"):
            return
        n_inc = sum(1 for e in self._minima_entries if e["included"])
        n_contrib = sum(int(e["count"]) for e in self._minima_entries if e["included"])
        self.minima_count_label.setText(tr(
            "minima.count_summary",
            default="{inc}/{tot} mínimos · {contrib} contribuciones",
            inc=n_inc, tot=len(self._minima_entries), contrib=n_contrib))

    def _exit_minima_edit(self) -> None:
        self._minima_edit_mode = False
        if hasattr(self, "minima_editor"):
            self.minima_editor.hide()
        self._update_plotly_view()

    def on_propose_from_minima(self) -> None:
        """Construye la propuesta de componentes a partir de los mínimos curados."""
        included = [e for e in self._minima_entries if e["included"]]
        if not included:
            QtWidgets.QMessageBox.information(
                self, tr("minima.propose", default="Proponer ajuste"),
                tr("minima.none_selected", default="Marca al menos un mínimo."))
            return
        peaks_override = [
            {"i": float(e["i"]), "pos": e["pos"], "depth": e["depth"],
             "smooth_depth": e["smooth_depth"], "width": e["width"]}
            for e in included
        ]
        multiplicities = {int(e["i"]): int(e["count"]) for e in included}
        ok = self.on_init_from_minima(show_message=True, peaks_override=peaks_override,
                                      multiplicities=multiplicities)
        if ok:
            self._exit_minima_edit()

    def on_open_plotly(self) -> None:
        if hasattr(self, "plot_tabs"):
            self.plot_tabs.setCurrentWidget(self.plotly_tab)
        self._update_plotly_view()

    def on_export_plotly_html(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("file.export_plotly_html"), str(ROOT / "mossbauer_plotly.html"),
            "HTML (*.html);;All (*.*)")
        if not path:
            return
        try:
            out = Path(path)
            if out.suffix.lower() not in (".html", ".htm"):
                out = out.with_suffix(".html")
            out.write_text(self._plotly_html_document(), encoding="utf-8")
            self.statusBar().showMessage(tr("status.plotly_exported", path=str(out)), 6000)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, tr("plotly.title"), str(exc))

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
        if (self.calib.fit_velocity.isChecked()
                and not all(ctl.is_fixed() for ctl in self._active_bhf_controls())):
            QtWidgets.QMessageBox.warning(
                self,
                tr("msg.fit_velocity_title"),
                tr("msg.fit_velocity_requires_bhf_fixed"),
            )
            return
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
        self.last_distribution_result = None
        self.last_error_source = "covarianza (1σ)"
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
        table = QtWidgets.QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(["id", "fichero", "muestra", "fecha", "T", "vel. display", "calib"])
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeToContents)
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

        def _first_value(it: dict, *keys: str):
            """Devuelve el primer campo no vacío, aceptando anidados comunes."""
            nested = (it, it.get("metadata") or {}, it.get("condiciones") or {},
                      it.get("conditions") or {}, it.get("calibracion") or {},
                      it.get("calibration") or {})
            for data in nested:
                if not isinstance(data, dict):
                    continue
                for key in keys:
                    val = data.get(key)
                    if val not in (None, ""):
                        return val
            return ""

        def _short_filename(name: str) -> str:
            base = Path(str(name)).name
            return base[:13]

        def _date_text(it: dict) -> str:
            val = _first_value(it, "fecha", "date", "measured_at", "measurement_date",
                               "created", "created_at", "updated_at")
            txt = str(val or "")
            return txt[:10] if len(txt) >= 10 else txt

        def _calibration_id_text(it: dict) -> str:
            val = _first_value(it, "calibracion_id", "calibration_id", "calib_id",
                               "id_calibracion", "id_calibration")
            if val:
                return str(val)
            cal = it.get("calibracion") or it.get("calibration") or it.get("calibrado")
            if isinstance(cal, dict) and cal.get("id") not in (None, ""):
                return str(cal.get("id"))
            if isinstance(cal, (int, str)):
                return str(cal)
            return ""

        def _temperature_text(it: dict) -> str:
            val = _first_value(it, "temperatura", "temperature", "temp", "temp_k",
                               "temperature_k", "temp_c", "temperature_c")
            return str(val) if val not in (None, "") else ""

        def _velocity_text(it: dict) -> str:
            # En el listado web queremos la velocidad *display* de la medida,
            # no necesariamente la velocidad calibrada/ajustada usada después.
            val = _first_value(it, "velocity_input", "velocidad_input",
                               "velocity_display", "velocidad_display",
                               "display_velocity", "display_vmax", "vmax_display",
                               "velocidad", "velocity", "vmax", "v_max",
                               "velocidad_max", "velocity_max")
            return str(val) if val not in (None, "") else ""

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
                filename = str(it.get("file_name") or it.get("filename") or it.get("datafile") or "")
                sample = str(_first_value(it, "muestra", "sample", "sample_name", "nombre_muestra", "name"))
                values = [
                    str(it.get("id", "")),
                    _short_filename(filename),
                    sample,
                    _date_text(it),
                    _temperature_text(it),
                    _velocity_text(it),
                    "" if is_calib else _calibration_id_text(it),
                ]
                for c, value in enumerate(values):
                    cell = QtWidgets.QTableWidgetItem(value)
                    if c == 1 and filename:
                        cell.setToolTip(filename)
                    elif c == 2 and sample:
                        cell.setToolTip(sample)
                    table.setItem(r, c, cell)
            debug(f"{len(items)} resultados.")

        btn_search.clicked.connect(refresh)
        e_search.returnPressed.connect(refresh)

        # Filtro local opcional sobre items ya descargados
        def local_filter(_=None):
            q = e_search.text().strip().lower()
            if not q:
                return
            for r in range(table.rowCount()):
                hay = " ".join(
                    table.item(r, c).text().lower()
                    for c in range(table.columnCount())
                    if table.item(r, c) is not None)
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
            selected_item = next((it for it in items if str(it.get("id", "")) == item_id), {})
            dest = Path(e_dest.text().strip() or (Path.home() / "Mossbauer"))
            calib: dict | None = None
            calib_path: Path | None = None
            try:
                dest.mkdir(parents=True, exist_ok=True)
                client = build_client()
                persist()
                if is_calib:
                    p = client.download_calibracion_datafile(item_id, dest_dir=str(dest))
                    calib = selected_item or client.get_calibracion(item_id)
                    calib_path = Path(p)
                else:
                    p = client.download_datafile(item_id, dest_dir=str(dest))
                    try:
                        calib = client.get_calibracion_de_medida(item_id)
                    except Exception as exc:
                        debug(f"(sin metadatos de calibración asociada: {exc})")
                    if cb_with_calib.isChecked() and calib and "id" in calib:
                        try:
                            calib_path = client.download_calibracion_datafile(
                                calib["id"], dest_dir=str(dest))
                            debug(f"Calibración asociada → {calib_path}")
                        except Exception as exc:
                            debug(f"(no se descargó el fichero de calibración: {exc})")
            except Exception as exc:
                QtWidgets.QMessageBox.critical(dlg, "Descarga", str(exc))
                return
            debug(f"Descargado: {p}")
            if not load_after:
                table.clearSelection()
                return
            try:
                self._load_file(Path(p))
                if is_calib:
                    self._apply_web_calibration_metadata(
                        calibration=calib or selected_item,
                        calibration_path=calib_path or Path(p),
                        debug=debug,
                    )
                elif calib:
                    self._apply_web_calibration_metadata(
                        measurement=selected_item or {"id": item_id},
                        calibration=calib,
                        calibration_path=calib_path,
                        debug=debug,
                    )
                else:
                    debug("La medida cargada no trae calibración asociada aplicable.")
                dlg.accept()
            except Exception as exc:
                QtWidgets.QMessageBox.warning(dlg, "Cargar", str(exc))

        btn_list.clicked.connect(refresh)
        btn_download_only.clicked.connect(lambda: download(False))
        btn_dl.clicked.connect(lambda: download(True))
        btn_close.clicked.connect(dlg.reject)
        dlg.exec()

    def _apply_web_calibration_metadata(self, *, calibration: dict | None,
                                        measurement: dict | None = None,
                                        calibration_path: Path | None = None,
                                        debug=None) -> None:
        """Guarda en la GUI los metadatos de una calibración web y aplica Vmax.

        La API devuelve ``velocity_calibrated`` e ``isomer_shift`` como
        metadatos de la calibración. Al cargar una medida desde la web, estos
        valores deben quedar en ``self.calibration_info`` igual que una
        calibración local, y ``velocity_calibrated`` debe reescalar el eje de
        velocidad del fichero activo.
        """
        if not calibration:
            if debug is not None:
                debug("La API no devolvió metadatos de calibración.")
            return

        def first_value(data: dict, *keys: str):
            nested = (data, data.get("metadata") or {}, data.get("condiciones") or {},
                      data.get("conditions") or {})
            for item in nested:
                if not isinstance(item, dict):
                    continue
                for key in keys:
                    value = item.get(key)
                    if value not in (None, ""):
                        return value
            return None

        velocity = first_value(calibration, "velocity_calibrated", "vmax_calibrated",
                               "velocity", "velocidad", "vmax", "v_max")
        iso = first_value(calibration, "isomer_shift", "isomershift",
                          "isomer", "iso", "delta")
        info = {
            "source": "web_api",
            "medida_id": (measurement or {}).get("id"),
            "calibration_id": calibration.get("id") or first_value(
                measurement or {}, "calibration_id", "calibracion_id", "calib_id"),
            "calibration_sample": first_value(
                calibration, "sample", "muestra", "sample_name",
                "nombre_muestra", "name"),
            "calibration_date": first_value(
                calibration, "date", "fecha", "measured_at", "created_at", "created"),
            "velocity_calibrated": velocity,
            "isomer_shift": iso,
            "calibration_file_name": Path(calibration_path).name if calibration_path else None,
            "calibration_file_path": str(calibration_path) if calibration_path else None,
        }
        for key in ("velocity_uncertainty", "vmax_uncertainty", "velocity_error",
                    "vmax_error", "sigma_vmax"):
            value = first_value(calibration, key)
            if value not in (None, ""):
                info[key] = value

        self.calibration_info = info
        self._refresh_calib_label()
        if debug is not None:
            debug(f"Calibración web aplicada: id={info.get('calibration_id') or '—'} "
                  f"Vmax={velocity if velocity not in (None, '') else '—'} "
                  f"IS={iso if iso not in (None, '') else '—'}")

        if velocity in (None, ""):
            if debug is not None:
                debug("La calibración no trae velocity_calibrated; no se aplica Vmax.")
            return
        try:
            vmax = float(velocity)
        except (TypeError, ValueError):
            if debug is not None:
                debug(f"velocity_calibrated no numérico: {velocity!r}")
            return

        self.calib.vmax.set_value(vmax)
        if self.file.counts is not None:
            center = float(self.calib.center.value())
            self._refold_current_data(center)
        self._refresh_plot()

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

    def _qt_update_prefs(self) -> dict:
        try:
            if SETTINGS_PATH.exists():
                data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def _updates_at_startup_enabled(self) -> bool:
        return bool(self._qt_update_prefs().get("check_updates_on_startup", False))

    def _save_qt_update_prefs(self, *, startup: bool, checksum: bool) -> None:
        current = self._qt_update_prefs()
        current["check_updates_on_startup"] = bool(startup)
        current["verify_update_checksum"] = bool(checksum)
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")

    def _downloads_dir(self) -> Path:
        for name in ("Descargas", "Downloads"):
            path = Path.home() / name
            if path.exists():
                return path
        return Path.home()

    def _run_in_ui_thread(self, fn) -> None:
        bridge = getattr(self, "_ui_bridge", None)
        if bridge is not None:
            bridge.call.emit(fn)
            return
        QtCore.QTimer.singleShot(0, fn)

    def on_configure_updates(self) -> None:
        """Configura el canal de releases y las opciones propias del front-end Qt."""
        update_cfg = load_update_settings(CONFIG_DIR)
        qt_cfg = self._qt_update_prefs()

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("help.configure_updates"))
        dlg.setModal(True)
        v = QtWidgets.QVBoxLayout(dlg)

        v.addWidget(QtWidgets.QLabel("Canal de avisos de actualización:"))
        rb_stable = QtWidgets.QRadioButton("Solo versiones estables")
        rb_all = QtWidgets.QRadioButton("Estables y versiones no estables/beta")
        if update_cfg.get("channel", "stable") == "all":
            rb_all.setChecked(True)
        else:
            rb_stable.setChecked(True)
        v.addWidget(rb_stable)
        v.addWidget(rb_all)

        hint = QtWidgets.QLabel(
            "Las versiones beta sirven para probar cambios. Si eliges betas, "
            "el programa avisará también de prereleases de GitHub."
        )
        hint.setWordWrap(True)
        v.addWidget(hint)

        cb_startup = QtWidgets.QCheckBox("Buscar actualizaciones al arrancar (silencioso)")
        cb_startup.setChecked(bool(qt_cfg.get("check_updates_on_startup", False)))
        v.addWidget(cb_startup)
        cb_checksum = QtWidgets.QCheckBox("Verificar checksum SHA-256 al descargar")
        cb_checksum.setChecked(bool(qt_cfg.get("verify_update_checksum", True)))
        v.addWidget(cb_checksum)

        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        channel = "all" if rb_all.isChecked() else "stable"
        try:
            save_update_settings(CONFIG_DIR, {"channel": channel}, parent=None)
            self._save_qt_update_prefs(
                startup=cb_startup.isChecked(), checksum=cb_checksum.isChecked())
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, tr("help.configure_updates"), str(exc))

    # ── Check for updates ───────────────────────────────────────────────
    def check_for_updates(self, silent: bool = False) -> None:
        """Comprueba GitHub Releases en segundo plano, igual que la interfaz Tk."""
        update_settings = load_update_settings(CONFIG_DIR)
        include_prereleases = update_settings.get("channel", "stable") == "all"
        verify_checksum = bool(self._qt_update_prefs().get("verify_update_checksum", True))
        channel_txt = "estables y beta" if include_prereleases else "solo estables"
        if not silent:
            self.statusBar().showMessage("Buscando actualizaciones…")

        def worker() -> None:
            try:
                release = latest_release(include_prereleases=include_prereleases)
                newer = is_newer(release.tag, APP_VERSION)
            except Exception as exc:
                if not silent:
                    self._run_in_ui_thread(
                        lambda e=exc: QtWidgets.QMessageBox.warning(
                            self, tr("help.check_updates"),
                            f"No se pudo comprobar GitHub Releases:\n{e}"))
                return

            def finish() -> None:
                if not newer:
                    if not silent:
                        QtWidgets.QMessageBox.information(
                            self, tr("help.check_updates"),
                            f"Ya tienes la última versión ({APP_VERSION}) para el canal: {channel_txt}.")
                    return
                self._show_update_available_dialog(release, channel_txt, verify_checksum)

            self._run_in_ui_thread(finish)

        threading.Thread(target=worker, daemon=True).start()

    def on_check_updates(self) -> None:
        self.check_for_updates(silent=False)

    def _show_update_available_dialog(self, release, channel_txt: str, verify_checksum: bool) -> None:
        body = (release.body or "").strip()
        release_kind = "no estable/beta" if getattr(release, "prerelease", False) else "estable"
        msg = (
            f"Hay una versión nueva disponible ({release_kind}).\n\n"
            f"Canal configurado: {channel_txt}\n"
            f"Versión actual:    {APP_VERSION}\n"
            f"Nueva versión:     {release.tag}\n\n"
            + (("─" * 60) + "\n\n" + body + "\n\n" if body else "")
            + "¿Quieres descargarla ahora?"
        )

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Actualización disponible")
        dlg.resize(860, 480)
        v = QtWidgets.QVBoxLayout(dlg)
        text = QtWidgets.QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(msg)
        v.addWidget(text, stretch=1)
        buttons = QtWidgets.QDialogButtonBox()
        btn_yes = buttons.addButton("Sí, descargar ahora", QtWidgets.QDialogButtonBox.AcceptRole)
        buttons.addButton("No por ahora", QtWidgets.QDialogButtonBox.RejectRole)
        buttons.accepted.connect(dlg.accept); buttons.rejected.connect(dlg.reject)
        v.addWidget(buttons)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            url, filename = choose_download(release, prefer_exe=(os.name == "nt"))
            self._download_update_in_background(release, url, filename, verify_checksum)
        else:
            answer = QtWidgets.QMessageBox.question(
                self, "Actualizaciones", "¿Abrir la página de releases en el navegador?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No)
            if answer == QtWidgets.QMessageBox.Yes:
                webbrowser.open(release.html_url)
        btn_yes.deleteLater()

    def _download_update_in_background(self, release, url: str, filename: str, verify_checksum: bool) -> None:
        self.statusBar().showMessage("Descargando actualización…")

        def worker_download() -> None:
            expected = None
            if verify_checksum:
                try:
                    expected = find_release_checksum(release, filename)
                except Exception:
                    expected = None
            try:
                path = download_file(
                    url, self._downloads_dir(), filename,
                    expected_sha256=expected if verify_checksum else None)
            except Exception as exc:
                errmsg = (
                    "No se pudo descargar o verificar la actualización"
                    if verify_checksum else "No se pudo descargar la actualización"
                )
                self._run_in_ui_thread(
                    lambda e=exc: QtWidgets.QMessageBox.critical(
                        self, "Actualizaciones", f"{errmsg}:\n{e}"))
                return
            verified = verify_checksum and expected is not None
            self._run_in_ui_thread(lambda: self._finish_downloaded_update(path, verified, verify_checksum))

        threading.Thread(target=worker_download, daemon=True).start()

    def _finish_downloaded_update(self, path: Path, verified: bool, verify_checksum: bool) -> None:
        if verify_checksum:
            integridad = (
                "Integridad verificada con SHA-256."
                if verified
                else "Aviso: la release no publica checksum; no se pudo verificar la integridad."
            )
            integridad_suffix = f"\n\n{integridad}"
        else:
            integridad_suffix = ""
        if is_zip_update(path):
            answer = QtWidgets.QMessageBox.question(
                self, "Actualización descargada",
                f"Descargado en:\n{path}{integridad_suffix}\n\n"
                "¿Instalar ahora sobre esta carpeta del programa?\n"
                "Después solo tendrás que cerrar y volver a abrir el programa.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes)
            if answer == QtWidgets.QMessageBox.Yes:
                try:
                    install_zip_update(path, ROOT)
                    pip_msg = _pip_install_requirements(ROOT)
                    _update_pip_stamp(ROOT, CONFIG_DIR)
                except Exception as exc:
                    QtWidgets.QMessageBox.critical(
                        self, "Actualizaciones", f"No se pudo instalar la actualización:\n{exc}")
                    return
                pip_suffix = f"\n\n{pip_msg}" if pip_msg else ""
                QtWidgets.QMessageBox.information(
                    self, "Actualización instalada",
                    "La nueva versión se ha descomprimido en la carpeta del programa."
                    f"{pip_suffix}\n\n"
                    "Cierra y vuelve a abrir el programa para usarla.")
                return
        QtWidgets.QMessageBox.information(
            self, "Actualización descargada",
            f"Descargado en:\n{path}{integridad_suffix}\n\n"
            "Cierra el programa y usa ese fichero para instalar/ejecutar la nueva versión.")

    def _check_requirements_background(self) -> None:
        try:
            check_requirements_if_needed(ROOT, CONFIG_DIR)
        except Exception:
            pass

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
            try:
                vmax_txt = f"{float(vmax):.4f}"
            except (TypeError, ValueError):
                vmax_txt = str(vmax)
            if iso not in (None, ""):
                try:
                    iso_txt = f"{float(iso):.4f}"
                except (TypeError, ValueError):
                    iso_txt = str(iso)
            else:
                iso_txt = "—"
            txt += f"Vmax = {vmax_txt} mm/s · IS = {iso_txt} mm/s"
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
        # Motor puro: ajuste base + remuestreo Monte Carlo (core.fit_engine).
        self.statusBar().showMessage("Ajuste base…")
        QtWidgets.QApplication.processEvents()

        def _progress(msg: str, _i: int, _n: int) -> None:
            self.statusBar().showMessage(f"{msg}…")
            QtWidgets.QApplication.processEvents()

        try:
            res = bootstrap_errors(state, n_rep=nrep, progress_cb=_progress)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("msg.bootstrap_title"),
                                            f"{type(exc).__name__}: {exc}")
            return
        if not res.base.free_keys:
            QtWidgets.QMessageBox.information(
                self, tr("msg.bootstrap_title"), tr("msg.bootstrap_no_free"))
            return
        # Vuelca σ(MC) en el último ajuste para que el informe la use como
        # incertidumbre (más fiable que la covarianza cuando hay correlaciones).
        if self.last_fit_result is not None:
            self.last_fit_result.errors.update(res.std)
        else:
            self.last_fit_result = res.base
            self.last_fit_result.errors.update(res.std)
        self.last_error_source = f"bootstrap Monte Carlo (n={res.n_ok})"
        self.act_export_report.setEnabled(True)
        msg_lines = [tr("msg.bootstrap_done", ok=res.n_ok, total=res.n_rep), ""]
        for k in res.base.free_keys:
            msg_lines.append(f"  {k:14s}  σ(MC) = {res.std[k]:.4g}")
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
                "depth": float(vals.get(p + "depth", 0.0)),
                "depth_fixed": bool(cp.params["depth"].is_fixed()) if "depth" in cp.params else False,
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
        from core.constants import CHANGELOG_PATH
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
        components_for_plot: list[tuple[int, str, np.ndarray]] = []
        if self.dist_use_sharp and result.sharp_weights is not None and result.sharp_weights.size:
            baseline_line = float(result.baseline) + float(result.slope) * self.file.velocity
            sharp_abs_sum = np.zeros_like(self.file.velocity, dtype=float)
            for idx, weight in zip(sharp_indices, result.sharp_weights):
                cp = self.components_panels[idx - 1]
                vals = cp.values_dict()
                pfx = f"s{idx}_"
                params = np.array([float(vals.get(pfx + name, 0.0)) for name in SEXTET_PARAM_NAMES], dtype=float)
                params[6] = float(weight)
                sharp_abs = component_absorption(self.file.velocity, cp.kind, params)
                sharp_abs_sum += sharp_abs
                components_for_plot.append((idx, f"Nítido {tr(f'kind.{cp.kind}', default=cp.kind)}", baseline_line - sharp_abs))
            if np.any(sharp_abs_sum > 0):
                dist_name = "P(ΔEQ)" if var == "quad" else "P(BHF)"
                components_for_plot.insert(0, (0, dist_name, result.fitted_curve + sharp_abs_sum))
        self.canvas.render(self.file.velocity, self.file.y_data,
                           model=result.fitted_curve, components=components_for_plot,
                           style=style, show_residual=show_res, show_legend=show_leg,
                           style_name=self.plot_style_name)
        self.last_distribution_result = result
        self._schedule_plotly_update()
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

    def on_init_from_minima(self, show_message: bool = True,
                            peaks_override: list[dict] | None = None,
                            multiplicities: dict[int, int] | None = None) -> bool:
        """Detecta mínimos y configura componentes discretas como en Tk.

        Con ``peaks_override`` se usan los mínimos ya curados por el usuario en
        el editor semi-manual (en vez de la detección automática), y
        ``multiplicities`` indica cuántas contribuciones tiene cada mínimo
        (``{índice_canal: nº}``) para añadir componentes solapadas extra.
        """
        if self.file.velocity is None or self.file.y_data is None:
            return False
        if peaks_override is not None:
            peaks = list(peaks_override)
            _, baseline, slope = self.detect_absorption_minima()
        else:
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

        # Contribuciones extra señaladas por el usuario: cada mínimo marcado con
        # n>1 añade (n-1) singletes solapados en esa posición, hasta el máximo de
        # componentes, para que el ajuste pueda separar las contribuciones.
        if multiplicities:
            next_extra = max((idx for idx, _k, _g in components), default=0) + 1
            for pk in peaks:
                extra = int(multiplicities.get(int(pk["i"]), 1)) - 1
                for _ in range(max(0, extra)):
                    if next_extra > MAX_QT_COMPONENTS:
                        break
                    pfx = f"s{next_extra}_"
                    components.append((next_extra, "Singlete", [pk]))
                    params[pfx + "delta"] = float(pk["pos"])
                    params[pfx + "gamma1"] = float(np.clip(pk["width"] / 2.0, 0.04, 1.0))
                    params[pfx + "depth"] = float(np.clip(pk["depth"] * 0.5, 0.002, 0.25))
                    params[pfx + "int1"] = 1.0
                    next_extra += 1

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

        def _progress(msg: str, _i: int, _n: int) -> None:
            self.statusBar().showMessage(f"{msg}…")
            QtWidgets.QApplication.processEvents()

        # Motor puro: verosimilitud perfilada con escaneo adaptativo (core.fit_engine).
        try:
            results = profile_likelihood(state, progress_cb=_progress)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("fit.profile_likelihood"),
                                            f"{type(exc).__name__}: {exc}")
            return
        if not results:
            QtWidgets.QMessageBox.information(
                self, tr("fit.profile_likelihood"),
                "No hay parámetros libres para perfilar.")
            return
        self.statusBar().showMessage(
            f"Verosimilitud perfilada: {len(results)} parámetros", 5000)
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

    def _build_report_lines(self) -> list[str]:
        """Genera el informe en Markdown estructurado por secciones.

        Recoge **toda** la información mostrada en el panel "Estado y
        parámetros" (espectro, calibración, bondad, diagnóstico residual,
        análisis de áreas, parámetros por componente con magnitudes físicas
        derivadas, δ corregidos por calibración, fijados y restricciones)
        y la presenta como tablas y bloques tipados.
        """
        from datetime import datetime
        file_name = self.file.path.name if self.file.path else "—"
        ci = self.calibration_info
        iso_ref = self.calibration_iso_ref()
        fit = self.last_fit_result
        active_panels = [cp for cp in self.components_panels if cp.enabled.isChecked()]

        def _ferr(v: float | None) -> str:
            return f"± {v:.3g}" if v is not None and v > 0 else "—"

        lines: list[str] = []
        lines.append("# 📊 Mössbauer Fe-57 — Informe de ajuste")
        lines.append("")
        lines.append(
            f"**Fichero:** `{file_name}` · **Fecha:** "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')} · **Programa:** "
            f"{APP_NAME} v{APP_VERSION} (Qt)"
        )
        lines.append("")

        if fit is not None and fit.stats:
            st = fit.stats
            bits = []
            if st.get("red_chi2") is not None:
                bits.append(f"χ²ᵣ = **{st['red_chi2']:.4g}**")
            if st.get("chi2") is not None:
                bits.append(f"χ² = {st['chi2']:.4g}")
            if st.get("dof") is not None:
                bits.append(f"dof = {int(st['dof'])}")
            if st.get("aic") is not None:
                bits.append(f"AIC = {st['aic']:.4g}")
            if st.get("bic") is not None:
                bits.append(f"BIC = {st['bic']:.4g}")
            lines.append("> ### 🎯 Resumen del ajuste")
            lines.append("> " + " · ".join(bits))
            lines.append(
                f"> {len(fit.free_keys)} parámetros libres · "
                f"σ: {self.last_error_source}"
            )
            lines.append("")

        # ── Espectro y plegado ──────────────────────────────────────────
        lines.append("## 📁 Espectro y plegado")
        lines.append("")
        lines.append("| Campo | Valor |")
        lines.append("|---|---|")
        lines.append(f"| Fichero | `{file_name}` |")
        n_chan = self.file.counts.size if self.file.counts is not None else 0
        lines.append(f"| Canales leídos | {n_chan} |")
        center_val = float(self.calib.center.value())
        lines.append(f"| Folding point centro | {center_val:.5f} |")
        lines.append(f"| Folding point Normos (≈ 2·centro) | {2.0 * center_val:.5f} |")
        if self.file.folded is not None:
            lines.append(f"| Pares doblados | {int(self.file.folded.size)} |")
        norm_factor = getattr(self.file, "norm_factor", None)
        if norm_factor is not None:
            lines.append(f"| Normalización | / {norm_factor:.6g} |")
        lines.append(f"| Perfil de línea | {self.calib.line_profile} |")
        lines.append("")

        # ── Calibración ──────────────────────────────────────────────────
        lines.append("## 🎛️ Calibración y escala de velocidades")
        lines.append("")
        lines.append("| Campo | Valor |")
        lines.append("|---|---|")
        lines.append(f"| Vmax | {self.calib.vmax.value():.6g} mm/s |")
        lines.append(f"| Línea base | {self.calib.baseline.value():.6g} |")
        lines.append(f"| Pendiente del fondo | {self.calib.slope.value():.6g} |")
        lines.append(f"| Ajustar Vmax con el patrón | "
                     f"{'sí' if self.calib.fit_velocity.isChecked() else 'no'} |")
        if ci:
            sample = ci.get("calibration_sample") or ci.get("calibration_file_name") or "—"
            lines.append(f"| Origen calibración | {ci.get('source', '?')} |")
            lines.append(f"| Muestra | {sample} |")
            if ci.get("calibration_file_name"):
                lines.append(f"| Fichero calibración | `{ci['calibration_file_name']}` |")
            if ci.get("velocity_calibrated") is not None:
                lines.append(
                    f"| Vmax calibrada | {float(ci['velocity_calibrated']):.6g} mm/s |"
                )
            if iso_ref is not None:
                lines.append(f"| δ de referencia (iso_ref) | {iso_ref:.6g} mm/s |")
            if ci.get("calibration_date"):
                lines.append(f"| Fecha calibración | {ci['calibration_date']} |")
        cal_unc = self.calibration_uncertainty_text()
        if cal_unc:
            lines.append("")
            lines.append(f"> ℹ️ {cal_unc}")
        elif not ci:
            lines.append("")
            lines.append("> ⚠️ Sin calibración activa; los δ no están corregidos.")
        lines.append("")

        # ── Bondad y diagnóstico del ajuste ──────────────────────────────
        stats = (fit.stats if fit is not None else {}) or {}
        rms = self._info_rms()
        if stats or not (rms != rms):  # rms != rms ⇒ NaN
            lines.append("## 📐 Bondad y diagnóstico")
            lines.append("")
            lines.append("| Indicador | Valor |")
            lines.append("|---|---|")
            if stats.get("chi2") is not None:
                lines.append(f"| χ² | {stats['chi2']:.6g} |")
            if stats.get("red_chi2") is not None:
                lines.append(f"| χ² reducido | {stats['red_chi2']:.6g} |")
            if stats.get("dof") is not None:
                lines.append(f"| dof | {int(stats['dof'])} |")
            if stats.get("aic") is not None:
                lines.append(f"| AIC | {stats['aic']:.6g} |")
            if stats.get("bic") is not None:
                lines.append(f"| BIC | {stats['bic']:.6g} |")
            if stats.get("n_params") is not None:
                lines.append(f"| Nº parámetros del modelo | {int(stats['n_params'])} |")
            if rms == rms:  # not NaN
                lines.append(f"| RMS del ajuste | {rms:.6g} |")
            if fit is not None:
                lines.append(f"| Autoarranques probados | {int(fit.n_starts)} |")
            lines.append("")
            # Diagnóstico residual
            if any(k in stats for k in ("resid_lag1", "resid_runs_z", "resid_antisym_corr")):
                lines.append("**Diagnóstico del residuo**")
                lines.append("")
                lines.append("| Estadístico | Valor | Umbral de aviso |")
                lines.append("|---|---|---|")
                lines.append(f"| Autocorrelación lag-1 | {stats.get('resid_lag1', float('nan')):.3f} | \\|·\\| > 0.35 |")
                lines.append(f"| Runs test (z) | {stats.get('resid_runs_z', float('nan')):.3f} | \\|·\\| > 2.0 |")
                lines.append(f"| Correlación antisimétrica | {stats.get('resid_antisym_corr', float('nan')):.3f} | > 0.45 |")
                lines.append("")
                if (abs(stats.get("resid_lag1", 0.0)) > 0.35
                        or abs(stats.get("resid_runs_z", 0.0)) > 2.0
                        or stats.get("resid_antisym_corr", 0.0) > 0.45):
                    lines.append("> ⚠️ El residuo parece tener estructura no aleatoria. "
                                 "Revisa modelo, *folding point*, calibración Vmax o si "
                                 "faltan componentes.")
                    lines.append("")
            # Correlaciones
            corr = (fit.correlations or {}) if fit is not None else {}
            max_pair = corr.get("max_pair") or []
            max_abs = corr.get("max_abs_corr")
            if max_pair and max_abs is not None:
                lines.append(
                    f"_Correlación máxima:_ `{max_pair[0]}` ↔ `{max_pair[1]}` con "
                    f"|r| = **{float(max_abs):.3f}**."
                )
                lines.append("")
            high = corr.get("high_pairs") or []
            if high:
                lines.append("**⚠️ Parámetros muy correlacionados (|r| ≥ 0.95)**")
                lines.append("")
                lines.append("| Par | r |")
                lines.append("|---|---|")
                for hp in high:
                    lines.append(f"| `{hp['param1']}` ↔ `{hp['param2']}` | {hp['corr']:.3f} |")
                lines.append("")

        # ── Análisis de áreas ───────────────────────────────────────────
        pct_active, areas, percentages = self.component_area_percentages()
        pct_errors = self.component_percentage_errors()
        if pct_active:
            lines.append("## 🥧 Análisis de áreas por componente")
            lines.append("")
            lines.append("| Componente | Tipo | % área | σ (%) | Área absoluta |")
            lines.append("|---|---|---|---|---|")
            for idx, area, pct in zip(pct_active, areas, percentages):
                cp = self.components_panels[idx - 1]
                kind_disp = tr(f"kind.{cp.kind}", default=cp.kind)
                err = pct_errors.get(idx)
                err_txt = f"± {err:.3g}" if err is not None else "—"
                lines.append(
                    f"| {idx} | {kind_disp} | {pct:.3f}% | {err_txt} | {area:.6g} |"
                )
            lines.append("")

        # ── Componentes (parámetros + magnitudes físicas) ───────────────
        lines.append("## 🧪 Componentes")
        lines.append("")
        for cp in active_panels:
            kind_disp = tr(f"kind.{cp.kind}", default=cp.kind)
            lines.append(f"### 🔹 Componente {cp.idx} — {kind_disp}")
            lines.append("")
            lines.append("**Parámetros**")
            lines.append("")
            lines.append("| Parámetro | Valor | Estado |")
            lines.append("|---|---|---|")
            for k, ctl in cp.params.items():
                state_lbl = "🔒 fijo" if ctl.is_fixed() else "🔓 libre"
                lines.append(f"| `s{cp.idx}_{k}` | {ctl.value():.6g} | {state_lbl} |")
            lines.append("")
            # Magnitudes físicas derivadas: anchuras reales e intensidades absolutas
            g1 = cp.params["gamma1"].value()
            g2 = g1 * cp.params["gamma2"].value()
            g3 = g1 * cp.params["gamma3"].value()
            i3_real = cp.params["int3"].value()
            i2_real = i3_real * cp.params["int2"].value()
            i1_real = i3_real * cp.params["int1"].value()
            lines.append("**Magnitudes físicas derivadas**")
            lines.append("")
            lines.append("| Magnitud | Valor |")
            lines.append("|---|---|")
            lines.append(f"| Γ HWHM reales 1 / 2 / 3 (mm/s) | {g1:.4g} / {g2:.4g} / {g3:.4g} |")
            lines.append(f"| FWHM equivalentes 1 / 2 / 3 (mm/s) | {2.0 * g1:.4g} / {2.0 * g2:.4g} / {2.0 * g3:.4g} |")
            lines.append(f"| Γ relativas 2 / 3 | {cp.params['gamma2'].value():.4g} / {cp.params['gamma3'].value():.4g} |")
            lines.append(f"| Profundidad | {cp.params['depth'].value():.6g} |")
            lines.append(f"| Intensidades reales I₁ / I₂ / I₃ | {i1_real:.4g} / {i2_real:.4g} / {i3_real:.4g} |")
            lines.append(f"| BHF | {cp.params['bhf'].value():.6g} T |")
            lines.append(f"| δ (sin corregir) | {cp.params['delta'].value():.6g} mm/s |")
            lines.append(f"| ΔEQ | {cp.params['quad'].value():.6g} mm/s |")
            if iso_ref is not None:
                lines.append(
                    f"| **δ corregido** (iso_ref = {iso_ref:.6g}) | "
                    f"**{cp.params['delta'].value() - iso_ref:.6g} mm/s** |"
                )
            lines.append("")
            # Textura derivada
            derived = self.texture_derived(cp)
            if derived is not None:
                lines.append("**🧭 Magnitudes derivadas de la textura (t = sin²θ)**")
                lines.append("")
                lines.append("| Magnitud | Valor | σ |")
                lines.append("|---|---|---|")
                lines.append(f"| t (parámetro de textura) | {derived['t']:.4g} | {_ferr(derived['sigma_t'])} |")
                lines.append(f"| θ (ángulo respecto a γ) | {derived['theta_deg']:.4g}° | {_ferr(derived['sigma_theta_deg'])} |")
                lines.append(f"| R₂₃ = I₂/I₃ | {derived['r23']:.4g} | {_ferr(derived['sigma_r23'])} |")
                lines.append(f"| S = ⟨P₂(cos θ)⟩ | {derived['s']:.4g} | {_ferr(derived['sigma_s'])} |")
                lines.append("")
                lines.append("> 💡 **Interpretación:** *t = sin²θ* parametriza la razón de "
                             "intensidades I₂/I₃ del sextete: t = 0 ⇒ campo paralelo al rayo γ "
                             "(I₂ = 0), t = 2/3 ⇒ muestra random (θ ≈ 54.7°, R₂₃ = 2), "
                             "t = 1 ⇒ campo perpendicular (R₂₃ = 4). *S* es un parámetro de "
                             "orden tipo Hermans: **+1** alineado al γ, **0** isótropo, "
                             "**−½** perpendicular.")
                lines.append("")

        # ── δ corregidos por calibración (resumen) ──────────────────────
        if iso_ref is not None and active_panels:
            lines.append("## 🎯 δ corregidos por calibración")
            lines.append("")
            lines.append(f"_Referencia isomérica de la calibración:_ **{iso_ref:.6g} mm/s**.")
            lines.append("")
            lines.append("| Componente | Tipo | δ ajustado (mm/s) | δ corregido (mm/s) |")
            lines.append("|---|---|---|---|")
            for cp in active_panels:
                d = cp.params["delta"].value()
                kind_disp = tr(f"kind.{cp.kind}", default=cp.kind)
                lines.append(
                    f"| {cp.idx} | {kind_disp} | {d:.6g} | **{d - iso_ref:.6g}** |"
                )
            lines.append("")

        # ── Parámetros libres (resumen rápido para tabla del ajuste) ────
        if fit is not None and fit.free_keys:
            lines.append("## 📈 Parámetros del ajuste (libres)")
            lines.append("")
            lines.append(f"_Fuente de σ:_ {self.last_error_source}")
            lines.append("")
            lines.append("| Parámetro | Valor | σ |")
            lines.append("|---|---|---|")
            for k in fit.free_keys:
                val = fit.values.get(k)
                err = fit.errors.get(k)
                val_txt = f"{val:.6g}" if val is not None else "—"
                err_txt = f"± {err:.3g}" if err is not None and err > 0 else "—"
                lines.append(f"| `{k}` | {val_txt} | {err_txt} |")
            lines.append("")

        # ── Fijados y restricciones ──────────────────────────────────────
        fixed = self._fixed_param_keys()
        if fixed:
            lines.append("## 🔒 Parámetros fijados")
            lines.append("")
            lines.append(", ".join(f"`{k}`" for k in fixed))
            lines.append("")
        if self.constraints:
            lines.append("## 🔗 Restricciones entre parámetros")
            lines.append("")
            lines.append("| Destino | Fórmula |")
            lines.append("|---|---|")
            for c in self.constraints:
                lines.append(
                    f"| `{c['target']}` | "
                    f"{c.get('factor', 1.0):g} · `{c['source']}` + "
                    f"{c.get('offset', 0.0):g} |"
                )
            lines.append("")

        # ── Glosario ─────────────────────────────────────────────────────
        lines.append("## 📖 Glosario de parámetros")
        lines.append("")
        lines.append("| Símbolo | Magnitud | Unidad | Observación |")
        lines.append("|---|---|---|---|")
        lines.append("| δ | Desplazamiento isomérico | mm/s | Densidad de carga electrónica en el núcleo; referido a α-Fe. |")
        lines.append("| ΔEQ (`quad`) | Desdoblamiento cuadrupolar | mm/s | Asimetría del gradiente de campo eléctrico en el núcleo. |")
        lines.append("| BHF | Campo hiperfino magnético | T | Magnetismo local sentido por el núcleo. |")
        lines.append("| Γ (HWHM) | Anchura de línea | mm/s | Semianchura a media altura del perfil de línea. |")
        lines.append("| `depth` | Profundidad de absorción | (rel.) | Amplitud relativa del componente; ligada al efecto Mössbauer y al espesor. |")
        lines.append("| `int1/2/3` | Intensidades relativas | (rel.) | Razones nominales 3 : I₂ : 1 para un sextete. |")
        lines.append("| `texture` (t) | Parámetro de textura | (0–1) | t = sin²θ con θ = ángulo del campo respecto al γ; controla I₂/I₃. |")
        lines.append("| `beta` (β) | Ángulo EFG–BHF | ° | Solo en tratamiento Kündig fijo del cuadrupolo. |")
        lines.append("| `voigt_sigma` | σ gaussiana del perfil Voigt | mm/s | Anchura instrumental gaussiana convolucionada. |")
        lines.append("| `sat_scale` | Factor de saturación | (rel.) | Solo en modelo de absorbente grueso. |")
        lines.append("| `baseline` / `slope` | Línea base | (rel.) | Nivel y pendiente del fondo de transmisión. |")
        lines.append("| Vmax (`vmax`) | Velocidad máxima | mm/s | Calibración de la escala de velocidades. |")
        lines.append("")

        return lines

    @staticmethod
    def _md_strip_inline(text: str) -> str:
        """Limpia marcadores Markdown y emojis para renderizado en PDF.

        Elimina ``**bold**``, ``*italic*`` y `` `code` `` (se conserva el texto
        sin los caracteres de formato) y quita los emojis fuera del BMP que
        DejaVu (la fuente por defecto de matplotlib) no puede renderizar.
        """
        import re
        out = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        out = re.sub(r"\*(.+?)\*", r"\1", out)
        out = re.sub(r"`([^`]+)`", r"\1", out)
        # Quita emojis (Misc Symbols and Pictographs, Emoticons, Transport,
        # Supplemental Symbols and Pictographs, Dingbats, etc.).
        out = re.sub(
            "["
            "\U0001F300-\U0001F9FF"
            "\U0001FA00-\U0001FAFF"
            "\U00002600-\U000027BF"
            "]\\s?",
            "", out,
        )
        return out.strip()

    def _md_to_blocks(self, md_lines: list[str]) -> list[tuple[str, object]]:
        """Convierte líneas Markdown en bloques tipados ``(kind, data)``.

        Reconoce: encabezados ``### h3``, tablas GFM ``| … |``, callouts
        ``> …``, bloques de código `` ``` `` y párrafos consecutivos.
        """
        blocks: list[tuple[str, object]] = []
        i, n = 0, len(md_lines)
        while i < n:
            raw = md_lines[i]
            s = raw.strip()
            if not s:
                i += 1
                continue
            if s.startswith("### "):
                blocks.append(("h3", s[4:].strip()))
                i += 1
                continue
            if s.startswith("```"):
                j = i + 1
                buf: list[str] = []
                while j < n and not md_lines[j].strip().startswith("```"):
                    buf.append(md_lines[j])
                    j += 1
                blocks.append(("code", buf))
                i = j + 1
                continue
            if s.startswith(">"):
                buf = []
                while i < n and md_lines[i].strip().startswith(">"):
                    buf.append(md_lines[i].strip().lstrip(">").strip())
                    i += 1
                blocks.append(("callout", buf))
                continue
            if s.startswith("|") and s.endswith("|"):
                rows: list[str] = []
                while i < n and md_lines[i].strip().startswith("|") and md_lines[i].strip().endswith("|"):
                    rows.append(md_lines[i].strip())
                    i += 1
                is_table = (
                    len(rows) >= 2
                    and set(rows[1].replace("|", "").replace("-", "").replace(":", "").strip()) == set()
                )
                if is_table:
                    header = [c.strip() for c in rows[0].strip("|").split("|")]
                    data = [[c.strip() for c in r.strip("|").split("|")] for r in rows[2:]]
                    blocks.append(("table", (header, data)))
                else:
                    for r in rows:
                        blocks.append(("para", r))
                continue
            buf = [raw.rstrip()]
            j = i + 1
            while j < n and md_lines[j].strip() and not (
                md_lines[j].lstrip().startswith(("#", "|", ">", "```"))
            ):
                buf.append(md_lines[j].rstrip())
                j += 1
            blocks.append(("para", " ".join(s.strip() for s in buf).strip()))
            i = j
        return blocks

    def _render_pdf_report(self, pdf_path: "Path", md_lines: list[str]) -> None:
        """Renderiza el informe PDF con portada, banners de color, tablas
        reales (cuadrículas en vez de texto monoespaciado) y la gráfica
        actual al final. Solo depende de matplotlib."""
        from datetime import datetime
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib.figure import Figure as _PdfFigure
        from matplotlib.patches import Rectangle
        import textwrap as _tw

        SECTION_COLOR = "#1e40af"
        SECTION_COLOR_ALT = "#0f766e"
        ACCENT = "#dbeafe"
        TEXT_DARK = "#1f2937"
        TEXT_MUTED = "#475569"
        ZEBRA_BG = "#f8fafc"
        TABLE_BORDER = "#e2e8f0"
        CALLOUT_BG = "#fef3c7"
        CALLOUT_BAR = "#f59e0b"
        CODE_BG = "#f1f5f9"

        LEFT, RIGHT = 0.05, 0.95
        WIDTH = RIGHT - LEFT
        TOP_BODY = 0.92
        BOTTOM = 0.06

        def _open_page(title: str, color: str):
            fig = _PdfFigure(figsize=(8.27, 11.69), dpi=100, facecolor="white")
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.set_xlim(0, 1); ax.set_ylim(0, 1)
            ax.add_patch(Rectangle((0.0, 0.94), 1.0, 0.05,
                                   facecolor=color, edgecolor="none"))
            ax.text(LEFT, 0.965, self._md_strip_inline(title), color="white",
                    fontsize=14, fontweight="bold", va="center", ha="left")
            return fig, ax

        def _render_h3(ax, text, y):
            ax.text(LEFT, y - 0.022, self._md_strip_inline(text),
                    color=SECTION_COLOR, fontsize=11.5,
                    fontweight="bold", va="center", ha="left")
            ax.add_patch(Rectangle((LEFT, y - 0.038), 0.22, 0.0015,
                                   facecolor=SECTION_COLOR, edgecolor="none"))
            return y - 0.05

        def _wrap_lines(text, width):
            text = self._md_strip_inline(text)
            return _tw.wrap(text, width=width) or [""]

        def _render_para(ax, text, y, on_break):
            line_h = 0.020
            for ln in _wrap_lines(text, 110):
                if y - line_h < BOTTOM:
                    on_break()
                    y = TOP_BODY
                ax.text(LEFT, y - line_h * 0.7, ln,
                        color=TEXT_DARK, fontsize=9.5,
                        va="center", ha="left")
                y -= line_h
                ax = _current_ax()  # may have changed after on_break
            return y - 0.006

        def _render_callout(ax, lines, y, on_break):
            line_h = 0.020
            wrapped: list[str] = []
            for raw in lines:
                for w in _wrap_lines(raw, 105):
                    wrapped.append(w)
            if not wrapped:
                wrapped = [""]
            i_w = 0
            while i_w < len(wrapped):
                # Cuántas líneas caben antes del salto
                avail = int(max(0, (y - BOTTOM)) / line_h)
                if avail < 2:
                    on_break()
                    y = TOP_BODY
                    ax = _current_ax()
                    avail = int((y - BOTTOM) / line_h)
                take = min(avail, len(wrapped) - i_w)
                block_h = take * line_h + 0.012
                ax.add_patch(Rectangle((LEFT, y - block_h), WIDTH, block_h,
                                       facecolor=CALLOUT_BG, edgecolor="none"))
                ax.add_patch(Rectangle((LEFT, y - block_h), 0.006, block_h,
                                       facecolor=CALLOUT_BAR, edgecolor="none"))
                for k in range(take):
                    ax.text(LEFT + 0.015, y - 0.012 - k * line_h - line_h * 0.6,
                            wrapped[i_w + k], color="#7c2d12", fontsize=9.5,
                            va="center", ha="left")
                y -= block_h + 0.006
                i_w += take
            return y

        def _render_code(ax, lines, y, on_break):
            line_h = 0.018
            content = lines or [""]
            i_l = 0
            while i_l < len(content):
                avail = int(max(0, (y - BOTTOM)) / line_h)
                if avail < 2:
                    on_break()
                    y = TOP_BODY
                    ax = _current_ax()
                    avail = int((y - BOTTOM) / line_h)
                take = min(avail, len(content) - i_l)
                block_h = take * line_h + 0.010
                ax.add_patch(Rectangle((LEFT, y - block_h), WIDTH, block_h,
                                       facecolor=CODE_BG, edgecolor=TABLE_BORDER,
                                       linewidth=0.5))
                for k in range(take):
                    txt = content[i_l + k][:120]
                    ax.text(LEFT + 0.012, y - 0.008 - k * line_h - line_h * 0.6,
                            txt, color=TEXT_DARK, fontsize=8.5,
                            family="monospace", va="center", ha="left")
                y -= block_h + 0.006
                i_l += take
            return y

        def _render_table(ax, header, rows, y, on_break):
            # Calcular anchos por longitud máxima del contenido
            n_cols = len(header)
            if n_cols == 0:
                return y
            max_len = [len(self._md_strip_inline(header[c])) for c in range(n_cols)]
            for r in rows:
                for c in range(min(n_cols, len(r))):
                    max_len[c] = max(max_len[c], len(self._md_strip_inline(r[c])))
            total = sum(max_len) or 1
            col_w = [WIDTH * (m / total) for m in max_len]
            col_x = [LEFT]
            for c in range(n_cols - 1):
                col_x.append(col_x[-1] + col_w[c])
            row_h = 0.026
            header_h = 0.028

            def _draw_header(local_y):
                ax.add_patch(Rectangle((LEFT, local_y - header_h), WIDTH, header_h,
                                       facecolor=SECTION_COLOR, edgecolor="none"))
                for c, txt in enumerate(header):
                    ax.text(col_x[c] + col_w[c] * 0.04,
                            local_y - header_h * 0.55,
                            self._md_strip_inline(txt),
                            color="white", fontsize=9.0,
                            fontweight="bold", va="center", ha="left")
                return local_y - header_h

            # Espacio mínimo para encabezado + 1 fila
            if y - (header_h + row_h) < BOTTOM:
                on_break()
                y = TOP_BODY
                ax = _current_ax()
            y = _draw_header(y)
            for r_idx, row in enumerate(rows):
                if y - row_h < BOTTOM:
                    on_break()
                    y = TOP_BODY
                    ax = _current_ax()
                    y = _draw_header(y)
                bg = ZEBRA_BG if r_idx % 2 == 0 else "white"
                ax.add_patch(Rectangle((LEFT, y - row_h), WIDTH, row_h,
                                       facecolor=bg, edgecolor=TABLE_BORDER,
                                       linewidth=0.5))
                for c in range(n_cols):
                    cell = row[c] if c < len(row) else ""
                    txt = self._md_strip_inline(cell)
                    # Truncar si excede el ancho de columna
                    max_chars = max(4, int(col_w[c] * 95))
                    if len(txt) > max_chars:
                        txt = txt[: max_chars - 1] + "…"
                    ax.text(col_x[c] + col_w[c] * 0.04,
                            y - row_h * 0.55, txt,
                            color=TEXT_DARK, fontsize=8.8,
                            va="center", ha="left")
                y -= row_h
            return y - 0.010

        # Estado mutable de página actual durante el render
        _state = {"fig": None, "ax": None, "title": "", "color": SECTION_COLOR}

        def _current_ax():
            return _state["ax"]

        def _new_section_page(title, color, *, continuation=False):
            head = f"{title} (cont.)" if continuation else title
            fig, ax = _open_page(head, color)
            _state["fig"], _state["ax"] = fig, ax

        with PdfPages(pdf_path) as pdf:
            # — Portada —
            fig = _PdfFigure(figsize=(8.27, 11.69), dpi=100, facecolor="white")
            ax = fig.add_subplot(111); ax.axis("off")
            ax.set_xlim(0, 1); ax.set_ylim(0, 1)
            ax.add_patch(Rectangle((0.0, 0.78), 1.0, 0.16,
                                   facecolor=SECTION_COLOR, edgecolor="none"))
            ax.text(0.5, 0.88, "Mössbauer Fe-57", color="white",
                    fontsize=22, fontweight="bold", va="center", ha="center")
            ax.text(0.5, 0.82, "Informe de ajuste", color=ACCENT,
                    fontsize=14, va="center", ha="center")
            file_name = self.file.path.name if self.file.path else "—"
            ax.text(0.5, 0.72, file_name, color=TEXT_DARK, fontsize=12,
                    va="center", ha="center", family="monospace")
            ax.text(0.5, 0.685, datetime.now().strftime("%Y-%m-%d %H:%M"),
                    color=TEXT_MUTED, fontsize=10, va="center", ha="center")
            ax.text(0.5, 0.655, f"{APP_NAME} v{APP_VERSION} (Qt)",
                    color="#94a3b8", fontsize=9, va="center", ha="center")

            boxes: list[tuple[str, str]] = []
            fit = self.last_fit_result
            if fit is not None and fit.stats:
                st = fit.stats
                if st.get("red_chi2") is not None:
                    boxes.append(("χ² reducido", f"{st['red_chi2']:.4g}"))
                if st.get("chi2") is not None and st.get("dof") is not None:
                    boxes.append(("χ² · dof", f"{st['chi2']:.4g} · {int(st['dof'])}"))
                if st.get("aic") is not None:
                    boxes.append(("AIC", f"{st['aic']:.4g}"))
                if st.get("bic") is not None:
                    boxes.append(("BIC", f"{st['bic']:.4g}"))
            n_active = sum(1 for cp in self.components_panels if cp.enabled.isChecked())
            boxes.append(("Componentes activos", str(n_active)))
            if fit is not None:
                boxes.append(("Parámetros libres", str(len(fit.free_keys))))
                boxes.append(("Fuente σ", str(self.last_error_source)))

            cols = 2
            box_w, box_h = 0.42, 0.07
            x0, y0, gx, gy = 0.06, 0.58, 0.06, 0.025
            for i, (lbl, val) in enumerate(boxes):
                r, c = divmod(i, cols)
                x = x0 + c * (box_w + gx)
                y = y0 - r * (box_h + gy)
                ax.add_patch(Rectangle((x, y - box_h), box_w, box_h,
                                       facecolor=ZEBRA_BG,
                                       edgecolor="#cbd5e1", linewidth=1))
                ax.text(x + 0.015, y - box_h * 0.28, lbl, fontsize=9,
                        color=TEXT_MUTED, va="center", ha="left")
                ax.text(x + box_w - 0.015, y - box_h * 0.65, val, fontsize=12,
                        color=SECTION_COLOR, va="center", ha="right",
                        fontweight="bold")
            pdf.savefig(fig, bbox_inches="tight")

            # — Cuerpo: secciones ## con bloques tipados —
            sections: list[tuple[str, list[str]]] = []
            current_title: str | None = None
            current_body: list[str] = []
            for ln in md_lines:
                if ln.startswith("## "):
                    if current_title is not None:
                        sections.append((current_title, current_body))
                    current_title = ln[3:].strip()
                    current_body = []
                elif ln.startswith("# "):
                    continue
                else:
                    current_body.append(ln)
            if current_title is not None:
                sections.append((current_title, current_body))

            for title, body in sections:
                blocks = self._md_to_blocks(body)
                if not blocks:
                    continue
                _state["title"] = title
                _state["color"] = SECTION_COLOR
                _new_section_page(title, SECTION_COLOR)
                y = TOP_BODY

                def _on_break():
                    pdf.savefig(_state["fig"], bbox_inches="tight")
                    _state["color"] = SECTION_COLOR_ALT
                    _new_section_page(_state["title"], _state["color"],
                                      continuation=True)

                for kind, data in blocks:
                    ax = _state["ax"]
                    if kind == "h3":
                        if y - 0.05 < BOTTOM:
                            _on_break(); y = TOP_BODY
                        y = _render_h3(_state["ax"], data, y)
                    elif kind == "para":
                        y = _render_para(_state["ax"], data, y, _on_break)
                    elif kind == "callout":
                        y = _render_callout(_state["ax"], data, y, _on_break)
                    elif kind == "code":
                        y = _render_code(_state["ax"], data, y, _on_break)
                    elif kind == "table":
                        header, rows = data
                        y = _render_table(_state["ax"], header, rows, y,
                                          _on_break)
                pdf.savefig(_state["fig"], bbox_inches="tight")

            pdf.savefig(self.canvas.fig, bbox_inches="tight")

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
        lines = self._build_report_lines()
        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8")
            self.statusBar().showMessage(f"Informe guardado: {path}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("file.export_report"),
                                            f"{type(exc).__name__}: {exc}")
            return

        want_pdf = QtWidgets.QMessageBox.question(
            self, tr("file.export_report"),
            tr("msg.report_ask_pdf",
               default="Informe Markdown guardado. ¿Generar también un PDF?"),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes)
        if want_pdf != QtWidgets.QMessageBox.Yes:
            return
        try:
            pdf_path = Path(path).with_suffix(".pdf")
            self._render_pdf_report(pdf_path, lines)
            self.statusBar().showMessage(f"Informe + PDF guardados: {path}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, tr("file.export_report"),
                f"No se pudo generar el PDF: {type(exc).__name__}: {exc}")

    @staticmethod
    def _help_format_content(content: str) -> str:
        """Convierte el texto plano de un capítulo de ayuda en HTML enriquecido.

        Reconoce subtítulos en una línea acabada en dos puntos (``X:``) seguidos
        de bloque sangrado, viñetas (``•``, ``-`` o ``  número.``) y aplica
        ``**bold**``, ``*italic*`` y `` `code` `` inline. También resalta en
        **negrita** automáticamente las etiquetas de menús y submenús del
        programa (Archivo, Cargar..., Ajustar, etc.) para que el lector
        identifique a qué control se refiere cada explicación.
        """
        import re
        text = content.strip("\n")
        menu_pattern = MossbauerQtWindow._help_menu_pattern()

        def _inline(s: str) -> str:
            s = html.escape(s)
            s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
            s = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", s)
            s = re.sub(r"`([^`]+)`",
                       r"<code style='background:#f1f5f9;color:#0f172a;"
                       r"padding:1px 4px;border-radius:3px;'>\1</code>", s)
            if menu_pattern is not None:
                s = menu_pattern.sub(
                    lambda m: (
                        m.group(0)
                        if (m.string[max(0, m.start() - 4):m.start()].endswith(("<b>", "<i>"))
                            or "<b>" in m.group(0)
                            or "<i>" in m.group(0))
                        else f"<b>{m.group(0)}</b>"
                    ),
                    s,
                )
            return s

        parts: list[str] = []
        lines = text.split("\n")
        i, n = 0, len(lines)

        def _indent(raw_line: str) -> int:
            return len(raw_line) - len(raw_line.lstrip(" \t"))

        def _is_bullet(raw_line: str) -> bool:
            return (
                re.match(r"^\s*[•\-]\s+", raw_line) is not None
                or re.match(r"^\s*\d+\.\s+", raw_line) is not None
            )

        def _is_menu_item_start(pos: int) -> bool:
            """Detecta bloques sangrados de tipo ``Submenú`` + ``Campo: texto``.

            Gran parte de la ayuda replica la estructura de los menús como::

                Cargar...
                  Qué es: ...
                  Para qué sirve: ...

            Si se tratan como párrafos normales, Qt los fusiona en una línea
            larga. Este detector conserva la jerarquía visual del texto fuente.
            """
            if pos + 1 >= n:
                return False
            current = lines[pos]
            stripped_current = current.strip()
            if (
                not stripped_current
                or stripped_current.endswith(":")
                or _is_bullet(current)
                or _indent(current) == 0
                or len(stripped_current) > 90
            ):
                return False
            nxt = lines[pos + 1]
            stripped_next = nxt.strip()
            if not stripped_next or _indent(nxt) <= _indent(current):
                return False
            return re.match(r"^[^:]{2,36}:\s+.+", stripped_next) is not None

        def _render_menu_item(pos: int) -> tuple[str, int]:
            base_indent = _indent(lines[pos])
            title = lines[pos].strip()
            rows: list[tuple[str, str]] = []
            j = pos + 1
            while j < n:
                raw_line = lines[j]
                stripped_line = raw_line.strip()
                if not stripped_line:
                    break
                if _indent(raw_line) <= base_indent:
                    break
                match = re.match(r"^([^:]{2,36}):\s*(.*)$", stripped_line)
                if match:
                    rows.append((match.group(1).strip(), match.group(2).strip()))
                elif rows:
                    key, value = rows[-1]
                    rows[-1] = (key, f"{value} {stripped_line}".strip())
                else:
                    rows.append(("", stripped_line))
                j += 1
            if rows:
                body = "".join(
                    "<li style='margin:3px 0;'>"
                    + (f"<b>{_inline(key)}:</b> " if key else "")
                    + f"{_inline(value)}</li>"
                    for key, value in rows
                )
            else:
                body = ""
            html_block = (
                "<div style='margin:10px 0 12px 18px;padding:10px 12px;"
                "border-left:4px solid #38bdf8;background:#f8fafc;"
                "border-radius:6px;'>"
                f"<h5 style='color:#075985;font-size:1.02em;margin:0 0 6px 0;'>"
                f"{_inline(title)}</h5>"
                "<ul style='margin:0 0 0 20px;padding:0;line-height:1.45;'>"
                f"{body}</ul></div>"
            )
            return html_block, j

        while i < n:
            raw = lines[i]
            stripped = raw.strip()
            # Línea en blanco → separador de párrafos
            if not stripped:
                parts.append("")
                i += 1
                continue
            # Bloque de submenú/opción con campos descriptivos. Debe evaluarse
            # antes de los párrafos para no perder la sangría del help.json.
            if _is_menu_item_start(i):
                html_block, i = _render_menu_item(i)
                parts.append(html_block)
                continue
            # Subtítulo de tipo "Algo:" seguido de bloque sangrado o líneas
            if (
                stripped.endswith(":")
                and not stripped.startswith(("-", "•"))
                and len(stripped) <= 80
                and (i + 1 >= n or not lines[i + 1].strip()
                     or lines[i + 1].startswith((" ", "\t")))
            ):
                parts.append(
                    f"<h4 style='color:#0f766e;margin:14px 0 4px 0;'>"
                    f"{_inline(stripped[:-1])}</h4>"
                )
                i += 1
                continue
            # Viñetas y numeración con sangría
            if _is_bullet(raw):
                numbered = re.match(r"^\s*\d+\.\s+", raw) is not None
                tag = "ol" if numbered else "ul"
                items: list[str] = []
                while i < n and _is_bullet(lines[i]):
                    body = re.sub(r"^\s*(?:[•\-]\s+|\d+\.\s+)", "", lines[i])
                    items.append(f"<li>{_inline(body)}</li>")
                    i += 1
                parts.append(
                    f"<{tag} style='margin:4px 0 8px 22px;padding:0;"
                    "line-height:1.5;'>" + "".join(items) + f"</{tag}>"
                )
                continue
            # Párrafo normal: junta líneas hasta separador o cambio de tipo
            buf = [raw]
            i += 1
            while i < n and lines[i].strip() and not (
                _is_bullet(lines[i])
                or _is_menu_item_start(i)
                or lines[i].strip().endswith(":")
            ):
                buf.append(lines[i])
                i += 1
            joined = _inline(" ".join(s.strip() for s in buf))
            parts.append(f"<p style='margin:6px 0;line-height:1.55;'>{joined}</p>")
        return "\n".join(p for p in parts if p)

    @staticmethod
    def _help_menu_pattern() -> "re.Pattern | None":
        """Construye un patrón con las etiquetas de menús/submenús del programa.

        Memoizado por idioma: lee los valores de las claves ``menu.*``,
        ``file.*``, ``fit.*``, ``options.*``, ``view.*`` y un subconjunto
        seguro de ``help.*`` del catálogo actual y los compone como un único
        regex case-insensitive (los términos más largos antes para que
        ``Ajustar Vmax con el patrón`` gane a ``Ajustar``).
        """
        import re
        from mossbauer_i18n import CATALOGS, get_language
        lang = get_language()
        cache = getattr(MossbauerQtWindow, "_help_menu_pattern_cache", {})
        if lang in cache:
            return cache[lang]
        catalog = CATALOGS.get(lang, {})
        prefixes = ("menu.", "file.", "fit.", "options.", "view.")
        help_allow = {
            "help.open", "help.about", "help.changelog",
            "help.check_updates", "help.configure_updates",
        }
        # Vocabulario común que jamás queremos en negrita aunque aparezca
        # como traducción (por ejemplo "Idioma" o "Lengua", "Tema", "sí/no").
        blacklist = {
            tr("yes", default="sí"), tr("no", default="no"),
            tr("menu.language", default="Idioma"),
            tr("help.language_label", default="Idioma:").rstrip(":"),
        }
        terms: set[str] = set()
        for k, v in catalog.items():
            if not isinstance(v, str):
                continue
            if not (k.startswith(prefixes) or k in help_allow):
                continue
            s = v.strip()
            # Saltar valores con placeholders ({...}) o demasiado largos
            if "{" in s or "}" in s or len(s) > 60 or len(s) < 3:
                continue
            if s in blacklist:
                continue
            # Una palabra de longitud < 4 suele ser demasiado genérica
            if " " not in s and len(s) < 4:
                continue
            terms.add(s)
            # Para etiquetas de varias palabras, añade también la versión sin
            # elipsis/dos-puntos para capturar referencias en el texto que
            # omiten esos signos ("Restricciones entre parámetros").
            stripped = s.rstrip(" .…:")
            if stripped != s and stripped.count(" ") >= 1 and len(stripped) >= 6:
                terms.add(stripped)
        if not terms:
            cache[lang] = None
            MossbauerQtWindow._help_menu_pattern_cache = cache
            return None
        # Ordena por longitud descendente y construye alternancia
        ordered = sorted(terms, key=lambda t: (-len(t), t))
        pat = "|".join(re.escape(t) for t in ordered)
        # Case-sensitive a propósito: las etiquetas de menú están capitalizadas
        # (Archivo, Ajustar, Opciones), así que evitamos resaltar el sustantivo
        # genérico en minúsculas ("ajuste", "archivo"…). El borde por delante
        # es blando porque varias etiquetas acaban en "…", "..." o ":".
        compiled = re.compile(rf"(?<![\w&]){pat}")
        cache[lang] = compiled
        MossbauerQtWindow._help_menu_pattern_cache = cache
        return compiled

    @staticmethod
    def _help_layout() -> list[tuple[str, list[int]]]:
        """Distribución jerárquica de la ayuda según los menús del programa.

        Refleja la estructura real de la barra de menús (Archivo, Ajuste,
        Opciones, Vista, Ayuda) más grupos temáticos para los conceptos
        físicos y las distribuciones P(BHF) / P(ΔEQ). Los índices son los
        del orden canónico de ``help.json`` (idéntico en todos los idiomas
        empaquetados con el programa, ver ``locales/<code>/help.json``).
        """
        return [
            (tr("help.tree_overview", default="🚀 Visión general"),
             [0, 22]),
            (tr("help.tree_file",     default="📁 Menú Archivo"),
             [1, 7, 18]),
            (tr("help.tree_fit",      default="🧮 Menú Ajuste"),
             [2, 17, 19, 24]),
            (tr("help.tree_options",  default="🎛️ Menú Opciones"),
             [3, 10]),
            (tr("help.tree_view",     default="👁️ Menú Vista"),
             [4]),
            (tr("help.tree_help",     default="❓ Menú Ayuda"),
             [5, 23, 25]),
            (tr("help.tree_physics",  default="🔬 Conceptos físicos"),
             [6, 9, 8, 20, 21]),
            (tr("help.tree_distrib",
                default="📊 Distribuciones P(BHF) / P(ΔEQ)"),
             [11, 12, 13, 14, 15, 16]),
        ]

    def on_help(self) -> None:
        if self._help_dialog is not None:
            self._help_dialog.show()
            self._help_dialog.raise_()
            self._help_dialog.activateWindow()
            return

        sections = get_help_sections(
            voigt_sigma=self.calib.voigt_sigma.value(),
            settings_path=SETTINGS_PATH,
            lang=get_language(),
        )
        dlg = QtWidgets.QDialog(self)
        dlg.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        dlg.setModal(False)
        dlg.setWindowModality(QtCore.Qt.NonModal)
        dlg.destroyed.connect(lambda _obj=None: setattr(self, "_help_dialog", None))
        self._help_dialog = dlg
        dlg.setWindowTitle(tr("help.window_title"))
        dlg.resize(1180, 760)
        v = QtWidgets.QVBoxLayout(dlg)
        v.setContentsMargins(14, 12, 14, 10)
        v.setSpacing(8)
        header = QtWidgets.QLabel(f"<h2 style='margin:0;'>{tr('help.header_title')}</h2>")
        header.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(header)

        # Buscador en la cabecera
        search_row = QtWidgets.QHBoxLayout()
        search_lbl = QtWidgets.QLabel(tr("help.search_label", default="🔍 Buscar:"))
        search_edit = QtWidgets.QLineEdit()
        search_edit.setPlaceholderText(
            tr("help.search_placeholder",
               default="Filtra los capítulos y resalta los aciertos…")
        )
        search_count = QtWidgets.QLabel("")
        search_count.setStyleSheet("color:#475569;")
        search_row.addWidget(search_lbl)
        search_row.addWidget(search_edit, stretch=1)
        search_row.addWidget(search_count)
        v.addLayout(search_row)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        tree = QtWidgets.QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setIndentation(18)
        tree.setRootIsDecorated(True)
        tree.setUniformRowHeights(False)
        tree.setAnimated(True)
        tree.setStyleSheet(
            "QTreeWidget { font-size: 10.5pt; background:#f8fafc;"
            " border:1px solid #e2e8f0; border-radius:6px; padding:4px; }"
            "QTreeWidget::item { padding: 4px 4px; }"
            "QTreeWidget::item:selected { background:#dbeafe; color:#1e40af; }"
        )
        tree.setMinimumWidth(320)
        tree.setMaximumWidth(380)

        # Construye el árbol a partir de la distribución por menús.
        group_items: list[QtWidgets.QTreeWidgetItem] = []
        leaves: list[QtWidgets.QTreeWidgetItem] = []
        seen: set[int] = set()
        n_total = len(sections)
        for grp_label, indices in self._help_layout():
            top = QtWidgets.QTreeWidgetItem(tree, [grp_label])
            font = top.font(0)
            font.setBold(True)
            font.setPointSizeF(font.pointSizeF() + 0.5)
            top.setFont(0, font)
            top.setForeground(0, QtGui.QBrush(QtGui.QColor("#1e3a8a")))
            # Las cabeceras no son seleccionables (solo los capítulos).
            top.setFlags(top.flags() & ~QtCore.Qt.ItemIsSelectable)
            for idx in indices:
                if 0 <= idx < n_total and idx not in seen:
                    seen.add(idx)
                    leaf = QtWidgets.QTreeWidgetItem(top, [sections[idx][0]])
                    leaf.setData(0, QtCore.Qt.UserRole, idx)
                    leaves.append(leaf)
            group_items.append(top)
        # Capítulos no contemplados por la distribución (defensivo) → "Otros".
        unassigned = [i for i in range(n_total) if i not in seen]
        if unassigned:
            other = QtWidgets.QTreeWidgetItem(
                tree, [tr("help.tree_other", default="📚 Otros")]
            )
            font = other.font(0); font.setBold(True); other.setFont(0, font)
            other.setFlags(other.flags() & ~QtCore.Qt.ItemIsSelectable)
            for idx in unassigned:
                leaf = QtWidgets.QTreeWidgetItem(other, [sections[idx][0]])
                leaf.setData(0, QtCore.Qt.UserRole, idx)
                leaves.append(leaf)
            group_items.append(other)
        tree.expandAll()
        split.addWidget(tree)

        text_w = QtWidgets.QTextBrowser()
        text_w.setOpenExternalLinks(True)
        text_w.setStyleSheet(
            "QTextBrowser { font-family: -apple-system, Segoe UI, sans-serif;"
            " font-size: 10.8pt; padding: 14px 18px;"
            " border:1px solid #e2e8f0; border-radius:6px; background:white; }"
        )
        split.addWidget(text_w)
        split.setSizes([340, 840])
        v.addWidget(split, stretch=1)

        def _render(idx: int, highlight: str = "") -> None:
            if not (0 <= idx < len(sections)):
                return
            title, heading, content = sections[idx]
            body = self._help_format_content(content)
            css = (
                "h2{color:#1e40af;margin:0 0 4px 0;}"
                "h3{color:#475569;margin:0 0 14px 0;font-weight:500;"
                "border-bottom:1px solid #e2e8f0;padding-bottom:6px;}"
                "h4{color:#0f766e;margin:14px 0 4px 0;}"
                "p,li{color:#1f2937;}"
                "mark{background:#fde68a;color:#7c2d12;border-radius:2px;padding:0 1px;}"
            )
            html_doc = (
                f"<style>{css}</style>"
                f"<h2>{html.escape(title)}</h2>"
                f"<h3>{html.escape(heading)}</h3>{body}"
            )
            if highlight:
                import re
                pat = re.compile(re.escape(highlight), re.IGNORECASE)

                def _highlight_outside_tags(s: str) -> str:
                    out, buf = [], []
                    i, n = 0, len(s)
                    while i < n:
                        ch = s[i]
                        if ch == "<":
                            if buf:
                                out.append(pat.sub(
                                    lambda m: f"<mark>{m.group(0)}</mark>",
                                    "".join(buf)))
                                buf = []
                            j = s.find(">", i)
                            if j == -1:
                                out.append(s[i:]); break
                            out.append(s[i:j + 1]); i = j + 1
                        else:
                            buf.append(ch); i += 1
                    if buf:
                        out.append(pat.sub(
                            lambda m: f"<mark>{m.group(0)}</mark>",
                            "".join(buf)))
                    return "".join(out)

                html_doc = _highlight_outside_tags(html_doc)
            text_w.setHtml(html_doc)

        def _on_tree(curr: QtWidgets.QTreeWidgetItem, _prev) -> None:
            if curr is None:
                return
            data = curr.data(0, QtCore.Qt.UserRole)
            if data is not None:
                _render(int(data), search_edit.text().strip())
            elif curr.childCount() > 0:
                # Si el usuario pulsa una cabecera, mostramos su primer capítulo
                child = curr.child(0)
                tree.setCurrentItem(child)

        tree.currentItemChanged.connect(_on_tree)
        # Selecciona el primer capítulo asignado al primer grupo.
        if leaves:
            tree.setCurrentItem(leaves[0])

        def _apply_filter() -> None:
            q = search_edit.text().strip().lower()
            visible = 0
            for grp_item in group_items:
                grp_has = False
                for ch_idx in range(grp_item.childCount()):
                    leaf = grp_item.child(ch_idx)
                    data = leaf.data(0, QtCore.Qt.UserRole)
                    if data is None:
                        continue
                    title, heading, content = sections[int(data)]
                    hay = (
                        not q
                        or q in title.lower()
                        or q in heading.lower()
                        or q in content.lower()
                    )
                    leaf.setHidden(not hay)
                    if hay:
                        visible += 1
                        grp_has = True
                grp_item.setHidden(not grp_has)
            if q:
                search_count.setText(
                    tr("help.search_count", default="{n} capítulos").format(n=visible)
                )
            else:
                search_count.setText("")
            curr = tree.currentItem()
            if curr is not None and curr.data(0, QtCore.Qt.UserRole) is not None:
                _render(int(curr.data(0, QtCore.Qt.UserRole)), q)

        search_edit.textChanged.connect(lambda _t: _apply_filter())

        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.close)
        v.addWidget(bb)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def on_about(self) -> None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("help.about_title", version=APP_VERSION))
        v = QtWidgets.QVBoxLayout(dlg); v.setContentsMargins(24, 20, 24, 20)
        _pix = _logo_pixmap(110)
        if _pix is not None:
            logo = QtWidgets.QLabel(); logo.setPixmap(_pix)
            logo.setAlignment(QtCore.Qt.AlignCenter)
            v.addWidget(logo)
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


def _logo_pixmap(size: int = 96) -> "QtGui.QPixmap | None":
    """Devuelve el logo de Fitbauer escalado a ``size`` px, o None si falta."""
    path = ROOT / "assets" / "fitbauer_icon.png"
    if not path.exists():
        return None
    pix = QtGui.QPixmap(str(path))
    if pix.isNull():
        return None
    return pix.scaled(size, size, QtCore.Qt.KeepAspectRatio,
                      QtCore.Qt.SmoothTransformation)


def _show_splash(app: QtWidgets.QApplication, duration_ms: int = 1800) -> None:
    """Splash sencillo con logo, nombre/versión; se cierra al pulsar o al expirar."""
    splash = QtWidgets.QDialog(None, QtCore.Qt.SplashScreen | QtCore.Qt.FramelessWindowHint)
    splash.setStyleSheet(
        "QDialog { background-color: #075985; }"
        "QLabel { color: white; }")
    splash.setFixedSize(440, 260)
    v = QtWidgets.QVBoxLayout(splash); v.setContentsMargins(36, 24, 36, 24)
    _pix = _logo_pixmap(96)
    if _pix is not None:
        logo = QtWidgets.QLabel(); logo.setPixmap(_pix)
        logo.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(logo)
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
    icon_png = ROOT / "assets" / "fitbauer_icon.png"
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
