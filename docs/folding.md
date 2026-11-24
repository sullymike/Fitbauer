# Plegado (folding) de espectros Mössbauer

Módulo: `core/folding.py` (funciones puras, sin GUI)

---

## Por qué hay que doblar

Un espectrómetro Mössbauer de aceleración constante registra **dos semiespectros**
simétricos: el detector ve la misma secuencia de velocidades en el barrido de ida y
en el de vuelta. Un fichero de $N$ canales (típicamente 512) contiene dos copias del
espectro, una reflejada respecto a la otra en torno a un **punto de simetría** (el
*folding point*). Doblar (promediar los dos semiespectros) produce un único espectro
de $N/2$ puntos con relación señal/ruido $\sqrt{2}$ mejor y elimina la duplicación.

---

## Punto de doblado (folding point)

El folding point es el canal de simetría $c$ que minimiza la diferencia entre los dos
semiespectros. Para cada candidato $c$ se calcula:

$$\chi^2(c) = \sum_{\text{pares}} \bigl[C(c - d) - C(c + d)\bigr]^2$$

donde $d = j + 0.5$ recorre las distancias al centro y $C(\cdot)$ es el conteo
interpolado (canales numerados 1..N). El mínimo se busca primero en una malla de
medios canales y luego se **interpola parabólicamente** para obtener una precisión
subcanal (`find_best_integer_or_half_center`).

> **Convención Normos.** Fitbauer usa internamente el centro de simetría
> (≈ 255.77 para un *upper folding point* Normos ≈ 511.55 en 512 canales). El número
> que reporta Normos es aproximadamente el **doble** del centro interno.
> `read_normos_folding_point` lee el "Final folding point" del sidecar `.RES` y lo
> convierte: si el valor es ≥ 400 se interpreta como convención de espectro completo
> (÷2); si es < 400, como semiespectro.

---

## Interpolación de canales (`interp_channel_1based`)

El folding point rara vez cae en un canal entero. La función dobla en $N/2$ puntos al
estilo Normos, obteniendo cada conteo por **interpolación** entre canales: por
defecto un B-spline **cúbico** (`FOLD_INTERP_ORDER_DEFAULT = 3`; la lineal sesga la
anchura recuperada hasta un +9,5 %, la cúbica un +2,8 %). Con centro semientero no se
interpola nada. En los bordes (canales fuera del rango 1..N) se usa **extrapolación
lineal mínima**, lo que evita perder un canal para centros semienteros como 255.5 en
espectros de 512 canales.

Para cada punto doblado $j$ (con $j = 0..N/2-1$):

$$F_j = \tfrac{1}{2}\bigl[C(c - (j{+}0.5)) + C(c + (j{+}0.5))\bigr]$$

El resultado se ordena de velocidad negativa a positiva.

---

## Recorte de bordes y normalización (`fold_and_normalize`)

Por defecto **no se recorta ningún canal** (`EDGE_TRIM_DEFAULT = 0`), igual que
NORMOS. El recorte lo decide `edge_outlier_trim` mirando los datos: solo se quitan los
extremos que caen más de un 20 % respecto a la mediana de sus vecinos, o que dan un
salto aislado de más de 25 σ de Poisson (canales muertos o saturados), hasta 3 por lado y siempre el mismo número a cada lado, para que el eje
de velocidad se deduzca del número de puntos sin estirar la escala. `edge_trim` sigue
existiendo como mínimo forzado.

La normalización lleva la línea base a ≈ 1.0 usando el **percentil 90** del espectro
doblado (robusto frente a los picos de absorción, que son mínimos):

$$\mathrm{norm} = P_{90}(F), \qquad y_i = \frac{F_i}{\mathrm{norm}}$$

El ruido Poisson se propaga teniendo en cuenta que cada punto doblado es la media de
**dos** canales Poisson:

$$\sigma_i = \frac{\sqrt{\max(F_i / 2,\; 1)}}{\mathrm{norm}}$$

La función devuelve la tupla `(folded, sigma, y, norm)`.

---

## Eje de velocidad (`velocity_axis`)

El eje de velocidad va de $-v_{\max}$ a $+v_{\max}$ con $N/2$ puntos:

$$v = \mathrm{linspace}(-v_{\max},\; +v_{\max},\; N/2)$$

**Importante:** el eje se recorta en las **mismas posiciones** que el espectro
(`[edge_trim:-edge_trim]`), no se reescala. Reescalar el eje tras el recorte estiraría
la escala de velocidad y sesgaría el BHF ajustado.

---

## Formato CSV/velocidad pre-doblado (`load_velocity_csv`)

Para espectros ya doblados en espacio de velocidad (p.ej. datos de sincrotrón ESRF),
se admite un formato CSV/TXT/DAT/EXP de **dos columnas** `velocidad, cuentas`:

- Separadores: coma, tabulador o espacios.
- Líneas de comentario (`#`) o cabecera no numérica se ignoran.
- Si todos los valores de la columna 2 son ≤ 1.0, se interpretan como **transmisión
  normalizada** y se escalan a cuentas (`round(2_000_000 · col2)`).
- Detección de columnas invertidas: si la col0 tiene todo > 100 y la col1 todo en
  [−20, 20], se lanza error sugiriendo invertir las columnas.
- Deduplicación: velocidades más cercanas que $10^{-9}$ se promedian.
- Validaciones: ≥ 10 puntos, rango de velocidad ≥ 1 mm/s.

Estos ficheros **no se doblan** (ya vienen doblados); se cargan directamente al eje
de velocidad.

---

## Sidecars Normos

Cuando hay ficheros sidecar de Normos junto al espectro, Fitbauer los lee para
heredar parámetros:

| Sidecar | Función | Qué extrae |
|---|---|---|
| `.RES` | `read_normos_folding_point`, `read_normos_sidecar_params` | Folding point final; valores finales WID/ARE/ISO/QUA/BHF |
| `.PLT` | `read_normos_plt_velocity` | $V_{\max}$ del eje |
| `.JOB` | `read_normos_sidecar_params` | VMAX y QUA(1) fijos |

Los valores finales de Normos se traducen a parámetros internos
(`s1_delta`, `s1_bhf`, `s1_quad`, `s1_gamma1`, `s1_depth`) como punto de partida.

---

## Ruido del punto doblado y χ² (Fitbauer, NORMOS y WMOSS)

Interpolar promedia canales vecinos: el punto doblado tiene menos ruido del que dicen
sus cuentas y queda correlacionado con sus vecinos. Varianza del punto doblado
respecto a la de Poisson, según la fracción del centro (0,5 = semientero, sin
interpolar; simulación con 200 000 cuentas por canal):

| Fracción del centro | 0,5 | 0,4 | 0,3 | 0,2 | 0,1 | 0 |
|---|---|---|---|---|---|---|
| Cúbica (Fitbauer) | 0,99 | 0,97 | 0,90 | 0,83 | 0,77 | 0,76 |
| Lineal | 1,00 | 0,82 | 0,68 | 0,58 | 0,52 | 0,50 |

La σ del ajuste sale de las cuentas (`fold_and_normalize`) y **no** descuenta este
suavizado, así que el χ² reducido sale hasta un 24 % bajo con centro entero.

- **NORMOS** trunca el punto de doblado y suma canales enteros: no suaviza, pero
  desalinea los pares hasta medio canal.
- **WMOSS** (manual WMOSS4 ver. F, §4.1–4.3) suma las dos mitades del barrido con un
  punto de doblado fraccionario, manual o automático; con la corrección de no
  linealidad de la velocidad, antes reproyecta por interpolación los datos sin doblar
  sobre una escala lineal. En espectros reales doblados por WMOSS, la varianza de la
  diferencia entre puntos vecinos de la zona plana era el 38 % de la de Poisson
  (Fitbauer, mismas cuentas: 102 %).
- **χ² de WMOSS.** Mismo estadístico que Fitbauer: χ² = Σ (D − M)² / D con D las
  cuentas sumadas del punto doblado, y χ²ᵣ = χ² / (N − Nvar), con las áreas y la línea
  base en Nvar. Reconstruyendo las cuentas de sus `.b` (cabecera: BL20 y área de
  absorción) se reproduce exactamente el valor que imprime. Como sus datos están
  suavizados, el mismo modelo da un χ²ᵣ más bajo en WMOSS: en un espectro real de
  cuatro dobletes estrechos, 2,42 sobre sus datos y 3,07 sobre los de Fitbauer para la
  misma curva. Entre programas se comparan parámetros y curvas, no χ²ᵣ.

---

## Resumen del flujo

```text
counts (N canales)
   ↓ find_best_integer_or_half_center  →  center (subcanal)
   ↓ fold_integer_or_half              →  N/2 puntos doblados
   ↓ fold_and_normalize (edge_trim)    →  (folded, sigma, y, norm)
   ↓ velocity_axis (mismo recorte)     →  eje de velocidad -vmax..vmax
espectro listo para ajuste
```
