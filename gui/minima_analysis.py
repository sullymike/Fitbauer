"""Detección de mínimos e inicialización automática del modelo."""
from __future__ import annotations

import numpy as np
from PySide6 import QtWidgets

from mossbauer_i18n import tr
from core.constants import BHF_DEFAULT_T, LINE_POS_33T
from core.fit_engine import Component, model_from_values
from gui.panels import ComponentPanel

MAX_QT_COMPONENTS = 6


class MinimaAnalysisMixin:
    # ── Auto-inicialización desde mínimos ───────────────────────────────
    def _smooth_1d(self, values: np.ndarray, window: int) -> np.ndarray:
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

    def detect_absorption_minima(self) -> tuple[list[dict[str, float]], float, float]:
        """Detecta mínimos de transmisión como máximos de absorción.

        Qt usaba una detección directa sobre datos sin suavizar y solo miraba la
        primera componente. Esta versión porta la heurística robusta de Tk:
        baseline lineal en la zona alta, umbrales por ruido/prominencia,
        anchuras FWHM aproximadas y eliminación de duplicados cercanos.
        """
        if self.file.velocity is None or self.file.y_data is None or self.file.y_data.size < 7:
            return [], 1.0, 0.0
        v = self.file.velocity
        y = self.file.y_data
        high = y >= np.percentile(y, 70)
        if int(np.sum(high)) >= 4:
            slope, baseline0 = np.polyfit(v[high], y[high], 1)
        else:
            baseline0 = float(np.percentile(y, 90))
            slope = 0.0
        baseline_line = baseline0 + slope * v
        absorption = np.maximum(baseline_line - y, 0.0)

        coarse_smooth = self._smooth_1d(absorption, max(5, absorption.size // 80))
        max_abs = float(np.nanmax(coarse_smooth)) if coarse_smooth.size else 0.0
        if max_abs <= 0:
            return [], float(baseline0), float(slope)
        diff_noise = np.diff(coarse_smooth)
        noise = (1.4826 * float(np.median(np.abs(diff_noise - np.median(diff_noise))))
                 if diff_noise.size else 0.0)

        fine_win = max(3, absorption.size // 120)
        if fine_win % 2 == 0:
            fine_win += 1
        fine_smooth = self._smooth_1d(absorption, fine_win)

        dv = abs(float(v[1] - v[0])) if v.size > 1 else 0.05
        min_dist_ch = max(3, int(0.15 / dv))
        height_thr = max(0.06 * max_abs, 4.0 * noise, 5e-4)
        prom_thr = max(0.05 * max_abs, 2.5 * noise, 3e-4)

        try:
            from scipy.signal import find_peaks as _find_peaks
        except ImportError:
            return [], float(baseline0), float(slope)
        peak_idxs, _ = _find_peaks(fine_smooth, height=height_thr,
                                   prominence=prom_thr, distance=min_dist_ch)

        peaks: list[dict[str, float]] = []
        min_distance = max(0.12, 2.0 * dv)
        for i in peak_idxs:
            half = 0.5 * fine_smooth[i]
            left = int(i)
            while left > 0 and fine_smooth[left] > half:
                left -= 1
            right = int(i)
            while right < fine_smooth.size - 1 and fine_smooth[right] > half:
                right += 1
            width = abs(float(v[right] - v[left])) if right > left else min_distance
            peaks.append({"i": float(i), "pos": float(v[i]),
                          "depth": float(absorption[i]),
                          "smooth_depth": float(fine_smooth[i]),
                          "width": width})

        selected: list[dict[str, float]] = []
        for peak in sorted(peaks, key=lambda p: p["smooth_depth"], reverse=True):
            if all(abs(peak["pos"] - q["pos"]) >= min_distance for q in selected):
                selected.append(peak)
        return sorted(selected[:15], key=lambda p: p["pos"]), float(baseline0), float(slope)

    def _best_sextet_from_peaks(
        self, peaks: list[dict[str, float]]
    ) -> tuple[list[dict[str, float]], float, float, float, float] | None:
        if len(peaks) < 5:
            split = self._try_split_peaks_for_sextet(peaks)
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
                if 10.0 <= bhf <= 60.0 and (best is None or rms < best[0]):
                    weights5 = np.delete(np.array([3.0, 2.0, 1.0, 1.0, 2.0, 3.0]), missing_idx)
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
            if not (10.0 <= bhf <= 60.0):
                continue
            if best is None or rms < best[0]:
                weights = np.array([3.0, 2.0, 1.0, 1.0, 2.0, 3.0], dtype=float)
                depths = np.array([p["depth"] for p in sub], dtype=float)
                depth_est = float(np.median(depths / weights))
                best = (rms, list(sub), float(delta), float(bhf),
                        float(np.median([p["width"] for p in sub])), depth_est)
        if best is None:
            return self._try_split_peaks_for_sextet(peaks)
        score, sub, delta, bhf, width, depth = best
        if score > max(0.45, 0.10 * max(1.0, abs(bhf / BHF_DEFAULT_T))):
            return self._try_split_peaks_for_sextet(peaks)
        return sub, delta, bhf, width, depth

    def _try_split_peaks_for_sextet(self, peaks: list[dict[str, float]]) -> tuple | None:
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
        narrow_tol = max(median_width * 0.5, 0.20)
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
                    if not (10.0 <= bhf_est <= 60.0):
                        continue
                    delta = pk_a["pos"] - scale * LINE_POS_33T[la]
                    pred_all = delta + scale * LINE_POS_33T
                    if max(abs(pk_a["pos"] - pred_all[la]),
                           abs(pk_b["pos"] - pred_all[lb])) > 0.18:
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
                    result = self._best_sextet_from_peaks(augmented)
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

    def _try_2peak_sextet_estimate(
        self, peaks: list[dict[str, float]]
    ) -> tuple[list[dict[str, float]], float, float, float, float] | None:
        if len(peaks) != 2:
            return None
        from core.constants import _BASE_POSITIONS
        p = sorted(peaks, key=lambda x: x["pos"])
        obs_spacing = p[1]["pos"] - p[0]["pos"]
        if obs_spacing < 0.5:
            return None
        spacing_ref = float(_BASE_POSITIONS[1] - _BASE_POSITIONS[0])
        scale = obs_spacing / spacing_ref
        bhf = scale * BHF_DEFAULT_T
        if not (25.0 <= bhf <= 60.0):
            return None
        best: tuple | None = None
        if p[0]["pos"] < 0 and p[1]["pos"] < 0:
            delta_01 = p[0]["pos"] - scale * float(_BASE_POSITIONS[0])
            if abs(delta_01) <= 1.5:
                best = (delta_01, bhf, (3.0, 2.0))
        if p[0]["pos"] > 0 and p[1]["pos"] > 0:
            delta_45 = p[0]["pos"] - scale * float(_BASE_POSITIONS[4])
            if abs(delta_45) <= 1.5:
                best = (delta_45, bhf, (2.0, 3.0))
        if best is None:
            return None
        delta_est, bhf_est, (w0, w1) = best
        width = float(np.mean([p[0]["width"], p[1]["width"]]))
        depth = float(np.median([p[0]["depth"] / w0, p[1]["depth"] / w1]))
        return list(p), delta_est, bhf_est, width, depth

    def _depth_profile_hint(self, peaks: list[dict[str, float]]) -> tuple[str, list[dict[str, float]]] | None:
        if not peaks:
            return None
        by_d = sorted(peaks, key=lambda p: p["smooth_depth"], reverse=True)
        d0 = by_d[0]["smooth_depth"]
        d1 = by_d[1]["smooth_depth"] if len(by_d) > 1 else 0.0
        d2 = by_d[2]["smooth_depth"] if len(by_d) > 2 else 0.0
        if d0 > 2.5 * max(d1, 1e-10) and abs(by_d[0]["pos"]) < 2.5:
            return "Singlete", [by_d[0]]
        if len(by_d) >= 2 and d1 >= 0.40 * d0 and d2 < 0.30 * d0 and len(peaks) <= 4:
            pair = sorted([by_d[0], by_d[1]], key=lambda p: p["pos"])
            sep = abs(pair[1]["pos"] - pair[0]["pos"])
            if 0.18 <= sep <= 5.0:
                return "Doblete", pair
        return None

    def _rescale_minima_depths(self, params: dict[str, float], component_indices: tuple[int, ...]) -> None:
        if self.file.velocity is None or self.file.y_data is None:
            return
        v = self.file.velocity
        baseline = float(params.get("baseline", self.calib.baseline.value()))
        slope = float(params.get("slope", self.calib.slope.value()))
        comps = []
        depth_keys = []
        for idx in component_indices:
            cp = self.components_panels[idx - 1]
            p = f"s{idx}_"
            vals = {name: params.get(p + name, cp.params[name].value()) for name in cp.params}
            params.update({p + name: float(vals[name]) for name in vals})
            comps.append(Component(idx=idx, enabled=True, kind=cp.kind,
                                   intensity_mode=cp.intensity_mode,
                                   quad_treatment=cp.quad_treatment))
            depth_keys.append(p + "depth")
        if not comps:
            return
        baseline_line = baseline + slope * v
        values = {**params, "baseline": baseline, "slope": slope}
        try:
            model = model_from_values(v, values, comps, self.constraints,
                                      absorber_model=self.absorber_model)
        except Exception:
            return
        model_abs = float(np.max(baseline_line - model)) if v.size else 0.0
        data_abs = float(np.max(baseline_line - self.file.y_data)) if v.size else 0.0
        if model_abs > 1e-6 and data_abs > 0.0 and model_abs > data_abs:
            factor = data_abs / model_abs
            for key in depth_keys:
                if key in params:
                    params[key] = float(params[key] * factor)

    def on_init_from_minima(self, show_message: bool = True,
                            peaks_override: list[dict] | None = None,
                            multiplicities: dict[int, int] | None = None) -> bool:
        """Detecta mínimos y configura componentes discretas como en Tk.

        Con ``peaks_override`` se usan los mínimos ya curados por el usuario en
        el editor semi-manual (en vez de la detección automática), y
        ``multiplicities`` indica cuántas contribuciones tiene cada mínimo
        (``{índice_canal: nº}``) para añadir componentes solapadas extra.
        """
        if self.file.velocity is None or self.file.y_data is None:
            return False
        if peaks_override is not None:
            peaks = list(peaks_override)
            _, baseline, slope = self.detect_absorption_minima()
        else:
            peaks, baseline, slope = self.detect_absorption_minima()
        if not peaks:
            if show_message:
                QtWidgets.QMessageBox.information(
                    self, tr("fit.init_from_minima"),
                    tr("msg.auto_minima_none", default="No se detectaron mínimos de absorción."))
            return False

        self.mode_combo.setCurrentIndex(0)
        params: dict[str, float] = {
            "baseline": baseline,
            "slope": float(np.clip(slope, -1e-4, 1e-4)),
        }
        for idx in range(1, MAX_QT_COMPONENTS + 1):
            p = f"s{idx}_"
            params.update({
                p + "delta": 0.0, p + "quad": 0.0, p + "bhf": BHF_DEFAULT_T,
                p + "gamma1": 0.15, p + "gamma2": 1.0, p + "gamma3": 1.0,
                p + "depth": 0.005, p + "int1": 3.0, p + "int2": 2.0, p + "int3": 1.0,
            })

        components: list[tuple[int, str, list[dict[str, float]]]] = []
        used_ids: set[int] = set()

        hint = self._depth_profile_hint(peaks)
        if hint is not None:
            kind_h, group_h = hint
            components.append((1, kind_h, group_h))
            pfx = "s1_"
            if kind_h == "Doblete":
                g = group_h
                params[pfx + "delta"] = float(np.mean([g[0]["pos"], g[1]["pos"]]))
                params[pfx + "quad"] = float(abs(g[1]["pos"] - g[0]["pos"]))
                params[pfx + "gamma1"] = float(np.clip(np.mean([x["width"] for x in g]) / 2.0, 0.04, 1.0))
                params[pfx + "gamma2"] = 1.0
                params[pfx + "depth"] = float(np.clip(np.mean([x["depth"] for x in g]), 0.002, 0.25))
                params[pfx + "int1"] = 1.0
                params[pfx + "int2"] = 1.0
            else:
                pk = group_h[0]
                params[pfx + "delta"] = float(pk["pos"])
                params[pfx + "gamma1"] = float(np.clip(pk["width"] / 2.0, 0.04, 1.0))
                params[pfx + "depth"] = float(np.clip(pk["depth"], 0.002, 0.25))
                params[pfx + "int1"] = 1.0
            used_ids.update(int(pk["i"]) for pk in group_h)
        else:
            sext = self._best_sextet_from_peaks(peaks)
            if sext is not None:
                sub, delta, bhf, width, depth = sext
                if len(sub) >= 5 and abs(sub[-1]["pos"] - sub[0]["pos"]) > 3.0:
                    components.append((1, "Sextete", sub))
                    p = "s1_"
                    params[p + "delta"] = float(np.clip(delta, -2.5, 2.5))
                    params[p + "bhf"] = float(np.clip(bhf, 20.0, 60.0))
                    params[p + "quad"] = 0.0
                    params[p + "gamma1"] = float(np.clip(width / 2.0, 0.04, 1.0))
                    params[p + "depth"] = float(np.clip(depth, 0.002, 0.25))
                    used_ids.update(int(pk["i"]) for pk in sub)

        remaining = [p for p in sorted(peaks, key=lambda q: q["smooth_depth"], reverse=True)
                     if int(p["i"]) not in used_ids]
        next_idx = 2 if components else 1
        while next_idx <= min(3, MAX_QT_COMPONENTS) and remaining:
            if len(remaining) >= 5:
                sext_extra = self._best_sextet_from_peaks(remaining)
                if sext_extra is not None:
                    sub_e, delta_e, bhf_e, width_e, depth_e = sext_extra
                    if len(sub_e) >= 5 and abs(sub_e[-1]["pos"] - sub_e[0]["pos"]) > 3.0:
                        pfx = f"s{next_idx}_"
                        components.append((next_idx, "Sextete", sub_e))
                        params[pfx + "delta"] = float(np.clip(delta_e, -2.5, 2.5))
                        params[pfx + "bhf"] = float(np.clip(bhf_e, 20.0, 60.0))
                        params[pfx + "quad"] = 0.0
                        params[pfx + "gamma1"] = float(np.clip(width_e / 2.0, 0.04, 1.0))
                        params[pfx + "depth"] = float(np.clip(depth_e, 0.002, 0.25))
                        sub_ids = {int(pk["i"]) for pk in sub_e}
                        remaining = [p for p in remaining if int(p["i"]) not in sub_ids]
                        next_idx += 1
                        continue
            two_peak_sext = self._try_2peak_sextet_estimate(remaining) if len(remaining) == 2 else None
            if two_peak_sext is not None:
                sub2, delta2, bhf2, width2, depth2 = two_peak_sext
                pfx = f"s{next_idx}_"
                components.append((next_idx, "Sextete", sub2))
                params[pfx + "delta"] = float(np.clip(delta2, -2.5, 2.5))
                params[pfx + "bhf"] = float(np.clip(bhf2, 20.0, 60.0))
                params[pfx + "quad"] = 0.0
                params[pfx + "gamma1"] = float(np.clip(width2 / 2.0, 0.04, 1.0))
                params[pfx + "depth"] = float(np.clip(depth2, 0.002, 0.25))
                remaining.clear()
                next_idx += 1
                continue
            if len(remaining) >= 2:
                pair = sorted(remaining[:2], key=lambda p: p["pos"])
                sep = abs(pair[1]["pos"] - pair[0]["pos"])
                if 0.18 <= sep <= 4.0:
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
                params[pfx + "gamma1"] = float(np.clip(np.mean([x["width"] for x in g]) / 2.0, 0.04, 1.0))
                params[pfx + "gamma2"] = 1.0
                params[pfx + "depth"] = float(np.clip(np.mean([x["depth"] for x in g]), 0.002, 0.25))
                params[pfx + "int1"] = 1.0
                params[pfx + "int2"] = 1.0
            else:
                g = group[0]
                params[pfx + "delta"] = float(g["pos"])
                params[pfx + "gamma1"] = float(np.clip(g["width"] / 2.0, 0.04, 1.0))
                params[pfx + "depth"] = float(np.clip(g["depth"], 0.002, 0.25))
                params[pfx + "int1"] = 1.0
            next_idx += 1

        if not components:
            g = max(peaks, key=lambda p: p["depth"])
            components.append((1, "Singlete", [g]))
            params["s1_delta"] = float(g["pos"])
            params["s1_gamma1"] = float(np.clip(g["width"] / 2.0, 0.04, 1.0))
            params["s1_depth"] = float(np.clip(g["depth"], 0.002, 0.25))

        # Contribuciones extra señaladas por el usuario: cada mínimo marcado con
        # n>1 añade (n-1) singletes solapados en esa posición, hasta el máximo de
        # componentes, para que el ajuste pueda separar las contribuciones.
        if multiplicities:
            next_extra = max((idx for idx, _k, _g in components), default=0) + 1
            for pk in peaks:
                extra = int(multiplicities.get(int(pk["i"]), 1)) - 1
                for _ in range(max(0, extra)):
                    if next_extra > MAX_QT_COMPONENTS:
                        break
                    pfx = f"s{next_extra}_"
                    components.append((next_extra, "Singlete", [pk]))
                    params[pfx + "delta"] = float(pk["pos"])
                    params[pfx + "gamma1"] = float(np.clip(pk["width"] / 2.0, 0.04, 1.0))
                    params[pfx + "depth"] = float(np.clip(pk["depth"] * 0.5, 0.002, 0.25))
                    params[pfx + "int1"] = 1.0
                    next_extra += 1

        active_count = max(1, max((idx for idx, _kind, _g in components), default=1))
        self._building = True
        try:
            self._sync_component_count(active_count)
            for cp in self.components_panels:
                match = next(((kind, group) for idx, kind, group in components if idx == cp.idx), None)
                cp.enabled.setChecked(match is not None)
                cp.type_combo.setCurrentText(match[0] if match is not None else "Sextete")
                cp.apply_values(params)
                if match is not None:
                    used = ComponentPanel._USED_BY.get(cp.to_view_state().kind, set())
                    for name in used:
                        cp.params[name].set_fixed(False)
            self.calib.baseline.set_value(params["baseline"])
            self.calib.slope.set_value(params["slope"])
            self.calib.baseline.set_fixed(False)
            self.calib.slope.set_fixed(False)
            self._rescale_minima_depths(params, tuple(idx for idx, _kind, _g in components))
            for cp in self.components_panels:
                cp.apply_values(params)
        finally:
            self._building = False

        # Igual que en Tk: tras inicializar desde mínimos se dibuja ya la
        # simulación propuesta (habilita el trazado del modelo).
        self._simulate_enabled = True
        self._refresh_plot()
        summary = ", ".join(
            tr("text.component_kind_label", idx=idx, kind=tr(f"kind.{kind}", default=kind))
            for idx, kind, _g in components
        )
        msg = tr("msg.auto_minima_detected", n=len(peaks), summary=summary)
        self.statusBar().showMessage(f"{tr('msg.auto_minima_title')}: {summary}", 5000)
        if show_message:
            QtWidgets.QMessageBox.information(self, tr("msg.auto_minima_title"), msg)
        return True
