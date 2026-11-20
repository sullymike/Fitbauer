"""CLI y sesión headless con equipo: calibración por fecha de medida.

Dos medidas sintéticas del mismo doblete con Vmax reales distintas (la
calibración del equipo cambió entre ambas). Con el equipo, cada una se ajusta
con la calibración de su fecha y recupera δ; sin él, la segunda sale sesgada.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pytest

import mossbauer_fit_cli as cli
from core.folding import triangular_velocity_axis
from core.instruments import CalibrationRecord, InstrumentLibrary, InstrumentProfile
from core.session import HeadlessSession

ROOT = Path(__file__).resolve().parents[1]
N, CENTER, DELTA = 512, 256.5, 0.40


def _counts(vmax: float, seed: int) -> np.ndarray:
    v = triangular_velocity_axis(N, vmax, CENTER)
    g = 0.15 ** 2
    t = 1 - sum(0.08 * g / ((v - x) ** 2 + g) for x in (DELTA - 0.5, DELTA + 0.5))
    return np.random.default_rng(seed).poisson(2e5 * t).astype(float)


@pytest.fixture
def setup(tmp_path):
    lib = InstrumentLibrary(tmp_path / "lib")
    lib.save(InstrumentProfile(name="Lab B"))
    lib.add_calibration("Lab B", CalibrationRecord(date=dt.date(2025, 1, 1), vmax=6.0))
    lib.add_calibration("Lab B", CalibrationRecord(date=dt.date(2025, 6, 1), vmax=6.6))
    files = []
    for name, date, vmax in (("ene.dat", "2025-03-14", 6.0), ("jul.dat", "14/07/2025", 6.6)):
        p = tmp_path / name
        p.write_text(f"Sample: FeX\nDate: {date}\n" + "\n".join(f"{x:.0f}" for x in _counts(vmax, 1)))
        files.append(p)
    ms = json.loads((ROOT / "data_sample/template_siderita.json").read_text())["model_state"]
    ms["vars"].update(vmax=6.0, s1_delta=0.45, s1_quad=0.9, s1_gamma1=0.35, s1_depth=0.08)
    template = tmp_path / "t.json"
    template.write_text(json.dumps({"model_state": ms}))
    return lib, files, template


def test_session_assigns_calibration_by_date(setup):
    lib, files, template = setup
    s = HeadlessSession()
    s.apply_template_model_state(json.loads(template.read_text())["model_state"])
    s.use_instrument("Lab B", lib)
    s.load_ws5(files[1])
    assert s.model.vars["vmax"] == pytest.approx(6.6)
    info = s.session_payload()["calibration"]
    assert info["calibration_date"] == "2025-06-01" and info["measurement_date"] == "2025-07-14"
    with pytest.raises(KeyError):
        s.use_instrument("nadie", lib)


def test_cli_batch_with_instrument(setup, tmp_path, capsys):
    lib, files, template = setup
    out = tmp_path / "serie.json"
    rc = cli.main(["--template", str(template), "--spectrum", *map(str, files),
                   "--out", str(out), "--instrument", "Lab B",
                   "--instruments-dir", str(lib.root)])
    assert rc == 0
    rows = json.loads(out.read_text())["results"]
    assert [r["calibration"]["date"] for r in rows] == ["2025-01-01", "2025-06-01"]
    for r in rows:
        assert abs(r["values"]["s1_delta"] - DELTA) < 4 * r["errors"]["s1_delta"]
    assert "cal. 2025-06-01" in capsys.readouterr().out
    # Sin equipo, la Vmax de la plantilla sesga la medida de julio.
    rc = cli.main(["--template", str(template), "--spectrum", str(files[1]),
                   "--out", str(tmp_path / "sin.json"), "--quiet"])
    sin = json.loads((tmp_path / "sin.json").read_text())["batch_fit_result"]
    assert rc == 0 and abs(sin["values"]["s1_delta"] - DELTA) > 10 * sin["errors"]["s1_delta"]


def test_cli_single_with_instrument_and_warning(setup, tmp_path, capsys):
    lib, files, template = setup
    early = tmp_path / "old.dat"
    early.write_text("Date: 2024-12-01\n" + "\n".join(f"{x:.0f}" for x in _counts(6.0, 2)))
    rc = cli.main(["--template", str(template), "--spectrum", str(early), "--out",
                   str(tmp_path / "o.json"), "--instrument", "Lab B",
                   "--instruments-dir", str(lib.root)])
    assert rc == 0
    res = json.loads((tmp_path / "o.json").read_text())
    assert "no calibration on or before 2024-12-01" in res["batch_fit_result"]["warning"]
    assert "AVISO" in capsys.readouterr().out
    rc = cli.main(["--template", str(template), "--spectrum", str(files[0]), "--out",
                   str(tmp_path / "o2.json"), "--instrument", "Lab B",
                   "--instruments-dir", str(lib.root), "--quiet"])
    assert rc == 0
    cal = json.loads((tmp_path / "o2.json").read_text())["calibration"]
    assert cal["source"] == "instrument" and cal["calibration_date"] == "2025-01-01"


def test_cli_vmax_and_instrument_conflict(setup, tmp_path):
    _lib, files, template = setup
    rc = cli.main(["--template", str(template), "--spectrum", str(files[0]), "--out",
                   str(tmp_path / "x.json"), "--instrument", "Lab B", "--vmax", "6"])
    assert rc == 2


def test_cli_instrument_auto(setup, tmp_path, capsys):
    lib, files, template = setup
    out = tmp_path / "auto.json"
    args = ["--template", str(template), "--spectrum", *map(str, files),
            "--out", str(out), "--instrument", "auto", "--instruments-dir", str(lib.root)]
    # Nadie declara cómo reconocer sus ficheros: falla con un mensaje claro.
    assert cli.main(args) == 1
    assert "no instrument recognizes" in capsys.readouterr().err
    profile = lib.get("Lab B")
    profile.match_text = ["Sample: FeX"]
    lib.save(profile)
    assert cli.main(args) == 0
    payload = json.loads(out.read_text())
    assert payload["instrument"] == "Lab B"
    assert [r["calibration"]["date"] for r in payload["results"]] == ["2025-01-01", "2025-06-01"]
    assert "Equipo: Lab B" in capsys.readouterr().out
    # Un espectro suelto también.
    assert cli.main([*args[:2], "--spectrum", str(files[1]), "--out", str(tmp_path / "1.json"),
                     "--instrument", "auto", "--instruments-dir", str(lib.root), "--quiet"]) == 0
    single = json.loads((tmp_path / "1.json").read_text())
    assert single["calibration"]["instrument"] == "Lab B"


def test_cli_latest_rule(setup, tmp_path, capsys):
    lib, files, template = setup
    prof = lib.get("Lab B"); prof.calibration_rule = "latest"; lib.save(prof)
    out = tmp_path / "o.json"
    assert cli.main(["--template", str(template), "--spectrum", str(files[0]),
                     "--out", str(out), "--instrument", "Lab B",
                     "--instruments-dir", str(lib.root)]) == 0
    cal = json.loads(out.read_text())["calibration"]
    assert cal["calibration_date"] == "2025-06-01" and cal["calibration_rule"] == "latest"
    assert "la más reciente" in capsys.readouterr().out
