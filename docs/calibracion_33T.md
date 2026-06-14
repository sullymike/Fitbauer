# Calibración del campo hiperfino: patrón α-Fe a 33.0 T

Fuente: `core/constants.py` (`LINE_POS_33T`, `_BASE_POSITIONS`, `fe57_sextet_positions`)

---

## El problema de calibrar el BHF

En un sextete magnético de Fe-57, las seis líneas se separan proporcionalmente al
campo hiperfino $B_{hf}$. Para convertir las **posiciones de línea medidas** (en mm/s)
a un **campo en teslas** hace falta un factor de conversión. Hay dos formas de
obtenerlo:

1. **Desde los momentos nucleares** (cálculo "de libro"): usando $\mu_N$, los factores
   $g$ del estado fundamental e excitado, y la energía $\gamma$. Da posiciones teóricas.
2. **Desde un patrón de velocidad publicado**: usando las posiciones medidas de un
   material de referencia bien caracterizado (α-Fe metálico a temperatura ambiente).

**Fitbauer usa la segunda forma**, igual que Normos.

---

## Por qué NO se usan los momentos nucleares

El cálculo teórico desde los momentos nucleares da un desdoblamiento magnético
**~0.4 % menor** que el patrón experimental de α-Fe:

| Origen | Separación líneas externas (1–6) |
|---|---|
| Teórico (momentos nucleares) | ~5.309 mm/s |
| Experimental (α-Fe publicado) | 5.328 mm/s |

Si se calibrara desde la teoría, un espectro de α-Fe real ajustaría a un BHF
**~0.1 T demasiado alto** (sesgo sistemático). Por eso `core/constants.py` advierte
explícitamente de no sustituir las posiciones publicadas por valores teóricos
(ver CHANGELOG v4.0.2 / v4.0.3).

Los datos nucleares (`MU_N`, `E_GAMMA`, `G_GROUND`, `G_EXCITED`) **siguen en el módulo
como referencia/documentación**, pero NO se usan para calibrar.

---

## Patrón de velocidad de α-Fe a 33.0 T

El campo hiperfino del α-Fe metálico a temperatura ambiente es, por convención,
**33.0 T**. Las posiciones publicadas de sus seis líneas (en mm/s, respecto al centro)
son:

$$\pm 5.329 \quad \pm 3.084 \quad \pm 0.839 \;\; \text{mm/s}$$

En el código, las posiciones base se almacenan ya simetrizadas:

```python
_BASE_POSITIONS = np.array([-10.657, -6.167, -1.677, 1.677, 6.167, 10.657]) * 0.5
#                = [-5.3285, -3.0835, -0.8385, 0.8385, 3.0835, 5.3285] mm/s
LINE_POS_33T = fe57_sextet_positions(33.0)
```

---

## Escalado lineal con el campo

Para un campo arbitrario $B_{hf}$, las posiciones escalan **linealmente** respecto al
patrón de 33.0 T:

$$v_j(B_{hf}) = v_j^{(33\mathrm{T})} \cdot \frac{B_{hf}}{33.0}$$

implementado en `fe57_sextet_positions(bhf_t)`. A esto se suman después el
desplazamiento isomérico $\delta$ y el patrón cuadrupolar de primer orden
$q_j \cdot \Delta E_Q$ (ver `docs/manual_mossbauer.tex`, sección de sextete):

$$v_{0,j} = \delta + q_j \Delta E_Q + v_j^{(33\mathrm{T})}\frac{B_{hf}}{33.0}$$

con el patrón cuadrupolar de primer orden:

```python
LINE_QUAD_PATTERN = [0.5, -0.5, -0.5, -0.5, -0.5, 0.5]
```

---

## Constantes relacionadas

| Constante | Valor | Uso |
|---|---|---|
| `BHF_DEFAULT_T` | 33.0 | Campo de referencia y valor inicial por defecto |
| `_BASE_POSITIONS` | ±5.329 / ±3.084 / ±0.839 (×escala interna) | Patrón α-Fe publicado |
| `LINE_POS_33T` | `fe57_sextet_positions(33.0)` | Posiciones a 33 T usadas por el motor de ajuste |
| `LINE_QUAD_PATTERN` | [+½,−½,−½,−½,−½,+½] | Patrón cuadrupolar de primer orden |
| `DIST_BHF_RANGE` | (0.0, 60.0) | Rango por defecto de la malla `P(BHF)` |

---

## Verificación práctica

Para comprobar la calibración: cargar `data_sample/hierro_metalico_alphaFe.adt` (o la
calibración del ESRF) y ajustar. El BHF resultante debe salir muy cerca de **33.0 T**
y las posiciones de las líneas coincidir con el patrón publicado. Cualquier desviación
sistemática indica un problema de $V_{\max}$ (calibración de velocidad) o de folding
point, no del modelo físico.

> **Regla del repositorio.** El campo de referencia es **33.0 T** con el patrón de
> velocidad publicado de α-Fe (±0.839 / ±3.084 / ±5.329 mm/s). `LINE_POS_33T` vive en
> `core.constants`. No derivar posiciones de los momentos nucleares.
