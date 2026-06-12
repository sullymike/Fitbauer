"""Gestión de layout, presets, temas y ajustes persistentes de la GUI Qt."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from mossbauer_i18n import tr, available_languages, set_language
from core.data_io import SETTINGS_PATH
from core.plot_styles import apply_rc
from gui.state import UiPreferencesState
from gui.themes import COLOR_THEMES

MAX_QT_COMPONENTS = 6
_COMP_STACK_H = 300
_DIST_STACK_H = 340
_COMP_OVERHEAD_H = 120

# Claves i18n de los presets de layout integrados. La clave interna (que se
# guarda en settings.json) sigue siendo en español; aquí solo se traduce el
# texto mostrado en el diálogo de configuración.
_PRESET_TR = {
    "Estándar":      "layout.preset.standard",
    "Tres columnas": "layout.preset.three_columns",
    "Análisis":      "layout.preset.analysis",
    "Compacto":      "layout.preset.compact",
}


def _tr_preset_name(name: str) -> str:
    key = _PRESET_TR.get(name)
    return tr(key, default=name) if key else name


def _tr_preset_desc(name: str, fallback: str = "") -> str:
    key = _PRESET_TR.get(name)
    return tr(f"{key}.desc", default=fallback) if key else fallback


class LayoutSettingsMixin:
    def _all_presets(self) -> dict[str, dict]:
        """Combina presets Tk + customs del usuario."""
        try:
            from layout.presets import PRESETS
        except Exception:
            PRESETS = {}
        out: dict[str, dict] = dict(PRESETS)
        for name, spec in self.custom_layouts.items():
            out[name] = spec
        return out

    def _insert_panel_widget(self, layout: QtWidgets.QVBoxLayout, widget: QtWidgets.QWidget) -> None:
        """Inserta un panel antes del stretch final de una columna, si existe."""
        widget.setParent(None)
        pos = layout.count()
        if pos and layout.itemAt(pos - 1).spacerItem() is not None:
            pos -= 1
        layout.insertWidget(pos, widget)
        widget.show()

    def _collect_layout_spec(self, columns: dict[str, list[str]],
                             left_width: int, right_width: int,
                             description: str = "Custom") -> dict:
        known = set(getattr(self, "_layout_panel_widgets", {}))
        out = {
            "description": description,
            "left": [pid for pid in columns.get("left", []) if pid in known],
            "center": [pid for pid in columns.get("center", []) if pid in known],
            "right": [pid for pid in columns.get("right", []) if pid in known],
            "left_width": int(left_width),
            "right_width": int(right_width),
        }
        # Los paneles no asignados a ninguna columna quedan "apartados" (no se
        # muestran), igual que el pool de Disponibles del configurador Tk.
        return out

    def _apply_panel_layout(self, spec: dict) -> None:
        if not hasattr(self, "_layout_panel_widgets"):
            return
        right_w = int(spec.get("right_width", 0))
        columns = {
            "left": list(spec.get("left", [])),
            "center": list(spec.get("center", [])),
            "right": list(spec.get("right", [])),
        }
        # Los paneles que no estén en ninguna columna quedan apartados: se
        # ocultan (equivalente al pool 'Disponibles' del configurador Tk).
        assigned = set(columns["left"]) | set(columns["center"]) | set(columns["right"])
        for pid, widget in self._layout_panel_widgets.items():
            if pid not in assigned:
                widget.setParent(None)
                widget.hide()
        for pid in columns["left"]:
            if pid in self._layout_panel_widgets:
                self._insert_panel_widget(self._left_panels_layout,
                                          self._layout_panel_widgets[pid])
        for pid in columns["center"]:
            if pid in self._layout_panel_widgets:
                self._insert_panel_widget(self._center_top_layout,
                                          self._layout_panel_widgets[pid])
        right_target = (self._right_panels_layout if right_w > 0
                        else self._center_bottom_layout)
        for pid in columns["right"]:
            if pid in self._layout_panel_widgets:
                self._insert_panel_widget(right_target, self._layout_panel_widgets[pid])
        self._center_top_widget.setVisible(bool(columns["center"]))
        self._center_bottom_widget.setVisible(right_w == 0 and bool(columns["right"]))

        # Igual que el panel Tk modular (_force_tabs en la columna central):
        # si la simulación queda en el centro o anclada debajo del gráfico (poca
        # altura), se fuerzan pestañas; el apilado adaptativo solo se permite en
        # una columna lateral (izquierda o derecha con anchura propia).
        sim_in_center = "sim_controls" in columns["center"]
        sim_below_graph = (right_w == 0 and "sim_controls" in columns["right"])
        self._sim_force_tabs = bool(sim_in_center or sim_below_graph)
        self._check_layout()

    def _layout_preset_with_available_space(self, name: str) -> str:
        """Coloca la simulación a la derecha si no cabe bien debajo del gráfico."""
        if name == "Estándar":
            screen = QtGui.QGuiApplication.primaryScreen()
            width = screen.availableGeometry().width() if screen is not None else self.width()
            if width >= 1450:
                return "Tres columnas"
        return name

    def _apply_layout_preset(self, name: str) -> None:
        """Aplica preset al QSplitter principal usando 3 columnas."""
        spec = self._all_presets().get(name, {})
        self._apply_panel_layout(spec)
        left_w = int(spec.get("left_width", 430))
        right_w = int(spec.get("right_width", 0))
        total_w = max(900, self.width() - 20)
        center_w = max(500, total_w - left_w - right_w)
        sizes = [left_w, center_w, max(0, right_w)]
        if hasattr(self, "_left_scroll"):
            self._left_scroll.setMinimumWidth(left_w)
            self._left_scroll.setMaximumWidth(left_w)
        if hasattr(self, "_right_column"):
            self._right_column.setVisible(right_w > 0)
            self._right_column.setMinimumWidth(right_w if right_w > 0 else 0)
            self._right_column.setMaximumWidth(right_w if right_w > 0 else 0)
        if hasattr(self, "_main_splitter"):
            self._main_splitter.setSizes(sizes)
        self.layout_preset = name
        self._save_settings()

    def on_configure_layout(self) -> None:
        """Editor visual de presets con columnas Izquierda | Centro | Derecha."""
        try:
            from layout.presets import PRESETS, DEFAULT_PRESET
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, tr("view.configure_layout"),
                f"layout.presets no disponible: {exc}")
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("view.configure_layout"))
        dlg.resize(980, 640)
        v = QtWidgets.QVBoxLayout(dlg)
        v.addWidget(QtWidgets.QLabel(
            "<i>Choose a preset or move panels between <b>Available</b> and the "
            "<b>3 columns</b>. Panels left in <b>Available</b> are hidden. "
            "The right column with width 0 is hidden and its panels anchor below the plot.</i>"))

        list_w = QtWidgets.QListWidget()
        v.addWidget(list_w, stretch=1)

        left_width_spin = QtWidgets.QSpinBox()
        left_width_spin.setRange(200, 900); left_width_spin.setSuffix("  px left")
        right_width_spin = QtWidgets.QSpinBox()
        right_width_spin.setRange(0, 900); right_width_spin.setSuffix("  px right")

        panel_names = dict(getattr(self, "_layout_panel_names", {}))
        panel_lists: dict[str, QtWidgets.QListWidget] = {}

        def clear_selection_except(active: QtWidgets.QListWidget) -> None:
            for lw_col in panel_lists.values():
                if lw_col is not active:
                    lw_col.clearSelection()

        def selected_column() -> tuple[str, QtWidgets.QListWidget] | tuple[None, None]:
            for key, lw_col in panel_lists.items():
                if lw_col.currentItem() is not None:
                    return key, lw_col
            return None, None

        def columns_from_lists() -> dict[str, list[str]]:
            return {
                key: [lw_col.item(i).data(QtCore.Qt.UserRole)
                      for i in range(lw_col.count())]
                for key, lw_col in panel_lists.items()
            }

        def fill_columns(spec: dict) -> None:
            for lw_col in panel_lists.values():
                lw_col.clear()
            used: set[str] = set()
            for key in ("left", "center", "right"):
                for pid in spec.get(key, []):
                    if pid in panel_names and pid not in used:
                        item = QtWidgets.QListWidgetItem(panel_names.get(pid, pid))
                        item.setData(QtCore.Qt.UserRole, pid)
                        panel_lists[key].addItem(item)
                        used.add(pid)
            for pid, label in panel_names.items():
                if pid not in used:
                    item = QtWidgets.QListWidgetItem(label)
                    item.setData(QtCore.Qt.UserRole, pid)
                    panel_lists["available"].addItem(item)
            left_width_spin.setValue(int(spec.get("left_width", 430)))
            right_width_spin.setValue(int(spec.get("right_width", 0)))

        def current_spec(description: str = "Custom") -> dict:
            return self._collect_layout_spec(
                columns_from_lists(), left_width_spin.value(), right_width_spin.value(),
                description=description,
            )

        def refresh_list(select_name: str | None = None) -> None:
            list_w.clear()
            all_presets = self._all_presets()
            for name, spec in all_presets.items():
                is_custom = name in self.custom_layouts
                kind = "(custom)" if is_custom else "(built-in)"
                lw = spec.get("left_width", "—")
                rw = spec.get("right_width", "—")
                disp_name = name if is_custom else _tr_preset_name(name)
                desc = (spec.get("description", "") if is_custom
                        else _tr_preset_desc(name, spec.get("description", "")))
                txt = (f"{disp_name}  {kind}  ·  left={lw}px  ·  "
                       f"right={rw}px  ·  {desc}")
                item = QtWidgets.QListWidgetItem(txt)
                item.setData(QtCore.Qt.UserRole, name)
                list_w.addItem(item)
                target = select_name or (self.layout_preset if self.layout_preset in all_presets else DEFAULT_PRESET)
                if name == target:
                    list_w.setCurrentItem(item)

        # Editor visual de columnas.
        edit_box = QtWidgets.QGroupBox("Column editor")
        edit_v = QtWidgets.QVBoxLayout(edit_box)
        edit_row = QtWidgets.QHBoxLayout()
        for key, title in (("available", "Available (unassigned)"),
                           ("left", "Left"), ("center", "Center"),
                           ("right", "Right")):
            col = QtWidgets.QVBoxLayout()
            col.addWidget(QtWidgets.QLabel(f"<b>{title}</b>"))
            lw_col = QtWidgets.QListWidget()
            lw_col.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            lw_col.currentItemChanged.connect(lambda _cur, _prev, lw=lw_col: clear_selection_except(lw))
            col.addWidget(lw_col)
            edit_row.addLayout(col)
            panel_lists[key] = lw_col
        edit_v.addLayout(edit_row)

        move_row = QtWidgets.QHBoxLayout()
        for key, label in (("available", "Set aside"),
                           ("left", "Move to left"),
                           ("center", "Move to center"),
                           ("right", "Move to right")):
            btn = QtWidgets.QPushButton(label)
            def _move(_=False, target=key):
                _src_key, src = selected_column()
                if src is None:
                    return
                item = src.takeItem(src.currentRow())
                panel_lists[target].addItem(item)
                panel_lists[target].setCurrentItem(item)
            btn.clicked.connect(_move)
            move_row.addWidget(btn)
        btn_up = QtWidgets.QPushButton("Up")
        btn_down = QtWidgets.QPushButton("Down")
        def _reorder(delta: int) -> None:
            _key, lw_col = selected_column()
            if lw_col is None:
                return
            row = lw_col.currentRow()
            new_row = row + delta
            if new_row < 0 or new_row >= lw_col.count():
                return
            item = lw_col.takeItem(row)
            lw_col.insertItem(new_row, item)
            lw_col.setCurrentItem(item)
        btn_up.clicked.connect(lambda: _reorder(-1))
        btn_down.clicked.connect(lambda: _reorder(+1))
        move_row.addWidget(btn_up); move_row.addWidget(btn_down)
        edit_v.addLayout(move_row)

        width_row = QtWidgets.QHBoxLayout()
        width_row.addWidget(QtWidgets.QLabel("Widths:"))
        width_row.addWidget(left_width_spin)
        width_row.addWidget(right_width_spin)
        width_row.addStretch(1)
        edit_v.addLayout(width_row)
        v.addWidget(edit_box, stretch=2)

        def on_preset_changed(item: QtWidgets.QListWidgetItem | None) -> None:
            if item is None:
                return
            spec = self._all_presets().get(item.data(QtCore.Qt.UserRole), {})
            fill_columns(spec)

        list_w.currentItemChanged.connect(lambda cur, _prev: on_preset_changed(cur))
        refresh_list()
        on_preset_changed(list_w.currentItem())

        # Guardar el diseño visual actual en Custom 1 / Custom 2.
        for slot in ("Custom 1", "Custom 2"):
            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel(f"<b>{slot}</b>:"))
            desc_e = QtWidgets.QLineEdit(
                self.custom_layouts.get(slot, {}).get(
                    "description", "User custom"))
            row.addWidget(desc_e, stretch=1)
            btn = QtWidgets.QPushButton("Save current layout")
            def _save(_=False, _slot=slot, _desc=desc_e):
                self.custom_layouts[_slot] = current_spec(
                    _desc.text().strip() or "Custom")
                self._save_settings()
                refresh_list(_slot)
            btn.clicked.connect(_save)
            row.addWidget(btn)
            v.addLayout(row)

        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        item = list_w.currentItem()
        if item is None:
            return
        name = item.data(QtCore.Qt.UserRole)
        shown = current_spec(self._all_presets().get(name, {}).get("description", "Custom"))
        selected = self._all_presets().get(name, {})
        comparable = {k: selected.get(k, [] if k in ("left", "center", "right") else 0)
                      for k in ("left", "center", "right", "left_width", "right_width")}
        shown_comp = {k: shown.get(k) for k in comparable}
        if shown_comp != comparable:
            name = name if name in self.custom_layouts else "Custom 1"
            shown["description"] = shown.get("description") or "Custom"
            self.custom_layouts[name] = shown
            self._save_settings()
        self._apply_layout_preset(name)

    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.clear()
        if not self.recent_files:
            act = QtGui.QAction("(vacío)", self); act.setEnabled(False)
            self.recent_menu.addAction(act); return
        for p in self.recent_files:
            act = QtGui.QAction(Path(p).name, self)
            act.setStatusTip(p)
            act.triggered.connect(lambda _checked=False, path=p: self._open_recent(path))
            self.recent_menu.addAction(act)

    def _open_recent(self, path: str) -> None:
        try:
            self._load_file(Path(path))
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, tr("file.open"), str(exc))

    def _add_recent(self, path: Path) -> None:
        s = str(path.resolve())
        if s in self.recent_files:
            self.recent_files.remove(s)
        self.recent_files.insert(0, s)
        self.recent_files = self.recent_files[:5]
        self._rebuild_recent_menu()
        self._save_settings()

    def _set_qt_style(self, style_name: str) -> None:
        try:
            QtWidgets.QApplication.instance().setStyle(style_name)
        except Exception:
            return
        self.qt_style = style_name
        try:
            import json
            current = {}
            if SETTINGS_PATH.exists():
                current = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            current["qt_style"] = style_name
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _set_plot_style(self, name: str) -> None:
        self.plot_style_name = name
        apply_rc(name)
        self._save_settings()
        self._refresh_plot()

    def _apply_color_theme(self, name: str, persist: bool = True) -> None:
        """Aplica un tema de color (paleta + acentos) a toda la interfaz."""
        if name not in COLOR_THEMES:
            name = "blue"
        self.color_theme = name
        theme = COLOR_THEMES[name]
        app = QtWidgets.QApplication.instance()

        if name == "system":
            # Aspecto nativo: paleta estándar del estilo y sin hoja de estilos.
            if app is not None:
                app.setPalette(QtWidgets.QApplication.style().standardPalette())
            self.setStyleSheet("")
            accent, accent_text, accent_sub, title = "#075985", "#ffffff", "#dff6ff", "#075985"
        else:
            def c(h: str) -> QtGui.QColor:
                return QtGui.QColor(h)
            pal = QtGui.QPalette()
            pal.setColor(QtGui.QPalette.Window, c(theme["window"]))
            pal.setColor(QtGui.QPalette.WindowText, c(theme["text"]))
            pal.setColor(QtGui.QPalette.Base, c(theme["base"]))
            pal.setColor(QtGui.QPalette.AlternateBase, c(theme["alt_base"]))
            pal.setColor(QtGui.QPalette.Text, c(theme["text"]))
            pal.setColor(QtGui.QPalette.Button, c(theme["button"]))
            pal.setColor(QtGui.QPalette.ButtonText, c(theme["button_text"]))
            pal.setColor(QtGui.QPalette.Highlight, c(theme["highlight"]))
            pal.setColor(QtGui.QPalette.HighlightedText, c(theme["highlight_text"]))
            pal.setColor(QtGui.QPalette.ToolTipBase, c(theme["base"]))
            pal.setColor(QtGui.QPalette.ToolTipText, c(theme["text"]))
            # Grupo "Disabled": los campos no modificables se ven claramente
            # apagados (antes no se distinguían de los editables).
            dis_text = c(theme.get("disabled_text", "#9aa0a6"))
            dis_base = c(theme.get("disabled_base", theme["window"]))
            for role in (QtGui.QPalette.WindowText, QtGui.QPalette.Text,
                         QtGui.QPalette.ButtonText):
                pal.setColor(QtGui.QPalette.Disabled, role, dis_text)
            pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Base, dis_base)
            pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Button, dis_base)
            pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Highlight, dis_base)
            if app is not None:
                app.setPalette(pal)
            accent = theme["accent"]; accent_text = theme["accent_text"]
            accent_sub = theme["accent_sub"]; title = theme["title"]
            dt = theme.get("disabled_text", "#9aa0a6")
            db = theme.get("disabled_base", theme["window"])
            # Refuerzo por hoja de estilos: con stylesheet activa, Qt no aplica
            # el grupo Disabled de la paleta a algunos widgets, así que se
            # explicita el aspecto de los campos deshabilitados.
            self.setStyleSheet(
                "QGroupBox { font-weight: 600; margin-top: 6px; }"
                f"QGroupBox::title {{ color: {title}; subcontrol-origin: margin; left: 8px; }}"
                f"QDoubleSpinBox:disabled, QSpinBox:disabled, QLineEdit:disabled, "
                f"QComboBox:disabled {{ color: {dt}; background: {db}; }}"
                f"QLabel:disabled, QCheckBox:disabled, QRadioButton:disabled {{ color: {dt}; }}"
                f"QSlider:disabled {{ background: transparent; }}"
            )

        # La cabecera siempre con su banner de acento, acorde al tema.
        if hasattr(self, "header_box"):
            self.header_box.setStyleSheet(
                f"#AppHeader {{ background: {accent}; border-radius: 4px; }}"
                f"#AppHeader QLabel {{ background: transparent; color: {accent_sub}; font-size: 9pt; }}"
                f"#AppHeaderTitle {{ color: {accent_text}; font-size: 16pt; font-weight: bold; }}"
            )
        if persist:
            self._save_settings()

    # ── Preferencias de interfaz ─────────────────────────────────────────
    def _ui_preferences_state(self) -> UiPreferencesState:
        """Snapshot formal de preferencias no científicas de la GUI."""
        ui_state = self._ui_action_state()
        return UiPreferencesState(
            plot_style=self.plot_style_name,
            color_theme=self.color_theme,
            custom_shortcuts=dict(getattr(self, "_custom_shortcuts", {})),
            show_residual=ui_state.show_residual,
            recent_files=tuple(self.recent_files),
            layout_preset=self.layout_preset,
            custom_layouts=dict(self.custom_layouts),
            qt_style=getattr(self, "qt_style", None),
            multistart_n=getattr(self, "multistart_n", 8),
        )

    def _apply_ui_preferences_state(self, prefs: UiPreferencesState) -> None:
        if prefs.plot_style in ("classic", "modern", "publication", "dark"):
            self.plot_style_name = prefs.plot_style
        if prefs.ui_language and prefs.ui_language in available_languages():
            set_language(prefs.ui_language)
        self.recent_files = [p for p in prefs.recent_files if Path(p).exists()][:5]
        if prefs.color_theme in COLOR_THEMES:
            self.color_theme = prefs.color_theme
        self._show_residual_pref = bool(prefs.show_residual)
        if prefs.layout_preset:
            self.layout_preset = prefs.layout_preset
        self.custom_layouts = {
            str(k): v for k, v in prefs.custom_layouts.items()
            if isinstance(v, dict) and "left_width" in v
        }
        if prefs.qt_style:
            self.qt_style = prefs.qt_style
        if prefs.custom_shortcuts:
            self._custom_shortcuts = dict(prefs.custom_shortcuts)
            if hasattr(self, "_action_registry") and self._action_registry:
                self._apply_custom_shortcuts(prefs.custom_shortcuts)
        self.multistart_n = int(prefs.multistart_n)
        spin = getattr(self, "_multistart_spin", None)
        if spin is not None:
            spin.blockSignals(True)
            spin.setValue(self.multistart_n)
            spin.blockSignals(False)

    # ── Persistencia mínima ──────────────────────────────────────────────
    def _load_settings(self) -> None:
        try:
            if SETTINGS_PATH.exists():
                data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                self._apply_ui_preferences_state(
                    UiPreferencesState.from_settings_dict(data)
                )
        except Exception:
            pass

    def _save_settings(self) -> None:
        try:
            current = {}
            if SETTINGS_PATH.exists():
                try:
                    current = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                except Exception:
                    current = {}
            current = self._ui_preferences_state().to_settings_dict(base=current)
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps(current, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception:
            pass

    # ── Número de componentes ────────────────────────────────────────────
    def _on_n_components_changed(self, n_components: int) -> None:
        self._sync_component_count(n_components)
        self._check_layout()
        self._refresh_plot()

    def _component_visibility(self, n_components: int) -> tuple[bool, list[bool]]:
        """(is_dist, [visible_i…]) para los MAX componentes.

        En modo distribución los sextetes solo se muestran si está marcado
        'sumar componentes nítidas' (dist_use_sharp), igual que en Tk: sin
        nítidas, no aparecen los sextetes.
        """
        is_dist = self.is_distribution_mode if hasattr(self, "mode_combo") else False
        show_components = (not is_dist) or bool(getattr(self, "dist_use_sharp", False))
        vis = [(i <= n_components) and show_components
               for i in range(1, MAX_QT_COMPONENTS + 1)]
        return is_dist, vis

    def _sync_component_count(self, n_components: int) -> None:
        n_components = max(1, min(MAX_QT_COMPONENTS, int(n_components)))
        current_n = self._ui_action_state().n_components if hasattr(self, "n_components_spin") else n_components
        if hasattr(self, "n_components_spin") and current_n != n_components:
            self.n_components_spin.blockSignals(True)
            self.n_components_spin.setValue(n_components)
            self.n_components_spin.blockSignals(False)

        is_dist, vis = self._component_visibility(n_components)
        # El estado 'activo' refleja el número de componentes elegido, aunque el
        # panel esté oculto (en distribución sin nítidas se ocultan pero
        # conservan su estado para cuando se reactiven).
        for i, cp in enumerate(self.components_panels, start=1):
            cp.enabled.blockSignals(True)
            cp.enabled.setChecked(i <= n_components)
            cp.enabled.blockSignals(False)

        if self._using_tabs:
            self.comp_tabs.setTabVisible(0, is_dist)
            for i in range(1, MAX_QT_COMPONENTS + 1):
                self.comp_tabs.setTabVisible(i, vis[i - 1])
            # Al entrar en distribución se selecciona la pestaña de distribución
            # (índice 0); en discreto, la primera componente.
            self.comp_tabs.setCurrentIndex(0 if is_dist else 1)
        else:
            self.dist_panel.setVisible(is_dist)
            for i in range(1, MAX_QT_COMPONENTS + 1):
                frame = self._comp_stack_frames.get(i)
                if frame is not None:
                    frame.setVisible(vis[i - 1])

    def _rebuild_component_area(self, use_tabs: bool) -> None:
        """Reconstruye el área de componentes en modo pestañas o apilado.

        Reutiliza los mismos paneles (conservan su estado) reparentándolos
        entre el QTabWidget y el contenedor apilado.
        """
        if use_tabs == self._using_tabs:
            return
        # Saca todos los paneles de su contenedor actual.
        self.dist_panel.setParent(None)
        for cp in self.components_panels:
            cp.setParent(None)
        # Vacía el QTabWidget.
        while self.comp_tabs.count():
            self.comp_tabs.removeTab(0)
        # Vacía el layout apilado (descarta las envolturas tituladas).
        while self._comp_stack_layout.count():
            item = self._comp_stack_layout.takeAt(0)
            w = item.widget()
            if w is not None and w is not self.dist_panel:
                w.setParent(None)
                w.deleteLater()
        self._comp_stack_frames.clear()

        if use_tabs:
            self.comp_tabs.addTab(self.dist_panel, tr("tab.distribution_bhf"))
            for i, cp in enumerate(self.components_panels, start=1):
                self.comp_tabs.addTab(cp, tr("tab.component", idx=i))
            self.comp_tabs.setVisible(True)
            self.comp_stack.setVisible(False)
        else:
            self._comp_stack_layout.addWidget(self.dist_panel)
            for i, cp in enumerate(self.components_panels, start=1):
                box = QtWidgets.QGroupBox(tr("tab.component", idx=i))
                bl = QtWidgets.QVBoxLayout(box)
                bl.setContentsMargins(4, 4, 4, 4)
                bl.setSpacing(2)
                bl.addWidget(cp)
                cp.setVisible(True)
                self._comp_stack_frames[i] = box
                self._comp_stack_layout.addWidget(box)
            self._comp_stack_layout.addStretch(1)
            self.comp_tabs.setVisible(False)
            self.comp_stack.setVisible(True)

        self._using_tabs = use_tabs
        self._sync_component_count(self._ui_action_state().n_components)

    def _check_layout(self) -> None:
        """Cambia entre apilado y pestañas según el espacio vertical disponible.

        Replica el comportamiento del panel Tk modular: apilado cuando cabe,
        pestañas cuando no. La histéresis (0.78 / 0.88) evita oscilaciones.
        """
        if getattr(self, "_using_tabs", None) is None or not hasattr(self, "n_components_spin"):
            return
        if getattr(self, "_in_layout_check", False):
            return
        # Si la simulación está en el centro o debajo del gráfico, siempre
        # pestañas (no hay altura para apilar sin recortar).
        if getattr(self, "_sim_force_tabs", False):
            if not self._using_tabs:
                self._in_layout_check = True
                try:
                    self._rebuild_component_area(use_tabs=True)
                finally:
                    self._in_layout_check = False
            return
        win_h = self.height()
        if win_h < 100:
            return
        ui_state = self._ui_action_state()
        is_dist, vis = self._component_visibility(ui_state.n_components)
        # Mide siempre la altura real de los paneles (SizePolicy.Fixed →
        # sizeHint es fiable independientemente del contenedor actual).
        # Así los umbrales tabs→apilado y apilado→tabs usan la misma métrica
        # y no oscilan cuando hay tipos con muchos parámetros (p.ej. NeelSize).
        if hasattr(self, "components_panels"):
            comp_h = sum(
                cp.sizeHint().height() + 4
                for cp, v in zip(self.components_panels, vis) if v
            )
        else:
            n_visible = sum(1 for v in vis if v)
            comp_h = n_visible * _COMP_STACK_H
        stacked_h = (_COMP_OVERHEAD_H + (_DIST_STACK_H if is_dist else 0) + comp_h)
        self._in_layout_check = True
        try:
            if self._using_tabs:
                if stacked_h < win_h * 0.78:
                    self._rebuild_component_area(use_tabs=False)
            else:
                if stacked_h > win_h * 0.88:
                    self._rebuild_component_area(use_tabs=True)
        finally:
            self._in_layout_check = False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._check_layout()
