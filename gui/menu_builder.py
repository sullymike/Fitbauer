"""Construcción de la barra de menús y acciones globales."""
from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from mossbauer_i18n import tr, get_language, set_language, available_languages
from core.data_io import update_settings
from gui.main_layout import fit_mode_labels
from gui.themes import COLOR_THEMES

# Registro canónico de atajos configurables por el usuario.
# Cada entrada: (action_id, menu_label_key, action_label_key, default_shortcut)
# El action_id coincide con la clave de traducción de la acción salvo donde se
# anota, y se usa para casar la QAction con su fila en el editor de atajos.
# Un default vacío ("") indica que la acción no trae atajo de fábrica pero el
# usuario puede asignarle uno.
SHORTCUT_REGISTRY: list[tuple[str, str, str, str]] = [
    # ── Archivo ──
    ("file.open",              "menu.file", "file.open",              "Ctrl+O"),
    ("file.compare_spectrum",  "menu.file", "file.compare_spectrum",  ""),
    ("file.clear_comparison",  "menu.file", "file.clear_comparison",  ""),
    ("file.use_as_calibration","menu.file", "file.use_as_calibration",""),
    ("file.save_fit",             "menu.file", "file.save_fit",             ""),
    ("file.export_report",        "menu.file", "file.export_report",        ""),
    ("file.export_short_report",  "menu.file", "file.export_short_report",  ""),
    ("file.save_session",      "menu.file", "file.save_session",      "Ctrl+S"),
    ("file.load_session",      "menu.file", "file.load_session",      "Ctrl+L"),
    ("file.exit",              "menu.file", "file.exit",              "Ctrl+Q"),
    # ── Ajuste ──
    ("fit.run",                "menu.fit",  "fit.run",                "Ctrl+R"),
    ("fit.undo_fit",           "menu.fit",  "fit.undo_fit",           "Ctrl+Z"),
    ("fit.history",            "menu.fit",  "history.title",          ""),
    ("fit.find_center",        "menu.fit",  "fit.find_center",        ""),
    ("fit.init_from_minima",   "menu.fit",  "fit.init_from_minima",   ""),
    ("fit.identify_phases",    "menu.fit",  "phase.identify",         ""),
    ("fit.edit_minima",        "menu.fit",  "minima.edit_action",     ""),
    ("fit.auto_from_minima",   "menu.fit",  "fit.auto_from_minima",   ""),
    ("fit.ollama_start",       "menu.fit",  "fit.ollama_start",       ""),
    ("fit.bootstrap",          "menu.fit",  "fit.bootstrap",          ""),
    ("fit.profile_likelihood", "menu.fit",  "fit.profile_likelihood", ""),
    ("fit.lcurve",             "menu.fit",  "bhf.lcurve_alpha",       ""),
    ("fit.batch_fit",          "menu.fit",  "fit.batch_fit",          ""),
    ("fit.global_neel_fit",    "menu.fit",  "fit.global_neel_fit",    ""),
    ("fit.free_all",           "menu.fit",  "fit.free_all",           ""),
    ("fit.fix_all",            "menu.fit",  "fit.fix_all",            ""),
    ("fit.constraints",        "menu.fit",  "options.constraints",    ""),
    ("fit.physical_presets",   "menu.fit",  "options.physical_presets",""),
    # ── Vista ──
    ("view.show_residual",     "menu.view", "options.show_residual",  ""),
    ("view.show_legend",       "menu.view", "options.show_legend",    ""),
    ("view.show_component_fill", "menu.view", "options.show_component_fill", ""),
    ("view.configure_layout",  "menu.view", "view.configure_layout",  ""),
    # ── Ayuda ──
    ("help.open",              "menu.help", "help.open",              "F1"),
    ("help.manual",            "menu.help", "help.manual",            ""),
    ("help.about",             "menu.help", "help.about",             ""),
    ("help.changelog",         "menu.help", "help.changelog",         ""),
    ("help.check_updates",     "menu.help", "help.check_updates",     ""),
    ("help.configure_updates", "menu.help", "help.configure_updates", ""),
]


class MenuBuilderMixin:
    # ── Menubar ──────────────────────────────────────────────────────────
    # Estructura: Archivo / Ajuste / Vista / Ayuda. El antiguo menú
    # "Opciones" (herencia Tk) se eliminó: duplicaba entradas de Ajuste y
    # Vista compartiendo los mismos QActionGroup exclusivos, con lo que sus
    # checkmarks nunca podían reflejar el estado (mismo problema que el
    # "Tema visual" duplicado retirado en v4.7.1).

    def _shortcut_for(self, action_id: str, default: str = "") -> str:
        """Devuelve el atajo personalizado para action_id, o el predeterminado."""
        return getattr(self, "_custom_shortcuts", {}).get(action_id, default)

    def _reg(self, action_id: str, action: "QtGui.QAction") -> "QtGui.QAction":
        """Registra una QAction y le aplica su atajo (custom o predeterminado).

        Permite que cualquier acción de menú sea configurable desde el editor de
        atajos aunque no traiga uno de fábrica.
        """
        default = next((d for a, _, _, d in SHORTCUT_REGISTRY if a == action_id), "")
        sc = self._shortcut_for(action_id, default)
        if sc:
            action.setShortcut(QtGui.QKeySequence(sc))
        self._action_registry[action_id] = action
        return action

    def _apply_custom_shortcuts(self, shortcuts: dict) -> None:
        """Aplica un dict {action_id: shortcut_str} a los QAction registrados."""
        self._custom_shortcuts = dict(shortcuts)
        for action_id, action in getattr(self, "_action_registry", {}).items():
            default = next((d for a, _, _, d in SHORTCUT_REGISTRY if a == action_id), "")
            new_sc = shortcuts.get(action_id, default)
            action.setShortcut(QtGui.QKeySequence(new_sc) if new_sc else QtGui.QKeySequence())

    def _build_menubar(self) -> None:
        self._action_registry: dict[str, QtGui.QAction] = {}
        mb = self.menuBar()

        # ── Archivo ──────────────────────────────────────────────────────
        file_menu = mb.addMenu(tr("menu.file"))
        act_open = QtGui.QAction(tr("file.open"), self)
        act_open.triggered.connect(self.on_open)
        file_menu.addAction(act_open)
        self._reg("file.open", act_open)
        self.recent_menu = file_menu.addMenu(tr("file.open_recent", default="Abrir recientes"))
        self._rebuild_recent_menu()
        act_compare = QtGui.QAction(tr("file.compare_spectrum"), self)
        act_compare.triggered.connect(self.on_open_comparison)
        file_menu.addAction(act_compare)
        self._reg("file.compare_spectrum", act_compare)
        self.act_clear_comparison = QtGui.QAction(tr("file.clear_comparison"), self)
        self.act_clear_comparison.triggered.connect(self.on_clear_comparison)
        self.act_clear_comparison.setEnabled(False)
        file_menu.addAction(self.act_clear_comparison)
        self._reg("file.clear_comparison", self.act_clear_comparison)
        self.act_use_as_calib = QtGui.QAction(tr("file.use_as_calibration"), self)
        self.act_use_as_calib.triggered.connect(self._use_as_calibration_detailed)
        self.act_use_as_calib.setEnabled(False)
        file_menu.addAction(self.act_use_as_calib)
        self._reg("file.use_as_calibration", self.act_use_as_calib)
        file_menu.addSeparator()
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
        file_menu.addSeparator()
        self.act_save_fit = QtGui.QAction(tr("file.save_fit"), self)
        self.act_save_fit.triggered.connect(self.on_save_fit)
        self.act_save_fit.setEnabled(False)
        file_menu.addAction(self.act_save_fit)
        self._reg("file.save_fit", self.act_save_fit)
        self.act_export_report = QtGui.QAction(tr("file.export_report"), self)
        self.act_export_report.triggered.connect(self.on_export_report)
        self.act_export_report.setEnabled(False)
        file_menu.addAction(self.act_export_report)
        self._reg("file.export_report", self.act_export_report)
        self.act_export_short_report = QtGui.QAction(tr("file.export_short_report"), self)
        self.act_export_short_report.triggered.connect(self.on_export_short_report)
        self.act_export_short_report.setEnabled(False)
        file_menu.addAction(self.act_export_short_report)
        self._reg("file.export_short_report", self.act_export_short_report)
        file_menu.addSeparator()
        act_save_session = QtGui.QAction(tr("file.save_session"), self)
        act_save_session.triggered.connect(self.on_save_session)
        file_menu.addAction(act_save_session)
        self._reg("file.save_session", act_save_session)
        act_load_session = QtGui.QAction(tr("file.load_session"), self)
        act_load_session.triggered.connect(self.on_load_session)
        file_menu.addAction(act_load_session)
        self._reg("file.load_session", act_load_session)
        file_menu.addSeparator()
        act_exit = QtGui.QAction(tr("file.exit"), self)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)
        self._reg("file.exit", act_exit)

        # ── Ajuste ───────────────────────────────────────────────────────
        fit_menu = mb.addMenu(tr("menu.fit"))
        self.act_fit = QtGui.QAction(tr("fit.run"), self)
        self.act_fit.triggered.connect(self.on_fit)
        self.act_fit.setEnabled(False)
        fit_menu.addAction(self.act_fit)
        self._reg("fit.run", self.act_fit)
        self.act_undo_fit = QtGui.QAction(tr("fit.undo_fit"), self)
        self.act_undo_fit.triggered.connect(self._undo_fit)
        self.act_undo_fit.setEnabled(False)
        fit_menu.addAction(self.act_undo_fit)
        self._reg("fit.undo_fit", self.act_undo_fit)
        self.act_fit_history = QtGui.QAction(
            tr("history.title", default="Historial de ajustes…"), self)
        self.act_fit_history.triggered.connect(lambda _checked=False: self.on_fit_history())
        self.act_fit_history.setEnabled(bool(getattr(self, "fit_history", None)))
        fit_menu.addAction(self.act_fit_history)
        self._reg("fit.history", self.act_fit_history)
        # Modo de ajuste: radios para TODOS los modos del combo lateral
        # (sincronizados en ambos sentidos vía _on_mode_changed).
        mode_menu = fit_menu.addMenu(tr("fit.mode_menu", default="Modo de ajuste"))
        self.mode_action_group = QtGui.QActionGroup(self)
        self._mode_menu_actions = []
        for idx, label in enumerate(fit_mode_labels()):
            a = QtGui.QAction(label, self, checkable=True)
            if idx == 0:
                a.setChecked(True)
            a.triggered.connect(lambda _c=False, i=idx: self.mode_combo.setCurrentIndex(i))
            mode_menu.addAction(a)
            self.mode_action_group.addAction(a)
            self._mode_menu_actions.append(a)
        fit_menu.addSeparator()
        # Preparación del ajuste (acciones pre-ajuste).
        prep_menu = fit_menu.addMenu(tr("fit.prepare_menu", default="Preparación"))
        self.act_find_center = QtGui.QAction(tr("fit.find_center"), self)
        self.act_find_center.triggered.connect(self.on_find_center)
        self.act_find_center.setEnabled(False)
        prep_menu.addAction(self.act_find_center)
        self._reg("fit.find_center", self.act_find_center)
        self.act_init = QtGui.QAction(tr("fit.init_from_minima"), self)
        # QAction.triggered emits a checked=False argument.  Use a lambda so it
        # does not override on_init_from_minima(show_message=True).
        self.act_init.triggered.connect(lambda _checked=False: self.on_init_from_minima(show_message=True))
        self.act_init.setEnabled(False)
        prep_menu.addAction(self.act_init)
        self._reg("fit.init_from_minima", self.act_init)
        # Interruptor maestro de la predicción de fases (desactivado por defecto).
        self.act_phase_predict = QtGui.QAction(
            tr("phase.predict_toggle", default="Predicción de fases"), self,
            checkable=True)
        self.act_phase_predict.setChecked(getattr(self, "phase_predict_enabled", False))
        self.act_phase_predict.toggled.connect(self._on_phase_predict_toggled)
        prep_menu.addAction(self.act_phase_predict)
        self.act_identify_phases = QtGui.QAction(
            tr("phase.identify", default="Identificar fases…"), self)
        self.act_identify_phases.triggered.connect(
            lambda _checked=False: self.on_identify_phases())
        self.act_identify_phases.setEnabled(False)
        prep_menu.addAction(self.act_identify_phases)
        self._reg("fit.identify_phases", self.act_identify_phases)
        self.act_edit_minima = QtGui.QAction(
            tr("minima.edit_action", default="Editar mínimos (semi-manual)…"), self)
        self.act_edit_minima.triggered.connect(lambda _checked=False: self.on_edit_minima())
        self.act_edit_minima.setEnabled(False)
        prep_menu.addAction(self.act_edit_minima)
        self._reg("fit.edit_minima", self.act_edit_minima)
        self.act_auto_fit = QtGui.QAction(tr("fit.auto_from_minima"), self)
        self.act_auto_fit.triggered.connect(lambda _checked=False: self.on_auto_fit_from_minima())
        self.act_auto_fit.setEnabled(False)
        prep_menu.addAction(self.act_auto_fit)
        self._reg("fit.auto_from_minima", self.act_auto_fit)
        self.act_ai = QtGui.QAction(tr("fit.ollama_start"), self)
        self.act_ai.triggered.connect(self.on_ai_summary)
        self.act_ai.setEnabled(False)
        prep_menu.addAction(self.act_ai)
        self._reg("fit.ollama_start", self.act_ai)
        # Análisis de errores post-ajuste (incluida la L-curve del modo distribución).
        err_menu = fit_menu.addMenu(tr("fit.error_analysis_menu", default="Análisis de errores"))
        self.act_bootstrap = QtGui.QAction(tr("fit.bootstrap"), self)
        self.act_bootstrap.triggered.connect(self.on_bootstrap)
        self.act_bootstrap.setEnabled(False)
        err_menu.addAction(self.act_bootstrap)
        self._reg("fit.bootstrap", self.act_bootstrap)
        self.act_profile = QtGui.QAction(tr("fit.profile_likelihood"), self)
        self.act_profile.triggered.connect(self.on_profile_likelihood)
        self.act_profile.setEnabled(False)
        err_menu.addAction(self.act_profile)
        self._reg("fit.profile_likelihood", self.act_profile)
        self.act_lcurve = QtGui.QAction(tr("bhf.lcurve_alpha"), self)
        self.act_lcurve.triggered.connect(self.on_lcurve)
        self.act_lcurve.setEnabled(False)
        err_menu.addAction(self.act_lcurve)
        self._reg("fit.lcurve", self.act_lcurve)
        self.act_batch = QtGui.QAction(tr("fit.batch_fit"), self)
        self.act_batch.triggered.connect(self.on_batch_fit)
        fit_menu.addAction(self.act_batch)
        self._reg("fit.batch_fit", self.act_batch)
        self.act_global_neel = QtGui.QAction(tr("fit.global_neel_fit"), self)
        self.act_global_neel.triggered.connect(self.on_global_neel_fit)
        fit_menu.addAction(self.act_global_neel)
        self._reg("fit.global_neel_fit", self.act_global_neel)
        fit_menu.addSeparator()
        # Gestión de parámetros del modelo.
        act_free_all = QtGui.QAction(tr("fit.free_all"), self)
        act_free_all.triggered.connect(lambda: self._set_all_fixed(False))
        fit_menu.addAction(act_free_all)
        self._reg("fit.free_all", act_free_all)
        act_fix_all = QtGui.QAction(tr("fit.fix_all"), self)
        act_fix_all.triggered.connect(lambda: self._set_all_fixed(True))
        fit_menu.addAction(act_fix_all)
        self._reg("fit.fix_all", act_fix_all)
        act_constraints = QtGui.QAction(tr("options.constraints"), self)
        act_constraints.triggered.connect(self.on_constraints)
        fit_menu.addAction(act_constraints)
        self._reg("fit.constraints", act_constraints)
        act_presets = QtGui.QAction(tr("options.physical_presets"), self)
        act_presets.triggered.connect(self.on_physical_presets)
        fit_menu.addAction(act_presets)
        self._reg("fit.physical_presets", act_presets)
        fit_menu.addSeparator()
        # Submenú de opciones avanzadas.
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
        # Arranques múltiples (spinbox inline)
        _wa = QtWidgets.QWidgetAction(self)
        _ms_container = QtWidgets.QWidget()
        _ms_h = QtWidgets.QHBoxLayout(_ms_container)
        _ms_h.setContentsMargins(16, 2, 8, 2)
        _ms_h.addWidget(QtWidgets.QLabel(tr("options.multistart_n")))
        _ms_h.addStretch(1)
        from core.param_overrides import effective_fit_init_specs as _eff_fi
        _fi = _eff_fi()
        self._multistart_spin = QtWidgets.QSpinBox()
        self._multistart_spin.setRange(0, int(_fi["multistart_n_max"].default))
        self._multistart_spin.setValue(getattr(self, "multistart_n", 8))
        self._multistart_spin.setFixedWidth(50)
        def _on_multistart_changed(v: int) -> None:
            self.multistart_n = v
            self._save_settings()
        self._multistart_spin.valueChanged.connect(_on_multistart_changed)
        _ms_h.addWidget(self._multistart_spin)
        _wa.setDefaultWidget(_ms_container)
        adv_menu.addAction(_wa)
        # Modelo de absorbente
        abs_menu = adv_menu.addMenu(tr("absorber.model_label"))
        self.absorber_action_group = QtGui.QActionGroup(self)
        for val, key in (("thin", "absorber.thin"),
                          ("thickness", "absorber.thickness")):
            a = QtGui.QAction(tr(key), self, checkable=True)
            if val == self.absorber_model:
                a.setChecked(True)
            # Sincroniza el combo del panel (fuente que lee el motor); el combo
            # emite paramChanged, que re-sincroniza el atributo y refresca el
            # plot. Un setattr directo dejaba el fit usando el modelo antiguo.
            a.triggered.connect(lambda _c=False, v=val: self.calib.set_absorber_model(v))
            abs_menu.addAction(a); self.absorber_action_group.addAction(a)
        adv_menu.addSeparator()
        # P(BHF) extras
        self.act_add_sharp = QtGui.QAction(tr("options.add_sharp"), self,
                                            checkable=True)
        self.act_add_sharp.setChecked(self.dist_use_sharp)
        self.act_add_sharp.toggled.connect(self._set_dist_use_sharp)
        adv_menu.addAction(self.act_add_sharp)
        # Reabrir el gráfico de la última distribución ajustada (1D/2D).
        self.act_show_distribution = QtGui.QAction(
            tr("button.show_distribution", default="Ver distribución…"), self)
        self.act_show_distribution.triggered.connect(self._on_reopen_map_dialog)
        adv_menu.addAction(self.act_show_distribution)


        # ── Vista ────────────────────────────────────────────────────────
        view_menu = mb.addMenu(tr("menu.view"))
        self.act_show_residual = QtGui.QAction(tr("options.show_residual"), self,
                                                checkable=True, checked=self._show_residual_pref)
        self.act_show_residual.toggled.connect(self._on_show_residual_toggled)
        self.act_show_residual.toggled.connect(lambda _: self._refresh_plot())
        view_menu.addAction(self.act_show_residual)
        self._reg("view.show_residual", self.act_show_residual)
        self.act_show_legend = QtGui.QAction(tr("options.show_legend"), self,
                                              checkable=True, checked=True)
        self.act_show_legend.toggled.connect(lambda _: self._refresh_plot())
        view_menu.addAction(self.act_show_legend)
        self._reg("view.show_legend", self.act_show_legend)
        self.act_show_component_fill = QtGui.QAction(tr("options.show_component_fill"), self,
                                                     checkable=True, checked=True)
        self.act_show_component_fill.toggled.connect(lambda _: self._refresh_plot())
        view_menu.addAction(self.act_show_component_fill)
        self._reg("view.show_component_fill", self.act_show_component_fill)
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
        self._reg("view.configure_layout", act_configure_layout)
        act_param_limits = QtGui.QAction(
            tr("view.param_limits", default="Límites de parámetros…"), self
        )
        act_param_limits.triggered.connect(self.on_param_limits)
        view_menu.addAction(act_param_limits)

        # ── Ayuda ────────────────────────────────────────────────────────
        help_menu = mb.addMenu(tr("menu.help"))
        act_help = QtGui.QAction(tr("help.open"), self)
        act_help.triggered.connect(lambda _checked=False: self.on_help())
        help_menu.addAction(act_help)
        self._reg("help.open", act_help)
        act_manual = QtGui.QAction(tr("help.manual", default="Manual (PDF, inglés)"), self)
        act_manual.triggered.connect(lambda _checked=False: self.on_open_manual())
        help_menu.addAction(act_manual)
        self._reg("help.manual", act_manual)
        act_shortcuts = QtGui.QAction(tr("help.shortcuts", default="Atajos de teclado…"), self)
        act_shortcuts.triggered.connect(lambda _checked=False: self.on_help(show_shortcuts=True))
        help_menu.addAction(act_shortcuts)
        act_about = QtGui.QAction(tr("help.about"), self)
        act_about.triggered.connect(self.on_about)
        help_menu.addAction(act_about)
        self._reg("help.about", act_about)
        help_menu.addSeparator()
        act_changelog = QtGui.QAction(tr("help.changelog"), self)
        act_changelog.triggered.connect(self.on_changelog)
        help_menu.addAction(act_changelog)
        self._reg("help.changelog", act_changelog)
        act_check_updates = QtGui.QAction(tr("help.check_updates"), self)
        act_check_updates.triggered.connect(self.on_check_updates)
        help_menu.addAction(act_check_updates)
        self._reg("help.check_updates", act_check_updates)
        act_configure_updates = QtGui.QAction(tr("help.configure_updates"), self)
        act_configure_updates.triggered.connect(self.on_configure_updates)
        help_menu.addAction(act_configure_updates)
        self._reg("help.configure_updates", act_configure_updates)


    def on_param_limits(self) -> None:
        """Abre el diálogo de edición de límites de parámetros."""
        from gui.param_limits_dialog import ParamLimitsDialog
        dlg = ParamLimitsDialog(self)
        dlg.exec()

    def _set_dist_use_sharp(self, enabled: bool) -> None:
        self.dist_use_sharp = bool(enabled)
        act = getattr(self, "act_add_sharp", None)
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


    def _set_language(self, code: str) -> None:
        set_language(code)
        # Persistir (best-effort)
        try:
            update_settings(ui_language=code)
        except Exception:
            pass
        QtWidgets.QMessageBox.information(
            self, tr("language.restart_title"), tr("language.restart_message"))
