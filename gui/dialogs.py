"""Diálogos auxiliares de la interfaz Qt de Fitbauer."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PySide6 import QtWidgets
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from mossbauer_i18n import tr
from core.folding import (
    read_ws5_counts, find_best_integer_or_half_center, fold_and_normalize,
    velocity_axis,
)
from core.fit_engine import fit_discrete
from core.batch_fit import extract_metadata, write_results_csv, collect_trend_data

if TYPE_CHECKING:
    from mossbauer_qt import MossbauerQtWindow

ROOT = Path(__file__).resolve().parents[1]


class ConstraintsDialog(QtWidgets.QDialog):
    """Editor de restricciones lineales: target = factor·source + offset."""

    def __init__(self, parent: "MossbauerQtWindow"):
        super().__init__(parent)
        self.setWindowTitle(tr("options.constraints"))
        self.resize(660, 380)
        self.parent_win = parent
        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(QtWidgets.QLabel(
            "<i>target = factor · source + offset</i>"))
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["target", "factor", "source", "offset"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        v.addWidget(self.table, stretch=1)
        row = QtWidgets.QHBoxLayout()
        btn_add = QtWidgets.QPushButton("+")
        btn_add.clicked.connect(self._add_row)
        btn_rm = QtWidgets.QPushButton("−")
        btn_rm.clicked.connect(self._remove_row)
        row.addWidget(btn_add); row.addWidget(btn_rm); row.addStretch(1)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self._apply_and_accept)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        v.addLayout(row)
        self._param_keys = self._collect_param_keys()
        self._load_existing()

    def _collect_param_keys(self) -> list[str]:
        """Claves de parámetros disponibles (de las 3 componentes)."""
        keys: list[str] = []
        for cp in self.parent_win.components_panels:
            for name in cp.params:
                keys.append(f"s{cp.idx}_{name}")
        return keys

    def _load_existing(self) -> None:
        constraints = getattr(self.parent_win, "constraints", []) or []
        for c in constraints:
            self._add_row(c)

    def _make_combo(self, current: str = "") -> QtWidgets.QComboBox:
        cb = QtWidgets.QComboBox()
        cb.addItems(self._param_keys)
        if current in self._param_keys:
            cb.setCurrentText(current)
        return cb

    def _make_spin(self, value: float, decimals: int = 4) -> QtWidgets.QDoubleSpinBox:
        s = QtWidgets.QDoubleSpinBox()
        s.setRange(-1e6, 1e6); s.setDecimals(decimals); s.setSingleStep(0.1)
        s.setValue(float(value))
        return s

    def _add_row(self, c: dict | None = None) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setCellWidget(r, 0, self._make_combo((c or {}).get("target", "")))
        self.table.setCellWidget(r, 1, self._make_spin((c or {}).get("factor", 1.0)))
        self.table.setCellWidget(r, 2, self._make_combo((c or {}).get("source", "")))
        self.table.setCellWidget(r, 3, self._make_spin((c or {}).get("offset", 0.0)))

    def _remove_row(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def _apply_and_accept(self) -> None:
        new: list[dict] = []
        for r in range(self.table.rowCount()):
            target = self.table.cellWidget(r, 0).currentText()
            factor = float(self.table.cellWidget(r, 1).value())
            source = self.table.cellWidget(r, 2).currentText()
            offset = float(self.table.cellWidget(r, 3).value())
            if target and source and target != source:
                new.append({"target": target, "factor": factor,
                             "source": source, "offset": offset})
        self.parent_win.constraints = new
        self.parent_win._refresh_plot()
        self.accept()


class BatchFitDialog(QtWidgets.QDialog):
    """Diálogo de ajuste en serie con warm-start secuencial.

    Selecciona N ficheros .ws5/.adt y los ajusta uno tras otro usando el
    modelo activo de la ventana principal como plantilla. El resultado de
    cada uno es la plantilla del siguiente.
    """
    def __init__(self, parent: "MossbauerQtWindow"):
        super().__init__(parent)
        self.parent_win = parent
        self.setWindowTitle(tr("msg.batch_title"))
        self.resize(820, 500)
        self.results: list[dict] = []
        self.entries: list[dict] = []  # cada uno {path, metadata, status, result}

        v = QtWidgets.QVBoxLayout(self)

        # Botones de gestión
        row = QtWidgets.QHBoxLayout()
        btn_add = QtWidgets.QPushButton(tr("batch.add_files"))
        btn_add.clicked.connect(self._add_files)
        btn_rm = QtWidgets.QPushButton(tr("batch.remove"))
        btn_rm.clicked.connect(self._remove_selected)
        row.addWidget(btn_add); row.addWidget(btn_rm)
        row.addStretch(1)
        row.addWidget(QtWidgets.QLabel("<i>" + tr("batch.template_label") + "</i>"))
        v.addLayout(row)

        # Tabla
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([
            tr("batch.col_file"), tr("batch.col_meta"), tr("batch.col_status"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        v.addWidget(self.table, stretch=1)

        # Regex
        rrow = QtWidgets.QHBoxLayout()
        rrow.addWidget(QtWidgets.QLabel(tr("batch.regex_label")))
        self.regex_edit = QtWidgets.QLineEdit(r"(?P<v>[-+]?\d+(?:\.\d+)?)\s*K")
        rrow.addWidget(self.regex_edit, stretch=1)
        btn_apply = QtWidgets.QPushButton(tr("batch.apply_regex"))
        btn_apply.clicked.connect(self._apply_regex)
        rrow.addWidget(btn_apply)
        v.addLayout(rrow)

        # Progreso
        self.progress = QtWidgets.QLabel("")
        v.addWidget(self.progress)

        # Botones de acción
        brow = QtWidgets.QHBoxLayout()
        self.btn_run = QtWidgets.QPushButton(tr("batch.run"))
        self.btn_run.clicked.connect(self._run)
        self.btn_csv = QtWidgets.QPushButton(tr("batch.save_csv"))
        self.btn_csv.clicked.connect(self._save_csv)
        self.btn_csv.setEnabled(False)
        self.btn_trends = QtWidgets.QPushButton(tr("batch.show_trends"))
        self.btn_trends.clicked.connect(self._show_trends)
        self.btn_trends.setEnabled(False)
        brow.addWidget(self.btn_run); brow.addStretch(1)
        brow.addWidget(self.btn_csv); brow.addWidget(self.btn_trends)
        btn_close = QtWidgets.QPushButton(tr("button.close"))
        btn_close.clicked.connect(self.reject)
        brow.addWidget(btn_close)
        v.addLayout(brow)

    def _refresh_table(self):
        self.table.setRowCount(len(self.entries))
        for i, e in enumerate(self.entries):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(e["path"].name))
            meta = e.get("metadata")
            meta_txt = "" if meta is None else (f"{meta:g}" if isinstance(meta, (int, float)) else str(meta))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(meta_txt))
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(tr(f"batch.status_{e['status']}")))

    def _add_files(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, tr("batch.add_files"), str(ROOT),
            "WS5/ADT (*.ws5 *.adt *.WS5 *.ADT);;All (*.*)")
        for p in paths:
            self.entries.append({"path": Path(p), "metadata": None,
                                  "status": "pending", "result": None})
        self._refresh_table()

    def _remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.entries):
                del self.entries[r]
        self._refresh_table()

    def _apply_regex(self):
        pat = self.regex_edit.text().strip()
        for e in self.entries:
            e["metadata"] = extract_metadata(e["path"].name, pat)
        self._refresh_table()

    def _run(self):
        if not self.entries:
            QtWidgets.QMessageBox.information(
                self, tr("msg.batch_title"), tr("msg.batch_no_files"))
            return
        self.btn_run.setEnabled(False)
        self.btn_csv.setEnabled(False); self.btn_trends.setEnabled(False)
        ok = fail = 0
        for i, e in enumerate(self.entries, 1):
            self.progress.setText(
                tr("progress.batch_step", i=i, n=len(self.entries), name=e["path"].name))
            QtWidgets.QApplication.processEvents()
            try:
                # Reusar warm-start: aplicamos el estado actual del Qt y
                # cargamos el nuevo espectro (que sobrescribe folding center).
                # Mismo doblado que el flujo principal y core.session: recorte
                # de borde y eje de velocidad sin estirar la escala.
                counts = read_ws5_counts(e["path"])
                center = find_best_integer_or_half_center(counts)
                edge_trim = int(getattr(self.parent_win, "_edge_trim", 1))
                folded, sigma, y, norm = fold_and_normalize(counts, center, edge_trim)
                calib_state = self.parent_win.calib.to_view_state()
                vmax = calib_state.vmax
                v = velocity_axis(counts.size, vmax, y.size, edge_trim)
                # Construir state desde la UI parental
                state = self.parent_win._build_state()
                if state is None:
                    raise RuntimeError("No hay modelo activo")
                state.velocity = v
                state.y_data = y
                state.sigma_data = sigma
                # Cuentas crudas y normalización del fichero del batch (no las
                # del espectro cargado en la ventana): las usan el re-folding
                # de fit_center y la σ Poisson.
                state.counts = counts
                state.norm_factor = norm
                state.values["center"] = float(center)
                result = fit_discrete(state)
                e["status"] = "ok"
                e["result"] = {
                    "file": e["path"].name,
                    "metadata": e["metadata"],
                    "status": "ok",
                    "values": result.values,
                    "errors": result.errors,
                    "stats": result.stats,
                    "free_keys": result.free_keys,
                }
                ok += 1
                # warm-start: aplicar valores al UI para la siguiente iteración
                self.parent_win._building = True
                try:
                    for cp in self.parent_win.components_panels:
                        cp.apply_values(result.values)
                    calib_state = self.parent_win.calib.to_view_state()
                    self.parent_win.calib.baseline.set_value(
                        result.values.get("baseline", calib_state.baseline))
                    self.parent_win.calib.slope.set_value(
                        result.values.get("slope", calib_state.slope))
                finally:
                    self.parent_win._building = False
            except Exception as exc:
                e["status"] = "failed"
                e["result"] = {"file": e["path"].name, "metadata": e["metadata"],
                                "status": "failed", "error": str(exc),
                                "values": {}, "errors": {}, "stats": {}}
                fail += 1
            self._refresh_table()
            QtWidgets.QApplication.processEvents()
        self.progress.setText(tr("msg.batch_done", ok=ok, fail=fail, n=len(self.entries)))
        self.btn_run.setEnabled(True)
        self.btn_csv.setEnabled(True); self.btn_trends.setEnabled(True)

    def _save_csv(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("batch.save_csv"), str(ROOT),
            "TSV (*.tsv);;CSV (*.csv);;All (*.*)")
        if not path:
            return
        results = [e["result"] for e in self.entries if e.get("result")]
        keys: set[str] = set()
        for r in results:
            keys.update(r.get("free_keys", []) or r.get("values", {}).keys())
        try:
            write_results_csv(Path(path), sorted(keys), results)
            self.progress.setText(f"TSV guardado: {path}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("batch.save_csv"),
                                            f"{type(exc).__name__}: {exc}")

    def _show_trends(self):
        results = [e["result"] for e in self.entries if e.get("result")]
        keys: set[str] = set()
        for r in results:
            keys.update(r.get("values", {}).keys())
        trend = collect_trend_data(results, sorted(keys))
        if not trend:
            QtWidgets.QMessageBox.information(
                self, tr("batch.show_trends"),
                "No hay datos numéricos para representar.")
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("msg.batch_title"))
        dlg.resize(900, 600)
        vv = QtWidgets.QVBoxLayout(dlg)
        vv.addWidget(QtWidgets.QLabel(tr("dialog.batch_trends_subtitle")))
        fig = Figure(figsize=(8.5, 5.0), dpi=96)
        cv = FigureCanvas(fig); vv.addWidget(cv, stretch=1)
        skeys = sorted(trend.keys())
        ncols = 2 if len(skeys) > 1 else 1
        nrows = (len(skeys) + ncols - 1) // ncols
        for i, k in enumerate(skeys, 1):
            ax = fig.add_subplot(nrows, ncols, i)
            xs = [p[0] for p in trend[k]]; ys = [p[1] for p in trend[k]]
            es = [p[2] if p[2] is not None else 0.0 for p in trend[k]]
            ax.errorbar(xs, ys, yerr=es, fmt="o-", color="#2563eb", ms=4)
            ax.set_title(k, fontsize=9); ax.tick_params(labelsize=7)
            ax.grid(alpha=0.3)
        fig.tight_layout(); cv.draw_idle()
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); vv.addWidget(bb)
        dlg.exec()


class GlobalNeelFitDialog(QtWidgets.QDialog):
    """Diálogo de ajuste global Néel-Arrhenius multi-temperatura.

    Permite cargar N espectros a distintas temperaturas y ajustarlos
    simultáneamente compartiendo los parámetros físicos de la distribución
    de tamaños (Néel-Arrhenius lognormal).
    """
    def __init__(self, parent: "MossbauerQtWindow"):
        super().__init__(parent)
        self.parent_win = parent
        self.setWindowTitle(tr("global_neel.title"))
        self.resize(860, 620)
        self._fit_result = None  # GlobalRelaxationFitResult | None
        self.entries: list[dict] = []  # {path, temp_k, status}

        v = QtWidgets.QVBoxLayout(self)

        # ── Botones de gestión de ficheros ────────────────────────────────
        row = QtWidgets.QHBoxLayout()
        btn_add = QtWidgets.QPushButton(tr("batch.add_files"))
        btn_add.clicked.connect(self._add_files)
        btn_rm = QtWidgets.QPushButton(tr("batch.remove"))
        btn_rm.clicked.connect(self._remove_selected)
        row.addWidget(btn_add); row.addWidget(btn_rm); row.addStretch(1)
        v.addLayout(row)

        # ── Tabla (fichero | T(K) | estado) ──────────────────────────────
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([
            tr("batch.col_file"), tr("global_neel.col_temp"), tr("batch.col_status"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        v.addWidget(self.table, stretch=1)

        # ── Regex para extraer temperatura del nombre de fichero ──────────
        rrow = QtWidgets.QHBoxLayout()
        rrow.addWidget(QtWidgets.QLabel(tr("batch.regex_label")))
        self.regex_edit = QtWidgets.QLineEdit(r"(?P<v>[-+]?\d+(?:\.\d+)?)\s*K")
        rrow.addWidget(self.regex_edit, stretch=1)
        btn_apply = QtWidgets.QPushButton(tr("batch.apply_regex"))
        btn_apply.clicked.connect(self._apply_regex)
        rrow.addWidget(btn_apply)
        v.addLayout(rrow)

        # ── Grupo parámetros iniciales Néel (compartidos) ─────────────────
        grp = QtWidgets.QGroupBox(tr("global_neel.init_group"))
        grp_h = QtWidgets.QHBoxLayout(grp)

        def _make_spin(lo: float, hi: float, default: float, step: float, decimals: int) -> QtWidgets.QDoubleSpinBox:
            sp = QtWidgets.QDoubleSpinBox()
            sp.setRange(lo, hi); sp.setSingleStep(step); sp.setDecimals(decimals)
            sp.setValue(default)
            return sp

        # BHF (T)
        grp_h.addWidget(QtWidgets.QLabel(tr("slider.s_bhf")))
        self.spin_bhf = _make_spin(0.0, 60.0, 33.0, 0.1, 2)
        grp_h.addWidget(self.spin_bhf)
        grp_h.addSpacing(8)
        # log10 Keff
        grp_h.addWidget(QtWidgets.QLabel(tr("slider.s_neel_log10_keff")))
        self.spin_log10_keff = _make_spin(2.0, 7.0, 4.0, 0.05, 3)
        grp_h.addWidget(self.spin_log10_keff)
        grp_h.addSpacing(8)
        # d50 (nm)
        grp_h.addWidget(QtWidgets.QLabel(tr("slider.s_neel_mean_d_nm")))
        self.spin_mean_d = _make_spin(0.5, 100.0, 8.0, 0.1, 2)
        grp_h.addWidget(self.spin_mean_d)
        grp_h.addSpacing(8)
        # sigma
        grp_h.addWidget(QtWidgets.QLabel(tr("slider.s_neel_sigma")))
        self.spin_sigma = _make_spin(0.01, 1.5, 0.25, 0.01, 3)
        grp_h.addWidget(self.spin_sigma)
        grp_h.addSpacing(8)
        # log10 tau0
        grp_h.addWidget(QtWidgets.QLabel(tr("slider.s_neel_log10_tau0")))
        self.spin_log10_tau0 = _make_spin(-12.0, -6.0, -9.0, 0.1, 2)
        grp_h.addWidget(self.spin_log10_tau0)
        grp_h.addStretch(1)

        v.addWidget(grp)

        # ── Etiqueta de progreso ──────────────────────────────────────────
        self.progress = QtWidgets.QLabel("")
        v.addWidget(self.progress)

        # ── Área de resultados (solo lectura) ─────────────────────────────
        results_label = QtWidgets.QLabel(tr("global_neel.results"))
        v.addWidget(results_label)
        self.results_text = QtWidgets.QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(140)
        self.results_text.setStyleSheet("QTextEdit { font-family: monospace; font-size: 9pt; }")
        v.addWidget(self.results_text)

        # ── Botones de acción ─────────────────────────────────────────────
        brow = QtWidgets.QHBoxLayout()
        self.btn_run = QtWidgets.QPushButton(tr("batch.run"))
        self.btn_run.clicked.connect(self._run)
        self.btn_csv = QtWidgets.QPushButton(tr("batch.save_csv"))
        self.btn_csv.clicked.connect(self._save_csv)
        self.btn_csv.setEnabled(False)
        self.btn_trends = QtWidgets.QPushButton(tr("batch.show_trends"))
        self.btn_trends.clicked.connect(self._show_trends)
        self.btn_trends.setEnabled(False)
        brow.addWidget(self.btn_run); brow.addStretch(1)
        brow.addWidget(self.btn_csv); brow.addWidget(self.btn_trends)
        btn_close = QtWidgets.QPushButton(tr("button.close"))
        btn_close.clicked.connect(self.reject)
        brow.addWidget(btn_close)
        v.addLayout(brow)

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.entries))
        for i, e in enumerate(self.entries):
            item_file = QtWidgets.QTableWidgetItem(e["path"].name)
            item_file.setFlags(item_file.flags() & ~QtWidgets.QTableWidgetItem.ItemFlag.ItemIsEditable)  # type: ignore[attr-defined]
            self.table.setItem(i, 0, item_file)
            temp_val = e.get("temp_k")
            item_temp = QtWidgets.QTableWidgetItem("" if temp_val is None else f"{temp_val:g}")
            item_temp.setFlags(item_temp.flags() | QtWidgets.QTableWidgetItem.ItemFlag.ItemIsEditable)  # type: ignore[attr-defined]
            self.table.setItem(i, 1, item_temp)
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(tr(f"batch.status_{e['status']}")))

    def _add_files(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, tr("batch.add_files"), str(ROOT),
            "WS5/ADT (*.ws5 *.adt *.WS5 *.ADT);;All (*.*)")
        for p in paths:
            self.entries.append({"path": Path(p), "temp_k": None, "status": "pending"})
        self._refresh_table()

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.entries):
                del self.entries[r]
        self._refresh_table()

    def _apply_regex(self) -> None:
        pat = self.regex_edit.text().strip()
        for e in self.entries:
            val = extract_metadata(e["path"].name, pat)
            e["temp_k"] = float(val) if val is not None else None
        self._refresh_table()

    def _sync_temps_from_table(self) -> bool:
        """Lee las temperaturas de la tabla y las copia en self.entries.

        Devuelve True si todas las filas tienen temperatura válida.
        """
        for i, e in enumerate(self.entries):
            item = self.table.item(i, 1)
            text = (item.text().strip() if item else "").replace(",", ".")
            try:
                e["temp_k"] = float(text)
            except ValueError:
                e["temp_k"] = None
        return all(e["temp_k"] is not None for e in self.entries)

    def _run(self) -> None:
        from core.relaxation import fit_neel_size_global, GlobalRelaxationSpectrum

        if not self.entries:
            QtWidgets.QMessageBox.information(
                self, tr("global_neel.title"), tr("msg.batch_no_files"))
            return

        if not self._sync_temps_from_table():
            QtWidgets.QMessageBox.warning(
                self, tr("global_neel.title"), tr("global_neel.temp_missing"))
            return

        n = len(self.entries)
        self.progress.setText(tr("global_neel.running", n=n))
        QtWidgets.QApplication.processEvents()
        self.btn_run.setEnabled(False)
        self.btn_csv.setEnabled(False)
        self.btn_trends.setEnabled(False)

        # Calibración del espectrómetro (Vmax)
        calib_state = self.parent_win.calib.to_view_state()
        vmax = calib_state.vmax

        spectra: list[GlobalRelaxationSpectrum] = []
        load_errors: list[str] = []
        for e in self.entries:
            try:
                counts = read_ws5_counts(e["path"])
                center = find_best_integer_or_half_center(counts)
                edge_trim = int(getattr(self.parent_win, "_edge_trim", 1))
                folded, sigma, y, norm = fold_and_normalize(counts, center, edge_trim)
                vel = velocity_axis(counts.size, vmax, y.size, edge_trim)
                spectra.append(GlobalRelaxationSpectrum(
                    velocity=vel,
                    y_data=y,
                    temperature_k=float(e["temp_k"]),
                    sigma_data=sigma,
                    label=e["path"].stem,
                ))
                e["status"] = "pending"
            except Exception as exc:
                e["status"] = "failed"
                load_errors.append(f"{e['path'].name}: {exc}")

        if load_errors:
            QtWidgets.QMessageBox.warning(
                self, tr("global_neel.title"),
                "Errores al cargar espectros:\n" + "\n".join(load_errors))
            self.btn_run.setEnabled(True)
            self.progress.setText("")
            self._refresh_table()
            return

        # Valores iniciales de los spinboxes
        shared_initial = {
            "bhf": self.spin_bhf.value(),
            "neel_log10_keff": self.spin_log10_keff.value(),
            "neel_mean_d_nm": self.spin_mean_d.value(),
            "neel_sigma": self.spin_sigma.value(),
            "neel_log10_tau0": self.spin_log10_tau0.value(),
        }

        from PySide6.QtCore import Qt
        QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = fit_neel_size_global(spectra, shared_initial=shared_initial)
        except Exception as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.critical(
                self, tr("global_neel.title"), f"{type(exc).__name__}: {exc}")
            self.btn_run.setEnabled(True)
            self.progress.setText("")
            return
        QtWidgets.QApplication.restoreOverrideCursor()

        self._fit_result = result
        self._spectra = spectra

        # Calcular chi^2 reducido
        n_data = sum(s.y_data.size for s in spectra)
        n_free = len(result.free_keys)
        dof = max(1, n_data - n_free)
        redchi2 = float(2.0 * result.cost) / dof

        # Actualizar estados de la tabla
        for e in self.entries:
            e["status"] = "ok" if result.success else "failed"
        self._refresh_table()

        # Mostrar resultado en el área de texto
        lines = [
            tr("global_neel.save_header"),
        ]
        for k, vv in result.shared.items():
            lines.append(f"  {k:20s} = {vv:.6g}")
        lines.append("")
        lines.append(f"  χ²_red = {redchi2:.4g}   cost={result.cost:.6g}   success={result.success}")
        lines.append(f"  {result.message}")
        lines.append("")
        lines.append("Parámetros locales:")
        for i, (e, loc) in enumerate(zip(self.entries, result.local)):
            lines.append(f"  [{e['path'].name}  T={e['temp_k']:g} K]  " +
                         "  ".join(f"{k}={v:.5g}" for k, v in loc.items()))
        self.results_text.setPlainText("\n".join(lines))

        self.progress.setText(tr("global_neel.done", redchi2=redchi2))
        self.btn_run.setEnabled(True)
        self.btn_csv.setEnabled(True)
        self.btn_trends.setEnabled(True)

    def _save_csv(self) -> None:
        if self._fit_result is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("batch.save_csv"), str(ROOT),
            "TSV (*.tsv);;CSV (*.csv);;All (*.*)")
        if not path:
            return
        result = self._fit_result
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh, delimiter="\t")
                # Cabecera
                local_keys = list(result.local[0].keys()) if result.local else []
                shared_keys = list(result.shared.keys())
                w.writerow(["file", "temp_K"] + local_keys + shared_keys)
                # Una fila por espectro (parámetros locales + compartidos repetidos)
                for e, loc in zip(self.entries, result.local):
                    row_vals = (
                        [e["path"].name, f"{e['temp_k']:g}"] +
                        [f"{loc.get(k, '')}" for k in local_keys] +
                        [f"{result.shared.get(k, '')}" for k in shared_keys]
                    )
                    w.writerow(row_vals)
            self.progress.setText(f"TSV guardado: {path}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("batch.save_csv"),
                                            f"{type(exc).__name__}: {exc}")

    def _show_trends(self) -> None:
        if self._fit_result is None:
            return
        result = self._fit_result
        # Eje X: temperatura; eje Y: parámetros locales
        local_keys = list(result.local[0].keys()) if result.local else []
        if not local_keys:
            QtWidgets.QMessageBox.information(
                self, tr("batch.show_trends"),
                "No hay datos numéricos para representar.")
            return

        temps = [e["temp_k"] for e in self.entries if e.get("temp_k") is not None]
        local_vals: dict[str, list[float]] = {k: [] for k in local_keys}
        for loc in result.local:
            for k in local_keys:
                local_vals[k].append(float(loc.get(k, 0.0)))

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("global_neel.title"))
        dlg.resize(900, 600)
        vv = QtWidgets.QVBoxLayout(dlg)
        vv.addWidget(QtWidgets.QLabel(tr("dialog.batch_trends_subtitle")))
        fig = Figure(figsize=(8.5, 5.0), dpi=96)
        cv = FigureCanvas(fig); vv.addWidget(cv, stretch=1)
        ncols = 2 if len(local_keys) > 1 else 1
        nrows = (len(local_keys) + ncols - 1) // ncols
        for i, k in enumerate(local_keys, 1):
            ax = fig.add_subplot(nrows, ncols, i)
            ax.plot(temps, local_vals[k], "o-", color="#2563eb", ms=4)
            ax.set_xlabel("T (K)", fontsize=8)
            ax.set_title(k, fontsize=9); ax.tick_params(labelsize=7)
            ax.grid(alpha=0.3)
        fig.tight_layout(); cv.draw_idle()
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); vv.addWidget(bb)
        dlg.exec()
