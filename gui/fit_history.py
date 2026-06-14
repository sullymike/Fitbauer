"""Historial de ajustes: guarda los últimos ajustes (en memoria y en disco).

Cada ajuste terminado añade una entrada con la muestra, el nombre del fichero,
el modo y las métricas, más un snapshot completo (``session_payload``) que
permite **restaurar** ese ajuste con la maquinaria ya existente
(``_apply_session_payload``). Se conservan como máximo ``MAX_HISTORY`` entradas.
"""
from __future__ import annotations

import json
from collections import deque
from datetime import datetime

from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.data_io import SETTINGS_PATH

HISTORY_PATH = SETTINGS_PATH.parent / "fit_history.json"
MAX_HISTORY = 20


class FitHistoryMixin:
    # ── Estado / persistencia ────────────────────────────────────────────
    def _ensure_fit_history(self) -> None:
        if getattr(self, "fit_history", None) is None:
            self.fit_history = deque(maxlen=MAX_HISTORY)

    def _load_fit_history(self) -> None:
        self.fit_history = deque(maxlen=MAX_HISTORY)
        try:
            if HISTORY_PATH.exists():
                data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
                for entry in data[-MAX_HISTORY:]:
                    self.fit_history.append(entry)
        except Exception:
            pass

    def _save_fit_history(self) -> None:
        try:
            HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            HISTORY_PATH.write_text(
                json.dumps(list(self.fit_history), ensure_ascii=False, default=str),
                encoding="utf-8")
        except Exception:
            pass

    # ── Registro de un ajuste ────────────────────────────────────────────
    def _fit_components_summary(self) -> str:
        parts: list[str] = []
        for cp in getattr(self, "components_panels", []):
            if cp.enabled.isChecked():
                kind = getattr(cp, "kind", None) or cp.type_combo.currentText()
                parts.append(f"{cp.idx}:{tr(f'kind.{kind}', default=kind)}")
        return ", ".join(parts)

    def _record_fit_history(self, mode: str, stats: dict | None = None) -> None:
        """Añade el ajuste recién terminado al historial y persiste."""
        self._ensure_fit_history()
        try:
            payload = self._project_state().to_session_payload()
        except Exception:
            return
        stats = stats or {}
        try:
            chi2 = float(stats.get("chi2", float("nan")))
            red = float(stats.get("red_chi2", float("nan")))
        except (TypeError, ValueError):
            chi2 = red = float("nan")
        file_name = self.file.path.name if getattr(self.file, "path", None) else "—"
        summary = self._fit_components_summary() if mode == "discrete" else mode
        self.fit_history.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "file_name": file_name,
            "mode": mode,
            "chi2": chi2,
            "red_chi2": red,
            "summary": summary,
            "payload": payload,
        })
        self._save_fit_history()
        if hasattr(self, "act_fit_history"):
            self.act_fit_history.setEnabled(True)

    # ── Diálogo del historial ────────────────────────────────────────────
    def on_fit_history(self) -> None:
        self._ensure_fit_history()
        if not self.fit_history:
            QtWidgets.QMessageBox.information(
                self, tr("history.title", default="Historial de ajustes"),
                tr("history.empty", default="No hay ajustes en el historial todavía."))
            return

        # Más reciente primero.
        entries = list(self.fit_history)[::-1]
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("history.title", default="Historial de ajustes"))
        dlg.resize(760, 440)
        v = QtWidgets.QVBoxLayout(dlg)

        table = QtWidgets.QTableWidget(len(entries), 5)
        table.setHorizontalHeaderLabels([
            tr("history.col_time", default="Hora"),
            tr("history.col_file", default="Fichero"),
            tr("history.col_mode", default="Modo"),
            tr("history.col_redchi2", default="χ²ᵣ"),
            tr("history.col_summary", default="Componentes"),
        ])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        for r, e in enumerate(entries):
            ts = str(e.get("timestamp", "")).replace("T", " ")
            red = e.get("red_chi2")
            red_txt = "" if red is None or red != red else f"{float(red):.4g}"  # NaN-safe
            table.setItem(r, 0, QtWidgets.QTableWidgetItem(ts))
            table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(e.get("file_name", "—"))))
            table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(e.get("mode", ""))))
            table.setItem(r, 3, QtWidgets.QTableWidgetItem(red_txt))
            table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(e.get("summary", ""))))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        if entries:
            table.selectRow(0)
        v.addWidget(table, stretch=1)

        bb = QtWidgets.QDialogButtonBox()
        btn_restore = bb.addButton(
            tr("history.restore", default="Restaurar"), QtWidgets.QDialogButtonBox.AcceptRole)
        btn_clear = bb.addButton(
            tr("history.clear", default="Borrar historial"), QtWidgets.QDialogButtonBox.DestructiveRole)
        bb.addButton(QtWidgets.QDialogButtonBox.Close)
        v.addWidget(bb)

        def _restore() -> None:
            row = table.currentRow()
            if 0 <= row < len(entries):
                self._restore_fit_history_entry(entries[row])
                dlg.accept()

        def _clear() -> None:
            confirm = QtWidgets.QMessageBox.question(
                dlg, tr("history.clear", default="Borrar historial"),
                tr("history.clear_confirm", default="¿Borrar todo el historial de ajustes?"))
            if confirm == QtWidgets.QMessageBox.Yes:
                self.fit_history.clear()
                self._save_fit_history()
                if hasattr(self, "act_fit_history"):
                    self.act_fit_history.setEnabled(False)
                dlg.reject()

        btn_restore.clicked.connect(_restore)
        btn_clear.clicked.connect(_clear)
        bb.rejected.connect(dlg.reject)
        dlg.exec()

    def _restore_fit_history_entry(self, entry: dict) -> None:
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            return
        try:
            self._apply_session_payload(payload)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("history.title", default="Historial de ajustes"),
                f"{type(exc).__name__}: {exc}")
            return
        self.statusBar().showMessage(
            tr("history.restored", name=entry.get("file_name", "—"),
               default=f"Ajuste restaurado: {entry.get('file_name', '—')}"), 5000)
