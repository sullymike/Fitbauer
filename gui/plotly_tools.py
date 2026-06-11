"""Vista Plotly interactiva y editor semi-manual de mínimos."""
from __future__ import annotations

import html
import os
import tempfile
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtWidgets

from mossbauer_i18n import tr
from core.constants import APP_NAME, APP_VERSION
from core.result_views import discrete_result_view, distribution_result_view
from core.data_io import CONFIG_DIR
from core.plot_styles import get_style
from gui.bridges import MinimaBridge

ROOT = Path(__file__).resolve().parents[1]


class PlotlyToolsMixin:
    def _current_plotly_figure(self):
        """Construye una figura Plotly a partir de lo último dibujado."""
        render = getattr(self.canvas, "last_render", None)
        if not render:
            raise RuntimeError(tr("msg.plotly_no_plot"))
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except Exception as exc:
            raise RuntimeError(tr("msg.plotly_missing")) from exc

        v = render["velocity"]
        y = render["y_data"]
        model = render.get("model")
        # Rejilla densa del modelo/componentes (curva de ajuste suave). Si no
        # está disponible, se cae a la rejilla de los datos.
        mv = render.get("model_v")
        if mv is None:
            mv = v
        components = render.get("components") or []
        style = render.get("style") or get_style(self.plot_style_name)
        show_residual = bool(render.get("show_residual", True)) and model is not None
        residual = render.get("residual")
        if residual is None and model is not None:
            residual = y - model
        dist_result = self.runtime_results.distribution_result if getattr(self, "is_distribution_mode", False) else None
        dist_view = distribution_result_view(dist_result) if dist_result is not None else None
        show_distribution = bool(dist_view is not None)
        is_2d_dist = show_distribution and dist_view.is_2d()
        rows = 1 + (1 if show_residual else 0) + (1 if show_distribution else 0)
        row_heights = [0.62]
        if show_residual:
            row_heights.append(0.18)
        if show_distribution:
            row_heights.append(0.38 if is_2d_dist else 0.20)
        fig = make_subplots(
            rows=rows, cols=1, shared_xaxes=False,
            row_heights=row_heights, vertical_spacing=0.055,
        )
        # WebGL (scattergl) para que muchos puntos se dibujen con fluidez.
        fig.add_trace(
            go.Scattergl(
                x=v, y=y, mode="markers", name=tr("plot.legend_data"),
                marker=dict(color=style.get("data", "#2563eb"), size=6),
                hovertemplate="v=%{x:.5g}<br>y=%{y:.6g}<extra></extra>",
            ),
            row=1, col=1,
        )
        palette = style.get("components_palette") or ("#10b981", "#f59e0b", "#8b5cf6")
        for idx, kind, comp in components:
            param_txt = str(kind) if idx <= 0 else self._plotly_component_param_text(idx)
            comp_name = str(kind) if idx <= 0 else f"{tr(f'kind.{kind}', default=kind)} {idx}"
            comp_color = style.get("dist_line", style.get("model", "#dc2626")) if idx <= 0 else palette[(idx - 1) % len(palette)]
            fig.add_trace(
                go.Scattergl(
                    x=mv, y=comp, mode="lines",
                    name=comp_name,
                    line=dict(color=comp_color, width=1.5, dash="dash"),
                    hovertemplate=(
                        f"{html.escape(param_txt)}<br>"
                        "v=%{x:.5g}<br>y=%{y:.6g}<extra></extra>"
                    ),
                ),
                row=1, col=1,
            )
        if model is not None:
            fig.add_trace(
                go.Scattergl(
                    x=mv, y=model, mode="lines", name=tr("plot.legend_model"),
                    line=dict(color=style.get("model", "#dc2626"), width=2.4),
                    hovertemplate="v=%{x:.5g}<br>modelo=%{y:.6g}<extra></extra>",
                ),
                row=1, col=1,
            )
            if show_residual and residual is not None:
                res_row = 2
                fig.add_trace(
                    go.Scattergl(
                        x=v, y=residual, mode="lines", name=tr("plot.residual_ylabel"),
                        line=dict(color=style.get("res_line", "#7c3aed"), width=1.2),
                        fill="tozeroy", fillcolor="rgba(124,58,237,0.18)",
                        hovertemplate="v=%{x:.5g}<br>res=%{y:.6g}<extra></extra>",
                    ),
                    row=res_row, col=1,
                )
                fig.add_hline(y=0, line_width=1, line_color=style.get("res_zero", "#64748b"), row=res_row, col=1)
                fig.update_yaxes(title_text=tr("plot.residual_ylabel"), row=res_row, col=1)
                fig.update_xaxes(title_text=tr("plot.velocity_xlabel"), row=res_row, col=1)
        if show_distribution:
            dist_row = rows
            if dist_view.is_2d():
                xc, yc, P = dist_view.probability_2d()
                xlbl, ylbl = dist_view.var_labels_2d()
                xv = getattr(dist_result, "x_variable", "bhf")
                yv = getattr(dist_result, "y_variable", "quad")
                _short = {"bhf": "B_HF", "quad": "ΔEQ", "delta": "δ"}
                dist_name = f"P({_short.get(xv, xv)}, {_short.get(yv, yv)})"
                cscale = "Inferno" if (self.plot_style_name == "dark" or
                                       self.color_theme == "dark") else "Viridis"
                fig.add_trace(
                    go.Heatmap(
                        z=P.T.tolist(),     # shape (n_y, n_x) para Plotly
                        x=xc.tolist(),
                        y=yc.tolist(),
                        colorscale=cscale,
                        colorbar=dict(
                            title="P(x,y)",
                            len=0.35, y=0.13,
                            thickness=14,
                        ),
                        name=dist_name,
                        hovertemplate=(
                            f"{xlbl}=%{{x:.4g}}<br>"
                            f"{ylbl}=%{{y:.4g}}<br>"
                            "P=%{z:.5g}<extra></extra>"
                        ),
                    ),
                    row=dist_row, col=1,
                )
                # Contornos superpuestos en la misma celda
                try:
                    fig.add_trace(
                        go.Contour(
                            z=P.T.tolist(), x=xc.tolist(), y=yc.tolist(),
                            contours=dict(coloring="none", showlabels=False),
                            line=dict(color="white", width=0.6),
                            showscale=False, opacity=0.5, name="",
                            hoverinfo="skip",
                        ),
                        row=dist_row, col=1,
                    )
                except Exception:
                    pass
                fig.update_xaxes(title_text=xlbl, row=dist_row, col=1)
                fig.update_yaxes(title_text=ylbl, row=dist_row, col=1)
            else:
                xdist, pdist = dist_view.probability_curve()
                dist_name = "P(ΔEQ)" if self.dist_variable == "quad" else "P(BHF)"
                fig.add_trace(
                    go.Scatter(
                        x=xdist, y=pdist, mode="lines", name=dist_name,
                        line=dict(color="#2563eb", width=2.2),
                        fill="tozeroy", fillcolor="rgba(37,99,235,0.22)",
                        hovertemplate="x=%{x:.5g}<br>P=%{y:.6g}<extra></extra>",
                    ),
                    row=dist_row, col=1,
                )
                xlabel = (tr("plot.distribution_xlabel_deq") if self.dist_variable == "quad"
                          else tr("plot.distribution_xlabel_bhf"))
                fig.update_xaxes(title_text=xlabel, row=dist_row, col=1)
                fig.update_yaxes(title_text=dist_name, row=dist_row, col=1)
        if not show_residual:
            fig.update_xaxes(title_text=tr("plot.velocity_xlabel"), row=1, col=1)
        template = "plotly_dark" if self.plot_style_name == "dark" or self.color_theme == "dark" else "plotly_white"
        subtitle = self._plotly_subtitle()
        title = tr("plot.title_discrete") + (f"<br><sup>{html.escape(subtitle)}</sup>" if subtitle else "")
        fig.update_layout(
            template=template,
            title=title,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
            margin=dict(l=60, r=24, t=86, b=56),
        )
        fig.update_yaxes(title_text=tr("plot.transmission_ylabel"), row=1, col=1)
        if getattr(self, "_minima_edit_mode", False) and self._minima_entries:
            self._add_minima_overlay(fig, go, v, y)
        return fig

    def _add_minima_overlay(self, fig, go, v, y) -> None:
        """Dibuja los mínimos detectados como marcadores clicables en Plotly.

        Los incluidos van resaltados; los excluidos, atenuados. El número de
        contribuciones (>1) se muestra como una etiqueta ``×n`` sobre el marcador.
        ``customdata`` lleva el índice de cada mínimo para identificarlo al clicar.
        """
        n = int(np.asarray(y).size)
        for included in (False, True):
            xs, ys, texts, custom = [], [], [], []
            for k, e in enumerate(self._minima_entries):
                if bool(e["included"]) is not included:
                    continue
                ch = int(e["i"])
                yv = float(y[ch]) if 0 <= ch < n else float(np.interp(e["pos"], v, y))
                xs.append(float(e["pos"]))
                ys.append(yv)
                texts.append(f"×{int(e['count'])}" if int(e["count"]) > 1 else "")
                custom.append(k)
            if not xs:
                continue
            if included:
                marker = dict(color="#dc2626", size=13, symbol="circle",
                              line=dict(color="#ffffff", width=1.5))
                name = tr("minima.included", default="Mínimos (incluidos)")
            else:
                marker = dict(color="rgba(148,163,184,0.55)", size=11,
                              symbol="circle-open", line=dict(color="#94a3b8", width=1.5))
                name = tr("minima.excluded", default="Mínimos (excluidos)")
            fig.add_trace(
                go.Scatter(
                    x=xs, y=ys, mode="markers+text", name=name,
                    marker=marker, customdata=custom,
                    text=texts, textposition="top center",
                    textfont=dict(color="#dc2626", size=12),
                    hovertemplate="v=%{x:.4f}<extra></extra>",
                ),
                row=1, col=1,
            )

    def _plotly_subtitle(self) -> str:
        parts: list[str] = []
        if self.file.path:
            parts.append(self.file.path.name)
        if self.runtime_results.fit_result is not None:
            view = discrete_result_view(self.runtime_results.fit_result)
            stats = {metric.key: metric.value for metric in view.metrics(keys=("red_chi2", "aic", "bic"))}
            if "red_chi2" in stats:
                parts.append(f"χ²red={float(stats['red_chi2']):.5g}")
            if "aic" in stats:
                parts.append(f"AIC={float(stats['aic']):.5g}")
            if "bic" in stats:
                parts.append(f"BIC={float(stats['bic']):.5g}")
        return " · ".join(parts)

    def _plotly_component_param_text(self, idx: int) -> str:
        if idx < 1 or idx > len(self.components_panels):
            return f"Comp. {idx}"
        comp_state = self.components_panels[idx - 1].to_view_state()
        fields = [f"Comp. {idx} ({tr(f'kind.{comp_state.kind}', default=comp_state.kind)})"]
        for name, label in (("delta", "δ"), ("quad", "ΔEQ"), ("bhf", "BHF"), ("gamma1", "Γ"), ("depth", "prof")):
            if name in comp_state.values:
                fields.append(f"{label}={comp_state.value(name):.5g}")
        return " · ".join(fields)

    def _plotly_metadata_html(self) -> str:
        rows: list[tuple[str, str]] = [
            (tr("report.program", default="Programa"), f"{APP_NAME} v{APP_VERSION} (Qt)"),
        ]
        if self.file.path:
            rows.append((tr("report.file", default="Fichero"), self.file.path.name))
        if self.file.velocity is not None:
            rows.append(("Canales doblados", str(self.file.velocity.size)))
        rows.append(("Modo", "P(ΔEQ)" if self.mode_combo.currentIndex() == 2 else ("P(BHF)" if self.mode_combo.currentIndex() == 1 else "Discreto")))
        calib_state = self.calib.to_view_state()
        rows.append(("Perfil", calib_state.line_profile))
        rows.append(("Verosimilitud", self.likelihood))
        rows.append(("Pérdida", self.robust_loss))
        if self.runtime_results.fit_result is not None:
            view = discrete_result_view(self.runtime_results.fit_result)
            for metric in view.metrics(keys=("chi2", "red_chi2", "aic", "bic")):
                rows.append((metric.key, f"{float(metric.value):.6g}"))
        comp_lines = [
            self._plotly_component_param_text(comp_state.idx)
            for comp_state in (cp.to_view_state() for cp in self.components_panels)
            if comp_state.enabled
        ]
        table = "".join(
            f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
            for k, v in rows
        )
        comps = "".join(f"<li>{html.escape(line)}</li>" for line in comp_lines)
        return (
            "<section class='metadata'>"
            f"<h2>{html.escape(tr('plotly.metadata_title', default='Metadatos del ajuste'))}</h2>"
            f"<table>{table}</table>"
            f"<h3>{html.escape(tr('plotly.components_title', default='Componentes activos'))}</h3>"
            f"<ul>{comps}</ul>"
            "</section>"
        )

    def _plotly_html_document(self) -> str:
        fig = self._current_plotly_figure()
        body = fig.to_html(
            include_plotlyjs=True,
            full_html=False,
            config={"responsive": True, "displaylogo": False, "toImageButtonOptions": {"format": "png", "scale": 2}},
        )
        bg = "#111827" if self.color_theme == "dark" else "#ffffff"
        fg = "#e5e7eb" if self.color_theme == "dark" else "#111827"
        border = "#374151" if self.color_theme == "dark" else "#d1d5db"
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{html.escape(tr('plotly.title'))}</title>"
            "<style>"
            f"body{{margin:0;background:{bg};color:{fg};font-family:system-ui,Segoe UI,sans-serif;}}"
            "main{padding:10px 14px 24px 14px;}"
            f".metadata{{margin:12px 8px 4px 8px;padding:12px;border:1px solid {border};border-radius:10px;}}"
            ".metadata h2,.metadata h3{margin:0.2rem 0 0.5rem 0;}"
            ".metadata table{border-collapse:collapse;margin-bottom:0.75rem;}"
            ".metadata th{text-align:left;padding:3px 12px 3px 0;}"
            ".metadata td{padding:3px 0;}"
            "</style></head><body><main>"
            f"{body}"
            "</main></body></html>"
        )

    def _cleanup_plotly_temp_files(self) -> None:
        for path in list(getattr(self, "_plotly_temp_files", [])):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        self._plotly_temp_files = []

    def _load_plotly_html(self, html_text: str) -> None:
        """Carga HTML de Plotly mediante fichero temporal, no con setHtml().

        QWebEngineView.setHtml() convierte el contenido en una URL de datos y
        Qt WebEngine tiene un límite práctico de tamaño. Como plotly.js embebido
        mide varios MB, setHtml() puede terminar en una página en blanco (sin
        datos ni ejes). Cargar un fichero local evita ese límite.
        """
        if self.plotly_view is None:
            return
        tmp_dir = CONFIG_DIR / "plotly"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="plotly_", suffix=".html", dir=str(tmp_dir))
        path = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(html_text)
        self._plotly_temp_files.append(path)
        # Mantén solo unos pocos ficheros vivos para no borrar el que se acaba
        # de pedir al motor web, pero evita acumular muchos en sesiones largas.
        while len(self._plotly_temp_files) > 6:
            old = self._plotly_temp_files.pop(0)
            try:
                old.unlink(missing_ok=True)
            except Exception:
                pass
        self.plotly_view.load(QtCore.QUrl.fromLocalFile(str(path)))

    def _is_plotly_tab_active(self) -> bool:
        return hasattr(self, "plot_tabs") and self.plot_tabs.currentWidget() is getattr(self, "plotly_tab", None)

    def _schedule_plotly_update(self) -> None:
        if self._is_plotly_tab_active() and getattr(self, "_plotly_available", False):
            self._plotly_update_timer.start()

    def _plotly_page_template(self, theme: str) -> str:
        """HTML que se carga UNA sola vez: plotly.js + función de refresco.

        Los datos se inyectan luego con ``window.__render`` (Plotly.react), de
        modo que cada actualización no recarga la página ni vuelve a parsear
        plotly.js — solo redibuja de forma incremental lo que cambia.
        """
        import plotly.offline as _poff
        plotlyjs = _poff.get_plotlyjs()
        bg = "#111827" if theme == "dark" else "#ffffff"
        fg = "#e5e7eb" if theme == "dark" else "#111827"
        border = "#374151" if theme == "dark" else "#d1d5db"
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{html.escape(tr('plotly.title'))}</title>"
            "<style>"
            "html,body{height:100%;}"
            f"body{{margin:0;background:{bg};color:{fg};font-family:system-ui,Segoe UI,sans-serif;}}"
            "main{padding:4px 8px;height:100%;box-sizing:border-box;display:flex;flex-direction:column;}"
            "#plot{width:100%;flex:1 1 auto;min-height:0;}"
            f".metadata{{margin:12px 8px 4px 8px;padding:12px;border:1px solid {border};border-radius:10px;}}"
            ".metadata h2,.metadata h3{margin:0.2rem 0 0.5rem 0;}"
            ".metadata table{border-collapse:collapse;margin-bottom:0.75rem;}"
            ".metadata th{text-align:left;padding:3px 12px 3px 0;}"
            ".metadata td{padding:3px 0;}"
            "</style>"
            "<script src='qrc:///qtwebchannel/qwebchannel.js'></script>"
            "<script>" + plotlyjs + "</script></head>"
            "<body><main><div id='plot'></div></main><script>"
            "var CFG={responsive:true,displaylogo:false,"
            "toImageButtonOptions:{format:'png',scale:2}};"
            "window.__bridge=null;"
            "if(typeof QWebChannel!=='undefined'&&typeof qt!=='undefined'){"
            "new QWebChannel(qt.webChannelTransport,function(ch){"
            "window.__bridge=ch.objects.minima;});}"
            "window.__clickBound=false;"
            "window.__render=function(fig,meta){"
            "var gd=document.getElementById('plot');"
            "Plotly.react(gd,fig.data,fig.layout,CFG);"
            "if(!window.__clickBound){window.__clickBound=true;"
            "gd.on('plotly_click',function(ev){"
            "if(!ev||!ev.points||!ev.points.length)return;"
            "var p=ev.points[0];"
            "if(!window.__bridge)return;"
            "if(p.customdata!==undefined&&p.customdata!==null){"
            "window.__bridge.toggle(p.customdata);return;}"
            "if(p.x!==undefined&&p.x!==null){window.__bridge.add(Number(p.x));}});}"
            "};"
            "</script></body></html>"
        )

    def _on_plotly_loaded(self, ok: bool) -> None:
        self._plotly_loading = False
        self._plotly_page_ready = bool(ok)
        # Al terminar de cargar la plantilla, vuelca el último estado pendiente.
        if ok and self._plotly_pending and self.plotly_view is not None:
            self.plotly_view.page().runJavaScript(self._plotly_pending)
            self._plotly_pending = None

    def _update_plotly_view(self) -> None:
        if not getattr(self, "_plotly_available", False) or self.plotly_view is None:
            if hasattr(self, "plotly_status"):
                self.plotly_status.setText(tr("msg.plotly_webengine_missing"))
            return
        try:
            import plotly.io as _pio
            fig = self._current_plotly_figure()
            fig_json = _pio.to_json(fig)
            payload = f"window.__render({fig_json},null);"
            theme = "dark" if self.color_theme == "dark" else "light"
            if self._plotly_loading and self._plotly_theme == theme:
                # La plantilla aún se está cargando: solo se actualiza el estado
                # pendiente (sin recargar plotly.js otra vez).
                self._plotly_pending = payload
            elif not self._plotly_page_ready or self._plotly_theme != theme:
                # Primera vez (o cambio de tema): carga la plantilla y deja el
                # estado pendiente para aplicarlo cuando termine la carga.
                self._plotly_theme = theme
                self._plotly_page_ready = False
                self._plotly_loading = True
                self._plotly_pending = payload
                self._load_plotly_html(self._plotly_page_template(theme))
            else:
                # Refresco incremental: solo se envían los datos nuevos.
                self.plotly_view.page().runJavaScript(payload)
            if hasattr(self, "plotly_status"):
                self.plotly_status.setText(tr("status.plotly_updated", default="Plotly actualizado."))
        except Exception as exc:
            # Fuerza recargar la plantilla en el próximo intento.
            self._plotly_page_ready = False
            self._plotly_loading = False
            self._plotly_theme = None
            self._plotly_pending = None
            if hasattr(self, "plotly_status"):
                self.plotly_status.setText(str(exc))

    # ── Edición semi-manual de mínimos ──────────────────────────────────
    def _build_minima_editor(self) -> QtWidgets.QWidget:
        """Panel lateral con la lista de mínimos detectados (editable)."""
        box = QtWidgets.QGroupBox(tr("minima.editor_title", default="Mínimos detectados"))
        box.setMinimumWidth(240)
        lay = QtWidgets.QVBoxLayout(box)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        hint = QtWidgets.QLabel(tr(
            "minima.editor_hint",
            default="Marca/desmarca los mínimos a usar e indica cuántas "
                    "contribuciones tiene cada uno. En Plotly, clic sobre el "
                    "espectro añade un mínimo y clic sobre/cerca de un marcador "
                    "lo activa o desactiva."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#64748b;font-size:11px;")
        lay.addWidget(hint)

        self.btn_minima_detect = QtWidgets.QPushButton(
            tr("minima.redetect", default="Volver a detectar"))
        self.btn_minima_detect.clicked.connect(lambda _=False: self.on_edit_minima(redetect=True))
        lay.addWidget(self.btn_minima_detect)

        self._minima_list_container = QtWidgets.QWidget()
        self._minima_list_layout = QtWidgets.QVBoxLayout(self._minima_list_container)
        self._minima_list_layout.setContentsMargins(0, 0, 0, 0)
        self._minima_list_layout.setSpacing(2)
        self._minima_list_layout.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._minima_list_container)
        lay.addWidget(scroll, stretch=1)

        self.minima_count_label = QtWidgets.QLabel("")
        self.minima_count_label.setStyleSheet("font-size:11px;")
        lay.addWidget(self.minima_count_label)

        btns = QtWidgets.QHBoxLayout()
        self.btn_minima_propose = QtWidgets.QPushButton(
            tr("minima.propose", default="Proponer ajuste"))
        self.btn_minima_propose.clicked.connect(lambda _=False: self.on_propose_from_minima())
        self.btn_minima_done = QtWidgets.QPushButton(
            tr("minima.done", default="Cerrar edición"))
        self.btn_minima_done.clicked.connect(lambda _=False: self._exit_minima_edit())
        btns.addWidget(self.btn_minima_propose)
        btns.addWidget(self.btn_minima_done)
        lay.addLayout(btns)
        return box

    def _setup_minima_webchannel(self) -> None:
        """Conecta el puente JS↔Python para clicar marcadores en Plotly."""
        if self.plotly_view is None:
            return
        try:
            from PySide6.QtWebChannel import QWebChannel
            self._minima_bridge = MinimaBridge()
            self._minima_bridge.toggled.connect(self._on_minima_marker_clicked)
            self._minima_bridge.added.connect(self._on_minima_plot_clicked)
            channel = QWebChannel(self.plotly_view.page())
            channel.registerObject("minima", self._minima_bridge)
            self.plotly_view.page().setWebChannel(channel)
        except Exception:
            # Sin QWebChannel la lista lateral sigue siendo plenamente funcional.
            self._minima_bridge = None

    def on_edit_minima(self, redetect: bool = True) -> None:
        """Entra en el modo de edición semi-manual de mínimos."""
        if self.file.velocity is None or self.file.y_data is None:
            QtWidgets.QMessageBox.information(
                self, tr("minima.editor_title", default="Mínimos detectados"),
                tr("msg.no_file", default="Carga primero un espectro."))
            return
        if not getattr(self, "_plotly_available", False):
            # Sin la vista Plotly interactiva no hay edición visual: se recurre
            # a la inicialización automática clásica.
            self.on_init_from_minima(show_message=True)
            return
        if redetect or not self._minima_entries:
            peaks, baseline, slope = self.detect_absorption_minima()
            self._minima_baseline = baseline
            self._minima_slope = slope
            self._minima_entries = [
                {"i": int(p["i"]), "pos": float(p["pos"]), "depth": float(p["depth"]),
                 "width": float(p["width"]), "smooth_depth": float(p.get("smooth_depth", p["depth"])),
                 "included": True, "count": 1}
                for p in peaks
            ]
        if not self._minima_entries:
            QtWidgets.QMessageBox.information(
                self, tr("minima.editor_title", default="Mínimos detectados"),
                tr("msg.auto_minima_none", default="No se detectaron mínimos."))
            return
        self._minima_edit_mode = True
        self._populate_minima_list()
        self.minima_editor.show()
        if hasattr(self, "plot_tabs"):
            self.plot_tabs.setCurrentWidget(self.plotly_tab)
        self._update_plotly_view()

    def _populate_minima_list(self) -> None:
        """Reconstruye las filas de la lista a partir de ``_minima_entries``."""
        # Limpia las filas previas (deja el stretch final).
        while self._minima_list_layout.count() > 1:
            item = self._minima_list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._minima_rows = []
        for k, e in enumerate(self._minima_entries):
            row = QtWidgets.QWidget()
            rl = QtWidgets.QHBoxLayout(row)
            rl.setContentsMargins(2, 0, 2, 0)
            rl.setSpacing(6)
            chk = QtWidgets.QCheckBox(f"v={e['pos']:+.3f}")
            chk.setChecked(bool(e["included"]))
            chk.setToolTip(tr("minima.include_tip", default="Usar este mínimo en la propuesta"))
            chk.toggled.connect(lambda state, idx=k: self._on_minima_row_changed(idx, included=state))
            spin = QtWidgets.QSpinBox()
            spin.setRange(1, 4)
            spin.setValue(int(e["count"]))
            spin.setPrefix("×")
            spin.setToolTip(tr("minima.count_tip", default="Nº de contribuciones bajo este mínimo"))
            spin.valueChanged.connect(lambda val, idx=k: self._on_minima_row_changed(idx, count=val))
            depth = QtWidgets.QLabel(f"{e['depth']*100:.1f}%")
            depth.setStyleSheet("color:#64748b;font-size:11px;")
            rl.addWidget(chk, stretch=1)
            rl.addWidget(depth)
            rl.addWidget(spin)
            self._minima_list_layout.insertWidget(self._minima_list_layout.count() - 1, row)
            self._minima_rows.append({"check": chk, "spin": spin})
        self._update_minima_count_label()

    def _on_minima_row_changed(self, idx: int, included: bool | None = None,
                               count: int | None = None) -> None:
        if idx < 0 or idx >= len(self._minima_entries):
            return
        if included is not None:
            self._minima_entries[idx]["included"] = bool(included)
        if count is not None:
            self._minima_entries[idx]["count"] = int(count)
        self._update_minima_count_label()
        self._update_plotly_view()

    def _on_minima_marker_clicked(self, idx: int) -> None:
        """Clic en un marcador del gráfico: alterna incluir/excluir y sincroniza."""
        if idx < 0 or idx >= len(self._minima_entries):
            return
        new_state = not self._minima_entries[idx]["included"]
        self._minima_entries[idx]["included"] = new_state
        if idx < len(self._minima_rows):
            chk = self._minima_rows[idx]["check"]
            chk.blockSignals(True)
            chk.setChecked(new_state)
            chk.blockSignals(False)
        self._update_minima_count_label()
        self._update_plotly_view()

    def _on_minima_plot_clicked(self, x: float) -> None:
        """Clic sobre el gráfico en modo edición: añade un mínimo manual."""
        if not getattr(self, "_minima_edit_mode", False):
            return
        if self.file.velocity is None or self.file.y_data is None:
            return
        v = np.asarray(self.file.velocity, dtype=float)
        y = np.asarray(self.file.y_data, dtype=float)
        if v.size == 0 or y.size == 0:
            return
        idx = int(np.argmin(np.abs(v - float(x))))
        # Si se clica sobre/cerca de un mínimo existente, alterna incluir/excluir
        # en vez de crear un duplicado. Así basta un clic para desactivarlo.
        if v.size > 1:
            dv = float(np.nanmedian(np.abs(np.diff(np.sort(v)))))
        else:
            dv = 0.05
        tol = max(1.5 * abs(dv), 0.05)
        if self._minima_entries:
            distances = [abs(float(e["pos"]) - float(x)) for e in self._minima_entries]
            nearest = int(np.argmin(distances))
            if distances[nearest] <= tol or abs(int(self._minima_entries[nearest]["i"]) - idx) <= 1:
                self._on_minima_marker_clicked(nearest)
                return
        calib_state = self.calib.to_view_state()
        baseline = float(getattr(self, "_minima_baseline", calib_state.baseline))
        slope = float(getattr(self, "_minima_slope", calib_state.slope))
        depth = max(0.0, baseline + slope * float(v[idx]) - float(y[idx]))
        self._minima_entries.append({
            "i": idx,
            "pos": float(v[idx]),
            "depth": depth,
            "width": 0.2,
            "smooth_depth": depth,
            "included": True,
            "count": 1,
        })
        self._minima_entries.sort(key=lambda e: float(e["pos"]))
        self._populate_minima_list()
        self._update_plotly_view()

    def _update_minima_count_label(self) -> None:
        if not hasattr(self, "minima_count_label"):
            return
        n_inc = sum(1 for e in self._minima_entries if e["included"])
        n_contrib = sum(int(e["count"]) for e in self._minima_entries if e["included"])
        self.minima_count_label.setText(tr(
            "minima.count_summary",
            default="{inc}/{tot} mínimos · {contrib} contribuciones",
            inc=n_inc, tot=len(self._minima_entries), contrib=n_contrib))

    def _exit_minima_edit(self) -> None:
        self._minima_edit_mode = False
        if hasattr(self, "minima_editor"):
            self.minima_editor.hide()
        self._update_plotly_view()

    def on_propose_from_minima(self) -> None:
        """Construye la propuesta de componentes a partir de los mínimos curados."""
        included = [e for e in self._minima_entries if e["included"]]
        if not included:
            QtWidgets.QMessageBox.information(
                self, tr("minima.propose", default="Proponer ajuste"),
                tr("minima.none_selected", default="Marca al menos un mínimo."))
            return
        peaks_override = [
            {"i": float(e["i"]), "pos": e["pos"], "depth": e["depth"],
             "smooth_depth": e["smooth_depth"], "width": e["width"]}
            for e in included
        ]
        multiplicities = {int(e["i"]): int(e["count"]) for e in included}
        ok = self.on_init_from_minima(show_message=True, peaks_override=peaks_override,
                                      multiplicities=multiplicities)
        if ok:
            self._exit_minima_edit()

    def on_open_plotly(self) -> None:
        if hasattr(self, "plot_tabs"):
            self.plot_tabs.setCurrentWidget(self.plotly_tab)
        self._update_plotly_view()

    def on_export_plotly_html(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("file.export_plotly_html"), str(ROOT / "mossbauer_plotly.html"),
            "HTML (*.html);;All (*.*)")
        if not path:
            return
        try:
            out = Path(path)
            if out.suffix.lower() not in (".html", ".htm"):
                out = out.with_suffix(".html")
            out.write_text(self._plotly_html_document(), encoding="utf-8")
            self.statusBar().showMessage(tr("status.plotly_exported", path=str(out)), 6000)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, tr("plotly.title"), str(exc))
