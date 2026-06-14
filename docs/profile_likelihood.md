# Confidence Intervals via Profile Likelihood

Module: `core/profile_likelihood.py`  
GUI integration: discrete fit panel → **Errors → Profile likelihood**

---

## Motivation

The 1σ errors from Gaussian covariance (`core/fit_engine.py`, §Covariance)
assume that the cost surface is quadratic around the optimum. For parameters
with active bounds, strong correlations or asymmetric cost curves, that
approximation can be pessimistic or even incorrect. Profile likelihood gives
exact intervals (for the given model and statistical weights) without assuming
quadraticity.

---

## Definition

Let $\hat{\mathbf{x}}$ be the optimal parameter vector with cost $\mathcal{C}_{\min}$.
The **profile likelihood** of parameter $x_k$ is:

$$\mathcal{C}_P(x_k) = \min_{\mathbf{x}_{-k}} \mathcal{C}(\mathbf{x})$$

i.e., the minimum of the cost with respect to all other parameters, with $x_k$ fixed.
The difference:

$$\Delta\chi^2(x_k) = 2\bigl[\mathcal{C}_P(x_k) - \mathcal{C}_{\min}\bigr]$$

follows (asymptotically) a $\chi^2$ distribution with 1 degree of freedom. Confidence
intervals are obtained as the values of $x_k$ where:

$$\Delta\chi^2 = 1 \quad\Rightarrow\quad 1\sigma \;\;(\approx 68.3\%)$$
$$\Delta\chi^2 = 4 \quad\Rightarrow\quad 2\sigma \;\;(\approx 95.4\%)$$

---

## Implementation in Fitbauer

### Adaptive scan

For each free parameter $x_k$, values are scanned over an interval centred on
$\hat{x}_k$ and the remaining free parameters are refitted at each point. The
interval and number of scan points are adjusted automatically to ensure that the
$\Delta\chi^2$ curve reaches level 4 (2σ) on both sides.

### Crossing location (`find_crossing`)

Given the array of scanned values $v_k$ and the corresponding $\Delta\chi^2$,
the crossing with a level $\ell$ (1 or 4) is located by **linear interpolation**:

$$x_\ell = x_i + \frac{(\ell - \Delta\chi^2_i)(\Delta\chi^2_{i+1} - \Delta\chi^2_i)^{-1}(x_{i+1} - x_i)}{1}$$

in the segment where $(\Delta\chi^2_i - \ell)(\Delta\chi^2_{i+1} - \ell) \leq 0$.
The first crossing to the right of the optimum (interval $+$) and the first to the
left (interval $-$) are sought. If the curve does not reach the level on one side,
the corresponding crossing is reported as `None` (parameter at a bound or ill-conditioned).

### Asymmetric intervals (`asymmetric_intervals`)

```python
from core.profile_likelihood import asymmetric_intervals

result = asymmetric_intervals(scan_values, d_chi2, best_value)
# result: {"minus_1s": float|None, "plus_1s": float|None,
#           "minus_2s": float|None, "plus_2s": float|None}
```

The returned values are **positive distances** from the optimum to the crossing:
$x_k^+ - \hat{x}_k$ (to the right) and $\hat{x}_k - x_k^-$ (to the left).

---

## Comparison with covariance errors

| Aspect | Covariance (Gaussian) | Profile likelihood |
|---|---|---|
| Assumption | Quadratic cost | None (asymptotic) |
| Computational cost | Low (SVD of final Jacobian) | High (N_scan × refit per parameter) |
| Valid with active bounds | No (underestimates error) | Yes |
| Strong correlations | Can be unreliable | Captured implicitly |
| Interval asymmetry | No (symmetric) | Yes |

---

## When to use profile likelihood

- Parameters with active bounds (e.g. depth near 0, BHF near its minimum).
- Doublet with small quadrupole splitting (high δ–ΔEQ correlation).
- Sextets with free intensities correlated with depth.
- Whenever parametric bootstrap and covariance give very different results.

---

## Implementation notes

- `core/profile_likelihood.py` contains only pure functions (no GUI or Qt dependency).
- The scan is launched from the GUI using threads to avoid blocking the interface.
- Profile results are shown in the diagnostics panel and included in the PDF report
  if the corresponding option is enabled.
- If $\Delta\chi^2$ never exceeds the level (flat curve), the parameter may be
  non-identifiable or at an active bound: interpret with caution.
