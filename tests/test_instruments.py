"""Biblioteca de equipos (core/instruments.py) y ventana de importación."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from core.instruments import InstrumentLibrary, InstrumentProfile, instrument_slug
from core.spectrum_import import ImportHints, parse_spectrum_text


def _profile(name="Mössbauer 2 (lab B)", **kw) -> InstrumentProfile:
    return InstrumentProfile(
        name=name, import_hints=ImportHints(y_kind="absorption_percent", decimal=","),
        drive_form="triangular", fold_mode="single_sweep", reverse_velocity=True, **kw)


def test_save_get_list_delete(tmp_path):
    lib = InstrumentLibrary(tmp_path)
    assert lib.list() == []
    path = lib.save(_profile())
    assert path.parent.name == instrument_slug("Mössbauer 2 (lab B)") == "mossbauer_2_lab_b"
    back = lib.get("Mössbauer 2 (lab B)")
    assert back == _profile()
    lib.save(_profile("alpha"))
    assert lib.names() == ["alpha", "Mössbauer 2 (lab B)"]
    assert lib.delete("alpha") and not (tmp_path / "alpha").exists()
    assert lib.get("alpha") is None and not lib.delete("alpha")


def test_delete_keeps_other_files(tmp_path):
    """La carpeta del equipo guardará calibraciones: no se borran con el perfil."""
    lib = InstrumentLibrary(tmp_path)
    folder = lib.save(_profile("A")).parent
    (folder / "calib.adt").write_text("1\n")
    lib.delete("A")
    assert (folder / "calib.adt").exists() and lib.get("A") is None


def test_slug_clash_refused(tmp_path):
    lib = InstrumentLibrary(tmp_path)
    lib.save(_profile("Equipo 1"))
    with pytest.raises(ValueError):
        lib.save(_profile("equipo-1"))


def test_broken_profile_is_skipped(tmp_path):
    lib = InstrumentLibrary(tmp_path)
    lib.save(_profile("ok"))
    (tmp_path / "roto").mkdir()
    (tmp_path / "roto" / "instrument.json").write_text("{not json")
    assert lib.names() == ["ok"]


def test_profile_hints_drive_reader(tmp_path):
    lib = InstrumentLibrary(tmp_path)
    lib.save(_profile("B"))
    v = np.linspace(-4, 4, 200)
    a = 0.5 * np.exp(-v ** 2)                       # absorción < 1 %: ambigua
    text = "\n".join(f"{x:.4f};{y:.6f}".replace(".", ",") for x, y in zip(v, a))
    assert parse_spectrum_text(text).y_kind == "absorption"
    r = parse_spectrum_text(text, lib.get("B").import_hints)
    assert r.y_kind == "absorption_percent"
    np.testing.assert_allclose(r.transmission()[0], 1 - np.round(a, 6) / 100)


def test_unknown_values_fall_back():
    p = InstrumentProfile.from_dict({"name": "x", "drive_form": "square", "fold_mode": "??"})
    assert p.drive_form == "triangular" and p.fold_mode == "fold"
