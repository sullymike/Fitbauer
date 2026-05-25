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
    """Ventana modal con 3 columnas configurables: izquierda | centro | derecha.

    El gráfico siempre rellena el espacio sobrante del centro.
    Los paneles colocados en el centro se apilan encima del gráfico.
    """

    def __init__(self, app: "MossbauerApp", manager: "LayoutManager") -> None:
        super().__init__(app)
        self.app = app
        self.manager = manager
        self.title("Configurar disposición de paneles")
        self.resizable(False, False)
        self.grab_set()

        current = manager.load_config()
        self._panel_names = manager.get_panel_names()

        self._left:   list[str] = list(current.get("left", []))
        self._center: list[str] = list(current.get("center", []))
        self._right:  list[str] = list(current.get("right", []))
        self._left_width  = tk.IntVar(value=int(current.get("left_width",  455)))
        self._right_width = tk.IntVar(value=int(current.get("right_width",   0)))

        self._build_ui()
        self._refresh_lists()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        pad = dict(padx=7, pady=5)

        # Presets
        pf = ttk.LabelFrame(self, text="Presets", padding=6)
        pf.grid(row=0, column=0, columnspan=7, sticky="ew", **pad)
        for name, data in PRESETS.items():
            ttk.Button(pf, text=name,
                       command=lambda d=data: self._apply_preset(d)).pack(side=tk.LEFT, padx=3)

        # ── Columna izquierda ─────────────────────────────────────────────────
        lf = ttk.LabelFrame(self, text="◀ Izquierda", padding=6)
        lf.grid(row=1, column=0, sticky="nsew", **pad)
        self._left_lb = self._make_listbox(lf)

        bf1 = self._arrow_buttons(self, col=1,
                                  on_right=self._left_to_center,
                                  on_left=self._center_to_left)

        # ── Columna central ───────────────────────────────────────────────────
        cf = ttk.LabelFrame(self, text="● Centro", padding=6)
        cf.grid(row=1, column=2, sticky="nsew", **pad)
        self._center_lb = self._make_listbox(cf)
        ttk.Label(cf, text="+ gráfica (fija, siempre aquí)",
                  foreground="#64748b", font=("TkDefaultFont", 8)).pack(pady=(2, 0))

        bf2 = self._arrow_buttons(self, col=3,
                                  on_right=self._center_to_right,
                                  on_left=self._right_to_center)

        # ── Columna derecha ───────────────────────────────────────────────────
        rf = ttk.LabelFrame(self, text="Derecha ▶", padding=6)
        rf.grid(row=1, column=4, sticky="nsew", **pad)
        self._right_lb = self._make_listbox(rf)

        # Botones subir/bajar y quitar (columna 5)
        ord_f = ttk.Frame(self, padding=4)
        ord_f.grid(row=1, column=5, sticky="ns", pady=5)
        ttk.Button(ord_f, text="▲",  width=3, command=lambda: self._move_item(-1)).pack(pady=2)
        ttk.Button(ord_f, text="▼",  width=3, command=lambda: self._move_item(+1)).pack(pady=2)
        ttk.Separator(ord_f, orient="horizontal").pack(fill=tk.X, pady=6)
        ttk.Button(ord_f, text="✕",  width=3, command=self._remove_item,
                   style="Small.TButton").pack(pady=2)

        # Anchos
        wf = ttk.Frame(self, padding=(7, 2, 7, 4))
        wf.grid(row=2, column=0, columnspan=6, sticky="ew")
        ttk.Label(wf, text="Ancho columna izquierda:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(wf, from_=200, to=600, increment=10,
                    textvariable=self._left_width, width=6).grid(row=0, column=1, padx=(4, 20))
        ttk.Label(wf, text="Ancho columna derecha:").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(wf, from_=200, to=700, increment=10,
                    textvariable=self._right_width, width=6).grid(row=0, column=3, padx=4)
        ttk.Label(wf, text="(0 = derecha oculta)",
                  foreground="#64748b", font=("TkDefaultFont", 8)
                  ).grid(row=0, column=4, padx=(6, 0))

        # Nota
        ttk.Label(self, text="Paneles sin asignar no se muestran. Usa ✕ para quitarlos de una columna.",
                  foreground="#94a3b8", font=("TkDefaultFont", 8)
                  ).grid(row=3, column=0, columnspan=6, padx=7, pady=(0, 2))

        # OK / Cancelar
        okf = ttk.Frame(self, padding=(7, 4, 7, 8))
        okf.grid(row=4, column=0, columnspan=6, sticky="e")
        ttk.Button(okf, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(okf, text="Aplicar", style="Accent.TButton",
                   command=self._apply).pack(side=tk.RIGHT)

        for c in (0, 2, 4):
            self.columnconfigure(c, weight=1)

    def _arrow_buttons(self, parent, col, on_right, on_left):
        f = ttk.Frame(parent, padding=4)
        f.grid(row=1, column=col, sticky="ns", pady=5)
        ttk.Button(f, text="◀", width=3, command=on_left ).pack(pady=2)
        ttk.Button(f, text="▶", width=3, command=on_right).pack(pady=2)
        return f

    def _make_listbox(self, parent: tk.Widget) -> tk.Listbox:
        f = ttk.Frame(parent)
        f.pack(fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(f, orient=tk.VERTICAL)
        lb = tk.Listbox(f, width=20, height=7, yscrollcommand=sb.set, selectmode=tk.SINGLE)
        sb.config(command=lb.yview)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        return lb

    def _refresh_lists(self) -> None:
        for lb, ids in (
            (self._left_lb,   self._left),
            (self._center_lb, self._center),
            (self._right_lb,  self._right),
        ):
            lb.delete(0, tk.END)
            for pid in ids:
                lb.insert(tk.END, self._panel_names.get(pid, pid))

    # ── Movimientos entre columnas ────────────────────────────────────────────

    def _transfer(self, src_lb, src_lst, dst_lst, dst_lb) -> None:
        sel = src_lb.curselection()
        if not sel:
            return
        dst_lst.append(src_lst.pop(sel[0]))
        self._refresh_lists()
        dst_lb.selection_set(len(dst_lst) - 1)

    def _left_to_center(self)  -> None: self._transfer(self._left_lb,   self._left,   self._center, self._center_lb)
    def _center_to_left(self)  -> None: self._transfer(self._center_lb, self._center, self._left,   self._left_lb)
    def _center_to_right(self) -> None: self._transfer(self._center_lb, self._center, self._right,  self._right_lb)
    def _right_to_center(self) -> None: self._transfer(self._right_lb,  self._right,  self._center, self._center_lb)

    def _active(self) -> tuple[tk.Listbox, list[str]] | tuple[None, None]:
        for lb, lst in (
            (self._left_lb,   self._left),
            (self._center_lb, self._center),
            (self._right_lb,  self._right),
        ):
            if lb.curselection():
                return lb, lst
        return None, None

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
        self._left   = list(data.get("left",   []))
        self._center = list(data.get("center", []))
        self._right  = list(data.get("right",  []))
        self._left_width.set( int(data.get("left_width",  455)))
        self._right_width.set(int(data.get("right_width",   0)))
        self._refresh_lists()

    def _apply(self) -> None:
        config = {
            "version":     1,
            "left":        self._left,
            "center":      self._center,
            "right":       self._right,
            "left_width":  self._left_width.get(),
            "right_width": self._right_width.get(),
        }
        self.destroy()
        self.manager.rebuild(config)
