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

# Ajustes de distribución
EDGE_PILEUP_MAX = 0.3   # P en el bin extremo / máximo de P: la malla se queda corta
COMP_SHARE_MIN = 0.02   # gaussiana (VBF) con menos del 2 % del área: sobra
SHARP_SHARE_MIN = 0.01  # componente nítida con menos del 1 % del área: sobra
#: Histograma regularizado: k_eff / parámetros posibles por encima de esto =
#: la regularización casi no actúa (cada bin va por libre).
REG_DOF_MAX = 0.9
#: Desplazamiento de línea por unidad de la variable distribuida (mm/s): las
#: líneas externas del sextete (1/6) por tesla, cada línea del doblete por
#: mm/s de ΔEQ y todas las líneas por mm/s de δ.
_LINE_SHIFT = {"quad": 0.5, "delta": 1.0}

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


# ── Ajustes de distribución ───────────────────────────────────────────────
def _at_bounds(outer, rel_tol: float = 1e-4) -> list:
    """``outer``: (clave, valor, cota_inf, cota_sup) → las que tocan una cota."""
    out = []
    for key, v, lo, hi in outer or ():
        v, lo, hi = float(v), float(lo), float(hi)
        span = hi - lo if math.isfinite(hi - lo) and hi > lo else max(1.0, abs(v))
        tol = rel_tol * span
        if math.isfinite(lo) and v <= lo + tol:
            out.append((key, v, "min", lo))
        elif math.isfinite(hi) and v >= hi - tol:
            out.append((key, v, "max", hi))
    return out


def check_convergence_dist(success: bool, budget_exhausted: bool) -> Check:
    if not success:
        return check_convergence(False)
    if budget_exhausted:
        return Check("convergence", "warn", tr("diag.conv_title"), tr("diag.conv_budget"),
                     tr("diag.conv_thr"), tr("diag.conv_budget_meaning"),
                     tr("diag.conv_budget_action"))
    return check_convergence(True)


def edge_ratio(probability) -> float:
    """``max(P en el borde de la malla) / max(P)`` (1D: primer y último bin;
    2D: todo el contorno)."""
    p = np.asarray(probability, dtype=float)
    if p.size == 0 or not np.all(np.isfinite(p)):
        return float("nan")
    top = float(np.max(p))
    if top <= 0:
        return float("nan")
    if p.ndim == 1:
        borde = max(p[0], p[-1])
    else:
        borde = max(p[0, :].max(), p[-1, :].max(), p[:, 0].max(), p[:, -1].max())
    return float(borde) / top


def check_edge(ratio: float) -> Check:
    title = tr("diag.edge_title")
    thr = tr("diag.edge_thr", r=EDGE_PILEUP_MAX)
    if not math.isfinite(ratio):
        return Check("edge", "na", title, "—", thr)
    val = tr("diag.edge_value", pct=f"{100.0 * ratio:.0f}")
    if ratio > EDGE_PILEUP_MAX:
        return Check("edge", "warn", title, val, thr, tr("diag.edge_meaning"),
                     tr("diag.edge_action"))
    return Check("edge", "ok", title, val, thr, tr("diag.edge_ok_meaning"))


def line_shift_per_unit(variable: str) -> float:
    if variable == "bhf":
        from core.constants import LINE_POS_33T
        return abs(float(LINE_POS_33T[0])) / 33.0
    return _LINE_SHIFT.get(variable, float("nan"))


def check_mesh(centers, variable: str, gamma) -> Check | None:
    """Paso de la malla, en mm/s sobre las líneas, frente a la anchura Γ."""
    c = np.asarray(centers, dtype=float)
    try:
        g = float(gamma)
    except (TypeError, ValueError):
        return None
    f = line_shift_per_unit(variable)
    if c.size < 2 or not (math.isfinite(g) and g > 0 and math.isfinite(f)):
        return None
    paso = float(abs(c[1] - c[0]))
    mov = paso * f
    title = tr("diag.mesh_title")
    thr = tr("diag.mesh_thr")
    val = tr("diag.mesh_value", step=_fmt(paso, 3), shift=_fmt(mov, 2), gamma=_fmt(g, 3))
    if mov > g:
        return Check("mesh", "warn", title, val, thr, tr("diag.mesh_meaning"),
                     tr("diag.mesh_action"))
    return Check("mesh", "ok", title, val, thr, tr("diag.mesh_ok_meaning"))


def check_regularization(result) -> Check | None:
    """Histograma (Tikhonov/TV): ¿actúa de verdad la regularización?

    k_eff es la traza del operador regularizado: con α efectivo nulo vale el
    número de parámetros (bins + fondo + nítidos) y baja al suavizar. Si
    queda cerca del máximo, la P se ajusta bin a bin y sus picos pueden ser
    ruido. El umbral solo marca el caso «prácticamente sin regularizar».
    """
    if getattr(result, "shape", None) != "Histograma":
        return None
    if str(getattr(result, "reg_mode", "tikhonov") or "tikhonov") not in ("tikhonov", "tv"):
        return None
    k = getattr(result, "effective_dof", None)
    centers = np.asarray(getattr(result, "bhf_centers", []), dtype=float)
    try:
        k = float(k)
    except (TypeError, ValueError):
        return None
    if centers.size < 3 or not math.isfinite(k):
        return None
    sharp = getattr(result, "sharp_weights", None)
    n_sharp = int(np.size(sharp)) if sharp is not None else 0
    posibles = centers.size + 2 + n_sharp            # bins + fondo y pendiente + nítidos
    ratio = k / posibles
    alpha = getattr(result, "alpha", None)
    try:
        la = f"{math.log10(float(alpha)):.1f}"
    except (TypeError, ValueError):
        la = "—"
    title = tr("diag.reg_title")
    thr = tr("diag.reg_thr", pct=f"{100 * REG_DOF_MAX:.0f}")
    val = tr("diag.reg_value", k=f"{k:.1f}", n=posibles, la=la)
    if ratio >= REG_DOF_MAX:
        return Check("regularization", "warn", title, val, thr, tr("diag.reg_meaning"),
                     tr("diag.reg_action"))
    return Check("regularization", "ok", title, val, thr, tr("diag.reg_ok_meaning"))


def _shape_components(result) -> tuple[list, list, tuple | None]:
    """(componentes [(A, μ, σ)] 1D o [(A, μx, μy, σx, σy, ρ)] 2D, cotas de σ)."""
    comps = getattr(result, "vbf_components", None)
    if comps:
        b = getattr(result, "vbf_sigma_bounds", None)
        return [tuple(map(float, c)) for c in comps], [], b
    comps2 = getattr(result, "vbf2d_components", None)
    if comps2:
        return [], [tuple(map(float, c)) for c in comps2], getattr(result, "vbf2d_sigma_bounds", None)
    return [], [], None


def _sig_at_bound(s: float, b) -> str | None:
    if not b:
        return None
    lo, hi = float(b[0]), float(b[1])
    tol = 1e-3 * max(hi - lo, 1e-12) if math.isfinite(hi - lo) else 1e-9
    if math.isfinite(lo) and s <= lo + tol:
        return "min"
    if math.isfinite(hi) and s >= hi - tol:
        return "max"
    return None


def check_shape_components(result, centers) -> Check | None:
    """Gaussianas del VBF/Gaussiana: σ en su cota, peso despreciable,
    solapadas (redundantes) o con el centro fuera de la malla."""
    c1, c2, bounds = _shape_components(result)
    comps = c1 or c2
    if not comps:
        return None
    title = tr("diag.comp_title")
    thr = tr("diag.comp_thr", pct=f"{100 * COMP_SHARE_MIN:g}")
    total = sum(max(c[0], 0.0) for c in comps) or 1.0
    avisos: list[str] = []
    x = np.asarray(centers, dtype=float)
    lo_x, hi_x = (float(x.min()), float(x.max())) if x.size else (-np.inf, np.inf)
    for k, c in enumerate(comps, start=1):
        share = max(c[0], 0.0) / total
        if len(comps) > 1 and share < COMP_SHARE_MIN:
            avisos.append(tr("diag.comp_small", k=k, pct=f"{100 * share:.1f}"))
        sigmas = (c[2],) if c1 else (c[3], c[4])
        ejes = bounds if (c2 and bounds) else ((bounds,) if bounds else ())
        for s, b in zip(sigmas, ejes):
            side = _sig_at_bound(s, b)
            if side:
                avisos.append(tr("diag.comp_sigma", k=k, s=_fmt(s, 3),
                                 side=tr("diag.min") if side == "min" else tr("diag.max")))
        if c1 and not (lo_x <= c[1] <= hi_x):
            avisos.append(tr("diag.comp_outside", k=k, mu=_fmt(c[1], 4)))
    if c1:
        for i in range(len(c1)):
            for j in range(i + 1, len(c1)):
                if abs(c1[i][1] - c1[j][1]) < 0.5 * min(c1[i][2], c1[j][2]):
                    avisos.append(tr("diag.comp_overlap", a=i + 1, b=j + 1))
    if not avisos:
        return Check("components", "ok", title, tr("diag.comp_ok", n=len(comps)), thr)
    return Check("components", "warn", title, "; ".join(avisos), thr,
                 tr("diag.comp_meaning"), tr("diag.comp_action"))


def check_sharp(area_split) -> Check | None:
    """Componentes nítidas con un área despreciable frente al total."""
    filas = [f for f in (area_split or ()) if int(f[1]) != 0]
    if not filas:
        return None
    title = tr("diag.sharp_title")
    thr = tr("diag.sharp_thr", pct=f"{100 * SHARP_SHARE_MIN:g}")
    pocas = [f for f in filas if float(f[3]) < 100.0 * SHARP_SHARE_MIN]
    if not pocas:
        return Check("sharp", "ok", title, tr("diag.none"), thr)
    txt = "; ".join(f"{f[0]} ({float(f[3]):.2f} %)" for f in pocas)
    return Check("sharp", "warn", title, txt, thr, tr("diag.sharp_meaning"),
                 tr("diag.sharp_action"))


def check_dist_errors(globals_rows: list[dict]) -> Check | None:
    libres = [g for g in globals_rows or () if g.get("free")]
    if not libres:
        return None
    title = tr("diag.err_title")
    thr = tr("diag.err_thr")
    faltan = [g["label"] for g in libres if not g.get("sigma")]
    if faltan:
        return Check("errors", "warn", title, tr("diag.err_missing", n=len(faltan)), thr,
                     tr("diag.err_meaning"), tr("diag.err_action"), tuple(faltan))
    return Check("errors", "ok", title, tr("diag.err_ok"), thr)


def diagnose_distribution(result, summary: dict, *, outer=None,
                          budget_exhausted: bool = False, label=str) -> list[Check]:
    """Todas las comprobaciones de un ajuste de distribución.

    ``summary`` es el resumen del ajuste (bondad, globales con σ y libres,
    pares de correlación, variable); ``outer`` los parámetros del bucle
    externo (globales y de los nítidos) como ``(clave, valor, cota_inf,
    cota_sup)``; ``budget_exhausted`` si ese bucle agotó sus evaluaciones.
    """
    goodness = summary.get("goodness") or {}
    is_2d = bool(summary.get("is_2d"))
    checks: list[Check] = [
        check_convergence_dist(bool(getattr(result, "success", True)), budget_exhausted),
        check_chi2(goodness),
        check_residual(goodness),
        check_edge(edge_ratio(getattr(result, "probability", []))),
    ]
    if not is_2d:
        gamma = next((g["value"] for g in summary.get("globals") or ()
                      if g.get("key") == "dist_gamma"), None)
        mesh = check_mesh(getattr(result, "bhf_centers", []),
                          summary.get("variable") or "bhf", gamma)
        if mesh is not None:
            checks.append(mesh)
    for extra in (check_regularization(result) if not is_2d else None,
                  check_shape_components(result, getattr(result, "bhf_centers", [])),
                  check_sharp(getattr(result, "area_split", None))):
        if extra is not None:
            checks.append(extra)
    if outer:
        checks.append(check_bounds(_at_bounds(outer), label))
    err = check_dist_errors(summary.get("globals") or [])
    if err is not None:
        checks.append(err)
    pairs = list(summary.get("corr_pairs") or [])
    if pairs:
        corr = {"high_pairs": [p for p in pairs if abs(float(p["corr"])) >= CORR_MAX],
                "max_abs_corr": max(abs(float(p["corr"])) for p in pairs)}
        checks.append(check_correlations(corr, str))
    return checks


def diagnose_stats(stats: dict) -> list[Check]:
    """Comprobaciones disponibles solo con estadísticos (ajuste de distribución)."""
    return [check_chi2(stats), check_residual(stats)]
