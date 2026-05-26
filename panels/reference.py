"""Panel de líneas de referencia del sextete Fe-57."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from mossbauer_i18n import tr
from core.constants import LINE_POS_33T
from .base import BasePanel


class ReferenceLinesPanel(BasePanel):
    PANEL_ID = "reference"
    PANEL_NAME = "Líneas de referencia"

    def build(self, parent: tk.Widget) -> tk.Widget:
        box = ttk.LabelFrame(
            parent, text=tr("controls.reference_box"), style="Section.TLabelframe"
        )
        ttk.Label(
            box,
            text=tr(
                "controls.reference_lines",
                positions=", ".join(f"{x:.3f}" for x in LINE_POS_33T),
            ),
            justify=tk.LEFT,
            wraplength=350,
        ).pack(anchor=tk.W, pady=2)

        self._root = box
        return box
