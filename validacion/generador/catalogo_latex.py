#!/usr/bin/env python3
"""Catálogo LaTeX del banco de validación: cada espectro con su ajuste.

Genera ``validacion/informe/catalogo/`` con:
- ``figs/<serie>_<caso>.png`` — datos doblados + modelo ajustado por Fitbauer
  (reconstruido con ``core.fit_engine.model_from_values`` a partir del JSON
  del ajuste, rellenando los parámetros que iban fijos desde la definición
  del caso), o el espectro del CLI de distribución para J/L.
- ``catalogo_espectros.tex`` (+ cuerpo) — una entrada por caso: figura +
  tabla con nombre, ruta, tipo de ajuste, tratamiento y parámetros
  verdadero→ajustado. Se compila con pdflatex.

El ajuste mostrado es el MEJOR disponible por caso (v0m > v0 > v0h > v1 >
primer fitbauer_*.json que exista), con la versión indicada en la tabla.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

GEN = Path(__file__).resolve().parent
VALID = GEN.parent
OUT = VALID / "informe" / "catalogo"
FIGS = OUT / "figs"
sys.path.insert(0, str(GEN))
sys.path.insert(0, str(VALID.parent))

from core.fit_engine import Component, model_from_values
from runner import Case, expected_params
from normos_lib import BHF_SCALE_SITE

plt.rcParams.update({"figure.dpi": 100, "font.size": 8,
                     "axes.grid": True, "grid.alpha": 0.3})

FIT_KIND = {1: "Singlete", 2: "Doblete", 6: "Sextete", 8: "Sextete"}
KIND_LABEL = {"Singlete": "singlete", "Doblete": "doblete",
              "Sextete": "sexteto", "BlumeTjon": "relajaci\\'on Blume-Tjon"}
TREAT_LABEL = {"1st_order": "1er orden", "kundig_fixed": "K\\\"undig fijo",
               "kundig_powder": "K\\\"undig polvo",
               "hamiltonian": "Hamiltoniano (polvo)",
               "hamiltonian_sc": "Hamiltoniano cristal \\'unico"}
PARAM_LABEL = {"delta": "$\\delta$", "quad": "$\\Delta E_Q$", "bhf": "$B$",
               "gamma1": "$\\Gamma_1$", "gamma2": "$\\Gamma_2/\\Gamma_1$",
               "gamma3": "$\\Gamma_3/\\Gamma_1$", "depth": "prof.",
               "int1": "$I_1$", "int2": "$I_2$"}


# ── Registro de casos discretos ──────────────────────────────────────────────

def build_registry() -> dict[tuple[str, str], dict]:
    """(serie, cid) → {case, quad_treatment, absorber, extra, tipo}."""
    from series_AB import SERIES as SAB
    from series_CG import SERIES as SCG
    from series_HI import I_CASES, H2, X1
    from series_KL import K1_PAIRS, K2, K3, K5, K4_SPECS
    import series_ext
    import valida_mejoras

    reg: dict[tuple[str, str], dict] = {}

    def add(serie, case, **kw):
        d = {"case": case, "quad_treatment": None, "absorber": "thin",
             "extra": {}, "kind_override": case.fit_kwargs.get("kind_override")}
        d["quad_treatment"] = case.fit_kwargs.get("quad_treatment")
        d["absorber"] = case.fit_kwargs.get("absorber_model", "thin")
        d.update(kw)
        reg[(serie, case.cid)] = d

    for series in (SAB, SCG):
        for serie, cases in series.items():
            for c in cases:
                add(serie, c)
    for c in I_CASES:
        add("I", c)
    for c in H2:
        add("H2", c)
    for c in X1:
        add("X1", c)
    for serie, cases in series_ext.EXT.items():
        for c in cases:
            add(serie, c)
    for _, fit in K1_PAIRS:
        add("K1", fit)
    for c in K2:
        add("K2", c)
    for c in K3:
        add("K3", c)
    for c in K5:
        add("K5", c)
    for s in K4_SPECS:
        add("K4", Case(s["cid"], s["comps"],
                       fit_kwargs={"constraints": [s["constraint"]]},
                       nota=s["nota"]))
    for c in valida_mejoras.e1_binned_cases():
        add("E1", c)

    # Mutaciones v0m (mismo mapa que valida_mejoras / valida_v4_19)
    ham = {("A4", None), ("A5", None), ("B3", None)}
    for (serie, cid), d in reg.items():
        if (serie, None) in ham or (serie == "A6" and cid.endswith("_HC")) \
                or cid == "D4_sextHC+dob":
            d["v0m_treatment"] = "hamiltonian"
        if serie in ("F1", "F2") or cid.startswith("I1"):
            d["v0m_absorber"] = "transmission"
        if serie == "E3":
            d["v0m_extra"] = {"curv": True}
        if cid.endswith("bin"):
            d["v0m_extra"] = {"channel_sub": 5}
    k3_ang = {"K3_sc_b0_g0": (0.0, 90.0), "K3_sc_b547_g0": (54.7, 90.0),
              "K3_sc_b90_g0": (90.0, 90.0), "K3_sc_b90_g90": (90.0, 180.0)}
    for cid, (bex, gax) in k3_ang.items():
        reg[("K3", cid)]["v0m_treatment"] = "hamiltonian_sc"
        reg[("K3", cid)]["v0m_angles"] = (bex, gax)
    return reg


def pick_version(cdir: Path) -> str | None:
    """Mejor ajuste disponible en el directorio del caso."""
    have = {p.stem.replace("fitbauer_", "") for p in cdir.glob("fitbauer_*.json")
            if not p.stem.endswith("_moments")}
    for v in ("v0m", "v0", "v0h", "v1"):
        if v in have:
            return v
    return sorted(have)[0] if have else None


def folded_data(cdir: Path, version: str, vmax: float):
    """(v, y) de los datos que usó ese ajuste, en el MARCO DE LA SESIÓN.

    Doblado + normalización P90 idénticos a HeadlessSession (incluido el
    recorte de borde): dibujar la teoría de SITE (base=1) desplazaba el marco
    y hacía parecer malos ajustes perfectos (fondos, transmisión, E3).
    """
    from core.folding import fold_and_normalize, velocity_axis
    from core.session import _EDGE_TRIM
    tag = version.split("m")[0] if version in ("v0m", "v0h") else version
    for cand in (f"{tag}.dat", "v0.dat", "v1.dat"):
        raw_f = cdir / cand
        if raw_f.exists():
            break
    counts = np.loadtxt(raw_f)
    _folded, _sigma, y, _norm = fold_and_normalize(
        counts, counts.size / 2 + 0.5, _EDGE_TRIM)
    v = velocity_axis(counts.size, vmax, y.size, _EDGE_TRIM)
    return v, y


def rebuild_model(entry: dict, cdir: Path, version: str):
    """Reconstruye la curva ajustada con core.fit_engine.model_from_values."""
    case: Case = entry["case"]
    fit = json.loads((cdir / f"fitbauer_{version}.json").read_text())
    vals = dict(fit.get("values", {}))
    info = json.loads((cdir / "verdad.json").read_text())
    vmax = float(info.get("vmax", case.vmax))
    n = np.load(cdir / "teoria_norm.npy").size
    v = np.linspace(-vmax, vmax, n)

    qt = entry.get("quad_treatment")
    absorber = entry.get("absorber", "thin")
    channel_sub = 1
    if version == "v0m":
        qt = entry.get("v0m_treatment", qt)
        absorber = entry.get("v0m_absorber", absorber)
        channel_sub = entry.get("v0m_extra", {}).get("channel_sub", 1)
    qt = qt or "1st_order"
    if absorber == "transmission":
        vals.setdefault("src_fwhm", 0.097)

    comps: list[Component] = []
    ko = entry.get("kind_override") or {}
    for i, c in enumerate(case.comps, 1):
        kind = ko.get(i) or FIT_KIND.get(c.get("nline", 6), "Sextete")
        comps.append(Component(idx=i, enabled=True, kind=kind,
                               quad_treatment=qt if kind == "Sextete" else "1st_order"))
        # parámetros que iban FIJOS y no están en el JSON: rellenar de la verdad
        dflt = {"delta": c.get("iso", 0.0), "quad": c.get("qua", 0.0),
                "bhf": c.get("bhf", 33.0), "gamma1": c.get("wid", 0.25),
                "gamma2": 1.0, "gamma3": 1.0, "depth": c.get("dep", 0.02),
                "int1": c.get("d13", 3.0), "int2": c.get("d23", 2.0),
                "int3": 1.0, "beta": c.get("the", 0.0),
                "eta": c.get("eta", 0.0), "phi": c.get("phi", 0.0),
                "bex": 0.0, "gax": 0.0,
                "relax_log_nu": 8.5, "relax_fraction": 1.0}
        if version == "v0m" and "v0m_angles" in entry:
            dflt["bex"], dflt["gax"] = entry["v0m_angles"]
        for k, dv in dflt.items():
            vals.setdefault(f"s{i}_{k}", dv)
    vals.setdefault("baseline", 1.0)
    vals.setdefault("slope", 0.0)
    model = model_from_values(v, vals, comps, absorber_model=absorber,
                              channel_sub=channel_sub)
    return v, model, fit


# ── Utilidades LaTeX ─────────────────────────────────────────────────────────

_UNI = {"Δ": "$\\Delta$", "Γ": "$\\Gamma$", "σ": "$\\sigma$",
        "δ": "$\\delta$", "η": "$\\eta$", "θ": "$\\theta$",
        "φ": "$\\varphi$", "γ": "$\\gamma$", "±": "$\\pm$",
        "→": "$\\rightarrow$", "≪": "$\\ll$", "×": "$\\times$",
        "⟨": "$\\langle$", "⟩": "$\\rangle$", "²": "$^2$", "³": "$^3$"}


def esc(s: str) -> str:
    s = (s.replace("\\", "\\textbackslash{}").replace("_", "\\_")
         .replace("%", "\\%").replace("&", "\\&").replace("#", "\\#"))
    for k, v in _UNI.items():
        s = s.replace(k, v)
    return s


def fnum(x) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "--"
    return f"{x:.4g}"


def tipo_label(entry: dict, version: str) -> str:
    case: Case = entry["case"]
    kinds = [FIT_KIND.get(c.get("nline", 6), "Sextete") for c in case.comps]
    ko = entry.get("kind_override") or {}
    for i, k in ko.items():
        kinds[i - 1] = k
    from collections import Counter
    cnt = Counter(kinds)
    parts = []
    for kind in ("Sextete", "Doblete", "Singlete", "BlumeTjon"):
        if cnt.get(kind):
            n = cnt[kind]
            parts.append((f"{n}\\,$\\times$\\," if n > 1 else "") + KIND_LABEL[kind])
    tipo = " + ".join(parts)
    qt = entry.get("quad_treatment")
    absorber = entry.get("absorber", "thin")
    if version == "v0m":
        qt = entry.get("v0m_treatment", qt)
        absorber = entry.get("v0m_absorber", absorber)
    if qt and qt != "1st_order" and "Sextete" in kinds:
        tipo += f", {TREAT_LABEL.get(qt, qt)}"
    if absorber == "transmission":
        tipo += ", integral de transmisi\\'on"
    elif absorber == "thickness":
        tipo += ", absorbente grueso"
    return tipo


def truth_fit_rows(entry: dict, vals: dict, version: str) -> list[tuple[str, str, str]]:
    case: Case = entry["case"]
    truth = expected_params(case)
    rows = []
    order = ("delta", "quad", "bhf", "gamma1", "gamma2", "gamma3", "depth",
             "int1", "int2")
    ncomp = len(case.comps)
    for i in range(1, ncomp + 1):
        pre = f"s{i}_"
        for name in order:
            k = pre + name
            if k not in truth:
                continue
            lab = (f"c{i} " if ncomp > 1 else "") + PARAM_LABEL[name]
            rows.append((lab, fnum(truth[k]), fnum(vals.get(k))))
    for g, lab in (("slope", "slope"), ("curv", "curv ($v^2$)"),
                   ("curv3", "base $v^3$"), ("curv4", "base $v^4$"),
                   ("sat_scale", "$C$ (grueso)"), ("src_fwhm", "$\\Gamma$ fuente")):
        if g in case.truth_override or (g in vals and g in ("curv3", "curv4")):
            rows.append((lab, fnum(case.truth_override.get(g)), fnum(vals.get(g))))
    return rows


def rows_to_tabular(rows: list[tuple[str, str, str]]) -> str:
    """Tabla de parámetros; si es muy larga, en bloques lado a lado."""
    chunks = [rows[i:i + 16] for i in range(0, len(rows), 16)] or [[]]
    tabs = []
    for ch in chunks:
        body = "\\\\\n".join(f"{a} & {b} & {c}" for a, b, c in ch)
        tabs.append(
            "\\begin{tabular}[t]{@{}lrr@{}}\n\\toprule\n"
            "par\\'am. & verdad & ajuste\\\\\n\\midrule\n" + body +
            "\\\\\n\\bottomrule\n\\end{tabular}")
    return "\\hspace{6pt}".join(tabs)


def entry_block(serie: str, cid: str, figname: str, ruta: str, tipo: str,
                version: str, chi2: str, rows_tex: str, nota: str) -> str:
    wide = rows_tex.count("tabular}") > 4
    fig_tex = (f"\\includegraphics[width=\\linewidth]{{figs/{figname}}}")
    meta = (f"\\textbf{{{esc(cid)}}}\\\\[1pt]\n"
            f"{{\\scriptsize ruta: \\texttt{{{esc(ruta)}}}\\\\\n"
            f"tipo: {tipo}\\\\\n"
            f"ajuste mostrado: {esc(version)}"
            + (f", $\\chi^2_r$={chi2}" if chi2 else "") + "\\\\\n"
            + (f"nota: {esc(nota)}\\\\\n" if nota else "") + "}\\\\[2pt]\n")
    if wide:
        return ("\\noindent\\begin{minipage}[t]{0.42\\linewidth}\n"
                + fig_tex + "\n\\end{minipage}\\hfill\n"
                "\\begin{minipage}[t]{0.55\\linewidth}\n" + meta
                + "\\end{minipage}\\\\[2pt]\n{\\tiny " + rows_tex
                + "}\\par\\vspace{8pt}\n")
    return ("\\noindent\\begin{minipage}[t]{0.46\\linewidth}\n"
            + fig_tex + "\n\\end{minipage}\\hfill\n"
            "\\begin{minipage}[t]{0.52\\linewidth}\n" + meta
            + "{\\scriptsize " + rows_tex + "}\n\\end{minipage}"
            "\\par\\vspace{8pt}\n")


def _nota_final(entry, cid, serie, version, chi2) -> str:
    """Nota de la entrada: la documentada, la regla SITE-approx, o la del caso."""
    if cid in NOTAS_DOC:
        return NOTAS_DOC[cid]
    qt = entry.get("quad_treatment")
    if version == "v0m":
        qt = entry.get("v0m_treatment", qt)
    hc = qt in ("hamiltonian", "hamiltonian_sc", "kundig_fixed")
    if hc and serie in ("A4", "A5", "A6", "B3", "D4", "K3") \
            and chi2 is not None and chi2 > 1.5:
        return NOTA_SITE_APPROX
    return entry["case"].nota[:90]


# ── Casos discretos ──────────────────────────────────────────────────────────

def make_discrete_entries() -> tuple[list[str], int, int]:
    reg = build_registry()
    orden_series = ["A1a", "A1b", "A1c", "A2", "A3a", "A3b", "A3c", "A4",
                    "A5", "A6", "A7", "B1", "B2", "B3", "C1", "C2", "C3",
                    "C4", "D1", "D2", "D3", "D4", "D5", "D6", "E1", "E2",
                    "E3", "E4", "E5", "F1", "F2", "F3", "H2", "I", "X1",
                    "K1", "K2", "K3", "K4", "K5"]
    bloques: dict[str, list[str]] = {s: [] for s in orden_series}
    ok = fallos = 0
    for (serie, cid), entry in sorted(reg.items()):
        if serie not in bloques:
            continue
        cdir = VALID / serie / cid
        if not (cdir / "teoria_norm.npy").exists():
            continue
        version = pick_version(cdir)
        if version is None:
            continue
        try:
            v, model, fit = rebuild_model(entry, cdir, version)
            vd, yd = folded_data(cdir, version, float(v[-1]))
            figname = f"{serie}_{cid}".replace("+", "p")
            fig, ax = plt.subplots(figsize=(3.6, 2.4))
            ax.plot(vd, yd, ".", ms=2.2, color="0.45", label="datos")
            ax.plot(v, model, "-", lw=1.1, color="crimson", label="Fitbauer")
            ax.set_xlabel("v (mm/s)", fontsize=7)
            ax.tick_params(labelsize=6.5)
            ax.legend(fontsize=6, loc="lower right", frameon=False)
            fig.savefig(FIGS / f"{figname}.png", bbox_inches="tight")
            plt.close(fig)
            chi2 = fit.get("stats", {}).get("red_chi2")
            rows = truth_fit_rows(entry, fit.get("values", {}), version)
            bloques[serie].append(entry_block(
                serie, cid, figname, f"validacion/{serie}/{cid}/"
                + ("v1.dat" if version.startswith("v1") else "v0.dat"),
                tipo_label(entry, version), version,
                fnum(chi2) if chi2 is not None else "",
                rows_to_tabular(rows),
                _nota_final(entry, cid, serie, version, chi2)))
            ok += 1
        except Exception as exc:
            print(f"  !! {serie}/{cid}: {type(exc).__name__}: {exc}")
            fallos += 1
    out = []
    for serie in orden_series:
        if bloques[serie]:
            out.append(f"\\section{{Serie {esc(serie)}}}\n")
            out.extend(bloques[serie])
    return out, ok, fallos


# ── Distribuciones J/L ───────────────────────────────────────────────────────

def dist_entries() -> tuple[list[str], int]:
    out = []
    n = 0
    for serie in ("J", "L"):
        sdir = VALID / serie
        if not sdir.exists():
            continue
        primero = True
        for cdir in sorted(sdir.iterdir()):
            if not (cdir / "verdad.json").exists():
                continue
            info = json.loads((cdir / "verdad.json").read_text())
            tag = next((t for t in ("v0h", "v0m", "v0", "v1")
                        if (cdir / f"fit_{t}_spectrum.dat").exists()), None)
            if tag is None:
                continue
            spec = np.loadtxt(cdir / f"fit_{tag}_spectrum.dat")
            dist_f = cdir / f"fit_{tag}_distribution.dat"
            mom_fit = ("", "")
            if dist_f.exists():
                cols = np.loadtxt(dist_f)
                w = np.maximum(cols[:, 1], 0.0)
                if w.sum() > 0:
                    wn = w / w.sum()
                    avg = float(np.sum(wn * cols[:, 0]))
                    std = float(np.sqrt(np.sum(wn * (cols[:, 0] - avg) ** 2)))
                    mom_fit = (fnum(avg), fnum(std))
            mv = info.get("momentos_verdad") or {}
            t_avg = mv.get("avg", info.get("truth_avg"))
            t_std = mv.get("std", info.get("truth_std"))
            var = info.get("var", "bhf")
            tipo = ("distribuci\\'on $P(B_{hf})$" if var == "bhf"
                    else "distribuci\\'on $P(\\Delta E_Q)$")
            tipo += ", histograma"
            if tag == "v0h":
                tipo += " (kernel Hamiltoniano)"
            cid = cdir.name
            figname = f"{serie}_{cid}".replace("+", "p")
            fig, ax = plt.subplots(figsize=(3.6, 2.4))
            ax.plot(spec[:, 0], spec[:, 1], ".", ms=2.2, color="0.45",
                    label="datos")
            ax.plot(spec[:, 0], spec[:, 2], "-", lw=1.1, color="crimson",
                    label="Fitbauer")
            ax.set_xlabel("v (mm/s)", fontsize=7)
            ax.tick_params(labelsize=6.5)
            ax.legend(fontsize=6, loc="lower right", frameon=False)
            fig.savefig(FIGS / f"{figname}.png", bbox_inches="tight")
            plt.close(fig)
            unidad = "T" if var == "bhf" else "mm/s"
            rows = [("$\\langle x\\rangle$ (" + unidad + ")", fnum(t_avg),
                     mom_fit[0]),
                    ("$\\sigma$ (" + unidad + ")", fnum(t_std), mom_fit[1])]
            if primero:
                out.append(f"\\section{{Serie {serie} (distribuciones)}}\n")
                primero = False
            out.append(entry_block(
                serie, cid, figname, f"validacion/{serie}/{cid}/v0.dat",
                tipo, f"fit_{tag}", "", rows_to_tabular(rows),
                str(info.get("nota", ""))[:90]))
            n += 1
    return out, n


# Casos que se muestran con desajuste A PROPÓSITO (evidencia documentada en
# el INFORME) o cuyo residuo es la aproximación del propio SITE-1994.
NOTAS_DOC = {
    "C3_fuera_de_rango": "FALLO DOCUMENTADO (evidencia historica): lineas fuera del rango clasico de delta; resuelto por wide_delta (INFORME 16.2)",
    "F3_t1_fina": "SESGO DOCUMENTADO: ajuste deliberado con modelo fino sobre datos saturados (INFORME 6.3)",
    "F3_t5_fina": "SESGO DOCUMENTADO: modelo fino sobre datos saturados",
    "F3_t10_fina": "SESGO DOCUMENTADO: modelo fino sobre datos saturados",
    "I1_sat50_fina": "SESGO DOCUMENTADO: transmision t=50 con modelo fino",
    "I4_limite": "limite de deteccion: 0.2% de area con base 1e5 (ruido > senal)",
    "E5_sext55_v8": "LIMITACION DOCUMENTADA: lineas fuera del rango de velocidad",
    "E5_dob_cortado": "LIMITACION DOCUMENTADA: lineas fuera del rango",
    "E5_sitio_parcial": "una linea fuera del rango (documentado)",
}
for _cid in ("X1_ising_ome0.3", "X1_ising_ome1", "X1_ising_ome3", "X1_ising_ome10"):
    NOTAS_DOC[_cid] = ("comparacion CUALITATIVA: relajacion Ising de SITE vs "
                       "Blume-Tjon (mapeo no verificable con el demo)")
NOTA_SITE_APPROX = ("residuo = aproximacion de SITE-1994 (omite interferencia "
                    "del fundamental); Fitbauer es aqui MAS exacto que la "
                    "referencia (INFORME 13)")
for _cid in ("H2_dob_debil", "H2_sext_debil"):
    NOTAS_DOC[_cid] = ("absorcion 0.5% con base 1e5: el ruido domina la figura "
                       "(vease resumen.csv)")


MASTER = r"""\documentclass[10pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[spanish,es-noshorthands]{babel}
\usepackage[margin=1.7cm]{geometry}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{parskip}
\title{Cat\'alogo del banco de validaci\'on NORMOS $\rightarrow$ Fitbauer\\
{\large todos los espectros con su ajuste}}
\author{Fitbauer v%VERSION%}
\date{\today}
\begin{document}
\maketitle
Cada entrada muestra el espectro sint\'etico generado por NORMOS-SITE/DIST
(puntos) con el modelo ajustado por Fitbauer (l\'inea), la ruta del fichero
de datos, el tipo de ajuste y los par\'ametros verdaderos frente a los
ajustados. El ajuste mostrado es el mejor disponible por caso (v0m = con las
extensiones de modelo v4.18/v4.19). An\'alisis completo en
\texttt{INFORME.md} y veredicto en \texttt{VEREDICTO.md}.
\tableofcontents
\input{catalogo_cuerpo}
\end{document}
"""


if __name__ == "__main__":
    FIGS.mkdir(parents=True, exist_ok=True)
    print("Generando entradas discretas…")
    disc, ok, fallos = make_discrete_entries()
    print(f"  {ok} casos, {fallos} fallos")
    print("Generando distribuciones…")
    dist, ndist = dist_entries()
    print(f"  {ndist} casos de distribución")
    (OUT / "catalogo_cuerpo.tex").write_text(
        "\n".join(disc + dist), encoding="utf-8")
    from core.constants import APP_VERSION
    (OUT / "catalogo_espectros.tex").write_text(
        MASTER.replace("%VERSION%", APP_VERSION), encoding="utf-8")
    print(f"LaTeX en {OUT}")
