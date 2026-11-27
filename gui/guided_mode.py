"""Modo guiado: panel lateral con los pasos de un ajuste discreto.

Pensado para quien no conoce el programa. Cada paso dice qué hay que hacer,
cómo va y tiene un botón que llama a la acción que ya existe en la ventana
(cargar, inicializar desde mínimos, ajustar, autoajustar el residuo,
diagnóstico, informe). No tiene lógica de ajuste propia: el resto de la
interfaz sigue funcionando igual y lo que se haga allí se refleja aquí.

1. Calibración     — la activa (Vmax e IS del α-Fe) y cómo fijarla: equipo,
                     web o un α-Fe ajustado aquí mismo.
2. Espectro        — fichero y Vmax.
3. Componentes     — detectar desde los mínimos; tipo y fase probable.
4. Ajustar         — ajuste (estrategia de la ventana) y «buscar lo que falta».
5. ¿Es fiable?     — veredicto del diagnóstico en lenguaje llano, con un
                     botón para el arreglo de cada aviso.
6. Resultado       — tabla sencilla (tipo, δ, ΔEQ, BHF, área, fase) e informe.

El panel se refresca solo mientras está visible, comparando una firma del
estado para no reconstruir los widgets si nada cambió.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

from mossbauer_i18n import tr

_COLOR = {"ok": "#1a8a5a", "warn": "#b7791f", "fail": "#c53030"}
_ICON = {"ok": "✓", "warn": "⚠", "fail": "✗"}

#: Arreglo propuesto para cada comprobación del diagnóstico discreto:
#: (clave del texto del botón, nombre del método de la ventana).
_FIXES = {
    "chi2": ("guided.fix_residual", "on_auto_fit_residual"),
    "residual": ("guided.fix_residual", "on_auto_fit_residual"),
    "bounds": ("guided.fix_limits", "on_param_limits"),
    "start": ("guided.fix_explore", "_guided_fit_explore"),
    "minima": ("guided.fix_explore", "_guided_fit_explore"),
    "swap": ("guided.fix_explore", "_guided_fit_explore"),
    "convergence": ("guided.fix_explore", "_guided_fit_explore"),
}


def _fmt(x, nd: int = 3) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "—"
    return "—" if not math.isfinite(x) else f"{x:.{nd}f}"


def _fmt_err(x, err, nd: int = 3) -> str:
    """«valor» y debajo «± error» (dos líneas, para que la tabla quepa en el
    panel); sin error (parámetro fijo o sin covarianza), solo el valor."""
    txt = _fmt(x, nd)
    try:
        e = float(err)
    except (TypeError, ValueError):
        return txt
    if txt == "—" or not math.isfinite(e) or e <= 0:
        return txt
    return f"{txt}\n± {_fmt(e, nd)}"


class _Step(QtWidgets.QFrame):
    """Caja de un paso: número + título, estado y zona de botones."""

    def __init__(self, n: int, title: str, hint: str):
        super().__init__()
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        # Que no se comprima: si no cabe, el QScrollArea desplaza (con la
        # política por defecto los rótulos con salto de línea se montaban).
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                           QtWidgets.QSizePolicy.Policy.Minimum)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)
        head = QtWidgets.QLabel(f"<b>{n}. {title}</b>")
        lay.addWidget(head)
        self.hint = QtWidgets.QLabel(hint)
        self.hint.setWordWrap(True)
        pal = self.hint.palette()
        pal.setColor(QtGui.QPalette.ColorRole.WindowText,
                     pal.color(QtGui.QPalette.ColorGroup.Disabled,
                               QtGui.QPalette.ColorRole.WindowText))
        self.hint.setPalette(pal)
        lay.addWidget(self.hint)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(QtCore.Qt.TextFormat.RichText)
        lay.addWidget(self.status)
        self.body = QtWidgets.QVBoxLayout()
        self.body.setSpacing(4)
        lay.addLayout(self.body)
        self.buttons = QtWidgets.QHBoxLayout()
        lay.addLayout(self.buttons)

    def add_button(self, text: str, slot, primary: bool = False) -> QtWidgets.QPushButton:
        b = QtWidgets.QPushButton(text)
        if primary:
            f = b.font()
            f.setBold(True)
            b.setFont(f)
        b.clicked.connect(lambda _c=False: slot())
        self.buttons.addWidget(b)
        return b


class GuidedPanel(QtWidgets.QWidget):
    def __init__(self, win):
        super().__init__()
        self._win = win
        self._sig = None
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        intro = QtWidgets.QLabel(tr("guided.intro"))
        intro.setWordWrap(True)
        outer.addWidget(intro)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QtWidgets.QWidget()
        self._lay = QtWidgets.QVBoxLayout(inner)
        self._lay.setSpacing(8)
        scroll.setWidget(inner)
        outer.addWidget(scroll, stretch=1)

        w = win
        self.s_cal = _Step(1, tr("guided.s0_title"), tr("guided.s0_hint"))
        self.s_cal.add_button(tr("guided.s0_instruments"), lambda: w.on_instruments(),
                              primary=True)
        self.s_cal.add_button(tr("guided.s0_web"),
                              lambda: w._open_web_dialog("calibrations"))
        self.btn_use_calib = self.s_cal.add_button(
            tr("guided.s0_use"), lambda: w._use_as_calibration_detailed())
        self.btn_use_calib.setToolTip(tr("guided.s0_use_tip"))
        self.s_file = _Step(2, tr("guided.s1_title"), tr("guided.s1_hint"))
        self.s_file.add_button(tr("guided.s1_open"), w.on_open, primary=True)
        self.s_comp = _Step(3, tr("guided.s2_title"), tr("guided.s2_hint"))
        self.btn_detect = self.s_comp.add_button(
            tr("guided.s2_detect"), lambda: w.on_init_from_minima(show_message=False),
            primary=True)
        self.btn_edit_minima = self.s_comp.add_button(
            tr("guided.s2_edit"), lambda: w.on_edit_minima())
        self.s_fit = _Step(4, tr("guided.s3_title"), tr("guided.s3_hint"))
        self.btn_fit = self.s_fit.add_button(tr("guided.s3_fit"), w.on_fit, primary=True)
        self.btn_residual = self.s_fit.add_button(
            tr("guided.s3_residual"), lambda: w.on_auto_fit_residual())
        self.s_diag = _Step(5, tr("guided.s4_title"), tr("guided.s4_hint"))
        self.btn_details = self.s_diag.add_button(
            tr("guided.s4_details"), lambda: w.show_fit_diagnostics())
        self.s_res = _Step(6, tr("guided.s5_title"), tr("guided.s5_hint"))
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            tr("guided.col_kind"), "δ\n(mm/s)", "ΔEQ\n(mm/s)", "BHF\n(T)",
            tr("guided.col_area") + "\n(%)", tr("guided.col_phase").replace(" ", "\n", 1)])
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.s_res.body.addWidget(self.table)
        self.btn_report = self.s_res.add_button(
            tr("guided.s5_report"), lambda: w.on_export_short_report(), primary=True)
        self.btn_save = self.s_res.add_button(tr("guided.s5_save"), lambda: w.on_save_session())
        for s in (self.s_cal, self.s_file, self.s_comp, self.s_fit, self.s_diag, self.s_res):
            self._lay.addWidget(s)
        self.dist_note = QtWidgets.QLabel(tr("guided.dist_note"))
        self.dist_note.setWordWrap(True)
        self._lay.addWidget(self.dist_note)
        self._lay.addStretch(1)
        self._fix_buttons: list[QtWidgets.QWidget] = []

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self.refresh)

    def showEvent(self, event):  # noqa: N802 (API de Qt)
        super().showEvent(event)
        self._sig = None
        self.refresh()
        self._timer.start()

    def resizeEvent(self, event):  # noqa: N802 (API de Qt)
        super().resizeEvent(event)
        QtCore.QTimer.singleShot(0, self._fit_labels)

    def _fit_labels(self) -> None:
        """Altura mínima de cada rótulo con salto de línea según su ancho real.

        Dentro de un QScrollArea, Qt no propaga bien la altura que necesita
        un texto partido en varias líneas y los rótulos se montaban unos
        encima de otros cuando el panel es bajo; fijándola, el área desplaza.
        """
        for lab in self.findChildren(QtWidgets.QLabel):
            if lab.wordWrap() and lab.width() > 20:
                lab.setMinimumHeight(lab.heightForWidth(lab.width()))

    def hideEvent(self, event):  # noqa: N802 (API de Qt)
        super().hideEvent(event)
        self._timer.stop()

    # ── estado ──────────────────────────────────────────────────────────
    def _components(self):
        w = self._win
        out = []
        for cs in w._active_component_states():
            v = cs.values
            out.append((cs.idx, cs.kind, v.get("delta"), v.get("quad"), v.get("bhf")))
        return out

    def _signature(self):
        w = self._win
        res = w.runtime_results.fit_result if hasattr(w, "runtime_results") else None
        comps = tuple((i, k, round(float(d or 0), 3), round(float(q or 0), 3),
                       round(float(b or 0), 2)) for i, k, d, q, b in self._components())
        checks = tuple((c.key, c.status) for c in w.fit_checks())
        return (str(getattr(w.file, "path", "")), w.file.y_data is not None,
                bool(w.is_distribution_mode), comps, id(res), checks,
                getattr(w, "_fit_strategy", lambda: "")(),
                id(getattr(w, "calibration_info", None)),
                id(getattr(w, "_last_detection", None)),
                id(getattr(w, "_last_fit_story", None)),
                id(getattr(w, "_last_residual_story", None)))

    def refresh(self) -> None:
        sig = self._signature()
        if sig == self._sig:
            return
        self._sig = sig
        w = self._win
        loaded = w.file.y_data is not None
        dist = bool(w.is_distribution_mode)
        self.dist_note.setVisible(dist)
        for s in (self.s_comp, self.s_fit, self.s_diag, self.s_res):
            s.setEnabled(loaded and not dist)

        # 1. Calibración
        self.s_cal.status.setText(self._calibration_text())
        self.btn_use_calib.setEnabled(
            loaded and not dist and getattr(w.runtime_results, "fit_result", None) is not None)

        # 2. Espectro
        if loaded:
            nombre = getattr(w.file.path, "name", None) or str(w.file.path or "")
            vmax = w.calib.to_view_state().values_dict().get("vmax")
            texto = tr("guided.s1_status", file=nombre, vmax=_fmt(vmax, 4))
            iso = w.calibration_iso_ref() if hasattr(w, "calibration_iso_ref") else None
            if iso is None:
                texto += ("<br><span style='color:%s'>⚠ %s</span>"
                          % (_COLOR["warn"], tr("guided.s1_no_calib")))
            self.s_file.status.setText(texto)
        else:
            self.s_file.status.setText(tr("guided.s1_empty"))

        # 2. Componentes
        comps = self._components()
        if comps:
            filas = []
            for idx, kind, d, q, b in comps:
                fase = self._phase(kind, d, q, b)
                txt = tr("guided.s2_comp", idx=idx, kind=tr(f"kind.{kind}", default=kind))
                if fase:
                    txt += f" · ≈ {fase}"
                filas.append(txt)
            det = self._detection_text()
            self.s_comp.status.setText((det + "<br>" if det else "") + "<br>".join(filas))
        else:
            self.s_comp.status.setText(tr("guided.s2_none"))

        # 3. Ajustar
        res = w.runtime_results.fit_result
        estrategia = tr("fit.strategy_local") if w._fit_strategy() == "local" \
            else tr("fit.strategy_explore")
        if res is not None and getattr(res, "stats", None):
            texto = tr("guided.s3_done", chi2=_fmt(res.stats.get("red_chi2"), 2),
                       strategy=estrategia)
            texto += self._fit_story_text()
        else:
            texto = tr("guided.s3_strategy", strategy=estrategia)
        texto += self._residual_story_text()
        self.s_fit.status.setText(texto)
        self.btn_residual.setEnabled(bool(comps))

        # 4. ¿Es fiable?
        for b in self._fix_buttons:
            b.setParent(None)
            b.deleteLater()
        self._fix_buttons = []
        checks = w.fit_checks()
        if not checks:
            self.s_diag.status.setText(tr("guided.s4_none"))
            self.btn_details.setEnabled(False)
        else:
            from core.fit_diagnostics import verdict
            v = verdict(checks)
            clave = {"ok": "guided.s4_ok", "warn": "guided.s4_warn", "fail": "guided.s4_fail"}[v]
            self.s_diag.status.setText(
                f"<span style='color:{_COLOR[v]}'><b>{_ICON[v]} {tr(clave)}</b></span>")
            self.btn_details.setEnabled(True)
            vistos = set()
            for c in checks:
                if c.status not in ("warn", "fail"):
                    continue
                box = QtWidgets.QWidget()
                bl = QtWidgets.QVBoxLayout(box)
                bl.setContentsMargins(0, 2, 0, 2)
                bl.setSpacing(2)
                lab = QtWidgets.QLabel(
                    f"<span style='color:{_COLOR[c.status]}'>{_ICON[c.status]}</span> "
                    f"<b>{c.title}</b>: {c.meaning or c.value}")
                lab.setWordWrap(True)
                bl.addWidget(lab)
                fix = _FIXES.get(c.key)
                # χ² bajo no se arregla añadiendo componentes.
                if c.key == "chi2" and c.meaning == tr("diag.chi2_low_meaning"):
                    fix = None
                if fix and fix[1] not in vistos and hasattr(w, fix[1]):
                    vistos.add(fix[1])
                    b = QtWidgets.QPushButton(tr(fix[0]))
                    b.clicked.connect(lambda _c=False, m=fix[1]: getattr(w, m)())
                    bl.addWidget(b, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
                elif c.action:
                    act = QtWidgets.QLabel("→ " + c.action)
                    act.setWordWrap(True)
                    bl.addWidget(act)
                self.s_diag.body.addWidget(box)
                self._fix_buttons.append(box)

        # 5. Resultado
        self._fill_table(res is not None)
        QtCore.QTimer.singleShot(0, self._fit_labels)

    # ── relatos de lo que hizo cada acción ───────────────────────────────
    def _calibration_text(self) -> str:
        """La calibración activa con su origen, Vmax e IS (± σ si constan),
        o el aviso de que no hay ninguna."""
        w = self._win
        info = getattr(w, "calibration_info", None) or {}
        iso = w.calibration_iso_ref() if hasattr(w, "calibration_iso_ref") else None
        vmax = w._fixed_calibration_vmax() if hasattr(w, "_fixed_calibration_vmax") else None
        if not info or (iso is None and vmax is None):
            return ("<span style='color:%s'>⚠ %s</span>"
                    % (_COLOR["warn"], tr("guided.s0_none")))
        origen = (w.calib_label.text().split("<br>")[0]
                  if hasattr(w, "calib_label") else str(info.get("source", "")))
        escala = w._calibration_scale() if hasattr(w, "_calibration_scale") else 1.0

        def con_sigma(x, clave):
            sig = info.get(clave)
            try:
                sig = float(sig) * escala if sig not in (None, "") else None
            except (TypeError, ValueError):
                sig = None
            return _fmt(x, 4) + (f" ± {_fmt(sig, 4)}" if sig else "")
        partes = []
        if vmax is not None:
            partes.append(f"Vmax = {con_sigma(vmax, 'vmax_uncertainty')} mm/s")
        if iso is not None:
            partes.append(tr("guided.s0_iso", iso=con_sigma(iso, "isomer_shift_uncertainty")))
        return (f"<span style='color:{_COLOR['ok']}'>✓</span> {origen}<br>"
                + " · ".join(partes))

    def _detection_text(self) -> str:
        det = getattr(self._win, "_last_detection", None)
        if not det:
            return ""
        partes = []
        for c in det["components"]:
            kind = tr(f"kind.{c['kind']}", default=c["kind"])
            datos = [f"δ ≈ {_fmt(c.get('delta'), 2)}"]
            if c["kind"] == "Doblete":
                datos.append(f"ΔEQ ≈ {_fmt(c.get('quad'), 2)}")
            elif c["kind"] not in ("Singlete",):
                datos.append(f"BHF ≈ {_fmt(c.get('bhf'), 1)} T")
            partes.append(tr("guided.det_comp", idx=c["idx"], kind=kind,
                             n=len(c["positions"]), data=", ".join(datos)))
        txt = tr("guided.det_head", n=det["n_peaks"]) + "<br>" + "<br>".join(
            "&nbsp;&nbsp;" + p for p in partes)
        if det["unused"]:
            txt += "<br>&nbsp;&nbsp;" + tr(
                "guided.det_unused", n=len(det["unused"]),
                pos=", ".join(_fmt(x, 2) for x in det["unused"][:6]))
        if getattr(self._win, "_detection_fresh", False):
            txt += "<br><i>" + tr("guided.det_marks") + "</i>"
        return txt

    def _fit_story_text(self) -> str:
        """Los parámetros que más se movieron (respecto a su rango de ajuste)."""
        w = self._win
        st = getattr(w, "_last_fit_story", None)
        if not st:
            return ""
        filas = []
        for k, v1 in st["end"].items():
            v0 = st["start"].get(k)
            if v0 is None:
                continue
            lo, hi = st["bounds"].get(k, (-math.inf, math.inf))
            rango = (hi - lo) if math.isfinite(hi - lo) and hi > lo else max(abs(v0), 1.0)
            filas.append((abs(v1 - v0) / rango, k, v0, v1))
        filas.sort(reverse=True)
        movidos = [f for f in filas if f[0] > 1e-4][:5]
        cab = tr("guided.fit_head", n=len(st["end"]), starts=st["n_starts"])
        if not movidos:
            return "<br>" + cab + " " + tr("guided.fit_nothing")
        nombre = getattr(w, "_param_short_name", lambda k: k)
        lineas = [f"&nbsp;&nbsp;{nombre(k)}: {_fmt(v0, 4)} → <b>{_fmt(v1, 4)}</b>"
                  + (f" ± {_fmt(st['errors'].get(k), 4)}" if st["errors"].get(k) else "")
                  for _r, k, v0, v1 in movidos]
        return "<br>" + cab + "<br>" + "<br>".join(lineas)

    def _residual_story_text(self) -> str:
        st = getattr(self._win, "_last_residual_story", None)
        if not st:
            return ""
        out = st.get("outcome")
        if out == "none":
            return "<br><b>" + tr("guided.res_title") + ":</b> " + st.get("text", "")
        prop = "; ".join(
            tr(f"kind.{p['kind']}", default=p["kind"]) + f" (δ ≈ {_fmt(p.get('delta'), 2)}"
            + (f", BHF ≈ {_fmt(p.get('bhf'), 1)} T" if p.get("bhf") is not None else "")
            + (f", ΔEQ ≈ {_fmt(p.get('quad'), 2)}" if p.get("quad") is not None else "") + ")"
            for p in st.get("proposed", []))
        dbic = _fmt(st.get("dbic"), 1)
        clave = "guided.res_accepted" if out == "accepted" else "guided.res_rejected"
        color = _COLOR["ok"] if out == "accepted" else _COLOR["warn"]
        return ("<br><b>" + tr("guided.res_title") + ":</b> " + tr("guided.res_proposed", what=prop)
                + f"<br>&nbsp;&nbsp;<span style='color:{color}'>"
                + tr(clave, dbic=dbic) + "</span>")

    def _phase(self, kind, d, q, b) -> str:
        if d is None:
            return ""
        try:
            from core.phase_id import suggest_phases
            m = suggest_phases(d, quad=q, bhf=b, kind=kind, top_n=1)
        except Exception:
            return ""
        if not m or m[0].score_pct < 75:
            return ""
        t = m[0].temperature_k
        temp = f", {t:g} K" if t is not None and t < 250 else ""
        return f"{m[0].sample} ({m[0].score_pct:.0f} %{temp})"

    def _fill_table(self, has_fit: bool) -> None:
        w = self._win
        comps = self._components() if has_fit else []
        pct, pct_err = {}, {}
        res = getattr(getattr(w, "runtime_results", None), "fit_result", None)
        errs = dict(getattr(res, "errors", None) or {}) if comps else {}
        if comps:
            try:
                idxs, _areas, perc = w.component_area_percentages()
                pct = {int(i): float(p) for i, p in zip(idxs, perc)}
            except Exception:
                pct = {}
            try:
                pct_err = {int(i): float(e) for i, e in w.component_percentage_errors().items()}
            except Exception:
                pct_err = {}
        self.table.setRowCount(len(comps))
        for r, (idx, kind, d, q, b) in enumerate(comps):
            magnet = kind not in ("Doblete", "Singlete")
            e = lambda name: errs.get(f"s{idx}_{name}")
            cells = [f"{idx} · " + tr(f"kind.{kind}", default=kind),
                     _fmt_err(d, e("delta")), _fmt_err(q, e("quad")),
                     _fmt_err(b, e("bhf"), 2) if magnet else "—",
                     _fmt_err(pct[idx], pct_err.get(idx), 1) if idx in pct else "—",
                     (self._phase(kind, d, q, b) or "—").replace(" (", "\n(", 1)]
            for col, txt in enumerate(cells):
                self.table.setItem(r, col, QtWidgets.QTableWidgetItem(txt))
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()
        alto = self.table.horizontalHeader().sizeHint().height() + 2 * self.table.frameWidth()
        alto += sum(self.table.rowHeight(r) for r in range(len(comps)))
        if self.table.horizontalHeader().length() > self.table.viewport().width():
            alto += self.table.horizontalScrollBar().sizeHint().height()
        self.table.setFixedHeight(alto)
        self.table.setVisible(bool(comps))
        self.s_res.status.setText("" if comps else tr("guided.s5_none"))
        self.btn_report.setEnabled(bool(comps))
        self.btn_save.setEnabled(bool(comps))


class GuidedModeMixin:
    """Acción Vista › Modo guiado y dock del asistente."""

    def _ensure_guided_dock(self) -> QtWidgets.QDockWidget:
        dock = getattr(self, "_guided_dock", None)
        if dock is None:
            dock = QtWidgets.QDockWidget(tr("guided.title"), self)
            dock.setObjectName("guided_dock")
            dock.setAllowedAreas(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
                                 | QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
            self.guided_panel = GuidedPanel(self)
            dock.setWidget(self.guided_panel)
            dock.setMinimumWidth(400)
            self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
            # Cerrar el dock con su «×» apaga el modo (y la casilla del menú).
            dock.visibilityChanged.connect(self._on_guided_dock_visibility)
            self._guided_dock = dock
        return dock

    def set_guided_mode(self, enabled: bool) -> None:
        self.guided_mode = bool(enabled)
        act = getattr(self, "act_guided_mode", None)
        if act is not None and act.isChecked() != self.guided_mode:
            act.blockSignals(True)
            act.setChecked(self.guided_mode)
            act.blockSignals(False)
        if self.guided_mode:
            self._ensure_guided_dock().show()
        elif getattr(self, "_guided_dock", None) is not None:
            self._guided_dock.hide()
        if getattr(self.file, "velocity", None) is not None:
            self._refresh_plot()      # pone o quita las marcas de la detección

    def _on_guided_toggled(self, checked: bool) -> None:
        self.set_guided_mode(checked)
        self._save_settings()

    def _on_guided_dock_visibility(self, visible: bool) -> None:
        # Solo el cierre explícito (no minimizar la ventana) apaga el modo.
        if not visible and self.isVisible() and not self.isMinimized() \
                and getattr(self, "guided_mode", False) and self._guided_dock.isHidden():
            self.set_guided_mode(False)
            self._save_settings()

    def _draw_guided_overlay(self) -> None:
        """En modo guiado y tras «Detectar», marca sobre los datos los mínimos
        de cada componente propuesta (número encima) y, en gris, los que no
        se usaron. Desaparecen con el siguiente ajuste."""
        det = getattr(self, "_last_detection", None)
        if not (getattr(self, "guided_mode", False) and det
                and getattr(self, "_detection_fresh", False)):
            return
        canvas = getattr(self, "canvas", None)
        ax = getattr(canvas, "ax", None)
        v, y = self.file.velocity, self.file.y_data
        if ax is None or v is None or y is None:
            return
        import numpy as np
        v = np.asarray(v, dtype=float)
        y = np.asarray(y, dtype=float)
        orden = np.argsort(v)
        colores = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"]
        for k, c in enumerate(det["components"]):
            col = colores[k % len(colores)]
            xs = np.asarray(c["positions"], dtype=float)
            ys = np.interp(xs, v[orden], y[orden])
            ax.scatter(xs, ys, s=70, marker="v", c=col, edgecolors="white",
                       linewidths=1.0, zorder=7)
            for xx, yy in zip(xs, ys):
                ax.annotate(str(c["idx"]), (xx, yy), textcoords="offset points",
                            xytext=(0, -14), ha="center", color=col, fontsize=9,
                            fontweight="bold", zorder=8)
        if det["unused"]:
            xs = np.asarray(det["unused"], dtype=float)
            ax.scatter(xs, np.interp(xs, v[orden], y[orden]), s=60, marker="v",
                       facecolors="none", edgecolors="#94a3b8", linewidths=1.2, zorder=7)
        canvas.draw_idle()

    def _guided_fit_explore(self) -> None:
        """Arreglo del diagnóstico: repetir el ajuste con varios arranques."""
        combo = getattr(self, "strategy_combo", None)
        if combo is not None:
            combo.setCurrentText("explore")
        self.on_fit()
