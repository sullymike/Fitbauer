"""Golden regression del CLI headless (core.session a través de mossbauer_fit_cli).

``core.fit_engine.fit_discrete`` es determinista (semilla fija 12345), así que el
ajuste de un espectro+plantilla dados debe reproducir siempre los mismos valores.
Estos baselines fijan la física esperada de α-Fe y hematita y protegen contra
regresiones numéricas en la extracción headless.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mossbauer_fit_cli import fit_spectrum  # noqa: E402

DATA = ROOT / "data_sample"
DATA_PUBLIC = ROOT / "data_sample" / "public"

# Baselines registrados con la implementación headless verificada.
GOLDEN = {
    "alphaFe": {
        "template": "template_alphaFe.json",
        "spectrum": "hierro_metalico_alphaFe.adt",
        "values": {
            "baseline": 0.999748,
            "s1_delta": -0.110049,
            "s1_bhf": 33.0446,
            "s1_gamma1": 0.287096,
            "s1_depth": 0.0145671,
        },
        "red_chi2": 0.97175,
    },
    "hematita": {
        "template": "template_hematita.json",
        "spectrum": "hematita_Fe2O3.adt",
        "values": {
            "baseline": 1.00002,
            "s1_delta": 0.261291,
            "s1_quad": -0.199276,
            "s1_bhf": 51.5813,
            "s1_gamma1": 0.320071,
            "s1_depth": 0.0139081,
        },
        "red_chi2": 1.03455,
    },
    "siderita": {
        "template": "template_siderita.json",
        "spectrum": "siderita_FeCO3.adt",
        "values": {
            "baseline": 0.999557,
            "s1_delta": 1.12156,
            "s1_quad": 1.79830,
            "s1_gamma1": 0.339687,
            "s1_depth": 0.0448438,
        },
        "red_chi2": 0.84981,
    },
    "jarosita": {
        "template": "template_jarosita.json",
        "spectrum_dir": "public",
        "spectrum": "jarosita_KFe3SO4.adt",
        "values": {
            "baseline": 0.999857,
            "s1_delta": 0.260198,
            "s1_bhf": 30.5965,
            "s1_quad": -0.341154,
            "s1_gamma1": 0.319105,
            "s1_depth": 0.0129736,
        },
        "red_chi2": 0.86495,
    },
}


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_cli_golden_values(name, tmp_path):
    spec = GOLDEN[name]
    spectrum_dir = DATA / spec.get("spectrum_dir", "")
    session = fit_spectrum(DATA / spec["template"], spectrum_dir / spec["spectrum"],
                           tmp_path / f"{name}.json")
    result = session["batch_fit_result"]
    values = result["values"]
    for key, expected in spec["values"].items():
        assert key in values, f"falta {key}"
        assert values[key] == pytest.approx(expected, rel=2e-4, abs=2e-4), (
            f"{name}.{key}: {values[key]} != {expected}")
    assert result["stats"]["red_chi2"] == pytest.approx(spec["red_chi2"], rel=5e-3)
