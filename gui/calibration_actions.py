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
        chosen = menu.exec(self.file_box.mapToGlobal(pos))
        if chosen == act_quick:
            self._use_as_calibration_quick()
        elif chosen == act_detail:
            self._use_as_calibration_detailed()

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

    def _refresh_calib_label(self) -> None:
        if not self.calibration_info:
            self.calib_label.setText("")
            return
        info = self.calibration_info
        src = info.get("source", "local")
        sample = info.get("calibration_sample", "")
        vmax = info.get("velocity_calibrated")
        iso = info.get("isomer_shift")
        txt = f"Calibración [{src}] {sample}<br>"
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
