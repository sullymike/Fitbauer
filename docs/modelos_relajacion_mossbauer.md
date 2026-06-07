# Implementación de modelos de relajación magnética en un programa de ajuste Mössbauer

## Contexto

Se desea ampliar un programa de ajuste de espectros Mössbauer que actualmente permite:

1. Ajuste de componentes discretas: singletes, dobletes y sextetos.
2. Ajuste de distribuciones de campo hiperfino mediante el método de Hesse–Rübartsch.
3. Análisis de áreas, posiciones, anchuras, desplazamiento isomérico, desdoblamiento cuadrupolar y campo hiperfino.

El objetivo es añadir un módulo de **relajación magnética**, especialmente útil para el análisis de:

- nanopartículas magnéticas;
- ferritas;
- magnetita, maghemita y otros óxidos de hierro;
- materiales con comportamiento superparamagnético;
- espectros con sextetos parcialmente colapsados, líneas anchas o coexistencia aparente de doblete y sexteto.

El nuevo módulo no debe sustituir los ajustes ya existentes, sino complementarlos.

---

# 1. Concepto físico

En nanopartículas magnéticas, el momento magnético de la partícula puede fluctuar entre orientaciones equivalentes. En la escala temporal Mössbauer, el núcleo de \(^{57}\mathrm{Fe}\) puede observar:

- un campo hiperfino prácticamente estático, si la partícula está bloqueada;
- un campo hiperfino parcialmente promediado, si la relajación es intermedia;
- un campo hiperfino promediado a cero, si la relajación es rápida.

Por tanto, el programa debe describir la transición continua entre:

\[
\text{sexteto magnético bloqueado}
\]

\[
\text{sexteto ensanchado/deformado por relajación}
\]

\[
\text{doblete o singlete superparamagnético aparente}
\]

No debe tratarse únicamente como un ajuste empírico de tipo:

\[
\text{sexteto} + \text{doblete}
\]

salvo como aproximación inicial o fenomenológica.

Debe existir una componente específica de **relajación magnética**.

---

# 2. Nuevo tipo de componente: `MagneticRelaxationComponent`

Añadir una nueva clase o tipo de componente, por ejemplo:

```text
MagneticRelaxationComponent
```

o alternativamente:

```text
relaxation_sextet
```

Esta componente debe representar un sexteto magnético cuyo campo hiperfino cambia estocásticamente con una determinada frecuencia de relajación.

## Parámetros mínimos

```text
area
isomer_shift
quadrupole_shift / quadrupole_splitting
hyperfine_field
linewidth
relaxation_rate
line_intensity_ratio
background contribution, if needed
```

Donde:

```text
relaxation_rate = nu = 1/tau
```

con unidades preferentemente en:

```text
s^-1
```

o, de forma más práctica para el ajuste:

```text
log10(nu)
```

Esto es recomendable porque las tasas de relajación pueden variar muchos órdenes de magnitud.

---

# 3. Límites físicos que debe reproducir el modelo

El modelo debe comportarse correctamente en los tres regímenes principales.

## 3.1. Relajación lenta

Si:

\[
\nu \ll 10^7\ \mathrm{s^{-1}}
\]

O, de forma general:

\[
\tau \gg \tau_M
\]

el espectro debe tender a un sexteto magnético convencional.

Resultado esperado:

```text
sexteto nítido, similar al ajuste discreto ya existente
```

---

## 3.2. Relajación intermedia

Si:

\[
\nu \sim 10^7 - 10^9\ \mathrm{s^{-1}}
\]

el espectro debe mostrar:

```text
ensanchamiento de líneas
pérdida de resolución
campo hiperfino aparente reducido
posible asimetría
colapso parcial del sexteto
```

Este es el régimen más importante para nanopartículas magnéticas.

---

## 3.3. Relajación rápida

Si:

\[
\nu \gg 10^9\ \mathrm{s^{-1}}
\]

el campo hiperfino debe promediarse y el espectro debe tender a:

```text
doblete cuadrupolar
```

O bien a:

```text
singlete, si QS ≈ 0
```

No debe aparecer un sexteto artificial en este límite.

---

# 4. Modelo matemático inicial: Blume–Tjon simplificado

Implementar inicialmente un modelo tipo **Blume–Tjon**, donde el campo hiperfino cambia estocásticamente entre dos orientaciones opuestas:

\[
+B_\mathrm{hf} \leftrightarrow -B_\mathrm{hf}
\]

con una tasa de salto:

\[
\nu = \frac{1}{\tau}
\]

Como primera versión, puede implementarse un modelo de relajación de dos estados con matriz de transición:

\[
W =
\begin{pmatrix}
-\nu & \nu \\
\nu & -\nu
\end{pmatrix}
\]

El cálculo espectral debe permitir obtener la forma de línea resultante para distintas tasas de relajación.

La implementación debe ser modular para permitir añadir posteriormente modelos más complejos:

```text
two-state relaxation
three-state relaxation
six-state relaxation
isotropic relaxation
anisotropic relaxation
relaxation with field distribution
relaxation with particle size distribution
```

---

# 5. Alternativa práctica para una primera versión

Si implementar el modelo Blume–Tjon completo resulta demasiado complejo en una primera fase, se puede crear una versión aproximada, claramente marcada como **fenomenológica**, que interpole entre:

```text
sexteto bloqueado
componente relajada/intermedia
doblete superparamagnético
```

Esta aproximación debe cumplir las siguientes condiciones:

1. Conservar el área total.
2. Permitir ajustar la fracción bloqueada y la fracción superparamagnética.
3. No interpretar automáticamente el doblete como una fase paramagnética distinta.
4. Exportar los parámetros como “modelo fenomenológico de relajación”, no como modelo dinámico exacto.

Modelo inicial aceptable:

\[
S(v)=A_b S_\mathrm{sextet}(v) + A_\mathrm{spm} S_\mathrm{doublet}(v)
\]

con:

\[
A_b + A_\mathrm{spm}=A_\mathrm{total}
\]

Opcionalmente:

\[
A_b(T)=\int_{V_c(T)}^\infty f(V)\,dV
\]

\[
A_\mathrm{spm}(T)=\int_0^{V_c(T)} f(V)\,dV
\]

Donde \(V_c(T)\) se calcula a partir de la condición de bloqueo.

---

# 6. Relación con Néel–Arrhenius

Añadir opcionalmente un modo físico basado en la relación:

\[
\tau_N=\tau_0 \exp\left(\frac{K V}{k_B T}\right)
\]

O equivalentemente:

\[
\nu = \nu_0 \exp\left(-\frac{K V}{k_B T}\right)
\]

## Parámetros

```text
temperature
anisotropy_constant_K
particle_volume
attempt_time_tau0
attempt_frequency_nu0
```

Valores iniciales razonables:

```text
tau0 = 1e-9 s
nu0 = 1e9 s^-1
```

El usuario debe poder fijar o ajustar:

```text
K
V
tau0
temperature
```

El programa debe poder calcular:

```text
tau_N
nu
blocking_temperature
```

mediante:

\[
T_B = \frac{K V}{k_B \ln(\tau_M/\tau_0)}
\]

Donde \(\tau_M\) es el tiempo característico de observación Mössbauer.

---

# 7. Distribución de tamaños de partícula

Añadir soporte para una distribución de tamaños o volúmenes.

La muestra real no tiene un único tamaño, por lo que debe permitirse:

```text
lognormal diameter distribution
normal diameter distribution
user-defined distribution
```

Se recomienda implementar primero una distribución lognormal de diámetros:

\[
f(d)=\frac{1}{d\sigma\sqrt{2\pi}}
\exp\left[-\frac{(\ln d-\mu)^2}{2\sigma^2}\right]
\]

Y convertir diámetro a volumen suponiendo partículas esféricas:

\[
V=\frac{\pi d^3}{6}
\]

El espectro total será:

\[
S(v)=\int f(d)\,S(v,d,T,K)\,dd
\]

O, de forma discretizada:

\[
S(v)=\sum_i w_i S(v,d_i,T,K)
\]

## Parámetros de usuario

```text
number_of_size_bins
d_min
d_max
mean_diameter
sigma_lognormal
```

---

# 8. Integración con Hesse–Rübartsch

El programa ya implementa distribuciones Hesse–Rübartsch. El nuevo módulo debe poder combinarse con ellas.

Debe permitir los siguientes modelos.

---

## 8.1. Solo distribución estática

```text
Hesse-Ruebartsch P(Bhf)
```

Uso: desorden estático de campos hiperfinos.

---

## 8.2. Solo relajación dinámica

```text
MagneticRelaxationComponent
```

Uso: fluctuación temporal del campo hiperfino.

---

## 8.3. Distribución estática + relajación

\[
S(v)=\int P(B_\mathrm{hf})\,S_\mathrm{relax}(v,B_\mathrm{hf},\nu)\,dB_\mathrm{hf}
\]

O discretizado:

\[
S(v)=\sum_i P_i\,S_\mathrm{relax}(v,B_i,\nu)
\]

Esto permite modelar nanopartículas con:

```text
desorden superficial
distribución de campos
relajación superparamagnética
```

---

## 8.4. Distribución de campos + distribución de tasas

Modelo más general:

\[
S(v)=\sum_i \sum_j w_{ij} S(v,B_i,\nu_j)
\]

O, si se asume independencia:

\[
S(v)=\sum_i \sum_j P(B_i)P(\nu_j)S(v,B_i,\nu_j)
\]

---

# 9. Interfaz de usuario

Añadir en la interfaz un nuevo tipo de componente:

```text
Magnetic relaxation / superparamagnetic relaxation
```

## Opciones de modo

```text
Empirical sextet-doublet relaxation
Blume-Tjon two-state relaxation
Neel-Arrhenius size-distribution relaxation
Hesse-Ruebartsch + relaxation
```

## Parámetros visibles

```text
Area
IS / CS
QS / epsilon
Bhf
linewidth
relaxation rate nu
log10(nu)
temperature
tau0
Keff
particle diameter
diameter distribution sigma
blocked fraction
superparamagnetic fraction
```

Cada parámetro debe poder fijarse o liberarse durante el ajuste.

---

# 10. Resultados que debe devolver

Además de los parámetros habituales del ajuste Mössbauer, el programa debe devolver:

```text
relaxation_rate_nu
relaxation_time_tau
log10_nu
blocked_fraction
superparamagnetic_fraction
mean_particle_diameter, if applicable
sigma_diameter, if applicable
effective_anisotropy_Keff, if applicable
blocking_temperature, if applicable
mean_hyperfine_field
field_distribution_width, if applicable
```

También debe exportar las siguientes gráficas:

```text
spectrum fit
residuals
individual components
P(Bhf), if used
P(log10 nu), if used
particle size distribution, if used
blocked fraction vs temperature, if multiple temperatures are fitted
```

---

# 11. Ajuste simultáneo de varios espectros

Añadir, si es posible, ajuste global de varios espectros medidos a diferentes temperaturas.

Ejemplo:

```text
spectrum_300K
spectrum_150K
spectrum_80K
spectrum_4K
```

## Parámetros globales compartidos

```text
isomer_shift model
Keff
particle size distribution
tau0
mean diameter
sigma diameter
```

## Parámetros dependientes de temperatura

```text
temperature
Bhf(T)
QS(T)
linewidth(T)
blocked fraction
relaxation rate
```

Esto es importante porque un único espectro rara vez permite separar de forma fiable:

```text
distribución de campos
relajación magnética
distribución de tamaños
fases reales
```

---

# 12. Advertencias interpretativas

El programa debe advertir al usuario cuando:

1. Un doblete coexistente con un sexteto pueda deberse a relajación superparamagnética y no necesariamente a una fase paramagnética.
2. Una distribución \(P(B_\mathrm{hf})\) muy ancha hacia campos bajos pueda estar absorbiendo efectos dinámicos.
3. Los parámetros \(K\), \(V\), \(\tau_0\) y \(T_B\) estén fuertemente correlacionados.
4. Un único espectro no sea suficiente para extraer una distribución de tamaños única.
5. El ajuste no sea físicamente identificable.

---

# 13. Validaciones y pruebas

Crear espectros sintéticos para validar el módulo.

---

## Caso 1: relajación lenta

```text
Bhf = 49 T
IS = 0.30 mm/s
QS = 0.00 mm/s
linewidth = 0.25 mm/s
nu = 1e5 s^-1
```

Resultado esperado:

```text
sexteto prácticamente normal
```

---

## Caso 2: relajación intermedia

```text
Bhf = 49 T
IS = 0.30 mm/s
QS = 0.00 mm/s
linewidth = 0.25 mm/s
nu = 1e8 s^-1
```

Resultado esperado:

```text
sexteto ensanchado y parcialmente colapsado
```

---

## Caso 3: relajación rápida

```text
Bhf = 49 T
IS = 0.30 mm/s
QS = 0.65 mm/s
linewidth = 0.25 mm/s
nu = 1e11 s^-1
```

Resultado esperado:

```text
doblete superparamagnético aparente
```

---

## Caso 4: distribución de tamaños

```text
mean_diameter = 8 nm
sigma_lognormal = 0.25
Keff = 1e4 J/m3
T = 300 K
tau0 = 1e-9 s
```

Resultado esperado:

```text
mezcla de partículas bloqueadas y superparamagnéticas
```

---

# 14. Criterios de implementación

La implementación debe ser modular y compatible con el código existente.

## Estructura sugerida

```text
Component
 ├── Singlet
 ├── Doublet
 ├── Sextet
 ├── HesseRuebartschDistribution
 ├── MagneticRelaxationComponent
 ├── SizeDistributionRelaxation
 └── HybridDistributionRelaxation
```

## Funciones sugeridas

```python
calculate_sextet(v, isomer_shift, quadrupole_shift, bhf, linewidth, intensities)

calculate_doublet(v, isomer_shift, quadrupole_splitting, linewidth)

calculate_relaxation_spectrum(
    v,
    isomer_shift,
    quadrupole_shift,
    bhf,
    linewidth,
    relaxation_rate,
    model="blume_tjon"
)

calculate_neel_relaxation_time(K, V, T, tau0=1e-9)

calculate_blocking_temperature(K, V, tau_m, tau0=1e-9)

calculate_size_distribution(d_values, mean_d, sigma, distribution="lognormal")

calculate_size_distribution_relaxation_spectrum(
    v,
    d_values,
    weights,
    K,
    T,
    tau0,
    base_hyperfine_params
)

calculate_hybrid_HR_relaxation(
    v,
    B_values,
    B_weights,
    relaxation_rates,
    relaxation_weights
)
```

---

# 15. Prioridad de desarrollo

Implementar por fases.

---

## Fase 1

Añadir modelo fenomenológico:

```text
sexteto bloqueado + doblete superparamagnético
```

con conservación de área y fracciones ajustables.

---

## Fase 2

Añadir parámetro de tasa de relajación:

```text
relaxation_rate
log10(nu)
```

con interpolación o modelo dinámico simplificado.

---

## Fase 3

Implementar modelo Blume–Tjon de dos estados.

---

## Fase 4

Añadir distribución de tamaños mediante Néel–Arrhenius.

---

## Fase 5

Permitir ajuste global de espectros a varias temperaturas.

---

# 16. Requisito interpretativo importante

No presentar el doblete superparamagnético como una fase química independiente por defecto.

En la salida del programa, etiquetar la componente como:

```text
superparamagnetic / fast relaxation component
```

Y no como:

```text
paramagnetic phase
```

salvo que el usuario lo indique explícitamente.

---

# 17. Versión corta para pasar a una IA

Amplía el programa Mössbauer actual, que ya ajusta singletes, dobletes, sextetos y distribuciones Hesse–Rübartsch \(P(B_\mathrm{hf})\), añadiendo un módulo de relajación magnética/superparamagnética para nanopartículas.

Debe incluir una nueva componente `MagneticRelaxationComponent` con parámetros:

```text
área
IS
QS/epsilon
Bhf
anchura
intensidades
tasa de relajación nu = 1/tau
```

La tasa de relajación debe ser preferentemente ajustable como:

```text
log10(nu)
```

El modelo debe reproducir los límites de:

1. Relajación lenta: sexteto convencional.
2. Relajación intermedia: sexteto ensanchado y parcialmente colapsado.
3. Relajación rápida: doblete/singlete superparamagnético aparente.

Implementar primero una versión fenomenológica:

```text
sexteto bloqueado + doblete superparamagnético
```

con conservación de área.

Después implementar un modelo tipo Blume–Tjon de dos estados:

\[
+B_\mathrm{hf} \leftrightarrow -B_\mathrm{hf}
\]

Y finalmente una opción basada en Néel–Arrhenius:

\[
\tau_N=\tau_0\exp\left(\frac{KV}{k_BT}\right)
\]

con distribución lognormal de tamaños.

El módulo debe poder combinarse con Hesse–Rübartsch mediante:

\[
S(v)=\sum_i P(B_i)S_\mathrm{relax}(v,B_i,\nu)
\]

Y, en una versión avanzada, con una distribución conjunta de campos y tasas:

\[
S(v)=\sum_i\sum_j w_{ij}S(v,B_i,\nu_j)
\]

El programa debe exportar:

```text
nu
tau
log10(nu)
fracción bloqueada
fracción superparamagnética
Keff
tamaño medio
distribución de tamaños
T_B
```

cuando proceda.

Debe incluir advertencias para evitar interpretar automáticamente el doblete como una fase paramagnética real, ya que puede corresponder a una fracción superparamagnética por relajación rápida.
