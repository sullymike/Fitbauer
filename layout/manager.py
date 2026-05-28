"""LayoutManager: 3 columnas (izquierda | centro=gráfica | derecha)."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from core.data_io import CONFIG_DIR
from .presets import PRESETS, DEFAULT_PRESET

if TYPE_CHECKING:
    from mossbauer_app import MossbauerApp

LAYOUT_PATH       = CONFIG_DIR / "layout.json"
USER_PRESETS_PATH = CONFIG_DIR / "user_presets.json"

USER_PRESET_NAMES = ["Usuario 1", "Usuario 2"]

# Paneles reconfigurables (pueden ir en izquierda o derecha)
ALL_PANEL_IDS = [
    "header", "file_info", "info_display",
    "calibration", "reference", "sim_controls",
]


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
            "header":       HeaderPanel(app),
            "file_info":    FileInfoPanel(app),
            "info_display": InfoDisplayPanel(app),
            "calibration":  CalibrationPanel(app),
            "reference":    ReferenceLinesPanel(app),
            "sim_controls": SimPanel(app),
            "plot":         PlotPanel(app),
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
        config = self.load_config()
        self._build_from_config(window, config)

    def _build_from_config(self, window: tk.Tk, config: dict) -> None:
        left_ids:   list[str] = config.get("left",   [])
        center_ids: list[str] = config.get("center", [])
        right_ids:  list[str] = config.get("right",  [])
        left_width:  int = int(config.get("left_width",  455))
        right_width: int = int(config.get("right_width",   0))

        # sim_controls se ancla debajo del gráfico cuando right_width == 0
        # y está asignado a la columna derecha (preset Estándar/Compacto)
        sim_below = ("sim_controls" in right_ids and right_width == 0)

        main = ttk.Frame(window)
        main.pack(fill=tk.BOTH, expand=True)
        self._main_frame = main

        # ── Columna izquierda ─────────────────────────────────────────────────
        if left_ids:
            left_outer = ttk.Frame(main, width=left_width, padding=(8, 8, 4, 8))
            left_outer.pack(side=tk.LEFT, fill=tk.Y)
            left_outer.pack_propagate(False)
            self._fill_column(left_outer, left_ids)

        # ── Columna derecha (solo si tiene ancho) ─────────────────────────────
        right_ids_visible = [p for p in right_ids if not (p == "sim_controls" and sim_below)]
        if right_ids_visible and right_width > 0:
            right_outer = ttk.Frame(main, width=right_width, padding=(4, 8, 8, 8))
            right_outer.pack(side=tk.RIGHT, fill=tk.Y)
            right_outer.pack_propagate(False)
            self._fill_column(right_outer, right_ids_visible)

        # ── Centro: paneles opcionales + gráfica (rellena) + sim opcional ─────
        center = ttk.Frame(main, padding=(4, 6, 4, 6))
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Paneles del centro se apilan encima del gráfico
        # sim_controls en el centro → forzar pestañas para no tapar el gráfico
        if center_ids:
            for pid in center_ids:
                panel = self._panels.get(pid)
                if panel:
                    if pid == "sim_controls":
                        panel._force_tabs = True
                    widget = panel.build(center)
                    widget.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))

        # sim_controls debajo del gráfico (modo "ancho 0") → también pestañas
        if sim_below:
            sim_panel = self._panels["sim_controls"]
            sim_panel._force_tabs = True
            sim_widget = sim_panel.build(center)
            sim_widget.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))

        plot_widget = self._panels["plot"].build(center)
        plot_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Paneles esenciales no asignados: construirlos en un frame invisible
        # para que sus vars (baseline, vmax, s1_delta…) siempre existan.
        all_placed = (
            set(left_ids) | set(center_ids) | set(right_ids)
        )
        _essential = {"calibration", "sim_controls", "info_display"}
        _unplaced  = _essential - all_placed
        if _unplaced:
            _hidden = ttk.Frame(window)   # no se empaqueta → invisible
            for pid in _unplaced:
                panel = self._panels.get(pid)
                if panel:
                    panel.build(_hidden)

    def _fill_column(self, parent: tk.Widget, panel_ids: list[str]) -> None:
        for pid in panel_ids:
            panel = self._panels.get(pid)
            if panel:
                widget = panel.build(parent)
                widget.pack(fill=tk.X, pady=(0, 6))

    # ── Reconstrucción dinámica ───────────────────────────────────────────────

    def rebuild(self, config: dict) -> None:
        app = self.app
        snapshot = app.settings_payload()

        if self._main_frame:
            self._main_frame.destroy()
            self._main_frame = None

        for attr in (
            "file_label", "info", "fig", "ax", "ax_res",
            "canvas", "notebook", "dist_tab",
        ):
            if hasattr(app, attr):
                delattr(app, attr)

        app.vars = {}
        app.entry_vars = {}
        app.fixed_vars = {}
        app.slider_specs = {}

        self._register_panels()
        self._build_from_config(app, config)
        self.save_config(config)

        app._apply_state_payload(snapshot, restore_geometry=False)
        app._refresh_distribution_tab_visibility(update=False)
        if app.counts is not None:
            app.refold_data()
            app.update_plot()
        # Re-aplicar tema: el rebuild crea una nueva figura matplotlib
        try:
            from tkinter import ttk as _ttk
            app._reconfigure_styles(_ttk.Style(app), app._sv_active)
        except Exception:
            pass

    # ── Presets de usuario ────────────────────────────────────────────────────

    def load_user_presets(self) -> dict[str, dict]:
        if USER_PRESETS_PATH.exists():
            try:
                data = json.loads(USER_PRESETS_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    def save_user_preset(self, slot: str, config: dict) -> None:
        presets = self.load_user_presets()
        presets[slot] = config
        USER_PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
        USER_PRESETS_PATH.write_text(
            json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── Configurador ─────────────────────────────────────────────────────────

    def open_configurator(self) -> None:
        from .configurator import LayoutConfigDialog
        LayoutConfigDialog(self.app, self)

    def get_panel_names(self) -> dict[str, str]:
        return {pid: p.PANEL_NAME for pid, p in self._panels.items() if pid != "plot"}
