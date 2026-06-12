"""Acceso a la API del laboratorio desde la GUI Qt."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.data_io import load_credentials, save_credentials
from gui.compat import frontend_attr


class WebApiMixin:
    # ── Acceso a la API del laboratorio ──────────────────────────────────
    def _get_api_client(self):
        """Devuelve un MatelecLabClient autenticado o None si el usuario cancela."""
        try:
            from mossbauer_api_client import MatelecLabClient, DEFAULT_BASE_URL
        except ImportError as exc:
            QtWidgets.QMessageBox.critical(
                self, "Web", f"Cliente API no disponible: {exc}")
            return None
        creds = frontend_attr("load_credentials", load_credentials)() or {}
        base = creds.get("api_base") or DEFAULT_BASE_URL
        token = creds.get("token") or ""
        client = MatelecLabClient(base_url=base, token=token)
        if token:
            try:
                if client.token_is_valid():
                    return client
            except Exception:
                pass
        # Token inválido o ausente: pedir credenciales.
        if not self._login_dialog(client, creds):
            return None
        return client

    def _login_dialog(self, client, creds: dict) -> bool:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("webapi.login_title", default="Login (lab API)"))
        form = QtWidgets.QFormLayout(dlg)
        e_user = QtWidgets.QLineEdit(creds.get("username", ""))
        e_pass = QtWidgets.QLineEdit(creds.get("password", ""))
        e_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        cb_remember = QtWidgets.QCheckBox(
            tr("checkbox.remember_credentials_short", default="Remember credentials and token"))
        cb_remember.setChecked(bool(creds.get("username") or creds.get("token")))
        form.addRow(tr("webapi.username", default="Username:"), e_user)
        form.addRow(tr("webapi.password", default="Password:"), e_pass)
        form.addRow(cb_remember)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return False
        user = e_user.text().strip(); pwd = e_pass.text()
        if not user or not pwd:
            return False
        try:
            client.login(user, pwd)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("webapi.login", default="Login"),
                tr("webapi.login_failed", default="Login failed: {err}", err=str(exc)))
            return False
        if cb_remember.isChecked():
            creds = dict(creds); creds["username"] = user
            creds["token"] = client.token
            frontend_attr("save_credentials", save_credentials)(creds)
        return True

    def _open_web_dialog(self, kind: str) -> None:
        """Diálogo Web estilo Tk: server / usuario / contraseña / recordar /
        carpeta destino / buscar / log de depuración. ``kind`` ∈
        {'measurements', 'calibrations'}.
        """
        try:
            from mossbauer_api_client import MatelecLabClient, DEFAULT_BASE_URL
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, tr("msg.web_title", default="Web"),
                f"Cliente API no disponible: {exc}")
            return
        kind_key = "calibraciones" if kind == "calibrations" else "medidas"
        is_calib = (kind == "calibrations")
        creds = frontend_attr("load_credentials", load_credentials)() or {}
        saved_dirs = creds.get("download_dirs", {}) if isinstance(creds.get("download_dirs"), dict) else {}
        default_dir_name = "calibraciones" if is_calib else "medidas"
        effective_dir = saved_dirs.get(kind_key,
                                        str(Path.home() / "Mossbauer" / default_dir_name))
        base_url = creds.get("api_base") or DEFAULT_BASE_URL

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr(f"dialog.web_download_{'calib' if is_calib else 'meas'}",
                              default=f"{'Calibraciones' if is_calib else 'Medidas'} (web)"))
        dlg.resize(820, 600)

        v = QtWidgets.QVBoxLayout(dlg)
        form = QtWidgets.QFormLayout()
        e_server = QtWidgets.QLineEdit(base_url)
        form.addRow(tr("label.server", default="Servidor:"), e_server)
        e_user = QtWidgets.QLineEdit(creds.get("username", ""))
        form.addRow(tr("label.username", default="Usuario:"), e_user)
        pw_row = QtWidgets.QHBoxLayout()
        e_pass = QtWidgets.QLineEdit(creds.get("password", ""))
        e_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        pw_row.addWidget(e_pass, stretch=1)
        cb_remember = QtWidgets.QCheckBox(
            tr("checkbox.remember_credentials", default="Recordar usuario y token"))
        cb_remember.setChecked(bool(creds.get("username") or creds.get("token")))
        pw_row.addWidget(cb_remember)
        pw_wrap = QtWidgets.QWidget(); pw_wrap.setLayout(pw_row)
        form.addRow(tr("label.password", default="Contraseña:"), pw_wrap)
        # Carpeta destino + botones
        dest_row = QtWidgets.QHBoxLayout()
        e_dest = QtWidgets.QLineEdit(effective_dir)
        dest_row.addWidget(e_dest, stretch=1)
        btn_choose = QtWidgets.QPushButton(
            tr("button.choose", default="Elegir..."))
        dest_row.addWidget(btn_choose)
        dest_wrap = QtWidgets.QWidget(); dest_wrap.setLayout(dest_row)
        form.addRow(tr("label.dest_folder", default="Carpeta destino:"), dest_wrap)
        cb_with_calib = QtWidgets.QCheckBox(
            tr("checkbox.download_calibration_too",
               default="Descargar también la calibración asociada"))
        if not is_calib:
            cb_with_calib.setChecked(True)
            form.addRow("", cb_with_calib)
        v.addLayout(form)

        # Buscador + tabla
        search_row = QtWidgets.QHBoxLayout()
        search_row.addWidget(QtWidgets.QLabel(
            tr("label.search", default="Buscar:")))
        e_search = QtWidgets.QLineEdit()
        search_row.addWidget(e_search, stretch=1)
        btn_search = QtWidgets.QPushButton(
            tr("webapi.search_refresh", default="Search/Refresh"))
        search_row.addWidget(btn_search)
        v.addLayout(search_row)
        table = QtWidgets.QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(["id", "fichero", "muestra", "fecha", "T", "vel. display", "calib"])
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeToContents)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        v.addWidget(table, stretch=1)

        # Log de depuración
        log = QtWidgets.QPlainTextEdit()
        log.setReadOnly(True)
        log.setMaximumHeight(140)
        log.setStyleSheet(
            "QPlainTextEdit { background:#111827; color:#d1fae5; "
            "font-family:monospace; font-size:9pt; }")
        v.addWidget(log)

        def debug(msg: str) -> None:
            log.appendPlainText(msg)
            QtWidgets.QApplication.processEvents()

        def choose_dest():
            current = e_dest.text().strip() or str(Path.home())
            folder = QtWidgets.QFileDialog.getExistingDirectory(
                dlg, tr("dialog.select_folder", default="Elegir carpeta"),
                current)
            if folder:
                e_dest.setText(folder)
        btn_choose.clicked.connect(choose_dest)

        items: list[dict] = []

        def _first_value(it: dict, *keys: str):
            """Devuelve el primer campo no vacío, aceptando anidados comunes."""
            nested = (it, it.get("metadata") or {}, it.get("condiciones") or {},
                      it.get("conditions") or {}, it.get("calibracion") or {},
                      it.get("calibration") or {})
            for data in nested:
                if not isinstance(data, dict):
                    continue
                for key in keys:
                    val = data.get(key)
                    if val not in (None, ""):
                        return val
            return ""

        def _short_filename(name: str) -> str:
            base = Path(str(name)).name
            return base[:13]

        def _date_text(it: dict) -> str:
            val = _first_value(it, "fecha", "date", "measured_at", "measurement_date",
                               "created", "created_at", "updated_at")
            txt = str(val or "")
            return txt[:10] if len(txt) >= 10 else txt

        def _calibration_id_text(it: dict) -> str:
            val = _first_value(it, "calibracion_id", "calibration_id", "calib_id",
                               "id_calibracion", "id_calibration")
            if val:
                return str(val)
            cal = it.get("calibracion") or it.get("calibration") or it.get("calibrado")
            if isinstance(cal, dict) and cal.get("id") not in (None, ""):
                return str(cal.get("id"))
            if isinstance(cal, (int, str)):
                return str(cal)
            return ""

        def _temperature_text(it: dict) -> str:
            val = _first_value(it, "temperatura", "temperature", "temp", "temp_k",
                               "temperature_k", "temp_c", "temperature_c")
            return str(val) if val not in (None, "") else ""

        def _velocity_text(it: dict) -> str:
            # En el listado web queremos la velocidad *display* de la medida,
            # no necesariamente la velocidad calibrada/ajustada usada después.
            val = _first_value(it, "velocity_input", "velocidad_input",
                               "velocity_display", "velocidad_display",
                               "display_velocity", "display_vmax", "vmax_display",
                               "velocidad", "velocity", "vmax", "v_max",
                               "velocidad_max", "velocity_max")
            return str(val) if val not in (None, "") else ""

        def build_client():
            base = e_server.text().strip() or DEFAULT_BASE_URL
            token = creds.get("token")
            client = MatelecLabClient(base_url=base, token=token)
            if token:
                try:
                    if client.token_is_valid():
                        debug("Token guardado válido; reusándolo.")
                        return client
                except Exception:
                    pass
            user = e_user.text().strip(); pwd = e_pass.text()
            if not user or not pwd:
                raise RuntimeError("Falta usuario o contraseña para hacer login.")
            debug(f"Login como '{user}'...")
            client.login(user, pwd)
            creds["token"] = client.token
            debug("Token nuevo recibido.")
            return client

        def persist():
            if not cb_remember.isChecked():
                return
            creds["username"] = e_user.text().strip()
            creds["password"] = e_pass.text()
            creds["api_base"] = e_server.text().strip() or DEFAULT_BASE_URL
            if e_dest.text().strip():
                dirs = creds.setdefault("download_dirs", {})
                if not isinstance(dirs, dict):
                    dirs = {}
                    creds["download_dirs"] = dirs
                dirs[kind_key] = e_dest.text().strip()
            frontend_attr("save_credentials", save_credentials)(creds)

        def refresh():
            nonlocal items
            try:
                client = build_client()
            except Exception as exc:
                debug(f"ERROR login: {exc}")
                QtWidgets.QMessageBox.critical(dlg, "Login", str(exc))
                return
            persist()
            try:
                if is_calib:
                    items = list(client.iter_calibraciones(
                        search=e_search.text().strip() or None, limit=200))
                else:
                    items = list(client.iter_medidas(
                        search=e_search.text().strip() or None, limit=200))
            except Exception as exc:
                debug(f"ERROR consulta: {exc}")
                return
            table.setRowCount(0)
            for it in items:
                r = table.rowCount(); table.insertRow(r)
                filename = str(it.get("file_name") or it.get("filename") or it.get("datafile") or "")
                sample = str(_first_value(it, "muestra", "sample", "sample_name", "nombre_muestra", "name"))
                values = [
                    str(it.get("id", "")),
                    _short_filename(filename),
                    sample,
                    _date_text(it),
                    _temperature_text(it),
                    _velocity_text(it),
                    "" if is_calib else _calibration_id_text(it),
                ]
                for c, value in enumerate(values):
                    cell = QtWidgets.QTableWidgetItem(value)
                    if c == 1 and filename:
                        cell.setToolTip(filename)
                    elif c == 2 and sample:
                        cell.setToolTip(sample)
                    table.setItem(r, c, cell)
            debug(f"{len(items)} resultados.")

        btn_search.clicked.connect(refresh)
        e_search.returnPressed.connect(refresh)

        # Filtro local opcional sobre items ya descargados
        def local_filter(_=None):
            q = e_search.text().strip().lower()
            if not q:
                return
            for r in range(table.rowCount()):
                hay = " ".join(
                    table.item(r, c).text().lower()
                    for c in range(table.columnCount())
                    if table.item(r, c) is not None)
                table.setRowHidden(r, q not in hay)
        e_search.textChanged.connect(local_filter)

        # Botones inferiores
        btn_row = QtWidgets.QHBoxLayout()
        btn_list = QtWidgets.QPushButton(tr("button.list", default="Listar"))
        btn_download_only = QtWidgets.QPushButton(tr("button.download", default="Download"))
        btn_dl = QtWidgets.QPushButton(tr("button.download_load", default="Download and load"))
        btn_close = QtWidgets.QPushButton(
            tr("button.close", default="Cerrar"))
        btn_row.addStretch(1)
        btn_row.addWidget(btn_list); btn_row.addWidget(btn_download_only)
        btn_row.addWidget(btn_dl); btn_row.addWidget(btn_close)
        v.addLayout(btn_row)

        def download(load_after: bool = True):
            rows = sorted({i.row() for i in table.selectedIndexes()})
            if not rows:
                debug("Selecciona una fila primero.")
                return
            item_id = table.item(rows[0], 0).text()
            selected_item = next((it for it in items if str(it.get("id", "")) == item_id), {})
            dest = Path(e_dest.text().strip() or (Path.home() / "Mossbauer"))
            calib: dict | None = None
            calib_path: Path | None = None
            try:
                dest.mkdir(parents=True, exist_ok=True)
                client = build_client()
                persist()
                if is_calib:
                    p = client.download_calibracion_datafile(item_id, dest_dir=str(dest))
                    calib = selected_item or client.get_calibracion(item_id)
                    calib_path = Path(p)
                else:
                    p = client.download_datafile(item_id, dest_dir=str(dest))
                    try:
                        calib = client.get_calibracion_de_medida(item_id)
                    except Exception as exc:
                        debug(f"(sin metadatos de calibración asociada: {exc})")
                    if cb_with_calib.isChecked() and calib and "id" in calib:
                        try:
                            calib_path = client.download_calibracion_datafile(
                                calib["id"], dest_dir=str(dest))
                            debug(f"Calibración asociada → {calib_path}")
                        except Exception as exc:
                            debug(f"(no se descargó el fichero de calibración: {exc})")
            except Exception as exc:
                QtWidgets.QMessageBox.critical(dlg, "Descarga", str(exc))
                return
            debug(f"Descargado: {p}")
            if not load_after:
                table.clearSelection()
                return
            try:
                self._load_file(Path(p))
                if is_calib:
                    self._apply_web_calibration_metadata(
                        calibration=calib or selected_item,
                        calibration_path=calib_path or Path(p),
                        debug=debug,
                    )
                elif calib:
                    self._apply_web_calibration_metadata(
                        measurement=selected_item or {"id": item_id},
                        calibration=calib,
                        calibration_path=calib_path,
                        debug=debug,
                    )
                else:
                    debug("La medida cargada no trae calibración asociada aplicable.")
                dlg.accept()
            except Exception as exc:
                QtWidgets.QMessageBox.warning(dlg, "Cargar", str(exc))

        btn_list.clicked.connect(refresh)
        btn_download_only.clicked.connect(lambda: download(False))
        btn_dl.clicked.connect(lambda: download(True))
        btn_close.clicked.connect(dlg.reject)
        dlg.exec()

    def _apply_web_calibration_metadata(self, *, calibration: dict | None,
                                        measurement: dict | None = None,
                                        calibration_path: Path | None = None,
                                        debug=None) -> None:
        """Guarda en la GUI los metadatos de una calibración web y aplica Vmax.

        La API devuelve ``velocity_calibrated`` e ``isomer_shift`` como
        metadatos de la calibración. Al cargar una medida desde la web, estos
        valores deben quedar en ``self.calibration_info`` igual que una
        calibración local, y ``velocity_calibrated`` debe reescalar el eje de
        velocidad del fichero activo.
        """
        if not calibration:
            if debug is not None:
                debug("La API no devolvió metadatos de calibración.")
            return

        def first_value(data: dict, *keys: str):
            nested = (data, data.get("metadata") or {}, data.get("condiciones") or {},
                      data.get("conditions") or {})
            for item in nested:
                if not isinstance(item, dict):
                    continue
                for key in keys:
                    value = item.get(key)
                    if value not in (None, ""):
                        return value
            return None

        velocity = first_value(calibration, "velocity_calibrated", "vmax_calibrated",
                               "velocity", "velocidad", "vmax", "v_max")
        iso = first_value(calibration, "isomer_shift", "isomershift",
                          "isomer", "iso", "delta")
        info = {
            "source": "web_api",
            "medida_id": (measurement or {}).get("id"),
            "calibration_id": calibration.get("id") or first_value(
                measurement or {}, "calibration_id", "calibracion_id", "calib_id"),
            "calibration_sample": first_value(
                calibration, "sample", "muestra", "sample_name",
                "nombre_muestra", "name"),
            "calibration_date": first_value(
                calibration, "date", "fecha", "measured_at", "created_at", "created"),
            "velocity_calibrated": velocity,
            "isomer_shift": iso,
            "calibration_file_name": Path(calibration_path).name if calibration_path else None,
            "calibration_file_path": str(calibration_path) if calibration_path else None,
        }
        for key in ("velocity_uncertainty", "vmax_uncertainty", "velocity_error",
                    "vmax_error", "sigma_vmax"):
            value = first_value(calibration, key)
            if value not in (None, ""):
                info[key] = value

        self.calibration_info = info
        self._refresh_calib_label()
        if debug is not None:
            debug(f"Calibración web aplicada: id={info.get('calibration_id') or '—'} "
                  f"Vmax={velocity if velocity not in (None, '') else '—'} "
                  f"IS={iso if iso not in (None, '') else '—'}")

        if velocity in (None, ""):
            if debug is not None:
                debug("La calibración no trae velocity_calibrated; no se aplica Vmax.")
            return
        try:
            vmax = float(velocity)
        except (TypeError, ValueError):
            if debug is not None:
                debug(f"velocity_calibrated no numérico: {velocity!r}")
            return

        self.calib.vmax.set_value(vmax)
        if self.file.counts is not None:
            calib_state = self.calib.to_view_state()
            self._refold_current_data(float(calib_state.center))
        self._refresh_plot()

    # ── Subir sesión al API ──────────────────────────────────────────────
    def on_upload_session(self) -> None:
        if self.file.path is None:
            return
        client = self._get_api_client()
        if client is None:
            return
        # Sugiere el medida_id si ya conocemos el fichero en remoto
        suggested = ""
        try:
            m = client.find_medida_by_filename(self.file.path.name)
            if m and "id" in m:
                suggested = str(m["id"])
        except Exception:
            pass
        medida_id, ok = QtWidgets.QInputDialog.getText(
            self, tr("file.upload_session"), "medida_id:", text=suggested)
        if not ok or not medida_id.strip():
            return
        note, _ = QtWidgets.QInputDialog.getText(
            self, tr("file.upload_session"), "Nota (opcional):", text="")
        try:
            payload = self._session_payload()
            data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            r = client.upload_analysis(medida_id.strip(), data=data,
                                        filename="qt_session.json", note=note or "")
            self.statusBar().showMessage(
                f"Subido como analysis #{r.get('id', '?')}", 5000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("file.upload_session"), str(exc))
