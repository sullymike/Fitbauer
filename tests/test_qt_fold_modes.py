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
    vmax, cal = win._series_vmax(p, win._read_series_spectrum(p))
    assert vmax == pytest.approx(10.5) and cal["date"] == "2025-01-10"
    _c, _s, _y, _n, v = win._prepare_counts(win._read_channel_counts(p), vmax=vmax)
    assert abs(v).max() == pytest.approx(10.5, rel=0.02)


def test_import_dialog_shows_assigned_calibration(qapp, tmp_path):
    from gui.import_dialog import ImportDialog
    dlg = ImportDialog(None, _dated_copy(tmp_path, "a.dat", "2025-03-14"),
                       library=_lab(tmp_path), vmax=12.0, instrument="Lab B")
    rec, date, origin = dlg.assigned_calibration()
    assert rec.vmax == 10.5 and origin == "header"
    assert dlg.preview_vmax() == pytest.approx(10.5)
    assert "2025-01-10" in dlg.summary.text()
    dlg.deleteLater()


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
