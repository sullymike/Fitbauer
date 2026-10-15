# Distributions in Mössbauer Spectra

Continuous distribution engine integrated in the GUI and available via CLI and Python API.
The full treatment (physics, mathematics, worked examples) is in the user manual,
chapter *Distributions* and its appendices.

## Main files

- `mossbauer_distribution.py`: the engine — Hesse–Rübartsch histogram (`P ≥ 0` with Tikhonov, TV or MaxEnt regularization), parametric shapes (Gaussian, VBF, binomial, fixed, Czjzek) and 2D distributions.
- `mossbauer_ws5.py`: reading/folding of `.ws5` files and Normos sidecars.
- `mossbauer_bhf_pipeline.py`: high-level function for the web endpoint.
- `fit_bhf_distribution_cli.py`: headless CLI; writes `.dat`, `.json` and `.png` files.

## Distribution modes available in the GUI

| Mode | Distributed variable | Kernel | Typical use |
|---|---|---|---|
| `P(BHF)` | Hyperfine field $B_{hf}$ | sextets | Ferrites, oxides with magnetic disorder |
| `P(ΔEQ)` | Quadrupole splitting | doublets (B = 0) | Silicates, glasses, paramagnetic amorphous phases |
| `P(IS)` | Isomer shift | singlets, or doublets with the global ΔEQ (B = 0) | Distribution of electronic environments |
| `P(BHF, ΔEQ) 2D` | Field + quadrupole | sextets | Nanoparticles with $B$–$Q$ coupling |
| `P(IS, ΔEQ) 2D` | IS + quadrupole | doublets | Wide doublets with simultaneous variation of centre and separation |
| `P(BHF, IS) 2D` | Field + IS | sextets | Magnetic phases with environmental distribution (sensitive to calibration) |

In `P(ΔEQ)` an advanced option replaces the doublets by first-order sextets with a
fixed field («Sextet with fixed field»), for a magnetic phase with a single field and a
distributed quadrupole shift. Each variable remembers its own grid (min/max/bins).

All modes support simultaneous **sharp components**: the active components of the
discrete panel (sextets, doublets, singlets or relaxation models) are added with a free
non-negative amplitude, fitted together with the distribution.

## Distribution shapes

| Shape | What is fitted | Regularization |
|---|---|---|
| **Histogram** (Hesse–Rübartsch) | one free weight per bin | α (Tikhonov, TV or MaxEnt) |
| **Gaussian** | one Gaussian (A, μ, σ) — VBF with N = 1 | none |
| **VBF** (Rancourt–Ping) | sum of N Gaussians, each with its area A, centre μ and width σ | none |
| **Binomial** (as NORMOS-DIST `DISTRI=3`) | solute-neighbour model: value without neighbours, change per neighbour, concentration | none |
| **Fixed** | a distribution loaded from a file; only its amplitude | none |
| **Czjzek** (`P(ΔEQ)` with doublets only) | \|ΔEQ\| of a random electric field gradient: $P \propto \Delta^4 e^{-\Delta^2/2\sigma^2}$; σ only | none |
| **Extended Czjzek** (Le Caër–Brand) | random on top of an ordered environment ΔEQ₀: non-central χ with 5 degrees of freedom; σ and ΔEQ₀ | none |

- **Czjzek.** In glasses and amorphous materials the ΔEQ distribution is usually not
  Gaussian. If the charges around the Fe are random, the 5 independent components of the
  field gradient are Gaussian and ΔEQ, proportional to their norm, follows a χ
  distribution with 5 degrees of freedom: asymmetric, zero at ΔEQ = 0, mode at 2σ, mean
  ≈ 2.13σ and a fixed relative width (≈ 0.32). The extended version adds an ordered
  tensor of norm ΔEQ₀; with ΔEQ₀ ≫ σ it tends to a Gaussian. Doublets only see the
  marginal of |ΔEQ| (neither η nor the sign). It accepts κδ and sharp components; the
  report gives σ and ΔEQ₀ with their errors. To choose between Czjzek, Gaussian or
  Histogram, compare their AIC/BIC. It is NORMOS-DIST's `DISTRI=4` with `METHOD=6`,
  with σ² = STG² + DTQ² (checked against its binary), and such `.JOB` files are
  imported with this shape. σ and ΔEQ₀ have their controls in the panel (starting
  point of the fit, with a «Fixed» box); in the CLI, `--czjzek-sigma`/`--czjzek-delta0`
  and `--fix-czjzek-sigma`/`--fix-czjzek-delta0`.

- **Width bounds of the Gaussians.** In the Gaussian and VBF shapes the width σ, common
  to all the Gaussians, can be bounded with **σ min / σ max** (units of the variable;
  0 = automatic: from 0.001, or a quarter of the grid step in 2D, up to the width of the
  range). Useful when, with several Gaussians, one collapses into a spike or widens until
  it absorbs the background.
- **2D shapes.** The 2D modes offer Histogram (one weight per cell, with αx and αy),
  Gaussian (one bivariate Gaussian with centre, widths σx/σy and correlation ρ) and VBF
  (N bivariate Gaussians, one per site). Gaussian and VBF have a σ min / σ max pair per
  axis and fit δ, ΔEQ and Γ inside the same optimization, so they take seconds.

## Regularization

### Tikhonov (second difference, default)

Penalizes the curvature of the distribution:

$$\Phi(\mathbf{p}) = \|W^{1/2}(X\mathbf{z} - \mathbf{y})\|^2 + \alpha \|L\mathbf{p}\|^2$$

where $L$ is the second-difference operator. Favours smooth distributions. α is
dimensionless (log α ≈ 0 is the natural data/smoothness balance); the **L-curve α**
button scans α, marks the elbow (maximum curvature) and lets you pick another value with a click.

### Total Variation (L1, for discrete phases)

Penalizes the total variation of the distribution:

$$\Phi(\mathbf{p}) = \|W^{1/2}(X\mathbf{z} - \mathbf{y})\|^2 + \alpha \|D_1\mathbf{p}\|_1$$

Favours distributions with sharp transitions (mixture of a few well-defined phases),
unlike Tikhonov which smooths. Solved by iteratively reweighted least squares.

### Maximum entropy (MaxEnt)

Maximizes the entropy $S(P) = -\sum_j P_j \log(P_j/m_j)$: the least committed
distribution compatible with the data, positive by construction and without spurious
oscillations. Convex problem, solved with L-BFGS-B and an analytical gradient.

### Edge anchoring

An optional weight (NORMOS-DIST BETA1/BETA2) pushes P towards 0 at the first and last bin,
so the histogram cannot pile up weight at the edge when the distribution leaves the grid.
The `edge_pileup` diagnostic warns when that happens; widening the grid is the first fix.

## Physics of the kernel

- **Line profile**: Lorentzian or exact Voigt.
- **δ(x) / ΔEQ(x) correlation**: slopes κδ and κq make δ and ΔEQ vary linearly with the
  grid variable, $\delta_j = \delta + \kappa_\delta\,(x_j - x_{\text{ref}})$, with
  $x_{\text{ref}}$ the centre of the grid. In `P(BHF)` they are dδ/dH and dΔEQ/dH; in
  `P(ΔEQ)` only dδ/dΔEQ exists (the Rancourt–Ping coupling); in `P(IS)` only dΔEQ/dδ.
  0 = classical model. Histogram, VBF, binomial and Czjzek.
- **Hamiltonian kernel** (histogram `P(BHF)`): each column from the full
  magnetic + quadrupole Hamiltonian with powder average, with EFG asymmetry η — the
  analogue of NORMOS-DIST EXACT.
- **Polarized source** (histogram `P(BHF)`): 36-line source × absorber comb, as
  NORMOS-DIST METHOD=4/POLAR.

## Global refinement in the GUI

δ, ΔEQ, Γ, the κ slopes and the parameters of the sharp components can be refined
together with the distribution by unlocking them: an outer non-linear loop optimizes
them and, at each step, the distribution is re-solved exactly (VARPRO scheme).

## The distribution plot

**Show distribution…** opens the plot of P(x) after the fit. Besides the distribution:

- **1σ band of P** (histogram with Tikhonov or TV): the spread of each bin over 100
  refits on the fitted model plus noise of the data σ (scaled by the reduced χ²). It
  respects P ≥ 0, unlike the linearized covariance of the weights, which with peaks
  surrounded by zero bins came out several times wider. It is a bin-by-bin
  uncertainty: neighbouring bins are anticorrelated, so integrated quantities (area of
  a peak, ⟨x⟩) are much more precise than the band suggests. It does not include the
  uncertainty of the global values (δ, Γ…).
- **Correlation curve** (if a κ slope is non-zero): on a right axis, the δ(x) or ΔEQ(x)
  line the kernel applied, with its 1σ band when the slope or the global value was
  refined, and κ ± σ in the legend. If |κ| does not clearly exceed its σ, the
  correlation is not established. Solid where P has weight, dotted elsewhere.

Each overlay has a check that hides it; the choice is remembered.

## Data and reports

- **File → Export distribution…** (or **Save data…** in the P(x) or 2D map dialog) saves
  the distribution as tab-separated text: variable, normalised P, σ of P, weight and,
  with κ slopes, the δ(x)/ΔEQ(x) curve with its σ; in 2D, one row per cell. The header
  (`#`) summarises shape, α, χ², ν, reduced χ², AIC, BIC and the globals with their σ.
- **Save fit…** exports velocity, data, the distribution model and the residual, with the
  same P table at the end.
- In distribution mode the **report** (full and short, Markdown and PDF) holds the setup,
  the goodness of fit (N, χ², k, ν, reduced χ², AIC and BIC —same definition as the
  discrete fit, to compare models on the same spectrum—, RMS, lag-1 autocorrelation and
  runs test of the residual), the globals with their σ, the distribution, the sharp
  components and the warnings (e.g. weight piled up at the grid edge). The PDF adds the
  P(x) plot or the 2D map.
- **Correlations.** The "Status and parameters" panel shows the correlation matrix as a
  colour table (red positive, blue negative, stronger the larger |r|; bold if
  |r| ≥ 0.95) between the refined globals (δ, ΔEQ, Γ, κ) and the **mean and width of
  P**. The report carries the same matrix and the PDF its heat map. This tells whether
  the width of the distribution is trading off against Γ in that fit. They are computed with P refitted: the part due to
  the globals (sensitivity of the moments of P to each global, by central differences)
  plus the internal one (Monte Carlo replicas of the histogram or covariance of the shape
  parameters). The mean and width of P thus carry an error that includes that of the
  globals.
- **Shape of P.** Alongside the mean, width and mode, the panel and the report give the
  **skewness** (negative = tail towards low values) and the **excess kurtosis** (0 for a
  Gaussian, negative if P is flatter, positive if it is more peaked), the same ones
  NORMOS-DIST gives to compare P with a Gaussian. They carry no error.

## Warnings of the distribution panel

The panel warns, with a link to the help, about combinations that fit well but do not
mean what they seem:

- **P(IS) with free Γ**: a distribution of isomer shifts broadens every line equally and
  is confused with Γ. Fix Γ to the instrumental width.
- **P(ΔEQ) with doublets and free Γ**: P(ΔEQ) broadens both lines of the doublet just
  like Γ (in synthetic spectra, σ–Γ correlation of −0.90 to −0.95 and a σ error about
  3 times larger). Fix Γ here too. P(BHF) does not need it: the field broadens the outer
  lines about 6 times more than the inner ones, so Γ separates.
- **P(ΔEQ) with fixed-field sextets**: the first-order kernel is valid only when ΔEQ is
  small compared to the magnetic splitting.
- **P(IS, ΔEQ) with doublets**: the spectrum only sees the distribution of each line,
  so the IS–ΔEQ map is not unique. For the IS–ΔEQ correlation of glasses use `P(ΔEQ)`
  with κδ, which is identifiable.

## Basic CLI usage

```bash
python3 fit_bhf_distribution_cli.py sample.ws5 \
  --bmin 0 --bmax 50 --nbins 50 \
  --gamma 0.18 --alpha 0.01 \
  --plot --scan-alpha

# P(ΔEQ) with doublets; P(IS) with singlets:
python3 fit_bhf_distribution_cli.py sample.adt --variable quad --bmax 3
python3 fit_bhf_distribution_cli.py sample.adt --variable delta --bmin -1 --bmax 2

# Shapes: VBF with two Gaussians and bounded widths; binomial as NORMOS (5 % solute):
python3 fit_bhf_distribution_cli.py sample.adt --shape vbf --vbf-components 2 \
  --vbf-sigma-min 0.5 --vbf-sigma-max 3
python3 fit_bhf_distribution_cli.py sample.adt --shape binomial \
  --binomial-conc 5 --binomial-start 33 --binomial-step -2.5
# Czjzek P(ΔEQ) (pure or extended) for a glass:
python3 fit_bhf_distribution_cli.py sample.adt --variable quad --bmax 3 --shape czjzek-ext

# Histogram regularizer: tikhonov (default), tv, maxent:
python3 fit_bhf_distribution_cli.py sample.adt --reg-mode maxent

# 2D: P(BHF, ΔEQ) histogram, two bivariate Gaussians, P(IS, ΔEQ):
python3 fit_bhf_distribution_cli.py sample.adt --dist-2d --qmin -1 --qmax 1
python3 fit_bhf_distribution_cli.py sample.adt --dist-2d --shape vbf --vbf-components 2
python3 fit_bhf_distribution_cli.py sample.adt --dist-2d --pair delta-quad
```

In the CLI δ, ΔEQ, Γ and the κ slopes are fixed values (`--delta`, `--quad`, `--gamma`,
`--delta-slope`, `--quad-slope`); the global refinement is a GUI feature.

Outputs (prefix `<input>_bhf` or `--out-prefix`):

- `*_spectrum.dat`: velocity, data, fit, residual, folded counts.
- `*_distribution.dat`: grid, P, normalized P (1D).
- `*_distribution2d.dat` plus `*_<x>_axis.dat` and `*_<y>_axis.dat` (2D).
- `*_summary.json`: parameters and metrics; with VBF the fitted (A, μ, σ) and the σ bounds applied.
- `*_plot.png` and `*_alpha_scan.dat/.png` with `--plot` / `--scan-alpha`.

The complete option list is `python3 fit_bhf_distribution_cli.py -h` and the
*Command-line tools* appendix of the manual.

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

- `alpha` is the critical parameter of the histogram: use `--scan-alpha` or the GUI's
  `L-curve α` button and check that the main features of P are stable around the value
  chosen. The parametric shapes do not use α.
- If `B_min=0`, the fit may use low-field values to absorb non-magnetic contributions.
  For a purely magnetic distribution, try `--bmin 15` or `--bmin 20`.
- Start simple: Gaussian or VBF with 1–2 components before a free histogram, and 1D
  before 2D.
- For 2D distributions the grid can be large ($N_x \times N_y$ bins): use independent
  regularizations $\alpha_x$, $\alpha_y$ and verify stability by varying both. See the
  two-dimensional distributions appendix of the manual.
- Distributions with IS (`P(IS)`, `P(IS, ΔEQ)`, `P(BHF, IS)`) are very sensitive to the
  velocity calibration and the folding point. See the P(IS) appendix of the manual.
- The thickness correction applies to the discrete model; distribution fits assume a
  thin absorber.
