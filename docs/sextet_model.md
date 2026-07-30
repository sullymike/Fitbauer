# Sextet model specification (Fe-57) — source of truth

> **Purpose.** This document describes **exactly** how Fitbauer computes the magnetic
> sextet, so that any other implementation (in particular the **web** application the
> program originally grew out of) can reproduce an **identical** fit. It is the
> reference contract: if the web follows this document, the same parameters will
> produce the same absorption and the same transmission.
>
> The canonical implementation lives in `core/physics.py`, `core/constants.py` and
> `core/hamiltonian.py`. If this document and the code disagree, **the code wins**.

---

## 1. General conventions

- **Velocity axis** `v` in **mm/s**. The sign is preserved as-is (it may be negative;
  see folding in §7).
- **Transmission model** (not absorption): the observed spectrum dips below a baseline.
  For a single component:

  ```
  T(v) = baseline + slope · v − A(v)
  ```

  where `A(v) ≥ 0` is the absorption of the component. With several components the total
  absorption `A_tot = Σ A_c` is summed before subtracting (see §6).
- **Parameter units**: `δ` (delta), `ΔE_Q` (quad) and the `Γ` values in mm/s; `BHF` in
  tesla (T); intensities dimensionless; `depth` dimensionless (absorption scale).

---

## 2. Sextet parameters

Canonical order (see `SEXTET_PARAM_NAMES` in `core/constants.py`):

| # | Name     | Symbol         | Meaning |
|---|----------|----------------|---------|
| 0 | `delta`  | δ              | Isomer shift (mm/s) |
| 1 | `quad`   | ΔE_Q           | First-order quadrupole splitting (mm/s) |
| 2 | `bhf`    | B_hf           | Hyperfine field (T) |
| 3 | `gamma1` | Γ₁             | HWHM width of lines **1 and 6** (mm/s) |
| 4 | `gamma2` | Γ₂(rel)        | **Relative** width of lines 2 and 5 |
| 5 | `gamma3` | Γ₃(rel)        | **Relative** width of lines 3 and 4 |
| 6 | `depth`  | d              | Depth (global absorption scale) |
| 7 | `int1`   | I₁₃            | Relative intensity of lines 1,6 with respect to 3,4 |
| 8 | `int2`   | I₂₃            | Relative intensity of lines 2,5 with respect to 3,4 |
| 9 | `int3`   | I (base)       | Base intensity of lines 3,4 (NORMOS convention: **fixed to 1**) |

The six lines are indexed **1..6** from left to right in velocity.

---

## 3. Positions of the six lines (first-order model, historical)

This is the default treatment (`treatment="1st_order"`), the one the web must replicate.

### 3.1 Calibration pattern at 33.0 T

The positions come from the **published α-Fe velocity standard**, NOT from the nuclear
moments (see §8). In `core/constants.py`:

```
_BASE_POSITIONS = [-10.657, -6.167, -1.677, 1.677, 6.167, 10.657] · 0.5
                = [ -5.3285, -3.0835, -0.8385, 0.8385, 3.0835, 5.3285]   (mm/s)

BHF_DEFAULT_T = 33.0
LINE_POS_33T  = _BASE_POSITIONS              # positions at exactly 33.0 T
```

> ⚠️ **Do not derive these positions from the nuclear moments.** The textbook
> calculation gives a splitting ~0.4 % smaller (outer line 5.309 vs 5.328 mm/s) and
> biases the BHF ~0.1 T upwards. The constant 33.0 T *is* the calibration; an α-Fe
> spectrum must fit to exactly 33.0 T, just as in NORMOS.

### 3.2 Effective positions

The positions scale **linearly** with the field and are shifted by δ and by the
quadrupole pattern:

```
LINE_QUAD_PATTERN = [ +0.5, −0.5, −0.5, −0.5, −0.5, +0.5 ]

position_i = LINE_POS_33T[i] · (BHF / 33.0) + δ + ΔE_Q · LINE_QUAD_PATTERN[i]
```

That is: the field scales the magnetic splitting, δ shifts the whole sextet, and the
first-order quadrupole separates the outer pair (lines 1,6: +ΔE_Q/2) from the rest
(lines 2,3,4,5: −ΔE_Q/2).

---

## 4. Intensities and widths of the six lines

### 4.1 Intensities (relative weights)

```
i3 = int3                 # lines 3 and 4
i2 = int3 · int2          # lines 2 and 5
i1 = int3 · int1          # lines 1 and 6

weights = [ i1, i2, i3, i3, i2, i1 ]
```

With the default NORMOS convention (`int3 = 1`, `int2 = 2`, `int1 = 3`) this yields the
classic **3 : 2 : 1 : 1 : 2 : 3** pattern.

### 4.2 Widths (HWHM, half width at half maximum)

`gamma2` and `gamma3` are **relative multipliers** applied to `gamma1`, not absolute
widths:

```
g1 = gamma1               # lines 1 and 6
g2 = gamma1 · gamma2      # lines 2 and 5
g3 = gamma1 · gamma3      # lines 3 and 4

gammas = [ g1, g2, g3, g3, g2, g1 ]
```

---

## 5. Line profile

Each line contributes `weight · profile(v; centre, γ)`. Two profiles are selectable; the
global state lives in `core/physics.py` (`LINE_PROFILE_KIND`, `VOIGT_SIGMA`).

### 5.1 Lorentzian (default), normalized to peak = 1

```
L(v; v0, γ) = γ² / ( (v − v0)² + γ² )
```

`γ` is the HWHM. `L(v0) = 1` at the centre.

### 5.2 Voigt (optional), normalized to peak = 1

Using the Faddeeva function `w(z)` (`scipy.special.wofz`), with `σ = VOIGT_SIGMA`:

```
denom = σ · √2
norm  = σ · √(2π)

V(v; v0, γ) = Re[ w( ((v − v0) + iγ) / denom ) ] / norm
peak        = Re[ w( iγ / denom ) ] / norm

profile     = V / peak          # normalized to 1 at the centre
```

> The normalization is **analytic at the peak** (it does not divide by the discrete
> maximum over the grid). This avoids underestimating the peak when the velocity grid
> does not fall exactly on `v0`. The web must normalize the same way to match.

---

## 6. Total absorption and transmission

### 6.1 Absorption of a sextet

```
A_sextet(v) = depth · Σ_{i=1..6}  weights[i] · profile(v; position_i, gammas[i])
```

### 6.2 Total transmission model

```
A_tot(v) = Σ_c  A_c(v)                         # sum over all active components
T(v)     = baseline + slope · v − A_eff(v)
```

where by default `A_eff = A_tot` (thin-absorber, linear model). There is an optional
**thick-absorber / saturation** mode with amplitude `C = sat_scale > 0`:

```
A_eff(v) = C · ( 1 − exp(−A_tot(v) / C) )       # the C→∞ limit recovers A_eff = A_tot
```

If the web only implements the thin model, it must use `A_eff = A_tot` (equivalent to
leaving saturation switched off in Fitbauer).

---

## 7. Folding, normalization and velocity axis — **CRITICAL**

For a fit over **the same spectrum** to agree, the forward model (§3–§6) is **not
enough**: the data must be folded the same way, normalized the same way, and the
velocity axis must be built the same way. If the web folds differently, the `BHF`, the
positions and the areas will come out different even if the sextet model is identical.
The canonical implementation is `core/folding.py`. This section is the part that
**diverges most** between implementations, so it is specified in full.

### 7.1 What folding is and why

The detector records `N` channels (typically 512) containing the spectrum **twice**
(forward and backward strokes of the transducer), mirrored about a **symmetry centre**
(the *folding point*). Folding = averaging each channel with its mirror to obtain `N/2`
points (typically 256) with a better signal-to-noise ratio. The result is ordered from
negative to positive velocity.

### 7.2 Channel numbering and centre

- Channels are numbered **1..N** (1-based), **not** 0-based. This matters for the formula.
- The `center` (internal folding point) is the **symmetry centre** and may be
  **fractional** (e.g. 255.77), not just integer or half-integer.
- **Relation to Normos**: the number Normos reports ("Final/Upper folding point") is
  usually in **full-spectrum** convention (≈ 511 for 512 channels) and is
  **approximately twice** this GUI's internal centre (≈ 255.5). Conversion in
  `read_normos_folding_point`: if the value is `≥ 400` → full spectrum → divide by 2;
  if `< 400` → already a half-spectrum → use as-is.

### 7.3 Folding algorithm (`fold_integer_or_half`)

Always produces `n_out = N // 2` points. For each point `j = 0 .. n_out−1`:

```
distance   = j + 0.5
left_chan  = center − distance
right_chan = center + distance
folded[j]  = 0.5 · ( C(left_chan) + C(right_chan) )
```

where `C(channel)` is the 1-based **sub-channel linear interpolation**
(`interp_channel_1based`):

```
# channels 1..N, values counts[0..N-1]
if channel < 1:      C = counts[0]   + (channel − 1) · (counts[1]   − counts[0])      # extrapolates
if channel ≥ N:      C = counts[N-1] + (channel − N) · (counts[N-1] − counts[N-2])    # extrapolates
otherwise:
    lo   = floor(channel)
    frac = channel − lo
    if frac ≈ 0:     C = counts[lo−1]
    else:            C = (1 − frac)·counts[lo−1] + frac·counts[lo]
```

> **Key to reproducing Normos**: folding does NOT stop at integer channel pairs. For
> fractional centres it uses linear interpolation, and at the edges it **extrapolates**
> linearly instead of dropping a channel. That way it always yields `N/2` points.

### 7.4 Folding-point search (`find_best_integer_or_half_center`)

If it is not supplied by Normos, it is found by minimizing the χ² of the difference
between symmetric channels:

1. Candidate grid in steps of 0.5 (by default 250.5 .. 262.5 for 512 channels).
2. For each centre, `χ²(center) = Σ (counts[left] − counts[right])²` over the pairs.
3. The centre of minimum χ² is taken and the minimum is **parabolically interpolated**
   (sub-channel refinement) using the three points around it.

### 7.5 Edge trimming and normalization (`fold_and_normalize`)

```
folded = fold_integer_or_half(counts, center)
# Trims edge_trim channels at each end (1 by default), if the array is large enough:
if edge_trim > 0 and folded.size > 2·edge_trim + 2:
    folded = folded[edge_trim : −edge_trim]

norm  = percentile_90(folded)        # ≈ baseline
y     = folded / norm                # normalized spectrum (~1 at the baseline)
sigma = sqrt( max(folded/2, 1) ) / norm   # normalized Poisson noise
```

- **Edge trimming**: the outermost channels of the folded spectrum are less reliable and
  are discarded (`edge_trim = 1` by default). Note it only trims if the array is large
  enough (`> 2·edge_trim + 2`); for real 256-point spectra it always applies.
- **Normalization**: by the **90th percentile** of the folded counts (a robust baseline
  estimator), not by the maximum.
- **Poisson σ**: `sqrt(folded/2)` (the `/2` comes from averaging two channels) floored at
  1 count, divided by `norm`. These `sigma` values are the **fit weights** (see §8).

### 7.6 Velocity axis (`velocity_axis`) — do not stretch the scale

```
full_n   = N // 2
velocity = linspace(−Vmax, +Vmax, full_n)        # build the FULL axis first
# trim the SAME edge positions as in the data:
if edge_trim > 0 and the size matches:
    velocity = velocity[edge_trim : −edge_trim]
```

> ⚠️ **Classic mistake to avoid**: do NOT rebuild the axis as
> `linspace(−Vmax, +Vmax, trimmed_n_points)`. The full `N/2`-point axis must be built and
> then trimmed at the same edges as the data. Rebuilding it with fewer points
> **stretches the velocity scale and biases the BHF**.

- `Vmax` may be **negative**; the sign is preserved (NORMOS/web compatibility with an
  inverted axis).

### 7.7 Numerical folding contract (verifiable)

Reproducible example with `core/folding.py`. **Input**: 8 channels (1-based)

```
counts = [100, 90, 70, 95, 98, 60, 88, 105]
```

**Folding at half-integer centre `center = 4.5`** → pairs `(4,5) (3,6) (2,7) (1,8)`:

```
folded = [ 96.5, 65.0, 89.0, 102.5 ]
```

**Folding at fractional centre `center = 4.30`** (shows the sub-channel interpolation):

```
folded = [ 93.7, 70.8, 87.2, 101.8 ]
```

**`fold_and_normalize(counts, center=4.5, edge_trim=1)`** (on this small array of 4
folded points, `edge_trim` does not trim because `4 ≤ 2·1+2`):

```
norm  = 100.7                                          # 90th percentile
y     = [ 0.958292, 0.645482, 0.883813, 1.017875 ]
sigma = [ 0.068979, 0.056612, 0.066245, 0.071091 ]
```

**`velocity_axis(N=8, Vmax=4.0, n_points=4, edge_trim=1)`**:

```
velocity = [ −4.0, −1.333333, +1.333333, +4.0 ]
```

> If the web reproduces these four blocks (to a tolerance of ~1e-6), the folding, the
> normalization and the axis are **identical**. Keep this vector as a regression test.

### 7.8 Reading Normos sidecars (optional)

`core/folding.py` also reads parameters from associated Normos files to seed the fit
(this does not affect the model, only the starting values):

- `.RES`: final values `ISO→δ`, `BHF`, `QUA→ΔE_Q`, `WID` (Normos reports **FWHM**; the
  internal Lorentzian uses **HWHM** = FWHM/2!), `ARE→depth` (via `ARE / (π·Γ·Σweights)`,
  with `Σweights = 2·(3+2+1) = 12`).
- `.JOB`: `VMAX`, `QUA(1)`.
- `.PLT`: `Vmax` from the blocks of 256 values.

---

## 8. Fit objective function (affects the fitted values)

Two implementations can share the forward model and **still** return different fitted
parameters if they minimize different things. Fitbauer (`core/fit_engine.py`) uses:

- **Poisson weights** (counts): residual weighted by the variance ≈ counts.
- Non-linear least squares (TRF) with deterministic multistart; optional robust loss and
  global differential evolution.
- Physical parameter bounds (ranges for `BHF`, `ΔE_Q`, etc.).

For a fit **identical** to Fitbauer's, the web must match: the forward model (§3–§6)
**and** the weighting scheme **and** the same bounds/seed. If the web only needs the
**same curve** given parameters (simulation), §3–§6 suffice.

---

## 9. Reference vector (verifiable numerical contract)

Values generated by running `core/physics.py` (Lorentzian profile, first-order mode).
**Parameters**: `δ=0`, `ΔE_Q=0`, `BHF=33.0`, `Γ₁=0.300`, `Γ₂rel=Γ₃rel=1.0`,
`depth=0.02`, `int1=3`, `int2=2`, `int3=1` → weights `3:2:1:1:2:3`, `baseline=1`,
`slope=0`.

> `Γ₁ = 0.300` is the **HWHM** value passed to `sextet_absorption` (equivalent to
> FWHM = 0.600 mm/s). Mind this distinction: it is the same trap described in §7.8 for
> the Normos sidecars.

**Positions of the 6 lines (mm/s):**

```
[ −5.3285, −3.0835, −0.8385, +0.8385, +3.0835, +5.3285 ]
```

**Sampled absorption and transmission:**

| v (mm/s)  | A(v)      | T(v) = 1 − A(v) |
|-----------|-----------|-----------------|
| −5.3285   | 0.060236  | 0.939764        |
| −3.0835   | 0.040427  | 0.959573        |
| −0.8385   | 0.020497  | 0.979503        |
|  0.0      | 0.001524  | 0.998476        |
| +0.8385   | 0.020497  | 0.979503        |
| +3.0835   | 0.040427  | 0.959573        |
| +5.3285   | 0.060236  | 0.939764        |

> If the web implementation reproduces this table (to a tolerance of ~1e-6), the forward
> sextet model is **identical**. It is worth keeping this vector as a regression test on
> both sides.

---

## 10. Advanced treatments (optional)

By default the web only needs the **first order** (§3). For completeness,
`core/physics.py` + `core/hamiltonian.py` offer two further quadrupole treatments, by
diagonalizing the Hamiltonian `ω_e·I_z + (ΔE_Q/6)(3 I_{z'}² − I(I+1))` (axial EFG, η=0):

- `kundig_fixed`: fixed angle β between B and V_zz.
- `kundig_powder`: polycrystalline average by Gauss–Legendre quadrature over `n_quad`
  orientations (β ∈ [0, π]).

Only replicate these if the web is going to offer those modes.

---

## 11. Checklist for aligning the web

1. [ ] Base α-Fe positions at 33.0 T = `±0.8385 / ±3.0835 / ±5.3285` mm/s (§3.1).
2. [ ] Linear scaling `· (BHF/33.0)`, shift `+δ`, quadrupole pattern
       `[+0.5,−0.5,−0.5,−0.5,−0.5,+0.5]·ΔE_Q` (§3.2).
3. [ ] Intensities `[i1,i2,i3,i3,i2,i1]` with `i1=int3·int1`, `i2=int3·int2`, `i3=int3`
       (§4.1).
4. [ ] Widths `gamma2/gamma3` as **multipliers** of `gamma1` (§4.2).
5. [ ] Lorentzian with peak = 1 (or Voigt with analytic peak normalization) (§5).
6. [ ] Transmission `baseline + slope·v − A_tot`; optional saturation (§6).
7. [ ] **Folding** (§7) — only if comparing over data:
   - [ ] **1-based** channels; possibly fractional symmetry centre (§7.2).
   - [ ] Normos folding-point conversion (≈ twice the internal centre) (§7.2).
   - [ ] Folding `0.5·(C(center−(j+0.5)) + C(center+(j+0.5)))` with sub-channel linear
         interpolation and edge extrapolation (§7.3).
   - [ ] Edge trimming `edge_trim=1` (§7.5).
   - [ ] Normalization by the **90th percentile** and `σ = sqrt(max(folded/2,1))/norm`
         (§7.5).
   - [ ] Velocity axis built in full and then trimmed, **not rebuilt** with fewer points
         (§7.6).
   - [ ] Reproduce the numerical folding contract (§7.7).
8. [ ] Same Poisson weighting scheme (the `σ` of §7.5) and bounds — only if the same
       **fit** is required, not just the same curve (§8).
9. [ ] Reproduce the forward-model reference vector of §9 as a test.

---

## 12. What is needed to produce a concrete "what to change" for the web

This document is the specification of the Fitbauer side. To deliver an **exact delta**
(which lines to change in the web) it helps to have:

- The **current web code** that computes the sextet (formulas for positions,
  intensities, profile, transmission) and the language/stack (JS, PHP, Python…).
- If it exists, the **reference field value** the web uses (32.95 T? 33.0 T?) and its
  base positions — this is the most likely cause of the historical discrepancy.
- A test spectrum (e.g. α-Fe) fitted on both sides to compare numbers.
