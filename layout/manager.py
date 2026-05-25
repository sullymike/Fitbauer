"""LayoutManager: lee la configuración, crea paneles y construye la ventana."""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING

from core.data_io import CONFIG_DIR
from .presets import PRESETS, DEFAULT_PRESET

if TYPE_CHECKING:
    from mossbauer_app import MossbauerApp

LAYOUT_PATH = CONFIG_DIR / "layout.json"

# IDs de paneles que siempre van a la derecha y no son reconfigurables.
_FIXED_RIGHT = ("plot", "sim_controls")

# Orden de registro de todos los paneles reconfigurables.
ALL_PANEL_IDS = ["header", "file_info", "info_display", "calibration", "reference"]


class LayoutManager:
    def __init__(self, app: "MossbauerApp") -> None:
        self.app = app
        self._panels: dict = {}
        self._main_frame: tk.Widget | None = None
        self._register_panels()

    # ── Registro de paneles ───────────────────────────────────────────────────

    def _register_panels(self) -> None:
        from panels.header import HeaderPanel
        from panels.file_info import FileInfoPanel
        from panels.info_display import InfoDisplayPanel
        from panels.calibration import CalibrationPanel
        from panels.reference import ReferenceLinesPanel
        from panels.plot_panel import PlotPanel
        from panels.sim_panel import SimPanel

        app = self.app
        self._panels = {
            "header": HeaderPanel(app),
            "file_info": FileInfoPanel(app),
            "info_display": InfoDisplayPanel(app),
            "calibration": CalibrationPanel(app),
            "reference": ReferenceLinesPanel(app),
            "plot": PlotPanel(app),
            "sim_controls": SimPanel(app),
        }

    # ── Config I/O ────────────────────────────────────────────────────────────

    def load_config(self) -> dict:
        if LAYOUT_PATH.exists():
            try:
                data = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "left" in data:
                    return data
            except Exception:
                pass
        return dict(PRESETS[DEFAULT_PRESET])

    def save_config(self, config: dict) -> None:
        LAYOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAYOUT_PATH.write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── Construcción de la UI ─────────────────────────────────────────────────

    def build(self, window: tk.Tk) -> None:
        """Construye el layout completo de la ventana."""
        config = self.load_config()
        self._build_from_config(window, config)

    def _build_from_config(self, window: tk.Tk, config: dict) -> None:
        left_ids: list[str] = config.get("left", [])
        right_ids: list[str] = config.get("right", [])
        left_width: int = int(config.get("left_width", 455))

        main = ttk.Frame(window)
        main.pack(fill=tk.BOTH, expand=True)
        self._main_frame = main

        # ── Columna izquierda ─────────────────────────────────────────────────
        left_outer = ttk.Frame(main, width=left_width, padding=10)
        left_outer.pack(side=tk.LEFT, fill=tk.Y)
        left_outer.pack_propagate(False)
        controls = ttk.Frame(left_outer)
        controls.pack(fill=tk.BOTH, expand=True)

        for panel_id in left_ids:
            panel = self._panels.get(panel_id)
            if panel:
                widget = panel.build(controls)
                widget.pack(fill=tk.X, pady=(0, 8))

        # ── Columna derecha ───────────────────────────────────────────────────
        plot_frame = ttk.Frame(main, padding=(6, 6, 8, 8))
        plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Paneles adicionales opcionales en la derecha (encima del plot)
        if right_ids:
            right_controls = ttk.Frame(plot_frame)
            right_controls.pack(side=tk.TOP, fill=tk.X)
            for panel_id in right_ids:
                panel = self._panels.get(panel_id)
                if panel:
                    widget = panel.build(right_controls)
                    widget.pack(fill=tk.X, pady=(0, 8))

        # SimPanel siempre va anclado al fondo de la columna derecha
        sim_widget = self._panels["sim_controls"].build(plot_frame)
        sim_widget.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

        # PlotPanel ocupa el espacio restante
        plot_area = ttk.Frame(plot_frame)
        plot_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        plot_widget = self._panels["plot"].build(plot_area)
        plot_widget.pack(fill=tk.BOTH, expand=True)

    # ── Reconstrucción dinámica ───────────────────────────────────────────────

    def rebuild(self, config: dict) -> None:
        """Destruye el layout actual y lo reconstruye con la nueva configuración."""
        app = self.app
        snapshot = app.settings_payload()

        if self._main_frame:
            self._main_frame.destroy()
            self._main_frame = None

        # Reiniciar referencias a widgets que ya no existen
        for attr in ("file_label", "info", "fig", "ax", "ax_res", "canvas", "notebook", "dist_tab"):
            if hasattr(app, attr):
                delattr(app, attr)
        app.vars = {}
        app.entry_vars = {}
        app.fixed_vars = {}
        app.slider_specs = {}

        self._register_panels()
        self._build_from_config(app, config)
        self.save_config(config)

        # Restaurar valores de parámetros y estado
        app._apply_state_payload(snapshot, restore_geometry=False)
        app._refresh_distribution_tab_visibility(update=False)
        if app.counts is not None:
            app.refold_data()
            app.update_plot()

    # ── Acceso desde el configurador ─────────────────────────────────────────

    def open_configurator(self) -> None:
        from .configurator import LayoutConfigDialog
        LayoutConfigDialog(self.app, self)

    def get_panel_names(self) -> dict[str, str]:
        return {pid: p.PANEL_NAME for pid, p in self._panels.items() if pid not in _FIXED_RIGHT}
