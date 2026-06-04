# Fitbauer v4.0.3

Corrige una **regresión de calibración** introducida en v4.0.2.

## 🛠️ Corrección del BHF

- En v4.0.2 las posiciones del sextete se derivaban de los momentos nucleares de libro; eso daba un desdoblamiento ~0,4 % menor (línea externa 5.309 vs 5.328 mm/s a 33 T) y **sesgaba el campo hiperfino ~0,1 T hacia arriba** (un α-Fe leía 33.12 T).
- Se vuelve al **patrón de velocidad publicado de α-Fe** (`±0.839 / ±3.084 / ±5.329 mm/s` a 33 T): un espectro de **α-Fe ajusta a 33.0 T exacto, igual que NORMOS**.
- Documentado en el código para no reintroducir el sesgo.

## ⚠️ Recomendación

Si analizaste algo con **v4.0.2**, revisa los valores de BHF: salían ~0,1 T altos. Con v4.0.3 vuelven a ser correctos.

## 🔁 Compatibilidad

- Sesiones e informes se cargan sin cambios.
- Verifica el ZIP con `sha256sums.txt`.
