# Fitbauer v5.2.0

*[🇪🇸 Notas en español](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.2.0_ES.md)*

A release about distributions: P(ΔEQ) and P(IS) now use the right kernels, the
binomial shape is NORMOS's, the 2D modes gain Gaussian shapes, the distribution
plot shows honest error bands, and fits are much faster. The whole interface,
the reports and the help are now in all eight languages.

---

## Distributions

- **P(ΔEQ) and P(IS) use doublets / singlets.** Their kernel used to be sextets
  at the panel's fixed field (33 T by default), and the live preview drew the
  discrete model. P(ΔEQ) and P(IS, ΔEQ) now use doublets (B = 0); P(IS) uses
  singlets, or doublets with the global ΔEQ, like NORMOS-DIST METHOD=8. Sextets
  with a fixed field remain as an advanced option. Older sessions that saved a
  field reproduce their fit. **Results change** for P(ΔEQ)/P(IS) fits made with
  the old default.
- **Binomial shape as in NORMOS-DIST** (`DISTRI=3` with `CONC`): n neighbour
  sites (12 by default), solute concentration c and n+1 subspectra at
  “value without neighbours + k·change per neighbour”, with binomial weights
  that match the NORMOS binary. Works for BHF, ΔEQ and IS. The previous
  “Binomial” shape had no relation to a number of neighbours, so **results
  change** for sessions that used it. `.JOB` import carries `CONC`, `BHF` and
  `DTB` over.
- **Gaussian and VBF shapes in 2D.** Besides the regularized histogram, the 2D
  modes fit one bivariate Gaussian (μx, μy, σx, σy and correlation ρ) or N of
  them (VBF, one per site). δ, ΔEQ and Γ are fitted in the same problem, so it
  takes seconds.
- **Width bounds for the Gaussians.** In the Gaussian and VBF shapes (1D and 2D)
  the width σ, common to all the Gaussians, can be bounded with **σ min /
  σ max** (one pair per axis in 2D; 0 = automatic). Useful when one Gaussian
  collapses into a spike or widens until it absorbs the background.
- **1σ band of P.** The help promised a 1σ band around the histogram that no
  plot drew, and the linearized covariance behind it ignores P ≥ 0: with peaks
  surrounded by empty bins it came out 2 to 16 times too wide. The band is now
  a parametric Monte Carlo (100 refits with noise, about 0.05 s), validated
  against independent refits. A check hides it.
- **δ(x) / ΔEQ(x) correlation curve.** With a non-zero κ slope (for example the
  Rancourt–Ping δ(ΔEQ) coupling in P(ΔEQ)), the distribution plot draws the
  line the kernel applied on a right axis, with its 1σ band and κ ± σ in the
  legend. A check hides it.
- **The panel shows only what applies**: the active distribution in the title,
  kernel physics only where it is used, correlation slopes with their meaning
  and units, and each variable remembers its own grid.
- **Warnings that explain themselves.** P(IS) with free Γ, P(ΔEQ) with
  fixed-field sextets and P(IS, ΔEQ) with doublets (whose map is not unique)
  each end in “More information…”, which opens a new help chapter at the
  section that explains why and what to do.

## Command line

- `fit_bhf_distribution_cli.py` fits the three 2D pairs with
  `--pair bhf-quad|delta-quad|bhf-delta`, the 2D Gaussian shapes with
  `--dist-2d --shape gaussiana|vbf`, the NORMOS binomial with `--binomial-*`,
  and bounds the Gaussian widths with `--vbf-sigma-min/--vbf-sigma-max`
  (`-y` variants for the second 2D axis).
- `--scan-alpha` now scans exactly the same model as the fit (it ignored the
  edge anchoring, D13/D23, the kernel treatment and the polarized source).

## Much faster fits

Measured on a 14-core machine:

- P(BHF) with free δ, ΔEQ and Γ: from 30 s to 0.6 s. OpenBLAS spread every
  operation over all cores, which for matrices this small cost a hundred times
  more than the computation; BLAS now uses one thread (`OPENBLAS_NUM_THREADS`
  still wins if you set it).
- P(BHF, ΔEQ) 2D: from over 30 min to about 1.5 min, with a faster
  non-negative least-squares solver that reaches the same optimum.
- Fits with free global parameters or sharp components no longer seem to run
  forever: the evaluation cap now counts every evaluation, and the progress bar
  shows it.

## Eight languages throughout

The interface no longer has fixed Spanish text: dialogs, status bar, reports
(full and short, Markdown and PDF), the parameter-limits dialog, progress and
error messages, NORMOS import warnings and the engine notes all follow the
selected language. Qt's own buttons and file dialogs (“Cancel”, “Open”…) are
translated too. The integrated help has been retranslated so that all eight
languages have the same 32 chapters in the same order.

## Documentation

- The Spanish manual now has the *Command-line tools* appendix, and both
  manuals cover everything above.
- The manual appendices are the single source for the mathematics; the loose
  `.tex`/`.pdf` documents in `docs/` that lagged behind them have been removed.
- `BHF_DISTRIBUTION.md`, the README and the wiki are up to date.

## Fixes

- **Cancel** was lost during the automatic global escalation (differential
  evolution) of the discrete fit, and answered only between steps in VBF 2D.
- The 2D map under the spectrum did not refresh after a second 2D fit.
- In 2D modes, a free δ was refined even when IS was an axis of the map.
- “Tie δ” and “Tie Γ1” only tied components 2 and 3; they now tie every active
  component.
- The Blume–Tjon polarization control showed an internal key as its label.
- The folding help contradicted itself about trimming the edges.

---

Full suite: **704 tests passing**.
