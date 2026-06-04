# Fitbauer v4.0.1

Versión de mantenimiento sobre **Fitbauer v4.0**.

## ✨ Cambios

- El **logo de Fitbauer** se muestra ahora dentro del programa, en ambas interfaces (Qt y Tk):
  - Tarjeta de **cabecera** (junto al nombre, subtítulo y autor).
  - **Pantalla de inicio** (splash).
  - Diálogo **«Acerca de»**.
- Carga robusta del logo: si la imagen no está disponible, se conserva el comportamiento anterior (texto / dibujo vectorial) sin romper la interfaz.

## 📦 Instalación

```bash
python3 install.py
./fitbauer          # Qt por defecto; cae a Tk si PySide6 no está disponible
./fitbauer --tk     # fuerza la interfaz Tk
```

En Windows: `py install.py` y luego `fitbauer.bat`.

## 🔁 Compatibilidad

- Totalmente compatible con sesiones, informes y datos de v3.x / v4.0.
- Verifica el ZIP con `sha256sums.txt`.
