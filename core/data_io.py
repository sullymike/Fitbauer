"""Rutas de configuración, credenciales y reexports de lectura/plegado (sin GUI).

Las funciones de lectura (.ws5/.adt/Normos) y folding viven en
``core.folding`` (fuente única). Aquí se reexportan por compatibilidad:
antes existían copias duplicadas que divergieron de las canónicas
(heurística del folding point Normos y normalización del área ARE).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .folding import (  # noqa: F401  (reexports por compatibilidad)
    chi2_for_center,
    find_best_integer_or_half_center,
    fold_integer_or_half,
    interp_channel_1based,
    read_normos_folding_point,
    read_normos_plt_velocity,
    read_normos_sidecar_params,
    read_ws5_counts,
)

CONFIG_DIR = Path.home() / ".config" / "mossbauer_fe33_gui"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"


def load_settings() -> dict:
    """Lee ``settings.json`` y devuelve su contenido como dict.

    Devuelve ``{}`` si el fichero no existe, está corrupto o no contiene un
    objeto JSON (lectura best-effort: nunca lanza).
    """
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def update_settings(**kwargs) -> None:
    """Actualiza claves de ``settings.json`` conservando el resto.

    Carga el contenido actual (``{}`` si falta o está corrupto), aplica
    ``kwargs`` encima y reescribe el fichero con el formato habitual
    (``indent=2``, ``ensure_ascii=False``). Los errores de escritura se
    propagan: cada llamador decide si los silencia o los muestra.
    """
    current = load_settings()
    current.update(kwargs)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_credentials() -> dict:
    if CREDENTIALS_PATH.exists():
        try:
            return json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_credentials(data: dict) -> None:
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        os.chmod(CREDENTIALS_PATH, 0o600)
    except Exception:
        pass
