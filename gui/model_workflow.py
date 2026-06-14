"""Flujo de modelo, datos, estado e información de la GUI Qt."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.constants import GLOBAL_PARAM_NAMES, SEXTET_PARAM_NAMES
from core.folding import (
    find_best_integer_or_half_center, fold_and_normalize, load_velocity_csv,
    read_ws5_counts, velocity_axis,
)
from core.fit_engine import FitState, resolve_values
from core.result_views import discrete_result_view
from core.reconstruction import (
    component_area_percentages as core_component_area_percentages,
    component_absorption_area,
    component_params_array,
    dense_velocity_grid,
    reconstruct_discrete_model,
)
from core.session import ModelState
from core.validation import format_validation_issues, validate_fit_state
from gui.controls import ParamControl
from gui.panels import ComponentPanel
from gui.fit_workflow import GuiFitRenderState
from gui.state import FileState, FitOptionsState, PlotViewState, UiActionState

ROOT = Path(__file__).resolve().parents[1]


class ModelWorkflowMixin:
    def _ui_action_state(self) -> UiActionState:
        """Snapshot ligero de acciones Qt usadas como estado runtime."""
        n_components = (
            int(self.n_components_spin.value())
            if hasattr(self, "n_components_spin") else 1
        )
        plot = PlotViewState(
            show_residual=(
                bool(self.act_show_residual.isChecked())
                if hasattr(self, "act_show_residual") else bool(getattr(self, "_show_residual_pref", True))
            ),
            show_legend=(
                bool(self.act_show_legend.isChecked())
                if hasattr(self, "act_show_legend") else True
            ),
        )
        return UiActionState(n_components=n_components, plot=plot)

    # ── Cambio de modo ───────────────────────────────────────────────────
    def _on_mode_changed(self, idx: int) -> None:
        is_dist = (idx in (1, 2, 3, 4, 5, 6))
        is_deq = (idx == 2)
        is_delta = (idx == 3)
        is_2d = (idx in (4, 5, 6))
        # El mapa topográfico 2D solo pertenece a un ajuste 2D vigente.
        if not is_2d:
            self._dist_map_2d = None
            _prev_fig = getattr(self, "_dist_map_2d_fig", None)
            if _prev_fig is not None:
                _prev_fig.clf()
            self._dist_map_2d_fig = None
            if hasattr(self, "dist_panel"):
                self.dist_panel.btn_show_map.setVisible(False)
        self._sync_component_count(self._ui_action_state().n_components)
        # La visibilidad de dist_panel/sextetes la fija _sync_component_count
        # según el modo y el contenedor (apilado o pestañas).
        # Sincroniza el radio del menú Ajuste → Modo de ajuste (los 7 modos).
        if hasattr(self, "_mode_menu_actions") and 0 <= idx < len(self._mode_menu_actions):
            self._mode_menu_actions[idx].setChecked(True)
        if is_dist:
            if is_2d:
                # Fuerza forma 2D y configura el par de variables
                if hasattr(self.dist_panel, "shape_combo"):
                    idx_shape = self.dist_panel.shape_combo.findData("2D")
                    if idx_shape >= 0 and self.dist_panel.shape_combo.currentIndex() != idx_shape:
                        self.dist_panel.shape_combo.setCurrentIndex(idx_shape)
                if hasattr(self.dist_panel, "set_distribution_pair"):
                    self.dist_panel.set_distribution_pair(*self.dist_pair)
            else:
                # Si veníamos de 2D, volver a Histograma
                if hasattr(self.dist_panel, "shape_combo") and getattr(self.dist_panel, "shape", "") == "2D":
                    idx_shape = self.dist_panel.shape_combo.findData("Histograma")
                    if idx_shape >= 0:
                        self.dist_panel.shape_combo.setCurrentIndex(idx_shape)
                var = "delta" if is_delta else ("quad" if is_deq else "bhf")
                self.dist_panel.set_distribution_variable(var)
        self._check_layout()
        self._refresh_plot()

    @property
    def is_distribution_mode(self) -> bool:
        return self.mode_combo.currentIndex() in (1, 2, 3, 4, 5, 6)

    @property
    def dist_variable(self) -> str:
        idx = self.mode_combo.currentIndex()
        if idx == 2:
            return "quad"
        if idx == 3:
            return "delta"
        return "bhf"

    @property
    def dist_pair(self) -> tuple[str, str]:
        """Par de variables para modos 2D (eje X, eje Y)."""
        idx = self.mode_combo.currentIndex()
        if idx == 5:
            return ("delta", "quad")   # P(IS, ΔEQ) 2D
        if idx == 6:
            return ("bhf", "delta")    # P(BHF, IS) 2D
        return ("bhf", "quad")         # P(BHF, ΔEQ) 2D (idx==4)

    def _on_model_param_changed(self, *args) -> None:
        if not self._building:
            self._simulate_enabled = True
        self._sync_absorber_model_from_panel()
        self._sync_constraint_targets()
        self._refresh_plot()

    def _sync_constraint_targets(self) -> None:
        """Actualiza los widgets dependientes cuando hay restricciones lineales activas.

        resolve_values() ya calcula los valores correctos para el plot; este método
        escribe esos valores de vuelta en los spinboxes de los parámetros objetivo.
        set_value() bloquea señales, por lo que no provoca reentrada.
        """
        state = self._build_state()
        if state is None or not state.constraints:
            return
        resolved = resolve_values(state.values, state.components, state.constraints, state.bounds)
        target_keys = {c["target"] for c in state.constraints if "target" in c}
        if not target_keys:
            return
        target_resolved = {k: v for k, v in resolved.items() if k in target_keys}
        self._building = True
        try:
            for cp in getattr(self, "components_panels", []):
                cp.apply_values(target_resolved)
            calib = getattr(self, "calib", None)
            if calib is not None:
                if "baseline" in target_keys and "baseline" in resolved:
                    calib.baseline.set_value(resolved["baseline"])
                if "slope" in target_keys and "slope" in resolved:
                    calib.slope.set_value(resolved["slope"])
        finally:
            self._building = False

    def _sync_absorber_model_from_panel(self, *args) -> None:
        if hasattr(self, "calib"):
            self.absorber_model = self.calib.to_view_state().absorber_model

    def _set_quick_action_buttons_enabled(self, enabled: bool) -> None:
        for name in ("btn_sim_fit", "btn_sim_auto_min", "btn_sim_ai"):
            btn = getattr(self, name, None)
            if btn is not None:
                btn.setEnabled(bool(enabled))

    def _active_bhf_controls(self) -> list[ParamControl]:
        """Controles BHF que participan en operaciones de escritura de la UI."""
        controls: list[ParamControl] = []
        for cp in getattr(self, "components_panels", []):
            comp_state = cp.to_view_state()
            if comp_state.enabled and comp_state.kind in ("Sextete", "Relajacion", "BlumeTjon", "NeelSize"):
                ctl = cp.params.get("bhf")  # widget necesario para fijarlo
                if ctl is not None:
                    controls.append(ctl)
        return controls

    def _active_bhf_fixed_flags(self) -> list[bool]:
        """Snapshot de los flags 'fixed' de BHF de sextetes activos."""
        flags: list[bool] = []
        for cp in getattr(self, "components_panels", []):
            comp_state = cp.to_view_state()
            if comp_state.enabled and comp_state.kind in ("Sextete", "Relajacion", "BlumeTjon", "NeelSize"):
                flags.append(comp_state.is_fixed("bhf"))
        return flags

    def _on_fit_velocity_toggled(self, checked: bool) -> None:
        """Al activar 'Ajustar Vmax', fija BHF y muestra el aviso de Tk."""
        if not checked:
            return
        for ctl in self._active_bhf_controls():
            ctl.set_fixed(True)
        QtWidgets.QMessageBox.information(
            self,
            tr("msg.fit_velocity_title"),
            tr("msg.fit_velocity_info"),
        )

    def _on_show_residual_toggled(self, checked: bool) -> None:
        """Reserva o libera el espacio de la diferencia y persiste la opción."""
        if hasattr(self, "canvas"):
            self.canvas.residual_pref = bool(checked)
            # Sin fichero cargado, _refresh_plot no redibuja: actualiza el
            # marcador de 'sin fichero' con la nueva disposición.
            if self.file.velocity is None:
                self.canvas.show_no_file()
        self._save_settings()

    # ── Helpers UI ───────────────────────────────────────────────────────
    def _set_all_fixed(self, value: bool) -> None:
        self._building = True
        for ctl in (self.calib.baseline, self.calib.slope, self.calib.sat_scale):
            ctl.set_fixed(value)
        for cp in self.components_panels:
            for name, ctl in cp.params.items():
                # int3 (intensidad de referencia = 1) permanece siempre fija,
                # igual que en Tk; no se libera con "Liberar todos".
                if name == "int3":
                    ctl.set_fixed(True)
                    continue
                ctl.set_fixed(value)
        self._building = False
        self._refresh_plot()

    def _fold_counts_for_center(self, center: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Dobla las cuentas con el mismo recorte de borde que el controlador headless."""
        if self.file.counts is None:
            raise ValueError("No hay cuentas cargadas")
        folded, sigma, y, _norm = fold_and_normalize(
            self.file.counts, center, int(getattr(self, "_edge_trim", 0)))
        return folded, sigma, y

    def _velocity_for_folded(self, n_points: int, trim_edges: bool = True) -> np.ndarray:
        """Crea el eje de velocidad y recorta sus extremos si se recortó el folding."""
        if self.file.counts is None:
            return np.array([], dtype=float)
        calib_state = self.calib.to_view_state()
        return velocity_axis(self.file.counts.size, calib_state.vmax,
                             n_points, int(getattr(self, "_edge_trim", 0)), trim_edges)

    def _refold_current_data(self, center: float) -> None:
        """Recalcula datos normalizados/sigma/eje cuando cambia el folding point."""
        if self.file.counts is None:
            return
        folded, sigma, y = self._fold_counts_for_center(center)
        self.file.folded = folded
        self.file.center = float(center)
        self.file.norm_factor = float(np.percentile(folded, 90)) if folded.size else 1.0
        self.file.norm_factor = self.file.norm_factor or 1.0
        self.file.sigma = sigma
        self.file.y_data = y
        self.file.velocity = self._velocity_for_folded(folded.size)

    def _on_center_value_changed(self, center: float) -> None:
        if self._building or self.file.counts is None:
            return
        self._refold_current_data(float(center))
        if self.file.path is not None:
            self.file_label.setText(f"<b>{self.file.path.name}</b><br>"
                                    f"{self.file.counts.size} canales · centro={float(center):.3f} · "
                                    f"norm={self.file.norm_factor:.4g}")
        self.statusBar().showMessage(tr("status.refolded", center=f"{float(center):.4f}", default=f"Refolded with center={float(center):.4f}"), 3000)
        self._refresh_plot()

    # ── Resumen de estado y parámetros (paridad con la GUI Tk) ───────────
    def _component_states(self):
        return [cp.to_view_state() for cp in self.components_panels]

    def _active_component_states(self):
        return [state for state in self._component_states() if state.enabled]

    def _active_components(self) -> list[ComponentPanel]:
        # Compatibilidad: algunas acciones aún necesitan modificar widgets.
        return [cp for cp in self.components_panels if cp.to_view_state().enabled]

    def active_param_keys(self) -> list[str]:
        keys = list(GLOBAL_PARAM_NAMES)
        if self.absorber_model == "thickness":
            keys.append("sat_scale")
        for comp_state in self._active_component_states():
            keys.extend(f"s{comp_state.idx}_{name}" for name in SEXTET_PARAM_NAMES)
            if comp_state.kind == "Sextete":
                keys.extend((f"s{comp_state.idx}_texture", f"s{comp_state.idx}_beta"))
        return keys

    def _fixed_param_keys(self) -> list[str]:
        fixed = []
        calib_state = self.calib.to_view_state()
        if calib_state.is_fixed("baseline"):
            fixed.append("baseline")
        if calib_state.is_fixed("slope"):
            fixed.append("slope")
        if calib_state.absorber_model == "thickness" and calib_state.is_fixed("sat_scale"):
            fixed.append("sat_scale")
        for comp_state in self._active_component_states():
            for name in SEXTET_PARAM_NAMES:
                if comp_state.is_fixed(name):
                    fixed.append(f"s{comp_state.idx}_{name}")
        return fixed

    def _component_params_array(self, cp: ComponentPanel, values: dict[str, float] | None = None) -> np.ndarray:
        comp_state = cp.to_view_state() if hasattr(cp, "to_view_state") else cp
        return component_params_array(comp_state, values)

    def component_area_from_params(self, kind: str, p: np.ndarray) -> float:
        return component_absorption_area(kind, p, self.file.velocity)

    def component_area_percentages(
        self, values: dict[str, float] | None = None
    ) -> tuple[list[int], np.ndarray, np.ndarray]:
        return core_component_area_percentages(
            self._active_component_states(),
            self.file.velocity,
            values,
        )

    def component_percentage_errors(self) -> dict[int, float]:
        result = self.runtime_results.fit_result
        if result is None or result.cov is None or not result.free_keys:
            return {}
        base_values = dict(result.values)
        active, _areas, _pct0 = self.component_area_percentages(base_values)
        if not active:
            return {}
        jac = np.zeros((len(active), len(result.free_keys)), dtype=float)
        for j, key in enumerate(result.free_keys):
            if key not in base_values:
                continue
            x = float(base_values[key])
            step = max(1e-6, abs(x) * 1e-5)
            vals_p = base_values.copy(); vals_m = base_values.copy()
            vals_p[key] = x + step
            vals_m[key] = x - step
            _a, _ar, pct_p = self.component_area_percentages(vals_p)
            _a, _ar, pct_m = self.component_area_percentages(vals_m)
            jac[:, j] = (pct_p - pct_m) / (2.0 * step)
        try:
            cov_pct = jac @ result.cov @ jac.T
        except Exception:
            return {}
        errs = np.sqrt(np.maximum(np.diag(cov_pct), 0.0))
        return {idx: float(err) for idx, err in zip(active, errs)}

    def calibration_iso_ref(self) -> float | None:
        info = self.calibration_info
        if not info:
            return None
        value = info.get("isomer_shift")
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def calibration_uncertainty_text(self) -> str | None:
        if not self.calibration_info:
            return None
        for key in ("velocity_uncertainty", "vmax_uncertainty", "velocity_error", "vmax_error", "sigma_vmax"):
            val = self.calibration_info.get(key)
            if val not in (None, ""):
                try:
                    return tr("info.calib_uncertainty", field=key, value=f"{float(val):.4g}")
                except (TypeError, ValueError):
                    return tr("info.calib_uncertainty_raw", field=key, value=val)
        return tr("info.calib_no_uncertainty")

    def enabled_constraints(self) -> list[dict]:
        keys = {"vmax", "center", "baseline", "slope", "voigt_sigma", "sat_scale"}
        for comp_state in self._component_states():
            keys.update(f"s{comp_state.idx}_{name}" for name in comp_state.values)
        return [
            c for c in self.constraints
            if c.get("enabled", True) and c.get("target") in keys and c.get("source") in keys
        ]

    def texture_derived(self, cp: "ComponentPanel") -> dict | None:
        """Magnitudes derivadas del parámetro de textura t = sin²θ.

        Acepta tanto un ``ComponentPanel`` como un ``ComponentViewState`` para
        facilitar la transición a snapshots sin depender de widgets.
        """
        comp_state = cp.to_view_state() if hasattr(cp, "to_view_state") else cp
        if comp_state.kind != "Sextete" or comp_state.intensity_mode != "texture":
            return None
        import math
        t = comp_state.value("texture", 0.0)
        tc = min(max(t, 0.0), 1.0)
        denom = max(2.0 - tc, 1e-9)
        theta_deg = math.degrees(math.asin(math.sqrt(tc)))
        r23 = 4.0 * tc / denom
        s_orient = 1.0 - 1.5 * tc
        sigma_t = None
        if self.runtime_results.fit_result is not None:
            sigma_t = discrete_result_view(self.runtime_results.fit_result).error_for(f"s{comp_state.idx}_texture")
        sigma_theta_deg = sigma_r23 = sigma_s = None
        if sigma_t is not None and sigma_t > 0:
            if 1e-6 < tc < 1.0 - 1e-6:
                sigma_theta_deg = math.degrees(
                    sigma_t / (2.0 * math.sqrt(tc * (1.0 - tc)))
                )
            sigma_r23 = 8.0 / (denom * denom) * sigma_t
            sigma_s = 1.5 * sigma_t
        return {
            "t": t, "theta_deg": theta_deg, "r23": r23, "s": s_orient,
            "sigma_t": sigma_t, "sigma_theta_deg": sigma_theta_deg,
            "sigma_r23": sigma_r23, "sigma_s": sigma_s,
        }

    def _info_rms(self) -> float:
        if self.file.velocity is None or self.file.y_data is None or not self._simulate_enabled:
            return float("nan")
        state = self._build_state()
        if state is None:
            return float("nan")
        try:
            reconstruction = reconstruct_discrete_model(
                state.velocity,
                self.file.y_data,
                state.values,
                state.components,
                state.constraints,
                absorber_model=state.absorber_model,
            )
        except Exception:
            return float("nan")
        return float(np.sqrt(np.mean(reconstruction.residual ** 2)))

    def _update_info_panel(self) -> None:
        if not hasattr(self, "info_panel"):
            return
        if self.file.counts is None or self.file.folded is None:
            self.info_panel.set_lines([])
            return
        active = [comp_state.idx for comp_state in self._active_component_states()]
        fixed = self._fixed_param_keys()
        pct_active, areas, percentages = self.component_area_percentages()
        pct_errors = self.component_percentage_errors()
        calib_state = self.calib.to_view_state()
        center = float(calib_state.center)
        lines = [
            tr("info.file", name=self.file.path.name if self.file.path else "-"),
            tr("info.channels_read", n=self.file.counts.size),
            tr("info.folding_center", center=f"{center:.5f}"),
            tr("info.folding_normos", value=f"{2.0 * center:.5f}"),
            tr("info.folded_pairs", n=int(self.file.folded.size)),
            tr("info.normalization", factor=f"{self.file.norm_factor:.6g}"),
            tr("info.vmax", value=f"{calib_state.vmax:.6g}"),
            tr("info.baseline", value=f"{calib_state.baseline:.6g}"),
            tr("info.slope", value=f"{calib_state.slope:.6g}"),
            tr("info.active_sextets", list=", ".join(map(str, active))),
            tr("info.fit_velocity_yes") if calib_state.fit_velocity else tr("info.fit_velocity_no"),
            tr("info.rms", value=f"{self._info_rms():.6g}"),
        ]
        result = self.runtime_results.fit_result
        result_view = discrete_result_view(result) if result is not None else None
        stats = ({metric.key: metric.value for metric in result_view.metrics()} if result_view is not None else {})
        if stats:
            lines.extend([
                tr("info.chi2_line", red_chi2=f"{stats.get('red_chi2', float('nan')):.6g}",
                   chi2=f"{stats.get('chi2', float('nan')):.6g}", dof=f"{stats.get('dof', float('nan')):.0f}"),
                tr("info.aic_bic_line", aic=f"{stats.get('aic', float('nan')):.6g}",
                   bic=f"{stats.get('bic', float('nan')):.6g}", n_params=f"{stats.get('n_params', len(result.free_keys)):.0f}"),
                tr("info.residual_diag", lag1=f"{stats.get('resid_lag1', float('nan')):.3f}",
                   z=f"{stats.get('resid_runs_z', float('nan')):.3f}",
                   antisym=f"{stats.get('resid_antisym_corr', float('nan')):.3f}"),
                tr("info.model_comparison"),
                tr("info.multistart_count", n=f"{result.n_starts:.0f}"),
            ])
            if (abs(stats.get("resid_lag1", 0.0)) > 0.35
                    or abs(stats.get("resid_runs_z", 0.0)) > 2.0
                    or stats.get("resid_antisym_corr", 0.0) > 0.45):
                lines.extend([tr("info.residual_warning_1"), tr("info.residual_warning_2")])
        cal_unc = self.calibration_uncertainty_text()
        if cal_unc:
            lines.append(cal_unc)
        corr = result.correlations if result is not None else {}
        if corr:
            max_pair = corr.get("max_pair") or []
            if max_pair:
                lines.append(tr("info.max_correlation", value=f"{float(corr.get('max_abs_corr', 0.0)):.3f}",
                               p1=max_pair[0], p2=max_pair[1]))
            high_pairs = corr.get("high_pairs") or []
            if high_pairs:
                lines.append(tr("info.correlation_warning"))
                for pair in high_pairs[:6]:
                    lines.append(f"  {pair['param1']} ↔ {pair['param2']}: r={float(pair['corr']):.3f}")
                if len(high_pairs) > 6:
                    lines.append(tr("info.correlation_more", n=len(high_pairs) - 6))
        lines.append("")
        if len(pct_active) > 1:
            lines.append(tr("info.area_percent_header"))
            for idx, area, pct in zip(pct_active, areas, percentages):
                err = pct_errors.get(idx)
                err_txt = f" ± {err:.3g}%" if err is not None else ""
                comp_state = self.components_panels[idx - 1].to_view_state()
                kind_disp = tr(f"kind.{comp_state.kind}", default=comp_state.kind)
                lines.append(tr("info.component_percent_line", idx=idx, kind=kind_disp,
                               pct=pct, err_txt=err_txt, area=area))
            lines.append("")
        iso_ref = self.calibration_iso_ref()
        for comp_state in self._active_component_states():
            i3_real = comp_state.value("int3", 1.0)
            i2_real = i3_real * comp_state.value("int2", 1.0)
            i1_real = i3_real * comp_state.value("int1", 1.0)
            g1 = comp_state.value("gamma1")
            g2 = g1 * comp_state.value("gamma2", 1.0)
            g3 = g1 * comp_state.value("gamma3", 1.0)
            kind_disp = tr(f"kind.{comp_state.kind}", default=comp_state.kind)
            lines.extend([
                tr("info.component_params_line", kind=kind_disp, idx=comp_state.idx,
                   bhf=comp_state.value("bhf"), delta=comp_state.value("delta"), quad=comp_state.value("quad")),
                tr("info.gamma_hwhm", g1=g1, g2=g2, g3=g3),
                tr("info.gamma_rel", gamma2=comp_state.value("gamma2", 1.0), gamma3=comp_state.value("gamma3", 1.0)),
                tr("info.depth_intensities", depth=comp_state.value("depth"), i1=i1_real, i2=i2_real, i3=i3_real),
            ])
            derived = self.texture_derived(comp_state)
            if derived is not None:
                def _fmt_err(v: float | None) -> str:
                    return f" ± {v:.3g}" if v is not None and v > 0 else ""
                lines.append(tr(
                    "info.texture_derived",
                    t=f"{derived['t']:.4g}",
                    theta=f"{derived['theta_deg']:.4g}",
                    theta_err=_fmt_err(derived["sigma_theta_deg"]),
                    r23=f"{derived['r23']:.4g}",
                    r23_err=_fmt_err(derived["sigma_r23"]),
                    s=f"{derived['s']:.4g}",
                    s_err=_fmt_err(derived["sigma_s"]),
                ))
            if iso_ref is not None:
                lines.append(tr("info.delta_corrected",
                               value=f"{comp_state.value('delta') - iso_ref:.6g}", ref=f"{iso_ref:.6g}"))
        lines.extend(["", tr("info.fixed_line", fixed=", ".join(fixed) if fixed else tr("info.none"))])
        cons = self.enabled_constraints()
        if cons:
            lines.append("")
            lines.append(tr("info.constraints_header"))
            for c in cons:
                lines.append(tr("info.constraint_line", target=c["target"], factor=float(c.get("factor", 1.0)),
                               source=c["source"], offset=float(c.get("offset", 0.0))))
        self.info_panel.set_lines(lines)

    # ── Construcción del FitState a partir de la UI ───────────────────────
    def _fit_options_state(self) -> FitOptionsState:
        """Snapshot formal de opciones globales de ajuste leídas de la GUI."""
        calib_state = self.calib.to_view_state()
        return FitOptionsState(
            line_profile=calib_state.line_profile,
            likelihood=self.likelihood,
            robust_loss=self.robust_loss,
            absorber_model=calib_state.absorber_model,
            propagate_calib=self.propagate_calib,
            global_opt=self.global_opt,
            fit_velocity=calib_state.fit_velocity,
            fit_center=calib_state.fit_center,
            fit_sigma=calib_state.fit_sigma,
            multistart_n=getattr(self, "multistart_n", 8),
        )

    def _model_state(self) -> ModelState:
        """Vuelca el estado de los widgets en un ``core.session.ModelState``.

        Fuente única del estado del modelo: a partir de aquí, la construcción del
        ``FitState`` y el ``model_state`` de la sesión se delegan en el
        controlador headless (``core.session``), sin lógica duplicada en la GUI.
        """
        ms = ModelState.defaults(n_components=max(1, len(self.components_panels)))
        calib_state = self.calib.to_view_state()
        ms.vars.update(calib_state.values_dict())
        ms.fixed.update({
            "vmax": True, "center": True,
            "baseline": calib_state.is_fixed("baseline"),
            "slope": calib_state.is_fixed("slope"),
            "sat_scale": calib_state.is_fixed("sat_scale"),
        })
        for cp in self.components_panels:
            comp_state = cp.to_view_state()
            ms.vars.update(comp_state.prefixed_values())
            ms.fixed.update(comp_state.prefixed_fixed())
            ms.sextet_enabled[comp_state.idx] = comp_state.enabled
            ms.component_kind[comp_state.idx] = comp_state.kind
            ms.intensity_mode[comp_state.idx] = comp_state.intensity_mode
            ms.quad_treatment[comp_state.idx] = comp_state.quad_treatment
        self._fit_options_state().apply_to_model_state(ms)
        ms.constraints = list(self.constraints)
        return ms

    def _build_state(self, *, validate_params: bool = False) -> FitState | None:
        if self.file.velocity is None or self.file.y_data is None:
            return None
        state = self._model_state().build_fit_state(
            velocity=self.file.velocity, y_data=self.file.y_data,
            sigma_data=self.file.sigma, counts=self.file.counts,
            norm_factor=self.file.norm_factor)
        if validate_params:
            issues = validate_fit_state(state)
            if issues:
                QtWidgets.QMessageBox.warning(
                    self,
                    tr("msg.validation_title", default="Parámetros no válidos"),
                    format_validation_issues(issues),
                )
                return None
        return state

    # ── Acciones ─────────────────────────────────────────────────────────
    # Extensiones reconocidas como espectros ya doblados en espacio de velocidad.
    _CSV_EXTENSIONS = frozenset({".csv", ".txt", ".dat", ".exp"})

    def on_open(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, tr("file.open"), str(ROOT),
            "Espectros Mössbauer (*.ws5 *.adt *.WS5 *.ADT *.csv *.txt *.dat *.exp);;"
            "WS5/ADT (*.ws5 *.adt *.WS5 *.ADT);;"
            "Velocidad CSV (*.csv *.txt *.dat *.exp);;"
            "All (*.*)")
        if not path:
            return
        p = Path(path)
        try:
            if p.suffix.lower() in self._CSV_EXTENSIONS:
                self._load_velocity_csv_file(p)
            else:
                self._load_file(p)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("file.open"),
                                           f"{type(exc).__name__}: {exc}")

    def _load_file(self, path: Path) -> None:
        counts = read_ws5_counts(path)
        center = find_best_integer_or_half_center(counts)
        self.file = FileState(path=path, counts=counts, center=center)
        self._simulate_enabled = False
        self._dist_map_2d = None
        _prev_fig = getattr(self, "_dist_map_2d_fig", None)
        if _prev_fig is not None:
            _prev_fig.clf()
        self._dist_map_2d_fig = None
        if hasattr(self, "dist_panel"):
            self.dist_panel.btn_show_map.setVisible(False)
        folded, sigma, y = self._fold_counts_for_center(center)
        norm = float(np.percentile(folded, 90)) if folded.size else 1.0
        norm = norm or 1.0
        v = self._velocity_for_folded(folded.size)
        self.file.folded = folded
        self.file.sigma = sigma
        self.file.norm_factor = norm
        self.file.velocity = v
        self.file.y_data = y
        # actualiza UI
        self.calib.center.set_value(center)
        self.file_label.setText(f"<b>{path.name}</b><br>"
                                f"{counts.size} canales · centro={center:.3f} · "
                                f"norm={norm:.4g}")
        self.act_fit.setEnabled(True)
        self.act_init.setEnabled(True)
        if hasattr(self, 'act_identify_phases'):
            self.act_identify_phases.setEnabled(
                getattr(self, 'phase_predict_enabled', False))
        self.act_edit_minima.setEnabled(True)
        self.act_auto_fit.setEnabled(True)
        self.act_ai.setEnabled(True)
        self.act_upload_session.setEnabled(True)
        self.act_use_as_calib.setEnabled(True)
        self.act_profile.setEnabled(True)
        self.act_find_center.setEnabled(True)
        self.act_save_fit.setEnabled(True)
        self.act_export_report.setEnabled(True)
        self.act_export_short_report.setEnabled(True)
        self.act_export_plotly.setEnabled(True)
        self.act_open_plotly.setEnabled(True)
        self.act_bootstrap.setEnabled(True)
        self.act_lcurve.setEnabled(True)
        self._set_quick_action_buttons_enabled(True)
        self._add_recent(path)
        self.statusBar().showMessage(
            f"{path.name} · {counts.size} canales · centro={center:.3f}")
        self.runtime_results.clear()
        self._refresh_plot()

    def _load_velocity_csv_file(self, path: Path) -> None:
        """Carga un espectro ya doblado en espacio de velocidad (CSV/TXT/DAT/EXP).

        A diferencia de ``_load_file``, no realiza folding: el eje de velocidad
        y los valores de cuentas provienen directamente del fichero.  El estado
        ``FileState`` se rellena con ``counts=None`` para señalar que no hay
        cuentas en bruto disponibles (operaciones como «Detectar centro» quedan
        deshabilitadas).
        """
        data = load_velocity_csv(path)
        vel: np.ndarray = data["velocity"]
        y_raw: np.ndarray = data["y"]

        # Normalizar a línea base ~1.
        norm = float(np.percentile(y_raw, 90)) if y_raw.size else 1.0
        norm = norm or 1.0
        y = y_raw / norm

        # Ruido Poisson proporcional (sin cuentas en bruto, usar y_raw como proxy).
        sigma = np.sqrt(np.maximum(y_raw / 2.0, 1.0)) / norm

        # Vmax aproximado a partir del eje de velocidad.
        vmax = float(np.max(np.abs(vel))) if vel.size else 12.0

        self.file = FileState(
            path=path,
            counts=None,       # sin cuentas en bruto
            folded=y_raw,      # las cuentas CSV hacen las veces de «folded»
            sigma=sigma,
            norm_factor=norm,
            center=None,
            velocity=vel,
            y_data=y,
        )
        self._simulate_enabled = False
        self._dist_map_2d = None
        _prev_fig = getattr(self, "_dist_map_2d_fig", None)
        if _prev_fig is not None:
            _prev_fig.clf()
        self._dist_map_2d_fig = None
        if hasattr(self, "dist_panel"):
            self.dist_panel.btn_show_map.setVisible(False)

        # Actualizar controles de calibración con el Vmax detectado.
        self._building = True
        try:
            if hasattr(self, "calib") and hasattr(self.calib, "vmax"):
                self.calib.vmax.set_value(vmax)
        finally:
            self._building = False

        n_pts = int(vel.size)
        self.file_label.setText(
            f"<b>{path.name}</b><br>"
            f"{n_pts} puntos · velocidad CSV · norm={norm:.4g}"
        )
        # Habilitar acciones compatibles con espectros sin cuentas en bruto.
        self.act_fit.setEnabled(True)
        self.act_init.setEnabled(True)
        if hasattr(self, 'act_identify_phases'):
            self.act_identify_phases.setEnabled(
                getattr(self, 'phase_predict_enabled', False))
        self.act_edit_minima.setEnabled(True)
        self.act_auto_fit.setEnabled(True)
        self.act_ai.setEnabled(True)
        self.act_upload_session.setEnabled(True)
        self.act_profile.setEnabled(True)
        self.act_save_fit.setEnabled(True)
        self.act_export_report.setEnabled(True)
        self.act_export_short_report.setEnabled(True)
        self.act_export_plotly.setEnabled(True)
        self.act_open_plotly.setEnabled(True)
        self.act_bootstrap.setEnabled(True)
        self.act_lcurve.setEnabled(True)
        self._set_quick_action_buttons_enabled(True)
        # Acciones que requieren cuentas en bruto quedan deshabilitadas.
        self.act_find_center.setEnabled(False)
        self.act_use_as_calib.setEnabled(False)
        self._add_recent(path)
        self.statusBar().showMessage(
            f"{path.name} · {n_pts} puntos · CSV velocidad · vmax≈{vmax:.3g} mm/s"
        )
        self.runtime_results.clear()
        self._refresh_plot()

    def _refresh_plot(self) -> None:
        if self._building or self.file.velocity is None:
            return
        v = self.file.velocity
        y = self.file.y_data
        # Recalcular velocidad si vmax cambia, respetando el recorte de bordes.
        expected_v = self._velocity_for_folded(y.size)
        if v.size and expected_v.size == v.size and not np.allclose(v, expected_v, atol=1e-9, rtol=0.0):
            v = expected_v
            self.file.velocity = v
        state = self._build_state()
        if state is None or not self._simulate_enabled:
            self._render_fit_result(GuiFitRenderState(velocity=v, y_data=y))
            self._update_info_panel()
            self._schedule_plotly_update()
            return
        try:
            reconstruction = reconstruct_discrete_model(
                v,
                y,
                state.values,
                state.components,
                state.constraints,
                absorber_model=state.absorber_model,
            )
        except Exception:
            self._render_fit_result(GuiFitRenderState(velocity=v, y_data=y))
            self._update_info_panel()
            self._schedule_plotly_update()
            return
        self._render_fit_result(GuiFitRenderState(
            velocity=v,
            y_data=y,
            model=reconstruction.model_dense,
            components=[(curve.idx, curve.kind, curve.y) for curve in reconstruction.components],
            residual=reconstruction.residual,
            model_v=reconstruction.model_v,
        ))
        self._update_info_panel()
        self._schedule_plotly_update()

    def _render_intermediate_fit(self, state: FitState, free_keys: list[str], free_values: list[float]) -> None:
        """Renderiza el modelo con los parámetros intermedios del optimizador.

        Se llama desde el progress_cb durante el ajuste discreto; no toca widgets
        ni emite señales. El render se limita a superponer el modelo total sobre
        los datos experimentales.
        """
        v = self.file.velocity
        y = self.file.y_data
        if v is None or y is None:
            return
        merged = dict(state.values)
        merged.update(zip(free_keys, free_values))
        try:
            reconstruction = reconstruct_discrete_model(
                v, y, merged, state.components, state.constraints,
                absorber_model=state.absorber_model,
            )
        except Exception:
            return
        from gui.fit_workflow import GuiFitRenderState
        self._render_fit_result(GuiFitRenderState(
            velocity=v,
            y_data=y,
            model=reconstruction.model_dense,
            components=[(c.idx, c.kind, c.y) for c in reconstruction.components],
            residual=reconstruction.residual,
            model_v=reconstruction.model_v,
        ))

    def _model_grid(self, v: np.ndarray) -> np.ndarray | None:
        """Compatibilidad: delega la rejilla densa en ``core.reconstruction``."""
        return dense_velocity_grid(v)

