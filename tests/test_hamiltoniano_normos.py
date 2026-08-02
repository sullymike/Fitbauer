"""Nivel 8 de la revisión del fuente de NORMOS: Hamiltoniano completo.

El GMFP de NORMOS (``sitegmfp.for``, Ruebenbauer–Birchall 1979) monta en
``HMLTN``::

    H = −B·(S_z cosθ + S_x sinθcosφ + i S_y sinθsinφ)
        + A·(3S_z² − S(S+1) + η(S_x²−S_y²))          [solo si S > 1/2]

es decir el EFG en z y el campo rotado, y diagonaliza excitado Y fundamental.
Las intensidades salen de ``|Σ_{m,m'} CG·V_e·V_g*|²`` sumadas INCOHERENTEMENTE
entre canales q en polvo y COHERENTEMENTE en cristal único — que es justo lo
que hacen ``full_hamiltonian_lines`` y ``full_hamiltonian_lines_sc``.

Estos tests comprueban el Hamiltoniano contra una diagonalización INDEPENDIENTE
escrita aquí desde cero, no contra la implementación de producción.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.hamiltonian import _omegas_33t, full_hamiltonian_lines

# ── Referencia independiente (matrices de espín construidas aquí) ────────────
_IZ = np.diag([1.5, 0.5, -0.5, -1.5])
_IP = np.zeros((4, 4))
_IP[0, 1] = np.sqrt(3.0)
_IP[1, 2] = 2.0
_IP[2, 3] = np.sqrt(3.0)
_IM = _IP.T
_IX = (_IP + _IM) / 2.0
_IY = (_IP - _IM) / 2.0j
_SZ = np.diag([0.5, -0.5])
_SX = np.array([[0.0, 0.5], [0.5, 0.0]])
_SY = np.array([[0.0, -0.5j], [0.5j, 0.0]])


def _energias_referencia(bhf, delta, deq, eta, theta, phi):
    """Las 8 transiciones, diagonalizando los dos estados por separado."""
    omega_e, omega_g = _omegas_33t()
    s = bhf / 33.0
    n = np.array([np.sin(theta) * np.cos(phi),
                  np.sin(theta) * np.sin(phi),
                  np.cos(theta)])
    h_e = (s * omega_e * (n[0] * _IX + n[1] * _IY + n[2] * _IZ)
           + (deq / 6.0) * (3.0 * _IZ @ _IZ - 3.75 * np.eye(4)
                            + eta * (_IX @ _IX - _IY @ _IY)))
    h_g = s * omega_g * (n[0] * _SX + n[1] * _SY + n[2] * _SZ)
    e_e = np.linalg.eigvalsh(h_e)
    e_g = np.linalg.eigvalsh(h_g)
    return np.sort([a - b + delta for a in e_e for b in e_g])


@pytest.mark.parametrize("theta,phi,eta,deq", [
    (0.0, 0.0, 0.0, 0.0),
    (0.6, 0.4, 0.0, 0.5),
    (1.1, 0.9, 0.7, 0.9),
    (np.pi / 2, 0.0, 1.0, 1.5),
    (0.3, 2.0, 0.4, -0.8),
])
def test_energias_contra_diagonalizacion_independiente(theta, phi, eta, deq):
    pos, _inten, _wc = full_hamiltonian_lines(
        33.0, 0.1, deq, eta=eta, theta=theta, phi=phi)
    ref = _energias_referencia(33.0, 0.1, deq, eta, theta, phi)
    np.testing.assert_allclose(np.sort(pos), ref, atol=1e-12)


def test_el_fundamental_sigue_a_la_direccion_del_campo():
    """El desdoblamiento del fundamental es |ω_g| en cualquier orientación.

    Las 8 transiciones son 4 niveles excitados × 2 fundamentales, así que
    entre las diferencias por PARES tiene que aparecer |ω_g| exactamente 4
    veces (una por cada m_e), sea cual sea θ. Si el fundamental se tratase
    como Zeeman fijo en z en vez de a lo largo del campo, dejaría de cumplirse
    en cuanto θ≠0.
    """
    _omega_e, omega_g = _omegas_33t()
    for theta in (0.0, 0.7, np.pi / 2, 1.9):
        pos, _i, _w = full_hamiltonian_lines(
            33.0, 0.0, 0.0, eta=0.0, theta=theta, phi=0.3)
        difs = np.abs(pos[:, None] - pos[None, :])
        coincidencias = np.count_nonzero(
            np.isclose(np.triu(difs, 1), abs(omega_g), atol=1e-9))
        assert coincidencias == 4, f"theta={theta}: {coincidencias}"


def test_regla_de_suma_de_intensidades():
    """Σ I se conserva bajo mezcla, para que ``depth`` no cambie de significado."""
    ref = float(np.sum(full_hamiltonian_lines(33.0, 0.0, 0.0)[1]))
    for eta, theta, deq in ((0.0, 0.0, 0.0), (0.5, 0.9, 1.2),
                            (1.0, np.pi / 2, 2.0), (0.3, 0.4, -1.0)):
        total = float(np.sum(full_hamiltonian_lines(
            33.0, 0.0, deq, eta=eta, theta=theta)[1]))
        assert total == pytest.approx(ref, rel=1e-9)


def test_limite_de_primer_orden_reproduce_3_2_1():
    """Sin cuadrupolo y con B en z, las intensidades son el patrón clásico."""
    pos, inten, _wc = full_hamiltonian_lines(33.0, 0.0, 0.0, int1=3.0, int2=2.0)
    vivas = inten[inten > 1e-9]
    assert vivas.size == 6                       # las ΔmI=±2 se apagan
    patron = vivas / vivas.min()
    np.testing.assert_allclose(np.sort(patron), [1, 1, 2, 2, 3, 3], rtol=1e-6)


def test_los_pesos_por_canal_equivalen_al_goldanskii_karyagin():
    """G11 de NORMOS ↔ int1 aquí.

    NORMOS aplica el factor a la AMPLITUD tomando ``B=sqrt(|G|)``
    (``sitecalf.for:874``), así que su G equivale al peso que aquí multiplica
    la INTENSIDAD: duplicar int1 duplica el peso del canal q=±1.
    """
    _p, base, _w = full_hamiltonian_lines(33.0, 0.0, 0.0, int1=3.0, int2=2.0)
    _p, doble, _w = full_hamiltonian_lines(33.0, 0.0, 0.0, int1=6.0, int2=2.0)
    vivas_b = np.sort(base[base > 1e-9])
    vivas_d = np.sort(doble[doble > 1e-9])
    # Las líneas q=±1 (las de peso 3 y 1, que salen de int1) se duplican;
    # las q=0 (peso 2, de int2) no.
    assert vivas_d[-1] / vivas_b[-1] == pytest.approx(2.0, rel=1e-9)
    assert vivas_d[0] / vivas_b[0] == pytest.approx(2.0, rel=1e-9)
    medias_b = vivas_b[2:4]
    medias_d = vivas_d[2:4]
    np.testing.assert_allclose(medias_d, medias_b, rtol=1e-9)
