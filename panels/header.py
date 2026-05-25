"""Panel de cabecera con nombre de la aplicación, subtítulo y autor."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from mossbauer_i18n import tr
from core.constants import APP_NAME, APP_AUTHOR, APP_DEPARTMENT
from .base import BasePanel

ACCENT_DARK = "#075985"


class HeaderPanel(BasePanel):
    PANEL_ID = "header"
    PANEL_NAME = "Cabecera"

    def build(self, parent: tk.Widget) -> tk.Widget:
        header = tk.Frame(parent, bg=ACCENT_DARK, bd=0, highlightthickness=0)
        title_block = tk.Frame(header, bg=ACCENT_DARK, bd=0, highlightthickness=0)
        title_block.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12, pady=8)
        tk.Label(
            title_block,
            text=APP_NAME,
            bg=ACCENT_DARK,
            fg="white",
            font=("TkDefaultFont", 18, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            title_block,
            text=tr("main.subtitle"),
            bg=ACCENT_DARK,
            fg="#dff6ff",
            font=("TkDefaultFont", 9),
        ).pack(anchor=tk.W, pady=(0, 5))
        tk.Label(
            title_block,
            text=APP_AUTHOR,
            bg=ACCENT_DARK,
            fg="#dff6ff",
            font=("TkDefaultFont", 9),
        ).pack(anchor=tk.W)
        tk.Label(
            title_block,
            text=APP_DEPARTMENT,
            bg=ACCENT_DARK,
            fg="#dff6ff",
            font=("TkDefaultFont", 9),
        ).pack(anchor=tk.W)
        self._root = header
        return header
