# Fitbauer v5.1.0

*[🇪🇸 Notas en español](RELEASE_NOTES_v5.1.0_ES.md)*

Minor release on top of 5.0.0: a more comfortable interface, a fidelity fix when
importing NORMOS jobs, and third-party licensing put in order.

---

## Importing `.JOB`: area constraints, properly rescaled

NORMOS constrains **areas** (`ARE(2)=f·ARE(1)`); Fitbauer's parameter is the
**depth** (area = depth·(π/2)·ΣΓ). When the two subspectra have different
linewidths, copying the factor verbatim mis-scaled the constrained subspectrum —
in one real job, 14 % off the NORMOS curve. Factor and offset are now rescaled
using the job's own denominators, with a warning that the ratio drifts if the fit
moves the linewidths.

Found in a bulk analysis of **357 real `.JOB` files**. After the fix, Fitbauer
reproduces the NORMOS curve to a **median 0.022 % of peak** in 336 of the 337
analysable jobs —the remaining one is a fit where NORMOS itself diverged— and its
refit **matches or improves NORMOS's χ² in 321 of 336**.

## A more comfortable interface

- **Drag and drop** onto the window: `.ws5`/`.adt`/`.mos` opens the spectrum,
  `.json` restores the session, and `.JOB` imports the NORMOS job together with
  its spectrum.
- **Autosave and recovery.** Every three minutes the work in progress is dumped
  to `recuperacion.json` (atomic write); if Fitbauer was closed without saving,
  it offers to recover it at start-up, naming the spectrum and the time. It does
  not replace saving the session: it is a safety net for the hours spent on fine
  fitting.
- **Warning when closing with unsaved work** (Save / Quit without saving /
  Cancel). The window used to close silently and, since autosave arrived, a clean
  close also took the recovery point with it.
- **Shortcuts for the daily workflow**: Ctrl+M initialise from minima,
  Ctrl+Shift+M autofit, Ctrl+E edit minima, Ctrl+F release all, Ctrl+Shift+F fix
  all. The whole cycle can now be driven from the keyboard.
- **Copy results** (*File ▸ Copy results*, Ctrl+Shift+C): the parameter table
  with its errors, χ², AIC and BIC, as tab-separated text that Excel and Origin
  paste into columns — active components only.
- **Tooltips on every parameter** —label, spin box and slider—, stating which
  controls open a context menu, and **"Right-click ▸ More information"** takes
  each parameter to its chapter of the built-in help. 38 new keys × 8 languages.
- **The line profile becomes a dropdown**, next to the waveform and absorber
  ones, with σ right below it. Calibration now hides what does not apply
  (−23 % panel height) and the isomer shift heads the component panel again.
- **The empty state shows how to start**: "Drag a spectrum here (.ws5, .adt,
  .csv…) or press Ctrl+O".

## Your settings, safe

- **The test suite no longer overwrites the user's configuration.** Building a
  window inside a test was enough to clobber `~/.config/mossbauer_fe33_gui/`; an
  autouse fixture now redirects that directory to a temporary one.
- **`settings.json` is written atomically**, and if it exists but cannot be read
  it is set aside as `settings.json.corrupto` instead of being overwritten.

## Third-party licences

Fitbauer's code remains **Apache 2.0**, but distributing executables that bundle
Qt brings the **LGPLv3** obligations for that part. All three are now covered:

- `NOTICE` and `THIRD-PARTY-LICENSES.md` at the root, listing every dependency
  with its licence, plus the full text of the LGPLv3 and GPLv3 in `licenses/`.
  All four travel inside the ZIP and inside the PyInstaller build.
- The **About** dialog states that Qt is used through PySide6 under the LGPLv3,
  in all 8 languages.
- The READMEs explain how to **replace the Qt libraries** (LGPLv3 §4): the source
  distribution does not bundle Qt at all —`pip` installs it— and in the *one-dir*
  build it is enough to replace the `.so`/`.dll` files under
  `_internal/PySide6/`, with no rebuild.

---

Full suite: **584 tests passing**.
