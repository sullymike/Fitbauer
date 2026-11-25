"""Diagnóstico de un ajuste: una lista de comprobaciones con veredicto.

Fuente única para la ventana «Diagnóstico del ajuste» de la GUI, el informe y
el CLI. Cada comprobación lleva su estado (``ok``/``warn``/``fail``/``na``),
el valor medido, el umbral (fijo y visible), qué significa y qué hacer.

El veredicto del ajuste sale de TODAS las comprobaciones, no solo del χ²red:
un χ²red de 1.2 con un parámetro en su cota o un residuo con estructura no es
un ajuste «correcto».
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from mossbauer_i18n import tr

# ── Umbrales (fijos; la ventana los muestra) ──────────────────────────────
CHI2_LOW = 0.7          # χ²red por debajo: σ sobrestimada (o modelo que sigue el ruido)
CHI2_WARN = 1.5         # por encima: el modelo no llega al nivel del ruido
CHI2_FAIL = 3.0         # por encima: ajuste poco fiable
LAG1_MAX = 0.35         # |autocorrelación lag-1| del residuo
RUNS_Z_MAX = 2.0        # |z| de la prueba de rachas del residuo
CORR_MAX = 0.95         # |r| entre dos parámetros libres
SWAP_RATIO = 0.5        # intercambio si la asignación cruzada cuesta < la mitad

# Escalas para comparar componentes (intercambio de papeles).
_SWAP_SCALES = {"delta": 0.1, "quad": 0.1, "bhf": 1.0, "gamma1": 0.1}

STATUS_ORDER = {"ok": 0, "na": 0, "info": 0, "warn": 1, "fail": 2}


@dataclass(frozen=True)
class Check:
    key: str
    status: str             # "ok" | "warn" | "fail" | "na"
    title: str
    value: str
    threshold: str
    meaning: str = ""
    action: str = ""
    params: tuple = field(default_factory=tuple)   # claves afectadas


def verdict(checks: list[Check]) -> str:
    """Peor estado de todas las comprobaciones: ``ok``, ``warn`` o ``fail``."""
    worst = max((STATUS_ORDER.get(c.status, 0) for c in checks), default=0)
    return {0: "ok", 1: "warn", 2: "fail"}[worst]


def n_issues(checks: list[Check]) -> int:
    return sum(1 for c in checks if c.status in ("warn", "fail"))


def _fmt(v, nd=3) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    return "—" if not math.isfinite(v) else f"{v:.{nd}g}"


# ── Comprobaciones sueltas ────────────────────────────────────────────────
def check_chi2(stats: dict) -> Check:
    red = float(stats.get("red_chi2", float("nan")))
    thr = tr("diag.chi2_thr", low=CHI2_LOW, warn=CHI2_WARN, fail=CHI2_FAIL)
    title = tr("diag.chi2_title")
    if not math.isfinite(red):
        return Check("chi2", "na", title, "—", thr)
    if red < CHI2_LOW:
        return Check("chi2", "warn", title, _fmt(red), thr,
                     tr("diag.chi2_low_meaning"), tr("diag.chi2_low_action"))
    if red >= CHI2_FAIL:
        return Check("chi2", "fail", title, _fmt(red), thr,
                     tr("diag.chi2_high_meaning"), tr("diag.chi2_high_action"))
    if red >= CHI2_WARN:
        return Check("chi2", "warn", title, _fmt(red), thr,
                     tr("diag.chi2_high_meaning"), tr("diag.chi2_high_action"))
    return Check("chi2", "ok", title, _fmt(red), thr, tr("diag.chi2_ok_meaning"))


def check_residual(stats: dict) -> Check:
    lag1 = float(stats.get("resid_lag1", float("nan")))
    z = float(stats.get("resid_runs_z", float("nan")))
    title = tr("diag.resid_title")
    thr = tr("diag.resid_thr", lag=LAG1_MAX, z=RUNS_Z_MAX)
    value = tr("diag.resid_value", lag=_fmt(lag1), z=_fmt(z))
    if not (math.isfinite(lag1) or math.isfinite(z)):
        return Check("residual", "na", title, "—", thr)
    bad = ((math.isfinite(lag1) and abs(lag1) > LAG1_MAX)
           or (math.isfinite(z) and abs(z) > RUNS_Z_MAX))
    if bad:
        return Check("residual", "warn", title, value, thr,
                     tr("diag.resid_meaning"), tr("diag.resid_action"))
    return Check("residual", "ok", title, value, thr, tr("diag.resid_ok_meaning"))


def check_correlations(correlations: dict | None, label=str) -> Check:
    title = tr("diag.corr_title")
    thr = f"|r| < {CORR_MAX}"
    pairs = list((correlations or {}).get("high_pairs") or [])
    if not correlations:
        return Check("correlations", "na", title, "—", thr)
    if not pairs:
        mx = (correlations or {}).get("max_abs_corr")
        return Check("correlations", "ok", title,
                     tr("diag.corr_max", r=_fmt(mx, 3)) if mx is not None else "—", thr)
    txt = "; ".join(f"{label(p['param1'])} ↔ {label(p['param2'])} (r = {float(p['corr']):+.2f})"
                    for p in pairs[:6])
    if len(pairs) > 6:
        txt += f"; +{len(pairs) - 6}"
    keys = tuple({k for p in pairs for k in (p["param1"], p["param2"])})
    return Check("correlations", "warn", title, txt, thr,
                 tr("diag.corr_meaning"), tr("diag.corr_action"), keys)


def check_convergence(success: bool) -> Check:
    title = tr("diag.conv_title")
    if success:
        return Check("convergence", "ok", title, tr("diag.yes"), tr("diag.conv_thr"))
    return Check("convergence", "fail", title, tr("diag.no"), tr("diag.conv_thr"),
                 tr("diag.conv_meaning"), tr("diag.conv_action"))


def check_errors(result) -> Check:
    title = tr("diag.err_title")
    thr = tr("diag.err_thr")
    if not result.free_keys:
        return Check("errors", "na", title, "—", thr)
    missing = [k for k in result.free_keys
               if not (isinstance(result.errors.get(k), (int, float))
                       and math.isfinite(result.errors[k]) and result.errors[k] > 0)]
    if result.cov is None or missing:
        return Check("errors", "warn", title,
                     tr("diag.err_missing", n=len(missing) if result.cov is not None
                        else len(result.free_keys)), thr,
                     tr("diag.err_meaning"), tr("diag.err_action"), tuple(missing))
    return Check("errors", "ok", title, tr("diag.err_ok"), thr)


def check_bounds(at_bounds: list, label=str) -> Check:
    title = tr("diag.bounds_title")
    thr = tr("diag.bounds_thr")
    if not at_bounds:
        return Check("bounds", "ok", title, tr("diag.none"), thr)
    txt = "; ".join(f"{label(k)} = {_fmt(v, 5)} "
                    f"({tr('diag.min') if side == 'min' else tr('diag.max')} {_fmt(b, 5)})"
                    for k, v, side, b in at_bounds)
    return Check("bounds", "warn", title, txt, thr, tr("diag.bounds_meaning"),
                 tr("diag.bounds_action"), tuple(k for k, *_ in at_bounds))


def check_dependent(outside: list, label=str) -> Check | None:
    if not outside:
        return None
    txt = "; ".join(f"{label(k)} = {_fmt(v, 5)}" for k, v in outside)
    return Check("dependent", "warn", tr("diag.dep_title"), txt, tr("diag.dep_thr"),
                 tr("diag.dep_meaning"), tr("diag.dep_action"), tuple(k for k, _ in outside))


def check_start(result) -> Check | None:
    """De qué arranque sale la solución (solo con multiarranque)."""
    best = getattr(result, "best_start", None) or {}
    starts = getattr(result, "starts", None) or []
    if not best or len(starts) <= 1:
        return None
    title = tr("diag.start_title")
    thr = tr("diag.start_thr")
    lab = best.get("label")
    if lab in ("base", "local"):
        return Check("start", "ok", title, tr("diag.start_yours"), thr)
    n = best.get("n", "?")
    txt = {"perturbed": tr("diag.start_perturbed", n=n),
           "global": tr("diag.start_global", n=n),
           "auto_global": tr("diag.start_auto_global", n=n)}.get(lab, str(lab))
    return Check("start", "warn", title, txt, thr, tr("diag.start_meaning"),
                 tr("diag.start_action"))


def check_multiple_minima(result, label=str) -> Check | None:
    """Otros arranques con χ² indistinguible y parámetros distintos (> 3σ)."""
    starts = getattr(result, "starts", None) or []
    if len(starts) <= 1 or not result.free_keys:
        return None
    title = tr("diag.minima_title")
    red = float(result.stats.get("red_chi2", 1.0) or 1.0)
    tol = max(1.0, red if math.isfinite(red) else 1.0)       # Δχ² indistinguible
    thr = tr("diag.minima_thr", d=_fmt(tol, 2))
    best_cost = min(s["cost"] for s in starts)
    best = min(starts, key=lambda s: s["cost"])
    xb = np.asarray(best["x"], dtype=float)
    sig = np.array([float(result.errors.get(k, float("nan"))) for k in result.free_keys])
    if sig.size != xb.size:
        # El vector del optimizador no se corresponde 1:1 con free_keys (p. ej.
        # con el centro de doblado libre): no se puede comparar por parámetro.
        return None
    rivales = []
    for s in starts:
        if s is best or len(s["x"]) != xb.size:
            continue
        if 2.0 * (s["cost"] - best_cost) > tol:
            continue
        d = np.abs(np.asarray(s["x"], dtype=float) - xb)
        ok = np.isfinite(sig) & (sig > 0)
        far = np.where(ok, d > 3.0 * np.where(ok, sig, 1.0), False)
        if np.any(far):
            rivales.append((s, [result.free_keys[i] for i in np.flatnonzero(far)]))
    if not rivales:
        return Check("minima", "ok", title, tr("diag.minima_one"), thr)
    keys = sorted({k for _s, ks in rivales for k in ks})
    txt = tr("diag.minima_value", n=len(rivales),
             params=", ".join(label(k) for k in keys[:6]))
    return Check("minima", "warn", title, txt, thr, tr("diag.minima_meaning"),
                 tr("diag.minima_action"), tuple(keys))


def component_swaps(start_values: dict, final_values: dict, kinds: dict[int, str]
                    ) -> list[tuple[int, int]]:
    """Parejas de componentes del mismo tipo que han intercambiado papeles.

    Compara δ, ΔEQ, BHF y Γ (en escalas típicas) de cada componente al empezar
    y al terminar: si la asignación cruzada a↔b se parece mucho más que la
    directa, las dos componentes se han cambiado el sitio.
    """
    def dist(va: dict, a: int, vb: dict, b: int) -> float:
        tot = 0.0
        for name, sc in _SWAP_SCALES.items():
            ka, kb = f"s{a}_{name}", f"s{b}_{name}"
            if ka in va and kb in vb:
                tot += ((float(va[ka]) - float(vb[kb])) / sc) ** 2
        return math.sqrt(tot)

    idxs = sorted(kinds)
    out = []
    for i, a in enumerate(idxs):
        for b in idxs[i + 1:]:
            if kinds[a] != kinds[b]:
                continue
            direct = dist(start_values, a, final_values, a) + dist(start_values, b, final_values, b)
            cross = dist(start_values, a, final_values, b) + dist(start_values, b, final_values, a)
            if direct > 1.0 and cross < SWAP_RATIO * direct:
                out.append((a, b))
    return out


def check_swaps(swaps: list[tuple[int, int]]) -> Check | None:
    title = tr("diag.swap_title")
    thr = tr("diag.swap_thr")
    if not swaps:
        return Check("swap", "ok", title, tr("diag.none"), thr)
    txt = ", ".join(tr("diag.swap_pair", a=a, b=b) for a, b in swaps)
    return Check("swap", "warn", title, txt, thr, tr("diag.swap_meaning"),
                 tr("diag.swap_action"))


# ── Diagnóstico completo ──────────────────────────────────────────────────
def diagnose_discrete(result, *, start_values: dict | None = None,
                      kinds: dict[int, str] | None = None,
                      dependent_outside: list | None = None,
                      label=str) -> list[Check]:
    """Todas las comprobaciones de un ajuste discreto (``core.fit_engine.FitResult``)."""
    from core.fit_engine import parameters_at_bounds
    checks: list[Check] = [
        check_convergence(bool(result.success)),
        check_chi2(result.stats),
        check_residual(result.stats),
        check_errors(result),
        check_bounds(parameters_at_bounds(result), label),
        check_correlations(result.correlations, label),
    ]
    for extra in (check_dependent(dependent_outside or [], label),
                  check_start(result), check_multiple_minima(result, label)):
        if extra is not None:
            checks.append(extra)
    if start_values and kinds and len(kinds) > 1:
        checks.append(check_swaps(component_swaps(start_values, result.values, kinds)))
    return checks


def diagnose_stats(stats: dict) -> list[Check]:
    """Comprobaciones disponibles solo con estadísticos (ajuste de distribución)."""
    return [check_chi2(stats), check_residual(stats)]
