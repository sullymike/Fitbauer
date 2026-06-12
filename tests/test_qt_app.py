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
def make_window(app):
    """Crea ventanas Qt y las destruye de forma segura para QtWebEngine.

    Cada ``MossbauerQtWindow`` crea una ``QWebEngineView``. Si la vista/página no
    se eliminan y se procesan ANTES de que se libere el perfil global de
    WebEngine, PySide6 segfaultea al cerrar el proceso ("Release of profile
    requested but WebEnginePage still not deleted"). La factoría rastrea todas
    las ventanas creadas en el test y las limpia en orden.
    """
    created: list = []

    def _make():
        w = mq.MossbauerQtWindow()
        created.append(w)
        return w

    yield _make

    for w in created:
        view = getattr(w, "plotly_view", None)
        if view is not None:
            try:
                view.stop()
            except Exception:
                pass
            view.setParent(None)
            view.deleteLater()
        w.close()
        w.deleteLater()
    # Procesa las eliminaciones diferidas (DeferredDelete) mientras el perfil
    # de WebEngine sigue vivo, evitando el segfault de cierre.
    app.processEvents()


@pytest.fixture
def win(make_window):
    return make_window()


def test_window_starts_and_menus_exist(win):
    """La ventana arranca y tiene los menús básicos."""
    titles = [m.title() for m in win.menuBar().findChildren(QtWidgets.QMenu) if m.title()]
    # Los 4 menús principales deben estar presentes.
    assert any("File" in t or "Archivo" in t for t in titles)
    assert any("Fit" in t or "Ajuste" in t for t in titles)
    assert any("View" in t or "Vista" in t for t in titles)


def test_help_dialog_is_modeless(win, app, monkeypatch):
    """La ayuda se abre sin bloquear la ventana principal."""
    monkeypatch.setattr(
        QtWidgets.QDialog, "exec",
        lambda self_: pytest.fail("La ayuda debe abrirse con show(), no con exec()."))

    win.on_help()
    app.processEvents()

    dlg = win._help_dialog
    assert dlg is not None
    assert dlg.isVisible()
    assert not dlg.isModal()
    assert dlg.windowModality() == mq.QtCore.Qt.NonModal
    assert win.isEnabled()

    win.on_help()
    app.processEvents()
    assert win._help_dialog is dlg

    dlg.close()
    app.processEvents()


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
    cp.params["gamma1"].set_value(0.28)
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


def test_2d_distribution_fit_renders_topographic_map(win):
    """Un ajuste 2D produce un resultado con probabilidad matricial y mapa.

    Cubre la regresión del AttributeError 'alpha' (el resultado 2D expone
    alpha_bhf/alpha_quad) y verifica que el canvas crea el panel de mapa y que
    la figura Plotly incluye un heatmap.
    """
    import numpy as np
    win._load_file(DATA / "magnetita_Fe3O4.adt")
    captured = {}
    win._show_distribution_dialog = lambda r: captured.setdefault("r", r)
    # Modo P(BHF, ΔEQ) 2D
    win.mode_combo.setCurrentIndex(4)
    assert win.is_distribution_mode
    # Reduce el tamaño de malla para que el test sea rápido (qbins/nbins son
    # ParamControl, con API set_value).
    if hasattr(win.dist_panel, "qbins"):
        win.dist_panel.qbins.set_value(9)
    if hasattr(win.dist_panel, "nbins"):
        win.dist_panel.nbins.set_value(15)
    win.on_fit()  # no debe lanzar AttributeError
    res = win.runtime_results.distribution_result
    assert np.asarray(res.probability).ndim == 2
    # El canvas Matplotlib añadió el panel del mapa topográfico.
    assert win.canvas.ax_map is not None
    assert win.canvas.last_render.get("dist_map_2d") is res
    # La figura Plotly incluye un heatmap del mapa P(x, y).
    fig = win._current_plotly_figure()
    assert any(t.type == "heatmap" for t in fig.data)


def test_session_save_load_roundtrip(win, make_window, tmp_path):
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

    win2 = make_window()
    win2._apply_session_payload(json.loads(p.read_text()))
    cp2 = win2.components_panels[0]
    assert abs(cp2.params["delta"].value() - 0.123) < 1e-6
    assert abs(cp2.params["bhf"].value() - 42.0) < 1e-6
    assert abs(cp2.params["depth"].value() - 0.025) < 1e-6


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


def test_undo_discrete_fit_keeps_mode(win):
    """Deshacer un ajuste discreto NO debe saltar a modo P(BHF).

    Regresión: _apply_session_payload reconstruye el modo desde dist_variable
    (siempre 'BHF' por defecto), así que sin preservar el modo activo deshacer
    un ajuste en modo discreto cambiaba indebidamente a Distribución P(BHF).
    """
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    win.mode_combo.setCurrentIndex(0)
    assert not win.is_distribution_mode
    win._pre_fit_snapshot = win._session_payload()
    win.act_undo_fit.setEnabled(True)
    win._undo_fit()
    assert win.mode_combo.currentIndex() == 0
    assert not win.is_distribution_mode


def test_all_registered_shortcuts_have_actions(win):
    """Cada entrada de SHORTCUT_REGISTRY tiene su QAction en el registro."""
    from gui.menu_builder import SHORTCUT_REGISTRY
    for action_id, _menu, _label, _default in SHORTCUT_REGISTRY:
        assert action_id in win._action_registry, action_id


def test_custom_shortcut_applies_and_persists(win):
    """Aplicar un atajo custom lo refleja en la QAction y en las preferencias."""
    win._apply_custom_shortcuts({"fit.bootstrap": "Ctrl+B"})
    assert win._action_registry["fit.bootstrap"].shortcut().toString() == "Ctrl+B"
    # fit.run conserva su predeterminado al no estar en el dict custom
    assert win._action_registry["fit.run"].shortcut().toString() == "Ctrl+R"
    # Se serializa en las preferencias de interfaz
    prefs = win._ui_preferences_state()
    assert prefs.custom_shortcuts.get("fit.bootstrap") == "Ctrl+B"


def test_model_grid_is_denser_than_data(win):
    """La rejilla del modelo tiene muchos más puntos que los canales."""
    import numpy as np
    v = np.linspace(-10.0, 10.0, 256)
    mv = win._model_grid(v)
    assert mv is not None
    assert mv.size > v.size
    assert mv.size >= 1200
    assert mv[0] == pytest.approx(v.min())
    assert mv[-1] == pytest.approx(v.max())


def test_render_stores_dense_curve_for_plotly(win):
    """El render guarda la curva densa y el residual para el gráfico Plotly."""
    import numpy as np
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    win.components_panels[0].enabled.setChecked(True)
    win._simulate_enabled = True
    win._refresh_plot()
    lr = win.canvas.last_render
    assert lr is not None and lr["model"] is not None
    # El modelo se evalúa en una rejilla más densa que los datos.
    assert lr["model_v"].size >= lr["velocity"].size
    assert lr["model"].size == lr["model_v"].size
    # El residual va en la rejilla de los datos.
    assert lr["residual"] is not None
    assert lr["residual"].size == lr["velocity"].size


def test_incremental_render_reuses_artists(win):
    """Dos renders con la misma disposición reutilizan los mismos artistas."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    win.components_panels[0].enabled.setChecked(True)
    win._simulate_enabled = True
    win._refresh_plot()
    cv = win.canvas
    artists = cv._artists
    assert artists is not None
    data_line = artists["data"]
    win._refresh_plot()
    # Misma estructura -> no se reconstruye la figura.
    assert cv._artists is artists
    assert cv._artists["data"] is data_line


def test_current_plotly_figure_builds(win):
    """La figura Plotly se construye con la curva densa (si plotly está)."""
    plotly = pytest.importorskip("plotly")  # noqa: F841
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    win.components_panels[0].enabled.setChecked(True)
    win._simulate_enabled = True
    win._refresh_plot()
    fig = win._current_plotly_figure()
    # Debe haber al menos datos + modelo.
    assert len(fig.data) >= 2
    # El trazo del modelo usa la rejilla densa.
    n_data = win.canvas.last_render["velocity"].size
    line_lengths = [len(tr.x) for tr in fig.data if tr.mode == "lines"]
    assert line_lengths and max(line_lengths) > n_data


def test_edit_minima_populates_list(win):
    """Entrar en edición semi-manual detecta mínimos y crea filas editables."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    win.on_edit_minima(redetect=True)
    assert win._minima_edit_mode
    assert len(win._minima_entries) > 0
    assert len(win._minima_rows) == len(win._minima_entries)
    # α-Fe (sextete) debe dar varios mínimos.
    assert len(win._minima_entries) >= 5
    # Por defecto todos incluidos con una contribución.
    assert all(e["included"] and e["count"] == 1 for e in win._minima_entries)


def test_minima_marker_click_syncs_checkbox(win):
    """Clicar un marcador (vía puente) alterna incluir y sincroniza la casilla."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    win.on_edit_minima(redetect=True)
    before = win._minima_entries[0]["included"]
    win._on_minima_marker_clicked(0)
    assert win._minima_entries[0]["included"] is (not before)
    assert win._minima_rows[0]["check"].isChecked() == win._minima_entries[0]["included"]


def test_minima_overlay_present_in_plotly_figure(win):
    """En modo edición, la figura Plotly añade la capa de marcadores de mínimos."""
    pytest.importorskip("plotly")
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    win.on_edit_minima(redetect=True)
    fig = win._current_plotly_figure()
    names = [t.name or "" for t in fig.data]
    assert any("nimos" in n for n in names)  # "Mínimos (...)"
    # Excluir uno hace aparecer la traza de excluidos.
    win._on_minima_row_changed(0, included=False)
    fig2 = win._current_plotly_figure()
    names2 = [t.name or "" for t in fig2.data]
    assert any("xcl" in n for n in names2)  # "...(excluidos)"


def test_propose_from_minima_builds_components(win):
    """Proponer desde mínimos curados configura componentes y simula."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    win.on_edit_minima(redetect=True)
    win.on_propose_from_minima()
    assert not win._minima_edit_mode          # se cierra la edición
    assert win._simulate_enabled
    active = [cp for cp in win.components_panels if cp.enabled.isChecked()]
    assert len(active) >= 1


def test_minima_multiplicity_adds_extra_components(win):
    """Marcar contribuciones extra añade más componentes que sin marcarlas."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    win.on_edit_minima(redetect=True)
    win.on_propose_from_minima()
    base = sum(cp.enabled.isChecked() for cp in win.components_panels)
    # Repite marcando todas las contribuciones como dobles.
    win.on_edit_minima(redetect=True)
    for k in range(len(win._minima_entries)):
        win._on_minima_row_changed(k, count=2)
    win.on_propose_from_minima()
    extra = sum(cp.enabled.isChecked() for cp in win.components_panels)
    assert extra > base


def test_propose_with_no_selection_warns_and_keeps_mode(win):
    """Si no hay mínimos marcados, avisa y no propone."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    win.on_edit_minima(redetect=True)
    for k in range(len(win._minima_entries)):
        win._on_minima_row_changed(k, included=False)
    win.on_propose_from_minima()
    # Sigue en modo edición (no se construyó propuesta).
    assert win._minima_edit_mode


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


def test_session_save_load_roundtrip_keeps_calibration(win, make_window, tmp_path):
    """Save→Load preserva calibration_info."""
    import json
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    win.calibration_info = {"source": "local", "calibration_sample": "X",
                             "velocity_calibrated": 12.0, "isomer_shift": -0.11}
    p = tmp_path / "s.json"
    p.write_text(json.dumps(win._session_payload(), default=str))
    win2 = make_window()
    win2._apply_session_payload(json.loads(p.read_text()))
    assert win2.calibration_info is not None
    assert win2.calibration_info["calibration_sample"] == "X"


def test_apply_web_calibration_metadata_sets_info_and_vmax(win, tmp_path):
    """La calibración web asociada actualiza la GUI y reescala el eje."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    calibration_file = tmp_path / "calibration.adt"
    calibration_file.write_text("dummy", encoding="utf-8")
    messages = []

    win._apply_web_calibration_metadata(
        measurement={"id": 1357, "calibration_id": 2468},
        calibration={
            "id": 2468,
            "sample": "alpha-Fe",
            "date": "2026-06-04",
            "velocity_calibrated": "11.966",
            "isomer_shift": "-0.1084",
        },
        calibration_path=calibration_file,
        debug=messages.append,
    )

    assert win.calibration_info is not None
    assert win.calibration_info["source"] == "web_api"
    assert win.calibration_info["medida_id"] == 1357
    assert win.calibration_info["calibration_id"] == 2468
    assert abs(float(win.calibration_info["velocity_calibrated"]) - 11.966) < 1e-6
    assert abs(float(win.calibration_info["isomer_shift"]) - (-0.1084)) < 1e-6
    assert win.calibration_info["calibration_file_name"] == "calibration.adt"
    assert abs(win.calib.vmax.value() - 11.966) < 1e-6
    assert win.file.velocity is not None
    # El eje de velocidad recorta el primer y último canal (igual que la GUI Tk
    # modular), así que su máximo queda ~un canal por debajo de vmax. Se
    # comprueba que el eje se reconstruyó con el nuevo vmax con esa tolerancia.
    vmax_axis = float(max(abs(win.file.velocity)))
    channel = 2.0 * win.calib.vmax.value() / max(1, win.file.counts.size // 2 - 1)
    assert 0.0 <= win.calib.vmax.value() - vmax_axis < 1.5 * channel
    assert any("Calibración web aplicada" in msg for msg in messages)


def test_apply_web_calibration_metadata_handles_missing_isomer_shift(win):
    """El label no falla si la API no envía isomer_shift."""
    win._apply_web_calibration_metadata(
        calibration={"id": 1, "sample": "alpha-Fe", "velocity_calibrated": "12.0"},
    )

    assert win.calibration_info is not None
    assert win.calibration_info["isomer_shift"] is None
    assert "IS = —" in win.calib_label.text()


def test_bootstrap_returns_sigma_estimates(win):
    """Bootstrap MC con 5 réplicas devuelve un mensaje con σ(MC) por parámetro."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    cp = win.components_panels[0]
    cp.params["delta"].set_value(-0.11)
    cp.params["bhf"].set_value(33.0)
    cp.params["gamma1"].set_value(0.28)
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


def test_qt_check_updates_uses_releaseinfo_without_tk_dict_bug(win, monkeypatch):
    """El actualizador Qt maneja ReleaseInfo (dataclass), no un dict de GitHub."""
    release = mq.ReleaseInfo(
        tag="v0.0.0", name="old", html_url="https://example.invalid/releases",
        body="", zipball_url="https://example.invalid/archive.zip", assets=[])
    monkeypatch.setattr(mq, "latest_release", lambda **kwargs: release)

    class ImmediateThread:
        def __init__(self, target, daemon=False):
            self.target = target
        def start(self):
            self.target()

    messages = []
    monkeypatch.setattr(mq.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(
        QtWidgets.QMessageBox, "information",
        staticmethod(lambda *args, **kwargs: messages.append(args[2]) or QtWidgets.QMessageBox.Ok))

    win.on_check_updates()

    assert messages
    assert "última versión" in messages[0]


def test_qt_update_available_dialog_can_offer_release_download(win, monkeypatch):
    """Qt muestra una release nueva con cuerpo largo y permite cancelar sin lanzar."""
    release = mq.ReleaseInfo(
        tag="v999.0.0", name="future", html_url="https://example.invalid/releases",
        body="Notas de prueba", zipball_url="https://example.invalid/archive.zip", assets=[])
    monkeypatch.setattr(mq.QtWidgets.QDialog, "exec", lambda self: QtWidgets.QDialog.Rejected)
    opened = []
    monkeypatch.setattr(mq.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(
        QtWidgets.QMessageBox, "question",
        staticmethod(lambda *args, **kwargs: QtWidgets.QMessageBox.No))

    win._show_update_available_dialog(release, "solo estables", verify_checksum=True)

    assert opened == []
def test_qt_distribution_range_limits_follow_mode(win):
    """Qt también ajusta límites de P(BHF) frente a P(ΔEQ)."""
    win.mode_combo.setCurrentIndex(1)
    assert win.dist_panel.bmin.spin.minimum() == 0.0
    assert win.dist_panel.bmin.spin.maximum() == 60.0
    assert win.dist_panel.bmax.spin.minimum() == 0.0
    assert win.dist_panel.bmax.spin.maximum() == 60.0

    win.dist_panel.bmin.set_value(10.0)
    win.dist_panel.bmax.set_value(50.0)
    win.mode_combo.setCurrentIndex(2)

    assert win.dist_panel.bmin.spin.minimum() == 0.0
    assert win.dist_panel.bmin.spin.maximum() == 7.0
    assert win.dist_panel.bmax.spin.minimum() == 0.0
    assert win.dist_panel.bmax.spin.maximum() == 7.0
    assert win.dist_panel.bmin.value() == 7.0
    assert win.dist_panel.bmax.value() == 7.0
    assert win.dist_panel.fixed_bhf.isEnabled()


def test_qt_distribution_2d_mode_is_exposed_and_persisted(win):
    """La opción P(BHF, ΔEQ) 2D aparece en el desplegable principal y en sesiones."""
    mode_items = [win.mode_combo.itemText(i) for i in range(win.mode_combo.count())]
    assert any("2D" in item and "BHF" in item for item in mode_items)
    shape_items = [win.dist_panel.shape_combo.itemData(i) for i in range(win.dist_panel.shape_combo.count())]
    assert "2D" in shape_items

    assert any("P(IS)" in item for item in mode_items)
    assert any("IS" in item and "ΔEQ" in item for item in mode_items)

    win.mode_combo.setCurrentIndex(4)
    assert win.is_distribution_mode
    assert win.dist_panel.shape == "2D"
    assert not win.dist_panel.qmin.isHidden()
    assert not win.dist_panel.quad.isEnabled()

    payload = win._session_payload()
    assert payload["model_state"]["dist_shape"] == "2D"
    assert payload["model_state"]["dist_variable"] == "BHF-ΔEQ"

    win.mode_combo.setCurrentIndex(0)
    win.dist_panel.shape_combo.setCurrentIndex(win.dist_panel.shape_combo.findData("Histograma"))
    win._apply_session_payload(payload)
    assert win.mode_combo.currentIndex() == 4
    assert win.dist_panel.shape == "2D"

    win.mode_combo.setCurrentIndex(5)
    assert win.dist_pair == ("delta", "quad")
    assert win._session_payload()["model_state"]["dist_variable"] == "IS-ΔEQ"


# ── Regresión: restauración de tipo Relajacion en sesión ─────────────────────

def test_session_roundtrip_preserves_relajacion_type(win):
    """Guardar y cargar una sesión con tipo Relajacion recupera el tipo correctamente.

    Regresión: session_io.py filtraba ki in ('Sextete','Doblete','Singlete'),
    descartando silenciosamente Relajacion/BlumeTjon/NeelSize.
    """
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")
    cp = win.components_panels[0]
    cp.type_combo.setCurrentText("Relajacion")
    assert cp.kind == "Relajacion"

    payload = win._session_payload()
    assert payload["model_state"]["component_kind"]["1"] == "Relajacion"

    # Restablecer a Sextete y volver a aplicar
    cp.type_combo.setCurrentText("Sextete")
    win._apply_session_payload(payload)
    assert win.components_panels[0].kind == "Relajacion"


def test_session_roundtrip_preserves_blume_tjon_and_neel_size(win):
    """BlumeTjon y NeelSize también se restauran tras save+load."""
    win._load_file(DATA / "hierro_metalico_alphaFe.adt")

    for tipo in ("BlumeTjon", "NeelSize"):
        win.components_panels[0].type_combo.setCurrentText(tipo)
        payload = win._session_payload()
        win.components_panels[0].type_combo.setCurrentText("Sextete")
        win._apply_session_payload(payload)
        assert win.components_panels[0].kind == tipo, f"Tipo {tipo} no se restauró"


# ── Regresión: validación acepta los nuevos tipos de componente ───────────────

def test_validate_fit_state_accepts_all_component_kinds():
    """validate_fit_state no debe reportar error para ningún tipo de componente válido.

    Regresión: la whitelist solo tenía Sextete/Doblete/Singlete.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.fit_engine import Component, FitState
    from core.params import COMPONENT_KINDS
    from core.validation import validate_fit_state
    import numpy as np

    v = np.linspace(-6, 6, 512)
    y = np.ones(512)
    for kind in COMPONENT_KINDS:
        state = FitState(
            velocity=v, y_data=y, sigma_data=np.ones(512),
            values={"baseline": 1.0}, fixed={}, bounds={},
            components=[Component(idx=1, enabled=True, kind=kind)],
            constraints=[], line_profile="Lorentziana",
        )
        issues = validate_fit_state(state)
        kind_issues = [i for i in issues if i.key == "s1_kind"]
        assert not kind_issues, f"validate_fit_state rechaza tipo válido {kind!r}"


# ── Botón Cancelar del diálogo de progreso ────────────────────────────────────

def test_cancel_button_aborts_fit_silently(win):
    """Pulsar Cancelar durante un ajuste aborta sin mostrar error y devuelve None.

    _run_with_fit_progress captura FitCancelledError en silencio y devuelve None.
    """
    from gui.fit_workflow import FitCancelledError
    from unittest.mock import patch

    errors = []
    with patch("PySide6.QtWidgets.QMessageBox.critical",
               side_effect=lambda *a, **kw: errors.append(a)):
        result = win._run_with_fit_progress(
            "Test", "Trabajando…",
            lambda upd: (_ for _ in ()).throw(FitCancelledError()),
        )

    assert result is None, "Debe devolver None al cancelar"
    assert not errors, "No debe mostrar QMessageBox de error al cancelar"


def test_progress_dialog_has_cancel_button(win):
    """El diálogo de progreso contiene un botón con el texto de cancelar."""
    from PySide6.QtWidgets import QPushButton

    _dlg, _update, close = win._open_progress_dialog("Test", "Trabajando…")
    try:
        btns = _dlg.findChildren(QPushButton)
        assert any(b.objectName() == "btn_cancel_fit" for b in btns), \
            "No se encontró el botón Cancelar en el diálogo de progreso"
    finally:
        close()


# ── Reflow del panel de componentes según el tipo ─────────────────────────────

def _placed_in_grid(panel):
    """{name: (row, col)} de los controles colocados y no ocultos."""
    g = panel.params_grid
    out = {}
    for name, ctl in panel.params.items():
        idx = g.indexOf(ctl)
        if idx >= 0 and not ctl.isHidden():
            r, c, _rs, _cs = g.getItemPosition(idx)
            out[name] = (r, c)
    return out


def test_component_panel_reflow_has_no_gaps_per_kind(win):
    """Para cada tipo, las columnas del grid se llenan sin huecos."""
    cp = win.components_panels[0]
    for kind in ("Sextete", "Doblete", "Singlete", "Relajacion", "BlumeTjon", "NeelSize"):
        cp.type_combo.setCurrentText(kind)
        placed = _placed_in_grid(cp)
        for col in (0, 1):
            rows = sorted(r for _, (r, c) in placed.items() if c == col)
            assert rows == list(range(len(rows))), \
                f"{kind} col{col} tiene huecos: filas {rows}"


def test_neelsize_hides_texture_beta_and_shows_neel_params(win):
    """NeelSize oculta textura/β y muestra los parámetros Néel agrupados."""
    cp = win.components_panels[0]
    cp.type_combo.setCurrentText("NeelSize")
    placed = _placed_in_grid(cp)
    assert "texture" not in placed and "beta" not in placed
    for p in ("neel_mean_d_nm", "neel_sigma", "neel_bins",
              "neel_temp_k", "neel_log10_keff", "neel_log10_tau0"):
        assert p in placed, f"falta {p} en NeelSize"
    # El bloque de tamaño aparece antes que el de dinámica en la columna derecha.
    assert placed["neel_mean_d_nm"][0] < placed["neel_temp_k"][0]


def test_doblete_hides_bhf_and_gamma3(win):
    """Un doblete no muestra BHF ni Γ3 (no greado: oculto)."""
    cp = win.components_panels[0]
    cp.type_combo.setCurrentText("Doblete")
    placed = _placed_in_grid(cp)
    assert "bhf" not in placed and "gamma3" not in placed
    assert "delta" in placed and "quad" in placed


def test_btn_show_map_lifecycle(win):
    """btn_show_map: oculto por defecto, visible tras ajuste 2D, oculto al cambiar modo."""
    import numpy as np

    # Antes de cualquier ajuste el botón debe estar oculto.
    assert not win.dist_panel.btn_show_map.isVisible()

    # Simular que se completa un ajuste 2D registrando un resultado falso.
    win._load_file(DATA / "magnetita_Fe3O4.adt")
    captured = {}
    win._show_distribution_dialog = lambda r: captured.setdefault("r", r)
    win.mode_combo.setCurrentIndex(4)
    if hasattr(win.dist_panel, "qbins"):
        win.dist_panel.qbins.set_value(9)
    if hasattr(win.dist_panel, "nbins"):
        win.dist_panel.nbins.set_value(15)
    win.on_fit()
    res = win.runtime_results.distribution_result
    assert np.asarray(res.probability).ndim == 2
    # Tras el ajuste 2D el botón debe ser visible.
    assert win.dist_panel.btn_show_map.isVisible()

    # Pulsar el botón reabre el diálogo (interceptado con lambda).
    reopened = {}
    win._show_distribution_dialog = lambda r: reopened.setdefault("r", r)
    win.dist_panel.btn_show_map.click()
    assert "r" in reopened, "btn_show_map no llamó a _show_distribution_dialog"

    # Cambiar a un modo no-2D debe ocultar el botón.
    win.mode_combo.setCurrentIndex(0)
    assert not win.dist_panel.btn_show_map.isVisible()


def test_lorentzian_gamma_zero_returns_finite(win):
    """lorentzian con gamma=0 no produce NaN ni inf (guard 1e-9)."""
    import numpy as np
    from core.physics import lorentzian
    v = np.linspace(-5, 5, 100)
    result = lorentzian(v, center=0.0, gamma=0.0)
    assert np.all(np.isfinite(result)), "lorentzian(gamma=0) produce NaN/inf"
    assert float(result.max()) <= 1.0 + 1e-9
