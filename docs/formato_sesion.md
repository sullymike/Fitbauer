# Formato de sesión JSON

Módulos: `gui/session_io.py` (GUI) · `core/session.py` (headless) · `gui/state.py` (`ProjectState`)

Menú: **Archivo → Guardar sesión…** / **Archivo → Cargar sesión…**

---

## Qué guarda una sesión

Una sesión JSON captura todo lo necesario para **reproducir el estado de trabajo**:
el espectro, la calibración, el modelo de componentes, las opciones de ajuste, la
configuración de distribución y el último resultado de ajuste. Permite cerrar la
aplicación y retomar exactamente donde se dejó, o compartir un análisis completo.

---

## Esquema del payload

El payload (idéntico entre la GUI Qt y la capa headless `core.session`) tiene esta
estructura de primer nivel:

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

> **Cuentas embebidas.** El array `counts` guarda el espectro crudo dentro del JSON,
> de modo que la sesión se puede recargar aunque el fichero original ya no exista.
> Al cargar, si `file_path` existe se relee del disco; si no, se usan las `counts`
> embebidas y se redobla con el folding point detectado.

---

## Bloque `model_state`

Es el corazón de la sesión: define los componentes y todas las opciones del modelo
(`ModelState.to_model_state_dict`):

| Clave | Tipo | Contenido |
|---|---|---|
| `vars` | dict | Valores planos: `vmax`, `center`, `baseline`, `slope`, `voigt_sigma`, `sat_scale`, y `s{idx}_{param}` por componente |
| `fixed` | dict | Flags fijo/libre por cada clave de `vars` |
| `sextet_enabled` | dict | `{idx: bool}` — qué componentes están activos |
| `component_kind` | dict | `{idx: "Sextete"/"Doblete"/"Singlete"/"Relajacion"/"BlumeTjon"/"NeelSize"}` |
| `intensity_mode` | dict | `{idx: "free"/...}` |
| `quad_treatment` | dict | `{idx: "1st_order"/...}` |
| `fit_velocity`, `fit_center`, `fit_sigma` | bool | Qué parámetros de calibración se ajustan |
| `line_profile` | str | `"Lorentziana"` / `"Voigt"` |
| `likelihood` | str | `"gauss"` / `"poisson"` |
| `robust_loss` | str | `"linear"` / `"soft_l1"` / `"huber"` |
| `absorber_model` | str | `"thin"` / `"thickness"` |
| `propagate_calib`, `global_opt` | bool | Opciones avanzadas |
| `multistart_n` | int | Nº de reinicios multistart (0–10) |
| `n_components` | int | Nº de componentes |
| `constraints` | list | Restricciones lineales entre parámetros |

La GUI añade además claves propias al guardar: `mode_combo_idx` (modo discreto/
distribución/2D), `dist_*` (forma, regularización, ruta de distribución fija),
`show_residual`, `show_legend`, etc.

---

## Bloque `last_fit`

Resultado del último ajuste (vacío si no se ha ajustado):

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

## Plantillas vs sesiones

Un mismo `model_state` sirve como **plantilla** reutilizable. `apply_template`
(en `ModelState`) vuelca el modelo sobre el estado actual pero:

- **Ignora `center`**: cada espectro detecta su propio folding point.
- **Valida los enums**: solo acepta tipos de componente, modos de intensidad y
  tratamientos cuadrupolares conocidos.
- **Fuerza `int3` fijo**: `int3` es la referencia NORMOS, siempre fija.

Esto permite cargar una plantilla de componentes (p.ej. "magnetita: 2 sextetes")
sobre cualquier espectro nuevo. Los ejemplos viven en `data_sample/` como JSON.

---

## Uso headless (sin GUI)

`core.session.HeadlessSession` genera y consume el mismo formato:

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

El CLI `mossbauer_fit_cli.py` usa exactamente este flujo.

---

## Compatibilidad histórica

El formato es compatible hacia atrás con las sesiones de la antigua GUI Tk. Al cargar
sesiones antiguas:

- Sin `mode_combo_idx`: el modo se infiere de `dist_variable` (BHF→1, ΔEQ→2, IS→3,
  variantes 2D→4/5/6).
- `dist_refine_global` (campo legacy de v4.5): se ignora silenciosamente.
- Claves desconocidas: se ignoran sin error.
