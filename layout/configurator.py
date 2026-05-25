"""Diálogo GUI para que el usuario configure la disposición de paneles."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING

from .presets import PRESETS

if TYPE_CHECKING:
    from mossbauer_app import MossbauerApp
    from .manager import LayoutManager


class LayoutConfigDialog(tk.Toplevel):
    """Ventana modal para reordenar paneles entre columna izquierda y derecha."""

    def __init__(self, app: "MossbauerApp", manager: "LayoutManager") -> None:
        super().__init__(app)
        self.app = app
        self.manager = manager
        self.title("Configurar disposición de paneles")
        self.resizable(False, False)
        self.grab_set()

        current = manager.load_config()
        panel_names = manager.get_panel_names()

        # Estado interno: listas mutables de IDs
        self._left: list[str] = list(current.get("left", []))
        self._right: list[str] = list(current.get("right", []))
        self._left_width = tk.IntVar(value=int(current.get("left_width", 455)))

        # Paneles que aún no están en ninguna columna
        assigned = set(self._left) | set(self._right)
        self._unassigned = [pid for pid in panel_names if pid not in assigned]
        self._panel_names = panel_names

        self._build_ui()
        self._refresh_lists()

    def _build_ui(self) -> None:
        pad = dict(padx=8, pady=6)

        # ── Presets ───────────────────────────────────────────────────────────
        preset_frame = ttk.LabelFrame(self, text="Presets", padding=6)
        preset_frame.grid(row=0, column=0, columnspan=3, sticky="ew", **pad)
        for name, data in PRESETS.items():
            ttk.Button(
                preset_frame,
                text=name,
                command=lambda d=data, n=name: self._apply_preset(d),
            ).pack(side=tk.LEFT, padx=4)

        # ── Columnas ──────────────────────────────────────────────────────────
        left_frame = ttk.LabelFrame(self, text="Columna izquierda", padding=6)
        left_frame.grid(row=1, column=0, sticky="nsew", **pad)
        self._left_lb = self._make_listbox(left_frame)

        mid_frame = ttk.Frame(self, padding=6)
        mid_frame.grid(row=1, column=1, sticky="ns", pady=6)
        ttk.Button(mid_frame, text="← Izquierda", command=self._move_to_left).pack(fill=tk.X, pady=2)
        ttk.Button(mid_frame, text="Derecha →", command=self._move_to_right).pack(fill=tk.X, pady=2)
        ttk.Separator(mid_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        ttk.Button(mid_frame, text="▲ Subir", command=lambda: self._move_up(self._focused_list())).pack(fill=tk.X, pady=2)
        ttk.Button(mid_frame, text="▼ Bajar", command=lambda: self._move_down(self._focused_list())).pack(fill=tk.X, pady=2)

        right_frame = ttk.LabelFrame(self, text="Columna derecha", padding=6)
        right_frame.grid(row=1, column=2, sticky="nsew", **pad)
        self._right_lb = self._make_listbox(right_frame)

        # ── Ancho columna izquierda ───────────────────────────────────────────
        width_frame = ttk.Frame(self, padding=6)
        width_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=8)
        ttk.Label(width_frame, text="Ancho columna izquierda (px):").pack(side=tk.LEFT)
        ttk.Spinbox(
            width_frame, from_=260, to=600, increment=10,
            textvariable=self._left_width, width=6,
        ).pack(side=tk.LEFT, padx=6)

        # ── Nota paneles fijos ────────────────────────────────────────────────
        ttk.Label(
            self,
            text="Nota: la gráfica y los controles de ajuste siempre van a la derecha.",
            foreground="#64748b",
            font=("TkDefaultFont", 8),
        ).grid(row=3, column=0, columnspan=3, padx=8, pady=(0, 4))

        # ── Botones OK / Cancelar ─────────────────────────────────────────────
        btn_frame = ttk.Frame(self, padding=(8, 4, 8, 8))
        btn_frame.grid(row=4, column=0, columnspan=3, sticky="e")
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(
            btn_frame, text="Aplicar", style="Accent.TButton", command=self._apply
        ).pack(side=tk.RIGHT)

        self.columnconfigure(0, weight=1)
        self.columnconfigure(2, weight=1)

    def _make_listbox(self, parent: tk.Widget) -> tk.Listbox:
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL)
        lb = tk.Listbox(frame, width=26, height=10, yscrollcommand=sb.set, selectmode=tk.SINGLE)
        sb.config(command=lb.yview)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb.bind("<<ListboxSelect>>", lambda _e: None)
        return lb

    def _refresh_lists(self) -> None:
        for lb, ids in ((self._left_lb, self._left), (self._right_lb, self._right)):
            lb.delete(0, tk.END)
            for pid in ids:
                lb.insert(tk.END, self._panel_names.get(pid, pid))

    def _focused_list(self) -> list[str]:
        """Devuelve la lista (izquierda o derecha) con selección activa."""
        if self._left_lb.curselection():
            return self._left
        return self._right

    def _focused_lb(self) -> tk.Listbox:
        if self._left_lb.curselection():
            return self._left_lb
        return self._right_lb

    def _move_to_left(self) -> None:
        sel = self._right_lb.curselection()
        if not sel:
            return
        idx = sel[0]
        pid = self._right.pop(idx)
        self._left.append(pid)
        self._refresh_lists()

    def _move_to_right(self) -> None:
        sel = self._left_lb.curselection()
        if not sel:
            return
        idx = sel[0]
        pid = self._left.pop(idx)
        self._right.append(pid)
        self._refresh_lists()

    def _move_up(self, lst: list[str]) -> None:
        lb = self._focused_lb()
        sel = lb.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        lst[i - 1], lst[i] = lst[i], lst[i - 1]
        self._refresh_lists()
        lb.selection_set(i - 1)

    def _move_down(self, lst: list[str]) -> None:
        lb = self._focused_lb()
        sel = lb.curselection()
        if not sel or sel[0] >= len(lst) - 1:
            return
        i = sel[0]
        lst[i], lst[i + 1] = lst[i + 1], lst[i]
        self._refresh_lists()
        lb.selection_set(i + 1)

    def _apply_preset(self, data: dict) -> None:
        self._left = list(data.get("left", []))
        self._right = list(data.get("right", []))
        self._left_width.set(int(data.get("left_width", 455)))
        self._refresh_lists()

    def _apply(self) -> None:
        config = {
            "version": 1,
            "left": self._left,
            "right": self._right,
            "left_width": self._left_width.get(),
        }
        self.destroy()
        self.manager.rebuild(config)
