"""Test de integración del ajuste en serie: warm-start sobre dos espectros sintéticos."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import tkinter as tk
    import mossbauer_fe33_gui_v2IA  # noqa: F401
    from mossbauer_app import MossbauerApp
except Exception as exc:  # pragma: no cover
    pytest.skip(f"GUI/Tk no disponible: {exc}", allow_module_level=True)

import tkinter.messagebox as mb  # noqa: E402

DATA = ROOT / "data_sample"


@pytest.fixture
def app():
    mb.showinfo = mb.showwarning = mb.showerror = lambda *a, **k: None
    tk.Menu.tk_popup = lambda self, *a, **k: None
    app = MossbauerApp()
    yield app
    app.destroy()


def _prepare_alpha_fe_template(app):
    """Carga hierro metálico y configura el modelo activo para warm-start."""
    app.load_ws5(DATA / "hierro_metalico_alphaFe.adt")
    app.vars["s1_delta"].set(-0.1)
    app.vars["s1_quad"].set(0.0)
    app.vars["s1_bhf"].set(33.0)
    app.vars["s1_gamma1"].set(0.14)
    app.vars["s1_depth"].set(0.013)
    for k in ("s1_int1", "s1_int2", "s1_int3", "s1_gamma2", "s1_gamma3", "s1_quad"):
        app.fixed_vars[k].set(True)


def test_batch_fit_sequential_runs_and_recovers(app):
    _prepare_alpha_fe_template(app)
    files = [DATA / "hierro_metalico_alphaFe.adt",
             DATA / "hierro_metalico_alphaFe.adt"]
    metas = [10.0, 20.0]
    results = app.batch_fit_sequential(files, metas)
    assert len(results) == 2
    assert all(r["status"] == "ok" for r in results)
    for r in results:
        bhf = r["values"].get("s1_bhf")
        delta = r["values"].get("s1_delta")
        assert bhf is not None and abs(bhf - 33.0) < 1.0
        assert delta is not None and abs(delta - (-0.1)) < 0.1
        assert r["stats"].get("chi2") is not None


def test_batch_fit_continues_after_failure(app, tmp_path):
    _prepare_alpha_fe_template(app)
    # Fichero inexistente fuerza fallo; el siguiente debe ajustarse igualmente.
    missing = tmp_path / "no_existe.adt"
    files = [missing, DATA / "hierro_metalico_alphaFe.adt"]
    results = app.batch_fit_sequential(files, [1.0, 2.0])
    assert results[0]["status"] == "failed"
    assert "error" in results[0]
    assert results[1]["status"] == "ok"
