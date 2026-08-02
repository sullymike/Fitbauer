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
| `SRELAX`/`IRELAX` relajación | `BlumeTjon` | **=** reproduce `ISIRLX` a <10⁻¹² |
| `BSAT` (vía `SPN=BHF/BSAT`) | `relax_polarization` | **=** |
| `POLAR` + `D10 D20 D2N D2P` + `BHS THETAS PHIS` | kernel `"polarized"` | **=** |
| `NDEX FACTOR CONST` ligaduras | `constraints` | **+** NORMOS propaga mal el error del parámetro ligado (usa el offset en vez del factor) |
| `STB` Czjzek sobre el Hamiltoniano | Voigt σ_B / forma Gaussiana | **~** por otra vía, sin las correcciones de orden 3-5 |
| `EFGB` (Blaes: orientaciones de EFG + campo) | `kundig_powder`, kernel hamiltoniano | **~** el promedio existe, pero en el componente DISCRETO no se combina con η |
| `PHS`/`MIX` mezcla multipolar M1+E2 | — | **✗** irrelevante para ⁵⁷Fe (`MIX=0` cableado en el propio SITE) |
| `ISTYPE`/`SEX SG GFR QMR` otros isótopos | solo ⁵⁷Fe | **✗** |
| `EMSPEC` espectro de emisión | — | **✗** |
| `BEXT` campo externo en relajación de Ising | — | **✗** |

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
| `METHOD=2` Brand: dispersiones `H1P`/`ISP`/`QUP` | — | **✗** |
| `METHOD=8` distribución de desplazamiento isomérico P(δ) | — | **✗** |
| `DISTRI=1` histograma + suavizado | igual | **=** |
| `LAMDA` (matriz `λ·D₂ᵀD₂`) | `alpha` | **=** matriz idéntica elemento a elemento |
| `BETA1`/`BETA2` anclajes de borde | `edge_anchor` + diagnóstico `edge_pileup` | **=** |
| `DISTRI=2` gaussiana | VBF con N=1 | **=** |
| `DISTRI=3` binomial / fija | Binomial / Fija | **=** |
| `DISTRI=4` Czjzek / Le Caër analíticas | el histograma reproduce la forma | **~** sin forma paramétrica |
| `DTB DTI DTQ` correlaciones con la malla | `delta_slope quad_slope` | **=** |
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

1. **P(δ), distribución de desplazamiento isomérico** (`METHOD=8`). Es el hueco
   con más sentido experimental: vidrios metálicos, óxidos amorfos y fases mal
   cristalizadas donde lo que se distribuye es δ y no B. Hoy solo se puede
   aproximar con δ correlacionado al campo (`delta_slope`).
2. **Modelo de Brand** (`METHOD=2`): dispersiones adicionales de campo
   transversal (`H1P`), de isomérico (`ISP`) y de cuadrupolo (`QUP`) que
   ensanchan cada línea del kernel. Es la vía de NORMOS para distribuciones
   anchas sin malla; complementa al punto 1.
3. **Czjzek / Le Caër analíticas** (`DISTRI=4`). El histograma reproduce la
   forma (validado en la serie L2), pero no hay una forma paramétrica de 2-3
   parámetros que ajustar directamente.
4. **`BEXT`**, campo externo en la relajación de Ising: desplaza las líneas
   además de polarizar las poblaciones. La polarización ya está; el
   desplazamiento no.
5. **Espectros de emisión** (`EMSPEC`). Un cambio de signo en el modelo, pero
   sin exponer.
6. **Otros isótopos** (¹¹⁹Sn, ¹⁹⁷Au, ¹⁵¹Eu, ¹²¹Sb). Fitbauer es ⁵⁷Fe.
7. **Preprocesado**: `NADD` (rebin), `NDECKS` (sumar espectros), `MULT`/`ADD`.
8. **Mezcla multipolar M1+E2** (`PHS`/`MIX`). Sin efecto en ⁵⁷Fe.

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
