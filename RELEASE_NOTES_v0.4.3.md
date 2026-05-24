# Mössbauer Fe-57 GUI v0.4.3

Patch release sobre v0.4.2 que mejora la visibilidad de la calibración activa y facilita la entrada de parámetros en el diálogo de calibración local.

## Cambios

- **Label de calibración activa en el panel de fichero.**
  Aparece justo debajo del nombre del espectro cargado, en color azul-teal, mostrando en dos líneas:
  ```
  Calibración [local]:  NombreMuestra
  Vmax: 3.9443 mm/s   IS: −0.100 mm/s
  ```
  Funciona tanto para calibraciones descargadas de la web como para las marcadas manualmente como locales. Se oculta automáticamente al cargar un fichero nuevo y reaparece al restaurar una sesión que tenga calibración asociada.

- **Pre-relleno automático del diálogo de calibración local.**
  Al abrir `Archivo → Usar fichero actual como calibración...`, los campos se rellenan con los valores de la sesión actual:
  - **Vmax** → valor actual del slider de velocidad.
  - **IS** → valor de δ del primer sextete activo.
  Permite confirmar con un solo clic si el ajuste ya está hecho, o editar los valores antes de aceptar.

## Sin cambios en ajuste ni en formatos de fichero

El comportamiento del ajuste, los formatos WS5/ADT, el protocolo de sesión y la API web no se modifican.
