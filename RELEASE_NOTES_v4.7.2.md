# Release Notes v4.7.2 — Fitbauer

Versión de mantenimiento: revisión completa del código en busca de fallos latentes, sin nuevas funcionalidades. Corrige errores que afectaban a acciones concretas de la GUI, a la coherencia del ajuste por lotes y a la internacionalización, además de varias mejoras de robustez.

## Bugs corregidos

- **Cargar P fija fallaba siempre.** La acción «Cargar P fija» del modo distribución lanzaba `NameError` por un import ausente en `gui/distribution_fit.py`.
- **Diálogos web siempre en español.** Los diálogos de descarga de medidas/calibraciones ignoraban las traducciones EN/FR existentes por una comprobación que nunca se cumplía; ahora respetan el idioma de la interfaz.
- **Coherencia batch ↔ ajuste individual.** El diálogo de lote doblaba el espectro sin el recorte de canales de borde que aplica el flujo principal, y reutilizaba las cuentas crudas del espectro cargado en la ventana en lugar de las de cada fichero (afectaba al re-folding de `fit_center` y a la σ Poisson). Ahora el batch usa exactamente el mismo doblado y eje de velocidad que la GUI y la capa headless. *Los resultados de batch pueden variar ligeramente respecto a series antiguas; a cambio, batch e individual ahora coinciden.*
- **Fuente única de folding.** `core/data_io.py` mantenía copias antiguas de las funciones de lectura/folding que habían divergido de `core/folding.py` (heurística del folding point Normos y normalización del área ARE); ahora reexporta las canónicas.
- **Motor de ajuste.** Corregida una desalineación latente del vector de parámetros cuando se activaba el ajuste de `vmax`/`center`/`σ Voigt` sin la clave correspondiente en el estado.

## Internacionalización

- Todo el flujo de actualizaciones (configurar canal, buscar, descargar, instalar) está ahora traducido a ES/EN/FR (31 claves nuevas en los catálogos).

## Robustez

- El actualizador borra las descargas parciales si la conexión falla a medias.
- Limpieza de código muerto, imports redundantes y comentarios/docstrings desactualizados (referencias a la GUI Tk eliminada, convención de calibración de `LINE_POS_33T`).

## Verificación

Suite completa de tests en verde (142 tests, incluido el golden test headless: el núcleo de ajuste no cambia de resultados). Detalle completo de cambios en `CHANGELOG.md`.
