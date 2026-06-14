# Comparación de espectros (superposición visual)

Disponible desde **v4.10.0** · Menú **Archivo → Comparar espectro…**

Módulos: `gui/file_actions.py` (`on_open_comparison`, `on_clear_comparison`),
`gui/canvas.py` (render), `gui/plotly_tools.py`, `gui/state.py`
(`ComparisonSpectrum`)

---

## Qué hace

Permite cargar **uno o más espectros adicionales** y superponerlos al espectro
principal como líneas finas de colores distintos, **sin tocar el motor de ajuste ni
el estado de calibración**. Es una ayuda puramente visual para comparar muestras,
seguir una serie de temperatura de un vistazo o contrastar un espectro con una
referencia.

- Hasta **6 espectros de comparación** simultáneos.
- Cada uno con un color distinto de la paleta:
  naranja, teal, rosa, lima, violeta, azul cielo.
- Aparecen también en la figura **Plotly** exportable (HTML interactivo).
- El ajuste sigue funcionando con espectros de comparación activos: no interfieren.

---

## Flujo de uso

1. Cargar primero un **espectro principal** (Archivo → Cargar…). Sin espectro
   principal, "Comparar espectro…" muestra un aviso y no hace nada.
2. **Archivo → Comparar espectro…** → seleccionar un fichero ADT/WS5/CSV.
3. El espectro se normaliza y se superpone (primera línea: naranja).
4. Repetir para añadir más (segunda: teal, etc.), hasta 6.
5. **Archivo → Limpiar comparación** elimina todos (la acción se habilita solo cuando
   hay al menos uno).

---

## Carga y normalización

`on_open_comparison` admite los mismos formatos que el espectro principal:

| Formato | Tratamiento |
|---|---|
| `.csv`, `.txt`, `.dat`, `.exp` | `load_velocity_csv` — ya doblado en velocidad |
| `.ws5`, `.adt` | Doblado automático: `find_best_integer_or_half_center` + `fold_and_normalize` con el centro óptimo, eje por `velocity_axis` |

Tras cargar, el espectro se normaliza a transmisión relativa (baseline ≈ 1.0)
dividiendo por el **percentil 90**:

```python
norm = float(np.percentile(y_raw, 90)) or 1.0
y_data = y_raw / norm
```

El resultado se guarda como un `ComparisonSpectrum`:

```python
@dataclass
class ComparisonSpectrum:
    """Espectro cargado solo para comparación visual (sin ajuste)."""
    path: Path
    velocity: np.ndarray
    y_data: np.ndarray
    label: str
```

y se añade a `self.comparison_spectra` (lista inicializada en `__init__` de
`MossbauerQtWindow`). La etiqueta es el nombre del fichero sin extensión.

---

## Renderizado

### Canvas Matplotlib (`gui/canvas.py`)

`render()` acepta un parámetro `comparison=` (lista de `ComparisonSpectrum`). Las
líneas de comparación se dibujan **antes** del espectro principal, con la paleta
`_COMPARISON_PALETTE`. Se almacenan en `self._artists["cmp_lines"]` y la firma de
layout (`layout_sig`) incluye `n_cmp = len(comparison)` para forzar un redibujado
completo cuando cambia el número de espectros comparados.

### Plotly (`gui/plotly_tools.py`)

Cada espectro de comparación se añade como traza `Scattergl` (líneas, opacidad 0.75)
antes de la traza del espectro principal, con su color de paleta, de modo que aparezca
también en la exportación HTML interactiva.

---

## Separación de responsabilidades

- Los `ComparisonSpectrum` son **solo de display**: no entran en `FitState`, no se
  guardan en la sesión, no afectan a la calibración ni al modelo.
- `on_clear_comparison` vacía la lista y deshabilita la acción de limpiar.
- El reescalado de cada espectro es independiente (percentil 90 propio), de modo que
  espectros con distinta profundidad de absorción se comparan en la misma escala
  relativa de transmisión.

---

## Cadenas de traducción

Las etiquetas de menú y mensajes están en `locales/{es,en,fr}/strings.json`:

- `file.compare_spectrum`, `file.clear_comparison`
- `status.comparison_added`, `status.comparison_cleared`
- `msg.comparison_needs_main`
