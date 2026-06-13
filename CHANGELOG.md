# Changelog

## v4.9.0 — Detección híbrida CWT, early-stop multistart y biblioteca de espectros de referencia

Versión con **mejoras en el motor de ajuste**, **nueva detección automática de mínimos
multi-escala** y una **biblioteca de 10 espectros sintéticos de referencia** para minerales
de hierro comunes. Incluye soporte de espectros pre-doblados en CSV y el diálogo de ajuste
global Néel-Arrhenius.

### Motor de ajuste (`core/fit_engine.py`)

- **Early-stop en multistart**: se detiene si el coste no mejora más de 1 ppm
  en 4 arranques consecutivos (`stagnation_patience=4`, `rel_tol=1e-6`), reduciendo
  tiempo de cómputo sin pérdida de calidad.

### Detección de mínimos (`gui/minima_analysis.py`)

- **CWT multi-escala con ondícula Ricker** (sustituye la convolución simple):
  detecta picos solapados en el rango físico Mössbauer (0.12–2.0 mm/s) con
  robustez frente a líneas anchas y sextetes.
- **Estrategia híbrida CWT + absorción directa**: la cresta CWT cubre líneas
  anchas/sextetes; el canal directo rescata dobletes estrechos que el CWT puede
  fusionar. Ambas listas se fusionan antes del filtrado final.
- **Corrección de desbordamiento CWT**: el kernel Ricker se clampea a
  `(n−1)//2` para que nunca supere el tamaño del signal (`np.convolve mode="same"`
  devuelve `max(M,N)`, no `M`).
- **Parámetros físicos ajustados** en `core/params.py`:
  - `init_gamma_min`: 0.08 → 0.10 mm/s (por encima del FWHM natural de Fe-57, ~0.097 mm/s)
  - `min_separation`: 0.12 → 0.15 mm/s

### Nuevos datos (`data_sample/public/`)

- **10 espectros sintéticos** de referencia con ruido Poisson realista (5 × 10⁶ cuentas):
  goetita, ferridrita, pirita, troilita, wüstita, ilmenita, jarosita, lepidocrocita,
  maghemita y pirrotita. Cada uno acompañado de su plantilla JSON de ajuste.
- **Script generador** `_generar_publicos.py` para reproducir o modificar los datos.
- **Espectro experimental real** de α-Fe calibración del ESRF
  (`alphaFe_calibracion_ESRF.dat`).

### Soporte de formatos (`core/data_io.py`)

- **Espectros pre-doblados en CSV/velocidad**: nuevos archivos `.dat` con columnas
  `velocidad, cuentas` se cargan directamente sin folding (útil para datos del ESRF
  y otros sincrotrones).

### Nuevas funcionalidades GUI

- **Diálogo GlobalNeelFitDialog** (`gui/`): ajuste global Néel-Arrhenius sobre
  múltiples espectros a distintas temperaturas, con exportación de parámetros.
- **Centralización de modos de intensidad y tratamiento cuadrupolar** en
  `core/params.py` (`INTENSITY_MODES`, `QUAD_TREATMENTS`) — fuente única para
  GUI y CLI.

### Tests (`tests/`)

- **Golden tests ampliados** (`test_headless_golden.py`): casos jarosita y siderita
  añadidos a los existentes (alphaFe, hematita). Los 4 casos son deterministas
  (semilla 12345) y protegen la física de regresiones numéricas.
- **Invarianza de signo para ΔEQ en dobletes** (`sign_invariant`): para un doblete
  puro sin BHF, `+ΔEQ` y `−ΔEQ` producen espectros idénticos; el test verifica
  `|s1_quad|` para evitar falsos negativos por diferencias de precisión numérica
  entre Python 3.11 y 3.12 / distintos BLAS.
- Correcciones en 3 tests sensibles al idioma (`test_qt_app.py`) y en el test
  de exportación TSV (`test_save_fit_writes_tsv`).

---

## v4.8.2 — Ayuda completa en tres idiomas y árbol de ayuda por grupo

Versión de **pulido de documentación interna**: sin cambios en el núcleo de
física ni en el motor de ajuste.

### Ayuda integrada (ES / EN / FR)

- **Paridad de capítulos**: inglés y francés pasan de 19 a **28 capítulos**,
  igualando la versión española. Se añaden 9 capítulos nuevos por idioma:
  - Menú Archivo / File menu / Menu Fichier
  - Menú Ajuste / Fit menu / Menu Ajustement
  - Perfil de línea (Voigt) / Line profile / Profil de raie
  - P(BHF): método / P(BHF): method / P(BHF) : méthode
  - P(BHF): parámetros / P(BHF): parameters / P(BHF) : paramètres
  - P(BHF): componentes nítidas / P(BHF): sharp components / P(BHF) : composantes nettes
  - Menú Vista / View menu / Menu Affichage
  - Menú Ayuda / Help menu / Menu Aide
  - Atajos y flujo rápido / Shortcuts and quick workflow / Raccourcis et flux rapide
- **Árbol de ayuda agrupado por campo `group`**: el árbol lateral de la ventana
  de Ayuda ahora agrupa los capítulos por su campo `group` (overview, files,
  fitting, distributions, results, tools) en lugar de usar índices fijos, lo que
  lo hace robusto ante reordenaciones o ampliaciones del JSON.

---

## v4.8.1 — Internacionalización completa, idioma por defecto inglés e informe reducido

Versión centrada en **pulido de la interfaz**: barrido exhaustivo de
internacionalización, cambio del idioma por defecto a inglés, un nuevo informe
reducido en PDF, y varias correcciones en sesiones, ajustes persistentes y
exportación de datos. No toca el núcleo de física/ajuste.

### Internacionalización (ES/EN/FR)

- **Barrido exhaustivo de cadenas hardcodeadas**: se han eliminado prácticamente
  todas las cadenas en español que estaban incrustadas en el código de la GUI y
  no pasaban por el sistema `tr()`. Afecta a barras de estado, títulos de diálogo,
  cabeceras de tabla, etiquetas de formulario y botones.
  - **Diálogos traducidos por completo**: límites de parámetros (70+ etiquetas
    científicas por idioma), configuración de layout (nombres de paneles y de
    presets predeterminados: Estándar/Tres columnas/Análisis/Compacto), API web
    (login, buscador, cabeceras de tabla, descarga), resumen para IA/LLM, y
    presets físicos de restricciones.
  - **Formulario de calibración local** (Sample / Vmax / IS), mensajes de barra
    de estado («Centro detectado», «Ajuste guardado», «Datos re-doblados»,
    «Ajuste base», verosimilitud perfilada) y el menú **Vista → Límites de
    parámetros…** ahora se traducen.
  - **Paridad de catálogos**: los tres idiomas mantienen exactamente el mismo
    conjunto de claves (744 cada uno).
- **Idioma por defecto cambiado de español a inglés** (`DEFAULT_LANGUAGE = "en"`).
- **«Ajuste con sextetes» → «Ajuste cristalino»** (EN: *Discrete fit*; FR:
  *Ajustement cristallin*), pues el modo admite singletes y dobletes, no solo
  sextetes.
- En inglés, la casilla de parámetro fijo pasa de «fixed» a **«fix»** para evitar
  que el texto se solape con los controles de subir/bajar valor.

### Informe reducido (Archivo → Exportar informe reducido MD/PDF…)

- Nuevo **informe condensado** en Markdown y PDF, complementario al informe largo
  (que se mantiene). Incluye solo los parámetros de cada componente, el análisis
  de áreas y la figura del espectro al final.
- **Renderer PDF propio y compacto**: cabecera y tablas reducidas, sin portada ni
  tarjeta de metadatos, para ocupar las menos páginas posibles.

### Exportación del ajuste (Archivo → Guardar ajuste…)

- El fichero TSV guarda ahora **los subespectros de cada componente**, no solo el
  modelo total.
- **Cabecera informativa** que indica fichero, fecha, modo (discreto/distribución)
  y el tipo de cada componente.
- Los nombres de tipo de componente se escriben **en inglés** (Sextet, Doublet,
  Singlet…) de forma consistente en todo el fichero de datos.

### Correcciones

- **Sesiones**: al cargar una sesión de ajuste discreto (p. ej. dos dobletes) ya
  no se salta erróneamente al modo distribución P(BHF). Se guarda el índice de
  modo explícito (`mode_combo_idx`), con compatibilidad hacia atrás para sesiones
  antiguas.
- **Arranques múltiples** (`multistart_n`): ahora se persiste en `settings.json` y
  se restaura entre arranques de la aplicación; también se restaura al cargar
  sesión, sin el límite máximo hardcodeado anterior.
- **Informes**: las tablas muestran solo los parámetros y magnitudes derivadas
  relevantes para cada tipo de componente (singlete/doblete/sextete), en lugar de
  todos los parámetros aunque no se hubieran ajustado.

### Créditos

- Se añade a **Nieves Menéndez González** como coautora.

## v4.8.0 — Editor de límites de parámetros y consolidación de constantes

### Diálogo de límites de parámetros (Vista → Límites de parámetros…)

- Nuevo diálogo accesible desde el menú **Vista** que permite editar todos los
  rangos y valores por defecto de los controles de la GUI sin tocar el código.
- Los cambios se guardan en `~/.config/mossbauer_fe33_gui/param_limits.json` y
  se aplican al reiniciar; `core/params.py` permanece como fuente de solo lectura.
- **Cinco pestañas**: Componentes (20 parámetros), Calibración (6), Distribución (16,
  incluyendo los nuevos IS mín/máx y ΔEQ mín/máx), Inicialización del ajuste (17)
  y Detección de picos (avanzado) (14).
- Cada pestaña incluye un botón «Restablecer a valores predeterminados».

### Nuevos parámetros configurables de distribución

- **IS mín / IS máx** (`is_lo` / `is_hi`): controlan el rango exterior de los
  sliders `bmin`/`bmax` cuando la distribución opera en modo IS (δ).
- **ΔEQ mín / ΔEQ máx** (`quad_lo` / `quad_hi`): ídem para modo ΔEQ distribuido.
- Antes estos límites eran fijos (±2.5 mm/s y 0–7 mm/s respectivamente).

### Consolidación de constantes en `core/params.py`

- `FIT_INIT_SPECS`: 17 parámetros de inicialización automática del modelo
  (límites BHF de detección, clips de Γ/δ/profundidad, rango L-curve, bootstrap,
  multistart) que antes eran literales dispersos en `gui/minima_analysis.py`,
  `gui/distribution_fit.py`, `gui/discrete_fit.py` y `gui/menu_builder.py`.
- `PEAK_DETECTION_SPECS`: 14 umbrales de detección y clasificación de picos
  (factores de altura/prominencia/distancia, tolerancias de match, ratios
  singlete/doblete, tolerancia de marcadores Plotly).
- `SEXTET_WEIGHTS = (3, 2, 1, 1, 2, 3)`: constante exportada que sustituye el
  literal repetido en la detección de sextetes.
- Los rangos del diálogo de calibración detallada y del spinner de arranques
  múltiples usan ahora los specs efectivos en lugar de valores hardcodeados.

### Corrección de bug: gamma/2 en `two_state_exchange_profile`

- `mossbauer_distribution.py` tenía una copia local de `two_state_exchange_profile`
  con un bug en el guard de gamma (usaba FWHM en lugar de semianchura). Corregido
  eliminando las funciones duplicadas e importando directamente desde `core.physics`,
  que tiene la implementación correcta.

## v4.7.5 — Mapas topográficos 2D y editor de atajos

Primera versión **estable** que consolida todo lo introducido en la pre-release
v4.7.4 (convención FWHM, deshacer ajuste, previsualización en vivo, intensidades
de doblete/singlete) y añade visualización 2D y atajos configurables.

### Mapas topográficos para distribuciones 2D

- Los ajustes **P(BHF, ΔEQ)**, **P(IS, ΔEQ)** y **P(BHF, IS)** muestran ahora la
  imagen topográfica del resultado P(x, y), que antes se calculaba pero no se
  dibujaba en ninguna parte.
  - **Canvas Matplotlib**: panel inferior con `pcolormesh` + contornos del mapa.
  - **Diálogo emergente**: heatmap principal con marginales P(x)/P(y) en
    disposición *corner-plot* y anotación de medias, sigmas y correlación.
  - **Plotly**: `go.Heatmap` interactivo con `go.Contour` superpuesto y hover
    con los valores exactos de x, y y P.
- El mapa persiste en los re-dibujos y se limpia al cambiar a un modo no-2D,
  lanzar un ajuste discreto o cargar otro fichero.
- Corrección: el ajuste 2D fallaba con `AttributeError` porque el resultado
  expone `alpha_bhf`/`alpha_quad` en vez de un único `alpha`.

### Editor de atajos de teclado

- **Ayuda → Atajos de teclado…**: cuadro para ver, asignar y restablecer los
  atajos de **32 acciones** de los menús Archivo/Ajuste/Vista/Ayuda (traigan o
  no atajo de fábrica). Los cambios se guardan en las preferencias y se aplican
  a los menús al instante; detección de conflictos sobre todos los atajos
  efectivos.
- Corrección: pulsar **Ctrl+Z** (Deshacer ajuste) tras un ajuste discreto
  saltaba indebidamente al modo Distribución P(BHF); ahora deshacer conserva el
  modo activo.

## v4.7.4 — Mejoras de interfaz y convención FWHM *(pre-release)*

### Cambio de convención: Γ pasa a ser FWHM

- **Anchura de línea en FWHM** en toda la aplicación. Hasta ahora Γ representaba
  el semianchura a media altura (HWHM); ahora es la anchura completa (FWHM = 2·HWHM),
  que es la convención habitual en espectroscopía Mössbauer y en los programas de
  referencia (NORMOS, MossWinn).
- La física es idéntica: `lorentzian()` divide γ/2 internamente. Los valores
  visibles en la GUI son el doble de los anteriores (p. ej. α-Fe: 0.28 mm/s en
  vez de 0.14 mm/s).
- Importación Normos (.RES): WID ya se guardaba en FWHM; se elimina la división
  por 2 que existía en `core/folding.py`, `core/data_io.py` y `mossbauer_ws5.py`.
- Todos los valores por defecto, límites, plantillas JSON de `data_sample/`,
  documentación ES/EN/FR y tests actualizados.

### Render en vivo durante el ajuste discreto

- La figura se actualiza en tiempo real mientras corre el optimizador (~4 fps,
  limitado por el throttle de 0,25 s ya existente en el callback de progreso).
- Sin impacto en velocidad: el canvas se repinta con `reconstruct_discrete_model`
  usando los parámetros libres actuales sin tocar los widgets.

### Deshacer ajuste (Ctrl+Z)

- **Ajuste → Deshacer ajuste** (Ctrl+Z): recupera todos los parámetros al estado
  previo al último ajuste (discreto o distribución).
- La acción se habilita al completar el primer ajuste y se deshabilita tras
  deshacer (un solo nivel de undo).

### Corrección: widgets enlazados no se actualizaban visualmente

- Al modificar un parámetro fuente (p. ej. δ del componente 1 enlazado al δ del
  componente 2), el spinbox del parámetro objetivo no mostraba el valor actualizado
  aunque la figura sí se redibujaba correctamente. Corregido en
  `_sync_constraint_targets()` llamado desde `_on_model_param_changed`.

### Arranques múltiples configurables

- **Ajuste → Opciones avanzadas → Arranques múltiples (0–10)**: permite elegir
  cuántas perturbaciones aleatorias se lanzan en el multistart (por defecto 8).
  `0` = un único arranque desde los valores iniciales (ajuste más rápido).
  El valor se guarda en la sesión.

### Intensidades de doblete y singlete

- En **doblete** se oculta `I13` (redundante con la profundidad) y la intensidad
  restante (`I23` → etiqueta «I rel (L2/L1)») pasa a representar la relación entre
  las dos ramas, con valor inicial 1.0 (ramas simétricas) fijo por defecto.
- En **singlete** se ocultan ambas intensidades (`I13`/`I23`): la profundidad ya
  fija el área de la única línea.

### Etiquetas de anchura: global vs relativa

- Γ1 se etiqueta como anchura **absoluta (global, mm/s)** y Γ2/Γ3 como **ratios**
  relativos a ella (`Γ 2,5 / Γ₁`, `Γ 3,4 / Γ₁`), dejando explícito que
  Γ_real = Γ1·Γ2. Las etiquetas se adaptan al tipo de componente (los números de
  línea 1,6 / 2,5 solo aplican al sextete; doblete y singlete usan variantes propias).

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
