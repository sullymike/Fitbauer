"""Minimal internationalization layer for the Mössbauer GUI.

Each language lives in its own ``locales/<code>/`` directory next to this
module:

    locales/
      es/
        strings.json   -- {"_meta": {"name": "Español"}, "menu.file": "...", ...}
        help.json      -- [{"title": "...", "heading": "...", "content": "..."}]
      en/
        ...

To add a new language drop a new ``locales/<code>/`` folder with the same
files; the program will pick it up automatically on next launch.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_LANGUAGE = "en"


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
    """Discover and load ``strings.json`` for every locale under ``LOCALES_DIR``."""
    CATALOGS.clear()
    LANGUAGES.clear()
    if not LOCALES_DIR.is_dir():
        return
    for sub in sorted(p for p in LOCALES_DIR.iterdir() if p.is_dir()):
        strings_path = sub / "strings.json"
        if not strings_path.is_file():
            continue
        try:
            data = json.loads(strings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        code = sub.name
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


def load_help_chapters(lang: str) -> list[tuple[str, str, str]]:
    """Load ``help.json`` for ``lang`` (falling back to default) as raw tuples.

    Returns ``[(title, heading, content), ...]``. Placeholders inside
    ``content`` (e.g. ``{voigt_sigma}``) are left untouched so callers can
    apply ``str.format`` with their own runtime values.
    """
    for code in (lang, DEFAULT_LANGUAGE):
        if not code:
            continue
        path = LOCALES_DIR / code / "help.json"
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, list):
            continue
        chapters: list[tuple[str, str, str]] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            chapters.append((
                str(entry.get("title", "")),
                str(entry.get("heading", "")),
                str(entry.get("content", "")),
            ))
        return chapters
    return []

