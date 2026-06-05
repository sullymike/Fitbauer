"""Controles reutilizables de la GUI Qt."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from mossbauer_i18n import tr


class ParamControl(QtWidgets.QWidget):
    """Una fila: etiqueta + QDoubleSpinBox + casilla 'fijo'.

    Emite ``valueChanged(float)`` cuando cambia el spinbox.
    """
    valueChanged = QtCore.Signal(float)
    fixedChanged = QtCore.Signal(bool)

    def __init__(self, label: str, value: float, lo: float, hi: float,
                 step: float = 0.01, decimals: int = 4, with_fixed: bool = True,
                 parent=None):
        super().__init__(parent)
        self._lo = float(lo)
        self._hi = float(hi)
        self._syncing = False

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 2, 0, 2)
        v.setSpacing(2)

        h = QtWidgets.QHBoxLayout()
        h.setSpacing(4)
        self.label = QtWidgets.QLabel(label)
        self.label.setMinimumWidth(82)
        self.label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.spin = QtWidgets.QDoubleSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(decimals)
        self.spin.setValue(value)
        self.spin.setMinimumWidth(80)
        h.addWidget(self.label, stretch=1)
        h.addWidget(self.spin)
        self.fixed_cb = None
        if with_fixed:
            self.fixed_cb = QtWidgets.QCheckBox(tr("checkbox.fixed"))
            h.addWidget(self.fixed_cb)
            self.fixed_cb.toggled.connect(self.fixedChanged)
        v.addLayout(h)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(25)
        self.slider.setToolTip(label)
        self.slider.setValue(self._value_to_slider(value))
        v.addWidget(self.slider)

        self.spin.valueChanged.connect(self._on_spin_changed)
        self.slider.valueChanged.connect(self._on_slider_changed)

    def value(self) -> float:
        return float(self.spin.value())

    def set_value(self, v: float) -> None:
        self._syncing = True
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(float(v))
        self.slider.setValue(self._value_to_slider(self.spin.value()))
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)
        self._syncing = False

    def set_range(self, lo: float, hi: float, step: float | None = None) -> None:
        self._lo = float(lo)
        self._hi = float(hi)
        value = max(self._lo, min(self._hi, float(self.spin.value())))
        self._syncing = True
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setRange(self._lo, self._hi)
        if step is not None:
            self.spin.setSingleStep(float(step))
        self.spin.setValue(value)
        self.slider.setValue(self._value_to_slider(self.spin.value()))
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)
        self._syncing = False

    def _value_to_slider(self, value: float) -> int:
        if self._hi <= self._lo:
            return 0
        frac = (float(value) - self._lo) / (self._hi - self._lo)
        return int(round(max(0.0, min(1.0, frac)) * self.slider.maximum()))

    def _slider_to_value(self, pos: int) -> float:
        if self.slider.maximum() <= 0:
            return self._lo
        frac = float(pos) / float(self.slider.maximum())
        return self._lo + frac * (self._hi - self._lo)

    def _on_spin_changed(self, value: float) -> None:
        if self._syncing:
            return
        self._syncing = True
        self.slider.blockSignals(True)
        self.slider.setValue(self._value_to_slider(value))
        self.slider.blockSignals(False)
        self._syncing = False
        self.valueChanged.emit(float(value))

    def _on_slider_changed(self, pos: int) -> None:
        if self._syncing:
            return
        value = self._slider_to_value(pos)
        self._syncing = True
        self.spin.blockSignals(True)
        self.spin.setValue(value)
        value = float(self.spin.value())
        self.spin.blockSignals(False)
        self._syncing = False
        self.valueChanged.emit(value)

    def is_fixed(self) -> bool:
        return bool(self.fixed_cb.isChecked()) if self.fixed_cb is not None else False

    def set_fixed(self, b: bool) -> None:
        if self.fixed_cb is not None:
            self.fixed_cb.setChecked(bool(b))
