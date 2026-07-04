"""Editor semi-manual de mínimos sobre el canvas Matplotlib.

Sustituye a la antigua implementación basada en Plotly + QtWebEngine (ver
``docs/plotly.md``). Reutiliza intacta la lógica de estado (``_minima_entries``,
detección, propuesta de componentes) y solo cambia la capa de dibujo y de
eventos: los mínimos se dibujan como marcadores sobre ``SpectrumCanvas`` y la
interacción usa los eventos de ratón de Matplotlib (``button_press_event``).

Interacción:
- Clic sobre el espectro en zona vacía  → añade un mínimo.
- Clic sobre/cerca de un marcador         → lo activa o desactiva.
"""
from __future__ import annotations

import numpy as np
from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.param_overrides import effective_peak_detection_specs as _eff_pd


class MinimaEditorMixin:
    # ── Panel lateral con la lista de mínimos ────────────────────────────
    def _build_minima_editor(self) -> QtWidgets.QWidget:
        """Panel lateral con la lista de mínimos detectados (editable)."""
        box = QtWidgets.QGroupBox(tr("minima.editor_title", default="Mínimos detectados"))
        box.setMinimumWidth(240)
        lay = QtWidgets.QVBoxLayout(box)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        hint = QtWidgets.QLabel(tr(
            "minima.editor_hint",
            default="Marca/desmarca los mínimos a usar e indica cuántas "
                    "contribuciones tiene cada uno. Sobre el gráfico, un clic en "
                    "zona vacía añade un mínimo y un clic sobre/cerca de un "
                    "marcador lo activa o desactiva."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#64748b;font-size:11px;")
        lay.addWidget(hint)

        self.btn_minima_detect = QtWidgets.QPushButton(
            tr("minima.redetect", default="Volver a detectar"))
        self.btn_minima_detect.clicked.connect(lambda _=False: self.on_edit_minima(redetect=True))
        lay.addWidget(self.btn_minima_detect)

        self._minima_list_container = QtWidgets.QWidget()
        self._minima_list_layout = QtWidgets.QVBoxLayout(self._minima_list_container)
        self._minima_list_layout.setContentsMargins(0, 0, 0, 0)
        self._minima_list_layout.setSpacing(2)
        self._minima_list_layout.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._minima_list_container)
        lay.addWidget(scroll, stretch=1)

        self.minima_count_label = QtWidgets.QLabel("")
        self.minima_count_label.setStyleSheet("font-size:11px;")
        lay.addWidget(self.minima_count_label)

        btns = QtWidgets.QHBoxLayout()
        self.btn_minima_propose = QtWidgets.QPushButton(
            tr("minima.propose", default="Proponer ajuste"))
        self.btn_minima_propose.clicked.connect(lambda _=False: self.on_propose_from_minima())
        self.btn_minima_done = QtWidgets.QPushButton(
            tr("minima.done", default="Cerrar edición"))
        self.btn_minima_done.clicked.connect(lambda _=False: self._exit_minima_edit())
        btns.addWidget(self.btn_minima_propose)
        btns.addWidget(self.btn_minima_done)
        lay.addLayout(btns)
        return box

    # ── Entrada/salida del modo edición ──────────────────────────────────
    def on_edit_minima(self, redetect: bool = True) -> None:
        """Entra en el modo de edición semi-manual de mínimos."""
        if self.file.velocity is None or self.file.y_data is None:
            QtWidgets.QMessageBox.information(
                self, tr("minima.editor_title", default="Mínimos detectados"),
                tr("msg.no_file", default="Carga primero un espectro."))
            return
        if redetect or not self._minima_entries:
            peaks, baseline, slope = self.detect_absorption_minima()
            self._minima_baseline = baseline
            self._minima_slope = slope
            self._minima_entries = [
                {"i": int(p["i"]), "pos": float(p["pos"]), "depth": float(p["depth"]),
                 "width": float(p["width"]), "smooth_depth": float(p.get("smooth_depth", p["depth"])),
                 "included": True, "count": 1}
                for p in peaks
            ]
        if not self._minima_entries:
            QtWidgets.QMessageBox.information(
                self, tr("minima.editor_title", default="Mínimos detectados"),
                tr("msg.auto_minima_none", default="No se detectaron mínimos."))
            return
        self._minima_edit_mode = True
        self._populate_minima_list()
        if hasattr(self, "minima_editor"):
            self.minima_editor.show()
        # Asegura el render base y dibuja el overlay de marcadores encima.
        self._refresh_plot()
        self._draw_minima_overlay_mpl()

    def _exit_minima_edit(self) -> None:
        self._minima_edit_mode = False
        if hasattr(self, "minima_editor"):
            self.minima_editor.hide()
        self._draw_minima_overlay_mpl()   # con edit_mode=False, limpia el overlay

    # ── Lista lateral ────────────────────────────────────────────────────
    def _populate_minima_list(self) -> None:
        """Reconstruye las filas de la lista a partir de ``_minima_entries``."""
        while self._minima_list_layout.count() > 1:
            item = self._minima_list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._minima_rows = []
        for k, e in enumerate(self._minima_entries):
            row = QtWidgets.QWidget()
            rl = QtWidgets.QHBoxLayout(row)
            rl.setContentsMargins(2, 0, 2, 0)
            rl.setSpacing(6)
            chk = QtWidgets.QCheckBox(f"v={e['pos']:+.3f}")
            chk.setChecked(bool(e["included"]))
            chk.setToolTip(tr("minima.include_tip", default="Usar este mínimo en la propuesta"))
            chk.toggled.connect(lambda state, idx=k: self._on_minima_row_changed(idx, included=state))
            spin = QtWidgets.QSpinBox()
            spin.setRange(1, 4)
            spin.setValue(int(e["count"]))
            spin.setPrefix("×")
            spin.setToolTip(tr("minima.count_tip", default="Nº de contribuciones bajo este mínimo"))
            spin.valueChanged.connect(lambda val, idx=k: self._on_minima_row_changed(idx, count=val))
            depth = QtWidgets.QLabel(f"{e['depth']*100:.1f}%")
            depth.setStyleSheet("color:#64748b;font-size:11px;")
            rl.addWidget(chk, stretch=1)
            rl.addWidget(depth)
            rl.addWidget(spin)
            self._minima_list_layout.insertWidget(self._minima_list_layout.count() - 1, row)
            self._minima_rows.append({"check": chk, "spin": spin})
        self._update_minima_count_label()

    def _on_minima_row_changed(self, idx: int, included: bool | None = None,
                               count: int | None = None) -> None:
        if idx < 0 or idx >= len(self._minima_entries):
            return
        if included is not None:
            self._minima_entries[idx]["included"] = bool(included)
        if count is not None:
            self._minima_entries[idx]["count"] = int(count)
        self._update_minima_count_label()
        self._draw_minima_overlay_mpl()

    def _update_minima_count_label(self) -> None:
        if not hasattr(self, "minima_count_label"):
            return
        n_inc = sum(1 for e in self._minima_entries if e["included"])
        n_contrib = sum(int(e["count"]) for e in self._minima_entries if e["included"])
        self.minima_count_label.setText(tr(
            "minima.count_summary",
            default="{inc}/{tot} mínimos · {contrib} contribuciones",
            inc=n_inc, tot=len(self._minima_entries), contrib=n_contrib))

    # ── Interacción sobre el canvas Matplotlib ───────────────────────────
    def _on_minima_canvas_click(self, event) -> None:
        """Clic sobre el canvas en modo edición → añade/alterna un mínimo."""
        if not getattr(self, "_minima_edit_mode", False):
            return
        if getattr(event, "inaxes", None) is not getattr(self.canvas, "ax", None):
            return
        if getattr(event, "xdata", None) is None:
            return
        if getattr(event, "button", 1) != 1:    # solo botón izquierdo
            return
        self._on_minima_plot_clicked(float(event.xdata))

    def _on_minima_marker_clicked(self, idx: int) -> None:
        """Alterna incluir/excluir el mínimo ``idx`` y sincroniza la lista."""
        if idx < 0 or idx >= len(self._minima_entries):
            return
        new_state = not self._minima_entries[idx]["included"]
        self._minima_entries[idx]["included"] = new_state
        if idx < len(self._minima_rows):
            chk = self._minima_rows[idx]["check"]
            chk.blockSignals(True)
            chk.setChecked(new_state)
            chk.blockSignals(False)
        self._update_minima_count_label()
        self._draw_minima_overlay_mpl()

    def _on_minima_plot_clicked(self, x: float) -> None:
        """Clic sobre el gráfico: alterna el mínimo cercano o añade uno nuevo."""
        if not getattr(self, "_minima_edit_mode", False):
            return
        if self.file.velocity is None or self.file.y_data is None:
            return
        v = np.asarray(self.file.velocity, dtype=float)
        y = np.asarray(self.file.y_data, dtype=float)
        if v.size == 0 or y.size == 0:
            return
        idx = int(np.argmin(np.abs(v - float(x))))
        # Si se clica sobre/cerca de un mínimo existente, alterna en vez de duplicar.
        if v.size > 1:
            dv = float(np.nanmedian(np.abs(np.diff(np.sort(v)))))
        else:
            dv = 0.05
        _pd = _eff_pd()
        tol = max(_pd["plotly_tol_factor"].default * abs(dv), _pd["plotly_tol_min"].default)
        if self._minima_entries:
            distances = [abs(float(e["pos"]) - float(x)) for e in self._minima_entries]
            nearest = int(np.argmin(distances))
            if distances[nearest] <= tol or abs(int(self._minima_entries[nearest]["i"]) - idx) <= 1:
                self._on_minima_marker_clicked(nearest)
                return
        calib_state = self.calib.to_view_state()
        baseline = float(getattr(self, "_minima_baseline", calib_state.baseline))
        slope = float(getattr(self, "_minima_slope", calib_state.slope))
        depth = max(0.0, baseline + slope * float(v[idx]) - float(y[idx]))
        self._minima_entries.append({
            "i": idx,
            "pos": float(v[idx]),
            "depth": depth,
            "width": 0.2,
            "smooth_depth": depth,
            "included": True,
            "count": 1,
        })
        self._minima_entries.sort(key=lambda e: float(e["pos"]))
        self._populate_minima_list()
        self._draw_minima_overlay_mpl()

    # ── Dibujo del overlay de marcadores ─────────────────────────────────
    def _refresh_minima_overlay(self) -> None:
        """Redibuja los marcadores si estamos en modo edición (no-op si no)."""
        if getattr(self, "_minima_edit_mode", False):
            self._draw_minima_overlay_mpl()

    def _draw_minima_overlay_mpl(self) -> None:
        """Dibuja los mínimos como marcadores clicables sobre el canvas.

        Los incluidos van resaltados (rojos rellenos); los excluidos, atenuados
        (huecos). La etiqueta ``×n`` indica multiplicidad > 1. Se eliminan los
        artistas del overlay anterior antes de redibujar.
        """
        canvas = getattr(self, "canvas", None)
        ax = getattr(canvas, "ax", None) if canvas is not None else None
        if ax is None:
            return
        for art in getattr(self, "_minima_artists", []):
            try:
                art.remove()
            except Exception:
                pass
        self._minima_artists = []
        if not getattr(self, "_minima_edit_mode", False) or not self._minima_entries:
            canvas.draw_idle()
            return
        if self.file.velocity is None or self.file.y_data is None:
            canvas.draw_idle()
            return
        v = np.asarray(self.file.velocity, dtype=float)
        y = np.asarray(self.file.y_data, dtype=float)
        if v.size == 0 or y.size == 0:
            canvas.draw_idle()
            return
        n = int(y.size)
        for included in (False, True):
            xs, ys, texts = [], [], []
            for e in self._minima_entries:
                if bool(e["included"]) is not included:
                    continue
                ch = int(e["i"])
                yv = float(y[ch]) if 0 <= ch < n else float(np.interp(e["pos"], v, y))
                xs.append(float(e["pos"]))
                ys.append(yv)
                texts.append(f"×{int(e['count'])}" if int(e["count"]) > 1 else "")
            if not xs:
                continue
            if included:
                sc = ax.scatter(xs, ys, s=95, c="#dc2626", marker="o",
                                edgecolors="white", linewidths=1.4, zorder=6)
            else:
                sc = ax.scatter(xs, ys, s=70, facecolors="none", edgecolors="#94a3b8",
                                linewidths=1.4, zorder=6)
            self._minima_artists.append(sc)
            for xx, yy, tt in zip(xs, ys, texts):
                if tt:
                    ann = ax.annotate(tt, (xx, yy), textcoords="offset points",
                                      xytext=(0, 9), ha="center", color="#dc2626",
                                      fontsize=9, zorder=7)
                    self._minima_artists.append(ann)
        canvas.draw_idle()

    # ── Propuesta de componentes a partir de los mínimos curados ─────────
    def on_propose_from_minima(self) -> None:
        included = [e for e in self._minima_entries if e["included"]]
        if not included:
            QtWidgets.QMessageBox.information(
                self, tr("minima.propose", default="Proponer ajuste"),
                tr("minima.none_selected", default="Marca al menos un mínimo."))
            return
        peaks_override = [
            {"i": float(e["i"]), "pos": e["pos"], "depth": e["depth"],
             "smooth_depth": e["smooth_depth"], "width": e["width"]}
            for e in included
        ]
        multiplicities = {int(e["i"]): int(e["count"]) for e in included}
        ok = self.on_init_from_minima(show_message=True, peaks_override=peaks_override,
                                      multiplicities=multiplicities)
        if ok:
            self._exit_minima_edit()
