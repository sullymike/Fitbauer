"""Motor de ajuste discreto, puro (sin Tk).

API basada en un :class:`FitState` plano (diccionarios y arrays). El mismo
motor puede ser invocado desde la GUI Tk legacy, la GUI Qt o un script CLI.

Cobertura actual: ajuste discreto (sextetes / doblete / singlete) con
multistart determinista, pérdida robusta (linear / soft_l1 / huber),
verosimilitud Gauss o Poisson IRLS, ajuste opcional de vmax / folding
center / σ Voigt, y modelo de absorbente fino (lineal) o grueso
(saturación) vía ``sat_scale``.

El modo de distribución P(BHF) sigue en ``mossbauer_distribution.py``;
este motor lo deja fuera por ahora.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy.optimize import least_squares, differential_evolution

from core.physics import (
    LINE_PROFILE_KIND as _DEFAULT_PROFILE,  # noqa: F401 (sólo doc)
    component_absorption,
    sextet_absorption,
    total_model,
)
from core.constants import SEXTET_PARAM_NAMES
from core.folding import fold_integer_or_half
from core.profile_likelihood import asymmetric_intervals


# ── Tipos públicos ────────────────────────────────────────────────────────


@dataclass
class Component:
    """Configuración de una componente del modelo discreto."""
    idx: int
    enabled: bool = False
    kind: str = "Sextete"            # "Sextete" / "Doblete" / "Singlete"
    intensity_mode: str = "free"     # "free" / "texture"
    quad_treatment: str = "1st_order"
    # "1st_order" / "kundig_fixed" / "kundig_powder"


@dataclass
class FitState:
    """Estado completo necesario para evaluar el modelo y lanzar un ajuste.

    Todos los campos son tipos planos (numpy / dict / list) sin referencias
    a Tk u otras dependencias de UI.
    """
    velocity: np.ndarray
    y_data: np.ndarray
    sigma_data: np.ndarray | None       # ruido (Poisson normalizado o constante)
    values: dict[str, float]            # todos los parámetros (sN_*, baseline, slope, vmax, voigt_sigma, sat_scale)
    fixed: dict[str, bool]
    bounds: dict[str, tuple[float, float]]
    components: list[Component]
    constraints: list[dict] = field(default_factory=list)
    # opciones
    likelihood: str = "gauss"           # "gauss" / "poisson"
    robust_loss: str = "linear"         # "linear" / "soft_l1" / "huber"
    line_profile: str = "Lorentziana"   # "Lorentziana" / "Voigt"
    voigt_sigma: float = 0.05
    propagate_calib: bool = False
    sigma_vmax: float | None = None     # σ_calib si propagate_calib=True
    global_opt: bool = False            # pre-pasada DE
    fit_velocity: bool = False
    fit_center: bool = False
    fit_sigma: bool = False
    absorber_model: str = "thin"        # "thin" / "thickness"
    multistart_n: int = 8               # nº de réplicas perturbadas (+1 base)
    # Re-folding del centro (portado del Tk): cuentas crudas sin doblar y
    # normalización de referencia. Si se proporcionan y fit_center=True, el
    # residuo vuelve a doblar las cuentas en el centro de prueba en cada
    # iteración (recalculando y y σ), igual que la GUI Tk. Sin ellas, fit_center
    # no afecta al modelo (datos ya doblados).
    counts: np.ndarray | None = None
    norm_factor: float | None = None


@dataclass
class FitResult:
    values: dict[str, float]
    errors: dict[str, float]
    free_keys: list[str]
    cov: np.ndarray | None
    stats: dict[str, float]
    correlations: dict[str, object]
    n_starts: int
    success: bool


# ── Utilidades puras ──────────────────────────────────────────────────────


def apply_constraints(values: dict[str, float], constraints: list[dict]) -> dict[str, float]:
    """``target = factor·source + offset`` aplicado in-place sobre una copia."""
    out = dict(values)
    for c in constraints:
        try:
            t = c["target"]
            s = c["source"]
            factor = float(c.get("factor", 1.0))
            offset = float(c.get("offset", 0.0))
        except (KeyError, TypeError, ValueError):
            continue
        if s in out and t in out:
            out[t] = factor * out[s] + offset
    return out


def _refold_at_center(
    counts: np.ndarray, center: float, fallback_norm: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Re-pliega las cuentas crudas en ``center`` y devuelve (y, σ) normalizados.

    Réplica del ``data_for_center`` de la GUI Tk: dobla al estilo Normos, normaliza
    por el percentil 90 (cae a ``fallback_norm`` si es 0) y estima σ Poisson del
    promedio de dos canales (Var ≈ folded/2), con un suelo para evitar pesos
    infinitos.
    """
    folded, _pairs = fold_integer_or_half(counts, center)
    if folded.size:
        norm = float(np.percentile(folded, 90))
    else:
        norm = fallback_norm
    if not norm:
        norm = fallback_norm or 1.0
    y = folded / norm
    sig = np.sqrt(np.maximum(folded / 2.0, 1.0)) / max(norm, 1e-12)
    return y, np.maximum(sig, 1e-9)


def _build_components_list(values: dict[str, float], components: list[Component]) -> list[tuple]:
    """Construye la lista que ``total_model`` espera."""
    out = []
    for comp in components:
        if not comp.enabled:
            continue
        p = f"s{comp.idx}_"
        params = np.array(
            [values.get(p + name, 0.0) for name in SEXTET_PARAM_NAMES], dtype=float
        )
        if comp.kind == "Sextete" and comp.quad_treatment != "1st_order":
            beta_deg = float(values.get(f"s{comp.idx}_beta", 0.0))
            extras = {
                "treatment": comp.quad_treatment,
                "beta": float(np.deg2rad(beta_deg)),
                "n_quad": 20,
            }
            out.append((comp.kind, params, extras))
        else:
            out.append((comp.kind, params))
    return out


def model_from_values(
    velocity: np.ndarray,
    values: dict[str, float],
    components: list[Component],
    constraints: list[dict] | None = None,
    absorber_model: str = "thin",
) -> np.ndarray:
    """Evalúa el modelo total dado un estado de parámetros plano."""
    vals = apply_constraints(values, constraints or [])
    comps = _build_components_list(vals, components)
    baseline = float(vals.get("baseline", 1.0))
    slope = float(vals.get("slope", 0.0))
    sat_scale: float | None = None
    if absorber_model == "thickness":
        s = vals.get("sat_scale")
        if s is not None:
            try:
                s = float(s)
                if np.isfinite(s) and s > 0:
                    sat_scale = s
            except (TypeError, ValueError):
                pass
    return total_model(velocity, baseline, slope, comps, sat_scale=sat_scale)


# ── Construcción del residual ─────────────────────────────────────────────


def _make_residual(state: FitState, free_keys: list[str]) -> Callable[[np.ndarray], np.ndarray]:
    """Crea la función residuo a minimizar.

    El vector ``x`` contiene primero los valores de ``free_keys``, después
    (opcionalmente) ``vmax``, ``center`` y ``voigt_sigma`` si están como
    parámetros libres globales.
    """
    base_values = dict(state.values)
    y = state.y_data
    sigma_data = state.sigma_data
    propagate = state.propagate_calib and state.sigma_vmax is not None
    sigma_vmax = float(state.sigma_vmax) if state.sigma_vmax is not None else 0.0
    likelihood = state.likelihood
    profile = state.line_profile
    fit_velocity = state.fit_velocity
    fit_center = state.fit_center
    fit_sigma = state.fit_sigma and profile == "Voigt"
    # Re-folding del centro (portado del Tk): sólo si tenemos las cuentas crudas.
    counts = state.counts
    can_refold = fit_center and counts is not None
    fallback_norm = float(state.norm_factor) if state.norm_factor else 1.0

    # Aplicamos el perfil globalmente (variable mutable en core.physics).
    from core import physics as _phys

    def residual(x: np.ndarray) -> np.ndarray:
        # 1. Reconstruir valores a partir de free_keys.
        vals = dict(base_values)
        for k, v in zip(free_keys, x[:len(free_keys)]):
            vals[k] = float(v)
        pos = len(free_keys)
        vmax = float(x[pos]) if fit_velocity else float(vals.get("vmax", 0.0))
        pos += 1 if fit_velocity else 0
        center = float(x[pos]) if fit_center else float(vals.get("center", 0.0))
        pos += 1 if fit_center else 0
        if fit_sigma:
            _phys.VOIGT_SIGMA = max(float(x[pos]), 1e-9)
            pos += 1
        # 2. Aplicar perfil de línea global.
        _phys.LINE_PROFILE_KIND = profile
        if profile == "Voigt" and not fit_sigma:
            _phys.VOIGT_SIGMA = max(float(state.voigt_sigma), 1e-9)
        # 3. Evaluar el modelo.
        if velocity_scaler is not None:
            v = velocity_scaler(vmax)
        else:
            v = state.velocity
        m = model_from_values(v, vals, state.components, state.constraints,
                              absorber_model=state.absorber_model)
        # 4. Datos: re-doblar las cuentas en el centro de prueba si procede; así
        #    el ajuste del centro es físicamente real (cambia y y σ por iteración).
        if can_refold:
            y_use, sig_fold = _refold_at_center(counts, center, fallback_norm)
            if y_use.size != m.size:   # malla incompatible → no re-doblar
                y_use, sig_fold = y, sigma_data
        else:
            y_use, sig_fold = y, sigma_data
        # 5. σ por canal.
        if likelihood == "poisson":
            sig = np.sqrt(np.maximum(np.abs(m), 1e-12))
        else:
            sig = sig_fold
        if sig is None:
            sig_use = np.ones_like(m)
        else:
            sig_use = np.asarray(sig, dtype=float)
        if propagate and fit_velocity and vmax > 0:
            # Sensibilidad a la ESCALA vmax (portado del Tk, forma correcta):
            #   ∂T/∂v_max|_i = (∂T/∂v)|_i · (v_i/v_max),  pues v_i = v_max·(…),
            # de modo que σ_eff² = σ² + (∂T/∂v_max · σ_vmax)². Pesa en los flancos.
            dT_dv = np.gradient(m, v)
            dT_dvmax = dT_dv * (v / vmax)
            sig_use = np.sqrt(sig_use ** 2 + (dT_dvmax * sigma_vmax) ** 2)
        return (m - y_use) / np.maximum(sig_use, 1e-12)

    # Si fit_velocity está activo, la velocidad se reescala con x[pos_vmax].
    if fit_velocity:
        # ``state.velocity`` se asume ya construida con un vmax_ref; al cambiar
        # vmax, la velocidad reescala linealmente.
        v_ref = state.velocity.copy()
        vmax_ref = float(state.values.get("vmax", 0.0)) or float(np.max(np.abs(v_ref))) or 1.0

        def velocity_scaler(vmax: float) -> np.ndarray:
            if vmax == 0:
                return v_ref
            return v_ref * (vmax / vmax_ref)
    else:
        velocity_scaler = None

    return residual


# ── Ajuste discreto ───────────────────────────────────────────────────────


def fit_discrete(state: FitState, progress_cb: Callable[[str], None] | None = None) -> FitResult:
    """Ejecuta el ajuste discreto y devuelve los resultados.

    No tiene side effects sobre ``state``: la copia interna de valores se
    actualiza en el resultado pero ``state.values`` queda intacto.
    """
    if progress_cb is None:
        progress_cb = lambda _msg: None

    # 1. Localizar parámetros activos.
    target_keys = {c["target"] for c in (state.constraints or []) if "target" in c}
    free_keys: list[str] = []
    for key in state.values:
        if key in ("vmax", "center", "voigt_sigma", "sat_scale"):
            continue
        # Solo claves de componente o globales del modelo (baseline/slope).
        if key.startswith("s") and "_" in key:
            comp_idx = int(key[1:].split("_", 1)[0])
            active = any(c.idx == comp_idx and c.enabled for c in state.components)
            if not active:
                continue
        if key in target_keys:
            continue
        if state.fixed.get(key):
            continue
        free_keys.append(key)
    # sat_scale solo libre si modo grueso
    if state.absorber_model == "thickness" and "sat_scale" in state.values and not state.fixed.get("sat_scale"):
        free_keys.append("sat_scale")

    # 2. x0 / bounds.
    x0 = [state.values[k] for k in free_keys]
    lo = [state.bounds.get(k, (-np.inf, np.inf))[0] for k in free_keys]
    hi = [state.bounds.get(k, (-np.inf, np.inf))[1] for k in free_keys]

    if state.fit_velocity and "vmax" in state.values:
        x0.append(abs(state.values["vmax"]))
        lo.append(state.bounds.get("vmax", (1.0, 15.0))[0])
        hi.append(state.bounds.get("vmax", (1.0, 15.0))[1])
    if state.fit_center and "center" in state.values:
        x0.append(state.values["center"])
        lo.append(state.bounds.get("center", (250.0, 263.0))[0])
        hi.append(state.bounds.get("center", (250.0, 263.0))[1])
    if state.fit_sigma and state.line_profile == "Voigt" and "voigt_sigma" in state.values:
        x0.append(state.values["voigt_sigma"])
        lo.append(state.bounds.get("voigt_sigma", (0.0, 1.0))[0])
        hi.append(state.bounds.get("voigt_sigma", (0.0, 1.0))[1])

    x0_arr = np.clip(np.array(x0, dtype=float), lo, hi)
    lo_arr = np.array(lo, dtype=float)
    hi_arr = np.array(hi, dtype=float)

    if x0_arr.size == 0:
        return FitResult(values=dict(state.values), errors={}, free_keys=free_keys,
                         cov=None, stats={}, correlations={}, n_starts=0, success=False)

    residual = _make_residual(state, free_keys)

    # 3. Multistart determinista.
    rng = np.random.default_rng(12345)
    span = hi_arr - lo_arr
    candidates = [x0_arr]
    for _ in range(max(0, state.multistart_n)):
        trial = x0_arr.copy()
        for i in range(trial.size):
            w = span[i] if np.isfinite(span[i]) and span[i] > 0 else 0.0
            trial[i] += rng.normal(0.0, 0.12 * w)
        candidates.append(np.clip(trial, lo_arr, hi_arr))

    # 4. Opcional: pre-pasada Differential Evolution.
    if state.global_opt:
        progress_cb("Optimización global (DE)...")
        try:
            de = differential_evolution(
                lambda x: 0.5 * float(np.dot(residual(x), residual(x))),
                bounds=list(zip(lo_arr.tolist(), hi_arr.tolist())),
                seed=12345, maxiter=60, tol=1e-4, polish=False, init="sobol",
                updating="deferred",
            )
            candidates.insert(0, np.clip(de.x, lo_arr, hi_arr))
        except Exception:
            pass

    # 5. TRF desde cada candidato; nos quedamos con el de menor coste.
    ls_kwargs: dict = {}
    if state.robust_loss in ("soft_l1", "huber"):
        ls_kwargs["loss"] = state.robust_loss
    result = None
    n_starts = 0
    for cand in candidates:
        n_starts += 1
        progress_cb(f"Ajuste {n_starts}/{len(candidates)}...")
        try:
            res_i = least_squares(residual, cand, bounds=(lo_arr, hi_arr),
                                   max_nfev=7000, **ls_kwargs)
        except Exception:
            continue
        if result is None or res_i.cost < result.cost:
            result = res_i

    if result is None:
        return FitResult(values=dict(state.values), errors={}, free_keys=free_keys,
                         cov=None, stats={}, correlations={}, n_starts=n_starts, success=False)

    # 6. Covarianza aproximada.
    cov = None
    errors: dict[str, float] = {}
    correlations: dict[str, object] = {}
    n_obs = state.y_data.size
    n_par = len(result.x)
    if n_obs > n_par and result.jac.size:
        try:
            _, sv, vt = np.linalg.svd(result.jac, full_matrices=False)
            threshold = np.finfo(float).eps * max(result.jac.shape) * sv[0]
            sv = sv[sv > threshold]
            vt = vt[:sv.size]
            cov_all = (vt.T / (sv ** 2)) @ vt
            cov_all *= 2.0 * result.cost / max(1, n_obs - n_par)
            cov = cov_all[:len(free_keys), :len(free_keys)]
            for key, err in zip(free_keys, np.sqrt(np.maximum(np.diag(cov), 0.0))):
                errors[key] = float(err)
            correlations = _correlation_summary(cov, free_keys)
        except Exception:
            cov = None
            errors = {}

    # 7. Aplica los valores finales (sin tocar state).
    values_final = dict(state.values)
    for k, v in zip(free_keys, result.x[:len(free_keys)]):
        values_final[k] = float(v)
    values_final = apply_constraints(values_final, state.constraints or [])
    pos = len(free_keys)
    if state.fit_velocity:
        values_final["vmax"] = float(result.x[pos]); pos += 1
    if state.fit_center:
        values_final["center"] = float(result.x[pos]); pos += 1
    if state.fit_sigma and state.line_profile == "Voigt":
        values_final["voigt_sigma"] = float(result.x[pos])

    # 8. Estadísticos básicos.
    final_residual = residual(result.x)
    rss = float(np.sum(final_residual ** 2))
    dof = max(1, n_obs - n_par)
    red_chi2 = rss / dof if dof > 0 else float("nan")
    aic = n_obs * np.log(max(rss / n_obs, 1e-300)) + 2 * n_par
    bic = n_obs * np.log(max(rss / n_obs, 1e-300)) + n_par * np.log(n_obs)
    stats = {
        "chi2": rss,
        "red_chi2": red_chi2,
        "dof": float(dof),
        "n_params": float(n_par),
        "aic": float(aic),
        "bic": float(bic),
        "rss": rss,
    }

    return FitResult(values=values_final, errors=errors, free_keys=free_keys,
                     cov=cov, stats=stats, correlations=correlations,
                     n_starts=n_starts, success=result.success)


def _correlation_summary(cov: np.ndarray, free_keys: list[str]) -> dict[str, object]:
    """Resumen: correlación máxima y parejas con |r| ≥ 0.95."""
    if cov is None or cov.size == 0:
        return {}
    d = np.sqrt(np.maximum(np.diag(cov), 0.0))
    safe = np.where(d > 0, d, 1.0)
    corr = cov / np.outer(safe, safe)
    np.fill_diagonal(corr, 0.0)
    if corr.size == 0:
        return {}
    idx = np.unravel_index(np.argmax(np.abs(corr)), corr.shape)
    max_pair = (free_keys[int(idx[0])], free_keys[int(idx[1])]) if idx[0] != idx[1] else ()
    high_pairs = []
    for i in range(len(free_keys)):
        for j in range(i + 1, len(free_keys)):
            r = float(corr[i, j])
            if abs(r) >= 0.95:
                high_pairs.append({"param1": free_keys[i], "param2": free_keys[j], "corr": r})
    return {
        "max_abs_corr": float(np.max(np.abs(corr))),
        "max_pair": list(max_pair),
        "high_pairs": high_pairs,
    }


# ── Análisis de errores (portado del Tk, puro y testeable) ─────────────────


@dataclass
class BootstrapResult:
    """Resultado del bootstrap Monte Carlo de errores."""
    base: FitResult
    std: dict[str, float]                 # σ(MC) por parámetro libre
    samples: dict[str, list[float]]       # réplicas aceptadas por parámetro
    n_ok: int                             # nº de réplicas que convergieron
    n_rep: int                            # nº de réplicas solicitadas


def _replica_state(
    state: FitState, values: dict[str, float], y_data: np.ndarray,
    sigma_data: np.ndarray | None, *,
    extra_fixed: dict[str, bool] | None = None, multistart_n: int = 1,
) -> FitState:
    """Sub-estado para una réplica (bootstrap) o un punto de perfil.

    Conserva el modelo y las opciones relevantes (componentes, restricciones,
    verosimilitud, pérdida robusta, perfil de línea, σ-Voigt y modelo de
    absorbente) pero NO re-ajusta la calibración (vmax/center/σ) y reduce el
    multiarranque. Copiar ``absorber_model`` corrige un descuido de la GUI Qt,
    que dejaba las réplicas en modo fino aunque el ajuste fuese de absorbente
    grueso.
    """
    fixed = dict(state.fixed)
    if extra_fixed:
        fixed.update(extra_fixed)
    return FitState(
        velocity=state.velocity, y_data=y_data, sigma_data=sigma_data,
        values=dict(values), fixed=fixed, bounds=dict(state.bounds),
        components=state.components, constraints=state.constraints,
        likelihood=state.likelihood, robust_loss=state.robust_loss,
        line_profile=state.line_profile, voigt_sigma=state.voigt_sigma,
        absorber_model=state.absorber_model, multistart_n=multistart_n,
    )


def bootstrap_errors(
    state: FitState, *, n_rep: int = 30, seed: int = 24680,
    base: FitResult | None = None,
    progress_cb: Callable[[str, int, int], None] | None = None,
) -> BootstrapResult:
    """Estima errores por remuestreo Monte Carlo (modo discreto).

    Ajusta el modelo base, genera ``n_rep`` espectros sintéticos a partir de él
    y re-ajusta cada uno; la desviación estándar (muestral, ddof=1) de los
    parámetros libres es la incertidumbre. En verosimilitud Poisson, si se
    dispone de ``norm_factor``, simula cuentas Poisson reales (mejora del Tk);
    en otro caso usa ruido gaussiano con la σ de los datos.
    """
    if progress_cb is None:
        progress_cb = lambda *_: None
    if base is None:
        base = fit_discrete(state)
    if not base.free_keys:
        return BootstrapResult(base=base, std={}, samples={}, n_ok=0, n_rep=n_rep)

    v = state.velocity
    model0 = model_from_values(v, base.values, state.components,
                               state.constraints, absorber_model=state.absorber_model)
    sigma = state.sigma_data if state.sigma_data is not None else np.ones_like(model0) * 0.005
    rng = np.random.default_rng(seed)
    poisson = state.likelihood == "poisson" and state.norm_factor not in (None, 0)
    norm = float(state.norm_factor) if poisson else 1.0

    samples: dict[str, list[float]] = {k: [] for k in base.free_keys}
    for i in range(int(n_rep)):
        progress_cb(f"Bootstrap {i + 1}/{n_rep}", i + 1, n_rep)
        if poisson:
            # c_sim ~ Poisson(λ = model0·norm·2) / 2  (promedio de dos canales).
            lam = np.maximum(model0 * norm * 2.0, 0.0)
            y_sim = (rng.poisson(lam).astype(float) / 2.0) / norm
        else:
            y_sim = model0 + rng.normal(0.0, sigma)
        sub = _replica_state(state, base.values, y_sim, sigma, multistart_n=1)
        try:
            r = fit_discrete(sub)
        except Exception:
            continue
        if r.values:
            for k in base.free_keys:
                samples[k].append(float(r.values.get(k, float("nan"))))

    std = {
        k: (float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0)
        for k, vals in samples.items()
    }
    n_ok = len(samples[base.free_keys[0]]) if base.free_keys else 0
    return BootstrapResult(base=base, std=std, samples=samples, n_ok=n_ok, n_rep=int(n_rep))


def profile_likelihood(
    state: FitState, *, base: FitResult | None = None,
    points_per_side: int = 7, spans: tuple[float, ...] = (3.0, 5.0),
    max_nfev: int = 2000,
    progress_cb: Callable[[str, int, int], None] | None = None,
) -> dict[str, dict]:
    """Intervalos de confianza asimétricos por verosimilitud perfilada.

    Para cada parámetro libre del ajuste base: lo fija en una rejilla en torno
    al óptimo, re-ajusta el resto, calcula Δχ²(p) y localiza los cruces Δχ²=1
    (1σ) y Δχ²=4 (2σ). El escaneo es adaptativo (portado del Tk): empieza en
    ±``spans[0]``·σ y se amplía si Δχ²=1 no se cruza en un lado con margen
    frente al límite físico. Devuelve ``{clave: {best, scan_values, d_chi2,
    minus_1s, plus_1s, minus_2s, plus_2s}}``.
    """
    if progress_cb is None:
        progress_cb = lambda *_: None
    if base is None:
        base = fit_discrete(state)
    if not base.free_keys:
        return {}
    chi2_min = float(base.stats.get("chi2", 0.0))
    free_keys = list(base.free_keys)

    def _cost_with_fixed(key: str, val: float) -> float:
        sub = _replica_state(
            state, {**base.values, key: float(val)}, state.y_data,
            state.sigma_data, extra_fixed={key: True}, multistart_n=2,
        )
        try:
            r = fit_discrete(sub)
            return float(r.stats.get("chi2", float("inf")))
        except Exception:
            return float("inf")

    results: dict[str, dict] = {}
    n = len(free_keys)
    for i, key in enumerate(free_keys, 1):
        progress_cb(f"Perfilando {key} ({i}/{n})", i, n)
        best = float(base.values[key])
        sigma_est = float(base.errors.get(key) or 0.0)
        if sigma_est <= 0:
            sigma_est = max(0.05 * (abs(best) + 1.0), 1e-6)
        lo_b, hi_b = state.bounds.get(key, (best - 5 * sigma_est, best + 5 * sigma_est))
        scan_vals = np.array([])
        d_chi2 = np.array([])
        for span in spans:
            left = np.linspace(max(lo_b, best - span * sigma_est), best, points_per_side)
            right = np.linspace(best, min(hi_b, best + span * sigma_est), points_per_side)
            grid = np.unique(np.concatenate([left, right]))
            costs = np.array([_cost_with_fixed(key, float(val)) for val in grid])
            d = costs - chi2_min
            scan_vals, d_chi2 = grid, d
            bracket_left = any(d[j] >= 1.0 for j, val in enumerate(grid) if val < best)
            bracket_right = any(d[j] >= 1.0 for j, val in enumerate(grid) if val > best)
            headroom_left = (best - lo_b) > span * sigma_est * 1.05
            headroom_right = (hi_b - best) > span * sigma_est * 1.05
            if (bracket_left or not headroom_left) and (bracket_right or not headroom_right):
                break
        intervals = asymmetric_intervals(scan_vals, d_chi2, best)
        results[key] = {
            "best": best,
            "scan_values": scan_vals.tolist(),
            "d_chi2": d_chi2.tolist(),
            **intervals,
        }
    return results
