"""Diálogos de actualización del programa Mössbauer Fe-57."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk


def _update_dialog(parent, title: str, msg: str) -> bool:
    """Diálogo scrollable para notificación de actualización. Devuelve True si el usuario acepta."""
    result = tk.BooleanVar(value=False)
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry("860x480")
    win.resizable(True, True)
    win.transient(parent)
    win.grab_set()

    frame = ttk.Frame(win, padding=(12, 10, 12, 6))
    frame.pack(fill=tk.BOTH, expand=True)
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)

    txt = tk.Text(frame, wrap=tk.WORD, font=("TkDefaultFont", 9),
                  relief="flat", padx=8, pady=8)
    scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=txt.yview)
    txt.configure(yscrollcommand=scroll.set)
    txt.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")
    txt.insert("1.0", msg)
    txt.configure(state=tk.DISABLED)

    btn_frame = ttk.Frame(win, padding=(12, 4, 12, 10))
    btn_frame.pack(fill=tk.X)

    def on_yes():
        result.set(True)
        win.destroy()

    def on_no():
        win.destroy()

    ttk.Button(btn_frame, text="Sí, descargar ahora", command=on_yes).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(btn_frame, text="No por ahora",        command=on_no).pack(side=tk.RIGHT)

    win.wait_window()
    return result.get()


def _pip_install_requirements(install_dir: Path) -> str:
    """Ejecuta pip install -r requirements.txt del directorio dado.

    Devuelve una cadena con el resultado (vacía si no hay requirements.txt).
    Nunca lanza excepción.
    """
    req_file = install_dir / "requirements.txt"
    if not req_file.exists():
        return ""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file),
             "--quiet", "--disable-pip-version-check"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            return "Dependencias actualizadas correctamente (pip)."
        err = (result.stderr or result.stdout or "").strip()
        return f"Aviso de pip:\n{err[:300]}"
    except subprocess.TimeoutExpired:
        return "pip tardó demasiado y se canceló."
    except Exception as exc:
        return f"No se pudo ejecutar pip: {exc}"


def _update_pip_stamp(install_dir: Path, config_dir: Path) -> None:
    req_file = install_dir / "requirements.txt"
    if not req_file.exists():
        return
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "last_pip_check").write_text(
            str(req_file.stat().st_mtime), encoding="utf-8"
        )
    except Exception:
        pass


def check_requirements_if_needed(install_dir: Path, config_dir: Path) -> None:
    """Lanza pip en background si requirements.txt es más nuevo que el último chequeo."""
    req_file = install_dir / "requirements.txt"
    if not req_file.exists():
        return
    stamp_file = config_dir / "last_pip_check"
    req_mtime = req_file.stat().st_mtime
    if stamp_file.exists():
        try:
            last = float(stamp_file.read_text(encoding="utf-8").strip())
            if req_mtime <= last:
                return
        except Exception:
            pass

    def _worker() -> None:
        _pip_install_requirements(install_dir)
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            stamp_file.write_text(str(req_mtime), encoding="utf-8")
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def load_update_settings(config_dir: Path) -> dict:
    path = config_dir / "update_settings.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"channel": "stable"}


def save_update_settings(config_dir: Path, data: dict, parent=None) -> None:
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "update_settings.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        messagebox.showerror("Actualizaciones", f"No se pudo guardar la configuración:\n{exc}", parent=parent)


def open_update_settings_dialog(parent, config_dir: Path) -> None:
    win = tk.Toplevel(parent)
    win.title("Configurar actualizaciones")
    win.transient(parent)
    win.resizable(False, False)
    frame = ttk.Frame(win, padding=14)
    frame.pack(fill=tk.BOTH, expand=True)
    settings = load_update_settings(config_dir)
    channel_var = tk.StringVar(value=settings.get("channel", "stable"))
    ttk.Label(frame, text="Canal de avisos de actualización:").pack(anchor=tk.W, pady=(0, 8))
    ttk.Radiobutton(frame, text="Solo versiones estables", variable=channel_var, value="stable").pack(anchor=tk.W)
    ttk.Radiobutton(frame, text="Estables y versiones no estables/beta", variable=channel_var, value="all").pack(anchor=tk.W)
    ttk.Label(
        frame,
        text="Las versiones beta sirven para probar cambios. Si eliges betas, el programa avisará también de prereleases de GitHub.",
        style="Subtitle.TLabel",
        wraplength=430,
    ).pack(anchor=tk.W, pady=(10, 12))
    buttons = ttk.Frame(frame)
    buttons.pack(fill=tk.X)

    def save() -> None:
        save_update_settings(config_dir, {"channel": channel_var.get()}, parent=win)
        win.destroy()

    ttk.Button(buttons, text="Guardar", command=save, style="Accent.TButton").pack(side=tk.RIGHT)
    ttk.Button(buttons, text="Cancelar", command=win.destroy).pack(side=tk.RIGHT, padx=(0, 8))


def check_for_updates(
    parent,
    app_version: str,
    install_dir: Path,
    config_dir: Path,
    silent: bool = False,
    with_checksum: bool = False,
) -> None:
    """Comprueba GitHub Releases y descarga la nueva versión si existe."""
    try:
        if with_checksum:
            from mossbauer_updater import (
                choose_download, download_file, find_release_checksum,
                install_zip_update, is_newer, is_zip_update, latest_release,
            )
        else:
            from mossbauer_updater import (
                choose_download, download_file,
                install_zip_update, is_newer, is_zip_update, latest_release,
            )
            find_release_checksum = None
    except Exception as exc:
        if not silent:
            messagebox.showerror("Actualizaciones", f"No se pudo cargar el actualizador: {exc}", parent=parent)
        return

    update_settings = load_update_settings(config_dir)
    include_prereleases = update_settings.get("channel", "stable") == "all"

    def downloads_dir() -> Path:
        for name in ("Descargas", "Downloads"):
            p = Path.home() / name
            if p.exists():
                return p
        return Path.home()

    def download_in_background(release, url: str, filename: str) -> None:
        def worker_download() -> None:
            expected = None
            if with_checksum and find_release_checksum is not None:
                try:
                    expected = find_release_checksum(release, filename)
                except Exception:
                    pass
            try:
                if with_checksum:
                    path = download_file(url, downloads_dir(), filename, expected_sha256=expected)
                else:
                    path = download_file(url, downloads_dir(), filename)
            except Exception as exc:
                errmsg = "No se pudo descargar o verificar la actualización" if with_checksum else "No se pudo descargar la actualización"
                parent.after(0, lambda e=exc: messagebox.showerror("Actualizaciones", f"{errmsg}:\n{e}", parent=parent))
                return
            verified = with_checksum and expected is not None

            def finish_download() -> None:
                if with_checksum:
                    integridad = (
                        "Integridad verificada con SHA-256."
                        if verified
                        else "Aviso: la release no publica checksum; no se pudo verificar la integridad."
                    )
                    integridad_suffix = f"\n\n{integridad}"
                else:
                    integridad_suffix = ""
                if is_zip_update(path):
                    if messagebox.askyesno(
                        "Actualización descargada",
                        f"Descargado en:\n{path}{integridad_suffix}\n\n"
                        "¿Instalar ahora sobre esta carpeta del programa?\n"
                        "Después solo tendrás que cerrar y volver a abrir el programa.",
                        parent=parent,
                    ):
                        try:
                            install_zip_update(path, install_dir)
                        except Exception as exc:
                            messagebox.showerror("Actualizaciones", f"No se pudo instalar la actualización:\n{exc}", parent=parent)
                            return
                        pip_msg = _pip_install_requirements(install_dir)
                        pip_suffix = f"\n\n{pip_msg}" if pip_msg else ""
                        # Actualizar sello para no repetir pip al arrancar
                        _update_pip_stamp(install_dir, config_dir)
                        messagebox.showinfo(
                            "Actualización instalada",
                            "La nueva versión se ha descomprimido en la carpeta del programa."
                            f"{pip_suffix}\n\n"
                            "Cierra y vuelve a abrir el programa para usarla.",
                            parent=parent,
                        )
                        return
                messagebox.showinfo(
                    "Actualización descargada",
                    f"Descargado en:\n{path}{integridad_suffix}\n\n"
                    "Cierra el programa y usa ese fichero para instalar/ejecutar la nueva versión.",
                    parent=parent,
                )

            parent.after(0, finish_download)
        threading.Thread(target=worker_download, daemon=True).start()

    def worker() -> None:
        try:
            release = latest_release(include_prereleases=include_prereleases)
            newer = is_newer(release.tag, app_version)
        except Exception as exc:
            if not silent:
                parent.after(0, lambda e=exc: messagebox.showerror("Actualizaciones", f"No se pudo comprobar GitHub Releases:\n{e}", parent=parent))
            return

        def finish() -> None:
            channel_txt = "estables y beta" if include_prereleases else "solo estables"
            if not newer:
                if not silent:
                    messagebox.showinfo("Actualizaciones", f"Ya tienes la última versión ({app_version}) para el canal: {channel_txt}.", parent=parent)
                return
            body = (release.body or "").strip()
            release_kind = "no estable/beta" if getattr(release, "prerelease", False) else "estable"
            msg = (
                f"Hay una versión nueva disponible ({release_kind}).\n\n"
                f"Canal configurado: {channel_txt}\n"
                f"Versión actual:    {app_version}\n"
                f"Nueva versión:     {release.tag}\n\n"
                + ("─" * 60 + "\n\n" + body + "\n\n" if body else "")
                + "¿Quieres descargarla ahora?"
            )
            if _update_dialog(parent, "Actualización disponible", msg):
                url, filename = choose_download(release, prefer_exe=(os.name == "nt"))
                download_in_background(release, url, filename)
            else:
                if messagebox.askyesno("Actualizaciones", "¿Abrir la página de releases en el navegador?", parent=parent):
                    webbrowser.open(release.html_url)

        parent.after(0, finish)

    threading.Thread(target=worker, daemon=True).start()
