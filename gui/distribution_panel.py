"""Panel de distribución P(BHF) / P(ΔEQ) para la GUI Qt."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from mossbauer_i18n import tr
from core.constants import (
    BHF_DEFAULT_T, DIST_BHF_RANGE, DIST_QUAD_RANGE, DIST_RANGE_RESOLUTION,
)
from gui.controls import ParamControl
from gui.state import DistributionViewState


class DistributionPanel(QtWidgets.QGroupBox):
    """Panel para modo distribución P(BHF) / P(ΔEQ).

    Soporta 4 formas (igual que la GUI Tk): Histograma (Hesse-Rübartsch
    no paramétrica), Gaussiana, Binomial y Fija (P cargada desde fichero).
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
                          ("Binomial", "shape.Binomial"),
                          ("Fija", "shape.Fija")):
            self.shape_combo.addItem(tr(key), code)
        self.shape_combo.currentIndexChanged.connect(lambda *_: self.paramChanged.emit())
        shape_row.addWidget(self.shape_combo, stretch=1)
        left_v.addLayout(shape_row)

        reg_row = QtWidgets.QHBoxLayout()
        reg_row.addWidget(QtWidgets.QLabel(tr("bhf.reg_mode_label") + ":"))
        self.reg_mode_combo = QtWidgets.QComboBox()
        self.reg_mode_combo.addItems(["tikhonov", "tv"])
        self.reg_mode_combo.currentIndexChanged.connect(lambda *_: self.paramChanged.emit())
        reg_row.addWidget(self.reg_mode_combo, stretch=1)
        left_v.addLayout(reg_row)

        self.btn_load_fixed = QtWidgets.QPushButton(tr("bhf.load_fixed"))
        self.btn_load_fixed.clicked.connect(self.loadFixedRequested)
        self.btn_load_fixed.setEnabled(False)
        self.shape_combo.currentIndexChanged.connect(
            lambda i: self.btn_load_fixed.setEnabled(self.shape == "Fija"))
        left_v.addWidget(self.btn_load_fixed)

        self.delta = ParamControl(tr("slider.dist_delta"), 0.0, -2.5, 2.5, 0.001, 4)
        self.quad  = ParamControl(tr("slider.dist_quad"),  0.0, -4.0, 4.0, 0.001, 4)
        self.fixed_bhf = ParamControl(tr("slider.dist_fixed_bhf"), BHF_DEFAULT_T, 0.0, 60.0, 0.01, 3, with_fixed=False)
        self.gamma = ParamControl(tr("slider.dist_gamma"), 0.18, 0.03, 1.0, 0.001, 4)
        for w in (self.delta, self.quad, self.fixed_bhf, self.gamma):
            left_v.addWidget(w)
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())
        left_v.addStretch(1)

        # Columna 2 — rango/bins/alfa + presets y opciones avanzadas.
        self.bmin  = ParamControl(tr("slider.dist_bmin"), 0.0,  0.0, 60.0, 0.1, 2, with_fixed=False)
        self.bmax  = ParamControl(tr("slider.dist_bmax"), 50.0, 0.0, 60.0, 0.1, 2, with_fixed=False)
        self.nbins = ParamControl(tr("slider.dist_nbins"), 50.0, 10.0, 100.0, 1.0, 0, with_fixed=False)
        self.log_alpha = ParamControl(tr("slider.dist_log_alpha"), -2.0, -8.0, 4.0, 0.1, 2, with_fixed=False)
        for w in (self.bmin, self.bmax, self.nbins, self.log_alpha):
            right_v.addWidget(w)
            w.valueChanged.connect(lambda *_: self.paramChanged.emit())

        alpha_row = QtWidgets.QHBoxLayout()
        alpha_row.setSpacing(4)
        for text, value in ((tr("bhf.alpha_fine", default="Fina"), -5.0),
                            (tr("bhf.alpha_medium", default="Media"), -2.0),
                            (tr("bhf.alpha_smooth", default="Suave"), 1.0)):
            btn = QtWidgets.QPushButton(text)
            btn.clicked.connect(lambda _=False, val=value: self._set_log_alpha(val))
            alpha_row.addWidget(btn)
        right_v.addLayout(alpha_row)

        self.use_sharp = QtWidgets.QCheckBox(tr("bhf.use_sharp", default="Añadir componentes nítidas activas"))
        self.refine_global = QtWidgets.QCheckBox(tr("bhf.refine_global", default="Refinar δ y Γ globales"))
        self.lcurve_link = QtWidgets.QCommandLinkButton(tr("bhf.lcurve_alpha", default="L-curve α"))
        self.lcurve_link.setDescription(tr("bhf.lcurve_hint", default="Estimar la regularización del histograma"))
        for w in (self.use_sharp, self.refine_global):
            right_v.addWidget(w)
            w.toggled.connect(lambda *_: self.paramChanged.emit())
        right_v.addWidget(self.lcurve_link)
        right_v.addStretch(1)
        v.addStretch(1)
        self.fixed_path: Path | None = None

    def _set_log_alpha(self, value: float) -> None:
        self.log_alpha.set_value(float(value))
        self.paramChanged.emit()

    def set_distribution_variable(self, variable: str) -> None:
        is_quad = variable == "quad"
        if is_quad:
            self.bmin.label.setText(tr("slider.dist_bmin_quad"))
            self.bmax.label.setText(tr("slider.dist_bmax_quad"))
            self.fixed_bhf.label.setText(tr("slider.dist_fixed_bhf_active", default="BHF fijo (T)"))
            self.fixed_bhf.setEnabled(True)
            # En P(ΔEQ) el ΔEQ ES la magnitud distribuida (rango bmin/bmax), así
            # que el ΔEQ global no tiene sentido y se desactiva.
            self.quad.label.setText(
                tr("slider.dist_quad_inactive", default="ΔEQ global (no usado: distribuido)"))
            self.quad.setEnabled(False)
            max_value = DIST_QUAD_RANGE[1]
        else:
            self.bmin.label.setText(tr("slider.dist_bmin_bhf"))
            self.bmax.label.setText(tr("slider.dist_bmax_bhf"))
            self.fixed_bhf.label.setText(tr("slider.dist_fixed_bhf_inactive", default="BHF fijo (no usado en modo BHF)"))
            self.fixed_bhf.setEnabled(False)
            # En P(BHF) el ΔEQ global sí actúa como desplazamiento común.
            self.quad.label.setText(tr("slider.dist_quad"))
            self.quad.setEnabled(True)
            max_value = DIST_BHF_RANGE[1]
        for ctl in (self.bmin, self.bmax):
            ctl.set_range(0.0, max_value, DIST_RANGE_RESOLUTION)

    def to_view_state(self, *, variable: str = "BHF") -> DistributionViewState:
        """Snapshot del panel sin exponer widgets al resto de la GUI."""
        variable_label = "ΔEQ" if variable in ("quad", "ΔEQ") else "BHF"
        return DistributionViewState(
            use_sharp=self.use_sharp.isChecked(),
            refine_global=self.refine_global.isChecked(),
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
            fixed={
                "delta": self.delta.is_fixed(),
                "quad": self.quad.is_fixed(),
                "gamma": self.gamma.is_fixed(),
            },
        )

    @property
    def shape(self) -> str:
        return self.shape_combo.currentData() or "Histograma"

    @property
    def reg_mode(self) -> str:
        return self.reg_mode_combo.currentText() or "tikhonov"
