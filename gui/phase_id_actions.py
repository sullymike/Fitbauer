"""Sugeridor de fases: identifica fases compatibles con los parámetros de cada
componente, tanto tras el ajuste como al inicializar desde mínimos.

La lógica de comparación vive en ``core.phase_id`` (pura). Aquí sólo se leen los
parámetros de los paneles, se muestran las sugerencias y, opcionalmente, se
aplican los valores de referencia como punto de partida del ajuste.
"""
from __future__ import annotations

from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.phase_id import PhaseMatch, suggest_phases


class PhaseIdMixin:
    # ── Lectura de parámetros de un panel de componente ──────────────────
    def _component_query(self, cp) -> tuple[float | None, float | None, float | None, str]:
        """Devuelve (delta, quad, bhf, kind) leídos del panel ``cp``."""
        kind = getattr(cp, "kind", None) or cp.type_combo.currentText()

        def _val(name: str) -> float | None:
            ctl = cp.params.get(name)
            return float(ctl.value()) if ctl is not None else None

        return _val("delta"), _val("quad"), _val("bhf"), kind

    def _gather_suggestions(self) -> list[tuple[int, str, tuple, list[PhaseMatch]]]:
        """Para cada componente activo: (idx, kind, (δ,ΔEQ,B), matches)."""
        out: list[tuple[int, str, tuple, list[PhaseMatch]]] = []
        for cp in getattr(self, "components_panels", []):
            if not cp.enabled.isChecked():
                continue
            delta, quad, bhf, kind = self._component_query(cp)
            if delta is None:
                continue
            matches = suggest_phases(delta, quad=quad, bhf=bhf, kind=kind, top_n=6)
            out.append((cp.idx, kind, (delta, quad, bhf), matches))
        return out

    # ── Acción de menú: identificar fases (post-ajuste) ──────────────────
    def on_identify_phases(self) -> None:
        data = self._gather_suggestions()
        if not data:
            QtWidgets.QMessageBox.information(
                self, tr("phase.identify", default="Identificar fases"),
                tr("phase.no_components",
                   default="No hay componentes activas con parámetros para identificar."))
            return
        self._show_phase_dialog(data, allow_apply=True)

    # ── Diálogo de sugerencias ───────────────────────────────────────────
    def _show_phase_dialog(self, data, allow_apply: bool) -> None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("phase.dialog_title", default="Fases compatibles"))
        dlg.resize(820, 560)
        outer = QtWidgets.QVBoxLayout(dlg)

        intro = QtWidgets.QLabel(tr(
            "phase.intro",
            default="Fases de referencia compatibles con cada componente "
                    "(ordenadas por similitud). Selecciona una para usar sus "
                    "valores como punto de partida."))
        intro.setWordWrap(True)
        outer.addWidget(intro)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(inner)
        scroll.setWidget(inner)
        outer.addWidget(scroll, stretch=1)

        # combos[idx] = (QComboBox, kind) para aplicar al aceptar.
        self._phase_apply_combos: dict[int, tuple[QtWidgets.QComboBox, str]] = {}

        for idx, kind, (delta, quad, bhf), matches in data:
            box = QtWidgets.QGroupBox(self._component_header(idx, kind, delta, quad, bhf))
            bl = QtWidgets.QVBoxLayout(box)
            if not matches:
                bl.addWidget(QtWidgets.QLabel(
                    tr("phase.no_match", default="Sin fases compatibles en la base de datos.")))
            else:
                table = QtWidgets.QTableWidget(len(matches), 6)
                table.setHorizontalHeaderLabels([
                    tr("phase.col_phase", default="Fase"),
                    tr("phase.col_score", default="Similitud"),
                    tr("phase.col_params", default="δ / ΔEQ / B(T)"),
                    tr("phase.col_os", default="Fe"),
                    tr("phase.col_T", default="T (K)"),
                    tr("phase.col_ref", default="Referencia"),
                ])
                table.verticalHeader().setVisible(False)
                table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
                table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
                for r, m in enumerate(matches):
                    table.setItem(r, 0, QtWidgets.QTableWidgetItem(m.sample))
                    table.setItem(r, 1, QtWidgets.QTableWidgetItem(f"{m.score_pct:.0f}%"))
                    table.setItem(r, 2, QtWidgets.QTableWidgetItem(self._fmt_params(m)))
                    table.setItem(r, 3, QtWidgets.QTableWidgetItem(m.oxidation_state or "—"))
                    table.setItem(r, 4, QtWidgets.QTableWidgetItem(
                        "" if m.temperature_k is None else f"{m.temperature_k:g}"))
                    table.setItem(r, 5, QtWidgets.QTableWidgetItem(m.reference))
                table.resizeColumnsToContents()
                table.horizontalHeader().setStretchLastSection(True)
                table.setMinimumHeight(min(38 + 26 * len(matches), 200))
                bl.addWidget(table)

                if allow_apply:
                    row = QtWidgets.QHBoxLayout()
                    row.addWidget(QtWidgets.QLabel(
                        tr("phase.apply_label", default="Usar valores de:")))
                    combo = QtWidgets.QComboBox()
                    combo.addItem(tr("phase.apply_none", default="(no aplicar)"), None)
                    for m in matches:
                        combo.addItem(f"{m.sample} ({m.score_pct:.0f}%)", m)
                    row.addWidget(combo, stretch=1)
                    bl.addLayout(row)
                    self._phase_apply_combos[idx] = (combo, kind)
            vbox.addWidget(box)

        vbox.addStretch(1)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        outer.addWidget(bb)

        if dlg.exec() == QtWidgets.QDialog.Accepted and allow_apply:
            self._apply_phase_selections()

    def _apply_phase_selections(self) -> None:
        """Aplica los valores de referencia elegidos a cada componente."""
        applied = 0
        self._building = True
        try:
            for idx, (combo, kind) in getattr(self, "_phase_apply_combos", {}).items():
                m: PhaseMatch | None = combo.currentData()
                if m is None:
                    continue
                cp = next((c for c in self.components_panels if c.idx == idx), None)
                if cp is None:
                    continue
                self._apply_match_to_panel(cp, m, kind)
                applied += 1
        finally:
            self._building = False
        if applied:
            self._simulate_enabled = True
            self._refresh_plot()
            self.statusBar().showMessage(
                tr("phase.applied", n=applied,
                   default=f"Valores de referencia aplicados a {applied} componente(s)"), 5000)

    @staticmethod
    def _apply_match_to_panel(cp, m: PhaseMatch, kind: str) -> None:
        def _set(name: str, value: float | None) -> None:
            if value is None:
                return
            ctl = cp.params.get(name)
            if ctl is not None:
                ctl.set_value(float(value))

        _set("delta", m.delta)
        if kind in ("Sextete", "Doblete"):
            _set("quad", abs(m.quad) if (m.quad is not None and kind == "Sextete") else m.quad)
        if kind == "Sextete":
            _set("bhf", m.bhf)

    # ── Sugerencia tras inicializar desde mínimos ────────────────────────
    def _suggest_phases_after_init(self) -> None:
        """Tras inicializar desde mínimos, ofrece identificar y sembrar fases."""
        data = self._gather_suggestions()
        if not any(matches for _i, _k, _p, matches in data):
            return
        self._show_phase_dialog(data, allow_apply=True)

    # ── Formato ──────────────────────────────────────────────────────────
    @staticmethod
    def _component_header(idx, kind, delta, quad, bhf) -> str:
        parts = [f"δ={delta:.2f}"]
        if quad is not None:
            parts.append(f"ΔEQ={quad:.2f}")
        if bhf is not None and bhf > 5.0:
            parts.append(f"B={bhf:.1f} T")
        return tr("phase.component_header",
                  idx=idx, kind=tr(f"kind.{kind}", default=kind),
                  params="  ".join(parts),
                  default=f"Componente {idx} ({kind}):  " + "  ".join(parts))

    @staticmethod
    def _fmt_params(m: PhaseMatch) -> str:
        d = "—" if m.delta is None else f"{m.delta:.2f}"
        q = "—" if m.quad is None else f"{m.quad:.2f}"
        b = "—" if m.bhf is None else f"{m.bhf:.1f}"
        return f"{d} / {q} / {b}"
