"""Flujo común de ajustes para la GUI Qt.

Este módulo no contiene física ni motores de ajuste: solo utilidades de
orquestación compartidas por los modos discreto y distribución (progreso,
render y manejo de estado visual).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
from PySide6 import QtCore, QtWidgets

from mossbauer_i18n import tr
from core.plot_styles import get_style


@dataclass(frozen=True)
class GuiFitRenderState:
    """Datos mínimos para dibujar un resultado de ajuste en el canvas."""

    velocity: np.ndarray
    y_data: np.ndarray
    model: np.ndarray | None = None
    components: list[tuple[int, str, np.ndarray]] = field(default_factory=list)
    residual: np.ndarray | None = None
    model_v: np.ndarray | None = None


@dataclass(frozen=True)
class GuiFitResult:
    """Envoltura común del resultado que consume la GUI.

    No sustituye a los resultados científicos de ``core``/distribución; solo
    agrupa la salida necesaria para la capa Qt: modo, resultado bruto, render y
    mensaje de estado.
    """

    mode: str
    raw_result: Any
    render: GuiFitRenderState | None = None
    message: str = ""
    info_result: Any | None = None


class FitWorkflowMixin:
    """Helpers comunes de orquestación de ajustes en la ventana Qt."""

    def _open_progress_dialog(self, title: str, message: str | None = None):
        """Ventana modal de progreso indeterminado.

        Devuelve ``(dialog, update, close)``: ``update(msg)`` cambia el texto y
        ``close()`` la cierra. La implementación queda compartida por ajuste
        discreto, distribución y herramientas auxiliares.
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
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        v.addWidget(bar)
        dlg.show()
        QtWidgets.QApplication.processEvents()

        def update(msg) -> None:
            if dlg.isVisible():
                if isinstance(msg, dict):
                    phase = msg.get("phase", "")
                    it = msg.get("iteration")
                    max_it = msg.get("max_iter")
                    rms = msg.get("rms")
                    if it is not None and max_it:
                        bar.setRange(0, int(max_it))
                        bar.setValue(int(it))
                    txt = phase
                    if rms is not None and isinstance(rms, float) and not (rms != rms):
                        txt += f"  RMS={rms:.5g}"
                    label.setText(txt)
                else:
                    label.setText(str(msg))
                QtWidgets.QApplication.processEvents()

        def close() -> None:
            dlg.close()
            dlg.deleteLater()

        return dlg, update, close

    def _run_with_fit_progress(
        self,
        title: str,
        message: str,
        run: Callable[[Callable[[str], None]], Any],
        *,
        error_title: str | None = None,
        disable_fit_action: bool = False,
    ) -> Any | None:
        """Ejecuta un cálculo con diálogo de progreso y manejo uniforme de error."""
        if disable_fit_action and hasattr(self, "act_fit"):
            self.act_fit.setEnabled(False)
        _dlg, update_progress, close_progress = self._open_progress_dialog(title, message)
        try:
            return run(update_progress)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self,
                error_title or tr("fit.run"),
                f"{type(exc).__name__}: {exc}",
            )
            return None
        finally:
            close_progress()
            if disable_fit_action and hasattr(self, "act_fit"):
                self.act_fit.setEnabled(True)

    def _render_fit_result(self, render_state: GuiFitRenderState) -> None:
        """Dibuja datos/modelo/componentes con las opciones visuales actuales."""
        style = get_style(self.plot_style_name)
        ui_state = self._ui_action_state()
        self.canvas.render(
            render_state.velocity,
            render_state.y_data,
            model=render_state.model,
            components=render_state.components,
            style=style,
            show_residual=ui_state.show_residual,
            show_legend=ui_state.show_legend,
            model_v=render_state.model_v,
            residual=render_state.residual,
            style_name=self.plot_style_name,
        )

    def _finish_gui_fit_result(self, result: GuiFitResult) -> None:
        """Aplica las salidas GUI comunes: render y mensaje de estado."""
        if result.render is not None:
            self._render_fit_result(result.render)
        if result.message:
            self.statusBar().showMessage(result.message)
