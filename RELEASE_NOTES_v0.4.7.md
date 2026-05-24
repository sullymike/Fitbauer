# Mössbauer Fe-57 GUI v0.4.7

Patch release sobre v0.4.6 que automatiza la instalación de dependencias Python.

## Cambios

- **pip automático tras actualizar.**
  Cuando el usuario acepta instalar una actualización descargada, después de descomprimir los ficheros el programa ejecuta automáticamente:
  ```
  pip install -r requirements.txt
  ```
  El resultado (éxito o aviso) se muestra en el mismo mensaje de "cierra y vuelve a abrir el programa".

- **Comprobación silenciosa al arrancar.**
  4 segundos después de abrirse, el programa compara la fecha de modificación de `requirements.txt` con la del último chequeo pip registrado. Si `requirements.txt` es más nuevo (por ejemplo, tras una actualización manual o al primera vez), lanza pip en un hilo de fondo sin interrumpir al usuario. El sello `last_pip_check` se guarda en el directorio de configuración del programa.

## Sin cambios en ajuste ni en formatos

El algoritmo de ajuste, los rangos de parámetros, los formatos de fichero y la API web son los mismos que en v0.4.6.
