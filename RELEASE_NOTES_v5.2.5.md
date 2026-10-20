# Fitbauer v5.2.5

*[🇪🇸 Notas en español](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.2.5_ES.md)*

A corrective release. The sextet line pattern that Fitbauer used by default
had no published source. It is replaced by the pattern derived from the
nuclear moments, the same one NORMOS uses. With it, Fitbauer and NORMOS give
the same hyperfine field without any adjustment.

**Old calibrations and sessions keep working.** Calibrations made with earlier
versions are converted automatically, and saved sessions are reproduced
exactly. A sample's BHF changes by less than 0.01 % (about 0.002 T).

---

## The sextet line pattern

Since v4.0.3, Fitbauer placed the six lines of a sextet at 33 T at
±0.8385 / ±3.0835 / ±5.3285 mm/s, described in the code as the "published α-Fe
pattern".

- **It has no published source.** These numbers are constants from the
  laboratory's earlier software, where they were the 32.95 T pattern. In
  v4.0.2 they were relabelled as the 33.0 T pattern.
- **Its shape matches no measured moments.** Its ratio of excited- to
  ground-state splitting, g1/g0, is 0.5724. The value measured by Violet and
  Pipkorn (J. Appl. Phys. 42, 4339, 1971) is 0.5714, the one NORMOS uses.
- **The old argument against the nuclear moments was circular.** It said that
  "α-Fe reads 33.12 T" with them, but that came from reusing a calibration made
  with the previous pattern. With Vmax calibrated with the same pattern, any
  pattern gives 33.0 T for α-Fe.

The new default, `"normos"`, places the lines at ±0.8410 / ±3.0836 / ±5.3261
mm/s at 33 T, checked against the NORMOS binary to 6·10⁻⁶ mm/s.

The previous pattern remains available as `"legacy"` (alias `"alpha_fe"`) in
*Fit › Advanced fit options › Conventions* and in the `--sextet-pattern`
option of the command-line tools, to reproduce old work.

## Calibrations and sessions

- **Calibrations store the pattern they were made with.** Local calibrations
  without one, from earlier versions, are taken as legacy. Fitbauer applies
  their Vmax converted (× 0.999623) and says so in the calibration panel and in
  the report. Changing the pattern in the menu re-applies the calibration,
  converted.
- **Calibrations downloaded from the web API** are NORMOS VMAX values, already
  in the new pattern, and are applied as they are. Only those the API marks as
  `"legacy"` are converted.
- **Files that carry their own velocity axis** are not touched.
- **Saved sessions** without a pattern, or with `"alpha_fe"`, load with the
  legacy pattern and give the same results as before.
- **Preferences** from earlier versions move to the new default.

With a converted calibration, a sample's BHF changes by less than 0.01 %, and
δ and ΔEQ by −0.038 %.

## Other fixes

- **Conventions brought in by a session or a `.JOB` are no longer saved as
  preferences.** Only what you choose in the Conventions menu becomes the
  default for new analyses. Before, opening an old session and closing the
  program left its conventions, including the legacy pattern, as the default
  for everything that followed.
- **The four "reference" spectra in `data_sample/`** (α-Fe, haematite,
  siderite, magnetite) are synthetic. The documentation no longer presents
  them as measurements.

## Validation

The synthetic validation bench against NORMOS was regenerated with the new
pattern: 432 cases, 6520 comparisons. It no longer needs a scale factor for
the hyperfine field.

| Block | Median BHF difference before | Now |
|---|---|---|
| First-order core | 4·10⁻⁵ T | 6·10⁻⁶ T |
| Texture and intensities | 2·10⁻³ T | 6·10⁻⁶ T |
| Multi-site and constraints | 2·10⁻⁴ T | 1·10⁻⁵ T |
| Full Hamiltonian | 8·10⁻⁴ T | 1.4·10⁻³ T |

Only the full Hamiltonian block goes up, within the approximation NORMOS-SITE
itself makes. Failed criteria drop from 745 to 711. The comparison on 146 real
NORMOS jobs is unchanged.

## Documentation

The calibration chapter (`docs/calibration_33T.md`), the sextet model
specification, the user manuals (English and Spanish), the in-program help in
8 languages and the wiki are updated.

---

Full suite: **770 tests passing**.
