# Automatic Peak Detection in Mössbauer Spectra

Module: `gui/minima_analysis.py` · Class: `MinimaAnalysisMixin`  
GUI action: **Fit → Initialize from minima**

---

## Motivation

Before fitting, the user needs a reasonable starting point for the parameters of each
component. Automatic peak detection locates the absorption peaks in the spectrum
(transmission minima) and converts them into initial parameters for sextets, doublets
and singlets. The algorithm combines multi-scale CWT detection and a direct channel
to be robust against:

- sextets with overlapping lines or variable linewidths;
- narrow doublets that large-scale CWT might merge into a single peak;
- spectra with high noise or a sloped baseline.

---

## Step 1: absorption and baseline

The net absorption is computed as:

$$A(v) = \max\!\bigl(b(v) - y(v),\; 0\bigr)$$

where $b(v) = b_0 + s_0 v$ is a linear baseline estimated over the top 70 % of the
data (by least squares). If fewer than 4 points fall in that upper region, the 90th
percentile is used as a constant reference.

---

## Step 2: noise thresholds

$A(v)$ is smoothed with a coarse moving average (window ≈ $N/80$ channels) and the
noise is estimated using the MAD (median absolute deviation) of the differences:

$$\sigma_n = 1.4826 \cdot \mathrm{median}|D_A - \mathrm{median}(D_A)|, \quad D_A = \Delta A$$

The thresholds are:

$$h_{\min} = \max(f_h \cdot A_{\max},\; 4\sigma_n,\; 5\times10^{-4})$$
$$p_{\min} = \max(f_p \cdot A_{\max},\; 2.5\sigma_n,\; 3\times10^{-4})$$
$$d_{\min} = \max(\delta_{\min},\; 2\Delta v)$$

with factors $f_h$, $f_p$, and minimum separation $\delta_{\min}$ configurable in
`core/param_overrides.py` (table `_PD`).

---

## Step 3: multi-scale CWT detection (Ricker wavelet)

The continuous wavelet transform (CWT) with the Ricker (Mexican hat) wavelet:

$$\psi(x, a) = A\!\left(1 - \frac{x^2}{a^2}\right)\exp\!\left(-\frac{x^2}{2a^2}\right), \quad A = \frac{2}{\sqrt{3a}\,\pi^{1/4}}$$

is applied to $A(v)$ for scales $a \in [a_{\min}, a_{\max}]$ (in channels), where
the physical Mössbauer range of linewidths (0.12–2.0 mm/s) determines:

$$a_{\min} = \max\!\left(2,\;\left\lfloor\frac{0.12}{\Delta v}\right\rfloor\right), \qquad
a_{\max} = \max\!\left(a_{\min}+3,\;\left\lfloor\frac{2.0}{\Delta v}\right\rfloor\right)$$

**Implementation with `np.convolve`** (replaces `scipy.signal.cwt` removed in SciPy 1.12):
the kernel is convolved with the signal in `"same"` mode. To prevent the kernel from
exceeding the signal length (which would cause a `ValueError` due to the `mode="same"`
semantics with short signals), the kernel half-length is clamped:

$$\mathrm{half} = \min\!\left(\max(5a, 3),\; \frac{N-1}{2}\right)$$

The **CWT ridge** is the maximum across scales at each channel:

$$R(v_i) = \max_{a}\!\left[\max\!\left(\mathrm{CWT}(v_i, a),\; 0\right)\right]$$

Peaks in $R(v_i)$ (CWT channel) are detected with `scipy.signal.find_peaks` using
the thresholds $h_{\min}$, $p_{\min}$ and $d_{\min}$.

---

## Step 4: direct channel (fine smoothing)

To recover narrow doublets that large-scale CWT might merge into a single peak,
peaks are also searched in the absorption with fine smoothing (window ~0.15 mm/s,
always odd). The smoothed absorption is renormalized to the range of $A_{\max}$
before searching for peaks with the same thresholds.

---

## Step 5: candidate merging

The CWT indices ($I_\mathrm{CWT}$) and direct indices ($I_\mathrm{dir}$) are merged
by removing duplicates and artifacts:

1. Direct peaks form the base list (they avoid the "valley peak" artifact that
   large-scale CWT can generate between the two lines of a doublet).
2. A CWT peak is added only if it is **not** between two consecutive direct peaks
   (sign of a valley artifact) and is not a duplicate of one already present (distance ≤ 1 channel).

---

## Step 6: FWHM width estimation

For each merged peak:

- If there is a positive CWT response, the **scale with the highest response** determines
  the width: $\Gamma \approx 2 \cdot a_\mathrm{best} \cdot \Delta v$.
- If there is no positive CWT response, the FWHM is estimated directly from the
  fine-smoothed signal: the 50 % crossings of the peak value are located to the left and right.

---

## Step 7: final selection and ordering

Peaks are sorted by smoothed depth (descending) and selected greedily, adding a peak
only if it is more than $d_{\min}$ away from all already-selected peaks. At most 15
peaks are retained.

---

## Step 8: classification and component initialization

Once the minima are detected, the initialization logic (`on_init_from_minima`)
assigns components:

1. **Shape heuristic** (`_depth_profile_hint`): if one peak dominates in depth
   with position < 2.5 mm/s → Singlet; if two peaks are comparable and the separation
   falls in the doublet range → Doublet.
2. **Sextet search** (`_best_sextet_from_peaks`): linear fit
   $v_j = \delta + (B_{hf}/B_0) \cdot r_j^{(33)}$ by least squares over
   combinations of 5–6 peaks; accepted if RMS < threshold and BHF is physical.
3. **Estimation with 2 visible peaks** (`_try_2peak_sextet_estimate`): if only
   2 peaks are present, BHF is estimated from the outer spacing (lines 1–2 or 5–6).
4. **Remaining components**: unassigned peaks form doublets (if the separation
   is in the physical range) or additional singlets.

Initial depths are rescaled so that the proposed model does not exceed the maximum
absorption of the data.

---

## Implementation notes

- The CWT replaces `scipy.signal.cwt + ricker` (removed in SciPy 1.12).
- Kernel clamping (`half = min(max(5a,3), (N-1)//2)`) corrects the
  `ValueError: could not broadcast input array` that occurred with short signals
  (~254 points after edge trimming from folding).
- Detection parameters (thresholds, ranges, tolerances) are configurable
  in `core/param_overrides.py` via `_PD` (peak detection) and `_FI` (fit init).
