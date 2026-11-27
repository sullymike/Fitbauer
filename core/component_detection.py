"""Detección de componentes desde los mínimos del espectro (sin GUI).

Dos niveles:

1. **Reglas** (``detect_minima`` + ``components_from_peaks``): busca los
   mínimos y les asigna componentes con reglas fijas (mejor sextete, dobletes
   por separación, singletes con lo que sobra). Rápido, pero no comprueba si
   la propuesta explica el espectro.
2. **Propuestas evaluadas** (``evaluate_detection``): con los mismos mínimos
   genera varias interpretaciones (la de las reglas y otras: dobletes que
   comparten una línea, quitar una componente débil…), las preselecciona con
   un ajuste lineal de profundidades (NNLS) y ajusta en local las mejores; gana
   la de menor BIC. Después mira el residuo y añade una componente donde quede
   estructura, solo si baja el BIC al menos ``RESIDUAL_DBIC``. Devuelve todos
   los números para que la interfaz los enseñe (nada de caja negra).

La GUI (``gui/minima_analysis.py``) y cualquier CLI son clientes de este módulo.
"""
from __future__ import annotations

import numpy as np

from core.constants import BHF_DEFAULT_T, LINE_POS_33T
from core.param_overrides import (effective_fit_init_specs as _eff_fi,
                                  effective_peak_detection_specs as _eff_pd)
from core.params import COMPONENT_FIT_BOUNDS, MAX_COMPONENTS, SEXTET_WEIGHTS

_FI = _eff_fi()
_PD = _eff_pd()


def reload_param_specs() -> None:
    """Relee los límites de inicialización y detección (diálogo de límites)."""
    global _FI, _PD
    _FI = _eff_fi()
    _PD = _eff_pd()


# Calibración del estimador de anchura CWT: para una Lorentziana de FWHM Γ, la
# escala Ricker de máxima respuesta cumple 2·a·dv ≈ 2.85·Γ (ratio empírico
# estable 2.6–3.0 para Γ = 0.2–1.0 mm/s con las mallas típicas). Se divide por
# este factor para que la rama CWT devuelva FWHM reales, consistentes con la
# rama directa a media altura.
_CWT_LORENTZ_WIDTH_RATIO = 2.85


def _smooth_1d(values: np.ndarray, window: int) -> np.ndarray:
    """Suavizado de media móvil equivalente al usado por la GUI Tk."""
    window = int(max(3, window))
    if window % 2 == 0:
        window += 1
    if values.size < window:
        return values.astype(float).copy()
    kernel = np.ones(window, dtype=float) / float(window)
    pad = window // 2
    padded = np.pad(values.astype(float), pad, mode="edge")
    return np.convolve(padded, kernel, mode="valid")

def _cwt_ricker(signal: np.ndarray, scales: np.ndarray) -> np.ndarray:
    """CWT con ondícula Ricker (Mexican hat) implementada con np.convolve.

    Réplica de scipy.signal.cwt + ricker sin depender de esas funciones
    (eliminadas de scipy.signal en 1.12). Para cada escala a (en canales):
      ψ(x,a) = A·(1 − (x/a)²)·exp(−x²/(2a²))   A = 2/(√(3a)·π^1/4)
    La respuesta CWT en (escala, posición) es la correlación cruzada del
    espectro de absorción con ψ: valores positivos grandes indican un pico
    cuyo FWHM coincide con la escala.
    """
    n = signal.size
    cwt_mat = np.zeros((scales.size, n))
    for j, a in enumerate(scales):
        a = float(a)
        # Longitud del kernel: 10·a puntos a cada lado (análogo a scipy).
        # Clampeado a (n-1)//2 para que psi nunca supere al signal en longitud
        # (np.convolve mode="same" devuelve max(M,N), no M).
        half = min(max(int(5 * a), 3), (n - 1) // 2)
        x = np.arange(-half, half + 1, dtype=float)
        A = 2.0 / (np.sqrt(3.0 * a) * np.pi ** 0.25)
        psi = A * (1.0 - (x / a) ** 2) * np.exp(-0.5 * (x / a) ** 2)
        # Ricker es simétrica → correlación == convolución
        cwt_mat[j] = np.convolve(signal, psi, mode="same")
    return cwt_mat

def _compute_absorption(v: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Calcula la absorción como baseline_line - y (≥ 0).

    Ajusta una baseline lineal sobre el 70 % superior de los datos (o usa el
    percentil 90 como fallback si hay menos de 4 puntos altos).

    Devuelve ``(absorption, baseline0, slope)``.
    """
    high = y >= np.percentile(y, 70)
    if int(np.sum(high)) >= 4:
        slope, baseline0 = np.polyfit(v[high], y[high], 1)
    else:
        baseline0 = float(np.percentile(y, 90))
        slope = 0.0
    baseline_line = baseline0 + slope * v
    absorption = np.maximum(baseline_line - y, 0.0)
    return absorption, float(baseline0), float(slope)

def _noise_and_thresholds(coarse_smooth: np.ndarray, max_abs: float, dv: float
) -> tuple[float, float, float]:
    """Calcula umbrales de altura, prominencia y separación mínima.

    Estima el ruido con la MAD sobre las diferencias del suavizado grueso y
    aplica los factores configurables de ``_PD``.

    Devuelve ``(height_thr, prom_thr, min_distance)``.
    """
    diff_noise = np.diff(coarse_smooth)
    noise = (1.4826 * float(np.median(np.abs(diff_noise - np.median(diff_noise))))
             if diff_noise.size else 0.0)
    height_thr = max(_PD["height_thr_factor"].default * max_abs, 4.0 * noise, 5e-4)
    prom_thr = max(_PD["prom_thr_factor"].default * max_abs, 2.5 * noise, 3e-4)
    min_distance = max(_PD["min_separation"].default, 2.0 * dv)
    return height_thr, prom_thr, min_distance

def _cwt_and_direct_candidates(absorption: np.ndarray,
    dv: float,
    height_thr: float,
    prom_thr: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Detecta candidatos a pico por CWT y por suavizado fino directo.

    CWT multi-escala con ondícula Ricker: detecta picos solapados y estima
    anchuras en el rango físico Mössbauer (0.12..2.0 mm/s). Estrategia
    híbrida: la cresta CWT (max entre escalas) es robusta para líneas anchas
    y sextetes, pero puede fundir dobletes cercanos en un único "pico". Por
    eso se buscan candidatos también en la absorción directamente suavizada
    y se fusionan ambas listas antes del filtrado final.

    Devuelve ``(cwt_mat, scales, fine_smooth, abs_fine, cwt_idxs, dir_idxs)``.
    """
    from scipy.signal import find_peaks as _find_peaks

    min_sc = max(2, int(0.12 / dv))
    max_sc = max(min_sc + 3, int(2.0 / dv))
    scales = np.arange(min_sc, max_sc + 1, dtype=float)
    cwt_mat = _cwt_ricker(absorption, scales)         # (n_escalas, n_pts)
    ridge = np.maximum(np.max(cwt_mat, axis=0), 0.0)
    ridge_max = float(np.nanmax(ridge)) if ridge.size else 0.0
    max_abs = float(np.nanmax(absorption)) if absorption.size else 0.0
    fine_smooth = ridge * (max_abs / ridge_max) if ridge_max > 0.0 else ridge

    # Canal 1 — picos en la cresta CWT (buen SNR para líneas anchas/sextetes)
    cwt_idxs, _ = _find_peaks(fine_smooth, height=height_thr, prominence=prom_thr)
    # Canal 2 — picos en la absorción con suavizado fino (rescata dobletes estrechos
    # que el CWT fusionaría al tomar el máximo entre escalas grandes)
    fine_win = max(3, int(0.15 / dv)) | 1   # ~0.15 mm/s, siempre impar
    abs_fine = _smooth_1d(absorption, fine_win)
    abs_fine_norm = abs_fine * (max_abs / float(np.nanmax(abs_fine))) if np.nanmax(abs_fine) > 0 else abs_fine
    dir_idxs, _ = _find_peaks(abs_fine_norm, height=height_thr, prominence=prom_thr)
    return cwt_mat, scales, fine_smooth, abs_fine, cwt_idxs, dir_idxs

def _fuse_peak_indices(cwt_idxs: np.ndarray, dir_idxs: np.ndarray) -> list[int]:
    """Fusiona índices de picos CWT y directos eliminando duplicados y artefactos.

    Fusión de listas:
    1) Los picos directos son la referencia principal (evitan falsos "picos de valle"
       en dobletes estrechos donde el CWT a escalas grandes responde en el mínimo).
    2) Se añaden picos CWT sólo si NO están entre dos picos directos consecutivos
       (ese caso es síntoma del artefacto de valle CWT) y no son duplicados.

    Devuelve lista ordenada de índices fusionados.
    """
    dir_positions = sorted(int(i) for i in dir_idxs)

    def _between_direct(idx: int) -> bool:
        for k in range(len(dir_positions) - 1):
            lo, hi = dir_positions[k], dir_positions[k + 1]
            if lo < idx < hi:
                return True
        return False

    all_idxs: set[int] = set(dir_positions)
    for i in cwt_idxs:
        ci = int(i)
        if ci not in all_idxs and not any(abs(ci - q) <= 1 for q in all_idxs):
            if not _between_direct(ci):
                all_idxs.add(ci)
    return sorted(all_idxs)

def _build_peaks_list(all_idxs: list[int],
    v: np.ndarray,
    absorption: np.ndarray,
    abs_fine: np.ndarray,
    fine_smooth: np.ndarray,
    cwt_mat: np.ndarray,
    scales: np.ndarray,
    dv: float,
) -> list[dict[str, float]]:
    """Construye la lista de dicts de picos con pos, depth, smooth_depth y width.

    Para cada índice en ``all_idxs`` estima la anchura FWHM: si hay respuesta
    CWT positiva, usa la escala de mayor respuesta; si no, usa FWHM directo
    sobre ``abs_fine``.
    """
    max_abs = float(np.nanmax(absorption)) if absorption.size else 0.0
    abs_fine_norm = abs_fine * (max_abs / float(np.nanmax(abs_fine))) if np.nanmax(abs_fine) > 0 else abs_fine
    peaks: list[dict[str, float]] = []
    for i in all_idxs:
        # Anchura desde la escala de mayor respuesta CWT positiva en ese índice
        best_sc = int(np.argmax(np.maximum(cwt_mat[:, i], 0.0)))
        cwt_resp = float(np.max(np.maximum(cwt_mat[:, i], 0.0)))
        if cwt_resp < 1e-10:
            # Sin respuesta CWT positiva: estimar anchura por FWHM directo
            half = float(abs_fine[i]) * 0.5
            li, ri = i, i
            while li > 0 and abs_fine[li] > half:
                li -= 1
            while ri < abs_fine.size - 1 and abs_fine[ri] > half:
                ri += 1
            width = max(abs(float(v[ri] - v[li])), 2.0 * dv)
        else:
            # Calibración empírica del estimador CWT: para una Lorentziana
            # de FWHM Γ, la escala Ricker de máxima respuesta cumple
            # 2·a·dv ≈ 2.85·Γ (ratio estable 2.6–3.0 en Γ=0.2–1.0 mm/s).
            # Sin este factor, Γ inicial salía ~3× demasiado grande (0.75
            # en α-Fe, 2.0 recortado en magnetita) y además era
            # inconsistente con la rama directa a media altura (que sí
            # mide FWHM).
            width = max(float(scales[best_sc]) * dv * 2.0 / _CWT_LORENTZ_WIDTH_RATIO,
                        2.0 * dv)
        smooth_d = float(fine_smooth[i]) if fine_smooth[i] > 0 else float(abs_fine_norm[i])
        peaks.append({"i": float(i), "pos": float(v[i]),
                      "depth": float(absorption[i]),
                      "smooth_depth": smooth_d,
                      "width": width})
    return peaks

def detect_minima(v: np.ndarray, y: np.ndarray) -> tuple[list[dict[str, float]], float, float]:
    """Detecta mínimos de transmisión como máximos de absorción.

    Baseline lineal en la zona alta, umbrales por ruido/prominencia, candidatos
    por CWT (Ricker) y por suavizado fino, anchuras FWHM aproximadas y
    eliminación de duplicados cercanos. ``y`` puede ser otra curva sobre el
    mismo eje (p. ej. el residuo de un modelo más su fondo).

    Devuelve ``(mínimos, baseline0, slope)``; cada mínimo es un dict con
    ``i`` (canal), ``pos``, ``depth``, ``smooth_depth`` y ``width`` (FWHM).
    """
    if v is None or y is None:
        return [], 1.0, 0.0
    v = np.asarray(v, dtype=float)
    y = np.asarray(y, dtype=float)
    if y.size < 7:
        return [], 1.0, 0.0

    absorption, baseline0, slope = _compute_absorption(v, y)

    coarse_smooth = _smooth_1d(absorption, max(5, absorption.size // 80))
    max_abs = float(np.nanmax(coarse_smooth)) if coarse_smooth.size else 0.0
    if max_abs <= 0:
        return [], baseline0, slope

    dv = abs(float(v[1] - v[0])) if v.size > 1 else 0.05
    height_thr, prom_thr, min_distance = _noise_and_thresholds(coarse_smooth, max_abs, dv)

    try:
        cwt_mat, scales, fine_smooth, abs_fine, cwt_idxs, dir_idxs = \
            _cwt_and_direct_candidates(absorption, dv, height_thr, prom_thr)
    except ImportError:
        return [], baseline0, slope

    all_idxs = _fuse_peak_indices(cwt_idxs, dir_idxs)
    peaks = _build_peaks_list(all_idxs, v, absorption, abs_fine, fine_smooth, cwt_mat, scales, dv)

    selected: list[dict[str, float]] = []
    for peak in sorted(peaks, key=lambda p: p["smooth_depth"], reverse=True):
        if all(abs(peak["pos"] - q["pos"]) >= min_distance for q in selected):
            selected.append(peak)
    return sorted(selected[:15], key=lambda p: p["pos"]), baseline0, slope

def _best_sextet_from_peaks(peaks: list[dict[str, float]]
) -> tuple[list[dict[str, float]], float, float, float, float] | None:
    if len(peaks) < 5:
        split = _try_split_peaks_for_sextet(peaks)
        if split is not None:
            return split
        return None
    from itertools import combinations
    candidates = sorted(peaks, key=lambda p: p["smooth_depth"], reverse=True)[:10]
    best = None
    iterator = combinations(candidates, 6) if len(candidates) >= 6 else [tuple(candidates[:5])]
    for subset in iterator:
        sub = sorted(subset, key=lambda p: p["pos"])
        pos = np.array([p["pos"] for p in sub], dtype=float)
        if len(sub) == 6:
            ref = LINE_POS_33T
        else:
            local_best = None
            for missing in range(6):
                ref5 = np.delete(LINE_POS_33T, missing)
                A5 = np.column_stack([np.ones(ref5.size), ref5])
                delta5, scale5 = np.linalg.lstsq(A5, pos, rcond=None)[0]
                pred5 = delta5 + scale5 * ref5
                rms5 = float(np.sqrt(np.mean((pos - pred5) ** 2)))
                if local_best is None or rms5 < local_best[0]:
                    local_best = (rms5, delta5, scale5, missing)
            if local_best is None:
                continue
            rms, delta, scale, missing_idx = local_best
            bhf = scale * BHF_DEFAULT_T
            if _FI["sextet_bhf_min"].default <= bhf <= _FI["sextet_bhf_max"].default and (best is None or rms < best[0]):
                weights5 = np.delete(np.array(SEXTET_WEIGHTS, dtype=float), missing_idx)
                depths = np.array([p["depth"] for p in sub], dtype=float)
                depth_est = float(np.median(depths / weights5))
                best = (rms, list(sub), float(delta), float(bhf),
                        float(np.median([p["width"] for p in sub])), depth_est)
            continue
        A = np.column_stack([np.ones(ref.size), ref])
        delta, scale = np.linalg.lstsq(A, pos, rcond=None)[0]
        pred = delta + scale * ref
        rms = float(np.sqrt(np.mean((pos - pred) ** 2)))
        bhf = scale * BHF_DEFAULT_T
        if not (_FI["sextet_bhf_min"].default <= bhf <= _FI["sextet_bhf_max"].default):
            continue
        if best is None or rms < best[0]:
            weights = np.array(SEXTET_WEIGHTS, dtype=float)
            depths = np.array([p["depth"] for p in sub], dtype=float)
            depth_est = float(np.median(depths / weights))
            best = (rms, list(sub), float(delta), float(bhf),
                    float(np.median([p["width"] for p in sub])), depth_est)
    if best is None:
        return _try_split_peaks_for_sextet(peaks)
    score, sub, delta, bhf, width, depth = best
    if score > max(_PD["score_tol"].default, _PD["score_tol_factor"].default * max(1.0, abs(bhf / BHF_DEFAULT_T))):
        return _try_split_peaks_for_sextet(peaks)
    return sub, delta, bhf, width, depth

def _sextet_sharing_lines(remaining: list[dict[str, float]], peaks: list[dict[str, float]]
) -> tuple[list[dict[str, float]], float, float, float, float] | None:
    """Sextete con al menos dos mínimos de ``remaining`` y el resto de ``peaks``.

    En un espectro con dos sextetes de campo parecido (magnetita) las
    líneas interiores se solapan: el segundo sextete solo deja dos o tres
    mínimos propios y comparte los demás con el primero. Se prueban los
    subconjuntos de 6 (o 5, con una línea perdida) de los mínimos más
    profundos que incluyan al menos dos de ``remaining``.
    """
    from itertools import combinations
    rem_ids = {int(p["i"]) for p in remaining}
    if len(rem_ids) < 2:
        return None
    cands = sorted(peaks, key=lambda p: p["smooth_depth"], reverse=True)[:10]
    for p in remaining:                     # los sobrantes, siempre
        if all(int(p["i"]) != int(c["i"]) for c in cands):
            cands.append(p)
    weights_all = np.array(SEXTET_WEIGHTS, dtype=float)
    tol = _PD["score_tol"].default
    best = None
    for n in (6, 5):
        for subset in combinations(cands, n):
            if sum(int(p["i"]) in rem_ids for p in subset) < 2:
                continue
            sub = sorted(subset, key=lambda p: p["pos"])
            pos = np.array([p["pos"] for p in sub], dtype=float)
            missing_opts = [None] if n == 6 else range(6)
            for missing in missing_opts:
                ref = LINE_POS_33T if missing is None else np.delete(LINE_POS_33T, missing)
                A = np.column_stack([np.ones(ref.size), ref])
                delta, scale = np.linalg.lstsq(A, pos, rcond=None)[0]
                rms = float(np.sqrt(np.mean((pos - (delta + scale * ref)) ** 2)))
                bhf = scale * BHF_DEFAULT_T
                if not (_FI["sextet_bhf_min"].default <= bhf <= _FI["sextet_bhf_max"].default):
                    continue
                if rms > tol * max(1.0, abs(bhf / BHF_DEFAULT_T)):
                    continue
                if best is None or rms < best[0]:
                    w = weights_all if missing is None else np.delete(weights_all, missing)
                    own = [p for p in sub if int(p["i"]) in rem_ids]
                    own_w = np.array([w[sub.index(p)] for p in own], dtype=float)
                    depth = float(np.median(np.array([p["depth"] for p in own]) / own_w))
                    best = (rms, sub, float(delta), float(bhf),
                            float(np.median([p["width"] for p in own])), depth)
        if best is not None:
            break
    if best is None:
        return None
    _rms, sub, delta, bhf, width, depth = best
    return sub, delta, bhf, width, depth

def _try_split_peaks_for_sextet(peaks: list[dict[str, float]]) -> tuple | None:
    if len(peaks) < 4 or len(peaks) >= 6:
        return None
    from itertools import combinations as _comb
    median_width = float(np.median([p["width"] for p in peaks]))
    median_depth = float(np.median([p["depth"] for p in peaks]))

    def is_normal(pk: dict) -> bool:
        return pk["width"] <= median_width * 1.25 and pk["depth"] <= median_depth * 1.40

    normal_peaks = [p for p in peaks if is_normal(p)]
    if len(normal_peaks) < 2:
        normal_peaks = sorted(peaks, key=lambda p: p["width"])[:2]
    narrow_tol = max(median_width * _PD["narrow_tol_factor"].default, _PD["narrow_tol_min"].default)
    next_vid = max(p["i"] for p in peaks) + 1.0
    best_result = None
    best_score = -1
    seen: set[tuple] = set()
    for pk_a, pk_b in _comb(sorted(normal_peaks, key=lambda p: p["pos"]), 2):
        span_obs = abs(pk_b["pos"] - pk_a["pos"])
        if span_obs < 0.5:
            continue
        for la in range(6):
            for lb in range(la + 1, 6):
                span_ref = LINE_POS_33T[lb] - LINE_POS_33T[la]
                if abs(span_ref) < 0.3:
                    continue
                scale = span_obs / span_ref
                bhf_est = scale * BHF_DEFAULT_T
                if not (_FI["sextet_bhf_min"].default <= bhf_est <= _FI["sextet_bhf_max"].default):
                    continue
                delta = pk_a["pos"] - scale * LINE_POS_33T[la]
                pred_all = delta + scale * LINE_POS_33T
                if max(abs(pk_a["pos"] - pred_all[la]),
                       abs(pk_b["pos"] - pred_all[lb])) > _PD["match_tol"].default:
                    continue
                key = (round(bhf_est, 1), round(delta, 2))
                if key in seen:
                    continue
                seen.add(key)
                augmented = list(peaks)
                vid = next_vid
                virtual_added = 0
                for pred_pos in pred_all:
                    if any(abs(p["pos"] - pred_pos) < narrow_tol and is_normal(p)
                           for p in peaks):
                        continue
                    for pk in sorted(peaks, key=lambda p: abs(p["pos"] - pred_pos)):
                        if abs(pk["pos"] - pred_pos) > pk["width"] * 0.7:
                            break
                        if not is_normal(pk):
                            augmented.append({
                                "i": vid, "pos": float(pred_pos),
                                "depth": pk["depth"] * 0.45,
                                "smooth_depth": pk["smooth_depth"] * 0.45,
                                "width": pk["width"] * 0.65,
                            })
                            vid += 1.0
                            virtual_added += 1
                            break
                if virtual_added == 0:
                    continue
                result = _best_sextet_from_peaks(augmented)
                if result is None:
                    continue
                _, delta_r, bhf_r, _, _ = result
                scale_r = bhf_r / BHF_DEFAULT_T
                pred_r = delta_r + scale_r * LINE_POS_33T
                score = sum(
                    1 for pk in peaks if not is_normal(pk)
                    and sum(1 for pp in pred_r if abs(pk["pos"] - pp) < pk["width"] * 0.65) >= 2
                )
                if score > best_score:
                    best_score = score
                    best_result = result
    return best_result

def _try_2peak_sextet_estimate(peaks: list[dict[str, float]]
) -> tuple[list[dict[str, float]], float, float, float, float] | None:
    if len(peaks) != 2:
        return None
    p = sorted(peaks, key=lambda x: x["pos"])
    obs_spacing = p[1]["pos"] - p[0]["pos"]
    if obs_spacing < 0.5:
        return None
    spacing_ref = float(LINE_POS_33T[1] - LINE_POS_33T[0])
    scale = obs_spacing / spacing_ref
    bhf = scale * BHF_DEFAULT_T
    if not (_FI["sextet_2pk_bhf_min"].default <= bhf <= _FI["sextet_bhf_max"].default):
        return None
    best: tuple | None = None
    if p[0]["pos"] < 0 and p[1]["pos"] < 0:
        delta_01 = p[0]["pos"] - scale * float(LINE_POS_33T[0])
        if abs(delta_01) <= 1.5:
            best = (delta_01, bhf, (3.0, 2.0))
    if p[0]["pos"] > 0 and p[1]["pos"] > 0:
        delta_45 = p[0]["pos"] - scale * float(LINE_POS_33T[4])
        if abs(delta_45) <= 1.5:
            best = (delta_45, bhf, (2.0, 3.0))
    if best is None:
        return None
    delta_est, bhf_est, (w0, w1) = best
    width = float(np.mean([p[0]["width"], p[1]["width"]]))
    depth = float(np.median([p[0]["depth"] / w0, p[1]["depth"] / w1]))
    return list(p), delta_est, bhf_est, width, depth

def _depth_profile_hint(peaks: list[dict[str, float]]) -> tuple[str, list[dict[str, float]]] | None:
    if not peaks:
        return None
    by_d = sorted(peaks, key=lambda p: p["smooth_depth"], reverse=True)
    d0 = by_d[0]["smooth_depth"]
    d1 = by_d[1]["smooth_depth"] if len(by_d) > 1 else 0.0
    d2 = by_d[2]["smooth_depth"] if len(by_d) > 2 else 0.0
    if d0 > _PD["singlet_dominance"].default * max(d1, 1e-10) and abs(by_d[0]["pos"]) < 2.5:
        return "Singlete", [by_d[0]]
    if len(by_d) >= 2 and d1 >= _PD["doublet_ratio_min"].default * d0 and d2 < _PD["doublet_ratio_max"].default * d0 and len(peaks) <= 4:
        pair = sorted([by_d[0], by_d[1]], key=lambda p: p["pos"])
        sep = abs(pair[1]["pos"] - pair[0]["pos"])
        if _FI["doublet_sep_min"].default <= sep <= _FI["doublet_sep_max"].default:
            return "Doblete", pair
    return None

def components_from_peaks(peaks: list[dict], baseline: float, slope: float,
                           multiplicities: dict[int, int] | None = None
                           ) -> tuple[list[tuple[int, str, list[dict]]], dict[str, float]]:
    """Componentes (índice, tipo, mínimos) y sus parámetros iniciales a
    partir de los mínimos detectados, numeradas desde 1. No toca la GUI."""
    params: dict[str, float] = {
        "baseline": baseline,
        "slope": float(np.clip(slope, -1e-4, 1e-4)),
    }
    for idx in range(1, MAX_COMPONENTS + 1):
        p = f"s{idx}_"
        params.update({
            p + "delta": 0.0, p + "quad": 0.0, p + "bhf": BHF_DEFAULT_T,
            p + "gamma1": 0.30, p + "gamma2": 1.0, p + "gamma3": 1.0,
            p + "depth": 0.005, p + "int1": 3.0, p + "int2": 2.0, p + "int3": 1.0,
        })

    components: list[tuple[int, str, list[dict[str, float]]]] = []
    used_ids: set[int] = set()

    hint = _depth_profile_hint(peaks)
    if hint is not None:
        kind_h, group_h = hint
        components.append((1, kind_h, group_h))
        pfx = "s1_"
        if kind_h == "Doblete":
            g = group_h
            params[pfx + "delta"] = float(np.mean([g[0]["pos"], g[1]["pos"]]))
            params[pfx + "quad"] = float(abs(g[1]["pos"] - g[0]["pos"]))
            params[pfx + "gamma1"] = float(np.clip(np.mean([x["width"] for x in g]), _FI["init_gamma_min"].default, _FI["init_gamma_max"].default))
            params[pfx + "gamma2"] = 1.0
            params[pfx + "depth"] = float(np.clip(np.mean([x["depth"] for x in g]), _FI["init_depth_min"].default, _FI["init_depth_max"].default))
            params[pfx + "int1"] = 1.0
            params[pfx + "int2"] = 1.0
        else:
            pk = group_h[0]
            params[pfx + "delta"] = float(pk["pos"])
            params[pfx + "gamma1"] = float(np.clip(pk["width"], _FI["init_gamma_min"].default, _FI["init_gamma_max"].default))
            params[pfx + "depth"] = float(np.clip(pk["depth"], _FI["init_depth_min"].default, _FI["init_depth_max"].default))
            params[pfx + "int1"] = 1.0
        used_ids.update(int(pk["i"]) for pk in group_h)
    else:
        sext = _best_sextet_from_peaks(peaks)
        if sext is not None:
            sub, delta, bhf, width, depth = sext
            if len(sub) >= 5 and abs(sub[-1]["pos"] - sub[0]["pos"]) > 3.0:
                components.append((1, "Sextete", sub))
                p = "s1_"
                params[p + "delta"] = float(np.clip(delta, _FI["init_delta_lo"].default, _FI["init_delta_hi"].default))
                params[p + "bhf"] = float(np.clip(bhf, _FI["init_bhf_min"].default, _FI["sextet_bhf_max"].default))
                params[p + "quad"] = 0.0
                params[p + "gamma1"] = float(np.clip(width, _FI["init_gamma_min"].default, _FI["init_gamma_max"].default))
                params[p + "depth"] = float(np.clip(depth, _FI["init_depth_min"].default, _FI["init_depth_max"].default))
                used_ids.update(int(pk["i"]) for pk in sub)

    remaining = [p for p in sorted(peaks, key=lambda q: q["smooth_depth"], reverse=True)
                 if int(p["i"]) not in used_ids]
    # Centros admisibles para un componente nuevo: rango de inicialización
    # dentro de las cotas de δ del ajuste.
    delta_lo = max(_FI["init_delta_lo"].default, COMPONENT_FIT_BOUNDS["delta"][0])
    delta_hi = min(_FI["init_delta_hi"].default, COMPONENT_FIT_BOUNDS["delta"][1])
    next_idx = 2 if components else 1
    while next_idx <= min(3, MAX_COMPONENTS) and remaining:
        if len(remaining) >= 5:
            sext_extra = _best_sextet_from_peaks(remaining)
            if sext_extra is not None:
                sub_e, delta_e, bhf_e, width_e, depth_e = sext_extra
                if len(sub_e) >= 5 and abs(sub_e[-1]["pos"] - sub_e[0]["pos"]) > 3.0:
                    pfx = f"s{next_idx}_"
                    components.append((next_idx, "Sextete", sub_e))
                    params[pfx + "delta"] = float(np.clip(delta_e, _FI["init_delta_lo"].default, _FI["init_delta_hi"].default))
                    params[pfx + "bhf"] = float(np.clip(bhf_e, _FI["init_bhf_min"].default, _FI["sextet_bhf_max"].default))
                    params[pfx + "quad"] = 0.0
                    params[pfx + "gamma1"] = float(np.clip(width_e, _FI["init_gamma_min"].default, _FI["init_gamma_max"].default))
                    params[pfx + "depth"] = float(np.clip(depth_e, _FI["init_depth_min"].default, _FI["init_depth_max"].default))
                    sub_ids = {int(pk["i"]) for pk in sub_e}
                    remaining = [p for p in remaining if int(p["i"]) not in sub_ids]
                    next_idx += 1
                    continue
        # Sobrantes fuera del rango de un centro paramagnético: son líneas de
        # otro sextete que comparte las interiores con uno ya encontrado.
        if any(not (delta_lo <= p["pos"] <= delta_hi) for p in remaining):
            shared = _sextet_sharing_lines(remaining, peaks)
            if shared is not None:
                sub_s, delta_s, bhf_s, width_s, depth_s = shared
                pfx = f"s{next_idx}_"
                components.append((next_idx, "Sextete", sub_s))
                params[pfx + "delta"] = float(np.clip(delta_s, delta_lo, delta_hi))
                params[pfx + "bhf"] = float(np.clip(bhf_s, _FI["init_bhf_min"].default, _FI["sextet_bhf_max"].default))
                params[pfx + "quad"] = 0.0
                params[pfx + "gamma1"] = float(np.clip(width_s, _FI["init_gamma_min"].default, _FI["init_gamma_max"].default))
                params[pfx + "depth"] = float(np.clip(depth_s, _FI["init_depth_min"].default, _FI["init_depth_max"].default))
                sub_ids = {int(pk["i"]) for pk in sub_s}
                remaining = [p for p in remaining if int(p["i"]) not in sub_ids]
                next_idx += 1
                continue
            # Sin sextete posible: un singlete o doblete con el centro fuera
            # de las cotas de δ ni siquiera arrancaría el ajuste.
            remaining = [p for p in remaining if delta_lo <= p["pos"] <= delta_hi]
            if not remaining:
                break
        two_peak_sext = _try_2peak_sextet_estimate(remaining) if len(remaining) == 2 else None
        if two_peak_sext is not None:
            sub2, delta2, bhf2, width2, depth2 = two_peak_sext
            pfx = f"s{next_idx}_"
            components.append((next_idx, "Sextete", sub2))
            params[pfx + "delta"] = float(np.clip(delta2, _FI["init_delta_lo"].default, _FI["init_delta_hi"].default))
            params[pfx + "bhf"] = float(np.clip(bhf2, _FI["init_bhf_min"].default, _FI["sextet_bhf_max"].default))
            params[pfx + "quad"] = 0.0
            params[pfx + "gamma1"] = float(np.clip(width2, _FI["init_gamma_min"].default, _FI["init_gamma_max"].default))
            params[pfx + "depth"] = float(np.clip(depth2, _FI["init_depth_min"].default, _FI["init_depth_max"].default))
            remaining.clear()
            next_idx += 1
            continue
        if len(remaining) >= 2:
            pair = sorted(remaining[:2], key=lambda p: p["pos"])
            sep = abs(pair[1]["pos"] - pair[0]["pos"])
            mid = 0.5 * (pair[0]["pos"] + pair[1]["pos"])
            if (_FI["doublet_sep_min"].default <= sep <= _FI["doublet_sep_max"].default
                    and delta_lo <= mid <= delta_hi):
                kind = "Doblete"
                group = pair
                remaining = [p for p in remaining if p not in pair]
            else:
                kind = "Singlete"
                group = [remaining.pop(0)]
        else:
            kind = "Singlete"
            group = [remaining.pop(0)]
        components.append((next_idx, kind, group))
        pfx = f"s{next_idx}_"
        if kind == "Doblete":
            g = sorted(group, key=lambda p: p["pos"])
            params[pfx + "delta"] = float(np.mean([g[0]["pos"], g[1]["pos"]]))
            params[pfx + "quad"] = float(abs(g[1]["pos"] - g[0]["pos"]))
            params[pfx + "gamma1"] = float(np.clip(np.mean([x["width"] for x in g]), _FI["init_gamma_min"].default, _FI["init_gamma_max"].default))
            params[pfx + "gamma2"] = 1.0
            params[pfx + "depth"] = float(np.clip(np.mean([x["depth"] for x in g]), _FI["init_depth_min"].default, _FI["init_depth_max"].default))
            params[pfx + "int1"] = 1.0
            params[pfx + "int2"] = 1.0
        else:
            g = group[0]
            params[pfx + "delta"] = float(g["pos"])
            params[pfx + "gamma1"] = float(np.clip(g["width"], _FI["init_gamma_min"].default, _FI["init_gamma_max"].default))
            params[pfx + "depth"] = float(np.clip(g["depth"], _FI["init_depth_min"].default, _FI["init_depth_max"].default))
            params[pfx + "int1"] = 1.0
        next_idx += 1

    if not components:
        g = max(peaks, key=lambda p: p["depth"])
        components.append((1, "Singlete", [g]))
        params["s1_delta"] = float(g["pos"])
        params["s1_gamma1"] = float(np.clip(g["width"], _FI["init_gamma_min"].default, _FI["init_gamma_max"].default))
        params["s1_depth"] = float(np.clip(g["depth"], _FI["init_depth_min"].default, _FI["init_depth_max"].default))

    # Contribuciones extra señaladas por el usuario: cada mínimo marcado con
    # n>1 añade (n-1) singletes solapados en esa posición, hasta el máximo de
    # componentes, para que el ajuste pueda separar las contribuciones.
    if multiplicities:
        next_extra = max((idx for idx, _k, _g in components), default=0) + 1
        for pk in peaks:
            extra = int(multiplicities.get(int(pk["i"]), 1)) - 1
            for _ in range(max(0, extra)):
                if next_extra > MAX_COMPONENTS:
                    break
                pfx = f"s{next_extra}_"
                components.append((next_extra, "Singlete", [pk]))
                params[pfx + "delta"] = float(pk["pos"])
                params[pfx + "gamma1"] = float(np.clip(pk["width"], _FI["init_gamma_min"].default, _FI["init_gamma_max"].default))
                params[pfx + "depth"] = float(np.clip(pk["depth"] * 0.5, _FI["init_depth_min"].default, _FI["init_depth_max"].default))
                params[pfx + "int1"] = 1.0
                next_extra += 1

    return components, params
