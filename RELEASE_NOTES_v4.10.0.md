## Fitbauer v4.10.0

### ✨ Nueva funcionalidad: comparación de espectros

- **Archivo → Comparar espectro…**: carga hasta 6 espectros adicionales (`.ws5`, `.adt`, `.csv`, `.dat`) para superponerlos al espectro principal como líneas finas de colores distintos.
- **Archivo → Limpiar comparación**: elimina todos los espectros de comparación.
- Los espectros de comparación aparecen también en la figura Plotly exportable (HTML interactivo).
- Los ADT/WS5 se doblan automáticamente; los CSV se cargan directamente.

### 🐛 Correcciones

- **CWT kernel overflow**: corregido `ValueError: could not broadcast input array from shape (261,) into shape (254,)` en la detección automática de mínimos. El kernel Ricker ahora se clampea correctamente a `(n−1)//2`.
- **Qt.ItemFlag**: corregido `AttributeError` en el diálogo GlobalNeelFitDialog al cargar ficheros para el ajuste en temperatura.
- **fold_and_normalize**: corregido desempaquetado incorrecto al cargar espectros de comparación en formato WS5/ADT.

### 📚 Documentación de ayuda

- **28 → 30 capítulos** en los tres idiomas (ES/EN/FR):
  - Nuevo: «Comparación de espectros» / "Spectrum comparison" / "Comparaison de spectres"
  - Nuevo: «Ajuste global Néel-Arrhenius» / "Global Néel-Arrhenius fit" / "Ajustement global Néel-Arrhenius"
  - Actualizado: «Archivo y web» con soporte de formato CSV de velocidad
  - Actualizado: «Novedades» con entradas v4.9.0 y v4.10.0
