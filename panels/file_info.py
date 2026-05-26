"""Panel que muestra el fichero cargado y la etiqueta de calibración."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from mossbauer_i18n import tr
from .base import BasePanel


class FileInfoPanel(BasePanel):
    PANEL_ID = "file_info"
    PANEL_NAME = "Fichero cargado"

    def build(self, parent: tk.Widget) -> tk.Widget:
        app = self.app
        card = self._card

        box = ttk.LabelFrame(parent, text=tr("controls.file_box"), style="Section.TLabelframe")

        app.file_label = tk.Label(
            box,
            textvariable=app.current_file_var,
            bg=card,
            fg="#083344",
            font=("TkDefaultFont", 12, "bold"),
            anchor="w",
            justify="left",
            padx=10,
            pady=8,
            wraplength=405,
        )
        app.file_label.pack(anchor=tk.W, fill=tk.X)

        app.calib_label = tk.Label(
            box,
            textvariable=app.calib_label_var,
            bg=card,
            fg="#0e7490",
            font=("TkDefaultFont", 9),
            anchor="w",
            justify="left",
            padx=10,
            pady=0,
            wraplength=405,
        )
        # Se muestra solo cuando hay calibración activa (update_calibration_label lo gestiona)

        self._root = box
        return box
