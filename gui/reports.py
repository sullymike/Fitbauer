"""Generación y exportación de informes desde la GUI Qt."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.constants import APP_NAME, APP_VERSION
from core.params import USED_BY
from core.result_views import discrete_result_view

ROOT = Path(__file__).resolve().parents[1]


class ReportMixin:
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
        lines.append("# 📊 Mössbauer Fe-57 — Informe de ajuste")
        lines.append("")
        lines.append(
            f"**Fichero:** `{file_name}` · **Fecha:** "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')} · **Programa:** "
            f"{APP_NAME} v{APP_VERSION} (Qt)"
        )
        lines.append("")

        if fit_view is not None and fit_view.metrics():
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
            lines.append("> ### 🎯 Resumen del ajuste")
            lines.append("> " + " · ".join(bits))
            lines.append(
                f"> {len(fit_view.free_keys())} parámetros libres · "
                f"σ: {self.runtime_results.error_source}"
            )
            lines.append("")

        # ── Espectro y plegado ──────────────────────────────────────────
        lines.append("## 📁 Espectro y plegado")
        lines.append("")
        lines.append("| Campo | Valor |")
        lines.append("|---|---|")
        lines.append(f"| Fichero | `{file_name}` |")
        n_chan = self.file.counts.size if self.file.counts is not None else 0
        lines.append(f"| Canales leídos | {n_chan} |")
        center_val = float(calib_state.center)
        lines.append(f"| Folding point centro | {center_val:.5f} |")
        lines.append(f"| Folding point Normos (≈ 2·centro) | {2.0 * center_val:.5f} |")
        if self.file.folded is not None:
            lines.append(f"| Pares doblados | {int(self.file.folded.size)} |")
        norm_factor = getattr(self.file, "norm_factor", None)
        if norm_factor is not None:
            lines.append(f"| Normalización | / {norm_factor:.6g} |")
        lines.append(f"| Perfil de línea | {calib_state.line_profile} |")
        lines.append("")

        # ── Calibración ──────────────────────────────────────────────────
        lines.append("## 🎛️ Calibración y escala de velocidades")
        lines.append("")
        lines.append("| Campo | Valor |")
        lines.append("|---|---|")
        lines.append(f"| Vmax | {calib_state.vmax:.6g} mm/s |")
        lines.append(f"| Línea base | {calib_state.baseline:.6g} |")
        lines.append(f"| Pendiente del fondo | {calib_state.slope:.6g} |")
        lines.append(f"| Ajustar Vmax con el patrón | "
                     f"{'sí' if calib_state.fit_velocity else 'no'} |")
        if ci:
            sample = ci.get("calibration_sample") or ci.get("calibration_file_name") or "—"
            lines.append(f"| Origen calibración | {ci.get('source', '?')} |")
            lines.append(f"| Muestra | {sample} |")
            if ci.get("calibration_file_name"):
                lines.append(f"| Fichero calibración | `{ci['calibration_file_name']}` |")
            if ci.get("velocity_calibrated") is not None:
                lines.append(
                    f"| Vmax calibrada | {float(ci['velocity_calibrated']):.6g} mm/s |"
                )
            if iso_ref is not None:
                lines.append(f"| δ de referencia (iso_ref) | {iso_ref:.6g} mm/s |")
            if ci.get("calibration_date"):
                lines.append(f"| Fecha calibración | {ci['calibration_date']} |")
        cal_unc = self.calibration_uncertainty_text()
        if cal_unc:
            lines.append("")
            lines.append(f"> ℹ️ {cal_unc}")
        elif not ci:
            lines.append("")
            lines.append("> ⚠️ Sin calibración activa; los δ no están corregidos.")
        lines.append("")

        # ── Bondad y diagnóstico del ajuste ──────────────────────────────
        stats = ({metric.key: metric.value for metric in fit_view.metrics()} if fit_view is not None else {}) or {}
        rms = self._info_rms()
        if stats or not (rms != rms):  # rms != rms ⇒ NaN
            lines.append("## 📐 Bondad y diagnóstico")
            lines.append("")
            lines.append("| Indicador | Valor |")
            lines.append("|---|---|")
            if stats.get("chi2") is not None:
                lines.append(f"| χ² | {stats['chi2']:.6g} |")
            if stats.get("red_chi2") is not None:
                lines.append(f"| χ² reducido | {stats['red_chi2']:.6g} |")
            if stats.get("dof") is not None:
                lines.append(f"| dof | {int(stats['dof'])} |")
            if stats.get("aic") is not None:
                lines.append(f"| AIC | {stats['aic']:.6g} |")
            if stats.get("bic") is not None:
                lines.append(f"| BIC | {stats['bic']:.6g} |")
            if stats.get("n_params") is not None:
                lines.append(f"| Nº parámetros del modelo | {int(stats['n_params'])} |")
            if rms == rms:  # not NaN
                lines.append(f"| RMS del ajuste | {rms:.6g} |")
            if fit_view is not None:
                lines.append(f"| Autoarranques probados | {int(fit_view.n_starts())} |")
            lines.append("")
            # Diagnóstico residual
            if any(k in stats for k in ("resid_lag1", "resid_runs_z", "resid_antisym_corr")):
                lines.append("**Diagnóstico del residuo**")
                lines.append("")
                lines.append("| Estadístico | Valor | Umbral de aviso |")
                lines.append("|---|---|---|")
                lines.append(f"| Autocorrelación lag-1 | {stats.get('resid_lag1', float('nan')):.3f} | \\|·\\| > 0.35 |")
                lines.append(f"| Runs test (z) | {stats.get('resid_runs_z', float('nan')):.3f} | \\|·\\| > 2.0 |")
                lines.append(f"| Correlación antisimétrica | {stats.get('resid_antisym_corr', float('nan')):.3f} | > 0.45 |")
                lines.append("")
                if (abs(stats.get("resid_lag1", 0.0)) > 0.35
                        or abs(stats.get("resid_runs_z", 0.0)) > 2.0
                        or stats.get("resid_antisym_corr", 0.0) > 0.45):
                    lines.append("> ⚠️ El residuo parece tener estructura no aleatoria. "
                                 "Revisa modelo, *folding point*, calibración Vmax o si "
                                 "faltan componentes.")
                    lines.append("")
            # Correlaciones
            corr = fit_view.correlations() if fit_view is not None else {}
            max_pair = corr.get("max_pair") or []
            max_abs = corr.get("max_abs_corr")
            if max_pair and max_abs is not None:
                lines.append(
                    f"_Correlación máxima:_ `{max_pair[0]}` ↔ `{max_pair[1]}` con "
                    f"|r| = **{float(max_abs):.3f}**."
                )
                lines.append("")
            high = corr.get("high_pairs") or []
            if high:
                lines.append("**⚠️ Parámetros muy correlacionados (|r| ≥ 0.95)**")
                lines.append("")
                lines.append("| Par | r |")
                lines.append("|---|---|")
                for hp in high:
                    lines.append(f"| `{hp['param1']}` ↔ `{hp['param2']}` | {hp['corr']:.3f} |")
                lines.append("")

        # ── Análisis de áreas ───────────────────────────────────────────
        pct_active, areas, percentages = self.component_area_percentages()
        pct_errors = self.component_percentage_errors()
        if pct_active:
            lines.append("## 🥧 Análisis de áreas por componente")
            lines.append("")
            lines.append("| Componente | Tipo | % área | σ (%) | Área absoluta |")
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
        lines.append("## 🧪 Componentes")
        lines.append("")
        for comp_state in active_components:
            kind = comp_state.kind
            kind_disp = tr(f"kind.{kind}", default=kind)
            lines.append(f"### 🔹 Componente {comp_state.idx} — {kind_disp}")
            lines.append("")
            used = USED_BY.get(kind, set())
            uses_gamma2 = "gamma2" in used
            uses_gamma3 = "gamma3" in used
            uses_bhf = "bhf" in used
            uses_quad = "quad" in used
            uses_int1 = "int1" in used  # True for magnetic/relaxation kinds
            lines.append("**Parámetros**")
            lines.append("")
            lines.append("| Parámetro | Valor | Estado |")
            lines.append("|---|---|---|")
            for k, value in comp_state.values.items():
                if k not in used:
                    continue
                state_lbl = "🔒 fijo" if comp_state.is_fixed(k) else "🔓 libre"
                lines.append(f"| `s{comp_state.idx}_{k}` | {value:.6g} | {state_lbl} |")
            lines.append("")
            # Magnitudes físicas derivadas: anchuras reales e intensidades absolutas
            g1 = comp_state.value("gamma1")
            lines.append("**Magnitudes físicas derivadas**")
            lines.append("")
            lines.append("| Magnitud | Valor |")
            lines.append("|---|---|")
            if uses_gamma2 and uses_gamma3:
                g2 = g1 * comp_state.value("gamma2", 1.0)
                g3 = g1 * comp_state.value("gamma3", 1.0)
                lines.append(f"| Γ FWHM reales 1 / 2 / 3 (mm/s) | {g1:.4g} / {g2:.4g} / {g3:.4g} |")
                lines.append(f"| Γ relativas 2 / 3 | {comp_state.value('gamma2', 1.0):.4g} / {comp_state.value('gamma3', 1.0):.4g} |")
            elif uses_gamma2:
                g2 = g1 * comp_state.value("gamma2", 1.0)
                lines.append(f"| Γ FWHM reales 1 / 2 (mm/s) | {g1:.4g} / {g2:.4g} |")
                lines.append(f"| Γ relativa 2 | {comp_state.value('gamma2', 1.0):.4g} |")
            else:
                lines.append(f"| Γ FWHM (mm/s) | {g1:.4g} |")
            lines.append(f"| Profundidad | {comp_state.value('depth'):.6g} |")
            if uses_bhf:
                lines.append(f"| BHF | {comp_state.value('bhf'):.6g} T |")
            lines.append(f"| δ (sin corregir) | {comp_state.value('delta'):.6g} mm/s |")
            if uses_quad:
                lines.append(f"| ΔEQ | {comp_state.value('quad'):.6g} mm/s |")
            if iso_ref is not None:
                lines.append(
                    f"| **δ corregido** (iso_ref = {iso_ref:.6g}) | "
                    f"**{comp_state.value('delta') - iso_ref:.6g} mm/s** |"
                )
            if uses_int1:
                i3_real = comp_state.value("int3", 1.0)
                i2_real = i3_real * comp_state.value("int2", 1.0)
                i1_real = i3_real * comp_state.value("int1", 1.0)
                lines.append(f"| Intensidades reales I₁ / I₂ / I₃ | {i1_real:.4g} / {i2_real:.4g} / {i3_real:.4g} |")
            lines.append("")
            # Textura derivada: solo para Sextete
            if kind == "Sextete":
                derived = self.texture_derived(comp_state)
                if derived is not None:
                    lines.append("**🧭 Magnitudes derivadas de la textura (t = sin²θ)**")
                    lines.append("")
                    lines.append("| Magnitud | Valor | σ |")
                    lines.append("|---|---|---|")
                    lines.append(f"| t (parámetro de textura) | {derived['t']:.4g} | {_ferr(derived['sigma_t'])} |")
                    lines.append(f"| θ (ángulo respecto a γ) | {derived['theta_deg']:.4g}° | {_ferr(derived['sigma_theta_deg'])} |")
                    lines.append(f"| R₂₃ = I₂/I₃ | {derived['r23']:.4g} | {_ferr(derived['sigma_r23'])} |")
                    lines.append(f"| S = ⟨P₂(cos θ)⟩ | {derived['s']:.4g} | {_ferr(derived['sigma_s'])} |")
                    lines.append("")
                    lines.append("> 💡 **Interpretación:** *t = sin²θ* parametriza la razón de "
                                 "intensidades I₂/I₃ del sextete: t = 0 ⇒ campo paralelo al rayo γ "
                                 "(I₂ = 0), t = 2/3 ⇒ muestra random (θ ≈ 54.7°, R₂₃ = 2), "
                                 "t = 1 ⇒ campo perpendicular (R₂₃ = 4). *S* es un parámetro de "
                                 "orden tipo Hermans: **+1** alineado al γ, **0** isótropo, "
                                 "**−½** perpendicular.")
                    lines.append("")

        # ── δ corregidos por calibración (resumen) ──────────────────────
        if iso_ref is not None and active_components:
            lines.append("## 🎯 δ corregidos por calibración")
            lines.append("")
            lines.append(f"_Referencia isomérica de la calibración:_ **{iso_ref:.6g} mm/s**.")
            lines.append("")
            lines.append("| Componente | Tipo | δ ajustado (mm/s) | δ corregido (mm/s) |")
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
            lines.append("## 📈 Parámetros del ajuste (libres)")
            lines.append("")
            lines.append(f"_Fuente de σ:_ {self.runtime_results.error_source}")
            lines.append("")
            lines.append("| Parámetro | Valor | σ |")
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
            lines.append("## 🔒 Parámetros fijados")
            lines.append("")
            lines.append(", ".join(f"`{k}`" for k in fixed))
            lines.append("")
        if self.constraints:
            lines.append("## 🔗 Restricciones entre parámetros")
            lines.append("")
            lines.append("| Destino | Fórmula |")
            lines.append("|---|---|")
            for c in self.constraints:
                lines.append(
                    f"| `{c['target']}` | "
                    f"{c.get('factor', 1.0):g} · `{c['source']}` + "
                    f"{c.get('offset', 0.0):g} |"
                )
            lines.append("")

        # ── Glosario ─────────────────────────────────────────────────────
        lines.append("## 📖 Glosario de parámetros")
        lines.append("")
        lines.append("| Símbolo | Magnitud | Unidad | Observación |")
        lines.append("|---|---|---|---|")
        lines.append("| δ | Desplazamiento isomérico | mm/s | Densidad de carga electrónica en el núcleo; referido a α-Fe. |")
        lines.append("| ΔEQ (`quad`) | Desdoblamiento cuadrupolar | mm/s | Asimetría del gradiente de campo eléctrico en el núcleo. |")
        lines.append("| BHF | Campo hiperfino magnético | T | Magnetismo local sentido por el núcleo. |")
        lines.append("| Γ (FWHM) | Anchura de línea | mm/s | Anchura total a media altura del perfil de línea. |")
        lines.append("| `depth` | Profundidad de absorción | (rel.) | Amplitud relativa del componente; ligada al efecto Mössbauer y al espesor. |")
        lines.append("| `int1/2/3` | Intensidades relativas | (rel.) | Razones nominales 3 : I₂ : 1 para un sextete. |")
        lines.append("| `texture` (t) | Parámetro de textura | (0–1) | t = sin²θ con θ = ángulo del campo respecto al γ; controla I₂/I₃. |")
        lines.append("| `beta` (β) | Ángulo EFG–BHF | ° | Solo en tratamiento Kündig fijo del cuadrupolo. |")
        lines.append("| `voigt_sigma` | σ gaussiana del perfil Voigt | mm/s | Anchura instrumental gaussiana convolucionada. |")
        lines.append("| `sat_scale` | Factor de saturación | (rel.) | Solo en modelo de absorbente grueso. |")
        lines.append("| `baseline` / `slope` | Línea base | (rel.) | Nivel y pendiente del fondo de transmisión. |")
        lines.append("| Vmax (`vmax`) | Velocidad máxima | mm/s | Calibración de la escala de velocidades. |")
        lines.append("")

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
            head = f"{title} (cont.)" if continuation else title
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
            ax.text(0.5, 0.82, "Informe de ajuste", color=ACCENT,
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
                    boxes.append(("χ² reducido", f"{st['red_chi2']:.4g}"))
                if st.get("chi2") is not None and st.get("dof") is not None:
                    boxes.append(("χ² · dof", f"{st['chi2']:.4g} · {int(st['dof'])}"))
                if st.get("aic") is not None:
                    boxes.append(("AIC", f"{st['aic']:.4g}"))
                if st.get("bic") is not None:
                    boxes.append(("BIC", f"{st['bic']:.4g}"))
            n_active = sum(1 for cp in self.components_panels if cp.to_view_state().enabled)
            boxes.append(("Componentes activos", str(n_active)))
            if fit_view is not None:
                boxes.append(("Parámetros libres", str(len(fit_view.free_keys()))))
                boxes.append(("Fuente σ", str(self.runtime_results.error_source)))

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
            fig2d = getattr(self, "_dist_map_2d_fig", None)
            if fig2d is not None:
                try:
                    pdf.savefig(fig2d, bbox_inches="tight")
                except Exception:
                    pass

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
            self.statusBar().showMessage(f"Informe guardado: {path}", 5000)
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
            self.statusBar().showMessage(f"Informe + PDF guardados: {path}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, tr("file.export_report"),
                f"No se pudo generar el PDF: {type(exc).__name__}: {exc}")

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
            lines.append(f"_Referencia isomérica: **{iso_ref:.6g} mm/s**_")
            lines.append("")

        # ── Parámetros por componente ───────────────────────────────────
        lines.append("## Parámetros")
        lines.append("")
        for comp_state in active_components:
            kind = comp_state.kind
            kind_disp = tr(f"kind.{kind}", default=kind)
            lines.append(f"**Componente {comp_state.idx} — {kind_disp}**")
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

            lines.append("| Parámetro | Valor | σ | Estado |")
            lines.append("|---|---|---|---|")
            for k, v in comp_state.values.items():
                if k not in used:
                    continue
                key = f"s{comp_state.idx}_{k}"
                err = free_vals.get(key, (None, None))[1]
                err_txt = f"± {err:.3g}" if err is not None and err > 0 else "—"
                fixed_txt = "fijo" if comp_state.is_fixed(k) else "libre"
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
            lines.append("## Áreas")
            lines.append("")
            lines.append("| Comp. | Tipo | % área | σ (%) |")
            lines.append("|---|---|---|---|")
            for idx, area, pct in zip(pct_active, areas, percentages):
                cs = self.components_panels[idx - 1].to_view_state()
                kd = tr(f"kind.{cs.kind}", default=cs.kind)
                err = pct_errors.get(idx)
                err_txt = f"± {err:.3g}" if err is not None else "—"
                lines.append(f"| {idx} | {kd} | {pct:.3f}% | {err_txt} |")
            lines.append("")

        return lines

    def _render_short_pdf_report(self, pdf_path: Path, md_lines: list[str]) -> None:
        """PDF del informe reducido reutilizando el renderer existente."""
        self._render_pdf_report(pdf_path, md_lines)

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
            str(ROOT / (self.file.path.stem + "_resumen")),
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
            self.statusBar().showMessage(f"Informe reducido guardado: {path}", 5000)
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
            self._render_short_pdf_report(pdf_path, lines)
            self.statusBar().showMessage(
                f"Informe reducido (.md + .pdf) guardado: {md_path.stem}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, tr("file.export_short_report"),
                f"No se pudo generar el PDF: {type(exc).__name__}: {exc}")
