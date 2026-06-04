# Fitbauer v4.0.2

Versión de mantenimiento sobre **Fitbauer v4.0.1**. Corrección de la calibración del sextete.

## 🔬 Posiciones del sextete teóricas (consistentes con NORMOS)

- Las 6 posiciones del sextete magnético se **derivan ahora de primeros principios** a partir de los momentos nucleares del ⁵⁷Fe (niveles Zeeman + transiciones dipolares M1), exactamente como hace NORMOS, en lugar de una tabla fija.
- A 33.0 T pasan de `±0.839 / ±3.084 / ±5.329` a **`±0.840 / ±3.074 / ±5.309` mm/s**. La tabla anterior (`10.657 / 6.167 / 1.677`) era ~0,4 % alta en las líneas externas y no era coherente con los momentos nucleares del propio programa.
- Las tres definiciones duplicadas (núcleo, GUI Tk y módulo de distribución) quedan **unificadas en una única fuente** (`core/constants.py`).

## 🧲 Campo de α-Fe unificado a 33.0 T

- Se elimina la constante interna **32.95 T** (no publicada). Toda la calibración de velocidad/campo usa el valor publicado de α-Fe a temperatura ambiente, **33.0 T (330 kOe)**, en Tk, Qt, modelo discreto y distribución.

## 🔁 Efecto y compatibilidad

- El BHF y las posiciones calculadas se desplazan ≈ **0,4 %** en las líneas externas, ahora consistentes con NORMOS.
- Las sesiones e informes previos se cargan sin cambios; conviene rehacer ajustes finos de calibración.
- Verifica el ZIP con `sha256sums.txt`.
