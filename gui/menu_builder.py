"""Construcción de la barra de menús y acciones globales."""
from __future__ import annotations

import json

from PySide6 import QtGui, QtWidgets

from mossbauer_i18n import tr, get_language, set_language, available_languages
from core.data_io import SETTINGS_PATH
from gui.themes import COLOR_THEMES


class MenuBuilderMixin:
    # ── Menubar (orden igual al de la GUI Tk) ────────────────────────────
    def _build_menubar(self) -> None:
        mb = self.menuBar()

        # ── Archivo ──────────────────────────────────────────────────────
        file_menu = mb.addMenu(tr("menu.file"))
        act_open = QtGui.QAction(tr("file.open"), self)
        act_open.setShortcut(QtGui.QKeySequence.Open)
        act_open.triggered.connect(self.on_open)
        file_menu.addAction(act_open)
        self.recent_menu = file_menu.addMenu("Open Recent")
        self._rebuild_recent_menu()
        web_menu = file_menu.addMenu(tr("file.web"))
        act_web_meas = QtGui.QAction(tr("file.web_measurements"), self)
        act_web_meas.triggered.connect(lambda: self._open_web_dialog("measurements"))
        web_menu.addAction(act_web_meas)
        act_web_calib = QtGui.QAction(tr("file.web_calibrations"), self)
        act_web_calib.triggered.connect(lambda: self._open_web_dialog("calibrations"))
        web_menu.addAction(act_web_calib)
        self.act_upload_session = QtGui.QAction(tr("file.upload_session"), self)
        self.act_upload_session.triggered.connect(self.on_upload_session)
        self.act_upload_session.setEnabled(False)
        web_menu.addAction(self.act_upload_session)
        self.act_use_as_calib = QtGui.QAction(tr("file.use_as_calibration"), self)
        self.act_use_as_calib.triggered.connect(self._use_as_calibration_detailed)
        self.act_use_as_calib.setEnabled(False)
        file_menu.addAction(self.act_use_as_calib)
        file_menu.addSeparator()
        self.act_save_fit = QtGui.QAction(tr("file.save_fit"), self)
        self.act_save_fit.triggered.connect(self.on_save_fit)
        self.act_save_fit.setEnabled(False)
        file_menu.addAction(self.act_save_fit)
        self.act_export_report = QtGui.QAction(tr("file.export_report"), self)
        self.act_export_report.triggered.connect(self.on_export_report)
        self.act_export_report.setEnabled(False)
        file_menu.addAction(self.act_export_report)
        self.act_export_plotly = QtGui.QAction(tr("file.export_plotly_html"), self)
        self.act_export_plotly.triggered.connect(self.on_export_plotly_html)
        self.act_export_plotly.setEnabled(False)
        file_menu.addAction(self.act_export_plotly)
        file_menu.addSeparator()
        act_save_session = QtGui.QAction(tr("file.save_session"), self)
        act_save_session.setShortcut("Ctrl+S")
        act_save_session.triggered.connect(self.on_save_session)
        file_menu.addAction(act_save_session)
        act_load_session = QtGui.QAction(tr("file.load_session"), self)
        act_load_session.setShortcut("Ctrl+L")
        act_load_session.triggered.connect(self.on_load_session)
        file_menu.addAction(act_load_session)
        file_menu.addSeparator()
        act_exit = QtGui.QAction(tr("file.exit"), self)
        act_exit.setShortcut(QtGui.QKeySequence.Quit)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # ── Ajuste ───────────────────────────────────────────────────────
        fit_menu = mb.addMenu(tr("menu.fit"))
        self.act_fit = QtGui.QAction(tr("fit.run"), self)
        self.act_fit.setShortcut("Ctrl+R")
        self.act_fit.triggered.connect(self.on_fit)
        self.act_fit.setEnabled(False)
        fit_menu.addAction(self.act_fit)
        fit_menu.addSeparator()
        self.act_find_center = QtGui.QAction(tr("fit.find_center"), self)
        self.act_find_center.triggered.connect(self.on_find_center)
        self.act_find_center.setEnabled(False)
        fit_menu.addAction(self.act_find_center)
        self.act_init = QtGui.QAction(tr("fit.init_from_minima"), self)
        # QAction.triggered emits a checked=False argument.  Use a lambda so it
        # does not override on_init_from_minima(show_message=True).
        self.act_init.triggered.connect(lambda _checked=False: self.on_init_from_minima(show_message=True))
        self.act_init.setEnabled(False)
        fit_menu.addAction(self.act_init)
        self.act_edit_minima = QtGui.QAction(
            tr("minima.edit_action", default="Editar mínimos (semi-manual)…"), self)
        self.act_edit_minima.triggered.connect(lambda _checked=False: self.on_edit_minima())
        self.act_edit_minima.setEnabled(False)
        fit_menu.addAction(self.act_edit_minima)
        self.act_auto_fit = QtGui.QAction(tr("fit.auto_from_minima"), self)
        self.act_auto_fit.triggered.connect(lambda _checked=False: self.on_auto_fit_from_minima())
        self.act_auto_fit.setEnabled(False)
        fit_menu.addAction(self.act_auto_fit)
        self.act_ai = QtGui.QAction(tr("fit.ollama_start"), self)
        self.act_ai.triggered.connect(self.on_ai_summary)
        self.act_ai.setEnabled(False)
        fit_menu.addAction(self.act_ai)
        self.act_bootstrap = QtGui.QAction(tr("fit.bootstrap"), self)
        self.act_bootstrap.triggered.connect(self.on_bootstrap)
        self.act_bootstrap.setEnabled(False)
        fit_menu.addAction(self.act_bootstrap)
        self.act_profile = QtGui.QAction(tr("fit.profile_likelihood"), self)
        self.act_profile.triggered.connect(self.on_profile_likelihood)
        self.act_profile.setEnabled(False)
        fit_menu.addAction(self.act_profile)
        self.act_batch = QtGui.QAction(tr("fit.batch_fit"), self)
        self.act_batch.triggered.connect(self.on_batch_fit)
        fit_menu.addAction(self.act_batch)
        fit_menu.addSeparator()
        # Modos (radio): Discreto / P(BHF) — coincide con el combobox lateral.
        self.mode_action_group = QtGui.QActionGroup(self)
        act_discrete = QtGui.QAction(tr("options.discrete_sextets"), self, checkable=True)
        act_discrete.setChecked(True)
        act_discrete.triggered.connect(lambda _c: self.mode_combo.setCurrentIndex(0))
        fit_menu.addAction(act_discrete); self.mode_action_group.addAction(act_discrete)
        act_pbhf = QtGui.QAction(tr("options.distribution_bhf"), self, checkable=True)
        act_pbhf.triggered.connect(lambda _c: self.mode_combo.setCurrentIndex(1))
        fit_menu.addAction(act_pbhf); self.mode_action_group.addAction(act_pbhf)
        self._mode_menu_actions = [act_discrete, act_pbhf]
        fit_menu.addSeparator()
        # Submenú de opciones avanzadas (igual estructura que la GUI Tk).
        adv_menu = fit_menu.addMenu(tr("options.advanced_fit"))
        # Perfil de línea
        prof_menu = adv_menu.addMenu(tr("options.line_profile"))
        self.profile_action_group = QtGui.QActionGroup(self)
        for kind, key in (("Lorentziana", "options.profile_lorentzian"),
                          ("Voigt", "options.profile_voigt")):
            a = QtGui.QAction(tr(key), self, checkable=True)
            if kind == "Lorentziana":
                a.setChecked(True)
            a.triggered.connect(lambda _c, k=kind: self.calib._set_line_profile(k))
            prof_menu.addAction(a); self.profile_action_group.addAction(a)
        # Verosimilitud
        lik_menu = adv_menu.addMenu(tr("options.likelihood"))
        self.likelihood_action_group = QtGui.QActionGroup(self)
        for val, key in (("gauss", "options.likelihood_gauss"),
                          ("poisson", "options.likelihood_poisson")):
            a = QtGui.QAction(tr(key), self, checkable=True)
            if val == self.likelihood:
                a.setChecked(True)
            a.triggered.connect(lambda _c=False, v=val: setattr(self, "likelihood", v))
            lik_menu.addAction(a); self.likelihood_action_group.addAction(a)
        # Pérdida robusta
        loss_menu = adv_menu.addMenu(tr("options.robust_loss"))
        self.loss_action_group = QtGui.QActionGroup(self)
        for val, key in (("linear", "options.loss_linear"),
                          ("soft_l1", "options.loss_soft_l1"),
                          ("huber", "options.loss_huber")):
            a = QtGui.QAction(tr(key), self, checkable=True)
            if val == self.robust_loss:
                a.setChecked(True)
            a.triggered.connect(lambda _c=False, v=val: setattr(self, "robust_loss", v))
            loss_menu.addAction(a); self.loss_action_group.addAction(a)
        # Propagar σ calibración (check)
        self.act_propagate = QtGui.QAction(tr("options.propagate_calib"), self,
                                            checkable=True)
        self.act_propagate.setChecked(self.propagate_calib)
        self.act_propagate.toggled.connect(
            lambda b: setattr(self, "propagate_calib", bool(b)))
        adv_menu.addAction(self.act_propagate)
        # Optimización global DE (check)
        self.act_global_opt = QtGui.QAction(tr("options.global_opt"), self,
                                             checkable=True)
        self.act_global_opt.setChecked(self.global_opt)
        self.act_global_opt.toggled.connect(
            lambda b: setattr(self, "global_opt", bool(b)))
        adv_menu.addAction(self.act_global_opt)
        # Modelo de absorbente
        abs_menu = adv_menu.addMenu(tr("absorber.model_label"))
        self.absorber_action_group = QtGui.QActionGroup(self)
        for val, key in (("thin", "absorber.thin"),
                          ("thickness", "absorber.thickness")):
            a = QtGui.QAction(tr(key), self, checkable=True)
            if val == self.absorber_model:
                a.setChecked(True)
            a.triggered.connect(lambda _c=False, v=val: setattr(self, "absorber_model", v))
            abs_menu.addAction(a); self.absorber_action_group.addAction(a)
        adv_menu.addSeparator()
        # P(BHF) extras
        self.act_add_sharp = QtGui.QAction(tr("options.add_sharp"), self,
                                            checkable=True)
        self.act_add_sharp.setChecked(self.dist_use_sharp)
        self.act_add_sharp.toggled.connect(self._set_dist_use_sharp)
        adv_menu.addAction(self.act_add_sharp)
        self.act_refine_global = QtGui.QAction(tr("options.refine_global"), self,
                                                checkable=True)
        self.act_refine_global.setChecked(self.dist_refine_global)
        self.act_refine_global.toggled.connect(self._set_dist_refine_global)
        adv_menu.addAction(self.act_refine_global)
        fit_menu.addSeparator()
        act_free_all = QtGui.QAction(tr("fit.free_all"), self)
        act_free_all.triggered.connect(lambda: self._set_all_fixed(False))
        fit_menu.addAction(act_free_all)
        act_fix_all = QtGui.QAction(tr("fit.fix_all"), self)
        act_fix_all.triggered.connect(lambda: self._set_all_fixed(True))
        fit_menu.addAction(act_fix_all)
        fit_menu.addSeparator()
        act_constraints = QtGui.QAction(tr("options.constraints"), self)
        act_constraints.triggered.connect(self.on_constraints)
        fit_menu.addAction(act_constraints)
        act_presets = QtGui.QAction(tr("options.physical_presets"), self)
        act_presets.triggered.connect(self.on_physical_presets)
        fit_menu.addAction(act_presets)
        self.act_lcurve = QtGui.QAction(tr("bhf.lcurve_alpha"), self)
        self.act_lcurve.triggered.connect(self.on_lcurve)
        self.act_lcurve.setEnabled(False)
        fit_menu.addAction(self.act_lcurve)

        # ── Opciones (menú clásico Tk) ───────────────────────────────────
        options_menu = mb.addMenu(tr("menu.options"))
        opt_discrete = QtGui.QAction(tr("options.discrete_sextets"), self, checkable=True)
        opt_discrete.setChecked(True)
        opt_discrete.triggered.connect(lambda _c=False: self.mode_combo.setCurrentIndex(0))
        options_menu.addAction(opt_discrete)
        self.mode_action_group.addAction(opt_discrete)
        opt_pbhf = QtGui.QAction(tr("options.distribution_bhf"), self, checkable=True)
        opt_pbhf.triggered.connect(lambda _c=False: self.mode_combo.setCurrentIndex(1))
        options_menu.addAction(opt_pbhf)
        self.mode_action_group.addAction(opt_pbhf)
        self._mode_menu_actions.extend([opt_discrete, opt_pbhf])
        options_menu.addSeparator()
        self.act_opt_show_residual = QtGui.QAction(tr("options.show_residual"), self,
                                                   checkable=True, checked=self._show_residual_pref)
        self.act_opt_show_residual.toggled.connect(lambda checked: getattr(self, "act_show_residual", self.act_opt_show_residual).setChecked(checked))
        options_menu.addAction(self.act_opt_show_residual)
        self.act_opt_show_legend = QtGui.QAction(tr("options.show_legend"), self, checkable=True, checked=True)
        self.act_opt_show_legend.toggled.connect(lambda checked: getattr(self, "act_show_legend", self.act_opt_show_legend).setChecked(checked))
        options_menu.addAction(self.act_opt_show_legend)
        options_menu.addSeparator()
        opt_profile_menu = options_menu.addMenu(tr("options.line_profile"))
        calib_state = self.calib.to_view_state()
        for kind, key in (("Lorentziana", "options.profile_lorentzian"), ("Voigt", "options.profile_voigt")):
            a = QtGui.QAction(tr(key), self, checkable=True)
            if kind == calib_state.line_profile:
                a.setChecked(True)
            a.triggered.connect(lambda _c=False, k=kind: self.calib._set_line_profile(k))
            opt_profile_menu.addAction(a)
            self.profile_action_group.addAction(a)
        options_menu.addSeparator()
        self.act_opt_add_sharp = QtGui.QAction(tr("options.add_sharp"), self, checkable=True)
        self.act_opt_add_sharp.toggled.connect(self._set_dist_use_sharp)
        options_menu.addAction(self.act_opt_add_sharp)
        self.act_opt_refine_global = QtGui.QAction(tr("options.refine_global"), self, checkable=True)
        self.act_opt_refine_global.toggled.connect(self._set_dist_refine_global)
        options_menu.addAction(self.act_opt_refine_global)
        options_menu.addSeparator()
        opt_constraints = QtGui.QAction(tr("options.constraints"), self)
        opt_constraints.triggered.connect(self.on_constraints)
        options_menu.addAction(opt_constraints)
        opt_presets = QtGui.QAction(tr("options.physical_presets"), self)
        opt_presets.triggered.connect(self.on_physical_presets)
        options_menu.addAction(opt_presets)
        options_menu.addSeparator()
        opt_theme_menu = options_menu.addMenu(tr("options.theme"))
        for style_name in QtWidgets.QStyleFactory.keys():
            a = QtGui.QAction(style_name, self, checkable=True)
            if style_name.lower() == "fusion":
                a.setChecked(True)
            a.triggered.connect(lambda _c=False, s=style_name: self._set_qt_style(s))
            opt_theme_menu.addAction(a)

        # ── Vista ────────────────────────────────────────────────────────
        view_menu = mb.addMenu(tr("menu.view"))
        self.act_show_residual = QtGui.QAction(tr("options.show_residual"), self,
                                                checkable=True, checked=self._show_residual_pref)
        self.act_show_residual.toggled.connect(self._on_show_residual_toggled)
        self.act_show_residual.toggled.connect(lambda _: self._refresh_plot())
        self.act_show_residual.toggled.connect(lambda checked: self.act_opt_show_residual.setChecked(checked) if hasattr(self, "act_opt_show_residual") and self.act_opt_show_residual.isChecked() != checked else None)
        view_menu.addAction(self.act_show_residual)
        self.act_show_legend = QtGui.QAction(tr("options.show_legend"), self,
                                              checkable=True, checked=True)
        self.act_show_legend.toggled.connect(lambda _: self._refresh_plot())
        self.act_show_legend.toggled.connect(lambda checked: self.act_opt_show_legend.setChecked(checked) if hasattr(self, "act_opt_show_legend") and self.act_opt_show_legend.isChecked() != checked else None)
        view_menu.addAction(self.act_show_legend)
        self.act_open_plotly = QtGui.QAction(tr("view.open_plotly"), self)
        self.act_open_plotly.triggered.connect(self.on_open_plotly)
        self.act_open_plotly.setEnabled(False)
        view_menu.addAction(self.act_open_plotly)
        view_menu.addSeparator()
        # Tema UI (QStyle de Qt). Por defecto Fusion.
        theme_menu = view_menu.addMenu(tr("options.theme"))
        self.theme_action_group = QtGui.QActionGroup(self)
        from PySide6 import QtWidgets as _qw
        available_styles = _qw.QStyleFactory.keys()
        for style_name in available_styles:
            a = QtGui.QAction(style_name, self, checkable=True)
            if style_name.lower() == "fusion":
                a.setChecked(True)
            a.triggered.connect(lambda _c=False, s=style_name: self._set_qt_style(s))
            theme_menu.addAction(a); self.theme_action_group.addAction(a)
        style_menu = view_menu.addMenu(tr("options.plot_style"))
        self.style_action_group = QtGui.QActionGroup(self)
        for value, label_key in (
            ("classic", "plot_style.classic"),
            ("modern", "plot_style.modern"),
            ("publication", "plot_style.publication"),
            ("dark", "plot_style.dark"),
        ):
            act = QtGui.QAction(tr(label_key), self, checkable=True)
            if value == self.plot_style_name:
                act.setChecked(True)
            act.triggered.connect(lambda _checked=False, v=value: self._set_plot_style(v))
            style_menu.addAction(act)
            self.style_action_group.addAction(act)

        # Tema de color de la interfaz (paleta de la aplicación).
        color_menu = view_menu.addMenu(tr("options.color_theme", default="Tema de color"))
        self.color_theme_group = QtGui.QActionGroup(self)
        for value, theme in COLOR_THEMES.items():
            act = QtGui.QAction(theme.get("label", value), self, checkable=True)
            if value == self.color_theme:
                act.setChecked(True)
            act.triggered.connect(lambda _checked=False, v=value: self._apply_color_theme(v))
            color_menu.addAction(act)
            self.color_theme_group.addAction(act)
        lang_menu = view_menu.addMenu(tr("menu.language"))
        self.lang_action_group = QtGui.QActionGroup(self)
        current_lang = get_language()
        for code, name in available_languages().items():
            act = QtGui.QAction(name, self, checkable=True)
            act.setChecked(code == current_lang)
            act.triggered.connect(lambda _checked=False, c=code: self._set_language(c))
            lang_menu.addAction(act)
            self.lang_action_group.addAction(act)
        view_menu.addSeparator()
        act_configure_layout = QtGui.QAction(tr("view.configure_layout"), self)
        act_configure_layout.triggered.connect(self.on_configure_layout)
        view_menu.addAction(act_configure_layout)

        # ── Ayuda ────────────────────────────────────────────────────────
        help_menu = mb.addMenu(tr("menu.help"))
        act_help = QtGui.QAction(tr("help.open"), self)
        act_help.setShortcut("F1")
        act_help.triggered.connect(self.on_help)
        help_menu.addAction(act_help)
        act_about = QtGui.QAction(tr("help.about"), self)
        act_about.triggered.connect(self.on_about)
        help_menu.addAction(act_about)
        help_menu.addSeparator()
        act_changelog = QtGui.QAction(tr("help.changelog"), self)
        act_changelog.triggered.connect(self.on_changelog)
        help_menu.addAction(act_changelog)
        act_check_updates = QtGui.QAction(tr("help.check_updates"), self)
        act_check_updates.triggered.connect(self.on_check_updates)
        help_menu.addAction(act_check_updates)
        act_configure_updates = QtGui.QAction(tr("help.configure_updates"), self)
        act_configure_updates.triggered.connect(self.on_configure_updates)
        help_menu.addAction(act_configure_updates)


    def _set_dist_use_sharp(self, enabled: bool) -> None:
        self.dist_use_sharp = bool(enabled)
        for attr in ("act_add_sharp", "act_opt_add_sharp"):
            act = getattr(self, attr, None)
            if act is not None and act.isChecked() != self.dist_use_sharp:
                act.blockSignals(True)
                act.setChecked(self.dist_use_sharp)
                act.blockSignals(False)
        if hasattr(self, "dist_panel") and self.dist_panel.use_sharp.isChecked() != self.dist_use_sharp:
            self.dist_panel.use_sharp.blockSignals(True)
            self.dist_panel.use_sharp.setChecked(self.dist_use_sharp)
            self.dist_panel.use_sharp.blockSignals(False)
        # En distribución, los sextetes solo se ven si se suman como nítidas.
        if hasattr(self, "_using_tabs") and self._using_tabs is not None:
            self._sync_component_count(self._ui_action_state().n_components)
            self._check_layout()
        self._simulate_enabled = True
        self._refresh_plot()

    def _set_dist_refine_global(self, enabled: bool) -> None:
        self.dist_refine_global = bool(enabled)
        for attr in ("act_refine_global", "act_opt_refine_global"):
            act = getattr(self, attr, None)
            if act is not None and act.isChecked() != self.dist_refine_global:
                act.blockSignals(True)
                act.setChecked(self.dist_refine_global)
                act.blockSignals(False)
        if hasattr(self, "dist_panel") and self.dist_panel.refine_global.isChecked() != self.dist_refine_global:
            self.dist_panel.refine_global.blockSignals(True)
            self.dist_panel.refine_global.setChecked(self.dist_refine_global)
            self.dist_panel.refine_global.blockSignals(False)
        self._simulate_enabled = True
        self._refresh_plot()

    def _set_language(self, code: str) -> None:
        set_language(code)
        # Persistir
        try:
            import json
            current = {}
            if SETTINGS_PATH.exists():
                try:
                    current = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                except Exception:
                    pass
            current["ui_language"] = code
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps(current, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception:
            pass
        QtWidgets.QMessageBox.information(
            self, tr("language.restart_title"), tr("language.restart_message"))
