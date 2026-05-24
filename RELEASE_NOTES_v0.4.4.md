# Mössbauer Fe-57 GUI v0.4.4

Patch release sobre v0.4.3 que corrige el comportamiento de la calibración activa al cargar nuevos ficheros.

## Cambio

- **La calibración persiste al abrir nuevos ficheros de datos.**
  En v0.4.2–v0.4.3, al cargar un `.ws5` o `.adt` local la calibración activa se borraba y el label desaparecía. Esto era incorrecto: la calibración describe el estado del instrumento (escala de velocidades), no el fichero analizado. Ahora la calibración se mantiene visible en el panel hasta que el usuario indique explícitamente otra, ya sea mediante `Archivo → Usar fichero actual como calibración...` o descargando una medida con calibración asociada desde la web.

## Sin otros cambios

Toda la funcionalidad de v0.4.3 se mantiene tal cual.
