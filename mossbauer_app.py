"""MossbauerApp: versión modular con layout de 3 columnas configurable.

Hereda toda la lógica de MossbauerFe33GUI y sobreescribe únicamente:
  - La construcción de la UI (_build_ui) para usar el sistema de paneles.
  - Los métodos que iteran sobre componentes (1,2,3) para soportar hasta
    MAX_COMPONENTS componentes configurables por el usuario.
El fichero original queda intacto; datos, ajuste y sesiones son compatibles.
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import numpy as np

from mossbauer_i18n import available_languages, get_language, set_language, tr
from mossbauer_fe33_gui_v2IA import (
    MossbauerFe33GUI,
    SETTINGS_PATH,
    APP_NAME,
)
from core.constants import BHF_DEFAULT_T, SEXTET_PARAM_NAMES, GLOBAL_PARAM_NAMES
from core.physics import component_absorption
from layout.manager import LayoutManager
from panels.sim_panel import MAX_COMPONENTS

# Colores para hasta MAX_COMPONENTS componentes en la gráfica
_COMPONENT_COLORS = {
    1: "#16a34a",
    2: "#f97316",
    3: "#8b5cf6",
    4: "#e11d48",
    5: "#0891b2",
    6: "#ca8a04",
}


class MossbauerApp(MossbauerFe33GUI):
    """GUI modular con paneles reubicables y layout de 3 columnas."""

    # Puntos a recortar en cada extremo tras el plegado.
    # El canal extremo del array ADT suele estar semilleno (~50 % de cuentas)
    # y el canal opuesto requiere extrapolación, ambos sesgan la pendiente.
    _N_EDGE_TRIM: int = 1

    # ── Recorte de bordes tras el plegado ────────────────────────────────────

    def refold_data(self) -> None:
        super().refold_data()
        n = self._N_EDGE_TRIM
        if self.y_data is not None and self.y_data.size > 2 * n + 2:
            self.folded_raw = self.folded_raw[n:-n]
            self.pairs      = self.pairs[n:-n]
            self.y_data     = self.y_data[n:-n]
            vmax            = float(self.velocity[-1])
            self.velocity   = np.linspace(-vmax, vmax, self.y_data.size)



    def _build_ui(self) -> None:
        # n_components_var persiste entre rebuilds; se inicializa solo una vez
        if not hasattr(self, "n_components_var"):
            self.n_components_var = tk.IntVar(value=1)

        # Extender sextet_enabled, component_kind, intensity_mode, quad_treatment al máximo de componentes
        for idx in range(4, MAX_COMPONENTS + 1):
            if idx not in self.sextet_enabled:
                self.sextet_enabled[idx] = tk.BooleanVar(value=False)
            if idx not in self.component_kind:
                self.component_kind[idx] = tk.StringVar(value="Sextete")
            if idx not in self.intensity_mode:
                self.intensity_mode[idx] = tk.StringVar(value="free")
            if idx not in self.quad_treatment:
                self.quad_treatment[idx] = tk.StringVar(value="1st_order")

        # ── Tema ──────────────────────────────────────────────────────────────
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
            if _saved_theme == "sv_ttk_dark":
                sv_ttk.set_theme("dark")
                _sv = True
            elif _saved_theme != "clam":
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
        self._theme_var.set(_saved_theme if _saved_theme in ("sv_ttk", "sv_ttk_dark", "clam") else ("sv_ttk" if _sv else "clam"))
        self._reconfigure_styles(style, _sv)

        # ── Menú ──────────────────────────────────────────────────────────────
        self._build_menubar()

        # ── Layout de paneles ─────────────────────────────────────────────────
        self._layout_manager = LayoutManager(self)
        self._layout_manager.build(self)

    def _build_menubar(self) -> None:
        menubar = tk.Menu(self)

        # ── Archivo ───────────────────────────────────────────────────────────
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label=tr("file.open"), command=self.open_file)
        web_menu = tk.Menu(file_menu, tearoff=0)
        web_menu.add_command(label=tr("file.web_measurements"),
                             command=lambda: self.open_web_download_dialog(kind="mossbauer"))
        web_menu.add_command(label=tr("file.web_calibrations"),
                             command=self.open_calibration_download_dialog)
        web_menu.add_command(label=tr("file.upload_session"),
                             command=self.open_web_upload_analysis_dialog)
        file_menu.add_cascade(label=tr("file.web"), menu=web_menu)
        file_menu.add_command(label=tr("file.use_as_calibration"),
                              command=self.use_loaded_file_as_calibration)
        file_menu.add_separator()
        file_menu.add_command(label=tr("file.save_fit"),      command=self.save_fit)
        file_menu.add_command(label=tr("file.export_report"), command=self.export_report_dialog)
        file_menu.add_separator()
        file_menu.add_command(label=tr("file.save_session"),  command=self.save_session_dialog)
        file_menu.add_command(label=tr("file.load_session"),  command=self.load_session_dialog)
        file_menu.add_separator()
        file_menu.add_command(label=tr("file.exit"),          command=self.on_close)
        menubar.add_cascade(label=tr("menu.file"), menu=file_menu)

        # ── Ajuste ────────────────────────────────────────────────────────────
        fit_menu = tk.Menu(menubar, tearoff=0)
        fit_menu.add_command(label=tr("fit.run"),             command=self.fit_current_data)
        fit_menu.add_separator()
        fit_menu.add_command(label=tr("fit.find_center"),     command=self.auto_center)
        fit_menu.add_command(label=tr("fit.init_from_minima"),command=self.auto_guess_from_minima)
        fit_menu.add_command(label=tr("fit.auto_from_minima"),command=self.auto_fit_from_minima)
        fit_menu.add_command(label=tr("fit.ollama_start"),    command=self.open_ollama_ai_dialog)
        fit_menu.add_command(label=tr("fit.bootstrap"),       command=self.bootstrap_errors_current)
        fit_menu.add_separator()
        fit_menu.add_radiobutton(label=tr("options.discrete_sextets"),
                                 variable=self.fit_mode_var, value="discrete",
                                 command=self.set_fit_mode_from_menu)
        fit_menu.add_radiobutton(label=tr("options.distribution_bhf"),
                                 variable=self.fit_mode_var, value="bhf_distribution",
                                 command=self.set_fit_mode_from_menu)
        fit_menu.add_separator()
        profile_menu = tk.Menu(fit_menu, tearoff=0)
        profile_menu.add_radiobutton(label=tr("options.profile_lorentzian"),
                                     variable=self.line_profile_var, value="Lorentziana",
                                     command=self.on_line_profile_change)
        profile_menu.add_radiobutton(label=tr("options.profile_voigt"),
                                     variable=self.line_profile_var, value="Voigt",
                                     command=self.on_line_profile_change)
        fit_menu.add_cascade(label=tr("options.line_profile"), menu=profile_menu)
        likelihood_menu = tk.Menu(fit_menu, tearoff=0)
        likelihood_menu.add_radiobutton(label=tr("options.likelihood_gauss"),
                                        variable=self.likelihood_var, value="gauss")
        likelihood_menu.add_radiobutton(label=tr("options.likelihood_poisson"),
                                        variable=self.likelihood_var, value="poisson")
        fit_menu.add_cascade(label=tr("options.likelihood"), menu=likelihood_menu)
        fit_menu.add_separator()
        fit_menu.add_checkbutton(label=tr("options.add_sharp"),
                                 variable=self.dist_use_sharp_var,
                                 command=self.on_bhf_distribution_option_change)
        fit_menu.add_checkbutton(label=tr("options.refine_global"),
                                 variable=self.dist_refine_global_var,
                                 command=self.on_bhf_distribution_option_change)
        fit_menu.add_separator()
        fit_menu.add_command(label=tr("fit.free_all"), command=self.free_all_parameters)
        fit_menu.add_command(label=tr("fit.fix_all"),  command=self.fix_all_parameters)
        fit_menu.add_separator()
        fit_menu.add_command(label=tr("options.constraints"),     command=self.open_constraints_dialog)
        fit_menu.add_command(label=tr("options.physical_presets"), command=self.open_physical_presets_dialog)
        menubar.add_cascade(label=tr("menu.fit"), menu=fit_menu)

        # ── Vista ─────────────────────────────────────────────────────────────
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(label=tr("options.show_residual"),
                                  variable=self.show_residual_var, command=self.update_plot)
        view_menu.add_checkbutton(label=tr("options.show_legend"),
                                  variable=self.show_legend_var,   command=self.update_plot)
        view_menu.add_separator()
        theme_menu = tk.Menu(view_menu, tearoff=0)
        theme_menu.add_radiobutton(label=tr("options.theme_modern"),
                                   variable=self._theme_var, value="sv_ttk",
                                   command=lambda: self._switch_theme("sv_ttk"))
        theme_menu.add_radiobutton(label=tr("options.theme_dark"),
                                   variable=self._theme_var, value="sv_ttk_dark",
                                   command=lambda: self._switch_theme("sv_ttk_dark"))
        theme_menu.add_radiobutton(label=tr("options.theme_classic"),
                                   variable=self._theme_var, value="clam",
                                   command=lambda: self._switch_theme("clam"))
        view_menu.add_cascade(label=tr("options.theme"), menu=theme_menu)
        language_menu = tk.Menu(view_menu, tearoff=0)
        self._ui_language_var = tk.StringVar(value=get_language())
        for lang_code, lang_name in available_languages().items():
            language_menu.add_radiobutton(
                label=lang_name, variable=self._ui_language_var, value=lang_code,
                command=lambda code=lang_code: self.change_ui_language(code),
            )
        view_menu.add_cascade(label=tr("menu.language"), menu=language_menu)
        view_menu.add_separator()
        view_menu.add_command(label=tr("view.configure_layout"),
                              command=self._open_layout_configurator)
        menubar.add_cascade(label=tr("menu.view"), menu=view_menu)

        # ── Ayuda ─────────────────────────────────────────────────────────────
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label=tr("help.open"),             command=self.show_help)
        help_menu.add_command(label=tr("help.about"),            command=self.show_about)
        help_menu.add_separator()
        help_menu.add_command(label=tr("help.changelog"),        command=self.show_changelog)
        help_menu.add_command(label=tr("help.check_updates"),
                              command=lambda: self.check_for_updates(silent=False))
        help_menu.add_command(label=tr("help.configure_updates"),command=self.open_update_settings_dialog)
        menubar.add_cascade(label=tr("menu.help"), menu=help_menu)

        self.config(menu=menubar)

    def _rebuild_ui(self) -> None:
        self.config(menu=tk.Menu(self))
        for child in list(self.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        for attr in ("file_label", "info", "fig", "ax", "ax_res",
                     "canvas", "notebook", "dist_tab",
                     "_sim_dist_wrapper", "_sim_comp_area",
                     "_ui_language_var", "_layout_manager"):
            if hasattr(self, attr):
                delattr(self, attr)
        self.vars = {}
        self.entry_vars = {}
        self.fixed_vars = {}
        self.slider_specs = {}
        self.slider_label_widgets = {}
        self.slider_widget_refs = {}
        self._build_ui()

    def _open_layout_configurator(self) -> None:
        if hasattr(self, "_layout_manager"):
            self._layout_manager.open_configurator()

    # ── Helper: rango activo de componentes ──────────────────────────────────

    def _component_range(self) -> range:
        n = self.n_components_var.get() if hasattr(self, "n_components_var") else 3
        return range(1, n + 1)

    # ── Overrides para N componentes ─────────────────────────────────────────

    def active_param_keys(self) -> list[str]:
        keys = GLOBAL_PARAM_NAMES.copy()
        for idx in self._component_range():
            if self.sextet_enabled[idx].get():
                keys.extend(f"s{idx}_{name}" for name in self.component_param_names(idx))
        return keys

    def active_bhf_keys(self) -> list[str]:
        return [
            f"s{idx}_bhf"
            for idx in self._component_range()
            if self.sextet_enabled[idx].get()
            and self.component_kind[idx].get() == "Sextete"
        ]

    def build_components_from_vars(self):
        if not self.updating_sliders:
            # Cubre constraints lineales + derivación de textura.
            self.apply_constraints_to_vars()
        components = []
        for idx in self._component_range():
            if not self.sextet_enabled[idx].get():
                continue
            p = f"s{idx}_"
            params = np.array(
                [self.vars[p + name].get() for name in SEXTET_PARAM_NAMES], dtype=float
            )
            kind = self.component_kind[idx].get()
            extras = self.sextet_extras(idx) if kind == "Sextete" else None
            if extras is not None:
                components.append((kind, params, extras))
            else:
                components.append((kind, params))
        return components

    def component_area_percentages(
        self, values: dict[str, float] | None = None
    ) -> tuple[list[int], np.ndarray, np.ndarray]:
        active: list[int] = []
        areas: list[float] = []
        for idx in self._component_range():
            if not self.sextet_enabled[idx].get():
                continue
            pfx = f"s{idx}_"
            p = np.array(
                [
                    values.get(pfx + name, self.vars[pfx + name].get())
                    if values
                    else self.vars[pfx + name].get()
                    for name in SEXTET_PARAM_NAMES
                ],
                dtype=float,
            )
            area = max(0.0, self.component_area_from_params(self.component_kind[idx].get(), p))
            active.append(idx)
            areas.append(area)
        area_arr = np.array(areas, dtype=float)
        total = float(np.sum(area_arr))
        pct = 100.0 * area_arr / total if total > 0 else np.zeros_like(area_arr)
        return active, area_arr, pct

    def update_plot(self) -> None:
        if self.fit_mode_var.get() == "bhf_distribution":
            self.update_plot_bhf_distribution()
            return
        c = self._plot_theme()
        self.fig.clear()
        show_residual = self.show_residual_var.get()
        if show_residual:
            gs = self.fig.add_gridspec(2, 1, height_ratios=[4.8, 1.05], hspace=0.08)
            self.ax = self.fig.add_subplot(gs[0])
            self.ax_res = self.fig.add_subplot(gs[1], sharex=self.ax)
        else:
            self.ax = self.fig.add_subplot(111)
            self.ax_res = None

        self.fig.set_facecolor(c["fig_bg"])
        self.ax.set_facecolor(c["ax_bg"])
        self.ax.set_title(tr("plot.title_discrete"), color=c["title"], pad=10, fontweight="bold")
        self.ax.set_ylabel(tr("plot.transmission_ylabel"))
        self.ax.yaxis.label.set_color(c["lbl"])
        self.ax.grid(True, color=c["grid"], alpha=c["grid_alpha"], linewidth=0.8)
        self.ax.tick_params(colors=c["tick"])
        for spine in self.ax.spines.values():
            spine.set_color(c["spine"])

        if self.ax_res is not None:
            self.ax_res.set_facecolor(c["res_bg"])
            self.ax_res.set_ylabel(tr("plot.residual_ylabel"))
            self.ax_res.set_xlabel(tr("plot.velocity_xlabel"))
            self.ax_res.yaxis.label.set_color(c["lbl"])
            self.ax_res.xaxis.label.set_color(c["lbl"])
            self.ax_res.grid(True, color=c["res_grid"], alpha=0.8, linewidth=0.75)
            self.ax_res.tick_params(colors=c["res_tick"])
            for spine in self.ax_res.spines.values():
                spine.set_color(c["res_spine"])
        else:
            self.ax.set_xlabel(tr("plot.velocity_xlabel"))
            self.ax.xaxis.label.set_color(c["lbl"])

        if self.velocity is not None and self.y_data is not None:
            model = self.current_model()
            self.ax.plot(self.velocity, self.y_data, ".", color=c["data"],
                         ms=4, alpha=0.88, label=tr("plot.legend_data"))
            if model is not None:
                baseline_line = (
                    self.vars["baseline"].get() + self.vars["slope"].get() * self.velocity
                )
                self.ax.plot(self.velocity, baseline_line, ":", color=c["baseline"],
                             lw=1.35, label=tr("plot.legend_baseline"))

                for idx in self._component_range():
                    if not self.sextet_enabled[idx].get():
                        continue
                    p = f"s{idx}_"
                    params = np.array(
                        [self.vars[p + name].get() for name in SEXTET_PARAM_NAMES], dtype=float
                    )
                    kind = self.component_kind[idx].get()
                    extras = self.sextet_extras(idx) if kind == "Sextete" else None
                    comp_line = baseline_line - component_absorption(self.velocity, kind, params, extras=extras)
                    color = _COMPONENT_COLORS.get(idx, "#888888")
                    self.ax.plot(
                        self.velocity, comp_line, "--",
                        color=color, lw=1.65, alpha=0.95,
                        label=f"{tr(f'kind.{kind}', default=kind)} {idx}",
                    )

                self.ax.plot(self.velocity, model, "-", color=c["model"],
                             lw=2.6, label=tr("plot.legend_model"))
                residual = self.y_data - model
                rms = float(np.sqrt(np.mean(residual ** 2)))
                if self.ax_res is not None:
                    self.ax_res.axhline(0, color=c["res_zero"], lw=0.9, alpha=0.9)
                    self.ax_res.fill_between(self.velocity, residual, 0,
                                             color=c["res_fill"], alpha=0.22)
                    self.ax_res.plot(self.velocity, residual, "-",
                                     color=c["res_line"], lw=1.25)
                    lim = max(float(np.nanmax(np.abs(residual))) * 1.18, 1e-6)
                    self.ax_res.set_ylim(-lim, lim)
                    self.ax.tick_params(labelbottom=False)
            else:
                rms = float("nan")
            if self.show_legend_var.get():
                leg = self.ax.legend(loc="best", frameon=True, facecolor=c["leg_face"],
                                     edgecolor=c["leg_edge"], framealpha=0.85)
                leg.set_draggable(True)
                for text in leg.get_texts():
                    text.set_color(c["leg_text"])
            self.update_info(rms)
        else:
            self.ax.text(0.5, 0.5, tr("plot.no_file"), transform=self.ax.transAxes,
                         ha="center", va="center", color=c["no_file"],
                         fontsize=14, fontweight="bold")
        self.fig.tight_layout()
        self.canvas.draw_idle()

    def update_info(self, rms: float) -> None:
        if not hasattr(self, "info") or self.counts is None or self.folded_raw is None:
            return
        center = self.vars["center"].get()
        active = [idx for idx in self._component_range() if self.sextet_enabled[idx].get()]
        fixed  = [k for k in self.active_param_keys() if self.fixed_vars[k].get()]
        pct_active, areas, percentages = self.component_area_percentages()
        pct_errors = self.component_percentage_errors()
        text = [
            tr("info.file", name=self.file_path.name if self.file_path else "-"),
            tr("info.channels_read", n=self.counts.size),
            tr("info.folding_center", center=f"{center:.5f}"),
            tr("info.folding_normos", value=f"{2.0 * center:.5f}"),
            tr("info.folded_pairs", n=len(self.pairs)),
            tr("info.normalization", factor=f"{self.norm_factor:.6g}"),
            tr("info.vmax",      value=f"{self.vars['vmax'].get():.6g}"),
            tr("info.baseline",  value=f"{self.vars['baseline'].get():.6g}"),
            tr("info.slope",     value=f"{self.vars['slope'].get():.6g}"),
            tr("info.active_sextets", list=", ".join(map(str, active))),
            tr("info.fit_velocity_yes") if self.fit_velocity_var.get() else tr("info.fit_velocity_no"),
            tr("info.rms", value=f"{rms:.6g}"),
        ]
        stats = self.last_fit_stats
        if stats:
            text.extend([
                tr("info.chi2_line",
                   red_chi2=f"{stats.get('red_chi2', float('nan')):.6g}",
                   chi2=f"{stats.get('chi2', float('nan')):.6g}",
                   dof=f"{stats.get('dof', float('nan')):.0f}"),
                tr("info.aic_bic_line",
                   aic=f"{stats.get('aic', float('nan')):.6g}",
                   bic=f"{stats.get('bic', float('nan')):.6g}",
                   n_params=f"{stats.get('n_params', float('nan')):.0f}"),
                tr("info.residual_diag",
                   lag1=f"{stats.get('resid_lag1', float('nan')):.3f}",
                   z=f"{stats.get('resid_runs_z', float('nan')):.3f}",
                   antisym=f"{stats.get('resid_antisym_corr', float('nan')):.3f}"),
                tr("info.model_comparison"),
                tr("info.multistart_count", n=f"{stats.get('n_starts', 1.0):.0f}"),
            ])
            if (abs(stats.get("resid_lag1", 0.0)) > 0.35
                    or abs(stats.get("resid_runs_z", 0.0)) > 2.0
                    or stats.get("resid_antisym_corr", 0.0) > 0.45):
                text.extend([tr("info.residual_warning_1"), tr("info.residual_warning_2")])
        cal_unc = self.calibration_uncertainty_text()
        if cal_unc:
            text.append(cal_unc)
        corr = self.last_fit_correlations
        if corr:
            max_pair = corr.get("max_pair") or []
            if max_pair:
                text.append(tr("info.max_correlation",
                               value=f"{float(corr.get('max_abs_corr', 0.0)):.3f}",
                               p1=max_pair[0], p2=max_pair[1]))
            high_pairs = corr.get("high_pairs") or []
            if high_pairs:
                text.append(tr("info.correlation_warning"))
                for pair in high_pairs[:6]:
                    text.append(f"  {pair['param1']} ↔ {pair['param2']}: r={float(pair['corr']):.3f}")
                if len(high_pairs) > 6:
                    text.append(tr("info.correlation_more", n=len(high_pairs) - 6))
        text.append("")
        if len(pct_active) > 1:
            text.append(tr("info.area_percent_header"))
            for idx, area, pct in zip(pct_active, areas, percentages):
                err = pct_errors.get(idx)
                err_txt = f" ± {err:.3g}%" if err is not None else ""
                kind_disp = tr(f"kind.{self.component_kind[idx].get()}",
                               default=self.component_kind[idx].get())
                text.append(tr("info.component_percent_line",
                               idx=idx, kind=kind_disp, pct=pct, err_txt=err_txt, area=area))
            text.append("")
        for idx in active:
            p = f"s{idx}_"
            i3_real  = self.vars[p + "int3"].get()
            i2_real  = i3_real * self.vars[p + "int2"].get()
            i1_real  = i3_real * self.vars[p + "int1"].get()
            g1 = self.vars[p + "gamma1"].get()
            g2 = g1 * self.vars[p + "gamma2"].get()
            g3 = g1 * self.vars[p + "gamma3"].get()
            f1, f2, f3 = 2.0 * g1, 2.0 * g2, 2.0 * g3
            kind_disp = tr(f"kind.{self.component_kind[idx].get()}",
                           default=self.component_kind[idx].get())
            text.extend([
                tr("info.component_params_line", kind=kind_disp, idx=idx,
                   bhf=self.vars[p + "bhf"].get(),
                   delta=self.vars[p + "delta"].get(),
                   quad=self.vars[p + "quad"].get()),
                tr("info.gamma_hwhm",       g1=g1, g2=g2, g3=g3),
                tr("info.fwhm_equiv",       f1=f1, f2=f2, f3=f3),
                tr("info.gamma_rel",        gamma2=self.vars[p + "gamma2"].get(),
                                            gamma3=self.vars[p + "gamma3"].get()),
                tr("info.depth_intensities",depth=self.vars[p + "depth"].get(),
                                            i1=i1_real, i2=i2_real, i3=i3_real),
            ])
        text.extend(["", tr("info.fixed_line",
                             fixed=", ".join(fixed) if fixed else tr("info.none"))])
        cons = self.enabled_constraints()
        if cons:
            text.append("")
            text.append(tr("info.constraints_header"))
            for c in cons:
                text.append(tr("info.constraint_line",
                               target=c["target"], factor=float(c.get("factor", 1.0)),
                               source=c["source"],  offset=float(c.get("offset", 0.0))))
        self.info.delete("1.0", tk.END)
        self.info.insert(tk.END, "\n".join(text))

    # ── Visibilidad del panel de distribución BHF ───────────────────────────

    def _refresh_distribution_tab_visibility(self, update: bool = True) -> None:
        if hasattr(self, "refresh_dist_slider_labels"):
            self.refresh_dist_slider_labels()
        nb        = getattr(self, "notebook",          None)
        dist_tab  = getattr(self, "dist_tab",          None)
        wrapper   = getattr(self, "_sim_dist_wrapper", None)
        comp_area = getattr(self, "_sim_comp_area",    None)
        dist_on   = self.fit_mode_var.get() == "bhf_distribution"

        if nb is not None and dist_tab is not None:
            # Modo pestañas: el frame apilado siempre oculto (distribución va en pestaña)
            if wrapper is not None and wrapper.winfo_exists() and wrapper.winfo_ismapped():
                wrapper.pack_forget()
            if dist_on:
                if str(dist_tab) not in nb.tabs():
                    nb.insert(0, dist_tab, text=tr("tab.distribution_bhf"))
                nb.select(dist_tab)
            else:
                if str(dist_tab) in nb.tabs():
                    nb.forget(dist_tab)
        elif wrapper is not None and wrapper.winfo_exists():
            # Modo apilado: mostrar u ocultar el frame de distribución
            if dist_on:
                if not wrapper.winfo_ismapped():
                    try:
                        if comp_area and comp_area.winfo_exists() and comp_area.winfo_ismapped():
                            wrapper.pack(fill=tk.X, before=comp_area)
                        else:
                            wrapper.pack(fill=tk.X)
                    except tk.TclError:
                        wrapper.pack(fill=tk.X)
            else:
                if wrapper.winfo_ismapped():
                    wrapper.pack_forget()

        if update:
            self.update_plot()

    # ── Pendiente: límites ampliados ─────────────────────────────────────────

    def bounds_for_key(self, key: str) -> tuple[float, float]:
        if key == "slope":
            return (-0.005, 0.005)
        return super().bounds_for_key(key)

    def auto_guess_from_minima(self, fit_after: bool = False) -> None:
        """Como el original, pero con límite de pendiente ±0.005 y hasta MAX_COMPONENTS."""
        if self.velocity is None or self.y_data is None:
            return
        peaks, baseline, slope = self.detect_absorption_minima()
        if not peaks:
            messagebox.showinfo(tr("msg.auto_minima_title"), tr("msg.auto_minima_none"))
            return

        self.fit_mode_var.set("discrete")
        self.set_fit_mode_from_menu()
        params: dict[str, float] = {
            "baseline": baseline,
            "slope": float(np.clip(slope, -0.005, 0.005)),
        }
        for idx in range(1, MAX_COMPONENTS + 1):
            if idx > 1:
                self.sextet_enabled[idx].set(False)
            pfx = f"s{idx}_"
            params.update({
                pfx + "delta": 0.0, pfx + "quad": 0.0, pfx + "bhf": BHF_DEFAULT_T,
                pfx + "gamma1": 0.20, pfx + "gamma2": 1.0, pfx + "gamma3": 1.0,
                pfx + "depth": 0.005, pfx + "int1": 3.0, pfx + "int2": 2.0, pfx + "int3": 1.0,
            })

        components: list[tuple[int, str, list[dict[str, float]]]] = []
        used_ids: set[int] = set()
        sext = self._best_sextet_from_peaks(peaks)
        if sext is not None:
            sub, delta, bhf, width, depth = sext
            if len(sub) >= 5 and abs(sub[-1]["pos"] - sub[0]["pos"]) > 3.0:
                components.append((1, "Sextete", sub))
                params["s1_delta"]  = float(np.clip(delta, -2.5, 2.5))
                params["s1_bhf"]    = float(np.clip(bhf, 20.0, 50.0))
                params["s1_quad"]   = 0.0
                params["s1_gamma1"] = float(np.clip(width / 2.0, 0.04, 1.0))
                params["s1_depth"]  = float(np.clip(depth, 0.002, 0.25))
                used_ids.update(int(pk["i"]) for pk in sub)

        remaining = [
            pk for pk in sorted(peaks, key=lambda q: q["smooth_depth"], reverse=True)
            if int(pk["i"]) not in used_ids
        ]
        next_idx = 2 if components else 1
        while next_idx <= MAX_COMPONENTS and remaining:
            # Intentar otro sexteto antes de caer en doblete/singlete.
            # Con ≥4 picos también se intenta dividir picos anchos/profundos que
            # puedan ser dos líneas solapadas (6+5→6+6, 6+4→6+6).
            if len(remaining) >= 4:
                sext_extra = self._best_sextet_from_peaks(remaining)
                if sext_extra is None:
                    sext_extra = self._try_split_peaks_for_sextet(remaining)
                if sext_extra is not None:
                    sub_e, delta_e, bhf_e, width_e, depth_e = sext_extra
                    if len(sub_e) >= 5 and abs(sub_e[-1]["pos"] - sub_e[0]["pos"]) > 3.0:
                        pfx = f"s{next_idx}_"
                        if next_idx > 1:
                            self.sextet_enabled[next_idx].set(True)
                        components.append((next_idx, "Sextete", sub_e))
                        params[pfx + "delta"]  = float(np.clip(delta_e, -2.5, 2.5))
                        params[pfx + "bhf"]    = float(np.clip(bhf_e, 20.0, 50.0))
                        params[pfx + "quad"]   = 0.0
                        params[pfx + "gamma1"] = float(np.clip(width_e / 2.0, 0.04, 1.0))
                        params[pfx + "depth"]  = float(np.clip(depth_e, 0.002, 0.25))
                        sub_ids = {int(pk["i"]) for pk in sub_e}
                        remaining = [pk for pk in remaining if int(pk["i"]) not in sub_ids]
                        next_idx += 1
                        continue

            # Con exactamente 2 picos restantes y un sexteto ya colocado, intentar
            # identificar las líneas exteriores adyacentes de un segundo sexteto.
            if len(remaining) == 2 and next_idx > 1:
                sext_2pk = self._try_2peak_sextet_estimate(remaining)
                if sext_2pk is not None:
                    sub_2, delta_2, bhf_2, width_2, depth_2 = sext_2pk
                    pfx = f"s{next_idx}_"
                    if next_idx > 1:
                        self.sextet_enabled[next_idx].set(True)
                    components.append((next_idx, "Sextete", sub_2))
                    params[pfx + "delta"]  = float(np.clip(delta_2, -2.5, 2.5))
                    params[pfx + "bhf"]    = float(np.clip(bhf_2, 20.0, 60.0))
                    params[pfx + "quad"]   = 0.0
                    params[pfx + "gamma1"] = float(np.clip(width_2 / 2.0, 0.04, 1.0))
                    params[pfx + "depth"]  = float(np.clip(depth_2, 0.001, 0.25))
                    remaining = []
                    next_idx += 1
                    continue

            if len(remaining) >= 2:
                pair = sorted(remaining[:2], key=lambda pk: pk["pos"])
                sep = abs(pair[1]["pos"] - pair[0]["pos"])
                if 0.18 <= sep <= 4.0:
                    kind = "Doblete"
                    group = pair
                    remaining = [pk for pk in remaining if pk not in pair]
                else:
                    kind = "Singlete"
                    group = [remaining.pop(0)]
            else:
                kind = "Singlete"
                group = [remaining.pop(0)]
            components.append((next_idx, kind, group))
            pfx = f"s{next_idx}_"
            if next_idx > 1:
                self.sextet_enabled[next_idx].set(True)
            if kind == "Doblete":
                g = sorted(group, key=lambda pk: pk["pos"])
                params[pfx + "delta"]  = float(np.mean([g[0]["pos"], g[1]["pos"]]))
                params[pfx + "quad"]   = float(abs(g[1]["pos"] - g[0]["pos"]))
                params[pfx + "gamma1"] = float(np.clip(np.mean([x["width"] for x in g]) / 2.0, 0.04, 1.0))
                params[pfx + "gamma2"] = 1.0
                params[pfx + "depth"]  = float(np.clip(np.mean([x["depth"] for x in g]), 0.002, 0.25))
                params[pfx + "int1"]   = 1.0
                params[pfx + "int2"]   = 1.0
            else:
                pk = group[0]
                params[pfx + "delta"]  = float(pk["pos"])
                params[pfx + "gamma1"] = float(np.clip(pk["width"] / 2.0, 0.04, 1.0))
                params[pfx + "depth"]  = float(np.clip(pk["depth"], 0.002, 0.25))
                params[pfx + "int1"]   = 1.0
            next_idx += 1

        if not components:
            pk = max(peaks, key=lambda p: p["depth"])
            components.append((1, "Singlete", [pk]))
            params["s1_delta"]  = float(pk["pos"])
            params["s1_gamma1"] = float(np.clip(pk["width"] / 2.0, 0.04, 1.0))
            params["s1_depth"]  = float(np.clip(pk["depth"], 0.002, 0.25))

        # Adjust n_components_var to match detected components
        if hasattr(self, "n_components_var") and components:
            n_detected = max(i for i, _k, _g in components)
            self.n_components_var.set(min(n_detected, MAX_COMPONENTS))

        for idx in range(1, MAX_COMPONENTS + 1):
            found = next((k for i, k, _g in components if i == idx), "Sextete")
            self.component_kind[idx].set(found)
            if idx > 1 and not any(i == idx for i, _k, _g in components):
                self.sextet_enabled[idx].set(False)
        self.set_params(params)
        for idx, kind, _group in components:
            self.on_component_kind_change(idx)
        for key in self.active_param_keys():
            if key in self.fixed_vars:
                self.fixed_vars[key].set(False)
        self.update_plot()
        resumen = ", ".join(
            tr("text.component_kind_label", idx=idx, kind=tr(f"kind.{kind}", default=kind))
            for idx, kind, _g in components
        )
        if fit_after:
            self.fit_current_data()
        else:
            messagebox.showinfo(
                tr("msg.auto_minima_title"),
                tr("msg.auto_minima_detected", n=len(peaks), summary=resumen),
            )

    # ── Persistencia (incluye n_components) ──────────────────────────────────

    def settings_payload(self) -> dict:
        data = super().settings_payload()
        data["n_components"] = self.n_components_var.get() if hasattr(self, "n_components_var") else 1
        return data

    def _apply_state_payload(self, data: dict, restore_geometry: bool = True) -> None:
        super()._apply_state_payload(data, restore_geometry)
        if hasattr(self, "n_components_var") and "n_components" in data:
            self.n_components_var.set(int(data["n_components"]))


def main() -> None:
    app = MossbauerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
