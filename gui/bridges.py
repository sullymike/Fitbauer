"""Puentes Qt usados por la interfaz principal."""
from __future__ import annotations

from PySide6 import QtCore


class _UiCallBridge(QtCore.QObject):
    call = QtCore.Signal(object)

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
