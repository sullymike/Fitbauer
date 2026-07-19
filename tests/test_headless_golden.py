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
# Recalibrados en v4.17.2: chi2_for_center pasó a interpolación subcanal con
# exclusión de bordes, el centro detectado se mueve ≤0.16 canales y con él
# Γ/depth/χ² en la 3ª cifra; δ/BHF/ΔEQ no cambian a 1e-4.
GOLDEN = {
    "alphaFe": {
        "template": "template_alphaFe.json",
        "spectrum": "hierro_metalico_alphaFe.adt",
        "values": {
            "baseline": 0.999685,
            "s1_delta": -0.110077,
            "s1_bhf": 33.0454,
            "s1_gamma1": 0.279147,
            "s1_depth": 0.0148640,
        },
        "red_chi2": 1.14420,
    },
    "hematita": {
        "template": "template_hematita.json",
        "spectrum": "hematita_Fe2O3.adt",
        "values": {
            "baseline": 1.00002,
            "s1_delta": 0.261288,
            "s1_quad": -0.199261,
            "s1_bhf": 51.5812,
            "s1_gamma1": 0.320721,
            "s1_depth": 0.0138880,
        },
        "red_chi2": 1.02264,
    },
    "siderita": {
        "template": "template_siderita.json",
        "spectrum": "siderita_FeCO3.adt",
        "values": {
            "baseline": 0.999558,
            "s1_delta": 1.12157,
            "s1_quad": 1.79836,
            "s1_gamma1": 0.338051,
            "s1_depth": 0.0450120,
        },
        # ±ΔEQ produce espectros idénticos en un doblete sin BHF; solo verificamos |quad|.
        "sign_invariant": {"s1_quad"},
        "red_chi2": 0.88200,
    },
    "jarosita": {
        "template": "template_jarosita.json",
        "spectrum_dir": "public",
        "spectrum": "jarosita_KFe3SO4.adt",
        "values": {
            "baseline": 0.999856,
            "s1_delta": 0.260191,
            "s1_bhf": 30.5965,
            "s1_quad": -0.341146,
            "s1_gamma1": 0.318761,
            "s1_depth": 0.0129840,
        },
        "red_chi2": 0.87116,
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
    sign_invariant = spec.get("sign_invariant", set())
    for key, expected in spec["values"].items():
        assert key in values, f"falta {key}"
        actual = values[key]
        if key in sign_invariant:
            actual, expected = abs(actual), abs(expected)
        assert actual == pytest.approx(expected, rel=2e-4, abs=2e-4), (
            f"{name}.{key}: {values[key]} != {expected}")
    assert result["stats"]["red_chi2"] == pytest.approx(spec["red_chi2"], rel=5e-3)
