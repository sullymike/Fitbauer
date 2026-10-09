# Fitbauer v5.1.1

*[🇬🇧 Release notes in English](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.1.1.md)*

Versión de corrección de errores sobre la 5.1.0.

---

## El gráfico ya no se queda congelado tras un zoom

Después de hacer zoom o desplazar con la barra del gráfico, los espectros que se
cargaban a continuación podían dibujarse fuera de la zona visible: el gráfico
parecía congelado y daba la impresión de no mostrar los datos nuevos. El zoom
desactiva el autoescalado de Matplotlib y el refresco rápido reutilizaba los
límites antiguos para cualquier espectro con el mismo número de canales. Tras
hacer zoom sobre α-Fe, de un espectro de hematita se veía el 7 % de los puntos y
de uno de magnetita, el 20 %.

Ahora, al cargar otro espectro se reactiva el autoescalado y se reinicia el
historial de vistas de la barra, así que **Inicio** lleva al espectro nuevo. Si
solo cambia el modelo (sliders, ajuste), se conserva tu zoom.

## Las restricciones entre parámetros usan los nombres del panel

**Ajuste ▸ Restricciones entre parámetros** listaba todas las claves internas
(`s1_delta`, …) de todos los componentes, incluidos los desactivados y los
parámetros que la forma elegida no usa. Ahora ofrece solo lo que se ve en el
cuadro de simulación y ajuste, con las mismas etiquetas («Componente 1 · δ
isomérico»). Las sesiones no se ven afectadas: las restricciones se siguen
guardando por clave, y una restricción existente sobre un parámetro que ya no se
muestra se conserva. Las cabeceras están traducidas y el nuevo valor del
parámetro destino aparece en el panel nada más pulsar OK.
