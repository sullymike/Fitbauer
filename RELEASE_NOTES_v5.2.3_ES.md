# Fitbauer v5.2.3

*[🇬🇧 English notes](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.2.3.md)*

Una versión de compatibilidad con NORMOS, a partir de una revisión de su código
fuente y del manual de WinNormos. Añade la distribución de Le Caër con campo y
el campo aplicado de la relajación de Ising. También corrige cómo se abren los
`.JOB` con VMAX negativo.

---

## Corrección importante: `.JOB` con VMAX negativo

En NORMOS el signo de VMAX invierte el espectro. El importador tomaba su valor
absoluto, así que esos trabajos se abrían **reflejados**, con el desplazamiento
isomérico de signo cambiado. Ahora el signo se conserva al importar y al
exportar, con un aviso. Lo destapó el banco de trabajos reales de NORMOS: todos
los que tenían VMAX negativo doblaban distinto que NORMOS, y con el signo
coinciden al nivel del ruido. **Si importaste un trabajo así, vuelve a
importarlo.**

## Nuevo: distribución de Le Caër con campo

Nueva forma **Le Caër** para P(ΔEQ): el gradiente de campo aleatorio de Czjzek
visto por sextetes en un campo fijo, para fases magnéticas desordenadas como
vidrios metálicos y materiales nanocristalinos.

- La malla es el acoplamiento con signo e²qQ/2.
- Cada subespectro es el promedio de polvo exacto de un sextete con el EFG
  orientado al azar respecto al campo.
- Los pesos son la distribución de Vzz con signo de un tensor de Czjzek
  (comprobada por Monte Carlo); σ es el único parámetro de forma.

Es el `DISTRI=4` con `METHOD=7` de NORMOS-DIST, y esos `.JOB` se importan ya
con esta forma. En P(ΔEQ) Czjzek y Le Caër se pueden elegir siempre: elegir Le
Caër activa el sextete con campo fijo (33 T si el campo estaba en 0), y elegir
Czjzek lo desactiva. En el CLI: `--shape lecaer`.

## Nuevo: campo aplicado en la relajación de Blume–Tjon

El componente Blume–Tjon tiene un parámetro nuevo, **Campo externo BEXT (T)**,
el BEXT de NORMOS. El campo hiperfino se invierte con el espín y el aplicado
no, así que los dos estados ven BEXT ± BHF. En el límite rápido el espectro
colapsa a un sextete de campo BEXT en lugar de a una sola línea.

Es un dato del experimento: va fijo por defecto, «Liberar todos» no lo suelta y
con 0 no cambia nada. Coincide con la ecuación matricial de Blume a 1e-10.

## Más de NORMOS

- **Se importa la relajación de Ising (`IRELAX`)** como componente
  Blume–Tjon, con ν = OME·10⁶/2, P = BHF/BSAT y el BEXT global. Antes solo
  daba un aviso.
- **Distribuciones gaussianas (`DISTRI=2`):** NORMOS ensancha STG con el paso
  de la malla, así que la anchura real es √(STG² + paso²). El aviso de
  importación la da ahora. Antes decía, por error, que STG no se trasladaba.
- **`METHOD=5`/`7`** conservan la forma del `DISTRI`. El fichero spline de
  NORMOS guarda los subespectros, no la distribución. Antes se importaban como
  «Fija».
- **Forma de P:** el panel y el informe dan la asimetría y la curtosis en
  exceso de la distribución, como NORMOS-DIST.
- **Parámetro de Hesse–Rübartsch:** el criterio de suavizado de NORMOS-DIST,
  Σ(y − y_teo)²/Σy ≈ χ²/N, aparece en el panel y en el informe.

## Validación

Se ha rehecho el banco de trabajos reales de NORMOS. Cubre 407 trabajos
distintos, y solo se conservan los que valen como referencia:

- los que NORMOS ajustó bien (χ² reducido ≤ 2): se descartan 161 en que no lo
  hizo;
- aquellos en que los dos programas ven el mismo espectro.

En los 216 restantes, partiendo de la solución de NORMOS, Fitbauer llega al
mismo χ² o a uno menor en 211. El acuerdo mediano es de 0.0014 mm/s en δ y
0.016 T en BHF.

---

Suite completa: **759 tests en verde**.
