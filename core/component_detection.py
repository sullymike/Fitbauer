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


# ═══════════════════════════════════════════════════════════════════════════
# Propuestas evaluadas: varias interpretaciones de los mismos mínimos, cada
# una ajustada en local y comparada por BIC; después, revisión del residuo.
# ═══════════════════════════════════════════════════════════════════════════
from dataclasses import dataclass, field, replace  # noqa: E402

#: Una componente añadida tras mirar el residuo se queda solo si baja el BIC
#: al menos esto (evidencia fuerte; mismo umbral que «Autoajustar el residuo»).
RESIDUAL_DBIC = -6.0
#: Propuestas que se ajustan en no lineal (las demás solo se puntúan con NNLS).
MAX_FITS = 6
#: Componentes como mucho en una propuesta de la búsqueda.
MAX_SEARCH_COMPONENTS = 6
#: Anchura del haz en la búsqueda hacia delante (alternativas que se conservan
#: en cada paso).
BEAM_WIDTH = 4

#: Al comparar propuestas, el doblete es simétrico y el sextete tiene las
#: tres anchuras iguales: si no, un doblete asimétrico tiene los mismos
#: parámetros que dos singletes y el BIC no los distingue. La propuesta que se
#: aplique al panel los deja libres, como siempre.
_COMPARE_FIXED = {"Doblete": ("gamma2", "int2"), "Sextete": ("gamma2", "gamma3")}

#: Parámetros no lineales que aporta cada tipo a la puntuación NNLS (solo
#: para comparar propuestas antes de ajustarlas).
_NNLS_K = {"Singlete": 3, "Doblete": 4, "Sextete": 6}


@dataclass
class Proposal:
    """Una interpretación del espectro: componentes ``(idx, tipo, mínimos)``
    numeradas desde 1 y sus parámetros de partida (``sN_*``, baseline, slope).

    ``origin`` dice de dónde sale (clave de texto + datos para formatearla);
    tras evaluarla, ``chi2``/``red_chi2``/``bic``/``n_params`` son los del
    ajuste local y ``values`` los valores ajustados.
    """
    origin: tuple[str, dict]
    components: list[tuple[int, str, list[dict]]]
    params: dict[str, float]
    nnls_score: float = float("inf")
    fitted: bool = False
    chi2: float = float("nan")
    red_chi2: float = float("nan")
    bic: float = float("inf")
    n_params: int = 0
    values: dict[str, float] = field(default_factory=dict)
    #: Índices de componente que se comparan con su forma completa (doblete
    #: asimétrico): los que salen de juntar dos singletes.
    full_shape: set[int] = field(default_factory=set)

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(k for _i, k, _g in self.components)

    def signature(self) -> tuple:
        """Para no evaluar dos veces la misma propuesta."""
        out = []
        for idx, kind, _g in self.components:
            p = f"s{idx}_"
            out.append((kind, round(self.params.get(p + "delta", 0.0), 1),
                        round(self.params.get(p + "quad", 0.0), 1) if kind == "Doblete" else 0.0,
                        round(self.params.get(p + "bhf", 0.0)) if kind == "Sextete" else 0.0))
        return tuple(sorted(out))


@dataclass
class DetectionReport:
    """Todo lo que se decidió, para enseñarlo."""
    peaks: list[dict]
    baseline: float
    slope: float
    proposals: list[Proposal]            # evaluadas, de menor a mayor BIC
    chosen: Proposal                     # la de menor BIC
    #: Cambios tras elegir, en orden: ``{"removed"|"added": tipo, "idx",
    #: "origin", "dbic", "accepted", "proposal"}`` (poda y residuo).
    residual_steps: list[dict]
    final: Proposal                      # la elegida + lo aceptado del residuo


# ── Formas de línea para la preselección lineal ──────────────────────────────
def _lorentz(v: np.ndarray, c: float, fwhm: float) -> np.ndarray:
    hw = max(float(fwhm), 1e-3) / 2.0
    return 1.0 / (1.0 + ((v - c) / hw) ** 2)


def _line_positions(kind: str, params: dict, idx: int) -> list[tuple[float, float]]:
    """(posición, peso) de las líneas de la componente ``idx`` (1er orden)."""
    p = f"s{idx}_"
    d = float(params.get(p + "delta", 0.0))
    if kind == "Singlete":
        return [(d, 1.0)]
    if kind == "Doblete":
        q = float(params.get(p + "quad", 0.0))
        return [(d - q / 2.0, 1.0), (d + q / 2.0, 1.0)]
    scale = float(params.get(p + "bhf", BHF_DEFAULT_T)) / BHF_DEFAULT_T
    eps = float(params.get(p + "quad", 0.0)) / 2.0
    shift = (eps, -eps, -eps, -eps, -eps, eps)
    return [(d + scale * float(x) + s, float(w))
            for x, w, s in zip(LINE_POS_33T, SEXTET_WEIGHTS, shift)]


def _basis(v: np.ndarray, kind: str, params: dict, idx: int) -> np.ndarray:
    g = float(params.get(f"s{idx}_gamma1", 0.3))
    col = np.zeros_like(v, dtype=float)
    for c, w in _line_positions(kind, params, idx):
        col += w * _lorentz(v, c, g)
    return col


def _nnls_fit(v, absorption, sigma, cols: list[np.ndarray]) -> tuple[float, np.ndarray]:
    """χ² y amplitudes (≥ 0) del ajuste lineal de la absorción con las
    columnas dadas y un desplazamiento constante libre de signo."""
    from scipy.optimize import nnls
    w = 1.0 / np.maximum(sigma, 1e-12)
    ones = np.ones_like(v, dtype=float)
    A = np.column_stack(cols + [ones, -ones]) if cols else np.column_stack([ones, -ones])
    coef, _ = nnls(A * w[:, None], absorption * w)
    r = (absorption - A @ coef) * w
    return float(r @ r), coef[:len(cols)]


def _nnls_score(chi2: float, kinds, n: int) -> float:
    k = sum(_NNLS_K.get(kd, 6) for kd in kinds) + 2
    return n * np.log(max(chi2 / n, 1e-300)) + k * np.log(n)


# ── Candidatas ───────────────────────────────────────────────────────────────
def _clip(x, lo, hi):
    return float(np.clip(x, lo, hi))


def _component_params(idx: int, kind: str, *, delta: float, gamma: float,
                      depth: float, quad: float = 0.0, bhf: float = BHF_DEFAULT_T) -> dict:
    """Parámetros de partida de una componente, con los mismos recortes que
    las reglas."""
    p = f"s{idx}_"
    out = {p + "delta": float(delta), p + "quad": float(quad), p + "bhf": float(bhf),
           p + "gamma1": _clip(gamma, _FI["init_gamma_min"].default, _FI["init_gamma_max"].default),
           p + "gamma2": 1.0, p + "gamma3": 1.0,
           p + "depth": _clip(depth, _FI["init_depth_min"].default, _FI["init_depth_max"].default),
           p + "int1": 3.0, p + "int2": 2.0, p + "int3": 1.0}
    if kind == "Doblete":
        out[p + "int1"] = 1.0
        out[p + "int2"] = 1.0
    elif kind == "Singlete":
        out[p + "int1"] = 1.0
    return out


def _delta_range() -> tuple[float, float]:
    return (max(_FI["init_delta_lo"].default, COMPONENT_FIT_BOUNDS["delta"][0]),
            min(_FI["init_delta_hi"].default, COMPONENT_FIT_BOUNDS["delta"][1]))


def _candidate_pool(peaks: list[dict], rules: Proposal) -> list[dict]:
    """Componentes sueltas posibles: un singlete por mínimo, un doblete por
    cada par compatible (aunque compartan una línea con otra componente) y
    los sextetes que encontraron las reglas."""
    lo, hi = _delta_range()
    sep_lo, sep_hi = _FI["doublet_sep_min"].default, _FI["doublet_sep_max"].default
    pool: list[dict] = []
    for pk in peaks:
        if lo <= pk["pos"] <= hi:
            pool.append({"kind": "Singlete", "ids": (int(pk["i"]),),
                         "p": dict(delta=pk["pos"], gamma=pk["width"], depth=pk["depth"])})
    for a in range(len(peaks)):
        for b in range(a + 1, len(peaks)):
            pa, pb = sorted((peaks[a], peaks[b]), key=lambda q: q["pos"])
            sep = pb["pos"] - pa["pos"]
            mid = 0.5 * (pa["pos"] + pb["pos"])
            if not (sep_lo <= sep <= sep_hi and lo <= mid <= hi):
                continue
            pool.append({"kind": "Doblete", "ids": (int(pa["i"]), int(pb["i"])),
                         "p": dict(delta=mid, quad=sep,
                                   gamma=min(pa["width"], pb["width"]),
                                   depth=min(pa["depth"], pb["depth"]))})
    for idx, kind, g in rules.components:
        if kind == "Sextete":
            p = f"s{idx}_"
            pool.append({"kind": "Sextete", "ids": tuple(int(pk["i"]) for pk in g),
                         "p": dict(delta=rules.params[p + "delta"], bhf=rules.params[p + "bhf"],
                                   quad=rules.params.get(p + "quad", 0.0),
                                   gamma=rules.params[p + "gamma1"],
                                   depth=rules.params[p + "depth"])})
    return pool


def _proposal_from_candidates(cands: list[dict], peaks: list[dict], baseline: float,
                              slope: float, origin: tuple[str, dict],
                              amplitudes=None) -> Proposal:
    by_id = {int(pk["i"]): pk for pk in peaks}
    params: dict[str, float] = {"baseline": float(baseline),
                                "slope": float(np.clip(slope, -1e-4, 1e-4))}
    comps = []
    for n, c in enumerate(cands, start=1):
        kw = dict(c["p"])
        if amplitudes is not None and amplitudes[n - 1] > 0:
            kw["depth"] = float(amplitudes[n - 1])
        params.update(_component_params(n, c["kind"], **kw))
        comps.append((n, c["kind"], [by_id[i] for i in c["ids"] if i in by_id]))
    return Proposal(origin=origin, components=comps, params=params)


def _renumber(components, params, keep: list[int]) -> tuple[list, dict]:
    """Componentes ``keep`` (índices viejos) renumeradas desde 1."""
    new_c, new_p = [], {k: v for k, v in params.items() if _comp_index(k) is None}
    for n, old in enumerate(keep, start=1):
        kind, g = next((k, g) for i, k, g in components if i == old)
        new_c.append((n, kind, g))
        for k, v in params.items():
            if _comp_index(k) == old:
                new_p[f"s{n}_" + k.split("_", 1)[1]] = v
    return new_c, new_p


def _comp_index(key: str) -> int | None:
    """``3`` para ``s3_delta``; ``None`` para globales (``slope``, ``baseline``…)."""
    if not key.startswith("s") or "_" not in key:
        return None
    head = key.split("_", 1)[0][1:]
    return int(head) if head.isdigit() else None


def generate_proposals(v, y, sigma, peaks, baseline, slope) -> list[Proposal]:
    """Interpretaciones candidatas, puntuadas con NNLS (menor = mejor).

    1. Las reglas (``components_from_peaks``).
    2. Las reglas sin cada una de sus componentes (por si sobra una).
    3. Las reglas con cada singlete convertido en doblete con otro mínimo
       (su otra línea puede estar tapada por otra componente).
    4. Búsqueda hacia delante en haz sobre las candidatas sueltas (singletes,
       dobletes, también los que comparten línea, y los sextetes de las
       reglas): en cada paso se añade la que más baja la puntuación.
    """
    v = np.asarray(v, dtype=float)
    absorption = (baseline + slope * v) - np.asarray(y, dtype=float)
    n = v.size
    comps, params = components_from_peaks(peaks, baseline, slope)
    rules = Proposal(origin=("detect.origin_rules", {}), components=comps, params=params)
    out = [rules]
    if len(comps) > 1:
        for idx, kind, _g in comps:
            keep = [i for i, _k, _g in comps if i != idx]
            c2, p2 = _renumber(comps, params, keep)
            out.append(Proposal(origin=("detect.origin_drop", {"idx": idx, "kind": kind}),
                                components=c2, params=p2))
    lo, hi = _delta_range()
    sep_lo, sep_hi = _FI["doublet_sep_min"].default, _FI["doublet_sep_max"].default
    for idx, kind, g in comps:
        if kind != "Singlete" or not g:
            continue
        s = g[0]
        for other in peaks:
            if int(other["i"]) == int(s["i"]):
                continue
            a, b = sorted((s["pos"], other["pos"]))
            sep, mid = b - a, 0.5 * (a + b)
            if not (sep_lo <= sep <= sep_hi and lo <= mid <= hi):
                continue
            p2 = dict(params)
            p2.update(_component_params(idx, "Doblete", delta=mid, quad=sep,
                                        gamma=s["width"], depth=s["depth"]))
            c2 = [(i, "Doblete" if i == idx else k, (gg + [other]) if i == idx else gg)
                  for i, k, gg in comps]
            out.append(Proposal(origin=("detect.origin_singlet_doublet",
                                        {"idx": idx, "pos": f"{other['pos']:.2f}"}),
                                components=c2, params=p2))
    # Búsqueda en haz con NNLS.
    pool = _candidate_pool(peaks, rules)
    cols = [_basis(v, c["kind"], _component_params(1, c["kind"], **c["p"]), 1) for c in pool]
    beam: list[tuple[float, tuple[int, ...]]] = [(np.inf, ())]
    found: dict[tuple[int, ...], float] = {}
    for _step in range(min(MAX_SEARCH_COMPONENTS, MAX_COMPONENTS)):
        nxt: dict[tuple[int, ...], float] = {}
        for _sc, sel in beam:
            for j in range(len(pool)):
                if j in sel:
                    continue
                key = tuple(sorted(sel + (j,)))
                if key in nxt or key in found:
                    continue
                chi2, amp = _nnls_fit(v, absorption, sigma, [cols[i] for i in key])
                if np.any(amp <= 0):       # una componente que no aporta nada
                    continue
                nxt[key] = _nnls_score(chi2, [pool[i]["kind"] for i in key], n)
        if not nxt:
            break
        best_prev = min(found.values()) if found else np.inf
        ranked = sorted(nxt.items(), key=lambda kv: kv[1])[:BEAM_WIDTH]
        found.update(ranked)
        if ranked[0][1] > best_prev:   # añadir ya no mejora
            break
        beam = [(sc, key) for key, sc in ranked]
    # Las dos mejores de cada tamaño (si no, las de más componentes, que con
    # formas fijas siempre «explican» algo más, desplazan a las sencillas).
    elegidas: list[tuple[int, ...]] = []
    for size in sorted({len(k) for k in found}):
        mismas = sorted((kv for kv in found.items() if len(kv[0]) == size), key=lambda kv: kv[1])
        elegidas.extend(k for k, _sc in mismas[:2])
    for key in elegidas:
        cands = sorted((pool[i] for i in key), key=lambda c: c["p"]["delta"])
        _chi2, amp = _nnls_fit(v, absorption, sigma,
                               [_basis(v, c["kind"], _component_params(1, c["kind"], **c["p"]), 1)
                                for c in cands])
        out.append(_proposal_from_candidates(
            cands, peaks, baseline, slope, ("detect.origin_search", {}), amplitudes=amp))
    # Puntuación NNLS común y sin repetidas.
    uniq: dict[tuple, Proposal] = {}
    for prop in out:
        if not prop.components:
            continue
        cols_p = [_basis(v, k, prop.params, i) for i, k, _g in prop.components]
        chi2, _amp = _nnls_fit(v, absorption, sigma, cols_p)
        prop.nnls_score = _nnls_score(chi2, prop.kinds, n)
        sig = prop.signature()
        if sig not in uniq or (prop.origin[0] == "detect.origin_rules"):
            uniq[sig] = prop
    return sorted(uniq.values(), key=lambda p: p.nnls_score)


# ── Ajuste local de una propuesta ────────────────────────────────────────────
def _proposal_state(base, prop: Proposal):
    """``FitState`` de la propuesta a partir del de la ventana/sesión: sus
    componentes y valores de partida, todo lo propio de cada tipo libre,
    estrategia local sin perturbaciones y sin ligaduras (los índices cambian)."""
    from core.fit_engine import Component
    from core.params import COMPONENT_SOFT_BOUNDS, relevant_params
    values = dict(base.values)
    values.update(prop.params)
    fixed = dict(base.fixed)
    bounds = dict(base.bounds)
    soft = dict(getattr(base, "soft_bounds", {}) or {})
    comps = []
    for idx, kind, _g in prop.components:
        p = f"s{idx}_"
        relevant = relevant_params(kind, "free", "1st_order")
        for name, rng in COMPONENT_FIT_BOUNDS.items():
            key = p + name
            if key not in values:
                values[key] = float(np.clip(1.0, *rng)) if name.startswith("int") else float(rng[0])
            bounds[key] = base.bounds.get(f"s1_{name}", rng) if key not in base.bounds else base.bounds[key]
            fixed[key] = (name not in relevant or name == "int3"
                          or (idx not in prop.full_shape
                              and name in _COMPARE_FIXED.get(kind, ())))
        for name, rng in COMPONENT_SOFT_BOUNDS.items():
            soft.setdefault(p + name, rng)
        comps.append(Component(idx=idx, enabled=True, kind=kind,
                               intensity_mode="free", quad_treatment="1st_order"))
    # Lo de componentes que no están en la propuesta, fijo: si no, cuenta
    # como parámetro libre en el BIC sin hacer nada.
    propias = {idx for idx, _k, _g in prop.components}
    for key in list(fixed):
        i = _comp_index(key)
        if i is not None and i not in propias:
            fixed[key] = True
    for key in ("baseline", "slope"):
        if key in values:
            fixed[key] = False
    return replace(base, values=values, fixed=fixed, bounds=bounds, soft_bounds=soft,
                   components=comps, constraints=[], fit_strategy="local",
                   multistart_n=0, global_opt=False, auto_global=False,
                   fit_velocity=False, fit_center=False, max_step_frac=0.0)


def fit_proposal(base, prop: Proposal) -> Proposal:
    """Ajusta la propuesta en local y guarda χ², BIC y valores."""
    from core.fit_engine import fit_discrete
    try:
        res = fit_discrete(_proposal_state(base, prop))
    except Exception:                                   # noqa: BLE001
        prop.fitted = True
        return prop
    prop.fitted = True
    prop.chi2 = float(res.stats.get("chi2", np.nan))
    prop.red_chi2 = float(res.stats.get("red_chi2", np.nan))
    prop.bic = float(res.stats.get("bic", np.inf))
    prop.n_params = int(res.stats.get("n_params", 0))
    prop.values = dict(res.values)
    return prop


def _fitted_model(base, prop: Proposal) -> np.ndarray:
    from core.fit_engine import model_from_values
    st = _proposal_state(base, prop)
    st.values.update(prop.values)
    return model_from_values(st.velocity, st.values, st.components, [],
                             absorber_model=st.absorber_model)


def _residual_candidates(base, prop: Proposal, peaks: list[dict]) -> list[Proposal]:
    """Propuestas con una componente más donde el residuo deja estructura:
    las que proponen las reglas sobre el residuo y, para cada mínimo del
    residuo, un doblete con cada mínimo original compatible."""
    v = np.asarray(base.velocity, dtype=float)
    y = np.asarray(base.y_data, dtype=float)
    vals = prop.values or prop.params
    fondo = float(vals.get("baseline", 1.0)) + float(vals.get("slope", 0.0)) * v
    try:
        model = _fitted_model(base, prop)
    except Exception:                                   # noqa: BLE001
        return []
    y_res = y - model + fondo
    res_peaks, b, s = detect_minima(v, y_res)
    ruido = float(np.std(np.diff(y))) / np.sqrt(2.0)
    hondo = max((float(p.get("smooth_depth", p["depth"])) for p in res_peaks), default=0.0)
    umbral = max(2.0 * ruido, 0.25 * hondo)
    res_peaks = [p for p in res_peaks if float(p.get("smooth_depth", p["depth"])) >= umbral]
    if not res_peaks:
        return []
    n0 = len(prop.components)
    if n0 >= MAX_COMPONENTS:
        return []
    base_params = _start_params(prop)
    nuevas: list[tuple[str, dict, list[dict], tuple[str, dict]]] = []
    comps_r, params_r = components_from_peaks(res_peaks, b, s)
    for idx, kind, g in comps_r:
        p = f"s{idx}_"
        nuevas.append((kind, {k.split("_", 1)[1]: params_r[k] for k in params_r if k.startswith(p)},
                       g, ("detect.residual_rules", {"kind": kind})))
    lo, hi = _delta_range()
    sep_lo, sep_hi = _FI["doublet_sep_min"].default, _FI["doublet_sep_max"].default
    for rp in res_peaks:
        for op in peaks:
            a, c = sorted((rp["pos"], op["pos"]))
            sep, mid = c - a, 0.5 * (a + c)
            if sep_lo <= sep <= sep_hi and lo <= mid <= hi:
                pp = _component_params(1, "Doblete", delta=mid, quad=sep,
                                       gamma=rp["width"], depth=rp["depth"])
                nuevas.append(("Doblete", {k.split("_", 1)[1]: x for k, x in pp.items()},
                               [rp, op], ("detect.residual_pair",
                                          {"pos": f"{rp['pos']:.2f}", "with": f"{op['pos']:.2f}"})))
    out = []
    for kind, pars, g, origin in nuevas:
        idx = n0 + 1
        p2 = dict(base_params)
        p2.update({f"s{idx}_{k}": float(x) for k, x in pars.items()})
        out.append(Proposal(origin=origin, components=list(prop.components) + [(idx, kind, g)],
                            params=p2, full_shape=set(prop.full_shape)))
    # Preselección NNLS sobre el residuo: las 4 que más lo explican.
    absorption = fondo - y
    sigma = (np.asarray(base.sigma_data, dtype=float) if base.sigma_data is not None
             else np.full_like(v, max(ruido, 1e-6)))
    for q in out:
        cols = [_basis(v, k, q.params, i) for i, k, _g in q.components]
        chi2, _a = _nnls_fit(v, absorption, sigma, cols)
        q.nnls_score = _nnls_score(chi2, q.kinds, v.size)
    uniq: dict[tuple, Proposal] = {}
    for q in sorted(out, key=lambda q: q.nnls_score):
        uniq.setdefault(q.signature(), q)
    return list(uniq.values())[:4]


def _start_params(prop: Proposal) -> dict:
    """Parámetros de partida = los ajustados de ``prop`` (o los suyos)."""
    start = dict(prop.params)
    start.update({k: float(x) for k, x in (prop.values or {}).items()
                  if k.startswith("s") or k in ("baseline", "slope")})
    return start


def _simplifications(prop: Proposal) -> list[Proposal]:
    """La propuesta sin cada componente, y con cada par de singletes
    compatible convertido en un doblete."""
    start = _start_params(prop)
    out = []
    for idx, kind, _g in prop.components:
        keep = [i for i, _k, _g in prop.components if i != idx]
        c2, p2 = _renumber(prop.components, start, keep)
        out.append(Proposal(origin=("detect.origin_drop", {"idx": idx, "kind": kind}),
                            components=c2, params=p2,
                            full_shape={keep.index(i) + 1 for i in prop.full_shape if i in keep}))
    lo, hi = _delta_range()
    sep_lo, sep_hi = _FI["doublet_sep_min"].default, _FI["doublet_sep_max"].default
    singles = [(i, g) for i, k, g in prop.components if k == "Singlete"]
    for a in range(len(singles)):
        for b in range(a + 1, len(singles)):
            (ia, ga), (ib, gb) = singles[a], singles[b]
            da, db = start[f"s{ia}_delta"], start[f"s{ib}_delta"]
            lo_d, hi_d = sorted((da, db))
            sep, mid = hi_d - lo_d, 0.5 * (lo_d + hi_d)
            if not (sep_lo <= sep <= sep_hi and lo <= mid <= hi):
                continue
            keep = [i for i, _k, _g in prop.components if i != ib]
            c2, p2 = _renumber(prop.components, start, keep)
            n = keep.index(ia) + 1
            # Doblete asimétrico: con Γ₂ e I₂ libres tiene los mismos
            # parámetros que los dos singletes y parte de su misma forma (la
            # línea de la izquierda es la 1; I₂ es la razón de profundidades).
            (il, gl), (ir, gr_) = sorted(((ia, da), (ib, db)), key=lambda t: t[1])
            p2.update(_component_params(n, "Doblete", delta=mid, quad=sep,
                                        gamma=start[f"s{il}_gamma1"],
                                        depth=start[f"s{il}_depth"]))
            p2[f"s{n}_gamma2"] = float(np.clip(start[f"s{ir}_gamma1"]
                                               / max(start[f"s{il}_gamma1"], 1e-6), 0.2, 6.0))
            p2[f"s{n}_int2"] = float(np.clip(start[f"s{ir}_depth"]
                                             / max(start[f"s{il}_depth"], 1e-9), 0.05, 6.0))
            c2 = [(i, "Doblete" if i == n else k, (g + gb) if i == n else g) for i, k, g in c2]
            full = {keep.index(i) + 1 for i in prop.full_shape if i in keep} | {n}
            out.append(Proposal(origin=("detect.origin_merge",
                                        {"idx": ia, "other": ib, "kind": "Singlete"}),
                                components=c2, params=p2, full_shape=full))
    return out


def choose(evaluated: list[Proposal]) -> Proposal:
    """La de menor BIC, salvo que otra con MENOS componentes quede a menos de
    ``-RESIDUAL_DBIC`` de ella: entonces la más sencilla (una componente más
    tiene que bajar el BIC al menos 6 para ganarse el sitio)."""
    best = min(evaluated, key=lambda p: p.bic)
    cerca = [p for p in evaluated if p.bic - best.bic < -RESIDUAL_DBIC]
    return min(cerca, key=lambda p: (len(p.components), p.bic))


def evaluate_detection(base, peaks: list[dict] | None = None, baseline: float | None = None,
                       slope: float | None = None, *, max_fits: int = MAX_FITS,
                       residual_rounds: int = 2, progress=None) -> DetectionReport | None:
    """Detecta, propone varias interpretaciones, ajusta las mejores y elige.

    ``base`` es el ``FitState`` de la ventana o la sesión (datos, σ, cotas,
    opciones); de él solo se toman los datos y las opciones, no las
    componentes. ``peaks`` permite pasar mínimos curados a mano. ``progress``
    recibe ``(hechas, total)`` para enseñar el avance.
    """
    v = np.asarray(base.velocity, dtype=float)
    y = np.asarray(base.y_data, dtype=float)
    if peaks is None:
        peaks, baseline, slope = detect_minima(v, y)
    elif baseline is None or slope is None:
        _p, baseline, slope = detect_minima(v, y)
    if not peaks:
        return None
    ruido = float(np.std(np.diff(y))) / np.sqrt(2.0)
    sigma = (np.asarray(base.sigma_data, dtype=float) if base.sigma_data is not None
             else np.full_like(v, max(ruido, 1e-6)))
    props = generate_proposals(v, y, sigma, peaks, baseline, slope)
    rules = next(p for p in props if p.origin[0] == "detect.origin_rules")
    to_fit = props[:max_fits]
    if rules not in to_fit:
        to_fit = to_fit[:-1] + [rules]
    total = len(to_fit) + 4 * residual_rounds
    done = 0
    for prop in to_fit:
        fit_proposal(base, prop)
        done += 1
        if progress:
            progress(done, total)
    evaluated = sorted([p for p in to_fit if np.isfinite(p.bic)], key=lambda p: p.bic)
    if not evaluated:
        return None
    chosen = choose(evaluated)
    final = chosen
    steps: list[dict] = []
    # Simplificar: quitar una componente que no se gana el sitio o juntar dos
    # singletes en un doblete. Se acepta si el BIC no sube al menos 6 (la
    # más sencilla gana salvo evidencia fuerte), desde los valores ajustados.
    while len(final.components) > 1:
        simples = [q for q in _simplifications(final) if np.isfinite(fit_proposal(base, q).bic)]
        if not simples:
            break
        q = min(simples, key=lambda t: t.bic)
        dbic = q.bic - final.bic
        if dbic >= -RESIDUAL_DBIC:
            break
        steps.append({"removed": q.origin[1]["kind"], "idx": q.origin[1]["idx"],
                      "origin": q.origin, "dbic": float(dbic), "accepted": True, "proposal": q})
        final = q
    for _r in range(residual_rounds):
        cands = _residual_candidates(base, final, peaks)
        if not cands:
            break
        for q in cands:
            fit_proposal(base, q)
            done += 1
            if progress:
                progress(done, total)
        best = min(cands, key=lambda q: q.bic)
        dbic = best.bic - final.bic
        added = best.components[-1]
        steps.append({"added": added[1], "idx": added[0], "origin": best.origin, "dbic": float(dbic),
                      "accepted": bool(dbic <= RESIDUAL_DBIC), "proposal": best})
        if dbic > RESIDUAL_DBIC:
            break
        final = best
    return DetectionReport(peaks=peaks, baseline=float(baseline), slope=float(slope),
                           proposals=evaluated, chosen=chosen,
                           residual_steps=steps, final=final)
