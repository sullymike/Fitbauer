# Changelog

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
