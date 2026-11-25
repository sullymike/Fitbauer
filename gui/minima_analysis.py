"""Detección de mínimos e inicialización automática del modelo (GUI).

La detección vive en :mod:`core.component_detection`; aquí solo se aplica la
propuesta a los paneles.
"""
from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtWidgets

from mossbauer_i18n import tr
from core import component_detection as _cd
from core.fit_engine import Component, model_from_values
from gui.panels import ComponentPanel


def reload_param_specs() -> None:
    """Relee los límites de inicialización y detección (diálogo de límites)."""
    _cd.reload_param_specs()


class MinimaAnalysisMixin:
    # ── Auto-inicialización desde mínimos ───────────────────────────────
    def detect_absorption_minima(self, y_override=None) -> tuple[list[dict[str, float]], float, float]:
        """Mínimos del espectro cargado (o de ``y_override`` sobre su eje);
        ver :func:`core.component_detection.detect_minima`."""
        y = self.file.y_data if y_override is None else y_override
        return _cd.detect_minima(self.file.velocity, y)

    def _components_from_peaks(self, peaks: list[dict], baseline: float, slope: float,
                               multiplicities: dict[int, int] | None = None):
        """Ver :func:`core.component_detection.components_from_peaks`."""
        return _cd.components_from_peaks(peaks, baseline, slope, multiplicities)

    def _rescale_minima_depths(self, params: dict[str, float], component_indices: tuple[int, ...]) -> None:
        if self.file.velocity is None or self.file.y_data is None:
            return
        v = self.file.velocity
        baseline = float(params.get("baseline", self.calib.baseline.value()))
        slope = float(params.get("slope", self.calib.slope.value()))
        comps = []
        depth_keys = []
        for idx in component_indices:
            cp = self.components_panels[idx - 1]
            p = f"s{idx}_"
            vals = {name: params.get(p + name, cp.params[name].value()) for name in cp.params}
            params.update({p + name: float(vals[name]) for name in vals})
            comps.append(Component(idx=idx, enabled=True, kind=cp.kind,
                                   intensity_mode=cp.intensity_mode,
                                   quad_treatment=cp.quad_treatment))
            depth_keys.append(p + "depth")
        if not comps:
            return
        baseline_line = baseline + slope * v
        values = {**params, "baseline": baseline, "slope": slope}
        try:
            model = model_from_values(v, values, comps, self.constraints,
                                      absorber_model=self.absorber_model)
        except Exception:
            return
        model_abs = float(np.max(baseline_line - model)) if v.size else 0.0
        data_abs = float(np.max(baseline_line - self.file.y_data)) if v.size else 0.0
        if model_abs > 1e-6 and data_abs > 0.0 and model_abs > data_abs:
            factor = data_abs / model_abs
            for key in depth_keys:
                if key in params:
                    params[key] = float(params[key] * factor)

    def on_init_from_minima(self, show_message: bool = True,
                            peaks_override: list[dict] | None = None,
                            multiplicities: dict[int, int] | None = None) -> bool:
        """Detecta mínimos y configura componentes discretas como en Tk.

        Con ``peaks_override`` se usan los mínimos ya curados por el usuario en
        el editor semi-manual (en vez de la detección automática), y
        ``multiplicities`` indica cuántas contribuciones tiene cada mínimo
        (``{índice_canal: nº}``) para añadir componentes solapadas extra.
        """
        if self.file.velocity is None or self.file.y_data is None:
            return False
        if peaks_override is not None:
            peaks = list(peaks_override)
            _, baseline, slope = self.detect_absorption_minima()
        else:
            peaks, baseline, slope = self.detect_absorption_minima()
        if not peaks:
            if show_message:
                QtWidgets.QMessageBox.information(
                    self, tr("fit.init_from_minima"),
                    tr("msg.auto_minima_none", default="No se detectaron mínimos de absorción."))
            return False

        self.mode_combo.setCurrentIndex(0)
        components, params = self._components_from_peaks(peaks, baseline, slope, multiplicities)
        # Propuestas evaluadas (core.component_detection.evaluate_detection):
        # varias interpretaciones de los mismos mínimos, ajustadas en local y
        # comparadas por BIC, más la revisión del residuo. Con contribuciones
        # marcadas a mano en el editor manda lo que dijo el usuario.
        self._last_detection_report = None
        if not multiplicities:
            report = self._evaluate_detection(peaks, baseline, slope)
            if report is not None:
                self._last_detection_report = report
                components = list(report.final.components)
                params.update(_cd._start_params(report.final))

        active_count = max(1, max((idx for idx, _kind, _g in components), default=1))
        self._building = True
        try:
            self._sync_component_count(active_count)
            for cp in self.components_panels:
                match = next(((kind, group) for idx, kind, group in components if idx == cp.idx), None)
                cp.enabled.setChecked(match is not None)
                cp.type_combo.setCurrentText(match[0] if match is not None else "Sextete")
                cp.apply_values(params)
                if match is not None:
                    used = ComponentPanel._USED_BY.get(cp.to_view_state().kind, set())
                    for name in used:
                        cp.params[name].set_fixed(False)
            self.calib.baseline.set_value(params["baseline"])
            self.calib.slope.set_value(params["slope"])
            self.calib.baseline.set_fixed(False)
            self.calib.slope.set_fixed(False)
            self._rescale_minima_depths(params, tuple(idx for idx, _kind, _g in components))
            for cp in self.components_panels:
                cp.apply_values(params)
        finally:
            self._building = False

        # Igual que en Tk: tras inicializar desde mínimos se dibuja ya la
        # simulación propuesta (habilita el trazado del modelo).
        # Lo que se decidió, para contarlo (modo guiado) y marcarlo en la
        # gráfica: mínimos de cada componente y los que no se usaron.
        usados = {int(pk["i"]) for _i, _k, g in components for pk in g}
        self._last_detection = {
            "n_peaks": len(peaks),
            "components": [
                {"idx": idx, "kind": kind, "positions": [float(pk["pos"]) for pk in g],
                 "delta": params.get(f"s{idx}_delta"), "quad": params.get(f"s{idx}_quad"),
                 "bhf": params.get(f"s{idx}_bhf")}
                for idx, kind, g in components],
            "unused": [float(pk["pos"]) for pk in peaks if int(pk["i"]) not in usados],
        }
        self._detection_fresh = True
        self._simulate_enabled = True
        self._refresh_plot()
        summary = ", ".join(
            tr("text.component_kind_label", idx=idx, kind=tr(f"kind.{kind}", default=kind))
            for idx, kind, _g in components
        )
        msg = tr("msg.auto_minima_detected", n=len(peaks), summary=summary)
        self.statusBar().showMessage(f"{tr('msg.auto_minima_title')}: {summary}", 5000)
        if show_message:
            if self._last_detection_report is not None:
                self._show_detection_report(self._last_detection_report)
            else:
                QtWidgets.QMessageBox.information(self, tr("msg.auto_minima_title"), msg)
            # Tras inicializar, ofrecer identificar fases y, si se desea, sembrar
            # el ajuste con sus valores de referencia.
            if hasattr(self, "_suggest_phases_after_init"):
                try:
                    self._suggest_phases_after_init()
                except Exception:
                    pass
        return True

    def _evaluate_detection(self, peaks, baseline, slope):
        """Evalúa las propuestas con la σ, las cotas y las opciones de la
        ventana; enseña el avance en la barra de estado."""
        state = self._build_state()
        if state is None:
            return None

        def avance(hechas: int, total: int) -> None:
            self.statusBar().showMessage(
                tr("detect.progress", done=hechas, total=total))
            QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            return _cd.evaluate_detection(state, peaks, baseline, slope, progress=avance)
        except Exception:                                   # noqa: BLE001
            return None
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def _show_detection_report(self, report) -> None:
        """Ventana no modal con las propuestas evaluadas y lo que se hizo
        después (se puede mirar el gráfico mientras está abierta)."""
        dlg = getattr(self, "_detection_dialog", None)
        if dlg is None:
            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle(tr("detect.title"))
            dlg.resize(820, 460)
            lay = QtWidgets.QVBoxLayout(dlg)
            dlg.view = QtWidgets.QTextBrowser()
            lay.addWidget(dlg.view)
            bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
            bb.rejected.connect(dlg.close)
            lay.addWidget(bb)
            self._detection_dialog = dlg
        dlg.view.setHtml(detection_report_html(report))
        dlg.show()
        dlg.raise_()


# ── Texto del informe de detección (también lo usa el modo guiado) ───────────
def _kind(k: str) -> str:
    return tr(f"kind.{k}", default=k)


def origin_text(origin) -> str:
    key, data = origin
    data = dict(data)
    if "kind" in data:
        data["kind"] = _kind(data["kind"])
    return tr(key, **data)


def proposal_components_text(prop) -> str:
    """«Doblete δ 0.26 Δ 2.46 · Sextete δ 0.09 B 47.1» con los valores
    ajustados (o los de partida si no se ajustó)."""
    vals = prop.values or prop.params
    out = []
    for idx, kind, _g in prop.components:
        p = f"s{idx}_"
        t = f"{_kind(kind)} δ {vals.get(p + 'delta', 0.0):.2f}"
        if kind == "Doblete":
            t += f" Δ {vals.get(p + 'quad', 0.0):.2f}"
        elif kind == "Sextete":
            t += f" B {vals.get(p + 'bhf', 0.0):.1f}"
        out.append(t)
    return " · ".join(out)


def detection_report_html(report) -> str:
    import html as _h
    best = min(p.bic for p in report.proposals)
    filas = []
    for p in report.proposals:
        marca = "▶" if p is report.chosen else ""
        filas.append(
            f"<tr><td>{marca}</td><td>{_h.escape(origin_text(p.origin))}</td>"
            f"<td>{_h.escape(proposal_components_text(p))}</td>"
            f"<td align='right'>{p.red_chi2:.2f}</td>"
            f"<td align='right'>{p.bic - best:+.1f}</td></tr>")
    pasos = []
    for st in report.residual_steps:
        clave = ("detect.step_removed" if "removed" in st else
                 "detect.step_added" if st["accepted"] else "detect.step_rejected")
        pasos.append("<li>" + _h.escape(tr(clave, what=origin_text(st["origin"]),
                                             dbic=f"{st['dbic']:+.1f}")) + "</li>")
    final = report.final
    html = [f"<p>{_h.escape(tr('detect.intro', n=len(report.peaks)))}</p>",
            "<table cellspacing='0' cellpadding='4' border='1' style='border-collapse:collapse'>",
            f"<tr><th></th><th>{_h.escape(tr('detect.col_origin'))}</th>"
            f"<th>{_h.escape(tr('detect.col_components'))}</th>"
            f"<th>χ²red</th><th>ΔBIC</th></tr>", *filas, "</table>",
            f"<p>{_h.escape(tr('detect.choice_rule'))}</p>"]
    if pasos:
        html += [f"<p><b>{_h.escape(tr('detect.steps_title'))}</b></p><ul>", *pasos, "</ul>"]
    html.append(f"<p><b>{_h.escape(tr('detect.final', comps=proposal_components_text(final), chi2=f'{final.red_chi2:.2f}'))}</b></p>")
    html.append(f"<p>{_h.escape(tr('detect.applied'))}</p>")
    return "\n".join(html)

