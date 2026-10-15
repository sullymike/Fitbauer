# Fitbauer v5.2.4

*[🇬🇧 English notes](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.2.4.md)*

Una versión de correcciones. Al comparar con NORMOS más a fondo, trabajo a
trabajo y volviendo a ejecutar el propio NORMOS, se vio que importar un `.JOB`
no siempre reconstruía el mismo modelo que NORMOS había ajustado. Esta versión
lo corrige, y corrige también las cifras de validación de la v5.2.3.

**Si importaste `.JOB` de NORMOS con la v5.2.3 o anteriores, vuelve a
importarlos.** Los ajustes podían tener más parámetros libres que en NORMOS, y
el campo hiperfino estaba en una escala algo distinta.

---

## Correcciones en la importación de `.JOB`

- **Solo queda libre lo que el `.JOB` libera.** En NORMOS, todo parámetro sin
  `…FIT=.TRUE.` está fijo. El importador solo trasladaba las banderas de ISO,
  QUA, BHF, WID y DEP. Todo lo demás —intensidades y anchuras relativas (D13,
  D23, W13, W23, D21, W21), ETA, THE, PHI, BEX, GAX y la pendiente del fondo
  (`BKGFIT`)— quedaba como estuviera en la sesión, libre por defecto. Fitbauer
  podía acabar ajustando 11 variables donde NORMOS ajustaba 6.
- **Razones de intensidad por área.** D13/D23/D21 son razones de área. Antes se
  convertían en razones de profundidad, y liberar W13/W23 liberaba también las
  intensidades. Ahora pasan tal cual a int1/int2 con el convenio de
  intensidades por área.
- **Se activan los convenios de NORMOS.** Al importar se activan el patrón de
  líneas de NORMOS (derivado de los momentos nucleares), las intensidades por
  área y su regla de relajación, y el trabajo da los valores de NORMOS. Con el
  patrón de α-Fe que se usaba antes, el campo salía un 0.035 % más bajo: unos
  0.01 T a 33 T, más que el error de un buen ajuste. **Al cargar después otro
  espectro se vuelve a los convenios de Fitbauer**, salvo que los hayas elegido
  a mano en *Ajuste › Opciones avanzadas de ajuste › Convenios (compatibilidad
  NORMOS)*.
- **Ligaduras.** Al importar, las ligaduras de WID tienen ya en cuenta la
  escala de W13, y las de W13/W23 de un sextete van a los parámetros de anchura
  correctos (estaban cruzados).

## Corrección en la exportación a `.JOB`

- **Se escriben las ligaduras** (`NDEX`/`FACTOR`/`CONST`). Antes se perdían.
  Se ha comprobado que NORMOS las acepta y ajusta con las mismas variables.

## Cifras de validación corregidas

Las notas de la v5.2.3 decían que, en 216 trabajos reales de NORMOS, Fitbauer
llegaba al mismo χ² o a uno menor en 211 (χ² reducido mediano 1.08 → 0.81).
Esas cifras venían de fallos de la propia comparación: la importación liberaba
parámetros que NORMOS tenía fijos, el reajuste usaba el patrón de líneas de
α-Fe, Fitbauer doblaba los datos de otra forma y el χ² se calculaba sobre la
media de cada par de canales, lo que daba la mitad del de NORMOS.

Rehecha con los datos doblados exactamente como los dobla NORMOS, el mismo
modelo y los mismos parámetros libres, el χ² de NORMOS se reproduce al ~1 %. De
407 trabajos reales distintos, 146 son una referencia válida. Los otros 261 se
descartan:

- 214 porque el χ² reducido de NORMOS pasa de 2;
- 19 porque los dos programas no ven exactamente los mismos datos;
- 28 porque no se pueden analizar (ficheros que faltan, opciones no
  admitidas).

En los 146:

- Fitbauer llega al mismo χ² o a uno menor en todos (mediana 1.40 → 1.38).
- El acuerdo mediano es de 0.0006 mm/s en δ, 0.0015 mm/s en ΔEQ, 0.0034 T en
  BHF y 0.0014 mm/s en Γ: entre 0.15 y 0.2 veces los errores del propio
  NORMOS, y sin sesgo.
- Las pocas diferencias de más de tres errores son ajustes en los que NORMOS se
  había parado antes del mínimo. Arrancado desde la solución de Fitbauer,
  NORMOS llega al mismo χ².

## Limitaciones conocidas

Siguen ahí. Donde se indica, la importación avisa cuando se dan.

- **Anchuras relativas de un sextete.** NORMOS usa WID (líneas 3–4) con W13 y
  W23 relativas a ella; Fitbauer usa Γ1 (líneas 1–6) con Γ2/Γ1 y Γ3/Γ1.
  - Lo libre y lo fijo se trasladan exactamente cuando WID, W13 y W23 son todos
    fijos, cuando solo WID es libre o cuando lo son los tres.
  - Con W13 libre y WID o W23 fijos, Fitbauer tiene uno o dos parámetros de
    anchura libres más que NORMOS (avisa).
  - Las ligaduras sobre W13/W23 no se exportan. Al importar, solo es exacta una
    ligadura de factor 1 entre valores de W13.
- **Ligaduras de área** (`NDEX` sobre DEP/ARE): son exactas en los valores del
  `.JOB`. Si el ajuste cambia las anchuras, la razón de áreas deriva un poco
  (avisa).
- **Doblado.** Fitbauer dobla en el punto de doblado refinado, interpolando
  entre canales, y descarta los canales muertos de los bordes. NORMOS suma
  pares de canales enteros en ⌊PFP⌋ + 0.5. Las anchuras de línea pueden salir
  unos 0.005 mm/s más estrechas que en NORMOS. Cuando el punto de doblado de
  NORMOS está a más de un canal del centro del espectro, sus canales de borde
  no se reproducen exactamente.
- **No se trasladan al importar**, como antes (avisa):
  - la ligadura sobre `OME` de la relajación de Ising;
  - el modelo de Billard–Chamberod (`METHOD=3`);
  - varios bloques de distribución en un mismo trabajo;
  - el parámetro de suavizado absoluto `LAMDA` (usa la curva L).
- **No se escriben al exportar:** los tratamientos hamiltonianos, la
  relajación y las formas de distribución. El `.JOB` exportado es un punto de
  partida para NORMOS, no una traducción exacta de cualquier modelo.

---

Suite completa: **763 tests en verde**.
