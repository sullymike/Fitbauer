"""Candado de «fijar/liberar» para un grupo de parámetros.

Lo usan cada componente (sus parámetros ajustables) y el botón global junto a
«Ajustar» (línea base + todos los componentes activos). Un clic:

* libre o parcial → fija todos y recuerda cuáles estaban fijados a mano;
* fijo → vuelve a como estaba antes de fijarlo (si estaba libre, libera todo).

«Fijar todos» y «Liberar todos» explícitos van en el menú del candado y borran
la memoria. La memoria se conserva aunque luego se toquen parámetros a mano:
liberar una componente tras un «fijar todo» global deja el global parcial, y
al volver a fijarlo y liberarlo tiene que seguir sabiendo cómo estaba.
"""
from __future__ import annotations

from typing import Callable, Iterable

from PySide6 import QtCore, QtGui, QtWidgets

from mossbauer_i18n import tr

FREE, PARTIAL, FIXED, EMPTY = "free", "partial", "fixed", "empty"


class FixGroup:
    """Estado y memoria de un grupo; ``controls`` da los ParamControl vigentes
    (cambian con el tipo de componente o al activar componentes)."""

    def __init__(self, controls: Callable[[], Iterable],
                 fallback: Callable[[], dict | None] | None = None):
        self._controls = controls
        self._fallback = fallback
        self.memory: dict | None = None
        self.busy = False

    def controls(self) -> list:
        return list(self._controls())

    def state(self) -> str:
        ctls = self.controls()
        if not ctls:
            return EMPTY
        n = sum(1 for c in ctls if c.is_fixed())
        return FIXED if n == len(ctls) else FREE if n == 0 else PARTIAL

    def _apply(self, values: dict) -> None:
        """Cambia las casillas sin la cadena de cada parámetro (fixedChanged →
        paramChanged → recalcular y redibujar el modelo): con 11 parámetros
        eran 11 refrescos del gráfico por clic, y fijar no cambia la curva.
        Quien usa el grupo hace luego una sola actualización ligera."""
        self.busy = True
        try:
            for ctl, v in values.items():
                old = ctl.blockSignals(True)
                try:
                    ctl.set_fixed(bool(v))
                finally:
                    ctl.blockSignals(old)
        finally:
            self.busy = False

    def toggle(self) -> None:
        ctls = self.controls()
        if self.state() == FIXED:
            mem = self.memory
            if mem is None and self._fallback is not None:
                mem = self._fallback()
            self.memory = None
            self._apply({c: bool(mem and mem.get(c, False)) for c in ctls})
        else:
            self.memory = {c: c.is_fixed() for c in ctls}
            self._apply({c: True for c in ctls})

    def set_all(self, value: bool) -> None:
        self.memory = None
        self._apply({c: value for c in self.controls()})

    def restore_text_key(self) -> str:
        """Qué hará un clic, para el rótulo y el globo."""
        st = self.state()
        if st != FIXED:
            return "fixlock.fix_all"
        mem = self.memory
        if mem is None and self._fallback is not None:
            mem = self._fallback()
        if mem and any(mem.get(c, False) for c in self.controls()):
            return "fixlock.restore"
        return "fixlock.free_all"



def lock_icon(state: str, color: QtGui.QColor, size: int = 16) -> QtGui.QIcon:
    """Candado dibujado (no depende de fuentes con emoji): abierto = libre,
    cerrado hueco con media carga = parcial, cerrado relleno = fijo."""
    pm = QtGui.QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(color, 1.6)
    p.setPen(pen)
    s = float(size)
    body = QtCore.QRectF(s * 0.18, s * 0.46, s * 0.64, s * 0.46)
    # Arco del candado: abierto, desplazado hacia arriba y a la derecha.
    arc = QtCore.QRectF(s * 0.30, s * 0.10, s * 0.40, s * 0.62)
    if state == FREE:
        arc.translate(s * 0.16, -s * 0.06)
        path = QtGui.QPainterPath()
        path.arcMoveTo(arc, 0)
        path.arcTo(arc, 0, 180)
        p.drawPath(path)
    else:
        p.drawArc(arc, 0, 180 * 16)
    p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(body, 1.5, 1.5)
    if state == FIXED:
        p.fillRect(body.adjusted(0.8, 0.8, -0.8, -0.8), color)
    elif state == PARTIAL:
        half = body.adjusted(0.8, body.height() / 2, -0.8, -0.8)
        p.fillRect(half, color)
    p.end()
    return QtGui.QIcon(pm)


class FixLockButton(QtWidgets.QToolButton):
    """Botón con el candado. ``with_text``: el global enseña además lo que
    hará el clic; el de componente, solo el icono (el globo lo dice)."""

    def __init__(self, group: FixGroup, *, with_text: bool = False, parent=None,
                 on_changed: Callable[[], None] | None = None):
        super().__init__(parent)
        self.group = group
        self._with_text = with_text
        self._on_changed = on_changed
        self.setAutoRaise(not with_text)
        if with_text:
            self.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup
                          if with_text else QtWidgets.QToolButton.ToolButtonPopupMode.DelayedPopup)
        menu = QtWidgets.QMenu(self)
        menu.addAction(tr("fixlock.fix_all"), lambda: self._do(lambda: group.set_all(True)))
        menu.addAction(tr("fixlock.free_all"), lambda: self._do(lambda: group.set_all(False)))
        self.setMenu(menu)
        if not with_text:
            # En el de componente la flecha estorba: menú con clic derecho.
            self.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.DelayedPopup)
            self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            self.customContextMenuRequested.connect(
                lambda pos: menu.exec(self.mapToGlobal(pos)))
            self.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        self.clicked.connect(lambda: self._do(group.toggle))
        self.refresh()

    def _do(self, fn) -> None:
        fn()
        self.refresh()
        if self._on_changed is not None:
            self._on_changed()

    def refresh(self) -> None:
        st = self.group.state()
        color = self.palette().color(QtGui.QPalette.ColorRole.ButtonText)
        self.setIcon(lock_icon(FIXED if st == EMPTY else st, color))
        key = self.group.restore_text_key()
        state_txt = tr(f"fixlock.state_{st}")
        if self._with_text:
            self.setText(tr(key))
        self.setToolTip(tr("fixlock.tip", state=state_txt, action=tr(key)))
        self.setEnabled(st != EMPTY)
