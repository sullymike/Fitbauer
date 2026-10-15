"""Generación y exportación de informes desde la GUI Qt."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.constants import APP_NAME, APP_VERSION
from core.params import USED_BY
from core.result_views import discrete_result_view, distribution_result_view

ROOT = Path(__file__).resolve().parents[1]


def _r(key: str, **kwargs) -> str:
    """Texto del informe en el idioma activo (claves ``rep.*``)."""
    return tr(f"rep.{key}", **kwargs)


def correlation_table_lines(pairs: list[dict], *, threshold: float = 0.5,
                            code: bool = False) -> list[str]:
    """Tabla Markdown con las parejas de |r| ≥ ``threshold``, de mayor a menor.

    ⚠ marca |r| ≥ 0.95 (no separables) y ! |r| ≥ 0.8. Sin parejas que
    lleguen al umbral devuelve una línea con la máxima.
    """
    pairs = sorted(pairs or [], key=lambda p: -abs(float(p["corr"])))
    if not pairs:
        return []
    q = (lambda s: f"`{s}`") if code else (lambda s: s)
    shown = [p for p in pairs if abs(float(p["corr"])) >= threshold]
    if not shown:
        top = pairs[0]
        return [tr("info.corr_none", thr=f"{threshold:g}", r=f"{float(top['corr']):+.3f}",
                   p1=q(top["param1"]), p2=q(top["param2"])), ""]
    lines = [f"**{_r('corr_table', thr=f'{threshold:g}')}**", "",
             f"| {_r('col_pair')} | r | |", "|---|---|---|"]
    for p in shown:
        r = float(p["corr"])
        flag = "⚠" if abs(r) >= 0.95 else ("!" if abs(r) >= 0.8 else "")
        lines.append(f"| {q(p['param1'])} ↔ {q(p['param2'])} | {r:+.3f} | {flag} |")
    lines += ["", f"> ℹ️ {tr('info.corr_legend').strip()}", ""]
    return lines


#: Hasta cuántos parámetros cabe la matriz como tabla en el informe; con más,
#: lista de parejas (la figura del PDF la dibuja siempre).
CORR_MATRIX_MAX = 12


def correlation_report_lines(corr: dict | None, *, code: bool = False) -> list[str]:
    """Correlaciones en el informe: matriz parámetro × parámetro (o parejas).

    Filas y columnas son los parámetros (columnas numeradas para que quepa);
    |r| ≥ 0.95 en negrita. Con más de ``CORR_MATRIX_MAX`` parámetros cae a
    la lista de parejas de :func:`correlation_table_lines`.
    """
    from core.result_views import correlation_matrix

    datos = correlation_matrix(corr)
    if datos is None:
        return []
    labels, m = datos
    if len(labels) > CORR_MATRIX_MAX:
        return correlation_table_lines((corr or {}).get("pairs") or [], code=code)
    q = (lambda s: f"`{s}`") if code else (lambda s: s)
    lines = [f"**{tr('info.corr_matrix_title')}**", "",
             "| | " + " | ".join(str(k + 1) for k in range(len(labels))) + " |",
             "|---|" + "---|" * len(labels)]
    for i, lab in enumerate(labels):
        celdas = []
        for j in range(len(labels)):
            r = m[i, j]
            if i == j:
                celdas.append("—")
            elif not np.isfinite(r):
                celdas.append("·")
            else:
                celdas.append(f"**{r:+.2f}**" if abs(r) >= 0.95 else f"{r:+.2f}")
        lines.append(f"| {i + 1} {q(lab)} | " + " | ".join(celdas) + " |")
    # Como nota (> …): el PDF ajusta al ancho los recuadros, no los párrafos.
    lines += ["", f"> ℹ️ {_r('corr_matrix_note')}", ""]
    return lines


def correlation_figure(corr: dict | None, title: str = ""):
    """Mapa de calor de la matriz de correlación (rojo +, azul −) o None."""
    from matplotlib.figure import Figure

    from core.result_views import correlation_matrix

    datos = correlation_matrix(corr)
    if datos is None:
        return None
    labels, m = datos
    n = len(labels)
    lado = min(max(3.2, 0.55 * n + 2.0), 9.0)
    fig = Figure(figsize=(lado + 1.0, lado), dpi=100, constrained_layout=True)
    ax = fig.add_subplot(111)
    import matplotlib

    # Gris para la diagonal y las parejas sin dato.
    cmap = matplotlib.colormaps["RdBu_r"].with_extremes(bad="#d1d5db")
    m_plot = np.array(m, dtype=float)
    np.fill_diagonal(m_plot, np.nan)
    im = ax.imshow(np.ma.masked_invalid(m_plot), cmap=cmap, vmin=-1, vmax=1)
    ax.set_xticks(range(n), [str(k + 1) for k in range(n)])
    ax.set_yticks(range(n), [f"{k + 1} {lab}" for k, lab in enumerate(labels)])
    if n <= 16:
        for i in range(n):
            for j in range(n):
                if i != j and np.isfinite(m[i, j]):
                    r = m[i, j]
                    ax.text(j, i, f"{r:+.2f}", ha="center", va="center",
                            fontsize=8 if n <= 10 else 6,
                            color="white" if abs(r) >= 0.55 else "#1f2937",
                            fontweight="bold" if abs(r) >= 0.95 else "normal")
    fig.colorbar(im, ax=ax, shrink=0.8, label="r")
    ax.set_title(title or tr("info.corr_matrix_title"), fontsize=11)
    return fig


def error_source_text(source: str) -> str:
    """Traduce la fuente de σ guardada en el estado (valor interno en español)."""
    import re
    s = str(source)
    if s.startswith("covarianza"):
        return _r("err_cov")
    m = re.match(r"bootstrap Monte Carlo \(n=(\d+)\)", s)
    if m:
        return _r("err_boot", n=m.group(1))
    return s


class ReportMixin:
    def _distribution_report_active(self) -> bool:
        """¿El informe es de distribución? (modo distribución en la GUI)."""
        return bool(getattr(self, "is_distribution_mode", False))

    def _distribution_report_lines(self, *, short: bool = False) -> list[str]:
        """Bloque de informe del ajuste de distribución (1D y 2D).

        Completo: montaje (modo, forma, regularizador, α, malla), bondad del
        ajuste (χ², ν, χ²ᵣ, AIC/BIC comparables con el discreto, RMS y
        diagnóstico del residuo), parámetros globales con su σ, la
        distribución (media, σ, moda, gaussianas VBF/2D, binomial), los
        componentes nítidos y los avisos. Reducido: una línea de montaje, otra
        de bondad y la tabla de globales. ``[]`` si no hay resultado.
        """
        import html
        import re

        import numpy as np
        result = getattr(self.runtime_results, "distribution_result", None)
        if result is None:
            return []
        view = distribution_result_view(result)
        s = self._distribution_summary(result)
        g, m = s["goodness"], s["moments"]

        def _fmt(v, nd=".6g"):
            try:
                return format(float(v), nd)
            except (TypeError, ValueError):
                return str(v)

        shape = getattr(result, "shape", None) or "—"
        reg_mode = getattr(result, "reg_mode", None)
        is_2d = view.is_2d()
        regularized_2d = is_2d and shape == "2D"
        _short = {"bhf": "BHF", "quad": "ΔEQ", "delta": "δ"}
        x2 = _short.get(getattr(result, "x_variable", "bhf"), "BHF")
        y2 = _short.get(getattr(result, "y_variable", "quad"), "ΔEQ")
        var = s["variable"] or "bhf"
        var_lbl = _short.get(var, "BHF")
        unit = "T" if var == "bhf" else "mm/s"
        modo = f"P({x2}, {y2})" if is_2d else f"P({ {'delta': 'IS'}.get(var, var_lbl) })"
        iso_ref = self.calibration_iso_ref()

        def _bondad_bits() -> list[str]:
            bits = []
            if "red_chi2" in g:
                bits.append(f"χ²ᵣ = **{g['red_chi2']:.4g}**")
            if "chi2" in g:
                bits.append(f"χ² = {g['chi2']:.4g}")
            if "dof" in g:
                bits.append(f"ν = {g['dof']:.4g}")
            for k, lbl in (("aic", "AIC"), ("bic", "BIC")):
                if k in g:
                    bits.append(f"{lbl} = {g[k]:.4g}")
            return bits

        def _tabla_globales() -> list[str]:
            if not s["globals"]:
                return []
            out = [f"| {_r('col_param')} | {_r('col_value')} | σ | {_r('col_state')} |",
                   "|---|---|---|---|"]
            for f in s["globals"]:
                err = f"± {f['sigma']:.3g}" if f["sigma"] else "—"
                estado = f"🔓 {_r('free')}" if f["free"] else f"🔒 {_r('fixed')}"
                out.append(f"| {f['label']} | {f['value']:.6g} {f['unit']} | {err} | {estado} |")
                if f["key"] == "dist_delta" and iso_ref is not None:
                    out.append(f"| {_r('delta_corr')} (iso_ref = {iso_ref:.6g}) | "
                               f"**{f['value'] - iso_ref:.6g} mm/s** | {err} | |")
            return out

        lines: list[str] = []
        if short:
            bits = [modo, _r("dist_short_shape", shape=shape)]
            if reg_mode:
                bits.append(_r("dist_short_reg", mode=reg_mode))
            if regularized_2d:
                bits.append(f"α{x2}={_fmt(getattr(result, 'alpha_bhf', None), '.3g')}")
                bits.append(f"α{y2}={_fmt(getattr(result, 'alpha_quad', None), '.3g')}")
            elif not is_2d and shape == "Histograma":
                bits.append(f"α={_fmt(getattr(result, 'alpha', None), '.3g')}")
            if m:
                bits.append(f"⟨{var_lbl}⟩={m['mean']:.4g} {unit}")
                bits.append(f"σ={m['std']:.3g} {unit}")
            lines.append(f"**{_r('dist_label')}:** " + " · ".join(bits))
            lines.append("")
            if _bondad_bits():
                lines.append("> " + " · ".join(_bondad_bits()))
                lines.append("")
            tabla = _tabla_globales()
            if tabla:
                lines.append(f"## {_r('globals_header')}")
                lines.append("")
                lines.extend(tabla)
                lines.append("")
            return lines

        # ── Montaje ─────────────────────────────────────────────────────
        lines.append(f"## 🌫️ {_r('dist_header')}")
        lines.append("")
        lines.append(f"| {_r('col_field')} | {_r('col_value')} |")
        lines.append("|---|---|")
        lines.append(f"| {_r('dist_mode')} | {modo} |")
        lines.append(f"| {_r('shape')} | {shape} |")
        if reg_mode and (shape == "Histograma" or regularized_2d):
            lines.append(f"| {_r('regularizer')} | {reg_mode} |")
        if regularized_2d:
            lines.append(f"| α ({x2}) | {_fmt(getattr(result, 'alpha_bhf', None))} |")
            lines.append(f"| α ({y2}) | {_fmt(getattr(result, 'alpha_quad', None))} |")
        elif not is_2d and shape == "Histograma":
            lines.append(f"| {_r('alpha_reg')} | {_fmt(getattr(result, 'alpha', None))} |")
        # En 1D el resultado no trae x_variable: la etiqueta es la variable
        # ajustada (antes ponía «BHF» también en P(ΔEQ) y P(IS)).
        ejes = [(x2 if is_2d else var_lbl, view.result.bhf_centers)]
        if is_2d:
            ejes.append((y2, view.result.quad_centers))
        for lbl, c in ejes:
            c = np.asarray(c, dtype=float)
            if c.size:
                lines.append(f"| {_r('grid')} ({lbl}) | {c.min():.4g} – {c.max():.4g}, "
                             f"{_r('n_bins', n=c.size)} |")
        lines.append(f"| {_r('baseline')} | {_fmt(result.baseline)} |")
        lines.append(f"| {_r('bg_slope')} | {_fmt(result.slope)} |")
        lines.append("")

        # ── Bondad del ajuste ───────────────────────────────────────────
        lines.append(f"### 📐 {_r('sec_goodness')}")
        lines.append("")
        lines.append(f"| {_r('col_indicator')} | {_r('col_value')} |")
        lines.append("|---|---|")
        lines.append(f"| {_r('n_points')} | {int(g['n_points'])} |")
        if "chi2" in g:
            lines.append(f"| χ² | {g['chi2']:.6g} |")
        if "n_params" in g:
            lines.append(f"| {_r('k_dist')} | {g['n_params']:.4g} |")
        if "dof" in g:
            lines.append(f"| ν = N − k | {g['dof']:.6g} |")
        if "red_chi2" in g:
            lines.append(f"| {_r('red_chi2')} | {g['red_chi2']:.6g} |")
        if "hesse_ruebartsch" in g:
            lines.append(f"| {_r('hesse_ruebartsch')} | {g['hesse_ruebartsch']:.4f} |")
        for k, lbl in (("aic", "AIC"), ("bic", "BIC")):
            if k in g:
                lines.append(f"| {lbl} | {g[k]:.6g} |")
        lines.append(f"| {_r('fit_rms')} | {g['rms']:.6g} |")
        lines.append("")
        if not s["has_sigma"]:
            lines.append(f"> ⚠️ {_r('dist_no_sigma')}")
            lines.append("")
        elif "aic" in g:
            lines.append(f"> ℹ️ {_r('dist_aic_note')}")
            lines.append("")
        lag1, runs = g.get("resid_lag1"), g.get("resid_runs_z")
        if lag1 is not None and lag1 == lag1:
            lines.append(f"**{_r('resid_diag')}**")
            lines.append("")
            lines.append(f"| {_r('col_statistic')} | {_r('col_value')} | {_r('col_threshold')} |")
            lines.append("|---|---|---|")
            lines.append(f"| {_r('lag1')} | {lag1:.3f} | ∉ [−0.35, 0.35] |")
            if runs is not None and runs == runs:
                lines.append(f"| {_r('runs')} | {runs:.3f} | ∉ [−2, 2] |")
            lines.append("")
            if abs(lag1) > 0.35 or (runs is not None and runs == runs and abs(runs) > 2.0):
                lines.append(f"> ⚠️ {_r('resid_warning')}")
                lines.append("")

        # ── Parámetros globales ─────────────────────────────────────────
        tabla = _tabla_globales()
        if tabla:
            lines.append(f"### 🎚️ {_r('globals_header')}")
            lines.append("")
            lines.extend(tabla)
            lines.append("")
            for a, b, r in s["high_corr"]:
                lines.append(f"> ⚠️ {_r('high_corr')}: {a} ↔ {b}, r = {r:.3f}")
                lines.append("")
        # Correlaciones entre globales y con la media/anchura de P.
        lines.extend(correlation_report_lines(s.get("correlations")))

        # ── La distribución ─────────────────────────────────────────────
        lines.append(f"### 📊 {_r('dist_stats_header')}")
        lines.append("")
        lines.append(f"| {_r('col_quantity')} | {_r('col_value')} |")
        lines.append("|---|---|")
        if m:
            pm = lambda k: (f" ± {m[k + '_sigma']:.2g}" if m.get(k + "_sigma") else "")
            lines.append(f"| {tr('info.p_mean', var=var_lbl)} | {m['mean']:.6g}{pm('mean')} {unit} |")
            lines.append(f"| {tr('info.p_width', var=var_lbl)} | {m['std']:.6g}{pm('std')} {unit} |")
            lines.append(f"| {_r('mode_peak')} | {m['mode']:.6g} {unit} |")
            if "skew" in m:
                lines.append(f"| {tr('info.p_skew', var=var_lbl)} | {m['skew']:.3f} |")
                lines.append(f"| {tr('info.p_kurtosis', var=var_lbl)} | {m['kurtosis']:.3f} |")
        for key, lbl in (("fitted_dist_p", _r("binom_c")),
                         ("binomial_n", _r("binom_n")),
                         ("binomial_start", _r("binom_start")),
                         ("binomial_step", _r("binom_step"))):
            val = getattr(result, key, None)
            if val is not None:
                lines.append(f"| {lbl} | {_fmt(val)} |")
        for key, lbl in (("czjzek_sigma", _r("czjzek_sigma")),
                         ("czjzek_delta0", _r("czjzek_delta0"))):
            val = getattr(result, key, None)
            if val is not None:
                err = getattr(result, f"{key}_err", None)
                txt = _fmt(val, ".4g") + (f" ± {_fmt(err, '.2g')}" if err is not None else "")
                lines.append(f"| {lbl} | {txt} mm/s |")
        sb = getattr(result, "vbf_sigma_bounds", None)
        if sb:
            lines.append(f"| {_r('vbf_sigma_bounds')} ({var_lbl}) | "
                         f"{_fmt(sb[0], '.4g')} – {_fmt(sb[1], '.4g')} {unit} |")
        sb2 = getattr(result, "vbf2d_sigma_bounds", None)
        if sb2:
            for lbl_ax, var_ax, (s_lo, s_hi) in (
                    (x2, getattr(result, "x_variable", "bhf"), sb2[0]),
                    (y2, getattr(result, "y_variable", "quad"), sb2[1])):
                u_ax = "T" if var_ax == "bhf" else "mm/s"
                lines.append(f"| {_r('vbf_sigma_bounds')} ({lbl_ax}) | "
                             f"{_fmt(s_lo, '.4g')} – {_fmt(s_hi, '.4g')} {u_ax} |")
        if is_2d:
            for key, lbl in (("mean_bhf", f"⟨{x2}⟩"), ("mean_quad", f"⟨{y2}⟩"),
                             ("sigma_bhf", f"σ({x2})"), ("sigma_quad", f"σ({y2})"),
                             ("corr_bhf_quad", f"{_r('correlation')} {x2}–{y2}")):
                val = getattr(result, key, None)
                if val is not None:
                    lines.append(f"| {lbl} | {_fmt(val)} |")
        if getattr(result, "probability_sigma", None) is not None:
            lines.append(f"| σ(P) | {_r('dist_band_note')} |")
        lines.append("")

        vbf = getattr(result, "vbf_components", None)
        if vbf:
            lines.append(f"**{_r('vbf_header')}**")
            lines.append("")
            # A_k es el área de cada gaussiana (normalizadas a área unidad).
            area_tot = sum(max(float(c[0]), 0.0) for c in vbf)
            lines.append(f"| # | {_r('col_area_a')} | {_r('col_area_pct')} | μ ({unit}) | σ ({unit}) |")
            lines.append("|---|---|---|---|---|")
            for i, (a, mu, sg) in enumerate(vbf, start=1):
                frac = (100.0 * float(a) / area_tot) if area_tot > 0 else 0.0
                lines.append(f"| {i} | {_fmt(a, '.4g')} | {_fmt(frac, '.1f')} | "
                             f"{_fmt(mu, '.4g')} | {_fmt(sg, '.4g')} |")
            lines.append("")
        g2 = getattr(result, "vbf2d_components", None)
        if g2:
            lines.append(f"**{_r('g2d_header')}**")
            lines.append("")
            area_tot = sum(float(c[0]) for c in g2)
            lines.append(f"| # | {_r('col_area_a')} | {_r('col_area_pct')} | μ {x2} | μ {y2} | σ {x2} | σ {y2} | ρ |")
            lines.append("|---|---|---|---|---|---|---|---|")
            for i, (a, mx, my, sx, sy, rho) in enumerate(g2, start=1):
                frac = (100.0 * float(a) / area_tot) if area_tot > 0 else 0.0
                lines.append(
                    f"| {i} | {_fmt(a, '.4g')} | {_fmt(frac, '.1f')} | {_fmt(mx, '.4g')} | "
                    f"{_fmt(my, '.4g')} | {_fmt(sx, '.4g')} | {_fmt(sy, '.4g')} | {_fmt(rho, '.3f')} |")
            lines.append("")

        # ── Componentes nítidos ─────────────────────────────────────────
        sw = getattr(result, "sharp_weights", None)
        sharp, indices = self._active_sharp_components_for_distribution()
        if sw is not None and np.asarray(sw).size and sharp and len(indices) == np.asarray(sw).size:
            lines.append(f"### 🔹 {_r('sharp_header')}")
            lines.append("")
            lines.append(f"| # | {_r('col_type')} | δ (mm/s) | ΔEQ (mm/s) | BHF (T) | Γ (mm/s) | {_r('depth')} |")
            lines.append("|---|---|---|---|---|---|---|")
            for idx, comp, w in zip(indices, sharp, np.asarray(sw, dtype=float)):
                kind = tr(f"kind.{comp['kind']}", default=comp["kind"])
                bhf = f"{comp['bhf']:.5g}" if comp["kind"] in (
                    "Sextete", "Relajacion", "BlumeTjon", "NeelSize") else "—"
                quad = f"{comp['quad']:.4g}" if comp["kind"] != "Singlete" else "—"
                lines.append(f"| {idx} | {kind} | {comp['delta']:.4g} | {quad} | {bhf} | "
                             f"{comp['gamma']:.4g} | {w:.4g} |")
            lines.append("")

        # ── Avisos ──────────────────────────────────────────────────────
        avisos = []
        pile = getattr(result, "edge_pileup", None)
        if pile is not None and pile > 0.3:
            avisos.append(_r("dist_edge_pileup", pct=f"{100.0 * pile:.0f}"))
        if getattr(result, "dof_warning", None):
            avisos.append(str(result.dof_warning))
        panel = getattr(getattr(self, "dist_panel", None), "var_warning", None)
        if panel is not None and panel.text():
            txt = html.unescape(re.sub(r"<a\b.*?</a>", "", panel.text()))
            avisos.append(re.sub(r"<[^>]+>", "", txt).strip().lstrip("⚠").strip())
        if avisos:
            lines.append(f"### ⚠️ {_r('warnings_header')}")
            lines.append("")
            for a in avisos:
                lines.append(f"> ⚠️ {a}")
                lines.append("")
        return lines

    def _correlation_report_figure(self):
        """Mapa de calor de las correlaciones del ajuste activo, o None."""
        try:
            if self._distribution_report_active():
                result = getattr(self.runtime_results, "distribution_result", None)
                corr = (self._distribution_summary(result).get("correlations")
                        if result is not None else None)
            else:
                result = self.runtime_results.fit_result
                corr = getattr(result, "correlations", None) if result is not None else None
            return correlation_figure(corr)
        except Exception:
            return None

    def _distribution_report_figure(self):
        """Figura de la distribución para el PDF (P(x) o el mapa 2D), o None."""
        result = getattr(self.runtime_results, "distribution_result", None)
        if result is None or not self._distribution_report_active():
            return None
        try:
            if distribution_result_view(result).is_2d():
                return self._distribution_figure_2d(result)
            return self._distribution_figure_1d(result)[0]
        except Exception:
            return None

    def _glossary_lines(self, *, distribution: bool = False) -> list[str]:
        """Glosario del informe; en distribución, sin los parámetros que solo
        tiene el ajuste discreto y con α, κ y P(x)."""
        lines: list[str] = []
        filas = (
            ("δ", "gl_delta", "mm/s", "gl_delta_note"),
            ("ΔEQ (`quad`)", "gl_quad", "mm/s", "gl_quad_note"),
            ("BHF", "gl_bhf", "T", "gl_bhf_note"),
            ("Γ (FWHM)", "gl_gamma", "mm/s", "gl_gamma_note"),
            ("`depth`", "gl_depth", "(rel.)", "gl_depth_note"),
            ("`int1/2/3`", "gl_int", "(rel.)", "gl_int_note"),
            ("`texture` (t)", "gl_texture", "(0–1)", "gl_texture_note"),
            ("`beta` (β)", "gl_beta", "°", "gl_beta_note"),
            ("`voigt_sigma`", "gl_voigt", "mm/s", "gl_voigt_note"),
            ("`sat_scale`", "gl_sat", "(rel.)", "gl_sat_note"),
            ("`baseline` / `slope`", "baseline", "(rel.)", "gl_baseline_note"),
            ("Vmax (`vmax`)", "gl_vmax", "mm/s", "gl_vmax_note"))
        if distribution:
            solo_discreto = {"gl_depth", "gl_int", "gl_texture", "gl_beta", "gl_sat"}
            filas = tuple(f for f in filas if f[1] not in solo_discreto) + (
                ("P(x)", "gl_p", "—", "gl_p_note"),
                ("α", "gl_alpha", "—", "gl_alpha_note"),
                ("κδ / κq", "gl_kappa", "mm/s·T⁻¹ / —", "gl_kappa_note"),
                ("k, ν", "gl_k", "—", "gl_k_note"))
        lines.append(f"## 📖 {_r('sec_glossary')}")
        lines.append("")
        lines.append(f"| {_r('col_symbol')} | {_r('col_quantity')} | {_r('col_unit')} | {_r('col_remark')} |")
        lines.append("|---|---|---|---|")
        for sym, name, unit, note in filas:
            lines.append(f"| {sym} | {_r(name)} | {unit} | {_r(note)} |")
        lines.append("")
        return lines

    # ── Copiar resultados al portapapeles ────────────────────────────────
    def on_copy_results(self) -> bool:
        """Copia los parámetros ajustados como texto pegable.

        Existían el TSV y los informes, pero para llevar cuatro números al
        cuaderno o a un correo había que escribir un fichero. Esto lo deja en
        el portapapeles en formato tabulado, que Excel/Origin pegan en
        columnas y el correo respeta.
        """
        from PySide6 import QtWidgets as _qw

        lineas = self._results_as_text()
        if not lineas:
            self.statusBar().showMessage(
                tr("results.nothing_to_copy",
                   default="No hay resultados que copiar: ajusta primero."), 5000)
            return False
        _qw.QApplication.clipboard().setText("\n".join(lineas))
        self.statusBar().showMessage(
            tr("results.copied", default="Resultados copiados al portapapeles"), 5000)
        return True

    def _results_as_text(self) -> list[str]:
        """Tabla de parámetros del último ajuste, con errores y estadísticos.

        Solo lo que se quiere pegar: los componentes ACTIVOS con los parámetros
        que su tipo usa, más los globales. Volcar los 10 componentes con sus 25
        parámetros daban 269 líneas para un ajuste de un doblete.
        """
        from core.result_views import discrete_result_view

        resultado = getattr(self.runtime_results, "fit_result", None)
        if resultado is None:
            return []
        vista = discrete_result_view(resultado, fixed=dict(self._fixed_map()))
        valores = getattr(resultado, "values", {}) or {}
        libres = set(vista.free_keys())

        def num(v):
            return "" if v is None else f"{float(v):.6g}"

        def fila(clave, etiqueta=None):
            if clave not in valores:
                return None
            return "\t".join((etiqueta or clave, num(valores.get(clave)),
                              num(vista.error_for(clave)),
                              "" if clave in libres else _r("fixed")))

        lineas: list[str] = []
        nombre = self.file.path.name if getattr(self.file, "path", None) else "—"
        lineas.append(f"# {nombre}")
        for clave, etiqueta in (("red_chi2", "chi2_red"), ("chi2", "chi2"),
                                ("aic", "AIC"), ("bic", "BIC")):
            valor = vista.stat_for(clave)
            if valor is not None:
                lineas.append(f"# {etiqueta}\t{num(valor)}")
        lineas.append("")
        lineas.append(_r("copy_header"))

        # Globales: los de siempre, más cualquiera que se haya liberado.
        globales = ["vmax", "center", "baseline", "slope"]
        globales += [k for k in ("curv", "curv3", "curv4", "voigt_sigma",
                                 "sat_scale", "src_fwhm", "src_frac", "line_asym")
                     if k in libres]
        for clave in globales:
            f = fila(clave)
            if f:
                lineas.append(f)

        # Componentes activos, con los parámetros que su tipo usa.
        for cp in getattr(self, "components_panels", []):
            if not cp.enabled.isChecked():
                continue
            lineas.append("")
            lineas.append(f"# {_r('copy_component')} {cp.idx}\t{cp.kind}")
            for nombre_p in sorted(cp.relevant_params()):
                f = fila(f"s{cp.idx}_{nombre_p}", nombre_p)
                if f:
                    lineas.append(f)
        return lineas

    def _fixed_map(self) -> dict:
        """Mapa parámetro → fijo, tal y como lo ven los paneles."""
        fijos: dict[str, bool] = {}
        calib = self.calib.to_view_state()
        for nombre in ("baseline", "slope", "curv", "curv3", "curv4",
                       "sat_scale", "src_fwhm", "voigt_sigma"):
            fijos[nombre] = calib.is_fixed(nombre)
        for cp in getattr(self, "components_panels", []):
            estado = cp.to_view_state()
            for nombre, valor in (estado.fixed or {}).items():
                fijos[f"s{cp.idx}_{nombre}"] = bool(valor)
        return fijos

    def _build_report_lines(self) -> list[str]:
        """Genera el informe en Markdown estructurado por secciones.

        Recoge **toda** la información mostrada en el panel "Estado y
        parámetros" (espectro, calibración, bondad, diagnóstico residual,
        análisis de áreas, parámetros por componente con magnitudes físicas
        derivadas, δ corregidos por calibración, fijados y restricciones)
        y la presenta como tablas y bloques tipados.
        """
        from datetime import datetime
        file_name = self.file.path.name if self.file.path else "—"
        ci = self.calibration_info
        iso_ref = self.calibration_iso_ref()
        fit = self.runtime_results.fit_result
        fit_view = discrete_result_view(fit) if fit is not None else None
        calib_state = self.calib.to_view_state()
        active_components = [
            cp.to_view_state() for cp in self.components_panels
            if cp.to_view_state().enabled
        ]

        def _ferr(v: float | None) -> str:
            return f"± {v:.3g}" if v is not None and v > 0 else "—"

        lines: list[str] = []
        lines.append(f"# 📊 Mössbauer Fe-57 — {_r('title')}")
        lines.append("")
        lines.append(
            f"**{_r('file')}:** `{file_name}` · **{_r('date')}:** "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')} · **{_r('program')}:** "
            f"{APP_NAME} v{APP_VERSION} (Qt)"
        )
        lines.append("")

        dist_mode = self._distribution_report_active()
        dist_result = getattr(self.runtime_results, "distribution_result", None)
        if dist_mode and dist_result is not None:
            g = self._distribution_summary(dist_result)["goodness"]
            bits = []
            if "red_chi2" in g:
                bits.append(f"χ²ᵣ = **{g['red_chi2']:.4g}**")
            if "chi2" in g:
                bits.append(f"χ² = {g['chi2']:.4g}")
            if "dof" in g:
                bits.append(f"ν = {g['dof']:.4g}")
            for k, lbl in (("aic", "AIC"), ("bic", "BIC")):
                if k in g:
                    bits.append(f"{lbl} = {g[k]:.4g}")
            lines.append(f"> ### 🎯 {_r('summary_header')}")
            lines.append("> " + (" · ".join(bits) if bits else f"RMS = {g['rms']:.4g}"))
            lines.append("")
        elif dist_mode:
            lines.append(f"> ⚠️ {_r('no_dist_result')}")
            lines.append("")
        elif fit_view is not None and fit_view.metrics():
            st = {metric.key: metric.value for metric in fit_view.metrics()}
            bits = []
            if st.get("red_chi2") is not None:
                bits.append(f"χ²ᵣ = **{st['red_chi2']:.4g}**")
            if st.get("chi2") is not None:
                bits.append(f"χ² = {st['chi2']:.4g}")
            if st.get("dof") is not None:
                bits.append(f"dof = {int(st['dof'])}")
            if st.get("aic") is not None:
                bits.append(f"AIC = {st['aic']:.4g}")
            if st.get("bic") is not None:
                bits.append(f"BIC = {st['bic']:.4g}")
            lines.append(f"> ### 🎯 {_r('summary_header')}")
            lines.append("> " + " · ".join(bits))
            lines.append(
                f"> {_r('n_free', n=len(fit_view.free_keys()))} · "
                f"σ: {error_source_text(self.runtime_results.error_source)}"
            )
            lines.append("")

        # ── Ajuste de distribución (si aplica) ──────────────────────────
        if dist_mode:
            lines.extend(self._distribution_report_lines())

        # ── Espectro y plegado ──────────────────────────────────────────
        lines.append(f"## 📁 {_r('sec_spectrum')}")
        lines.append("")
        lines.append(f"| {_r('col_field')} | {_r('col_value')} |")
        lines.append("|---|---|")
        lines.append(f"| {_r('file')} | `{file_name}` |")
        n_chan = self.file.counts.size if self.file.counts is not None else 0
        lines.append(f"| {_r('channels_read')} | {n_chan} |")
        center_val = float(calib_state.center)
        lines.append(f"| {_r('fp_center')} | {center_val:.5f} |")
        lines.append(f"| {_r('fp_normos')} | {2.0 * center_val:.5f} |")
        if self.file.folded is not None:
            lines.append(f"| {_r('folded_pairs')} | {int(self.file.folded.size)} |")
        norm_factor = getattr(self.file, "norm_factor", None)
        if norm_factor is not None:
            lines.append(f"| {_r('normalization')} | / {norm_factor:.6g} |")
        perfil = {"Lorentziana": tr("options.profile_lorentzian"),
                  "Voigt": tr("options.profile_voigt")}.get(calib_state.line_profile,
                                                           calib_state.line_profile)
        lines.append(f"| {_r('line_profile')} | {perfil} |")
        lines.append("")

        # ── Calibración ──────────────────────────────────────────────────
        lines.append(f"## 🎛️ {_r('sec_calib')}")
        lines.append("")
        lines.append(f"| {_r('col_field')} | {_r('col_value')} |")
        lines.append("|---|---|")
        lines.append(f"| Vmax | {calib_state.vmax:.6g} mm/s |")
        lines.append(f"| {_r('baseline')} | {calib_state.baseline:.6g} |")
        lines.append(f"| {_r('bg_slope')} | {calib_state.slope:.6g} |")
        lines.append(f"| {_r('fit_vmax')} | "
                     f"{_r('yes') if calib_state.fit_velocity else _r('no')} |")
        if ci:
            sample = ci.get("calibration_sample") or ci.get("calibration_file_name") or "—"
            lines.append(f"| {_r('calib_source')} | {ci.get('source', '?')} |")
            lines.append(f"| {_r('sample')} | {sample} |")
            if ci.get("calibration_file_name"):
                lines.append(f"| {_r('calib_file')} | `{ci['calibration_file_name']}` |")
            if ci.get("velocity_calibrated") is not None:
                lines.append(
                    f"| {_r('vmax_calibrated')} | {float(ci['velocity_calibrated']):.6g} mm/s |"
                )
                if abs(self._calibration_scale() - 1.0) > 1e-12:
                    vmax_orig = f"{float(ci['velocity_calibrated']):.6g}"
                    lines.append(f"| | {tr('calib.converted', vmax=vmax_orig)} |")
            if iso_ref is not None:
                lines.append(f"| {_r('iso_ref_row')} | {iso_ref:.6g} mm/s |")
            if ci.get("calibration_date"):
                lines.append(f"| {_r('calib_date')} | {ci['calibration_date']} |")
        cal_unc = self.calibration_uncertainty_text()
        if cal_unc:
            lines.append("")
            lines.append(f"> ℹ️ {cal_unc}")
        elif not ci:
            lines.append("")
            lines.append(f"> ⚠️ {_r('no_calib')}")
        lines.append("")

        # En modo distribución lo que sigue (bondad, áreas y componentes del
        # ajuste discreto, fijados…) describe los paneles discretos, no el
        # ajuste hecho: solo el glosario.
        if dist_mode:
            lines.extend(self._glossary_lines(distribution=True))
            return lines

        # ── Bondad y diagnóstico del ajuste ──────────────────────────────
        stats = ({metric.key: metric.value for metric in fit_view.metrics()} if fit_view is not None else {}) or {}
        rms = self._info_rms()
        if stats or not (rms != rms):  # rms != rms ⇒ NaN
            lines.append(f"## 📐 {_r('sec_goodness')}")
            lines.append("")
            lines.append(f"| {_r('col_indicator')} | {_r('col_value')} |")
            lines.append("|---|---|")
            if stats.get("chi2") is not None:
                lines.append(f"| χ² | {stats['chi2']:.6g} |")
            if stats.get("red_chi2") is not None:
                lines.append(f"| {_r('red_chi2')} | {stats['red_chi2']:.6g} |")
            if stats.get("dof") is not None:
                lines.append(f"| dof | {int(stats['dof'])} |")
            if stats.get("aic") is not None:
                lines.append(f"| AIC | {stats['aic']:.6g} |")
            if stats.get("bic") is not None:
                lines.append(f"| BIC | {stats['bic']:.6g} |")
            if stats.get("n_params") is not None:
                lines.append(f"| {_r('n_params')} | {int(stats['n_params'])} |")
            if rms == rms:  # not NaN
                lines.append(f"| {_r('fit_rms')} | {rms:.6g} |")
            if fit_view is not None:
                lines.append(f"| {_r('n_starts')} | {int(fit_view.n_starts())} |")
            lines.append("")
            # Diagnóstico residual
            if any(k in stats for k in ("resid_lag1", "resid_runs_z")):
                lines.append(f"**{_r('resid_diag')}**")
                lines.append("")
                lines.append(f"| {_r('col_statistic')} | {_r('col_value')} | {_r('col_threshold')} |")
                lines.append("|---|---|---|")
                lines.append(f"| {_r('lag1')} | {stats.get('resid_lag1', float('nan')):.3f} | ∉ [−0.35, 0.35] |")
                lines.append(f"| {_r('runs')} | {stats.get('resid_runs_z', float('nan')):.3f} | ∉ [−2, 2] |")
                lines.append("")
                if (abs(stats.get("resid_lag1", 0.0)) > 0.35
                        or abs(stats.get("resid_runs_z", 0.0)) > 2.0):
                    lines.append(f"> ⚠️ {_r('resid_warning')}")
                    lines.append("")
            # Correlaciones
            corr = fit_view.correlations() if fit_view is not None else {}
            max_pair = corr.get("max_pair") or []
            max_abs = corr.get("max_abs_corr")
            if max_pair and max_abs is not None:
                lines.append(
                    _r("max_corr", p1=max_pair[0], p2=max_pair[1],
                       r=f"{float(max_abs):.3f}")
                )
                lines.append("")
            high = corr.get("high_pairs") or []
            if high:
                lines.append(f"> ⚠️ {_r('high_corr')}")
                lines.append("")
            lines.extend(correlation_report_lines(corr, code=True))

        # ── Análisis de áreas ───────────────────────────────────────────
        pct_active, areas, percentages = self.component_area_percentages()
        pct_errors = self.component_percentage_errors()
        if pct_active:
            lines.append(f"## 🥧 {_r('sec_areas')}")
            lines.append("")
            lines.append(f"| {_r('col_component')} | {_r('col_type')} | {_r('col_pct_area')} | σ (%) | {_r('col_abs_area')} |")
            lines.append("|---|---|---|---|---|")
            for idx, area, pct in zip(pct_active, areas, percentages):
                comp_state = self.components_panels[idx - 1].to_view_state()
                kind_disp = tr(f"kind.{comp_state.kind}", default=comp_state.kind)
                err = pct_errors.get(idx)
                err_txt = f"± {err:.3g}" if err is not None else "—"
                lines.append(
                    f"| {idx} | {kind_disp} | {pct:.3f}% | {err_txt} | {area:.6g} |"
                )
            lines.append("")

        # ── Componentes (parámetros + magnitudes físicas) ───────────────
        lines.append(f"## 🧪 {_r('sec_components')}")
        lines.append("")
        for comp_state in active_components:
            kind = comp_state.kind
            kind_disp = tr(f"kind.{kind}", default=kind)
            lines.append(f"### 🔹 {_r('component_title', idx=comp_state.idx, kind=kind_disp)}")
            lines.append("")
            used = USED_BY.get(kind, set())
            uses_gamma2 = "gamma2" in used
            uses_gamma3 = "gamma3" in used
            uses_bhf = "bhf" in used
            uses_quad = "quad" in used
            uses_int1 = "int1" in used  # True for magnetic/relaxation kinds
            lines.append(f"**{_r('params')}**")
            lines.append("")
            lines.append(f"| {_r('col_param')} | {_r('col_value')} | {_r('col_state')} |")
            lines.append("|---|---|---|")
            for k, value in comp_state.values.items():
                if k not in used:
                    continue
                state_lbl = f"🔒 {_r('fixed')}" if comp_state.is_fixed(k) else f"🔓 {_r('free')}"
                lines.append(f"| `s{comp_state.idx}_{k}` | {value:.6g} | {state_lbl} |")
            lines.append("")
            # Magnitudes físicas derivadas: anchuras reales e intensidades absolutas
            g1 = comp_state.value("gamma1")
            lines.append(f"**{_r('derived')}**")
            lines.append("")
            lines.append(f"| {_r('col_quantity')} | {_r('col_value')} |")
            lines.append("|---|---|")
            if uses_gamma2 and uses_gamma3:
                g2 = g1 * comp_state.value("gamma2", 1.0)
                g3 = g1 * comp_state.value("gamma3", 1.0)
                lines.append(f"| {_r('real_g123')} | {g1:.4g} / {g2:.4g} / {g3:.4g} |")
                lines.append(f"| {_r('rel_g23')} | {comp_state.value('gamma2', 1.0):.4g} / {comp_state.value('gamma3', 1.0):.4g} |")
            elif uses_gamma2:
                g2 = g1 * comp_state.value("gamma2", 1.0)
                lines.append(f"| {_r('real_g12')} | {g1:.4g} / {g2:.4g} |")
                lines.append(f"| {_r('rel_g2')} | {comp_state.value('gamma2', 1.0):.4g} |")
            else:
                lines.append(f"| Γ FWHM (mm/s) | {g1:.4g} |")
            lines.append(f"| {_r('depth')} | {comp_state.value('depth'):.6g} |")
            if uses_bhf:
                lines.append(f"| BHF | {comp_state.value('bhf'):.6g} T |")
            lines.append(f"| {_r('delta_uncorr')} | {comp_state.value('delta'):.6g} mm/s |")
            if uses_quad:
                lines.append(f"| ΔEQ | {comp_state.value('quad'):.6g} mm/s |")
            if iso_ref is not None:
                lines.append(
                    f"| **{_r('delta_corr')}** (iso_ref = {iso_ref:.6g}) | "
                    f"**{comp_state.value('delta') - iso_ref:.6g} mm/s** |"
                )
            if uses_int1:
                i3_real = comp_state.value("int3", 1.0)
                i2_real = i3_real * comp_state.value("int2", 1.0)
                i1_real = i3_real * comp_state.value("int1", 1.0)
                lines.append(f"| {_r('real_int')} | {i1_real:.4g} / {i2_real:.4g} / {i3_real:.4g} |")
            lines.append("")
            # Textura derivada: solo para Sextete
            if kind == "Sextete":
                derived = self.texture_derived(comp_state)
                if derived is not None:
                    lines.append(f"**🧭 {_r('texture_header')}**")
                    lines.append("")
                    lines.append(f"| {_r('col_quantity')} | {_r('col_value')} | σ |")
                    lines.append("|---|---|---|")
                    lines.append(f"| {_r('t_param')} | {derived['t']:.4g} | {_ferr(derived['sigma_t'])} |")
                    lines.append(f"| {_r('theta')} | {derived['theta_deg']:.4g}° | {_ferr(derived['sigma_theta_deg'])} |")
                    lines.append(f"| R₂₃ = I₂/I₃ | {derived['r23']:.4g} | {_ferr(derived['sigma_r23'])} |")
                    lines.append(f"| S = ⟨P₂(cos θ)⟩ | {derived['s']:.4g} | {_ferr(derived['sigma_s'])} |")
                    lines.append("")
                    lines.append(f"> 💡 **{_r('interpretation')}:** {_r('texture_note')}")
                    lines.append("")

        # ── δ corregidos por calibración (resumen) ──────────────────────
        if iso_ref is not None and active_components:
            lines.append(f"## 🎯 {_r('sec_dcorr')}")
            lines.append("")
            lines.append(f"_{_r('iso_ref_line')}:_ **{iso_ref:.6g} mm/s**.")
            lines.append("")
            lines.append(f"| {_r('col_component')} | {_r('col_type')} | {_r('col_delta_fit')} | {_r('col_delta_corr')} |")
            lines.append("|---|---|---|---|")
            for comp_state in active_components:
                d = comp_state.value("delta")
                kind_disp = tr(f"kind.{comp_state.kind}", default=comp_state.kind)
                lines.append(
                    f"| {comp_state.idx} | {kind_disp} | {d:.6g} | **{d - iso_ref:.6g}** |"
                )
            lines.append("")

        # ── Parámetros libres (resumen rápido para tabla del ajuste) ────
        if fit_view is not None and fit_view.free_keys():
            lines.append(f"## 📈 {_r('sec_free')}")
            lines.append("")
            lines.append(f"_{_r('sigma_source')}:_ {error_source_text(self.runtime_results.error_source)}")
            lines.append("")
            lines.append(f"| {_r('col_param')} | {_r('col_value')} | σ |")
            lines.append("|---|---|---|")
            for estimate in fit_view.parameters(keys=fit_view.free_keys()):
                val = estimate.value
                err = estimate.error
                val_txt = f"{val:.6g}" if val is not None else "—"
                err_txt = f"± {err:.3g}" if err is not None and err > 0 else "—"
                lines.append(f"| `{estimate.key}` | {val_txt} | {err_txt} |")
            lines.append("")

        # ── Fijados y restricciones ──────────────────────────────────────
        fixed = self._fixed_param_keys()
        if fixed:
            lines.append(f"## 🔒 {_r('sec_fixed')}")
            lines.append("")
            lines.append(", ".join(f"`{k}`" for k in fixed))
            lines.append("")
        if self.constraints:
            lines.append(f"## 🔗 {_r('sec_constraints')}")
            lines.append("")
            lines.append(f"| {_r('col_target')} | {_r('col_formula')} |")
            lines.append("|---|---|")
            for c in self.constraints:
                lines.append(
                    f"| `{c['target']}` | "
                    f"{c.get('factor', 1.0):g} · `{c['source']}` + "
                    f"{c.get('offset', 0.0):g} |"
                )
            lines.append("")

        lines.extend(self._glossary_lines())
        return lines

    @staticmethod
    def _md_strip_inline(text: str) -> str:
        """Limpia marcadores Markdown y emojis para renderizado en PDF.

        Elimina ``**bold**``, ``*italic*`` y `` `code` `` (se conserva el texto
        sin los caracteres de formato) y quita los emojis fuera del BMP que
        DejaVu (la fuente por defecto de matplotlib) no puede renderizar.
        """
        import re
        out = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        out = re.sub(r"\*(.+?)\*", r"\1", out)
        out = re.sub(r"`([^`]+)`", r"\1", out)
        # Quita emojis (Misc Symbols and Pictographs, Emoticons, Transport,
        # Supplemental Symbols and Pictographs, Dingbats, etc.).
        out = re.sub(
            "["
            "\U0001F300-\U0001F9FF"
            "\U0001FA00-\U0001FAFF"
            "\U00002600-\U000027BF"
            "]\\s?",
            "", out,
        )
        return out.strip()

    def _md_to_blocks(self, md_lines: list[str]) -> list[tuple[str, object]]:
        """Convierte líneas Markdown en bloques tipados ``(kind, data)``.

        Reconoce: encabezados ``### h3``, tablas GFM ``| … |``, callouts
        ``> …``, bloques de código `` ``` `` y párrafos consecutivos.
        """
        blocks: list[tuple[str, object]] = []
        i, n = 0, len(md_lines)
        while i < n:
            raw = md_lines[i]
            s = raw.strip()
            if not s:
                i += 1
                continue
            if s.startswith("### "):
                blocks.append(("h3", s[4:].strip()))
                i += 1
                continue
            if s.startswith("```"):
                j = i + 1
                buf: list[str] = []
                while j < n and not md_lines[j].strip().startswith("```"):
                    buf.append(md_lines[j])
                    j += 1
                blocks.append(("code", buf))
                i = j + 1
                continue
            if s.startswith(">"):
                buf = []
                while i < n and md_lines[i].strip().startswith(">"):
                    buf.append(md_lines[i].strip().lstrip(">").strip())
                    i += 1
                blocks.append(("callout", buf))
                continue
            if s.startswith("|") and s.endswith("|"):
                rows: list[str] = []
                while i < n and md_lines[i].strip().startswith("|") and md_lines[i].strip().endswith("|"):
                    rows.append(md_lines[i].strip())
                    i += 1
                is_table = (
                    len(rows) >= 2
                    and set(rows[1].replace("|", "").replace("-", "").replace(":", "").strip()) == set()
                )
                if is_table:
                    header = [c.strip() for c in rows[0].strip("|").split("|")]
                    data = [[c.strip() for c in r.strip("|").split("|")] for r in rows[2:]]
                    blocks.append(("table", (header, data)))
                else:
                    for r in rows:
                        blocks.append(("para", r))
                continue
            buf = [raw.rstrip()]
            j = i + 1
            while j < n and md_lines[j].strip() and not (
                md_lines[j].lstrip().startswith(("#", "|", ">", "```"))
            ):
                buf.append(md_lines[j].rstrip())
                j += 1
            blocks.append(("para", " ".join(s.strip() for s in buf).strip()))
            i = j
        return blocks

    def _render_pdf_report(self, pdf_path: "Path", md_lines: list[str]) -> None:
        """Renderiza el informe PDF con portada, banners de color, tablas
        reales (cuadrículas en vez de texto monoespaciado) y la gráfica
        actual al final. Solo depende de matplotlib."""
        from datetime import datetime
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib.figure import Figure as _PdfFigure
        from matplotlib.patches import Rectangle
        import textwrap as _tw

        SECTION_COLOR = "#1e40af"
        SECTION_COLOR_ALT = "#0f766e"
        ACCENT = "#dbeafe"
        TEXT_DARK = "#1f2937"
        TEXT_MUTED = "#475569"
        ZEBRA_BG = "#f8fafc"
        TABLE_BORDER = "#e2e8f0"
        CALLOUT_BG = "#fef3c7"
        CALLOUT_BAR = "#f59e0b"
        CODE_BG = "#f1f5f9"

        LEFT, RIGHT = 0.05, 0.95
        WIDTH = RIGHT - LEFT
        TOP_BODY = 0.92
        BOTTOM = 0.06

        def _open_page(title: str, color: str):
            fig = _PdfFigure(figsize=(8.27, 11.69), dpi=100, facecolor="white")
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.set_xlim(0, 1); ax.set_ylim(0, 1)
            ax.add_patch(Rectangle((0.0, 0.94), 1.0, 0.05,
                                   facecolor=color, edgecolor="none"))
            ax.text(LEFT, 0.965, self._md_strip_inline(title), color="white",
                    fontsize=14, fontweight="bold", va="center", ha="left")
            return fig, ax

        def _render_h3(ax, text, y):
            ax.text(LEFT, y - 0.022, self._md_strip_inline(text),
                    color=SECTION_COLOR, fontsize=11.5,
                    fontweight="bold", va="center", ha="left")
            ax.add_patch(Rectangle((LEFT, y - 0.038), 0.22, 0.0015,
                                   facecolor=SECTION_COLOR, edgecolor="none"))
            return y - 0.05

        def _wrap_lines(text, width):
            text = self._md_strip_inline(text)
            return _tw.wrap(text, width=width) or [""]

        def _render_para(ax, text, y, on_break):
            line_h = 0.020
            for ln in _wrap_lines(text, 110):
                if y - line_h < BOTTOM:
                    on_break()
                    y = TOP_BODY
                ax.text(LEFT, y - line_h * 0.7, ln,
                        color=TEXT_DARK, fontsize=9.5,
                        va="center", ha="left")
                y -= line_h
                ax = _current_ax()  # may have changed after on_break
            return y - 0.006

        def _render_callout(ax, lines, y, on_break):
            line_h = 0.020
            wrapped: list[str] = []
            for raw in lines:
                for w in _wrap_lines(raw, 105):
                    wrapped.append(w)
            if not wrapped:
                wrapped = [""]
            i_w = 0
            while i_w < len(wrapped):
                # Cuántas líneas caben antes del salto
                avail = int(max(0, (y - BOTTOM)) / line_h)
                if avail < 2:
                    on_break()
                    y = TOP_BODY
                    ax = _current_ax()
                    avail = int((y - BOTTOM) / line_h)
                take = min(avail, len(wrapped) - i_w)
                block_h = take * line_h + 0.012
                ax.add_patch(Rectangle((LEFT, y - block_h), WIDTH, block_h,
                                       facecolor=CALLOUT_BG, edgecolor="none"))
                ax.add_patch(Rectangle((LEFT, y - block_h), 0.006, block_h,
                                       facecolor=CALLOUT_BAR, edgecolor="none"))
                for k in range(take):
                    ax.text(LEFT + 0.015, y - 0.012 - k * line_h - line_h * 0.6,
                            wrapped[i_w + k], color="#7c2d12", fontsize=9.5,
                            va="center", ha="left")
                y -= block_h + 0.006
                i_w += take
            return y

        def _render_code(ax, lines, y, on_break):
            line_h = 0.018
            content = lines or [""]
            i_l = 0
            while i_l < len(content):
                avail = int(max(0, (y - BOTTOM)) / line_h)
                if avail < 2:
                    on_break()
                    y = TOP_BODY
                    ax = _current_ax()
                    avail = int((y - BOTTOM) / line_h)
                take = min(avail, len(content) - i_l)
                block_h = take * line_h + 0.010
                ax.add_patch(Rectangle((LEFT, y - block_h), WIDTH, block_h,
                                       facecolor=CODE_BG, edgecolor=TABLE_BORDER,
                                       linewidth=0.5))
                for k in range(take):
                    txt = content[i_l + k][:120]
                    ax.text(LEFT + 0.012, y - 0.008 - k * line_h - line_h * 0.6,
                            txt, color=TEXT_DARK, fontsize=8.5,
                            family="monospace", va="center", ha="left")
                y -= block_h + 0.006
                i_l += take
            return y

        def _render_table(ax, header, rows, y, on_break):
            # Calcular anchos por longitud máxima del contenido
            n_cols = len(header)
            if n_cols == 0:
                return y
            max_len = [len(self._md_strip_inline(header[c])) for c in range(n_cols)]
            for r in rows:
                for c in range(min(n_cols, len(r))):
                    max_len[c] = max(max_len[c], len(self._md_strip_inline(r[c])))
            total = sum(max_len) or 1
            col_w = [WIDTH * (m / total) for m in max_len]
            col_x = [LEFT]
            for c in range(n_cols - 1):
                col_x.append(col_x[-1] + col_w[c])
            row_h = 0.026
            header_h = 0.028

            def _draw_header(local_y):
                ax.add_patch(Rectangle((LEFT, local_y - header_h), WIDTH, header_h,
                                       facecolor=SECTION_COLOR, edgecolor="none"))
                for c, txt in enumerate(header):
                    ax.text(col_x[c] + col_w[c] * 0.04,
                            local_y - header_h * 0.55,
                            self._md_strip_inline(txt),
                            color="white", fontsize=9.0,
                            fontweight="bold", va="center", ha="left")
                return local_y - header_h

            # Espacio mínimo para encabezado + 1 fila
            if y - (header_h + row_h) < BOTTOM:
                on_break()
                y = TOP_BODY
                ax = _current_ax()
            y = _draw_header(y)
            for r_idx, row in enumerate(rows):
                if y - row_h < BOTTOM:
                    on_break()
                    y = TOP_BODY
                    ax = _current_ax()
                    y = _draw_header(y)
                bg = ZEBRA_BG if r_idx % 2 == 0 else "white"
                ax.add_patch(Rectangle((LEFT, y - row_h), WIDTH, row_h,
                                       facecolor=bg, edgecolor=TABLE_BORDER,
                                       linewidth=0.5))
                for c in range(n_cols):
                    cell = row[c] if c < len(row) else ""
                    txt = self._md_strip_inline(cell)
                    # Truncar si excede el ancho de columna
                    max_chars = max(4, int(col_w[c] * 95))
                    if len(txt) > max_chars:
                        txt = txt[: max_chars - 1] + "…"
                    ax.text(col_x[c] + col_w[c] * 0.04,
                            y - row_h * 0.55, txt,
                            color=TEXT_DARK, fontsize=8.8,
                            va="center", ha="left")
                y -= row_h
            return y - 0.010

        # Estado mutable de página actual durante el render
        _state = {"fig": None, "ax": None, "title": "", "color": SECTION_COLOR}

        def _current_ax():
            return _state["ax"]

        def _new_section_page(title, color, *, continuation=False):
            head = f"{title} ({_r('continued')})" if continuation else title
            fig, ax = _open_page(head, color)
            _state["fig"], _state["ax"] = fig, ax

        with PdfPages(pdf_path) as pdf:
            # — Portada —
            fig = _PdfFigure(figsize=(8.27, 11.69), dpi=100, facecolor="white")
            ax = fig.add_subplot(111); ax.axis("off")
            ax.set_xlim(0, 1); ax.set_ylim(0, 1)
            ax.add_patch(Rectangle((0.0, 0.78), 1.0, 0.16,
                                   facecolor=SECTION_COLOR, edgecolor="none"))
            ax.text(0.5, 0.88, "Mössbauer Fe-57", color="white",
                    fontsize=22, fontweight="bold", va="center", ha="center")
            ax.text(0.5, 0.82, _r("title"), color=ACCENT,
                    fontsize=14, va="center", ha="center")
            file_name = self.file.path.name if self.file.path else "—"
            ax.text(0.5, 0.72, file_name, color=TEXT_DARK, fontsize=12,
                    va="center", ha="center", family="monospace")
            ax.text(0.5, 0.685, datetime.now().strftime("%Y-%m-%d %H:%M"),
                    color=TEXT_MUTED, fontsize=10, va="center", ha="center")
            ax.text(0.5, 0.655, f"{APP_NAME} v{APP_VERSION} (Qt)",
                    color="#94a3b8", fontsize=9, va="center", ha="center")

            boxes: list[tuple[str, str]] = []
            fit = self.runtime_results.fit_result
            fit_view = discrete_result_view(fit) if fit is not None else None
            if fit_view is not None and fit_view.metrics():
                st = {metric.key: metric.value for metric in fit_view.metrics()}
                if st.get("red_chi2") is not None:
                    boxes.append((_r("red_chi2"), f"{st['red_chi2']:.4g}"))
                if st.get("chi2") is not None and st.get("dof") is not None:
                    boxes.append(("χ² · dof", f"{st['chi2']:.4g} · {int(st['dof'])}"))
                if st.get("aic") is not None:
                    boxes.append(("AIC", f"{st['aic']:.4g}"))
                if st.get("bic") is not None:
                    boxes.append(("BIC", f"{st['bic']:.4g}"))
            n_active = sum(1 for cp in self.components_panels if cp.to_view_state().enabled)
            boxes.append((_r("active_components"), str(n_active)))
            if fit_view is not None:
                boxes.append((_r("free_params"), str(len(fit_view.free_keys()))))
                boxes.append((_r("sigma_source"), error_source_text(self.runtime_results.error_source)))

            cols = 2
            box_w, box_h = 0.42, 0.07
            x0, y0, gx, gy = 0.06, 0.58, 0.06, 0.025
            for i, (lbl, val) in enumerate(boxes):
                r, c = divmod(i, cols)
                x = x0 + c * (box_w + gx)
                y = y0 - r * (box_h + gy)
                ax.add_patch(Rectangle((x, y - box_h), box_w, box_h,
                                       facecolor=ZEBRA_BG,
                                       edgecolor="#cbd5e1", linewidth=1))
                ax.text(x + 0.015, y - box_h * 0.28, lbl, fontsize=9,
                        color=TEXT_MUTED, va="center", ha="left")
                ax.text(x + box_w - 0.015, y - box_h * 0.65, val, fontsize=12,
                        color=SECTION_COLOR, va="center", ha="right",
                        fontweight="bold")
            pdf.savefig(fig, bbox_inches="tight")

            # — Cuerpo: secciones ## con bloques tipados —
            sections: list[tuple[str, list[str]]] = []
            current_title: str | None = None
            current_body: list[str] = []
            for ln in md_lines:
                if ln.startswith("## "):
                    if current_title is not None:
                        sections.append((current_title, current_body))
                    current_title = ln[3:].strip()
                    current_body = []
                elif ln.startswith("# "):
                    continue
                else:
                    current_body.append(ln)
            if current_title is not None:
                sections.append((current_title, current_body))

            for title, body in sections:
                blocks = self._md_to_blocks(body)
                if not blocks:
                    continue
                _state["title"] = title
                _state["color"] = SECTION_COLOR
                _new_section_page(title, SECTION_COLOR)
                y = TOP_BODY

                def _on_break():
                    pdf.savefig(_state["fig"], bbox_inches="tight")
                    _state["color"] = SECTION_COLOR_ALT
                    _new_section_page(_state["title"], _state["color"],
                                      continuation=True)

                for kind, data in blocks:
                    ax = _state["ax"]
                    if kind == "h3":
                        if y - 0.05 < BOTTOM:
                            _on_break(); y = TOP_BODY
                        y = _render_h3(_state["ax"], data, y)
                    elif kind == "para":
                        y = _render_para(_state["ax"], data, y, _on_break)
                    elif kind == "callout":
                        y = _render_callout(_state["ax"], data, y, _on_break)
                    elif kind == "code":
                        y = _render_code(_state["ax"], data, y, _on_break)
                    elif kind == "table":
                        header, rows = data
                        y = _render_table(_state["ax"], header, rows, y,
                                          _on_break)
                pdf.savefig(_state["fig"], bbox_inches="tight")

            pdf.savefig(self.canvas.fig, bbox_inches="tight")
            # La figura de la distribución se construye del resultado actual
            # (antes: la del último diálogo 2D abierto, aunque fuera de otro
            # ajuste, y ninguna en 1D).
            fig_dist = self._distribution_report_figure()
            if fig_dist is not None:
                pdf.savefig(fig_dist, bbox_inches="tight")
            fig_corr = self._correlation_report_figure()
            if fig_corr is not None:
                pdf.savefig(fig_corr, bbox_inches="tight")

    def on_export_report(self) -> None:
        """Exporta un informe Markdown del ajuste actual."""
        if self.file.path is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("file.export_report"), str(ROOT),
            "Markdown (*.md);;All (*.*)")
        if not path:
            return
        state = self._build_state()
        if state is None:
            return
        lines = self._build_report_lines()
        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8")
            self.statusBar().showMessage(_r("saved", path=path), 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("file.export_report"),
                                            f"{type(exc).__name__}: {exc}")
            return

        want_pdf = QtWidgets.QMessageBox.question(
            self, tr("file.export_report"),
            tr("msg.report_ask_pdf",
               default="Informe Markdown guardado. ¿Generar también un PDF?"),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes)
        if want_pdf != QtWidgets.QMessageBox.Yes:
            return
        try:
            pdf_path = Path(path).with_suffix(".pdf")
            self._render_pdf_report(pdf_path, lines)
            self.statusBar().showMessage(_r("saved_pdf", path=path), 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, tr("file.export_report"),
                _r("pdf_failed", error=f"{type(exc).__name__}: {exc}"))

    # ── Informe reducido ────────────────────────────────────────────────
    def _build_short_report_lines(self) -> list[str]:
        """Informe reducido: parámetros por componente, áreas y figura."""
        from datetime import datetime
        file_name = self.file.path.name if self.file.path else "—"
        iso_ref = self.calibration_iso_ref()
        fit = self.runtime_results.fit_result
        fit_view = discrete_result_view(fit) if fit is not None else None
        active_components = [
            cp.to_view_state() for cp in self.components_panels
            if cp.to_view_state().enabled
        ]

        lines: list[str] = []
        lines.append(f"# Mössbauer Fe-57 — {file_name}")
        lines.append(f"_{datetime.now().strftime('%Y-%m-%d %H:%M')} · {APP_NAME} v{APP_VERSION}_")
        lines.append("")

        # En modo distribución, el resumen del ajuste de distribución (los
        # paneles discretos no describen el ajuste hecho).
        if self._distribution_report_active():
            dist_lines = self._distribution_report_lines(short=True)
            if not dist_lines:
                dist_lines = [f"> ⚠️ {_r('no_dist_result')}", ""]
            if iso_ref is not None:
                lines.append(f"_{_r('iso_ref_short')}: **{iso_ref:.6g} mm/s**_")
                lines.append("")
            return lines + dist_lines

        # Métricas de bondad en una sola línea
        if fit_view is not None and fit_view.metrics():
            st = {m.key: m.value for m in fit_view.metrics()}
            bits = []
            if st.get("red_chi2") is not None:
                bits.append(f"χ²ᵣ = {st['red_chi2']:.4g}")
            if st.get("dof") is not None:
                bits.append(f"dof = {int(st['dof'])}")
            if st.get("aic") is not None:
                bits.append(f"AIC = {st['aic']:.4g}")
            if st.get("bic") is not None:
                bits.append(f"BIC = {st['bic']:.4g}")
            if bits:
                lines.append("> " + " · ".join(bits))
                lines.append("")

        # Calibración ISO en una línea
        if iso_ref is not None:
            lines.append(f"_{_r('iso_ref_short')}: **{iso_ref:.6g} mm/s**_")
            lines.append("")

        # ── Parámetros por componente ───────────────────────────────────
        lines.append(f"## {_r('params')}")
        lines.append("")
        for comp_state in active_components:
            kind = comp_state.kind
            kind_disp = tr(f"kind.{kind}", default=kind)
            lines.append(f"**{_r('component_title', idx=comp_state.idx, kind=kind_disp)}**")
            lines.append("")
            used = USED_BY.get(kind, set())
            uses_bhf = "bhf" in used
            uses_quad = "quad" in used
            uses_gamma2 = "gamma2" in used
            uses_gamma3 = "gamma3" in used

            # Tabla compacta: solo parámetros relevantes, valor + σ si disponible
            free_vals: dict[str, tuple[float, float | None]] = {}
            if fit_view is not None:
                for est in fit_view.parameters():
                    free_vals[est.key] = (est.value or 0.0, est.error)

            lines.append(f"| {_r('col_param')} | {_r('col_value')} | σ | {_r('col_state')} |")
            lines.append("|---|---|---|---|")
            for k, v in comp_state.values.items():
                if k not in used:
                    continue
                key = f"s{comp_state.idx}_{k}"
                err = free_vals.get(key, (None, None))[1]
                err_txt = f"± {err:.3g}" if err is not None and err > 0 else "—"
                fixed_txt = _r("fixed") if comp_state.is_fixed(k) else _r("free")
                lines.append(f"| `{key}` | {v:.6g} | {err_txt} | {fixed_txt} |")

            # Magnitudes clave derivadas
            g1 = comp_state.value("gamma1")
            derived_bits = [f"Γ₁ = {g1:.4g} mm/s"]
            if uses_gamma2:
                g2 = g1 * comp_state.value("gamma2", 1.0)
                derived_bits.append(f"Γ₂ = {g2:.4g}")
            if uses_gamma3:
                g3 = g1 * comp_state.value("gamma3", 1.0)
                derived_bits.append(f"Γ₃ = {g3:.4g}")
            if uses_bhf:
                derived_bits.append(f"BHF = {comp_state.value('bhf'):.5g} T")
            if uses_quad:
                derived_bits.append(f"ΔEQ = {comp_state.value('quad'):.5g} mm/s")
            delta = comp_state.value("delta")
            derived_bits.append(f"δ = {delta:.5g} mm/s")
            if iso_ref is not None:
                derived_bits.append(f"δ_corr = {delta - iso_ref:.5g} mm/s")
            lines.append("")
            lines.append("_" + " · ".join(derived_bits) + "_")
            lines.append("")

        # ── Análisis de áreas ───────────────────────────────────────────
        pct_active, areas, percentages = self.component_area_percentages()
        pct_errors = self.component_percentage_errors()
        if pct_active:
            lines.append(f"## {_r('sec_areas_short')}")
            lines.append("")
            lines.append(f"| {_r('col_comp_short')} | {_r('col_type')} | {_r('col_pct_area')} | σ (%) |")
            lines.append("|---|---|---|---|")
            for idx, area, pct in zip(pct_active, areas, percentages):
                cs = self.components_panels[idx - 1].to_view_state()
                kd = tr(f"kind.{cs.kind}", default=cs.kind)
                err = pct_errors.get(idx)
                err_txt = f"± {err:.3g}" if err is not None else "—"
                lines.append(f"| {idx} | {kd} | {pct:.3f}% | {err_txt} |")
            lines.append("")

        return lines

    def _render_short_pdf_report(self, pdf_path: Path) -> None:
        """PDF compacto: todo en la menor cantidad de hojas, sin portada."""
        from datetime import datetime
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib.figure import Figure as _Fig
        from matplotlib.patches import Rectangle

        file_name = self.file.path.name if self.file.path else "—"
        iso_ref = self.calibration_iso_ref()
        fit = self.runtime_results.fit_result
        fit_view = discrete_result_view(fit) if fit is not None else None
        active_components = [
            cp.to_view_state() for cp in self.components_panels
            if cp.to_view_state().enabled
        ]
        free_vals: dict[str, tuple[float, float | None]] = {}
        if fit_view is not None:
            for est in fit_view.parameters():
                free_vals[est.key] = (est.value or 0.0, est.error)
        pct_active, areas, percentages = self.component_area_percentages()
        pct_errors = self.component_percentage_errors()

        # ── Constantes de layout ────────────────────────────────────────
        LEFT, RIGHT = 0.04, 0.96
        W = RIGHT - LEFT
        TOP, BOTTOM = 0.975, 0.02
        ROW_H   = 0.0175   # altura fila de tabla
        LABEL_H = 0.024    # altura de cabecera de componente
        GAP     = 0.005
        FS_HDR  = 7.0
        FS_LBL  = 8.5
        FS_TBL  = 7.2
        FS_DRV  = 7.0
        BLUE    = "#1e40af"
        LBLUE   = "#dbeafe"
        ZEBRA   = "#f5f8ff"
        DARK    = "#1f2937"
        BORDER  = "#d1d5db"

        pages: list[tuple] = []

        def _new_page():
            fig = _Fig(figsize=(8.27, 11.69), dpi=100, facecolor="white")
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            pages.append((fig, ax))
            return ax

        def _draw_table(ax, y, headers, rows, fracs):
            xs = [LEFT]
            for f in fracs[:-1]:
                xs.append(xs[-1] + f * W)
            ws = [f * W for f in fracs]
            # header row
            ax.add_patch(Rectangle((LEFT, y - ROW_H), W, ROW_H,
                                   facecolor=BLUE, edgecolor="none"))
            for i, h in enumerate(headers):
                ax.text(xs[i] + 0.003, y - ROW_H * 0.52, h,
                        color="white", fontsize=FS_TBL, fontweight="bold",
                        va="center", ha="left")
            y -= ROW_H
            for ri, row in enumerate(rows):
                bg = ZEBRA if ri % 2 == 0 else "white"
                ax.add_patch(Rectangle((LEFT, y - ROW_H), W, ROW_H,
                                       facecolor=bg, edgecolor=BORDER, linewidth=0.25))
                for ci, cell in enumerate(row):
                    ax.text(xs[ci] + 0.003, y - ROW_H * 0.52, str(cell),
                            color=DARK, fontsize=FS_TBL, va="center", ha="left")
                y -= ROW_H
            return y - GAP

        ax = _new_page()
        y = TOP

        # ── Cabecera ────────────────────────────────────────────────────
        metrics_parts = []
        dist_mode = self._distribution_report_active()
        dist_result = getattr(self.runtime_results, "distribution_result", None)
        if dist_mode:
            # Los paneles discretos no describen el ajuste de distribución.
            active_components, pct_active = [], []
            if dist_result is not None:
                g = self._distribution_summary(dist_result)["goodness"]
                for k, lbl, fmt in (("red_chi2", "χ²ᵣ", ".4g"), ("dof", "ν", ".4g"),
                                    ("aic", "AIC", ".4g"), ("bic", "BIC", ".4g")):
                    if k in g:
                        metrics_parts.append(f"{lbl}={g[k]:{fmt}}")
        elif fit_view is not None and fit_view.metrics():
            st = {m.key: m.value for m in fit_view.metrics()}
            if st.get("red_chi2") is not None:
                metrics_parts.append(f"χ²ᵣ={st['red_chi2']:.4g}")
            if st.get("dof") is not None:
                metrics_parts.append(f"dof={int(st['dof'])}")
            if st.get("aic") is not None:
                metrics_parts.append(f"AIC={st['aic']:.4g}")
            if st.get("bic") is not None:
                metrics_parts.append(f"BIC={st['bic']:.4g}")
        hdr = f"{file_name}   {datetime.now().strftime('%Y-%m-%d %H:%M')}   {APP_NAME} v{APP_VERSION}"
        if metrics_parts:
            hdr += "     " + "  ·  ".join(metrics_parts)
        if iso_ref is not None:
            hdr += f"     δ_ref={iso_ref:.5g} mm/s"
        HDR_H = 0.022
        ax.add_patch(Rectangle((LEFT, y - HDR_H), W, HDR_H,
                               facecolor=BLUE, edgecolor="none"))
        ax.text(LEFT + 0.006, y - HDR_H * 0.52, hdr,
                color="white", fontsize=FS_HDR, va="center", ha="left")
        y -= HDR_H + GAP * 2

        # ── Ajuste de distribución: los bloques del informe completo ────
        if dist_mode:
            md = self._distribution_report_lines() or [f"> {_r('no_dist_result')}"]
            for kind, data in self._md_to_blocks(md):
                if kind == "h3":
                    if y - (LABEL_H + 3 * ROW_H) < BOTTOM + 0.05:
                        ax = _new_page()
                        y = TOP
                    ax.add_patch(Rectangle((LEFT, y - LABEL_H), W, LABEL_H,
                                           facecolor=LBLUE, edgecolor="none"))
                    ax.text(LEFT + 0.006, y - LABEL_H * 0.52, self._md_strip_inline(data),
                            color=BLUE, fontsize=FS_LBL, fontweight="bold",
                            va="center", ha="left")
                    y -= LABEL_H
                elif kind == "table":
                    header, rows = data
                    header = [self._md_strip_inline(h) for h in header]
                    rows = [[self._md_strip_inline(c).replace("\\|", "|") for c in r]
                            for r in rows]
                    if y - (len(rows) + 1) * ROW_H - GAP < BOTTOM + 0.02:
                        ax = _new_page()
                        y = TOP
                    n = max(len(header), 1)
                    fracs = ([0.45, 0.55] if n == 2 else [1.0 / n] * n)
                    y = _draw_table(ax, y, header, rows, fracs)
                elif kind == "callout":
                    import textwrap
                    partes = [w for ln in data
                              for w in (textwrap.wrap(self._md_strip_inline(ln), 125) or [""])]
                    for ln in partes:
                        if y - 0.016 < BOTTOM + 0.02:
                            ax = _new_page()
                            y = TOP
                        ax.text(LEFT + 0.006, y - 0.002, ln,
                                color="#374151", fontsize=FS_DRV, fontstyle="italic",
                                va="top", ha="left")
                        y -= 0.016
                    y -= GAP

        # ── Componentes activos ─────────────────────────────────────────
        for comp_state in active_components:
            kind = comp_state.kind
            kind_disp = tr(f"kind.{kind}", default=kind)
            used = USED_BY.get(kind, set())
            uses_bhf    = "bhf"    in used
            uses_quad   = "quad"   in used
            uses_gamma2 = "gamma2" in used
            uses_gamma3 = "gamma3" in used

            param_rows = []
            for k, v in comp_state.values.items():
                if k not in used:
                    continue
                key = f"s{comp_state.idx}_{k}"
                err = free_vals.get(key, (None, None))[1]
                err_txt = f"±{err:.3g}" if err is not None and err > 0 else "—"
                param_rows.append([key, f"{v:.6g}", err_txt,
                                   _r("fixed") if comp_state.is_fixed(k) else _r("free")])

            needed = LABEL_H + (len(param_rows) + 1) * ROW_H + 0.018 + GAP * 2
            if y - needed < BOTTOM + 0.05:
                ax = _new_page()
                y = TOP - HDR_H - GAP * 2

            # Etiqueta de componente
            ax.add_patch(Rectangle((LEFT, y - LABEL_H), W, LABEL_H,
                                   facecolor=LBLUE, edgecolor="none"))
            ax.text(LEFT + 0.006, y - LABEL_H * 0.52,
                    _r("component_title", idx=comp_state.idx, kind=kind_disp),
                    color=BLUE, fontsize=FS_LBL, fontweight="bold",
                    va="center", ha="left")
            y -= LABEL_H

            # Tabla de parámetros
            y = _draw_table(ax, y,
                            [_r("col_param"), _r("col_value"), "σ", _r("col_state")],
                            param_rows,
                            [0.38, 0.22, 0.22, 0.18])

            # Línea de magnitudes derivadas
            g1 = comp_state.value("gamma1")
            bits = [f"Γ₁={g1:.4g}"]
            if uses_gamma2:
                bits.append(f"Γ₂={g1 * comp_state.value('gamma2', 1.0):.4g}")
            if uses_gamma3:
                bits.append(f"Γ₃={g1 * comp_state.value('gamma3', 1.0):.4g}")
            if uses_bhf:
                bits.append(f"BHF={comp_state.value('bhf'):.5g} T")
            if uses_quad:
                bits.append(f"ΔEQ={comp_state.value('quad'):.5g} mm/s")
            d = comp_state.value("delta")
            bits.append(f"δ={d:.5g} mm/s")
            if iso_ref is not None:
                bits.append(f"δ_corr={d - iso_ref:.5g} mm/s")
            ax.text(LEFT + 0.006, y - 0.001, "  ".join(bits),
                    color="#374151", fontsize=FS_DRV, fontstyle="italic",
                    va="top", ha="left")
            y -= 0.016 + GAP * 2

        # ── Análisis de áreas ───────────────────────────────────────────
        if pct_active:
            area_rows = []
            for idx, area, pct in zip(pct_active, areas, percentages):
                cs = self.components_panels[idx - 1].to_view_state()
                kd = tr(f"kind.{cs.kind}", default=cs.kind)
                err = pct_errors.get(idx)
                area_rows.append([str(idx), kd, f"{pct:.3f}%",
                                  f"±{err:.3g}" if err is not None else "—"])

            needed = LABEL_H + (len(area_rows) + 1) * ROW_H + GAP
            if y - needed < BOTTOM + 0.05:
                ax = _new_page()
                y = TOP - HDR_H - GAP * 2

            ax.add_patch(Rectangle((LEFT, y - LABEL_H), W, LABEL_H,
                                   facecolor=LBLUE, edgecolor="none"))
            ax.text(LEFT + 0.006, y - LABEL_H * 0.52, _r("areas_title"),
                    color=BLUE, fontsize=FS_LBL, fontweight="bold",
                    va="center", ha="left")
            y -= LABEL_H
            _draw_table(ax, y,
                        [_r("col_comp_short"), _r("col_type"), _r("col_pct_area"), "σ (%)"],
                        area_rows,
                        [0.10, 0.45, 0.25, 0.20])

        # ── Figura al final ─────────────────────────────────────────────
        with PdfPages(pdf_path) as pdf:
            for fig, _ in pages:
                pdf.savefig(fig, bbox_inches="tight")
            pdf.savefig(self.canvas.fig, bbox_inches="tight")
            fig_dist = self._distribution_report_figure()
            if fig_dist is not None:
                pdf.savefig(fig_dist, bbox_inches="tight")
            fig_corr = self._correlation_report_figure()
            if fig_corr is not None:
                pdf.savefig(fig_corr, bbox_inches="tight")

    def _render_odt_report(self, odt_path: Path, md_lines: list[str],
                            fig_png_path: Path | None = None) -> None:
        """Genera un archivo ODT mínimo desde cero (stdlib: zipfile + xml)."""
        import io
        import zipfile
        from xml.sax.saxutils import escape as xe

        MIME = "application/vnd.oasis.opendocument.text"

        NS = {
            "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
            "style":  "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
            "text":   "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
            "table":  "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
            "draw":   "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
            "fo":     "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
            "xlink":  "http://www.w3.org/1999/xlink",
            "dc":     "http://purl.org/dc/elements/1.1/",
            "svg":    "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
            "manifest": "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0",
        }

        def nsp(prefix: str, local: str) -> str:
            return f"{{{NS[prefix]}}}{local}"

        # ── styles.xml ──────────────────────────────────────────────────
        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document-styles'
            ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
            ' xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"'
            ' xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"'
            ' office:version="1.3">'
            '<office:styles>'
            '<style:style style:name="Standard" style:family="paragraph"'
            ' style:class="text"/>'
            '<style:style style:name="Heading1" style:family="paragraph"'
            ' style:parent-style-name="Standard">'
            '<style:text-properties fo:font-size="16pt" fo:font-weight="bold"/>'
            '</style:style>'
            '<style:style style:name="Heading2" style:family="paragraph"'
            ' style:parent-style-name="Standard">'
            '<style:text-properties fo:font-size="13pt" fo:font-weight="bold"/>'
            '</style:style>'
            '<style:style style:name="Bold" style:family="text">'
            '<style:text-properties fo:font-weight="bold"/>'
            '</style:style>'
            '<style:style style:name="Italic" style:family="text">'
            '<style:text-properties fo:font-style="italic"/>'
            '</style:style>'
            '<style:style style:name="Code" style:family="text">'
            '<style:text-properties style:font-name="Courier New" fo:font-size="9pt"/>'
            '</style:style>'
            '<style:style style:name="TableHeader" style:family="table-cell">'
            '<style:text-properties fo:font-weight="bold" fo:background-color="#dbeafe"/>'
            '</style:style>'
            '</office:styles>'
            '</office:document-styles>'
        )

        # ── Convertir líneas MD a bloques ───────────────────────────────
        import re as _re

        def _strip_inline(s: str) -> str:
            s = _re.sub(r"\*\*(.+?)\*\*", r"\1", s)
            s = _re.sub(r"\*(.+?)\*", r"\1", s)
            s = _re.sub(r"`([^`]+)`", r"\1", s)
            s = _re.sub(r"[\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF\U00002600-\U000027BF]\\s?", "", s)
            return s.strip()

        # Parsear bloques: ('h1'|'h2'|'h3'|'para'|'table'|'callout'), data
        blocks: list[tuple[str, object]] = []
        i, n = 0, len(md_lines)
        while i < n:
            raw = md_lines[i]
            s = raw.strip()
            if not s:
                i += 1
                continue
            if s.startswith("# ") and not s.startswith("## "):
                blocks.append(("h1", s[2:].strip()))
                i += 1
            elif s.startswith("## ") and not s.startswith("### "):
                blocks.append(("h2", s[3:].strip()))
                i += 1
            elif s.startswith("### "):
                blocks.append(("h3", s[4:].strip()))
                i += 1
            elif s.startswith(">"):
                buf = []
                while i < n and md_lines[i].strip().startswith(">"):
                    buf.append(md_lines[i].strip().lstrip(">").strip())
                    i += 1
                blocks.append(("callout", " ".join(buf)))
            elif s.startswith("_") and s.endswith("_") and "\n" not in s:
                blocks.append(("italic_para", s[1:-1]))
                i += 1
            elif s.startswith("|") and s.endswith("|"):
                rows = []
                while i < n and md_lines[i].strip().startswith("|") and md_lines[i].strip().endswith("|"):
                    rows.append(md_lines[i].strip())
                    i += 1
                if len(rows) >= 2 and set(rows[1].replace("|","").replace("-","").replace(":","").strip()) == set():
                    hdr = [c.strip() for c in rows[0].strip("|").split("|")]
                    data = [[c.strip() for c in r.strip("|").split("|")] for r in rows[2:]]
                    blocks.append(("table", (hdr, data)))
                else:
                    for r in rows:
                        blocks.append(("para", r))
            else:
                blocks.append(("para", s))
                i += 1

        # ── Construire content.xml usando strings ────────────────────────
        import xml.etree.ElementTree as ET

        def _p(parent, text: str, style: str = "Standard") -> ET.Element:
            el = ET.SubElement(parent, nsp("text", "p"))
            el.set(nsp("text", "style-name"), style)
            el.text = _strip_inline(text)
            return el

        def _p_bold(parent, text: str) -> ET.Element:
            el = ET.SubElement(parent, nsp("text", "p"))
            el.set(nsp("text", "style-name"), "Standard")
            span = ET.SubElement(el, nsp("text", "span"))
            span.set(nsp("text", "style-name"), "Bold")
            span.text = _strip_inline(text)
            return el

        def _p_italic(parent, text: str) -> ET.Element:
            el = ET.SubElement(parent, nsp("text", "p"))
            el.set(nsp("text", "style-name"), "Standard")
            span = ET.SubElement(el, nsp("text", "span"))
            span.set(nsp("text", "style-name"), "Italic")
            span.text = _strip_inline(text)
            return el

        def _table(parent, hdr: list[str], rows: list[list[str]]) -> None:
            tbl = ET.SubElement(parent, nsp("table", "table"))
            n_cols = len(hdr)
            for _ in range(n_cols):
                ET.SubElement(tbl, nsp("table", "table-column"))
            # Header row
            hrow = ET.SubElement(tbl, nsp("table", "table-row"))
            for h in hdr:
                tc = ET.SubElement(hrow, nsp("table", "table-cell"))
                p = ET.SubElement(tc, nsp("text", "p"))
                span = ET.SubElement(p, nsp("text", "span"))
                span.set(nsp("text", "style-name"), "Bold")
                span.text = _strip_inline(h)
            # Data rows
            for row in rows:
                drow = ET.SubElement(tbl, nsp("table", "table-row"))
                for c in range(n_cols):
                    tc = ET.SubElement(drow, nsp("table", "table-cell"))
                    p = ET.SubElement(tc, nsp("text", "p"))
                    p.text = _strip_inline(row[c] if c < len(row) else "")

        # Root element
        doc_el = ET.Element(nsp("office", "document-content"))
        for prefix, uri in NS.items():
            if prefix != "manifest":
                doc_el.set(f"xmlns:{prefix}", uri)
        doc_el.set(nsp("office", "version"), "1.3")
        auto_styles = ET.SubElement(doc_el, nsp("office", "automatic-styles"))
        body = ET.SubElement(doc_el, nsp("office", "body"))
        text_el = ET.SubElement(body, nsp("office", "text"))

        for kind, data in blocks:
            if kind == "h1":
                _p(text_el, data, "Heading1")
            elif kind == "h2":
                _p(text_el, data, "Heading2")
            elif kind == "h3":
                _p_bold(text_el, data)
            elif kind in ("para", "callout"):
                _p(text_el, data)
            elif kind == "italic_para":
                _p_italic(text_el, data)
            elif kind == "table":
                hdr, rows = data
                _table(text_el, hdr, rows)
                ET.SubElement(text_el, nsp("text", "p"))  # espacio tras tabla

        # Figura embebida si existe
        if fig_png_path is not None and fig_png_path.exists():
            ET.SubElement(text_el, nsp("text", "p"))
            frame = ET.SubElement(text_el, nsp("draw", "frame"))
            frame.set(nsp("draw", "name"), "figura")
            frame.set(nsp("text", "anchor-type"), "paragraph")
            frame.set(nsp("svg", "width"), "17cm")
            frame.set(nsp("svg", "height"), "11cm")
            img = ET.SubElement(frame, nsp("draw", "image"))
            img.set(nsp("xlink", "href"), f"Pictures/{fig_png_path.name}")
            img.set(nsp("xlink", "type"), "simple")
            img.set(nsp("xlink", "show"), "embed")
            img.set(nsp("xlink", "actuate"), "onLoad")

        content_io = io.BytesIO()
        ET.ElementTree(doc_el).write(content_io, encoding="UTF-8", xml_declaration=True)
        content_bytes = content_io.getvalue()

        # ── manifest.xml ────────────────────────────────────────────────
        manifest_entries = [
            ('/', MIME),
            ('/content.xml', 'text/xml'),
            ('/styles.xml', 'text/xml'),
        ]
        if fig_png_path is not None and fig_png_path.exists():
            manifest_entries.append((f'/Pictures/{fig_png_path.name}', 'image/png'))

        mf_root = ET.Element(nsp("manifest", "manifest"))
        mf_root.set("xmlns:manifest", NS["manifest"])
        mf_root.set(nsp("manifest", "version"), "1.3")
        for full_path, media_type in manifest_entries:
            fe = ET.SubElement(mf_root, nsp("manifest", "file-entry"))
            fe.set(nsp("manifest", "full-path"), full_path)
            fe.set(nsp("manifest", "media-type"), media_type)
        mf_io = io.BytesIO()
        ET.ElementTree(mf_root).write(mf_io, encoding="UTF-8", xml_declaration=True)

        # ── Empaquetar ZIP ───────────────────────────────────────────────
        with zipfile.ZipFile(odt_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # mimetype sin comprimir y como primer entry (requerimiento ODT)
            zf.writestr(zipfile.ZipInfo("mimetype"), MIME)
            zf.writestr("META-INF/manifest.xml", mf_io.getvalue())
            zf.writestr("styles.xml", styles_xml.encode("utf-8"))
            zf.writestr("content.xml", content_bytes)
            if fig_png_path is not None and fig_png_path.exists():
                zf.write(fig_png_path, f"Pictures/{fig_png_path.name}")

    def on_export_short_report(self) -> None:
        """Exporta el informe reducido (.md) y opcionalmente .pdf."""
        if self.file.path is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("file.export_short_report"),
            str(ROOT / (self.file.path.stem + "_" + _r("short_suffix"))),
            "Markdown (*.md);;All (*.*)")
        if not path:
            return
        state = self._build_state()
        if state is None:
            return
        lines = self._build_short_report_lines()
        md_path = Path(path)
        try:
            md_path.write_text("\n".join(lines), encoding="utf-8")
            self.statusBar().showMessage(_r("short_saved", path=path), 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("file.export_short_report"),
                f"{type(exc).__name__}: {exc}")
            return

        want_pdf = QtWidgets.QMessageBox.question(
            self, tr("file.export_short_report"),
            tr("msg.short_report_ask_pdf",
               default="Informe Markdown guardado. ¿Generar también un PDF?"),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes)
        if want_pdf != QtWidgets.QMessageBox.Yes:
            return
        try:
            pdf_path = md_path.with_suffix(".pdf")
            self._render_short_pdf_report(pdf_path)
            self.statusBar().showMessage(
                _r("short_saved_pdf", name=md_path.stem), 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, tr("file.export_short_report"),
                _r("pdf_failed", error=f"{type(exc).__name__}: {exc}"))
