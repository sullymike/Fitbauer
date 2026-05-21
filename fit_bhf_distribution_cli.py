#!/usr/bin/env python3
"""CLI de prueba para ajuste P(BHF) sin GUI.

Ejemplo:

    python3 fit_bhf_distribution_cli.py JA271025.ws5 --alpha 0.01 --nbins 50 --plot

Genera tres ficheros:
  *_bhf_spectrum.dat       velocidad, datos, ajuste, residuo, cuentas dobladas
  *_bhf_distribution.dat   BHF, P, P_normalizada
  *_bhf_summary.json       parametros y metricas
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from mossbauer_distribution import fit_bhf_distribution, scan_alpha, second_difference_matrix
from mossbauer_ws5 import folded_velocity_data, read_normos_sidecar_params


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ajusta una distribucion P(BHF) Hesse-Ruebartsch a un WS5 doblado.")
    parser.add_argument("input", type=Path, help="Fichero .ws5/.ADT")
    parser.add_argument("--out-prefix", type=Path, default=None, help="Prefijo de salida; por defecto <input>_bhf")
    parser.add_argument("--center", type=float, default=None, help="Centro interno de doblado. Si se omite usa .RES o busqueda chi2.")
    parser.add_argument("--vmax", type=float, default=None, help="Velocidad maxima mm/s. Si se omite usa .JOB/.PLT o 12.")
    parser.add_argument("--norm-percentile", type=float, default=90.0, help="Percentil para normalizar cuentas dobladas.")

    parser.add_argument("--delta", type=float, default=None, help="CS/delta fijo. Por defecto intenta .RES o 0.")
    parser.add_argument("--quad", type=float, default=None, help="DeltaEQ fijo. Por defecto intenta .RES/.JOB o 0.")
    parser.add_argument("--gamma", type=float, default=None, help="Gamma HWHM fija. Por defecto intenta WID/2 de .RES o 0.18.")
    parser.add_argument("--bmin", type=float, default=0.0, help="BHF minimo, T")
    parser.add_argument("--bmax", type=float, default=50.0, help="BHF maximo, T")
    parser.add_argument("--nbins", type=int, default=50, help="Numero de bins BHF")
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
    return parser.parse_args()


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


def main() -> None:
    args = parse_args()
    in_path = args.input
    out_prefix = args.out_prefix or in_path.with_suffix("")
    out_prefix = Path(str(out_prefix) + "_bhf") if args.out_prefix is None else out_prefix

    sidecar = read_normos_sidecar_params(in_path)
    delta = float(args.delta if args.delta is not None else sidecar.get("delta", 0.0))
    quad = float(args.quad if args.quad is not None else sidecar.get("quad", 0.0))
    gamma = float(args.gamma if args.gamma is not None else sidecar.get("gamma", 0.18))

    v, y, folded, center, vmax, norm = folded_velocity_data(
        in_path,
        center=args.center,
        vmax=args.vmax,
        norm_percentile=args.norm_percentile,
    )

    sharp_components = [
        {
            "bhf": float(bhf),
            "delta": float(args.sharp_delta if args.sharp_delta is not None else delta),
            "quad": float(args.sharp_quad if args.sharp_quad is not None else quad),
            "gamma": float(args.sharp_gamma if args.sharp_gamma is not None else gamma),
        }
        for bhf in args.sharp_bhf
    ]

    result = fit_bhf_distribution(
        v,
        y,
        delta=delta,
        quad=quad,
        gamma=gamma,
        bmin=args.bmin,
        bmax=args.bmax,
        nbins=args.nbins,
        alpha=args.alpha,
        fit_baseline=not args.no_fit_baseline,
        fit_slope=not args.no_fit_slope,
        baseline=args.baseline,
        slope=args.slope,
        sharp_components=sharp_components,
    )

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
        "BHF_T P_amplitud P_normalizada",
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
            "delta": delta,
            "quad": quad,
            "gamma": gamma,
            "bmin": args.bmin,
            "bmax": args.bmax,
            "nbins": args.nbins,
            "peak_bhf": float(result.bhf_centers[int(np.argmax(result.weights))]),
            "area_weights_trapz": float(np.trapezoid(result.weights, result.bhf_centers)),
            "sharp_components": [
                {"bhf": comp["bhf"], "amplitude": amp}
                for comp, amp in zip(sharp_components, [] if result.sharp_weights is None else result.sharp_weights.tolist())
            ],
        }
    )

    if args.scan_alpha:
        alphas = np.logspace(np.log10(args.alpha_min), np.log10(args.alpha_max), args.alpha_count)
        scans = scan_alpha(
            v,
            y,
            alphas,
            delta=delta,
            quad=quad,
            gamma=gamma,
            bmin=args.bmin,
            bmax=args.bmax,
            nbins=args.nbins,
            fit_baseline=not args.no_fit_baseline,
            fit_slope=not args.no_fit_slope,
            baseline=args.baseline,
            slope=args.slope,
            sharp_components=sharp_components,
        )
        L = second_difference_matrix(args.nbins)
        curve_rows = []
        for r in scans:
            misfit = float(np.linalg.norm(r.residuals))
            rough = float(np.linalg.norm(L @ r.weights))
            sharp_total = 0.0 if r.sharp_weights is None else float(np.sum(r.sharp_weights))
            curve_rows.append((r.alpha, r.rms, misfit, rough, r.baseline, r.slope, r.bhf_centers[int(np.argmax(r.weights))], sharp_total))
        curve_array = np.array(curve_rows)
        lcurve_path = out_prefix.with_name(out_prefix.name + "_alpha_scan.dat")
        save_dat(lcurve_path, "alpha rms norm_residual norm_LP baseline slope peak_BHF_T sharp_amplitude_sum", curve_array)
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

    print(f"OK P(BHF): RMS={result.rms:.6g}, peak={summary['peak_bhf']:.3g} T, alpha={args.alpha:g}")
    print(f"  espectro:     {spectrum_path}")
    print(f"  distribucion: {distribution_path}")
    print(f"  resumen:      {summary_path}")


if __name__ == "__main__":
    main()
