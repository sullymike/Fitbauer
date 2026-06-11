# Changelog

## v4.7.3 — Reorganización de menús y ayuda alineada

### Interfaz

- **Menú «Opciones» eliminado.** Duplicaba entradas de Ajuste y Vista
  compartiendo los mismos `QActionGroup` exclusivos, por lo que sus radios y
  checkmarks no podían reflejar el estado real (mismo defecto que el «Tema
  visual» duplicado retirado en v4.7.1). Desaparecen también las lambdas de
  sincronización entre menús.
- **Menú Ajuste reagrupado**: «Modo de ajuste» (radios con los **7 modos** del
  combo lateral, antes solo 2, con sincronización en ambos sentidos también
  para P(ΔEQ)/P(IS)/2D), submenús «Preparación» (centro, mínimos, IA) y
  «Análisis de errores» (bootstrap, verosimilitud perfilada y L-curve, antes
  desubicada al final del menú), bloque de parámetros y Opciones avanzadas.
- **Archivo**: «Open Recent» traducido (clave `file.open_recent` ES/EN/FR) y
  «Usar como calibración» junto a Cargar/Recientes.
- `fit_mode_labels()` en `gui/main_layout.py` como fuente única de las
  etiquetas de modo (combo lateral + menú).

### Ayuda integrada

- ES: eliminado el capítulo «Menú Opciones»; «Menú Ajuste» reescrito y
  reordenado según el menú real, con entrada nueva para «Editar mínimos
  (semi-manual)» (existía en el menú pero no estaba documentada); «Abrir
  recientes» en Menú Archivo.
- Rutas «menú → ítem» actualizadas en los tres idiomas (Buscar centro,
  Bootstrap, Verosimilitud perfilada y L-curve apuntan a sus submenús nuevos);
  verificado con un inventario automático sin referencias obsoletas.

---

## v4.7.2 — Revisión de fallos latentes, batch coherente e i18n de actualizaciones

### Bugs corregidos

- **Cargar P fija lanzaba `NameError`.** `gui/distribution_fit.py` usaba `Path`
  y `ROOT` sin importarlos/definirlos; la acción «Cargar P fija» fallaba siempre.
- **Diálogos web siempre en español.** El patrón `tr(...) if hasattr(tr, "_d")
  else "literal"` de `gui/web_api.py` era siempre falso, así que se ignoraban
  las traducciones EN/FR existentes. Sustituido por `tr(clave, default=...)`.
- **Duplicados divergentes en `core/data_io.py`.** Tenía copias antiguas de las
  funciones de lectura/folding que habían divergido de `core/folding.py` (sin la
  heurística ≥400 del folding point Normos; `weight_sum` 4 vs 12 al estimar
  `depth` desde ARE). Ahora reexporta las canónicas de `core.folding`.
- **Desalineación latente en `core/fit_engine.py`.** Los globales
  `vmax`/`center`/`voigt_sigma` se añadían a `x0` solo si la clave existía en
  `values`, pero el residuo y el desempaquetado final solo miraban el flag;
  un flag activo sin clave desalineaba el vector de parámetros. Condiciones
  unificadas en las tres rutas.
- **El batch doblaba distinto que el flujo principal.** El diálogo de lote
  (`gui/dialogs.py`) ahora usa `fold_and_normalize` (recorte de borde) y
  `velocity_axis`, igual que la GUI e `HeadlessSession`, y el `FitState` recibe
  `counts`/`norm_factor`/`center` del fichero del batch (antes conservaba los
  del espectro cargado, afectando al re-folding de `fit_center` y la σ Poisson).
  Los resultados de batch pueden variar ligeramente respecto a series antiguas
  (se excluyen los dos canales de borde); batch e individual ahora coinciden.

### Internacionalización

- **Diálogos de actualización traducidos** (`gui/updates.py`): 31 claves nuevas
  `updates.*` en los catálogos ES/EN/FR; antes todo el flujo de actualizaciones
  aparecía en español también con la interfaz en inglés o francés.

### Robustez y limpieza

- `mossbauer_updater.py`: si una descarga falla a medias se borra el fichero
  parcial en lugar de dejarlo en Descargas.
- `gui/dialogs.py`: eliminada una línea muerta del batch y protegido el flag
  `_building` del warm-start con `try/finally`.
- Comentario de `LINE_POS_33T` en `mossbauer_distribution.py` corregido
  (contradecía la convención del patrón publicado de α-Fe; ver v4.0.2/v4.0.3).
- Docstrings que aludían a la GUI Tk eliminada e imports redundantes.

---

## v4.7.1 — Revisión completa de ayuda y corrección de menú

### Documentación y ayuda integrada (ES/EN/FR)

- **Referencias bibliográficas** añadidas en todos los idiomas: Hesse & Rübartsch
  (1974) para P(BHF), Hansen (1992) para L-curve/GCV, Blume & Tjon (1968) para
  relajación dinámica de dos estados, Néel (1949) y Brown (1963) para NeelSize,
  Margulies & Ehrman (1961) para absorbente grueso, Kündig (1967) para tratamiento
  cuadrupolar Hamiltoniano completo.
- **FR P(ΔEQ)** expandido desde 280 a ~2200 chars: modelo, parámetros BHF fijo/
  rangos/δ global, usos típicos y precauciones sobre correlaciones.
- **FR L-curve** expandida: descripción de GCV (validación cruzada generalizada)
  y referencia Hansen (1992).
- **FR Contraintes** expandida: ejemplos con sintaxis real y sección de presets
  físicos con los cuatro botones disponibles.
- **ES capítulo 27** («Acceso a opciones y novedades») convertido en índice corto
  que apunta a los capítulos temáticos propios; conserva las tres funciones sin
  capítulo propio (comportamiento simulación, calibración por clic derecho, δ
  corregido). Elimina duplicación con Menú Ajuste, P(BHF): método/parámetros y
  Restricciones.
- **ES capítulo 29** («Novedades desde v0.2») reducido de 12 804 a ~4 800 chars:
  elimina la entrada v0.2.0 (referenciaba GUI obsoleta), condensa v0.2.1–v0.2.6
  en lista de bullets con punteros, mantiene los how-to de bootstrap y presets,
  resume v0.4.2–v0.4.11 en una línea por versión.
- **EN P(ΔEQ)** ya expandido en PR anterior; **EN absorbente grueso** y **Kündig**
  descritos con fórmula y referencia en «Accessing options».

### Corrección de menú

- **Bug: Tema visual duplicado en Opciones.** El submenú `Opciones → Tema visual`
  creaba acciones sin `QActionGroup` y sin sincronización con `Vista → Tema visual`
  (que sí usa grupo exclusivo). El checkmark de Opciones nunca reflejaba el tema
  activo. Se elimina el submenú de Opciones; el tema sigue operativo en
  **Vista → Tema visual**.
- **Separador en menú Ajuste** entre herramientas pre-ajuste (Buscar centro,
  Inicializar, IA Ollama) y post-ajuste (Bootstrap, Verosimilitud, Lote).

---

## v4.7 — Reconciliación arquitectónica y mejoras de interfaz

> **Contexto histórico.** La v4.5 (refactorización modular de `gui/`) se
> publicó y tuvo que revertirse porque la v4.6 (física nueva: relajación,
> distribuciones 2D/IS) se había desarrollado en paralelo sobre la
> arquitectura anterior. Esta versión fusiona definitivamente ambas líneas:
> toda la física de la 4.6 sobre la arquitectura modular de la 4.5, más
> los cambios descritos a continuación.

### Reconciliación v4.5 + v4.6

- **Arquitectura modular `gui/`** (originada en v4.5) integrada con toda la
  física de la v4.6: los módulos `gui/discrete_fit.py`, `gui/distribution_fit.py`,
  `gui/model_workflow.py`, `gui/fit_workflow.py`, etc. son la base definitiva.
- **Corrección de tipos desconocidos.** `core/validation.py` y `core/session.py`
  ahora usan `COMPONENT_KINDS` y `DISTRIBUTION_SHAPES` de `core/params.py` como
  fuente única, eliminando los errores «tipo desconocido 'Relajacion'» y «tipo
  desconocido '2D'» que aparecían en la versión reconciliada anterior.
- **Restauración de sesión completa.** `gui/session_io.py` acepta todos los tipos
  de componente (`Relajacion`, `BlumeTjon`, `NeelSize`) y todas las formas de
  distribución (`2D`) al cargar una sesión guardada.

### Mejoras de interfaz (panel de componentes)

- **Reflow dinámico del panel de componentes.** Los parámetros aparecen y
  desaparecen sin huecos al cambiar el tipo; solo se muestran los relevantes
  para cada tipo según `USED_BY` de `core/params.py`.
- **Columnas equilibradas automáticamente.** Si una columna supera a la otra
  en más de dos filas, el exceso se redistribuye, evitando columnas muy cargadas
  junto a columnas casi vacías (especialmente visible en NeelSize y Relajacion).
- **Altura fija de controles.** `ParamControl` y `ComponentPanel` tienen política
  de tamaño `Fixed` vertical: los campos nunca se comprimen aunque haya muchos
  parámetros; el `QScrollArea` del panel izquierdo se encarga del desplazamiento.
- **Conmutación apilado↔pestañas por altura real.** El umbral que decide cuándo
  pasar de componentes apilados a pestañas usa `sizeHint()` de cada panel en
  lugar de una constante fija, de modo que tipos con muchos parámetros (NeelSize)
  activan el cambio al tamaño correcto y sin oscilaciones. La comprobación también
  se dispara al cambiar el tipo en el combo, no solo al redimensionar la ventana.

### Mejoras del diálogo de progreso de ajuste

- **Diálogo detallado restaurado.** Durante el ajuste se muestran fase, número
  de evaluaciones, RMS actual y mejor, y tabla de parámetros libres con sus
  valores en curso — información que se había perdido en la reconciliación.
- **Botón Cancelar.** Un botón en el diálogo de progreso permite abortar el
  ajuste en cualquier momento de forma limpia (`FitCancelledError`), sin
  mensajes de error espurios.

### Calidad y tests

- **Whitelists centralizadas.** `COMPONENT_KINDS` y `DISTRIBUTION_SHAPES` en
  `core/params.py` son ahora la fuente única para validación, sesión y GUI;
  añadir un nuevo tipo o forma ya no requiere buscar todas las listas dispersas.
- **Tests de regresión.** Nuevos tests en `tests/test_qt_app.py` y
  `tests/test_validation.py` cubren: tipos nuevos en validación, restauración
  de sesión con `Relajacion`/`2D`, cancelación del ajuste, reflow sin huecos
  por columnas y ningún campo fuera del grid.

### Pendiente / trabajo en curso

- **TODO (punto 3):** Centralizar las listas de `intensity_mode`
  (`"free"`, `"texture"`) y `quad_treatment` (`"1st_order"`, `"kundig_fixed"`,
  `"kundig_powder"`) en `core/params.py`, igual que se hizo con
  `COMPONENT_KINDS`/`DISTRIBUTION_SHAPES`, para que añadir nuevos modos no
  sea un bug silencioso (ver `gui/session_io.py`).
- **TODO (punto 4):** Evaluar reconstrucción de nítidos con `build_sharp_kernel`
  (SHA `a7c803b`) como alternativa más fiel cuando el ajuste refina δ/Γ globales
  (ver `gui/distribution_fit.py`).
- **Multi-ajuste con temperaturas** (Néel-Arrhenius global sobre series de
  espectros a distintas temperaturas): pendiente de implementación.

## v4.6 — Distribuciones generalizadas y relajación magnética

- Distribuciones 2D: backend `mossbauer_distribution.fit_bhf_quad_distribution()` generalizado para pares `BHF`, `ΔEQ/QS` e `IS`; integración en la GUI como modos **P(BHF, ΔEQ) 2D**, **P(IS, ΔEQ) 2D**, **P(BHF, IS) 2D** y distribución 1D **P(IS)**, con mapa de calor, marginales, heatmap Plotly, exportación TSV, L-surface `αx/αy`, componentes nítidos simultáneos, diagnósticos (medias, sigmas, correlación aparente, dof efectivo) e informe PDF con mapa 2D; advertencias de sobreajuste/identificabilidad en ayuda y documentación matemática. Nuevo documento `docs/distribuciones_is_mossbauer.pdf` para `P(IS)` y `P(IS, ΔEQ)`.
- Relajación magnética: implementación completa desde el modelo fenomenológico y dinámico (Blume-Tjon) hasta la distribución de tamaños Néel-Arrhenius y ajuste global multi-temperatura.
- En distribuciones `P(BHF)`, `δ`, `ΔEQ` y `Γ` se refinan directamente si su casilla **fijo** está desmarcada; se elimina el interruptor extra “refinar δ y Γ globales”. En `P(ΔEQ)`, `ΔEQ` sigue siendo la variable distribuida y no se refina como parámetro global.
- Las sesiones guardan y restauran los parámetros propios del panel de distribución y sus estados fijo/libre.
- La ventana de progreso del ajuste muestra ahora fase, evaluaciones, RMS actual/mejor y tabla de parámetros libres durante el refinamiento de distribuciones.
- El parámetro `β` del sextete se oculta salvo en el tratamiento cuadrupolar **Kündig fijo** y se renombra a `β Kündig (BHF↔Vzz, °)` para evitar confundirlo con versiones beta.

## v4.5 — Arquitectura Qt modular, estado formal y core más puro

- **Refactorización completa de la GUI Qt.** `mossbauer_qt.py` queda como punto de entrada fino y la lógica se organiza en módulos `gui/` especializados: layout, menús, sesiones, ajustes, distribución, Plotly, informes, actualización, API web y compatibilidad.
- **Snapshots de estado GUI.** Se introducen `ComponentViewState`, `CalibrationViewState`, `DistributionViewState`, `UiActionState`, `ProjectState` y otros estados para reducir el acoplamiento widget→lógica.
- **Flujo común de ajuste.** Los modos discreto y distribución comparten progreso, manejo de errores, render y `GuiFitResult` mediante `gui.fit_workflow` y `RuntimeResultState`.
- **Reconstrucción física fuera de la GUI.** `core.reconstruction` centraliza reconstrucción de modelos, residuos, curvas densas, áreas, porcentajes y subespectros de distribuciones con componentes nítidas.
- **Validación de parámetros en core.** `core.validation` comprueba límites, finitud, rangos de distribución, tamaños de arrays y coherencia antes de lanzar ajustes.
- **API interna de resultados.** `core.result_views` proporciona vistas de solo lectura para estadísticas, parámetros, errores, curvas de distribución y métricas, usadas por informes, Plotly y paneles.
- **Compatibilidad histórica centralizada.** `gui.compat` agrupa los puentes para símbolos parcheables de `mossbauer_qt.py` y propiedades legacy.
- **Documentación y tests.** Nuevos documentos `docs/architecture.md` y `docs/user-flows.md`; más tests específicos para snapshots, flujo de ajuste, reconstrucción, validación, vistas de resultado y compatibilidad.

## v4.1.0 — Interfaz única Qt y ajuste headless en core

- **Se elimina por completo la interfaz Tk.** La aplicación tiene ahora una sola interfaz gráfica, la Qt (`mossbauer_qt.py`). Se retiran el monolito `mossbauer_fe33_gui_v2IA.py`, `mossbauer_app.py`, el paquete `panels/`, el gestor/configurador Tk de `layout/`, el diálogo Tk de actualizaciones (`mossbauer_updater_ui.py`), `Fitbauer-Tk.spec` y la dependencia `sv_ttk`.
- **Capa de ajuste headless en `core/session.py`.** La orquestación cargar → doblar → ajustar → sesión que antes vivía en la app Tk se extrae a `core.session` (`ModelState` + `HeadlessSession`), sin dependencia de ninguna GUI y reusando `core.fit_engine`/`core.folding`. El CLI `mossbauer_fit_cli.py` ya no necesita display ni Tk.
- **Lanzador simplificado.** `fitbauer.py` arranca directamente la interfaz Qt (sin opciones `--tk`/`--qt` ni respaldo Tk).
- **Funciones de actualización sin GUI** (`load/save_update_settings`, `check_requirements_if_needed`, refresco de dependencias pip) trasladadas de `mossbauer_updater_ui.py` a `mossbauer_updater.py`.

## v4.0.4 — Nítidos fijos y subespectros en distribuciones

- **Profundidad fija real en componentes nítidos.** En los ajustes `P(BHF)` / `P(ΔEQ)` con nítidos, si `depth` está marcada como fija, el backend la trata como contribución de absorción conocida y no como amplitud ajustable. Los nítidos libres conservan amplitud `>= 0` ajustable.
- **Backend consistente en todas las formas de distribución.** La corrección cubre histograma/Tikhonov, gaussiana, binomial y distribución fija.
- **Subespectros visibles.** Al ajustar distribución + nítidos se muestran la contribución de la distribución sola, cada nítido por separado y el ajuste total, facilitando diagnosticar el reparto de absorción.

## v4.0.3 — Corrige el BHF de calibración (regresión de v4.0.2)

- La **v4.0.2** publicada derivaba las posiciones del sextete de los momentos nucleares de libro, lo que daba un desdoblamiento ~0,4 % menor (línea externa 5.309 vs 5.328 mm/s a 33 T) y **sesgaba el BHF ~0,1 T hacia arriba** (un α-Fe leía 33.12 T en vez de 33.0).
- Se vuelve al **patrón de velocidad publicado de α-Fe** (`±0.839 / ±3.084 / ±5.329 mm/s` a 33 T): un α-Fe ajusta a **33.0 T exacto, igual que NORMOS**. Documentado en el código para no reintroducir el sesgo.

## v4.0.2 — Calibración del campo a 33.0 T

- **Elimina la constante interna `32.95 T`**: la calibración de velocidad/campo (Tk, Qt, modelo discreto y distribución) usa el campo de referencia **33.0 T (330 kOe)**.
- **Fuente única.** `mossbauer_distribution.py` toma `LINE_POS_33T` de `core.constants`, eliminando una tercera copia duplicada de las posiciones.
- Incluyó un cálculo de las posiciones desde los momentos nucleares que resultó **sesgar el BHF ~0,1 T** (corregido en v4.0.3).
- Limpieza: se elimina el parámetro muerto `max_nfev` de `profile_likelihood()`.

## v4.0.1 — Logo en la interfaz

- El logo de Fitbauer se muestra ahora dentro del programa: tarjeta de cabecera, pantalla de inicio (splash) y diálogo «Acerca de», tanto en la interfaz Qt como en la Tk.
- Carga robusta del logo: si la imagen no está disponible se conserva el comportamiento anterior (texto / dibujo vectorial).

## v4.0 — Fitbauer

Cambio de marca y preparación para producción.

### Identidad

- La aplicación pasa a llamarse **Fitbauer** — *Software for Mössbauer spectrum fitting and analysis*.
- Nuevo logo/icono (`assets/fitbauer_icon.*`, fuente vectorial `assets/fitbauer_logo.svg` generada por `assets/make_logo.py`): firma de un sextete Mössbauer con su curva de ajuste sobre insignia azul→cian.

### Arranque unificado

- Nuevo punto de entrada único `fitbauer.py` (y lanzadores `fitbauer` / `fitbauer.bat`): abre la interfaz Qt por defecto y cae automáticamente a la Tk si PySide6 no está disponible o falla. Opciones `--tk` / `--qt`.
- Los ejecutables PyInstaller pasan a `Fitbauer.spec` (Qt, principal) y `Fitbauer-Tk.spec` (Tk, respaldo).

### Limpieza del repositorio

- `layout.json` deja de versionarse (es estado de runtime) y se añade a `.gitignore`.
- Eliminado `download_and_fit_calibrations.py` (roto e inutilizado: importaba un módulo inexistente).
- Retiradas notas de versión sueltas (`RELEASE_NOTES_v*.md`, `RELEASES.md`) — el historial vive en este `CHANGELOG.md` — y documentos internos de roadmap (`PROPUESTAS_*.md`, `NORMOS_comparison_improvements.md`).
- Capturas movidas a `docs/img/`.

## v3.7 — Informe completo, ayuda jerárquica y textura interpretada

Release estable. Foco en el informe Markdown/PDF y en el diálogo de Ayuda.

### Plotly en Qt

- El gráfico Plotly ocupa todo el alto del tab (flex `100%`) en lugar de un `72vh` fijo.
- Eliminado el *debounce* de 300 ms en las actualizaciones: ahora el gráfico se refresca de forma inmediata al mover sliders o cambiar parámetros (`QTimer` a 0 ms).

### Sextete: textura interpretada

- Para sextetes en modo de intensidades por **textura** (`I₂/I₃ = 4t/(2-t)`), se calculan y se muestran tres magnitudes físicas derivadas de `t = sin²θ`:
  - **θ** = `arcsin(√t)`: ángulo entre el campo hiperfino y el rayo γ (54.7° = ángulo "mágico" para muestra random).
  - **R₂₃** = I₂/I₃: razón de intensidades.
  - **S** = ⟨P₂(cos θ)⟩ = 1 − 3t/2: orden tipo Hermans (+1 alineado a γ, 0 isótropo, −½ perpendicular).
- Cada magnitud trae su σ propagada a partir de σ(t) cuando t es libre en el ajuste.
- Aparecen en el cuadro "Estado y parámetros" tras cada ajuste / cambio.

### Informe (Markdown + PDF) completo

- El informe ahora reproduce **toda** la información del panel "Estado y parámetros" como tablas estructuradas:
  - Espectro y plegado (canales, folding centro y Normos, pares doblados, normalización, perfil de línea).
  - Calibración y escala de velocidades (Vmax, baseline, slope, fit_velocity, calibración, δ ref, σ).
  - Bondad y diagnóstico (χ², χ²ᵣ, dof, AIC, BIC, nº params, RMS, multistart, diagnóstico residual lag-1 / runs z / antisymmetric corr con umbrales, correlación máxima y pares muy correlacionados).
  - **Análisis de áreas** por componente con % + σ + área absoluta (la σ estaba ausente).
  - Por componente, nuevo subbloque "Magnitudes físicas derivadas" con Γ HWHM reales, FWHM equiv., Γ relativas, profundidad, I₁/I₂/I₃ reales, BHF, δ, ΔEQ y δ corregido destacado.
  - Bloque "🧭 Magnitudes derivadas de la textura" con su tabla y un callout explicando el significado físico.
  - **δ corregidos por calibración**: tabla resumen δ ajustado vs. δ corregido.
  - **Parámetros fijados** y **Restricciones** como bloques dedicados.
  - **📖 Glosario de parámetros** al final del informe (δ, ΔEQ, BHF, Γ, depth, intensidades, textura, β, voigt_sigma, sat_scale, baseline, slope, Vmax).

### PDF rediseñado

- Portada con banner azul, título, fichero, fecha y cuadros con χ²ᵣ, χ², AIC, BIC, nº de componentes y nº de parámetros libres.
- Cuerpo parseado en bloques tipados (h3, párrafo, callout, código y **tablas reales**) en vez del volcado monoespaciado anterior. Las tablas tienen encabezado a color, filas zebra y anchos proporcionales con truncado por elipsis. Los callouts llevan barra lateral de color. Los emojis se filtran (DejaVu no los renderiza).

### Diálogo de Ayuda

- Barra lateral en **árbol jerárquico** que refleja la estructura real de menús del programa (Archivo, Ajuste, Opciones, Vista, Ayuda) + grupos temáticos de Conceptos físicos y Distribuciones P(BHF) / P(ΔEQ). Las cabeceras de grupo no son seleccionables y, al pulsarlas, saltan al primer capítulo del grupo.
- **Buscador** en la cabecera que filtra el árbol y resalta los aciertos en el panel de contenido con `<mark>`; cuenta los capítulos coincidentes.
- **HTML enriquecido**: el texto plano de cada capítulo se convierte a HTML con subtítulos h4, listas con viñetas y numeración, **negrita**, *cursiva* y `código` inline.
- **Negrita automática para las etiquetas de menú**: se construye un regex case-sensitive con todos los valores de `menu.*`, `file.*`, `fit.*`, `options.*` y `view.*` del catálogo activo (más un subconjunto de `help.*`), ordenados por longitud para que las etiquetas largas ganen prioridad. Variantes sin elipsis para etiquetas multi-palabra.
- Tipografía mejorada (h2/h3 con jerarquía visual, padding generoso, h3 subrayado), splitter 340/840 y diálogo 1180×760.

### Versión

- La versión local de la aplicación pasa a `3.7`.

## v3.6 — Plotly Qt corregido y listado web mejorado

Release estable con los cambios posteriores a v3.5.

### Plotly en Qt

- Corregida la vista Plotly en Qt cuando aparecía en blanco, sin datos ni ejes, cargando el HTML desde fichero local en vez de `setHtml()`.
- Eliminado de nuevo el bloque de metadatos bajo el gráfico Plotly para dejar solo la figura interactiva.
- Restaurada y mejorada la edición semi-manual de mínimos: botón visible en la pestaña Plotly, clic en el espectro para añadir mínimos y clic sobre/cerca de un marcador para activarlo o desactivarlo.

### Descarga web

- Corregida la consulta de medidas/calibraciones desde la GUI Qt aceptando `limit` en el cliente API.
- Listado web más legible: fichero abreviado a 13 caracteres, muestra con más espacio, fecha, temperatura, velocidad display (`velocity_input`) e id de calibración asociada.

### Versión

- La versión local de la aplicación pasa a `3.6`.

## v3.5 — integración Plotly y edición semi-manual de mínimos

Agrupa todos los cambios incorporados desde v3.0.

### Interfaz Qt/Plotly

- Integración de un gráfico **Plotly interactivo** en la GUI Qt para explorar espectros, ajustes, componentes y residuos con zoom/pan más fluido.
- Refresco incremental del gráfico para reducir redibujados completos y mejorar la respuesta durante simulación y ajuste.
- Curva de ajuste densa para una visualización más suave del modelo.
- Uso de trazas WebGL cuando conviene para mejorar el rendimiento con muchos puntos.

### Edición y ayuda

- Nuevo editor **semi-manual de mínimos** en la interfaz Plotly/Qt para revisar, añadir y ajustar mínimos detectados antes de inicializar componentes.
- Ayuda de los menús Qt ampliada y documentada en español.

### Empaquetado y versión

- La versión local de la aplicación pasa a `3.5`.
- Se mantiene compatibilidad con sesiones, plantillas y datos de v3.0.

## v3.0 — interfaz Qt y núcleo de cálculo unificado

Release mayor. Incorpora una segunda interfaz gráfica (Qt/PySide6) y, sobre todo,
unifica todo el cálculo en `core/`, compartido por la GUI Tk, la GUI Qt, el CLI y
el ajuste en serie.

### Interfaces y empaquetado

- Nueva **GUI Qt (PySide6)** junto a la GUI Tk clásica; ambas sobre el mismo núcleo.
- **Dos ejecutables**: Tk (`MossbauerFeFit.spec`, lanzadores `mossbauer`/`mossbauer.bat`)
  y Qt (`MossbauerFeFit-Qt.spec`, lanzadores `mossbauer-qt`/`mossbauer-qt.bat`).
- Informe (Qt) con tabla de parámetros valor ± σ, origen de la incertidumbre
  (covarianza o bootstrap), bondad (χ²ᵣ/χ²/AIC/BIC) y correlaciones altas.

### Núcleo de cálculo (`core/`) unificado

- Física del modelo única en `core.physics` (el Tk la reutiliza).
- Motor de ajuste único en `core.fit_engine`, usado por Tk, Qt, CLI y batch:
  multistart + optimización global + pérdida robusta + covarianza, re-folding del
  centro, σ de calibración (escala Vmax) y σ Poisson correcta, modo textura y
  restricciones encadenadas, bootstrap (Poisson) y verosimilitud perfilada como
  funciones puras. Eliminada la duplicación del optimizador en el Tk.
- CI ejecuta la suite completa (GUIs Tk/Qt, CLI y batch) headless con Xvfb/offscreen.

## v2.3-beta1 — prerelease no estable

Versión beta para validar cambios posteriores a v2.2 antes de una release estable.

- Vmax con signo conservado en GUI, CLI y calibraciones web.
- Corrección del eje de velocidades al recortar el primer y último punto doblado: se recorta el eje original en vez de reconstruirlo a ±Vmax con menos canales, evitando sesgo sistemático en BHF.
- Convención NORMOS para intensidades de sextete: int3 oculto/fijo a 1, int1≈D13, int2≈D23 y DEP/profundidad como escala global.
- Profundidad por defecto 0.02, Γ por defecto 0.15 mm/s y barra de profundidad 0–0.07 con límite interno de ajuste más amplio.
- Menú contextual en σ para alternar Lorentziana/Voigt.
- Icono de aplicación para gestor de ventanas/Alt-Tab.
- Padding reducido en botones del diálogo de actualización.
- Ayuda/README ampliados e informe de ejemplo Fe3O4 en Markdown/PDF.

## v2.2 — ajuste en serie, CLI y compatibilidad NORMOS

Agrupa todos los cambios incorporados desde v2.1 y prepara la nueva release.

### Ajuste y física

- Ajuste en serie desde la GUI con warm-start secuencial para procesar lotes de espectros relacionados.
- CLI de ajuste por fichero a partir de una plantilla JSON y un espectro, con salida JSON reproducible.
- Errores asimétricos opcionales por verosimilitud perfilada.
- Ajuste opcional de `σ` en perfiles Voigt y control visible desde el menú contextual del slider de `σ`.
- Selector de perfil Lorentziana/Voigt desde el clic derecho del control `σ`.
- Límites ampliados de `BHF` hasta 60 T y soporte para `ΔEQ` negativo.
- Modelo experimental opt-in de absorbente grueso/saturación, disponible tanto en ajuste discreto como en distribución, con refinamiento VARPRO de `(b, s, C)`.

### Datos, CLI y documentación

- Nuevos espectros sintéticos de compuestos de hierro y espectros sintéticos adicionales con ruido reducido.
- Plantillas CLI listas para magnetita, hematita, siderita y α-Fe.
- Capítulo de ayuda sobre el CLI en español, inglés y francés.
- Documento técnico sobre la corrección por espesor en `docs/correccion_espesor.*`.
- Ayuda ampliada sobre `VMAX`, signo del eje de velocidades y criterios de calibración.

### Interfaz y trazabilidad

- Menú de estilos de gráficos: clásico, moderno, publicación y oscuro.
- Corrección de la detección del punto de plegado (`PFP`) y mejor alineación con la convención NORMOS.
- Ajustes de GUI/calibración para reproducir mejor flujos NORMOS, incluido `Vmax` con signo.
- Eliminación de la caja de cabecera de presets para simplificar la interfaz.
- Ventana **Acerca de** cerrable con clic.

### Calidad

- Suite inicial de `pytest` y workflow de CI en GitHub Actions.
- Corrección del cableado del checkbox modular para ajustar `σ`.

## v2.1 — motor de ajuste ampliado y usabilidad

Incorpora las mejoras desarrolladas tras el manual matemático del motor de
ajuste (`docs/manual_mossbauer.pdf`).

### Motor de ajuste

- Verosimilitud seleccionable Gauss / Poisson (IRLS sobre σ del modelo).
- Pérdida robusta opcional (Soft L1 / Huber) frente a canales con picos espurios.
- Propagación de la incertidumbre de calibración (σ de vmax) a los pesos.
- Optimización global opcional (evolución diferencial) antes del pulido TRF.
- Tratamiento de Kündig del cuadrupolo (Hamiltoniano axial, β libre) y promedio policristalino, además del 1er orden.
- Parámetro de textura por sextete (t = sin²θ → 3 : 4t/(2−t) : 1).
- Normalización analítica del perfil Voigt (independiente del muestreo).

### Distribución P(BHF) / P(ΔEQ)

- Regularización por Variación Total (bordes afilados) además de Tikhonov.
- Selección automática de α por GCV (junto a curva L y compromiso).
- Grados de libertad efectivos en el χ² reducido.
- Barras de error 1σ de P(BHF) por covarianza linealizada.
- Preacondicionamiento de la matriz núcleo para BHF pequeño.

### Usabilidad

- Submenú "Ajuste → Opciones avanzadas de ajuste" para descongestionar el menú.
- Menús contextuales (clic derecho) en los sliders para elegir modo de intensidades y tratamiento del cuadrupolo.
- Agrisado de los parámetros no usados según tipo de componente y modo.
- No se simula nada al cargar datos hasta tocar un parámetro o ajustar.
- Previsualización en vivo de los sextetes en modo distribución antes de ajustar.
- "Inicializar desde mínimos" activa los componentes detectados y escala las profundidades para no pasarse de los datos.
- Clic derecho en la caja de muestra: usarla como calibración tomando vmax e iso actuales.
- Desplazamiento isomérico corregido (δ − iso de calibración) en el cuadro de resultados y el informe.
- Ayuda integrada ampliada (capítulo de acceso a opciones y novedades) en es/en/fr.

### Documentación

- Manual matemático extenso del motor de ajuste en `docs/` (LaTeX + PDF).

## v2.0 — release estable

Versión estable que consolida el desarrollo anterior y sustituye al historial fragmentado de releases 0.x y 1.x.

### Interfaz y flujo de trabajo

- Arquitectura modular con `core/`, `layout/` y `panels/`.
- Interfaz multilingüe español/inglés/francés y ayuda integrada ampliada.
- Layout configurable, tema claro/oscuro y paneles reorganizados.
- Guardado/carga de sesiones JSON, exportación de ajuste y generación de informes Markdown/PDF.
- Empaquetado de release con ZIP, checksums SHA-256, datos de ejemplo y lanzadores.

### Ajuste discreto

- Ajuste de singletes, dobletes y sextetes con pesos Poisson.
- Autoarranques deterministas, bootstrap MC, métricas χ²/AIC/BIC y diagnóstico de residuos.
- Áreas integradas, errores 1σ cuando están disponibles y resumen de correlaciones.
- Presets físicos de restricciones e imposición de relaciones entre parámetros.
- Ajuste opcional de Vmax y folding point.
- Detección automática mejorada de mínimos y propuesta inicial para uno o dos sextetes.

### Distribuciones hiperfinas

- Distribuciones `P(BHF)` y `P(ΔEQ)` con regularización tipo Hesse-Rübartsch.
- Escaneo L-curve, regularización por variación total, GCV/dof efectivo y acondicionamiento del kernel.
- Componentes nítidos simultáneos con la distribución.
- Barras de error 1σ en distribuciones y comparación de modelos.
- Corrección de la conversión de intensidades entre sextetes nítidos de la GUI y el motor de distribución.

### Física y perfiles

- Perfil Lorentziano y Voigt con normalización consistente.
- Tratamiento cuadrupolar de primer orden, Kündig fijo y Kündig polvo.
- Parámetro de textura para intensidades de sextete.
- Menús contextuales para modo de intensidades y tratamiento cuadrupolar desde `β` y `ΔEQ/AEQ`.

### Calibración y web

- Descarga de medidas y calibraciones desde la API web del laboratorio.
- Uso del fichero cargado como calibración local.
- Persistencia de la calibración entre ficheros y sesiones.
- Inclusión de metadatos e incertidumbre de calibración en estado e informes cuando está disponible.

### Limpieza de release

- Ramas antiguas incorporadas en `main` y eliminadas cuando ya no contenían cambios únicos.
- Release notes anteriores sustituidas por `RELEASE_NOTES_v2.0.md`.
