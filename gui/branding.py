"""Logo y splash de Fitbauer para la interfaz Qt."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from mossbauer_i18n import tr
from core.constants import APP_NAME, APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


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
