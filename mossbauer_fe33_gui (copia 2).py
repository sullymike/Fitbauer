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
from urllib.parse import unquote, urljoin, urlparse

import numpy as np
from scipy.optimize import least_squares

from mossbauer_distribution import (
    fit_bhf_distribution as fit_bhf_distribution_engine,
    scan_alpha as scan_bhf_alpha_engine,
    second_difference_matrix,
)

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
    """Posiciones de las 6 líneas del sextete Fe-57 según las constantes del
    simulador web (≡ 10.657, 6.167, 1.677 mm/s a 32.95 T). Coincide con la
    fórmula usada por _fit_calibration_fefoil en lab/views.py.
    """
    base = np.array([-10.657, -6.167, -1.677, 1.677, 6.167, 10.657]) * 0.5
    return base * (bhf_t / 32.95)


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
    """Lee cuentas de ficheros WS5 XML o ADT antiguos sin cabecera.

    Los WS5 modernos tienen un bloque <data>...</data>. Algunos ficheros antiguos
    descargados de la web son ADT: solo una lista de cuentas, sin XML ni cabecera.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<data[^>]*>(.*?)</data>", text, re.S | re.I)
    source = m.group(1) if m else text
    counts = np.array([float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", source)])
    if counts.size < 2:
        raise ValueError(f"No se encontraron cuentas suficientes en {path}")
    return counts


def _number_re() -> str:
    return r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[EeDd][-+]?\d+)?"


def read_normos_folding_point(path: Path) -> float | None:
    """Lee el 'Final folding point' de Normos si existe y lo pasa a centro interno."""
    res = path.with_suffix(".RES")
    if not res.exists():
        res = path.with_suffix(".res")
    if not res.exists():
        return None
    text = res.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"Final folding point\s*=\s*(" + _number_re() + ")", text, re.I)
    if not matches:
        return None
    # Normos informa el punto de retorno superior de una rampa triangular
    # (≈511.55 para 512 canales). El centro de simetría usado aquí es la mitad.
    return 0.5 * float(matches[-1].replace("D", "E").replace("d", "E"))


def read_normos_plt_velocity(path: Path) -> float | None:
    """Lee Vmax del .PLT asociado si existe."""
    plt = path.with_suffix(".PLT")
    if not plt.exists():
        plt = path.with_suffix(".plt")
    if not plt.exists():
        return None
    text = plt.read_text(encoding="utf-8", errors="replace")
    nums = [float(x.replace("D", "E").replace("d", "E")) for x in re.findall(_number_re(), text)]
    # El primer número suele venir de la cabecera "2d"; después hay bloques de 256.
    if len(nums) % 256 == 1:
        nums = nums[1:]
    if len(nums) >= 256:
        return float(max(abs(min(nums[:256])), abs(max(nums[:256]))))
    return None


def read_normos_sidecar_params(path: Path) -> dict[str, float]:
    """Extrae valores finales de Normos (.RES) y parámetros fijos del .JOB."""
    params: dict[str, float] = {}
    res = path.with_suffix(".RES")
    if not res.exists():
        res = path.with_suffix(".res")
    if res.exists():
        text = res.read_text(encoding="utf-8", errors="replace")
        final: dict[str, float] = {}
        for name in ("WID", "ARE", "ISO", "QUA", "BHF"):
            m = re.search(rf"\b{name}\s+({_number_re()})\s+({_number_re()})", text, re.I)
            if m:
                final[name.upper()] = float(m.group(2).replace("D", "E").replace("d", "E"))
        if "ISO" in final:
            params["s1_delta"] = final["ISO"]
        if "BHF" in final:
            params["s1_bhf"] = final["BHF"]
        if "QUA" in final:
            params["s1_quad"] = final["QUA"]
        if "WID" in final:
            # Normos WID es FWHM; la lorentziana interna usa HWHM.
            params["s1_gamma1"] = max(0.03, final["WID"] / 2.0)
            params["s1_gamma2"] = 1.0
            params["s1_gamma3"] = 1.0
        if "ARE" in final and "s1_gamma1" in params:
            weight_sum = 2.0 * (1.0 + 2.0 / 3.0 + 1.0 / 3.0)
            params["s1_depth"] = max(0.0, min(0.30, final["ARE"] / (np.pi * params["s1_gamma1"] * weight_sum)))
    job = path.with_suffix(".JOB")
    if not job.exists():
        job = path.with_suffix(".job")
    if job.exists():
        text = job.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\bVMAX\s*=\s*(" + _number_re() + ")", text, re.I)
        if m:
            params["vmax"] = abs(float(m.group(1).replace("D", "E").replace("d", "E")))
        m = re.search(r"\bQUA\(1\)\s*=\s*(" + _number_re() + ")", text, re.I)
        if m and "s1_quad" not in params:
            params["s1_quad"] = float(m.group(1).replace("D", "E").replace("d", "E"))
    return params


def interp_channel_1based(counts: np.ndarray, channel: float) -> float:
    """Interpolación lineal C(channel) con canales 1..N; extrapola en bordes.

    Normos genera siempre NP=N/2 puntos doblados. Cuando el punto de doblado no
    deja 256 pares enteros completos, el primer/último punto se obtiene por una
    extrapolación mínima en el borde; esto evita perder un canal para centros
    como 255.5 en espectros de 512 canales.
    """
    n = counts.size
    if channel < 1.0:
        return float(counts[0] + (channel - 1.0) * (counts[1] - counts[0]))
    if channel >= float(n):
        return float(counts[-1] + (channel - float(n)) * (counts[-1] - counts[-2]))
    lo = int(np.floor(channel))
    frac = channel - lo
    if frac < 1e-12:
        return float(counts[lo - 1])
    return float((1.0 - frac) * counts[lo - 1] + frac * counts[lo])


def fold_integer_or_half(counts: np.ndarray, center: float) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Dobla a N/2 puntos al estilo Normos.

    Canales numerados 1..N. El resultado va de velocidad negativa a positiva,
    desde el par exterior izquierdo hacia el centro y de nuevo hacia el exterior
    derecho. Para centros semienteros ordinarios coincide con el promedio de
    pares simétricos; en los bordes usa interpolación/extrapolación lineal.
    """
    n = counts.size
    n_out = n // 2
    rows: list[tuple[int, int, float]] = []
    for j in range(n_out):
        distance = j + 0.5
        left_ch = center - distance
        right_ch = center + distance
        folded = 0.5 * (interp_channel_1based(counts, left_ch) + interp_channel_1based(counts, right_ch))
        rows.append((int(round(left_ch)), int(round(right_ch)), folded))
    return np.array([r[2] for r in rows], dtype=float), [(r[0], r[1]) for r in rows]


def chi2_for_center(counts: np.ndarray, center: float) -> tuple[float, int]:
    folded, pairs = fold_integer_or_half(counts, center)
    chi2 = 0.0
    for left, right in pairs:
        if not (1 <= left <= counts.size and 1 <= right <= counts.size):
            continue
        d = counts[left - 1] - counts[right - 1]
        chi2 += d * d
    return chi2, len(pairs)


def find_best_integer_or_half_center(counts: np.ndarray, cmin: float = 250.5, cmax: float = 262.5) -> float:
    """Busca el folding point con interpolación subcanal.

    Normos no se queda en canales enteros/semienteros: primero localiza el
    mínimo de chi² en una malla y después interpola el mínimo. Internamente esta
    GUI usa el centro de simetría (≈255.77 para un "upper folding point" Normos
    ≈511.55 en 512 canales), por eso el número Normos es aproximadamente el
    doble del mostrado aquí.
    """
    candidates = np.arange(cmin, cmax + 1e-9, 0.5)
    values: list[tuple[float, float]] = []
    for center in candidates:
        chi2, n_pairs = chi2_for_center(counts, float(center))
        if n_pairs:
            values.append((float(center), chi2 / n_pairs))
    if not values:
        return 0.5 * counts.size
    best_i = min(range(len(values)), key=lambda i: values[i][1])
    if 0 < best_i < len(values) - 1:
        xm, ym = values[best_i - 1]
        x0, y0 = values[best_i]
        xp, yp = values[best_i + 1]
        den = ym - 2.0 * y0 + yp
        if den > 0:
            step = x0 - xm
            xv = x0 + 0.5 * step * (ym - yp) / den
            if xm <= xv <= xp:
                return float(xv)
    return values[best_i][0]


def lorentzian(v: np.ndarray, center: float, gamma: float) -> np.ndarray:
    """Lorentziana usada en la web: γ²/((v−c)² + γ²). γ es HWHM, no FWHM.
    Para una línea con FWHM_físico = W, usa γ = W/2.
    """
    return gamma * gamma / ((v - center) ** 2 + gamma * gamma)


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


def singlet_absorption(v: np.ndarray, delta: float, gamma1: float, depth: float, int1: float) -> np.ndarray:
    return depth * int1 * lorentzian(v, delta, gamma1)


def doublet_absorption(v: np.ndarray, delta: float, quad: float, gamma1: float,
                       gamma2: float, depth: float, int1: float, int2: float) -> np.ndarray:
    g1 = gamma1
    g2 = gamma1 * gamma2
    return depth * (int1 * lorentzian(v, delta - quad / 2.0, g1) + int1 * int2 * lorentzian(v, delta + quad / 2.0, g2))


def component_absorption(v: np.ndarray, kind: str, p: np.ndarray) -> np.ndarray:
    if kind == "Singlete":
        delta, _quad, _bhf, gamma1, _gamma2, _gamma3, depth, int1, _int2, _int3 = p
        return singlet_absorption(v, delta, gamma1, depth, int1)
    if kind == "Doblete":
        delta, quad, _bhf, gamma1, gamma2, _gamma3, depth, int1, int2, _int3 = p
        return doublet_absorption(v, delta, quad, gamma1, gamma2, depth, int1, int2)
    return sextet_absorption(v, *p)


def total_model(v: np.ndarray, baseline: float, slope: float, components: list[tuple[str, np.ndarray] | np.ndarray]) -> np.ndarray:
    y = baseline + slope * v
    for comp in components:
        if isinstance(comp, tuple):
            kind, p = comp
            y -= component_absorption(v, kind, p)
        else:
            y -= sextet_absorption(v, *comp)
    return y


def sextet_model(v: np.ndarray, delta: float, quad: float, bhf: float, gamma: float,
                 depth: float, baseline: float, slope: float, int1: float,
                 int2: float, int3: float) -> np.ndarray:
    """Compatibilidad: un sextete con una sola anchura."""
    return total_model(v, baseline, slope, [np.array([delta, quad, bhf, gamma, 1.0, 1.0, depth, int1, int2, int3])])


class MossbauerFe33GUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Ajuste Mössbauer Fe-57")
        self.geometry("1350x930")
        self.minsize(1150, 840)

        self.file_path: Path | None = None
        self.counts: np.ndarray | None = None
        self.folded_raw: np.ndarray | None = None
        self.y_data: np.ndarray | None = None
        self.velocity: np.ndarray | None = None
        self.pairs: list[tuple[int, int]] = []
        self.norm_factor = 1.0
        self.updating_sliders = False
        self.fit_velocity_var = tk.BooleanVar(value=False)
        self.show_residual_var = tk.BooleanVar(value=True)
        self.show_legend_var = tk.BooleanVar(value=False)
        self.fit_mode_var = tk.StringVar(value="discrete")
        self.dist_use_sharp_var = tk.BooleanVar(value=False)
        self.dist_refine_global_var = tk.BooleanVar(value=False)
        self.last_bhf_fit = None
        self.last_bhf_sharp_indices: list[int] = []
        self.sextet_enabled: dict[int, tk.BooleanVar] = {1: tk.BooleanVar(value=True), 2: tk.BooleanVar(value=False), 3: tk.BooleanVar(value=False)}
        self.component_kind: dict[int, tk.StringVar] = {1: tk.StringVar(value="Sextete"), 2: tk.StringVar(value="Sextete"), 3: tk.StringVar(value="Sextete")}
        self.current_file_var = tk.StringVar(value="Sin fichero cargado")
        self.last_fit_free_keys: list[str] = []
        self.last_fit_cov: np.ndarray | None = None
        self.last_fit_param_errors: dict[str, float] = {}

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
        bg = "#eaf4ff"
        card = "#f8fbff"
        accent = "#0ea5d9"
        accent_dark = "#075985"
        self.configure(background=bg)
        style.configure("TFrame", background=bg)
        style.configure("TLabelframe", background=card, borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background=bg)
        style.configure("TLabel", background=bg, foreground="#17202a")
        style.configure("Title.TLabel", font=("TkDefaultFont", 17, "bold"), foreground=accent_dark, background=bg)
        style.configure("Header.TLabel", font=("TkDefaultFont", 18, "bold"), foreground="white", background=accent_dark)
        style.configure("HeaderSub.TLabel", font=("TkDefaultFont", 9), foreground="#dff6ff", background=accent_dark)
        style.configure("Subtitle.TLabel", font=("TkDefaultFont", 9), foreground="#4b6478", background=bg)
        style.configure("Section.TLabelframe", padding=10, background=card, relief="solid")
        style.configure("Section.TLabelframe.Label", font=("TkDefaultFont", 10, "bold"), foreground=accent_dark, background=bg)
        style.configure("Accent.TButton", padding=7, font=("TkDefaultFont", 9, "bold"), background=accent, foreground="white")
        style.map("Accent.TButton", background=[("active", "#0284c7")])
        style.configure("Small.TButton", padding=5, background="#d7efff")
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 6), background="#cfefff", foreground="#0f3d5c")
        style.map("TNotebook.Tab", background=[("selected", "#38bdf8")], foreground=[("selected", "white")])

        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Cargar...", command=self.open_file)
        file_menu.add_command(label="Mössbauer web...", command=self.open_web_download_dialog)
        file_menu.add_command(label="Calibraciones web...", command=self.open_calibration_download_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Guardar ajuste...", command=self.save_fit)
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self.destroy)
        menubar.add_cascade(label="Archivo", menu=file_menu)

        fit_menu = tk.Menu(menubar, tearoff=0)
        fit_menu.add_command(label="Buscar centro", command=self.auto_center)
        fit_menu.add_command(label="Ajustar", command=self.fit_current_data)
        fit_menu.add_separator()
        fit_menu.add_command(label="Fijar todos", command=self.fix_all_parameters)
        fit_menu.add_command(label="Liberar todos", command=self.free_all_parameters)
        menubar.add_cascade(label="Ajuste", menu=fit_menu)
        self.config(menu=menubar)

        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True)

        left_outer = ttk.Frame(main, width=455, padding=10)
        left_outer.pack(side=tk.LEFT, fill=tk.Y)
        left_outer.pack_propagate(False)

        controls = ttk.Frame(left_outer)
        controls.pack(fill=tk.BOTH, expand=True)

        plot_frame = ttk.Frame(main, padding=(6, 6, 8, 8))
        plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        header = tk.Frame(controls, bg="#075985", bd=0, highlightthickness=0)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text="Mössbauer Fe-57", style="Header.TLabel").pack(anchor=tk.W, padx=12, pady=(10, 0))
        ttk.Label(header, text="Doblado, simulación y ajuste interactivo", style="HeaderSub.TLabel").pack(anchor=tk.W, padx=12, pady=(0, 10))

        file_box = ttk.LabelFrame(controls, text="Fichero actual", style="Section.TLabelframe")
        file_box.pack(fill=tk.X, pady=(0, 8))
        self.file_label = tk.Label(
            file_box,
            textvariable=self.current_file_var,
            bg="#dff6ff",
            fg="#083344",
            font=("TkDefaultFont", 12, "bold"),
            anchor="w",
            justify="left",
            padx=10,
            pady=8,
            wraplength=405,
        )
        self.file_label.pack(anchor=tk.W, fill=tk.X)

        info_box = ttk.LabelFrame(controls, text="Estado y parámetros", style="Section.TLabelframe")
        info_box.pack(fill=tk.X, pady=8)
        self.info = tk.Text(
            info_box,
            width=38,
            height=12,
            wrap=tk.WORD,
            relief=tk.FLAT,
            background="#f8fbff",
            foreground="#102a43",
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
        self._add_slider(calib_box, "center", "Folding point (centro)", 256.5, 250.0, 263.0, 0.0001, fit_param=False)
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

        sim_box = ttk.LabelFrame(plot_frame, text="Simulación / ajuste", style="Section.TLabelframe")
        sim_box.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
        sim_header = ttk.Frame(sim_box)
        sim_header.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(
            sim_header,
            text="Tipo de ajuste:",
            style="Subtitle.TLabel",
        ).pack(side=tk.LEFT, anchor=tk.W)
        ttk.Radiobutton(sim_header, text="Sextetes", variable=self.fit_mode_var, value="discrete", command=self.update_plot).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Radiobutton(sim_header, text="P(BHF)", variable=self.fit_mode_var, value="bhf_distribution", command=self.update_plot).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Checkbutton(sim_header, text="Diferencia", variable=self.show_residual_var, command=self.update_plot).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Checkbutton(sim_header, text="Leyenda", variable=self.show_legend_var, command=self.update_plot).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(sim_header, text="Ajuste", command=self.fit_current_data, style="Accent.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(sim_header, text="Fijar todos", command=self.fix_all_parameters, style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(sim_header, text="Liberar todos", command=self.free_all_parameters, style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))

        notebook = ttk.Notebook(sim_box)
        notebook.pack(fill=tk.X, expand=False)
        dist_tab = ttk.Frame(notebook, padding=6)
        notebook.add(dist_tab, text="Distribución BHF")
        dist_top = ttk.Frame(dist_tab)
        dist_top.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(
            dist_top,
            text="P(BHF) regularizada. Puede sumar los componentes activos como subespectros nítidos (amplitudes ajustadas).",
            style="Subtitle.TLabel",
        ).pack(side=tk.LEFT, anchor=tk.W)
        dist_cols = ttk.Frame(dist_tab)
        dist_cols.pack(fill=tk.X)
        d1 = ttk.Frame(dist_cols); d2 = ttk.Frame(dist_cols); d3 = ttk.Frame(dist_cols)
        d1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        d2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        d3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        self._add_slider(d1, "dist_delta", "δ global", 0.0, -2.5, 2.5, 0.001, fit_param=False)
        self._add_slider(d1, "dist_quad", "ΔEQ global", 0.0, -2.0, 2.0, 0.001, fit_param=False)
        self._add_slider(d1, "dist_gamma", "Γ HWHM", 0.18, 0.03, 1.0, 0.001, fit_param=False)
        self._add_slider(d2, "dist_bmin", "B mín (T)", 0.0, 0.0, 50.0, 0.1, fit_param=False)
        self._add_slider(d2, "dist_bmax", "B máx (T)", 50.0, 1.0, 60.0, 0.1, fit_param=False)
        self._add_slider(d2, "dist_nbins", "Bins BHF", 50.0, 10.0, 100.0, 1.0, fit_param=False)
        self._add_slider(d3, "dist_log_alpha", "log10 α", -2.0, -8.0, 4.0, 0.1, fit_param=False)
        alpha_buttons = ttk.Frame(d3)
        alpha_buttons.pack(fill=tk.X, pady=(0, 2))
        ttk.Button(alpha_buttons, text="fino", command=lambda: self.set_bhf_alpha_preset(-5.0), style="Small.TButton").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(alpha_buttons, text="medio", command=lambda: self.set_bhf_alpha_preset(-2.0), style="Small.TButton").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(alpha_buttons, text="suave", command=lambda: self.set_bhf_alpha_preset(1.0), style="Small.TButton").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))
        ttk.Checkbutton(d3, text="sumar componentes activos nítidos", variable=self.dist_use_sharp_var, command=self.on_bhf_distribution_option_change).pack(anchor=tk.W, pady=(2, 0))
        ttk.Checkbutton(d3, text="refinar δ y Γ globales", variable=self.dist_refine_global_var, command=self.on_bhf_distribution_option_change).pack(anchor=tk.W, pady=(0, 2))
        ttk.Button(d3, text="L-curve α", command=self.scan_bhf_alpha_gui, style="Small.TButton").pack(anchor=tk.E, fill=tk.X, pady=(2, 0))

        for idx in (1, 2, 3):
            tab = ttk.Frame(notebook, padding=6)
            notebook.add(tab, text=f"Componente {idx}")
            top_row = ttk.Frame(tab)
            top_row.pack(fill=tk.X, pady=(0, 4))
            if idx > 1:
                ttk.Checkbutton(top_row, text=f"Usar componente {idx}", variable=self.sextet_enabled[idx], command=self.on_component_activation_change).pack(side=tk.LEFT)
            else:
                ttk.Label(top_row, text="Componente principal activo", style="Subtitle.TLabel").pack(side=tk.LEFT)
            ttk.Label(top_row, text="Forma:").pack(side=tk.LEFT, padx=(18, 4))
            kind_box = ttk.Combobox(top_row, textvariable=self.component_kind[idx], values=("Sextete", "Doblete", "Singlete"), width=10, state="readonly")
            kind_box.pack(side=tk.LEFT)
            kind_box.bind("<<ComboboxSelected>>", lambda _event, i=idx: self.on_component_kind_change(i))
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

        self.fig = Figure(figsize=(8.5, 5.8), dpi=100, facecolor="#f8fbff")
        gs = self.fig.add_gridspec(2, 1, height_ratios=[4.6, 1.0], hspace=0.08)
        self.ax = self.fig.add_subplot(gs[0])
        self.ax_res = self.fig.add_subplot(gs[1], sharex=self.ax)
        self.ax.set_ylabel("Transmisión normalizada")
        self.ax_res.set_ylabel("Datos-ajuste")
        self.ax_res.set_xlabel("Velocidad (mm/s)")
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
            return f"{value:.5f}"
        if base == "slope":
            return f"{value:.6f}"
        if key == "vmax" or base in {"delta", "quad", "gamma1", "gamma2", "gamma3", "depth", "baseline", "int1", "int2", "int3"}:
            return f"{value:.6g}"
        return f"{value:.5g}"

    def _snap_value(self, key: str, value: float) -> float:
        min_value, max_value, resolution = self.slider_specs[key]
        value = max(min_value, min(max_value, value))
        if key == "center":
            # Normos interpola el folding point: no forzar enteros/semienteros.
            return value
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

        if key.startswith("dist_") or (self.fit_mode_var.get() == "bhf_distribution" and (key in {"baseline", "slope"} or (self.dist_use_sharp_var.get() and re.match(r"s[123]_", key)))):
            self.last_bhf_fit = None
        if key in {"center", "vmax"}:
            self.refold_data()
        self.update_plot()

    def set_bhf_alpha_preset(self, log_alpha: float) -> None:
        self.last_bhf_fit = None
        self.vars["dist_log_alpha"].set(float(log_alpha))
        self.entry_vars["dist_log_alpha"].set(self._format_value("dist_log_alpha", float(log_alpha)))
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

    def on_bhf_distribution_option_change(self) -> None:
        self.last_bhf_fit = None
        self.update_plot()

    def on_component_activation_change(self) -> None:
        if self.fit_mode_var.get() == "bhf_distribution" and self.dist_use_sharp_var.get():
            self.last_bhf_fit = None
        self.update_plot()

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
        found_links: list[tuple[str, str, str]] = []
        displayed_links: list[tuple[str, str, str]] = []

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

        search_var = tk.StringVar()
        ttk.Label(frm, text="Buscar:").grid(row=4, column=0, sticky="w", pady=(0, 4))
        search_entry = ttk.Entry(frm, textvariable=search_var)
        search_entry.grid(row=4, column=1, sticky="ew", pady=(0, 4))
        ttk.Button(frm, text="Limpiar", command=lambda: search_var.set(""), style="Small.TButton").grid(row=4, column=2, sticky="ew", padx=(8, 0), pady=(0, 4))

        listbox = tk.Listbox(frm, height=10, activestyle="dotbox")
        listbox.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=4)
        frm.rowconfigure(5, weight=1)

        debug_box = tk.Text(frm, height=8, wrap=tk.WORD, background="#111827", foreground="#d1fae5", insertbackground="#d1fae5", font=("TkFixedFont", 9))
        debug_box.grid(row=6, column=0, columnspan=3, sticky="nsew", pady=(6, 0))

        def apply_search_filter(*_args) -> None:
            nonlocal displayed_links
            words = [w for w in search_var.get().lower().split() if w]
            displayed_links = []
            listbox.delete(0, tk.END)
            for item in found_links:
                name, full, display = item
                haystack = f"{display} {name} {full}".lower()
                if all(w in haystack for w in words):
                    displayed_links.append(item)
                    listbox.insert(tk.END, f"{display}    {full}")
            if found_links:
                status_var.set(f"Mostrando {len(displayed_links)} de {len(found_links)} resultados.")

        search_var.trace_add("write", apply_search_filter)

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
            return name if name.lower().endswith((".ws5", ".adt")) else name + ".ws5"

        def filename_from_response(response, fallback: str) -> str:
            """Obtiene el nombre real indicado por la web en Content-Disposition."""
            cd = response.headers.get("content-disposition", "")
            m = re.search(r"filename\*=UTF-8''([^;]+)", cd, flags=re.I)
            if m:
                return Path(unquote(m.group(1))).name
            m = re.search(r'filename="?([^";]+)"?', cd, flags=re.I)
            if m:
                return Path(unescape(m.group(1))).name
            return fallback

        def clean_text(html_fragment: str) -> str:
            text = re.sub(r"<[^>]+>", " ", html_fragment)
            text = unescape(text)
            return re.sub(r"\s+", " ", text).strip()

        def safe_filename(text: str, max_len: int = 90) -> str:
            text = unescape(text).strip()
            text = re.sub(r"[^\w.()+\-]+", "_", text, flags=re.UNICODE).strip("_")
            return (text[:max_len] or "mossbauer")

        def row_cells(row_html: str) -> list[str]:
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row_html, flags=re.S | re.I)
            return [clean_text(c).replace("↓ datos", "").replace("Ver", "").replace("✏", "").strip() for c in cells]

        def name_from_row(row_html: str, download_url: str, data_kind: str) -> str:
            m_id = re.search(r"/(?:mossbauer|calibration)/(\d+)/datafile/", download_url)
            item_id = m_id.group(1) if m_id else ""
            cells = row_cells(row_html)
            sample = cells[0] if cells else data_kind
            date = next((c for c in cells if re.search(r"\b20\d{2}-\d{2}-\d{2}\b", c)), "sin_fecha")
            prefix = "cal" if data_kind == "calibration" else "moss"
            return safe_filename(f"{date}_{prefix}_{sample}_{item_id}") + ".ws5"

        def display_from_row(row_html: str, download_url: str, data_kind: str) -> str:
            m_id = re.search(r"/(?:mossbauer|calibration)/(\d+)/datafile/", download_url)
            item_id = m_id.group(1) if m_id else ""
            cells = row_cells(row_html)
            sample = cells[0] if len(cells) > 0 else data_kind
            date = cells[1] if len(cells) > 1 else "sin_fecha"
            entorno = cells[2] if len(cells) > 2 else "-"
            if data_kind == "calibration":
                # Columnas típicas: muestra, fecha, entorno/T, línea, V entrada, V calibrada, ISO.
                calibrado = " / ".join(c for c in [cells[5] if len(cells) > 5 else "", cells[6] if len(cells) > 6 else ""] if c) or "-"
            else:
                calibrado = cells[3] if len(cells) > 3 else "-"
            return f"{sample} - {date} - {entorno} - {calibrado}  [id {item_id}]"

        def list_ws5() -> None:
            """Lee la tabla paginada de Mössbauer o calibraciones y extrae los enlaces de datos."""
            nonlocal found_links, displayed_links
            start_url = url_var.get().strip()
            if not start_url:
                return

            listbox.delete(0, tk.END)
            found: dict[str, tuple[str, str]] = {}
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

            def add_download(url: str, name: str, display: str | None = None) -> None:
                found[url] = (name, display or name)

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
                                display = display_from_row(row, full, data_kind)
                                debug(f"     datos: {display} -> {full}")
                                add_download(full, name, display)
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
            found_links = [(name, url, display) for url, (name, display) in sorted(found.items(), key=lambda item: item[1][0].lower(), reverse=True)]
            apply_search_filter()

            if found_links:
                status_var.set(
                    f"Encontrados {len(found_links)} espectros en {len(visited)} páginas. Selecciona uno y pulsa Descargar."
                )
            else:
                status_var.set(f"No encontré enlaces de datos tras revisar {len(visited)} páginas. Mira el panel debug para ver status, redirects y HTML recibido.")

        def download_selected() -> None:
            save_credentials_if_requested()
            if displayed_links and listbox.curselection():
                name, file_url, _display = displayed_links[listbox.curselection()[0]]
            else:
                file_url = url_var.get().strip()
                name = filename_from_url(file_url)
            if not file_url:
                return
            try:
                r = response_for(file_url)
                r.raise_for_status()
                content = r.content
                name = filename_from_response(r, name)
            except Exception as exc:
                status_var.set(f"Error descargando: {exc}")
                return

            save_path = filedialog.asksaveasfilename(
                title="Guardar dato descargado",
                initialfile=name,
                defaultextension=".ws5",
                filetypes=[("Mössbauer WS5/ADT", "*.ws5 *.adt"), ("Wissoft WS5", "*.ws5"), ("ADT antiguo", "*.adt"), ("Todos", "*")],
            )
            if not save_path:
                return
            path = Path(save_path)
            path.write_bytes(content)
            status_var.set(f"Descargado: {path}")
            self.load_ws5(path)
            dialog.destroy()

        buttons = ttk.Frame(frm)
        buttons.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        ttk.Button(buttons, text="Listar", command=list_ws5).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(buttons, text="Descargar", command=download_selected, style="Accent.TButton").grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def open_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Selecciona fichero .ws5 o .adt",
            filetypes=[("Mössbauer WS5/ADT", "*.ws5 *.adt"), ("Wissoft WS5", "*.ws5"), ("ADT antiguo", "*.adt"), ("Todos", "*")],
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
        self.current_file_var.set(path.name)
        self.counts = counts
        center = read_normos_folding_point(path)
        if center is None:
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
        self.last_bhf_fit = None
        center = self.vars["center"].get()
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
                p + "delta": -0.11 if idx == 1 else 0.0,
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

    def component_param_names(self, idx: int) -> list[str]:
        kind = self.component_kind[idx].get()
        if kind == "Singlete":
            return ["delta", "gamma1", "depth", "int1"]
        if kind == "Doblete":
            return ["delta", "quad", "gamma1", "gamma2", "depth", "int1", "int2"]
        return SEXTET_PARAM_NAMES.copy()

    def on_component_kind_change(self, idx: int) -> None:
        if self.fit_mode_var.get() == "bhf_distribution" and self.dist_use_sharp_var.get() and idx in self.active_sharp_component_indices_for_bhf():
            self.last_bhf_fit = None
        kind = self.component_kind[idx].get()
        p = f"s{idx}_"
        relevant = set(self.component_param_names(idx))
        # Marcar como fijos los parámetros que no se usan en la forma elegida.
        for name in SEXTET_PARAM_NAMES:
            key = p + name
            if key in self.fixed_vars and name not in relevant:
                self.fixed_vars[key].set(True)
        self.update_plot()

    def active_param_keys(self) -> list[str]:
        keys = GLOBAL_PARAM_NAMES.copy()
        for idx in (1, 2, 3):
            if self.sextet_enabled[idx].get():
                keys.extend(f"s{idx}_{name}" for name in self.component_param_names(idx))
        return keys

    def active_bhf_keys(self) -> list[str]:
        return [f"s{idx}_bhf" for idx in (1, 2, 3) if self.sextet_enabled[idx].get() and self.component_kind[idx].get() == "Sextete"]

    def build_components_from_vars(self) -> list[tuple[str, np.ndarray]]:
        components: list[tuple[str, np.ndarray]] = []
        for idx in (1, 2, 3):
            if not self.sextet_enabled[idx].get():
                continue
            p = f"s{idx}_"
            params = np.array([self.vars[p + name].get() for name in SEXTET_PARAM_NAMES], dtype=float)
            components.append((self.component_kind[idx].get(), params))
        return components

    def component_area_from_params(self, kind: str, p: np.ndarray) -> float:
        """Área integrada de absorción del componente (unidades relativas)."""
        delta, quad, bhf, gamma1, gamma2, gamma3, depth, int1, int2, int3 = p
        if kind == "Singlete":
            return float(depth * np.pi * gamma1 * int1)
        if kind == "Doblete":
            g1 = gamma1
            g2 = gamma1 * gamma2
            return float(depth * np.pi * (int1 * g1 + int1 * int2 * g2))
        i1 = int1
        i2 = int1 * (2.0 / 3.0) * int2
        i3 = int1 * (1.0 / 3.0) * int3
        weights = np.array([i1, i2, i3, i3, i2, i1], dtype=float)
        gammas = gamma1 * np.array([1.0, gamma2, gamma3, gamma3, gamma2, 1.0], dtype=float)
        return float(depth * np.pi * np.sum(weights * gammas))

    def component_area_percentages(self, values: dict[str, float] | None = None) -> tuple[list[int], np.ndarray, np.ndarray]:
        """Devuelve índices, áreas y porcentajes de los componentes activos."""
        active: list[int] = []
        areas: list[float] = []
        for idx in (1, 2, 3):
            if not self.sextet_enabled[idx].get():
                continue
            pfx = f"s{idx}_"
            p = np.array([values.get(pfx + name, self.vars[pfx + name].get()) if values else self.vars[pfx + name].get() for name in SEXTET_PARAM_NAMES], dtype=float)
            area = max(0.0, self.component_area_from_params(self.component_kind[idx].get(), p))
            active.append(idx)
            areas.append(area)
        area_arr = np.array(areas, dtype=float)
        total = float(np.sum(area_arr))
        pct = 100.0 * area_arr / total if total > 0 else np.zeros_like(area_arr)
        return active, area_arr, pct

    def component_percentage_errors(self) -> dict[int, float]:
        """Errores 1σ de porcentajes por propagación lineal de la covarianza."""
        if self.last_fit_cov is None or not self.last_fit_free_keys:
            return {}
        base_values = {key: self.vars[key].get() for key in self.active_param_keys()}
        active, _areas, pct0 = self.component_area_percentages(base_values)
        if not active:
            return {}

        jac = np.zeros((len(active), len(self.last_fit_free_keys)), dtype=float)
        for j, key in enumerate(self.last_fit_free_keys):
            if key not in base_values:
                continue
            x = base_values[key]
            step = max(1e-6, abs(x) * 1e-5)
            vals_p = base_values.copy(); vals_m = base_values.copy()
            vals_p[key] = x + step
            vals_m[key] = x - step
            _a, _ar, pct_p = self.component_area_percentages(vals_p)
            _a, _ar, pct_m = self.component_area_percentages(vals_m)
            jac[:, j] = (pct_p - pct_m) / (2.0 * step)
        cov_pct = jac @ self.last_fit_cov @ jac.T
        errs = np.sqrt(np.maximum(np.diag(cov_pct), 0.0))
        return {idx: float(err) for idx, err in zip(active, errs)}

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
        if key.startswith("dist_") or (self.fit_mode_var.get() == "bhf_distribution" and (key in {"baseline", "slope"} or (self.dist_use_sharp_var.get() and re.match(r"s[123]_", key)))):
            self.last_bhf_fit = None
        if key in {"center", "vmax"}:
            self.refold_data()
        self.update_plot()

    def current_model(self) -> np.ndarray | None:
        if self.fit_mode_var.get() == "bhf_distribution" and self.last_bhf_fit is not None:
            return self.last_bhf_fit.fitted_curve
        if self.velocity is None:
            return None
        return total_model(
            self.velocity,
            self.vars["baseline"].get(),
            self.vars["slope"].get(),
            self.build_components_from_vars(),
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
        components: list[tuple[str, np.ndarray]] = []
        for idx in (1, 2, 3):
            if self.sextet_enabled[idx].get():
                p = f"s{idx}_"
                params = np.array([values.get(p + name, self.vars[p + name].get()) for name in SEXTET_PARAM_NAMES], dtype=float)
                components.append((self.component_kind[idx].get(), params))
        return total_model(v, values["baseline"], values["slope"], components)

    def fit_current_data(self) -> None:
        if self.fit_mode_var.get() == "bhf_distribution":
            self.fit_bhf_distribution_current()
            return
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

        # Covarianza aproximada de los parámetros libres para errores 1σ.
        self.last_fit_free_keys = free_keys.copy()
        self.last_fit_cov = None
        self.last_fit_param_errors = {}
        try:
            n_obs = y.size
            n_par = len(result.x)
            if n_obs > n_par and result.jac.size:
                _, svals, vt = np.linalg.svd(result.jac, full_matrices=False)
                threshold = np.finfo(float).eps * max(result.jac.shape) * svals[0]
                svals = svals[svals > threshold]
                vt = vt[:svals.size]
                cov_all = (vt.T / (svals ** 2)) @ vt
                cov_all *= 2.0 * result.cost / max(1, n_obs - n_par)
                self.last_fit_cov = cov_all[:len(free_keys), :len(free_keys)]
                for key, err in zip(free_keys, np.sqrt(np.maximum(np.diag(self.last_fit_cov), 0.0))):
                    self.last_fit_param_errors[key] = float(err)
        except Exception:
            self.last_fit_cov = None
            self.last_fit_param_errors = {}

        values_final, vmax_final = unpack(result.x)
        self.set_params(values_final)
        if fit_velocity:
            self.vars["vmax"].set(vmax_final)
            self.entry_vars["vmax"].set(self._format_value("vmax", vmax_final))
            self.refold_data()
        self.update_plot()

    def dist_alpha(self) -> float:
        return float(10.0 ** self.vars["dist_log_alpha"].get())

    def suggest_alpha_from_lcurve_rows(self, rows: np.ndarray) -> float | None:
        if rows.shape[0] < 5:
            return None
        alpha, misfit, rough = rows[:, 0], rows[:, 2], rows[:, 3]
        mask = (alpha > 0) & (misfit > 0) & (rough > 0) & np.all(np.isfinite(rows[:, :4]), axis=1)
        if int(np.sum(mask)) < 5:
            return None
        a = alpha[mask]
        x = np.log(rough[mask])
        y = np.log(misfit[mask])
        t = np.log(a)
        dx = np.gradient(x, t); dy = np.gradient(y, t)
        ddx = np.gradient(dx, t); ddy = np.gradient(dy, t)
        curv = np.abs(dx * ddy - dy * ddx) / np.maximum((dx * dx + dy * dy) ** 1.5, 1e-30)
        if not np.any(np.isfinite(curv)):
            return None
        return float(a[int(np.nanargmax(curv))])

    def scan_bhf_alpha_gui(self) -> None:
        if self.velocity is None or self.y_data is None:
            return
        bmin = self.vars["dist_bmin"].get()
        bmax = self.vars["dist_bmax"].get()
        nbins = int(round(self.vars["dist_nbins"].get()))
        if bmax <= bmin or nbins < 3:
            messagebox.showwarning("L-curve α", "Revisa B mín/B máx y número de bins.")
            return
        sharp_components = None
        if self.dist_use_sharp_var.get():
            sharp_components, _indices = self.build_bhf_sharp_components_from_active_components()
        try:
            alphas = np.logspace(-8, 4, 31)
            scans = scan_bhf_alpha_engine(
                self.velocity,
                self.y_data,
                alphas,
                delta=self.vars["dist_delta"].get(),
                quad=self.vars["dist_quad"].get(),
                gamma=self.vars["dist_gamma"].get(),
                bmin=bmin,
                bmax=bmax,
                nbins=nbins,
                fit_baseline=not self.fixed_vars["baseline"].get(),
                fit_slope=not self.fixed_vars["slope"].get(),
                baseline=self.vars["baseline"].get(),
                slope=self.vars["slope"].get(),
                sharp_components=sharp_components,
            )
        except Exception as exc:
            messagebox.showerror("L-curve α", str(exc))
            return
        L = second_difference_matrix(nbins)
        rows = np.array([(r.alpha, r.rms, float(np.linalg.norm(r.residuals)), float(np.linalg.norm(L @ r.weights))) for r in scans], dtype=float)
        suggested = self.suggest_alpha_from_lcurve_rows(rows)

        dialog = tk.Toplevel(self)
        dialog.title("L-curve α para P(BHF)")
        dialog.geometry("850x420")
        dialog.transient(self)
        fig = Figure(figsize=(8.2, 3.6), dpi=100, facecolor="#f8fbff")
        ax0 = fig.add_subplot(121)
        ax1 = fig.add_subplot(122)
        sc = ax0.scatter(rows[:, 3], rows[:, 2], c=np.log10(rows[:, 0]), cmap="viridis", s=34)
        ax0.plot(rows[:, 3], rows[:, 2], "-", color="#94a3b8", lw=0.8)
        ax0.set_xscale("log"); ax0.set_yscale("log")
        ax0.set_xlabel("||L·P||"); ax0.set_ylabel("||residuo||"); ax0.set_title("L-curve")
        ax0.grid(True, alpha=0.3)
        fig.colorbar(sc, ax=ax0, label="log10 α")
        ax1.loglog(rows[:, 0], rows[:, 1], "-o", ms=3.2)
        if suggested is not None:
            ax1.axvline(suggested, color="#dc2626", ls="--", lw=1.2, label=f"sugerido {suggested:.3g}")
            ax1.legend()
        ax1.set_xlabel("α"); ax1.set_ylabel("RMS"); ax1.set_title("RMS vs α")
        ax1.grid(True, which="both", alpha=0.3)
        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=dialog)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        canvas.draw_idle()
        buttons = ttk.Frame(dialog, padding=8)
        buttons.pack(fill=tk.X)
        if suggested is not None:
            ttk.Button(buttons, text=f"Usar α sugerido ({suggested:.3g})", command=lambda a=suggested, d=dialog: (self.set_bhf_alpha_preset(np.log10(a)), d.destroy()), style="Accent.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(buttons, text="Cerrar", command=dialog.destroy, style="Small.TButton").pack(side=tk.RIGHT)

    def active_sharp_component_indices_for_bhf(self) -> list[int]:
        if not self.dist_use_sharp_var.get():
            return []
        return [idx for idx in (1, 2, 3) if idx == 1 or self.sextet_enabled[idx].get()]

    def build_bhf_sharp_components_from_active_components(self) -> tuple[list[dict[str, float]], list[int]]:
        components: list[dict[str, float]] = []
        indices = self.active_sharp_component_indices_for_bhf()
        for idx in indices:
            p = f"s{idx}_"
            components.append({
                "kind": self.component_kind[idx].get(),
                "bhf": self.vars[p + "bhf"].get(),
                "delta": self.vars[p + "delta"].get(),
                "quad": self.vars[p + "quad"].get(),
                "gamma": self.vars[p + "gamma1"].get(),
                "gamma2_rel": self.vars[p + "gamma2"].get(),
                "gamma3_rel": self.vars[p + "gamma3"].get(),
                "int1": self.vars[p + "int1"].get(),
                "int2_rel": self.vars[p + "int2"].get(),
                "int3_rel": self.vars[p + "int3"].get(),
            })
        return components, indices

    def fit_bhf_distribution_current(self) -> None:
        if self.velocity is None or self.y_data is None:
            return
        bmin = self.vars["dist_bmin"].get()
        bmax = self.vars["dist_bmax"].get()
        nbins = int(round(self.vars["dist_nbins"].get()))
        if bmax <= bmin:
            messagebox.showwarning("P(BHF)", "B máx debe ser mayor que B mín.")
            return
        if nbins < 3:
            messagebox.showwarning("P(BHF)", "El número de bins debe ser al menos 3.")
            return
        sharp_components = None
        sharp_indices: list[int] = []
        if self.dist_use_sharp_var.get():
            sharp_components, sharp_indices = self.build_bhf_sharp_components_from_active_components()

        fit_baseline = not self.fixed_vars["baseline"].get()
        fit_slope = not self.fixed_vars["slope"].get()

        def run_fit(delta_value: float, gamma_value: float):
            return fit_bhf_distribution_engine(
                self.velocity,
                self.y_data,
                delta=delta_value,
                quad=self.vars["dist_quad"].get(),
                gamma=gamma_value,
                bmin=bmin,
                bmax=bmax,
                nbins=nbins,
                alpha=self.dist_alpha(),
                fit_baseline=fit_baseline,
                fit_slope=fit_slope,
                baseline=self.vars["baseline"].get(),
                slope=self.vars["slope"].get(),
                sharp_components=sharp_components,
            )

        try:
            if self.dist_refine_global_var.get():
                x0 = np.array([self.vars["dist_delta"].get(), np.log(max(self.vars["dist_gamma"].get(), 0.03))], dtype=float)
                lo = np.array([-2.5, np.log(0.03)], dtype=float)
                hi = np.array([2.5, np.log(1.0)], dtype=float)

                def residual_outer(x: np.ndarray) -> np.ndarray:
                    r = run_fit(float(x[0]), float(np.exp(x[1])))
                    return r.residuals

                outer = least_squares(residual_outer, np.clip(x0, lo, hi), bounds=(lo, hi), max_nfev=35)
                delta_final = float(outer.x[0])
                gamma_final = float(np.exp(outer.x[1]))
                result = run_fit(delta_final, gamma_final)
                self.set_params({"dist_delta": delta_final, "dist_gamma": gamma_final})
            else:
                result = run_fit(self.vars["dist_delta"].get(), self.vars["dist_gamma"].get())
        except Exception as exc:
            messagebox.showerror("Error en P(BHF)", str(exc))
            return
        self.last_bhf_fit = result
        self.last_bhf_sharp_indices = sharp_indices
        params_to_update = {"baseline": result.baseline, "slope": result.slope}
        if self.dist_use_sharp_var.get() and result.sharp_weights is not None:
            for idx, weight in zip(sharp_indices, result.sharp_weights):
                params_to_update[f"s{idx}_depth"] = float(weight)
        self.set_params(params_to_update)
        self.update_plot()

    def update_plot_bhf_distribution(self) -> None:
        self.fig.clear()
        show_residual = self.show_residual_var.get()
        if self.last_bhf_fit is not None and show_residual:
            gs = self.fig.add_gridspec(3, 1, height_ratios=[3.8, 0.8, 1.7], hspace=0.08)
            ax = self.fig.add_subplot(gs[0])
            ax_res = self.fig.add_subplot(gs[1], sharex=ax)
            ax_dist = self.fig.add_subplot(gs[2])
        elif self.last_bhf_fit is not None:
            gs = self.fig.add_gridspec(2, 1, height_ratios=[3.8, 1.7], hspace=0.18)
            ax = self.fig.add_subplot(gs[0])
            ax_res = None
            ax_dist = self.fig.add_subplot(gs[1])
        else:
            gs = self.fig.add_gridspec(1, 1)
            ax = self.fig.add_subplot(gs[0])
            ax_res = None
            ax_dist = None

        self.fig.set_facecolor("#f8fbff")
        ax.set_facecolor("#fbfdff")
        ax.set_title("Espectro Mössbauer: modo distribución P(BHF)", color="#083344", pad=10, fontweight="bold")
        ax.set_ylabel("Transmisión normalizada")
        ax.grid(True, color="#c8e4f7", alpha=0.85, linewidth=0.8)
        ax.tick_params(colors="#243b53")
        for spine in ax.spines.values():
            spine.set_color("#8ecae6")

        if self.velocity is not None and self.y_data is not None:
            ax.plot(self.velocity, self.y_data, ".", color="#0f172a", ms=4, alpha=0.88, label="Datos doblados")
            baseline_line = self.vars["baseline"].get() + self.vars["slope"].get() * self.velocity
            ax.plot(self.velocity, baseline_line, ":", color="#64748b", lw=1.25, label="Fondo")
            if self.last_bhf_fit is not None:
                fit = self.last_bhf_fit.fitted_curve
                sharp_abs_sum = np.zeros_like(self.velocity, dtype=float)
                if self.last_bhf_fit.sharp_weights is not None and self.last_bhf_fit.sharp_weights.size:
                    colors = {1: "#16a34a", 2: "#f97316", 3: "#8b5cf6"}
                    for idx, weight in zip(self.last_bhf_sharp_indices, self.last_bhf_fit.sharp_weights):
                        p = f"s{idx}_"
                        params = np.array([self.vars[p + name].get() for name in SEXTET_PARAM_NAMES], dtype=float)
                        params[6] = float(weight)
                        kind = self.component_kind[idx].get()
                        sharp_abs = component_absorption(self.velocity, kind, params)
                        sharp_abs_sum += sharp_abs
                        sharp_curve = baseline_line - sharp_abs
                        ax.plot(self.velocity, sharp_curve, "--", color=colors.get(idx, "#16a34a"), lw=1.45, alpha=0.9, label=f"Comp. {idx} nítido ({kind})")
                if np.any(sharp_abs_sum > 0):
                    distribution_curve = fit + sharp_abs_sum
                    ax.plot(self.velocity, distribution_curve, "--", color="#2563eb", lw=1.7, alpha=0.95, label="Componente distribución P(BHF)")
                ax.plot(self.velocity, fit, "-", color="#dc2626", lw=2.4, label="Ajuste total")
                residual = self.y_data - fit
                if ax_res is not None:
                    ax_res.set_facecolor("#fff7ed")
                    ax_res.axhline(0, color="#9a3412", lw=0.9, alpha=0.9)
                    ax_res.fill_between(self.velocity, residual, 0, color="#fb923c", alpha=0.22)
                    ax_res.plot(self.velocity, residual, "-", color="#ea580c", lw=1.15)
                    ax_res.set_ylabel("Datos-ajuste")
                    ax_res.grid(True, color="#fed7aa", alpha=0.8, linewidth=0.75)
                    lim = max(float(np.nanmax(np.abs(residual))) * 1.18, 1e-6)
                    ax_res.set_ylim(-lim, lim)
                    ax.tick_params(labelbottom=False)
                if ax_dist is not None:
                    ax_dist.plot(self.last_bhf_fit.bhf_centers, self.last_bhf_fit.probability, "-o", ms=3.0, color="#2563eb")
                    ax_dist.fill_between(self.last_bhf_fit.bhf_centers, self.last_bhf_fit.probability, 0, color="#60a5fa", alpha=0.25)
                    if self.last_bhf_fit.sharp_bhf_centers is not None and self.last_bhf_fit.sharp_weights is not None:
                        ymax = max(float(np.nanmax(self.last_bhf_fit.probability)), 1e-12)
                        for b, w in zip(self.last_bhf_fit.sharp_bhf_centers, self.last_bhf_fit.sharp_weights):
                            if np.isfinite(float(b)):
                                ax_dist.axvline(float(b), color="#dc2626", lw=1.4, ls="--", alpha=0.85)
                                ax_dist.text(float(b), ymax * 0.92, f"nítido {float(w):.3g}", rotation=90, va="top", ha="right", color="#991b1b", fontsize=8)
                    ax_dist.set_xlabel("BHF (T)")
                    ax_dist.set_ylabel("P(BHF)")
                    ax_dist.grid(True, color="#bfdbfe", alpha=0.8, linewidth=0.75)
                rms = self.last_bhf_fit.rms
            else:
                ax.text(0.5, 0.12, "Pulsa 'Ajuste' para calcular P(BHF)", transform=ax.transAxes, ha="center", color="#075985", fontsize=12, fontweight="bold")
                ax.set_xlabel("Velocidad (mm/s)")
                rms = float("nan")
            if self.show_legend_var.get():
                leg = ax.legend(loc="best", frameon=True, facecolor="#ffffff", edgecolor="#bae6fd", framealpha=0.85)
                leg.set_draggable(True)
                for text in leg.get_texts():
                    text.set_color("#102a43")
            self.update_info_bhf_distribution(rms)
        else:
            ax.text(0.5, 0.5, "Carga un fichero .ws5", transform=ax.transAxes, ha="center", va="center", color="#075985", fontsize=14, fontweight="bold")
        self.fig.tight_layout()
        self.canvas.draw_idle()

    def bhf_component_area_percentages(self) -> tuple[float, list[tuple[int, str, float]], float, list[tuple[int, str, float]]]:
        """Áreas y porcentajes espectrales en modo P(BHF).

        Devuelve area_distribucion, areas_nitidas, pct_distribucion, pct_nitidos.
        Las áreas son áreas integradas de absorción, comparables con las usadas
        para porcentajes de componentes discretos.
        """
        if self.last_bhf_fit is None:
            return 0.0, [], 0.0, []
        gamma = self.vars["dist_gamma"].get()
        # La distribución usa sextetes unitarios con intensidades 1 : 2/3 : 1/3
        # y anchuras relativas 1,1,1. El área de un sextete unitario es 4πΓ.
        dist_area = float(np.sum(np.maximum(self.last_bhf_fit.weights, 0.0)) * 4.0 * np.pi * gamma)

        sharp_areas: list[tuple[int, str, float]] = []
        if self.last_bhf_fit.sharp_weights is not None:
            for idx, weight in zip(self.last_bhf_sharp_indices, self.last_bhf_fit.sharp_weights):
                pfx = f"s{idx}_"
                params = np.array([self.vars[pfx + name].get() for name in SEXTET_PARAM_NAMES], dtype=float)
                params[6] = float(weight)
                kind = self.component_kind[idx].get()
                area = max(0.0, self.component_area_from_params(kind, params))
                sharp_areas.append((idx, kind, area))

        total = dist_area + sum(area for _idx, _kind, area in sharp_areas)
        if total <= 0:
            return dist_area, sharp_areas, 0.0, [(idx, kind, 0.0) for idx, kind, _area in sharp_areas]
        return dist_area, sharp_areas, 100.0 * dist_area / total, [(idx, kind, 100.0 * area / total) for idx, kind, area in sharp_areas]

    def update_info_bhf_distribution(self, rms: float) -> None:
        if self.counts is None or self.folded_raw is None:
            return
        text = [
            f"Fichero: {self.file_path.name if self.file_path else '-'}",
            "Modo: distribución P(BHF)",
            f"Folding point centro: {self.vars['center'].get():.5f}",
            f"Vmax = {self.vars['vmax'].get():.6g} mm/s",
            f"Base = {self.vars['baseline'].get():.6g}",
            f"Pendiente = {self.vars['slope'].get():.6g}",
            f"δ = {self.vars['dist_delta'].get():.6g}, ΔEQ = {self.vars['dist_quad'].get():.6g}",
            f"Γ = {self.vars['dist_gamma'].get():.6g}",
            f"BHF rango = {self.vars['dist_bmin'].get():.4g}–{self.vars['dist_bmax'].get():.4g} T",
            f"Bins = {int(round(self.vars['dist_nbins'].get()))}",
            f"α = {self.dist_alpha():.3g}  (log10 α = {self.vars['dist_log_alpha'].get():.3g})",
            f"Subespectros nítidos: {', '.join(map(str, self.last_bhf_sharp_indices or self.active_sharp_component_indices_for_bhf())) if self.dist_use_sharp_var.get() else 'no'}",
            f"RMS ajuste: {rms:.6g}",
        ]
        if self.last_bhf_fit is not None:
            peak = float(self.last_bhf_fit.bhf_centers[int(np.argmax(self.last_bhf_fit.weights))])
            area = float(np.trapz(self.last_bhf_fit.weights, self.last_bhf_fit.bhf_centers))
            dist_area, sharp_areas, dist_pct, sharp_pct = self.bhf_component_area_percentages()
            text.extend([
                f"Pico P(BHF): {peak:.4g} T",
                f"Área P amplitud: {area:.6g}",
                "",
                "Porcentaje de área espectral:",
                f"  Distribución P(BHF): {dist_pct:.3f}%  área={dist_area:.6g}",
            ])
            for idx, kind, pct in sharp_pct:
                sharp_area = next((a for i, _k, a in sharp_areas if i == idx), 0.0)
                text.append(f"  Comp. {idx} nítido ({kind}): {pct:.3f}%  área={sharp_area:.6g}")
            if self.last_bhf_fit.sharp_bhf_centers is not None and self.last_bhf_fit.sharp_weights is not None:
                for idx, b, w in zip(self.last_bhf_sharp_indices, self.last_bhf_fit.sharp_bhf_centers, self.last_bhf_fit.sharp_weights):
                    kind = self.component_kind[idx].get()
                    if np.isfinite(float(b)):
                        text.append(f"Comp. {idx} nítido ({kind}) BHF={float(b):.4g} T, amp/prof={float(w):.6g}")
                    else:
                        text.append(f"Comp. {idx} nítido ({kind}), amp/prof={float(w):.6g}")
                    text.append(
                        f"  δ{idx}={self.vars[f's{idx}_delta'].get():.5g}, ΔEQ{idx}={self.vars[f's{idx}_quad'].get():.5g}, Γ{idx}={self.vars[f's{idx}_gamma1'].get():.5g}"
                    )
        self.info.delete("1.0", tk.END)
        self.info.insert(tk.END, "\n".join(text))

    def update_plot(self) -> None:
        if self.fit_mode_var.get() == "bhf_distribution":
            self.update_plot_bhf_distribution()
            return
        self.fig.clear()
        show_residual = self.show_residual_var.get()
        if show_residual:
            gs = self.fig.add_gridspec(2, 1, height_ratios=[4.8, 1.05], hspace=0.08)
            self.ax = self.fig.add_subplot(gs[0])
            self.ax_res = self.fig.add_subplot(gs[1], sharex=self.ax)
        else:
            self.ax = self.fig.add_subplot(111)
            self.ax_res = None

        self.fig.set_facecolor("#f8fbff")
        self.ax.set_facecolor("#fbfdff")
        self.ax.set_title("Espectro Mössbauer: datos doblados y modelo", color="#083344", pad=10, fontweight="bold")
        self.ax.set_ylabel("Transmisión normalizada")
        self.ax.grid(True, color="#c8e4f7", alpha=0.85, linewidth=0.8)
        self.ax.tick_params(colors="#243b53")
        for spine in self.ax.spines.values():
            spine.set_color("#8ecae6")

        if self.ax_res is not None:
            self.ax_res.set_facecolor("#fff7ed")
            self.ax_res.set_ylabel("Datos-ajuste")
            self.ax_res.set_xlabel("Velocidad (mm/s)")
            self.ax_res.grid(True, color="#fed7aa", alpha=0.8, linewidth=0.75)
            self.ax_res.tick_params(colors="#7c2d12")
            for spine in self.ax_res.spines.values():
                spine.set_color("#fdba74")
        else:
            self.ax.set_xlabel("Velocidad (mm/s)")

        if self.velocity is not None and self.y_data is not None:
            model = self.current_model()
            self.ax.plot(self.velocity, self.y_data, ".", color="#0f172a", ms=4, alpha=0.88, label="Datos doblados")
            if model is not None:
                baseline_line = self.vars["baseline"].get() + self.vars["slope"].get() * self.velocity
                self.ax.plot(self.velocity, baseline_line, ":", color="#64748b", lw=1.35, label="Fondo")

                component_colors = {1: "#16a34a", 2: "#f97316", 3: "#8b5cf6"}
                for idx in (1, 2, 3):
                    if not self.sextet_enabled[idx].get():
                        continue
                    p = f"s{idx}_"
                    params = np.array([self.vars[p + name].get() for name in SEXTET_PARAM_NAMES], dtype=float)
                    kind = self.component_kind[idx].get()
                    component = baseline_line - component_absorption(self.velocity, kind, params)
                    self.ax.plot(
                        self.velocity,
                        component,
                        "--",
                        color=component_colors[idx],
                        lw=1.65,
                        alpha=0.95,
                        label=f"{kind} {idx}",
                    )

                self.ax.plot(self.velocity, model, "-", color="#dc2626", lw=2.6, label="Modelo global")
                residual = self.y_data - model
                rms = float(np.sqrt(np.mean(residual ** 2)))
                if self.ax_res is not None:
                    self.ax_res.axhline(0, color="#9a3412", lw=0.9, alpha=0.9)
                    self.ax_res.fill_between(self.velocity, residual, 0, color="#fb923c", alpha=0.22)
                    self.ax_res.plot(self.velocity, residual, "-", color="#ea580c", lw=1.25)
                    lim = max(float(np.nanmax(np.abs(residual))) * 1.18, 1e-6)
                    self.ax_res.set_ylim(-lim, lim)
                    self.ax.tick_params(labelbottom=False)
            else:
                rms = float("nan")
            if self.show_legend_var.get():
                leg = self.ax.legend(loc="best", frameon=True, facecolor="#ffffff", edgecolor="#bae6fd", framealpha=0.85)
                leg.set_draggable(True)
                for text in leg.get_texts():
                    text.set_color("#102a43")
            self.update_info(rms)
        else:
            self.ax.text(0.5, 0.5, "Carga un fichero .ws5", transform=self.ax.transAxes,
                         ha="center", va="center", color="#075985", fontsize=14, fontweight="bold")
        self.fig.tight_layout()
        self.canvas.draw_idle()

    def update_info(self, rms: float) -> None:
        if self.counts is None or self.folded_raw is None:
            return
        center = self.vars["center"].get()
        active = [idx for idx in (1, 2, 3) if self.sextet_enabled[idx].get()]
        fixed = [k for k in self.active_param_keys() if self.fixed_vars[k].get()]
        pct_active, areas, percentages = self.component_area_percentages()
        pct_errors = self.component_percentage_errors()
        text = [
            f"Fichero: {self.file_path.name if self.file_path else '-'}",
            f"Canales leídos: {self.counts.size}",
            f"Folding point centro: {center:.5f}",
            f"Folding point Normos aprox.: {2.0 * center:.5f}",
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
        if len(pct_active) > 1:
            text.append("Porcentaje de área por componente:")
            for idx, area, pct in zip(pct_active, areas, percentages):
                err = pct_errors.get(idx)
                err_txt = f" ± {err:.3g}%" if err is not None else ""
                text.append(f"  Comp. {idx} ({self.component_kind[idx].get()}): {pct:.3f}%{err_txt}  área={area:.6g}")
            text.append("")
        for idx in active:
            p = f"s{idx}_"
            i1 = self.vars[p + 'int1'].get()
            i2_real = i1 * (2/3) * self.vars[p + 'int2'].get()
            i3_real = i1 * (1/3) * self.vars[p + 'int3'].get()
            g1 = self.vars[p + 'gamma1'].get()
            g2 = g1 * self.vars[p + 'gamma2'].get()
            g3 = g1 * self.vars[p + 'gamma3'].get()
            text.extend([
                f"{self.component_kind[idx].get()} {idx}: BHF={self.vars[p+'bhf'].get():.6g} T, δ={self.vars[p+'delta'].get():.6g}, ΔEQ={self.vars[p+'quad'].get():.6g}",
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
        suffix = "_bhf_fit.dat" if self.fit_mode_var.get() == "bhf_distribution" else "_fe33_fit.dat"
        default_name = (self.file_path.stem if self.file_path else "espectro") + suffix
        filename = filedialog.asksaveasfilename(
            title="Guardar ajuste",
            initialfile=default_name,
            defaultextension=".dat",
            filetypes=[("Datos", "*.dat"), ("Todos", "*")],
        )
        if not filename:
            return
        with Path(filename).open("w", encoding="utf-8") as f:
            f.write("# [fit_config]\n")
            f.write(f"# mode = {self.fit_mode_var.get()}\n")
            f.write(f"# source = {self.file_path.name if self.file_path else '-'}\n")
            f.write(f"# center_internal = {self.vars['center'].get():.10g}\n")
            f.write(f"# vmax = {self.vars['vmax'].get():.10g}\n")
            f.write(f"# norm_factor = {self.norm_factor:.10g}\n")
            if self.fit_mode_var.get() == "bhf_distribution" and self.last_bhf_fit is not None:
                f.write(f"# dist_delta = {self.vars['dist_delta'].get():.10g}\n")
                f.write(f"# dist_quad = {self.vars['dist_quad'].get():.10g}\n")
                f.write(f"# dist_gamma = {self.vars['dist_gamma'].get():.10g}\n")
                f.write(f"# dist_bmin = {self.vars['dist_bmin'].get():.10g}\n")
                f.write(f"# dist_bmax = {self.vars['dist_bmax'].get():.10g}\n")
                f.write(f"# dist_nbins = {int(round(self.vars['dist_nbins'].get()))}\n")
                f.write(f"# dist_alpha = {self.dist_alpha():.10g}\n")
                f.write(f"# dist_log10_alpha = {self.vars['dist_log_alpha'].get():.10g}\n")
                f.write(f"# dist_refine_delta_gamma = {self.dist_refine_global_var.get()}\n")
                f.write(f"# sharp_component_indices = {','.join(map(str, self.last_bhf_sharp_indices)) if self.last_bhf_sharp_indices else '-'}\n")
                dist_area, sharp_areas, dist_pct, sharp_pct = self.bhf_component_area_percentages()
                f.write(f"# area_pct_distribution = {dist_pct:.10g}\n")
                f.write(f"# area_distribution = {dist_area:.10g}\n")
                for idx, kind, pct in sharp_pct:
                    sharp_area = next((a for i, _k, a in sharp_areas if i == idx), 0.0)
                    f.write(f"# area_pct_sharp_{idx}_{kind} = {pct:.10g}\n")
                    f.write(f"# area_sharp_{idx}_{kind} = {sharp_area:.10g}\n")
                for idx in self.last_bhf_sharp_indices:
                    pfx = f"s{idx}_"
                    f.write(
                        f"# sharp_{idx} = kind:{self.component_kind[idx].get()} "
                        f"delta:{self.vars[pfx+'delta'].get():.10g} quad:{self.vars[pfx+'quad'].get():.10g} "
                        f"bhf:{self.vars[pfx+'bhf'].get():.10g} gamma1:{self.vars[pfx+'gamma1'].get():.10g} "
                        f"gamma2:{self.vars[pfx+'gamma2'].get():.10g} gamma3:{self.vars[pfx+'gamma3'].get():.10g} "
                        f"depth:{self.vars[pfx+'depth'].get():.10g} int1:{self.vars[pfx+'int1'].get():.10g} "
                        f"int2:{self.vars[pfx+'int2'].get():.10g} int3:{self.vars[pfx+'int3'].get():.10g}\n"
                    )
            f.write("\n# [spectrum]\n")
            f.write("# velocidad_mm/s\tdatos_norm\tajuste_norm\tresiduo\tcuentas_dobladas\n")
            for v, y, m, raw in zip(self.velocity, self.y_data, model, self.folded_raw):
                f.write(f"{v:.8f}\t{y:.8f}\t{m:.8f}\t{(y-m):.8f}\t{raw:.6f}\n")
            if self.fit_mode_var.get() == "bhf_distribution" and self.last_bhf_fit is not None:
                f.write("\n# [bhf_distribution]\n")
                f.write("# BHF_T\tP_amplitud\tP_normalizada\n")
                for b, p, pn in zip(self.last_bhf_fit.bhf_centers, self.last_bhf_fit.weights, self.last_bhf_fit.probability):
                    f.write(f"{b:.8f}\t{p:.10g}\t{pn:.10g}\n")
                if self.last_bhf_fit.sharp_bhf_centers is not None and self.last_bhf_fit.sharp_weights is not None:
                    f.write("\n# [sharp_components]\n")
                    f.write("# idx\tkind\tBHF_T\tamplitud\n")
                    for idx, b, w in zip(self.last_bhf_sharp_indices, self.last_bhf_fit.sharp_bhf_centers, self.last_bhf_fit.sharp_weights):
                        b_txt = f"{float(b):.8f}" if np.isfinite(float(b)) else "nan"
                        f.write(f"{idx}\t{self.component_kind[idx].get()}\t{b_txt}\t{float(w):.10g}\n")
        messagebox.showinfo("Guardado", f"Ajuste guardado en:\n{filename}")


if __name__ == "__main__":
    app = MossbauerFe33GUI()
    app.mainloop()
