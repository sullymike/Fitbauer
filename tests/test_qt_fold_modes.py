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
