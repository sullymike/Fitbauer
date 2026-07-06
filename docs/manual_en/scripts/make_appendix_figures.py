#!/usr/bin/env python3
"""Genera las figuras ilustrativas de los anexos matemáticos del manual.

Son figuras conceptuales (física estándar Mössbauer) que acompañan al texto de
los anexos para hacerlo más digerible:

  apx_lineshapes    — perfiles Lorentz / Voigt / Gauss a igual FWHM (Anexo A).
  apx_zeeman        — esquema Zeeman del 57Fe y sexteto resultante (Anexo A).
  apx_regularization— efecto de α: sub / óptima / sobre-regularización (Anexo A).
  apx_relaxation    — colapso por relajación (Blume-Tjon) al crecer la tasa (Anexo D).
  apx_thickness     — absorbente delgado vs grueso: saturación y ensanchamiento (Anexo E).

Uso (desde la raíz del repositorio):

    python docs/manual/scripts/make_appendix_figures.py

Salidas: docs/manual/img/apx_*.pdf y .png
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.special import wofz

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
IMG = ROOT / "docs" / "manual_en" / "img"

from core.constants import LINE_POS_33T  # posiciones publicadas del sexteto α-Fe

plt.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 120,
    "font.size": 10,
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.6,
    "lines.linewidth": 1.6,
    "legend.frameon": False,
    "figure.autolayout": True,
})
C_LOR = "#c1272d"    # rojo
C_VOI = "#1f4e79"    # azul
C_GAU = "#2e7d32"    # verde
C_GRAY = "#6b6b6b"

# Posiciones publicadas del sexteto a 33 T (6 líneas, ambos signos) e intensidades.
SEXT_POS = np.sort(np.asarray(LINE_POS_33T, dtype=float))
SEXT_INT = np.array([3.0, 2.0, 1.0, 1.0, 2.0, 3.0])


def _save(fig, name: str) -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(IMG / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {name}.pdf / .png")


def _lorentz(v, v0, fwhm):
    h = fwhm / 2.0
    return h * h / ((v - v0) ** 2 + h * h)


def _gauss(v, v0, fwhm):
    sig = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    return np.exp(-((v - v0) ** 2) / (2.0 * sig * sig))


def _voigt(v, v0, fwhm_l, sigma):
    """Voigt normalizado a altura 1 (HWHM lorentziana = fwhm_l/2)."""
    z = ((v - v0) + 1j * fwhm_l / 2.0) / (sigma * np.sqrt(2.0))
    z0 = (1j * fwhm_l / 2.0) / (sigma * np.sqrt(2.0))
    return np.real(wofz(z)) / np.real(wofz(z0))


# ── A.1 Perfiles de línea ────────────────────────────────────────────────────
def fig_lineshapes():
    v = np.linspace(-6, 6, 1201)
    fwhm = 1.0
    fig, (ax, axlog) = plt.subplots(1, 2, figsize=(9.2, 3.6))
    for a in (ax, axlog):
        a.plot(v, _lorentz(v, 0, fwhm), color=C_LOR, label="Lorentzian")
        a.plot(v, _voigt(v, 0, 0.7 * fwhm, 0.30), color=C_VOI, label="Voigt")
        a.plot(v, _gauss(v, 0, fwhm), color=C_GAU, ls="--", label="Gaussian")
        a.axhline(0.5, color=C_GRAY, lw=0.7, ls=":")
        a.set_xlabel("$v-v_0$ (units of FWHM)")
    ax.set_ylabel("profile (height 1)")
    ax.set_title("Profiles at equal FWHM")
    ax.annotate("half maximum", (3.4, 0.52), color=C_GRAY, fontsize=8)
    axlog.set_yscale("log")
    axlog.set_ylim(1e-3, 1.3)
    axlog.set_title("Tails (log scale)")
    ax.legend(loc="upper right", fontsize=8)
    _save(fig, "apx_lineshapes")


# ── A.2 Esquema Zeeman → sexteto ─────────────────────────────────────────────
def fig_zeeman():
    fig, (axl, axs) = plt.subplots(
        2, 1, figsize=(8.4, 6.4), gridspec_kw={"height_ratios": [1.15, 1.0]})

    # Niveles: fundamental I=1/2 (m=-1/2,+1/2), excitado I=3/2 (m=-3/2..+3/2).
    xg = (0.0, 1.0)
    yg = {+0.5: 1.0, -0.5: 0.6}          # fundamental (abajo)
    ye = {-1.5: 5.2, -0.5: 5.7, +0.5: 6.2, +1.5: 6.7}  # excitado (arriba)
    for m, y in yg.items():
        axl.hlines(y, *xg, color="k", lw=2)
        axl.text(xg[1] + 0.03, y, rf"$m_g={int(m*2):+d}/2$",
                 va="center", fontsize=9)
    for m, y in ye.items():
        axl.hlines(y, *xg, color="k", lw=2)
        axl.text(xg[1] + 0.03, y, rf"$m_e={int(m*2):+d}/2$",
                 va="center", fontsize=9)
    axl.text(-0.05, 0.8, r"$I_g=1/2$", ha="right", va="center", fontsize=11)
    axl.text(-0.05, 5.95, r"$I_e=3/2$", ha="right", va="center", fontsize=11)

    # 6 transiciones permitidas (Δm=0,±1), coloreadas como en el espectro.
    colors = plt.cm.viridis(np.linspace(0.05, 0.9, 6))
    trans = [(-0.5, -1.5), (-0.5, -0.5), (-0.5, +0.5),   # líneas 1,2,3 (m_g=-1/2)
             (+0.5, -0.5), (+0.5, +0.5), (+0.5, +1.5)]   # líneas 4,5,6 (m_g=+1/2)
    xarr = np.linspace(0.12, 0.88, 6)
    for k, ((mg, me), xa) in enumerate(zip(trans, xarr)):
        axl.annotate("", xy=(xa, ye[me]), xytext=(xa, yg[mg]),
                     arrowprops=dict(arrowstyle="-|>", color=colors[k], lw=1.7))
    axl.set_title("Zeeman splitting of $^{57}$Fe and allowed "
                  r"transitions ($\Delta m=0,\pm1$)")
    axl.set_xlim(-0.35, 1.35)
    axl.set_ylim(0.2, 7.2)
    axl.axis("off")

    # Espectro resultante: 6 líneas a las posiciones publicadas.
    v = np.linspace(-8, 8, 1600)
    dips = np.zeros_like(v)
    for pos, inten in zip(SEXT_POS, SEXT_INT):
        dips += (inten / SEXT_INT.max()) * _lorentz(v, pos, 0.32)
    axs.plot(v, 1 - 0.85 * dips, color="k", lw=1.5, zorder=3)
    for k, (pos, inten) in enumerate(zip(SEXT_POS, SEXT_INT)):
        ymin = 1 - 0.85 * inten / SEXT_INT.max()
        axs.vlines(pos, ymin, 1.10, color=colors[k], lw=1.0, ls=":", zorder=2)
        axs.text(pos, 1.15, f"{k+1}", ha="center", va="center",
                 color=colors[k], fontsize=10, fontweight="bold")
    axs.set_xlabel("velocity (mm/s)")
    axs.set_ylabel("transmission")
    axs.set_title("Resulting sextet: 6 lines, intensities 3:2:1:1:2:3")
    axs.set_xlim(-8, 8)
    axs.set_ylim(0.05, 1.25)
    _save(fig, "apx_zeeman")


# ── A.3 Efecto de la regularización ──────────────────────────────────────────
def fig_regularization():
    B = np.linspace(20, 55, 400)
    true = (np.exp(-((B - 46) ** 2) / (2 * 1.6 ** 2))
            + 0.7 * np.exp(-((B - 50) ** 2) / (2 * 1.2 ** 2)))
    rng = np.random.default_rng(3)
    # sub-regularizada: oscilaciones espurias de alta frecuencia
    under = np.clip(true + 0.35 * np.sin(B * 3.3) * np.exp(-((B - 48) ** 2) / 120)
                    + 0.12 * rng.standard_normal(B.size), 0, None)
    # sobre-regularizada: demasiado suave (convolución ancha)
    from numpy import convolve
    k = np.exp(-np.linspace(-3, 3, 81) ** 2 / (2 * 1.0 ** 2)); k /= k.sum()
    over = convolve(true, k, mode="same")
    over *= true.max() / over.max()

    fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.3), sharey=True)
    titles = [r"small $\alpha$: under-regularized",
              r"optimal $\alpha$ (L corner)",
              r"large $\alpha$: over-regularized"]
    data = [under, true, over]
    cols = [C_LOR, C_GAU, C_VOI]
    for a, d, t, c in zip(axes, data, titles, cols):
        a.fill_between(B, 0, true, color="k", alpha=0.08, label="true")
        a.plot(B, d, color=c, lw=1.8)
        a.set_title(t, fontsize=9.5)
        a.set_xlabel("$B_{\\mathrm{hf}}$ (T)")
    axes[0].set_ylabel("$P(B_{\\mathrm{hf}})$")
    axes[0].annotate("spurious\noscillations", (30, 0.55), color=C_LOR, fontsize=8)
    axes[2].annotate("washed-out\nstructure", (30, 0.55), color=C_VOI, fontsize=8)
    _save(fig, "apx_regularization")


# ── D.1 Colapso por relajación (Blume-Tjon) ──────────────────────────────────
def _bt_spectrum(v, k, gamma=0.18):
    """Espectro de intercambio +BHF <-> -BHF a tasa k (unidades de velocidad)."""
    a = np.zeros_like(v)
    for pos, inten in zip(SEXT_POS, SEXT_INT):
        va, vb = pos, -pos           # la línea salta a su posición espejo
        za = gamma + 1j * (v - va)
        zb = gamma + 1j * (v - vb)
        R = 0.5 * gamma * (za + zb + 4 * k) / (za * zb + k * (za + zb))
        a += inten * np.clip(np.real(R), 0, None)
    return a


def fig_relaxation():
    v = np.linspace(-8, 8, 1600)
    rates = [(0.02, "slow: static sextet"),
             (0.6, "intermediate"),
             (2.5, "intermediate-fast"),
             (30.0, "fast: collapsed singlet")]
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    off = 0.0
    cmap = plt.cm.plasma(np.linspace(0.1, 0.8, len(rates)))
    for (k, lab), c in zip(rates, cmap):
        a = _bt_spectrum(v, k)
        a = a / a.max()
        ax.plot(v, 1 - 0.8 * a + off, color=c, lw=1.5)
        ax.text(7.7, 1 + off, lab, ha="right", va="bottom", color=c, fontsize=9)
        off += 1.15
    ax.set_xlabel("velocity (mm/s)")
    ax.set_ylabel("transmission (shifted)")
    ax.set_title(r"Relaxational collapse as the exchange rate $\nu$ increases")
    ax.set_yticks([])
    ax.set_xlim(-8, 8)
    _save(fig, "apx_relaxation")


# ── E.1 Absorbente delgado vs grueso ─────────────────────────────────────────
def fig_thickness():
    fig, (axm, axs) = plt.subplots(1, 2, figsize=(9.4, 3.7))

    # (a) mapeo A_eff = C(1-e^{-A/C})
    A = np.linspace(0, 3, 400)
    axm.plot(A, A, color=C_GRAY, ls="--", label=r"thin ($C\to\infty$)")
    for C, c in [(1.0, C_VOI), (0.4, C_LOR)]:
        axm.plot(A, C * (1 - np.exp(-A / C)), color=c, label=f"$C={C:g}$")
        axm.axhline(C, color=c, lw=0.7, ls=":")
    axm.set_xlabel("$A_{\\mathrm{tot}}$ (unsaturated absorption)")
    axm.set_ylabel("$A_{\\mathrm{eff}}$ (effective)")
    axm.set_title("Absorption saturation")
    axm.legend(loc="lower right", fontsize=8)

    # (b) una línea profunda: delgado vs grueso (más plana y más ancha)
    v = np.linspace(-4, 4, 800)
    A0 = 1.6
    Atot = A0 * _lorentz(v, 0, 1.0)
    axs.axhline(0.0, color="k", lw=0.7, ls=":")
    axs.plot(v, 1 - Atot, color=C_GRAY, ls="--", label="thin $1-A$")
    for C, c in [(1.0, C_VOI), (0.4, C_LOR)]:
        axs.plot(v, 1 - C * (1 - np.exp(-Atot / C)), color=c, label=f"thick $C={C:g}$")
    axs.set_xlabel("velocity (mm/s)")
    axs.set_ylabel("transmission")
    axs.set_title("Single line: saturation and broadening")
    axs.set_ylim(-0.7, 1.06)
    axs.legend(loc="lower right", fontsize=8)
    axs.annotate("$1-A<0$:\nthe linear model\nbreaks down", (-3.8, -0.42),
                 color=C_GRAY, fontsize=8, ha="left", va="center")
    axs.annotate("flatter\nand broader", (1.25, 0.55), color=C_LOR, fontsize=8)
    _save(fig, "apx_thickness")


# ── A.4 Textura: intensidad de las líneas 2 y 5 ──────────────────────────────
def fig_texture():
    fig, (axr, axs) = plt.subplots(1, 2, figsize=(9.6, 3.8))
    t = np.linspace(0, 1, 300)
    axr.plot(t, 4 * t / (2 - t), color=C_VOI, lw=1.9)
    marks = [(0.0, "3:0:1\naxis ∥ beam", (8, 4), "left"),
             (2 / 3, "3:2:1\nrandom powder", (-6, 10), "center"),
             (1.0, "3:4:1\nfoil ⊥ beam", (-8, 2), "right")]
    for tv, lab, off, ha in marks:
        y = 4 * tv / (2 - tv)
        axr.plot(tv, y, "o", color=C_LOR, ms=6)
        axr.annotate(lab, (tv, y), textcoords="offset points", xytext=off,
                     fontsize=8, ha=ha)
    axr.set_xlabel(r"texture parameter $t=\sin^2\theta$")
    axr.set_ylabel(r"$i_2$ (intensity of lines 2 and 5)")
    axr.set_title("Texture of a sextet")
    axr.set_xlim(-0.02, 1.02)

    v = np.linspace(-8, 8, 1600)
    off = 0.0
    for tv, c, lab in [(0.0, C_GAU, "$t=0$  (3:0:1)"),
                       (2 / 3, "k", "$t=2/3$  (3:2:1)"),
                       (1.0, C_LOR, "$t=1$  (3:4:1)")]:
        i2 = 4 * tv / (2 - tv)
        W = np.array([3.0, i2, 1.0, 1.0, i2, 3.0])
        a = np.zeros_like(v)
        for pos, w in zip(SEXT_POS, W):
            a += w * _lorentz(v, pos, 0.32)
        axs.plot(v, 1 - 0.22 * a + off, color=c, lw=1.3)
        axs.text(7.7, 1 + off, lab, ha="right", va="bottom", color=c, fontsize=8.5)
        off += 0.75
    axs.set_xlabel("velocity (mm/s)")
    axs.set_ylabel("transmission (shifted)")
    axs.set_title("Lines 2 and 5 grow with $t$")
    axs.set_yticks([])
    axs.set_xlim(-8, 8)
    _save(fig, "apx_texture")


# ── A.5 Pérdidas robustas ────────────────────────────────────────────────────
def fig_losses():
    r = np.linspace(-6, 6, 800)
    z = r ** 2
    d = 1.35
    L = {"linear ($\\chi^2$)": (C_GRAY, "--", 0.5 * z),
         r"soft-$\ell_1$": (C_VOI, "-", np.sqrt(1 + z) - 1),
         "Huber": (C_LOR, "-", np.where(np.abs(r) <= d, 0.5 * z, d * (np.abs(r) - 0.5 * d)))}
    W = {"linear ($\\chi^2$)": (C_GRAY, "--", np.ones_like(r)),
         r"soft-$\ell_1$": (C_VOI, "-", 1 / np.sqrt(1 + z)),
         "Huber": (C_LOR, "-", np.minimum(1.0, d / np.maximum(np.abs(r), 1e-9)))}
    fig, (axl, axw) = plt.subplots(1, 2, figsize=(9.4, 3.6))
    for lab, (c, ls, y) in L.items():
        axl.plot(r, y, color=c, ls=ls, label=lab)
    axl.set_xlabel("normalized residual $r$")
    axl.set_ylabel(r"loss $\frac{1}{2}\rho(r^2)$")
    axl.set_title("Loss function")
    axl.set_ylim(0, 8)
    axl.legend(fontsize=8)
    for lab, (c, ls, y) in W.items():
        axw.plot(r, y, color=c, ls=ls, label=lab)
    axw.set_xlabel("normalized residual $r$")
    axw.set_ylabel("effective weight (IRLS)")
    axw.set_title("Weight of each point")
    axw.set_ylim(0, 1.08)
    axw.annotate("outliers\nweigh less", (3.2, 0.30), color=C_LOR, fontsize=8)
    _save(fig, "apx_losses")


# ── B.1 Distribución de desplazamiento isomérico P(IS) ───────────────────────
def fig_is():
    fig, (axp, axs) = plt.subplots(1, 2, figsize=(9.4, 3.6))
    d = np.linspace(-0.4, 1.7, 500)
    peaks = [(0.35, 0.09, 1.0, "Fe$^{3+}$"), (1.05, 0.13, 0.8, "Fe$^{2+}$")]
    P = np.zeros_like(d)
    for mu, sig, amp, _ in peaks:
        P += amp * np.exp(-((d - mu) ** 2) / (2 * sig ** 2))
    axp.fill_between(d, 0, P, color=C_GAU, alpha=0.25)
    axp.plot(d, P, color=C_GAU, lw=1.8)
    for mu, sig, amp, lab in peaks:
        axp.annotate(lab, (mu, amp + 0.05), ha="center", color=C_GAU, fontsize=9)
    axp.set_xlabel(r"$\delta$ (mm/s)")
    axp.set_ylabel(r"$P(\delta)$")
    axp.set_title("Distribution of $\\delta$ (oxidation states)")
    axp.set_ylim(0, 1.25)

    v = np.linspace(-1.2, 2.4, 900)
    absb = np.zeros_like(v)
    for mu, sig, amp, _ in peaks:
        for dd in np.linspace(mu - 3 * sig, mu + 3 * sig, 25):
            w = amp * np.exp(-((dd - mu) ** 2) / (2 * sig ** 2))
            absb += w * _lorentz(v, dd, 0.28)
    absb /= absb.max()
    axs.plot(v, 1 - 0.6 * absb, color="k", lw=1.5)
    axs.set_xlabel("velocity (mm/s)")
    axs.set_ylabel("transmission")
    axs.set_title("Spectrum: two overlapping environments")
    axs.set_xlim(-1.2, 2.4)
    _save(fig, "apx_is")


# ── C.1 Distribución 2D con marginales ───────────────────────────────────────
def fig_2d_contour():
    B = np.linspace(15, 55, 160)
    Q = np.linspace(-0.4, 1.4, 140)
    BB, QQ = np.meshgrid(B, Q)
    xb, xq = (BB - 46) / 6.0, (QQ - 0.15) / 0.22
    P = np.exp(-(xb ** 2 + xq ** 2 - 1.2 * xb * xq) / 1.4)      # nube inclinada (correlación)
    P += 0.55 * np.exp(-(((BB - 31) / 5) ** 2 + ((QQ - 0.7) / 0.28) ** 2))  # 2º sitio

    fig = plt.figure(figsize=(6.8, 5.4))
    gs = fig.add_gridspec(2, 2, width_ratios=[4, 1], height_ratios=[1, 4],
                          hspace=0.06, wspace=0.06)
    axm = fig.add_subplot(gs[1, 0])
    axt = fig.add_subplot(gs[0, 0], sharex=axm)
    axr = fig.add_subplot(gs[1, 1], sharey=axm)
    axm.contourf(BB, QQ, P, levels=12, cmap="viridis")
    axm.contour(BB, QQ, P, levels=6, colors="white", linewidths=0.4, alpha=0.5)
    axm.set_xlabel(r"$B_{\mathrm{hf}}$ (T)")
    axm.set_ylabel(r"$\Delta E_Q$ (mm/s)")
    axm.grid(False)
    axt.plot(B, P.sum(0), color=C_VOI)
    axt.fill_between(B, 0, P.sum(0), color=C_VOI, alpha=0.2)
    axt.set_ylabel(r"$P_B$", fontsize=9)
    axt.tick_params(labelbottom=False); axt.set_yticks([]); axt.grid(False)
    axt.set_title("Joint distribution $P(B_{\\mathrm{hf}},\\Delta E_Q)$ and marginals")
    axr.plot(P.sum(1), Q, color=C_LOR)
    axr.fill_betweenx(Q, 0, P.sum(1), color=C_LOR, alpha=0.2)
    axr.set_xlabel(r"$P_Q$", fontsize=9)
    axr.tick_params(labelleft=False); axr.set_xticks([]); axr.grid(False)
    _save(fig, "apx_2d_contour")


# ── D.2 Néel–Arrhenius: bloqueo y tamaño ─────────────────────────────────────
def fig_neel():
    kB = 1.380649e-23
    tau0 = 1e-10
    Keff = 2.0e4                      # J/m^3 (orden de magnitud típico)
    fig, (axl, axr) = plt.subplots(1, 2, figsize=(9.6, 3.8))

    d_nm = np.linspace(2, 20, 400)
    V = np.pi * (d_nm * 1e-9) ** 3 / 6.0
    for T, c in [(80, C_VOI), (300, C_LOR)]:
        lognu = -np.log10(tau0) - Keff * V / (kB * T * np.log(10))
        axl.plot(d_nm, lognu, color=c, lw=1.9, label=f"T = {T} K")
    axl.axhspan(7, 8, color=C_GRAY, alpha=0.18)
    axl.text(2.4, 7.5, "Mössbauer\nwindow", fontsize=8, color=C_GRAY, va="center")
    axl.set_xlabel("diameter $d$ (nm)")
    axl.set_ylabel(r"$\log_{10}\nu$  (s$^{-1}$)")
    axl.set_title("Néel relaxation rate")
    axl.set_ylim(0, 11)
    axl.legend(fontsize=8, loc="lower left")
    axl.annotate(r"SPM (fast): high $\nu$", (6.2, 9.5), fontsize=8, color="#444")
    axl.annotate(r"blocked (slow): low $\nu$", (10.2, 1.0), fontsize=8, color="#444")

    dd = np.linspace(1, 20, 400)
    d50, sig = 8.0, 0.32
    f = np.exp(-(np.log(dd / d50) ** 2) / (2 * sig ** 2)) / (dd * sig * np.sqrt(2 * np.pi))
    axr.plot(dd, f, color="k", lw=1.6)
    d_b = 12.5   # diámetro de bloqueo aproximado a 300 K (donde ν cruza la ventana)
    axr.fill_between(dd, 0, f, where=dd < d_b, color=C_LOR, alpha=0.25, label="SPM (collapsed)")
    axr.fill_between(dd, 0, f, where=dd >= d_b, color=C_VOI, alpha=0.25, label="blocked (sextet)")
    axr.axvline(d_b, color=C_GRAY, ls="--", lw=1.0)
    axr.text(d_b + 0.2, f.max() * 0.85, r"$d_B$", color=C_GRAY, fontsize=9)
    axr.set_xlabel("diameter $d$ (nm)")
    axr.set_ylabel("$f(d)$ (lognormal)")
    axr.set_title("Size partitioning at fixed $T$")
    axr.legend(fontsize=8, loc="upper right")
    _save(fig, "apx_neel")


# ── A.x Efecto del cuadrupolo (primer orden) ─────────────────────────────────
def fig_quadrupole():
    v = np.linspace(-8, 8, 1600)
    s = np.array([+0.5, -0.5, -0.5, -0.5, -0.5, +0.5])   # patrón cuadrupolar
    fig, ax = plt.subplots(figsize=(7.8, 4.4))
    for deq, c, lab, off in [(0.0, C_GRAY, r"$\Delta E_Q = 0$", 0.0),
                             (0.6, C_LOR, r"$\Delta E_Q = 0.6$ mm/s", 0.9)]:
        pos = SEXT_POS + s * deq
        a = np.zeros_like(v)
        for p, inten in zip(pos, SEXT_INT):
            a += inten * _lorentz(v, p, 0.30)
        a /= a.max()
        ax.plot(v, 1 - 0.82 * a + off, color=c, lw=1.4)
        ax.text(7.7, 1 + off, lab, ha="right", va="bottom", color=c, fontsize=9)
    ax.set_xlabel("velocity (mm/s)")
    ax.set_ylabel("transmission (shifted)")
    ax.set_title("Effect of the quadrupole on a sextet (first order)")
    ax.set_yticks([])
    ax.set_xlim(-8, 8)
    _save(fig, "apx_quadrupole")


# ── A.y Promedio policristalino (Kündig) ─────────────────────────────────────
def fig_powder():
    from core.hamiltonian import (kundig_sextet_positions,
                                  polycrystal_kundig_positions)
    v = np.linspace(-9, 9, 1800)
    bhf, deq, delta = 33.0, 1.4, 0.0

    def spec(pos, gamma=0.28):
        a = np.zeros_like(v)
        for p, inten in zip(pos, SEXT_INT):
            a += inten * _lorentz(v, p, gamma)
        return a

    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    singles = [(0.0, C_VOI, "single crystal  β = 0° (∥)"),
               (np.pi / 2, C_GAU, "single crystal  β = 90° (⊥)")]
    off = 0.0
    for beta, c, lab in singles:
        pos = kundig_sextet_positions(bhf, delta, deq, beta)
        a = spec(pos); a /= a.max()
        ax.plot(v, 1 - 0.8 * a + off, color=c, lw=1.2)
        ax.text(8.7, 1 + off, lab, ha="right", va="bottom", color=c, fontsize=8.5)
        off += 1.05
    P, W = polycrystal_kundig_positions(bhf, delta, deq, 20)
    a = np.zeros_like(v)
    for k in range(P.shape[0]):
        a += W[k] * spec(P[k])
    a /= a.max()
    ax.plot(v, 1 - 0.8 * a + off, color="k", lw=1.7)
    ax.text(8.7, 1 + off, "powder average", ha="right", va="bottom",
            color="k", fontsize=9)
    ax.set_xlabel("velocity (mm/s)")
    ax.set_ylabel("transmission (shifted)")
    ax.set_title(r"Polycrystalline average over the $\beta$ orientations"
                 " (with $\\Delta E_Q\\neq0$)")
    ax.set_yticks([])
    ax.set_xlim(-9, 9)
    _save(fig, "apx_powder")


# ── C.2 L-surface de regularización 2D ───────────────────────────────────────
def fig_lsurface():
    lax = np.linspace(-4, 0, 70)
    lay = np.linspace(-4, 0, 70)
    LX, LY = np.meshgrid(lax, lay)
    rms = 0.0045 * (1 + 0.9 / (1 + np.exp(-(LX + 2.2) * 3.5))) \
                 * (1 + 0.9 / (1 + np.exp(-(LY + 2.2) * 3.5)))
    fig, ax = plt.subplots(figsize=(6.6, 5.2))
    cf = ax.contourf(LX, LY, rms * 1000, levels=14, cmap="viridis")
    ax.contour(LX, LY, rms * 1000, levels=8, colors="white", linewidths=0.4, alpha=0.5)
    ax.plot(-2.2, -2.2, "*", ms=20, color="#f97316", mec="k", mew=0.8)
    ax.annotate("chosen corner", (-2.2, -2.2), textcoords="offset points",
                xytext=(12, -2), color="white", fontsize=9, va="center")
    cb = fig.colorbar(cf, ax=ax)
    cb.set_label(r"RMS ($\times10^{-3}$)")
    ax.set_xlabel(r"$\log_{10}\alpha_{B}$ (field)")
    ax.set_ylabel(r"$\log_{10}\alpha_{Q}$ (quadrupole)")
    ax.set_title("L-surface: RMS versus the two regularizations")
    ax.grid(False)
    _save(fig, "apx_lsurface")


# ── D.3 Modelo fenomenológico Relajacion: fracción bloqueada ─────────────────
def fig_relax_phenom():
    v = np.linspace(-9, 9, 1800)
    s6 = np.zeros_like(v)
    for p, inten in zip(SEXT_POS, SEXT_INT):
        s6 += inten * _lorentz(v, p, 0.30)
    d2 = _lorentz(v, 0.30 - 0.35, 0.30) + _lorentz(v, 0.30 + 0.35, 0.30)
    d2 *= s6.sum() / d2.sum()      # doblete escalado a igual área (D_2^*)
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    rows = [(1.0, C_VOI, "$f_b=1$  (blocked: sextet)"),
            (0.66, "#7b3ba1", "$f_b=0.66$"),
            (0.33, "#c0561f", "$f_b=0.33$"),
            (0.0, C_LOR, "$f_b=0$  (SPM: doublet)")]
    off = 0.0
    for fb, c, lab in rows:
        a = fb * s6 + (1 - fb) * d2
        ax.plot(v, 1 - 0.5 * a + off, color=c, lw=1.4)
        ax.text(8.7, 1 + off, lab, ha="right", va="bottom", color=c, fontsize=8.5)
        off += 0.85
    ax.set_xlabel("velocity (mm/s)")
    ax.set_ylabel("transmission (shifted)")
    ax.set_title(r"Phenomenological model: sextet$\leftrightarrow$doublet interpolation")
    ax.set_yticks([])
    ax.set_xlim(-9, 9)
    _save(fig, "apx_relax_phenom")


# ── A.z Verosimilitud perfilada frente a covarianza ──────────────────────────
def fig_profile():
    th = np.linspace(-3, 3.6, 500)
    chi_cov = th ** 2                                  # parábola (covarianza), σ=1
    chi_true = np.where(th >= 0, (th / 1.5) ** 2, (th / 1.05) ** 2)  # perfil asimétrico
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    ax.plot(th, chi_cov, color=C_GRAY, ls="--", label=r"covariance (parabola)")
    ax.plot(th, chi_true, color=C_VOI, lw=1.8, label="profile likelihood")
    ax.axhline(1.0, color=C_LOR, lw=1.0, ls=":")
    ax.text(-2.9, 1.08, r"$\Delta\chi^2=1$", color=C_LOR, fontsize=9)
    # intervalos: covarianza ±1; perfil [-1.05, +1.5]
    for x, c in [(-1.0, C_GRAY), (1.0, C_GRAY)]:
        ax.plot([x, x], [0, 1], color=c, ls="--", lw=0.8)
    for x, c in [(-1.05, C_VOI), (1.5, C_VOI)]:
        ax.plot([x, x], [0, 1], color=c, lw=1.0)
    ax.annotate("", xy=(1.5, 0.18), xytext=(-1.05, 0.18),
                arrowprops=dict(arrowstyle="<->", color=C_VOI, lw=1.2))
    ax.text(0.22, 0.28, "asymmetric CI\n(realistic)", color=C_VOI, fontsize=8, ha="center")
    ax.set_xlabel(r"parameter $\theta$ (from the optimum, in $\sigma$)")
    ax.set_ylabel(r"$\chi^2-\chi^2_{\min}$")
    ax.set_title("Error bars: profile likelihood vs covariance")
    ax.set_ylim(0, 4)
    ax.legend(fontsize=8, loc="upper center")
    _save(fig, "apx_profile")


# ── A.w Arranque múltiple (multistart) ───────────────────────────────────────
def fig_multistart():
    x = np.linspace(-4, 4, 700)
    cost = (1.0
            - 1.00 * np.exp(-((x - 1.2) ** 2) / 0.5)     # mínimo global
            - 0.55 * np.exp(-((x + 2.3) ** 2) / 0.4)      # local
            - 0.35 * np.exp(-((x - 3.1) ** 2) / 0.3))     # local
    def costf(xx):
        return (1.0 - 1.00 * np.exp(-((xx - 1.2) ** 2) / 0.5)
                - 0.55 * np.exp(-((xx + 2.3) ** 2) / 0.4)
                - 0.35 * np.exp(-((xx - 3.1) ** 2) / 0.3))
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    ax.plot(x, cost, color="k", lw=1.6)
    starts = [(-2.3, C_VOI), (1.2, C_GAU), (3.1, C_VOI)]
    labeled = False
    for xs, c in starts:
        ax.plot(xs, 1.15, "o", color=c, ms=7,
                label=("starts" if not labeled else None))
        labeled = True
        ax.annotate("", xy=(xs, costf(xs) + 0.03), xytext=(xs, 1.12),
                    arrowprops=dict(arrowstyle="->", color=c, lw=1.1, alpha=0.8))
    ax.plot(1.2, costf(1.2), "*", ms=20, color="#f97316", mec="k", mew=0.7,
            label="global minimum")
    ax.text(-2.3, costf(-2.3) - 0.12, "local\nminimum", ha="center", fontsize=8, color="#555")
    ax.set_xlabel("parameter")
    ax.set_ylabel("cost $\\mathcal{C}$")
    ax.set_title("Multistart: escaping local minima")
    ax.set_ylim(-0.15, 1.3)
    ax.legend(fontsize=8, loc="lower right")
    _save(fig, "apx_multistart")


# ── A.v VBF: suma de gaussianas (Rancourt–Ping) ──────────────────────────────
def fig_vbf():
    B = np.linspace(20, 56, 500)
    comps = [(46.0, 2.2, 1.00, "site 1"), (50.0, 1.4, 0.55, "site 2"),
             (33.0, 4.0, 0.30, "disorder tail")]
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    total = np.zeros_like(B)
    colors = [C_VOI, C_GAU, C_LOR]
    for (mu, sig, amp, lab), c in zip(comps, colors):
        g = amp * np.exp(-((B - mu) ** 2) / (2 * sig ** 2))
        total += g
        ax.plot(B, g, color=c, ls="--", lw=1.1)
        ax.fill_between(B, 0, g, color=c, alpha=0.13)
        ax.annotate(lab, (mu, amp + 0.03), ha="center", color=c, fontsize=8)
    ax.plot(B, total, color="k", lw=1.9, label=r"$P(B_{\mathrm{hf}})$ (VBF sum)")
    ax.set_xlabel(r"$B_{\mathrm{hf}}$ (T)")
    ax.set_ylabel(r"$P(B_{\mathrm{hf}})$")
    ax.set_title("VBF: the distribution as a sum of Gaussians")
    ax.set_ylim(0, 1.3)
    ax.legend(fontsize=8, loc="upper left")
    _save(fig, "apx_vbf")


def main() -> int:
    fig_lineshapes()
    fig_zeeman()
    fig_regularization()
    fig_relaxation()
    fig_thickness()
    fig_texture()
    fig_losses()
    fig_is()
    fig_2d_contour()
    fig_neel()
    fig_quadrupole()
    fig_powder()
    fig_lsurface()
    fig_relax_phenom()
    fig_profile()
    fig_multistart()
    fig_vbf()
    print("Appendix figures generated in docs/manual_en/img/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
