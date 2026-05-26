"""Panel de texto con resultados del ajuste e información de la sesión."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from mossbauer_i18n import tr
from .base import BasePanel


class InfoDisplayPanel(BasePanel):
    PANEL_ID = "info_display"
    PANEL_NAME = "Información / resultados"

    def build(self, parent: tk.Widget) -> tk.Widget:
        app = self.app
        card = self._card

        box = ttk.LabelFrame(parent, text=tr("controls.info_box"), style="Section.TLabelframe")

        app.info = tk.Text(
            box,
            width=38,
            height=12,
            wrap=tk.WORD,
            relief=tk.FLAT,
            background=card,
            foreground="#102a43",
            font=("TkDefaultFont", 9),
        )
        app.info.pack(fill=tk.X, pady=2)

        self._root = box
        return box
