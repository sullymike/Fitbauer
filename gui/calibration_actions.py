"""Acciones de calibración local de la GUI Qt."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from mossbauer_i18n import tr


class CalibrationActionsMixin:
    # ── Equipos: biblioteca y asignación de calibración por fecha ─────────
    def _instrument_library(self):
        """Biblioteca de equipos (una por ventana; los tests la sustituyen)."""
        lib = getattr(self, "_instruments", None)
        if lib is None:
            from core.instruments import InstrumentLibrary
            lib = self._instruments = InstrumentLibrary()
        return lib

    def _instrument_profile(self, name):
        if not name:
            return None
        try:
            return self._instrument_library().get(name)
        except (OSError, ValueError):
            return None

    def _instrument_calibration(self, path, imported, instrument, record_id=None):
        """:class:`~core.instruments.CalibrationChoice` del equipo para un fichero:
        la elegida a mano (``record_id``) o la que da la regla del equipo."""
        from core.instruments import CalibrationChoice
        if self._instrument_profile(instrument) is None:
            return CalibrationChoice(None)
        return self._instrument_library().choose_calibration(
            instrument, imported, path, record_id=record_id)

    def _series_calibration(self, path, imported):
        """Vmax de un fichero de una serie según su equipo (o ``None``).

        Solo si el espectro activo se abrió con un equipo. Devuelve también la
        información para la tabla de resultados.
        """
        from core.spectrum_loading import calibration_vmax
        instrument = getattr(self.file, "instrument", None)
        if not instrument:
            return None, None
        choice = self._instrument_calibration(path, imported, instrument)
        record, date = choice.record, choice.date
        measured = date.isoformat() if date else ""
        if record is None:
            return None, ({"measured": measured, "date": "", "vmax": ""}
                          if date else None)
        info = self._instrument_library().calibration_info(instrument, choice)
        vmax = calibration_vmax(info, getattr(self, "sextet_pattern", "normos"))
        return vmax, {"measured": measured, "date": record.date.isoformat(),
                      "vmax": vmax, "date_source": choice.origin}

    def _assign_instrument_calibration(self, path, imported, instrument,
                                       record_id=None) -> None:
        """Fija la calibración del equipo para el fichero: la elegida a mano
        (``record_id``) o la de la regla del equipo (por fecha o la más reciente)."""
        if not instrument:
            return
        choice = self._instrument_calibration(path, imported, instrument, record_id)
        info = (self._instrument_library().calibration_info(instrument, choice)
                if choice.record is not None else None)
        self._take_instrument_calibration(instrument, choice, info)

    def _take_instrument_calibration(self, instrument, choice, info, *,
                                     show: bool = True) -> str | None:
        """Deja fijada la calibración ``info`` del equipo o, si no hay ninguna
        aplicable, mantiene la fijada y devuelve el aviso del porqué (y lo
        muestra con ``show``; al cargar se muestra junto al resto)."""
        from core.spectrum_loading import missing_calibration_reason
        if info is not None:
            self.calibration_info = info
            self._refresh_calib_label()
            return None
        reason = missing_calibration_reason(choice)
        if reason == "none":
            msg = tr("instr.no_calibrations", name=instrument,
                     default="«{name}» no tiene calibraciones; "
                             "se mantiene la calibración actual.")
        elif reason == "no_date":
            msg = tr("instr.no_date", name=instrument,
                     default="Sin fecha de medida: no se asigna calibración de «{name}».")
        else:
            msg = tr("instr.no_calibration", name=instrument, date=choice.date.isoformat(),
                     default="«{name}» no tiene calibraciones del {date} o anteriores; "
                             "se mantiene la calibración actual.")
        if show:
            self.statusBar().showMessage(msg, 8000)
        return msg

    # ── Calibración rápida desde el cuadro de fichero ─────────────────────
    def _show_file_box_menu(self, pos: QtCore.QPoint) -> None:
        if self.file.path is None:
            return
        menu = QtWidgets.QMenu(self)
        act_quick = menu.addAction(tr("context.use_as_calibration_quick"))
        act_detail = menu.addAction(tr("context.use_as_calibration_detailed"))
        act_release = None
        if self.calibration_info:
            menu.addSeparator()
            act_release = menu.addAction(
                tr("context.release_calibration", default="Liberar calibración fijada"))
        chosen = menu.exec(self.file_box.mapToGlobal(pos))
        if chosen == act_quick:
            self._use_as_calibration_quick()
        elif chosen == act_detail:
            self._use_as_calibration_detailed()
        elif act_release is not None and chosen == act_release:
            self._release_calibration()

    def _use_as_calibration_quick(self) -> None:
        if self.file.path is None:
            return
        calib_state = self.calib.to_view_state()
        comp_state = self.components_panels[0].to_view_state()
        vmax = float(calib_state.vmax)
        iso = float(comp_state.value("delta"))
        name = self.file.path.stem
        self.calibration_info = {
            "source": "local", "calibration_sample": name,
            "velocity_calibrated": vmax, "isomer_shift": iso,
            "calibration_file_name": self.file.path.name,
            "calibration_file_path": str(self.file.path),
            # Vmax e IS dependen del patrón con que se ajustó el α-Fe.
            "sextet_pattern": getattr(self, "sextet_pattern", "normos"),
        }
        self._refresh_calib_label()
        QtWidgets.QMessageBox.information(
            self, tr("file.use_as_calibration"),
            tr("msg.use_as_calib_quick_ok",
               name=name, vmax=f"{vmax:.4f}", iso=f"{iso:.4f}"))

    def _use_as_calibration_detailed(self) -> None:
        if self.file.path is None:
            return
        from core.param_overrides import effective_calibration_specs, effective_component_specs
        _cs = effective_calibration_specs()
        _cp = effective_component_specs()
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("file.use_as_calibration"))
        form = QtWidgets.QFormLayout(dlg)
        e_name = QtWidgets.QLineEdit(self.file.path.stem)
        calib_state = self.calib.to_view_state()
        comp_state = self.components_panels[0].to_view_state()
        e_vmax = QtWidgets.QDoubleSpinBox()
        e_vmax.setRange(_cs["vmax"].lo, _cs["vmax"].hi)
        e_vmax.setDecimals(_cs["vmax"].decimals)
        e_vmax.setValue(float(calib_state.vmax))
        e_iso = QtWidgets.QDoubleSpinBox()
        e_iso.setRange(_cp["delta"].lo, _cp["delta"].hi)
        e_iso.setDecimals(_cp["delta"].decimals)
        e_iso.setValue(float(comp_state.value("delta")))
        form.addRow(tr("label.calib_sample_name"), e_name)
        form.addRow(tr("label.calib_vmax"), e_vmax)
        form.addRow(tr("label.calib_is"), e_iso)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        self.calibration_info = {
            "source": "local",
            "calibration_sample": e_name.text() or self.file.path.stem,
            "velocity_calibrated": float(e_vmax.value()),
            "isomer_shift": float(e_iso.value()),
            "calibration_file_name": self.file.path.name,
            "calibration_file_path": str(self.file.path),
            "sextet_pattern": getattr(self, "sextet_pattern", "normos"),
        }
        self._refresh_calib_label()

    # ── Calibración fija: aplicación al cargar datos ──────────────────────
    def _calibration_scale(self) -> float:
        """Factor que lleva la Vmax (y el IS) de la calibración al patrón activo."""
        from core.constants import convert_vmax
        from core.spectrum_loading import calibration_pattern
        origen = calibration_pattern(self.calibration_info)
        if origen is None:
            return 1.0
        return convert_vmax(1.0, origen, getattr(self, "sextet_pattern", "normos"))

    def _fixed_calibration_vmax(self) -> float | None:
        """Vmax de la calibración fijada en el patrón activo (o ``None``).

        Si la calibración se hizo con otro patrón, se convierte: es la Vmax
        que da 33.0 T al mismo α-Fe con el patrón activo.
        """
        from core.spectrum_loading import calibration_vmax
        return calibration_vmax(self.calibration_info,
                                getattr(self, "sextet_pattern", "normos"))

    def _reapply_fixed_calibration(self) -> None:
        """Vuelve a imponer la Vmax de la calibración fijada (p. ej. al cambiar
        de patrón del sextete, que cambia la Vmax equivalente)."""
        vmax = self._fixed_calibration_vmax()
        if vmax is None or getattr(self.file, "path", None) is None:
            return
        if hasattr(self, "calib") and hasattr(self.calib, "vmax"):
            self.calib.vmax.set_value(float(vmax))
        self._refresh_calib_label()
        # set_value no emite señal: el eje de los datos y el gráfico se
        # rehacen aquí con la Vmax nueva.
        self._refresh_plot()

    def _set_vmax_quiet(self, vmax: float) -> None:
        """Fija el control de Vmax sin disparar refolds intermedios."""
        if not (hasattr(self, "calib") and hasattr(self.calib, "vmax")):
            return
        prev = bool(getattr(self, "_building", False))
        self._building = True
        try:
            self.calib.vmax.set_value(float(vmax))
        finally:
            self._building = prev

    def _apply_calibration_on_load(self, opened) -> None:
        """Aplica al cargar la prioridad entre calibraciones
        (:func:`core.spectrum_loading.calibration_after_load`) e impone su Vmax.

        Un fichero con eje de velocidad propio sustituye la calibración fijada
        (y se avisa si cambia la Vmax); unas cuentas usan la del equipo, si la
        hay, o la fijada.
        """
        from core.spectrum_loading import calibration_after_load
        before = self._fixed_calibration_vmax()
        previous = self.calibration_info
        panel_vmax = (float(self.calib.to_view_state().vmax)
                      if hasattr(self, "calib") else None)
        info = calibration_after_load(previous, opened, panel_vmax)
        if opened.has_velocity_axis:
            new = opened.file_vmax
            if before is not None and abs(before - new) > 1e-9:
                # Se muestra al terminar la carga, junto al resto de avisos.
                name = opened.path.name
                self._load_notes = getattr(self, "_load_notes", None) or []
                self._load_notes.append(
                    tr("status.calib_replaced", name=name,
                       old=f"{before:.4f}", new=f"{new:.4f}",
                       default=(f"Calibración sustituida por la del fichero "
                                f"{name}: Vmax {before:.4f} → {new:.4f} mm/s")))
        if info is not self.calibration_info:
            self.calibration_info = info
            self._refresh_calib_label()
        vmax = self._fixed_calibration_vmax()
        if (vmax is None and not opened.has_velocity_axis
                and (previous or {}).get("source") == "embedded"):
            # Tras un fichero con eje propio sin calibración detrás: vuelve
            # la Vmax que había en el panel antes de abrirlo.
            vmax = previous.get("replaced_vmax")
        if vmax is not None:
            self._set_vmax_quiet(vmax)

    def _release_calibration(self) -> None:
        """Libera la calibración fijada (deja de aplicarse a cargas futuras)."""
        self.calibration_info = None
        self._refresh_calib_label()
        try:
            self.statusBar().showMessage(
                tr("status.calib_released", default="Calibración liberada."), 4000)
        except Exception:
            pass

    @staticmethod
    def _instrument_calib_text(info: dict) -> str:
        """«Equipo X: calibración del … (por qué esa)» para la etiqueta."""
        rule = info.get("calibration_rule") or "date"
        name, cal = info.get("instrument", ""), info.get("calibration_date", "")
        if rule == "latest":
            return tr("instr.label_latest", name=name, cal=cal,
                      default="Equipo {name}: calibración del {cal} (la más reciente)")
        if rule == "manual":
            return tr("instr.label_manual", name=name, cal=cal,
                      default="Equipo {name}: calibración del {cal} (elegida a mano)")
        key = ("instr.label_file_date" if info.get("measurement_date_source") == "file"
               else "instr.label")
        return tr(key, name=name, cal=cal, measured=info.get("measurement_date") or "",
                  default=("Equipo {name}: calibración del {cal} (medida {measured})"
                           if key == "instr.label" else
                           "Equipo {name}: calibración del {cal} (medida {measured}, "
                           "fecha del fichero)"))

    def _refresh_calib_label(self) -> None:
        if not self.calibration_info:
            self.calib_label.setText("")
            return
        info = self.calibration_info
        code = str(info.get("source") or "local")
        src = {"local": tr("calib.src_local"), "instrument": tr("calib.src_instrument"),
               "web_api": tr("calib.src_web_api"),
               "embedded": tr("calib.src_embedded")}.get(code, code)
        # Calibración local: el nombre del fichero dice más que su raíz
        # («calibration» parecía un rótulo sin traducir).
        sample = (info.get("calibration_file_name") if code == "local" else None) \
            or info.get("calibration_sample", "")
        vmax = info.get("velocity_calibrated")
        iso = info.get("isomer_shift")
        fija = tr("label.calib_fixed", default="fija") if vmax not in (None, "") else ""
        tag = f" · <b>{fija}</b>" if fija else ""
        txt = tr("calib.label", src=src, sample=sample) + f"{tag}<br>"
        escala = self._calibration_scale()
        if vmax is not None:
            try:
                vmax_txt = f"{float(vmax) * escala:.4f}"
            except (TypeError, ValueError):
                vmax_txt = str(vmax)
            iso_ref = self.calibration_iso_ref()
            iso_txt = f"{iso_ref:.4f}" if iso_ref is not None else "—"
            txt += f"Vmax = {vmax_txt} mm/s · IS = {iso_txt} mm/s"
            if info.get("source") == "instrument":
                txt += "<br>" + self._instrument_calib_text(info)
            if abs(escala - 1.0) > 1e-12:
                txt += "<br>" + tr(
                    "calib.converted", vmax=f"{float(vmax):.4f}",
                    default=("convertida desde el patrón histórico "
                             "(Vmax original {vmax} mm/s)").format(vmax=f"{float(vmax):.4f}"))
        self.calib_label.setText(txt)
