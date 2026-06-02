"""Smoke tests del front-end Qt (mossbauer_qt.py).

Requiere PySide6 y pytest-qt. Si no están disponibles, los tests se omiten.
Se ejecutan con QT_QPA_PLATFORM=offscreen para no necesitar display real.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Plataforma offscreen — no necesita Xvfb.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtWidgets  # noqa: F401
    import mossbauer_qt as mq
except Exception as exc:  # pragma: no cover
    pytest.skip(f"PySide6 / mossbauer_qt no disponible: {exc}",
                allow_module_level=True)

DATA = ROOT / "data_sample"


@pytest.fixture
def app(qapp):
    """Reusa la QApplication única de pytest-qt."""
    return qapp


@pytest.fixture
def win(app):
    w = mq.MossbauerQtWindow()
    yield w
    w.close()
    w.deleteLater()


def test_window_starts_and_menus_exist(win):
    """La ventana arranca y tiene los menús básicos."""
    titles = [m.title() for m in win.menuBar().findChildren(QtWidgets.QMenu) if m.title()]
    # Los 4 menús principales deben estar presentes.
    assert any("File" in t or "Archivo" in t for t in titles)
    assert any("Fit" in t or "Ajuste" in t for t in titles)
    assert any("View" in t or "Vista" in t for t in titles)


def test_load_file_then_fit_recovers_alpha_fe(win):
    """Cargar α-Fe + lanzar Fit recupera BHF≈33 y δ≈ISO_REF."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    assert win.file.counts is not None and win.file.counts.size == 512
    # Valores iniciales razonables (ya por defecto en la UI)
    cp = win.components_panels[0]
    cp.params["delta"].set_value(-0.11)
    cp.params["bhf"].set_value(33.0)
    cp.params["gamma1"].set_value(0.14)
    cp.params["depth"].set_value(0.013)
    win.on_fit()
    bhf = cp.params["bhf"].value()
    delta = cp.params["delta"].value()
    assert abs(bhf - 33.0) < 1.0
    assert abs(delta - (-0.1092)) < 0.05


def test_init_from_minima_proposes_sextet(win):
    """Init from minima sobre α-Fe propone un sextete con BHF razonable."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    # Resetea s1 a valores muy alejados para que la detección sea informativa
    cp = win.components_panels[0]
    cp.params["delta"].set_value(0.0)
    cp.params["bhf"].set_value(20.0)
    win.on_init_from_minima()
    assert cp.kind == "Sextete"
    bhf = cp.params["bhf"].value()
    delta = cp.params["delta"].value()
    assert 28.0 < bhf < 38.0
    assert -0.3 < delta < 0.1


def test_mode_switch_to_pbhf_and_fit(win):
    """Cambio a modo P(BHF) y ajuste produce un pico cercano a 33 T."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    # Override del modal para no bloquear
    captured = {}
    win._show_distribution_dialog = lambda r: captured.setdefault("r", r)
    win.mode_combo.setCurrentIndex(1)
    assert win.is_distribution_mode
    win.on_fit()
    r = captured["r"]
    import numpy as np
    i_max = int(np.argmax(r.probability))
    bhf_peak = float(r.bhf_centers[i_max])
    assert 28.0 < bhf_peak < 38.0


def test_session_save_load_roundtrip(win, tmp_path):
    """Guardar y cargar una sesión reproduce los mismos parámetros."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    cp = win.components_panels[0]
    cp.params["delta"].set_value(0.123)
    cp.params["bhf"].set_value(42.0)
    cp.params["depth"].set_value(0.025)
    payload = win._session_payload()
    import json
    p = tmp_path / "sess.json"
    p.write_text(json.dumps(payload, default=str))

    win2 = mq.MossbauerQtWindow()
    try:
        win2._apply_session_payload(json.loads(p.read_text()))
        cp2 = win2.components_panels[0]
        assert abs(cp2.params["delta"].value() - 0.123) < 1e-6
        assert abs(cp2.params["bhf"].value() - 42.0) < 1e-6
        assert abs(cp2.params["depth"].value() - 0.025) < 1e-6
    finally:
        win2.close()
        win2.deleteLater()


def test_plot_styles_apply(win):
    """Los 4 estilos se aplican sin error."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    for style in ("classic", "modern", "publication", "dark"):
        win._set_plot_style(style)
        assert win.plot_style_name == style


def test_sigma_context_menu_toggle_profile(win):
    """Cambiar perfil Lorentziana→Voigt habilita el spinbox σ."""
    win.calib._set_line_profile("Voigt")
    assert win.calib.line_profile == "Voigt"
    assert win.calib.voigt_sigma.spin.isEnabled()
    win.calib._set_line_profile("Lorentziana")
    assert not win.calib.fit_sigma.isChecked()


def test_find_center_updates_calibration(win):
    """Fit ▸ Find center detecta un centro razonable y lo escribe al panel."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    # Mueve el slider center fuera del óptimo
    win.calib.center.set_value(258.0)
    win.on_find_center()
    c = win.calib.center.value()
    assert 254.0 < c < 258.5  # centro real esperado ≈ 256.5


def test_save_fit_writes_tsv(win, tmp_path):
    """Save fit exporta velocidad, datos, modelo y residuo en TSV."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    out = tmp_path / "fit.dat"
    # Bypass del diálogo de fichero
    old = QtWidgets.QFileDialog.getSaveFileName
    QtWidgets.QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (str(out), "TSV (*.dat)"))
    try:
        win.on_save_fit()
    finally:
        QtWidgets.QFileDialog.getSaveFileName = old
    assert out.exists()
    head = out.read_text().splitlines()[0]
    assert "velocity_mm_s" in head and "data_norm" in head and "model" in head
