"""MossbauerApp: versión modular de la GUI con layout configurable por el usuario.

Hereda toda la lógica de cálculo y ajuste de MossbauerFe33GUI y sobreescribe
únicamente la construcción de la interfaz para usar el sistema de paneles.
Los datos, el ajuste y las sesiones son 100% compatibles con la versión original.
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from mossbauer_i18n import available_languages, get_language, set_language, tr

# Importamos la clase base con toda la lógica de análisis y ajuste.
from mossbauer_fe33_gui_v2IA import MossbauerFe33GUI, SETTINGS_PATH, APP_NAME

from layout.manager import LayoutManager


class MossbauerApp(MossbauerFe33GUI):
    """GUI modular con paneles reubicables y layout configurable por el usuario."""

    def _build_ui(self) -> None:
        # ── 1. Tema y estilos ─────────────────────────────────────────────────
        style = ttk.Style(self)
        _saved_theme = "sv_ttk"
        try:
            if SETTINGS_PATH.exists():
                _saved_theme = json.loads(
                    SETTINGS_PATH.read_text(encoding="utf-8")
                ).get("theme", "sv_ttk")
        except Exception:
            pass
        _sv = False
        try:
            import sv_ttk
            self._sv_available = True
            if _saved_theme != "clam":
                sv_ttk.set_theme("light")
                _sv = True
        except ImportError:
            self._sv_available = False
        if not _sv:
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass
        self._sv_active = _sv
        self._theme_var.set("sv_ttk" if _sv else "clam")
        self._reconfigure_styles(style, _sv)

        # ── 2. Barra de menús ─────────────────────────────────────────────────
        self._build_menubar()

        # ── 3. Layout de paneles ──────────────────────────────────────────────
        self._layout_manager = LayoutManager(self)
        self._layout_manager.build(self)

    # ── Barra de menús (igual que el original + opción Layout) ────────────────

    def _build_menubar(self) -> None:
        menubar = tk.Menu(self)

        # Archivo
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label=tr("file.open"), command=self.open_file)
        file_menu.add_command(
            label=tr("file.web_measurements"),
            command=lambda: self.open_web_download_dialog(kind="mossbauer"),
        )
        file_menu.add_command(
            label=tr("file.web_calibrations"), command=self.open_calibration_download_dialog
        )
        file_menu.add_command(
            label=tr("file.use_as_calibration"), command=self.use_loaded_file_as_calibration
        )
        file_menu.add_separator()
        file_menu.add_command(label=tr("file.save_fit"), command=self.save_fit)
        file_menu.add_command(label=tr("file.export_report"), command=self.export_report_dialog)
        file_menu.add_separator()
        file_menu.add_command(label=tr("file.save_session"), command=self.save_session_dialog)
        file_menu.add_command(
            label=tr("file.upload_session"), command=self.open_web_upload_analysis_dialog
        )
        file_menu.add_command(label=tr("file.load_session"), command=self.load_session_dialog)
        file_menu.add_separator()
        file_menu.add_command(label=tr("file.exit"), command=self.on_close)
        menubar.add_cascade(label=tr("menu.file"), menu=file_menu)

        # Ajuste
        fit_menu = tk.Menu(menubar, tearoff=0)
        fit_menu.add_command(label=tr("fit.find_center"), command=self.auto_center)
        fit_menu.add_command(label=tr("fit.init_from_minima"), command=self.auto_guess_from_minima)
        fit_menu.add_command(label=tr("fit.auto_from_minima"), command=self.auto_fit_from_minima)
        fit_menu.add_command(label=tr("fit.ollama_start"), command=self.open_ollama_ai_dialog)
        fit_menu.add_command(label=tr("fit.run"), command=self.fit_current_data)
        fit_menu.add_command(label=tr("fit.bootstrap"), command=self.bootstrap_errors_current)
        fit_menu.add_separator()
        fit_menu.add_command(label=tr("fit.fix_all"), command=self.fix_all_parameters)
        fit_menu.add_command(label=tr("fit.free_all"), command=self.free_all_parameters)
        menubar.add_cascade(label=tr("menu.fit"), menu=fit_menu)

        # Opciones
        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_radiobutton(
            label=tr("options.discrete_sextets"),
            variable=self.fit_mode_var,
            value="discrete",
            command=self.set_fit_mode_from_menu,
        )
        options_menu.add_radiobutton(
            label=tr("options.distribution_bhf"),
            variable=self.fit_mode_var,
            value="bhf_distribution",
            command=self.set_fit_mode_from_menu,
        )
        options_menu.add_separator()
        options_menu.add_checkbutton(
            label=tr("options.show_residual"),
            variable=self.show_residual_var,
            command=self.update_plot,
        )
        options_menu.add_checkbutton(
            label=tr("options.show_legend"),
            variable=self.show_legend_var,
            command=self.update_plot,
        )
        options_menu.add_separator()
        profile_menu = tk.Menu(options_menu, tearoff=0)
        profile_menu.add_radiobutton(
            label=tr("options.profile_lorentzian"),
            variable=self.line_profile_var,
            value="Lorentziana",
            command=self.on_line_profile_change,
        )
        profile_menu.add_radiobutton(
            label=tr("options.profile_voigt"),
            variable=self.line_profile_var,
            value="Voigt",
            command=self.on_line_profile_change,
        )
        options_menu.add_cascade(label=tr("options.line_profile"), menu=profile_menu)
        options_menu.add_separator()
        options_menu.add_checkbutton(
            label=tr("options.add_sharp"),
            variable=self.dist_use_sharp_var,
            command=self.on_bhf_distribution_option_change,
        )
        options_menu.add_checkbutton(
            label=tr("options.refine_global"),
            variable=self.dist_refine_global_var,
            command=self.on_bhf_distribution_option_change,
        )
        options_menu.add_separator()
        options_menu.add_command(
            label=tr("options.constraints"), command=self.open_constraints_dialog
        )
        options_menu.add_command(
            label=tr("options.physical_presets"), command=self.open_physical_presets_dialog
        )
        options_menu.add_separator()

        # Tema
        theme_menu = tk.Menu(options_menu, tearoff=0)
        theme_menu.add_radiobutton(
            label=tr("options.theme_modern"),
            variable=self._theme_var,
            value="sv_ttk",
            command=lambda: self._switch_theme("sv_ttk"),
        )
        theme_menu.add_radiobutton(
            label=tr("options.theme_classic"),
            variable=self._theme_var,
            value="clam",
            command=lambda: self._switch_theme("clam"),
        )
        options_menu.add_cascade(label=tr("options.theme"), menu=theme_menu)

        # Layout (nueva opción)
        options_menu.add_separator()
        options_menu.add_command(
            label="Configurar layout de paneles…",
            command=self._open_layout_configurator,
        )

        menubar.add_cascade(label=tr("menu.options"), menu=options_menu)

        # Idioma
        language_menu = tk.Menu(menubar, tearoff=0)
        self._ui_language_var = tk.StringVar(value=get_language())
        for lang_code, lang_name in available_languages().items():
            language_menu.add_radiobutton(
                label=lang_name,
                variable=self._ui_language_var,
                value=lang_code,
                command=lambda code=lang_code: self.change_ui_language(code),
            )
        menubar.add_cascade(label=tr("menu.language"), menu=language_menu)

        # Ayuda
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label=tr("help.open"), command=self.show_help)
        help_menu.add_command(label=tr("help.about"), command=self.show_about)
        help_menu.add_separator()
        help_menu.add_command(label=tr("help.changelog"), command=self.show_changelog)
        help_menu.add_command(
            label=tr("help.check_updates"),
            command=lambda: self.check_for_updates(silent=False),
        )
        help_menu.add_command(
            label=tr("help.configure_updates"), command=self.open_update_settings_dialog
        )
        menubar.add_cascade(label=tr("menu.help"), menu=help_menu)

        self.config(menu=menubar)

    # ── Helpers para el layout ────────────────────────────────────────────────

    def _open_layout_configurator(self) -> None:
        if hasattr(self, "_layout_manager"):
            self._layout_manager.open_configurator()

    def _rebuild_ui(self) -> None:
        """Destruye todos los widgets hijos y reconstruye la UI.

        Sobreescribe el método original para limpiar también la referencia
        al LayoutManager antes de reconstruir.
        """
        self.config(menu=tk.Menu(self))
        for child in list(self.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        for attr in (
            "file_label", "info", "fig", "ax", "ax_res",
            "canvas", "notebook", "dist_tab", "_ui_language_var",
            "_layout_manager",
        ):
            if hasattr(self, attr):
                delattr(self, attr)
        self.vars = {}
        self.entry_vars = {}
        self.fixed_vars = {}
        self.slider_specs = {}
        self._build_ui()


def main() -> None:
    app = MossbauerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
