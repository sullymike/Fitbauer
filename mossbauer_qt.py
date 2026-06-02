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

from mossbauer_i18n import tr  # noqa: E402
from core.constants import APP_VERSION, APP_NAME, SEXTET_PARAM_NAMES  # noqa: E402
from core.folding import (  # noqa: E402
    read_ws5_counts, find_best_integer_or_half_center, fold_integer_or_half,
)
from core.fit_engine import (  # noqa: E402
    Component, FitState, fit_discrete, model_from_values,
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
               components: list[tuple[int, str, np.ndarray]] | None = None) -> None:
        self.ax.clear(); self.ax_res.clear()
        self.ax.plot(v, y, ".", color="#0f172a", ms=3.5, alpha=0.7,
                     label=tr("plot.legend_data"))
        if components:
            palette = ("#10b981", "#f59e0b", "#8b5cf6")
            for idx, kind, comp in components:
                self.ax.plot(v, comp, "--", color=palette[(idx - 1) % len(palette)],
                             lw=1.4, alpha=0.85,
                             label=f"{tr(f'kind.{kind}', default=kind)} {idx}")
        if model is not None:
            self.ax.plot(v, model, "-", color="#ef4444", lw=2.2,
                         label=tr("plot.legend_model"))
            residual = y - model
            self.ax_res.axhline(0, color="#9a3412", lw=0.9, alpha=0.9)
            self.ax_res.plot(v, residual, "-", color="#64748b", lw=1.0)
            lim = max(float(np.nanmax(np.abs(residual))) * 1.18, 1e-6)
            self.ax_res.set_ylim(-lim, lim)
            self.ax.tick_params(labelbottom=False)
        self.ax.set_ylabel(tr("plot.transmission_ylabel"))
        self.ax.set_title(tr("plot.title_discrete"), pad=10, fontweight="semibold")
        self.ax.grid(True, alpha=0.3)
        self.ax_res.set_xlabel(tr("plot.velocity_xlabel"))
        self.ax_res.set_ylabel(tr("plot.residual_ylabel"))
        self.ax_res.grid(True, alpha=0.3)
        self.ax.legend(loc="lower right", fontsize=9, framealpha=0.85)
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


class MossbauerQtWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}  (Qt)")
        self.resize(1400, 900)
        self.file = FileState()
        self._building = False
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
        self.act_fit = QtGui.QAction(tr("fit.run"), self)
        self.act_fit.setShortcut("Ctrl+R")
        self.act_fit.triggered.connect(self.on_fit)
        self.act_fit.setEnabled(False)
        fit_menu.addAction(self.act_fit)
        fit_menu.addSeparator()
        act_fix_all = QtGui.QAction(tr("fit.fix_all"), self)
        act_fix_all.triggered.connect(lambda: self._set_all_fixed(True))
        fit_menu.addAction(act_fix_all)
        act_free_all = QtGui.QAction(tr("fit.free_all"), self)
        act_free_all.triggered.connect(lambda: self._set_all_fixed(False))
        fit_menu.addAction(act_free_all)

        help_menu = mb.addMenu(tr("menu.help"))
        act_about = QtGui.QAction(tr("help.about"), self)
        act_about.triggered.connect(self.on_about)
        help_menu.addAction(act_about)

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
        if state is None:
            self.canvas.render(v, y)
            return
        try:
            model = model_from_values(v, state.values, state.components)
        except Exception:
            self.canvas.render(v, y)
            return
        # Solo dibujar componentes individuales si hay más de uno activo.
        comps = []
        enabled = [c for c in state.components if c.enabled]
        if len(enabled) >= 2:
            for comp in enabled:
                only_this = model_from_values(v, state.values, [comp])
                comps.append((comp.idx, comp.kind, only_this))
        self.canvas.render(v, y, model=model, components=comps)

    def on_fit(self) -> None:
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
