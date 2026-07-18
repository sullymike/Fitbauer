# Fitbauer v4.16.2

Auditoría sistemática de todo lo ajustable: se comprobó el camino completo
widget → estado → motor → resultado → widget para cada parámetro (calibración,
componentes, distribución y sesiones). Dos huecos encontrados y corregidos, del
mismo patrón que el del folding point en v4.16.1.

## Corregido

- **`sat_scale` no se volcaba tras el ajuste**: con modelo de absorbente grueso y
  la casilla «Fijo» desmarcada, el motor ajustaba la escala de saturación pero la
  GUI no escribía el valor ajustado en el widget de calibración. Ahora sí.
- **Cargar sesión / deshacer ajuste no re-doblaba con el centro guardado**: la
  restauración doblaba los datos con el centro auto-detectado y ponía el centro de
  la sesión solo en el widget — datos y widget quedaban incoherentes (relevante
  tras guardar una sesión con centro ajustado). Ahora, si el centro de la sesión
  difiere del auto-detectado, los datos se re-doblan con él.

## Verificado sin cambios

- Modo discreto: `baseline`, `slope`, `vmax` («Ajustar velocidad», con recálculo
  del eje), σ-Voigt («Ajustar σ»), todos los parámetros de componentes y los
  targets de restricciones lineales se vuelcan correctamente a la GUI.
- Modo distribución: δ/ΔEQ/Γ globales, pendientes de correlación δ(H)/ΔEQ(H),
  parámetros de componentes nítidos y sus pesos, respetando las casillas «Fijo».

Tests de regresión nuevos en `tests/test_qt_app.py`; suite completa: 279 en verde.
