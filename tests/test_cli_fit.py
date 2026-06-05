"""Tests del CLI de ajuste por fichero (mossbauer_fit_cli.py).

El CLI es completamente headless (core.session.HeadlessSession); no requiere Tk.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mossbauer_fit_cli import fit_spectrum, main  # noqa: E402

DATA = ROOT / "data_sample"


def _make_alpha_fe_template(tmp_path: Path) -> Path:
    """Escribe una plantilla .json con parámetros iniciales razonables para α-Fe."""
    template = {
        "model_state": {
            "vars": {
                "vmax": 12.007, "voigt_sigma": 0.05,
                "baseline": 1.0, "slope": 0.0,
                "s1_delta": -0.1, "s1_quad": 0.0, "s1_bhf": 33.0,
                "s1_gamma1": 0.14, "s1_gamma2": 1.0, "s1_gamma3": 1.0,
                "s1_depth": 0.013, "s1_int1": 3.0, "s1_int2": 2.0, "s1_int3": 1.0,
            },
            "fixed": {
                "s1_int1": True, "s1_int2": True, "s1_int3": True,
                "s1_gamma2": True, "s1_gamma3": True, "s1_quad": True,
            },
            "sextet_enabled": {"1": True, "2": False, "3": False},
            "component_kind": {"1": "Sextete", "2": "Sextete", "3": "Sextete"},
            "intensity_mode": {"1": "free"},
            "quad_treatment": {"1": "1st_order"},
            "fit_velocity": False, "fit_center": False,
            "line_profile": "Lorentziana", "likelihood": "gauss",
            "robust_loss": "linear", "constraints": [],
        }
    }
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
