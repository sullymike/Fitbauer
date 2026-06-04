# Fitbauer v4.0.2

Versión de mantenimiento sobre **Fitbauer v4.0.1**. Unifica la calibración del campo.

## 🧲 Calibración del campo a 33.0 T (consistente con NORMOS)

- Se elimina la constante interna **32.95 T** (no publicada). Toda la calibración de velocidad/campo (Tk, Qt, modelo discreto y distribución) usa las posiciones publicadas de α-Fe escaladas al campo de referencia **33.0 T (330 kOe)**.
- Resultado: un espectro de **α-Fe ajusta exactamente a 33.0 T, igual que NORMOS**.

## 🧹 Fuente única y limpieza

- `mossbauer_distribution.py` toma ahora `LINE_POS_33T` de `core.constants` (se elimina una tercera copia duplicada de las posiciones).
- Las posiciones del sextete se mantienen en el **patrón de velocidad publicado** de α-Fe (`±0.839 / ±3.084 / ±5.329 mm/s` a 33 T). Se documenta por qué no deben derivarse de los momentos nucleares de libro (sesgarían el BHF ~0,1 T hacia arriba).
- Se elimina el parámetro muerto `max_nfev` de `profile_likelihood()`.

## 🔁 Compatibilidad

- Las sesiones e informes previos se cargan sin cambios.
- Verifica el ZIP con `sha256sums.txt`.
