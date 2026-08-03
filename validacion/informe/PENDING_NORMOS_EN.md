# Pending versus NORMOS — roadmap

*English version of `PENDIENTE_NORMOS.md`. The Spanish file is the original;
this one is kept in step with it.*

**Status as of 2026-08-02.** Companion to `COVERAGE_NORMOS_EN.md`, which says
WHAT is missing; this document says HOW to do it. Each entry carries the exact
source reference, what to touch in Fitbauer, how to validate it and an honest
estimate of whether it is worth it.

Nothing that remains has a clear experimental demand for ⁵⁷Fe. They are ordered
by descending value in my judgement; item 1 is the only one I would recommend
up front.

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

## 1. Analytical Czjzek / Le Caër (`DISTRI=4`)

**What it is.** Parametric forms for the electric field gradient distribution
in disordered solids. Czjzek with `METHOD=6` (quadrupole without field), Le
Caër with `METHOD=7`. They are fitted with 2-3 parameters instead of a 40-60
bin histogram.

**In NORMOS.** `distinif.for` (construction of the probability grid) and
`distcalf.for:104` and `:167`. The `CZJZEK` routine in `sitegmfp.for:1153` is
something else: those are the order 3-5 corrections over the Hamiltonian lines.

**In Fitbauer today.** The histogram reproduces the shape without needing the
analytical form — validated in series L2 of the bank, with ⟨x⟩ to 0.004 and σ
to 0.015. What is missing is the parametric form.

**What would need doing.**
- A `czjzek_distribution(grid, sigma, mu)` function in `mossbauer_distribution`
  alongside the other parametric shapes.
- Register it in `DISTRIBUTION_SHAPES` (`core/params.py`) and in the panel
  selector (`gui/distribution_panel.py`), plus the CLI (`--shape czjzek`).
- The fit follows the same route as Binomial/Gaussian (parametric shapes, no
  `alpha`).

**Validation.** Feasible: the demo supports `DISTRI=4` with `METHOD=6`
(confirmed in the inventory). A new bank series in the style of `serie_L.py`.

**Cost / value.** Medium / medium. I would only do it if you work with metallic
glasses or amorphous materials and want to publish 2-3 parameters instead of a
curve. Otherwise the histogram already gives you the shape.

---

## 2. `BEXT` — external field in Ising relaxation

**What it is.** An applied external field shifts the lines as well as
polarizing the populations. In `ISIRLX`, `VL0 = AL(j)·BEXT` enters the
imaginary part of the eigenvalues.

**In NORMOS.** `siterelx.for:68` (`VL0 = AL(J)*BEXT`) and its use in
`XP/YP/XN/YN` and in `BB`/`CC`.

**In Fitbauer today.** Population polarization is in place
(`relax_polarization`); the shift is not. The `ISIRLX` port in
`tests/test_relajacion_normos.py::_isirlx` **already accepts `vl0`**, so the
reference for validating it is written.

**What would need doing.**
- Add `vl0` to `_blume_polarizado` in `core/physics.py` (the formula is already
  ported; it just has to stop being pinned to 0).
- A `relax_bext` component parameter in `core/params.py` (registry, bounds,
  `USED_BY["BlumeTjon"]`) and in the `extras` of `core/fit_engine.py:258`.

**Validation.** **Not** with the demo binary: `BSAT` is not in its namelist and
its `IRELAX` spectra come out almost collapsed even with `OME=0` (§19 of
`REPORT_EN.md`). It is validated against the `ISIRLX` port, as was done with the
polarization.

**Cost / value.** Low / low. Half an hour, but only useful if you measure with
a magnet.

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
4. The review tests are in `tests/test_*_normos.py` and several carry a
   **literal port** of the Fortran routine as a reference (`_isirlx`,
   `_smooth_normos`, `_energias_referencia`): reuse them.
