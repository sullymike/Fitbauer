"""Ventana de importación: ver cómo se lee un fichero y corregirlo.

Muestra el texto con cabecera, datos y pie marcados, lo que el lector
genérico (:mod:`core.spectrum_import`) ha deducido y una vista previa del
espectro tal como quedaría. Cada deducción puede corregirse; las correcciones,
junto con la forma de onda y el plegado, se guardan como **equipo**
(:mod:`core.instruments`) para que los ficheros siguientes de ese equipo
entren sin tocar nada. El cálculo vive en ``core``; aquí solo hay controles.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from mossbauer_i18n import tr
from core.folding import (
    FOLD_MODES, channel_velocity_axis, detect_fold_center, prepare_channel_counts,
)
from core.constants import convert_vmax
from core.instruments import InstrumentLibrary, InstrumentProfile
from core.spectrum_import import (
    COLUMN_ROLES, Y_KINDS, ImportedSpectrum, ImportHints, measurement_date,
    parse_spectrum_text, read_text,
)

_ROLE_DEFAULTS = {"channel": "Canal", "velocity": "Velocidad", "y": "Intensidad",
                  "sigma": "Error (σ)", "ignore": "Ignorar"}
_KIND_DEFAULTS = {"counts": "Cuentas", "transmission": "Transmisión",
                  "transmission_percent": "Transmisión (%)",
                  "absorption": "Absorción", "absorption_percent": "Absorción (%)",
                  "transmission_deviation": "Transmisión − 1"}
_FOLD_DEFAULTS = {"fold": "Doblar", "single_sweep": "Sin doblar: un solo barrido",
                  "two_branches": "Sin doblar: dos ramas"}

# Fondo de las líneas: datos y cabecera/pie (semitransparentes: valen en
# tema claro y oscuro).
_DATA_BG = QtGui.QColor(76, 175, 80, 55)
_OTHER_BG = QtGui.QColor(158, 158, 158, 45)


def role_label(role: str) -> str:
    return tr(f"import.role.{role}", default=_ROLE_DEFAULTS[role])


def kind_label(kind: str) -> str:
    return tr(f"import.kind.{kind}", default=_KIND_DEFAULTS[kind])


class ImportDialog(QtWidgets.QDialog):
    """Importa un fichero con vista previa, correcciones y perfiles de equipo."""

    def __init__(self, parent, path: Path, *, library: InstrumentLibrary,
                 vmax: float = 12.0, drive_form: str = "triangular",
                 fold_mode: str = "fold", reverse: bool = False,
                 instrument: str | None = None, sextet_pattern: str = "normos",
                 current_calibration=None):
        super().__init__(parent)
        self.path = Path(path)
        self.library = library
        self.vmax = float(vmax)
        self.sextet_pattern = sextet_pattern
        self.current_calibration = current_calibration
        self.text = read_text(self.path)
        self.result: ImportedSpectrum | None = None
        self._updating = False
        self._col_combos: list[QtWidgets.QComboBox] = []
        self.setWindowTitle(tr("import.title", default="Importar espectro") + f" — {self.path.name}")
        self.resize(1100, 720)
        self._build()
        self._set_preparation(drive_form, fold_mode, reverse)
        # Un equipo que reconoce el fichero (nombre/cabecera) manda sobre el
        # del espectro anterior; con varios candidatos no se elige ninguno.
        try:
            found = [p.name for p in self.library.recognize(self.path)]
        except OSError:
            found = []
        self.recognized = found[0] if len(found) == 1 else None
        self.ambiguous = found if len(found) > 1 else []
        if self.recognized:
            instrument = self.recognized
        self._reload_instruments(instrument)
        if instrument and self.library.get(instrument) is not None:
            self._apply_profile(self.library.get(instrument))
        self.refresh()

    # ── Construcción ──────────────────────────────────────────────────────
    def _build(self) -> None:
        outer = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel(tr("import.instrument", default="Equipo")))
        self.instrument_combo = QtWidgets.QComboBox()
        self.instrument_combo.setMinimumWidth(220)
        top.addWidget(self.instrument_combo, stretch=1)
        self.btn_save_instrument = QtWidgets.QPushButton(
            tr("import.save_instrument", default="Guardar como equipo…"))
        self.btn_delete_instrument = QtWidgets.QPushButton(
            tr("import.delete_instrument", default="Eliminar equipo"))
        self.btn_calibrations = QtWidgets.QPushButton(
            tr("import.calibrations", default="Calibraciones…"))
        top.addWidget(self.btn_save_instrument)
        top.addWidget(self.btn_delete_instrument)
        top.addWidget(self.btn_calibrations)
        outer.addLayout(top)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.view = QtWidgets.QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.view.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        lines = self.text.splitlines()
        self.view.setPlainText("\n".join(f"{i:5d} │ {l}" for i, l in enumerate(lines, 1)))
        split.addWidget(self.view)

        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        form = QtWidgets.QFormLayout()

        # Líneas de datos (1-based, inclusivas en pantalla).
        rng = QtWidgets.QHBoxLayout()
        self.range_auto = QtWidgets.QCheckBox(tr("import.auto", default="automático"))
        self.range_auto.setChecked(True)
        n_lines = max(1, len(lines))
        self.start_spin = QtWidgets.QSpinBox()
        self.end_spin = QtWidgets.QSpinBox()
        for sp in (self.start_spin, self.end_spin):
            sp.setRange(1, n_lines)
        rng.addWidget(self.range_auto)
        rng.addWidget(self.start_spin)
        rng.addWidget(QtWidgets.QLabel("–"))
        rng.addWidget(self.end_spin)
        form.addRow(tr("import.data_lines", default="Líneas de datos"), rng)

        self.sep_combo = QtWidgets.QComboBox()
        for value, key, default in ((None, "import.auto", "automático"),
                                    ("whitespace", "import.sep_whitespace",
                                     "espacios, tabuladores o ;"),
                                    ("comma", "import.sep_comma", "comas")):
            self.sep_combo.addItem(tr(key, default=default), value)
        form.addRow(tr("import.separator", default="Separador"), self.sep_combo)
        self.dec_combo = QtWidgets.QComboBox()
        for value, label in ((None, tr("import.auto", default="automático")),
                             (".", "."), (",", ",")):
            self.dec_combo.addItem(label, value)
        form.addRow(tr("import.decimal", default="Separador decimal"), self.dec_combo)

        cols = QtWidgets.QVBoxLayout()
        self.cols_auto = QtWidgets.QCheckBox(tr("import.auto", default="automático"))
        self.cols_auto.setChecked(True)
        cols.addWidget(self.cols_auto)
        self.cols_box = QtWidgets.QHBoxLayout()
        cols.addLayout(self.cols_box)
        form.addRow(tr("import.columns", default="Columnas"), cols)

        self.rowmajor_combo = QtWidgets.QComboBox()
        for value, key, default in ((None, "import.auto", "automático"),
                                    (True, "import.yes", "sí"), (False, "import.no", "no")):
            self.rowmajor_combo.addItem(tr(key, default=default), value)
        form.addRow(tr("import.row_major", default="Varias cuentas por línea"),
                    self.rowmajor_combo)

        self.kind_combo = QtWidgets.QComboBox()
        self.kind_combo.addItem(tr("import.auto", default="automático"), None)
        for kind in Y_KINDS:
            self.kind_combo.addItem(kind_label(kind), kind)
        form.addRow(tr("import.intensity", default="Intensidad"), self.kind_combo)

        self.drive_combo = QtWidgets.QComboBox()
        self.drive_combo.addItem(tr("drive.triangular", default="Triangular"), "triangular")
        self.drive_combo.addItem(tr("drive.sine", default="Senoidal"), "sine")
        form.addRow(tr("drive.model_label", default="Forma de onda"), self.drive_combo)
        self.fold_combo = QtWidgets.QComboBox()
        for mode in FOLD_MODES:
            self.fold_combo.addItem(tr(f"fold.{mode}", default=_FOLD_DEFAULTS[mode]), mode)
        form.addRow(tr("fold.label", default="Plegado"), self.fold_combo)
        self.reverse_check = QtWidgets.QCheckBox(tr("fold.reverse", default="Invertir sentido"))
        form.addRow("", self.reverse_check)
        rv.addLayout(form)

        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        rv.addWidget(self.summary)

        self.figure = Figure(figsize=(5, 3), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumHeight(220)
        rv.addWidget(self.canvas, stretch=1)
        split.addWidget(right)
        split.setSizes([480, 620])
        outer.addWidget(split, stretch=1)

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        for w in (self.range_auto, self.cols_auto, self.reverse_check):
            w.toggled.connect(self._on_auto_toggled)
        for sp in (self.start_spin, self.end_spin):
            sp.valueChanged.connect(lambda *_: self.refresh())
        for cb in (self.sep_combo, self.dec_combo, self.rowmajor_combo, self.kind_combo,
                   self.drive_combo, self.fold_combo):
            cb.currentIndexChanged.connect(lambda *_: self.refresh())
        self.instrument_combo.currentIndexChanged.connect(self._on_instrument_selected)
        self.btn_save_instrument.clicked.connect(self._on_save_instrument)
        self.btn_delete_instrument.clicked.connect(self._on_delete_instrument)
        self.btn_calibrations.clicked.connect(self._on_calibrations)

    # ── Estado de los controles ↔ hints / equipo ─────────────────────────
    def hints(self) -> ImportHints:
        """Solo lo que el usuario ha fijado; lo demás queda en automático."""
        h = ImportHints(separator=self.sep_combo.currentData(),
                        decimal=self.dec_combo.currentData(),
                        row_major=self.rowmajor_combo.currentData(),
                        y_kind=self.kind_combo.currentData())
        if not self.range_auto.isChecked():
            h.data_start = self.start_spin.value() - 1
            h.data_end = self.end_spin.value()
        if not self.cols_auto.isChecked() and self._col_combos:
            h.columns = tuple(c.currentData() for c in self._col_combos)
        return h

    def drive_form(self) -> str:
        return self.drive_combo.currentData()

    def fold_mode(self) -> str:
        return self.fold_combo.currentData()

    def reverse(self) -> bool:
        return self.reverse_check.isChecked()

    def instrument_name(self) -> str | None:
        return self.instrument_combo.currentData()

    @staticmethod
    def _select(combo: QtWidgets.QComboBox, value) -> None:
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _set_preparation(self, drive: str, fold: str, reverse: bool) -> None:
        self._select(self.drive_combo, drive)
        self._select(self.fold_combo, fold)
        self.reverse_check.setChecked(bool(reverse))

    def _apply_profile(self, profile: InstrumentProfile | None) -> None:
        """Pone los controles como dice el equipo (o todo en automático)."""
        h = profile.import_hints if profile else ImportHints()
        self._updating = True
        try:
            self._select(self.sep_combo, h.separator)
            self._select(self.dec_combo, h.decimal)
            self._select(self.rowmajor_combo, h.row_major)
            self._select(self.kind_combo, h.y_kind)
            self.range_auto.setChecked(h.data_start is None)
            if h.data_start is not None:
                self.start_spin.setValue(h.data_start + 1)
                self.end_spin.setValue(h.data_end or self.end_spin.maximum())
            self.cols_auto.setChecked(h.columns is None)
            if h.columns is not None:
                self._rebuild_columns(h.columns, editable=True)
            if profile is not None:
                self._set_preparation(profile.drive_form, profile.fold_mode,
                                      profile.reverse_velocity)
        finally:
            self._updating = False

    def _rebuild_columns(self, roles, editable: bool) -> None:
        roles = tuple(roles)
        if [c.currentData() for c in self._col_combos] == list(roles):
            for c in self._col_combos:
                c.setEnabled(editable)
            return
        while self.cols_box.count():
            item = self.cols_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._col_combos = []
        for role in roles:
            combo = QtWidgets.QComboBox()
            for r in COLUMN_ROLES:
                combo.addItem(role_label(r), r)
            self._select(combo, role)
            combo.setEnabled(editable)
            combo.currentIndexChanged.connect(lambda *_: self.refresh())
            self.cols_box.addWidget(combo)
            self._col_combos.append(combo)

    # ── Equipos ───────────────────────────────────────────────────────────
    def _reload_instruments(self, select: str | None = None) -> None:
        self._updating = True
        try:
            self.instrument_combo.clear()
            self.instrument_combo.addItem(
                tr("import.no_instrument", default="(detección automática)"), None)
            for name in self.library.names():
                self.instrument_combo.addItem(name, name)
            self._select(self.instrument_combo, select)
        finally:
            self._updating = False
        self.btn_delete_instrument.setEnabled(self.instrument_name() is not None)

    def _on_instrument_selected(self) -> None:
        if self._updating:
            return
        name = self.instrument_name()
        self.btn_delete_instrument.setEnabled(name is not None)
        self._apply_profile(self.library.get(name) if name else None)
        self.refresh()

    def _on_save_instrument(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(
            self, tr("import.save_instrument", default="Guardar como equipo…"),
            tr("import.instrument_name", default="Nombre del equipo:"),
            text=self.instrument_name() or "")
        name = name.strip()
        if not ok or not name:
            return
        old = self.library.get(name)
        profile = InstrumentProfile(
            name=name, import_hints=self.hints(), drive_form=self.drive_form(),
            fold_mode=self.fold_mode(), reverse_velocity=self.reverse(),
            date_order=old.date_order if old else "dmy",
            notes=old.notes if old else "",
            match_text=list(old.match_text) if old else [],
            match_name=list(old.match_name) if old else [])
        try:
            self.library.save(profile)
        except (OSError, ValueError) as exc:
            QtWidgets.QMessageBox.critical(self, tr("import.save_instrument",
                                                    default="Guardar como equipo…"), str(exc))
            return
        self._reload_instruments(name)

    def _on_calibrations(self) -> None:
        from gui.instrument_manager import InstrumentManagerDialog
        InstrumentManagerDialog(self, self.library, self.instrument_name(),
                                self.current_calibration).exec()
        self._reload_instruments(self.instrument_name())
        self.refresh()

    def assigned_calibration(self):
        """``(registro | None, fecha | None, origen)`` según el equipo elegido."""
        name = self.instrument_name()
        r = self.result
        if not name or r is None or r.x_kind != "channel":
            return None, None, None
        profile = self.library.get(name)
        if profile is None:
            return None, None, None
        date, origin = measurement_date(r, self.path, profile.date_order)
        if date is None:
            return None, None, None
        return self.library.calibration_for(name, date), date, origin

    def preview_vmax(self) -> float:
        record, _d, _o = self.assigned_calibration()
        if record is None:
            return self.vmax
        return convert_vmax(record.vmax, record.sextet_pattern, self.sextet_pattern)

    def _on_delete_instrument(self) -> None:
        name = self.instrument_name()
        if not name:
            return
        ans = QtWidgets.QMessageBox.question(
            self, tr("import.delete_instrument", default="Eliminar equipo"),
            tr("import.delete_confirm", name=name,
               default="¿Eliminar el equipo «{name}»? Sus ficheros no se tocan."))
        if ans != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.library.delete(name)
        self._reload_instruments(None)
        self._apply_profile(None)
        self.refresh()

    # ── Lectura y vista previa ────────────────────────────────────────────
    def _on_auto_toggled(self) -> None:
        if self._updating:
            return
        if not self.range_auto.isChecked() and self.result is not None:
            # Al pasar a manual se parte de lo detectado.
            self._updating = True
            self.start_spin.setValue(self.result.data_start + 1)
            self.end_spin.setValue(self.result.data_end)
            self._updating = False
        self.refresh()

    def refresh(self) -> None:
        if self._updating:
            return
        self.start_spin.setEnabled(not self.range_auto.isChecked())
        self.end_spin.setEnabled(not self.range_auto.isChecked())
        try:
            self.result = parse_spectrum_text(self.text, self.hints())
        except ValueError as exc:
            self.result = None
            self.summary.setText(f"<b>{tr('import.cannot_read', default='No se puede leer')}:</b> {exc}")
            self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)
            self._highlight(None)
            self._plot(None)
            return
        r = self.result
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(True)
        self._updating = True
        try:
            if self.range_auto.isChecked():
                self.start_spin.setValue(r.data_start + 1)
                self.end_spin.setValue(r.data_end)
            if self.cols_auto.isChecked() or len(self._col_combos) != len(r.columns):
                self._rebuild_columns(r.columns, editable=not self.cols_auto.isChecked())
        finally:
            self._updating = False
        self.fold_combo.setEnabled(r.x_kind == "channel" and self.drive_form() != "sine")
        self.drive_combo.setEnabled(r.x_kind == "channel")
        self.reverse_check.setEnabled(r.x_kind == "channel")
        self.summary.setText(self._summary_text(r))
        self._highlight(r)
        self._plot(r)

    def _summary_text(self, r: ImportedSpectrum) -> str:
        if r.x_kind == "velocity":
            what = tr("import.summary_velocity", n=r.y.size, kind=kind_label(r.y_kind),
                      default="Eje de velocidad · {n} puntos · {kind}")
        else:
            what = tr("import.summary_channels", n=r.y.size, kind=kind_label(r.y_kind),
                      default="{n} canales · {kind}")
        parts = [f"<b>{what}</b>",
                 tr("import.summary_layout", start=r.data_start + 1, end=r.data_end,
                    header=len(r.header), footer=len(r.footer),
                    default="datos en las líneas {start}–{end} · cabecera {header} · pie {footer}")]
        if r.metadata:
            meta = ", ".join(f"{k}: {v}" for k, v in list(r.metadata.items())[:6])
            parts.append(tr("import.summary_metadata", default="Metadatos") + f": {meta}")
        if r.dates:
            parts.append(tr("import.summary_dates", default="Fechas") + ": " + ", ".join(r.dates[:3]))
        for w in r.warnings:
            parts.append("⚠ " + tr(f"import.warn.{w}", default=w))
        if self.recognized and self.instrument_name() == self.recognized:
            parts.append(tr("import.recognized", name=self.recognized,
                            default="Equipo reconocido por su nombre o cabecera: {name}"))
        elif self.ambiguous:
            parts.append("⚠ " + tr("import.ambiguous", names=", ".join(self.ambiguous),
                                   default="Lo reconocen varios equipos: {names}. Elige uno."))
        if self.instrument_name() and r.x_kind == "channel":
            record, date, origin = self.assigned_calibration()
            if date is None:
                parts.append("⚠ " + tr("import.no_date",
                                       default="Sin fecha de medida: no se asignará calibración."))
            else:
                when = date.isoformat() + (
                    " " + tr("import.date_from_file", default="(fecha del fichero)")
                    if origin == "file" else "")
                if record is None:
                    parts.append("⚠ " + tr(
                        "import.no_calibration", date=when,
                        default="Medida {date}: el equipo no tiene calibraciones "
                                "de esa fecha o anteriores."))
                else:
                    parts.append(tr(
                        "import.calibration", date=when, cal=record.date.isoformat(),
                        vmax=f"{self.preview_vmax():.4f}",
                        default="Medida {date} → calibración del {cal}, Vmax = {vmax} mm/s"))
        return "<br>".join(parts)

    def _highlight(self, r: ImportedSpectrum | None) -> None:
        sels = []
        if r is not None:
            doc = self.view.document()
            for i in range(doc.blockCount()):
                sel = QtWidgets.QTextEdit.ExtraSelection()
                sel.format.setBackground(_DATA_BG if r.data_start <= i < r.data_end else _OTHER_BG)
                sel.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
                sel.cursor = QtGui.QTextCursor(doc.findBlockByNumber(i))
                sels.append(sel)
            self.view.setTextCursor(QtGui.QTextCursor(doc.findBlockByNumber(r.data_start)))
            self.view.centerCursor()
        self.view.setExtraSelections(sels)

    def preview_data(self) -> tuple[np.ndarray, np.ndarray] | None:
        """Velocidad y transmisión como quedarían al cargar (para la vista previa)."""
        r = self.result
        if r is None:
            return None
        if r.x_kind == "velocity":
            order = np.argsort(r.x, kind="stable")
            return r.x[order], r.transmission()[0][order]
        if not r.is_counts:
            return None
        center = detect_fold_center(r.y, drive_form=self.drive_form(),
                                    fold_mode=self.fold_mode())
        _d, _s, y, _n = prepare_channel_counts(
            r.y, center, fold_mode=self.fold_mode(), drive_form=self.drive_form())
        v = channel_velocity_axis(r.y.size, self.preview_vmax(), y.size, center=center,
                                  fold_mode=self.fold_mode(), drive_form=self.drive_form(),
                                  reverse=self.reverse())
        return v, y

    def _plot(self, r: ImportedSpectrum | None) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        data = self.preview_data() if r is not None else None
        if data is not None:
            v, y = data
            ax.plot(v, y, ".", ms=2.5)
            ax.set_xlabel(tr("import.preview_velocity", default="Velocidad (mm/s)"))
            ax.set_ylabel(tr("import.preview_transmission", default="Transmisión relativa"))
        self.canvas.draw_idle()
