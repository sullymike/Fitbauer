#!/usr/bin/env python3
"""Utilidades ligeras para leer y doblar espectros Mossbauer WS5/ADT.

Este modulo no depende de Tk ni de matplotlib, para poder reutilizarlo desde
scripts, backend web y pruebas automaticas.

Las funciones de lectura y folding son reexports de ``core.folding`` (fuente
única, igual que hace ``core.data_io``). Aquí solo viven la variante local de
``read_normos_sidecar_params`` (claves planas) y ``folded_velocity_data``.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from core.folding import (  # noqa: F401  (reexports por compatibilidad)
    EDGE_TRIM_DEFAULT,
    _number_re,
    chi2_for_center,
    find_best_integer_or_half_center,
    fold_integer_or_half,
    interp_channel_1based,
    read_normos_folding_point,
    read_normos_plt_velocity,
    read_ws5_counts,
    velocity_axis,
)
from core.folding import read_normos_sidecar_params as _core_sidecar_params


def read_normos_sidecar_params(path: str | Path) -> dict[str, float]:
    """Extrae valores finales de Normos (.RES/.JOB) con claves planas.

    Adaptador sobre ``core.folding.read_normos_sidecar_params`` (que usa claves
    prefijadas ``s1_*`` para el motor de ajuste): devuelve el subconjunto plano
    ``delta``/``quad``/``gamma``/``vmax`` que consumen los CLIs de distribución.
    """
    core = _core_sidecar_params(Path(path))
    params: dict[str, float] = {}
    if "s1_delta" in core:
        params["delta"] = core["s1_delta"]
    if "s1_quad" in core:
        params["quad"] = core["s1_quad"]
    if "s1_gamma1" in core:
        params["gamma"] = core["s1_gamma1"]
    if "vmax" in core:
        params["vmax"] = core["vmax"]
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
    # Mismo recorte de bordes que GUI/core.session (fold_and_normalize): sin él,
    # un canal extremo anómalo (p. ej. canal 1 muerto) entra como línea de
    # absorción falsa en los ajustes de distribución de los CLIs.
    trim = EDGE_TRIM_DEFAULT
    if trim > 0 and folded.size > 2 * trim + 2:
        folded = folded[trim:-trim]
    norm = float(np.percentile(folded, norm_percentile)) or 1.0
    y = folded / norm
    if vmax is None:
        params = read_normos_sidecar_params(path)
        vmax = params.get("vmax")
    if vmax is None:
        vmax = read_normos_plt_velocity(path)
    if vmax is None or not np.isfinite(vmax) or vmax <= 0:
        vmax = 12.0
    v = velocity_axis(counts.size, abs(float(vmax)), y.size)
    return v, y, folded, float(center), float(abs(vmax)), norm
