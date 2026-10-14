# Fitbauer v5.2.2

*[🇪🇸 Notas en español](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.2.2_ES.md)*

A release about NORMOS-DIST compatibility and consistent statistics: NORMOS's
Czjzek distributions are now imported with the matching shape, imported grids
sit exactly on NORMOS's nodes, and every distribution shape weights the fit with
the data uncertainties.

---

## NORMOS-DIST

- **Czjzek jobs are carried over.** A probe of the NORMOS-DIST binary
  (09.09.1993) shows that `DISTRI=4` with `METHOD=6` uses exactly the same
  P ∝ ΔEQ⁴·exp(−ΔEQ²/2σ²) as Fitbauer's Czjzek shape, with
  **σ² = STG² + DTQ²**: NORMOS broadens its STG with the grid step (checked to
  1e-5 for steps from 0.06 to 0.36 mm/s, independent of QUA and WID). Such
  `.JOB` files are now imported with the Czjzek shape and a warning that gives
  the equivalent σ; before, they became a histogram. With another `METHOD`, or
  with fixed-field sextets, they are still imported as a histogram.
- **Imported grids sit on NORMOS's nodes.** NORMOS computes its subspectra at
  QUA + k·DTQ (or BHF + k·DTB…). The importer passed that range as the grid
  edges, while Fitbauer places its nodes at the bin centres, so the nodes were
  shifted by half a step and the step was (NSB−1)/NSB of NORMOS's (0.173
  instead of 0.18 mm/s with NSB = 25). The bin centres now fall exactly on the
  NORMOS nodes. **Results change for imported DIST jobs.**

## Czjzek σ and ΔEQ₀ can be fixed

New **Czjzek σ** and **Ordered ΔEQ₀** controls in the distribution panel (shown
only with the Czjzek shapes) give the starting point of the fit, receive the
fitted values and, with their **Fixed** box, are not fitted. This reproduces a
fixed NORMOS STG: the importer puts σ = √(STG² + DTQ²) in the control and fixes
it when the `.JOB` has `STGFIT=.FALSE.`. Both are saved in the session. In the
CLI: `--czjzek-sigma`, `--czjzek-delta0`, `--fix-czjzek-sigma` and
`--fix-czjzek-delta0`.

## Fixes

- **Gaussian, VBF, Binomial and Fixed shapes weight the fit with the data σ.**
  The histogram, Czjzek and the 2D shapes already did; these four gave every
  channel the same weight. Errors and the covariance of the mean and width of P
  are now on the same footing for every shape. **Results of these shapes change
  slightly.**
- **Errors of the 2D globals when the evaluation budget runs out.** The 2D
  histogram left δ, ΔEQ and Γ without errors in that case; the Jacobian is now
  computed at the best point. This extra step shows in the progress bar with
  its own count.
- **The “classic” plot style inherited the previous style:** serif font, inward
  ticks and a framed legend after “publication”.
- **Test suite crash in CI.** The tests passed and the process then died with a
  segmentation fault when Python shut down, as PySide6 destroyed Qt objects in
  the wrong order. The suite now closes its widgets and exits cleanly.

## Documentation

The help (eight languages), both manuals, `BHF_DISTRIBUTION.md`, the NORMOS
notes and the wiki cover everything above.

---

Full suite: **735 tests passing**.
