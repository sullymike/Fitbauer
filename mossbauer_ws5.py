#!/usr/bin/env python3
"""Utilidades ligeras para leer y doblar espectros Mossbauer WS5/ADT.

Este modulo no depende de Tk ni de matplotlib, para poder reutilizarlo desde
scripts, backend web y pruebas automaticas.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np


def _number_re() -> str:
    return r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[EeDd][-+]?\d+)?"


def read_ws5_counts(path: str | Path) -> np.ndarray:
    """Lee cuentas de ficheros WS5 XML o ADT antiguos sin cabecera."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<data[^>]*>(.*?)</data>", text, re.S | re.I)
    source = m.group(1) if m else text
    counts = np.array([float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", source)], dtype=float)
    if counts.size < 2:
        raise ValueError(f"No se encontraron cuentas suficientes en {path}")
    return counts


def read_normos_folding_point(path: str | Path) -> float | None:
    """Lee el 'Final folding point' de Normos si existe y lo pasa a centro interno.

    Algunas versiones de Normos reportan el PFP en convención de espectro
    completo (~511 para 512 canales) y otras en convención de semiespecro
    (~256). Se distinguen por el valor: >= 400 → espectro completo (÷2);
    < 400 → semiespecro (usar tal cual).
    """
    path = Path(path)
    res = path.with_suffix(".RES")
    if not res.exists():
        res = path.with_suffix(".res")
    if not res.exists():
        return None
    text = res.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"Final folding point\s*=\s*(" + _number_re() + ")", text, re.I)
    if not matches:
        return None
    v = float(matches[-1].replace("D", "E").replace("d", "E"))
    return 0.5 * v if v >= 400.0 else v


def read_normos_plt_velocity(path: str | Path) -> float | None:
    """Lee Vmax del .PLT asociado si existe."""
    path = Path(path)
    plt = path.with_suffix(".PLT")
    if not plt.exists():
        plt = path.with_suffix(".plt")
    if not plt.exists():
        return None
    text = plt.read_text(encoding="utf-8", errors="replace")
    nums = [float(x.replace("D", "E").replace("d", "E")) for x in re.findall(_number_re(), text)]
    if len(nums) % 256 == 1:
        nums = nums[1:]
    if len(nums) >= 256:
        return float(max(abs(min(nums[:256])), abs(max(nums[:256]))))
    return None


def read_normos_sidecar_params(path: str | Path) -> dict[str, float]:
    """Extrae algunos valores finales de Normos (.RES) y parametros fijos del .JOB."""
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
            params["gamma"] = max(0.03, final["WID"] / 2.0)
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


def interp_channel_1based(counts: np.ndarray, channel: float) -> float:
    """Interpolacion lineal C(channel) con canales 1..N; extrapola en bordes."""
    counts = np.asarray(counts, dtype=float)
    n = counts.size
    if channel < 1.0:
        return float(counts[0] + (channel - 1.0) * (counts[1] - counts[0]))
    if channel >= float(n):
        return float(counts[-1] + (channel - float(n)) * (counts[-1] - counts[-2]))
    lo = int(np.floor(channel))
    frac = channel - lo
    if frac < 1e-12:
        return float(counts[lo - 1])
    return float((1.0 - frac) * counts[lo - 1] + frac * counts[lo])


def fold_integer_or_half(counts: np.ndarray, center: float) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Dobla a N/2 puntos al estilo Normos usando un centro interno."""
    counts = np.asarray(counts, dtype=float)
    n = counts.size
    n_out = n // 2
    rows: list[tuple[int, int, float]] = []
    for j in range(n_out):
        distance = j + 0.5
        left_ch = center - distance
        right_ch = center + distance
        folded = 0.5 * (interp_channel_1based(counts, left_ch) + interp_channel_1based(counts, right_ch))
        rows.append((int(round(left_ch)), int(round(right_ch)), folded))
    return np.array([r[2] for r in rows], dtype=float), [(r[0], r[1]) for r in rows]


def chi2_for_center(counts: np.ndarray, center: float) -> tuple[float, int]:
    folded, pairs = fold_integer_or_half(counts, center)
    del folded
    chi2 = 0.0
    n_used = 0
    for left, right in pairs:
        if not (1 <= left <= counts.size and 1 <= right <= counts.size):
            continue
        d = counts[left - 1] - counts[right - 1]
        chi2 += d * d
        n_used += 1
    return chi2, n_used


def find_best_integer_or_half_center(counts: np.ndarray, cmin: float = 250.5, cmax: float = 262.5) -> float:
    """Busca el folding point con malla de 0.5 canales e interpolacion parabolica."""
    counts = np.asarray(counts, dtype=float)
    candidates = np.arange(cmin, cmax + 1e-9, 0.5)
    values: list[tuple[float, float]] = []
    for center in candidates:
        chi2, n_pairs = chi2_for_center(counts, float(center))
        if n_pairs:
            values.append((float(center), chi2 / n_pairs))
    if not values:
        return 0.5 * counts.size
    best_i = min(range(len(values)), key=lambda i: values[i][1])
    if 0 < best_i < len(values) - 1:
        xm, ym = values[best_i - 1]
        x0, y0 = values[best_i]
        xp, yp = values[best_i + 1]
        den = ym - 2.0 * y0 + yp
        if den > 0:
            step = x0 - xm
            xv = x0 + 0.5 * step * (ym - yp) / den
            if xm <= xv <= xp:
                return float(xv)
    return values[best_i][0]


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
