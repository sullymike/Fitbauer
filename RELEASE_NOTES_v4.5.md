# Fitbauer v4.5

Release centrada en arquitectura, mantenibilidad y robustez de la interfaz Qt.

## Cambios principales

- GUI Qt modular en `gui/`, con `mossbauer_qt.py` como wrapper fino.
- Snapshots formales para paneles y acciones (`ComponentViewState`, `CalibrationViewState`, `DistributionViewState`, `UiActionState`, `ProjectState`).
- Flujo común de ajuste discreto/distribución: progreso, errores, render y `GuiFitResult`.
- Nueva capa `core.reconstruction` para reconstrucción física de modelos, residuos, áreas y curvas de distribución.
- Nueva capa `core.validation` para validar parámetros antes de ajustar.
- Nueva capa `core.result_views` para consultar resultados desde informes, Plotly y paneles.
- Compatibilidad histórica centralizada en `gui.compat`.
- Documentación nueva: `docs/architecture.md` y `docs/user-flows.md`.
- Más tests específicos por módulo GUI y core.

## Validación

La suite completa de tests pasa en modo offscreen:

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```
