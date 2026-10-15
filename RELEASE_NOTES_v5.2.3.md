# Fitbauer v5.2.3

*[🇪🇸 Notas en español](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.2.3_ES.md)*

A release about NORMOS compatibility, based on a review of the NORMOS source
code and the WinNormos manual. It adds the in-field Le Caër distribution and
the applied field of the Ising relaxation. It also fixes how `.JOB` files with
a negative VMAX are opened.

---

## Important fix: `.JOB` files with a negative VMAX

In NORMOS the sign of VMAX reverses the spectrum. The importer took its
absolute value, so those jobs opened **mirrored**, with the isomer shift of the
wrong sign. The sign is now kept on import and export, with a warning. The
benchmark of real NORMOS jobs exposed the problem: every job with a negative
VMAX folded differently from NORMOS, and with the sign they agree to noise
level. **If you imported such a job, import it again.**

## New: in-field Le Caër distribution

A new **Le Caër** shape for P(ΔEQ): the random Czjzek field gradient seen by
sextets in a fixed field, for disordered magnetic phases such as metallic
glasses and nanocrystalline materials.

- The grid is the signed coupling e²qQ/2.
- Each subspectrum is the exact powder average of a sextet whose EFG is
  randomly oriented with respect to the field.
- The weights are the distribution of the signed Vzz of a Czjzek tensor
  (checked by Monte Carlo); σ is the only shape parameter.

It is NORMOS-DIST's `DISTRI=4` with `METHOD=7`, and such `.JOB` files are now
imported with it. In P(ΔEQ) both Czjzek and Le Caër can always be chosen:
choosing Le Caër switches on the fixed-field sextet (33 T if the field was 0),
and choosing Czjzek switches it off. In the CLI: `--shape lecaer`.

## New: applied field in the Blume–Tjon relaxation

The Blume–Tjon component has a new parameter, **External field BEXT (T)**,
NORMOS's BEXT. The hyperfine field reverses with the spin and the applied one
does not, so the two states see BEXT ± BHF. In the fast limit the spectrum
collapses to a sextet of field BEXT instead of a single line.

It is a datum of the experiment: it is fixed by default, «Free all» does not
release it, and with 0 nothing changes. It matches Blume's matrix equation to
1e-10.

## More from NORMOS

- **Ising relaxation (`IRELAX`) is imported** as a Blume–Tjon component, with
  ν = OME·10⁶/2, P = BHF/BSAT and the global BEXT. Before, only a warning was
  given.
- **Gaussian distributions (`DISTRI=2`):** NORMOS broadens STG with the grid
  step, so the real width is √(STG² + step²). The import warning now gives it.
  It used to say, wrongly, that STG was not carried over.
- **`METHOD=5`/`7`** keep the `DISTRI` shape. NORMOS's spline file holds the
  subspectra, not the distribution. Before, they were imported as «Fixed».
- **Shape of P:** the panel and the report give the skewness and the excess
  kurtosis of the distribution, as NORMOS-DIST does.
- **Hesse–Rübartsch parameter:** NORMOS-DIST's smoothing criterion,
  Σ(y − y_theo)²/Σy ≈ χ²/N, is shown in the panel and the report.

## Validation

The benchmark of real NORMOS jobs has been redone. It covers 407 distinct
jobs, and only those that are a valid reference are kept:

- jobs where NORMOS fitted well (reduced χ² ≤ 2): 161 jobs where it did not
  are discarded;
- jobs where both programs see the same spectrum.

On the 216 remaining jobs, starting from NORMOS's solution, Fitbauer reaches
the same or a lower χ² in 211. The median agreement is 0.0014 mm/s in δ and
0.016 T in BHF.

---

Full suite: **759 tests passing**.
