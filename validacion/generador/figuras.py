#!/usr/bin/env python3
"""Figuras del informe: cada fallo documentado con espectro, datos y causa.

Genera PNG+PDF en validacion/informe/figuras/. Usa la teoría de SITE
archivada (teoria_norm.npy) y reconstruye el modelo de Fitbauer desde los
JSON de ajuste con core.physics.
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

from analisis import load_rows, tol_v0
from normos_lib import BHF_SCALE_SITE
from core.physics import (doublet_absorption, sextet_absorption,
                          singlet_absorption)

plt.rcParams.update({"figure.dpi": 110, "font.size": 9,
                     "axes.grid": True, "grid.alpha": 0.3})


def theory_and_axis(serie: str, cid: str) -> tuple[np.ndarray, np.ndarray, dict]:
    cdir = VALID / serie / cid
    th = np.load(cdir / "teoria_norm.npy")
    info = json.loads((cdir / "verdad.json").read_text())
    v = np.linspace(-info["vmax"], info["vmax"], th.size)
    return v, th, info


def fitted_model(serie: str, cid: str, version: str = "v0"):
    """Reconstruye la curva del modelo ajustado por Fitbauer."""
    cdir = VALID / serie / cid
    fit = json.loads((cdir / f"fitbauer_{version}.json").read_text())
    info = json.loads((cdir / "verdad.json").read_text())
    vals = fit.get("values", {})
    v = np.linspace(-info["vmax"], info["vmax"],
                    np.load(cdir / "teoria_norm.npy").size)
    total = np.full_like(v, vals.get("baseline", 1.0))
    total = total + vals.get("slope", 0.0) * v
    absorb = np.zeros_like(v)
    for i, c in enumerate(info["comps"], 1):
        nline = c.get("nline", 6)
        g = lambda name, dflt=0.0: float(vals.get(f"s{i}_{name}", dflt))
        if nline == 6:
            kt = "kundig_fixed" if "kundig" in json.dumps(fit) else "1st_order"
            absorb += sextet_absorption(
                v, g("delta"), g("quad"), g("bhf", 33.0), g("gamma1", 0.25),
                g("gamma2", 1.0), g("gamma3", 1.0), g("depth", 0.02),
                g("int1", 3.0), g("int2", 2.0), 1.0,
                treatment="1st_order" if kt == "1st_order" else "kundig_fixed",
                beta=np.deg2rad(c.get("the", 0.0)))
        elif nline == 2:
            absorb += doublet_absorption(v, g("delta"), g("quad"),
                                         g("gamma1", 0.25), g("gamma2", 1.0),
                                         g("depth", 0.02), 3.0, g("int2", 1.0))
        else:
            absorb += singlet_absorption(v, g("delta"), g("gamma1", 0.25),
                                         g("depth", 0.02), 3.0)
    return v, total - absorb, fit


def save(fig, name: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{name}.png", bbox_inches="tight")
    fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"  figura: {name}")


def fig_A4_mapa() -> None:
    """Mapa de sesgos del Hamiltoniano completo axial (R × θ)."""
    rows = [r for r in load_rows("v0") if r["serie"] == "A4"]
    Rs = [0.1, 0.5, 1.0, 2.0, 10.0]
    ths = [0.0, 15.0, 30.0, 54.7, 75.0, 90.0]
    grids = {}
    for pname, scale in (("s1_bhf", None), ("s1_gamma1", None), ("s1_int2", None)):
        m = np.full((len(Rs), len(ths)), np.nan)
        for r in rows:
            if r["parametro"] != pname or r["abs_delta"] is None:
                continue
            parts = r["caso"].split("_")           # A4_R{r}_th{t}
            rr, tt = float(parts[1][1:]), float(parts[2][2:])
            m[Rs.index(rr), ths.index(tt)] = r["abs_delta"]
        grids[pname] = m
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.2))
    titles = {"s1_bhf": "|ΔBhf| (T)", "s1_gamma1": "|ΔΓ| (mm/s)",
              "s1_int2": "|Δint2| (rel. 2)"}
    for ax, (pname, m) in zip(axes, grids.items()):
        im = ax.imshow(m, aspect="auto", cmap="viridis", origin="lower")
        ax.set_xticks(range(len(ths)), [f"{t:g}" for t in ths])
        ax.set_yticks(range(len(Rs)), [f"{r:g}" for r in Rs])
        ax.set_xlabel("θ (°)"); ax.set_ylabel("R = ΔEQ/despl. magnético")
        ax.set_title(titles[pname]); ax.grid(False)
        fig.colorbar(im, ax=ax, shrink=0.85)
        for (i, j), val in np.ndenumerate(m):
            if np.isfinite(val):
                ax.text(j, i, f"{val:.2g}", ha="center", va="center",
                        fontsize=6.5,
                        color="w" if val < np.nanmax(m) * 0.6 else "k")
    fig.suptitle("A4 — sesgo del ajuste Kündig de Fitbauer sobre espectros HC de SITE "
                 "(intensidades libres)", y=1.04)
    save(fig, "fig_A4_mapa_sesgos")

    # Ejemplo ilustrativo: peor caso θ=90, R=2
    v, th, _ = theory_and_axis("A4", "A4_R2_th90")
    vf, mf, _ = fitted_model("A4", "A4_R2_th90")
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7, 5), sharex=True,
                                 height_ratios=[3, 1])
    a1.plot(v, th, "k.", ms=3, label="SITE HC (verdad)")
    a1.plot(vf, mf, "r-", lw=1, label="Fitbauer Kündig (ajuste)")
    a1.legend(); a1.set_ylabel("Transmisión")
    a1.set_title("A4_R2_th90 — SITE recalcula intensidades y transiciones ΔmI=±2;\n"
                 "el Kündig de Fitbauer solo mueve posiciones")
    a2.plot(v, th - mf, "b-", lw=0.8)
    a2.set_xlabel("v (mm/s)"); a2.set_ylabel("residuo")
    save(fig, "fig_A4_ejemplo_R2_th90")


def fig_A5_eta() -> None:
    rows = [r for r in load_rows("v0") if r["serie"] == "A5"
            and r["parametro"] in ("s1_bhf", "s1_quad", "s1_delta")]
    fig, ax = plt.subplots(figsize=(7, 4))
    marks = {"s1_bhf": ("o", "|ΔBhf| (T)"), "s1_quad": ("s", "|ΔΔEQ| (mm/s)"),
             "s1_delta": ("^", "|Δδ| (mm/s)")}
    for pname, (mk, lab) in marks.items():
        pts = {}
        for r in rows:
            if r["parametro"] != pname or r["abs_delta"] is None:
                continue
            eta = float(r["caso"].split("_")[1][3:])
            pts.setdefault(eta, []).append(r["abs_delta"])
        etas = sorted(pts)
        med = [np.median(pts[e]) for e in etas]
        mx = [np.max(pts[e]) for e in etas]
        ax.plot(etas, med, mk + "-", label=f"{lab} (mediana)")
        ax.plot(etas, mx, mk + "--", alpha=0.4, label=f"{lab} (máx)")
    ax.set_xlabel("η (asimetría del EFG)"); ax.set_yscale("log")
    ax.set_ylabel("sesgo absoluto")
    ax.set_title("A5 — sesgo al ajustar espectros con η≠0 con el modelo axial "
                 "de Fitbauer (η no soportado)")
    ax.legend(fontsize=7)
    save(fig, "fig_A5_sesgo_eta")


def fig_A6_validez() -> None:
    """Mapa de validez del 1er orden: sesgo vs R para ambos motores."""
    rows = load_rows("v0")
    Rs, b_1er, b_hc = [], [], []
    for r in sorted({rr["caso"] for rr in rows if rr["serie"] == "A6"}):
        pass
    data = {}
    for r in rows:
        if r["serie"] != "A6" or r["parametro"] != "s1_bhf":
            continue
        parts = r["caso"].split("_")
        rr = float(parts[1][1:])
        data.setdefault(parts[2], {})[rr] = r["abs_delta"]
    fig, ax = plt.subplots(figsize=(7, 4))
    for tag, lab, mk in (("1er", "SITE 1er orden ↔ Fitbauer 1er orden", "o"),
                         ("HC", "SITE HC(θ=30°) ↔ Fitbauer Kündig", "s")):
        d = data.get(tag, {})
        xs = sorted(d)
        ax.plot(xs, [d[x] for x in xs], mk + "-", label=lab)
    ax.axhline(0.05, color="r", ls=":", lw=1, label="criterio 0.05 T")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("R = interacción cuadrupolar / magnética")
    ax.set_ylabel("|ΔBhf| (T)")
    ax.set_title("A6 — validez del tratamiento de 1er orden y del Kündig con R creciente")
    ax.legend(fontsize=8)
    save(fig, "fig_A6_validez_1er_orden")


def fig_C4() -> None:
    v, th, _ = theory_and_axis("C4", "C4_g0.078")
    vf, mf, fit = fitted_model("C4", "C4_g0.078",
                               version="v0_intento_fallido")
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(v, th, "k.", ms=3, label="SITE (verdad, Γ=0.078=1 canal)")
    ax.plot(vf, mf, "r-", lw=1,
            label=f"intento 1 (multistart local): Γ clavada en el límite 0.06, "
                  f"χ²red={fit['stats'].get('red_chi2', 0):.1f}")
    v2, m2, fit2 = fitted_model("C4", "C4_g0.078")
    ax.plot(v2, m2, "g--", lw=1,
            label=f"con pre-pasada DE: χ²red={fit2['stats'].get('red_chi2', 0):.3f}")
    ax.set_xlabel("v (mm/s)"); ax.set_ylabel("Transmisión")
    ax.set_title("C4 — Γ ≈ anchura de canal: cuenca de convergencia ~Γ\n"
                 "(con arranque exacto o DE el sesgo es <4e-4 T: convergencia, no modelo)")
    ax.legend(fontsize=8)
    save(fig, "fig_C4_lineas_estrechas")


def fig_F_transmision() -> None:
    rows = load_rows("v0")
    tas, g_thick, g_thin = [], {}, {}
    for r in rows:
        if r["parametro"] != "s1_gamma1" or r["abs_delta"] is None:
            continue
        if r["serie"] == "F1":
            ta = float(r["caso"].split("_t")[1])
            g_thick[ta] = r["ajustado"]
        elif r["serie"] == "F3":
            ta = float(r["caso"].split("_t")[1].split("_")[0])
            g_thin[ta] = r["ajustado"]
    fig, ax = plt.subplots(figsize=(7, 4))
    xs = sorted(g_thick)
    ax.plot(xs, [g_thick[x] for x in xs], "o-",
            label="ajuste con saturación exponencial de Fitbauer")
    xs3 = sorted(g_thin)
    ax.plot(xs3, [g_thin[x] for x in xs3], "s--", label="ajuste modelo fino (F3)")
    ax.axhline(0.25, color="k", ls=":", label="Γ del absorbente (WID=0.25)")
    ax.axhline(0.347, color="g", ls="--", lw=1,
               label="referencia límite fino: WID+WDS = 0.347 (fuente incluida en IFTRAN)")
    ax.set_xscale("log")
    ax.set_xlabel("espesor efectivo t_a (TAB de SITE)")
    ax.set_ylabel("Γ ajustado (mm/s)")
    ax.set_title("F — integral de transmisión de SITE vs modelos de Fitbauer:\n"
                 "el ensanchamiento por espesor no es capturado por la saturación exponencial")
    ax.legend(fontsize=8)
    save(fig, "fig_F_transmision_gamma")

    # ejemplo t=10 con residuos
    v, th, _ = theory_and_axis("F1", "F1_t10")
    vf, mf, _ = fitted_model("F1", "F1_t10")
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7, 5), sharex=True,
                                 height_ratios=[3, 1])
    a1.plot(v, th, "k.", ms=3, label="SITE IFTRAN t_a=10")
    a1.plot(vf, mf, "r-", lw=1, label="Fitbauer (saturación exponencial)")
    a1.legend(); a1.set_ylabel("Transmisión")
    a2.plot(v, th - mf, "b-", lw=0.8)
    a2.set_xlabel("v (mm/s)"); a2.set_ylabel("residuo")
    a1.set_title("F1_t10 — forma de línea de transmisión gruesa")
    save(fig, "fig_F_ejemplo_t10")


def fig_E3_base() -> None:
    rows = [r for r in load_rows("v0") if r["serie"] == "E3"]
    fig, ax = plt.subplots(figsize=(7, 4))
    order = ["E3_parab_leve", "E3_parab_media", "E3_parab_fuerte", "E3_inclinada"]
    for pname, mk in (("s1_bhf", "o"), ("s1_gamma1", "s"), ("s1_depth", "^")):
        ys = []
        for cid in order:
            rr = [r for r in rows if r["caso"] == cid and r["parametro"] == pname]
            ys.append(rr[0]["abs_delta"] if rr else np.nan)
        ax.plot(range(len(order)), ys, mk + "-", label=pname)
    ax.set_xticks(range(len(order)),
                  ["parab 0.2%", "parab 0.5%", "parab 1.5%", "inclinada 0.5%"])
    ax.set_yscale("log"); ax.set_ylabel("sesgo absoluto")
    ax.set_title("E3 — base no plana: sesgo con el modelo baseline+slope de Fitbauer\n"
                 "(sin término de curvatura)")
    ax.legend(fontsize=8)
    save(fig, "fig_E3_base_no_plana")


def fig_z_hist() -> None:
    """Histograma global de z para las versiones con ruido (v1*)."""
    rows = [r for r in load_rows() if r["version"].startswith("v1")
            and r["z"] is not None and r["convergido"] == "si"]
    # solo series con modelo equivalente (sin huecos de capacidad)
    okseries = {"A1a", "A1b", "A1c", "A2", "A3a", "A3b", "A3c", "B1", "B2",
                "C1", "C2", "C4", "D1", "D2", "D3", "D5", "D6", "E1", "E2",
                "E5", "H2", "S0"}
    zs = np.array([r["z"] for r in rows if r["serie"] in okseries])
    zs = zs[np.abs(zs) < 20]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(zs, bins=80, density=True, alpha=0.7, label=f"z (n={zs.size})")
    x = np.linspace(-6, 6, 200)
    ax.plot(x, np.exp(-x**2 / 2) / np.sqrt(2 * np.pi), "r-", label="N(0,1)")
    frac1 = float(np.mean(np.abs(zs) < 1))
    frac2 = float(np.mean(np.abs(zs) < 2))
    ax.set_title(f"v1 — pull global (series con modelo equivalente): "
                 f"{100*frac1:.1f}% dentro de ±1σ, {100*frac2:.1f}% dentro de ±2σ")
    ax.set_xlabel("z = (ajustado − verdadero)/σ"); ax.set_xlim(-6, 6)
    ax.legend()
    save(fig, "fig_v1_pull_global")


def fig_H3_cobertura() -> None:
    rows = [r for r in load_rows() if r["version"].startswith("v1_r")
            and r["z"] is not None and r["convergido"] == "si"]
    by_case = {}
    for r in rows:
        by_case.setdefault(f"{r['serie']}:{r['caso']}", []).append(r["z"])
    fig, ax = plt.subplots(figsize=(7, 4))
    labels, f1s, f2s = [], [], []
    for k, zs in by_case.items():
        zs = np.array(zs)
        labels.append(k.split(":")[1])
        f1s.append(100 * np.mean(np.abs(zs) < 1))
        f2s.append(100 * np.mean(np.abs(zs) < 2))
    x = np.arange(len(labels))
    ax.bar(x - 0.18, f1s, 0.36, label="dentro de ±1σ")
    ax.bar(x + 0.18, f2s, 0.36, label="dentro de ±2σ")
    ax.axhline(68.3, color="b", ls=":"); ax.axhline(95.4, color="orange", ls=":")
    ax.set_xticks(x, labels, fontsize=7)
    ax.set_ylabel("% de parámetros·réplicas")
    ax.set_title("H3 — cobertura de las σ de Fitbauer (50 réplicas de ruido)")
    ax.legend(fontsize=8)
    save(fig, "fig_H3_cobertura")


def fig_D3_umbral() -> None:
    rows = [r for r in load_rows() if r["serie"] == "D3"
            and r["parametro"] == "s2_depth" and r["convergido"] == "si"]
    fig, ax = plt.subplots(figsize=(7, 4))
    for version, mk, lab in (("v0", "o-", "v0 (sin ruido)"),
                             ("v1", "s--", "v1 (Poisson 1e6)")):
        pts = {}
        for r in rows:
            if r["version"] != version:
                continue
            f = float(r["caso"].split("_f")[1][:-2])
            if r["verdadero"]:
                pts[f] = 100 * abs(r["ajustado"] - r["verdadero"]) / r["verdadero"]
        xs = sorted(pts)
        if xs:
            ax.plot(xs, [pts[x] for x in xs], mk, label=lab)
    ax.set_xlabel("área de la fase minoritaria (%)")
    ax.set_ylabel("error relativo del área recuperada (%)")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_title("D3 — recuperación de la fase minoritaria")
    ax.legend()
    save(fig, "fig_D3_minoritaria")


ALL_FIGS = [fig_A4_mapa, fig_A5_eta, fig_A6_validez, fig_C4,
            fig_F_transmision, fig_E3_base, fig_D3_umbral,
            fig_z_hist, fig_H3_cobertura]

if __name__ == "__main__":
    names = sys.argv[1:]
    for fn in ALL_FIGS:
        if names and fn.__name__ not in names:
            continue
        try:
            fn()
        except Exception as exc:
            print(f"  [AVISO] {fn.__name__}: {type(exc).__name__}: {exc}")
