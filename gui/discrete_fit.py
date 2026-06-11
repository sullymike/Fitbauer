"""Ajuste discreto y bootstrap desde la GUI Qt."""
from __future__ import annotations

from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.fit_engine import bootstrap_errors, fit_discrete
from gui.fit_workflow import GuiFitResult


class DiscreteFitMixin:
    def on_fit(self) -> None:
        if self.is_distribution_mode:
            self._simulate_enabled = True
            self.on_fit_distribution()
            return
        self._simulate_enabled = True
        # Un ajuste discreto invalida cualquier mapa topográfico 2D previo.
        self._dist_map_2d = None
        calib_state = self.calib.to_view_state()
        if (calib_state.fit_velocity
                and not all(self._active_bhf_fixed_flags())):
            QtWidgets.QMessageBox.warning(
                self,
                tr("msg.fit_velocity_title"),
                tr("msg.fit_velocity_requires_bhf_fixed"),
            )
            return
        state = self._build_state(validate_params=True)
        if state is None:
            return
        self._pre_fit_snapshot = self._project_state().to_session_payload()

        def _progress(update_progress):
            def cb(info):
                update_progress(info)
                if isinstance(info, dict) and "free_keys" in info:
                    self._render_intermediate_fit(
                        state, info["free_keys"], info["free_values"])
            return fit_discrete(state, progress_cb=cb)

        result = self._run_with_fit_progress(
            tr("progress.fitting_title", default="Ajustando"),
            tr("progress.fit_prepare", default="Preparando ajuste…"),
            _progress,
            error_title=tr("fit.run"),
            disable_fit_action=True,
        )
        if result is None:
            return
        if hasattr(self, "act_undo_fit"):
            self.act_undo_fit.setEnabled(True)
        # Aplica resultados
        self._building = True
        calib_state = self.calib.to_view_state()
        self.calib.baseline.set_value(result.values.get("baseline", calib_state.baseline))
        self.calib.slope.set_value(result.values.get("slope", calib_state.slope))
        if state.fit_velocity:
            self.calib.vmax.set_value(result.values.get("vmax", calib_state.vmax))
        if state.fit_sigma:
            self.calib.voigt_sigma.set_value(result.values.get("voigt_sigma", calib_state.voigt_sigma))
        for cp in self.components_panels:
            cp.apply_values(result.values)
        self._building = False
        red = result.stats.get("red_chi2", float("nan"))
        chi2 = result.stats.get("chi2", float("nan"))
        gui_result = GuiFitResult(
            mode="discrete",
            raw_result=result,
            message=f"χ²={chi2:.4g}  χ²red={red:.4g}  ·  {result.n_starts} arranques",
        )
        self.runtime_results.set_discrete_fit(result, gui_result=gui_result)
        self._finish_gui_fit_result(gui_result)
        self._refresh_plot()





    # ── Bootstrap MC ─────────────────────────────────────────────────────
    def on_bootstrap(self) -> None:
        """Estima errores por remuestreo Monte Carlo (solo modo discreto)."""
        if self.is_distribution_mode:
            QtWidgets.QMessageBox.information(
                self, tr("msg.bootstrap_title"), tr("msg.bootstrap_discrete_only"))
            return
        state = self._build_state(validate_params=True)
        if state is None:
            return
        nrep, ok = QtWidgets.QInputDialog.getInt(
            self, tr("msg.bootstrap_title"),
            tr("dialog.bootstrap_prompt") if hasattr(tr, "_dummy") else "Número de réplicas:",
            30, 5, 300, 5)
        if not ok:
            return
        # Motor puro: ajuste base + remuestreo Monte Carlo (core.fit_engine).
        self.statusBar().showMessage("Ajuste base…")
        QtWidgets.QApplication.processEvents()

        def _progress(msg: str, _i: int, _n: int) -> None:
            self.statusBar().showMessage(f"{msg}…")
            QtWidgets.QApplication.processEvents()

        try:
            res = bootstrap_errors(state, n_rep=nrep, progress_cb=_progress)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("msg.bootstrap_title"),
                                            f"{type(exc).__name__}: {exc}")
            return
        if not res.base.free_keys:
            QtWidgets.QMessageBox.information(
                self, tr("msg.bootstrap_title"), tr("msg.bootstrap_no_free"))
            return
        # Vuelca σ(MC) en el último ajuste para que el informe la use como
        # incertidumbre (más fiable que la covarianza cuando hay correlaciones).
        error_source = f"bootstrap Monte Carlo (n={res.n_ok})"
        if self.runtime_results.fit_result is not None:
            self.runtime_results.update_discrete_errors(res.std)
            self.runtime_results.set_error_source(error_source)
        else:
            self.runtime_results.replace_discrete_fit(
                res.base,
                errors=res.std,
                error_source=error_source,
            )
        self.act_export_report.setEnabled(True)
        msg_lines = [tr("msg.bootstrap_done", ok=res.n_ok, total=res.n_rep), ""]
        for k in res.base.free_keys:
            msg_lines.append(f"  {k:14s}  σ(MC) = {res.std[k]:.4g}")
        QtWidgets.QMessageBox.information(
            self, tr("msg.bootstrap_title"), "\n".join(msg_lines))
