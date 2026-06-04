#!/usr/bin/env python3
"""Punto de entrada único de Fitbauer.

Arranca la interfaz Qt (PySide6) por defecto. Si PySide6 no está instalado
o la GUI Qt falla al iniciarse, cae automáticamente a la interfaz Tk, de modo
que el programa siempre se abre con la mejor interfaz disponible.

Uso:
    python fitbauer.py            # Qt si es posible, si no Tk
    python fitbauer.py --tk       # fuerza la interfaz Tk
    python fitbauer.py --qt       # fuerza Qt (error si PySide6 no está)
"""
from __future__ import annotations

import sys


def _run_qt() -> int:
    import mossbauer_qt
    return mossbauer_qt.main()


def _run_tk() -> int:
    import mossbauer_app
    mossbauer_app.main()
    return 0


def main() -> int:
    argv = sys.argv

    if "--tk" in argv:
        argv.remove("--tk")
        return _run_tk()

    force_qt = "--qt" in argv
    if force_qt:
        argv.remove("--qt")

    try:
        import PySide6  # noqa: F401
    except ImportError:
        if force_qt:
            print("Fitbauer: --qt solicitado pero PySide6 no está instalado.",
                  file=sys.stderr)
            return 1
        print("Fitbauer: PySide6 no disponible, usando interfaz Tk.",
              file=sys.stderr)
        return _run_tk()

    try:
        return _run_qt()
    except Exception as exc:  # arranque de Qt fallido → respaldo Tk
        if force_qt:
            raise
        print(f"Fitbauer: la interfaz Qt falló ({exc}); usando interfaz Tk.",
              file=sys.stderr)
        return _run_tk()


if __name__ == "__main__":
    sys.exit(main())
