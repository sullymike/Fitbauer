"""Panel de gráfica Matplotlib integrado con Tkinter."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from mossbauer_i18n import tr
from .base import BasePanel


class PlotPanel(BasePanel):
    PANEL_ID = "plot"
    PANEL_NAME = "Gráfica"

    def build(self, parent: tk.Widget) -> tk.Widget:
        app = self.app
        _dark = getattr(app, "_theme_var", None) is not None and app._theme_var.get() == "sv_ttk_dark"
        fig_bg  = "#1c1c1e" if _dark else "#f8fbff"
        axes_bg = "#2a2a2a" if _dark else "#f8fbff"
        tc = "#a6adc8" if _dark else "#17202a"
        lc = "#e2e8f0" if _dark else "#17202a"
        sc = "#6c7086" if _dark else "#cccccc"

        frame = ttk.Frame(parent)

        app.fig = Figure(figsize=(8.5, 5.8), dpi=100, facecolor=fig_bg)
        gs = app.fig.add_gridspec(2, 1, height_ratios=[4.6, 1.0], hspace=0.08)
        app.ax = app.fig.add_subplot(gs[0])
        app.ax_res = app.fig.add_subplot(gs[1], sharex=app.ax)
        for _ax in (app.ax, app.ax_res):
            _ax.set_facecolor(axes_bg)
            _ax.tick_params(colors=tc, which="both")
            _ax.xaxis.label.set_color(lc)
            _ax.yaxis.label.set_color(lc)
            for _sp in _ax.spines.values():
                _sp.set_color(sc)
        app.ax.set_ylabel(tr("plot.transmission_ylabel"))
        app.ax_res.set_ylabel(tr("plot.residual_ylabel"))
        app.ax_res.set_xlabel(tr("plot.velocity_xlabel"))
        app.fig.tight_layout()

        app.canvas = FigureCanvasTkAgg(app.fig, master=frame)
        toolbar = NavigationToolbar2Tk(app.canvas, frame, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        app.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._root = frame
        return frame
