#!/usr/bin/env python3
"""CLI de ajuste de distribuciones hiperfinas sin GUI.

Cubre los mismos modos que la GUI (mismo motor, ``mossbauer_distribution``):

- Variable: ``--variable bhf`` (P(BHF), por defecto), ``--variable quad``
  (P(ΔEQ) con BHF fijo en ``--fixed-bhf``, 0 por defecto → doblete) o
  ``--variable delta`` (P(IS)).
- Forma: ``--shape histograma|gaussiana|vbf|binomial|czjzek|czjzek-ext|lecaer``
  (czjzek: P(ΔEQ) de un gradiente de campo aleatorio, χ de 5 grados de
  libertad; czjzek-ext: más un entorno ordenado ΔEQ₀; solo ``--variable quad``
  con dobletes). Gaussiana = VBF con
  N=1 y línea Lorentziana; ``--vbf-components`` fija N para VBF;
  ``--vbf-sigma-min``/``--vbf-sigma-max`` acotan la anchura σ común a todas
  las gaussianas, y ``--vbf-sigma-min-y``/``--vbf-sigma-max-y`` la del eje Y
  en 2D; 0 = automático; binomial =
  vecinos de soluto al estilo NORMOS-DIST ``DISTRI=3``, con
  ``--binomial-conc``/``--binomial-neighbors``/``--binomial-start``/
  ``--binomial-step`` y ``--fit-conc``).
- Regularizador (solo histograma): ``--reg-mode tikhonov|tv|maxent``.
- Física del kernel (solo histograma): ``--kernel-treatment
  1er_orden|hamiltoniano`` (+ ``--kernel-eta``) y textura ``--d13``/``--d23``
  (convenio de áreas NORMOS).
- Perfil de línea del kernel: ``--profile Lorentziana|Voigt`` + ``--voigt-sigma``.
- Correlación con la variable de la malla: ``--delta-slope``/``--quad-slope``.
- Distribuciones 2D: ``--dist-2d`` con ``--pair bhf-quad`` (P(BHF, ΔEQ), por
  defecto), ``--pair delta-quad`` (P(IS, ΔEQ)) o ``--pair bhf-delta``
  (P(BHF, IS)). La primera variable usa ``--bmin/--bmax/--nbins`` y la segunda
  ``--qmin/--qmax/--nbins-quad/--alpha-quad``.

Ejemplos:

    python3 fit_bhf_distribution_cli.py JA271025.ws5 --alpha 0.01 --nbins 50 --plot
    python3 fit_bhf_distribution_cli.py muestra.adt --variable quad --bmin 0 --bmax 3
    python3 fit_bhf_distribution_cli.py muestra.adt --shape vbf --vbf-components 2
    python3 fit_bhf_distribution_cli.py muestra.adt --shape vbf --vbf-sigma-min 0.5 --vbf-sigma-max 3
    python3 fit_bhf_distribution_cli.py muestra.adt --reg-mode maxent
    python3 fit_bhf_distribution_cli.py muestra.adt --dist-2d --qmin -1 --qmax 1
    python3 fit_bhf_distribution_cli.py muestra.adt --dist-2d --pair delta-quad

Genera tres ficheros (1D):
  *_bhf_spectrum.dat       velocidad, datos, ajuste, residuo, cuentas dobladas
  *_bhf_distribution.dat   variable, P, P_normalizada
  *_bhf_summary.json       parametros y metricas
En modo 2D, la distribución se guarda como matriz *_distribution2d.dat con las
mallas en *_<x>_axis.dat / *_<y>_axis.dat (p. ej. *_bhf_axis.dat y
*_quad_axis.dat para la pareja por defecto).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import core.blas_threads  # noqa: F401  (antes de numpy: BLAS con un hilo)
import numpy as np

from core.constants import (BHF_DEFAULT_T, DEFAULT_SEXTET_PATTERN, SEXTET_PATTERN_ALIASES,
                            SEXTET_PATTERNS, sextet_pattern)
from core.physics import intensity_convention, line_asymmetry
from core.param_overrides import effective_distribution_specs
from core.params import DIST_VAR_DEFAULT_SPAN
from mossbauer_bhf_pipeline import make_sharp_components
from mossbauer_distribution import (
    fit_bhf_quad_distribution,
    fit_vbf_2d_distribution,
    fit_binomial_hyperfine_distribution,
    fit_czjzek_hyperfine_distribution,
    fit_hyperfine_distribution,
    fit_vbf_hyperfine_distribution,
    second_difference_matrix,
)
from mossbauer_ws5 import folded_velocity_data, read_normos_sidecar_params


#: Parejas 2D admitidas (x, y), como en la GUI.
PAIRS_2D: dict[str, tuple[str, str]] = {
    "bhf-quad": ("bhf", "quad"),
    "delta-quad": ("delta", "quad"),
    "bhf-delta": ("bhf", "delta"),
}


def _span_2d(var: str, con_campo: bool) -> tuple[float, float]:
    """Rango por defecto de una variable de la malla 2D (mismo criterio que la GUI)."""
    if var == "quad":
        return DIST_VAR_DEFAULT_SPAN["quad±" if con_campo else "quad"]
    return DIST_VAR_DEFAULT_SPAN[var]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ajusta una distribución hiperfina P(BHF)/P(ΔEQ)/P(IS), 1D o 2D, a un espectro doblado.")
    parser.add_argument("input", type=Path, help="Fichero .ws5/.adt (o CSV de velocidad)")
    parser.add_argument("--out-prefix", type=Path, default=None, help="Prefijo de salida; por defecto <input>_bhf")
    parser.add_argument("--center", type=float, default=None, help="Centro interno de doblado. Si se omite usa .RES o búsqueda χ².")
    parser.add_argument("--vmax", type=float, default=None, help="Velocidad máxima (mm/s). Si se omite usa .JOB/.PLT o 12.")
    parser.add_argument("--norm-percentile", type=float, default=90.0, help="Percentil para normalizar cuentas dobladas.")

    parser.add_argument("--variable", choices=["bhf", "quad", "delta"], default="bhf",
                        help="Variable de la distribución: bhf → P(BHF); "
                             "quad → P(ΔEQ) con BHF fijo; delta → P(δ), "
                             "distribución de desplazamiento isomérico "
                             "(paridad con METHOD=8 de NORMOS-DIST; con "
                             "--fixed-bhf 0 y --quad 0 el kernel son "
                             "singletes, que es el caso de NORMOS, pero "
                             "también admite sexteto o doblete).")
    parser.add_argument("--fixed-bhf", type=float, default=0.0,
                        help="BHF fijo (T) del kernel con --variable quad/delta o --pair delta-quad (0 = doblete).")
    parser.add_argument("--shape", choices=["histograma", "gaussiana", "vbf", "binomial",
                                            "czjzek", "czjzek-ext", "lecaer"],
                        default="histograma",
                        help="Forma de la distribución (gaussiana = VBF con N=1 y línea "
                             "Lorentziana; czjzek/czjzek-ext = |ΔEQ| de un gradiente de "
                             "campo aleatorio, solo con --variable quad y dobletes; "
                             "lecaer = el mismo EFG en sextetes con campo, DISTRI=4 + "
                             "METHOD=7 de NORMOS: --variable quad con --fixed-bhf > 0, "
                             "malla en e²qQ/2 con signo).")
    parser.add_argument("--czjzek-sigma", type=float, default=None,
                        help="Czjzek: σ inicial (mm/s). Equivale a √(STG² + DTQ²) "
                             "de NORMOS-DIST.")
    parser.add_argument("--fix-czjzek-sigma", action="store_true",
                        help="Czjzek: no ajustar σ (requiere --czjzek-sigma).")
    parser.add_argument("--czjzek-delta0", type=float, default=None,
                        help="Czjzek extendido: ΔEQ₀ inicial (mm/s).")
    parser.add_argument("--fix-czjzek-delta0", action="store_true",
                        help="Czjzek extendido: no ajustar ΔEQ₀ (requiere --czjzek-delta0).")
    parser.add_argument("--binomial-conc", type=float, default=10.0,
                        help="Binomial (NORMOS DISTRI=3): concentración de soluto "
                             "en %% (CONC). Fija salvo --fit-conc.")
    parser.add_argument("--binomial-neighbors", type=int, default=12,
                        help="Binomial: nº de posiciones vecinas (NORMOS usa 12).")
    parser.add_argument("--binomial-start", type=float, default=None,
                        help="Binomial: valor de la variable sin vecinos de soluto "
                             "(BHF/QUA/ISO de NORMOS). Por defecto --bmin.")
    parser.add_argument("--binomial-step", type=float, default=None,
                        help="Binomial: cambio por vecino (DTB/DTQ/DTI de NORMOS). "
                             "Por defecto (bmax-bmin)/vecinos.")
    parser.add_argument("--fit-conc", action="store_true",
                        help="Binomial: ajustar también la concentración.")
    parser.add_argument("--vbf-components", type=int, default=2,
                        help="Número de gaussianas del VBF (solo --shape vbf).")
    parser.add_argument("--vbf-sigma-min", type=float, default=0.0,
                        help="Gaussiana/VBF: σ mínima común a todas las gaussianas, "
                             "en unidades de la variable (eje X en 2D). "
                             "0 = automático (1e-3 en 1D, ¼ de paso de malla en 2D).")
    parser.add_argument("--vbf-sigma-max", type=float, default=0.0,
                        help="Gaussiana/VBF: σ máxima común a todas las gaussianas "
                             "(eje X en 2D). 0 = automático (anchura del rango).")
    parser.add_argument("--vbf-sigma-min-y", type=float, default=0.0,
                        help="Gaussiana/VBF 2D: σ mínima del eje Y (mm/s). 0 = automático.")
    parser.add_argument("--vbf-sigma-max-y", type=float, default=0.0,
                        help="Gaussiana/VBF 2D: σ máxima del eje Y (mm/s). 0 = automático.")
    parser.add_argument("--reg-mode", choices=["tikhonov", "tv", "maxent"], default="tikhonov",
                        help="Regularizador del histograma Hesse-Rübartsch.")
    parser.add_argument("--profile", choices=["Lorentziana", "Voigt"], default="Lorentziana",
                        help="Perfil de línea del kernel.")
    parser.add_argument("--voigt-sigma", type=float, default=0.05,
                        help="Anchura gaussiana instrumental (mm/s) con --profile Voigt.")
    parser.add_argument("--delta-slope", type=float, default=0.0,
                        help="Correlación lineal δ(H): dδ/dH (mm/s por unidad de la malla). 0 = clásico.")
    parser.add_argument("--quad-slope", type=float, default=0.0,
                        help="Correlación lineal ΔEQ(H): dΔEQ/dH. 0 = clásico.")
    parser.add_argument("--d13", type=float, default=3.0,
                        help="Razón de áreas de las líneas (1,6)/(3,4) del kernel "
                             "sextete (convenio NORMOS D13; 3 = patrón "
                             "estándar). Solo --shape histograma.")
    parser.add_argument("--d23", type=float, default=2.0,
                        help="Razón de áreas de las líneas (2,5)/(3,4) del kernel "
                             "sextete (convenio NORMOS D23; 2 = polvo, 0-4 = "
                             "textura). Solo --shape histograma.")
    parser.add_argument("--kernel-treatment",
                        choices=["1er_orden", "hamiltoniano"],
                        default="1er_orden",
                        help="Física del kernel sextete: '1er_orden' clásico "
                             "o 'hamiltoniano' (promedio de polvo del "
                             "Hamiltoniano completo; --quad pasa a ser el "
                             "módulo del EFG aleatorio, análogo exacto del "
                             "EXACT/QUP de NORMOS-DIST). Solo --shape "
                             "histograma.")
    parser.add_argument("--kernel-eta", type=float, default=0.0,
                        help="Asimetría η del EFG con --kernel-treatment "
                             "hamiltoniano.")
    parser.add_argument("--source-polarized", action="store_true",
                        help="Fuente POLARIZADA (paridad METHOD=4/POLAR de "
                             "NORMOS-DIST): kernel de peine 36 líneas por "
                             "selección de helicidad. Solo --shape "
                             "histograma con --variable bhf.")
    parser.add_argument("--source-bhf", type=float, default=33.0,
                        help="Campo hiperfino de la FUENTE (T) con "
                             "--source-polarized.")
    parser.add_argument("--source-theta", type=float, default=0.0,
                        help="Ángulo fuente-haz (grados) con "
                             "--source-polarized (0 = paralelo, validado).")
    parser.add_argument("--absorber-theta", type=float, default=0.0,
                        help="Ángulo campo del absorbente-haz (grados) con "
                             "--source-polarized (0 = alineado).")

    parser.add_argument("--dist-2d", action="store_true",
                        help="Distribución bidimensional (pareja en --pair): histograma "
                             "regularizado, o con --shape gaussiana/vbf gaussianas "
                             "bivariantes (A, μ, σ, ρ).")
    parser.add_argument("--pair", choices=list(PAIRS_2D), default="bhf-quad",
                        help="Pareja de variables en modo 2D: bhf-quad → P(BHF, ΔEQ) "
                             "(por defecto), delta-quad → P(IS, ΔEQ), bhf-delta → "
                             "P(BHF, IS). La primera usa --bmin/--bmax/--nbins y la "
                             "segunda --qmin/--qmax/--nbins-quad.")
    parser.add_argument("--qmin", type=float, default=None,
                        help="Mínimo de la segunda variable en modo 2D (mm/s). Por "
                             "defecto −1 para ΔEQ con campo, 0 para ΔEQ sin campo, −1 para IS.")
    parser.add_argument("--qmax", type=float, default=None,
                        help="Máximo de la segunda variable en modo 2D (mm/s). Por "
                             "defecto 1 para ΔEQ con campo, 3 sin campo, 2 para IS.")
    parser.add_argument("--nbins-quad", type=int, default=21, help="Bins de la segunda variable en modo 2D.")
    parser.add_argument("--alpha-quad", type=float, default=None,
                        help="Regularización en la dirección de la segunda variable (2D); "
                             "por defecto igual a --alpha.")

    parser.add_argument("--delta", type=float, default=None, help="δ (desplazamiento isomérico) fijo. Por defecto intenta .RES o 0.")
    parser.add_argument("--quad", type=float, default=None, help="ΔEQ fijo. Por defecto intenta .RES/.JOB o 0.")
    parser.add_argument("--gamma", type=float, default=None, help="Γ FWHM fija. Por defecto intenta WID de .RES o 0.36.")
    parser.add_argument("--bmin", type=float, default=None,
                        help="Mínimo de la malla (T para bhf, mm/s para quad/delta). Por defecto 0 T / 0 mm/s / −1 mm/s.")
    parser.add_argument("--bmax", type=float, default=None,
                        help="Máximo de la malla (T para bhf, mm/s para quad/delta). Por defecto 50 T / 3 mm/s / 2 mm/s.")
    parser.add_argument("--nbins", type=int, default=50, help="Número de bins de la malla")
    parser.add_argument("--alpha", type=float, default=1e-2, help="Regularización α")
    parser.add_argument("--no-fit-baseline", action="store_true", help="Fija la línea base")
    parser.add_argument("--no-fit-slope", action="store_true", help="Fija la pendiente")
    parser.add_argument("--baseline", type=float, default=None, help="Línea base inicial/fija")
    parser.add_argument("--slope", type=float, default=0.0, help="Pendiente inicial/fija")
    parser.add_argument(
        "--sharp-bhf",
        type=float,
        action="append",
        default=[],
        help="Añade un sextete nítido no regularizado con este BHF. Repetible, p.ej. --sharp-bhf 33",
    )
    parser.add_argument("--sharp-delta", type=float, default=None, help="δ de los sextetes nítidos; por defecto usa --delta")
    parser.add_argument("--sharp-quad", type=float, default=None, help="ΔEQ de los sextetes nítidos; por defecto usa --quad")
    parser.add_argument("--sharp-gamma", type=float, default=None, help="Γ de los sextetes nítidos; por defecto usa --gamma")

    parser.add_argument("--scan-alpha", action="store_true", help="Además escanea α para una L-curve simple")
    parser.add_argument("--alpha-min", type=float, default=1e-6)
    parser.add_argument("--alpha-max", type=float, default=1e2)
    parser.add_argument("--alpha-count", type=int, default=33)
    parser.add_argument("--plot", action="store_true", help="Guarda PNG con el espectro y la distribución")
    parser.add_argument("--edge-anchor", type=float, default=0.0, metavar="B",
                        help="Anclaje de los extremos de la malla (BETA1/BETA2 "
                             "de NORMOS-DIST): fuerza P->0 en el primer y "
                             "último bin. 0 = sin anclaje. Útil para que el "
                             "histograma no apile peso espurio en el borde.")
    parser.add_argument("--intensity-convention", choices=("depth", "area"),
                        default="depth",
                        help="Razones de intensidad entre líneas del kernel: "
                             "'depth' (profundidad, histórico) o 'area' (AREA, "
                             "convenio D13/D23 de NORMOS). Solo difieren si las "
                             "anchuras relativas no son 1.")
    parser.add_argument("--line-asym", type=float, default=0.0, metavar="A",
                        help="Asimetría de línea por interferencia (AKS de "
                             "NORMOS-SITE): el perfil se multiplica por "
                             "1 - A*(v-v0)/Γ. 0 = línea simétrica.")
    parser.add_argument("--sextet-pattern",
                        choices=sorted(set(SEXTET_PATTERNS) | set(SEXTET_PATTERN_ALIASES)),
                        default=DEFAULT_SEXTET_PATTERN,
                        help="Patrón de posiciones del sexteto del kernel: "
                             "'normos' (derivado de los momentos nucleares, como "
                             "NORMOS-SITE; por defecto) o 'legacy' (el histórico "
                             "de Fitbauer hasta la v5.2.4; 'alpha_fe' es su "
                             "alias). Una Vmax calibrada antes de la v5.3.0 se "
                             "usa con 'legacy' o multiplicada por 0.999623.")
    args = parser.parse_args()
    # Validación temprana: antes se detectaba tras completar el ajuste y
    # escribir 2 de los 3 ficheros de salida (cómputo perdido, salida parcial).
    if args.scan_alpha and args.shape != "histograma":
        parser.error("--scan-alpha solo aplica a --shape histograma "
                     "(las formas paramétricas no usan alpha).")
    if args.scan_alpha and args.dist_2d:
        parser.error("--scan-alpha no aplica en modo --dist-2d.")
    if args.pair != "bhf-quad" and not args.dist_2d:
        parser.error("--pair solo aplica con --dist-2d.")
    if args.shape.startswith("czjzek") and (
            args.dist_2d or args.variable != "quad" or args.fixed_bhf > 0):
        parser.error("--shape czjzek/czjzek-ext solo aplica a --variable quad con "
                     "dobletes (--fixed-bhf 0), en 1D.")
    if args.shape == "lecaer" and (
            args.dist_2d or args.variable != "quad" or args.fixed_bhf <= 0):
        parser.error("--shape lecaer solo aplica a --variable quad con campo "
                     "(--fixed-bhf > 0), en 1D.")
    if args.fix_czjzek_sigma and args.czjzek_sigma is None:
        parser.error("--fix-czjzek-sigma requiere --czjzek-sigma.")
    if args.fix_czjzek_delta0 and args.czjzek_delta0 is None:
        parser.error("--fix-czjzek-delta0 requiere --czjzek-delta0.")
    if args.dist_2d and args.shape == "binomial":
        parser.error("--dist-2d admite --shape histograma, gaussiana o vbf.")
    sig_x = (args.vbf_sigma_min, args.vbf_sigma_max)
    sig_y = (args.vbf_sigma_min_y, args.vbf_sigma_max_y)
    if any(v < 0 for v in sig_x + sig_y):
        parser.error("--vbf-sigma-* no admite valores negativos (0 = automático).")
    if any(v > 0 for v in sig_x + sig_y) and args.shape not in ("gaussiana", "vbf"):
        parser.error("--vbf-sigma-* solo aplica a --shape gaussiana o vbf.")
    if any(v > 0 for v in sig_y) and not args.dist_2d:
        parser.error("--vbf-sigma-min-y/--vbf-sigma-max-y solo aplican con --dist-2d.")
    for lo, hi, name in ((*sig_x, "--vbf-sigma"), (*sig_y, "--vbf-sigma-*-y")):
        if lo > 0 and hi > 0 and hi <= lo:
            parser.error(f"{name}: σ máx ({hi:g}) debe ser mayor que σ mín ({lo:g}).")
    if (args.d13 != 3.0 or args.d23 != 2.0) and (
            args.shape != "histograma" or args.dist_2d):
        parser.error("--d13/--d23 solo aplican a --shape histograma 1D.")
    if (args.kernel_treatment != "1er_orden" and
            (args.shape != "histograma" or args.dist_2d)):
        parser.error("--kernel-treatment solo aplica a --shape histograma 1D.")
    if args.source_polarized and (
            args.shape != "histograma" or args.dist_2d
            or args.variable != "bhf"
            or args.kernel_treatment != "1er_orden"):
        parser.error("--source-polarized solo aplica a --shape histograma 1D "
                     "con --variable bhf y kernel 1er_orden.")
    return args


def save_dat(path: Path, header: str, data: np.ndarray) -> None:
    np.savetxt(path, data, header=header, comments="# ", fmt="%.10g")


def lcurve_suggest_alpha(curve_rows: np.ndarray) -> float | None:
    """Sugiere alpha por maxima curvatura en log(norm_LP) vs log(norm_residual)."""
    rows = np.asarray(curve_rows, dtype=float)
    if rows.shape[0] < 5:
        return None
    alpha = rows[:, 0]
    misfit = rows[:, 2]
    rough = rows[:, 3]
    mask = (alpha > 0) & (misfit > 0) & (rough > 0) & np.all(np.isfinite(rows[:, :4]), axis=1)
    if int(np.sum(mask)) < 5:
        return None
    a = alpha[mask]
    x = np.log(rough[mask])
    y = np.log(misfit[mask])
    t = np.log(a)
    dx = np.gradient(x, t)
    dy = np.gradient(y, t)
    ddx = np.gradient(dx, t)
    ddy = np.gradient(dy, t)
    curvature = np.abs(dx * ddy - dy * ddx) / np.maximum((dx * dx + dy * dy) ** 1.5, 1e-30)
    if not np.any(np.isfinite(curvature)):
        return None
    return float(a[int(np.nanargmax(curvature))])


def maybe_plot_lcurve(path: Path, curve_rows: np.ndarray, suggested_alpha: float | None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = np.asarray(curve_rows, dtype=float)
    alpha, rms, misfit, rough = rows[:, 0], rows[:, 1], rows[:, 2], rows[:, 3]
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(10, 4.2))
    sc = ax0.scatter(rough, misfit, c=np.log10(alpha), cmap="viridis", s=36)
    ax0.plot(rough, misfit, "-", color="0.55", lw=0.8, zorder=0)
    ax0.set_xscale("log")
    ax0.set_yscale("log")
    ax0.set_xlabel("||L P||")
    ax0.set_ylabel("||residuo||")
    ax0.set_title("L-curve")
    ax0.grid(True, alpha=0.3)
    fig.colorbar(sc, ax=ax0, label="log10(alpha)")

    ax1.loglog(alpha, rms, "-o", ms=3.5)
    if suggested_alpha is not None:
        ax1.axvline(suggested_alpha, color="crimson", ls="--", lw=1.2, label=f"sugerido {suggested_alpha:g}")
        ax1.legend()
    ax1.set_xlabel("alpha")
    ax1.set_ylabel("RMS")
    ax1.set_title("RMS vs regularizacion")
    ax1.grid(True, which="both", alpha=0.3)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def maybe_plot(path: Path, v: np.ndarray, y: np.ndarray, fit: np.ndarray, B: np.ndarray, Pn: np.ndarray) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    residual = y - fit
    fig = plt.figure(figsize=(9, 7))
    gs = fig.add_gridspec(3, 1, height_ratios=[3.0, 0.8, 1.8], hspace=0.08)
    ax = fig.add_subplot(gs[0])
    axr = fig.add_subplot(gs[1], sharex=ax)
    axp = fig.add_subplot(gs[2])

    ax.plot(v, y, ".", ms=3.5, color="black", label="datos")
    ax.plot(v, fit, "-", lw=2.0, color="crimson", label="ajuste P(BHF)")
    ax.set_ylabel("Transmision norm.")
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.tick_params(labelbottom=False)

    axr.axhline(0, color="0.35", lw=0.8)
    axr.plot(v, residual, "-", lw=1.0, color="tab:orange")
    axr.set_ylabel("res.")
    axr.set_xlabel("Velocidad (mm/s)")
    axr.grid(True, alpha=0.3)

    axp.plot(B, Pn, "-o", ms=3.0, color="tab:blue")
    axp.fill_between(B, Pn, 0, color="tab:blue", alpha=0.18)
    axp.set_xlabel("BHF (T)")
    axp.set_ylabel("P(BHF) norm.")
    axp.grid(True, alpha=0.3)

    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def run_fit_2d(args, v, y, *, delta, quad, gamma, bmin, bmax, sharp_components):
    """Ajuste 2D (pareja de --pair): histograma regularizado o gaussianas bivariantes."""
    x_var, y_var = PAIRS_2D[args.pair]
    # Sin BHF en la pareja, el kernel usa el campo fijo (0 → dobletes), como la GUI.
    kernel = dict(variable_x=x_var, variable_y=y_var,
                  bhf=(args.fixed_bhf if "bhf" not in (x_var, y_var) else BHF_DEFAULT_T))
    if args.shape in ("gaussiana", "vbf"):
        return fit_vbf_2d_distribution(
            v, y,
            n_components=(1 if args.shape == "gaussiana" else args.vbf_components),
            **kernel,
            delta=delta, quad=quad, gamma=gamma,
            bmin=bmin, bmax=bmax, nbins_bhf=args.nbins,
            qmin=args.qmin, qmax=args.qmax, nbins_quad=args.nbins_quad,
            fit_baseline=not args.no_fit_baseline,
            fit_slope=not args.no_fit_slope,
            baseline=args.baseline, slope=args.slope,
            sharp_components=sharp_components,
            profile=args.profile, voigt_sigma=args.voigt_sigma,
            sigma_x_min=args.vbf_sigma_min, sigma_x_max=args.vbf_sigma_max,
            sigma_y_min=args.vbf_sigma_min_y, sigma_y_max=args.vbf_sigma_max_y,
        )
    result = fit_bhf_quad_distribution(
        v, y,
        **kernel,
        delta=delta, quad=quad, gamma=gamma,
        bmin=bmin, bmax=bmax, nbins_bhf=args.nbins,
        qmin=args.qmin, qmax=args.qmax, nbins_quad=args.nbins_quad,
        alpha_bhf=args.alpha,
        alpha_quad=args.alpha if args.alpha_quad is None else args.alpha_quad,
        fit_baseline=not args.no_fit_baseline,
        fit_slope=not args.no_fit_slope,
        baseline=args.baseline, slope=args.slope,
        sharp_components=sharp_components,
        profile=args.profile, voigt_sigma=args.voigt_sigma,
    )
    return result


def run_fit_1d(args, v, y, *, delta, quad, gamma, bmin, bmax, sharp_components):
    """Enruta el ajuste 1D según --shape al motor moderno."""
    # --no-fit-baseline/--no-fit-slope aplican a TODAS las formas: antes solo
    # el histograma los recibía y en vbf/gaussiana/binomial se ignoraban en
    # silencio (el baseline se ajustaba libre aunque el usuario lo fijara).
    common = dict(
        variable=args.variable,
        delta=delta,
        quad=(0.0 if args.variable == "quad" else quad),
        bhf=args.fixed_bhf,
        gamma=gamma,
        pmin=bmin, pmax=bmax, nbins=args.nbins,
        baseline=args.baseline, slope=args.slope,
        fit_baseline=not args.no_fit_baseline,
        fit_slope=not args.no_fit_slope,
        sharp_components=sharp_components,
    )
    if args.shape == "histograma":
        # Textura del kernel (convenio NORMOS D13/D23, ratios de área con
        # anchuras iguales): int3_rel = 3/D13, int2_rel = 3·D23/(2·D13)
        # (banco NORMOS-2, serie L6: DIST admite D23≠2 y el kernel clásico
        # 3:2:1 sesgaba ⟨B⟩ ~1.5 T y σ hasta +4 T).
        if args.d13 <= 0:
            raise SystemExit("FAIL  --d13 debe ser > 0")
        int3_rel = 3.0 / args.d13
        int2_rel = 3.0 * args.d23 / (2.0 * args.d13)
        return fit_hyperfine_distribution(
            v, y, alpha=args.alpha,
            reg_mode=args.reg_mode, edge_anchor=args.edge_anchor,
            profile=args.profile, voigt_sigma=args.voigt_sigma,
            delta_slope=args.delta_slope, quad_slope=args.quad_slope,
            int2_rel=int2_rel, int3_rel=int3_rel,
            kernel_treatment=("polarized" if args.source_polarized
                              else "hamiltonian"
                              if args.kernel_treatment == "hamiltoniano"
                              else "1st_order"),
            kernel_eta=args.kernel_eta,
            source_bhf=args.source_bhf,
            source_theta=args.source_theta,
            absorber_theta=args.absorber_theta,
            **common)
    if args.shape in ("vbf", "gaussiana"):
        gaussian = args.shape == "gaussiana"
        return fit_vbf_hyperfine_distribution(
            v, y,
            n_components=1 if gaussian else max(1, args.vbf_components),
            profile="Lorentziana" if gaussian else args.profile,
            voigt_sigma=args.voigt_sigma,
            delta_slope=args.delta_slope, quad_slope=args.quad_slope,
            shape="Gaussiana" if gaussian else "VBF",
            sigma_min=args.vbf_sigma_min, sigma_max=args.vbf_sigma_max,
            **common)
    if args.shape in ("czjzek", "czjzek-ext", "lecaer"):
        return fit_czjzek_hyperfine_distribution(
            v, y, extended=args.shape == "czjzek-ext",
            lecaer=args.shape == "lecaer", kernel_eta=args.kernel_eta,
            czjzek_sigma=args.czjzek_sigma, fit_czjzek_sigma=not args.fix_czjzek_sigma,
            czjzek_delta0=args.czjzek_delta0, fit_czjzek_delta0=not args.fix_czjzek_delta0,
            profile=args.profile, voigt_sigma=args.voigt_sigma,
            delta_slope=args.delta_slope, quad_slope=args.quad_slope,
            **common)
    if args.shape == "binomial":
        return fit_binomial_hyperfine_distribution(
            v, y, profile=args.profile, voigt_sigma=args.voigt_sigma,
            conc=args.binomial_conc / 100.0, fit_conc=args.fit_conc,
            n_neighbors=args.binomial_neighbors,
            start=args.binomial_start, step=args.binomial_step,
            delta_slope=args.delta_slope, quad_slope=args.quad_slope,
            **common)
    raise ValueError(f"forma no reconocida: {args.shape}")


def main() -> None:
    args = parse_args()
    # El convenio de posiciones envuelve todo el ajuste y se restaura al salir.
    with sextet_pattern(args.sextet_pattern), \
            intensity_convention(args.intensity_convention), \
            line_asymmetry(args.line_asym):
        _run(args)


def _run(args) -> None:
    in_path = args.input
    if not in_path.exists():
        raise SystemExit(f"FAIL  {in_path}: fichero de espectro no encontrado")
    out_prefix = args.out_prefix or in_path.with_suffix("")
    out_prefix = Path(str(out_prefix) + "_bhf") if args.out_prefix is None else out_prefix

    sidecar = read_normos_sidecar_params(in_path)
    delta = float(args.delta if args.delta is not None else sidecar.get("delta", 0.0))
    quad = float(args.quad if args.quad is not None else sidecar.get("quad", 0.0))
    # Mismo default de Γ que la GUI y el pipeline web (fuente única en core.params).
    _gamma_default = float(effective_distribution_specs()["gamma"].default)
    gamma = float(args.gamma if args.gamma is not None else sidecar.get("gamma", _gamma_default))
    # Rango de la malla por defecto según la variable (T para BHF, mm/s para ΔEQ/IS).
    if args.dist_2d:
        x_var, y_var = PAIRS_2D[args.pair]
        con_campo = "bhf" in (x_var, y_var) or args.fixed_bhf > 0
        _rango_defecto = _span_2d(x_var, con_campo)
        _rango_y = _span_2d(y_var, con_campo)
        if args.qmin is None:
            args.qmin = _rango_y[0]
        if args.qmax is None:
            args.qmax = _rango_y[1]
    else:
        _rango_defecto = DIST_VAR_DEFAULT_SPAN[args.variable]
    bmin = float(args.bmin) if args.bmin is not None else _rango_defecto[0]
    bmax = float(args.bmax) if args.bmax is not None else _rango_defecto[1]

    v, y, folded, center, vmax, norm = folded_velocity_data(
        in_path,
        center=args.center,
        vmax=args.vmax,
        norm_percentile=args.norm_percentile,
    )

    sharp_components = make_sharp_components(
        args.sharp_bhf,
        delta=delta,
        quad=quad,
        gamma=gamma,
        sharp_delta=args.sharp_delta,
        sharp_quad=args.sharp_quad,
        sharp_gamma=args.sharp_gamma,
    )

    if args.dist_2d:
        result2d = run_fit_2d(args, v, y, delta=delta, quad=quad, gamma=gamma,
                              bmin=bmin, bmax=bmax, sharp_components=sharp_components)
        write_outputs_2d(args, in_path, out_prefix, v, y, folded, center, vmax, norm,
                         delta, quad, gamma, bmin, bmax, result2d)
        return

    result = run_fit_1d(args, v, y, delta=delta, quad=quad, gamma=gamma,
                        bmin=bmin, bmax=bmax, sharp_components=sharp_components)

    var_label = {"quad": "DeltaEQ_mm_s", "delta": "IS_mm_s"}.get(
        args.variable, "BHF_T")
    var_unit = "T" if args.variable == "bhf" else "mm/s"

    spectrum_path = out_prefix.with_name(out_prefix.name + "_spectrum.dat")
    distribution_path = out_prefix.with_name(out_prefix.name + "_distribution.dat")
    summary_path = out_prefix.with_name(out_prefix.name + "_summary.json")
    save_dat(
        spectrum_path,
        "velocidad_mm_s datos_norm ajuste_norm residuo cuentas_dobladas",
        np.column_stack([v, y, result.fitted_curve, result.residuals, folded]),
    )
    save_dat(
        distribution_path,
        f"{var_label} P_amplitud P_normalizada",
        np.column_stack([result.bhf_centers, result.weights, result.probability]),
    )

    summary = result.as_dict()
    # No duplicar arrays grandes en el resumen JSON.
    for key in ("BHF_centers", "P", "probability", "fitted_curve", "residuals"):
        summary.pop(key, None)
    summary.update(
        {
            "input": str(in_path),
            "spectrum_file": str(spectrum_path),
            "distribution_file": str(distribution_path),
            "center_internal": center,
            "center_normos_equiv": 2.0 * center,
            "vmax": vmax,
            "norm_factor": norm,
            "variable": args.variable,
            "delta": delta,
            "quad": quad,
            "gamma": gamma,
            "bmin": bmin,
            "bmax": bmax,
            "nbins": args.nbins,
            "peak_position": float(result.bhf_centers[int(np.argmax(result.weights))]),
            "area_weights_trapz": float(np.trapezoid(result.weights, result.bhf_centers)),
            "sharp_components": [
                {"bhf": comp["bhf"], "amplitude": amp}
                for comp, amp in zip(sharp_components, [] if result.sharp_weights is None else result.sharp_weights.tolist())
            ],
        }
    )
    if args.variable == "bhf":
        summary["peak_bhf"] = summary["peak_position"]  # compatibilidad
        summary["fixed_bhf"] = None
    else:
        summary["fixed_bhf"] = args.fixed_bhf
    if result.vbf_components is not None:
        summary["vbf_components"] = [list(c) for c in result.vbf_components]

    if args.scan_alpha:
        alphas = np.logspace(np.log10(args.alpha_min), np.log10(args.alpha_max), args.alpha_count)
        scans = [run_fit_1d_alpha(args, v, y, delta=delta, quad=quad, gamma=gamma,
                                  bmin=bmin, bmax=bmax,
                                  sharp_components=sharp_components, alpha=float(a))
                 for a in alphas]
        L = second_difference_matrix(args.nbins)
        curve_rows = []
        for r in scans:
            misfit = float(np.linalg.norm(r.residuals))
            rough = float(np.linalg.norm(L @ r.weights))
            sharp_total = 0.0 if r.sharp_weights is None else float(np.sum(r.sharp_weights))
            curve_rows.append((r.alpha, r.rms, misfit, rough, r.baseline, r.slope, r.bhf_centers[int(np.argmax(r.weights))], sharp_total))
        curve_array = np.array(curve_rows)
        lcurve_path = out_prefix.with_name(out_prefix.name + "_alpha_scan.dat")
        save_dat(lcurve_path, f"alpha rms norm_residual norm_LP baseline slope peak_{var_label} sharp_amplitude_sum", curve_array)
        suggested_alpha = lcurve_suggest_alpha(curve_array)
        summary["alpha_scan_file"] = str(lcurve_path)
        summary["suggested_alpha_lcurve"] = suggested_alpha
        if args.plot:
            lcurve_png_path = out_prefix.with_name(out_prefix.name + "_alpha_scan.png")
            maybe_plot_lcurve(lcurve_png_path, curve_array, suggested_alpha)
            summary["alpha_scan_plot_file"] = str(lcurve_png_path)

    if args.plot:
        png_path = out_prefix.with_name(out_prefix.name + "_plot.png")
        maybe_plot(png_path, v, y, result.fitted_curve, result.bhf_centers, result.probability)
        summary["plot_file"] = str(png_path)

    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    dist_name = {"quad": "P(ΔEQ)", "delta": "P(δ)"}.get(args.variable, "P(BHF)")
    print(f"OK {dist_name} [{args.shape}]: RMS={result.rms:.6g}, "
          f"peak={summary['peak_position']:.3g} {var_unit}, alpha={args.alpha:g}")
    print(f"  espectro:     {spectrum_path}")
    print(f"  distribución: {distribution_path}")
    print(f"  resumen:      {summary_path}")


def run_fit_1d_alpha(args, v, y, *, delta, quad, gamma, bmin, bmax,
                     sharp_components, alpha):
    """Ajuste de histograma con un alpha concreto (para --scan-alpha).

    Reutiliza ``run_fit_1d`` cambiando solo α: antes repetía la llamada a mano
    y omitía --edge-anchor, --d13/--d23, la física del kernel y la fuente
    polarizada, así que el α sugerido correspondía a otro modelo.
    """
    scan_args = argparse.Namespace(**{**vars(args), "alpha": float(alpha)})
    return run_fit_1d(scan_args, v, y, delta=delta, quad=quad, gamma=gamma,
                      bmin=bmin, bmax=bmax, sharp_components=sharp_components)


def write_outputs_2d(args, in_path, out_prefix, v, y, folded, center, vmax, norm,
                     delta, quad, gamma, bmin, bmax, result) -> None:
    """Ficheros de salida del modo 2D (pareja de --pair)."""
    x_var, y_var = PAIRS_2D[args.pair]
    nombre = {"bhf": "BHF_T", "quad": "DeltaEQ_mm_s", "delta": "IS_mm_s"}
    etiqueta = {"bhf": "BHF", "quad": "ΔEQ", "delta": "IS"}
    spectrum_path = out_prefix.with_name(out_prefix.name + "_spectrum.dat")
    matrix_path = out_prefix.with_name(out_prefix.name + "_distribution2d.dat")
    bhf_axis_path = out_prefix.with_name(out_prefix.name + f"_{x_var}_axis.dat")
    quad_axis_path = out_prefix.with_name(out_prefix.name + f"_{y_var}_axis.dat")
    summary_path = out_prefix.with_name(out_prefix.name + "_summary.json")

    save_dat(
        spectrum_path,
        "velocidad_mm_s datos_norm ajuste_norm residuo cuentas_dobladas",
        np.column_stack([v, y, result.fitted_curve, result.residuals, folded]),
    )
    save_dat(matrix_path,
             f"P_normalizada[i,j]: filas={nombre[x_var]} (ver _{x_var}_axis), "
             f"columnas={nombre[y_var]} (ver _{y_var}_axis)",
             np.asarray(result.probability, dtype=float))
    save_dat(bhf_axis_path, nombre[x_var], np.asarray(result.bhf_centers, dtype=float))
    save_dat(quad_axis_path, nombre[y_var], np.asarray(result.quad_centers, dtype=float))

    summary = result.as_dict()
    for key in ("BHF_centers", "quad_centers", "P", "probability",
                "fitted_curve", "residuals", "marginal_bhf", "marginal_quad"):
        summary.pop(key, None)
    summary.update(
        {
            "input": str(in_path),
            "spectrum_file": str(spectrum_path),
            "distribution2d_file": str(matrix_path),
            "pair": args.pair,
            "x_axis_file": str(bhf_axis_path),
            "y_axis_file": str(quad_axis_path),
            "bhf_axis_file": str(bhf_axis_path),
            "quad_axis_file": str(quad_axis_path),
            "center_internal": center,
            "center_normos_equiv": 2.0 * center,
            "vmax": vmax,
            "norm_factor": norm,
            "delta": delta,
            "quad": quad,
            "gamma": gamma,
            "bmin": bmin, "bmax": bmax, "nbins_bhf": args.nbins,
            "qmin": args.qmin, "qmax": args.qmax, "nbins_quad": args.nbins_quad,
        }
    )
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    ux = "T" if x_var == "bhf" else "mm/s"
    print(f"OK P({etiqueta[x_var]},{etiqueta[y_var]}) 2D: RMS={result.rms:.6g}, "
          f"<{etiqueta[x_var]}>={result.mean_bhf if result.mean_bhf is None else round(result.mean_bhf, 4)} {ux}, "
          f"<{etiqueta[y_var]}>={result.mean_quad if result.mean_quad is None else round(result.mean_quad, 4)} mm/s")
    for i, (a, mx, my, sx, sy, rho) in enumerate(result.vbf2d_components or (), start=1):
        print(f"  gaussiana {i}: A={a:.4g} μ=({mx:.4g} {ux}, {my:.4g} mm/s) "
              f"σ=({sx:.3g}, {sy:.3g}) ρ={rho:.3f}")
    print(f"  espectro:      {spectrum_path}")
    print(f"  distribución:  {matrix_path}")
    print(f"  resumen:       {summary_path}")


if __name__ == "__main__":
    main()
