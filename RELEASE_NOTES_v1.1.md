# Mössbauer Fe-57 GUI v1.1

Patch release sobre v1.0 que arregla el arranque del programa cuando se ejecuta a través de los lanzadores creados por `install.py` o del ejecutable de PyInstaller, y un error visual en el diálogo de actualización.

## Cambios

- **Lanzadores arrancan la UI modular.** `mossbauer`, `mossbauer.bat` y el ejecutable empaquetado apuntan a `mossbauer_fe33_gui_v2IA.py`, que en v1.0 seguía instanciando la clase base `MossbauerFe33GUI` (sin paneles ni layout manager). Ahora el bloque `if __name__ == "__main__"` redirige a `MossbauerApp` con un import diferido (para evitar el ciclo de imports a nivel de módulo).
- **PyInstaller empaqueta los subpaquetes nuevos.** `MossbauerFeFit.spec` declara como `hiddenimports`: `mossbauer_app`, `core` (`constants`, `physics`, `data_io`), `layout` (`manager`, `presets`, `configurator`) y `panels` (`base`, `header`, `file_info`, `info_display`, `calibration`, `reference`, `sim_panel`, `plot_panel`). PyInstaller no sigue automáticamente imports dentro de `__main__` ni siempre detecta subpaquetes nuevos, así que sin esto el `.exe` arrancaba pero faltaban módulos.
- **`install.py` valida también `mossbauer_app.py`.** El smoke test del instalador compila tanto el fichero principal como `mossbauer_app.py` para detectar errores antes de crear los lanzadores.
- **Diálogo de actualización: `grab_set` diferido.** El `Toplevel` del diálogo "Actualización disponible" lanzaba `TclError: grab failed: window not viewable` porque `win.grab_set()` se llamaba antes de que la ventana terminara de mapearse. Ahora se difiere con `after(50, ...)` + `wait_visibility()` y `try/except` por si la ventana se cierra antes.

## Compatibilidad

Sin cambios en el motor de ajuste, formatos de fichero, sesiones JSON, API web ni catálogos de traducción. Las sesiones de v0.4.x / v1.0 se cargan sin cambios.
