"""Acciones de fichero/exportación simples de la GUI Qt."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.folding import find_best_integer_or_half_center, fold_and_normalize, read_ws5_counts, load_velocity_csv
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
        center = find_best_integer_or_half_center(self.file.counts)
        # Re-dobla con el nuevo centro y aplica el recorte de bordes de Tk.
        self._refold_current_data(center)
        self._building = True
        self.calib.center.set_value(center)
        self._building = False
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
        if is_dist:
            dist_res = getattr(self.runtime_results, "distribution_result", None)
            if dist_res is not None and hasattr(dist_res, "model_at_v"):
                model = np.asarray(dist_res.model_at_v, dtype=float)
                residual = y - model
            elif dist_res is not None and hasattr(dist_res, "model"):
                m = np.asarray(dist_res.model, dtype=float)
                if m.size == v.size:
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

        try:
            with open(path, "w", encoding="utf-8") as fh:
                for hl in header:
                    fh.write(hl + "\n")
                fh.write("\t".join(cols) + "\n")
                for i in range(v.size):
                    fh.write("\t".join(f"{rows[j][i]:.8g}" for j in range(len(rows))) + "\n")
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
            "Espectros (*.ws5 *.adt *.csv *.txt *.dat *.exp);;Todos (*.*)")
        if not path:
            return
        fpath = Path(path)
        try:
            suffix = fpath.suffix.lower()
            if suffix in (".csv", ".txt", ".dat", ".exp"):
                data = load_velocity_csv(fpath)
                vel = np.asarray(data["velocity"], dtype=float)
                y_raw = np.asarray(data["y"], dtype=float)
            else:
                from core.folding import velocity_axis
                counts = read_ws5_counts(fpath)
                center = find_best_integer_or_half_center(counts)
                folded, _sigma, _ = fold_and_normalize(counts, center)
                vmax = float(self.calib.vmax.value()) if hasattr(self, "calib") else 12.007
                edge_trim = getattr(self, "_edge_trim", 1)
                vel = velocity_axis(counts.size, vmax, folded.size, edge_trim=edge_trim)
                y_raw = folded.astype(float)
            norm = float(np.percentile(y_raw, 90)) or 1.0
            y_data = y_raw / norm
            label = fpath.stem
            csp = ComparisonSpectrum(path=fpath, velocity=vel, y_data=y_data, label=label)
            self.comparison_spectra.append(csp)
            self.act_clear_comparison.setEnabled(True)
            n = len(self.comparison_spectra)
            self.statusBar().showMessage(
                tr("status.comparison_added", n=n, name=label,
                   default=f"Comparación [{n}]: {label}"), 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("file.compare_spectrum"),
                f"{type(exc).__name__}: {exc}")
            return
        self._refresh_plot()

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
