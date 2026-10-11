"""Traducción de los textos propios de Qt (botones estándar, diálogos de fichero…).

Los catálogos de ``locales/`` cubren los textos de Fitbauer, pero los botones
estándar de Qt («Cancel», «Yes», «Open»…) salían en inglés en todos los
idiomas porque nunca se instalaba el traductor de Qt. PySide6 trae los
``qtbase_<idioma>.qm``; aquí se carga el del idioma activo.
"""
from __future__ import annotations

from PySide6 import QtCore

#: Código de catálogo de Fitbauer → sufijo del fichero ``qtbase_*.qm``.
_QT_LOCALE = {
    "es": "es", "fr": "fr", "de": "de", "pt": "pt_BR",
    "ru": "ru", "ja": "ja", "ch": "zh_CN",
}


def install_qt_translator(language: str) -> bool:
    """Instala en la aplicación el traductor de Qt para ``language``.

    Devuelve False si no hace falta (inglés) o si no se encuentra el fichero
    (p. ej. un ejecutable empaquetado sin las traducciones de Qt): en ese caso
    los botones siguen en inglés, sin error.
    """
    app = QtCore.QCoreApplication.instance()
    if app is None:
        return False
    anterior = getattr(app, "_fitbauer_qt_translator", None)
    if anterior is not None:
        app.removeTranslator(anterior)
        app._fitbauer_qt_translator = None
    sufijo = _QT_LOCALE.get(str(language))
    if sufijo is None:
        return False
    traductor = QtCore.QTranslator(app)
    ruta = QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.LibraryPath.TranslationsPath)
    if not traductor.load(f"qtbase_{sufijo}", ruta):
        return False
    app.installTranslator(traductor)
    # Se guarda en la aplicación: si el objeto Python se destruye, Qt lo pierde.
    app._fitbauer_qt_translator = traductor
    return True
