# Fitbauer v5.3.0

*[🇪🇸 Notas en español](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.3.0_ES.md)*

Fitbauer now opens spectra from any spectrometer without converting them
first, and remembers each instrument: how to read its files, how to fold them
and which velocity calibration applies on each date. This release also brings
a set of fixes found by fitting real spectra that had already been analysed
with WMOSS and WinNormos, and the agreement with both programs is now
documented.

**Nothing changes for existing work.** Instruments are optional; without one,
files open as before. Saved sessions, templates and calibrations load as they
did in v5.2.5.

---

## Importing spectra from any instrument

- **Files are opened by their content, not their extension.** A generic
  reader finds the data block (whatever comes before is the header and
  whatever comes after is the footer), detects the separator and the decimal
  comma, and works out what each column is: channel, velocity, intensity,
  error, or several counts per line. It also tells counts from transmission or
  absorption, as a fraction or in %. This applies to *Load…*, drag and drop,
  recent files, batch fitting, the global relaxation fit and spectrum
  comparison.
- **New import window** (*File › Import…*, Ctrl+I). It shows the file before
  loading it, with the data highlighted, what the reader deduced, and a
  preview of the spectrum. Every deduction can be corrected.
- **Folding is an explicit choice**, as with `FOLD` in NORMOS: *Fold*, *Unfolded:
  single sweep* (data already folded by the spectrometer) or *Unfolded: two
  branches*, plus *Reverse direction* for instruments that sweep from + to −.
  Unfolded, each point is one channel and the fit uses σ = √counts. The mode is
  kept in sessions, templates, batch fits, comparisons and the command line
  (`--fold`, `--reverse-velocity`). `.JOB` files with `FOLD=.FALSE.` are
  imported and exported accordingly.
- **Spectra with their own velocity axis** take their noise from the error
  column, or estimate it from the data, and are fitted with Gaussian weights.
- **WMOSS processed files** (`*.b`, `*.t`, "% absorbance") are read correctly,
  including the trace of a single subspectrum.

## Instruments and calibrations

- **Instruments** (*File › Instruments and calibrations…*). An instrument
  stores the import corrections, drive waveform, folding mode and direction.
  It can also recognise its own files by text in the header or footer or by
  the file name, and is then applied automatically on opening.
- **Calibrations per instrument.** Each instrument keeps its velocity
  calibrations: the date from which each one is valid, Vmax, sextet pattern,
  isomer shift of α-Fe, and a copy of the α-Fe spectrum, which can be reopened
  from the manager. A spectrum receives the calibration valid on its
  measurement date, read from the file or, failing that, from the file date
  with a warning. Instruments whose files carry no dates can use the most
  recent calibration instead. A calibration can also be chosen by hand.
- **Batch fitting, the global Néel fit and the command line** use each file's
  calibration (`mossbauer_fit_cli.py --instrument NAME`, or `--instrument auto`).
  The result tables record which calibration was used for each file.

## Comparison with WMOSS and WinNormos

- **Comparing spectra with processed files from WMOSS or WinNormos.** You can
  choose which column to overlay (data, total fit or one site). An axis with
  α-Fe at zero can be moved to the source scale with the active calibration.
- **Fits of real spectra already analysed with WMOSS and WinNormos agree**
  within the precision those programs report: δ, ΔEQ and Γ to within a few
  thousandths of mm/s, and relative areas to within about one point.
- **How each program folds, and what that does to χ², is now documented** in
  the manual, the in-program help and `docs/folding_en.md`. WMOSS folds with a
  fractional folding point and smooths the data, so its reduced χ² is not
  directly comparable with Fitbauer's or NORMOS's on the same spectrum.

## Fixes

- **The noise of a folded spectrum now accounts for interpolation.** With a
  fractional folding point, Fitbauer interpolates between channels, which
  averages neighbouring channels and reduces the noise. The fit σ ignored this,
  so the reduced χ² came out up to 24 % low and the errors slightly large. It is
  now corrected for any folding point. Fitted parameters do not change.
- **Deep doublets.** A line deeper than 30 % stuck at the fit bound and the fit
  compensated by widening Γ. The bound is now released when it is reached.
  Fitted values outside a control's range are shown instead of being silently
  clipped.
- **The velocity axis follows Vmax** when a calibration is applied from the
  manager, a session or the web, so that the next fit uses the new axis.
- **The folding point** is limited relative to the number of channels (it was
  capped at 263 with 1024 channels). The window and the command line use the
  same NORMOS folding point, and only when it is plausible.
- **The window, batch fits and the command line use the same velocity axis**
  when outlier edge channels are trimmed.
- **The Vmax of a processed file applies only to that file**, not to raw
  spectra opened afterwards.
- **A component switched to a doublet has ΔEQ free.**
- **A session whose folder was moved** finds its spectrum next to it.
- Loading warnings are no longer hidden by the "file loaded" message.

## Documentation

The user manuals (English and Spanish), the in-program help in 8 languages
and the command-line appendix cover importing, instruments, calibrations,
folding and the comparison with WMOSS.

---

Full suite: **933 tests passing**.
