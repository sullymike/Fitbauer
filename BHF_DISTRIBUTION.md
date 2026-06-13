# Distribuciones en espectros Mössbauer

Motor de distribución continua integrado en la GUI y disponible por CLI y API Python.

## Archivos principales

- `mossbauer_distribution.py`: motor Hesse–Rübartsch (`P(BHF) ≥ 0` + regularización Tikhonov/TV).
- `mossbauer_ws5.py`: lectura/doblado de `.ws5` y sidecars Normos.
- `mossbauer_bhf_pipeline.py`: función de alto nivel para endpoint web.
- `fit_bhf_distribution_cli.py`: script CLI para pruebas y generación de `.dat`/`.png`.

## Modos de distribución disponibles en la GUI

| Modo | Variable distribuida | Uso típico |
|---|---|---|
| `P(BHF)` | Campo hiperfino $B_{hf}$ | Ferritas, óxidos con desorden magnético |
| `P(ΔEQ)` | Desdoblamiento cuadrupolar | Silicatos, vidrios, fases amorfas paramagnéticas |
| `P(δ)` | Desplazamiento isomérico | Distribución de entornos electrónicos |
| `P(BHF, ΔEQ) 2D` | Campo + cuadrupolo | Nanopartículas con acoplamiento $B$–$Q$ |
| `P(δ, ΔEQ) 2D` | IS + cuadrupolo | Dobletes anchos con variación simultánea de centro y separación |
| `P(BHF, δ) 2D` | Campo + IS | Fases magnéticas con distribución de entornos (sensible a calibración) |

Todos los modos admiten componentes nítidas simultáneas (sextetes, dobletes o singletes con amplitud libre no negativa ajustada junto a la distribución).

## Regularización

### Tikhonov (segunda diferencia, por defecto)

Penaliza la curvatura de la distribución:

$$\Phi(\mathbf{p}) = \|W^{1/2}(X\mathbf{z} - \mathbf{y})\|^2 + \alpha \|L\mathbf{p}\|^2$$

donde $L$ es el operador de segundas diferencias. Favorece distribuciones suaves. Selector `alpha` en la GUI; botones de preset (fino / medio / suave) y `L-curve α` para estimación automática por máxima curvatura o GCV.

### Total Variation (L1, para fases discretas)

Penaliza la variación total de la distribución:

$$\Phi(\mathbf{p}) = \|W^{1/2}(X\mathbf{z} - \mathbf{y})\|^2 + \alpha \|D_1\mathbf{p}\|_1$$

Favorece distribuciones con transiciones abruptas (mezcla de pocas fases bien definidas), a diferencia de Tikhonov que suaviza. Seleccionable en el panel de opciones del modo distribución.

## Uso CLI básico

```bash
python3 fit_bhf_distribution_cli.py muestra.ws5 \
  --bmin 0 --bmax 50 --nbins 50 \
  --gamma 0.18 --alpha 0.01 \
  --plot --scan-alpha
```

Salidas:

- `*_bhf_spectrum.dat`: velocidad, datos, ajuste, residuo, cuentas dobladas.
- `*_bhf_distribution.dat`: BHF, P, P normalizada.
- `*_bhf_summary.json`: parámetros y métricas.
- `*_bhf_plot.png`: espectro + residual + P(BHF).
- `*_bhf_alpha_scan.dat/.png`: L-curve si se usa `--scan-alpha --plot`.

## Mezcla con componentes nítidos

En la GUI, con modo `P(BHF)` activado, se puede activar _sumar componentes activos nítidos_. Los componentes activos 1–3 se suman a la distribución como singlete, doblete o sextete. El ajuste recalcula `P(BHF)` y la amplitud de cada nítido simultáneamente.

Para añadir una fase tipo Fe metálico residual con BHF fijo desde CLI:

```bash
python3 fit_bhf_distribution_cli.py muestra.ws5 \
  --bmin 15 --bmax 45 --nbins 50 \
  --alpha 0.1 --gamma 0.18 \
  --sharp-bhf 33 --sharp-gamma 0.14 \
  --plot --scan-alpha
```

## Corrección de espesor con distribuciones

Cuando la muestra es gruesa (absorción > ~15 %), se puede activar la corrección de espesor también en modo distribución. El modo distribución usa una **transformada inversa** que recupera la linealidad en los pesos:

$$A_\text{obs}(v) = -C \ln\!\left(1 - \frac{b + sv - y(v)}{C}\right)$$

El solver regularizado trabaja sobre $A_\text{obs}$ (lineal en $P$) y el modelo se re-satura para calcular residuos. Un lazo VARPRO externo refina $(b, s, C)$ mientras el solver interno recupera $P$ en cada iteración. Ver `docs/correccion_espesor.tex` para la derivación completa.

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

- `alpha` es el parámetro crítico: usar `--scan-alpha` o el botón `L-curve α` de la GUI para elegirlo.
- Si `B_min=0`, el ajuste puede usar bajo campo para absorber contribuciones no magnéticas. Para distribución magnética pura, probar `--bmin 15` o `--bmin 20`.
- `delta`, `quad` y `gamma` son globales/fijos para toda la distribución en el modo 1D.
- Para distribuciones 2D: la malla puede ser grande ($N_x \times N_y$ bins); usar regularizaciones $\alpha_x$, $\alpha_y$ independientes y verificar estabilidad variando ambas. Ver `docs/distribuciones_2d_mossbauer.tex`.
- Distribuciones con IS (`P(δ)`, `P(δ, ΔEQ)`): muy sensibles a calibración de velocidad y folding point. Ver `docs/distribuciones_is_mossbauer.tex`.
