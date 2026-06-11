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


class FitCancelledError(Exception):
    """El usuario canceló el ajuste desde el diálogo de progreso."""


class FitWorkflowMixin:
    """Helpers comunes de orquestación de ajustes en la ventana Qt."""

    def _open_progress_dialog(self, title: str, message: str | None = None):
        """Ventana modal de progreso con estado, métricas y parámetros.

        Devuelve ``(dialog, update, close)``. ``update()`` acepta un texto simple
        o un diccionario con claves como ``phase``, ``iteration``, ``max_iter``,
        ``rms``, ``best_rms`` y ``params``. Compatible con callbacks que solo
        envían una cadena.
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
        v.setSpacing(8)

        label = QtWidgets.QLabel(message)
        label.setWordWrap(True)
        label.setMinimumWidth(460)
        v.addWidget(label)

        detail_label = QtWidgets.QLabel("")
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet("color: #475569;")
        v.addWidget(detail_label)
        detail_label.hide()

        metrics_label = QtWidgets.QLabel("")
        metrics_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        metrics_label.setStyleSheet("font-family: monospace;")
        v.addWidget(metrics_label)
        metrics_label.hide()

        params_table = QtWidgets.QTableWidget(0, 2)
        params_table.setHorizontalHeaderLabels([
            tr("report.parameter", default="Parámetro"),
            tr("report.value", default="Valor"),
        ])
        params_table.horizontalHeader().setStretchLastSection(True)
        params_table.verticalHeader().setVisible(False)
        params_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        params_table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        params_table.setMaximumHeight(150)
        v.addWidget(params_table)
        params_table.hide()

        bar = QtWidgets.QProgressBar()
        bar.setRange(0, 0)
        bar.setTextVisible(True)
        v.addWidget(bar)

        btn_cancel = QtWidgets.QPushButton(tr("progress.cancel", default="Cancelar"))
        btn_cancel.setObjectName("btn_cancel_fit")
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(btn_cancel)
        v.addLayout(btn_row)

        _state = {"cancelled": False}
        btn_cancel.clicked.connect(lambda: _state.__setitem__("cancelled", True))

        dlg.show()
        QtWidgets.QApplication.processEvents()

        def _fmt_value(x: object) -> str:
            try:
                xf = float(x)  # type: ignore[arg-type]
                return f"{xf:.6g}" if np.isfinite(xf) else str(x)
            except Exception:
                return str(x)

        def update(payload) -> None:
            if not dlg.isVisible():
                return
            if _state["cancelled"]:
                raise FitCancelledError()
            if isinstance(payload, dict):
                phase = str(payload.get("phase") or payload.get("message") or message)
                label.setText(phase)
                iteration = payload.get("iteration")
                max_iter = payload.get("max_iter")
                if iteration is not None and max_iter is not None:
                    try:
                        it = int(iteration); mx = max(1, int(max_iter))
                        bar.setRange(0, mx)
                        bar.setValue(max(0, min(mx, it)))
                        detail = str(payload.get("detail") or "")
                        iter_txt = tr("progress.iteration", default="Evaluación {i}/{n}", i=it, n=mx)
                        detail_label.setText(f"{iter_txt}\n{detail}" if detail else iter_txt)
                        detail_label.show()
                    except Exception:
                        bar.setRange(0, 0)
                elif payload.get("detail"):
                    detail_label.setText(str(payload["detail"]))
                    detail_label.show()
                else:
                    detail_label.hide()
                    bar.setRange(0, 0)

                metric_parts: list[str] = []
                for key, lbl in (("rms", "RMS"), ("best_rms", "mejor RMS"),
                                 ("chi2", "χ²"), ("best_chi2", "mejor χ²")):
                    if key in payload and payload[key] is not None:
                        metric_parts.append(f"{lbl}={_fmt_value(payload[key])}")
                if metric_parts:
                    metrics_label.setText("   ".join(metric_parts))
                    metrics_label.show()
                else:
                    metrics_label.hide()

                params = payload.get("params")
                if isinstance(params, dict) and params:
                    params_table.setRowCount(len(params))
                    for row, (k, val) in enumerate(params.items()):
                        params_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(k)))
                        params_table.setItem(row, 1, QtWidgets.QTableWidgetItem(_fmt_value(val)))
                    params_table.resizeColumnsToContents()
                    params_table.show()
                else:
                    params_table.hide()
            else:
                label.setText(str(payload))
                detail_label.setText(tr("progress.detail_wait", default="El cálculo está en curso…"))
                detail_label.show()
                metrics_label.hide()
                params_table.hide()
                bar.setRange(0, 0)
            dlg.adjustSize()
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
        except FitCancelledError:
            return None
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
            dist_map_2d=getattr(self, "_dist_map_2d", None),
        )

    def _finish_gui_fit_result(self, result: GuiFitResult) -> None:
        """Aplica las salidas GUI comunes: render y mensaje de estado."""
        if result.render is not None:
            self._render_fit_result(result.render)
        if result.message:
            self.statusBar().showMessage(result.message)
