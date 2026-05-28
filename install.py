#!/usr/bin/env python3
"""Instalador simple para Mössbauer Fe-57.

Uso:
    python install.py

Crea un entorno virtual local, instala dependencias y genera un lanzador:
- Linux/macOS: ./mossbauer
- Windows: mossbauer.bat
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
MAIN_GUI = "mossbauer_fe33_gui_v2IA.py"


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(str(c) for c in cmd))
    subprocess.check_call(cmd, **kwargs)


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def create_venv() -> None:
    if VENV_DIR.exists():
        print(f"Entorno virtual ya existe: {VENV_DIR}")
        return
    print(f"Creando entorno virtual en {VENV_DIR}...")
    venv.EnvBuilder(with_pip=True, clear=False).create(VENV_DIR)


def install_dependencies() -> None:
    py = str(venv_python())
    run([py, "-m", "pip", "install", "--upgrade", "pip"])
    if REQUIREMENTS.exists():
        run([py, "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    else:
        run([py, "-m", "pip", "install", "numpy", "scipy", "matplotlib", "requests", "sv-ttk"])


def make_posix_launcher(name: str, script: str) -> None:
    path = ROOT / name
    path.write_text(
        f"#!/usr/bin/env sh\n"
        f"DIR=$(CDPATH= cd -- \"$(dirname -- \"$0\")\" && pwd)\n"
        f"exec \"$DIR/.venv/bin/python\" \"$DIR/{script}\" \"$@\"\n",
        encoding="utf-8",
    )
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Lanzador creado: {path}")


def make_windows_launcher(name: str, script: str) -> None:
    path = ROOT / name
    path.write_text(
        "@echo off\r\n"
        "set DIR=%~dp0\r\n"
        f'"%DIR%.venv\\Scripts\\python.exe" "%DIR%{script}" %*\r\n',
        encoding="utf-8",
    )
    print(f"Lanzador creado: {path}")


def create_launchers() -> None:
    make_posix_launcher("mossbauer", MAIN_GUI)
    make_windows_launcher("mossbauer.bat", MAIN_GUI)


def smoke_test() -> None:
    py = str(venv_python())
    run([
        py,
        "-m",
        "py_compile",
        str(ROOT / MAIN_GUI),
        str(ROOT / "mossbauer_app.py"),
        str(ROOT / "mossbauer_updater.py"),
        str(ROOT / "mossbauer_updater_ui.py"),
        str(ROOT / "mossbauer_api_client.py"),
        str(ROOT / "mossbauer_help.py"),
    ])


def main() -> int:
    if not (ROOT / MAIN_GUI).exists():
        print(f"Falta el fichero principal: {MAIN_GUI}", file=sys.stderr)
        return 1
    create_venv()
    install_dependencies()
    create_launchers()
    smoke_test()
    print("\nInstalación terminada.")
    if os.name == "nt":
        print("Ejecuta: mossbauer.bat")
    else:
        print("Ejecuta: ./mossbauer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
