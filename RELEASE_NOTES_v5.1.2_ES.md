# Fitbauer v5.1.2

*[🇬🇧 Release notes in English](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.1.2.md)*

La compatibilidad con NORMOS llega a la interfaz, la relajación de Ising queda
validada frente al ejecutable de NORMOS, y varias correcciones.

---

## Convenios NORMOS en la interfaz

Nuevo submenú **Ajuste ▸ Opciones avanzadas de ajuste ▸ Convenios (compatibilidad
NORMOS)**, con tres elecciones. La primera opción de cada una es la de
Fitbauer:

- **Patrón de líneas del sextete**: posiciones publicadas del α-Fe, o
  derivadas de los momentos nucleares como hace NORMOS. Con el mismo espectro
  el campo difiere unos 0,01 T a 33 T.
- **Razones de intensidad**: por profundidad, o por área como los D13/D23 de
  NORMOS. Solo difieren si las anchuras Γ2/Γ3 no son iguales a Γ1.
- **Relajación con poblaciones desiguales**: modelo de Blume con balance
  detallado, o la regla de NORMOS (ver abajo).

Se aplican a todo a la vez: simulación en vivo, ajustes discretos y de
distribución, bootstrap y verosimilitud perfilada. Se guardan en la sesión y se
recuerdan como preferencia, y el panel de estado avisa cuando alguno no es el
de por defecto. Ajustando α-Fe en la interfaz con cualquiera de los dos
patrones se obtiene lo mismo que con la línea de comandos.

## Relajación: modelo propio, validado frente a NORMOS

- La relajación de dos estados con poblaciones desiguales es ahora una
  implementación propia del modelo estocástico de Blume (Phys. Rev. 174, 351,
  1968). **Cambian los resultados con polarización P > 0**; con P ≤ 0 no cambia
  nada.
- Una sonda nueva del ejecutable de NORMOS-SITE muestra que, con poblaciones
  iguales, Fitbauer reproduce su relajación de Ising a 10⁻⁵ del pico en seis
  décadas de la tasa de relajación. El `OME` de NORMOS (MHz) es el doble de la
  tasa de intercambio de Fitbauer.
- Con poblaciones desiguales NORMOS sigue una regla que no cumple el balance
  detallado. Está disponible como **convenio NORMOS** opcional, que reproduce
  el ejecutable a 4·10⁻⁵, desde el menú anterior o con
  `--relax-convention normos` en la línea de comandos. El defecto sigue siendo
  el modelo físico.

## Validación frente a NORMOS, regenerada

El banco de validación frente a NORMOS (más de 400 espectros generados por
NORMOS y ajustados por Fitbauer) se ha regenerado con la versión actual y
reproduce las cifras publicadas. Ahora se ejecuta con un solo script,
`validacion/generador/banco_completo.sh`.

## Correcciones

- Las sesiones antiguas ajustadas en modo discreto se abrían en modo
  distribución. Afectaba a las sesiones de ejemplo que recomienda el README,
  que además se han regenerado con el formato actual.
- Las réplicas del bootstrap y del perfil de verosimilitud ignoraban el
  convenio de intensidades por área y se reajustaban con el de profundidad.
- El temporizador de autoguardado seguía activo tras cerrar la ventana y podía
  volver a escribir el fichero de recuperación que un cierre limpio acababa de
  borrar.

---

Suite completa: **624 tests en verde**.
