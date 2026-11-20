"""Equipos y sus calibraciones (Archivo → Equipos y calibraciones…).

Cada equipo guarda sus calibraciones de velocidad con la fecha desde la que
valen; al importar un espectro con ese equipo se le asigna la vigente en su
fecha de medida o la más reciente, según la regla del equipo
(:meth:`core.instruments.InstrumentLibrary.choose_calibration`). Aquí solo
hay controles: el almacenamiento vive en :mod:`core.instruments`.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Callable

from PySide6 import QtCore, QtWidgets

from mossbauer_i18n import tr
from core.instruments import (
    CalibrationRecord, InstrumentLibrary, InstrumentProfile, split_patterns,
)

_PATTERNS = (("normos", "conventions.sextet_normos_opt", "Momentos nucleares (Fitbauer y NORMOS)"),
             ("legacy", "conventions.sextet_legacy", "Histórico de Fitbauer (hasta v5.2.4)"))
_DATE_ORDERS = (("dmy", "instr.date_dmy", "día/mes/año"),
                ("mdy", "instr.date_mdy", "mes/día/año"))


def pattern_label(pattern: str) -> str:
    for value, key, default in _PATTERNS:
        if value == pattern:
            return tr(key, default=default)
    return pattern


class CalibrationEntryDialog(QtWidgets.QDialog):
    """Datos de una calibración: fecha, Vmax, patrón, IS, muestra y notas."""

    def __init__(self, parent, *, date: dt.date | None = None, vmax: float = 10.0,
                 pattern: str = "normos", isomer_shift: float | None = None,
                 sample: str = "", file_name: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("instr.add_calibration", default="Añadir calibración"))
        form = QtWidgets.QFormLayout(self)
        self.date_edit = QtWidgets.QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        d = date or dt.date.today()
        self.date_edit.setDate(QtCore.QDate(d.year, d.month, d.day))
        form.addRow(tr("instr.valid_from", default="Válida desde"), self.date_edit)
        self.vmax_spin = QtWidgets.QDoubleSpinBox()
        self.vmax_spin.setRange(-200.0, 200.0)
        self.vmax_spin.setDecimals(4)
        self.vmax_spin.setValue(float(vmax))
        form.addRow("Vmax (mm/s)", self.vmax_spin)
        self.pattern_combo = QtWidgets.QComboBox()
        for value, key, default in _PATTERNS:
            self.pattern_combo.addItem(tr(key, default=default), value)
        self.pattern_combo.setCurrentIndex(max(0, self.pattern_combo.findData(pattern)))
        form.addRow(tr("conventions.sextet_title", default="Patrón de líneas del sextete"),
                    self.pattern_combo)
        self.iso_check = QtWidgets.QCheckBox()
        self.iso_spin = QtWidgets.QDoubleSpinBox()
        self.iso_spin.setRange(-5.0, 5.0)
        self.iso_spin.setDecimals(4)
        self.iso_check.setChecked(isomer_shift is not None)
        self.iso_spin.setValue(float(isomer_shift or 0.0))
        self.iso_spin.setEnabled(isomer_shift is not None)
        self.iso_check.toggled.connect(self.iso_spin.setEnabled)
        iso_row = QtWidgets.QHBoxLayout()
        iso_row.addWidget(self.iso_check)
        iso_row.addWidget(self.iso_spin, stretch=1)
        form.addRow("IS (mm/s)", iso_row)
        self.sample_edit = QtWidgets.QLineEdit(sample)
        form.addRow(tr("label.calib_sample_name", default="Muestra"), self.sample_edit)
        self.notes_edit = QtWidgets.QLineEdit()
        form.addRow(tr("instr.notes", default="Notas"), self.notes_edit)
        if file_name:
            form.addRow(tr("instr.file", default="Fichero"), QtWidgets.QLabel(file_name))
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def record(self) -> CalibrationRecord:
        q = self.date_edit.date()
        return CalibrationRecord(
            date=dt.date(q.year(), q.month(), q.day()),
            vmax=float(self.vmax_spin.value()),
            sextet_pattern=self.pattern_combo.currentData(),
            isomer_shift=float(self.iso_spin.value()) if self.iso_check.isChecked() else None,
            sample=self.sample_edit.text().strip(),
            notes=self.notes_edit.text().strip(),
        )


class InstrumentManagerDialog(QtWidgets.QDialog):
    """Lista de equipos y, para el elegido, sus calibraciones por fecha.

    ``current_calibration`` devuelve la calibración que da el espectro activo
    (``dict`` con ``vmax``, ``isomer_shift``, ``sample``, ``path``, ``date``,
    ``sextet_pattern``) o ``None`` si no hay espectro. ``apply_calibration``
    (``(equipo, id) -> bool``) aplica la calibración seleccionada al espectro
    activo; sin ella no aparece el botón.
    """

    COLUMNS = ("date", "vmax", "pattern", "is", "sample", "file", "notes")

    def __init__(self, parent, library: InstrumentLibrary, instrument: str | None = None,
                 current_calibration: Callable[[], dict | None] | None = None,
                 apply_calibration: Callable[[str, str], bool] | None = None):
        super().__init__(parent)
        self.library = library
        self.current_calibration = current_calibration
        self.apply_calibration = apply_calibration
        self.setWindowTitle(tr("instr.title", default="Equipos y calibraciones"))
        self.resize(900, 460)
        v = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel(tr("import.instrument", default="Equipo")))
        self.instrument_combo = QtWidgets.QComboBox()
        self.instrument_combo.setMinimumWidth(220)
        top.addWidget(self.instrument_combo, stretch=1)
        self.btn_new = QtWidgets.QPushButton(tr("instr.new", default="Nuevo equipo…"))
        top.addWidget(self.btn_new)
        top.addWidget(QtWidgets.QLabel(tr("instr.date_order", default="Fechas en sus ficheros")))
        self.date_order_combo = QtWidgets.QComboBox()
        for value, key, default in _DATE_ORDERS:
            self.date_order_combo.addItem(tr(key, default=default), value)
        top.addWidget(self.date_order_combo)
        v.addLayout(top)

        # Reconocimiento automático (Cargar / arrastrar sin elegir equipo).
        match = QtWidgets.QHBoxLayout()
        match.addWidget(QtWidgets.QLabel(tr("instr.match", default="Reconocer sus ficheros por:")))
        match.addWidget(QtWidgets.QLabel(tr("instr.match_text", default="texto de la cabecera")))
        self.match_text_edit = QtWidgets.QLineEdit()
        self.match_text_edit.setPlaceholderText(tr("instr.match_text_ph", default="p. ej. WissEl; Lab B"))
        match.addWidget(self.match_text_edit, stretch=1)
        match.addWidget(QtWidgets.QLabel(tr("instr.match_name", default="nombre de fichero")))
        self.match_name_edit = QtWidgets.QLineEdit()
        self.match_name_edit.setPlaceholderText(tr("instr.match_name_ph", default="p. ej. *.ws5; FeB*"))
        match.addWidget(self.match_name_edit, stretch=1)
        tip = tr("instr.match_tip",
                 default="Varios valores separados por «;»: basta uno. Si rellenas los dos "
                         "campos, se exigen ambos. Al abrir un fichero sin elegir equipo, "
                         "el único equipo que lo reconoce se aplica solo.")
        for w in (self.match_text_edit, self.match_name_edit):
            w.setToolTip(tip)
            w.editingFinished.connect(self._on_match_changed)
        v.addLayout(match)

        self.table = QtWidgets.QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([
            tr("instr.valid_from", default="Válida desde"), "Vmax (mm/s)",
            tr("instr.pattern", default="Patrón"), "IS (mm/s)",
            tr("label.calib_sample_name", default="Muestra").rstrip(": ："),
            tr("instr.file", default="Fichero"), tr("instr.notes", default="Notas")])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table, stretch=1)
        rule_row = QtWidgets.QHBoxLayout()
        rule_row.addWidget(QtWidgets.QLabel(
            tr("instr.rule_label", default="Calibración de cada espectro:")))
        self.rule_combo = QtWidgets.QComboBox()
        self.rule_combo.addItem(tr("instr.rule_date", default="Por fecha de medida"), "date")
        self.rule_combo.addItem(tr("instr.rule_latest", default="La más reciente"), "latest")
        rule_row.addWidget(self.rule_combo)
        self.rule_hint = QtWidgets.QLabel()
        self.rule_hint.setWordWrap(True)
        rule_row.addWidget(self.rule_hint, stretch=1)
        v.addLayout(rule_row)

        row = QtWidgets.QHBoxLayout()
        self.btn_add_current = QtWidgets.QPushButton(
            tr("instr.add_current", default="Añadir el espectro actual…"))
        self.btn_add_manual = QtWidgets.QPushButton(
            tr("instr.add_manual", default="Añadir a mano…"))
        self.btn_remove = QtWidgets.QPushButton(
            tr("instr.remove_calibration", default="Eliminar calibración"))
        self.btn_apply = QtWidgets.QPushButton(
            tr("instr.apply", default="Aplicar al espectro actual"))
        self.btn_apply.setToolTip(tr(
            "instr.apply_tip", default="Usa la calibración seleccionada para el espectro "
            "abierto, sea cual sea su fecha."))
        self.btn_apply.setVisible(apply_calibration is not None)
        btn_close = QtWidgets.QPushButton(tr("button.close", default="Cerrar"))
        for b in (self.btn_add_current, self.btn_add_manual, self.btn_remove, self.btn_apply):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(btn_close)
        v.addLayout(row)

        btn_close.clicked.connect(self.accept)
        self.btn_new.clicked.connect(self._on_new)
        self.btn_add_current.clicked.connect(self._on_add_current)
        self.btn_add_manual.clicked.connect(self._on_add_manual)
        self.btn_remove.clicked.connect(self._on_remove)
        self.btn_apply.clicked.connect(self._on_apply)
        self.instrument_combo.currentIndexChanged.connect(lambda *_: self._refresh())
        self.date_order_combo.currentIndexChanged.connect(self._on_date_order)
        self.rule_combo.currentIndexChanged.connect(self._on_rule)
        self.table.itemSelectionChanged.connect(self._refresh_buttons)
        self._reload(instrument)

    # ── Equipos ───────────────────────────────────────────────────────────
    def instrument_name(self) -> str | None:
        return self.instrument_combo.currentData()

    def _reload(self, select: str | None = None) -> None:
        self.instrument_combo.blockSignals(True)
        self.instrument_combo.clear()
        for name in self.library.names():
            self.instrument_combo.addItem(name, name)
        idx = self.instrument_combo.findData(select)
        self.instrument_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.instrument_combo.blockSignals(False)
        self._refresh()

    def _on_new(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(
            self, tr("instr.new", default="Nuevo equipo…"),
            tr("import.instrument_name", default="Nombre del equipo:"))
        name = name.strip()
        if not ok or not name:
            return
        if self.library.get(name) is None:
            try:
                self.library.save(InstrumentProfile(name=name))
            except (OSError, ValueError) as exc:
                QtWidgets.QMessageBox.critical(self, tr("instr.new", default="Nuevo equipo…"),
                                               str(exc))
                return
        self._reload(name)

    def _on_date_order(self) -> None:
        profile = self.library.get(self.instrument_name() or "")
        if profile is None:
            return
        profile.date_order = self.date_order_combo.currentData()
        self.library.save(profile)

    def _on_rule(self) -> None:
        profile = self.library.get(self.instrument_name() or "")
        if profile is not None:
            profile.calibration_rule = self.rule_combo.currentData()
            self.library.save(profile)
        self._refresh_rule_hint()

    def _refresh_rule_hint(self) -> None:
        if self.rule_combo.currentData() == "latest":
            text = tr("instr.rule_latest_tip",
                      default="Se aplica la calibración más reciente del equipo, sin mirar "
                              "fechas (para ficheros que no las traen).")
        else:
            text = tr("instr.rule",
                      default="A cada espectro importado con este equipo se le aplica la "
                              "última calibración con fecha igual o anterior a la de su medida.")
        self.rule_hint.setText(text)

    def _on_match_changed(self) -> None:
        profile = self.library.get(self.instrument_name() or "")
        if profile is None:
            return
        text = split_patterns(self.match_text_edit.text())
        name = split_patterns(self.match_name_edit.text())
        if (text, name) == (profile.match_text, profile.match_name):
            return
        profile.match_text, profile.match_name = text, name
        self.library.save(profile)

    # ── Calibraciones ─────────────────────────────────────────────────────
    def _records(self) -> list[CalibrationRecord]:
        name = self.instrument_name()
        return self.library.calibrations(name) if name else []

    def _refresh(self) -> None:
        name = self.instrument_name()
        profile = self.library.get(name) if name else None
        self.date_order_combo.blockSignals(True)
        self.date_order_combo.setCurrentIndex(
            max(0, self.date_order_combo.findData(profile.date_order if profile else "dmy")))
        self.date_order_combo.blockSignals(False)
        self.date_order_combo.setEnabled(profile is not None)
        self.rule_combo.blockSignals(True)
        self.rule_combo.setCurrentIndex(
            max(0, self.rule_combo.findData(profile.calibration_rule if profile else "date")))
        self.rule_combo.blockSignals(False)
        self.rule_combo.setEnabled(profile is not None)
        self._refresh_rule_hint()
        for edit, values in ((self.match_text_edit, profile.match_text if profile else []),
                             (self.match_name_edit, profile.match_name if profile else [])):
            edit.blockSignals(True)
            edit.setText("; ".join(values))
            edit.blockSignals(False)
            edit.setEnabled(profile is not None)
        records = self._records()
        self.table.setRowCount(len(records))
        for i, r in enumerate(records):
            cells = (r.date.isoformat(), f"{r.vmax:.4f}", pattern_label(r.sextet_pattern),
                     "" if r.isomer_shift is None else f"{r.isomer_shift:.4f}",
                     r.sample, r.file_name or "", r.notes)
            for j, text in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                item.setData(QtCore.Qt.UserRole, r.id)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        has = self.instrument_name() is not None
        self.btn_add_manual.setEnabled(has)
        self.btn_add_current.setEnabled(
            has and self.current_calibration is not None
            and self.current_calibration() is not None)
        selected = has and bool(self.table.selectedItems())
        self.btn_remove.setEnabled(selected)
        self.btn_apply.setEnabled(
            selected and self.apply_calibration is not None
            and self.current_calibration is not None
            and self.current_calibration() is not None)

    def _add(self, dlg: CalibrationEntryDialog, source: Path | None) -> None:
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        try:
            self.library.add_calibration(self.instrument_name(), dlg.record(), source)
        except (OSError, KeyError, ValueError) as exc:
            QtWidgets.QMessageBox.critical(self, dlg.windowTitle(), str(exc))
            return
        self._refresh()

    def _on_add_manual(self) -> None:
        self._add(CalibrationEntryDialog(self), None)

    def _on_add_current(self) -> None:
        cur = self.current_calibration() if self.current_calibration else None
        if not cur:
            return
        path = Path(cur["path"]) if cur.get("path") else None
        self._add(CalibrationEntryDialog(
            self, date=cur.get("date"), vmax=cur["vmax"],
            pattern=cur.get("sextet_pattern", "normos"),
            isomer_shift=cur.get("isomer_shift"), sample=cur.get("sample", ""),
            file_name=path.name if path else None),
            path if path and path.is_file() else None)

    def _on_apply(self) -> None:
        items = self.table.selectedItems()
        if not items or self.apply_calibration is None:
            return
        if self.apply_calibration(self.instrument_name(), items[0].data(QtCore.Qt.UserRole)):
            self.accept()

    def _on_remove(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        record_id = items[0].data(QtCore.Qt.UserRole)
        ans = QtWidgets.QMessageBox.question(
            self, tr("instr.remove_calibration", default="Eliminar calibración"),
            tr("instr.remove_confirm", default="¿Eliminar la calibración seleccionada "
               "y su copia del espectro?"))
        if ans != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.library.remove_calibration(self.instrument_name(), record_id)
        self._refresh()
