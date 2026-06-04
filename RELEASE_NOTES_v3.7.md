# Mossbauer v3.7

Release estable. La versión local del programa pasa a `3.7`.

## Resumen

El foco de esta versión está en el **informe Markdown/PDF** (ahora reproduce todo el panel "Estado y parámetros" como tablas reales, con análisis de áreas, diagnóstico residual, magnitudes físicas por componente y δ corregidos por calibración) y en el **diálogo de Ayuda** (árbol jerárquico que sigue la estructura real de menús, buscador con resaltado, HTML enriquecido y negrita automática para las etiquetas de menú). Además, los sextetes en modo de intensidades por **textura** muestran las tres magnitudes físicas derivadas de `t = sin²θ` con sus σ propagadas.

## Cambios principales desde v3.6

### Plotly / Qt

- El gráfico Plotly ocupa todo el alto del tab (en vez de un `72vh` fijo).
- Eliminado el debounce de 300 ms al actualizar parámetros: el gráfico se refresca de forma inmediata.

### Sextete: textura interpretada

- Para sextetes en modo de intensidades por **textura** (donde `I₂/I₃ = 4t/(2-t)`), se calculan y muestran tres magnitudes derivadas de `t = sin²θ`:
  - **θ** = `arcsin(√t)`: ángulo entre el campo hiperfino y el rayo γ (54.7° = ángulo mágico para muestra random `t = 2/3`).
  - **R₂₃** = `4t/(2-t)`: razón de intensidades I₂/I₃ que se reporta habitualmente.
  - **S** = `1 − 3t/2`: parámetro de orden tipo Hermans (+1 alineado a γ, 0 isótropo, −½ perpendicular).
- Cada magnitud lleva su σ propagada a partir de σ(t) cuando t es libre en el ajuste.
- Aparecen en el cuadro "Estado y parámetros" tras cada ajuste o cambio de t.

### Informe Markdown/PDF

El informe ahora reproduce **toda** la información del panel "Estado y parámetros" como tablas estructuradas. Secciones nuevas o completadas:

- **📁 Espectro y plegado** (canales, folding centro y Normos, pares doblados, normalización, perfil).
- **🎛️ Calibración y escala de velocidades** (Vmax, baseline, slope, fit_velocity, origen / muestra / fichero, Vmax calibrado, δ ref, fecha, σ).
- **📐 Bondad y diagnóstico** (χ², χ²ᵣ, dof, AIC, BIC, RMS, multistart, tabla del **diagnóstico residual** con lag-1, runs z y correlación antisimétrica con sus umbrales y aviso automático, correlación máxima y pares muy correlacionados).
- **🥧 Análisis de áreas por componente** con porcentaje, **σ propagada** y área absoluta.
- Por componente, subbloque **Magnitudes físicas derivadas** (Γ HWHM reales, FWHM equiv., Γ relativas, profundidad, I₁/I₂/I₃ reales, BHF, δ, ΔEQ, δ corregido destacado).
- **🧭 Magnitudes derivadas de la textura** con tabla y callout explicando t, θ, R₂₃ y S.
- **🎯 δ corregidos por calibración**: tabla resumen con δ ajustado vs. δ corregido.
- **🔒 Parámetros fijados** y **🔗 Restricciones** como bloques dedicados.
- **📖 Glosario de parámetros** al final del informe.

### PDF rediseñado

- **Portada** con banner de color, fichero, fecha y cuadros de χ²ᵣ, χ², AIC, BIC, nº de componentes y nº de parámetros libres.
- Cuerpo parseado en **bloques tipados** (h3, párrafo, callout, código y **tablas reales**) en vez del volcado monoespaciado anterior.
  - Tablas con encabezado a color, filas zebra, anchos proporcionales al contenido y truncado con elipsis.
  - Callouts con barra lateral de color.
  - Emojis se filtran para evitar glifos vacíos (DejaVu no los renderiza).
- Banner de color en cada sección.

### Diálogo de Ayuda

- **Árbol jerárquico** que refleja la estructura real de menús del programa:
  - 🚀 Visión general (Inicio, Atajos y flujo rápido)
  - 📁 Menú Archivo (Menú Archivo, Archivo y web, Guardar y exportar)
  - 🧮 Menú Ajuste (Menú Ajuste, Restricciones, Estadística y ajuste, CLI)
  - 🎛️ Menú Opciones (Menú Opciones, Perfil de línea)
  - 👁️ Menú Vista (Menú Vista)
  - ❓ Menú Ayuda (Menú Ayuda, Acceso a opciones, Novedades v0.2)
  - 🔬 Conceptos físicos (Espectroscopía, Modelo discreto, Folding, Diagnóstico, Referencia)
  - 📊 Distribuciones P(BHF) / P(ΔEQ) (los 6 capítulos)
- **Buscador** que filtra el árbol y resalta los aciertos en el panel de contenido con `<mark>`; cuenta los resultados.
- **HTML enriquecido**: subtítulos h4 (líneas terminadas en `:`), listas con viñetas / numeración, **negrita**, *cursiva* y `código` inline.
- **Negrita automática para etiquetas de menú** (Archivo, Ajustar, Restricciones entre parámetros, Perfil de línea…) basada en regex case-sensitive construido a partir del catálogo de strings del idioma activo.
- Tipografía mejorada (h2/h3 con jerarquía visual, padding generoso, h3 subrayado). Diálogo 1180×760, splitter 340/840.

## Compatibilidad

- Compatible con sesiones, plantillas y datos de v3.x.
- Sin cambios en formatos de fichero ni en el motor de ajuste; las novedades son de presentación (informe y ayuda) y de cálculo derivado (textura).
- Mantiene las interfaces Tk y Qt/Plotly.
