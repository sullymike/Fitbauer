"""Tests unitarios para core.folding.load_velocity_csv."""
from __future__ import annotations

import textwrap

import numpy as np
import pytest

from core.folding import load_velocity_csv, _CSV_MAX_COUNT


# ── Helpers ────────────────────────────────────────────────────────────────────

def _write_csv(tmp_path, content: str, filename: str = "spectrum.csv"):
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _make_rows(n: int = 20, vmax: float = 10.0) -> list[tuple[float, float]]:
    """Genera n filas (velocidad, cuentas brutas) simétricas."""
    velocities = np.linspace(-vmax, vmax, n)
    counts = np.random.default_rng(42).integers(1_900_000, 2_100_000, size=n).astype(float)
    return list(zip(velocities.tolist(), counts.tolist()))


# ── Tests: formato CSV con separador coma ─────────────────────────────────────

def test_comma_separated_raw_counts(tmp_path):
    rows = _make_rows(30)
    lines = "\n".join(f"{v:.4f},{c:.1f}" for v, c in rows)
    p = _write_csv(tmp_path, lines)
    result = load_velocity_csv(p)

    assert result["source"] == "csv"
    assert isinstance(result["velocity"], np.ndarray)
    assert isinstance(result["y"], np.ndarray)
    assert result["velocity"].size == 30
    assert result["y"].size == 30


def test_comma_separated_with_header(tmp_path):
    content = """\
        # velocity_mm_s, counts
        -5.0, 2000000
        -4.5, 1990000
        -4.0, 1980000
        -3.5, 1970000
        -3.0, 1960000
        -2.5, 1950000
        -2.0, 1940000
        -1.5, 1930000
        -1.0, 1920000
        -0.5, 1910000
        0.0,  1900000
        0.5,  1910000
        1.0,  1920000
        1.5,  1930000
        2.0,  1940000
    """
    p = _write_csv(tmp_path, content)
    result = load_velocity_csv(p)
    assert result["velocity"].size == 15
    # Velocidades deben estar ordenadas ascendentemente
    assert np.all(np.diff(result["velocity"]) >= 0)


# ── Tests: separador tabulador / espacio ──────────────────────────────────────

def test_tab_separated(tmp_path):
    rows = _make_rows(20)
    lines = "\n".join(f"{v:.4f}\t{c:.1f}" for v, c in rows)
    p = _write_csv(tmp_path, lines, "spectrum.txt")
    result = load_velocity_csv(p)
    assert result["velocity"].size == 20


def test_space_separated(tmp_path):
    rows = _make_rows(15)
    lines = "\n".join(f"{v:.4f}  {c:.1f}" for v, c in rows)
    p = _write_csv(tmp_path, lines, "spectrum.dat")
    result = load_velocity_csv(p)
    assert result["velocity"].size == 15


# ── Tests: transmisión normalizada → conversión a cuentas ─────────────────────

def test_normalized_transmission_converted(tmp_path):
    """Valores ≤ 1 deben multiplicarse por _CSV_MAX_COUNT y redondearse."""
    content = "\n".join(
        f"{v:.2f},{t:.6f}"
        for v, t in zip(
            np.linspace(-5, 5, 20),
            np.linspace(0.95, 1.0, 20),
        )
    )
    p = _write_csv(tmp_path, content)
    result = load_velocity_csv(p)
    # Todos los valores de y deben ser enteros (redondeados) >= 1_900_000
    assert np.all(result["y"] >= 1_900_000)
    assert np.all(result["y"] == np.round(result["y"]))


def test_raw_counts_not_converted(tmp_path):
    """Valores > 1 se pasan sin escalar."""
    rows = _make_rows(20)
    lines = "\n".join(f"{v:.4f},{c:.1f}" for v, c in rows)
    p = _write_csv(tmp_path, lines)
    result = load_velocity_csv(p)
    # Las cuentas originales son ~2_000_000; no deben escalar a _CSV_MAX_COUNT²
    assert np.all(result["y"] > 1.0)
    # Los valores deben coincidir con los originales
    expected = np.array([c for _, c in rows])
    # Reordenamos por velocidad, igual que hace el loader
    order = np.argsort([v for v, _ in rows])
    expected = expected[order]
    np.testing.assert_array_almost_equal(result["y"], expected)


# ── Tests: ordenación ascendente de velocidades ──────────────────────────────

def test_velocity_sorted_ascending(tmp_path):
    """El loader debe devolver velocidades en orden ascendente."""
    rows = _make_rows(20)
    # Mezclar el orden intencionalmente
    shuffled = rows[10:] + rows[:10]
    lines = "\n".join(f"{v:.4f},{c:.1f}" for v, c in shuffled)
    p = _write_csv(tmp_path, lines)
    result = load_velocity_csv(p)
    assert np.all(np.diff(result["velocity"]) > 0)


# ── Tests: ignorar comentarios y cabeceras textuales ─────────────────────────

def test_comment_lines_skipped(tmp_path):
    content = """\
        # Este fichero es un espectro Mössbauer
        # Columnas: velocidad (mm/s), cuentas
        velocity counts
        -5.0 2000000
        -4.0 1990000
        -3.0 1980000
        -2.0 1970000
        -1.0 1960000
        0.0 1950000
        1.0 1960000
        2.0 1970000
        3.0 1980000
        4.0 1990000
        5.0 2000000
    """
    p = _write_csv(tmp_path, content)
    result = load_velocity_csv(p)
    # Solo las filas numéricas deben contarse
    assert result["velocity"].size == 11


# ── Tests: error con menos de 10 puntos ─────────────────────────────────────

def test_raises_if_too_few_points(tmp_path):
    content = "\n".join(f"{v:.1f} {c}" for v, c in [(-1, 1000), (0, 999), (1, 1001)])
    p = _write_csv(tmp_path, content)
    with pytest.raises(ValueError, match="10"):
        load_velocity_csv(p)


def test_raises_on_empty_file(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="10"):
        load_velocity_csv(p)


def test_raises_on_only_comments(tmp_path):
    content = "# solo comentarios\n# nada más\n"
    p = _write_csv(tmp_path, content)
    with pytest.raises(ValueError, match="10"):
        load_velocity_csv(p)


# ── Tests: extensiones alternativas ──────────────────────────────────────────

@pytest.mark.parametrize("ext", [".csv", ".txt", ".dat", ".exp"])
def test_accepts_various_extensions(tmp_path, ext):
    rows = _make_rows(20)
    lines = "\n".join(f"{v:.4f},{c:.1f}" for v, c in rows)
    p = tmp_path / f"spectrum{ext}"
    p.write_text(lines, encoding="utf-8")
    result = load_velocity_csv(p)
    assert result["velocity"].size == 20


# ── Tests: valores negativos de velocidad ────────────────────────────────────

def test_negative_velocities_handled(tmp_path):
    content = "\n".join(
        f"{v:.2f},{c}"
        for v, c in zip(np.linspace(-12, 12, 25), [2_000_000] * 25)
    )
    p = _write_csv(tmp_path, content)
    result = load_velocity_csv(p)
    assert result["velocity"][0] < 0
    assert result["velocity"][-1] > 0
    assert result["velocity"].size == 25


# ── Tests: campo de resultado ─────────────────────────────────────────────────

def test_result_has_required_keys(tmp_path):
    rows = _make_rows(12)
    lines = "\n".join(f"{v:.4f},{c:.1f}" for v, c in rows)
    p = _write_csv(tmp_path, lines)
    result = load_velocity_csv(p)
    assert set(result.keys()) == {"velocity", "y", "source"}
    assert result["source"] == "csv"


# ── Tests: nuevas validaciones ────────────────────────────────────────────────

def test_exactly_10_points_accepted(tmp_path):
    """Exactamente 10 puntos válidos NO debe lanzar ValueError."""
    velocities = np.linspace(-5.0, 5.0, 10)
    counts = [2_000_000.0] * 10
    lines = "\n".join(f"{v:.4f},{c:.1f}" for v, c in zip(velocities, counts))
    p = _write_csv(tmp_path, lines)
    result = load_velocity_csv(p)
    assert result["velocity"].size == 10


def test_narrow_range_raises(tmp_path):
    """20 puntos dentro de un rango < 1 mm/s debe lanzar ValueError con 'Rango'."""
    velocities = np.linspace(-0.2, 0.3, 20)  # rango = 0.5 mm/s
    counts = [2_000_000.0] * 20
    lines = "\n".join(f"{v:.6f},{c:.1f}" for v, c in zip(velocities, counts))
    p = _write_csv(tmp_path, lines)
    with pytest.raises(ValueError, match="Rango"):
        load_velocity_csv(p)


def test_duplicate_velocities_deduplicated(tmp_path):
    """15 velocidades únicas con 5 repetidas (20 filas) → resultado con ≤ 15 puntos y diffs > 0."""
    rng = np.random.default_rng(7)
    unique_vels = np.linspace(-7.0, 7.0, 15)
    unique_counts = rng.integers(1_900_000, 2_100_000, size=15).astype(float)

    # Duplicar las primeras 5 velocidades únicas
    dup_vels = list(unique_vels) + list(unique_vels[:5])
    dup_counts = list(unique_counts) + list(unique_counts[:5])

    lines = "\n".join(f"{v:.6f},{c:.1f}" for v, c in zip(dup_vels, dup_counts))
    p = _write_csv(tmp_path, lines)
    result = load_velocity_csv(p)

    assert result["velocity"].size <= 15
    assert np.all(np.diff(result["velocity"]) > 0)
