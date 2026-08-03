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
gaussiana, binomial o fija), la correlación δ(x) y los anclajes de borde; los
subespectros «cristalinos» (`NXLS`) pasan a ser componentes nítidos.

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
tampoco es donde dobla: su rutina final (`normospr.for:601-604`) lo trunca y suma
canales enteros,

```fortran
IPFA = PFA + 1.0E-4          ! asignación real→entero: trunca
IPFP = PFP + 1.0E-4
DO 602 L=1,NP
  TEMP(L) = Y(IPFA-L+1) + Y(IPFA+L)
```

Los pares suman `2·IPFA+1`, así que el eje de simetría cae en `⌊PFP⌋ + 0,5`. Está
en `core.normos_job.punto_de_doblado_normos()`, y tenerlo en cuenta es lo que
permite reproducir sus ajustes.

---

## Lo que no se traslada

El importador avisa de cada uno de estos puntos, porque lo que **no** se ha
traducido importa tanto como lo que sí:

- Distribuciones Czjzek / Le Caër (`DISTRI=4`) y el modelo de vecinos de
  Billard–Chamberod (`METHOD=3`).
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
dos bancos independientes —411 espectros sintéticos y 564 ajustes reales hechos con
el programa original—, con los informes completos en
[`validacion/informe/`](https://github.com/sullymike/Fitbauer/tree/main/validacion/informe).

En 355 de 503 trabajos comparables (71 %) Fitbauer iguala o mejora el χ² reducido
de NORMOS.
