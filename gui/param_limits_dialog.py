"""Diálogo para editar los límites de los controles de parámetros.

Lee los valores actuales (defaults + overrides del usuario) de
``core.param_overrides``, muestra una tabla editable por pestaña y guarda
los cambios en ``~/.config/mossbauer_fe33_gui/param_limits.json``.

Los cambios se aplican en el próximo arranque (se usa al construir los widgets
de control, no en tiempo de ejecución).
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from PySide6 import QtCore, QtWidgets

from core.param_overrides import (
    Category,
    effective_specs,
    load_raw,
    save_raw,
)
from core.params import (
    CALIBRATION_PARAM_SPECS,
    COMPONENT_PARAM_SPECS,
    DISTRIBUTION_PARAM_SPECS,
    ParamSpec,
)
from mossbauer_i18n import tr

# Nombres de columna (índices)
_COL_PARAM   = 0
_COL_DEFAULT = 1
_COL_LO      = 2
_COL_HI      = 3
_COL_STEP    = 4
_COL_DECS    = 5

_HEADERS = ["Parámetro", "Default", "Mín", "Máx", "Paso", "Decimales"]

# Etiquetas amigables para los parámetros (complementan al nombre técnico)
_PARAM_LABELS: dict[str, str] = {
    # Componente
    "delta":        "δ  (despl. isomérico, mm/s)",
    "quad":         "ΔEQ  (cuadrupolo, mm/s)",
    "bhf":          "BHF  (campo hiperfino, T)",
    "gamma1":       "Γ₁  (líneas 1,6  mm/s)",
    "gamma2":       "Γ₂  (relativa 2,5)",
    "gamma3":       "Γ₃  (relativa 3,4)",
    "depth":        "Profundidad",
    "int1":         "I₁₃  (ratio 1,6 / 3,4)",
    "int2":         "I₂₃  (ratio 2,5 / 3,4)",
    "int3":         "I  (líneas 3,4)  [fijo]",
    "texture":      "Textura",
    "beta":         "β  (Kündig, °)",
    "relax_fraction":"Fracción bloqueada",
    "relax_log_nu": "log₁₀ ν  (s⁻¹)",
    "neel_temp_k":  "T  (K)",
    "neel_log10_keff":"log₁₀ K_eff  (J/m³)",
    "neel_mean_d_nm":"d₅₀  (nm)",
    "neel_sigma":   "σ lognormal",
    "neel_log10_tau0":"log₁₀ τ₀  (s)",
    "neel_bins":    "Bins de tamaño",
    # Calibración
    "vmax":         "V_max  (mm/s)",
    "center":       "Centro  (canal)",
    "baseline":     "Línea base",
    "slope":        "Pendiente",
    "voigt_sigma":  "σ Voigt  (mm/s)",
    "sat_scale":    "Escala saturación",
    # Distribución
    "fixed_bhf":    "BHF fijo  (T)",
    "gamma":        "Γ  (mm/s)",
    "bmin":         "B mín  (eje X)",
    "bmax":         "B máx  (eje X)",
    "nbins":        "N bins (eje X)",
    "log_alpha":    "log₁₀ α",
    "qmin":         "Q mín  (eje Y)",
    "qmax":         "Q máx  (eje Y)",
    "qbins":        "N bins (eje Y)",
    "log_alpha_q":  "log₁₀ α_q",
    # Límites exteriores del eje X en modos IS y ΔEQ distribuido
    "is_lo":        "IS mín  (límite exterior eje δ en modo IS)",
    "is_hi":        "IS máx  (límite exterior eje δ en modo IS)",
    "quad_lo":      "ΔEQ mín  (límite exterior eje ΔEQ distribuido)",
    "quad_hi":      "ΔEQ máx  (límite exterior eje ΔEQ distribuido)",
}

_CATEGORY_DEFAULTS = {
    "component":    COMPONENT_PARAM_SPECS,
    "calibration":  CALIBRATION_PARAM_SPECS,
    "distribution": DISTRIBUTION_PARAM_SPECS,
}


class _ParamTable(QtWidgets.QWidget):
    """Widget de tabla editable para una categoría de parámetros."""

    def __init__(self, category: Category, parent=None):
        super().__init__(parent)
        self._category = category
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._table = QtWidgets.QTableWidget(0, len(_HEADERS), self)
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_PARAM, QtWidgets.QHeaderView.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_DEFAULT, QtWidgets.QHeaderView.Stretch
        )
        for col in (_COL_LO, _COL_HI, _COL_STEP, _COL_DECS):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QtWidgets.QHeaderView.Stretch
            )
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self._table)

        btn_reset = QtWidgets.QPushButton("Restablecer pestaña a valores predeterminados")
        btn_reset.clicked.connect(self._reset_to_defaults)
        layout.addWidget(btn_reset)

        self._populate(effective_specs(category))

    def _populate(self, specs: dict[str, ParamSpec]) -> None:
        self._table.setRowCount(0)
        for name, spec in specs.items():
            row = self._table.rowCount()
            self._table.insertRow(row)

            label = _PARAM_LABELS.get(name, name)
            item_name = QtWidgets.QTableWidgetItem(f"{name}  —  {label}")
            item_name.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self._table.setItem(row, _COL_PARAM, item_name)

            for col, val in (
                (_COL_DEFAULT, spec.default),
                (_COL_LO,      spec.lo),
                (_COL_HI,      spec.hi),
                (_COL_STEP,    spec.step),
                (_COL_DECS,    spec.decimals),
            ):
                self._table.setItem(row, col, QtWidgets.QTableWidgetItem(str(val)))

            # Store the param name in the first column's data role
            self._table.item(row, _COL_PARAM).setData(QtCore.Qt.UserRole, name)

    def _reset_to_defaults(self) -> None:
        self._populate(_CATEGORY_DEFAULTS[self._category])

    def collect(self) -> dict[str, dict]:
        """Lee la tabla y devuelve un dict {name: {default, lo, hi, step, decimals}}."""
        result: dict[str, dict] = {}
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, _COL_PARAM)
            if name_item is None:
                continue
            name = name_item.data(QtCore.Qt.UserRole)
            try:
                default  = float(self._table.item(row, _COL_DEFAULT).text())
                lo       = float(self._table.item(row, _COL_LO).text())
                hi       = float(self._table.item(row, _COL_HI).text())
                step     = float(self._table.item(row, _COL_STEP).text())
                decimals = int(float(self._table.item(row, _COL_DECS).text()))
            except (ValueError, AttributeError):
                continue
            result[name] = {
                "default": default, "lo": lo, "hi": hi,
                "step": step, "decimals": decimals,
            }
        return result


class ParamLimitsDialog(QtWidgets.QDialog):
    """Diálogo modal con tres pestañas para editar los límites de parámetros."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("param_limits.title", default="Límites de parámetros"))
        self.setMinimumSize(720, 540)
        self.resize(860, 620)

        layout = QtWidgets.QVBoxLayout(self)

        note = QtWidgets.QLabel(
            tr(
                "param_limits.note",
                default=(
                    "Los cambios se aplican al reiniciar la aplicación. "
                    "Se guardan en ~/.config/mossbauer_fe33_gui/param_limits.json"
                ),
            )
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(note)

        self._tabs = QtWidgets.QTabWidget()
        self._tab_component    = _ParamTable("component",    self)
        self._tab_calibration  = _ParamTable("calibration",  self)
        self._tab_distribution = _ParamTable("distribution", self)

        self._tabs.addTab(self._tab_component,    tr("param_limits.tab_component",    default="Componentes"))
        self._tabs.addTab(self._tab_calibration,  tr("param_limits.tab_calibration",  default="Calibración"))
        self._tabs.addTab(self._tab_distribution, tr("param_limits.tab_distribution", default="Distribución"))
        layout.addWidget(self._tabs)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.button(QtWidgets.QDialogButtonBox.Save).setText(
            tr("param_limits.btn_save", default="Guardar y cerrar")
        )
        btn_box.accepted.connect(self._save_and_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _save_and_accept(self) -> None:
        data = {
            "component":    self._tab_component.collect(),
            "calibration":  self._tab_calibration.collect(),
            "distribution": self._tab_distribution.collect(),
        }
        try:
            save_raw(data)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self,
                tr("param_limits.save_error_title", default="Error al guardar"),
                str(exc),
            )
            return
        QtWidgets.QMessageBox.information(
            self,
            tr("param_limits.saved_title", default="Guardado"),
            tr(
                "param_limits.saved_msg",
                default="Los límites se han guardado. Se aplicarán al reiniciar la aplicación.",
            ),
        )
        self.accept()
