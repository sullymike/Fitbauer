"""Tests del sugeridor de fases (core.phase_id)."""
from __future__ import annotations

from core.phase_id import load_reference_db, suggest_phases


def test_db_loads():
    db = load_reference_db()
    assert len(db) > 50
    # Campos esperados presentes en el primer registro.
    e = db[0]
    for key in ("sample", "IS_mm_s", "QS_mm_s", "Bhf_T", "reference"):
        assert key in e


def test_alpha_fe_top_is_iron():
    """δ≈0, B_hf≈33 T → α-Fe metálico (calibración)."""
    res = suggest_phases(0.0, quad=0.0, bhf=33.0, kind="Sextete")
    assert res, "esperaba al menos un match"
    assert res[0].sample == "Iron"
    assert res[0].score > 0.8


def test_hematite_sextet():
    """δ≈0.37, B_hf≈51.8 T (RT) → hematita."""
    res = suggest_phases(0.37, quad=-0.20, bhf=51.8, kind="Sextete")
    assert res
    assert res[0].sample == "Hematite"


def test_pyrite_doublet():
    """δ≈0.33, ΔEQ≈0.61, sin campo → pirita (doblete paramagnético)."""
    res = suggest_phases(0.33, quad=0.61, kind="Doblete")
    assert res
    assert res[0].sample == "Pyrite"
    # No debe proponer fases magnéticas para un doblete.
    assert all(m.bhf is None or m.bhf <= 5.0 for m in res)


def test_magnetic_gating():
    """Una componente magnética no debe casar con refs paramagnéticas."""
    res = suggest_phases(0.30, quad=0.0, bhf=49.0, kind="Sextete")
    assert res
    assert all(m.bhf is not None and m.bhf > 5.0 for m in res)


def test_kind_inference():
    """Sin kind explícito se infiere por B_hf."""
    res = suggest_phases(0.0, quad=0.0, bhf=33.0)  # debería inferir Sextete
    assert res and res[0].sample == "Iron"


def test_scores_sorted_descending():
    res = suggest_phases(0.37, quad=-0.20, bhf=51.8, kind="Sextete", top_n=5)
    scores = [m.score for m in res]
    assert scores == sorted(scores, reverse=True)
