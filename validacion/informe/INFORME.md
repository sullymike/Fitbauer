# Informe de validación de Fitbauer contra NORMOS-SITE

**Sesión de agente autónomo, 2026-07-31; 2ª ampliación (series K/L, manual de NORMOS) y 3ª tanda (extremos sobre las series originales) el 2026-08-01 — ver §16–§17 y el veredicto final en `VEREDICTO.md`.** Plan de referencia:
`validacion/plan_validacion_fitbauer_normos.md`. Todos los datos, scripts y
figuras citados viven bajo `validacion/`.

---

## 1. Resumen ejecutivo

Se construyó un banco round-trip **NORMOS-SITE simula → Fitbauer ajusta →
comparación con la verdad**: **327 espectros base** (SITE.EXE, DIST.EXE para el bloque J y 4
derivados por binning exacto), más
**285 réplicas v1 con ruido Poisson**, **150 réplicas de cobertura (H3)**,
32 ajustes de barrido de estadística (H1) y los bloques adversarios (I). En
total **411 espectros y ~1.150 ajustes** (fase 1 + series K/L de la 2ª
ampliación §16 + extremos de la 3ª tanda §17 + validación v4.19 §18) con
valores iniciales perturbados y semilla registrada (6.497 filas de
comparación en `resumen.csv`).

**Veredicto global**: el núcleo discreto de Fitbauer (singlete / doblete /
sextete a 1er orden, anchuras por pares, textura, multisitio, ligaduras,
plegado y ejes) **reproduce NORMOS dentro de 10⁻⁴–10⁻³ mm/s y ≲2·10⁻³ T**,
muy por debajo de cualquier incertidumbre experimental. Las σ reportadas son
estadísticamente correctas (χ²red mediana 0.976; pull global 64/92/96 % dentro
de 1σ/2σ/3σ). Los desacuerdos que quedan están **localizados, entendidos y
documentados** (§6): intensidades del Hamiltoniano completo, η no soportado,
integral de transmisión, base curva, robustez del arranque en multicomponente
y varias degeneraciones físicas reales que ningún programa puede romper.

| Bloque | Resultado |
|---|---|
| A1–A3 (singletes, dobletes, sextetes 1er orden) | ✅ exacto (≤2·10⁻⁴) |
| A4/A6 (Hamiltoniano completo axial) | ⚠️ posiciones OK hasta θ≲55°; intensidades no modeladas (§6.1) |
| A5 (EFG no axial, η≠0) | ❌ no soportado — hueco de capacidad (§6.2) |
| A7 (líneas libres) | ✅ dentro de δ∈[−2,3]; límite documentado (§6.5) |
| B (textura/intensidades) | ✅ (degeneración de rama del doblete documentada, §6.7) |
| C (anchuras) | ✅ ; Γ≈1 canal exige DE o buen arranque (§6.4) |
| D (multisitio, ligaduras) | ✅ hasta 10 sitios (¡el núcleo headless supera el límite 6 de la GUI!); degeneraciones D6 (§6.7) |
| E (adquisición) | ✅ ; sesgo por integración de canal y base curva cuantificados (§6.6, §6.8) |
| F (espesor) | ⚠️ saturación exponencial ≈ correcta hasta t≈10; sin ensanchamiento de espesor (§6.3) |
| G (isótopos) | ⛔ no ejecutable: el demo de SITE no acepta otros isótopos |
| H (estadística) | ✅ σ ∝ 1/√cuentas; cobertura ≈ nominal (ligera infraestimación, §7) |
| I (adversarios) | ✅ salvo lo esperado (t_a≥30 con modelo fino; señal 0.2 % con base 10⁵) |
| J (distribuciones, DIST) | ✅ ⟨B⟩ a ≤0.1 T, picos bimodales a ½ bin, P(ΔEQ) y correlación δ(B) validadas; ensanchamiento de regularización +0.2 T cuantificado (§8) |

> **Actualización v4.18.0 (§13)**: los sesgos de modelo de §6.1 (intensidades
> del HC), §6.2 (η/φ), §6.3 (transmisión), §6.6 (canal) y §6.8 (base curva)
> quedaron **eliminados** con cuatro extensiones opt-in de `core/`
> (medianas ×7–×285 menores, filas `v0m` del resumen). De paso se demostró
> que NORMOS-SITE 1994 no es exacto a mezcla fuerte (viola la invariancia
> rotacional): la nueva implementación de Fitbauer lo supera ahí.

---

## 2. Entorno y metodología

- **NORMOS-SITE**: `SITE.EXE` v. 27.01.1994 (WissEl GmbH, *Demonstration
  version*), sin manual; `DIST.EXE` (09.09.1993) llegó con el bloque J.
  Ejecutado bajo dosbox-staging 0.82.2 con la receta validada de
  `docs/normos_dosbox_guide.md`: JOB por stdin (`SITE < X.JOB`),
  `REMOTE=.TRUE.`, display real `:0`, lotes de hasta 45 casos por arranque
  (~0.6 s por lote). El namelist Fortran exige líneas ≤ ~72 columnas y CRLF.
- **Fitbauer**: capa headless `core.session.HeadlessSession`, motor
  `core.fit_engine` (TRF con límites, multistart, DE opcional), commit del
  repo en el momento de la sesión (rama `main`, v4.17.3).
- **Round-trip por caso**: SITE simula con todos los parámetros fijos
  (verificado: `SIMULT=.TRUE.` ≡ ajuste con 0 variables libres, bit a bit) →
  curva teórica del bloque *fit* del `.PLT` (256 puntos, eje
  `linspace(−VMAX,+VMAX)`, idéntico al de Fitbauer) → espectro **sin doblar**
  de 512 canales por espejo exacto alrededor de 256.5 (canal 1 en +vmax,
  drive triangular) → Fitbauer detecta el centro por simetría, dobla y ajusta
  desde valores iniciales **perturbados ±15 %** (semilla CRC32 del caso).
- **v1**: ruido Poisson con semilla registrada sobre la misma teoría
  (base 10⁶ salvo barridos H); el promedio de canales del doblado y la σ
  de Fitbauer (`sqrt(folded/2)/norm`) casan por construcción.
- **Verificaciones previas** (paso 0-bis): determinismo de SITE (dos
  ejecuciones → salida idéntica), singlete trivial contra Lorentziana
  analítica (residuo < 2·10⁻⁵), dummy plano con valle simétrico para que la
  búsqueda del punto de doblado de SITE dé exactamente 256.5.
- **Escalado de ajuste** (imita al usuario ante un mal ajuste): si el ajuste
  local+multistart acaba con χ²red>2 se reintenta con pre-pasada global DE, y
  si persiste, con arranque fino ±5 %. Solo lo necesitaron 6 y 8 casos de 318
  (multisitio solapado); el escalado queda anotado en `resumen.csv`.

## 3. Convenciones descifradas (paso 0.6 + sondas sobre el binario)

| Magnitud | SITE | Fitbauer | Conversión |
|---|---|---|---|
| Posición | `ISO` | `s_delta` | idéntica (ambos vs cero de la fuente) |
| Anchura | `WID` = **FWHM** de las líneas interiores (3,4) | `gamma1` = FWHM de las líneas exteriores (1,6) | `gamma1 = WID·W13` |
| Anchuras por pares | `W13`, `W23` = ratios 1,6/3,4 y 2,5/3,4 | `gamma2`, `gamma3` = ratios respecto a 1,6 | `gamma2 = W23/W13`, `gamma3 = 1/W13` |
| Cuadrupolo sextete | `QUA` (desplaza ±QUA/2; líneas 1,6 → +) | `quad` | **idéntico, signo incluido** |
| Cuadrupolo doblete | `QUA` | `quad` | signo opuesto y **degenerado** en dobletes simétricos → se compara \|ΔEQ\| |
| Campo hiperfino | `BHF` (posiciones desde momentos nucleares) | `bhf` (patrón α-Fe publicado, 33 T ↔ ±5.329 mm/s) | `bhf = BHF·k`, **k = 0.99962 ± 0.00000?** (medido en 33 y 51.7 T; diferencia de convención, cf. CHANGELOG Fitbauer v4.0.2/v4.0.3, no un error) |
| Intensidades | `D13`,`D23` (sextete), `D21` (doblete) = ratios de **área**; `D21` = línea alta-v / baja-v | `int1`,`int2` = pesos de **altura** | `int = D/W` del par correspondiente |
| Amplitud | `DEP` = **área integrada** del subespectro (mm/s) — verificado ∫(1−T)dv = DEP | `depth` = profundidad fraccional de pico | `depth = DEP/(π/2·Σ w_i·Γ_i)` |
| Hamiltoniano completo | `HAMILT=.TRUE.` (¡en `&PARAM`, no en `&DATA`!) + `THE/ETA/PHI` (grados) | `quad_treatment="kundig_fixed"` + `beta` (grados) | θ=0 ≡ 1er orden en ambos (verificado a 5·10⁻⁵) |
| Transmisión | `IFTRAN=.TRUE.` (en `&PARAM`) + `TAB` (espesor efectivo) + `WDS=0.097` (fuente, implícita) | `absorber_model="thickness"` + `sat_scale` | modelos distintos, ver §6.3 |

## 4. Inventario de capacidades

**SITE demo 27.01.1994** (sondas en `paso0/sonda*`): NSUB ≤ 10 (12/14 fallan
sin mensaje); **solo espectros de 512 canales crudos** (el lector WS5 exige
≥512 números y el plegado admite NP ≤ 256; 1024 crudos se leen pero exceden
NP); `HAMILT/THE/ETA/PHI` ✔; `IFTRAN`+`TAB` ✔; `W13/W23/D21` ✔;
relajación `SRELAX`/`IRELAX`+`OME`+`BH0` ✔ (en `&PARAM`); `QMR` ✔;
**no disponibles**: isótopos ≠ ⁵⁷Fe (`EGAMMA`/`GAMMA`/`GFACT` rechazados en
ambos namelists → bloque G descartado), `VOIGT` aceptado sin efecto
observable, ligaduras `NLINK` sin sintaxis descifrable sin manual (el D5
valida en su lugar el motor de ligaduras de Fitbauer sobre espectros
generados respetando la ligadura).

**DIST.EXE** (NORMOS-Dist 09.09.1993, añadido a posteriori — bloque J,
sondas en `_staging/sondaJ*`): bloques de distribución sobre una malla que es
**siempre de BHF** (`NDSS`, `NSB(k)` puntos desde `BHF(k)` con paso `DTB(k)`,
default 1 T); `DISTRI=2` = gaussiana con centro `AVG(k)` y anchura `STG(k)`
(compensada por el paso); `DTI(k)` = incremento de ISO por punto → correlación
lineal δ(B) ✔ (equivale a `delta_slope` de Fitbauer con DTB=1); **`DTQ`
aceptado pero inoperante** (sonda K1: efecto cero → P(ΔEQ) pura no generable
con este demo; J3 se generó con SITE: 10 dobletes de áreas gaussianas);
`SIMULT=.TRUE.` simula (amplitud arbitraria; el modelo es lineal en P → se
escala en Python de forma exacta); la verdad P(B) por bloque se lee de la
"Table of relative areas" del `.RES` (cada bloque normalizado a 100 → bloques
de áreas iguales); sitios cristalinos `*X` disponibles; `MAXENT`/`LAMBDA`
(regularización propia de DIST) no ejercitados (DIST solo genera aquí).

**Fitbauer**: hasta 6 componentes en la GUI — pero **el núcleo headless
ajustó 8 y 10 componentes sin problema** (D1_n08/n10, χ²red 0.004);
singlete/doblete/sextete; Kündig axial (η=0) fijo y polvo; Lorentz/Voigt;
ligaduras `target=factor·source+offset`; espesor por saturación exponencial;
relajación fenomenológica/Blume-Tjon/Néel; solo ⁵⁷Fe; δ acotado a [−2,+3] mm/s.

## 5. Resultados v0 — aciertos (mención breve, criterio plan §4: <10⁻³ mm/s, <0.05 T, <0.5 % áreas)

| Serie | Casos | máx desviación observada |
|---|---|---|
| S0 convenciones | 4 | 6.8·10⁻⁵ |
| A1a/A1b/A1c singletes | 21 | 2.7·10⁻⁵ mm/s |
| A2 dobletes (rejilla 45) | 45 | 7.1·10⁻⁶ mm/s |
| A3a/b/c sextetes (2–55 T) | 24 | 1.7·10⁻⁴ T |
| A7 líneas libres (1–8 líneas) | 5 | 1.9·10⁻⁵ mm/s |
| B1 textura (D23 0–4) | 10 | 3.6·10⁻³ en int2 (tol 0.04) |
| B2 dobletes asimétricos | 5 | criterio cumplido (rama degenerada reconocida) |
| C1/C2 anchuras comunes y por pares | 7 | 1.7·10⁻³ mm/s en anchura |
| C3 6 líneas libres | 3 | exacto (χ²red ≈ 10⁻⁴) |
| D2 2 sextetes solapados (ΔB 0.5–8 T) | 6 | 2.5·10⁻³ T |
| D3 fase minoritaria 1–20 % | 6 | área recuperada hasta el suelo del banco (§6.9) |
| D5 ligaduras (Γ común, áreas 2:1, δ, ΔEQ, combinada) | 6 | 7.8·10⁻⁴ |
| D1 multisitio 2–10 sitios | 7 | ≤7·10⁻³ salvo degeneraciones (§6.7) |
| E2 rangos ±2–±15 mm/s | 6 | 1.8·10⁻⁴ |
| E4 sin plegar ≡ plegado directo | 2×2 | 6·10⁻⁵ |
| E5 líneas cortadas por el borde | 3 | 4.4·10⁻³ T (¡recupera un sexteto de 55 T con las líneas 1,6 fuera del rango!) |
| I2 Γ enorme (1.5/3.0) · I4 límite detección (v0) · I5 fronteras | 5 | 7·10⁻⁴ |

El escalado (DE o arranque fino) solo fue necesario en 14 de 318 casos, todos
multisitio con fuerte solapamiento; queda anotado por fila en `resumen.csv`.

---

## 6. Fallos y limitaciones — documentación detallada

**Nota — sesgo de modelo vs convergencia**: los sesgos de §6.1, §6.3, §6.6 y
§6.8 se verificaron re-ajustando con arranque EXACTO en la verdad (perturbación
0, sin multistart): el optimizador se aleja de la verdad y aterriza en el mismo
valor sesgado (coincidencia a la 3ª–4ª cifra: p. ej. A4_R2_th90 Bhf −0.094 T,
F3_t10 Γ +0.092, E3 Γ +0.034, E1_128 Γ +0.091). El valor verdadero no es el
mínimo de χ² del modelo de Fitbauer: son sesgos sistemáticos que ni el
arranque ni la estadística curan, solo ampliar el modelo. En cambio, C4 y el
multisitio de §6.10 sí se curan con buen arranque (sesgo <4·10⁻⁴): allí el
modelo es capaz y el problema era encontrar el mínimo.

### 6.1 Hamiltoniano completo axial: SITE recalcula intensidades; Fitbauer solo posiciones

**Datos**: series A4 (30 casos R×θ), A6 (10 pares de contraste), D4_sextHC.
**Figuras**: `figuras/fig_A4_mapa_sesgos.*`, `fig_A4_ejemplo_R2_th90.*`,
`fig_A6_validez_1er_orden.*`.

Con `HAMILT=.TRUE.`, SITE diagonaliza el Hamiltoniano magnético+cuadrupolar y
**recalcula las intensidades de transición desde los autovectores** (incluidas
las transiciones ΔmI=±2 que se activan con la mezcla). El Kündig de Fitbauer
(`kundig_fixed`) diagonaliza igual las **posiciones** (θ=0 coincide con SITE a
5·10⁻⁵) pero mantiene las intensidades que fije el usuario.

Consecuencia medida (ajustando con intensidades libres):
- θ ≤ 30° y R ≤ 1: |ΔBhf| ≤ 0.022 T, |ΔΓ| ≤ 0.014 — **usable**.
- θ = 54.7°: posiciones aún buenas (|ΔBhf| ≤ 0.002 T) pero int2 ajustada se
  desvía hasta 1.5 del 2.0 nominal (absorbe la física de intensidades).
- θ ≥ 75° o R ≥ 2: |ΔBhf| hasta 0.17 T, |ΔΓ| hasta 0.058, int1→1, int2→0:
  el patrón de 8 líneas ya no es representable con 6 líneas de pesos fijos
  (residuos estructurados en la figura de ejemplo).
- A6 (mapa de validez, θ=30°): el **1er orden con QUA efectivo** reproduce a
  SITE-1er-orden en todo el rango (|ΔBhf| ≤ 7·10⁻⁴ T), y el ajuste Kündig de
  espectros HC cruza el criterio de 0.05 T en **R ≈ 0.35**.

**Causa**: diferencia de modelo documentada (intensidades no dependientes de
la mezcla en Fitbauer). **Hoja de ruta**: calcular los elementos de matriz de
transición desde los autovectores de `core/hamiltonian.py` (los autovectores
ya se computan; faltan los factores de Clebsch-Gordan y las 2 transiciones
prohibidas).

### 6.2 EFG no axial (η, φ): no soportado

**Datos**: serie A5 (45 casos η×θ×φ, R=1). **Figura**: `fig_A5_sesgo_eta.*`.

Fitbauer no tiene η ni φ. Ajustando con el modelo axial (R=1): sesgo mediano
en Bhf de ~0.09–0.14 T (η=0.2–0.4) que crece a ~0.45 T (η=1.0), con máximos
de 4.8 T (η=0.2, θ=0, φ=90); en ΔEQ, mediana 0.02–0.4 mm/s creciente con η.
δ se mantiene robusto (mediana < 1.5·10⁻³, máx 0.12 mm/s). Hueco de capacidad puro; en polvo el efecto se promedia y
sería menor (no evaluado: SITE demo no promedia polvo).

### 6.3 Integral de transmisión (espesor)

**Datos**: F1 (t_a 0.1–20), F2, F3, I1. **Figuras**:
`fig_F_transmision_gamma.*`, `fig_F_ejemplo_t10.*`.

Con `IFTRAN`, SITE calcula la integral de transmisión **incluyendo la línea
de la fuente (WDS = 0.097 mm/s)**: en el límite fino la anchura observada es
WID+WDS = 0.347, no WID. Con esa referencia:

- **Modelo fino de Fitbauer** (F3/I1): Γ ajustada crece 0.363 → 0.396 → 0.440
  → 0.60 → 0.80 para t_a = 1, 5, 10, 30, 50: el clásico ensanchamiento de
  espesor sin corregir. δ **no** se sesga (< 10⁻⁵ incluso a t_a=50).
- **Saturación exponencial de Fitbauer** (`sat_scale`): mantiene Γ = 0.354
  estable hasta t_a = 10 (+0.008 sobre la referencia) — **funciona
  notablemente bien** en el rango práctico; a t_a = 20 ya no (Γ=0.54).

**Causa**: la saturación exponencial captura la saturación de profundidad pero
no la deformación de forma de línea de la integral exacta; suficiente hasta
t_a≈10. La profundidad/área no se comparó (parametrizaciones no equivalentes;
`DEP` deja de ser el área bajo IFTRAN — el `.RES` reporta el área real).

### 6.4 Γ comparable a la anchura de canal: cuenca de convergencia estrecha

**Datos**: C4 (Γ = 0.078 y 0.156 = 1× y 2× canal). **Figura**:
`fig_C4_lineas_estrechas.*`.

Con arranque exacto Fitbauer recupera Γ=1 canal con |ΔBhf| < 4·10⁻⁴ T (no hay
sesgo de discretización del modelo). Pero con arranque ±15 %: el χ² apenas
tiene gradiente cuando las líneas del modelo no pisan las medidas (cuenca de
anchura ~Γ), el multistart estándar (σ = 12 % del rango) no cae dentro, y el
ajuste colapsa (Bhf 33→44.7). **La pre-pasada DE lo resuelve** (χ²red 0.013).
Recomendación de uso: para líneas ≤2 canales, inicializar por detección de
picos o activar la optimización global.

### 6.5 Líneas libres: límite δ∈[−2,+3] mm/s

**Datos**: C3_fuera_de_rango (6 singletes en ±5.33/±3.08). Los singletes de
Fitbauer no pueden salir de δ∈[−2,3] (`COMPONENT_FIT_BOUNDS`): el ajuste queda
clavado en el borde (χ²red 1702). Con las mismas anchuras en posiciones
internas (C3 a ~11 T) el ajuste es exacto. Para "líneas sueltas" fuera de ese
rango Fitbauer no tiene hoy un tipo de componente adecuado (los límites son
correctos para δ físicos de ⁵⁷Fe). A7 con 8 líneas (dentro del rango): exacto,
usando 8 componentes headless.

### 6.6 Integración sobre el canal (E1)

**Datos**: E1 binned (256 y 128 canales crudos derivados por suma exacta de
pares de la teoría de 512; el demo de SITE no genera otros tamaños).

Fitbauer (como SITE-1994) evalúa el modelo en el centro del canal, no lo
integra sobre su anchura. Con datos generados por integración de canal:
Γ ajustada +0.004 (canal = 0.157 mm/s ≈ 0.6Γ) y **+0.023/+0.091**
(sexteto/doblete con canal = 0.31 mm/s ≈ 1.3Γ), profundidad −5 % en el caso
extremo. δ/ΔEQ/Bhf no se sesgan (simetría). Regla práctica cuantificada:
mantener canal ≤ Γ/3, o esperar Γ sobreestimada.

### 6.7 Degeneraciones físicas reales (ningún ajustador puede romperlas)

- **Doblete simétrico**: signo de ΔEQ inobservable (A2/S0) — ambos programas
  lo "eligen" arbitrariamente.
- **Doblete asimétrico** (B2): (ΔEQ, r) ≡ (−ΔEQ, 1/r) exactamente; χ²red
  ~10⁻⁷ en ambas ramas. Documentado y reconocido en la comparación.
- **Dobletes casi degenerados** (D6, ΔΔEQ ≤ 0.3): existe un re-emparejamiento
  de las 4 líneas con χ² idéntico (dos dobletes "cruzados" con ΔEQ ~0.02 y
  ~2.5); el ajuste cae indistintamente en una u otra solución y las σ por
  covarianza no capturan esta multimodalidad (z hasta ±800 en v1 pese a
  χ²red=1.06). Recomendación: ligar ΔEQ o δ cuando se sepa que dos dobletes
  son próximos.
- **D1_n05/n10**: doblete no resuelto (ΔEQ=0.7, Γ=0.25) + singlete a 0.55
  mm/s: intercambio parcial de papeles con χ² casi idéntico (desviaciones
  ~0.1-0.35 en δ/ΔEQ de esos dos componentes, el resto de los 10 sitios
  exactos).

### 6.8 Base no plana (E3)

**Datos**: E3 (parábola 0.2/0.5/1.5 % y rampa 0.5 % aplicadas al crudo).
**Figura**: `fig_E3_base_no_plana.*`.

La rampa lineal en v la absorbe `slope` sin sesgo (< 10⁻⁴). La parábola
(efecto geométrico que sobrevive al doblado) no tiene término en el modelo
de Fitbauer: sesgos crecientes hasta ΔΓ = 0.034 y Δdepth = −5 % (1.5 % de
curvatura), δ/Bhf casi inmunes (< 3·10⁻³). Hoja de ruta: término cuadrático
opcional en la base (NORMOS tampoco lo ajusta; lo corrige antes con BKGCOR).

### 6.9 Suelo de precisión del propio banco

La cuantización del `.PLT` de SITE (6 decimales) y la normalización P90 de
Fitbauer fijan un suelo de ~3·10⁻⁵ en profundidad absoluta y ~10⁻⁴ relativo.
Solo es visible en D3 con fase minoritaria ≤ 2 % (Γ del minoritario +0.04 a
1 %) y en las profundidades de A1c. No es un defecto de Fitbauer: es el techo
de fidelidad del generador. **Umbral D3** (figura `fig_D3_minoritaria.*`):
con base 10⁶ y ruido Poisson, el área de la fase minoritaria se recupera con
error relativo ~1.5–2 % para fracciones ≥10 %, ~10–25 % en 3–5 %, ~80 % a 2 %
y ~400 % a 1 % (no detectada): el umbral práctico de detección con esta
estadística está entre el 2 y el 3 % de área.

### 6.10 Robustez del arranque en multicomponente (D2/D4/I3)

Con perturbación ±15 % y multistart local (6–8 réplicas), **~40 % de fallo**
en 2 sextetes solapados (medido con 20 semillas en D2_db8); la mezcla de 4
sitios (D4_suelo, I3) solo converge sin multistart desde ±5 %. La pre-pasada
**DE** (global_opt) resolvió el 100 % de las semillas probadas (3–14 s por
ajuste). El banco final solo necesitó escalado en 14/318 casos. Recomendación
de uso Fitbauer: para multisitio solapado, inicializar por picos/mínimos o
activar la optimización global; el multistart gaussiano local no sustituye a
un buen arranque.

---

## 7. Estadística con ruido (v1, H)

**Figuras**: `fig_v1_pull_global.*`, `fig_H3_cobertura.*`.

- **χ²red** (v1, base 10⁶, series con modelo equivalente): mediana 0.976,
  p5–p95 = 0.78–1.25 ✅ (criterio 0.8–1.2).
- **Pull global** (1516 parámetros·casos): 63.5 % dentro de ±1σ, 91.8 % dentro
  de ±2σ, 95.7 % dentro de ±3σ. Forma gaussiana limpia; las colas provienen de
  las degeneraciones de §6.7. Las σ de Fitbauer son **ligeramente
  optimistas** (~10 % estrechas) — consistente con errores por covarianza sin
  término de correlación entre componentes solapados.
- **H3 (50 réplicas × 3 casos)**: doblete A2 64/93 %, sexteto A3a 62/92 %,
  mezcla D4 53/84 % (1σ/2σ). La infraestimación crece con el solapamiento
  entre componentes: para mezclas conviene bootstrap (disponible en Fitbauer)
  en lugar de covarianza.
- **H1 (bases 10⁴–3·10⁶)**: σ(δ) del sexteto 0.0126 → 0.0034 → 0.0015 →
  0.00087 mm/s: escala 1/√N limpia; z estables.
- **H2 (absorción 0.5 %)**: recuperación correcta con base 10⁶ y 10⁵ (z ≤ 2).
- **I4 (límite de detección, 0.2 % con base 10⁵)**: v0 exacto; con ruido el
  ajuste diverge (señal ≈ 2× ruido por canal) — límite físico, no defecto.

## 8. Bloque J — distribuciones P(BHF)/P(ΔEQ) contra NORMOS-DIST

**Figura**: `figuras/fig_J_distribuciones.*`. 15 espectros de distribución
(v0+v1 cada uno), ajustados con `fit_bhf_distribution_cli.py` (histograma
Hesse-Rübartsch + Tikhonov, α elegido por L-curve `--scan-alpha`, malla de
ajuste distinta de la de generación: 5–52 T / 47 bins).

- **J1 (9 gaussianas ⟨B⟩∈{25,30,35} × σ∈{1.5,3,5})**: ⟨B⟩ recuperada a
  ≤0.06 T (v0) y ≤0.23 T (v1). σ con el sesgo clásico de regularización:
  **+0.17…+0.40 T en v0** y hasta +1.5 T para la más estrecha (σ=1.5) con
  ruido — la L-curve sobre-suaviza distribuciones estrechas; para σ≥3 el
  sesgo relativo es <10 %.
- **J2 (bimodales 28/45 y 26/44 asimétrica)**: ambos picos localizados a
  ±0.5 T (media anchura de bin: mallas desplazadas medio paso); momentos
  globales a <0.1 T; la réplica con ruido resuelve las dos modas sin
  artefactos.
- **J3 (P(ΔEQ), generada con SITE por la limitación DTQ del demo)**: media a
  10⁻⁴ y σ a 3·10⁻⁴ mm/s en v0; con ruido, ≤0.012. El kernel de dobletes
  distribuidos de Fitbauer queda validado.
- **J4 (correlación δ(B), DTI 0.005/0.01)**: con `--delta-slope` verdadero y
  el δ de referencia correcto, la recuperación es idéntica al caso sin
  correlación (σ +0.16 T) → **el kernel correlacionado δ(H) de Fitbauer es
  correcto**. Ignorar la correlación con estas pendientes apenas sesga
  (σ +0.20 vs +0.16): con Γ=0.30 y pendientes ≤0.01 mm/s/T el efecto es
  menor que la anchura de línea. Ojo metodológico: el δ del kernel va FIJO y
  debe valer el δ verdadero en H_ref (media de la malla) — omitirlo produce
  σ sobreestimadas en un factor ~2 (error cometido y corregido durante la
  sesión, §11).
- **J5 (sensibilidad a α, base 10⁶)**: el resultado es insensible a α en
  0.01–100 (dominan los datos); el sobre-suavizado solo aparece a α≳10⁶
  (RMS ×40 a α=10⁸). La L-curve eligió α=0.01.

## 9. Serie extra X1 — relajación (capacidad de SITE fuera del plan)

SITE demo modela relajación (`IRELAX`+`OME`+`BH0`, Ising). Se generaron 4
espectros (OME = 0.3–10, unidades sin documentar) y se ajustaron con el
Blume-Tjon de Fitbauer: los espectros están en régimen de colapso parcial; el
ajuste converge y recupera δ exactamente; el Bhf efectivo ajustado crece con
OME (1.0 → 7.1 T), lo que sugiere que OME ~ inverso de la tasa de relajación.
Sin manual no hay mapeo cuantitativo OME↔ν: comparación cualitativa
archivada en `X1/` para trabajo futuro.

## 10. Capacidades no cubiertas por Fitbauer (hoja de ruta, no fallos)

1. Intensidades del Hamiltoniano completo (y transiciones ΔmI=±2) — §6.1.
2. η y φ del EFG — §6.2.
3. Integral de transmisión exacta (la saturación cubre hasta t_a≈10) — §6.3.
4. Término cuadrático de base — §6.8.
5. Integración del modelo sobre el canal — §6.6.
6. "Líneas sueltas" fuera de δ∈[−2,3] — §6.5.
7. >6 componentes en la GUI (el núcleo ya lo hace) — §4.
8. Isótopos ≠ ⁵⁷Fe (SITE demo tampoco los expone; sin datos de referencia).

## 11. Incidencias del propio banco (transparencia metodológica)

Fallos del arnés detectados y corregidos durante la sesión (ninguno afecta a
los resultados finales; todos los casos afectados se regeneraron/reajustaron):
namelist >72 columnas; NP ambiguo del `.PLT` con NSUB∈{3,5,7,9} (bloques
mezclados → se pasa NP explícito); semilla con `hash()` salteado (no
determinista → CRC32); `int2` de doblete fijado pese a pedir intensidades
libres; `sat_scale` no liberado en modo grueso; dirección y rama del mapeo
`D21`; tolerancia mal escalada para ratios γ2/γ3; eje de velocidad efectivo
de los espectros binned (E1); en el bloque J: δ de referencia omitido con
`delta_slope` (σ ×2), primer intento de P(ΔEQ) con el DTQ inoperante del
demo, y el CLI de distribución requiere el numpy≥2 del venv del repo (el
del sistema carece de `np.trapezoid`). El detalle está en el historial de
`generador/*.py`.

## 12. Reproducibilidad

```bash
cd /home/jorge/fitbauer
python3 validacion/generador/paso0_verifica_receta.py   # receta DOSBox
python3 validacion/generador/paso0_sondas.py            # sondas de capacidades
python3 validacion/generador/serie_S0_convenciones.py   # paso 0.6
python3 validacion/generador/series_AB.py               # bloques A-B
python3 validacion/generador/series_CG.py               # bloques C-F
python3 validacion/generador/fix_E1_E4_refits.py        # E1 binned + E4 512
python3 validacion/generador/series_HI.py               # v1 + H + I + X1
python3 validacion/generador/serie_J.py                 # bloque J (DIST)
python3 validacion/generador/analisis.py                # criterios v0
python3 validacion/generador/figuras.py                 # figuras del informe
```

- `resumen.csv`: una fila por (caso, versión, parámetro): verdadero, ajustado,
  σ, z, χ²red, convergencia, tiempo, notas de escalado.
- Cada caso: `SITE.JOB/RES/PLT/MOS`, `teoria_norm.npy`, `v0.dat`, `v1*.dat`,
  `verdad.json`, `fitbauer_*.json`.
- Requisitos: `SITE.EXE` en `/home/jorge/normos_work/` y `DIST.EXE` en
  `validacion/` (**software comercial
  WissEl: no subir jamás al repositorio**, cubierto por `*.EXE` en
  `.gitignore`), dosbox-staging con display X real, numpy/scipy/matplotlib.
- Total en disco: ~50 MB. Duración de la sesión completa: ~2 h (dominada por
  los ~800 ajustes; la generación SITE completa tarda <1 min).

---

## 13. Mejoras de modelo implementadas a raíz del banco (v4.18.0)

Tras la validación se implementaron en `core/` las cuatro extensiones que
eliminan los sesgos de modelo de §6 (todas opt-in; los 310 tests previos
pasan sin cambios y hay 10 tests nuevos en `tests/test_mejoras_normos.py`).
**Figura**: `figuras/fig_mejoras_antes_despues.*`; filas `version=v0m` en
`resumen.csv` (mismos espectros v0, re-ajustados con la mejora).

| Sesgo (§) | Mejora | Mediana \|Δ\| antes → después |
|---|---|---|
| §6.1 HC axial (A4) | `quad_treatment="hamiltonian"`: intensidades desde autovectores, 8 líneas | Bhf 0.0056 → 0.00024 T (×23); Γ ×7 |
| §6.2 η≠0 (A5) | ídem + `eta`/`phi` por componente | Bhf 0.306 → 0.0093 T (×33); Γ ×8 |
| §6.1 contraste (A6-HC) | ídem | Bhf 0.020 → 0.0019 T (×11) |
| §6.6 canal grueso (E1) | `channel_sub` (Gauss-Legendre sobre el canal) | Γ 0.021 → 0.0016 (×14) |
| §6.8 base curva (E3) | global `curv` | Γ 0.0073 → 2.6·10⁻⁵ (×285) |
| §6.3 espesor (F1/F2/I1) | `absorber_model="transmission"` (L_fuente ⊗ exp(−τ), `src_fwhm`) | Γ 0.105 → 0.0037 (×28) |

Verificación clave: los sesgos de §6 eran de MODELO (re-ajustando con
arranque exacto en la verdad el optimizador volvía al valor sesgado); con las
extensiones, el mismo protocolo recupera la verdad.

**Hallazgo sobre la "verdad absoluta"**: al validar el Hamiltoniano completo
se demostró que **NORMOS-SITE 27.01.1994 no es exacto a mezcla fuerte**: dos
configuraciones físicamente idénticas por rotación (η=1, B∥y, ΔEQ=+2) ≡
(η=1, θ=0, ΔEQ=−2) producen en SITE espectros distintos (Δ = 9.6·10⁻³, un
40 % del pico), mientras que la nueva implementación de Fitbauer es
rotacionalmente invariante y coincide con SITE a 3.7·10⁻⁵ exactamente en el
marco donde el estado fundamental es puro (sin términos de interferencia).
Conclusión (revisada en §19 con el código fuente): SITE pierde exactitud
NUMÉRICAMENTE (diagonalizador EISPACK complejo general en precisión simple,
autovectores sin ortonormalizar) en sus
intensidades; los residuos remanentes del banco a η≥0.8 (χ²red 1.5–6.6 en
v0m) miden el error de SITE, no el de Fitbauer. A η=1 existe además la
degeneración física exacta (ΔEQ, φ) ↔ (−ΔEQ, 90°−φ) que explica los
"fallos" aparentes de quad en la comparación.

Queda fuera (hoja de ruta §10): promedio de polvo del HC completo con
intensidades (la cuadratura existe para posiciones), ajuste simultáneo
θ/η/φ libres (identificabilidad no explorada), e isótopos ≠ ⁵⁷Fe.

---

## 14. Cierre del bloque "a lo que no llega" con el manual (v4.18.0, 2ª fase)

Con `validacion/sitedistmanual.odt` (NORMOS Programs, R.A. Brand, 10.7.1990)
disponible, se cerró el resto de la lista de §10 (excepto isótopos ≠ ⁵⁷Fe, a
petición) y se corrigieron entradas del inventario §4:

**Mejoras Fitbauer adicionales**
- **Líneas sueltas** (`wide_delta` en `ModelState`, opt-in): amplía los
  límites de δ a ±(vmax+2). C3_fuera_de_rango (6 líneas en ±5.33/±3.08):
  χ²red 1702 → 0.0002, posiciones exactas a 10⁻⁴ mm/s.
- **Hasta 10 componentes en la GUI**: `MAX_COMPONENTS` = 10 (fuente única en
  `core/params.py`, importada por los tres módulos Qt que duplicaban el 6).
  El banco ya había demostrado que el motor ajusta 10 sitios (D1_n10).

**Correcciones al inventario de SITE/DIST gracias al manual**
- **Ligaduras de SITE**: el mecanismo es `NDEX(i)=j, FACTOR(i), CONST(i)` →
  `PAR(i) = factor·PAR(j) + const` — formalmente IDÉNTICO al modelo de
  ligaduras de Fitbauer (`target = factor·source + offset`). (No era `NLINK`,
  que es el contador interno.)
- **Isótopos**: SITE sí los soporta vía `ISTYPE='119SN'` etc. (parámetro de
  carácter; mis sondas probaron claves numéricas). No ejercitado (excluido).
- **DIST `METHOD=6`** = distribución de cuadrupolo: J3 regenerado como
  distribución continua real (casos `J3d_*`): Fitbauer recupera ⟨ΔEQ⟩ a
  0.002–0.010 y σ a 0.005–0.024 mm/s (v0/v1) — kernel P(ΔEQ) validado
  también contra DIST, no solo contra el apilado de 10 dobletes de SITE.
- **DIST ofrece además** Czjzek y Le Caër (`DISTRI=4`), binomial con `CONC`,
  correcciones "EXACT" de EFG aleatorio (QUP/ETA) y bloques máx. MBLK=2 —
  anotado como referencia para futuras comparaciones.
- **`THE/PHI` de SITE**: θ entre B y Vzz; φ entre Vxx y B — exactamente la
  convención implementada en `full_hamiltonian_lines` (§13). `IFSC=.FALSE.`
  (nuestro caso) = muestra en polvo → el promedio isótropo del haz es la
  física correcta, como se asumió.
- **Relajación**: el manual fija `OME` en **MHz** (Ising = dos estados ±B,
  la misma familia que el Blume-Tjon de Fitbauer, con ν en s⁻¹; conversión
  esperada ν = OME·10⁶). Sin embargo el IRELAX del demo es **no monotónico
  en OME** (espectros de OME=0.01 y 1000 MHz casi idénticos entre sí y
  distintos del de OME=1; sondas `_staging/sondaR2`): el binario de
  demostración no permite validar el mapeo cuantitativo. X1 queda como
  comparación cualitativa y el mapeo documentado como "según manual,
  no verificable con este demo".

## 15. Robustez de convergencia: corregida en el motor (v4.18.0, 3ª fase)

Los dos fallos de robustez de §6.10 y §6.4 quedan resueltos de serie:

1. El corte por estancamiento del multistart ya no abandona candidatos
   mientras el mejor χ²red siga siendo malo (>2).
2. **Escalado global automático** (`auto_global`, por defecto): si el
   multistart local termina con χ²red>10, el motor lanza una pasada de
   evolución diferencial y un refinado local.

Re-medición del experimento de referencia (D2_db8: dos sextetos solapados,
arranques perturbados ±15 %, 20 semillas): **0/20 fallos** frente a los 8/20
del motor anterior (~5 s/ajuste de media; el coste solo se paga cuando el
ajuste local fracasa). El caso C4 (Γ≈1 canal) queda cubierto por el mismo
mecanismo. Todas las funciones nuevas están además expuestas en la GUI Qt con
ayuda y manuales (ES/EN recompilados; 8 idiomas de interfaz).

## 16. Segunda ampliación con el manual: extremos y centro de cada capacidad (series K y L)

Con el manual completo (R.A. Brand, 1990) se re-inventarió TODO lo que los
binarios de demostración pueden hacer y se añadieron pruebas con **extremos y
centro** de cada capacidad que el banco v1 no cubría. Sondas en
`validacion/paso2/` (`paso2_sondas_manual.py`, `paso2b_voigt_bkg.py`);
series nuevas `K1`–`K5` (SITE, `series_KL.py`) y `L1`–`L6` (DIST,
`serie_L.py`), más re-ajustes paramétricos del bloque J. Total añadido:
**34 espectros SITE + 15 DIST + 2 ajustes nativos de SITE**, ~230 filas
nuevas en `resumen.csv`.

### 16.1 Inventario de capacidades del demo (sondas)

| Capacidad (manual) | ¿Demo? | Serie | Resultado |
|---|---|---|---|
| Octetes `NLINE=8` + `D73` | ✔ | K1 | ✔ sexteto+2 singletes, χ²red≈0.003 |
| Fondo no constante `BKG(2..5)` | ✔ | K2 | ✔ (slope/curv); v³ no existe en Fitbauer |
| Cristal único `IFSC`+`BEX/GAX` | ✔ | K3 | ✘ documentado (Fitbauer promedia el haz) |
| Ligaduras `NDEX/FACTOR/CONST` | ✔ | K4 | ✔ equivalentes a las constraints |
| Binomial `DISTRI=3`+`CONC` | ✔ | L1 | ✔ (forma binomial); histograma sobre-suaviza extremos |
| Czjzek `METHOD=6`+`DISTRI=4` | ✔ | L2 | ✔ histograma recupera forma y momentos |
| Espejo negativo `PNEG` | ✔ | L3 | ✔ (degenerado: inobservable en polvo, verdad analítica) |
| `EXACT` (orden mixto, `QUP`) | ✔ | L4 | parcial: textura efectiva corregible, residuo crece con QUP |
| Textura en distribución `D13/D23` | ✔ | L6 | ✔ tras exponer `--d13/--d23` en el CLI |
| Perfil Voigt `VOIGT/WDLOR` | ✘ inoperante | — | Γ=WID Lorentziana pura en todos los casos (paso2b) |
| `STI` (distribución de δ) | ✘ inoperante | — | espectro idéntico con y sin STI |
| `DEPSUB` (perfil fijo arbitrario) | ✘ no existe en namelist | — | solo vía CONC (binomial) o SITE (J3) |
| Goldanskii-Karyagin `IFGK`+`G2x` | ✘ inoperante | — | PLT idéntico al polvo |
| `S2T` (⟨sin²θ⟩ de EXACT) | ✘ no existe en namelist | — | intensidades EXACT no configurables |

### 16.2 Aciertos (mención)

- **K1 octetes**: las líneas ΔmI=±2 se modelan exactamente con sexteto + 2
  singletes (χ²red 0.003–0.006 en D73∈{0.087,0.25,0.5} y B∈{33,46}); la
  partición de áreas DEP·D73/(2·ΣD) se recupera al 10⁻³
  (`fig_K1_octete`).
- **K2 fondos**: lineal, parabólico y combinado exactos una vez descifrado el
  convenio (fondo = 1 + Σ (BKG(k)/1000)·(v/2v_max)^(k−1); el ~2 % de sesgo
  residual de slope es la normalización P90, documentada en §3).
- **K4 ligaduras nativas**: SITE ajustando con `NDEX/FACTOR/CONST` y
  Fitbauer con `constraints` recuperan la misma verdad sobre el mismo v1
  (δ ligada: |Δδ|≤1.4e-3 ambos; áreas 2:1: |Δdepth|/depth <2 %): **los dos
  motores de ligaduras son semánticamente idénticos**
  (PAR(i)=FACTOR·PAR(j)+CONST ≡ target=factor·source+offset).
- **K5 extremos**: QUA=±0.6, BHF=1 T (colapso) y 60 T, D13∈{1.5,4.5},
  W13=2.5/W23=0.6, Γ=0.16 subnatural, profundidad 40 % y dobletes con
  δ=−2.5/+3.4 vía `wide_delta`: todo dentro de tolerancias v0.
- **L1–L3**: binomial (forma paramétrica: p recuperado a ±0.026 incluso en
  CONC=10/90 %), Czjzek (σ a ±0.04) y PNEG (la verdad analítica plegada
  confirma que el espejo negativo es espectralmente inobservable: espectros
  de PNEG=0.2 y 0.5 idénticos).
- **L5 formas paramétricas**: `--shape gaussiana` recupera ⟨B⟩ a <0.02 T y σ
  a <0.18 T en la rejilla J1; `--shape vbf` N=2 clava momentos y picos
  (±0.5 T = resolución de la malla) en los bimodales J2. Los
  regularizadores `tv` y `maxent` sobre J1_b30_s3 v1 dan σ +0.42 (comparable
  al Tikhonov de referencia).

### 16.3 Fallos documentados

1. **Cristal único (K3, `fig_K3_cristal_unico`)**. Con `IFSC=.TRUE.` SITE
   fija la orientación del rayo γ en el sistema del EFG (BEX/GAX) y las
   intensidades de línea cambian; el tratamiento hamiltoniano de Fitbauer
   promedia el haz isotrópicamente (muestra en polvo). Posiciones ✔,
   intensidades ✘ → χ²red 3.4–8.0 y sesgos aparentes (BHF −0.9 T) en las
   orientaciones extremas (β_γ=0 y β_γ=φ_γ=90). Causa: capacidad no
   modelada; hoja de ruta si algún día interesa (requiere W(θ,φ) del haz por
   componente). En el caso de POLVO el residuo restante (máx 6.0e-3 = 20 %
   del pico en η=0.5, θ=30°) NO es de Fitbauer: es la aproximación de
   SITE-1994 (degradación numérica del diagonalizador, confirmada en el
   código fuente — §19);
   el ajuste lo redistribuye en BHF −0.38 T y ΔEQ +0.14.
2. **Fondo cúbico (K2_cubico, `fig_K2_fondo`)**. `BKG(4)` genera un término
   v³ que Fitbauer no tiene (baseline+slope·v+curv·v²): slope/curv absorben
   parte y queda χ²red 2.5. Extremo raro en la práctica; documentado como
   límite consciente.
3. **Cota de slope (K2_lin_p60)**. El extremo BKG(2)=60 (slope verdadero
   7.5e-3) excedía la cota histórica ±0.005 → χ²red 61 con el ajuste
   degenerado. **Corregido**: cota ±0.02 (χ²red → 3e-7).
4. **Cota de ΔEQ (K5_dob_q5)**. SITE admite ΔEQ=5; la cota clásica ±4 de
   Fitbauer degeneraba el ajuste (χ²red 82, δ→2.85). **Corregido**:
   `wide_delta` amplía también ΔEQ a ±2(v_max+2) (χ²red → 1e-7).
5. **Textura en distribuciones (L6, `fig_L_textura_exact`)**. DIST admite
   `D23≠2` por bloque; el kernel del CLI fijaba 3:2:1 → pico fantasma a
   ~15 T y σ +47 % (D23=3), σ +134 % (D23=1). **Corregido**: el kernel ya
   soportaba intensidades (mossbauer_distribution) y se exponen
   `--d13/--d23` en el CLI (mapeo int3_rel=3/D13, int2_rel=3·D23/(2·D13));
   con `--d23 3` el sesgo desaparece (σ 3.21 vs 3.0).
6. **EXACT de DIST (L4, `fig_L_textura_exact`)**. Con `EXACT=.TRUE.` el
   demo aplica un patrón de intensidades efectivo ≈3:3:1 **independiente de
   QUP** (medido con QUP=0; S2T no está en el namelist) más correcciones de
   orden mixto que sí crecen con QUP. Con `--d23 3` Fitbauer captura el
   límite QUP→0 (σ 3.38 vs 4.55); el residuo restante crece con QUP
   (σ +0.4/+0.8/+2.4 para QUP=0.2/0.5/1.0): dominio de validez del kernel
   de 1er orden, como el mapa R de §5.
7. **Histograma en binomiales extremas (L1, `fig_L1_binomial`)**. Con
   CONC=10/90 % la distribución es estrecha y pegada al borde de la malla:
   la regularización del histograma la sobre-suaviza (σ +71/+20 %). No es
   un fallo del modelo sino del regularizador con verdad casi-delta (ya
   visto en J5); la forma paramétrica binomial lo resuelve (p a ±0.026).

### 16.4 Mejoras implementadas en esta fase (post-v4.18.0)

1. `wide_delta` amplía también la cota de ΔEQ (core/session.py).
2. Cota de `slope` ±0.005 → ±0.02 (core/params.py, GUI incluida).
3. `--d13/--d23` en `fit_bhf_distribution_cli.py` (textura del kernel de
   distribución, convenio NORMOS).

Tests nuevos: `tests/test_mejoras_banco_normos2.py` (5); suite completa
**337 tests** en verde.

### 16.5 Convenciones nuevas de SITE/DIST descifradas

- **Líneas 7,8 del octete**: el demo las coloca en ±1.40108·(B/33) mm/s,
  un 0.32 % por debajo del valor implicado por su propio patrón sextete
  (±1.4055 = (1.5a_e−0.5a_g)·k). Medido por ajuste de 8 Lorentzianas; se
  usa el valor empírico como verdad.
- **Fondo**: `1 + Σ_{k≥2} (BKG(k)/1000)·(v/(2·VMAX))^{k−1}` (el "V1" del
  manual resulta ser 2·VMAX en el demo); verificado con ±BKG a dos
  amplitudes en lineal y parabólico.
- **NDEX**: numeración por índice GLOBAL de la tabla "Index" del RES
  (BKG(1)=1; subespectro k: WID=14+15(k−1), ARE=+1, ISO=+2, …). El RES
  imprime la ligadura ("Variable31(ISO) = 1.0·Variable16(ISO)+0.4") y
  reduce NVAR.
- **EXACT**: intensidades efectivas ≈3:3:1 fijas (D13/D23 ignoradas, S2T
  inaccesible); las correcciones de posición/anchura sí escalan con QUP.

## 17. Tercera tanda: extremos y centro sobre las series originales

Las rejillas de la fase 1 eran deliberadamente centrales; `series_ext.py`
añade los puntos extremos que faltaban DENTRO de cada serie ya existente
(24 casos, v0+v1): dobletes con δ=−1.0/+2.0 y ΔEQ de 0.08 (≪Γ) a 5 mm/s,
sextetos de 0.5 y 58 T, Γ de 0.16 a 2.0, profundidades de 0.5 % a 40 %,
D21∈{0.3, 3}, pares de anchura invertidos (W13=0.7/W23=1.3), η=0.1,
QUA=±0.45, dobletes casi degenerados (dΔEQ=0.02), gaussianas P(B) en los
bordes de la malla y casi-delta (σ≈paso), y DTI negativa (−0.01) y fuerte
(+0.02).

Resultado: **todo converge (0 no-convergencias) y todo lo identificable
sale**. Las únicas desviaciones son las esperables y quedan atribuidas:

- `D6_dq0.02` — degeneración práctica real (dos dobletes a 0.02 mm/s:
  soluciones equivalentes con χ²red≈1; le pasaría igual a NORMOS).
- `D3_f0.5pc` — por debajo del límite de detección con ruido (χ²red 0.83
  con el doblete errante; el umbral medido en D3 sigue siendo ~1–2 %).
- `A5_eta0.1` v0 (Kündig+intensidades libres) hereda el sesgo conocido de
  int1 (2.1 vs 3); el re-ajuste v0m con `quad_treatment="hamiltonian"`
  lo elimina, coherente con §13.
- `J1_b30_s0.8` y `J1_b15_s3` — sobre-suavizado del histograma en
  casi-delta y borde de malla (compromiso del regularizador, como L1/J5;
  las formas paramétricas lo resuelven).
- `J4_dti±` — la correlación δ(B) funciona con signo negativo y pendiente
  doble; ignorarla (v0_sin_slope) duplica el error de σ.

La sonda adicional `_staging/polar` confirma que la **fuente polarizada**
(DIST `METHOD=4`) sí funciona en el demo y transforma el espectro por
completo (max|Δ|≈0.9): capacidad de NORMOS sin equivalente en Fitbauer,
incorporada al veredicto.

**El veredicto completo (lo que sale, lo que no sale y por qué, y qué tiene
cada programa que el otro no) está en `VEREDICTO.md`**, con la síntesis
numérica generada por `veredicto_datos.py`.

## 18. Tres capacidades cerradas (v4.19): cristal único, kernel HC y fondo v³/v⁴

De las cuatro capacidades que el veredicto (§VEREDICTO.md) señalaba como "lo
que le falta a Fitbauer", se implementaron y validaron las tres primeras
(`valida_v4_19.py`, `fig_v419_mejoras`); queda solo la fuente polarizada
(baja demanda, se implementará si hace falta).

1. **Cristal único** (`quad_treatment="hamiltonian_sc"`, parámetros
   `bex`/`gax`): dirección fija del haz γ con suma coherente entre canales de
   radiación (matriz de Wigner d¹). Anclas físicas: patrón 3:0:1 con haz∥B y
   3:4:1 con haz⊥B en el límite axial; el promedio isótropo sobre
   direcciones reproduce el modo polvo a 1e-15. Re-ajuste del banco K3 con
   los ángulos verdaderos e intensidades FIJAS: χ²red 3.5/12.4*/20.4* → 
   2.9/2.3/2.5 (*con la convención corregida; el primer intento con
   GAX literal empeoraba: el barrido teoría-contra-teoría reveló que el
   GAX del demo se mide desplazado 90° del azimut geométrico —
   gax_Fitbauer = GAX_SITE + 90°, nueva convención documentada). El χ²red
   restante ≈2.5 es el suelo de la aproximación de SITE-1994 (idéntico al
   caso polvo).
2. **Kernel Hamiltoniano en distribuciones**
   (`kernel_treatment="hamiltonian"` + η; CLI `--kernel-treatment`): promedio
   de polvo del Hamiltoniano completo por columna del kernel; ΔEQ = módulo
   del EFG aleatorio (análogo no perturbativo del EXACT/QUP de DIST).
   Detalle físico clave: el promedio se hace en el MARCO DEL CAMPO (B∥z,
   EFG inclinado; nueva `full_hamiltonian_lines_field`) para que la textura
   D13/D23 quede ligada a B — en el marco del EFG el promedio la diluía a
   isótropa (bug detectado y corregido durante la validación). Round-trip
   sintético: momentos exactos (test). Banco L4 (v0h): σ a QUP=1 pasa de
   +2.4 T (1er orden) / +2.4 (d23 solo) a **+1.0 T**, y ⟨B⟩ queda a 0.04 T;
   el residuo restante es la propia truncación perturbativa del EXACT del
   demo (3er/4º orden) más su patrón 3:3:1 no configurable.
3. **Fondo v³/v⁴** (`curv3`/`curv4`): K2_cubico pasa de χ²red 2.5 a 2e-7 con
   curv3 recuperado a 3 cifras; caso nuevo K2_cuartico (BKG(5)=60) exacto.

Todo expuesto en la GUI (menú contextual de ΔEQ con el 5º tratamiento;
selector "Kernel" + η en el panel de distribución; Base v³/v⁴ en
calibración), con sesiones, i18n en 8 idiomas y manuales ES/EN actualizados.
Tests: `tests/test_mejoras_v4_19.py` (11).

## 19. Hallazgos del código fuente de NORMOS (2026-08-02)

Con el código fuente (Fortran, fechado 1990; el binario demo es de 1993/94 y
difiere en algunos puntos — se indica) quedaron resueltos los misterios
abiertos y validada una capacidad nueva. El fuente es propietario y NO está
en el repositorio (`normos/` doblemente excluido); aquí solo se documenta la
matemática.

1. **La "aproximación" del HAMILT de SITE es numérica, no analítica** —
   corrección a §13/§16.3: el GMFP (Ruebenbauer–Birchall) es exacto
   (Hamiltoniano exacto, coherencia completa incluida la del fundamental,
   promedio de polvo analítico). La desviación medida (3.7e-5 → 9.6e-3 según
   marco) viene del diagonalizador: EISPACK complejo GENERAL en precisión
   simple, autovectores sin normalizar ni ortogonalizar usados como base
   unitaria, MACHEP=2⁻⁴⁷ (doble precisión) en código REAL*4 e IERR ignorado.
   Error ∝ ε·‖H‖/gap → dependiente del marco. La conclusión práctica no
   cambia: Fitbauer (LAPACK hermítico en doble precisión) es más exacto.
2. **GAX**: en el fuente de 1990 es el azimut estándar desde x (como φ); el
   +90° del binario apunta a convención de Euler zxz en el ejecutable de
   1994 (equivale exactamente a un desfase de 90° en el azimut). El fuente y
   el binario difieren demostrablemente (bug de paso de argumentos η/θ/φ en
   el llamador del fuente que el binario no tiene).
3. **EXACT de DIST**: teoría de perturbaciones en R = −14.755·QUP/H
   (posición a 4º orden, área a 3º con suma nula — por eso las intensidades
   no dependen de QUP —, ensanchamiento en cuadratura por línea). S2T ocupa
   la RANURA de D23 (EQUIVALENCE): por eso "S2T no existe" en el namelist.
   El default del binario se comporta como S2T≈6/7 (→ el patrón 3:3:1
   medido), distinto del 2/3 del fuente; el mapeo del binario es no trivial
   (sondas registradas). El kernel hamiltoniano de Fitbauer contiene
   estrictamente más física que EXACT.
4. **STI**: solo implementado para METHOD=6/7 (satélites gaussianos de 5
   puntos en δ); en distribuciones de campo es solo cosmético del listado.
   **DTQ** en METHOD=1: no existe en esa rama (por diseño). Confirmadas las
   fórmulas exactas de DISTRI=2 (compensación σ²+Δ², PNEG espejo),
   binomial (n=12) y Czjzek/Le Caër; el suavizado LAMDA es exactamente la
   matriz D₂ᵀD₂ de segunda diferencia (el mismo Tikhonov de Fitbauer), sin
   pesos Poisson y con anclajes β₁/β₂ en los extremos.
5. **Voigt**: ¡NO estaba inoperante! El binario de 1994 cambió la semántica:
   la anchura gaussiana es STG(n) (σ en mm/s para paramagnéticos — la MISMA
   convención que Fitbauer —, σ_B en Tesla para sextetes = distribución
   gaussiana de campo). Verificado con sondas (σ recuperada a 3 cifras).
   Pasa de "no validable" a validable.
6. **Fuente polarizada (METHOD=4/POLAR)**: implementada en Fitbauer desde
   primeros principios (peine 36 líneas por selección de helicidad,
   I(i,j) ∝ |m_q|²|m_q|² Σ_λ |d¹|²|d¹|²) y validada contra el binario:
   0.4 % del pico (θ_s=0) y 1.1 % (θ_s=90). Round-trip completo del banco
   (casos L7): ⟨B⟩ a 0.08 T y σ a 0.13 T con ruido. CLI:
   `--source-polarized --source-bhf --source-theta --absorber-theta`.
   El POLAR de SITE es el mismo modelo (γ∥B) para sextetes discretos.
7. **IFGK**: inerte con IFSC (el ramal de cristal no usa los G) y para
   ⁵⁷Fe sin mezcla solo G11 puede actuar — explica el "sin efecto" de las
   sondas. **IFTRAN**: matemáticamente idéntico a la integral de
   transmisión de Fitbauer (misma fuente 0.097). **Fondo**: aditivo sobre
   la base (no multiplica la absorción), como en Fitbauer; nuestra fórmula
   empírica del convenio BKG es exacta. **Ligaduras**: numeración global
   confirmada (base 13+15(n−1)); NLINK se lee pero no se usa; bug de NORMOS
   en la propagación de errores de parámetros ligados (usa CONST donde
   debería FACTOR). **σ del ajuste**: Poisson sobre cuentas dobladas; el
   χ² del RES divide por el MODELO con DF=NP−1−NVAR (convención a imitar
   al comparar). **Relajación**: OME está en mm/s (no MHz) y es la forma
   cerrada de Blume de dos estados. Sondas adicionales (relax2) CIERRAN el
   punto como no-validable: BSAT no existe en el namelist del binario y los
   espectros IRELAX del demo salen casi colapsados incluso con OME=0 — el
   cableado de parámetros del ejecutable de 1994 difiere del fuente de 1990
   y no es reconstruible por caja negra. X1 queda como comparación
   cualitativa, ahora con la física de referencia identificada.


## 20. Serie V (Voigt del binario) y fuente polarizada en la GUI (2026-08-02)

- **Serie V**: con la semántica STG descubierta en §19.5 se validó el perfil
  Voigt round-trip. Paramagnético (V1, σ ∈ {0.05, 0.15, 0.30} mm/s):
  Fitbauer con perfil Voigt y σ LIBRE recupera σ a ≤4·10⁻³ mm/s (a σ=0.05,
  6.6·10⁻⁵), con una leve compensación σ↔Γ (Γ −0.7…−1.7 %) atribuible al
  pseudo-Voigt aproximado del binario frente al Voigt exacto de Fitbauer.
  Magnético (V2, σ_B ∈ {0.5, 1.5, 3} T): la forma "Gaussiana" de Fitbauer
  clava ⟨B⟩ (≤4·10⁻³ T) y σ_B (exacta en 1.5/3 T; +0.046 en 0.5 T donde
  σ_v ≈ Γ/2). El Voigt pasa de "no validable" a VALIDADO.
- **Fuente polarizada en la GUI**: casilla "Fuente polarizada (γ∥B)" en el
  panel de distribución con B fuente y ángulos fuente/absorbente-haz,
  persistencia de sesión y test de cableado; i18n en 8 idiomas y manuales
  ES/EN actualizados (§ nueva en el capítulo de distribuciones).


## 21. Revisión del código fuente completo y cierre de cobertura (2026-08-02)

Barrido sistemático de los diez niveles del fuente Fortran (SITE + DIST, 1990)
contra `core/`, verificando cada uno contra el binario demo o contra
referencias independientes. Resultado en dos documentos:

- **`COBERTURA_NORMOS.md`** — inventario COMPLETO de capacidades: se extrajo la
  lista de parámetros e interruptores de los namelist (`sitemdos.for`,
  `distmdos.for`) y se cruzó una por una. De ~60 capacidades, Fitbauer iguala o
  mejora todas las del dominio de ⁵⁷Fe salvo seis, y es medibleme mejor en seis
  puntos concretos.
- **`PENDIENTE_NORMOS.md`** — hoja de ruta de lo que queda, con referencia del
  fuente, qué tocar, cómo validarlo y si merece la pena.

Se cerraron en esta revisión: convenio de posiciones del sexteto seleccionable,
asimetría de línea (AKS), convenio de intensidades por área, doblado con
interpolación cúbica (Γ salía hasta un 9.5 % alto), efecto geométrico, dos
ciclos de búsqueda, recuperación de los canales de borde, fracción resonante de
la fuente (FSO), kernel de la fuente 19× más exacto, barras de error con σ
absolutas, errores de parámetros ligados, polarización de poblaciones en
relajación, anclajes de borde en distribuciones con diagnóstico `edge_pileup`,
P(δ) expuesta y anchuras por dispersión (modelo de Brand).

Suite del programa: 483 tests.
