# Versiones y actualizaciones

El programa comprueba nuevas versiones usando **GitHub Releases** del repositorio:

```text
https://github.com/sullymike/Mossbauer/releases
```

## Cómo publicar una versión nueva

1. Cambiar `APP_VERSION` en:
   - `mossbauer_fe33_gui_v2IA.py`
   - `core/constants.py`

2. Actualizar `CHANGELOG.md`.

3. Commit, tag y push:

```bash
git add -A
git commit -m "Release vX.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

4. En GitHub, crear la release desde ese tag:

```text
https://github.com/sullymike/Mossbauer/releases/new
```

5. Al publicar la release, el workflow `.github/workflows/release_assets.yml` se
   dispara automáticamente y adjunta dos assets:
   - `Mossbauer-vX.Y.Z.zip` — todos los ficheros del programa.
   - `sha256sums.txt` — checksum SHA-256 del ZIP, que el actualizador verifica
     al descargar.

No hace falta adjuntar nada manualmente.

## Cómo detecta actualizaciones el programa

Al arrancar, el programa consulta silenciosamente la última release publicada.
También se puede comprobar manualmente desde:

```text
Ayuda → Buscar actualizaciones...
```

Si el tag de GitHub, por ejemplo `v2.3`, es mayor que `APP_VERSION`, ofrece
descargar el ZIP en la carpeta `Descargas`/`Downloads` y verificar su integridad
con el `sha256sums.txt` adjunto.
