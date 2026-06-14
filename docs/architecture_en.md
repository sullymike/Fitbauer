# Fitbauer internal architecture

Fitbauer separates the Mössbauer computation from the graphical interface. The practical rule is:

```text
core/  → physics, fitting, reconstruction, validation and result views
 gui/  → widgets, menus, sessions, render and user orchestration
CLIs   → headless clients of core/
```

## Main layers

### `core/`

Pure code, without Qt/Tk:

- `physics.py`: line shapes and component absorption.
- `fit_engine.py`: discrete fitting and bootstrap.
- `mossbauer_distribution.py`: fitting of `P(BHF)` / `P(ΔEQ)` distributions.
- `session.py`: `ModelState` and headless session.
- `reconstruction.py`: reconstruction of models, residuals, subspectra, areas and distribution curves.
- `validation.py`: structural and parameter-bounds validation.
- `result_views.py`: result reading API for reports, Plotly and panels.
- `params.py`: canonical registry of parameters, defaults and bounds.

### `gui/`

Modular Qt interface. It must not contain physics engines or heavy fitting logic.

- `state.py`: GUI snapshots (`ComponentViewState`, `CalibrationViewState`, `DistributionViewState`, `UiActionState`, etc.).
- `fit_workflow.py`: common GUI fitting flow: progress, errors and render.
- `model_workflow.py`: loading/folding, construction of `FitState`, plot/info update.
- `discrete_fit.py` and `distribution_fit.py`: specific orchestration of each mode.
- `session_io.py`: JSON session via `ProjectState`.
- `reports.py` and `plotly_tools.py`: user outputs backed by `core.result_views`.
- `compat.py`: historical compatibility of symbols/patches from the old `mossbauer_qt.py`.

### `mossbauer_qt.py`

Thin entry point. It should be limited to creating `MossbauerQtWindow`, re-exporting the necessary historical symbols and calling `main()`.

## Simplified data flow

```text
WS5/ADT file
   ↓ core.folding / core.data_io
FileState
   ↓ GUI snapshots
ModelState / FitState
   ↓ core.fit_engine or distribution
FitResult / BhfDistributionFit
   ↓ core.reconstruction + core.result_views
Canvas / Plotly / reports / exports
```

## State and snapshots

The GUI avoids reading widgets directly from the logic. Each important panel exposes a snapshot:

- `CalibrationPanel.to_view_state()` → `CalibrationViewState`
- `ComponentPanel.to_view_state()` → `ComponentViewState`
- `DistributionPanel.to_view_state()` → `DistributionViewState`
- global actions → `UiActionState`

The snapshots are read-only. Writes still occur on widgets when results have to be applied, sessions loaded or menus synchronized.

## Discrete and distribution fitting

Both modes share:

- progress dialog,
- error handling,
- result render,
- `GuiFitResult` and `RuntimeResultState`.

The physics is not merged: the discrete mode uses `core.fit_engine`; the distributions use `mossbauer_distribution.py`.

## Validation

Before fitting, the GUI calls `core.validation`:

- discrete/bootstrap: `validate_fit_state(...)`,
- distribution: `validate_distribution_parameters(...)`.

The bounds come mainly from `core.params`.

## Historical compatibility

Some tests/extensions patch symbols in `mossbauer_qt.py`. The compatibility is centralized in `gui.compat.frontend_attr(...)` and in `HistoricalRuntimeCompatMixin`. New code must depend on the real modules, not on those re-exports.
