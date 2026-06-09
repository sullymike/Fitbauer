"""Gestión de actualizaciones de la GUI Qt."""
from __future__ import annotations

import json
import os
import threading
import webbrowser
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from mossbauer_i18n import tr
from core.constants import APP_VERSION
from core.data_io import CONFIG_DIR, SETTINGS_PATH
from gui.compat import frontend_attr
from mossbauer_updater import (
    choose_download, download_file, find_release_checksum,
    install_zip_update, is_newer, is_zip_update, latest_release,
    _pip_install_requirements, _update_pip_stamp, check_requirements_if_needed,
    load_update_settings, save_update_settings,
)

ROOT = Path(__file__).resolve().parents[1]


class UpdateMixin:
    def _qt_update_prefs(self) -> dict:
        try:
            if SETTINGS_PATH.exists():
                data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def _updates_at_startup_enabled(self) -> bool:
        return bool(self._qt_update_prefs().get("check_updates_on_startup", False))

    def _save_qt_update_prefs(self, *, startup: bool, checksum: bool) -> None:
        current = self._qt_update_prefs()
        current["check_updates_on_startup"] = bool(startup)
        current["verify_update_checksum"] = bool(checksum)
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")

    def _downloads_dir(self) -> Path:
        for name in ("Descargas", "Downloads"):
            path = Path.home() / name
            if path.exists():
                return path
        return Path.home()

    def _run_in_ui_thread(self, fn) -> None:
        bridge = getattr(self, "_ui_bridge", None)
        if bridge is not None:
            bridge.call.emit(fn)
            return
        QtCore.QTimer.singleShot(0, fn)

    def on_configure_updates(self) -> None:
        """Configura el canal de releases y las opciones propias del front-end Qt."""
        update_cfg = load_update_settings(CONFIG_DIR)
        qt_cfg = self._qt_update_prefs()

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("help.configure_updates"))
        dlg.setModal(True)
        v = QtWidgets.QVBoxLayout(dlg)

        v.addWidget(QtWidgets.QLabel("Canal de avisos de actualización:"))
        rb_stable = QtWidgets.QRadioButton("Solo versiones estables")
        rb_all = QtWidgets.QRadioButton("Estables y versiones no estables/beta")
        if update_cfg.get("channel", "stable") == "all":
            rb_all.setChecked(True)
        else:
            rb_stable.setChecked(True)
        v.addWidget(rb_stable)
        v.addWidget(rb_all)

        hint = QtWidgets.QLabel(
            "Las versiones beta sirven para probar cambios. Si eliges betas, "
            "el programa avisará también de prereleases de GitHub."
        )
        hint.setWordWrap(True)
        v.addWidget(hint)

        cb_startup = QtWidgets.QCheckBox("Buscar actualizaciones al arrancar (silencioso)")
        cb_startup.setChecked(bool(qt_cfg.get("check_updates_on_startup", False)))
        v.addWidget(cb_startup)
        cb_checksum = QtWidgets.QCheckBox("Verificar checksum SHA-256 al descargar")
        cb_checksum.setChecked(bool(qt_cfg.get("verify_update_checksum", True)))
        v.addWidget(cb_checksum)

        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        channel = "all" if rb_all.isChecked() else "stable"
        try:
            save_update_settings(CONFIG_DIR, {"channel": channel}, parent=None)
            self._save_qt_update_prefs(
                startup=cb_startup.isChecked(), checksum=cb_checksum.isChecked())
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, tr("help.configure_updates"), str(exc))

    # ── Check for updates ───────────────────────────────────────────────
    def check_for_updates(self, silent: bool = False) -> None:
        """Comprueba GitHub Releases en segundo plano, igual que la interfaz Tk."""
        update_settings = load_update_settings(CONFIG_DIR)
        include_prereleases = update_settings.get("channel", "stable") == "all"
        verify_checksum = bool(self._qt_update_prefs().get("verify_update_checksum", True))
        channel_txt = "estables y beta" if include_prereleases else "solo estables"
        if not silent:
            self.statusBar().showMessage("Buscando actualizaciones…")

        def worker() -> None:
            try:
                release = frontend_attr("latest_release", latest_release)(include_prereleases=include_prereleases)
                newer = frontend_attr("is_newer", is_newer)(release.tag, APP_VERSION)
            except Exception as exc:
                if not silent:
                    self._run_in_ui_thread(
                        lambda e=exc: QtWidgets.QMessageBox.warning(
                            self, tr("help.check_updates"),
                            f"No se pudo comprobar GitHub Releases:\n{e}"))
                return

            def finish() -> None:
                if not newer:
                    if not silent:
                        QtWidgets.QMessageBox.information(
                            self, tr("help.check_updates"),
                            f"Ya tienes la última versión ({APP_VERSION}) para el canal: {channel_txt}.")
                    return
                self._show_update_available_dialog(release, channel_txt, verify_checksum)

            self._run_in_ui_thread(finish)

        frontend_attr("threading", threading).Thread(target=worker, daemon=True).start()

    def on_check_updates(self) -> None:
        self.check_for_updates(silent=False)

    def _show_update_available_dialog(self, release, channel_txt: str, verify_checksum: bool) -> None:
        body = (release.body or "").strip()
        release_kind = "no estable/beta" if getattr(release, "prerelease", False) else "estable"
        msg = (
            f"Hay una versión nueva disponible ({release_kind}).\n\n"
            f"Canal configurado: {channel_txt}\n"
            f"Versión actual:    {APP_VERSION}\n"
            f"Nueva versión:     {release.tag}\n\n"
            + (("─" * 60) + "\n\n" + body + "\n\n" if body else "")
            + "¿Quieres descargarla ahora?"
        )

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Actualización disponible")
        dlg.resize(860, 480)
        v = QtWidgets.QVBoxLayout(dlg)
        text = QtWidgets.QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(msg)
        v.addWidget(text, stretch=1)
        buttons = QtWidgets.QDialogButtonBox()
        btn_yes = buttons.addButton("Sí, descargar ahora", QtWidgets.QDialogButtonBox.AcceptRole)
        buttons.addButton("No por ahora", QtWidgets.QDialogButtonBox.RejectRole)
        buttons.accepted.connect(dlg.accept); buttons.rejected.connect(dlg.reject)
        v.addWidget(buttons)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            url, filename = frontend_attr("choose_download", choose_download)(release, prefer_exe=(os.name == "nt"))
            self._download_update_in_background(release, url, filename, verify_checksum)
        else:
            answer = QtWidgets.QMessageBox.question(
                self, "Actualizaciones", "¿Abrir la página de releases en el navegador?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No)
            if answer == QtWidgets.QMessageBox.Yes:
                frontend_attr("webbrowser", webbrowser).open(release.html_url)
        btn_yes.deleteLater()

    def _download_update_in_background(self, release, url: str, filename: str, verify_checksum: bool) -> None:
        self.statusBar().showMessage("Descargando actualización…")

        def worker_download() -> None:
            expected = None
            if verify_checksum:
                try:
                    expected = frontend_attr("find_release_checksum", find_release_checksum)(release, filename)
                except Exception:
                    expected = None
            try:
                path = frontend_attr("download_file", download_file)(
                    url, self._downloads_dir(), filename,
                    expected_sha256=expected if verify_checksum else None)
            except Exception as exc:
                errmsg = (
                    "No se pudo descargar o verificar la actualización"
                    if verify_checksum else "No se pudo descargar la actualización"
                )
                self._run_in_ui_thread(
                    lambda e=exc: QtWidgets.QMessageBox.critical(
                        self, "Actualizaciones", f"{errmsg}:\n{e}"))
                return
            verified = verify_checksum and expected is not None
            self._run_in_ui_thread(lambda: self._finish_downloaded_update(path, verified, verify_checksum))

        frontend_attr("threading", threading).Thread(target=worker_download, daemon=True).start()

    def _finish_downloaded_update(self, path: Path, verified: bool, verify_checksum: bool) -> None:
        if verify_checksum:
            integridad = (
                "Integridad verificada con SHA-256."
                if verified
                else "Aviso: la release no publica checksum; no se pudo verificar la integridad."
            )
            integridad_suffix = f"\n\n{integridad}"
        else:
            integridad_suffix = ""
        if frontend_attr("is_zip_update", is_zip_update)(path):
            answer = QtWidgets.QMessageBox.question(
                self, "Actualización descargada",
                f"Descargado en:\n{path}{integridad_suffix}\n\n"
                "¿Instalar ahora sobre esta carpeta del programa?\n"
                "Después solo tendrás que cerrar y volver a abrir el programa.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes)
            if answer == QtWidgets.QMessageBox.Yes:
                try:
                    frontend_attr("install_zip_update", install_zip_update)(path, ROOT)
                    pip_msg = frontend_attr("_pip_install_requirements", _pip_install_requirements)(ROOT)
                    frontend_attr("_update_pip_stamp", _update_pip_stamp)(ROOT, CONFIG_DIR)
                except Exception as exc:
                    QtWidgets.QMessageBox.critical(
                        self, "Actualizaciones", f"No se pudo instalar la actualización:\n{exc}")
                    return
                pip_suffix = f"\n\n{pip_msg}" if pip_msg else ""
                QtWidgets.QMessageBox.information(
                    self, "Actualización instalada",
                    "La nueva versión se ha descomprimido en la carpeta del programa."
                    f"{pip_suffix}\n\n"
                    "Cierra y vuelve a abrir el programa para usarla.")
                return
        QtWidgets.QMessageBox.information(
            self, "Actualización descargada",
            f"Descargado en:\n{path}{integridad_suffix}\n\n"
            "Cierra el programa y usa ese fichero para instalar/ejecutar la nueva versión.")

    def _check_requirements_background(self) -> None:
        try:
            frontend_attr("check_requirements_if_needed", check_requirements_if_needed)(ROOT, CONFIG_DIR)
        except Exception:
            pass
