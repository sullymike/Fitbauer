"""Test de integración del ajuste en serie: warm-start sobre dos espectros sintéticos.

Headless: usa core.session.HeadlessSession; no requiere Tk.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.session import HeadlessSession  # noqa: E402

DATA = ROOT / "data_sample"


@pytest.fixture
def session():
    return HeadlessSession()


def _prepare_alpha_fe_template(session):
    """Carga hierro metálico y configura el modelo activo para warm-start."""
    session.load_ws5(DATA / "hierro_metalico_alphaFe.adt")
    session.model.vars["s1_delta"] = -0.1
    session.model.vars["s1_quad"] = 0.0
    session.model.vars["s1_bhf"] = 33.0
    session.model.vars["s1_gamma1"] = 0.14
    session.model.vars["s1_depth"] = 0.013
    for k in ("s1_int1", "s1_int2", "s1_int3", "s1_gamma2", "s1_gamma3", "s1_quad"):
        session.model.fixed[k] = True


def test_batch_fit_sequential_runs_and_recovers(session):
    _prepare_alpha_fe_template(session)
    files = [DATA / "hierro_metalico_alphaFe.adt",
             DATA / "hierro_metalico_alphaFe.adt"]
    metas = [10.0, 20.0]
    results = session.batch_fit_sequential(files, metas)
    assert len(results) == 2
    assert all(r["status"] == "ok" for r in results)
    for r in results:
        bhf = r["values"].get("s1_bhf")
        delta = r["values"].get("s1_delta")
        assert bhf is not None and abs(bhf - 33.0) < 1.0
        assert delta is not None and abs(delta - (-0.1)) < 0.1
        assert r["stats"].get("chi2") is not None


def test_batch_fit_continues_after_failure(session, tmp_path):
    _prepare_alpha_fe_template(session)
    # Fichero inexistente fuerza fallo; el siguiente debe ajustarse igualmente.
    missing = tmp_path / "no_existe.adt"
    files = [missing, DATA / "hierro_metalico_alphaFe.adt"]
    results = session.batch_fit_sequential(files, [1.0, 2.0])
    assert results[0]["status"] == "failed"
    assert "error" in results[0]
    assert results[1]["status"] == "ok"
