# Versiones y actualizaciones

El programa comprueba nuevas versiones usando **GitHub Releases** del repositorio:

```text
https://github.com/sullymike/Mossbauer/releases
```

## Cómo publicar una versión nueva

1. Cambiar `APP_VERSION` en:
   - `mossbauer_fe33_gui.py`
   - `mossbauer_fe33_gui_v2IA.py`

2. Actualizar `CHANGELOG.md`.

3. Commit y push:

```bash
git add -A
git commit -m "Release v0.1.1"
git push origin main
```

4. Crear un tag:

```bash
git tag v0.1.1
git push origin v0.1.1
```

5. En GitHub, crear la release desde ese tag:

```text
https://github.com/sullymike/Mossbauer/releases/new
```

6. Adjuntar, si existe, el ejecutable `.exe` o un `.zip` preparado. Si no se adjunta nada, el actualizador descargará el ZIP automático del código fuente generado por GitHub.

## Cómo detecta actualizaciones el programa

Al arrancar, el programa consulta silenciosamente la última release publicada. También se puede comprobar manualmente desde:

```text
Ayuda → Buscar actualizaciones...
```

Si el tag de GitHub, por ejemplo `v0.1.1`, es mayor que `APP_VERSION`, ofrece descargar la nueva versión en la carpeta `Descargas`/`Downloads`.
