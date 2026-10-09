# Fitbauer v5.1.1

*[🇪🇸 Notas en español](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.1.1_ES.md)*

Bug-fix release on top of 5.1.0.

---

## The plot no longer freezes after zooming

After zooming or panning with the plot toolbar, newly loaded spectra could be
drawn outside the visible area, so the plot looked frozen and seemed not to show
the new data. Zooming turns off Matplotlib's autoscaling, and the fast refresh
reused the old axis limits for any spectrum with the same number of channels.
After zooming on α-Fe, only 7 % of the points of a hematite spectrum and 20 % of
a magnetite one were visible.

Now, loading a different spectrum re-enables autoscaling and resets the
toolbar's view history, so **Home** takes you to the new spectrum. When only the
model changes (moving sliders, fitting), your zoom is kept.

## Parameter constraints use the panel's names

**Fit ▸ Parameter constraints** used to list every internal key (`s1_delta`, …)
for every component, including disabled components and parameters the chosen
shape does not use. It now offers only what is shown in the simulation and fit
panel, with the same labels (“Component 1 · Isomer shift δ”). Sessions are
unaffected: constraints are still stored by key, and an existing constraint on a
parameter that is no longer shown is kept. Column headers are translated, and
the constrained parameter's new value shows in the panel as soon as you press OK.
