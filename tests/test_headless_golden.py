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
#
# Recalibrados de nuevo (nivel 5 de la revisión de NORMOS): el doblado pasó de
# interpolación subcanal LINEAL a CÚBICA. La lineal es un filtro paso bajo que
# ensanchaba las líneas, así que Γ baja en los cuatro casos (−6·10⁻⁵ siderita,
# −4·10⁻⁴ jarosita, −9·10⁻⁴ αFe, −2·10⁻³ hematita) y `depth` sube compensando
# (el área se conserva). δ/BHF/ΔEQ no se mueven. χ²red sube un 2-4 % porque la
# interpolación lineal también suavizaba el RUIDO, deprimiendo el χ² de forma
# artificial. El tamaño del cambio escala como f(1−f) con f la parte
# fraccionaria del canal emparejado, y estos espectros tienen f ≈ 0.005–0.02:
# con f = 0.5 el sesgo de Γ llegaba al 10 % (ver tests/test_folding_interp.py).
#
# Y una tercera vez, al dejar de recortar 2 canales por sistema: el espectro
# doblado pasa de N/2−2 a N/2 puntos (el recorte es ahora adaptativo y solo
# actúa sobre canales muertos). Todos los parámetros se mueven ≤2·10⁻⁴.
GOLDEN = {
    "alphaFe": {
        "template": "template_alphaFe.json",
        "spectrum": "hierro_metalico_alphaFe.adt",
        "values": {
            "baseline": 0.999670,
            "s1_delta": -0.110082,
            "s1_bhf": 33.045508,
            "s1_gamma1": 0.278451,
            "s1_depth": 0.0148980,
        },
        "red_chi2": 1.16547,
    },
    "hematita": {
        "template": "template_hematita.json",
        "spectrum": "hematita_Fe2O3.adt",
        "values": {
            "baseline": 1.000005,
            "s1_delta": 0.261297,
            "s1_quad": -0.199285,
            "s1_bhf": 51.581385,
            "s1_gamma1": 0.318473,
            "s1_depth": 0.0139540,
        },
        "red_chi2": 1.05441,
    },
    "siderita": {
        "template": "template_siderita.json",
        "spectrum": "siderita_FeCO3.adt",
        "values": {
            "baseline": 0.999557,
            "s1_delta": 1.121573,
            "s1_quad": 1.798351,
            "s1_gamma1": 0.337954,
            "s1_depth": 0.045017,
        },
        # ±ΔEQ produce espectros idénticos en un doblete sin BHF; solo verificamos |quad|.
        "sign_invariant": {"s1_quad"},
        "red_chi2": 0.87808,
    },
    "jarosita": {
        "template": "template_jarosita.json",
        "spectrum_dir": "public",
        "spectrum": "jarosita_KFe3SO4.adt",
        "values": {
            "baseline": 0.999846,
            "s1_delta": 0.260189,
            "s1_bhf": 30.596476,
            "s1_quad": -0.341139,
            "s1_gamma1": 0.318113,
            "s1_depth": 0.012996,
        },
        "red_chi2": 0.90319,
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
