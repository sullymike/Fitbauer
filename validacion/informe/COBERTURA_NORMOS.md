# Cobertura de Fitbauer frente a NORMOS: inventario completo

**2026-08-02.** Cierre de la revisión del código fuente Fortran de NORMOS
(SITE + DIST, 1990) contra `core/`. A diferencia del banco de validación
—que compara RESULTADOS sobre espectros generados por el binario—, esto es un
inventario de CAPACIDADES: se extrajo la lista completa de parámetros e
interruptores de los namelist (`sitemdos.for`, `distmdos.for`) y se cruzó una
por una con lo que hace Fitbauer.

Veredicto por símbolo:

- **=** hace lo mismo (verificado)
- **+** hace lo mismo y es más exacto
- **~** lo cubre parcialmente o por otra vía
- **✗** no lo tiene

---

## 1. Modelo espectral (SITE)

| Capacidad de NORMOS | En Fitbauer | |
|---|---|---|
| `NLINE` 1/2/6 — singlete, doblete, sexteto | Singlete / Doblete / Sextete | **=** |
| `NLINE=8` — octete (ΔmI=±2) | sexteto + 2 singletes | **~** |
| `WID ARE ISO QUA BHF` | `gamma1 depth delta quad bhf` | **=** |
| `W13 W23 W73` anchuras por par | `gamma2 gamma3` (referencia en 1,6 y no en 3,4) | **=** |
| `A13 A23 A73`, `D21 W21` intensidades | `int1 int2` | **=** |
| `BKG(2..5)` fondo polinómico hasta v⁴ | `slope curv curv3 curv4` | **=** |
| `AKS` asimetría por interferencia | `line_asym` | **=** |
| `VOIGT` + `WDLOR` | perfil Voigt | **+** el suyo es pseudo-Voigt (David 1986) |
| `HAMILT` Hamiltoniano completo | `quad_treatment="hamiltonian"` | **+** LAPACK hermítico en doble precisión frente a EISPACK general en `REAL*4` |
| `ETA THE PHI` | `eta beta phi` | **=** |
| `IFSC` + `BEX GAX` cristal único | `quad_treatment="hamiltonian_sc"` | **=** |
| `IFGK` + `G11 G20 G21 G22` Goldanskii–Karyagin | `int1`/`int2` (pesos por canal q) | **=** su `B=√\|G\|` en la amplitud equivale a nuestro peso en la intensidad |
| `IFTRAN` integral de transmisión | `absorber_model="transmission"` | **+** kernel de fuente integrado por canal frente a su muestreo puntual |
| `FSO` fracción resonante de la fuente | `src_frac` | **=** |
| `TAB` espesor, `WDS` anchura de fuente | `depth` como τ, `src_fwhm` | **=** |
| `IRELAX` relajación de Ising | `BlumeTjon` | **=** contra el binario a ~10⁻⁵ (`sonda_relajacion*.py`), `OME` (MHz) = 2k |
| `SRELAX` relajación esférica | — | **✗** |
| `BSAT` (`BH0` en el demo; momento relativo BHF/BSAT) | `relax_polarization` + `relax_convention="normos"` | **=** a ~10⁻⁵ con el convenio NORMOS; el defecto es Blume con balance detallado, que difiere con P > 0 |
| `POLAR` + `D10 D20 D2N D2P` + `BHS THETAS PHIS` | kernel `"polarized"` | **=** |
| `NDEX FACTOR CONST` ligaduras | `constraints` | **+** NORMOS propaga mal el error del parámetro ligado (usa el offset en vez del factor) |
| `STB` Czjzek sobre el Hamiltoniano | Voigt σ_B / forma Gaussiana | **~** por otra vía, sin las correcciones de orden 3-5 |
| `EFGB` (Blaes: orientaciones de EFG + campo) | `kundig_powder`, kernel hamiltoniano | **~** el promedio existe, pero en el componente DISCRETO no se combina con η |
| `PHS`/`MIX` mezcla multipolar M1+E2 | — | **✗** irrelevante para ⁵⁷Fe (`MIX=0` cableado en el propio SITE) |
| `ISTYPE`/`SEX SG GFR QMR` otros isótopos | solo ⁵⁷Fe | **✗** |
| `EMSPEC` espectro de emisión | — | **✗** |
| `BEXT` campo externo en relajación de Ising | `relax_bext` (Blume–Tjon) | **=** los dos estados en BEXT ± BHF; validado contra la ecuación matricial de Blume (el demo no lo admite) |

## 2. Adquisición y plegado

| Capacidad de NORMOS | En Fitbauer | |
|---|---|---|
| `FOLD` + búsqueda del punto de doblado | sí, 2 ciclos | **+** interpolación cúbica; la suya trunca a canal entero |
| Efecto geométrico | `geometry_effect` (diagnóstico) | **=** |
| `TRIANG` triangular / senoidal | `drive_form` | **=** |
| Pesos `1/√Y` (Poisson sobre datos doblados) | idéntico | **=** |
| `NADD` sumar canales vecinos (rebin) | — | **✗** menor |
| `NDECKS` sumar varios espectros | — | **✗** menor |
| `MULT`/`ADD` escalado de cuentas | — | **✗** menor |

## 3. Ajuste y estadística

| Capacidad de NORMOS | En Fitbauer | |
|---|---|---|
| Minimizador `VA02A` | TRF con cotas + multistart + DE automática | **+** |
| Errores desde la covarianza, sin reescalar por χ² | idéntico (`absolute_sigma`) | **=** |
| χ² normalizado con DF = NP−1−NVAR | DF = NP−NVAR | **=** 0.4 % de diferencia |
| — | bootstrap, verosimilitud perfilada, AIC/BIC, L-curve | **+** extras sin equivalente |

## 4. Distribuciones (DIST)

| Capacidad de NORMOS | En Fitbauer | |
|---|---|---|
| `METHOD=1` distribución de campo | histograma Hesse–Rübartsch | **=** |
| `METHOD=3` Billard–Chamberod (vecinos) | forma Binomial | **=** |
| `METHOD=4` fuente polarizada | `kernel_treatment="polarized"` | **=** |
| `METHOD=5` P leída de fichero (spline) | forma "Fija" | **=** |
| `METHOD=6` distribución de cuadrupolo | `--variable quad` | **=** |
| `METHOD=7` P(ΔEQ) de fichero **con campo** | "Fija" (sin campo) | **~** |
| `METHOD=2` Brand: dispersiones `H1P`/`ISP`/`QUP` | `width_model="dispersion"` (σ_B, σ_δ, σ_Q) | **=** sin replicar su asimetría de línea, que su propio código marca como aproximación |
| `METHOD=8` distribución de desplazamiento isomérico P(δ) | `--variable delta` | **+** su kernel son singletes; aquí admite además sexteto o doblete |
| `DISTRI=1` histograma + suavizado | igual | **=** |
| `LAMDA` (matriz `λ·D₂ᵀD₂`) | `alpha` | **=** matriz idéntica elemento a elemento |
| `BETA1`/`BETA2` anclajes de borde | `edge_anchor` + diagnóstico `edge_pileup` | **=** |
| `DISTRI=2` gaussiana | VBF con N=1 | **=** |
| `DISTRI=3` binomial / fija | Binomial / Fija | **=** |
| `DISTRI=4` Czjzek analítica (`METHOD=6`) | formas «Czjzek» y «Czjzek ext.» | **=** misma P ∝ ΔEQ⁴·exp(−ΔEQ²/2σ²) con σ² = STG² + DTQ²; el `.JOB` se importa con esa forma (§9) |
| `DISTRI=4` con `METHOD=7` (Le Caër con campo) | forma «Le Caër» | **=** misma P (marginal de Vzz con signo de un EFG de Czjzek) y σ² = STG² + DTQ²; kernel de polvo exacto calculado, no leído de spline (§9) |
| `DTB DTI DTQ` correlaciones con la malla | `delta_slope quad_slope` | **=** ojo: en METHOD 1-5 NORMOS **solo** aplica `DTI`; `DTQ` es un parámetro muerto ahí (ver §7) |
| `.JOB` de DIST → panel de distribución | `job_to_distribution_state` | **=** malla, forma, correlaciones, anclajes y sitios cristalinos como nítidos |
| 2 bloques de distribución solapados | componentes nítidos + P(BHF,ΔEQ) 2D | **~** |
| — | regularización TV y máxima entropía, L-curve, 2D | **+** extras sin equivalente |

---

## 5. Dónde Fitbauer es medible­mente mejor

| | NORMOS | Fitbauer |
|---|---|---|
| Diagonalización del Hamiltoniano | EISPACK complejo **general** en `REAL*4`, con `MACHEP=2⁻⁴⁷` (épsilon de doble precisión) e `IERR` nunca comprobado | LAPACK hermítico en doble; energías exactas a 1.8·10⁻¹⁵ |
| Kernel de la fuente (transmisión) | muestreo puntual de la Lorentziana | integrado por canal; rms del modelo 2.8·10⁻³ → 1.5·10⁻⁴ |
| Perfil Voigt | pseudo-Voigt aproximado | Voigt exacto (`wofz`) |
| Doblado subcanal | trunca a canal entero (desalinea ≤½ canal) | interpolación cúbica |
| Error de parámetros ligados | **bug**: usa el offset en vez del factor → cero con ligadura multiplicativa | propagación correcta |
| Diagnóstico de malla insuficiente | — | `edge_pileup` |

## 6. Lo que falta, por relevancia práctica en ⁵⁷Fe

Los dos huecos con sentido experimental —P(δ) y el modelo de Brand— quedaron
CERRADOS el 2026-08-02; ver §8. El Czjzek analítico de `METHOD=6` se cerró el
2026-10-14 (v5.2.1–5.2.2); ver §9. Lo que queda está desarrollado en
**`PENDIENTE_NORMOS.md`**, con la referencia exacta del fuente, qué tocar en
Fitbauer, cómo validarlo y si merece la pena. Resumen:

1. ~~**`DISTRI=4` con `METHOD=7`** (Le Caër con campo)~~ — **cerrado el
   2026-10-15**: forma «Le Caër» (§9).
2. ~~**`BEXT`**, campo externo en la relajación de Ising~~ — **cerrado el
   2026-10-15**: `relax_bext` en el componente Blume–Tjon.
3. **Espectros de emisión** (`EMSPEC`). Un cambio de signo en el modelo, pero
   sin exponer.
4. **Otros isótopos** (¹¹⁹Sn, ¹⁹⁷Au, ¹⁵¹Eu, ¹²¹Sb). Fitbauer es ⁵⁷Fe.
5. **Preprocesado**: `NADD` (rebin), `NDECKS` (sumar espectros), `MULT`/`ADD`.
6. **Mezcla multipolar M1+E2** (`PHS`/`MIX`). Sin efecto en ⁵⁷Fe.

## 7. Diferencias de convenio que hay que conocer

Ninguna es un error; todas están cubiertas por un parámetro o documentadas.

- **Posiciones del sexteto**: SITE las deriva de los momentos nucleares;
  Fitbauer usa el patrón publicado de α-Fe. No difieren en una simple escala.
  Seleccionable con `sextet_pattern("normos")`.
- **Intensidades**: `D13`/`D23` son razones de ÁREA; `int1`/`int2` de
  PROFUNDIDAD. Coinciden si las anchuras son iguales. Seleccionable con
  `intensity_convention("area")`.
- **Anchuras**: `WID` es la de las líneas 3,4 y `W13`/`W23` son relativas a
  ella; `gamma1` es la de las líneas 1,6.
- **Relajación**: `k = OME/2`, y NORMOS reparte la anchura entre `WD`
  (autovalores) y `WDS` (convolución) mientras aquí hay una sola.
- **χ²**: NORMOS divide por los datos con DF = NP−1−NVAR.
- **Punto de doblado**: `PFP` del `&DATA` es solo la SEMILLA de la búsqueda, no
  el punto final; NORMOS la refina en dos ciclos. Y el punto continuo que
  imprime en el `.RES` tampoco es donde dobla: la rutina final
  (`normospr.for:601-604`) lo TRUNCA y suma canales enteros, con el eje en
  `⌊PFP⌋ + 0.5` (`core.normos_job.punto_de_doblado_normos`). Fitbauer sí
  interpola, así que su centro no tiene por qué coincidir.
- **Malla de DIST**: los subespectros son `x_k = X + (k−1)·DTX`, `k = 1..NSB`,
  con `X`/`DTX` = `BHF`/`DTB`, `QUA`/`DTQ` o `ISO`/`DTI` según el `METHOD`.
  El origen y el paso son PARÁMETROS AJUSTABLES (`BHFFIT`, `DTBFIT`…), así que
  la malla del `.RES` no tiene por qué ser la del `.JOB`.
- **`DTQ` en distribuciones de campo**: los bucles de `distcalf.for` para
  METHOD 1-5 calculan `RH = BHF+PP*DTB` y `RI = ISO+PP*DTI` y **no tocan ΔEQ**.
  Un `DTQ` escrito en un `.JOB` de campo no hace nada; solo entra en METHOD 6/7,
  donde la malla ya es de cuadrupolo. Trasladarlo metía una correlación
  inexistente (con `DTQ=0.03` y 40 puntos, un ΔEQ moviéndose > 1 mm/s).
- **`λ` frente a `alpha`**: la `LAMDA` de NORMOS es absoluta y multiplica
  `D₂ᵀD₂` sobre cuentas sin normalizar; el `alpha` de Fitbauer es adimensional
  y va normalizado por `λ_ref`. **No son trasladables 1:1** — hay que fijar
  `alpha` con la L-curve. La RAZÓN `BETA/LAMDA` sí se conserva y es el
  `edge_anchor`.
- **`DEX` frente a `ARX`**: el binario de 1994 renombró `ARX`→`DEX` igual que
  `ARE`→`DEP` en SITE; sigue siendo el ÁREA resonante en mm/s.
- **Namelist de DIST**: no acepta `NLINE`, `DEP`, `W13`, `W23`, `AKS`,
  `IFTRAN`… Si vienen copiadas de un `.JOB` de SITE, **NORMOS las lee y las
  tira sin avisar**: ese subespectro nunca entró en el ajuste. El importador de
  Fitbauer sí lo dice.

---

## 8. Cierre de los dos huecos con sentido experimental (2026-08-02)

### P(δ) — distribución de desplazamiento isomérico

**El motor ya sabía hacerlo**: `build_kernel` aceptaba `variable="delta"` desde
antes. Lo que faltaba era exponerlo — el CLI lo bloqueaba con
`choices=["bhf","quad"]` — y que constara en ninguna parte. Verificado de punta
a punta sobre un P(δ) bimodal sintético de singletes (el caso exacto de
`METHOD=8`): ⟨δ⟩ = 0.468 frente a 0.470 y σ = 0.372 frente a 0.369, separando
las dos poblaciones (0.15 y 0.85 mm/s).

Ahora `--variable delta`, con rango por defecto −1…2 mm/s y etiquetas propias.
Va **más allá** de NORMOS: su `METHOD=8` distribuye solo singletes, mientras
que aquí el kernel puede ser singlete, doblete o sexteto (δ distribuido con
campo fijo).

### Modelo de Brand — anchuras desde dispersiones físicas

Nuevo `width_model="dispersion"`: en vez de dejar libres `gamma2`/`gamma3`, la
anchura de cada línea sale de cuánto la desplaza cada variable dispersa,

    (Γ_i/2)² = (Γ/2)² + (∂v_i/∂B · σ_B)² + σ_δ² + (∂v_i/∂ΔE_Q · σ_Q)²

que es la suma en cuadratura de NORMOS. Reproduce la firma del desorden
químico: con σ_B = 1 T las líneas 1 y 6 pasan a 0.408 mm/s y las 3 y 4 se
quedan en 0.255, mientras que σ_δ ensancha todas por igual.

Detalle que importa: el ensanchamiento **conserva el área** de cada línea (una
dispersión reparte los mismos átomos), así que el peso de pico baja en
proporción. Sin eso el área crecía un 40 % con σ_B = 1 T.

No se replica la **asimetría** de línea de Brand. Su propio código advierte de
que la expresión «solo vale si los términos asimétricos son mucho menores que
la anchura, y si no, usar la expresión completa (`METHOD=3`)»; para ese régimen
Fitbauer tiene el histograma completo, que no aproxima nada.

## 9. Czjzek analítico (`DISTRI=4`, `METHOD=6`) — 2026-10-14

**Formas nuevas (v5.2.1).** «Czjzek» (Czjzek et al. 1981): ΔEQ/σ sigue una χ
de 5 grados de libertad, P ∝ ΔEQ⁴·exp(−ΔEQ²/2σ²). «Czjzek ext.» (Le Caër y
Brand 1998): desorden aleatorio sobre un entorno ordenado de norma ΔEQ₀, χ no
central de 5 grados de libertad. Solo en P(ΔEQ) con dobletes; se ajustan σ (y
ΔEQ₀), con error por la jacobiana, y desde v5.2.2 se pueden fijar.

**Equivalencia con NORMOS (v5.2.2).** Sonda del binario `DIST.EXE`
(09.09.1993) con `DISTRI=4` y `METHOD=6` (`validacion/_staging/czjzek`): los
pesos de su malla siguen la misma P con exponente 4.000 y residuos al nivel del
redondeo de su tabla, con

    σ² = STG² + DTQ²

es decir, NORMOS ensancha su STG con el paso de la malla. Comprobado al 1e-5
con DTQ de 0.06 a 0.36 mm/s; no depende de QUA ni de WID. El importador
traduce esos `.JOB` a la forma «Czjzek» con ese σ (fijo si `STGFIT=.FALSE.`)
y un aviso con el σ equivalente. Test: `tests/test_normos_job.py`, con la tabla
de pesos de NORMOS (STG 0.6, DTQ 0.18) incrustada.

**Malla en los nodos de NORMOS (v5.2.2).** NORMOS calcula los subespectros en
QUA + k·DTQ; Fitbauer, en los centros de los bins. El importador pasaba ese
rango como bordes, con lo que los nodos quedaban desplazados medio paso y con
un paso (NSB−1)/NSB del de NORMOS. Ahora los bordes van medio paso por fuera y
los centros caen exactamente en los nodos. Afecta a todos los `.JOB` de DIST
importados; el banco J/L ajusta con el CLI y su malla propia, así que sus
cifras no cambian.

**Le Caër con campo (2026-10-15).** `DISTRI=4` con `METHOD=7` también tiene su
forma. En el fuente (`distcalf.for`) cada subespectro es un espectro de polvo de
Blaes (EFG aleatorio respecto al campo, solución exacta) leído de un fichero
spline e indexado por QUA = e²qQ/2 con signo, y los pesos son

    P(q) = ½√(2/π)·[(3q²−2)e^(−q²/2) + (2 − 8q²/3)e^(−2q²/3)],  q = QUA/σ

con la misma σ = √(STG² + DTQ²). Por Monte Carlo sobre tensores de Czjzek es la
marginal de Vzz con signo (σ = √(2/3) veces la desviación de las componentes; la
diferencia con el histograma, 0.006 en el pico de 0.31, es ruido). Fitbauer calcula
los subespectros con el «Hamiltoniano (polvo)» (su `deq` es e²qQ/2) en lugar de leer
el spline. **No se ha sondado contra el binario**: el demo necesita el fichero spline
de subespectros, que no tenemos. Si el `.JOB` no trae `BHF` (el campo va en el
spline), se pone 33 T y se avisa.
