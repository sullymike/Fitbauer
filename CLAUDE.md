# CLAUDE.md

Guía de orientación para Claude Code en este repositorio. Pensada para que cualquier
sesión (web o VS Code) arranque con contexto sin tener que re-descubrir la arquitectura.

## Qué es

**Fitbauer** — *Software for Mössbauer spectrum fitting and analysis*. Aplicación de
escritorio para cargar, doblar (fold), simular y ajustar espectros Mössbauer de Fe-57.
Autor: Jorge Sánchez Marcos (Dpto. de Química Física · UAM). Idiomas: ES/EN/FR.

## Arranque y desarrollo

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # para los tests
python fitbauer.py                   # abre la GUI Qt
```

- **Una sola GUI: Qt (PySide6 + Plotly).** La antigua interfaz Tk fue **eliminada por
  completo**; no la reintroduzcas. Si ves referencias a `mossbauer_app.py`,
  `mossbauer_fe33_gui_v2IA.py`, `panels/`, `sv_ttk` o un fallback Tk, son obsoletas.
- Python objetivo: 3.11+ (CI usa 3.12).

## Arquitectura (lo más importante)

El cálculo vive en **`core/`** y NO depende de ninguna GUI. La GUI Qt y los CLIs son
clientes finos de `core/`. **Regla de oro: la física/ajuste va en `core/`, nunca dentro
del código de la GUI.**

### `core/` — núcleo puro (sin Tk/Qt)
- `constants.py` — constantes físicas + metadatos (`APP_VERSION` está aquí).
- `physics.py` — funciones puras de física Mössbauer (forma de línea, absorción de componentes).
- `hamiltonian.py` — tratamiento Kündig del Hamiltoniano magnético+cuadrupolar.
- `params.py` — registro único de parámetros del modelo (nombres canónicos, p.ej. `SEXTET_PARAM_NAMES`).
- `folding.py` / `data_io.py` — carga `.ws5`/`.adt`/Normos y folding (eje de velocidad conservador).
- `fit_engine.py` — motor de ajuste discreto (singlete/doblete/sextete).
- `profile_likelihood.py` — intervalos de confianza por verosimilitud perfilada.
- `batch_fit.py` — ajuste en serie por warm-start.
- `session.py` — **capa headless** `ModelState` + `HeadlessSession`: orquesta cargar →
  doblar → ajustar → sesión sin GUI. Es lo que usa el CLI.
- `plot_styles.py` — estilos de gráfico seleccionables desde la GUI.

### Front-ends y módulos de nivel superior
- `fitbauer.py` — **punto de entrada único**; lanza la GUI Qt.
- `mossbauer_qt.py` — la GUI Qt (PySide6 + Plotly). Archivo grande; delega los cálculos en `core/`.
- `mossbauer_distribution.py` — ajuste de distribución `P(BHF)`/`P(ΔEQ)` (Hesse-Rübartsch,
  regularización, L-curve, componentes nítidos). Aquí vive `build_sharp_kernel`.
- `mossbauer_fit_cli.py` — ajuste headless (plantilla + espectro → fichero); usa `core.session`.
- `fit_bhf_distribution_cli.py`, `mossbauer_bhf_pipeline.py` — CLIs/pipeline de distribución.
- `mossbauer_ws5.py`, `fold_mossbauer.py` — lectura WS5 y folding standalone.
- `mossbauer_api_client.py`, `mossbauer_updater.py` — descarga web de espectros/calibraciones y actualizaciones.
- `mossbauer_i18n.py`, `mossbauer_help.py`, `locales/` — traducciones ES/EN/FR y ayuda.
- `layout/presets.py` — presets de disposición usados por la GUI Qt. (`panels/` es vestigial: vacío.)

## Modos de ajuste

- **Discreto**: hasta tres componentes (singlete/doblete/sextete), perfiles Lorentz/Voigt,
  pesos Poisson, χ²/AIC/BIC, multistart, errores por covarianza/bootstrap, textura de sextete.
- **Distribución** `P(BHF)` / `P(ΔEQ)`: suma de muchos sextetes/dobletes en una malla,
  regularización por segunda diferencia (α), L-curve, y **componentes "nítidos"** simultáneos.
  - En modo distribución + nítidos, la GUI dibuja **todos los subespectros**: cada nítido por
    separado y la **envolvente de la distribución** (índice `idx=0` con estilo propio), además
    del modelo total. Esto vive en `MainWindow.on_fit_distribution` (`mossbauer_qt.py`) y se
    refleja en `SpectrumCanvas.render` y en la figura Plotly.
  - Nota: la reconstrucción actual de los nítidos usa `component_absorption` con los valores de
    los widgets + el peso ajustado. Existe un enfoque alternativo (reconstruir con el propio
    kernel del ajuste, `build_sharp_kernel`) que sería más fiel si el ajuste refina δ/Γ globales;
    se descartó como rama redundante (SHA `a7c803b`) por si alguna vez se quiere rescatar.

## Tests

```bash
QT_QPA_PLATFORM=offscreen xvfb-run -a pytest -q     # como en CI (Linux, sin display)
pytest -q                                           # local con display
```

- Suite en `tests/` (física core, fit_engine, folding, CLI, headless golden, distribución,
  batch, profile-likelihood, GUI Qt con pytest-qt).
- CI: `.github/workflows/tests.yml` (Python 3.12, PySide6 offscreen). `release_assets.yml`
  construye ejecutables PyInstaller (`Fitbauer.spec`).
- Hay un **golden test headless** (`tests/test_headless_golden.py`): si tocas el núcleo de
  ajuste, espera que sea sensible — revisa que los cambios sean intencionados.

## Datos de ejemplo

`data_sample/` trae espectros reales y sintéticos (`magnetita_Fe3O4.adt`,
`hierro_metalico_alphaFe.adt`, `hematita_Fe2O3.adt`, sintéticos…), calibración
(`calibration.adt` + `calibration_session.json`) y plantillas JSON. Para probar la GUI:
**Archivo → Cargar…** un `.adt` y luego **Archivo → Cargar sesión…** el JSON asociado.

## Convenciones del repo

- Calibración de campo de referencia: **33.0 T** con patrón de velocidad publicado de α-Fe
  (`±0.839 / ±3.084 / ±5.329 mm/s`); `LINE_POS_33T` vive en `core.constants`. No derivar
  posiciones de momentos nucleares (sesga el BHF ~0.1 T; ver CHANGELOG v4.0.2/v4.0.3).
- El historial de cambios se documenta en `CHANGELOG.md` (por versión).
- `APP_VERSION` en `core/constants.py` es la fuente única de versión.
- Idioma del proyecto: español (commits, comentarios, docs). Mantén ese registro.
