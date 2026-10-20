# Fitbauer v5.2.5

*[🇬🇧 English notes](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.2.5.md)*

Versión de correcciones. El patrón de líneas del sextete que Fitbauer usaba por
defecto no tenía fuente publicada. Se sustituye por el derivado de los momentos
nucleares, el mismo que usa NORMOS. Con él, Fitbauer y NORMOS dan el mismo
campo hiperfino sin ningún ajuste.

**Las calibraciones y sesiones antiguas siguen funcionando.** Las calibraciones
hechas con versiones anteriores se convierten solas y las sesiones guardadas se
reproducen exactamente. El BHF de una muestra cambia menos de un 0.01 % (unos
0.002 T).

---

## El patrón de líneas del sextete

Desde la v4.0.3, Fitbauer situaba las seis líneas de un sextete a 33 T en
±0.8385 / ±3.0835 / ±5.3285 mm/s, presentadas en el código como «patrón
publicado de α-Fe».

- **No tiene fuente publicada.** Son constantes del software previo del
  laboratorio, donde eran el patrón a 32.95 T. En la v4.0.2 pasaron a ser el
  patrón a 33.0 T.
- **Su forma no corresponde a ningún momento medido.** Su razón entre el
  desdoblamiento del estado excitado y el del fundamental, g1/g0, es 0.5724. La
  medida por Violet y Pipkorn (J. Appl. Phys. 42, 4339, 1971) es 0.5714, la que
  usa NORMOS.
- **El argumento de entonces contra los momentos nucleares era circular.**
  Decía que con ellos «un α-Fe lee 33.12 T», pero venía de reutilizar una
  calibración hecha con el patrón anterior. Con la Vmax calibrada con el mismo
  patrón, cualquier patrón da 33.0 T en el α-Fe.

El nuevo defecto, `"normos"`, sitúa las líneas en ±0.8410 / ±3.0836 / ±5.3261
mm/s a 33 T, comprobado contra el binario de NORMOS a 6·10⁻⁶ mm/s.

El patrón anterior sigue disponible como `"legacy"` (alias `"alpha_fe"`) en
*Ajuste › Opciones avanzadas de ajuste › Convenios* y en la opción
`--sextet-pattern` de las herramientas de línea de comandos, para reproducir
trabajos antiguos.

## Calibraciones y sesiones

- **Las calibraciones guardan el patrón con que se hicieron.** Las locales que
  no lo dicen, de versiones anteriores, se toman como históricas. Fitbauer
  aplica su Vmax convertida (× 0.999623) y lo indica en el panel de calibración
  y en el informe. Al cambiar de patrón en el menú, la calibración se vuelve a
  aplicar convertida.
- **Las calibraciones descargadas de la API web** son VMAX de NORMOS, ya en el
  patrón nuevo, y se aplican tal cual. Solo se convierten las que la API marca
  como `"legacy"`.
- **Los ficheros que traen su propio eje de velocidad** no se tocan.
- **Las sesiones guardadas** sin patrón, o con `"alpha_fe"`, se cargan con el
  histórico y dan los mismos resultados que antes.
- **Las preferencias** de versiones anteriores pasan al nuevo defecto.

Con la calibración convertida, el BHF de una muestra cambia menos de un 0.01 %,
y δ y ΔEQ, un −0.038 %.

## Otras correcciones

- **Los convenios que trae una sesión o un `.JOB` ya no se guardan como
  preferencia.** Solo lo elegido en el menú Convenios pasa a ser el defecto de
  los análisis nuevos. Antes, abrir una sesión antigua y cerrar el programa
  dejaba sus convenios, incluido el patrón histórico, como defecto de todo lo
  que viniera después.
- **Los cuatro espectros «de referencia» de `data_sample/`** (α-Fe, hematita,
  siderita, magnetita) son sintéticos. La documentación ya no los presenta como
  medidas.

## Validación

El banco de validación sintético frente a NORMOS se ha regenerado con el patrón
nuevo: 432 casos, 6520 comparaciones. Ya no necesita un factor de escala para
el campo hiperfino.

| Bloque | Mediana de la diferencia en BHF antes | Ahora |
|---|---|---|
| Núcleo de primer orden | 4·10⁻⁵ T | 6·10⁻⁶ T |
| Textura e intensidades | 2·10⁻³ T | 6·10⁻⁶ T |
| Multisitio y ligaduras | 2·10⁻⁴ T | 1·10⁻⁵ T |
| Hamiltoniano completo | 8·10⁻⁴ T | 1.4·10⁻³ T |

Solo sube el bloque del Hamiltoniano completo, dentro de la aproximación que
hace el propio NORMOS-SITE. Los fallos de criterio bajan de 745 a 711. La
comparación con 146 trabajos reales de NORMOS no cambia.

## Documentación

Al día el capítulo de calibración (`docs/calibracion_33T.md`), la
especificación del modelo de sextete, los manuales de usuario (español e
inglés), la ayuda del programa en 8 idiomas y la wiki.

---

Suite completa: **770 tests en verde**.
