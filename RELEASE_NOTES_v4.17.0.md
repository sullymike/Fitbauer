# Fitbauer v4.17.0

Caza de bugs en profundidad con cuatro auditorías independientes (motor de
ajuste, GUI, sesiones/estado, CLI+i18n), verificación manual de cada hallazgo y
**21 correcciones**. i18n resultó estar limpio (793 claves y placeholders
idénticos en los 7 idiomas).

## Motor de ajuste

- **Vmax negativo + «Ajustar velocidad» invertía el eje**: el eje quedaba
  des-invertido en todas las iteraciones (δ espejado) y el signo se perdía al
  terminar. Ahora la convención de eje se conserva (triangular y seno).
- **`fit_center` roto fuera de 512 canales**: los límites del centro estaban
  codificados para 512 (250–263); ahora derivan del nº de canales (N/2 ± 7).
- **σ Poisson en modo seno**: se aplicaba el ÷2 del promedio de dos canales del
  doblado también en seno (sin doblar) → χ² inflado ×2; ídem en las réplicas
  bootstrap. Corregido.
- **Perfil de verosimilitud con `fit_center`**: comparaba χ² de datasets
  doblados en centros distintos (offset constante en Δχ², intervalos `null`
  silenciosos en el CLI). Ahora se condiciona al dataset del centro ajustado.
- **Errores de vmax/centro/σ ajustados**: se calculaban en la covarianza y se
  descartaban. Ahora se informan en GUI, informes y CLI.
- **Réplicas bootstrap/perfil**: usan la σ-Voigt ajustada y heredan la forma de
  onda; `HeadlessSession` re-dobla tras `fit_center` (en seno actualiza la
  fase) y el CLI muestra los globales ajustados.
- **«Propagar incertidumbre de calibración» era un no-op**: `sigma_vmax` no se
  cableaba nunca; ahora se toma de la calibración asociada.

## GUI

- El menú **Modelo de absorbente** ahora sincroniza el panel (era un no-op para
  el ajuste: seguía usando el modelo antiguo y `sat_scale` quedaba agrisado).
- **Batch**: warm-start completo (vmax/σ/sat_scale) y refresh del plot/panel al
  cerrar el diálogo.
- **Bootstrap sin ajuste previo** vuelca el ajuste base a los widgets y al plot.
- La sincronización de restricciones ya no desbloquea señales a mitad de una
  carga de sesión (podía pisar el centro guardado).
- Menores: etiqueta del fichero tras «Buscar centro»; comprobación de tamaños
  al exportar un ajuste de distribución.

## Sesiones (guardar/cargar, historial, deshacer)

- El **tipo y los modos** de cada componente se restauran antes que los valores
  (un tipo distinto machacaba int1/int2 recién restaurados) y con re-layout.
- El **modo** se restaura antes que las casillas «activo» y los valores de la
  malla (se pisaba el patrón de componentes y se recortaban valores con los
  rangos de la variable anterior).
- Menores: limpieza de resultados runtime/mapa 2D con cuentas embebidas; la
  calibración y la ruta de P fija ya no se heredan de la GUI anterior;
  `multistart_n: null` de sesiones antiguas ya no aborta la carga.

## CLI de distribución

- **Default de Γ unificado (0.36 mm/s, fuente única en `core.params`)**: el
  pipeline web usaba 0.18 sin sidecar mientras GUI y CLI usaban 0.36 — el mismo
  espectro daba P(BHF) distintas según el punto de entrada. Para reproducir el
  comportamiento antiguo del pipeline: `--gamma 0.18`.

## Verificación

7 tests de regresión nuevos (todos fallan sin los fixes). Suite completa:
**287 tests en verde**, golden headless incluido.
