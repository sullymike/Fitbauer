"""Convenio de posiciones del sexteto (NORMOS-SITE vs histórico de Fitbauer).

SITE deriva las posiciones de los momentos nucleares (``sitecalf.for``
INIFUN). Es el patrón por defecto de Fitbauer desde la v5.3.0. El histórico
(hasta la v5.2.4) venía del simulador web del laboratorio y no tiene fuente
publicada; se conserva para reproducir sesiones y calibraciones antiguas. Los
dos NO difieren en una simple escala.
"""
from __future__ import annotations

import numpy as np
import pytest

from core import hamiltonian
from core.constants import (
    BHF_DEFAULT_T,
    LINE_POS_33T,
    SEXTET_PATTERNS,
    canonical_sextet_pattern,
    convert_vmax,
    active_sextet_pattern,
    active_sextet_pattern_name,
    fe57_sextet_positions,
    set_sextet_pattern,
    sextet_pattern,
)
from core.physics import sextet_line_positions

# Posiciones a 33 T que produce el binario demo de NORMOS-SITE (27.01.1994),
# medidas ajustando seis lorentzianas al espectro sintético `B1_x1` del banco
# de validación (BHF=33 T, ISO=QUA=0, WID=0.25, D13=3, D23=1). El ajuste
# recupera las posiciones con residuo rms de 2·10⁻⁶ en transmisión.
SITE_MEDIDO_33T = np.array(
    [-5.326106, -3.083577, -0.841041, 0.841041, 3.083577, 5.326106]
)


def test_default_es_normos():
    assert active_sextet_pattern_name() == "normos"
    np.testing.assert_allclose(active_sextet_pattern(), LINE_POS_33T, atol=0)
    np.testing.assert_allclose(LINE_POS_33T, SITE_MEDIDO_33T, atol=1e-5)
    np.testing.assert_allclose(fe57_sextet_positions(BHF_DEFAULT_T), LINE_POS_33T)


def test_el_historico_no_cambia_y_alpha_fe_es_su_alias():
    """Las sesiones hasta la v5.2.4 se reproducen solo si el histórico sigue
    siendo exactamente el mismo."""
    np.testing.assert_array_equal(
        SEXTET_PATTERNS["legacy"],
        np.array([-10.657, -6.167, -1.677, 1.677, 6.167, 10.657]) * 0.5)
    assert canonical_sextet_pattern("alpha_fe") == "legacy"
    assert canonical_sextet_pattern(None) == "normos"
    with sextet_pattern("alpha_fe"):
        assert active_sextet_pattern_name() == "legacy"


@pytest.mark.parametrize("gamma", [0.18, 0.25, 0.32, 0.40])
def test_factor_de_vmax_entre_patrones(gamma):
    """La Vmax de una calibración con α-Fe (BHF = 33 T, anchura única, 3:2:1,
    escala libre, como la de la API web) hecha con el histórico, convertida,
    es la que da 33 T con el de NORMOS."""
    from scipy.optimize import least_squares
    pesos = np.array([3, 2, 1, 1, 2, 3]) / 12.0

    def espectro(v, pos, g, cs=-0.11):
        return 1 - 0.05 * sum(w * (g / 2) ** 2 / ((v - d - cs) ** 2 + (g / 2) ** 2)
                              for w, d in zip(pesos, pos))

    v = np.linspace(-12.0, 12.0, 256)
    y = espectro(v, SEXTET_PATTERNS["legacy"], gamma)
    r = least_squares(lambda p: espectro(v * p[0], SEXTET_PATTERNS["normos"], p[1], p[2]) - y,
                      [1.0, gamma, -0.11], xtol=1e-15, ftol=1e-15)
    assert convert_vmax(1.0, "legacy", "normos") == pytest.approx(r.x[0], abs=5e-6)
    assert convert_vmax(convert_vmax(12.0, "legacy", "normos"), "normos", "legacy") \
        == pytest.approx(12.0, rel=1e-12)
    assert convert_vmax(12.0, "normos", "normos") == 12.0


def test_patron_normos_reproduce_el_binario():
    """El patrón "normos" clava lo que hace el ejecutable, no solo el fuente."""
    np.testing.assert_allclose(SEXTET_PATTERNS["normos"], SITE_MEDIDO_33T, atol=1e-5)


def test_los_dos_patrones_no_son_una_escala():
    """Justifica que el convenio exista: no basta con un factor k sobre BHF."""
    a = SEXTET_PATTERNS["legacy"]
    n = SEXTET_PATTERNS["normos"]
    k = float(np.sum(a * n) / np.sum(a * a))       # mejor escala en mínimos cuadrados
    residuo = n - k * a
    # Con una simple escala quedarían residuos < 1e-9; quedan milésimas de mm/s.
    assert np.max(np.abs(residuo)) > 2.0e-3
    # Y el residuo es ANTISIMÉTRICO, así que ni δ (constante) ni ΔE_Q
    # (patrón [+,−,−,−,−,+]) pueden absorberlo.
    np.testing.assert_allclose(residuo, -residuo[::-1], atol=1e-9)


def test_context_manager_cambia_y_restaura():
    antes = active_sextet_pattern().copy()
    with sextet_pattern("legacy"):
        np.testing.assert_allclose(active_sextet_pattern(), SEXTET_PATTERNS["legacy"])
        pos = sextet_line_positions(0.0, 0.0, BHF_DEFAULT_T)
        np.testing.assert_allclose(pos, SEXTET_PATTERNS["legacy"], atol=1e-12)
    np.testing.assert_allclose(active_sextet_pattern(), antes, atol=0)
    np.testing.assert_allclose(sextet_line_positions(0.0, 0.0, BHF_DEFAULT_T),
                               SITE_MEDIDO_33T, atol=1e-5)


def test_context_manager_restaura_ante_excepcion():
    antes = active_sextet_pattern_name()
    with pytest.raises(RuntimeError):
        with sextet_pattern("legacy"):
            raise RuntimeError("boom")
    assert active_sextet_pattern_name() == antes


def test_patron_desconocido_lanza():
    with pytest.raises(ValueError, match="patrón de sexteto desconocido"):
        set_sextet_pattern("no_existe")
    assert active_sextet_pattern_name() == "normos"


def test_el_hamiltoniano_sigue_al_convenio():
    """ω_e/ω_g se leen del patrón activo, no de una constante congelada."""
    we_n, wg_n = hamiltonian._omegas_33t()
    # Límite ΔE_Q → 0, β=0: el Hamiltoniano debe dar el patrón de SITE.
    pos = hamiltonian.kundig_sextet_positions(BHF_DEFAULT_T, 0.0, 0.0, 0.0)
    np.testing.assert_allclose(pos, SITE_MEDIDO_33T, atol=1e-5)
    with sextet_pattern("legacy"):
        we_a, wg_a = hamiltonian._omegas_33t()
    assert we_a != pytest.approx(we_n, abs=1e-6)
    assert wg_a != pytest.approx(wg_n, abs=1e-6)
    # Y al salir del bloque vuelve al de NORMOS.
    np.testing.assert_allclose(hamiltonian._omegas_33t(), (we_n, wg_n))


def test_el_kernel_de_distribucion_sigue_al_convenio():
    import mossbauer_distribution as md

    v = np.linspace(-11.0, 11.0, 601)
    kw = dict(delta=0.0, quad=0.0, bhf=BHF_DEFAULT_T, gamma=0.25)
    y_normos = md.sextet_absorption(v, **kw)
    with sextet_pattern("legacy"):
        y_alpha = md.sextet_absorption(v, **kw)
    # El desplazamiento de las líneas internas (2.5·10⁻³ mm/s) es pequeño pero
    # muy por encima del ruido numérico: el kernel TIENE que notarlo.
    assert np.max(np.abs(y_normos - y_alpha)) > 1e-4


def test_normos_reduce_el_residuo_frente_a_un_sexteto_de_site():
    """El caso de uso: ajustar un espectro de SITE con el convenio correcto."""
    v = np.linspace(-11.0, 11.0, 512)
    pesos = np.array([3.0, 2.0, 1.0, 1.0, 2.0, 3.0])

    def espectro(pos, gamma=0.25):
        g = gamma / 2.0
        return sum(w * g * g / ((v - p) ** 2 + g * g) for w, p in zip(pesos, pos))

    objetivo = espectro(SITE_MEDIDO_33T)

    def mejor_residuo(nombre):
        with sextet_pattern(nombre):
            # Solo se deja libre la escala del campo, que es lo que un ajuste
            # real puede mover (δ y ΔE_Q no absorben un residuo antisimétrico).
            escalas = np.linspace(0.998, 1.002, 4001)
            return min(
                float(np.sqrt(np.mean((espectro(sextet_line_positions(
                    0.0, 0.0, BHF_DEFAULT_T * s)) - objetivo) ** 2)))
                for s in escalas
            )

    # El suelo de `normos` lo pone el redondeo a 1e-6 de SITE_MEDIDO_33T, no el
    # modelo; con α-Fe el residuo es tres órdenes mayor y es irreducible.
    assert mejor_residuo("normos") < 1e-5
    assert mejor_residuo("legacy") > 1e-3
