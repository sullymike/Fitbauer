"""Ventana «Opciones avanzadas de ajuste».

Sustituye a los submenús sueltos (perfil, verosimilitud, pérdida robusta,
absorbente, convenios…) por una ventana con pestañas y una línea de
explicación por opción. No guarda estado propio: cada control refleja y
cambia la ``QAction`` (o el ``QSpinBox``) que ya existía en la ventana
principal, que sigue siendo la fuente que leen la sesión, los presets de
disposición y el ajuste. Así, cambiar una opción aquí o al cargar una sesión
deja las dos vistas iguales.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from mossbauer_i18n import tr


def _plain(text: str) -> str:
    """Rótulo sin «…», «...» ni «:» finales ni el «&» de los atajos."""
    t = text.replace("&", "").strip()
    for tail in ("…", "...", ":"):
        if t.endswith(tail):
            t = t[: -len(tail)].rstrip()
    return t


class AdvancedOptionsDialog(QtWidgets.QDialog):
    """No modal: se puede dejar abierta mientras se ajusta."""

    def __init__(self, win):
        super().__init__(win)
        self._win = win
        self.setWindowTitle(_plain(tr("options.advanced_fit")))
        self.resize(800, 540)
        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(tr("adv.intro"))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.tabs = QtWidgets.QTabWidget()
        lay.addWidget(self.tabs, stretch=1)
        w = win
        self._tab(tr("adv.tab_model"), [
            ("combo", tr("options.line_profile"), w.profile_action_group, tr("adv.desc.profile")),
            ("combo", tr("absorber.model_label"), w.absorber_action_group, tr("adv.desc.absorber")),
            ("spin", tr("options.channel_sub", default="Integración por canal"),
             getattr(w, "_channel_sub_spin", None), tr("tooltip.channel_sub")),
            ("check", None, getattr(w, "act_wide_delta", None), tr("adv.desc.wide_delta")),
        ])
        self._tab(tr("adv.tab_stats"), [
            ("combo", tr("options.likelihood"), w.likelihood_action_group, tr("adv.desc.likelihood")),
            ("combo", tr("options.robust_loss"), w.loss_action_group, tr("adv.desc.loss")),
            ("check", None, getattr(w, "act_propagate", None), tr("adv.desc.propagate")),
        ])
        self._tab(tr("adv.tab_search"), [
            ("spin", tr("options.multistart_n"), getattr(w, "_multistart_spin", None),
             tr("adv.desc.multistart")),
            ("check", None, getattr(w, "act_global_opt", None), tr("adv.desc.global_opt")),
            ("check", None, getattr(w, "act_auto_global", None), tr("adv.desc.auto_global")),
        ])
        conv = []
        for kind, title_key, tip_key in (
                ("sextet_pattern", "conventions.sextet_title", "conventions.sextet_tip"),
                ("intensity_convention", "conventions.intensity_title", "conventions.intensity_tip"),
                ("relax_convention", "conventions.relax_title", "conventions.relax_tip")):
            grupo = getattr(w, f"_{kind}_action_group", None)
            conv.append(("combo", tr(title_key), grupo, tr(tip_key)))
        self._tab(_plain(tr("conventions.menu")), conv, note=tr("adv.conventions_note"))
        self._tab(tr("param_limits.tab_distribution"), [
            ("check", None, getattr(w, "act_add_sharp", None), tr("adv.desc.add_sharp")),
        ])
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.close)
        lay.addWidget(bb)

    # ── construcción ────────────────────────────────────────────────────
    def _tab(self, title: str, rows, note: str = "") -> None:
        page = QtWidgets.QWidget()
        form = QtWidgets.QVBoxLayout(page)
        for kind, label, source, desc in rows:
            if source is None:
                continue
            box = QtWidgets.QVBoxLayout()
            box.setSpacing(2)
            if kind == "check":
                ctl = self._bind_check(source)
                box.addWidget(ctl)
            else:
                row = QtWidgets.QHBoxLayout()
                lab = QtWidgets.QLabel(_plain(label) + ":")
                row.addWidget(lab)
                ctl = self._bind_combo(source) if kind == "combo" else self._bind_spin(source)
                row.addWidget(ctl, stretch=1 if kind == "combo" else 0)
                if kind != "combo":
                    row.addStretch(1)
                box.addLayout(row)
            if desc:
                d = QtWidgets.QLabel(desc)
                d.setWordWrap(True)
                d.setContentsMargins(18, 0, 0, 0)
                pal = d.palette()
                pal.setColor(QtGui.QPalette.ColorRole.WindowText,
                             pal.color(QtGui.QPalette.ColorGroup.Disabled,
                                       QtGui.QPalette.ColorRole.WindowText))
                d.setPalette(pal)
                box.addWidget(d)
                ctl.setToolTip(desc)
            form.addLayout(box)
            form.addSpacing(8)
        if note:
            n = QtWidgets.QLabel(note)
            n.setWordWrap(True)
            form.addWidget(n)
        form.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, title)

    def _bind_combo(self, group: QtGui.QActionGroup) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        actions = list(group.actions())
        for a in actions:
            combo.addItem(_plain(a.text()))

        def sync(*_):
            idx = next((i for i, a in enumerate(actions) if a.isChecked()), -1)
            combo.blockSignals(True)
            combo.setCurrentIndex(idx)
            combo.blockSignals(False)

        def chosen(i: int) -> None:
            if 0 <= i < len(actions) and not actions[i].isChecked():
                actions[i].trigger()
            sync()      # si la acción se negó (p. ej. pidió confirmación), se vuelve

        combo.activated.connect(chosen)
        for a in actions:
            a.toggled.connect(sync)
        sync()
        return combo

    def _bind_check(self, action: QtGui.QAction) -> QtWidgets.QCheckBox:
        cb = QtWidgets.QCheckBox(_plain(action.text()))
        cb.setChecked(action.isChecked())
        cb.toggled.connect(lambda b: action.isChecked() != b and action.setChecked(b))

        def sync(b: bool) -> None:
            cb.blockSignals(True)
            cb.setChecked(b)
            cb.blockSignals(False)

        action.toggled.connect(sync)
        return cb

    def _bind_spin(self, src: QtWidgets.QSpinBox) -> QtWidgets.QSpinBox:
        sp = QtWidgets.QSpinBox()
        sp.setRange(src.minimum(), src.maximum())
        sp.setValue(src.value())
        sp.setMinimumWidth(70)
        sp.valueChanged.connect(lambda v: src.value() != v and src.setValue(v))

        def sync(v: int) -> None:
            sp.blockSignals(True)
            sp.setRange(src.minimum(), src.maximum())
            sp.setValue(v)
            sp.blockSignals(False)

        src.valueChanged.connect(sync)
        return sp


class AdvancedOptionsMixin:
    def on_advanced_options(self) -> None:
        dlg = getattr(self, "_adv_dialog", None)
        if dlg is None:
            dlg = AdvancedOptionsDialog(self)
            self._adv_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
