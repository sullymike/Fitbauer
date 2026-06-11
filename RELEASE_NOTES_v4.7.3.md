# Release Notes v4.7.3 — Fitbauer

Versión de mantenimiento centrada en la barra de menús y la ayuda integrada. No cambia la física ni los motores de ajuste.

## Menús reorganizados

- **Desaparece el menú «Opciones».** Era redundante: todas sus entradas existían ya en Ajuste o Vista, y por construcción sus radios/checkmarks no podían reflejar el estado real. Lo que buscabas allí está ahora en un único sitio: modo de ajuste, restricciones y presets en **Ajuste**; residual, leyenda y temas en **Vista**.
- **Menú Ajuste reagrupado** para seguir el flujo de trabajo:
  - `Modo de ajuste ▸` — ahora con los **siete modos** (discreto, P(BHF), P(ΔEQ), P(IS) y los tres 2D), sincronizados con el desplegable del panel en ambos sentidos.
  - `Preparación ▸` — Buscar centro, Inicializar/Editar mínimos, Auto-ajuste, IA local.
  - `Análisis de errores ▸` — Bootstrap, verosimilitud perfilada y L-curve (antes suelta al final del menú).
  - Ajuste en serie, gestión de parámetros (liberar/fijar, restricciones, presets) y Opciones avanzadas.
- **Archivo**: «Abrir recientes» traducido (antes "Open Recent" fijo en inglés) y «Usar como calibración» junto a Cargar.

## Ayuda integrada al día

- El capítulo «Menú Opciones» (ES) se elimina y «Menú Ajuste» se reescribe siguiendo la nueva estructura, con documentación nueva para «Editar mínimos (semi-manual)».
- Todas las rutas «menú → ítem» citadas en la ayuda (ES/EN/FR) se han actualizado y verificado automáticamente: no quedan referencias a menús o posiciones antiguas.

## Verificación

Suite completa de tests en verde (142 tests) y smoke test offscreen de la estructura del menú y la sincronización de modos. Detalle completo en `CHANGELOG.md`.
