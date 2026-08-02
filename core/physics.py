"""Funciones puras de física Mössbauer (sin dependencias de GUI)."""
from __future__ import annotations

from contextlib import contextmanager

import numpy as np
from scipy.special import wofz

from .constants import (
    LINE_QUAD_PATTERN, BHF_DEFAULT_T, E_GAMMA, active_sextet_pattern,
)
from .hamiltonian import (
    full_hamiltonian_lines,
    full_hamiltonian_lines_sc,
    kundig_sextet_positions,
    kundig_sextet_positions_batch,
    polycrystal_kundig_positions,
)

# Estado global del perfil de línea (modificado por la GUI).
LINE_PROFILE_KIND: str = "Lorentziana"
VOIGT_SIGMA: float = 0.05
#: Asimetría de línea por interferencia (paridad con el AKS de NORMOS-SITE).
#: 0 = línea simétrica (comportamiento histórico).
LINE_ASYM: float = 0.0
#: Convenio de las razones de intensidad entre líneas de una misma componente:
#: ``"depth"`` (razones de PROFUNDIDAD, histórico) o ``"area"`` (razones de
#: ÁREA, que es lo que son físicamente las probabilidades de transición 3:2:1 y
#: lo que significan D13/D23 en NORMOS). Coinciden si las anchuras son iguales.
INTENSITY_CONVENTION: str = "depth"


@contextmanager
def line_profile(kind: str = "Lorentziana", voigt_sigma: float = 0.05,
                 asym: float | None = None):
    """Fija de forma determinista el perfil de línea usado por ``lorentzian``.

    La forma de línea vive en las variables de módulo ``LINE_PROFILE_KIND`` /
    ``VOIGT_SIGMA`` / ``LINE_ASYM`` que ``lorentzian`` lee en cada llamada.
    Distintas rutas (ajuste discreto, distribución, previsualización) las
    escriben; este gestor las fija durante un bloque y las **restaura** al
    salir, evitando que el perfil quede "contaminado" entre operaciones.

    ``asym=None`` deja la asimetría como esté (no la toca).
    """
    global LINE_PROFILE_KIND, VOIGT_SIGMA, LINE_ASYM
    use_voigt = str(kind) == "Voigt"
    prev_kind, prev_sigma, prev_asym = LINE_PROFILE_KIND, VOIGT_SIGMA, LINE_ASYM
    LINE_PROFILE_KIND = "Voigt" if use_voigt else "Lorentziana"
    if use_voigt:
        VOIGT_SIGMA = max(float(voigt_sigma), 1e-9)
    if asym is not None:
        LINE_ASYM = float(asym)
    try:
        yield
    finally:
        LINE_PROFILE_KIND = prev_kind
        VOIGT_SIGMA = prev_sigma
        LINE_ASYM = prev_asym


@contextmanager
def line_asymmetry(asym: float):
    """Fija solo la asimetría de línea (AKS) durante un bloque y la restaura.

    Gestor dedicado para las rutas que evalúan el modelo a partir de un
    diccionario de parámetros (``fit_engine.model_from_values``) y no deben
    tocar el resto del estado del perfil.
    """
    global LINE_ASYM
    previous, LINE_ASYM = LINE_ASYM, float(asym)
    try:
        yield
    finally:
        LINE_ASYM = previous


@contextmanager
def intensity_convention(name: str):
    """Fija el convenio de razones de intensidad durante un bloque.

    ``"depth"`` (histórico) o ``"area"`` (físico / NORMOS). Ver
    :data:`INTENSITY_CONVENTION`.
    """
    global INTENSITY_CONVENTION
    key = str(name)
    if key not in ("depth", "area"):
        raise ValueError(
            f"convenio de intensidad desconocido: {name!r} (usa 'depth' o 'area')")
    previous, INTENSITY_CONVENTION = INTENSITY_CONVENTION, key
    try:
        yield
    finally:
        INTENSITY_CONVENTION = previous


def _area_to_depth_weights(weights: np.ndarray, gammas: np.ndarray) -> np.ndarray:
    """Convierte razones de ÁREA en los pesos de pico que usa ``lorentzian``.

    Un perfil normalizado en pico tiene área ∝ profundidad·Γ, así que para que
    las áreas queden en la razón pedida basta dividir por la anchura RELATIVA a
    la primera línea. Con todas las anchuras iguales es la identidad, de modo
    que el convenio ``"area"`` solo se separa del histórico cuando el usuario
    libera ``gamma2``/``gamma3``.
    """
    g = np.asarray(gammas, dtype=float)
    ref = float(g[0]) if g.size and g[0] > 0 else 1.0
    rel = np.where(g > 0, g / ref, 1.0)
    return np.asarray(weights, dtype=float) / rel


def lorentzian(v: np.ndarray, center: float, gamma: float) -> np.ndarray:
    """Perfil de línea normalizado en PICO, con la asimetría global aplicada.

    La asimetría reproduce el AKS de NORMOS-SITE (``LORLIN`` en
    ``siteauxl.for``): el perfil se multiplica por ``1 − a·(v−v₀)/Γ``. La
    fórmula se verificó contra el binario demo 27.01.1994 (rms 1.2·10⁻⁴, el
    suelo de precisión de su ``.PLT``).

    Divergencia deliberada: en modo Voigt, SITE aplica AKS solo a la mitad
    lorentziana de su pseudo-Voigt (su ``GAULIN`` lo ignora); aquí se aplica al
    perfil completo, que es lo coherente.
    """
    gamma_f = max(float(gamma), 1e-9)
    g = gamma_f / 2.0
    if LINE_PROFILE_KIND == "Voigt":
        sigma = max(float(VOIGT_SIGMA), 1e-9)
        denom = sigma * np.sqrt(2.0)
        norm = sigma * np.sqrt(2.0 * np.pi)
        prof = np.real(wofz(((v - center) + 1j * g) / denom)) / norm
        peak = float(np.real(wofz(1j * g / denom))) / norm
        shape = prof / max(peak, 1e-12)
    else:
        shape = g * g / ((v - center) ** 2 + g * g)
    if LINE_ASYM:
        shape = shape * (1.0 - float(LINE_ASYM) * (v - center) / gamma_f)
    return shape


def sextet_line_positions(delta: float, quad: float, bhf: float) -> np.ndarray:
    """Posiciones de las 6 líneas del sextete a 1er orden (patrón activo escalado).

    El patrón es el del convenio activo (``core.constants.sextet_pattern``):
    α-Fe publicado por defecto, o el de NORMOS-SITE si se ha seleccionado.
    """
    return (active_sextet_pattern() * (float(bhf) / BHF_DEFAULT_T)
            + float(delta) + float(quad) * LINE_QUAD_PATTERN)


def sum_lorentzian_lines(
    v: np.ndarray, positions: np.ndarray, weights: np.ndarray, gammas: np.ndarray,
) -> np.ndarray:
    """Suma de líneas (perfil global Lorentz/Voigt) con pesos y anchuras por línea.

    Primitivo compartido por las dos convenciones de intensidad del proyecto
    (pesos explícitos en ``core.physics``; ``int2_rel``/``int3_rel`` con los
    factores 2/3 y 1/3 horneados en ``mossbauer_distribution``).
    """
    absorption = np.zeros_like(np.asarray(v, dtype=float), dtype=float)
    for pos, weight, gamma in zip(positions, weights, gammas):
        absorption += weight * lorentzian(v, float(pos), float(gamma))
    return absorption


def sextet_absorption(
    v: np.ndarray,
    delta: float, quad: float, bhf: float,
    gamma1: float, gamma2: float, gamma3: float,
    depth: float, int1: float, int2: float, int3: float,
    *,
    treatment: str = "1st_order",
    beta: float = 0.0,
    n_quad: int = 20,
    eta: float = 0.0,
    phi: float = 0.0,
    beam_theta: float = 0.0,
    beam_phi: float = 0.0,
) -> np.ndarray:
    """Absorción del sextete.

    ``treatment``:
      * ``"1st_order"`` (default): patrón rígido aditivo (modelo histórico).
      * ``"kundig_fixed"``: posiciones por diagonalización del Hamiltoniano
        ω_e I_z + (ΔE_Q/6)(3 I_{z'}^2 − I(I+1)) con ángulo β fijo (rad)
        entre B y V_{zz} (EFG axial, η=0). Mejora 8b.
      * ``"kundig_powder"``: promedio policristal por cuadratura
        Gauss–Legendre de ``n_quad`` orientaciones (β ∈ [0, π]).
      * ``"hamiltonian"``: Hamiltoniano estático completo (EFG con ``eta`` y
        ángulos β=θ, ``phi`` en rad) con INTENSIDADES calculadas desde los
        autovectores (8 transiciones, CG + promedio isótropo del haz). Los
        pesos int1/int2 fijan la textura de los canales q (int1→q=±1,
        int2→q=0); int3 no aplica (la relación 1,6/3,4 = 3 es física).
        Validado contra NORMOS-SITE HAMILT (banco de validación, §6.1).
      * ``"hamiltonian_sc"``: cristal único — como ``"hamiltonian"`` pero con
        el haz γ en dirección fija (``beam_theta``, ``beam_phi``, rad, marco
        del EFG; BEX/GAX de NORMOS-SITE) y suma coherente entre canales q.
        int1/int2 no aplican. Banco de validación banco-2 §K3.
    """
    i3 = int3
    i2 = int3 * int2
    i1 = int3 * int1
    weights = np.array([i1, i2, i3, i3, i2, i1], dtype=float)
    g1 = gamma1
    g2 = gamma1 * gamma2
    g3 = gamma1 * gamma3
    gammas = np.array([g1, g2, g3, g3, g2, g1], dtype=float)
    if INTENSITY_CONVENTION == "area":
        # int1/int2 pasan a ser A13/A23 (razones de ÁREA, convenio NORMOS).
        weights = _area_to_depth_weights(weights, gammas)

    if treatment == "hamiltonian":
        positions, inten, wclass = full_hamiltonian_lines(
            bhf, delta, quad, eta=eta, theta=beta, phi=phi,
            int1=i1, int2=i2)
        g_by_class = {1: g1, 2: g2, 3: g3}
        gam8 = np.array([g_by_class[int(c)] for c in wclass], dtype=float)
        return depth * sum_lorentzian_lines(v, positions, inten, gam8)

    if treatment == "hamiltonian_sc":
        # Cristal único (mejora banco-2 §K3): haz γ en dirección fija
        # (beam_theta, beam_phi) en el marco del EFG; int1/int2 no aplican
        # (la geometría de intensidades es explícita).
        positions, inten, wclass = full_hamiltonian_lines_sc(
            bhf, delta, quad, eta=eta, theta=beta, phi=phi,
            beam_theta=beam_theta, beam_phi=beam_phi)
        g_by_class = {1: g1, 2: g2, 3: g3}
        gam8 = np.array([g_by_class[int(c)] for c in wclass], dtype=float)
        return depth * sum_lorentzian_lines(v, positions, inten, gam8)

    if treatment == "kundig_fixed":
        positions = kundig_sextet_positions(bhf, delta, quad, beta)
        return depth * sum_lorentzian_lines(v, positions, weights, gammas)

    if treatment == "kundig_powder":
        pos_grid, w_grid = polycrystal_kundig_positions(bhf, delta, quad, n_quad)
        absorption = np.zeros_like(v, dtype=float)
        for k in range(pos_grid.shape[0]):
            absorption += w_grid[k] * sum_lorentzian_lines(v, pos_grid[k], weights, gammas)
        return depth * absorption

    if treatment != "1st_order":
        # Sin esto, un tratamiento desconocido (typo, valor antiguo) caía en
        # SILENCIO al 1er orden — la misma clase de fallo que el preset de
        # layout huérfano (auditoría de tests 2026-08-02).
        raise ValueError(f"treatment desconocido: {treatment!r}")
    positions = sextet_line_positions(delta, quad, bhf)
    return depth * sum_lorentzian_lines(v, positions, weights, gammas)


def singlet_absorption(
    v: np.ndarray, delta: float, gamma1: float, depth: float, int1: float,
) -> np.ndarray:
    return depth * int1 * lorentzian(v, delta, gamma1)


def doublet_absorption(
    v: np.ndarray,
    delta: float, quad: float, gamma1: float, gamma2: float,
    depth: float, int1: float, int2: float,
) -> np.ndarray:
    g1 = gamma1
    g2 = gamma1 * gamma2
    w1, w2 = int1, int1 * int2
    if INTENSITY_CONVENTION == "area":
        # int2 pasa a ser A21 (razón de ÁREA, convenio NORMOS).
        w1, w2 = _area_to_depth_weights(
            np.array([w1, w2], dtype=float), np.array([g1, g2], dtype=float))
    return depth * (
        w1 * lorentzian(v, delta - quad / 2.0, g1)
        + w2 * lorentzian(v, delta + quad / 2.0, g2)
    )


def relaxation_transition_factors(log10_nu: float | None) -> tuple[float, float]:
    """Factores fenomenológicos (fracción bloqueada, ensanchamiento) de ν.

    Sigmoide centrado en el rango intermedio Mössbauer (~10^8.5 s⁻¹): ν lento
    conserva el sextete, ν intermedio añade ensanchamiento máximo y ν rápido
    colapsa hacia el doblete. Devuelve ``(f_blocked_factor, gamma_factor)``;
    con ``log10_nu=None`` es la identidad ``(1, 1)``. Fuente única del modelo
    empírico usado por ``core.physics`` y ``mossbauer_distribution``.
    """
    if log10_nu is None or not np.isfinite(float(log10_nu)):
        return 1.0, 1.0
    lognu = float(log10_nu)
    center = 8.5
    width = 0.55
    dynamic_blocked = 1.0 / (1.0 + np.exp((lognu - center) / width))
    broad = np.exp(-0.5 * ((lognu - center) / 0.75) ** 2)
    return float(dynamic_blocked), 1.0 + 1.6 * float(broad)


def match_positive_area(y: np.ndarray, ref: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Reescala ``y`` para que su área positiva integrada iguale la de ``ref``.

    Si alguna de las áreas no es finita o la de ``y`` es ~0, devuelve ``y``
    sin cambios (comportamiento histórico de la mezcla sextete/doblete).
    """
    try:
        area_ref = float(np.trapezoid(np.maximum(ref, 0.0), v))
        area_y = float(np.trapezoid(np.maximum(y, 0.0), v))
    except AttributeError:  # compatibilidad NumPy antiguo
        area_ref = float(np.trapz(np.maximum(ref, 0.0), v))
        area_y = float(np.trapz(np.maximum(y, 0.0), v))
    if np.isfinite(area_ref) and np.isfinite(area_y) and abs(area_y) > 1e-12:
        return y * (area_ref / area_y)
    return y


def relaxation_empirical_absorption(
    v: np.ndarray,
    delta: float, quad: float, bhf: float,
    gamma1: float, gamma2: float, gamma3: float,
    depth: float, int1: float, int2: float, int3: float,
    blocked_fraction: float,
    log10_nu: float | None = None,
) -> np.ndarray:
    """Modelo fenomenológico de relajación magnética/superparamagnética.

    Interpola entre una fracción bloqueada (sextete magnético) y una fracción
    de relajación rápida (doblete superparamagnético aparente). No es un modelo
    Blume–Tjon dinámico: es una componente interpretativa para no tratar el
    doblete de relajación rápida como fase química independiente por defecto.

    Si se da ``log10_nu`` (ν en s⁻¹), se aplica una transición fenomenológica:
    ν lento conserva el sextete, ν intermedio añade ensanchamiento máximo y ν
    rápido colapsa hacia el doblete. ``blocked_fraction`` actúa como fracción
    bloqueada máxima; con su valor por defecto 1, ``log10_nu`` gobierna toda la
    transición.

    La forma de doblete se escala para que su área integrada sea comparable al
    área del sextete de profundidad unitaria en la malla de velocidades usada.
    Así ``depth`` mantiene el papel de amplitud/área total aproximada.
    """
    f_dyn, g_factor = relaxation_transition_factors(log10_nu)
    f_blocked = max(0.0, min(1.0, float(blocked_fraction))) * f_dyn
    gamma_eff = float(gamma1) * g_factor
    sext = sextet_absorption(
        v, delta, quad, bhf, gamma_eff, gamma2, gamma3,
        1.0, int1, int2, int3,
    )
    doub = doublet_absorption(v, delta, quad, gamma_eff, gamma2, 1.0, int1, int2)
    doub = match_positive_area(doub, sext, v)
    return float(depth) * (f_blocked * sext + (1.0 - f_blocked) * doub)


_PLANCK_H = 6.62607015e-34
_K_BOLTZMANN = 1.380649e-23
_RELAX_RATE_PER_MM_S = E_GAMMA / (_PLANCK_H * 299_792_458_000.0)


def lognormal_diameter_distribution(
    mean_d_nm: float,
    sigma_lognormal: float,
    n_bins: int = 20,
) -> tuple[np.ndarray, np.ndarray]:
    """Malla y pesos lognormales de diámetros (nm).

    ``mean_d_nm`` se interpreta como mediana de la lognormal. Los pesos se
    normalizan a suma 1. La malla cubre aproximadamente ±4σ en log(d).
    """
    median = max(float(mean_d_nm), 1e-6)
    sigma = max(float(sigma_lognormal), 1e-6)
    n = max(1, int(round(n_bins)))
    if n == 1:
        return np.array([median], dtype=float), np.array([1.0], dtype=float)
    lo = median * np.exp(-4.0 * sigma)
    hi = median * np.exp(4.0 * sigma)
    d = np.exp(np.linspace(np.log(max(lo, 1e-6)), np.log(max(hi, lo * 1.001)), n))
    mu = np.log(median)
    w = np.exp(-0.5 * ((np.log(d) - mu) / sigma) ** 2) / np.maximum(d * sigma, 1e-300)
    w = np.maximum(w, 0.0)
    s = float(np.sum(w))
    if not np.isfinite(s) or s <= 0.0:
        w = np.ones_like(d) / d.size
    else:
        w = w / s
    return d.astype(float), w.astype(float)


def neel_log10_nu(
    diameter_nm: np.ndarray | float,
    temperature_k: float,
    log10_keff: float,
    log10_tau0: float = -9.0,
) -> np.ndarray:
    """Néel--Arrhenius: log10(ν/s⁻¹) para partículas esféricas."""
    d_m = np.asarray(diameter_nm, dtype=float) * 1e-9
    volume = np.pi * np.maximum(d_m, 0.0) ** 3 / 6.0
    keff = 10.0 ** float(log10_keff)
    temp = max(float(temperature_k), 1e-9)
    barrier = keff * volume / (_K_BOLTZMANN * temp)
    return -float(log10_tau0) - barrier / np.log(10.0)


def neel_blocking_temperature(
    diameter_nm: float,
    log10_keff: float,
    tau_m: float = 1e-8,
    log10_tau0: float = -9.0,
) -> float:
    """Temperatura de bloqueo aproximada para una partícula esférica."""
    d_m = max(float(diameter_nm), 0.0) * 1e-9
    volume = np.pi * d_m ** 3 / 6.0
    keff = 10.0 ** float(log10_keff)
    tau0 = 10.0 ** float(log10_tau0)
    denom = _K_BOLTZMANN * np.log(max(float(tau_m) / max(tau0, 1e-300), 1.0000001))
    return float(keff * volume / denom) if denom > 0 else float("nan")


def neel_size_relaxation_absorption(
    v: np.ndarray,
    delta: float, quad: float, bhf: float,
    gamma1: float, gamma2: float, gamma3: float,
    depth: float, int1: float, int2: float, int3: float,
    temperature_k: float,
    log10_keff: float,
    mean_d_nm: float,
    sigma_lognormal: float,
    log10_tau0: float = -9.0,
    n_bins: int = 20,
) -> np.ndarray:
    """Relajación Néel--Arrhenius integrada sobre distribución lognormal."""
    diam, weights = lognormal_diameter_distribution(mean_d_nm, sigma_lognormal, n_bins)
    lognus = neel_log10_nu(diam, temperature_k, log10_keff, log10_tau0)
    total = np.zeros_like(np.asarray(v, dtype=float), dtype=float)
    for w, lognu in zip(weights, lognus):
        total += float(w) * relaxation_blume_tjon_two_state_absorption(
            v, delta, quad, bhf, gamma1, gamma2, gamma3,
            1.0, int1, int2, int3, float(np.clip(lognu, -50.0, 50.0)),
        )
    return float(depth) * total


def two_state_exchange_profile(
    v: np.ndarray,
    center_a: float,
    center_b: float,
    gamma: float,
    log10_nu: float,
    polarization: float = 0.0,
) -> np.ndarray:
    """Línea de intercambio estocástico entre dos estados a tasa ν.

    Forma cerrada de Blume para dos frecuencias que intercambian. La tasa se
    introduce como ``log10_nu`` en s⁻¹ y se convierte a unidades de velocidad
    con la relación Doppler del ⁵⁷Fe. En el límite lento devuelve dos
    lorentzianas; en el rápido, una sola línea en el centro promedio.

    ``polarization`` (P ∈ [−1, 1]) desequilibra las POBLACIONES de los dos
    estados, ``p_{1,2} = (1 ± P)/2`` — es el ``SPN = BHF/BSAT`` de NORMOS
    (``siterelx.for``, ``ISIRLX``), o sea el efecto de un campo externo que
    polariza los dos estados. Con P=0 (defecto) las poblaciones son 50/50 y se
    recupera exactamente la fórmula anterior.

    La expresión general es::

        I(v) ∝ Re[ (p₁z₂ + p₂z₁ + w₁ + w₂) / (z₁z₂ + z₁w₂ + z₂w₁) ]

    con ``z_j = Γ/2 + i(v − v_j)`` y tasas de salida ligadas por balance
    detallado (``p₁w₁ = p₂w₂``), parametrizadas como ``w₁ = 2kp₂``,
    ``w₂ = 2kp₁`` para que P=0 dé ``w₁ = w₂ = k``.
    """
    vv = np.asarray(v, dtype=float)
    g = max(float(gamma), 1e-9) / 2.0
    try:
        rate_v = (10.0 ** float(log10_nu)) / _RELAX_RATE_PER_MM_S
    except OverflowError:
        rate_v = 1e12 / _RELAX_RATE_PER_MM_S
    k = max(float(rate_v), 0.0)
    pol = float(np.clip(float(polarization), -1.0, 1.0))
    p1 = 0.5 * (1.0 + pol)
    p2 = 0.5 * (1.0 - pol)
    z1 = g + 1j * (vv - float(center_a))
    z2 = g + 1j * (vv - float(center_b))
    if k <= 0.0:
        # Sin saltos: cada estado aporta según su población.
        return p1 * np.real(g / z1) + p2 * np.real(g / z2)
    if pol == 0.0:
        det = z1 * z2 + k * (z1 + z2)
        det = np.where(np.abs(det) < 1e-300, 1e-300 + 0j, det)
        resp = 0.5 * g * (z1 + z2 + 4.0 * k) / det
        return np.maximum(np.real(resp), 0.0)
    # Sin recortar a ≥0: con poblaciones muy desiguales la forma de Blume tiene
    # regiones negativas (hasta el 27 % de los canales con P=0.9), y NORMOS
    # tampoco las recorta (``ISIRLX`` acumula ``REAL(CC)`` tal cual). Recortar
    # línea a línea rompería la equivalencia y además el total del sexteto
    # suele salir positivo aunque una línea suelta no lo sea.
    return _blume_polarizado(vv, center_a, center_b, g, k, pol)


def _blume_polarizado(vv, center_a, center_b, g, k, pol):
    """Forma cerrada de Blume con poblaciones desiguales (port de ``ISIRLX``).

    Portado literalmente de ``siterelx.for`` (NORMOS), que es la referencia
    publicada. Con ``pol=0`` coincide exactamente con la expresión simétrica
    (comprobado a rms 0), pero con ``pol≠0`` los pesos no son la simple
    generalización por poblaciones: la asimetría entra también en los
    autovalores vía ``RK``.

    Correspondencia de parámetros: ``OME = 2k``, ``DVL0 = (c_b − c_a)/2``,
    ``VELS = (c_a + c_b)/2``, ``WD = 0`` (la anchura va toda en ``z``).
    """
    ome = 2.0 * k
    dvl0 = 0.5 * (float(center_b) - float(center_a))
    vels = 0.5 * (float(center_a) + float(center_b))
    b1 = -0.5 * ome
    h = 0.25 * ome ** 2 - dvl0 ** 2
    rk = -dvl0 * pol * ome
    hk = float(np.hypot(h, rk))
    eta = float(np.sqrt(max(0.5 * (hk + h), 0.0)))
    rnue = float(np.sqrt(max(0.5 * (hk - h), 0.0)))
    xp, yp = eta - b1, rnue
    xn, yn = -eta - b1, -rnue
    if dvl0 <= 0:
        lam1, lam2 = complex(xp, yp), complex(xn, yn)
    else:
        lam1, lam2 = complex(xp, yn), complex(xn, yp)
    bb = complex(ome, -dvl0)
    cc = complex(ome, dvl0)
    den = (cc - lam1) * (bb - lam2)
    if abs(den) < 1e-300:
        return np.zeros_like(vv)
    rk1 = (bb - lam1) / (cc - lam1)
    rk2 = (cc - lam2) / (bb - lam2)
    denom = 1.0 - rk1 * rk2
    if abs(denom) < 1e-300:
        return np.zeros_like(vv)
    ac = 0.5 * (1.0 + pol + rk1 * (1.0 - pol)) * (1.0 - rk2) / denom
    bd = 0.5 * (1.0 - pol + rk2 * (1.0 + pol)) * (1.0 - rk1) / denom
    z = g + 1j * (vels - vv)
    return g * np.real(ac / (lam1 + z) + bd / (lam2 + z))


def two_state_sextet_absorption(
    v: np.ndarray,
    delta: float, quad: float, bhf: float,
    weights: np.ndarray, gammas: np.ndarray,
    log10_nu: float,
    polarization: float = 0.0,
) -> np.ndarray:
    """Sextete de dos estados +BHF ↔ −BHF con pesos/anchuras explícitos por línea.

    Primitivo Blume–Tjon compartido: cada transición intercambia entre la
    frecuencia calculada con +BHF y la calculada con −BHF a tasa ν. Las dos
    convenciones de intensidad del proyecto construyen ``weights``/``gammas``
    y delegan aquí.
    """
    mag = active_sextet_pattern() * (float(bhf) / BHF_DEFAULT_T)
    q = float(quad) * LINE_QUAD_PATTERN
    c_plus = float(delta) + q + mag
    c_minus = float(delta) + q - mag
    out = np.zeros_like(np.asarray(v, dtype=float), dtype=float)
    for ca, cb, g, w in zip(c_plus, c_minus, gammas, weights):
        out += float(w) * two_state_exchange_profile(
            v, float(ca), float(cb), float(g), float(log10_nu),
            float(polarization))
    return out


def relaxation_blume_tjon_two_state_absorption(
    v: np.ndarray,
    delta: float, quad: float, bhf: float,
    gamma1: float, gamma2: float, gamma3: float,
    depth: float, int1: float, int2: float, int3: float,
    log10_nu: float,
    polarization: float = 0.0,
) -> np.ndarray:
    """Modelo dinámico simplificado de dos estados +BHF ↔ -BHF.

    Es la primera versión tipo Blume–Tjon: cada transición intercambia entre la
    frecuencia calculada con +BHF y la calculada con -BHF. Reproduce los límites
    lento (sextete), intermedio (ensanchamiento/coalescencia) y rápido
    (doblete/singlete promediado) sin interpretar la fracción rápida como fase
    química independiente.
    """
    weights = np.array([int3 * int1, int3 * int2, int3, int3, int3 * int2, int3 * int1], dtype=float)
    gammas = float(gamma1) * np.array([1.0, gamma2, gamma3, gamma3, gamma2, 1.0], dtype=float)
    return float(depth) * two_state_sextet_absorption(
        v, delta, quad, bhf, weights, gammas, log10_nu, polarization)


def component_absorption(
    v: np.ndarray, kind: str, p: np.ndarray, *, extras: dict | None = None,
) -> np.ndarray:
    if kind == "Singlete":
        delta, _quad, _bhf, gamma1, _gamma2, _gamma3, depth, int1, _int2, _int3 = p
        return singlet_absorption(v, delta, gamma1, depth, int1)
    if kind == "Doblete":
        delta, quad, _bhf, gamma1, gamma2, _gamma3, depth, int1, int2, _int3 = p
        return doublet_absorption(v, delta, quad, gamma1, gamma2, depth, int1, int2)
    if kind == "Relajacion":
        delta, quad, bhf, gamma1, gamma2, gamma3, depth, int1, int2, int3 = p
        frac = 1.0
        log10_nu = None
        if extras is not None:
            frac = float(extras.get("blocked_fraction", extras.get("relax_fraction", 1.0)))
            if "log10_nu" in extras or "relax_log_nu" in extras:
                log10_nu = float(extras.get("log10_nu", extras.get("relax_log_nu")))
        return relaxation_empirical_absorption(
            v, delta, quad, bhf, gamma1, gamma2, gamma3,
            depth, int1, int2, int3, frac, log10_nu,
        )
    if kind == "BlumeTjon":
        delta, quad, bhf, gamma1, gamma2, gamma3, depth, int1, int2, int3 = p
        log10_nu = 5.0
        if extras is not None:
            log10_nu = float(extras.get("log10_nu", extras.get("relax_log_nu", log10_nu)))
        pol = float(extras.get("polarization",
                                extras.get("relax_polarization", 0.0))) if extras else 0.0
        return relaxation_blume_tjon_two_state_absorption(
            v, delta, quad, bhf, gamma1, gamma2, gamma3,
            depth, int1, int2, int3, log10_nu, pol,
        )
    if kind == "NeelSize":
        delta, quad, bhf, gamma1, gamma2, gamma3, depth, int1, int2, int3 = p
        extras = extras or {}
        return neel_size_relaxation_absorption(
            v, delta, quad, bhf, gamma1, gamma2, gamma3,
            depth, int1, int2, int3,
            temperature_k=float(extras.get("temperature_k", extras.get("neel_temp_k", 300.0))),
            log10_keff=float(extras.get("log10_keff", extras.get("neel_log10_keff", 4.0))),
            mean_d_nm=float(extras.get("mean_d_nm", extras.get("neel_mean_d_nm", 8.0))),
            sigma_lognormal=float(extras.get("sigma_lognormal", extras.get("neel_sigma", 0.25))),
            log10_tau0=float(extras.get("log10_tau0", extras.get("neel_log10_tau0", -9.0))),
            n_bins=int(round(float(extras.get("n_bins", extras.get("neel_bins", 20.0))))),
        )
    if extras:
        return sextet_absorption(
            v, *p,
            treatment=str(extras.get("treatment", "1st_order")),
            beta=float(extras.get("beta", 0.0)),
            n_quad=int(extras.get("n_quad", 20)),
            eta=float(extras.get("eta", 0.0)),
            phi=float(extras.get("phi", 0.0)),
            beam_theta=float(extras.get("beam_theta", 0.0)),
            beam_phi=float(extras.get("beam_phi", 0.0)),
        )
    return sextet_absorption(v, *p)


#: Semianchura del kernel de la fuente, en FWHM. La Lorentziana tiene colas
#: ~1/v², así que truncarla corta: a ±20 FWHM se pierde un 1.6 % del peso, y
#: RENORMALIZAR ese kernel truncado redistribuye el peso perdido al centro y
#: falsea la absorción. Medido contra el binario de SITE (sonda FSO), pasar de
#: ±20 renormalizado a ±200 sin renormalizar baja el rms del modelo de
#: 2.8·10⁻³ a 1.5·10⁻⁴ — 19× mejor.
SOURCE_KERNEL_HALF_WIDTHS = 200.0


def _source_kernel(v: np.ndarray, fwhm: float) -> np.ndarray | None:
    """Kernel Lorentziano de la línea de la fuente, integrado por canal.

    Cada peso es la integral analítica de la Lorentziana sobre la anchura del
    canal (diferencias de arctan): exacto incluso cuando la FWHM de la fuente
    es comparable al paso de la malla. Devuelve ``None`` si no procede
    convolucionar (malla degenerada o fuente ≪ canal).

    **No se renormaliza**: los pesos son las integrales reales y su suma es
    algo menor que 1. El déficit es la cola que queda fuera de la ventana, y
    dejarlo fuera equivale a suponer que allí no hay absorción — exactamente
    la corrección ``WING`` de NORMOS (``sitecalf.for``, rama IFTRAN).
    """
    if v.size < 5 or fwhm <= 0:
        return None
    dv = float(np.median(np.diff(v)))
    if dv <= 0 or fwhm < 0.05 * dv:
        return None
    # Cota superior por tamaño: más allá del propio rango de datos la cola ya
    # solo ve el relleno de borde y no aporta.
    wanted = int(np.ceil(SOURCE_KERNEL_HALF_WIDTHS * fwhm / dv))
    half = max(3, min(wanted, 4 * int(v.size)))
    edges = (np.arange(-half, half + 2, dtype=float) - 0.5) * dv
    g = fwhm / 2.0
    cdf = np.arctan(edges / g)
    return np.diff(cdf) / np.pi


def total_model(
    v: np.ndarray,
    baseline: float,
    slope: float,
    components,
    sat_scale: float | None = None,
    curv: float = 0.0,
    transmission_src: float | None = None,
    curv3: float = 0.0,
    curv4: float = 0.0,
    transmission_frac: float = 1.0,
) -> np.ndarray:
    """Modelo de transmisión.

    ``components`` es lista de ``(kind, params)`` o ``(kind, params, extras)``.

    Si ``sat_scale`` (C>0) se da, se aplica el modelo de absorbente grueso
    (saturación exponencial):

        T = baseline + slope·v − C·(1 − exp(−A_tot/C)),   A_tot = Σ_c A_c.

    En el límite C→∞ se recupera el modelo delgado lineal
    T = baseline + slope·v − A_tot. C es la amplitud de saturación (≈ f_s·baseline).

    Si ``transmission_src`` no es ``None`` (modo ``absorber_model=
    "transmission"``, mejora banco NORMOS §6.3), se calcula la INTEGRAL DE
    TRANSMISIÓN: A_tot se interpreta como profundidad óptica τ(E) y

        T = baseline + slope·v + curv·v² − f_s · L_src ⊗ [1 − exp(−τ)]

    con L_src la línea de la fuente (Lorentziana de FWHM ``transmission_src``
    en mm/s, normalizada; 0 → sin convolución). En el límite fino
    (τ≪1, fuente estrecha) reproduce el modelo delgado.

    ``transmission_frac`` (f_s) es la FRACCIÓN RESONANTE de la fuente: el FSO
    de NORMOS-SITE. Solo una fracción de los fotones que llegan pertenece a la
    línea Mössbauer; el resto atraviesa sin poder absorberse, así que la
    transmisión satura en ``1 − f_s`` y no en 0. Con f_s = 1 (defecto) no hay
    cambio. NO es degenerado con la profundidad: ``depth`` escala τ DENTRO de
    la exponencial y f_s escala el resultado ya saturado — solo se confunden
    en el límite fino.

    ``curv`` añade un término cuadrático de base (efecto geométrico residual
    tras el doblado; mejora banco NORMOS §6.8). ``curv3``/``curv4`` añaden
    los términos cúbico y cuártico (paridad con los fondos BKG(4)/BKG(5) de
    NORMOS, banco-2 §K2). Con todos a 0 no hay cambio.
    """
    a_tot = np.zeros_like(v, dtype=float)
    for comp in components:
        if isinstance(comp, tuple):
            if len(comp) == 3:
                kind, p, extras = comp
                a_tot += component_absorption(v, kind, p, extras=extras)
            else:
                kind, p = comp
                a_tot += component_absorption(v, kind, p)
        else:
            a_tot += sextet_absorption(v, *comp)
    if transmission_src is not None:
        a_eff = 1.0 - np.exp(-a_tot)
        ker = _source_kernel(np.asarray(v, dtype=float), float(transmission_src))
        if ker is not None:
            pad = ker.size // 2
            padded = np.concatenate([np.full(pad, a_eff[0]), a_eff,
                                     np.full(pad, a_eff[-1])])
            a_eff = np.convolve(padded, ker, mode="valid")
        frac = float(transmission_frac)
        if frac != 1.0:
            a_eff = frac * a_eff
    elif sat_scale is not None and np.isfinite(sat_scale) and sat_scale > 0:
        a_eff = sat_scale * (1.0 - np.exp(-a_tot / sat_scale))
    else:
        a_eff = a_tot
    out = baseline + slope * v - a_eff
    if curv or curv3 or curv4:
        # Fondo polinómico hasta v⁴ (banco NORMOS-2 §K2: BKG(3..5) de SITE).
        vv = np.asarray(v, dtype=float)
        out = out + curv * vv ** 2 + curv3 * vv ** 3 + curv4 * vv ** 4
    return out
