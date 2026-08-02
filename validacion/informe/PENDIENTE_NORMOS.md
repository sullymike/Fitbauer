# Pendiente frente a NORMOS — hoja de ruta

**Estado a 2026-08-02.** Complemento de `COBERTURA_NORMOS.md`, que dice QUÉ
falta; este documento dice CÓMO hacerlo. Cada ficha lleva la referencia exacta
del fuente, qué tocar en Fitbauer, cómo validarlo y una estimación honesta de
si merece la pena.

Nada de lo que queda tiene demanda experimental clara para ⁵⁷Fe. Están
ordenados por valor descendente según mi criterio; el ítem 1 es el único que
recomendaría de entrada.

---

## Antes de empezar: cosas que ahorran horas

Trampas ya pagadas en esta revisión. Merece la pena leerlas antes de tocar nada.

- **El fuente está en `normos/`**, doblemente gitignored (propietario, nunca
  al repo). Fechado 1990; el binario demo es de 1993/94 y **difiere en varios
  puntos** — siempre verificar contra el binario, no solo leer el Fortran.
- **DOSBox es un snap y NO ve `/tmp`.** El staging tiene que estar bajo `$HOME`
  (usa `normos_lib.STAGING_ROOT`). Si el `.PLT` no aparece, mira el log: dirá
  `MOUNT: Path ... not found`.
- **`IFTRAN`, `HAMILT`, `SRELAX` van en `&PARAM`, no en `&DATA`.** Ponerlos en
  `&DATA` da `ERROR OR EOF IN NAMELIST` sin más pista.
- Las líneas del namelist no pueden pasar de **72 columnas**.
- El demo tiene límites: `NSUB ≤ 10`, 512 canales, sin isótopos.
- **Sondar antes de implementar.** Varios interruptores están inertes en el
  demo (`STI`, `DEPSUB`, `IFGK`, `S2T`, `VOIGT/WDLOR`); otros que parecían
  inertes resultaron operativos (`AKS`, `FSO`). El patrón que funciona es:
  generar 4-5 casos que difieran en un solo parámetro y comparar los `.PLT`.
  Plantillas listas: `validacion/generador/paso0_sondas.py`.
- **Para comparar formas de línea, cuidado con las anchuras.** NORMOS usa dos
  (`WD` en los autovalores, `WDS` en la convolución) donde Fitbauer usa una.
  Contarlas ambas mete un ~2 % de residuo que no es del modelo. Esto ya me
  costó una conclusión equivocada en la relajación.
- El banco entero tiene el punto de doblado en **256.5** (semientero), así que
  nada que dependa de la interpolación subcanal se ve en él.

---

## 1. Czjzek / Le Caër analíticas (`DISTRI=4`)

**Qué es.** Formas paramétricas para la distribución de gradiente de campo
eléctrico en sólidos desordenados. Czjzek con `METHOD=6` (cuadrupolo sin
campo), Le Caër con `METHOD=7`. Se ajustan con 2-3 parámetros en vez de un
histograma de 40-60 bins.

**En NORMOS.** `distinif.for` (construcción de la malla de probabilidades) y
`distcalf.for:104` y `:167`. La rutina `CZJZEK` de `sitegmfp.for:1153` es otra
cosa: son las correcciones de orden 3-5 sobre las líneas del Hamiltoniano.

**Hoy en Fitbauer.** El histograma reproduce la forma sin necesitarla
analítica — validado en la serie L2 del banco, con ⟨x⟩ a 0.004 y σ a 0.015.
Lo que no hay es la forma paramétrica.

**Qué habría que hacer.**
- Una función `czjzek_distribution(grid, sigma, mu)` en `mossbauer_distribution`
  al lado de las otras formas paramétricas.
- Registrarla en `DISTRIBUTION_SHAPES` (`core/params.py`) y en el selector del
  panel (`gui/distribution_panel.py`), más el CLI (`--shape czjzek`).
- El ajuste va por el mismo camino que Binomial/Gaussiana (formas paramétricas,
  sin `alpha`).

**Validación.** Sí es posible: el demo soporta `DISTRI=4` con `METHOD=6`
(confirmado en el inventario). Serie de banco nueva al estilo de `serie_L.py`.

**Coste / valor.** Medio / medio. Solo lo haría si trabajas con vidrios
metálicos o materiales amorfos y quieres publicar 2-3 parámetros en vez de una
curva. Si no, el histograma ya te da la forma.

---

## 2. `BEXT` — campo externo en la relajación de Ising

**Qué es.** Un campo externo aplicado desplaza las líneas además de polarizar
las poblaciones. En `ISIRLX`, `VL0 = AL(j)·BEXT` entra en la parte imaginaria
de los autovalores.

**En NORMOS.** `siterelx.for:68` (`VL0 = AL(J)*BEXT`) y su uso en `XP/YP/XN/YN`
y en `BB`/`CC`.

**Hoy en Fitbauer.** La polarización de poblaciones ya está
(`relax_polarization`); el desplazamiento no. El port de `ISIRLX` que hay en
`tests/test_relajacion_normos.py::_isirlx` **ya acepta `vl0`**, así que la
referencia para validar está escrita.

**Qué habría que hacer.**
- Añadir `vl0` a `_blume_polarizado` en `core/physics.py` (la fórmula ya está
  portada, solo hay que dejar de fijarlo a 0).
- Parámetro de componente `relax_bext` en `core/params.py` (registro, bounds,
  `USED_BY["BlumeTjon"]`) y en los `extras` de `core/fit_engine.py:258`.

**Validación.** **No** con el binario del demo: `BSAT` no está en su namelist y
sus espectros `IRELAX` salen casi colapsados incluso con `OME=0` (§19 del
informe). Se valida contra el port de `ISIRLX`, como se hizo con la
polarización.

**Coste / valor.** Bajo / bajo. Media hora, pero solo sirve si mides con imán.

---

## 3. Espectros de emisión (`EMSPEC`)

**Qué es.** Fuente Mössbauer como muestra (MES): el espectro sale invertido.

**En NORMOS.** Un solo signo: `SGN = +1.0` en vez de `−1.0`
(`sitecalf.for:131`), aplicado en `YC = BKG1·(BK + SGN·YC)`.

**Hoy en Fitbauer.** `total_model` siempre resta la absorción.

**Qué habría que hacer.** Un flag de modelo `emission: bool` en `FitState` /
`ModelState` que cambie el signo en `core/physics.total_model`. Trivial en el
motor; el trabajo está en exponerlo (GUI + i18n en 8 idiomas + manual).

**Coste / valor.** Bajo en core, medio con GUI / bajo salvo que hagas MES.

---

## 4. Otros isótopos (¹¹⁹Sn, ¹⁹⁷Au, ¹⁵¹Eu, ¹²¹Sb)

**Qué es.** NORMOS parametriza el isótopo con `ISTYPE` y deriva de ahí
`WIDNAT`, `GFR`, `QMR`, `SEX`, `SG`, `GFACT`, `EGAMMA`, `PARITY`.

**En NORMOS.** `sitecalf.for:161-245`, la cadena de `IF(INDEX(ISTYPE,...))`.
Todos los valores están ahí, tabulados y listos para copiar.

**Hoy en Fitbauer.** Solo ⁵⁷Fe. El patrón del sexteto ya es seleccionable
(`SEXTET_PATTERNS`), que es la mitad del camino.

**Qué habría que hacer.** Bastante: `core/constants.py` tendría que pasar de
constantes de ⁵⁷Fe a un registro por isótopo, y `core/hamiltonian.py` está
escrito para I=3/2→1/2 (matrices 4×4 fijas). Para Eu/Sb (I=5/2→7/2) habría que
generalizar las matrices de espín — NORMOS ya lo hace con `SPNP`
(`sitegmfp.for:245`), que construye las matrices para cualquier espín.

**Coste / valor.** Alto / bajo, salvo que el laboratorio cambie de isótopo. Es
la decisión de si Fitbauer sigue siendo un programa de ⁵⁷Fe.

---

## 5. Preprocesado de datos

**Qué es.** Tres utilidades de adquisición que NORMOS hace al leer:
- `NADD` — sumar canales vecinos (rebin) para mejorar la estadística.
- `NDECKS` — sumar varios espectros del mismo fichero.
- `MULT`/`ADD` — escalar y desplazar las cuentas.

**En NORMOS.** `normospr.for:1084-1108` (`NADD`, con el reajuste de `ND`, `PFP`
y `DELV`) y `:1035-1056` (`NDECKS`, `MULT`, `ADD`).

**Qué habría que hacer.** Funciones puras en `core/folding.py` y un paso previo
en `HeadlessSession.load_ws5`. Ojo con `NADD`: hay que reescalar el centro de
doblado y el paso de velocidad, que es donde NORMOS se complica.

**Coste / valor.** Bajo / bajo. Se resuelve fuera con cuatro líneas de numpy.

---

## 6. Mezcla multipolar M1+E2 (`PHS`/`MIX`)

**En NORMOS.** `sitegmfp.for`, las ramas con `AS1 = |AMIX|·exp(i·PHASE)` y los
coeficientes `CL1` (Clebsch–Gordan de multipolaridad L+1).

**Por qué no.** Para ⁵⁷Fe la transición es M1 pura y el propio SITE lleva
`MIX = 0.0` cableado (`sitecalf.for:165`). Solo tiene sentido junto con el
ítem 4.

**Coste / valor.** Medio / nulo en ⁵⁷Fe.

---

## Parciales: cubierto por otra vía, mejorable

No son huecos, pero constan como **~** en `COBERTURA_NORMOS.md`.

| | Situación | Qué faltaría |
|---|---|---|
| **Octete** (`NLINE=8`) | se modela como sexteto + 2 singletes, validado en la serie K1 | una componente de 8 líneas propia, con las ΔmI=±2 ligadas al mismo BHF |
| **`STB`** (Czjzek sobre el Hamiltoniano) | se cubre con Voigt σ_B / forma Gaussiana | las correcciones de orden 3-5 de `CZJZEK` (`sitegmfp.for:1153`), que corrigen posición e intensidad además de la anchura |
| **`EFGB`** (Blaes) | el promedio de orientaciones existe en `kundig_powder` y en el kernel hamiltoniano | en el componente DISCRETO, combinar el promedio de orientaciones con η ≠ 0 |
| **`METHOD=7`** | la forma "Fija" carga P de fichero | que además admita campo magnético |
| **2 bloques de distribución** | componentes nítidos + P(BHF,ΔEQ) 2D | dos distribuciones independientes solapadas, cada una con su malla |

De estos, el más defendible es el **octete propio**: hoy funciona pero obliga a
declarar tres componentes y a ligarlas a mano.

---

## Cómo retomar

1. Leer `COBERTURA_NORMOS.md` (qué hay y qué falta) y este documento (cómo).
2. El banco de validación se regenera con `validacion/generador/`; las series
   nuevas siguen el patrón de `series_M.py` (asimetría) y `series_N.py` (FSO),
   que son las dos más recientes y las más limpias.
3. Sondear el binario ANTES de implementar, con `paso0_sondas.py` como
   plantilla.
4. Los tests de la revisión están en `tests/test_*_normos.py` y varios llevan
   un **port literal** de la rutina Fortran como referencia
   (`_isirlx`, `_smooth_normos`, `_energias_referencia`): reutilizarlos.
