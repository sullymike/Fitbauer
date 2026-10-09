"""Relajación de dos estados (Blume) con poblaciones desiguales.

``two_state_exchange_profile`` implementa el modelo estocástico de dos estados
de Blume (Phys. Rev. 174, 351, 1968) en forma cerrada. NORMOS-SITE tiene el
mismo modelo para la relajación de Ising (±B_hf); las poblaciones desiguales
(su ``SPN = BHF/BSAT``: un campo externo que polariza los dos estados) son
``polarization`` / ``relax_polarization``.

La referencia de estos tests es la propia ecuación de Blume resuelta
numéricamente punto a punto, ``I(v) ∝ Re[𝟙ᵀ (Z + W)⁻¹ p]``, independiente de la
forma cerrada, más las propiedades que cualquier modelo físico debe cumplir:
conservación del área, no negatividad, límites lento y rápido, e invariancia
al intercambiar los dos estados.

Nota histórica: hasta v5.1.1 la rama polarizada era una transcripción de la
rutina ``ISIRLX`` de NORMOS. Esa transcripción coincidía con este modelo para
P ≤ 0 (a 10⁻¹¹) pero con P > 0 tomaba la otra rama de la raíz compleja: el
espectro cambiaba al intercambiar los estados y aparecían regiones negativas.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.physics import _RELAX_RATE_PER_MM_S, two_state_exchange_profile

V = np.linspace(-12.0, 12.0, 4001)
GAMMA = 0.25
SPLIT = 5.3285          # línea 1/6 de un sexteto a 33 T


def _log10_nu(k_mm_s: float) -> float:
    return float(np.log10(k_mm_s * _RELAX_RATE_PER_MM_S))


def _fitbauer(k_mm_s: float, pol: float = 0.0, ca: float = -SPLIT, cb: float = SPLIT,
              v: np.ndarray = V):
    return two_state_exchange_profile(v, ca, cb, GAMMA, _log10_nu(k_mm_s), pol)


def _blume_matricial(v, ca, cb, gamma, k, pol):
    """Referencia: resuelve (Z + W) x = p en cada velocidad y suma x.

    W es la matriz de tasas de un proceso de Markov de dos estados con
    balance detallado: sale de a a tasa w_a = 2k·p_b y de b a w_b = 2k·p_a.
    """
    g = gamma / 2.0
    p = np.array([0.5 * (1.0 + pol), 0.5 * (1.0 - pol)])
    w_a, w_b = 2.0 * k * p[1], 2.0 * k * p[0]
    W = np.array([[w_a, -w_b], [-w_a, w_b]], dtype=complex)
    out = np.empty_like(v)
    for i, vi in enumerate(v):
        Z = np.diag([g + 1j * (vi - ca), g + 1j * (vi - cb)])
        out[i] = g * np.real(np.linalg.solve(Z + W, p).sum())
    return out


@pytest.mark.parametrize("k", [1e-3, 0.5, 3.0, 40.0])
@pytest.mark.parametrize("pol", [-0.9, -0.3, 0.0, 0.4, 0.9])
def test_coincide_con_la_ecuacion_matricial_de_blume(k, pol):
    v = np.linspace(-12.0, 12.0, 401)
    ref = _blume_matricial(v, -SPLIT, SPLIT, GAMMA, k, pol)
    mio = _fitbauer(k, pol, v=v)
    assert np.max(np.abs(mio - ref)) < 1e-10 * ref.max()


@pytest.mark.parametrize("k", [0.5, 3.0])
@pytest.mark.parametrize("pol", [0.4, 0.9])
def test_intercambiar_los_estados_no_cambia_el_espectro(k, pol):
    """Las etiquetas a/b son arbitrarias: (a, b, P) ≡ (b, a, −P)."""
    uno = _fitbauer(k, pol, -SPLIT, SPLIT)
    otro = _fitbauer(k, -pol, SPLIT, -SPLIT)
    assert np.max(np.abs(uno - otro)) < 1e-12 * uno.max()


@pytest.mark.parametrize("pol", [-0.6, 0.4, 0.9])
def test_limite_lento_pesa_cada_linea_por_su_poblacion(pol):
    """k → 0: el doblete estático p_a·L_a + p_b·L_b (colas incluidas)."""
    g = GAMMA / 2.0
    estatico = (0.5 * (1 + pol) * g ** 2 / ((V + SPLIT) ** 2 + g ** 2)
                + 0.5 * (1 - pol) * g ** 2 / ((V - SPLIT) ** 2 + g ** 2))
    y = _fitbauer(1e-6, pol)
    assert np.max(np.abs(y - estatico)) < 1e-4 * estatico.max()


def test_polarizacion_conserva_el_area_y_no_es_negativa():
    v = np.linspace(-60.0, 60.0, 24001)
    areas = []
    for pol in (-0.9, -0.3, 0.0, 0.3, 0.6, 0.9):
        y = _fitbauer(1.0, pol, v=v)
        assert y.min() >= 0.0
        areas.append(float(np.trapezoid(y, v)))
    assert max(areas) - min(areas) < 1e-3 * areas[0]


def test_polarizacion_cero_es_el_comportamiento_historico():
    """P=0 no cambia respecto al defecto."""
    a = _fitbauer(1.0, 0.0)
    b = two_state_exchange_profile(V, -SPLIT, SPLIT, GAMMA, _log10_nu(1.0))
    np.testing.assert_allclose(a, b, atol=0)


def test_poblaciones_desiguales_cambian_el_espectro():
    """P ≠ 0 no es degenerado con la tasa: el espectro deja de ser simétrico."""
    simetrico = _fitbauer(1.0, 0.0)
    polarizado = _fitbauer(1.0, 0.6)
    assert np.max(np.abs(simetrico - simetrico[::-1])) < 1e-9
    assert np.max(np.abs(polarizado - polarizado[::-1])) > 0.01 * polarizado.max()


def test_el_sexteto_no_se_asimetriza_con_la_polarizacion():
    """Y no debe: un sexteto con +B y −B da el MISMO espectro estático.

    La polarización cambia la mezcla dinámica (y con ella el ensanchamiento),
    pero no puede romper la simetría del sexteto, porque los dos estados entre
    los que salta son espectralmente idénticos.
    """
    from core.physics import component_absorption

    v = np.linspace(-12.0, 12.0, 2401)
    p = np.array([0.0, 0.0, 33.0, 0.28, 1.0, 1.0, 0.05, 3.0, 2.0, 1.0])
    for pol in (0.0, 0.5):
        y = component_absorption(v, "BlumeTjon", p,
                                 extras={"log10_nu": 8.5, "polarization": pol})
        assert np.max(np.abs(y - y[::-1])) < 1e-12


def test_limite_lento_es_el_doblete_estatico():
    """k → 0: dos lorentzianas en ±SPLIT, sin ensanchar."""
    lento = _fitbauer(1e-6)
    picos = [V[np.argmax(lento[V < 0])], V[V >= 0][np.argmax(lento[V >= 0])]]
    assert picos[0] == pytest.approx(-SPLIT, abs=0.02)
    assert picos[1] == pytest.approx(+SPLIT, abs=0.02)


def test_limite_rapido_colapsa_al_centro():
    """k → ∞: una sola línea en el promedio (0), más estrecha que la separación."""
    rapido = _fitbauer(1e4)
    assert V[np.argmax(rapido)] == pytest.approx(0.0, abs=0.02)
    mitad = rapido.max() / 2.0
    ancho = float(np.sum(rapido > mitad)) * (V[1] - V[0])
    assert ancho < SPLIT
