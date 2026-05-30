# Mossbauer v2.2

Release que consolida todos los commits posteriores a v2.1. La versión local del programa pasa a ser `2.2`.

## Resumen

v2.2 se centra en tres frentes: ajuste en serie/CLI reproducible, mejoras de compatibilidad con flujos NORMOS y nuevas herramientas de control del perfil de línea. También incorpora datos de ejemplo, documentación técnica y la primera suite de tests automatizados del proyecto.

## Cambios principales

### Ajuste en serie y CLI

- Nuevo ajuste en serie desde la GUI con warm-start secuencial para analizar colecciones de espectros relacionados.
- Nuevo CLI de ajuste por fichero: combina una plantilla JSON y un espectro para producir resultados JSON reproducibles.
- Plantillas CLI preparadas para α-Fe, magnetita, hematita y siderita.
- Ayuda integrada con capítulo de uso del CLI en español, inglés y francés.

### Perfil de línea, errores y límites físicos

- Ajuste opcional de `σ` en perfiles Voigt desde controles visibles de la interfaz.
- Menú contextual del slider de `σ` para elegir Lorentziana/Voigt y controlar el ajuste de `σ`.
- Errores asimétricos por verosimilitud perfilada.
- Rango de `BHF` ampliado hasta 60 T.
- Soporte de `ΔEQ` negativo en los límites del ajuste.

### Compatibilidad NORMOS y calibración

- Corrección de la detección del punto de plegado (`PFP`).
- Tratamiento más conservador de `Vmax`, incluido el signo del eje, para reproducir calibraciones web/NORMOS con eje invertido.
- Ayuda ampliada sobre `VMAX`, eje de velocidades y criterios de calibración.

### Modelo experimental de espesor

- Corrección opt-in de absorbente grueso/saturación para ajuste discreto.
- Soporte equivalente en el modo de distribución.
- Refinamiento VARPRO de los parámetros `(b, s, C)`.
- Documento técnico `docs/correccion_espesor.*` con la formulación y advertencias de uso.

### Interfaz, gráficos y datos

- Menú de estilos de gráficos: clásico, moderno, publicación y oscuro.
- Eliminación de la caja de cabecera de presets para simplificar el panel.
- Ventana **Acerca de** cerrable con clic.
- Nuevos espectros sintéticos de compuestos de hierro y ejemplos adicionales con ruido reducido.

### Calidad y CI

- Suite inicial de `pytest` para física, plegado, CLI, ajuste por lotes y verosimilitud perfilada.
- Workflow de GitHub Actions para ejecutar tests automáticamente.
- Corrección del cableado del checkbox modular para ajustar `σ`.

## Publicación

Para publicar esta versión en GitHub, crear una release desde el tag `v2.2`. El workflow de assets adjuntará el ZIP de distribución y `sha256sums.txt` automáticamente.
