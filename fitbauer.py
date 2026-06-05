#!/usr/bin/env python3
"""Punto de entrada único de Fitbauer.

Arranca la interfaz Qt (PySide6), la única interfaz del programa.

Uso:
    python fitbauer.py
"""
from __future__ import annotations

import sys


def main() -> int:
    try:
        import PySide6  # noqa: F401
    except ImportError:
        print("Fitbauer: PySide6 no está instalado. Instala las dependencias "
              "con 'pip install -r requirements.txt'.", file=sys.stderr)
        return 1
    import mossbauer_qt
    return mossbauer_qt.main()


if __name__ == "__main__":
    sys.exit(main())
