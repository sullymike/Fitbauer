"""Acciones de fichero/exportación simples de la GUI Qt."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.spectrum_import import (
    ImportHints, axis_referred_to_alpha_fe, intensity_column_choices, read_spectrum_file,
    with_intensity_column,
)
from core.reconstruction import reconstruct_discrete_model
from gui.state import ComparisonSpectrum

ROOT = Path(__file__).resolve().parents[1]

_KIND_EN = {
    "Sextete":   "Sextet",
    "Doblete":   "Doublet",
    "Singlete":  "Singlet",
    "Relajacion":"Relaxation",
    "BlumeTjon": "BlumeTjon",
    "NeelSize":  "NeelSize",
}

class FileActionsMixin:
    # ── Acciones rápidas ─────────────────────────────────────────────────
    def on_find_center(self) -> None:
        if self.file.counts is None:
            return
        center = self._detect_center(self.file.counts)
        # Re-dobla con el nuevo centro y aplica el recorte de bordes de Tk.
        self._refold_current_data(center)
        self._building = True
        self.calib.center.set_value(center)
        self._building = False
        if self.file.path is not None:
            self.file_label.setText(f"<b>{self.file.path.name}</b><br>" +
                                    tr("file.label_info", n=self.file.counts.size,
                                       center=f"{float(center):.3f}",
                                       norm=f"{self.file.norm_factor:.4g}"))
        self.statusBar().showMessage(tr("status.center_found", center=f"{center:.4f}", default=f"Center detected: {center:.4f}"), 5000)
        self._refresh_plot()

    def on_save_fit(self) -> None:
        """Exporta velocidad / datos / modelo / subespectros / residuo en TSV."""
        from datetime import datetime
        from core.fit_engine import model_from_values

        if self.file.velocity is None or self.file.y_data is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("file.save_fit"), str(ROOT),
            "TSV (*.dat *.tsv);;All (*.*)")
        if not path:
            return

        v = self.file.velocity
        y = self.file.y_data
        file_name = self.file.path.name if self.file.path else "—"
        is_dist = getattr(self, "is_distribution_mode", False)
        state = self._build_state()

        # ── Modelo total y residuo ──────────────────────────────────────
        model = None
        residual = np.zeros_like(y)
        try:
            reconstruction = reconstruct_discrete_model(
                v, y, state.values, state.components, state.constraints,
                absorber_model=state.absorber_model,
            ) if state else None
            if reconstruction is not None:
                model = reconstruction.model
                residual = reconstruction.residual
        except Exception:
            reconstruction = None

        # En modo distribución, si hay un resultado de distribución, úsalo
        dist_res = None
        if is_dist:
            dist_res = getattr(self.runtime_results, "distribution_result", None)
            # El modelo es la curva del ajuste de distribución, no el discreto
            # de los paneles (antes se buscaban campos que no existen y se
            # exportaba el modelo discreto).
            m = (np.asarray(dist_res.fitted_curve, dtype=float)
                 if dist_res is not None else None)
            if m is not None and m.size == v.size:
                model = m
                residual = y - model

        # ── Subespectros por componente (solo modo discreto) ──────────
        comp_curves: list[tuple[int, str, np.ndarray]] = []
        if not is_dist and state is not None:
            enabled = [c for c in state.components if getattr(c, "enabled", False)]
            for comp in enabled:
                try:
                    c_y = model_from_values(
                        v, state.values, [comp], state.constraints or [],
                        absorber_model=state.absorber_model,
                    )
                    comp_curves.append((int(comp.idx), _KIND_EN.get(comp.kind, comp.kind), c_y))
                except Exception:
                    pass

        # ── Líneas de cabecera ──────────────────────────────────────────
        mode_label = "distribution" if is_dist else "discrete (sextet/doublet/singlet)"
        header = [
            f"# Mossbauer Fe-57 — {file_name} — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"# Mode: {mode_label}",
        ]
        if comp_curves:
            header.append("# Components: " + "  ".join(
                f"comp{idx}={kind}" for idx, kind, _ in comp_curves))
        # Metadatos del ajuste de distribución (forma, regularizador, α, κδ/κq)
        if is_dist and dist_res is not None:
            def _g(attr):
                return getattr(dist_res, attr, None)
            meta_bits = []
            if _g("shape"):
                meta_bits.append(f"shape={_g('shape')}")
            if _g("reg_mode"):
                meta_bits.append(f"reg_mode={_g('reg_mode')}")
            for attr, tag in (("alpha", "alpha"), ("alpha_bhf", "alpha_bhf"),
                              ("alpha_quad", "alpha_quad"), ("rms", "rms"),
                              ("effective_dof", "eff_dof")):
                val = _g(attr)
                if val is not None:
                    meta_bits.append(f"{tag}={float(val):.6g}")
            dsl = float(_g("delta_slope") or 0.0)
            qsl = float(_g("quad_slope") or 0.0)
            if dsl or qsl:
                meta_bits.append(f"kdelta={dsl:.6g}")
                meta_bits.append(f"kquad={qsl:.6g}")
            if meta_bits:
                header.append("# Distribution: " + "  ".join(meta_bits))

        # ── Columnas ────────────────────────────────────────────────────
        cols: list[str] = ["velocity_mm_s", "data_norm"]
        rows: list[np.ndarray] = [v, y]
        if model is not None:
            cols += ["model", "residual"]
            rows += [model, residual]
        for idx, kind, c_y in comp_curves:
            cols.append(f"comp{idx}_{kind}")
            rows.append(c_y)
        if self.file.folded is not None:
            cols.append("folded_counts")
            rows.append(self.file.folded)

        # ── Bloque de la distribución P(x) (rejilla propia ≠ velocidad) ──
        # Mismas columnas que «Exportar distribución…» (2D: una fila por celda).
        dist_block: list[str] = []
        if is_dist and dist_res is not None:
            from mossbauer_distribution import distribution_data_table
            try:
                dcols, drows = distribution_data_table(dist_res)
                dist_block.append("")
                dist_block.append("# --- Distribution P(x) ---")
                dist_block.append("\t".join(dcols))
                for row in drows:
                    dist_block.append("\t".join(f"{val:.8g}" for val in row))
            except Exception:
                dist_block = []

        try:
            with open(path, "w", encoding="utf-8") as fh:
                for hl in header:
                    fh.write(hl + "\n")
                fh.write("\t".join(cols) + "\n")
                for i in range(v.size):
                    fh.write("\t".join(f"{rows[j][i]:.8g}" for j in range(len(rows))) + "\n")
                for dl in dist_block:
                    fh.write(dl + "\n")
            self.statusBar().showMessage(tr("status.fit_saved", path=path, default=f"Fit saved: {path}"), 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("file.save_fit"),
                                            f"{type(exc).__name__}: {exc}")

    # ── Comparación de espectros ─────────────────────────────────────────
    def on_open_comparison(self) -> None:
        """Carga un espectro adicional para superponerlo al actual (solo display)."""
        if self.file.velocity is None:
            QtWidgets.QMessageBox.information(
                self, tr("file.compare_spectrum"),
                tr("msg.comparison_needs_main", default="Carga primero un espectro principal."))
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, tr("file.compare_spectrum"),
            str(ROOT / "data_sample"),
            f"{tr('filter.spectra')} (*.ws5 *.adt *.csv *.txt *.dat *.exp *.b *.t);;"
            f"{tr('filter.all')} (*.*)")
        if not path:
            return
        try:
            self._add_comparison(Path(path))
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("file.compare_spectrum"),
                f"{type(exc).__name__}: {exc}")

    def _add_comparison(self, fpath: Path, *, column: int | None = None,
                        shift_alpha_fe: bool | None = None, ask: bool = True) -> bool:
        """Añade ``fpath`` a la comparación.

        En un fichero en velocidad se puede elegir la columna de intensidad
        (datos, ajuste total o un sitio de WinNormos) y desplazar el eje por
        el δ del α-Fe de la calibración activa, si el fichero lo tiene en 0
        (WMOSS, WinNormos). Con ``ask`` se pregunta lo que no venga dado.
        """
        imported = read_spectrum_file(fpath)
        suffix = ""
        if imported.x_kind == "velocity":
            choices = intensity_column_choices(imported)
            iso = self.calibration_iso_ref()
            if column is None:
                column = imported.columns.index("y")
            if shift_alpha_fe is None:
                shift_alpha_fe = axis_referred_to_alpha_fe(imported.x, iso)
            if ask and (len(choices) > 1 or iso is not None):
                dlg = ComparisonOptionsDialog(self, fpath, imported, choices, column,
                                              iso, shift_alpha_fe)
                if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                    return False
                column, shift_alpha_fe = dlg.column(), dlg.shift_alpha_fe()
            if column != imported.columns.index("y"):
                imported = read_spectrum_file(
                    fpath, ImportHints(columns=with_intensity_column(imported, column)))
                suffix += f" [{column + 1}]"
            order = np.argsort(imported.x, kind="stable")
            vel = imported.x[order]
            y_raw = imported.transmission()[0][order]
            if shift_alpha_fe and iso is not None:
                # Su eje tiene el α-Fe en 0: v(fuente) = v(α-Fe) + δ(α-Fe).
                vel = vel + iso
                suffix += " (α-Fe → " + tr("compare.source_axis", default="fuente") + ")"
        else:
            prep = self._prepare_like_active(self._read_like_active(fpath).y)
            y_raw, vel = prep.y, prep.velocity
        norm = float(np.percentile(y_raw, 90)) or 1.0
        label = fpath.stem + suffix
        self.comparison_spectra.append(
            ComparisonSpectrum(path=fpath, velocity=vel, y_data=y_raw / norm, label=label))
        self.act_clear_comparison.setEnabled(True)
        n = len(self.comparison_spectra)
        self.statusBar().showMessage(
            tr("status.comparison_added", n=n, name=label,
               default=f"Comparación [{n}]: {label}"), 5000)
        self._refresh_plot()
        return True

    def on_clear_comparison(self) -> None:
        """Elimina todos los espectros de comparación."""
        self.comparison_spectra.clear()
        if hasattr(self, "act_clear_comparison"):
            self.act_clear_comparison.setEnabled(False)
        self.statusBar().showMessage(
            tr("status.comparison_cleared", default="Comparación eliminada"), 3000)
        self._refresh_plot()

    def on_changelog(self) -> None:
        from core.constants import CHANGELOG_PATH
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("help.changelog"))
        dlg.resize(820, 600)
        v = QtWidgets.QVBoxLayout(dlg)
        text = QtWidgets.QTextBrowser()
        text.setOpenExternalLinks(True)
        if CHANGELOG_PATH.exists():
            content = CHANGELOG_PATH.read_text(encoding="utf-8", errors="replace")
            text.setPlainText(content)
        else:
            text.setPlainText(tr("help.changelog_unavailable"))
        v.addWidget(text, stretch=1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.exec()


class ComparisonOptionsDialog(QtWidgets.QDialog):
    """Columna de intensidad y referencia del eje de un fichero de comparación."""

    def __init__(self, parent, path: Path, imported, choices: list[int], column: int,
                 iso_ref: float | None, shift: bool):
        super().__init__(parent)
        self.setWindowTitle(tr("file.compare_spectrum", default="Comparar espectro…"))
        form = QtWidgets.QFormLayout(self)
        form.addRow(QtWidgets.QLabel(f"<b>{path.name}</b>"))
        self.column_combo = QtWidgets.QComboBox()
        from core.spectrum_import import read_text, parse_spectrum_text
        text = read_text(path)
        for i in choices:
            label = tr("compare.column", n=i + 1, default="Columna {n}")
            try:
                y = parse_spectrum_text(
                    text, ImportHints(columns=with_intensity_column(imported, i))).y
                label += f"  ({float(np.min(y)):.4g} … {float(np.max(y)):.4g})"
            except ValueError:
                pass
            if imported.columns[i] == "y":
                label += " · " + tr("compare.detected", default="detectada como datos")
            self.column_combo.addItem(label, i)
        self.column_combo.setCurrentIndex(max(0, self.column_combo.findData(column)))
        self.column_combo.setEnabled(len(choices) > 1)
        form.addRow(tr("compare.intensity", default="Intensidad"), self.column_combo)
        self.shift_check = QtWidgets.QCheckBox()
        if iso_ref is None:
            self.shift_check.setText(tr(
                "compare.no_iso", default="Sin δ(α-Fe) en la calibración: eje tal cual"))
            self.shift_check.setEnabled(False)
        else:
            self.shift_check.setText(tr(
                "compare.shift", iso=f"{iso_ref:+.4f}",
                default="Eje con el α-Fe en 0 (WMOSS, WinNormos): llevarlo a la fuente "
                        "sumando δ(α-Fe) = {iso} mm/s"))
            self.shift_check.setChecked(bool(shift))
        form.addRow(self.shift_check)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def column(self) -> int:
        return int(self.column_combo.currentData())

    def shift_alpha_fe(self) -> bool:
        return self.shift_check.isEnabled() and self.shift_check.isChecked()
