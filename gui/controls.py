"""Controles reutilizables de la GUI Qt."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from mossbauer_i18n import tr


class CodeComboBox(QtWidgets.QComboBox):
    """Combo que muestra rótulos traducidos pero trabaja con códigos internos.

    ``currentText()``/``setCurrentText()`` leen y aceptan el **código** (p. ej.
    ``"Doblete"``), y ``codeChanged`` lo emite; el texto visible es el rótulo del
    idioma activo. Así la lógica, las sesiones y los tests siguen usando los
    códigos y la interfaz no los enseña. ``setCurrentText`` acepta también el
    rótulo visible.
    """

    codeChanged = QtCore.Signal(str)

    def __init__(self, items, parent=None):
        super().__init__(parent)
        for code, label in items:
            self.addItem(label, code)
        self.currentIndexChanged.connect(lambda _i: self.codeChanged.emit(self.currentText()))

    def currentText(self) -> str:  # noqa: N802 (API de Qt)
        code = self.currentData()
        return code if code is not None else super().currentText()

    def setCurrentText(self, text: str) -> None:  # noqa: N802 (API de Qt)
        i = self.findData(text)
        if i < 0:
            i = self.findText(text)
        if i >= 0:
            self.setCurrentIndex(i)

    def currentLabel(self) -> str:
        return super().currentText()


class ParamControl(QtWidgets.QWidget):
    """Una fila: etiqueta + QDoubleSpinBox + casilla 'fijo'.

    Emite ``valueChanged(float)`` cuando cambia el spinbox.
    """
    valueChanged = QtCore.Signal(float)
    fixedChanged = QtCore.Signal(bool)
    #: Cambió alguna de las cotas de ajuste propias (mín/máx).
    limitsChanged = QtCore.Signal()

    def __init__(self, label: str, value: float, lo: float, hi: float,
                 step: float = 0.01, decimals: int = 4, with_fixed: bool = True,
                 parent=None):
        super().__init__(parent)
        self._lo = float(lo)
        self._hi = float(hi)
        #: Rango del control según los límites de parámetros (sin cotas propias).
        self._spec_range = (float(lo), float(hi))
        #: Cotas de ajuste propias (``None`` = la general del motor).
        self._fit_limits: tuple[float | None, float | None] = (None, None)
        #: Admite cotas de ajuste propias (parámetros de componente).
        self.limits_enabled = False
        self._syncing = False
        self._label_text = label
        #: Rótulo válido para el valor interno (``value()``): los avisos y las
        #: restricciones, que trabajan con él, lo usan aunque se vea otro.
        self.source_label = label
        #: Lo que se resta al valor para mostrarlo (δ respecto al α-Fe); el
        #: valor interno, el rango y las cotas siguen en su referencia propia.
        self._offset = 0.0
        #: Valor interno exacto, para no perder decimales al desplazarlo.
        self._raw: float | None = None
        self._extra_tip = ""

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
        self._row = h
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

        # Altura fija: el control nunca se comprime aunque el panel tenga poco
        # espacio — si no caben todos, la tarjeta ya tiene scroll.
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

    def set_help(self, text: str) -> None:
        """Globo de ayuda sobre TODO el control, no solo sobre el slider.

        El ratón se posa indistintamente en la etiqueta, la casilla numérica o
        la barra; si el globo solo estuviera en una de las tres, aparecería a
        ratos y el usuario no llegaría a fiarse de él.
        """
        self._help = text
        for w in (self, self.label, self.spin, self.slider):
            w.setToolTip(text)
        self._update_limits_marker()
        if self.fixed_cb is not None:
            self.fixed_cb.setToolTip(
                tr("tooltip.fixed_cb",
                   default="Marcado: el parámetro NO se ajusta, se queda en su valor."))

    def set_compact(self, compact: bool) -> None:
        """Modo compacto: oculta el slider y el control pasa a UNA fila.

        El slider es la mitad de la altura de cada parámetro (43 px frente a
        ~29). Quitarlo deja el control en una sola fila y permite ver dos o
        tres componentes a la vez, que es para lo que existe el modo. **No se
        pierde ningún parámetro**: el spinbox sigue editándolos todos, con sus
        flechas y su rueda; solo desaparece el arrastre grueso.
        """
        self.slider.setVisible(not bool(compact))
        self.updateGeometry()

    def value(self) -> float:
        shown = float(self.spin.value())
        if not self._offset:
            return shown
        tol = 0.5 * 10.0 ** -self.spin.decimals() + 1e-12
        if self._raw is not None and abs(self._raw - self._offset - shown) <= tol:
            return self._raw
        return shown + self._offset

    @property
    def display_offset(self) -> float:
        return self._offset

    def set_display_offset(self, offset: float) -> None:
        """Muestra ``valor − offset`` sin cambiar el valor interno, el rango
        ni las cotas, y sin emitir señal (no es un cambio del modelo)."""
        offset = float(offset or 0.0)
        if offset == self._offset:
            return
        v = self.value()
        self._offset = offset
        self.set_range(self._lo, self._hi)
        self.set_value(v)
        self._update_limits_marker()

    def set_value(self, v: float, *, widen: bool = False) -> None:
        """Pone el valor sin emitir señal. Fuera del rango se recorta, salvo
        con ``widen``: entonces el rango se amplía para mostrarlo (resultados
        de un ajuste o de una sesión, que no deben cambiar al volcarse)."""
        v = float(v)
        if widen and (v < self._lo or v > self._hi):
            self.set_range(min(self._lo, v), max(self._hi, v))
        self._syncing = True
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(v - self._offset)
        self._raw = max(self._lo, min(self._hi, v))
        self.slider.setValue(self._value_to_slider(self.value()))
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)
        self._syncing = False

    def set_range(self, lo: float, hi: float, step: float | None = None) -> None:
        self._lo = float(lo)
        self._hi = float(hi)
        value = max(self._lo, min(self._hi, self.value()))
        self._syncing = True
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setRange(self._lo - self._offset, self._hi - self._offset)
        if step is not None:
            self.spin.setSingleStep(float(step))
        self.spin.setValue(value - self._offset)
        self._raw = value
        self.slider.setValue(self._value_to_slider(self.value()))
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)
        self._syncing = False

    def apply_spec(self, spec) -> None:
        """Aplica un ``ParamSpec`` nuevo (diálogo de límites) sin reiniciar.

        Cambian el rango, el paso y los decimales del control; el valor
        actual no se toca: si queda fuera del rango nuevo, el rango se amplía
        para contenerlo (como al volcar un resultado).
        """
        value = self.value()
        self.spin.blockSignals(True)
        self.spin.setDecimals(int(spec.decimals))
        self.spin.blockSignals(False)
        self._spec_range = (float(spec.lo), float(spec.hi))
        self.spin.setSingleStep(float(spec.step))
        self._apply_display_range()
        self.set_value(value)

    # ── Cotas de ajuste propias ──────────────────────────────────────────
    def enable_fit_limits(self) -> None:
        """Admite cotas de ajuste propias. Se editan desde el menú del clic
        derecho («Cotas de ajuste…») o desde Ajuste › Cotas por componente;
        en el panel solo queda la marca «↔» junto al nombre. Antes eran dos
        casillas mín/máx por parámetro junto a «fijo», y no cabían."""
        self.limits_enabled = True

    def fit_limits(self) -> tuple[float | None, float | None]:
        return self._fit_limits

    def has_fit_limits(self) -> bool:
        return any(x is not None for x in self._fit_limits)

    def set_fit_limits(self, lo: float | None, hi: float | None) -> None:
        """Pone las cotas propias sin emitir señal (sesión, plantilla)."""
        lo = None if lo is None else float(lo)
        hi = None if hi is None else float(hi)
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo
        self._fit_limits = (lo, hi)
        self._apply_display_range()
        self._update_limits_marker()

    def apply_fit_limits(self, lo: float | None, hi: float | None) -> None:
        """Pone las cotas propias desde la interfaz y avisa si cambiaron."""
        old = self._fit_limits
        self.set_fit_limits(lo, hi)
        if self._fit_limits != old:
            self.limitsChanged.emit()

    def _apply_display_range(self) -> None:
        """Rango del control: el de los límites de parámetros o, si las hay,
        las cotas propias; siempre ampliado para contener el valor."""
        lo, hi = self._spec_range
        u_lo, u_hi = self._fit_limits
        if u_lo is not None:
            lo = u_lo
        if u_hi is not None:
            hi = u_hi
        if hi <= lo:
            hi = lo + max(abs(lo) * 1e-3, 10.0 ** -self.spin.decimals())
        value = self.value()
        self.set_range(min(lo, value), max(hi, value))

    def _update_limits_marker(self) -> None:
        """Con cotas propias, la etiqueta lo indica («↔») y el globo las dice."""
        mark = self.has_fit_limits()
        self.label.setText(f"{self._label_text} ↔" if mark else self._label_text)
        tip = getattr(self, "_help", "")
        if self._extra_tip:
            tip = f"{tip}\n\n{self._extra_tip}" if tip else self._extra_tip
        if self.has_fit_limits():
            lo, hi = self._fit_limits
            off = self._offset
            txt = tr("tooltip.fit_limits_set", lo="−∞" if lo is None else f"{lo - off:.6g}",
                     hi="+∞" if hi is None else f"{hi - off:.6g}",
                     default="Cotas del ajuste: {lo} … {hi}")
            tip = f"{tip}\n\n{txt}" if tip else txt
        self.label.setToolTip(tip)

    def set_extra_tip(self, text: str) -> None:
        """Texto añadido al globo del rótulo (p. ej. la referencia de δ)."""
        self._extra_tip = text or ""
        self._update_limits_marker()

    def set_label_warning(self, warn: bool) -> None:
        """Rótulo en color de aviso (lo mostrado no es lo que se pidió)."""
        self.label.setStyleSheet("color: #b45309" if warn else "")

    def set_label(self, text: str) -> None:
        """Cambia el rótulo conservando la marca de cotas propias."""
        self._label_text = text
        self._update_limits_marker()

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

    def _on_spin_changed(self, shown: float) -> None:
        if self._syncing:
            return
        value = float(shown) + self._offset
        self._raw = value
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
        self.spin.setValue(value - self._offset)
        value = float(self.spin.value()) + self._offset
        self._raw = value
        self.spin.blockSignals(False)
        self._syncing = False
        self.valueChanged.emit(value)

    def is_fixed(self) -> bool:
        return bool(self.fixed_cb.isChecked()) if self.fixed_cb is not None else False

    def set_fixed(self, b: bool) -> None:
        if self.fixed_cb is not None:
            self.fixed_cb.setChecked(bool(b))
