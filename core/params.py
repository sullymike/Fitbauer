"""Registro único de parámetros del modelo Mössbauer Fe-57.

Fuente única de: orden canónico, conjuntos usados por tipo de componente,
relevancia para el ajuste, valores por defecto, rangos/resolución de los
controles de la GUI y límites del ajuste. Lo consumen la interfaz Qt
(construcción de los controles de componente) y ``core.session`` (controlador
headless: valores por defecto y construcción del ``FitState``). No depende de
ninguna GUI.
"""
from __future__ import annotations

from dataclasses import dataclass

BHF_DEFAULT_T = 33.0
MAX_COMPONENTS = 6

# Orden canónico de parámetros de componente (incluye ocultos int3/texture/beta).
PARAM_ORDER = (
    "delta", "quad", "bhf", "gamma1", "gamma2", "gamma3",
    "depth", "int1", "int2", "int3", "texture", "beta",
    "relax_fraction", "relax_log_nu",
    "neel_temp_k", "neel_log10_keff", "neel_mean_d_nm",
    "neel_sigma", "neel_log10_tau0", "neel_bins",
)
# Parámetros "clásicos" reportados por componente activo en el ajuste por lotes.
ACTIVE_PARAM_ORDER = (
    "delta", "quad", "bhf", "gamma1", "gamma2", "gamma3",
    "depth", "int1", "int2", "int3", "relax_fraction", "relax_log_nu",
    "neel_temp_k", "neel_log10_keff", "neel_mean_d_nm",
    "neel_sigma", "neel_log10_tau0", "neel_bins",
)

# Conjunto de parámetros realmente usados por cada tipo de componente.
USED_BY = {
    "Sextete": {"delta", "quad", "bhf", "gamma1", "gamma2", "gamma3",
                "depth", "int1", "int2", "texture", "beta"},
    "Doblete": {"delta", "quad", "gamma1", "gamma2", "depth", "int2"},
    "Singlete": {"delta", "gamma1", "depth"},
    # Modelo fenomenológico de relajación: mezcla de sextete bloqueado y
    # doblete superparamagnético con conservación aproximada del área.
    "Relajacion": {"delta", "quad", "bhf", "gamma1", "gamma2", "gamma3",
                   "depth", "int1", "int2", "relax_fraction", "relax_log_nu"},
    "BlumeTjon": {"delta", "quad", "bhf", "gamma1", "gamma2", "gamma3",
                  "depth", "int1", "int2", "relax_log_nu"},
    "NeelSize": {"delta", "quad", "bhf", "gamma1", "gamma2", "gamma3",
                 "depth", "int1", "int2", "neel_temp_k",
                 "neel_log10_keff", "neel_mean_d_nm", "neel_sigma",
                 "neel_log10_tau0", "neel_bins"},
}

# Tipos de componente discreto válidos. Fuente única para las whitelists de la
# GUI (selector de tipo, restauración de sesión) y la validación. El orden
# refleja el del selector de la GUI.
COMPONENT_KINDS = (
    "Sextete", "Doblete", "Singlete", "Relajacion", "BlumeTjon", "NeelSize",
)

# Formas válidas de distribución hiperfina (selector del panel y validación).
DISTRIBUTION_SHAPES = ("Histograma", "Gaussiana", "Binomial", "Fija", "2D")

# Modos válidos de intensidad relativa para sextetes.
INTENSITY_MODES = ("free", "texture")

# Tratamientos cuadrupolares válidos para sextetes.
QUAD_TREATMENTS = ("1st_order", "kundig_fixed", "kundig_powder")


@dataclass(frozen=True)
class ParamSpec:
    """Rango/resolución/valor por defecto de un control de la GUI."""

    default: float
    lo: float
    hi: float
    step: float
    decimals: int


# Especificación del control de cada parámetro de componente (lo que ve la GUI).
COMPONENT_PARAM_SPECS = {
    "delta":   ParamSpec(0.0, -2.0, 3.0, 0.001, 4),
    "quad":    ParamSpec(0.0, -4.0, 4.0, 0.001, 4),
    "bhf":     ParamSpec(BHF_DEFAULT_T, 0.0, 60.0, 0.01, 3),
    "gamma1":  ParamSpec(0.30, 0.06, 4.0, 0.001, 4),
    "gamma2":  ParamSpec(1.0, 0.2, 6.0, 0.001, 4),
    "gamma3":  ParamSpec(1.0, 0.2, 6.0, 0.001, 4),
    "depth":   ParamSpec(0.020, 0.0, 0.07, 0.0001, 5),
    "int1":    ParamSpec(3.0, 0.0, 6.0, 0.01, 3),
    "int2":    ParamSpec(2.0, 0.0, 4.0, 0.01, 3),
    "texture": ParamSpec(2.0 / 3.0, 0.0, 1.0, 0.001, 4),
    "beta":    ParamSpec(0.0, 0.0, 90.0, 0.1, 2),
    "relax_fraction": ParamSpec(1.0, 0.0, 1.0, 0.001, 4),
    "relax_log_nu": ParamSpec(5.0, 3.0, 12.0, 0.1, 2),
    "neel_temp_k": ParamSpec(300.0, 1.0, 800.0, 1.0, 1),
    "neel_log10_keff": ParamSpec(4.0, 2.0, 7.0, 0.05, 3),
    "neel_mean_d_nm": ParamSpec(8.0, 0.5, 100.0, 0.1, 3),
    "neel_sigma": ParamSpec(0.25, 0.01, 1.5, 0.01, 3),
    "neel_log10_tau0": ParamSpec(-9.0, -12.0, -6.0, 0.05, 3),
    "neel_bins": ParamSpec(20.0, 3.0, 80.0, 1.0, 0),
    "int3":    ParamSpec(1.0, 1.0, 1.0, 0.0, 3),
}
# Disposición de los controles en la GUI (dos columnas + ocultos).
# Columna izquierda: parámetros hiperfinos. Columna derecha: profundidad,
# intensidades, textura/β y los parámetros especializados (relajación / Néel).
# El bloque Néel se agrupa por significado: primero el tamaño (diámetro medio,
# anchura lognormal, nº de bins) y luego la dinámica de Arrhenius (T, K_eff, τ0).
COMPONENT_PARAM_LAYOUT = {
    "left": ("delta", "quad", "bhf", "gamma1", "gamma2", "gamma3"),
    "right": ("depth", "int1", "int2", "texture", "beta",
              "relax_fraction", "relax_log_nu",
              "neel_mean_d_nm", "neel_sigma", "neel_bins",
              "neel_temp_k", "neel_log10_keff", "neel_log10_tau0"),
    "hidden": ("int3",),
}
# La profundidad por defecto del primer componente es mayor que la del resto.
DEPTH_DEFAULT_FIRST = 0.020
DEPTH_DEFAULT_OTHERS = 0.005

# Límites del AJUSTE (más amplios que los rangos de los controles de la GUI).
GLOBAL_FIT_BOUNDS = {
    "baseline": (0.70, 1.30), "slope": (-0.005, 0.005),
    "vmax": (1.0, 15.0), "voigt_sigma": (0.0, 1.0), "sat_scale": (0.05, 50.0),
}
COMPONENT_FIT_BOUNDS = {
    "delta": (-2.0, 3.0), "quad": (-4.0, 4.0), "bhf": (0.0, 60.0),
    "gamma1": (0.06, 4.0), "gamma2": (0.2, 6.0), "gamma3": (0.2, 6.0),
    "depth": (0.0, 0.30), "int1": (0.0, 9.0), "int2": (0.0, 6.0),
    "int3": (0.0, 3.0), "texture": (0.0, 1.0), "beta": (0.0, 90.0),
    "relax_fraction": (0.0, 1.0), "relax_log_nu": (3.0, 12.0),
    "neel_temp_k": (1.0, 800.0), "neel_log10_keff": (2.0, 7.0),
    "neel_mean_d_nm": (0.5, 100.0), "neel_sigma": (0.01, 1.5),
    "neel_log10_tau0": (-12.0, -6.0), "neel_bins": (3.0, 80.0),
}


# Especificación de los controles del panel de calibración.
CALIBRATION_PARAM_SPECS: dict[str, ParamSpec] = {
    "vmax":        ParamSpec(12.007, -15.0,  15.0,  0.0001, 4),
    "center":      ParamSpec(256.5,  250.0, 263.0,  0.0001, 4),
    "baseline":    ParamSpec(1.0,      0.70,  1.30, 0.0005, 4),
    "slope":       ParamSpec(0.0,    -0.002, 0.002,  1e-5,  6),
    "voigt_sigma": ParamSpec(0.05,    0.0,   1.0,    0.001, 4),
    "sat_scale":   ParamSpec(5.0,     0.05, 50.0,    0.01,  3),
}

# Especificación de los controles del panel de distribución.
DISTRIBUTION_PARAM_SPECS: dict[str, ParamSpec] = {
    # Parámetros globales del perfil lineal
    "delta":       ParamSpec(0.0,          -2.5,  2.5,   0.001, 4),
    "quad":        ParamSpec(0.0,          -4.0,  4.0,   0.001, 4),
    "fixed_bhf":   ParamSpec(BHF_DEFAULT_T, 0.0, 60.0,   0.01,  3),
    "gamma":       ParamSpec(0.36,          0.06,  2.0,  0.001, 4),
    # Malla eje X  (BHF / ΔEQ / IS según modo)
    "bmin":        ParamSpec(0.0,    0.0,  60.0,  0.1, 2),
    "bmax":        ParamSpec(50.0,   0.0,  60.0,  0.1, 2),
    "nbins":       ParamSpec(50.0,  10.0, 100.0,  1.0, 0),
    "log_alpha":   ParamSpec(-2.0,  -8.0,   4.0,  0.1, 2),
    # Límites exteriores del eje X en modo IS (δ) y ΔEQ distribuido.
    # Controlan hasta dónde pueden llegar los sliders bmin/bmax en esos modos.
    "is_lo":       ParamSpec(-2.5, -10.0,  0.0,  0.1, 2),
    "is_hi":       ParamSpec( 2.5,   0.0, 10.0,  0.1, 2),
    "quad_lo":     ParamSpec( 0.0,  -7.0,  0.0,  0.1, 2),
    "quad_hi":     ParamSpec( 7.0,   0.0, 15.0,  0.1, 2),
    # Malla eje Y en modo 2D (ΔEQ o IS)
    "qmin":        ParamSpec(-1.0,  -4.0,  4.0, 0.01, 3),
    "qmax":        ParamSpec(1.0,   -4.0,  4.0, 0.01, 3),
    "qbins":       ParamSpec(21.0,   5.0, 80.0,  1.0, 0),
    "log_alpha_q": ParamSpec(-2.0,  -8.0,  4.0,  0.1, 2),
}

# Constante física: pesos estándar de las 6 líneas del sextete Fe-57.
SEXTET_WEIGHTS = (3.0, 2.0, 1.0, 1.0, 2.0, 3.0)

# Parámetros de inicialización automática del modelo (detección de picos → clips).
FIT_INIT_SPECS: dict[str, ParamSpec] = {
    # Límites BHF aceptables al ajustar sextetes a picos detectados
    "sextet_bhf_min":      ParamSpec(10.0,  0.0, 60.0,  0.5, 1),
    "sextet_bhf_max":      ParamSpec(60.0, 10.0, 60.0,  0.5, 1),
    "sextet_2pk_bhf_min":  ParamSpec(25.0,  0.0, 60.0,  0.5, 1),
    "init_bhf_min":        ParamSpec(20.0, 10.0, 60.0,  0.5, 1),
    # Clips de anchura, isomer shift y profundidad en la inicialización
    "init_gamma_min":      ParamSpec(0.08, 0.06,  1.0, 0.01, 3),
    "init_gamma_max":      ParamSpec(2.0,   0.3,  4.0,  0.1, 2),
    "init_delta_lo":       ParamSpec(-2.5, -5.0,  0.0,  0.1, 2),
    "init_delta_hi":       ParamSpec( 2.5,  0.0,  5.0,  0.1, 2),
    "init_depth_min":      ParamSpec(0.002, 0.0, 0.05, 0.001, 4),
    "init_depth_max":      ParamSpec(0.25,  0.05, 0.5,  0.01, 3),
    # Separación de picos para clasificar como doblete
    "doublet_sep_min":     ParamSpec(0.18, 0.05, 1.0,  0.01, 3),
    "doublet_sep_max":     ParamSpec(5.0,  1.0, 10.0,   0.1, 2),
    # L-curve: rango del barrido de α
    "lcurve_alpha_lo":     ParamSpec(-6.0, -10.0, -1.0,  0.5, 1),
    "lcurve_alpha_hi":     ParamSpec( 2.0,   0.0,  6.0,  0.5, 1),
    "lcurve_n_points":     ParamSpec(25.0,   5.0, 100.0,  1.0, 0),
    # Bootstrap
    "bootstrap_nrep":      ParamSpec(30.0,   5.0, 500.0,  5.0, 0),
    # Multistart
    "multistart_n_max":    ParamSpec(10.0,   1.0,  50.0,  1.0, 0),
}

# Umbrales de detección de picos y clasificación de componentes (avanzado).
PEAK_DETECTION_SPECS: dict[str, ParamSpec] = {
    "min_dist_factor":        ParamSpec(0.15, 0.05, 0.5,  0.01, 3),
    "height_thr_factor":      ParamSpec(0.06, 0.01, 0.3,  0.01, 3),
    "prom_thr_factor":        ParamSpec(0.05, 0.01, 0.3,  0.01, 3),
    "min_separation":         ParamSpec(0.12, 0.05, 0.5,  0.01, 3),
    "score_tol":              ParamSpec(0.45, 0.1,  2.0,  0.05, 3),
    "score_tol_factor":       ParamSpec(0.10, 0.0,  0.5,  0.01, 3),
    "narrow_tol_factor":      ParamSpec(0.50, 0.1,  1.0,  0.05, 3),
    "narrow_tol_min":         ParamSpec(0.20, 0.05, 0.5,  0.01, 3),
    "match_tol":              ParamSpec(0.18, 0.05, 0.5,  0.01, 3),
    "singlet_dominance":      ParamSpec(2.5,  1.0, 10.0,   0.1, 2),
    "doublet_ratio_min":      ParamSpec(0.40, 0.1,  0.9,  0.05, 3),
    "doublet_ratio_max":      ParamSpec(0.30, 0.1,  0.9,  0.05, 3),
    "plotly_tol_factor":      ParamSpec(1.5,  0.5,  5.0,   0.1, 2),
    "plotly_tol_min":         ParamSpec(0.05, 0.01, 0.3,  0.01, 3),
}

# Rango dinámico de la malla del histograma según la variable distribuida.
# El panel de distribución llama a set_range() con estos valores al cambiar de modo.
DIST_VAR_RANGE: dict[str, tuple[float, float]] = {
    "bhf":   (0.0,  60.0),
    "quad":  (0.0,   7.0),
    "delta": (-2.5,  2.5),
}
DIST_RANGE_RESOLUTION: float = 0.1


def component_default_value(name: str, idx: int = 1) -> float:
    """Valor por defecto de un parámetro de componente (``depth`` depende del índice)."""
    if name == "depth":
        return DEPTH_DEFAULT_FIRST if idx == 1 else DEPTH_DEFAULT_OTHERS
    return COMPONENT_PARAM_SPECS[name].default


def component_defaults(idx: int) -> dict[str, float]:
    """Valores por defecto de todos los parámetros de un componente."""
    return {name: component_default_value(name, idx) for name in PARAM_ORDER}


def relevant_params(kind: str, intensity_mode: str, quad_treatment: str) -> set[str]:
    """Parámetros realmente ajustables según tipo/modo de intensidad/cuadrupolo.

    Los no incluidos (p. ej. ``texture`` en modo libre, ``int1``/``int2`` en modo
    textura, ``beta`` salvo Kündig fijo, ``int3`` siempre) no deben ajustarse.
    """
    used = set(USED_BY.get(kind, set()))
    if kind == "Sextete":
        if intensity_mode == "texture":
            used.discard("int1")
            used.discard("int2")
        else:
            used.discard("texture")
        if quad_treatment != "kundig_fixed":
            used.discard("beta")
    else:
        used.discard("texture")
        used.discard("beta")
    return used
