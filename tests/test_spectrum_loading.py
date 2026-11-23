"""Carga de espectros sin GUI (core.spectrum_loading): preparación y prioridad
de calibraciones, fuente única de la ventana, la serie y la sesión sin GUI."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pytest

from core.constants import convert_vmax
from core.instruments import CalibrationRecord, InstrumentLibrary, InstrumentProfile
from core.session import HeadlessSession
from core.spectrum_loading import (
    Acquisition, calibration_after_load, calibration_pattern, calibration_vmax,
    missing_calibration_reason, open_spectrum, prepare_spectrum,
)

DATA = Path(__file__).resolve().parents[1] / "data_sample"


def _counts_file(tmp_path, name="m.dat", header="Date: 2025-03-14\n"):
    c = np.random.default_rng(1).poisson(1e4, 256)
    p = tmp_path / name
    p.write_text(header + "\n".join(str(x) for x in c))
    return p


def _lib(tmp_path):
    lib = InstrumentLibrary(tmp_path / "lib")
    lib.save(InstrumentProfile(name="Lab"))
    lib.add_calibration("Lab", CalibrationRecord(date=dt.date(2025, 1, 10), vmax=10.0,
                                                 sextet_pattern="legacy", isomer_shift=-0.11))
    return lib


@pytest.mark.parametrize("acq", [Acquisition(), Acquisition(reverse=True),
                                 Acquisition(fold_mode="two_branches"),
                                 Acquisition(fold_mode="single_sweep"),
                                 Acquisition(drive_form="sine")])
def test_prepare_matches_headless(acq):
    """La preparación es la misma que la de la sesión sin GUI (y el CLI)."""
    path = DATA / "calibration.adt"
    s = HeadlessSession()
    s.model.drive_form, s.model.fold_mode = acq.drive_form, acq.fold_mode
    s.model.reverse_velocity = acq.reverse
    s.load_ws5(path, vmax=6.0)
    prep = prepare_spectrum(s.spectrum.counts, acq, 6.0)
    assert prep.center == s.spectrum.center
    np.testing.assert_array_equal(prep.y, s.spectrum.y_data)
    np.testing.assert_array_equal(prep.sigma, s.spectrum.sigma)
    np.testing.assert_array_equal(prep.velocity, s._velocity())
    assert prepare_spectrum(s.spectrum.counts, acq, None).velocity is None


def test_calibration_pattern_and_vmax():
    assert calibration_pattern(None) is None
    assert calibration_pattern({"source": "embedded"}) is None
    assert calibration_pattern({"source": "local"}) == "legacy"        # pre-v5.2.5
    assert calibration_pattern({"source": "web_api"}) == "normos"
    assert calibration_pattern({"source": "local", "sextet_pattern": "normos"}) == "normos"
    info = {"source": "local", "velocity_calibrated": 6.05}
    assert calibration_vmax(info, "normos") == convert_vmax(6.05, "legacy", "normos")
    assert calibration_vmax(info, "legacy") == 6.05
    assert calibration_vmax({"source": "embedded", "velocity_calibrated": 6.2}, "legacy") == 6.2
    assert calibration_vmax({"source": "local", "velocity_calibrated": ""}, "normos") is None
    assert calibration_vmax(None, "normos") is None


def test_open_with_instrument_and_priority(tmp_path):
    lib = _lib(tmp_path)
    path = _counts_file(tmp_path)
    fixed = {"source": "local", "velocity_calibrated": 6.0, "isomer_shift": -0.1}
    # Sin equipo: se mantiene la fijada.
    plain = open_spectrum(path)
    assert plain.choice is None and plain.calibration is None
    assert calibration_after_load(fixed, plain) is fixed
    # Con equipo y calibración aplicable: la del equipo.
    opened = open_spectrum(path, library=lib, instrument="Lab")
    assert opened.calibration["source"] == "instrument"
    assert opened.calibration["measurement_date"] == "2025-03-14"
    assert calibration_after_load(fixed, opened) is opened.calibration
    # Sin calibración aplicable (medida anterior): la fijada, con su motivo.
    old = open_spectrum(_counts_file(tmp_path, "o.dat", "Date: 2024-01-01\n"),
                        library=lib, instrument="Lab")
    assert old.calibration is None and missing_calibration_reason(old.choice) == "none_before"
    assert calibration_after_load(fixed, old) is fixed
    # Los tres motivos de «sin calibración».
    from core.instruments import CalibrationChoice
    assert missing_calibration_reason(CalibrationChoice(None, rule="latest")) == "none"
    assert missing_calibration_reason(CalibrationChoice(None, rule="manual")) == "none"
    assert missing_calibration_reason(CalibrationChoice(None)) == "no_date"


def test_velocity_file_brings_its_own_calibration(tmp_path):
    p = tmp_path / "v.csv"
    v = np.linspace(-6.2, 6.2, 101)
    p.write_text("\n".join(f"{x:.5f}\t{1 - 0.01 * np.exp(-x * x):.6f}" for x in v))
    opened = open_spectrum(p, library=_lib(tmp_path), instrument="Lab")
    assert opened.has_velocity_axis and opened.choice is None
    assert opened.file_vmax == pytest.approx(6.2)
    info = calibration_after_load({"source": "local", "isomer_shift": -0.1,
                                   "velocity_calibrated": 6.0}, opened)
    assert info["source"] == "embedded" and info["isomer_shift"] == -0.1
    assert calibration_vmax(info, "legacy") == pytest.approx(6.2)


def test_open_rejects_channel_data_that_are_not_counts(tmp_path):
    """Por canales solo valen cuentas (una transmisión por canal no se dobla)."""
    p = tmp_path / "t.dat"
    p.write_text("\n".join(f"{1 - 0.01 * np.sin(i):.6f}" for i in range(256)))
    with pytest.raises(ValueError):
        open_spectrum(p)
