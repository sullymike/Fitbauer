#!/usr/bin/env python3
"""Utilidades ligeras para leer y doblar espectros Mossbauer WS5/ADT.

Este modulo no depende de Tk ni de matplotlib, para poder reutilizarlo desde
scripts, backend web y pruebas automaticas.

Las funciones de lectura y folding son reexports de ``core.folding`` (fuente
única, igual que hace ``core.data_io``). Aquí solo viven la variante local de
``read_normos_sidecar_params`` (claves planas) y ``folded_velocity_data``.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from core.folding import (  # noqa: F401  (reexports por compatibilidad)
    _number_re,
    chi2_for_center,
    find_best_integer_or_half_center,
    fold_integer_or_half,
    interp_channel_1based,
    read_normos_folding_point,
    read_normos_plt_velocity,
    read_ws5_counts,
)


def read_normos_sidecar_params(path: str | Path) -> dict[str, float]:
    """Extrae algunos valores finales de Normos (.RES) y parametros fijos del .JOB.

    NO reexportar desde ``core.folding``: esta variante divergió deliberadamente
    de la de core. Devuelve claves planas ``delta``/``quad``/``gamma`` (las que
    consumen los CLIs de distribución), mientras que la versión canónica de
    ``core.folding`` usa claves prefijadas ``s1_*`` para el motor de ajuste.
    """
    path = Path(path)
    params: dict[str, float] = {}
    res = path.with_suffix(".RES")
    if not res.exists():
        res = path.with_suffix(".res")
    if res.exists():
        text = res.read_text(encoding="utf-8", errors="replace")
        final: dict[str, float] = {}
        for name in ("WID", "ARE", "ISO", "QUA", "BHF"):
            m = re.search(rf"\b{name}\s+({_number_re()})\s+({_number_re()})", text, re.I)
            if m:
                final[name.upper()] = float(m.group(2).replace("D", "E").replace("d", "E"))
        if "ISO" in final:
            params["delta"] = final["ISO"]
        if "QUA" in final:
            params["quad"] = final["QUA"]
        if "WID" in final:
            params["gamma"] = max(0.06, final["WID"])
    job = path.with_suffix(".JOB")
    if not job.exists():
        job = path.with_suffix(".job")
    if job.exists():
        text = job.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\bVMAX\s*=\s*(" + _number_re() + ")", text, re.I)
        if m:
            params["vmax"] = abs(float(m.group(1).replace("D", "E").replace("d", "E")))
        m = re.search(r"\bQUA\(1\)\s*=\s*(" + _number_re() + ")", text, re.I)
        if m and "quad" not in params:
            params["quad"] = float(m.group(1).replace("D", "E").replace("d", "E"))
    return params


def folded_velocity_data(
    path: str | Path,
    *,
    center: float | None = None,
    vmax: float | None = None,
    norm_percentile: float = 90.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float, float]:
    """Lee, dobla y normaliza un WS5.

    Devuelve ``(v, y_norm, folded_counts, center, vmax, norm_factor)``.
    """
    path = Path(path)
    counts = read_ws5_counts(path)
    if center is None:
        center = read_normos_folding_point(path)
    if center is None:
        center = find_best_integer_or_half_center(counts)
    folded, _pairs = fold_integer_or_half(counts, center)
    norm = float(np.percentile(folded, norm_percentile)) or 1.0
    y = folded / norm
    if vmax is None:
        params = read_normos_sidecar_params(path)
        vmax = params.get("vmax")
    if vmax is None:
        vmax = read_normos_plt_velocity(path)
    if vmax is None or not np.isfinite(vmax) or vmax <= 0:
        vmax = 12.0
    v = np.linspace(-abs(float(vmax)), abs(float(vmax)), y.size)
    return v, y, folded, float(center), float(abs(vmax)), norm
