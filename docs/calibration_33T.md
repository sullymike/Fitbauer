# Hyperfine-field calibration: α-Fe at 33.0 T

Source: `core/constants.py` (`SEXTET_PATTERNS`, `LINE_POS_33T`, `convert_vmax`)

---

## How calibration works

The six lines of a Fe-57 sextet split in proportion to the hyperfine field $B_{hf}$.
Fitbauer needs two things to go from channels to tesla:

1. **A pattern of line positions at 33.0 T**, which sets the *shape* of the sextet: the
   ratio of the excited-state to the ground-state splitting ($g_1/g_0$).
2. **A velocity calibration** (Vmax), which sets the *scale*. It is obtained by fitting
   an α-Fe spectrum with the field fixed at **33.0 T**, as in NORMOS.

Since Vmax is calibrated with α-Fe at 33.0 T, the absolute scale of the pattern cancels
when fields are measured: a sample's BHF depends only on the shape of the pattern.
Shifts (δ, ΔEQ) do depend on the absolute scale, which the calibration sets.

---

## The default pattern: nuclear moments (since v5.3.0)

Fitbauer derives the line positions from the **nuclear moments**, with the same
constants as NORMOS-SITE (the `"normos"` pattern, checked against the NORMOS binary to
6·10⁻⁶ mm/s):

$$\pm 5.3261 \quad \pm 3.0836 \quad \pm 0.8410 \;\; \text{mm/s at 33.0 T}$$

Its ratio $g_1/g_0 = 0.5714$ is the one Violet and Pipkorn measured for α-Fe at 298 K
(J. Appl. Phys. **42**, 4339, 1971: $g_0 = 3.9098$, $g_1 = 2.2342$ mm/s). With this
pattern Fitbauer and NORMOS give the same field.

---

## The legacy pattern (up to v5.2.4)

Up to v5.2.4 Fitbauer used

$$\pm 5.3285 \quad \pm 3.0835 \quad \pm 0.8385 \;\; \text{mm/s at 33.0 T}$$

described in the code as the "published α-Fe pattern". **It has no published source**:
these are the constants of the laboratory's earlier software, where they were the
32.95 T pattern. In v4.0.2 the 32.95 T was dropped and the same
numbers became the 33.0 T pattern. Its $g_1/g_0$ ratio (0.5724) does not match any
measured pair of moments.

The argument given then against the nuclear moments ("α-Fe read 33.12 T") was circular:
it came from reusing a calibration made with the previous pattern. With Vmax calibrated
with the same pattern, any pattern gives 33.0 T for α-Fe.

The legacy pattern remains available as `"legacy"` (alias `"alpha_fe"`), in
*Fit › Advanced fit options › Conventions*, to reproduce old sessions.

---

## Calibrations made with the legacy pattern

A Vmax calibrated with the legacy pattern is not the one that gives 33.0 T with the new
one. Fitbauer converts it automatically:

$$V_{\max}^{\text{normos}} = 0.999623 \cdot V_{\max}^{\text{legacy}}$$

The factor comes from fitting, with the new pattern (BHF fixed at 33 T, a single width,
3:2:1, free scale), an α-Fe spectrum generated with the legacy one, as the calibration
does. It holds to ±4·10⁻⁶ for widths from 0.18 to 0.40 mm/s.

- Each calibration stores the pattern it was made with (`sextet_pattern`). Local ones
  that do not, from Fitbauer before v5.3.0, are taken as legacy and applied converted.
  The panel and the report say so.
- Those from the web API are the VMAX values calibrated in NORMOS, already in its
  pattern: they are applied as they are. The API marks `sextet_pattern = "legacy"` on
  those the web stored with its old fit ("Store velocity" button, until the web adopted
  this pattern), and those are converted.
- Changing the pattern in the menu re-applies the fixed calibration, converted.
- A file that carries its own velocity axis is left alone: its scale is absolute.
- Saved sessions keep their pattern (those without one were made with the legacy one)
  and are reproduced exactly.

With the calibration converted, a sample's BHF changes by less than 0.01 % (about
0.002 T); δ and ΔEQ by −0.038 %.

---

## The absolute velocity scale

Calling α-Fe 33.0 T is a convention. Violet and Pipkorn measure, for α-Fe at 298 K, an
outer-line separation of 10.612 mm/s; the NORMOS pattern at 33.0 T gives 10.652.
Calibrating with "α-Fe = 33.0 T" leaves the velocity scale **0.38 %** above theirs, as in
NORMOS. It affects δ and ΔEQ (≈0.004 mm/s for a δ of 1 mm/s), not the BHF. For the
highest accuracy in δ and ΔEQ, compare with the measured α-Fe line positions.

---

## Scaling with the field

Positions scale **linearly** from the 33.0 T pattern:

$$v_{0,j} = \delta + q_j \Delta E_Q + v_j^{(33\mathrm{T})}\frac{B_{hf}}{33.0},
\qquad q = [\tfrac12,-\tfrac12,-\tfrac12,-\tfrac12,-\tfrac12,\tfrac12]$$

implemented in `fe57_sextet_positions(bhf_t)` and in `core.physics`. The full
Hamiltonian, relaxation and the distribution kernels read the same active pattern.

---

## Practical check

Load an α-Fe spectrum and fit it with the calibrated Vmax: the BHF must come out very
close to **33.0 T**. A systematic deviation points to a Vmax or folding-point problem,
not to the model.

> **Repository rule.** Reference field **33.0 T**, default pattern the one from the
> nuclear moments (`"normos"`). `core.constants` is the single source; calibrations
> store their pattern and are converted with `convert_vmax`.
