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

Capacidad de NORMOS que Fitbauer NO tiene: **poblaciones desiguales**
(``SPN = BHF/BSAT``), es decir relajación con un campo externo que polariza los
dos estados. Aquí se asume siempre 50/50, que es ``SPN = 0``.
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


def _fitbauer(k_mm_s: float):
    return two_state_exchange_profile(
        V, -SPLIT, SPLIT, GAMMA, np.log10(k_mm_s * _RELAX_RATE_PER_MM_S))


def _k_optimo(ome: float) -> tuple[float, float]:
    """Tasa de Fitbauer que mejor reproduce un ``OME`` de NORMOS, y su residuo."""
    from scipy.optimize import minimize_scalar

    ref = _norm(_isirlx(V, SPLIT, ome, GAMMA, GAMMA))
    coste = lambda lk: float(  # noqa: E731
        np.max(np.abs(_norm(_fitbauer(10.0 ** lk)) - ref)) / ref.max())
    r = minimize_scalar(coste, bounds=(-3.0, 3.0), method="bounded",
                        options={"xatol": 1e-7})
    return 10.0 ** r.x, float(r.fun)


@pytest.mark.parametrize("ome", [0.1, 0.5, 2.0, 10.0, 40.0])
def test_misma_forma_que_isirlx(ome):
    """Es el MISMO modelo: existe un k que reproduce la forma de ISIRLX.

    El residuo se queda en el 2 % del pico en todo el rango, y baja al 0.1 %
    en relajación rápida. Lo que NO es constante es el mapeo ``k↔OME``: las dos
    parametrizaciones solo coinciden asintóticamente (ver test siguiente), así
    que aquí se ajusta k en vez de imponerlo.
    """
    _k, residuo = _k_optimo(ome)
    assert residuo < 0.025


def test_el_mapeo_k_ome_tiende_a_un_medio():
    """``k → OME/2`` en el límite de relajación rápida.

    En el límite LENTO la forma casi no depende de la tasa, así que el ajuste
    no la determina y el cociente se dispara: por eso no se puede publicar un
    factor de conversión único entre ``OME`` y ``k``.
    """
    razones = {ome: _k_optimo(ome)[0] / ome for ome in (0.1, 2.0, 10.0, 40.0)}
    assert razones[0.1] > 1.0                    # indeterminado en el límite lento
    assert razones[40.0] == pytest.approx(0.5, abs=0.1)
    # y decrece monótonamente hacia 1/2
    valores = [razones[o] for o in (0.1, 2.0, 10.0, 40.0)]
    assert all(a > b for a, b in zip(valores, valores[1:]))


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
