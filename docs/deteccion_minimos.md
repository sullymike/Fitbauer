# Detección automática de mínimos en espectros Mössbauer

Módulo: `gui/minima_analysis.py` · Clase: `MinimaAnalysisMixin`  
Acción de GUI: **Ajuste → Inicializar desde mínimos**

---

## Motivación

Antes de ajustar, el usuario necesita un punto de partida razonable para los
parámetros de cada componente. La detección automática de mínimos localiza los
picos de absorción en el espectro (mínimos de transmisión) y los convierte en
parámetros iniciales de sextetes, dobletes y singletes. El algoritmo combina
detección multi-escala CWT y canal directo para ser robusto frente a:

- sextetes con líneas solapadas o de anchuras variables;
- dobletes estrechos que el CWT a escalas grandes podría fundir en un pico;
- espectros con ruido alto o línea base inclinada.

---

## Paso 1: absorción y línea base

La absorción neta se calcula como:

$$A(v) = \max\!\bigl(b(v) - y(v),\; 0\bigr)$$

donde $b(v) = b_0 + s_0 v$ es una línea base lineal estimada sobre el 70 % superior
de los datos (por mínimos cuadrados). Si hay menos de 4 puntos en esa zona alta, se
usa el percentil 90 como constante de referencia.

---

## Paso 2: umbrales de ruido

Se suaviza $A(v)$ con media móvil gruesa (ventana ≈ $N/80$ canales) y se estima el
ruido con la MAD (desviación absoluta mediana) de las diferencias:

$$\sigma_n = 1.4826 \cdot \mathrm{median}|D_A - \mathrm{median}(D_A)|, \quad D_A = \Delta A$$

Los umbrales son:

$$h_{\min} = \max(f_h \cdot A_{\max},\; 4\sigma_n,\; 5\times10^{-4})$$
$$p_{\min} = \max(f_p \cdot A_{\max},\; 2.5\sigma_n,\; 3\times10^{-4})$$
$$d_{\min} = \max(\delta_{\min},\; 2\Delta v)$$

con factores $f_h$, $f_p$, separación mínima $\delta_{\min}$ configurables en
`core/param_overrides.py` (tabla `_PD`).

---

## Paso 3: detección CWT multi-escala (ondícula Ricker)

La transformada wavelet continua (CWT) con la ondícula Ricker (Mexican hat):

$$\psi(x, a) = A\!\left(1 - \frac{x^2}{a^2}\right)\exp\!\left(-\frac{x^2}{2a^2}\right), \quad A = \frac{2}{\sqrt{3a}\,\pi^{1/4}}$$

se aplica a $A(v)$ para escalas $a \in [a_{\min}, a_{\max}]$ (en canales), donde
el rango físico Mössbauer de anchuras de línea (0.12–2.0 mm/s) determina:

$$a_{\min} = \max\!\left(2,\;\left\lfloor\frac{0.12}{\Delta v}\right\rfloor\right), \qquad
a_{\max} = \max\!\left(a_{\min}+3,\;\left\lfloor\frac{2.0}{\Delta v}\right\rfloor\right)$$

**Implementación con `np.convolve`** (reemplaza `scipy.signal.cwt` eliminada en SciPy 1.12):
el kernel se convuelve con la señal en modo `"same"`. Para evitar que el kernel
supere la longitud de la señal (que provocaría un `ValueError` por la semántica de
`mode="same"` con señales cortas), la semilongitud del kernel se clampea:

$$\mathrm{half} = \min\!\left(\max(5a, 3),\; \frac{N-1}{2}\right)$$

La **cresta CWT** (ridge) es el máximo entre escalas en cada canal:

$$R(v_i) = \max_{a}\!\left[\max\!\left(\mathrm{CWT}(v_i, a),\; 0\right)\right]$$

Los picos en $R(v_i)$ (canal CWT) se detectan con `scipy.signal.find_peaks` usando
los umbrales $h_{\min}$, $p_{\min}$ y $d_{\min}$.

---

## Paso 4: canal directo (suavizado fino)

Para rescatar dobletes estrechos que el CWT a escalas grandes podría fundir en un
único "pico", se buscan picos también en la absorción con suavizado fino (ventana
~0.15 mm/s, siempre impar). La absorción suavizada se renormaliza al rango de
$A_{\max}$ antes de buscar picos con los mismos umbrales.

---

## Paso 5: fusión de candidatos

Los índices CWT ($I_\mathrm{CWT}$) y directos ($I_\mathrm{dir}$) se fusionan
eliminando duplicados y artefactos:

1. Los picos directos son la lista base (evitan el artefacto de "pico de valle"
   que el CWT a escalas grandes puede generar entre dos líneas de un doblete).
2. Se añade un pico CWT solo si **no** está entre dos picos directos consecutivos
   (señal de artefacto de valle) y no es duplicado de uno ya presente (distancia ≤ 1 canal).

---

## Paso 6: estimación de anchura FWHM

Para cada pico fusionado:

- Si hay respuesta CWT positiva, la **escala de mayor respuesta** determina la
  anchura: $\Gamma \approx 2 \cdot a_\mathrm{best} \cdot \Delta v$.
- Si no hay respuesta CWT positiva, se estima el FWHM directamente sobre la señal
  suavizada fina: se buscan los cruces al 50 % del valor del pico a izquierda y derecha.

---

## Paso 7: selección final y ordenación

Los picos se ordenan por profundidad suavizada (descendente) y se seleccionan
greedily, añadiendo un pico solo si está a más de $d_{\min}$ de todos los ya
seleccionados. Se retienen como máximo 15 picos.

---

## Paso 8: clasificación e inicialización de componentes

Una vez detectados los mínimos, la lógica de inicialización (`on_init_from_minima`)
asigna componentes:

1. **Heurística de forma** (`_depth_profile_hint`): si un pico domina en profundidad
   con posición < 2.5 mm/s → Singlete; si dos picos son comparables y la separación
   está en el rango doblete → Doblete.
2. **Búsqueda de sextete** (`_best_sextet_from_peaks`): ajuste lineal
   $v_j = \delta + (B_{hf}/B_0) \cdot r_j^{(33)}$ por mínimos cuadrados sobre
   combinaciones de 5–6 picos; se acepta si el RMS < umbral y el BHF es físico.
3. **Estimación con 2 picos visibles** (`_try_2peak_sextet_estimate`): si sólo hay
   2 picos, se estima el BHF a partir del espaciado externo (líneas 1–2 o 5–6).
4. **Componentes restantes**: los picos no asignados forman dobletes (si la separación
   está en rango físico) o singletes adicionales.

Las profundidades iniciales se reescalan para que el modelo propuesto no exceda la
absorción máxima de los datos.

---

## Notas de implementación

- La CWT reemplaza a `scipy.signal.cwt + ricker` (eliminadas en SciPy 1.12).
- El clampeo del kernel (`half = min(max(5a,3), (N-1)//2)`) corrige el
  `ValueError: could not broadcast input array` que ocurría en señales cortas
  (~254 puntos tras el recorte de bordes del folding).
- Los parámetros de la detección (umbrales, rangos, tolerancias) son configurables
  en `core/param_overrides.py` mediante `_PD` (peak detection) y `_FI` (fit init).
