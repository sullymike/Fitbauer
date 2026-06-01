# Changelog

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
