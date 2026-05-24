# Mössbauer Fe-57 GUI v0.4.5

Patch release sobre v0.4.4 que amplía los rangos físicos de BHF y AEQ.

## Cambios

- **BHF hasta 60 T.**
  Los sliders de campo hiperfino magnético pasan de 50 T a 60 T en todos los modos:
  - `BHF` en sextetes discretos (componentes 1, 2 y 3).
  - `BHF fijo` en el modo distribución P(BHF).
  - `B mín` del rango de integración de la distribución.

- **AEQ con valores negativos (rango −4 a +4 mm/s).**
  El desplazamiento cuadrupolar puede ser negativo en función de la simetría del gradiente de campo eléctrico. Los sliders `AEQ` (sextetes discretos) y `ΔEQ fijo` (distribución P(ΔEQ)) pasan de [0, 4] a [−4, 4] mm/s.

## Sin otros cambios

El algoritmo de ajuste, los formatos de fichero y la API web no se modifican.
