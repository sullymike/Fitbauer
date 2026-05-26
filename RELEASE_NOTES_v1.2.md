# Mössbauer Fe-57 GUI v1.2

Patch release sobre v1.1 que completa el paquete ZIP de release: ahora incluye los nuevos módulos introducidos en v1.0 y los lanzadores del programa, de modo que una actualización vía ZIP deja la instalación lista para ejecutar sin volver a correr `install.py`.

## Cambios

- **El ZIP de release incluye los nuevos módulos.** El workflow `release_assets.yml` empaqueta ahora `mossbauer_app.py`, los subpaquetes `core/` (constantes, físicas, IO), `layout/` (manager, presets, configurador) y `panels/` (los 6 paneles configurables + `plot_panel` y `base`). Sin esto, una actualización ZIP sobre una instalación v0.4.x fallaba con `ImportError: No module named 'mossbauer_app'` al arrancar.
- **Lanzadores incluidos en el ZIP.** Se han añadido `mossbauer` (shell, Linux/macOS) y `mossbauer.bat` (Windows) directamente al repositorio. Ambos son portables: calculan su propio directorio en tiempo de ejecución (`$DIR` / `%DIR%`) y lanzan `python mossbauer_fe33_gui_v2IA.py`, así que se pueden distribuir tal cual y sustituyen al lanzador anterior tras una actualización ZIP.
- **`install_zip_update()` restaura el bit ejecutable.** `zipfile.extractall` de Python no preserva permisos Unix, así que el lanzador `mossbauer` quedaba sin `+x` tras una actualización. Ahora el actualizador hace `chmod +x mossbauer` tras descomprimir.

## Compatibilidad

Sin cambios en el motor de ajuste, formatos de fichero, sesiones JSON, API web ni traducciones. Las sesiones v0.4.x / v1.0 / v1.1 se cargan sin cambios.

Si vienes de v0.4.x y la actualización automática falló por `ImportError`, el ZIP de esta versión instala correctamente sobre tu carpeta. Tras la actualización, ejecuta:

- Linux/macOS: `./mossbauer`
- Windows: doble click en `mossbauer.bat`
