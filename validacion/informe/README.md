# Validation against NORMOS — reports

Fitbauer's physics has been contrasted against **NORMOS** (R. A. Brand,
1990-1994) on two independent benchmarks: a synthetic bank —NORMOS generates
the spectrum from known parameters, Fitbauer fits it, the result is compared
with the truth— and a bank of real jobs fitted in NORMOS over the years.

The project language is Spanish, so the Spanish files are the originals. The
English versions are kept in step with them.

| Report | English | Español |
|---|---|---|
| **Verdict** — synthesis of the four validation rounds: where Fitbauer reproduces NORMOS, where it does not, and what it has that NORMOS does not | [`VERDICT_EN.md`](VERDICT_EN.md) | [`VEREDICTO.md`](VEREDICTO.md) |
| **Coverage** — capability inventory, parameter by parameter, taken from the NORMOS namelists | [`COVERAGE_NORMOS_EN.md`](COVERAGE_NORMOS_EN.md) | [`COBERTURA_NORMOS.md`](COBERTURA_NORMOS.md) |
| **Pending** — roadmap for what is still missing: source reference, what to touch, how to validate it and whether it is worth it | [`PENDING_NORMOS_EN.md`](PENDING_NORMOS_EN.md) | [`PENDIENTE_NORMOS.md`](PENDIENTE_NORMOS.md) |
| **Full report** — case-by-case technical detail of the synthetic bank | [`REPORT_EN.md`](REPORT_EN.md) | [`INFORME.md`](INFORME.md) |

`figuras/` holds the 19 figures cited by the reports, and `catalogo/` a
catalogue of every spectrum in the bank with its fit.

## The numbers, in brief

**Synthetic bank** — 411 spectra, ~1,150 fits, 6,497 comparisons. Median
deviation from the true value: 2·10⁻⁷ mm/s in position and 4·10⁻⁵ T in BHF for
the first-order core; 6·10⁻⁵ mm/s and 8·10⁻⁴ T with the full Hamiltonian.
Regenerated on 2026-10-09 with Fitbauer 5.1.1+ (432 cases, 6,520
comparisons; `generador/banco_completo.sh`): the same medians are reproduced.

**Ising relaxation** — validated against the SITE binary to ~10⁻⁵ of the
peak (`generador/sonda_relajacion*.py`), with `OME` (MHz) = 2k. The August
probe had used `BH0 = BHF` (total polarization, no exchange possible). With
unequal populations NORMOS follows its own rule, available as
`relax_convention="normos"`.

**Real jobs** — 407 distinct fits performed in NORMOS (564 `.JOB` files,
duplicates removed by their `.RES`), reloaded and refitted from NORMOS's
solution with the same free parameters, on the data folded as NORMOS folds
them (whole channel pairs at ⌊PFP⌋ + 0.5). Recomputed this way, NORMOS's
reduced χ² matches the one printed in its `.RES` (median ratio 0.998, 90 %
within 0.96–1.02). Only jobs that are a valid reference count: NORMOS's
reduced χ² ≤ 2 —228 discarded— and both programs seeing the same spectrum
—2 discarded—; 28 cannot be analysed. On the 149 left, Fitbauer matches or
improves on the χ² in all 149 (median 1.41 → 1.36). Median parameter
agreement: δ 0.0007 mm/s, ΔEQ 0.0016, BHF 0.0035 T, Γ 0.0015, depth 0.0001.
The figures hardly change with a cut at 1.5 or 3 (89 and 213 jobs).

Earlier passes of this analysis had four biases of its own, now removed: the
importer dropped the sign of VMAX (23 jobs folded differently) and freed
relative widths and intensities that the `.JOB` kept fixed; the NORMOS line
pattern was overridden by the model's α-Fe one during the refit (BHF 0.035 %
low); and Fitbauer folded at the continuous PFP, by interpolation, while the
χ² was computed on pair averages, half of NORMOS's value.

Among the discarded jobs, two had NORMOS stuck in a local minimum (reduced χ²
29.4 → 1.5 and 26.5 → 1.2): from the same starting values Fitbauer finds the
lower minimum, and NORMOS confirms it when started there.

> The real-job analysis lives in `jobs/_analisis/` (with the job-by-job
> classification, `clasificacion_comparativa.csv`), which is not part of the
> repository: it contains laboratory measurements. Its conclusions are
> summarised here and on the front page.
