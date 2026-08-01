#!/usr/bin/env python3
"""Utilidades de análisis del resumen.csv (sin pandas)."""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

VALID_ROOT = Path(__file__).resolve().parent.parent
RESUMEN = VALID_ROOT / "resumen.csv"


def load_rows(version: str | None = None) -> list[dict]:
    with RESUMEN.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        if version and r["version"] != version:
            continue
        for k in ("verdadero", "ajustado", "sigma", "z", "abs_delta",
                  "chi2red", "t_ajuste_s"):
            try:
                r[k] = float(r[k])
            except (ValueError, KeyError):
                r[k] = None
        out.append(r)
    return out


def tol_v0(param: str, truth: float | None) -> float:
    """Criterios de aceptación v0 del plan §4.

    gamma2/gamma3 son RATIOS adimensionales respecto a gamma1 (~0.25 mm/s):
    el criterio de 0.001 mm/s en anchura equivale a ~0.004 en el ratio.
    """
    if "bhf" in param:
        return 0.05
    if "depth" in param:
        return 0.005 * max(abs(truth or 0.0), 1e-9)
    if "int" in param:
        return 0.02 * max(abs(truth or 0.0), 0.05)
    if "gamma2" in param or "gamma3" in param:
        return 0.004
    return 0.001            # posiciones y anchuras, mm/s


def eval_v0(version: str = "v0") -> tuple[dict, list[dict]]:
    rows = load_rows(version)
    per_serie: dict = defaultdict(lambda: {"casos": set(), "filas": 0,
                                           "fallos": 0, "max_abs": 0.0,
                                           "no_conv": set()})
    failures = []
    for r in rows:
        s = per_serie[r["serie"]]
        s["casos"].add(r["caso"])
        s["filas"] += 1
        if r["convergido"] != "si":
            s["no_conv"].add(r["caso"])
            continue
        d = r["abs_delta"]
        if d is None:
            continue
        s["max_abs"] = max(s["max_abs"], d)
        if d > tol_v0(r["parametro"], r["verdadero"]):
            s["fallos"] += 1
            failures.append(r)
    return per_serie, failures


if __name__ == "__main__":
    per_serie, failures = eval_v0()
    print(f"{'serie':6s} {'casos':>5s} {'filas':>5s} {'fallos':>6s} {'max|Δ|':>9s}  no_conv")
    for name in sorted(per_serie):
        s = per_serie[name]
        print(f"{name:6s} {len(s['casos']):5d} {s['filas']:5d} {s['fallos']:6d} "
              f"{s['max_abs']:9.3g}  {len(s['no_conv'])}")
    print(f"\nTotal fallos de criterio v0: {len(failures)}")
    bys = defaultdict(list)
    for f in failures:
        bys[f["serie"]].append(f)
    for s in sorted(bys):
        top = sorted(bys[s], key=lambda r: -(r["abs_delta"] or 0))[:3]
        print(f"\n[{s}] {len(bys[s])} fallos; peores:")
        for r in top:
            print(f"  {r['caso']:28s} {r['parametro']:10s} "
                  f"verd={r['verdadero']:.4g} ajust={r['ajustado']:.4g} "
                  f"|Δ|={r['abs_delta']:.3g}")
