# Fitbauer v5.2.4

*[🇪🇸 Notas en español](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.2.4_ES.md)*

A corrective release. A closer comparison with NORMOS, job by job and with
NORMOS itself re-run, showed that importing a `.JOB` did not always rebuild
the same model that NORMOS had fitted. This release fixes that, and corrects
the validation figures given with v5.2.3.

**If you imported NORMOS `.JOB` files with v5.2.3 or earlier, import them
again.** The fits may have had more free parameters than in NORMOS, and the
hyperfine field was on a slightly different scale.

---

## Fixes in the `.JOB` import

- **Only what the `.JOB` frees is free.** In NORMOS, every parameter without
  `…FIT=.TRUE.` is fixed. The importer only carried over the flags of ISO,
  QUA, BHF, WID and DEP. Everything else —relative intensities and widths
  (D13, D23, W13, W23, D21, W21), ETA, THE, PHI, BEX, GAX and the background
  slope (`BKGFIT`)— was left as it was in the session, which is free by
  default. Fitbauer could end up fitting 11 variables where NORMOS fitted 6.
- **Intensity ratios by area.** D13/D23/D21 are area ratios. They used to be
  converted into depth ratios, so freeing W13/W23 also freed the intensities.
  They now go straight into int1/int2 with the by-area intensity convention.
- **NORMOS conventions are switched on.** The NORMOS line pattern (derived
  from the nuclear moments), intensities by area and its relaxation rule are
  activated on import, so the job gives NORMOS's values. With the α-Fe pattern
  used before, the field came out 0.035 % lower: about 0.01 T at 33 T, more
  than the error of a good fit. **Loading another spectrum afterwards switches
  back to Fitbauer's conventions**, unless you chose them by hand in *Fit ›
  Advanced fit options › Conventions (NORMOS compatibility)*.
- **Constraints.** On import, constraints on WID now take the W13 scaling into
  account, and W13/W23 constraints of a sextet are mapped to the right width
  parameters (they were swapped).

## Fix in the `.JOB` export

- **Constraints are written** (`NDEX`/`FACTOR`/`CONST`). They used to be lost.
  NORMOS has been checked to accept them and to fit with the same variables.

## Validation figures corrected

The v5.2.3 notes said that, on 216 real NORMOS jobs, Fitbauer reached the same
or a lower χ² in 211 (median reduced χ² 1.08 → 0.81). Those figures came from
flaws in the comparison itself: the import freed parameters that NORMOS kept
fixed, the refit used the α-Fe line pattern, Fitbauer folded the data
differently, and the χ² was computed on pair averages, giving half of NORMOS's
value.

Redone on the data exactly as NORMOS folds them, with the same model and the
same free parameters, NORMOS's χ² is reproduced to about 1 %. Of 407 distinct
real jobs, 146 are a valid reference. The other 261 are discarded:

- 214 because NORMOS's reduced χ² is above 2;
- 19 because the two programs do not see exactly the same data;
- 28 because they cannot be analysed (missing files, unsupported options).

On the 146:

- Fitbauer reaches the same or a lower χ² in all of them (median 1.40 → 1.38).
- The median agreement is 0.0006 mm/s in δ, 0.0015 mm/s in ΔEQ, 0.0034 T in
  BHF and 0.0014 mm/s in Γ. That is 0.15–0.2 of NORMOS's own standard errors,
  with no bias.
- The few differences above three standard errors are fits where NORMOS had
  stopped short of the minimum. Re-run from Fitbauer's solution, NORMOS
  reaches the same χ².

## Known limitations

These remain. Where marked, the import shows a warning when they apply.

- **Relative widths of a sextet.** NORMOS uses WID (lines 3–4) with W13 and
  W23 relative to it; Fitbauer uses Γ1 (lines 1–6) with Γ2/Γ1 and Γ3/Γ1.
  - The free/fixed status maps exactly when WID, W13 and W23 are all fixed,
    when only WID is free, or when all three are free.
  - With W13 free and WID or W23 fixed, Fitbauer has one or two more free
    width parameters than NORMOS (warned).
  - Constraints on W13/W23 are not exported. On import, only a factor-1
    constraint between W13 values is exact.
- **Area constraints** (`NDEX` on DEP/ARE) are exact at the values in the
  `.JOB`. If the fit changes the widths, the area ratio drifts slightly
  (warned).
- **Folding.** Fitbauer folds at the refined folding point, interpolating
  between channels, and drops dead edge channels. NORMOS adds whole channel
  pairs at ⌊PFP⌋ + 0.5. Line widths can come out about 0.005 mm/s narrower
  than in NORMOS. When NORMOS's folding point is more than about one channel
  from the centre of the spectrum, its edge channels cannot be reproduced
  exactly.
- **Not carried over on import**, as before (warned):
  - the `OME` constraint of the Ising relaxation;
  - the Billard–Chamberod model (`METHOD=3`);
  - several distribution blocks in one job;
  - the absolute `LAMDA` smoothing parameter (use the L-curve).
- **Not written on export:** Hamiltonian treatments, relaxation and
  distribution shapes. The exported `.JOB` is a starting point for NORMOS, not
  an exact translation of every model.

---

Full suite: **763 tests passing**.
