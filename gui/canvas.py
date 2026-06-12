"""Canvas Matplotlib usado por la interfaz Qt de Fitbauer."""
from __future__ import annotations

import logging
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from mossbauer_i18n import tr
from core.plot_styles import get_style


class SpectrumCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(7.0, 5.0), dpi=100, facecolor="white",
                          constrained_layout=True)
        super().__init__(self.fig)
        self.setParent(parent)
        # Preferencia de mostrar la subgráfica de diferencia (residuos). Se fija
        # al arrancar según los ajustes, de modo que el espacio dedicado se
        # reserva (o no) desde el inicio.
        self.residual_pref = True
        self._gs = self.fig.add_gridspec(2, 1, height_ratios=[4.6, 1.0], hspace=0.08)
        self.ax = self.fig.add_subplot(self._gs[0])
        self.ax_res = self.fig.add_subplot(self._gs[1], sharex=self.ax)
        self.ax.set_ylabel(tr("plot.transmission_ylabel"))
        self.ax_res.set_xlabel(tr("plot.velocity_xlabel"))
        self.ax_res.set_ylabel(tr("plot.residual_ylabel"))
        self.last_render: dict | None = None
        # Estado para la actualización incremental (evita reconstruir toda la
        # figura en cada refresco: solo se reescriben los datos de las líneas).
        self._artists: dict | None = None
        self._layout_sig: tuple | None = None
        self.show_no_file()

    def show_no_file(self) -> None:
        self.last_render = None
        self._artists = None
        self._layout_sig = None
        # Reconstruye la rejilla según la preferencia: con residuos (2 filas) o
        # sin ellos (1 fila), para que el espacio coincida con la opción ya
        # desde el arranque.
        self.fig.clear()
        if self.residual_pref:
            self._gs = self.fig.add_gridspec(2, 1, height_ratios=[4.6, 1.0], hspace=0.08)
            self.ax = self.fig.add_subplot(self._gs[0])
            self.ax_res = self.fig.add_subplot(self._gs[1], sharex=self.ax)
        else:
            self._gs = self.fig.add_gridspec(1, 1)
            self.ax = self.fig.add_subplot(self._gs[0])
            self.ax_res = None
        self.ax.text(0.5, 0.5, tr("plot.no_file"),
                     transform=self.ax.transAxes, ha="center", va="center",
                     fontsize=13, color="#075985", fontweight="bold")
        self.ax.set_xticks([]); self.ax.set_yticks([])
        if self.ax_res is not None:
            self.ax_res.set_xticks([]); self.ax_res.set_yticks([])
        self.draw_idle()

    def render(self, v: np.ndarray, y: np.ndarray,
               model: np.ndarray | None = None,
               components: list[tuple[int, str, np.ndarray]] | None = None,
               style: dict | None = None,
               show_residual: bool = True,
               show_legend: bool = True,
               model_v: np.ndarray | None = None,
               residual: np.ndarray | None = None,
               style_name: str | None = None,
               dist_map_2d=None) -> None:
        s = style or get_style("classic")
        actual_show_residual = bool(show_residual)
        # ``model``/``components`` pueden venir muestreados en una rejilla densa
        # (``model_v``) para que la curva de ajuste salga suave aunque el espectro
        # tenga pocos canales. Los datos y los residuos van en la rejilla ``v``.
        mv = model_v if model_v is not None else v
        if residual is None and model is not None and model_v is None:
            residual = y - model
        # Estado para el gráfico Plotly (y otros consumidores) y para alternar.
        self.last_render = {
            "velocity": np.asarray(v, dtype=float).copy(),
            "y_data": np.asarray(y, dtype=float).copy(),
            "model": None if model is None else np.asarray(model, dtype=float).copy(),
            "model_v": np.asarray(mv, dtype=float).copy(),
            "residual": None if residual is None else np.asarray(residual, dtype=float).copy(),
            "components": [
                (int(idx), str(kind), np.asarray(comp, dtype=float).copy())
                for idx, kind, comp in (components or [])
            ],
            "style": dict(s),
            "show_residual": bool(show_residual),
            "show_legend": bool(show_legend),
            "dist_map_2d": dist_map_2d,
        }
        n_comp = len(components or [])
        has_2d = dist_map_2d is not None
        # Firma de la disposición: si no cambia, se reutilizan los ejes/artistas
        # y solo se reescriben los datos (mucho más rápido, sin reconstruir).
        layout_sig = (actual_show_residual, model is not None, n_comp,
                      bool(show_legend), style_name, int(np.asarray(v).size),
                      int(np.asarray(mv).size), has_2d)
        if (self._artists is not None and self._layout_sig == layout_sig
                and style_name is not None):
            try:
                self._update_fast(v, y, model, components, residual, mv, s,
                                  actual_show_residual)
                return
            except Exception as _exc:
                logging.debug("Actualización incremental del canvas fallida, reconstruyendo: %s", _exc)
                self._artists = None
        self.fig.set_facecolor(s["fig_bg"])
        # El espacio de residuos depende SOLO de la opción 'mostrar diferencia',
        # no de que exista un modelo: así un ajuste no altera la disposición.
        self.residual_pref = actual_show_residual
        self.fig.clear()
        self._artists = None
        self.ax_map = None
        if has_2d and actual_show_residual:
            self._gs = self.fig.add_gridspec(
                3, 1, height_ratios=[3.5, 0.9, 2.5], hspace=0.08)
            self.ax = self.fig.add_subplot(self._gs[0])
            self.ax_res = self.fig.add_subplot(self._gs[1], sharex=self.ax)
            self.ax_map = self.fig.add_subplot(self._gs[2])
        elif has_2d:
            self._gs = self.fig.add_gridspec(2, 1, height_ratios=[1.5, 1.6], hspace=0.28)
            self.ax = self.fig.add_subplot(self._gs[0])
            self.ax_res = None
            self.ax_map = self.fig.add_subplot(self._gs[1])
        elif actual_show_residual:
            self._gs = self.fig.add_gridspec(2, 1, height_ratios=[4.6, 1.0], hspace=0.08)
            self.ax = self.fig.add_subplot(self._gs[0])
            self.ax_res = self.fig.add_subplot(self._gs[1], sharex=self.ax)
        else:
            self._gs = self.fig.add_gridspec(1, 1)
            self.ax = self.fig.add_subplot(self._gs[0])
            self.ax_res = None
        self.ax.set_facecolor(s["ax_bg"])
        if self.ax_res is not None:
            self.ax_res.set_facecolor(s["res_bg"])
        data_line, = self.ax.plot(v, y, ".", color=s["data"],
                                  ms=s.get("data_ms", 3.5),
                                  alpha=s.get("data_alpha", 0.7),
                                  label=tr("plot.legend_data"))
        comp_lines: list = []
        if components:
            palette = s.get("components_palette") or ("#10b981", "#f59e0b", "#8b5cf6")
            for idx, kind, comp in components:
                label = str(kind) if idx <= 0 else f"{tr(f'kind.{kind}', default=kind)} {idx}"
                color = s.get("dist_line", s.get("model", "#dc2626")) if idx <= 0 else palette[(idx - 1) % len(palette)]
                ln, = self.ax.plot(mv, comp, "--",
                                   color=color,
                                   lw=s.get("component_lw", 1.4),
                                   alpha=s.get("component_alpha", 0.85),
                                   label=label)
                comp_lines.append(ln)
        model_line = None
        res_line = None
        res_fill = None
        if model is not None:
            model_line, = self.ax.plot(mv, model, "-", color=s["model"],
                                       lw=s.get("model_lw", 2.2),
                                       label=tr("plot.legend_model"))
            if residual is not None and actual_show_residual and self.ax_res is not None:
                self.ax_res.axhline(0, color=s["res_zero"], lw=0.9, alpha=0.9)
                res_fill = self.ax_res.fill_between(
                    v, residual, 0, color=s["res_fill"],
                    alpha=s.get("res_fill_alpha", 0.22))
                res_line, = self.ax_res.plot(v, residual, "-", color=s["res_line"],
                                             lw=s.get("res_line_lw", 1.0))
                lim = max(float(np.nanmax(np.abs(residual))) * 1.18, 1e-6)
                self.ax_res.set_ylim(-lim, lim)
        if not actual_show_residual:
            self.ax.tick_params(labelbottom=True)
            self.ax.set_xlabel(tr("plot.velocity_xlabel"), color=s["lbl"])
        else:
            self.ax.tick_params(labelbottom=False)
            self.ax.set_xlabel("")
        self.ax.set_ylabel(tr("plot.transmission_ylabel"), color=s["lbl"])
        self.ax.set_title(tr("plot.title_discrete"), color=s["title"], pad=10,
                          fontweight=s.get("title_weight", "bold"))
        self.ax.tick_params(colors=s["tick"])
        self.ax.grid(True, color=s["grid"], alpha=s["grid_alpha"],
                     linewidth=s.get("grid_lw", 0.8))
        for name, sp in self.ax.spines.items():
            sp.set_color(s["spine"])
            if name in s.get("spines_hide", ()):
                sp.set_visible(False)
        if self.ax_res is not None:
            self.ax_res.set_xlabel(tr("plot.velocity_xlabel"), color=s["lbl"])
            self.ax_res.set_ylabel(tr("plot.residual_ylabel"), color=s["lbl"])
            self.ax_res.tick_params(colors=s["res_tick"])
            self.ax_res.grid(True, color=s["res_grid"], alpha=0.8, linewidth=0.75)
            for name, sp in self.ax_res.spines.items():
                sp.set_color(s["res_spine"])
                if name in s.get("spines_hide", ()):
                    sp.set_visible(False)
        if show_legend:
            self.ax.legend(loc="lower right", fontsize=9, framealpha=0.85,
                           facecolor=s["leg_face"], edgecolor=s["leg_edge"],
                           labelcolor=s["leg_text"])
        if dist_map_2d is not None and self.ax_map is not None:
            self._draw_2d_map(self.ax_map, dist_map_2d, s, style_name)
        self.draw_idle()
        # Memoriza artistas y disposición para los refrescos incrementales.
        self._artists = {
            "data": data_line,
            "comps": comp_lines,
            "model": model_line,
            "res_line": res_line,
            "res_fill": res_fill,
            "res_color": s["res_fill"],
            "res_alpha": s.get("res_fill_alpha", 0.22),
        }
        self._layout_sig = layout_sig

    @staticmethod
    def _draw_2d_map(ax, result, style: dict, style_name: str | None) -> None:
        """Dibuja el heatmap topográfico P(x,y) en el eje ax."""
        from core.result_views import DistributionResultView
        view = DistributionResultView(result)
        try:
            xc, yc, P = view.probability_2d()
        except (AttributeError, Exception):
            return
        xlbl, ylbl = view.var_labels_2d()
        cmap = "inferno" if style_name == "dark" else "viridis"
        ax.set_facecolor(style.get("ax_bg", "#f8fafc"))
        # pcolormesh: Z[j,i] = valor en (y[j], x[i]) → transponer P (n_x, n_y) → (n_y, n_x)
        im = ax.pcolormesh(xc, yc, P.T, cmap=cmap, shading="auto")
        try:
            ax.get_figure().colorbar(im, ax=ax, fraction=0.046, pad=0.04,
                                     label="P(x, y)")
        except Exception as _exc:
            logging.debug("Colorbar del mapa 2D no disponible: %s", _exc)
        # Contornos suaves sobre el heatmap para resaltar la topografía
        if P.size >= 4:
            try:
                ax.contour(xc, yc, P.T, levels=5, colors="white",
                           linewidths=0.5, alpha=0.45)
            except Exception as _exc:
                logging.debug("Contornos del mapa 2D no disponibles: %s", _exc)
        ax.set_xlabel(xlbl, color=style.get("lbl", "#1e293b"))
        ax.set_ylabel(ylbl, color=style.get("lbl", "#1e293b"))
        xv = getattr(result, "x_variable", "bhf")
        yv = getattr(result, "y_variable", "quad")
        _short = {"bhf": "B_HF", "quad": "ΔEQ", "delta": "δ"}
        title = f"P({_short.get(xv, xv)}, {_short.get(yv, yv)})"
        ax.set_title(title, fontsize=9, color=style.get("title", "#0c4a6e"),
                     fontweight="bold")
        ax.tick_params(colors=style.get("tick", "#64748b"))
        for sp in ax.spines.values():
            sp.set_color(style.get("spine", "#cbd5e1"))

    def _update_fast(self, v, y, model, components, residual, mv, s,
                     actual_show_residual) -> None:
        """Refresco incremental: reescribe los datos sin reconstruir la figura.

        Se usa cuando la disposición (residuos, nº de componentes, leyenda,
        estilo y tamaños) no ha cambiado respecto al render anterior. Evita el
        coste de ``fig.clear`` + recrear ejes + ``tight_layout`` en cada cambio
        de parámetro, que es lo que hace lento el arrastre de sliders.
        """
        a = self._artists
        a["data"].set_data(v, y)
        comps = components or []
        for ln, (_idx, _kind, comp) in zip(a["comps"], comps):
            ln.set_data(mv, comp)
        if a["model"] is not None and model is not None:
            a["model"].set_data(mv, model)
        self.ax.relim()
        self.ax.autoscale_view()
        if (a["res_line"] is not None and residual is not None
                and actual_show_residual and self.ax_res is not None):
            a["res_line"].set_data(v, residual)
            # ``fill_between`` no admite set_data: se sustituye la colección.
            if a["res_fill"] is not None:
                try:
                    a["res_fill"].remove()
                except Exception as _exc:
                    logging.debug("No se pudo eliminar el relleno de residuo anterior: %s", _exc)
            a["res_fill"] = self.ax_res.fill_between(
                v, residual, 0, color=a["res_color"], alpha=a["res_alpha"])
            lim = max(float(np.nanmax(np.abs(residual))) * 1.18, 1e-6)
            self.ax_res.set_ylim(-lim, lim)
        self.draw_idle()
