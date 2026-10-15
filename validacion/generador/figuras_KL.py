#!/usr/bin/env python3
"""Figuras de la 2ª ampliación del banco (series K y L, manual de NORMOS).

Cada fallo documentado con espectro, datos y causa; genera PNG+PDF en
validacion/informe/figuras/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

GEN = Path(__file__).resolve().parent
VALID = GEN.parent
FIG = VALID / "informe" / "figuras"
sys.path.insert(0, str(GEN))
sys.path.insert(0, str(VALID.parent))

from normos_lib import parse_plt, BHF_SCALE_SITE
from core.physics import sextet_absorption

plt.rcParams.update({"figure.dpi": 110, "font.size": 9,
                     "axes.grid": True, "grid.alpha": 0.3})


def save(fig, name: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}")


def fig_K3_cristal_unico() -> None:
    """Cristal único: SITE-IFSC vs el promedio de polvo de Fitbauer."""
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6), sharey=True)
    pw = parse_plt(VALID / "K3/K3_powder/SITE.PLT", np_ch=256)
    v = pw["velocity"]
    model = sextet_absorption(v, 0.0, 2.0, 20.0 * BHF_SCALE_SITE, 0.25,
                              1.0, 1.0, 1.0, 3.0, 2.0, 1.0,
                              treatment="hamiltonian",
                              beta=np.deg2rad(30.0), eta=0.5, phi=0.0)
    absn_pw = 1 - pw["fit"]
    model = model / np.trapezoid(model, v) * np.trapezoid(absn_pw, v)
    ax = axes[0]
    ax.plot(v, absn_pw, "k-", lw=1, label="SITE polvo (HAMILT)")
    ax.plot(v, model, "r--", lw=1,
            label="Fitbauer hamiltoniano (verdad exacta)")
    ax.plot(v, 5 * (model - absn_pw) - 0.006, "b-", lw=0.7,
            label="residuo ×5 (aprox. SITE-1994)")
    ax.set_title("Polvo: residuo = aproximación de SITE\n"
                 "(máx 6.0e-3 = 20 % del pico; η=0.5, θ=30°)")
    ax.set_xlabel("v (mm/s)"), ax.set_ylabel("absorción"), ax.legend(fontsize=7)
    ax = axes[1]
    for cid, style, lab in (("K3_sc_b0_g0", "r-", "IFSC β_γ=0"),
                            ("K3_sc_b90_g90", "b-", "IFSC β_γ=90 φ_γ=90")):
        p = parse_plt(VALID / f"K3/{cid}/SITE.PLT", np_ch=256)
        ax.plot(p["velocity"], 1 - p["fit"], style, lw=0.9, label=lab)
    ax.plot(v, absn_pw, "k--", lw=0.9, label="polvo (referencia)")
    ax.set_title("Cristal único (IFSC): intensidades ≠ polvo\n"
                 "Fitbauer promedia el haz → χ²red 3.4–8.0")
    ax.set_xlabel("v (mm/s)"), ax.legend(fontsize=7)
    save(fig, "fig_K3_cristal_unico")


def fig_K2_fondo() -> None:
    """Fondos BKG: extremo de slope (antes/después) y límite cúbico."""
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6))
    ax = axes[0]
    for cid, lab in (("K2_lin_p60", "lineal +60 (slope 7.5e-3)"),
                     ("K2_cubico", "cúbico BKG(4)=60")):
        v, th, _ = _theory("K2", cid)
        ax.plot(v, th, lw=1, label=lab)
    ax.set_title("Fondos SITE: 1 + Σ (BKG(k)/1000)·(v/2v_max)^(k−1)")
    ax.set_xlabel("v (mm/s)"), ax.set_ylabel("transmisión"), ax.legend(fontsize=7)
    ax = axes[1]
    labels = ["lineal +60\n(cota vieja ±0.005)", "lineal +60\n(cota ±0.02, v0m)",
              "cúbico\n(sin término v³)"]
    chi2 = []
    for cid, ver in (("K2_lin_p60", "v0"), ("K2_lin_p60", "v0m"),
                     ("K2_cubico", "v0")):
        r = json.loads((VALID / f"K2/{cid}/fitbauer_{ver}.json").read_text())
        chi2.append(r["stats"]["red_chi2"])
    bars = ax.bar(labels, chi2, color=["#c44", "#4a4", "#c84"])
    for b, c in zip(bars, chi2):
        ax.text(b.get_x() + b.get_width() / 2, c * 1.05, f"{c:.2g}",
                ha="center", fontsize=8)
    ax.set_yscale("log"), ax.set_ylabel("χ²red (v0 sin ruido)")
    ax.set_title("Cota de slope ampliada: 61 → 3e-7.\nEl cúbico queda en 2.5")
    save(fig, "fig_K2_fondo")


def _theory(serie, cid):
    cdir = VALID / serie / cid
    th = np.load(cdir / "teoria_norm.npy")
    info = json.loads((cdir / "verdad.json").read_text())
    v = np.linspace(-info["vmax"], info["vmax"], th.size)
    return v, th, info


def fig_L1_binomial() -> None:
    """Binomial CONC: histograma vs forma binomial en extremos y centro."""
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharey=False)
    for ax, conc in zip(axes, (10, 50, 90)):
        cid = f"L1_conc{conc:02d}"
        info = json.loads((VALID / f"L/{cid}/verdad.json").read_text())
        t = info["tablas_P"][0]
        vv, pp = np.array(t["var"]), np.maximum(np.array(t["P"]), 0)
        pp = pp / pp.sum()
        ax.bar(vv, pp, width=1.8, color="#bbb", label="verdad DIST")
        for tag, style, lab in (("v0", "r.-", "histograma"),
                                ("v0_binom_binomial", "b.-", "forma binomial")):
            f = VALID / f"L/{cid}/fit_{tag}_distribution.dat"
            if not f.exists():
                f = VALID / f"L/{cid}/fit_v0_binom_binomial_distribution.dat"
            if not f.exists():
                continue
            cols = np.loadtxt(f)
            pv = np.maximum(cols[:, 1], 0)
            ax.plot(cols[:, 0], pv / pv.sum(), style, ms=3, lw=0.9, label=lab)
        ax.set_title(f"CONC = {conc} %")
        ax.set_xlabel("B (T)")
    axes[0].set_ylabel("P(B)"), axes[0].legend(fontsize=7)
    fig.suptitle("L1 — binomial: el histograma sobre-suaviza los extremos; "
                 "la forma binomial recupera p en toda la rejilla", y=1.04)
    save(fig, "fig_L1_binomial")


def fig_L_textura_exact() -> None:
    """L6/L4: kernel 3:2:1 vs textura D23; sesgo EXACT vs QUP."""
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6))
    ax = axes[0]
    cid = "L6_d23_3"
    info = json.loads((VALID / f"L/{cid}/verdad.json").read_text())
    t = info["tablas_P"][0]
    vv, pp = np.array(t["var"]), np.maximum(np.array(t["P"]), 0)
    ax.plot(vv, pp / pp.sum(), "k-", lw=1.4, label="verdad (gauss 25/3)")
    for tag, style, lab in (("v0", "r.-", "kernel 3:2:1 (σ +47 %)"),
                            ("v0m", "g.-", "kernel --d23 3 (v0m)")):
        f = VALID / f"L/{cid}/fit_{tag}_distribution.dat"
        if f.exists():
            cols = np.loadtxt(f)
            pv = np.maximum(cols[:, 1], 0)
            ax.plot(cols[:, 0], pv / pv.sum(), style, ms=3, lw=0.9, label=lab)
    ax.set_title("L6 — textura D23=3 de DIST:\nel kernel clásico deforma P(B)")
    ax.set_xlabel("B (T)"), ax.set_ylabel("P(B)"), ax.legend(fontsize=7)
    ax = axes[1]
    qups = [0.2, 0.5, 1.0]
    std_v0, std_v0m = [], []
    from analisis import load_rows
    rows = load_rows()
    for q in qups:
        cid = f"L4_exact_q{q:g}"
        for ver, acc in (("v0", std_v0), ("v0m", std_v0m)):
            r = [x for x in rows if x["caso"] == cid and x["version"] == ver
                 and x["parametro"] == "dist_std"]
            acc.append(r[0]["ajustado"] if r else np.nan)
    ax.axhline(3.0, color="k", lw=1, label="σ verdadera")
    ax.plot(qups, std_v0, "ro-", label="kernel 3:2:1")
    ax.plot(qups, std_v0m, "go-", label="kernel --d23 3 (v0m)")
    ax.set_xlabel("QUP (mm/s)"), ax.set_ylabel("σ ajustada (T)")
    ax.set_title("L4 — EXACT: la textura efectiva 3:3:1 se corrige;\n"
                 "el residuo crece con QUP (orden mixto)")
    ax.legend(fontsize=7)
    save(fig, "fig_L_textura_exact")


def fig_K1_octete() -> None:
    """Octete NLINE=8: sexteto + 2 singletes reproducen las líneas ΔmI=±2."""
    fig, ax = plt.subplots(figsize=(7, 3.4))
    v, th, _ = _theory("K1", "K1_d73_050")
    ax.plot(v, 1 - th, "k-", lw=1, label="SITE octete D73=0.5")
    r = json.loads((VALID / "K1/K1_d73_050/fitbauer_v0.json").read_text())
    print("  K1 chi2red:", r["stats"]["red_chi2"])
    for s in (-1, 1):
        ax.axvline(s * 1.40108, color="r", ls=":", lw=1)
    ax.annotate("líneas ΔmI=±2 en ±1.401 mm/s\n(el patrón sextete de SITE "
                "implicaría ±1.406)", xy=(1.4, 0.02), fontsize=8,
                xytext=(2.5, 0.028),
                arrowprops=dict(arrowstyle="->", lw=0.8))
    ax.set_xlabel("v (mm/s)"), ax.set_ylabel("absorción")
    ax.set_title("K1 — octete: modelable como sexteto + 2 singletes "
                 "(χ²red ≈ 0.003)")
    ax.legend(fontsize=8)
    save(fig, "fig_K1_octete")


if __name__ == "__main__":
    print("Figuras K/L:")
    fig_K3_cristal_unico()
    fig_K2_fondo()
    fig_L1_binomial()
    fig_L_textura_exact()
    fig_K1_octete()


def fig_v419_mejoras() -> None:
    """v4.19: cristal único, kernel HC en distribuciones y fondo v³/v⁴."""
    from analisis import load_rows
    rows = load_rows()

    def chi2(serie, caso, ver):
        r = json.loads((VALID / f"{serie}/{caso}/fitbauer_{ver}.json")
                       .read_text())
        return r["stats"]["red_chi2"]

    fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.6))
    # (a) K3 cristal único: chi2 antes (polvo+int libres) vs despues (sc)
    ax = axes[0]
    cases = ["K3_sc_b0_g0", "K3_sc_b547_g0", "K3_sc_b90_g0", "K3_sc_b90_g90"]
    labels = ["β=0", "β=54.7", "β=90\nφ=0", "β=90\nφ=90"]
    antes = [chi2("K3", c, "v0") for c in cases]
    despues = [chi2("K3", c, "v0m") for c in cases]
    xx = np.arange(len(cases))
    ax.bar(xx - 0.18, antes, 0.36, color="#c44",
           label="polvo + int. libres (v0)")
    ax.bar(xx + 0.18, despues, 0.36, color="#4a4",
           label="hamiltonian_sc, int. FIJAS (v0m)")
    ax.axhline(1.0, color="k", lw=0.8, ls=":")
    ax.set_xticks(xx, labels, fontsize=7)
    ax.set_ylabel("χ²red"), ax.legend(fontsize=7)
    ax.set_title("K3 — cristal único (v4.19):\nresiduo restante = aprox. SITE-1994")
    # (b) L4: sigma vs QUP con los tres kernels
    ax = axes[1]
    qups = [0.2, 0.5, 1.0]
    curvas = (("v0", "kernel 1er orden", "#c44"),
              ("v0m", "1er orden + --d23 3", "#c84"),
              ("v0h", "kernel hamiltoniano (v4.19)", "#4a4"))
    for ver, lab, col in curvas:
        ys = []
        for q in qups:
            r = [x for x in rows if x["caso"] == f"L4_exact_q{q:g}"
                 and x["version"] == ver and x["parametro"] == "dist_std"]
            ys.append(r[0]["ajustado"] if r else np.nan)
        ax.plot(qups, ys, "o-", color=col, label=lab)
    ax.axhline(3.0, color="k", lw=1, label="σ verdadera")
    ax.set_xlabel("QUP (mm/s)"), ax.set_ylabel("σ ajustada (T)")
    ax.legend(fontsize=7)
    ax.set_title("L4 — EXACT de DIST:\nel kernel HC captura el orden mixto")
    # (c) K2: fondos de orden alto
    ax = axes[2]
    labels = ["cúbico\n(solo v²)", "cúbico\n(curv3, v4.19)",
              "cuártico\n(curv4, v4.19)"]
    vals = [chi2("K2", "K2_cubico", "v0"), chi2("K2", "K2_cubico", "v0m"),
            chi2("K2", "K2_cuartico", "v0")]
    bars = ax.bar(labels, np.maximum(vals, 1e-8),
                  color=["#c44", "#4a4", "#4a4"])
    for b, c in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, max(c, 1e-8) * 1.3,
                f"{c:.2g}", ha="center", fontsize=8)
    ax.set_yscale("log"), ax.set_ylabel("χ²red (v0)")
    ax.set_title("K2 — fondo BKG(4)/BKG(5):\nparidad completa")
    save(fig, "fig_v419_mejoras")
