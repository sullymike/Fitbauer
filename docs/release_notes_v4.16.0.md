# Fitbauer v4.16.0

Reúne todo lo acumulado desde la última release publicada (`v4.14.2`): renombrado del
repositorio, paridad completa GUI ↔ línea de comandos, unificación de la física y
correcciones de la auditoría. (`v4.14.3` y `v4.15.0` no se publicaron por separado.)

## Renombrado del repositorio a Fitbauer
- El repo de GitHub pasa de `Mossbauer` a **`Fitbauer`**. Actualizadas todas las
  referencias codificadas al slug → `sullymike/Fitbauer`: actualizador (`GITHUB_REPO`,
  API/atom/releases/descargas), enlace del manual EN (`gui/help.py`) y documentación
  (`INSTALL_EN.md`, artículos y paper). GitHub mantiene la redirección desde el nombre
  antiguo, pero ya no dependemos de ella.

## CLI: paridad completa con la GUI (v4.15.0)
- **`fit_bhf_distribution_cli.py`**: motor de distribución completo — `--variable quad`
  (P(ΔEQ) con `--fixed-bhf`), `--shape histograma|gaussiana|vbf|binomial`
  (+`--vbf-components`), `--reg-mode tikhonov|tv|maxent`, `--profile Voigt`
  (+`--voigt-sigma`), correlaciones `--delta-slope`/`--quad-slope`, distribución 2D
  `--dist-2d` y `--scan-alpha` coherente.
- **`mossbauer_fit_cli.py`**: `--bootstrap N`, `--profile-likelihood` (1σ/2σ por Δχ²) y
  serie con warm-start secuencial (varios `--spectrum`).
- Manual EN: nuevo apéndice «Command-line tools (headless fitting)»;
  `BHF_DISTRIBUTION.md` actualizado; tests en `tests/test_cli_extended.py`.

## Correcciones (auditoría, v4.15.0)
- **«Ajustar centro» era un no-op en modo triangular**: ahora recorta bordes
  simétricamente y el centro se ajusta de verdad.
- **Bootstrap y verosimilitud perfilada** no propagaban `norm_factor` → σ e intervalos
  sesgados en modo Poisson. Corregido.
- **CLI**: la plantilla se aplica antes de cargar el espectro (`drive_form="sine"` dobla bien).
- El diálogo de bootstrap respeta el idioma de la interfaz.

## Física unificada (fuente única, v4.15.0)
- Perfiles de absorción de `mossbauer_distribution.py` ahora son adaptadores finos sobre
  primitivos de `core/physics.py`. Equivalencia garantizada por 21 tests (atol 1e-12),
  salida del CLI idéntica bit a bit.
- `mossbauer_ws5.py` reexporta de `core.folding`; persistencia de `settings.json`
  centralizada en `core/data_io.py`. Retirado `fold_mossbauer.py` (legacy).

## Ayuda y menús (v4.15.0)
- Ayuda in-app (7 idiomas): retirados los restos de Plotly/QtWebEngine y documentadas las
  acciones que faltaban («Mostrar área de componentes», «Límites de parámetros…»,
  «Manual (PDF)»).
- «Manual (PDF)» entra en el registro de atajos configurables.

## Instalador (v4.14.3)
- `install.py` **registra Fitbauer en los menús del sistema** (por-usuario, sin admin):
  `.desktop` + icono en Linux, acceso directo en el menú Inicio en Windows.
