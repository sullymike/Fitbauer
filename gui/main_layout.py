"""Construcción del layout principal de la ventana Qt."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

from mossbauer_i18n import tr
from core.constants import APP_NAME, APP_AUTHOR, APP_DEPARTMENT, LINE_POS_33T
from gui.branding import _logo_pixmap
from gui.canvas import SpectrumCanvas
from gui.distribution_panel import DistributionPanel
from gui.panels import CalibrationPanel, ComponentPanel, InfoPanel

MAX_QT_COMPONENTS = 6


class MainLayoutMixin:
    # ── Construcción de la UI ────────────────────────────────────────────
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self); self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central); layout.setContentsMargins(4, 4, 4, 4)
        # El layout central NO debe redimensionar la ventana según su contenido:
        # al añadir/quitar componentes (apilado) el tamaño global se mantiene.
        layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        # Mínimo de ventana fijo e independiente del contenido.
        self.setMinimumSize(900, 520)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal); layout.addWidget(splitter)
        self._main_splitter = splitter

        # ── Columna izquierda: cabecera + file info + calibración + sextete ─
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left); lv.setContentsMargins(6, 6, 6, 6); lv.setSpacing(8)
        self._left_panels_layout = lv

        # Módulo cabecera (igual que en Tk): banner con nombre, subtítulo y autor.
        self.header_box = QtWidgets.QFrame()
        self.header_box.setObjectName("AppHeader")
        hb = QtWidgets.QHBoxLayout(self.header_box)
        hb.setContentsMargins(12, 8, 12, 8); hb.setSpacing(10)
        self.header_logo = QtWidgets.QLabel()
        _hpix = _logo_pixmap(54)
        if _hpix is not None:
            self.header_logo.setPixmap(_hpix)
            hb.addWidget(self.header_logo, 0, QtCore.Qt.AlignVCenter)
        _header_text = QtWidgets.QVBoxLayout(); _header_text.setSpacing(1)
        self.header_title = QtWidgets.QLabel(APP_NAME)
        self.header_title.setObjectName("AppHeaderTitle")
        self.header_title.setWordWrap(True)
        self._header_sub_labels = [
            QtWidgets.QLabel(tr("main.subtitle")),
            QtWidgets.QLabel(APP_AUTHOR),
            QtWidgets.QLabel(APP_DEPARTMENT),
        ]
        _header_text.addWidget(self.header_title)
        for lbl in self._header_sub_labels:
            lbl.setWordWrap(True)
            _header_text.addWidget(lbl)
        hb.addLayout(_header_text, 1)
        lv.addWidget(self.header_box)

        self.file_box = QtWidgets.QGroupBox(tr("controls.file_box"))
        fb = QtWidgets.QVBoxLayout(self.file_box)
        self.file_label = QtWidgets.QLabel("—"); self.file_label.setWordWrap(True)
        fb.addWidget(self.file_label)
        self.calib_label = QtWidgets.QLabel("")
        self.calib_label.setWordWrap(True)
        self.calib_label.setStyleSheet("color: #0e7490; font-size: 9pt;")
        fb.addWidget(self.calib_label)
        # Clic derecho sobre el cuadro de fichero → menú "usar como calibración".
        self.file_box.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.file_box.customContextMenuRequested.connect(self._show_file_box_menu)
        self.file_label.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.file_label.customContextMenuRequested.connect(self._show_file_box_menu)
        lv.addWidget(self.file_box)

        # Panel de referencia con las posiciones de las líneas Fe-57 a 33 T.
        ref_box = QtWidgets.QGroupBox(tr("controls.reference_box"))
        rb = QtWidgets.QVBoxLayout(ref_box)
        pos_str = ", ".join(f"{x:+.3f}" for x in LINE_POS_33T)
        ref_lbl = QtWidgets.QLabel(tr("controls.reference_lines", positions=pos_str))
        ref_lbl.setWordWrap(True)
        rb.addWidget(ref_lbl)
        lv.addWidget(ref_box)

        # Selector de modo (discreto / P(BHF)) y controles de simulación.
        self.sim_controls_box = QtWidgets.QGroupBox("Simulación / ajuste")
        sim_lay = QtWidgets.QVBoxLayout(self.sim_controls_box)
        mode_row = QtWidgets.QHBoxLayout()
        mode_row.addWidget(QtWidgets.QLabel(tr("controls.fit_mode_hint").split(":")[0] + ":"))
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems([
            tr("options.discrete_sextets"),
            tr("options.distribution_bhf"),
            "P(ΔEQ)",
            "P(IS)",
            "P(BHF, ΔEQ) 2D",
            "P(IS, ΔEQ) 2D",
            "P(BHF, IS) 2D",
        ])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo, stretch=1)
        sim_lay.addLayout(mode_row)

        ncomp_row = QtWidgets.QHBoxLayout()
        ncomp_row.addWidget(QtWidgets.QLabel(tr("sim.n_components", default="Componentes:")))
        self.n_components_spin = QtWidgets.QSpinBox()
        self.n_components_spin.setRange(1, MAX_QT_COMPONENTS)
        self.n_components_spin.setValue(1)
        self.n_components_spin.setToolTip(
            tr("sim.n_components", default="Número de componentes/sextetes activos"))
        self.n_components_spin.valueChanged.connect(self._on_n_components_changed)
        ncomp_row.addWidget(self.n_components_spin)
        ncomp_row.addWidget(QtWidgets.QLabel(f"(máx. {MAX_QT_COMPONENTS})"))
        ncomp_row.addStretch(1)
        sim_lay.addLayout(ncomp_row)

        action_grid = QtWidgets.QGridLayout()
        action_grid.setContentsMargins(0, 0, 0, 0)
        action_grid.setHorizontalSpacing(6)
        action_grid.setVerticalSpacing(4)
        self.btn_sim_fit = QtWidgets.QPushButton(tr("fit.run"))
        self.btn_sim_free_all = QtWidgets.QPushButton(tr("fit.free_all"))
        self.btn_sim_auto_min = QtWidgets.QPushButton(tr("fit.auto_from_minima"))
        self.btn_sim_ai = QtWidgets.QPushButton(tr("fit.ollama_start"))
        for pos, btn in enumerate((self.btn_sim_fit, self.btn_sim_free_all,
                                   self.btn_sim_auto_min, self.btn_sim_ai)):
            action_grid.addWidget(btn, pos // 2, pos % 2)
        self.btn_sim_fit.clicked.connect(self.on_fit)
        self.btn_sim_free_all.clicked.connect(lambda: self._set_all_fixed(False))
        self.btn_sim_auto_min.clicked.connect(lambda _checked=False: self.on_auto_fit_from_minima())
        self.btn_sim_ai.clicked.connect(self.on_ai_summary)
        self._set_quick_action_buttons_enabled(False)
        sim_lay.addLayout(action_grid)

        self.calib = CalibrationPanel()
        lv.addWidget(self.calib)

        # Área de componentes con disposición adaptativa, igual que el panel
        # Tk modular: los sextetes se apilan verticalmente cuando hay espacio
        # debajo y solo pasan a pestañas cuando ya no caben. El combo superior
        # conserva la mejora Qt para elegir Discreto / P(BHF) / P(ΔEQ).
        self.dist_panel = DistributionPanel()
        self.components_panels: list[ComponentPanel] = []
        for i in range(1, MAX_QT_COMPONENTS + 1):
            self.components_panels.append(ComponentPanel(idx=i))

        # Contenedor que alberga las dos disposiciones intercambiables.
        self.comp_area = QtWidgets.QWidget()
        comp_area_lay = QtWidgets.QVBoxLayout(self.comp_area)
        comp_area_lay.setContentsMargins(0, 0, 0, 0)
        comp_area_lay.setSpacing(4)

        # Disposición en pestañas (QTabWidget).
        self.comp_tabs = QtWidgets.QTabWidget()
        comp_area_lay.addWidget(self.comp_tabs)

        # Disposición apilada (QVBoxLayout con envolturas tituladas).
        self.comp_stack = QtWidgets.QWidget()
        self._comp_stack_layout = QtWidgets.QVBoxLayout(self.comp_stack)
        self._comp_stack_layout.setContentsMargins(0, 0, 0, 0)
        self._comp_stack_layout.setSpacing(4)
        self._comp_stack_frames: dict[int, QtWidgets.QGroupBox] = {}
        comp_area_lay.addWidget(self.comp_stack)

        self._using_tabs: bool | None = None  # fuerza la primera construcción
        sim_lay.addWidget(self.comp_area)

        self.dist_panel.paramChanged.connect(self._on_model_param_changed)
        self.dist_panel.loadFixedRequested.connect(self._on_load_fixed_distribution)
        self.dist_panel.lcurve_link.clicked.connect(self.on_lcurve)
        self.dist_panel.use_sharp.toggled.connect(self._set_dist_use_sharp)
        self._rebuild_component_area(use_tabs=False)
        self._sync_component_count(1)
        lv.addWidget(self.sim_controls_box)
        lv.addStretch(1)

        scroll = QtWidgets.QScrollArea(); scroll.setWidget(left); scroll.setWidgetResizable(True)
        self._left_scroll = scroll
        splitter.addWidget(scroll)

        # ── Centro: canvas + toolbar + panel de info ─────────────────────
        center = QtWidgets.QWidget()
        cv = QtWidgets.QVBoxLayout(center); cv.setContentsMargins(0, 0, 0, 0)
        self._center_top_widget = QtWidgets.QWidget(center)
        self._center_top_layout = QtWidgets.QVBoxLayout(self._center_top_widget)
        self._center_top_layout.setContentsMargins(6, 6, 6, 0)
        self._center_top_layout.setSpacing(8)
        self.canvas = SpectrumCanvas(center)
        self.toolbar = NavigationToolbar(self.canvas, center)
        self.info_panel = InfoPanel()
        self._center_bottom_widget = QtWidgets.QWidget(center)
        self._center_bottom_layout = QtWidgets.QVBoxLayout(self._center_bottom_widget)
        self._center_bottom_layout.setContentsMargins(6, 0, 6, 6)
        self._center_bottom_layout.setSpacing(8)

        self.plot_tabs = QtWidgets.QTabWidget(center)
        mpl_tab = QtWidgets.QWidget(self.plot_tabs)
        mpl_lay = QtWidgets.QVBoxLayout(mpl_tab)
        mpl_lay.setContentsMargins(0, 0, 0, 0)
        mpl_lay.addWidget(self.toolbar)
        mpl_lay.addWidget(self.canvas, stretch=1)
        self.plot_tabs.addTab(mpl_tab, tr("plot.tab_matplotlib", default="Matplotlib"))

        self.plotly_tab = QtWidgets.QWidget(self.plot_tabs)
        plotly_lay = QtWidgets.QVBoxLayout(self.plotly_tab)
        plotly_lay.setContentsMargins(6, 6, 6, 6)
        plotly_actions = QtWidgets.QHBoxLayout()
        self.btn_plotly_update = QtWidgets.QPushButton(tr("button.update_plotly", default="Actualizar Plotly"))
        self.btn_plotly_update.clicked.connect(self._update_plotly_view)
        self.btn_plotly_minima = QtWidgets.QPushButton(tr("minima.edit_action", default="Editar mínimos"))
        self.btn_plotly_minima.clicked.connect(lambda _checked=False: self.on_edit_minima())
        self.btn_plotly_export = QtWidgets.QPushButton(tr("file.export_plotly_html"))
        self.btn_plotly_export.clicked.connect(self.on_export_plotly_html)
        self.plotly_status = QtWidgets.QLabel(tr("plotly.initial", default="Abre o actualiza el gráfico interactivo."))
        self.plotly_status.setWordWrap(True)
        plotly_actions.addWidget(self.btn_plotly_update)
        plotly_actions.addWidget(self.btn_plotly_minima)
        plotly_actions.addWidget(self.btn_plotly_export)
        plotly_actions.addWidget(self.plotly_status, stretch=1)
        plotly_lay.addLayout(plotly_actions)
        self.plotly_view = None
        self._plotly_available = False
        # Estado de la página incremental: la plantilla con plotly.js se carga
        # una sola vez; los refrescos usan Plotly.react (no recargan el HTML).
        self._plotly_page_ready = False
        self._plotly_loading = False
        self._plotly_pending: str | None = None
        self._plotly_theme: str | None = None
        # Estado de la edición semi-manual de mínimos.
        self._minima_edit_mode = False
        self._minima_entries: list[dict] = []
        self._minima_rows: list[dict] = []
        self._minima_bridge = None
        # La vista web y el editor de mínimos van lado a lado en un splitter.
        self.plotly_split = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self.plotly_tab)
        self.minima_editor = self._build_minima_editor()
        try:
            from PySide6 import QtWebEngineWidgets as _QtWebEngineWidgets
            self.plotly_view = _QtWebEngineWidgets.QWebEngineView(self.plotly_tab)
            self._plotly_available = True
            self.plotly_view.loadFinished.connect(self._on_plotly_loaded)
            self.plotly_split.addWidget(self.plotly_view)
            self.plotly_split.addWidget(self.minima_editor)
            self.plotly_split.setStretchFactor(0, 1)
            self.plotly_split.setStretchFactor(1, 0)
            self.minima_editor.hide()
            plotly_lay.addWidget(self.plotly_split, stretch=1)
            self._setup_minima_webchannel()
        except Exception:
            self.plotly_placeholder = QtWidgets.QLabel(tr("msg.plotly_webengine_missing"))
            self.plotly_placeholder.setAlignment(QtCore.Qt.AlignCenter)
            self.plotly_placeholder.setWordWrap(True)
            plotly_lay.addWidget(self.plotly_placeholder, stretch=1)
        self.plot_tabs.addTab(self.plotly_tab, tr("plot.tab_plotly", default="Plotly interactivo"))
        self._plotly_update_timer = QtCore.QTimer(self)
        self._plotly_update_timer.setSingleShot(True)
        self._plotly_update_timer.setInterval(0)
        self._plotly_update_timer.timeout.connect(self._update_plotly_view)
        self.plot_tabs.currentChanged.connect(lambda _idx: self._schedule_plotly_update() if self._is_plotly_tab_active() else None)

        cv.addWidget(self._center_top_widget)
        cv.addWidget(self.plot_tabs, stretch=1)
        cv.addWidget(self._center_bottom_widget)
        splitter.addWidget(center)

        # ── Columna derecha: la completan los presets de layout ─────────────
        self._right_column = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(self._right_column)
        rv.setContentsMargins(6, 6, 6, 6); rv.setSpacing(8)
        self._right_panels_layout = rv
        rv.addStretch(1)
        splitter.addWidget(self._right_column)

        self._layout_panel_names = {
            "header": "Cabecera",
            "file_info": "Fichero",
            "info_display": "Info",
            "calibration": "Calibración",
            "reference": "Referencia",
            "sim_controls": "Simulación / ajuste",
        }
        self._layout_panel_widgets = {
            "header": self.header_box,
            "file_info": self.file_box,
            "info_display": self.info_panel,
            "calibration": self.calib,
            "reference": ref_box,
            "sim_controls": self.sim_controls_box,
        }

        splitter.setSizes([430, 1000, 0])
        self._apply_layout_preset(self._layout_preset_with_available_space(self.layout_preset))

        # Conectar señales de cambio para refrescar el plot en vivo
        self.calib.paramChanged.connect(self._on_model_param_changed)
        self.calib.center.valueChanged.connect(self._on_center_value_changed)
        self.calib.absorber_combo.currentIndexChanged.connect(self._sync_absorber_model_from_panel)
        # Al activar "Ajustar Vmax", fijar automáticamente todos los BHF (el
        # ajuste de velocidad exige que el campo hiperfino esté fijo).
        self.calib.fit_velocity.toggled.connect(self._on_fit_velocity_toggled)
        for cp in self.components_panels:
            cp.paramChanged.connect(self._on_model_param_changed)
            # Al cambiar el tipo, el panel puede crecer (p.ej. NeelSize tiene
            # más parámetros que Sextete): revisar si sigue cabiendo apilado.
            cp.type_combo.currentTextChanged.connect(
                lambda _text, self=self: self._check_layout()
            )
