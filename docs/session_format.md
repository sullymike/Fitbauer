# JSON session format

Modules: `gui/session_io.py` (GUI) · `core/session.py` (headless) · `gui/state.py` (`ProjectState`)

Menu: **File → Save session…** / **File → Load session…**

---

## What a session saves

A JSON session captures everything needed to **reproduce the working state**:
the spectrum, the calibration, the component model, the fit options, the distribution
configuration and the last fit result. It lets you close the application and resume
exactly where you left off, or share a complete analysis.

---

## Payload schema

The payload (identical between the Qt GUI and the headless layer `core.session`) has
this top-level structure:

```json
{
  "version": 1,
  "program": "core.session",
  "file_path": "/ruta/al/espectro.ws5",
  "file_name": "espectro.ws5",
  "counts": [ ... ],                 // cuentas crudas embebidas (N canales)
  "calibration": { ... },            // dict de calibración o null
  "state_and_parameters_text": "",
  "model_state": { ... },            // ver abajo
  "last_fit": { ... }                // ver abajo
}
```

> **Embedded counts.** The `counts` array stores the raw spectrum inside the JSON,
> so that the session can be reloaded even if the original file no longer exists.
> When loading, if `file_path` exists it is re-read from disk; if not, the embedded
> `counts` are used and re-folded with the detected folding point.

---

## `model_state` block

It is the heart of the session: it defines the components and all the model options
(`ModelState.to_model_state_dict`):

| Key | Type | Content |
|---|---|---|
| `vars` | dict | Flat values: `vmax`, `center`, `baseline`, `slope`, `voigt_sigma`, `sat_scale`, and `s{idx}_{param}` per component |
| `fixed` | dict | Fixed/free flags for each key in `vars` |
| `sextet_enabled` | dict | `{idx: bool}` — which components are active |
| `component_kind` | dict | `{idx: "Sextete"/"Doblete"/"Singlete"/"Relajacion"/"BlumeTjon"/"NeelSize"}` |
| `intensity_mode` | dict | `{idx: "free"/...}` |
| `quad_treatment` | dict | `{idx: "1st_order"/...}` |
| `fit_velocity`, `fit_center`, `fit_sigma` | bool | Which calibration parameters are fitted |
| `line_profile` | str | `"Lorentziana"` / `"Voigt"` |
| `likelihood` | str | `"gauss"` / `"poisson"` |
| `robust_loss` | str | `"linear"` / `"soft_l1"` / `"huber"` |
| `absorber_model` | str | `"thin"` / `"thickness"` |
| `propagate_calib`, `global_opt` | bool | Advanced options |
| `multistart_n` | int | Number of multistart restarts (0–10) |
| `n_components` | int | Number of components |
| `constraints` | list | Linear constraints between parameters |

The GUI additionally adds its own keys when saving: `mode_combo_idx` (discrete/
distribution/2D mode), `dist_*` (shape, regularization, fixed distribution path),
`show_residual`, `show_legend`, etc.

---

## `last_fit` block

Result of the last fit (empty if no fit has been done):

```json
"last_fit": {
  "free_keys": ["s1_bhf", "s1_delta", ...],
  "covariance": [[...]],            // matriz de covarianza o null
  "parameter_errors": { "s1_bhf": 0.3, ... },
  "fit_statistics": { "chi2": ..., "red_chi2": ..., "aic": ..., ... },
  "correlations": { ... },
  "info_text": ""
}
```

---

## Templates vs sessions

The same `model_state` serves as a reusable **template**. `apply_template`
(in `ModelState`) dumps the model onto the current state but:

- **Ignores `center`**: each spectrum detects its own folding point.
- **Validates the enums**: it only accepts known component types, intensity modes and
  quadrupole treatments.
- **Forces `int3` fixed**: `int3` is the NORMOS reference, always fixed.

This allows loading a component template (e.g. "magnetite: 2 sextets") onto any new
spectrum. The examples live in `data_sample/` as JSON.

---

## Headless use (no GUI)

`core.session.HeadlessSession` generates and consumes the same format:

```python
from core.session import HeadlessSession, ModelState
import json

session = HeadlessSession(ModelState.defaults())
session.load_ws5("espectro.ws5", vmax=12.0)
session.apply_template_model_state(json.load(open("plantilla.json"))["model_state"])
result = session.run_fit()                      # {values, errors, stats, free_keys}

payload = session.session_payload()             # mismo esquema que la GUI
json.dump(payload, open("sesion.json", "w"), indent=2, ensure_ascii=False)
```

The CLI `mossbauer_fit_cli.py` uses exactly this flow.

---

## Historical compatibility

The format is backward-compatible with sessions from the old Tk GUI. When loading
old sessions:

- Without `mode_combo_idx`: the mode is inferred from `dist_variable` (BHF→1, ΔEQ→2,
  IS→3, 2D variants→4/5/6).
- `dist_refine_global` (legacy field from v4.5): silently ignored.
- Unknown keys: ignored without error.
```
