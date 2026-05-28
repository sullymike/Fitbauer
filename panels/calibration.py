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
        # Mejora 9 (experimental): selector de modelo de absorbente + escala de
        # saturación C. C sólo se usa (y se ajusta) en modo "thickness".
        am = ttk.Frame(box)
        am.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(am, text=tr("absorber.model_label")).pack(side=tk.LEFT, padx=(0, 4))
        amb = ttk.Combobox(am, textvariable=app.absorber_model_var,
                           values=("thin", "thickness"), width=10, state="readonly")
        amb.pack(side=tk.LEFT)
        amb.bind("<<ComboboxSelected>>", lambda _e: app.on_absorber_model_change())
        self._add_slider(box, "sat_scale", tr("slider.sat_scale"), 5.0, 0.05, 50.0, 0.01)
        app._refresh_absorber_widgets()

        self._root = box
        return box
