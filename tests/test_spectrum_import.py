"""Lector genérico de espectros (core/spectrum_import.py).

Los ficheros son sintéticos y cubren disposiciones típicas de distintos
equipos y programas, sin depender de ninguno concreto.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.folding import read_ws5_counts
from core.spectrum_import import (
    ImportHints, parse_spectrum_text, read_spectrum_file,
)

ROOT = Path(__file__).resolve().parents[1]
RNG = np.random.default_rng(1234)


def _doublet(v: np.ndarray, depth: float = 0.08) -> np.ndarray:
    """Transmisión de un doblete (δ = 0.4, ΔEQ = 1.0, Γ = 0.3 mm/s)."""
    g = 0.15 ** 2
    a = depth * (g / ((v - 0.9) ** 2 + g) + g / ((v + 0.1) ** 2 + g))
    return 1.0 - a


def _counts(n: int = 512, base: float = 2e5) -> np.ndarray:
    """Cuentas crudas de un barrido triangular (dos ramas especulares)."""
    half = np.linspace(-6, 6, n // 2)
    v = np.concatenate([half, half[::-1]])
    return RNG.poisson(base * _doublet(v)).astype(float)


def _col(values) -> str:
    return "\n".join(f"{x:.0f}" for x in values)


# ── Bloque de datos: cabeceras y pies ─────────────────────────────────────────

def test_header_and_footer_with_numbers_are_excluded():
    c = _counts()
    text = ("Sample: FeCl3 in THF\nTemperature: 80 K\nDate: 2025-03-14\n"
            "Channels 512\n\n" + _col(c) + "\n\nTotal counts: 123456789\nEnd 1 2\n")
    r = parse_spectrum_text(text)
    assert r.x_kind == "channel" and r.y_kind == "counts"
    np.testing.assert_array_equal(r.y, c)
    assert r.data_start == 5 and r.data_end == 5 + c.size
    assert r.metadata["Sample"] == "FeCl3 in THF"
    assert r.metadata["Temperature"] == "80 K"
    assert r.metadata["Total counts"] == "123456789"
    assert "2025-03-14" in r.dates
    assert r.sigma_source == "poisson"


def test_mca_style_sections():
    """Secciones ``$KEY:`` con rango de canales antes de las cuentas."""
    c = _counts(1024)
    text = ("$SPEC_ID:\nalpha-Fe foil\n$DATE_MEA:\n03/15/2025 10:00:00\n"
            "$DATA:\n0 1023\n" + _col(c) + "\n$ROI:\n0\n$PRESETS:\nNone\n")
    r = parse_spectrum_text(text)
    np.testing.assert_array_equal(r.y, c)
    assert "03/15/2025" in r.dates


def test_leading_channel_count_is_header():
    c = _counts(256)
    r = parse_spectrum_text("256\n" + _col(c))
    np.testing.assert_array_equal(r.y, c)
    assert r.data_start == 1


def test_no_data_raises():
    with pytest.raises(ValueError):
        parse_spectrum_text("only text\nno numbers here\n")


def test_too_few_values_raises():
    with pytest.raises(ValueError):
        parse_spectrum_text("1\n2\n3\n")


# ── Separadores y coma decimal ───────────────────────────────────────────────

def test_channel_counts_csv_with_header():
    c = _counts()
    text = "Channel,Counts\n" + "\n".join(f"{i},{x:.0f}" for i, x in enumerate(c))
    r = parse_spectrum_text(text)
    assert r.columns == ("channel", "y") and r.separator == "comma"
    np.testing.assert_array_equal(r.y, c)
    assert r.x[0] == 0


@pytest.mark.parametrize("sep", [";", "\t", "   "])
def test_decimal_comma(sep):
    v = np.linspace(-4, 4, 200)
    t = _doublet(v)
    text = "Velocidad;Transmisión\n" + "\n".join(
        f"{a:.4f}{sep}{b:.6f}".replace(".", ",") for a, b in zip(v, t))
    r = parse_spectrum_text(text)
    assert r.decimal == "," and r.x_kind == "velocity"
    np.testing.assert_allclose(r.x, np.round(v, 4))
    np.testing.assert_allclose(r.y, np.round(t, 6))


def test_fortran_exponent():
    v = np.linspace(-4, 4, 100)
    t = _doublet(v)
    text = "\n".join(f"{a:.6E}  {b:.6E}".replace("E", "D") for a, b in zip(v, t))
    r = parse_spectrum_text(text)
    np.testing.assert_allclose(r.y, t, rtol=1e-6)


# ── Varias cuentas por línea ─────────────────────────────────────────────────

def test_row_major_with_channel_index():
    c = _counts()
    rows = [f"{i:5d}: " + " ".join(f"{x:.0f}" for x in c[i:i + 8])
            for i in range(0, c.size, 8)]
    r = parse_spectrum_text("\n".join(rows).replace(":", ""))
    assert r.row_major and r.x_kind == "channel"
    np.testing.assert_array_equal(r.y, c)
    assert r.x[0] == 0 and r.x[-1] == c.size - 1


def test_row_major_without_index():
    c = _counts()
    rows = [" ".join(f"{x:.0f}" for x in c[i:i + 10]) for i in range(0, 510, 10)]
    r = parse_spectrum_text("header line\n" + "\n".join(rows))
    assert r.row_major
    np.testing.assert_array_equal(r.y, c[:510])


# ── Tipos de intensidad ──────────────────────────────────────────────────────

def _velocity_file(y, v=None, fmt="{:.6f}"):
    v = np.linspace(-4, 4, 256) if v is None else v
    return "v (mm/s)  I\n" + "\n".join(f"{a:.4f} " + fmt.format(b) for a, b in zip(v, y))


def test_absorption_percent_is_inverted():
    v = np.linspace(-4, 4, 256)
    a = 100 * (1 - _doublet(v))
    r = parse_spectrum_text(_velocity_file(a, v))
    assert r.y_kind == "absorption_percent"
    t, s = r.transmission()
    np.testing.assert_allclose(t, _doublet(v), atol=1e-8)
    assert r.sigma_source == "estimated" and "sigma_estimated" in r.warnings


def test_absorption_fraction_warns_units():
    v = np.linspace(-4, 4, 256)
    r = parse_spectrum_text(_velocity_file(1 - _doublet(v), v))
    assert r.y_kind == "absorption"
    assert "absorption_units_ambiguous" in r.warnings


def test_transmission_and_percent():
    v = np.linspace(-4, 4, 256)
    t = _doublet(v) + RNG.normal(0, 1e-3, v.size)
    assert parse_spectrum_text(_velocity_file(t, v)).y_kind == "transmission"
    r = parse_spectrum_text(_velocity_file(100 * t, v))
    assert r.y_kind == "transmission_percent"
    np.testing.assert_allclose(r.transmission()[0], np.round(100 * t, 6) / 100)


def test_transmission_deviation():
    v = np.linspace(-4, 4, 256)
    r = parse_spectrum_text(_velocity_file(_doublet(v) - 1.0, v))
    assert r.y_kind == "transmission_deviation"
    np.testing.assert_allclose(r.transmission()[0], _doublet(v), atol=1e-6)


def test_transmission_deviation_percent_wmoss():
    """WMOSS exporta «% absorbance» = 100·(T − 1): negativo en los picos."""
    v = np.linspace(-6, 6, 512)
    t = _doublet(v)
    r = parse_spectrum_text(_velocity_file(100 * (t - 1.0), v, "{:.3f}"))
    assert r.y_kind == "transmission_deviation_percent"
    np.testing.assert_allclose(r.transmission()[0], t, atol=1e-5)


def test_offset_subspectrum_trace_is_not_counts():
    # Traza de un sitio de WMOSS: línea base en −1.6 %, picos hasta −4.3 %.
    v = np.linspace(-6, 6, 256)
    y = -1.6 - 2.7 * 0.04 / ((v - 1.0) ** 2 + 0.04)
    r = parse_spectrum_text("\n".join(f"{a:.5f}\t{b:.5f}" for a, b in zip(v, y)))
    assert r.y_kind == "transmission_deviation_percent"
    assert r.transmission()[0].max() == pytest.approx(0.984, abs=1e-3)


def test_ws5_metadata_excludes_data_block():
    text = ('<?xml version="1.0"?>\r\n<wissoft version="1.1">\r\n<comment>http://x</comment>\r\n'
            '<data channels="4" time="0">\r\n10\r\n11\r\n12\r\n13\r\n</data>\r\n</wissoft>\r\n')
    r = parse_spectrum_text(text)
    assert r.y.size == 4 and "data" not in r.metadata
    assert r.metadata["comment"] == "http://x" and r.metadata["data.channels"] == "4"


def test_estimated_noise_is_close_to_true():
    v = np.linspace(-6, 6, 512)
    t = _doublet(v) + RNG.normal(0, 2e-3, v.size)
    r = parse_spectrum_text(_velocity_file(t, v, "{:.8f}"))
    _, s = r.transmission()
    assert 1.6e-3 < s[0] < 2.4e-3


def test_sigma_column():
    v = np.linspace(-4, 4, 256)
    t = _doublet(v)
    text = "\n".join(f"{a:.4f} {b:.6f} 0.0015" for a, b in zip(v, t))
    r = parse_spectrum_text(text)
    assert r.columns == ("velocity", "y", "sigma") and r.sigma_source == "column"
    np.testing.assert_allclose(r.transmission()[1], 0.0015)


def test_counts_transmission_normalised():
    c = _counts()
    t, s = parse_spectrum_text(_col(c)).transmission()
    assert abs(np.percentile(t, 90) - 1.0) < 1e-12
    np.testing.assert_allclose(s, np.sqrt(c) / np.percentile(c, 90))


# ── Eje de velocidad ─────────────────────────────────────────────────────────

def test_two_velocity_branches_detected():
    half = np.linspace(-5, 5, 256)
    v = np.concatenate([half, half[::-1]])
    c = RNG.poisson(1e5 * _doublet(v))
    r = parse_spectrum_text("\n".join(f"{a:.5f}\t{b}" for a, b in zip(v, c)))
    assert r.x_kind == "velocity" and r.velocity_turning_points == 1
    assert r.y_kind == "counts"


# ── Hints (perfil de importación) ────────────────────────────────────────────

def test_hints_override_and_roundtrip():
    v = np.linspace(-4, 4, 256)
    a = 1 - _doublet(v)
    text = _velocity_file(a, v)
    auto = parse_spectrum_text(text)
    h = ImportHints.from_dict(auto.hints().to_dict())
    assert h == auto.hints()
    forced = parse_spectrum_text(text, ImportHints(y_kind="absorption_percent"))
    assert forced.y_kind == "absorption_percent"
    assert "absorption_units_ambiguous" not in forced.warnings
    np.testing.assert_allclose(forced.transmission()[0], 1 - a / 100)


def test_hints_columns_and_range():
    v = np.linspace(-4, 4, 100)
    t = _doublet(v)
    lines = ["# junk"] + [f"{i} {a:.4f} {b:.6f}" for i, (a, b) in enumerate(zip(v, t))] + ["7 7 7"]
    text = "\n".join(lines)
    r = parse_spectrum_text(text, ImportHints(data_start=1, data_end=101,
                                              columns=("ignore", "velocity", "y")))
    assert r.x_kind == "velocity" and r.y.size == 100
    with pytest.raises(ValueError):
        parse_spectrum_text(text, ImportHints(columns=("velocity", "y")))


# ── Ficheros reales y codificaciones ─────────────────────────────────────────

def test_ws5_xml():
    c = _counts()
    text = ('<?xml version="1.0"?>\n<wissoft version="1.1">\n<comment>lab 2</comment>\n'
            f'<data channels="{c.size}" time="0">\n{_col(c)}\n</data>\n</wissoft>\n')
    r = parse_spectrum_text(text)
    assert r.source_format == "ws5"
    np.testing.assert_array_equal(r.y, c)
    assert r.metadata["data.channels"] == str(c.size)
    assert r.metadata["comment"] == "lab 2"


@pytest.mark.parametrize("path", sorted((ROOT / "data_sample").rglob("*.adt")),
                         ids=lambda p: p.name)
def test_sample_adt_same_as_legacy_reader(path):
    r = read_spectrum_file(path)
    np.testing.assert_array_equal(r.y, read_ws5_counts(path))


def test_sample_velocity_file():
    r = read_spectrum_file(ROOT / "data_sample/public/alphaFe_calibracion_ESRF.dat")
    assert r.x_kind == "velocity" and r.y.size == 512 and r.data_start == 1


@pytest.mark.parametrize("encoding", ["latin-1", "utf-16"])
def test_encodings(tmp_path, encoding):
    c = _counts()
    p = tmp_path / "s.txt"
    p.write_text("Température: 25 °C\n" + _col(c), encoding=encoding)
    r = read_spectrum_file(p)
    np.testing.assert_array_equal(r.y, c)
    assert r.metadata["Température"] == "25 °C"
