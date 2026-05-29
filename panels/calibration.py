"""Panel de calibración: sliders de Vmax, centro, línea base, pendiente y Voigt."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from mossbauer_i18n import tr
from .base import BasePanel


class CalibrationPanel(BasePanel):
    PANEL_ID = "calibration"
    PANEL_NAME = "Calibración"

    def build(self, parent: tk.Widget) -> tk.Widget:
        app = self.app

        box = ttk.LabelFrame(
            parent, text=tr("controls.calibration_box"), style="Section.TLabelframe"
        )
        self._add_slider(box, "vmax", tr("slider.vmax"), 11.8788, 1.0, 15.0, 0.0001, fit_param=False)
        ttk.Checkbutton(
            box,
            text=tr("checkbox.fit_vmax"),
            variable=app.fit_velocity_var,
            command=app.on_fit_velocity_toggle,
        ).pack(anchor=tk.W, pady=(0, 4))
        self._add_slider(box, "center", tr("slider.center"), 256.5, 250.0, 263.0, 0.0001, fit_param=False)
        ttk.Checkbutton(
            box,
            text=tr("checkbox.fit_center"),
            variable=app.fit_center_var,
        ).pack(anchor=tk.W, pady=(0, 4))
        self._add_slider(box, "baseline", tr("slider.baseline"), 1.0, 0.70, 1.30, 0.0005)
        self._add_slider(box, "slope", tr("slider.slope"), 0.0, -0.002, 0.002, 0.00001)
        self._add_slider(
            box, "voigt_sigma", tr("slider.voigt_sigma"), 0.05, 0.0, 1.0, 0.001, fit_param=False
        )
        sigma_refs = app.slider_widget_refs.get("voigt_sigma", {})
        for widget in (sigma_refs.get("slider"), sigma_refs.get("label")):
            if widget is not None:
                widget.bind("<Button-3>", app.show_sigma_profile_menu)
        app.fit_sigma_check = ttk.Checkbutton(
            box,
            text=tr("checkbox.fit_sigma"),
            variable=app.fit_sigma_var,
        )
        app.fit_sigma_check.pack(anchor=tk.W, pady=(0, 4))
        app.fit_sigma_check.configure(
            state=tk.NORMAL if app.line_profile_var.get() == "Voigt" else tk.DISABLED
        )

        self._root = box
        return box
