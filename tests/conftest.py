"""Configuración compartida de pytest.

Monkeypatch para entornos de desarrollo con NumPy<2: añade ``np.trapezoid``
(introducido en NumPy 2.0) apuntando a ``np.trapz`` si no existe.

En CI ``requirements.txt`` fija ``numpy>=2.0`` y este monkeypatch es no-op.
"""
from __future__ import annotations

import importlib

import numpy as np
import pytest

if not hasattr(np, "trapezoid"):
    np.trapezoid = np.trapz  # type: ignore[attr-defined]



@pytest.fixture(autouse=True, scope="session")
def _configuracion_aislada(tmp_path_factory):
    """Ningún test debe escribir en la configuración REAL del usuario.

    Los módulos resuelven `~/.config/mossbauer_fe33_gui/` al importarse, y la
    ventana guarda sus preferencias sola durante el arranque
    (`_apply_layout_preset` llama a `_save_settings`). El resultado es que basta
    con construir una `MossbauerQtWindow` en un test para machacar los ajustes
    de quien esté ejecutando la suite: se comprobó que
    `test_layout_presets_change_splitter_sizes` cambiaba el `layout_preset` real
    de «Tres columnas» a «Compacto», y que los layouts personalizados
    desaparecían.

    Este fixture redirige el directorio de configuración a uno temporal durante
    toda la sesión de pytest. Es autouse y de ámbito de sesión a propósito: si
    dependiera de que cada test se acuerde de parchearlo, volvería a pasar.
    """
    import core.data_io as data_io
    import core.param_overrides as param_overrides

    cfg = tmp_path_factory.mktemp("config_fitbauer")
    parches = [
        (data_io, "CONFIG_DIR", cfg),
        (data_io, "SETTINGS_PATH", cfg / "settings.json"),
        (data_io, "CREDENTIALS_PATH", cfg / "credentials.json"),
        (param_overrides, "CONFIG_DIR", cfg),
        (param_overrides, "PARAM_LIMITS_PATH", cfg / "param_limits.json"),
    ]
    # Los módulos que hicieron `from ... import SETTINGS_PATH` tienen su propia
    # referencia y hay que parchearlos también.
    for nombre, atributo in (("gui.layout_manager", "SETTINGS_PATH"),
                             ("gui.session_io", "CONFIG_DIR"),
                             ("gui.updates", "CONFIG_DIR"),
                             ("gui.fit_history", "HISTORY_PATH"),
                             ("gui.help", "SETTINGS_PATH")):
        try:
            modulo = importlib.import_module(nombre)
        except Exception:
            continue
        if not hasattr(modulo, atributo):
            continue
        destino = cfg / ("fit_history.json" if atributo == "HISTORY_PATH"
                         else "settings.json")
        parches.append((modulo, atributo, cfg if atributo == "CONFIG_DIR" else destino))

    originales = [(m, a, getattr(m, a)) for m, a, _ in parches]
    for modulo, atributo, valor in parches:
        setattr(modulo, atributo, valor)
    yield cfg
    for modulo, atributo, valor in originales:
        setattr(modulo, atributo, valor)
