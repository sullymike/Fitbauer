"""Configuración compartida de pytest.

Monkeypatch para entornos de desarrollo con NumPy<2: añade ``np.trapezoid``
(introducido en NumPy 2.0) apuntando a ``np.trapz`` si no existe.

En CI ``requirements.txt`` fija ``numpy>=2.0`` y este monkeypatch es no-op.
"""
from __future__ import annotations

import numpy as np
import pytest

if not hasattr(np, "trapezoid"):
    np.trapezoid = np.trapz  # type: ignore[attr-defined]


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """Evita el segfault de QtWebEngine al cerrar el proceso.

    PySide6/QtWebEngine segfaultea al destruir su perfil global durante el
    apagado del intérprete ("Release of profile requested but WebEnginePage
    still not deleted") — un bug conocido ajeno a la lógica de la app. Cuando se
    ha cargado WebEngine, salimos del proceso aquí (ya terminados los tests y
    emitido el informe de pytest), saltándonos ese teardown problemático. El
    código de salida refleja el resultado real de la sesión.
    """
    import os
    import sys

    if "PySide6.QtWebEngineWidgets" in sys.modules:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0 if exitstatus == 0 else 1)

