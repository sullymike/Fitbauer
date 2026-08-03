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

    Carga el contenido actual, aplica ``kwargs`` encima y reescribe el fichero.
    Los errores de escritura se propagan: cada llamador decide si los silencia.

    Dos precauciones, porque este fichero guarda TODO lo que el usuario ha
    configurado y se reescribe solo durante el arranque:

    * **Escritura atómica.** Se escribe a un temporal y se renombra. Un corte a
      media escritura dejaba antes un JSON truncado, y como ``load_settings``
      devuelve ``{}`` ante un fichero corrupto, el siguiente guardado lo
      reemplazaba entero: la corrupción se convertía en pérdida total.
    * **Un fichero ilegible se aparta, no se pisa.** Si existe pero no se puede
      leer, se conserva como ``settings.json.corrupto`` antes de escribir el
      nuevo, para poder recuperar a mano lo que hubiera dentro.
    """
    current = load_settings()
    if not current and SETTINGS_PATH.exists() and SETTINGS_PATH.stat().st_size:
        try:
            SETTINGS_PATH.replace(SETTINGS_PATH.with_suffix(".json.corrupto"))
        except OSError:
            pass
    current.update(kwargs)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(SETTINGS_PATH)


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
