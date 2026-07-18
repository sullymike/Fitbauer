# Fitbauer v4.16.1

Corrección de un fallo visible en la GUI relacionado con el ajuste del folding point.

## «Ajustar centro» ahora se refleja en la interfaz

- El motor de ajuste sí optimizaba el folding point con «Ajustar centro» activo
  (corregido en v4.15.0), pero la GUI **descartaba el resultado**: no volcaba el
  centro ajustado al widget de calibración ni re-doblaba los datos con él, por lo
  que el usuario veía siempre el mismo valor tras el ajuste.
- Ahora, tras el ajuste discreto con «Ajustar centro» activo, el widget muestra el
  centro ajustado y los datos se re-doblan con él — GUI y motor quedan coherentes.
  Funciona en modo triangular y seno.
- Test de regresión: `tests/test_qt_app.py::test_fit_center_updates_widget_and_refolds`
  (falla sin el arreglo, pasa con él). Suite completa: 277 tests en verde.
