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
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path
import urllib.error
import urllib.request

import numpy as np
from scipy.optimize import least_squares, differential_evolution
from scipy.special import wofz

from mossbauer_i18n import available_languages, get_language, set_language, tr
from mossbauer_distribution import (
    fit_hyperfine_distribution as fit_hyperfine_distribution_engine,
    fit_gaussian_hyperfine_distribution as fit_gaussian_hyperfine_distribution_engine,
    fit_binomial_hyperfine_distribution as fit_binomial_hyperfine_distribution_engine,
    fit_fixed_hyperfine_distribution as fit_fixed_hyperfine_distribution_engine,
    fit_bhf_distribution as fit_bhf_distribution_engine,
    scan_alpha as scan_bhf_alpha_engine,
    second_difference_matrix,
    first_difference_matrix,
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
APP_VERSION = "2.1"
APP_AUTHOR = "Jorge Sánchez Marcos"
APP_DEPARTMENT = "Departamento de Química Física · UAM"
LINE_PROFILE_KIND = "Lorentziana"
VOIGT_SIGMA = 0.05
CONFIG_DIR = Path.home() / ".config" / "mossbauer_fe33_gui"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"
README_PATH = Path(__file__).with_name("README.md")
CHANGELOG_PATH = Path(__file__).with_name("CHANGELOG.md")


def load_credentials() -> dict:
    """Lee credentials.json (usuario, contraseña, token y rutas guardadas)."""
    if CREDENTIALS_PATH.exists():
        try:
            return json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_credentials(data: dict) -> None:
    """Guarda credentials.json (texto local sin cifrar, permisos restrictivos)."""
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(CREDENTIALS_PATH, 0o600)
    except Exception:
        pass


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
    "int3": "I (líneas 3 y 4)",
    "int2": "I23 (2 = líneas 2,5 / líneas 3,4)",
    "int1": "I13 (3 = líneas 1,6 / líneas 3,4)",
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
            weight_sum = 2.0 * (3.0 + 2.0 + 1.0)
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
        denom = sigma * np.sqrt(2.0)
        norm = sigma * np.sqrt(2.0 * np.pi)
        prof = np.real(wofz(((v - center) + 1j * gamma) / denom)) / norm
        # Normalización analítica al pico (v=v0), independiente del muestreo.
        peak = float(np.real(wofz(1j * gamma / denom))) / norm
        return prof / max(peak, 1e-12)
    return gamma * gamma / ((v - center) ** 2 + gamma * gamma)


def sextet_absorption(v: np.ndarray, delta: float, quad: float, bhf: float,
                      gamma1: float, gamma2: float, gamma3: float, depth: float,
                      int1: float, int2: float, int3: float,
                      *, treatment: str = "1st_order", beta: float = 0.0,
                      n_quad: int = 20) -> np.ndarray:
    """Absorción de un sextete Fe-57.

    Convención NORMOS: int3=I (intensidad base, líneas 3 y 4),
    int2=I23 (ratio líneas 2,5 / 3,4; estándar=2), int1=I13 (ratio líneas 1,6 / 3,4; estándar=3).
    gamma1 es la anchura de las líneas 1 y 6. gamma2 y gamma3 son relativas:
    gamma2=1 -> Γ2,5=Γ1,6; gamma3=1 -> Γ3,4=Γ1,6.

    ``treatment``: "1st_order" (histórico), "kundig_fixed" (β fijo, mejora 8b),
    "kundig_powder" (promedio policristal por Gauss-Legendre).
    """
    from core.hamiltonian import (
        kundig_sextet_positions, polycrystal_kundig_positions,
    )

    i3 = int3
    i2 = int3 * int2
    i1 = int3 * int1
    weights = np.array([i1, i2, i3, i3, i2, i1], dtype=float)
    g1 = gamma1
    g2 = gamma1 * gamma2
    g3 = gamma1 * gamma3
    gammas = np.array([g1, g2, g3, g3, g2, g1], dtype=float)

    if treatment == "kundig_fixed":
        positions = kundig_sextet_positions(bhf, delta, quad, beta)
        absorption = np.zeros_like(v, dtype=float)
        for pos, weight, gamma in zip(positions, weights, gammas):
            absorption += weight * lorentzian(v, pos, gamma)
        return depth * absorption

    if treatment == "kundig_powder":
        pos_grid, w_grid = polycrystal_kundig_positions(bhf, delta, quad, n_quad)
        absorption = np.zeros_like(v, dtype=float)
        for k in range(pos_grid.shape[0]):
            for j in range(6):
                absorption += w_grid[k] * weights[j] * lorentzian(v, pos_grid[k, j], gammas[j])
        return depth * absorption

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


def component_absorption(v: np.ndarray, kind: str, p: np.ndarray, *, extras: dict | None = None) -> np.ndarray:
    if kind == "Singlete":
        delta, _quad, _bhf, gamma1, _gamma2, _gamma3, depth, int1, _int2, _int3 = p
        return singlet_absorption(v, delta, gamma1, depth, int1)
    if kind == "Doblete":
        delta, quad, _bhf, gamma1, gamma2, _gamma3, depth, int1, int2, _int3 = p
        return doublet_absorption(v, delta, quad, gamma1, gamma2, depth, int1, int2)
    if extras:
        return sextet_absorption(
            v, *p,
            treatment=str(extras.get("treatment", "1st_order")),
            beta=float(extras.get("beta", 0.0)),
            n_quad=int(extras.get("n_quad", 20)),
        )
    return sextet_absorption(v, *p)


def total_model(v: np.ndarray, baseline: float, slope: float, components) -> np.ndarray:
    """``components`` es lista de ``(kind, params)`` o ``(kind, params, extras)``."""
    y = baseline + slope * v
    for comp in components:
        if isinstance(comp, tuple):
            if len(comp) == 3:
                kind, p, extras = comp
                y -= component_absorption(v, kind, p, extras=extras)
            else:
                kind, p = comp
                y -= component_absorption(v, kind, p)
        else:
            y -= sextet_absorption(v, *comp)
    return y


def _log_warning(context: str, exc: BaseException) -> None:
    """Anota en stderr un fallo no critico sin interrumpir la GUI."""
    print(f"[Mossbauer] {context}: {type(exc).__name__}: {exc}", file=sys.stderr)


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
        self.fit_center_var = tk.BooleanVar(value=False)
        # σ gaussiano de la Voigt como parámetro global libre (sólo en modo Voigt).
        self.fit_sigma_var = tk.BooleanVar(value=False)
        self.likelihood_var = tk.StringVar(value="gauss")
        # Mejora 10: pérdida robusta del optimizador (linear/soft_l1/huber).
        self.robust_loss_var = tk.StringVar(value="linear")
        # Mejora 12: propagar la incertidumbre de calibración (σ_vmax) a los pesos.
        self.propagate_calib_var = tk.BooleanVar(value=False)
        # Mejora 14: pre-pasada de optimización global (differential_evolution)
        # antes del pulido TRF. Opt-in (lenta); útil con varios sextetes.
        self.global_opt_var = tk.BooleanVar(value=False)
        self.show_residual_var = tk.BooleanVar(value=True)
        self.show_legend_var = tk.BooleanVar(value=False)
        self.fit_mode_var = tk.StringVar(value="discrete")
        self.line_profile_var = tk.StringVar(value="Lorentziana")
        self.dist_variable_var = tk.StringVar(value="BHF")
        self.dist_shape_var = tk.StringVar(value="Histograma")
        self.dist_use_sharp_var = tk.BooleanVar(value=False)
        self.fixed_distribution_path: Path | None = None
        self.dist_refine_global_var = tk.BooleanVar(value=False)
        # Mejora 5: regularización del histograma — "tikhonov" (L2, suave) o
        # "tv" (variación total, picos afilados).
        self.dist_reg_mode_var = tk.StringVar(value="tikhonov")
        self.ai_ollama_url_var = tk.StringVar(value="http://localhost:11434")
        self.ai_ollama_model_var = tk.StringVar(value="")
        self.last_bhf_fit = None
        self.last_bhf_sharp_indices: list[int] = []
        # No simular nada hasta que el usuario toque un parámetro del modelo
        # (o ejecute un ajuste / auto-detección). Se reinicia al cargar datos.
        self._simulate_enabled = False
        self.sextet_enabled: dict[int, tk.BooleanVar] = {1: tk.BooleanVar(value=True), 2: tk.BooleanVar(value=False), 3: tk.BooleanVar(value=False)}
        self.component_kind: dict[int, tk.StringVar] = {1: tk.StringVar(value="Sextete"), 2: tk.StringVar(value="Sextete"), 3: tk.StringVar(value="Sextete")}
        # Modo de intensidades por sextete: "free" = i1,i2,i3 libres (sin
        # constraint física); "texture" = parámetro de textura t ∈ [0,1] con
        # i1=3, i3=1, i2=4t/(2−t). Sólo aplica a kind=Sextete.
        self.intensity_mode: dict[int, tk.StringVar] = {1: tk.StringVar(value="free"), 2: tk.StringVar(value="free"), 3: tk.StringVar(value="free")}
        # Tratamiento del cuadrupolo por sextete (mejora 8b):
        #   "1st_order"      : patrón rígido aditivo (histórico).
        #   "kundig_fixed"   : diagonalización completa con β fijo (slider).
        #   "kundig_powder"  : promedio policristal Gauss-Legendre.
        self.quad_treatment: dict[int, tk.StringVar] = {1: tk.StringVar(value="1st_order"), 2: tk.StringVar(value="1st_order"), 3: tk.StringVar(value="1st_order")}
        self.current_file_var = tk.StringVar(value="Sin fichero cargado")
        self.calib_label_var = tk.StringVar(value="")
        self.last_fit_free_keys: list[str] = []
        self.last_fit_cov: np.ndarray | None = None
        self.last_fit_param_errors: dict[str, float] = {}
        self.last_fit_stats: dict[str, float] = {}
        self.last_fit_correlations: dict[str, object] = {}
        # Restricciones lineales: target = factor * source + offset.
        self.constraints: list[dict[str, object]] = []
        # Calibración asociada al espectro actual (de la web o de un fichero).
        self.calibration_info: dict | None = None

        self.vars: dict[str, tk.DoubleVar] = {}
        self.entry_vars: dict[str, tk.StringVar] = {}
        self.fixed_vars: dict[str, tk.BooleanVar] = {}
        self.slider_specs: dict[str, tuple[float, float, float]] = {}
        self.slider_label_widgets: dict[str, ttk.Label] = {}

        try:
            if SETTINGS_PATH.exists():
                _settings_lang = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")).get("ui_language", get_language())
                set_language(_settings_lang)
        except Exception:
            pass

        self._theme_var = tk.StringVar(value="sv_ttk")
        self._sv_available = False
        self._sv_active = False
        self._build_ui()

        for default in (Path("FE040723.ws5"), Path("Ja271025.ws5")):
            if default.exists():
                self.load_ws5(default)
                break

        self.load_settings()
        # Estado inicial de agrisado (cubre el arranque sin settings.json).
        self._refresh_component_widgets()
        self.on_line_profile_change()
        self.refresh_dist_slider_labels()
        if self.counts is not None:
            self.refold_data()
            self.update_plot()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(150, self.show_startup_splash)
        self.after(2500, lambda: self.check_for_updates(silent=True))
        self.after(4000, self._check_requirements_background)

    def _reconfigure_styles(self, style: ttk.Style, sv_active: bool) -> None:
        _dark = (self._theme_var.get() == "sv_ttk_dark")
        if _dark:
            # sv_ttk dark gestiona los widgets estándar; solo corregimos lo específico.
            # Paleta: mauve (sin ningún azul) + slate para texto
            accent  = "#cba6f7"   # Catppuccin mauve
            hdr_bg  = "#11111b"   # crust
            hdr_sub = "#b4befe"   # lavender
            fg_main = "#e2e8f0"
            fg_sub  = "#a6adc8"
            bg   = style.lookup("TFrame", "background") or "#1c1c1e"
            card = bg
            self.configure(background=bg)
            # Pestañas: sv_ttk dark puede usar azul Windows → neutralizar
            style.configure("TNotebook.Tab", foreground=fg_sub)
            style.map("TNotebook.Tab",
                      background=[("selected", "#313244")],
                      foreground=[("selected", fg_main)])
            # Etiquetas de LabelFrame: sv_ttk dark las pinta de azul → mauve
            style.configure("TLabelframe.Label", foreground=accent)
            # Estilos propios
            style.configure("Section.TLabelframe", padding=10)
            style.configure("Section.TLabelframe.Label",
                            font=("TkDefaultFont", 10, "bold"), foreground=accent)
            style.configure("Title.TLabel",
                            font=("TkDefaultFont", 17, "bold"), foreground=fg_main)
            style.configure("Subtitle.TLabel",
                            font=("TkDefaultFont", 9), foreground=fg_sub)
            style.configure("Header.TLabel",
                            font=("TkDefaultFont", 18, "bold"), foreground=fg_main, background=hdr_bg)
            style.configure("HeaderSub.TLabel",
                            font=("TkDefaultFont", 9), foreground=hdr_sub, background=hdr_bg)
            style.configure("Accent.TButton", padding=7, font=("TkDefaultFont", 9, "bold"),
                            background="#7c3aed", foreground="white")
            style.map("Accent.TButton",
                      background=[("active", "#6d28d9"), ("pressed", "#5b21b6")])
            style.configure("Small.TButton", padding=(5, 4))
            # Widgets tk (no ttk): colores explícitos
            if hasattr(self, "file_label"):
                self.file_label.configure(bg=card, fg=fg_main)
            if hasattr(self, "calib_label"):
                self.calib_label.configure(bg=card, fg=fg_sub)
            if hasattr(self, "info"):
                self.info.configure(background=card, foreground=fg_main)
            # Matplotlib
            _plot_bg = bg; _axes_bg = "#2a2a2a"; _tc = fg_sub; _lc = fg_main; _sc = "#6c7086"
        elif sv_active:
            accent      = "#0ea5d9"
            accent_dark = "#075985"
            bg   = style.lookup("TFrame", "background") or "#f0f0f0"
            card = "#ffffff"
            self.configure(background=bg)
            style.configure("Section.TLabelframe", padding=10)
            style.configure("Section.TLabelframe.Label", font=("TkDefaultFont", 10, "bold"), foreground=accent_dark)
            style.configure("Title.TLabel",    font=("TkDefaultFont", 17, "bold"), foreground=accent_dark)
            style.configure("Subtitle.TLabel", font=("TkDefaultFont", 9), foreground="#4b6478")
            style.configure("Header.TLabel",    font=("TkDefaultFont", 18, "bold"), foreground="white",    background=accent_dark)
            style.configure("HeaderSub.TLabel", font=("TkDefaultFont", 9), foreground="#dff6ff", background=accent_dark)
            style.configure("Accent.TButton", padding=7, font=("TkDefaultFont", 9, "bold"), background=accent, foreground="white")
            style.map("Accent.TButton", background=[("active", "#0284c7"), ("pressed", "#0369a1")])
            style.configure("Small.TButton", padding=(5, 4))
            if hasattr(self, "file_label"):
                self.file_label.configure(bg=card, fg="#083344")
            if hasattr(self, "calib_label"):
                self.calib_label.configure(bg=card, fg="#0e7490")
            if hasattr(self, "info"):
                self.info.configure(background=card, foreground="#102a43")
            _plot_bg = card; _axes_bg = card; _tc = "#17202a"; _lc = "#17202a"; _sc = "#cccccc"
        else:
            accent      = "#0ea5d9"
            accent_dark = "#075985"
            bg   = "#eaf4ff"
            card = "#f8fbff"
            self.configure(background=bg)
            style.configure("TFrame", background=bg)
            style.configure("TLabelframe", background=card, borderwidth=1, relief="solid")
            style.configure("TLabelframe.Label", background=bg)
            style.configure("TLabel", background=bg, foreground="#17202a")
            style.configure("Title.TLabel",    font=("TkDefaultFont", 17, "bold"), foreground=accent_dark, background=bg)
            style.configure("Subtitle.TLabel", font=("TkDefaultFont", 9), foreground="#4b6478", background=bg)
            style.configure("Section.TLabelframe", padding=10, background=card, relief="solid")
            style.configure("Section.TLabelframe.Label", font=("TkDefaultFont", 10, "bold"), foreground=accent_dark, background=bg)
            style.configure("TNotebook", background=bg, borderwidth=0)
            style.configure("TNotebook.Tab", padding=(12, 6), background="#cfefff", foreground="#0f3d5c")
            style.map("TNotebook.Tab", background=[("selected", "#38bdf8")], foreground=[("selected", "white")])
            style.configure("Header.TLabel",    font=("TkDefaultFont", 18, "bold"), foreground="white",    background=accent_dark)
            style.configure("HeaderSub.TLabel", font=("TkDefaultFont", 9), foreground="#dff6ff", background=accent_dark)
            style.configure("TNotebook", borderwidth=0)
            style.configure("Accent.TButton", padding=7, font=("TkDefaultFont", 9, "bold"), background=accent, foreground="white")
            style.map("Accent.TButton", background=[("active", "#0284c7"), ("pressed", "#0369a1")])
            style.configure("Small.TButton", padding=(5, 4))
            if hasattr(self, "file_label"):
                self.file_label.configure(bg=card, fg="#083344")
            if hasattr(self, "calib_label"):
                self.calib_label.configure(bg=card, fg="#0e7490")
            if hasattr(self, "info"):
                self.info.configure(background=card, foreground="#102a43")
            _plot_bg = card; _axes_bg = card; _tc = "#17202a"; _lc = "#17202a"; _sc = "#cccccc"
        self._bg = bg
        self._card = card
        # Matplotlib: actualizar si la figura ya existe
        if hasattr(self, "fig") and hasattr(self, "canvas"):
            try:
                self.fig.patch.set_facecolor(_plot_bg)
                for _ax in ([self.ax, self.ax_res] if hasattr(self, "ax_res") else [self.ax]):
                    _ax.set_facecolor(_axes_bg)
                    _ax.tick_params(colors=_tc, which="both")
                    _ax.xaxis.label.set_color(_lc)
                    _ax.yaxis.label.set_color(_lc)
                    for _spine in _ax.spines.values():
                        _spine.set_color(_sc)
                self.canvas.draw_idle()
            except Exception:
                pass
        # Toolbar matplotlib: iconos negros → fondo claro en modo oscuro
        if hasattr(self, "toolbar"):
            try:
                _tbg = "#d4d4d4" if _dark else ""
                self.toolbar.config(background=_tbg)
                for _w in self.toolbar.winfo_children():
                    try:
                        _w.config(background=_tbg)
                    except Exception:
                        pass
            except Exception:
                pass

    def _switch_theme(self, theme: str) -> None:
        style = ttk.Style(self)
        _sv = False
        if theme == "sv_ttk":
            if not self._sv_available:
                messagebox.showwarning(tr("msg.theme_title"), tr("msg.theme_not_installed"))
                self._theme_var.set("clam")
                return
            try:
                import sv_ttk
                sv_ttk.set_theme("light")
                _sv = True
            except Exception as exc:
                messagebox.showerror(tr("msg.theme_title"), tr("msg.theme_apply_error", error=str(exc)))
                self._theme_var.set("clam")
                return
        elif theme == "sv_ttk_dark":
            if not self._sv_available:
                messagebox.showwarning(tr("msg.theme_title"), tr("msg.theme_not_installed"))
                self._theme_var.set("clam")
                return
            try:
                import sv_ttk
                sv_ttk.set_theme("dark")
                _sv = True
            except Exception as exc:
                messagebox.showerror(tr("msg.theme_title"), tr("msg.theme_apply_error", error=str(exc)))
                self._theme_var.set("clam")
                return
        else:
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass
        self._sv_active = _sv
        self._reconfigure_styles(style, _sv)
        self.save_settings()

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        _saved_theme = "sv_ttk"
        try:
            if SETTINGS_PATH.exists():
                _saved_theme = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")).get("theme", "sv_ttk")
        except Exception:
            pass
        _sv = False
        try:
            import sv_ttk
            self._sv_available = True
            if _saved_theme == "sv_ttk_dark":
                sv_ttk.set_theme("dark")
                _sv = True
            elif _saved_theme != "clam":
                sv_ttk.set_theme("light")
                _sv = True
        except ImportError:
            self._sv_available = False
        if not _sv:
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass
        self._sv_active = _sv
        self._theme_var.set(_saved_theme if _saved_theme in ("sv_ttk", "sv_ttk_dark", "clam") else ("sv_ttk" if _sv else "clam"))
        self._reconfigure_styles(style, _sv)
        accent_dark = "#075985"
        bg = self._bg
        card = self._card

        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label=tr("file.open"), command=self.open_file)
        file_menu.add_command(label=tr("file.web_measurements"), command=lambda: self.open_web_download_dialog(kind="mossbauer"))
        file_menu.add_command(label=tr("file.web_calibrations"), command=self.open_calibration_download_dialog)
        file_menu.add_command(label=tr("file.use_as_calibration"), command=self.use_loaded_file_as_calibration)
        file_menu.add_separator()
        file_menu.add_command(label=tr("file.save_fit"), command=self.save_fit)
        file_menu.add_command(label=tr("file.export_report"), command=self.export_report_dialog)
        file_menu.add_separator()
        file_menu.add_command(label=tr("file.save_session"), command=self.save_session_dialog)
        file_menu.add_command(label=tr("file.upload_session"), command=self.open_web_upload_analysis_dialog)
        file_menu.add_command(label=tr("file.load_session"), command=self.load_session_dialog)
        file_menu.add_separator()
        file_menu.add_command(label=tr("file.exit"), command=self.on_close)
        menubar.add_cascade(label=tr("menu.file"), menu=file_menu)

        fit_menu = tk.Menu(menubar, tearoff=0)
        fit_menu.add_command(label=tr("fit.find_center"), command=self.auto_center)
        fit_menu.add_command(label=tr("fit.init_from_minima"), command=self.auto_guess_from_minima)
        fit_menu.add_command(label=tr("fit.auto_from_minima"), command=self.auto_fit_from_minima)
        fit_menu.add_command(label=tr("fit.ollama_start"), command=self.open_ollama_ai_dialog)
        fit_menu.add_command(label=tr("fit.run"), command=self.fit_current_data)
        fit_menu.add_command(label=tr("fit.bootstrap"), command=self.bootstrap_errors_current)
        fit_menu.add_separator()
        fit_menu.add_command(label=tr("fit.fix_all"), command=self.fix_all_parameters)
        fit_menu.add_command(label=tr("fit.free_all"), command=self.free_all_parameters)
        menubar.add_cascade(label=tr("menu.fit"), menu=fit_menu)

        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_radiobutton(
            label=tr("options.discrete_sextets"),
            variable=self.fit_mode_var,
            value="discrete",
            command=self.set_fit_mode_from_menu,
        )
        options_menu.add_radiobutton(
            label=tr("options.distribution_bhf"),
            variable=self.fit_mode_var,
            value="bhf_distribution",
            command=self.set_fit_mode_from_menu,
        )
        options_menu.add_separator()
        options_menu.add_checkbutton(label=tr("options.show_residual"), variable=self.show_residual_var, command=self.update_plot)
        options_menu.add_checkbutton(label=tr("options.show_legend"), variable=self.show_legend_var, command=self.update_plot)
        options_menu.add_separator()
        profile_menu = tk.Menu(options_menu, tearoff=0)
        profile_menu.add_radiobutton(label=tr("options.profile_lorentzian"), variable=self.line_profile_var, value="Lorentziana", command=self.on_line_profile_change)
        profile_menu.add_radiobutton(label=tr("options.profile_voigt"), variable=self.line_profile_var, value="Voigt", command=self.on_line_profile_change)
        options_menu.add_cascade(label=tr("options.line_profile"), menu=profile_menu)
        options_menu.add_separator()
        options_menu.add_checkbutton(
            label=tr("options.add_sharp"),
            variable=self.dist_use_sharp_var,
            command=self.on_bhf_distribution_option_change,
        )
        options_menu.add_checkbutton(
            label=tr("options.refine_global"),
            variable=self.dist_refine_global_var,
            command=self.on_bhf_distribution_option_change,
        )
        options_menu.add_separator()
        options_menu.add_command(label=tr("options.constraints"), command=self.open_constraints_dialog)
        options_menu.add_command(label=tr("options.physical_presets"), command=self.open_physical_presets_dialog)
        options_menu.add_separator()
        theme_menu = tk.Menu(options_menu, tearoff=0)
        theme_menu.add_radiobutton(label=tr("options.theme_modern"), variable=self._theme_var,
                                   value="sv_ttk", command=lambda: self._switch_theme("sv_ttk"))
        theme_menu.add_radiobutton(label=tr("options.theme_classic"), variable=self._theme_var,
                                   value="clam", command=lambda: self._switch_theme("clam"))
        options_menu.add_cascade(label=tr("options.theme"), menu=theme_menu)
        menubar.add_cascade(label=tr("menu.options"), menu=options_menu)

        language_menu = tk.Menu(menubar, tearoff=0)
        self._ui_language_var = tk.StringVar(value=get_language())
        for lang_code, lang_name in available_languages().items():
            language_menu.add_radiobutton(
                label=lang_name,
                variable=self._ui_language_var,
                value=lang_code,
                command=lambda code=lang_code: self.change_ui_language(code),
            )
        menubar.add_cascade(label=tr("menu.language"), menu=language_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label=tr("help.open"), command=self.show_help)
        help_menu.add_command(label=tr("help.about"), command=self.show_about)
        help_menu.add_separator()
        help_menu.add_command(label=tr("help.changelog"), command=self.show_changelog)
        help_menu.add_command(label=tr("help.check_updates"), command=lambda: self.check_for_updates(silent=False))
        help_menu.add_command(label=tr("help.configure_updates"), command=self.open_update_settings_dialog)
        menubar.add_cascade(label=tr("menu.help"), menu=help_menu)
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
        tk.Label(title_block, text=APP_NAME, bg=accent_dark, fg="white",
                 font=("TkDefaultFont", 18, "bold")).pack(anchor=tk.W)
        tk.Label(title_block, text=tr("main.subtitle"), bg=accent_dark, fg="#dff6ff",
                 font=("TkDefaultFont", 9)).pack(anchor=tk.W, pady=(0, 5))
        tk.Label(title_block, text=APP_AUTHOR, bg=accent_dark, fg="#dff6ff",
                 font=("TkDefaultFont", 9)).pack(anchor=tk.W)
        tk.Label(title_block, text=APP_DEPARTMENT, bg=accent_dark, fg="#dff6ff",
                 font=("TkDefaultFont", 9)).pack(anchor=tk.W)

        file_box = ttk.LabelFrame(controls, text=tr("controls.file_box"), style="Section.TLabelframe")
        file_box.pack(fill=tk.X, pady=(0, 8))
        self.file_label = tk.Label(
            file_box,
            textvariable=self.current_file_var,
            bg=card,
            fg="#083344",
            font=("TkDefaultFont", 12, "bold"),
            anchor="w",
            justify="left",
            padx=10,
            pady=8,
            wraplength=405,
        )
        self.file_label.pack(anchor=tk.W, fill=tk.X)
        file_box.bind("<Button-3>", self.show_file_box_menu)
        self.file_label.bind("<Button-3>", self.show_file_box_menu)
        self.calib_label = tk.Label(
            file_box,
            textvariable=self.calib_label_var,
            bg=card,
            fg="#0e7490",
            font=("TkDefaultFont", 9),
            anchor="w",
            justify="left",
            padx=10,
            pady=0,
            wraplength=405,
        )
        # Se muestra solo cuando hay calibración activa (update_calibration_label lo gestiona)

        info_box = ttk.LabelFrame(controls, text=tr("controls.info_box"), style="Section.TLabelframe")
        info_box.pack(fill=tk.X, pady=8)
        self.info = tk.Text(
            info_box,
            width=38,
            height=12,
            wrap=tk.WORD,
            relief=tk.FLAT,
            background=card,
            foreground="#102a43",
            font=("TkDefaultFont", 9),
        )
        self.info.pack(fill=tk.X, pady=2)

        calib_box = ttk.LabelFrame(controls, text=tr("controls.calibration_box"), style="Section.TLabelframe")
        calib_box.pack(fill=tk.X, pady=8)
        self._add_slider(calib_box, "vmax", tr("slider.vmax"), 11.8788, 1.0, 15.0, 0.0001, fit_param=False)
        ttk.Checkbutton(
            calib_box,
            text=tr("checkbox.fit_vmax"),
            variable=self.fit_velocity_var,
            command=self.on_fit_velocity_toggle,
        ).pack(anchor=tk.W, pady=(0, 4))
        self._add_slider(calib_box, "center", tr("slider.center"), 256.5, 250.0, 263.0, 0.0001, fit_param=False)
        ttk.Checkbutton(
            calib_box,
            text=tr("checkbox.fit_center"),
            variable=self.fit_center_var,
        ).pack(anchor=tk.W, pady=(0, 4))
        self._add_slider(calib_box, "baseline", tr("slider.baseline"), 1.0, 0.70, 1.30, 0.0005)
        self._add_slider(calib_box, "slope", tr("slider.slope"), 0.0, -0.0001, 0.0001, 0.000001)
        self._add_slider(calib_box, "voigt_sigma", tr("slider.voigt_sigma"), 0.05, 0.0, 1.0, 0.001, fit_param=False)
        self.fit_sigma_check = ttk.Checkbutton(
            calib_box,
            text=tr("checkbox.fit_sigma"),
            variable=self.fit_sigma_var,
        )
        self.fit_sigma_check.pack(anchor=tk.W, pady=(0, 4))
        self.fit_sigma_check.configure(
            state=tk.NORMAL if self.line_profile_var.get() == "Voigt" else tk.DISABLED
        )

        line_box = ttk.LabelFrame(controls, text=tr("controls.reference_box"), style="Section.TLabelframe")
        line_box.pack(fill=tk.X, pady=8)
        ttk.Label(
            line_box,
            text=tr("controls.reference_lines", positions=", ".join(f"{x:.3f}" for x in LINE_POS_33T)),
            justify=tk.LEFT,
            wraplength=350,
        ).pack(anchor=tk.W, pady=2)

        sim_box = ttk.LabelFrame(plot_frame, text=tr("controls.simulation_box"), style="Section.TLabelframe")
        sim_box.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
        sim_header = ttk.Frame(sim_box)
        sim_header.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(
            sim_header,
            text=tr("controls.fit_mode_hint"),
            style="Subtitle.TLabel",
        ).pack(side=tk.LEFT, anchor=tk.W)
        ttk.Button(sim_header, text=tr("sim.fit"), command=self.fit_current_data, style="Accent.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(sim_header, text=tr("sim.ai_start"), command=self.open_ollama_ai_dialog, style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(sim_header, text=tr("sim.auto_minima"), command=self.auto_fit_from_minima, style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(sim_header, text=tr("sim.fix_all"), command=self.fix_all_parameters, style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(sim_header, text=tr("sim.free_all"), command=self.free_all_parameters, style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))

        notebook = ttk.Notebook(sim_box)
        notebook.pack(fill=tk.X, expand=False)
        self.notebook = notebook
        dist_tab = ttk.Frame(notebook, padding=6)
        self.dist_tab = dist_tab
        notebook.add(dist_tab, text=tr("tab.distribution_bhf"))
        dist_top = ttk.Frame(dist_tab)
        dist_top.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(
            dist_top,
            text=tr("bhf.description"),
            style="Subtitle.TLabel",
        ).pack(side=tk.LEFT, anchor=tk.W)
        dist_cols = ttk.Frame(dist_tab)
        dist_cols.pack(fill=tk.X)
        d1 = ttk.Frame(dist_cols); d2 = ttk.Frame(dist_cols); d3 = ttk.Frame(dist_cols)
        d1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        d2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        d3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        ttk.Label(d1, text=tr("bhf.variable_label")).pack(anchor=tk.W)
        dist_var_box = ttk.Combobox(d1, textvariable=self.dist_variable_var, values=("BHF", "ΔEQ"), width=10, state="readonly")
        dist_var_box.pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
        dist_var_box.bind("<<ComboboxSelected>>", lambda _event: self.on_bhf_distribution_option_change())
        ttk.Label(d1, text=tr("bhf.shape_label")).pack(anchor=tk.W)
        dist_shape_box = ttk.Combobox(d1, textvariable=self.dist_shape_var, values=("Histograma", "Gaussiana", "Binomial", "Fija"), width=12, state="readonly")
        dist_shape_box.pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
        dist_shape_box.bind("<<ComboboxSelected>>", lambda _event: self.on_bhf_distribution_option_change())
        ttk.Button(d1, text=tr("bhf.load_fixed"), command=self.load_fixed_distribution_file, style="Small.TButton").pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
        self._add_slider(d1, "dist_delta", tr("slider.dist_delta"), 0.0, -2.5, 2.5, 0.001, fit_param=False)
        self._add_slider(d1, "dist_quad", tr("slider.dist_quad"), 0.0, -4.0, 4.0, 0.001, fit_param=False)
        self._add_slider(d1, "dist_fixed_bhf", tr("slider.dist_fixed_bhf"), BHF_DEFAULT_T, 0.0, 60.0, 0.01, fit_param=False)
        self._add_slider(d1, "dist_gamma", tr("slider.dist_gamma"), 0.18, 0.03, 1.0, 0.001, fit_param=False)
        self._add_slider(d2, "dist_bmin", tr("slider.dist_bmin"), 0.0, 0.0, 60.0, 0.1, fit_param=False)
        self._add_slider(d2, "dist_bmax", tr("slider.dist_bmax"), 50.0, 1.0, 60.0, 0.1, fit_param=False)
        self._add_slider(d2, "dist_nbins", tr("slider.dist_nbins"), 50.0, 10.0, 100.0, 1.0, fit_param=False)
        self._add_slider(d3, "dist_log_alpha", tr("slider.dist_log_alpha"), -2.0, -8.0, 4.0, 0.1, fit_param=False)
        alpha_buttons = ttk.Frame(d3)
        alpha_buttons.pack(fill=tk.X, pady=(0, 2))
        ttk.Button(alpha_buttons, text=tr("bhf.alpha_fine"), command=lambda: self.set_bhf_alpha_preset(-5.0), style="Small.TButton").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(alpha_buttons, text=tr("bhf.alpha_medium"), command=lambda: self.set_bhf_alpha_preset(-2.0), style="Small.TButton").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(alpha_buttons, text=tr("bhf.alpha_smooth"), command=lambda: self.set_bhf_alpha_preset(1.0), style="Small.TButton").pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))
        ttk.Checkbutton(d3, text=tr("bhf.use_sharp"), variable=self.dist_use_sharp_var, command=self.on_bhf_distribution_option_change).pack(anchor=tk.W, pady=(2, 0))
        ttk.Checkbutton(d3, text=tr("bhf.refine_global"), variable=self.dist_refine_global_var, command=self.on_bhf_distribution_option_change).pack(anchor=tk.W, pady=(0, 2))
        ttk.Button(d3, text=tr("bhf.lcurve_alpha"), command=self.scan_bhf_alpha_gui, style="Small.TButton").pack(anchor=tk.E, fill=tk.X, pady=(2, 0))

        for idx in (1, 2, 3):
            tab = ttk.Frame(notebook, padding=6)
            notebook.add(tab, text=tr("tab.component", idx=idx))
            top_row = ttk.Frame(tab)
            top_row.pack(fill=tk.X, pady=(0, 4))
            if idx > 1:
                ttk.Checkbutton(top_row, text=tr("component.enable", idx=idx), variable=self.sextet_enabled[idx], command=self.on_component_activation_change).pack(side=tk.LEFT)
            else:
                ttk.Label(top_row, text=tr("component.main_active"), style="Subtitle.TLabel").pack(side=tk.LEFT)
            ttk.Label(top_row, text=tr("component.shape_label")).pack(side=tk.LEFT, padx=(18, 4))
            kind_box = ttk.Combobox(top_row, textvariable=self.component_kind[idx], values=("Sextete", "Doblete", "Singlete"), width=10, state="readonly")
            kind_box.pack(side=tk.LEFT)
            kind_box.bind("<<ComboboxSelected>>", lambda _event, i=idx: self.on_component_kind_change(i))
            ttk.Label(top_row, text=tr("component.intensity_label")).pack(side=tk.LEFT, padx=(12, 4))
            mode_box = ttk.Combobox(top_row, textvariable=self.intensity_mode[idx], values=("free", "texture"), width=8, state="readonly")
            mode_box.pack(side=tk.LEFT)
            mode_box.bind("<<ComboboxSelected>>", lambda _event, i=idx: self.on_intensity_mode_change(i))
            if not hasattr(self, "_intensity_combos"):
                self._intensity_combos = {}
            self._intensity_combos[idx] = mode_box
            ttk.Label(top_row, text=tr("component.quad_treatment_label")).pack(side=tk.LEFT, padx=(12, 4))
            treat_box = ttk.Combobox(top_row, textvariable=self.quad_treatment[idx], values=("1st_order", "kundig_fixed", "kundig_powder"), width=14, state="readonly")
            treat_box.pack(side=tk.LEFT)
            treat_box.bind("<<ComboboxSelected>>", lambda _event, i=idx: self.on_quad_treatment_change(i))
            if not hasattr(self, "_quad_combos"):
                self._quad_combos = {}
            self._quad_combos[idx] = treat_box
            cols = ttk.Frame(tab)
            cols.pack(fill=tk.X)
            c1 = ttk.Frame(cols); c2 = ttk.Frame(cols); c3 = ttk.Frame(cols)
            c1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
            c2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
            c3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
            p = f"s{idx}_"
            self._add_slider(c1, p + "delta", tr("slider.s_delta"), 0.0, -2.0, 3.0, 0.001)
            self._add_slider(c1, p + "quad", tr("slider.s_quad"), 0.0, -4.0, 4.0, 0.001)
            self._add_slider(c1, p + "bhf", tr("slider.s_bhf"), BHF_DEFAULT_T, 0.0, 60.0, 0.01)
            self._add_slider(c2, p + "gamma1", tr("slider.s_gamma1"), 0.30, 0.03, 2.0, 0.001)
            self._add_slider(c2, p + "gamma2", tr("slider.s_gamma2"), 1.0, 0.2, 3.0, 0.001)
            self._add_slider(c2, p + "gamma3", tr("slider.s_gamma3"), 1.0, 0.2, 3.0, 0.001)
            self._add_slider(c3, p + "depth", tr("slider.s_depth"), 0.030 if idx == 1 else 0.005, 0.0, 0.30, 0.0005)
            self._add_slider(c3, p + "int1", tr("slider.s_int1"), 1.0, 0.0, 2.0, 0.001)
            self._add_slider(c3, p + "int2", tr("slider.s_int2"), 1.0, 0.0, 3.0, 0.001)
            self._add_slider(c3, p + "int3", tr("slider.s_int3"), 1.0, 0.0, 3.0, 0.001)
            self._add_slider(c3, p + "texture", tr("slider.s_texture"), 2.0/3.0, 0.0, 1.0, 0.001)
            self._add_slider(c3, p + "beta", tr("slider.s_beta"), 0.0, 0.0, 90.0, 0.1)
            self._refresh_intensity_mode_widgets(idx)
            self._refresh_quad_treatment_widgets(idx)

        plot_area = ttk.Frame(plot_frame)
        plot_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._refresh_distribution_tab_visibility(update=False)

        self.fig = Figure(figsize=(8.5, 5.8), dpi=100, facecolor="#f8fbff")
        gs = self.fig.add_gridspec(2, 1, height_ratios=[4.6, 1.0], hspace=0.08)
        self.ax = self.fig.add_subplot(gs[0])
        self.ax_res = self.fig.add_subplot(gs[1], sharex=self.ax)
        self.ax.set_ylabel(tr("plot.transmission_ylabel"))
        self.ax_res.set_ylabel(tr("plot.residual_ylabel"))
        self.ax_res.set_xlabel(tr("plot.velocity_xlabel"))
        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_area)
        toolbar = NavigationToolbar2Tk(self.canvas, plot_area, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def settings_payload(self) -> dict:
        return {
            "geometry": self.geometry(),
            "vars": {k: float(v.get()) for k, v in self.vars.items()},
            "fixed": {k: bool(v.get()) for k, v in self.fixed_vars.items()},
            "sextet_enabled": {str(k): bool(v.get()) for k, v in self.sextet_enabled.items()},
            "component_kind": {str(k): v.get() for k, v in self.component_kind.items()},
            "intensity_mode": {str(k): v.get() for k, v in getattr(self, "intensity_mode", {}).items()},
            "quad_treatment": {str(k): v.get() for k, v in getattr(self, "quad_treatment", {}).items()},
            "fit_velocity": bool(self.fit_velocity_var.get()),
            "fit_center": bool(self.fit_center_var.get()),
            "show_residual": bool(self.show_residual_var.get()),
            "show_legend": bool(self.show_legend_var.get()),
            "fit_mode": self.fit_mode_var.get(),
            "line_profile": self.line_profile_var.get(),
            "likelihood": self.likelihood_var.get(),
            "robust_loss": self.robust_loss_var.get(),
            "propagate_calib": bool(self.propagate_calib_var.get()),
            "global_opt": bool(self.global_opt_var.get()),
            "dist_variable": self.dist_variable_var.get(),
            "dist_shape": self.dist_shape_var.get(),
            "dist_reg_mode": self.dist_reg_mode_var.get(),
            "fixed_distribution_path": str(self.fixed_distribution_path) if self.fixed_distribution_path else None,
            "dist_use_sharp": bool(self.dist_use_sharp_var.get()),
            "dist_refine_global": bool(self.dist_refine_global_var.get()),
            "theme": self._theme_var.get(),
            "ui_language": get_language(),
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
        except Exception as exc:
            _log_warning("No se pudieron cargar los ajustes guardados", exc)
            return
        self._apply_state_payload(data)

    def _apply_state_payload(self, data: dict, restore_geometry: bool = True) -> None:
        """Apply an in-memory settings dict (matching ``settings_payload()``).

        Used by ``load_settings`` after reading from disk and by
        ``change_ui_language`` to restore state after rebuilding the UI.
        """
        try:
            if restore_geometry:
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
            for idx, value in data.get("intensity_mode", {}).items():
                i = int(idx)
                if i in self.intensity_mode and value in ("free", "texture"):
                    self.intensity_mode[i].set(value)
            for idx, value in data.get("quad_treatment", {}).items():
                i = int(idx)
                if i in self.quad_treatment and value in ("1st_order", "kundig_fixed", "kundig_powder"):
                    self.quad_treatment[i].set(value)
            self.fit_velocity_var.set(bool(data.get("fit_velocity", self.fit_velocity_var.get())))
            self.fit_center_var.set(bool(data.get("fit_center", self.fit_center_var.get())))
            self.show_residual_var.set(bool(data.get("show_residual", self.show_residual_var.get())))
            self.show_legend_var.set(bool(data.get("show_legend", self.show_legend_var.get())))
            self.fit_mode_var.set(data.get("fit_mode", self.fit_mode_var.get()))
            self.line_profile_var.set(data.get("line_profile", self.line_profile_var.get()))
            self.on_line_profile_change()
            self.likelihood_var.set(data.get("likelihood", self.likelihood_var.get()))
            self.robust_loss_var.set(data.get("robust_loss", self.robust_loss_var.get()))
            self.propagate_calib_var.set(bool(data.get("propagate_calib", self.propagate_calib_var.get())))
            self.global_opt_var.set(bool(data.get("global_opt", self.global_opt_var.get())))
            self.dist_variable_var.set(data.get("dist_variable", self.dist_variable_var.get()))
            self.dist_shape_var.set(data.get("dist_shape", self.dist_shape_var.get()))
            self.dist_reg_mode_var.set(data.get("dist_reg_mode", self.dist_reg_mode_var.get()))
            self.fixed_distribution_path = Path(data["fixed_distribution_path"]) if data.get("fixed_distribution_path") else None
            self.dist_use_sharp_var.set(bool(data.get("dist_use_sharp", self.dist_use_sharp_var.get())))
            self.dist_refine_global_var.set(bool(data.get("dist_refine_global", self.dist_refine_global_var.get())))
            self._theme_var.set(data.get("theme", "sv_ttk" if self._sv_active else "clam"))
            if data.get("ui_language"):
                set_language(data.get("ui_language"))
                if hasattr(self, "_ui_language_var"):
                    self._ui_language_var.set(get_language())
            self.constraints = list(data.get("constraints", self.constraints))
            self.ai_ollama_url_var.set(data.get("ai_ollama_url", self.ai_ollama_url_var.get()))
            self.ai_ollama_model_var.set(data.get("ai_ollama_model", self.ai_ollama_model_var.get()))
            info_text = data.get("info_text")
            if info_text and hasattr(self, "info"):
                self.info.delete("1.0", tk.END)
                self.info.insert(tk.END, info_text)
        except Exception as exc:
            _log_warning("No se pudieron aplicar los ajustes", exc)
        finally:
            self.updating_sliders = False
            self._refresh_distribution_tab_visibility(update=False)
            self._refresh_intensity_mode_widgets()
            self._refresh_quad_treatment_widgets()

    def save_settings(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(json.dumps(self.settings_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            _log_warning("No se pudieron guardar los ajustes", exc)

    def change_ui_language(self, lang: str) -> None:
        if lang not in available_languages():
            return
        if lang == get_language():
            if hasattr(self, "_ui_language_var"):
                self._ui_language_var.set(get_language())
            return
        snapshot = self.settings_payload()
        snapshot["ui_language"] = lang
        set_language(lang)
        # Ocultar la ventana evita que Tk repinte cada widget intermedio
        # durante el destroy/rebuild — la mayor parte del tiempo de cambio
        # de idioma se va en esos repaints, no en CPU.
        was_viewable = bool(self.winfo_viewable())
        if was_viewable:
            self.withdraw()
        try:
            self._rebuild_ui()
            self._apply_state_payload(snapshot, restore_geometry=False)
            self.update_plot()
        finally:
            if was_viewable:
                self.deiconify()
        self.save_settings()

    def _rebuild_ui(self) -> None:
        """Tear down all child widgets and run ``_build_ui`` again.

        Used by ``change_ui_language`` so the UI picks up the new language
        without restarting the program. Plain-Python state (data arrays,
        fit results, calibration info, etc.) lives on ``self`` and survives
        the rebuild because the Tk root itself is not destroyed.
        """
        self.config(menu=tk.Menu(self))
        for child in list(self.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        # Drop references to widgets that no longer exist so helpers like
        # _reconfigure_styles don't poke destroyed handles during rebuild.
        for attr in ("file_label", "info", "fig", "ax", "ax_res",
                     "canvas", "notebook", "dist_tab", "_ui_language_var"):
            if hasattr(self, attr):
                delattr(self, attr)
        self.vars = {}
        self.entry_vars = {}
        self.fixed_vars = {}
        self.slider_specs = {}
        self.slider_label_widgets = {}
        self.slider_widget_refs = {}
        self._build_ui()

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
        tk.Label(body, text=tr("splash.version", version=APP_VERSION), bg="#075985", fg="#fef08a", font=("TkDefaultFont", int(9 * scale), "bold")).pack(pady=(2, 0))
        tk.Label(body, text=tr("main.subtitle"), bg="#075985", fg="#dff6ff", font=("TkDefaultFont", int(10 * scale))).pack(pady=(2, 8))
        tk.Label(body, text=APP_AUTHOR, bg="#075985", fg="#dff6ff", font=("TkDefaultFont", int(9 * scale))).pack()
        tk.Label(body, text=APP_DEPARTMENT, bg="#075985", fg="#dff6ff", font=("TkDefaultFont", int(9 * scale))).pack()
        if click_to_close:
            tk.Label(body, text=tr("splash.click_to_continue"), bg="#075985", fg="#fef08a", font=("TkDefaultFont", int(9 * scale), "bold")).pack(pady=(12, 0))
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
        _dark = (self._theme_var.get() == "sv_ttk_dark")
        txt_bg = "#1e1e2e" if _dark else "#ffffff"
        txt_fg = "#e0e7ff" if _dark else "#17202a"
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("940x660")
        win.transient(self)
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        txt = tk.Text(frame, wrap=tk.WORD, background=txt_bg, foreground=txt_fg,
                      font=("TkDefaultFont", 9), relief="flat", padx=6, pady=6)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(frame, command=txt.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        txt.configure(yscrollcommand=scroll.set)
        txt.insert("1.0", text)
        txt.configure(state=tk.DISABLED)

    def show_help(self) -> None:
        from mossbauer_help import get_help_sections
        help_lang_var = tk.StringVar(value=get_language() if get_language() in {"es", "en", "fr"} else "es")
        sections = get_help_sections(VOIGT_SIGMA, SETTINGS_PATH, lang=help_lang_var.get())

        win = tk.Toplevel(self)
        win.title(tr("help.window_title"))
        win.geometry("1050x720")
        win.transient(self)
        win.configure(background="#eaf4ff")

        header = tk.Frame(win, bg="#075985", padx=14, pady=10)
        header.pack(fill=tk.X)
        header_top = tk.Frame(header, bg="#075985")
        header_top.pack(fill=tk.X)
        tk.Label(header_top, text=tr("help.header_title"), bg="#075985", fg="white", font=("TkDefaultFont", 18, "bold")).pack(side=tk.LEFT, anchor=tk.W)
        lang_frame = tk.Frame(header_top, bg="#075985")
        lang_frame.pack(side=tk.RIGHT)
        tk.Label(lang_frame, text=tr("help.language_label"), bg="#075985", fg="#dff6ff").pack(side=tk.LEFT, padx=(0, 6))
        tk.OptionMenu(lang_frame, help_lang_var, "es", "en", "fr", command=lambda _value: refresh_language()).pack(side=tk.LEFT)
        tk.Label(header, text=tr("help.select_chapter"), bg="#075985", fg="#dff6ff").pack(anchor=tk.W)

        body = ttk.Frame(win, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        chapters = tk.Listbox(body, width=28, bg="#f8fbff", fg="#083344", selectbackground="#38bdf8", selectforeground="white", relief=tk.FLAT, highlightthickness=1, highlightbackground="#bae6fd", font=("TkDefaultFont", 10))
        chapters.grid(row=0, column=0, sticky="ns", padx=(0, 10))

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
            "Vmax", "Ajustar Vmax", "Folding point", "Ajustar folding point", "Base", "Pendiente",
            "Fit Vmax", "Fit folding point", "Baseline and slope", "Baseline", "Slope",
            # Tipos de componente
            "Singlete", "Doblete", "Sextete", "Singlet", "Doublet", "Sextet",
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
            "Cargar sesión", "Opciones automáticas", "Save fit (.dat)", "Save session (.json)",
            "Export Markdown/PDF report", "Automatic settings",
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

        def refresh_language() -> None:
            nonlocal sections
            sections = get_help_sections(VOIGT_SIGMA, SETTINGS_PATH, lang=help_lang_var.get())
            chapters.delete(0, tk.END)
            for title, _heading, _content in sections:
                chapters.insert(tk.END, title)
            chapters.selection_clear(0, tk.END)
            chapters.selection_set(0)
            show_section(0)

        chapters.bind("<<ListboxSelect>>", on_select)
        refresh_language()

        buttons = ttk.Frame(win, padding=(10, 0, 10, 10))
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text=tr("help.about"), command=self.show_about, style="Small.TButton").pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(buttons, text=tr("help.close"), command=win.destroy, style="Accent.TButton").pack(side=tk.RIGHT)

    def show_about(self) -> None:
        self.show_logo_popup(title=tr("help.about_title", version=APP_VERSION), scale=2.6, click_to_close=False)

    def update_settings_payload(self) -> dict:
        from mossbauer_updater_ui import load_update_settings
        return load_update_settings(CONFIG_DIR)

    def save_update_settings_payload(self, data: dict) -> None:
        from mossbauer_updater_ui import save_update_settings
        save_update_settings(CONFIG_DIR, data, parent=self)

    def open_update_settings_dialog(self) -> None:
        from mossbauer_updater_ui import open_update_settings_dialog as _dlg
        _dlg(self, CONFIG_DIR)

    def check_for_updates(self, silent: bool = False) -> None:
        from mossbauer_updater_ui import check_for_updates as _check
        _check(self, APP_VERSION, Path(__file__).resolve().parent, CONFIG_DIR,
               silent=silent, with_checksum=True)

    def _check_requirements_background(self) -> None:
        from mossbauer_updater_ui import check_requirements_if_needed
        check_requirements_if_needed(Path(__file__).resolve().parent, CONFIG_DIR)

    def show_changelog(self) -> None:
        if CHANGELOG_PATH.exists():
            text = CHANGELOG_PATH.read_text(encoding="utf-8", errors="replace")
        elif README_PATH.exists():
            text = README_PATH.read_text(encoding="utf-8", errors="replace")
        else:
            text = tr("help.changelog_unavailable")
        self.show_text_window(tr("help.changelog"), text)

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
        canvas.create_text(*xy(59, 75), text=tr("logo.text_sextete"), fill="#dff6ff", font=("TkDefaultFont", max(8, int(8 * s))))
        return canvas

    def _refresh_distribution_tab_visibility(self, update: bool = True) -> None:
        if hasattr(self, "refresh_dist_slider_labels"):
            self.refresh_dist_slider_labels()
        if not hasattr(self, "notebook") or not hasattr(self, "dist_tab"):
            return
        if self.fit_mode_var.get() == "bhf_distribution":
            try:
                self.notebook.add(self.dist_tab, text=tr("tab.distribution_bhf"))
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
        # σ gaussiano sólo se usa con perfil Voigt → agrisarlo en Lorentziana.
        is_voigt = LINE_PROFILE_KIND == "Voigt"
        self._set_slider_enabled("voigt_sigma", is_voigt)
        check = getattr(self, "fit_sigma_check", None)
        if check is not None:
            check.configure(state=tk.NORMAL if is_voigt else tk.DISABLED)
        if not is_voigt:
            self.fit_sigma_var.set(False)
        if self.updating_sliders:
            return
        self.update_plot()

    def _add_slider(self, parent: ttk.Frame, key: str, label: str, value: float,
                    min_value: float, max_value: float, resolution: float,
                    fit_param: bool = True) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=4)

        top = ttk.Frame(frame)
        top.pack(fill=tk.X)
        label_widget = ttk.Label(top, text=label)
        label_widget.pack(side=tk.LEFT, anchor=tk.W)
        self.slider_label_widgets[key] = label_widget

        var = tk.DoubleVar(value=value)
        entry_var = tk.StringVar(value=self._format_value(key, value))
        if fit_param:
            fixed_var = tk.BooleanVar(value=False)
            fixed = ttk.Checkbutton(top, text=tr("checkbox.fixed"), variable=fixed_var)
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
        # Guardar refs para habilitar/deshabilitar (modo textura, etc.)
        widget_refs = {"slider": slider, "entry": entry, "label": label_widget}
        if fit_param:
            widget_refs["fixed"] = fixed
        if not hasattr(self, "slider_widget_refs"):
            self.slider_widget_refs = {}
        self.slider_widget_refs[key] = widget_refs

    def _format_value(self, key: str, value: float) -> str:
        base = key.split("_", 1)[-1]
        if key == "center":
            return f"{value:.5f}"
        if base == "slope":
            return f"{value:.6f}"
        if key == "vmax" or base in {"delta", "quad", "gamma1", "gamma2", "gamma3", "depth", "baseline", "int1", "int2", "int3", "texture", "beta"}:
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

        if key not in {"center", "vmax"}:
            self._simulate_enabled = True
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
                tr("msg.fit_velocity_title"),
                tr("msg.fit_velocity_info"),
            )

    def on_bhf_distribution_option_change(self) -> None:
        self.last_bhf_fit = None
        self.refresh_dist_slider_labels()
        self.update_plot()

    def refresh_dist_slider_labels(self) -> None:
        is_quad = self.dist_variable_var.get() == "ΔEQ"
        mapping = {
            "dist_bmin": ("slider.dist_bmin_quad", "slider.dist_bmin_bhf"),
            "dist_bmax": ("slider.dist_bmax_quad", "slider.dist_bmax_bhf"),
            "dist_quad": ("slider.dist_quad_inactive", "slider.dist_quad_active"),
            "dist_fixed_bhf": ("slider.dist_fixed_bhf_active", "slider.dist_fixed_bhf_inactive"),
        }
        for key, (key_quad, key_bhf) in mapping.items():
            widget = self.slider_label_widgets.get(key)
            if widget is None:
                continue
            tr_key = key_quad if is_quad else key_bhf
            try:
                widget.configure(text=tr(tr_key))
            except tk.TclError:
                pass
        # Agrisar el parámetro fijo que no se usa con la variable elegida:
        # en modo BHF el ΔEQ fijo (dist_quad) sí se usa y el BHF fijo no;
        # en modo ΔEQ es al revés.
        self._set_slider_enabled("dist_quad", is_quad is False)
        self._set_slider_enabled("dist_fixed_bhf", is_quad is True)

    def on_component_activation_change(self) -> None:
        if self.fit_mode_var.get() == "bhf_distribution" and self.dist_use_sharp_var.get():
            self.last_bhf_fit = None
        self.update_plot()

    def open_calibration_download_dialog(self) -> None:
        self.open_web_download_dialog(kind="calibraciones")

    def mark_loaded_as_calibration_quick(self) -> None:
        """Marca el fichero cargado como calibración tomando los valores actuales
        de velocidad (vmax) y desplazamiento isomérico (δ del primer sextete
        activo), sin diálogo. Pensado para el menú contextual de la caja."""
        if self.file_path is None:
            messagebox.showinfo(tr("msg.calibration_title"), tr("msg.no_file_loaded"))
            return
        vmax_val = abs(float(self.vars["vmax"].get())) if "vmax" in self.vars else None
        active_idx = next((i for i in self.sextet_enabled if self.sextet_enabled[i].get()), None)
        is_val = None
        if active_idx is not None and f"s{active_idx}_delta" in self.vars:
            is_val = float(self.vars[f"s{active_idx}_delta"].get())
        self.calibration_info = {
            "source": "local",
            "calibration_file_name": self.file_path.name,
            "calibration_file_path": str(self.file_path),
            "calibration_sample": self.file_path.stem,
            "calibration_date": None,
            "velocity_calibrated": vmax_val,
            "isomer_shift": is_val,
        }
        self.update_calibration_label()
        messagebox.showinfo(tr("msg.calibration_title"),
                            tr("msg.use_as_calib_quick_ok", name=self.file_path.name,
                               vmax=f"{vmax_val:.6g}" if vmax_val is not None else "—",
                               iso=f"{is_val:.6g}" if is_val is not None else "—"))

    def show_file_box_menu(self, event) -> None:
        """Menú contextual (clic derecho) sobre la caja del fichero/muestra."""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label=tr("context.use_as_calibration_quick"),
                         command=self.mark_loaded_as_calibration_quick)
        menu.add_command(label=tr("context.use_as_calibration_detailed"),
                         command=self.use_loaded_file_as_calibration)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def use_loaded_file_as_calibration(self) -> None:
        """Marca el fichero actualmente cargado como espectro de calibración local."""
        if self.file_path is None:
            messagebox.showinfo(tr("msg.calibration_title"), tr("msg.no_file_loaded"))
            return
        fname = self.file_path.name
        dialog = tk.Toplevel(self)
        dialog.title(tr("dialog.use_as_calibration"))
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        frm = ttk.Frame(dialog, padding=14)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text=tr("label.use_as_calib_info", name=fname),
                  wraplength=400, justify=tk.LEFT).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(frm, text=tr("label.calib_sample_name")).grid(
            row=1, column=0, sticky="e", padx=(0, 6), pady=3)
        sample_var = tk.StringVar(value=self.file_path.stem)
        ttk.Entry(frm, textvariable=sample_var, width=28).grid(
            row=1, column=1, sticky="ew", pady=3)

        # Vmax: pre-rellena desde el valor actual del slider
        current_vmax_str = ""
        if "vmax" in self.vars:
            current_vmax_str = f"{self.vars['vmax'].get():.6g}"

        ttk.Label(frm, text=tr("label.calib_vmax")).grid(
            row=2, column=0, sticky="e", padx=(0, 6), pady=3)
        vmax_var = tk.StringVar(value=current_vmax_str)
        ttk.Entry(frm, textvariable=vmax_var, width=14).grid(
            row=2, column=1, sticky="w", pady=3)
        ttk.Label(frm, text=tr("label.calib_vmax_hint"),
                  font=("TkSmallCaptionFont",)).grid(
            row=3, column=1, sticky="w", pady=(0, 4))

        # IS (delta): pre-rellena desde el primer sextete activo de la sesión
        active_idx = next((i for i in (1, 2, 3) if self.sextet_enabled[i].get()), None)
        current_is_str = ""
        if active_idx is not None:
            delta_key = f"s{active_idx}_delta"
            if delta_key in self.vars:
                current_is_str = f"{self.vars[delta_key].get():.6g}"

        ttk.Label(frm, text=tr("label.calib_is")).grid(
            row=4, column=0, sticky="e", padx=(0, 6), pady=3)
        is_var = tk.StringVar(value=current_is_str)
        ttk.Entry(frm, textvariable=is_var, width=14).grid(
            row=4, column=1, sticky="w", pady=3)

        def confirm() -> None:
            vmax_text = vmax_var.get().strip().replace(",", ".")
            is_text = is_var.get().strip().replace(",", ".")

            vmax_val: float | None = None
            if vmax_text:
                try:
                    vmax_val = abs(float(vmax_text))
                except ValueError:
                    messagebox.showerror(tr("msg.calibration_title"),
                                         tr("msg.use_as_calib_invalid_vmax"))
                    return

            is_val: float | None = None
            if is_text:
                try:
                    is_val = float(is_text)
                except ValueError:
                    messagebox.showerror(tr("msg.calibration_title"),
                                         tr("msg.use_as_calib_invalid_is"))
                    return

            self.calibration_info = {
                "source": "local",
                "calibration_file_name": fname,
                "calibration_file_path": str(self.file_path),
                "calibration_sample": sample_var.get().strip() or self.file_path.stem,
                "calibration_date": None,
                "velocity_calibrated": vmax_val,
                "isomer_shift": is_val,
            }

            if vmax_val is not None:
                self.updating_sliders = True
                self.vars["vmax"].set(vmax_val)
                self.entry_vars["vmax"].set(self._format_value("vmax", vmax_val))
                self.updating_sliders = False
                self.refold_data()
                self.update_plot()

            self.update_calibration_label()
            dialog.destroy()
            messagebox.showinfo(tr("msg.calibration_title"),
                                tr("msg.use_as_calib_ok", name=fname))

        buttons = ttk.Frame(frm)
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        ttk.Button(buttons, text=tr("button.cancel"),
                   command=dialog.destroy).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(buttons, text=tr("button.ok"), style="Accent.TButton",
                   command=confirm).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        dialog.wait_window()

    def update_calibration_label(self) -> None:
        """Actualiza el widget de calibración activa en el panel de fichero."""
        info = self.calibration_info
        if not info:
            self.calib_label_var.set("")
            self.calib_label.pack_forget()
            return
        source = info.get("source", "?")
        sample = info.get("calibration_sample") or info.get("calibration_file_name") or "?"
        title = tr("msg.calibration_title")
        line1 = f"{title} [{source}]:  {sample}"
        parts2: list[str] = []
        vmax = info.get("velocity_calibrated")
        if vmax not in (None, ""):
            try:
                parts2.append(f"Vmax: {float(vmax):.6g} mm/s")
            except (TypeError, ValueError):
                pass
        is_val = info.get("isomer_shift")
        if is_val not in (None, ""):
            try:
                parts2.append(f"IS: {float(is_val):.6g} mm/s")
            except (TypeError, ValueError):
                pass
        text = line1 + ("\n" + "   ".join(parts2) if parts2 else "")
        self.calib_label_var.set(text)
        self.calib_label.pack(anchor=tk.W, fill=tk.X, pady=(0, 6))


    def open_web_download_dialog(self, kind: str = "mossbauer") -> None:
        """Lista y descarga medidas o calibraciones usando la API REST del laboratorio."""
        try:
            from mossbauer_api_client import MatelecLabClient, DEFAULT_BASE_URL
        except Exception as exc:
            messagebox.showerror(
                tr("msg.web_title"),
                tr("msg.web_api_error", error=str(exc)),
            )
            return

        is_calibraciones = (kind == "calibraciones")
        creds = load_credentials()
        saved_dirs = creds.get("download_dirs", {})
        default_dir_name = "calibraciones" if is_calibraciones else "medidas"
        effective_dir = saved_dirs.get(kind, str(Path.home() / "Mossbauer" / default_dir_name))
        base_url = creds.get("api_base") or DEFAULT_BASE_URL

        dialog = tk.Toplevel(self)
        dialog.title(tr("dialog.web_download_calib") if is_calibraciones
                     else tr("dialog.web_download_meas"))
        dialog.geometry("820x600")
        dialog.transient(self)
        dialog.configure(background="#edf4fb")

        items: list[dict] = []          # medidas o calibraciones cargadas
        displayed: list[dict] = []      # subconjunto visible tras el filtro

        frm = ttk.Frame(dialog, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text=tr("label.server")).grid(row=0, column=0, sticky="w", pady=3)
        base_var = tk.StringVar(value=base_url)
        ttk.Entry(frm, textvariable=base_var).grid(row=0, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(frm, text=tr("label.username")).grid(row=1, column=0, sticky="w", pady=3)
        user_var = tk.StringVar(value=creds.get("username", ""))
        ttk.Entry(frm, textvariable=user_var).grid(row=1, column=1, sticky="ew", pady=3)

        ttk.Label(frm, text=tr("label.password")).grid(row=2, column=0, sticky="w", pady=3)
        pass_var = tk.StringVar(value=creds.get("password", ""))
        ttk.Entry(frm, textvariable=pass_var, show="•").grid(row=2, column=1, sticky="ew", pady=3)
        remember_var = tk.BooleanVar(value=bool(creds.get("username") or creds.get("token")))
        ttk.Checkbutton(
            frm,
            text=tr("checkbox.remember_credentials"),
            variable=remember_var,
        ).grid(row=2, column=2, sticky="w", padx=(8, 0), pady=3)

        ttk.Label(frm, text=tr("label.dest_folder")).grid(row=3, column=0, sticky="w", pady=3)
        dest_dir_var = tk.StringVar(value=effective_dir)
        ttk.Entry(frm, textvariable=dest_dir_var).grid(row=3, column=1, sticky="ew", pady=3)

        def choose_dest_dir() -> None:
            current = dest_dir_var.get().strip() or str(Path.home())
            selected = filedialog.askdirectory(
                title=tr("dialog.select_folder"),
                initialdir=current if Path(current).exists() else str(Path.home()),
                mustexist=False,
            )
            if selected:
                dest_dir_var.set(selected)

        def create_subfolder() -> None:
            base = dest_dir_var.get().strip() or str(Path.home() / "Mossbauer")
            name = simpledialog.askstring(tr("dialog.create_folder_title"), tr("dialog.create_folder_prompt"), parent=dialog)
            if not name:
                return
            safe = re.sub(r"[^\w.()+\- ]+", "_", name, flags=re.UNICODE).strip()
            if not safe:
                return
            path = Path(base) / safe
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                messagebox.showerror(tr("msg.folder_title"), tr("msg.folder_create_error", error=str(exc)))
                return
            dest_dir_var.set(str(path))
            status_var.set(tr("status.dest_folder_set", path=str(path)))

        dir_buttons = ttk.Frame(frm)
        dir_buttons.grid(row=3, column=2, sticky="ew", padx=(8, 0), pady=3)
        ttk.Button(dir_buttons, text=tr("button.choose"), command=choose_dest_dir, style="Small.TButton").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(dir_buttons, text=tr("button.create"), command=create_subfolder, style="Small.TButton").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        with_calib_var = tk.BooleanVar(value=not is_calibraciones)
        if not is_calibraciones:
            ttk.Checkbutton(
                frm,
                text=tr("checkbox.download_calibration_too"),
                variable=with_calib_var,
            ).grid(row=4, column=1, columnspan=2, sticky="w", pady=(0, 3))

        status_var = tk.StringVar(value=tr("status.web_initial"))
        ttk.Label(frm, textvariable=status_var, style="Subtitle.TLabel", wraplength=760).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(4, 8))

        search_var = tk.StringVar()
        ttk.Label(frm, text=tr("label.search")).grid(row=6, column=0, sticky="w", pady=(0, 4))
        search_entry = ttk.Entry(frm, textvariable=search_var)
        search_entry.grid(row=6, column=1, sticky="ew", pady=(0, 4))
        ttk.Button(frm, text=tr("button.clear"), command=lambda: search_var.set(""),
                   style="Small.TButton").grid(row=6, column=2, sticky="ew", padx=(8, 0), pady=(0, 4))

        listbox = tk.Listbox(frm, height=12, activestyle="dotbox")
        listbox.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=4)
        frm.rowconfigure(7, weight=1)

        debug_box = tk.Text(frm, height=7, wrap=tk.WORD, background="#111827",
                            foreground="#d1fae5", insertbackground="#d1fae5",
                            font=("TkFixedFont", 9))
        debug_box.grid(row=8, column=0, columnspan=3, sticky="nsew", pady=(6, 0))

        def debug(msg: str) -> None:
            debug_box.insert(tk.END, msg.rstrip() + "\n")
            debug_box.see(tk.END)
            dialog.update_idletasks()

        def describe(item: dict) -> str:
            sample = item.get("sample") or tr("text.no_sample")
            date = item.get("date") or tr("text.no_date")
            env = item.get("environment") or item.get("temperature") or "-"
            vcal = item.get("velocity_calibrated")
            vcal_txt = f" · v={vcal}" if vcal not in (None, "") else ""
            return f"{sample} · {date} · {env}{vcal_txt}  [id {item.get('id')}]"

        def apply_search_filter(*_args) -> None:
            nonlocal displayed
            words = [w for w in search_var.get().lower().split() if w]
            displayed = []
            listbox.delete(0, tk.END)
            for item in items:
                haystack = " ".join(str(v) for v in item.values()).lower()
                if all(w in haystack for w in words):
                    displayed.append(item)
                    listbox.insert(tk.END, describe(item))
            if items:
                status_var.set(tr("status.search_results", n=len(displayed), total=len(items)))

        search_var.trace_add("write", apply_search_filter)

        def build_client():
            """Cliente autenticado: reusa el token guardado si vale, si no hace login."""
            base = base_var.get().strip() or DEFAULT_BASE_URL
            token = creds.get("token")
            client = MatelecLabClient(base_url=base, token=token)
            if token and client.token_is_valid():
                debug("Token guardado válido; no hace falta login.")
                return client
            user = user_var.get().strip()
            password = pass_var.get()
            if not user or not password:
                raise RuntimeError("Falta usuario o contraseña para obtener el token.")
            debug(f"Obteniendo token nuevo para el usuario '{user}'...")
            client.login(user, password)
            creds["token"] = client.token
            debug("Token obtenido correctamente.")
            return client

        def persist_credentials() -> None:
            if not remember_var.get():
                return
            creds["username"] = user_var.get().strip()
            creds["password"] = pass_var.get()
            creds["api_base"] = base_var.get().strip() or DEFAULT_BASE_URL
            dirs = creds.setdefault("download_dirs", {})
            if dest_dir_var.get().strip():
                dirs[kind] = dest_dir_var.get().strip()
            save_credentials(creds)
            debug("Credenciales y token guardados localmente.")

        def do_list() -> None:
            nonlocal items
            listbox.delete(0, tk.END)
            try:
                client = build_client()
            except Exception as exc:
                status_var.set(tr("status.web_auth_error", error=str(exc)))
                debug(f"ERROR autenticación: {type(exc).__name__}: {exc}")
                return
            persist_credentials()
            status_var.set(tr("status.web_loading"))
            dialog.update_idletasks()
            try:
                if is_calibraciones:
                    items = list(client.iter_calibraciones())
                else:
                    items = list(client.iter_medidas())
            except Exception as exc:
                status_var.set(tr("status.web_list_error", error=f"{type(exc).__name__}: {exc}"))
                debug(f"ERROR: {type(exc).__name__}: {exc}")
                return
            debug(f"Recibidos {len(items)} elementos de la API.")
            apply_search_filter()
            if items:
                status_var.set(tr("status.web_items_count", n=len(items)))
            else:
                status_var.set(tr("status.web_no_items"))

        def do_download() -> None:
            if not (displayed and listbox.curselection()):
                status_var.set(tr("status.web_select_item"))
                return
            item = displayed[listbox.curselection()[0]]
            dest_dir = dest_dir_var.get().strip() or str(Path.home() / "Mossbauer")
            try:
                client = build_client()
            except Exception as exc:
                status_var.set(tr("status.web_auth_error", error=str(exc)))
                debug(f"ERROR autenticación: {type(exc).__name__}: {exc}")
                return
            persist_credentials()
            try:
                if is_calibraciones:
                    path = client.download_calibracion_datafile(item["id"], dest_dir)
                    debug(f"Calibración descargada: {path}")
                else:
                    path = client.download_datafile(item["id"], dest_dir)
                    debug(f"Medida descargada: {path}")
            except Exception as exc:
                status_var.set(tr("status.web_download_error", error=f"{type(exc).__name__}: {exc}"))
                debug(f"ERROR: {type(exc).__name__}: {exc}")
                return
            self.load_ws5(Path(path))
            if not is_calibraciones:
                try:
                    self._apply_web_calibration(client, item, dest_dir,
                                                with_calib_var.get(), debug)
                except Exception as exc:
                    debug(f"Aviso: no se pudo asociar la calibración: {exc}")
            status_var.set(tr("status.web_downloaded", path=str(path)))
            dialog.destroy()

        buttons = ttk.Frame(frm)
        buttons.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        ttk.Button(buttons, text=tr("button.list"), command=do_list).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(buttons, text=tr("button.download"), command=do_download, style="Accent.TButton").grid(
            row=0, column=1, sticky="ew", padx=(5, 0))

    def _apply_web_calibration(self, client, medida: dict, dest_dir: str,
                               download_file: bool, debug) -> None:
        """Asocia a la medida recién cargada su calibración de la web: guarda la
        trazabilidad en self.calibration_info y aplica el Vmax calibrado."""
        calib_id = medida.get("calibration_id")
        if not calib_id:
            debug("La medida no tiene calibración asociada en la web.")
            return
        calib = client.get_calibracion_de_medida(medida["id"])
        if not calib:
            debug("La API no devolvió la calibración asociada.")
            return
        info = {
            "source": "web_api",
            "medida_id": medida.get("id"),
            "calibration_id": calib.get("id", calib_id),
            "calibration_sample": calib.get("sample"),
            "calibration_date": calib.get("date"),
            "velocity_calibrated": calib.get("velocity_calibrated"),
            "isomer_shift": calib.get("isomer_shift"),
            "calibration_file_name": None,
            "calibration_file_path": None,
        }
        if download_file:
            try:
                cpath = client.download_calibracion_datafile(calib["id"], dest_dir)
                info["calibration_file_name"] = Path(cpath).name
                info["calibration_file_path"] = str(cpath)
                debug(f"Calibración asociada descargada: {cpath}")
            except Exception as exc:
                debug(f"No se pudo descargar el fichero de calibración: {exc}")
        self.calibration_info = info
        self.update_calibration_label()
        vmax = info.get("velocity_calibrated")
        if vmax in (None, ""):
            debug("La calibración no trae velocity_calibrated; no se aplica Vmax.")
            return
        try:
            vmax = abs(float(vmax))
        except (TypeError, ValueError):
            debug(f"velocity_calibrated no numérico: {vmax!r}")
            return
        self.updating_sliders = True
        self.vars["vmax"].set(vmax)
        self.entry_vars["vmax"].set(self._format_value("vmax", vmax))
        self.updating_sliders = False
        self.refold_data()
        self.update_plot()
        debug(f"Vmax aplicado desde la calibración: {vmax}")

    def open_web_upload_analysis_dialog(self) -> None:
        """Sube el JSON de la sesión actual como nueva versión de análisis vía API."""
        try:
            from mossbauer_api_client import MatelecLabClient, DEFAULT_BASE_URL
        except Exception as exc:
            messagebox.showerror(
                tr("msg.web_title"),
                tr("msg.web_api_error", error=str(exc)),
            )
            return

        creds = load_credentials()
        base_url = creds.get("api_base") or DEFAULT_BASE_URL

        dialog = tk.Toplevel(self)
        dialog.title(tr("dialog.upload_session"))
        dialog.geometry("780x540")
        dialog.transient(self)
        dialog.configure(background="#edf4fb")

        frm = ttk.Frame(dialog, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text=tr("label.server")).grid(row=0, column=0, sticky="w", pady=3)
        base_var = tk.StringVar(value=base_url)
        ttk.Entry(frm, textvariable=base_var).grid(row=0, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(frm, text=tr("label.username")).grid(row=1, column=0, sticky="w", pady=3)
        user_var = tk.StringVar(value=creds.get("username", ""))
        ttk.Entry(frm, textvariable=user_var).grid(row=1, column=1, sticky="ew", pady=3)

        ttk.Label(frm, text=tr("label.password")).grid(row=2, column=0, sticky="w", pady=3)
        pass_var = tk.StringVar(value=creds.get("password", ""))
        ttk.Entry(frm, textvariable=pass_var, show="•").grid(row=2, column=1, sticky="ew", pady=3)
        remember_var = tk.BooleanVar(value=bool(creds.get("username") or creds.get("token")))
        ttk.Checkbutton(frm, text=tr("checkbox.remember_credentials_short"), variable=remember_var).grid(
            row=2, column=2, sticky="w", padx=(8, 0), pady=3)

        default_name = (self.file_path.stem if self.file_path else "mossbauer") + "_session.json"
        ttk.Label(frm, text=tr("label.json_name")).grid(row=3, column=0, sticky="w", pady=3)
        name_var = tk.StringVar(value=default_name)
        ttk.Entry(frm, textvariable=name_var).grid(row=3, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(frm, text=tr("label.measurement_id")).grid(row=4, column=0, sticky="w", pady=3)
        medida_id_var = tk.StringVar(value="")
        ttk.Entry(frm, textvariable=medida_id_var).grid(row=4, column=1, sticky="ew", pady=3)

        ttk.Label(frm, text=tr("label.note")).grid(row=5, column=0, sticky="nw", pady=3)
        note_text = tk.Text(frm, height=3, wrap=tk.WORD, background="#ffffff",
                            foreground="#17202a", font=("TkDefaultFont", 9))
        note_text.grid(row=5, column=1, columnspan=2, sticky="ew", pady=3)

        status_var = tk.StringVar(value=tr("status.upload_initial"))
        ttk.Label(frm, textvariable=status_var, style="Subtitle.TLabel", wraplength=740).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(4, 8))

        debug_box = tk.Text(frm, height=14, wrap=tk.WORD, background="#111827",
                            foreground="#d1fae5", insertbackground="#d1fae5",
                            font=("TkFixedFont", 9))
        debug_box.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(6, 0))
        frm.rowconfigure(7, weight=1)

        def debug(msg: str) -> None:
            debug_box.insert(tk.END, msg.rstrip() + "\n")
            debug_box.see(tk.END)
            dialog.update_idletasks()

        def build_client():
            base = base_var.get().strip() or DEFAULT_BASE_URL
            token = creds.get("token")
            client = MatelecLabClient(base_url=base, token=token)
            if token and client.token_is_valid():
                debug("Token guardado válido.")
                return client
            user = user_var.get().strip()
            password = pass_var.get()
            if not user or not password:
                raise RuntimeError("Falta usuario o contraseña para obtener el token.")
            debug(f"Obteniendo token para '{user}'...")
            client.login(user, password)
            creds["token"] = client.token
            debug("Token obtenido.")
            return client

        def persist_credentials() -> None:
            if not remember_var.get():
                return
            creds["username"] = user_var.get().strip()
            creds["password"] = pass_var.get()
            creds["api_base"] = base_var.get().strip() or DEFAULT_BASE_URL
            save_credentials(creds)
            debug("Credenciales y token guardados localmente.")

        def find_medida() -> None:
            if not self.file_path:
                status_var.set(tr("status.no_file_loaded"))
                return
            try:
                client = build_client()
            except Exception as exc:
                status_var.set(tr("status.web_auth_error", error=str(exc)))
                debug(f"ERROR autenticación: {type(exc).__name__}: {exc}")
                return
            persist_credentials()
            status_var.set(tr("status.searching_measurement", name=self.file_path.name))
            dialog.update_idletasks()
            try:
                medida = client.find_medida_by_filename(self.file_path.name)
            except Exception as exc:
                status_var.set(tr("status.measurement_search_error", error=f"{type(exc).__name__}: {exc}"))
                debug(f"ERROR: {type(exc).__name__}: {exc}")
                return
            if not medida:
                status_var.set(tr("status.measurement_not_found", name=self.file_path.name))
                return
            medida_id_var.set(str(medida["id"]))
            status_var.set(tr("status.measurement_found", id=medida['id'], sample=medida.get('sample', '')))
            debug(f"Medida {medida['id']}: {medida.get('sample')} ({medida.get('date')})")

        def upload() -> None:
            medida_id = medida_id_var.get().strip()
            if not medida_id:
                status_var.set(tr("status.upload_no_id"))
                return
            upload_name = name_var.get().strip() or default_name
            if not upload_name.lower().endswith(".json"):
                upload_name += ".json"
            try:
                client = build_client()
            except Exception as exc:
                status_var.set(tr("status.web_auth_error", error=str(exc)))
                debug(f"ERROR autenticación: {type(exc).__name__}: {exc}")
                return
            persist_credentials()
            note = note_text.get("1.0", tk.END).strip()
            session_data = self.session_payload()
            if note:
                session_data["web_analysis_note"] = note
            payload = json.dumps(session_data, ensure_ascii=False, indent=2).encode("utf-8")
            try:
                result = client.upload_analysis(medida_id, data=payload,
                                                filename=upload_name, note=note)
            except ValueError as exc:
                status_var.set(tr("status.upload_rejected", error=str(exc)))
                debug(str(exc))
                return
            except Exception as exc:
                status_var.set(tr("status.upload_error", error=f"{type(exc).__name__}: {exc}"))
                debug(f"ERROR: {type(exc).__name__}: {exc}")
                return
            version = result.get("version", "?")
            status_var.set(tr("status.upload_done", name=upload_name, version=version))
            debug(f"OK: {result}")
            messagebox.showinfo(
                tr("msg.web_title"),
                tr("msg.upload_success", id=medida_id, version=version))

        ttk.Button(frm, text=tr("button.find_by_filename"), command=find_medida,
                   style="Small.TButton").grid(row=4, column=2, sticky="ew", padx=(8, 0), pady=3)

        buttons = ttk.Frame(frm)
        buttons.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        ttk.Button(buttons, text=tr("button.upload"), command=upload, style="Accent.TButton").grid(
            row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(buttons, text=tr("button.close"), command=dialog.destroy).grid(
            row=0, column=1, sticky="ew", padx=(5, 0))

    def open_file(self) -> None:
        filename = filedialog.askopenfilename(
            title=tr("dialog.open_file"),
            filetypes=[
                (tr("filetype.ws5_adt"), "*.ws5 *.WS5 *.adt *.ADT"),
                (tr("filetype.ws5"), "*.ws5 *.WS5"),
                (tr("filetype.adt"), "*.adt *.ADT"),
                (tr("filetype.all"), "*"),
            ],
        )
        if filename:
            self.load_ws5(Path(filename))

    def load_ws5(self, path: Path) -> None:
        try:
            counts = read_ws5_counts(path)
        except Exception as exc:
            messagebox.showerror(tr("msg.load_error"), str(exc))
            return
        self.file_path = path
        self.current_file_var.set(path.name)
        self.counts = counts
        # La calibración es independiente del fichero de datos: persiste hasta
        # que el usuario indique explícitamente otra (diálogo local o descarga web).
        center = read_normos_folding_point(path)
        if center is None:
            center = find_best_integer_or_half_center(counts)
        self.updating_sliders = True
        self.vars["center"].set(center)
        self.entry_vars["center"].set(self._format_value("center", center))
        self.updating_sliders = False
        self.refold_data()
        self.guess_initial_parameters()
        # Datos recién cargados: no simular hasta tocar un parámetro o ajustar.
        self._simulate_enabled = False
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
                p + "int1": 3.0,
                p + "int2": 2.0,
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

        # Suavizado grueso: estimación de ruido y máximo global.
        coarse_smooth = self._smooth_1d(absorption, max(5, absorption.size // 80))
        max_abs = float(np.nanmax(coarse_smooth)) if coarse_smooth.size else 0.0
        if max_abs <= 0:
            return [], float(baseline0), float(slope)
        diff_noise = np.diff(coarse_smooth)
        noise = 1.4826 * float(np.median(np.abs(diff_noise - np.median(diff_noise)))) if diff_noise.size else 0.0

        # Suavizado fino: mejor resolución de hombros entre picos solapados.
        fine_win = max(3, absorption.size // 120)
        if fine_win % 2 == 0:
            fine_win += 1
        fine_smooth = self._smooth_1d(absorption, fine_win)

        dv = abs(float(v[1] - v[0])) if v.size > 1 else 0.05
        min_dist_ch = max(3, int(0.15 / dv))

        # Umbral de altura al 6% (era 10%); los hombros de sextetos solapados
        # suelen ser 5-8% del máximo global.
        height_thr = max(0.06 * max_abs, 4.0 * noise, 5e-4)
        # Prominencia mínima: el pico debe sobresalir al menos un 5% del máximo
        # sobre los valles que lo flanquean (filtra ruido sin eliminar hombros).
        prom_thr = max(0.05 * max_abs, 2.5 * noise, 3e-4)

        from scipy.signal import find_peaks as _find_peaks
        peak_idxs, _ = _find_peaks(fine_smooth, height=height_thr,
                                   prominence=prom_thr, distance=min_dist_ch)

        peaks: list[dict[str, float]] = []
        min_distance = max(0.12, 2.0 * dv)
        for i in peak_idxs:
            half = 0.5 * fine_smooth[i]
            left = int(i)
            while left > 0 and fine_smooth[left] > half:
                left -= 1
            right = int(i)
            while right < fine_smooth.size - 1 and fine_smooth[right] > half:
                right += 1
            width = abs(float(v[right] - v[left])) if right > left else min_distance
            peaks.append({"i": float(i), "pos": float(v[i]),
                          "depth": float(absorption[i]),
                          "smooth_depth": float(fine_smooth[i]), "width": width})

        # Quitar duplicados muy cercanos quedándonos con el más profundo.
        selected: list[dict[str, float]] = []
        for peak in sorted(peaks, key=lambda p: p["smooth_depth"], reverse=True):
            if all(abs(peak["pos"] - q["pos"]) >= min_distance for q in selected):
                selected.append(peak)
        selected = sorted(selected[:15], key=lambda p: p["pos"])
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
                        local_best = (rms5, delta5, scale5, missing)
                assert local_best is not None
                rms, delta, scale, missing_idx = local_best
                bhf = scale * BHF_DEFAULT_T
                score = rms
                if 10.0 <= bhf <= 60.0 and (best is None or score < best[0]):
                    widths = [p["width"] for p in sub]
                    # Profundidad por línea / peso relativo (W = [3,2,1,1,2,3]),
                    # quitando la línea no detectada, para no sobre-tirar.
                    weights5 = np.delete(np.array([3.0, 2.0, 1.0, 1.0, 2.0, 3.0]), missing_idx)
                    depths = np.array([p["depth"] for p in sub], dtype=float)
                    depth_est = float(np.median(depths / weights5))
                    best = (score, list(sub), float(delta), float(bhf), float(np.median(widths)), depth_est)
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
                weights = np.array([3.0, 2.0, 1.0, 1.0, 2.0, 3.0], dtype=float)
                depths = np.array([p["depth"] for p in sub], dtype=float)
                depth_est = float(np.median(depths / weights))
                best = (score, list(sub), float(delta), float(bhf), float(np.median([p["width"] for p in sub])), depth_est)
        if best is None:
            return None
        score, sub, delta, bhf, width, depth = best
        if score > max(0.45, 0.10 * max(1.0, abs(bhf / BHF_DEFAULT_T))):
            return None
        return sub, delta, bhf, width, depth

    def _try_split_peaks_for_sextet(self, peaks: list[dict[str, float]]) -> tuple | None:
        """Para 4-5 picos detectados, detecta fusiones e inserta picos virtuales.

        Útil cuando dos líneas solapadas del sexteto se detectan como un único
        pico más ancho/profundo (caso 6+4→6+6 o 6+5→6+6).
        """
        n = len(peaks)
        if n < 4 or n >= 6:
            return None

        from itertools import combinations as _comb

        median_width = float(np.median([p["width"] for p in peaks]))
        median_depth = float(np.median([p["depth"] for p in peaks]))

        def is_normal(pk: dict) -> bool:
            return pk["width"] <= median_width * 1.25 and pk["depth"] <= median_depth * 1.40

        normal_peaks = [p for p in peaks if is_normal(p)]
        if len(normal_peaks) < 2:
            normal_peaks = sorted(peaks, key=lambda p: p["width"])[:2]

        narrow_tol = max(median_width * 0.5, 0.20)
        next_vid = max(p["i"] for p in peaks) + 1.0

        best_result = None
        best_score = -1

        seen: set[tuple] = set()
        for pk_a, pk_b in _comb(sorted(normal_peaks, key=lambda p: p["pos"]), 2):
            span_obs = abs(pk_b["pos"] - pk_a["pos"])
            if span_obs < 0.5:
                continue
            for la in range(6):
                for lb in range(la + 1, 6):
                    span_ref = LINE_POS_33T[lb] - LINE_POS_33T[la]
                    if abs(span_ref) < 0.3:
                        continue
                    scale = span_obs / span_ref
                    bhf_est = scale * BHF_DEFAULT_T
                    if not (10.0 <= bhf_est <= 60.0):
                        continue
                    delta = pk_a["pos"] - scale * LINE_POS_33T[la]
                    pred_all = delta + scale * LINE_POS_33T

                    if max(abs(pk_a["pos"] - pred_all[la]),
                           abs(pk_b["pos"] - pred_all[lb])) > 0.18:
                        continue

                    key = (round(bhf_est, 1), round(delta, 2))
                    if key in seen:
                        continue
                    seen.add(key)

                    augmented = list(peaks)
                    vid = next_vid
                    virtual_added = 0
                    for pred_pos in pred_all:
                        if any(abs(p["pos"] - pred_pos) < narrow_tol and is_normal(p)
                               for p in peaks):
                            continue
                        for pk in sorted(peaks, key=lambda p: abs(p["pos"] - pred_pos)):
                            if abs(pk["pos"] - pred_pos) > pk["width"] * 0.7:
                                break
                            if not is_normal(pk):
                                augmented.append({
                                    "i": vid,
                                    "pos": float(pred_pos),
                                    "depth": pk["depth"] * 0.45,
                                    "smooth_depth": pk["smooth_depth"] * 0.45,
                                    "width": pk["width"] * 0.65,
                                })
                                vid += 1.0
                                virtual_added += 1
                                break

                    if virtual_added == 0:
                        continue

                    result = self._best_sextet_from_peaks(augmented)
                    if result is None:
                        continue

                    _, delta_r, bhf_r, _, _ = result
                    scale_r = bhf_r / BHF_DEFAULT_T
                    pred_r = delta_r + scale_r * LINE_POS_33T
                    score = sum(
                        1 for pk in peaks if not is_normal(pk)
                        and sum(1 for pp in pred_r
                                if abs(pk["pos"] - pp) < pk["width"] * 0.65) >= 2
                    )
                    if score > best_score:
                        best_score = score
                        best_result = result

        return best_result

    def _try_2peak_sextet_estimate(
        self, peaks: list[dict[str, float]]
    ) -> tuple[list[dict[str, float]], float, float, float, float] | None:
        """Estima BHF y δ cuando solo quedan 2 picos tras identificar el primer sexteto.

        Prueba los pares exteriores adyacentes (0,1) y (4,5) del patrón Fe-57.
        Solo acepta si BHF ∈ [25,60] T, |δ| ≤ 1.5 mm/s y ambos picos están
        en el mismo semiplano de velocidades.
        """
        if len(peaks) != 2:
            return None
        from core.constants import _BASE_POSITIONS
        p = sorted(peaks, key=lambda x: x["pos"])
        p0_pos, p1_pos = p[0]["pos"], p[1]["pos"]
        obs_spacing = p1_pos - p0_pos
        if obs_spacing < 0.5:
            return None

        b0, b1 = float(_BASE_POSITIONS[0]), float(_BASE_POSITIONS[1])
        b4, b5 = float(_BASE_POSITIONS[4]), float(_BASE_POSITIONS[5])
        spacing_ref = b1 - b0  # idéntico a b5 - b4 por simetría

        scale = obs_spacing / spacing_ref
        bhf = scale * 32.95
        if not (25.0 <= bhf <= 60.0):
            return None

        best: tuple | None = None
        # Pesos relativos de las líneas externas del patrón [3,2,1,1,2,3]:
        # par (0,1) → (3,2); par (4,5) → (2,3).
        if p0_pos < 0 and p1_pos < 0:
            delta_01 = p0_pos - scale * b0
            if abs(delta_01) <= 1.5:
                best = (delta_01, bhf, (3.0, 2.0))
        if p0_pos > 0 and p1_pos > 0:
            delta_45 = p0_pos - scale * b4
            if abs(delta_45) <= 1.5:
                best = (delta_45, bhf, (2.0, 3.0))

        if best is None:
            return None

        delta_est, bhf_est, (w0, w1) = best
        width = float(np.mean([p[0]["width"], p[1]["width"]]))
        # Profundidad por línea / peso, para no sobre-tirar (líneas externas W≈3).
        depth = float(np.median([p[0]["depth"] / w0, p[1]["depth"] / w1]))
        return list(p), delta_est, bhf_est, width, depth

    def _depth_profile_hint(
        self, peaks: list[dict[str, float]]
    ) -> tuple[str, list[dict[str, float]]] | None:
        """Clasifica el espectro en singlete/doblete cuando el perfil es obvio.

        - Singlete: pico dominante ≥2.5× el siguiente y dentro de ±2.5 mm/s del cero.
        - Doblete: dos picos similares (d₁ ≥ 40% d₀), el tercero mucho menor
          (d₂ < 30% d₀), ≤4 picos totales y separación 0.18–5 mm/s.
        - None: patrón no concluyente → intentar sexteto.
        """
        if not peaks:
            return None
        by_d = sorted(peaks, key=lambda p: p["smooth_depth"], reverse=True)
        d0 = by_d[0]["smooth_depth"]
        d1 = by_d[1]["smooth_depth"] if len(by_d) > 1 else 0.0
        d2 = by_d[2]["smooth_depth"] if len(by_d) > 2 else 0.0

        if d0 > 2.5 * max(d1, 1e-10) and abs(by_d[0]["pos"]) < 2.5:
            return ("Singlete", [by_d[0]])

        if (len(by_d) >= 2 and d1 >= 0.40 * d0 and d2 < 0.30 * d0
                and len(peaks) <= 4):
            pair = sorted([by_d[0], by_d[1]], key=lambda p: p["pos"])
            sep = abs(pair[1]["pos"] - pair[0]["pos"])
            if 0.18 <= sep <= 5.0:
                return ("Doblete", pair)

        return None

    def auto_guess_from_minima(self, fit_after: bool = False) -> None:
        if self.velocity is None or self.y_data is None:
            return
        peaks, baseline, slope = self.detect_absorption_minima()
        if not peaks:
            messagebox.showinfo(tr("msg.auto_minima_title"), tr("msg.auto_minima_none"))
            return

        self.fit_mode_var.set("discrete")
        self.set_fit_mode_from_menu()
        params: dict[str, float] = {"baseline": baseline, "slope": float(np.clip(slope, -1e-4, 1e-4))}
        for idx in (1, 2, 3):
            if idx > 1:
                self.sextet_enabled[idx].set(False)
            p = f"s{idx}_"
            params.update({p + "delta": 0.0, p + "quad": 0.0, p + "bhf": BHF_DEFAULT_T, p + "gamma1": 0.20, p + "gamma2": 1.0, p + "gamma3": 1.0, p + "depth": 0.005, p + "int1": 3.0, p + "int2": 2.0, p + "int3": 1.0})

        components: list[tuple[int, str, list[dict[str, float]]]] = []
        used_ids: set[int] = set()

        # Clasificación previa por perfil de profundidades: si hay un singlete
        # o doblete obvio, se coloca antes de intentar el sexteto.
        hint = self._depth_profile_hint(peaks)
        if hint is not None:
            kind_h, group_h = hint
            components.append((1, kind_h, group_h))
            pfx = "s1_"
            if kind_h == "Doblete":
                g = group_h
                params[pfx + "delta"]  = float(np.mean([g[0]["pos"], g[1]["pos"]]))
                params[pfx + "quad"]   = float(abs(g[1]["pos"] - g[0]["pos"]))
                params[pfx + "gamma1"] = float(np.clip(np.mean([x["width"] for x in g]) / 2.0, 0.04, 1.0))
                params[pfx + "gamma2"] = 1.0
                params[pfx + "depth"]  = float(np.clip(np.mean([x["depth"] for x in g]), 0.002, 0.25))
                params[pfx + "int1"]   = 1.0; params[pfx + "int2"] = 1.0
            else:
                pk = group_h[0]
                params[pfx + "delta"]  = float(pk["pos"])
                params[pfx + "gamma1"] = float(np.clip(pk["width"] / 2.0, 0.04, 1.0))
                params[pfx + "depth"]  = float(np.clip(pk["depth"], 0.002, 0.25))
                params[pfx + "int1"]   = 1.0
            used_ids.update(int(pk["i"]) for pk in group_h)
        else:
            sext = self._best_sextet_from_peaks(peaks)
            if sext is not None:
                sub, delta, bhf, width, depth = sext
                if len(sub) >= 5 and abs(sub[-1]["pos"] - sub[0]["pos"]) > 3.0:
                    components.append((1, "Sextete", sub))
                    p = "s1_"
                    params[p + "delta"] = float(np.clip(delta, -2.5, 2.5))
                    params[p + "bhf"] = float(np.clip(bhf, 20.0, 60.0))
                    params[p + "quad"] = 0.0
                    params[p + "gamma1"] = float(np.clip(width / 2.0, 0.04, 1.0))
                    params[p + "depth"] = float(np.clip(depth, 0.002, 0.25))
                    used_ids.update(int(p["i"]) for p in sub)

        remaining = [p for p in sorted(peaks, key=lambda q: q["smooth_depth"], reverse=True) if int(p["i"]) not in used_ids]
        next_idx = 2 if components else 1
        while next_idx <= 3 and remaining:
            if len(remaining) >= 5:
                sext_extra = self._best_sextet_from_peaks(remaining)
                if sext_extra is not None:
                    sub_e, delta_e, bhf_e, width_e, depth_e = sext_extra
                    if len(sub_e) >= 5 and abs(sub_e[-1]["pos"] - sub_e[0]["pos"]) > 3.0:
                        pfx = f"s{next_idx}_"
                        if next_idx > 1:
                            self.sextet_enabled[next_idx].set(True)
                        components.append((next_idx, "Sextete", sub_e))
                        params[pfx + "delta"] = float(np.clip(delta_e, -2.5, 2.5))
                        params[pfx + "bhf"] = float(np.clip(bhf_e, 20.0, 60.0))
                        params[pfx + "quad"] = 0.0
                        params[pfx + "gamma1"] = float(np.clip(width_e / 2.0, 0.04, 1.0))
                        params[pfx + "depth"] = float(np.clip(depth_e, 0.002, 0.25))
                        sub_ids = {int(pk["i"]) for pk in sub_e}
                        remaining = [p for p in remaining if int(p["i"]) not in sub_ids]
                        next_idx += 1
                        continue
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
        self._simulate_enabled = True
        self._rescale_initial_depths(params, component_range=(1, 2, 3))
        self.set_params(params)
        for idx, kind, _group in components:
            self.on_component_kind_change(idx)
        # Dejar libres los parámetros relevantes para que el ajuste posterior los refine.
        for key in self.active_param_keys():
            if key in self.fixed_vars:
                self.fixed_vars[key].set(False)
        self.update_plot()
        resumen = ", ".join(tr("text.component_kind_label", idx=idx, kind=tr(f"kind.{kind}", default=kind)) for idx, kind, _g in components)
        if fit_after:
            self.fit_current_data()
        else:
            messagebox.showinfo(tr("msg.auto_minima_title"), tr("msg.auto_minima_detected", n=len(peaks), summary=resumen))

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
        dialog.title(tr("dialog.ai_suggestion_title"))
        dialog.geometry("820x650")
        dialog.transient(self)
        frm = ttk.Frame(dialog, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        rationale = str(suggestion.get("rationale", ""))
        conf = suggestion.get("confidence", "?")
        ttk.Label(frm, text=tr("label.confidence_rationale", conf=conf, rationale=rationale), style="Subtitle.TLabel", wraplength=780).pack(anchor=tk.W, pady=(0, 6))
        txt = tk.Text(frm, wrap=tk.WORD, background="#ffffff", foreground="#17202a", font=("TkFixedFont", 9))
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert("1.0", json.dumps(suggestion, ensure_ascii=False, indent=2))
        buttons = ttk.Frame(frm)
        buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(buttons, text=tr("button.view_prompt"), command=lambda: self.show_text_window(tr("dialog.prompt_window"), prompt), style="Small.TButton").pack(side=tk.LEFT)
        ttk.Button(buttons, text=tr("button.close"), command=dialog.destroy, style="Small.TButton").pack(side=tk.RIGHT)
        ttk.Button(buttons, text=tr("button.apply_suggestion"), command=lambda: (self.apply_ai_suggestion(suggestion), dialog.destroy()), style="Accent.TButton").pack(side=tk.RIGHT, padx=(0, 6))

    def open_ollama_ai_dialog(self) -> None:
        if self.velocity is None or self.y_data is None:
            messagebox.showinfo(tr("msg.ollama_title"), tr("msg.ollama_no_spectrum"))
            return
        dialog = tk.Toplevel(self)
        dialog.title(tr("dialog.ollama_start"))
        dialog.geometry("760x520")
        dialog.transient(self)
        frm = ttk.Frame(dialog, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)
        ttk.Label(frm, text=tr("label.ollama_url")).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(frm, textvariable=self.ai_ollama_url_var).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(frm, text=tr("label.ollama_model")).grid(row=1, column=0, sticky="w", pady=3)
        model_entry = ttk.Entry(frm, textvariable=self.ai_ollama_model_var)
        model_entry.grid(row=1, column=1, sticky="ew", pady=3)
        models_var = tk.StringVar(value="")
        model_box = ttk.Combobox(frm, textvariable=models_var, values=(), state="readonly")
        model_box.grid(row=2, column=1, sticky="ew", pady=3)
        status_var = tk.StringVar(value=tr("status.ollama_initial"))
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
            status_var.set(tr("status.ollama_models_found", n=len(models)))

        def choose_model(*_args) -> None:
            if models_var.get():
                self.ai_ollama_model_var.set(models_var.get())
        models_var.trace_add("write", choose_model)

        def ask_ai() -> None:
            prompt_text = txt.get("1.0", tk.END).strip()
            self.save_settings()
            status_var.set(tr("status.ollama_querying"))
            dialog.update_idletasks()
            try:
                suggestion = self.ollama_request_json(prompt_text, self.ai_ollama_model_var.get().strip(), self.ai_ollama_url_var.get().strip())
            except Exception as exc:
                messagebox.showerror(tr("msg.ollama_title"), str(exc))
                status_var.set(tr("status.ollama_error"))
                return
            dialog.destroy()
            self.show_ai_suggestion_dialog(suggestion, prompt_text)

        buttons = ttk.Frame(frm)
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text=tr("button.list_models"), command=load_models, style="Small.TButton").pack(side=tk.LEFT)
        ttk.Button(buttons, text=tr("button.cancel"), command=dialog.destroy, style="Small.TButton").pack(side=tk.RIGHT)
        ttk.Button(buttons, text=tr("button.ask_suggestion"), command=ask_ai, style="Accent.TButton").pack(side=tk.RIGHT, padx=(0, 6))

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
        # Sextete: en modo "texture" el parámetro libre es s{i}_texture (t)
        # en lugar de int1,int2,int3; el optimizador no toca i_k.
        mode_var = getattr(self, "intensity_mode", {}).get(idx)
        if mode_var is not None and mode_var.get() == "texture" and f"s{idx}_texture" in self.vars:
            names = [n for n in SEXTET_PARAM_NAMES if n not in ("int1", "int2", "int3")]
            names.append("texture")
        else:
            names = SEXTET_PARAM_NAMES.copy()
        # Tratamiento de Kündig con β fijo: β es libre del optimizador.
        # En modo policristal, β no aplica (se integra). En 1er orden, β no se usa.
        treat = getattr(self, "quad_treatment", {}).get(idx)
        if treat is not None and treat.get() == "kundig_fixed" and f"s{idx}_beta" in self.vars:
            names.append("beta")
        return names

    def sextet_extras(self, idx: int) -> dict | None:
        """Devuelve dict de extras para pasar a sextet_absorption / component_absorption.

        None si el modo es 1er orden (comportamiento histórico).
        """
        treat_var = getattr(self, "quad_treatment", {}).get(idx)
        if treat_var is None:
            return None
        treat = treat_var.get()
        if treat == "1st_order":
            return None
        beta_deg = float(self.vars[f"s{idx}_beta"].get()) if f"s{idx}_beta" in self.vars else 0.0
        return {
            "treatment": treat,
            "beta": float(np.deg2rad(beta_deg)),
            "n_quad": 20,
        }

    def on_component_kind_change(self, idx: int) -> None:
        if self.fit_mode_var.get() == "bhf_distribution" and self.dist_use_sharp_var.get() and idx in self.active_sharp_component_indices_for_bhf():
            self.last_bhf_fit = None
        kind = self.component_kind[idx].get()
        p = f"s{idx}_"
        # Modo textura sólo aplica a sextete: si cambias a Doblete/Singlete,
        # vuelve a "free" para evitar derivaciones inaplicables.
        if kind != "Sextete" and idx in getattr(self, "intensity_mode", {}):
            self.intensity_mode[idx].set("free")
        # Lo mismo para el tratamiento Kündig: sólo tiene sentido en sextete.
        if kind != "Sextete" and idx in getattr(self, "quad_treatment", {}):
            self.quad_treatment[idx].set("1st_order")
        relevant = set(self.component_param_names(idx))
        # Marcar como fijos los parámetros que no se usan en la forma elegida.
        for name in SEXTET_PARAM_NAMES:
            key = p + name
            if key in self.fixed_vars and name not in relevant:
                self.fixed_vars[key].set(True)
        self._refresh_component_widgets(idx)
        self.update_plot()

    def _set_slider_enabled(self, key: str, enabled: bool) -> None:
        refs = getattr(self, "slider_widget_refs", {}).get(key)
        if not refs:
            return
        state = "normal" if enabled else "disabled"
        for name in ("slider", "entry", "fixed"):
            w = refs.get(name)
            if w is None:
                continue
            try:
                w.configure(state=state)
            except tk.TclError:
                pass

    def _component_relevant_params(self, idx: int) -> set[str]:
        """Conjunto de parámetros REALMENTE usados por el componente idx,
        teniendo en cuenta su tipo (sextete/doblete/singlete) y, en sextete,
        el modo de intensidades (libre/textura) y el tratamiento del cuadrupolo
        (1er orden / Kündig). Los no incluidos se deshabilitan (gris)."""
        kind = self.component_kind[idx].get()
        if kind == "Singlete":
            return {"delta", "gamma1", "depth", "int1"}
        if kind == "Doblete":
            return {"delta", "quad", "gamma1", "gamma2", "depth", "int1", "int2"}
        # Sextete
        rel = {"delta", "quad", "bhf", "gamma1", "gamma2", "gamma3", "depth"}
        mode = getattr(self, "intensity_mode", {}).get(idx)
        if mode is not None and mode.get() == "texture":
            rel.add("texture")
        else:
            rel.update({"int1", "int2", "int3"})
        treat = getattr(self, "quad_treatment", {}).get(idx)
        if treat is not None and treat.get() == "kundig_fixed":
            rel.add("beta")
        return rel

    def _refresh_component_widgets(self, idx: int | None = None) -> None:
        """Agrisa (deshabilita) todo parámetro del componente que no se use con
        el tipo y modo actuales; habilita los relevantes. Unifica el greying de
        dobletes/singletes, textura y β de Kündig. También deshabilita los combos
        de intensidades y tratamiento de cuadrupolo si el componente no es sextete."""
        if not hasattr(self, "component_kind"):
            return
        indices = [idx] if idx is not None else list(self.component_kind.keys())
        all_params = SEXTET_PARAM_NAMES + ["texture", "beta"]
        for i in indices:
            if i not in self.component_kind:
                continue
            rel = self._component_relevant_params(i)
            for name in all_params:
                self._set_slider_enabled(f"s{i}_{name}", name in rel)
            is_sextete = self.component_kind[i].get() == "Sextete"
            for combo in (getattr(self, "_intensity_combos", {}).get(i),
                          getattr(self, "_quad_combos", {}).get(i)):
                if combo is not None:
                    try:
                        combo.configure(state="readonly" if is_sextete else "disabled")
                    except tk.TclError:
                        pass

    # Alias retro-compatibles (los paneles los invocan al construir/cargar).
    def _refresh_intensity_mode_widgets(self, idx: int | None = None) -> None:
        self._refresh_component_widgets(idx)

    def _refresh_quad_treatment_widgets(self, idx: int | None = None) -> None:
        self._refresh_component_widgets(idx)

    def on_quad_treatment_change(self, idx: int) -> None:
        """Reacciona al cambio del tratamiento del cuadrupolo en un sextete."""
        self._refresh_component_widgets(idx)
        if self.fit_mode_var.get() == "bhf_distribution":
            self.last_bhf_fit = None
        self.update_plot()

    def on_intensity_mode_change(self, idx: int) -> None:
        """Reacciona al cambio de modo Libre/Textura en un sextete."""
        # Sincroniza i1,i2,i3 con el t actual al cambiar a modo textura.
        if self.intensity_mode[idx].get() == "texture" and f"s{idx}_texture" in self.vars:
            t = float(self.vars[f"s{idx}_texture"].get())
            i1, i2, i3 = self.texture_to_intensities(t)
            self.updating_sliders = True
            self.vars[f"s{idx}_int1"].set(i1)
            self.vars[f"s{idx}_int2"].set(i2)
            self.vars[f"s{idx}_int3"].set(i3)
            self.entry_vars[f"s{idx}_int1"].set(self._format_value(f"s{idx}_int1", i1))
            self.entry_vars[f"s{idx}_int2"].set(self._format_value(f"s{idx}_int2", i2))
            self.entry_vars[f"s{idx}_int3"].set(self._format_value(f"s{idx}_int3", i3))
            self.updating_sliders = False
        self._refresh_intensity_mode_widgets(idx)
        if self.fit_mode_var.get() == "bhf_distribution":
            self.last_bhf_fit = None
        self.update_plot()

    def constraint_param_keys(self) -> list[str]:
        return [k for k in self.vars if k in GLOBAL_PARAM_NAMES or re.match(r"s[123]_", k)]

    def enabled_constraints(self) -> list[dict[str, object]]:
        return [c for c in self.constraints if c.get("enabled", True) and c.get("target") in self.vars and c.get("source") in self.vars]

    def constrained_target_keys(self) -> set[str]:
        return {str(c["target"]) for c in self.enabled_constraints()}

    def apply_constraints_to_values(self, values: dict[str, float]) -> dict[str, float]:
        """Aplica target = factor*source + offset sobre un diccionario de parámetros.

        Si algún sextete está en modo "texture", deriva i1,i2,i3 a partir de
        ``s{i}_texture`` antes de las restricciones lineales: así una
        restricción puede usar i1/i2/i3 como fuente o destino.
        """
        out = self.apply_texture_mode_to_values(values)
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
        # Re-aplicar textura por si una restricción tocó t (improbable pero
        # cubre el caso de "t = f(otro)"): así i1,i2,i3 reflejan el t final.
        out = self.apply_texture_mode_to_values(out)
        return out

    def apply_constraints_to_vars(self) -> None:
        # Trabajamos también si hay sólo modo textura, no sólo constraints.
        has_texture = any(
            v.get() == "texture" and self.component_kind.get(idx) is not None
            and self.component_kind[idx].get() == "Sextete"
            for idx, v in getattr(self, "intensity_mode", {}).items()
        )
        if not self.constraints and not has_texture:
            return
        values = {k: v.get() for k, v in self.vars.items()}
        values = self.apply_constraints_to_values(values)
        # Targets que el optimizador no escribe: los del constraint lineal y los
        # i1,i2,i3 derivados por textura.
        targets = list(self.constrained_target_keys())
        if has_texture:
            for idx, mode_var in self.intensity_mode.items():
                if mode_var.get() == "texture" and self.component_kind[idx].get() == "Sextete":
                    targets += [f"s{idx}_int1", f"s{idx}_int2", f"s{idx}_int3"]
        self.updating_sliders = True
        for key in targets:
            if key in values and key in self.vars:
                self.vars[key].set(values[key])
                self.entry_vars[key].set(self._format_value(key, values[key]))
        self.updating_sliders = False

    def open_physical_presets_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(tr("dialog.presets_title"))
        dialog.transient(self)
        dialog.resizable(False, False)
        frm = ttk.Frame(dialog, padding=14)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text=tr("presets.title"), style="Title.TLabel").pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(frm, text=tr("presets.subtitle"), style="Subtitle.TLabel", wraplength=520).pack(anchor=tk.W, pady=(0, 10))

        def powder_intensities() -> None:
            for idx in (1, 2, 3):
                if self.sextet_enabled[idx].get() and self.component_kind[idx].get() == "Sextete":
                    for name, value in (("int1", 3.0), ("int2", 2.0), ("int3", 1.0)):
                        key = f"s{idx}_{name}"
                        self.vars[key].set(value)
                        self.entry_vars[key].set(self._format_value(key, value))
                        self.fixed_vars[key].set(True)
            self.update_plot()
            messagebox.showinfo(tr("msg.preset_title"), tr("msg.preset_intensities"))

        def equal_widths_within_components() -> None:
            for idx in (1, 2, 3):
                if self.sextet_enabled[idx].get():
                    for name in ("gamma2", "gamma3"):
                        key = f"s{idx}_{name}"
                        self.vars[key].set(1.0)
                        self.entry_vars[key].set(self._format_value(key, 1.0))
                        self.fixed_vars[key].set(True)
            self.update_plot()
            messagebox.showinfo(tr("msg.preset_title"), tr("msg.preset_widths"))

        def tie_delta_to_component1() -> None:
            added = 0
            for idx in (2, 3):
                if self.sextet_enabled[idx].get():
                    target = f"s{idx}_delta"
                    if not any(c.get("target") == target for c in self.constraints):
                        self.constraints.append({"enabled": True, "target": target, "source": "s1_delta", "factor": 1.0, "offset": 0.0})
                        added += 1
            self.apply_constraints_to_vars()
            self.update_plot()
            messagebox.showinfo(tr("msg.preset_title"), tr("msg.preset_delta_tied", n=added))

        def tie_width_to_component1() -> None:
            added = 0
            for idx in (2, 3):
                if self.sextet_enabled[idx].get():
                    target = f"s{idx}_gamma1"
                    if not any(c.get("target") == target for c in self.constraints):
                        self.constraints.append({"enabled": True, "target": target, "source": "s1_gamma1", "factor": 1.0, "offset": 0.0})
                        added += 1
            self.apply_constraints_to_vars()
            self.update_plot()
            messagebox.showinfo(tr("msg.preset_title"), tr("msg.preset_gamma_tied", n=added))

        ttk.Button(frm, text=tr("button.preset_powder"), command=powder_intensities, style="Accent.TButton").pack(fill=tk.X, pady=3)
        ttk.Button(frm, text=tr("button.preset_equal_widths"), command=equal_widths_within_components).pack(fill=tk.X, pady=3)
        ttk.Button(frm, text=tr("button.preset_tie_delta"), command=tie_delta_to_component1).pack(fill=tk.X, pady=3)
        ttk.Button(frm, text=tr("button.preset_tie_gamma"), command=tie_width_to_component1).pack(fill=tk.X, pady=3)
        ttk.Button(frm, text=tr("button.close"), command=dialog.destroy).pack(anchor=tk.E, pady=(10, 0))

    def open_constraints_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(tr("dialog.constraints_title"))
        dialog.geometry("920x520")
        dialog.transient(self)
        dialog.configure(background="#eaf4ff")

        frm = ttk.Frame(dialog, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text=tr("constraints.title"), style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(frm, text=tr("constraints.subtitle"), style="Subtitle.TLabel").pack(anchor=tk.W, pady=(0, 8))

        cols = ("enabled", "target", "source", "factor", "offset")
        tree = ttk.Treeview(frm, columns=cols, show="headings", height=9)
        for col, title, width in [("enabled", tr("constraints.col_active"), 70), ("target", tr("constraints.col_target"), 170), ("source", tr("constraints.col_source"), 170), ("factor", tr("constraints.col_factor"), 110), ("offset", tr("constraints.col_offset"), 110)]:
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor=tk.CENTER)
        tree.pack(fill=tk.BOTH, expand=True, pady=8)

        def refresh() -> None:
            tree.delete(*tree.get_children())
            for i, c in enumerate(self.constraints):
                tree.insert("", tk.END, iid=str(i), values=(tr("yes") if c.get("enabled", True) else tr("no"), c.get("target", ""), c.get("source", ""), c.get("factor", 1.0), c.get("offset", 0.0)))

        edit = ttk.Frame(frm)
        edit.pack(fill=tk.X, pady=(4, 0))
        keys = self.constraint_param_keys()
        target_var = tk.StringVar(value=keys[0] if keys else "")
        source_var = tk.StringVar(value=keys[0] if keys else "")
        factor_var = tk.StringVar(value="1.0")
        offset_var = tk.StringVar(value="0.0")
        enabled_var = tk.BooleanVar(value=True)
        ttk.Label(edit, text=tr("constraints.col_target")).grid(row=0, column=0, sticky="w")
        ttk.Label(edit, text=tr("constraints.col_source")).grid(row=0, column=1, sticky="w")
        ttk.Label(edit, text=tr("constraints.col_factor")).grid(row=0, column=2, sticky="w")
        ttk.Label(edit, text=tr("constraints.col_offset")).grid(row=0, column=3, sticky="w")
        ttk.Combobox(edit, textvariable=target_var, values=keys, width=20, state="readonly").grid(row=1, column=0, padx=(0, 6), sticky="ew")
        ttk.Combobox(edit, textvariable=source_var, values=keys, width=20, state="readonly").grid(row=1, column=1, padx=6, sticky="ew")
        ttk.Entry(edit, textvariable=factor_var, width=12).grid(row=1, column=2, padx=6, sticky="ew")
        ttk.Entry(edit, textvariable=offset_var, width=12).grid(row=1, column=3, padx=6, sticky="ew")
        ttk.Checkbutton(edit, text=tr("constraints.active_check"), variable=enabled_var).grid(row=1, column=4, padx=6)

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
                messagebox.showwarning(tr("msg.constraint_title"), tr("msg.constraint_same"), parent=dialog)
                return None
            if would_create_cycle(target_var.get(), source_var.get(), skip_index):
                messagebox.showwarning(tr("msg.constraint_title"), tr("msg.constraint_cycle"), parent=dialog)
                return None
            if source_var.get() in self.fixed_vars and self.fixed_vars[source_var.get()].get():
                messagebox.showinfo(tr("msg.constraint_title"), tr("msg.constraint_source_fixed"), parent=dialog)
            if target_var.get() in self.fixed_vars and not self.fixed_vars[target_var.get()].get():
                self.fixed_vars[target_var.get()].set(True)
            return {"enabled": bool(enabled_var.get()), "target": target_var.get(), "source": source_var.get(), "factor": float(factor_var.get().replace(",", ".")), "offset": float(offset_var.get().replace(",", "."))}

        def add_constraint() -> None:
            try:
                c = make_constraint()
            except ValueError:
                messagebox.showwarning(tr("msg.constraint_title"), tr("msg.constraint_numeric"), parent=dialog); return
            if c is not None:
                self.constraints.append(c); refresh(); self.apply_constraints_to_vars(); self.update_plot()

        def update_constraint() -> None:
            i = selected_index()
            if i is None:
                return
            try:
                c = make_constraint(i)
            except ValueError:
                messagebox.showwarning(tr("msg.constraint_title"), tr("msg.constraint_numeric"), parent=dialog); return
            if c is not None:
                self.constraints[i] = c; refresh(); self.apply_constraints_to_vars(); self.update_plot()

        def delete_constraint() -> None:
            i = selected_index()
            if i is not None:
                del self.constraints[i]; refresh(); self.update_plot()

        tree.bind("<<TreeviewSelect>>", load_selected)
        buttons = ttk.Frame(frm)
        buttons.pack(fill=tk.X, pady=8)
        ttk.Button(buttons, text=tr("button.add"), command=add_constraint, style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(buttons, text=tr("button.update_selected"), command=update_constraint, style="Small.TButton").pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text=tr("button.delete_selected"), command=delete_constraint, style="Small.TButton").pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text=tr("button.close"), command=dialog.destroy, style="Small.TButton").pack(side=tk.RIGHT)
        refresh()

    def active_param_keys(self) -> list[str]:
        keys = GLOBAL_PARAM_NAMES.copy()
        for idx in (1, 2, 3):
            if self.sextet_enabled[idx].get():
                keys.extend(f"s{idx}_{name}" for name in self.component_param_names(idx))
        return keys

    def active_bhf_keys(self) -> list[str]:
        return [f"s{idx}_bhf" for idx in (1, 2, 3) if self.sextet_enabled[idx].get() and self.component_kind[idx].get() == "Sextete"]

    def build_components_from_vars(self):
        if not self.updating_sliders:
            # apply_constraints_to_vars también re-deriva i1,i2,i3 de textura.
            self.apply_constraints_to_vars()
        components = []
        for idx in (1, 2, 3):
            if not self.sextet_enabled[idx].get():
                continue
            p = f"s{idx}_"
            params = np.array([self.vars[p + name].get() for name in SEXTET_PARAM_NAMES], dtype=float)
            kind = self.component_kind[idx].get()
            extras = self.sextet_extras(idx) if kind == "Sextete" else None
            if extras is not None:
                components.append((kind, params, extras))
            else:
                components.append((kind, params))
        return components

    def component_area_from_params(self, kind: str, p: np.ndarray) -> float:
        """Área integrada numérica de absorción del componente.

        Se integra el perfil real usado en el ajuste sobre una malla de velocidad.
        Así los porcentajes son consistentes tanto para Lorentziana como para
        Voigt y para singlete/doblete/sextete.
        """
        if self.velocity is not None and self.velocity.size > 1:
            vmin, vmax = float(np.min(self.velocity)), float(np.max(self.velocity))
            n = max(2000, int(self.velocity.size) * 8)
            v = np.linspace(vmin, vmax, n)
        else:
            v = np.linspace(-12.0, 12.0, 4000)
        absorption = np.maximum(component_absorption(v, kind, p), 0.0)
        return float(np.trapezoid(absorption, v))

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
        # Tocar un parámetro del modelo (no la calibración) activa la simulación.
        if key not in {"center", "vmax"}:
            self._simulate_enabled = True
        if key == "voigt_sigma":
            global VOIGT_SIGMA
            VOIGT_SIGMA = self.vars["voigt_sigma"].get()
        if key.startswith("dist_") or (self.fit_mode_var.get() == "bhf_distribution" and (key in {"baseline", "slope"} or (self.dist_use_sharp_var.get() and re.match(r"s[123]_", key)))):
            self.last_bhf_fit = None
        if key in {"center", "vmax"}:
            self.refold_data()
        self.apply_constraints_to_vars()
        self.update_plot()

    def calibration_iso_ref(self) -> float | None:
        """Desplazamiento isomérico de referencia de la calibración activa, o None.

        El δ corregido de un componente es δ_medido − iso_calibración, que
        traslada el cero de la escala al centro del patrón de calibración
        (p. ej. α-Fe), dejando los δ referidos al estándar.
        """
        info = getattr(self, "calibration_info", None)
        if not info:
            return None
        v = info.get("isomer_shift")
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def calibration_uncertainty_text(self) -> str | None:
        if not self.calibration_info:
            return None
        for key in ("velocity_uncertainty", "vmax_uncertainty", "velocity_error", "vmax_error", "sigma_vmax"):
            val = self.calibration_info.get(key)
            if val not in (None, ""):
                try:
                    return tr("info.calib_uncertainty", field=key, value=f"{float(val):.4g}")
                except (TypeError, ValueError):
                    return tr("info.calib_uncertainty_raw", field=key, value=val)
        return tr("info.calib_no_uncertainty")

    def data_sigma(self) -> np.ndarray | None:
        """Incertidumbre 1σ de los datos normalizados por estadística Poisson.

        El doblado promedia dos canales independientes. Para cuentas similares,
        Var((c1+c2)/2) ≈ folded/2. Se impone un suelo para evitar pesos infinitos.
        """
        if self.folded_raw is None or self.y_data is None:
            return None
        sigma_counts = np.sqrt(np.maximum(self.folded_raw / 2.0, 1.0))
        sigma = sigma_counts / max(float(self.norm_factor), 1e-12)
        return np.maximum(sigma, 1e-9)

    def predicted_sigma(self, model_y: np.ndarray) -> np.ndarray | None:
        """σ basada en el modelo (verosimilitud Poisson). Usada para IRLS."""
        if self.norm_factor is None:
            return None
        norm = max(float(self.norm_factor), 1e-12)
        predicted_counts = np.maximum(np.asarray(model_y, dtype=float) * norm, 1.0)
        sigma_counts = np.sqrt(predicted_counts / 2.0)
        return np.maximum(sigma_counts / norm, 1e-9)

    def residual_sigma(self, model_y: np.ndarray | None) -> np.ndarray | None:
        """Devuelve la σ apropiada al modo de verosimilitud activo.

        ``gauss``  → σ del dato observado (estimación clásica Gaussiana).
        ``poisson``→ σ predicha por el modelo (Newton/IRLS sobre log-L Poisson).
        """
        if self.likelihood_var.get() == "poisson" and model_y is not None:
            sig = self.predicted_sigma(model_y)
            if sig is not None:
                return sig
        return self.data_sigma()

    def calibration_vmax_sigma(self) -> float | None:
        """σ de la escala de velocidad (vmax) leída de calibration_info, o None."""
        info = getattr(self, "calibration_info", None)
        if not info:
            return None
        for key in ("vmax_uncertainty", "velocity_uncertainty", "sigma_vmax", "vmax_error", "velocity_error"):
            val = info.get(key)
            if val not in (None, ""):
                try:
                    s = abs(float(val))
                    return s if np.isfinite(s) and s > 0 else None
                except (TypeError, ValueError):
                    continue
        return None

    def augment_sigma_calibration(self, base_sigma: np.ndarray | None, model_y: np.ndarray, vmax: float) -> np.ndarray | None:
        """Suma en cuadratura la contribución de σ_vmax a la incertidumbre.

        La sensibilidad del modelo al cambio de escala es
            ∂T/∂v_max |_i = (∂T/∂v)|_i · (v_i / v_max),
        porque v_i = v_max·(2i/(N−1) − 1) ⇒ ∂v_i/∂v_max = v_i/v_max.
        El término pesa más en los flancos de los picos (∂T/∂v grande), que es
        justo donde un error de calibración sesga δ y BHF.
        """
        if base_sigma is None:
            return None
        if not self.propagate_calib_var.get():
            return base_sigma
        sv = self.calibration_vmax_sigma()
        if not sv or vmax <= 0 or self.velocity is None or self.velocity.size != base_sigma.size:
            return base_sigma
        v = self.velocity
        dT_dv = np.gradient(np.asarray(model_y, dtype=float), v)
        dT_dvmax = dT_dv * (v / vmax)
        return np.sqrt(base_sigma ** 2 + (dT_dvmax * sv) ** 2)

    def _least_squares_kwargs(self) -> dict:
        """kwargs comunes para least_squares incluyendo pérdida robusta (mejora 10)."""
        loss = self.robust_loss_var.get()
        kwargs: dict = {}
        if loss in ("soft_l1", "huber", "cauchy"):
            kwargs["loss"] = loss
            kwargs["f_scale"] = 3.0  # umbral ~3σ (residuos ya normalizados por σ)
        return kwargs

    def fit_correlation_summary(self, cov: np.ndarray | None, names: list[str], threshold: float = 0.95) -> dict[str, object]:
        """Resume correlaciones de la matriz de covarianza para diagnosticar degeneraciones."""
        if cov is None or cov.size == 0 or len(names) < 2:
            return {}
        diag = np.sqrt(np.maximum(np.diag(cov), 0.0))
        denom = np.outer(diag, diag)
        with np.errstate(divide="ignore", invalid="ignore"):
            corr = np.divide(cov, denom, out=np.zeros_like(cov, dtype=float), where=denom > 0)
        pairs: list[dict[str, object]] = []
        max_abs = 0.0
        max_pair: tuple[str, str] | None = None
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                c = float(corr[i, j])
                if not np.isfinite(c):
                    continue
                ac = abs(c)
                if ac > max_abs:
                    max_abs = ac
                    max_pair = (names[i], names[j])
                if ac >= threshold:
                    pairs.append({"param1": names[i], "param2": names[j], "corr": c})
        return {"max_abs_corr": float(max_abs), "max_pair": list(max_pair) if max_pair else [], "high_pairs": pairs, "threshold": float(threshold)}

    def residual_diagnostics(self, residual: np.ndarray, sigma: np.ndarray | None = None) -> dict[str, float]:
        """Diagnósticos simples para detectar estructura no aleatoria en el residuo."""
        r = np.asarray(residual, dtype=float)
        if sigma is not None and sigma.size == r.size:
            r = r / sigma
        r = r[np.isfinite(r)]
        if r.size < 4:
            return {}
        r0 = r - float(np.mean(r))
        denom = float(np.dot(r0, r0))
        lag1 = float(np.dot(r0[:-1], r0[1:]) / denom) if denom > 0 else 0.0
        signs = np.sign(r0)
        signs = signs[signs != 0]
        runs_z = 0.0
        if signs.size > 2:
            runs = 1 + int(np.sum(signs[1:] != signs[:-1]))
            n_pos = int(np.sum(signs > 0)); n_neg = int(np.sum(signs < 0)); n_tot = n_pos + n_neg
            if n_pos > 0 and n_neg > 0 and n_tot > 1:
                mean_runs = 1.0 + 2.0 * n_pos * n_neg / n_tot
                var_runs = (2.0 * n_pos * n_neg * (2.0 * n_pos * n_neg - n_tot)) / (n_tot ** 2 * max(n_tot - 1, 1))
                if var_runs > 0:
                    runs_z = float((runs - mean_runs) / np.sqrt(var_runs))
        rev = r0[::-1]
        anti = float(np.dot(r0, -rev) / denom) if denom > 0 else 0.0
        return {"resid_lag1": lag1, "resid_runs_z": runs_z, "resid_antisym_corr": anti}

    def fit_statistics(self, residual: np.ndarray, sigma: np.ndarray | None, n_params: int) -> dict[str, float]:
        n = int(residual.size)
        k = int(max(n_params, 0))
        rss = float(np.sum(residual ** 2))
        rms = float(np.sqrt(np.mean(residual ** 2))) if n else float("nan")
        if sigma is not None and sigma.size == residual.size:
            r = residual / sigma
            chi2 = float(np.sum(r ** 2))
        else:
            chi2 = rss
        dof = max(1, n - k)
        red_chi2 = chi2 / dof
        # AIC/BIC gaussianos con varianza estimada; constantes omitidas.
        rss_like = max(chi2, 1e-300)
        aic = float(n * np.log(rss_like / max(n, 1)) + 2 * k) if n else float("nan")
        bic = float(n * np.log(rss_like / max(n, 1)) + k * np.log(max(n, 1))) if n else float("nan")
        stats = {"n": float(n), "n_params": float(k), "dof": float(dof), "rms": rms, "chi2": chi2, "red_chi2": red_chi2, "aic": aic, "bic": bic}
        stats.update(self.residual_diagnostics(residual, sigma))
        return stats

    def _rescale_initial_depths(self, params: dict[str, float], component_range=None) -> None:
        """Reescala las profundidades del guess inicial para que la absorción
        máxima del modelo no supere la de los datos.

        Los estimadores de profundidad por pico no siempre dividen por el peso
        relativo de cada línea (W hasta 3 en un sextete), por lo que el modelo
        inicial puede pasarse con creces de los datos. Un factor global común a
        todas las profundidades corrige el sobre-tiro preservando las relaciones
        entre componentes; el ajuste posterior afina el resto.
        """
        if self.velocity is None or self.y_data is None:
            return
        rng = component_range if component_range is not None else (
            self._component_range() if hasattr(self, "_component_range") else (1, 2, 3))
        baseline = float(params.get("baseline", self.vars["baseline"].get()))
        slope = float(params.get("slope", self.vars["slope"].get()))
        v = self.velocity
        comps: list[tuple[str, np.ndarray]] = []
        depth_keys: list[str] = []
        for idx in rng:
            if idx not in self.sextet_enabled or not self.sextet_enabled[idx].get():
                continue
            p = f"s{idx}_"
            arr = np.array([params.get(p + name, self.vars[p + name].get()) for name in SEXTET_PARAM_NAMES], dtype=float)
            comps.append((self.component_kind[idx].get(), arr))
            depth_keys.append(p + "depth")
        if not comps:
            return
        baseline_line = baseline + slope * v
        model = total_model(v, baseline, slope, comps)
        model_abs = float(np.max(baseline_line - model)) if v.size else 0.0
        data_abs = float(np.max(baseline_line - self.y_data)) if v.size else 0.0
        if model_abs > 1e-6 and data_abs > 0.0 and model_abs > data_abs:
            factor = data_abs / model_abs
            for key in depth_keys:
                if key in params:
                    params[key] = float(params[key] * factor)

    def current_model(self) -> np.ndarray | None:
        if self.fit_mode_var.get() == "bhf_distribution" and self.last_bhf_fit is not None:
            return self.last_bhf_fit.fitted_curve
        if self.velocity is None:
            return None
        # No simular hasta que se toque un parámetro o se ajuste (modo discreto).
        if not getattr(self, "_simulate_enabled", True):
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
            "slope": (-0.005, 0.005),
            "delta": (-2.0, 3.0),
            "quad": (-4.0, 4.0),
            "bhf": (0.0, 60.0),
            "gamma1": (0.03, 2.0),
            "gamma2": (0.2, 3.0),
            "gamma3": (0.2, 3.0),
            "depth": (0.0, 0.30),
            "int1": (0.0, 9.0),
            "int2": (0.0, 6.0),
            "int3": (0.0, 3.0),
            "texture": (0.0, 1.0),
            "beta": (0.0, 90.0),   # ángulo β entre B y V_zz, en grados
        }
        return bounds[base]

    @staticmethod
    def texture_to_intensities(t: float) -> tuple[float, float, float]:
        """Conversión textura → (i1, i2, i3) para el sextete con eje aleatorio.

        Para ángulo θ entre B y k_γ, las amplitudes de las seis líneas son
            W₁,₆ = 3(1+cos²θ), W₂,₅ = 4 sin²θ, W₃,₄ = 1+cos²θ.
        Con t = sin²θ se obtiene 1+cos²θ = 2−t, así que normalizando por (2−t)
        queda W₁,₆ : W₂,₅ : W₃,₄ = 3 : 4t/(2−t) : 1.
        t=2/3 ⇒ 3:2:1 (polvo aleatorio).  t=1 ⇒ 3:4:1 (texturado plano).
        t=0 ⇒ 3:0:1 (eje fácil paralelo al haz).
        """
        t = max(0.0, min(1.0, float(t)))
        denom = max(2.0 - t, 1e-9)
        return 3.0, 4.0 * t / denom, 1.0

    def apply_texture_mode_to_values(self, values: dict[str, float]) -> dict[str, float]:
        """Si un sextete está en modo "texture", deriva i1,i2,i3 desde s{i}_texture."""
        if not hasattr(self, "intensity_mode"):
            return values
        out = values
        for idx, mode_var in self.intensity_mode.items():
            if mode_var.get() != "texture":
                continue
            if self.component_kind.get(idx) is None or self.component_kind[idx].get() != "Sextete":
                continue
            t_key = f"s{idx}_texture"
            t = out.get(t_key, self.vars[t_key].get()) if t_key in self.vars else None
            if t is None:
                continue
            i1, i2, i3 = self.texture_to_intensities(float(t))
            if out is values:
                out = values.copy()
            out[f"s{idx}_int1"] = i1
            out[f"s{idx}_int2"] = i2
            out[f"s{idx}_int3"] = i3
        return out

    def model_from_values(self, values: dict[str, float], vmax: float) -> np.ndarray:
        assert self.y_data is not None
        values = self.apply_constraints_to_values(values)
        v = np.linspace(-vmax, vmax, self.y_data.size)
        components: list = []
        for idx in (1, 2, 3):
            if self.sextet_enabled[idx].get():
                p = f"s{idx}_"
                params = np.array([values.get(p + name, self.vars[p + name].get()) for name in SEXTET_PARAM_NAMES], dtype=float)
                kind = self.component_kind[idx].get()
                if kind == "Sextete":
                    treat_var = getattr(self, "quad_treatment", {}).get(idx)
                    if treat_var is not None and treat_var.get() != "1st_order":
                        beta_deg = float(values.get(f"s{idx}_beta", self.vars[f"s{idx}_beta"].get())) if f"s{idx}_beta" in self.vars else 0.0
                        extras = {
                            "treatment": treat_var.get(),
                            "beta": float(np.deg2rad(beta_deg)),
                            "n_quad": 20,
                        }
                        components.append((kind, params, extras))
                        continue
                components.append((kind, params))
        return total_model(v, values["baseline"], values["slope"], components)

    def open_progress_dialog(self, title: str, message: str | None = None):
        if message is None:
            message = tr("progress.generic_working")
        """Ventana simple de progreso para indicar que el cálculo sigue activo."""
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        status_var = tk.StringVar(value=message)
        ttk.Label(frame, textvariable=status_var, wraplength=430).pack(anchor=tk.W, pady=(0, 10))
        bar = ttk.Progressbar(frame, mode="indeterminate", length=420)
        bar.pack(fill=tk.X)
        bar.start(12)
        dialog.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - dialog.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")

        def update(msg: str) -> None:
            if dialog.winfo_exists():
                status_var.set(msg)
                dialog.update_idletasks()
                self.update_idletasks()

        def close() -> None:
            try:
                bar.stop()
                if dialog.winfo_exists():
                    dialog.destroy()
            except tk.TclError:
                pass

        return dialog, update, close

    def fit_current_data(self) -> None:
        self._simulate_enabled = True
        self.apply_constraints_to_vars()
        if self.fit_mode_var.get() == "bhf_distribution":
            self.fit_bhf_distribution_current()
            return
        if self.velocity is None or self.y_data is None:
            return
        y = self.y_data
        sigma = self.data_sigma()
        keys = self.active_param_keys()
        self.apply_constraints_to_vars()
        constrained_targets = self.constrained_target_keys()
        values0 = {key: self.vars[key].get() for key in keys}

        fit_velocity = self.fit_velocity_var.get()
        fit_center = self.fit_center_var.get()
        fit_sigma = self.fit_sigma_var.get() and self.line_profile_var.get() == "Voigt"
        if fit_velocity and not all(self.fixed_vars[k].get() for k in self.active_bhf_keys()):
            messagebox.showwarning(
                tr("msg.fit_velocity_title"),
                tr("msg.fit_velocity_requires_bhf_fixed"),
            )
            return

        free_keys = [key for key in keys if key not in constrained_targets and not self.fixed_vars.get(key, tk.BooleanVar(value=False)).get()]
        if not free_keys and not fit_velocity and not fit_center:
            messagebox.showinfo(tr("msg.fit_title"), tr("msg.fit_all_fixed"))
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
        if fit_center:
            x0.append(self.vars["center"].get())
            lo.append(self.slider_specs["center"][0])
            hi.append(self.slider_specs["center"][1])
        if fit_sigma:
            x0.append(float(self.vars["voigt_sigma"].get()))
            lo.append(self.slider_specs["voigt_sigma"][0])
            hi.append(self.slider_specs["voigt_sigma"][1])
        x0_arr = np.array(x0, dtype=float)
        lo_arr = np.array(lo, dtype=float)
        hi_arr = np.array(hi, dtype=float)
        x0_arr = np.clip(x0_arr, lo_arr, hi_arr)

        def unpack(x: np.ndarray) -> tuple[dict[str, float], float, float]:
            global VOIGT_SIGMA
            values = values0.copy()
            for key, value in zip(free_keys, x[:len(free_keys)]):
                values[key] = float(value)
            values = self.apply_constraints_to_values(values)
            pos = len(free_keys)
            vmax = float(x[pos]) if fit_velocity else abs(self.vars["vmax"].get())
            pos += 1 if fit_velocity else 0
            center_fit = float(x[pos]) if fit_center else self.vars["center"].get()
            pos += 1 if fit_center else 0
            if fit_sigma:
                VOIGT_SIGMA = float(x[pos])
            return values, vmax, center_fit

        def data_for_center(center_value: float) -> tuple[np.ndarray, np.ndarray | None]:
            if not fit_center or self.counts is None:
                return y, sigma
            folded, _pairs = fold_integer_or_half(self.counts, center_value)
            norm = float(np.percentile(folded, 90)) if folded.size else self.norm_factor
            if norm == 0:
                norm = 1.0
            yy = folded / norm
            sig = np.sqrt(np.maximum(folded / 2.0, 1.0)) / max(norm, 1e-12)
            return yy, np.maximum(sig, 1e-9)

        use_poisson = self.likelihood_var.get() == "poisson"

        def residual(x: np.ndarray) -> np.ndarray:
            values, vmax, center_fit = unpack(x)
            yy, sig = data_for_center(center_fit)
            model_y = self.model_from_values(values, vmax)
            if use_poisson:
                sig_use = self.predicted_sigma(model_y)
                if sig_use is None:
                    sig_use = sig
            else:
                sig_use = sig
            sig_use = self.augment_sigma_calibration(sig_use, model_y, vmax)
            res = model_y - yy
            return res / sig_use if sig_use is not None else res

        def multistart_candidates() -> list[np.ndarray]:
            candidates = [x0_arr]
            rng = np.random.default_rng(12345)
            span = hi_arr - lo_arr
            for _ in range(8):
                trial = x0_arr.copy()
                for i, key in enumerate(free_keys + (["vmax"] if fit_velocity else []) + (["center"] if fit_center else []) + (["voigt_sigma"] if fit_sigma else [])):
                    width = span[i]
                    if not np.isfinite(width) or width <= 0:
                        continue
                    if key.endswith(("delta", "quad", "bhf", "gamma1", "depth", "vmax")):
                        trial[i] += rng.normal(0.0, 0.12 * width)
                    else:
                        trial[i] += rng.normal(0.0, 0.08 * width)
                candidates.append(np.clip(trial, lo_arr, hi_arr))
            return candidates

        progress = self.open_progress_dialog(tr("progress.fitting_title"), tr("progress.fit_prepare"))
        _progress_dialog, update_progress, close_progress = progress
        try:
            result = None
            n_starts = 0
            candidates = multistart_candidates()
            # Mejora 14: pre-pasada global con differential_evolution (opt-in).
            # Su mejor punto se añade como semilla extra; el TRF lo pule luego.
            if self.global_opt_var.get():
                update_progress(tr("progress.fit_global"))

                def _scalar_cost(x: np.ndarray) -> float:
                    r = residual(x)
                    return 0.5 * float(np.dot(r, r))

                try:
                    de = differential_evolution(
                        _scalar_cost,
                        bounds=list(zip(lo_arr.tolist(), hi_arr.tolist())),
                        seed=12345, maxiter=60, tol=1e-4,
                        mutation=(0.5, 1.0), recombination=0.7,
                        polish=False, init="sobol", updating="deferred",
                    )
                    candidates.insert(0, np.clip(de.x, lo_arr, hi_arr))
                except Exception:
                    pass
            ls_kwargs = self._least_squares_kwargs()
            for candidate in candidates:
                n_starts += 1
                update_progress(tr("progress.fit_step", i=n_starts, total=len(candidates)))
                res_i = least_squares(residual, candidate, bounds=(lo_arr, hi_arr), max_nfev=7000, **ls_kwargs)
                if result is None or res_i.cost < result.cost:
                    result = res_i
                    update_progress(tr("progress.fit_step_new_best", i=n_starts, total=len(candidates), cost=res_i.cost))
                else:
                    update_progress(tr("progress.fit_step_done", i=n_starts, total=len(candidates), cost=result.cost))
            assert result is not None
        except Exception as exc:
            close_progress()
            messagebox.showerror(tr("msg.fit_error_title"), str(exc))
            return

        # Covarianza aproximada de los parámetros libres para errores 1σ.
        self.last_fit_free_keys = free_keys.copy()
        self.last_fit_cov = None
        self.last_fit_param_errors = {}
        self.last_fit_stats = {}
        self.last_fit_correlations = {}
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
                self.last_fit_correlations = self.fit_correlation_summary(self.last_fit_cov, free_keys)
        except Exception:
            self.last_fit_cov = None
            self.last_fit_param_errors = {}
            self.last_fit_correlations = {}

        update_progress(tr("progress.fit_finalize"))
        values_final, vmax_final, center_final = unpack(result.x)
        y_final, sigma_final = data_for_center(center_final)
        model_final = self.model_from_values(values_final, vmax_final)
        final_residual = model_final - y_final
        sigma_for_stats = self.predicted_sigma(model_final) if use_poisson else sigma_final
        sigma_for_stats = self.augment_sigma_calibration(sigma_for_stats, model_final, vmax_final)
        self.last_fit_stats = self.fit_statistics(final_residual, sigma_for_stats, len(result.x))
        self.last_fit_stats["likelihood"] = self.likelihood_var.get()
        self.last_fit_stats["robust_loss"] = self.robust_loss_var.get()
        self.last_fit_stats["n_starts"] = float(n_starts)
        self.set_params(values_final)
        if fit_velocity:
            self.vars["vmax"].set(vmax_final)
            self.entry_vars["vmax"].set(self._format_value("vmax", vmax_final))
        if fit_center:
            self.vars["center"].set(center_final)
            self.entry_vars["center"].set(self._format_value("center", center_final))
        if fit_sigma:
            pos = len(free_keys) + (1 if fit_velocity else 0) + (1 if fit_center else 0)
            sigma_final_val = float(result.x[pos])
            self.vars["voigt_sigma"].set(sigma_final_val)
            self.entry_vars["voigt_sigma"].set(self._format_value("voigt_sigma", sigma_final_val))
        if fit_velocity or fit_center:
            self.refold_data()
        self.update_plot()
        close_progress()

    def bootstrap_errors_current(self) -> None:
        """Estimación Monte Carlo rápida de errores para el modelo discreto actual."""
        if self.fit_mode_var.get() == "bhf_distribution":
            messagebox.showinfo(tr("msg.bootstrap_title"), tr("msg.bootstrap_discrete_only"))
            return
        if self.velocity is None or self.y_data is None:
            return
        self._simulate_enabled = True
        model0 = self.current_model()
        sigma = self.data_sigma()
        if model0 is None or sigma is None:
            messagebox.showwarning(tr("msg.bootstrap_title"), tr("msg.bootstrap_no_model"))
            return
        keys = self.active_param_keys()
        constrained_targets = self.constrained_target_keys()
        free_keys = [key for key in keys if key not in constrained_targets and not self.fixed_vars.get(key, tk.BooleanVar(value=False)).get()]
        if not free_keys:
            messagebox.showinfo(tr("msg.bootstrap_title"), tr("msg.bootstrap_no_free"))
            return
        nrep = simpledialog.askinteger(tr("msg.bootstrap_title"), tr("dialog.bootstrap_prompt"), initialvalue=30, minvalue=5, maxvalue=300, parent=self)
        if not nrep:
            return
        base_values = {key: self.vars[key].get() for key in keys}
        lo = np.array([self.bounds_for_key(k)[0] for k in free_keys], dtype=float)
        hi = np.array([self.bounds_for_key(k)[1] for k in free_keys], dtype=float)
        x0 = np.clip(np.array([base_values[k] for k in free_keys], dtype=float), lo, hi)

        def model_values(values: dict[str, float]) -> np.ndarray:
            return self.model_from_values(values, abs(self.vars["vmax"].get()))

        progress = self.open_progress_dialog(tr("progress.bootstrap_title"), tr("progress.bootstrap_prepare"))
        _dlg, update_progress, close_progress = progress
        rng = np.random.default_rng(24680)
        use_poisson_boot = self.likelihood_var.get() == "poisson"
        norm_factor = max(float(self.norm_factor or 1.0), 1e-12)
        samples: list[np.ndarray] = []
        try:
            for i in range(int(nrep)):
                if use_poisson_boot:
                    # Simulación Poisson real: c_sim ~ Poisson(λ_pred=model0·f_norm·2)/2
                    lam = np.maximum(model0 * norm_factor * 2.0, 0.0)
                    c_sim = rng.poisson(lam).astype(float) / 2.0
                    y_sim = c_sim / norm_factor
                else:
                    y_sim = model0 + rng.normal(0.0, sigma)

                def resid(x: np.ndarray, _y_sim=y_sim) -> np.ndarray:
                    vals = base_values.copy()
                    for key, value in zip(free_keys, x):
                        vals[key] = float(value)
                    vals = self.apply_constraints_to_values(vals)
                    model_v = model_values(vals)
                    sig_use = self.predicted_sigma(model_v) if use_poisson_boot else sigma
                    if sig_use is None:
                        sig_use = sigma
                    return (model_v - _y_sim) / sig_use
                update_progress(tr("progress.bootstrap_step", i=i + 1, n=nrep))
                res = least_squares(resid, x0, bounds=(lo, hi), max_nfev=2500, **self._least_squares_kwargs())
                if res.success and np.all(np.isfinite(res.x)):
                    samples.append(res.x.copy())
            close_progress()
        except Exception as exc:
            close_progress()
            messagebox.showerror(tr("msg.bootstrap_title"), str(exc))
            return
        if len(samples) < 3:
            messagebox.showwarning(tr("msg.bootstrap_title"), tr("msg.bootstrap_few_replicas"))
            return
        arr = np.vstack(samples)
        errs = np.std(arr, axis=0, ddof=1)
        self.last_fit_param_errors.update({k: float(e) for k, e in zip(free_keys, errs)})
        self.last_fit_stats["bootstrap_replicates"] = float(len(samples))
        self.update_info(self.last_fit_stats.get("rms", float("nan")))
        messagebox.showinfo(tr("msg.bootstrap_title"), tr("msg.bootstrap_done", ok=len(samples), total=nrep))

    def load_fixed_distribution_file(self) -> None:
        filename = filedialog.askopenfilename(
            title=tr("dialog.load_fixed_dist"),
            filetypes=[(tr("filetype.data"), "*.dat *.txt *.csv"), (tr("filetype.all"), "*")],
        )
        if filename:
            self.fixed_distribution_path = Path(filename)
            self.dist_shape_var.set("Fija")
            self.last_bhf_fit = None
            messagebox.showinfo(tr("msg.fixed_dist_title"), tr("msg.fixed_dist_loaded", path=str(self.fixed_distribution_path)))
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

    def suggest_alpha_compromise_from_lcurve_rows(self, rows: np.ndarray) -> float | None:
        """Sugiere α por distancia al punto ideal: bajo residuo y baja rugosidad."""
        if rows.shape[0] < 3:
            return None
        alpha, misfit, rough = rows[:, 0], rows[:, 2], rows[:, 3]
        mask = (alpha > 0) & (misfit > 0) & (rough > 0) & np.isfinite(misfit) & np.isfinite(rough)
        if int(np.sum(mask)) < 3:
            return None
        a = alpha[mask]
        x = np.log10(rough[mask])
        y = np.log10(misfit[mask])
        xr = (x - np.nanmin(x)) / max(float(np.nanmax(x) - np.nanmin(x)), 1e-12)
        yr = (y - np.nanmin(y)) / max(float(np.nanmax(y) - np.nanmin(y)), 1e-12)
        score = xr * xr + yr * yr
        return float(a[int(np.nanargmin(score))])

    def scan_bhf_alpha_gui(self) -> None:
        if self.velocity is None or self.y_data is None:
            return
        bmin = self.vars["dist_bmin"].get()
        bmax = self.vars["dist_bmax"].get()
        nbins = int(round(self.vars["dist_nbins"].get()))
        if bmax <= bmin or nbins < 3:
            messagebox.showwarning(tr("msg.lcurve_title"), tr("msg.lcurve_invalid_bins"))
            return
        sharp_components = None
        if self.dist_use_sharp_var.get():
            sharp_components, _indices = self.build_bhf_sharp_components_from_active_components()
        progress = self.open_progress_dialog(tr("msg.lcurve_title"), tr("progress.lcurve_prepare"))
        _progress_dialog, update_progress, close_progress = progress
        try:
            alphas = np.logspace(-8, 4, 31)
            variable = "quad" if self.dist_variable_var.get() == "ΔEQ" else "bhf"
            scans = []
            for i, a in enumerate(alphas, start=1):
                update_progress(tr("progress.lcurve_step", i=i, total=len(alphas), alpha=float(a)))
                scans.append(fit_hyperfine_distribution_engine(
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
                    sigma=self.data_sigma(),
                    reg_mode=self.dist_reg_mode_var.get(),
                ))
            update_progress(tr("progress.lcurve_finalize"))
        except Exception as exc:
            close_progress()
            messagebox.showerror(tr("msg.lcurve_title"), str(exc))
            return
        L = first_difference_matrix(nbins) if self.dist_reg_mode_var.get().lower() in ("tv", "total_variation") else second_difference_matrix(nbins)
        sigma = self.data_sigma()
        n_raw = nbins + int(not self.fixed_vars["baseline"].get()) + int(not self.fixed_vars["slope"].get()) + (len(sharp_components or []) if self.dist_use_sharp_var.get() else 0)
        rows_list = []
        gcv_list = []
        for r in scans:
            misfit = float(np.linalg.norm(r.residuals))
            rough = float(np.linalg.norm(L @ r.weights))
            if sigma is not None and sigma.size == r.residuals.size:
                chi2 = float(np.sum((r.residuals / sigma) ** 2))
                misfit_w = float(np.linalg.norm(r.residuals / sigma))
            else:
                chi2 = float(np.sum(r.residuals ** 2))
                misfit_w = misfit
            # dof efectivo (Mejora 2). Si no está disponible, cae al recuento ingenuo.
            dof_eff = float(getattr(r, "effective_dof", None) or n_raw)
            red_chi2 = chi2 / max(1.0, float(r.residuals.size) - dof_eff)
            # GCV(α) = ‖W^{1/2}(y − ŷ)‖² / (N − tr A(α))²   (Mejora 3)
            denom = max(float(r.residuals.size) - dof_eff, 1e-6)
            gcv = (misfit_w ** 2) / (denom ** 2)
            gcv_list.append(gcv)
            peak = float(r.bhf_centers[int(np.argmax(r.weights))]) if r.weights.size else float("nan")
            rows_list.append((r.alpha, r.rms, misfit, rough, chi2, red_chi2, peak, dof_eff, gcv))
        rows = np.array(rows_list, dtype=float)
        suggested = self.suggest_alpha_from_lcurve_rows(rows)
        suggested_compromise = self.suggest_alpha_compromise_from_lcurve_rows(rows)
        gcv_arr = np.array(gcv_list, dtype=float)
        suggested_gcv = None
        if gcv_arr.size and np.any(np.isfinite(gcv_arr)):
            idx = int(np.nanargmin(np.where(np.isfinite(gcv_arr), gcv_arr, np.inf)))
            suggested_gcv = float(rows[idx, 0])

        dialog = tk.Toplevel(self)
        dist_label_lc = 'P(ΔEQ)' if self.dist_variable_var.get() == 'ΔEQ' else 'P(BHF)'
        dialog.title(tr("dialog.lcurve_title", label=dist_label_lc))
        dialog.geometry("850x420")
        dialog.transient(self)
        fig = Figure(figsize=(8.2, 3.6), dpi=100, facecolor="#f8fbff")
        ax0 = fig.add_subplot(121)
        ax1 = fig.add_subplot(122)
        sc = ax0.scatter(rows[:, 3], rows[:, 2], c=np.log10(rows[:, 0]), cmap="viridis", s=34)
        ax0.plot(rows[:, 3], rows[:, 2], "-", color="#94a3b8", lw=0.8)
        ax0.set_xscale("log"); ax0.set_yscale("log")
        ax0.set_xlabel(tr("plot.lcurve_xlabel")); ax0.set_ylabel(tr("plot.lcurve_ylabel")); ax0.set_title(tr("plot.lcurve_title"))
        ax0.grid(True, alpha=0.3)
        fig.colorbar(sc, ax=ax0, label=tr("plot.lcurve_colorbar"))
        ax1.loglog(rows[:, 0], rows[:, 1], "-o", ms=3.2, label=tr("plot.label_rms"))
        ax1b = ax1.twinx()
        ax1b.semilogx(rows[:, 0], rows[:, 5], "--", color="#7c3aed", lw=1.0, label=tr("plot.label_chi2_red"))
        if np.any(np.isfinite(gcv_arr)):
            gcv_norm = gcv_arr / max(float(np.nanmin(gcv_arr[np.isfinite(gcv_arr)])), 1e-30)
            ax1b.semilogx(rows[:, 0], gcv_norm, ":", color="#0891b2", lw=1.1, label="GCV/min")
        ax1b.set_ylabel(tr("plot.chi2_reduced_ylabel"), color="#7c3aed")
        ax1b.tick_params(axis="y", colors="#7c3aed")
        if suggested is not None:
            ax1.axvline(suggested, color="#dc2626", ls="--", lw=1.2, label=tr("plot.label_lcurve_suggest", value=suggested))
        if suggested_compromise is not None:
            ax1.axvline(suggested_compromise, color="#16a34a", ls=":", lw=1.4, label=tr("plot.label_compromise_suggest", value=suggested_compromise))
        if suggested_gcv is not None:
            ax1.axvline(suggested_gcv, color="#0891b2", ls="-.", lw=1.4, label=tr("plot.label_gcv_suggest", value=suggested_gcv))
        ax1.legend(loc="best", fontsize=8)
        ax1.set_xlabel("α"); ax1.set_ylabel(tr("plot.label_rms")); ax1.set_title(tr("plot.alpha_scan_title"))
        ax1.grid(True, which="both", alpha=0.3)
        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=dialog)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        canvas.draw_idle()
        close_progress()
        buttons = ttk.Frame(dialog, padding=8)
        buttons.pack(fill=tk.X)
        def save_alpha_table() -> None:
            filename = filedialog.asksaveasfilename(
                title=tr("dialog.save_alpha_table"),
                initialfile=(self.file_path.stem if self.file_path else "mossbauer") + "_alpha_scan.dat",
                defaultextension=".dat",
                filetypes=[(tr("filetype.data"), "*.dat"), (tr("filetype.text"), "*.txt"), (tr("filetype.all"), "*")],
            )
            if filename:
                np.savetxt(filename, rows, header="alpha rms norm_residual norm_LP chi2 red_chi2 peak_parameter dof_eff gcv", fmt="%.10g")
        if suggested_compromise is not None:
            ttk.Button(buttons, text=tr("button.use_compromise", value=suggested_compromise), command=lambda a=suggested_compromise, d=dialog: (self.set_bhf_alpha_preset(np.log10(a)), d.destroy()), style="Accent.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        if suggested_gcv is not None:
            ttk.Button(buttons, text=tr("button.use_gcv", value=suggested_gcv), command=lambda a=suggested_gcv, d=dialog: (self.set_bhf_alpha_preset(np.log10(a)), d.destroy()), style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        if suggested is not None:
            ttk.Button(buttons, text=tr("button.use_lcurve", value=suggested), command=lambda a=suggested, d=dialog: (self.set_bhf_alpha_preset(np.log10(a)), d.destroy()), style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(buttons, text=tr("button.save_table"), command=save_alpha_table, style="Small.TButton").pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(buttons, text=tr("button.close"), command=dialog.destroy, style="Small.TButton").pack(side=tk.RIGHT)

    def active_sharp_component_indices_for_bhf(self) -> list[int]:
        if not self.dist_use_sharp_var.get():
            return []
        return [idx for idx in (1, 2, 3) if self.sextet_enabled[idx].get()]

    def build_bhf_sharp_components_from_active_components(self) -> tuple[list[dict[str, float]], list[int]]:
        components: list[dict[str, float]] = []
        indices = self.active_sharp_component_indices_for_bhf()
        for idx in indices:
            p = f"s{idx}_"
            kind = self.component_kind[idx].get()
            int1_gui = float(self.vars[p + "int1"].get())
            int2_gui = float(self.vars[p + "int2"].get())
            int3_gui = float(self.vars[p + "int3"].get())
            # El motor de distribución usa para sextetes la convención interna
            # int1, (2/3)*int1*int2_rel, (1/3)*int1*int3_rel, mientras que
            # la GUI discreta usa la convención NORMOS I13/I23/I: int3*int1,
            # int3*int2, int3. Convertimos aquí para que el kernel nítido que
            # se ajusta sea exactamente el mismo que luego se dibuja y se resta
            # de la curva total para mostrar solo la distribución.
            if kind == "Sextete":
                i1 = int3_gui * int1_gui
                if abs(i1) > 1e-12:
                    engine_int1 = i1
                    engine_int2_rel = (1.5 * int2_gui / int1_gui) if abs(int1_gui) > 1e-12 else 0.0
                    engine_int3_rel = 3.0 / int1_gui if abs(int1_gui) > 1e-12 else 0.0
                else:
                    engine_int1 = 0.0
                    engine_int2_rel = 0.0
                    engine_int3_rel = 0.0
            else:
                engine_int1 = int1_gui
                engine_int2_rel = int2_gui
                engine_int3_rel = int3_gui
            components.append({
                "kind": kind,
                "bhf": self.vars[p + "bhf"].get(),
                "delta": self.vars[p + "delta"].get(),
                "quad": self.vars[p + "quad"].get(),
                "gamma": self.vars[p + "gamma1"].get(),
                "gamma2_rel": self.vars[p + "gamma2"].get(),
                "gamma3_rel": self.vars[p + "gamma3"].get(),
                "int1": engine_int1,
                "int2_rel": engine_int2_rel,
                "int3_rel": engine_int3_rel,
            })
        return components, indices

    def fit_bhf_distribution_current(self) -> None:
        if self.velocity is None or self.y_data is None:
            return
        bmin = self.vars["dist_bmin"].get()
        bmax = self.vars["dist_bmax"].get()
        nbins = int(round(self.vars["dist_nbins"].get()))
        if bmax <= bmin:
            messagebox.showwarning(tr("msg.pbhf_title"), tr("msg.pbhf_bmax_lt_bmin"))
            return
        if nbins < 3:
            messagebox.showwarning(tr("msg.pbhf_title"), tr("msg.pbhf_too_few_bins"))
            return
        sharp_components: list[dict[str, float]] | None = None
        sharp_indices: list[int] = []
        if self.dist_use_sharp_var.get():
            sharp_components, sharp_indices = self.build_bhf_sharp_components_from_active_components()

        fit_baseline = not self.fixed_vars["baseline"].get()
        fit_slope = not self.fixed_vars["slope"].get()

        def run_fit(delta_value: float, gamma_value: float, sharp_for_fit: list[dict[str, float]] | None, sigma_override: np.ndarray | None = None):
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
                    sharp_components=sharp_for_fit,
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
                    sharp_components=sharp_for_fit,
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
                    sharp_components=sharp_for_fit,
                )
            sigma_use = sigma_override if sigma_override is not None else self.data_sigma()
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
                sharp_components=sharp_for_fit,
                sigma=sigma_use,
                reg_mode=self.dist_reg_mode_var.get(),
            )

        # Build outer parameter vector: dist_delta/dist_gamma (when refining globals)
        # plus per-sharp-component shape params (delta, quad, bhf, log gamma) when sharp
        # components are active and not individually fixed.
        refine_global = self.dist_refine_global_var.get()
        have_sharp = bool(sharp_indices)

        outer_specs: list[tuple[str, str, float, float]] = []
        if refine_global:
            if not self.fixed_vars.get("dist_delta", tk.BooleanVar(value=False)).get():
                outer_specs.append(("dist_delta", "lin", -2.5, 2.5))
            if not self.fixed_vars.get("dist_gamma", tk.BooleanVar(value=False)).get():
                outer_specs.append(("dist_gamma", "loggamma", 0.03, 1.0))

        if have_sharp:
            for idx in sharp_indices:
                kind = self.component_kind[idx].get()
                for pname in ("delta", "quad", "bhf", "gamma1"):
                    if pname == "quad" and kind == "Singlete":
                        continue
                    if pname == "bhf" and kind != "Sextete":
                        continue
                    key = f"s{idx}_{pname}"
                    if self.fixed_vars.get(key, tk.BooleanVar(value=False)).get():
                        continue
                    lo, hi, _res = self.slider_specs[key]
                    if pname == "gamma1":
                        outer_specs.append((key, "loggamma", max(float(lo), 1e-3), float(hi)))
                    else:
                        outer_specs.append((key, "lin", float(lo), float(hi)))

        def x0_from_specs() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            x0_list, lo_list, hi_list = [], [], []
            for key, kind, lo, hi in outer_specs:
                cur = float(self.vars[key].get())
                if kind == "loggamma":
                    x0_list.append(np.log(max(cur, lo)))
                    lo_list.append(np.log(lo))
                    hi_list.append(np.log(hi))
                else:
                    x0_list.append(cur)
                    lo_list.append(lo)
                    hi_list.append(hi)
            return (
                np.array(x0_list, dtype=float),
                np.array(lo_list, dtype=float),
                np.array(hi_list, dtype=float),
            )

        def x_to_state(x: np.ndarray) -> tuple[float, float, list[dict[str, float]] | None]:
            delta_value = float(self.vars["dist_delta"].get())
            gamma_value = float(self.vars["dist_gamma"].get())
            local_sharp = [dict(c) for c in sharp_components] if sharp_components else None
            for i, (key, kind, _lo, _hi) in enumerate(outer_specs):
                v = float(np.exp(x[i])) if kind == "loggamma" else float(x[i])
                if key == "dist_delta":
                    delta_value = v
                elif key == "dist_gamma":
                    gamma_value = v
                elif local_sharp is not None:
                    m = re.match(r"s(\d+)_(.+)", key)
                    if m:
                        idx_ = int(m.group(1))
                        pname = m.group(2)
                        pos = sharp_indices.index(idx_) if idx_ in sharp_indices else -1
                        if pos >= 0:
                            mapping = {"delta": "delta", "quad": "quad", "bhf": "bhf", "gamma1": "gamma"}
                            if pname in mapping:
                                local_sharp[pos][mapping[pname]] = v
            return delta_value, gamma_value, local_sharp

        progress = self.open_progress_dialog(tr("progress.distribution_title"), tr("progress.distribution_prepare"))
        _progress_dialog, update_progress, close_progress = progress
        fitted_x: np.ndarray | None = None
        # IRLS Poisson sólo para la distribución de histograma (única ruta que
        # acepta sigma); para Gaussiana/Binomial/Fija se mantiene Gauss.
        irls_active = (
            self.likelihood_var.get() == "poisson"
            and self.dist_shape_var.get() not in ("Gaussiana", "Binomial", "Fija")
        )
        irls_max_iter = 3 if irls_active else 1
        try:
            if outer_specs:
                update_progress(tr("progress.distribution_refine"))
                x0, lo, hi = x0_from_specs()
                x0c = np.clip(x0, lo, hi)
                sigma_state = {"sigma": None}

                def residual_outer(x: np.ndarray) -> np.ndarray:
                    d, g, s = x_to_state(x)
                    return run_fit(d, g, s, sigma_override=sigma_state["sigma"]).residuals

                outer = least_squares(residual_outer, x0c, bounds=(lo, hi), max_nfev=60)
                fitted_x = outer.x
                update_progress(tr("progress.distribution_compute_final"))
                delta_final, gamma_final, sharp_final = x_to_state(fitted_x)
                result = run_fit(delta_final, gamma_final, sharp_final, sigma_override=sigma_state["sigma"])
                # IRLS Poisson: reajustar refinando σ a partir del modelo.
                for _ in range(irls_max_iter - 1):
                    sigma_state["sigma"] = self.predicted_sigma(result.fitted_curve)
                    outer = least_squares(residual_outer, fitted_x, bounds=(lo, hi), max_nfev=60)
                    fitted_x = outer.x
                    delta_final, gamma_final, sharp_final = x_to_state(fitted_x)
                    result = run_fit(delta_final, gamma_final, sharp_final, sigma_override=sigma_state["sigma"])
            else:
                shape_disp = tr(f"shape.{self.dist_shape_var.get()}", default=self.dist_shape_var.get())
                update_progress(tr("progress.distribution_compute", shape=shape_disp))
                result = run_fit(self.vars["dist_delta"].get(), self.vars["dist_gamma"].get(), sharp_components)
                for _ in range(irls_max_iter - 1):
                    sigma_irls = self.predicted_sigma(result.fitted_curve)
                    result = run_fit(self.vars["dist_delta"].get(), self.vars["dist_gamma"].get(), sharp_components, sigma_override=sigma_irls)
        except Exception as exc:
            close_progress()
            messagebox.showerror(tr("msg.pbhf_error_title"), str(exc))
            return
        self.last_bhf_fit = result
        self.last_bhf_sharp_indices = sharp_indices
        self.last_fit_correlations = {}
        n_outer = len(outer_specs)
        n_sharp = len(sharp_indices) if self.dist_use_sharp_var.get() else 0
        if self.dist_shape_var.get() == "Histograma" and getattr(result, "effective_dof", None) is not None:
            # Tikhonov: grados de libertad efectivos tr(A(α)) ya incluye baseline,
            # slope y sharps (todo lo que estaba en X). Sólo sumar los exteriores NL.
            n_params = float(result.effective_dof) + n_outer
        elif self.dist_shape_var.get() in ("Gaussiana", "Binomial"):
            n_params = 4 + int(fit_baseline) + int(fit_slope) + n_sharp + n_outer
        elif self.dist_shape_var.get() == "Fija":
            n_params = 3 + int(fit_baseline) + int(fit_slope) + n_sharp + n_outer
        else:
            n_params = nbins + int(fit_baseline) + int(fit_slope) + n_sharp + n_outer
        sigma_stats = self.predicted_sigma(result.fitted_curve) if irls_active else self.data_sigma()
        self.last_fit_stats = self.fit_statistics(result.fitted_curve - self.y_data, sigma_stats, int(round(n_params)))
        self.last_fit_stats["effective_dof"] = float(n_params)
        self.last_fit_stats["likelihood"] = self.likelihood_var.get()
        params_to_update: dict[str, float] = {"baseline": result.baseline, "slope": result.slope}
        if fitted_x is not None:
            for i, (key, kind, _lo, _hi) in enumerate(outer_specs):
                v = float(np.exp(fitted_x[i])) if kind == "loggamma" else float(fitted_x[i])
                params_to_update[key] = v
        if self.dist_use_sharp_var.get() and result.sharp_weights is not None:
            for idx, weight in zip(sharp_indices, result.sharp_weights):
                params_to_update[f"s{idx}_depth"] = float(weight)
        update_progress(tr("progress.distribution_update"))
        self.set_params(params_to_update)
        self.update_plot()
        close_progress()

    def _plot_theme(self) -> dict:
        if getattr(self, "_theme_var", None) and self._theme_var.get() == "sv_ttk_dark":
            return dict(
                fig_bg="#1c1c1e", ax_bg="#2a2a2a", res_bg="#252520",
                title="#e2e8f0",
                grid="#444444", grid_alpha=0.45,
                tick="#a6adc8", spine="#6c7086",
                lbl="#a6adc8",
                res_tick="#a6adc8", res_spine="#6c7086",
                res_zero="#6c7086", res_fill="#fb923c", res_line="#fdba74",
                res_grid="#3a3a3a",
                data="#e2e8f0", baseline="#94a3b8", model="#f87171",
                leg_face="#2a2a2a", leg_edge="#6c7086", leg_text="#e2e8f0",
                no_file="#a6adc8",
                dist_line="#89b4fa", dist_fill="#89b4fa",
                dist_grid="#3a3a3a", ann="#f87171",
            )
        return dict(
            fig_bg="#f8fbff", ax_bg="#fbfdff", res_bg="#fff7ed",
            title="#083344",
            grid="#c8e4f7", grid_alpha=0.85,
            tick="#243b53", spine="#8ecae6",
            lbl="#243b53",
            res_tick="#7c2d12", res_spine="#fdba74",
            res_zero="#9a3412", res_fill="#fb923c", res_line="#ea580c",
            res_grid="#fed7aa",
            data="#0f172a", baseline="#64748b", model="#dc2626",
            leg_face="#ffffff", leg_edge="#bae6fd", leg_text="#102a43",
            no_file="#075985",
            dist_line="#2563eb", dist_fill="#60a5fa",
            dist_grid="#bfdbfe", ann="#991b1b",
        )

    def update_plot_bhf_distribution(self) -> None:
        c = self._plot_theme()
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

        self.fig.set_facecolor(c["fig_bg"])
        ax.set_facecolor(c["ax_bg"])
        dist_label = "P(ΔEQ)" if self.dist_variable_var.get() == "ΔEQ" else "P(BHF)"
        ax.set_title(tr("plot.title_distribution", label=dist_label), color=c["title"], pad=10, fontweight="bold")
        ax.set_ylabel(tr("plot.transmission_ylabel"))
        ax.yaxis.label.set_color(c["lbl"])
        ax.grid(True, color=c["grid"], alpha=c["grid_alpha"], linewidth=0.8)
        ax.tick_params(colors=c["tick"])
        for spine in ax.spines.values():
            spine.set_color(c["spine"])

        if self.velocity is not None and self.y_data is not None:
            ax.plot(self.velocity, self.y_data, ".", color=c["data"], ms=4, alpha=0.88, label=tr("plot.legend_data"))
            baseline_line = self.vars["baseline"].get() + self.vars["slope"].get() * self.velocity
            ax.plot(self.velocity, baseline_line, ":", color=c["baseline"], lw=1.25, label=tr("plot.legend_baseline"))
            if self.last_bhf_fit is not None:
                fit = self.last_bhf_fit.fitted_curve
                sharp_abs_sum = np.zeros_like(self.velocity, dtype=float)
                if self.last_bhf_fit.sharp_weights is not None and self.last_bhf_fit.sharp_weights.size:
                    comp_colors = {1: "#16a34a", 2: "#f97316", 3: "#8b5cf6"}
                    for idx, weight in zip(self.last_bhf_sharp_indices, self.last_bhf_fit.sharp_weights):
                        p = f"s{idx}_"
                        params = np.array([self.vars[p + name].get() for name in SEXTET_PARAM_NAMES], dtype=float)
                        params[6] = float(weight)
                        kind = self.component_kind[idx].get()
                        sharp_abs = component_absorption(self.velocity, kind, params)
                        sharp_abs_sum += sharp_abs
                        sharp_curve = baseline_line - sharp_abs
                        ax.plot(self.velocity, sharp_curve, "--", color=comp_colors.get(idx, "#16a34a"), lw=1.45, alpha=0.9, label=tr("plot.legend_sharp_component", idx=idx, kind=tr(f"kind.{kind}", default=kind)))
                if np.any(sharp_abs_sum > 0):
                    distribution_curve = fit + sharp_abs_sum
                    ax.plot(self.velocity, distribution_curve, "--", color=c["dist_line"], lw=1.7, alpha=0.95, label=tr("plot.legend_distribution_component"))
                ax.plot(self.velocity, fit, "-", color=c["model"], lw=2.4, label=tr("plot.legend_total_fit"))
                residual = self.y_data - fit
                if ax_res is not None:
                    ax_res.set_facecolor(c["res_bg"])
                    ax_res.axhline(0, color=c["res_zero"], lw=0.9, alpha=0.9)
                    ax_res.fill_between(self.velocity, residual, 0, color=c["res_fill"], alpha=0.22)
                    ax_res.plot(self.velocity, residual, "-", color=c["res_line"], lw=1.15)
                    ax_res.set_ylabel(tr("plot.residual_ylabel"))
                    ax_res.yaxis.label.set_color(c["lbl"])
                    ax_res.tick_params(colors=c["res_tick"])
                    for spine in ax_res.spines.values():
                        spine.set_color(c["res_spine"])
                    ax_res.grid(True, color=c["res_grid"], alpha=0.8, linewidth=0.75)
                    lim = max(float(np.nanmax(np.abs(residual))) * 1.18, 1e-6)
                    ax_res.set_ylim(-lim, lim)
                    ax.tick_params(labelbottom=False)
                if ax_dist is not None:
                    ax_dist.set_facecolor(c["ax_bg"])
                    ax_dist.plot(self.last_bhf_fit.bhf_centers, self.last_bhf_fit.probability, "-o", ms=3.0, color=c["dist_line"])
                    ax_dist.fill_between(self.last_bhf_fit.bhf_centers, self.last_bhf_fit.probability, 0, color=c["dist_fill"], alpha=0.25)
                    # Banda de error 1σ de P (mejora 11), recortada a P≥0.
                    wsig = getattr(self.last_bhf_fit, "weight_sigma", None)
                    if wsig is not None and np.size(wsig) == self.last_bhf_fit.weights.size:
                        area = float(np.trapezoid(self.last_bhf_fit.weights, self.last_bhf_fit.bhf_centers))
                        if np.isfinite(area) and area > 0:
                            prob_sigma = np.asarray(wsig, dtype=float) / area
                            lo_band = np.clip(self.last_bhf_fit.probability - prob_sigma, 0.0, None)
                            hi_band = self.last_bhf_fit.probability + prob_sigma
                            ax_dist.fill_between(self.last_bhf_fit.bhf_centers, lo_band, hi_band, color=c["dist_line"], alpha=0.18, linewidth=0)
                    if self.last_bhf_fit.sharp_bhf_centers is not None and self.last_bhf_fit.sharp_weights is not None:
                        ymax = max(float(np.nanmax(self.last_bhf_fit.probability)), 1e-12)
                        for b, w in zip(self.last_bhf_fit.sharp_bhf_centers, self.last_bhf_fit.sharp_weights):
                            if np.isfinite(float(b)):
                                ax_dist.axvline(float(b), color=c["model"], lw=1.4, ls="--", alpha=0.85)
                                ax_dist.text(float(b), ymax * 0.92, tr("plot.sharp_annotation", weight=float(w)), rotation=90, va="top", ha="right", color=c["ann"], fontsize=8)
                    ax_dist.set_xlabel(tr("plot.distribution_xlabel_deq") if self.dist_variable_var.get() == "ΔEQ" else tr("plot.distribution_xlabel_bhf"))
                    ax_dist.set_ylabel(dist_label)
                    ax_dist.xaxis.label.set_color(c["lbl"])
                    ax_dist.yaxis.label.set_color(c["lbl"])
                    ax_dist.tick_params(colors=c["tick"])
                    for spine in ax_dist.spines.values():
                        spine.set_color(c["spine"])
                    ax_dist.grid(True, color=c["dist_grid"], alpha=0.8, linewidth=0.75)
                rms = self.last_bhf_fit.rms
            else:
                # Sin ajuste todavía (o invalidado al editar a mano): previsualizar
                # en vivo los sextetes/componentes activos con sus parámetros
                # actuales, para poder centrarlos antes de ajustar la distribución.
                comp_colors = {1: "#16a34a", 2: "#f97316", 3: "#8b5cf6", 4: "#e11d48", 5: "#0891b2", 6: "#ca8a04"}
                rng = self._component_range() if hasattr(self, "_component_range") else range(1, 4)
                preview_sum = np.zeros_like(self.velocity, dtype=float)
                any_preview = False
                for idx in (rng if getattr(self, "_simulate_enabled", True) else []):
                    if idx not in self.sextet_enabled or not self.sextet_enabled[idx].get():
                        continue
                    p = f"s{idx}_"
                    params = np.array([self.vars[p + name].get() for name in SEXTET_PARAM_NAMES], dtype=float)
                    kind = self.component_kind[idx].get()
                    extras = self.sextet_extras(idx) if (kind == "Sextete" and hasattr(self, "sextet_extras")) else None
                    abs_c = component_absorption(self.velocity, kind, params, extras=extras)
                    preview_sum += abs_c
                    any_preview = True
                    ax.plot(self.velocity, baseline_line - abs_c, "--",
                            color=comp_colors.get(idx, "#16a34a"), lw=1.4, alpha=0.9,
                            label=tr("plot.legend_sharp_component", idx=idx, kind=tr(f"kind.{kind}", default=kind)))
                if any_preview:
                    ax.plot(self.velocity, baseline_line - preview_sum, "-", color=c["model"], lw=1.8, alpha=0.9,
                            label=tr("plot.legend_preview"))
                ax.text(0.5, 0.06, tr("plot.click_fit_pbhf"), transform=ax.transAxes, ha="center", color=c["no_file"], fontsize=11, fontweight="bold")
                ax.set_xlabel(tr("plot.velocity_xlabel"))
                ax.xaxis.label.set_color(c["lbl"])
                rms = float("nan")
            if self.show_legend_var.get():
                leg = ax.legend(loc="best", frameon=True, facecolor=c["leg_face"], edgecolor=c["leg_edge"], framealpha=0.85)
                leg.set_draggable(True)
                for text in leg.get_texts():
                    text.set_color(c["leg_text"])
            self.update_info_bhf_distribution(rms)
        else:
            ax.text(0.5, 0.5, tr("plot.no_file"), transform=ax.transAxes, ha="center", va="center", color=c["no_file"], fontsize=14, fontweight="bold")
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
        if self.velocity is not None and self.velocity.size > 1:
            v = np.linspace(float(np.min(self.velocity)), float(np.max(self.velocity)), max(2000, int(self.velocity.size) * 8))
        else:
            v = np.linspace(-12.0, 12.0, 4000)
        dist_abs = np.zeros_like(v, dtype=float)
        variable = self.dist_variable_var.get()
        for center, weight in zip(self.last_bhf_fit.bhf_centers, self.last_bhf_fit.weights):
            if variable == "ΔEQ":
                params = np.array([self.vars["dist_delta"].get(), float(center), self.vars["dist_fixed_bhf"].get(), gamma, 1.0, 1.0, max(float(weight), 0.0), 1.0, 1.0, 1.0], dtype=float)
            else:
                params = np.array([self.vars["dist_delta"].get(), self.vars["dist_quad"].get(), float(center), gamma, 1.0, 1.0, max(float(weight), 0.0), 1.0, 1.0, 1.0], dtype=float)
            dist_abs += component_absorption(v, "Sextete", params)
        dist_area = float(np.trapezoid(np.maximum(dist_abs, 0.0), v))

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
        dist_label = "P(ΔEQ)" if self.dist_variable_var.get() == "ΔEQ" else "P(BHF)"
        dist_unit = "mm/s" if self.dist_variable_var.get() == "ΔEQ" else "T"
        shape_disp = tr(f"shape.{self.dist_shape_var.get()}", default=self.dist_shape_var.get())
        text = [
            tr("info.file", name=self.file_path.name if self.file_path else "-"),
            tr("info.dist_mode", label=dist_label, shape=shape_disp),
            tr("info.folding_center", center=f"{self.vars['center'].get():.5f}"),
            tr("info.vmax", value=f"{self.vars['vmax'].get():.6g}"),
            tr("info.baseline", value=f"{self.vars['baseline'].get():.6g}"),
            tr("info.slope", value=f"{self.vars['slope'].get():.6g}"),
            tr("info.dist_delta_quad", delta=self.vars['dist_delta'].get(), quad=self.vars['dist_quad'].get()),
            tr("info.dist_bhf_gamma", bhf=self.vars['dist_fixed_bhf'].get(), gamma=self.vars['dist_gamma'].get()),
            tr("info.dist_range", bmin=self.vars['dist_bmin'].get(), bmax=self.vars['dist_bmax'].get(), unit=dist_unit),
            tr("info.dist_bins", n=int(round(self.vars['dist_nbins'].get()))),
            tr("info.dist_alpha", alpha=self.dist_alpha(), log_alpha=self.vars['dist_log_alpha'].get()),
            (tr("info.dist_sharp_yes", indices=", ".join(map(str, self.last_bhf_sharp_indices or self.active_sharp_component_indices_for_bhf())))
             if self.dist_use_sharp_var.get() else tr("info.dist_sharp_no")),
            tr("info.rms", value=f"{rms:.6g}"),
        ]
        stats = self.last_fit_stats
        if stats:
            text.extend([
                tr("info.chi2_line", red_chi2=f"{stats.get('red_chi2', float('nan')):.6g}", chi2=f"{stats.get('chi2', float('nan')):.6g}", dof=f"{stats.get('dof', float('nan')):.0f}"),
                tr("info.aic_bic_line", aic=f"{stats.get('aic', float('nan')):.6g}", bic=f"{stats.get('bic', float('nan')):.6g}", n_params=f"{stats.get('n_params', float('nan')):.0f}"),
                tr("info.residual_diag", lag1=f"{stats.get('resid_lag1', float('nan')):.3f}", z=f"{stats.get('resid_runs_z', float('nan')):.3f}", antisym=f"{stats.get('resid_antisym_corr', float('nan')):.3f}"),
                tr("info.model_comparison"),
                tr("info.multistart_count", n=f"{stats.get('n_starts', 1.0):.0f}"),
            ])
            if abs(stats.get('resid_lag1', 0.0)) > 0.35 or abs(stats.get('resid_runs_z', 0.0)) > 2.0 or stats.get('resid_antisym_corr', 0.0) > 0.45:
                text.extend([
                    tr("info.residual_warning_1"),
                    tr("info.residual_warning_2"),
                ])
        cal_unc = self.calibration_uncertainty_text()
        if cal_unc:
            text.append(cal_unc)
        if self.last_bhf_fit is not None:
            fitted_center = getattr(self.last_bhf_fit, "fitted_dist_center", None)
            fitted_sigma = getattr(self.last_bhf_fit, "fitted_dist_sigma", None)
            fitted_p = getattr(self.last_bhf_fit, "fitted_dist_p", None)
            if fitted_center is not None or fitted_sigma is not None or fitted_p is not None:
                parts = []
                if fitted_center is not None:
                    parts.append(f"center={fitted_center:.4g} {dist_unit}")
                if fitted_sigma is not None:
                    parts.append(f"sigma={fitted_sigma:.4g} {dist_unit}")
                if fitted_p is not None:
                    parts.append(f"p={fitted_p:.4g}")
                if parts:
                    text.append(f"{shape_disp}: " + ", ".join(parts))
            peak = float(self.last_bhf_fit.bhf_centers[int(np.argmax(self.last_bhf_fit.weights))])
            area = float(np.trapezoid(self.last_bhf_fit.weights, self.last_bhf_fit.bhf_centers))
            dist_area, sharp_areas, dist_pct, sharp_pct = self.bhf_component_area_percentages()
            text.extend([
                tr("info.dist_peak", label=dist_label, peak=peak, unit=dist_unit),
                tr("info.dist_p_area", area=area),
                "",
                tr("info.dist_area_header"),
                tr("info.dist_area_line", label=dist_label, pct=dist_pct, area=dist_area),
            ])
            for idx, kind, pct in sharp_pct:
                sharp_area = next((a for i, _k, a in sharp_areas if i == idx), 0.0)
                text.append(tr("info.dist_sharp_line", idx=idx, kind=tr(f"kind.{kind}", default=kind), pct=pct, area=sharp_area))
            if self.last_bhf_fit.sharp_bhf_centers is not None and self.last_bhf_fit.sharp_weights is not None:
                for idx, b, w in zip(self.last_bhf_sharp_indices, self.last_bhf_fit.sharp_bhf_centers, self.last_bhf_fit.sharp_weights):
                    kind = self.component_kind[idx].get()
                    kind_disp = tr(f"kind.{kind}", default=kind)
                    if np.isfinite(float(b)):
                        text.append(tr("info.dist_sharp_bhf", idx=idx, kind=kind_disp, bhf=float(b), weight=float(w)))
                    else:
                        text.append(tr("info.dist_sharp_no_bhf", idx=idx, kind=kind_disp, weight=float(w)))
                    text.append(tr("info.dist_sharp_params", idx=idx, delta=self.vars[f's{idx}_delta'].get(), quad=self.vars[f's{idx}_quad'].get(), gamma=self.vars[f's{idx}_gamma1'].get()))
        self.info.delete("1.0", tk.END)
        self.info.insert(tk.END, "\n".join(text))

    def update_plot(self) -> None:
        if self.fit_mode_var.get() == "bhf_distribution":
            self.update_plot_bhf_distribution()
            return
        c = self._plot_theme()
        self.fig.clear()
        show_residual = self.show_residual_var.get()
        if show_residual:
            gs = self.fig.add_gridspec(2, 1, height_ratios=[4.8, 1.05], hspace=0.08)
            self.ax = self.fig.add_subplot(gs[0])
            self.ax_res = self.fig.add_subplot(gs[1], sharex=self.ax)
        else:
            self.ax = self.fig.add_subplot(111)
            self.ax_res = None

        self.fig.set_facecolor(c["fig_bg"])
        self.ax.set_facecolor(c["ax_bg"])
        self.ax.set_title(tr("plot.title_discrete"), color=c["title"], pad=10, fontweight="bold")
        self.ax.set_ylabel(tr("plot.transmission_ylabel"))
        self.ax.yaxis.label.set_color(c["lbl"])
        self.ax.grid(True, color=c["grid"], alpha=c["grid_alpha"], linewidth=0.8)
        self.ax.tick_params(colors=c["tick"])
        for spine in self.ax.spines.values():
            spine.set_color(c["spine"])

        if self.ax_res is not None:
            self.ax_res.set_facecolor(c["res_bg"])
            self.ax_res.set_ylabel(tr("plot.residual_ylabel"))
            self.ax_res.set_xlabel(tr("plot.velocity_xlabel"))
            self.ax_res.yaxis.label.set_color(c["lbl"])
            self.ax_res.xaxis.label.set_color(c["lbl"])
            self.ax_res.grid(True, color=c["res_grid"], alpha=0.8, linewidth=0.75)
            self.ax_res.tick_params(colors=c["res_tick"])
            for spine in self.ax_res.spines.values():
                spine.set_color(c["res_spine"])
        else:
            self.ax.set_xlabel(tr("plot.velocity_xlabel"))
            self.ax.xaxis.label.set_color(c["lbl"])

        if self.velocity is not None and self.y_data is not None:
            model = self.current_model()
            self.ax.plot(self.velocity, self.y_data, ".", color=c["data"], ms=4, alpha=0.88, label=tr("plot.legend_data"))
            if model is not None:
                baseline_line = self.vars["baseline"].get() + self.vars["slope"].get() * self.velocity
                self.ax.plot(self.velocity, baseline_line, ":", color=c["baseline"], lw=1.35, label=tr("plot.legend_baseline"))

                component_colors = {1: "#16a34a", 2: "#f97316", 3: "#8b5cf6"}
                for idx in (1, 2, 3):
                    if not self.sextet_enabled[idx].get():
                        continue
                    p = f"s{idx}_"
                    params = np.array([self.vars[p + name].get() for name in SEXTET_PARAM_NAMES], dtype=float)
                    kind = self.component_kind[idx].get()
                    component = baseline_line - component_absorption(self.velocity, kind, params)
                    self.ax.plot(
                        self.velocity, component, "--",
                        color=component_colors[idx], lw=1.65, alpha=0.95,
                        label=f"{tr(f'kind.{kind}', default=kind)} {idx}",
                    )

                self.ax.plot(self.velocity, model, "-", color=c["model"], lw=2.6, label=tr("plot.legend_model"))
                residual = self.y_data - model
                rms = float(np.sqrt(np.mean(residual ** 2)))
                if self.ax_res is not None:
                    self.ax_res.axhline(0, color=c["res_zero"], lw=0.9, alpha=0.9)
                    self.ax_res.fill_between(self.velocity, residual, 0, color=c["res_fill"], alpha=0.22)
                    self.ax_res.plot(self.velocity, residual, "-", color=c["res_line"], lw=1.25)
                    lim = max(float(np.nanmax(np.abs(residual))) * 1.18, 1e-6)
                    self.ax_res.set_ylim(-lim, lim)
                    self.ax.tick_params(labelbottom=False)
            else:
                rms = float("nan")
            if self.show_legend_var.get():
                leg = self.ax.legend(loc="best", frameon=True, facecolor=c["leg_face"], edgecolor=c["leg_edge"], framealpha=0.85)
                leg.set_draggable(True)
                for text in leg.get_texts():
                    text.set_color(c["leg_text"])
            self.update_info(rms)
        else:
            self.ax.text(0.5, 0.5, tr("plot.no_file"), transform=self.ax.transAxes,
                         ha="center", va="center", color=c["no_file"], fontsize=14, fontweight="bold")
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
            tr("info.file", name=self.file_path.name if self.file_path else "-"),
            tr("info.channels_read", n=self.counts.size),
            tr("info.folding_center", center=f"{center:.5f}"),
            tr("info.folding_normos", value=f"{2.0 * center:.5f}"),
            tr("info.folded_pairs", n=len(self.pairs)),
            tr("info.normalization", factor=f"{self.norm_factor:.6g}"),
            tr("info.vmax", value=f"{self.vars['vmax'].get():.6g}"),
            tr("info.baseline", value=f"{self.vars['baseline'].get():.6g}"),
            tr("info.slope", value=f"{self.vars['slope'].get():.6g}"),
            tr("info.active_sextets", list=", ".join(map(str, active))),
            tr("info.fit_velocity_yes") if self.fit_velocity_var.get() else tr("info.fit_velocity_no"),
            tr("info.rms", value=f"{rms:.6g}"),
        ]
        stats = self.last_fit_stats
        if stats:
            text.extend([
                tr("info.chi2_line", red_chi2=f"{stats.get('red_chi2', float('nan')):.6g}", chi2=f"{stats.get('chi2', float('nan')):.6g}", dof=f"{stats.get('dof', float('nan')):.0f}"),
                tr("info.aic_bic_line", aic=f"{stats.get('aic', float('nan')):.6g}", bic=f"{stats.get('bic', float('nan')):.6g}", n_params=f"{stats.get('n_params', float('nan')):.0f}"),
                tr("info.residual_diag", lag1=f"{stats.get('resid_lag1', float('nan')):.3f}", z=f"{stats.get('resid_runs_z', float('nan')):.3f}", antisym=f"{stats.get('resid_antisym_corr', float('nan')):.3f}"),
                tr("info.model_comparison"),
                tr("info.multistart_count", n=f"{stats.get('n_starts', 1.0):.0f}"),
            ])
            if abs(stats.get('resid_lag1', 0.0)) > 0.35 or abs(stats.get('resid_runs_z', 0.0)) > 2.0 or stats.get('resid_antisym_corr', 0.0) > 0.45:
                text.extend([
                    tr("info.residual_warning_1"),
                    tr("info.residual_warning_2"),
                ])
        cal_unc = self.calibration_uncertainty_text()
        if cal_unc:
            text.append(cal_unc)
        corr = self.last_fit_correlations
        if corr:
            max_pair = corr.get("max_pair") or []
            if max_pair:
                text.append(tr("info.max_correlation", value=f"{float(corr.get('max_abs_corr', 0.0)):.3f}", p1=max_pair[0], p2=max_pair[1]))
            high_pairs = corr.get("high_pairs") or []
            if high_pairs:
                text.append(tr("info.correlation_warning"))
                for pair in high_pairs[:6]:
                    text.append(f"  {pair['param1']} ↔ {pair['param2']}: r={float(pair['corr']):.3f}")
                if len(high_pairs) > 6:
                    text.append(tr("info.correlation_more", n=len(high_pairs) - 6))
        text.append("")
        if len(pct_active) > 1:
            text.append(tr("info.area_percent_header"))
            for idx, area, pct in zip(pct_active, areas, percentages):
                err = pct_errors.get(idx)
                err_txt = f" ± {err:.3g}%" if err is not None else ""
                kind_disp = tr(f"kind.{self.component_kind[idx].get()}", default=self.component_kind[idx].get())
                text.append(tr("info.component_percent_line", idx=idx, kind=kind_disp, pct=pct, err_txt=err_txt, area=area))
            text.append("")
        iso_ref = self.calibration_iso_ref()
        for idx in active:
            p = f"s{idx}_"
            i1 = self.vars[p + 'int1'].get()
            i2_real = i1 * (2/3) * self.vars[p + 'int2'].get()
            i3_real = i1 * (1/3) * self.vars[p + 'int3'].get()
            g1 = self.vars[p + 'gamma1'].get()
            g2 = g1 * self.vars[p + 'gamma2'].get()
            g3 = g1 * self.vars[p + 'gamma3'].get()
            f1, f2, f3 = 2.0 * g1, 2.0 * g2, 2.0 * g3
            kind_disp = tr(f"kind.{self.component_kind[idx].get()}", default=self.component_kind[idx].get())
            text.extend([
                tr("info.component_params_line", kind=kind_disp, idx=idx, bhf=self.vars[p+'bhf'].get(), delta=self.vars[p+'delta'].get(), quad=self.vars[p+'quad'].get()),
                tr("info.gamma_hwhm", g1=g1, g2=g2, g3=g3),
                tr("info.fwhm_equiv", f1=f1, f2=f2, f3=f3),
                tr("info.gamma_rel", gamma2=self.vars[p+'gamma2'].get(), gamma3=self.vars[p+'gamma3'].get()),
                tr("info.depth_intensities", depth=self.vars[p+'depth'].get(), i1=i1, i2=i2_real, i3=i3_real),
            ])
            if iso_ref is not None:
                text.append(tr("info.delta_corrected", value=f"{self.vars[p+'delta'].get() - iso_ref:.6g}", ref=f"{iso_ref:.6g}"))
        text.extend(["", tr("info.fixed_line", fixed=(", ".join(fixed) if fixed else tr("info.none")))])
        cons = self.enabled_constraints()
        if cons:
            text.append("")
            text.append(tr("info.constraints_header"))
            for c in cons:
                text.append(tr("info.constraint_line", target=c['target'], factor=float(c.get('factor', 1.0)), source=c['source'], offset=float(c.get('offset', 0.0))))
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
            "intensity_mode": {str(k): v.get() for k, v in getattr(self, "intensity_mode", {}).items()},
            "quad_treatment": {str(k): v.get() for k, v in getattr(self, "quad_treatment", {}).items()},
            "fit_velocity": bool(self.fit_velocity_var.get()),
            "fit_center": bool(self.fit_center_var.get()),
            "show_residual": bool(self.show_residual_var.get()),
            "show_legend": bool(self.show_legend_var.get()),
            "fit_mode": self.fit_mode_var.get(),
            "line_profile": self.line_profile_var.get(),
            "likelihood": self.likelihood_var.get(),
            "robust_loss": self.robust_loss_var.get(),
            "propagate_calib": bool(self.propagate_calib_var.get()),
            "global_opt": bool(self.global_opt_var.get()),
            "dist_variable": self.dist_variable_var.get(),
            "dist_shape": self.dist_shape_var.get(),
            "dist_reg_mode": self.dist_reg_mode_var.get(),
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
            "fit_statistics": self.last_fit_stats,
            "correlations": self.last_fit_correlations,
            "info_text": info_text,
        }
        return {
            "version": 1,
            "program": "mossbauer_fe33_gui_v2IA.py",
            "file_path": str(self.file_path) if self.file_path else None,
            "file_name": self.file_path.name if self.file_path else None,
            "counts": self.counts.tolist() if self.counts is not None else None,
            "calibration": self.calibration_info,
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
            self.current_file_var.set(data.get("file_name") or (file_path.name if file_path else tr("text.session_no_file")))
            self.counts = np.array(data["counts"], dtype=float)
        else:
            raise ValueError(tr("msg.session_no_file"))

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
        for idx, value in state.get("intensity_mode", {}).items():
            i = int(idx)
            if i in self.intensity_mode and value in ("free", "texture"):
                self.intensity_mode[i].set(value)
        for idx, value in state.get("quad_treatment", {}).items():
            i = int(idx)
            if i in self.quad_treatment and value in ("1st_order", "kundig_fixed", "kundig_powder"):
                self.quad_treatment[i].set(value)
        self.fit_velocity_var.set(bool(state.get("fit_velocity", self.fit_velocity_var.get())))
        self.fit_center_var.set(bool(state.get("fit_center", self.fit_center_var.get())))
        self.show_residual_var.set(bool(state.get("show_residual", self.show_residual_var.get())))
        self.show_legend_var.set(bool(state.get("show_legend", self.show_legend_var.get())))
        self.fit_mode_var.set(state.get("fit_mode", self.fit_mode_var.get()))
        self.line_profile_var.set(state.get("line_profile", self.line_profile_var.get()))
        self.on_line_profile_change()
        self.likelihood_var.set(state.get("likelihood", self.likelihood_var.get()))
        self.robust_loss_var.set(state.get("robust_loss", self.robust_loss_var.get()))
        self.propagate_calib_var.set(bool(state.get("propagate_calib", self.propagate_calib_var.get())))
        self.global_opt_var.set(bool(state.get("global_opt", self.global_opt_var.get())))
        self.dist_variable_var.set(state.get("dist_variable", self.dist_variable_var.get()))
        self.dist_shape_var.set(state.get("dist_shape", self.dist_shape_var.get()))
        self.dist_reg_mode_var.set(state.get("dist_reg_mode", self.dist_reg_mode_var.get()))
        self.fixed_distribution_path = Path(state["fixed_distribution_path"]) if state.get("fixed_distribution_path") else None
        self.dist_use_sharp_var.set(bool(state.get("dist_use_sharp", self.dist_use_sharp_var.get())))
        self.dist_refine_global_var.set(bool(state.get("dist_refine_global", self.dist_refine_global_var.get())))
        self.constraints = list(state.get("constraints", data.get("constraints", self.constraints)))
        self.updating_sliders = False

        self.calibration_info = data.get("calibration")
        self.update_calibration_label()
        if self.calibration_info:
            cal_v = self.calibration_info.get("velocity_calibrated")
            if cal_v not in (None, "") and "vmax" in self.vars:
                try:
                    if abs(float(cal_v) - float(self.vars["vmax"].get())) > 1e-3:
                        messagebox.showwarning(
                            tr("msg.calibration_title"),
                            tr("msg.calibration_mismatch", session=self.vars['vmax'].get(), calib=float(cal_v), id=self.calibration_info.get('calibration_id')),
                        )
                except (TypeError, ValueError):
                    pass

        last_fit = data.get("last_fit", {})
        self.last_fit_free_keys = list(last_fit.get("free_keys", []))
        cov = last_fit.get("covariance")
        self.last_fit_cov = np.array(cov, dtype=float) if cov is not None else None
        self.last_fit_param_errors = {k: float(v) for k, v in last_fit.get("parameter_errors", {}).items()}
        self.last_fit_stats = {k: float(v) for k, v in last_fit.get("fit_statistics", {}).items()}
        self.last_fit_correlations = last_fit.get("correlations", {}) if isinstance(last_fit.get("correlations", {}), dict) else {}

        self._refresh_distribution_tab_visibility(update=False)
        self.refold_data()
        self._refresh_intensity_mode_widgets()
        self._refresh_quad_treatment_widgets()
        # Sesión cargada: mostrar el modelo restaurado (anula el reset de load_ws5).
        self._simulate_enabled = True
        self.update_plot()
        info_text = data.get("state_and_parameters_text") or state.get("info_text") or last_fit.get("info_text")
        if info_text:
            self.info.delete("1.0", tk.END)
            self.info.insert(tk.END, info_text)
        if not loaded_file and self.file_path:
            self.current_file_var.set(tr("text.from_session", name=self.file_path.name))

    def save_session_dialog(self) -> None:
        default_name = (self.file_path.stem if self.file_path else "mossbauer") + "_session.json"
        filename = filedialog.asksaveasfilename(
            title=tr("dialog.save_session_title"),
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[(tr("filetype.json_session"), "*.json"), (tr("filetype.all"), "*")],
        )
        if not filename:
            return
        path = Path(filename)
        path.write_text(json.dumps(self.session_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
        messagebox.showinfo(tr("msg.session_saved_title"), tr("msg.session_saved", path=str(path)))

    def load_session_dialog(self) -> None:
        filename = filedialog.askopenfilename(
            title=tr("dialog.load_session_title"),
            filetypes=[(tr("filetype.json_session"), "*.json"), (tr("filetype.all"), "*")],
        )
        if not filename:
            return
        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8"))
            self.apply_session_payload(data)
        except Exception as exc:
            messagebox.showerror(tr("msg.session_load_error"), str(exc))
            return
        messagebox.showinfo(tr("msg.session_loaded_title"), tr("msg.session_loaded", path=str(filename)))

    def build_markdown_report(self) -> str:
        """Informe humano del ajuste actual en Markdown.

        No sustituye a la sesión JSON ni al .dat: resume parámetros, métricas,
        diagnóstico y trazabilidad para documentación/publicación.
        """
        from datetime import datetime

        model = self.current_model()
        residual = self.y_data - model if self.y_data is not None and model is not None else None
        stats = self.last_fit_stats or (self.fit_statistics(model - self.y_data, self.data_sigma(), 0) if self.y_data is not None and model is not None else {})
        lines: list[str] = []
        lines.append("# " + tr("report.title"))
        lines.append("")
        lines.append("- " + tr("report.date", date=datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        lines.append("- " + tr("report.program", program=f"{APP_NAME} v{APP_VERSION}"))
        lines.append("- " + tr("report.file", name=self.file_path.name if self.file_path else '-'))
        mode_detail = tr(f"shape.{self.dist_shape_var.get()}", default=self.dist_shape_var.get()) if self.fit_mode_var.get() == 'bhf_distribution' else tr("report.mode_discrete")
        lines.append("- " + tr("report.mode", mode=self.fit_mode_var.get(), detail=mode_detail))
        lines.append("- " + tr("report.profile", profile=self.line_profile_var.get()))
        lines.append("- " + tr("report.vmax", value=self.vars['vmax'].get()))
        lines.append("- " + tr("report.folding", value=self.vars['center'].get()))
        lines.append("- " + tr("report.normalization", value=self.norm_factor))
        lines.append("")

        if self.calibration_info:
            lines.append(tr("report.calibration_header"))
            lines.append("")
            cal_unc = self.calibration_uncertainty_text()
            if cal_unc:
                lines.append(f"- {cal_unc}")
                lines.append("")
            lines.append("```json")
            lines.append(json.dumps(self.calibration_info, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

        lines.append(tr("report.metrics_header"))
        lines.append("")
        if stats:
            lines.append(f"| {tr('report.metric_col')} | {tr('report.value_col')} |")
            lines.append("|---|---:|")
            for key, label in (("rms", tr("report.metric_rms")), ("chi2", tr("report.metric_chi2")), ("red_chi2", tr("report.metric_red_chi2")), ("dof", tr("report.metric_dof")), ("aic", tr("report.metric_aic")), ("bic", tr("report.metric_bic")), ("n_params", tr("report.metric_params"))):
                if key in stats:
                    lines.append(f"| {label} | {stats[key]:.8g} |")
            lines.append("")
            lines.append(tr("report.residual_diag_header"))
            lines.append("")
            lines.append(f"| {tr('report.indicator_col')} | {tr('report.value_col')} |")
            lines.append("|---|---:|")
            for key, label in (("resid_lag1", tr("report.diag_lag1")), ("resid_runs_z", tr("report.diag_runs")), ("resid_antisym_corr", tr("report.diag_antisym"))):
                if key in stats:
                    lines.append(f"| {label} | {stats[key]:.6g} |")
            lines.append("")
        else:
            lines.append(tr("report.no_metrics"))
            lines.append("")

        if self.last_fit_correlations:
            lines.append(tr("report.correlations_header"))
            lines.append("")
            corr = self.last_fit_correlations
            max_pair = corr.get("max_pair") or []
            if max_pair:
                lines.append(tr("report.max_correlation", value=float(corr.get('max_abs_corr', 0.0)), p1=max_pair[0], p2=max_pair[1]))
            high_pairs = corr.get("high_pairs") or []
            if high_pairs:
                lines.append("")
                lines.append(f"| {tr('report.corr_p1')} | {tr('report.corr_p2')} | {tr('report.corr_r')} |")
                lines.append("|---|---|---:|")
                for pair in high_pairs:
                    lines.append(f"| `{pair['param1']}` | `{pair['param2']}` | {float(pair['corr']):.5g} |")
            lines.append("")

        lines.append(tr("report.components_header"))
        lines.append("")
        if self.fit_mode_var.get() == "bhf_distribution" and self.last_bhf_fit is not None:
            dist_area, sharp_areas, dist_pct, sharp_pct = self.bhf_component_area_percentages()
            lines.append(f"| {tr('report.component_col')} | {tr('report.area_col')} | {tr('report.percent_col')} |")
            lines.append("|---|---:|---:|")
            lines.append(f"| {tr('report.distribution_row', var=self.dist_variable_var.get())} | {dist_area:.8g} | {dist_pct:.5g}% |")
            for idx, kind, pct in sharp_pct:
                area = next((a for i, _k, a in sharp_areas if i == idx), 0.0)
                kind_disp = tr(f"kind.{kind}", default=kind)
                lines.append(f"| {tr('report.sharp_row', idx=idx, kind=kind_disp)} | {area:.8g} | {pct:.5g}% |")
        else:
            active, areas, percentages = self.component_area_percentages()
            lines.append(f"| {tr('report.component_col')} | {tr('report.type_col')} | {tr('report.area_integrated_col')} | {tr('report.percent_col')} |")
            lines.append("|---:|---|---:|---:|")
            for idx, area, pct in zip(active, areas, percentages):
                kind_disp = tr(f"kind.{self.component_kind[idx].get()}", default=self.component_kind[idx].get())
                lines.append(f"| {idx} | {kind_disp} | {area:.8g} | {pct:.5g}% |")
        lines.append("")

        lines.append(tr("report.params_header"))
        lines.append("")
        lines.append(f"| {tr('report.param_col')} | {tr('report.value_col')} | {tr('report.error_col')} | {tr('report.fixed_col')} |")
        lines.append("|---|---:|---:|:---:|")
        for key in self.active_param_keys():
            err = self.last_fit_param_errors.get(key)
            err_txt = f"{err:.6g}" if err is not None else ""
            fixed = tr("yes") if self.fixed_vars.get(key, tk.BooleanVar(value=False)).get() else tr("no")
            lines.append(f"| `{key}` | {self.vars[key].get():.8g} | {err_txt} | {fixed} |")
        if self.fit_mode_var.get() == "bhf_distribution":
            for key in ("dist_delta", "dist_quad", "dist_fixed_bhf", "dist_gamma", "dist_bmin", "dist_bmax", "dist_nbins", "dist_log_alpha"):
                if key in self.vars:
                    lines.append(f"| `{key}` | {self.vars[key].get():.8g} |  |  |")
        lines.append("")

        iso_ref = self.calibration_iso_ref()
        if iso_ref is not None:
            lines.append(tr("report.iso_corrected_header", ref=f"{iso_ref:.6g}"))
            lines.append("")
            if self.fit_mode_var.get() == "bhf_distribution":
                if "dist_delta" in self.vars:
                    lines.append(tr("report.iso_corrected_row", name="dist_delta",
                                    value=f"{self.vars['dist_delta'].get() - iso_ref:.6g}"))
            else:
                rng = self._component_range() if hasattr(self, "_component_range") else (1, 2, 3)
                for idx in rng:
                    if idx in self.sextet_enabled and self.sextet_enabled[idx].get():
                        lines.append(tr("report.iso_corrected_row", name=f"s{idx}",
                                        value=f"{self.vars[f's{idx}_delta'].get() - iso_ref:.6g}"))
            lines.append("")

        if residual is not None:
            lines.append(tr("report.residual_summary_header"))
            lines.append("")
            lines.append(tr("report.residual_mean", value=float(np.mean(residual))))
            lines.append(tr("report.residual_std", value=float(np.std(residual))))
            lines.append(tr("report.residual_max", value=float(np.max(np.abs(residual)))))
            lines.append("")

        lines.append(tr("report.info_panel_header"))
        lines.append("")
        lines.append("```text")
        lines.append(self.info.get("1.0", tk.END).strip() if hasattr(self, "info") else "")
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append(tr("report.disclaimer"))
        return "\n".join(lines) + "\n"

    def export_report_pdf(self, pdf_path: Path, markdown_text: str) -> None:
        from matplotlib.backends.backend_pdf import PdfPages
        import textwrap

        with PdfPages(pdf_path) as pdf:
            lines = markdown_text.splitlines()
            page_lines: list[str] = []
            for line in lines:
                wrapped = textwrap.wrap(line, width=95) or [""]
                for w in wrapped:
                    page_lines.append(w)
                    if len(page_lines) >= 46:
                        fig = Figure(figsize=(8.27, 11.69), dpi=100, facecolor="white")
                        ax = fig.add_subplot(111)
                        ax.axis("off")
                        ax.text(0.04, 0.97, "\n".join(page_lines), va="top", ha="left", family="monospace", fontsize=8.5)
                        pdf.savefig(fig, bbox_inches="tight")
                        page_lines = []
            if page_lines:
                fig = Figure(figsize=(8.27, 11.69), dpi=100, facecolor="white")
                ax = fig.add_subplot(111)
                ax.axis("off")
                ax.text(0.04, 0.97, "\n".join(page_lines), va="top", ha="left", family="monospace", fontsize=8.5)
                pdf.savefig(fig, bbox_inches="tight")
            if getattr(self, "fig", None) is not None:
                pdf.savefig(self.fig, bbox_inches="tight")

    def export_report_dialog(self) -> None:
        default_name = (self.file_path.stem if self.file_path else "mossbauer") + "_informe.md"
        filename = filedialog.asksaveasfilename(
            title=tr("dialog.export_report"),
            initialfile=default_name,
            defaultextension=".md",
            filetypes=[(tr("filetype.markdown"), "*.md"), (tr("filetype.text"), "*.txt"), (tr("filetype.all"), "*")],
        )
        if not filename:
            return
        md_path = Path(filename)
        if md_path.suffix.lower() != ".md":
            md_path = md_path.with_suffix(".md")
        try:
            report = self.build_markdown_report()
            md_path.write_text(report, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror(tr("msg.report_title"), tr("msg.report_write_error", error=str(exc)))
            return
        pdf_msg = ""
        if messagebox.askyesno(tr("msg.report_title"), tr("msg.report_ask_pdf")):
            pdf_path = md_path.with_suffix(".pdf")
            try:
                self.export_report_pdf(pdf_path, report)
                pdf_msg = f"\nPDF: {pdf_path}"
            except Exception as exc:
                messagebox.showerror(tr("msg.report_pdf_title"), tr("msg.report_pdf_error", error=str(exc)))
                return
        messagebox.showinfo(tr("msg.report_done_title"), tr("msg.report_done", md=str(md_path), pdf_msg=pdf_msg))

    def save_fit(self) -> None:
        if self.velocity is None or self.y_data is None or self.folded_raw is None:
            return
        model = self.current_model()
        if model is None:
            return
        suffix = "_bhf_fit.dat" if self.fit_mode_var.get() == "bhf_distribution" else "_fe33_fit.dat"
        default_name = (self.file_path.stem if self.file_path else "espectro") + suffix
        filename = filedialog.asksaveasfilename(
            title=tr("dialog.save_fit_title"),
            initialfile=default_name,
            defaultextension=".dat",
            filetypes=[(tr("filetype.data"), "*.dat"), (tr("filetype.all"), "*")],
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
            if self.last_fit_stats:
                for key in ("rms", "chi2", "red_chi2", "dof", "aic", "bic", "n_params"):
                    if key in self.last_fit_stats:
                        f.write(f"# {key} = {self.last_fit_stats[key]:.10g}\n")
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
        messagebox.showinfo(tr("msg.saved_title"), tr("msg.fit_saved", path=str(filename)))


if __name__ == "__main__":
    from mossbauer_app import MossbauerApp
    app = MossbauerApp()
    app.mainloop()
