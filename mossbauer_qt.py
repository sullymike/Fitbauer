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

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from mossbauer_i18n import (  # noqa: E402
    tr, get_language, set_language, available_languages,
)
from mossbauer_help import get_help_sections  # noqa: E402
from core.data_io import SETTINGS_PATH  # noqa: E402
from core.constants import APP_VERSION, APP_NAME, SEXTET_PARAM_NAMES  # noqa: E402
from core.folding import (  # noqa: E402
    read_ws5_counts, find_best_integer_or_half_center, fold_integer_or_half,
)
from core.fit_engine import (  # noqa: E402
    Component, FitState, fit_discrete, model_from_values,
)
from core.profile_likelihood import asymmetric_intervals  # noqa: E402
from core.plot_styles import get_style, apply_rc  # noqa: E402
from core.batch_fit import extract_metadata, write_results_csv, collect_trend_data  # noqa: E402
from mossbauer_distribution import (  # noqa: E402
    fit_bhf_distribution, fit_hyperfine_distribution, scan_alpha,
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
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(8)
        self.label = QtWidgets.QLabel(label)
        self.label.setMinimumWidth(120)
        self.spin = QtWidgets.QDoubleSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(decimals)
        self.spin.setValue(value)
        self.spin.setMinimumWidth(110)
        h.addWidget(self.label)
        h.addStretch(1)
        h.addWidget(self.spin)
        self.fixed_cb = None
        if with_fixed:
            self.fixed_cb = QtWidgets.QCheckBox(tr("checkbox.fixed"))
            h.addWidget(self.fixed_cb)
            self.fixed_cb.toggled.connect(self.fixedChanged)
        self.spin.valueChanged.connect(self.valueChanged)

    def value(self) -> float:
        return float(self.spin.value())

    def set_value(self, v: float) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(float(v))
        self.spin.blockSignals(False)

    def is_fixed(self) -> bool:
        return bool(self.fixed_cb.isChecked()) if self.fixed_cb is not None else False

    def set_fixed(self, b: bool) -> None:
        if self.fixed_cb is not None:
            self.fixed_cb.setChecked(bool(b))


# ─────────────────────────────────────────────────────────────────────────
#  Paneles
# ─────────────────────────────────────────────────────────────────────────


class CalibrationPanel(QtWidgets.QGroupBox):
    """vmax / center / baseline / slope / voigt_sigma + fit-velocity/center/sigma."""

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
        self.voigt_sigma.spin.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.voigt_sigma.spin.customContextMenuRequested.connect(self._show_sigma_menu)
        self.line_profile = "Lorentziana"
        self.fit_sigma = QtWidgets.QCheckBox(tr("checkbox.fit_sigma"))

        for w in (self.vmax, self.fit_velocity, self.center, self.fit_center,
                  self.baseline, self.slope, self.voigt_sigma, self.fit_sigma):
            v.addWidget(w)
        v.addStretch(1)

        for w in (self.vmax, self.center, self.baseline, self.slope, self.voigt_sigma):
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())
            w.fixedChanged.connect(lambda *_: self.paramChanged.emit())
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
        menu.exec(self.voigt_sigma.spin.mapToGlobal(pos))

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
                     "depth", "int1", "int2", "int3"},
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

        specs = [
            ("delta",  tr("slider.s_delta"),  -0.11, -2.0, 3.0, 0.001, 4),
            ("quad",   tr("slider.s_quad"),    0.00, -4.0, 4.0, 0.001, 4),
            ("bhf",    tr("slider.s_bhf"),    33.00,  0.0, 60.0, 0.01, 3),
            ("gamma1", tr("slider.s_gamma1"),  0.14, 0.03, 2.0, 0.001, 4),
            ("gamma2", tr("slider.s_gamma2"),  1.00,  0.2, 3.0, 0.01,  3),
            ("gamma3", tr("slider.s_gamma3"),  1.00,  0.2, 3.0, 0.01,  3),
            ("depth",  tr("slider.s_depth"),   0.013, 0.0, 0.30, 0.0001, 5),
            ("int1",   tr("slider.s_int1"),    3.0,   0.0, 9.0, 0.05,  3),
            ("int2",   tr("slider.s_int2"),    2.0,   0.0, 6.0, 0.05,  3),
            ("int3",   tr("slider.s_int3"),    1.0,   0.0, 3.0, 0.05,  3),
        ]
        self.params: dict[str, ParamControl] = {}
        for name, label, val, lo, hi, step, dec in specs:
            ctl = ParamControl(label, val, lo, hi, step, dec)
            v.addWidget(ctl)
            self.params[name] = ctl
            ctl.valueChanged.connect(lambda *_: self.paramChanged.emit())
            ctl.fixedChanged.connect(lambda *_: self.paramChanged.emit())
        self.enabled.toggled.connect(lambda *_: self.paramChanged.emit())
        self.type_combo.currentTextChanged.connect(self._on_type_changed)

        # Fijos típicos para α-Fe (intensidades + gammas relativas + quad).
        for k in ("int1", "int2", "int3", "gamma2", "gamma3", "quad"):
            self.params[k].set_fixed(True)
        v.addStretch(1)
        self._on_type_changed(self.type_combo.currentText())

    @property
    def kind(self) -> str:
        return self.type_combo.currentText()

    def _on_type_changed(self, kind: str) -> None:
        used = self._USED_BY.get(kind, set())
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
    """Panel de resultados: estadísticos + parámetros libres con errores."""

    def __init__(self, parent=None):
        super().__init__(tr("controls.info_box"), parent)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        self.text = QtWidgets.QTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(120)
        self.text.setStyleSheet("QTextEdit { font-family: monospace; font-size: 10pt; }")
        v.addWidget(self.text)

    def show_result(self, result) -> None:
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
            lines.append("Correlaciones altas (|r| ≥ 0.95):")
            for p in pairs[:6]:
                lines.append(f"  {p['param1']} ↔ {p['param2']}: r={float(p['corr']):.3f}")
        self.text.setPlainText("\n".join(lines) or "—")


# ─────────────────────────────────────────────────────────────────────────
#  Canvas
# ─────────────────────────────────────────────────────────────────────────


class SpectrumCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(7.0, 5.0), dpi=100, facecolor="white")
        super().__init__(self.fig)
        self.setParent(parent)
        gs = self.fig.add_gridspec(2, 1, height_ratios=[4.6, 1.0], hspace=0.08)
        self.ax = self.fig.add_subplot(gs[0])
        self.ax_res = self.fig.add_subplot(gs[1], sharex=self.ax)
        self.ax.set_ylabel(tr("plot.transmission_ylabel"))
        self.ax_res.set_xlabel(tr("plot.velocity_xlabel"))
        self.ax_res.set_ylabel(tr("plot.residual_ylabel"))
        self.show_no_file()

    def show_no_file(self) -> None:
        self.ax.clear(); self.ax_res.clear()
        self.ax.text(0.5, 0.5, tr("plot.no_file"),
                     transform=self.ax.transAxes, ha="center", va="center",
                     fontsize=13, color="#075985", fontweight="bold")
        for a in (self.ax, self.ax_res):
            a.set_xticks([]); a.set_yticks([])
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
        self.ax.clear(); self.ax_res.clear()
        self.ax.set_facecolor(s["ax_bg"])
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
            if show_residual:
                self.ax_res.axhline(0, color=s["res_zero"], lw=0.9, alpha=0.9)
                self.ax_res.fill_between(v, residual, 0, color=s["res_fill"],
                                         alpha=s.get("res_fill_alpha", 0.22))
                self.ax_res.plot(v, residual, "-", color=s["res_line"],
                                 lw=s.get("res_line_lw", 1.0))
                lim = max(float(np.nanmax(np.abs(residual))) * 1.18, 1e-6)
                self.ax_res.set_ylim(-lim, lim)
                self.ax.tick_params(labelbottom=False)
            else:
                self.ax_res.set_visible(False)
        if not show_residual:
            self.ax_res.set_visible(False)
        else:
            self.ax_res.set_visible(True)
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
    """Panel para modo distribución P(BHF) (Hesse-Rübartsch)."""

    paramChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(tr("tab.distribution_bhf"), parent)
        v = QtWidgets.QVBoxLayout(self)
        v.setSpacing(2)

        self.delta = ParamControl(tr("slider.dist_delta"), 0.0, -2.5, 2.5, 0.001, 4)
        self.quad  = ParamControl(tr("slider.dist_quad"),  0.0, -4.0, 4.0, 0.001, 4)
        self.gamma = ParamControl(tr("slider.dist_gamma"), 0.18, 0.03, 1.0, 0.001, 4)
        self.bmin  = ParamControl(tr("slider.dist_bmin_bhf"), 0.0,  0.0, 60.0, 0.1, 2, with_fixed=False)
        self.bmax  = ParamControl(tr("slider.dist_bmax_bhf"), 50.0, 1.0, 60.0, 0.1, 2, with_fixed=False)
        self.nbins = ParamControl(tr("slider.dist_nbins"), 50.0, 10.0, 100.0, 1.0, 0, with_fixed=False)
        self.log_alpha = ParamControl(tr("slider.dist_log_alpha"), -2.0, -8.0, 4.0, 0.1, 2, with_fixed=False)

        for w in (self.delta, self.quad, self.gamma, self.bmin, self.bmax,
                  self.nbins, self.log_alpha):
            v.addWidget(w)
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())
        v.addStretch(1)


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
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}  (Qt)")
        self.resize(1400, 900)
        self.file = FileState()
        self._building = False
        self.plot_style_name = "modern"
        self.constraints: list[dict] = []
        self._load_settings()
        self._build_ui()
        self._build_menubar()
        self.statusBar().showMessage(tr("plot.no_file"))

    # ── Construcción de la UI ────────────────────────────────────────────
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self); self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central); layout.setContentsMargins(4, 4, 4, 4)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal); layout.addWidget(splitter)

        # ── Columna izquierda: file info + calibración + sextete ─────────
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left); lv.setContentsMargins(6, 6, 6, 6); lv.setSpacing(8)

        self.file_box = QtWidgets.QGroupBox(tr("controls.file_box"))
        fb = QtWidgets.QVBoxLayout(self.file_box)
        self.file_label = QtWidgets.QLabel("—"); self.file_label.setWordWrap(True)
        fb.addWidget(self.file_label)
        lv.addWidget(self.file_box)

        # Selector de modo (discreto / P(BHF)).
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
        lv.addLayout(mode_row)

        self.calib = CalibrationPanel()
        lv.addWidget(self.calib)

        # Componentes 1, 2 y 3 en pestañas (solo el 1 activo por defecto).
        self.comp_tabs = QtWidgets.QTabWidget()
        self.components_panels: list[ComponentPanel] = []
        for i in (1, 2, 3):
            cp = ComponentPanel(idx=i)
            self.components_panels.append(cp)
            self.comp_tabs.addTab(cp, tr("tab.component", idx=i))
        lv.addWidget(self.comp_tabs)

        # Panel de distribución (oculto en modo discreto).
        self.dist_panel = DistributionPanel()
        self.dist_panel.setVisible(False)
        self.dist_panel.paramChanged.connect(self._refresh_plot)
        lv.addWidget(self.dist_panel)
        lv.addStretch(1)

        scroll = QtWidgets.QScrollArea(); scroll.setWidget(left); scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(380); scroll.setMaximumWidth(460)
        splitter.addWidget(scroll)

        # ── Centro: canvas + toolbar + panel de info ─────────────────────
        center = QtWidgets.QWidget()
        cv = QtWidgets.QVBoxLayout(center); cv.setContentsMargins(0, 0, 0, 0)
        self.canvas = SpectrumCanvas(center)
        self.toolbar = NavigationToolbar(self.canvas, center)
        self.info_panel = InfoPanel()
        cv.addWidget(self.toolbar); cv.addWidget(self.canvas, stretch=1)
        cv.addWidget(self.info_panel)
        splitter.addWidget(center)

        splitter.setSizes([430, 1000])

        # Conectar señales de cambio para refrescar el plot en vivo
        self.calib.paramChanged.connect(self._refresh_plot)
        for cp in self.components_panels:
            cp.paramChanged.connect(self._refresh_plot)

    # ── Menubar ──────────────────────────────────────────────────────────
    def _build_menubar(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu(tr("menu.file"))
        act_open = QtGui.QAction(tr("file.open"), self)
        act_open.setShortcut(QtGui.QKeySequence.Open)
        act_open.triggered.connect(self.on_open)
        file_menu.addAction(act_open)
        file_menu.addSeparator()
        self.act_save_fit = QtGui.QAction(tr("file.save_fit"), self)
        self.act_save_fit.triggered.connect(self.on_save_fit)
        self.act_save_fit.setEnabled(False)
        file_menu.addAction(self.act_save_fit)
        self.act_export_report = QtGui.QAction(tr("file.export_report"), self)
        self.act_export_report.triggered.connect(self.on_export_report)
        self.act_export_report.setEnabled(False)
        file_menu.addAction(self.act_export_report)
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

        fit_menu = mb.addMenu(tr("menu.fit"))
        self.act_find_center = QtGui.QAction(tr("fit.find_center"), self)
        self.act_find_center.triggered.connect(self.on_find_center)
        self.act_find_center.setEnabled(False)
        fit_menu.addAction(self.act_find_center)
        self.act_init = QtGui.QAction(tr("fit.init_from_minima"), self)
        self.act_init.triggered.connect(self.on_init_from_minima)
        self.act_init.setEnabled(False)
        fit_menu.addAction(self.act_init)
        self.act_fit = QtGui.QAction(tr("fit.run"), self)
        self.act_fit.setShortcut("Ctrl+R")
        self.act_fit.triggered.connect(self.on_fit)
        self.act_fit.setEnabled(False)
        fit_menu.addAction(self.act_fit)
        self.act_profile = QtGui.QAction(tr("fit.profile_likelihood"), self)
        self.act_profile.triggered.connect(self.on_profile_likelihood)
        self.act_profile.setEnabled(False)
        fit_menu.addAction(self.act_profile)
        self.act_batch = QtGui.QAction(tr("fit.batch_fit"), self)
        self.act_batch.triggered.connect(self.on_batch_fit)
        fit_menu.addAction(self.act_batch)
        self.act_bootstrap = QtGui.QAction(tr("fit.bootstrap"), self)
        self.act_bootstrap.triggered.connect(self.on_bootstrap)
        self.act_bootstrap.setEnabled(False)
        fit_menu.addAction(self.act_bootstrap)
        self.act_lcurve = QtGui.QAction(tr("bhf.lcurve_alpha"), self)
        self.act_lcurve.triggered.connect(self.on_lcurve)
        self.act_lcurve.setEnabled(False)
        fit_menu.addAction(self.act_lcurve)
        fit_menu.addSeparator()
        act_fix_all = QtGui.QAction(tr("fit.fix_all"), self)
        act_fix_all.triggered.connect(lambda: self._set_all_fixed(True))
        fit_menu.addAction(act_fix_all)
        act_free_all = QtGui.QAction(tr("fit.free_all"), self)
        act_free_all.triggered.connect(lambda: self._set_all_fixed(False))
        fit_menu.addAction(act_free_all)

        view_menu = mb.addMenu(tr("menu.view"))
        self.act_show_residual = QtGui.QAction(tr("options.show_residual"), self,
                                                checkable=True, checked=True)
        self.act_show_residual.toggled.connect(lambda _: self._refresh_plot())
        view_menu.addAction(self.act_show_residual)
        self.act_show_legend = QtGui.QAction(tr("options.show_legend"), self,
                                              checkable=True, checked=True)
        self.act_show_legend.toggled.connect(lambda _: self._refresh_plot())
        view_menu.addAction(self.act_show_legend)
        view_menu.addSeparator()
        act_constraints = QtGui.QAction(tr("options.constraints"), self)
        act_constraints.triggered.connect(self.on_constraints)
        view_menu.addAction(act_constraints)
        act_presets = QtGui.QAction(tr("options.physical_presets"), self)
        act_presets.triggered.connect(self.on_physical_presets)
        view_menu.addAction(act_presets)
        view_menu.addSeparator()
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

        # Submenú de idioma dentro de View
        view_menu.addSeparator()
        lang_menu = view_menu.addMenu(tr("menu.language"))
        self.lang_action_group = QtGui.QActionGroup(self)
        current_lang = get_language()
        for code, name in available_languages().items():
            act = QtGui.QAction(name, self, checkable=True)
            act.setChecked(code == current_lang)
            act.triggered.connect(lambda _checked=False, c=code: self._set_language(c))
            lang_menu.addAction(act)
            self.lang_action_group.addAction(act)

        help_menu = mb.addMenu(tr("menu.help"))
        act_help = QtGui.QAction(tr("help.open"), self)
        act_help.setShortcut("F1")
        act_help.triggered.connect(self.on_help)
        help_menu.addAction(act_help)
        act_changelog = QtGui.QAction(tr("help.changelog"), self)
        act_changelog.triggered.connect(self.on_changelog)
        help_menu.addAction(act_changelog)
        help_menu.addSeparator()
        act_about = QtGui.QAction(tr("help.about"), self)
        act_about.triggered.connect(self.on_about)
        help_menu.addAction(act_about)

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

    def _set_plot_style(self, name: str) -> None:
        self.plot_style_name = name
        apply_rc(name)
        self._save_settings()
        self._refresh_plot()

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
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps(current, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception:
            pass

    # ── Cambio de modo ───────────────────────────────────────────────────
    def _on_mode_changed(self, idx: int) -> None:
        is_dist = (idx in (1, 2))
        is_deq = (idx == 2)
        self.comp_tabs.setVisible(not is_dist)
        self.dist_panel.setVisible(is_dist)
        # Etiquetas según variable distribuida
        if is_dist:
            if is_deq:
                self.dist_panel.bmin.label.setText(tr("slider.dist_bmin_quad"))
                self.dist_panel.bmax.label.setText(tr("slider.dist_bmax_quad"))
            else:
                self.dist_panel.bmin.label.setText(tr("slider.dist_bmin_bhf"))
                self.dist_panel.bmax.label.setText(tr("slider.dist_bmax_bhf"))
        self._refresh_plot()

    @property
    def is_distribution_mode(self) -> bool:
        return self.mode_combo.currentIndex() in (1, 2)

    @property
    def dist_variable(self) -> str:
        return "quad" if self.mode_combo.currentIndex() == 2 else "bhf"

    # ── Helpers UI ───────────────────────────────────────────────────────
    def _set_all_fixed(self, value: bool) -> None:
        self._building = True
        for cp in self.components_panels:
            for ctl in cp.params.values():
                ctl.set_fixed(value)
        self._building = False
        self._refresh_plot()

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
        }
        fixed: dict[str, bool] = {k: False for k in values}
        fixed.update({k: True for k in ("vmax", "center")})
        bounds = {
            "baseline": (0.70, 1.30), "slope": (-0.005, 0.005),
            "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0),
        }
        param_bounds = (
            ("delta", (-2.0, 3.0)), ("quad", (-4.0, 4.0)),
            ("bhf", (0.0, 60.0)), ("gamma1", (0.03, 2.0)),
            ("gamma2", (0.2, 3.0)), ("gamma3", (0.2, 3.0)),
            ("depth", (0.0, 0.30)), ("int1", (0.0, 9.0)),
            ("int2", (0.0, 6.0)), ("int3", (0.0, 3.0)),
        )
        components = []
        for cp in self.components_panels:
            values.update(cp.values_dict())
            fixed.update(cp.fixed_dict())
            for name, rng in param_bounds:
                bounds[f"s{cp.idx}_{name}"] = rng
            components.append(Component(idx=cp.idx,
                                        enabled=cp.enabled.isChecked(),
                                        kind=cp.kind))
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
        folded, _ = fold_integer_or_half(counts, center)
        norm = float(np.percentile(folded, 90)) if folded.size else 1.0
        norm = norm or 1.0
        sigma = np.sqrt(np.maximum(folded / 2.0, 1.0)) / norm
        y = folded / norm
        v = np.linspace(-self.calib.vmax.value(), self.calib.vmax.value(), folded.size)
        self.file = FileState(path=path, counts=counts, folded=folded, sigma=sigma,
                              norm_factor=norm, center=center, velocity=v, y_data=y)
        # actualiza UI
        self.calib.center.set_value(center)
        self.file_label.setText(f"<b>{path.name}</b><br>"
                                f"{counts.size} canales · centro={center:.3f} · "
                                f"norm={norm:.4g}")
        self.act_fit.setEnabled(True)
        self.act_init.setEnabled(True)
        self.act_profile.setEnabled(True)
        self.act_find_center.setEnabled(True)
        self.act_save_fit.setEnabled(True)
        self.act_export_report.setEnabled(True)
        self.act_bootstrap.setEnabled(True)
        self.act_lcurve.setEnabled(True)
        self.statusBar().showMessage(
            f"{path.name} · {counts.size} canales · centro={center:.3f}")
        self._refresh_plot()

    def _refresh_plot(self) -> None:
        if self._building or self.file.velocity is None:
            return
        v = self.file.velocity
        y = self.file.y_data
        # recalcular velocidad si vmax cambia
        vmax = abs(self.calib.vmax.value())
        if v.size and (abs(v[-1] - vmax) > 1e-6 or abs(v[0] + vmax) > 1e-6):
            v = np.linspace(-vmax, vmax, y.size)
            self.file.velocity = v
        state = self._build_state()
        style = get_style(self.plot_style_name)
        show_res = self.act_show_residual.isChecked() if hasattr(self, "act_show_residual") else True
        show_leg = self.act_show_legend.isChecked() if hasattr(self, "act_show_legend") else True
        if state is None:
            self.canvas.render(v, y, style=style,
                               show_residual=show_res, show_legend=show_leg)
            return
        try:
            model = model_from_values(v, state.values, state.components)
        except Exception:
            self.canvas.render(v, y, style=style,
                               show_residual=show_res, show_legend=show_leg)
            return
        # Solo dibujar componentes individuales si hay más de uno activo.
        comps = []
        enabled = [c for c in state.components if c.enabled]
        if len(enabled) >= 2:
            for comp in enabled:
                only_this = model_from_values(v, state.values, [comp])
                comps.append((comp.idx, comp.kind, only_this))
        self.canvas.render(v, y, model=model, components=comps, style=style,
                           show_residual=show_res, show_legend=show_leg)

    def on_fit(self) -> None:
        if self.is_distribution_mode:
            self.on_fit_distribution()
            return
        state = self._build_state()
        if state is None:
            return
        # Bloquea acción mientras corre
        self.act_fit.setEnabled(False)
        self.statusBar().showMessage("Ajustando…")
        QtWidgets.QApplication.processEvents()
        try:
            result = fit_discrete(state, progress_cb=lambda msg: self.statusBar().showMessage(msg))
        except Exception as exc:
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
        red = result.stats.get("red_chi2", float("nan"))
        chi2 = result.stats.get("chi2", float("nan"))
        self.statusBar().showMessage(
            f"χ²={chi2:.4g}  χ²red={red:.4g}  ·  {result.n_starts} arranques")
        self.info_panel.show_result(result)
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
        }
        fixed: dict[str, bool] = {}
        sextet_enabled: dict[str, bool] = {}
        component_kind: dict[str, str] = {}
        for cp in self.components_panels:
            values.update(cp.values_dict())
            fixed.update(cp.fixed_dict())
            sextet_enabled[str(cp.idx)] = bool(cp.enabled.isChecked())
            component_kind[str(cp.idx)] = cp.kind
        model_state = {
            "vars": values,
            "fixed": fixed,
            "sextet_enabled": sextet_enabled,
            "component_kind": component_kind,
            "fit_velocity": self.calib.fit_velocity.isChecked(),
            "fit_center": self.calib.fit_center.isChecked(),
            "fit_sigma": self.calib.fit_sigma.isChecked(),
            "line_profile": "Lorentziana",
            "likelihood": "gauss",
            "robust_loss": "linear",
        }
        return {
            "version": 1,
            "program": "mossbauer_qt.py",
            "file_path": str(self.file.path) if self.file.path else None,
            "file_name": self.file.path.name if self.file.path else None,
            "counts": self.file.counts.tolist() if self.file.counts is not None else None,
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
            folded, _ = fold_integer_or_half(counts, center)
            norm = float(np.percentile(folded, 90)) or 1.0
            sigma = np.sqrt(np.maximum(folded / 2.0, 1.0)) / norm
            self.file.folded = folded
            self.file.norm_factor = norm
            self.file.sigma = sigma
            self.file.center = center
            self.file.y_data = folded / norm
            self.file.velocity = np.linspace(
                -self.calib.vmax.value(), self.calib.vmax.value(), folded.size)
            self.file_label.setText(
                f"<b>{data.get('file_name') or '—'}</b><br>"
                f"{counts.size} canales (sesión)")
            self.act_fit.setEnabled(True)

        # 2. Modelo: aplicar vars / fixed / sextet_enabled / component_kind.
        state = data.get("model_state", {})
        self._building = True
        try:
            vmap = state.get("vars", {})
            self.calib.vmax.set_value(vmap.get("vmax", self.calib.vmax.value()))
            self.calib.center.set_value(vmap.get("center", self.calib.center.value()))
            self.calib.baseline.set_value(vmap.get("baseline", self.calib.baseline.value()))
            self.calib.slope.set_value(vmap.get("slope", self.calib.slope.value()))
            self.calib.voigt_sigma.set_value(vmap.get("voigt_sigma", self.calib.voigt_sigma.value()))
            for cp in self.components_panels:
                cp.apply_values(vmap)
                ki = state.get("component_kind", {}).get(str(cp.idx))
                if ki in ("Sextete", "Doblete", "Singlete"):
                    cp.type_combo.setCurrentText(ki)
                en = state.get("sextet_enabled", {}).get(str(cp.idx))
                if en is not None:
                    cp.enabled.setChecked(bool(en))
                for name, ctl in cp.params.items():
                    f = state.get("fixed", {}).get(f"s{cp.idx}_{name}")
                    if f is not None:
                        ctl.set_fixed(bool(f))
            self.calib.fit_velocity.setChecked(bool(state.get("fit_velocity", False)))
            self.calib.fit_center.setChecked(bool(state.get("fit_center", False)))
            self.calib.fit_sigma.setChecked(bool(state.get("fit_sigma", False)))
        finally:
            self._building = False
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
        try:
            if var == "quad":
                fits = [fit_hyperfine_distribution(
                    self.file.velocity, self.file.y_data, variable="quad",
                    delta=float(d.delta.value()), gamma=float(d.gamma.value()),
                    pmin=bmin, pmax=bmax, nbins=nbins, alpha=float(a),
                    sigma=self.file.sigma) for a in alphas]
            else:
                fits = scan_alpha(
                    self.file.velocity, self.file.y_data, list(alphas),
                    delta=float(d.delta.value()), quad=float(d.quad.value()),
                    gamma=float(d.gamma.value()),
                    bmin=bmin, bmax=bmax, nbins=nbins, sigma=self.file.sigma)
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
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); v.addWidget(bb)
        dlg.exec()

    # ── Acciones rápidas ─────────────────────────────────────────────────
    def on_find_center(self) -> None:
        if self.file.counts is None:
            return
        center = find_best_integer_or_half_center(self.file.counts)
        # Re-dobla con el nuevo centro
        folded, _ = fold_integer_or_half(self.file.counts, center)
        norm = float(np.percentile(folded, 90)) or 1.0
        self.file.folded = folded
        self.file.center = center
        self.file.norm_factor = norm
        self.file.sigma = np.sqrt(np.maximum(folded / 2.0, 1.0)) / norm
        self.file.y_data = folded / norm
        vmax = abs(self.calib.vmax.value())
        self.file.velocity = np.linspace(-vmax, vmax, folded.size)
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
            model = model_from_values(v, state.values, state.components) if state else None
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

    # ── Ajuste distribución P(BHF) ──────────────────────────────────────
    def on_fit_distribution(self) -> None:
        if self.file.velocity is None or self.file.y_data is None:
            return
        d = self.dist_panel
        bmin = float(d.bmin.value())
        bmax = max(bmin + 0.5, float(d.bmax.value()))
        nbins = max(5, int(round(d.nbins.value())))
        alpha = 10.0 ** float(d.log_alpha.value())
        var = self.dist_variable
        label = "P(ΔEQ)" if var == "quad" else "P(BHF)"
        self.statusBar().showMessage(f"Ajustando {label}…")
        QtWidgets.QApplication.processEvents()
        try:
            if var == "quad":
                result = fit_hyperfine_distribution(
                    self.file.velocity, self.file.y_data,
                    variable="quad",
                    delta=float(d.delta.value()), quad=0.0,
                    gamma=float(d.gamma.value()),
                    pmin=bmin, pmax=bmax, nbins=nbins, alpha=alpha,
                    sigma=self.file.sigma,
                )
            else:
                result = fit_bhf_distribution(
                    self.file.velocity, self.file.y_data,
                    delta=float(d.delta.value()), quad=float(d.quad.value()),
                    gamma=float(d.gamma.value()),
                    bmin=bmin, bmax=bmax, nbins=nbins, alpha=alpha,
                    sigma=self.file.sigma,
                )
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("fit.run"),
                                            f"{type(exc).__name__}: {exc}")
            return
        # Pintar el ajuste sobre el canvas principal y abrir un diálogo
        # con la curva P(BHF).
        style = get_style(self.plot_style_name)
        self.canvas.render(self.file.velocity, self.file.y_data,
                           model=result.fitted_curve, style=style)
        msg = (f"{label}: bins={nbins}  α=10^{d.log_alpha.value():.2f}  "
               f"RMS={result.rms:.5g}")
        self.statusBar().showMessage(msg)
        # Mostrar info
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
    def on_init_from_minima(self) -> None:
        """Detecta picos de absorción y propone parámetros para la componente 1."""
        if self.file.velocity is None or self.file.y_data is None:
            return
        v = self.file.velocity
        y = self.file.y_data
        baseline0 = float(np.percentile(y, 90))
        absorption = np.maximum(baseline0 - y, 0.0)
        max_abs = float(np.nanmax(absorption))
        if max_abs <= 0:
            QtWidgets.QMessageBox.information(
                self, tr("fit.init_from_minima"),
                "No se detectaron mínimos de absorción.")
            return
        dv = abs(float(v[1] - v[0])) if v.size > 1 else 0.05
        min_dist_ch = max(3, int(0.15 / dv))
        try:
            from scipy.signal import find_peaks
        except ImportError:
            return
        idxs, _ = find_peaks(absorption, height=0.06 * max_abs, distance=min_dist_ch)
        if idxs.size == 0:
            QtWidgets.QMessageBox.information(
                self, tr("fit.init_from_minima"),
                "No se detectaron mínimos significativos.")
            return
        positions = v[idxs]
        depths = absorption[idxs]
        # Ordenar por posición.
        order = np.argsort(positions)
        positions = positions[order]
        depths = depths[order]

        from core.constants import LINE_POS_33T, BHF_DEFAULT_T
        self._building = True
        cp = self.components_panels[0]
        cp.enabled.setChecked(True)
        if len(positions) >= 5:
            # Sextete: ajusta BHF al espaciado y delta al centro de simetría.
            outer = (positions[-1] - positions[0])
            bhf = float(BHF_DEFAULT_T * outer / (LINE_POS_33T[-1] - LINE_POS_33T[0]))
            delta = float(0.5 * (positions[0] + positions[-1]))
            cp.type_combo.setCurrentText("Sextete")
            cp.params["delta"].set_value(delta)
            cp.params["quad"].set_value(0.0)
            cp.params["bhf"].set_value(max(1.0, min(60.0, bhf)))
            cp.params["gamma1"].set_value(0.15)
            cp.params["depth"].set_value(float(max(depths) / 3.0))
            msg = f"Sextete: δ≈{delta:.3f}  BHF≈{bhf:.2f} T"
        elif len(positions) == 2:
            # Doblete.
            delta = float(0.5 * (positions[0] + positions[1]))
            deq = float(abs(positions[1] - positions[0]))
            cp.type_combo.setCurrentText("Doblete")
            cp.params["delta"].set_value(delta)
            cp.params["quad"].set_value(deq)
            cp.params["gamma1"].set_value(0.16)
            cp.params["depth"].set_value(float(max(depths) * 1.0))
            msg = f"Doblete: δ≈{delta:.3f}  ΔEQ≈{deq:.3f}"
        else:
            # Singlete: usar el pico más profundo.
            i_best = int(np.argmax(depths))
            cp.type_combo.setCurrentText("Singlete")
            cp.params["delta"].set_value(float(positions[i_best]))
            cp.params["gamma1"].set_value(0.16)
            cp.params["depth"].set_value(float(depths[i_best]))
            msg = f"Singlete: δ≈{positions[i_best]:.3f}"
        self.calib.baseline.set_value(baseline0)
        self._building = False
        self.statusBar().showMessage(msg, 5000)
        self._refresh_plot()

    # ── Verosimilitud perfilada ─────────────────────────────────────────
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
        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8")
            self.statusBar().showMessage(f"Informe guardado: {path}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("file.export_report"),
                                            f"{type(exc).__name__}: {exc}")

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


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    # Estilo Fusion (Qt nativo, plano y moderno; igual en Win/Linux/macOS).
    try:
        app.setStyle("Fusion")
    except Exception:
        pass
    win = MossbauerQtWindow(); win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
