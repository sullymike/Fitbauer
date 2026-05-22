# Changelog

## v0.2.1

- Ajuste discreto ponderado por incertidumbre Poisson de las cuentas dobladas.
- Se muestran χ² reducido, AIC y BIC para comparar modelos.
- Porcentajes de área calculados por integración numérica del perfil real, consistente con Lorentziana y Voigt.

## v0.2.0

- Limpieza del repositorio: queda una única GUI oficial, `mossbauer_fe33_gui_v2IA.py`.
- Instalador y releases simplificados para usar solo el lanzador `mossbauer` / `mossbauer.bat`.
- Workflow de release actualizado para empaquetar solo la versión completa.

## v0.1.7

- Tema visual moderno basado en `sv_ttk` (Sun Valley); aspecto limpio con sliders y checkboxes estilo Windows 11.
- Selector de tema en `Opciones → Tema visual`: alterna entre "Moderno (sv_ttk)" y "Clásico (clam)"; la elección se guarda en ajustes.
- Workflow de GitHub Actions que genera automáticamente el ZIP del programa y `sha256sums.txt` al publicar una release.

## v0.1.6

- Ayuda, actualizador y cliente API extraídos a módulos independientes (`mossbauer_help.py`, `mossbauer_updater_ui.py`).
- Los textos de ayuda documentan el token en `credentials.json`, el bloque `"calibration"` en el JSON de sesión y el aviso de desajuste de Vmax al cargar sesión.
- La variante `mossbauer_fe33_gui_v2IA.py` queda migrada también al cliente REST del laboratorio.
- Sincronización de versión estable tras los cambios remotos del servidor.

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
