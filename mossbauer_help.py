"""Help chapters for the Mössbauer Fe-57 program.

Content lives in ``locales/<code>/help.json`` next to ``mossbauer_i18n``. This
module is a thin loader that injects runtime values (``voigt_sigma`` and the
settings path) into the chapter content via ``str.format`` placeholders.
"""
from __future__ import annotations

from mossbauer_i18n import DEFAULT_LANGUAGE, load_help_chapters, load_help_groups

_SETTINGS_DEFAULTS = {
    "es": "(configuración)",
    "en": "(settings)",
    "fr": "(configuration)",
}


def get_help_sections(voigt_sigma: float = 0.05,
                      settings_path: object = None,
                      lang: str = DEFAULT_LANGUAGE) -> list[tuple[str, str, str]]:
    """Return help chapters for ``lang``: ``[(title, heading, content), ...]``.

    ``voigt_sigma`` and ``settings_path`` are substituted into the chapter
    content for the placeholders ``{voigt_sigma}`` / ``{voigt_sigma:.3g}`` and
    ``{settings_path_str}``.
    """
    code = str(lang).lower()
    if code.startswith("en"):
        code = "en"
    elif code.startswith("fr"):
        code = "fr"
    elif code.startswith("es"):
        code = "es"

    settings_path_str = (
        str(settings_path)
        if settings_path is not None
        else _SETTINGS_DEFAULTS.get(code, _SETTINGS_DEFAULTS[DEFAULT_LANGUAGE])
    )

    chapters = load_help_chapters(code)
    rendered: list[tuple[str, str, str]] = []
    for title, heading, content in chapters:
        # Sustitución dirigida (no str.format): un capítulo con llaves
        # literales (fragmentos de código/JSON) hacía fallar el format entero
        # y dejaba sus placeholders sin resolver.
        content = (content
                   .replace("{voigt_sigma:.3g}", f"{voigt_sigma:.3g}")
                   .replace("{voigt_sigma}", str(voigt_sigma))
                   .replace("{settings_path_str}", settings_path_str))
        rendered.append((title, heading, content))
    return rendered


def get_help_groups(lang: str = DEFAULT_LANGUAGE) -> list[str]:
    """Return the thematic group code of each chapter, parallel to
    :func:`get_help_sections`.

    Used by the GUI help tree to group chapters by topic in a way that is
    independent of language, chapter count or ordering.
    """
    code = str(lang).lower()
    if code.startswith("en"):
        code = "en"
    elif code.startswith("fr"):
        code = "fr"
    elif code.startswith("es"):
        code = "es"
    return load_help_groups(code)
