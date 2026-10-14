# Fitbauer v5.2.2

*[🇬🇧 English notes](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.2.2.md)*

Una versión de compatibilidad con NORMOS-DIST y de estadística coherente: las
distribuciones de Czjzek de NORMOS se importan con la forma equivalente, las
mallas importadas caen exactamente en los nodos de NORMOS y todas las formas de
distribución ponderan el ajuste con la incertidumbre de los datos.

---

## NORMOS-DIST

- **Se trasladan los trabajos de Czjzek.** Una sonda del binario de
  NORMOS-DIST (09.09.1993) muestra que `DISTRI=4` con `METHOD=6` usa
  exactamente la misma P ∝ ΔEQ⁴·exp(−ΔEQ²/2σ²) que la forma Czjzek de
  Fitbauer, con **σ² = STG² + DTQ²**: NORMOS ensancha su STG con el paso de la
  malla (comprobado al 1e-5 con pasos de 0.06 a 0.36 mm/s, sin depender de QUA
  ni de WID). Esos `.JOB` se importan ahora con la forma Czjzek y un aviso con
  el σ equivalente; antes pasaban a histograma. Con otro `METHOD`, o con
  sextetes de campo fijo, siguen importándose como histograma.
- **Las mallas importadas caen en los nodos de NORMOS.** NORMOS calcula sus
  subespectros en QUA + k·DTQ (o BHF + k·DTB…). El importador pasaba ese rango
  como bordes de la malla, mientras que Fitbauer coloca los nodos en los
  centros de los bins: quedaban desplazados medio paso y con un paso
  (NSB−1)/NSB del de NORMOS (0.173 en lugar de 0.18 mm/s con NSB = 25). Ahora
  los centros de los bins caen exactamente en los nodos de NORMOS. **Cambian
  los resultados de los trabajos de DIST importados.**

## σ y ΔEQ₀ de Czjzek se pueden fijar

Nuevos controles **σ Czjzek** y **ΔEQ₀ ordenado** en el panel de distribución
(solo con las formas de Czjzek): dan el punto de partida del ajuste, recogen los
valores ajustados y, con su casilla **Fijo**, no se ajustan. Así se reproduce un
STG fijo de NORMOS: el importador pone σ = √(STG² + DTQ²) en el control y lo
fija si el `.JOB` trae `STGFIT=.FALSE.`. Los dos se guardan en la sesión. En el
CLI: `--czjzek-sigma`, `--czjzek-delta0`, `--fix-czjzek-sigma` y
`--fix-czjzek-delta0`.

## Correcciones

- **Gaussiana, VBF, Binomial y Fija ponderan el ajuste con la σ de los
  datos.** El histograma, el Czjzek y las formas 2D ya lo hacían; estas cuatro
  daban el mismo peso a todos los canales. Los errores y la covarianza de la
  media y la anchura de P quedan ahora en la misma escala para todas las
  formas. **Cambian ligeramente los resultados de esas formas.**
- **Errores de los globales en 2D cuando se agota el presupuesto de
  evaluaciones.** En ese caso el histograma 2D dejaba δ, ΔEQ y Γ sin error;
  ahora la jacobiana se calcula en el mejor punto. Ese paso extra aparece en la
  barra de progreso con su propio contador.
- **El estilo de gráfico «clásico» heredaba el anterior:** letra serif, ticks
  hacia dentro y leyenda con marco tras «publicación».
- **Caída de la suite de tests en CI.** Los tests pasaban y luego el proceso
  moría con un fallo de segmentación al cerrar Python, porque PySide6
  destruía los objetos Qt en mal orden. La suite cierra ahora sus widgets y
  termina limpia.

## Documentación

La ayuda (ocho idiomas), los dos manuales, `BHF_DISTRIBUTION.md`, las notas de
NORMOS y la wiki recogen todo lo anterior.

---

Suite completa: **735 tests en verde**.
