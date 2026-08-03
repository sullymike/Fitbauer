<p align="center">
  <img src="assets/fitbauer_icon.png" alt="Fitbauer" width="140">
</p>

<h1 align="center">Fitbauer</h1>

<p align="center"><b>Software for Mössbauer spectrum fitting and analysis.</b></p>

<p align="center">
  <a href="README.md">🇬🇧 English version (main README)</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/versi%C3%B3n-5.0.0-0e7490" alt="versión 5.0.0">
  <img src="https://img.shields.io/badge/validado%20frente%20a-NORMOS-2563eb" alt="validado frente a NORMOS">
  <img src="https://img.shields.io/badge/tests-546%20en%20verde-16a34a" alt="546 tests en verde">
  <img src="https://img.shields.io/badge/licencia-Apache%202.0-64748b" alt="Apache 2.0">
</p>

Programa de escritorio estable para cargar, doblar, simular y ajustar espectros Mössbauer de Fe-57.

Versión estable actual: **v5.0.0**  
Arranque: `python fitbauer.py`  
Ajuste por línea de comandos (headless): `mossbauer_fit_cli.py` (discreto) · `fit_bhf_distribution_cli.py` (distribuciones)

**Autores:** Jorge Sánchez Marcos · Nieves Menéndez González  
Departamento de Química Física · UAM

---

## Fitbauer y NORMOS

NORMOS (R. A. Brand, 1990-1994) es el programa con el que se ha analizado buena
parte de la bibliografía Mössbauer publicada. Corre bajo DOS, es propietario y
ya no se mantiene. Fitbauer nace para poder **seguir trabajando con esos
análisis** —y con esos ficheros— desde un programa actual, abierto y
multiplataforma.

Eso obliga a dos cosas: dar los mismos números que NORMOS, y hablar su formato.
Las dos se han verificado contra el programa original.

### Validado contra NORMOS, con números

La física de Fitbauer se ha contrastado en dos bancos independientes.

**1. Banco sintético.** NORMOS genera un espectro a partir de parámetros
conocidos, Fitbauer lo ajusta y se compara con la verdad.

| | espectros | ajustes | comparaciones |
|---|---|---|---|
| Round-trip NORMOS → Fitbauer | 411 | ~1.150 | 6.497 |

Desviación mediana respecto al valor verdadero:

| Bloque | posición | BHF | anchura |
|---|---|---|---|
| Sexteto/doblete de primer orden | 2·10⁻⁷ mm/s | 4·10⁻⁵ T | 8·10⁻⁷ mm/s |
| Hamiltoniano completo | 6·10⁻⁵ mm/s | 8·10⁻⁴ T | 5·10⁻⁴ mm/s |
| Textura e intensidades | 2·10⁻⁷ mm/s | 2·10⁻³ T | 2·10⁻⁵ mm/s |
| Multisitio y ligaduras (hasta 10 sitios) | 2·10⁻⁴ mm/s | 2·10⁻⁴ T | 2·10⁻⁴ mm/s |

En el núcleo de primer orden la coincidencia es **exacta** dentro de la
precisión numérica. La cola que queda en el Hamiltoniano es la aproximación del
propio NORMOS de 1994, no de Fitbauer.

**2. Banco de trabajos reales.** 564 ajustes hechos en NORMOS a lo largo de años
—no sintéticos: medidas de laboratorio, con sus modelos y sus resultados—
recargados en Fitbauer y reproducidos.

- En **355 de 503** trabajos comparables (**71 %**) Fitbauer iguala o mejora el
  χ² reducido de NORMOS.
- χ² reducido mediano: NORMOS **2,433** · Fitbauer **2,089**.
- Acuerdo en los parámetros, sobre los trabajos que reproducen:

  | δ | ΔEQ | BHF | Γ | área |
  |---|---|---|---|---|
  | 0,0011 mm/s | 0,0019 mm/s | 0,017 T | 0,030 mm/s | 0,0036 |

De los que no reproducen, en **22 casos NORMOS había convergido a algo no
físico** —anchuras por debajo de la natural, áreas negativas— que Fitbauer no
puede replicar porque tiene cotas físicas.

Los informes completos, con el detalle trabajo a trabajo, están en
[`validacion/informe/`](validacion/informe/).

### Abre y escribe ficheros `.JOB`

**Archivo ▸ NORMOS (.JOB)**

- **Importar** un trabajo de NORMOS reconstruye el modelo **y carga su
  espectro**: el `.JOB` nombra sus ficheros en la cabecera, y Fitbauer los busca
  junto a él. Funcionan tanto los trabajos de **NORMOS-SITE** (sitios discretos)
  como los de **NORMOS-DIST** (distribuciones), que se detectan solos y abren el
  panel P(BHF)/P(ΔEQ).
- **Exportar** escribe el modelo actual en formato NORMOS. Se ha comprobado que
  **NORMOS acepta el fichero que produce Fitbauer** y reproduce la teoría
  original con diferencia exactamente cero.
- Las conversiones de convenio delicadas —anchuras `WID`/`W13` frente a Γ₁,
  razones de área `D13`/`D23` frente a razones de profundidad, la numeración
  global de las ligaduras `NDEX`— se hacen solas, y el importador **avisa de
  todo lo que no ha podido trasladar**.

Fitbauer **no ejecuta NORMOS ni lo distribuye**: solo habla su formato de texto,
que no es propietario.

### Lo que Fitbauer hace y NORMOS no

| | NORMOS | Fitbauer |
|---|---|---|
| **Distribuciones 2D** | — | P(BHF,ΔEQ), P(IS,ΔEQ), P(BHF,IS) |
| **Regularizadores** | Tikhonov y máxima entropía | además **variación total** (preserva bordes) |
| **Elección de α** | a mano | L-curve y criterio GCV, con tabla exportable |
| **P(IS)** | núcleo de singletes | núcleo de singlete, doblete o sexteto |
| **Formas de distribución** | histograma, gaussiana, binomial | además VBF multigaussiano (Rancourt–Ping) |
| **Errores** | matriz de covarianza | además bootstrap Monte Carlo e intervalos asimétricos por verosimilitud perfilada |
| **Búsqueda del mínimo** | un arranque | multiarranque y escalado global (evolución diferencial) automático |
| **Series de espectros** | un fichero cada vez | **ajuste secuencial en serie** con arranque en caliente |
| **Superparamagnetismo** | — | Néel–Arrhenius con distribución lognormal de tamaños y **ajuste global multitemperatura** |
| **Perfil Voigt** | pseudo-Voigt aproximado | Voigt exacto |
| **Diagnóstico** | χ² | además residuos (lag-1, rachas, antisimetría), correlaciones y aviso de malla insuficiente |
| **Salidas** | texto | informes Markdown/PDF, TSV con subespectros y sesión JSON completa |
| **Uso sin interfaz** | — | CLI para ajuste discreto y de distribuciones |
| **Plataforma** | DOS | Windows, macOS y Linux |
| **Idiomas** | inglés | 8 idiomas, con ayuda integrada |
| **Licencia** | propietario | Apache 2.0, código abierto |

Además, en varios puntos el cálculo es medibleme­nte más preciso: diagonalización
del Hamiltoniano en doble precisión (LAPACK hermítico frente a EISPACK general
en `REAL*4`), kernel de la fuente integrado por canal en vez de muestreado, e
interpolación cúbica al doblar en vez de truncar a canal entero.

### Lo que todavía no hace

Con la misma franqueza. Nada de esto impide el uso habitual en ⁵⁷Fe, pero
conviene saberlo:

- **Solo ⁵⁷Fe.** NORMOS admite además ¹¹⁹Sn, ¹⁹⁷Au, ¹⁵¹Eu y ¹²¹Sb.
- **Distribuciones de Czjzek / Le Caër analíticas.** El histograma reproduce su
  forma, pero no hay una función paramétrica de 2-3 parámetros que ajustar.
- **Campo externo en la relajación de Ising** (`BEXT`): la polarización de
  poblaciones sí está; el desplazamiento de líneas que provoca, no.
- **Espectros de emisión** (fuente en la muestra).
- **Dos bloques de distribución solapados**, cada uno con su malla. Fitbauer
  maneja uno, más componentes nítidos.
- **Octete** (ΔmI = ±2): se modela como sexteto más dos singletes, no como una
  componente propia.
- **Preprocesado**: agrupar canales, sumar varios espectros o reescalar cuentas.
- Al importar un `.JOB` de distribución, el **parámetro de suavizado `LAMDA` no
  se traslada**: el de NORMOS es absoluto y el de Fitbauer adimensional, así que
  hay que fijarlo con la L-curve.

El inventario completo, capacidad por capacidad y con la referencia exacta del
código de NORMOS, está en
[`validacion/informe/COBERTURA_NORMOS.md`](validacion/informe/COBERTURA_NORMOS.md);
lo pendiente, con qué habría que tocar y cómo validarlo, en
[`PENDIENTE_NORMOS.md`](validacion/informe/PENDIENTE_NORMOS.md).

---

## Funciones principales

- Carga local de `.ws5` y `.adt`; descarga de espectros y calibraciones desde la web del laboratorio.
- Doblado del espectro con folding point fraccionario e interpolación cúbica.
- **Ajuste cristalino** — singletes, dobletes y sextetes; perfiles Lorentziano/Voigt; verosimilitud Poisson o Gauss; pérdida robusta; χ²/AIC/BIC.
- **Arranques múltiples** configurables y errores bootstrap Monte Carlo.
- **Intervalos de confianza por verosimilitud perfilada** con escaneo adaptativo.
- **Ajuste de distribuciones** — `P(BHF)`, `P(ΔEQ)`, `P(IS)` y tres modos 2D; regularización Hesse-Rübartsch; L-curve; componentes nítidos simultáneos.
- Cuadrupolo avanzado: primer orden, Kündig fijo, Kündig polvo; textura de intensidades de sextete.
- Presets físicos de restricciones (3:2:1 polvo, anchuras ligadas, δ/Γ atados entre componentes).
- Modelos de relajación: fenomenológico, Blume–Tjon dos estados, Néel–Arrhenius con distribución lognormal de tamaños.
- Límites de parámetros configurables desde la GUI (Vista → Límites de parámetros…).
- Figura Matplotlib interactiva con editor semi-manual de mínimos.
- Ajuste en serie (batch) con warm-start.
- Exportación del ajuste como TSV con **subespectros por componente** y cabecera informativa.
- Informes Markdown/PDF: informe completo e informe reducido.
- Guardado/carga de sesión JSON completa; ajustes persistentes entre arranques.
- Comprobación de actualizaciones y descarga desde GitHub Releases.
- Interfaz y ayuda integrada en **inglés**, español, francés, alemán, portugués, ruso, japonés y chino.

---

## Capturas del programa

### Pantalla principal

<img src="docs/img/captura-pantalla-principal.png" alt="Pantalla principal de Fitbauer" width="900">

### Ajuste discreto

<img src="docs/img/captura-ajuste-discreto.png" alt="Ajuste discreto con dos dobletes, áreas y residuos" width="900">

### Distribución P(BHF)

<img src="docs/img/captura-distribucion-bhf.png" alt="Distribución de campo hiperfino P(BHF) con componentes nítidos" width="900">

### L-curve de regularización

<img src="docs/img/captura-lcurve.png" alt="L-curve para elegir el parámetro de regularización α" width="900">

### Informe Markdown/PDF

<img src="docs/img/captura-informe-markdown-pdf.png" alt="Informe PDF condensado con parámetros y figura" width="900">

---

## Arranque rápido

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python fitbauer.py
```

Prueba los datos de ejemplo:

1. **Archivo → Cargar…** → `data_sample/magnetita_Fe3O4.adt`
2. **Archivo → Cargar sesión…** → `data_sample/Fe3O4_session.json`

Flujo rápido:

```
Cargar espectro → revisar folding/Vmax → elegir modelo → ajustar
  → revisar residuos/áreas → exportar sesión/informe
```

---

## Instalación

Consulta [`INSTALL.md`](INSTALL.md) para instrucciones completas.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python fitbauer.py
```

Construir ejecutable con PyInstaller:

```bash
pyinstaller Fitbauer.spec    # → dist/Fitbauer/
```

---

## Historial de cambios

Consulta [`CHANGELOG.md`](CHANGELOG.md).
