# Notas de versión — Fitbauer v4.14.0

Esta versión es una **puesta al día grande** (acumula todo lo trabajado desde
v4.11.0): drive senoidal, un ejecutable más ligero sin Plotly, calibración fija
reutilizable, manual de usuario, y un salto importante en el ajuste de
distribución P(BHF)/P(ΔEQ).

---

## Novedades destacadas

### Drive senoidal estilo NORMOS (v4.14.0)
Fitbauer ya admite datos medidos con drive **senoidal**, no solo de aceleración
constante (triangular). Antes había que pre-linealizarlos; ahora se ajustan de
forma nativa (`TRIANG=.FALSE.`, `FOLD=.FALSE.`, `SIMULT=.TRUE.`): **no se doblan**
y se ajusta el espectro completo asignando a cada canal su velocidad real
`v_i = vmax·sin(2π(i−c0)/N)`.

- Nuevo control **Forma de onda** (triangular/senoidal) en calibración, persistido
  en la sesión.
- En senoidal la **fase** `c0` (canal de v=0) se autodetecta por simetría y es
  ajustable; con *Ajustar centro* entra como parámetro libre. *Ajustar Vmax* refina
  la amplitud.

### L-curve interactiva (v4.13.2)
El diálogo de la L-curve permite ahora **elegir α pinchando la figura** (en la L
`rugosidad↔residuo` o en `α↔RMS`). La esquina automática (curvatura de Menger) pasa
a ser una sugerencia; el botón «Usar α=…» aplica el valor elegido.

### Ejecutable más ligero: se retira Plotly + QtWebEngine (v4.13.1)
Se elimina la dependencia de **Plotly** y **QtWebEngine** (Chromium embebido): binario
mucho más ligero, arranque más rápido y sin *segfaults* de cierre. El **gráfico es solo
Matplotlib** y el **editor de mínimos** se reimplementa sobre el canvas Matplotlib
(`gui/minima_editor.py`). La integración anterior queda documentada en `docs/plotly.md`
por si se quisiera restaurar.

### Calibración fija reutilizable + manual de usuario (v4.13.0)
La calibración deja de reajustarse en cada carga: se convierte en un estado **fijo y
persistente** que se aplica de forma coherente al cargar espectros en bruto, se sustituye
(con aviso) al cargar un fichero con calibración propia, y puede **liberarse** desde el
menú contextual. Se añade un **manual de usuario** LaTeX extenso en `docs/manual/`
(calibración, carga de datos, simular/ajustar y distribuciones) con figuras de física
auto-generadas desde `core/`.

### Ajuste de distribución P(BHF)/P(ΔEQ): tres métodos nuevos (v4.12.0–v4.12.3)
- **Correlación δ(H)/ΔEQ(H)**: δ y ΔEQ pueden variar linealmente con H
  (pendientes κδ/κq; opt-in, 0 = clásico; refinables en el lazo externo).
- **MaxEnt** (`reg_mode="maxent"`): máxima entropía por L-BFGS-B con gradiente
  analítico; garantiza P≥0 y ∫P=1.
- **VBF multi-gaussiano** (Rancourt–Ping): ajuste de N gaussianas sobre perfil Voigt;
  informa **área y % de cada componente** (población de cada entorno).
- **α adimensional** (v4.12.2): el penalizador se escala por la norma de los operadores,
  de modo que `log α ≈ 0` es el balance natural datos/suavidad para cualquier espectro y
  el codo de la L-curve queda estable frente a N, ruido y profundidad de absorción.
- **Persistencia e informes** (v4.12.1): forma, regularizador, κδ/κq, componentes VBF y
  nítidos se guardan en el resultado, la sesión, el panel de estado, los informes
  (PDF/ODT) y el export TSV.

---

## Compatibilidad

- El valor numérico de **α** de distribución cambia de significado (ahora adimensional);
  las sesiones antiguas cargan con el nuevo default y los α guardados se reinterpretan en
  la nueva escala. El comportamiento cualitativo (α→0 sin regularizar, α↑ más suave) se
  conserva.
- **No soportado** aún: componente de relajación con drive senoidal.

## Tests

Suite completa en verde (**244 tests**), incluyendo los nuevos de distribución avanzada
(correlación/MaxEnt/VBF), drive senoidal y L-curve interactiva, además del golden headless
y la validación sintética del motor.

El detalle completo por versión está en `CHANGELOG.md`.
