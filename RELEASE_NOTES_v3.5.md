# Mossbauer v3.5

Release estable. La versión local del programa pasa a ser `3.5`.

## Resumen

v3.5 consolida los cambios incorporados desde v3.0, centrados en la interfaz Qt con gráficos Plotly interactivos, mejoras de rendimiento del trazado y nuevas herramientas de edición semi-manual de mínimos.

## Cambios desde v3.0

### Qt/Plotly interactivo

- Integración de **Plotly** en la GUI Qt para visualizar espectros, ajustes, componentes, fondo, residuos y distribuciones de forma interactiva.
- Navegación más cómoda con zoom, pan, autoscale y herramientas propias del visor Plotly.
- Refresco incremental del gráfico para evitar redibujados completos innecesarios.
- Curva de ajuste densa para representar el modelo con mayor suavidad visual.
- Uso de trazas WebGL en escenarios adecuados para mejorar el rendimiento con espectros grandes.

### Editor semi-manual de mínimos

- Nuevo flujo de revisión de mínimos detectados desde la interfaz Plotly/Qt.
- Posibilidad de inspeccionar y corregir mínimos antes de usarlos para inicializar componentes.
- Mejor control del usuario en casos donde la detección automática necesita supervisión.

### Ayuda y documentación

- Ayuda de los menús Qt ampliada en español.
- `CHANGELOG.md`, `README.md` y `README_EN.md` actualizados para la nueva versión estable.

## Compatibilidad

- Compatible con sesiones, plantillas y datos de v3.0.
- Se mantienen las interfaces Tk y Qt junto con el núcleo de cálculo unificado introducido en v3.0.
