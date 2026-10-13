# Arquitectura interna de Fitbauer

Fitbauer separa el cálculo Mössbauer de la interfaz gráfica. La regla práctica es:

```text
core/  → física, ajuste, reconstrucción, validación y vistas de resultado
 gui/  → widgets, menús, sesiones, render y orquestación de usuario
CLIs   → clientes headless de core/
```

## Capas principales

### `core/`

Código puro, sin Qt/Tk:

- `physics.py`: formas de línea y absorción de componentes.
- `fit_engine.py`: ajuste discreto y bootstrap.
- `mossbauer_distribution.py` (en la raíz, sin Qt): distribuciones `P(BHF)`, `P(ΔEQ)`, `P(IS)` y 2D — histograma regularizado, gaussiana, VBF, binomial y fija.
- `session.py`: `ModelState` y sesión headless.
- `reconstruction.py`: reconstrucción de modelos, residuos, subespectros, áreas y curvas de distribución.
- `validation.py`: validación estructural y de límites de parámetros.
- `result_views.py`: API de lectura de resultados para informes y paneles.
- `params.py`: registro canónico de parámetros, defaults y límites.
- `param_overrides.py`: límites de parámetros editados por el usuario (diálogo «Límites de parámetros»); el resto del código usa sus `effective_*`.
- `hamiltonian.py` / `relaxation.py`: Hamiltoniano magnético + cuadrupolar completo; relajación y ajuste global Néel–Arrhenius multi-temperatura.
- `normos_job.py`: lectura y escritura de ficheros `.JOB` de NORMOS.
- `phase_id.py`: sugerencia de fases por comparación con la base de referencia.
- `blas_threads.py`: BLAS/LAPACK con un solo hilo (se importa antes que numpy); con las matrices de Fitbauer el reparto entre núcleos costaba más que el cálculo.

Los textos que ve el usuario pasan por `mossbauer_i18n.tr()` (sin Qt), con catálogos en `locales/` para 8 idiomas.

### `gui/`

Interfaz Qt modular. No debe contener motores físicos ni lógica de ajuste pesada.

- `state.py`: snapshots de GUI (`ComponentViewState`, `CalibrationViewState`, `DistributionViewState`, `UiActionState`, etc.).
- `fit_workflow.py`: flujo común de ajuste GUI: progreso, errores y render.
- `model_workflow.py`: carga/folding, construcción de `FitState`, actualización de plot/info.
- `discrete_fit.py` y `distribution_fit.py`: orquestación específica de cada modo.
- `distribution_panel.py`: panel de distribución; muestra solo los controles que usan la variable y la forma activas.
- `param_limits_dialog.py`: diálogo de límites de parámetros.
- `qt_translations.py`: instala el traductor de Qt (`qtbase_<idioma>.qm`) para los botones y diálogos estándar.
- `session_io.py`: sesión JSON mediante `ProjectState`.
- `reports.py`: salidas de usuario apoyadas en `core.result_views`.
- `compat.py`: compatibilidad histórica de símbolos/parches del antiguo `mossbauer_qt.py`.

### `mossbauer_qt.py`

Punto de entrada fino. Debe limitarse a crear `MossbauerQtWindow`, reexportar símbolos históricos necesarios y llamar a `main()`.

## Flujo de datos simplificado

```text
Fichero WS5/ADT
   ↓ core.folding / core.data_io
FileState
   ↓ snapshots GUI
ModelState / FitState
   ↓ core.fit_engine o distribución
FitResult / BhfDistributionFit
   ↓ core.reconstruction + core.result_views
Canvas / informes / exportaciones
```

## Estado y snapshots

La GUI evita leer widgets directamente desde la lógica. Cada panel importante expone un snapshot:

- `CalibrationPanel.to_view_state()` → `CalibrationViewState`
- `ComponentPanel.to_view_state()` → `ComponentViewState`
- `DistributionPanel.to_view_state()` → `DistributionViewState`
- acciones globales → `UiActionState`

Los snapshots son de lectura. Las escrituras siguen ocurriendo sobre widgets cuando hay que aplicar resultados, cargar sesiones o sincronizar menús.

## Ajustes discreto y distribución

Ambos modos comparten:

- diálogo de progreso,
- manejo de errores,
- render del resultado,
- `GuiFitResult` y `RuntimeResultState`.

La física no se fusiona: el discreto usa `core.fit_engine`; las distribuciones usan `mossbauer_distribution.py`.

## Validación

Antes de ajustar, la GUI llama a `core.validation`:

- discreto/bootstrap: `validate_fit_state(...)`,
- distribución: `validate_distribution_parameters(...)`.

Los límites proceden principalmente de `core.params`.

## Compatibilidad histórica

Algunos tests/extensiones parchean símbolos en `mossbauer_qt.py`. La compatibilidad se centraliza en `gui.compat.frontend_attr(...)` y en `HistoricalRuntimeCompatMixin`. El código nuevo debe depender de los módulos reales, no de esos reexports.
