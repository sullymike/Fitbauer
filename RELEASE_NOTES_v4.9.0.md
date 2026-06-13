## Fitbauer v4.9.0 — Detección híbrida CWT, early-stop multistart y biblioteca de espectros de referencia

Versión con **mejoras en el motor de ajuste**, **nueva detección automática de mínimos multi-escala** y una **biblioteca de 10 espectros sintéticos de referencia** para minerales de hierro comunes. Incluye soporte de espectros pre-doblados en CSV y el diálogo de ajuste global Néel-Arrhenius.

### Motor de ajuste (`core/fit_engine.py`)

- **Early-stop en multistart**: se detiene si el coste no mejora más de 1 ppm en 4 arranques consecutivos (`stagnation_patience=4`, `rel_tol=1e-6`), reduciendo tiempo de cómputo sin pérdida de calidad.

### Detección de mínimos (`gui/minima_analysis.py`)

- **CWT multi-escala con ondícula Ricker** (sustituye la convolución simple): detecta picos solapados en el rango físico Mössbauer (0.12–2.0 mm/s) con robustez frente a líneas anchas y sextetes.
- **Estrategia híbrida CWT + absorción directa**: la cresta CWT cubre líneas anchas/sextetes; el canal directo rescata dobletes estrechos que el CWT puede fusionar. Ambas listas se fusionan antes del filtrado final.
- **Corrección de desbordamiento CWT**: el kernel Ricker se clampea a `(n−1)//2` para que nunca supere el tamaño del signal (`np.convolve mode="same"` devuelve `max(M,N)`, no `M`).
- **Parámetros físicos ajustados** en `core/params.py`: `init_gamma_min` 0.08 → 0.10 mm/s (por encima del FWHM natural de Fe-57, ~0.097 mm/s), `min_separation` 0.12 → 0.15 mm/s.

### Nuevos datos (`data_sample/public/`)

- **10 espectros sintéticos** de referencia con ruido Poisson realista (5 × 10⁶ cuentas): goetita, ferridrita, pirita, troilita, wüstita, ilmenita, jarosita, lepidocrocita, maghemita y pirrotita. Cada uno acompañado de su plantilla JSON de ajuste.
- **Script generador** `_generar_publicos.py` para reproducir o modificar los datos (semilla fija 20260613).
- **Espectro experimental real** de α-Fe calibración del ESRF (`alphaFe_calibracion_ESRF.dat`).

### Soporte de formatos (`core/data_io.py`)

- **Espectros pre-doblados en CSV/velocidad**: archivos `.dat` con columnas `velocidad, cuentas` se cargan directamente sin folding (útil para datos del ESRF y otros sincrotrones).

### Nuevas funcionalidades GUI

- **Diálogo GlobalNeelFitDialog**: ajuste global Néel-Arrhenius sobre múltiples espectros a distintas temperaturas, con exportación de parámetros.
- **Centralización** de `INTENSITY_MODES` y `QUAD_TREATMENTS` en `core/params.py` — fuente única para GUI y CLI.

### Tests (`tests/`)

- **Golden tests ampliados** (`test_headless_golden.py`): casos jarosita y siderita añadidos a los existentes (alphaFe, hematita). Los 4 casos son deterministas (semilla 12345) y protegen la física de regresiones numéricas.
- **Invarianza de signo para ΔEQ en dobletes**: para un doblete puro sin BHF, `+ΔEQ` y `−ΔEQ` producen espectros idénticos; el test verifica `|s1_quad|` para evitar falsos negativos por diferencias de precisión numérica entre Python 3.11 y 3.12 / distintos BLAS.
- Correcciones en 3 tests sensibles al idioma (`test_qt_app.py`) y en el test de exportación TSV (`test_save_fit_writes_tsv`).

### Correcciones de bugs

- **ValueError en detección de mínimos** con espectros cortos (≤256 canales): el kernel Ricker podía superar el tamaño del signal, haciendo que `np.convolve(mode="same")` devolviera más elementos de los esperados.
