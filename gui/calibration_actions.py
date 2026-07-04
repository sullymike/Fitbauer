"""Acciones de calibración local de la GUI Qt."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from mossbauer_i18n import tr


class CalibrationActionsMixin:
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
        }
        self._refresh_calib_label()

    # ── Calibración fija: aplicación al cargar datos ──────────────────────
    def _fixed_calibration_vmax(self) -> float | None:
        """Vmax de la calibración fijada (o ``None`` si no hay ninguna)."""
        info = self.calibration_info
        if not info:
            return None
        value = info.get("velocity_calibrated")
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

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

    def _apply_calibration_on_load(self, path, *, file_vmax: float | None) -> None:
        """Aplica la política de calibración fija al cargar un espectro.

        - ``file_vmax is None`` → el fichero NO trae calibración propia
          (cuentas en bruto: ``.ws5``/``.adt``). Si hay una calibración fijada,
          se **usa** (se impone su Vmax); la calibración no varía.
        - ``file_vmax`` numérico → el fichero trae calibración propia (eje de
          velocidad, CSV/TXT/DAT/EXP). **Sustituye** la calibración fijada por la
          del fichero y se avisa en la barra de estado.
        """
        fixed = self._fixed_calibration_vmax()
        if file_vmax is None:
            # Datos sin calibración propia: aplicar la fija si existe.
            if fixed is not None:
                self._set_vmax_quiet(fixed)
            return
        # Fichero con calibración propia: sustituye.
        if fixed is not None and abs(fixed - float(file_vmax)) > 1e-9:
            try:
                self.statusBar().showMessage(
                    tr("status.calib_replaced",
                       name=getattr(path, "name", str(path)),
                       old=f"{fixed:.4f}", new=f"{float(file_vmax):.4f}",
                       default=(f"Calibración sustituida por la del fichero "
                                f"{getattr(path, 'name', path)}: "
                                f"Vmax {fixed:.4f} → {float(file_vmax):.4f} mm/s")),
                    6000)
            except Exception:
                pass
        keep_iso = (self.calibration_info or {}).get("isomer_shift")
        self.calibration_info = {
            "source": "embedded",
            "calibration_sample": getattr(path, "stem", str(path)),
            "velocity_calibrated": float(file_vmax),
            "isomer_shift": keep_iso,
            "calibration_file_name": getattr(path, "name", str(path)),
            "calibration_file_path": str(path),
        }
        self._set_vmax_quiet(float(file_vmax))
        self._refresh_calib_label()

    def _release_calibration(self) -> None:
        """Libera la calibración fijada (deja de aplicarse a cargas futuras)."""
        self.calibration_info = None
        self._refresh_calib_label()
        try:
            self.statusBar().showMessage(
                tr("status.calib_released", default="Calibración liberada."), 4000)
        except Exception:
            pass

    def _refresh_calib_label(self) -> None:
        if not self.calibration_info:
            self.calib_label.setText("")
            return
        info = self.calibration_info
        src = info.get("source", "local")
        sample = info.get("calibration_sample", "")
        vmax = info.get("velocity_calibrated")
        iso = info.get("isomer_shift")
        fija = tr("label.calib_fixed", default="fija") if vmax not in (None, "") else ""
        tag = f" · <b>{fija}</b>" if fija else ""
        txt = f"Calibración [{src}] {sample}{tag}<br>"
        if vmax is not None:
            try:
                vmax_txt = f"{float(vmax):.4f}"
            except (TypeError, ValueError):
                vmax_txt = str(vmax)
            if iso not in (None, ""):
                try:
                    iso_txt = f"{float(iso):.4f}"
                except (TypeError, ValueError):
                    iso_txt = str(iso)
            else:
                iso_txt = "—"
            txt += f"Vmax = {vmax_txt} mm/s · IS = {iso_txt} mm/s"
        self.calib_label.setText(txt)
