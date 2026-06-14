# Folding of Mössbauer spectra

Module: `core/folding.py` (pure functions, no GUI)

---

## Why folding is needed

A constant-acceleration Mössbauer spectrometer records **two symmetric
half-spectra**: the detector sees the same sequence of velocities in the forward
sweep and in the return sweep. A file of $N$ channels (typically 512) contains two
copies of the spectrum, one reflected with respect to the other about a **symmetry
point** (the *folding point*). Folding (averaging the two half-spectra) produces a
single spectrum of $N/2$ points with a signal/noise ratio $\sqrt{2}$ better and
removes the duplication.

---

## Folding point

The folding point is the symmetry channel $c$ that minimizes the difference between
the two half-spectra. For each candidate $c$ the following is computed:

$$\chi^2(c) = \sum_{\text{pares}} \bigl[C(c - d) - C(c + d)\bigr]^2$$

where $d = j + 0.5$ runs through the distances to the center and $C(\cdot)$ is the
interpolated count (channels numbered 1..N). The minimum is first searched on a grid
of half-channels and then **parabolically interpolated** to obtain subchannel
precision (`find_best_integer_or_half_center`).

> **Normos convention.** Fitbauer internally uses the symmetry center
> (≈ 255.77 for a Normos *upper folding point* ≈ 511.55 in 512 channels). The number
> Normos reports is approximately **twice** the internal center.
> `read_normos_folding_point` reads the "Final folding point" from the `.RES` sidecar
> and converts it: if the value is ≥ 400 it is interpreted as full-spectrum
> convention (÷2); if it is < 400, as a half-spectrum.

---

## Channel interpolation (`interp_channel_1based`)

The folding point rarely falls on an integer channel. The function folds into $N/2$
points in the Normos style, obtaining each count by **linear interpolation** between
adjacent channels. At the edges (channels outside the range 1..N), **minimal linear
extrapolation** is used, which avoids losing a channel for half-integer centers such
as 255.5 in 512-channel spectra.

For each folded point $j$ (with $j = 0..N/2-1$):

$$F_j = \tfrac{1}{2}\bigl[C(c - (j{+}0.5)) + C(c + (j{+}0.5))\bigr]$$

The result is sorted from negative to positive velocity.

---

## Edge trimming and normalization (`fold_and_normalize`)

After folding, the **edge channels** (first and last) are less reliable because they
come from extrapolation. By default, `EDGE_TRIM_DEFAULT = 1` channel is trimmed at
each end.

Normalization brings the baseline to ≈ 1.0 using the **90th percentile** of the
folded spectrum (robust against the absorption peaks, which are minima):

$$\mathrm{norm} = P_{90}(F), \qquad y_i = \frac{F_i}{\mathrm{norm}}$$

Poisson noise is propagated taking into account that each folded point is the mean of
**two** Poisson channels:

$$\sigma_i = \frac{\sqrt{\max(F_i / 2,\; 1)}}{\mathrm{norm}}$$

The function returns the tuple `(folded, sigma, y, norm)`.

---

## Velocity axis (`velocity_axis`)

The velocity axis goes from $-v_{\max}$ to $+v_{\max}$ with $N/2$ points:

$$v = \mathrm{linspace}(-v_{\max},\; +v_{\max},\; N/2)$$

**Important:** the axis is trimmed at the **same positions** as the spectrum
(`[edge_trim:-edge_trim]`), it is not rescaled. Rescaling the axis after trimming
would stretch the velocity scale and bias the fitted BHF.

---

## Pre-folded CSV/velocity format (`load_velocity_csv`)

For spectra already folded in velocity space (e.g. ESRF synchrotron data), a
**two-column** `velocity, counts` CSV/TXT/DAT/EXP format is supported:

- Separators: comma, tab or spaces.
- Comment lines (`#`) or non-numeric header are ignored.
- If all values in column 2 are ≤ 1.0, they are interpreted as **normalized
  transmission** and scaled to counts (`round(2_000_000 · col2)`).
- Inverted-column detection: if col0 has everything > 100 and col1 everything in
  [−20, 20], an error is raised suggesting that the columns be inverted.
- Deduplication: velocities closer than $10^{-9}$ are averaged.
- Validations: ≥ 10 points, velocity range ≥ 1 mm/s.

These files are **not folded** (they already come folded); they are loaded directly
onto the velocity axis.

---

## Normos sidecars

When there are Normos sidecar files next to the spectrum, Fitbauer reads them to
inherit parameters:

| Sidecar | Function | What it extracts |
|---|---|---|
| `.RES` | `read_normos_folding_point`, `read_normos_sidecar_params` | Final folding point; final values WID/ARE/ISO/QUA/BHF |
| `.PLT` | `read_normos_plt_velocity` | $V_{\max}$ of the axis |
| `.JOB` | `read_normos_sidecar_params` | Fixed VMAX and QUA(1) |

The final Normos values are translated into internal parameters
(`s1_delta`, `s1_bhf`, `s1_quad`, `s1_gamma1`, `s1_depth`) as a starting point.

---

## Flow summary

```text
counts (N canales)
   ↓ find_best_integer_or_half_center  →  center (subcanal)
   ↓ fold_integer_or_half              →  N/2 puntos doblados
   ↓ fold_and_normalize (edge_trim)    →  (folded, sigma, y, norm)
   ↓ velocity_axis (mismo recorte)     →  eje de velocidad -vmax..vmax
espectro listo para ajuste
```
