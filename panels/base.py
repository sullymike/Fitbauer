"""Clase base para todos los paneles de la interfaz Mössbauer."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mossbauer_app import MossbauerApp


class BasePanel:
    """Panel de UI reutilizable y reubicable.

    Subclases deben definir PANEL_ID y PANEL_NAME, e implementar build().
    """

    PANEL_ID: str = ""
    PANEL_NAME: str = ""

    def __init__(self, app: "MossbauerApp") -> None:
        self.app = app
        self._root: tk.Widget | None = None

    def build(self, parent: tk.Widget) -> tk.Widget:
        """Crea todos los widgets dentro de parent y devuelve el widget raíz."""
        raise NotImplementedError

    def refresh(self) -> None:
        """Actualiza la vista cuando el estado de la aplicación cambia."""

    # ── Delegaciones de conveniencia a la app ─────────────────────────────────

    def _add_slider(
        self,
        parent: ttk.Frame,
        key: str,
        label: str,
        value: float,
        min_value: float,
        max_value: float,
        resolution: float,
        fit_param: bool = True,
    ) -> None:
        self.app._add_slider(
            parent, key, label, value, min_value, max_value, resolution, fit_param
        )

    @property
    def _bg(self) -> str:
        return self.app._bg

    @property
    def _card(self) -> str:
        return self.app._card
