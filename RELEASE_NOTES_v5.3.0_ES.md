# Fitbauer v5.3.0

*[🇬🇧 English notes](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.3.0.md)*

Fitbauer abre ya espectros de cualquier espectrómetro sin convertirlos antes y
recuerda cada equipo: cómo leer sus ficheros, cómo doblarlos y qué calibración
de velocidad vale en cada fecha. Esta versión trae además una serie de
arreglos encontrados al ajustar espectros reales ya analizados con WMOSS y
WinNormos, y deja documentado el acuerdo con los dos programas.

**El trabajo existente no cambia.** Los equipos son opcionales; sin ellos, los
ficheros se abren como antes. Las sesiones, plantillas y calibraciones
guardadas se cargan igual que en la v5.2.5.

---

## Importar espectros de cualquier equipo

- **Los ficheros se abren por su contenido, no por la extensión.** Un lector
  genérico localiza el bloque de datos (lo anterior es la cabecera y lo
  posterior el pie), detecta el separador y la coma decimal y deduce qué es
  cada columna: canal, velocidad, intensidad, error o varias cuentas por línea.
  Distingue también cuentas de transmisión o absorción, en fracción o en %.
  Vale para *Cargar…*, arrastrar, recientes, ajuste en serie, ajuste global de
  relajación y comparación de espectros.
- **Nueva ventana de importación** (*Archivo › Importar…*, Ctrl+I). Enseña el
  fichero antes de cargarlo, con los datos resaltados, lo que ha deducido el
  lector y una vista previa del espectro. Todo se puede corregir.
- **Doblar es una elección explícita**, como el `FOLD` de NORMOS: *Doblar*,
  *Sin doblar: un solo barrido* (datos ya doblados por el espectrómetro) o *Sin
  doblar: dos ramas*, más *Invertir sentido* para los equipos que barren de + a
  −. Sin doblar, cada punto es un canal y el ajuste usa σ = √cuentas. El modo
  viaja en sesiones, plantillas, ajustes en serie, comparaciones y la línea de
  órdenes (`--fold`, `--reverse-velocity`). Los `.JOB` con `FOLD=.FALSE.` se
  importan y exportan en consecuencia.
- **Los espectros con eje de velocidad propio** toman el ruido de la columna de
  errores, o lo estiman de los datos, y se ajustan con pesos gaussianos.
- **Los ficheros procesados de WMOSS** (`*.b`, `*.t`, «% absorbance») se leen
  bien, incluida la traza de un solo subespectro.

## Equipos y calibraciones

- **Equipos** (*Archivo › Equipos y calibraciones…*). Un equipo guarda las
  correcciones de importación, la forma de onda, el plegado y el sentido. Puede
  además reconocer sus propios ficheros por un texto de la cabecera o el pie o
  por el nombre, y entonces se aplica solo al abrirlos.
- **Calibraciones por equipo.** Cada equipo guarda sus calibraciones de
  velocidad: fecha desde la que vale cada una, Vmax, patrón del sextete,
  desplazamiento isomérico del α-Fe y una copia del espectro de α-Fe, que se
  puede volver a abrir desde el gestor. Un espectro recibe la calibración
  vigente en su fecha de medida, leída del fichero o, si no la trae, de la
  fecha del fichero, con aviso. Los equipos cuyos ficheros no traen fecha
  pueden usar siempre la más reciente. También se puede elegir a mano.
- **El ajuste en serie, el ajuste global de Néel y la línea de órdenes** usan
  la calibración de cada fichero (`mossbauer_fit_cli.py --instrument NOMBRE`,
  o `--instrument auto`). Las tablas de resultados dicen qué calibración se
  usó en cada fichero.

## Comparación con WMOSS y WinNormos

- **Comparar con ficheros procesados de WMOSS o WinNormos.** Se elige qué
  columna se superpone (datos, ajuste total o un sitio). Un eje con el α-Fe en
  cero se puede llevar a la escala de la fuente con la calibración activa.
- **Los ajustes de espectros reales ya analizados con WMOSS y WinNormos
  coinciden** dentro de la precisión que dan esos programas: δ, ΔEQ y Γ a
  unas milésimas de mm/s y áreas relativas a cerca de un punto.
- **Queda documentado cómo dobla cada programa y qué supone para el χ²**, en
  el manual, la ayuda del programa y `docs/folding.md`. WMOSS dobla con un punto
  de plegado fraccionario y suaviza los datos, así que su χ² reducido no se
  puede comparar directamente con el de Fitbauer o NORMOS en el mismo espectro.

## Arreglos

- **El ruido de un espectro doblado tiene en cuenta la interpolación.** Con un
  punto de plegado fraccionario, Fitbauer interpola entre canales, lo que
  promedia canales vecinos y reduce el ruido. La σ del ajuste no lo descontaba:
  el χ² reducido salía hasta un 24 % bajo y los errores algo grandes. Ahora es
  correcto con cualquier punto de plegado. Los parámetros ajustados no cambian.
- **Dobletes profundos.** Una línea de más del 30 % se quedaba en la cota del
  ajuste y este lo compensaba ensanchando Γ. Ahora la cota se suelta cuando se
  alcanza. Los valores ajustados fuera del rango de un control se muestran en
  vez de recortarse en silencio.
- **El eje de velocidad sigue a la Vmax** cuando se aplica una calibración
  desde el gestor, una sesión o la web, y el siguiente ajuste usa el eje nuevo.
- **El punto de plegado** se limita respecto al número de canales (con 1024
  canales se quedaba en 263). La ventana y la línea de órdenes usan el mismo
  punto de plegado de NORMOS, y solo si es plausible.
- **La ventana, el ajuste en serie y la línea de órdenes usan el mismo eje de
  velocidad** cuando se recortan canales extremos atípicos.
- **La Vmax de un fichero procesado vale solo para ese fichero**, no para los
  espectros en bruto que se abran después.
- **Un componente que pasa a doblete tiene ΔEQ libre.**
- **Una sesión cuya carpeta se ha movido** encuentra su espectro junto a ella.
- Los avisos de carga ya no los tapa el mensaje de «fichero cargado».

## Documentación

Los manuales (español e inglés), la ayuda del programa en 8 idiomas y el
apéndice de la línea de órdenes cubren la importación, los equipos, las
calibraciones, el plegado y la comparación con WMOSS.

---

Suite completa: **933 tests superados**.
