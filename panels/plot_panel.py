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

        frame = ttk.Frame(parent)

        app.fig = Figure(figsize=(8.5, 5.8), dpi=100, facecolor="#f8fbff")
        gs = app.fig.add_gridspec(2, 1, height_ratios=[4.6, 1.0], hspace=0.08)
        app.ax = app.fig.add_subplot(gs[0])
        app.ax_res = app.fig.add_subplot(gs[1], sharex=app.ax)
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
