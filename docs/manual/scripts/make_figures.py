#!/usr/bin/env python3
"""Genera las figuras «de física/datos» del manual de usuario de Fitbauer.

Reutiliza el núcleo puro ``core/`` y ``mossbauer_distribution`` (sin GUI) para
producir figuras auténticas: espectro α-Fe cargado, ajuste de calibración,
componentes discretos simulados (singlete/doblete/sextete) y una distribución
P(BHF) con su espectro. No cubre capturas de la interfaz (esas se añaden a mano
en ``docs/manual/img`` con el mismo nombre que el hueco del LaTeX).

Uso (desde la raíz del repositorio):

    python docs/manual/scripts/make_figures.py

Salidas: ``docs/manual/img/fig_*.pdf`` y ``.png``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
IMG = ROOT / "docs" / "manual" / "img"
DATA = ROOT / "data_sample"

# ── Estilo científico sobrio y consistente ───────────────────────────────────
plt.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 120,
    "font.size": 10,
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.6,
    "lines.linewidth": 1.4,
    "legend.frameon": False,
    "figure.autolayout": True,
})
DATA_C = "#1f4e79"     # azul datos
MODEL_C = "#c1272d"    # rojo modelo
DIST_C = "#2e7d32"     # verde distribución


def _save(fig, name: str) -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(IMG / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {name}.pdf / .png")


def _load(sample: str, vmax: float = 12.007):
    """Carga y dobla un espectro; devuelve (velocity, y, session)."""
    from core.session import HeadlessSession
    sess = HeadlessSession()
    sess.load_ws5(str(DATA / sample), vmax=vmax)
    return sess._velocity(), sess.spectrum.y_data, sess


# ── Figura 1: α-Fe sin doblar y doblado (ilustra el folding) ─────────────────
def fig_load_alphafe() -> None:
    from core.session import HeadlessSession
    from core.folding import read_ws5_counts
    sample = DATA / "hierro_metalico_alphaFe.adt"
    sess = HeadlessSession()
    sess.load_ws5(str(sample), vmax=12.007)
    counts = read_ws5_counts(sample)
    center = float(sess.spectrum.center)
    v, y = sess._velocity(), sess.spectrum.y_data
    ch = np.arange(1, counts.size + 1)
    cn = counts / (float(np.percentile(counts, 90)) or 1.0)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.6))
    # Izq: espectro SIN doblar (dos ramas del barrido, sextete repetido).
    a1.plot(ch, cn, ".", color=DATA_C, ms=2.2)
    a1.axvline(center, color=MODEL_C, ls="--", lw=1.3,
               label=f"centro de folding ≈ {center:.1f}")
    a1.set_xlabel("Canal")
    a1.set_ylabel("Cuentas (norm.)")
    a1.set_title(f"Sin doblar ({counts.size} canales)")
    a1.legend(loc="lower center", fontsize=8)
    # Dcha: espectro doblado en eje de velocidad.
    a2.plot(v, y, ".", color=DATA_C, ms=3.0)
    a2.set_xlabel("Velocidad (mm/s)")
    a2.set_ylabel("Transmisión relativa")
    a2.set_title(f"Doblado ({y.size} puntos)")
    fig.suptitle("α-Fe: del espectro sin doblar al doblado", y=1.03)
    _save(fig, "fig_load_alphafe")


# ── Figura 1b: drive senoidal (ley de velocidad + espectro sin plegar) ───────
def fig_sine_drive() -> None:
    from core.folding import sine_velocity_axis
    from core.physics import total_model
    N, vmax = 512, 11.0
    ch = np.arange(1, N + 1)
    v = sine_velocity_axis(N, vmax, 0.0)          # v_i = vmax·sin(2π(i−c0)/N)
    p_sext = np.array([0.0, 0.0, 33.0, 0.30, 1.0, 1.0, 0.30, 3.0, 2.0, 1.0])
    T = total_model(v, 1.0, 0.0, [("Sextete", p_sext)])

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.6))
    # Izq: la velocidad NO es lineal con el canal, es senoidal.
    a1.plot(ch, v, "-", color=DIST_C, lw=1.6)
    a1.axhline(0.0, color="0.6", lw=0.7)
    a1.set_xlabel("Canal")
    a1.set_ylabel("Velocidad (mm/s)")
    a1.set_title("Ley de velocidad: $v_i = v_{max}\\,\\sin(2\\pi(i-c_0)/N)$",
                 fontsize=9)
    # Dcha: espectro SIN plegar (cada canal en su velocidad real, no monótono).
    a2.plot(v, T, ".", color=DATA_C, ms=2.5)
    a2.set_xlabel("Velocidad (mm/s)")
    a2.set_ylabel("Transmisión relativa")
    a2.set_title("Espectro sin plegar (se ajusta así)", fontsize=9)
    fig.suptitle("Drive senoidal: no se dobla; cada canal en su velocidad real",
                 y=1.03)
    _save(fig, "fig_sine_drive")


# ── Figura 2: calibración α-Fe = ajuste de la VELOCIDAD (BHF fijo = 33,0 T) ───
def fig_calibration_fit() -> None:
    from core.session import HeadlessSession, ModelState
    from core.fit_engine import model_from_values
    sess = HeadlessSession(ModelState.defaults())
    sess.load_ws5(str(DATA / "hierro_metalico_alphaFe.adt"), vmax=12.007)
    # Calibrar = fijar el patrón (BHF = 33,0 T de α-Fe) y AJUSTAR la velocidad.
    sess.model.vars.update({"s1_bhf": 33.0, "s1_delta": 0.0, "s1_quad": 0.0,
                            "s1_gamma1": 0.30})
    sess.model.fixed["s1_bhf"] = True
    sess.model.fit_velocity = True
    result = sess.run_fit()
    vmax_fit = float(sess.model.vars.get("vmax", 12.007))
    state = sess.build_fit_state()
    fit_curve = model_from_values(state.velocity, sess.model.vars, state.components,
                                  state.constraints,
                                  absorber_model=sess.model.absorber_model,
                                  bounds=state.bounds)
    v = state.velocity
    y = sess.spectrum.y_data
    resid = y - fit_curve

    fig, (ax, axr) = plt.subplots(
        2, 1, figsize=(6.4, 4.4), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.05})
    ax.plot(v, y, ".", color=DATA_C, ms=3.2, label="Datos")
    ax.plot(v, fit_curve, "-", color=MODEL_C, label="Ajuste (sexteto)")
    ax.set_ylabel("Transmisión relativa")
    rchi = result["stats"].get("red_chi2", float("nan"))
    ax.set_title(f"Calibración α-Fe · BHF = 33,0 T (fijo) · "
                 f"Vmax ajustada = {vmax_fit:.3f} mm/s · χ²ᵣ = {rchi:.3g}",
                 fontsize=9)
    ax.legend(loc="lower right")
    axr.axhline(0.0, color="0.5", lw=0.8)
    axr.plot(v, resid, "-", color="0.35", lw=0.9)
    axr.set_xlabel("Velocidad (mm/s)")
    axr.set_ylabel("Resid.")
    _save(fig, "fig_calibration_fit")


# ── Figura 3: componentes discretos simulados ────────────────────────────────
def fig_sim_components() -> None:
    from core.physics import total_model
    v = np.linspace(-6, 6, 600)
    # Singlete: p = [delta, quad, bhf, g1, g2, g3, depth, int1, int2, int3]
    p_sing = np.array([0.0, 0.0, 0.0, 0.28, 1.0, 1.0, 0.30, 1.0, 0.0, 0.0])
    p_doub = np.array([0.35, 0.80, 0.0, 0.28, 1.0, 1.0, 0.30, 1.0, 1.0, 0.0])
    v6 = np.linspace(-11, 11, 800)
    p_sext = np.array([0.0, 0.0, 33.0, 0.30, 1.0, 1.0, 0.30, 3.0, 2.0, 1.0])

    fig, axs = plt.subplots(1, 3, figsize=(9.6, 3.2))
    for ax, (vx, kind, p, title) in zip(axs, [
            (v, "Singlete", p_sing, "Singlete"),
            (v, "Doblete", p_doub, "Doblete (ΔEQ = 0.80)"),
            (v6, "Sextete", p_sext, "Sexteto (BHF = 33 T)")]):
        m = total_model(vx, 1.0, 0.0, [(kind, p)])
        ax.plot(vx, m, "-", color=MODEL_C)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("v (mm/s)")
    axs[0].set_ylabel("Transmisión")
    fig.suptitle("Simulación de componentes discretos", y=1.02)
    _save(fig, "fig_sim_components")


# ── Figura 4: distribución P(BHF) y su espectro ──────────────────────────────
def fig_pbhf_distribution() -> None:
    from mossbauer_distribution import (bhf_grid, build_bhf_kernel,
                                        normalize_probability)
    v = np.linspace(-11, 11, 400)
    centers = bhf_grid(bmin=0.0, bmax=55.0, nbins=120)
    K = build_bhf_kernel(v, centers, delta=0.25, quad=0.0, gamma=0.28)

    # Cristalino (sitio nítido, ~un solo campo) vs distribución ancha.
    P_sharp = np.exp(-0.5 * ((centers - 49.0) / 0.6) ** 2)
    P_broad = (np.exp(-0.5 * ((centers - 46.0) / 3.5) ** 2)
               + 0.6 * np.exp(-0.5 * ((centers - 30.0) / 5.0) ** 2))
    Pn_sharp = normalize_probability(P_sharp, centers)
    Pn_broad = normalize_probability(P_broad, centers)

    def _spectrum(P: np.ndarray, depth: float = 0.18) -> np.ndarray:
        """Espectro de transmisión con profundidad de absorción realista."""
        absP = K @ P
        peak = float(np.max(absP)) or 1.0
        return 1.0 - depth * absP / peak

    sp_sharp = _spectrum(P_sharp)
    sp_broad = _spectrum(P_broad)

    fig, (axP, axS) = plt.subplots(1, 2, figsize=(9.6, 3.4))
    axP.plot(centers, Pn_sharp, "-", color=DIST_C, label="Cristalino (nítido)")
    axP.plot(centers, Pn_broad, "--", color=DATA_C, label="Distribución ancha")
    axP.set_xlabel("BHF (T)")
    axP.set_ylabel("P(BHF)")
    axP.set_title("Distribución de campo hiperfino")
    axP.legend(loc="upper left")

    axS.plot(v, sp_sharp, "-", color=DIST_C, label="Espectro cristalino")
    axS.plot(v, sp_broad, "--", color=DATA_C, label="Espectro distribuido")
    axS.set_xlabel("Velocidad (mm/s)")
    axS.set_ylabel("Transmisión")
    axS.set_title("Espectros simulados")
    axS.legend(loc="lower right")
    _save(fig, "fig_pbhf_distribution")


FIGURES = [
    ("espectro α-Fe sin doblar/doblado", fig_load_alphafe),
    ("drive senoidal", fig_sine_drive),
    ("ajuste de calibración", fig_calibration_fit),
    ("componentes simulados", fig_sim_components),
    ("distribución P(BHF)", fig_pbhf_distribution),
]


def main() -> int:
    print(f"Generando figuras en {IMG.relative_to(ROOT)} …")
    failures = 0
    for label, fn in FIGURES:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ✗ {label}: {type(exc).__name__}: {exc}")
    if failures:
        print(f"Terminado con {failures} figura(s) fallida(s).")
        return 1
    print("Todas las figuras generadas correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
