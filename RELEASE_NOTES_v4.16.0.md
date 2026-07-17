# Notas de versión — Fitbauer v4.16.0

## Renombrado del repositorio a Fitbauer

El repositorio de GitHub se ha renombrado de `Mossbauer` a **`Fitbauer`**, alineándolo con
el nombre del programa. Esta versión actualiza todas las referencias codificadas al slug del
repositorio para que apunten a `sullymike/Fitbauer`.

---

### Qué cambia

- **Actualizador (`mossbauer_updater.py`).** `GITHUB_REPO` pasa a `sullymike/Fitbauer`, lo
  que propaga automáticamente a las URLs de la API REST, el feed atom público, la página de
  releases y las descargas de assets. La comprobación de actualizaciones y la descarga de
  nuevas versiones apuntan ya al nombre nuevo.
- **Ayuda (`gui/help.py`).** El enlace «Abrir manual» (`MANUAL_EN_URL`) apunta al PDF en el
  repositorio renombrado.
- **Documentación.** `INSTALL_EN.md` (URL de `git clone` y directorio de trabajo) y los
  artículos/paper en `docs/` (`.tex`, `.md`, `.bib`) enlazan a `sullymike/Fitbauer`.

### Compatibilidad

- GitHub mantiene la **redirección** automática desde el nombre antiguo, de modo que los
  enlaces y clones previos siguen funcionando. Este cambio evita depender de esa redirección
  y deja la referencia canónica correcta en el código y la documentación.
- No hay cambios en la física, el motor de ajuste ni la interfaz. Actualización puramente de
  mantenimiento.

---

*Fitbauer — Software for Mössbauer spectrum fitting and analysis. Jorge Sánchez Marcos,
Dpto. de Química Física · UAM.*
