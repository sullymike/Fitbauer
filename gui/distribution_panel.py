"""Panel de distribución P(BHF) / P(ΔEQ) / P(IS) / 2D para la GUI Qt."""
from __future__ import annotations

import html
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from dataclasses import astuple

from mossbauer_i18n import tr
from core.params import (DIST_VAR_DEFAULT_SPAN, DIST_VAR_RANGE, DIST_RANGE_RESOLUTION,
                         GAUSSIAN_DISTRIBUTION_SHAPES, is_2d_shape)
from core.param_overrides import effective_distribution_specs
from gui.controls import ParamControl
from gui.panels import attach_help_menu
from mossbauer_distribution import BINOMIAL_BOUNDS, BINOMIAL_NEIGHBORS_NORMOS
from gui.state import DistributionViewState


#: Capítulo y ancla de la ayuda que explican los límites σ de las gaussianas.
VBF_SIGMA_HELP = "distributions.2#vbf-sigma"


#: Capítulo de ayuda que explica en detalle cada aviso del panel; cada aviso
#: enlaza a su ancla (``[[#id]]`` en el help.json de todos los idiomas).
WARNINGS_HELP_CHAPTER = "distributions.8"


class DistributionPanel(QtWidgets.QGroupBox):
    """Panel para modo distribución P(BHF) / P(ΔEQ) / P(IS) / 2D.

    Formas 1D: Histograma (Hesse-Rübartsch no paramétrica), Gaussiana, VBF,
    Binomial y Fija (P cargada desde fichero). En los modos 2D el combo ofrece
    Histograma (código «2D», mapa regularizado), Gaussiana 2D y VBF 2D.
    """

    paramChanged = QtCore.Signal()
    loadFixedRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(tr("tab.distribution_bhf"), parent)
        v = QtWidgets.QVBoxLayout(self)
        v.setSpacing(2)

        cols = QtWidgets.QGridLayout()
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setHorizontalSpacing(12)
        cols.setVerticalSpacing(2)
        cols.setColumnStretch(0, 1)
        cols.setColumnStretch(1, 1)
        left = QtWidgets.QWidget()
        right = QtWidgets.QWidget()
        left_v = QtWidgets.QVBoxLayout(left)
        right_v = QtWidgets.QVBoxLayout(right)
        for lay in (left_v, right_v):
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(2)
        cols.addWidget(left, 0, 0)
        cols.addWidget(right, 0, 1)
        v.addLayout(cols)

        # Columna 1 — forma, regulación y parámetros globales.
        shape_row = QtWidgets.QHBoxLayout()
        shape_row.addWidget(QtWidgets.QLabel(tr("bhf.shape_label") + ":"))
        self.shape_combo = QtWidgets.QComboBox()
        # 1D o 2D lo fija el modo de ajuste; el combo ofrece las formas de
        # ese modo (_set_shape_choices).
        self._shape_choices_2d = False
        self._fill_shape_combo(self._SHAPES_1D)
        self.shape_combo.currentIndexChanged.connect(
            lambda *_: (self._sync_2d_controls(), self.paramChanged.emit()))
        shape_row.addWidget(self.shape_combo, stretch=1)
        left_v.addLayout(shape_row)

        # Aviso de uso (P(IS) con Γ libre, P(ΔEQ) con campo): oculto si no aplica.
        self.var_warning = QtWidgets.QLabel()
        self.var_warning.setObjectName("DistWarning")
        self.var_warning.setWordWrap(True)
        self.var_warning.setStyleSheet("color: #b45309;")
        # Texto enriquecido con un enlace «Más información…» a la sección de
        # la ayuda que lo explica en detalle (una frase no da para más).
        self.var_warning.setTextFormat(QtCore.Qt.RichText)
        self.var_warning.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
        self.var_warning.setOpenExternalLinks(False)
        self.var_warning.linkActivated.connect(self._open_warning_help)
        self.var_warning.setVisible(False)
        self.warning_anchor: str | None = None
        left_v.addWidget(self.var_warning)

        reg_row = QtWidgets.QHBoxLayout()
        reg_row.addWidget(QtWidgets.QLabel(tr("bhf.reg_mode_label") + ":"))
        self.reg_mode_combo = QtWidgets.QComboBox()
        self.reg_mode_combo.addItems(["tikhonov", "tv", "maxent"])
        self.reg_mode_combo.currentIndexChanged.connect(lambda *_: self.paramChanged.emit())
        reg_row.addWidget(self.reg_mode_combo, stretch=1)
        left_v.addLayout(reg_row)

        # Física del kernel (solo histograma): 1er orden clásico o promedio
        # de polvo del Hamiltoniano completo (análogo del EXACT de
        # NORMOS-DIST; con él, ΔEQ es el módulo del EFG aleatorio).
        kt_row = QtWidgets.QHBoxLayout()
        kt_row.addWidget(QtWidgets.QLabel(
            tr("bhf.kernel_treatment_label", default="Kernel") + ":"))
        self.kernel_combo = QtWidgets.QComboBox()
        for code, key in (("1st_order", "bhf.kernel_1st_order"),
                          ("hamiltonian", "bhf.kernel_hamiltonian")):
            self.kernel_combo.addItem(
                tr(key, default=("1er orden" if code == "1st_order"
                                 else "Hamiltoniano (polvo)")), code)
        self.kernel_combo.currentIndexChanged.connect(lambda *_: self.paramChanged.emit())
        kt_row.addWidget(self.kernel_combo, stretch=1)
        # Todo lo de la física del kernel va en una caja que solo se ve en
        # P(BHF) con Histograma: el resto de formas y variables no lo usan.
        self._kernel_box = QtWidgets.QWidget()
        kernel_v = QtWidgets.QVBoxLayout(self._kernel_box)
        kernel_v.setContentsMargins(0, 0, 0, 0)
        kernel_v.setSpacing(2)
        left_v.addWidget(self._kernel_box)
        kernel_v.addLayout(kt_row)
        self.kernel_eta = ParamControl(
            tr("slider.dist_kernel_eta", default="η EFG (kernel HC)"),
            0.0, 0.0, 1.0, 0.01, 3)
        self.kernel_eta.set_fixed(True)
        kernel_v.addWidget(self.kernel_eta)
        self.kernel_eta.valueChanged.connect(lambda *_: self.paramChanged.emit())

        # Fuente polarizada (paridad METHOD=4/POLAR de NORMOS-DIST): sexteto
        # emisor magnetizado; peine de 36 líneas por selección de helicidad.
        self.source_polarized = QtWidgets.QCheckBox(
            tr("bhf.source_polarized", default="Fuente polarizada (γ∥B)"))
        kernel_v.addWidget(self.source_polarized)
        self.source_bhf = ParamControl(
            tr("slider.dist_source_bhf", default="B fuente (T)"),
            33.0, 0.0, 60.0, 0.01, 3)
        self.source_theta = ParamControl(
            tr("slider.dist_source_theta", default="θ fuente (°)"),
            0.0, 0.0, 90.0, 0.1, 2)
        self.absorber_theta = ParamControl(
            tr("slider.dist_absorber_theta", default="θ absorbente (°)"),
            0.0, 0.0, 90.0, 0.1, 2)
        for w in (self.source_bhf, self.source_theta, self.absorber_theta):
            kernel_v.addWidget(w)
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())
        self._sync_source_widgets()
        self.source_polarized.toggled.connect(
            lambda *_: (self._sync_source_widgets(), self.paramChanged.emit()))

        # Nº de gaussianas para la forma VBF (Rancourt–Ping). Oculto salvo VBF.
        self.vbf_row = QtWidgets.QHBoxLayout()
        self.vbf_row.addWidget(QtWidgets.QLabel(tr("bhf.vbf_ncomp", default="Componentes VBF") + ":"))
        self.vbf_ncomp = QtWidgets.QSpinBox()
        self.vbf_ncomp.setRange(1, 6)
        self.vbf_ncomp.setValue(2)
        self.vbf_ncomp.valueChanged.connect(lambda *_: self.paramChanged.emit())
        self.vbf_row.addWidget(self.vbf_ncomp, stretch=1)
        self._vbf_row_widget = QtWidgets.QWidget()
        self._vbf_row_widget.setLayout(self.vbf_row)
        left_v.addWidget(self._vbf_row_widget)
        # Límites de anchura σ comunes a todas las gaussianas (VBF y Gaussiana,
        # 1D y 2D). Los controles se crean más abajo, con las specs efectivas.
        self._vbf_sigma_box = QtWidgets.QWidget()
        self._vbf_sigma_v = QtWidgets.QVBoxLayout(self._vbf_sigma_box)
        self._vbf_sigma_v.setContentsMargins(0, 0, 0, 0)
        self._vbf_sigma_v.setSpacing(2)
        left_v.addWidget(self._vbf_sigma_box)

        # Binomial de vecinos (DISTRI=3 + CONC de NORMOS-DIST): n vecinos,
        # concentración del soluto y valor sin vecinos + cambio por vecino.
        # Oculto salvo con la forma Binomial, que no usa la malla.
        self._binom_box = QtWidgets.QWidget()
        binom_v = QtWidgets.QVBoxLayout(self._binom_box)
        binom_v.setContentsMargins(0, 0, 0, 0)
        binom_v.setSpacing(2)
        nrow = QtWidgets.QHBoxLayout()
        nrow.addWidget(QtWidgets.QLabel(
            tr("bhf.binom_neighbors", default="Vecinos") + ":"))
        self.binom_neighbors = QtWidgets.QSpinBox()
        self.binom_neighbors.setRange(1, 24)
        self.binom_neighbors.setValue(BINOMIAL_NEIGHBORS_NORMOS)
        self.binom_neighbors.valueChanged.connect(lambda *_: self.paramChanged.emit())
        nrow.addWidget(self.binom_neighbors, stretch=1)
        binom_v.addLayout(nrow)
        self.binom_conc = ParamControl(
            tr("slider.dist_binom_conc", default="Concentración soluto (%)"),
            10.0, 0.0, 100.0, 0.1, 2)
        self.binom_conc.set_fixed(True)   # como CONC en NORMOS: es un dato
        self.binom_start = ParamControl("", 33.0, 0.0, 80.0, 0.01, 3)
        self.binom_step = ParamControl("", -2.5, -15.0, 15.0, 0.01, 3)
        for w in (self.binom_conc, self.binom_start, self.binom_step):
            binom_v.addWidget(w)
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())
            w.fixedChanged.connect(lambda *_: self.paramChanged.emit())
        left_v.addWidget(self._binom_box)
        self._binom_owner: str | None = None

        self.btn_load_fixed = QtWidgets.QPushButton(tr("bhf.load_fixed"))
        self.btn_load_fixed.clicked.connect(self.loadFixedRequested)
        self.btn_load_fixed.setEnabled(False)
        self.shape_combo.currentIndexChanged.connect(
            lambda i: self.btn_load_fixed.setEnabled(self.shape == "Fija"))
        left_v.addWidget(self.btn_load_fixed)

        _ds = effective_distribution_specs()
        self._dist_eff_specs = _ds  # cache para _dist_var_range
        # σ mín/máx de las gaussianas: 0 se muestra como «auto» (límite
        # automático del motor). Los *_y son del eje Y de las formas 2D.
        self.vbf_sigma_min = ParamControl("", *astuple(_ds["vbf_sigma_min"]), with_fixed=False)
        self.vbf_sigma_max = ParamControl("", *astuple(_ds["vbf_sigma_max"]), with_fixed=False)
        self.vbf_sigma_min_y = ParamControl("", *astuple(_ds["vbf_sigma_min_y"]), with_fixed=False)
        self.vbf_sigma_max_y = ParamControl("", *astuple(_ds["vbf_sigma_max_y"]), with_fixed=False)
        for w in self._vbf_sigma_controls():
            w.spin.setSpecialValueText(tr("bhf.vbf_sigma_auto", default="auto"))
            w.set_help(tr("tooltip.dist_vbf_sigma", default=""))
            attach_help_menu(self, w, VBF_SIGMA_HELP)
            self._vbf_sigma_v.addWidget(w)
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())
        # Variable de cada eje a la que pertenecen los σ (al cambiar, vuelven a auto).
        self._vbf_sigma_owner: dict[str, str | None] = {"x": None, "y": None}
        self.delta     = ParamControl(tr("slider.dist_delta"),     *astuple(_ds["delta"]))
        self.quad      = ParamControl(tr("slider.dist_quad"),      *astuple(_ds["quad"]))
        self.fixed_bhf = ParamControl(tr("slider.dist_fixed_bhf"), *astuple(_ds["fixed_bhf"]), with_fixed=False)
        self.gamma     = ParamControl(tr("slider.dist_gamma"),     *astuple(_ds["gamma"]))
        # Correlación δ(H)/ΔEQ(H) (mm/s·T⁻¹). Default 0 = sin correlación. La
        # casilla 'Fijo' desmarcada refina la pendiente en la capa externa (nivel b).
        self.delta_slope = ParamControl(
            tr("slider.dist_delta_slope", default="κδ dδ/dH (mm/s·T⁻¹)"),
            0.0, -0.02, 0.02, 0.0005, 4)
        self.quad_slope = ParamControl(
            tr("slider.dist_quad_slope", default="κq dΔEQ/dH (mm/s·T⁻¹)"),
            0.0, -0.02, 0.02, 0.0005, 4)
        self.delta_slope.set_fixed(True)
        self.quad_slope.set_fixed(True)
        # Opción avanzada de P(ΔEQ): sextetes con campo fijo en vez de dobletes.
        self.field_enabled = QtWidgets.QCheckBox(
            tr("bhf.field_advanced", default="Sextete con campo fijo (avanzado)"))
        self.field_enabled.setToolTip(tr("bhf.field_advanced_tip", default=""))
        self.field_enabled.toggled.connect(
            lambda *_: (self._sync_field_controls(), self.paramChanged.emit()))
        self.fixed_bhf.label.setText(
            tr("slider.dist_fixed_bhf_active", default="BHF fijo (T)"))
        for w in (self.delta, self.quad, self.field_enabled, self.fixed_bhf,
                  self.gamma, self.delta_slope, self.quad_slope):
            left_v.addWidget(w)
            if not isinstance(w, ParamControl):
                continue
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())
            if w.fixed_cb is not None:
                w.fixedChanged.connect(lambda *_: self.paramChanged.emit())
        self.fixed_bhf.valueChanged.connect(lambda *_: self._sync_warning())
        self.gamma.fixedChanged.connect(lambda *_: self._sync_warning())
        left_v.addStretch(1)

        # Columna 2 — rango/bins/alfa + controles 2D + presets y opciones.
        self.bmin      = ParamControl(tr("slider.dist_bmin"),      *astuple(_ds["bmin"]),      with_fixed=False)
        self.bmax      = ParamControl(tr("slider.dist_bmax"),      *astuple(_ds["bmax"]),      with_fixed=False)
        self.nbins     = ParamControl(tr("slider.dist_nbins"),     *astuple(_ds["nbins"]),     with_fixed=False)
        self.log_alpha = ParamControl(tr("slider.dist_log_alpha"), *astuple(_ds["log_alpha"]), with_fixed=False)
        for w in (self.bmin, self.bmax, self.nbins, self.log_alpha):
            right_v.addWidget(w)
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())

        # Controles 2D (ocultos por defecto)
        self.qmin        = ParamControl(tr("slider.dist2d_qmin",       default="ΔEQ mín 2D"),   *astuple(_ds["qmin"]),        with_fixed=False)
        self.qmax        = ParamControl(tr("slider.dist2d_qmax",       default="ΔEQ máx 2D"),   *astuple(_ds["qmax"]),        with_fixed=False)
        self.qbins       = ParamControl(tr("slider.dist2d_qbins",      default="Bins ΔEQ 2D"),  *astuple(_ds["qbins"]),       with_fixed=False)
        self.log_alpha_q = ParamControl(tr("slider.dist2d_log_alpha_q", default="log10 α ΔEQ"), *astuple(_ds["log_alpha_q"]), with_fixed=False)
        for w in (self.qmin, self.qmax, self.qbins, self.log_alpha_q):
            right_v.addWidget(w)
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())

        alpha_row = QtWidgets.QHBoxLayout()
        alpha_row.setSpacing(4)
        self._alpha_preset_btns: list[QtWidgets.QPushButton] = []
        for text, value in ((tr("bhf.alpha_fine", default="Fina"), -5.0),
                            (tr("bhf.alpha_medium", default="Media"), -2.0),
                            (tr("bhf.alpha_smooth", default="Suave"), 1.0)):
            btn = QtWidgets.QPushButton(text)
            btn.clicked.connect(lambda _=False, val=value: self._set_log_alpha(val))
            alpha_row.addWidget(btn)
            self._alpha_preset_btns.append(btn)
        right_v.addLayout(alpha_row)

        self.use_sharp = QtWidgets.QCheckBox(tr("bhf.use_sharp", default="Añadir componentes nítidas activas"))
        self.lcurve_link = QtWidgets.QCommandLinkButton(tr("bhf.lcurve_alpha", default="L-curve α"))
        self.lcurve_link.setDescription(tr("bhf.lcurve_hint", default="Estimar la regularización del histograma"))
        right_v.addWidget(self.use_sharp)
        self.use_sharp.toggled.connect(lambda *_: self.paramChanged.emit())
        right_v.addWidget(self.lcurve_link)
        self.btn_show_map = QtWidgets.QPushButton(tr("button.show_map", default="Ver mapa 2D…"))
        self.btn_show_map.setVisible(False)
        right_v.addWidget(self.btn_show_map)
        right_v.addStretch(1)
        v.addStretch(1)
        self.fixed_path: Path | None = None

        # Estado interno para sincronización 2D
        self._distribution_variable = "bhf"
        self._distribution_pair = ("bhf", "quad")
        # Malla recordada por (eje, variable); el eje X arranca con la de BHF.
        self._spans: dict[tuple[str, str], tuple[float, float]] = {}
        self._span_owner: dict[str, str | None] = {"x": "bhf", "y": None}
        self._slope_owner: str | None = "bhf"
        self._sync_2d_controls()

    _SHAPES_1D = (("Histograma", "shape.Histograma"),
                  ("Gaussiana", "shape.Gaussiana"),
                  ("VBF", "shape.VBF"),
                  ("Binomial", "shape.Binomial"),
                  ("Fija", "shape.Fija"))
    # En 2D se reutilizan los rótulos 1D: el modo ya dice que es bidimensional.
    _SHAPES_2D = (("2D", "shape.Histograma"),
                  ("Gaussiana 2D", "shape.Gaussiana"),
                  ("VBF 2D", "shape.VBF"))
    #: Forma equivalente al pasar de 1D a 2D (y la inversa al volver).
    _SHAPE_TO_2D = {"Histograma": "2D", "Gaussiana": "Gaussiana 2D", "VBF": "VBF 2D"}
    _VAR_SHORT = {"bhf": "BHF", "quad": "ΔEQ", "delta": "IS"}

    def _fill_shape_combo(self, shapes) -> None:
        for code, key in shapes:
            self.shape_combo.addItem(tr(key, default=code), code)

    def _set_shape_choices(self, is_2d: bool) -> None:
        """Rellena el combo de formas según el modo (1D o 2D) sin emitir señales."""
        if is_2d == self._shape_choices_2d:
            return
        previous = self.shape
        if is_2d:
            previous = self._SHAPE_TO_2D.get(previous, previous)
        else:
            previous = {v: k for k, v in self._SHAPE_TO_2D.items()}.get(previous, previous)
        self.shape_combo.blockSignals(True)
        self.shape_combo.clear()
        self._fill_shape_combo(self._SHAPES_2D if is_2d else self._SHAPES_1D)
        idx = self.shape_combo.findData(previous)
        self.shape_combo.setCurrentIndex(max(idx, 0))
        self.shape_combo.blockSignals(False)
        self._shape_choices_2d = is_2d

    def variable_label(self) -> str:
        """Nombre de la distribución activa: P(BHF), P(ΔEQ), P(IS) o P(x, y)."""
        if self._shape_choices_2d:
            x, y = self._distribution_pair
            return f"P({self._VAR_SHORT.get(x, x)}, {self._VAR_SHORT.get(y, y)})"
        var = self._distribution_variable
        return f"P({self._VAR_SHORT.get(var, var)})"

    def _set_log_alpha(self, value: float) -> None:
        self.log_alpha.set_value(float(value))
        self.paramChanged.emit()

    def _dist_var_label(self, var: str, role: str) -> str:
        if var == "delta":
            return tr(f"slider.dist_{role}_delta", default=f"IS {'mín' if role == 'bmin' else 'máx'}")
        if var == "quad":
            return tr(f"slider.dist_{role}_quad")
        return tr(f"slider.dist_{role}_bhf")

    def _dist_var_range(self, var: str) -> tuple[float, float]:
        s = self._dist_eff_specs
        if var == "delta":
            return s["is_lo"].default, s["is_hi"].default
        if var == "quad":
            return s["quad_lo"].default, s["quad_hi"].default
        if var == "quad±":
            return s["qmin"].lo, s["qmax"].hi
        return DIST_VAR_RANGE.get(var, DIST_VAR_RANGE["bhf"])

    def _switch_axis_range(self, axis: str, key: str) -> None:
        """Pone en el eje ``x`` (bmin/bmax) o ``y`` (qmin/qmax) el rango de ``key``.

        Cada variable recuerda su propia malla: antes los valores de BHF se
        recortaban a los límites de IS al cambiar de modo (0–50 T → 0–2.5 mm/s)
        y al volver a BHF quedaba una malla de 0–2.5 T.
        """
        lo_ctl, hi_ctl = (self.bmin, self.bmax) if axis == "x" else (self.qmin, self.qmax)
        lo, hi = self._dist_var_range(key)
        owner = self._span_owner.get(axis)
        if owner == key:
            for ctl in (lo_ctl, hi_ctl):
                ctl.set_range(lo, hi, DIST_RANGE_RESOLUTION)
            return
        if owner is not None:
            self._spans[(axis, owner)] = (lo_ctl.value(), hi_ctl.value())
        a, b = self._spans.get((axis, key), DIST_VAR_DEFAULT_SPAN.get(key, (lo, hi)))
        for ctl, val in ((lo_ctl, a), (hi_ctl, b)):
            ctl.set_range(lo, hi, DIST_RANGE_RESOLUTION)
            ctl.set_value(min(hi, max(lo, float(val))))
        self._span_owner[axis] = key

    def _sync_2d_controls(self) -> None:
        is_2d = is_2d_shape(self.shape)
        for ctl in (self.qmin, self.qmax, self.qbins):
            ctl.setVisible(is_2d)
        # α del eje Y: solo el histograma 2D está regularizado.
        self.log_alpha_q.setVisible(self.shape == "2D")
        # reg_mode (tikhonov/tv/maxent) solo lo consume el Histograma 1D.
        self.reg_mode_combo.setEnabled(self.shape == "Histograma")
        # Nº de gaussianas: solo con forma VBF.
        if hasattr(self, "_vbf_row_widget"):
            self._vbf_row_widget.setVisible(self.shape in ("VBF", "VBF 2D"))
        # Binomial: sus propios controles en lugar de la malla.
        is_binomial = self.shape == "Binomial"
        self._binom_box.setVisible(is_binomial)
        for ctl in (self.bmin, self.bmax, self.nbins):
            ctl.setVisible(not is_binomial)
        # Correlación δ(H)/ΔEQ(H): Histograma, VBF y Binomial.
        corr_ok = self.shape in ("Histograma", "VBF", "Binomial")
        for ctl in (self.delta_slope, self.quad_slope):
            ctl.setEnabled(corr_ok)
        self.btn_load_fixed.setEnabled(self.shape == "Fija")
        # α regulariza el Histograma (Tikhonov/TV) y también el histograma 2D
        # (α_x/α_y); Gaussiana/VBF/Binomial/Fija (y sus 2D) son paramétricas.
        # La L-curve solo está implementada para el Histograma 1D.
        is_histogram = self.shape == "Histograma"
        is_regularized = self.shape in ("Histograma", "2D")
        self.lcurve_link.setEnabled(is_histogram)
        self.log_alpha.setEnabled(is_regularized)
        for _btn in getattr(self, "_alpha_preset_btns", ()):
            _btn.setEnabled(is_regularized)
        self.lcurve_link.setToolTip(
            "" if is_histogram
            else tr("bhf.lcurve_only_histogram",
                    default="La L-curve solo aplica a la forma Histograma "
                            "(Gaussiana/Binomial son paramétricas y no usan α)."))
        self.use_sharp.setEnabled(True)
        self.setTitle(tr("tab.distribution", label=self.variable_label(),
                         default=f"Distribución {self.variable_label()}"))
        if is_2d:
            x_var, y_var = getattr(self, "_distribution_pair", ("bhf", "quad"))
            self.log_alpha.label.setText(
                f"{tr('slider.dist_log_alpha')} {self._VAR_SHORT.get(x_var, x_var)}"
                if self.shape == "2D" else tr("slider.dist_log_alpha"))
            self.log_alpha_q.label.setText(
                f"{tr('slider.dist_log_alpha')} {self._VAR_SHORT.get(y_var, y_var)}")
            self.bmin.label.setText(self._dist_var_label(x_var, "bmin"))
            self.bmax.label.setText(self._dist_var_label(x_var, "bmax"))
            self.qmin.label.setText(
                tr("slider.dist2d_qmin", default="Eje Y mín 2D") if y_var == "quad"
                else self._dist_var_label(y_var, "bmin"))
            self.qmax.label.setText(
                tr("slider.dist2d_qmax", default="Eje Y máx 2D") if y_var == "quad"
                else self._dist_var_label(y_var, "bmax"))
            self.qbins.label.setText(tr("slider.dist2d_qbins", default="Bins eje Y 2D"))
            self.quad.label.setText(
                tr("slider.dist_quad_inactive_2d", default="ΔEQ global (no usado: eje 2D)")
                if "quad" in (x_var, y_var) else tr("slider.dist_quad"))
            self.quad.setEnabled("quad" not in (x_var, y_var))
            self._switch_axis_range("x", x_var)
            # Junto a BHF, ΔEQ es el corrimiento 2ε de un sextete: lleva signo.
            self._switch_axis_range(
                "y", "quad±" if (y_var == "quad" and x_var == "bhf") else y_var)
        else:
            var = getattr(self, "_distribution_variable", "bhf")
            self.log_alpha.label.setText(tr("slider.dist_log_alpha"))
            is_quad = var == "quad"
            is_delta = var == "delta"
            self.bmin.label.setText(self._dist_var_label(var, "bmin"))
            self.bmax.label.setText(self._dist_var_label(var, "bmax"))
            self.quad.label.setText(
                tr("slider.dist_quad_inactive", default="ΔEQ global (no usado: distribuido)")
                if is_quad else tr("slider.dist_quad"))
            self.quad.setEnabled(not is_quad)
            self._switch_axis_range("x", var)
        self._sync_variable_controls(is_2d)
        self._sync_vbf_sigma_controls(is_2d)

    def _vbf_sigma_controls(self) -> tuple[ParamControl, ...]:
        return (self.vbf_sigma_min, self.vbf_sigma_max,
                self.vbf_sigma_min_y, self.vbf_sigma_max_y)

    def _sync_vbf_sigma_controls(self, is_2d: bool) -> None:
        """σ mín/máx de las gaussianas: visibles con VBF/Gaussiana, en unidades
        de cada eje y con rango hasta la anchura de su eje. Si cambia la
        variable de un eje, sus límites vuelven a «auto» (otras unidades)."""
        gauss = self.shape in GAUSSIAN_DISTRIBUTION_SHAPES
        self._vbf_sigma_box.setVisible(gauss)
        if is_2d:
            x_var, y_var = self._distribution_pair
            y_key = "quad±" if (y_var == "quad" and x_var == "bhf") else y_var
        else:
            x_var, y_var, y_key = self._distribution_variable, None, None
        for ctl in (self.vbf_sigma_min_y, self.vbf_sigma_max_y):
            ctl.setVisible(gauss and is_2d)
        for axis, var, key, (c_min, c_max) in (
                ("x", x_var, x_var, (self.vbf_sigma_min, self.vbf_sigma_max)),
                ("y", y_var, y_key, (self.vbf_sigma_min_y, self.vbf_sigma_max_y))):
            if var is None:
                continue
            short = self._VAR_SHORT.get(var, var)
            unit = self._VAR_UNIT.get(var, "")
            c_min.label.setText(tr("slider.dist_vbf_sigma_min", var=short, unit=unit,
                                   default=f"σ {short} mín ({unit})"))
            c_max.label.setText(tr("slider.dist_vbf_sigma_max", var=short, unit=unit,
                                   default=f"σ {short} máx ({unit})"))
            lo, hi = self._dist_var_range(key)
            sufijo = "_y" if axis == "y" else ""
            for ctl, nombre in ((c_min, "vbf_sigma_min"), (c_max, "vbf_sigma_max")):
                spec_hi = self._dist_eff_specs[nombre + sufijo].hi
                ctl.set_range(0.0, max(min(float(hi) - float(lo), float(spec_hi)), 0.001))
            if self._vbf_sigma_owner.get(axis) not in (None, var):
                for ctl in (c_min, c_max):
                    ctl.set_value(0.0)
            self._vbf_sigma_owner[axis] = var

    def _variables(self, is_2d: bool) -> tuple[str, ...]:
        return tuple(self._distribution_pair) if is_2d else (self._distribution_variable,)

    def _field_optional(self) -> bool:
        """¿Admite la variable activa la opción de campo fijo? Solo con ΔEQ sin BHF."""
        vars_ = self._variables(self._shape_choices_2d)
        return "quad" in vars_ and "bhf" not in vars_

    def effective_fixed_bhf(self) -> float:
        """Campo de las columnas del kernel: 0 salvo la opción avanzada de P(ΔEQ)."""
        if self._field_optional() and self.field_enabled.isChecked():
            return float(self.fixed_bhf.value())
        return 0.0

    def _sync_field_controls(self) -> None:
        optional = self._field_optional()
        self.field_enabled.setVisible(optional)
        self.fixed_bhf.setVisible(optional and self.field_enabled.isChecked())
        self._sync_warning()

    def _sync_warning(self) -> None:
        text = ""
        anchor = None
        vars_ = self._variables(self._shape_choices_2d)
        if vars_ == ("delta",) and not self.gamma.is_fixed():
            anchor = "is-gamma"
            text = tr("bhf.warn_is_gamma", default=(
                "⚠ Una distribución de IS ensancha todas las líneas por igual y "
                "se confunde con Γ: fija Γ para que P(IS) tenga sentido."))
        elif vars_ == ("delta", "quad") and self.effective_fixed_bhf() <= 0.0:
            anchor = "is-quad-doublets"
            text = tr("bhf.warn_is_quad_2d", default=(
                "⚠ Con dobletes solo se observa la distribución de cada línea "
                "(δ ± ΔEQ/2): el mapa IS–ΔEQ no es único (σ IS, σ ΔEQ y ρ se "
                "compensan). Para la correlación IS–ΔEQ usa P(ΔEQ) con κδ."))
        elif self.effective_fixed_bhf() > 0.0:
            anchor = "quad-field"
            text = tr("bhf.warn_quad_field", default=(
                "⚠ Con B ≠ 0 cada columna es un sextete de primer orden: solo es "
                "válido si ΔEQ es mucho menor que el desdoblamiento magnético."))
        self.warning_anchor = anchor if text else None
        if text:
            text = (f"{html.escape(text)} <a href='{WARNINGS_HELP_CHAPTER}#{anchor}'>"
                    f"{html.escape(tr('context.more_help', default='Más información…'))}</a>")
        self.var_warning.setText(text)
        self.var_warning.setVisible(bool(text))

    def _open_warning_help(self, href: str) -> None:
        """Abre la ayuda en la sección del aviso (``grupo.n#ancla``)."""
        ventana = self.window()
        if hasattr(ventana, "on_help"):
            ventana.on_help(chapter=href)

    #: Pendientes de correlación según la variable distribuida (1D): rótulo,
    #: semirrango. Con BHF van por tesla; con ΔEQ o IS por mm/s (adimensional).
    _SLOPES = {
        "bhf": {"delta_slope": ("slider.dist_delta_slope", "κδ dδ/dH (mm/s·T⁻¹)", 0.02),
                "quad_slope": ("slider.dist_quad_slope", "κq dΔEQ/dH (mm/s·T⁻¹)", 0.02)},
        "quad": {"delta_slope": ("slider.dist_delta_slope_quad", "κδ dδ/dΔEQ", 1.0)},
        "delta": {"quad_slope": ("slider.dist_quad_slope_is", "κq dΔEQ/dδ", 1.0)},
    }

    def _sync_variable_controls(self, is_2d: bool) -> None:
        """Muestra solo lo que usa la variable y forma activas."""
        var = self._distribution_variable
        # Física del kernel (1er orden/Hamiltoniano/fuente polarizada): solo
        # la consume el Histograma de P(BHF).
        self._kernel_box.setVisible(
            not is_2d and var == "bhf" and self.shape == "Histograma")
        # δ global: en P(IS) (o un 2D con IS) es la variable distribuida.
        uses_delta = "delta" in self._variables(is_2d)
        self.delta.setEnabled(not uses_delta)
        self.delta.label.setText(
            tr("slider.dist_delta_inactive", default="δ (no usado: distribuido)")
            if uses_delta else tr("slider.dist_delta"))
        # Pendientes de correlación: no existen en 2D; en 1D según la variable.
        slopes = {} if is_2d else self._SLOPES.get(var, {})
        if self._slope_owner != (None if is_2d else var):
            # Cambia el significado (y las unidades): se vuelve a «sin correlación».
            for ctl in (self.delta_slope, self.quad_slope):
                ctl.set_value(0.0)
                ctl.set_fixed(True)
            self._slope_owner = None if is_2d else var
        for name, ctl in (("delta_slope", self.delta_slope), ("quad_slope", self.quad_slope)):
            spec = slopes.get(name)
            ctl.setVisible(spec is not None)
            if spec is not None:
                key, default, half = spec
                ctl.label.setText(tr(key, default=default))
                ctl.set_range(-half, half)
        self._sync_field_controls()
        if not is_2d:
            self._sync_binomial_controls(var)

    #: Valor sin vecinos y cambio por vecino al estrenar cada variable
    #: (BHF: un soluto que baja el campo 2.5 T por vecino, tipo Fe-Al).
    _BINOM_DEFAULTS = {"bhf": (33.0, -2.5), "quad": (0.3, 0.2), "delta": (0.3, 0.05)}
    _VAR_UNIT = {"bhf": "T", "quad": "mm/s", "delta": "mm/s"}

    def _sync_binomial_controls(self, var: str) -> None:
        unit = self._VAR_UNIT.get(var, "")
        self.binom_start.label.setText(tr(
            "slider.dist_binom_start", var=self._VAR_SHORT.get(var, var), unit=unit,
            default=f"{self._VAR_SHORT.get(var, var)} sin vecinos ({unit})"))
        self.binom_step.label.setText(tr(
            "slider.dist_binom_step", unit=unit,
            default=f"Cambio por vecino ({unit})"))
        if self._binom_owner == var:
            return
        (lo, hi), (slo, shi) = BINOMIAL_BOUNDS.get(var, BINOMIAL_BOUNDS["bhf"])
        start, step = self._BINOM_DEFAULTS.get(var, (lo, (hi - lo) / 12))
        for ctl, a, b, val in ((self.binom_start, lo, hi, start),
                               (self.binom_step, slo, shi, step)):
            ctl.set_range(a, b)
            ctl.set_value(val)
        self._binom_owner = var

    def set_distribution_variable(self, variable: str) -> None:
        """Modo 1D: variable distribuida ``bhf``, ``quad`` o ``delta``."""
        self._distribution_variable = variable
        self._set_shape_choices(False)
        self._sync_2d_controls()

    def set_distribution_pair(self, variable_x: str, variable_y: str) -> None:
        """Modo 2D: par de variables (eje X, eje Y); el combo pasa a las formas 2D."""
        self._distribution_pair = (variable_x, variable_y)
        self._set_shape_choices(True)
        self._sync_2d_controls()

    def to_view_state(self, *, variable: str = "BHF") -> DistributionViewState:
        """Snapshot del panel sin exponer widgets al resto de la GUI."""
        if is_2d_shape(self.shape):
            _lmap = {"bhf": "BHF", "quad": "ΔEQ", "delta": "IS"}
            x, y = self._distribution_pair
            variable_label = f"{_lmap.get(x, x)}-{_lmap.get(y, y)}"
        elif variable in ("quad", "ΔEQ"):
            variable_label = "ΔEQ"
        elif variable in ("delta", "IS"):
            variable_label = "IS"
        else:
            variable_label = "BHF"
        return DistributionViewState(
            use_sharp=self.use_sharp.isChecked(),
            shape=self.shape,
            reg_mode=self.reg_mode,
            fixed_distribution_path=self.fixed_path,
            variable=variable_label,
            delta=self.delta.value(),
            quad=self.quad.value(),
            fixed_bhf=self.fixed_bhf.value(),
            field_enabled=self.field_enabled.isChecked(),
            gamma=self.gamma.value(),
            bmin=self.bmin.value(),
            bmax=self.bmax.value(),
            nbins=max(1, int(round(self.nbins.value()))),
            log_alpha=self.log_alpha.value(),
            delta_slope=self.delta_slope.value(),
            quad_slope=self.quad_slope.value(),
            kernel_treatment=self.kernel_treatment,
            kernel_eta=self.kernel_eta.value(),
            source_bhf=self.source_bhf.value(),
            source_theta=self.source_theta.value(),
            absorber_theta=self.absorber_theta.value(),
            vbf_n_components=int(self.vbf_ncomp.value()),
            vbf_sigma_min=self.vbf_sigma_min.value(),
            vbf_sigma_max=self.vbf_sigma_max.value(),
            vbf_sigma_min_y=self.vbf_sigma_min_y.value(),
            vbf_sigma_max_y=self.vbf_sigma_max_y.value(),
            binom_conc=self.binom_conc.value(),
            binom_neighbors=int(self.binom_neighbors.value()),
            binom_start=self.binom_start.value(),
            binom_step=self.binom_step.value(),
            qmin=self.qmin.value(),
            qmax=self.qmax.value(),
            qbins=max(1, int(round(self.qbins.value()))),
            log_alpha_q=self.log_alpha_q.value(),
            fixed={
                "delta": self.delta.is_fixed(),
                "quad": self.quad.is_fixed(),
                "gamma": self.gamma.is_fixed(),
                "delta_slope": self.delta_slope.is_fixed(),
                "quad_slope": self.quad_slope.is_fixed(),
                "binom_conc": self.binom_conc.is_fixed(),
                "binom_start": self.binom_start.is_fixed(),
                "binom_step": self.binom_step.is_fixed(),
            },
        )

    @property
    def shape(self) -> str:
        return self.shape_combo.currentData() or "Histograma"

    def _sync_source_widgets(self) -> None:
        on = self.source_polarized.isChecked()
        for w in (self.source_bhf, self.source_theta, self.absorber_theta):
            w.setEnabled(on)
        # la fuente polarizada usa su propio kernel: el selector de física
        # del kernel no aplica mientras esté activa
        self.kernel_combo.setEnabled(not on)
        self.kernel_eta.setEnabled(not on)

    @property
    def kernel_treatment(self) -> str:
        if self.source_polarized.isChecked():
            return "polarized"
        return self.kernel_combo.currentData() or "1st_order"

    @property
    def reg_mode(self) -> str:
        return self.reg_mode_combo.currentText() or "tikhonov"
