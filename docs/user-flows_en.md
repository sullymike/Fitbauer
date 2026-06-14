# User flows

This guide summarizes the usual journeys in Fitbauer's Qt interface.

## 1. Open a spectrum and simulate

1. Start the application:

   ```bash
   python fitbauer.py
   ```

2. Open a file from **File → Load...** (`.ws5` or `.adt`).
3. Review the folding point and `Vmax` in the calibration panel.
4. Adjust component parameters manually if desired.
5. The plot updates in simulation mode until a real fit is launched.

## 2. Discrete fitting

1. Choose discrete mode.
2. Select the number of components.
3. For each component:
   - type: singlet, doublet or sextet,
   - initial values,
   - fixed/free parameters.
4. Optional: use **Initialize from minima** to propose components.
5. Press **Fit**.
6. Review:
   - χ², reduced χ², AIC/BIC,
   - residual diagnostics,
   - percentage areas,
   - errors and correlations if available.

## 3. Bootstrap

1. Perform or prepare a discrete fit.
2. Go to **Tools → Bootstrap**.
3. Choose the number of replicas.
4. The result updates the uncertainties and the error source indicated in reports.

## 4. Distribution `P(BHF)` / `P(ΔEQ)`

1. Switch the mode to distribution.
2. Choose the variable: `P(BHF)` or `P(ΔEQ)`.
3. Configure:
   - minimum/maximum range,
   - number of bins,
   - `δ`, fixed `ΔEQ`/`BHF`, `Γ`,
   - `log10 α`, shape and regularization.
4. Optional: use **L-curve α** to estimate regularization.
5. Optional: enable **sharp components** to add discrete phases to the fit.
6. Press **Fit**.
7. Review the fitted curve, residual and resulting distribution.

## 5. Calibration

There are two routes:

- **Web calibration**: download metadata from the laboratory API.
- **Local calibration**: use the current file as calibration from the context menu.

The calibration affects traceability, `Vmax` and the isomer shift reference when available.

## 6. Save session

Use **File → Save session...** to save:

- file/counts,
- model,
- parameters and fixed flags,
- fitting options,
- distribution,
- relevant visual preferences.

The JSON session keeps compatibility with historical formats.

## 7. Export results

Main options:

- **Save fit**: exports velocity, data, model and residual in text.
- **Export Plotly**: interactive HTML figure.
- **Export report**: Markdown and, if available, PDF.

The report includes traceability, calibration, parameters, areas, metrics, correlations and residual diagnostics.

## 8. Validations and warnings

Before fitting, Fitbauer validates:

- data lengths and finiteness,
- parameter bounds,
- positive `sigma`,
- distribution ranges,
- minimum number of bins,
- known component types and regularization.

If there are problems, the GUI shows a warning and does not launch the fit.
