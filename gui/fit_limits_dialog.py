"""Cotas de ajuste propias de los parámetros de componente.

Dos sitios para editarlas, ninguno en el panel (allí solo queda la marca «↔»
junto al nombre del parámetro que tiene cota propia):

* clic derecho sobre un parámetro → «Cotas de ajuste…»: una ventanita con
  mín/máx, la cota general como referencia y «Quitar»;
* Ajuste › Cotas por componente…: una tabla con todos los parámetros
  ajustables de las componentes activas.

Una casilla vacía = la cota general en ese lado (la de «Límites de
parámetros…», o la del código).
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from core.params import COMPONENT_FIT_BOUNDS
from mossbauer_i18n import tr


def general_bound(name: str) -> tuple[float, float] | None:
    """Cota general del parámetro: la cambiada en Límites de parámetros o,
    si no, la del código."""
    try:
        from core.param_overrides import component_fit_bound_overrides
        over = component_fit_bound_overrides().get(name)
    except Exception:
        over = None
    code = COMPONENT_FIT_BOUNDS.get(name)
    if code is None and over is None:
        return None
    # Las cambiadas solo traen el extremo que difiere; el otro es None y se
    # queda el del código.
    lo = over[0] if over and over[0] is not None else (code[0] if code else None)
    hi = over[1] if over and over[1] is not None else (code[1] if code else None)
    if lo is None or hi is None:
        return None
    return (float(lo), float(hi))


def _fmt(x: float | None, decimals: int) -> str:
    return "" if x is None else f"{x:.{decimals}f}"


def _parse(text: str) -> float | None:
    text = text.strip().replace(",", ".")
    return float(text) if text else None


def _general_text(name: str) -> str:
    g = general_bound(name)
    return "—" if g is None else f"{g[0]:g} … {g[1]:g}"


def _limit_edit(name: str, side: int, decimals: int, value: float | None) -> QtWidgets.QLineEdit:
    ed = QtWidgets.QLineEdit(_fmt(value, decimals))
    g = general_bound(name)
    ed.setPlaceholderText(f"{g[side]:g}" if g else ("mín" if side == 0 else "máx"))
    ed.setToolTip(tr("limits.empty_tip"))
    return ed


class ParamLimitsDialog(QtWidgets.QDialog):
    """Cotas de un solo parámetro (clic derecho → «Cotas de ajuste…»)."""

    def __init__(self, parent, ctl, title: str, name: str):
        super().__init__(parent)
        self.setWindowTitle(tr("limits.param_title", param=title))
        self._ctl = ctl
        dec = ctl.spin.decimals()
        lo, hi = ctl.fit_limits()
        lay = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        self.ed_lo = _limit_edit(name, 0, dec, lo)
        self.ed_hi = _limit_edit(name, 1, dec, hi)
        form.addRow(tr("limits.min"), self.ed_lo)
        form.addRow(tr("limits.max"), self.ed_hi)
        form.addRow(tr("limits.general"), QtWidgets.QLabel(_general_text(name)))
        form.addRow(tr("limits.current"), QtWidgets.QLabel(_fmt(ctl.value(), dec)))
        lay.addLayout(form)
        note = QtWidgets.QLabel(tr("limits.note"))
        note.setWordWrap(True)
        lay.addWidget(note)
        self.error = QtWidgets.QLabel()
        self.error.setStyleSheet("color: #b91c1c")
        self.error.hide()
        lay.addWidget(self.error)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok
                                        | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self.btn_clear = bb.addButton(tr("limits.clear"),
                                      QtWidgets.QDialogButtonBox.ButtonRole.ResetRole)
        self.btn_clear.clicked.connect(self._clear)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _clear(self) -> None:
        self._ctl.apply_fit_limits(None, None)
        self.accept()

    def _accept(self) -> None:
        try:
            lo, hi = _parse(self.ed_lo.text()), _parse(self.ed_hi.text())
        except ValueError:
            self.error.setText(tr("limits.not_number"))
            self.error.show()
            return
        self._ctl.apply_fit_limits(lo, hi)
        self.accept()


class ComponentLimitsDialog(QtWidgets.QDialog):
    """Ajuste › Cotas por componente…: todas en una tabla."""

    COLS = ("limits.col_comp", "limits.col_param", "limits.col_value",
            "limits.col_general", "limits.min", "limits.max")

    def __init__(self, win):
        super().__init__(win)
        self.setWindowTitle(tr("limits.table_title"))
        self.resize(640, 520)
        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(tr("limits.table_intro"))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.table = QtWidgets.QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels([tr(k) for k in self.COLS])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self._rows: list[tuple] = []          # (ctl, ed_lo, ed_hi)
        for cp in win.components_panels:
            if not cp.enabled.isChecked():
                continue
            for name, ctl in cp.params.items():
                if ctl not in cp.lockable_params() or not ctl.limits_enabled:
                    continue
                self._add_row(cp, name, ctl)
        lay.addWidget(self.table, stretch=1)
        self.error = QtWidgets.QLabel()
        self.error.setStyleSheet("color: #b91c1c")
        self.error.hide()
        lay.addWidget(self.error)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok
                                        | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        clear = bb.addButton(tr("limits.clear_all"),
                             QtWidgets.QDialogButtonBox.ButtonRole.ResetRole)
        clear.clicked.connect(self._clear_all)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _add_row(self, cp, name: str, ctl) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        dec = ctl.spin.decimals()
        kind = tr(f"kind.{cp.kind}", default=cp.kind)
        textos = (f"{cp.idx} · {kind}", ctl.label.text().rstrip(" ↔"),
                  _fmt(ctl.value(), dec), _general_text(name))
        for c, t in enumerate(textos):
            item = QtWidgets.QTableWidgetItem(t)
            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            if ctl.is_fixed():
                item.setToolTip(tr("checkbox.fixed"))
            self.table.setItem(r, c, item)
        lo, hi = ctl.fit_limits()
        ed_lo = _limit_edit(name, 0, dec, lo)
        ed_hi = _limit_edit(name, 1, dec, hi)
        for ed in (ed_lo, ed_hi):
            ed.setFrame(False)
        self.table.setCellWidget(r, 4, ed_lo)
        self.table.setCellWidget(r, 5, ed_hi)
        self._rows.append((ctl, ed_lo, ed_hi))

    def _clear_all(self) -> None:
        for _ctl, ed_lo, ed_hi in self._rows:
            ed_lo.clear()
            ed_hi.clear()

    def _accept(self) -> None:
        nuevos = []
        for r, (ctl, ed_lo, ed_hi) in enumerate(self._rows):
            try:
                nuevos.append((ctl, _parse(ed_lo.text()), _parse(ed_hi.text())))
            except ValueError:
                self.error.setText(tr("limits.not_number_row", row=r + 1))
                self.error.show()
                self.table.selectRow(r)
                return
        for ctl, lo, hi in nuevos:
            ctl.apply_fit_limits(lo, hi)
        self.accept()
