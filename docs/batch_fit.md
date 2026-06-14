# Batch (serial) fitting by warm-start

Modules: `core/batch_fit.py` (pure helpers) · `core.session.HeadlessSession.batch_fit_sequential`

---

## Motivation

A typical experimental series measures the **same material at several temperatures**,
or several samples from a family, and one wants to extract the trend of a parameter
(BHF, ΔEQ, δ, area) against an external variable (temperature, pressure, composition).
Fitting each spectrum from scratch is slow and prone to local-minimum jumps between
neighboring spectra. Batch fitting by **warm-start** solves both problems:
the fitted parameters of one spectrum are used as the starting point of the next.

---

## Warm-start chaining (`batch_fit_sequential`)

The headless loop processes the files in order:

1. **Save** the model's current values of the active parameters
   (`active_param_keys`), plus `voigt_sigma`.
2. **Load** the next spectrum (`load_ws5`): it detects its own folding point and
   $V_{\max}$ — these are **per spectrum** and are NOT inherited.
3. **Restore** the saved values onto the new spectrum (warm-start):
   the rest of the physical parameters (δ, ΔEQ, BHF, linewidths, depths) start from
   the previous fit.
4. **Fit** (`run_fit`).
5. Record the result. **Failures do not stop the series**: they are marked with
   `status="failed"` and processing continues with the next file.

```python
from core.session import HeadlessSession, ModelState

session = HeadlessSession(ModelState.defaults())
session.load_ws5("espectro_300K.ws5")     # primer espectro: define el modelo base
session.apply_template_model_state(plantilla)  # opcional: plantilla de componentes

files = ["espectro_300K.ws5", "espectro_200K.ws5", "espectro_80K.ws5"]
temps = [300.0, 200.0, 80.0]
rows = session.batch_fit_sequential(files, metadata_list=temps)
```

Each row of `rows` is a dict with `file`, `metadata`, `status`, `values`, `errors`, `stats`.

---

## Extracting metadata from the name (`extract_metadata`)

To associate each spectrum with its external variable without having to type it by
hand, it can be extracted from the file name with a regular expression:

```python
from core.batch_fit import extract_metadata

extract_metadata("muestra_80K.ws5", r"(\d+)K")      # → 80.0
extract_metadata("Fe2O3_300.adt", r"_(?P<v>\d+)")   # → 300.0
```

- If the pattern has a named group `(?P<v>...)` that one is used; if not, the first
  capturing group; if there are no groups, the full match.
- The value is returned as a `float` if convertible, otherwise as a `str`.
- Returns `None` if there is no match or the pattern is invalid.

---

## Exporting results (`write_results_csv`)

Writes a CSV (actually TSV) with **one row per spectrum**:

| Column | Content |
|---|---|
| `file` | File name |
| `metadata` | External value (temperature, etc.) |
| `status` | `ok` / `failed` |
| `chi2`, `red_chi2` | Fit statistics |
| `<key>`, `<key>_err` | Value and 1σ error of each free parameter |

```python
from core.batch_fit import write_results_csv
from pathlib import Path

free_keys = ["s1_bhf", "s1_delta", "s1_quad"]
write_results_csv(Path("serie.tsv"), free_keys, rows)
```

---

## Trend data (`collect_trend_data`)

To plot a parameter against the external metadata, it groups the valid points:

```python
from core.batch_fit import collect_trend_data

trend = collect_trend_data(rows, free_keys)
# trend["s1_bhf"] = [(80.0, 51.2, 0.3), (200.0, 49.8, 0.4), (300.0, 47.1, 0.5), ...]
#                    (metadato, valor, error)  ordenado por metadato
```

Only includes rows with `status == "ok"` and numeric metadata, sorted by metadata.
It is the direct input for a BHF(T), δ(T), etc. plot.

---

## Practical notes

- The order of the files matters: it is best to sort them by the external variable
  (e.g. from higher to lower temperature) so that the warm-start is smooth.
- The first spectrum defines the base model: it is best to fit it well (or load a
  template) before launching the series.
- `center` and `vmax` are **never** inherited: each spectrum detects its own folding
  point and uses its own velocity calibration.
- All of the code in `core/batch_fit.py` is pure (no Qt): it can be tested and run
  without a display, and it is what the batch tests use.
