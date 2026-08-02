"""Nivel 5 de la revisión del fuente de NORMOS: interpolación del doblado.

NORMOS (``normospr.for``, doblado de Hoersten 14.4.89) trunca el punto de
doblado a ENTERO y suma pares de canales enteros: no interpola nunca, pero
desalinea el par hasta medio canal. Fitbauer interpola a subcanal, que alinea
bien — pero con interpolación LINEAL, que es un filtro paso bajo y ENSANCHA las
líneas. Estos tests fijan la mejora (cúbica) y su ausencia de efecto en el caso
semientero, que es el habitual.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import least_squares

from core.folding import (
    FOLD_INTERP_ORDER_DEFAULT,
    chi2_for_center,
    find_best_integer_or_half_center,
    fold_and_normalize,
    fold_integer_or_half,
    interp_channel_1based,
    velocity_axis,
)
from core.physics import sextet_absorption

N = 512
GAMMA = 0.28
_I = np.arange(1, N + 1, dtype=float)


def _espectro(centro: float, base: float = 1e6) -> np.ndarray:
    """Sexteto perfectamente simétrico respecto a ``centro`` (sin ruido)."""
    d = np.abs(_I - centro)
    v = -10.0 + 20.0 * (1.0 - d / d.max())
    return base * (1.0 - sextet_absorption(
        v, 0.0, 0.0, 33.0, GAMMA, 1.0, 1.0, 0.05, 3.0, 2.0, 1.0))


def _gamma_ajustada(counts: np.ndarray, centro: float, order: int) -> float:
    _folded, _sigma, y, _norm = fold_and_normalize(counts, centro, order=order)
    v = velocity_axis(counts.size, 10.0, y.size)

    def res(p):
        return p[0] - sextet_absorption(
            v, p[1], 0.0, 33.0, p[2], 1.0, 1.0, p[3], 3.0, 2.0, 1.0) - y

    return float(least_squares(res, [1.0, 0.0, GAMMA, 0.05],
                               xtol=1e-14, ftol=1e-14).x[2])


def test_default_es_cubica():
    assert FOLD_INTERP_ORDER_DEFAULT == 3


def test_centro_semientero_no_interpola():
    """El caso habitual: los pares caen en canales enteros, orden irrelevante."""
    counts = _espectro(256.5)
    f1, _ = fold_integer_or_half(counts, 256.5, order=1)
    f3, _ = fold_integer_or_half(counts, 256.5, order=3)
    np.testing.assert_allclose(f3, f1, rtol=0, atol=1e-9)


@pytest.mark.parametrize("centro", [256.25, 256.0, 255.77])
def test_cubica_reduce_el_ensanchamiento(centro):
    """Con centro fraccionario, la lineal infla Γ y la cúbica lo corrige."""
    counts = _espectro(centro)
    e1 = _gamma_ajustada(counts, centro, 1) - GAMMA
    e3 = _gamma_ajustada(counts, centro, 3) - GAMMA
    # Las dos sobreestiman (queda el suelo de la integración por canal), pero
    # la cúbica al menos a la mitad del error de la lineal.
    assert e1 > 0 and e3 > 0
    assert e3 < 0.5 * e1


def test_ensanchamiento_lineal_es_grande_en_el_peor_caso():
    """Documenta la magnitud: con f=0.5 la lineal infla Γ casi un 10 %."""
    counts = _espectro(256.0)          # pares en canales semienteros → f = 0.5
    e1 = _gamma_ajustada(counts, 256.0, 1) - GAMMA
    assert e1 / GAMMA > 0.09


def test_centro_detectado_sigue_siendo_exacto():
    """El centro no se degrada con la cúbica.

    Sobre este sexteto la cúbica además mejora (de ±0.013 a ±0.004 canales),
    pero NO es una mejora universal: con un doblete gaussiano ancho y ruidoso
    el orden 1 sale algo mejor. Lo que sí se sostiene en ambos casos es que el
    error se queda muy por debajo de un canal, y un desajuste de 0.02 canales
    son 8·10⁻⁴ mm/s — despreciable frente a cualquier Γ. La mejora sistemática
    de la cúbica es el ensanchamiento, no el centro.
    """
    for centro in (256.25, 255.77):
        counts = _espectro(centro)
        s1 = abs(find_best_integer_or_half_center(counts, order=1) - centro)
        s3 = abs(find_best_integer_or_half_center(counts, order=3) - centro)
        assert s1 < 0.02 and s3 < 0.02
        assert s3 < s1          # en este espectro concreto


def test_canal_muerto_de_borde_no_mueve_el_centro():
    """La spline es global: sin recortar bordes, un canal 1 muerto contamina.

    Regresión del nivel 5: con la B-spline construida sobre el array completo
    el centro se desplazaba 0.056 canales al poner el canal 1 a ~0.
    """
    counts = _espectro(255.77)
    muerto = counts.copy()
    muerto[0] = 6760.0
    for order in (1, 3):
        limpio = find_best_integer_or_half_center(counts, order=order)
        sucio = find_best_integer_or_half_center(muerto, order=order)
        assert abs(sucio - limpio) < 0.01, f"order={order}"


def test_orden_se_resuelve_en_tiempo_de_ejecucion():
    """Se puede volver al doblado lineal para reproducir resultados antiguos."""
    import core.folding as folding

    counts = _espectro(255.77)
    previo = folding.FOLD_INTERP_ORDER_DEFAULT
    try:
        folding.FOLD_INTERP_ORDER_DEFAULT = 1
        por_defecto, _ = fold_integer_or_half(counts, 255.77)
        explicito, _ = fold_integer_or_half(counts, 255.77, order=1)
        np.testing.assert_allclose(por_defecto, explicito, atol=0)
    finally:
        folding.FOLD_INTERP_ORDER_DEFAULT = previo
    cubica, _ = fold_integer_or_half(counts, 255.77)
    assert np.max(np.abs(cubica - por_defecto)) > 0


def test_interp_channel_1based_sigue_siendo_lineal():
    """API histórica intacta: se usa en scripts y en la GUI."""
    counts = np.arange(1, 11, dtype=float) ** 2
    assert interp_channel_1based(counts, 3.0) == pytest.approx(9.0)
    assert interp_channel_1based(counts, 3.5) == pytest.approx(0.5 * (9.0 + 16.0))
    # Extrapolación lineal por los bordes.
    assert interp_channel_1based(counts, 0.0) == pytest.approx(1.0 - 3.0)


def test_pares_devueltos_no_cambian():
    counts = _espectro(255.77)
    _f, pares = fold_integer_or_half(counts, 255.77)
    esperado = [(int(round(255.77 - (j + 0.5))), int(round(255.77 + (j + 0.5))))
                for j in range(counts.size // 2)]
    assert pares == esperado


def test_chi2_for_center_acepta_orden():
    counts = _espectro(256.5)
    c1, n1 = chi2_for_center(counts, 256.5, order=1)
    c3, n3 = chi2_for_center(counts, 256.5, order=3)
    assert n1 == n3
    # En el centro exacto la simetría es perfecta con cualquier interpolación.
    assert c1 == pytest.approx(0.0, abs=1e-6)
    assert c3 == pytest.approx(0.0, abs=1e-6)


# ── Efecto geométrico (portado de NORMOS) ────────────────────────────────────

def _con_efecto_geometrico(counts: np.ndarray, centro: float, rel: float) -> np.ndarray:
    i = np.arange(1, counts.size + 1, dtype=float)
    return counts + rel * float(np.median(counts)) * np.sin(
        np.pi * (i - centro) / (0.5 * counts.size))


def test_efecto_geometrico_es_cero_en_espectro_simetrico():
    from core.folding import geometry_effect_amplitude

    counts = _espectro(256.5)
    amp = geometry_effect_amplitude(counts, 256.5)
    assert abs(amp) / np.median(counts) < 1e-6


@pytest.mark.parametrize("rel", [-0.02, -0.005, 0.001, 0.02])
def test_efecto_geometrico_recupera_la_amplitud(rel):
    from core.folding import geometry_effect_amplitude

    centro = 255.77
    counts = _con_efecto_geometrico(_espectro(centro), centro, rel)
    amp = geometry_effect_amplitude(counts, centro)
    assert amp / np.median(counts) == pytest.approx(rel, rel=0.02)


def test_remove_geometry_effect_deja_el_espectro_simetrico():
    from core.folding import geometry_effect_amplitude, remove_geometry_effect

    centro = 255.77
    counts = _con_efecto_geometrico(_espectro(centro), centro, 0.02)
    limpio, amp = remove_geometry_effect(counts, centro)
    assert amp / np.median(counts) == pytest.approx(0.02, rel=0.02)
    residual = geometry_effect_amplitude(limpio, centro)
    assert abs(residual) < 1e-3 * abs(amp)


def test_el_doblado_ya_cancela_el_efecto_geometrico():
    """Por eso es un diagnóstico y no una corrección: al doblar se va solo."""
    centro = 256.5
    limpio = _espectro(centro)
    sucio = _con_efecto_geometrico(limpio, centro, 0.02)
    f_limpio, _ = fold_integer_or_half(limpio, centro)
    f_sucio, _ = fold_integer_or_half(sucio, centro)
    np.testing.assert_allclose(f_sucio, f_limpio, rtol=1e-9)


# ── Dos ciclos de búsqueda ───────────────────────────────────────────────────

def test_dos_ciclos_no_degradan_el_centro():
    from core.folding import CENTER_SEARCH_CYCLES

    assert CENTER_SEARCH_CYCLES == 2
    for centro in (256.5, 255.77, 256.25):
        counts = _espectro(centro)
        c2 = find_best_integer_or_half_center(counts, cycles=2)
        assert abs(c2 - centro) < 0.01


def test_segundo_ciclo_recupera_un_centro_lejano():
    """La ventana ancha del 1er ciclo localiza; el 2º refina en su entorno."""
    centro = 262.3
    counts = _espectro(centro)
    c1 = find_best_integer_or_half_center(counts, cycles=1)
    c2 = find_best_integer_or_half_center(counts, cycles=2)
    assert abs(c2 - centro) <= abs(c1 - centro) + 1e-9
    assert abs(c2 - centro) < 0.05


def test_sesion_headless_expone_el_efecto_geometrico(tmp_path):
    """El diagnóstico llega al payload de sesión (y de ahí al CLI)."""
    from core.session import HeadlessSession

    counts = _con_efecto_geometrico(_espectro(256.5), 256.5, 0.015)
    adt = tmp_path / "geo.adt"
    adt.write_text("\n".join(str(int(round(c))) for c in counts), encoding="utf-8")
    sesion = HeadlessSession()
    sesion.load_ws5(adt, vmax=10.0)
    assert sesion.geometry_effect["relative"] == pytest.approx(0.015, rel=0.05)
    assert sesion.session_payload()["geometry_effect"]["relative"] == pytest.approx(
        sesion.geometry_effect["relative"])
