# Fitbauer v5.2.1

*[🇪🇸 Notas en español](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.2.1_ES.md)*

A release about understanding a distribution fit: reports that describe the
distribution that was actually fitted, its data can be exported, a new Czjzek
shape for P(ΔEQ) of disordered solids, and a colour correlation matrix that
shows at a glance which parameters trade off against each other.

---

## Distribution reports and data

- **Reports describe the distribution fit.** In distribution mode the full and
  short reports (Markdown and PDF) used to show the discrete component of the
  panels (a sextet that was not part of the fit), the RMS of the discrete model
  and the spectrum plot, and nothing else. They now contain:
  - the setup (mode, shape, regularizer, α, grid);
  - the goodness of fit: N, χ², k, ν = N − k, reduced χ², AIC, BIC and RMS,
    plus the lag-1 autocorrelation and runs test of the residual. AIC and BIC
    use the same definition as the discrete fit, so a distribution and a
    discrete model of the same spectrum can be compared;
  - the global parameters (δ, ΔEQ, Γ, κ) with their σ and whether they were
    refined;
  - the distribution: mean, width and mode of P, the Gaussians of VBF/2D or
    the binomial parameters;
  - the sharp components with their fitted depth, and the warnings (including
    weight piled up at the grid edge, which was computed but never shown).

  The PDF adds the P(x) plot with its band, or the map of the current 2D fit.
- **Export the distribution.** A **Save data…** button in the P(x) and 2D map
  dialogs, and **File → Export distribution…**, write a tab-separated file:
  variable, normalized P, σ of P, weight and, with κ slopes, the δ(x)/ΔEQ(x)
  curve with its σ; in 2D, one row per cell. The header summarizes the fit.
- **Save fit…** in distribution mode exported the discrete model of the panels.
  It now exports the distribution model and the full 2D map.

## Czjzek shape for P(ΔEQ)

Two new parametric shapes for the |ΔEQ| distribution of glasses and amorphous
materials, offered only in P(ΔEQ) with doublets:

- **Czjzek**: a random electric field gradient (Czjzek et al. 1981). ΔEQ/σ
  follows a χ distribution with 5 degrees of freedom,
  P ∝ ΔEQ⁴·exp(−ΔEQ²/2σ²): asymmetric, zero at the origin, mode at 2σ.
- **Extended Czjzek** (Le Caër–Brand 1998): random disorder on top of an
  ordered environment ΔEQ₀ (non-central χ with 5 degrees of freedom). It tends
  to a Gaussian when ΔEQ₀ ≫ σ.

σ and ΔEQ₀ are reported with their errors; the shapes accept the κδ
correlation and sharp components, and are available in the CLI
(`--shape czjzek` / `czjzek-ext`). Compare them with the Gaussian or the
histogram through AIC/BIC.

## Correlations at a glance

- **Colour correlation matrix.** The *Status and parameters* panel shows the
  correlation matrix as a table: rows and columns are the parameters, red for
  positive and blue for negative correlation, stronger the larger |r|, bold for
  |r| ≥ 0.95 (the fit cannot separate them). The report carries the same matrix
  and the PDF a heat map.
- **Discrete fits** include every free parameter, now also vmax, the centre and
  the Voigt σ when they are fitted.
- **Distribution fits** correlate the refined globals (δ, ΔEQ, Γ, κ) with the
  **mean and width of P**, which now carry an error that includes that of the
  globals. This answers directly whether the width of the distribution is
  trading off against Γ. The result was checked against a joint fit of all
  parameters (σ_P–Γ: −0.93 vs −0.94).
- The status panel labels them “mean of P” and “width of P”, and shows the σ of
  each Gaussian next to its μ.

## Warnings

- **P(ΔEQ) with doublets and free Γ** now gets the same warning as P(IS): the
  distribution broadens both lines just like Γ (σ–Γ correlation −0.90 to −0.95
  in synthetic spectra). Fix Γ to the instrumental width.
- **Thick absorber.** With *Absorber* set to thick or transmission integral,
  the distribution fit silently assumed a thin absorber. The panel now warns.

Each warning links to its section of the help.

## Fixes

- **Unstable errors of the distribution globals.** The covariance of δ, ΔEQ, Γ
  and κ came from a Jacobian with a step of ~1e-8, where the tolerance of the
  inner fit of P dominates: the derivative with respect to Γ changed by a factor
  of 3.6 between almost identical fits. It is now recomputed with central
  differences and a sensible step. **Reported σ of the globals change.**
- In distribution mode the status panel showed the RMS as “reduced χ²” and
  dof, AIC and BIC as 0, also in the fit history.
- The residual diagnostics of the discrete fit (lag-1, runs test) were never
  computed: the panel showed `nan` and the report section never appeared. The
  ill-defined “antisymmetric correlation” has been removed.
- Japanese and Chinese text in plots and PDF reports showed as empty boxes; an
  installed CJK font is now used as fallback. The saved plot style is also
  applied at start-up.
- The report of P(ΔEQ)/P(IS) labelled the grid as “(BHF)”.

## Documentation

- The help (eight languages), both manuals, `BHF_DISTRIBUTION.md`, the README
  and the wiki cover everything above.
- The help and the manual described the L-curve dialog of the old interface
  (GCV, a “compromise” value, an L-surface for 2D): they now describe what the
  dialog does. The thickness appendix no longer describes a distribution-mode
  correction that does not exist.

---

Full suite: **728 tests passing**.
