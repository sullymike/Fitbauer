# Mössbauer Fe-57 GUI v0.4.0

Versión centrada en la cobertura completa de traducciones y en hacer el cambio de idioma trivial — tanto para el usuario (en caliente) como para añadir nuevas lenguas.

## Novedades principales

- **Toda la GUI traducida.** Paneles "Fichero actual", "Estado y parámetros", "Velocidad, folding y fondo", "Referencia" y "Simulación / ajuste"; pestañas de componentes (sextete/doblete/singlete) con todos sus sliders (δ, ΔEQ, BHF, Γ 1,6 / 2,5 rel / 3,4 rel, profundidad, intensidades); pestaña de distribución P(BHF)/P(ΔEQ) con sus controles; botones de ajuste; el contenido entero del panel "Estado y parámetros" (métricas, diagnóstico de residuo, correlaciones, áreas por componente, restricciones); ejes/leyendas/títulos de las gráficas; todos los diálogos (web, Ollama, presets físicos, restricciones, L-curve, bootstrap MC, exportar informe, guardar/cargar sesión); y el informe Markdown/PDF.
- **Idiomas en `locales/<code>/`.** Cada idioma vive ahora en su propia carpeta con dos ficheros: `strings.json` para el catálogo de la interfaz y `help.json` para los capítulos de ayuda. Añadir una traducción es dejar caer un nuevo `locales/<code>/` y reiniciar el programa — el menú Idioma lo detecta automáticamente.
- **Cambio de idioma sin reiniciar.** El menú Idioma aplica el cambio al instante reconstruyendo la interfaz; se preservan los valores de los sliders, los checkboxes de "fijo", los sextetes activos, el modo de ajuste, las restricciones, el ajuste actual y el contenido del panel de estado.
- **`mossbauer_help.py` reducido a un cargador delgado.** De 1399 líneas con tres funciones casi paralelas a ~50 que cargan el JSON del idioma activo e interpolan `voigt_sigma` y la ruta de configuración.

## Bajo el capó

- `mossbauer_i18n.py` ahora descubre dinámicamente los idiomas escaneando `locales/*/strings.json`. Cada catálogo expone `_meta.name` como nombre visible en el menú Idioma.
- Las claves no presentes en el idioma activo caen al idioma por defecto (español), así que una traducción parcial sigue siendo utilizable.
- Los valores internos de enumeración (`Sextete`/`Doblete`/`Singlete`, `Histograma`/`Gaussiana`/`Binomial`/`Fija`, `BHF`/`ΔEQ`, `Lorentziana`/`Voigt`) se conservan en español por compatibilidad con sesiones guardadas; su **display** se traduce vía claves `kind.*` y `shape.*`.
- `load_settings` se ha partido en una capa fina sobre disco y un `_apply_state_payload(dict)` reutilizable, que es lo que usa el cambio de idioma en caliente para restaurar el estado tras reconstruir la UI.
- 430 claves de traducción por idioma (es/en/fr), con paridad verificada.
- El workflow de release ahora empaqueta el directorio `locales/` en el ZIP distribuido.

## Cómo añadir un idioma

1. Copiar `locales/es/` a `locales/<código>/`.
2. Traducir los valores en `strings.json` y `help.json` (manteniendo las claves).
3. Cambiar `_meta.name` en `strings.json` por el nombre del idioma en su propio idioma.
4. Reiniciar el programa: el menú Idioma incluirá la nueva opción.

Las claves faltantes recaen sobre el catálogo español, así que se puede empezar por traducir lo más visible y completar después.
