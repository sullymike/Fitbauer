# Spectrum comparison (visual overlay)

Available since **v4.10.0** · Menu **File → Compare spectrum…**

Modules: `gui/file_actions.py` (`on_open_comparison`, `on_clear_comparison`),
`gui/canvas.py` (render), `gui/plotly_tools.py`, `gui/state.py`
(`ComparisonSpectrum`)

---

## What it does

Allows loading **one or more additional spectra** and overlaying them on the main
spectrum as thin lines of distinct colors, **without touching the fit engine or the
calibration state**. It is a purely visual aid to compare samples, follow a
temperature series at a glance, or contrast a spectrum with a reference.

- Up to **6 comparison spectra** simultaneously.
- Each one with a distinct color from the palette:
  orange, teal, pink, lime, violet, sky blue.
- They also appear in the exportable **Plotly** figure (interactive HTML).
- Fitting keeps working with comparison spectra active: they do not interfere.

---

## Usage flow

1. First load a **main spectrum** (File → Load…). Without a main spectrum,
   "Compare spectrum…" shows a warning and does nothing.
2. **File → Compare spectrum…** → select an ADT/WS5/CSV file.
3. The spectrum is normalized and overlaid (first line: orange).
4. Repeat to add more (second: teal, etc.), up to 6.
5. **File → Clear comparison** removes all (the action is enabled only when there is
   at least one).

---

## Loading and normalization

`on_open_comparison` accepts the same formats as the main spectrum:

| Format | Treatment |
|---|---|
| `.csv`, `.txt`, `.dat`, `.exp` | `load_velocity_csv` — already folded in velocity |
| `.ws5`, `.adt` | Automatic folding: `find_best_integer_or_half_center` + `fold_and_normalize` with the optimal center, axis by `velocity_axis` |

After loading, the spectrum is normalized to relative transmission (baseline ≈ 1.0)
by dividing by the **90th percentile**:

```python
norm = float(np.percentile(y_raw, 90)) or 1.0
y_data = y_raw / norm
```

The result is stored as a `ComparisonSpectrum`:

```python
@dataclass
class ComparisonSpectrum:
    """Espectro cargado solo para comparación visual (sin ajuste)."""
    path: Path
    velocity: np.ndarray
    y_data: np.ndarray
    label: str
```

and is added to `self.comparison_spectra` (list initialized in `__init__` of
`MossbauerQtWindow`). The label is the file name without extension.

---

## Rendering

### Matplotlib canvas (`gui/canvas.py`)

`render()` accepts a `comparison=` parameter (list of `ComparisonSpectrum`). The
comparison lines are drawn **before** the main spectrum, with the `_COMPARISON_PALETTE`
palette. They are stored in `self._artists["cmp_lines"]` and the layout signature
(`layout_sig`) includes `n_cmp = len(comparison)` to force a full redraw when the
number of compared spectra changes.

### Plotly (`gui/plotly_tools.py`)

Each comparison spectrum is added as a `Scattergl` trace (lines, opacity 0.75) before
the main spectrum trace, with its palette color, so that it also appears in the
interactive HTML export.

---

## Separation of responsibilities

- The `ComparisonSpectrum` are **display-only**: they do not enter `FitState`, are not
  saved in the session, do not affect the calibration or the model.
- `on_clear_comparison` empties the list and disables the clear action.
- The rescaling of each spectrum is independent (its own 90th percentile), so that
  spectra with different absorption depth are compared on the same relative
  transmission scale.

---

## Translation strings

The menu labels and messages are in `locales/{es,en,fr}/strings.json`:

- `file.compare_spectrum`, `file.clear_comparison`
- `status.comparison_added`, `status.comparison_cleared`
- `msg.comparison_needs_main`
