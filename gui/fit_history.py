"""Historial de ajustes en árbol (en memoria y en disco).

Cada ajuste terminado añade una entrada con el fichero, el modo, las métricas
y un snapshot completo (``session_payload``) que permite **restaurarlo** con
la maquinaria ya existente (``_apply_session_payload``). Cada entrada guarda
también de qué ajuste partió (``parent``): restaurar una entrada y volver a
ajustar abre una rama desde ella, sin perder las posteriores. La ventana
recuerda el nodo actual (``_history_head``); cargar otro espectro o sesión
empieza un árbol nuevo. La lógica sin Qt está en ``gui/history_tree.py``.
"""
from __future__ import annotations

import json
from datetime import datetime

from PySide6 import QtCore, QtGui, QtWidgets

from mossbauer_i18n import tr
from gui import history_tree as ht
from core.data_io import SETTINGS_PATH

HISTORY_PATH = SETTINGS_PATH.parent / "fit_history.json"
DEFAULT_MAX_HISTORY = 50    # por fichero; configurable por el usuario
MIN_MAX_HISTORY = 1
MAX_MAX_HISTORY = 500       # tope para que reescribir el JSON siga siendo barato


class FitHistoryMixin:
    # ── Estado / persistencia ────────────────────────────────────────────
    def _ensure_fit_history(self) -> None:
        if getattr(self, "fit_history", None) is None:
            self.fit_history = []
        if not hasattr(self, "_history_head"):
            self._history_head = None

    def _load_fit_history(self) -> None:
        """Carga el historial y el tope configurado desde disco.

        Formato en disco: ``{"max_entries": int, "entries": [...]}``; se acepta
        también el antiguo (lista simple). Las entradas sin ``id`` (anteriores
        al árbol) se encadenan en orden dentro de cada fichero.
        """
        self.fit_history_max = DEFAULT_MAX_HISTORY
        self._history_head = None
        entries: list = []
        try:
            if HISTORY_PATH.exists():
                data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.fit_history_max = self._clamp_max(
                        int(data.get("max_entries", DEFAULT_MAX_HISTORY)))
                    entries = data.get("entries", []) or []
                elif isinstance(data, list):   # formato antiguo
                    entries = data
        except Exception:
            pass
        self.fit_history = ht.prune(ht.migrate(entries), self.fit_history_max)

    def _save_fit_history(self) -> None:
        try:
            HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            HISTORY_PATH.write_text(
                json.dumps({"max_entries": getattr(self, "fit_history_max", DEFAULT_MAX_HISTORY),
                            "entries": list(self.fit_history)},
                           ensure_ascii=False, default=str),
                encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _clamp_max(n: int) -> int:
        return max(MIN_MAX_HISTORY, min(MAX_MAX_HISTORY, int(n)))

    def _prune_fit_history(self) -> None:
        head = getattr(self, "_history_head", None)
        self.fit_history = ht.prune(self.fit_history, self.fit_history_max,
                                    protect={head} if head else frozenset())

    def _set_fit_history_max(self, n: int) -> None:
        """Cambia el tope de entradas por fichero, recorta y persiste."""
        self._ensure_fit_history()
        new_max = self._clamp_max(n)
        if new_max == getattr(self, "fit_history_max", DEFAULT_MAX_HISTORY):
            return
        self.fit_history_max = new_max
        self._prune_fit_history()
        self._save_fit_history()

    def _history_entry(self, entry_id: str | None) -> dict | None:
        if not entry_id:
            return None
        return next((e for e in getattr(self, "fit_history", None) or []
                     if e.get("id") == entry_id), None)

    def _history_reset_branch(self) -> None:
        """Otro espectro u otra sesión: el próximo ajuste empieza árbol."""
        self._history_head = None

    # ── Registro de un ajuste ────────────────────────────────────────────
    def _fit_components_summary(self) -> str:
        parts: list[str] = []
        for cp in getattr(self, "components_panels", []):
            if cp.enabled.isChecked():
                kind = getattr(cp, "kind", None) or cp.type_combo.currentText()
                parts.append(f"{cp.idx}:{tr(f'kind.{kind}', default=kind)}")
        return ", ".join(parts)

    def _record_fit_history(self, mode: str, stats: dict | None = None) -> None:
        """Añade el ajuste recién terminado, colgado del nodo actual, y persiste."""
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
        path = getattr(self.file, "path", None)
        file_name = path.name if path else "—"
        key = str(path) if path else file_name
        summary = self._fit_components_summary() if mode == "discrete" else mode
        parent = self._history_entry(self._history_head)
        if parent is not None and ht.file_key(parent) != key:
            parent = None
        entry = {
            "id": ht.new_id(),
            "parent": parent["id"] if parent else None,
            "note": "",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "file_name": file_name,
            "file_path": key,
            "mode": mode,
            "chi2": chi2,
            "red_chi2": red,
            "summary": summary,
            "payload": payload,
        }
        self.fit_history.append(entry)
        self._history_head = entry["id"]
        self._prune_fit_history()
        self._save_fit_history()
        if hasattr(self, "act_fit_history"):
            self.act_fit_history.setEnabled(True)

    # ── Diálogo del historial ────────────────────────────────────────────
    def history_changes_text(self, entry: dict) -> str:
        """Qué cambió respecto al ajuste del que partió (una línea por cambio)."""
        parent = self._history_entry(entry.get("parent"))
        if parent is None:
            return tr("history.diff_root")
        lines = ht.describe_changes(parent, entry, label=self._param_display_name, tr=tr)
        return tr("history.diff_title") + "\n" + "\n".join(f"• {x}" for x in lines)

    def on_fit_history(self) -> None:
        self._ensure_fit_history()
        if not self.fit_history:
            QtWidgets.QMessageBox.information(
                self, tr("history.title", default="Historial de ajustes"),
                tr("history.empty", default="No hay ajustes en el historial todavía."))
            return
        dlg = HistoryDialog(self)
        self._history_dialog = dlg
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
        # Lo siguiente que se ajuste cuelga de aquí: una rama nueva.
        self._history_head = entry.get("id")
        self.statusBar().showMessage(
            tr("history.restored", name=entry.get("file_name", "—"),
               default=f"Ajuste restaurado: {entry.get('file_name', '—')}"), 5000)


class HistoryDialog(QtWidgets.QDialog):
    """Historial en árbol: un grupo por fichero y, debajo, de qué ajuste
    salió cada uno. Nota editable y, para la entrada elegida, qué cambió
    respecto a su padre."""

    COLS = ("history.col_time", "history.col_redchi2", "history.col_dchi2",
            "history.col_summary", "history.col_note")
    NOTE_COL = 4

    def __init__(self, win):
        super().__init__(win)
        self._win = win
        self.setWindowTitle(tr("history.title", default="Historial de ajustes"))
        self.resize(880, 560)
        v = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel(tr("history.hint"))
        hint.setWordWrap(True)
        v.addWidget(hint)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(len(self.COLS))
        self.tree.setHeaderLabels([tr(k) for k in self.COLS])
        self.tree.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.currentItemChanged.connect(lambda *_: self._on_current())
        v.addWidget(self.tree, stretch=3)
        self.changes = QtWidgets.QLabel()
        self.changes.setWordWrap(True)
        self.changes.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.changes.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.changes.setMinimumHeight(90)
        v.addWidget(self.changes, stretch=1)

        cfg = QtWidgets.QHBoxLayout()
        cfg.addWidget(QtWidgets.QLabel(tr("history.max_label", default="Máximo por fichero:")))
        self.spin = QtWidgets.QSpinBox()
        self.spin.setRange(MIN_MAX_HISTORY, MAX_MAX_HISTORY)
        self.spin.setValue(getattr(win, "fit_history_max", DEFAULT_MAX_HISTORY))
        self.spin.valueChanged.connect(self._on_max_changed)
        cfg.addWidget(self.spin)
        cfg.addStretch(1)
        v.addLayout(cfg)

        bb = QtWidgets.QDialogButtonBox()
        self.btn_restore = bb.addButton(tr("history.restore", default="Restaurar"),
                                        QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        btn_clear = bb.addButton(tr("history.clear", default="Borrar historial"),
                                 QtWidgets.QDialogButtonBox.ButtonRole.DestructiveRole)
        bb.addButton(QtWidgets.QDialogButtonBox.StandardButton.Close)
        self.btn_restore.clicked.connect(self._restore)
        btn_clear.clicked.connect(self._clear)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._populate()

    # ── Construcción del árbol ───────────────────────────────────────────
    def _populate(self) -> None:
        win = self._win
        entries = list(win.fit_history)
        head = getattr(win, "_history_head", None)
        self._building = True
        self.tree.clear()
        self._items: dict[str, QtWidgets.QTreeWidgetItem] = {}
        current = None
        by_file: dict[str, list[dict]] = {}
        for e in entries:
            by_file.setdefault(ht.file_key(e), []).append(e)
        last_use = {k: max(entries.index(e) for e in g) for k, g in by_file.items()}
        bold = QtGui.QFont()
        bold.setBold(True)
        for key in sorted(by_file, key=last_use.get, reverse=True):
            group = by_file[key]
            top = QtWidgets.QTreeWidgetItem(
                [tr("history.group", name=group[-1].get("file_name") or key, n=len(group))])
            top.setToolTip(0, key)
            top.setFont(0, bold)
            self.tree.addTopLevelItem(top)
            roots, kids = ht.children_map(group)

            def add(parent_item, e, parent_entry):
                item = self._make_item(e, parent_entry)
                parent_item.addChild(item)
                self._items[e["id"]] = item
                for c in kids.get(e["id"], []):
                    add(item, c, e)
                return item

            for r in roots:
                add(top, r, None)
            top.setExpanded(True)
        self.tree.expandAll()
        for i in range(len(self.COLS) - 1):
            self.tree.resizeColumnToContents(i)
        if head and head in self._items:
            item = self._items[head]
            for c in range(len(self.COLS)):
                item.setFont(c, bold)
            item.setText(0, f"▶ {item.text(0)}")
            item.setToolTip(0, tr("history.current"))
            current = item
        self._building = False
        if current is None and entries:
            current = self._items.get(entries[-1].get("id"))
        if current is not None:
            self.tree.setCurrentItem(current)
            self.tree.scrollToItem(current)
        self._on_current()

    def _make_item(self, e: dict, parent: dict | None) -> QtWidgets.QTreeWidgetItem:
        ts = str(e.get("timestamp", "")).replace("T", " ")
        red = ht._fmt_chi2(e.get("red_chi2")) or ""
        dchi = ""
        if parent is not None:
            try:
                d = float(e.get("red_chi2")) - float(parent.get("red_chi2"))
                if d == d:
                    dchi = f"{d:+.3g}"
            except (TypeError, ValueError):
                pass
        mode = e.get("mode", "")
        summary = str(e.get("summary", "")) if mode == "discrete" else str(mode)
        item = QtWidgets.QTreeWidgetItem([ts, red, dchi, summary, str(e.get("note", ""))])
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, e.get("id"))
        item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
        item.setToolTip(self.NOTE_COL, tr("history.note_tip"))
        if dchi:
            item.setForeground(2, QtGui.QBrush(QtGui.QColor(
                "#15803d" if dchi.startswith("-") else "#b91c1c")))
        return item

    # ── Interacción ──────────────────────────────────────────────────────
    def _entry_of(self, item) -> dict | None:
        if item is None:
            return None
        return self._win._history_entry(item.data(0, QtCore.Qt.ItemDataRole.UserRole))

    def _on_current(self) -> None:
        e = self._entry_of(self.tree.currentItem())
        self.btn_restore.setEnabled(e is not None)
        self.changes.setText(self._win.history_changes_text(e) if e is not None
                             else tr("history.pick"))

    def _on_double_click(self, item, column: int) -> None:
        if column == self.NOTE_COL and self._entry_of(item) is not None:
            self.tree.editItem(item, column)

    def _on_item_changed(self, item, column: int) -> None:
        if getattr(self, "_building", False) or column != self.NOTE_COL:
            return
        e = self._entry_of(item)
        if e is None:
            return
        e["note"] = item.text(column).strip()
        self._win._save_fit_history()

    def _on_max_changed(self, n: int) -> None:
        self._win._set_fit_history_max(n)
        self._populate()

    def _restore(self) -> None:
        e = self._entry_of(self.tree.currentItem())
        if e is not None:
            self._win._restore_fit_history_entry(e)
            self.accept()

    def _clear(self) -> None:
        win = self._win
        confirm = QtWidgets.QMessageBox.question(
            self, tr("history.clear", default="Borrar historial"),
            tr("history.clear_confirm", default="¿Borrar todo el historial de ajustes?"))
        if confirm == QtWidgets.QMessageBox.StandardButton.Yes:
            win.fit_history.clear()
            win._history_head = None
            win._save_fit_history()
            if hasattr(win, "act_fit_history"):
                win.act_fit_history.setEnabled(False)
            self.reject()
