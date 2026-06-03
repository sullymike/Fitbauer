# Mossbauer v3.6

Release estable. La versión local del programa pasa a `3.6`.

## Cambios principales desde v3.5

### Plotly / Qt

- Corregida la pestaña Plotly cuando quedaba en blanco, sin datos ni ejes. El HTML interactivo se carga ahora desde un fichero local temporal para evitar límites de tamaño de `QWebEngineView.setHtml()` con `plotly.js` embebido.
- Eliminado el bloque de metadatos bajo la figura Plotly.
- Mejorada la edición semi-manual de mínimos:
  - botón visible en la pestaña Plotly;
  - clic en el espectro para añadir un mínimo;
  - clic sobre o cerca de un marcador para activarlo/desactivarlo;
  - sincronización con la lista lateral.

### Web / API MATELEC

- Corregido el error `iter_medidas() got an unexpected keyword argument 'limit'`.
- El listado web de medidas/calibraciones muestra columnas más útiles: id, fichero abreviado, muestra, fecha, temperatura, velocidad display e id de calibración asociada.
- La velocidad del listado usa `velocity_input` como velocidad display.

## Compatibilidad

- Compatible con sesiones, plantillas y datos de v3.x.
- Mantiene las interfaces Tk y Qt/Plotly.
