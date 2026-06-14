# Ajuste en serie (batch) por warm-start

Módulos: `core/batch_fit.py` (helpers puros) · `core.session.HeadlessSession.batch_fit_sequential`

---

## Motivación

Una serie experimental típica mide el **mismo material a varias temperaturas**, o
varias muestras de una familia, y se quiere extraer la tendencia de un parámetro
(BHF, ΔEQ, δ, área) frente a una variable externa (temperatura, presión, composición).
Ajustar cada espectro desde cero es lento y propenso a saltos de mínimo local entre
espectros vecinos. El ajuste en serie por **warm-start** resuelve ambos problemas:
los parámetros ajustados de un espectro se usan como punto de partida del siguiente.

---

## Encadenado por warm-start (`batch_fit_sequential`)

El bucle headless procesa los ficheros en orden:

1. **Guardar** los valores actuales del modelo de los parámetros activos
   (`active_param_keys`), más `voigt_sigma`.
2. **Cargar** el siguiente espectro (`load_ws5`): detecta su propio folding point y
   $V_{\max}$ — estos son **por espectro** y NO se heredan.
3. **Restaurar** los valores guardados sobre el nuevo espectro (warm-start):
   el resto de parámetros físicos (δ, ΔEQ, BHF, anchuras, profundidades) parten del
   ajuste anterior.
4. **Ajustar** (`run_fit`).
5. Registrar el resultado. **Los fallos no detienen la serie**: se marcan con
   `status="failed"` y se continúa con el siguiente fichero.

```python
from core.session import HeadlessSession, ModelState

session = HeadlessSession(ModelState.defaults())
session.load_ws5("espectro_300K.ws5")     # primer espectro: define el modelo base
session.apply_template_model_state(plantilla)  # opcional: plantilla de componentes

files = ["espectro_300K.ws5", "espectro_200K.ws5", "espectro_80K.ws5"]
temps = [300.0, 200.0, 80.0]
rows = session.batch_fit_sequential(files, metadata_list=temps)
```

Cada fila de `rows` es un dict con `file`, `metadata`, `status`, `values`, `errors`, `stats`.

---

## Extracción de metadatos del nombre (`extract_metadata`)

Para asociar cada espectro a su variable externa sin tener que escribirla a mano, se
puede extraer del nombre del fichero con una expresión regular:

```python
from core.batch_fit import extract_metadata

extract_metadata("muestra_80K.ws5", r"(\d+)K")      # → 80.0
extract_metadata("Fe2O3_300.adt", r"_(?P<v>\d+)")   # → 300.0
```

- Si el patrón tiene un grupo nombrado `(?P<v>...)` se usa ese; si no, el primer grupo
  capturador; si no hay grupos, la coincidencia completa.
- El valor se devuelve como `float` si es convertible, si no como `str`.
- Devuelve `None` si no hay coincidencia o el patrón es inválido.

---

## Exportación de resultados (`write_results_csv`)

Escribe un CSV (TSV en realidad) con **una fila por espectro**:

| Columna | Contenido |
|---|---|
| `file` | Nombre del fichero |
| `metadata` | Valor externo (temperatura, etc.) |
| `status` | `ok` / `failed` |
| `chi2`, `red_chi2` | Estadísticos del ajuste |
| `<key>`, `<key>_err` | Valor y error 1σ de cada parámetro libre |

```python
from core.batch_fit import write_results_csv
from pathlib import Path

free_keys = ["s1_bhf", "s1_delta", "s1_quad"]
write_results_csv(Path("serie.tsv"), free_keys, rows)
```

---

## Datos de tendencia (`collect_trend_data`)

Para representar un parámetro frente al metadato externo, agrupa los puntos válidos:

```python
from core.batch_fit import collect_trend_data

trend = collect_trend_data(rows, free_keys)
# trend["s1_bhf"] = [(80.0, 51.2, 0.3), (200.0, 49.8, 0.4), (300.0, 47.1, 0.5), ...]
#                    (metadato, valor, error)  ordenado por metadato
```

Solo incluye filas con `status == "ok"` y metadato numérico, ordenadas por metadato.
Es la entrada directa para una gráfica BHF(T), δ(T), etc.

---

## Notas prácticas

- El orden de los ficheros importa: conviene ordenarlos por la variable externa
  (p.ej. de mayor a menor temperatura) para que el warm-start sea suave.
- El primer espectro define el modelo base: conviene ajustarlo bien (o cargar una
  plantilla) antes de lanzar la serie.
- `center` y `vmax` **nunca** se heredan: cada espectro detecta su propio folding
  point y usa su propia calibración de velocidad.
- Todo el código de `core/batch_fit.py` es puro (sin Qt): se puede probar y ejecutar
  sin display, y es lo que usan los tests por lotes.
