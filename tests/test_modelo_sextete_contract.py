"""Verifica los contratos numéricos de ``docs/modelo_sextete.md``.

Ese documento es la especificación con la que otra implementación (la web) debe
reproducir un ajuste idéntico, y él mismo pide mantener sus vectores como test de
regresión. Sin este test el documento envejece en silencio: se detectó ya una
deriva (la tabla de §9 se había generado con Γ=0.300 pero declaraba 0.150).

Si un cambio de física hace fallar estas comprobaciones, hay que decidir
explícitamente si el que se corrige es el código o el documento — nunca dejarlos
divergir.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import folding as F  # noqa: E402
from core import physics as p  # noqa: E402
from core.constants import LINE_POS_33T  # noqa: E402

DOC = Path(__file__).resolve().parents[1] / "docs" / "modelo_sextete.md"

# §7.7 — Contrato numérico de folding.
COUNTS = np.array([100, 90, 70, 95, 98, 60, 88, 105], dtype=float)

# §9 — Vector de referencia del sextete (δ=0, ΔEQ=0, BHF=33, Γ₁=0.300 HWHM,
# Γ₂rel=Γ₃rel=1, depth=0.02, pesos 3:2:1:1:2:3).
REF_V = np.array([-5.3285, -3.0835, -0.8385, 0.0, 0.8385, 3.0835, 5.3285])
REF_A = np.array([0.060236, 0.040427, 0.020497, 0.001524,
                  0.020497, 0.040427, 0.060236])


def test_documento_presente():
    assert DOC.exists(), "falta docs/modelo_sextete.md"


def test_posiciones_de_las_seis_lineas():
    """§9: patrón de α-Fe a 33 T, sin desplazamiento ni cuadrupolo."""
    esperado = np.array([-5.3285, -3.0835, -0.8385, 0.8385, 3.0835, 5.3285])
    np.testing.assert_allclose(LINE_POS_33T, esperado, atol=1e-6)
    np.testing.assert_allclose(
        p.sextet_line_positions(0.0, 0.0, 33.0), esperado, atol=1e-6)


def test_absorcion_de_referencia():
    """§9: el modelo directo del sextete, a la tolerancia que fija el documento."""
    obtenido = p.sextet_absorption(REF_V, 0.0, 0.0, 33.0,
                                   0.300, 1.0, 1.0, 0.02, 3, 2, 1)
    np.testing.assert_allclose(obtenido, REF_A, atol=1e-6)


def test_gamma_declarada_coincide_con_la_tabla():
    """La Γ que declara §9 debe ser la que genera su tabla, no otra.

    Es la deriva concreta que tenía el documento al integrarlo.
    """
    texto = DOC.read_text(encoding="utf-8")
    assert "`Γ₁=0.300`" in texto, "§9 declara una Γ distinta de la que usa su tabla"


@pytest.mark.parametrize("center, esperado", [
    (4.5, [96.5, 65.0, 89.0, 102.5]),
    (4.30, [93.7, 70.8, 87.2, 101.8]),
])
def test_doblado(center, esperado):
    """§7.3–§7.4: doblado a centro semientero y fraccionario (interpolación)."""
    folded, _pares = F.fold_integer_or_half(COUNTS, center)
    np.testing.assert_allclose(folded, esperado, atol=1e-6)


def test_normalizacion_y_sigma():
    """§7.5: percentil 90, base ≈ 1 y ruido Poisson normalizado."""
    folded, sigma, y, norm = F.fold_and_normalize(COUNTS, 4.5, 1)
    assert norm == pytest.approx(100.7, abs=1e-4)
    np.testing.assert_allclose(
        y, [0.958292, 0.645482, 0.883813, 1.017875], atol=1e-6)
    np.testing.assert_allclose(
        sigma, [0.068979, 0.056612, 0.066245, 0.071091], atol=1e-6)


def test_eje_de_velocidad():
    """§7.6: el eje conserva la escala, recortando los mismos bordes que los datos."""
    np.testing.assert_allclose(
        F.velocity_axis(8, 4.0, 4, 1),
        [-4.0, -1.333333, 1.333333, 4.0], atol=1e-6)
