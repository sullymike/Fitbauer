# Fitbauer v4.0

**Software for Mössbauer spectrum fitting and analysis.**

Primera versión con la nueva identidad **Fitbauer** y el repositorio preparado para producción. El núcleo de cálculo, los formatos de sesión y los datos siguen siendo totalmente compatibles con versiones anteriores.

## ✨ Novedades

### Nueva identidad
- La aplicación pasa a llamarse **Fitbauer** — *Software for Mössbauer spectrum fitting and analysis*.
- Logo e icono nuevos: la firma de un sextete Mössbauer con su curva de ajuste sobre una insignia azul→cian. Fuente vectorial reproducible en `assets/fitbauer_logo.svg` (generador `assets/make_logo.py`).

### Arranque unificado Qt → Tk
- Nuevo punto de entrada único **`fitbauer.py`** (y lanzadores `fitbauer` / `fitbauer.bat`): abre la interfaz **Qt** por defecto y cae automáticamente a la interfaz **Tk** si PySide6 no está disponible o falla al iniciarse.
- Opciones `--qt` y `--tk` para forzar una interfaz concreta.
- Ejecutables PyInstaller renombrados: **`Fitbauer.spec`** (Qt, principal) y **`Fitbauer-Tk.spec`** (Tk, respaldo).

### Repositorio listo para producción
- `layout.json` deja de versionarse (es estado de runtime del usuario) y se añade a `.gitignore`.
- Eliminado `download_and_fit_calibrations.py` (roto y sin uso: importaba un módulo inexistente).
- Retiradas notas de versión sueltas y documentos internos de roadmap; el historial vive en `CHANGELOG.md`.
- Capturas movidas a `docs/img/` y workflow de publicación actualizado.

## 📦 Instalación

```bash
python3 install.py
./fitbauer          # Qt por defecto; cae a Tk si PySide6 no está disponible
./fitbauer --tk     # fuerza la interfaz Tk
```

En Windows: `py install.py` y luego `fitbauer.bat`.

Requisitos (`requirements.txt`): numpy ≥ 2.0, scipy, matplotlib, requests, sv_ttk, PySide6 ≥ 6.5, plotly. En Linux, la interfaz Tk necesita además el paquete de sistema `python3-tk`.

## 🔁 Compatibilidad
- Sesiones, informes y datos de versiones 3.x se cargan sin cambios.
- Verifica el ZIP con `sha256sums.txt`.
