# GUI Qt

Implementación modular de la interfaz Qt/Plotly de Fitbauer.

`mossbauer_qt.py` debe permanecer como wrapper fino: define `MossbauerQtWindow`,
compone `WindowMixins` y contiene `main()`. La lógica de interfaz vive aquí.

## Estructura

- `compat.py` — compatibilidad histórica centralizada (`frontend_attr`, propiedades legacy).
- `window_mixins.py` — composición ordenada de los mixins de la ventana principal.
- `main_layout.py` — construcción del layout principal.
- `menu_builder.py` — barra de menús y acciones globales.
- `layout_manager.py` — presets de layout, temas, settings y apilado/pestañas.
- `controls.py` — controles reutilizables (`ParamControl`).
- `panels.py` — paneles de calibración, componentes e información.
- `distribution_panel.py` — controles de `P(BHF)` / `P(ΔEQ)` y snapshot
  `DistributionViewState` mediante `to_view_state()`.
- `canvas.py` — canvas Matplotlib y render incremental.
- `model_workflow.py` — carga de espectro, folding/refolding, `ModelState`/`FitState`,
  actualización de plot e info.
- `fit_workflow.py` — flujo común de ajustes GUI: progreso y render compartido.
- `discrete_fit.py` — ajuste discreto y bootstrap.
- `distribution_fit.py` — ajuste de distribuciones, L-curve y componentes nítidos.
- `minima_analysis.py` — detección de mínimos e inicialización automática.
- `plotly_tools.py` — figura Plotly, HTML incremental y editor semi-manual de mínimos.
- `fit_tools.py` — batch, restricciones, perfil likelihood, presets físicos y resumen IA.
- `state.py` — estado runtime (`FileState`, `RuntimeResultState`) y snapshots serializables
  (`ComponentViewState`, `SpectrumState`, `CalibrationState`, `FitOptionsState`,
  `DistributionViewState`, `PlotViewState`, `UiActionState`, `UiPreferencesState`,
  `ProjectState`) para reducir el acoplamiento
  widget→lógica.
- `session_io.py` — guardar/cargar sesión usando `ProjectState` sin romper el formato JSON histórico.
- `reports.py` — informe Markdown/PDF.
- `web_api.py` — API web del laboratorio.
- `updates.py` — GitHub Releases y actualización.
- `help.py` — ayuda integrada y acerca de.
- `calibration_actions.py`, `file_actions.py` — acciones auxiliares.
- `branding.py`, `bridges.py`, `state.py`, `themes.py` — piezas de soporte.

## Flujo interno principal

```text
Usuario/Qt widgets
  ↓ to_view_state()
Snapshots GUI (`CalibrationViewState`, `ComponentViewState`, `DistributionViewState`)
  ↓
`ModelState` / `FitState`
  ↓ validación (`core.validation`)
Motores (`core.fit_engine`, `mossbauer_distribution`)
  ↓
`RuntimeResultState` + `GuiFitResult`
  ↓
Reconstrucción/render (`core.reconstruction`, `FitWorkflowMixin`)
  ↓
Canvas, Plotly, informes y exportaciones
```

## Flujos de usuario cubiertos por módulos

- **Carga/folding**: `file_actions.py` + `model_workflow.py`.
- **Ajuste discreto**: `discrete_fit.py` orquesta; el cálculo vive en `core.fit_engine`.
- **Distribución**: `distribution_fit.py` orquesta; la reconstrucción de curvas vive en `core.reconstruction`.
- **Sesiones**: `session_io.py` usa `ProjectState` y conserva el JSON histórico.
- **Informes/Plotly**: consumen `core.result_views` para no depender directamente de atributos internos de resultados.
- **Compatibilidad**: `compat.py` concentra accesos a símbolos históricos parcheables de `mossbauer_qt.py`.

## Tests específicos por módulo

La suite incluye tests unitarios de snapshots y helpers para evitar que los módulos GUI vuelvan a depender de widgets en la lógica:

- `tests/test_gui_panel_snapshots.py` — snapshots de `CalibrationPanel`, `ComponentPanel` y `DistributionPanel`.
- `tests/test_fit_workflow_mixin.py` — render común de `FitWorkflowMixin`.
- `tests/test_gui_compat.py` — compatibilidad histórica centralizada.
- `tests/test_gui_state.py`, `tests/test_component_view_state.py`, `tests/test_ui_action_state.py` — estados/snapshots puros.

## Reglas

- No poner física ni motores de ajuste aquí: deben vivir en `core/`.
- Evitar engordar `mossbauer_qt.py`; añadir nuevas acciones en el mixin/módulo adecuado.
- Mantener compatibilidad con tests/extensiones que parchean símbolos históricos reexportados desde
  `mossbauer_qt.py`; añadir nuevos puentes en `compat.py`, no dispersarlos.
- Para leer widgets desde lógica, crear/usar snapshots `*ViewState`. Para escribir en la UI, tocar widgets explícitamente.
- Para presentar resultados, usar `core.result_views`; para reconstruir curvas/áreas/modelos, usar `core.reconstruction`.
- Tras cambios de GUI ejecutar:

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```
