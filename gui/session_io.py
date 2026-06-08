"""Guardado y carga de sesiones de la GUI Qt."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.folding import find_best_integer_or_half_center
from gui.state import (
    CalibrationState,
    DistributionViewState,
    FileState,
    FitOptionsState,
    ProjectState,
    SpectrumState,
)

ROOT = Path(__file__).resolve().parents[1]


class SessionIOMixin:
    # ── Save / Load session (formato compatible con la GUI Tk) ──────────
    def _project_state(self) -> ProjectState:
        """Snapshot formal del estado serializable de la GUI.

        Mantiene el payload histórico, pero centraliza la frontera widgets →
        estado. Las fases siguientes deberían ampliar este objeto en vez de
        añadir más lecturas directas de widgets en ``_session_payload``.
        """
        model_state = self._model_state().to_model_state_dict()
        model_state.pop("fit_mode", None)  # lo gestiona la GUI (discreto/distrib.)
        ui_state = self._ui_action_state()
        model_state["n_components"] = ui_state.n_components
        distribution = (
            self.dist_panel.to_view_state(variable=self.dist_variable)
            if hasattr(self, "dist_panel") else DistributionViewState()
        )
        plot = ui_state.plot
        return ProjectState(
            spectrum=SpectrumState.from_file_state(self.file),
            calibration=CalibrationState(self.calibration_info),
            model_state=model_state,
            fit_options=self._fit_options_state(),
            distribution=distribution,
            plot=plot,
        )

    def _session_payload(self) -> dict:
        """Estado completo del Qt en el mismo formato que la GUI Tk."""
        return self._project_state().to_session_payload()

    def _apply_session_payload(self, data: dict) -> None:
        project = ProjectState.from_session_payload(data)
        spectrum = project.spectrum
        # 1. Datos: si trae un file_path existente o counts embebidos, los carga.
        if spectrum.path and spectrum.path.exists():
            try:
                self._load_file(spectrum.path)
            except Exception:
                pass
        elif spectrum.counts is not None:
            self.file = FileState(
                path=spectrum.path,
                counts=np.array(spectrum.counts, dtype=float),
            )
            counts = self.file.counts
            center = find_best_integer_or_half_center(counts)
            self.file.center = center
            folded, sigma, y = self._fold_counts_for_center(center)
            norm = float(np.percentile(folded, 90)) if folded.size else 1.0
            norm = norm or 1.0
            self.file.folded = folded
            self.file.norm_factor = norm
            self.file.sigma = sigma
            self.file.y_data = y
            self.file.velocity = self._velocity_for_folded(folded.size)
            self.file_label.setText(
                f"<b>{spectrum.file_name or '—'}</b><br>"
                f"{counts.size} canales (sesión)")
            self.act_fit.setEnabled(True)
            self._set_quick_action_buttons_enabled(True)

        # 2. Calibración guardada
        calib = project.calibration.info
        if isinstance(calib, dict):
            self.calibration_info = dict(calib)
            self._refresh_calib_label()

        # 3. Modelo: aplicar vars / fixed / sextet_enabled / component_kind.
        state = project.model_state
        self._building = True
        try:
            vmap = state.get("vars", {})
            calib_state = self.calib.to_view_state()
            self.calib.vmax.set_value(vmap.get("vmax", calib_state.vmax))
            self.calib.center.set_value(vmap.get("center", calib_state.center))
            self.calib.baseline.set_value(vmap.get("baseline", calib_state.baseline))
            self.calib.slope.set_value(vmap.get("slope", calib_state.slope))
            self.calib.voigt_sigma.set_value(vmap.get("voigt_sigma", calib_state.voigt_sigma))
            self.calib.sat_scale.set_value(vmap.get("sat_scale", calib_state.sat_scale))
            n_saved = state.get("n_components")
            if n_saved is None:
                enabled_map = state.get("sextet_enabled", {})
                enabled_idx = [int(k) for k, v in enabled_map.items()
                               if str(k).isdigit() and bool(v)]
                n_saved = max(enabled_idx, default=1)
            self._sync_component_count(int(n_saved))
            for cp in self.components_panels:
                cp.apply_values(vmap)
                ki = state.get("component_kind", {}).get(str(cp.idx))
                if ki in ("Sextete", "Doblete", "Singlete"):
                    cp.type_combo.setCurrentText(ki)
                en = state.get("sextet_enabled", {}).get(str(cp.idx))
                if en is not None:
                    cp.enabled.setChecked(bool(en))
                im = state.get("intensity_mode", {}).get(str(cp.idx))
                if im in ("free", "texture"):
                    cp.intensity_mode = im
                qt_v = state.get("quad_treatment", {}).get(str(cp.idx))
                if qt_v in ("1st_order", "kundig_fixed", "kundig_powder"):
                    cp.quad_treatment = qt_v
                for name, ctl in cp.params.items():
                    f = state.get("fixed", {}).get(f"s{cp.idx}_{name}")
                    if f is not None:
                        ctl.set_fixed(bool(f))
            self.calib.fit_velocity.setChecked(bool(state.get("fit_velocity", False)))
            self.calib.fit_center.setChecked(bool(state.get("fit_center", False)))
            self.calib.fit_sigma.setChecked(bool(state.get("fit_sigma", False)))
            lp = state.get("line_profile")
            if lp in ("Lorentziana", "Voigt"):
                self.calib._set_line_profile(lp)
            if "show_residual" in state and hasattr(self, "act_show_residual"):
                self.act_show_residual.setChecked(bool(state["show_residual"]))
            if "show_legend" in state and hasattr(self, "act_show_legend"):
                self.act_show_legend.setChecked(bool(state["show_legend"]))
            # Opciones avanzadas
            lk = state.get("likelihood")
            if lk in ("gauss", "poisson"):
                self.likelihood = lk
            rl = state.get("robust_loss")
            if rl in ("linear", "soft_l1", "huber"):
                self.robust_loss = rl
            if "propagate_calib" in state:
                self.propagate_calib = bool(state["propagate_calib"])
            if "global_opt" in state:
                self.global_opt = bool(state["global_opt"])
            am = state.get("absorber_model")
            if am in ("thin", "thickness"):
                self.absorber_model = am
                self.calib.set_absorber_model(am)
            if "dist_use_sharp" in state:
                self.dist_use_sharp = bool(state["dist_use_sharp"])
            if "dist_refine_global" in state:
                self.dist_refine_global = bool(state["dist_refine_global"])
            if "constraints" in state:
                self.constraints = list(state.get("constraints") or [])
            shape_saved = state.get("dist_shape")
            reg_saved = state.get("dist_reg_mode")
            if reg_saved in ("tikhonov", "tv") and hasattr(self, "dist_panel"):
                self.dist_panel.reg_mode_combo.setCurrentText(reg_saved)
            fixed_path = state.get("fixed_distribution_path")
            if fixed_path and hasattr(self, "dist_panel"):
                self.dist_panel.fixed_path = Path(fixed_path)
            if shape_saved in ("Histograma", "Gaussiana", "Binomial", "Fija") and hasattr(self, "dist_panel"):
                idx_shape = self.dist_panel.shape_combo.findData(shape_saved)
                if idx_shape >= 0:
                    self.dist_panel.shape_combo.setCurrentIndex(idx_shape)
            var_saved = state.get("dist_variable")
            if var_saved in ("BHF", "bhf"):
                self.mode_combo.setCurrentIndex(1)
            elif var_saved in ("ΔEQ", "quad"):
                self.mode_combo.setCurrentIndex(2)
            # Sincroniza las acciones del menú avanzado si ya existen
            for grp_attr, val, items in (
                ("likelihood_action_group", self.likelihood, ("gauss", "poisson")),
                ("loss_action_group", self.robust_loss, ("linear", "soft_l1", "huber")),
                ("absorber_action_group", self.absorber_model, ("thin", "thickness")),
            ):
                grp = getattr(self, grp_attr, None)
                if grp is None:
                    continue
                actions = grp.actions()
                for idx_, key_ in enumerate(items):
                    if key_ == val and idx_ < len(actions):
                        actions[idx_].setChecked(True)
            for attr, value in (
                ("act_propagate", self.propagate_calib),
                ("act_global_opt", self.global_opt),
                ("act_add_sharp", self.dist_use_sharp),
                ("act_refine_global", self.dist_refine_global),
            ):
                a = getattr(self, attr, None)
                if a is not None:
                    a.setChecked(bool(value))
            if hasattr(self, "dist_panel"):
                self.dist_panel.use_sharp.setChecked(bool(self.dist_use_sharp))
                self.dist_panel.refine_global.setChecked(bool(self.dist_refine_global))
        finally:
            self._building = False
        self._simulate_enabled = True
        self._refresh_plot()

    def on_save_session(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("file.save_session"), str(ROOT),
            "JSON (*.json);;All (*.*)")
        if not path:
            return
        import json
        try:
            data = self._session_payload()
            Path(path).write_text(
                json.dumps(data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8")
            self.statusBar().showMessage(f"Sesión guardada: {path}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("file.save_session"),
                f"{type(exc).__name__}: {exc}")

    def on_load_session(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, tr("file.load_session"), str(ROOT),
            "JSON (*.json);;All (*.*)")
        if not path:
            return
        import json
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("file.load_session"),
                f"{type(exc).__name__}: {exc}")
            return
        try:
            self._apply_session_payload(data)
            self.statusBar().showMessage(f"Sesión cargada: {path}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("file.load_session"),
                f"{type(exc).__name__}: {exc}")
