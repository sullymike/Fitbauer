"""Panel de distribución P(BHF) / P(ΔEQ) / P(IS) / 2D para la GUI Qt."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from dataclasses import astuple

from mossbauer_i18n import tr
from core.params import DIST_VAR_RANGE, DIST_RANGE_RESOLUTION
from core.param_overrides import effective_distribution_specs
from gui.controls import ParamControl
from gui.state import DistributionViewState


class DistributionPanel(QtWidgets.QGroupBox):
    """Panel para modo distribución P(BHF) / P(ΔEQ) / P(IS) / 2D.

    Soporta 5 formas: Histograma (Hesse-Rübartsch no paramétrica), Gaussiana,
    Binomial, Fija (P cargada desde fichero) y 2D (distribución bidimensional).
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
        for code, key in (("Histograma", "shape.Histograma"),
                          ("Gaussiana", "shape.Gaussiana"),
                          ("VBF", "shape.VBF"),
                          ("Binomial", "shape.Binomial"),
                          ("Fija", "shape.Fija"),
                          ("2D", "shape.2D")):
            self.shape_combo.addItem(tr(key, default=code), code)
        self.shape_combo.currentIndexChanged.connect(
            lambda *_: (self._sync_2d_controls(), self.paramChanged.emit()))
        shape_row.addWidget(self.shape_combo, stretch=1)
        left_v.addLayout(shape_row)

        reg_row = QtWidgets.QHBoxLayout()
        reg_row.addWidget(QtWidgets.QLabel(tr("bhf.reg_mode_label") + ":"))
        self.reg_mode_combo = QtWidgets.QComboBox()
        self.reg_mode_combo.addItems(["tikhonov", "tv", "maxent"])
        self.reg_mode_combo.currentIndexChanged.connect(lambda *_: self.paramChanged.emit())
        reg_row.addWidget(self.reg_mode_combo, stretch=1)
        left_v.addLayout(reg_row)

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

        self.btn_load_fixed = QtWidgets.QPushButton(tr("bhf.load_fixed"))
        self.btn_load_fixed.clicked.connect(self.loadFixedRequested)
        self.btn_load_fixed.setEnabled(False)
        self.shape_combo.currentIndexChanged.connect(
            lambda i: self.btn_load_fixed.setEnabled(self.shape == "Fija"))
        left_v.addWidget(self.btn_load_fixed)

        _ds = effective_distribution_specs()
        self._dist_eff_specs = _ds  # cache para _dist_var_range
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
        for w in (self.delta, self.quad, self.fixed_bhf, self.gamma,
                  self.delta_slope, self.quad_slope):
            left_v.addWidget(w)
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())
            if w.fixed_cb is not None:
                w.fixedChanged.connect(lambda *_: self.paramChanged.emit())
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
        self._sync_2d_controls()

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
        return DIST_VAR_RANGE.get(var, DIST_VAR_RANGE["bhf"])

    def _sync_2d_controls(self) -> None:
        is_2d = self.shape == "2D"
        for ctl in (self.qmin, self.qmax, self.qbins, self.log_alpha_q):
            ctl.setVisible(is_2d)
        # reg_mode (tikhonov/tv/maxent) solo lo consume el Histograma 1D.
        self.reg_mode_combo.setEnabled(self.shape == "Histograma")
        # Nº de gaussianas: solo con forma VBF.
        if hasattr(self, "_vbf_row_widget"):
            self._vbf_row_widget.setVisible(self.shape == "VBF")
        # Correlación δ(H)/ΔEQ(H): aplica al Histograma y al VBF.
        corr_ok = self.shape in ("Histograma", "VBF")
        for ctl in (self.delta_slope, self.quad_slope):
            ctl.setEnabled(corr_ok)
        self.btn_load_fixed.setEnabled(self.shape == "Fija")
        # α regulariza el Histograma (Tikhonov/TV) y también la 2D (α_BHF/α_ΔEQ);
        # Gaussiana/Binomial/Fija son paramétricas y no usan α.
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
        if is_2d:
            x_var, y_var = getattr(self, "_distribution_pair", ("bhf", "quad"))
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
            self.fixed_bhf.setEnabled("bhf" not in (x_var, y_var))
            lo, hi = self._dist_var_range(x_var)
            for ctl in (self.bmin, self.bmax):
                ctl.set_range(lo, hi, DIST_RANGE_RESOLUTION)
            lo_y, hi_y = self._dist_var_range(y_var)
            for ctl in (self.qmin, self.qmax):
                ctl.set_range(lo_y, hi_y, DIST_RANGE_RESOLUTION)
        else:
            var = getattr(self, "_distribution_variable", "bhf")
            is_quad = var == "quad"
            is_delta = var == "delta"
            self.bmin.label.setText(self._dist_var_label(var, "bmin"))
            self.bmax.label.setText(self._dist_var_label(var, "bmax"))
            self.fixed_bhf.label.setText(
                tr("slider.dist_fixed_bhf_active", default="BHF fijo (T)") if (is_quad or is_delta)
                else tr("slider.dist_fixed_bhf_inactive", default="BHF fijo (no usado en modo BHF)"))
            self.fixed_bhf.setEnabled(is_quad or is_delta)
            self.quad.label.setText(
                tr("slider.dist_quad_inactive", default="ΔEQ global (no usado: distribuido)")
                if is_quad else tr("slider.dist_quad"))
            self.quad.setEnabled(not is_quad)
            lo, hi = self._dist_var_range(var)
            for ctl in (self.bmin, self.bmax):
                ctl.set_range(lo, hi, DIST_RANGE_RESOLUTION)

    def set_distribution_variable(self, variable: str) -> None:
        self._distribution_variable = variable
        if self.shape == "2D":
            self._sync_2d_controls()
            return
        self._sync_2d_controls()

    def set_distribution_pair(self, variable_x: str, variable_y: str) -> None:
        self._distribution_pair = (variable_x, variable_y)
        self._sync_2d_controls()

    def to_view_state(self, *, variable: str = "BHF") -> DistributionViewState:
        """Snapshot del panel sin exponer widgets al resto de la GUI."""
        if self.shape == "2D":
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
            gamma=self.gamma.value(),
            bmin=self.bmin.value(),
            bmax=self.bmax.value(),
            nbins=max(1, int(round(self.nbins.value()))),
            log_alpha=self.log_alpha.value(),
            delta_slope=self.delta_slope.value(),
            quad_slope=self.quad_slope.value(),
            vbf_n_components=int(self.vbf_ncomp.value()),
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
            },
        )

    @property
    def shape(self) -> str:
        return self.shape_combo.currentData() or "Histograma"

    @property
    def reg_mode(self) -> str:
        return self.reg_mode_combo.currentText() or "tikhonov"
