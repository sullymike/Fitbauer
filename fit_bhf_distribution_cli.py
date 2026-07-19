#!/usr/bin/env python3
"""CLI de ajuste de distribuciones hiperfinas sin GUI.

Cubre los mismos modos que la GUI (mismo motor, ``mossbauer_distribution``):

- Variable: ``--variable bhf`` (P(BHF), por defecto) o ``--variable quad``
  (P(ΔEQ) con BHF fijo en ``--fixed-bhf``, 0 por defecto → doblete).
- Forma: ``--shape histograma|gaussiana|vbf|binomial`` (Gaussiana = VBF con
  N=1 y línea Lorentziana; ``--vbf-components`` fija N para VBF).
- Regularizador (solo histograma): ``--reg-mode tikhonov|tv|maxent``.
- Perfil de línea del kernel: ``--profile Lorentziana|Voigt`` + ``--voigt-sigma``.
- Correlación con la variable de la malla: ``--delta-slope``/``--quad-slope``.
- Distribución 2D P(BHF, ΔEQ): ``--dist-2d`` (+ ``--qmin/--qmax/--nbins-quad/
  --alpha-quad``).

Ejemplos:

    python3 fit_bhf_distribution_cli.py JA271025.ws5 --alpha 0.01 --nbins 50 --plot
    python3 fit_bhf_distribution_cli.py muestra.adt --variable quad --bmin 0 --bmax 3
    python3 fit_bhf_distribution_cli.py muestra.adt --shape vbf --vbf-components 2
    python3 fit_bhf_distribution_cli.py muestra.adt --reg-mode maxent
    python3 fit_bhf_distribution_cli.py muestra.adt --dist-2d --qmin -1 --qmax 1

Genera tres ficheros (1D):
  *_bhf_spectrum.dat       velocidad, datos, ajuste, residuo, cuentas dobladas
  *_bhf_distribution.dat   variable, P, P_normalizada
  *_bhf_summary.json       parametros y metricas
En modo 2D, la distribución se guarda como matriz *_distribution2d.dat con las
mallas en *_bhf_axis.dat / *_quad_axis.dat.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from core.param_overrides import effective_distribution_specs
from mossbauer_bhf_pipeline import make_sharp_components
from mossbauer_distribution import (
    fit_bhf_quad_distribution,
    fit_binomial_hyperfine_distribution,
    fit_hyperfine_distribution,
    fit_vbf_hyperfine_distribution,
    second_difference_matrix,
)
from mossbauer_ws5 import folded_velocity_data, read_normos_sidecar_params


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ajusta una distribucion hiperfina P(BHF)/P(ΔEQ) a un WS5 doblado.")
    parser.add_argument("input", type=Path, help="Fichero .ws5/.ADT")
    parser.add_argument("--out-prefix", type=Path, default=None, help="Prefijo de salida; por defecto <input>_bhf")
    parser.add_argument("--center", type=float, default=None, help="Centro interno de doblado. Si se omite usa .RES o busqueda chi2.")
    parser.add_argument("--vmax", type=float, default=None, help="Velocidad maxima mm/s. Si se omite usa .JOB/.PLT o 12.")
    parser.add_argument("--norm-percentile", type=float, default=90.0, help="Percentil para normalizar cuentas dobladas.")

    parser.add_argument("--variable", choices=["bhf", "quad"], default="bhf",
                        help="Variable de la distribucion: bhf → P(BHF); quad → P(ΔEQ) con BHF fijo.")
    parser.add_argument("--fixed-bhf", type=float, default=0.0,
                        help="BHF fijo (T) del kernel cuando --variable quad (0 = doblete).")
    parser.add_argument("--shape", choices=["histograma", "gaussiana", "vbf", "binomial"],
                        default="histograma",
                        help="Forma de la distribucion (gaussiana = VBF con N=1 y linea Lorentziana).")
    parser.add_argument("--vbf-components", type=int, default=2,
                        help="Numero de gaussianas del VBF (solo --shape vbf).")
    parser.add_argument("--reg-mode", choices=["tikhonov", "tv", "maxent"], default="tikhonov",
                        help="Regularizador del histograma Hesse-Rübartsch.")
    parser.add_argument("--profile", choices=["Lorentziana", "Voigt"], default="Lorentziana",
                        help="Perfil de linea del kernel.")
    parser.add_argument("--voigt-sigma", type=float, default=0.05,
                        help="Anchura gaussiana instrumental (mm/s) con --profile Voigt.")
    parser.add_argument("--delta-slope", type=float, default=0.0,
                        help="Correlacion lineal δ(H): dδ/dH (mm/s por unidad de la malla). 0 = clasico.")
    parser.add_argument("--quad-slope", type=float, default=0.0,
                        help="Correlacion lineal ΔEQ(H): dΔEQ/dH. 0 = clasico.")

    parser.add_argument("--dist-2d", action="store_true",
                        help="Distribucion bidimensional P(BHF, ΔEQ) regularizada.")
    parser.add_argument("--qmin", type=float, default=-1.0, help="ΔEQ minimo (mm/s) en modo 2D.")
    parser.add_argument("--qmax", type=float, default=1.0, help="ΔEQ maximo (mm/s) en modo 2D.")
    parser.add_argument("--nbins-quad", type=int, default=21, help="Bins de ΔEQ en modo 2D.")
    parser.add_argument("--alpha-quad", type=float, default=None,
                        help="Regularizacion en la direccion ΔEQ (2D); por defecto igual a --alpha.")

    parser.add_argument("--delta", type=float, default=None, help="CS/delta fijo. Por defecto intenta .RES o 0.")
    parser.add_argument("--quad", type=float, default=None, help="DeltaEQ fijo. Por defecto intenta .RES/.JOB o 0.")
    parser.add_argument("--gamma", type=float, default=None, help="Gamma FWHM fija. Por defecto intenta WID de .RES o 0.36.")
    parser.add_argument("--bmin", type=float, default=None,
                        help="Minimo de la malla (T para bhf, mm/s para quad). Por defecto 0.")
    parser.add_argument("--bmax", type=float, default=None,
                        help="Maximo de la malla (T para bhf, mm/s para quad). Por defecto 50 T / 3 mm/s.")
    parser.add_argument("--nbins", type=int, default=50, help="Numero de bins de la malla")
    parser.add_argument("--alpha", type=float, default=1e-2, help="Regularizacion")
    parser.add_argument("--no-fit-baseline", action="store_true", help="Fija baseline")
    parser.add_argument("--no-fit-slope", action="store_true", help="Fija slope")
    parser.add_argument("--baseline", type=float, default=None, help="Baseline inicial/fijo")
    parser.add_argument("--slope", type=float, default=0.0, help="Slope inicial/fijo")
    parser.add_argument(
        "--sharp-bhf",
        type=float,
        action="append",
        default=[],
        help="Añade un sextete nítido no regularizado con este BHF. Repetible, p.ej. --sharp-bhf 33",
    )
    parser.add_argument("--sharp-delta", type=float, default=None, help="Delta de sextetes nítidos; por defecto usa --delta")
    parser.add_argument("--sharp-quad", type=float, default=None, help="Quad de sextetes nítidos; por defecto usa --quad")
    parser.add_argument("--sharp-gamma", type=float, default=None, help="Gamma de sextetes nítidos; por defecto usa --gamma")

    parser.add_argument("--scan-alpha", action="store_true", help="Ademas escanea alpha para una L-curve simple")
    parser.add_argument("--alpha-min", type=float, default=1e-6)
    parser.add_argument("--alpha-max", type=float, default=1e2)
    parser.add_argument("--alpha-count", type=int, default=33)
    parser.add_argument("--plot", action="store_true", help="Guarda PNG con espectro y P(BHF)")
    args = parser.parse_args()
    # Validación temprana: antes se detectaba tras completar el ajuste y
    # escribir 2 de los 3 ficheros de salida (cómputo perdido, salida parcial).
    if args.scan_alpha and args.shape != "histograma":
        parser.error("--scan-alpha solo aplica a --shape histograma "
                     "(las formas paramétricas no usan alpha).")
    if args.scan_alpha and args.dist_2d:
        parser.error("--scan-alpha no aplica en modo --dist-2d.")
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
    """Ajuste 2D P(BHF, ΔEQ) y volcado de ficheros. Devuelve el summary parcial."""
    result = fit_bhf_quad_distribution(
        v, y,
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
        return fit_hyperfine_distribution(
            v, y, alpha=args.alpha,
            reg_mode=args.reg_mode,
            profile=args.profile, voigt_sigma=args.voigt_sigma,
            delta_slope=args.delta_slope, quad_slope=args.quad_slope,
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
            **common)
    if args.shape == "binomial":
        return fit_binomial_hyperfine_distribution(
            v, y, profile=args.profile, voigt_sigma=args.voigt_sigma, **common)
    raise ValueError(f"forma no reconocida: {args.shape}")


def main() -> None:
    args = parse_args()
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
    # Rango de la malla por defecto según la variable (T para BHF, mm/s para ΔEQ).
    bmin = float(args.bmin) if args.bmin is not None else 0.0
    bmax = float(args.bmax) if args.bmax is not None else (3.0 if args.variable == "quad" else 50.0)

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

    var_label = "DeltaEQ_mm_s" if args.variable == "quad" else "BHF_T"
    var_unit = "mm/s" if args.variable == "quad" else "T"

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

    dist_name = "P(ΔEQ)" if args.variable == "quad" else "P(BHF)"
    print(f"OK {dist_name} [{args.shape}]: RMS={result.rms:.6g}, "
          f"peak={summary['peak_position']:.3g} {var_unit}, alpha={args.alpha:g}")
    print(f"  espectro:     {spectrum_path}")
    print(f"  distribucion: {distribution_path}")
    print(f"  resumen:      {summary_path}")


def run_fit_1d_alpha(args, v, y, *, delta, quad, gamma, bmin, bmax,
                     sharp_components, alpha):
    """Ajuste de histograma con un alpha concreto (para --scan-alpha)."""
    return fit_hyperfine_distribution(
        v, y,
        variable=args.variable,
        delta=delta,
        quad=(0.0 if args.variable == "quad" else quad),
        bhf=args.fixed_bhf,
        gamma=gamma,
        pmin=bmin, pmax=bmax, nbins=args.nbins, alpha=alpha,
        fit_baseline=not args.no_fit_baseline,
        fit_slope=not args.no_fit_slope,
        baseline=args.baseline, slope=args.slope,
        sharp_components=sharp_components,
        reg_mode=args.reg_mode,
        profile=args.profile, voigt_sigma=args.voigt_sigma,
        delta_slope=args.delta_slope, quad_slope=args.quad_slope,
    )


def write_outputs_2d(args, in_path, out_prefix, v, y, folded, center, vmax, norm,
                     delta, quad, gamma, bmin, bmax, result) -> None:
    """Ficheros de salida del modo 2D P(BHF, ΔEQ)."""
    spectrum_path = out_prefix.with_name(out_prefix.name + "_spectrum.dat")
    matrix_path = out_prefix.with_name(out_prefix.name + "_distribution2d.dat")
    bhf_axis_path = out_prefix.with_name(out_prefix.name + "_bhf_axis.dat")
    quad_axis_path = out_prefix.with_name(out_prefix.name + "_quad_axis.dat")
    summary_path = out_prefix.with_name(out_prefix.name + "_summary.json")

    save_dat(
        spectrum_path,
        "velocidad_mm_s datos_norm ajuste_norm residuo cuentas_dobladas",
        np.column_stack([v, y, result.fitted_curve, result.residuals, folded]),
    )
    save_dat(matrix_path,
             "P_normalizada[i,j]: filas=BHF (ver _bhf_axis), columnas=DeltaEQ (ver _quad_axis)",
             np.asarray(result.probability, dtype=float))
    save_dat(bhf_axis_path, "BHF_T", np.asarray(result.bhf_centers, dtype=float))
    save_dat(quad_axis_path, "DeltaEQ_mm_s", np.asarray(result.quad_centers, dtype=float))

    summary = result.as_dict()
    for key in ("BHF_centers", "quad_centers", "P", "probability",
                "fitted_curve", "residuals", "marginal_bhf", "marginal_quad"):
        summary.pop(key, None)
    summary.update(
        {
            "input": str(in_path),
            "spectrum_file": str(spectrum_path),
            "distribution2d_file": str(matrix_path),
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

    print(f"OK P(BHF,ΔEQ) 2D: RMS={result.rms:.6g}, "
          f"<BHF>={result.mean_bhf if result.mean_bhf is None else round(result.mean_bhf, 3)} T, "
          f"<ΔEQ>={result.mean_quad if result.mean_quad is None else round(result.mean_quad, 4)} mm/s")
    print(f"  espectro:      {spectrum_path}")
    print(f"  distribucion:  {matrix_path}")
    print(f"  resumen:       {summary_path}")


if __name__ == "__main__":
    main()
