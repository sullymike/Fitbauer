# Changelog

## v4.0.2 — Calibración de α-Fe unificada a 33.0 T

- Se elimina la constante interna `32.95 T` y se unifica toda la calibración al campo hiperfino **publicado de α-Fe a temperatura ambiente: 33.0 T (330 kOe)**.
- Afecta a la fórmula de posiciones del sextete (`fe57_sextet_positions`), a `LINE_POS_33T` (núcleo y módulo de distribución) y a la autocalibración de velocidad/campo de la interfaz Tk (la Qt ya usaba `BHF_DEFAULT_T`).
- Consecuencia: un espectro de α-Fe ideal autocalibra ahora exactamente a 33.0 T (antes ~32.95 T). El BHF informado se desplaza ≈ 0,15 % (~0,05 T) y queda consistente con NORMOS.

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
