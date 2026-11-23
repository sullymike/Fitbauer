"""Plegado explícito en la GUI Qt: desplegable, datos y sesión."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pytestqt")
try:
    import mossbauer_qt as mq
except Exception as exc:  # pragma: no cover
    pytest.skip(f"PySide6 / mossbauer_qt no disponible: {exc}", allow_module_level=True)

DATA = Path(__file__).resolve().parents[1] / "data_sample"
SPECTRUM = DATA / "hierro_metalico_alphaFe.adt"


@pytest.fixture
def make_window(qapp):
    created: list = []

    def _make():
        w = mq.MossbauerQtWindow()
        created.append(w)
        return w

    yield _make
    for w in created:
        w.mark_saved()          # sin «¿Guardar cambios?» modal al cerrar
        w.close()
        w.deleteLater()
    mq.QtCore.QCoreApplication.sendPostedEvents(None, mq.QtCore.QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_fold_combo_recomputes_data(make_window):
    win = make_window()
    win._load_file(SPECTRUM)
    n = win.file.counts.size
    assert win.file.y_data.size == n // 2
    win.calib.set_fold_mode("two_branches")
    assert win.file.y_data.size == win.file.velocity.size == n
    assert win.calib.fit_center.isEnabled()
    win.calib.set_fold_mode("single_sweep")
    assert win.file.velocity[0] == pytest.approx(-win.calib.vmax.value())
    assert not win.calib.fit_center.isEnabled() and not win.calib.center.isEnabled()
    win.calib.set_fold_mode("single_sweep", reverse=True)
    assert win.file.velocity[0] == pytest.approx(win.calib.vmax.value())
    win.calib.set_fold_mode("fold", reverse=False)
    assert win.file.y_data.size == n // 2


def test_sine_disables_fold_combo(make_window):
    win = make_window()
    win.calib.set_drive_form("sine")
    assert not win.calib.fold_combo.isEnabled()
    win.calib.set_drive_form("triangular")
    assert win.calib.fold_combo.isEnabled()


def test_session_roundtrip_restores_fold_before_data(make_window):
    win = make_window()
    win._load_file(SPECTRUM)
    win.calib.set_fold_mode("two_branches", reverse=True)
    payload = win._session_payload()
    assert payload["model_state"]["fold_mode"] == "two_branches"
    win2 = make_window()
    win2._apply_session_payload(payload)
    assert win2.calib.fold_mode == "two_branches"
    assert win2.calib.reverse_velocity.isChecked()
    # Los datos se prepararon ya con el modo de la sesión, no doblados.
    assert win2.file.y_data.size == win2.file.counts.size


def test_old_session_without_fold_is_folded(make_window):
    win = make_window()
    win._load_file(SPECTRUM)
    payload = win._session_payload()
    payload["model_state"].pop("fold_mode", None)
    payload["model_state"].pop("reverse_velocity", None)
    win2 = make_window()
    win2.calib.set_fold_mode("single_sweep")
    win2._apply_session_payload(payload)
    assert win2.calib.fold_mode == "fold"
    assert win2.file.y_data.size == win2.file.counts.size // 2


def test_fit_state_carries_fold_mode(make_window):
    win = make_window()
    win._load_file(SPECTRUM)
    win.calib.set_fold_mode("two_branches", reverse=True)
    st = win._build_state()
    assert st.fold_mode == "two_branches" and st.reverse_velocity
    assert st.velocity.size == st.y_data.size == win.file.counts.size


# ── Carga por contenido (lector genérico) ────────────────────────────────────

import numpy as np  # noqa: E402

from core.folding import single_sweep_velocity_axis  # noqa: E402


def _doublet_t(v):
    g = 0.15 ** 2
    return 1.0 - 0.08 * (g / ((v - 0.9) ** 2 + g) + g / ((v + 0.1) ** 2 + g))


def test_channel_counts_csv_is_folded(make_window, tmp_path):
    counts = np.loadtxt(SPECTRUM)
    p = tmp_path / "equipo.csv"
    p.write_text("Channel,Counts\n" + "\n".join(f"{i},{c:.0f}" for i, c in enumerate(counts)))
    win = make_window()
    win._load_file(p)
    assert win.file.counts is not None
    assert win.file.y_data.size == counts.size // 2


def test_counts_with_header_footer_and_unknown_extension(make_window, tmp_path):
    counts = np.loadtxt(SPECTRUM)
    p = tmp_path / "medida.spe"
    p.write_text("$SPEC_ID:\nalpha-Fe\n$DATA:\n0 511\n"
                 + "\n".join(f"{c:.0f}" for c in counts) + "\n$ROI:\n0\n")
    win = make_window()
    win._load_file(p)
    np.testing.assert_array_equal(win.file.counts, counts)


def test_absorbance_velocity_file_is_fitted_with_gaussian_weights(make_window, tmp_path):
    v = single_sweep_velocity_axis(256, 4.0)
    a = 100 * (1 - _doublet_t(v)) + np.random.default_rng(5).normal(0, 0.05, v.size)
    p = tmp_path / "abs.txt"
    p.write_text("v(mm/s)\tAbs(%)\n" + "\n".join(f"{x:.4f}\t{y:.4f}" for x, y in zip(v, a)))
    win = make_window()
    win._load_file(p)
    assert win.file.counts is None and win.file.y_kind == "absorption_percent"
    assert abs(np.percentile(win.file.y_data, 90) - 1.0) < 0.01
    st = win._build_state()
    assert st.likelihood == "gauss" and st.norm_factor is None
    assert st.fold_mode == "single_sweep" and not st.fit_center
    np.testing.assert_allclose(st.sigma_data, 5e-4, rtol=0.25)


def test_velocity_counts_file_uses_poisson_sigma(make_window):
    win = make_window()
    win._load_file(DATA / "public/alphaFe_calibracion_ESRF.dat")
    assert win.file.counts is None and win.file.y_kind == "counts"
    raw = win.file.folded
    np.testing.assert_allclose(win.file.sigma, np.sqrt(raw) / win.file.norm_factor)
    assert np.all(np.diff(win.file.velocity) >= 0)


# ── Ventana de importación ───────────────────────────────────────────────────

def _spe_with_footer(tmp_path: Path) -> Path:
    from core.folding import read_ws5_counts
    c = read_ws5_counts(SPECTRUM)
    p = tmp_path / "raro.xyz"
    p.write_text("Sample: alpha-Fe\nDate: 2025-03-14\n"
                 + "\n".join(f"{x:.0f}" for x in c) + "\nTotal 1 2 3\n")
    return p


def test_import_dialog_detects_and_previews(qapp, tmp_path):
    from core.instruments import InstrumentLibrary
    from core.spectrum_import import ImportHints
    from gui.import_dialog import ImportDialog
    dlg = ImportDialog(None, _spe_with_footer(tmp_path), library=InstrumentLibrary(tmp_path / "lib"))
    r = dlg.result
    assert r is not None and r.x_kind == "channel" and r.data_start == 2
    assert dlg.start_spin.value() == 3 and not dlg.start_spin.isEnabled()
    v, y = dlg.preview_data()
    assert v.size == y.size == r.y.size // 2
    dlg.fold_combo.setCurrentIndex(dlg.fold_combo.findData("two_branches"))
    assert dlg.preview_data()[0].size == r.y.size
    assert dlg.hints() == ImportHints()             # nada fijado a mano
    dlg.deleteLater()


def test_import_dialog_manual_range_and_instrument(qapp, tmp_path, monkeypatch):
    from core.instruments import InstrumentLibrary
    from gui.import_dialog import ImportDialog
    lib = InstrumentLibrary(tmp_path / "lib")
    dlg = ImportDialog(None, _spe_with_footer(tmp_path), library=lib)
    dlg.range_auto.setChecked(False)
    dlg.end_spin.setValue(dlg.end_spin.value() - 2)       # quita dos canales
    assert dlg.result.y.size == 510
    dlg.reverse_check.setChecked(True)
    monkeypatch.setattr(mq.QtWidgets.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Lab B", True)))
    dlg._on_save_instrument()
    prof = lib.get("Lab B")
    assert prof.import_hints.data_start == 2 and prof.import_hints.data_end == 512
    assert prof.reverse_velocity is True
    assert dlg.instrument_name() == "Lab B"
    dlg.deleteLater()
    # Un diálogo nuevo con el equipo lo aplica.
    dlg2 = ImportDialog(None, _spe_with_footer(tmp_path), library=lib, instrument="Lab B")
    assert not dlg2.range_auto.isChecked() and dlg2.result.y.size == 510
    assert dlg2.reverse()
    dlg2.deleteLater()


def test_import_loads_and_session_keeps_hints(make_window, tmp_path, monkeypatch):
    from core.spectrum_import import ImportHints
    from gui import import_dialog
    path = _spe_with_footer(tmp_path)
    hints = ImportHints(data_start=2, data_end=512)

    class FakeDialog:
        def __init__(self, *a, **k): pass
        def exec(self): return mq.QtWidgets.QDialog.DialogCode.Accepted
        def hints(self): return hints
        def drive_form(self): return "triangular"
        def fold_mode(self): return "two_branches"
        def reverse(self): return False
        def instrument_name(self): return "Lab B"
        def calibration_id(self): return None

    monkeypatch.setattr(import_dialog, "ImportDialog", FakeDialog)
    win = make_window()
    win.on_import(path)
    assert win.file.counts.size == 510 and win.calib.fold_mode == "two_branches"
    assert win.file.instrument == "Lab B"
    payload = win._session_payload()
    assert payload["import_hints"]["data_end"] == 512 and payload["instrument"] == "Lab B"
    # Al recargar la sesión se vuelve a leer con las mismas correcciones.
    win2 = make_window()
    win2._apply_session_payload(payload)
    assert win2.file.counts.size == 510 and win2.file.instrument == "Lab B"


# ── Calibración del equipo por fecha ────────────────────────────────────────

def _dated_copy(tmp_path: Path, name: str, date: str) -> Path:
    from core.folding import read_ws5_counts
    p = tmp_path / name
    p.write_text(f"Date: {date}\n" + "\n".join(f"{x:.0f}" for x in read_ws5_counts(SPECTRUM)))
    return p


def _lab(tmp_path):
    import datetime as dt
    from core.instruments import CalibrationRecord, InstrumentLibrary, InstrumentProfile
    lib = InstrumentLibrary(tmp_path / "lib")
    lib.save(InstrumentProfile(name="Lab B"))
    lib.add_calibration("Lab B", CalibrationRecord(date=dt.date(2025, 1, 10), vmax=10.5,
                                                   sample="aFe enero"))
    lib.add_calibration("Lab B", CalibrationRecord(date=dt.date(2025, 6, 1), vmax=11.0,
                                                   sextet_pattern="legacy"))
    return lib


def test_load_with_instrument_assigns_calibration_by_date(make_window, tmp_path):
    from core.constants import convert_vmax
    win = make_window()
    win._instruments = _lab(tmp_path)
    win._load_file(_dated_copy(tmp_path, "a.dat", "2025-03-14"), None, "Lab B")
    info = win.calibration_info
    assert info["source"] == "instrument" and info["calibration_date"] == "2025-01-10"
    assert info["measurement_date"] == "2025-03-14"
    assert win.calib.vmax.value() == pytest.approx(10.5)
    assert "2025-01-10" in win.calib_label.text()
    # Otra fecha → otra calibración (hecha con el patrón histórico: se convierte).
    win._load_file(_dated_copy(tmp_path, "b.dat", "2025-07-02"), None, "Lab B")
    assert win.calib.vmax.value() == pytest.approx(
        convert_vmax(11.0, "legacy", win.sextet_pattern), abs=1e-4)   # control a 4 decimales
    # Anterior a toda calibración: se mantiene la vigente.
    win._load_file(_dated_copy(tmp_path, "c.dat", "2024-12-31"), None, "Lab B")
    assert win.calibration_info["calibration_date"] == "2025-06-01"


def test_series_vmax_per_file(make_window, tmp_path):
    win = make_window()
    win._instruments = _lab(tmp_path)
    win._load_file(_dated_copy(tmp_path, "a.dat", "2025-03-14"), None, "Lab B")
    p = _dated_copy(tmp_path, "b.dat", "2025-02-01")
    vmax, cal, prep = win._prepare_series_file(p)
    assert vmax == pytest.approx(10.5) and cal["date"] == "2025-01-10"
    assert abs(prep.velocity).max() == pytest.approx(10.5, rel=0.02)


def test_import_dialog_shows_assigned_calibration(qapp, tmp_path):
    from gui.import_dialog import ImportDialog
    dlg = ImportDialog(None, _dated_copy(tmp_path, "a.dat", "2025-03-14"),
                       library=_lab(tmp_path), vmax=12.0, instrument="Lab B")
    choice = dlg.assigned_calibration()
    assert choice.record.vmax == 10.5 and choice.origin == "header" and choice.rule == "date"
    assert dlg.preview_vmax() == pytest.approx(10.5)
    assert "2025-01-10" in dlg.summary.text()
    dlg.deleteLater()


def test_latest_rule_ignores_dates(make_window, tmp_path):
    from gui.import_dialog import ImportDialog
    lib = _lab(tmp_path)
    prof = lib.get("Lab B"); prof.calibration_rule = "latest"; lib.save(prof)
    win = make_window()
    win._instruments = lib
    # Medida anterior a todas las calibraciones: por fecha no habría ninguna.
    win._load_file(_dated_copy(tmp_path, "a.dat", "2020-01-01"), None, "Lab B")
    info = win.calibration_info
    assert info["calibration_date"] == "2025-06-01" and info["calibration_rule"] == "latest"
    assert "2025-06-01" in win.calib_label.text()
    dlg = ImportDialog(None, _dated_copy(tmp_path, "b.dat", "2020-01-01"),
                       library=lib, vmax=12.0, instrument="Lab B")
    assert dlg.assigned_calibration().record.date.isoformat() == "2025-06-01"
    assert "2025-06-01" in dlg.summary.text()
    dlg.deleteLater()


def test_instrument_manager_rule_combo(qapp, tmp_path):
    from gui.instrument_manager import InstrumentManagerDialog
    lib = _lab(tmp_path)
    dlg = InstrumentManagerDialog(None, lib, "Lab B")
    assert dlg.rule_combo.currentData() == "date"
    dlg.rule_combo.setCurrentIndex(dlg.rule_combo.findData("latest"))
    assert lib.get("Lab B").calibration_rule == "latest"
    dlg.deleteLater()


def test_import_dialog_manual_calibration(make_window, tmp_path, monkeypatch):
    from gui.import_dialog import ImportDialog
    lib = _lab(tmp_path)
    path = _dated_copy(tmp_path, "a.dat", "2025-03-14")
    dlg = ImportDialog(None, path, library=lib, vmax=12.0, instrument="Lab B")
    combo = dlg.calibration_combo
    assert combo.isEnabled() and combo.count() == 3 and dlg.calibration_id() is None
    june = next(r for r in lib.calibrations("Lab B") if r.date.isoformat() == "2025-06-01")
    combo.setCurrentIndex(combo.findData(june.id))
    ch = dlg.assigned_calibration()
    assert ch.rule == "manual" and ch.record.id == june.id
    assert "2025-06-01" in dlg.summary.text()
    # Al cambiar a «sin equipo» no queda una calibración elegida.
    dlg.instrument_combo.setCurrentIndex(0)
    assert dlg.calibration_id() is None and not combo.isEnabled()
    dlg.deleteLater()
    # La ventana carga con la calibración elegida.
    win = make_window()
    win._instruments = lib
    win._load_file(path, None, "Lab B", calibration_id=june.id)
    assert win.calibration_info["calibration_id"] == june.id
    assert win.calibration_info["calibration_rule"] == "manual"
    assert "elegida a mano" in win.calib_label.text() or "manually" in win.calib_label.text()


def test_manager_applies_calibration_to_current_spectrum(make_window, tmp_path, monkeypatch):
    from core.constants import convert_vmax
    from gui.instrument_manager import InstrumentManagerDialog
    import gui.model_workflow as mw
    lib = _lab(tmp_path)
    win = make_window()
    win._instruments = lib
    win._load_file(_dated_copy(tmp_path, "a.dat", "2025-03-14"), None, "Lab B")
    assert win.calib.vmax.value() == pytest.approx(10.5)
    # Lo leído se guarda: aplicar o tomar la entrada no vuelve a leer el fichero.
    assert win.file.imported is not None

    def _no_read(*_a, **_k):
        raise AssertionError("no debería releer el espectro activo")
    monkeypatch.setattr(mw, "read_spectrum_file", _no_read)
    assert win._current_calibration_entry()["date"].isoformat() == "2025-03-14"
    dlg = InstrumentManagerDialog(win, lib, "Lab B", win._current_calibration_entry,
                                  apply_calibration=win._apply_instrument_calibration)
    assert dlg.btn_apply.isVisible() or not dlg.isVisible()
    assert not dlg.btn_apply.isEnabled()                 # nada seleccionado
    row = next(i for i in range(dlg.table.rowCount())
               if dlg.table.item(i, 0).text() == "2025-06-01")
    dlg.table.selectRow(row)
    assert dlg.btn_apply.isEnabled()
    dlg.btn_apply.click()
    assert win.calibration_info["calibration_date"] == "2025-06-01"
    assert win.calibration_info["calibration_rule"] == "manual"
    assert win.calib.vmax.value() == pytest.approx(
        convert_vmax(11.0, "legacy", win.sextet_pattern), abs=1e-4)
    dlg.deleteLater()
    # Sin la función de aplicar (p. ej. desde Importar…) no hay botón.
    dlg2 = InstrumentManagerDialog(None, lib, "Lab B")
    assert dlg2.btn_apply.isHidden()
    dlg2.deleteLater()


def test_manager_opens_calibration_spectrum(make_window, tmp_path):
    import datetime as dt
    from core.instruments import CalibrationRecord
    from gui.instrument_manager import InstrumentManagerDialog
    lib = _lab(tmp_path)
    prof = lib.get("Lab B"); prof.fold_mode = "two_branches"; lib.save(prof)
    src = _dated_copy(tmp_path, "afe.dat", "2025-09-09")
    rec = lib.add_calibration("Lab B", CalibrationRecord(date=dt.date(2025, 9, 9), vmax=10.8,
                                                         sample="afe"), src)
    win = make_window()
    win._instruments = lib
    dlg = InstrumentManagerDialog(win, lib, "Lab B", win._current_calibration_entry,
                                  open_calibration=win._open_calibration_spectrum)
    rows = {dlg.table.item(i, 0).text(): i for i in range(dlg.table.rowCount())}
    dlg.table.selectRow(rows["2025-01-10"])              # sin copia del espectro
    assert not dlg.btn_open.isEnabled()
    dlg.table.selectRow(rows["2025-09-09"])
    assert dlg.btn_open.isEnabled()
    dlg.btn_open.click()
    assert win.file.path == lib.calibration_file("Lab B", rec)
    assert win.file.instrument == "Lab B" and win.calib.fold_mode == "two_branches"
    assert win.calibration_info["calibration_id"] == rec.id
    assert win.calib.vmax.value() == pytest.approx(10.8)
    dlg.deleteLater()
    assert InstrumentManagerDialog(None, lib, "Lab B").btn_open.isHidden()


def test_instrument_manager_add_and_remove(qapp, tmp_path, monkeypatch):
    import datetime as dt
    from gui.instrument_manager import CalibrationEntryDialog, InstrumentManagerDialog
    lib = _lab(tmp_path)
    src = _dated_copy(tmp_path, "afe.dat", "2025-09-09")
    cur = {"vmax": 10.8, "isomer_shift": -0.1, "sample": "afe", "path": str(src),
           "date": dt.date(2025, 9, 9), "sextet_pattern": "normos"}
    dlg = InstrumentManagerDialog(None, lib, "Lab B", lambda: cur)
    assert dlg.table.rowCount() == 2 and dlg.btn_add_current.isEnabled()
    monkeypatch.setattr(CalibrationEntryDialog, "exec",
                        lambda self: mq.QtWidgets.QDialog.DialogCode.Accepted)
    dlg._on_add_current()
    recs = lib.calibrations("Lab B")
    assert recs[-1].date == dt.date(2025, 9, 9) and recs[-1].vmax == pytest.approx(10.8)
    assert lib.calibration_file("Lab B", recs[-1]) is not None
    dlg.table.selectRow(2)
    monkeypatch.setattr(mq.QtWidgets.QMessageBox, "question",
                        staticmethod(lambda *a, **k: mq.QtWidgets.QMessageBox.StandardButton.Yes))
    dlg._on_remove()
    assert len(lib.calibrations("Lab B")) == 2 and dlg.table.rowCount() == 2
    dlg.date_order_combo.setCurrentIndex(dlg.date_order_combo.findData("mdy"))
    assert lib.get("Lab B").date_order == "mdy"
    dlg.deleteLater()


def test_global_relaxation_uses_calibration_per_date(make_window, tmp_path, monkeypatch):
    """Ajuste global Néel: cada fichero con el eje de la calibración de su fecha."""
    import numpy as np
    import core.relaxation as relax
    from gui.dialogs import GlobalNeelFitDialog
    captured = {}

    def fake_fit(spectra, **kw):
        captured["spectra"] = spectra
        return relax.GlobalRelaxationFitResult(
            shared={"bhf": 33.0}, local=[{"depth": 0.1} for _ in spectra],
            residuals=np.zeros(1), cost=1.0, success=True, message="ok", free_keys=["bhf"])

    monkeypatch.setattr(relax, "fit_neel_size_global", fake_fit)
    win = make_window()
    win._instruments = _lab(tmp_path)
    win._load_file(_dated_copy(tmp_path, "a.dat", "2025-03-14"), None, "Lab B")
    dlg = GlobalNeelFitDialog(win)
    for name, date, t in (("t1.dat", "2025-02-01", 10.0), ("t2.dat", "2025-07-01", 50.0),
                          ("t0.dat", "2024-01-01", 80.0)):
        dlg.entries.append({"path": _dated_copy(tmp_path, name, date), "temp_k": t,
                            "status": "pending"})
    dlg._refresh_table()
    win.calib.vmax.set_value(9.0)                  # Vmax del panel, para t0
    dlg._run()
    vmaxes = [abs(s.velocity).max() for s in captured["spectra"]]
    assert vmaxes[0] == pytest.approx(10.5, rel=0.02)
    assert vmaxes[1] == pytest.approx(10.9959, rel=0.02)
    assert vmaxes[2] == pytest.approx(9.0, rel=0.02)
    text = dlg.results_text.toPlainText()
    assert "2025-01-10" in text and "2024-01-01" in text
    dlg.deleteLater()


# ── Reconocimiento automático del equipo ──────────────────────────────────────

def _recognizing_lab(tmp_path):
    lib = _lab(tmp_path)
    profile = lib.get("Lab B")
    profile.match_text = ["Lab B"]
    profile.fold_mode = "two_branches"
    lib.save(profile)
    return lib


def _lab_b_file(tmp_path: Path, name: str, date: str) -> Path:
    p = _dated_copy(tmp_path, name, date)
    p.write_text("Instrument: Lab B\n" + p.read_text())
    return p


def test_open_recognizes_instrument(make_window, tmp_path):
    win = make_window()
    win._instruments = _recognizing_lab(tmp_path)
    win._open_spectrum(_lab_b_file(tmp_path, "a.dat", "2025-03-14"))
    assert win.file.instrument == "Lab B"
    assert win.calibration_info["calibration_date"] == "2025-01-10"
    assert win.calib.to_view_state().fold_mode == "two_branches"
    assert "Lab B" in win.statusBar().currentMessage()
    # Un fichero que no lo menciona se abre sin equipo.
    win._open_spectrum(_dated_copy(tmp_path, "otro.dat", "2025-03-14"))
    assert win.file.instrument is None


def test_open_with_two_candidates_uses_none(make_window, tmp_path):
    from core.instruments import InstrumentProfile
    win = make_window()
    lib = win._instruments = _recognizing_lab(tmp_path)
    lib.save(InstrumentProfile(name="Lab C", match_name=["*.dat"]))
    win._open_spectrum(_lab_b_file(tmp_path, "a.dat", "2025-03-14"))
    assert win.file.instrument is None
    assert "Lab C" in win.statusBar().currentMessage()


def test_import_dialog_preselects_recognized_instrument(qapp, tmp_path):
    from gui.import_dialog import ImportDialog
    dlg = ImportDialog(None, _lab_b_file(tmp_path, "a.dat", "2025-03-14"),
                       library=_recognizing_lab(tmp_path), vmax=12.0, instrument=None)
    assert dlg.instrument_name() == "Lab B" and dlg.fold_mode() == "two_branches"
    assert "Lab B" in dlg.summary.text() and "2025-01-10" in dlg.summary.text()
    dlg.deleteLater()


def test_instrument_manager_edits_recognition(qapp, tmp_path):
    from gui.instrument_manager import InstrumentManagerDialog
    lib = _lab(tmp_path)
    dlg = InstrumentManagerDialog(None, lib, "Lab B")
    assert dlg.match_text_edit.text() == "" and dlg.match_text_edit.isEnabled()
    dlg.match_text_edit.setText("Lab B; Spectro 2")
    dlg.match_name_edit.setText("*.ws5")
    dlg._on_match_changed()
    back = lib.get("Lab B")
    assert back.match_text == ["Lab B", "Spectro 2"] and back.match_name == ["*.ws5"]
    assert lib.calibrations("Lab B")            # el perfil se reescribe, las calibraciones siguen
    dlg.deleteLater()


def test_comparison_column_and_alpha_fe_shift(make_window, tmp_path, monkeypatch):
    from tests.test_spectrum_import import _winnormos_like
    text, fit = _winnormos_like()
    path = tmp_path / "winnormos.txt"
    path.write_text(text)
    win = make_window()
    win._load_file(SPECTRUM)
    win.calibration_info = {"source": "local", "velocity_calibrated": 12.0,
                            "isomer_shift": -0.115, "sextet_pattern": "normos"}
    # Sin preguntar: columna de datos y eje desplazado, deducido del centro.
    assert win._add_comparison(path, ask=False)
    c = win.comparison_spectra[-1]
    assert abs(0.5 * (c.velocity.min() + c.velocity.max())) < 1e-6
    # Ajuste total (3.ª columna) y eje tal cual.
    win._add_comparison(path, column=2, shift_alpha_fe=False, ask=False)
    c = win.comparison_spectra[-1]
    assert c.velocity.min() == pytest.approx(-6 + 0.115) and "[3]" in c.label
    assert np.allclose(c.y_data * np.percentile(fit, 90), fit, atol=1e-4)
    # El diálogo propone la detección y deja elegir.
    from gui.file_actions import ComparisonOptionsDialog
    from core.spectrum_import import intensity_column_choices, read_spectrum_file
    imp = read_spectrum_file(path)
    dlg = ComparisonOptionsDialog(win, path, imp, intensity_column_choices(imp), 1, -0.115, True)
    assert dlg.column_combo.count() == 3 and dlg.column() == 1 and dlg.shift_alpha_fe()
    dlg.deleteLater()


def test_window_axis_matches_headless_with_adaptive_trim(make_window):
    """Con recorte adaptativo de bordes (calibration.adt pierde un canal por
    lado) la ventana usa el mismo eje que la sesión sin GUI: recortado, no
    estirado a ±Vmax sobre menos puntos."""
    import numpy as np
    from core.session import HeadlessSession
    path = DATA / "calibration.adt"
    win = make_window()
    win._load_file(path)
    vmax = win.calib.vmax.value()
    s = HeadlessSession()
    s.load_ws5(path, vmax=vmax)
    assert win.file.y_data.size < win.file.counts.size // 2     # hubo recorte
    assert win.file.center == pytest.approx(s.spectrum.center)
    np.testing.assert_allclose(win.file.velocity, s._velocity(), rtol=0, atol=1e-12)
    assert abs(win.file.velocity[0]) < vmax
