"""Herramientas auxiliares de ajuste para la GUI Qt."""
from __future__ import annotations

import json

import numpy as np
from PySide6 import QtWidgets
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from mossbauer_i18n import tr
from core.fit_engine import profile_likelihood
from gui.dialogs import BatchFitDialog, ConstraintsDialog


class FitToolsMixin:
    def on_auto_fit_from_minima(self) -> None:
        """Atajo: inicializa desde mínimos y a continuación ejecuta el ajuste."""
        if self.on_init_from_minima(show_message=False):
            if not self.is_distribution_mode:
                self.on_fit()

    def on_ai_summary(self) -> None:
        """Muestra un resumen JSON del espectro listo para pegar en un LLM."""
        if self.file.velocity is None or self.file.y_data is None:
            return
        peaks_raw, baseline, slope = self.detect_absorption_minima()
        v = self.file.velocity
        y = self.file.y_data
        peaks = [{"v_mm_s": round(float(p["pos"]), 4),
                  "depth": round(float(p["depth"]), 5),
                  "fwhm_mm_s": round(float(p["width"]), 4)}
                 for p in peaks_raw]
        summary = {
            "file": self.file.path.name if self.file.path else None,
            "n_channels": int(self.file.counts.size) if self.file.counts is not None else 0,
            "vmin_mm_s": round(float(np.min(v)), 4),
            "vmax_mm_s": round(float(np.max(v)), 4),
            "y_min": round(float(np.min(y)), 5),
            "y_max": round(float(np.max(y)), 5),
            "baseline_est": round(float(baseline), 5),
            "slope_est": round(float(slope), 7),
            "detected_minima": peaks,
            "ask": "Suggest a discrete Mössbauer Fe-57 fit (sextet/doublet/singlet) with starting δ, ΔEQ, BHF, Γ, depth.",
        }
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("ai_summary.title", default="Spectrum summary (for AI/LLM)"))
        dlg.resize(640, 480)
        v_lay = QtWidgets.QVBoxLayout(dlg)
        v_lay.addWidget(QtWidgets.QLabel("<i>" + tr(
            "ai_summary.hint",
            default=("Copy this JSON into any LLM (Ollama, ChatGPT, Claude, …) "
                     "to get suggested starting fit values.")) + "</i>"))
        text = QtWidgets.QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet("QTextEdit { font-family: monospace; font-size: 10pt; }")
        text.setPlainText(json.dumps(summary, indent=2, ensure_ascii=False))
        v_lay.addWidget(text, stretch=1)
        btn_copy = QtWidgets.QPushButton(
            tr("ai_summary.copy_clipboard", default="Copy to clipboard"))
        btn_copy.clicked.connect(
            lambda: QtWidgets.QApplication.clipboard().setText(text.toPlainText()))
        v_lay.addWidget(btn_copy)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        v_lay.addWidget(bb)
        dlg.exec()

    def on_profile_likelihood(self) -> None:
        """Para cada parámetro libre del último ajuste: perfila Δχ² y muestra los cruces."""
        state = self._build_state()
        if state is None:
            return
        self.statusBar().showMessage("Ajustando antes de perfilar…")
        QtWidgets.QApplication.processEvents()

        def _progress(msg: str, _i: int, _n: int) -> None:
            self.statusBar().showMessage(f"{msg}…")
            QtWidgets.QApplication.processEvents()

        # Motor puro: verosimilitud perfilada con escaneo adaptativo (core.fit_engine).
        try:
            results = profile_likelihood(state, progress_cb=_progress)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("fit.profile_likelihood"),
                                            f"{type(exc).__name__}: {exc}")
            return
        if not results:
            QtWidgets.QMessageBox.information(
                self, tr("fit.profile_likelihood"),
                "No hay parámetros libres para perfilar.")
            return
        self.statusBar().showMessage(
            f"Verosimilitud perfilada: {len(results)} parámetros", 5000)
        self._show_profile_dialog(results)

    def _show_profile_dialog(self, results: dict) -> None:
        if not results:
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("msg.profile_lik_title"))
        dlg.resize(900, 600)
        v = QtWidgets.QVBoxLayout(dlg)
        v.addWidget(QtWidgets.QLabel(tr("dialog.profile_lik_subtitle")))
        fig = Figure(figsize=(8.5, 5.0), dpi=96)
        canvas = FigureCanvas(fig); v.addWidget(canvas, stretch=1)
        keys = list(results.keys())
        ncols = 2 if len(keys) > 1 else 1
        nrows = (len(keys) + ncols - 1) // ncols
        for i, k in enumerate(keys, 1):
            ax = fig.add_subplot(nrows, ncols, i)
            r = results[k]
            ax.plot(r["scan_values"], r["d_chi2"], "o-", color="#2563eb", ms=3)
            ax.axhline(1.0, color="#888", ls="--", lw=0.8)
            ax.axhline(4.0, color="#bbb", ls=":", lw=0.8)
            ax.axvline(r["best"], color="#ef4444", lw=0.8)
            ax.set_title(k, fontsize=9)
            ax.set_ylabel("Δχ²", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.grid(alpha=0.3)
        fig.tight_layout(); canvas.draw_idle()
        # Resumen como texto
        text_lines = []
        for k, r in results.items():
            best = r["best"]; pl = r.get("plus_1s"); mi = r.get("minus_1s")
            p_txt = f"+{pl:.4g}" if pl is not None else "—"
            m_txt = f"−{mi:.4g}" if mi is not None else "—"
            text_lines.append(f"  {k:14s} = {best:.6g}  ({p_txt} / {m_txt})")
        summary = QtWidgets.QTextEdit(); summary.setReadOnly(True)
        summary.setMaximumHeight(120)
        summary.setStyleSheet("QTextEdit { font-family: monospace; font-size: 10pt; }")
        summary.setPlainText("\n".join(text_lines))
        v.addWidget(summary)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.exec()

    # ── Ajuste en serie (batch) ─────────────────────────────────────────
    def on_batch_fit(self) -> None:
        dlg = BatchFitDialog(self)
        dlg.exec()

    def on_constraints(self) -> None:
        dlg = ConstraintsDialog(self)
        dlg.exec()

    def on_physical_presets(self) -> None:
        """Cuatro botones rápidos para imponer relaciones físicas habituales."""
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("options.physical_presets"))
        dlg.resize(520, 240)
        v = QtWidgets.QVBoxLayout(dlg)
        v.addWidget(QtWidgets.QLabel(
            "Aplica con un clic relaciones físicas sobre las componentes activas."))

        def _apply_321() -> None:
            """3:2:1 fijado en int1=3, int2=2, int3=1."""
            self._building = True
            for cp in self.components_panels:
                if not cp.to_view_state().enabled:
                    continue
                cp.params["int1"].set_value(3.0); cp.params["int1"].set_fixed(True)
                cp.params["int2"].set_value(2.0); cp.params["int2"].set_fixed(True)
                cp.params["int3"].set_value(1.0); cp.params["int3"].set_fixed(True)
            self._building = False
            self._refresh_plot()

        def _equal_widths() -> None:
            """Γ2 = Γ3 = 1 (misma anchura)."""
            self._building = True
            for cp in self.components_panels:
                if not cp.to_view_state().enabled:
                    continue
                cp.params["gamma2"].set_value(1.0); cp.params["gamma2"].set_fixed(True)
                cp.params["gamma3"].set_value(1.0); cp.params["gamma3"].set_fixed(True)
            self._building = False
            self._refresh_plot()

        def _link_delta() -> None:
            """δ de las componentes 2 y 3 atados al δ del componente 1."""
            for idx in (2, 3):
                cp = self.components_panels[idx - 1]
                if cp.to_view_state().enabled:
                    self.constraints = [c for c in self.constraints
                                         if c.get("target") != f"s{idx}_delta"]
                    self.constraints.append({
                        "target": f"s{idx}_delta", "source": "s1_delta",
                        "factor": 1.0, "offset": 0.0,
                    })
            self._refresh_plot()

        def _link_gamma() -> None:
            """Γ1 de componentes 2 y 3 atados a Γ1 del 1."""
            for idx in (2, 3):
                cp = self.components_panels[idx - 1]
                if cp.to_view_state().enabled:
                    self.constraints = [c for c in self.constraints
                                         if c.get("target") != f"s{idx}_gamma1"]
                    self.constraints.append({
                        "target": f"s{idx}_gamma1", "source": "s1_gamma1",
                        "factor": 1.0, "offset": 0.0,
                    })
            self._refresh_plot()

        for label, fn in (
            ("Sextetes polvo 3:2:1", _apply_321),
            ("Mismas anchuras (γ2 = γ3 = 1)", _equal_widths),
            ("Ligar δ a componente 1", _link_delta),
            ("Ligar Γ1 a componente 1", _link_gamma),
        ):
            btn = QtWidgets.QPushButton(label)
            btn.clicked.connect(fn)
            v.addWidget(btn)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); v.addWidget(bb)
        dlg.exec()
