# Mössbauer Fe-57 GUI v0.4.1

Patch release sobre v0.4.0 centrada en la velocidad del cambio de idioma en caliente.

## Cambios

- **Cambio de idioma mucho más rápido.** En v0.4.0 el menú `Idioma` aplicaba el cambio sin reiniciar, pero tardaba bastante porque Tk repintaba cada uno de los ~hundreds de widgets que se destruían y se recreaban (30+ sliders, menubar entero, notebook con 4 pestañas, `FigureCanvasTkAgg`). Ahora la ventana se oculta durante el rebuild y se vuelve a mostrar al final, así Tk acumula la geometría y pinta una sola vez.
- **Sin redraw duplicado de matplotlib.** Durante la restauración del estado tras el cambio de idioma, `on_line_profile_change` disparaba un `update_plot` adicional que se sumaba al `update_plot` explícito del final → dos redraws completos del gráfico por cada cambio. Ahora hay uno solo.

## Sin cambios funcionales

Toda la funcionalidad y los catálogos de traducción de v0.4.0 se mantienen tal cual. Esta release es estrictamente una mejora de rendimiento.
