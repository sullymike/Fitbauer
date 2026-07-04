# Plotly + QtWebEngine en Fitbauer — documentación de referencia

> **Estado:** Plotly y QtWebEngine se **retiraron** de la aplicación en la
> v4.13.1 (opción B, adelgazamiento). El gráfico es ahora solo Matplotlib
> (`gui/canvas.py`) y el editor de mínimos vive en `gui/minima_editor.py`. Este
> documento se conserva como **referencia histórica y guía de restauración**:
> describe con detalle exhaustivo cómo estaba integrado Plotly, para poder
> **volver a añadirlo en el futuro** sin arqueología (§13). Recoge dependencias,
> ficheros, símbolos, el flujo de datos, el HTML/JS embebido, los puentes
> WebChannel, el editor de mínimos, el prototipo de arrastre de BHF, la
> exportación, los tests y el empaquetado.
>
> Los apartados en tiempo presente («está», «hace») describen el estado
> **anterior** a la retirada, tal como se conservó para poder reproducirlo.

Referencia del código descrito: rama `main` justo antes de la retirada (v4.13.0).

---

## 1. Resumen ejecutivo

Fitbauer tiene **dos rutas de dibujo** del espectro:

1. **Matplotlib** (`SpectrumCanvas`, en `gui/canvas.py`) — el gráfico **principal y
   estático** que se ve por defecto. Es la fuente de verdad: guarda en
   `self.canvas.last_render` un diccionario con lo último dibujado.
2. **Plotly interactivo** (pestaña «Plotly interactivo») — una vista web
   (`QWebEngineView`) que **reconstruye** una figura Plotly a partir de
   `canvas.last_render`. Añade zoom/pan/hover, exportación a HTML autocontenido,
   el **editor semi-manual de mínimos** (clic para añadir/activar puntos) y el
   **prototipo de arrastre de BHF**.

**Qué justifica su existencia hoy:** el editor de mínimos (interacción clic→modelo
vía WebChannel) y, en menor medida, el HTML compartible. La vista interactiva en sí
duplica en gran parte el canvas Matplotlib.

**Qué cuesta:** `QtWebEngine` (Chromium) es una dependencia pesada — infla el
ejecutable PyInstaller (cientos de MB), ralentiza el arranque y obliga a un
*workaround* anti-*segfault* al cerrar (ver §11). Total: ~725 líneas en
`gui/plotly_tools.py` + fontanería en otros 5 sitios.

---

## 2. Dependencias exactas

| Dónde | Qué |
|---|---|
| `requirements.txt` | Línea `plotly` (sin pin). `PySide6>=6.5` incluye `QtWebEngineWidgets`/`QtWebEngineCore`/`QtWebChannel` como componentes separados y grandes. |
| `Fitbauer.spec` → `hiddenimports` | `'plotly'`, `'plotly.graph_objects'`, `'plotly.subplots'`, `'PySide6.QtWebEngineWidgets'`, `'PySide6.QtWebEngineCore'`. |
| Runtime JS | `qrc:///qtwebchannel/qwebchannel.js` (lo sirve Qt, no es un fichero del repo). |
| `plotly.js` | Se **embebe inline** en el HTML vía `plotly.offline.get_plotlyjs()` (varios MB). No se descarga de CDN (la app funciona sin red). |

`plotly` se importa **de forma diferida** (dentro de los métodos), de modo que si no
está instalado, el resto de la app arranca; la pestaña muestra un aviso.

---

## 3. Inventario de ficheros y símbolos

### 3.1 `gui/plotly_tools.py` — `PlotlyToolsMixin` (núcleo, ~725 líneas)

Mixin compuesto en `MossbauerQtWindow` (ver `gui/window_mixins.py`, posición 23/50
del MRO). Métodos, agrupados por función:

**Construcción de la figura Plotly**
- `_current_plotly_figure()` — **corazón**. Lee `self.canvas.last_render` (dict que
  deja el canvas Matplotlib) y construye una figura `plotly.graph_objects` con
  `make_subplots` (1–3 filas: espectro, residuo, distribución). Traza datos
  (`Scattergl`), comparaciones, componentes (líneas discontinuas), modelo, residuo
  (con relleno), y la distribución (`Scatter` 1D o `Heatmap`+`Contour` 2D). Aplica
  tema (`plotly_dark`/`plotly_white`), título con subtítulo, leyenda horizontal.
  Al final añade, si procede, el *overlay* de mínimos y la línea de arrastre de BHF.
- `_add_minima_overlay(fig, go, v, y)` — marcadores clicables de mínimos
  (incluidos = rojos rellenos; excluidos = grises huecos); `customdata` = índice.
- `_add_bhf_drag_line(fig)` / `_drag_sextet_panel()` / `_bhf_outer_line_x(panel)` —
  prototipo de arrastre (ver §8).
- `_plotly_subtitle()` — subtítulo con nombre de fichero y χ²ᵣ/AIC/BIC.
- `_plotly_component_param_text(idx)` — texto de parámetros de un componente
  (para hover y metadatos).
- `_plotly_metadata_html()` — tabla HTML de metadatos del ajuste. **Definido pero
  actualmente NO se usa** (vestigio de una inyección de metadatos planificada; ver
  §10). La firma `__render(fig, meta)` acepta `meta`, pero siempre se llama con
  `null`.

**Ciclo de vida de la vista web (render incremental)**
- `_plotly_page_template(theme)` — genera el **HTML que se carga una sola vez**:
  `plotly.js` embebido + `qwebchannel.js` + la función JS `window.__render`
  (usa `Plotly.react`). Ver §5 y §6 para el HTML/JS literal.
- `_update_plotly_view()` — construye la figura, la serializa a JSON
  (`plotly.io.to_json`) y la inyecta con `window.__render(<json>, null)` vía
  `runJavaScript`. Gestiona 3 estados: plantilla cargándose (guarda *pending*),
  primera carga o cambio de tema (recarga plantilla) y refresco incremental.
- `_on_plotly_loaded(ok)` — callback de `loadFinished`; vuelca el estado *pending*.
- `_load_plotly_html(html_text)` — escribe el HTML en un **fichero temporal**
  (`CONFIG_DIR/plotly/plotly_*.html`) y hace `view.load(QUrl.fromLocalFile(...))`.
  **Motivo:** `QWebEngineView.setHtml()` convierte el contenido en *data URL* y Qt
  tiene un límite práctico de tamaño; con `plotly.js` (varios MB) `setHtml()`
  produce página en blanco. Mantiene los últimos 6 temporales.
- `_cleanup_plotly_temp_files()` — borra los temporales (se llama en `closeEvent`).
- `_is_plotly_tab_active()` / `_schedule_plotly_update()` — sólo refresca si la
  pestaña Plotly está activa (usa un `QTimer` *single-shot* de intervalo 0).

**Exportación HTML**
- `_plotly_html_document()` — HTML **autocontenido** (`fig.to_html` con
  `include_plotlyjs=True`, `full_html=False`) + estilos. Es lo que se guarda.
- `on_export_plotly_html()` — diálogo de guardado → escribe el HTML.
- `on_open_plotly()` — cambia a la pestaña y refresca.

**Editor semi-manual de mínimos** (ver §7)
- `_build_minima_editor()` — panel lateral (lista editable de mínimos).
- `_setup_minima_webchannel()` — crea `QWebChannel`, registra `MinimaBridge`
  (nombre `"minima"`) y `ModelDragBridge` (nombre `"drag"`).
- `on_edit_minima(redetect=True)` — entra en modo edición; detecta mínimos.
- `_populate_minima_list()` — reconstruye las filas (checkbox incluir + *spin* de
  multiplicidad + etiqueta de profundidad).
- `_on_minima_row_changed(idx, included, count)` — cambios desde la lista lateral.
- `_on_minima_marker_clicked(idx)` — clic en marcador (vía bridge) → alterna
  incluir/excluir y sincroniza la lista.
- `_on_minima_plot_clicked(x)` — clic en zona vacía (vía bridge) → añade un mínimo
  manual (o alterna el más cercano si está dentro de tolerancia).
- `on_propose_from_minima()` — construye la propuesta y llama a
  `on_init_from_minima(peaks_override, multiplicities)`.
- `_update_minima_count_label()` / `_exit_minima_edit()`.

**Prototipo arrastre de BHF** (ver §8)
- `_on_bhf_dragged(x)` — traduce la x arrastrada a BHF y lo aplica en vivo.
- `_on_toggle_bhf_drag(on)` — activa/desactiva el modo.

### 3.2 `gui/bridges.py` — puentes JS↔Python (QObject/Slots)

- `MinimaBridge(QObject)` — señales `toggled(int)`, `added(float)`; slots
  `@Slot(int) toggle(index)` y `@Slot(float) add(x)`. El JS los invoca al clicar.
- `ModelDragBridge(QObject)` — señal `bhf_dragged(float)`; slot
  `@Slot(float) set_bhf_x(x)`. El JS lo invoca al soltar la línea de arrastre.
- `_UiCallBridge(QObject)` — señal `call(object)`. **Definido pero sin uso actual.**

### 3.3 `gui/main_layout.py` — construcción de la pestaña (líneas ~214–269)

Crea `self.plotly_tab`, la barra de botones (`btn_plotly_update`,
`btn_plotly_minima`, `btn_plotly_export`, checkbox `chk_bhf_drag`, etiqueta
`plotly_status`), el `QWebEngineView` (`self.plotly_view`) dentro de un
`QSplitter` junto al editor de mínimos, inicializa el estado incremental
(`_plotly_page_ready/_loading/_pending/_theme`), el estado de mínimos, llama a
`_setup_minima_webchannel()` y crea `_plotly_update_timer`. Si `QtWebEngineWidgets`
no importa, cae a un `QLabel` de aviso (`plotly_placeholder`) y `_plotly_available=False`.

### 3.4 `gui/menu_builder.py` — acciones de menú

- `file.export_plotly_html` → `act_export_plotly` → `on_export_plotly_html`.
- `view.open_plotly` → `on_open_plotly` (pestaña Plotly interactiva).
- `fit.edit_minima` → `act_edit_minima` → `on_edit_minima`.

### 3.5 `mossbauer_qt.py`

- `self._plotly_temp_files: list[Path] = []` (init, ~línea 87).
- `closeEvent` → `self._cleanup_plotly_temp_files()` (~52–58).

### 3.6 `gui/window_mixins.py`

- `from gui.plotly_tools import PlotlyToolsMixin` y su inclusión en la clase
  `WindowMixins` (posición 50).

### 3.7 Otros

- `core/data_io.py`: `CONFIG_DIR = ~/.config/mossbauer_fe33_gui`; los temporales van
  a `CONFIG_DIR/plotly/`.
- `core/params.py`: `plotly_tol_factor` (1.5) y `plotly_tol_min` (0.05) — tolerancia
  para decidir si un clic cae «sobre» un mínimo existente (usado en
  `_on_minima_plot_clicked` vía `effective_peak_detection_specs`).
- `locales/{es,en,fr}/strings.json`: claves `plotly.*` y `minima.*` (ver §10).

---

## 4. Flujo de datos (cómo Plotly deriva del canvas Matplotlib)

Plotly **no** recalcula física. Reproduce lo que el canvas Matplotlib acaba de
dibujar, leyendo `self.canvas.last_render`, un dict con (entre otras) estas claves:

| Clave | Contenido |
|---|---|
| `velocity`, `y_data` | Eje de velocidad y transmisión de los datos. |
| `model`, `model_v` | Curva del modelo y su rejilla densa (si existe). |
| `components` | Lista de `(idx, kind, curva)` de subespectros. |
| `residual`, `show_residual` | Residuo y si mostrarlo. |
| `comparison` | Espectros de comparación superpuestos. |
| `style` | Estilo de gráfico (`core.plot_styles.get_style`). |
| `dist_map_2d` | Resultado de distribución 2D (para el heatmap). |

Secuencia típica de refresco:

```
usuario cambia parámetro / carga / ajusta
  → _on_model_param_changed() / _refresh_plot()
     → canvas.render(...) guarda canvas.last_render
     → _schedule_plotly_update()  (si la pestaña Plotly está activa)
        → _update_plotly_view()
           → fig = _current_plotly_figure()      # lee last_render
           → runJavaScript("window.__render(<fig_json>, null)")   # Plotly.react
```

---

## 5. Renderizado incremental (por qué es rápido)

La clave de rendimiento: **`plotly.js` se parsea una sola vez**. La plantilla HTML
(`_plotly_page_template`) se carga al abrir la pestaña o al cambiar de tema; después,
cada actualización sólo envía el JSON de la figura y llama a `Plotly.react`, que
redibuja de forma incremental sólo lo que cambia (no recarga la página ni re-parsea
`plotly.js`).

Estados que gestiona `_update_plotly_view`:
1. **Plantilla cargándose** y mismo tema → guarda el *payload* en `_plotly_pending`.
2. **Primera vez o cambio de tema** → recarga plantilla y deja *pending*.
3. **Refresco incremental** → `runJavaScript(payload)` directo.

Los temas (`dark`/`light`) usan colores de fondo/texto distintos y plantillas
`plotly_dark`/`plotly_white`.

---

## 6. HTML/JS embebido y puentes WebChannel

### 6.1 Plantilla de la vista interactiva (`_plotly_page_template`)

Versión legible (en el código va minificada como concatenación de strings Python):

```html
<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>{plotly.title}</title>
<style> … html,body,#plot,.metadata … </style>
<script src='qrc:///qtwebchannel/qwebchannel.js'></script>
<script>{plotly.js embebido}</script>
</head>
<body><main><div id='plot'></div></main>
<script>
var CFG = {responsive:true, displaylogo:false,
           edits:{shapePosition:true},                 // ← permite arrastrar formas
           toImageButtonOptions:{format:'png', scale:2}};
window.__bridge = null; window.__dragbridge = null;
if (typeof QWebChannel!=='undefined' && typeof qt!=='undefined') {
  new QWebChannel(qt.webChannelTransport, function(ch){
    window.__bridge     = ch.objects.minima;   // MinimaBridge
    window.__dragbridge = ch.objects.drag;     // ModelDragBridge
  });
}
window.__clickBound = false;
window.__render = function(fig, meta){
  var gd = document.getElementById('plot');
  Plotly.react(gd, fig.data, fig.layout, CFG);
  if (!window.__clickBound){
    window.__clickBound = true;
    // (a) Clic sobre marcador de mínimo o zona vacía → editor de mínimos
    gd.on('plotly_click', function(ev){
      if(!ev||!ev.points||!ev.points.length) return;
      var p = ev.points[0];
      if(!window.__bridge) return;
      if(p.customdata!==undefined && p.customdata!==null){
        window.__bridge.toggle(p.customdata); return;   // alterna incluir/excluir
      }
      if(p.x!==undefined && p.x!==null){
        window.__bridge.add(Number(p.x));               // añade un mínimo
      }
    });
    // (b) Arrastre de una forma: si es la línea 'bhf_drag', envía su x
    gd.on('plotly_relayout', function(ev){
      if(!ev || !window.__dragbridge) return;
      var shapes = gd.layout && gd.layout.shapes; if(!shapes) return;
      for(var key in ev){
        var m = key.match(/^shapes\[(\d+)\]\./);
        if(m){
          var sh = shapes[Number(m[1])];
          if(sh && sh.name==='bhf_drag' && sh.x0!==undefined){
            window.__dragbridge.set_bhf_x(Number(sh.x0)); break;
          }
        }
      }
    });
  }
};
</script></body></html>
```

### 6.2 Registro de los puentes (`_setup_minima_webchannel`)

```python
from PySide6.QtWebChannel import QWebChannel
self._minima_bridge = MinimaBridge()
self._minima_bridge.toggled.connect(self._on_minima_marker_clicked)
self._minima_bridge.added.connect(self._on_minima_plot_clicked)
self._drag_bridge = ModelDragBridge()
self._drag_bridge.bhf_dragged.connect(self._on_bhf_dragged)
channel = QWebChannel(self.plotly_view.page())
channel.registerObject("minima", self._minima_bridge)
channel.registerObject("drag", self._drag_bridge)
self.plotly_view.page().setWebChannel(channel)
```

El JS accede a los objetos como `ch.objects.minima` y `ch.objects.drag`. Los
`@QtCore.Slot` de los bridges se invocan directamente desde JavaScript.

---

## 7. Editor semi-manual de mínimos (la funcionalidad con valor real)

Es la razón de peso para tener interactividad web. Flujo completo:

1. **Entrar**: `on_edit_minima()` (menú `Ajuste > Editar mínimos` o botón).
   Si no hay `QtWebEngine`, cae a `on_init_from_minima(show_message=True)` (versión
   clásica, sin edición visual).
2. **Detectar**: `detect_absorption_minima()` → lista de picos → `_minima_entries`
   (cada uno: canal `i`, `pos` en mm/s, `depth`, `width`, `included`, `count`).
3. **Dibujar**: `_add_minima_overlay` añade dos trazas de marcadores (incluidos /
   excluidos) con `customdata` = índice.
4. **Interactuar**:
   - Clic en un marcador → JS `__bridge.toggle(customdata)` → `MinimaBridge.toggle` →
     `_on_minima_marker_clicked(idx)` → alterna incluir/excluir y sincroniza la
     lista lateral.
   - Clic en zona vacía → JS `__bridge.add(x)` → `MinimaBridge.add` →
     `_on_minima_plot_clicked(x)` → añade un mínimo (o alterna el cercano si está
     dentro de `plotly_tol`).
   - Lista lateral (`_build_minima_editor` / `_populate_minima_list`): checkbox de
     incluir + *spin* `×n` de multiplicidad + profundidad.
5. **Proponer**: `on_propose_from_minima()` → `on_init_from_minima(peaks_override,
   multiplicities)` construye los componentes del modelo.

**Nota para la opción B:** esta es la única pieza que hay que **reimplementar** (no
sólo borrar) si se quita Plotly. Matplotlib puede hacerlo con `mpl_connect`
(`button_press_event`/`pick_event`); ver §12.

---

## 8. Prototipo: arrastrar la línea de BHF (β)

Añadido como prueba de concepto de «ajuste interactivo por arrastre».

- **UI**: checkbox `chk_bhf_drag` («Arrastrar BHF (β)») en la barra de la pestaña
  Plotly; estado `self._bhf_drag_mode`.
- **Figura**: `_add_bhf_drag_line` dibuja una **línea vertical editable**
  (`fig.add_vline`, luego `shape.update(name='bhf_drag', editable=True, label=...)`)
  sobre la **línea 6** (externa derecha) del primer sexteto activo. Requiere
  `edits:{shapePosition:true}` en `CFG`.
- **Física**: posición de la línea 6 =
  `δ + patrón_cuadrupolar[-1]·ΔEQ + LINE_POS_33T[-1]·(BHF/33)`.
  Inversa (en `_on_bhf_dragged`): `BHF = (x − δ − patrón·ΔEQ)·33 / LINE_POS_33T[-1]`.
- **Ciclo**: arrastrar → al soltar, `plotly_relayout` → `__dragbridge.set_bhf_x(x)`
  → `ModelDragBridge.bhf_dragged` → `_on_bhf_dragged(x)` → fija `s1_bhf`
  (`ParamControl.set_value`, que **bloquea señales**, por eso llama después a
  `_on_model_param_changed()` para refrescar) → barra de estado
  `BHF ← xx.x T (arrastre)`.
- Convive con el editor de mínimos: usa `plotly_relayout`, ortogonal a
  `plotly_click`.

Limitaciones conocidas: sólo componente 1 / sólo BHF; `edits.shapePosition` hace
técnicamente arrastrable también la línea cero del residuo (inofensivo); reconstruye
la figura entera en cada arrastre.

---

## 9. Exportación a HTML autocontenido

`on_export_plotly_html()` → `_plotly_html_document()` produce un HTML **independiente**
(`fig.to_html(include_plotlyjs=True, full_html=False)` + estilos y contenedor). Se
puede abrir en cualquier navegador sin red. No usa WebChannel (es estático).

---

## 10. Temas, subtítulo, metadatos e i18n

- **Temas**: dark/light, decididos por `self.color_theme` / `self.plot_style_name`.
- **Subtítulo** (`_plotly_subtitle`): fichero + χ²ᵣ/AIC/BIC del último ajuste.
- **Metadatos** (`_plotly_metadata_html`): tabla HTML con programa/versión, fichero,
  canales, modo, perfil, verosimilitud, pérdida, estadísticos y componentes activos.
  **Actualmente sin uso** (la firma `__render(fig, meta)` reserva el hueco `meta`,
  siempre `null`). Si se restaura, aquí estaba la vía para inyectar metadatos junto
  a la figura interactiva.
- **Claves i18n** (`locales/*/strings.json`):
  - `plotly.title`, `plotly.initial`, `plotly.metadata_title`,
    `plotly.components_title`, `plotly.bhf_drag`, `plotly.bhf_drag_tip`,
    `plotly.bhf_drag_status`, `status.plotly_updated`, `status.plotly_exported`,
    `button.update_plotly`, `plot.tab_plotly`, `msg.plotly_missing`,
    `msg.plotly_no_plot`, `msg.plotly_webengine_missing`, `file.export_plotly_html`,
    `view.open_plotly`.
  - `minima.*`: `edit_action`, `editor_title`, `editor_hint`, `redetect`,
    `included`, `excluded`, `include_tip`, `count_tip`, `count_summary`, `propose`,
    `done`, `none_selected`.

---

## 11. Tests y el *workaround* de segfault

- `tests/test_qt_app.py`: ~9 pruebas tocan Plotly/mínimos/arrastre:
  `test_render_stores_dense_curve_for_plotly`, `test_current_plotly_figure_builds`,
  `test_edit_minima_populates_list`, `test_minima_marker_click_syncs_checkbox`,
  `test_minima_overlay_present_in_plotly_figure`, `test_propose_from_minima_builds_components`,
  `test_minima_multiplicity_adds_extra_components`, `test_auto_fit_from_minima`,
  `test_bhf_drag_prototype_line_and_roundtrip`, y el heatmap 2D en el test de
  distribución. También el test de distribución 2D usa `_current_plotly_figure()`.
- **Teardown de la fixture `make_window`**: antes de cerrar cada ventana hace
  `view.stop()`, `view.setParent(None)`, `view.deleteLater()` y `app.processEvents()`
  para evitar el *segfault* de QtWebEngine («Release of profile requested but
  WebEnginePage still not deleted»).
- **`tests/conftest.py` → `pytest_sessionfinish`**: si se cargó
  `PySide6.QtWebEngineWidgets`, hace `os._exit(0/1)` tras emitir el informe, para
  saltarse el teardown problemático del perfil global de WebEngine al apagar el
  intérprete.

Ambos *workarounds* desaparecerían con la opción B.

---

## 12. Guía de ELIMINACIÓN (opción B — adelgazar)

Objetivo: quitar `QtWebEngine` y `plotly` conservando el **editor de mínimos**
(reimplementado en Matplotlib) y, si se quiere, la exportación estática.

**Paso 0 — reimplementar el editor de mínimos en Matplotlib** (lo único con valor):
- Usar `SpectrumCanvas` (Matplotlib) con `figure.canvas.mpl_connect`:
  - `button_press_event` para clic en zona vacía → añadir mínimo (equivale a
    `_on_minima_plot_clicked`).
  - `pick_event` (marcadores con `picker=True`) para alternar incluir/excluir
    (equivale a `_on_minima_marker_clicked`).
- Reusar TODA la lógica de estado ya existente (`_minima_entries`,
  `_populate_minima_list`, `on_propose_from_minima`, `detect_absorption_minima`,
  `plotly_tol_factor/min`): sólo cambia la capa de dibujo/eventos, no la lógica.
- Dibujar los marcadores incluidos/excluidos como `ax.scatter` sobre el canvas.

**Paso 1 — retirar la vista interactiva y el prototipo de arrastre**:
- `gui/main_layout.py`: eliminar la creación de `plotly_tab`, `plotly_view`,
  `plotly_split`, botones `btn_plotly_*`, `chk_bhf_drag`, `plotly_status`,
  `_setup_minima_webchannel()`, el `QTimer` y todo el estado `_plotly_*`. El editor
  de mínimos pasa a colgar del canvas Matplotlib (panel lateral en la pestaña
  principal).
- `gui/plotly_tools.py`: eliminar o **vaciar** el mixin. Conservar y **migrar** a un
  nuevo `gui/minima_editor.py` (Matplotlib) los métodos de mínimos
  (`_build_minima_editor`, `_populate_minima_list`, `on_edit_minima`,
  `_on_minima_*`, `on_propose_from_minima`, `_update_minima_count_label`,
  `_exit_minima_edit`). Borrar: `_current_plotly_figure`, `_plotly_*`,
  `_add_bhf_drag_line`, `_drag_sextet_panel`, `_bhf_outer_line_x`, `_on_bhf_dragged`,
  `_on_toggle_bhf_drag`, `on_open_plotly`, `on_export_plotly_html`,
  `_add_minima_overlay` (se sustituye por el dibujo en Matplotlib).
- `gui/bridges.py`: eliminar `MinimaBridge`, `ModelDragBridge`, `_UiCallBridge`
  (ninguno hace falta sin WebChannel).
- `gui/window_mixins.py`: quitar `PlotlyToolsMixin` (o sustituir por el nuevo mixin
  de mínimos Matplotlib).
- `gui/menu_builder.py`: eliminar `file.export_plotly_html` y `view.open_plotly`
  (conservar `fit.edit_minima`, ahora sobre el canvas). Quitar `act_export_plotly`.
- `mossbauer_qt.py`: eliminar `_plotly_temp_files` y la llamada a
  `_cleanup_plotly_temp_files` del `closeEvent`.

**Paso 2 — dependencias y empaquetado**:
- `requirements.txt`: quitar `plotly`.
- `Fitbauer.spec`: quitar de `hiddenimports` `plotly*` y `PySide6.QtWebEngine*`.
  (Esto es lo que **reduce cientos de MB** el ejecutable.)

**Paso 3 — tests**:
- `tests/conftest.py`: eliminar el `pytest_sessionfinish` (ya no hay WebEngine).
- `tests/test_qt_app.py`: eliminar/reescribir las pruebas de §11. Las de mínimos
  se reescriben contra la nueva capa Matplotlib (misma lógica de estado, distinto
  disparador de eventos). Simplificar el teardown de `make_window` (quitar
  `view.stop()`/`deleteLater()`).
- Añadir tests de los eventos Matplotlib (simular `button_press_event`/`pick_event`).

**Paso 4 — exportación (opcional)**:
- Si se quiere conservar «compartir gráfico», sustituir el HTML Plotly por
  `fig.savefig(...)` (PNG/SVG/PDF) de Matplotlib, o `mpld3`/`plotly.io` puntual
  **sin** WebEngine (export a fichero, no vista embebida).

**Paso 5 — i18n y docs**:
- Retirar (o dejar inertes) las claves `plotly.*` y las de exportación en los tres
  locales.
- Actualizar `docs/` y `CLAUDE.md` (que mencionan la figura Plotly y
  `gui/plotly_tools.py`).

**Impacto neto esperado:** ejecutable mucho más ligero y con arranque más rápido,
sin *segfaults* de teardown, ~700 líneas menos y 2 dependencias menos. Se pierde la
vista interactiva pulida y el HTML compartible fácil; el editor de mínimos se
conserva (reimplementado).

---

## 13. Guía de RESTAURACIÓN (volver a poner Plotly)

1. `requirements.txt`: añadir `plotly`. Reinstalar (`PySide6` ya trae WebEngine).
2. `Fitbauer.spec`: re-añadir a `hiddenimports`: `plotly`, `plotly.graph_objects`,
   `plotly.subplots`, `PySide6.QtWebEngineWidgets`, `PySide6.QtWebEngineCore`.
3. Recrear `gui/bridges.py` con `MinimaBridge` y `ModelDragBridge` (§3.2 / §6.2).
4. Recrear `gui/plotly_tools.py` (`PlotlyToolsMixin`) con la plantilla HTML/JS de §6.1
   y los métodos de §3.1. El render incremental (§5) y el truco del **fichero
   temporal** en lugar de `setHtml()` (§3.1, `_load_plotly_html`) son **críticos**:
   no usar `setHtml()` con `plotly.js` embebido.
5. `gui/main_layout.py`: recrear la pestaña, el `QWebEngineView` en `QSplitter` con
   el editor de mínimos, el estado incremental, el `QTimer` y
   `_setup_minima_webchannel()`.
6. `gui/window_mixins.py`: re-insertar `PlotlyToolsMixin` en el MRO.
7. `gui/menu_builder.py`: re-añadir `file.export_plotly_html` y `view.open_plotly`.
8. `mossbauer_qt.py`: re-añadir `_plotly_temp_files` y la limpieza en `closeEvent`.
9. `tests/conftest.py`: re-añadir el `pytest_sessionfinish` anti-*segfault*; en la
   fixture `make_window`, re-añadir `view.stop()/deleteLater()`.
10. Re-crear las claves i18n `plotly.*` (§10).

**Detalles críticos que es fácil olvidar al restaurar:**
- `Plotly.react` (no `Plotly.newPlot`) para el refresco incremental.
- Cargar `plotly.js` **inline** con `plotly.offline.get_plotlyjs()` (sin CDN).
- `qrc:///qtwebchannel/qwebchannel.js` para el puente.
- Fichero temporal + `QUrl.fromLocalFile`, **nunca** `setHtml()`.
- El *workaround* de *segfault* al cerrar (fixture y `conftest`).
- `ParamControl.set_value` **bloquea señales** → tras fijarlo hay que llamar a
  `_on_model_param_changed()` para refrescar (patrón del prototipo de arrastre).

---

## 14. Apéndice — mapa rápido de símbolos a tocar

```
requirements.txt                 plotly
Fitbauer.spec                    hiddenimports: plotly*, PySide6.QtWebEngine*
gui/bridges.py                   MinimaBridge, ModelDragBridge, _UiCallBridge
gui/plotly_tools.py              PlotlyToolsMixin (todo)
gui/main_layout.py               plotly_tab, plotly_view, plotly_split, botones,
                                 chk_bhf_drag, _plotly_* estado, _setup_minima_webchannel,
                                 _plotly_update_timer
gui/menu_builder.py              file.export_plotly_html, view.open_plotly, act_export_plotly
gui/window_mixins.py             PlotlyToolsMixin en el MRO
mossbauer_qt.py                  _plotly_temp_files, closeEvent→_cleanup_plotly_temp_files
tests/conftest.py                pytest_sessionfinish (segfault WebEngine)
tests/test_qt_app.py             ~9 tests de plotly/mínimos/arrastre + teardown fixture
locales/{es,en,fr}/strings.json  plotly.*, minima.*
core/data_io.py                  CONFIG_DIR/plotly (temporales)
core/params.py                   plotly_tol_factor, plotly_tol_min
CLAUDE.md, docs/                 menciones a la figura Plotly y gui/plotly_tools.py
```
