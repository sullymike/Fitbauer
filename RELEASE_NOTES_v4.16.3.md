# Fitbauer v4.16.3

Auditoría de la persistencia: cada ajuste de la GUI debe guardarse en la sesión y
restaurarse al cargarla. Afecta a **guardar/cargar sesión**, al **historial de
ajustes** y a **Deshacer ajuste** (los tres comparten el mismo mecanismo).

## Corregido

- **La malla 2D no se persistía**: los controles del eje Y de la distribución 2D
  (`qmin`/`qmax`/`qbins`/`log α_q`) no formaban parte del estado de sesión — al
  recargar volvían a sus valores por defecto. Ahora se guardan y restauran.
- **Las casillas «Fijo» de calibración no se restauraban**: `baseline`, `slope` y
  `sat_scale` guardaban su estado fijo/libre en la sesión pero al cargarla solo se
  restauraban las de los componentes (y σ vía «Ajustar σ»). Ahora también las tres
  de calibración.

## Blindaje

Test nuevo de **ida y vuelta completa**: guardar → cargar → guardar debe
reproducir el `model_state` exactamente, con lo que cualquier deriva futura entre
guardado y restauración hará fallar la suite. Suite completa: 280 tests en verde.

## Documentación

- Manuales ES y EN: documentadas la casilla «Ajustar folding point dentro del
  ajuste» (§ El folding y el centro) y el diálogo «Historial de ajustes»
  (§ Herramientas de ayuda al ajuste); PDFs recompilados.
- Verificado que la ayuda in-app cubre en los 7 idiomas el folding point
  ajustable, sesiones, historial, absorbente grueso/saturación, L-curve,
  bootstrap, verosimilitud perfilada, CLI, mínimos y batch.
