# Ajuste con distribución P(BHF)

Backend experimental, todavía sin integrar en GUI.

## Archivos

- `mossbauer_distribution.py`: motor Hesse-Rübartsch (`P(BHF) >= 0` + regularización de segundas diferencias).
- `mossbauer_ws5.py`: lectura/doblado de `.ws5` y sidecars Normos.
- `mossbauer_bhf_pipeline.py`: función de alto nivel lista para endpoint web.
- `fit_bhf_distribution_cli.py`: script CLI para pruebas y generación de `.dat`/`.png`.

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
- `*_bhf_alpha_scan.dat/.png`: L-curve simple si se usa `--scan-alpha --plot`.

## Mezcla con subespectros nítidos

En la GUI, modo `P(BHF)`, se puede activar `sumar componentes activos nítidos`.
Entonces los componentes activos 1–3 se suman a la distribución como singlete,
doblete o sextete según la forma elegida en cada pestaña. El ajuste recalcula
`P(BHF)` y la amplitud/profundidad de cada subespectro nítido; los demás
parámetros se cambian manualmente o con la opción experimental de refinar
`δ` y `Γ` globales de la distribución.

Para añadir una fase tipo Fe metálico residual con BHF fijo desde CLI:

```bash
python3 fit_bhf_distribution_cli.py muestra.ws5 \
  --bmin 15 --bmax 45 --nbins 50 \
  --alpha 0.1 --gamma 0.18 \
  --sharp-bhf 33 --sharp-gamma 0.14 \
  --plot --scan-alpha
```

El/los sextetes `--sharp-bhf` se ajustan con amplitud no negativa, pero no se regularizan.

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

# payload ya es serializable a JSON por defecto
print(payload["BHF_centers"])
print(payload["probability"])
print(payload["fitted_curve"])
```

## Notas prácticas

- En la GUI hay presets de `alpha`: fino, medio y suave. También hay botón `L-curve α` para estimar un valor razonable.
- `alpha` es el parámetro crítico. Usar `--scan-alpha` para ver el compromiso residuo/suavidad.
- Si `B_min=0`, el ajuste puede usar bajo campo para absorber contribuciones no magnéticas o fondo. Para una distribución magnética pura suele ser mejor probar `--bmin 15` o `--bmin 20`.
- `delta`, `quad` y `gamma` son globales/fijos para toda la distribución en esta primera versión.
