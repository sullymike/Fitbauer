# Release Notes v4.7.5 — Fitbauer

Versión **estable** que consolida la pre-release v4.7.4 (convención FWHM, deshacer
ajuste, previsualización en vivo, intensidades de doblete/singlete) y añade dos
funcionalidades nuevas: la visualización de distribuciones 2D y un editor de
atajos de teclado. No cambia los motores de ajuste.

## Mapas topográficos para distribuciones 2D

Los ajustes **P(BHF, ΔEQ)**, **P(IS, ΔEQ)** y **P(BHF, IS)** ya muestran la imagen
topográfica del resultado P(x, y) — antes se calculaba pero no se dibujaba.

- **Canvas Matplotlib**: panel inferior con `pcolormesh` y contornos del mapa.
- **Diálogo emergente**: heatmap principal con marginales P(x)/P(y) en disposición
  *corner-plot* y anotación de medias, sigmas y correlación.
- **Plotly**: `go.Heatmap` interactivo con `go.Contour` superpuesto; el hover
  muestra los valores exactos de x, y y P.
- El mapa persiste en los re-dibujos y se limpia al cambiar a un modo no-2D,
  lanzar un ajuste discreto o cargar otro fichero.
- Corregido el `AttributeError` que rompía el ajuste 2D (el resultado expone
  `alpha_bhf`/`alpha_quad`, no un único `alpha`).

## Editor de atajos de teclado

- **Ayuda → Atajos de teclado…**: cuadro para ver, asignar y restablecer los
  atajos de **32 acciones** de los menús Archivo / Ajuste / Vista / Ayuda, traigan
  o no atajo de fábrica. Los cambios se guardan en las preferencias y se aplican a
  los menús al instante, con detección de conflictos sobre todos los atajos
  efectivos.
- Corregido: pulsar **Ctrl+Z** (Deshacer ajuste) tras un ajuste discreto saltaba
  indebidamente al modo Distribución P(BHF); ahora deshacer conserva el modo activo.

## Incluido desde v4.7.4

- **Convención FWHM**: Γ es la anchura completa a media altura (como NORMOS /
  MossWinn). Γ1 se etiqueta como anchura absoluta (global) y Γ2/Γ3 como ratios.
- **Deshacer ajuste (Ctrl+Z)** discreto o de distribución.
- **Render en vivo** durante el ajuste discreto (~4 fps).
- **Intensidades de doblete/singlete** simplificadas (relación entre ramas).
- **Arranques múltiples configurables** (0–10) en Opciones avanzadas.

## Verificación

Suite completa de tests en verde (146 tests), incluido un test end-to-end del
ajuste 2D y el golden test headless del núcleo de ajuste. Detalle completo en
`CHANGELOG.md`.
