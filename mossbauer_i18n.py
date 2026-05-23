"""Minimal internationalization layer for the Mössbauer GUI.

Catalogs live as JSON files inside the ``locales/`` directory next to this
module. Each ``<code>.json`` file holds the translation pairs for one language
and an optional ``_meta`` block with the display name shown in the language
menu::

    {
      "_meta": {"name": "Español"},
      "menu.file": "Archivo",
      ...
    }

To add a new language drop a new ``locales/<code>.json`` file with the same
keys as the others; the program will pick it up automatically on next launch.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_LANGUAGE = "es"


def _resolve_locales_dir() -> Path:
    """Find the locales directory next to this module or inside a frozen bundle."""
    candidates = [Path(__file__).resolve().parent / "locales"]
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(Path(base) / "locales")
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[0]


LOCALES_DIR = _resolve_locales_dir()

CATALOGS: dict[str, dict[str, str]] = {}
LANGUAGES: dict[str, str] = {}


def _load_catalogs() -> None:
    """Discover and load every locale file under ``LOCALES_DIR``."""
    CATALOGS.clear()
    LANGUAGES.clear()
    if not LOCALES_DIR.is_dir():
        return
    for path in sorted(LOCALES_DIR.glob("*.json")):
        code = path.stem
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
        CATALOGS[code] = {k: v for k, v in data.items() if k != "_meta" and isinstance(v, str)}
        LANGUAGES[code] = str(meta.get("name") or code)


_load_catalogs()

_current_language = DEFAULT_LANGUAGE if DEFAULT_LANGUAGE in CATALOGS else next(iter(CATALOGS), DEFAULT_LANGUAGE)


def available_languages() -> dict[str, str]:
    """Return discovered language code -> display name."""
    return dict(LANGUAGES)


def set_language(lang: str) -> None:
    """Set the active UI language if available."""
    global _current_language
    if lang in CATALOGS:
        _current_language = lang


def get_language() -> str:
    """Return the active UI language code."""
    return _current_language


def tr(key: str, default: str | None = None, **kwargs: object) -> str:
    """Translate a stable key using the active catalog.

    If the key is missing from the active language the default-language
    catalog is consulted; if still missing, ``default`` (or the key itself)
    is returned. ``kwargs`` are applied with ``str.format`` so messages can
    contain placeholders.
    """
    text = CATALOGS.get(_current_language, {}).get(key)
    if text is None:
        text = CATALOGS.get(DEFAULT_LANGUAGE, {}).get(key, default if default is not None else key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text
