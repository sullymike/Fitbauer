# Validation report: Fitbauer against NORMOS-SITE

*English version of `INFORME.md`. The Spanish file is the original; this one is
kept in step with it.*

**Autonomous agent session, 2026-07-31; 2nd extension (series K/L, NORMOS
manual) and 3rd round (extremes over the original series) on 2026-08-01 — see
§16–§17 and the final verdict in `VERDICT_EN.md`.** Reference plan:
`validacion/plan_validacion_fitbauer_normos.md`. All the data, scripts and
figures cited live under `validacion/`.

---

## 1. Executive summary

A round-trip bank was built: **NORMOS-SITE simulates → Fitbauer fits →
comparison against the truth**. **327 base spectra** (SITE.EXE, DIST.EXE for
block J and 4 derived by exact binning), plus **285 v1 replicas with Poisson
noise**, **150 coverage replicas (H3)**, 32 statistics-sweep fits (H1) and the
adversarial blocks (I). In total **411 spectra and ~1,150 fits** (phase 1 +
series K/L of the 2nd extension §16 + extremes of the 3rd round §17 + v4.19
validation §18) with perturbed starting values and a recorded seed (6,497
comparison rows in `resumen.csv`).

**Overall verdict**: Fitbauer's discrete core (singlet / doublet / first-order
sextet, per-pair widths, texture, multi-site, constraints, folding and axes)
**reproduces NORMOS within 10⁻⁴–10⁻³ mm/s and ≲2·10⁻³ T**, far below any
experimental uncertainty. The reported σ are statistically correct (median
χ²red 0.976; global pull 64/92/96 % within 1σ/2σ/3σ). The disagreements that
remain are **localised, understood and documented** (§6): full-Hamiltonian
intensities, η unsupported, transmission integral, curved baseline, start
robustness in multi-component fits, and several genuine physical degeneracies
that no program can break.

| Block | Result |
|---|---|
| A1–A3 (singlets, doublets, first-order sextets) | ✅ exact (≤2·10⁻⁴) |
| A4/A6 (axial full Hamiltonian) | ⚠️ positions OK up to θ≲55°; intensities not modelled (§6.1) |
| A5 (non-axial EFG, η≠0) | ❌ unsupported — capability gap (§6.2) |
| A7 (free lines) | ✅ within δ∈[−2,3]; limit documented (§6.5) |
| B (texture/intensities) | ✅ (doublet branch degeneracy documented, §6.7) |
| C (widths) | ✅ ; Γ≈1 channel requires DE or a good start (§6.4) |
| D (multi-site, constraints) | ✅ up to 10 sites (the headless core exceeds the GUI's limit of 6!); D6 degeneracies (§6.7) |
| E (acquisition) | ✅ ; channel-integration and curved-baseline bias quantified (§6.6, §6.8) |
| F (thickness) | ⚠️ exponential saturation ≈ correct up to t≈10; no thickness broadening (§6.3) |
| G (isotopes) | ⛔ not executable: the SITE demo does not accept other isotopes |
| H (statistics) | ✅ σ ∝ 1/√counts; coverage ≈ nominal (slight underestimation, §7) |
| I (adversarial) | ✅ except as expected (t_a≥30 with the thin model; 0.2 % signal on a 10⁵ baseline) |
| J (distributions, DIST) | ✅ ⟨B⟩ to ≤0.1 T, bimodal peaks to ½ bin, P(ΔEQ) and δ(B) correlation validated; regularization broadening of +0.2 T quantified (§8) |

> **v4.18.0 update (§13)**: the model biases of §6.1 (HC intensities), §6.2
> (η/φ), §6.3 (transmission), §6.6 (channel) and §6.8 (curved baseline) were
> **eliminated** with four opt-in extensions to `core/` (medians ×7–×285
> smaller, `v0m` rows in the summary). Along the way it was shown that
> NORMOS-SITE 1994 is not exact at strong mixing (it violates rotational
> invariance): Fitbauer's new implementation beats it there.

---

## 2. Environment and methodology

- **NORMOS-SITE**: `SITE.EXE` v. 27.01.1994 (WissEl GmbH, *Demonstration
  version*), without a manual; `DIST.EXE` (09.09.1993) arrived with block J.
  Run under dosbox-staging 0.82.2 with the validated recipe in
  `docs/normos_dosbox_guide.md`: JOB via stdin (`SITE < X.JOB`),
  `REMOTE=.TRUE.`, real display `:0`, batches of up to 45 cases per launch
  (~0.6 s per batch). The Fortran namelist requires lines ≤ ~72 columns and
  CRLF.
- **Fitbauer**: headless layer `core.session.HeadlessSession`, engine
  `core.fit_engine` (TRF with bounds, multi-start, optional DE), repository
  commit at the time of the session (branch `main`, v4.17.3).
- **Round trip per case**: SITE simulates with every parameter fixed (verified:
  `SIMULT=.TRUE.` ≡ a fit with 0 free variables, bit for bit) → theoretical
  curve from the *fit* block of the `.PLT` (256 points, axis
  `linspace(−VMAX,+VMAX)`, identical to Fitbauer's) → **unfolded** 512-channel
  spectrum by exact mirroring about 256.5 (channel 1 at +vmax, triangular
  drive) → Fitbauer detects the centre by symmetry, folds and fits from
  starting values **perturbed by ±15 %** (CRC32 seed of the case).
- **v1**: Poisson noise with a recorded seed over the same theory (10⁶ baseline
  except in the H sweeps); the channel averaging of the folding and Fitbauer's
  σ (`sqrt(folded/2)/norm`) match by construction.
- **Prior checks** (step 0-bis): SITE determinism (two runs → identical
  output), trivial singlet against an analytical Lorentzian (residual
  < 2·10⁻⁵), flat dummy with a symmetric valley so that SITE's folding-point
  search returns exactly 256.5.
- **Fit escalation** (mimicking a user faced with a bad fit): if the
  local+multistart fit ends with χ²red>2 it is retried with a global DE
  pre-pass, and if that persists, with a fine ±5 % start. Only 6 and 8 of 318
  cases needed it (overlapped multi-site); the escalation is recorded in
  `resumen.csv`.

## 3. Conventions deciphered (step 0.6 + probes on the binary)

| Quantity | SITE | Fitbauer | Conversion |
|---|---|---|---|
| Position | `ISO` | `s_delta` | identical (both versus the source zero) |
| Width | `WID` = **FWHM** of the inner lines (3,4) | `gamma1` = FWHM of the outer lines (1,6) | `gamma1 = WID·W13` |
| Per-pair widths | `W13`, `W23` = ratios 1,6/3,4 and 2,5/3,4 | `gamma2`, `gamma3` = ratios relative to 1,6 | `gamma2 = W23/W13`, `gamma3 = 1/W13` |
| Sextet quadrupole | `QUA` (shifts ±QUA/2; lines 1,6 → +) | `quad` | **identical, sign included** |
| Doublet quadrupole | `QUA` | `quad` | opposite sign and **degenerate** in symmetric doublets → \|ΔEQ\| is compared |
| Hyperfine field | `BHF` (positions from nuclear moments) | `bhf` (published α-Fe pattern, 33 T ↔ ±5.329 mm/s) | `bhf = BHF·k`, **k = 0.99962** (measured at 33 and 51.7 T; a convention difference, cf. Fitbauer CHANGELOG v4.0.2/v4.0.3, not an error) |
| Intensities | `D13`,`D23` (sextet), `D21` (doublet) = **area** ratios; `D21` = high-v line / low-v line | `int1`,`int2` = **height** weights | `int = D/W` of the corresponding pair |
| Amplitude | `DEP` = **integrated area** of the subspectrum (mm/s) — verified ∫(1−T)dv = DEP | `depth` = fractional peak depth | `depth = DEP/(π/2·Σ w_i·Γ_i)` |
| Full Hamiltonian | `HAMILT=.TRUE.` (in `&PARAM`, not in `&DATA`!) + `THE/ETA/PHI` (degrees) | `quad_treatment="kundig_fixed"` + `beta` (degrees) | θ=0 ≡ first order in both (verified to 5·10⁻⁵) |
| Transmission | `IFTRAN=.TRUE.` (in `&PARAM`) + `TAB` (effective thickness) + `WDS=0.097` (source, implicit) | `absorber_model="thickness"` + `sat_scale` | different models, see §6.3 |

## 4. Capability inventory

**SITE demo 27.01.1994** (probes in `paso0/sonda*`): NSUB ≤ 10 (12/14 fail
without a message); **512-channel raw spectra only** (the WS5 reader requires
≥512 numbers and the folding accepts NP ≤ 256; 1024 raw channels are read but
exceed NP); `HAMILT/THE/ETA/PHI` ✔; `IFTRAN`+`TAB` ✔; `W13/W23/D21` ✔;
relaxation `SRELAX`/`IRELAX`+`OME`+`BH0` ✔ (in `&PARAM`); `QMR` ✔; **not
available**: isotopes other than ⁵⁷Fe (`EGAMMA`/`GAMMA`/`GFACT` rejected in
both namelists → block G dropped), `VOIGT` accepted with no observable effect,
`NLINK` constraints with no syntax decipherable without the manual (D5
validates instead Fitbauer's constraint engine over spectra generated
respecting the constraint).

**DIST.EXE** (NORMOS-Dist 09.09.1993, added afterwards — block J, probes in
`_staging/sondaJ*`): distribution blocks over a grid that is **always in BHF**
(`NDSS`, `NSB(k)` points from `BHF(k)` with step `DTB(k)`, default 1 T);
`DISTRI=2` = Gaussian with centre `AVG(k)` and width `STG(k)` (compensated by
the step); `DTI(k)` = ISO increment per point → linear δ(B) correlation ✔
(equivalent to Fitbauer's `delta_slope` with DTB=1); **`DTQ` accepted but
inoperative** (probe K1: zero effect → a pure P(ΔEQ) cannot be generated with
this demo; J3 was generated with SITE: 10 doublets of Gaussian areas);
`SIMULT=.TRUE.` simulates (arbitrary amplitude; the model is linear in P → it
is scaled exactly in Python); the true P(B) per block is read from the "Table
of relative areas" of the `.RES` (each block normalised to 100 → blocks of
equal areas); crystalline sites `*X` available; `MAXENT`/`LAMBDA` (DIST's own
regularization) not exercised (DIST only generates here).

**Fitbauer**: up to 6 components in the GUI — but **the headless core fitted 8
and 10 components without trouble** (D1_n08/n10, χ²red 0.004);
singlet/doublet/sextet; fixed axial Kündig (η=0) and powder; Lorentz/Voigt;
constraints `target=factor·source+offset`; thickness by exponential
saturation; phenomenological/Blume-Tjon/Néel relaxation; ⁵⁷Fe only; δ bounded
to [−2,+3] mm/s.

## 5. v0 results — successes (brief mention; plan criterion §4: <10⁻³ mm/s, <0.05 T, <0.5 % areas)

| Series | Cases | max deviation observed |
|---|---|---|
| S0 conventions | 4 | 6.8·10⁻⁵ |
| A1a/A1b/A1c singlets | 21 | 2.7·10⁻⁵ mm/s |
| A2 doublets (45-point grid) | 45 | 7.1·10⁻⁶ mm/s |
| A3a/b/c sextets (2–55 T) | 24 | 1.7·10⁻⁴ T |
| A7 free lines (1–8 lines) | 5 | 1.9·10⁻⁵ mm/s |
| B1 texture (D23 0–4) | 10 | 3.6·10⁻³ in int2 (tol 0.04) |
| B2 asymmetric doublets | 5 | criterion met (degenerate branch recognised) |
| C1/C2 common and per-pair widths | 7 | 1.7·10⁻³ mm/s in width |
| C3 6 free lines | 3 | exact (χ²red ≈ 10⁻⁴) |
| D2 2 overlapping sextets (ΔB 0.5–8 T) | 6 | 2.5·10⁻³ T |
| D3 minority phase 1–20 % | 6 | area recovered down to the bank floor (§6.9) |
| D5 constraints (common Γ, 2:1 areas, δ, ΔEQ, combined) | 6 | 7.8·10⁻⁴ |
| D1 multi-site 2–10 sites | 7 | ≤7·10⁻³ except for degeneracies (§6.7) |
| E2 ranges ±2–±15 mm/s | 6 | 1.8·10⁻⁴ |
| E4 unfolded ≡ directly folded | 2×2 | 6·10⁻⁵ |
| E5 lines cut off by the edge | 3 | 4.4·10⁻³ T (it recovers a 55 T sextet with lines 1,6 outside the range!) |
| I2 huge Γ (1.5/3.0) · I4 detection limit (v0) · I5 boundaries | 5 | 7·10⁻⁴ |

Escalation (DE or a fine start) was needed in only 14 of 318 cases, all of them
multi-site with strong overlap; it is recorded row by row in `resumen.csv`.

---

## 6. Failures and limitations — detailed documentation

**Note — model bias versus convergence**: the biases of §6.1, §6.3, §6.6 and
§6.8 were verified by re-fitting from an EXACT start at the truth (zero
perturbation, no multistart): the optimiser moves away from the truth and lands
on the same biased value (agreement to the 3rd–4th figure: e.g. A4_R2_th90
Bhf −0.094 T, F3_t10 Γ +0.092, E3 Γ +0.034, E1_128 Γ +0.091). The true value is
not the χ² minimum of Fitbauer's model: these are systematic biases that
neither the start nor the statistics can cure, only extending the model. C4 and
the multi-site case of §6.10, by contrast, are cured by a good start (bias
<4·10⁻⁴): there the model is capable and the problem was finding the minimum.

### 6.1 Axial full Hamiltonian: SITE recomputes intensities; Fitbauer only positions

**Data**: series A4 (30 R×θ cases), A6 (10 contrast pairs), D4_sextHC.
**Figures**: `figuras/fig_A4_mapa_sesgos.*`, `fig_A4_ejemplo_R2_th90.*`,
`fig_A6_validez_1er_orden.*`.

With `HAMILT=.TRUE.`, SITE diagonalises the magnetic+quadrupole Hamiltonian and
**recomputes the transition intensities from the eigenvectors** (including the
ΔmI=±2 transitions activated by mixing). Fitbauer's Kündig (`kundig_fixed`)
diagonalises the **positions** the same way (θ=0 agrees with SITE to 5·10⁻⁵)
but keeps whatever intensities the user sets.

Measured consequence (fitting with free intensities):
- θ ≤ 30° and R ≤ 1: |ΔBhf| ≤ 0.022 T, |ΔΓ| ≤ 0.014 — **usable**.
- θ = 54.7°: positions still good (|ΔBhf| ≤ 0.002 T) but the fitted int2
  deviates to 1.5 from the nominal 2.0 (it absorbs the intensity physics).
- θ ≥ 75° or R ≥ 2: |ΔBhf| up to 0.17 T, |ΔΓ| up to 0.058, int1→1, int2→0: the
  8-line pattern is no longer representable with 6 lines of fixed weights
  (structured residuals in the example figure).
- A6 (validity map, θ=30°): **first order with an effective QUA** reproduces
  SITE-first-order over the whole range (|ΔBhf| ≤ 7·10⁻⁴ T), and the Kündig fit
  of HC spectra crosses the 0.05 T criterion at **R ≈ 0.35**.

**Cause**: a documented model difference (intensities not depending on mixing
in Fitbauer). **Roadmap**: compute the transition matrix elements from the
eigenvectors of `core/hamiltonian.py` (the eigenvectors are already computed;
what is missing are the Clebsch-Gordan factors and the 2 forbidden
transitions).

### 6.2 Non-axial EFG (η, φ): unsupported

**Data**: series A5 (45 η×θ×φ cases, R=1). **Figure**: `fig_A5_sesgo_eta.*`.

Fitbauer has neither η nor φ. Fitting with the axial model (R=1): median bias
in Bhf of ~0.09–0.14 T (η=0.2–0.4) growing to ~0.45 T (η=1.0), with maxima of
4.8 T (η=0.2, θ=0, φ=90); in ΔEQ, median 0.02–0.4 mm/s growing with η. δ stays
robust (median < 1.5·10⁻³, max 0.12 mm/s). A pure capability gap; in powder the
effect averages out and would be smaller (not evaluated: the SITE demo does not
average over powder).

### 6.3 Transmission integral (thickness)

**Data**: F1 (t_a 0.1–20), F2, F3, I1. **Figures**:
`fig_F_transmision_gamma.*`, `fig_F_ejemplo_t10.*`.

With `IFTRAN`, SITE computes the transmission integral **including the source
line (WDS = 0.097 mm/s)**: in the thin limit the observed width is
WID+WDS = 0.347, not WID. Against that reference:

- **Fitbauer's thin model** (F3/I1): the fitted Γ grows 0.363 → 0.396 → 0.440 →
  0.60 → 0.80 for t_a = 1, 5, 10, 30, 50: the classic uncorrected thickness
  broadening. δ is **not** biased (< 10⁻⁵ even at t_a=50).
- **Fitbauer's exponential saturation** (`sat_scale`): keeps Γ = 0.354 stable up
  to t_a = 10 (+0.008 over the reference) — it **works remarkably well** in the
  practical range; at t_a = 20 it no longer does (Γ=0.54).

**Cause**: exponential saturation captures the depth saturation but not the
line-shape distortion of the exact integral; sufficient up to t_a≈10. Depth and
area were not compared (non-equivalent parametrisations; `DEP` stops being the
area under IFTRAN — the `.RES` reports the real area).

### 6.4 Γ comparable to the channel width: narrow convergence basin

**Data**: C4 (Γ = 0.078 and 0.156 = 1× and 2× the channel). **Figure**:
`fig_C4_lineas_estrechas.*`.

From an exact start Fitbauer recovers Γ=1 channel with |ΔBhf| < 4·10⁻⁴ T (there
is no model discretisation bias). But from a ±15 % start: χ² has hardly any
gradient when the model lines do not overlap the measured ones (basin of width
~Γ), the standard multistart (σ = 12 % of the range) does not land inside, and
the fit collapses (Bhf 33→44.7). **The DE pre-pass solves it** (χ²red 0.013).
Usage recommendation: for lines ≤2 channels, initialise by peak detection or
enable global optimisation.

### 6.5 Free lines: the δ∈[−2,+3] mm/s limit

**Data**: C3_fuera_de_rango (6 singlets at ±5.33/±3.08). Fitbauer's singlets
cannot leave δ∈[−2,3] (`COMPONENT_FIT_BOUNDS`): the fit gets pinned at the
boundary (χ²red 1702). With the same widths at interior positions (C3 at
~11 T) the fit is exact. For "free lines" outside that range Fitbauer has no
suitable component type today (the bounds are correct for physical ⁵⁷Fe δ). A7
with 8 lines (inside the range): exact, using 8 headless components.

### 6.6 Integration over the channel (E1)

**Data**: E1 binned (256 and 128 raw channels derived by exact pairwise
summation of the 512-channel theory; the SITE demo does not generate other
sizes).

Fitbauer (like SITE-1994) evaluates the model at the channel centre; it does
not integrate over its width. With data generated by channel integration: the
fitted Γ is +0.004 (channel = 0.157 mm/s ≈ 0.6Γ) and **+0.023/+0.091**
(sextet/doublet with channel = 0.31 mm/s ≈ 1.3Γ), depth −5 % in the extreme
case. δ/ΔEQ/Bhf are not biased (symmetry). Quantified rule of thumb: keep the
channel ≤ Γ/3, or expect Γ to be overestimated.

### 6.7 Genuine physical degeneracies (no fitter can break them)

- **Symmetric doublet**: the sign of ΔEQ is unobservable (A2/S0) — both
  programs "choose" it arbitrarily.
- **Asymmetric doublet** (B2): (ΔEQ, r) ≡ (−ΔEQ, 1/r) exactly; χ²red ~10⁻⁷ in
  both branches. Documented and acknowledged in the comparison.
- **Nearly degenerate doublets** (D6, ΔΔEQ ≤ 0.3): there is a re-pairing of the
  4 lines with identical χ² (two "crossed" doublets with ΔEQ ~0.02 and ~2.5);
  the fit falls indistinguishably into one solution or the other and the
  covariance σ do not capture this multimodality (z up to ±800 in v1 despite
  χ²red=1.06). Recommendation: tie ΔEQ or δ when two doublets are known to be
  close.
- **D1_n05/n10**: an unresolved doublet (ΔEQ=0.7, Γ=0.25) + a singlet at
  0.55 mm/s: partial role exchange with almost identical χ² (deviations
  ~0.1-0.35 in δ/ΔEQ of those two components, the other 10 sites exact).

### 6.8 Non-flat baseline (E3)

**Data**: E3 (0.2/0.5/1.5 % parabola and 0.5 % ramp applied to the raw data).
**Figure**: `fig_E3_base_no_plana.*`.

The linear ramp in v is absorbed by `slope` without bias (< 10⁻⁴). The parabola
(a geometry effect that survives folding) has no term in Fitbauer's model:
growing biases up to ΔΓ = 0.034 and Δdepth = −5 % (1.5 % curvature), with δ/Bhf
almost immune (< 3·10⁻³). Roadmap: an optional quadratic term in the baseline
(NORMOS does not fit it either; it corrects it beforehand with BKGCOR).

### 6.9 Precision floor of the bank itself

The quantisation of SITE's `.PLT` (6 decimals) and Fitbauer's P90
normalisation set a floor of ~3·10⁻⁵ in absolute depth and ~10⁻⁴ relative. It
is only visible in D3 with a minority phase ≤ 2 % (minority Γ +0.04 at 1 %) and
in the depths of A1c. This is not a Fitbauer defect: it is the fidelity ceiling
of the generator. **D3 threshold** (figure `fig_D3_minoritaria.*`): with a 10⁶
baseline and Poisson noise, the minority phase area is recovered with a
relative error of ~1.5–2 % for fractions ≥10 %, ~10–25 % at 3–5 %, ~80 % at 2 %
and ~400 % at 1 % (not detected): the practical detection threshold with this
statistics lies between 2 and 3 % of area.

### 6.10 Start robustness in multi-component fits (D2/D4/I3)

With a ±15 % perturbation and local multistart (6–8 replicas), **~40 % failure**
on 2 overlapping sextets (measured with 20 seeds in D2_db8); the 4-site mixture
(D4_suelo, I3) only converges without multistart from ±5 %. The **DE**
(global_opt) pre-pass solved 100 % of the seeds tried (3–14 s per fit). The
final bank needed escalation in only 14/318 cases. Fitbauer usage
recommendation: for overlapped multi-site fits, initialise from peaks/minima or
enable global optimisation; local Gaussian multistart is no substitute for a
good start.

---

## 7. Statistics with noise (v1, H)

**Figures**: `fig_v1_pull_global.*`, `fig_H3_cobertura.*`.

- **χ²red** (v1, 10⁶ baseline, series with an equivalent model): median 0.976,
  p5–p95 = 0.78–1.25 ✅ (criterion 0.8–1.2).
- **Global pull** (1516 parameter·cases): 63.5 % within ±1σ, 91.8 % within ±2σ,
  95.7 % within ±3σ. Clean Gaussian shape; the tails come from the degeneracies
  of §6.7. Fitbauer's σ are **slightly optimistic** (~10 % narrow) —
  consistent with covariance errors without a correlation term between
  overlapping components.
- **H3 (50 replicas × 3 cases)**: doublet A2 64/93 %, sextet A3a 62/92 %,
  mixture D4 53/84 % (1σ/2σ). The underestimation grows with the overlap
  between components: for mixtures, bootstrap (available in Fitbauer) is
  preferable to covariance.
- **H1 (baselines 10⁴–3·10⁶)**: sextet σ(δ) 0.0126 → 0.0034 → 0.0015 →
  0.00087 mm/s: clean 1/√N scaling; stable z.
- **H2 (0.5 % absorption)**: correct recovery with 10⁶ and 10⁵ baselines
  (z ≤ 2).
- **I4 (detection limit, 0.2 % on a 10⁵ baseline)**: v0 exact; with noise the
  fit diverges (signal ≈ 2× noise per channel) — a physical limit, not a
  defect.

## 8. Block J — P(BHF)/P(ΔEQ) distributions against NORMOS-DIST

**Figure**: `figuras/fig_J_distribuciones.*`. 15 distribution spectra (v0+v1
each), fitted with `fit_bhf_distribution_cli.py` (Hesse-Rübartsch histogram +
Tikhonov, α chosen by L-curve `--scan-alpha`, fitting grid different from the
generating one: 5–52 T / 47 bins).

- **J1 (9 Gaussians ⟨B⟩∈{25,30,35} × σ∈{1.5,3,5})**: ⟨B⟩ recovered to ≤0.06 T
  (v0) and ≤0.23 T (v1). σ with the classic regularization bias:
  **+0.17…+0.40 T in v0** and up to +1.5 T for the narrowest (σ=1.5) with
  noise — the L-curve over-smooths narrow distributions; for σ≥3 the relative
  bias is <10 %.
- **J2 (bimodal 28/45 and asymmetric 26/44)**: both peaks located to ±0.5 T
  (half a bin width: grids offset by half a step); global moments to <0.1 T;
  the noisy replica resolves both modes without artefacts.
- **J3 (P(ΔEQ), generated with SITE because of the demo's DTQ limitation)**:
  mean to 10⁻⁴ and σ to 3·10⁻⁴ mm/s in v0; with noise, ≤0.012. Fitbauer's
  distributed-doublet kernel is validated.
- **J4 (δ(B) correlation, DTI 0.005/0.01)**: with the true `--delta-slope` and
  the correct reference δ, the recovery is identical to the uncorrelated case
  (σ +0.16 T) → **Fitbauer's correlated δ(H) kernel is correct**. Ignoring the
  correlation at these slopes barely biases anything (σ +0.20 vs +0.16): with
  Γ=0.30 and slopes ≤0.01 mm/s/T the effect is smaller than the linewidth. A
  methodological caveat: the kernel's δ is held FIXED and must equal the true δ
  at H_ref (the grid mean) — omitting it produces σ overestimated by a factor
  of ~2 (an error made and corrected during the session, §11).
- **J5 (sensitivity to α, 10⁶ baseline)**: the result is insensitive to α over
  0.01–100 (the data dominate); over-smoothing only appears at α≳10⁶ (RMS ×40
  at α=10⁸). The L-curve chose α=0.01.

## 9. Extra series X1 — relaxation (a SITE capability outside the plan)

The SITE demo models relaxation (`IRELAX`+`OME`+`BH0`, Ising). Four spectra
were generated (OME = 0.3–10, units undocumented) and fitted with Fitbauer's
Blume-Tjon: the spectra are in a partial-collapse regime; the fit converges and
recovers δ exactly; the fitted effective Bhf grows with OME (1.0 → 7.1 T),
suggesting that OME ~ the inverse of the relaxation rate. Without a manual
there is no quantitative OME↔ν mapping: a qualitative comparison is archived in
`X1/` for future work.

## 10. Capabilities not covered by Fitbauer (roadmap, not failures)

1. Full-Hamiltonian intensities (and ΔmI=±2 transitions) — §6.1.
2. EFG η and φ — §6.2.
3. Exact transmission integral (saturation covers up to t_a≈10) — §6.3.
4. Quadratic baseline term — §6.8.
5. Integration of the model over the channel — §6.6.
6. "Free lines" outside δ∈[−2,3] — §6.5.
7. >6 components in the GUI (the core already does it) — §4.
8. Isotopes other than ⁵⁷Fe (the SITE demo does not expose them either; no
   reference data).

## 11. Issues within the bank itself (methodological transparency)

Harness failures detected and corrected during the session (none affects the
final results; every affected case was regenerated/refitted): namelist lines
>72 columns; ambiguous NP in the `.PLT` with NSUB∈{3,5,7,9} (mixed blocks → NP
is now passed explicitly); seed with a salted `hash()` (non-deterministic →
CRC32); doublet `int2` held fixed despite requesting free intensities;
`sat_scale` not released in thick mode; direction and branch of the `D21`
mapping; badly scaled tolerance for the γ2/γ3 ratios; effective velocity axis
of the binned spectra (E1); and in block J: reference δ omitted with
`delta_slope` (σ ×2), a first P(ΔEQ) attempt with the demo's inoperative DTQ,
and the distribution CLI requiring the repository venv's numpy≥2 (the system
one lacks `np.trapezoid`). The detail is in the history of `generador/*.py`.

## 12. Reproducibility

```bash
cd /home/jorge/fitbauer
python3 validacion/generador/paso0_verifica_receta.py   # DOSBox recipe
python3 validacion/generador/paso0_sondas.py            # capability probes
python3 validacion/generador/serie_S0_convenciones.py   # step 0.6
python3 validacion/generador/series_AB.py               # blocks A-B
python3 validacion/generador/series_CG.py               # blocks C-F
python3 validacion/generador/fix_E1_E4_refits.py        # E1 binned + E4 512
python3 validacion/generador/series_HI.py               # v1 + H + I + X1
python3 validacion/generador/serie_J.py                 # block J (DIST)
python3 validacion/generador/analisis.py                # v0 criteria
python3 validacion/generador/figuras.py                 # report figures
```

- `resumen.csv`: one row per (case, version, parameter): true, fitted, σ, z,
  χ²red, convergence, time, escalation notes.
- Per case: `SITE.JOB/RES/PLT/MOS`, `teoria_norm.npy`, `v0.dat`, `v1*.dat`,
  `verdad.json`, `fitbauer_*.json`.
- Requirements: `SITE.EXE` in `/home/jorge/normos_work/` and `DIST.EXE` in
  `validacion/` (**WissEl commercial software: never to be committed to the
  repository**, covered by `*.EXE` in `.gitignore`), dosbox-staging with a real
  X display, numpy/scipy/matplotlib.
- Total on disk: ~50 MB. Duration of the full session: ~2 h (dominated by the
  ~800 fits; full SITE generation takes <1 min).

---

## 13. Model improvements implemented as a result of the bank (v4.18.0)

After the validation, the four extensions that eliminate the model biases of §6
were implemented in `core/` (all opt-in; the 310 previous tests pass unchanged
and there are 10 new tests in `tests/test_mejoras_normos.py`). **Figure**:
`figuras/fig_mejoras_antes_despues.*`; `version=v0m` rows in `resumen.csv` (the
same v0 spectra, refitted with the improvement).

| Bias (§) | Improvement | Median \|Δ\| before → after |
|---|---|---|
| §6.1 axial HC (A4) | `quad_treatment="hamiltonian"`: intensities from eigenvectors, 8 lines | Bhf 0.0056 → 0.00024 T (×23); Γ ×7 |
| §6.2 η≠0 (A5) | same + per-component `eta`/`phi` | Bhf 0.306 → 0.0093 T (×33); Γ ×8 |
| §6.1 contrast (A6-HC) | same | Bhf 0.020 → 0.0019 T (×11) |
| §6.6 coarse channel (E1) | `channel_sub` (Gauss-Legendre over the channel) | Γ 0.021 → 0.0016 (×14) |
| §6.8 curved baseline (E3) | global `curv` | Γ 0.0073 → 2.6·10⁻⁵ (×285) |
| §6.3 thickness (F1/F2/I1) | `absorber_model="transmission"` (L_source ⊗ exp(−τ), `src_fwhm`) | Γ 0.105 → 0.0037 (×28) |

Key verification: the biases of §6 were MODEL biases (refitting from an exact
start at the truth, the optimiser returned to the biased value); with the
extensions, the same protocol recovers the truth.

**A finding about the "absolute truth"**: while validating the full Hamiltonian
it was shown that **NORMOS-SITE 27.01.1994 is not exact at strong mixing**: two
configurations that are physically identical by rotation (η=1, B∥y, ΔEQ=+2) ≡
(η=1, θ=0, ΔEQ=−2) produce different spectra in SITE (Δ = 9.6·10⁻³, 40 % of the
peak), whereas Fitbauer's new implementation is rotationally invariant and
agrees with SITE to 3.7·10⁻⁵ exactly in the frame where the ground state is
pure (no interference terms). Conclusion (revised in §19 with the source code):
SITE loses accuracy NUMERICALLY (general complex EISPACK diagonaliser in single
precision, eigenvectors not orthonormalised) in its intensities; the residuals
remaining in the bank at η≥0.8 (χ²red 1.5–6.6 in v0m) measure SITE's error, not
Fitbauer's. At η=1 there is in addition the exact physical degeneracy
(ΔEQ, φ) ↔ (−ΔEQ, 90°−φ), which explains the apparent quad "failures" in the
comparison.

Out of scope (roadmap §10): powder averaging of the full HC with intensities
(the quadrature exists for positions), simultaneous free θ/η/φ fitting
(identifiability unexplored), and isotopes other than ⁵⁷Fe.

---

## 14. Closing the "what it cannot reach" block with the manual (v4.18.0, 2nd phase)

With `validacion/sitedistmanual.odt` (NORMOS Programs, R.A. Brand, 10.7.1990)
available, the rest of the §10 list was closed (except isotopes other than
⁵⁷Fe, by request) and entries in the §4 inventory were corrected:

**Additional Fitbauer improvements**
- **Free lines** (`wide_delta` in `ModelState`, opt-in): widens the δ bounds to
  ±(vmax+2). C3_fuera_de_rango (6 lines at ±5.33/±3.08): χ²red 1702 → 0.0002,
  positions exact to 10⁻⁴ mm/s.
- **Up to 10 components in the GUI**: `MAX_COMPONENTS` = 10 (single source in
  `core/params.py`, imported by the three Qt modules that duplicated the 6).
  The bank had already shown the engine fits 10 sites (D1_n10).

**Corrections to the SITE/DIST inventory thanks to the manual**
- **SITE constraints**: the mechanism is `NDEX(i)=j, FACTOR(i), CONST(i)` →
  `PAR(i) = factor·PAR(j) + const` — formally IDENTICAL to Fitbauer's
  constraint model (`target = factor·source + offset`). (It was not `NLINK`,
  which is the internal counter.)
- **Isotopes**: SITE does support them via `ISTYPE='119SN'` etc. (a character
  parameter; my probes tried numeric keys). Not exercised (excluded).
- **DIST `METHOD=6`** = quadrupole distribution: J3 regenerated as a true
  continuous distribution (cases `J3d_*`): Fitbauer recovers ⟨ΔEQ⟩ to
  0.002–0.010 and σ to 0.005–0.024 mm/s (v0/v1) — the P(ΔEQ) kernel is
  validated against DIST as well, not only against SITE's stack of 10 doublets.
- **DIST also offers** Czjzek and Le Caër (`DISTRI=4`), binomial with `CONC`,
  "EXACT" corrections for a random EFG (QUP/ETA) and at most MBLK=2 blocks —
  noted as a reference for future comparisons.
- **SITE's `THE/PHI`**: θ between B and Vzz; φ between Vxx and B — exactly the
  convention implemented in `full_hamiltonian_lines` (§13). `IFSC=.FALSE.` (our
  case) = powder sample → the isotropic beam average is the correct physics, as
  was assumed.
- **Relaxation**: the manual gives `OME` in **MHz** (Ising = two states ±B, the
  same family as Fitbauer's Blume-Tjon, with ν in s⁻¹; expected conversion
  ν = OME·10⁶). However the demo's IRELAX is **not monotonic in OME** (spectra
  at OME=0.01 and 1000 MHz almost identical to each other and different from
  the one at OME=1; probes `_staging/sondaR2`): the demonstration binary does
  not allow the quantitative mapping to be validated. X1 remains a qualitative
  comparison and the mapping is documented as "per the manual, not verifiable
  with this demo".

## 15. Convergence robustness: fixed in the engine (v4.18.0, 3rd phase)

The two robustness failures of §6.10 and §6.4 are resolved out of the box:

1. The multistart stagnation cut-off no longer abandons candidates while the
   best χ²red is still bad (>2).
2. **Automatic global escalation** (`auto_global`, on by default): if the local
   multistart ends with χ²red>10, the engine launches a differential evolution
   pass and a local refinement.

Re-measurement of the reference experiment (D2_db8: two overlapping sextets,
starts perturbed ±15 %, 20 seeds): **0/20 failures** versus 8/20 with the
previous engine (~5 s/fit on average; the cost is only paid when the local fit
fails). Case C4 (Γ≈1 channel) is covered by the same mechanism. All the new
functions are additionally exposed in the Qt GUI with help and manuals (ES/EN
recompiled; 8 interface languages).

## 16. Second extension with the manual: extremes and centre of every capability (series K and L)

With the full manual (R.A. Brand, 1990) EVERYTHING the demonstration binaries
can do was re-inventoried, and tests were added at the **extremes and centre**
of every capability the v1 bank did not cover. Probes in `validacion/paso2/`
(`paso2_sondas_manual.py`, `paso2b_voigt_bkg.py`); new series `K1`–`K5` (SITE,
`series_KL.py`) and `L1`–`L6` (DIST, `serie_L.py`), plus parametric refits of
block J. Total added: **34 SITE spectra + 15 DIST + 2 native SITE fits**, ~230
new rows in `resumen.csv`.

### 16.1 Capability inventory of the demo (probes)

| Capability (manual) | In the demo? | Series | Result |
|---|---|---|---|
| Octets `NLINE=8` + `D73` | ✔ | K1 | ✔ sextet+2 singlets, χ²red≈0.003 |
| Non-constant background `BKG(2..5)` | ✔ | K2 | ✔ (slope/curv); v³ does not exist in Fitbauer |
| Single crystal `IFSC`+`BEX/GAX` | ✔ | K3 | ✘ documented (Fitbauer averages the beam) |
| Constraints `NDEX/FACTOR/CONST` | ✔ | K4 | ✔ equivalent to the constraints |
| Binomial `DISTRI=3`+`CONC` | ✔ | L1 | ✔ (binomial shape); the histogram over-smooths the extremes |
| Czjzek `METHOD=6`+`DISTRI=4` | ✔ | L2 | ✔ the histogram recovers shape and moments |
| Negative mirror `PNEG` | ✔ | L3 | ✔ (degenerate: unobservable in powder, analytical truth) |
| `EXACT` (mixed order, `QUP`) | ✔ | L4 | partial: effective texture correctable, residual grows with QUP |
| Texture in the distribution `D13/D23` | ✔ | L6 | ✔ after exposing `--d13/--d23` in the CLI |
| Voigt profile `VOIGT/WDLOR` | ✘ inoperative | — | Γ=WID, pure Lorentzian in every case (paso2b) |
| `STI` (δ distribution) | ✘ inoperative | — | identical spectrum with and without STI |
| `DEPSUB` (arbitrary fixed profile) | ✘ not in the namelist | — | only via CONC (binomial) or SITE (J3) |
| Goldanskii-Karyagin `IFGK`+`G2x` | ✘ inoperative | — | PLT identical to powder |
| `S2T` (⟨sin²θ⟩ of EXACT) | ✘ not in the namelist | — | EXACT intensities not configurable |

### 16.2 Successes (mention)

- **K1 octets**: the ΔmI=±2 lines are modelled exactly with a sextet + 2
  singlets (χ²red 0.003–0.006 for D73∈{0.087,0.25,0.5} and B∈{33,46}); the area
  partition DEP·D73/(2·ΣD) is recovered to 10⁻³ (`fig_K1_octete`).
- **K2 backgrounds**: linear, parabolic and combined exact once the convention
  was deciphered (background = 1 + Σ (BKG(k)/1000)·(v/2v_max)^(k−1); the ~2 %
  residual slope bias is the P90 normalisation, documented in §3).
- **K4 native constraints**: SITE fitting with `NDEX/FACTOR/CONST` and Fitbauer
  with `constraints` recover the same truth over the same v1 (tied δ:
  |Δδ|≤1.4e-3 in both; 2:1 areas: |Δdepth|/depth <2 %): **the two constraint
  engines are semantically identical** (PAR(i)=FACTOR·PAR(j)+CONST ≡
  target=factor·source+offset).
- **K5 extremes**: QUA=±0.6, BHF=1 T (collapse) and 60 T, D13∈{1.5,4.5},
  W13=2.5/W23=0.6, sub-natural Γ=0.16, 40 % depth and doublets with
  δ=−2.5/+3.4 via `wide_delta`: all within the v0 tolerances.
- **L1–L3**: binomial (parametric shape: p recovered to ±0.026 even at
  CONC=10/90 %), Czjzek (σ to ±0.04) and PNEG (the folded analytical truth
  confirms the negative mirror is spectrally unobservable: the PNEG=0.2 and 0.5
  spectra are identical).
- **L5 parametric shapes**: `--shape gaussiana` recovers ⟨B⟩ to <0.02 T and σ to
  <0.18 T on the J1 grid; `--shape vbf` N=2 nails moments and peaks (±0.5 T =
  grid resolution) on the J2 bimodals. The `tv` and `maxent` regularizers on
  J1_b30_s3 v1 give σ +0.42 (comparable to the reference Tikhonov).

### 16.3 Documented failures

1. **Single crystal (K3, `fig_K3_cristal_unico`)**. With `IFSC=.TRUE.` SITE
   fixes the γ-ray orientation in the EFG frame (BEX/GAX) and the line
   intensities change; Fitbauer's Hamiltonian treatment averages the beam
   isotropically (powder sample). Positions ✔, intensities ✘ → χ²red 3.4–8.0
   and apparent biases (BHF −0.9 T) at the extreme orientations (β_γ=0 and
   β_γ=φ_γ=90). Cause: an unmodelled capability; roadmap if it ever becomes of
   interest (it requires the beam W(θ,φ) per component). In the POWDER case the
   remaining residual (max 6.0e-3 = 20 % of the peak at η=0.5, θ=30°) is NOT
   Fitbauer's: it is the SITE-1994 approximation (numerical degradation of the
   diagonaliser, confirmed in the source code — §19); the fit redistributes it
   into BHF −0.38 T and ΔEQ +0.14.
2. **Cubic background (K2_cubico, `fig_K2_fondo`)**. `BKG(4)` generates a v³
   term that Fitbauer does not have (baseline+slope·v+curv·v²): slope/curv
   absorb part of it and χ²red 2.5 remains. A rare extreme in practice;
   documented as a conscious limit.
3. **Slope bound (K2_lin_p60)**. The extreme BKG(2)=60 (true slope 7.5e-3)
   exceeded the historical bound of ±0.005 → χ²red 61 with a degenerate fit.
   **Fixed**: bound ±0.02 (χ²red → 3e-7).
4. **ΔEQ bound (K5_dob_q5)**. SITE accepts ΔEQ=5; Fitbauer's classic ±4 bound
   made the fit degenerate (χ²red 82, δ→2.85). **Fixed**: `wide_delta` also
   widens ΔEQ to ±2(v_max+2) (χ²red → 1e-7).
5. **Texture in distributions (L6, `fig_L_textura_exact`)**. DIST accepts
   `D23≠2` per block; the CLI kernel fixed 3:2:1 → a phantom peak at ~15 T and
   σ +47 % (D23=3), σ +134 % (D23=1). **Fixed**: the kernel already supported
   intensities (mossbauer_distribution) and `--d13/--d23` are now exposed in the
   CLI (mapping int3_rel=3/D13, int2_rel=3·D23/(2·D13)); with `--d23 3` the bias
   disappears (σ 3.21 vs 3.0).
6. **DIST's EXACT (L4, `fig_L_textura_exact`)**. With `EXACT=.TRUE.` the demo
   applies an effective intensity pattern ≈3:3:1 **independent of QUP**
   (measured with QUP=0; S2T is not in the namelist) plus mixed-order
   corrections that do grow with QUP. With `--d23 3` Fitbauer captures the
   QUP→0 limit (σ 3.38 vs 4.55); the remaining residual grows with QUP
   (σ +0.4/+0.8/+2.4 for QUP=0.2/0.5/1.0): the validity domain of the
   first-order kernel, like the R map of §5.
7. **Histogram on extreme binomials (L1, `fig_L1_binomial`)**. At CONC=10/90 %
   the distribution is narrow and pressed against the grid edge: the histogram
   regularization over-smooths it (σ +71/+20 %). This is not a model failure but
   a regularizer one with a near-delta truth (already seen in J5); the
   parametric binomial shape solves it (p to ±0.026).

### 16.4 Improvements implemented in this phase (post-v4.18.0)

1. `wide_delta` also widens the ΔEQ bound (core/session.py).
2. `slope` bound ±0.005 → ±0.02 (core/params.py, GUI included).
3. `--d13/--d23` in `fit_bhf_distribution_cli.py` (distribution kernel texture,
   NORMOS convention).

New tests: `tests/test_mejoras_banco_normos2.py` (5); full suite **337 tests**
green.

### 16.5 New SITE/DIST conventions deciphered

- **Octet lines 7,8**: the demo places them at ±1.40108·(B/33) mm/s, 0.32 %
  below the value implied by its own sextet pattern
  (±1.4055 = (1.5a_e−0.5a_g)·k). Measured by fitting 8 Lorentzians; the
  empirical value is used as the truth.
- **Background**: `1 + Σ_{k≥2} (BKG(k)/1000)·(v/(2·VMAX))^{k−1}` (the manual's
  "V1" turns out to be 2·VMAX in the demo); verified with ±BKG at two
  amplitudes, linear and parabolic.
- **NDEX**: numbering by the GLOBAL index of the RES "Index" table (BKG(1)=1;
  subspectrum k: WID=14+15(k−1), ARE=+1, ISO=+2, …). The RES prints the
  constraint ("Variable31(ISO) = 1.0·Variable16(ISO)+0.4") and reduces NVAR.
- **EXACT**: fixed effective intensities ≈3:3:1 (D13/D23 ignored, S2T
  inaccessible); the position/width corrections do scale with QUP.

## 17. Third round: extremes and centre over the original series

The phase-1 grids were deliberately central; `series_ext.py` adds the extreme
points that were missing WITHIN each existing series (24 cases, v0+v1):
doublets with δ=−1.0/+2.0 and ΔEQ from 0.08 (≪Γ) to 5 mm/s, sextets of 0.5 and
58 T, Γ from 0.16 to 2.0, depths from 0.5 % to 40 %, D21∈{0.3, 3}, inverted
width pairs (W13=0.7/W23=1.3), η=0.1, QUA=±0.45, nearly degenerate doublets
(dΔEQ=0.02), Gaussian P(B) at the grid edges and near-delta (σ≈step), and
negative (−0.01) and strong (+0.02) DTI.

Result: **everything converges (0 non-convergences) and everything identifiable
comes out**. The only deviations are the expected ones, and they are
attributed:

- `D6_dq0.02` — a genuine practical degeneracy (two doublets 0.02 mm/s apart:
  equivalent solutions with χ²red≈1; the same would happen to NORMOS).
- `D3_f0.5pc` — below the detection limit with noise (χ²red 0.83 with the
  doublet wandering; the threshold measured in D3 is still ~1–2 %).
- `A5_eta0.1` v0 (Kündig + free intensities) inherits the known int1 bias
  (2.1 vs 3); the v0m refit with `quad_treatment="hamiltonian"` removes it,
  consistent with §13.
- `J1_b30_s0.8` and `J1_b15_s3` — histogram over-smoothing at near-delta and at
  the grid edge (the regularizer's trade-off, as in L1/J5; the parametric
  shapes solve it).
- `J4_dti±` — the δ(B) correlation works with a negative sign and double slope;
  ignoring it (v0_sin_slope) doubles the σ error.

The additional probe `_staging/polar` confirms that the **polarized source**
(DIST `METHOD=4`) does work in the demo and transforms the spectrum completely
(max|Δ|≈0.9): a NORMOS capability with no Fitbauer equivalent, incorporated
into the verdict.

**The complete verdict (what comes out, what does not and why, and what each
program has that the other lacks) is in `VERDICT_EN.md`**, with the numerical
synthesis generated by `veredicto_datos.py`.

## 18. Three capabilities closed (v4.19): single crystal, HC kernel and v³/v⁴ background

Of the four capabilities the verdict flagged as "what Fitbauer is missing", the
first three were implemented and validated (`valida_v4_19.py`,
`fig_v419_mejoras`); only the polarized source remained (low demand, to be
implemented if needed).

1. **Single crystal** (`quad_treatment="hamiltonian_sc"`, parameters
   `bex`/`gax`): a fixed γ-beam direction with a coherent sum across radiation
   channels (Wigner d¹ matrix). Physical anchors: a 3:0:1 pattern with beam∥B
   and 3:4:1 with beam⊥B in the axial limit; the isotropic average over
   directions reproduces the powder mode to 1e-15. Refit of the K3 bank with
   the true angles and FIXED intensities: χ²red 3.5/12.4*/20.4* → 2.9/2.3/2.5
   (*with the corrected convention; the first attempt with a literal GAX made
   things worse: the theory-against-theory sweep revealed that the demo's GAX is
   measured 90° away from the geometric azimuth — gax_Fitbauer = GAX_SITE + 90°,
   a newly documented convention). The remaining χ²red ≈2.5 is the floor of the
   SITE-1994 approximation (identical to the powder case).
2. **Hamiltonian kernel in distributions** (`kernel_treatment="hamiltonian"` +
   η; CLI `--kernel-treatment`): powder averaging of the full Hamiltonian per
   kernel column; ΔEQ = modulus of the random EFG (the non-perturbative
   analogue of DIST's EXACT/QUP). Key physical detail: the average is taken in
   the FIELD FRAME (B∥z, tilted EFG; new `full_hamiltonian_lines_field`) so
   that the D13/D23 texture stays tied to B — in the EFG frame the average
   diluted it to isotropic (a bug detected and fixed during the validation).
   Synthetic round trip: exact moments (test). Bank L4 (v0h): σ at QUP=1 goes
   from +2.4 T (first order) / +2.4 (d23 only) to **+1.0 T**, and ⟨B⟩ stays
   within 0.04 T; the remaining residual is the perturbative truncation of the
   demo's own EXACT (3rd/4th order) plus its non-configurable 3:3:1 pattern.
3. **v³/v⁴ background** (`curv3`/`curv4`): K2_cubico goes from χ²red 2.5 to 2e-7
   with curv3 recovered to 3 figures; the new case K2_cuartico (BKG(5)=60) is
   exact.

All exposed in the GUI (ΔEQ context menu with the 5th treatment; "Kernel"
selector + η in the distribution panel; v³/v⁴ baseline in calibration), with
sessions, i18n in 8 languages and updated ES/EN manuals. Tests:
`tests/test_mejoras_v4_19.py` (11).

## 19. Findings from the NORMOS source code (2026-08-02)

With the source code (Fortran, dated 1990; the demo binary is from 1993/94 and
differs in some places — this is flagged) the open mysteries were resolved and
a new capability validated. The source is proprietary and is NOT in the
repository (`normos/` doubly excluded); only the mathematics is documented
here.

1. **SITE's HAMILT "approximation" is numerical, not analytical** — a
   correction to §13/§16.3: the GMFP (Ruebenbauer–Birchall) is exact (exact
   Hamiltonian, full coherence including that of the ground state, analytical
   powder averaging). The measured deviation (3.7e-5 → 9.6e-3 depending on the
   frame) comes from the diagonaliser: GENERAL complex EISPACK in single
   precision, eigenvectors used as a unitary basis without being normalised or
   orthogonalised, MACHEP=2⁻⁴⁷ (double precision) in REAL*4 code, and IERR
   ignored. Error ∝ ε·‖H‖/gap → frame-dependent. The practical conclusion does
   not change: Fitbauer (Hermitian LAPACK in double precision) is more
   accurate.
2. **GAX**: in the 1990 source it is the standard azimuth from x (like φ); the
   binary's +90° points to a zxz Euler convention in the 1994 executable
   (exactly equivalent to a 90° azimuth offset). The source and the binary
   demonstrably differ (an η/θ/φ argument-passing bug in the source's caller
   that the binary does not have).
3. **DIST's EXACT**: perturbation theory in R = −14.755·QUP/H (position to 4th
   order, area to 3rd with zero sum — which is why the intensities do not
   depend on QUP —, broadening in quadrature per line). S2T occupies D23's SLOT
   (EQUIVALENCE): that is why "S2T does not exist" in the namelist. The
   binary's default behaves like S2T≈6/7 (→ the measured 3:3:1 pattern),
   different from the source's 2/3; the binary's mapping is non-trivial (probes
   recorded). Fitbauer's Hamiltonian kernel contains strictly more physics than
   EXACT.
4. **STI**: only implemented for METHOD=6/7 (5-point Gaussian satellites in δ);
   in field distributions it is merely cosmetic in the listing. **DTQ** in
   METHOD=1: it does not exist in that branch (by design). The exact formulas
   of DISTRI=2 (σ²+Δ² compensation, PNEG mirror), binomial (n=12) and
   Czjzek/Le Caër are confirmed; the LAMDA smoothing is exactly the
   second-difference matrix D₂ᵀD₂ (the same Tikhonov as Fitbauer), without
   Poisson weights and with β₁/β₂ anchors at the ends.
5. **Voigt**: it was NOT inoperative! The 1994 binary changed the semantics:
   the Gaussian width is STG(n) (σ in mm/s for paramagnets — the SAME
   convention as Fitbauer —, σ_B in Tesla for sextets = a Gaussian field
   distribution). Verified with probes (σ recovered to 3 figures). It moves
   from "not validatable" to validatable.
6. **Polarized source (METHOD=4/POLAR)**: implemented in Fitbauer from first
   principles (36-line comb by helicity selection,
   I(i,j) ∝ |m_q|²|m_q|² Σ_λ |d¹|²|d¹|²) and validated against the binary:
   0.4 % of the peak (θ_s=0) and 1.1 % (θ_s=90). Full bank round trip (cases
   L7): ⟨B⟩ to 0.08 T and σ to 0.13 T with noise. CLI:
   `--source-polarized --source-bhf --source-theta --absorber-theta`. SITE's
   POLAR is the same model (γ∥B) for discrete sextets.
7. **IFGK**: inert with IFSC (the crystal branch does not use the G) and for
   ⁵⁷Fe without mixing only G11 can act — this explains the probes' "no
   effect". **IFTRAN**: mathematically identical to Fitbauer's transmission
   integral (same 0.097 source). **Background**: additive over the baseline (it
   does not multiply the absorption), as in Fitbauer; our empirical BKG
   convention formula is exact. **Constraints**: global numbering confirmed
   (base 13+15(n−1)); NLINK is read but not used; a NORMOS bug in the error
   propagation of linked parameters (it uses CONST where it should use FACTOR).
   **Fit σ**: Poisson over folded counts; the RES χ² divides by the MODEL with
   DF=NP−1−NVAR (a convention to imitate when comparing). **Relaxation**: OME
   is in mm/s (not MHz) and it is Blume's closed two-state form. Additional
   probes (relax2) CLOSE the point as non-validatable: BSAT is not in the
   binary's namelist and the demo's IRELAX spectra come out almost collapsed
   even with OME=0 — the 1994 executable's parameter wiring differs from the
   1990 source and is not reconstructible as a black box. X1 remains a
   qualitative comparison, now with the reference physics identified.

## 20. Series V (the binary's Voigt) and the polarized source in the GUI (2026-08-02)

- **Series V**: with the STG semantics discovered in §19.5, the Voigt profile
  was validated round trip. Paramagnetic (V1, σ ∈ {0.05, 0.15, 0.30} mm/s):
  Fitbauer with a Voigt profile and FREE σ recovers σ to ≤4·10⁻³ mm/s (at
  σ=0.05, 6.6·10⁻⁵), with a slight σ↔Γ compensation (Γ −0.7…−1.7 %)
  attributable to the binary's approximate pseudo-Voigt versus Fitbauer's exact
  Voigt. Magnetic (V2, σ_B ∈ {0.5, 1.5, 3} T): Fitbauer's "Gaussian" shape
  nails ⟨B⟩ (≤4·10⁻³ T) and σ_B (exact at 1.5/3 T; +0.046 at 0.5 T where
  σ_v ≈ Γ/2). Voigt moves from "not validatable" to VALIDATED.
- **Polarized source in the GUI**: a "Polarized source (γ∥B)" checkbox in the
  distribution panel with the source B and the source/absorber-beam angles,
  session persistence and a wiring test; i18n in 8 languages and updated ES/EN
  manuals (a new § in the distributions chapter).

## 21. Full source-code review and coverage closure (2026-08-02)

A systematic sweep of the ten levels of the Fortran source (SITE + DIST, 1990)
against `core/`, verifying each one against the demo binary or against
independent references. The result is in two documents:

- **`COVERAGE_NORMOS_EN.md`** — a COMPLETE capability inventory: the list of
  parameters and switches was extracted from the namelists (`sitemdos.for`,
  `distmdos.for`) and cross-checked one by one. Of ~60 capabilities, Fitbauer
  matches or improves on all those in the ⁵⁷Fe domain except six, and is
  measurably better at six specific points.
- **`PENDING_NORMOS_EN.md`** — a roadmap of what remains, with the source
  reference, what to touch, how to validate it and whether it is worth it.

Closed in this review: selectable sextet position convention, line asymmetry
(AKS), area-based intensity convention, folding with cubic interpolation (Γ was
coming out up to 9.5 % high), geometry effect, two search cycles, recovery of
the edge channels, resonant fraction of the source (FSO), a source kernel 19×
more accurate, error bars with absolute σ, linked-parameter errors, population
polarization in relaxation, edge anchors in distributions with the
`edge_pileup` diagnostic, P(δ) exposed, and dispersion-based widths (the Brand
model).

Program suite: 483 tests.
