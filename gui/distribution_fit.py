"""Ajuste de distribuciones hiperfinas desde la GUI Qt."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from PySide6 import QtWidgets
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from scipy.optimize import least_squares

from mossbauer_i18n import tr
from core.constants import BHF_DEFAULT_T, SEXTET_PARAM_NAMES
from core.physics import component_absorption
from core.plot_styles import get_style
from core.reconstruction import reconstruct_distribution_curves
from core.validation import format_validation_issues, validate_distribution_parameters
from core.param_overrides import effective_fit_init_specs as _eff_fi, effective_distribution_specs as _eff_ds
from gui.fit_workflow import GuiFitRenderState, GuiFitResult
from mossbauer_distribution import (
    fit_hyperfine_distribution,
    fit_gaussian_hyperfine_distribution,
    fit_binomial_hyperfine_distribution,
    fit_fixed_hyperfine_distribution,
    fit_bhf_quad_distribution,
)

ROOT = Path(__file__).resolve().parents[1]


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
            comp: dict = {
                "kind": comp_state.kind,
                "delta": comp_state.value("delta", 0.0),
                "quad": comp_state.value("quad", 0.0),
                "bhf": comp_state.value("bhf", 33.0),
                "gamma": comp_state.value("gamma1", 0.36),
                "gamma2_rel": comp_state.value("gamma2", 1.0),
                "gamma3_rel": comp_state.value("gamma3", 1.0),
                "int1": engine_int1,
                "int2_rel": engine_int2_rel,
                "int3_rel": engine_int3_rel,
                "depth": comp_state.value("depth", 0.0),
                "depth_fixed": comp_state.is_fixed("depth"),
            }
            # Parámetros de relajación/Néel para los nuevos tipos de componente
            if comp_state.kind == "Relajacion":
                comp["relax_fraction"] = comp_state.value("relax_fraction", 1.0)
                comp["relax_log_nu"] = comp_state.value("relax_log_nu", 5.0)
            elif comp_state.kind == "BlumeTjon":
                comp["relax_log_nu"] = comp_state.value("relax_log_nu", 5.0)
            elif comp_state.kind == "NeelSize":
                for _p in ("neel_temp_k", "neel_log10_keff", "neel_mean_d_nm",
                           "neel_sigma", "neel_log10_tau0", "neel_bins"):
                    comp[_p] = comp_state.value(_p, 0.0)
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
        _fi = _eff_fi()
        alphas = np.logspace(_fi["lcurve_alpha_lo"].default, _fi["lcurve_alpha_hi"].default, int(_fi["lcurve_n_points"].default))
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
        fig = Figure(figsize=(8.0, 5.0), dpi=96, constrained_layout=True)
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
        cv.draw_idle()
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

    # ── Ajuste distribución P(BHF) / P(ΔEQ) / P(IS) / 2D ───────────────────
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

        # Parámetros 2D (disponibles tras la actualización del panel)
        _ds = _eff_ds()
        qmin: float = float(d.qmin.value()) if hasattr(d, "qmin") else _ds["qmin"].default
        qmax: float = max(qmin + 0.05, float(d.qmax.value())) if hasattr(d, "qmax") else _ds["qmax"].default
        qbins: int = max(5, int(round(d.qbins.value()))) if hasattr(d, "qbins") else int(_ds["qbins"].default)
        alpha_q: float = 10.0 ** float(d.log_alpha_q.value()) if hasattr(d, "log_alpha_q") else 10.0 ** _ds["log_alpha_q"].default
        pair: tuple[str, str] = getattr(self, "dist_pair", ("bhf", "quad")) if shape == "2D" else ("bhf", "quad")

        label_map = {"bhf": "BHF", "quad": "ΔEQ", "delta": "IS"}
        label = (f"P({label_map.get(pair[0], pair[0])}, {label_map.get(pair[1], pair[1])})"
                 if shape == "2D" else f"P({label_map.get(var, var)})")

        self.statusBar().showMessage(f"Ajustando {label} [{shape}]…")
        sharp_components, sharp_indices = self._active_sharp_components_for_distribution()
        calib_state = self.calib.to_view_state()
        fit_baseline = not calib_state.is_fixed("baseline")
        fit_slope = not calib_state.is_fixed("slope")
        base_delta = dist_state.delta
        base_quad = dist_state.quad
        base_gamma = dist_state.gamma
        v_arr = self.file.velocity
        y_arr = self.file.y_data

        def run_fit(delta_value: float, quad_value: float, gamma_value: float,
                    sharp_for_fit: list[dict] | None):
            if shape == "2D":
                return fit_bhf_quad_distribution(
                    v_arr, y_arr,
                    variable_x=pair[0], variable_y=pair[1],
                    delta=delta_value, quad=quad_value,
                    bhf=(dist_state.fixed_bhf if "bhf" not in pair else BHF_DEFAULT_T),
                    gamma=gamma_value,
                    bmin=bmin, bmax=bmax, nbins_bhf=nbins,
                    qmin=qmin, qmax=qmax, nbins_quad=qbins,
                    alpha_bhf=alpha, alpha_quad=alpha_q,
                    fit_baseline=fit_baseline, fit_slope=fit_slope,
                    baseline=calib_state.baseline, slope=calib_state.slope,
                    sharp_components=sharp_for_fit,
                    sigma=self.file.sigma,
                )
            common = dict(
                variable=var, delta=delta_value, gamma=gamma_value,
                quad=(0.0 if var == "quad" else quad_value),
                bhf=(dist_state.fixed_bhf if var in ("quad", "delta") else BHF_DEFAULT_T),
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

        # outer_specs: parámetros globales libres a refinar en la capa exterior
        outer_specs: list[tuple[str, str, float, float]] = []
        if var != "delta" and not dist_state.is_fixed("delta"):
            outer_specs.append(("dist_delta", "lin", d.delta._lo, d.delta._hi))
        if ((shape != "2D" and var in ("bhf", "delta"))
                or (shape == "2D" and "quad" not in pair)):
            if not dist_state.is_fixed("quad"):
                outer_specs.append(("dist_quad", "lin", d.quad._lo, d.quad._hi))
        if not dist_state.is_fixed("gamma"):
            outer_specs.append(("dist_gamma", "loggamma", d.gamma._lo, d.gamma._hi))
        if sharp_components:
            for pos, idx in enumerate(sharp_indices):
                cp = self.components_panels[idx - 1]
                comp_state = cp.to_view_state()
                sharp_names = ["delta", "quad", "bhf", "gamma1"]
                if comp_state.kind == "Relajacion":
                    sharp_names.extend(("relax_fraction", "relax_log_nu"))
                elif comp_state.kind == "BlumeTjon":
                    sharp_names.append("relax_log_nu")
                elif comp_state.kind == "NeelSize":
                    sharp_names.extend(("neel_temp_k", "neel_log10_keff", "neel_mean_d_nm",
                                        "neel_sigma", "neel_log10_tau0", "neel_bins"))
                for pname in sharp_names:
                    if pname == "quad" and comp_state.kind == "Singlete":
                        continue
                    if pname == "bhf" and comp_state.kind not in (
                            "Sextete", "Relajacion", "BlumeTjon", "NeelSize"):
                        continue
                    ctl = cp.params.get(pname)
                    if ctl is None or comp_state.is_fixed(pname):
                        continue
                    outer_specs.append((f"sharp:{pos}:{pname}",
                                        "loggamma" if pname == "gamma1" else "lin",
                                        ctl._lo, ctl._hi))

        max_outer_evals = 60
        progress_state: dict = {"eval": 0, "best_rms": np.inf, "last_update": 0.0}

        def x0_bounds() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            x0, lo, hi = [], [], []
            for key, kind, lo_v, hi_v in outer_specs:
                if key == "dist_delta":
                    cur = base_delta
                elif key == "dist_quad":
                    cur = base_quad
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

        def expand(x: np.ndarray) -> tuple[float, float, float, list[dict] | None]:
            delta_value = base_delta
            quad_value = base_quad
            gamma_value = base_gamma
            local_sharp = [dict(c) for c in sharp_components] if sharp_components else None
            for i, (key, kind, _lo, _hi) in enumerate(outer_specs):
                value = float(np.exp(x[i])) if kind == "loggamma" else float(x[i])
                if key == "dist_delta":
                    delta_value = value
                elif key == "dist_quad":
                    quad_value = value
                elif key == "dist_gamma":
                    gamma_value = value
                elif local_sharp is not None:
                    _sharp, pos_txt, pname = key.split(":")
                    local_sharp[int(pos_txt)]["gamma" if pname == "gamma1" else pname] = value
            return delta_value, quad_value, gamma_value, local_sharp

        def compute_distribution(update_progress):
            fitted_x_local = None
            if outer_specs:
                update_progress(tr("progress.distribution_refine",
                                   default="Refinando parámetros globales libres…"))
                x0, lo, hi = x0_bounds()
                x0 = np.clip(x0, lo, hi)

                def residual_outer(x: np.ndarray) -> np.ndarray:
                    dd, qq, gg, ss = expand(x)
                    fit = run_fit(dd, qq, gg, ss)
                    resid = fit.residuals
                    rms = float(np.sqrt(np.mean(resid * resid))) if resid.size else float("nan")
                    progress_state["eval"] = int(progress_state["eval"]) + 1
                    if np.isfinite(rms):
                        progress_state["best_rms"] = min(float(progress_state["best_rms"]), rms)
                    now = time.monotonic()
                    if (progress_state["eval"] == 1
                            or now - float(progress_state["last_update"]) > 0.20):
                        progress_state["last_update"] = now
                        update_progress({
                            "phase": tr("progress.distribution_refine",
                                        default="Refinando parámetros globales libres…"),
                            "iteration": int(progress_state["eval"]),
                            "max_iter": max_outer_evals,
                            "rms": rms,
                            "best_rms": float(progress_state["best_rms"]),
                        })
                    return resid

                opt = least_squares(residual_outer, x0, bounds=(lo, hi), max_nfev=max_outer_evals)
                fitted_x_local = opt.x
                delta_final, quad_final, gamma_final, sharp_final = expand(fitted_x_local)
                update_progress(tr("progress.distribution_compute_final",
                                   default="Calculando distribución final…"))
                result_local = run_fit(delta_final, quad_final, gamma_final, sharp_final)
            else:
                update_progress(tr("progress.distribution_compute", shape=shape,
                                   default=f"Calculando distribución {shape}…"))
                result_local = run_fit(base_delta, base_quad, base_gamma, sharp_components)
            return result_local, fitted_x_local

        self._pre_fit_snapshot = self._project_state().to_session_payload()
        fit_output = self._run_with_fit_progress(
            tr("progress.distribution_title", default="Distribución hiperfina"),
            tr("progress.distribution_prepare", default="Preparando ajuste de distribución…"),
            compute_distribution,
            error_title=tr("fit.run"),
        )
        if fit_output is None:
            return
        if hasattr(self, "act_undo_fit"):
            self.act_undo_fit.setEnabled(True)
        result, fitted_x = fit_output

        self._building = True
        self.calib.baseline.set_value(float(result.baseline))
        self.calib.slope.set_value(float(result.slope))
        if fitted_x is not None:
            for i, (key, kind, _lo, _hi) in enumerate(outer_specs):
                value = float(np.exp(fitted_x[i])) if kind == "loggamma" else float(fitted_x[i])
                if key == "dist_delta":
                    d.delta.set_value(value)
                elif key == "dist_quad":
                    d.quad.set_value(value)
                elif key == "dist_gamma":
                    d.gamma.set_value(value)
                elif key.startswith("sharp:"):
                    _sharp, pos_txt, pname = key.split(":")
                    cp = self.components_panels[sharp_indices[int(pos_txt)] - 1]
                    cp.params[pname].set_value(value)
        if self.dist_use_sharp and hasattr(result, "sharp_weights") and result.sharp_weights is not None:
            for idx, weight in zip(sharp_indices, result.sharp_weights):
                self.components_panels[idx - 1].params["depth"].set_value(float(weight))
        self._building = False

        # Componentes para el gráfico
        # TODO (punto 4): los nítidos se reconstruyen aquí con component_absorption
        # usando los valores de los widgets + el peso ajustado. Una alternativa más
        # fiel sería usar build_sharp_kernel (que el propio ajuste emplea internamente),
        # de modo que si on_fit_distribution refina δ/Γ globales el gráfico sea
        # coherente con los residuos. La rama alternativa está en SHA a7c803b y se
        # puede recuperar cuando el multi-ajuste esté integrado.
        components_for_plot: list[tuple[int, str, np.ndarray]] = []
        if self.dist_use_sharp and hasattr(result, "sharp_weights") and result.sharp_weights is not None and result.sharp_weights.size:
            baseline_line = float(result.baseline) + float(result.slope) * self.file.velocity
            sharp_abs_sum = np.zeros_like(self.file.velocity, dtype=float)
            for idx, weight in zip(sharp_indices, result.sharp_weights):
                cp = self.components_panels[idx - 1]
                comp_state = cp.to_view_state()
                vals = cp.values_dict()
                pfx = f"s{idx}_"
                params = np.array([float(vals.get(pfx + name, 0.0)) for name in SEXTET_PARAM_NAMES], dtype=float)
                params[6] = float(weight)
                extras = None
                if comp_state.kind == "Relajacion":
                    extras = {
                        "blocked_fraction": float(vals.get(pfx + "relax_fraction", 1.0)),
                        "log10_nu": float(vals.get(pfx + "relax_log_nu", 5.0)),
                    }
                elif comp_state.kind == "BlumeTjon":
                    extras = {"log10_nu": float(vals.get(pfx + "relax_log_nu", 5.0))}
                elif comp_state.kind == "NeelSize":
                    extras = {
                        "temperature_k": float(vals.get(pfx + "neel_temp_k", 300.0)),
                        "log10_keff": float(vals.get(pfx + "neel_log10_keff", 4.0)),
                        "mean_d_nm": float(vals.get(pfx + "neel_mean_d_nm", 8.0)),
                        "sigma_lognormal": float(vals.get(pfx + "neel_sigma", 0.25)),
                        "log10_tau0": float(vals.get(pfx + "neel_log10_tau0", -9.0)),
                        "n_bins": int(round(float(vals.get(pfx + "neel_bins", 20.0)))),
                    }
                sharp_abs = component_absorption(self.file.velocity, comp_state.kind, params, extras=extras)
                sharp_abs_sum += sharp_abs
                components_for_plot.append((idx, f"Nítido {tr(f'kind.{comp_state.kind}', default=comp_state.kind)}", baseline_line - sharp_abs))
            if np.any(sharp_abs_sum > 0):
                dist_name = label if shape == "2D" else ("P(ΔEQ)" if var == "quad" else ("P(IS)" if var == "delta" else "P(BHF)"))
                components_for_plot.insert(0, (0, dist_name, result.fitted_curve + sharp_abs_sum))

        # Persistimos el mapa 2D para que sobreviva a los re-renders posteriores
        # (_finish_gui_fit_result vuelve a dibujar vía _render_fit_result).
        self._dist_map_2d = result if shape == "2D" else None
        if shape != "2D":
            _prev_fig = getattr(self, "_dist_map_2d_fig", None)
            if _prev_fig is not None:
                _prev_fig.clf()
            self._dist_map_2d_fig = None
        if hasattr(self, "dist_panel"):
            self.dist_panel.btn_show_map.setVisible(shape == "2D")
        style = get_style(self.plot_style_name)
        show_res = self.act_show_residual.isChecked() if hasattr(self, "act_show_residual") else True
        show_leg = self.act_show_legend.isChecked() if hasattr(self, "act_show_legend") else True
        self.canvas.render(self.file.velocity, self.file.y_data,
                           model=result.fitted_curve, components=components_for_plot,
                           style=style, show_residual=show_res, show_legend=show_leg,
                           style_name=self.plot_style_name,
                           dist_map_2d=self._dist_map_2d)

        if shape == "2D":
            alpha_q_log = d.log_alpha_q.value() if hasattr(d, "log_alpha_q") else -2.0
            msg = (f"{label}: bins={nbins}×{qbins}  "
                   f"αB=10^{dist_state.log_alpha:.2f} αQ=10^{alpha_q_log:.2f}  "
                   f"RMS={result.rms:.5g}")
        else:
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
        # El resultado 2D expone alpha_bhf/alpha_quad en vez de un único alpha.
        alpha_val = getattr(result, "alpha", None)
        if alpha_val is None:
            alpha_val = getattr(result, "alpha_bhf", 0.0)
        r.values = {"baseline": result.baseline, "slope": result.slope, "alpha": alpha_val}
        r.errors = {}
        r.correlations = {}
        r.n_starts = 1
        self.info_panel.show_result(r)
        if hasattr(self, "_record_fit_history"):
            self._record_fit_history("distribution", r.stats)
        self._show_distribution_dialog(result)

    def _show_distribution_dialog(self, result) -> None:
        from core.result_views import DistributionResultView
        view = DistributionResultView(result)
        if view.is_2d():
            self._show_distribution_dialog_2d(result, view)
        else:
            self._show_distribution_dialog_1d(result)

    def _show_distribution_dialog_1d(self, result) -> None:
        var = self.dist_variable
        title = "P(ΔEQ)" if var == "quad" else "P(BHF)"
        xlabel = (tr("plot.distribution_xlabel_deq") if var == "quad"
                  else tr("plot.distribution_xlabel_bhf"))
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(720, 480)
        lay = QtWidgets.QVBoxLayout(dlg)
        fig = Figure(figsize=(8.0, 4.5), dpi=96, constrained_layout=True)
        cv = FigureCanvas(fig); lay.addWidget(cv, stretch=1)
        ax = fig.add_subplot(111)
        xc = np.asarray(result.bhf_centers, dtype=float)
        pr = np.asarray(result.probability, dtype=float)
        ax.plot(xc, pr, "-", color="#2563eb", lw=2.0)
        ax.fill_between(xc, pr, 0, color="#93c5fd", alpha=0.45)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(title)
        ax.grid(True, alpha=0.3)
        cv.draw_idle()
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); lay.addWidget(bb)
        dlg.exec()

    def _show_distribution_dialog_2d(self, result, view) -> None:
        import numpy as np
        from matplotlib.gridspec import GridSpec
        xc, yc, P = view.probability_2d()
        xlbl, ylbl = view.var_labels_2d()
        mx, my = view.marginals_2d()
        xv = getattr(result, "x_variable", "bhf")
        yv = getattr(result, "y_variable", "quad")
        _short = {"bhf": "B_HF", "quad": "ΔEQ", "delta": "δ"}
        title_map = f"P({_short.get(xv, xv)}, {_short.get(yv, yv)})"

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title_map)
        dlg.resize(820, 700)
        lay = QtWidgets.QVBoxLayout(dlg)

        fig = Figure(figsize=(8.5, 7.0), dpi=96, constrained_layout=True)
        cv = FigureCanvas(fig); lay.addWidget(cv, stretch=1)

        # Disposición: fila superior = marginal x; columna derecha = marginal y;
        # celda principal = heatmap 2D.
        has_marginals = mx is not None and my is not None
        if has_marginals:
            gs = GridSpec(2, 2, figure=fig,
                          width_ratios=[4, 1], height_ratios=[1, 4],
                          hspace=0.06, wspace=0.06)
            ax_main  = fig.add_subplot(gs[1, 0])
            ax_top   = fig.add_subplot(gs[0, 0], sharex=ax_main)
            ax_right = fig.add_subplot(gs[1, 1], sharey=ax_main)
        else:
            gs = GridSpec(1, 1, figure=fig)
            ax_main = fig.add_subplot(gs[0, 0])
            ax_top = ax_right = None

        cmap = "viridis"
        im = ax_main.pcolormesh(xc, yc, P.T, cmap=cmap, shading="auto")
        if P.size >= 4:
            try:
                ax_main.contour(xc, yc, P.T, levels=5,
                                colors="white", linewidths=0.6, alpha=0.5)
            except Exception:
                pass
        fig.colorbar(im, ax=ax_main, fraction=0.046, pad=0.04, label="P(x, y)")
        ax_main.set_xlabel(xlbl, fontsize=10)
        ax_main.set_ylabel(ylbl, fontsize=10)
        ax_main.set_title(title_map, fontsize=11, fontweight="bold")
        ax_main.grid(False)

        if has_marginals and ax_top is not None and ax_right is not None:
            # Marginal X (superior)
            norm_x = float(mx.max()) or 1.0
            ax_top.fill_between(xc, mx / norm_x, 0, color="#3b82f6", alpha=0.55)
            ax_top.plot(xc, mx / norm_x, "-", color="#1d4ed8", lw=1.5)
            ax_top.set_ylabel("P(x)", fontsize=8)
            ax_top.tick_params(labelbottom=False, labelsize=7)
            ax_top.grid(True, alpha=0.25)
            ax_top.set_title("")
            # Marginal Y (derecha) — horizontal
            norm_y = float(my.max()) or 1.0
            ax_right.fill_betweenx(yc, my / norm_y, 0, color="#f59e0b", alpha=0.55)
            ax_right.plot(my / norm_y, yc, "-", color="#d97706", lw=1.5)
            ax_right.set_xlabel("P(y)", fontsize=8)
            ax_right.tick_params(labelleft=False, labelsize=7)
            ax_right.grid(True, alpha=0.25)

        # Estadísticas en texto
        lines = []
        for attr, fmt, name in (
            ("mean_bhf",  ".3f", f"⟨{_short.get(xv, xv)}⟩"),
            ("sigma_bhf", ".3f", f"σ({_short.get(xv, xv)})"),
            ("mean_quad", ".3f", f"⟨{_short.get(yv, yv)}⟩"),
            ("sigma_quad",".3f", f"σ({_short.get(yv, yv)})"),
            ("corr_bhf_quad", ".3f", "ρ(x,y)"),
        ):
            val = getattr(result, attr, None)
            if val is not None:
                lines.append(f"{name} = {val:{fmt}}")
        if lines:
            ax_main.annotate(
                "  ".join(lines),
                xy=(0.01, 0.01), xycoords="axes fraction",
                fontsize=7.5, color="white",
                bbox=dict(boxstyle="round,pad=0.25", fc="#00000080", ec="none"),
            )

        cv.draw_idle()

        # Persist for the PDF report
        self._dist_map_2d_fig = fig

        btn_row = QtWidgets.QHBoxLayout()
        btn_save = QtWidgets.QPushButton(tr("button.save_figure", default="Guardar figura…"))

        def _save_figure() -> None:
            stem = self.file.path.stem if self.file.path else "map2d"
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                dlg,
                tr("dialog.save_2d_figure", default="Guardar mapa 2D"),
                str(ROOT / f"{stem}_mapa2D.png"),
                "PNG (*.png);;SVG (*.svg);;PDF (*.pdf);;All (*.*)",
            )
            if path:
                try:
                    fig.savefig(path, dpi=150, bbox_inches="tight")
                except Exception as exc:
                    QtWidgets.QMessageBox.warning(
                        dlg,
                        tr("dialog.save_2d_figure", default="Guardar mapa 2D"),
                        f"{type(exc).__name__}: {exc}",
                    )

        btn_save.clicked.connect(_save_figure)
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        btn_row.addWidget(bb)
        lay.addLayout(btn_row)
        dlg.exec()

    def _on_reopen_map_dialog(self) -> None:
        result = getattr(self, "_dist_map_2d", None)
        if result is not None:
            self._show_distribution_dialog(result)
