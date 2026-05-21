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
import urllib.error
import urllib.request

import numpy as np
from scipy.optimize import least_squares
from scipy.special import wofz

from mossbauer_distribution import (
    fit_hyperfine_distribution as fit_hyperfine_distribution_engine,
    fit_gaussian_hyperfine_distribution as fit_gaussian_hyperfine_distribution_engine,
    fit_binomial_hyperfine_distribution as fit_binomial_hyperfine_distribution_engine,
    fit_fixed_hyperfine_distribution as fit_fixed_hyperfine_distribution_engine,
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
APP_NAME = "Mössbauer Fe-57 v2IA"
APP_VERSION = "0.1.0"
APP_AUTHOR = "Jorge Sánchez Marcos"
APP_DEPARTMENT = "Departamento de Química Física · UAM"
LINE_PROFILE_KIND = "Lorentziana"
VOIGT_SIGMA = 0.05
CONFIG_DIR = Path.home() / ".config" / "mossbauer_fe33_gui"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
README_PATH = Path(__file__).with_name("README.md")
CHANGELOG_PATH = Path(__file__).with_name("CHANGELOG.md")


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
    """Perfil de línea normalizado a altura máxima 1.

    Por defecto es Lorentziana: γ²/((v−c)² + γ²), con γ=HWHM.
    Si LINE_PROFILE_KIND='Voigt', usa una convolución Voigt con sigma gaussiana
    global VOIGT_SIGMA y gamma Lorentziana HWHM.
    """
    if LINE_PROFILE_KIND == "Voigt":
        sigma = max(float(VOIGT_SIGMA), 1e-9)
        z = ((v - center) + 1j * gamma) / (sigma * np.sqrt(2.0))
        prof = np.real(wofz(z)) / (sigma * np.sqrt(2.0 * np.pi))
        max_prof = float(np.nanmax(prof)) if prof.size else 1.0
        return prof / max(max_prof, 1e-12)
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
        self.title("Ajuste Mössbauer Fe-57 v2IA")
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
        self.line_profile_var = tk.StringVar(value="Lorentziana")
        self.dist_variable_var = tk.StringVar(value="BHF")
        self.dist_shape_var = tk.StringVar(value="Histograma")
        self.dist_use_sharp_var = tk.BooleanVar(value=False)
        self.fixed_distribution_path: Path | None = None
        self.dist_refine_global_var = tk.BooleanVar(value=False)
        self.ai_ollama_url_var = tk.StringVar(value="http://localhost:11434")
        self.ai_ollama_model_var = tk.StringVar(value="")
        self.last_bhf_fit = None
        self.last_bhf_sharp_indices: list[int] = []
        self.sextet_enabled: dict[int, tk.BooleanVar] = {1: tk.BooleanVar(value=True), 2: tk.BooleanVar(value=False), 3: tk.BooleanVar(value=False)}
        self.component_kind: dict[int, tk.StringVar] = {1: tk.StringVar(value="Sextete"), 2: tk.StringVar(value="Sextete"), 3: tk.StringVar(value="Sextete")}
        self.current_file_var = tk.StringVar(value="Sin fichero cargado")
        self.last_fit_free_keys: list[str] = []
        self.last_fit_cov: np.ndarray | None = None
        self.last_fit_param_errors: dict[str, float] = {}
        # Restricciones lineales: target = factor * source + offset.
        self.constraints: list[dict[str, object]] = []

        self.vars: dict[str, tk.DoubleVar] = {}
        self.entry_vars: dict[str, tk.StringVar] = {}
        self.fixed_vars: dict[str, tk.BooleanVar] = {}
        self.slider_specs: dict[str, tuple[float, float, float]] = {}

        self._build_ui()

        for default in (Path("FE040723.ws5"), Path("Ja271025.ws5")):
            if default.exists():
                self.load_ws5(default)
                break

        self.load_settings()
        if self.counts is not None:
            self.refold_data()
            self.update_plot()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(150, self.show_startup_splash)
        self.after(2500, lambda: self.check_for_updates(silent=True))

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
        file_menu.add_command(label="Medidas web...", command=lambda: self.open_web_download_dialog(kind="mossbauer"))
        file_menu.add_command(label="Calibraciones web...", command=self.open_calibration_download_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Guardar ajuste...", command=self.save_fit)
        file_menu.add_separator()
        file_menu.add_command(label="Guardar sesión...", command=self.save_session_dialog)
        file_menu.add_command(label="Subir sesión JSON a web...", command=self.open_web_upload_analysis_dialog)
        file_menu.add_command(label="Cargar sesión...", command=self.load_session_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self.on_close)
        menubar.add_cascade(label="Archivo", menu=file_menu)

        fit_menu = tk.Menu(menubar, tearoff=0)
        fit_menu.add_command(label="Buscar centro", command=self.auto_center)
        fit_menu.add_command(label="Inicializar desde mínimos", command=self.auto_guess_from_minima)
        fit_menu.add_command(label="Autoajustar desde mínimos", command=self.auto_fit_from_minima)
        fit_menu.add_command(label="IA local Ollama: sugerir inicio...", command=self.open_ollama_ai_dialog)
        fit_menu.add_command(label="Ajustar", command=self.fit_current_data)
        fit_menu.add_separator()
        fit_menu.add_command(label="Fijar todos", command=self.fix_all_parameters)
        fit_menu.add_command(label="Liberar todos", command=self.free_all_parameters)
        menubar.add_cascade(label="Ajuste", menu=fit_menu)

        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_radiobutton(
            label="Ajuste con sextetes",
            variable=self.fit_mode_var,
            value="discrete",
            command=self.set_fit_mode_from_menu,
        )
        options_menu.add_radiobutton(
            label="Distribución P(BHF)",
            variable=self.fit_mode_var,
            value="bhf_distribution",
            command=self.set_fit_mode_from_menu,
        )
        options_menu.add_separator()
        options_menu.add_checkbutton(label="Mostrar diferencia", variable=self.show_residual_var, command=self.update_plot)
        options_menu.add_checkbutton(label="Mostrar leyenda", variable=self.show_legend_var, command=self.update_plot)
        options_menu.add_separator()
        profile_menu = tk.Menu(options_menu, tearoff=0)
        profile_menu.add_radiobutton(label="Lorentziana", variable=self.line_profile_var, value="Lorentziana", command=self.on_line_profile_change)
        profile_menu.add_radiobutton(label="Voigt", variable=self.line_profile_var, value="Voigt", command=self.on_line_profile_change)
        options_menu.add_cascade(label="Perfil de línea", menu=profile_menu)
        options_menu.add_separator()
        options_menu.add_checkbutton(
            label="P(BHF): sumar componentes activos nítidos",
            variable=self.dist_use_sharp_var,
            command=self.on_bhf_distribution_option_change,
        )
        options_menu.add_checkbutton(
            label="P(BHF): refinar δ y Γ globales",
            variable=self.dist_refine_global_var,
            command=self.on_bhf_distribution_option_change,
        )
        options_menu.add_separator()
        options_menu.add_command(label="Restricciones entre parámetros...", command=self.open_constraints_dialog)
        menubar.add_cascade(label="Opciones", menu=options_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Ayuda", command=self.show_help)
        help_menu.add_command(label="Acerca de", command=self.show_about)
        help_menu.add_separator()
        help_menu.add_command(label="Changelog", command=self.show_changelog)
        help_menu.add_command(label="Buscar actualizaciones...", command=lambda: self.check_for_updates(silent=False))
        menubar.add_cascade(label="Ayuda", menu=help_menu)
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
        title_block = tk.Frame(header, bg="#075985", bd=0, highlightthickness=0)
        title_block.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12, pady=8)
        ttk.Label(title_block, text=APP_NAME, style="Header.TLabel").pack(anchor=tk.W)
        ttk.Label(title_block, text="Doblado, simulación y ajuste interactivo", style="HeaderSub.TLabel").pack(anchor=tk.W, pady=(0, 5))
        ttk.Label(title_block, text=APP_AUTHOR, style="HeaderSub.TLabel").pack(anchor=tk.W)
        ttk.Label(title_block, text=APP_DEPARTMENT, style="HeaderSub.TLabel").pack(anchor=tk.W)

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
        self._add_slider(calib_box, "slope", "Pendiente", 0.0, -0.0001, 0.0001, 0.000001)
        self._add_slider(calib_box, "voigt_sigma", "σ gauss Voigt", 0.05, 0.0, 1.0, 0.001, fit_param=False)

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
            text="Tipo de ajuste y distribución: menú Opciones",
            style="Subtitle.TLabel",
        ).pack(side=tk.LEFT, anchor=tk.W)
        ttk.Button(sim_header, text="Ajuste", command=self.fit_current_data, style="Accent.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(sim_header, text="IA inicio", command=self.open_ollama_ai_dialog, style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(sim_header, text="Auto mínimos", command=self.auto_fit_from_minima, style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(sim_header, text="Fijar todos", command=self.fix_all_parameters, style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(sim_header, text="Liberar todos", command=self.free_all_parameters, style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))

        notebook = ttk.Notebook(sim_box)
        notebook.pack(fill=tk.X, expand=False)
        self.notebook = notebook
        dist_tab = ttk.Frame(notebook, padding=6)
        self.dist_tab = dist_tab
        notebook.add(dist_tab, text="Distribución BHF")
        dist_top = ttk.Frame(dist_tab)
        dist_top.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(
            dist_top,
            text="Distribución regularizada 1D: P(BHF) o P(ΔEQ). Puede sumar componentes activos nítidos.",
            style="Subtitle.TLabel",
        ).pack(side=tk.LEFT, anchor=tk.W)
        dist_cols = ttk.Frame(dist_tab)
        dist_cols.pack(fill=tk.X)
        d1 = ttk.Frame(dist_cols); d2 = ttk.Frame(dist_cols); d3 = ttk.Frame(dist_cols)
        d1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        d2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        d3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        ttk.Label(d1, text="Variable distribuida").pack(anchor=tk.W)
        dist_var_box = ttk.Combobox(d1, textvariable=self.dist_variable_var, values=("BHF", "ΔEQ"), width=10, state="readonly")
        dist_var_box.pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
        dist_var_box.bind("<<ComboboxSelected>>", lambda _event: self.on_bhf_distribution_option_change())
        ttk.Label(d1, text="Forma").pack(anchor=tk.W)
        dist_shape_box = ttk.Combobox(d1, textvariable=self.dist_shape_var, values=("Histograma", "Gaussiana", "Binomial", "Fija"), width=12, state="readonly")
        dist_shape_box.pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
        dist_shape_box.bind("<<ComboboxSelected>>", lambda _event: self.on_bhf_distribution_option_change())
        ttk.Button(d1, text="Cargar P fija...", command=self.load_fixed_distribution_file, style="Small.TButton").pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
        self._add_slider(d1, "dist_delta", "δ global", 0.0, -2.5, 2.5, 0.001, fit_param=False)
        self._add_slider(d1, "dist_quad", "ΔEQ fijo/global", 0.0, 0.0, 4.0, 0.001, fit_param=False)
        self._add_slider(d1, "dist_fixed_bhf", "BHF fijo p/ P(ΔEQ)", BHF_DEFAULT_T, 0.0, 50.0, 0.01, fit_param=False)
        self._add_slider(d1, "dist_gamma", "Γ HWHM", 0.18, 0.03, 1.0, 0.001, fit_param=False)
        self._add_slider(d2, "dist_bmin", "Mín distribución", 0.0, 0.0, 50.0, 0.1, fit_param=False)
        self._add_slider(d2, "dist_bmax", "Máx distribución", 50.0, 1.0, 60.0, 0.1, fit_param=False)
        self._add_slider(d2, "dist_nbins", "Bins distribución", 50.0, 10.0, 100.0, 1.0, fit_param=False)
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
            self._add_slider(c1, p + "delta", "δ isomérico", 0.0, -2.0, 3.0, 0.001)
            self._add_slider(c1, p + "quad", "ΔEQ", 0.0, 0.0, 4.0, 0.001)
            self._add_slider(c1, p + "bhf", "BHF (T)", BHF_DEFAULT_T, 0.0, 50.0, 0.01)
            self._add_slider(c2, p + "gamma1", "Γ 1,6", 0.30, 0.03, 2.0, 0.001)
            self._add_slider(c2, p + "gamma2", "Γ 2,5 rel", 1.0, 0.2, 3.0, 0.001)
            self._add_slider(c2, p + "gamma3", "Γ 3,4 rel", 1.0, 0.2, 3.0, 0.001)
            self._add_slider(c3, p + "depth", "Profundidad", 0.030 if idx == 1 else 0.005, 0.0, 0.30, 0.0005)
            self._add_slider(c3, p + "int1", "I1", 1.0, 0.0, 2.0, 0.001)
            self._add_slider(c3, p + "int2", "I2 rel", 1.0, 0.0, 3.0, 0.001)
            self._add_slider(c3, p + "int3", "I3 rel", 1.0, 0.0, 3.0, 0.001)

        plot_area = ttk.Frame(plot_frame)
        plot_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._refresh_distribution_tab_visibility(update=False)

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

    def settings_payload(self) -> dict:
        return {
            "geometry": self.geometry(),
            "vars": {k: float(v.get()) for k, v in self.vars.items()},
            "fixed": {k: bool(v.get()) for k, v in self.fixed_vars.items()},
            "sextet_enabled": {str(k): bool(v.get()) for k, v in self.sextet_enabled.items()},
            "component_kind": {str(k): v.get() for k, v in self.component_kind.items()},
            "fit_velocity": bool(self.fit_velocity_var.get()),
            "show_residual": bool(self.show_residual_var.get()),
            "show_legend": bool(self.show_legend_var.get()),
            "fit_mode": self.fit_mode_var.get(),
            "line_profile": self.line_profile_var.get(),
            "dist_variable": self.dist_variable_var.get(),
            "dist_shape": self.dist_shape_var.get(),
            "fixed_distribution_path": str(self.fixed_distribution_path) if self.fixed_distribution_path else None,
            "dist_use_sharp": bool(self.dist_use_sharp_var.get()),
            "dist_refine_global": bool(self.dist_refine_global_var.get()),
            "info_text": self.info.get("1.0", tk.END).strip() if hasattr(self, "info") else "",
            "constraints": self.constraints,
            "ai_ollama_url": self.ai_ollama_url_var.get(),
            "ai_ollama_model": self.ai_ollama_model_var.get(),
        }

    def load_settings(self) -> None:
        if not SETTINGS_PATH.exists():
            return
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            geom = data.get("geometry")
            if isinstance(geom, str):
                self.geometry(geom)
            self.updating_sliders = True
            for key, value in data.get("vars", {}).items():
                if key in self.vars:
                    self.vars[key].set(float(value))
                    self.entry_vars[key].set(self._format_value(key, float(value)))
            for key, value in data.get("fixed", {}).items():
                if key in self.fixed_vars:
                    self.fixed_vars[key].set(bool(value))
            for idx, value in data.get("sextet_enabled", {}).items():
                i = int(idx)
                if i in self.sextet_enabled:
                    self.sextet_enabled[i].set(bool(value))
            for idx, value in data.get("component_kind", {}).items():
                i = int(idx)
                if i in self.component_kind and value in ("Sextete", "Doblete", "Singlete"):
                    self.component_kind[i].set(value)
            self.fit_velocity_var.set(bool(data.get("fit_velocity", self.fit_velocity_var.get())))
            self.show_residual_var.set(bool(data.get("show_residual", self.show_residual_var.get())))
            self.show_legend_var.set(bool(data.get("show_legend", self.show_legend_var.get())))
            self.fit_mode_var.set(data.get("fit_mode", self.fit_mode_var.get()))
            self.line_profile_var.set(data.get("line_profile", self.line_profile_var.get()))
            self.on_line_profile_change()
            self.dist_variable_var.set(data.get("dist_variable", self.dist_variable_var.get()))
            self.dist_shape_var.set(data.get("dist_shape", self.dist_shape_var.get()))
            self.fixed_distribution_path = Path(data["fixed_distribution_path"]) if data.get("fixed_distribution_path") else None
            self.dist_use_sharp_var.set(bool(data.get("dist_use_sharp", self.dist_use_sharp_var.get())))
            self.dist_refine_global_var.set(bool(data.get("dist_refine_global", self.dist_refine_global_var.get())))
            self.constraints = list(data.get("constraints", self.constraints))
            self.ai_ollama_url_var.set(data.get("ai_ollama_url", self.ai_ollama_url_var.get()))
            self.ai_ollama_model_var.set(data.get("ai_ollama_model", self.ai_ollama_model_var.get()))
            info_text = data.get("info_text")
            if info_text and hasattr(self, "info"):
                self.info.delete("1.0", tk.END)
                self.info.insert(tk.END, info_text)
        except Exception:
            pass
        finally:
            self.updating_sliders = False
            self._refresh_distribution_tab_visibility(update=False)

    def save_settings(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(json.dumps(self.settings_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def on_close(self) -> None:
        self.save_settings()
        self.destroy()

    def show_startup_splash(self) -> None:
        self.show_logo_popup(title=APP_NAME, scale=2.0, click_to_close=True)

    def show_logo_popup(self, auto_close_ms: int | None = None, title: str = "Logo", scale: float = 1.0, click_to_close: bool = False) -> None:
        popup = tk.Toplevel(self)
        popup.title(title)
        popup.transient(self)
        popup.configure(background="#075985")
        popup.resizable(False, False)
        body = tk.Frame(popup, bg="#075985", padx=22, pady=18)
        body.pack(fill=tk.BOTH, expand=True)
        logo = self._create_logo(body, scale=scale)
        logo.pack(pady=(0, 10))
        tk.Label(body, text=APP_NAME, bg="#075985", fg="white", font=("TkDefaultFont", int(18 * scale), "bold")).pack()
        tk.Label(body, text="Doblado, simulación y ajuste interactivo", bg="#075985", fg="#dff6ff", font=("TkDefaultFont", int(10 * scale))).pack(pady=(2, 8))
        tk.Label(body, text=APP_AUTHOR, bg="#075985", fg="#dff6ff", font=("TkDefaultFont", int(9 * scale))).pack()
        tk.Label(body, text=APP_DEPARTMENT, bg="#075985", fg="#dff6ff", font=("TkDefaultFont", int(9 * scale))).pack()
        if click_to_close:
            tk.Label(body, text="Pulsa en esta ventana para continuar", bg="#075985", fg="#fef08a", font=("TkDefaultFont", int(9 * scale), "bold")).pack(pady=(12, 0))
            def close_popup(_event=None) -> None:
                if popup.winfo_exists():
                    popup.destroy()
            def bind_all_children(widget: tk.Widget) -> None:
                widget.bind("<Button-1>", close_popup)
                for child in widget.winfo_children():
                    bind_all_children(child)
            bind_all_children(popup)
        popup.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - popup.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - popup.winfo_height()) // 2)
        popup.geometry(f"+{x}+{y}")
        if auto_close_ms is not None:
            popup.after(auto_close_ms, popup.destroy)

    def show_text_window(self, title: str, text: str) -> None:
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("760x620")
        win.transient(self)
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        txt = tk.Text(frame, wrap=tk.WORD, background="#ffffff", foreground="#17202a", font=("TkDefaultFont", 10))
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(frame, command=txt.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        txt.configure(yscrollcommand=scroll.set)
        txt.insert("1.0", text)
        txt.configure(state=tk.DISABLED)

    def show_help(self) -> None:
        sections = [
            ("Inicio", "Inicio y filosofía", """
Este programa sirve para cargar, doblar, simular y ajustar espectros Mössbauer de ⁵⁷Fe.

Flujo de trabajo recomendado:

  1. Cargar un fichero local (.ws5, .adt) o descargarlo de la base de datos web.
  2. Revisar el folding point y Vmax. Si hay fichero .RES de Normos, se cargan automáticamente.
  3. Ajustar la línea base y comprobar que la normalización es correcta.
  4. Elegir modelo: discreto (singlete / doblete / sextete) o distribución P(BHF) / P(ΔEQ).
  5. Fijar los parámetros conocidos y liberar solo los necesarios.
  6. Lanzar el ajuste y examinar el residuo.
  7. Guardar el ajuste exportado y/o la sesión completa.

Filosofía del programa:

  Todos los parámetros están visibles y se pueden modificar manualmente antes, durante y después del ajuste. Un RMS bajo no garantiza interpretación física correcta. Conviene siempre comprobar:

  • Estabilidad del resultado al cambiar valores iniciales.
  • Ausencia de estructura sistemática en el residuo.
  • Que los errores 1σ sean razonables en relación con el efecto.
  • Que los porcentajes de área sean físicamente coherentes.

Notación usada en esta ayuda:

  δ = desplazamiento isomérico (mm/s, referido a α-Fe a temperatura ambiente)
  ΔEQ = desdoblamiento cuadrupolar (mm/s)
  BHF = campo hiperfino magnético (T)
  Γ = anchura de línea HWHM (mm/s)
"""),
            ("Espectroscopía Mössbauer", "Fundamentos físicos de la espectroscopía Mössbauer", """
La espectroscopía Mössbauer mide la absorción resonante sin retroceso de fotones gamma de 14.4 keV emitidos por ⁵⁷Co y absorbidos por ⁵⁷Fe en la muestra. El movimiento Doppler del transductor barre el desfase de energía.

Interacciones hiperfinas:

  Las interacciones entre el núcleo de ⁵⁷Fe y su entorno electrónico y magnético desdoblan los niveles nucleares y dan lugar al espectro:

  1. Interacción monopolar eléctrica → desplazamiento isomérico δ
       Refleja la densidad electrónica en el núcleo. Es sensible al estado de oxidación y enlace. Fe²⁺ tiene δ mayor que Fe³⁺ en entornos similares.

  2. Interacción cuadrupolar eléctrica → desdoblamiento cuadrupolar ΔEQ
       El gradiente de campo eléctrico (GCE) interacciona con el momento cuadrupolar del estado excitado (I=3/2). Produce un doblete en fases paramagnéticas o una corrección de primer orden en fases magnéticas. ΔEQ es cero en entornos cúbicos perfectos.

  3. Interacción magnética dipolar → campo hiperfino BHF
       El campo magnético en el núcleo (campo de contacto de Fermi + contribuciones orbitales y dipolares) divide el estado fundamental (I=1/2) en 2 subniveles y el excitado (I=3/2) en 4, dando lugar al sextete de 6 líneas permitidas (ΔmI = 0, ±1).

Reglas de selección e intensidades ideales:

  Para una muestra en polvo sin textura (orientaciones al azar), el promedio angular da las intensidades relativas:

  línea 1(6) : línea 2(5) : línea 3(4) = 3 : 2 : 1

  En monocristales o con campo externo aplicado, la relación depende del ángulo θ entre el campo hiperfino y la dirección del rayo gamma:

  líneas 1,6:  3(1 + cos²θ)
  líneas 2,5:  4 sin²θ
  líneas 3,4:  (1 + cos²θ)

  Casos particulares:

  θ = 0° (campo paralelo al rayo gamma):  3 : 0 : 1
  θ = 90° (campo perpendicular):           3 : 4 : 1
  Polvo (promedio angular):                 3 : 2 : 1

  Las intensidades relativas I2 e I3 (parámetros int2, int3) pueden ajustarse libremente para muestras texturadas o con campo externo aplicado.

Velocidades características de ⁵⁷Fe (valores de referencia a T ambiente):

  Fe metálico α-Fe:    δ ≈ 0.00,  ΔEQ ≈ 0.00,  BHF ≈ 33.0 T  (6 líneas)
  Fe³⁺ octaédrico:    δ ≈ 0.37,  ΔEQ ≈ 0.60–0.90 mm/s       (doblete)
  Fe²⁺ octaédrico:    δ ≈ 1.00–1.20,  ΔEQ ≈ 2.0–3.5 mm/s    (doblete)
  Magnetita Fe³⁺(A):  δ ≈ 0.28,  ΔEQ ≈ 0.00,  BHF ≈ 49.1 T  (sextete)
  Magnetita Fe²˙⁵⁺(B): δ ≈ 0.66, ΔEQ ≈ 0.00,  BHF ≈ 45.8 T  (sextete)
  Hematita α-Fe₂O₃:  δ ≈ 0.37,  ΔEQ ≈ −0.20, BHF ≈ 51.8 T  (sextete)
  Goetita α-FeOOH:   δ ≈ 0.37,  ΔEQ ≈ −0.25, BHF ≈ 38.0 T  (sextete)
  Ferritina:          δ ≈ 0.47,  ΔEQ ≈ 0.90 mm/s             (doblete)

  Estos valores son orientativos. La temperatura, sustituciones y desorden pueden desplazarlos.
"""),
            ("Archivo y web", "Carga de datos y descarga web", """
Formatos admitidos:

  • WS5 moderno: fichero XML con bloque <data>...</data>.
  • ADT antiguo: lista plana de cuentas enteras sin cabecera XML.
  • Ambos pueden tener ficheros sidecar Normos (.RES, .PLT, .JOB) que se leen automáticamente.

Menú Archivo:

  Cargar...
    Abre ficheros locales. Si existe .RES de Normos en el mismo directorio, se cargan el folding point, Vmax y parámetros iniciales automáticamente.

  Medidas web...
    Abre una ventana para introducir una URL de listado o descarga. La URL, usuario y contraseña se pueden guardar en el fichero local de credenciales para reutilizarlos.

  Calibraciones web...
    Igual que el anterior, pero guarda una URL separada para calibraciones dentro del mismo fichero de credenciales.

  Guardar ajuste...
    Exporta un fichero .dat con columnas: velocidad, datos normalizados, modelo, residuo, cuentas dobladas. En modo P(BHF) añade una tabla con BHF y P(BHF) normalizada.

  Guardar sesión...
    Guarda en JSON todo el estado de trabajo: cuentas, parámetros, fijos, componentes, covarianza, errores, restricciones, texto de estado. Permite retomar el trabajo exactamente donde se dejó.

  Subir sesión JSON a web...
    Busca en la lista web la entrada cuyo fichero de datos descargable tiene exactamente el mismo nombre que el fichero cargado y envía el JSON a su sección de análisis. Permite añadir una nota; si la web tiene campo de nota se envía allí, y en cualquier caso queda incluida dentro del JSON.

  Cargar sesión...
    Recupera una sesión guardada. Si el fichero de datos original está accesible se recarga; si no, se usan las cuentas guardadas en el JSON.

Ficheros sidecar Normos:

  Si junto al .ws5 existe un fichero .RES (resultados Normos), se extrae el folding point final y los parámetros del último ajuste como valores iniciales. Si existe .PLT, se lee Vmax. Esto facilita continuar un análisis iniciado en Normos.
"""),
            ("Folding", "Folding, velocidad y fondo", """
El folding simetriza el espectro triangular de velocidades en un espectro con eje simétrico, reduciendo el número de canales efectivos a la mitad. Es un paso previo obligatorio antes de modelar.

¿Qué es el punto de folding?

  El transductor genera una rampa triangular de velocidades. Los canales 1..N/2 corresponden a la rampa ascendente y los canales N/2+1..N a la descendente. El punto de simetría (folding point) es el canal donde la rampa invierte. En Normos se llama "Final folding point" y suele ser ≈ N/2 + fracción.

  Un error de 0.5 canales en el folding point introduce una asimetría antisimétrica visible en el residuo. Si el residuo muestra picos positivos a un lado y negativos al otro de cada línea, la causa más probable es un folding point incorrecto.

Parámetros:

  Vmax
    Velocidad máxima del transductor en mm/s. Construye el eje de velocidades desde −Vmax hasta +Vmax. El valor real se obtiene de la calibración con α-Fe. Valores típicos: 10–12 mm/s para espectros de Fe puro; hasta 20 mm/s para óxidos.

  Ajustar Vmax
    Incluye Vmax como parámetro libre en el ajuste. Útil si la calibración no es exacta, pero conviene fijar BHF simultáneamente para evitar correlación perfecta entre Vmax y BHF.

  Folding point
    Centro interno de simetría en unidades de canales. Acepta valores fraccionarios como Normos. El "Valor Normos aprox." mostrado en pantalla equivale aproximadamente al doble.

  Base
    Nivel de transmisión normalizado fuera de las líneas de absorción. Idealmente 1.0. Desviaciones indican mala normalización o saturación.

  Pendiente
    Fondo lineal (pendiente respecto a velocidad). Compensa ligeras asimetrías de fondo, pero no debe usarse para compensar un mal folding o una calibración incorrecta.

Diagnóstico de problemas de folding:

  • Residuos antisimétricos respecto al centro de cada línea → folding point incorrecto.
  • Fondo inclinado persistente → Vmax mal calibrado o pendiente real.
  • Base > 1.05 o < 0.95 → posible problema de normalización o saturación del detector.
"""),
            ("Modelo discreto", "Singlete, doblete y sextete", """
El modelo discreto superpone hasta tres componentes independientes. Cada uno puede ser singlete, doblete o sextete.

Tipos de componente:

  Singlete
    Una sola línea Lorentziana (o Voigt). Útil para fases con interacciones muy pequeñas no resueltas o para compuestos de Fe con simetría cúbica perfecta y sin campo magnético.

  Doblete
    Dos líneas simétricas separadas 2 × ΔEQ/2. Típico de Fe²⁺ o Fe³⁺ paramagnéticos con gradiente de campo eléctrico no nulo. La separación entre los dos picos del doblete visible en el espectro es directamente ΔEQ.

  Sextete
    Seis líneas magnéticas según las reglas de selección ΔmI = 0, ±1. Las posiciones dependen de BHF, δ y ΔEQ (corrección de primer orden).

Parámetros por componente (prefijo sN_ con N = 1, 2, 3):

  δ isomérico
    Desplazamiento del centro del patrón. Referido al estándar α-Fe a T ambiente.

  ΔEQ
    Desdoblamiento cuadrupolar. En el sextete actúa como corrección de primer orden: las líneas 1 y 6 se desplazan +ΔEQ/2 y las líneas 2-5 se desplazan −ΔEQ/2.

  BHF
    Campo hiperfino en teslas. Solo activo en sextete. A 33 T (α-Fe, T ambiente) las líneas externas están a ±5.33 mm/s aproximadamente.

  Γ (gamma1)
    Anchura HWHM de la línea más estrecha (líneas 1 y 6 del sextete, o la única línea del singlete/doblete). El valor mínimo físico está en torno a 0.097 mm/s (anchura natural del ⁵⁷Fe).

  Γ relativa líneas 2 y 5 (gamma2)
    Factor multiplicador sobre gamma1. 1.0 significa misma anchura que las líneas externas.

  Γ relativa líneas 3 y 4 (gamma3)
    Factor multiplicador sobre gamma1 para las líneas centrales.

  Profundidad
    Amplitud total de absorción. Es proporcional al espesor efectivo y a la abundancia de la fase. Los porcentajes de área se calculan a partir de este parámetro y las intensidades.

  Intensidades (int1, int2, int3)
    Pesos relativos de los tripletes de líneas del sextete (líneas 1&6, 2&5, 3&4). Los valores ideales para polvo sin textura son 3:2:1. Se pueden liberar para ajustar texturas o geometrías de medida no convencionales.

Porcentajes de área:

  El programa calcula el porcentaje de área de cada componente integrado sobre todas sus líneas. Son los valores que se publican habitualmente como "abundancias de fases". Aparecen en el panel Estado y parámetros tras cada ajuste.

Errores 1σ:

  Si la covarianza del ajuste es estimable (Jacobiano bien condicionado), se muestran los errores estadísticos 1σ de cada parámetro libre. Son solo errores estadísticos; el error sistemático (folding, calibración, modelo) suele ser mayor.
"""),
            ("Perfil de línea", "Lorentziana y Voigt", """
El programa admite dos perfiles de línea:

  Lorentziana (perfil por defecto)
    Es el perfil natural de una transición nuclear sin ensanchamiento inhomogéneo. Es la elección habitual para la mayoría de los ajustes Mössbauer. Colas más largas que una gaussiana.

  Voigt
    Convolución de Lorentziana (anchura natural) con Gaussiana (ensanchamiento inhomogéneo). Útil cuando hay una distribución de entornos locales que ensanchan simétricamente las líneas sin llegar a necesitar una distribución P(BHF) completa.

  El parámetro σ de la componente gaussiana del Voigt se fija en {voigt_s:.2f} mm/s en esta versión.

Cuándo usar Voigt:

  • Las líneas son claramente más anchas de lo esperado pero mantienen forma simétrica.
  • Se sospecha ensanchamiento inhomogéneo moderado (nanocristales, sustituciones parciales).
  • El ajuste Lorentziano deja residuos en las alas de las líneas.

Cuándo usar P(BHF) en su lugar:

  • El ensanchamiento es asimétrico o tiene estructura (hombros, picos secundarios).
  • Se sospecha una distribución real de campos hiperfinos (desorden magnético, tamaño de partícula).
  • El Voigt no mejora suficientemente el residuo.
""".format(voigt_s=VOIGT_SIGMA)),
            ("P(BHF): idea", "Distribución de campo hiperfino P(BHF)", """
P(BHF) se usa cuando no hay un único campo hiperfino sino una distribución continua de campos. En lugar de uno o varios sextetes bien definidos, el espectro se describe como suma de muchos sextetes con BHF distinto.

¿Cuándo usar P(BHF)?

  • Materiales amorfos o nanocristalinos con distribución de entornos magnéticos.
  • Ferritas con sustituciones catiónicas (Zn, Mn, Co...) que generan variación de BHF.
  • Nanopartículas con distribución de tamaños: las partículas más pequeñas tienen BHF más bajo por relajación superparamagnética.
  • Interfaces y superficies donde el campo hiperfino varía.
  • Cualquier sistema donde las líneas del sextete estén claramente ensanchadas de forma asimétrica.

Interpretación de P(BHF):

  P(BHF) indica la fracción del espectro que proviene de iones Fe con cada valor de campo hiperfino. No es directamente una función de distribución de tamaños ni de composición, aunque en muchos sistemas hay correlación.

  Una P(BHF) con un pico bien definido indica una fase mayoritaria con campo bien determinado. Una P(BHF) ancha y sin estructura indica gran desorden magnético. Un hombro o pico secundario puede indicar una segunda fase.

Modelo simplificado:

  espectro = fondo − Σᵢ Pᵢ · sextete(Bᵢ, δ, ΔEQ, Γ)

  donde Bᵢ son los centros de los bins y Pᵢ son los pesos (no negativos).

Limitación fundamental:

  La inversión espectro → P(BHF) es un problema mal condicionado: existen infinitas distribuciones que ajustan igual de bien dentro del ruido. La regularización reduce la ambigüedad penalizando distribuciones rugosas, pero no la elimina. Dos distribuciones suavizadas distintas pueden dar residuos casi idénticos.
"""),
            ("P(BHF): método", "Método Hesse-Rübartsch y regularización", """
El motor implementa una aproximación tipo Hesse-Rübartsch (método estándar en espectroscopía Mössbauer):

Pasos del algoritmo:

  1. Se define una malla uniforme de N_bins campos entre B_mín y B_máx.
  2. Para cada bin se calcula el sextete correspondiente (matriz de respuesta A).
  3. Se buscan pesos P ≥ 0 que minimicen:

     residuo² + α · ||D² P||²

  4. D² es la matriz de segundas diferencias: penaliza la curvatura de P(BHF).
  5. El problema se resuelve iterativamente con restricción de no negatividad.

Función objetivo:

  χ² = ||y − A·P||² + α · ||D²·P||²

  El primer término mide el ajuste a los datos. El segundo mide la rugosidad de P(BHF).

Papel del parámetro α:

  α = 0        El ajuste reproduce el espectro al máximo, pero P(BHF) llena de picos espurios.
  α pequeño    P(BHF) detallada con posibles oscilaciones de ruido.
  α óptimo     Compromiso entre fidelidad al espectro y suavidad física.
  α grande     P(BHF) muy suave, quizás demasiado, perdiendo estructura real.

  El valor óptimo no es universal: depende de la relación señal/ruido, del número de canales, del número de bins y del ancho de línea. Siempre hay que explorar varios valores de α y comprobar que los rasgos principales de P(BHF) son estables.

Formas de P(BHF) disponibles:

  Histograma (libre, no paramétrica)
    Cada bin tiene un peso independiente ajustable. Máxima flexibilidad, más sensible a la elección de α. Es la forma más usada.

  Gaussiana
    La distribución se parametriza como una gaussiana (centro, anchura, amplitud). Reduce los grados de libertad a 3. Útil cuando se espera una distribución unimodal bien definida. No necesita α.

  Binomial
    Modelo combinatorio para ferritas con sustituciones catiónicas. La forma de P(BHF) viene dada por la distribución binomial del número de sustituyentes en los primeros vecinos. Solo ajusta probabilidad de sustitución y amplitud. No necesita α.

  Fija
    Carga una P(BHF) definida externamente (fichero con dos columnas: centro, peso) y solo ajusta la amplitud global, baseline y slope. Útil para comparar con distribuciones publicadas o para refinar δ y Γ manteniendo la forma fija.

  Las cuatro formas admiten componentes nítidos (activando "sumar componentes activos nítidos"). Los nítidos se ajustan simultáneamente con la distribución en todos los casos.
"""),
            ("P(BHF): parámetros", "Parámetros de la distribución P(BHF)", """
Parámetros globales (comunes a todos los sextetes de la distribución):

  δ global
    Desplazamiento isomérico común. Si la distribución contiene fases con δ muy distinto, es mejor usar componentes nítidos para cada fase.

  ΔEQ global
    Cuadrupolo común (corrección de primer orden). Puede refinarse junto con δ activando la opción "Refinar δ y Γ globales".

  Γ HWHM
    Anchura de línea común a todos los bins. Una Γ más grande suaviza la distribución y reduce la inestabilidad pero oscurece estructura fina. Una Γ más pequeña puede reproducir mejor picos estrechos pero requiere α mayor para estabilizar.

Parámetros de la malla:

  B mín
    Límite inferior de la distribución. B_mín = 0 permite absorber contribuciones de bajo campo (fases paramagnéticas, relajación), pero puede introducir peso artificial si no hay señal real en esa zona. Para fases puramente magnéticas conviene empezar en 10–20 T.

  B máx
    Límite superior. Debe superar el BHF máximo esperado. Para hematita (~52 T) conviene B_máx ≥ 55 T. Para α-Fe (~33 T) basta con 36–38 T.

  Bins BHF
    Número de puntos de la malla. Más bins = mayor resolución potencial + mayor inestabilidad. Para espectros típicos de 512 canales, 30–60 bins suele ser suficiente. Con muchos bins y α bajo pueden aparecer oscilaciones artefacto.

Control de regularización:

  log10 α
    Logaritmo del parámetro de regularización. Un valor de −2 a 0 es habitual. Variar en pasos de 0.5 y observar la estabilidad de P(BHF) y del RMS.

  L-curve α
    Escanea automáticamente un rango de α y traza la curva L (log residuo vs. log rugosidad). El punto de máxima curvatura ("codo") suele indicar un α razonable. Es un punto de partida, no una respuesta definitiva.

  Distribución fija
    Carga una P(BHF) externa (dos columnas: BHF, peso) y la aplica sin ajustar los pesos. Útil para comparar con resultados de otras referencias o para refinar solo δ, Γ con una distribución conocida.
"""),
            ("P(BHF): nítidos", "Componentes nítidos junto a la distribución", """
Es posible combinar una distribución P(BHF) o P(ΔEQ) continua con uno o más componentes discretos ("nítidos") en el mismo ajuste. Los nítidos funcionan con todas las formas de distribución: Histograma, Gaussiana, Binomial y Fija.

Cómo activarlo:

  Marcar la opción "sumar componentes activos nítidos" en la pestaña Distribución.

  Al activarla, el componente 1 se usa siempre como nítido. Los componentes 2 y 3 se usan si están activados ("Usar componente 2/3" marcado en su pestaña). Sus parámetros (δ, ΔEQ, BHF, Γ, intensidades) se toman de los sliders de cada pestaña de componente.

Cuándo es útil:

  • Una muestra tiene una fase mayoritaria desordenada (P(BHF) ancha) y una fase minoritaria bien definida (sextete estrecho).
  • Ejemplo: ferrita de zinc con distribución amplia + traza de α-Fe a BHF ≈ 33 T.
  • Ejemplo: óxido de Fe amorfo (P(BHF) amplia) + doblete de Fe²⁺ paramagnético.
  • Ejemplo: vidrio con P(ΔEQ) ancha + singlete de Fe metálico.

Cómo funciona internamente:

  • La distribución (pesos de los bins) se ajusta como siempre (con regularización en Histograma, paramétricamente en Gaussiana/Binomial, con amplitud global en Fija).
  • Los componentes nítidos se añaden como columnas adicionales al sistema de ecuaciones.
  • Sus amplitudes se ajustan junto con los pesos de la distribución, con restricción de no negatividad, pero sin regularización.
  • El panel Estado muestra por separado el porcentaje de área de la distribución y de cada componente nítido.

Diferencias entre formas:

  Histograma
    Máxima flexibilidad para la distribución. Los nítidos compiten con los bins de la distribución solo si solapan en el espectro. Es la combinación más usada.

  Gaussiana / Binomial
    La distribución tiene pocos parámetros y forma rígida. Los nítidos son especialmente útiles aquí porque absorben las fases que la distribución no puede reproducir por su forma fija.

  Fija
    La forma de la distribución está predefinida. Los nítidos permiten añadir contribuciones no incluidas en la distribución externa.

Precauciones:

  • Un componente nítido puede competir con un pico de P(BHF) si el BHF del nítido cae dentro del rango de la distribución. El ajuste puede distribuir la señal arbitrariamente entre ambos.
  • Si el nítido tiene BHF conocido (p. ej. α-Fe a 33 T como calibrante), conviene fijarlo.
  • Conviene comparar el ajuste con y sin el componente nítido para verificar que aporta mejora estadística real.
  • Aumentar α puede transferir peso del nítido a la distribución o viceversa.
  • Si un nítido sale con peso ≈ 0, probablemente no es necesario en el modelo.
"""),
            ("P(ΔEQ): distribución", "Distribución de desdoblamiento cuadrupolar P(ΔEQ)", """
P(ΔEQ) es el análogo cuadrupolar de P(BHF): en lugar de distribuir campos hiperfinos, distribuye valores de desdoblamiento cuadrupolar ΔEQ manteniendo un BHF fijo común a todos los dobletes o sextetes de la distribución.

Cómo se activa:

  En la pestaña Distribución, el selector "Variable de distribución" permite elegir entre BHF y ΔEQ. Al seleccionar ΔEQ, los sliders "Mín distribución" y "Máx distribución" pasan a operar en mm/s (rango de ΔEQ), y aparece el parámetro "BHF fijo p/ P(ΔEQ)".

¿Cuándo usar P(ΔEQ)?

  • Fases paramagnéticas con distribución de entornos locales: Fe³⁺ o Fe²⁺ en vidrios, zeolitas, arcillas o materiales amorfos, donde cada ión Fe ve un gradiente de campo eléctrico (GCE) diferente.
  • Materiales con desorden estructural que produce una distribución de distorsiones del poliedro de coordinación, sin que haya campo magnético relevante.
  • Superparamagnéticos por encima de su temperatura de bloqueo: el espectro colapsa a un doblete ancho cuya anchura real refleja la distribución de ΔEQ y/o relajación.
  • Vidrios de óxido de hierro, ferritinas, proteínas con Fe, silicatos con Fe²⁺ en sitios distorsionados.

Diferencia fundamental con P(BHF):

  En P(BHF) el espectro es suma de sextetes con distintos campos. En P(ΔEQ) el espectro es suma de sextetes (o dobletes si BHF = 0) con distintos valores de ΔEQ y un único BHF fijo:

  espectro = fondo − Σᵢ Pᵢ · sextete(BHF_fijo, ΔEQᵢ, δ, Γ)

  Si BHF_fijo = 0, cada término es un doblete, y P(ΔEQ) es literalmente la distribución de separaciones de un conjunto de dobletes.

Interpretación física de P(ΔEQ):

  P(ΔEQ) indica qué fracción de los iones Fe presenta cada valor de desdoblamiento cuadrupolar. Un pico estrecho corresponde a un entorno bien definido; una distribución ancha indica desorden en la geometría de coordinación o en la distribución de cargas alrededor del núcleo.
"""),
            ("P(ΔEQ): parámetros", "Parámetros específicos de P(ΔEQ)", """
Selector de variable de distribución:

  Variable de distribución
    Selector BHF / ΔEQ en la pestaña Distribución. Al cambiar a ΔEQ, los sliders de rango pasan a mm/s y se habilita el BHF fijo. El resto de controles (α, bins, Γ, δ, forma) funcionan igual que en P(BHF).

Parámetros específicos de P(ΔEQ):

  BHF fijo p/ P(ΔEQ)
    Campo hiperfino único compartido por todos los sextetes de la distribución. Si se fija a 0, cada bin es un doblete. Si se fija a un valor distinto de cero (p. ej. 33 T para α-Fe), cada bin es un sextete con la separación magnética correspondiente y un desdoblamiento cuadrupolar variable. Fijar BHF fijo en el valor del campo de la fase estudiada y dejar que P(ΔEQ) recoja la distribución de entornos locales.

  Mín distribución (en mm/s para P(ΔEQ))
    Valor mínimo de ΔEQ en la malla. Para dobletes paramagnéticos sin campo aplicado conviene empezar en 0 mm/s. Si se sabe que ΔEQ mínimo es mayor (p. ej. el sistema siempre tiene al menos 0.5 mm/s de desdoblamiento), se puede restringir el rango para mejorar la estabilidad.

  Máx distribución (en mm/s para P(ΔEQ))
    Valor máximo de ΔEQ. Para Fe²⁺ con desorden puede llegar a 3–4 mm/s; para Fe³⁺ rara vez supera 2 mm/s. Un rango innecesariamente amplio dilata los bins y reduce la resolución.

  δ global
    Desplazamiento isomérico común a todos los bins. Si la muestra tiene iones Fe con δ muy distintos (p. ej. mezcla Fe²⁺ / Fe³⁺), no es apropiado usar una sola P(ΔEQ); conviene un componente nítido para cada especie o subdividir el análisis.

  ΔEQ fijo/global
    En modo P(ΔEQ) este parámetro no se usa como variable de distribución, pero si se activa "refinar δ y Γ globales" se puede refinar junto con δ. En modo P(BHF) sí actúa como ΔEQ único para todos los sextetes de la distribución.

  Γ HWHM
    Anchura de línea de cada bin. Igual que en P(BHF): una Γ más grande suaviza la distribución resultante.

  log10 α, L-curve α, Bins, forma
    Funcionan exactamente igual que en P(BHF). Ver los capítulos P(BHF): método y P(BHF): parámetros.

Casos típicos de configuración:

  Vidrio de Fe³⁺ paramagnético (doblete ancho):
    BHF fijo = 0, δ ≈ 0.35 mm/s, Mín = 0, Máx = 2.0 mm/s, Γ ≈ 0.15 mm/s.

  Fe²⁺ en silicato distorsionado (doblete muy ancho):
    BHF fijo = 0, δ ≈ 1.1 mm/s, Mín = 0, Máx = 4.0 mm/s, Γ ≈ 0.15–0.20 mm/s.

  Fase magnética con distribución de ΔEQ (p. ej. hematita con desorden):
    BHF fijo ≈ 51.8 T, δ ≈ 0.37 mm/s, Mín = −0.8, Máx = 0.8 mm/s, Γ ≈ 0.15 mm/s.

Precauciones específicas de P(ΔEQ):

  • Con BHF fijo ≠ 0, la distribución de ΔEQ puede correlacionarse con el δ global: un cambio de δ puede compensarse parcialmente con un desplazamiento de toda P(ΔEQ). Conviene fijar δ si es conocido.
  • Si el espectro tiene tanto distribución de BHF como de ΔEQ, ninguno de los dos modos unidimensionales será completamente satisfactorio. En ese caso, el modelo más honesto es P(BHF) con ΔEQ como corrección de primer orden global, o viceversa según cuál sea la fuente dominante de ensanchamiento.
  • Los porcentajes de área se calculan igual que en P(BHF): integral de los pesos de la distribución más los componentes nítidos si los hay.
"""),
            ("Restricciones", "Restricciones lineales entre parámetros", """
Las restricciones permiten imponer relaciones lineales entre parámetros de distintos subespectros. Se configuran en:

  Opciones → Restricciones entre parámetros...

Forma matemática:

  destino = factor × origen + suma

  El parámetro destino no se ajusta directamente: en cada evaluación del modelo se recalcula a partir del origen.

Ejemplos prácticos:

  s2_gamma1 = 1.0 × s1_gamma1 + 0
    Fuerza a que la anchura del subespectro 2 sea igual a la del subespectro 1.

  s2_int1 = 0.5 × s1_int1 + 0
    La intensidad I1 del subespectro 2 será la mitad de la del subespectro 1.

  s3_delta = 1.0 × s1_delta + 0.15
    El δ del subespectro 3 queda 0.15 mm/s por encima del del subespectro 1.

  s2_depth = 0.333 × s1_depth + 0
    La profundidad del subespectro 2 es 1/3 de la del subespectro 1.

Columnas de la tabla:

  Activa
    Permite activar o desactivar una restricción sin borrarla.

  Destino
    Parámetro dependiente. Se recalcula automáticamente.

  Origen
    Parámetro independiente del que depende el destino.

  Factor
    Multiplicador aplicado al origen.

  Suma
    Término constante añadido al final.

Cómo actúan durante el ajuste:

  • El parámetro destino no es libre: no tiene entrada en el vector de parámetros del optimizador.
  • En cada evaluación del modelo se aplica: destino ← factor × origen + suma.
  • Si el slider del origen se mueve manualmente, el destino se actualiza en tiempo real.
  • Si el resultado cae fuera del rango permitido del destino, se recorta al límite.

Usos típicos:

  • Igualar anchuras de dos fases con el mismo tipo de Fe: s2_gamma1 = 1 × s1_gamma1 + 0.
  • Mantener una relación de intensidades conocida por geometría: s2_depth = 0.5 × s1_depth + 0.
  • Imponer que dos δ son iguales: s2_delta = 1 × s1_delta + 0.
  • Añadir un desplazamiento de segundo orden conocido: s2_delta = 1 × s1_delta + 0.08.
  • Reducir el número de parámetros libres cuando hay correlaciones fuertes.

Precauciones:

  • Evita cadenas circulares: A depende de B y B depende de A.
  • No uses restricciones para forzar un resultado físico si el residuo empeora claramente.
  • Una restricción demasiado estricta puede sesgar el ajuste si el supuesto físico es solo aproximado; en ese caso, liberar ambos parámetros y comprobar si la diferencia es significativa.
  • Las restricciones activas se muestran en el panel Estado y parámetros, y se guardan en sesiones.
"""),
            ("Guardar y exportar", "Guardar ajuste, sesión y opciones", f"""
Guardar ajuste (.dat):

  Exporta un fichero de texto con columnas tabuladas:
    velocidad (mm/s) | datos normalizados | modelo | residuo | cuentas dobladas

  En modo P(BHF) añade una sección con la tabla BHF-P(BHF) (amplitud y probabilidad normalizada).

  La cabecera del fichero incluye todos los parámetros relevantes (modo, Vmax, folding, factores de área, etc.) en formato legible por humanos y parseables por scripts.

Guardar sesión (.json):

  Guarda en JSON todo el estado de trabajo:
    • Cuentas originales (si no hay ruta accesible).
    • Todos los parámetros y sus valores actuales.
    • Cuáles están fijados y cuáles libres.
    • Tipo de componente (singlete/doblete/sextete) por subespectro.
    • Opciones de visualización.
    • Covarianza del último ajuste y errores 1σ.
    • Restricciones activas.
    • Texto del panel Estado y parámetros.

  La sesión permite retomar el trabajo exactamente donde se dejó, incluso en otro ordenador.

Opciones automáticas:

  Al cerrar el programa se guardan preferencias de visualización y último directorio usado en:

  {SETTINGS_PATH}

Recomendaciones:

  • Guardar la sesión antes de probar cambios arriesgados (liberar muchos parámetros, cambiar α).
  • El ajuste exportado (.dat) es el adecuado para adjuntar a publicaciones o enviar a colaboradores.
  • Si se publican resultados, anotar siempre el folding point, Vmax, modo de ajuste y α (en P(BHF)).
"""),
            ("Diagnóstico", "Residuos, errores frecuentes y buenas prácticas", """
El residuo (datos − modelo) debe parecerse al ruido estadístico. Cualquier estructura sistemática indica que el modelo no es adecuado o que hay un problema instrumental.

Patrones de residuo y sus causas habituales:

  Pares positivo-negativo en torno a cada línea (antisimétrico)
    → Folding point incorrecto o asimetría de velocidades. Corregir el folding point, no añadir componentes.

  Fondo inclinado o curvado
    → Vmax incorrecto, pendiente real del detector, o normalización errónea. No compensar con pendiente si el origen es instrumental.

  Líneas más anchas en el modelo que en los datos
    → Γ demasiado grande. Reducirla manualmente y ajustar de nuevo.

  Picos de residuo en las alas de las líneas (modelo más estrecho que los datos)
    → Considerar perfil Voigt o P(BHF) si el ensanchamiento es real.

  Residuo sistemático en el centro del espectro
    → Puede indicar un componente no modelado (doblete, singlete paramagnético).

  Residuo con estructura en P(BHF)
    → α demasiado grande (distribución demasiado suavizada). Reducir α.

  Oscilaciones de alta frecuencia en P(BHF) con buen residuo
    → α demasiado pequeño. La distribución está absorbiendo ruido. Aumentar α.

Errores frecuentes:

  • Añadir componentes hasta que el residuo mejore sin justificación física.
  • Liberar Vmax y BHF simultáneamente sin fijar ninguno de los dos.
  • Interpretar el mínimo encontrado como la única solución posible.
  • Usar α demasiado pequeño en P(BHF) y publicar picos espurios como fases reales.
  • Interpretar los errores 1σ estadísticos como errores totales del experimento.
  • Usar una pendiente grande para compensar un mal folding.

Buenas prácticas:

  • Probar al menos 3-5 conjuntos distintos de valores iniciales para confirmar el mínimo.
  • Fijar BHF en los rangos conocidos para el sistema antes de liberar todos los parámetros.
  • Comparar modelos con el mismo criterio (mismo χ² reducido o RMS).
  • En P(BHF), variar α en un rango de 2–3 órdenes de magnitud y comprobar estabilidad.
  • Guardar sesiones alternativas cuando hay ambigüedad en el modelo.
  • Si dos modelos dan residuos similares, preferir el más parsimonioso (menos parámetros libres).
  • Informar siempre el número de canales, Vmax, temperatura de medida y referencia de δ.
"""),
            ("Parámetros de referencia", "Valores de referencia para fases comunes de Fe", """
Esta sección recoge valores típicos publicados en la literatura para orientar el ajuste inicial. Los valores pueden variar según temperatura, composición y entorno.

Temperatura ambiente (≈ 295 K), referencia α-Fe:

  α-Fe (hierro metálico):
    δ = 0.00 mm/s   ΔEQ = 0.00 mm/s   BHF = 33.0 T   Γ ≈ 0.13–0.15 mm/s

  γ-Fe₂O₃ (maghemita), sitio tetraédrico (A):
    δ ≈ 0.22 mm/s   ΔEQ ≈ 0.00 mm/s   BHF ≈ 49.7 T

  γ-Fe₂O₃ (maghemita), sitio octaédrico (B):
    δ ≈ 0.33 mm/s   ΔEQ ≈ 0.00 mm/s   BHF ≈ 50.6 T

  α-Fe₂O₃ (hematita, T > T_Morin ≈ 263 K):
    δ ≈ 0.37 mm/s   ΔEQ ≈ −0.20 mm/s  BHF ≈ 51.8 T

  α-Fe₂O₃ (hematita, T < T_Morin):
    δ ≈ 0.37 mm/s   ΔEQ ≈ +0.40 mm/s  BHF ≈ 54.2 T

  Fe₃O₄ (magnetita), sitio A (Fe³⁺):
    δ ≈ 0.28 mm/s   ΔEQ ≈ 0.00 mm/s   BHF ≈ 49.1 T

  Fe₃O₄ (magnetita), sitio B (Fe²˙⁵⁺):
    δ ≈ 0.66 mm/s   ΔEQ ≈ 0.00 mm/s   BHF ≈ 45.8 T

  α-FeOOH (goetita):
    δ ≈ 0.37 mm/s   ΔEQ ≈ −0.25 mm/s  BHF ≈ 38.2 T

  β-FeOOH (akaganeíta):
    δ ≈ 0.37 mm/s   ΔEQ ≈ 0.55 mm/s  (doblete paramagnético a T amb.)

  γ-FeOOH (lepidocrocita):
    δ ≈ 0.37 mm/s   ΔEQ ≈ 0.53 mm/s  (doblete paramagnético a T amb.)

  Fe²⁺ octaédrico (general):
    δ ≈ 1.0–1.2 mm/s   ΔEQ ≈ 2.0–3.5 mm/s

  Fe³⁺ octaédrico paramagnético:
    δ ≈ 0.35–0.45 mm/s   ΔEQ ≈ 0.60–0.90 mm/s

  Fe³⁺ tetraédrico paramagnético:
    δ ≈ 0.18–0.25 mm/s   ΔEQ ≈ 0.20–0.50 mm/s

  FeS₂ (pirita):
    δ ≈ 0.31 mm/s   ΔEQ ≈ 0.61 mm/s

Notas de uso:

  • Los valores de BHF disminuyen con la temperatura siguiendo aproximadamente una ley de Bloch.
  • En nanopartículas, BHF es típicamente más bajo que en el bulk por efectos de superficie y relajación.
  • Hematita: por debajo de la transición de Morin (~263 K), el espín se reorienta y ΔEQ cambia de signo (de −0.20 a +0.40 mm/s) y BHF aumenta ligeramente (~54 T). En nanopartículas la T de Morin baja o desaparece.
  • Magnetita: la transición de Verwey (~120 K) desdobla el sitio B en múltiples componentes. Por encima de Verwey, el sitio B muestra un solo sextete por promedio rápido de electrones.
  • Para ajustes publicables, usar valores de referencia de la literatura del sistema específico.
  • Los valores de δ se dan referidos a α-Fe a temperatura ambiente. Para convertir a otra referencia, sumar la diferencia de δ entre los estándares.
"""),
            ("Atajos y flujo rápido", "Flujo de trabajo eficiente", """
Controles principales:

  Botón "Ajuste"
    Lanza el ajuste con los parámetros libres actuales. En modo discreto usa least_squares; en modo distribución usa el motor correspondiente a la forma seleccionada.

  Botón "Liberar todos"
    Desmarca todos los checkboxes "fijo", permitiendo que todos los parámetros se ajusten.

  Botón "Fijar todos"
    Marca todos los checkboxes "fijo". Útil antes de liberar selectivamente solo los parámetros deseados.

  Menú Opciones → Tipo de ajuste
    Cambia entre modelo discreto y distribución P(BHF)/P(ΔEQ).

  Menú Opciones → Restricciones
    Abre el diálogo de restricciones lineales entre parámetros.

  Casillas de entrada numérica
    Además de los sliders, se puede escribir un valor exacto en la casilla y pulsar Enter para aplicarlo.

Flujo rápido para un espectro conocido:

  1. Cargar el espectro.
  2. Comprobar que el folding point y Vmax son correctos (mirar si las líneas externas terminan en ≈ Vmax).
  3. Seleccionar tipo de componente (Sextete para fases magnéticas, Doblete para paramagnéticas).
  4. Fijar BHF al valor esperado, liberar δ, ΔEQ y Profundidad.
  5. Pulsar Ajuste. Revisar residuo.
  6. Si el residuo es bueno, liberar también Γ.
  7. Ajustar de nuevo. Anotar RMS.
  8. Guardar sesión.

Flujo para espectro con P(BHF):

  1. Cargar y verificar folding.
  2. En Opciones, seleccionar "Distribución P(BHF)/P(ΔEQ)".
  3. Estimar B_mín, B_máx, δ y Γ globales.
  4. Empezar con log10 α = 0 (muy suave) y ajustar.
  5. Reducir α en pasos de 0.5 hasta que aparezca estructura estable en P(BHF).
  6. Usar L-curve α para orientarse sobre el valor óptimo.
  7. Comparar P(BHF) a 3–4 valores de α para identificar rasgos robustos.
  8. Si hay fases discretas, activar "sumar componentes activos nítidos" y configurar los componentes.
  9. Guardar sesión para cada α significativo.

Flujo para P(BHF) Gaussiana/Binomial con nítidos:

  1. Configurar la distribución como arriba.
  2. Seleccionar forma Gaussiana o Binomial.
  3. Activar "sumar componentes activos nítidos".
  4. Configurar los parámetros del nítido (p. ej. singlete o doblete paramagnético).
  5. Ajustar. El programa optimiza simultáneamente la distribución paramétrica y los pesos de los nítidos.
  6. Comparar el RMS con y sin nítidos para verificar que aportan mejora.
"""),
        ]

        win = tk.Toplevel(self)
        win.title("Ayuda Mössbauer Fe-57 v2IA")
        win.geometry("1050x720")
        win.transient(self)
        win.configure(background="#eaf4ff")

        header = tk.Frame(win, bg="#075985", padx=14, pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text="Ayuda Mössbauer Fe-57 v2IA", bg="#075985", fg="white", font=("TkDefaultFont", 18, "bold")).pack(anchor=tk.W)
        tk.Label(header, text="Selecciona un capítulo para verlo por separado", bg="#075985", fg="#dff6ff").pack(anchor=tk.W)

        body = ttk.Frame(win, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        chapters = tk.Listbox(body, width=28, bg="#f8fbff", fg="#083344", selectbackground="#38bdf8", selectforeground="white", relief=tk.FLAT, highlightthickness=1, highlightbackground="#bae6fd", font=("TkDefaultFont", 10))
        chapters.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        for title, _heading, _content in sections:
            chapters.insert(tk.END, title)

        frame = ttk.Frame(body)
        frame.grid(row=0, column=1, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        txt = tk.Text(frame, wrap=tk.WORD, bg="#ffffff", fg="#17202a", font=("TkDefaultFont", 10), padx=18, pady=14, relief=tk.FLAT, highlightthickness=1, highlightbackground="#bae6fd")
        txt.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, command=txt.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        txt.configure(yscrollcommand=scroll.set)
        txt.tag_configure("heading", font=("TkDefaultFont", 17, "bold"), foreground="#075985", spacing3=12)
        txt.tag_configure("body", font=("TkDefaultFont", 10), foreground="#17202a", lmargin1=8, lmargin2=24, spacing1=2, spacing3=6)
        txt.tag_configure("param", font=("TkDefaultFont", 10, "bold"), foreground="#0f766e", lmargin1=8, lmargin2=24, spacing1=4, spacing3=2)
        txt.tag_configure("subheading", font=("TkDefaultFont", 11, "bold"), foreground="#0c4a6e", spacing1=8, spacing3=4)
        txt.tag_configure("bullet", foreground="#075985", lmargin1=24, lmargin2=42, spacing1=2, spacing3=2)
        txt.tag_configure("formula", font=("TkFixedFont", 10, "bold"), background="#e0f2fe", foreground="#083344", lmargin1=28, lmargin2=28, spacing1=6, spacing3=6)

        parameter_labels = {
            # Folding y fondo
            "Vmax", "Ajustar Vmax", "Folding point", "Base", "Pendiente",
            # Tipos de componente
            "Singlete", "Doblete", "Sextete",
            # Parámetros de componente
            "δ isomérico", "ΔEQ", "BHF", "Γ", "Profundidad", "Intensidades",
            "Γ (gamma1)", "Γ relativa líneas 2 y 5 (gamma2)", "Γ relativa líneas 3 y 4 (gamma3)",
            # P(BHF) globales
            "δ global", "ΔEQ global", "Γ HWHM",
            # P(BHF) / P(ΔEQ) malla y parámetros específicos
            "B mín", "B máx", "B mín / B máx", "Bins BHF",
            "Variable de distribución",
            "BHF fijo p/ P(ΔEQ)",
            "Mín distribución (en mm/s para P(ΔEQ))",
            "Máx distribución (en mm/s para P(ΔEQ))",
            "ΔEQ fijo/global",
            # Regularización
            "log10 α", "L-curve α", "Distribución fija",
            # Guardar
            "Guardar ajuste (.dat)", "Guardar sesión (.json)", "Guardar ajuste", "Guardar sesión",
            "Cargar sesión", "Opciones automáticas",
            # Restricciones
            "Activa", "Destino", "Origen", "Factor", "Suma",
            "Cómo actúan durante el ajuste", "Usos típicos", "Precauciones",
            # Diagnóstico
            "Residuo", "Errores frecuentes", "Buenas prácticas",
            # Perfiles de línea
            "Lorentziana (perfil por defecto)", "Voigt",
            # Interacciones hiperfinas
            "Interacción monopolar eléctrica", "Interacción cuadrupolar eléctrica",
            "Interacción magnética dipolar",
            "Reglas de selección e intensidades ideales",
            # Secciones de P(BHF)
            "Parámetros globales (comunes a todos los sextetes de la distribución)",
            "Parámetros de la malla", "Control de regularización",
            "Formas de P(BHF) disponibles",
            "Histograma (libre, no paramétrica)", "Gaussiana", "Binomial", "Fija",
            "Diferencias entre formas",
            # Flujo rápido
            "Controles principales",
            "Flujo rápido para un espectro conocido",
            "Flujo para espectro con P(BHF)",
            "Flujo para P(BHF) Gaussiana/Binomial con nítidos",
            # Otros
            "Recomendaciones", "Notas de uso",
        }

        def insert_help_content(content: str) -> None:
            for raw_line in content.strip().splitlines():
                line = raw_line.rstrip()
                stripped = line.strip()
                if not stripped:
                    txt.insert(tk.END, "\n", "body")
                elif stripped in parameter_labels:
                    txt.insert(tk.END, line + "\n", "param")
                elif stripped.endswith(":") and len(stripped) < 55 and not stripped.startswith("http"):
                    txt.insert(tk.END, line + "\n", "subheading")
                elif stripped.startswith(("•", "-")) or stripped.startswith(tuple(f"{n}." for n in range(1, 10))):
                    txt.insert(tk.END, line + "\n", "bullet")
                elif "residuo²" in stripped or "espectro =" in stripped or "||D² P||" in stripped:
                    txt.insert(tk.END, line + "\n", "formula")
                else:
                    # Resalta parámetros cuando aparecen al principio de una línea tipo "  Vmax ...".
                    matched = False
                    for label in sorted(parameter_labels, key=len, reverse=True):
                        pos = line.find(label)
                        if pos >= 0 and line[:pos].strip() == "":
                            txt.insert(tk.END, line[:pos], "body")
                            txt.insert(tk.END, label, "param")
                            txt.insert(tk.END, line[pos + len(label):] + "\n", "body")
                            matched = True
                            break
                    if not matched:
                        txt.insert(tk.END, line + "\n", "body")

        def show_section(i: int) -> None:
            _title, heading, content = sections[i]
            txt.configure(state=tk.NORMAL)
            txt.delete("1.0", tk.END)
            txt.insert(tk.END, heading + "\n", "heading")
            txt.insert(tk.END, "─" * min(76, len(heading) + 10) + "\n\n", "heading")
            insert_help_content(content)
            txt.configure(state=tk.DISABLED)
            txt.yview_moveto(0)

        def on_select(_event=None) -> None:
            sel = chapters.curselection()
            if sel:
                show_section(sel[0])

        chapters.bind("<<ListboxSelect>>", on_select)
        chapters.selection_set(0)
        show_section(0)

        buttons = ttk.Frame(win, padding=(10, 0, 10, 10))
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Acerca de", command=self.show_about, style="Small.TButton").pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(buttons, text="Cerrar", command=win.destroy, style="Accent.TButton").pack(side=tk.RIGHT)

    def show_about(self) -> None:
        self.show_logo_popup(title=f"Acerca de Mössbauer Fe-57 v2IA v{APP_VERSION}", scale=2.6, click_to_close=False)

    def check_for_updates(self, silent: bool = False) -> None:
        """Comprueba GitHub Releases y descarga la nueva versión si existe."""
        import os
        import threading
        import webbrowser
        from pathlib import Path as _Path

        try:
            from mossbauer_updater import choose_download, download_file, is_newer, latest_release
        except Exception as exc:
            if not silent:
                messagebox.showerror("Actualizaciones", f"No se pudo cargar el actualizador: {exc}")
            return

        current_version = APP_VERSION

        def downloads_dir() -> _Path:
            for name in ("Descargas", "Downloads"):
                p = _Path.home() / name
                if p.exists():
                    return p
            return _Path.home()

        def download_in_background(url: str, filename: str) -> None:
            def worker_download() -> None:
                try:
                    path = download_file(url, downloads_dir(), filename)
                except Exception as exc:
                    self.after(0, lambda: messagebox.showerror("Actualizaciones", f"No se pudo descargar la actualización:\n{exc}"))
                    return
                self.after(0, lambda: messagebox.showinfo(
                    "Actualización descargada",
                    f"Descargado en:\n{path}\n\nCierra el programa y usa ese fichero para instalar/ejecutar la nueva versión.",
                ))
            threading.Thread(target=worker_download, daemon=True).start()

        def worker() -> None:
            try:
                release = latest_release()
                newer = is_newer(release.tag, current_version)
            except Exception as exc:
                if not silent:
                    self.after(0, lambda: messagebox.showerror("Actualizaciones", f"No se pudo comprobar GitHub Releases:\n{exc}"))
                return

            def finish() -> None:
                if not newer:
                    if not silent:
                        messagebox.showinfo("Actualizaciones", f"Ya tienes la última versión ({current_version}).")
                    return
                body = (release.body or "").strip()
                if len(body) > 900:
                    body = body[:900] + "…"
                msg = (
                    f"Hay una versión nueva disponible.\n\n"
                    f"Versión actual: {current_version}\n"
                    f"Nueva versión: {release.tag}\n\n"
                    f"{body}\n\n"
                    "¿Quieres descargarla ahora?"
                )
                if messagebox.askyesno("Actualización disponible", msg):
                    url, filename = choose_download(release, prefer_exe=(os.name == "nt"))
                    download_in_background(url, filename)
                else:
                    if messagebox.askyesno("Actualizaciones", "¿Abrir la página de releases en el navegador?"):
                        webbrowser.open(release.html_url)

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def show_changelog(self) -> None:
        if CHANGELOG_PATH.exists():
            text = CHANGELOG_PATH.read_text(encoding="utf-8", errors="replace")
        elif README_PATH.exists():
            text = README_PATH.read_text(encoding="utf-8", errors="replace")
        else:
            text = "Changelog no disponible."
        self.show_text_window("Changelog", text)

    def _create_logo(self, parent: tk.Widget, scale: float = 1.0) -> tk.Canvas:
        """Logo vectorial: sextete Mössbauer sobre átomo/campo magnético."""
        s = scale
        canvas = tk.Canvas(parent, width=int(118 * s), height=int(82 * s), bg="#075985", highlightthickness=0, bd=0)
        def xy(*vals: float) -> tuple[int, ...]:
            return tuple(int(v * s) for v in vals)
        canvas.create_oval(*xy(10, 8, 108, 66), outline="#7dd3fc", width=max(1, int(2 * s)))
        canvas.create_oval(*xy(31, 18, 87, 56), outline="#bae6fd", width=max(1, int(1 * s)))
        canvas.create_line(*xy(18, 37, 100, 37), fill="#e0f2fe", width=max(1, int(1 * s)))
        canvas.create_line(*xy(59, 10, 59, 65), fill="#e0f2fe", width=max(1, int(1 * s)))
        for x, h in zip((22, 37, 51, 67, 81, 96), (30, 22, 15, 15, 22, 30)):
            canvas.create_line(*xy(x, 59, x, 59 - h), fill="#facc15", width=max(2, int(4 * s)), capstyle=tk.ROUND)
            canvas.create_oval(*xy(x - 3, 59 - h - 3, x + 3, 59 - h + 3), fill="#fef08a", outline="")
        canvas.create_oval(*xy(49, 27, 69, 47), fill="#38bdf8", outline="#e0f2fe", width=max(1, int(2 * s)))
        canvas.create_text(*xy(59, 37), text="Fe", fill="#083344", font=("TkDefaultFont", max(8, int(8 * s)), "bold"))
        canvas.create_text(*xy(59, 75), text="sextete", fill="#dff6ff", font=("TkDefaultFont", max(8, int(8 * s))))
        return canvas

    def _refresh_distribution_tab_visibility(self, update: bool = True) -> None:
        if not hasattr(self, "notebook") or not hasattr(self, "dist_tab"):
            return
        if self.fit_mode_var.get() == "bhf_distribution":
            try:
                self.notebook.add(self.dist_tab, text="Distribución BHF")
            except tk.TclError:
                pass
            self.notebook.select(self.dist_tab)
        else:
            try:
                if self.notebook.select() == str(self.dist_tab) and self.notebook.tabs():
                    for tab_id in self.notebook.tabs():
                        if tab_id != str(self.dist_tab):
                            self.notebook.select(tab_id)
                            break
                self.notebook.hide(self.dist_tab)
            except tk.TclError:
                pass
        if update:
            self.update_plot()

    def set_fit_mode_from_menu(self) -> None:
        self._refresh_distribution_tab_visibility(update=True)

    def on_line_profile_change(self) -> None:
        global LINE_PROFILE_KIND, VOIGT_SIGMA
        LINE_PROFILE_KIND = self.line_profile_var.get()
        VOIGT_SIGMA = self.vars.get("voigt_sigma", tk.DoubleVar(value=0.05)).get()
        self.update_plot()

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
        self.open_web_download_dialog(kind="calibraciones")

    def open_web_download_dialog(self, default_url: str = "", kind: str = "mossbauer") -> None:
        """Ventana sencilla para listar/descargar datos de una web con usuario y contraseña."""
        try:
            import requests
        except Exception as exc:
            messagebox.showerror("Web", f"No se pudo importar requests: {exc}")
            return

        cred_path = Path.home() / ".config" / "mossbauer_fe33_gui" / "credentials.json"
        saved_user = ""
        saved_pass = ""
        saved_urls: dict[str, str] = {}
        if cred_path.exists():
            try:
                saved = json.loads(cred_path.read_text(encoding="utf-8"))
                saved_user = saved.get("username", "")
                saved_pass = saved.get("password", "")
                saved_urls = saved.get("urls", {})
            except Exception:
                pass
        # Usar la URL guardada para este tipo si existe, si no la por defecto.
        effective_url = saved_urls.get(kind, default_url)

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
        url_var = tk.StringVar(value=effective_url)
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
            text="Recordar credenciales y URL en este ordenador (fichero local, no cifrado)",
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
                    # Leer las URLs ya guardadas para no perder las de otros tipos.
                    existing_urls: dict[str, str] = {}
                    if cred_path.exists():
                        try:
                            existing = json.loads(cred_path.read_text(encoding="utf-8"))
                            existing_urls = existing.get("urls", {})
                        except Exception:
                            pass
                    # Guardar la URL actual para este tipo (mossbauer o calibraciones).
                    current_url = url_var.get().strip()
                    if current_url:
                        existing_urls[kind] = current_url
                    cred_path.parent.mkdir(parents=True, exist_ok=True)
                    cred_path.write_text(
                        json.dumps({"username": user_var.get().strip(), "password": pass_var.get(), "urls": existing_urls}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    os.chmod(cred_path, 0o600)
                    debug(f"Credenciales y URLs guardadas en {cred_path} (texto local no cifrado).")
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

    def open_web_upload_analysis_dialog(self) -> None:
        """Sube a la web el JSON de la sesión actual en la sección de análisis."""
        try:
            import requests
        except Exception as exc:
            messagebox.showerror("Web", f"No se pudo importar requests: {exc}")
            return

        cred_path = CONFIG_DIR / "credentials.json"
        saved_user = ""
        saved_pass = ""
        saved_urls: dict[str, str] = {}
        if cred_path.exists():
            try:
                saved = json.loads(cred_path.read_text(encoding="utf-8"))
                saved_user = saved.get("username", "")
                saved_pass = saved.get("password", "")
                saved_urls = saved.get("urls", {})
            except Exception:
                pass

        default_measure_id = "1357"
        if self.file_path:
            ids = re.findall(r"(?:^|_)(\d{3,})(?=\D|$)", self.file_path.stem)
            if ids:
                default_measure_id = ids[-1]
        default_url = saved_urls.get("mossbauer_analysis", f"https://matelec.qfa.uam.es/lab/mossbauer/{default_measure_id}/")

        dialog = tk.Toplevel(self)
        dialog.title("Subir análisis JSON a web")
        dialog.geometry("760x520")
        dialog.transient(self)
        dialog.configure(background="#edf4fb")

        session = requests.Session()
        frm = ttk.Frame(dialog, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Página de la medida:").grid(row=0, column=0, sticky="w", pady=3)
        url_var = tk.StringVar(value=default_url)
        ttk.Entry(frm, textvariable=url_var).grid(row=0, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(frm, text="Usuario:").grid(row=1, column=0, sticky="w", pady=3)
        user_var = tk.StringVar(value=saved_user)
        ttk.Entry(frm, textvariable=user_var).grid(row=1, column=1, sticky="ew", pady=3)

        ttk.Label(frm, text="Contraseña:").grid(row=2, column=0, sticky="w", pady=3)
        pass_var = tk.StringVar(value=saved_pass)
        ttk.Entry(frm, textvariable=pass_var, show="•").grid(row=2, column=1, sticky="ew", pady=3)
        remember_var = tk.BooleanVar(value=bool(saved_user or saved_pass))
        ttk.Checkbutton(frm, text="Recordar credenciales y URL", variable=remember_var).grid(row=2, column=2, sticky="w", padx=(8, 0), pady=3)

        default_name = (self.file_path.stem if self.file_path else "mossbauer") + "_session.json"
        ttk.Label(frm, text="Nombre JSON:").grid(row=3, column=0, sticky="w", pady=3)
        name_var = tk.StringVar(value=default_name)
        ttk.Entry(frm, textvariable=name_var).grid(row=3, column=1, columnspan=2, sticky="ew", pady=3)

        list_url = saved_urls.get("mossbauer", "https://matelec.qfa.uam.es/lab/mossbauer/")
        list_url_var = tk.StringVar(value=list_url)
        ttk.Label(frm, text="Lista para buscar:").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Entry(frm, textvariable=list_url_var).grid(row=4, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(frm, text="Nota:").grid(row=5, column=0, sticky="nw", pady=3)
        note_text = tk.Text(frm, height=3, wrap=tk.WORD, background="#ffffff", foreground="#17202a", font=("TkDefaultFont", 9))
        note_text.grid(row=5, column=1, columnspan=2, sticky="ew", pady=3)

        status_var = tk.StringVar(value="Primero busca la entrada cuyo fichero de datos tenga el mismo nombre; después pulsa Subir.")
        ttk.Label(frm, textvariable=status_var, style="Subtitle.TLabel", wraplength=710).grid(row=6, column=0, columnspan=3, sticky="w", pady=(4, 8))

        debug_box = tk.Text(frm, height=16, wrap=tk.WORD, background="#111827", foreground="#d1fae5", insertbackground="#d1fae5", font=("TkFixedFont", 9))
        debug_box.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(6, 0))
        frm.rowconfigure(7, weight=1)

        def debug(msg: str) -> None:
            debug_box.insert(tk.END, msg.rstrip() + "\n")
            debug_box.see(tk.END)
            dialog.update_idletasks()

        def save_credentials_if_requested() -> None:
            try:
                if remember_var.get():
                    existing_urls: dict[str, str] = {}
                    if cred_path.exists():
                        try:
                            existing_urls = json.loads(cred_path.read_text(encoding="utf-8")).get("urls", {})
                        except Exception:
                            pass
                    current_url = url_var.get().strip()
                    if current_url:
                        existing_urls["mossbauer_analysis"] = current_url
                    current_list_url = list_url_var.get().strip()
                    if current_list_url:
                        existing_urls["mossbauer"] = current_list_url
                    cred_path.parent.mkdir(parents=True, exist_ok=True)
                    cred_path.write_text(
                        json.dumps({"username": user_var.get().strip(), "password": pass_var.get(), "urls": existing_urls}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    os.chmod(cred_path, 0o600)
                    debug(f"Credenciales y URL guardadas en {cred_path}.")
            except Exception as exc:
                debug(f"No se pudieron guardar credenciales: {exc}")

        def parse_inputs(form_html: str) -> dict[str, str]:
            data: dict[str, str] = {}
            for input_tag in re.findall(r"<input\b[^>]*>", form_html, flags=re.S | re.I):
                type_m = re.search(r"\btype=[\"']([^\"']+)[\"']", input_tag, flags=re.I)
                typ = (type_m.group(1).lower() if type_m else "text")
                if typ in ("file", "submit", "button", "image", "reset"):
                    continue
                name_m = re.search(r"\bname=[\"']([^\"']+)[\"']", input_tag, flags=re.I)
                if not name_m:
                    continue
                value_m = re.search(r"\bvalue=[\"']([^\"']*)[\"']", input_tag, flags=re.I)
                data[unescape(name_m.group(1))] = unescape(value_m.group(1)) if value_m else ""
            for select in re.findall(r"<select\b.*?</select>", form_html, flags=re.S | re.I):
                name_m = re.search(r"<select\b[^>]*\bname=[\"']([^\"']+)[\"']", select, flags=re.S | re.I)
                if not name_m:
                    continue
                options = re.findall(r"<option\b[^>]*>", select, flags=re.S | re.I)
                chosen = next((o for o in options if re.search(r"\bselected\b", o, flags=re.I)), options[0] if options else "")
                value_m = re.search(r"\bvalue=[\"']([^\"']*)[\"']", chosen, flags=re.I)
                if value_m:
                    data[unescape(name_m.group(1))] = unescape(value_m.group(1))
            for textarea in re.findall(r"<textarea\b.*?</textarea>", form_html, flags=re.S | re.I):
                name_m = re.search(r"<textarea\b[^>]*\bname=[\"']([^\"']+)[\"']", textarea, flags=re.S | re.I)
                if not name_m:
                    continue
                value_m = re.search(r"<textarea\b[^>]*>(.*?)</textarea>", textarea, flags=re.S | re.I)
                data[unescape(name_m.group(1))] = unescape(value_m.group(1)) if value_m else ""
            return data

        def input_name(form_html: str, input_type: str, preferred: tuple[str, ...] = ()) -> str | None:
            candidates: list[str] = []
            for input_tag in re.findall(r"<input\b[^>]*>", form_html, flags=re.S | re.I):
                type_m = re.search(r"\btype=[\"']([^\"']+)[\"']", input_tag, flags=re.I)
                typ = type_m.group(1).lower() if type_m else "text"
                if typ == input_type:
                    name_m = re.search(r"\bname=[\"']([^\"']+)[\"']", input_tag, flags=re.I)
                    if name_m:
                        candidates.append(unescape(name_m.group(1)))
            for pref in preferred:
                for cand in candidates:
                    if cand.lower() == pref:
                        return cand
            return candidates[0] if candidates else None

        def get_url(url: str):
            debug(f"GET {url}")
            r = session.get(url, timeout=30, allow_redirects=True)
            debug(f"  -> status={r.status_code} final={r.url} bytes={len(r.content)}")
            return r

        def ensure_login(target_url: str) -> bool:
            save_credentials_if_requested()
            user = user_var.get().strip()
            password = pass_var.get()
            r = get_url(target_url)
            if not re.search(r"type=[\"']password[\"']", r.text, flags=re.I):
                debug("LOGIN: no aparece formulario de contraseña; se continúa con la sesión actual.")
                return True
            if not user and not password:
                debug("LOGIN: faltan usuario y contraseña.")
                return False
            forms = re.findall(r"<form\b.*?</form>", r.text, flags=re.S | re.I)
            login_form = next((form for form in forms if re.search(r"type=[\"']password[\"']", form, flags=re.I)), None)
            if login_form is None:
                return False
            action_m = re.search(r"<form\b[^>]*\baction=[\"']([^\"']*)[\"']", login_form, flags=re.S | re.I)
            post_url = urljoin(r.url, unescape(action_m.group(1))) if action_m else r.url
            method_m = re.search(r"<form\b[^>]*\bmethod=[\"']([^\"']*)[\"']", login_form, flags=re.S | re.I)
            method = method_m.group(1).lower() if method_m else "post"
            data = parse_inputs(login_form)
            user_name = input_name(login_form, "text", ("username", "user", "login", "email")) or input_name(login_form, "email", ("email", "username"))
            pass_name = input_name(login_form, "password", ("password", "passwd"))
            if user_name is None or pass_name is None:
                debug("LOGIN: no se pudieron detectar los campos usuario/contraseña.")
                return False
            data[user_name] = user
            data[pass_name] = password
            if "next" in data and not data["next"]:
                data["next"] = urlparse(target_url).path
            debug(f"LOGIN: enviando credenciales a {post_url}")
            headers = {"Referer": r.url}
            if method == "get":
                r2 = session.get(post_url, params=data, headers=headers, timeout=30, allow_redirects=True)
            else:
                r2 = session.post(post_url, data=data, headers=headers, timeout=30, allow_redirects=True)
            debug(f"LOGIN: respuesta status={r2.status_code} final={r2.url} bytes={len(r2.content)}")
            r3 = get_url(target_url)
            ok = not re.search(r"type=[\"']password[\"']", r3.text[:6000], flags=re.I)
            debug("LOGIN: correcto." if ok else "LOGIN: parece que seguimos en la página de acceso.")
            return ok

        def find_analysis_upload_form(html: str, base_url: str) -> tuple[str, dict[str, str], str, str] | None:
            forms = re.findall(r"<form\b.*?</form>", html, flags=re.S | re.I)
            scored: list[tuple[int, str, str]] = []
            for form in forms:
                file_name = input_name(form, "file")
                if not file_name:
                    continue
                action_m = re.search(r"<form\b[^>]*\baction=[\"']([^\"']*)[\"']", form, flags=re.S | re.I)
                action = urljoin(base_url, unescape(action_m.group(1))) if action_m else base_url
                hay = re.sub(r"<[^>]+>", " ", form).lower() + " " + action.lower()
                score = 0
                if "análisis" in hay or "analisis" in hay or "analysis" in hay:
                    score += 10
                if "json" in hay:
                    score += 2
                scored.append((score, action, form))
            if not scored:
                return None
            scored.sort(key=lambda item: item[0], reverse=True)
            _score, action, form = scored[0]
            file_name = input_name(form, "file")
            if file_name is None:
                return None
            return action, parse_inputs(form), file_name, form

        def note_field_names(form_html: str) -> list[str]:
            names: list[str] = []
            for tag_re in (r"<textarea\b[^>]*>", r"<input\b[^>]*>"):
                for tag in re.findall(tag_re, form_html, flags=re.S | re.I):
                    name_m = re.search(r"\bname=[\"']([^\"']+)[\"']", tag, flags=re.I)
                    if not name_m:
                        continue
                    name = unescape(name_m.group(1))
                    lname = name.lower()
                    if any(token in lname for token in ("note", "nota", "comment", "coment", "observ", "description", "descripcion", "descrip")):
                        names.append(name)
            return names

        def filename_from_response(response, fallback: str) -> str:
            cd = response.headers.get("content-disposition", "")
            m = re.search(r"filename\*=UTF-8''([^;]+)", cd, flags=re.I)
            if m:
                return Path(unquote(m.group(1))).name
            m = re.search(r'filename="?([^";]+)"?', cd, flags=re.I)
            if m:
                return Path(unescape(m.group(1))).name
            return fallback

        def find_measure_by_current_filename() -> None:
            if not self.file_path:
                status_var.set("No hay fichero de datos cargado; no se puede comparar el nombre.")
                return
            target_name = self.file_path.name.strip().lower()
            start_url = list_url_var.get().strip() or "https://matelec.qfa.uam.es/lab/mossbauer/"
            if not ensure_login(start_url):
                status_var.set("No se pudo iniciar sesión para buscar la entrada.")
                return

            status_var.set(f"Buscando en la web el fichero de datos: {self.file_path.name}")
            dialog.update_idletasks()
            visited: set[str] = set()
            queue: list[str] = [start_url]
            download_re = re.compile(r"/lab/download/mossbauer/(\d+)/datafile/?")
            found: dict[str, str] = {}
            max_pages = 80
            base_netloc = urlparse(start_url).netloc

            def clean_url(url: str) -> str:
                p = urlparse(url)
                return p._replace(fragment="").geturl()

            try:
                while queue and len(visited) < max_pages:
                    current = clean_url(queue.pop(0))
                    if current in visited:
                        continue
                    visited.add(current)
                    r = get_url(current)
                    r.raise_for_status()
                    text = r.text
                    for href in re.findall(r"href=[\"']([^\"']+)[\"']", text, flags=re.I):
                        href = unescape(href).strip()
                        if not href or href.startswith(("#", "mailto:", "javascript:")):
                            continue
                        full = clean_url(urljoin(r.url, href))
                        parsed = urlparse(full)
                        if parsed.netloc != base_netloc:
                            continue
                        m = download_re.search(parsed.path)
                        if m:
                            found[full] = m.group(1)
                        elif parsed.path.rstrip("/") == "/lab/mossbauer" and "page=" in parsed.query:
                            if full not in visited and full not in queue:
                                queue.append(full)
                    status_var.set(f"Revisadas {len(visited)} páginas; {len(found)} ficheros candidatos...")
                    dialog.update_idletasks()

                debug(f"BUSCAR: comparando {len(found)} ficheros descargables con {self.file_path.name}")
                for n, (file_url, item_id) in enumerate(found.items(), start=1):
                    status_var.set(f"Comprobando fichero {n}/{len(found)}...")
                    dialog.update_idletasks()
                    r = session.get(file_url, timeout=30, allow_redirects=True)
                    r.raise_for_status()
                    web_name = filename_from_response(r, Path(urlparse(r.url).path).name).strip()
                    debug(f"  id {item_id}: {web_name} <- {file_url}")
                    if web_name.lower() == target_name:
                        measure_url = urljoin(start_url, f"/lab/mossbauer/{item_id}/")
                        url_var.set(measure_url)
                        status_var.set(f"Encontrada entrada id {item_id} para {self.file_path.name}. Ya puedes pulsar Subir.")
                        debug(f"BUSCAR: coincidencia exacta -> {measure_url}")
                        return
                status_var.set(f"No se encontró en la web ningún dato llamado exactamente {self.file_path.name}.")
            except Exception as exc:
                status_var.set(f"Error buscando entrada: {type(exc).__name__}: {exc}")
                debug(f"BUSCAR EXCEPCIÓN: {type(exc).__name__}: {exc}")

        def upload() -> None:
            target_url = url_var.get().strip()
            upload_name = name_var.get().strip() or default_name
            if not upload_name.lower().endswith(".json"):
                upload_name += ".json"
            if not target_url:
                return
            try:
                note = note_text.get("1.0", tk.END).strip()
                session_data = self.session_payload()
                if note:
                    session_data["web_analysis_note"] = note
                payload = json.dumps(session_data, ensure_ascii=False, indent=2).encode("utf-8")
                if not ensure_login(target_url):
                    status_var.set("No se pudo iniciar sesión. Revisa usuario/contraseña y el panel debug.")
                    return
                page = get_url(target_url)
                page.raise_for_status()
                form_info = find_analysis_upload_form(page.text, page.url)
                if form_info is None:
                    status_var.set("No encontré un formulario con campo de fichero en la sección de análisis.")
                    debug("Busca en la página un formulario de subida en 'Análisis'. Si cambia el HTML habrá que ajustar el detector.")
                    return
                post_url, data, file_field, form_html = form_info
                if note:
                    note_fields = note_field_names(form_html)
                    if note_fields:
                        data[note_fields[0]] = note
                        debug(f"UPLOAD: nota enviada en campo {note_fields[0]}")
                    else:
                        debug("UPLOAD: no encontré campo de nota en el formulario; la nota va incluida dentro del JSON.")
                debug(f"UPLOAD: POST multipart {post_url} campo_fichero={file_field} campos={list(data.keys())}")
                files = {file_field: (upload_name, payload, "application/json")}
                r = session.post(post_url, data=data, files=files, headers={"Referer": page.url}, timeout=60, allow_redirects=True)
                debug(f"UPLOAD: respuesta status={r.status_code} final={r.url} bytes={len(r.content)}")
                try:
                    r.raise_for_status()
                except Exception:
                    status_var.set(f"Error HTTP al subir: {r.status_code}")
                    return
                if re.search(r"type=[\"']password[\"']", r.text[:6000], flags=re.I):
                    status_var.set("La web devolvió la página de login; no se subió el análisis.")
                    return
                status_var.set(f"Análisis subido como {upload_name}.")
                messagebox.showinfo("Web", f"Análisis JSON subido a:\n{target_url}")
            except Exception as exc:
                status_var.set(f"Error subiendo análisis: {type(exc).__name__}: {exc}")
                debug(f"EXCEPCIÓN: {type(exc).__name__}: {exc}")

        buttons = ttk.Frame(frm)
        buttons.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        buttons.columnconfigure(2, weight=1)
        ttk.Button(buttons, text="Buscar entrada por nombre", command=find_measure_by_current_filename).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(buttons, text="Subir", command=upload, style="Accent.TButton").grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(buttons, text="Cerrar", command=dialog.destroy).grid(row=0, column=2, sticky="ew", padx=(5, 0))

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

    def _smooth_1d(self, values: np.ndarray, window: int) -> np.ndarray:
        window = int(max(3, window))
        if window % 2 == 0:
            window += 1
        if values.size < window:
            return values.astype(float).copy()
        kernel = np.ones(window, dtype=float) / float(window)
        pad = window // 2
        padded = np.pad(values.astype(float), pad, mode="edge")
        return np.convolve(padded, kernel, mode="valid")

    def detect_absorption_minima(self) -> tuple[list[dict[str, float]], float, float]:
        """Detecta mínimos de transmisión como máximos de absorción.

        Devuelve una lista de picos con posición, profundidad y anchura FWHM
        aproximada, más baseline y slope estimados. Es heurístico: sirve para
        proponer valores iniciales, no para sustituir el ajuste.
        """
        if self.velocity is None or self.y_data is None or self.y_data.size < 7:
            return [], 1.0, 0.0
        v = self.velocity
        y = self.y_data
        high = y >= np.percentile(y, 70)
        if int(np.sum(high)) >= 4:
            slope, baseline0 = np.polyfit(v[high], y[high], 1)
        else:
            baseline0 = float(np.percentile(y, 90)); slope = 0.0
        baseline_line = baseline0 + slope * v
        absorption = np.maximum(baseline_line - y, 0.0)
        smooth = self._smooth_1d(absorption, max(5, absorption.size // 80))
        max_abs = float(np.nanmax(smooth)) if smooth.size else 0.0
        if max_abs <= 0:
            return [], float(baseline0), float(slope)
        diff_noise = np.diff(smooth)
        noise = 1.4826 * float(np.median(np.abs(diff_noise - np.median(diff_noise)))) if diff_noise.size else 0.0
        threshold = max(0.10 * max_abs, 4.0 * noise, 5e-4)
        idxs = [i for i in range(1, smooth.size - 1) if smooth[i] >= smooth[i - 1] and smooth[i] > smooth[i + 1] and smooth[i] >= threshold]

        peaks: list[dict[str, float]] = []
        min_distance = max(0.12, 2.0 * abs(v[1] - v[0]))
        for i in idxs:
            half = 0.5 * smooth[i]
            left = i
            while left > 0 and smooth[left] > half:
                left -= 1
            right = i
            while right < smooth.size - 1 and smooth[right] > half:
                right += 1
            width = abs(float(v[right] - v[left])) if right > left else max(0.12, 2.0 * abs(v[1] - v[0]))
            peaks.append({"i": float(i), "pos": float(v[i]), "depth": float(absorption[i]), "smooth_depth": float(smooth[i]), "width": width})

        # Quitar duplicados muy cercanos quedándonos con el más profundo.
        selected: list[dict[str, float]] = []
        for peak in sorted(peaks, key=lambda p: p["smooth_depth"], reverse=True):
            if all(abs(peak["pos"] - q["pos"]) >= min_distance for q in selected):
                selected.append(peak)
        selected = sorted(selected[:12], key=lambda p: p["pos"])
        return selected, float(baseline0), float(slope)

    def _best_sextet_from_peaks(self, peaks: list[dict[str, float]]) -> tuple[list[dict[str, float]], float, float, float, float] | None:
        if len(peaks) < 5:
            return None
        from itertools import combinations
        candidates = sorted(peaks, key=lambda p: p["smooth_depth"], reverse=True)[:10]
        best = None
        for subset in combinations(candidates, 6) if len(candidates) >= 6 else [tuple(candidates[:5])]:
            sub = sorted(subset, key=lambda p: p["pos"])
            pos = np.array([p["pos"] for p in sub], dtype=float)
            if len(sub) == 6:
                ref = LINE_POS_33T
            else:
                # Caso de una línea débil no detectada: se prueba quitando una línea teórica.
                local_best = None
                for missing in range(6):
                    ref5 = np.delete(LINE_POS_33T, missing)
                    A5 = np.column_stack([np.ones(ref5.size), ref5])
                    delta5, scale5 = np.linalg.lstsq(A5, pos, rcond=None)[0]
                    pred5 = delta5 + scale5 * ref5
                    rms5 = float(np.sqrt(np.mean((pos - pred5) ** 2)))
                    if local_best is None or rms5 < local_best[0]:
                        local_best = (rms5, delta5, scale5)
                assert local_best is not None
                rms, delta, scale = local_best
                bhf = scale * BHF_DEFAULT_T
                score = rms
                if 10.0 <= bhf <= 60.0 and (best is None or score < best[0]):
                    widths = [p["width"] for p in sub]
                    depths = [p["depth"] for p in sub]
                    best = (score, list(sub), float(delta), float(bhf), float(np.median(widths)), float(np.median(depths)))
                continue
            A = np.column_stack([np.ones(ref.size), ref])
            delta, scale = np.linalg.lstsq(A, pos, rcond=None)[0]
            pred = delta + scale * ref
            rms = float(np.sqrt(np.mean((pos - pred) ** 2)))
            bhf = scale * BHF_DEFAULT_T
            if not (10.0 <= bhf <= 60.0):
                continue
            score = rms
            if best is None or score < best[0]:
                weights = np.array([1.0, 2/3, 1/3, 1/3, 2/3, 1.0], dtype=float)
                depths = np.array([p["depth"] for p in sub], dtype=float)
                depth_est = float(np.median(depths / weights))
                best = (score, list(sub), float(delta), float(bhf), float(np.median([p["width"] for p in sub])), depth_est)
        if best is None:
            return None
        score, sub, delta, bhf, width, depth = best
        if score > max(0.45, 0.10 * max(1.0, abs(bhf / BHF_DEFAULT_T))):
            return None
        return sub, delta, bhf, width, depth

    def auto_guess_from_minima(self, fit_after: bool = False) -> None:
        if self.velocity is None or self.y_data is None:
            return
        peaks, baseline, slope = self.detect_absorption_minima()
        if not peaks:
            messagebox.showinfo("Auto mínimos", "No se detectaron mínimos claros en el espectro.")
            return

        self.fit_mode_var.set("discrete")
        self.set_fit_mode_from_menu()
        params: dict[str, float] = {"baseline": baseline, "slope": float(np.clip(slope, -1e-4, 1e-4))}
        for idx in (1, 2, 3):
            if idx > 1:
                self.sextet_enabled[idx].set(False)
            p = f"s{idx}_"
            params.update({p + "delta": 0.0, p + "quad": 0.0, p + "bhf": BHF_DEFAULT_T, p + "gamma1": 0.20, p + "gamma2": 1.0, p + "gamma3": 1.0, p + "depth": 0.005, p + "int1": 1.0, p + "int2": 1.0, p + "int3": 1.0})

        components: list[tuple[int, str, list[dict[str, float]]]] = []
        used_ids: set[int] = set()
        sext = self._best_sextet_from_peaks(peaks)
        if sext is not None:
            sub, delta, bhf, width, depth = sext
            if len(sub) >= 5 and abs(sub[-1]["pos"] - sub[0]["pos"]) > 3.0:
                components.append((1, "Sextete", sub))
                p = "s1_"
                params[p + "delta"] = float(np.clip(delta, -2.5, 2.5))
                params[p + "bhf"] = float(np.clip(bhf, 20.0, 50.0))
                params[p + "quad"] = 0.0
                params[p + "gamma1"] = float(np.clip(width / 2.0, 0.04, 1.0))
                params[p + "depth"] = float(np.clip(depth, 0.002, 0.25))
                used_ids.update(int(p["i"]) for p in sub)

        remaining = [p for p in sorted(peaks, key=lambda q: q["smooth_depth"], reverse=True) if int(p["i"]) not in used_ids]
        next_idx = 2 if components else 1
        while next_idx <= 3 and remaining:
            if len(remaining) >= 2:
                pair = sorted(remaining[:2], key=lambda p: p["pos"])
                sep = abs(pair[1]["pos"] - pair[0]["pos"])
                if 0.18 <= sep <= 4.0:
                    kind = "Doblete"
                    group = pair
                    remaining = [p for p in remaining if p not in pair]
                else:
                    kind = "Singlete"
                    group = [remaining.pop(0)]
            else:
                kind = "Singlete"
                group = [remaining.pop(0)]
            components.append((next_idx, kind, group))
            pfx = f"s{next_idx}_"
            if next_idx > 1:
                self.sextet_enabled[next_idx].set(True)
            if kind == "Doblete":
                g = sorted(group, key=lambda p: p["pos"])
                params[pfx + "delta"] = float(np.mean([g[0]["pos"], g[1]["pos"]]))
                params[pfx + "quad"] = float(abs(g[1]["pos"] - g[0]["pos"]))
                params[pfx + "gamma1"] = float(np.clip(np.mean([x["width"] for x in g]) / 2.0, 0.04, 1.0))
                params[pfx + "gamma2"] = 1.0
                params[pfx + "depth"] = float(np.clip(np.mean([x["depth"] for x in g]), 0.002, 0.25))
                params[pfx + "int1"] = 1.0; params[pfx + "int2"] = 1.0
            else:
                g = group[0]
                params[pfx + "delta"] = float(g["pos"])
                params[pfx + "gamma1"] = float(np.clip(g["width"] / 2.0, 0.04, 1.0))
                params[pfx + "depth"] = float(np.clip(g["depth"], 0.002, 0.25))
                params[pfx + "int1"] = 1.0
            next_idx += 1

        if not components:
            # Si no se pudo clasificar, al menos proponer un singlete en el mínimo más profundo.
            g = max(peaks, key=lambda p: p["depth"])
            components.append((1, "Singlete", [g]))
            params["s1_delta"] = float(g["pos"])
            params["s1_gamma1"] = float(np.clip(g["width"] / 2.0, 0.04, 1.0))
            params["s1_depth"] = float(np.clip(g["depth"], 0.002, 0.25))

        for idx in (1, 2, 3):
            found = next((kind for i, kind, _g in components if i == idx), "Sextete")
            self.component_kind[idx].set(found)
            if idx > 1 and not any(i == idx for i, _kind, _g in components):
                self.sextet_enabled[idx].set(False)
        self.set_params(params)
        for idx, kind, _group in components:
            self.on_component_kind_change(idx)
        # Dejar libres los parámetros relevantes para que el ajuste posterior los refine.
        for key in self.active_param_keys():
            if key in self.fixed_vars:
                self.fixed_vars[key].set(False)
        self.update_plot()
        resumen = ", ".join(f"Comp. {idx}: {kind}" for idx, kind, _g in components)
        if fit_after:
            self.fit_current_data()
        else:
            messagebox.showinfo("Auto mínimos", f"Detectados {len(peaks)} mínimos. Propuesta inicial:\n{resumen}\n\nRevisa los parámetros y pulsa Ajuste, o usa Autoajustar desde mínimos.")

    def auto_fit_from_minima(self) -> None:
        self.auto_guess_from_minima(fit_after=True)

    def ai_spectrum_summary(self) -> dict[str, object]:
        peaks, baseline, slope = self.detect_absorption_minima()
        return {
            "file": self.file_path.name if self.file_path else None,
            "n_points": int(self.y_data.size) if self.y_data is not None else 0,
            "vmin": float(np.min(self.velocity)) if self.velocity is not None else None,
            "vmax": float(np.max(self.velocity)) if self.velocity is not None else None,
            "baseline_est": baseline,
            "slope_est": slope,
            "y_min": float(np.min(self.y_data)) if self.y_data is not None else None,
            "y_max": float(np.max(self.y_data)) if self.y_data is not None else None,
            "line_profile": self.line_profile_var.get(),
            "detected_minima": [
                {
                    "v_mm_s": round(p["pos"], 5),
                    "depth": round(p["depth"], 6),
                    "width_fwhm_mm_s": round(p["width"], 5),
                }
                for p in peaks
            ],
            "current_fit_mode": self.fit_mode_var.get(),
            "allowed_component_types": ["Singlete", "Doblete", "Sextete"],
            "allowed_distribution_variables": ["BHF", "ΔEQ"],
            "note": "Sugiere solo valores iniciales; el ajuste final lo hará scipy en la GUI.",
        }

    def ollama_request_json(self, prompt: str, model: str, base_url: str) -> dict[str, object]:
        base_url = base_url.rstrip("/")
        if not base_url:
            raise ValueError("Falta la URL de Ollama, por ejemplo http://localhost:11434")
        if not model:
            raise ValueError("Falta el modelo de Ollama, por ejemplo llama3.1, qwen2.5 o mistral")
        payload = {
            "model": model,
            "stream": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente experto en espectroscopía Mössbauer de 57Fe. "
                        "Debes proponer únicamente parámetros iniciales razonables para una GUI. "
                        "No inventes certeza física; si dudas, marca confidence baja. Responde solo JSON válido."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.1},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            base_url + "/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"No se pudo conectar con Ollama en {base_url}: {exc}") from exc
        outer = json.loads(raw)
        content = outer.get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Ollama respondió sin contenido útil")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", content, flags=re.S)
            if not m:
                raise
            return json.loads(m.group(0))

    def ollama_list_models(self, base_url: str) -> list[str]:
        base_url = base_url.rstrip("/")
        req = urllib.request.Request(base_url + "/api/tags", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"No se pudo consultar Ollama en {base_url}: {exc}") from exc
        data = json.loads(raw)
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]

    def build_ollama_prompt(self) -> str:
        summary = self.ai_spectrum_summary()
        return (
            "Analiza este resumen numérico de un espectro Mössbauer de 57Fe y sugiere cómo inicializar el ajuste.\n"
            "Elige entre ajuste discreto de hasta 3 componentes o distribución P(BHF)/P(ΔEQ) con componentes nítidos.\n"
            "Devuelve JSON con este esquema exacto aproximado:\n"
            "{\n"
            "  \"fit_mode\": \"discrete\" | \"distribution\",\n"
            "  \"distribution\": {\"variable\": \"BHF\"|\"ΔEQ\", \"shape\": \"Histograma\"|\"Gaussiana\", \"min\": 0, \"max\": 50, \"nbins\": 50, \"log10_alpha\": -2, \"delta\": 0, \"quad\": 0, \"gamma\": 0.18, \"use_sharp_components\": false},\n"
            "  \"components\": [\n"
            "    {\"idx\":1, \"kind\":\"Singlete\"|\"Doblete\"|\"Sextete\", \"delta\":0, \"quad\":0, \"bhf\":33, \"gamma1\":0.2, \"gamma2\":1, \"gamma3\":1, \"depth\":0.02, \"int1\":1, \"int2\":1, \"int3\":1, \"enabled\":true}\n"
            "  ],\n"
            "  \"fit_after_apply\": false,\n"
            "  \"confidence\": 0.0,\n"
            "  \"rationale\": \"explicación breve en español\"\n"
            "}\n"
            "Resumen del espectro:\n"
            + json.dumps(summary, ensure_ascii=False, indent=2)
        )

    def apply_ai_suggestion(self, suggestion: dict[str, object]) -> None:
        mode = str(suggestion.get("fit_mode", "discrete")).lower()
        distribution = suggestion.get("distribution", {}) if isinstance(suggestion.get("distribution", {}), dict) else {}
        components = suggestion.get("components", []) if isinstance(suggestion.get("components", []), list) else []

        params: dict[str, float] = {}
        if mode.startswith("dist") or mode in {"pbhf", "p(bhf)", "distribution"}:
            self.fit_mode_var.set("bhf_distribution")
            var = str(distribution.get("variable", self.dist_variable_var.get()))
            self.dist_variable_var.set("ΔEQ" if "Δ" in var or "eq" in var.lower() else "BHF")
            shape = str(distribution.get("shape", self.dist_shape_var.get()))
            if shape in ("Histograma", "Gaussiana", "Binomial", "Fija"):
                self.dist_shape_var.set(shape)
            mapping = {
                "dist_bmin": distribution.get("min"),
                "dist_bmax": distribution.get("max"),
                "dist_nbins": distribution.get("nbins"),
                "dist_log_alpha": distribution.get("log10_alpha"),
                "dist_delta": distribution.get("delta"),
                "dist_quad": distribution.get("quad"),
                "dist_gamma": distribution.get("gamma"),
                "dist_fixed_bhf": distribution.get("fixed_bhf"),
            }
            for key, value in mapping.items():
                if value is not None and key in self.vars:
                    params[key] = float(value)
            self.dist_use_sharp_var.set(bool(distribution.get("use_sharp_components", False)))
        else:
            self.fit_mode_var.set("discrete")

        active_idxs: set[int] = set()
        for comp in components[:3]:
            if not isinstance(comp, dict):
                continue
            idx = int(comp.get("idx", len(active_idxs) + 1))
            if idx not in (1, 2, 3):
                continue
            active_idxs.add(idx)
            kind = str(comp.get("kind", "Sextete"))
            if kind not in ("Singlete", "Doblete", "Sextete"):
                kind = "Sextete"
            self.component_kind[idx].set(kind)
            if idx > 1:
                self.sextet_enabled[idx].set(bool(comp.get("enabled", True)))
            p = f"s{idx}_"
            for name in SEXTET_PARAM_NAMES:
                if name in comp and p + name in self.vars:
                    params[p + name] = float(comp[name])
            if "gamma" in comp and p + "gamma1" in self.vars:
                params[p + "gamma1"] = float(comp["gamma"])
        for idx in (2, 3):
            if idx not in active_idxs and self.fit_mode_var.get() == "discrete":
                self.sextet_enabled[idx].set(False)
        self.set_params(params)
        self.set_fit_mode_from_menu()
        for idx in (1, 2, 3):
            self.on_component_kind_change(idx)
        self.update_plot()

    def show_ai_suggestion_dialog(self, suggestion: dict[str, object], prompt: str) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Sugerencia IA local Ollama")
        dialog.geometry("820x650")
        dialog.transient(self)
        frm = ttk.Frame(dialog, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        rationale = str(suggestion.get("rationale", ""))
        conf = suggestion.get("confidence", "?")
        ttk.Label(frm, text=f"Confianza: {conf}    {rationale}", style="Subtitle.TLabel", wraplength=780).pack(anchor=tk.W, pady=(0, 6))
        txt = tk.Text(frm, wrap=tk.WORD, background="#ffffff", foreground="#17202a", font=("TkFixedFont", 9))
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert("1.0", json.dumps(suggestion, ensure_ascii=False, indent=2))
        buttons = ttk.Frame(frm)
        buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(buttons, text="Ver prompt enviado", command=lambda: self.show_text_window("Prompt enviado a Ollama", prompt), style="Small.TButton").pack(side=tk.LEFT)
        ttk.Button(buttons, text="Cerrar", command=dialog.destroy, style="Small.TButton").pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Aplicar propuesta", command=lambda: (self.apply_ai_suggestion(suggestion), dialog.destroy()), style="Accent.TButton").pack(side=tk.RIGHT, padx=(0, 6))

    def open_ollama_ai_dialog(self) -> None:
        if self.velocity is None or self.y_data is None:
            messagebox.showinfo("IA local Ollama", "Carga primero un espectro.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("IA local Ollama: sugerir inicio")
        dialog.geometry("760x520")
        dialog.transient(self)
        frm = ttk.Frame(dialog, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)
        ttk.Label(frm, text="URL Ollama:").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(frm, textvariable=self.ai_ollama_url_var).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(frm, text="Modelo:").grid(row=1, column=0, sticky="w", pady=3)
        model_entry = ttk.Entry(frm, textvariable=self.ai_ollama_model_var)
        model_entry.grid(row=1, column=1, sticky="ew", pady=3)
        models_var = tk.StringVar(value="")
        model_box = ttk.Combobox(frm, textvariable=models_var, values=(), state="readonly")
        model_box.grid(row=2, column=1, sticky="ew", pady=3)
        status_var = tk.StringVar(value="Ollama debe estar arrancado localmente. Ejemplo: ollama serve")
        ttk.Label(frm, textvariable=status_var, style="Subtitle.TLabel", wraplength=700).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 8))
        prompt = self.build_ollama_prompt()
        txt = tk.Text(frm, height=14, wrap=tk.WORD, background="#ffffff", foreground="#17202a", font=("TkFixedFont", 9))
        txt.grid(row=4, column=0, columnspan=2, sticky="nsew")
        frm.rowconfigure(4, weight=1)
        txt.insert("1.0", prompt)

        def load_models() -> None:
            try:
                models = self.ollama_list_models(self.ai_ollama_url_var.get().strip())
            except Exception as exc:
                status_var.set(str(exc))
                return
            model_box.configure(values=models)
            if models:
                models_var.set(models[0])
                if not self.ai_ollama_model_var.get().strip():
                    self.ai_ollama_model_var.set(models[0])
            status_var.set(f"Modelos encontrados: {len(models)}")

        def choose_model(*_args) -> None:
            if models_var.get():
                self.ai_ollama_model_var.set(models_var.get())
        models_var.trace_add("write", choose_model)

        def ask_ai() -> None:
            prompt_text = txt.get("1.0", tk.END).strip()
            self.save_settings()
            status_var.set("Consultando Ollama...")
            dialog.update_idletasks()
            try:
                suggestion = self.ollama_request_json(prompt_text, self.ai_ollama_model_var.get().strip(), self.ai_ollama_url_var.get().strip())
            except Exception as exc:
                messagebox.showerror("IA local Ollama", str(exc))
                status_var.set("Error consultando Ollama")
                return
            dialog.destroy()
            self.show_ai_suggestion_dialog(suggestion, prompt_text)

        buttons = ttk.Frame(frm)
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Listar modelos", command=load_models, style="Small.TButton").pack(side=tk.LEFT)
        ttk.Button(buttons, text="Cancelar", command=dialog.destroy, style="Small.TButton").pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Pedir sugerencia", command=ask_ai, style="Accent.TButton").pack(side=tk.RIGHT, padx=(0, 6))

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

    def constraint_param_keys(self) -> list[str]:
        return [k for k in self.vars if k in GLOBAL_PARAM_NAMES or re.match(r"s[123]_", k)]

    def enabled_constraints(self) -> list[dict[str, object]]:
        return [c for c in self.constraints if c.get("enabled", True) and c.get("target") in self.vars and c.get("source") in self.vars]

    def constrained_target_keys(self) -> set[str]:
        return {str(c["target"]) for c in self.enabled_constraints()}

    def apply_constraints_to_values(self, values: dict[str, float]) -> dict[str, float]:
        """Aplica target = factor*source + offset sobre un diccionario de parámetros."""
        out = values.copy()
        for _ in range(6):  # permite cadenas cortas de dependencias
            changed = False
            for c in self.enabled_constraints():
                target = str(c["target"])
                source = str(c["source"])
                if source not in out:
                    out[source] = self.vars[source].get()
                old = out.get(target, self.vars[target].get())
                new = float(c.get("factor", 1.0)) * out[source] + float(c.get("offset", 0.0))
                lo, hi = self.bounds_for_key(target) if target.split("_", 1)[-1] in MODEL_PARAM_LABELS or target in GLOBAL_PARAM_NAMES else self.slider_specs[target][:2]
                new = max(lo, min(hi, new))
                out[target] = new
                changed = changed or abs(new - old) > 1e-12
            if not changed:
                break
        return out

    def apply_constraints_to_vars(self) -> None:
        if not self.constraints:
            return
        values = {k: v.get() for k, v in self.vars.items()}
        values = self.apply_constraints_to_values(values)
        self.updating_sliders = True
        for key in self.constrained_target_keys():
            if key in values and key in self.vars:
                self.vars[key].set(values[key])
                self.entry_vars[key].set(self._format_value(key, values[key]))
        self.updating_sliders = False

    def open_constraints_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Restricciones entre parámetros")
        dialog.geometry("920x520")
        dialog.transient(self)
        dialog.configure(background="#eaf4ff")

        frm = ttk.Frame(dialog, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text="Restricciones lineales: parámetro destino = factor × parámetro origen + suma", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(frm, text="El parámetro destino queda dependiente: no se ajusta directamente y se recalcula durante el ajuste.", style="Subtitle.TLabel").pack(anchor=tk.W, pady=(0, 8))

        cols = ("enabled", "target", "source", "factor", "offset")
        tree = ttk.Treeview(frm, columns=cols, show="headings", height=9)
        for col, title, width in [("enabled", "Activa", 70), ("target", "Destino", 170), ("source", "Origen", 170), ("factor", "Factor", 110), ("offset", "Suma", 110)]:
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor=tk.CENTER)
        tree.pack(fill=tk.BOTH, expand=True, pady=8)

        def refresh() -> None:
            tree.delete(*tree.get_children())
            for i, c in enumerate(self.constraints):
                tree.insert("", tk.END, iid=str(i), values=("sí" if c.get("enabled", True) else "no", c.get("target", ""), c.get("source", ""), c.get("factor", 1.0), c.get("offset", 0.0)))

        edit = ttk.Frame(frm)
        edit.pack(fill=tk.X, pady=(4, 0))
        keys = self.constraint_param_keys()
        target_var = tk.StringVar(value=keys[0] if keys else "")
        source_var = tk.StringVar(value=keys[0] if keys else "")
        factor_var = tk.StringVar(value="1.0")
        offset_var = tk.StringVar(value="0.0")
        enabled_var = tk.BooleanVar(value=True)
        ttk.Label(edit, text="Destino").grid(row=0, column=0, sticky="w")
        ttk.Label(edit, text="Origen").grid(row=0, column=1, sticky="w")
        ttk.Label(edit, text="Factor").grid(row=0, column=2, sticky="w")
        ttk.Label(edit, text="Suma").grid(row=0, column=3, sticky="w")
        ttk.Combobox(edit, textvariable=target_var, values=keys, width=20, state="readonly").grid(row=1, column=0, padx=(0, 6), sticky="ew")
        ttk.Combobox(edit, textvariable=source_var, values=keys, width=20, state="readonly").grid(row=1, column=1, padx=6, sticky="ew")
        ttk.Entry(edit, textvariable=factor_var, width=12).grid(row=1, column=2, padx=6, sticky="ew")
        ttk.Entry(edit, textvariable=offset_var, width=12).grid(row=1, column=3, padx=6, sticky="ew")
        ttk.Checkbutton(edit, text="activa", variable=enabled_var).grid(row=1, column=4, padx=6)

        def selected_index() -> int | None:
            sel = tree.selection()
            return int(sel[0]) if sel else None

        def load_selected(_event=None) -> None:
            i = selected_index()
            if i is None:
                return
            c = self.constraints[i]
            target_var.set(str(c.get("target", "")))
            source_var.set(str(c.get("source", "")))
            factor_var.set(str(c.get("factor", 1.0)))
            offset_var.set(str(c.get("offset", 0.0)))
            enabled_var.set(bool(c.get("enabled", True)))

        def would_create_cycle(target: str, source: str, skip_index: int | None = None) -> bool:
            deps = {str(c.get("target")): str(c.get("source")) for n, c in enumerate(self.constraints) if n != skip_index and c.get("enabled", True)}
            deps[target] = source
            seen: set[str] = set()
            node = target
            while node in deps:
                node = deps[node]
                if node == target or node in seen:
                    return True
                seen.add(node)
            return False

        def make_constraint(skip_index: int | None = None) -> dict[str, object] | None:
            if not target_var.get() or not source_var.get() or target_var.get() == source_var.get():
                messagebox.showwarning("Restricción", "Elige destino y origen distintos.", parent=dialog)
                return None
            if would_create_cycle(target_var.get(), source_var.get(), skip_index):
                messagebox.showwarning("Restricción", "Esta restricción crea un ciclo. No se añadirá.", parent=dialog)
                return None
            if source_var.get() in self.fixed_vars and self.fixed_vars[source_var.get()].get():
                messagebox.showinfo("Restricción", "Aviso: el parámetro origen está fijado; la restricción será constante salvo cambio manual.", parent=dialog)
            if target_var.get() in self.fixed_vars and not self.fixed_vars[target_var.get()].get():
                self.fixed_vars[target_var.get()].set(True)
            return {"enabled": bool(enabled_var.get()), "target": target_var.get(), "source": source_var.get(), "factor": float(factor_var.get().replace(",", ".")), "offset": float(offset_var.get().replace(",", "."))}

        def add_constraint() -> None:
            try:
                c = make_constraint()
            except ValueError:
                messagebox.showwarning("Restricción", "Factor y suma deben ser numéricos.", parent=dialog); return
            if c is not None:
                self.constraints.append(c); refresh(); self.apply_constraints_to_vars(); self.update_plot()

        def update_constraint() -> None:
            i = selected_index()
            if i is None:
                return
            try:
                c = make_constraint(i)
            except ValueError:
                messagebox.showwarning("Restricción", "Factor y suma deben ser numéricos.", parent=dialog); return
            if c is not None:
                self.constraints[i] = c; refresh(); self.apply_constraints_to_vars(); self.update_plot()

        def delete_constraint() -> None:
            i = selected_index()
            if i is not None:
                del self.constraints[i]; refresh(); self.update_plot()

        tree.bind("<<TreeviewSelect>>", load_selected)
        buttons = ttk.Frame(frm)
        buttons.pack(fill=tk.X, pady=8)
        ttk.Button(buttons, text="Añadir", command=add_constraint, style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(buttons, text="Actualizar seleccionada", command=update_constraint, style="Small.TButton").pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Borrar seleccionada", command=delete_constraint, style="Small.TButton").pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Cerrar", command=dialog.destroy, style="Small.TButton").pack(side=tk.RIGHT)
        refresh()

    def active_param_keys(self) -> list[str]:
        keys = GLOBAL_PARAM_NAMES.copy()
        for idx in (1, 2, 3):
            if self.sextet_enabled[idx].get():
                keys.extend(f"s{idx}_{name}" for name in self.component_param_names(idx))
        return keys

    def active_bhf_keys(self) -> list[str]:
        return [f"s{idx}_bhf" for idx in (1, 2, 3) if self.sextet_enabled[idx].get() and self.component_kind[idx].get() == "Sextete"]

    def build_components_from_vars(self) -> list[tuple[str, np.ndarray]]:
        if self.constraints and not self.updating_sliders:
            self.apply_constraints_to_vars()
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
        self.apply_constraints_to_vars()

    def on_slider(self, key: str) -> None:
        value = self.vars[key].get()
        self.entry_vars[key].set(self._format_value(key, value))
        if self.updating_sliders:
            return
        if key == "voigt_sigma":
            global VOIGT_SIGMA
            VOIGT_SIGMA = self.vars["voigt_sigma"].get()
        if key.startswith("dist_") or (self.fit_mode_var.get() == "bhf_distribution" and (key in {"baseline", "slope"} or (self.dist_use_sharp_var.get() and re.match(r"s[123]_", key)))):
            self.last_bhf_fit = None
        if key in {"center", "vmax"}:
            self.refold_data()
        self.apply_constraints_to_vars()
        self.update_plot()

    def current_model(self) -> np.ndarray | None:
        if self.fit_mode_var.get() == "bhf_distribution" and self.last_bhf_fit is not None:
            return self.last_bhf_fit.fitted_curve
        if self.velocity is None:
            return None
        self.apply_constraints_to_vars()
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
            "slope": (-0.0001, 0.0001),
            "delta": (-2.0, 3.0),
            "quad": (0.0, 4.0),
            "bhf": (0.0, 50.0),
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
        values = self.apply_constraints_to_values(values)
        v = np.linspace(-vmax, vmax, self.y_data.size)
        components: list[tuple[str, np.ndarray]] = []
        for idx in (1, 2, 3):
            if self.sextet_enabled[idx].get():
                p = f"s{idx}_"
                params = np.array([values.get(p + name, self.vars[p + name].get()) for name in SEXTET_PARAM_NAMES], dtype=float)
                components.append((self.component_kind[idx].get(), params))
        return total_model(v, values["baseline"], values["slope"], components)

    def fit_current_data(self) -> None:
        self.apply_constraints_to_vars()
        if self.fit_mode_var.get() == "bhf_distribution":
            self.fit_bhf_distribution_current()
            return
        if self.velocity is None or self.y_data is None:
            return
        y = self.y_data
        keys = self.active_param_keys()
        self.apply_constraints_to_vars()
        constrained_targets = self.constrained_target_keys()
        values0 = {key: self.vars[key].get() for key in keys}

        fit_velocity = self.fit_velocity_var.get()
        if fit_velocity and not all(self.fixed_vars[k].get() for k in self.active_bhf_keys()):
            messagebox.showwarning(
                "Ajuste de velocidad",
                "Para ajustar la velocidad con el patrón, fija el BHF de todos los sextetes activos.",
            )
            return

        free_keys = [key for key in keys if key not in constrained_targets and not self.fixed_vars.get(key, tk.BooleanVar(value=False)).get()]
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
            values = self.apply_constraints_to_values(values)
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

    def load_fixed_distribution_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Cargar distribución fija",
            filetypes=[("Datos", "*.dat *.txt *.csv"), ("Todos", "*")],
        )
        if filename:
            self.fixed_distribution_path = Path(filename)
            self.dist_shape_var.set("Fija")
            self.last_bhf_fit = None
            messagebox.showinfo("Distribución fija", f"Cargada:\n{self.fixed_distribution_path}\n\nFormato esperado: dos columnas: parámetro, peso")
            self.update_plot()

    def read_fixed_distribution_file(self) -> tuple[np.ndarray, np.ndarray]:
        if self.fixed_distribution_path is None:
            raise ValueError("No hay fichero de distribución fija cargado")
        data = np.loadtxt(self.fixed_distribution_path, comments="#", delimiter=None)
        data = np.asarray(data, dtype=float)
        if data.ndim == 1:
            data = data.reshape(-1, 2)
        if data.shape[1] < 2:
            raise ValueError("La distribución fija debe tener al menos dos columnas: parámetro y peso")
        return data[:, 0], data[:, 1]

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
            variable = "quad" if self.dist_variable_var.get() == "ΔEQ" else "bhf"
            scans = [fit_hyperfine_distribution_engine(
                self.velocity,
                self.y_data,
                variable=variable,
                delta=self.vars["dist_delta"].get(),
                quad=self.vars["dist_quad"].get(),
                bhf=self.vars["dist_fixed_bhf"].get(),
                gamma=self.vars["dist_gamma"].get(),
                pmin=bmin,
                pmax=bmax,
                nbins=nbins,
                alpha=float(a),
                fit_baseline=not self.fixed_vars["baseline"].get(),
                fit_slope=not self.fixed_vars["slope"].get(),
                baseline=self.vars["baseline"].get(),
                slope=self.vars["slope"].get(),
                sharp_components=sharp_components,
            ) for a in alphas]
        except Exception as exc:
            messagebox.showerror("L-curve α", str(exc))
            return
        L = second_difference_matrix(nbins)
        rows = np.array([(r.alpha, r.rms, float(np.linalg.norm(r.residuals)), float(np.linalg.norm(L @ r.weights))) for r in scans], dtype=float)
        suggested = self.suggest_alpha_from_lcurve_rows(rows)

        dialog = tk.Toplevel(self)
        dialog.title(f"L-curve α para {'P(ΔEQ)' if self.dist_variable_var.get() == 'ΔEQ' else 'P(BHF)'}")
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
            variable = "quad" if self.dist_variable_var.get() == "ΔEQ" else "bhf"
            if self.dist_shape_var.get() == "Gaussiana":
                return fit_gaussian_hyperfine_distribution_engine(
                    self.velocity,
                    self.y_data,
                    variable=variable,
                    delta=delta_value,
                    quad=self.vars["dist_quad"].get(),
                    bhf=self.vars["dist_fixed_bhf"].get(),
                    gamma=gamma_value,
                    pmin=bmin,
                    pmax=bmax,
                    nbins=nbins,
                    baseline=self.vars["baseline"].get(),
                    slope=self.vars["slope"].get(),
                    sharp_components=sharp_components,
                )
            if self.dist_shape_var.get() == "Binomial":
                return fit_binomial_hyperfine_distribution_engine(
                    self.velocity,
                    self.y_data,
                    variable=variable,
                    delta=delta_value,
                    quad=self.vars["dist_quad"].get(),
                    bhf=self.vars["dist_fixed_bhf"].get(),
                    gamma=gamma_value,
                    pmin=bmin,
                    pmax=bmax,
                    nbins=nbins,
                    baseline=self.vars["baseline"].get(),
                    slope=self.vars["slope"].get(),
                    sharp_components=sharp_components,
                )
            if self.dist_shape_var.get() == "Fija":
                centers, weights = self.read_fixed_distribution_file()
                return fit_fixed_hyperfine_distribution_engine(
                    self.velocity,
                    self.y_data,
                    centers,
                    weights,
                    variable=variable,
                    delta=delta_value,
                    quad=self.vars["dist_quad"].get(),
                    bhf=self.vars["dist_fixed_bhf"].get(),
                    gamma=gamma_value,
                    baseline=self.vars["baseline"].get(),
                    slope=self.vars["slope"].get(),
                    sharp_components=sharp_components,
                )
            return fit_hyperfine_distribution_engine(
                self.velocity,
                self.y_data,
                variable=variable,
                delta=delta_value,
                quad=self.vars["dist_quad"].get(),
                bhf=self.vars["dist_fixed_bhf"].get(),
                gamma=gamma_value,
                pmin=bmin,
                pmax=bmax,
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
        dist_label = "P(ΔEQ)" if self.dist_variable_var.get() == "ΔEQ" else "P(BHF)"
        ax.set_title(f"Espectro Mössbauer: modo distribución {dist_label}", color="#083344", pad=10, fontweight="bold")
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
                    ax_dist.set_xlabel("ΔEQ (mm/s)" if self.dist_variable_var.get() == "ΔEQ" else "BHF (T)")
                    ax_dist.set_ylabel(dist_label)
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
            f"Modo: distribución {'P(ΔEQ)' if self.dist_variable_var.get() == 'ΔEQ' else 'P(BHF)'} ({self.dist_shape_var.get()})",
            f"Folding point centro: {self.vars['center'].get():.5f}",
            f"Vmax = {self.vars['vmax'].get():.6g} mm/s",
            f"Base = {self.vars['baseline'].get():.6g}",
            f"Pendiente = {self.vars['slope'].get():.6g}",
            f"δ = {self.vars['dist_delta'].get():.6g}, ΔEQ fijo/global = {self.vars['dist_quad'].get():.6g}",
            f"BHF fijo p/ P(ΔEQ) = {self.vars['dist_fixed_bhf'].get():.6g} T, Γ = {self.vars['dist_gamma'].get():.6g}",
            f"Rango distribución = {self.vars['dist_bmin'].get():.4g}–{self.vars['dist_bmax'].get():.4g} {'mm/s' if self.dist_variable_var.get() == 'ΔEQ' else 'T'}",
            f"Bins = {int(round(self.vars['dist_nbins'].get()))}",
            f"α = {self.dist_alpha():.3g}  (log10 α = {self.vars['dist_log_alpha'].get():.3g})",
            f"Subespectros nítidos: {', '.join(map(str, self.last_bhf_sharp_indices or self.active_sharp_component_indices_for_bhf())) if self.dist_use_sharp_var.get() else 'no'}",
            f"RMS ajuste: {rms:.6g}",
        ]
        if self.last_bhf_fit is not None:
            peak = float(self.last_bhf_fit.bhf_centers[int(np.argmax(self.last_bhf_fit.weights))])
            area = float(np.trapezoid(self.last_bhf_fit.weights, self.last_bhf_fit.bhf_centers))
            dist_area, sharp_areas, dist_pct, sharp_pct = self.bhf_component_area_percentages()
            text.extend([
                f"Pico {'P(ΔEQ)' if self.dist_variable_var.get() == 'ΔEQ' else 'P(BHF)'}: {peak:.4g} {'mm/s' if self.dist_variable_var.get() == 'ΔEQ' else 'T'}",
                f"Área P amplitud: {area:.6g}",
                "",
                "Porcentaje de área espectral:",
                f"  Distribución {'P(ΔEQ)' if self.dist_variable_var.get() == 'ΔEQ' else 'P(BHF)'}: {dist_pct:.3f}%  área={dist_area:.6g}",
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
            f1, f2, f3 = 2.0 * g1, 2.0 * g2, 2.0 * g3
            text.extend([
                f"{self.component_kind[idx].get()} {idx}: BHF={self.vars[p+'bhf'].get():.6g} T, δ={self.vars[p+'delta'].get():.6g}, ΔEQ={self.vars[p+'quad'].get():.6g}",
                f"  Γ HWHM reales 1/2/3 = {g1:.4g} / {g2:.4g} / {g3:.4g}",
                f"  FWHM equiv. 1/2/3 = {f1:.4g} / {f2:.4g} / {f3:.4g}",
                f"  Γ rel 2/3 = {self.vars[p+'gamma2'].get():.4g} / {self.vars[p+'gamma3'].get():.4g}",
                f"  prof={self.vars[p+'depth'].get():.6g}, I reales={i1:.4g}, {i2_real:.4g}, {i3_real:.4g}",
            ])
        text.extend(["", "Fijados: " + (", ".join(fixed) if fixed else "ninguno")])
        cons = self.enabled_constraints()
        if cons:
            text.append("")
            text.append("Restricciones activas:")
            for c in cons:
                text.append(f"  {c['target']} = {float(c.get('factor', 1.0)):.6g} · {c['source']} + {float(c.get('offset', 0.0)):.6g}")
        self.info.delete("1.0", tk.END)
        self.info.insert(tk.END, "\n".join(text))

    def session_payload(self) -> dict:
        """Estado completo reproducible de la sesión actual."""
        info_text = self.info.get("1.0", tk.END).strip()
        model_state = {
            "vars": {k: float(v.get()) for k, v in self.vars.items()},
            "fixed": {k: bool(v.get()) for k, v in self.fixed_vars.items()},
            "sextet_enabled": {str(k): bool(v.get()) for k, v in self.sextet_enabled.items()},
            "component_kind": {str(k): v.get() for k, v in self.component_kind.items()},
            "fit_velocity": bool(self.fit_velocity_var.get()),
            "show_residual": bool(self.show_residual_var.get()),
            "show_legend": bool(self.show_legend_var.get()),
            "fit_mode": self.fit_mode_var.get(),
            "line_profile": self.line_profile_var.get(),
            "dist_variable": self.dist_variable_var.get(),
            "dist_shape": self.dist_shape_var.get(),
            "fixed_distribution_path": str(self.fixed_distribution_path) if self.fixed_distribution_path else None,
            "dist_use_sharp": bool(self.dist_use_sharp_var.get()),
            "dist_refine_global": bool(self.dist_refine_global_var.get()),
            "info_text": info_text,
            "constraints": self.constraints,
        }
        last_fit = {
            "free_keys": self.last_fit_free_keys,
            "covariance": self.last_fit_cov.tolist() if self.last_fit_cov is not None else None,
            "parameter_errors": self.last_fit_param_errors,
            "info_text": info_text,
        }
        return {
            "version": 1,
            "program": "mossbauer_fe33_gui_v2IA.py",
            "file_path": str(self.file_path) if self.file_path else None,
            "file_name": self.file_path.name if self.file_path else None,
            "counts": self.counts.tolist() if self.counts is not None else None,
            "state_and_parameters_text": info_text,
            "model_state": model_state,
            "last_fit": last_fit,
        }

    def apply_session_payload(self, data: dict) -> None:
        file_path = Path(data["file_path"]) if data.get("file_path") else None
        loaded_file = False
        if file_path and file_path.exists():
            self.load_ws5(file_path)
            loaded_file = True
        elif data.get("counts") is not None:
            self.file_path = file_path
            self.current_file_var.set(data.get("file_name") or (file_path.name if file_path else "Sesión sin fichero"))
            self.counts = np.array(data["counts"], dtype=float)
        else:
            raise ValueError("La sesión no contiene fichero accesible ni cuentas guardadas")

        state = data.get("model_state", {})
        self.updating_sliders = True
        for key, value in state.get("vars", {}).items():
            if key in self.vars:
                val = float(value)
                self.vars[key].set(val)
                self.entry_vars[key].set(self._format_value(key, val))
        for key, value in state.get("fixed", {}).items():
            if key in self.fixed_vars:
                self.fixed_vars[key].set(bool(value))
        for idx, value in state.get("sextet_enabled", {}).items():
            i = int(idx)
            if i in self.sextet_enabled:
                self.sextet_enabled[i].set(bool(value))
        for idx, value in state.get("component_kind", {}).items():
            i = int(idx)
            if i in self.component_kind and value in ("Sextete", "Doblete", "Singlete"):
                self.component_kind[i].set(value)
        self.fit_velocity_var.set(bool(state.get("fit_velocity", self.fit_velocity_var.get())))
        self.show_residual_var.set(bool(state.get("show_residual", self.show_residual_var.get())))
        self.show_legend_var.set(bool(state.get("show_legend", self.show_legend_var.get())))
        self.fit_mode_var.set(state.get("fit_mode", self.fit_mode_var.get()))
        self.line_profile_var.set(state.get("line_profile", self.line_profile_var.get()))
        self.on_line_profile_change()
        self.dist_variable_var.set(state.get("dist_variable", self.dist_variable_var.get()))
        self.dist_shape_var.set(state.get("dist_shape", self.dist_shape_var.get()))
        self.fixed_distribution_path = Path(state["fixed_distribution_path"]) if state.get("fixed_distribution_path") else None
        self.dist_use_sharp_var.set(bool(state.get("dist_use_sharp", self.dist_use_sharp_var.get())))
        self.dist_refine_global_var.set(bool(state.get("dist_refine_global", self.dist_refine_global_var.get())))
        self.constraints = list(state.get("constraints", data.get("constraints", self.constraints)))
        self.updating_sliders = False

        last_fit = data.get("last_fit", {})
        self.last_fit_free_keys = list(last_fit.get("free_keys", []))
        cov = last_fit.get("covariance")
        self.last_fit_cov = np.array(cov, dtype=float) if cov is not None else None
        self.last_fit_param_errors = {k: float(v) for k, v in last_fit.get("parameter_errors", {}).items()}

        self._refresh_distribution_tab_visibility(update=False)
        self.refold_data()
        self.update_plot()
        info_text = data.get("state_and_parameters_text") or state.get("info_text") or last_fit.get("info_text")
        if info_text:
            self.info.delete("1.0", tk.END)
            self.info.insert(tk.END, info_text)
        if not loaded_file and self.file_path:
            self.current_file_var.set(f"{self.file_path.name} (desde sesión)")

    def save_session_dialog(self) -> None:
        default_name = (self.file_path.stem if self.file_path else "mossbauer") + "_session.json"
        filename = filedialog.asksaveasfilename(
            title="Guardar sesión",
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("Sesión JSON", "*.json"), ("Todos", "*")],
        )
        if not filename:
            return
        path = Path(filename)
        path.write_text(json.dumps(self.session_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
        messagebox.showinfo("Sesión guardada", f"Sesión guardada en:\n{path}")

    def load_session_dialog(self) -> None:
        filename = filedialog.askopenfilename(
            title="Cargar sesión",
            filetypes=[("Sesión JSON", "*.json"), ("Todos", "*")],
        )
        if not filename:
            return
        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8"))
            self.apply_session_payload(data)
        except Exception as exc:
            messagebox.showerror("Error cargando sesión", str(exc))
            return
        messagebox.showinfo("Sesión cargada", f"Sesión cargada desde:\n{filename}")

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
