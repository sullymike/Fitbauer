# Manual de usuario de Fitbauer (LaTeX)

Manual de usuario extenso, en español, del programa Fitbauer.

## Estructura

```
docs/manual/
├── main.tex              # Preámbulo + \input de capítulos
├── chapters/             # Un fichero .tex por capítulo
│   ├── 00_intro.tex
│   ├── 01_calibracion.tex
│   ├── 02_carga_datos.tex
│   ├── 03_simular_ajustar.tex
│   └── 04_distribuciones.tex
├── img/                  # Figuras (auto-generadas + capturas de GUI)
├── scripts/make_figures.py   # Genera las figuras de física con matplotlib
├── Makefile
└── README.md
```

## Compilar

Desde `docs/manual/`:

```bash
make            # genera figuras (si faltan) y compila main.pdf
make figures    # solo (re)genera las figuras de física
make pdf        # solo compila el PDF
```

Requiere una distribución LaTeX (`latexmk` o `pdflatex`) y el entorno Python del
proyecto para las figuras.

## Figuras

Hay **dos tipos** de imágenes:

1. **Figuras de física/datos** (espectros, ajustes, distribuciones). Se generan
   automáticamente reutilizando el núcleo `core/` con:

   ```bash
   python docs/manual/scripts/make_figures.py    # desde la raíz del repo
   ```

   Salen en `img/` como `fig_*.pdf` y `fig_*.png`. Se insertan con `\autofig`.

2. **Capturas de la interfaz** (menús, paneles, diálogos). Deben hacerse a mano
   desde la aplicación. Se insertan con `\guicap{nombre}{pie}`: mientras no
   exista `img/nombre.png`, el manual compila con un recuadro **«captura
   pendiente»** que indica el nombre de fichero esperado. Basta con guardar la
   captura con ese nombre en `img/` para que aparezca.

   Capturas pendientes actuales: `gui_overview`, `gui_use_as_calibration`,
   `gui_calib_label_fixed`, `gui_plot_area`, `gui_component_panel`,
   `gui_distribution_panel`.
