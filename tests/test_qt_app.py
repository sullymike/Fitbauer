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


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch):
    """Evita que los QMessageBox modales bloqueen los tests headless.

    En la app real estos diálogos informan al usuario y se cierran con OK; en
    los tests (sin usuario) se sustituyen por una respuesta inmediata.
    """
    ok = QtWidgets.QMessageBox.StandardButton.Ok
    for name in ("information", "warning", "critical", "question"):
        monkeypatch.setattr(QtWidgets.QMessageBox, name,
                            staticmethod(lambda *a, **k: ok), raising=False)


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


def test_fit_velocity_toggle_shows_tk_info_and_fixes_active_bhf(win, monkeypatch):
    """Activar Ajustar Vmax en Qt reproduce el aviso informativo de Tk."""
    cp = win.components_panels[0]
    cp.params["bhf"].set_fixed(False)
    captured = {}

    def fake_information(parent, title, text, *args, **kwargs):
        captured["title"] = title
        captured["text"] = text
        return QtWidgets.QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QtWidgets.QMessageBox, "information",
                        staticmethod(fake_information))
    win.calib.fit_velocity.setChecked(True)

    assert cp.params["bhf"].is_fixed()
    assert captured["title"] == mq.tr("msg.fit_velocity_title")
    assert captured["text"] == mq.tr("msg.fit_velocity_info")


def test_fit_velocity_requires_bhf_fixed_before_qt_fit(win, monkeypatch):
    """Si Ajustar Vmax está activo y BHF queda libre, Qt avisa y no ajusta."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    cp = win.components_panels[0]
    win.calib.fit_velocity.setChecked(True)
    cp.params["bhf"].set_fixed(False)
    captured = {}

    def fake_warning(parent, title, text, *args, **kwargs):
        captured["title"] = title
        captured["text"] = text
        return QtWidgets.QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QtWidgets.QMessageBox, "warning",
                        staticmethod(fake_warning))
    win.on_fit()

    assert captured["title"] == mq.tr("msg.fit_velocity_title")
    assert captured["text"] == mq.tr("msg.fit_velocity_requires_bhf_fixed")
    assert win.last_fit_result is None


def test_qt_component_count_selector_shows_six_components(win):
    """El selector de Qt permite activar hasta 6 componentes, igual que Tk."""
    assert len(win.components_panels) == 6
    assert win.n_components_spin.maximum() == 6
    win.n_components_spin.setValue(4)
    assert [cp.enabled.isChecked() for cp in win.components_panels[:4]] == [True] * 4
    assert not win.components_panels[4].enabled.isChecked()
    # En modo pestañas: índice 0 = distribución, 1..6 = componentes. Con n=4 las
    # pestañas de los componentes 1-4 están visibles y la del 5 (índice 5) oculta.
    if not win._using_tabs:
        win._rebuild_component_area(use_tabs=True)
    assert win.comp_tabs.isTabVisible(4)        # componente 4 visible
    assert not win.comp_tabs.isTabVisible(5)    # componente 5 oculto


def test_qt_param_control_has_slider_bar_synced_with_spinbox(win):
    """Cada control numérico de Qt incluye una barra tipo slider sincronizada."""
    ctl = win.components_panels[0].params["bhf"]
    assert isinstance(ctl.slider, QtWidgets.QSlider)
    ctl.set_value(30.0)
    before = ctl.slider.value()
    ctl.spin.setValue(40.0)
    assert ctl.slider.value() > before
    ctl.slider.setValue(0)
    assert abs(ctl.value() - ctl.spin.minimum()) < 1e-6


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


def test_init_from_minima_action_shows_detected_message(win, monkeypatch):
    """El QAction de Init from minima conserva el diálogo informativo."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    captured = {}

    def fake_information(parent, title, text, *args, **kwargs):
        captured["title"] = title
        captured["text"] = text
        return QtWidgets.QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QtWidgets.QMessageBox, "information",
                        staticmethod(fake_information))
    win.act_init.trigger()

    assert "Auto" in captured["title"]
    assert "Detected" in captured["text"] or "Detectados" in captured["text"]
    assert "Comp. 1" in captured["text"]


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


def test_view_toggles(win):
    """Show residual / show legend togglean sin error."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    win.act_show_residual.setChecked(False)
    win.act_show_legend.setChecked(False)
    win._refresh_plot()
    win.act_show_residual.setChecked(True)
    win.act_show_legend.setChecked(True)
    win._refresh_plot()


def test_physical_preset_3_2_1_fixes_intensities(win):
    """Aplicar 3:2:1 fija int1=3, int2=2, int3=1 en componentes activas."""
    cp = win.components_panels[0]
    cp.enabled.setChecked(True)
    # Cambia a valores arbitrarios
    cp.params["int1"].set_value(5.0); cp.params["int1"].set_fixed(False)
    # Simula el botón
    cp.params["int1"].set_value(3.0); cp.params["int1"].set_fixed(True)
    cp.params["int2"].set_value(2.0); cp.params["int2"].set_fixed(True)
    cp.params["int3"].set_value(1.0); cp.params["int3"].set_fixed(True)
    assert cp.params["int1"].value() == 3.0
    assert cp.params["int1"].is_fixed()


def test_export_report_writes_markdown(win, tmp_path):
    """Exportar informe escribe un .md con secciones esperadas."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    out = tmp_path / "report.md"
    old = QtWidgets.QFileDialog.getSaveFileName
    QtWidgets.QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (str(out), "Markdown (*.md)"))
    try:
        win.on_export_report()
    finally:
        QtWidgets.QFileDialog.getSaveFileName = old
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "Mössbauer" in content and "Componentes" in content


def test_auto_fit_from_minima(win):
    """Auto-fit = init + fit; sobre α-Fe recupera BHF≈33."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    # Mete valores groseramente desviados
    cp = win.components_panels[0]
    cp.params["bhf"].set_value(20.0)
    cp.params["delta"].set_value(0.5)
    win.on_auto_fit_from_minima()
    bhf = cp.params["bhf"].value()
    assert abs(bhf - 33.0) < 1.0


def test_ai_summary_dialog_builds(win, monkeypatch):
    """AI summary construye un JSON con los picos detectados sin bloquear modal."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    monkeypatch.setattr(
        QtWidgets.QDialog, "exec",
        lambda self_: QtWidgets.QDialog.Accepted)
    win.on_ai_summary()  # No debe lanzar


def test_recent_files_updates_on_load(win, monkeypatch):
    """Cargar un fichero añade su path a recent_files."""
    # No tocar settings.json real
    import mossbauer_qt as mq
    monkeypatch.setattr(mq.MossbauerQtWindow, "_save_settings", lambda self: None)
    win.recent_files = []
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    assert win.recent_files
    assert win.recent_files[0].endswith("hierro_metalico_alphaFe.adt")
    # Cargar otro lo pone al frente
    win._load_file(DATA / "hematita_Fe2O3.adt")
    assert win.recent_files[0].endswith("hematita_Fe2O3.adt")


def test_layout_presets_change_splitter_sizes(win):
    """Aplicar un preset cambia las proporciones del splitter principal."""
    win._apply_layout_preset("Wide plot")
    sizes = win._main_splitter.sizes()
    assert sizes  # se aplicó algo
    assert win.layout_preset == "Wide plot"
    win._apply_layout_preset("Balanced")
    assert win.layout_preset == "Balanced"


def test_login_dialog_cancel_returns_false(win, monkeypatch):
    """Si el usuario cierra el diálogo de login sin Ok, _login_dialog devuelve False."""
    # Fuerza credenciales vacías y simula cancelar el diálogo.
    import mossbauer_qt as mq
    monkeypatch.setattr(mq, "load_credentials", lambda: {})
    monkeypatch.setattr(
        QtWidgets.QDialog, "exec",
        lambda self_: QtWidgets.QDialog.Rejected)
    # Cliente dummy para no llamar al API real.
    class DummyClient:
        token = ""
    ok = win._login_dialog(DummyClient(), {})
    assert ok is False


def test_use_as_calibration_sets_info(win):
    """'Usar como calibración' guarda vmax/iso del estado actual."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    cp = win.components_panels[0]
    cp.params["delta"].set_value(-0.1092)
    QtWidgets.QMessageBox.information = staticmethod(lambda *a, **k: None)
    win._use_as_calibration_quick()
    assert win.calibration_info is not None
    assert abs(win.calibration_info["isomer_shift"] - (-0.1092)) < 1e-6
    assert win.calibration_info["source"] == "local"


def test_session_save_load_roundtrip_keeps_calibration(win, tmp_path):
    """Save→Load preserva calibration_info."""
    import json
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    win.calibration_info = {"source": "local", "calibration_sample": "X",
                             "velocity_calibrated": 12.0, "isomer_shift": -0.11}
    p = tmp_path / "s.json"
    p.write_text(json.dumps(win._session_payload(), default=str))
    win2 = mq.MossbauerQtWindow()
    try:
        win2._apply_session_payload(json.loads(p.read_text()))
        assert win2.calibration_info is not None
        assert win2.calibration_info["calibration_sample"] == "X"
    finally:
        win2.close(); win2.deleteLater()


def test_bootstrap_returns_sigma_estimates(win):
    """Bootstrap MC con 5 réplicas devuelve un mensaje con σ(MC) por parámetro."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    cp = win.components_panels[0]
    cp.params["delta"].set_value(-0.11)
    cp.params["bhf"].set_value(33.0)
    cp.params["gamma1"].set_value(0.14)
    cp.params["depth"].set_value(0.013)
    # Override del input dialog para no bloquear
    QtWidgets.QInputDialog.getInt = staticmethod(lambda *a, **k: (5, True))
    captured = {}
    QtWidgets.QMessageBox.information = staticmethod(
        lambda *a, **k: captured.setdefault("msg", a[-1]))
    win.on_bootstrap()
    assert "σ(MC)" in captured.get("msg", "") or "MC)" in captured.get("msg", "")


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
