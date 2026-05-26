"""Lectura y plegado de ficheros de espectro Mössbauer (sin GUI)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np

CONFIG_DIR = Path.home() / ".config" / "mossbauer_fe33_gui"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"


def load_credentials() -> dict:
    if CREDENTIALS_PATH.exists():
        try:
            return json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_credentials(data: dict) -> None:
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        os.chmod(CREDENTIALS_PATH, 0o600)
    except Exception:
        pass


def _number_re() -> str:
    return r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[EeDd][-+]?\d+)?"


def read_ws5_counts(path: Path) -> np.ndarray:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<data[^>]*>(.*?)</data>", text, re.S | re.I)
    source = m.group(1) if m else text
    counts = np.array([float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", source)])
    if counts.size < 2:
        raise ValueError(f"No se encontraron cuentas suficientes en {path}")
    return counts


def read_normos_folding_point(path: Path) -> float | None:
    for suffix in (".RES", ".res"):
        res = path.with_suffix(suffix)
        if res.exists():
            break
    else:
        return None
    text = res.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(
        r"Final folding point\s*=\s*(" + _number_re() + ")", text, re.I
    )
    if not matches:
        return None
    return 0.5 * float(matches[-1].replace("D", "E").replace("d", "E"))


def read_normos_plt_velocity(path: Path) -> float | None:
    for suffix in (".PLT", ".plt"):
        plt = path.with_suffix(suffix)
        if plt.exists():
            break
    else:
        return None
    text = plt.read_text(encoding="utf-8", errors="replace")
    nums = [
        float(x.replace("D", "E").replace("d", "E"))
        for x in re.findall(_number_re(), text)
    ]
    if len(nums) % 256 == 1:
        nums = nums[1:]
    if len(nums) >= 256:
        return float(max(abs(min(nums[:256])), abs(max(nums[:256]))))
    return None


def read_normos_sidecar_params(path: Path) -> dict[str, float]:
    params: dict[str, float] = {}
    for suffix in (".RES", ".res"):
        res = path.with_suffix(suffix)
        if res.exists():
            text = res.read_text(encoding="utf-8", errors="replace")
            final: dict[str, float] = {}
            for name in ("WID", "ARE", "ISO", "QUA", "BHF"):
                m = re.search(
                    rf"\b{name}\s+({_number_re()})\s+({_number_re()})", text, re.I
                )
                if m:
                    final[name.upper()] = float(
                        m.group(2).replace("D", "E").replace("d", "E")
                    )
            if "ISO" in final:
                params["s1_delta"] = final["ISO"]
            if "BHF" in final:
                params["s1_bhf"] = final["BHF"]
            if "QUA" in final:
                params["s1_quad"] = final["QUA"]
            if "WID" in final:
                params["s1_gamma1"] = max(0.03, final["WID"] / 2.0)
                params["s1_gamma2"] = 1.0
                params["s1_gamma3"] = 1.0
            if "ARE" in final and "s1_gamma1" in params:
                weight_sum = 2.0 * (1.0 + 2.0 / 3.0 + 1.0 / 3.0)
                params["s1_depth"] = max(
                    0.0,
                    min(
                        0.30,
                        final["ARE"] / (np.pi * params["s1_gamma1"] * weight_sum),
                    ),
                )
            break
    for suffix in (".JOB", ".job"):
        job = path.with_suffix(suffix)
        if job.exists():
            text = job.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"\bVMAX\s*=\s*(" + _number_re() + ")", text, re.I)
            if m:
                params["vmax"] = abs(
                    float(m.group(1).replace("D", "E").replace("d", "E"))
                )
            m = re.search(r"\bQUA\(1\)\s*=\s*(" + _number_re() + ")", text, re.I)
            if m and "s1_quad" not in params:
                params["s1_quad"] = float(
                    m.group(1).replace("D", "E").replace("d", "E")
                )
            break
    return params


def interp_channel_1based(counts: np.ndarray, channel: float) -> float:
    n = counts.size
    if channel < 1.0:
        return float(counts[0] + (channel - 1.0) * (counts[1] - counts[0]))
    if channel >= float(n):
        return float(
            counts[-1] + (channel - float(n)) * (counts[-1] - counts[-2])
        )
    lo = int(np.floor(channel))
    frac = channel - lo
    if frac < 1e-12:
        return float(counts[lo - 1])
    return float((1.0 - frac) * counts[lo - 1] + frac * counts[lo])


def fold_integer_or_half(
    counts: np.ndarray, center: float
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    n = counts.size
    n_out = n // 2
    rows: list[tuple[int, int, float]] = []
    for j in range(n_out):
        distance = j + 0.5
        left_ch = center - distance
        right_ch = center + distance
        folded = 0.5 * (
            interp_channel_1based(counts, left_ch)
            + interp_channel_1based(counts, right_ch)
        )
        rows.append((int(round(left_ch)), int(round(right_ch)), folded))
    return (
        np.array([r[2] for r in rows], dtype=float),
        [(r[0], r[1]) for r in rows],
    )


def chi2_for_center(
    counts: np.ndarray, center: float
) -> tuple[float, int]:
    folded, pairs = fold_integer_or_half(counts, center)
    chi2 = 0.0
    for left, right in pairs:
        if not (1 <= left <= counts.size and 1 <= right <= counts.size):
            continue
        d = counts[left - 1] - counts[right - 1]
        chi2 += d * d
    return chi2, len(pairs)


def find_best_integer_or_half_center(
    counts: np.ndarray,
    cmin: float = 250.5,
    cmax: float = 262.5,
) -> float:
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
