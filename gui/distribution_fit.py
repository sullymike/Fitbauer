"""Ajuste de distribuciones hiperfinas desde la GUI Qt."""
from __future__ import annotations

import numpy as np
from PySide6 import QtWidgets
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from scipy.optimize import least_squares

from mossbauer_i18n import tr
from core.constants import BHF_DEFAULT_T
from core.reconstruction import reconstruct_distribution_curves
from core.validation import format_validation_issues, validate_distribution_parameters
from gui.fit_workflow import GuiFitRenderState, GuiFitResult
from mossbauer_distribution import (
    fit_hyperfine_distribution,
    fit_gaussian_hyperfine_distribution,
    fit_binomial_hyperfine_distribution,
    fit_fixed_hyperfine_distribution,
)


class DistributionFitMixin:
    def _active_sharp_components_for_distribution(self) -> tuple[list[dict[str, float]] | None, list[int]]:
        if not self.dist_use_sharp:
            return None, []
        components: list[dict[str, float]] = []
        indices: list[int] = []
        for cp in self.components_panels:
            comp_state = cp.to_view_state()
            if not comp_state.enabled:
                continue
            int1_gui = comp_state.value("int1", 1.0)
            int2_gui = comp_state.value("int2", 1.0)
            int3_gui = comp_state.value("int3", 1.0)
            if comp_state.kind == "Sextete":
                engine_int1 = int3_gui * int1_gui
                if abs(int1_gui) > 1e-12:
                    engine_int2_rel = 1.5 * int2_gui / int1_gui
                    engine_int3_rel = 3.0 / int1_gui
                else:
                    engine_int2_rel = 0.0
                    engine_int3_rel = 0.0
            else:
                engine_int1 = int1_gui
                engine_int2_rel = int2_gui
                engine_int3_rel = int3_gui
            comp = {
                "kind": comp_state.kind,
                "delta": comp_state.value("delta", 0.0),
                "quad": comp_state.value("quad", 0.0),
                "bhf": comp_state.value("bhf", 33.0),
                "gamma": comp_state.value("gamma1", 0.18),
                "gamma2_rel": comp_state.value("gamma2", 1.0),
                "gamma3_rel": comp_state.value("gamma3", 1.0),
                "int1": engine_int1,
                "int2_rel": engine_int2_rel,
                "int3_rel": engine_int3_rel,
                "depth": comp_state.value("depth", 0.0),
                "depth_fixed": comp_state.is_fixed("depth"),
            }
            components.append(comp)
            indices.append(comp_state.idx)
        return (components or None), indices

    # ── L-curve α scanner (modo distribución) ────────────────────────────
    def on_lcurve(self) -> None:
        if not self.is_distribution_mode:
            QtWidgets.QMessageBox.information(
                self, tr("bhf.lcurve_alpha"),
                "Disponible solo en modo distribución P(BHF) / P(ΔEQ).")
            return
        if self.file.velocity is None or self.file.y_data is None:
            return
        d = self.dist_panel
        var = self.dist_variable
        dist_state = d.to_view_state(variable=var)
        alphas = np.logspace(-6, 2, 25)
        self.statusBar().showMessage(f"Escaneando α (n={len(alphas)})…")
        QtWidgets.QApplication.processEvents()
        bmin = float(dist_state.bmin); bmax = max(bmin + 0.5, float(dist_state.bmax))
        nbins = max(5, int(dist_state.nbins))
        sharp_components, _sharp_indices = self._active_sharp_components_for_distribution()
        calib_state = self.calib.to_view_state()
        fit_baseline = not calib_state.is_fixed("baseline")
        fit_slope = not calib_state.is_fixed("slope")
        try:
            common = dict(
                delta=dist_state.delta, gamma=dist_state.gamma,
                fit_baseline=fit_baseline, fit_slope=fit_slope,
                baseline=calib_state.baseline, slope=calib_state.slope,
                pmin=bmin, pmax=bmax, nbins=nbins, sigma=self.file.sigma,
                sharp_components=sharp_components,
            )
            if var == "quad":
                fits = [fit_hyperfine_distribution(
                    self.file.velocity, self.file.y_data, variable="quad",
                    bhf=dist_state.fixed_bhf, alpha=float(a), reg_mode=dist_state.reg_mode, **common) for a in alphas]
            else:
                fits = [fit_hyperfine_distribution(
                    self.file.velocity, self.file.y_data, variable="bhf",
                    quad=dist_state.quad, alpha=float(a), reg_mode=dist_state.reg_mode, **common) for a in alphas]
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("bhf.lcurve_alpha"),
                                            f"{type(exc).__name__}: {exc}")
            return
        # Diálogo: residuo² vs rugosidad
        resid_norm = np.array([float(np.linalg.norm(f.residuals)) for f in fits])
        rough = np.array([float(np.linalg.norm(np.diff(f.weights, 2)))
                          if f.weights.size > 2 else 0.0 for f in fits])
        rms = np.array([f.rms for f in fits])
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("bhf.lcurve_alpha"))
        dlg.resize(820, 540)
        v = QtWidgets.QVBoxLayout(dlg)
        fig = Figure(figsize=(8.0, 5.0), dpi=96)
        cv = FigureCanvas(fig); v.addWidget(cv, stretch=1)
        ax1 = fig.add_subplot(1, 2, 1)
        ax1.loglog(rough, resid_norm, "o-", color="#2563eb", ms=4)
        for i, a in enumerate(alphas):
            ax1.annotate(f"{np.log10(a):+.1f}", (rough[i], resid_norm[i]),
                          fontsize=6, alpha=0.7)
        ax1.set_xlabel(tr("plot.lcurve_xlabel"))
        ax1.set_ylabel(tr("plot.lcurve_ylabel"))
        ax1.set_title(tr("plot.lcurve_title"))
        ax1.grid(True, alpha=0.3, which="both")
        ax2 = fig.add_subplot(1, 2, 2)
        ax2.semilogx(alphas, rms, "o-", color="#ef4444", ms=4)
        ax2.set_xlabel("α")
        ax2.set_ylabel(tr("plot.label_rms"))
        ax2.set_title(tr("plot.alpha_scan_title"))
        ax2.grid(True, alpha=0.3, which="both")
        fig.tight_layout(); cv.draw_idle()
        best_idx = int(np.nanargmin(rms)) if rms.size else 0
        suggest = float(alphas[best_idx]) if alphas.size else dist_state.alpha
        buttons = QtWidgets.QHBoxLayout()
        btn_use = QtWidgets.QPushButton(tr("button.use_lcurve", default="Usar α={value}", value=suggest))
        btn_use.clicked.connect(lambda _=False, a=suggest, dialog=dlg: (d.log_alpha.set_value(float(np.log10(a))), dialog.accept()))
        buttons.addWidget(btn_use); buttons.addStretch(1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); buttons.addWidget(bb)
        v.addLayout(buttons)
        dlg.exec()



    def _load_fixed_distribution(self, path: Path) -> tuple[np.ndarray, np.ndarray]:
        """Lee dos columnas (centers, weights) de un .txt/.dat/.csv."""
        raw = Path(path).read_text(encoding="utf-8", errors="replace").strip().splitlines()
        c, w = [], []
        for line in raw:
            line = line.strip()
            if not line or line.startswith(("#", "//")):
                continue
            parts = line.replace(",", " ").replace(";", " ").split()
            if len(parts) < 2:
                continue
            try:
                c.append(float(parts[0])); w.append(float(parts[1]))
            except ValueError:
                continue
        return np.array(c, dtype=float), np.array(w, dtype=float)

    def _on_load_fixed_distribution(self) -> None:
        """Carga una distribución P fija desde fichero (dos columnas)."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, tr("bhf.load_fixed"), str(ROOT),
            "Texto (*.txt *.dat *.csv *.tsv);;All (*.*)")
        if not path:
            return
        self.dist_panel.fixed_path = Path(path)
        self.statusBar().showMessage(f"P fija: {path}", 5000)

    # ── Ajuste distribución P(BHF) ──────────────────────────────────────
    def on_fit_distribution(self) -> None:
        self._simulate_enabled = True
        if self.file.velocity is None or self.file.y_data is None:
            return
        d = self.dist_panel
        var = self.dist_variable
        dist_state = d.to_view_state(variable=var)
        issues = validate_distribution_parameters(dist_state)
        if issues:
            QtWidgets.QMessageBox.warning(
                self,
                tr("msg.validation_title", default="Parámetros no válidos"),
                format_validation_issues(issues),
            )
            return
        bmin = float(dist_state.bmin)
        bmax = max(bmin + 0.5, float(dist_state.bmax))
        nbins = max(5, int(dist_state.nbins))
        alpha = dist_state.alpha
        shape = dist_state.shape
        label = "P(ΔEQ)" if var == "quad" else "P(BHF)"
        self.statusBar().showMessage(f"Ajustando {label} [{shape}]…")
        sharp_components, sharp_indices = self._active_sharp_components_for_distribution()
        calib_state = self.calib.to_view_state()
        fit_baseline = not calib_state.is_fixed("baseline")
        fit_slope = not calib_state.is_fixed("slope")
        base_delta = dist_state.delta
        base_gamma = dist_state.gamma
        v_arr = self.file.velocity
        y_arr = self.file.y_data

        def run_fit(delta_value: float, gamma_value: float, sharp_for_fit: list[dict[str, float]] | None):
            common = dict(
                variable=var, delta=delta_value, gamma=gamma_value,
                quad=(0.0 if var == "quad" else dist_state.quad),
                bhf=(dist_state.fixed_bhf if var == "quad" else BHF_DEFAULT_T),
                baseline=calib_state.baseline, slope=calib_state.slope,
                sharp_components=sharp_for_fit,
            )
            if shape == "Histograma":
                return fit_hyperfine_distribution(
                    v_arr, y_arr, pmin=bmin, pmax=bmax, nbins=nbins, alpha=alpha,
                    fit_baseline=fit_baseline, fit_slope=fit_slope,
                    sigma=self.file.sigma, reg_mode=dist_state.reg_mode, **common)
            if shape == "Gaussiana":
                return fit_gaussian_hyperfine_distribution(
                    v_arr, y_arr, pmin=bmin, pmax=bmax, nbins=nbins, **common)
            if shape == "Binomial":
                return fit_binomial_hyperfine_distribution(
                    v_arr, y_arr, pmin=bmin, pmax=bmax, nbins=nbins, **common)
            if shape == "Fija":
                if dist_state.fixed_distribution_path is None:
                    raise RuntimeError("Carga primero un fichero de P fija.")
                centers_arr, weights_arr = self._load_fixed_distribution(dist_state.fixed_distribution_path)
                return fit_fixed_hyperfine_distribution(
                    v_arr, y_arr, centers_arr, weights_arr, **common)
            raise RuntimeError(f"Forma desconocida: {shape}")

        outer_specs: list[tuple[str, str, float, float]] = []
        if dist_state.refine_global:
            if not dist_state.is_fixed("delta"):
                outer_specs.append(("dist_delta", "lin", -2.5, 2.5))
            if not dist_state.is_fixed("gamma"):
                outer_specs.append(("dist_gamma", "loggamma", 0.03, 1.0))
        if sharp_components:
            for pos, idx in enumerate(sharp_indices):
                cp = self.components_panels[idx - 1]
                comp_state = cp.to_view_state()
                for pname in ("delta", "quad", "bhf", "gamma1"):
                    if pname == "quad" and comp_state.kind == "Singlete":
                        continue
                    if pname == "bhf" and comp_state.kind != "Sextete":
                        continue
                    ctl = cp.params[pname]  # widget necesario para límites y actualización posterior
                    if comp_state.is_fixed(pname):
                        continue
                    outer_specs.append((f"sharp:{pos}:{pname}",
                                        "loggamma" if pname == "gamma1" else "lin",
                                        ctl._lo, ctl._hi))

        def x0_bounds() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            x0, lo, hi = [], [], []
            for key, kind, lo_v, hi_v in outer_specs:
                if key == "dist_delta":
                    cur = base_delta
                elif key == "dist_gamma":
                    cur = base_gamma
                else:
                    _sharp, pos_txt, pname = key.split(":")
                    cur = float(sharp_components[int(pos_txt)]["gamma" if pname == "gamma1" else pname])
                if kind == "loggamma":
                    x0.append(np.log(max(cur, lo_v))); lo.append(np.log(lo_v)); hi.append(np.log(hi_v))
                else:
                    x0.append(cur); lo.append(lo_v); hi.append(hi_v)
            return np.array(x0, dtype=float), np.array(lo, dtype=float), np.array(hi, dtype=float)

        def expand(x: np.ndarray) -> tuple[float, float, list[dict[str, float]] | None]:
            delta_value = base_delta
            gamma_value = base_gamma
            local_sharp = [dict(c) for c in sharp_components] if sharp_components else None
            for i, (key, kind, _lo, _hi) in enumerate(outer_specs):
                value = float(np.exp(x[i])) if kind == "loggamma" else float(x[i])
                if key == "dist_delta":
                    delta_value = value
                elif key == "dist_gamma":
                    gamma_value = value
                elif local_sharp is not None:
                    _sharp, pos_txt, pname = key.split(":")
                    local_sharp[int(pos_txt)]["gamma" if pname == "gamma1" else pname] = value
            return delta_value, gamma_value, local_sharp

        def compute_distribution(update_progress):
            fitted_x_local = None
            if outer_specs:
                update_progress(tr("progress.distribution_refine",
                                   default="Refinando δ y Γ globales…"))
                x0, lo, hi = x0_bounds()
                x0 = np.clip(x0, lo, hi)
                def residual_outer(x: np.ndarray) -> np.ndarray:
                    dd, gg, ss = expand(x)
                    return run_fit(dd, gg, ss).residuals
                opt = least_squares(residual_outer, x0, bounds=(lo, hi), max_nfev=60)
                fitted_x_local = opt.x
                delta_final, gamma_final, sharp_final = expand(fitted_x_local)
                update_progress(tr("progress.distribution_compute_final",
                                   default="Calculando distribución final…"))
                result_local = run_fit(delta_final, gamma_final, sharp_final)
            else:
                update_progress(tr("progress.distribution_compute", shape=shape,
                                   default=f"Calculando distribución {shape}…"))
                result_local = run_fit(base_delta, base_gamma, sharp_components)
            return result_local, fitted_x_local

        fit_output = self._run_with_fit_progress(
            tr("progress.distribution_title", default="Distribución hiperfina"),
            tr("progress.distribution_prepare", default="Preparando ajuste de distribución…"),
            compute_distribution,
            error_title=tr("fit.run"),
        )
        if fit_output is None:
            return
        result, fitted_x = fit_output

        self._building = True
        self.calib.baseline.set_value(float(result.baseline))
        self.calib.slope.set_value(float(result.slope))
        if fitted_x is not None:
            for i, (key, kind, _lo, _hi) in enumerate(outer_specs):
                value = float(np.exp(fitted_x[i])) if kind == "loggamma" else float(fitted_x[i])
                if key == "dist_delta":
                    d.delta.set_value(value)
                elif key == "dist_gamma":
                    d.gamma.set_value(value)
                elif key.startswith("sharp:"):
                    _sharp, pos_txt, pname = key.split(":")
                    cp = self.components_panels[sharp_indices[int(pos_txt)] - 1]
                    cp.params[pname].set_value(value)
        if self.dist_use_sharp and result.sharp_weights is not None:
            for idx, weight in zip(sharp_indices, result.sharp_weights):
                self.components_panels[idx - 1].params["depth"].set_value(float(weight))
        self._building = False

        components_for_plot: list[tuple[int, str, np.ndarray]] = []
        if dist_state.use_sharp and result.sharp_weights is not None and result.sharp_weights.size:
            sharp_for_render = expand(fitted_x)[2] if fitted_x is not None else sharp_components
            dist_name = "P(ΔEQ)" if var == "quad" else "P(BHF)"
            reconstructed = reconstruct_distribution_curves(
                self.file.velocity,
                result.fitted_curve,
                result.baseline,
                result.slope,
                sharp_for_render,
                sharp_indices,
                result.sharp_weights,
                distribution_kind=dist_name,
            )
            for curve in reconstructed:
                label = curve.kind if curve.idx == 0 else f"Nítido {tr(f'kind.{curve.kind}', default=curve.kind)}"
                components_for_plot.append((curve.idx, label, curve.y))
        msg = (f"{label}: bins={nbins}  α=10^{dist_state.log_alpha:.2f}  "
               f"RMS={result.rms:.5g}")
        gui_result = GuiFitResult(
            mode="distribution",
            raw_result=result,
            render=GuiFitRenderState(
                velocity=self.file.velocity,
                y_data=self.file.y_data,
                model=result.fitted_curve,
                components=components_for_plot,
            ),
            message=msg,
        )
        self.runtime_results.set_distribution_fit(result, gui_result=gui_result)
        self._finish_gui_fit_result(gui_result)
        self._schedule_plotly_update()
        class _R:
            pass
        r = _R()
        r.stats = {"chi2": float(np.sum(result.residuals**2)), "red_chi2": float(result.rms),
                   "dof": 0.0, "aic": 0.0, "bic": 0.0}
        r.free_keys = []
        r.values = {"baseline": result.baseline, "slope": result.slope, "alpha": result.alpha}
        r.errors = {}
        r.correlations = {}
        r.n_starts = 1
        self.info_panel.show_result(r)
        self._show_distribution_dialog(result)

    def _show_distribution_dialog(self, result) -> None:
        var = self.dist_variable
        title = "P(ΔEQ)" if var == "quad" else "P(BHF)"
        xlabel = (tr("plot.distribution_xlabel_deq") if var == "quad"
                  else tr("plot.distribution_xlabel_bhf"))
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(720, 480)
        v = QtWidgets.QVBoxLayout(dlg)
        fig = Figure(figsize=(8.0, 4.5), dpi=96)
        cv = FigureCanvas(fig); v.addWidget(cv, stretch=1)
        ax = fig.add_subplot(111)
        ax.plot(result.bhf_centers, result.probability, "-", color="#2563eb", lw=2.0)
        ax.fill_between(result.bhf_centers, result.probability, 0, color="#93c5fd", alpha=0.45)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(title)
        ax.grid(True, alpha=0.3)
        fig.tight_layout(); cv.draw_idle()
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); v.addWidget(bb)
        dlg.exec()
