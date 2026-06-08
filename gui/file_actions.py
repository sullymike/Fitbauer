"""Acciones de fichero/exportación simples de la GUI Qt."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.folding import find_best_integer_or_half_center
from core.reconstruction import reconstruct_discrete_model

ROOT = Path(__file__).resolve().parents[1]


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
        self.statusBar().showMessage(f"Centro detectado: {center:.4f}", 5000)
        self._refresh_plot()

    def on_save_fit(self) -> None:
        """Exporta velocidad / datos / modelo / residuo en TSV."""
        if self.file.velocity is None or self.file.y_data is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("file.save_fit"), str(ROOT),
            "TSV (*.dat *.tsv);;All (*.*)")
        if not path:
            return
        state = self._build_state()
        v = self.file.velocity
        y = self.file.y_data
        try:
            reconstruction = reconstruct_discrete_model(
                v,
                y,
                state.values,
                state.components,
                state.constraints,
                absorber_model=state.absorber_model,
            ) if state else None
        except Exception:
            reconstruction = None
        model = reconstruction.model if reconstruction is not None else None
        residual = reconstruction.residual if reconstruction is not None else np.zeros_like(y)
        cols = ["velocity_mm_s", "data_norm"]
        rows = [v, y]
        if model is not None:
            cols += ["model", "residual"]
            rows += [model, residual]
        if self.file.folded is not None:
            cols.append("folded_counts"); rows.append(self.file.folded)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\t".join(cols) + "\n")
                for i in range(v.size):
                    fh.write("\t".join(f"{rows[j][i]:.8g}" for j in range(len(cols))) + "\n")
            self.statusBar().showMessage(f"Ajuste guardado: {path}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("file.save_fit"),
                                            f"{type(exc).__name__}: {exc}")

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
