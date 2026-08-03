# Final verdict: Fitbauer versus NORMOS

*English version of `VEREDICTO.md`. The Spanish file is the original; this one
is kept in step with it.*

**2026-08-01 (updated after v4.19.0).** Synthesis of the FOUR rounds of the
round-trip validation bank (NORMOS-SITE/DIST generates → Fitbauer fits →
comparison against the truth): phase 1 (original plan, §1–§15 of the REPORT),
2nd extension with the manual (series K/L, §16) and 3rd round of **extremes and
centre over the original series** (`series_ext.py`: doublets with δ=−1/+2 and
ΔEQ from 0.08 to 5 mm/s, sextets from 0.5 to 58 T, Γ from 0.16 to 2.0, depths
from 0.5 to 40 %, D21 from 0.3 to 3, inverted width pairs, nearly degenerate
doublets, Gaussian P(B) at the grid edges and near-delta, negative and strong
δ(B) correlation), plus the validation of the v4.19 capabilities
(`valida_v4_19.py`: single crystal, Hamiltonian kernel and v³/v⁴ backgrounds,
§18 of the REPORT).

**Totals**: 411 synthetic NORMOS spectra, ~1,150 Fitbauer fits, 6,497
comparison rows (`resumen.csv`), 19 figures. The numbers in this document come
from `veredicto_datos.py`.

---

## 1. What COMES OUT: where Fitbauer reproduces NORMOS

Median and 95th percentile of |fitted − true| over the v0 fits (noise-free;
with the v4.18 extensions where they apply). Units: mm/s (positions, widths),
T (BHF).

| Block (cases) | position | BHF | width | comment |
|---|---|---|---|---|
| **First-order core** (101) | 2·10⁻⁷ / 1.5·10⁻⁵ | 4·10⁻⁵ / 1.1·10⁻⁴ | 8·10⁻⁷ / 1.2·10⁻⁴ | **exact**, including all the new extremes |
| **Full Hamiltonian** (96) | 6·10⁻⁵ / 4·10⁻³ | 8·10⁻⁴ / 0.056 | 5·10⁻⁴ / 0.02 | after v4.18; the remaining tail is SITE-1994's own approximation (§16.3-1) and the sign degeneracy at η=1 |
| **Texture and intensities** (19) | 2·10⁻⁷ / 2·10⁻³ | 2·10⁻³ / 0.034 | 2·10⁻⁵ / 0.014 | D23 from 0 to 4, D21 from 0.3 to 3, D13 from 1.5 to 4.5 |
| **Free lines / widths** (20) | exact | — | exact | W13/W23 from 0.6 to 2.5 and inverted; C3_out_of_range solved by `wide_delta` |
| **Multi-site and constraints** (39) | 2·10⁻⁴ | 2·10⁻⁴ | 2·10⁻⁴ | up to 10 sites; the tail is physical degeneracies (D6, §2b) |
| **Acquisition** (21) | 2·10⁻⁷ | 6·10⁻⁵ | 3·10⁻⁵ | 128–1024 channels, vmax 2–15, non-flat baselines |
| **Thickness / transmission** (14) | 2·10⁻⁵ | 3·10⁻⁴ | 4·10⁻³ | τ from 0.1 to 50; Γ with a p95 bias of 7·10⁻³ from the Γ↔source degeneracy (source fixed) |
| **Octets and backgrounds** (14) | 2·10⁻⁷ | 6·10⁻⁵ | 3·10⁻⁵ | NLINE=8 as sextet+2 singlets; backgrounds BKG(2)…BKG(5) exact with slope/curv/curv3/curv4 (v4.19) |
| **Single crystal** (7, v4.19) | 0.04 / 0.22 | 0.38 / 0.71 | 0.014 / 0.024 | `hamiltonian_sc` with true BEX/GAX and FIXED intensities: χ²red 2.3–3.4; the remaining deviation is SITE-1994's approximation (identical to the powder case) |
| **Native SITE constraints** (2) | ≤1.4·10⁻³ | 0.02–0.03 | ≤5·10⁻³ | both engines (NDEX and constraints) recover the same truth over the same noisy spectrum |
| **K5 extremes** (12) | exact | ≤9·10⁻³ | ≤7·10⁻⁴ | ΔEQ=5, B=1 and 60 T, δ out of range, sub-natural Γ, 40 % |

Distributions (moments of P; median |Δ⟨x⟩| / |Δσ|, v0+v1):

| Group | ⟨x⟩ | σ | comment |
|---|---|---|---|
| J1 Gaussians (interior grid) | 0.02 T | 0.15 T | Hesse-Rübartsch histogram + L-curve |
| J2 bimodal | 0.03 T | 0.03 T | peaks at ±0.5 T (grid resolution) with VBF N=2 |
| J3 P(ΔEQ) (SITE and DIST METHOD=6) | 0.002 | 0.007 | |
| J4 δ(B) correlation, DTI −0.01…+0.02 | 0.04 T | 0.20 T | sign and magnitude correct; ignoring it doubles the error |
| L1 binomial (parametric shape) | — | — | **p recovered to ±0.026 over CONC=10…90 %** |
| L2 Czjzek | 0.004 | 0.015 | the histogram reproduces the shape without needing it analytically |
| L3 PNEG | 0.01 | 0.02 | analytically folded truth (the negative part is unobservable) |
| L6 D23 texture (with `--d23`) | 0.004 | 0.21 | fixed in this phase |
| L4 EXACT (HC kernel, v4.19) | 0.04–0.20 | 0.34–1.0 | kernel by exact diagonalisation; the residual (growing with QUP) is the perturbative truncation of the demo's own EXACT |

The statistical quality holds up too: median χ²red 0.976 in v1, pulls
64/92/96 % within 1σ/2σ/3σ, and the H3 coverage (50 replicas × 3 cases)
consistent with the reported σ. Robustness: 0/20 start failures in the hard
case D2 (previously 8/20).

**In short: across the whole domain both programs share, Fitbauer reproduces
NORMOS at the level of 10⁻⁴–10⁻³ mm/s — far below any experimental uncertainty
— including the extreme values of every parameter.**

## 2. What does NOT come out

### 2a. NORMOS capabilities Fitbauer was missing

**v4.19 update (§18 of the REPORT): items 1, 3 and 4 were CLOSED** — single
crystal (`hamiltonian_sc`), v³/v⁴ background (`curv3`/`curv4`) and mixed order
in distributions (`kernel_treatment="hamiltonian"`). Only the polarized source
(2) remained open.

1. **Single crystal / oriented sample** (SITE `IFSC` + `BEX/GAX`;
   `fig_K3_cristal_unico`). ✅ CLOSED in v4.19: new `hamiltonian_sc` treatment
   (γ beam along a fixed bex/gax direction, coherent sum across channels);
   χ²red of the K3 bank: 3.5–20 → 2.3–3.4 with fixed intensities (the rest =
   SITE-1994 approximation). Convention: GAX_demo = gax − 90°.
2. **Polarized source** (DIST `METHOD=4`/`POLAR`). ✅ CLOSED (2026-08-02, with
   the source code): implemented from first principles (36-line comb by
   helicity selection) and validated against the binary to 0.4 %/1.1 % of the
   peak (θ_s=0/90); bank round-trip (L7) with ⟨B⟩ to 0.08 T. In the GUI
   (distribution panel), the CLI and the kernel. **All four capabilities are
   now closed.**
3. **High-order polynomial background**: ✅ CLOSED in v4.19 (`curv3`/`curv4`):
   the cubic goes from χ²red 2.5 to exact and the quartic (BKG(5)) is recovered
   to 3 figures (`fig_v419_mejoras`).
4. **Mixed-order corrections in distributions** (DIST `EXACT`): ✅ CLOSED in
   v4.19 (`kernel_treatment="hamiltonian"`): kernel by exact diagonalisation
   with powder averaging in the field frame; σ at QUP=1 goes from +2.4 to
   +1.0 T and ⟨B⟩ comes out exact — the remaining residual is the perturbative
   truncation of the demo's own EXACT (`fig_v419_mejoras`).
5. **Isotopes other than ⁵⁷Fe** (`ISTYPE`: ¹¹⁹Sn, ¹⁹⁷Au, ¹⁵¹Eu, ¹²¹Sb, generic
   3/2–1/2): out of scope by explicit decision (the demo does not accept them
   either).
6. **Neighbour asymmetry** (DIST `METHOD=2/3`, Billard–Chamberod with
   CONC/PROB/S2): not tested (no direct counterpart in Fitbauer; it can be
   approximated with multi-site or the 2D mode, but has not been validated).
7. **Methods with external simulation files** (DIST `METHOD=5/7`, TAPE4): they
   require the SIMDATA program, which we do not have; not comparable.

### 2b. Shared limits (not Fitbauer failures)

- **Physical degeneracies**, identical in both programs: sign of ΔEQ in
  doublets; branch (quad, int2) ↔ (−quad, 1/int2); nearly degenerate doublets
  (D6 dΔEQ=0.02: equivalent solutions with perfect χ²); Γ↔source width
  (Lorentzian⊗Lorentzian); PNEG (the negative mirror of P(ΔEQ) is spectrally
  unobservable — demonstrated: the PNEG=0.2 and 0.5 spectra are identical);
  sign of the EFG at η=1 (axis permutation).
- **Histogram regularization**: with near-delta distributions (σ ≈ grid step)
  or ones pressed against the edge, the histogram over-smooths (J1_b30_s0.8:
  σ 1.7 vs 1.25 in v0; L1 CONC=10/90 %). This is the Hesse-Rübartsch
  bias-variance trade-off — the original DIST does the same with LAMDA — and
  the parametric shapes (Gaussian/VBF/binomial) resolve it.
- **Detection limit**: a doublet at 0.5 % of the area with 10⁶ counts is
  unrecoverable under noise (χ²red 0.83 with wandering parameters); the
  measured practical threshold is around 1–2 % (D3).
- **The SITE-1994 approximation in the full Hamiltonian**: at strong mixing
  SITE loses accuracy NUMERICALLY in its diagonaliser (general complex EISPACK
  in single precision, eigenvectors not orthonormalised) and violates
  rotational invariance (§13). In the K3 powder case SITE's theory deviates
  6·10⁻³ (20 % of the peak) from the exact Hamiltonian: there, "not matching"
  the NORMOS-truth means **Fitbauer is more accurate than the reference**.

### 2c. Not validatable with the demo (1994 binary limitations, not verdicts)

~~Pseudo-Voigt profile~~ (RESOLVED 2026-08-02: the binary uses `STG(n)` as the
Gaussian σ — the same convention as Fitbauer — and was VALIDATED round-trip,
series V; report §19-20), δ distribution (`STI` merely cosmetic in field
distributions, confirmed in the source), arbitrary fixed profile (`DEPSUB` does
not exist in the namelist), Goldanskii–Karyagin (`IFGK` has no effect), `S2T`
(does not exist), quantitative relaxation (`OME` not monotonic), `DTQ` in
METHOD=1, more than 512 channels, NSUB>10 and isotopes (`ISTYPE` rejected). All
of it is in the full NORMOS manual, but this demo does not run it: it falls
outside the verdict.

## 3. What Fitbauer has and NORMOS does not

**Physics and model**

- **Exact full static Hamiltonian** (intensities from eigenvectors, rotational
  invariance verified): more accurate than SITE-1994's HAMILT.
- **Real Voigt profile** in working order (the demo's pseudo-Voigt does not
  work; the one in full NORMOS is David's approximation).
- **Quantitative relaxation**: Blume–Tjon with the frequency in Hz (SITE's
  IRELAX/SRELAX is qualitative and in the demo its OME is not even monotonic)
  and a Néel superparamagnetic model with a size distribution.
- **Distributions**: TV and maximum-entropy regularizers with an analytical
  gradient, automatic α selection by L-curve, multi-Gaussian VBF shape
  (Rancourt–Ping), parametric binomial shape, **2D distribution
  P(BHF, ΔEQ)**, and ΔEQ(H) correlation as well as δ(H) (the demo's DTQ is
  dead). Simultaneous sharp components without DIST's limit of 5.
- `wide_delta`: free lines across the whole velocity range.
- **Exact single crystal** (v4.19): coherent sum across radiation channels —
  the interference SITE-1994 approximates — and a **distribution kernel by
  exact diagonalisation** (v4.19), without the perturbative truncation (or the
  fixed 3:3:1 pattern) of DIST's EXACT.

**Statistics and inference**

- Errors by **bootstrap** and by **profile likelihood**, on top of the
  covariance (NORMOS: covariance 1·STD only).
- Correct Poisson weights, robust losses, χ²/AIC/BIC for model comparison, and
  **multi-start + automatic global escalation by differential evolution** (the
  reason for 0/20 versus 8/20 on hard starts).

**Software**

- A modern Qt GUI with reproducible sessions (JSON), a minimum editor, physical
  presets and reports; batch fitting with warm start; a headless layer and CLIs
  for automation; 8 languages; ES/EN manuals; a full test suite and CI. NORMOS
  is a 1994 DOS binary with JOB input via stdin and 8.3 filenames.
- Calibration anchored to the published α-Fe pattern (SITE derives it from
  nuclear moments: measured factor 0.99962 — a documented convention
  difference).

## 4. Conclusion

Taking NORMOS as ground truth, **Fitbauer reproduces the entire shared
domain** — the discrete core at the level of 10⁻⁴–10⁻³ mm/s even at the
extremes of every parameter, the full Hamiltonian better than SITE itself, and
the distributions (Gaussian, bimodal, quadrupolar, Czjzek, binomial,
correlated) with moments to ~10⁻² relative. What it was missing to "reach
NORMOS" was reduced to four concrete capabilities, **all four of which are now
closed** (single crystal, v³/v⁴ background and mixed order in v4.19 §18;
polarized source with the source code, §19-20); only the deliberately excluded
isotopes remain. In the other direction, Fitbauer contributes a whole block of
statistical inference, modern regularization, quantitative relaxation and
automation that NORMOS never had.
