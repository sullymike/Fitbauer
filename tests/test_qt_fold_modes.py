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
