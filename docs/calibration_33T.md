# Hyperfine field calibration: α-Fe standard at 33.0 T

Source: `core/constants.py` (`LINE_POS_33T`, `_BASE_POSITIONS`, `fe57_sextet_positions`)

---

## The problem of calibrating the BHF

In a magnetic Fe-57 sextet, the six lines separate proportionally to the hyperfine
field $B_{hf}$. To convert the **measured line positions** (in mm/s) to a **field in
teslas** a conversion factor is needed. There are two ways to obtain it:

1. **From the nuclear moments** ("textbook" calculation): using $\mu_N$, the
   ground- and excited-state $g$ factors, and the $\gamma$ energy. It gives
   theoretical positions.
2. **From a published velocity standard**: using the measured positions of a
   well-characterized reference material (metallic α-Fe at room temperature).

**Fitbauer uses the second way**, just like Normos.

---

## Why nuclear moments are NOT used

The theoretical calculation from the nuclear moments gives a magnetic splitting
**~0.4 % smaller** than the experimental α-Fe standard:

| Origin | Outer-line separation (1–6) |
|---|---|
| Theoretical (nuclear moments) | ~5.309 mm/s |
| Experimental (published α-Fe) | 5.328 mm/s |

If calibrated from theory, a real α-Fe spectrum would fit to a BHF **~0.1 T too high**
(systematic bias). That is why `core/constants.py` explicitly warns against replacing
the published positions with theoretical values (see CHANGELOG v4.0.2 / v4.0.3).

The nuclear data (`MU_N`, `E_GAMMA`, `G_GROUND`, `G_EXCITED`) **remain in the module
as reference/documentation**, but are NOT used for calibration.

---

## α-Fe velocity standard at 33.0 T

The hyperfine field of metallic α-Fe at room temperature is, by convention,
**33.0 T**. The published positions of its six lines (in mm/s, with respect to the
center) are:

$$\pm 5.329 \quad \pm 3.084 \quad \pm 0.839 \;\; \text{mm/s}$$

In the code, the base positions are already stored symmetrized:

```python
_BASE_POSITIONS = np.array([-10.657, -6.167, -1.677, 1.677, 6.167, 10.657]) * 0.5
#                = [-5.3285, -3.0835, -0.8385, 0.8385, 3.0835, 5.3285] mm/s
LINE_POS_33T = fe57_sextet_positions(33.0)
```

---

## Linear scaling with the field

For an arbitrary field $B_{hf}$, the positions scale **linearly** with respect to the
33.0 T standard:

$$v_j(B_{hf}) = v_j^{(33\mathrm{T})} \cdot \frac{B_{hf}}{33.0}$$

implemented in `fe57_sextet_positions(bhf_t)`. To this are then added the isomer
shift $\delta$ and the first-order quadrupole pattern $q_j \cdot \Delta E_Q$ (see
`docs/manual_mossbauer.tex`, sextet section):

$$v_{0,j} = \delta + q_j \Delta E_Q + v_j^{(33\mathrm{T})}\frac{B_{hf}}{33.0}$$

with the first-order quadrupole pattern:

```python
LINE_QUAD_PATTERN = [0.5, -0.5, -0.5, -0.5, -0.5, 0.5]
```

---

## Related constants

| Constant | Value | Use |
|---|---|---|
| `BHF_DEFAULT_T` | 33.0 | Reference field and default initial value |
| `_BASE_POSITIONS` | ±5.329 / ±3.084 / ±0.839 (×internal scale) | Published α-Fe standard |
| `LINE_POS_33T` | `fe57_sextet_positions(33.0)` | Positions at 33 T used by the fit engine |
| `LINE_QUAD_PATTERN` | [+½,−½,−½,−½,−½,+½] | First-order quadrupole pattern |
| `DIST_BHF_RANGE` | (0.0, 60.0) | Default range of the `P(BHF)` grid |

---

## Practical verification

To check the calibration: load `data_sample/hierro_metalico_alphaFe.adt` (or the ESRF
calibration) and fit. The resulting BHF should come out very close to **33.0 T** and
the line positions should match the published standard. Any systematic deviation
indicates a problem with $V_{\max}$ (velocity calibration) or with the folding point,
not with the physical model.

> **Repository rule.** The reference field is **33.0 T** with the published α-Fe
> velocity standard (±0.839 / ±3.084 / ±5.329 mm/s). `LINE_POS_33T` lives in
> `core.constants`. Do not derive positions from the nuclear moments.
