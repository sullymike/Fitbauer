"""Panel de simulación/ajuste: cabecera, N componentes dinámicos y distribución BHF.

Layout adaptativo basado en la altura de la ventana:
  - Si hay espacio suficiente: distribución + componentes apilados verticalmente.
  - Si no caben: pestañas de notebook (distribución y componentes como pestañas).
  - Si el panel está en la columna central (_force_tabs=True): siempre pestañas.
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
# Coste fijo: botones + spinbox + márgenes de LabelFrame
_OVERHEAD_H = 110
# Altura estimada del bloque de distribución BHF (fallback para check inverso)
_DIST_H = 340


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
        # Cuando True (columna central), los componentes usan pestañas siempre
        self._force_tabs: bool = False

    # ── build ─────────────────────────────────────────────────────────────────

    def build(self, parent: tk.Widget) -> tk.Widget:
        app = self.app

        sim_box = ttk.LabelFrame(
            parent, text=tr("controls.simulation_box"), style="Section.TLabelframe"
        )

        # ── Fila 1: hint de modo + botón principal ────────────────────────────
        hdr1 = ttk.Frame(sim_box)
        hdr1.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(hdr1, text=tr("controls.fit_mode_hint"),
                  style="Subtitle.TLabel").pack(side=tk.LEFT, anchor=tk.W)
        ttk.Button(hdr1, text=tr("sim.fit"), command=app.fit_current_data,
                   style="Accent.TButton").pack(side=tk.RIGHT)

        # ── Fila 2: botones secundarios (siempre visibles, expanden al ancho) ─
        hdr2 = ttk.Frame(sim_box)
        hdr2.pack(fill=tk.X, pady=(0, 4))
        for text, cmd in [
            (tr("sim.free_all"),    app.free_all_parameters),
            (tr("sim.fix_all"),     app.fix_all_parameters),
            (tr("sim.auto_minima"), app.auto_fit_from_minima),
            (tr("sim.ai_start"),    app.open_ollama_ai_dialog),
        ]:
            ttk.Button(hdr2, text=text, command=cmd,
                       style="Small.TButton").pack(side=tk.LEFT, expand=True,
                                                   fill=tk.X, padx=(0, 2))

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

        # ── Distribución BHF (frame apilado, se oculta cuando no está activa) ─
        dist_frame = ttk.Frame(sim_box)
        app._sim_dist_wrapper = dist_frame
        self._build_distribution_tab(dist_frame)

        # ── Área de componentes ────────────────────────────────────────────────
        comp_area = ttk.Frame(sim_box)
        comp_area.pack(fill=tk.X)
        self._comp_area = comp_area
        app._sim_comp_area = comp_area

        if self._force_tabs:
            self._build_tabbed(comp_area)
        else:
            self._build_stacked(comp_area)
            sim_box.after(400, self._check_layout)

        # Reaccionar a cambios de modo distribución
        def _on_fit_mode_change(*_: object) -> None:
            if self._root is None or not self._root.winfo_exists():
                return
            app._refresh_distribution_tab_visibility(update=False)
            if not self._force_tabs:
                self._schedule_layout_check()

        app.fit_mode_var.trace_add("write", _on_fit_mode_change)

        app._refresh_distribution_tab_visibility(update=False)

        self._root = sim_box
        return sim_box

    # ── Distribución BHF ─────────────────────────────────────────────────────

    def _build_distribution_tab(self, dist_tab: ttk.Frame) -> None:
        """2 columnas — entra sin truncarse en paneles de 470 px o más anchos."""
        app = self.app

        dist_cols = ttk.Frame(dist_tab)
        dist_cols.pack(fill=tk.X)
        # Usar grid con grupo uniforme: las dos columnas tienen siempre el
        # mismo ancho. Con pack, la columna izquierda conservaba su ancho
        # solicitado y la derecha absorbía casi toda la reducción al estrechar.
        dist_cols.columnconfigure(0, weight=1, uniform="dist_cols")
        dist_cols.columnconfigure(1, weight=1, uniform="dist_cols")
        d1 = ttk.Frame(dist_cols)
        d2 = ttk.Frame(dist_cols)
        d1.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        d2.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        # Columna 1 — sliders principales + selección de variable/forma
        self._add_slider(d1, "dist_delta",     tr("slider.dist_delta"),     0.0,          -2.5, 2.5,  0.001, fit_param=False)
        self._add_slider(d1, "dist_quad",      tr("slider.dist_quad"),      0.0,          -4.0, 4.0,  0.001, fit_param=False)
        self._add_slider(d1, "dist_fixed_bhf", tr("slider.dist_fixed_bhf"), BHF_DEFAULT_T, 0.0, 60.0, 0.01,  fit_param=False)
        self._add_slider(d1, "dist_gamma",     tr("slider.dist_gamma"),     0.18,         0.03, 1.0,  0.001, fit_param=False)

        ttk.Label(d1, text=tr("bhf.variable_label")).pack(anchor=tk.W, pady=(4, 0))
        dv = ttk.Combobox(d1, textvariable=app.dist_variable_var,
                          values=("BHF", "ΔEQ"), width=10, state="readonly")
        dv.pack(fill=tk.X, pady=(0, 3))
        dv.bind("<<ComboboxSelected>>", lambda _e: app.on_bhf_distribution_option_change())

        ttk.Label(d1, text=tr("bhf.shape_label")).pack(anchor=tk.W)
        ds = ttk.Combobox(d1, textvariable=app.dist_shape_var,
                          values=("Histograma", "Gaussiana", "Binomial", "Fija"),
                          width=12, state="readonly")
        ds.pack(fill=tk.X, pady=(0, 3))
        ds.bind("<<ComboboxSelected>>", lambda _e: app.on_bhf_distribution_option_change())

        ttk.Label(d1, text=tr("bhf.reg_mode_label")).pack(anchor=tk.W)
        dr = ttk.Combobox(d1, textvariable=app.dist_reg_mode_var,
                          values=("tikhonov", "tv"), width=12, state="readonly")
        dr.pack(fill=tk.X, pady=(0, 3))
        dr.bind("<<ComboboxSelected>>", lambda _e: app.on_bhf_distribution_option_change())

        ttk.Button(d1, text=tr("bhf.load_fixed"), command=app.load_fixed_distribution_file,
                   style="Small.TButton").pack(fill=tk.X, pady=(0, 2))

        # Columna 2 — sliders de rango/bins/alfa + presets y opciones avanzadas
        self._add_slider(d2, "dist_bmin",      tr("slider.dist_bmin"),      0.0,   0.0,  60.0,  0.1,  fit_param=False)
        self._add_slider(d2, "dist_bmax",      tr("slider.dist_bmax"),      50.0,  1.0,  60.0,  0.1,  fit_param=False)
        self._add_slider(d2, "dist_nbins",     tr("slider.dist_nbins"),     50.0, 10.0, 100.0,  1.0,  fit_param=False)
        self._add_slider(d2, "dist_log_alpha", tr("slider.dist_log_alpha"), -2.0, -8.0,   4.0,  0.1,  fit_param=False)

        ab = ttk.Frame(d2)
        ab.pack(fill=tk.X, pady=(4, 2))
        # Botones de alpha con columnas uniformes: ocupan todo el ancho y se
        # redimensionan por igual al hacer la ventana más estrecha/ancha.
        for col in range(3):
            ab.columnconfigure(col, weight=1, uniform="alpha_buttons")
        ttk.Button(ab, text=tr("bhf.alpha_fine"),
                   command=lambda: app.set_bhf_alpha_preset(-5.0), style="Small.TButton"
                   ).grid(row=0, column=0, sticky="ew", padx=(0, 2))
        ttk.Button(ab, text=tr("bhf.alpha_medium"),
                   command=lambda: app.set_bhf_alpha_preset(-2.0), style="Small.TButton"
                   ).grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Button(ab, text=tr("bhf.alpha_smooth"),
                   command=lambda: app.set_bhf_alpha_preset(1.0), style="Small.TButton"
                   ).grid(row=0, column=2, sticky="ew", padx=(2, 0))

        ttk.Checkbutton(d2, text=tr("bhf.use_sharp"), variable=app.dist_use_sharp_var,
                        command=app.on_bhf_distribution_option_change).pack(anchor=tk.W, pady=(2, 0))
        ttk.Checkbutton(d2, text=tr("bhf.refine_global"), variable=app.dist_refine_global_var,
                        command=app.on_bhf_distribution_option_change).pack(anchor=tk.W, pady=(0, 2))
        ttk.Button(d2, text=tr("bhf.lcurve_alpha"), command=app.scan_bhf_alpha_gui,
                   style="Small.TButton").pack(fill=tk.X, pady=(2, 0))

        if hasattr(app, "refresh_dist_slider_labels"):
            app.refresh_dist_slider_labels()

    # ── Construcción de componentes en modo APILADO ───────────────────────────

    def _build_stacked(self, area: ttk.Frame) -> None:
        app = self.app
        n = app.n_components_var.get()
        self._comp_tabs.clear()
        self._comp_notebook = None
        self._using_tabs = False
        app.notebook = None

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
        app.notebook = nb

        # Pestaña de distribución BHF (se inserta/elimina según el modo activo)
        dist_tab = ttk.Frame(nb, padding=6)
        app.dist_tab = dist_tab
        self._build_distribution_tab(dist_tab)

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

        # Variables para modo de intensidades y tratamiento del cuadrupolo
        if idx not in app.intensity_mode:
            app.intensity_mode[idx] = tk.StringVar(value="free")
        if idx not in app.quad_treatment:
            app.quad_treatment[idx] = tk.StringVar(value="1st_order")

        # Sliders en 2 columnas — funcionan a cualquier ancho ≥ ~350 px
        cols = ttk.Frame(parent)
        cols.pack(fill=tk.X)
        c1 = ttk.Frame(cols)
        c2 = ttk.Frame(cols)
        c1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))
        c2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3, 0))

        p = f"s{idx}_"
        depth_default = 0.020 if idx == 1 else 0.005
        # c1: profundidad · intensidades · isomershift
        self._add_slider(c1, p + "depth",  tr("slider.s_depth"),  depth_default,  0.0,  0.07, 0.0001)
        app._add_hidden_model_param(p + "int3", 1.0, 1.0, 1.0, 0.0, fixed=True)
        self._add_slider(c1, p + "int2",   tr("slider.s_int2"),   2.0,            0.0,  4.0,  0.01)
        self._add_slider(c1, p + "int1",   tr("slider.s_int1"),   3.0,            0.0,  6.0,  0.01)
        # Parámetro de textura: t ∈ [0,1]. t=2/3 ⇒ 3:2:1 (polvo aleatorio).
        self._add_slider(c1, p + "texture", tr("slider.s_texture"), 2.0/3.0,      0.0,  1.0,  0.001)
        self._add_slider(c1, p + "delta",  tr("slider.s_delta"),  0.0,           -2.0,  3.0,  0.001)
        # c2: cuadrupolo · campo hiperfino · anchuras
        self._add_slider(c2, p + "quad",   tr("slider.s_quad"),   0.0,           -4.0,  4.0,  0.001)
        self._add_slider(c2, p + "bhf",    tr("slider.s_bhf"),    BHF_DEFAULT_T,  0.0, 60.0,  0.01)
        self._add_slider(c2, p + "gamma1", tr("slider.s_gamma1"), 0.15,           0.03,  2.0,  0.001)
        self._add_slider(c2, p + "gamma2", tr("slider.s_gamma2"), 1.0,            0.2,   3.0,  0.001)
        self._add_slider(c2, p + "gamma3", tr("slider.s_gamma3"), 1.0,            0.2,   3.0,  0.001)
        # Ángulo β entre B y V_zz, en grados (mejora 8b)
        self._add_slider(c2, p + "beta",   tr("slider.s_beta"),   0.0,            0.0,  90.0, 0.1)

        # Menús contextuales (clic derecho): intensidades ↔ modo, β/ΔEQ ↔ cuadrupolo
        for key in (p + "int1", p + "int2", p + "texture"):
            for w in app.slider_widget_refs.get(key, {}).values():
                w.bind("<Button-3>", lambda e, i=idx: self._show_intensity_mode_menu(e, i), add=True)
        for key in (p + "beta", p + "quad"):
            for w in app.slider_widget_refs.get(key, {}).values():
                w.bind("<Button-3>", lambda e, i=idx: self._show_quad_treatment_menu(e, i), add=True)

        # Estado inicial: el slider t empieza deshabilitado salvo que el modo
        # cargado sea "texture"; y β según quad_treatment.
        app._refresh_intensity_mode_widgets(idx)
        app._refresh_quad_treatment_widgets(idx)

    # ── Menús contextuales ────────────────────────────────────────────────────

    def _show_intensity_mode_menu(self, event: tk.Event, idx: int) -> None:
        app = self.app
        if idx not in app.intensity_mode:
            return
        menu = tk.Menu(app, tearoff=0)
        menu.add_command(label=tr("context.intensity_mode_title"), state="disabled")
        menu.add_separator()
        for val, label in (
            ("free", tr("context.intensity_mode_free")),
            ("texture", tr("context.intensity_mode_texture")),
        ):
            menu.add_radiobutton(
                label=label,
                variable=app.intensity_mode[idx],
                value=val,
                command=lambda i=idx: app.on_intensity_mode_change(i),
            )
        menu.tk_popup(event.x_root, event.y_root)

    def _show_quad_treatment_menu(self, event: tk.Event, idx: int) -> None:
        app = self.app
        if idx not in app.quad_treatment:
            return
        menu = tk.Menu(app, tearoff=0)
        menu.add_command(label=tr("context.quad_treatment_title"), state="disabled")
        menu.add_separator()
        for val, label in (
            ("1st_order", tr("context.quad_treatment_1st_order")),
            ("kundig_fixed", tr("context.quad_treatment_kundig_fixed")),
            ("kundig_powder", tr("context.quad_treatment_kundig_powder")),
        ):
            menu.add_radiobutton(
                label=label,
                variable=app.quad_treatment[idx],
                value=val,
                command=lambda i=idx: app.on_quad_treatment_change(i),
            )
        menu.tk_popup(event.x_root, event.y_root)

    # ── Cambio dinámico de modo ───────────────────────────────────────────────

    def _schedule_layout_check(self) -> None:
        if self._force_tabs:
            return
        app = self.app
        if self._layout_timer:
            try:
                app.after_cancel(self._layout_timer)
            except Exception:
                pass
        self._layout_timer = app.after(300, self._check_layout)

    def _check_layout(self) -> None:
        """Compara el espacio necesario con la altura de ventana y cambia de modo si hace falta."""
        root = self._root
        if root is None or not root.winfo_exists():
            return
        if self._force_tabs:
            if not self._using_tabs:
                self._switch_layout(use_tabs=True)
            return
        h_win = self.app.winfo_height()
        if h_win < 100:
            return
        n = self.app.n_components_var.get()
        dist_on = (
            hasattr(self.app, "fit_mode_var")
            and self.app.fit_mode_var.get() == "bhf_distribution"
        )

        if not self._using_tabs:
            # Altura real del panel (dist_frame incluida si está visible)
            root.update_idletasks()
            h_panel = root.winfo_reqheight()
            if h_panel > h_win * 0.88:
                self._switch_layout(use_tabs=True)
        else:
            root.update_idletasks()
            comp_tab = self._comp_tabs.get(1)
            h_one_comp = (
                comp_tab.winfo_reqheight()
                if comp_tab and comp_tab.winfo_exists()
                else _COMP_H
            )
            # Estimar altura en modo apilado incluyendo distribución si está activa
            wrapper = getattr(self.app, "_sim_dist_wrapper", None)
            h_dist = 0
            if dist_on and wrapper and wrapper.winfo_exists():
                h_dist = wrapper.winfo_reqheight() or _DIST_H
            h_stacked = _OVERHEAD_H + h_dist + n * h_one_comp
            if h_stacked < h_win * 0.78:
                self._switch_layout(use_tabs=False)

    def _switch_layout(self, use_tabs: bool) -> None:
        if use_tabs == self._using_tabs:
            return
        app = self.app
        n = app.n_components_var.get()

        # Instantánea de valores y estado fijado de todos los sliders de componente
        prefixes = tuple(f"s{i}_" for i in range(1, MAX_COMPONENTS + 1))
        var_snap   = {k: v.get() for k, v in app.vars.items()       if k.startswith(prefixes)}
        fixed_snap = {k: v.get() for k, v in app.fixed_vars.items() if k.startswith(prefixes)}

        # Vaciar el área de componentes
        for child in list(self._comp_area.winfo_children()):
            child.destroy()

        # Reconstruir en el nuevo modo
        if use_tabs:
            self._build_tabbed(self._comp_area)
        else:
            self._build_stacked(self._comp_area)

        # Restaurar valores
        for k, v in var_snap.items():
            if k in app.vars:
                app.vars[k].set(v)
                if k in app.entry_vars:
                    app.entry_vars[k].set(app._format_value(k, v))
        for k, v in fixed_snap.items():
            if k in app.fixed_vars:
                app.fixed_vars[k].set(v)

        # Actualizar UI de tipo de componente (p.ej. ocultar BHF en doblete)
        for idx in range(1, n + 1):
            if app.sextet_enabled[idx].get():
                app.on_component_kind_change(idx)

        # Sincronizar la pestaña de distribución en el nuevo notebook (si tabbed)
        app._refresh_distribution_tab_visibility(update=False)

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
        self._schedule_layout_check()
