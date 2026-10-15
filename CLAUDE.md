# CLAUDE.md

Guía de orientación para Claude Code en este repositorio. Pensada para que cualquier
sesión (web o VS Code) arranque con contexto sin tener que re-descubrir la arquitectura.

## Qué es

**Fitbauer** — *Software for Mössbauer spectrum fitting and analysis*. Aplicación de
escritorio para cargar, doblar (fold), simular y ajustar espectros Mössbauer de Fe-57.
Autor: Jorge Sánchez Marcos (Dpto. de Química Física · UAM). Idiomas: ES/EN/FR/DE/PT/RU/JA/ZH (catálogos en `locales/`; `ch` es el chino).

## Arranque y desarrollo

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # para los tests
python fitbauer.py                   # abre la GUI Qt
```

- **Una sola GUI: Qt (PySide6 + Matplotlib).** La antigua interfaz Tk fue **eliminada por
  completo**; no la reintroduzcas. Si ves referencias a `mossbauer_app.py`,
  `mossbauer_fe33_gui_v2IA.py`, `panels/`, `sv_ttk` o un fallback Tk, son obsoletas.
- **Plotly/QtWebEngine se retiraron** (adelgazamiento, v4.13.1). El gráfico es solo
  Matplotlib (`gui/canvas.py`) y el editor de mínimos vive en `gui/minima_editor.py`.
  Todo el detalle de la integración anterior, por si se quiere restaurar, está en
  `docs/plotly.md`. No reintroduzcas `plotly` ni `QtWebEngine` sin motivo.
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
- `mossbauer_qt.py` — wrapper/ensamblador de la ventana principal Qt. Debe permanecer fino:
  importa mixins de `gui/`, define `MossbauerQtWindow`, `main()` y mantiene algunos reexports
  históricos usados por tests/extensiones (`ReleaseInfo`, `latest_release`, `threading`,
  `webbrowser`, `load_credentials`, `save_credentials`). No volver a concentrar aquí lógica
  de paneles, menús o fitting.
- `gui/` — implementación modular de la GUI Qt. Es código de presentación/controlador; puede
  orquestar `core/`, pero la física y los motores de ajuste siguen viviendo en `core/`.
  - `window_mixins.py` — composición ordenada de mixins de `MossbauerQtWindow`.
  - `main_layout.py`, `menu_builder.py`, `layout_manager.py` — construcción visual, menús,
    presets de layout, temas y settings.
  - `panels.py`, `controls.py`, `distribution_panel.py`, `canvas.py` — widgets reutilizables
    (`ParamControl`, paneles, canvas Matplotlib).
  - `model_workflow.py` — carga de datos, folding/refolding, `ModelState`/`FitState`, refresh
    del plot y panel de información.
  - `discrete_fit.py`, `distribution_fit.py`, `minima_analysis.py`, `fit_tools.py` — acciones
    de ajuste discreto/distribución, bootstrap, perfil likelihood, detección de mínimos,
    presets físicos y batch.
  - `minima_editor.py` — editor semi-manual de mínimos sobre el canvas Matplotlib
    (clic para añadir/alternar; alimenta *Inicializar/Autoajustar desde mínimos*).
  - `state.py` — estados runtime (`FileState`, `RuntimeResultState`) y snapshots
    serializables (`ComponentViewState`, `SpectrumState`, `CalibrationState`, `FitOptionsState`,
    `DistributionViewState`, `PlotViewState`, `UiPreferencesState`, `ProjectState`); es el
    inicio de la capa formal de estado para reducir lecturas directas de widgets.
  - `session_io.py`, `reports.py`, `web_api.py`, `updates.py`, `help.py`,
    `calibration_actions.py`, `file_actions.py` — persistencia, informes, API web,
    actualizaciones, ayuda y acciones auxiliares.
- `mossbauer_distribution.py` — ajuste de distribución `P(BHF)`/`P(ΔEQ)` (Hesse-Rübartsch,
  regularización, L-curve, componentes nítidos). Aquí vive `build_sharp_kernel`.
- `mossbauer_fit_cli.py` — ajuste headless (plantilla + espectro → fichero); usa `core.session`.
- `fit_bhf_distribution_cli.py`, `mossbauer_bhf_pipeline.py` — CLIs/pipeline de distribución.
- `mossbauer_ws5.py` — lectura WS5/folding (reexports de `core.folding` + variantes para los CLIs de distribución).
- `mossbauer_api_client.py`, `mossbauer_updater.py` — descarga web de espectros/calibraciones y actualizaciones.
- `mossbauer_i18n.py`, `mossbauer_help.py`, `locales/` — traducciones (8 idiomas) y ayuda.
- `layout/presets.py` — presets de disposición usados por la GUI Qt. (`panels/` es vestigial: vacío.)

## Modos de ajuste

- **Discreto**: hasta diez componentes (singlete/doblete/sextete y tipos de relajación), perfiles Lorentz/Voigt,
  pesos Poisson, χ²/AIC/BIC, multistart, errores por covarianza/bootstrap, textura de sextete.
- **Distribución** `P(BHF)` / `P(ΔEQ)`: suma de muchos sextetes/dobletes en una malla,
  regularización por segunda diferencia (α), L-curve, y **componentes "nítidos"** simultáneos.
  - **Regularizadores** (`reg_mode`): `tikhonov` (curvatura, suave), `tv` (variación total,
    bordes) y `maxent` (máxima entropía; L-BFGS-B con gradiente analítico).
  - **Formas** (`shape`): `Histograma` (Hesse-Rübartsch), `Gaussiana`, `VBF` (multi-gaussiano
    Voigt, Rancourt–Ping; guarda A/μ/σ por componente), `Binomial`, `Fija`, `2D`.
    `Gaussiana` **no tiene función propia**: es VBF con `n_components=1` y `profile="Lorentz"`
    (`fit_vbf_hyperfine_distribution(..., shape="Gaussiana")`); se conserva la etiqueta solo
    para la GUI/sesión/informes.
  - **Correlación δ(H)/ΔEQ(H)** (`delta_slope`/`quad_slope` en el kernel): δ y ΔEQ varían
    linealmente con H (opt-in, 0 = clásico). Aplica a Histograma y VBF.
  - **Cotas σ** de Gaussiana/VBF (1D y 2D, un par por eje): `vbf_sigma_bounds()` en
    `mossbauer_distribution.py`; 0 = automático. Panel `σ mín/máx`, sesión
    `dist_vbf_sigma_min/max[_y]`, CLI `--vbf-sigma-min/max[-y]`.
  - En modo distribución + nítidos, la GUI dibuja **todos los subespectros**: cada nítido por
    separado y la **envolvente de la distribución** (índice `idx=0` con estilo propio), además
    del modelo total. Esto vive en `DistributionFitMixin.on_fit_distribution`
    (`gui/distribution_fit.py`) y se refleja en `SpectrumCanvas.render` (`gui/canvas.py`).
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

`data_sample/` trae espectros sintéticos y medidos, calibración
(`calibration.adt` + `calibration_session.json`) y plantillas JSON. **Ojo:** los
cuatro «de referencia» (`hierro_metalico_alphaFe.adt`, `hematita_Fe2O3.adt`,
`siderita_FeCO3.adt`, `magnetita_Fe3O4.adt`) son SINTÉTICOS (Fitbauer, mayo de 2026,
patrón histórico, Vmax = 12.007), igual que `sintetico_*` y `public/*.adt`; son
medidas `Fe3O4.adt`, `calibration.adt` (calibración web FC210422) y
`public/alphaFe_calibracion_ESRF.dat`. No ejecutes `_generate_synthetic.py`: está
desfasado y sobrescribe los de referencia. Para probar la GUI:
**Archivo → Cargar…** un `.adt` y luego **Archivo → Cargar sesión…** el JSON asociado.

## Convenciones del repo

- Calibración de campo de referencia: **33.0 T** (Vmax ajustada con α-Fe a 33.0 T).
  Patrón por defecto desde la v5.3.0: el derivado de los **momentos nucleares**, con
  las constantes de NORMOS-SITE (`"normos"`, ±0.8410 / ±3.0836 / ±5.3261 mm/s; razón
  g1/g0 de Violet–Pipkorn). El anterior, `"legacy"` (alias `"alpha_fe"`, ±5.3285…),
  NO es una tabla publicada: venía del simulador web del laboratorio; se conserva
  para sesiones antiguas. El viejo argumento «los momentos sesgan el BHF 0.1 T» era
  circular (calibración reutilizada); ver `docs/calibracion_33T.md`.
- **Las calibraciones guardan su patrón** (`calibration_info["sextet_pattern"]`) y la
  GUI aplica la Vmax convertida (`core.constants.convert_vmax`, factor 0.999623). Sin
  patrón: las locales son históricas; las de la API web son VMAX de NORMOS
  («normos»; la API marca «legacy» las que la web ajustó con su patrón antiguo). Las
  sesiones sin patrón se cargan con el histórico.
- **Fuente única del patrón**: `core.constants`. `active_sextet_pattern()` devuelve el
  patrón del convenio activo y de ahí derivan el sexteto de 1er orden, ω_e/ω_g del
  Hamiltoniano, Blume–Tjon y el kernel de distribución — no dupliques posiciones.
  **`fit_discrete` impone el patrón del modelo** (`ModelState.sextet_pattern`): un
  `with sextet_pattern(...)` alrededor del ajuste no basta; sirve para evaluar el
  modelo fuera del ajuste. `LINE_POS_33T` es el patrón por defecto como constante y
  la usan solo los consumidores que NO son física (rótulos, detección de mínimos,
  figuras).
- El historial de cambios se documenta en `CHANGELOG.md` (por versión).
- `APP_VERSION` en `core/constants.py` es la fuente única de versión.
- Idioma del proyecto: español (commits, comentarios, docs internas). Mantén ese registro.
- **Todo texto público de una release va en inglés.** Se dirige a quien descarga
  el programa, no al equipo. Afecta a `RELEASE_NOTES_v*.md` (que el workflow
  publica tal cual como cuerpo de la release en GitHub), al README principal y a
  `NOTICE` / `THIRD-PARTY-LICENSES.md`.
  - Si además se quiere en español, va en un fichero aparte con sufijo `_ES`
    (`RELEASE_NOTES_v5.2.0_ES.md`), enlazado desde la primera línea del inglés,
    igual que `README.md` ↔ `README_ES.md`. **El que se ve por defecto es
    siempre el inglés**: `release_assets.yml` usa `RELEASE_NOTES_${TAG}.md`, así
    que ese fichero, sin sufijo, tiene que ser el inglés.
  - Ese enlace cruzado va con **URL absoluta** a `blob/main/`: el cuerpo de la
    release en GitHub no resuelve rutas relativas al repositorio.
  - El `CHANGELOG.md` NO es texto público de release: sigue en español.
