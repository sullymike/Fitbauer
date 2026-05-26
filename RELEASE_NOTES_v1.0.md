# Mössbauer Fe-57 GUI v1.0

Primera versión mayor: refactor completo a una arquitectura modular de paneles, layout configurable por el usuario y un nuevo tema oscuro. Es el resultado de la rama `v1-approach`, que reorganiza la UI de fondo sin tocar el motor de ajuste.

## Novedades principales

- **Arquitectura modular de paneles (`LayoutManager`).** La GUI ya no es un único bloque monolítico: cada panel (cabecera, fichero actual, información/resultados, calibración, líneas de referencia, controles de simulación/ajuste y gráfica) vive en su propio módulo bajo `panels/`, hereda de `BasePanel` y se ensambla en tiempo de ejecución por un gestor de layout de 3 columnas (izquierda · centro=gráfica · derecha).
- **Layout configurable y persistente.** Cuatro presets integrados (Estándar, Compacto, Expandido, Laboratorio) y dos slots de usuario (`Usuario 1` / `Usuario 2`) guardables y persistentes entre sesiones. Un configurador (menú **Vista → Configurar layout**) permite arrastrar paneles entre las listas de disponibles y asignados por columna. La configuración se guarda en `CONFIG_DIR/layout.json` y los presets de usuario en `user_presets.json`.
- **Distribución BHF con espacio real.** El toggle de la distribución P(BHF) ya libera espacio vertical de verdad al desactivarse, y se apila junto a los componentes cuando hay altura suficiente o pasa a pestañas cuando la ventana es baja. El modo se decide midiendo la altura disponible en tiempo real.
- **Convención NORMOS para sextetes.** Intensidades relativas independientes `I`, `I₂₃`, `I₁₃` en lugar de un ratio fijo, con defaults `3 / 2 / 1` en la auto-estimación desde mínimos. Los sliders del panel del sextete se han reordenado: profundidad · intensidad · δ | EQ · BHF · Γ.
- **Reorganización de menús en 4 grupos.**
  - **Archivo**: abrir, submenú Web (medidas / calibraciones / subir), calibración, guardar, exportar, sesión, salir.
  - **Ajuste**: ejecutar ajuste, buscar centro, inicializar, auto, IA, bootstrap; modos Discreto / P(BHF); perfil de línea; opciones agudo/refinar; liberar/fijar; restricciones; presets físicos.
  - **Vista**: residuo, leyenda, submenú Tema (3 opciones), submenú Idioma, Configurar layout.
  - **Ayuda**: sin cambios.
- **Tres temas visuales.**
  - **Moderno** (sv_ttk light): el tema predeterminado, paleta azul/celeste.
  - **Oscuro** (sv_ttk dark + Catppuccin Mocha): base sv_ttk dark con overrides quirúrgicos sobre `TLabelframe.Label`, pestañas, botones y widgets `tk` no-ttk; acento mauve `#cba6f7`, fondo `#1c1c1e`, tarjeta `#2a2a2a`.
  - **Clásico** (clam): tema Tk nativo limpio.
- **Gráfica que respeta el tema.** Un nuevo helper `_plot_theme()` devuelve los colores activos y se aplica al inicio de cada `update_plot()` / `update_plot_bhf_distribution()`, tanto en la clase base como en el override de `mossbauer_app.py`. Esto evita que la gráfica vuelva a fondo blanco al cargar datos o reconstruir la UI. La toolbar de matplotlib usa fondo gris claro (`#d4d4d4`) en tema oscuro para que los iconos PNG (negros) sigan siendo legibles.
- **Diálogo de actualización mejorado.** Cuando hay nueva versión, se muestra un `Toplevel` 860×480 con `Text` + scrollbar (sin truncar el changelog) y botones "Sí, descargar ahora" / "No por ahora" con estilos coherentes.
- **Ventana de texto ampliada.** `show_text_window()` ahora abre a 940×660 (antes ~700×500) con tamaño de fuente 9.

## Bajo el capó

- Nueva carpeta `core/` con `constants.py`, `physics.py` y `data_io.py` aislando la lógica no-UI.
- `layout/` contiene `manager.py` (ensamblado de la GUI), `presets.py` (definiciones de layout) y `configurator.py` (diálogo del configurador).
- `panels/` agrupa los seis paneles configurables (`header`, `file_info`, `info_display`, `calibration`, `reference`, `sim_panel`, `plot_panel`) más `base.py`.
- Los paneles esenciales (`calibration`, `sim_controls`, `info_display`) se construyen siempre, aunque no estén asignados a una columna visible, para que sus `tk.Variable` existan y el modelo de ajuste no se rompa.
- `_reconfigure_styles()` tiene tres ramas (dark / sv_ttk light / clam). En la rama oscura se configura `TLabelframe.Label` además de su variante `Section.*` para evitar la herencia azul de sv_ttk en los títulos de los `LabelFrame`.
- `layout/manager.py.rebuild()` re-aplica el tema tras reconstruir la UI porque la nueva figura de matplotlib se crea con su propio facecolor por defecto.
- `_theme_var` ahora preserva el valor `"sv_ttk_dark"` al reabrir el programa (antes se sobreescribía por `"sv_ttk"`).

## Correcciones

- `TclError` en `comp_area` sin pack al mostrar la distribución BHF.
- Guard en `update_info` cuando `self.info` no existe (por configuraciones de layout que excluyen el panel).
- Presets de usuario aparecen primero en el configurador.
- `i1_real` incluido en el display de información de resultados.
- Límites de pendiente ampliados para espectros con fondo no plano.
- Recorte del primer y último punto del plegado para corregir la pendiente residual.

## Compatibilidad

El motor de ajuste, los formatos de fichero (.adt, sesiones .json), la API web y los catálogos de traducción son compatibles con v0.4.x. Las sesiones guardadas se cargan sin cambios; el layout y el tema se restauran si existen en disco, o se crean con valores por defecto si es la primera vez.
