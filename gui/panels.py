"""Paneles principales reutilizables de la GUI Qt."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from mossbauer_i18n import tr
from core.params import (
    COMPONENT_KINDS, COMPONENT_PARAM_LAYOUT, COMPONENT_PARAM_SPECS, USED_BY,
    component_default_value, relevant_params as _relevant_params,
)
from gui.controls import ParamControl
from core.result_views import discrete_result_view
from gui.state import CalibrationViewState, ComponentViewState


class CalibrationPanel(QtWidgets.QGroupBox):
    """Panel de calibración equivalente al de Tk.

    Incluye vmax/center/baseline/slope/σ-Voigt, las casillas de ajuste y el
    selector de modelo de absorbente con ``sat_scale``.
    """

    paramChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(tr("controls.calibration_box"), parent)
        v = QtWidgets.QVBoxLayout(self)
        v.setSpacing(2)

        self.vmax = ParamControl(tr("slider.vmax"), 12.007, -15.0, 15.0, 0.0001, 4, with_fixed=False)
        self.fit_velocity = QtWidgets.QCheckBox(tr("checkbox.fit_vmax"))
        self.center = ParamControl(tr("slider.center"), 256.5, 250.0, 263.0, 0.0001, 4, with_fixed=False)
        self.fit_center = QtWidgets.QCheckBox(tr("checkbox.fit_center"))
        self.baseline = ParamControl(tr("slider.baseline"), 1.0, 0.70, 1.30, 0.0005, 4)
        self.slope = ParamControl(tr("slider.slope"), 0.0, -0.002, 0.002, 1e-5, 6)
        self.voigt_sigma = ParamControl(tr("slider.voigt_sigma"), 0.05, 0.0, 1.0, 0.001, 4, with_fixed=False)
        self.line_profile = "Lorentziana"
        self.fit_sigma = QtWidgets.QCheckBox(tr("checkbox.fit_sigma"))

        # Menú contextual (clic derecho) del perfil de línea: solo sobre el
        # control de σ-Voigt (etiqueta, slider y spinbox). No aparece sobre el
        # resto de la caja de calibración ni sobre la casilla 'Ajustar σ'.
        for w in (self.voigt_sigma, self.voigt_sigma.label,
                  self.voigt_sigma.slider, self.voigt_sigma.spin):
            w.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            w.customContextMenuRequested.connect(self._show_sigma_menu)

        absorber_row = QtWidgets.QHBoxLayout()
        absorber_row.addWidget(QtWidgets.QLabel(tr("absorber.model_label")))
        self.absorber_combo = QtWidgets.QComboBox()
        for value, key in (("thin", "absorber.thin"), ("thickness", "absorber.thickness")):
            self.absorber_combo.addItem(tr(key), value)
        absorber_row.addWidget(self.absorber_combo, stretch=1)
        self.sat_scale = ParamControl(tr("slider.sat_scale"), 5.0, 0.05, 50.0, 0.01, 3)

        for w in (self.vmax, self.fit_velocity, self.center, self.fit_center,
                  self.baseline, self.slope, self.voigt_sigma, self.fit_sigma):
            v.addWidget(w)
        v.addLayout(absorber_row)
        v.addWidget(self.sat_scale)
        self._refresh_absorber_widgets()
        v.addStretch(1)

        for w in (self.vmax, self.center, self.baseline, self.slope, self.voigt_sigma, self.sat_scale):
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())
            w.fixedChanged.connect(lambda *_: self.paramChanged.emit())
        self.absorber_combo.currentIndexChanged.connect(lambda *_: (self._refresh_absorber_widgets(), self.paramChanged.emit()))
        for cb in (self.fit_velocity, self.fit_center, self.fit_sigma):
            cb.toggled.connect(lambda *_: self.paramChanged.emit())

    def _show_sigma_menu(self, pos: QtCore.QPoint) -> None:
        """Menú contextual sobre σ: cambiar perfil Lorentziana/Voigt + Ajustar σ."""
        menu = QtWidgets.QMenu(self)
        title = menu.addAction(tr("context.sigma_profile_title"))
        title.setEnabled(False)
        menu.addSeparator()
        for kind in ("Lorentziana", "Voigt"):
            act = menu.addAction(tr(f"options.profile_{'voigt' if kind == 'Voigt' else 'lorentzian'}"))
            act.setCheckable(True)
            act.setChecked(self.line_profile == kind)
            act.triggered.connect(lambda _checked=False, k=kind: self._set_line_profile(k))
        menu.addSeparator()
        act_fit_sigma = menu.addAction(tr("checkbox.fit_sigma"))
        act_fit_sigma.setCheckable(True)
        act_fit_sigma.setChecked(self.fit_sigma.isChecked())
        act_fit_sigma.setEnabled(self.line_profile == "Voigt")
        act_fit_sigma.triggered.connect(lambda checked: self.fit_sigma.setChecked(bool(checked)))
        sender = self.sender()
        anchor = sender if isinstance(sender, QtWidgets.QWidget) else self.voigt_sigma.spin
        menu.exec(anchor.mapToGlobal(pos))

    @property
    def absorber_model(self) -> str:
        return self.absorber_combo.currentData() or "thin"

    def set_absorber_model(self, model: str) -> None:
        idx = self.absorber_combo.findData(model)
        if idx >= 0:
            self.absorber_combo.setCurrentIndex(idx)
        self._refresh_absorber_widgets()

    def _refresh_absorber_widgets(self) -> None:
        self.sat_scale.setEnabled(self.absorber_model == "thickness")

    def to_view_state(self) -> CalibrationViewState:
        """Snapshot del panel sin exponer widgets al resto de la GUI."""
        return CalibrationViewState(
            vmax=self.vmax.value(),
            center=self.center.value(),
            baseline=self.baseline.value(),
            slope=self.slope.value(),
            voigt_sigma=self.voigt_sigma.value(),
            sat_scale=self.sat_scale.value(),
            line_profile=self.line_profile,
            absorber_model=self.absorber_model,
            fit_velocity=self.fit_velocity.isChecked(),
            fit_center=self.fit_center.isChecked(),
            fit_sigma=self.fit_sigma.isChecked(),
            fixed={
                "baseline": self.baseline.is_fixed(),
                "slope": self.slope.is_fixed(),
                "sat_scale": self.sat_scale.is_fixed(),
                "vmax": True,
                "center": True,
                "voigt_sigma": False,
            },
        )

    def _set_line_profile(self, kind: str) -> None:
        self.line_profile = kind
        self.voigt_sigma.spin.setEnabled(kind == "Voigt")
        self.fit_sigma.setEnabled(kind == "Voigt")
        if kind != "Voigt":
            self.fit_sigma.setChecked(False)
        self.paramChanged.emit()


class ComponentPanel(QtWidgets.QWidget):
    """10 parámetros + selector de tipo (Sextete/Doblete/Singlete) + 'activo'.

    Los parámetros que no aplican al tipo seleccionado se desactivan en gris.
    """

    paramChanged = QtCore.Signal()

    # Qué parámetros usa cada tipo (los demás se agrisan).
    # 'int3' es la intensidad de referencia (=1, oculta y siempre fija, igual
    # que en Tk): no se incluye aquí para que nunca se libere ni se ajuste.
    # Conjuntos por tipo: fuente única en core.params (compartida con core.session).
    _USED_BY = USED_BY

    def __init__(self, idx: int, parent=None):
        super().__init__(parent)
        self.idx = idx
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(2)

        # Cabecera: tipo + activo
        row = QtWidgets.QHBoxLayout()
        self.enabled = QtWidgets.QCheckBox(tr("component.enable", idx=idx))
        self.enabled.setChecked(idx == 1)
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(list(COMPONENT_KINDS))
        row.addWidget(self.enabled)
        row.addStretch(1)
        row.addWidget(QtWidgets.QLabel(tr("component.shape_label")))
        row.addWidget(self.type_combo)
        v.addLayout(row)

        # Orden y rangos de los controles: fuente única en core.params
        # (δ · ΔEQ · BHF · Γ1-Γ3 | profundidad · intensidades · textura · β).
        def _spec_rows(names):
            rows = []
            for name in names:
                s = COMPONENT_PARAM_SPECS[name]
                rows.append((name, tr(f"slider.s_{name}"),
                             component_default_value(name, idx),
                             s.lo, s.hi, s.step, s.decimals))
            return rows

        # Se crean TODOS los controles una sola vez; su colocación en el grid se
        # decide dinámicamente en _relayout_params según el tipo seleccionado, de
        # modo que aparezcan/desaparezcan sin dejar huecos.
        all_specs = (_spec_rows(COMPONENT_PARAM_LAYOUT["left"])
                     + _spec_rows(COMPONENT_PARAM_LAYOUT["right"])
                     + _spec_rows(COMPONENT_PARAM_LAYOUT["hidden"]))
        self.params: dict[str, ParamControl] = {}
        self.params_grid = QtWidgets.QGridLayout()
        self.params_grid.setContentsMargins(0, 0, 0, 0)
        self.params_grid.setHorizontalSpacing(10)
        self.params_grid.setVerticalSpacing(2)
        self.params_grid.setColumnStretch(0, 1)
        self.params_grid.setColumnStretch(1, 1)
        for name, label, val, lo, hi, step, dec in all_specs:
            ctl = ParamControl(label, val, lo, hi, step, dec)
            ctl.hide()
            self.params[name] = ctl
            ctl.valueChanged.connect(lambda *_: self.paramChanged.emit())
            ctl.fixedChanged.connect(lambda *_: self.paramChanged.emit())
        v.addLayout(self.params_grid)
        self.enabled.toggled.connect(lambda *_: self.paramChanged.emit())
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        # No se comprime: si los componentes apilados no caben, el QScrollArea
        # del panel izquierdo proporciona desplazamiento.
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

        # Estado para los menús contextuales (clic derecho). Ya no hay
        # desplegables: el modo de intensidades y el tratamiento del cuadrupolo
        # se eligen únicamente con el menú contextual, aligerando el panel.
        self.intensity_mode = "free"       # "free" / "texture"
        self.quad_treatment = "1st_order"  # 1st_order / kundig_fixed / kundig_powder

        # Clic derecho sobre intensidades y profundidad → menú Intensity mode
        # (free / textured), igual que el desplegable que sustituye.
        for k in ("int1", "int2", "texture", "depth"):
            ctl = self.params[k]
            for w in (ctl.spin, ctl.label, ctl.slider):
                w.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                w.customContextMenuRequested.connect(
                    lambda pos, c=ctl: self._show_intensity_menu(c, pos))
        self.params["texture"].valueChanged.connect(lambda *_: self._update_texture_intensities())

        # Clic derecho sobre quad → menú Quadrupole treatment
        # (1er orden / Kundig fijo / Kundig polvo).
        ctl_q = self.params["quad"]
        for w in (ctl_q.spin, ctl_q.label, ctl_q.slider):
            w.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            w.customContextMenuRequested.connect(
                lambda pos, c=ctl_q: self._show_quad_menu(c, pos))

        # Fijos típicos para α-Fe (intensidades + gammas relativas + quad).
        for k in ("int1", "int2", "int3", "gamma2", "gamma3", "quad", "texture"):
            self.params[k].set_fixed(True)
        v.addStretch(1)
        self._on_type_changed(self.type_combo.currentText())

    def _show_intensity_menu(self, ctl: "ParamControl", pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        title = menu.addAction(tr("context.intensity_mode_title"))
        title.setEnabled(False)
        menu.addSeparator()
        for val, key in (("free", "context.intensity_mode_free"),
                          ("texture", "context.intensity_mode_texture")):
            act = menu.addAction(tr(key))
            act.setCheckable(True)
            act.setChecked(self.intensity_mode == val)
            act.triggered.connect(lambda _c=False, v=val: self._set_intensity_mode(v))
        sender = self.sender()
        anchor = sender if isinstance(sender, QtWidgets.QWidget) else ctl.spin
        menu.exec(anchor.mapToGlobal(pos))

    def _set_intensity_mode(self, mode: str) -> None:
        if mode not in ("free", "texture"):
            return
        self.intensity_mode = mode
        # En modo textura, fija int1=3 / int2 (configurable via t implícito) /
        # int3=1 manteniéndolos como referencia 3:4t/(2-t):1 (t≈2/3 por defecto).
        if mode == "texture":
            self._update_texture_intensities()
            for k in ("int1", "int2", "int3"):
                self.params[k].set_fixed(True)
        self._on_type_changed(self.kind)
        self.paramChanged.emit()

    def _update_texture_intensities(self) -> None:
        if self.intensity_mode != "texture":
            return
        t = float(self.params["texture"].value())
        denom = max(2.0 - t, 1e-9)
        self.params["int1"].set_value(3.0)
        self.params["int2"].set_value(4.0 * t / denom)
        self.params["int3"].set_value(1.0)

    def _show_quad_menu(self, ctl: "ParamControl", pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        title = menu.addAction(tr("context.quad_treatment_title"))
        title.setEnabled(False)
        menu.addSeparator()
        for val, key in (
            ("1st_order", "context.quad_treatment_1st_order"),
            ("kundig_fixed", "context.quad_treatment_kundig_fixed"),
            ("kundig_powder", "context.quad_treatment_kundig_powder"),
        ):
            act = menu.addAction(tr(key))
            act.setCheckable(True)
            act.setChecked(self.quad_treatment == val)
            act.triggered.connect(lambda _c=False, v=val: self._set_quad_treatment(v))
        sender = self.sender()
        anchor = sender if isinstance(sender, QtWidgets.QWidget) else ctl.spin
        menu.exec(anchor.mapToGlobal(pos))

    def _set_quad_treatment(self, treatment: str) -> None:
        if treatment not in ("1st_order", "kundig_fixed", "kundig_powder"):
            return
        self.quad_treatment = treatment
        self._on_type_changed(self.kind)
        self.paramChanged.emit()

    @property
    def kind(self) -> str:
        return self.type_combo.currentText()

    def relevant_params(self) -> set[str]:
        """Parámetros realmente usados por el tipo y modo actuales (core.params)."""
        return _relevant_params(self.kind, self.intensity_mode, self.quad_treatment)

    def _on_type_changed(self, kind: str) -> None:
        prev = getattr(self, "_last_initialized_kind", None)
        if kind != prev:
            self._last_initialized_kind = kind
            if kind == "Doblete":
                self.params["int1"].set_value(1.0)
                self.params["int1"].set_fixed(True)
                self.params["int2"].set_value(1.0)
                self.params["int2"].set_fixed(True)
            elif kind == "Singlete":
                self.params["int1"].set_value(1.0)
                self.params["int1"].set_fixed(True)
            elif prev == "Doblete":
                self.params["int2"].set_value(2.0)
        self._relayout_params()
        self.paramChanged.emit()

    def _relayout_params(self) -> None:
        """Recoloca el grid mostrando solo los parámetros del tipo actual.

        Visibilidad = parámetros que pertenecen al tipo (``USED_BY[kind]``); así,
        p.ej., un componente Néel no muestra textura/β y un doblete no muestra
        BHF/Γ3. Los visibles se recolocan sin huecos respetando la separación de
        columnas (izquierda hiperfina · derecha intensidades/especializados) y se
        agrisan (``setEnabled``) los que no son ajustables en el modo actual.
        """
        used = self.relevant_params()
        shown = set(self._USED_BY.get(self.kind, set()))
        # Saca todo del grid (los widgets siguen vivos como hijos del panel).
        for ctl in self.params.values():
            self.params_grid.removeWidget(ctl)

        # Filtra los visibles para cada columna respetando el orden canónico.
        col0 = [n for n in COMPONENT_PARAM_LAYOUT["left"]  if n in shown]
        col1 = [n for n in COMPONENT_PARAM_LAYOUT["right"] if n in shown]

        # Reequilibra si una columna supera a la otra en más de 2 filas:
        # mueve el exceso desde el final de la columna más larga al final de
        # la más corta, manteniendo el orden relativo de cada param.
        while len(col1) > len(col0) + 2:
            col0.append(col1.pop(0))
        while len(col0) > len(col1) + 2:
            col1.append(col0.pop(0))

        for col, names in enumerate((col0, col1)):
            for row, name in enumerate(names):
                ctl = self.params[name]
                self.params_grid.addWidget(ctl, row, col)
                ctl.setVisible(True)
                ctl.setEnabled(name in used)

        # Oculta los no visibles ni ocultos.
        visible = set(col0) | set(col1)
        for name, ctl in self.params.items():
            if name not in visible:
                ctl.setVisible(False)

        # Etiqueta de int2 adaptada al tipo (I23 para sextetes, ratio para doblete).
        int2_ctl = self.params.get("int2")
        if int2_ctl is not None:
            if self.kind == "Doblete":
                int2_ctl.label.setText(tr("slider.s_int2_doblete"))
            else:
                int2_ctl.label.setText(tr("slider.s_int2"))

        # El grupo oculto (int3) nunca se muestra ni ocupa celda.
        for name in COMPONENT_PARAM_LAYOUT["hidden"]:
            ctl = self.params.get(name)
            if ctl is not None:
                ctl.setVisible(False)

    def to_view_state(self) -> ComponentViewState:
        """Snapshot del panel sin exponer widgets al resto de la GUI."""
        return ComponentViewState(
            idx=self.idx,
            enabled=self.enabled.isChecked(),
            kind=self.kind,
            intensity_mode=self.intensity_mode,
            quad_treatment=self.quad_treatment,
            values={k: ctl.value() for k, ctl in self.params.items()},
            fixed={k: ctl.is_fixed() for k, ctl in self.params.items()},
        )

    def values_dict(self) -> dict[str, float]:
        return self.to_view_state().prefixed_values()

    def fixed_dict(self) -> dict[str, bool]:
        return self.to_view_state().prefixed_fixed()

    def apply_values(self, values: dict[str, float]) -> None:
        for k, ctl in self.params.items():
            v = values.get(f"s{self.idx}_{k}")
            if v is not None:
                ctl.set_value(v)


class InfoPanel(QtWidgets.QGroupBox):
    """Panel de estado y parámetros, equivalente al resumen de la GUI Tk."""

    def __init__(self, parent=None):
        super().__init__(tr("controls.info_box"), parent)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        self.text = QtWidgets.QTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(120)
        self.text.setStyleSheet("QTextEdit { font-family: monospace; font-size: 10pt; }")
        v.addWidget(self.text)

    def set_lines(self, lines: list[str]) -> None:
        self.text.setPlainText("\n".join(lines) if lines else "—")

    def show_result(self, result) -> None:
        """Compatibilidad para llamadas antiguas: muestra sólo el ajuste."""
        lines = []
        view = discrete_result_view(result)
        s = view.stats_dict()
        if s:
            lines.append(
                f"χ²={s.get('chi2', float('nan')):.6g}   "
                f"χ²red={s.get('red_chi2', float('nan')):.4g}   "
                f"dof={int(s.get('dof', 0))}   "
                f"AIC={s.get('aic', float('nan')):.4g}   "
                f"BIC={s.get('bic', float('nan')):.4g}"
            )
            lines.append(f"arranques: {view.n_starts()}   params libres: {len(view.free_keys())}")
            lines.append("")
        if view.free_keys():
            for estimate in view.parameters(keys=view.free_keys()):
                val = estimate.value if estimate.value is not None else float("nan")
                err = estimate.error
                if err is not None and err > 0:
                    lines.append(f"  {estimate.key:14s} = {val:.6g}  ± {err:.3g}")
                else:
                    lines.append(f"  {estimate.key:14s} = {val:.6g}")
        corr = view.correlations()
        pairs = corr.get("high_pairs") or []
        if pairs:
            lines.append("")
            lines.append(tr("info.correlation_warning"))
            for p in pairs[:6]:
                lines.append(f"  {p['param1']} ↔ {p['param2']}: r={float(p['corr']):.3f}")
        self.set_lines(lines)
