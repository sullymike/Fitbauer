# Distributions in Mössbauer Spectra

Continuous distribution engine integrated in the GUI and available via CLI and Python API.

## Main files

- `mossbauer_distribution.py`: Hesse–Rübartsch engine (`P(BHF) ≥ 0` + Tikhonov/TV regularization).
- `mossbauer_ws5.py`: reading/folding of `.ws5` files and Normos sidecars.
- `mossbauer_bhf_pipeline.py`: high-level function for the web endpoint.
- `fit_bhf_distribution_cli.py`: CLI script for testing and generating `.dat`/`.png` files.

## Distribution modes available in the GUI

| Mode | Distributed variable | Typical use |
|---|---|---|
| `P(BHF)` | Hyperfine field $B_{hf}$ | Ferrites, oxides with magnetic disorder |
| `P(ΔEQ)` | Quadrupole splitting | Silicates, glasses, paramagnetic amorphous phases |
| `P(δ)` | Isomer shift | Distribution of electronic environments |
| `P(BHF, ΔEQ) 2D` | Field + quadrupole | Nanoparticles with $B$–$Q$ coupling |
| `P(δ, ΔEQ) 2D` | IS + quadrupole | Wide doublets with simultaneous variation of centre and separation |
| `P(BHF, δ) 2D` | Field + IS | Magnetic phases with environmental distribution (sensitive to calibration) |

All modes support simultaneous sharp components (sextets, doublets or singlets with free non-negative amplitude fitted jointly with the distribution).

## Regularization

### Tikhonov (second difference, default)

Penalizes the curvature of the distribution:

$$\Phi(\mathbf{p}) = \|W^{1/2}(X\mathbf{z} - \mathbf{y})\|^2 + \alpha \|L\mathbf{p}\|^2$$

where $L$ is the second-difference operator. Favours smooth distributions. The `alpha` selector is available in the GUI; preset buttons (fine / medium / smooth) and `L-curve α` for automatic estimation by maximum curvature or GCV.

### Total Variation (L1, for discrete phases)

Penalizes the total variation of the distribution:

$$\Phi(\mathbf{p}) = \|W^{1/2}(X\mathbf{z} - \mathbf{y})\|^2 + \alpha \|D_1\mathbf{p}\|_1$$

Favours distributions with sharp transitions (mixture of a few well-defined phases), unlike Tikhonov which smooths. Selectable in the distribution mode options panel.

## Basic CLI usage

```bash
python3 fit_bhf_distribution_cli.py sample.ws5 \
  --bmin 0 --bmax 50 --nbins 50 \
  --gamma 0.18 --alpha 0.01 \
  --plot --scan-alpha
```

Outputs:

- `*_bhf_spectrum.dat`: velocity, data, fit, residual, folded counts.
- `*_bhf_distribution.dat`: BHF, P, normalized P.
- `*_bhf_summary.json`: parameters and metrics.
- `*_bhf_plot.png`: spectrum + residual + P(BHF).
- `*_bhf_alpha_scan.dat/.png`: L-curve if `--scan-alpha --plot` is used.

## Mixing with sharp components

In the GUI, with `P(BHF)` mode active, you can enable _sum active sharp components_. Active components 1–3 are added to the distribution as a singlet, doublet or sextet. The fit recalculates `P(BHF)` and the amplitude of each sharp component simultaneously.

To add a residual metallic-Fe-type phase with a fixed BHF from the CLI:

```bash
python3 fit_bhf_distribution_cli.py sample.ws5 \
  --bmin 15 --bmax 45 --nbins 50 \
  --alpha 0.1 --gamma 0.18 \
  --sharp-bhf 33 --sharp-gamma 0.14 \
  --plot --scan-alpha
```

## Thickness correction with distributions

When the sample is thick (absorption > ~15 %), thickness correction can also be enabled in distribution mode. Distribution mode uses an **inverse transform** that recovers linearity in the weights:

$$A_\text{obs}(v) = -C \ln\!\left(1 - \frac{b + sv - y(v)}{C}\right)$$

The regularized solver works on $A_\text{obs}$ (linear in $P$) and the model is re-saturated to compute residuals. An external VARPRO loop refines $(b, s, C)$ while the internal solver recovers $P$ at each iteration. See `docs/correccion_espesor.tex` for the full derivation.

## Usage from Python / endpoint

```python
from mossbauer_bhf_pipeline import fit_ws5_bhf_distribution

payload = fit_ws5_bhf_distribution(
    "sample.ws5",
    bmin=0,
    bmax=50,
    nbins=50,
    alpha=1e-2,
    gamma=0.18,
    sharp_bhf=[33.0],   # optional
)

print(payload["BHF_centers"])
print(payload["probability"])
print(payload["fitted_curve"])
```

## Practical notes

- `alpha` is the critical parameter: use `--scan-alpha` or the GUI's `L-curve α` button to choose it.
- If `B_min=0`, the fit may use low-field values to absorb non-magnetic contributions. For a purely magnetic distribution, try `--bmin 15` or `--bmin 20`.
- `delta`, `quad` and `gamma` are global/fixed for the entire distribution in 1D mode.
- For 2D distributions: the grid can be large ($N_x \times N_y$ bins); use independent regularizations $\alpha_x$, $\alpha_y$ and verify stability by varying both. See `docs/distribuciones_2d_mossbauer.tex`.
- Distributions with IS (`P(δ)`, `P(δ, ΔEQ)`): very sensitive to velocity calibration and folding point. See `docs/distribuciones_is_mossbauer.tex`.
