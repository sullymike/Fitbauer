"""Figuras y tabla de comparación del artículo (docs/article_hyperfine_interactions.tex).

Reajusta los cuatro espectros de referencia de ``data_sample/`` con la versión
instalada de Fitbauer (mismas plantillas que el test golden) y regenera:

- ``img/fig_reference_fits.pdf``   ajustes con residuos (α-Fe, hematita, siderita, magnetita)
- ``img/fig_normos_comparison.pdf`` correlación NORMOS vs Fitbauer (B_hf, δ, Γ)
- ``img/fig_magnetita_fit.pdf``    descomposición en dos sextetes de la magnetita

y escribe en pantalla las filas de Fitbauer de la tabla ``tab:comparison``.

Los valores de NORMOS/SITE (v. 27.01.1994, ejecutado en DOSBox sobre los
mismos ficheros; ver docs/normos_dosbox_guide.md §6) se copian aquí tal cual:
NORMOS no cambia y su binario no está en el repositorio.

Uso:  python docs/article_figures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.session import HeadlessSession  # noqa: E402
from core.fit_engine import model_from_values  # noqa: E402
from core.constants import APP_VERSION  # noqa: E402

DATA = ROOT / "data_sample"
IMG = Path(__file__).resolve().parent / "img"

CASES = [
    # clave, etiqueta, plantilla, espectro
    ("alphaFe", r"(a) $\alpha$-Fe", "template_alphaFe.json", "hierro_metalico_alphaFe.adt"),
    ("hematita", r"(b) $\alpha$-Fe$_2$O$_3$", "template_hematita.json", "hematita_Fe2O3.adt"),
    ("siderita", r"(c) FeCO$_3$", "template_siderita.json", "siderita_FeCO3.adt"),
    ("magnetita", r"(d) Fe$_3$O$_4$", "template_magnetita.json", "magnetita_Fe3O4.adt"),
]

# NORMOS/SITE sobre los mismos espectros: (valor, σ). δ en bruto (respecto a la fuente).
NORMOS = {
    "alphaFe": {"s1_bhf": (33.035, 0.006), "s1_delta": (-0.110, 0.001), "s1_gamma1": (0.279, 0.002), "chi2": 1.195},
    "hematita": {"s1_bhf": (51.576, 0.007), "s1_delta": (0.262, 0.001), "s1_quad": (0.200, 0.002),
                 "s1_gamma1": (0.317, 0.003), "chi2": 1.058},
    "siderita": {"s1_delta": (1.121, 0.001), "s1_quad": (1.797, 0.002), "s1_gamma1": (0.337, 0.003), "chi2": 0.883},
    "magnetita": {"s1_bhf": (49.075, 0.010), "s1_delta": (0.159, 0.001), "s1_gamma1": (0.368, 0.006),
                  "s2_bhf": (46.079, 0.007), "s2_delta": (0.564, 0.001), "s2_gamma1": (0.549, 0.003),
                  "chi2": 1.093},
}

DELTA_ALPHA_FE = 0.110  # δ de α-Fe respecto a la fuente: corrección a la escala de α-Fe


def fit_case(template: str, spectrum: str):
    sess = HeadlessSession()
    state = json.loads((DATA / template).read_text())
    sess.apply_template_model_state(state.get("model_state", state))
    sess.load_ws5(DATA / spectrum)
    res = sess.run_fit()
    fs = sess.build_fit_state()
    v = np.asarray(fs.velocity)
    vals = dict(sess.model.vars)
    total = model_from_values(v, vals, fs.components, fs.constraints, fs.absorber_model)
    subs = []
    depth_keys = [k for k in vals if k.endswith("_depth") and k.startswith("s")]
    for i, comp in enumerate(fs.components, start=1):
        if not getattr(comp, "enabled", True) or f"s{i}_depth" not in vals:
            continue
        only = {k: (0.0 if (k in depth_keys and k != f"s{i}_depth") else val) for k, val in vals.items()}
        subs.append(model_from_values(v, only, fs.components, fs.constraints, fs.absorber_model))
    return v, np.asarray(fs.y_data), total, subs, res


def main() -> None:
    plt.rcParams.update({"font.size": 8, "axes.linewidth": 0.6, "font.family": "serif"})
    fits = {k: fit_case(t, s) for k, _, t, s in CASES}

    # ── Tabla: filas de Fitbauer ────────────────────────────────────────
    print(f"Fitbauer v{APP_VERSION}")
    for key, *_ in CASES:
        _, _, _, _, res = fits[key]
        val, err = res["values"], res["errors"]
        row = {k: f"{val[k]:.3f}({err.get(k, float('nan')):.3f})"
               for k in sorted(val) if k.split("_", 1)[-1] in ("bhf", "delta", "quad", "gamma1")
               and k[:2] in ("s1", "s2")}
        print(f"  {key:10s} chi2_red={res['stats']['red_chi2']:.3f}  {row}")

    # ── Fig. ajustes de referencia ──────────────────────────────────────
    fig = plt.figure(figsize=(7.0, 4.6))
    outer = fig.add_gridspec(2, 2, hspace=0.32, wspace=0.22)
    for n, (key, label, *_rest) in enumerate(CASES):
        v, y, total, _subs, res = fits[key]
        o = np.argsort(v)
        g = outer[n // 2, n % 2].subgridspec(2, 1, height_ratios=[3.2, 1], hspace=0.05)
        ax, axr = fig.add_subplot(g[0]), fig.add_subplot(g[1])
        ax.plot(v, y, ".", ms=1.8, color="#2563eb", alpha=0.75)
        ax.plot(v[o], total[o], "-", lw=0.9, color="black")
        axr.plot(v[o], (y - total)[o], "-", lw=0.5, color="#64748b")
        axr.axhline(0, lw=0.5, color="black")
        ax.set_xticklabels([])
        # Esquina inferior izquierda: libre de líneas en todos los espectros.
        ax.text(0.02, 0.17, label, transform=ax.transAxes)
        ax.text(0.02, 0.05, rf"$\tilde\chi^2={res['stats']['red_chi2']:.2f}$",
                transform=ax.transAxes)
        if n % 2 == 0:
            ax.set_ylabel("Transmission")
        if n // 2 == 1:
            axr.set_xlabel("Velocity (mm/s)")
    fig.savefig(IMG / "fig_reference_fits.pdf", bbox_inches="tight")
    plt.close(fig)

    # ── Fig. correlación NORMOS vs Fitbauer ─────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.4))
    panels = [("bhf", r"$B_\mathrm{hf}$ (T)", 1.0), ("delta", r"$\delta_\mathrm{raw}$ (mm/s)", 1.0),
              ("gamma1", r"$\Gamma$ (mm/s)", 1.0)]
    for ax, (par, lab, _) in zip(axes, panels):
        xs, ys, xe, ye = [], [], [], []
        for key, *_ in CASES:
            res = fits[key][4]
            for comp in ("s1", "s2"):
                k = f"{comp}_{par}"
                if k in NORMOS[key] and k in res["values"]:
                    nv, ne = NORMOS[key][k]
                    xs.append(nv); xe.append(ne)
                    ys.append(abs(res["values"][k]) if par == "quad" else res["values"][k])
                    ye.append(res["errors"].get(k, 0.0))
        lo, hi = min(xs + ys), max(xs + ys)
        pad = 0.05 * (hi - lo)
        ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad], "--", lw=0.6, color="#94a3b8")
        ax.errorbar(xs, ys, xerr=xe, yerr=ye, fmt="o", ms=3, color="#2563eb", elinewidth=0.6)
        ax.set_xlabel(f"NORMOS {lab}")
        ax.set_ylabel(f"Fitbauer {lab}")
    fig.tight_layout()
    fig.savefig(IMG / "fig_normos_comparison.pdf", bbox_inches="tight")
    plt.close(fig)

    # ── Fig. magnetita ─────────────────────────────────────────────────
    v, y, total, subs, res = fits["magnetita"]
    o = np.argsort(v)
    fig = plt.figure(figsize=(3.4, 3.0))
    g = fig.add_gridspec(2, 1, height_ratios=[3.2, 1], hspace=0.05)
    ax, axr = fig.add_subplot(g[0]), fig.add_subplot(g[1])
    ax.plot(v, y, ".", ms=1.8, color="#64748b", alpha=0.8)
    for sub, color, name in zip(subs, ("#2563eb", "#dc2626"), ("A", "B")):
        base = np.full_like(sub, float(np.max(sub)))
        ax.fill_between(v[o], base[o], sub[o], color=color, alpha=0.15, lw=0)
        ax.plot(v[o], sub[o], "-", lw=0.8, color=color, label=f"Site {name}")
    ax.plot(v[o], total[o], "-", lw=0.9, color="black", label="Total")
    axr.plot(v[o], (y - total)[o], "-", lw=0.5, color="#64748b")
    axr.axhline(0, lw=0.5, color="black")
    ax.set_xticklabels([])
    ax.set_ylabel("Transmission")
    axr.set_xlabel("Velocity (mm/s)")
    ax.legend(loc="lower left", fontsize=7, frameon=False)
    fig.savefig(IMG / "fig_magnetita_fit.pdf", bbox_inches="tight")
    plt.close(fig)
    val = res["values"]
    print("magnetita (δ respecto a α-Fe): "
          f"A δ={val['s1_delta'] + DELTA_ALPHA_FE:.3f} B={val['s1_bhf']:.1f}; "
          f"B δ={val['s2_delta'] + DELTA_ALPHA_FE:.3f} B={val['s2_bhf']:.1f}")


if __name__ == "__main__":
    main()
