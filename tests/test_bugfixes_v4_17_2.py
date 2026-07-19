"""Regresiones de la caza de bugs v4.17.2 (folding/E-S, distribución, sesiones, CLIs, i18n)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.folding import (  # noqa: E402
    chi2_for_center,
    find_best_integer_or_half_center,
    load_velocity_csv,
    read_normos_plt_velocity,
    read_ws5_counts,
)
from core.profile_likelihood import find_crossing  # noqa: E402
from core.session import ModelState  # noqa: E402


def _synthetic_counts(n: int, center: float, rng=None) -> np.ndarray:
    """Espectro triangular sintético con un doblete simétrico respecto a center."""
    rng = rng or np.random.default_rng(7)
    i = np.arange(1, n + 1, dtype=float)
    base = 1e6
    width = n / 60.0
    dip = 0.10 * base * (np.exp(-0.5 * ((i - (center - n / 8.0)) / width) ** 2)
                         + np.exp(-0.5 * ((i - (center + n / 8.0)) / width) ** 2))
    counts = base - dip
    return counts + rng.normal(0.0, np.sqrt(base), n)


# ── Folding / E-S ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("n", [256, 512, 1024])
def test_center_default_window_scales_with_channels(n):
    true_center = 0.5 * n + 0.25
    counts = _synthetic_counts(n, true_center)
    found = find_best_integer_or_half_center(counts)
    assert abs(found - true_center) < 0.6


def test_center_insensitive_to_dead_edge_channel():
    n = 512
    true_center = 255.6
    counts = _synthetic_counts(n, true_center)
    clean = find_best_integer_or_half_center(counts)
    dead = counts.copy()
    dead[0] = 6760.0  # canal 1 muerto, habitual en ADT reales
    shifted = find_best_integer_or_half_center(dead)
    assert abs(shifted - clean) < 0.05


def test_chi2_for_center_counts_only_valid_pairs():
    counts = _synthetic_counts(512, 256.5)
    # Candidato pegado al borde: la mayoría de pares caen fuera y NO deben
    # contar en la normalización.
    _chi2, n_valid = chi2_for_center(counts, 80.0)
    assert 0 < n_valid < counts.size // 2


def test_plt_title_with_digits_does_not_poison_vmax(tmp_path):
    velocities = np.linspace(-11.9, 11.9, 256)
    body = "\n".join(f"{v:14.6E}" for v in velocities)
    plt = tmp_path / "SPEC.PLT"
    plt.write_text("2d\nMagnetita Fe3O4 T=300K Fc211025\n" + body + "\n")
    vmax = read_normos_plt_velocity(tmp_path / "SPEC.adt")
    assert vmax == pytest.approx(11.9, abs=1e-6)


def test_csv_with_comma_decimals(tmp_path):
    f = tmp_path / "vel.csv"
    rows = [f"{-10.0 + 0.15 * i:.4f}\t{250000.0 + i:.1f}".replace(".", ",")
            for i in range(120)]
    f.write_text("\n".join(rows))
    data = load_velocity_csv(f)
    assert data["velocity"].size == 120
    assert data["velocity"][0] == pytest.approx(-10.0)
    assert float(np.min(data["y"])) >= 250000.0 - 1e-6


def test_csv_comma_as_column_separator_still_works(tmp_path):
    f = tmp_path / "vel2.csv"
    rows = [f"{-10.0 + 0.15 * i:.4f},{250000.0 + i:.1f}" for i in range(120)]
    f.write_text("\n".join(rows))
    data = load_velocity_csv(f)
    assert data["velocity"].size == 120
    assert data["velocity"][0] == pytest.approx(-10.0)


def test_truncated_ws5_skips_xml_header(tmp_path):
    counts = np.arange(100, 612, dtype=float)
    body = "\n".join(f"{c:.0f}" for c in counts)
    f = tmp_path / "trunc.ws5"
    f.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<ws5>\n<data>\n'
                 + body + "\n")  # sin </data>: descarga parcial
    read = read_ws5_counts(f)
    assert read.size == counts.size
    assert read[0] == pytest.approx(100.0)


def test_folded_velocity_data_trims_edges():
    from mossbauer_ws5 import folded_velocity_data
    sample = ROOT / "data_sample" / "hierro_metalico_alphaFe.adt"
    v, y, folded, _center, _vmax, _norm = folded_velocity_data(sample)
    n = read_ws5_counts(sample).size
    assert y.size == n // 2 - 2  # edge_trim=1 por ambos lados
    assert v.size == y.size


# ── Sesiones / estado ─────────────────────────────────────────────────────────

def test_apply_template_accepts_legacy_list_maps():
    ms = ModelState.defaults()
    ms.apply_template({
        "vars": {"s1_bhf": 30.0},
        "sextet_enabled": [True, False, True],
        "component_kind": ["Sextete", "Doblete", "Singlete"],
        "intensity_mode": ["free", "free", "free"],
    })
    assert ms.sextet_enabled[1] is True
    assert ms.sextet_enabled[3] is True
    assert ms.component_kind[3] == "Singlete"


def test_multistart_zero_survives_settings_roundtrip():
    from gui.state import UiPreferencesState
    prefs = UiPreferencesState.from_settings_dict({"multistart_n": 0})
    assert prefs.multistart_n == 0


def test_session_io_per_component_map_normalizes_lists():
    from gui.session_io import _per_component_map
    assert _per_component_map([False, True]) == {"1": False, "2": True}
    assert _per_component_map({"2": True}) == {"2": True}
    assert _per_component_map(None) == {}


# ── Distribución ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def dist_data():
    from mossbauer_distribution import build_hyperfine_distribution_kernel, parameter_grid
    rng = np.random.default_rng(11)
    v = np.linspace(-8.0, 8.0, 300)
    centers = parameter_grid(0.0, 50.0, 60)
    K = build_hyperfine_distribution_kernel(v, centers, variable="bhf", gamma=0.36)
    P = np.exp(-0.5 * ((centers - 30.0) / 2.5) ** 2)
    P /= np.trapezoid(P, centers)
    y = 1.0 - 0.10 * (K @ P) / np.max(K @ P) + rng.normal(0, 0.001, v.size)
    return v, y


@pytest.mark.parametrize("engine", ["vbf", "binomial", "fija"])
def test_distribution_engines_respect_fixed_baseline(engine, dist_data):
    from mossbauer_distribution import (
        fit_binomial_hyperfine_distribution,
        fit_fixed_hyperfine_distribution,
        fit_vbf_hyperfine_distribution,
        parameter_grid,
    )
    v, y = dist_data
    kwargs = dict(gamma=0.36, baseline=0.9, slope=0.0,
                  fit_baseline=False, fit_slope=False)
    if engine == "vbf":
        fit = fit_vbf_hyperfine_distribution(
            v, y, n_components=1, profile="Lorentziana",
            pmin=0.0, pmax=50.0, nbins=60, **kwargs)
    elif engine == "binomial":
        fit = fit_binomial_hyperfine_distribution(
            v, y, pmin=0.0, pmax=50.0, nbins=30, **kwargs)
    else:
        centers = parameter_grid(0.0, 50.0, 60)
        w = np.exp(-0.5 * ((centers - 30.0) / 2.5) ** 2)
        fit = fit_fixed_hyperfine_distribution(v, y, centers, w, **kwargs)
    assert fit.baseline == pytest.approx(0.9)
    assert fit.slope == pytest.approx(0.0)


def test_fit_discrete_restores_global_line_profile():
    from core import physics as _phys
    from core.session import HeadlessSession
    prev = (_phys.LINE_PROFILE_KIND, _phys.VOIGT_SIGMA)
    try:
        _phys.LINE_PROFILE_KIND = "Lorentziana"
        session = HeadlessSession()
        session.load_ws5(ROOT / "data_sample" / "hierro_metalico_alphaFe.adt")
        template = json.loads(
            (ROOT / "data_sample" / "template_alphaFe.json").read_text())
        state = template.get("model_state", template)
        state["line_profile"] = "Voigt"
        state["multistart_n"] = 0
        session.apply_template_model_state(state)
        session.run_fit()
        assert _phys.LINE_PROFILE_KIND == "Lorentziana"
    finally:
        _phys.LINE_PROFILE_KIND, _phys.VOIGT_SIGMA = prev


# ── i18n ──────────────────────────────────────────────────────────────────────

LOCALES = sorted(p.name for p in (ROOT / "locales").iterdir()
                 if (p / "strings.json").exists())

REQUIRED_KEYS = [
    "progress.cancel", "progress.detail_wait", "report.parameter",
    "report.value", "msg.validation_title", "msg.no_file",
    "msg.short_report_ask_pdf", "phase.component_header",
    "bhf.lcurve_hint", "bhf.lcurve_only_histogram",
]


def test_locales_have_key_parity():
    key_sets = {}
    for loc in LOCALES:
        data = json.loads((ROOT / "locales" / loc / "strings.json").read_text(encoding="utf-8"))
        key_sets[loc] = set(data) - {"_meta"}
    base = key_sets["es"]
    for loc, keys in key_sets.items():
        assert keys == base, f"claves desincronizadas en locale '{loc}'"
    for key in REQUIRED_KEYS:
        assert key in base, f"falta {key} en los locales"


# ── CLIs / utilidades ─────────────────────────────────────────────────────────

def test_cli_out_cannot_overwrite_template(tmp_path):
    from mossbauer_fit_cli import main
    template = tmp_path / "plantilla.json"
    template.write_text((ROOT / "data_sample" / "template_alphaFe.json").read_text())
    original = template.read_text()
    rc = main(["--template", str(template),
               "--spectrum", str(ROOT / "data_sample" / "hierro_metalico_alphaFe.adt"),
               "--out", str(template)])
    assert rc == 2
    assert template.read_text() == original


def test_find_crossing_empty_scan_returns_none():
    assert find_crossing(np.array([]), np.array([]), 0.0, 1.0) == (None, None)


def test_updater_prerelease_tokens():
    from mossbauer_updater import _is_prerelease_tag
    assert not _is_prerelease_tag("v4.18.0-mac")
    assert not _is_prerelease_tag("v4.18.0-stable")
    assert not _is_prerelease_tag("v4.18.0-final")
    assert _is_prerelease_tag("v4.18.0-beta.1")
    assert _is_prerelease_tag("v4.18.0-rc2")
    assert not _is_prerelease_tag("v4.18.0")
