#!/usr/bin/env python3
"""Front-end Qt de Fitbauer.

Este módulo queda como punto de entrada y ensamblador de la ventana principal.
La implementación de paneles, menús, layout y acciones vive en ``gui/``.
"""
from __future__ import annotations

import sys
import threading  # reexport histórico: tests/extensiones lo parchean aquí
import webbrowser  # reexport histórico: tests/extensiones lo parchean aquí
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
import matplotlib

if not hasattr(np, "trapezoid"):
    np.trapezoid = np.trapz  # type: ignore[attr-defined]

matplotlib.use("QtAgg")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from mossbauer_i18n import tr  # noqa: E402
from core.constants import APP_NAME, APP_VERSION  # noqa: E402
from core.data_io import load_credentials, save_credentials  # noqa: E402,F401
from mossbauer_updater import (  # noqa: E402,F401 - compatibilidad pública
    ReleaseInfo,
    _pip_install_requirements,
    _update_pip_stamp,
    check_requirements_if_needed,
    choose_download,
    download_file,
    find_release_checksum,
    install_zip_update,
    is_newer,
    is_zip_update,
    latest_release,
    load_update_settings,
    save_update_settings,
)

from gui.branding import _show_splash  # noqa: E402
from gui.bridges import _UiCallBridge  # noqa: E402
from gui.state import FileState, RuntimeResultState  # noqa: E402
from gui.window_mixins import WindowMixins  # noqa: E402


class MossbauerQtWindow(WindowMixins, QtWidgets.QMainWindow):
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
        icon_png = ROOT / "assets" / "fitbauer_icon.png"
        if icon_png.exists():
            self.setWindowIcon(QtGui.QIcon(str(icon_png)))
        self.resize(1400, 900)
        self.file = FileState()
        self.comparison_spectra: list = []   # ComparisonSpectrum, solo display
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
        self.runtime_results = RuntimeResultState()
        self._help_dialog: QtWidgets.QDialog | None = None
        self.dist_use_sharp = False
        self.phase_predict_enabled = False  # sugeridor de fases: desactivado por defecto
        self._edge_trim = 1
        self._load_settings()
        self._load_fit_history()
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
