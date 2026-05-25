"""Panel de simulación/ajuste: cabecera, N componentes dinámicos y distribución BHF.

Layout adaptativo basado en la altura de la ventana:
  - Si hay espacio suficiente: componentes apilados verticalmente.
  - Si no caben (la ventana es demasiado baja): pestañas de notebook.
Los sliders de cada componente se distribuyen en 2 columnas que se adaptan
al ancho del panel.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from mossbauer_i18n import tr
from core.constants import BHF_DEFAULT_T
from .base import BasePanel

if TYPE_CHECKING:
    from mossbauer_app import MossbauerApp

MAX_COMPONENTS = 6

# Altura estimada por componente en modo apilado (2 col × 5 sliders × ~52 px + cabecera)
_COMP_H = 315
# Coste fijo: botones + spinbox + wrapper distribución + márgenes de LabelFrame
_OVERHEAD_H = 110


class SimPanel(BasePanel):
    """Área de simulación/ajuste con número de componentes configurable (1-6)."""

    PANEL_ID = "sim_controls"
    PANEL_NAME = "Controles de ajuste"

    def __init__(self, app: "MossbauerApp") -> None:
        super().__init__(app)
        self._comp_tabs: dict[int, tk.Widget] = {}
        self._comp_notebook: ttk.Notebook | None = None
        self._comp_area: ttk.Frame | None = None
        self._using_tabs: bool = False
        self._layout_timer: str | None = None

    # ── build ─────────────────────────────────────────────────────────────────

    def build(self, parent: tk.Widget) -> tk.Widget:
        app = self.app

        sim_box = ttk.LabelFrame(
            parent, text=tr("controls.simulation_box"), style="Section.TLabelframe"
        )

        # ── Cabecera: botones de acción ───────────────────────────────────────
        hdr = ttk.Frame(sim_box)
        hdr.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(hdr, text=tr("controls.fit_mode_hint"), style="Subtitle.TLabel").pack(
            side=tk.LEFT, anchor=tk.W
        )
        ttk.Button(hdr, text=tr("sim.fit"), command=app.fit_current_data,
                   style="Accent.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(hdr, text=tr("sim.ai_start"), command=app.open_ollama_ai_dialog,
                   style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(hdr, text=tr("sim.auto_minima"), command=app.auto_fit_from_minima,
                   style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(hdr, text=tr("sim.fix_all"), command=app.fix_all_parameters,
                   style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(hdr, text=tr("sim.free_all"), command=app.free_all_parameters,
                   style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))

        # ── Selector de número de componentes ─────────────────────────────────
        ncomp_row = ttk.Frame(sim_box)
        ncomp_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(ncomp_row, text=tr("sim.n_components", default="Componentes:")).pack(
            side=tk.LEFT
        )
        ttk.Spinbox(
            ncomp_row,
            from_=1, to=MAX_COMPONENTS, increment=1,
            textvariable=app.n_components_var,
            width=4, state="readonly",
            command=self._on_n_components_change,
        ).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(ncomp_row, text=f"(máx. {MAX_COMPONENTS})",
                  foreground="#64748b", font=("TkDefaultFont", 8)).pack(side=tk.LEFT)

        # ── Distribución BHF ──────────────────────────────────────────────────
        # Wrapper siempre empaquetado; el notebook interior aparece/desaparece
        # según el modo (discreto vs. distribución) sin alterar el orden del layout.
        dist_wrapper = ttk.Frame(sim_box)
        dist_wrapper.pack(fill=tk.X)
        app._sim_dist_wrapper = dist_wrapper

        notebook = ttk.Notebook(dist_wrapper)
        self._notebook = notebook
        app.notebook = notebook

        dist_tab = ttk.Frame(notebook, padding=6)
        app.dist_tab = dist_tab
        notebook.add(dist_tab, text=tr("tab.distribution_bhf"))
        self._build_distribution_tab(dist_tab)

        # ── Área de componentes (modo determinado tras el primer render) ───────
        comp_area = ttk.Frame(sim_box)
        comp_area.pack(fill=tk.X)
        self._comp_area = comp_area

        self._build_stacked(comp_area)

        app._refresh_distribution_tab_visibility(update=False)

        # Comprobar modo inicial una vez que la ventana esté renderizada
        sim_box.after(400, self._check_layout)

        self._root = sim_box
        return sim_box

    # ── Distribución BHF ─────────────────────────────────────────────────────

    def _build_distribution_tab(self, dist_tab: ttk.Frame) -> None:
        app = self.app
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

        self._add_slider(d1, "dist_delta",     tr("slider.dist_delta"),     0.0,          -2.5, 2.5,  0.001, fit_param=False)
        self._add_slider(d1, "dist_quad",      tr("slider.dist_quad"),      0.0,          -4.0, 4.0,  0.001, fit_param=False)
        self._add_slider(d1, "dist_fixed_bhf", tr("slider.dist_fixed_bhf"), BHF_DEFAULT_T, 0.0, 60.0, 0.01,  fit_param=False)
        self._add_slider(d1, "dist_gamma",     tr("slider.dist_gamma"),     0.18,         0.03, 1.0,  0.001, fit_param=False)
        ttk.Label(d1, text=tr("bhf.variable_label")).pack(anchor=tk.W)
        dv = ttk.Combobox(d1, textvariable=app.dist_variable_var,
                          values=("BHF", "ΔEQ"), width=10, state="readonly")
        dv.pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
        dv.bind("<<ComboboxSelected>>", lambda _e: app.on_bhf_distribution_option_change())
        ttk.Label(d1, text=tr("bhf.shape_label")).pack(anchor=tk.W)
        ds = ttk.Combobox(d1, textvariable=app.dist_shape_var,
                          values=("Histograma", "Gaussiana", "Binomial", "Fija"),
                          width=12, state="readonly")
        ds.pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
        ds.bind("<<ComboboxSelected>>", lambda _e: app.on_bhf_distribution_option_change())
        ttk.Button(d1, text=tr("bhf.load_fixed"), command=app.load_fixed_distribution_file,
                   style="Small.TButton").pack(anchor=tk.W, fill=tk.X, pady=(0, 4))

        self._add_slider(d2, "dist_bmin",  tr("slider.dist_bmin"),  0.0,  0.0,  60.0, 0.1,  fit_param=False)
        self._add_slider(d2, "dist_bmax",  tr("slider.dist_bmax"),  50.0, 1.0,  60.0, 0.1,  fit_param=False)
        self._add_slider(d2, "dist_nbins", tr("slider.dist_nbins"), 50.0, 10.0, 100.0, 1.0, fit_param=False)

        self._add_slider(d3, "dist_log_alpha", tr("slider.dist_log_alpha"), -2.0, -8.0, 4.0, 0.1, fit_param=False)
        ab = ttk.Frame(d3)
        ab.pack(fill=tk.X, pady=(0, 2))
        ttk.Button(ab, text=tr("bhf.alpha_fine"),
                   command=lambda: app.set_bhf_alpha_preset(-5.0), style="Small.TButton"
                   ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(ab, text=tr("bhf.alpha_medium"),
                   command=lambda: app.set_bhf_alpha_preset(-2.0), style="Small.TButton"
                   ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(ab, text=tr("bhf.alpha_smooth"),
                   command=lambda: app.set_bhf_alpha_preset(1.0), style="Small.TButton"
                   ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))
        ttk.Checkbutton(d3, text=tr("bhf.use_sharp"), variable=app.dist_use_sharp_var,
                        command=app.on_bhf_distribution_option_change).pack(anchor=tk.W, pady=(2, 0))
        ttk.Checkbutton(d3, text=tr("bhf.refine_global"), variable=app.dist_refine_global_var,
                        command=app.on_bhf_distribution_option_change).pack(anchor=tk.W, pady=(0, 2))
        ttk.Button(d3, text=tr("bhf.lcurve_alpha"), command=app.scan_bhf_alpha_gui,
                   style="Small.TButton").pack(anchor=tk.E, fill=tk.X, pady=(2, 0))

    # ── Construcción de componentes en modo APILADO ───────────────────────────

    def _build_stacked(self, area: ttk.Frame) -> None:
        app = self.app
        n = app.n_components_var.get()
        self._comp_tabs.clear()
        self._comp_notebook = None
        self._using_tabs = False

        for idx in range(1, MAX_COMPONENTS + 1):
            lf = ttk.LabelFrame(area, text=tr("tab.component", idx=idx), padding=4)
            self._build_component_content(lf, idx)
            self._comp_tabs[idx] = lf
            if idx <= n:
                lf.pack(fill=tk.X, pady=(0, 4))
                if idx > 1:
                    app.sextet_enabled[idx].set(True)

    # ── Construcción de componentes en modo PESTAÑAS ──────────────────────────

    def _build_tabbed(self, area: ttk.Frame) -> None:
        app = self.app
        n = app.n_components_var.get()
        self._comp_tabs.clear()
        self._using_tabs = True

        nb = ttk.Notebook(area)
        nb.pack(fill=tk.X)
        self._comp_notebook = nb

        for idx in range(1, MAX_COMPONENTS + 1):
            tab = ttk.Frame(nb, padding=4)
            self._build_component_content(tab, idx)
            self._comp_tabs[idx] = tab
            if idx <= n:
                nb.add(tab, text=tr("tab.component", idx=idx))
                if idx > 1:
                    app.sextet_enabled[idx].set(True)

    # ── Contenido de un componente (reutilizado en ambos modos) ───────────────

    def _build_component_content(self, parent: tk.Widget, idx: int) -> None:
        app = self.app

        top = ttk.Frame(parent)
        top.pack(fill=tk.X, pady=(0, 2))
        if idx > 1:
            ttk.Checkbutton(
                top,
                text=tr("component.enable", idx=idx),
                variable=app.sextet_enabled[idx],
                command=app.on_component_activation_change,
            ).pack(side=tk.LEFT)
        else:
            ttk.Label(top, text=tr("component.main_active"),
                      style="Subtitle.TLabel").pack(side=tk.LEFT)
        ttk.Label(top, text=tr("component.shape_label")).pack(side=tk.LEFT, padx=(12, 4))
        kind_box = ttk.Combobox(
            top, textvariable=app.component_kind[idx],
            values=("Sextete", "Doblete", "Singlete"), width=10, state="readonly",
        )
        kind_box.pack(side=tk.LEFT)
        kind_box.bind("<<ComboboxSelected>>", lambda _e, i=idx: app.on_component_kind_change(i))

        # Sliders en 2 columnas — funcionan a cualquier ancho ≥ ~350 px
        cols = ttk.Frame(parent)
        cols.pack(fill=tk.X)
        c1 = ttk.Frame(cols)
        c2 = ttk.Frame(cols)
        c1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        c2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        p = f"s{idx}_"
        depth_default = 0.030 if idx == 1 else 0.005
        self._add_slider(c1, p + "delta",  tr("slider.s_delta"),  0.0,           -2.0, 3.0,  0.001)
        self._add_slider(c1, p + "quad",   tr("slider.s_quad"),   0.0,           -4.0, 4.0,  0.001)
        self._add_slider(c1, p + "bhf",    tr("slider.s_bhf"),    BHF_DEFAULT_T,  0.0, 60.0, 0.01)
        self._add_slider(c1, p + "gamma1", tr("slider.s_gamma1"), 0.30,          0.03, 2.0,  0.001)
        self._add_slider(c1, p + "depth",  tr("slider.s_depth"),  depth_default,  0.0, 0.30, 0.0005)
        self._add_slider(c2, p + "gamma2", tr("slider.s_gamma2"), 1.0,           0.2,  3.0,  0.001)
        self._add_slider(c2, p + "gamma3", tr("slider.s_gamma3"), 1.0,           0.2,  3.0,  0.001)
        self._add_slider(c2, p + "int1",   tr("slider.s_int1"),   1.0,           0.0,  2.0,  0.001)
        self._add_slider(c2, p + "int2",   tr("slider.s_int2"),   1.0,           0.0,  3.0,  0.001)
        self._add_slider(c2, p + "int3",   tr("slider.s_int3"),   1.0,           0.0,  3.0,  0.001)

    # ── Cambio dinámico de modo ───────────────────────────────────────────────

    def _check_layout(self) -> None:
        """Compara el espacio necesario con la altura de ventana y cambia de modo si hace falta."""
        root = self._root
        if root is None or not root.winfo_exists():
            return
        n = self.app.n_components_var.get()
        h_win = self.app.winfo_height()
        if h_win < 100:
            return
        h_needed = _OVERHEAD_H + n * _COMP_H
        # Cambiar a pestañas cuando el contenido supera el 88 % de la ventana.
        # Volver a apilado cuando baja del 78 % (histéresis para evitar rebotes).
        if not self._using_tabs and h_needed > h_win * 0.88:
            self._switch_layout(use_tabs=True)
        elif self._using_tabs and h_needed < h_win * 0.78:
            self._switch_layout(use_tabs=False)

    def _switch_layout(self, use_tabs: bool) -> None:
        if use_tabs == self._using_tabs:
            return
        app = self.app
        n = app.n_components_var.get()

        # 1. Instantánea de valores y estado fijado de todos los sliders de componente
        prefixes = tuple(f"s{i}_" for i in range(1, MAX_COMPONENTS + 1))
        var_snap   = {k: v.get() for k, v in app.vars.items()       if k.startswith(prefixes)}
        fixed_snap = {k: v.get() for k, v in app.fixed_vars.items() if k.startswith(prefixes)}

        # 2. Vaciar el área de componentes
        for child in list(self._comp_area.winfo_children()):
            child.destroy()

        # 3. Reconstruir en el nuevo modo
        if use_tabs:
            self._build_tabbed(self._comp_area)
        else:
            self._build_stacked(self._comp_area)

        # 4. Restaurar valores
        for k, v in var_snap.items():
            if k in app.vars:
                app.vars[k].set(v)
                if k in app.entry_vars:
                    app.entry_vars[k].set(app._format_value(k, v))
        for k, v in fixed_snap.items():
            if k in app.fixed_vars:
                app.fixed_vars[k].set(v)

        # 5. Actualizar UI de tipo de componente (p.ej. ocultar BHF en doblete)
        for idx in range(1, n + 1):
            if app.sextet_enabled[idx].get():
                app.on_component_kind_change(idx)

    # ── Callback del spinbox ──────────────────────────────────────────────────

    def _on_n_components_change(self) -> None:
        app = self.app
        n = app.n_components_var.get()

        if self._using_tabs:
            nb = self._comp_notebook
            if nb:
                for idx in range(1, MAX_COMPONENTS + 1):
                    tab = self._comp_tabs.get(idx)
                    if tab is None:
                        continue
                    in_nb = str(tab) in nb.tabs()
                    if idx <= n:
                        if not in_nb:
                            nb.add(tab, text=tr("tab.component", idx=idx))
                        if idx > 1:
                            app.sextet_enabled[idx].set(True)
                    else:
                        if in_nb:
                            nb.forget(tab)
                        app.sextet_enabled[idx].set(False)
        else:
            for idx in range(1, MAX_COMPONENTS + 1):
                frame = self._comp_tabs.get(idx)
                if frame is None:
                    continue
                if idx <= n:
                    if not frame.winfo_ismapped():
                        frame.pack(fill=tk.X, pady=(0, 4))
                    if idx > 1:
                        app.sextet_enabled[idx].set(True)
                else:
                    if frame.winfo_ismapped():
                        frame.pack_forget()
                    app.sextet_enabled[idx].set(False)

        app.sextet_enabled[1].set(True)
        app.on_component_activation_change()

        # Comprobar si el nuevo número de componentes requiere cambiar de modo
        if self._layout_timer:
            try:
                app.after_cancel(self._layout_timer)
            except Exception:
                pass
        self._layout_timer = app.after(300, self._check_layout)
