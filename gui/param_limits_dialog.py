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
    effective_fit_init_specs,
    effective_peak_detection_specs,
    load_raw,
    save_raw,
)
from core.params import (
    CALIBRATION_PARAM_SPECS,
    COMPONENT_PARAM_SPECS,
    DISTRIBUTION_PARAM_SPECS,
    FIT_INIT_SPECS,
    PEAK_DETECTION_SPECS,
    ParamSpec,
)
from mossbauer_i18n import tr, get_language

# Nombres de columna (índices)
_COL_PARAM   = 0
_COL_DEFAULT = 1
_COL_LO      = 2
_COL_HI      = 3
_COL_STEP    = 4
_COL_DECS    = 5

# Etiquetas amigables para los parámetros (complementan al nombre técnico).
# Se mantienen aquí (en vez de en los catálogos compartidos) por ser notación
# científica muy específica de este diálogo. Se eligen por idioma activo.
_PARAM_LABELS_BY_LANG: dict[str, dict[str, str]] = {
    "es": {
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
        "vmax":         "V_max  (mm/s)",
        "center":       "Centro  (canal)",
        "baseline":     "Línea base",
        "slope":        "Pendiente",
        "voigt_sigma":  "σ Voigt  (mm/s)",
        "sat_scale":    "Escala saturación",
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
        "is_lo":        "IS mín  (límite exterior eje δ en modo IS)",
        "is_hi":        "IS máx  (límite exterior eje δ en modo IS)",
        "quad_lo":      "ΔEQ mín  (límite exterior eje ΔEQ distribuido)",
        "quad_hi":      "ΔEQ máx  (límite exterior eje ΔEQ distribuido)",
        "sextet_bhf_min":      "BHF mín  (detección de sextetes, T)",
        "sextet_bhf_max":      "BHF máx  (detección de sextetes, T)",
        "sextet_2pk_bhf_min":  "BHF mín  (estimación 2 picos, T)",
        "init_bhf_min":        "BHF mín  (clip en inicialización, T)",
        "init_gamma_min":      "Γ mín  (clip en inicialización, mm/s)",
        "init_gamma_max":      "Γ máx  (clip en inicialización, mm/s)",
        "init_delta_lo":       "δ mín  (clip en inicialización, mm/s)",
        "init_delta_hi":       "δ máx  (clip en inicialización, mm/s)",
        "init_depth_min":      "Profundidad mín  (clip en inicialización)",
        "init_depth_max":      "Profundidad máx  (clip en inicialización)",
        "doublet_sep_min":     "Separación mín doblete  (mm/s)",
        "doublet_sep_max":     "Separación máx doblete  (mm/s)",
        "lcurve_alpha_lo":     "L-curve: log₁₀ α mín del barrido",
        "lcurve_alpha_hi":     "L-curve: log₁₀ α máx del barrido",
        "lcurve_n_points":     "L-curve: número de puntos",
        "bootstrap_nrep":      "Bootstrap: réplicas por defecto",
        "multistart_n_max":    "Arranques múltiples: máximo del spinner",
        "min_dist_factor":     "Factor distancia mínima entre picos (×dv)",
        "height_thr_factor":   "Factor umbral de altura de pico",
        "prom_thr_factor":     "Factor umbral de prominencia de pico",
        "min_separation":      "Separación mínima absoluta (mm/s)",
        "score_tol":           "Tolerancia RMS sextete (mm/s)",
        "score_tol_factor":    "Factor tolerancia RMS según BHF",
        "narrow_tol_factor":   "Factor tolerancia estrecha (×anchura mediana)",
        "narrow_tol_min":      "Tolerancia estrecha mínima (mm/s)",
        "match_tol":           "Tolerancia máx. match pico-línea (mm/s)",
        "singlet_dominance":   "Ratio d₀/d₁ para clasificar singlete",
        "doublet_ratio_min":   "Ratio mín. d₁/d₀ para doblete",
        "doublet_ratio_max":   "Ratio máx. d₂/d₀ para doblete",
        "plotly_tol_factor":   "Factor tolerancia marcadores de mínimos",
        "plotly_tol_min":      "Tolerancia mínima marcadores de mínimos (mm/s)",
    },
    "en": {
        "delta":        "δ  (isomer shift, mm/s)",
        "quad":         "ΔEQ  (quadrupole, mm/s)",
        "bhf":          "BHF  (hyperfine field, T)",
        "gamma1":       "Γ₁  (lines 1,6  mm/s)",
        "gamma2":       "Γ₂  (relative 2,5)",
        "gamma3":       "Γ₃  (relative 3,4)",
        "depth":        "Depth",
        "int1":         "I₁₃  (ratio 1,6 / 3,4)",
        "int2":         "I₂₃  (ratio 2,5 / 3,4)",
        "int3":         "I  (lines 3,4)  [fixed]",
        "texture":      "Texture",
        "beta":         "β  (Kündig, °)",
        "relax_fraction":"Blocked fraction",
        "relax_log_nu": "log₁₀ ν  (s⁻¹)",
        "neel_temp_k":  "T  (K)",
        "neel_log10_keff":"log₁₀ K_eff  (J/m³)",
        "neel_mean_d_nm":"d₅₀  (nm)",
        "neel_sigma":   "σ lognormal",
        "neel_log10_tau0":"log₁₀ τ₀  (s)",
        "neel_bins":    "Size bins",
        "vmax":         "V_max  (mm/s)",
        "center":       "Center  (channel)",
        "baseline":     "Baseline",
        "slope":        "Slope",
        "voigt_sigma":  "σ Voigt  (mm/s)",
        "sat_scale":    "Saturation scale",
        "fixed_bhf":    "Fixed BHF  (T)",
        "gamma":        "Γ  (mm/s)",
        "bmin":         "B min  (X axis)",
        "bmax":         "B max  (X axis)",
        "nbins":        "N bins (X axis)",
        "log_alpha":    "log₁₀ α",
        "qmin":         "Q min  (Y axis)",
        "qmax":         "Q max  (Y axis)",
        "qbins":        "N bins (Y axis)",
        "log_alpha_q":  "log₁₀ α_q",
        "is_lo":        "IS min  (outer δ-axis bound in IS mode)",
        "is_hi":        "IS max  (outer δ-axis bound in IS mode)",
        "quad_lo":      "ΔEQ min  (outer bound of distributed ΔEQ axis)",
        "quad_hi":      "ΔEQ max  (outer bound of distributed ΔEQ axis)",
        "sextet_bhf_min":      "BHF min  (sextet detection, T)",
        "sextet_bhf_max":      "BHF max  (sextet detection, T)",
        "sextet_2pk_bhf_min":  "BHF min  (2-peak estimate, T)",
        "init_bhf_min":        "BHF min  (initialization clip, T)",
        "init_gamma_min":      "Γ min  (initialization clip, mm/s)",
        "init_gamma_max":      "Γ max  (initialization clip, mm/s)",
        "init_delta_lo":       "δ min  (initialization clip, mm/s)",
        "init_delta_hi":       "δ max  (initialization clip, mm/s)",
        "init_depth_min":      "Depth min  (initialization clip)",
        "init_depth_max":      "Depth max  (initialization clip)",
        "doublet_sep_min":     "Doublet min separation  (mm/s)",
        "doublet_sep_max":     "Doublet max separation  (mm/s)",
        "lcurve_alpha_lo":     "L-curve: log₁₀ α min of the scan",
        "lcurve_alpha_hi":     "L-curve: log₁₀ α max of the scan",
        "lcurve_n_points":     "L-curve: number of points",
        "bootstrap_nrep":      "Bootstrap: default replicas",
        "multistart_n_max":    "Multistart: spinner maximum",
        "min_dist_factor":     "Min peak distance factor (×dv)",
        "height_thr_factor":   "Peak height threshold factor",
        "prom_thr_factor":     "Peak prominence threshold factor",
        "min_separation":      "Absolute minimum separation (mm/s)",
        "score_tol":           "Sextet RMS tolerance (mm/s)",
        "score_tol_factor":    "RMS tolerance factor vs BHF",
        "narrow_tol_factor":   "Narrow tolerance factor (×median width)",
        "narrow_tol_min":      "Minimum narrow tolerance (mm/s)",
        "match_tol":           "Max peak-line match tolerance (mm/s)",
        "singlet_dominance":   "d₀/d₁ ratio to classify singlet",
        "doublet_ratio_min":   "Min d₁/d₀ ratio for doublet",
        "doublet_ratio_max":   "Max d₂/d₀ ratio for doublet",
        "plotly_tol_factor":   "Minima marker tolerance factor",
        "plotly_tol_min":      "Minimum minima-marker tolerance (mm/s)",
    },
    "fr": {
        "delta":        "δ  (déplacement isomérique, mm/s)",
        "quad":         "ΔEQ  (quadrupôle, mm/s)",
        "bhf":          "BHF  (champ hyperfin, T)",
        "gamma1":       "Γ₁  (raies 1,6  mm/s)",
        "gamma2":       "Γ₂  (relative 2,5)",
        "gamma3":       "Γ₃  (relative 3,4)",
        "depth":        "Profondeur",
        "int1":         "I₁₃  (rapport 1,6 / 3,4)",
        "int2":         "I₂₃  (rapport 2,5 / 3,4)",
        "int3":         "I  (raies 3,4)  [fixe]",
        "texture":      "Texture",
        "beta":         "β  (Kündig, °)",
        "relax_fraction":"Fraction bloquée",
        "relax_log_nu": "log₁₀ ν  (s⁻¹)",
        "neel_temp_k":  "T  (K)",
        "neel_log10_keff":"log₁₀ K_eff  (J/m³)",
        "neel_mean_d_nm":"d₅₀  (nm)",
        "neel_sigma":   "σ lognormale",
        "neel_log10_tau0":"log₁₀ τ₀  (s)",
        "neel_bins":    "Bins de taille",
        "vmax":         "V_max  (mm/s)",
        "center":       "Centre  (canal)",
        "baseline":     "Ligne de base",
        "slope":        "Pente",
        "voigt_sigma":  "σ Voigt  (mm/s)",
        "sat_scale":    "Échelle de saturation",
        "fixed_bhf":    "BHF fixe  (T)",
        "gamma":        "Γ  (mm/s)",
        "bmin":         "B min  (axe X)",
        "bmax":         "B max  (axe X)",
        "nbins":        "N bins (axe X)",
        "log_alpha":    "log₁₀ α",
        "qmin":         "Q min  (axe Y)",
        "qmax":         "Q max  (axe Y)",
        "qbins":        "N bins (axe Y)",
        "log_alpha_q":  "log₁₀ α_q",
        "is_lo":        "IS min  (limite externe de l'axe δ en mode IS)",
        "is_hi":        "IS max  (limite externe de l'axe δ en mode IS)",
        "quad_lo":      "ΔEQ min  (limite externe de l'axe ΔEQ distribué)",
        "quad_hi":      "ΔEQ max  (limite externe de l'axe ΔEQ distribué)",
        "sextet_bhf_min":      "BHF min  (détection de sextets, T)",
        "sextet_bhf_max":      "BHF max  (détection de sextets, T)",
        "sextet_2pk_bhf_min":  "BHF min  (estimation 2 pics, T)",
        "init_bhf_min":        "BHF min  (clip à l'initialisation, T)",
        "init_gamma_min":      "Γ min  (clip à l'initialisation, mm/s)",
        "init_gamma_max":      "Γ max  (clip à l'initialisation, mm/s)",
        "init_delta_lo":       "δ min  (clip à l'initialisation, mm/s)",
        "init_delta_hi":       "δ max  (clip à l'initialisation, mm/s)",
        "init_depth_min":      "Profondeur min  (clip à l'initialisation)",
        "init_depth_max":      "Profondeur max  (clip à l'initialisation)",
        "doublet_sep_min":     "Séparation min doublet  (mm/s)",
        "doublet_sep_max":     "Séparation max doublet  (mm/s)",
        "lcurve_alpha_lo":     "L-curve : log₁₀ α min du balayage",
        "lcurve_alpha_hi":     "L-curve : log₁₀ α max du balayage",
        "lcurve_n_points":     "L-curve : nombre de points",
        "bootstrap_nrep":      "Bootstrap : répliques par défaut",
        "multistart_n_max":    "Multi-départs : maximum du sélecteur",
        "min_dist_factor":     "Facteur distance min entre pics (×dv)",
        "height_thr_factor":   "Facteur seuil de hauteur de pic",
        "prom_thr_factor":     "Facteur seuil de proéminence de pic",
        "min_separation":      "Séparation minimale absolue (mm/s)",
        "score_tol":           "Tolérance RMS sextet (mm/s)",
        "score_tol_factor":    "Facteur tolérance RMS selon BHF",
        "narrow_tol_factor":   "Facteur tolérance étroite (×largeur médiane)",
        "narrow_tol_min":      "Tolérance étroite minimale (mm/s)",
        "match_tol":           "Tolérance max correspondance pic-raie (mm/s)",
        "singlet_dominance":   "Rapport d₀/d₁ pour classer un singulet",
        "doublet_ratio_min":   "Rapport min d₁/d₀ pour doublet",
        "doublet_ratio_max":   "Rapport max d₂/d₀ pour doublet",
        "plotly_tol_factor":   "Facteur tolérance marqueurs de minima",
        "plotly_tol_min":      "Tolérance minimale marqueurs de minima (mm/s)",
    },
}


def _param_labels() -> dict[str, str]:
    """Etiquetas de parámetro para el idioma activo (con fallback a ES)."""
    return _PARAM_LABELS_BY_LANG.get(get_language(), _PARAM_LABELS_BY_LANG["es"])


def _headers() -> list[str]:
    return [
        tr("param_limits.col_param",   default="Parámetro"),
        tr("param_limits.col_default", default="Default"),
        tr("param_limits.col_min",     default="Mín"),
        tr("param_limits.col_max",     default="Máx"),
        tr("param_limits.col_step",    default="Paso"),
        tr("param_limits.col_decimals",default="Decimales"),
    ]

_CATEGORY_DEFAULTS = {
    "component":      COMPONENT_PARAM_SPECS,
    "calibration":    CALIBRATION_PARAM_SPECS,
    "distribution":   DISTRIBUTION_PARAM_SPECS,
    "fit_init":       FIT_INIT_SPECS,
    "peak_detection": PEAK_DETECTION_SPECS,
}


class _ParamTable(QtWidgets.QWidget):
    """Widget de tabla editable para una categoría de parámetros."""

    def __init__(self, category: Category, parent=None):
        super().__init__(parent)
        self._category = category
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        headers = _headers()
        self._table = QtWidgets.QTableWidget(0, len(headers), self)
        self._table.setHorizontalHeaderLabels(headers)
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

        btn_reset = QtWidgets.QPushButton(
            tr("param_limits.btn_reset",
               default="Restablecer pestaña a valores predeterminados"))
        btn_reset.clicked.connect(self._reset_to_defaults)
        layout.addWidget(btn_reset)

        self._populate(effective_specs(category))

    def _populate(self, specs: dict[str, ParamSpec]) -> None:
        self._table.setRowCount(0)
        for name, spec in specs.items():
            row = self._table.rowCount()
            self._table.insertRow(row)

            label = _param_labels().get(name, name)
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
        self._tab_fit_init      = _ParamTable("fit_init",       self)
        self._tab_peak_detect   = _ParamTable("peak_detection", self)

        self._tabs.addTab(self._tab_component,    tr("param_limits.tab_component",    default="Componentes"))
        self._tabs.addTab(self._tab_calibration,  tr("param_limits.tab_calibration",  default="Calibración"))
        self._tabs.addTab(self._tab_distribution, tr("param_limits.tab_distribution", default="Distribución"))
        self._tabs.addTab(self._tab_fit_init,
                          tr("param_limits.tab_fit_init", default="Inicialización del ajuste"))
        self._tabs.addTab(self._tab_peak_detect,
                          tr("param_limits.tab_peak_detection", default="Detección de picos (avanzado)"))
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
            "component":     self._tab_component.collect(),
            "calibration":   self._tab_calibration.collect(),
            "distribution":  self._tab_distribution.collect(),
            "fit_init":      self._tab_fit_init.collect(),
            "peak_detection":self._tab_peak_detect.collect(),
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
