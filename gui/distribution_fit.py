"""Ajuste de distribuciones hiperfinas desde la GUI Qt."""
from __future__ import annotations

import dataclasses
import time
from pathlib import Path

import numpy as np
from PySide6 import QtWidgets
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from scipy.optimize import least_squares

from mossbauer_i18n import tr
from core.constants import APP_VERSION, BHF_DEFAULT_T, SEXTET_PARAM_NAMES
from core.physics import component_absorption
from core.plot_styles import get_style
from core.reconstruction import reconstruct_distribution_curves
from core.validation import format_validation_issues, validate_distribution_parameters
from core.param_overrides import effective_fit_init_specs as _eff_fi, effective_distribution_specs as _eff_ds
from core.params import CZJZEK_SHAPES, is_2d_shape
from gui.fit_workflow import GuiFitRenderState, GuiFitResult
from mossbauer_distribution import (
    fit_hyperfine_distribution,
    fit_vbf_hyperfine_distribution,
    fit_binomial_hyperfine_distribution,
    fit_czjzek_hyperfine_distribution,
    fit_fixed_hyperfine_distribution,
    fit_bhf_quad_distribution,
    fit_vbf_2d_distribution,
    correlation_curve,
    global_parameter_covariance,
)

ROOT = Path(__file__).resolve().parents[1]

#: Réplicas del Monte Carlo paramétrico de la banda 1σ de P (Histograma):
#: ~0.05 s con Tikhonov y ~0.5 s con TV; error relativo de σ ≈ 7 %.
DIST_BAND_REPLICAS = 100


def _lcurve_corner_index(rough: np.ndarray, resid_norm: np.ndarray) -> int:
    """Índice de la esquina de la L-curve (criterio de máxima curvatura, Hansen).

    Trabaja en escala log-log: la esquina es el punto de máxima curvatura de la
    curva paramétrica (rugosidad ``‖Lw‖``  vs  residuo ``‖Kw−y‖``), es decir el
    mejor compromiso entre ajuste y suavidad. Devuelve 0 si no puede estimarse
    (curva demasiado corta o no positiva).
    """
    rough = np.asarray(rough, dtype=float)
    resid_norm = np.asarray(resid_norm, dtype=float)
    n = rough.size
    if n < 3 or resid_norm.size != n:
        return 0
    # Solo puntos positivos y finitos: el log exige valores > 0.
    valid = np.isfinite(rough) & np.isfinite(resid_norm) & (rough > 0) & (resid_norm > 0)
    if valid.sum() < 3:
        return 0
    idx_valid = np.flatnonzero(valid)
    x = np.log(rough[idx_valid])
    y = np.log(resid_norm[idx_valid])
    m = x.size
    # Curvatura de Menger sobre tríos consecutivos (sin signo): en las ramas
    # rectas de la L vale ~0 y se dispara en la esquina. Robusta frente al
    # sentido de recorrido (a diferencia de la curvatura con signo).
    best_local, best_curv = m // 2, -1.0
    for i in range(1, m - 1):
        ax, ay = x[i - 1], y[i - 1]
        bx, by = x[i], y[i]
        cx, cy = x[i + 1], y[i + 1]
        area2 = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))
        d_ab = np.hypot(bx - ax, by - ay)
        d_bc = np.hypot(cx - bx, cy - by)
        d_ca = np.hypot(ax - cx, ay - cy)
        denom = d_ab * d_bc * d_ca
        if denom <= 0:
            continue
        curv = 2.0 * area2 / denom          # = 1 / radio del círculo circunscrito
        if curv > best_curv:
            best_curv, best_local = curv, i
    return int(idx_valid[best_local])


def _lcurve_pick_index(axis: str, x, y, rough, resid_norm, alphas) -> int:
    """Índice del punto escaneado más cercano a un clic en la L-curve.

    ``axis="lcurve"`` mide la distancia en el plano log-log ``(rough, resid_norm)``
    (la propia L); ``axis="alpha"`` mide la distancia en ``log10(α)`` (la gráfica
    α↔RMS). Permite que el usuario elija α pinchando la figura cuando la esquina
    automática no acierta. Devuelve 0 si no hay puntos o el clic no es válido.
    """
    alphas = np.asarray(alphas, dtype=float)
    if alphas.size == 0 or x is None:
        return 0
    if axis == "lcurve" and y is not None:
        lr = np.log10(np.maximum(np.asarray(rough, dtype=float), 1e-30))
        ly = np.log10(np.maximum(np.asarray(resid_norm, dtype=float), 1e-30))
        d2 = (lr - np.log10(max(float(x), 1e-30))) ** 2 + \
             (ly - np.log10(max(float(y), 1e-30))) ** 2
        return int(np.argmin(d2))
    la = np.log10(np.maximum(alphas, 1e-30))
    return int(np.argmin(np.abs(la - np.log10(max(float(x), 1e-30)))))


def _couple_lcurve_zoom(cv, ax1, ax2, rough, resid_norm, alphas, rms) -> None:
    """Acopla el zoom de las dos figuras de la L-curve por el rango de α.

    Ambas figuras (izq: ``rough`` vs ``resid_norm``; der: ``alphas`` vs ``rms``)
    están parametrizadas por el mismo barrido, punto a punto. Al hacer zoom en una,
    la otra se limita a los puntos del mismo rango de α (selección por pertenencia,
    robusta aunque ``rough`` no sea monótona en α). Un cerrojo de reentrada evita el
    bucle infinito entre ambos callbacks.
    """
    rough = np.asarray(rough, dtype=float)
    resid_norm = np.asarray(resid_norm, dtype=float)
    alphas = np.asarray(alphas, dtype=float)
    rms = np.asarray(rms, dtype=float)
    if alphas.size < 2:
        return
    sync = {"busy": False}

    def _pad_log(lo: float, hi: float):
        lo, hi = float(min(lo, hi)), float(max(lo, hi))
        if lo <= 0 or hi <= 0:
            return None
        if lo == hi:
            return lo / 1.5, hi * 1.5
        return lo / 1.05, hi * 1.05

    def _apply(ax, xs, ys) -> None:
        rx = _pad_log(float(np.min(xs)), float(np.max(xs)))
        ry = _pad_log(float(np.min(ys)), float(np.max(ys)))
        if rx:
            ax.set_xlim(*rx)
        if ry:
            ax.set_ylim(*ry)

    def _couple(src_ax, src_vals, dst_ax, dst_x, dst_y) -> None:
        if sync["busy"]:
            return
        lo, hi = sorted(src_ax.get_xlim())
        mask = (src_vals >= lo) & (src_vals <= hi)
        if not mask.any():
            return
        sync["busy"] = True
        try:
            _apply(dst_ax, dst_x[mask], dst_y[mask])
        finally:
            sync["busy"] = False
        cv.draw_idle()

    ax1.callbacks.connect(
        "xlim_changed", lambda _ax: _couple(ax1, rough, ax2, alphas, rms))
    ax2.callbacks.connect(
        "xlim_changed", lambda _ax: _couple(ax2, alphas, ax1, rough, resid_norm))


class DistributionFitMixin:
    def _active_sharp_components_for_distribution(self) -> tuple[list[dict[str, float]] | None, list[int]]:
        if not self.dist_use_sharp:
            return None, []
        components: list[dict[str, float]] = []
        indices: list[int] = []
        for cp in self.components_panels:
            comp_state = cp.to_view_state()
            if not comp_state.enabled:
                continue
            int1_gui = comp_state.value("int1", 1.0)
            int2_gui = comp_state.value("int2", 1.0)
            int3_gui = comp_state.value("int3", 1.0)
            # Todos los tipos magnéticos de 6 líneas usan la convención relativa
            # del engine (int2_rel=1 → I2=(2/3)·I1): la conversión desde los
            # widgets (convención core [I3·I1, I3·I2, I3]) aplica igual a
            # Sextete, Relajación, Blume-Tjon y Néel — antes solo se convertía
            # Sextete y el resto se ajustaba con un patrón de líneas erróneo.
            if comp_state.kind in ("Sextete", "Relajacion", "BlumeTjon", "NeelSize"):
                engine_int1 = int3_gui * int1_gui
                if abs(int1_gui) > 1e-12:
                    engine_int2_rel = 1.5 * int2_gui / int1_gui
                    engine_int3_rel = 3.0 / int1_gui
                else:
                    engine_int2_rel = 0.0
                    engine_int3_rel = 0.0
            else:
                engine_int1 = int1_gui
                engine_int2_rel = int2_gui
                engine_int3_rel = int3_gui
            comp: dict = {
                "kind": comp_state.kind,
                "delta": comp_state.value("delta", 0.0),
                "quad": comp_state.value("quad", 0.0),
                "bhf": comp_state.value("bhf", 33.0),
                "gamma": comp_state.value("gamma1", 0.36),
                "gamma2_rel": comp_state.value("gamma2", 1.0),
                "gamma3_rel": comp_state.value("gamma3", 1.0),
                "int1": engine_int1,
                "int2_rel": engine_int2_rel,
                "int3_rel": engine_int3_rel,
                "depth": comp_state.value("depth", 0.0),
                "depth_fixed": comp_state.is_fixed("depth"),
            }
            # Parámetros de relajación/Néel para los nuevos tipos de componente
            if comp_state.kind == "Relajacion":
                comp["relax_fraction"] = comp_state.value("relax_fraction", 1.0)
                comp["relax_log_nu"] = comp_state.value("relax_log_nu", 5.0)
            elif comp_state.kind == "BlumeTjon":
                comp["relax_log_nu"] = comp_state.value("relax_log_nu", 5.0)
            elif comp_state.kind == "NeelSize":
                for _p in ("neel_temp_k", "neel_log10_keff", "neel_mean_d_nm",
                           "neel_sigma", "neel_log10_tau0", "neel_bins"):
                    comp[_p] = comp_state.value(_p, 0.0)
            components.append(comp)
            indices.append(comp_state.idx)
        return (components or None), indices

    # ── L-curve α scanner (modo distribución) ────────────────────────────
    def on_lcurve(self) -> None:
        if not self.is_distribution_mode:
            QtWidgets.QMessageBox.information(
                self, tr("bhf.lcurve_alpha"),
                tr("bhf.lcurve_only_distribution"))
            return
        if self.file.velocity is None or self.file.y_data is None:
            return
        d = self.dist_panel
        # α/L-curve solo tienen sentido en el histograma regularizado.
        if d.shape != "Histograma":
            QtWidgets.QMessageBox.information(
                self, tr("bhf.lcurve_alpha"),
                tr("bhf.lcurve_only_histogram",
                   default="La L-curve solo aplica a la forma Histograma "
                           "(Gaussiana/Binomial son paramétricas y no usan α)."))
            return
        var = self.dist_variable
        dist_state = d.to_view_state(variable=var)
        _fi = _eff_fi()
        alphas = np.logspace(_fi["lcurve_alpha_lo"].default, _fi["lcurve_alpha_hi"].default, int(_fi["lcurve_n_points"].default))
        self.statusBar().showMessage(tr("status.scanning_alpha", n=len(alphas)))
        QtWidgets.QApplication.processEvents()
        bmin = float(dist_state.bmin); bmax = max(bmin + 0.5, float(dist_state.bmax))
        nbins = max(5, int(dist_state.nbins))
        sharp_components, _sharp_indices = self._active_sharp_components_for_distribution()
        calib_state = self.calib.to_view_state()
        fit_baseline = not calib_state.is_fixed("baseline")
        fit_slope = not calib_state.is_fixed("slope")
        try:
            common = dict(
                delta=dist_state.delta, gamma=dist_state.gamma,
                fit_baseline=fit_baseline, fit_slope=fit_slope,
                baseline=calib_state.baseline, slope=calib_state.slope,
                pmin=bmin, pmax=bmax, nbins=nbins, sigma=self.file.sigma,
                sharp_components=sharp_components,
                profile=calib_state.line_profile, voigt_sigma=calib_state.voigt_sigma,
                delta_slope=dist_state.delta_slope, quad_slope=dist_state.quad_slope,
                kernel_treatment=dist_state.kernel_treatment,
                kernel_eta=dist_state.kernel_eta,
                source_bhf=dist_state.source_bhf,
                source_theta=dist_state.source_theta,
                absorber_theta=dist_state.absorber_theta,
            )
            if var == "quad":
                extra = dict(variable="quad", bhf=dist_state.kernel_bhf)
            elif var == "delta":
                # P(IS): sin esta rama el escaneo caía a variable="bhf" con la
                # malla de IS interpretada como teslas.
                extra = dict(variable="delta", quad=dist_state.quad,
                             bhf=dist_state.kernel_bhf)
            else:
                extra = dict(variable="bhf", quad=dist_state.quad)
            fits = [fit_hyperfine_distribution(
                self.file.velocity, self.file.y_data, alpha=float(a),
                reg_mode=dist_state.reg_mode, **extra, **common) for a in alphas]
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, tr("bhf.lcurve_alpha"),
                                            f"{type(exc).__name__}: {exc}")
            return
        # Diálogo: residuo² vs rugosidad
        resid_norm = np.array([float(np.linalg.norm(f.residuals)) for f in fits])
        rough = np.array([float(np.linalg.norm(np.diff(f.weights, 2)))
                          if f.weights.size > 2 else 0.0 for f in fits])
        rms = np.array([f.rms for f in fits])
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(tr("bhf.lcurve_alpha"))
        dlg.resize(820, 540)
        v = QtWidgets.QVBoxLayout(dlg)
        fig = Figure(figsize=(8.0, 5.0), dpi=96, constrained_layout=True)
        cv = FigureCanvas(fig); v.addWidget(cv, stretch=1)
        # Esquina de la L (máxima curvatura) = sugerencia de compromiso ajuste/suavidad.
        best_idx = _lcurve_corner_index(rough, resid_norm) if alphas.size else 0
        # Selección actual (arranca en la esquina automática; el usuario la corrige
        # pinchando sobre la figura).
        sel = {"idx": int(best_idx)}
        ax1 = fig.add_subplot(1, 2, 1)
        ax1.loglog(rough, resid_norm, "o-", color="#2563eb", ms=4, picker=False)
        for i, a in enumerate(alphas):
            ax1.annotate(f"{np.log10(a):+.1f}", (rough[i], resid_norm[i]),
                          fontsize=6, alpha=0.7)
        sel_pt1 = None
        if alphas.size:
            ax1.plot(rough[best_idx], resid_norm[best_idx], "o", ms=13,
                     mfc="none", mec="#16a34a", mew=2.0, zorder=5,
                     label=tr("plot.lcurve_corner", default="esquina (auto)"))
            sel_pt1, = ax1.plot([rough[best_idx]], [resid_norm[best_idx]], "o",
                                ms=11, mfc="#f97316", mec="#7c2d12", mew=1.6, zorder=6,
                                label=tr("plot.lcurve_selected", default="α elegido"))
            ax1.legend(loc="best", fontsize=7)
        ax1.set_xlabel(tr("plot.lcurve_xlabel"))
        ax1.set_ylabel(tr("plot.lcurve_ylabel"))
        ax1.set_title(tr("plot.lcurve_title"))
        ax1.grid(True, alpha=0.3, which="both")
        ax2 = fig.add_subplot(1, 2, 2)
        ax2.semilogx(alphas, rms, "o-", color="#ef4444", ms=4, picker=False)
        sel_line2 = None
        if alphas.size:
            ax2.axvline(float(alphas[best_idx]), color="#16a34a", ls="--", lw=1.2)
            sel_line2 = ax2.axvline(float(alphas[best_idx]), color="#f97316",
                                    ls="-", lw=1.6, zorder=6)
        ax2.set_xlabel("α")
        ax2.set_ylabel(tr("plot.label_rms"))
        ax2.set_title(tr("plot.alpha_scan_title"))
        ax2.grid(True, alpha=0.3, which="both")
        cv.draw_idle()

        # Barra de herramientas (zoom/pan/reset) que actúa sobre ambas figuras.
        toolbar = NavigationToolbar(cv, dlg)
        v.addWidget(toolbar)

        # Zoom acoplado por α entre ambas figuras.
        _couple_lcurve_zoom(cv, ax1, ax2, rough, resid_norm, alphas, rms)

        # Etiqueta + botón (se actualizan al elegir un punto en la figura).
        hint = QtWidgets.QLabel(tr(
            "plot.lcurve_pick_hint",
            default="Haz clic en un punto de cualquiera de las dos figuras para "
                    "elegir α (se ajusta al valor escaneado más cercano)."))
        hint.setStyleSheet("color:#64748b;font-size:11px;")
        v.addWidget(hint)
        buttons = QtWidgets.QHBoxLayout()
        btn_use = QtWidgets.QPushButton("")
        buttons.addWidget(btn_use); buttons.addStretch(1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); buttons.addWidget(bb)
        v.addLayout(buttons)

        def _update_selection() -> None:
            if not alphas.size:
                btn_use.setText(tr("button.use_lcurve", default="Usar α={value}",
                                   value=f"{float(dist_state.alpha):.3g}"))
                return
            i = int(sel["idx"])
            a = float(alphas[i])
            if sel_pt1 is not None:
                sel_pt1.set_data([rough[i]], [resid_norm[i]])
            if sel_line2 is not None:
                sel_line2.set_xdata([a, a])
            btn_use.setText(tr("button.use_lcurve", default="Usar α={value}",
                               value=f"{a:.3g}  (log₁₀={np.log10(a):+.2f})"))
            cv.draw_idle()

        def _on_pick(event) -> None:
            # No seleccionar mientras el zoom/pan de la toolbar está activo.
            if getattr(toolbar, "mode", ""):
                return
            if not alphas.size or event.xdata is None:
                return
            if event.inaxes is ax1 and event.ydata is not None:
                sel["idx"] = _lcurve_pick_index(
                    "lcurve", event.xdata, event.ydata, rough, resid_norm, alphas)
            elif event.inaxes is ax2:
                sel["idx"] = _lcurve_pick_index(
                    "alpha", event.xdata, None, rough, resid_norm, alphas)
            else:
                return
            _update_selection()

        cv.mpl_connect("button_press_event", _on_pick)
        btn_use.clicked.connect(
            lambda _=False: (
                d.log_alpha.set_value(float(np.log10(float(alphas[int(sel["idx"])]))))
                if alphas.size else None, dlg.accept()))
        _update_selection()
        dlg.exec()



    def _load_fixed_distribution(self, path: Path) -> tuple[np.ndarray, np.ndarray]:
        """Lee dos columnas (centers, weights) de un .txt/.dat/.csv."""
        raw = Path(path).read_text(encoding="utf-8", errors="replace").strip().splitlines()
        c, w = [], []
        for line in raw:
            line = line.strip()
            if not line or line.startswith(("#", "//")):
                continue
            parts = line.replace(",", " ").replace(";", " ").split()
            if len(parts) < 2:
                continue
            try:
                c.append(float(parts[0])); w.append(float(parts[1]))
            except ValueError:
                continue
        return np.array(c, dtype=float), np.array(w, dtype=float)

    def _on_load_fixed_distribution(self) -> None:
        """Carga una distribución P fija desde fichero (dos columnas)."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, tr("bhf.load_fixed"), str(ROOT),
            f"{tr('filter.text')} (*.txt *.dat *.csv *.tsv);;{tr('filter.all')} (*.*)")
        if not path:
            return
        self.dist_panel.fixed_path = Path(path)
        self.statusBar().showMessage(tr("status.fixed_p_loaded", path=path), 5000)

    # ── Ajuste distribución P(BHF) / P(ΔEQ) / P(IS) / 2D ───────────────────
    def on_fit_distribution(self) -> None:
        self._simulate_enabled = True
        if self.file.velocity is None or self.file.y_data is None:
            return
        d = self.dist_panel
        var = self.dist_variable
        dist_state = d.to_view_state(variable=var)
        issues = validate_distribution_parameters(dist_state)
        if issues:
            QtWidgets.QMessageBox.warning(
                self,
                tr("msg.validation_title", default="Parámetros no válidos"),
                format_validation_issues(issues),
            )
            return

        bmin = float(dist_state.bmin)
        bmax = max(bmin + 0.5, float(dist_state.bmax))
        nbins = max(5, int(dist_state.nbins))
        alpha = dist_state.alpha
        shape = dist_state.shape
        is_2d = is_2d_shape(shape)

        # Parámetros 2D (disponibles tras la actualización del panel)
        _ds = _eff_ds()
        qmin: float = float(d.qmin.value()) if hasattr(d, "qmin") else _ds["qmin"].default
        qmax: float = max(qmin + 0.05, float(d.qmax.value())) if hasattr(d, "qmax") else _ds["qmax"].default
        qbins: int = max(5, int(round(d.qbins.value()))) if hasattr(d, "qbins") else int(_ds["qbins"].default)
        alpha_q: float = 10.0 ** float(d.log_alpha_q.value()) if hasattr(d, "log_alpha_q") else 10.0 ** _ds["log_alpha_q"].default
        pair: tuple[str, str] = getattr(self, "dist_pair", ("bhf", "quad")) if is_2d else ("bhf", "quad")

        label_map = {"bhf": "BHF", "quad": "ΔEQ", "delta": "IS"}
        label = (f"P({label_map.get(pair[0], pair[0])}, {label_map.get(pair[1], pair[1])})"
                 if is_2d else f"P({label_map.get(var, var)})")

        self.statusBar().showMessage(tr("status.fitting_distribution", label=label, shape=shape))
        sharp_components, sharp_indices = self._active_sharp_components_for_distribution()
        calib_state = self.calib.to_view_state()
        fit_baseline = not calib_state.is_fixed("baseline")
        fit_slope = not calib_state.is_fixed("slope")
        base_delta = dist_state.delta
        base_quad = dist_state.quad
        base_gamma = dist_state.gamma
        base_delta_slope = dist_state.delta_slope
        base_quad_slope = dist_state.quad_slope
        v_arr = self.file.velocity
        y_arr = self.file.y_data

        vbf2d_seed: dict = {}
        # Sondeo de «Cancelar» durante el ajuste no lineal 2D (cada evaluación
        # puede tardar segundos); se conecta al diálogo en compute_distribution.
        cancel_poll: dict = {"fn": None, "last": 0.0}

        def poll_cancel() -> None:
            fn = cancel_poll["fn"]
            now = time.monotonic()
            if fn is not None and now - float(cancel_poll["last"]) > 0.1:
                cancel_poll["last"] = now
                fn(None)

        def run_fit(delta_value: float, quad_value: float, gamma_value: float,
                    sharp_for_fit: list[dict] | None,
                    delta_slope_value: float | None = None,
                    quad_slope_value: float | None = None,
                    final: bool = True):
            dsl = base_delta_slope if delta_slope_value is None else delta_slope_value
            qsl = base_quad_slope if quad_slope_value is None else quad_slope_value
            if shape in ("Gaussiana 2D", "VBF 2D"):
                # Gaussianas bivariantes sobre la misma malla; sin α. La primera
                # evaluación prueba varios arranques y las demás parten de su
                # solución (fija: el residuo sigue siendo función solo de x).
                res2d = fit_vbf_2d_distribution(
                    v_arr, y_arr,
                    n_components=(1 if shape == "Gaussiana 2D" else dist_state.vbf_n_components),
                    variable_x=pair[0], variable_y=pair[1],
                    delta=delta_value, quad=quad_value,
                    bhf=(dist_state.kernel_bhf if "bhf" not in pair else BHF_DEFAULT_T),
                    gamma=gamma_value,
                    bmin=bmin, bmax=bmax, nbins_bhf=nbins,
                    qmin=qmin, qmax=qmax, nbins_quad=qbins,
                    fit_baseline=fit_baseline, fit_slope=fit_slope,
                    baseline=calib_state.baseline, slope=calib_state.slope,
                    sharp_components=sharp_for_fit,
                    sigma=self.file.sigma,
                    profile=calib_state.line_profile, voigt_sigma=calib_state.voigt_sigma,
                    shape=shape,
                    initial_components=vbf2d_seed.get("comps"),
                    # δ/ΔEQ/Γ libres van dentro del ajuste no lineal (no en
                    # el bucle externo: ver fit_vbf_2d_distribution).
                    fit_delta=not dist_state.is_fixed("delta"),
                    fit_quad=not dist_state.is_fixed("quad"),
                    fit_gamma=not dist_state.is_fixed("gamma"),
                    delta_bounds=(d.delta._lo, d.delta._hi),
                    quad_bounds=(d.quad._lo, d.quad._hi),
                    gamma_bounds=(d.gamma._lo, d.gamma._hi),
                    sigma_x_min=dist_state.vbf_sigma_min,
                    sigma_x_max=dist_state.vbf_sigma_max,
                    sigma_y_min=dist_state.vbf_sigma_min_y,
                    sigma_y_max=dist_state.vbf_sigma_max_y,
                    progress=poll_cancel,
                )
                vbf2d_seed.setdefault("comps", res2d.vbf2d_components)
                return res2d
            if shape == "2D":
                return fit_bhf_quad_distribution(
                    v_arr, y_arr,
                    variable_x=pair[0], variable_y=pair[1],
                    delta=delta_value, quad=quad_value,
                    bhf=(dist_state.kernel_bhf if "bhf" not in pair else BHF_DEFAULT_T),
                    gamma=gamma_value,
                    bmin=bmin, bmax=bmax, nbins_bhf=nbins,
                    qmin=qmin, qmax=qmax, nbins_quad=qbins,
                    alpha_bhf=alpha, alpha_quad=alpha_q,
                    fit_baseline=fit_baseline, fit_slope=fit_slope,
                    baseline=calib_state.baseline, slope=calib_state.slope,
                    sharp_components=sharp_for_fit,
                    sigma=self.file.sigma,
                    profile=calib_state.line_profile, voigt_sigma=calib_state.voigt_sigma,
                    # Diagnóstico caro: solo en el ajuste que se muestra.
                    compute_effective_dof=final,
                )
            # fit_baseline/fit_slope van en common: TODAS las formas respetan el
            # fijado de baseline/slope del panel (antes solo Histograma y 2D).
            common = dict(
                variable=var, delta=delta_value, gamma=gamma_value,
                quad=(0.0 if var == "quad" else quad_value),
                bhf=(dist_state.kernel_bhf if var in ("quad", "delta") else BHF_DEFAULT_T),
                baseline=calib_state.baseline, slope=calib_state.slope,
                fit_baseline=fit_baseline, fit_slope=fit_slope,
                sharp_components=sharp_for_fit,
            )
            if shape == "Histograma":
                return fit_hyperfine_distribution(
                    v_arr, y_arr, pmin=bmin, pmax=bmax, nbins=nbins, alpha=alpha,
                    sigma=self.file.sigma, reg_mode=dist_state.reg_mode,
                    profile=calib_state.line_profile, voigt_sigma=calib_state.voigt_sigma,
                    delta_slope=dsl, quad_slope=qsl,
                    kernel_treatment=dist_state.kernel_treatment,
                    kernel_eta=dist_state.kernel_eta,
                    source_bhf=dist_state.source_bhf,
                    source_theta=dist_state.source_theta,
                    absorber_theta=dist_state.absorber_theta,
                    # Banda 1σ de P por Monte Carlo (respeta P ≥ 0): solo en el
                    # ajuste que se muestra, no en cada evaluación externa.
                    band_replicas=DIST_BAND_REPLICAS if final else 0,
                    **common)
            if shape == "VBF":
                return fit_vbf_hyperfine_distribution(
                    v_arr, y_arr, pmin=bmin, pmax=bmax, nbins=nbins,
                    n_components=dist_state.vbf_n_components,
                    profile=calib_state.line_profile, voigt_sigma=calib_state.voigt_sigma,
                    delta_slope=dsl, quad_slope=qsl,
                    sigma_min=dist_state.vbf_sigma_min,
                    sigma_max=dist_state.vbf_sigma_max,
                    **common)
            if shape == "Gaussiana":
                # "Gaussiana" = VBF con una sola gaussiana y línea Lorentziana (el
                # caso clásico). Se conserva la etiqueta shape="Gaussiana" en el
                # resultado para sesiones/informes; VBF es su generalización a N>1,
                # perfil Voigt y correlación δ(H)/ΔEQ(H).
                return fit_vbf_hyperfine_distribution(
                    v_arr, y_arr, pmin=bmin, pmax=bmax, nbins=nbins,
                    n_components=1, profile="Lorentz", shape="Gaussiana",
                    sigma_min=dist_state.vbf_sigma_min,
                    sigma_max=dist_state.vbf_sigma_max,
                    **common)
            if shape in CZJZEK_SHAPES:
                # |ΔEQ| de un gradiente de campo aleatorio (Czjzek) o aleatorio
                # sobre uno ordenado (extendido): paramétrica, con σ de datos.
                return fit_czjzek_hyperfine_distribution(
                    v_arr, y_arr, pmin=bmin, pmax=bmax, nbins=nbins,
                    extended=(shape == "Czjzek ext."),
                    profile=calib_state.line_profile, voigt_sigma=calib_state.voigt_sigma,
                    delta_slope=dsl, quad_slope=qsl, sigma=self.file.sigma,
                    **common)
            if shape == "Binomial":
                # Vecinos al estilo NORMOS (DISTRI=3): la malla no se usa; la
                # concentración es dato salvo que se desmarque su «Fijo».
                return fit_binomial_hyperfine_distribution(
                    v_arr, y_arr,
                    conc=dist_state.binom_conc / 100.0,
                    fit_conc=not dist_state.fixed.get("binom_conc", True),
                    n_neighbors=dist_state.binom_neighbors,
                    start=dist_state.binom_start, step=dist_state.binom_step,
                    fit_start=not dist_state.is_fixed("binom_start"),
                    fit_step=not dist_state.is_fixed("binom_step"),
                    delta_slope=dsl, quad_slope=qsl,
                    profile=calib_state.line_profile, voigt_sigma=calib_state.voigt_sigma,
                    **common)
            if shape == "Fija":
                if dist_state.fixed_distribution_path is None:
                    raise RuntimeError(tr("msg.fixed_p_missing"))
                centers_arr, weights_arr = self._load_fixed_distribution(dist_state.fixed_distribution_path)
                return fit_fixed_hyperfine_distribution(
                    v_arr, y_arr, centers_arr, weights_arr,
                    profile=calib_state.line_profile, voigt_sigma=calib_state.voigt_sigma,
                    **common)
            raise RuntimeError(f"Forma desconocida: {shape}")

        # outer_specs: parámetros globales libres a refinar en la capa exterior
        outer_specs: list[tuple[str, str, float, float]] = []
        # Gaussiana/VBF 2D ajustan δ/ΔEQ/Γ dentro del propio ajuste.
        # Variables distribuidas: no son globales a refinar. (En 2D antes se
        # miraba la variable 1D, «bhf», y un δ libre se refinaba aunque IS
        # fuera un eje del mapa.)
        dist_vars = pair if is_2d else (var,)
        globals_inside = shape in ("Gaussiana 2D", "VBF 2D")
        if not globals_inside:
            if "delta" not in dist_vars and not dist_state.is_fixed("delta"):
                outer_specs.append(("dist_delta", "lin", d.delta._lo, d.delta._hi))
            if "quad" not in dist_vars and not dist_state.is_fixed("quad"):
                outer_specs.append(("dist_quad", "lin", d.quad._lo, d.quad._hi))
            if not dist_state.is_fixed("gamma"):
                outer_specs.append(("dist_gamma", "loggamma", d.gamma._lo, d.gamma._hi))
        # Nivel (b): refinar las pendientes de correlación δ(H)/ΔEQ(H) en la capa
        # externa (son no lineales). Solo con Histograma/VBF y si no están fijas.
        # Solo las pendientes que tienen sentido con la variable (las visibles):
        # P(BHF) ambas, P(ΔEQ) solo δ(ΔEQ), P(IS) solo ΔEQ(δ); en 2D ninguna.
        if shape in ("Histograma", "VBF", "Binomial", *CZJZEK_SHAPES):
            if not dist_state.is_fixed("delta_slope") and var in ("bhf", "quad"):
                outer_specs.append(("dist_delta_slope", "lin", d.delta_slope._lo, d.delta_slope._hi))
            if not dist_state.is_fixed("quad_slope") and var in ("bhf", "delta"):
                outer_specs.append(("dist_quad_slope", "lin", d.quad_slope._lo, d.quad_slope._hi))
        if sharp_components:
            for pos, idx in enumerate(sharp_indices):
                cp = self.components_panels[idx - 1]
                comp_state = cp.to_view_state()
                sharp_names = ["delta", "quad", "bhf", "gamma1"]
                if comp_state.kind == "Relajacion":
                    sharp_names.extend(("relax_fraction", "relax_log_nu"))
                elif comp_state.kind == "BlumeTjon":
                    sharp_names.append("relax_log_nu")
                elif comp_state.kind == "NeelSize":
                    sharp_names.extend(("neel_temp_k", "neel_log10_keff", "neel_mean_d_nm",
                                        "neel_sigma", "neel_log10_tau0", "neel_bins"))
                for pname in sharp_names:
                    if pname == "quad" and comp_state.kind == "Singlete":
                        continue
                    if pname == "bhf" and comp_state.kind not in (
                            "Sextete", "Relajacion", "BlumeTjon", "NeelSize"):
                        continue
                    ctl = cp.params.get(pname)
                    if ctl is None or comp_state.is_fixed(pname):
                        continue
                    outer_specs.append((f"sharp:{pos}:{pname}",
                                        "loggamma" if pname == "gamma1" else "lin",
                                        ctl._lo, ctl._hi))

        # Tope de evaluaciones del ajuste interno, contando también las de la
        # jacobiana por diferencias finitas (``max_nfev`` de least_squares no
        # las cuenta: con varios nítidos se hacían 60·(n+1) ajustes y la barra
        # se quedaba en 60/60). Al agotarlo se usa el mejor punto evaluado.
        max_outer_evals = 25 * (len(outer_specs) + 1)
        progress_state: dict = {"eval": 0, "best_rms": np.inf, "last_update": 0.0,
                                "best_cost": np.inf, "best_x": None}
        # Jacobiana y residuos del bucle externo en el óptimo: dan la
        # covarianza de δ/ΔEQ/pendientes (banda de la curva de correlación).
        outer_opt: dict = {}

        class _OuterBudgetExhausted(Exception):
            pass

        def x0_bounds() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            x0, lo, hi = [], [], []
            for key, kind, lo_v, hi_v in outer_specs:
                if key == "dist_delta":
                    cur = base_delta
                elif key == "dist_quad":
                    cur = base_quad
                elif key == "dist_gamma":
                    cur = base_gamma
                elif key == "dist_delta_slope":
                    cur = base_delta_slope
                elif key == "dist_quad_slope":
                    cur = base_quad_slope
                else:
                    _sharp, pos_txt, pname = key.split(":")
                    cur = float(sharp_components[int(pos_txt)]["gamma" if pname == "gamma1" else pname])
                if kind == "loggamma":
                    x0.append(np.log(max(cur, lo_v))); lo.append(np.log(lo_v)); hi.append(np.log(hi_v))
                else:
                    x0.append(cur); lo.append(lo_v); hi.append(hi_v)
            return np.array(x0, dtype=float), np.array(lo, dtype=float), np.array(hi, dtype=float)

        def expand(x: np.ndarray):
            delta_value = base_delta
            quad_value = base_quad
            gamma_value = base_gamma
            delta_slope_value = base_delta_slope
            quad_slope_value = base_quad_slope
            local_sharp = [dict(c) for c in sharp_components] if sharp_components else None
            for i, (key, kind, _lo, _hi) in enumerate(outer_specs):
                value = float(np.exp(x[i])) if kind == "loggamma" else float(x[i])
                if key == "dist_delta":
                    delta_value = value
                elif key == "dist_quad":
                    quad_value = value
                elif key == "dist_gamma":
                    gamma_value = value
                elif key == "dist_delta_slope":
                    delta_slope_value = value
                elif key == "dist_quad_slope":
                    quad_slope_value = value
                elif local_sharp is not None:
                    _sharp, pos_txt, pname = key.split(":")
                    local_sharp[int(pos_txt)]["gamma" if pname == "gamma1" else pname] = value
            return (delta_value, quad_value, gamma_value, local_sharp,
                    delta_slope_value, quad_slope_value)

        def compute_distribution(update_progress):
            cancel_poll["fn"] = update_progress
            fitted_x_local = None
            if outer_specs:
                update_progress(tr("progress.distribution_refine",
                                   default="Refinando parámetros globales libres…"))
                x0, lo, hi = x0_bounds()
                x0 = np.clip(x0, lo, hi)

                def residual_outer(x: np.ndarray) -> np.ndarray:
                    if int(progress_state["eval"]) >= max_outer_evals:
                        raise _OuterBudgetExhausted()
                    dd, qq, gg, ss, dsl, qsl = expand(x)
                    fit = run_fit(dd, qq, gg, ss, dsl, qsl, final=False)
                    resid = fit.residuals
                    rms = float(np.sqrt(np.mean(resid * resid))) if resid.size else float("nan")
                    progress_state["eval"] = int(progress_state["eval"]) + 1
                    if np.isfinite(rms):
                        progress_state["best_rms"] = min(float(progress_state["best_rms"]), rms)
                        cost = float(np.dot(resid, resid))
                        if cost < float(progress_state["best_cost"]):
                            progress_state["best_cost"] = cost
                            progress_state["best_x"] = np.array(x, dtype=float)
                    now = time.monotonic()
                    if (progress_state["eval"] == 1
                            or now - float(progress_state["last_update"]) > 0.20):
                        progress_state["last_update"] = now
                        update_progress({
                            "phase": tr("progress.distribution_refine",
                                        default="Refinando parámetros globales libres…"),
                            "iteration": int(progress_state["eval"]),
                            "max_iter": max_outer_evals,
                            "rms": rms,
                            "best_rms": float(progress_state["best_rms"]),
                        })
                    return resid

                try:
                    opt = least_squares(residual_outer, x0, bounds=(lo, hi),
                                        max_nfev=max_outer_evals)
                    fitted_x_local = opt.x
                    outer_opt.update(jac=opt.jac, fun=opt.fun, x=opt.x)
                except _OuterBudgetExhausted:
                    best_x = progress_state["best_x"]
                    fitted_x_local = x0 if best_x is None else best_x
                    # En 1D la jacobiana se calcula igualmente en el mejor
                    # punto (abajo); en 2D no hay errores de los globales.
                delta_final, quad_final, gamma_final, sharp_final, dslope_final, qslope_final = expand(fitted_x_local)
                update_progress(tr("progress.distribution_compute_final",
                                   default="Calculando distribución final…"))
                result_local = run_fit(delta_final, quad_final, gamma_final, sharp_final,
                                       dslope_final, qslope_final)
                if not is_2d:
                    # Jacobiana del bucle externo por diferencias centradas con
                    # un paso razonable: la que deja least_squares usa ~1e-8 y
                    # ahí manda la tolerancia del ajuste interno, no la física
                    # (σ de Γ y sus correlaciones cambiaban ×3 entre ajustes
                    # casi idénticos). Con los mismos ajustes sale cómo se
                    # mueven la media y la anchura de P con cada global.
                    update_progress(tr("progress.distribution_correlations",
                                       default="Correlaciones de P con los globales…"))
                    xb = np.asarray(fitted_x_local, dtype=float)
                    jac, dm = self._distribution_outer_derivatives(
                        lambda x: run_fit(*expand(x), final=False), xb, lo, hi)
                    if jac is not None:
                        outer_opt.update(jac=jac, fun=np.asarray(result_local.residuals), x=xb)
                    if getattr(result_local, "moment_cov", None) is not None:
                        outer_opt["dm_dx"] = dm
            else:
                update_progress(tr("progress.distribution_compute", shape=shape,
                                   default=f"Calculando distribución {shape}…"))
                result_local = run_fit(base_delta, base_quad, base_gamma, sharp_components)
            return result_local, fitted_x_local

        self._pre_fit_snapshot = self._project_state().to_session_payload()
        fit_output = self._run_with_fit_progress(
            tr("progress.distribution_title", default="Distribución hiperfina"),
            tr("progress.distribution_prepare", default="Preparando ajuste de distribución…"),
            compute_distribution,
            error_title=tr("fit.run"),
        )
        if fit_output is None:
            return
        if hasattr(self, "act_undo_fit"):
            self.act_undo_fit.setEnabled(True)
        result, fitted_x = fit_output
        global_cov = self._distribution_global_covariance(outer_specs, outer_opt, result)

        self._building = True
        self.calib.baseline.set_value(float(result.baseline))
        self.calib.slope.set_value(float(result.slope))
        if fitted_x is not None:
            for i, (key, kind, _lo, _hi) in enumerate(outer_specs):
                value = float(np.exp(fitted_x[i])) if kind == "loggamma" else float(fitted_x[i])
                if key == "dist_delta":
                    d.delta.set_value(value)
                elif key == "dist_quad":
                    d.quad.set_value(value)
                elif key == "dist_gamma":
                    d.gamma.set_value(value)
                elif key == "dist_delta_slope":
                    d.delta_slope.set_value(value)
                elif key == "dist_quad_slope":
                    d.quad_slope.set_value(value)
                elif key.startswith("sharp:"):
                    _sharp, pos_txt, pname = key.split(":")
                    cp = self.components_panels[sharp_indices[int(pos_txt)] - 1]
                    cp.params[pname].set_value(value)
        for name, value in (getattr(result, "fitted_globals", None) or {}).items():
            {"delta": d.delta, "quad": d.quad, "gamma": d.gamma}[name].set_value(float(value))
        if getattr(result, "binomial_start", None) is not None:
            d.binom_start.set_value(float(result.binomial_start))
            d.binom_step.set_value(float(result.binomial_step))
            d.binom_conc.set_value(100.0 * float(result.fitted_dist_p))
        if self.dist_use_sharp and hasattr(result, "sharp_weights") and result.sharp_weights is not None:
            for idx, weight in zip(sharp_indices, result.sharp_weights):
                self.components_panels[idx - 1].params["depth"].set_value(float(weight))
        self._building = False
        # Globales finales, su covarianza y la variable van con el resultado
        # (no con la ventana): si el diálogo se reabre más tarde, la curva
        # δ(x)/ΔEQ(x) y su banda son las de este ajuste.
        # Las gaussianas 2D ajustan δ/ΔEQ/Γ dentro (``fitted_globals``), sin
        # bucle externo ni covarianza de esos globales.
        libres = [k for k, *_ in outer_specs if not k.startswith("sharp:")]
        libres += [f"dist_{n}" for n in (getattr(result, "fitted_globals", None) or {})]
        global_values = {"dist_delta": float(d.delta.value()),
                         "dist_quad": float(d.quad.value()),
                         "dist_gamma": float(d.gamma.value()),
                         "dist_delta_slope": float(d.delta_slope.value()),
                         "dist_quad_slope": float(d.quad_slope.value()),
                         "free": libres,
                         # Parámetros del bucle externo (globales y de los
                         # nítidos): consumen grados de libertad.
                         "n_outer": len(outer_specs)}
        if is_2d:
            result = dataclasses.replace(result, global_cov=global_cov,
                                         global_values=global_values)
        else:
            result = dataclasses.replace(
                result, fit_variable=var, global_cov=global_cov,
                global_values=global_values)

        # Componentes para el gráfico
        # TODO (punto 4): los nítidos se reconstruyen aquí con component_absorption
        # usando los valores de los widgets + el peso ajustado. Una alternativa más
        # fiel sería usar build_sharp_kernel (que el propio ajuste emplea internamente),
        # de modo que si on_fit_distribution refina δ/Γ globales el gráfico sea
        # coherente con los residuos. La rama alternativa está en SHA a7c803b y se
        # puede recuperar cuando el multi-ajuste esté integrado.
        components_for_plot: list[tuple[int, str, np.ndarray]] = []
        if self.dist_use_sharp and hasattr(result, "sharp_weights") and result.sharp_weights is not None and result.sharp_weights.size:
            baseline_line = float(result.baseline) + float(result.slope) * self.file.velocity
            sharp_abs_sum = np.zeros_like(self.file.velocity, dtype=float)
            for idx, weight in zip(sharp_indices, result.sharp_weights):
                cp = self.components_panels[idx - 1]
                comp_state = cp.to_view_state()
                vals = cp.values_dict()
                pfx = f"s{idx}_"
                params = np.array([float(vals.get(pfx + name, 0.0)) for name in SEXTET_PARAM_NAMES], dtype=float)
                params[6] = float(weight)
                extras = None
                if comp_state.kind == "Relajacion":
                    extras = {
                        "blocked_fraction": float(vals.get(pfx + "relax_fraction", 1.0)),
                        "log10_nu": float(vals.get(pfx + "relax_log_nu", 5.0)),
                    }
                elif comp_state.kind == "BlumeTjon":
                    extras = {"log10_nu": float(vals.get(pfx + "relax_log_nu", 5.0))}
                elif comp_state.kind == "NeelSize":
                    extras = {
                        "temperature_k": float(vals.get(pfx + "neel_temp_k", 300.0)),
                        "log10_keff": float(vals.get(pfx + "neel_log10_keff", 4.0)),
                        "mean_d_nm": float(vals.get(pfx + "neel_mean_d_nm", 8.0)),
                        "sigma_lognormal": float(vals.get(pfx + "neel_sigma", 0.25)),
                        "log10_tau0": float(vals.get(pfx + "neel_log10_tau0", -9.0)),
                        "n_bins": int(round(float(vals.get(pfx + "neel_bins", 20.0)))),
                    }
                sharp_abs = component_absorption(self.file.velocity, comp_state.kind, params, extras=extras)
                sharp_abs_sum += sharp_abs
                components_for_plot.append((idx, tr("plot.sharp_label", kind=tr(f"kind.{comp_state.kind}", default=comp_state.kind)), baseline_line - sharp_abs))
            if np.any(sharp_abs_sum > 0):
                dist_name = label if is_2d else ("P(ΔEQ)" if var == "quad" else ("P(IS)" if var == "delta" else "P(BHF)"))
                components_for_plot.insert(0, (0, dist_name, result.fitted_curve + sharp_abs_sum))

        # Persistimos el mapa 2D para que sobreviva a los re-renders posteriores
        # (_finish_gui_fit_result vuelve a dibujar vía _render_fit_result).
        self._dist_map_2d = result if is_2d else None
        if not is_2d:
            _prev_fig = getattr(self, "_dist_map_2d_fig", None)
            if _prev_fig is not None:
                _prev_fig.clf()
            self._dist_map_2d_fig = None
        if hasattr(self, "dist_panel"):
            # Botón para reabrir el gráfico de distribución tras cerrarlo (1D y 2D).
            self.dist_panel.btn_show_map.setText(
                tr("button.show_map", default="Ver mapa 2D…") if is_2d
                else tr("button.show_distribution", default="Ver distribución…"))
            self.dist_panel.btn_show_map.setVisible(True)
        style = get_style(self.plot_style_name)
        show_res = self.act_show_residual.isChecked() if hasattr(self, "act_show_residual") else True
        show_leg = self.act_show_legend.isChecked() if hasattr(self, "act_show_legend") else True
        show_fill = self.act_show_component_fill.isChecked() if hasattr(self, "act_show_component_fill") else True
        self.canvas.render(self.file.velocity, self.file.y_data,
                           model=result.fitted_curve, components=components_for_plot,
                           style=style, show_residual=show_res, show_legend=show_leg,
                           show_component_fill=show_fill,
                           style_name=self.plot_style_name,
                           dist_map_2d=self._dist_map_2d)

        if shape == "2D":
            alpha_q_log = d.log_alpha_q.value() if hasattr(d, "log_alpha_q") else -2.0
            msg = (f"{label}: bins={nbins}×{qbins}  "
                   f"αB=10^{dist_state.log_alpha:.2f} αQ=10^{alpha_q_log:.2f}  "
                   f"RMS={result.rms:.5g}")
        elif is_2d:
            msg = f"{label}: {shape}  bins={nbins}×{qbins}  RMS={result.rms:.5g}"
        if is_2d and getattr(result, "dof_warning", None):
            msg += f"  ⚠ {result.dof_warning}"
        else:
            reg_tag = f"/{result.reg_mode}" if getattr(result, "reg_mode", None) else ""
            msg = (f"{label}: {shape}{reg_tag}  bins={nbins}  "
                   f"α=10^{dist_state.log_alpha:.2f}  RMS={result.rms:.5g}")

        gui_result = GuiFitResult(
            mode="distribution",
            raw_result=result,
            render=GuiFitRenderState(
                velocity=self.file.velocity,
                y_data=self.file.y_data,
                model=result.fitted_curve,
                components=components_for_plot,
            ),
            message=msg,
        )
        self.runtime_results.set_distribution_fit(result, gui_result=gui_result)
        self._finish_gui_fit_result(gui_result)
        self._refresh_minima_overlay()
        class _R:
            pass
        r = _R()
        # Bondad real (χ² con la σ de los datos, ν = N − k, AIC/BIC): antes
        # se ponía el RMS como «χ²red» y dof/AIC/BIC a 0, también en el
        # historial de ajustes.
        resumen = self._distribution_summary(result)
        r.stats = {k: float(v) for k, v in resumen["goodness"].items()
                   if k in ("chi2", "red_chi2", "dof", "aic", "bic", "n_params")}
        # El resultado 2D expone alpha_bhf/alpha_quad en vez de un único alpha.
        alpha_val = getattr(result, "alpha", None)
        if alpha_val is None:
            alpha_val = getattr(result, "alpha_bhf", 0.0)
        r.values = {"baseline": result.baseline, "slope": result.slope, "alpha": alpha_val}
        # Pendientes de correlación δ(H)/ΔEQ(H): solo si la forma las usó (≠ 0).
        dsl = float(getattr(result, "delta_slope", 0.0) or 0.0)
        qsl = float(getattr(result, "quad_slope", 0.0) or 0.0)
        if dsl:
            r.values["delta_slope"] = dsl
        if qsl:
            r.values["quad_slope"] = qsl
        # Componentes VBF: A_k ya es el área de cada gaussiana (gauss_weights está
        # normalizada a área unidad); mostramos área y su % relativo (A_k/ΣA) por sitio.
        vbf = getattr(result, "vbf_components", None)
        if vbf:
            area_tot = sum(max(float(c[0]), 0.0) for c in vbf)
            for i, comp in enumerate(vbf, start=1):
                try:
                    a, mu, _sg = comp
                    a = max(float(a), 0.0)
                    r.values[f"vbf{i}_area"] = a
                    r.values[f"vbf{i}_area%"] = (100.0 * a / area_tot) if area_tot > 0 else 0.0
                    r.values[f"vbf{i}_mu"] = float(mu)
                except Exception:
                    pass
        # Gaussianas 2D: área, % y centro (μx, μy) de cada una.
        vbf2d = getattr(result, "vbf2d_components", None)
        if vbf2d:
            area_tot = sum(c[0] for c in vbf2d)
            for i, (a, mx, my, _sx, _sy, rho) in enumerate(vbf2d, start=1):
                r.values[f"g{i}_area%"] = (100.0 * a / area_tot) if area_tot > 0 else 0.0
                r.values[f"g{i}_mu_{pair[0]}"] = float(mx)
                r.values[f"g{i}_mu_{pair[1]}"] = float(my)
                r.values[f"g{i}_rho"] = float(rho)
        if getattr(result, "binomial_start", None) is not None:
            r.values["binom_conc%"] = 100.0 * float(result.fitted_dist_p)
            r.values["binom_start"] = float(result.binomial_start)
            r.values["binom_step"] = float(result.binomial_step)
        # Czjzek: escala σ del desorden y ΔEQ₀ del entorno ordenado (extendido).
        czjzek_errors = {}
        for key in ("czjzek_sigma", "czjzek_delta0"):
            val = getattr(result, key, None)
            if val is not None:
                r.values[key] = float(val)
                err = getattr(result, f"{key}_err", None)
                if err is not None:
                    czjzek_errors[key] = float(err)
        # Globales (δ, ΔEQ, Γ, κ) y media/anchura de P, con su σ: son las
        # magnitudes entre las que se dan las correlaciones de debajo.
        for f in resumen["globals"]:
            r.values[f["label"]] = f["value"]
            if f["sigma"]:
                czjzek_errors[f["label"]] = f["sigma"]
        m = resumen["moments"]
        if m and not resumen["is_2d"]:
            short = {"bhf": "BHF", "quad": "ΔEQ", "delta": "IS"}.get(
                resumen["variable"], resumen["variable"])
            for mk, lbl in (("mean", f"⟨{short}⟩"), ("std", f"σ({short})")):
                r.values[lbl] = m[mk]
                if m.get(f"{mk}_sigma"):
                    czjzek_errors[lbl] = m[f"{mk}_sigma"]
        # free_keys guía qué parámetros muestra el panel; sin esto no salía ninguno.
        r.free_keys = list(r.values.keys())
        r.errors = czjzek_errors
        r.correlations = resumen["correlations"]
        r.n_starts = 1
        self.info_panel.show_result(r)
        if hasattr(self, "_record_fit_history"):
            self._record_fit_history("distribution", r.stats)
        self._show_distribution_dialog(result)

    @staticmethod
    def _distribution_outer_derivatives(fit_at, x: np.ndarray, lo: np.ndarray,
                                        hi: np.ndarray):
        """(jacobiana del residuo, derivadas de los momentos de P) respecto a x.

        Diferencias centradas reajustando la distribución en x ± h (2n ajustes
        internos); h es una milésima del intervalo permitido de cada parámetro.
        La jacobiana es N × n; las derivadas de (media, desviación) de P,
        2 × n. Cualquiera de las dos es None si no se pudo calcular.
        """
        from mossbauer_distribution import distribution_moments

        def evalua(xi: np.ndarray):
            r = fit_at(xi)
            m = distribution_moments(r.bhf_centers, r.probability)
            mom = np.array([m.get("mean", np.nan), m.get("std", np.nan)], dtype=float)
            return np.asarray(r.residuals, dtype=float), mom

        try:
            J = D = None
            for i in range(x.size):
                span = float(hi[i] - lo[i]) if np.isfinite(hi[i] - lo[i]) else 1.0
                h = 1e-3 * max(span, 1e-6)
                a, b = max(x[i] - h, lo[i]), min(x[i] + h, hi[i])
                xa, xb = x.copy(), x.copy()
                xa[i], xb[i] = a, b
                (ra, ma), (rb, mb) = evalua(xa), evalua(xb)
                if J is None:
                    J = np.empty((ra.size, x.size)); D = np.empty((2, x.size))
                J[:, i] = (rb - ra) / (b - a)
                D[:, i] = (mb - ma) / (b - a)
            if J is None or not np.all(np.isfinite(J)):
                return None, None
            return J, (D if np.all(np.isfinite(D)) else None)
        except Exception:
            return None, None

    @staticmethod
    def _distribution_moment_sensitivity(fit_at, x: np.ndarray, lo: np.ndarray,
                                         hi: np.ndarray) -> np.ndarray | None:
        """Derivadas (2 × n) de la media y la desviación de P respecto a x."""
        return DistributionFitMixin._distribution_outer_derivatives(fit_at, x, lo, hi)[1]

    @staticmethod
    def _distribution_global_covariance(outer_specs, outer_opt, result) -> dict:
        """{(clave_i, clave_j): cov} de los globales y de los momentos de P.

        Claves ``dist_delta``, ``dist_quad``, ``dist_gamma``,
        ``dist_delta_slope``, ``dist_quad_slope``, en unidades físicas: Γ se
        refina en log Γ y su covarianza se pasa a Γ con dΓ = Γ·d(log Γ).
        Si el resultado trae ``moment_cov`` añade ``dist_P_mean`` y
        ``dist_P_std`` (media y desviación de P). Con P reajustada en cada
        punto, los momentos son m = m*(g) + ruido interno, y en la
        aproximación lineal (D = dm*/dg, C = cov de los globales):

            cov(m, g) = D·C        cov(m) = cov_interna(m) + D·C·Dᵀ

        Sin bucle externo solo queda la parte interna. Vacío si se agotó el
        presupuesto de evaluaciones en 2D (no hay jacobiana fiable).
        """
        mom = getattr(result, "moment_cov", None)
        out: dict = {}
        cov = None
        if outer_specs and "jac" in outer_opt:
            cov = global_parameter_covariance(
                outer_opt["jac"], outer_opt["fun"],
                float(getattr(result, "effective_dof", None) or 0.0))
        if cov is not None:
            x = np.asarray(outer_opt.get("x", np.zeros(len(outer_specs))), dtype=float)
            globales = {i: k for i, (k, _kind, _lo, _hi) in enumerate(outer_specs)
                        if not k.startswith("sharp:")}
            escala = {i: (float(np.exp(x[i])) if outer_specs[i][1] == "loggamma" else 1.0)
                      for i in globales}
            out = {(globales[i], globales[j]): float(cov[i, j]) * escala[i] * escala[j]
                   for i in globales for j in globales}
        if mom is None:
            return out
        mom = np.asarray(mom, dtype=float)
        claves_m = ("dist_P_mean", "dist_P_std")
        D = outer_opt.get("dm_dx") if cov is not None else None
        if D is not None:
            D = np.asarray(D, dtype=float)
            c_mg = D @ cov
            mom = mom + c_mg @ D.T
            for a, ka in enumerate(claves_m):
                for i, kg in globales.items():
                    out[(ka, kg)] = out[(kg, ka)] = float(c_mg[a, i]) * escala[i]
        elif cov is not None:
            # Hubo globales libres pero no su efecto sobre P: sin la parte
            # cruzada, los momentos no deben mezclarse con ellos.
            return out
        for a, ka in enumerate(claves_m):
            for b, kb in enumerate(claves_m):
                out[(ka, kb)] = float(mom[a, b])
        return out

    def _distribution_correlation_curves(self, result) -> list[dict]:
        """Curvas δ(x)/ΔEQ(x) que el kernel aplicó en un ajuste 1D, con su σ.

        Una por pendiente no nula que tenga sentido con la variable: P(BHF)
        δ(H) y ΔEQ(H); P(ΔEQ) δ(ΔEQ); P(IS) ΔEQ(IS). Cada entrada lleva
        ``label``, ``curve``, ``sigma`` y ``has_error`` (False si ni el global
        ni la pendiente se refinaron: la banda es nula).
        """
        var = getattr(result, "fit_variable", None) or self.dist_variable
        centers = np.asarray(result.bhf_centers, dtype=float)
        ref = getattr(result, "slope_ref", None)
        if centers.size < 2:
            return []
        if ref is None:
            ref = float(np.mean(centers))
        cov = getattr(result, "global_cov", None) or {}
        d = self.dist_panel
        valores = getattr(result, "global_values", None) or {
            "dist_delta": float(d.delta.value()), "dist_quad": float(d.quad.value())}
        short = {"bhf": "BHF", "quad": "ΔEQ", "delta": "IS"}.get(var, var)
        candidatos = []
        if var in ("bhf", "quad"):
            candidatos.append(("δ", "dist_delta", "dist_delta_slope",
                               valores["dist_delta"], float(result.delta_slope or 0.0)))
        if var in ("bhf", "delta"):
            candidatos.append(("ΔEQ", "dist_quad", "dist_quad_slope",
                               valores["dist_quad"], float(result.quad_slope or 0.0)))
        out = []
        for nombre, k_base, k_slope, base, slope in candidatos:
            if slope == 0.0:
                continue
            curve, sigma = correlation_curve(
                centers, base, slope, float(ref),
                var_base=cov.get((k_base, k_base), 0.0),
                var_slope=cov.get((k_slope, k_slope), 0.0),
                cov_base_slope=cov.get((k_base, k_slope), 0.0))
            var_k = float(cov.get((k_slope, k_slope), 0.0))
            out.append({"label": f"{nombre}({short})", "curve": curve, "sigma": sigma,
                        "has_error": bool(np.any(sigma > 0)),
                        "slope": slope,
                        "slope_free": k_slope in (valores.get("free") or ()),
                        "slope_sigma": float(np.sqrt(var_k)) if var_k > 0 else None})
        return out

    def _distribution_summary(self, result) -> dict:
        """Lo que el informe y la exportación cuentan de un ajuste de distribución.

        ``goodness`` (χ², ν, χ²_ν, AIC, BIC, RMS, lag-1, rachas), ``moments``
        (1D: media, σ, moda de P), ``globals`` (filas δ/ΔEQ/Γ/κ con valor, σ,
        libre y unidad), ``high_corr`` (pares de globales con |r| ≥ 0.95) y
        ``variable``/``pair``.
        """
        from core.result_views import DistributionResultView
        from mossbauer_distribution import distribution_goodness, distribution_moments

        is_2d = DistributionResultView(result).is_2d()
        gv = getattr(result, "global_values", None) or {}
        cov = getattr(result, "global_cov", None) or {}
        free = set(gv.get("free") or ())
        sigma = getattr(self.file, "sigma", None)
        res = np.asarray(result.residuals, dtype=float)
        if sigma is not None and np.asarray(sigma).size != res.size:
            sigma = None
        goodness = distribution_goodness(
            res, sigma, getattr(result, "effective_dof", None),
            n_outer=int(gv.get("n_outer", 0)))
        if is_2d:
            dvars = (getattr(result, "x_variable", "bhf"), getattr(result, "y_variable", "quad"))
            variable, moments = None, {}
        else:
            variable = getattr(result, "fit_variable", None) or self.dist_variable
            dvars = (variable,)
            moments = distribution_moments(result.bhf_centers, result.probability)
        kappa_unit = "mm/s·T⁻¹" if variable == "bhf" else ""
        filas = []
        candidatos = [("dist_delta", "δ", "mm/s", "delta" not in dvars),
                      ("dist_quad", "ΔEQ", "mm/s", "quad" not in dvars),
                      ("dist_gamma", "Γ", "mm/s", True),
                      ("dist_delta_slope", "κδ", kappa_unit, variable in ("bhf", "quad")),
                      ("dist_quad_slope", "κq", kappa_unit, variable in ("bhf", "delta"))]
        for key, label, unit, aplica in candidatos:
            if not aplica or key not in gv:
                continue
            value = float(gv[key])
            if key.endswith("_slope") and value == 0.0 and key not in free:
                continue
            var = cov.get((key, key))
            filas.append({"key": key, "label": label, "value": value, "unit": unit,
                          "sigma": float(np.sqrt(var)) if var and var > 0 else None,
                          "free": key in free})
        etiquetas = {f["key"]: f["label"] for f in filas}
        # Media y anchura de P: su σ incluye la de los globales (ver
        # _distribution_global_covariance) y entran en las correlaciones.
        short = {"bhf": "BHF", "quad": "ΔEQ", "delta": "IS"}.get(variable, variable)
        for key, lbl, mk in (("dist_P_mean", f"⟨{short}⟩", "mean"),
                             ("dist_P_std", f"σ({short})", "std")):
            var_m = cov.get((key, key))
            if moments and var_m is not None and var_m > 0:
                moments[f"{mk}_sigma"] = float(np.sqrt(var_m))
                etiquetas[key] = lbl
        pairs = []
        claves = [k for k in etiquetas if cov.get((k, k), 0.0) > 0]
        for i, a in enumerate(claves):
            for b in claves[i + 1:]:
                den = np.sqrt(cov[(a, a)] * cov[(b, b)])
                if (a, b) in cov and den > 0:
                    pairs.append({"param1": etiquetas[a], "param2": etiquetas[b],
                                  "corr": float(cov[(a, b)] / den)})
        pairs.sort(key=lambda p: -abs(p["corr"]))
        high = [(p["param1"], p["param2"], p["corr"]) for p in pairs if abs(p["corr"]) >= 0.95]
        # Matriz en orden fijo (globales y luego media/anchura de P).
        matriz = np.eye(len(claves))
        for i, a in enumerate(claves):
            for j, b in enumerate(claves):
                if i != j:
                    den = np.sqrt(cov[(a, a)] * cov[(b, b)])
                    matriz[i, j] = cov.get((a, b), np.nan) / den if den > 0 else np.nan
        corr_info = {"pairs": pairs, "keys": [etiquetas[k] for k in claves],
                     "matrix": matriz.tolist()}
        return {"goodness": goodness, "moments": moments, "globals": filas,
                "high_corr": high, "corr_pairs": pairs, "correlations": corr_info,
                "variable": variable,
                "is_2d": is_2d, "has_sigma": sigma is not None}

    def _export_distribution_data(self, result=None, parent=None) -> str | None:
        """Guarda los datos de la distribución (TSV) con un resumen en la cabecera.

        1D: variable, P normalizada, σ de P (banda Monte Carlo), peso y las
        curvas δ(x)/ΔEQ(x) con su σ. 2D: una fila por celda (x, y, P, peso).
        Devuelve la ruta escrita o None.
        """
        from datetime import datetime
        from mossbauer_distribution import write_distribution_data

        result = result if result is not None else getattr(
            self.runtime_results, "distribution_result", None)
        if result is None:
            QtWidgets.QMessageBox.information(
                parent or self, tr("file.export_distribution"),
                tr("msg.no_distribution_result"))
            return None
        stem = self.file.path.stem if self.file.path else "distribution"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            parent or self, tr("file.export_distribution"),
            str(ROOT / f"{stem}_distribution.dat"),
            "TSV (*.dat *.tsv *.txt);;All (*.*)")
        if not path:
            return None
        s = self._distribution_summary(result)
        g = s["goodness"]
        header = [f"Fitbauer v{APP_VERSION} — {self.file.path.name if self.file.path else '—'}"
                  f" — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                  f"shape={getattr(result, 'shape', None) or '—'}"
                  f"  reg_mode={getattr(result, 'reg_mode', None) or '—'}"]
        alphas = [f"{k}={float(getattr(result, k)):.6g}"
                  for k in ("alpha", "alpha_bhf", "alpha_quad")
                  if getattr(result, k, None) is not None]
        if alphas:
            header.append("  ".join(alphas))
        stats = [f"{k}={g[k]:.6g}" for k in ("chi2", "dof", "red_chi2", "aic", "bic", "rms")
                 if k in g]
        if stats:
            header.append("  ".join(stats))
        for f in s["globals"]:
            err = f"±{f['sigma']:.3g}" if f["sigma"] else ""
            estado = "free" if f["free"] else "fixed"
            header.append(f"{f['label']} = {f['value']:.6g}{err} {f['unit']} ({estado})".strip())
        for key, lbl in (("czjzek_sigma", "Czjzek sigma"), ("czjzek_delta0", "Czjzek dEQ0")):
            val = getattr(result, key, None)
            if val is not None:
                err = getattr(result, f"{key}_err", None)
                header.append(f"{lbl} = {val:.6g}" + (f"±{err:.3g}" if err else "") + " mm/s")
        extra = {}
        if not s["is_2d"]:
            nombres = {"δ": "delta", "ΔEQ": "dEQ"}
            for c in self._distribution_correlation_curves(result):
                base = nombres.get(c["label"].split("(")[0], "corr")
                extra[f"{base}_curve_mm_s"] = c["curve"]
                if c["has_error"]:
                    extra[f"{base}_curve_sigma"] = c["sigma"]
        try:
            write_distribution_data(path, result, header=header, extra_columns=extra)
        except OSError as exc:
            QtWidgets.QMessageBox.critical(parent or self, tr("file.export_distribution"),
                                           f"{type(exc).__name__}: {exc}")
            return None
        self.statusBar().showMessage(tr("status.distribution_saved", path=path), 5000)
        return path

    def _show_distribution_dialog(self, result) -> None:
        from core.result_views import DistributionResultView
        view = DistributionResultView(result)
        if view.is_2d():
            self._show_distribution_dialog_2d(result, view)
        else:
            self._show_distribution_dialog_1d(result)

    def _distribution_figure_1d(self, result):
        """Figura de P(x) 1D con su banda 1σ y la curva δ(x)/ΔEQ(x) si las hay.

        La usan el diálogo y el informe PDF. Devuelve (fig, ax, banda, eje_corr).
        """
        var = getattr(result, "fit_variable", None) or self.dist_variable
        title = {"quad": "P(ΔEQ)", "delta": "P(IS)"}.get(var, "P(BHF)")
        xlabel = tr({"quad": "plot.distribution_xlabel_deq",
                     "delta": "plot.distribution_xlabel_is"}.get(
                         var, "plot.distribution_xlabel_bhf"))
        fig = Figure(figsize=(8.0, 4.5), dpi=96, constrained_layout=True)
        ax = fig.add_subplot(111)
        xc = np.asarray(result.bhf_centers, dtype=float)
        pr = np.asarray(result.probability, dtype=float)
        if getattr(result, "shape", None) == "Binomial":
            # Distribución discreta: una barra por nº de vecinos (P_k suma 1).
            width = 0.6 * float(np.min(np.diff(xc))) if xc.size > 1 else 0.5
            ax.bar(xc, pr, width=width, color="#93c5fd", edgecolor="#2563eb")
        else:
            ax.plot(xc, pr, "-", color="#2563eb", lw=2.0)
            ax.fill_between(xc, pr, 0, color="#93c5fd", alpha=0.45)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(title)
        ax.grid(True, alpha=0.3)
        band = self._draw_probability_band(ax, xc, pr, result)
        corr_ax = self._draw_correlation_axis(ax, xc, pr, result)
        return fig, ax, band, corr_ax

    def _distribution_figure_2d(self, result, view=None):
        """Mapa P(x, y) con sus marginales; lo usan el diálogo y el informe PDF."""
        from matplotlib.gridspec import GridSpec
        from core.result_views import DistributionResultView
        view = view if view is not None else DistributionResultView(result)
        xc, yc, P = view.probability_2d()
        xlbl, ylbl = view.var_labels_2d()
        mx, my = view.marginals_2d()
        xv = getattr(result, "x_variable", "bhf")
        yv = getattr(result, "y_variable", "quad")
        _short = {"bhf": "B_HF", "quad": "ΔEQ", "delta": "δ"}
        title_map = f"P({_short.get(xv, xv)}, {_short.get(yv, yv)})"
        fig = Figure(figsize=(8.5, 7.0), dpi=96, constrained_layout=True)

        # Disposición: fila superior = marginal x; columna derecha = marginal y;
        # celda principal = heatmap 2D.
        has_marginals = mx is not None and my is not None
        if has_marginals:
            gs = GridSpec(2, 2, figure=fig,
                          width_ratios=[4, 1], height_ratios=[1, 4],
                          hspace=0.06, wspace=0.06)
            ax_main  = fig.add_subplot(gs[1, 0])
            ax_top   = fig.add_subplot(gs[0, 0], sharex=ax_main)
            ax_right = fig.add_subplot(gs[1, 1], sharey=ax_main)
        else:
            gs = GridSpec(1, 1, figure=fig)
            ax_main = fig.add_subplot(gs[0, 0])
            ax_top = ax_right = None

        cmap = "viridis"
        im = ax_main.pcolormesh(xc, yc, P.T, cmap=cmap, shading="auto")
        if P.size >= 4:
            try:
                ax_main.contour(xc, yc, P.T, levels=5,
                                colors="white", linewidths=0.6, alpha=0.5)
            except Exception:
                pass
        fig.colorbar(im, ax=ax_main, fraction=0.046, pad=0.04, label="P(x, y)")
        ax_main.set_xlabel(xlbl, fontsize=10)
        ax_main.set_ylabel(ylbl, fontsize=10)
        ax_main.set_title(title_map, fontsize=11, fontweight="bold")
        ax_main.grid(False)

        if has_marginals and ax_top is not None and ax_right is not None:
            # Marginal X (superior)
            norm_x = float(mx.max()) or 1.0
            ax_top.fill_between(xc, mx / norm_x, 0, color="#3b82f6", alpha=0.55)
            ax_top.plot(xc, mx / norm_x, "-", color="#1d4ed8", lw=1.5)
            ax_top.set_ylabel("P(x)", fontsize=8)
            ax_top.tick_params(labelbottom=False, labelsize=7)
            ax_top.grid(True, alpha=0.25)
            ax_top.set_title("")
            # Marginal Y (derecha) — horizontal
            norm_y = float(my.max()) or 1.0
            ax_right.fill_betweenx(yc, my / norm_y, 0, color="#f59e0b", alpha=0.55)
            ax_right.plot(my / norm_y, yc, "-", color="#d97706", lw=1.5)
            ax_right.set_xlabel("P(y)", fontsize=8)
            ax_right.tick_params(labelleft=False, labelsize=7)
            ax_right.grid(True, alpha=0.25)

        # Estadísticas en texto
        lines = []
        for attr, fmt, name in (
            ("mean_bhf",  ".3f", f"⟨{_short.get(xv, xv)}⟩"),
            ("sigma_bhf", ".3f", f"σ({_short.get(xv, xv)})"),
            ("mean_quad", ".3f", f"⟨{_short.get(yv, yv)}⟩"),
            ("sigma_quad",".3f", f"σ({_short.get(yv, yv)})"),
            ("corr_bhf_quad", ".3f", "ρ(x,y)"),
        ):
            val = getattr(result, attr, None)
            if val is not None:
                lines.append(f"{name} = {val:{fmt}}")
        if lines:
            ax_main.annotate(
                "  ".join(lines),
                xy=(0.01, 0.01), xycoords="axes fraction",
                fontsize=7.5, color="white",
                bbox=dict(boxstyle="round,pad=0.25", fc="#00000080", ec="none"),
            )

        return fig

    def _show_distribution_dialog_1d(self, result) -> None:
        var = getattr(result, "fit_variable", None) or self.dist_variable
        title = {"quad": "P(ΔEQ)", "delta": "P(IS)"}.get(var, "P(BHF)")
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(720, 480)
        lay = QtWidgets.QVBoxLayout(dlg)
        fig, ax, band, corr_ax = self._distribution_figure_1d(result)
        cv = FigureCanvas(fig); lay.addWidget(cv, stretch=1)
        bottom = QtWidgets.QHBoxLayout()
        if band is not None:
            chk_b = QtWidgets.QCheckBox(tr("plot.show_prob_band"))
            chk_b.setToolTip(tr("tooltip.show_prob_band"))
            chk_b.setChecked(bool(getattr(self, "_dist_show_band", True)))

            def _toggle_band(on: bool) -> None:
                self._dist_show_band = bool(on)
                for artist in band:
                    artist.set_visible(bool(on))
                cv.draw_idle()

            _toggle_band(chk_b.isChecked())
            chk_b.toggled.connect(_toggle_band)
            self._dist_band_check = chk_b
            bottom.addWidget(chk_b)
        if corr_ax is not None:
            chk = QtWidgets.QCheckBox(tr("plot.show_correlation"))
            chk.setToolTip(tr("tooltip.show_correlation"))
            chk.setChecked(bool(getattr(self, "_dist_show_correlation", True)))
            corr_ax.set_visible(chk.isChecked())

            def _toggle(on: bool) -> None:
                self._dist_show_correlation = bool(on)
                corr_ax.set_visible(bool(on))
                cv.draw_idle()

            chk.toggled.connect(_toggle)
            self._dist_corr_check = chk
            bottom.addWidget(chk)
        bottom.addStretch(1)
        cv.draw_idle()
        btn_data = QtWidgets.QPushButton(tr("button.save_distribution_data"))
        btn_data.clicked.connect(lambda: self._export_distribution_data(result, dlg))
        bottom.addWidget(btn_data)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject); bottom.addWidget(bb)
        lay.addLayout(bottom)
        self._dist_dialog_axes = (ax, corr_ax)
        self._dist_dialog_band = band
        dlg.exec()

    @staticmethod
    def _draw_probability_band(ax, xc, pr, result):
        """Banda ±1σ de P(x) por Monte Carlo paramétrico (``probability_sigma``
        del resultado: Histograma con Tikhonov o TV), recortada a P ≥ 0.
        Devuelve sus artistas (relleno y leyenda) o None si no hay banda.

        No se usa ``weight_sigma`` (covarianza linealizada): ignora P ≥ 0 y,
        con picos rodeados de bins a cero, sale de 2 a 16 veces más ancha que
        la dispersión real de reajustes con ruido.
        """
        sp = getattr(result, "probability_sigma", None)
        if sp is None or len(sp) != len(pr) or not np.any(np.asarray(sp) > 0):
            return None
        sp = np.asarray(sp, dtype=float)
        fill = ax.fill_between(xc, np.clip(pr - sp, 0.0, None), pr + sp,
                               color="#1d4ed8", alpha=0.22, linewidth=0,
                               label=tr("plot.prob_band_label"))
        leg = ax.legend(handles=[fill], loc="upper left", fontsize=8, framealpha=0.85)
        return (fill, leg)

    def _draw_correlation_axis(self, ax, xc, pr, result):
        """Eje derecho con δ(x)/ΔEQ(x) del kernel y su banda 1σ; None si no hay.

        La recta se dibuja continua donde P(x) tiene peso (≥ 2 % del máximo) y
        punteada fuera: ahí es una extrapolación que los datos no restringen.
        La banda solo se dibuja en la zona con peso.
        """
        curves = self._distribution_correlation_curves(result)
        if not curves:
            return None
        cax = ax.twinx()
        pmax = float(np.max(pr)) if pr.size else 0.0
        mask = pr >= 0.02 * pmax if pmax > 0 else np.ones_like(pr, dtype=bool)
        colores = ("#dc2626", "#16a34a")
        for c, color in zip(curves, colores):
            y, sg = c["curve"], c["sigma"]
            cax.plot(xc, y, ":", color=color, lw=1.0, alpha=0.7)
            label = c["label"] + (" ± 1σ" if c["has_error"] else "")
            if c["slope_sigma"] is not None:
                label += f"   κ = {c['slope']:.3g} ± {c['slope_sigma']:.2g}"
            elif c.get("slope_free"):
                label += f"   κ = {c['slope']:.3g} ({tr('plot.kappa_no_sigma')})"
            else:
                label += f"   κ = {c['slope']:.3g} ({tr('plot.kappa_fixed')})"
            cax.plot(xc, np.where(mask, y, np.nan), "-", color=color, lw=1.8,
                     label=label)
            if c["has_error"]:
                cax.fill_between(xc, y - sg, y + sg, where=mask, color=color,
                                 alpha=0.18, linewidth=0)
        # Escala del eje: la zona con peso y su banda, no la recta extrapolada
        # (que, con una pendiente grande, aplastaría lo que importa).
        zona = [np.concatenate([(c["curve"] - c["sigma"])[mask],
                                (c["curve"] + c["sigma"])[mask]]) for c in curves]
        zona = np.concatenate(zona) if zona else np.array([])
        if zona.size and np.all(np.isfinite(zona)):
            lo, hi = float(np.min(zona)), float(np.max(zona))
            pad = max(0.15 * (hi - lo), 0.01)
            cax.set_ylim(lo - pad, hi + pad)
        cax.set_ylabel(tr("plot.correlation_ylabel",
                          names=", ".join(c["label"] for c in curves)))
        cax.legend(loc="upper right", fontsize=8, framealpha=0.85)
        return cax

    def _show_distribution_dialog_2d(self, result, view) -> None:
        xv = getattr(result, "x_variable", "bhf")
        yv = getattr(result, "y_variable", "quad")
        _short = {"bhf": "B_HF", "quad": "ΔEQ", "delta": "δ"}
        title_map = f"P({_short.get(xv, xv)}, {_short.get(yv, yv)})"

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title_map)
        dlg.resize(820, 700)
        lay = QtWidgets.QVBoxLayout(dlg)

        fig = self._distribution_figure_2d(result, view)
        cv = FigureCanvas(fig); lay.addWidget(cv, stretch=1)
        cv.draw_idle()

        # Persist for the PDF report
        self._dist_map_2d_fig = fig

        btn_row = QtWidgets.QHBoxLayout()
        btn_save = QtWidgets.QPushButton(tr("button.save_figure", default="Guardar figura…"))

        def _save_figure() -> None:
            stem = self.file.path.stem if self.file.path else "map2d"
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                dlg,
                tr("dialog.save_2d_figure", default="Guardar mapa 2D"),
                str(ROOT / f"{stem}_mapa2D.png"),
                "PNG (*.png);;SVG (*.svg);;PDF (*.pdf);;All (*.*)",
            )
            if path:
                try:
                    fig.savefig(path, dpi=150, bbox_inches="tight")
                except Exception as exc:
                    QtWidgets.QMessageBox.warning(
                        dlg,
                        tr("dialog.save_2d_figure", default="Guardar mapa 2D"),
                        f"{type(exc).__name__}: {exc}",
                    )

        btn_save.clicked.connect(_save_figure)
        btn_row.addWidget(btn_save)
        btn_data = QtWidgets.QPushButton(tr("button.save_distribution_data"))
        btn_data.clicked.connect(lambda: self._export_distribution_data(result, dlg))
        btn_row.addWidget(btn_data)
        btn_row.addStretch()
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        btn_row.addWidget(bb)
        lay.addLayout(btn_row)
        dlg.exec()

    def _on_reopen_map_dialog(self) -> None:
        # Reabre el último gráfico de distribución (1D P(BHF)/P(ΔEQ) o 2D) desde
        # el resultado ya persistido, sin re-ejecutar el ajuste.
        result = getattr(self.runtime_results, "distribution_result", None)
        if result is None:
            result = getattr(self, "_dist_map_2d", None)
        if result is not None:
            self._show_distribution_dialog(result)
        else:
            QtWidgets.QMessageBox.information(
                self, tr("button.show_distribution", default="Ver distribución…"),
                tr("bhf.no_distribution_yet",
                   default="Aún no hay ninguna distribución ajustada que mostrar."))
