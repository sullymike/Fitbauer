# Calibración del campo hiperfino: α-Fe a 33.0 T

Fuente: `core/constants.py` (`SEXTET_PATTERNS`, `LINE_POS_33T`, `convert_vmax`)

---

## Cómo se calibra

Las seis líneas de un sextete de Fe-57 se separan en proporción al campo hiperfino
$B_{hf}$. Fitbauer necesita dos cosas para pasar de canales a teslas:

1. **Un patrón de posiciones a 33.0 T**, que fija la *forma* del sextete: la razón entre
   el desdoblamiento del estado excitado y el del fundamental ($g_1/g_0$).
2. **Una calibración de velocidad** (la Vmax), que fija la *escala*. Se obtiene
   ajustando un espectro de α-Fe con el campo fijo en **33.0 T**, igual que en NORMOS.

Como la Vmax se calibra con α-Fe a 33.0 T, la escala absoluta del patrón se cancela al
medir campos: el BHF de una muestra depende solo de la forma del patrón. Los
desplazamientos (δ, ΔEQ) sí dependen de la escala absoluta, que la calibración fija.

---

## El patrón por defecto: momentos nucleares (desde la v5.3.0)

Fitbauer deriva las posiciones de los **momentos nucleares**, con las mismas constantes
que NORMOS-SITE (patrón `"normos"`, verificado contra el binario de NORMOS a
6·10⁻⁶ mm/s):

$$\pm 5.3261 \quad \pm 3.0836 \quad \pm 0.8410 \;\; \text{mm/s a 33.0 T}$$

Su razón $g_1/g_0 = 0.5714$ es la que midieron Violet y Pipkorn para α-Fe a 298 K
(J. Appl. Phys. **42**, 4339, 1971: $g_0 = 3.9098$, $g_1 = 2.2342$ mm/s). Con este
patrón Fitbauer y NORMOS dan el mismo campo.

---

## El patrón histórico (hasta la v5.2.4)

Hasta la v5.2.4 Fitbauer usaba

$$\pm 5.3285 \quad \pm 3.0835 \quad \pm 0.8385 \;\; \text{mm/s a 33.0 T}$$

presentado en el código como «patrón publicado de α-Fe». **No tiene fuente
publicada**: son las constantes del software previo del laboratorio, donde eran
el patrón a 32.95 T. En la v4.0.2 se quitó el
32.95 T y los mismos números pasaron a ser el patrón a 33.0 T. Su razón $g_1/g_0$
(0.5724) no corresponde a ningún par de momentos medido.

El argumento de entonces para no usar los momentos nucleares («un α-Fe leía 33.12 T»)
era circular: se debía a reutilizar una calibración hecha con el patrón anterior. Con la
Vmax calibrada con el mismo patrón, cualquier patrón da 33.0 T en el α-Fe.

El histórico sigue disponible como `"legacy"` (alias `"alpha_fe"`), en
*Ajuste › Opciones avanzadas de ajuste › Convenios*, para reproducir sesiones antiguas.

---

## Calibraciones hechas con el patrón histórico

Una Vmax calibrada con el patrón histórico no es la que da 33.0 T con el nuevo. Fitbauer
la convierte sola:

$$V_{\max}^{\text{normos}} = 0.999623 \cdot V_{\max}^{\text{histórico}}$$

El factor sale de ajustar con el patrón nuevo (BHF fijo a 33 T, anchura única, 3:2:1,
escala libre) un α-Fe generado con el histórico, como hace la calibración. Vale a
±4·10⁻⁶ para anchuras de 0.18 a 0.40 mm/s.

- Cada calibración guarda el patrón con que se hizo (`sextet_pattern`). Las locales
  que no lo dicen, de Fitbauer anteriores a la v5.3.0, se toman como históricas y se
  aplican convertidas. El panel y el informe lo indican.
- Las de la API web son las VMAX calibradas en NORMOS, ya con su patrón: se aplican
  tal cual. La API marca `sextet_pattern = "legacy"` en las que la web guardó con su
  ajuste antiguo (botón «Almacenar velocidad», hasta que la web adoptó este patrón), y
  esas sí se convierten.
- Al cambiar de patrón en el menú, la calibración fijada se vuelve a aplicar convertida.
- Un fichero que trae su propio eje de velocidad no se toca: su escala es absoluta.
- Las sesiones guardadas conservan su patrón (las que no lo dicen se hicieron con el
  histórico) y se reproducen exactamente.

Con la calibración convertida, el BHF de una muestra cambia menos de un 0.01 % (unos
0.002 T); δ y ΔEQ, un −0.038 %.

---

## La escala absoluta de velocidad

Llamar 33.0 T al α-Fe es una convención. Violet y Pipkorn miden para α-Fe a 298 K una
separación de las líneas externas de 10.612 mm/s; el patrón de NORMOS a 33.0 T da
10.652. Calibrar con «α-Fe = 33.0 T» deja la escala de velocidad un **0.38 %** por
encima de la suya, igual que en NORMOS. Afecta a δ y ΔEQ (≈0.004 mm/s en un δ de
1 mm/s), no al BHF. Para la máxima exactitud en δ y ΔEQ, compárese con las posiciones
de línea medidas del α-Fe.

---

## Escalado con el campo

Las posiciones escalan **linealmente** con el patrón de 33.0 T:

$$v_{0,j} = \delta + q_j \Delta E_Q + v_j^{(33\mathrm{T})}\frac{B_{hf}}{33.0},
\qquad q = [\tfrac12,-\tfrac12,-\tfrac12,-\tfrac12,-\tfrac12,\tfrac12]$$

implementado en `fe57_sextet_positions(bhf_t)` y en `core.physics`. El Hamiltoniano
completo, la relajación y los núcleos de distribución leen el mismo patrón activo.

---

## Verificación práctica

Cargar un espectro de α-Fe y ajustarlo con la Vmax calibrada: el BHF debe salir muy
cerca de **33.0 T**. Una desviación sistemática indica un problema de Vmax o de punto de
doblado, no del modelo.

> **Regla del repositorio.** Campo de referencia **33.0 T**, patrón por defecto el de
> los momentos nucleares (`"normos"`). `core.constants` es la fuente única; las
> calibraciones guardan su patrón y se convierten con `convert_vmax`.
