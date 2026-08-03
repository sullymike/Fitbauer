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
| **Full report** — case-by-case technical detail of the synthetic bank (847 lines) | — | [`INFORME.md`](INFORME.md) |

`figuras/` holds the 19 figures cited by the reports, and `catalogo/` a
catalogue of every spectrum in the bank with its fit.

## The numbers, in brief

**Synthetic bank** — 411 spectra, ~1,150 fits, 6,497 comparisons. Median
deviation from the true value: 2·10⁻⁷ mm/s in position and 4·10⁻⁵ T in BHF for
the first-order core; 6·10⁻⁵ mm/s and 8·10⁻⁴ T with the full Hamiltonian.

**Real jobs** — 564 fits performed in NORMOS, reloaded and reproduced. In 355
of 503 comparable jobs (71 %) Fitbauer matches or improves on its reduced χ²
(median 2.433 → 2.089). Parameter agreement: δ 0.0011 mm/s, ΔEQ 0.0019,
BHF 0.017 T, Γ 0.030, area 0.0036.

> The real-job analysis lives in `jobs/_analisis/`, which is not part of the
> repository: it contains laboratory measurements. Its conclusions are
> summarised here and on the front page.
