"""Nivel 9 de la revisión del fuente de NORMOS: relajación.

``siterelx.for`` implementa la relajación de **Ising** (``ISIRLX``) como la
forma cerrada de Blume para dos estados ±B_hf: dos autovalores complejos
λ₁, λ₂ con pesos AC/BD, y el espectro es ``Σ_j D_j·Re[AC/(λ₁+z) + BD/(λ₂+z)]``
con ``z = Γ_s/2 + i(v_j − v)``.

Fitbauer tiene el mismo modelo en ``two_state_exchange_profile``, pero
parametrizado por la tasa ``k`` en vez de ``OME``. Este módulo fija la
equivalencia — es la primera validación de la relajación de Fitbauer, que con
el binario del demo no era comprobable (§19: BSAT no está en su namelist y sus
espectros IRELAX salen colapsados incluso con OME=0).

Las poblaciones desiguales (``SPN = BHF/BSAT``: un campo externo que polariza
los dos estados) eran una capacidad que faltaba; ahora están como
``polarization`` / ``relax_polarization``.

Ojo con la anchura al comparar: NORMOS usa DOS (``WD`` en los autovalores y
``WDS`` en la convolución final) y aquí solo hay una, así que la equivalencia
es con ``WD = 0`` y ``WDS = Γ``. Contarlas ambas mete un 2 % de residuo que
NO es del modelo.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.physics import _RELAX_RATE_PER_MM_S, two_state_exchange_profile

V = np.linspace(-12.0, 12.0, 4001)
GAMMA = 0.25
SPLIT = 5.3285          # línea 1/6 de un sexteto a 33 T


def _isirlx(v, dvl0, ome, wd, wds, vels=0.0, spn=0.0, vl0=0.0):
    """Port literal de ``ISIRLX`` (siterelx.for:58) para una línea."""
    b1 = -0.5 * (ome + wd)
    h = 0.25 * ome ** 2 - dvl0 ** 2
    rk = -dvl0 * spn * ome
    hk = np.sqrt(h ** 2 + rk ** 2)
    eta = np.sqrt(max(0.5 * (hk + h), 0.0))
    rnue = np.sqrt(max(0.5 * (hk - h), 0.0))
    xp, yp = eta - b1, rnue - vl0
    xn, yn = -eta - b1, -rnue - vl0
    if dvl0 <= 0:
        lam1, lam2 = complex(xp, yp), complex(xn, yn)
    else:
        lam1, lam2 = complex(xp, yn), complex(xn, yp)
    bb = complex(ome + 0.5 * wd, -vl0 - dvl0)
    cc = complex(ome + 0.5 * wd, -vl0 + dvl0)
    rk1 = (bb - lam1) / (cc - lam1)
    rk2 = (cc - lam2) / (bb - lam2)
    ac = 0.5 * (1 + spn + rk1 * (1 - spn)) * (1 - rk2) / (1 - rk1 * rk2)
    bd = 0.5 * (1 - spn + rk2 * (1 + spn)) * (1 - rk1) / (1 - rk1 * rk2)
    z = 0.5 * wds + 1j * (vels - v)
    return np.real(ac / (lam1 + z) + bd / (lam2 + z))


def _norm(y):
    return y / np.trapezoid(y, V)


def _fitbauer(k_mm_s: float, pol: float = 0.0):
    return two_state_exchange_profile(
        V, -SPLIT, SPLIT, GAMMA, np.log10(k_mm_s * _RELAX_RATE_PER_MM_S), pol)


@pytest.mark.parametrize("ome", [0.1, 0.5, 2.0, 10.0, 40.0])
def test_identico_a_isirlx_con_k_igual_a_ome_medio(ome):
    """Es EXACTAMENTE el mismo modelo, con ``k = OME/2``.

    La comparación se hace con ``WD=0`` (toda la anchura en la convolución),
    que es la correspondencia correcta entre las dos parametrizaciones.
    """
    ref = _isirlx(V, SPLIT, ome, 0.0, GAMMA)
    mio = _fitbauer(ome / 2.0)
    escala = float(np.sum(mio * ref) / np.sum(mio * mio))
    assert escala == pytest.approx(8.0, rel=1e-9)      # normalización a pico
    assert np.max(np.abs(escala * mio - ref)) < 1e-12 * max(1.0, ref.max())


@pytest.mark.parametrize("ome,spn", [(0.5, 0.3), (2.0, 0.3), (2.0, 0.6),
                                     (10.0, 0.6), (2.0, 0.9), (10.0, 0.9)])
def test_poblaciones_desiguales_identicas_a_isirlx(ome, spn):
    """La polarización también reproduce ISIRLX exactamente (P = SPN)."""
    ref = _isirlx(V, SPLIT, ome, 0.0, GAMMA, spn=spn)
    mio = _fitbauer(ome / 2.0, spn)
    assert np.max(np.abs(8.0 * mio - ref)) < 1e-12 * max(1.0, abs(ref).max())


def test_polarizacion_conserva_el_area():
    """``AC + BD = 1`` analíticamente; el peso total no depende de P."""
    v = np.linspace(-60.0, 60.0, 24001)
    areas = []
    for pol in (0.0, 0.3, 0.6, 0.9):
        y = two_state_exchange_profile(
            v, -SPLIT, SPLIT, GAMMA,
            np.log10(1.0 * _RELAX_RATE_PER_MM_S), pol)
        areas.append(float(np.trapezoid(y, v)))
    assert max(areas) - min(areas) < 1e-3 * areas[0]


def test_polarizacion_cero_es_el_comportamiento_historico():
    """P=0 debe pasar por la rama simétrica original, sin cambios."""
    a = _fitbauer(1.0, 0.0)
    b = two_state_exchange_profile(
        V, -SPLIT, SPLIT, GAMMA, np.log10(1.0 * _RELAX_RATE_PER_MM_S))
    np.testing.assert_allclose(a, b, atol=0)


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
    """OME → 0: dos lorentzianas en ±SPLIT, sin ensanchar."""
    lento = _norm(_fitbauer(1e-6))
    picos = [V[np.argmax(lento[V < 0])], V[V >= 0][np.argmax(lento[V >= 0])]]
    assert picos[0] == pytest.approx(-SPLIT, abs=0.02)
    assert picos[1] == pytest.approx(+SPLIT, abs=0.02)


def test_limite_rapido_colapsa_al_centro():
    """OME → ∞: una sola línea en el promedio (0)."""
    rapido = _norm(_fitbauer(1e4))
    assert V[np.argmax(rapido)] == pytest.approx(0.0, abs=0.02)
    # y es más estrecha que la separación original
    mitad = rapido.max() / 2.0
    ancho = float(np.sum(rapido > mitad)) * (V[1] - V[0])
    assert ancho < SPLIT


def test_isirlx_tambien_colapsa_y_se_ensancha():
    """Control del port: la referencia recorre los mismos regímenes."""
    lento = _isirlx(V, SPLIT, 1e-6, GAMMA, GAMMA)
    rapido = _isirlx(V, SPLIT, 200.0, GAMMA, GAMMA)
    assert V[np.argmax(lento)] == pytest.approx(-SPLIT, abs=0.05) or \
        V[np.argmax(lento)] == pytest.approx(SPLIT, abs=0.05)
    assert V[np.argmax(rapido)] == pytest.approx(0.0, abs=0.05)


def test_poblaciones_desiguales_cambian_el_espectro():
    """SPN ≠ 0 (capacidad de NORMOS que no tenemos) NO es un caso degenerado.

    Documenta que la asimetría por polarización de los dos estados es un
    efecto real, no absorbible por la tasa: con SPN=0.6 el espectro deja de
    ser simétrico.
    """
    simetrico = _isirlx(V, SPLIT, 2.0, GAMMA, GAMMA, spn=0.0)
    polarizado = _isirlx(V, SPLIT, 2.0, GAMMA, GAMMA, spn=0.6)
    asim = np.max(np.abs(polarizado - polarizado[::-1]))
    assert np.max(np.abs(simetrico - simetrico[::-1])) < 1e-9
    assert asim > 0.01 * polarizado.max()
