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

## 7. Folding y eje de velocidad (afecta al ajuste sobre datos reales)

Para que un ajuste sobre **el mismo espectro** coincida, no basta el modelo directo:
hay que doblar igual. Fitbauer (`core/folding.py`):

- Construye el eje completo `linspace(−Vmax, +Vmax, N)` y **recorta el primer y último
  punto** (`[1:-1]`) tanto en datos como en velocidad. **No** reconstruye un eje nuevo
  con menos canales (eso estiraría la escala y sesgaría el BHF).
- `Vmax` puede ser negativo; se conserva el signo (compatibilidad NORMOS/web con eje
  invertido).
- `folding point` fraccionario/interpolado (centro interno de simetría).

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
7. [ ] Mismo folding y manejo del eje de velocidad (§7) — solo si se compara sobre datos.
8. [ ] Mismo esquema de pesos Poisson y límites — solo si se exige el mismo **ajuste**,
       no solo la misma curva (§8).
9. [ ] Reproducir el vector de referencia de §9 como test.

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
