"""Gestión de actualizaciones de la GUI Qt."""
from __future__ import annotations

import os
import threading
import webbrowser
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from mossbauer_i18n import tr
from core.constants import APP_VERSION
from core.data_io import CONFIG_DIR, load_settings, update_settings
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
        return load_settings()

    def _updates_at_startup_enabled(self) -> bool:
        return bool(self._qt_update_prefs().get("check_updates_on_startup", False))

    def _save_qt_update_prefs(self, *, startup: bool, checksum: bool) -> None:
        # Los errores de escritura se propagan: el llamador muestra el aviso.
        update_settings(
            check_updates_on_startup=bool(startup),
            verify_update_checksum=bool(checksum),
        )

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

        v.addWidget(QtWidgets.QLabel(tr("updates.channel_label")))
        rb_stable = QtWidgets.QRadioButton(tr("updates.channel_stable"))
        rb_all = QtWidgets.QRadioButton(tr("updates.channel_all"))
        if update_cfg.get("channel", "stable") == "all":
            rb_all.setChecked(True)
        else:
            rb_stable.setChecked(True)
        v.addWidget(rb_stable)
        v.addWidget(rb_all)

        hint = QtWidgets.QLabel(tr("updates.beta_hint"))
        hint.setWordWrap(True)
        v.addWidget(hint)

        cb_startup = QtWidgets.QCheckBox(tr("updates.check_on_startup"))
        cb_startup.setChecked(bool(qt_cfg.get("check_updates_on_startup", False)))
        v.addWidget(cb_startup)
        cb_checksum = QtWidgets.QCheckBox(tr("updates.verify_checksum"))
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
        """Comprueba GitHub Releases en segundo plano (sin bloquear la GUI)."""
        update_settings = load_update_settings(CONFIG_DIR)
        include_prereleases = update_settings.get("channel", "stable") == "all"
        verify_checksum = bool(self._qt_update_prefs().get("verify_update_checksum", True))
        channel_txt = (tr("updates.channel_txt_all") if include_prereleases
                       else tr("updates.channel_txt_stable"))
        if not silent:
            self.statusBar().showMessage(tr("updates.checking"))

        def worker() -> None:
            try:
                release = frontend_attr("latest_release", latest_release)(include_prereleases=include_prereleases)
                newer = frontend_attr("is_newer", is_newer)(release.tag, APP_VERSION)
            except Exception as exc:
                if not silent:
                    self._run_in_ui_thread(
                        lambda e=exc: QtWidgets.QMessageBox.warning(
                            self, tr("help.check_updates"),
                            tr("updates.check_failed", error=str(e))))
                return

            def finish() -> None:
                if not newer:
                    if not silent:
                        QtWidgets.QMessageBox.information(
                            self, tr("help.check_updates"),
                            tr("updates.up_to_date", version=APP_VERSION, channel=channel_txt))
                    return
                self._show_update_available_dialog(release, channel_txt, verify_checksum)

            self._run_in_ui_thread(finish)

        frontend_attr("threading", threading).Thread(target=worker, daemon=True).start()

    def on_check_updates(self) -> None:
        self.check_for_updates(silent=False)

    def _show_update_available_dialog(self, release, channel_txt: str, verify_checksum: bool) -> None:
        body = (release.body or "").strip()
        release_kind = (tr("updates.kind_beta") if getattr(release, "prerelease", False)
                        else tr("updates.kind_stable"))
        msg = (
            tr("updates.new_version_msg", kind=release_kind, channel=channel_txt,
               current=APP_VERSION, new=release.tag)
            + (("─" * 60) + "\n\n" + body + "\n\n" if body else "")
            + tr("updates.download_now_q")
        )

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("updates.available_title"))
        dlg.resize(860, 480)
        v = QtWidgets.QVBoxLayout(dlg)
        text = QtWidgets.QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(msg)
        v.addWidget(text, stretch=1)
        buttons = QtWidgets.QDialogButtonBox()
        btn_yes = buttons.addButton(tr("updates.btn_download_now"), QtWidgets.QDialogButtonBox.AcceptRole)
        buttons.addButton(tr("updates.btn_not_now"), QtWidgets.QDialogButtonBox.RejectRole)
        buttons.accepted.connect(dlg.accept); buttons.rejected.connect(dlg.reject)
        v.addWidget(buttons)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            url, filename = frontend_attr("choose_download", choose_download)(release, prefer_exe=(os.name == "nt"))
            self._download_update_in_background(release, url, filename, verify_checksum)
        else:
            answer = QtWidgets.QMessageBox.question(
                self, tr("updates.title"), tr("updates.open_releases_q"),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No)
            if answer == QtWidgets.QMessageBox.Yes:
                frontend_attr("webbrowser", webbrowser).open(release.html_url)
        btn_yes.deleteLater()

    def _download_update_in_background(self, release, url: str, filename: str, verify_checksum: bool) -> None:
        self.statusBar().showMessage(tr("updates.downloading"))

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
                    tr("updates.download_verify_failed")
                    if verify_checksum else tr("updates.download_failed")
                )
                self._run_in_ui_thread(
                    lambda e=exc: QtWidgets.QMessageBox.critical(
                        self, tr("updates.title"), f"{errmsg}:\n{e}"))
                return
            verified = verify_checksum and expected is not None
            self._run_in_ui_thread(lambda: self._finish_downloaded_update(path, verified, verify_checksum))

        frontend_attr("threading", threading).Thread(target=worker_download, daemon=True).start()

    def _finish_downloaded_update(self, path: Path, verified: bool, verify_checksum: bool) -> None:
        if verify_checksum:
            integridad = (
                tr("updates.integrity_ok")
                if verified
                else tr("updates.integrity_missing")
            )
            integridad_suffix = f"\n\n{integridad}"
        else:
            integridad_suffix = ""
        if frontend_attr("is_zip_update", is_zip_update)(path):
            answer = QtWidgets.QMessageBox.question(
                self, tr("updates.downloaded_title"),
                tr("updates.install_now_q", path=path, integrity=integridad_suffix),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes)
            if answer == QtWidgets.QMessageBox.Yes:
                try:
                    frontend_attr("install_zip_update", install_zip_update)(path, ROOT)
                    pip_msg = frontend_attr("_pip_install_requirements", _pip_install_requirements)(ROOT)
                    frontend_attr("_update_pip_stamp", _update_pip_stamp)(ROOT, CONFIG_DIR)
                except Exception as exc:
                    QtWidgets.QMessageBox.critical(
                        self, tr("updates.title"),
                        tr("updates.install_failed", error=str(exc)))
                    return
                pip_suffix = f"\n\n{pip_msg}" if pip_msg else ""
                QtWidgets.QMessageBox.information(
                    self, tr("updates.installed_title"),
                    tr("updates.installed_msg", pip=pip_suffix))
                return
        QtWidgets.QMessageBox.information(
            self, tr("updates.downloaded_title"),
            tr("updates.downloaded_msg", path=path, integrity=integridad_suffix))

    def _check_requirements_background(self) -> None:
        try:
            frontend_attr("check_requirements_if_needed", check_requirements_if_needed)(ROOT, CONFIG_DIR)
        except Exception:
            pass
