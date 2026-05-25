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
    """Ventana modal con pool de disponibles + 3 columnas configurables.

    Disponibles → Izquierda | Centro | Derecha
    Los paneles quitados de cualquier columna vuelven al pool.
    """

    def __init__(self, app: "MossbauerApp", manager: "LayoutManager") -> None:
        super().__init__(app)
        self.app = app
        self.manager = manager
        self.title("Configurar disposición de paneles")
        self.resizable(False, False)
        self.grab_set()

        current = manager.load_config()
        self._panel_names = manager.get_panel_names()   # {id: nombre}

        self._left:   list[str] = list(current.get("left",   []))
        self._center: list[str] = list(current.get("center", []))
        self._right:  list[str] = list(current.get("right",  []))
        self._left_width  = tk.IntVar(value=int(current.get("left_width",  455)))
        self._right_width = tk.IntVar(value=int(current.get("right_width",   0)))

        # Paneles no asignados a ninguna columna
        assigned = set(self._left) | set(self._center) | set(self._right)
        self._pool: list[str] = [
            pid for pid in self._panel_names if pid not in assigned
        ]

        self._build_ui()
        self._refresh_all()

    # ── Construcción de la UI ─────────────────────────────────────────────────

    def _build_ui(self) -> None:
        p = dict(padx=6, pady=4)

        # ── Presets ────────────────────────────────────────────────────────────
        pf = ttk.LabelFrame(self, text="Presets", padding=5)
        pf.grid(row=0, column=0, columnspan=8, sticky="ew", **p)
        for name, data in PRESETS.items():
            ttk.Button(pf, text=name,
                       command=lambda d=data: self._apply_preset(d)
                       ).pack(side=tk.LEFT, padx=3)

        # ── Pool de disponibles ───────────────────────────────────────────────
        df = ttk.LabelFrame(self, text="Disponibles", padding=5)
        df.grid(row=1, column=0, sticky="nsew", **p)
        self._pool_lb = self._make_listbox(df, height=9, width=18)
        ttk.Label(df, text="(sin asignar)",
                  foreground="#94a3b8", font=("TkDefaultFont", 8)).pack()

        # ── Botones pool ↔ izquierda ──────────────────────────────────────────
        self._arrow_col(col=1,
                        right_cmd=self._pool_to_left,
                        left_cmd=self._left_to_pool)

        # ── Columna izquierda ─────────────────────────────────────────────────
        lf = ttk.LabelFrame(self, text="◀  Izquierda", padding=5)
        lf.grid(row=1, column=2, sticky="nsew", **p)
        self._left_lb = self._make_listbox(lf)

        # ── Botones izquierda ↔ centro ────────────────────────────────────────
        self._arrow_col(col=3,
                        right_cmd=self._left_to_center,
                        left_cmd=self._center_to_left)

        # ── Columna central ───────────────────────────────────────────────────
        cf = ttk.LabelFrame(self, text="●  Centro", padding=5)
        cf.grid(row=1, column=4, sticky="nsew", **p)
        self._center_lb = self._make_listbox(cf)
        ttk.Label(cf, text="+ gráfica (siempre aquí)",
                  foreground="#64748b", font=("TkDefaultFont", 8)).pack()

        # ── Botones centro ↔ derecha ──────────────────────────────────────────
        self._arrow_col(col=5,
                        right_cmd=self._center_to_right,
                        left_cmd=self._right_to_center)

        # ── Columna derecha ───────────────────────────────────────────────────
        rf = ttk.LabelFrame(self, text="Derecha  ▶", padding=5)
        rf.grid(row=1, column=6, sticky="nsew", **p)
        self._right_lb = self._make_listbox(rf)

        # ── Botones orden y quitar ────────────────────────────────────────────
        of = ttk.Frame(self, padding=4)
        of.grid(row=1, column=7, sticky="ns", pady=4)
        ttk.Button(of, text="▲", width=3, command=lambda: self._reorder(-1)).pack(pady=2)
        ttk.Button(of, text="▼", width=3, command=lambda: self._reorder(+1)).pack(pady=2)
        ttk.Separator(of, orient="horizontal").pack(fill=tk.X, pady=6)
        ttk.Button(of, text="✕", width=3, command=self._remove_to_pool,
                   style="Small.TButton").pack(pady=2)

        # ── Anchos ────────────────────────────────────────────────────────────
        wf = ttk.Frame(self, padding=(6, 2, 6, 2))
        wf.grid(row=2, column=0, columnspan=8, sticky="ew")
        ttk.Label(wf, text="Ancho izquierda:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(wf, from_=200, to=600, increment=10,
                    textvariable=self._left_width, width=6
                    ).grid(row=0, column=1, padx=(4, 20))
        ttk.Label(wf, text="Ancho derecha:").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(wf, from_=200, to=700, increment=10,
                    textvariable=self._right_width, width=6
                    ).grid(row=0, column=3, padx=4)
        ttk.Label(wf, text="(0 = sim debajo del gráfico)",
                  foreground="#64748b", font=("TkDefaultFont", 8)
                  ).grid(row=0, column=4, padx=(6, 0))

        # ── OK / Cancelar ─────────────────────────────────────────────────────
        okf = ttk.Frame(self, padding=(6, 4, 6, 8))
        okf.grid(row=3, column=0, columnspan=8, sticky="e")
        ttk.Button(okf, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(okf, text="Aplicar", style="Accent.TButton",
                   command=self._apply).pack(side=tk.RIGHT)

        for c in (0, 2, 4, 6):
            self.columnconfigure(c, weight=1)

    def _arrow_col(self, col: int, right_cmd, left_cmd) -> None:
        f = ttk.Frame(self, padding=3)
        f.grid(row=1, column=col, sticky="ns", pady=4)
        ttk.Button(f, text="◀", width=3, command=left_cmd ).pack(pady=2)
        ttk.Button(f, text="▶", width=3, command=right_cmd).pack(pady=2)

    def _make_listbox(self, parent: tk.Widget,
                      height: int = 8, width: int = 18) -> tk.Listbox:
        f = ttk.Frame(parent)
        f.pack(fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(f, orient=tk.VERTICAL)
        lb = tk.Listbox(f, width=width, height=height,
                        yscrollcommand=sb.set, selectmode=tk.SINGLE)
        sb.config(command=lb.yview)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        return lb

    # ── Refresco ──────────────────────────────────────────────────────────────

    def _refresh_all(self) -> None:
        for lb, lst in (
            (self._pool_lb,   self._pool),
            (self._left_lb,   self._left),
            (self._center_lb, self._center),
            (self._right_lb,  self._right),
        ):
            lb.delete(0, tk.END)
            for pid in lst:
                lb.insert(tk.END, self._panel_names.get(pid, pid))

    # ── Movimientos entre listas ──────────────────────────────────────────────

    def _transfer(self, src_lb: tk.Listbox, src: list[str],
                  dst: list[str], dst_lb: tk.Listbox) -> None:
        sel = src_lb.curselection()
        if not sel:
            return
        dst.append(src.pop(sel[0]))
        self._refresh_all()
        dst_lb.selection_set(len(dst) - 1)

    def _pool_to_left   (self): self._transfer(self._pool_lb,   self._pool,   self._left,   self._left_lb)
    def _left_to_pool   (self): self._transfer(self._left_lb,   self._left,   self._pool,   self._pool_lb)
    def _left_to_center (self): self._transfer(self._left_lb,   self._left,   self._center, self._center_lb)
    def _center_to_left (self): self._transfer(self._center_lb, self._center, self._left,   self._left_lb)
    def _center_to_right(self): self._transfer(self._center_lb, self._center, self._right,  self._right_lb)
    def _right_to_center(self): self._transfer(self._right_lb,  self._right,  self._center, self._center_lb)

    def _active(self) -> tuple[tk.Listbox, list[str]] | tuple[None, None]:
        for lb, lst in (
            (self._left_lb,   self._left),
            (self._center_lb, self._center),
            (self._right_lb,  self._right),
        ):
            if lb.curselection():
                return lb, lst
        return None, None

    def _reorder(self, direction: int) -> None:
        lb, lst = self._active()
        if lb is None:
            return
        sel = lb.curselection()
        if not sel:
            return
        i, j = sel[0], sel[0] + direction
        if 0 <= j < len(lst):
            lst[i], lst[j] = lst[j], lst[i]
            self._refresh_all()
            lb.selection_set(j)

    def _remove_to_pool(self) -> None:
        """Quita el elemento seleccionado de su columna y lo manda al pool."""
        lb, lst = self._active()
        if lb is None:
            return
        sel = lb.curselection()
        if not sel:
            return
        self._pool.append(lst.pop(sel[0]))
        self._refresh_all()

    # ── Presets y aplicar ─────────────────────────────────────────────────────

    def _apply_preset(self, data: dict) -> None:
        self._left   = list(data.get("left",   []))
        self._center = list(data.get("center", []))
        self._right  = list(data.get("right",  []))
        self._left_width.set( int(data.get("left_width",  455)))
        self._right_width.set(int(data.get("right_width",   0)))
        assigned = set(self._left) | set(self._center) | set(self._right)
        self._pool = [pid for pid in self._panel_names if pid not in assigned]
        self._refresh_all()

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
