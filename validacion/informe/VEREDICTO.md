# Veredicto final: Fitbauer frente a NORMOS

**2026-08-01 (actualizado tras v4.19.0).** Síntesis de las CUATRO tandas del
banco de validación round-trip
(NORMOS-SITE/DIST genera → Fitbauer ajusta → comparación con la verdad):
fase 1 (plan original, §1–§15 del INFORME), 2ª ampliación con el manual
(series K/L, §16) y 3ª tanda de **extremos y centro sobre las series
originales** (`series_ext.py`: dobletes con δ=−1/+2 y ΔEQ de 0.08 a 5 mm/s,
sextetos de 0.5 a 58 T, Γ de 0.16 a 2.0, profundidades del 0.5 al 40 %,
D21 de 0.3 a 3, pares de anchura invertidos, dobletes casi degenerados,
gaussianas P(B) en los bordes de malla y casi-delta, correlación δ(B)
negativa y fuerte), más la validación de las capacidades v4.19
(`valida_v4_19.py`: cristal único, kernel Hamiltoniano y fondos v³/v⁴,
§18 del INFORME).

**Totales**: 411 espectros sintéticos de NORMOS, ~1.150 ajustes de Fitbauer,
6.497 filas de comparación (`resumen.csv`), 19 figuras. Los números de este
documento salen de `veredicto_datos.py`. Suite de tests del programa: 349 en
verde.

---

## 1. Lo que SALE: dónde Fitbauer reproduce a NORMOS

Mediana y percentil 95 de |ajustado − verdadero| sobre los ajustes v0 (sin
ruido; con las extensiones v4.18 donde aplican). Unidades: mm/s (posiciones,
anchuras), T (BHF).

| Bloque (casos) | posición | BHF | anchura | comentario |
|---|---|---|---|---|
| **Núcleo 1er orden** (101) | 2·10⁻⁷ / 1.5·10⁻⁵ | 4·10⁻⁵ / 1.1·10⁻⁴ | 8·10⁻⁷ / 1.2·10⁻⁴ | **exacto**, incluidos todos los extremos nuevos |
| **Hamiltoniano completo** (96) | 6·10⁻⁵ / 4·10⁻³ | 8·10⁻⁴ / 0.056 | 5·10⁻⁴ / 0.02 | tras v4.18; la cola restante es la aproximación del propio SITE-1994 (§16.3-1) y la degeneración de signo en η=1 |
| **Textura e intensidades** (19) | 2·10⁻⁷ / 2·10⁻³ | 2·10⁻³ / 0.034 | 2·10⁻⁵ / 0.014 | D23 de 0 a 4, D21 de 0.3 a 3, D13 de 1.5 a 4.5 |
| **Líneas libres / anchuras** (20) | exacto | — | exacto | W13/W23 de 0.6 a 2.5 e invertidos; C3_fuera_de_rango resuelto por `wide_delta` (se conserva como evidencia histórica) |
| **Multisitio y ligaduras** (39) | 2·10⁻⁴ | 2·10⁻⁴ | 2·10⁻⁴ | hasta 10 sitios; la cola son degeneraciones físicas (D6, §2b) |
| **Adquisición** (21) | 2·10⁻⁷ | 6·10⁻⁵ | 3·10⁻⁵ | 128–1024 canales, vmax 2–15, bases no planas |
| **Espesor / transmisión** (14) | 2·10⁻⁵ | 3·10⁻⁴ | 4·10⁻³ | τ de 0.1 a 50; Γ con sesgo p95 7·10⁻³ por la degeneración Γ↔fuente (fuente fijada) |
| **Octetes y fondos** (14) | 2·10⁻⁷ | 6·10⁻⁵ | 3·10⁻⁵ | NLINE=8 como sexteto+2 singletes; fondos BKG(2)…BKG(5) exactos con slope/curv/curv3/curv4 (v4.19) |
| **Cristal único** (7, v4.19) | 0.04 / 0.22 | 0.38 / 0.71 | 0.014 / 0.024 | `hamiltonian_sc` con BEX/GAX verdaderos e intensidades FIJAS: χ²red 2.3–3.4; la desviación restante es la aproximación de SITE-1994 (idéntica al caso polvo) |
| **Ligaduras nativas de SITE** (2) | ≤1.4·10⁻³ | 0.02–0.03 | ≤5·10⁻³ | ambos motores (NDEX y constraints) recuperan la misma verdad sobre el mismo espectro con ruido |
| **Extremos K5** (12) | exacto | ≤9·10⁻³ | ≤7·10⁻⁴ | ΔEQ=5, B=1 y 60 T, δ fuera de rango, Γ subnatural, 40 % |

Distribuciones (momentos de P; |Δ⟨x⟩| / |Δσ| medianos, v0+v1):

| Grupo | ⟨x⟩ | σ | comentario |
|---|---|---|---|
| J1 gaussianas (rejilla interior) | 0.02 T | 0.15 T | histograma Hesse-Rübartsch + L-curve |
| J2 bimodales | 0.03 T | 0.03 T | picos a ±0.5 T (resolución de malla) con VBF N=2 |
| J3 P(ΔEQ) (SITE y DIST METHOD=6) | 0.002 | 0.007 | |
| J4 correlación δ(B), DTI −0.01…+0.02 | 0.04 T | 0.20 T | signo y magnitud correctos; ignorarla duplica el error |
| L1 binomial (forma paramétrica) | — | — | **p recuperado a ±0.026 en CONC=10…90 %** |
| L2 Czjzek | 0.004 | 0.015 | el histograma reproduce la forma sin necesitarla analítica |
| L3 PNEG | 0.01 | 0.02 | verdad analítica plegada (la parte negativa es inobservable) |
| L6 textura D23 (con `--d23`) | 0.004 | 0.21 | corregido en esta fase |
| L4 EXACT (kernel HC, v4.19) | 0.04–0.20 | 0.34–1.0 | kernel por diagonalización exacta; el residuo (crece con QUP) es la truncación perturbativa del propio EXACT del demo |

La calidad estadística también sale: χ²red mediano 0.976 en v1, pulls
64/92/96 % dentro de 1σ/2σ/3σ, y la cobertura H3 (50 réplicas × 3 casos)
compatible con las σ reportadas. Robustez: 0/20 fallos de arranque en el
caso duro D2 (antes 8/20).

**En resumen: en todo el dominio que ambos programas comparten, Fitbauer
reproduce a NORMOS al nivel de 10⁻⁴–10⁻³ mm/s — muy por debajo de cualquier
incertidumbre experimental — incluidos los valores extremos de cada
parámetro.**

## 2. Lo que NO SALE

### 2a. Capacidades de NORMOS que a Fitbauer le faltaban

**Actualización v4.19 (§18 del INFORME): los puntos 1, 3 y 4 quedaron
CERRADOS** — cristal único (`hamiltonian_sc`), fondo v³/v⁴ (`curv3`/`curv4`)
y orden mixto en distribuciones (`kernel_treatment="hamiltonian"`). Queda
abierta solo la fuente polarizada (2).

1. **Cristal único / muestra orientada** (SITE `IFSC` + `BEX/GAX`;
   `fig_K3_cristal_unico`). ✅ CERRADO en v4.19: nuevo tratamiento
   `hamiltonian_sc` (haz γ en dirección fija bex/gax, suma coherente entre
   canales); χ²red del banco K3: 3.5–20 → 2.3–3.4 con intensidades fijas
   (resto = aproximación de SITE-1994). Convención: GAX_demo = gax − 90°.
2. **Fuente polarizada** (DIST `METHOD=4`/`POLAR`, sextete fuente ×
   absorbente 6×6). Sondeada en el demo: transforma el espectro por completo
   (max|Δ| ≈ 0.9 del pico). Sin equivalente en Fitbauer.
3. **Fondo polinómico de orden alto**: ✅ CERRADO en v4.19 (`curv3`/`curv4`):
   el cúbico pasa de χ²red 2.5 a exacto y el cuártico (BKG(5)) se recupera a
   3 cifras (`fig_v419_mejoras`).
4. **Correcciones de orden mixto en distribuciones** (DIST `EXACT`):
   ✅ CERRADO en v4.19 (`kernel_treatment="hamiltonian"`): kernel por
   diagonalización exacta con promedio de polvo en el marco del campo;
   σ a QUP=1 pasa de +2.4 a +1.0 T y ⟨B⟩ queda exacto — el residuo restante
   es la truncación perturbativa del propio EXACT del demo
   (`fig_v419_mejoras`).
5. **Isótopos ≠ ⁵⁷Fe** (`ISTYPE`: ¹¹⁹Sn, ¹⁹⁷Au, ¹⁵¹Eu, ¹²¹Sb, genérico
   3/2–1/2): fuera del alcance por decisión explícita (el demo tampoco los
   acepta).
6. **Asimetría por vecinos** (DIST `METHOD=2/3`, Billard–Chamberod con
   CONC/PROB/S2): no probado (sin contraparte directa en Fitbauer; se puede
   aproximar con multisitio o la 2D, pero no se ha validado).
7. **Métodos con ficheros de simulación externos** (DIST `METHOD=5/7`,
   TAPE4): requieren el programa SIMDATA que no tenemos; no comparables.

### 2b. Límites compartidos (no son fallos de Fitbauer)

- **Degeneraciones físicas**, idénticas en ambos programas: signo de ΔEQ en
  dobletes; rama (quad, int2) ↔ (−quad, 1/int2); dobletes casi degenerados
  (D6 dΔEQ=0.02: soluciones equivalentes con χ² perfecto); Γ↔anchura de
  fuente (Lorentziana⊗Lorentziana); PNEG (el espejo negativo de P(ΔEQ) es
  espectralmente inobservable — demostrado: los espectros de PNEG=0.2 y 0.5
  son idénticos); signo del EFG en η=1 (permuta de ejes).
- **Regularización de histogramas**: con distribuciones casi-delta
  (σ ≈ paso de malla) o pegadas al borde, el histograma sobre-suaviza
  (J1_b30_s0.8: σ 1.7 vs 1.25 en v0; L1 CONC=10/90 %). Es el compromiso
  sesgo-varianza de Hesse-Rübartsch — el DIST original hace lo mismo con
  LAMDA — y las formas paramétricas (gaussiana/VBF/binomial) lo resuelven.
- **Límite de detección**: un doblete del 0.5 % del área con 10⁶ cuentas es
  irrecuperable con ruido (χ²red 0.83 con parámetros errantes); el umbral
  práctico medido está en ~1–2 % (D3).
- **La aproximación de SITE-1994 en el Hamiltoniano completo**: a mezcla
  fuerte SITE pierde exactitud NUMÉRICAMENTE en su diagonalizador (EISPACK complejo
  general en precisión simple, autovectores sin ortonormalizar) y viola
  la invariancia rotacional (§13). En el caso polvo K3 la teoría de SITE se
  desvía 6·10⁻³ (20 % del pico) del Hamiltoniano exacto: ahí "no salir" de
  la verdad-NORMOS significa que **Fitbauer es más exacto que la referencia**.

### 2c. No validable con el demo (limitaciones del binario 1994, no veredictos)

Perfil pseudo-Voigt (`VOIGT/WDLOR` inoperante), distribución de δ (`STI`
inoperante), perfil fijo arbitrario (`DEPSUB` no existe en el namelist),
Goldanskii–Karyagin (`IFGK` sin efecto), `S2T` (no existe), relajación
cuantitativa (`OME` no monotónico), `DTQ` en METHOD=1, más de 512 canales,
NSUB>10 e isótopos (`ISTYPE` rechazado). Todo ello está en el manual del
NORMOS completo pero este demo no lo ejecuta: queda fuera del veredicto.

## 3. Lo que Fitbauer tiene y NORMOS no

**Física y modelo**

- **Hamiltoniano estático completo exacto** (intensidades desde autovectores,
  invariancia rotacional verificada): más exacto que el HAMILT de SITE-1994.
- **Perfil Voigt real** operativo (el pseudo-Voigt del demo no funciona; el
  del NORMOS completo es la aproximación de David).
- **Relajación cuantitativa**: Blume–Tjon con frecuencia en Hz (el
  IRELAX/SRELAX de SITE es cualitativo y en el demo su OME ni siquiera es
  monotónico) y modelo superparamagnético de Néel con distribución de
  tamaños.
- **Distribuciones**: regularizadores TV y máxima entropía con gradiente
  analítico, selección automática de α por L-curve, forma VBF multi-gaussiana
  (Rancourt–Ping), forma binomial paramétrica, **distribución 2D
  P(BHF, ΔEQ)**, y correlación ΔEQ(H) además de δ(H) (el DTQ del demo está
  muerto). Componentes nítidos simultáneos sin el límite de 5 de DIST.
- `wide_delta`: líneas sueltas en todo el rango de velocidad.
- **Cristal único exacto** (v4.19): suma coherente entre canales de
  radiación — la interferencia que SITE-1994 aproxima — y **kernel de
  distribución por diagonalización exacta** (v4.19), sin la truncación
  perturbativa (ni el patrón 3:3:1 fijo) del EXACT de DIST.

**Estadística e inferencia**

- Errores por **bootstrap** y por **perfil de verosimilitud**, además de la
  covarianza (NORMOS: solo 1·STD de covarianza).
- Pesos de Poisson correctos, pérdidas robustas, χ²/AIC/BIC para comparar
  modelos, y **multistart + escalado global automático por evolución
  diferencial** (la razón del 0/20 vs 8/20 en arranques difíciles).

**Software**

- GUI Qt moderna con sesiones reproducibles (JSON), editor de mínimos,
  presets físicos, informes; ajuste por lotes con warm-start; capa headless
  y CLIs para automatización; 8 idiomas; manuales ES/EN; suite de 337 tests
  y CI. NORMOS es un binario DOS de 1994 con JOB por stdin y 8.3.
- Calibración anclada al patrón publicado de α-Fe (SITE deriva de momentos
  nucleares: factor 0.99962 medido — diferencia de convención documentada).

## 4. Conclusión

Con NORMOS como verdad absoluta, **Fitbauer reproduce todo el dominio
compartido** — el núcleo discreto al nivel de 10⁻⁴–10⁻³ mm/s incluso en los
extremos de cada parámetro, el Hamiltoniano completo mejor que el propio
SITE, y las distribuciones (gaussianas, bimodales, cuadrupolares, Czjzek,
binomiales, correlacionadas) con momentos a ~10⁻² relativos. Lo que le faltaba
para "llegar a NORMOS" quedó reducido a cuatro capacidades concretas, de las
que **tres se cerraron en v4.19** (cristal único, fondo v³/v⁴ y orden mixto
en distribuciones, §18); queda la fuente polarizada (bajo demanda) y los
isótopos excluidos a propósito. En sentido contrario, Fitbauer
aporta un bloque entero de inferencia estadística, regularización moderna,
relajación cuantitativa y automatización que NORMOS nunca tuvo.
