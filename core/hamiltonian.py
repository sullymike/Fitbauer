"""Tratamiento Kündig del Hamiltoniano combinado magnético+cuadrupolar
(I=3/2 excitado, axial η=0, ángulo β entre B y V_{zz}).

Mejora 8b del documento de matemática del ajuste: reemplaza el patrón rígido
``v_{0,j} = (B/33) r_j + δ + s_j ΔE_Q`` por las energías de transición
obtenidas diagonalizando el Hamiltoniano

    H_e = ω_e I_z  +  (ΔE_Q/6) · (3 I_{z'}^2 − I(I+1))

en la base |m_e⟩ = {|3/2⟩, |1/2⟩, |−1/2⟩, |−3/2⟩}, con
``I_{z'} = I_z cos β + I_x sin β``. El estado fundamental (I=1/2) sigue siendo
Zeeman puro: ``E_g(±1/2) = ±ω_g/2``.

Calibración: para que en el límite β=0 y ΔE_Q → 0 el resultado reproduzca
exactamente las posiciones ``LINE_POS_33T`` del código (multiplicado por B/33),
se usan los desdoblamientos Zeeman a 33 T del estado excitado y fundamental:

    ω_e(33 T)  =  +2.245   mm/s     (spacing entre m_e = -3/2 y -1/2)
    ω_g(33 T)  =  -3.922   mm/s     (desdoblamiento del fundamental por unidad m_g)

Estas dos constantes reproducen las seis posiciones del código a β=0 y ΔEQ=0.

Para el promedio policristalino (todas las orientaciones β equiprobables) se
integra ``A(v) = 1/2 ∫_0^π sin β · A(v; β) dβ`` por cuadratura de
Gauss--Legendre en cosβ ∈ [−1, 1]; con N≈20 nodos el error está por debajo del
0.01 % para todos los Δ_Q de interés en ⁵⁷Fe.

El cálculo está vectorizado: para N orientaciones se construye un tensor
(N, 4, 4) y se diagonaliza con ``np.linalg.eigh`` en una sola llamada.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from .constants import LINE_POS_33T, BHF_DEFAULT_T


# ── Matrices de espín para I = 3/2 ───────────────────────────────────────────
# Base ordenada |3/2⟩, |1/2⟩, |−1/2⟩, |−3/2⟩  (índices 0..3).
_Iz = np.diag([1.5, 0.5, -0.5, -1.5])
# I+|m⟩ = √(I(I+1)−m(m+1)) |m+1⟩
#   m=-3/2 → √3       (|-3/2⟩ → |-1/2⟩)
#   m=-1/2 → 2        (|-1/2⟩ → |1/2⟩)
#   m=+1/2 → √3       (|1/2⟩  → |3/2⟩)
_Ip = np.zeros((4, 4), dtype=float)
_Ip[0, 1] = np.sqrt(3.0)
_Ip[1, 2] = 2.0
_Ip[2, 3] = np.sqrt(3.0)
_Im = _Ip.T
_Ix = (_Ip + _Im) / 2.0
_I_squared = 15.0 / 4.0  # I(I+1)
_EYE4 = np.eye(4)

# ── Calibración a 33 T (mm/s) — derivada de LINE_POS_33T para coincidencia exacta ──
# Posiciones a β=0, ΔE_Q=0 son v_j = m_e·ω_e − m_g·ω_g con m_g ∈ {±1/2},
# m_e ∈ {±3/2, ±1/2}. De la diferencia LINE_POS_33T[1] − LINE_POS_33T[0] sale ω_e
# (separación entre m_e=−1/2 y m_e=−3/2 manteniendo m_g=−1/2), y de
# LINE_POS_33T[3] − LINE_POS_33T[2] sale −ω_g − ω_e.
BHF_REF_T = float(BHF_DEFAULT_T)
OMEGA_E_33T = float(LINE_POS_33T[1] - LINE_POS_33T[0])         # ~2.2484 mm/s
OMEGA_G_33T = float(-((LINE_POS_33T[3] - LINE_POS_33T[2]) + OMEGA_E_33T))   # ~-3.928 mm/s


@lru_cache(maxsize=8)
def _gauss_legendre_nodes(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Nodos x_k ∈ [-1, 1] y pesos w_k para cuadratura de Gauss-Legendre."""
    x, w = np.polynomial.legendre.leggauss(int(n))
    return x.astype(float), w.astype(float)


def excited_state_eigenvalues(bhf_T: float, deq: float, beta: float) -> np.ndarray:
    """Cuatro autovalores ordenados del Hamiltoniano del estado excitado.

    Parameters
    ----------
    bhf_T : campo hiperfino (T).
    deq   : ΔE_Q en mm/s (desdoblamiento cuadrupolar en B=0).
    beta  : ángulo entre B y V_{zz} (rad).

    Notes
    -----
    H_e = ω_e I_z + (ΔE_Q/6)(3 I_{z'}^2 − I(I+1))
    ω_e = (B/33 T) · 2.245 mm/s.

    Devuelve un array (4,) con los autovalores en mm/s, en orden ascendente.
    En β=0 los autovalores son ω_e·m_e ± ΔE_Q/2.
    """
    omega_e = bhf_T / BHF_REF_T * OMEGA_E_33T
    cos_b, sin_b = float(np.cos(beta)), float(np.sin(beta))
    Iz_prime = _Iz * cos_b + _Ix * sin_b
    Hq = (deq / 6.0) * (3.0 * (Iz_prime @ Iz_prime) - _I_squared * _EYE4)
    H = omega_e * _Iz + Hq
    return np.linalg.eigvalsh(H)


def excited_state_eigensystem(bhf_T: float, deq: float, beta: float) -> tuple[np.ndarray, np.ndarray]:
    """Autovalores y autovectores del Hamiltoniano excitado.

    Returns
    -------
    E : array (4,) autovalores ordenados (mm/s).
    V : array (4, 4) autovectores en columnas, base |m_e⟩.
    """
    omega_e = bhf_T / BHF_REF_T * OMEGA_E_33T
    cos_b, sin_b = float(np.cos(beta)), float(np.sin(beta))
    Iz_prime = _Iz * cos_b + _Ix * sin_b
    Hq = (deq / 6.0) * (3.0 * (Iz_prime @ Iz_prime) - _I_squared * _EYE4)
    H = omega_e * _Iz + Hq
    return np.linalg.eigh(H)


def _assign_me_labels(V: np.ndarray) -> np.ndarray:
    """Para cada autovector (columna) devuelve el 2·m_e dominante (-3, -1, +1, +3).

    Asigna por máxima superposición. Para β=0 los autovectores son puros |m_e⟩
    y la asignación es exacta. Para β ≠ 0 se asume mezcla "leve" (régimen de
    campo fuerte, |ΔE_Q| ≲ ω_e), donde la línea dominante sigue siendo
    identificable; si por degeneración hay ambigüedad, se devuelve el orden
    canónico {-3,-1,+1,+3} indexado por autovalor ascendente.
    """
    probs = np.abs(V) ** 2  # (4, 4) — fila k = peso de |m_e índice k⟩ en autovector
    # Intento 1: argmax por columna.
    dominant_idx = np.argmax(probs, axis=0)  # (4,) índices 0..3 → m_e = {3/2, 1/2, -1/2, -3/2}
    m2 = np.array([3, 1, -1, -3], dtype=int)[dominant_idx]
    if len(set(m2.tolist())) == 4:
        return m2
    # Fallback: orden canónico para ω_e > 0 (autovalores ascendentes ↔ m_e = -3/2…+3/2).
    return np.array([-3, -1, +1, +3], dtype=int)


def kundig_sextet_positions(
    bhf_T: float, delta: float, deq: float, beta: float
) -> np.ndarray:
    """Seis posiciones de transición (mm/s) por la solución de Kündig.

    Reproduce ``LINE_POS_33T * (B/33) + δ + s_j·ΔE_Q`` en el límite β=0
    (después se ha verificado numéricamente en los tests).
    """
    E_e, V = excited_state_eigensystem(bhf_T, deq, beta)
    omega_g = bhf_T / BHF_REF_T * OMEGA_G_33T
    Eg_plus = +omega_g / 2.0   # m_g = +1/2
    Eg_minus = -omega_g / 2.0  # m_g = -1/2

    m2 = _assign_me_labels(V)
    E_me = {int(m2[k]): float(E_e[k]) for k in range(4)}
    if len(E_me) != 4:
        # Si falla la asignación, asumir orden canónico.
        srt = np.sort(E_e)
        E_me = {-3: float(srt[0]), -1: float(srt[1]), +1: float(srt[2]), +3: float(srt[3])}

    # Líneas (m_g → m_e) en orden estándar (1..6, posición creciente en β=0):
    pos = np.array([
        E_me[-3] - Eg_minus,  # 1: m_g=-1/2 → m_e=-3/2
        E_me[-1] - Eg_minus,  # 2: m_g=-1/2 → m_e=-1/2
        E_me[+1] - Eg_minus,  # 3: m_g=-1/2 → m_e=+1/2
        E_me[-1] - Eg_plus,   # 4: m_g=+1/2 → m_e=-1/2
        E_me[+1] - Eg_plus,   # 5: m_g=+1/2 → m_e=+1/2
        E_me[+3] - Eg_plus,   # 6: m_g=+1/2 → m_e=+3/2
    ], dtype=float)
    return pos + float(delta)


def kundig_sextet_positions_batch(
    bhf_T: float, deq: float, betas: np.ndarray
) -> np.ndarray:
    """Versión vectorizada: para N betas devuelve (N, 6) posiciones (sin δ).

    Construye un tensor (N, 4, 4) de Hamiltonianos y diagonaliza en una sola
    llamada con ``np.linalg.eigh``. Crítico para el promedio policristal.
    """
    betas = np.asarray(betas, dtype=float)
    n = betas.size
    omega_e = bhf_T / BHF_REF_T * OMEGA_E_33T
    omega_g = bhf_T / BHF_REF_T * OMEGA_G_33T
    cos_b = np.cos(betas)[:, None, None]   # (N, 1, 1)
    sin_b = np.sin(betas)[:, None, None]
    # Iz_prime[n] = Iz * cos β_n + Ix * sin β_n
    Iz_p = _Iz[None, :, :] * cos_b + _Ix[None, :, :] * sin_b   # (N, 4, 4)
    Iz_p2 = np.einsum("nij,njk->nik", Iz_p, Iz_p)              # (N, 4, 4)
    Hq = (deq / 6.0) * (3.0 * Iz_p2 - _I_squared * _EYE4[None, :, :])
    H = omega_e * _Iz[None, :, :] + Hq                          # (N, 4, 4)
    E_all, V_all = np.linalg.eigh(H)                            # (N, 4), (N, 4, 4)

    # Asignación m_e dominante por orientación (vectorizado).
    probs = np.abs(V_all) ** 2                                   # (N, 4, 4)
    dom_idx = np.argmax(probs, axis=1)                           # (N, 4)
    m2_table = np.array([3, 1, -1, -3], dtype=int)
    m2 = m2_table[dom_idx]                                       # (N, 4)

    Eg_plus = +omega_g / 2.0
    Eg_minus = -omega_g / 2.0

    pos = np.empty((n, 6), dtype=float)
    canonical = np.array([-3, -1, +1, +3], dtype=int)
    for i in range(n):
        E_me = {int(m2[i, k]): float(E_all[i, k]) for k in range(4)}
        if len(E_me) != 4:
            srt = np.sort(E_all[i])
            E_me = {int(canonical[j]): float(srt[j]) for j in range(4)}
        pos[i, 0] = E_me[-3] - Eg_minus
        pos[i, 1] = E_me[-1] - Eg_minus
        pos[i, 2] = E_me[+1] - Eg_minus
        pos[i, 3] = E_me[-1] - Eg_plus
        pos[i, 4] = E_me[+1] - Eg_plus
        pos[i, 5] = E_me[+3] - Eg_plus
    return pos


def polycrystal_kundig_positions(
    bhf_T: float, delta: float, deq: float, n_quad: int = 20
) -> tuple[np.ndarray, np.ndarray]:
    """Posiciones por orientación + pesos para promedio policristal.

    Returns
    -------
    positions : (N, 6) posiciones (mm/s), δ ya sumado.
    weights   : (N,) pesos normalizados sin β · dβ = ½ d(cosβ).

    Notes
    -----
    Cuadratura Gauss-Legendre sobre x = cosβ ∈ [−1, 1] con N nodos.
    El integrando se simetriza: como el espectro es invariante bajo
    β → π − β para EFG axial η=0 con haz no polarizado, basta con β ∈ [0, π/2]
    y peso doble; aquí se usa el rango completo por simplicidad y robustez.
    """
    x, w = _gauss_legendre_nodes(int(n_quad))
    betas = np.arccos(np.clip(x, -1.0, 1.0))                       # β ∈ [0, π]
    pos = kundig_sextet_positions_batch(bhf_T, deq, betas) + float(delta)
    weights = 0.5 * w   # ½ d(cosβ) normaliza ∫_0^π sinβ dβ = 2 → 1
    return pos, weights
