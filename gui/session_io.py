"""Guardado y carga de sesiones de la GUI Qt."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.folding import find_best_integer_or_half_center
from core.params import COMPONENT_KINDS, DISTRIBUTION_SHAPES, INTENSITY_MODES, QUAD_TREATMENTS
from gui.state import (
    CalibrationState,
    DistributionViewState,
    FileState,
    FitOptionsState,
    ProjectState,
    SpectrumState,
)

ROOT = Path(__file__).resolve().parents[1]


def _per_component_map(value) -> dict:
    """Normaliza mapas por componente del payload a dict {"1": v, ...}.

    Las sesiones antiguas guardaban ``sextet_enabled``/``component_kind``/
    ``intensity_mode`` como LISTAS ([v1, v2, v3], índice 0 = componente 1);
    tratarlas como dict rompía la carga con AttributeError.
    """
    if isinstance(value, (list, tuple)):
        return {str(i + 1): v for i, v in enumerate(value)}
    return dict(value) if isinstance(value, dict) else {}


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
        if hasattr(self, "mode_combo"):
            model_state["mode_combo_idx"] = self.mode_combo.currentIndex()
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

    def _undo_fit(self) -> None:
        snapshot = getattr(self, "_pre_fit_snapshot", None)
        if snapshot is None:
            return
        # Un ajuste no cambia el modo (discreto/distribución), así que
        # preservamos el modo activo: _apply_session_payload lo reconstruye a
        # partir de dist_variable (siempre "BHF" por defecto) y, sin este
        # guardado, deshacer un ajuste discreto saltaría a P(BHF).
        mode_idx = (
            self.mode_combo.currentIndex()
            if hasattr(self, "mode_combo") else None
        )
        self._apply_session_payload(snapshot)
        if mode_idx is not None and hasattr(self, "mode_combo"):
            self.mode_combo.setCurrentIndex(mode_idx)
        self._pre_fit_snapshot = None
        if hasattr(self, "act_undo_fit"):
            self.act_undo_fit.setEnabled(False)
        self._refresh_plot()

    def _apply_session_payload(self, data: dict) -> None:
        project = ProjectState.from_session_payload(data)
        spectrum = project.spectrum
        # 1. Datos: si trae un file_path existente o counts embebidos, los carga.
        if spectrum.path and spectrum.path.exists():
            try:
                # Misma bifurcación que on_open: un CSV de velocidad NO pasa por
                # el lector WS5+folding (leería las dos columnas como cuentas
                # intercaladas y auto-doblaría ruido sin avisar).
                if spectrum.path.suffix.lower() in self._CSV_EXTENSIONS:
                    self._load_velocity_csv_file(spectrum.path)
                else:
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
            # Igual que _load_file: los resultados runtime (y el mapa 2D) del
            # estado anterior no pertenecen a la sesión restaurada.
            self.runtime_results.clear()
            self._dist_map_2d = None
            _prev_fig = getattr(self, "_dist_map_2d_fig", None)
            if _prev_fig is not None:
                _prev_fig.clf()
            self._dist_map_2d_fig = None
            if hasattr(self, "dist_panel"):
                self.dist_panel.btn_show_map.setVisible(False)

        # 2. Calibración guardada
        calib = project.calibration.info
        if isinstance(calib, dict):
            self.calibration_info = dict(calib)
            self._refresh_calib_label()
        else:
            # Sesión sin calibración: no heredar la de la GUI actual (afectaría
            # al δ corregido y a la incertidumbre de vmax en panel e informes).
            self.calibration_info = None
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
            enabled_map = _per_component_map(state.get("sextet_enabled", {}))
            kind_map = _per_component_map(state.get("component_kind", {}))
            imode_map = _per_component_map(state.get("intensity_mode", {}))
            qtreat_map = _per_component_map(state.get("quad_treatment", {}))
            n_saved = state.get("n_components")
            if n_saved is None:
                enabled_idx = [int(k) for k, v in enabled_map.items()
                               if str(k).isdigit() and bool(v)]
                n_saved = max(enabled_idx, default=1)
            self._sync_component_count(int(n_saved))
            # Restaurar el modo ANTES de las casillas «activo» y de los valores
            # del panel de distribución: _on_mode_changed re-sincroniza el nº de
            # componentes (pisaría el patrón enabled restaurado) y configura los
            # rangos de la variable de distribución (con los rangos de la
            # variable anterior, set_value recortaba los valores guardados).
            mode_idx_saved = state.get("mode_combo_idx")
            if mode_idx_saved is not None:
                # Índice guardado explícitamente: cubre el modo discreto (0) y 2D (4/5/6)
                self.mode_combo.setCurrentIndex(int(mode_idx_saved))
            else:
                # Compatibilidad con sesiones antiguas sin mode_combo_idx
                var_saved = state.get("dist_variable")
                _2d_var_to_idx = {"BHF-ΔEQ": 4, "IS-ΔEQ": 5, "BHF-IS": 6}
                if var_saved in _2d_var_to_idx:
                    self.mode_combo.setCurrentIndex(_2d_var_to_idx[var_saved])
                elif var_saved in ("BHF", "bhf"):
                    self.mode_combo.setCurrentIndex(1)
                elif var_saved in ("ΔEQ", "quad"):
                    self.mode_combo.setCurrentIndex(2)
                elif var_saved in ("IS", "delta"):
                    self.mode_combo.setCurrentIndex(3)
            # En modo discreto _on_mode_changed no toca la variable del panel de
            # distribución: alinearla con la guardada para que los rangos de los
            # controles casen con los valores que se restauran después.
            if self.mode_combo.currentIndex() == 0 and hasattr(self, "dist_panel"):
                _var_map = {"BHF": "bhf", "ΔEQ": "quad", "IS": "delta"}
                _var_lbl = state.get("dist_variable", "BHF")
                if _var_lbl in _var_map and hasattr(self.dist_panel, "set_distribution_variable"):
                    self.dist_panel.set_distribution_variable(_var_map[_var_lbl])
            for cp in self.components_panels:
                # Orden: primero tipo y modos (cambiar el tipo resetea valores
                # vía _on_type_changed, y los setters de modo re-layoutan el
                # grid); después los valores y las casillas «Fijo» guardados.
                # Con el orden antiguo (valores→tipo) un kind distinto al actual
                # machacaba int1/int2 recién restaurados, y la asignación
                # directa de los modos dejaba el grid agrisado obsoleto.
                ki = kind_map.get(str(cp.idx))
                if ki in COMPONENT_KINDS:
                    cp.type_combo.setCurrentText(ki)
                im = imode_map.get(str(cp.idx))
                if im in INTENSITY_MODES:
                    cp._set_intensity_mode(im)
                qt_v = qtreat_map.get(str(cp.idx))
                if qt_v in QUAD_TREATMENTS:
                    cp._set_quad_treatment(qt_v)
                cp.apply_values(vmap)
                en = enabled_map.get(str(cp.idx))
                if en is not None:
                    cp.enabled.setChecked(bool(en))
                for name, ctl in cp.params.items():
                    f = state.get("fixed", {}).get(f"s{cp.idx}_{name}")
                    if f is not None:
                        ctl.set_fixed(bool(f))
            # Casillas «Fijo» de calibración (antes solo se restauraban las de
            # los componentes y la de σ; baseline/slope/sat_scale se perdían).
            fixed_map_calib = state.get("fixed", {})
            for name, ctl in (("baseline", self.calib.baseline),
                              ("slope", self.calib.slope),
                              ("sat_scale", self.calib.sat_scale)):
                f = fixed_map_calib.get(name)
                if f is not None:
                    ctl.set_fixed(bool(f))
            self.calib.fit_velocity.setChecked(bool(state.get("fit_velocity", False)))
            self.calib.fit_center.setChecked(bool(state.get("fit_center", False)))
            # 'Ajustar σ' se controla ahora con la casilla 'Fijo' de σ.
            self.calib.voigt_sigma.set_fixed(not bool(state.get("fit_sigma", False)))
            lp = state.get("line_profile")
            if lp in ("Lorentziana", "Voigt"):
                self.calib._set_line_profile(lp)
            if "show_residual" in state and hasattr(self, "act_show_residual"):
                self.act_show_residual.setChecked(bool(state["show_residual"]))
            if "show_legend" in state and hasattr(self, "act_show_legend"):
                self.act_show_legend.setChecked(bool(state["show_legend"]))
            if "show_component_fill" in state and hasattr(self, "act_show_component_fill"):
                self.act_show_component_fill.setChecked(bool(state["show_component_fill"]))
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
            if state.get("multistart_n") is not None:
                self.multistart_n = int(state["multistart_n"])
                spin = getattr(self, "_multistart_spin", None)
                if spin is not None:
                    spin.blockSignals(True)
                    spin.setValue(self.multistart_n)
                    spin.blockSignals(False)
            am = state.get("absorber_model")
            if am in ("thin", "thickness"):
                self.absorber_model = am
                self.calib.set_absorber_model(am)
            df = state.get("drive_form")
            if df in ("triangular", "sine"):
                self.calib.set_drive_form(df)
            if "dist_use_sharp" in state:
                self.dist_use_sharp = bool(state["dist_use_sharp"])
            # dist_refine_global era un campo legacy (v4.5); se ignora silenciosamente
            if "constraints" in state:
                self.constraints = list(state.get("constraints") or [])
            shape_saved = state.get("dist_shape")
            reg_saved = state.get("dist_reg_mode")
            if reg_saved in ("tikhonov", "tv", "maxent") and hasattr(self, "dist_panel"):
                self.dist_panel.reg_mode_combo.setCurrentText(reg_saved)
            if hasattr(self, "dist_panel"):
                fixed_path = state.get("fixed_distribution_path")
                # None también resetea: una ruta fijada previamente no debe
                # sobrevivir a una sesión que no la contiene.
                self.dist_panel.fixed_path = Path(fixed_path) if fixed_path else None
            if shape_saved in DISTRIBUTION_SHAPES and hasattr(self, "dist_panel"):
                idx_shape = self.dist_panel.shape_combo.findData(shape_saved)
                if idx_shape >= 0:
                    self.dist_panel.shape_combo.setCurrentIndex(idx_shape)
            # Ajustes numéricos del panel de distribución (δ, ΔEQ, Γ, malla,
            # α, κδ/κq y nº de gaussianas VBF). Antes no se restauraban.
            if hasattr(self, "dist_panel"):
                dp = self.dist_panel
                _num_ctls = {
                    "dist_delta": dp.delta, "dist_quad": dp.quad,
                    "dist_fixed_bhf": dp.fixed_bhf, "dist_gamma": dp.gamma,
                    "dist_bmin": dp.bmin, "dist_bmax": dp.bmax,
                    "dist_nbins": dp.nbins, "dist_log_alpha": dp.log_alpha,
                    "dist_delta_slope": dp.delta_slope, "dist_quad_slope": dp.quad_slope,
                    "dist_qmin": dp.qmin, "dist_qmax": dp.qmax,
                    "dist_qbins": dp.qbins, "dist_log_alpha_q": dp.log_alpha_q,
                }
                for key, ctl in _num_ctls.items():
                    # Las sesiones antiguas guardaban estos ajustes dentro de
                    # model_state["vars"]; sin el fallback se reseteaban a los
                    # defaults en silencio.
                    val = state.get(key, vmap.get(key))
                    if val is not None:
                        try:
                            ctl.set_value(float(val))
                        except (TypeError, ValueError):
                            pass
                if "dist_vbf_n_components" in state:
                    try:
                        dp.vbf_ncomp.setValue(int(state["dist_vbf_n_components"]))
                    except (TypeError, ValueError):
                        pass
                fixed_map = state.get("dist_fixed") or {}
                _fix_ctls = {
                    "delta": dp.delta, "quad": dp.quad, "gamma": dp.gamma,
                    "delta_slope": dp.delta_slope, "quad_slope": dp.quad_slope,
                }
                for name, ctl in _fix_ctls.items():
                    if name in fixed_map:
                        ctl.set_fixed(bool(fixed_map[name]))
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
            ):
                a = getattr(self, attr, None)
                if a is not None:
                    a.setChecked(bool(value))
            if hasattr(self, "dist_panel"):
                self.dist_panel.use_sharp.setChecked(bool(self.dist_use_sharp))
        finally:
            self._building = False
        # Los datos se doblaron con el centro auto-detectado; si la sesión trae
        # otro folding point (p. ej. ajustado con «Ajustar centro»), re-dobla con
        # él para que datos y widget queden coherentes.
        saved_center = float(self.calib.center.value())
        if (self.file.counts is not None and self.file.center is not None
                and abs(saved_center - float(self.file.center)) > 1e-9):
            self._refold_current_data(saved_center)
        self._simulate_enabled = True
        self._refresh_plot()

    def on_save_session(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("file.save_session"), str(ROOT),
            "JSON (*.json);;All (*.*)")
        if not path:
            return
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
