# Changelog

## v0.1.5

- La descarga y subida web usan la API REST oficial del laboratorio (`/api/v1/`) en lugar de scraping de HTML.
- Autenticación por token: usuario y contraseña se piden una vez; el token se guarda y se reutiliza.
- Al descargar una medida puede descargarse también su calibración asociada y aplicarse su Vmax automáticamente.
- La sesión JSON guarda un bloque `calibration` con la trazabilidad de la calibración usada.
- Buscar la medida por nombre de fichero es ahora una sola llamada a la API.
- Nuevo módulo `mossbauer_api_client.py` con el cliente reutilizable de la API.
- La misma migración se aplica a la variante `mossbauer_fe33_gui_v2IA.py`.

## v0.1.4-beta.2

- Corregida la comparación de versiones beta para que no avise de la misma versión ya instalada.
- La versión se muestra dentro de la ventana `Acerca de`.

## v0.1.4

- El actualizador puede instalar automáticamente ZIPs de GitHub en la misma carpeta del programa.
- Tras instalar una actualización solo hay que cerrar y volver a abrir el programa.
- Se crea copia de seguridad de ficheros sobrescritos en `.update_backup`.

## v0.1.3

- El actualizador puede comprobar solo releases estables o también prereleases/betas.
- Nueva opción `Ayuda → Configurar actualizaciones...`.

## v0.1.2

- La descarga web permite elegir carpeta destino y crear subcarpetas.
- Carpetas separadas recordables para medidas y calibraciones.
- Las descargas se guardan directamente en la carpeta seleccionada con el nombre real de la web.

## v0.1.1

- Instalador Python (`install.py`) para Linux/Windows sin necesidad de `.exe`.
- Comprobación de actualizaciones desde GitHub Releases.
- Subida de sesiones JSON a la web en la entrada con el mismo fichero de datos.
- Campo de nota al subir análisis web.

## Versión inicial

- Soporte para ficheros WS5 y ADT antiguos sin cabecera.
- Descarga desde web con nombre real de fichero y extensión real `.ws5`/`.adt`.
- Buscador en la carga de datos web.
- Folding point fraccionario compatible con la interpolación tipo Normos.
- Ajuste discreto con singlete, doblete y sextete.
- Ajuste con distribución regularizada `P(BHF)`.
- Componentes nítidos combinables con `P(BHF)`.
- Porcentajes de área por componente y errores aproximados.
- Guardado/carga de sesión completa.
- Opciones persistentes.
- Ayuda por capítulos.

## Notas

El programa sigue en desarrollo. Conviene revisar siempre residuos, estabilidad de parámetros y sentido físico de los resultados.
