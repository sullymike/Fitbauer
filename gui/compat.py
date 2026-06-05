"""Compatibilidad histórica del front-end Qt.

Centraliza los pocos puntos que siguen existiendo para tests/extensiones que
parcheaban símbolos del antiguo ``mossbauer_qt.py`` monolítico.
"""
from __future__ import annotations

import sys
from typing import Any


def frontend_attr(name: str, fallback: Any) -> Any:
    """Devuelve el símbolo parcheado en ``mossbauer_qt`` si existe.

    Esto mantiene compatibilidad con monkeypatches históricos sin duplicar esta
    lógica en cada módulo de ``gui/``.
    """
    mod = sys.modules.get("mossbauer_qt")
    return getattr(mod, name, fallback) if mod is not None else fallback


class HistoricalRuntimeCompatMixin:
    """Propiedades legacy que delegan en ``RuntimeResultState``.

    Se conservan para código externo/tests que acceden a ``last_fit_result``,
    ``last_distribution_result`` o ``last_error_source`` en la ventana Qt.
    El código nuevo debe usar ``self.runtime_results``.
    """

    @property
    def last_fit_result(self):
        return self.runtime_results.fit_result

    @last_fit_result.setter
    def last_fit_result(self, value):
        self.runtime_results.fit_result = value

    @property
    def last_distribution_result(self):
        return self.runtime_results.distribution_result

    @last_distribution_result.setter
    def last_distribution_result(self, value):
        self.runtime_results.distribution_result = value

    @property
    def last_error_source(self) -> str:
        return self.runtime_results.error_source

    @last_error_source.setter
    def last_error_source(self, value: str) -> None:
        self.runtime_results.set_error_source(str(value))
