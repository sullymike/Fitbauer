# Distribuciones en espectros Mössbauer

Motor de distribución continua integrado en la GUI y disponible por CLI y API Python.
El tratamiento completo (física, matemáticas, ejemplos) está en el manual de usuario,
capítulo *Distribuciones* y sus anexos.

## Archivos principales

- `mossbauer_distribution.py`: el motor — histograma Hesse–Rübartsch (`P ≥ 0` con regularización Tikhonov, TV o MaxEnt), formas paramétricas (gaussiana, VBF, binomial, fija) y distribuciones 2D.
- `mossbauer_ws5.py`: lectura/doblado de `.ws5` y sidecars Normos.
- `mossbauer_bhf_pipeline.py`: función de alto nivel para el endpoint web.
- `fit_bhf_distribution_cli.py`: CLI sin interfaz; escribe ficheros `.dat`, `.json` y `.png`.

## Modos de distribución disponibles en la GUI

| Modo | Variable distribuida | Núcleo | Uso típico |
|---|---|---|---|
| `P(BHF)` | Campo hiperfino $B_{hf}$ | sextetes | Ferritas, óxidos con desorden magnético |
| `P(ΔEQ)` | Desdoblamiento cuadrupolar | dobletes (B = 0) | Silicatos, vidrios, fases amorfas paramagnéticas |
| `P(IS)` | Desplazamiento isomérico | singletes, o dobletes con el ΔEQ global (B = 0) | Distribución de entornos electrónicos |
| `P(BHF, ΔEQ) 2D` | Campo + cuadrupolo | sextetes | Nanopartículas con acoplamiento $B$–$Q$ |
| `P(IS, ΔEQ) 2D` | IS + cuadrupolo | dobletes | Dobletes anchos con variación simultánea de centro y separación |
| `P(BHF, IS) 2D` | Campo + IS | sextetes | Fases magnéticas con distribución de entornos (sensible a calibración) |

En `P(ΔEQ)` una opción avanzada cambia los dobletes por sextetes de primer orden con
campo fijo («Sextete con campo fijo»), para una fase magnética de campo único con el
corrimiento cuadrupolar distribuido. Cada variable recuerda su propia malla (mín/máx/bins).

Todos los modos admiten **componentes nítidos** simultáneos: los componentes activos del
panel discreto (sextetes, dobletes, singletes o modelos de relajación) se suman con
amplitud libre no negativa, ajustada junto a la distribución.

## Formas de la distribución

| Forma | Qué se ajusta | Regularización |
|---|---|---|
| **Histograma** (Hesse–Rübartsch) | un peso libre por bin | α (Tikhonov, TV o MaxEnt) |
| **Gaussiana** | una gaussiana (A, μ, σ) — VBF con N = 1 | ninguna |
| **VBF** (Rancourt–Ping) | suma de N gaussianas, cada una con su área A, centro μ y anchura σ | ninguna |
| **Binomial** (como `DISTRI=3` de NORMOS-DIST) | modelo de vecinos de soluto: valor sin vecinos, cambio por vecino, concentración | ninguna |
| **Fija** | una distribución cargada de fichero; solo su amplitud | ninguna |

- **Cotas de la anchura de las gaussianas.** En Gaussiana y VBF la anchura σ, común a
  todas las gaussianas, se puede acotar con **σ mín / σ máx** (unidades de la variable;
  0 = automático: desde 0.001, o un cuarto del paso de malla en 2D, hasta la anchura del
  rango). Útil cuando, con varias gaussianas, una colapsa en un pico o se ensancha hasta
  absorber el fondo.
- **Formas 2D.** Los modos 2D ofrecen Histograma (un peso por celda, con αx y αy),
  Gaussiana (una gaussiana bivariante con centro, anchuras σx/σy y correlación ρ) y VBF
  (N gaussianas bivariantes, una por sitio). Gaussiana y VBF tienen un par σ mín / σ máx
  por eje y ajustan δ, ΔEQ y Γ dentro de la misma optimización, así que tardan segundos.

## Regularización

### Tikhonov (segunda diferencia, por defecto)

Penaliza la curvatura de la distribución:

$$\Phi(\mathbf{p}) = \|W^{1/2}(X\mathbf{z} - \mathbf{y})\|^2 + \alpha \|L\mathbf{p}\|^2$$

donde $L$ es el operador de segunda diferencia. Favorece distribuciones suaves. α es
adimensional (log α ≈ 0 es el equilibrio natural datos/suavidad); el botón **L-curve α**
recorre α, marca el codo (máxima curvatura) y permite elegir otro valor con un clic.

### Variación total (L1, para fases discretas)

Penaliza la variación total de la distribución:

$$\Phi(\mathbf{p}) = \|W^{1/2}(X\mathbf{z} - \mathbf{y})\|^2 + \alpha \|D_1\mathbf{p}\|_1$$

Favorece distribuciones con transiciones bruscas (mezcla de pocas fases bien definidas),
al contrario que Tikhonov, que suaviza. Se resuelve por mínimos cuadrados reponderados.

### Máxima entropía (MaxEnt)

Maximiza la entropía $S(P) = -\sum_j P_j \log(P_j/m_j)$: la distribución menos
comprometida compatible con los datos, positiva por construcción y sin oscilaciones
espurias. Problema convexo, resuelto con L-BFGS-B y gradiente analítico.

### Anclaje de los bordes

Un peso opcional (BETA1/BETA2 de NORMOS-DIST) lleva P hacia 0 en el primer y el último
bin, para que el histograma no apile peso en el borde cuando la distribución se sale de
la malla. El diagnóstico `edge_pileup` avisa cuando ocurre; ampliar la malla es lo primero.

## Física del núcleo

- **Perfil de línea**: Lorentziana o Voigt exacto.
- **Correlación δ(x) / ΔEQ(x)**: las pendientes κδ y κq hacen variar δ y ΔEQ linealmente
  con la variable de la malla, $\delta_j = \delta + \kappa_\delta\,(x_j - x_{\text{ref}})$,
  con $x_{\text{ref}}$ el centro de la malla. En `P(BHF)` son dδ/dH y dΔEQ/dH; en
  `P(ΔEQ)` solo existe dδ/dΔEQ (el acoplamiento de Rancourt–Ping); en `P(IS)` solo
  dΔEQ/dδ. 0 = modelo clásico. Histograma, VBF y binomial.
- **Núcleo hamiltoniano** (histograma `P(BHF)`): cada columna sale del Hamiltoniano
  magnético + cuadrupolar completo con promedio de polvo, con asimetría η del EFG — el
  análogo de EXACT de NORMOS-DIST.
- **Fuente polarizada** (histograma `P(BHF)`): peine de 36 líneas fuente × absorbente,
  como METHOD=4/POLAR de NORMOS-DIST.

## Refinado global en la GUI

δ, ΔEQ, Γ, las pendientes κ y los parámetros de los componentes nítidos se pueden refinar
junto con la distribución desmarcando su candado: un bucle externo no lineal los optimiza
y, en cada paso, la distribución se resuelve de nuevo de forma exacta (esquema VARPRO).

## El gráfico de la distribución

**Ver distribución…** abre el gráfico de P(x) tras el ajuste. Además de la distribución:

- **Banda 1σ de P** (histograma con Tikhonov o TV): la dispersión de cada bin en 100
  reajustes sobre el modelo ajustado con ruido de la σ de los datos (escalada por el χ²
  reducido). Respeta P ≥ 0, a diferencia de la covarianza linealizada de los pesos, que
  con picos rodeados de bins a cero salía varias veces más ancha. Es una incertidumbre
  bin a bin: los bins vecinos están anticorrelacionados, así que las magnitudes
  integradas (área de un pico, ⟨x⟩) son mucho más precisas de lo que sugiere la banda.
  No incluye la incertidumbre de los globales (δ, Γ…).
- **Curva de correlación** (si alguna pendiente κ es distinta de 0): en un eje derecho,
  la recta δ(x) o ΔEQ(x) que aplicó el núcleo, con su banda 1σ si se refinó la pendiente
  o el global, y κ ± σ en la leyenda. Si |κ| no supera claramente su σ, la correlación no
  está demostrada. Continua donde P tiene peso, punteada fuera.

Cada superposición tiene una casilla que la oculta; la elección se recuerda.

## Datos e informes

- **Archivo → Exportar distribución…** (o **Guardar datos…** en el diálogo de P(x) o del
  mapa 2D) guarda la distribución en texto tabulado: variable, P normalizada, σ de P,
  peso y, con pendientes κ, la curva δ(x)/ΔEQ(x) con su σ; en 2D, una fila por celda.
  La cabecera (`#`) resume forma, α, χ², ν, χ²ᵣ, AIC, BIC y los globales con su σ.
- **Guardar ajuste…** exporta velocidad, datos, modelo de la distribución y residuo, con
  la misma tabla de P al final.
- El **informe** (completo y reducido, Markdown y PDF) recoge en modo distribución el
  montaje, la bondad del ajuste (N, χ², k, ν, χ²ᵣ, AIC y BIC —misma definición que el
  ajuste discreto, para comparar modelos sobre el mismo espectro—, RMS, autocorrelación
  lag-1 y test de rachas del residuo), los globales con su σ, la distribución, los
  nítidos y los avisos (p. ej. peso acumulado en el borde de la malla). El PDF añade la
  figura de P(x) o el mapa 2D.

## Avisos del panel de distribución

El panel avisa, con un enlace a la ayuda, de combinaciones que ajustan bien pero no
significan lo que parece:

- **P(IS) con Γ libre**: una distribución de desplazamientos isoméricos ensancha todas
  las líneas por igual y se confunde con Γ. Fije Γ a la anchura instrumental.
- **P(ΔEQ) con sextetes de campo fijo**: el núcleo de primer orden solo vale si ΔEQ es
  pequeño frente al desdoblamiento magnético.
- **P(IS, ΔEQ) con dobletes**: el espectro solo ve la distribución de cada línea, así que
  el mapa IS–ΔEQ no es único. Para la correlación IS–ΔEQ de vidrios use `P(ΔEQ)` con κδ,
  que sí es identificable.

## Uso CLI básico

```bash
python3 fit_bhf_distribution_cli.py muestra.ws5 \
  --bmin 0 --bmax 50 --nbins 50 \
  --gamma 0.18 --alpha 0.01 \
  --plot --scan-alpha

# P(ΔEQ) con dobletes; P(IS) con singletes:
python3 fit_bhf_distribution_cli.py muestra.adt --variable quad --bmax 3
python3 fit_bhf_distribution_cli.py muestra.adt --variable delta --bmin -1 --bmax 2

# Formas: VBF con dos gaussianas y anchuras acotadas; binomial como NORMOS (5 % de soluto):
python3 fit_bhf_distribution_cli.py muestra.adt --shape vbf --vbf-components 2 \
  --vbf-sigma-min 0.5 --vbf-sigma-max 3
python3 fit_bhf_distribution_cli.py muestra.adt --shape binomial \
  --binomial-conc 5 --binomial-start 33 --binomial-step -2.5

# Regularizador del histograma: tikhonov (defecto), tv, maxent:
python3 fit_bhf_distribution_cli.py muestra.adt --reg-mode maxent

# 2D: histograma P(BHF, ΔEQ), dos gaussianas bivariantes, P(IS, ΔEQ):
python3 fit_bhf_distribution_cli.py muestra.adt --dist-2d --qmin -1 --qmax 1
python3 fit_bhf_distribution_cli.py muestra.adt --dist-2d --shape vbf --vbf-components 2
python3 fit_bhf_distribution_cli.py muestra.adt --dist-2d --pair delta-quad
```

En la CLI δ, ΔEQ, Γ y las pendientes κ son valores fijos (`--delta`, `--quad`, `--gamma`,
`--delta-slope`, `--quad-slope`); el refinado global es una función de la GUI.

Salidas (prefijo `<entrada>_bhf` o `--out-prefix`):

- `*_spectrum.dat`: velocidad, datos, ajuste, residuo, cuentas dobladas.
- `*_distribution.dat`: malla, P, P normalizada (1D).
- `*_distribution2d.dat` más `*_<x>_axis.dat` y `*_<y>_axis.dat` (2D).
- `*_summary.json`: parámetros y métricas; con VBF, los (A, μ, σ) ajustados y las cotas de σ aplicadas.
- `*_plot.png` y `*_alpha_scan.dat/.png` con `--plot` / `--scan-alpha`.

La lista completa de opciones es `python3 fit_bhf_distribution_cli.py -h` y el anexo
*Herramientas de línea de comandos* del manual.

## Uso desde Python / endpoint

```python
from mossbauer_bhf_pipeline import fit_ws5_bhf_distribution

payload = fit_ws5_bhf_distribution(
    "muestra.ws5",
    bmin=0,
    bmax=50,
    nbins=50,
    alpha=1e-2,
    gamma=0.18,
    sharp_bhf=[33.0],   # opcional
)

print(payload["BHF_centers"])
print(payload["probability"])
print(payload["fitted_curve"])
```

## Notas prácticas

- `alpha` es el parámetro crítico del histograma: use `--scan-alpha` o el botón
  `L-curve α` de la GUI y compruebe que los rasgos principales de P son estables
  alrededor del valor elegido. Las formas paramétricas no usan α.
- Si `B_min=0`, el ajuste puede usar bajo campo para absorber contribuciones no
  magnéticas. Para una distribución magnética pura, pruebe `--bmin 15` o `--bmin 20`.
- Empiece por lo simple: Gaussiana o VBF con 1–2 componentes antes que un histograma
  libre, y 1D antes que 2D.
- En distribuciones 2D la malla puede ser grande ($N_x \times N_y$ bins): use
  regularizaciones $\alpha_x$, $\alpha_y$ independientes y compruebe la estabilidad
  variando ambas. Ver el anexo de distribuciones bidimensionales del manual.
- Las distribuciones con IS (`P(IS)`, `P(IS, ΔEQ)`, `P(BHF, IS)`) son muy sensibles a la
  calibración de velocidad y al folding point. Ver el anexo de distribuciones P(IS) del manual.
- La corrección de espesor se aplica al modelo discreto; los ajustes de distribución
  suponen absorbente delgado.
