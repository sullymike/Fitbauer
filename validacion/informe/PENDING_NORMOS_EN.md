# Pending versus NORMOS — roadmap

*English version of `PENDIENTE_NORMOS.md`. The Spanish file is the original;
this one is kept in step with it.*

**Status as of 2026-08-02; items 1 and 2 closed on 2026-10-15.** Companion to `COVERAGE_NORMOS_EN.md`, which says
WHAT is missing; this document says HOW to do it. Each entry carries the exact
source reference, what to touch in Fitbauer, how to validate it and an honest
estimate of whether it is worth it.

Nothing that remains has a clear experimental demand for ⁵⁷Fe. They are ordered
by descending value in my judgement. Item 1, the only one I recommended up
front, is covered in its useful part (the quadrupole Czjzek); what remains of
it is minor.

---

## Before you start: things that save hours

Traps already paid for during this review. Worth reading before touching
anything.

- **The source is in `normos/`**, doubly gitignored (proprietary, never into the
  repo). Dated 1990; the demo binary is from 1993/94 and **differs in several
  places** — always verify against the binary, not just by reading the Fortran.
- **DOSBox is a snap and does NOT see `/tmp`.** Staging has to live under
  `$HOME` (use `normos_lib.STAGING_ROOT`). If the `.PLT` does not appear, check
  the log: it will say `MOUNT: Path ... not found`.
- **`IFTRAN`, `HAMILT`, `SRELAX` go in `&PARAM`, not in `&DATA`.** Putting them
  in `&DATA` gives `ERROR OR EOF IN NAMELIST` with no further clue.
- Namelist lines cannot exceed **72 columns**.
- The demo has limits: `NSUB ≤ 10`, 512 channels, no isotopes.
- **Probe before implementing.** Several switches are inert in the demo (`STI`,
  `DEPSUB`, `IFGK`, `S2T`, `VOIGT/WDLOR`); others that looked inert turned out
  to be live (`AKS`, `FSO`). The pattern that works: generate 4-5 cases
  differing in a single parameter and compare the `.PLT` files. Ready-made
  templates: `validacion/generador/paso0_sondas.py`.
- **When comparing line shapes, mind the widths.** NORMOS uses two (`WD` in the
  eigenvalues, `WDS` in the convolution) where Fitbauer uses one. Counting both
  introduces a ~2 % residual that does not come from the model. This already
  cost me a wrong conclusion about relaxation.
- The whole bank has its folding point at **256.5** (half-integer), so nothing
  that depends on sub-channel interpolation shows up in it.

---

## 1. `DISTRI=4` with `METHOD=7`: the in-field Le Caër — CLOSED 2026-10-15

“Le Caër” shape (`lecaer_weights`, `fit_czjzek_hyperfine_distribution(lecaer=True)`),
importer, panel, CLI (`--shape lecaer`) and tests. Details, and what could not be
validated (probe of the binary: the spline file is missing), in
`COVERAGE_NORMOS_EN.md` §9.

---

## 2. `BEXT` — external field in Ising relaxation — CLOSED 2026-10-15

Parameter `relax_bext` (T) of the Blume–Tjon component: the two states see
BEXT ± BHF and each line shifts equally in both (`two_state_sextet_absorption`,
`core/physics.py`), like the `VL0 = AL(J)*BEXT` of `siterelx.for`. Fixed by
default (it is a datum) and «Free all» does not release it. Validated against
Blume's matrix equation with the states at BEXT ± BHF and in the slow (two
sextets) and fast (sextet of field BEXT) limits: `tests/test_relajacion_normos.py`.
It could not be compared with the binary: the demo does not accept `BSAT`/`BEXT`.

---

## 3. Emission spectra (`EMSPEC`)

**What it is.** The Mössbauer source as the sample (MES): the spectrum comes
out inverted.

**In NORMOS.** A single sign: `SGN = +1.0` instead of `−1.0`
(`sitecalf.for:131`), applied in `YC = BKG1·(BK + SGN·YC)`.

**In Fitbauer today.** `total_model` always subtracts the absorption.

**What would need doing.** An `emission: bool` model flag in `FitState` /
`ModelState` that flips the sign in `core/physics.total_model`. Trivial in the
engine; the work is in exposing it (GUI + i18n in 8 languages + manual).

**Cost / value.** Low in core, medium with the GUI / low unless you do MES.

---

## 4. Other isotopes (¹¹⁹Sn, ¹⁹⁷Au, ¹⁵¹Eu, ¹²¹Sb)

**What it is.** NORMOS parametrises the isotope with `ISTYPE` and derives
`WIDNAT`, `GFR`, `QMR`, `SEX`, `SG`, `GFACT`, `EGAMMA` and `PARITY` from it.

**In NORMOS.** `sitecalf.for:161-245`, the chain of `IF(INDEX(ISTYPE,...))`.
All the values are there, tabulated and ready to copy.

**In Fitbauer today.** ⁵⁷Fe only. The sextet pattern is already selectable
(`SEXTET_PATTERNS`), which is half the road.

**What would need doing.** Quite a lot: `core/constants.py` would have to go
from ⁵⁷Fe constants to a per-isotope registry, and `core/hamiltonian.py` is
written for I=3/2→1/2 (fixed 4×4 matrices). For Eu/Sb (I=5/2→7/2) the spin
matrices would have to be generalised — NORMOS already does this with `SPNP`
(`sitegmfp.for:245`), which builds the matrices for any spin.

**Cost / value.** High / low, unless the laboratory changes isotope. This is
the decision of whether Fitbauer remains a ⁵⁷Fe program.

---

## 5. Data preprocessing

**What it is.** Three acquisition utilities NORMOS applies on reading:
- `NADD` — add neighbouring channels (rebin) to improve the statistics.
- `NDECKS` — add several spectra from the same file.
- `MULT`/`ADD` — scale and offset the counts.

**In NORMOS.** `normospr.for:1084-1108` (`NADD`, with the readjustment of `ND`,
`PFP` and `DELV`) and `:1035-1056` (`NDECKS`, `MULT`, `ADD`).

**What would need doing.** Pure functions in `core/folding.py` and a
pre-processing step in `HeadlessSession.load_ws5`. Careful with `NADD`: the
folding centre and the velocity step have to be rescaled, which is where NORMOS
gets complicated.

**Cost / value.** Low / low. It can be handled outside with four lines of
numpy.

---

## 6. M1+E2 multipole mixing (`PHS`/`MIX`)

**In NORMOS.** `sitegmfp.for`, the branches with `AS1 = |AMIX|·exp(i·PHASE)`
and the `CL1` coefficients (Clebsch–Gordan of multipolarity L+1).

**Why not.** For ⁵⁷Fe the transition is pure M1 and SITE itself hard-wires
`MIX = 0.0` (`sitecalf.for:165`). It only makes sense together with item 4.

**Cost / value.** Medium / nil in ⁵⁷Fe.

---

## Partials: covered by another route, improvable

These are not gaps, but they appear as **~** in `COVERAGE_NORMOS_EN.md`.

| | Situation | What would be missing |
|---|---|---|
| **Octet** (`NLINE=8`) | modelled as sextet + 2 singlets, validated in series K1 | an 8-line component of its own, with the ΔmI=±2 lines tied to the same BHF |
| **`STB`** (Czjzek over the Hamiltonian) | covered with Voigt σ_B / Gaussian shape | the order 3-5 corrections of `CZJZEK` (`sitegmfp.for:1153`), which correct position and intensity as well as the width |
| **`EFGB`** (Blaes) | the orientation average exists in `kundig_powder` and in the Hamiltonian kernel | in the DISCRETE component, combining the orientation average with η ≠ 0 |
| **`METHOD=7`** | the "Fixed" shape loads P from file | making it accept a magnetic field as well |
| **2 distribution blocks** | sharp components + 2D P(BHF,ΔEQ) | two independent overlapping distributions, each with its own grid |

Of these, the most defensible is the **octet of its own**: it works today but
forces you to declare three components and tie them by hand.

---

## How to pick this up again

1. Read `COVERAGE_NORMOS_EN.md` (what there is and what is missing) and this
   document (how).
2. The validation bank is regenerated with `validacion/generador/`; new series
   follow the pattern of `series_M.py` (asymmetry) and `series_N.py` (FSO),
   which are the two most recent and the cleanest.
3. Probe the binary BEFORE implementing, using `paso0_sondas.py` as a template.
4. The review tests are in `tests/test_*_normos.py` and several carry an
   independent reference (`_smooth_normos`, `_energias_referencia`), written
   from the mathematical definition: reuse them. The NORMOS code is
   proprietary and is not copied, not even in tests.
