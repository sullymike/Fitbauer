#!/usr/bin/env python3
"""GUI sencilla para cargar, doblar y ajustar espectros Mossbauer de Fe-57.

Modelo implementado: sextete magnetico de hierro con BHF ajustable, inicializado a
33 T, y termino cuadrupolar de primer orden. El espectro .ws5 se dobla con centros
enteros/semienteros, por defecto buscando el mejor centro por chi2 medio, como
hace Normos en el caso habitual.
"""
from __future__ import annotations

import json
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from html import unescape
from urllib.parse import urljoin, urlparse

import numpy as np
from scipy.optimize import least_squares

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure


# Constantes de 57Fe para calcular posiciones magneticas.
BHF_DEFAULT_T = 33.0
MU_N = 5.0507837461e-27       # J/T
E_GAMMA = 14.4125e3 * 1.602176634e-19  # J
C_MM_S = 299_792_458_000.0    # mm/s
G_GROUND = 0.09044 / 0.5      # mu/I, estado fundamental I=1/2
G_EXCITED = -0.1549 / 1.5     # mu/I, estado excitado I=3/2


def fe57_sextet_positions(bhf_t: float = BHF_DEFAULT_T) -> np.ndarray:
    """Posiciones magneticas de las 6 lineas de Fe-57, en mm/s, centradas en 0."""
    factor = MU_N / E_GAMMA * C_MM_S
    positions: list[float] = []
    for m_g in (-0.5, 0.5):
        for delta_m in (-1, 0, 1):
            m_e = m_g + delta_m
            if m_e in (-1.5, -0.5, 0.5, 1.5):
                coeff = -(G_EXCITED * m_e - G_GROUND * m_g)
                positions.append(coeff * bhf_t * factor)
    return np.array(sorted(positions), dtype=float)


LINE_POS_33T = fe57_sextet_positions(BHF_DEFAULT_T)
# Aproximacion de primer orden: si "quad" es DeltaEQ, los niveles excitados
# |m_e|=3/2 se desplazan +quad/2 y |m_e|=1/2 se desplazan -quad/2.
LINE_QUAD_PATTERN = np.array([0.5, -0.5, -0.5, -0.5, -0.5, 0.5], dtype=float)
GLOBAL_PARAM_NAMES = ["baseline", "slope"]
SEXTET_PARAM_NAMES = ["delta", "quad", "bhf", "gamma1", "gamma2", "gamma3", "depth", "int1", "int2", "int3"]
MODEL_PARAM_LABELS = {
    "baseline": "Línea base",
    "slope": "Pendiente",
    "delta": "Desplazamiento isomérico δ",
    "quad": "Cuadrupolo ΔEQ",
    "bhf": "Campo hiperfino BHF (T)",
    "gamma1": "Anchura Γ líneas 1 y 6",
    "gamma2": "Γ relativa líneas 2 y 5",
    "gamma3": "Γ relativa líneas 3 y 4",
    "depth": "Profundidad",
    "int1": "I1 líneas 1 y 6",
    "int2": "I2 relativa (1 = 2/3·I1)",
    "int3": "I3 relativa (1 = 1/3·I1)",
}


def read_ws5_counts(path: Path) -> np.ndarray:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<data[^>]*>(.*?)</data>", text, re.S | re.I)
    if not m:
        raise ValueError(f"No se encontro bloque <data> en {path}")
    counts = np.array([float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", m.group(1))])
    if counts.size < 2:
        raise ValueError("No se encontraron cuentas suficientes en el fichero")
    return counts


def fold_integer_or_half(counts: np.ndarray, center: float) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Dobla usando solo pares de canales enteros simetricos respecto a center.

    Canales numerados 1..N. El resultado se ordena desde el par mas cercano al
    centro hacia fuera; para center=256.5: (256,257), (255,258), ..., (1,512).
    """
    n = counts.size
    rows: list[tuple[int, int, float]] = []
    for left in range(1, n + 1):
        right_f = 2.0 * center - left
        right = int(round(right_f))
        if left < center and abs(right_f - right) < 1e-9 and 1 <= right <= n:
            folded = 0.5 * (counts[left - 1] + counts[right - 1])
            rows.append((left, right, folded))
    rows.reverse()
    return np.array([r[2] for r in rows], dtype=float), [(r[0], r[1]) for r in rows]


def chi2_for_center(counts: np.ndarray, center: float) -> tuple[float, int]:
    folded, pairs = fold_integer_or_half(counts, center)
    chi2 = 0.0
    for left, right in pairs:
        d = counts[left - 1] - counts[right - 1]
        chi2 += d * d
    return chi2, len(pairs)


def find_best_integer_or_half_center(counts: np.ndarray, cmin: float = 250.0, cmax: float = 263.0) -> float:
    candidates = np.arange(cmin * 2, cmax * 2 + 1) / 2.0
    best_center = candidates[0]
    best_value = float("inf")
    for center in candidates:
        chi2, n_pairs = chi2_for_center(counts, float(center))
        if n_pairs and chi2 / n_pairs < best_value:
            best_value = chi2 / n_pairs
            best_center = float(center)
    return best_center


def lorentzian(v: np.ndarray, center: float, gamma: float) -> np.ndarray:
    """Lorentziana de altura maxima 1. gamma es FWHM en mm/s."""
    return 1.0 / (1.0 + 4.0 * ((v - center) / gamma) ** 2)


def sextet_absorption(v: np.ndarray, delta: float, quad: float, bhf: float,
                      gamma1: float, gamma2: float, gamma3: float, depth: float,
                      int1: float, int2: float, int3: float) -> np.ndarray:
    """Absorción de un sextete Fe-57.

    int1 es la intensidad de las líneas 1 y 6. int2 e int3 son relativas:
    int2=1 -> I2=(2/3)*I1; int3=1 -> I3=(1/3)*I1.
    gamma1 es la anchura de las líneas 1 y 6. gamma2 y gamma3 son relativas:
    gamma2=1 -> Γ2,5=Γ1,6; gamma3=1 -> Γ3,4=Γ1,6.
    """
    i1 = int1
    i2 = int1 * (2.0 / 3.0) * int2
    i3 = int1 * (1.0 / 3.0) * int3
    weights = np.array([i1, i2, i3, i3, i2, i1], dtype=float)
    g1 = gamma1
    g2 = gamma1 * gamma2
    g3 = gamma1 * gamma3
    gammas = np.array([g1, g2, g3, g3, g2, g1], dtype=float)
    positions = LINE_POS_33T * (bhf / BHF_DEFAULT_T) + delta + quad * LINE_QUAD_PATTERN
    absorption = np.zeros_like(v, dtype=float)
    for pos, weight, gamma in zip(positions, weights, gammas):
        absorption += weight * lorentzian(v, pos, gamma)
    return depth * absorption


def total_model(v: np.ndarray, baseline: float, slope: float, sextets: list[np.ndarray]) -> np.ndarray:
    y = baseline + slope * v
    for p in sextets:
        y -= sextet_absorption(v, *p)
    return y


def sextet_model(v: np.ndarray, delta: float, quad: float, bhf: float, gamma: float,
                 depth: float, baseline: float, slope: float, int1: float,
                 int2: float, int3: float) -> np.ndarray:
    """Compatibilidad: un sextete con una sola anchura."""
    return total_model(v, baseline, slope, [np.array([delta, quad, bhf, gamma, 1.0, 1.0, depth, int1, int2, int3])])


class MossbauerFe33GUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Ajuste Mossbauer Fe-57, BHF ajustable")
        self.geometry("1250x780")

        self.file_path: Path | None = None
        self.counts: np.ndarray | None = None
        self.folded_raw: np.ndarray | None = None
        self.y_data: np.ndarray | None = None
        self.velocity: np.ndarray | None = None
        self.pairs: list[tuple[int, int]] = []
        self.norm_factor = 1.0
        self.updating_sliders = False
        self.fit_velocity_var = tk.BooleanVar(value=False)
        self.sextet_enabled: dict[int, tk.BooleanVar] = {1: tk.BooleanVar(value=True), 2: tk.BooleanVar(value=False), 3: tk.BooleanVar(value=False)}

        self.vars: dict[str, tk.DoubleVar] = {}
        self.entry_vars: dict[str, tk.StringVar] = {}
        self.fixed_vars: dict[str, tk.BooleanVar] = {}
        self.slider_specs: dict[str, tuple[float, float, float]] = {}

        self._build_ui()

        for default in (Path("FE040723.ws5"), Path("Ja271025.ws5")):
            if default.exists():
                self.load_ws5(default)
                break

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self.configure(background="#edf4fb")
        style.configure("TFrame", background="#edf4fb")
        style.configure("TLabelframe", background="#edf4fb", borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background="#edf4fb")
        style.configure("TLabel", background="#edf4fb", foreground="#17202a")
        style.configure("Title.TLabel", font=("TkDefaultFont", 17, "bold"), foreground="#165a8f", background="#edf4fb")
        style.configure("Subtitle.TLabel", font=("TkDefaultFont", 9), foreground="#5d6d7e", background="#edf4fb")
        style.configure("Section.TLabelframe", padding=10, background="#edf4fb", relief="solid")
        style.configure("Section.TLabelframe.Label", font=("TkDefaultFont", 10, "bold"), foreground="#165a8f", background="#edf4fb")
        style.configure("Accent.TButton", padding=7, font=("TkDefaultFont", 9, "bold"), background="#4aa3df", foreground="white")
        style.map("Accent.TButton", background=[("active", "#2f8fca")])
        style.configure("Small.TButton", padding=5, background="#d9ecfb")

        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True)

        left_outer = ttk.Frame(main, width=455, padding=10)
        left_outer.pack(side=tk.LEFT, fill=tk.Y)
        left_outer.pack_propagate(False)

        controls = ttk.Frame(left_outer)
        controls.pack(fill=tk.BOTH, expand=True)

        plot_frame = ttk.Frame(main, padding=(6, 6, 8, 8))
        plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        ttk.Label(controls, text="Mössbauer Fe-57", style="Title.TLabel").pack(anchor=tk.W, pady=(0, 0))
        ttk.Label(controls, text="Doblado Normos + ajuste interactivo", style="Subtitle.TLabel").pack(anchor=tk.W, pady=(0, 8))

        file_box = ttk.LabelFrame(controls, text="Fichero y acciones", style="Section.TLabelframe")
        file_box.pack(fill=tk.X, pady=(0, 8))
        for col in (0, 1):
            file_box.columnconfigure(col, weight=1)
        ttk.Button(file_box, text="Cargar", command=self.open_file, style="Accent.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=3)
        ttk.Button(file_box, text="Mössbauer web", command=self.open_web_download_dialog).grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=3)
        ttk.Button(file_box, text="Calibraciones", command=self.open_calibration_download_dialog).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=3)
        ttk.Button(file_box, text="Buscar centro", command=self.auto_center).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=3)
        ttk.Button(file_box, text="Ajustar", command=self.fit_current_data).grid(row=2, column=0, sticky="ew", padx=(0, 4), pady=3)
        ttk.Button(file_box, text="Guardar", command=self.save_fit).grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=3)

        info_box = ttk.LabelFrame(controls, text="Estado y parámetros", style="Section.TLabelframe")
        info_box.pack(fill=tk.X, pady=8)
        self.info = tk.Text(
            info_box,
            width=38,
            height=12,
            wrap=tk.WORD,
            relief=tk.FLAT,
            background="#ffffff",
            foreground="#17202a",
            font=("TkDefaultFont", 9),
        )
        self.info.pack(fill=tk.X, pady=2)

        calib_box = ttk.LabelFrame(controls, text="Velocidad, folding y fondo", style="Section.TLabelframe")
        calib_box.pack(fill=tk.X, pady=8)
        self._add_slider(calib_box, "vmax", "Vmax (mm/s)", 11.8788, 1.0, 15.0, 0.0001, fit_param=False)
        ttk.Checkbutton(
            calib_box,
            text="Ajustar Vmax con el patrón de líneas (requiere BHF fijo)",
            variable=self.fit_velocity_var,
            command=self.on_fit_velocity_toggle,
        ).pack(anchor=tk.W, pady=(0, 4))
        self._add_slider(calib_box, "center", "Folding point", 256.5, 250.0, 263.0, 0.5, fit_param=False)
        self._add_slider(calib_box, "baseline", "Base", 1.0, 0.70, 1.30, 0.0005)
        self._add_slider(calib_box, "slope", "Pendiente", 0.0, -0.002, 0.002, 0.00001)

        line_box = ttk.LabelFrame(controls, text="Referencia", style="Section.TLabelframe")
        line_box.pack(fill=tk.X, pady=8)
        ttk.Label(
            line_box,
            text="Líneas Fe-57 para BHF=33 T y ΔEQ=0:\n" + ", ".join(f"{x:.3f}" for x in LINE_POS_33T) + " mm/s",
            justify=tk.LEFT,
            wraplength=350,
        ).pack(anchor=tk.W, pady=2)

        sim_box = ttk.LabelFrame(plot_frame, text="Simulación / ajuste: sextetes", style="Section.TLabelframe")
        sim_box.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
        sim_header = ttk.Frame(sim_box)
        sim_header.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(
            sim_header,
            text="Puedes activar hasta 3 sextetes. Γ2,5 y Γ3,4 son relativas a Γ1,6 (1 = iguales).",
            style="Subtitle.TLabel",
        ).pack(side=tk.LEFT, anchor=tk.W)
        ttk.Button(sim_header, text="Fijar todos", command=self.fix_all_parameters, style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(sim_header, text="Liberar todos", command=self.free_all_parameters, style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))

        notebook = ttk.Notebook(sim_box)
        notebook.pack(fill=tk.X, expand=False)
        for idx in (1, 2, 3):
            tab = ttk.Frame(notebook, padding=6)
            notebook.add(tab, text=f"Sextete {idx}")
            if idx > 1:
                ttk.Checkbutton(tab, text=f"Usar sextete {idx}", variable=self.sextet_enabled[idx], command=self.update_plot).pack(anchor=tk.W, pady=(0, 4))
            else:
                ttk.Label(tab, text="Sextete principal activo", style="Subtitle.TLabel").pack(anchor=tk.W, pady=(0, 4))
            cols = ttk.Frame(tab)
            cols.pack(fill=tk.X)
            c1 = ttk.Frame(cols); c2 = ttk.Frame(cols); c3 = ttk.Frame(cols)
            c1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
            c2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
            c3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
            p = f"s{idx}_"
            self._add_slider(c1, p + "delta", "δ isomérico", 0.0, -2.5, 2.5, 0.001)
            self._add_slider(c1, p + "quad", "ΔEQ", 0.0, -2.0, 2.0, 0.001)
            self._add_slider(c1, p + "bhf", "BHF (T)", BHF_DEFAULT_T, 20.0, 50.0, 0.01)
            self._add_slider(c2, p + "gamma1", "Γ 1,6", 0.30, 0.03, 2.0, 0.001)
            self._add_slider(c2, p + "gamma2", "Γ 2,5 rel", 1.0, 0.2, 3.0, 0.001)
            self._add_slider(c2, p + "gamma3", "Γ 3,4 rel", 1.0, 0.2, 3.0, 0.001)
            self._add_slider(c3, p + "depth", "Profundidad", 0.030 if idx == 1 else 0.005, 0.0, 0.30, 0.0005)
            self._add_slider(c3, p + "int1", "I1", 1.0, 0.0, 2.0, 0.001)
            self._add_slider(c3, p + "int2", "I2 rel", 1.0, 0.0, 3.0, 0.001)
            self._add_slider(c3, p + "int3", "I3 rel", 1.0, 0.0, 3.0, 0.001)

        plot_area = ttk.Frame(plot_frame)
        plot_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.fig = Figure(figsize=(8.5, 5.2), dpi=100, facecolor="#ffffff")
        self.ax = self.fig.add_subplot(111)
        self.ax.set_ylabel("Transmisión normalizada")
        self.ax.set_xlabel("Velocidad (mm/s)")
        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_area)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        toolbar = NavigationToolbar2Tk(self.canvas, plot_area)
        toolbar.update()

    def _add_slider(self, parent: ttk.Frame, key: str, label: str, value: float,
                    min_value: float, max_value: float, resolution: float,
                    fit_param: bool = True) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=4)

        top = ttk.Frame(frame)
        top.pack(fill=tk.X)
        ttk.Label(top, text=label).pack(side=tk.LEFT, anchor=tk.W)

        var = tk.DoubleVar(value=value)
        entry_var = tk.StringVar(value=self._format_value(key, value))
        if fit_param:
            fixed_var = tk.BooleanVar(value=False)
            fixed = ttk.Checkbutton(top, text="fijo", variable=fixed_var)
            fixed.pack(side=tk.RIGHT, padx=(6, 0))
            self.fixed_vars[key] = fixed_var

        entry = ttk.Entry(top, textvariable=entry_var, width=12, justify=tk.RIGHT)
        entry.pack(side=tk.RIGHT)
        entry.bind("<Return>", lambda _event, k=key: self.apply_entry_value(k))
        entry.bind("<FocusOut>", lambda _event, k=key: self.apply_entry_value(k))

        slider = tk.Scale(
            frame,
            from_=min_value,
            to=max_value,
            resolution=resolution,
            orient=tk.HORIZONTAL,
            variable=var,
            showvalue=False,
            length=210,
            bd=0,
            highlightthickness=0,
            background="#f4f6fb",
            troughcolor="#d9e2f3",
            activebackground="#4c78a8",
            command=lambda _v, k=key: self.on_slider(k),
        )
        slider.pack(fill=tk.X)

        self.vars[key] = var
        self.entry_vars[key] = entry_var
        self.slider_specs[key] = (min_value, max_value, resolution)

    def _format_value(self, key: str, value: float) -> str:
        base = key.split("_", 1)[-1]
        if key == "center":
            return f"{value:.1f}"
        if base == "slope":
            return f"{value:.6f}"
        if key == "vmax" or base in {"delta", "quad", "gamma1", "gamma2", "gamma3", "depth", "baseline", "int1", "int2", "int3"}:
            return f"{value:.6g}"
        return f"{value:.5g}"

    def _snap_value(self, key: str, value: float) -> float:
        min_value, max_value, resolution = self.slider_specs[key]
        value = max(min_value, min(max_value, value))
        if key == "center":
            return round(value * 2.0) / 2.0
        if resolution > 0:
            return round(value / resolution) * resolution
        return value

    def apply_entry_value(self, key: str) -> None:
        try:
            value = float(self.entry_vars[key].get().replace(",", "."))
        except ValueError:
            value = self.vars[key].get()
        value = self._snap_value(key, value)

        self.updating_sliders = True
        self.vars[key].set(value)
        self.entry_vars[key].set(self._format_value(key, value))
        self.updating_sliders = False

        if key in {"center", "vmax"}:
            self.refold_data()
        self.update_plot()

    def fix_all_parameters(self) -> None:
        for var in self.fixed_vars.values():
            var.set(True)

    def free_all_parameters(self) -> None:
        for var in self.fixed_vars.values():
            var.set(False)
        if self.fit_velocity_var.get():
            # La calibracion de velocidad solo tiene sentido con BHF fijo.
            for key in self.active_bhf_keys():
                self.fixed_vars[key].set(True)

    def on_fit_velocity_toggle(self) -> None:
        if self.fit_velocity_var.get():
            for key in self.active_bhf_keys():
                self.fixed_vars[key].set(True)
            messagebox.showinfo(
                "Ajuste de velocidad",
                "Se ha fijado BHF. La velocidad Vmax se ajustará usando el patrón de líneas del sextete.",
            )

    def open_calibration_download_dialog(self) -> None:
        self.open_web_download_dialog("https://matelec.qfa.uam.es/lab/calibraciones/", "calibraciones")

    def open_web_download_dialog(self, default_url: str = "https://matelec.qfa.uam.es/lab/mossbauer/", kind: str = "mossbauer") -> None:
        """Ventana sencilla para listar/descargar datos de una web con usuario y contraseña."""
        try:
            import requests
        except Exception as exc:
            messagebox.showerror("Web", f"No se pudo importar requests: {exc}")
            return

        cred_path = Path.home() / ".config" / "mossbauer_fe33_gui" / "credentials.json"
        saved_user = ""
        saved_pass = ""
        if cred_path.exists():
            try:
                saved = json.loads(cred_path.read_text(encoding="utf-8"))
                saved_user = saved.get("username", "")
                saved_pass = saved.get("password", "")
            except Exception:
                pass

        dialog = tk.Toplevel(self)
        dialog.title("Descargar datos desde web")
        dialog.geometry("780x560")
        dialog.transient(self)
        dialog.configure(background="#edf4fb")

        session = requests.Session()
        found_links: list[tuple[str, str]] = []

        frm = ttk.Frame(dialog, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Página o URL directa:").grid(row=0, column=0, sticky="w", pady=3)
        url_var = tk.StringVar(value=default_url)
        ttk.Entry(frm, textvariable=url_var).grid(row=0, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(frm, text="Usuario:").grid(row=1, column=0, sticky="w", pady=3)
        user_var = tk.StringVar(value=saved_user)
        ttk.Entry(frm, textvariable=user_var).grid(row=1, column=1, sticky="ew", pady=3)

        ttk.Label(frm, text="Contraseña:").grid(row=2, column=0, sticky="w", pady=3)
        pass_var = tk.StringVar(value=saved_pass)
        ttk.Entry(frm, textvariable=pass_var, show="•").grid(row=2, column=1, sticky="ew", pady=3)
        remember_var = tk.BooleanVar(value=bool(saved_user or saved_pass))
        ttk.Checkbutton(
            frm,
            text="Recordar credenciales en este ordenador (fichero local, no cifrado)",
            variable=remember_var,
        ).grid(row=2, column=2, sticky="w", padx=(8, 0), pady=3)

        status_var = tk.StringVar(value="Introduce credenciales y pulsa 'Listar' o descarga una URL directa.")
        ttk.Label(frm, textvariable=status_var, style="Subtitle.TLabel", wraplength=720).grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 8))

        listbox = tk.Listbox(frm, height=10, activestyle="dotbox")
        listbox.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=4)
        frm.rowconfigure(4, weight=1)

        debug_box = tk.Text(frm, height=8, wrap=tk.WORD, background="#111827", foreground="#d1fae5", insertbackground="#d1fae5", font=("TkFixedFont", 9))
        debug_box.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(6, 0))

        def debug(msg: str) -> None:
            debug_box.insert(tk.END, msg.rstrip() + "\n")
            debug_box.see(tk.END)
            dialog.update_idletasks()

        def save_credentials_if_requested() -> None:
            try:
                if remember_var.get():
                    cred_path.parent.mkdir(parents=True, exist_ok=True)
                    cred_path.write_text(
                        json.dumps({"username": user_var.get().strip(), "password": pass_var.get()}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    os.chmod(cred_path, 0o600)
                    debug(f"Credenciales guardadas en {cred_path} (texto local no cifrado).")
                elif cred_path.exists():
                    cred_path.unlink()
                    debug("Credenciales guardadas eliminadas.")
            except Exception as exc:
                debug(f"No se pudieron guardar/eliminar credenciales: {exc}")

        def response_for(url: str):
            debug(f"GET {url}")
            r = session.get(url, timeout=30, allow_redirects=True)
            debug(f"  -> status={r.status_code} final={r.url}")
            debug(f"  -> content-type={r.headers.get('content-type', '')} bytes={len(r.content)}")
            if r.history:
                debug("  -> redirects: " + " -> ".join(f"{h.status_code}:{h.url}" for h in r.history))
            return r

        def parse_inputs(form_html: str) -> dict[str, str]:
            data: dict[str, str] = {}
            for input_tag in re.findall(r"<input\b[^>]*>", form_html, flags=re.S | re.I):
                name_m = re.search(r"\bname=[\"']([^\"']+)[\"']", input_tag, flags=re.I)
                if not name_m:
                    continue
                value_m = re.search(r"\bvalue=[\"']([^\"']*)[\"']", input_tag, flags=re.I)
                data[unescape(name_m.group(1))] = unescape(value_m.group(1)) if value_m else ""
            return data

        def input_name(form_html: str, input_type: str, preferred: tuple[str, ...] = ()) -> str | None:
            candidates: list[str] = []
            for input_tag in re.findall(r"<input\b[^>]*>", form_html, flags=re.S | re.I):
                type_m = re.search(r"\btype=[\"']([^\"']+)[\"']", input_tag, flags=re.I)
                typ = type_m.group(1).lower() if type_m else "text"
                if typ != input_type:
                    continue
                name_m = re.search(r"\bname=[\"']([^\"']+)[\"']", input_tag, flags=re.I)
                if name_m:
                    candidates.append(unescape(name_m.group(1)))
            for pref in preferred:
                for cand in candidates:
                    if cand.lower() == pref:
                        return cand
            return candidates[0] if candidates else None

        def ensure_form_login(target_url: str) -> bool:
            """Hace login Django/formulario si la petición acaba en una página de login."""
            save_credentials_if_requested()
            user = user_var.get().strip()
            password = pass_var.get()
            if not user and not password:
                debug("LOGIN: sin usuario/contraseña; se intenta acceso como sesión ya abierta/anónima.")
                return True

            debug("LOGIN: comprobando si la página redirige a formulario de acceso...")
            r = response_for(target_url)
            text = r.text
            if re.search(r"/lab/download/(?:mossbauer|calibration)/\d+/datafile/?", text) or "Medidas Mössbauer" in text or "Calibr" in text:
                debug("LOGIN: ya estamos autenticados; la página contiene la tabla de datos.")
                return True

            forms = re.findall(r"<form\b.*?</form>", text, flags=re.S | re.I)
            login_form = None
            for form in forms:
                if re.search(r"type=[\"']password[\"']", form, flags=re.I):
                    login_form = form
                    break
            if login_form is None:
                debug("LOGIN: no encuentro formulario con campo password en la página recibida.")
                debug("LOGIN: primeros 500 caracteres HTML: " + re.sub(r"\s+", " ", text[:500]))
                return False

            action_m = re.search(r"<form\b[^>]*\baction=[\"']([^\"']*)[\"']", login_form, flags=re.S | re.I)
            post_url = urljoin(r.url, unescape(action_m.group(1))) if action_m else r.url
            method_m = re.search(r"<form\b[^>]*\bmethod=[\"']([^\"']*)[\"']", login_form, flags=re.S | re.I)
            method = method_m.group(1).lower() if method_m else "post"

            data = parse_inputs(login_form)
            user_name = input_name(login_form, "text", ("username", "user", "login", "email")) or input_name(login_form, "email", ("email", "username"))
            pass_name = input_name(login_form, "password", ("password", "passwd"))
            if user_name is None or pass_name is None:
                debug(f"LOGIN: no pude detectar campos. user_name={user_name}, pass_name={pass_name}, inputs={list(data)}")
                return False
            data[user_name] = user
            data[pass_name] = password
            # Muchos formularios Django usan ?next=... en la action o hidden next.
            if "next" in data and not data["next"]:
                data["next"] = urlparse(target_url).path

            debug(f"LOGIN: POST {post_url} method={method} user_field={user_name} pass_field={pass_name} campos={list(data.keys())}")
            headers = {"Referer": r.url}
            if method == "get":
                r2 = session.get(post_url, params=data, headers=headers, timeout=30, allow_redirects=True)
            else:
                r2 = session.post(post_url, data=data, headers=headers, timeout=30, allow_redirects=True)
            debug(f"LOGIN: respuesta status={r2.status_code} final={r2.url} bytes={len(r2.content)}")
            if r2.history:
                debug("LOGIN: redirects: " + " -> ".join(f"{h.status_code}:{h.url}" for h in r2.history))
            if "csrf" in r2.text[:3000].lower() and re.search(r"type=[\"']password[\"']", r2.text, flags=re.I):
                debug("LOGIN: seguimos en formulario de login. Posible CSRF/campos incorrectos/credenciales no aceptadas.")
                return False

            # Comprobación final en la URL objetivo.
            r3 = response_for(target_url)
            if re.search(r"/lab/download/(?:mossbauer|calibration)/\d+/datafile/?", r3.text) or "Medidas Mössbauer" in r3.text or "Calibr" in r3.text:
                debug("LOGIN: correcto, ya se ve la tabla de datos.")
                return True
            debug("LOGIN: no se ve la tabla tras login; revisar debug de URLs y HTML.")
            return False

        def filename_from_url(url: str) -> str:
            name = Path(urlparse(url).path).name or "descarga.ws5"
            return name if name.lower().endswith(".ws5") else name + ".ws5"

        def clean_text(html_fragment: str) -> str:
            text = re.sub(r"<[^>]+>", " ", html_fragment)
            text = unescape(text)
            return re.sub(r"\s+", " ", text).strip()

        def safe_filename(text: str, max_len: int = 90) -> str:
            text = unescape(text).strip()
            text = re.sub(r"[^\w.()+\-]+", "_", text, flags=re.UNICODE).strip("_")
            return (text[:max_len] or "mossbauer")

        def name_from_row(row_html: str, download_url: str, data_kind: str) -> str:
            m_id = re.search(r"/(?:mossbauer|calibration)/(\d+)/datafile/", download_url)
            item_id = m_id.group(1) if m_id else ""
            m_sample = re.search(r"<strong>(.*?)</strong>", row_html, flags=re.S | re.I)
            sample = clean_text(m_sample.group(1)) if m_sample else data_kind
            m_date = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", row_html)
            date = m_date.group(1) if m_date else "sin_fecha"
            prefix = "cal" if data_kind == "calibration" else "moss"
            return safe_filename(f"{date}_{prefix}_{sample}_{item_id}") + ".ws5"

        def list_ws5() -> None:
            """Lee la tabla paginada de Mössbauer o calibraciones y extrae los enlaces de datos."""
            nonlocal found_links
            start_url = url_var.get().strip()
            if not start_url:
                return

            listbox.delete(0, tk.END)
            found: dict[str, str] = {}
            visited: set[str] = set()
            if not ensure_form_login(start_url):
                status_var.set("No se pudo completar el login. Mira el panel debug.")
                return
            queue: list[str] = [start_url]
            max_pages = 80
            start = urlparse(start_url)
            base_netloc = start.netloc
            data_kind = "calibration" if "calibraciones" in start.path else "mossbauer"
            list_path = "/lab/calibraciones" if data_kind == "calibration" else "/lab/mossbauer"
            download_re = re.compile(rf"/lab/download/{data_kind}/\d+/datafile/?")

            def clean_url(url: str) -> str:
                p = urlparse(url)
                return p._replace(fragment="").geturl()

            def add_download(url: str, name: str) -> None:
                found[url] = name

            try:
                while queue and len(visited) < max_pages:
                    current = clean_url(queue.pop(0))
                    if current in visited:
                        continue
                    visited.add(current)
                    status_var.set(f"Leyendo página {len(visited)}... encontrados {len(found)} espectros")
                    dialog.update_idletasks()

                    r = response_for(current)
                    try:
                        r.raise_for_status()
                    except Exception as exc:
                        debug(f"  !! HTTP error: {exc}")
                        continue
                    text = r.text
                    lower_head = text[:3000].lower()
                    debug(f"  -> title={re.search(r'<title>(.*?)</title>', text, flags=re.S|re.I).group(1).strip() if re.search(r'<title>(.*?)</title>', text, flags=re.S|re.I) else 'sin title'}")
                    debug(f"  -> contains table={ '<table' in lower_head or '<table' in text.lower() }, login/form={ '<form' in lower_head }, data-links={len(download_re.findall(text))}")
                    if any(s in lower_head for s in ("login", "iniciar sesión", "csrfmiddlewaretoken")):
                        debug("  !! Parece página de login o formulario. Si no aparecen datos, la web no acepta autenticación básica y requiere login por formulario.")

                    # Caso URL directa a fichero ws5.
                    if current.lower().endswith(".ws5") or "<data" in lower_head:
                        debug("  -> parece WS5 directo")
                        add_download(r.url, filename_from_url(r.url))
                        continue

                    # En la tabla, los ficheros están en enlaces como:
                    # /lab/download/mossbauer/1357/datafile/  con texto "↓ datos".
                    rows = re.findall(r"<tr\b.*?</tr>", text, flags=re.S | re.I)
                    debug(f"  -> filas <tr>: {len(rows)}")
                    before = len(found)
                    for row in rows:
                        hrefs = re.findall(r"href=[\"']([^\"']+)[\"']", row, flags=re.I)
                        for href in hrefs:
                            href = unescape(href).strip()
                            if download_re.search(href):
                                full = clean_url(urljoin(r.url, href))
                                name = name_from_row(row, full, data_kind)
                                debug(f"     datos: {name} -> {full}")
                                add_download(full, name)
                    debug(f"  -> nuevos datos en esta página: {len(found)-before}")

                    # Compatibilidad por si hay enlaces directos .ws5 en alguna página.
                    page_links = 0
                    for href in re.findall(r"href=[\"']([^\"']+)[\"']", text, flags=re.I):
                        href = unescape(href).strip()
                        if not href or href.startswith(("#", "mailto:", "javascript:")):
                            continue
                        full = clean_url(urljoin(r.url, href))
                        parsed = urlparse(full)
                        if parsed.netloc != base_netloc:
                            continue
                        if ".ws5" in full.lower():
                            add_download(full, filename_from_url(full))
                        # Seguir solo paginación de la lista, no páginas Ver/Editar.
                        elif parsed.path.rstrip("/") == list_path and "page=" in parsed.query:
                            page_links += 1
                            if full not in visited and full not in queue:
                                queue.append(full)
                    debug(f"  -> enlaces de paginación añadidos/vistos: {page_links}; cola={len(queue)}")
            except Exception as exc:
                debug(f"EXCEPCIÓN: {type(exc).__name__}: {exc}")
                status_var.set(f"Error leyendo la lista paginada: {type(exc).__name__}: {exc}")
                return

            # Los nombres empiezan por fecha ISO cuando se puede extraer: ordenar nuevo -> viejo.
            found_links = [(name, url) for url, name in sorted(found.items(), key=lambda item: item[1].lower(), reverse=True)]
            listbox.delete(0, tk.END)
            for name, full in found_links:
                listbox.insert(tk.END, f"{name}    {full}")

            if found_links:
                status_var.set(
                    f"Encontrados {len(found_links)} espectros en {len(visited)} páginas. Selecciona uno y pulsa Descargar."
                )
            else:
                status_var.set(f"No encontré enlaces de datos tras revisar {len(visited)} páginas. Mira el panel debug para ver status, redirects y HTML recibido.")

        def download_selected() -> None:
            save_credentials_if_requested()
            if found_links and listbox.curselection():
                name, file_url = found_links[listbox.curselection()[0]]
            else:
                file_url = url_var.get().strip()
                name = filename_from_url(file_url)
            if not file_url:
                return
            try:
                r = response_for(file_url)
                r.raise_for_status()
                content = r.content
            except Exception as exc:
                status_var.set(f"Error descargando: {exc}")
                return

            save_path = filedialog.asksaveasfilename(
                title="Guardar .ws5 descargado",
                initialfile=name,
                defaultextension=".ws5",
                filetypes=[("Wissoft WS5", "*.ws5"), ("Todos", "*")],
            )
            if not save_path:
                return
            path = Path(save_path)
            path.write_bytes(content)
            status_var.set(f"Descargado: {path}")
            self.load_ws5(path)
            dialog.destroy()

        buttons = ttk.Frame(frm)
        buttons.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        ttk.Button(buttons, text="Listar", command=list_ws5).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(buttons, text="Descargar", command=download_selected, style="Accent.TButton").grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def open_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Selecciona fichero .ws5",
            filetypes=[("Wissoft WS5", "*.ws5"), ("Todos", "*")],
        )
        if filename:
            self.load_ws5(Path(filename))

    def load_ws5(self, path: Path) -> None:
        try:
            counts = read_ws5_counts(path)
        except Exception as exc:
            messagebox.showerror("Error al cargar", str(exc))
            return
        self.file_path = path
        self.counts = counts
        center = find_best_integer_or_half_center(counts)
        self.updating_sliders = True
        self.vars["center"].set(center)
        self.entry_vars["center"].set(self._format_value("center", center))
        self.updating_sliders = False
        self.refold_data()
        self.guess_initial_parameters()
        self.update_plot()

    def refold_data(self) -> None:
        if self.counts is None:
            return
        center = round(self.vars["center"].get() * 2.0) / 2.0
        self.vars["center"].set(center)
        self.entry_vars["center"].set(self._format_value("center", center))
        folded, pairs = fold_integer_or_half(self.counts, center)
        self.folded_raw = folded
        self.pairs = pairs
        if folded.size:
            # Normaliza a una linea base cercana a 1 sin destruir las cuentas originales.
            self.norm_factor = float(np.percentile(folded, 90))
            if self.norm_factor == 0:
                self.norm_factor = 1.0
            self.y_data = folded / self.norm_factor
            vmax = abs(self.vars["vmax"].get())
            self.velocity = np.linspace(-vmax, vmax, folded.size)
        else:
            self.y_data = None
            self.velocity = None

    def guess_initial_parameters(self) -> None:
        if self.y_data is None or self.y_data.size == 0:
            return
        y = self.y_data
        baseline = float(np.percentile(y, 90))
        depth = max(0.005, min(0.25, baseline - float(np.min(y))))
        params = {"baseline": baseline, "slope": 0.0}
        for idx in (1, 2, 3):
            p = f"s{idx}_"
            params.update({
                p + "depth": depth / 2.5 if idx == 1 else 0.005,
                p + "gamma1": 0.30,
                p + "gamma2": 1.0,
                p + "gamma3": 1.0,
                p + "delta": 0.0,
                p + "quad": 0.0,
                p + "bhf": BHF_DEFAULT_T,
                p + "int1": 1.0,
                p + "int2": 1.0,
                p + "int3": 1.0,
            })
        self.set_params(params)

    def auto_center(self) -> None:
        if self.counts is None:
            return
        center = find_best_integer_or_half_center(self.counts)
        self.vars["center"].set(center)
        self.entry_vars["center"].set(self._format_value("center", center))
        self.refold_data()
        self.update_plot()

    def active_param_keys(self) -> list[str]:
        keys = GLOBAL_PARAM_NAMES.copy()
        for idx in (1, 2, 3):
            if self.sextet_enabled[idx].get():
                keys.extend(f"s{idx}_{name}" for name in SEXTET_PARAM_NAMES)
        return keys

    def active_bhf_keys(self) -> list[str]:
        return [f"s{idx}_bhf" for idx in (1, 2, 3) if self.sextet_enabled[idx].get()]

    def build_sextets_from_vars(self) -> list[np.ndarray]:
        sextets: list[np.ndarray] = []
        for idx in (1, 2, 3):
            if not self.sextet_enabled[idx].get():
                continue
            p = f"s{idx}_"
            sextets.append(np.array([self.vars[p + name].get() for name in SEXTET_PARAM_NAMES], dtype=float))
        return sextets

    def set_params(self, params: dict[str, float] | np.ndarray, names: list[str] | None = None) -> None:
        self.updating_sliders = True
        if isinstance(params, dict):
            items = params.items()
        else:
            items = zip(names or self.active_param_keys(), params)
        for key, value in items:
            if key in self.vars:
                value = float(value)
                self.vars[key].set(value)
                self.entry_vars[key].set(self._format_value(key, value))
        self.updating_sliders = False

    def on_slider(self, key: str) -> None:
        value = self.vars[key].get()
        self.entry_vars[key].set(self._format_value(key, value))
        if self.updating_sliders:
            return
        if key in {"center", "vmax"}:
            self.refold_data()
        self.update_plot()

    def current_model(self) -> np.ndarray | None:
        if self.velocity is None:
            return None
        return total_model(
            self.velocity,
            self.vars["baseline"].get(),
            self.vars["slope"].get(),
            self.build_sextets_from_vars(),
        )

    def bounds_for_key(self, key: str) -> tuple[float, float]:
        base = key.split("_", 1)[-1]
        bounds = {
            "baseline": (0.70, 1.30),
            "slope": (-0.002, 0.002),
            "delta": (-2.5, 2.5),
            "quad": (-2.0, 2.0),
            "bhf": (20.0, 50.0),
            "gamma1": (0.03, 2.0),
            "gamma2": (0.2, 3.0),
            "gamma3": (0.2, 3.0),
            "depth": (0.0, 0.30),
            "int1": (0.0, 2.0),
            "int2": (0.0, 3.0),
            "int3": (0.0, 3.0),
        }
        return bounds[base]

    def model_from_values(self, values: dict[str, float], vmax: float) -> np.ndarray:
        assert self.y_data is not None
        v = np.linspace(-vmax, vmax, self.y_data.size)
        sextets: list[np.ndarray] = []
        for idx in (1, 2, 3):
            if self.sextet_enabled[idx].get():
                p = f"s{idx}_"
                sextets.append(np.array([values[p + name] for name in SEXTET_PARAM_NAMES], dtype=float))
        return total_model(v, values["baseline"], values["slope"], sextets)

    def fit_current_data(self) -> None:
        if self.velocity is None or self.y_data is None:
            return
        y = self.y_data
        keys = self.active_param_keys()
        values0 = {key: self.vars[key].get() for key in keys}

        fit_velocity = self.fit_velocity_var.get()
        if fit_velocity and not all(self.fixed_vars[k].get() for k in self.active_bhf_keys()):
            messagebox.showwarning(
                "Ajuste de velocidad",
                "Para ajustar la velocidad con el patrón, fija el BHF de todos los sextetes activos.",
            )
            return

        free_keys = [key for key in keys if not self.fixed_vars.get(key, tk.BooleanVar(value=False)).get()]
        if not free_keys and not fit_velocity:
            messagebox.showinfo("Ajuste", "Todos los parámetros están fijados. Libera alguno para ajustar.")
            return

        x0 = [values0[key] for key in free_keys]
        lo = []
        hi = []
        for key in free_keys:
            a, b = self.bounds_for_key(key)
            lo.append(a); hi.append(b)
        if fit_velocity:
            x0.append(abs(self.vars["vmax"].get()))
            lo.append(self.slider_specs["vmax"][0])
            hi.append(self.slider_specs["vmax"][1])
        x0_arr = np.array(x0, dtype=float)
        lo_arr = np.array(lo, dtype=float)
        hi_arr = np.array(hi, dtype=float)
        x0_arr = np.clip(x0_arr, lo_arr, hi_arr)

        def unpack(x: np.ndarray) -> tuple[dict[str, float], float]:
            values = values0.copy()
            for key, value in zip(free_keys, x[:len(free_keys)]):
                values[key] = float(value)
            vmax = float(x[len(free_keys)]) if fit_velocity else abs(self.vars["vmax"].get())
            return values, vmax

        def residual(x: np.ndarray) -> np.ndarray:
            values, vmax = unpack(x)
            return self.model_from_values(values, vmax) - y

        try:
            result = least_squares(residual, x0_arr, bounds=(lo_arr, hi_arr), max_nfev=7000)
        except Exception as exc:
            messagebox.showerror("Error en el ajuste", str(exc))
            return

        values_final, vmax_final = unpack(result.x)
        self.set_params(values_final)
        if fit_velocity:
            self.vars["vmax"].set(vmax_final)
            self.entry_vars["vmax"].set(self._format_value("vmax", vmax_final))
            self.refold_data()
        self.update_plot()

    def update_plot(self) -> None:
        self.ax.clear()
        self.ax.set_facecolor("#fbfcff")
        self.ax.set_title("Datos doblados y modelo", color="#203040", pad=8)
        self.ax.set_ylabel("Transmisión normalizada")
        self.ax.set_xlabel("Velocidad (mm/s)")
        self.ax.grid(True, color="#d5dce8", alpha=0.7)

        if self.velocity is not None and self.y_data is not None:
            model = self.current_model()
            self.ax.plot(self.velocity, self.y_data, ".", color="#1f2933", ms=4, label="Datos doblados")
            if model is not None:
                baseline_line = self.vars["baseline"].get() + self.vars["slope"].get() * self.velocity
                self.ax.plot(self.velocity, baseline_line, ":", color="#7f8c8d", lw=1.1, label="Fondo")

                component_colors = {1: "#2ca02c", 2: "#ff7f0e", 3: "#9467bd"}
                for idx in (1, 2, 3):
                    if not self.sextet_enabled[idx].get():
                        continue
                    p = f"s{idx}_"
                    params = np.array([self.vars[p + name].get() for name in SEXTET_PARAM_NAMES], dtype=float)
                    component = baseline_line - sextet_absorption(self.velocity, *params)
                    self.ax.plot(
                        self.velocity,
                        component,
                        "--",
                        color=component_colors[idx],
                        lw=1.5,
                        alpha=0.95,
                        label=f"Sextete {idx}",
                    )

                self.ax.plot(self.velocity, model, "-", color="#d62728", lw=2.4, label="Modelo global")
                rms = float(np.sqrt(np.mean((self.y_data - model) ** 2)))
            else:
                rms = float("nan")
            self.ax.legend(loc="best")
            self.update_info(rms)
        else:
            self.ax.text(0.5, 0.5, "Carga un fichero .ws5", transform=self.ax.transAxes,
                         ha="center", va="center")
        self.fig.tight_layout()
        self.canvas.draw_idle()

    def update_info(self, rms: float) -> None:
        if self.counts is None or self.folded_raw is None:
            return
        center = self.vars["center"].get()
        active = [idx for idx in (1, 2, 3) if self.sextet_enabled[idx].get()]
        fixed = [k for k in self.active_param_keys() if self.fixed_vars[k].get()]
        text = [
            f"Fichero: {self.file_path.name if self.file_path else '-'}",
            f"Canales leídos: {self.counts.size}",
            f"Folding point: {center:.1f}",
            f"Pares doblados: {len(self.pairs)}",
            f"Normalización: / {self.norm_factor:.6g}",
            f"Vmax = {self.vars['vmax'].get():.6g} mm/s",
            f"Base = {self.vars['baseline'].get():.6g}",
            f"Pendiente = {self.vars['slope'].get():.6g}",
            f"Sextetes activos: {', '.join(map(str, active))}",
            f"Ajuste velocidad: {'sí, con patrón' if self.fit_velocity_var.get() else 'no'}",
            f"RMS ajuste: {rms:.6g}",
            "",
        ]
        for idx in active:
            p = f"s{idx}_"
            i1 = self.vars[p + 'int1'].get()
            i2_real = i1 * (2/3) * self.vars[p + 'int2'].get()
            i3_real = i1 * (1/3) * self.vars[p + 'int3'].get()
            g1 = self.vars[p + 'gamma1'].get()
            g2 = g1 * self.vars[p + 'gamma2'].get()
            g3 = g1 * self.vars[p + 'gamma3'].get()
            text.extend([
                f"Sextete {idx}: BHF={self.vars[p+'bhf'].get():.6g} T, δ={self.vars[p+'delta'].get():.6g}, ΔEQ={self.vars[p+'quad'].get():.6g}",
                f"  Γ reales 1/2/3 = {g1:.4g} / {g2:.4g} / {g3:.4g}",
                f"  Γ rel 2/3 = {self.vars[p+'gamma2'].get():.4g} / {self.vars[p+'gamma3'].get():.4g}",
                f"  prof={self.vars[p+'depth'].get():.6g}, I reales={i1:.4g}, {i2_real:.4g}, {i3_real:.4g}",
            ])
        text.extend(["", "Fijados: " + (", ".join(fixed) if fixed else "ninguno")])
        self.info.delete("1.0", tk.END)
        self.info.insert(tk.END, "\n".join(text))

    def save_fit(self) -> None:
        if self.velocity is None or self.y_data is None or self.folded_raw is None:
            return
        model = self.current_model()
        if model is None:
            return
        default_name = (self.file_path.stem if self.file_path else "espectro") + "_fe33_fit.dat"
        filename = filedialog.asksaveasfilename(
            title="Guardar ajuste",
            initialfile=default_name,
            defaultextension=".dat",
            filetypes=[("Datos", "*.dat"), ("Todos", "*")],
        )
        if not filename:
            return
        with Path(filename).open("w", encoding="utf-8") as f:
            f.write("# velocidad_mm/s\tdatos_norm\tajuste_norm\tresiduo\tcuentas_dobladas\n")
            for v, y, m, raw in zip(self.velocity, self.y_data, model, self.folded_raw):
                f.write(f"{v:.8f}\t{y:.8f}\t{m:.8f}\t{(y-m):.8f}\t{raw:.6f}\n")
        messagebox.showinfo("Guardado", f"Ajuste guardado en:\n{filename}")


if __name__ == "__main__":
    app = MossbauerFe33GUI()
    app.mainloop()
