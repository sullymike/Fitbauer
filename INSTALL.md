# Instalación desde código Python

No hace falta descargar un `.exe`. Basta con tener Python instalado.

## Linux

```bash
python3 install.py
./fitbauer
```

Si `python3` no existe, instala Python 3 con el gestor de paquetes de tu distribución.

## Windows

1. Instalar Python 3 desde https://www.python.org/downloads/.
2. Durante la instalación, marcar **Add Python to PATH**.
3. Descargar el ZIP de la release o del repositorio y descomprimirlo.
4. Abrir una terminal dentro de la carpeta descomprimida.
5. Ejecutar:

```bat
py install.py
fitbauer.bat
```

Si `py` no funciona, probar:

```bat
python install.py
fitbauer.bat
```

## Qué hace `install.py`

- Crea un entorno virtual local `.venv`.
- Instala dependencias desde `requirements.txt`.
- Crea lanzadores:
  - Linux/macOS: `fitbauer`
  - Windows: `fitbauer.bat`
- **Registra Fitbauer en los menús de aplicaciones del sistema** (por-usuario, sin
  permisos de administrador), para poder abrirlo desde el menú con su icono:
  - Linux: fichero `~/.local/share/applications/fitbauer.desktop` (categoría
    *Education*, + icono en `hicolor`).
  - Windows: acceso directo en una carpeta *Fitbauer* del menú Inicio
    (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Fitbauer\Fitbauer.lnk`).

### Opciones

```bash
python install.py               # instalación completa + registro en menús
python install.py --menu-only   # solo registra la app en los menús
python install.py --no-menu     # instala sin tocar los menús
python install.py --uninstall   # elimina la entrada de menú
```

## Actualizar

Descarga una nueva release, descomprímela y ejecuta otra vez:

```bash
python3 install.py
```

El instalador reutiliza `.venv` si ya existe y actualiza las dependencias.
