# Especificación del modelo de sextete (Fe-57) — fuente de la verdad

> **Objetivo.** Este documento describe **exactamente** cómo Fitbauer calcula el
> sextete magnético, para que cualquier otra implementación (en particular la
> **web** de la que partió originalmente el programa) pueda reproducir un ajuste
> **idéntico**. Es el contrato de referencia: si la web sigue este documento,
> dados los mismos parámetros producirá la misma absorción y la misma transmisión.
>
> La implementación canónica vive en `core/physics.py`, `core/constants.py` y
> `core/hamiltonian.py`. Si este documento y el código discrepan, **manda el código**.

---

## 1. Convenciones generales

- **Eje de velocidad** `v` en **mm/s**. Signo conservado tal cual (puede ser negativo;
  ver folding en §7).
- **Modelo de transmisión** (no de absorción): el espectro observado baja desde una
  línea base. Para un solo componente:

  ```
  T(v) = baseline + slope · v − A(v)
  ```

  donde `A(v) ≥ 0` es la absorción del componente. Con varios componentes se suma la
  absorción total `A_tot = Σ A_c` antes de restar (ver §6).
- **Unidades de parámetros**: `δ` (delta), `ΔE_Q` (quad) y las `Γ` en mm/s; `BHF` en
  teslas (T); intensidades adimensionales; `depth` adimensional (escala de absorción).

---

## 2. Parámetros del sextete

Orden canónico (ver `SEXTET_PARAM_NAMES` en `core/constants.py`):

| # | Nombre   | Símbolo        | Significado |
|---|----------|----------------|-------------|
| 0 | `delta`  | δ              | Desplazamiento isómero (mm/s) |
| 1 | `quad`   | ΔE_Q           | Desdoblamiento cuadrupolar de 1er orden (mm/s) |
| 2 | `bhf`    | B_hf           | Campo hiperfino (T) |
| 3 | `gamma1` | Γ₁             | Anchura HWHM de las líneas **1 y 6** (mm/s) |
| 4 | `gamma2` | Γ₂(rel)        | Anchura **relativa** de las líneas 2 y 5 |
| 5 | `gamma3` | Γ₃(rel)        | Anchura **relativa** de las líneas 3 y 4 |
| 6 | `depth`  | d              | Profundidad (escala global de absorción) |
| 7 | `int1`   | I₁₃            | Intensidad relativa líneas 1,6 respecto a 3,4 |
| 8 | `int2`   | I₂₃            | Intensidad relativa líneas 2,5 respecto a 3,4 |
| 9 | `int3`   | I (base)       | Intensidad base de las líneas 3,4 (convención NORMOS: **fija a 1**) |

Las seis líneas se indexan **1..6** de izquierda a derecha en velocidad.

---

## 3. Posiciones de las seis líneas (modelo de 1er orden, histórico)

Este es el tratamiento por defecto (`treatment="1st_order"`), el que debe replicar la web.

### 3.1 Patrón de calibración a 33.0 T

Las posiciones provienen del **patrón de velocidad publicado de α-Fe**, NO de los
momentos nucleares (ver §8). En `core/constants.py`:

```
_BASE_POSITIONS = [-10.657, -6.167, -1.677, 1.677, 6.167, 10.657] · 0.5
                = [ -5.3285, -3.0835, -0.8385, 0.8385, 3.0835, 5.3285]   (mm/s)

BHF_DEFAULT_T = 33.0
LINE_POS_33T  = _BASE_POSITIONS              # posiciones a 33.0 T exactos
```

> ⚠️ **No derivar estas posiciones de los momentos nucleares.** El cálculo "de libro"
> da un desdoblamiento ~0,4 % menor (línea externa 5.309 vs 5.328 mm/s) y sesga el
> BHF ~0,1 T hacia arriba. La constante 33.0 T es la calibración; un α-Fe debe ajustar
> a 33.0 T exacto, igual que NORMOS.

### 3.2 Posiciones efectivas

Las posiciones escalan **linealmente** con el campo y se desplazan por δ y por el
patrón cuadrupolar:

```
LINE_QUAD_PATTERN = [ +0.5, −0.5, −0.5, −0.5, −0.5, +0.5 ]

posición_i = LINE_POS_33T[i] · (BHF / 33.0) + δ + ΔE_Q · LINE_QUAD_PATTERN[i]
```

Es decir, el campo escala el desdoblamiento magnético, δ desplaza el sextete completo,
y el cuadrupolo de 1er orden separa el par externo (líneas 1,6: +ΔE_Q/2) del resto
(líneas 2,3,4,5: −ΔE_Q/2).

---

## 4. Intensidades y anchuras de las seis líneas

### 4.1 Intensidades (pesos relativos)

```
i3 = int3                 # líneas 3 y 4
i2 = int3 · int2          # líneas 2 y 5
i1 = int3 · int1          # líneas 1 y 6

pesos = [ i1, i2, i3, i3, i2, i1 ]
```

Con la convención NORMOS por defecto (`int3 = 1`, `int2 = 2`, `int1 = 3`) se obtiene el
patrón clásico **3 : 2 : 1 : 1 : 2 : 3**.

### 4.2 Anchuras (HWHM, semianchura a media altura)

`gamma2` y `gamma3` son **multiplicadores relativos** sobre `gamma1`, no anchuras
absolutas:

```
g1 = gamma1               # líneas 1 y 6
g2 = gamma1 · gamma2      # líneas 2 y 5
g3 = gamma1 · gamma3      # líneas 3 y 4

gammas = [ g1, g2, g3, g3, g2, g1 ]
```

---

## 5. Perfil de línea

Cada línea aporta `peso · perfil(v; centro, γ)`. Hay dos perfiles seleccionables; el
estado global vive en `core/physics.py` (`LINE_PROFILE_KIND`, `VOIGT_SIGMA`).

### 5.1 Lorentziana (por defecto), normalizada al pico = 1

```
L(v; v0, γ) = γ² / ( (v − v0)² + γ² )
```

`γ` es la HWHM. `L(v0) = 1` en el centro.

### 5.2 Voigt (opcional), normalizada al pico = 1

Usando la función de Faddeeva `w(z)` (`scipy.special.wofz`), con `σ = VOIGT_SIGMA`:

```
denom = σ · √2
norm  = σ · √(2π)

V(v; v0, γ) = Re[ w( ((v − v0) + iγ) / denom ) ] / norm
pico        = Re[ w( iγ / denom ) ] / norm

perfil      = V / pico          # normalizado a 1 en el centro
```

> La normalización es **analítica al pico** (no se divide por el máximo discreto de la
> malla). Esto evita subestimar el pico cuando la malla de velocidad no cae justo en
> `v0`. La web debe normalizar igual para coincidir.

---

## 6. Absorción y transmisión total

### 6.1 Absorción de un sextete

```
A_sextete(v) = depth · Σ_{i=1..6}  pesos[i] · perfil(v; posición_i, gammas[i])
```

### 6.2 Modelo de transmisión total

```
A_tot(v) = Σ_c  A_c(v)                         # suma de todos los componentes activos
T(v)     = baseline + slope · v − A_eff(v)
```

donde por defecto `A_eff = A_tot` (modelo de absorbente delgado, lineal). Existe un modo
opcional de **absorbente grueso / saturación** con amplitud `C = sat_scale > 0`:

```
A_eff(v) = C · ( 1 − exp(−A_tot(v) / C) )       # límite C→∞ recupera A_eff = A_tot
```

Si la web solo implementa el modelo delgado, debe usar `A_eff = A_tot` (equivale a no
activar saturación en Fitbauer).

---

## 7. Doblado (folding), normalización y eje de velocidad — **CRÍTICO**

Para que un ajuste sobre **el mismo espectro** coincida, el modelo directo (§3–§6) **no
basta**: hay que **doblar igual**, normalizar igual y construir el eje de velocidad
igual. Si la web dobla de otra forma, el `BHF`, las posiciones y las áreas saldrán
distintas aunque el modelo del sextete sea idéntico. La implementación canónica es
`core/folding.py`. Esta sección es la parte que **más diverge** entre implementaciones,
así que se especifica completa.

### 7.1 Qué es el folding y por qué

El detector registra `N` canales (típicamente 512) que contienen el espectro **dos
veces** (ida y vuelta del movimiento del transductor), espejados respecto a un **centro
de simetría** (el *folding point*). Doblar = promediar cada canal con su simétrico para
obtener `N/2` puntos (típicamente 256) con mejor relación señal/ruido. El resultado se
ordena de velocidad negativa a positiva.

### 7.2 Numeración de canales y centro

- Canales numerados **1..N** (1-based), **no** 0-based. Esto importa para la fórmula.
- El `center` (folding point interno) es el **centro de simetría** y puede ser
  **fraccionario** (p. ej. 255.77), no solo entero/semientero.
- **Relación con Normos**: el número que reporta Normos ("Final/Upper folding point")
  suele estar en convención de **espectro completo** (≈ 511 para 512 canales) y es
  **aproximadamente el doble** del centro interno de esta GUI (≈ 255.5). Conversión en
  `read_normos_folding_point`: si el valor `≥ 400` → espectro completo → se divide por 2;
  si `< 400` → ya es semiespecro → se usa tal cual.

### 7.3 Algoritmo de doblado (`fold_integer_or_half`)

Genera siempre `n_out = N // 2` puntos. Para cada punto `j = 0 .. n_out−1`:

```
distancia  = j + 0.5
canal_izq  = center − distancia
canal_der  = center + distancia
folded[j]  = 0.5 · ( C(canal_izq) + C(canal_der) )
```

donde `C(canal)` es la **interpolación lineal subcanal** 1-based (`interp_channel_1based`):

```
# canales 1..N, valores counts[0..N-1]
si canal < 1:        C = counts[0]   + (canal − 1) · (counts[1]   − counts[0])      # extrapola
si canal ≥ N:        C = counts[N-1] + (canal − N) · (counts[N-1] − counts[N-2])    # extrapola
si no:
    lo   = floor(canal)
    frac = canal − lo
    si frac ≈ 0:     C = counts[lo−1]
    si no:           C = (1 − frac)·counts[lo−1] + frac·counts[lo]
```

> **Clave para reproducir Normos**: el doblado NO se queda en pares de canales enteros.
> Para centros fraccionarios usa interpolación lineal, y en los bordes
> **extrapola** linealmente en vez de perder un canal. Así siempre salen `N/2` puntos.

### 7.4 Búsqueda del folding point (`find_best_integer_or_half_center`)

Si no viene dado por Normos, se busca minimizando χ² de la diferencia entre canales
simétricos:

1. Malla de candidatos en pasos de 0.5 (por defecto 250.5 .. 262.5 para 512 canales).
2. Para cada centro, `χ²(center) = Σ (counts[izq] − counts[der])²` sobre los pares.
3. Se toma el centro de mínimo χ² y se **interpola el mínimo** con una parábola
   (refinamiento subcanal) usando los tres puntos alrededor del mínimo.

### 7.5 Recorte de bordes y normalización (`fold_and_normalize`)

```
folded = fold_integer_or_half(counts, center)
# Recorta edge_trim canales en cada extremo (por defecto 1), si hay tamaño suficiente:
si edge_trim > 0 y folded.size > 2·edge_trim + 2:
    folded = folded[edge_trim : −edge_trim]

norm  = percentil_90(folded)        # ≈ línea base
y     = folded / norm               # espectro normalizado (~1 en la base)
sigma = sqrt( max(folded/2, 1) ) / norm   # ruido Poisson normalizado
```

- **Recorte de bordes**: los canales extremos del espectro doblado son menos fiables y
  se descartan (`edge_trim = 1` por defecto). Nota: solo se recorta si el array es
  suficientemente grande (`> 2·edge_trim + 2`); en espectros reales de 256 puntos siempre
  aplica.
- **Normalización**: por el **percentil 90** de las cuentas dobladas (estimador robusto
  de la línea base), no por el máximo.
- **σ de Poisson**: `sqrt(folded/2)` (el `/2` viene de promediar dos canales) con suelo a
  1 cuenta, dividido por `norm`. Estos `sigma` son los **pesos del ajuste** (ver §8).

### 7.6 Eje de velocidad (`velocity_axis`) — no estirar la escala

```
full_n   = N // 2
velocity = linspace(−Vmax, +Vmax, full_n)        # eje COMPLETO primero
# se recortan las MISMAS posiciones de borde que en los datos:
si edge_trim > 0 y coincide el tamaño:
    velocity = velocity[edge_trim : −edge_trim]
```

> ⚠️ **Error clásico a evitar**: NO reconstruir el eje como
> `linspace(−Vmax, +Vmax, n_points_recortado)`. Hay que construir el eje completo de
> `N/2` puntos y recortar los mismos bordes que en los datos. Reconstruirlo con menos
> puntos **estira la escala de velocidad y sesga el BHF**.

- `Vmax` puede ser **negativo**; se conserva el signo (compatibilidad NORMOS/web con eje
  invertido).

### 7.7 Contrato numérico de folding (verificable)

Ejemplo reproducible con `core/folding.py`. **Entrada**: 8 canales (1-based)

```
counts = [100, 90, 70, 95, 98, 60, 88, 105]
```

**Doblado a centro semientero `center = 4.5`** → pares `(4,5) (3,6) (2,7) (1,8)`:

```
folded = [ 96.5, 65.0, 89.0, 102.5 ]
```

**Doblado a centro fraccionario `center = 4.30`** (muestra la interpolación subcanal):

```
folded = [ 93.7, 70.8, 87.2, 101.8 ]
```

**`fold_and_normalize(counts, center=4.5, edge_trim=1)`** (en este array pequeño de 4
puntos doblados, `edge_trim` no recorta porque `4 ≤ 2·1+2`):

```
norm  = 100.7                                          # percentil 90
y     = [ 0.958292, 0.645482, 0.883813, 1.017875 ]
sigma = [ 0.068979, 0.056612, 0.066245, 0.071091 ]
```

**`velocity_axis(N=8, Vmax=4.0, n_points=4, edge_trim=1)`**:

```
velocity = [ −4.0, −1.333333, +1.333333, +4.0 ]
```

> Si la web reproduce estos cuatro bloques (a tolerancia ~1e-6), el folding, la
> normalización y el eje son **idénticos**. Mantener este vector como test de regresión.

### 7.8 Lectura de sidecars Normos (opcional)

`core/folding.py` también lee parámetros de ficheros Normos asociados para inicializar
el ajuste (no afecta al modelo, solo a las semillas):

- `.RES`: valores finales `ISO→δ`, `BHF`, `QUA→ΔE_Q`, `WID` (¡Normos da **FWHM**; la
  lorentziana interna usa **HWHM** = FWHM/2!), `ARE→depth` (vía `ARE / (π·Γ·Σpesos)`,
  con `Σpesos = 2·(3+2+1) = 12`).
- `.JOB`: `VMAX`, `QUA(1)`.
- `.PLT`: `Vmax` a partir de los bloques de 256 valores.

---

## 8. Función objetivo del ajuste (afecta a los valores ajustados)

Dos implementaciones pueden compartir el modelo directo y **aun así** dar parámetros
ajustados distintos si minimizan cosas distintas. Fitbauer (`core/fit_engine.py`) usa:

- **Pesos de Poisson** (cuentas): residuo ponderado por la varianza ≈ cuentas.
- Mínimos cuadrados no lineales (TRF) con multistart determinista; opción de pérdida
  robusta y de evolución diferencial global.
- Límites físicos de parámetros (rangos de `BHF`, `ΔE_Q`, etc.).

Para un ajuste **idéntico** al de Fitbauer, la web debe coincidir en: modelo directo
(§3–§6) **y** esquema de pesos **y** mismos límites/semilla. Si la web solo necesita la
**misma curva** dados parámetros (simulación), basta §3–§6.

---

## 9. Vector de referencia (contrato numérico verificable)

Valores generados ejecutando `core/physics.py` (perfil Lorentziano, modo 1er orden).
**Parámetros**: `δ=0`, `ΔE_Q=0`, `BHF=33.0`, `Γ₁=0.150`, `Γ₂rel=Γ₃rel=1.0`,
`depth=0.02`, `int1=3`, `int2=2`, `int3=1` → pesos `3:2:1:1:2:3`, `baseline=1`, `slope=0`.

**Posiciones de las 6 líneas (mm/s):**

```
[ −5.3285, −3.0835, −0.8385, +0.8385, +3.0835, +5.3285 ]
```

**Absorción y transmisión muestreadas:**

| v (mm/s)  | A(v)      | T(v) = 1 − A(v) |
|-----------|-----------|-----------------|
| −5.3285   | 0.060236  | 0.939764        |
| −3.0835   | 0.040427  | 0.959573        |
| −0.8385   | 0.020497  | 0.979503        |
|  0.0      | 0.001524  | 0.998476        |
| +0.8385   | 0.020497  | 0.979503        |
| +3.0835   | 0.040427  | 0.959573        |
| +5.3285   | 0.060236  | 0.939764        |

> Si la implementación de la web reproduce esta tabla (a tolerancia ~1e-6), el modelo
> directo del sextete es **idéntico**. Conviene mantener este vector como test de
> regresión en ambos lados.

---

## 10. Tratamientos avanzados (opcionales)

Por defecto la web solo necesita el **1er orden** (§3). Para completitud, `core/physics.py`
+ `core/hamiltonian.py` ofrecen dos tratamientos cuadrupolares más, por diagonalización
del Hamiltoniano `ω_e·I_z + (ΔE_Q/6)(3 I_{z'}² − I(I+1))` (EFG axial, η=0):

- `kundig_fixed`: ángulo β fijo entre B y V_zz.
- `kundig_powder`: promedio policristal por cuadratura Gauss–Legendre de `n_quad`
  orientaciones (β ∈ [0, π]).

Solo replicarlos si la web va a ofrecer esos modos.

---

## 11. Checklist para alinear la web

1. [ ] Posiciones base de α-Fe a 33.0 T = `±0.8385 / ±3.0835 / ±5.3285` mm/s (§3.1).
2. [ ] Escalado lineal `· (BHF/33.0)`, desplazamiento `+δ`, patrón cuadrupolar
       `[+0.5,−0.5,−0.5,−0.5,−0.5,+0.5]·ΔE_Q` (§3.2).
3. [ ] Intensidades `[i1,i2,i3,i3,i2,i1]` con `i1=int3·int1`, `i2=int3·int2`, `i3=int3`
       (§4.1).
4. [ ] Anchuras `gamma2/gamma3` como **multiplicadores** de `gamma1` (§4.2).
5. [ ] Lorentziana con pico = 1 (o Voigt con normalización analítica al pico) (§5).
6. [ ] Transmisión `baseline + slope·v − A_tot`; saturación opcional (§6).
7. [ ] **Folding** (§7) — solo si se compara sobre datos:
   - [ ] Canales **1-based**; centro de simetría posiblemente fraccionario (§7.2).
   - [ ] Conversión del folding point Normos (≈ doble del centro interno) (§7.2).
   - [ ] Doblado `0.5·(C(center−(j+0.5)) + C(center+(j+0.5)))` con interpolación
         lineal subcanal y extrapolación en bordes (§7.3).
   - [ ] Recorte de bordes `edge_trim=1` (§7.5).
   - [ ] Normalización por **percentil 90** y `σ = sqrt(max(folded/2,1))/norm` (§7.5).
   - [ ] Eje de velocidad construido completo y recortado, **sin reconstruir** con menos
         puntos (§7.6).
   - [ ] Reproducir el contrato numérico de folding (§7.7).
8. [ ] Mismo esquema de pesos Poisson (los `σ` de §7.5) y límites — solo si se exige el
       mismo **ajuste**, no solo la misma curva (§8).
9. [ ] Reproducir el vector de referencia del modelo directo de §9 como test.

---

## 12. Qué hace falta para producir un "qué cambiar" concreto de la web

Este documento es la especificación del lado Fitbauer. Para entregar un **delta exacto**
(qué líneas cambiar en la web) conviene tener:

- El **código actual de la web** que calcula el sextete (fórmulas de posiciones,
  intensidades, perfil, transmisión) y el lenguaje/stack (JS, PHP, Python…).
- Si existe, el **valor de campo de referencia** que usa la web (¿32.95 T? ¿33.0 T?) y
  sus posiciones base — es la causa más probable de discrepancia histórica.
- Un espectro de prueba (p. ej. α-Fe) ajustado en ambos lados para comparar números.
```
