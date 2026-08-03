"""Paneles principales reutilizables de la GUI Qt."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from mossbauer_i18n import tr
from dataclasses import astuple

from core.params import (
    COMPONENT_KINDS, COMPONENT_PARAM_LAYOUT, INTENSITY_MODES, QUAD_TREATMENTS, USED_BY,
    component_default_value, relevant_params as _relevant_params,
)
from core.param_overrides import effective_calibration_specs, effective_component_specs
from gui.controls import ParamControl
from core.result_views import discrete_result_view
from gui.state import CalibrationViewState, ComponentViewState


#: Parámetros con menú contextual (clic derecho) y la clave que dice qué
#: ofrece. Sin esta pista el menú es invisible: nadie prueba el clic derecho
#: sobre una casilla numérica si nada lo insinúa.
CONTEXT_HINTS = {
    "quad": "tooltip.more_quad",
    "int1": "tooltip.more_intensity",
    "int2": "tooltip.more_intensity",
    "depth": "tooltip.more_intensity",
    "texture": "tooltip.more_intensity",
}


#: Capítulo de la ayuda al que lleva «Más información» de cada parámetro.
#: El formato es "grupo.posición_en_el_grupo": los ocho catálogos no ordenan
#: los capítulos igual, pero sí coinciden en cuántos tiene cada grupo y en su
#: orden interno (lo fija un test).
PARAM_HELP_CHAPTER = {
    # Modelo discreto (fitting.1)
    **{k: "fitting.1" for k in (
        "delta", "quad", "bhf", "gamma1", "gamma2", "gamma3", "depth",
        "int1", "int2", "texture", "beta", "eta", "phi", "bex", "gax")},
    # Relajación magnética (fitting.2)
    **{k: "fitting.2" for k in (
        "relax_fraction", "relax_log_nu", "relax_polarization")},
    # Ajuste global Néel-Arrhenius (fitting.3)
    **{k: "fitting.3" for k in (
        "neel_temp_k", "neel_log10_keff", "neel_mean_d_nm", "neel_sigma",
        "neel_log10_tau0", "neel_bins")},
}

#: Ídem para los parámetros de calibración.
CALIB_HELP_CHAPTER = {
    # Folding, velocidad y fondo (files.3)
    **{k: "files.3" for k in (
        "vmax", "center", "baseline", "slope", "curv", "curv3", "curv4")},
    "voigt_sigma": "fitting.4",   # Perfil de línea
    "sat_scale": "fitting.0",     # Menú Ajuste (opciones de absorbente)
    "src_fwhm": "fitting.0",
}


def _nombre_de(params: dict, ctl) -> str:
    """Nombre del parámetro cuyo control es ``ctl`` (para elegir capítulo)."""
    for nombre, c in params.items():
        if c is ctl:
            return nombre
    return ""


def add_help_entry(menu, panel, chapter: str) -> None:
    """Añade «Más información» al menú, si hay capítulo al que llevar.

    El enlace no puede ir DENTRO del globo: Qt lo cierra en cuanto el ratón
    sale del control, así que un ``<a href>`` ahí sería inalcanzable. Por eso
    el globo solo anuncia que hay más y el enlace vive en el menú del clic
    derecho, que sí se puede pulsar.
    """
    if not chapter:
        return
    ventana = panel.window()
    if not hasattr(ventana, "on_help"):
        return
    menu.addSeparator()
    act = menu.addAction(tr("context.more_help", default="Más información…"))
    act.triggered.connect(
        lambda _checked=False, c=chapter: ventana.on_help(chapter=c))


def attach_help_menu(panel, ctl, chapter: str) -> None:
    """Da menú contextual de solo «Más información» a un control sin menú propio.

    Los que ya tienen menú (ΔEQ, intensidades, σ) reciben la entrada al final
    del suyo; el resto la necesitan aquí o no habría forma de llegar a la
    ayuda desde el parámetro.
    """
    if not chapter:
        return

    def _menu(pos, _ctl=ctl, _cap=chapter):
        menu = QtWidgets.QMenu(panel)
        add_help_entry(menu, panel, _cap)
        if menu.isEmpty():
            return
        emisor = panel.sender()
        anclaje = emisor if isinstance(emisor, QtWidgets.QWidget) else _ctl.spin
        menu.exec(anclaje.mapToGlobal(pos))

    for w in (ctl, ctl.label, ctl.spin, ctl.slider):
        w.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        w.customContextMenuRequested.connect(_menu)


def param_tooltip(name: str, prefijo: str = "p") -> str:
    """Texto del globo de ayuda de un parámetro, con su pista de menú.

    ``prefijo`` es ``p`` para los parámetros de componente y ``c`` para los de
    calibración. Las claves viven en ``locales/<idioma>/strings.json``; si
    faltara alguna, ``tr`` cae al idioma por defecto, así que las traducciones
    tienen que estar completas en los ocho idiomas o el globo saldría en
    español a quien no lo lee.
    """
    texto = tr(f"tooltip.{prefijo}_{name}", default="")
    pista = CONTEXT_HINTS.get(name)
    if pista:
        extra = tr(pista, default="")
        if extra:
            texto = f"{texto}\n\n{extra}" if texto else extra
    mapa = PARAM_HELP_CHAPTER if prefijo == "p" else CALIB_HELP_CHAPTER
    if name in mapa:
        mas = tr("tooltip.more_help", default="")
        if mas:
            texto = f"{texto}\n\n{mas}" if texto else mas
    return texto


class CalibrationPanel(QtWidgets.QGroupBox):
    """Panel de calibración equivalente al de Tk.

    Incluye vmax/center/baseline/slope/σ-Voigt, las casillas de ajuste y el
    selector de modelo de absorbente con ``sat_scale``.
    """

    paramChanged = QtCore.Signal()
    driveFormChanged = QtCore.Signal()   # cambio de forma de onda (recomputar datos)
    profileChanged = QtCore.Signal(str)  # perfil de línea (para el radio del menú)

    def __init__(self, parent=None):
        super().__init__(tr("controls.calibration_box"), parent)
        v = QtWidgets.QVBoxLayout(self)
        v.setSpacing(2)

        _cs = effective_calibration_specs()
        self.vmax = ParamControl(tr("slider.vmax"), *astuple(_cs["vmax"]), with_fixed=False)
        self.fit_velocity = QtWidgets.QCheckBox(tr("checkbox.fit_vmax"))
        self.center = ParamControl(tr("slider.center"), *astuple(_cs["center"]), with_fixed=False)
        self.fit_center = QtWidgets.QCheckBox(tr("checkbox.fit_center"))
        self.baseline = ParamControl(tr("slider.baseline"), *astuple(_cs["baseline"]))
        self.slope = ParamControl(tr("slider.slope"), *astuple(_cs["slope"]))
        self.voigt_sigma = ParamControl(tr("slider.voigt_sigma"), *astuple(_cs["voigt_sigma"]), with_fixed=True)
        self.voigt_sigma.set_fixed(True)  # σ fija por defecto; con perfil Voigt, desmárcala para refinarla
        if self.voigt_sigma.fixed_cb is not None:
            self.voigt_sigma.fixed_cb.setToolTip(
                tr("tooltip.fit_sigma",
                   default="Con perfil Voigt, desmarca 'Fijo' para refinar σ en el ajuste."))
        self.line_profile = "Lorentziana"
        # Casilla interna (oculta): refleja "refinar σ", derivado de la casilla
        # 'Fijo' de σ + perfil Voigt. Es lo que consumen el motor y la sesión.
        self.fit_sigma = QtWidgets.QCheckBox(tr("checkbox.fit_sigma"), self)
        self.fit_sigma.hide()

        # Menú contextual (clic derecho) del perfil de línea: solo sobre el
        # control de σ-Voigt (etiqueta, slider y spinbox). No aparece sobre el
        # resto de la caja de calibración ni sobre la casilla 'Ajustar σ'.
        for w in (self.voigt_sigma, self.voigt_sigma.label,
                  self.voigt_sigma.slider, self.voigt_sigma.spin):
            w.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            w.customContextMenuRequested.connect(self._show_sigma_menu)

        # Perfil de línea como desplegable, al lado de los de forma de onda y
        # absorbente: los tres eligen el MODELO y hasta ahora este era el único
        # escondido tras un clic derecho y un submenú. Con σ oculta en modo
        # lorentziano, sin esto no quedaba ninguna pista visible de que exista
        # el perfil Voigt.
        profile_row = QtWidgets.QHBoxLayout()
        profile_row.addWidget(QtWidgets.QLabel(tr("options.line_profile")))
        self.profile_combo = QtWidgets.QComboBox()
        for value, key in (("Lorentziana", "options.profile_lorentzian"),
                           ("Voigt", "options.profile_voigt")):
            self.profile_combo.addItem(tr(key, default=value), value)
        self.profile_combo.setToolTip(tr(
            "tooltip.c_line_profile",
            default="Lorentziana: la forma natural de la línea. Voigt: además "
                    "una anchura gaussiana σ para el ensanchamiento "
                    "instrumental o un desorden pequeño."))
        profile_row.addWidget(self.profile_combo, stretch=1)

        absorber_row = QtWidgets.QHBoxLayout()
        absorber_row.addWidget(QtWidgets.QLabel(tr("absorber.model_label")))
        self.absorber_combo = QtWidgets.QComboBox()
        for value, key in (("thin", "absorber.thin"),
                           ("thickness", "absorber.thickness"),
                           ("transmission", "absorber.transmission")):
            self.absorber_combo.addItem(tr(key, default=value), value)
        absorber_row.addWidget(self.absorber_combo, stretch=1)
        self.sat_scale = ParamControl(tr("slider.sat_scale"), *astuple(_cs["sat_scale"]))
        # Integral de transmisión: anchura FWHM de la línea de la fuente
        # (fija por defecto; desmarcar 'Fijo' para refinarla).
        self.src_fwhm = ParamControl(tr("slider.src_fwhm", default="Γ fuente (mm/s)"),
                                     *astuple(_cs["src_fwhm"]), with_fixed=True)
        self.src_fwhm.set_fixed(True)
        # Curvatura de base (término v²), fija a 0 por defecto.
        self.curv = ParamControl(tr("slider.curv", default="Curvatura base"),
                                 *astuple(_cs["curv"]), with_fixed=True)
        self.curv.set_fixed(True)
        # Fondo cúbico/cuártico (BKG(4)/BKG(5) de NORMOS), fijos a 0.
        self.curv3 = ParamControl(tr("slider.curv3", default="Base v³"),
                                  *astuple(_cs["curv3"]), with_fixed=True)
        self.curv3.set_fixed(True)
        self.curv4 = ParamControl(tr("slider.curv4", default="Base v⁴"),
                                  *astuple(_cs["curv4"]), with_fixed=True)
        self.curv4.set_fixed(True)

        # Forma de onda del drive: triangular (aceleración cte, se dobla + eje
        # lineal) o senoidal (NORMOS FOLD=.FALSE.: sin doblar, v = vmax·sin).
        drive_row = QtWidgets.QHBoxLayout()
        drive_row.addWidget(QtWidgets.QLabel(tr("drive.model_label", default="Forma de onda")))
        self.drive_combo = QtWidgets.QComboBox()
        for value, key in (("triangular", "drive.triangular"), ("sine", "drive.sine")):
            self.drive_combo.addItem(tr(key, default=("Triangular" if value == "triangular" else "Senoidal")), value)
        self.drive_combo.setToolTip(tr(
            "drive.tooltip",
            default="Triangular (aceleración constante): se dobla y el eje es lineal. "
                    "Senoidal: no se dobla; v = vmax·sin(2π(i−c0)/N)."))
        drive_row.addWidget(self.drive_combo, stretch=1)

        for w in (self.vmax, self.fit_velocity, self.center, self.fit_center,
                  self.baseline, self.slope, self.curv, self.curv3,
                  self.curv4):
            v.addWidget(w)
        # Cada desplegable, justo encima de los parámetros que gobierna: así se
        # ve de dónde salen y por qué aparecen o desaparecen.
        v.addLayout(profile_row)
        v.addWidget(self.voigt_sigma)
        v.addLayout(drive_row)
        v.addLayout(absorber_row)
        v.addWidget(self.sat_scale)
        v.addWidget(self.src_fwhm)
        self._refresh_absorber_widgets()
        v.addStretch(1)

        for w in (self.vmax, self.center, self.baseline, self.slope, self.curv,
                  self.curv3, self.curv4,
                  self.voigt_sigma, self.sat_scale, self.src_fwhm):
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())
            w.fixedChanged.connect(lambda *_: self.paramChanged.emit())
        self.profile_combo.currentIndexChanged.connect(
            lambda *_: self._set_line_profile(
                self.profile_combo.currentData() or "Lorentziana"))
        self.absorber_combo.currentIndexChanged.connect(lambda *_: (self._refresh_absorber_widgets(), self.paramChanged.emit()))
        self.drive_combo.currentIndexChanged.connect(lambda *_: self.driveFormChanged.emit())
        for cb in (self.fit_velocity, self.fit_center):
            cb.toggled.connect(lambda *_: self.paramChanged.emit())
        # La casilla 'Fijo' de σ dirige el refinado (fit_sigma). Estado inicial coherente.
        self.voigt_sigma.fixedChanged.connect(lambda *_: self._refresh_fit_sigma())
        self._set_line_profile(self.line_profile)
        self._apply_tooltips()

    def _apply_tooltips(self) -> None:
        """Globo de ayuda en cada parámetro de calibración."""
        for nombre in ("vmax", "center", "baseline", "slope", "curv", "curv3",
                       "curv4", "voigt_sigma", "sat_scale", "src_fwhm"):
            ctl = getattr(self, nombre, None)
            if ctl is None:
                continue
            texto = param_tooltip(nombre, "c")
            if nombre == "voigt_sigma":
                extra = tr("tooltip.more_profile", default="")
                texto = f"{texto}\n\n{extra}" if texto and extra else (texto or extra)
            if texto:
                ctl.set_help(texto)
            if nombre != "voigt_sigma":
                attach_help_menu(self, ctl, CALIB_HELP_CHAPTER.get(nombre, ""))

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
        add_help_entry(menu, self, CALIB_HELP_CHAPTER.get("voigt_sigma", ""))
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

    @property
    def drive_form(self) -> str:
        return self.drive_combo.currentData() or "triangular"

    def set_drive_form(self, form: str) -> None:
        idx = self.drive_combo.findData(form)
        if idx >= 0:
            self.drive_combo.setCurrentIndex(idx)

    def _refresh_absorber_widgets(self) -> None:
        """Solo se muestran los parámetros del modelo de absorbente activo.

        Antes se agrisaban: la escala de saturación y la Γ de la fuente
        ocupaban dos filas permanentes que en el caso normal (absorbente
        delgado) no se pueden tocar. Es el mismo criterio que en los paneles de
        componente; el combo «Absorbente» está siempre visible, así que
        reaparecen en cuanto se cambia de modelo.
        """
        self.sat_scale.setVisible(self.absorber_model == "thickness")
        self.src_fwhm.setVisible(self.absorber_model == "transmission")

    def to_view_state(self) -> CalibrationViewState:
        """Snapshot del panel sin exponer widgets al resto de la GUI."""
        return CalibrationViewState(
            vmax=self.vmax.value(),
            center=self.center.value(),
            baseline=self.baseline.value(),
            slope=self.slope.value(),
            voigt_sigma=self.voigt_sigma.value(),
            sat_scale=self.sat_scale.value(),
            curv=self.curv.value(),
            curv3=self.curv3.value(),
            curv4=self.curv4.value(),
            src_fwhm=self.src_fwhm.value(),
            line_profile=self.line_profile,
            absorber_model=self.absorber_model,
            drive_form=self.drive_form,
            fit_velocity=self.fit_velocity.isChecked(),
            fit_center=self.fit_center.isChecked(),
            fit_sigma=self.fit_sigma.isChecked(),
            fixed={
                "baseline": self.baseline.is_fixed(),
                "slope": self.slope.is_fixed(),
                "sat_scale": self.sat_scale.is_fixed(),
                "curv": self.curv.is_fixed(),
                "curv3": self.curv3.is_fixed(),
                "curv4": self.curv4.is_fixed(),
                "src_fwhm": self.src_fwhm.is_fixed(),
                "vmax": True,
                "center": True,
                "voigt_sigma": self.voigt_sigma.is_fixed(),
            },
        )

    def _set_line_profile(self, kind: str) -> None:
        self.line_profile = kind
        # El perfil se puede cambiar desde tres sitios (este desplegable, el
        # clic derecho sobre σ y el menú Ajuste): el combo refleja el estado
        # venga de donde venga, con las señales bloqueadas para no reentrar.
        combo = getattr(self, "profile_combo", None)
        if combo is not None:
            idx = combo.findData(kind)
            if idx >= 0 and combo.currentIndex() != idx:
                combo.blockSignals(True)
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)
        is_voigt = kind == "Voigt"
        # Fuera de Voigt el control se OCULTA: no se puede tocar y ocupa dos
        # filas. El perfil se cambia desde Ajuste ▸ Opciones avanzadas ▸ Perfil
        # de línea, y con Voigt activo vuelve a estar aquí con su menú
        # contextual de clic derecho.
        self.voigt_sigma.setVisible(is_voigt)
        self.voigt_sigma.slider.setEnabled(is_voigt)
        self.voigt_sigma.spin.setEnabled(is_voigt)
        if self.voigt_sigma.fixed_cb is not None:
            self.voigt_sigma.fixed_cb.setEnabled(is_voigt)
            if not is_voigt:
                self.voigt_sigma.set_fixed(True)  # fuera de Voigt σ no se refina
        self._refresh_fit_sigma()
        self.profileChanged.emit(kind)
        self.paramChanged.emit()

    def _refresh_fit_sigma(self) -> None:
        """Sincroniza la casilla interna fit_sigma: refinar σ = perfil Voigt y σ NO fija."""
        refine = self.line_profile == "Voigt" and not self.voigt_sigma.is_fixed()
        if self.fit_sigma.isChecked() != refine:
            self.fit_sigma.setChecked(refine)


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
        _cspecs = effective_component_specs()
        def _spec_rows(names):
            rows = []
            for name in names:
                s = _cspecs[name]
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
        self._apply_tooltips()
        self._on_type_changed(self.type_combo.currentText())

    def _apply_tooltips(self) -> None:
        """Globo de ayuda en cada parámetro del componente.

        Se vuelve a aplicar en cada relayout porque las etiquetas de Γ y de
        int2 cambian con el tipo (sextete/doblete/singlete) y el globo debe
        decir lo mismo que la etiqueta que hay al lado.
        """
        con_menu_propio = set(CONTEXT_HINTS)
        for nombre, ctl in self.params.items():
            texto = param_tooltip(nombre, "p")
            if texto:
                ctl.set_help(texto)
            if nombre not in con_menu_propio:
                attach_help_menu(self, ctl, PARAM_HELP_CHAPTER.get(nombre, ""))

    def _show_intensity_menu(self, ctl: "ParamControl", pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        title = menu.addAction(tr("context.intensity_mode_title"))
        title.setEnabled(False)
        menu.addSeparator()
        for val, key in zip(INTENSITY_MODES,
                            ("context.intensity_mode_free",
                             "context.intensity_mode_texture")):
            act = menu.addAction(tr(key))
            act.setCheckable(True)
            act.setChecked(self.intensity_mode == val)
            act.triggered.connect(lambda _c=False, v=val: self._set_intensity_mode(v))
        add_help_entry(menu, self, PARAM_HELP_CHAPTER.get(_nombre_de(self.params, ctl), ""))
        sender = self.sender()
        anchor = sender if isinstance(sender, QtWidgets.QWidget) else ctl.spin
        menu.exec(anchor.mapToGlobal(pos))

    def _set_intensity_mode(self, mode: str) -> None:
        if mode not in INTENSITY_MODES:
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
        for val, key in zip(QUAD_TREATMENTS,
                            ("context.quad_treatment_1st_order",
                             "context.quad_treatment_kundig_fixed",
                             "context.quad_treatment_kundig_powder",
                             "context.quad_treatment_hamiltonian",
                             "context.quad_treatment_hamiltonian_sc")):
            act = menu.addAction(tr(key))
            act.setCheckable(True)
            act.setChecked(self.quad_treatment == val)
            act.triggered.connect(lambda _c=False, v=val: self._set_quad_treatment(v))
        add_help_entry(menu, self, PARAM_HELP_CHAPTER.get(_nombre_de(self.params, ctl), ""))
        sender = self.sender()
        anchor = sender if isinstance(sender, QtWidgets.QWidget) else ctl.spin
        menu.exec(anchor.mapToGlobal(pos))

    def _set_quad_treatment(self, treatment: str) -> None:
        if treatment not in QUAD_TREATMENTS:
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

    def set_compact(self, compact: bool) -> None:
        """Propaga el modo compacto a todos los controles del componente."""
        for ctl in self.params.values():
            ctl.set_compact(compact)
        self.updateGeometry()

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
        """Recoloca el grid mostrando solo los parámetros ajustables ahora.

        Visibilidad = ``relevant_params(tipo, modo de intensidad, tratamiento
        del cuadrupolo)``: un doblete no muestra BHF/Γ3, un Néel no muestra
        textura/β, y un sextete de primer orden no muestra η/φ/Bex/Gax, que
        solo existen con el Hamiltoniano.

        Antes la visibilidad era por TIPO (``USED_BY[kind]``) y lo no aplicable
        se agrisaba: un sextete enseñaba 15 controles de los que solo 9 se
        podían tocar, y los 6 agrisados costaban 3 filas (397 px frente a 262).
        Con dos o tres componentes abiertos eso impedía verlos a la vez.
        Ocultarlos es la misma regla que ya se aplicaba al tipo, llevada hasta
        el final; los parámetros reaparecen al cambiar el tratamiento o el modo
        de intensidad, que son combos siempre visibles.
        """
        used = self.relevant_params()
        shown = set(used)
        # Saca todo del grid (los widgets siguen vivos como hijos del panel).
        for ctl in self.params.values():
            self.params_grid.removeWidget(ctl)

        # Filtra los visibles para cada columna respetando el orden canónico.
        col0 = [n for n in COMPONENT_PARAM_LAYOUT["left"]  if n in shown]
        col1 = [n for n in COMPONENT_PARAM_LAYOUT["right"] if n in shown]

        # Reequilibra solo si una columna dobla holgadamente a la otra, y
        # entonces mueve el ÚLTIMO de la larga al final de la corta.
        #
        # Antes movía el PRIMERO (`pop(0)`) pese a que el comentario decía lo
        # contrario, y con un sexteto de primer orden —6 a la izquierda contra
        # 3 a la derecha— eso mandaba el DESPLAZAMIENTO ISOMÉRICO al final de
        # la columna derecha. δ es el primer parámetro que se mira y tiene que
        # encabezar el panel, como en el doblete y el singlete.
        #
        # El margen es 3 y no 2 para que ese mismo caso ni se reequilibre: la
        # fila de más que cuesta vale menos que romper el orden de lectura y
        # separar las Γ entre columnas.
        while len(col1) > len(col0) + 3:
            col0.append(col1.pop())
        while len(col0) > len(col1) + 3:
            col1.append(col0.pop())

        for col, names in enumerate((col0, col1)):
            for row, name in enumerate(names):
                ctl = self.params[name]
                self.params_grid.addWidget(ctl, row, col)
                ctl.setVisible(True)
                # Todo lo que se muestra es ajustable: lo que no, ya no está.
                ctl.setEnabled(True)

        # Oculta los no visibles ni ocultos.
        visible = set(col0) | set(col1)
        for name, ctl in self.params.items():
            if name not in visible:
                ctl.setVisible(False)

        # Etiquetas adaptadas al tipo. Γ1 es la anchura absoluta (global, mm/s)
        # y Γ2/Γ3 son relativas a ella; los números de línea (1,6 / 2,5) solo
        # tienen sentido en el sextete, así que doblete/singlete usan variantes
        # propias. int2 pasa de I23 (sextete) a ratio entre ramas (doblete).
        # Variante por tipo: si no existe la clave específica, se usa la base.
        suffix = {"Doblete": "_doblete", "Singlete": "_singlete"}.get(self.kind, "")
        for name in ("gamma1", "gamma2", "int2"):
            ctl = self.params.get(name)
            if ctl is None:
                continue
            base_key = f"slider.s_{name}"
            ctl.label.setText(tr(f"{base_key}{suffix}", default=tr(base_key)))

        # El grupo oculto (int3) nunca se muestra ni ocupa celda.
        for name in COMPONENT_PARAM_LAYOUT["hidden"]:
            ctl = self.params.get(name)
            if ctl is not None:
                ctl.setVisible(False)

        self._apply_tooltips()

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
