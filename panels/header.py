"""Panel de cabecera con logo, nombre de la aplicación, subtítulo y autor."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from mossbauer_i18n import tr
from core.constants import APP_NAME, APP_AUTHOR, APP_DEPARTMENT
from .base import BasePanel

ACCENT_DARK = "#075985"
ICON_PNG = Path(__file__).resolve().parents[1] / "assets" / "fitbauer_icon.png"


class HeaderPanel(BasePanel):
    PANEL_ID = "header"
    PANEL_NAME = "Cabecera"

    def build(self, parent: tk.Widget) -> tk.Widget:
        header = tk.Frame(parent, bg=ACCENT_DARK, bd=0, highlightthickness=0)
        logo = self._make_logo(header)
        if logo is not None:
            logo.pack(side=tk.LEFT, padx=(12, 0), pady=8)
        title_block = tk.Frame(header, bg=ACCENT_DARK, bd=0, highlightthickness=0)
        title_block.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=8)
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

    def _make_logo(self, parent: tk.Widget) -> tk.Widget | None:
        """Etiqueta con el logo de Fitbauer (~48 px). None si no se puede cargar."""
        try:
            if not ICON_PNG.exists():
                return None
            img = tk.PhotoImage(file=str(ICON_PNG))
            factor = max(1, round(img.width() / 48))
            if factor > 1:
                img = img.subsample(factor, factor)
            label = tk.Label(parent, image=img, bg=ACCENT_DARK, bd=0,
                             highlightthickness=0)
            label.image = img  # conservar referencia para evitar GC
            return label
        except Exception:
            return None
