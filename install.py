#!/usr/bin/env python3
"""Instalador simple para Fitbauer.

Uso:
    python install.py                 # instala venv + dependencias + lanzadores
                                      # y registra la app en los menús del sistema
    python install.py --menu-only     # solo registra la app en los menús
    python install.py --no-menu       # instala pero sin tocar los menús
    python install.py --uninstall     # elimina la entrada de menú (Linux/Windows)

Crea un entorno virtual local, instala dependencias y genera un lanzador:
- Linux/macOS: ./fitbauer
- Windows: fitbauer.bat

Además registra Fitbauer en los menús de aplicaciones del sistema:
- Linux: fichero .desktop en ~/.local/share/applications (categoría Education,
  icono en hicolor).
- Windows: acceso directo en una carpeta "Fitbauer" del menú Inicio
  (%APPDATA%\\...\\Start Menu\\Programs\\Fitbauer\\Fitbauer.lnk).
Ambos son por-usuario y no requieren privilegios de administrador.
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
MAIN_GUI = "mossbauer_qt.py"
LAUNCHER_ENTRY = "fitbauer.py"

# ── Metadatos para el registro en menús ──────────────────────────────────────
APP_ID = "fitbauer"                     # nombre de fichero .desktop / icono / .lnk
APP_NAME = "Fitbauer"
APP_COMMENT = "Software for Mössbauer spectrum fitting and analysis"
ICON_PNG = ROOT / "assets" / "fitbauer_icon.png"
ICON_ICO = ROOT / "assets" / "fitbauer_icon.ico"


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
    make_posix_launcher("fitbauer", LAUNCHER_ENTRY)
    make_windows_launcher("fitbauer.bat", LAUNCHER_ENTRY)


def smoke_test() -> None:
    py = str(venv_python())
    run([
        py,
        "-m",
        "py_compile",
        str(ROOT / MAIN_GUI),
        str(ROOT / LAUNCHER_ENTRY),
        str(ROOT / "mossbauer_updater.py"),
        str(ROOT / "mossbauer_api_client.py"),
        str(ROOT / "mossbauer_help.py"),
        str(ROOT / "core" / "session.py"),
    ])


# ── Registro en los menús de aplicaciones ────────────────────────────────────
def _gui_command() -> tuple[str, str]:
    """Devuelve (ejecutable, script) para lanzar la GUI.

    Prefiere el Python del entorno virtual (``pythonw`` en Windows, para no abrir
    una consola); si no existe, cae al Python del sistema.
    """
    script = str(ROOT / LAUNCHER_ENTRY)
    if os.name == "nt":
        pyw = VENV_DIR / "Scripts" / "pythonw.exe"
        return (str(pyw) if pyw.exists() else "pythonw"), script
    vpy = VENV_DIR / "bin" / "python"
    return (str(vpy) if vpy.exists() else "python3"), script


def _run_quiet(cmd: list[str]) -> None:
    """Ejecuta un comando best-effort; ignora que falte o falle (cachés, etc.)."""
    try:
        subprocess.run(cmd, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def _desktop_quote(s: str) -> str:
    """Cita un token para el campo ``Exec`` de un fichero .desktop."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _install_desktop_linux() -> None:
    apps_dir = Path.home() / ".local" / "share" / "applications"
    hicolor = Path.home() / ".local" / "share" / "icons" / "hicolor"
    apps_dir.mkdir(parents=True, exist_ok=True)

    icon_field = str(ICON_PNG)  # por defecto, ruta absoluta (siempre resuelve)
    if ICON_PNG.exists():
        try:
            icons_dir = hicolor / "256x256" / "apps"
            icons_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ICON_PNG, icons_dir / f"{APP_ID}.png")
            icon_field = APP_ID  # icono temático instalado
        except OSError:
            icon_field = str(ICON_PNG)

    exe, script = _gui_command()
    exec_line = f"{_desktop_quote(exe)} {_desktop_quote(script)}"
    desktop = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        f"Name={APP_NAME}\n"
        "GenericName=Mössbauer spectrum analysis\n"
        f"Comment={APP_COMMENT}\n"
        f"Exec={exec_line}\n"
        f"Icon={icon_field}\n"
        "Terminal=false\n"
        "Categories=Education;\n"
        "Keywords=Mossbauer;spectroscopy;spectrum;fitting;Fe57;\n"
        f"StartupWMClass={APP_NAME}\n"
    )
    dest = apps_dir / f"{APP_ID}.desktop"
    dest.write_text(desktop, encoding="utf-8")
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Entrada de menú creada: {dest}")
    _run_quiet(["update-desktop-database", str(apps_dir)])
    _run_quiet(["gtk-update-icon-cache", "-f", "-t", str(hicolor)])


def _ps_quote(s: str) -> str:
    """Escapa una cadena para una literal entre comillas simples de PowerShell."""
    return s.replace("'", "''")


def _install_desktop_windows() -> None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("No se encontró %APPDATA%; no se pudo crear el acceso directo.",
              file=sys.stderr)
        return
    programs = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    # Carpeta propia "Fitbauer" en el menú Inicio (grupo de programa).
    group = programs / APP_NAME
    group.mkdir(parents=True, exist_ok=True)
    lnk = group / f"{APP_NAME}.lnk"
    exe, script = _gui_command()
    icon = str(ICON_ICO) if ICON_ICO.exists() else exe
    ps = (
        "$W = New-Object -ComObject WScript.Shell; "
        f"$S = $W.CreateShortcut('{_ps_quote(str(lnk))}'); "
        f"$S.TargetPath = '{_ps_quote(exe)}'; "
        f"$S.Arguments = '\"{_ps_quote(script)}\"'; "
        f"$S.WorkingDirectory = '{_ps_quote(str(ROOT))}'; "
        f"$S.IconLocation = '{_ps_quote(icon)}'; "
        f"$S.Description = '{_ps_quote(APP_COMMENT)}'; "
        "$S.Save()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            check=True)
        print(f"Acceso directo creado: {lnk}")
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"No se pudo crear el acceso directo: {exc}", file=sys.stderr)


def install_desktop_entry() -> None:
    """Registra Fitbauer en los menús de aplicaciones del sistema (por-usuario)."""
    if sys.platform.startswith("linux"):
        _install_desktop_linux()
    elif os.name == "nt":
        _install_desktop_windows()
    elif sys.platform == "darwin":
        print("Registro automático en menús no soportado en macOS; "
              "usa el lanzador ./fitbauer o crea un .app manualmente.")
    else:
        print(f"Plataforma no soportada para registro en menús: {sys.platform}")


def uninstall_desktop_entry() -> None:
    """Elimina la entrada de menú creada por :func:`install_desktop_entry`."""
    if sys.platform.startswith("linux"):
        apps_dir = Path.home() / ".local" / "share" / "applications"
        targets = [
            apps_dir / f"{APP_ID}.desktop",
            Path.home() / ".local" / "share" / "icons" / "hicolor"
            / "256x256" / "apps" / f"{APP_ID}.png",
        ]
        removed = False
        for p in targets:
            if p.exists():
                p.unlink()
                print(f"Eliminado: {p}")
                removed = True
        _run_quiet(["update-desktop-database", str(apps_dir)])
        if not removed:
            print("No había entrada de menú que eliminar.")
    elif os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            print("No se encontró %APPDATA%; nada que desinstalar.")
            return
        programs = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        group = programs / APP_NAME
        removed = False
        # Acceso dentro del grupo "Fitbauer" y, por compatibilidad, el .lnk plano.
        for p in (group / f"{APP_NAME}.lnk", programs / f"{APP_NAME}.lnk"):
            if p.exists():
                p.unlink()
                print(f"Eliminado: {p}")
                removed = True
        if group.is_dir() and not any(group.iterdir()):
            group.rmdir()
            print(f"Eliminado: {group}")
        if not removed:
            print("No había acceso directo que eliminar.")
    else:
        print("Nada que desinstalar en esta plataforma.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Instalador de Fitbauer.")
    parser.add_argument("--menu-only", action="store_true",
                        help="solo registrar la app en los menús (no toca venv/deps)")
    parser.add_argument("--no-menu", action="store_true",
                        help="instalar sin registrar la app en los menús")
    parser.add_argument("--uninstall", action="store_true",
                        help="eliminar la entrada de menú y salir")
    args = parser.parse_args()

    if args.uninstall:
        uninstall_desktop_entry()
        return 0

    if not (ROOT / MAIN_GUI).exists():
        print(f"Falta el fichero principal: {MAIN_GUI}", file=sys.stderr)
        return 1

    if args.menu_only:
        create_launchers()
        install_desktop_entry()
        print("\nRegistro en menús terminado.")
        return 0

    create_venv()
    install_dependencies()
    create_launchers()
    smoke_test()
    if not args.no_menu:
        install_desktop_entry()
    print("\nInstalación terminada.")
    if os.name == "nt":
        print("Ejecuta: fitbauer.bat  (o búscalo en el menú Inicio)")
    else:
        print("Ejecuta: ./fitbauer  (o búscalo en el menú de aplicaciones)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
