# Fitbauer v4.1.0

Versión mayor de limpieza: la aplicación pasa a tener **una sola interfaz gráfica (Qt)** y la lógica de orquestación del ajuste se extrae a una **capa headless en `core/`**, sin dependencia de ninguna GUI.

## Interfaz única Qt

- **Se elimina por completo la interfaz Tk.** La aplicación tiene ahora una sola interfaz gráfica, la Qt (`mossbauer_qt.py`). Se retiran el monolito `mossbauer_fe33_gui_v2IA.py`, `mossbauer_app.py`, el paquete `panels/`, el gestor/configurador Tk de `layout/`, el diálogo Tk de actualizaciones (`mossbauer_updater_ui.py`), `Fitbauer-Tk.spec` y la dependencia `sv_ttk`.
- **Lanzador simplificado.** `fitbauer.py` arranca directamente la interfaz Qt (sin opciones `--tk` / `--qt` ni respaldo Tk).

## Capa de ajuste headless en `core/`

- La orquestación **cargar → doblar → ajustar → sesión** que antes vivía en la app Tk se extrae a `core.session` (`ModelState` + `HeadlessSession`), sin dependencia de ninguna GUI y reusando `core.fit_engine` / `core.folding`.
- El CLI `mossbauer_fit_cli.py` ya no necesita display ni Tk.
- **Funciones de actualización sin GUI** (`load/save_update_settings`, `check_requirements_if_needed`, refresco de dependencias pip) trasladadas de `mossbauer_updater_ui.py` a `mossbauer_updater.py`.

## Notas

- La física y el ajuste siguen viviendo en `core/`; la GUI Qt y los CLIs son clientes finos de ese núcleo.
- El dibujo de subespectros en modo distribución + nítidos (introducido en v4.0.4) se mantiene en la interfaz Qt.
