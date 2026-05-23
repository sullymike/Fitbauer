# Changelog

## v0.4.1

- El cambio de idioma en caliente es ahora perceptiblemente más rápido: la ventana se oculta durante el destroy/rebuild para que Tk no repinte cada widget intermedio, y se elimina el redraw duplicado de matplotlib que ocurría a mitad de la restauración del estado.

## v0.4.0

- Cobertura completa de traducciones: paneles de control, sextetes, panel de estado y parámetros, ajustes, gráficas, diálogos, mensajes e informe Markdown pasan por `tr()`.
- Reorganización en `locales/<code>/`: cada idioma vive en su propia carpeta con `strings.json` (catálogo GUI) y `help.json` (capítulos de ayuda).
- Auto-descubrimiento de idiomas: añadir una traducción es dejar caer `locales/<code>/` — el menú Idioma lo detecta al arrancar sin tocar código.
- Cambio de idioma en caliente: el menú aplica el idioma sobre la marcha reconstruyendo la UI y conservando el estado (sliders, fijos, sextetes activos, ajuste actual, panel de estado). Ya no hay mensaje de "reinicia para aplicar".
- `mossbauer_help.py` pasa de 1399 líneas a ~50: ahora es un cargador delgado que interpola `voigt_sigma` y la ruta de configuración en los capítulos cargados desde JSON.
- Workflow de release incluye el directorio `locales/` en el ZIP empaquetado.

## v0.3.0

- Release mayor 0.3: consolida documentación bilingüe/trilingüe, capturas en README, propuestas SyncMoss/NORMOS, ayuda ampliada y sistema inicial de internacionalización.
- Versión preparada para distribución pública con interfaz traducible y catálogos actuales en español, inglés y francés.

## v0.2.10

- Añadidos catálogos de interfaz en inglés y francés en `mossbauer_i18n.py`.
- El menú `Idioma` permite seleccionar Español, English o Français; la preferencia se guarda en la configuración y se aplica al reiniciar.
- Añadida ayuda interna en francés y el selector de ayuda ahora permite `es`, `en` y `fr`.

## v0.2.9

- Añadida capa inicial de internacionalización en `mossbauer_i18n.py`, de momento con catálogo español completo para menús principales y ventana de ayuda.
- La GUI empieza a usar claves estables `tr("...")`, preparada para añadir nuevos idiomas sin reescribir la interfaz.
- Añadido menú `Idioma` con Español como idioma disponible inicial.

## v0.2.8

- Añadida documentación inicial en inglés para GitHub: `README_EN.md` e `INSTALL_EN.md`.
- Añadido selector de idioma Español/English en la ventana de ayuda integrada.
- Añadida versión inglesa resumida de la ayuda interna con flujo de trabajo, modelos, distribuciones, estadística, diagnóstico e informes.

## v0.2.7

- Ayuda integrada actualizada con todas las modificaciones desde la v0.2 y nuevo capítulo "Novedades desde v0.2" con cómo se usa cada función (informe Markdown/PDF, bootstrap MC, presets físicos, diagnóstico de residuos, L-curve ampliada, etc.).
- Se documentan los 10 puntos de ajuste/diagnóstico y los 5 puntos adicionales: pesos en distribuciones, bootstrap, presets físicos, folding ajustable e incertidumbre de calibración.
- Capítulos de ayuda Folding, Modelo discreto, P(BHF): parámetros, Diagnóstico, Guardar y exportar y Atajos puestos al día.
- Barra de matplotlib (guardar figura, zoom, coordenadas del cursor) anclada al borde inferior del lienzo: deja de quedar recortada en ventanas bajas o pantallas con escalado HiDPI.

## v0.2.6

- Distribuciones Hesse-Rübartsch ponderadas por incertidumbre Poisson (`sigma`) en P(BHF)/P(ΔEQ) y L-curve.
- Bootstrap Monte Carlo para errores de parámetros en ajustes discretos.
- Presets físicos rápidos: intensidades 3:2:1, anchuras iguales y ligaduras de δ/Γ entre componentes.
- Ajuste opcional del folding point dentro del ajuste.
- Aviso/trazabilidad de incertidumbre de calibración Vmax cuando está disponible.

## v0.2.5

- Ventana de progreso durante ajustes discretos con autoarranques.
- Progreso visible durante escaneo L-curve de α.
- Progreso visible durante ajustes de distribución P(BHF)/P(ΔEQ), incluyendo refinamiento global.

## v0.2.4

- Nueva opción `Archivo → Exportar informe Markdown/PDF...`.
- El informe Markdown resume trazabilidad, calibración, métricas, áreas, parámetros, errores, correlaciones y diagnóstico de residuos.
- Si se solicita PDF, siempre se conserva también el Markdown y el PDF añade una página con la figura actual.

## v0.2.3

- Diagnóstico de residuos: autocorrelación lag-1, test de rachas y correlación antisimétrica para detectar estructura no aleatoria.
- Autoarranque múltiple determinista en ajustes discretos para reducir dependencia de valores iniciales.
- Se mantienen las áreas por integración numérica como método único para Lorentziana/Voigt.

## v0.2.2

- Diagnóstico de selección de modelo reforzado con mensaje explícito para comparar AIC/BIC.
- Matriz de correlación resumida: avisa de parámetros muy correlacionados (|r| ≥ 0.95).
- L-curve de P(BHF)/P(ΔEQ) ampliada: muestra χ² reducido, sugerencia por compromiso y permite guardar la tabla de α.

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
