"""Herramientas auxiliares de ajuste para la GUI Qt."""
from __future__ import annotations

import json

import numpy as np
from PySide6 import QtWidgets
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from mossbauer_i18n import tr
from core.fit_engine import profile_likelihood
from gui.dialogs import BatchFitDialog, ConstraintsDialog, GlobalNeelFitDialog


class FitToolsMixin:
    def on_auto_fit_from_minima(self) -> None:
        """Atajo: inicializa desde mínimos y a continuación ejecuta el ajuste."""
        if self.on_init_from_minima(show_message=False):
            if not self.is_distribution_mode:
                self.on_fit()

    def on_auto_fit_residual(self) -> None:
        """«Autoajustar el residuo»: añade componentes para lo que el modelo
        actual no explica, sin tocar las que ya hay.

        1. Quita a los datos la absorción de las componentes activas (queda el
           residuo sobre la línea base).
        2. Detecta mínimos en ese residuo y construye componentes nuevas en los
           huecos libres (como «Autoajustar desde mínimos»).
        3. Ajusta con TODOS los parámetros de las componentes previas fijos y
           al terminar restaura el «fijo» que tenía cada uno, para que un
           ajuste normal posterior pueda refinarlo todo junto.
        """
        from core.reconstruction import reconstruct_discrete_model
        from gui.panels import ComponentPanel
        if self.is_distribution_mode or self.file.velocity is None or self.file.y_data is None:
            return
        previas = [c for c in self._active_component_states()]
        if not previas:
            QtWidgets.QMessageBox.information(
                self, tr("fit.auto_residual"), tr("msg.auto_residual_no_components"))
            return
        state = self._build_state()
        if state is None:
            return
        v, y = self.file.velocity, self.file.y_data
        try:
            con = reconstruct_discrete_model(
                v, y, state.values, state.components, state.constraints,
                absorber_model=state.absorber_model, line_profile_kind=state.line_profile,
                voigt_sigma=state.voigt_sigma)
            sin = reconstruct_discrete_model(
                v, y, state.values, [], [], absorber_model=state.absorber_model,
                line_profile_kind=state.line_profile, voigt_sigma=state.voigt_sigma)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, tr("fit.auto_residual"), str(exc))
            return
        y_res = np.asarray(con.residual, dtype=float) + np.asarray(sin.model, dtype=float)
        peaks, baseline, slope = self.detect_absorption_minima(y_override=y_res)
        # En el residuo la absorción máxima es pequeña y los umbrales relativos
        # de la detección dejan pasar ruido: se exige además que cada mínimo
        # supere 2σ del ruido por punto y un 25 % del más profundo.
        ruido = float(np.std(np.diff(np.asarray(y, dtype=float)))) / np.sqrt(2.0)
        hondo = max((float(p.get("smooth_depth", p["depth"])) for p in peaks), default=0.0)
        umbral = max(2.0 * ruido, 0.25 * hondo)
        peaks = [p for p in peaks if float(p.get("smooth_depth", p["depth"])) >= umbral]
        ocupados = {c.idx for c in previas}
        libres = [i for i in range(1, len(self.components_panels) + 1) if i not in ocupados]
        if not peaks or not libres:
            QtWidgets.QMessageBox.information(
                self, tr("fit.auto_residual"),
                tr("msg.auto_residual_none") if not peaks else tr("msg.auto_residual_full"))
            return
        nuevas, params = self._components_from_peaks(peaks, baseline, slope)
        # Las nuevas van a los huecos libres, en orden.
        remap = {idx: libres[k] for k, (idx, _kind, _g) in enumerate(nuevas) if k < len(libres)}
        nuevas = [(remap[idx], kind, g) for idx, kind, g in nuevas if idx in remap]
        valores = {}
        for key, val in params.items():
            if key.startswith("s") and "_" in key:
                pre, name = key.split("_", 1)
                try:
                    idx = int(pre[1:])
                except ValueError:
                    continue
                if idx in remap:
                    valores[f"s{remap[idx]}_{name}"] = val
        # Estado previo, para descartar las nuevas si no mejoran el modelo.
        snapshot = self._project_state().to_session_payload()
        prev_result = self.runtime_results.fit_result
        prev_gui = self.runtime_results.gui_result
        prev_checks = (self.fit_checks(), getattr(self, "_fit_checks_note", ""),
                       self.fit_summary_label.text() if hasattr(self, "fit_summary_label") else "")
        sigma = (np.asarray(state.sigma_data, dtype=float) if state.sigma_data is not None
                 else np.full(np.shape(y), float(np.std(np.diff(y))) / np.sqrt(2.0)))
        chi2_prev = float(np.sum((np.asarray(con.residual, dtype=float)
                                  / np.maximum(sigma, 1e-300)) ** 2))
        # Congelar las previas, recordando su «fijo».
        fijos_previos = {(c.idx, name): ctl.is_fixed()
                         for c in previas
                         for name, ctl in self.components_panels[c.idx - 1].params.items()}
        self._building = True
        try:
            self._sync_component_count(max(ocupados | {idx for idx, _k, _g in nuevas}))
            for idx, kind, _g in nuevas:
                cp = self.components_panels[idx - 1]
                cp.enabled.setChecked(True)
                cp.type_combo.setCurrentText(kind)
                cp.apply_values({k: val for k, val in valores.items() if k.startswith(f"s{idx}_")})
                for name in ComponentPanel._USED_BY.get(kind, set()):
                    cp.params[name].set_fixed(False)
            # Los parámetros que el tipo no usa quedan como estaban (fijos).
            for c in previas:
                for ctl in self.components_panels[c.idx - 1].params.values():
                    ctl.set_fixed(True)
        finally:
            self._building = False
        self._simulate_enabled = True
        self._refresh_plot()
        resumen = ", ".join(
            tr("text.component_kind_label", idx=idx, kind=tr(f"kind.{kind}", default=kind))
            for idx, kind, _g in nuevas)
        try:
            self.on_fit()
        finally:
            self._building = True
            try:
                for (idx, name), fijo in fijos_previos.items():
                    self.components_panels[idx - 1].params[name].set_fixed(fijo)
            finally:
                self._building = False
        res = self.runtime_results.fit_result
        if res is None or res is prev_result:
            return
        # ¿Mejoran de verdad? BIC (misma definición que el motor): las nuevas
        # deben bajarlo al menos 6 (evidencia fuerte); si no, solo explican
        # ruido o un desajuste pequeño del modelo y se descartan.
        n_obs = int(np.size(y))
        nuevas_idx = {idx for idx, _k, _g in nuevas}
        n_nuevos = sum(1 for k in res.free_keys
                       if k.startswith("s") and k.split("_", 1)[0][1:].isdigit()
                       and int(k.split("_", 1)[0][1:]) in nuevas_idx)
        k_prev = max(0.0, float(res.stats.get("n_params", len(res.free_keys))) - n_nuevos)
        bic_prev = n_obs * np.log(max(chi2_prev / n_obs, 1e-300)) + k_prev * np.log(n_obs)
        d_bic = float(res.stats.get("bic", np.inf)) - bic_prev
        if not d_bic <= -6.0:
            mode_idx = self.mode_combo.currentIndex()
            self._apply_session_payload(snapshot)
            self.mode_combo.setCurrentIndex(mode_idx)
            if prev_result is not None:
                self.runtime_results.set_discrete_fit(prev_result, gui_result=prev_gui)
            else:
                self.runtime_results.clear()
            self._set_fit_diagnostics(*prev_checks)
            self._refresh_plot()
            QtWidgets.QMessageBox.information(
                self, tr("fit.auto_residual"),
                tr("msg.auto_residual_rejected", summary=resumen, dbic=f"{d_bic:+.1f}"))
            return
        self.statusBar().showMessage(
            tr("msg.auto_residual_done", summary=resumen) + f"  ΔBIC = {d_bic:+.1f}", 8000)

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
        self.statusBar().showMessage(tr("status.fitting_before_profile", default="Fitting before profiling…"))
        QtWidgets.QApplication.processEvents()

        def _progress(msg: str, _i: int, _n: int) -> None:
            self.statusBar().showMessage(msg)
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
                tr("msg.profile_lik_no_free", default="No free parameters to profile."))
            return
        self.statusBar().showMessage(
            tr("status.profile_lik_done", n=len(results), default=f"Profile likelihood: {len(results)} parameters"), 5000)
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
        # El warm-start del batch escribe en los widgets con señales bloqueadas:
        # al cerrar, sincroniza plot y panel de info con el último ajuste.
        self._simulate_enabled = True
        self._refresh_plot()

    # ── Ajuste global Néel-Arrhenius multi-temperatura ──────────────────
    def on_global_neel_fit(self) -> None:
        dlg = GlobalNeelFitDialog(self)
        dlg.exec()

    def on_constraints(self) -> None:
        dlg = ConstraintsDialog(self)
        dlg.exec()

    def apply_preset_321(self) -> None:
        """Preset físico 3:2:1 fijado en int1=3, int2=2, int3=1 (polvo)."""
        self._building = True
        for cp in self.components_panels:
            if not cp.to_view_state().enabled:
                continue
            cp.params["int1"].set_value(3.0); cp.params["int1"].set_fixed(True)
            cp.params["int2"].set_value(2.0); cp.params["int2"].set_fixed(True)
            cp.params["int3"].set_value(1.0); cp.params["int3"].set_fixed(True)
        self._building = False
        self._refresh_plot()

    def apply_preset_equal_widths(self) -> None:
        """Preset físico Γ2 = Γ3 = 1 (misma anchura en todas las líneas)."""
        self._building = True
        for cp in self.components_panels:
            if not cp.to_view_state().enabled:
                continue
            cp.params["gamma2"].set_value(1.0); cp.params["gamma2"].set_fixed(True)
            cp.params["gamma3"].set_value(1.0); cp.params["gamma3"].set_fixed(True)
        self._building = False
        self._refresh_plot()

    def apply_preset_tie(self, param: str) -> None:
        """Ata ``param`` de todos los componentes activos (2..N) al del componente 1."""
        for cp in self.components_panels[1:]:
            if not cp.to_view_state().enabled:
                continue
            target = f"s{cp.idx}_{param}"
            self.constraints = [c for c in self.constraints if c.get("target") != target]
            self.constraints.append({
                "target": target, "source": f"s1_{param}",
                "factor": 1.0, "offset": 0.0,
            })
        self._refresh_plot()

    def on_physical_presets(self) -> None:
        """Cuatro botones rápidos para imponer relaciones físicas habituales."""
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("options.physical_presets"))
        dlg.resize(520, 240)
        v = QtWidgets.QVBoxLayout(dlg)
        v.addWidget(QtWidgets.QLabel(tr(
            "dialog.physical_presets_desc",
            default="Click to apply common physical constraints to active components.")))
        _apply_321 = self.apply_preset_321
        _equal_widths = self.apply_preset_equal_widths

        for label, fn in (
            (tr("button.preset_powder"), _apply_321),
            (tr("button.preset_equal_widths"), _equal_widths),
            (tr("button.preset_tie_delta"), lambda: self.apply_preset_tie("delta")),
            (tr("button.preset_tie_gamma"), lambda: self.apply_preset_tie("gamma1")),
        ):
            btn = QtWidgets.QPushButton(label)
            btn.clicked.connect(fn)
            v.addWidget(btn)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); v.addWidget(bb)
        dlg.exec()
