# Fitbauer v4.17.2

## Caza de bugs multi-agente II — 21 correcciones

Segunda auditoría con cuatro revisores independientes sobre E/S de datos y
folding, distribución, sesiones/estado y CLIs+i18n. Cada hallazgo se reprodujo
con un script antes de corregirlo y se verificó después del arreglo.

### E/S y folding

- La búsqueda del centro de doblado usaba una ventana fija 250.5–262.5 (válida
  solo para 512 canales) en la GUI y en los CLIs de distribución: con 256 o
  1024 canales el centro era absurdo. Ahora deriva de N (N/2 ± 20).
- El χ² de simetría del detector de centro usa la misma interpolación subcanal
  que el folding, normaliza por pares realmente evaluados y excluye los
  canales de borde: el modo seno con absorción ≤1 % ya no se desvía hasta 50
  canales y un canal 1 muerto (habitual en ADT reales) ya no sesga el centro.
- `.PLT` de NORMOS con títulos con dígitos (`Fe3O4`, `T=300K`) ya no envenenan
  vmax; los CSV con decimales de coma (locale es_ES) cargan correctamente; un
  WS5 truncado ya no traga números de la cabecera XML; los CLIs de
  distribución aplican el mismo recorte de bordes que la GUI.

### Distribución

- Los componentes nítidos Relajación/Blume-Tjon/Néel se ajustaban con un
  patrón de líneas erróneo ([3, 4, 1] en vez de [3, 2, 1]); el subespectro
  dibujado coincide ahora exactamente con el ajustado.
- Gaussiana/VBF/Binomial/Fija respetan baseline/slope fijados (GUI y
  `--no-fit-baseline`/`--no-fit-slope` del CLI, que se ignoraban en silencio).
- Binomial y Fija ya no heredan el perfil de línea de un ajuste discreto
  anterior; la L-curve en modo P(IS) escanea la variable correcta.

### Sesiones

- Las sesiones antiguas (incluidas las 4 de ejemplo del repo) vuelven a
  cargar; los ajustes del panel de distribución guardados en formato legacy se
  restauran; una sesión de espectro CSV se restaura por el lector correcto;
  multistart = 0 sobrevive al reinicio.

### CLIs e i18n

- `--out` ya no puede sobrescribir la plantilla o el espectro de entrada;
  `--scan-alpha` con formas paramétricas falla antes de ajustar; 10 claves de
  traducción que faltaban en todos los idiomas están ahora en los 7 locales
  (con test de paridad de claves).

Suite completa: **310 tests en verde** (21 de regresión nuevos).
Detalle completo por bug en `CHANGELOG.md`.
