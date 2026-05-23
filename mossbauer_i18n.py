"""Minimal internationalization layer for the Mössbauer GUI.

The GUI calls ``tr("stable.key")``.  Catalogs live in this single Python file so
no locale subdirectories are needed.  More languages can be added by extending
``LANGUAGES`` and ``CATALOGS`` with the same keys.
"""
from __future__ import annotations

DEFAULT_LANGUAGE = "es"

LANGUAGES = {
    "es": "Español",
    "en": "English",
    "fr": "Français",
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
        # Language switching
        "language.restart_title": "Idioma cambiado",
        "language.restart_message": "El idioma seleccionado se aplicará completamente al reiniciar el programa.",
    },
    "en": {
        # Menu cascades
        "menu.file": "File",
        "menu.fit": "Fit",
        "menu.options": "Options",
        "menu.help": "Help",
        "menu.language": "Language",
        # File menu
        "file.open": "Open...",
        "file.web_measurements": "Web measurements...",
        "file.web_calibrations": "Web calibrations...",
        "file.save_fit": "Save fit...",
        "file.export_report": "Export Markdown/PDF report...",
        "file.save_session": "Save session...",
        "file.upload_session": "Upload JSON session to web...",
        "file.load_session": "Load session...",
        "file.exit": "Exit",
        # Fit menu
        "fit.find_center": "Find center",
        "fit.init_from_minima": "Initialize from minima",
        "fit.auto_from_minima": "Auto-fit from minima",
        "fit.ollama_start": "Local Ollama AI: suggest start...",
        "fit.run": "Fit",
        "fit.bootstrap": "Bootstrap errors (MC)...",
        "fit.fix_all": "Fix all",
        "fit.free_all": "Free all",
        # Options menu
        "options.discrete_sextets": "Sextet fit",
        "options.distribution_bhf": "P(BHF) distribution",
        "options.show_residual": "Show residual",
        "options.show_legend": "Show legend",
        "options.line_profile": "Line profile",
        "options.profile_lorentzian": "Lorentzian",
        "options.profile_voigt": "Voigt",
        "options.add_sharp": "P(BHF): add active sharp components",
        "options.refine_global": "P(BHF): refine global δ and Γ",
        "options.constraints": "Parameter constraints...",
        "options.physical_presets": "Physical constraint presets...",
        "options.theme": "Visual theme",
        "options.theme_modern": "Modern (sv_ttk)",
        "options.theme_classic": "Classic (clam)",
        # Help menu / help window
        "help.open": "Help",
        "help.about": "About",
        "help.changelog": "Changelog",
        "help.check_updates": "Check for updates...",
        "help.configure_updates": "Configure updates...",
        "help.window_title": "Mössbauer Fe-57 v2IA Help",
        "help.header_title": "Mössbauer Fe-57 v2IA Help",
        "help.select_chapter": "Select a chapter to view it separately",
        "help.language_label": "Language:",
        "help.close": "Close",
        # Header
        "main.subtitle": "Interactive folding, simulation and fitting",
        # Language switching
        "language.restart_title": "Language changed",
        "language.restart_message": "The selected language will be fully applied after restarting the program.",
    },
    "fr": {
        # Menu cascades
        "menu.file": "Fichier",
        "menu.fit": "Ajustement",
        "menu.options": "Options",
        "menu.help": "Aide",
        "menu.language": "Langue",
        # File menu
        "file.open": "Ouvrir...",
        "file.web_measurements": "Mesures web...",
        "file.web_calibrations": "Étalonnages web...",
        "file.save_fit": "Enregistrer l'ajustement...",
        "file.export_report": "Exporter le rapport Markdown/PDF...",
        "file.save_session": "Enregistrer la session...",
        "file.upload_session": "Téléverser la session JSON vers le web...",
        "file.load_session": "Charger une session...",
        "file.exit": "Quitter",
        # Fit menu
        "fit.find_center": "Chercher le centre",
        "fit.init_from_minima": "Initialiser depuis les minima",
        "fit.auto_from_minima": "Ajuster automatiquement depuis les minima",
        "fit.ollama_start": "IA locale Ollama : suggérer un départ...",
        "fit.run": "Ajuster",
        "fit.bootstrap": "Erreurs bootstrap (MC)...",
        "fit.fix_all": "Fixer tout",
        "fit.free_all": "Libérer tout",
        # Options menu
        "options.discrete_sextets": "Ajustement avec sextets",
        "options.distribution_bhf": "Distribution P(BHF)",
        "options.show_residual": "Afficher le résidu",
        "options.show_legend": "Afficher la légende",
        "options.line_profile": "Profil de raie",
        "options.profile_lorentzian": "Lorentzien",
        "options.profile_voigt": "Voigt",
        "options.add_sharp": "P(BHF) : ajouter les composants nets actifs",
        "options.refine_global": "P(BHF) : affiner δ et Γ globaux",
        "options.constraints": "Contraintes entre paramètres...",
        "options.physical_presets": "Préréglages physiques de contraintes...",
        "options.theme": "Thème visuel",
        "options.theme_modern": "Moderne (sv_ttk)",
        "options.theme_classic": "Classique (clam)",
        # Help menu / help window
        "help.open": "Aide",
        "help.about": "À propos",
        "help.changelog": "Changelog",
        "help.check_updates": "Rechercher des mises à jour...",
        "help.configure_updates": "Configurer les mises à jour...",
        "help.window_title": "Aide Mössbauer Fe-57 v2IA",
        "help.header_title": "Aide Mössbauer Fe-57 v2IA",
        "help.select_chapter": "Sélectionnez un chapitre pour le voir séparément",
        "help.language_label": "Langue :",
        "help.close": "Fermer",
        # Header
        "main.subtitle": "Pliage, simulation et ajustement interactifs",
        # Language switching
        "language.restart_title": "Langue modifiée",
        "language.restart_message": "La langue sélectionnée sera appliquée complètement après le redémarrage du programme.",
    },
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
