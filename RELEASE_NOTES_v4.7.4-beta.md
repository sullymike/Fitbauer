# Release Notes v4.7.4-beta — Fitbauer

Versión pre-release con nuevas funcionalidades de interfaz, cambio de convención de anchura y correcciones.  
No cambia la física de fondo ni los motores de ajuste; todos los resultados son equivalentes.

## Cambio de convención: Γ pasa a FWHM

- **Γ es ahora la anchura completa a media altura (FWHM)**, en línea con NORMOS, MossWinn y la literatura Mössbauer estándar. Hasta ahora representaba la HWHM.
- La física interna no cambia: `lorentzian()` divide γ/2 internamente. Los valores visibles en la GUI son el doble de los anteriores (α-Fe: 0.28 mm/s en vez de 0.14 mm/s).
- Importación Normos (.RES): se elimina la división por 2 que estaba de más en `core/folding.py` y `mossbauer_ws5.py`.
- Todos los valores por defecto, límites, plantillas JSON, documentación ES/EN/FR y tests actualizados.

## Etiquetas de anchura: global vs. relativa

- **Γ1** se etiqueta como anchura **absoluta (global, mm/s)**.
- **Γ2 / Γ3** se etiquetan como **ratios** relativos a Γ1 (`Γ 2,5 / Γ₁`, `Γ 3,4 / Γ₁`), dejando explícito que Γ_real = Γ1·Γ2.
- Las etiquetas se adaptan al tipo de componente: los números de línea (1,6 / 2,5) solo aplican al sextete; doblete y singlete usan variantes propias.

## Render en vivo durante el ajuste discreto

- La figura se actualiza en tiempo real mientras corre el optimizador (~4 fps).
- Sin impacto en velocidad de convergencia: el canvas se repinta con `reconstruct_discrete_model` usando los parámetros libres actuales sin tocar los widgets.

## Deshacer ajuste (Ctrl+Z)

- **Ajuste → Deshacer ajuste** (Ctrl+Z): recupera todos los parámetros al estado previo al último ajuste (discreto o distribución).
- La acción se habilita al completar el primer ajuste y se deshabilita tras deshacer (un nivel de undo).

## Intensidades de doblete y singlete

- En **doblete** se oculta `I13` (redundante con la profundidad); la intensidad restante (`I23`) pasa a representar la relación entre las dos ramas («I rel (L2/L1)»), con valor inicial 1.0 (ramas simétricas).
- En **singlete** se ocultan ambas intensidades: la profundidad ya fija el área de la única línea.

## Arranques múltiples configurables

- **Ajuste → Opciones avanzadas → Arranques múltiples (0–10)**: elige cuántas perturbaciones aleatorias se lanzan en el multistart (por defecto 8). `0` = un único arranque (ajuste más rápido). El valor se guarda en la sesión.

## Corrección: widgets enlazados no se actualizaban

- Al modificar un parámetro fuente enlazado a otro (p. ej. δ del componente 1 → δ del componente 2), el spinbox del parámetro objetivo no mostraba el valor actualizado aunque la figura sí se redibujaba. Corregido en `_sync_constraint_targets()`.

## Verificación

Suite completa de tests en verde y smoke test offscreen de la GUI. Detalle completo en `CHANGELOG.md`.
