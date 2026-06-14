# Intervalos de confianza por verosimilitud perfilada

Módulo: `core/profile_likelihood.py`  
Integración GUI: panel de ajuste discreto → **Errores → Perfil likelihood**

---

## Motivación

Los errores 1σ por covarianza gaussiana (`core/fit_engine.py`, §Covarianza)
asumen que la superficie de coste es cuadrática en torno al óptimo. Para
parámetros con bordes activos, correlaciones fuertes o curvas de coste asimétricas,
esa aproximación puede ser pesimista o incluso errónea. La verosimilitud perfilada
da intervalos exactos (para el modelo y los pesos estadísticos dados) sin asumir
cuadraticidad.

---

## Definición

Sea $\hat{\mathbf{x}}$ el vector de parámetros óptimo con coste $\mathcal{C}_{\min}$.
La **verosimilitud perfilada** del parámetro $x_k$ es:

$$\mathcal{C}_P(x_k) = \min_{\mathbf{x}_{-k}} \mathcal{C}(\mathbf{x})$$

es decir, el mínimo del coste respecto a todos los demás parámetros, con $x_k$ fijado.
La diferencia:

$$\Delta\chi^2(x_k) = 2\bigl[\mathcal{C}_P(x_k) - \mathcal{C}_{\min}\bigr]$$

sigue (asintóticamente) una distribución $\chi^2$ con 1 grado de libertad. Los
intervalos de confianza se obtienen como los valores de $x_k$ donde:

$$\Delta\chi^2 = 1 \quad\Rightarrow\quad 1\sigma \;\;(\approx 68.3\%)$$
$$\Delta\chi^2 = 4 \quad\Rightarrow\quad 2\sigma \;\;(\approx 95.4\%)$$

---

## Implementación en Fitbauer

### Escaneo adaptativo

Para cada parámetro libre $x_k$, se barren valores en un intervalo centrado en
$\hat{x}_k$ y se reajusta con el resto de parámetros libres en cada punto. El
intervalo y el número de puntos de escaneo se ajustan automáticamente para asegurar
que la curva $\Delta\chi^2$ alcance el nivel 4 (2σ) a ambos lados.

### Localización de cruces (`find_crossing`)

Dado el array de valores escaneados $v_k$ y los $\Delta\chi^2$ correspondientes,
se localiza el cruce con un nivel $\ell$ (1 o 4) por **interpolación lineal**:

$$x_\ell = x_i + \frac{(\ell - \Delta\chi^2_i)(\Delta\chi^2_{i+1} - \Delta\chi^2_i)^{-1}(x_{i+1} - x_i)}{1}$$

en el segmento donde $(\Delta\chi^2_i - \ell)(\Delta\chi^2_{i+1} - \ell) \leq 0$.
Se busca el primer cruce a la derecha del óptimo (intervalo $+$) y el primero a la
izquierda (intervalo $-$). Si la curva no llega al nivel en un lado, el cruce
correspondiente se reporta como `None` (parámetro en borde o mal condicionado).

### Intervalos asimétricos (`asymmetric_intervals`)

```python
from core.profile_likelihood import asymmetric_intervals

result = asymmetric_intervals(scan_values, d_chi2, best_value)
# result: {"minus_1s": float|None, "plus_1s": float|None,
#           "minus_2s": float|None, "plus_2s": float|None}
```

Los valores devueltos son **distancias positivas** desde el óptimo al cruce:
$x_k^+ - \hat{x}_k$ (a la derecha) y $\hat{x}_k - x_k^-$ (a la izquierda).

---

## Comparación con errores por covarianza

| Aspecto | Covarianza (gaussiana) | Perfil likelihood |
|---|---|---|
| Supuesto | Coste cuadrático | Ninguno (asintótico) |
| Coste computacional | Bajo (SVD del Jacobiano final) | Alto (N_scan × reajuste por parámetro) |
| Válido con bordes activos | No (subestima error) | Sí |
| Correlaciones fuertes | Puede ser poco fiable | Capturado implícitamente |
| Asimetría del intervalo | No (simétrico) | Sí |

---

## Cuándo usar el perfil likelihood

- Parámetros con bordes activos (p.ej. profundidad cerca de 0, BHF cerca del mínimo).
- Doblete con separación cuadrupolar pequeña (alta correlación δ–ΔEQ).
- Sextetes con intensidades libres correlacionadas con la profundidad.
- Siempre que el bootstrap paramétrico y la covarianza den resultados muy distintos.

---

## Notas de implementación

- `core/profile_likelihood.py` contiene sólo funciones puras (sin dependencia de GUI ni Qt).
- El escaneo se lanza desde la GUI mediante hilos para no bloquear la interfaz.
- Los resultados del perfil se muestran en el panel de diagnóstico y se incluyen en
  el informe PDF si se activa la opción correspondiente.
- Si $\Delta\chi^2$ nunca supera el nivel (curva plana), el parámetro puede ser
  no identificable o estar en un borde activo: interpretar con cautela.
