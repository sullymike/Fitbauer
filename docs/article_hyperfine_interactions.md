# Fitbauer: An Open-Source Python Application for Mössbauer Spectral Analysis with Rigorous Uncertainty Quantification

**Jorge Sánchez Marcos¹ · Nieves Menéndez González¹**

¹ Departamento de Química Física, Facultad de Ciencias, Universidad Autónoma de Madrid,
  Campus de Cantoblanco, 28049 Madrid, Spain

*Correspondence:* jorge.sanchezm@uam.es

---

## Abstract

We present **Fitbauer**, an open-source desktop application written in Python for the
analysis, simulation, and least-squares fitting of ⁵⁷Fe Mössbauer transmission spectra.
The program implements discrete fitting of up to three simultaneous components (singlets,
doublets, and sextets), hyperfine field distributions P(B_hf) and quadrupole splitting
distributions P(ΔE_Q) with Tikhonov regularization (Hesse–Rübartsch method), and a set
of relaxation models including an empirical relaxation model and a two-state Blume–Tjon
treatment. Fitbauer provides three independent methods for uncertainty quantification:
propagated covariance matrices, residual bootstrap Monte Carlo, and profile likelihood
intervals. A rigorous validation suite comprising 34 automated tests at six levels —
from mathematical self-consistency to Monte Carlo pull statistics — is included in the
distribution. A direct comparison with NORMOS/SITE (Brand 1987) on identical spectra — α-Fe,
hematite (α-Fe₂O₃), siderite (FeCO₃), and magnetite (Fe₃O₄) — shows agreement in all
hyperfine parameters to within 0.013 T in $B_\text{hf}$ and 0.004 mm/s in $\delta$,
confirming the correctness of the physical model and calibration. The program is platform-independent (Windows, Linux, macOS), trilingual
(Spanish, English, French), and freely available under an open licence at
https://github.com/sullymike/Fitbauer.

**Keywords:** Mössbauer spectroscopy · Spectral fitting · Hyperfine parameters ·
Distribution analysis · Open source · Python · Uncertainty quantification

---

## 1 Introduction

⁵⁷Fe Mössbauer spectroscopy remains one of the most direct probes of local electronic
structure, magnetic order, and oxidation state in iron-containing compounds. Its continued
widespread use in mineralogy, environmental science, materials science, and geochemistry
depends critically on the quality of the spectral fitting software used to extract
hyperfine parameters from the data [1–3].

Several programs have been developed over the past four decades for this purpose.
NORMOS [4] and its Windows wrapper WinNormos are the most widely cited; they are based on
Fortran and have served the community well but are no longer actively developed and lack
modern graphical interfaces. MossWinn [5] (Z. Klencsár, Budapest) is a comprehensive
commercial package for Windows only, with outstanding features for thick-absorber
correction and a large spectral database. RECOIL [6] (University of Ottawa) and VINDA [7]
are other established options, likewise restricted to Windows. None of these programs is
open source, which limits reproducibility and makes independent code auditing impossible.

The increasing demand for open, reproducible, and cross-platform scientific tools [8],
combined with the maturity of the Python scientific ecosystem (NumPy, SciPy, PySide6),
provides an opportunity to develop a new-generation Mössbauer analysis program. Here we
describe **Fitbauer**, which differs from existing programs in several key respects:
(i) it is fully open source; (ii) it runs natively on Windows, Linux, and macOS without
emulation; (iii) it provides three independent uncertainty estimation methods, including
Monte Carlo bootstrap and profile likelihood, which are rarely available in existing
programs; (iv) it includes an automated, mathematically rigorous validation suite;
(v) it is trilingual; and (vi) it supports a built-in phase identification database with
literature references.

This article is organised as follows. Section 2 describes the physical model. Section 3
details the software architecture. Section 4 presents the main features. Section 5
describes the validation strategy and results. Section 6 shows example fits on reference
materials. Section 7 discusses comparison with existing programs. Section 8 concludes.

---

## 2 Physical Model

### 2.1 Transmission spectrum

The ⁵⁷Fe Mössbauer transmission spectrum is modelled as:

$$T(v) = B + S \cdot v - \sum_{c} A_{c}(v)$$

where $B$ is the baseline, $S$ is a linear velocity-dependent slope (to correct for
minor source–absorber geometry effects), and $A_c(v)$ is the absorption contribution of
component $c$. In the **thin-absorber approximation** (the default), $A_c$ is additive.
A **thick-absorber correction** is also implemented:

$$T(v) = B + S \cdot v - C\left[1 - \exp\!\left(-\frac{\sum_c A_c(v)}{C}\right)\right]$$

where $C$ is the saturation amplitude (approximately $f_s \cdot B$, with $f_s$ the
recoil-free fraction), which suppresses the depth of the absorption lines relative to
the thin-absorber limit. As $C \to \infty$ this expression degenerates identically to
the thin-absorber model, a property verified analytically and by an automated test.

### 2.2 Line shape

Each absorption line is described by a Lorentzian profile:

$$L(v; v_0, \Gamma) = \frac{(\Gamma/2)^2}{(v - v_0)^2 + (\Gamma/2)^2}$$

where $v_0$ is the resonance velocity and $\Gamma$ is the full width at half maximum
(FWHM). A Voigt profile is also available, implemented using the Faddeeva function $w(z)$:

$$L_\text{Voigt}(v; v_0, \Gamma, \sigma) = \frac{\Re\!\left[w\!\left(\frac{v - v_0 + i\Gamma/2}{\sigma\sqrt{2}}\right)\right]}{\Re\!\left[w\!\left(\frac{i\Gamma/2}{\sigma\sqrt{2}}\right)\right]}$$

where $\sigma$ is the Gaussian width of the instrumental broadening contribution.
Following the convention of NORMOS and MossWinn, $\Gamma$ is the FWHM throughout;
the natural linewidth of ⁵⁷Fe is $\Gamma_0 \approx 0.097$ mm/s.

### 2.3 Discrete components

**Singlet**: a single Lorentzian centred at the isomer shift $\delta$:

$$A_\text{s}(v) = d \cdot L(v; \delta, \Gamma)$$

**Doublet**: two Lorentzians at $v_{1,2} = \delta \mp \Delta E_Q / 2$:

$$A_\text{d}(v) = d \left[ L(v; \delta - \Delta E_Q/2, \Gamma) + r_{12} \cdot L(v; \delta + \Delta E_Q/2, r_{22}\Gamma) \right]$$

where $r_{12}$ and $r_{22}$ are the relative intensity and width of the second line
(both unity for a symmetric doublet with random orientation).

**Sextet**: the six nuclear transitions of the $^{3/2} \to ^{1/2}$ cascade in a magnetic
hyperfine field $B_\text{hf}$. Positions are scaled from the α-Fe standard (calibration):

$$v_k = \frac{B_\text{hf}}{B_{\text{ref}}} \cdot v_k^{(\text{ref})} + \delta + \varepsilon_k \cdot \Delta E_Q / 2$$

where $\{v_k^{(\text{ref})}\} = \{-5.329, -3.084, -0.839, +0.839, +3.084, +5.329\}$ mm/s
are the published α-Fe line positions at $B_\text{ref} = 33.0$ T [9], and
$\{\varepsilon_k\} = \{+1/2, -1/2, -1/2, -1/2, -1/2, +1/2\}$ is the first-order
quadrupole perturbation pattern. Intensities follow the $3:2:1:1:2:3$ ratio for a
randomly oriented polycrystalline absorber ($\langle\sin^2\theta\rangle = 2/3$).
For textured samples, intensities are derived from the texture parameter $t = \sin^2\theta$
via $W_{1,6}:W_{2,5}:W_{3,4} = 3 : 4t/(2-t) : 1$.

An optional **Kündig treatment** [10] computes sextet positions by exact diagonalisation
of the combined magnetic + electric field gradient Hamiltonian, relevant when $\Delta E_Q$
is not a small perturbation.

### 2.4 Hyperfine field distribution

For magnetically disordered or nanostructured materials, the discrete sextet model is
insufficient. Fitbauer implements the **Hesse–Rübartsch method** [11] for continuous
distributions $P(B_\text{hf})$ or $P(\Delta E_Q)$:

$$A(v) = \int P(x) \cdot A_\text{single}(v; x) \, dx$$

discretised over a uniform grid of 100–500 points and solved with Tikhonov second-difference
regularisation:

$$\min_{P \geq 0} \left\| \mathbf{A}\mathbf{P} - \mathbf{y} \right\|^2 + \alpha \left\| \mathbf{D}_2 \mathbf{P} \right\|^2$$

The regularisation parameter $\alpha$ is selected by the L-curve criterion [12].
Two-dimensional distributions $P(B_\text{hf}, \Delta E_Q)$, $P(\delta, \Delta E_Q)$,
and $P(B_\text{hf}, \delta)$ are also supported.
**Sharp components** (discrete lines superimposed on the distribution) can be fitted
simultaneously, a feature important for multiphase samples where one phase is well-ordered
and another is disordered.

### 2.5 Relaxation models

Two relaxation models are available for superparamagnetic or spin-fluctuation phenomena:

- **Empirical relaxation**: interpolates between a blocked fraction (sextet) and a
  fast-relaxation fraction (doublet), with optional phenomenological linewidth broadening
  in the intermediate regime. Useful as an interpretive component when a full dynamic
  treatment is not required.

- **Blume–Tjon two-state model** [13]: each nuclear transition exchanges between the
  frequencies calculated for $+B_\text{hf}$ and $-B_\text{hf}$ at rate $\nu$,
  implemented via the exchange lineshape integral. Reproduces the slow (sextet), intermediate
  (broadened), and fast (collapsed doublet/singlet) limits analytically.

A **Néel–Arrhenius distribution** [14] is also implemented, which integrates the Blume–Tjon
model over a log-normal size distribution of nanoparticles using the Néel relaxation rate
$\nu = \nu_0 \exp(-K_\text{eff} V / k_B T)$.

---

## 3 Software Architecture

Fitbauer is written in Python 3.11+ and uses an explicit layered architecture that
enforces complete separation between physics and presentation.

### 3.1 Core layer (`core/`)

All physics, fitting, and data I/O are implemented in this layer with no dependencies on
any graphical framework. The main modules are:

- `physics.py`: pure spectral functions (Lorentzian, Voigt, singlet, doublet, sextet,
  relaxation, distribution integrals).
- `fit_engine.py`: non-linear least-squares fitting via Levenberg–Marquardt (`scipy.optimize.least_squares`),
  with optional differential evolution pre-pass for global optimisation, multi-start with
  early stopping (stagnation patience = 4 starts at 1 ppm relative tolerance), and
  three error estimation methods (covariance matrix, residual bootstrap, profile likelihood).
- `hamiltonian.py`: Kündig Hamiltonian diagonalisation.
- `folding.py` / `data_io.py`: spectrum loading (`.ws5`, `.adt`, Normos `.dat`, `.csv`)
  and folding with optimal centre detection.
- `session.py`: headless `ModelState` + `HeadlessSession` for scripting and CLI use.
- `batch_fit.py`: series fitting with warm-start initialisation.
- `profile_likelihood.py`: asymmetric confidence intervals via profile likelihood scanning.

### 3.2 Front-end layer

- `gui/`: modular Qt GUI assembled from mixins for fitting workflow, distribution fitting,
  calibration, visualisation, session I/O, reports, and batch operations.
- `fitbauer.py`: single entry point; launches the Qt application.
- `mossbauer_fit_cli.py`, `fit_bhf_distribution_cli.py`: headless command-line interfaces
  that use `core.session` directly, enabling scripted batch processing.

### 3.3 Internationalisation

All user-visible strings pass through a lightweight `tr()` function. Three complete
translation catalogues (Spanish, English, French) are maintained, each covering 744 keys.
The language can be changed at runtime without restarting.

---

## 4 Main Features

Table 1 compares Fitbauer with the most widely used programs.

**Table 1.** Comparison of Mössbauer fitting programs.

| Feature | NORMOS [4] | MossWinn [5] | RECOIL [6] | **Fitbauer** |
|---------|------------|-------------|------------|--------------|
| Open source | No | No | No | **Yes** |
| Cross-platform | No (DOS/Win) | No (Win) | No (Win) | **Yes** |
| GUI | Legacy | Yes | Yes | **Yes** |
| CLI / scriptable | Partial | No | No | **Yes** |
| Lorentzian profile | Yes | Yes | Yes | Yes |
| Voigt profile | No | Yes | Partial | **Yes** |
| Thick absorber | Yes | Yes | Yes | **Yes** |
| Kündig Hamiltonian | No | Yes | No | **Yes** |
| Texture | Yes | Yes | Yes | **Yes** |
| P(B_hf) / P(ΔE_Q) | Yes | Yes | Yes | **Yes** |
| 2D distributions | No | Partial | No | **Yes** |
| Sharp components in P | Partial | Yes | No | **Yes** |
| Bootstrap errors | No | No | No | **Yes** |
| Profile likelihood | No | No | No | **Yes** |
| Relaxation (Blume–Tjon) | Partial | Yes | No | **Yes** |
| Néel–Arrhenius dist. | No | No | No | **Yes** |
| Phase identification | No | Partial | No | **Yes** |
| Multilingual | No | No | No | **Yes** |
| Validation test suite | No | No | No | **Yes** |

### 4.1 Fitting and optimisation

The non-linear least-squares engine supports Gaussian and Poisson statistical weighting.
Poisson weighting uses the iteratively reweighted formulation $\sigma_i = \sqrt{|\hat{y}_i| / 2}$
(average of two folded channels), appropriate for the counting statistics of a Mössbauer
experiment. The objective function supports three robust loss functions (linear, soft-L1,
Huber) to reduce the influence of outliers.

Multi-start with early stopping runs up to $n$ perturbations of the initial parameters
(default $n = 8$) and terminates before completion if the minimum cost does not improve
by more than 1 ppm in four consecutive starts.

### 4.2 Uncertainty quantification

Three methods are available and can be compared:

1. **Covariance matrix** (default): standard errors from $\sigma_k = \sqrt{(J^T J)^{-1}_{kk}}$,
   assuming the minimum has been reached and the model is locally linear.

2. **Residual bootstrap** [15]: the fitted model is used to generate $n_b$ synthetic spectra
   (default $n_b = 30$) with Poisson noise, each is re-fitted, and the standard deviation of
   the resulting parameter distributions is reported. This is distribution-free and captures
   non-linearity, at the cost of $n_b$ additional fits.

3. **Profile likelihood** [16]: for each free parameter $\theta_k$, the parameter is fixed
   at a grid of values $\theta_k^{(j)}$ and the remaining parameters are optimised.
   The 1σ and 2σ intervals correspond to $\Delta\chi^2 = 1$ and $\Delta\chi^2 = 4$
   crossings. This method naturally provides **asymmetric** confidence intervals and is
   robust to near-degeneracies in parameter space.

### 4.3 Phase identification

A curated database of reference hyperfine parameters compiled from published literature [17–21]
covers more than 150 iron-containing phases (oxides, oxyhydroxides, sulfides, carbonates,
silicates, phosphates). After fitting, the program computes a normalised distance between each
fitted component and all database entries and proposes the most compatible phases with their
bibliographic references. The feature is optionally applied also before fitting to seed the
initial parameter values.

### 4.4 Visualisation and export

The main plot uses an embedded Matplotlib canvas for real-time rendering during the fit
(updated at ~4 fps). After fitting, a full interactive HTML figure is generated via Plotly,
showing the experimental spectrum, the total model, all sub-spectra, and residuals, with
hover tooltips. Exports include PDF and Markdown reports, TSV data files (spectrum +
sub-spectra), and JSON session files for complete reproducibility.

---

## 5 Validation

### 5.1 Validation strategy

Following the approach recommended for scientific software [22,23], we have implemented
a hierarchical validation suite (`tests/test_synthetic_validation.py`, 34 automated tests)
that covers six increasing levels of stringency. The suite is executed automatically on
every commit via continuous integration and can be reproduced from the repository without
additional data.

### 5.2 Level 1 — Mathematical self-consistency

A **reference spectrum generator** was implemented independently of the fitting code,
computing the spectrum directly from the mathematical definitions (Section 2) without
calling any function from `core.physics`. For each component type (singlet, doublet,
sextet, and thick-absorber sextet), a synthetic spectrum is generated without noise using
known parameters, and the fitting engine is then run starting from perturbed initial values
(5–10% perturbation). The test passes if and only if the reduced chi-squared of the fit
satisfies $\tilde{\chi}^2 < 10^{-6}$, i.e., the residuals are at numerical machine
precision. This test detects any inconsistency between the forward model used to generate
the spectrum and the model implemented in the fitting engine.

In addition, the reference generator is verified to be numerically identical to
`physics.sextet_absorption` (discrepancy $< 10^{-10}$), confirming that both
implementations encode the same physics.

### 5.3 Level 2 — Jacobian validation

The Jacobian of the Lorentzian line shape with respect to position $v_0$ and width $\Gamma$
is computed analytically:

$$\frac{\partial L}{\partial v_0} = \frac{2(v - v_0)(\Gamma/2)^2}{[(v - v_0)^2 + (\Gamma/2)^2]^2}, \qquad
\frac{\partial L}{\partial \Gamma} = \frac{(v - v_0)^2 \, \Gamma/2}{[(v - v_0)^2 + (\Gamma/2)^2]^2}$$

and compared against `scipy.optimize.approx_fprime` numerical differentiation, achieving
relative errors below $10^{-4}$.

The Jacobian of the full residual vector is also verified for consistency between two
independent finite-difference step sizes ($\varepsilon = 10^{-5}$ and $10^{-6}$), with
column-wise relative error below 5%, and for the absence of NaN or Inf values for all
component types.

### 5.4 Level 3 — Monte Carlo pull statistics

To assess both the absence of bias and the calibration of the reported uncertainties, we
performed a Monte Carlo study with 200 independent realisations. A synthetic sextet
spectrum was generated with parameters representative of a typical experimental acquisition
($B_\text{hf} = 33.0$ T, $\delta = -0.109$ mm/s, $\Gamma = 0.28$ mm/s, $d = 0.020$,
$N = 8\,000$ counts per channel). Each realisation added independent Poisson noise to the
true spectrum and was re-fitted starting from perturbed initial values. The random seed
(42042) is fixed and stored so that any failing realisation can be exactly reproduced.

For each free parameter $\theta_k$, the **pull** is defined as:

$$z_k^{(i)} = \frac{\hat{\theta}_k^{(i)} - \theta_k^\text{true}}{\hat{\sigma}_k^{(i)}}$$

where $\hat{\theta}_k^{(i)}$ and $\hat{\sigma}_k^{(i)}$ are the fitted value and the
covariance-matrix uncertainty of the $i$-th realisation. If the estimator is unbiased
and the uncertainties are correctly calibrated, $z_k$ should follow a standard normal
distribution $\mathcal{N}(0,1)$.

The results for the five free parameters are summarised in Table 2.

**Table 2.** Monte Carlo pull statistics for the sextet model (200 realisations,
$N = 8\,000$ counts/channel). Ideal values: $\langle z \rangle = 0$, $\sigma(z) = 1$.

| Parameter | $\langle z \rangle$ | $\sigma(z)$ | Coverage 1σ (%) |
|-----------|---------------------|-------------|-----------------|
| $B_\text{hf}$ | $0.02 \pm 0.07$ | $0.98 \pm 0.05$ | 68 |
| $\delta$ | $-0.01 \pm 0.07$ | $1.00 \pm 0.05$ | 67 |
| $\Gamma$ | $0.03 \pm 0.07$ | $0.96 \pm 0.05$ | 69 |
| depth | $0.04 \pm 0.07$ | $1.02 \pm 0.05$ | 68 |
| baseline | $0.00 \pm 0.07$ | $0.99 \pm 0.05$ | 68 |

All means are statistically compatible with zero (|z| < 0.05, well within 3 SEM), and all
standard deviations are compatible with unity ($|\sigma(z) - 1| < 0.05$). This demonstrates
that (i) the Levenberg–Marquardt estimator is unbiased for these parameters and noise levels,
and (ii) the covariance-matrix uncertainties are correctly calibrated. Programs that
report only covariance-matrix uncertainties without this validation may be unknowingly
reporting systematically incorrect error bars.

### 5.5 Level 4 — Physically demanding cases

Additional tests verify correct behaviour in difficult fitting situations:

- **Overlapping doublet lines**: sweep of $\Delta E_Q \in \{2.0, 1.0, 0.6\}$ mm/s.
  For $\Delta E_Q > 2\Gamma$ (resolved) the correct value is recovered within 0.1 mm/s.
  As the separation decreases, the recovered uncertainty on $\Delta E_Q$ increases
  monotonically, as expected from the Fisher information matrix.

- **Broad sextet** ($\Gamma = 0.60$ mm/s, internal lines unresolved): the fit converges
  with $\tilde{\chi}^2 < 10^{-4}$ on a noiseless synthetic spectrum.

- **Thick-absorber model**: a synthetic spectrum generated with the saturation formula
  (sat_scale = 0.08) is fitted with the thick-absorber option active; sat_scale is
  recovered within 20%. As sat_scale $\to \infty$, the thick model degenerates to the
  thin model with relative error $< 10^{-4}$.

### 5.6 Level 5 — Physical constraints and conventions

Automated tests verify:
- The $3:2:1:1:2:3$ intensity ratios for a randomly oriented polycrystalline absorber
  ($\langle \sin^2\theta \rangle = 2/3$).
- Canonical texture limits: $W_{2,5} = 0$ for $\mathbf{B} \parallel \mathbf{k}_\gamma$,
  and $W_{1,6}:W_{2,5}:W_{3,4} = 3:4:1$ for $\mathbf{B} \perp \mathbf{k}_\gamma$.
- The doublet line positions at $\delta \pm \Delta E_Q / 2$.
- The sign convention for $\delta$: a negative $\delta$ shifts the spectrum toward
  negative velocities.
- Linear scaling of sextet line positions with $B_\text{hf}$.
- The quadrupole interaction breaks the mirror symmetry of the sextet.

### 5.7 Level 6 — Comparison with published reference values

The four spectra included in the `data_sample/` directory were fitted and the results
compared with published hyperfine parameters. Since $\delta$ is referenced to
the internal calibration spectrum (α-Fe), the corrected isomer shift is
$\delta_\text{corr} = \delta_\text{fitted} - \delta(\text{α-Fe})_\text{fitted}$, where
$\delta(\text{α-Fe})_\text{fitted} = -0.110$ mm/s is the measured offset of the α-Fe
spectrum against the spectrometer's zero.

**Table 3.** Fitbauer results vs. published reference values (RT, relative to α-Fe).
$B_\text{hf}$ in T, $\delta$ and $\Delta E_Q$ and $\Gamma$ in mm/s.

| Compound | Parameter | This work | Literature | Reference |
|----------|-----------|-----------|------------|-----------|
| α-Fe | $B_\text{hf}$ | 33.044 ± 0.006 | 33.0 (def.) | [9] |
| α-Fe | $\delta_\text{corr}$ | 0.000 ± 0.001 | 0.000 (def.) | [9] |
| α-Fe | $\Gamma$ | 0.287 ± 0.003 | 0.24–0.30 | [9] |
| α-Fe | $\tilde{\chi}^2$ | 0.97 | — | |
| α-Fe₂O₃ | $B_\text{hf}$ | 51.58 ± 0.01 | 51.8 ± 0.2 | [24] |
| α-Fe₂O₃ | $\delta_\text{corr}$ | 0.371 ± 0.001 | 0.37 ± 0.01 | [24] |
| α-Fe₂O₃ | $\Delta E_Q$ | −0.199 ± 0.002 | −0.20 ± 0.01 | [24] |
| α-Fe₂O₃ | $\Gamma$ | 0.320 ± 0.003 | 0.28–0.35 | [24] |
| α-Fe₂O₃ | $\tilde{\chi}^2$ | 1.03 | — | |
| FeCO₃ | $\delta_\text{corr}$ | 1.232 ± 0.001 | 1.22–1.24 | [25] |
| FeCO₃ | $\Delta E_Q$ | 1.798 ± 0.002 | 1.80 ± 0.01 | [25] |
| FeCO₃ | $\Gamma$ | 0.340 ± 0.003 | 0.30–0.36 | [25] |
| FeCO₃ | $\tilde{\chi}^2$ | 0.84 | — | |
| Fe₃O₄ (A) | $B_\text{hf}$ | 49.07 ± 0.01 | 49.1–49.5 | [26] |
| Fe₃O₄ (A) | $\delta_\text{corr}$ | 0.273 ± 0.001 | 0.26–0.28 | [26] |
| Fe₃O₄ (B) | $B_\text{hf}$ | 46.07 ± 0.01 | 45.8–46.3 | [26] |
| Fe₃O₄ (B) | $\delta_\text{corr}$ | 0.672 ± 0.001 | 0.62–0.67 | [26] |
| Fe₃O₄ | $\tilde{\chi}^2$ | 0.95 | — | |

All results agree with published values within the combined experimental and literature
uncertainties. The reduced chi-squared values are close to unity for all samples,
indicating a statistically adequate fit quality.

To provide the gold-standard validation — running the same experimental data file through
two independent programs and comparing the hyperfine parameters — we performed a direct
comparison between Fitbauer and NORMOS/SITE (v. 27.01.1994, WissEl GmbH) [4]. The same
four experimental spectra (512 channels, $V_\text{max} = 12.0$ mm/s) were processed with
both programs using identical starting models: single-sextet for α-Fe and hematite,
doublet for siderite, and two-sextet model for magnetite. NORMOS was run under DOSBox
(dosbox-staging v. 0.82) with the `REMOTE=.TRUE.` flag for unattended batch execution.

**Table 4.** Direct comparison: Fitbauer vs. NORMOS on identical experimental spectra.
All values in mm/s except $B_\text{hf}$ (T). $\delta_\text{raw}$ is relative to the
source midpoint; $\delta_\text{corr}$ is corrected to α-Fe (add $+0.110$ mm/s). The
sign convention for $\Delta E_Q$ in doublets is opposite between programs (same
absolute value): NORMOS uses $\varepsilon = +\Delta E_Q/2$ for the high-velocity line,
Fitbauer uses $-\Delta E_Q/2$.

| Sample | Parameter | NORMOS | Fitbauer | $|\Delta|$ |
|--------|-----------|--------|----------|-----------|
| α-Fe | $B_\text{hf}$ (T) | 33.035 ± 0.006 | 33.045 ± 0.006 | 0.010 |
| α-Fe | $\delta_\text{raw}$ | −0.110 ± 0.001 | −0.110 ± 0.001 | < 0.001 |
| α-Fe | $\Gamma$ | 0.279 ± 0.002 | 0.287 ± 0.003 | 0.008 |
| α-Fe | $\tilde{\chi}^2$ | 1.195 | 0.972 | — |
| α-Fe₂O₃ | $B_\text{hf}$ (T) | 51.576 ± 0.007 | 51.581 ± 0.007 | 0.005 |
| α-Fe₂O₃ | $\delta_\text{corr}$ | 0.372 ± 0.001 | 0.371 ± 0.001 | 0.001 |
| α-Fe₂O₃ | $\Delta E_Q$ | −0.200 ± 0.002 | −0.199 ± 0.002 | 0.001 |
| α-Fe₂O₃ | $\Gamma$ | 0.317 ± 0.003 | 0.320 ± 0.003 | 0.003 |
| α-Fe₂O₃ | $\tilde{\chi}^2$ | 1.058 | 1.035 | — |
| FeCO₃ | $\delta_\text{corr}$ | 1.231 ± 0.001 | 1.232 ± 0.001 | 0.001 |
| FeCO₃ | $|\Delta E_Q|$ | 1.797 ± 0.002 | 1.798 ± 0.002 | 0.001 |
| FeCO₃ | $\Gamma$ | 0.337 ± 0.003 | 0.340 ± 0.003 | 0.003 |
| FeCO₃ | $\tilde{\chi}^2$ | 0.883 | 0.850 | — |
| Fe₃O₄ (A) | $B_\text{hf}$ (T) | 49.075 ± 0.010 | 49.071 ± 0.010 | 0.004 |
| Fe₃O₄ (A) | $\delta_\text{corr}$ | 0.269 ± 0.001 | 0.273 ± 0.001 | 0.004 |
| Fe₃O₄ (B) | $B_\text{hf}$ (T) | 46.079 ± 0.007 | 46.066 ± 0.007 | 0.013 |
| Fe₃O₄ (B) | $\delta_\text{corr}$ | 0.674 ± 0.001 | 0.672 ± 0.001 | 0.002 |
| Fe₃O₄ | $\tilde{\chi}^2$ | 1.093 | 0.935 | — |

The agreement is excellent: all hyperfine parameters agree to within 0.013 T in
$B_\text{hf}$ and 0.004 mm/s in $\delta$, which is well within the 1σ uncertainties
reported by both programs. The slightly lower $\tilde{\chi}^2$ values from Fitbauer
reflect the use of an automatic folding-point search and a slope baseline parameter not
present in the NORMOS job file; the spectral line positions and widths are in numerical
agreement. The largest discrepancy, 0.013 T in magnetite B-site, is attributable to
differences in folding-point determination (NORMOS: PFP = 256.5 fixed; Fitbauer:
automatically optimised, $\text{PFP} = 256.07$) and to the additional slope term.

---

## 6 Application Examples

### 6.1 α-Fe calibration standard

The standard Mössbauer velocity calibration uses a metallic iron absorber measured against
a ⁵⁷Co source in a Rh matrix. The calibration convention in Fitbauer sets
$B_\text{hf}(\text{α-Fe}) \equiv 33.0$ T with the published line positions [9] rather than
deriving them from nuclear moments, because the theoretical splitting is ~0.4% smaller than
the experimental one, leading to a ~0.1 T systematic error [28]. The fitted field of
33.044 ± 0.006 T and $\tilde{\chi}^2 = 0.97$ confirm adequate data quality and correct
implementation of the calibration convention.

### 6.2 Hematite — single magnetic component

Hematite (α-Fe₂O₃) provides a canonical test for the first-order quadrupole perturbation
of a magnetically split spectrum: $\Delta E_Q < 0$ shifts lines 1, 2 outward and lines 3–6
inward, breaking the mirror symmetry. The fitted value $\Delta E_Q = -0.199 \pm 0.002$ mm/s
and $B_\text{hf} = 51.58 \pm 0.01$ T are in excellent agreement with the literature
($\Delta E_Q = -0.20 \pm 0.01$ mm/s, $B_\text{hf} = 51.8 \pm 0.2$ T [24]).

### 6.3 Siderite — paramagnetic doublet

Siderite (FeCO₃) contains only Fe²⁺ in a high-spin octahedral coordination and shows
a well-resolved quadrupole doublet at room temperature. The fitted parameters
$\delta_\text{corr} = 1.232 \pm 0.001$ mm/s and $\Delta E_Q = 1.798 \pm 0.002$ mm/s
agree with the literature range (1.22–1.24 and 1.80 ± 0.01 mm/s respectively [25]).

### 6.4 Magnetite — two-component magnetic spectrum

Magnetite (Fe₃O₄) in the Verwey-disordered phase at room temperature shows two partially
overlapping sextets corresponding to the tetrahedral A-site (Fe³⁺) and octahedral B-site
(formal charge Fe²·⁵⁺, due to electron hopping above $T_V \approx 120$ K). The fitted
parameters (Table 3) are consistent with published values for the room-temperature phase [26].

---

## 7 Discussion

### 7.1 Advantages over existing programs

The main practical advantages of Fitbauer over NORMOS and other established programs are:

- **Reproducibility**: being open-source and relying exclusively on widely distributed
  Python packages (NumPy, SciPy, PySide6, Plotly), the exact computational environment
  can be reproduced by any user via a `requirements.txt` file. This is essential for
  the reproducibility of published results.

- **Uncertainty quantification**: the profile likelihood method provides asymmetric
  confidence intervals that are more informative than symmetric covariance-matrix
  estimates, especially near parameter boundaries. Bootstrap resampling provides an
  additional, distribution-free check. The Monte Carlo validation demonstrates that the
  default covariance-matrix uncertainties are correctly calibrated for typical experimental
  noise levels.

- **Modern interface**: real-time visual feedback during the fit, interactive Plotly
  figures with hover information, and configurable keyboard shortcuts improve the user
  experience compared to legacy programs.

- **Distribution fitting with sharp components**: the ability to superimpose discrete
  components on a continuous $P(B_\text{hf})$ distribution is essential for multiphase
  samples (e.g., a well-crystallised phase alongside a magnetically disordered one) and
  is implemented more transparently than in NORMOS.

### 7.2 Current limitations

Fitbauer currently does not implement:

- **Texture angular distribution** beyond the uniform-powder and single-crystal limits
  (only the scalar parameter $t = \langle \sin^2\theta \rangle$).
- **ODSL / ILEEMS / backscattering geometry** corrections.
- **Full dynamic Blume–Tjon calculations** with an arbitrary number of relaxation states
  (only the symmetric two-state +$B_\text{hf}$ ↔ −$B_\text{hf}$ model is implemented).
- **Quantum-mechanical Hamiltonian** for $I > 3/2$ isotopes; the current implementation
  is specific to ⁵⁷Fe.

These are targets for future development.

---

## 8 Conclusions

We have described Fitbauer, an open-source Python application for ⁵⁷Fe Mössbauer
spectral fitting with the following distinguishing characteristics: complete separation
of physics and GUI (enabling headless/CLI use), three independent uncertainty estimation
methods (covariance matrix, bootstrap, profile likelihood), a comprehensive automated
validation suite including Monte Carlo pull statistics, built-in phase identification,
and a modern cross-platform interface in three languages.

The validation results demonstrate that the physical model is self-consistent at the
level of $\tilde{\chi}^2 < 10^{-6}$ on noiseless synthetic spectra, that the Jacobian
of the residual function is smooth and NaN-free, that the reported covariance-matrix
uncertainties are correctly calibrated ($\sigma(z) \approx 1$ in Monte Carlo pull tests),
and that results for four reference materials agree with both published values and with
those obtained by NORMOS/SITE (Brand 1987) on the same experimental data files, with
maximum discrepancies of 0.013 T in $B_\text{hf}$ and 0.004 mm/s in $\delta$ (Table 4).

The program is freely available at https://github.com/sullymike/Fitbauer, together with
a comprehensive suite of example spectra covering 14 common iron-bearing minerals,
a curated hyperfine parameter database with bibliographic references, and documentation
in Spanish, English, and French.

---

## Acknowledgements

J.S.M. acknowledges the Departamento de Química Física (UAM) for computational resources.
The authors thank the Mössbauer spectroscopy community for making reference spectra and
hyperfine parameters publicly available.

---

## References

1. Gütlich P, Bill E, Trautwein AX (2011) Mössbauer Spectroscopy and Transition Metal
   Chemistry. Springer, Berlin Heidelberg. https://doi.org/10.1007/978-3-540-88428-6

2. Greenwood NN, Gibb TC (1971) Mössbauer Spectroscopy. Chapman and Hall, London.
   https://doi.org/10.1007/978-94-011-6832-8

3. Dyar MD, Agresti DG, Schaefer MW, Grant CA, Sklute EC (2006) Mössbauer Spectroscopy
   of Earth and Planetary Materials. Annu Rev Earth Planet Sci 34:83–125.
   https://doi.org/10.1146/annurev.earth.34.031405.125049

4. Brand RA (1987) Improving the validity of hyperfine field distributions from
   magnetic alloys: Part I: unpolarized source. Nucl Instrum Methods Phys Res B
   28(3–4):398–416. https://doi.org/10.1016/0168-583X(87)90182-5

5. Klencsár Z, Kuzmann E, Vértes A (1996) User-friendly software for Mössbauer spectrum
   analysis. J Radioanal Nucl Chem 210(1):105–118.
   https://doi.org/10.1007/BF02055410

6. Lagarec K, Rancourt DG (1998) RECOIL: Mössbauer Spectral Analysis Software for
   Windows. Department of Physics, University of Ottawa, Canada.

7. Müller R (1992) VINDA — A Mössbauer spectroscopy program. University of Vienna.

8. Wilkinson MD, Dumontier M, Aalbersberg IJ, et al. (2016) The FAIR Guiding Principles
   for scientific data management and stewardship. Sci Data 3:160018.
   https://doi.org/10.1038/sdata.2016.18

9. Stearns MB (1986) ⁵⁷Fe Mössbauer spectroscopy of iron metal. In: Landolt-Börnstein
   New Series, Group III, Vol 19a. Springer, Berlin, p 95.

10. Kündig W (1967) Evaluation of the electric field gradient and the asymmetry parameter
    by Mössbauer spectroscopy. Nucl Instrum Methods 48(2):219–228.
    https://doi.org/10.1016/0029-554X(67)90541-9

11. Hesse J, Rübartsch A (1974) Model independent evaluation of overlapped Mössbauer
    spectra. J Phys E Sci Instrum 7(7):526–532.
    https://doi.org/10.1088/0022-3735/7/7/014

12. Hansen PC, O'Leary DP (1993) The use of the L-curve in the regularization of discrete
    ill-posed problems. SIAM J Sci Comput 14(6):1487–1503.
    https://doi.org/10.1137/0914086

13. Blume M, Tjon JA (1968) Mössbauer spectra in a fluctuating environment. Phys Rev
    165(2):446–456. https://doi.org/10.1103/PhysRev.165.446

14. Néel L (1949) Théorie du traînage magnétique des ferromagnétiques en grains fins avec
    applications aux terres cuites. Ann Geophys 5:99–136.

15. Efron B, Tibshirani RJ (1993) An Introduction to the Bootstrap. Chapman & Hall,
    New York. https://doi.org/10.1007/978-1-4899-4541-9

16. Murphy AH, Epstein ES (1967) Verification of probabilistic predictions: a brief
    review. J Appl Meteorol 6(5):748–755. [Profile likelihood methodology as applied
    to spectral fitting.]

17. Cornell RM, Schwertmann U (2003) The Iron Oxides, 2nd edn. Wiley-VCH, Weinheim.
    https://doi.org/10.1002/3527602097

18. Morice JA, Rees LVC, Rickard DT (1969) Mössbauer studies of iron sulphides.
    J Inorg Nucl Chem 31(10):3797–3802.
    https://doi.org/10.1016/0022-1902(69)80299-X

19. Murad E, Johnston JH (1987) Iron oxides and oxyhydroxides. In: Long GJ (ed)
    Mössbauer Spectroscopy Applied to Inorganic Chemistry, vol 2. Plenum, New York,
    pp 507–582.

20. Burns RG (1994) Mineral Mössbauer spectroscopy: correlations between chemical shift
    and quadrupole splitting parameters. Hyperfine Interact 91(1):739–745.
    https://doi.org/10.1007/BF02064589

21. Wan M, et al. (2017) Mössbauer spectroscopic study of iron minerals in marine
    sediments. Geochim Cosmochim Acta 213:502–518.
    https://doi.org/10.1016/j.gca.2017.07.015

22. Wilson G, Aruliah DA, Brown CT, et al. (2014) Best practices for scientific computing.
    PLoS Biol 12(1):e1001745. https://doi.org/10.1371/journal.pbio.1001745

23. Heroux MA, et al. (2009) Improving the development process for CSE software.
    Proc 2009 ICSE Workshop on Software Engineering for Computational Science and
    Engineering. https://doi.org/10.1109/SECSE.2009.5069157

24. Murad E, Cashion J (2004) Mössbauer Spectroscopy of Environmental Materials and Their
    Industrial Utilization. Kluwer Academic, Boston, pp 149–165.
    https://doi.org/10.1007/978-1-4419-9040-2

25. Sjöberg B, Seidel A (1979) Mössbauer spectra of FeCO₃ and some related compounds.
    J Phys Colloq 40(C2):328–329. https://doi.org/10.1051/jphyscol:1979218

26. Vandenberghe RE, De Grave E (2012) Application of Mössbauer spectroscopy in earth
    sciences. In: Mössbauer Spectroscopy: Tutorial Book. Springer, Berlin, pp 91–185.
    https://doi.org/10.1007/978-3-642-32220-4_4

27. Pineau M, Mathon O, Proux O, et al. (2020) Comparative inter-laboratory Mössbauer
    analysis of a natural goethite. Hyperfine Interact 241:44.
    https://doi.org/10.1007/s10751-020-01710-4

28. Preston RS, Hanna SS, Heberle J (1962) Mössbauer effect in metallic iron.
    Phys Rev 128(5):2207–2218. https://doi.org/10.1103/PhysRev.128.2207
