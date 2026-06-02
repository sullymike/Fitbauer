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


class SextetPanel(QtWidgets.QGroupBox):
    """10 parámetros de un sextete + casilla 'activo'."""

    paramChanged = QtCore.Signal()

    def __init__(self, idx: int, parent=None):
        super().__init__(tr("tab.component", idx=idx), parent)
        self.idx = idx
        v = QtWidgets.QVBoxLayout(self)
        v.setSpacing(2)

        self.enabled = QtWidgets.QCheckBox(tr("component.enable", idx=idx))
        self.enabled.setChecked(idx == 1)
        v.addWidget(self.enabled)

        # 10 parámetros (rangos extendidos para ajustar α-Fe a Fe2O3, etc.)
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

        # Fijos típicos para α-Fe (intensidades + gammas relativas + quad).
        for k in ("int1", "int2", "int3", "gamma2", "gamma3", "quad"):
            self.params[k].set_fixed(True)
        v.addStretch(1)

    def values_dict(self) -> dict[str, float]:
        return {f"s{self.idx}_{k}": ctl.value() for k, ctl in self.params.items()}

    def fixed_dict(self) -> dict[str, bool]:
        return {f"s{self.idx}_{k}": ctl.is_fixed() for k, ctl in self.params.items()}

    def apply_values(self, values: dict[str, float]) -> None:
        for k, ctl in self.params.items():
            v = values.get(f"s{self.idx}_{k}")
            if v is not None:
                ctl.set_value(v)


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

        self.sextet1 = SextetPanel(idx=1)
        lv.addWidget(self.sextet1)
        lv.addStretch(1)

        scroll = QtWidgets.QScrollArea(); scroll.setWidget(left); scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(360); scroll.setMaximumWidth(440)
        splitter.addWidget(scroll)

        # ── Centro: canvas + toolbar ─────────────────────────────────────
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0)
        self.canvas = SpectrumCanvas(right)
        self.toolbar = NavigationToolbar(self.canvas, right)
        rv.addWidget(self.toolbar); rv.addWidget(self.canvas)
        splitter.addWidget(right)

        splitter.setSizes([420, 1000])

        # Conectar señales de cambio para refrescar el plot en vivo
        self.calib.paramChanged.connect(self._refresh_plot)
        self.sextet1.paramChanged.connect(self._refresh_plot)

    # ── Menubar ──────────────────────────────────────────────────────────
    def _build_menubar(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu(tr("menu.file"))
        act_open = QtGui.QAction(tr("file.open"), self)
        act_open.setShortcut(QtGui.QKeySequence.Open)
        act_open.triggered.connect(self.on_open)
        file_menu.addAction(act_open)
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

        help_menu = mb.addMenu(tr("menu.help"))
        act_about = QtGui.QAction(tr("help.about"), self)
        act_about.triggered.connect(self.on_about)
        help_menu.addAction(act_about)

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
        values.update(self.sextet1.values_dict())
        fixed: dict[str, bool] = {k: False for k in values}
        fixed.update({k: True for k in ("vmax", "center")})
        fixed.update(self.sextet1.fixed_dict())
        bounds = {
            "baseline": (0.70, 1.30), "slope": (-0.005, 0.005),
            "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0),
        }
        for name, (lo, hi) in (
            ("delta", (-2.0, 3.0)), ("quad", (-4.0, 4.0)),
            ("bhf", (0.0, 60.0)), ("gamma1", (0.03, 2.0)),
            ("gamma2", (0.2, 3.0)), ("gamma3", (0.2, 3.0)),
            ("depth", (0.0, 0.30)), ("int1", (0.0, 9.0)),
            ("int2", (0.0, 6.0)), ("int3", (0.0, 3.0)),
        ):
            bounds[f"s1_{name}"] = (lo, hi)
        components = [Component(idx=1, enabled=self.sextet1.enabled.isChecked(), kind="Sextete")]
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
        comps = []
        for comp in state.components:
            if comp.enabled:
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
        self.sextet1.apply_values(result.values)
        self._building = False
        red = result.stats.get("red_chi2", float("nan"))
        chi2 = result.stats.get("chi2", float("nan"))
        self.statusBar().showMessage(
            f"χ²={chi2:.4g}  χ²red={red:.4g}  ·  {result.n_starts} arranques")
        self.act_fit.setEnabled(True)
        self._refresh_plot()

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
    win = MossbauerQtWindow(); win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
