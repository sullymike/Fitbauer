"""Composición ordenada de mixins de la ventana principal Qt.

El orden sigue las dependencias prácticas:
1. construcción visual y menús,
2. layout/settings,
3. estado del modelo y carga de datos,
4. acciones de ajuste/visualización,
5. entradas/salidas y servicios externos.
"""
from __future__ import annotations

from gui.compat import HistoricalRuntimeCompatMixin
from gui.main_layout import MainLayoutMixin
from gui.menu_builder import MenuBuilderMixin
from gui.layout_manager import LayoutSettingsMixin
from gui.model_workflow import ModelWorkflowMixin
from gui.fit_workflow import FitWorkflowMixin
from gui.discrete_fit import DiscreteFitMixin
from gui.distribution_fit import DistributionFitMixin
from gui.minima_analysis import MinimaAnalysisMixin
from gui.phase_id_actions import PhaseIdMixin
from gui.fit_history import FitHistoryMixin
from gui.minima_editor import MinimaEditorMixin
from gui.file_actions import FileActionsMixin
from gui.fit_tools import FitToolsMixin
from gui.calibration_actions import CalibrationActionsMixin
from gui.session_io import SessionIOMixin
from gui.web_api import WebApiMixin
from gui.updates import UpdateMixin
from gui.help import HelpMixin
from gui.reports import ReportMixin


class WindowMixins(
    HistoricalRuntimeCompatMixin,
    # UI base
    MainLayoutMixin,
    MenuBuilderMixin,
    LayoutSettingsMixin,
    # Estado/modelo/datos
    ModelWorkflowMixin,
    FitWorkflowMixin,
    # Ajustes y herramientas científicas
    DiscreteFitMixin,
    DistributionFitMixin,
    MinimaAnalysisMixin,
    PhaseIdMixin,
    FitHistoryMixin,
    # Editor semi-manual de mínimos (sobre el canvas Matplotlib)
    MinimaEditorMixin,
    # Acciones auxiliares
    FileActionsMixin,
    FitToolsMixin,
    CalibrationActionsMixin,
    # Persistencia y servicios
    SessionIOMixin,
    WebApiMixin,
    UpdateMixin,
    HelpMixin,
    ReportMixin,
):
    """Base compuesta para ``MossbauerQtWindow``.

    No hereda de ``QMainWindow``: esa base se añade en ``mossbauer_qt.py`` para
    mantener claro el punto de entrada público.
    """

    pass
