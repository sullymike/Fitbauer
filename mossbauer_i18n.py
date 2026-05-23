"""Minimal internationalization layer for the Mössbauer GUI.

This module is intentionally kept as a plain Python file, without locale
subdirectories, so it fits the repository layout.  The public API is small and
can later be backed by gettext or external catalogs without changing the GUI
code that calls ``tr("key")``.

At this stage only the Spanish catalog is complete.  Other languages can be
added by extending CATALOGS with the same keys.
"""
from __future__ import annotations

DEFAULT_LANGUAGE = "es"

LANGUAGES = {
    "es": "Español",
}

CATALOGS: dict[str, dict[str, str]] = {
    "es": {
        # Menu cascades
        "menu.file": "Archivo",
        "menu.fit": "Ajuste",
        "menu.options": "Opciones",
        "menu.help": "Ayuda",
        "menu.language": "Idioma",
        # File menu
        "file.open": "Cargar...",
        "file.web_measurements": "Medidas web...",
        "file.web_calibrations": "Calibraciones web...",
        "file.save_fit": "Guardar ajuste...",
        "file.export_report": "Exportar informe Markdown/PDF...",
        "file.save_session": "Guardar sesión...",
        "file.upload_session": "Subir sesión JSON a web...",
        "file.load_session": "Cargar sesión...",
        "file.exit": "Salir",
        # Fit menu
        "fit.find_center": "Buscar centro",
        "fit.init_from_minima": "Inicializar desde mínimos",
        "fit.auto_from_minima": "Autoajustar desde mínimos",
        "fit.ollama_start": "IA local Ollama: sugerir inicio...",
        "fit.run": "Ajustar",
        "fit.bootstrap": "Bootstrap errores (MC)...",
        "fit.fix_all": "Fijar todos",
        "fit.free_all": "Liberar todos",
        # Options menu
        "options.discrete_sextets": "Ajuste con sextetes",
        "options.distribution_bhf": "Distribución P(BHF)",
        "options.show_residual": "Mostrar diferencia",
        "options.show_legend": "Mostrar leyenda",
        "options.line_profile": "Perfil de línea",
        "options.profile_lorentzian": "Lorentziana",
        "options.profile_voigt": "Voigt",
        "options.add_sharp": "P(BHF): sumar componentes activos nítidos",
        "options.refine_global": "P(BHF): refinar δ y Γ globales",
        "options.constraints": "Restricciones entre parámetros...",
        "options.physical_presets": "Presets físicos de restricciones...",
        "options.theme": "Tema visual",
        "options.theme_modern": "Moderno (sv_ttk)",
        "options.theme_classic": "Clásico (clam)",
        # Help menu / help window
        "help.open": "Ayuda",
        "help.about": "Acerca de",
        "help.changelog": "Changelog",
        "help.check_updates": "Buscar actualizaciones...",
        "help.configure_updates": "Configurar actualizaciones...",
        "help.window_title": "Ayuda Mössbauer Fe-57 v2IA",
        "help.header_title": "Ayuda Mössbauer Fe-57 v2IA",
        "help.select_chapter": "Selecciona un capítulo para verlo por separado",
        "help.language_label": "Idioma:",
        "help.close": "Cerrar",
        # Header
        "main.subtitle": "Doblado, simulación y ajuste interactivo",
    }
}

_current_language = DEFAULT_LANGUAGE


def available_languages() -> dict[str, str]:
    """Return available language code -> display name."""
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

    If the key is missing, ``default`` is returned. If no default is supplied,
    the key itself is returned. Keyword arguments are applied with
    ``str.format`` so future messages can contain placeholders.
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
