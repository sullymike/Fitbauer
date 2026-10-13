# Fitbauer v5.2.0

*[🇬🇧 Release notes in English](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.2.0.md)*

Una versión centrada en las distribuciones: P(ΔEQ) y P(IS) usan ya el núcleo
correcto, la forma binomial es la de NORMOS, los modos 2D ganan formas
gaussianas, el gráfico de la distribución muestra bandas de error honestas y los
ajustes son mucho más rápidos. Toda la interfaz, los informes y la ayuda están
ya en los ocho idiomas.

---

## Distribuciones

- **P(ΔEQ) y P(IS) usan dobletes / singletes.** Su núcleo eran sextetes al campo
  fijo del panel (33 T por defecto) y la vista previa dibujaba el modelo
  discreto. P(ΔEQ) y P(IS, ΔEQ) usan ahora dobletes (B = 0); P(IS), singletes o
  dobletes con el ΔEQ global, como el METHOD=8 de NORMOS-DIST. Los sextetes con
  campo fijo quedan como opción avanzada. Las sesiones antiguas que guardaban un
  campo reproducen su ajuste. **Cambian los resultados** de los ajustes P(ΔEQ)/
  P(IS) hechos con el valor por defecto anterior.
- **Forma binomial como en NORMOS-DIST** (`DISTRI=3` con `CONC`): n posiciones
  vecinas (12 por defecto), concentración de soluto c y n+1 subespectros en
  «valor sin vecinos + k·cambio por vecino», con pesos binomiales que coinciden
  con los del binario de NORMOS. Vale para BHF, ΔEQ e IS. La forma «Binomial»
  anterior no tenía relación con ningún número de vecinos, así que **cambian los
  resultados** de las sesiones que la usaban. El importador de `.JOB` traslada
  `CONC`, `BHF` y `DTB`.
- **Formas Gaussiana y VBF en 2D.** Además del histograma regularizado, los
  modos 2D ajustan una gaussiana bivariante (μx, μy, σx, σy y correlación ρ) o N
  de ellas (VBF, una por sitio). δ, ΔEQ y Γ se ajustan en el mismo problema, así
  que tarda segundos.
- **Cotas de anchura de las gaussianas.** En las formas Gaussiana y VBF (1D y 2D)
  la anchura σ, común a todas las gaussianas, se puede acotar con **σ mín /
  σ máx** (un par por eje en 2D; 0 = automático). Útil cuando una gaussiana
  colapsa en un pico o se ensancha hasta absorber el fondo.
- **Banda 1σ de P.** La ayuda prometía una banda 1σ alrededor del histograma que
  ningún gráfico dibujaba, y la covarianza linealizada en que se basaba ignora
  P ≥ 0: con picos rodeados de bins vacíos salía de 2 a 16 veces más ancha. La
  banda es ahora un Monte Carlo paramétrico (100 reajustes con ruido, unos
  0.05 s), validado frente a reajustes independientes. Una casilla la oculta.
- **Curva de correlación δ(x) / ΔEQ(x).** Con una pendiente κ distinta de 0 (por
  ejemplo el acoplamiento δ(ΔEQ) de Rancourt–Ping en P(ΔEQ)), el gráfico de la
  distribución dibuja en un eje derecho la recta que aplicó el núcleo, con su
  banda 1σ y κ ± σ en la leyenda. Una casilla la oculta.
- **El panel enseña solo lo que aplica**: la distribución activa en el título,
  la física del núcleo solo donde se usa, las pendientes de correlación con su
  significado y unidades, y cada variable recuerda su malla.
- **Avisos que se explican.** P(IS) con Γ libre, P(ΔEQ) con sextetes de campo
  fijo y P(IS, ΔEQ) con dobletes (cuyo mapa no es único) terminan en «Más
  información…», que abre un capítulo nuevo de la ayuda en la sección que
  explica por qué ocurre y qué hacer.

## Línea de comandos

- `fit_bhf_distribution_cli.py` ajusta las tres parejas 2D con
  `--pair bhf-quad|delta-quad|bhf-delta`, las formas gaussianas 2D con
  `--dist-2d --shape gaussiana|vbf`, la binomial de NORMOS con `--binomial-*`, y
  acota la anchura de las gaussianas con `--vbf-sigma-min/--vbf-sigma-max`
  (variantes `-y` para el segundo eje 2D).
- `--scan-alpha` barre ahora exactamente el mismo modelo que el ajuste (ignoraba
  el anclaje de bordes, D13/D23, el tratamiento del núcleo y la fuente
  polarizada).

## Ajustes mucho más rápidos

Medido en un equipo de 14 núcleos:

- P(BHF) con δ, ΔEQ y Γ libres: de 30 s a 0.6 s. OpenBLAS repartía cada
  operación entre todos los núcleos, y con matrices tan pequeñas eso costaba
  cien veces más que el cálculo; BLAS usa ahora un hilo (`OPENBLAS_NUM_THREADS`
  sigue mandando si lo fija).
- P(BHF, ΔEQ) 2D: de más de 30 min a unos 1.5 min, con un resolvedor de mínimos
  cuadrados no negativos más rápido que llega al mismo óptimo.
- Los ajustes con globales o nítidos libres ya no parecen no terminar: el tope de
  evaluaciones cuenta todas las evaluaciones y la barra de progreso lo refleja.

## Ocho idiomas en todo

La interfaz ya no tiene textos fijos en español: diálogos, barra de estado,
informes (completo y reducido, Markdown y PDF), el diálogo de límites de
parámetros, los mensajes de progreso y de error, los avisos de importación de
NORMOS y las notas del motor siguen el idioma elegido. Los botones y diálogos
propios de Qt («Cancelar», «Abrir»…) también se traducen. La ayuda integrada se
ha retraducido para que los ocho idiomas tengan los mismos 32 capítulos en el
mismo orden.

## Documentación

- El manual en español tiene ya el anexo *Herramientas de línea de comandos*, y
  los dos manuales cubren todo lo anterior.
- Los anexos del manual son la única fuente de la matemática; se retiran los
  `.tex`/`.pdf` sueltos de `docs/`, que iban por detrás de ellos.
- `BHF_DISTRIBUTION.md`, el README y el wiki están al día.

## Correcciones

- **Cancelar** se perdía durante el escalado global automático (evolución
  diferencial) del ajuste discreto, y en VBF 2D solo respondía entre pasos.
- El mapa 2D bajo el espectro no se refrescaba tras un segundo ajuste 2D.
- En los modos 2D se refinaba un δ libre aunque IS fuera un eje del mapa.
- «Ligar δ» y «Ligar Γ1» solo ataban los componentes 2 y 3; ahora atan todos
  los componentes activos.
- El control de polarización de Blume–Tjon mostraba una clave interna como
  etiqueta.
- La ayuda del plegado se contradecía sobre el recorte de los bordes.

---

Suite completa: **704 tests en verde**.
