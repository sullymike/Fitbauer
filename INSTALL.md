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

## Actualizar

Descarga una nueva release, descomprímela y ejecuta otra vez:

```bash
python3 install.py
```

El instalador reutiliza `.venv` si ya existe y actualiza las dependencias.
