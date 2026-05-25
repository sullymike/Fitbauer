"""Diálogo GUI para configurar la disposición de 3 columnas."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from .presets import PRESETS

if TYPE_CHECKING:
    from mossbauer_app import MossbauerApp
    from .manager import LayoutManager


class LayoutConfigDialog(tk.Toplevel):
    """Ventana modal con 3 zonas: izquierda | centro (fijo) | derecha."""

    def __init__(self, app: "MossbauerApp", manager: "LayoutManager") -> None:
        super().__init__(app)
        self.app = app
        self.manager = manager
        self.title("Configurar disposición de paneles")
        self.resizable(False, False)
        self.grab_set()

        current = manager.load_config()
        self._panel_names = manager.get_panel_names()

        self._left: list[str]  = list(current.get("left", []))
        self._right: list[str] = list(current.get("right", []))
        self._left_width  = tk.IntVar(value=int(current.get("left_width", 455)))
        self._right_width = tk.IntVar(value=int(current.get("right_width", 480)))

        # Paneles no asignados a ninguna columna
        assigned = set(self._left) | set(self._right)
        self._unassigned = [
            pid for pid in self._panel_names if pid not in assigned
        ]

        self._build_ui()
        self._refresh_lists()

    # ── UI principal ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        pad = dict(padx=8, pady=5)

        # ── Presets ────────────────────────────────────────────────────────────
        pf = ttk.LabelFrame(self, text="Presets", padding=6)
        pf.grid(row=0, column=0, columnspan=5, sticky="ew", **pad)
        for name, data in PRESETS.items():
            ttk.Button(
                pf, text=name, command=lambda d=data: self._apply_preset(d)
            ).pack(side=tk.LEFT, padx=3)

        # ── Tres listas ────────────────────────────────────────────────────────
        lf = ttk.LabelFrame(self, text="◀ Columna izquierda", padding=6)
        lf.grid(row=1, column=0, sticky="nsew", **pad)
        self._left_lb = self._make_listbox(lf)

        # Botones izq↔der
        bf = ttk.Frame(self, padding=4)
        bf.grid(row=1, column=1, sticky="ns", pady=5)
        ttk.Button(bf, text="◀ Izda",   command=self._move_to_left ).pack(fill=tk.X, pady=2)
        ttk.Button(bf, text="Dcha ▶",   command=self._move_to_right).pack(fill=tk.X, pady=2)
        ttk.Separator(bf, orient="horizontal").pack(fill=tk.X, pady=6)
        ttk.Button(bf, text="▲ Subir",  command=lambda: self._move_item(-1)).pack(fill=tk.X, pady=2)
        ttk.Button(bf, text="▼ Bajar",  command=lambda: self._move_item(+1)).pack(fill=tk.X, pady=2)
        ttk.Separator(bf, orient="horizontal").pack(fill=tk.X, pady=6)
        ttk.Button(bf, text="✕ Quitar", command=self._remove_item,
                   style="Small.TButton").pack(fill=tk.X, pady=2)

        # Centro fijo
        cf = ttk.LabelFrame(self, text="● Centro (fijo)", padding=6)
        cf.grid(row=1, column=2, sticky="nsew", **pad)
        center_lb = tk.Listbox(cf, width=14, height=6, state="disabled")
        center_lb.pack(fill=tk.BOTH, expand=True)
        center_lb.insert(tk.END, "Gráfica")
        ttk.Label(cf, text="(no modificable)", foreground="#94a3b8",
                  font=("TkDefaultFont", 8)).pack()

        # Botones der↔izq (mismo objeto bf reutilizado conceptualmente)
        bf2 = ttk.Frame(self, padding=4)
        bf2.grid(row=1, column=3, sticky="ns", pady=5)
        ttk.Button(bf2, text="◀ Izda",  command=self._move_to_left ).pack(fill=tk.X, pady=2)
        ttk.Button(bf2, text="Dcha ▶",  command=self._move_to_right).pack(fill=tk.X, pady=2)
        ttk.Separator(bf2, orient="horizontal").pack(fill=tk.X, pady=6)
        ttk.Button(bf2, text="▲ Subir", command=lambda: self._move_item(-1)).pack(fill=tk.X, pady=2)
        ttk.Button(bf2, text="▼ Bajar", command=lambda: self._move_item(+1)).pack(fill=tk.X, pady=2)

        rf = ttk.LabelFrame(self, text="Columna derecha ▶", padding=6)
        rf.grid(row=1, column=4, sticky="nsew", **pad)
        self._right_lb = self._make_listbox(rf)

        # ── Anchos ────────────────────────────────────────────────────────────
        wf = ttk.Frame(self, padding=(8, 2, 8, 4))
        wf.grid(row=2, column=0, columnspan=5, sticky="ew")
        ttk.Label(wf, text="Ancho columna izquierda:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(wf, from_=220, to=600, increment=10,
                    textvariable=self._left_width, width=6).grid(row=0, column=1, padx=(4, 20))
        ttk.Label(wf, text="Ancho columna derecha:").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(wf, from_=220, to=700, increment=10,
                    textvariable=self._right_width, width=6).grid(row=0, column=3, padx=4)
        ttk.Label(wf, text="(0 = sim debajo del gráfico)",
                  foreground="#64748b", font=("TkDefaultFont", 8)
                  ).grid(row=0, column=4, padx=(6, 0))

        # ── OK / Cancelar ─────────────────────────────────────────────────────
        okf = ttk.Frame(self, padding=(8, 4, 8, 8))
        okf.grid(row=3, column=0, columnspan=5, sticky="e")
        ttk.Button(okf, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(okf, text="Aplicar", style="Accent.TButton",
                   command=self._apply).pack(side=tk.RIGHT)

        for c in (0, 2, 4):
            self.columnconfigure(c, weight=1)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_listbox(self, parent: tk.Widget) -> tk.Listbox:
        f = ttk.Frame(parent)
        f.pack(fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(f, orient=tk.VERTICAL)
        lb = tk.Listbox(f, width=22, height=8, yscrollcommand=sb.set, selectmode=tk.SINGLE)
        sb.config(command=lb.yview)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        return lb

    def _refresh_lists(self) -> None:
        for lb, ids in ((self._left_lb, self._left), (self._right_lb, self._right)):
            lb.delete(0, tk.END)
            for pid in ids:
                lb.insert(tk.END, self._panel_names.get(pid, pid))

    def _active(self) -> tuple[tk.Listbox, list[str]] | tuple[None, None]:
        """Devuelve la listbox y lista activa (la que tiene selección)."""
        for lb, lst in ((self._left_lb, self._left), (self._right_lb, self._right)):
            if lb.curselection():
                return lb, lst
        return None, None

    def _move_to_left(self) -> None:
        sel = self._right_lb.curselection()
        if not sel:
            return
        idx = sel[0]
        self._left.append(self._right.pop(idx))
        self._refresh_lists()
        self._left_lb.selection_set(len(self._left) - 1)

    def _move_to_right(self) -> None:
        sel = self._left_lb.curselection()
        if not sel:
            return
        idx = sel[0]
        self._right.append(self._left.pop(idx))
        self._refresh_lists()
        self._right_lb.selection_set(len(self._right) - 1)

    def _move_item(self, direction: int) -> None:
        lb, lst = self._active()
        if lb is None:
            return
        sel = lb.curselection()
        if not sel:
            return
        i = sel[0]
        j = i + direction
        if 0 <= j < len(lst):
            lst[i], lst[j] = lst[j], lst[i]
            self._refresh_lists()
            lb.selection_set(j)

    def _remove_item(self) -> None:
        lb, lst = self._active()
        if lb is None:
            return
        sel = lb.curselection()
        if not sel:
            return
        lst.pop(sel[0])
        self._refresh_lists()

    def _apply_preset(self, data: dict) -> None:
        self._left  = list(data.get("left", []))
        self._right = list(data.get("right", []))
        self._left_width.set(int(data.get("left_width", 455)))
        self._right_width.set(int(data.get("right_width", 480)))
        self._refresh_lists()

    def _apply(self) -> None:
        config = {
            "version": 1,
            "left":        self._left,
            "right":       self._right,
            "left_width":  self._left_width.get(),
            "right_width": self._right_width.get(),
        }
        self.destroy()
        self.manager.rebuild(config)
