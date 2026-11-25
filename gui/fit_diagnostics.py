"""Indicador del estado del ajuste (barra de estado) y ventana de diagnóstico.

El indicador sustituye al «⚠ ajuste poco fiable» que se perdía con el
siguiente mensaje: queda fijo abajo a la izquierda hasta el siguiente ajuste
o la siguiente carga y, al pulsarlo, abre la ventana «Diagnóstico del ajuste»
con una fila por comprobación (estado, valor, umbral, qué significa y qué
hacer). Las comprobaciones salen de ``core.fit_diagnostics``.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from core.fit_diagnostics import Check, n_issues, verdict
from mossbauer_i18n import tr

_ICON = {"ok": "✓", "warn": "⚠", "fail": "✗", "na": "–"}
_COLOR = {"ok": "#1a8a5a", "warn": "#b7791f", "fail": "#c53030", "na": "#888888"}


def verdict_text(checks: list[Check]) -> str:
    v = verdict(checks)
    n = n_issues(checks)
    if v == "fail":
        return tr("diag.verdict_fail", n=n)
    if v == "warn":
        return tr("diag.verdict_warn", n=n)
    return tr("diag.verdict_ok")


def checks_as_text(checks: list[Check], note: str = "") -> str:
    lines = [verdict_text(checks), ""]
    for c in checks:
        lines.append(f"{_ICON.get(c.status, '?')} {c.title}: {c.value}  "
                     f"[{tr('diag.col_threshold')}: {c.threshold}]")
        for extra in (c.meaning, c.action):
            if extra and c.status in ("warn", "fail"):
                lines.append(f"    {extra}")
    if note:
        lines += ["", note]
    return "\n".join(lines)


class FitDiagnosticsDialog(QtWidgets.QDialog):
    """Ventana no modal: se puede dejar abierta mientras se cambia el modelo."""

    def __init__(self, parent=None, on_help=None):
        super().__init__(parent)
        self.setWindowTitle(tr("diag.window_title"))
        self.resize(1040, 680)
        self._checks: list[Check] = []
        self._note = ""
        v = QtWidgets.QVBoxLayout(self)
        self.verdict_label = QtWidgets.QLabel()
        f = self.verdict_label.font()
        f.setPointSizeF(f.pointSizeF() * 1.25)
        f.setBold(True)
        self.verdict_label.setFont(f)
        v.addWidget(self.verdict_label)
        intro = QtWidgets.QLabel(tr("diag.intro"))
        intro.setWordWrap(True)
        v.addWidget(intro)
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["", tr("diag.col_check"), tr("diag.col_value"),
             tr("diag.col_threshold"), tr("diag.col_meaning")])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        for col in (1, 2, 3):
            hh.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(3, 200)
        v.addWidget(self.table, stretch=1)
        self.note_label = QtWidgets.QLabel()
        self.note_label.setWordWrap(True)
        v.addWidget(self.note_label)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        btn_copy = bb.addButton(tr("diag.copy"), QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        btn_copy.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(
            checks_as_text(self._checks, self._note)))
        if on_help is not None:
            btn_help = bb.addButton(tr("diag.help"), QtWidgets.QDialogButtonBox.ButtonRole.HelpRole)
            btn_help.clicked.connect(on_help)
        bb.rejected.connect(self.close)
        v.addWidget(bb)

    def set_checks(self, checks: list[Check], note: str = "") -> None:
        self._checks, self._note = list(checks), note
        v = verdict(checks)
        self.verdict_label.setText(verdict_text(checks))
        self.verdict_label.setStyleSheet(f"color: {_COLOR.get(v, '#888')};")
        self.table.setRowCount(len(checks))
        for row, c in enumerate(checks):
            icon = QtWidgets.QTableWidgetItem(_ICON.get(c.status, "?"))
            icon.setForeground(QtGui.QColor(_COLOR.get(c.status, "#888")))
            icon.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            fi = icon.font()
            fi.setBold(True)
            icon.setFont(fi)
            self.table.setItem(row, 0, icon)
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(c.title))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(c.value))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(c.threshold))
            texto = c.meaning
            if c.action and c.status in ("warn", "fail"):
                texto = f"{c.meaning}\n→ {c.action}" if c.meaning else f"→ {c.action}"
            self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(texto))
        self._fit_rows()
        self.note_label.setText(note)
        self.note_label.setVisible(bool(note))


    def _fit_rows(self) -> None:
        # La altura depende del ancho real de la columna de texto: se
        # recalcula cuando la tabla ya está maquetada.
        QtCore.QTimer.singleShot(0, self.table.resizeRowsToContents)

    def showEvent(self, event):  # noqa: N802 (API de Qt)
        super().showEvent(event)
        self._fit_rows()

    def resizeEvent(self, event):  # noqa: N802 (API de Qt)
        super().resizeEvent(event)
        self._fit_rows()


class FitDiagnosticsMixin:
    """Indicador pulsable en la barra de estado + ventana de diagnóstico."""

    def _ensure_fit_indicator(self) -> QtWidgets.QPushButton:
        btn = getattr(self, "fit_indicator", None)
        if btn is None:
            btn = QtWidgets.QPushButton()
            btn.setFlat(True)
            btn.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
            btn.setToolTip(tr("diag.indicator_tip"))
            btn.clicked.connect(self.show_fit_diagnostics)
            btn.hide()
            self.statusBar().addWidget(btn)
            self.fit_indicator = btn
            # Resumen del ajuste (χ², arranques) al lado del indicador: como
            # widget y no como mensaje temporal, que ocultaría el indicador.
            lab = QtWidgets.QLabel()
            lab.hide()
            self.statusBar().addWidget(lab, 1)
            self.fit_summary_label = lab
        return btn

    def _set_fit_diagnostics(self, checks: list[Check] | None, note: str = "",
                             summary: str = "") -> None:
        """Guarda las comprobaciones del último ajuste y actualiza el indicador."""
        self._fit_checks = list(checks or [])
        self._fit_checks_note = note
        act = getattr(self, "act_fit_diagnostics", None)
        if act is not None:
            act.setEnabled(bool(self._fit_checks))
        btn = self._ensure_fit_indicator()
        lab = self.fit_summary_label
        lab.setText(summary)
        lab.setVisible(bool(self._fit_checks and summary))
        if not self._fit_checks:
            btn.hide()
        else:
            self.statusBar().clearMessage()
            v = verdict(self._fit_checks)
            btn.setText(verdict_text(self._fit_checks))
            btn.setStyleSheet(f"QPushButton {{ color: {_COLOR.get(v, '#888')}; "
                              f"font-weight: bold; text-decoration: underline; "
                              f"border: none; padding: 0 6px; }}")
            btn.show()
        dlg = getattr(self, "_fit_diag_dialog", None)
        if dlg is not None and dlg.isVisible():
            dlg.set_checks(self._fit_checks, note)

    def fit_checks(self) -> list[Check]:
        return list(getattr(self, "_fit_checks", []) or [])

    def show_fit_diagnostics(self) -> None:
        if not self.fit_checks():
            return
        dlg = getattr(self, "_fit_diag_dialog", None)
        if dlg is None:
            dlg = FitDiagnosticsDialog(
                self, on_help=lambda: self.on_help(chapter="results.2"))
            self._fit_diag_dialog = dlg
        dlg.set_checks(self.fit_checks(), getattr(self, "_fit_checks_note", ""))
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
