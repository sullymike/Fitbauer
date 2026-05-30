"""Tests del CLI de ajuste por fichero (mossbauer_fit_cli.py)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import tkinter as tk
    import mossbauer_fe33_gui_v2IA  # noqa: F401
    from mossbauer_app import MossbauerApp
    from mossbauer_fit_cli import fit_spectrum, main
except Exception as exc:  # pragma: no cover
    pytest.skip(f"GUI/Tk no disponible: {exc}", allow_module_level=True)

import tkinter.messagebox as mb  # noqa: E402

DATA = ROOT / "data_sample"


def _make_alpha_fe_template(tmp_path: Path) -> Path:
    """Crea una sesión .json con parámetros iniciales razonables para α-Fe."""
    mb.showinfo = mb.showwarning = mb.showerror = lambda *a, **k: None
    tk.Menu.tk_popup = lambda self, *a, **k: None
    app = MossbauerApp()
    try:
        app.load_ws5(DATA / "hierro_metalico_alphaFe.adt")
        app.vars["s1_delta"].set(-0.1)
        app.vars["s1_quad"].set(0.0)
        app.vars["s1_bhf"].set(33.0)
        app.vars["s1_gamma1"].set(0.14)
        app.vars["s1_depth"].set(0.013)
        for k in ("s1_int1", "s1_int2", "s1_int3", "s1_gamma2", "s1_gamma3", "s1_quad"):
            app.fixed_vars[k].set(True)
        template = app.session_payload()
    finally:
        app.destroy()
    path = tmp_path / "alpha_fe_template.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(template, fh, ensure_ascii=False)
    return path


def test_fit_spectrum_recovers_alpha_fe(tmp_path):
    template = _make_alpha_fe_template(tmp_path)
    out = tmp_path / "result.json"
    session = fit_spectrum(template, DATA / "hierro_metalico_alphaFe.adt", out)
    assert out.exists()
    r = session["batch_fit_result"]
    assert abs(r["values"]["s1_bhf"] - 33.0) < 1.0
    assert abs(r["values"]["s1_delta"] - (-0.1)) < 0.1
    assert r["stats"].get("chi2") is not None


def test_fit_spectrum_writes_reloadable_session(tmp_path):
    template = _make_alpha_fe_template(tmp_path)
    out = tmp_path / "result.json"
    fit_spectrum(template, DATA / "hierro_metalico_alphaFe.adt", out)
    with out.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    # Tiene la misma estructura que una sesión guardada + batch_fit_result.
    assert "model_state" in data and "counts" in data
    assert "batch_fit_result" in data
    assert data["batch_fit_result"]["spectrum"].endswith("hierro_metalico_alphaFe.adt")


def test_main_exit_codes(tmp_path):
    template = _make_alpha_fe_template(tmp_path)
    out_ok = tmp_path / "ok.json"
    code = main(["--template", str(template),
                 "--spectrum", str(DATA / "hierro_metalico_alphaFe.adt"),
                 "--out", str(out_ok), "--quiet"])
    assert code == 0 and out_ok.exists()
    code = main(["--template", str(template),
                 "--spectrum", str(tmp_path / "no-existe.adt"),
                 "--out", str(tmp_path / "fail.json"), "--quiet"])
    assert code == 1
