# Mossbauer v3.0

Release **mayor**. La versión local del programa pasa a ser `3.0`.

## Resumen

v3.0 añade una segunda interfaz gráfica, **Qt (PySide6)**, junto a la GUI Tk
clásica, y unifica todo el cálculo en el paquete `core/`. La física, el motor de
ajuste, el bootstrap y la verosimilitud perfilada existen ahora una sola vez y
los comparten **GUI Tk, GUI Qt, CLI y ajuste en serie**.

## Cambios principales

### Interfaces y empaquetado

- Nueva **GUI Qt (PySide6)** con la misma funcionalidad de ajuste sobre el núcleo común.
- **Dos ejecutables** independientes:
  - Tk: `pyinstaller MossbauerFeFit.spec` · lanzadores `mossbauer` / `mossbauer.bat`.
  - Qt: `pyinstaller MossbauerFeFit-Qt.spec` · lanzadores `mossbauer-qt` / `mossbauer-qt.bat`.
- Informe (Qt) con tabla de parámetros `valor ± σ`, origen de la incertidumbre
  (covarianza o bootstrap), bondad de ajuste (χ²ᵣ/χ²/AIC/BIC) y parejas de
  parámetros muy correlacionadas.

### Núcleo de cálculo unificado (`core/`)

- Física del modelo única en `core.physics`; la GUI Tk la reutiliza (sin duplicar).
- Motor de ajuste único en `core.fit_engine`, usado por Tk, Qt, CLI y batch:
  - multistart determinista + optimización global (`differential_evolution`) +
    pérdida robusta (`soft_l1`/`huber`/`cauchy`) + covarianza/correlaciones.
  - re-folding del centro, σ de calibración (sensibilidad a la escala Vmax) y σ
    Poisson correcta.
  - modo textura (intensidades derivadas) y restricciones encadenadas.
  - bootstrap (remuestreo Poisson) y verosimilitud perfilada como funciones puras.
- Eliminada la duplicación del optimizador en la GUI Tk (delega en el núcleo).

### Calidad

- La integración continua ejecuta la **suite completa** —incluidas las GUIs Tk y
  Qt, el CLI y el ajuste en serie— de forma headless (Xvfb + Qt `offscreen`).

## Compatibilidad

- Sesiones, plantillas y datos siguen siendo compatibles con v2.x.
- Ambas interfaces leen y escriben los mismos formatos.
