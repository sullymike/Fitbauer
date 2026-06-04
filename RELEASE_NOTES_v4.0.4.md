# Fitbauer v4.0.4

Versión de mantenimiento centrada en el ajuste combinado de distribuciones hiperfinas con componentes nítidos.

## Componentes nítidos con profundidad fija

- En los ajustes de distribución `P(BHF)` / `P(ΔEQ)`, la profundidad de un componente nítido marcada como **fija** se respeta ahora también en el backend.
- Físicamente, un nítido fijo se trata como una contribución de absorción conocida que se resta del modelo:

  ```text
  transmisión = fondo − distribución − nítidos_libres − nítidos_fijos
  ```

- Los nítidos con profundidad libre conservan el comportamiento anterior: su amplitud se ajusta con restricción `>= 0`.
- La corrección se aplica a todas las formas de distribución: histograma/Tikhonov, gaussiana, binomial y distribución fija.

## Subespectros visibles en distribución + nítidos

- Al ajustar una distribución con componentes nítidos, el gráfico muestra ahora los subespectros:
  - contribución de la distribución sola (`P(BHF)` o `P(ΔEQ)`),
  - cada componente nítido por separado,
  - ajuste total.
- Esto facilita diagnosticar si la absorción se reparte correctamente entre la distribución y los componentes discretos.

## Pruebas

- Añadidas pruebas de backend para verificar que una profundidad nítida fija no se reajusta y que una profundidad libre sigue ajustándose.
