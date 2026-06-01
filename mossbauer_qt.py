#!/usr/bin/env python3
"""Mössbauer Fe-57 — front-end Qt (PySide6).

Sesión 1 (scaffold): QMainWindow con menú File/Fit/View/Help y plot
principal embebido con matplotlib (FigureCanvasQTAgg). Permite abrir un
fichero .ws5/.adt y dibujar el espectro doblado. Reutiliza todo el motor
existente (folding, modelo, ajuste) desde mossbauer_fe33_gui_v2IA.py y
core/.

Pendiente de sesiones siguientes:
  - Paneles de sextete (sliders + entry + fijo) en QDockWidget o splitter.
  - Diálogos: ajuste en serie, perfil de verosimilitud, restricciones.
  - Menú contextual del slider σ.
  - Estilos QSS (claro/oscuro/publicación).
  - Tests pytest-qt.
"""
from __future__ import annotations

import sys
from pathlib import Path

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

from mossbauer_i18n import tr, get_language, available_languages, set_language  # noqa: E402
from core.constants import APP_VERSION, APP_NAME  # noqa: E402
from mossbauer_fe33_gui_v2IA import (  # noqa: E402
    read_ws5_counts,
    find_best_integer_or_half_center,
    fold_integer_or_half,
)


class SpectrumCanvas(FigureCanvas):
    """Lienzo matplotlib embebido que dibuja datos + (futuro) modelo."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        self.fig = Figure(figsize=(7.0, 5.0), dpi=100, facecolor="#ffffff")
        super().__init__(self.fig)
        self.setParent(parent)
        gs = self.fig.add_gridspec(2, 1, height_ratios=[4.6, 1.0], hspace=0.08)
        self.ax = self.fig.add_subplot(gs[0])
        self.ax_res = self.fig.add_subplot(gs[1], sharex=self.ax)
        self.ax.set_ylabel(tr("plot.transmission_ylabel"))
        self.ax_res.set_xlabel(tr("plot.velocity_xlabel"))
        self.ax_res.set_ylabel(tr("plot.residual_ylabel"))
        self.fig.tight_layout()

    def plot_spectrum(self, v: np.ndarray, y: np.ndarray) -> None:
        self.ax.clear()
        self.ax_res.clear()
        self.ax.plot(v, y, ".", color="#0f172a", ms=3.5, alpha=0.7,
                     label=tr("plot.legend_data"))
        self.ax.set_ylabel(tr("plot.transmission_ylabel"))
        self.ax.set_title(tr("plot.title_discrete"), pad=10, fontweight="bold")
        self.ax.grid(True, alpha=0.3)
        self.ax_res.axhline(0, color="#9a3412", lw=0.9)
        self.ax_res.set_xlabel(tr("plot.velocity_xlabel"))
        self.ax_res.set_ylabel(tr("plot.residual_ylabel"))
        self.ax_res.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.draw_idle()

    def show_no_file(self) -> None:
        self.ax.clear()
        self.ax_res.clear()
        self.ax.text(0.5, 0.5, tr("plot.no_file"),
                     transform=self.ax.transAxes, ha="center", va="center",
                     fontsize=14, color="#075985", fontweight="bold")
        self.ax.set_xticks([]); self.ax.set_yticks([])
        self.ax_res.set_xticks([]); self.ax_res.set_yticks([])
        self.fig.tight_layout()
        self.draw_idle()


class MossbauerQtWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}  (Qt)")
        self.resize(1300, 850)

        # ── Estado mínimo de sesión ───────────────────────────────────────────
        self.counts: np.ndarray | None = None
        self.folded: np.ndarray | None = None
        self.center: float | None = None
        self.vmax = 12.0
        self.norm_factor = 1.0
        self.file_path: Path | None = None

        # ── Layout: splitter horizontal con plot al centro ───────────────────
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        layout.addWidget(splitter)

        # Columna izquierda (placeholder para futuros paneles).
        left_box = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_box)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.addWidget(QtWidgets.QLabel("<i>Paneles (siguiente sesión)</i>"))
        self._file_label = QtWidgets.QLabel("—")
        self._file_label.setWordWrap(True)
        left_layout.addWidget(self._file_label)
        left_layout.addStretch(1)
        left_box.setMinimumWidth(260)
        splitter.addWidget(left_box)

        # Centro: canvas + toolbar.
        center_box = QtWidgets.QWidget()
        center_layout = QtWidgets.QVBoxLayout(center_box)
        center_layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = SpectrumCanvas(center_box)
        self.toolbar = NavigationToolbar(self.canvas, center_box)
        center_layout.addWidget(self.toolbar)
        center_layout.addWidget(self.canvas)
        splitter.addWidget(center_box)

        splitter.setSizes([320, 980])
        self.canvas.show_no_file()

        # ── Menú ───────────────────────────────────────────────────────────────
        self._build_menubar()

        # ── Status bar ─────────────────────────────────────────────────────────
        self.statusBar().showMessage(tr("plot.no_file"))

    # ── Construcción del menú ────────────────────────────────────────────────
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
        for label_key in ("fit.find_center", "fit.init_from_minima",
                          "fit.auto_from_minima", "fit.run", "fit.bootstrap",
                          "fit.profile_likelihood", "fit.batch_fit"):
            act = QtGui.QAction(tr(label_key), self)
            act.setEnabled(False)  # placeholders hasta portar la lógica
            fit_menu.addAction(act)

        view_menu = mb.addMenu(tr("menu.view"))
        act_residual = QtGui.QAction(tr("options.show_residual"), self,
                                     checkable=True, checked=True)
        view_menu.addAction(act_residual)
        act_legend = QtGui.QAction(tr("options.show_legend"), self,
                                    checkable=True, checked=False)
        view_menu.addAction(act_legend)

        help_menu = mb.addMenu(tr("menu.help"))
        act_about = QtGui.QAction(tr("help.about"), self)
        act_about.triggered.connect(self.on_about)
        help_menu.addAction(act_about)

    # ── Acciones ─────────────────────────────────────────────────────────────
    def on_open(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, tr("file.open"), str(ROOT),
            "WS5/ADT (*.ws5 *.adt *.WS5 *.ADT);;All (*.*)")
        if not path:
            return
        path = Path(path)
        try:
            counts = read_ws5_counts(path)
            center = find_best_integer_or_half_center(counts)
            folded, _pairs = fold_integer_or_half(counts, center)
            norm = float(np.percentile(folded, 90)) if folded.size else 1.0
            if norm == 0:
                norm = 1.0
            y = folded / norm
            v = np.linspace(-self.vmax, self.vmax, folded.size)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("file.open"), f"{type(exc).__name__}: {exc}")
            return
        self.counts = counts
        self.folded = folded
        self.center = center
        self.norm_factor = norm
        self.file_path = path
        self._file_label.setText(f"<b>{path.name}</b><br>"
                                 f"{counts.size} canales · centro={center:.3f}")
        self.canvas.plot_spectrum(v, y)
        self.statusBar().showMessage(
            f"{path.name} · {counts.size} canales · centro={center:.3f}")

    def on_about(self) -> None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("help.about_title", version=APP_VERSION))
        layout = QtWidgets.QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        title = QtWidgets.QLabel(f"<h2>{APP_NAME}</h2>")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        version = QtWidgets.QLabel(
            f"<center>{tr('splash.version', version=APP_VERSION)}<br>"
            f"<i>{tr('main.subtitle')}</i></center>")
        version.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(version)
        layout.addSpacing(8)
        hint = QtWidgets.QLabel(f"<center><i>{tr('splash.click_to_continue')}</i></center>")
        layout.addWidget(hint)
        # Cierre al pulsar
        dlg.mousePressEvent = lambda _e: dlg.accept()
        dlg.exec()


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = MossbauerQtWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
