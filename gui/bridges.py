"""Puentes Qt usados por la interfaz principal."""
from __future__ import annotations

from PySide6 import QtCore


class _UiCallBridge(QtCore.QObject):
    """Marshalla llamadas al hilo de la interfaz mediante una señal.

    Permite que hilos de trabajo pidan ejecutar un callable en el hilo de la GUI
    emitiendo ``call(fn)``; el receptor lo invoca de forma segura.
    """
    call = QtCore.Signal(object)
