"""Panel de simulación/ajuste: controles de modo, botones y pestañas de componentes."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from mossbauer_i18n import tr
from core.constants import BHF_DEFAULT_T
from .base import BasePanel


class SimPanel(BasePanel):
    """Área inferior derecha con cabecera de modo de ajuste, botones y notebook."""

    PANEL_ID = "sim_controls"
    PANEL_NAME = "Controles de ajuste"

    def build(self, parent: tk.Widget) -> tk.Widget:
        app = self.app

        sim_box = ttk.LabelFrame(
            parent, text=tr("controls.simulation_box"), style="Section.TLabelframe"
        )

        # ── Cabecera con botones ───────────────────────────────────────────────
        sim_header = ttk.Frame(sim_box)
        sim_header.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(sim_header, text=tr("controls.fit_mode_hint"), style="Subtitle.TLabel").pack(
            side=tk.LEFT, anchor=tk.W
        )
        ttk.Button(
            sim_header, text=tr("sim.fit"), command=app.fit_current_data, style="Accent.TButton"
        ).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(
            sim_header, text=tr("sim.ai_start"), command=app.open_ollama_ai_dialog, style="Small.TButton"
        ).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(
            sim_header, text=tr("sim.auto_minima"), command=app.auto_fit_from_minima, style="Small.TButton"
        ).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(
            sim_header, text=tr("sim.fix_all"), command=app.fix_all_parameters, style="Small.TButton"
        ).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(
            sim_header, text=tr("sim.free_all"), command=app.free_all_parameters, style="Small.TButton"
        ).pack(side=tk.RIGHT, padx=(4, 0))

        # ── Notebook con pestaña de distribución + 3 de componentes ──────────
        notebook = ttk.Notebook(sim_box)
        notebook.pack(fill=tk.X, expand=False)
        app.notebook = notebook

        self._build_distribution_tab(notebook)
        self._build_component_tabs(notebook)

        app._refresh_distribution_tab_visibility(update=False)

        self._root = sim_box
        return sim_box

    # ── Pestaña de distribución BHF ───────────────────────────────────────────

    def _build_distribution_tab(self, notebook: ttk.Notebook) -> None:
        app = self.app
        dist_tab = ttk.Frame(notebook, padding=6)
        app.dist_tab = dist_tab
        notebook.add(dist_tab, text=tr("tab.distribution_bhf"))

        dist_top = ttk.Frame(dist_tab)
        dist_top.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(dist_top, text=tr("bhf.description"), style="Subtitle.TLabel").pack(
            side=tk.LEFT, anchor=tk.W
        )

        dist_cols = ttk.Frame(dist_tab)
        dist_cols.pack(fill=tk.X)
        d1 = ttk.Frame(dist_cols)
        d2 = ttk.Frame(dist_cols)
        d3 = ttk.Frame(dist_cols)
        d1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        d2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        d3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        # Columna 1
        ttk.Label(d1, text=tr("bhf.variable_label")).pack(anchor=tk.W)
        dist_var_box = ttk.Combobox(
            d1, textvariable=app.dist_variable_var, values=("BHF", "ΔEQ"), width=10, state="readonly"
        )
        dist_var_box.pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
        dist_var_box.bind("<<ComboboxSelected>>", lambda _e: app.on_bhf_distribution_option_change())

        ttk.Label(d1, text=tr("bhf.shape_label")).pack(anchor=tk.W)
        dist_shape_box = ttk.Combobox(
            d1,
            textvariable=app.dist_shape_var,
            values=("Histograma", "Gaussiana", "Binomial", "Fija"),
            width=12,
            state="readonly",
        )
        dist_shape_box.pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
        dist_shape_box.bind("<<ComboboxSelected>>", lambda _e: app.on_bhf_distribution_option_change())

        ttk.Button(
            d1, text=tr("bhf.load_fixed"), command=app.load_fixed_distribution_file, style="Small.TButton"
        ).pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
        self._add_slider(d1, "dist_delta", tr("slider.dist_delta"), 0.0, -2.5, 2.5, 0.001, fit_param=False)
        self._add_slider(d1, "dist_quad", tr("slider.dist_quad"), 0.0, -4.0, 4.0, 0.001, fit_param=False)
        self._add_slider(
            d1, "dist_fixed_bhf", tr("slider.dist_fixed_bhf"), BHF_DEFAULT_T, 0.0, 60.0, 0.01, fit_param=False
        )
        self._add_slider(d1, "dist_gamma", tr("slider.dist_gamma"), 0.18, 0.03, 1.0, 0.001, fit_param=False)

        # Columna 2
        self._add_slider(d2, "dist_bmin", tr("slider.dist_bmin"), 0.0, 0.0, 60.0, 0.1, fit_param=False)
        self._add_slider(d2, "dist_bmax", tr("slider.dist_bmax"), 50.0, 1.0, 60.0, 0.1, fit_param=False)
        self._add_slider(d2, "dist_nbins", tr("slider.dist_nbins"), 50.0, 10.0, 100.0, 1.0, fit_param=False)

        # Columna 3
        self._add_slider(
            d3, "dist_log_alpha", tr("slider.dist_log_alpha"), -2.0, -8.0, 4.0, 0.1, fit_param=False
        )
        alpha_buttons = ttk.Frame(d3)
        alpha_buttons.pack(fill=tk.X, pady=(0, 2))
        ttk.Button(
            alpha_buttons, text=tr("bhf.alpha_fine"),
            command=lambda: app.set_bhf_alpha_preset(-5.0), style="Small.TButton"
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(
            alpha_buttons, text=tr("bhf.alpha_medium"),
            command=lambda: app.set_bhf_alpha_preset(-2.0), style="Small.TButton"
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(
            alpha_buttons, text=tr("bhf.alpha_smooth"),
            command=lambda: app.set_bhf_alpha_preset(1.0), style="Small.TButton"
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))
        ttk.Checkbutton(
            d3, text=tr("bhf.use_sharp"), variable=app.dist_use_sharp_var,
            command=app.on_bhf_distribution_option_change
        ).pack(anchor=tk.W, pady=(2, 0))
        ttk.Checkbutton(
            d3, text=tr("bhf.refine_global"), variable=app.dist_refine_global_var,
            command=app.on_bhf_distribution_option_change
        ).pack(anchor=tk.W, pady=(0, 2))
        ttk.Button(
            d3, text=tr("bhf.lcurve_alpha"), command=app.scan_bhf_alpha_gui, style="Small.TButton"
        ).pack(anchor=tk.E, fill=tk.X, pady=(2, 0))

    # ── Pestañas de componentes (×3) ──────────────────────────────────────────

    def _build_component_tabs(self, notebook: ttk.Notebook) -> None:
        app = self.app
        for idx in (1, 2, 3):
            tab = ttk.Frame(notebook, padding=6)
            notebook.add(tab, text=tr("tab.component", idx=idx))

            top_row = ttk.Frame(tab)
            top_row.pack(fill=tk.X, pady=(0, 4))
            if idx > 1:
                ttk.Checkbutton(
                    top_row,
                    text=tr("component.enable", idx=idx),
                    variable=app.sextet_enabled[idx],
                    command=app.on_component_activation_change,
                ).pack(side=tk.LEFT)
            else:
                ttk.Label(
                    top_row, text=tr("component.main_active"), style="Subtitle.TLabel"
                ).pack(side=tk.LEFT)
            ttk.Label(top_row, text=tr("component.shape_label")).pack(side=tk.LEFT, padx=(18, 4))
            kind_box = ttk.Combobox(
                top_row,
                textvariable=app.component_kind[idx],
                values=("Sextete", "Doblete", "Singlete"),
                width=10,
                state="readonly",
            )
            kind_box.pack(side=tk.LEFT)
            kind_box.bind("<<ComboboxSelected>>", lambda _e, i=idx: app.on_component_kind_change(i))

            cols = ttk.Frame(tab)
            cols.pack(fill=tk.X)
            c1 = ttk.Frame(cols)
            c2 = ttk.Frame(cols)
            c3 = ttk.Frame(cols)
            c1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
            c2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
            c3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

            p = f"s{idx}_"
            self._add_slider(c1, p + "delta", tr("slider.s_delta"), 0.0, -2.0, 3.0, 0.001)
            self._add_slider(c1, p + "quad", tr("slider.s_quad"), 0.0, -4.0, 4.0, 0.001)
            self._add_slider(c1, p + "bhf", tr("slider.s_bhf"), BHF_DEFAULT_T, 0.0, 60.0, 0.01)
            self._add_slider(c2, p + "gamma1", tr("slider.s_gamma1"), 0.30, 0.03, 2.0, 0.001)
            self._add_slider(c2, p + "gamma2", tr("slider.s_gamma2"), 1.0, 0.2, 3.0, 0.001)
            self._add_slider(c2, p + "gamma3", tr("slider.s_gamma3"), 1.0, 0.2, 3.0, 0.001)
            self._add_slider(
                c3, p + "depth", tr("slider.s_depth"), 0.030 if idx == 1 else 0.005, 0.0, 0.30, 0.0005
            )
            self._add_slider(c3, p + "int1", tr("slider.s_int1"), 1.0, 0.0, 2.0, 0.001)
            self._add_slider(c3, p + "int2", tr("slider.s_int2"), 1.0, 0.0, 3.0, 0.001)
            self._add_slider(c3, p + "int3", tr("slider.s_int3"), 1.0, 0.0, 3.0, 0.001)
