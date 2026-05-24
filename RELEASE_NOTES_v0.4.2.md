# Mössbauer Fe-57 GUI v0.4.2

Patch release sobre v0.4.1 que añade la posibilidad de marcar cualquier espectro cargado localmente como calibración.

## Cambios

- **Nuevo ítem `Archivo → Usar fichero actual como calibración...`**
  Hasta ahora solo era posible asociar una calibración a un espectro si ambos se descargaban desde la API web del laboratorio. Con este cambio, si cargas un `.ws5` o `.adt` que resulta ser un estándar de velocidad (α-Fe u otro), puedes indicárselo directamente al programa.

  El diálogo pide tres campos:
  - **Muestra** — nombre del estándar de velocidad (pre-relleno con el nombre del fichero).
  - **Vmax (mm/s)** — si se indica, se aplica inmediatamente al espectro activo, exactamente igual que cuando la calibración proviene de la API web.
  - **IS (mm/s)** — desplazamiento isomérico del estándar (informativo, sin efecto en el ajuste).

  La calibración queda registrada con `source = "local"` en `calibration_info`. Persiste al guardar y cargar la sesión JSON, y aparece en el panel de información lateral y en el informe Markdown/PDF exportado.

- **Traducciones** del nuevo diálogo y sus mensajes en español, inglés y francés. Nueva clave `button.ok` en los tres catálogos.

- **Ayuda integrada actualizada** en los tres idiomas: sección *Archivo y web* ampliada con la descripción del nuevo flujo; sección *Novedades* con entrada v0.4.2.

## Sin cambios en ajuste ni en formatos de fichero

El comportamiento del ajuste, los formatos WS5/ADT, el protocolo de sesión y la API web no se modifican. Esta release es exclusivamente una mejora de flujo de trabajo.
