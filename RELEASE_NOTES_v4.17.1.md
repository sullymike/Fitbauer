# Fitbauer v4.17.1

## Γ inicial físico en «Inicializar desde mínimos»

- **El estimador de anchura CWT proponía Γ ~3× demasiado grande**: para una
  Lorentziana de FWHM Γ, la escala Ricker de máxima respuesta cumple
  2·a·dv ≈ 2.85·Γ (ratio empírico estable 2.6–3.0 en Γ = 0.2–1.0 mm/s), pero la
  conversión escala→anchura no aplicaba ese factor. α-Fe arrancaba con
  Γ = 0.75 mm/s (real ≈ 0.28), hematita con 0.94 y magnetita saturaba el tope
  de 2.0 — el autoajuste partía de líneas absurdamente anchas, y la rama CWT era
  además inconsistente con la rama directa a media altura (que sí mide FWHM).
- Con la calibración (`_CWT_LORENTZ_WIDTH_RATIO = 2.85`): α-Fe → 0.26,
  hematita → 0.33, magnetita → 0.46/0.73.

## Verificación E2E por modalidad

Arnés ejecutado sobre las 10 variantes de ajuste del programa — discreto (con
«Ajustar centro»), P(BHF) Histograma/VBF/maxent, P(BHF)+componente nítida,
P(ΔEQ), P(IS) y las tres distribuciones 2D — con valores iniciales desplazados
a propósito: en todas, **cada parámetro libre varía en el ajuste y se recupera
tras guardar/cargar la sesión**. El caso representativo (P(BHF) con κδ libre +
roundtrip de sesión) queda incorporado a la suite.

Suite completa: **289 tests en verde**.
