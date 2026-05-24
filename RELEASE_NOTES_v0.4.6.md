# Mössbauer Fe-57 GUI v0.4.6

Patch release sobre v0.4.5 que añade datos de ejemplo y mejoras menores de usabilidad.

## Cambios

- **Datos de ejemplo incluidos en el ZIP.**
  La carpeta `data_sample/` contiene dos espectros listos para abrir y explorar:
  - `calibration.adt` + `calibration_session.json` — espectro de calibración α-Fe con sesión de ajuste ya hecha.
  - `Fe3O4.adt` + `Fe3O4_session.json` — espectro de magnetita (Fe₃O₄) con sesión de ajuste ya hecha.

  Para usarlos: abre primero el `.adt` con **Archivo → Cargar...** y después carga la sesión correspondiente con **Archivo → Cargar sesión...**.

- **Filtro de ficheros ampliado a mayúsculas.**
  El diálogo de apertura acepta ahora `*.WS5` y `*.ADT` además de `*.ws5` y `*.adt`, útil en sistemas Windows donde los ficheros pueden tener extensiones en mayúsculas.

## Sin cambios en ajuste ni en formatos

El algoritmo de ajuste, los rangos de parámetros y la API web son los mismos que en v0.4.5.
