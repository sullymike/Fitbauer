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


# ── Fechas de medida ─────────────────────────────────────────────────────────

import datetime as dt
import os

from core.batch_fit import write_results_csv
from core.instruments import CalibrationRecord, calibration_for_date
from core.spectrum_import import measurement_date, parse_date_text


@pytest.mark.parametrize("text, dmy, mdy", [
    ("2025-03-14", "2025-03-14", "2025-03-14"),
    ("Date: 14/03/2025", "2025-03-14", "2025-03-14"),       # 14 > 12: manda el día
    ("03/15/2025 10:00", "2025-03-15", "2025-03-15"),
    ("05.06.24", "2024-06-05", "2024-05-06"),               # ambigua: decide el orden
    ("Mar 14, 2025", "2025-03-14", "2025-03-14"),
    ("14-Mar-2025", "2025-03-14", "2025-03-14"),
    ("12 dic 2024", "2024-12-12", "2024-12-12"),
])
def test_parse_date_text(text, dmy, mdy):
    assert parse_date_text(text).isoformat() == dmy
    assert parse_date_text(text, "mdy").isoformat() == mdy


def test_parse_date_text_rejects_non_dates():
    assert parse_date_text("Channels 512 time 300") is None
    assert parse_date_text("31/02/2025") is None


def _counts_text(header: str) -> str:
    c = np.random.default_rng(0).poisson(1e4, 256)
    return header + "\n".join(str(x) for x in c)


def test_measurement_date_prefers_date_lines(tmp_path):
    text = _counts_text("Run 01.02.2020 (template)\nAcquisition date: 2025-03-14\n")
    r = parse_spectrum_text(text)
    assert measurement_date(r) == (dt.date(2025, 3, 14), "header")


def test_measurement_date_falls_back_to_file(tmp_path):
    p = tmp_path / "s.dat"
    p.write_text(_counts_text("Sample X\n"))
    stamp = dt.datetime(2024, 7, 1, 12).timestamp()
    os.utime(p, (stamp, stamp))
    from core.spectrum_import import read_spectrum_file
    assert measurement_date(read_spectrum_file(p), p) == (dt.date(2024, 7, 1), "file")
    assert measurement_date(read_spectrum_file(p)) == (None, None)


# ── Calibraciones por equipo ────────────────────────────────────────────────

def _cal(day: str, vmax: float, **kw) -> CalibrationRecord:
    return CalibrationRecord(date=dt.date.fromisoformat(day), vmax=vmax, **kw)


def test_calibration_for_date_rule():
    recs = [_cal("2025-01-10", 10.0), _cal("2025-06-01", 10.2), _cal("2025-06-01", 10.3)]
    assert calibration_for_date(recs, dt.date(2025, 1, 9)) is None
    assert calibration_for_date(recs, dt.date(2025, 1, 10)).vmax == 10.0
    assert calibration_for_date(recs, dt.date(2025, 5, 31)).vmax == 10.0
    assert calibration_for_date(recs, dt.date(2026, 1, 1)).vmax == 10.3   # la añadida después


def test_choose_calibration_rules(tmp_path):
    from core.instruments import latest_calibration
    assert latest_calibration([]) is None
    assert latest_calibration([_cal("2025-06-01", 1.0), _cal("2025-01-01", 2.0)]).vmax == 1.0
    lib = InstrumentLibrary(tmp_path / "lib")
    lib.save(_profile("Lab"))
    a = lib.add_calibration("Lab", _cal("2025-01-10", 10.0))
    lib.add_calibration("Lab", _cal("2025-06-01", 10.2))
    old = parse_spectrum_text(_counts_text("Date: 2025-03-14\n"))
    nodate = parse_spectrum_text(_counts_text("Sample\n"))
    ch = lib.choose_calibration("Lab", old)
    assert (ch.rule, ch.record.vmax, ch.date) == ("date", 10.0, dt.date(2025, 3, 14))
    assert lib.choose_calibration("Lab", nodate).record is None
    ch = lib.choose_calibration("Lab", old, record_id=a.id)
    assert (ch.rule, ch.record.vmax) == ("manual", 10.0)
    prof = lib.get("Lab"); prof.calibration_rule = "latest"; lib.save(prof)
    assert lib.get("Lab").calibration_rule == "latest"
    for spec in (old, nodate, None):
        ch = lib.choose_calibration("Lab", spec)
        assert (ch.rule, ch.record.vmax) == ("latest", 10.2)
    assert lib.choose_calibration("nadie", old).record is None
    # calibration_info: el mismo diccionario para la GUI y la sesión sin GUI.
    info = lib.calibration_info("Lab", lib.choose_calibration("Lab", old, record_id=a.id))
    assert info["source"] == "instrument" and info["instrument"] == "Lab"
    assert (info["velocity_calibrated"], info["calibration_rule"]) == (10.0, "manual")
    assert info["measurement_date"] == "2025-03-14" and info["calibration_id"] == a.id
    assert info["calibration_file_path"] is None
    assert lib.calibration_info("Lab", lib.choose_calibration("nadie", old)) is None
    assert InstrumentProfile.from_dict({"name": "x", "calibration_rule": "raro"}).calibration_rule == "date"


def test_calibrations_stored_with_file_copy(tmp_path):
    lib = InstrumentLibrary(tmp_path / "lib")
    with pytest.raises(KeyError):
        lib.add_calibration("nadie", _cal("2025-01-01", 10.0))
    lib.save(_profile("A"))
    src = tmp_path / "afe.adt"
    src.write_text("1\n2\n")
    rec = lib.add_calibration("A", _cal("2025-06-01", 10.2, sextet_pattern="legacy",
                                        isomer_shift=-0.11, sample="α-Fe"), src)
    lib.add_calibration("A", _cal("2025-01-10", 10.0))
    recs = lib.calibrations("A")
    assert [r.date.isoformat() for r in recs] == ["2025-01-10", "2025-06-01"]
    assert recs[1] == rec and recs[1].sextet_pattern == "legacy"
    copy = lib.calibration_file("A", recs[1])
    assert copy.read_text() == "1\n2\n" and copy.parent.parent == tmp_path / "lib" / "a"
    assert lib.calibration_for("A", dt.date(2025, 7, 1)).isomer_shift == -0.11
    # Borrar el equipo conserva sus calibraciones.
    lib.delete("A")
    assert copy.exists()
    lib.save(_profile("A"))
    assert len(lib.calibrations("A")) == 2
    assert lib.remove_calibration("A", rec.id) and not copy.exists()
    assert not lib.remove_calibration("A", rec.id)


def test_profile_date_order_roundtrip():
    p = InstrumentProfile.from_dict({**_profile().to_dict(), "date_order": "mdy"})
    assert p.date_order == "mdy"
    assert InstrumentProfile.from_dict({"name": "x", "date_order": "ymd"}).date_order == "dmy"


def test_batch_tsv_calibration_columns(tmp_path):
    rows = [{"file": "a", "status": "ok", "values": {"x": 1}, "errors": {"x": 0.1},
             "stats": {}, "calibration": {"measured": "2025-03-14", "date": "2025-01-10",
                                          "vmax": 10.0}}]
    p = tmp_path / "r.tsv"
    write_results_csv(p, ["x"], rows)
    head, line = p.read_text().splitlines()
    assert head.split("\t")[5:8] == ["measured", "calibration", "vmax_cal"]
    assert line.split("\t")[5:8] == ["2025-03-14", "2025-01-10", "10.0"]
    write_results_csv(p, ["x"], [{**rows[0], "calibration": None}])
    assert "calibration" not in p.read_text().splitlines()[0]


# ── Reconocimiento automático ────────────────────────────────────────────────

def _spectrum_file(tmp_path, name, header=""):
    p = tmp_path / name
    p.write_text(header + "\n".join(str(1000 + i % 7) for i in range(256)))
    return p


def test_match_fields_round_trip(tmp_path):
    lib = InstrumentLibrary(tmp_path / "lib")
    lib.save(_profile("A", match_text=["WissEl"], match_name=["*.ws5"]))
    back = lib.get("A")
    assert back.match_text == ["WissEl"] and back.match_name == ["*.ws5"]
    # Perfiles anteriores (sin los campos) no se reconocen nunca.
    assert InstrumentProfile.from_dict({"name": "viejo"}).recognizable is False


def test_recognize_by_header_and_by_name(tmp_path):
    lib = InstrumentLibrary(tmp_path / "lib")
    lib.save(InstrumentProfile(name="Lab B", match_text=["lab b; ", "Spectrometer B"]))
    lib.save(InstrumentProfile(name="FeB", match_name=["FeB*.dat"]))
    lib.save(InstrumentProfile(name="Sin criterios"))
    by_text = _spectrum_file(tmp_path, "x.dat", "Instrument: SPECTROMETER B\nDate: 2025-01-02\n")
    by_name = _spectrum_file(tmp_path, "feb_017.DAT")
    nothing = _spectrum_file(tmp_path, "otro.dat", "Instrument: C\n")
    assert [p.name for p in lib.recognize(by_text)] == ["Lab B"]
    assert [p.name for p in lib.recognize(by_name)] == ["FeB"]     # sin distinguir mayúsculas
    assert lib.recognize(nothing) == []
    # Los números de los datos no cuentan como cabecera.
    lib.save(InstrumentProfile(name="Num", match_text=["1003"]))
    assert lib.recognize(nothing) == []


def test_recognize_requires_both_criteria_and_reports_ambiguity(tmp_path):
    lib = InstrumentLibrary(tmp_path / "lib")
    lib.save(InstrumentProfile(name="Ambos", match_text=["Lab B"], match_name=["*.ws5"]))
    assert lib.recognize(_spectrum_file(tmp_path, "a.dat", "Lab B\n")) == []
    assert lib.recognize(_spectrum_file(tmp_path, "b.ws5", "Otro\n")) == []
    ok = _spectrum_file(tmp_path, "c.ws5", "Lab B\n")
    assert [p.name for p in lib.recognize(ok)] == ["Ambos"]
    lib.save(InstrumentProfile(name="Otro", match_name=["c.*"]))
    assert {p.name for p in lib.recognize(ok)} == {"Ambos", "Otro"}


def test_split_patterns():
    from core.instruments import split_patterns
    assert split_patterns(" FeB-1; *.ws5 ;; ") == ["FeB-1", "*.ws5"]
