# Interoperabilidad con NORMOS: ficheros `.JOB`

Módulo: `core/normos_job.py` (funciones puras) · GUI: **Archivo ▸ NORMOS (.JOB)**

---

## Qué es y por qué

NORMOS (R. A. Brand, 1990-1994) es el programa con el que se ha analizado buena
parte de la bibliografía Mössbauer publicada. Corre bajo DOS, es propietario y ya
no se mantiene, pero muchos laboratorios guardan años de trabajo en ficheros
`.JOB`.

Fitbauer lee y escribe ese formato. **No ejecuta NORMOS ni lo distribuye**: solo
habla su formato de texto, que no es propietario.

---

## Importar

**Archivo ▸ NORMOS (.JOB) ▸ Importar trabajo de NORMOS…**

Reconstruye el modelo en los paneles **y carga el espectro**. Un `.JOB` nombra sus
ficheros en las cuatro primeras líneas, sin ruta, porque NORMOS corría en DOS con
todo en el mismo directorio:

```text
Fe080725.ws5      ← espectro
distcri1.JOB      ← el propio trabajo
Fe0807di.res      ← resultados que escribirá NORMOS
Fe0807di.plt      ← gráfico
 &DATA
 NLTEXT=4, VMAX=-11.966, TRIANG=.true.,
 &END
```

`resuelve_fichero_de_datos()` busca el espectro junto al `.JOB` sin distinguir
mayúsculas de minúsculas —los nombres vienen de DOS y rara vez coinciden en caja
con los del disco—, y si el declarado no aparece prueba con el nombre del propio
trabajo y, en último caso, con el único espectro de la carpeta. Nunca devuelve una
salida de NORMOS (`.RES`/`.PLT`).

> **Deja todos los ficheros del trabajo en la misma carpeta.** Es lo que NORMOS
> espera y lo que hace que la importación funcione de una vez.

Se reconocen solas dos familias:

| Familia | Qué son sus subespectros | Dónde acaba |
|---|---|---|
| **NORMOS-SITE** | sitios discretos | componentes singlete / doblete / sextete |
| **NORMOS-DIST** | los puntos de una **malla** | panel P(BHF)/P(ΔEQ) |

En los de DIST se traduce la malla (origen y paso), la forma (histograma,
gaussiana, binomial, fija, Czjzek o Le Caër), la correlación δ(x) y los anclajes de borde;
los subespectros «cristalinos» (`NXLS`) pasan a ser componentes nítidos. NORMOS
calcula cada subespectro en un nodo (origen + k·paso) y Fitbauer en el centro de
cada bin, así que los bordes de la malla importada quedan medio paso por fuera
del primer y el último nodo: los centros caen exactamente en los nodos de NORMOS.

## Exportar

**Archivo ▸ NORMOS (.JOB) ▸ Exportar trabajo de NORMOS…** escribe el modelo actual
en formato NORMOS. Se ha comprobado que **NORMOS acepta el fichero que produce
Fitbauer** y reproduce la teoría original con diferencia exactamente cero.

---

## Conversiones de convenio

Es la parte delicada, y equivocarse aquí no da ningún error:

| NORMOS | Significado en Fitbauer |
|---|---|
| `WID`, `W13`, `W23` | `WID` es la anchura de las líneas 3,4 y `W13`/`W23` son relativas a ella; `gamma1` es la de las líneas 1,6. La conversión es `gamma1 = WID·W13` |
| `D13`, `D23` | Razones de **área**. `int1`/`int2` son razones de **profundidad**. Coinciden solo si las anchuras son iguales |
| `DEP` (o `ARE`) | El **área** del subespectro en mm/s, no una profundidad |
| `NDEX`/`FACTOR`/`CONST` | Ligaduras en la numeración **global** de NORMOS, `13 + 15·(n−1)` |

### La escala de BHF

NORMOS deriva las posiciones del sexteto de los momentos nucleares; Fitbauer usa el
patrón publicado de α-Fe. No difieren en un simple factor de escala. Para
reproducir un BHF suyo exactamente, ajusta con el convenio de NORMOS activo:

```python
from core.constants import sextet_pattern

with sextet_pattern("normos"):
    ...   # el ajuste usa las posiciones de NORMOS
```

La diferencia es de unos 0,1 T.

---

## El punto de doblado no se impone

El `PFP` que trae el `&DATA` es la **semilla** de la búsqueda del punto de doblado,
no su resultado: NORMOS lo refina en dos ciclos, y en trabajos reales acaba a más
de un canal de lo que pedía el fichero. Fitbauer hace su propia búsqueda —que es el
análogo correcto— e informa del `PFP` solo como dato.

Hay una segunda sutileza. El punto refinado que NORMOS **imprime** en su `.RES`
tampoco es donde dobla. Al doblar, NORMOS pasa ese punto a un número entero de
canal truncándolo, y suma después los canales a pares, a la misma distancia a un
lado y otro de ese entero. Los índices de cada par suman `2·⌊PFP⌋ + 1`, de modo que el eje de
simetría efectivo cae en `⌊PFP⌋ + 0,5`, y no en el valor impreso. Está
en `core.normos_job.punto_de_doblado_normos()`, y tenerlo en cuenta es lo que
permite reproducir sus ajustes.

### Signo de VMAX

En NORMOS un `VMAX` negativo invierte el espectro, y Fitbauer hace lo mismo (eje de
velocidad invertido); el importador conserva el signo y avisa. Hasta ahora tomaba
su valor absoluto y esos trabajos se abrían reflejados, con δ de signo cambiado.

### Relajación de Ising (`IRELAX`)

Un subespectro con `IRELAX(i)=.TRUE.` se importa como componente **Blume–Tjon**:
`OME` (MHz) = 2ν, la polarización es `P = BHF/BSAT` (el demo de 1994 la llama
`BH0`) y el campo externo `BEXT` pasa a «Campo externo BEXT». Las equivalencias
están validadas contra el binario de SITE. Con `P > 0` NORMOS usa su propio
convenio de tasas, disponible en Ajuste ▸ Opciones avanzadas de ajuste ▸
Convenios.

---

## Lo que no se traslada

El importador avisa de cada uno de estos puntos, porque lo que **no** se ha
traducido importa tanto como lo que sí:

- `DISTRI=4` (Czjzek y Le Caër) **sí** se traslada. Con `METHOD=7` va a la forma
  «Le Caër»: el mismo EFG aleatorio en sextetes con campo, malla en e²qQ/2 con signo
  y la misma σ; NORMOS lee esos subespectros (espectros de polvo de Blaes) de un
  fichero spline y Fitbauer los calcula con el Hamiltoniano exacto. Como el campo va
  en ese fichero y no en el `.JOB`, sin `BHF` se pone 33 T y se avisa. Con `METHOD=6` va a la forma
  «Czjzek»: una sonda del binario de NORMOS-DIST (09.09.1993) da exactamente la
  misma P ∝ ΔEQ⁴·exp(−ΔEQ²/2σ²), con **σ² = STG² + DTQ²** (exponente 4.000 y σ
  al 1e-5 con DTQ de 0.06 a 0.36; no depende de QUA ni de WID). En Fitbauer σ
  se importa como valor del control «σ Czjzek», fijo si el `.JOB` trae
  `STGFIT=.FALSE.`; el aviso de importación da el σ equivalente.
- La anchura de la gaussiana (`DISTRI=2`) no es STG. Según el manual de
  WinNormos (§2.3.2) y el fuente (`distcalf.for`, `distlstf.for`), en la gaussiana
  y en las de Czjzek y Le Caër NORMOS ensancha STG con
  el paso para que P no sea más estrecha que un bin: la σ real, la que ajusta
  Fitbauer, es **√(STG² + DTB²)** (o DTQ, DTI). Comprobado en el banco J1 (DTB =
  1 T): σ ajustada 1.801/3.163/5.112 T frente a √(STG²+1) = 1.803/3.162/5.099 T.
  El aviso de importación da el valor equivalente.
- El modelo de vecinos de Billard–Chamberod (`METHOD=3`).
- Varios bloques de distribución solapados: Fitbauer maneja uno.
- El parámetro de suavizado `LAMDA`. El de NORMOS es absoluto y el `alpha` de
  Fitbauer adimensional, así que no hay conversión uno a uno: hay que fijarlo con
  la L-curve. La **razón** `BETA/LAMDA` sí se conserva y es el anclaje de bordes.
- `DTQ` en las distribuciones de campo. Los bucles de `distcalf.for` para
  METHOD 1-5 calculan `RH = BHF+PP*DTB` y `RI = ISO+PP*DTI` y **no tocan ΔEQ**, así
  que trasladarlo metería una correlación que NORMOS nunca aplicó.

> **Cuidado con los `.JOB` heredados.** El formato de DIST no admite claves de SITE
> como `NLINE`, `DEP`, `W13` o `W23`. Si vienen copiadas de otro trabajo, NORMOS
> las lee y las descarta **sin decir nada**, de modo que ese subespectro nunca
> entró en su ajuste. Fitbauer sí lo avisa.

---

## Desde la línea de comandos

El CLI de ajuste discreto acepta un `.JOB` como plantilla, detectado por contenido
y no por extensión:

```bash
python mossbauer_fit_cli.py --template MI_TRABAJO.JOB --spectrum medida.ws5
python mossbauer_fit_cli.py --template modelo.json --spectrum medida.ws5 \
       --export-job SALIDA.JOB
```

---

## Validación

La equivalencia con NORMOS no es una afirmación de intenciones: está medida sobre
dos bancos independientes, 411 espectros sintéticos y 407 trabajos reales hechos
con el programa original. De los reales solo cuentan los 149 en que NORMOS ajustó
bien (χ² reducido ≤ 2) y los dos programas ven el mismo espectro: partiendo de la
solución de NORMOS, con los mismos parámetros libres y los datos doblados como
NORMOS, Fitbauer llega al mismo χ² o a uno menor en los 149, y los parámetros
coinciden en mediana a 0.0007 mm/s en δ y 0.0035 T en BHF. Los trabajos
reales no se distribuyen (son datos de laboratorio); el banco sintético y los
informes completos están en
[`validacion/informe/`](https://github.com/sullymike/Fitbauer/tree/main/validacion/informe).
