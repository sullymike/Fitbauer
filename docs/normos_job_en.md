# NORMOS interoperability: `.JOB` files

Module: `core/normos_job.py` (pure functions) · GUI: **File ▸ NORMOS (.JOB)**

---

## What it is and why

NORMOS (R. A. Brand, 1990-1994) is the program behind a large part of the
published Mössbauer literature. It runs under DOS, it is proprietary and it is no
longer maintained, yet many laboratories keep years of work stored as `.JOB` files.

Fitbauer reads and writes that format. It **does not run NORMOS and does not ship
it**: it only speaks its text format, which is not proprietary.

---

## Importing

**File ▸ NORMOS (.JOB) ▸ Import NORMOS job…**

It rebuilds the model in the panels **and loads the spectrum**. A `.JOB` names its
files in the first four lines, with no path, because NORMOS ran under DOS with
everything in one directory:

```text
Fe080725.ws5      ← spectrum
distcri1.JOB      ← the job itself
Fe0807di.res      ← results NORMOS will write
Fe0807di.plt      ← plot
 &DATA
 NLTEXT=4, VMAX=-11.966, TRIANG=.true.,
 &END
```

`resuelve_fichero_de_datos()` looks for the spectrum next to the `.JOB`, ignoring
upper/lower case —the names come from DOS and rarely match the case on disk— and
if the declared one is missing it tries the job's own name and, as a last resort,
the only spectrum in the folder. It never returns a NORMOS output (`.RES`/`.PLT`).

> **Keep every file of the job in the same folder.** That is what NORMOS expects
> and what makes the import work in one go.

Two families are recognised automatically:

| Family | What its subspectra are | Where it ends up |
|---|---|---|
| **NORMOS-SITE** | discrete sites | singlet / doublet / sextet components |
| **NORMOS-DIST** | the points of a **grid** | P(BHF)/P(ΔEQ) panel |

For DIST jobs Fitbauer translates the grid (origin and step), the shape (histogram,
Gaussian, binomial or fixed), the δ(x) correlation and the edge anchors; the
"crystalline" subspectra (`NXLS`) become sharp components.

## Exporting

**File ▸ NORMOS (.JOB) ▸ Export NORMOS job…** writes the current model in NORMOS
format. NORMOS has been verified to **accept the file Fitbauer produces**,
reproducing the original theory with a difference of exactly zero.

---

## Convention conversions

This is the delicate part, and getting it wrong raises no error:

| NORMOS | Meaning in Fitbauer |
|---|---|
| `WID`, `W13`, `W23` | `WID` is the width of lines 3,4 and `W13`/`W23` are relative to it; `gamma1` is that of lines 1,6. The conversion is `gamma1 = WID·W13` |
| `D13`, `D23` | **Area** ratios. `int1`/`int2` are **depth** ratios. They agree only when the widths are equal |
| `DEP` (or `ARE`) | The subspectrum **area** in mm/s, not a depth |
| `NDEX`/`FACTOR`/`CONST` | Constraints in NORMOS's **global** numbering, `13 + 15·(n−1)` |

### The BHF scale

NORMOS derives the sextet line positions from the nuclear moments; Fitbauer uses
the published α-Fe pattern. They do not differ by a simple scale factor. To
reproduce one of its BHF values exactly, fit with the NORMOS convention active:

```python
from core.constants import sextet_pattern

with sextet_pattern("normos"):
    ...   # the fit uses NORMOS line positions
```

The difference is about 0.1 T.

---

## The folding point is not imposed

The `PFP` carried in `&DATA` is the **seed** of the folding-point search, not its
result: NORMOS refines it over two cycles, and in real jobs it ends up more than one
channel away from what the file asked for. Fitbauer runs its own search —the
correct counterpart— and reports the `PFP` as information only.

There is a second subtlety. The refined point NORMOS **prints** in its `.RES` is not
where it folds either: its final routine (`normospr.for:601-604`) truncates it and
adds whole channels,

```fortran
IPFA = PFA + 1.0E-4          ! real→integer assignment: truncates
IPFP = PFP + 1.0E-4
DO 602 L=1,NP
  TEMP(L) = Y(IPFA-L+1) + Y(IPFA+L)
```

The pairs sum to `2·IPFA+1`, so the symmetry axis falls at `⌊PFP⌋ + 0.5`. It lives
in `core.normos_job.punto_de_doblado_normos()`, and taking it into account is what
makes its fits reproducible.

---

## What is not carried over

The importer warns about each of these, because what was **not** translated matters
as much as what was:

- Czjzek / Le Caër distributions (`DISTRI=4`) and the Billard–Chamberod neighbour
  model (`METHOD=3`).
- Several overlapping distribution blocks: Fitbauer handles one.
- The `LAMDA` smoothing parameter. NORMOS's is absolute and Fitbauer's `alpha` is
  dimensionless, so there is no one-to-one conversion: set it with the L-curve. The
  `BETA/LAMDA` **ratio** IS preserved and becomes the edge anchor.
- `DTQ` in field distributions. The `distcalf.for` loops for METHOD 1-5 compute
  `RH = BHF+PP*DTB` and `RI = ISO+PP*DTI` and **do not touch ΔEQ**, so carrying it
  over would introduce a correlation NORMOS never applied.

> **Watch out for inherited `.JOB` files.** The DIST format does not accept SITE
> keys such as `NLINE`, `DEP`, `W13` or `W23`. If they were copied from another
> job, NORMOS reads and discards them **without a word**, so that subspectrum never
> entered its fit. Fitbauer does warn about it.

---

## From the command line

The discrete-fit CLI accepts a `.JOB` as a template, detected by content rather
than by extension:

```bash
python mossbauer_fit_cli.py --template MY_JOB.JOB --spectrum measurement.ws5
python mossbauer_fit_cli.py --template model.json --spectrum measurement.ws5 \
       --export-job OUTPUT.JOB
```

---

## Validation

The equivalence with NORMOS is not a statement of intent: it is measured on two
independent benchmarks —411 synthetic spectra and 564 real fits made with the
original program— with the full reports in
[`validacion/informe/`](https://github.com/sullymike/Fitbauer/tree/main/validacion/informe).

In 355 of 503 comparable jobs (71 %) Fitbauer matches or improves on NORMOS's
reduced χ².
