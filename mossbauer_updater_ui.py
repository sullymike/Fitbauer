"""Diálogos de actualización del programa Mössbauer Fe-57."""
from __future__ import annotations

import json
import os
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk


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
                        messagebox.showinfo(
                            "Actualización instalada",
                            "La nueva versión se ha descomprimido en la carpeta del programa.\n\n"
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
            if len(body) > 900:
                body = body[:900] + "…"
            release_kind = "no estable/beta" if getattr(release, "prerelease", False) else "estable"
            msg = (
                f"Hay una versión nueva disponible ({release_kind}).\n\n"
                f"Canal configurado: {channel_txt}\n"
                f"Versión actual: {app_version}\n"
                f"Nueva versión: {release.tag}\n\n"
                f"{body}\n\n"
                "¿Quieres descargarla ahora?"
            )
            if messagebox.askyesno("Actualización disponible", msg, parent=parent):
                url, filename = choose_download(release, prefer_exe=(os.name == "nt"))
                download_in_background(release, url, filename)
            else:
                if messagebox.askyesno("Actualizaciones", "¿Abrir la página de releases en el navegador?", parent=parent):
                    webbrowser.open(release.html_url)

        parent.after(0, finish)

    threading.Thread(target=worker, daemon=True).start()
