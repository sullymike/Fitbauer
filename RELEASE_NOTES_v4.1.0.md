# Fitbauer v4.1.0

## ✨ Subespectros en el modo distribución (Qt)

- Al ajustar en **distribución P(BHF)/P(ΔEQ) con componentes nítidos**, la interfaz Qt dibuja ahora **todos los subespectros**:
  - cada componente nítido (sextete/doblete/singlete) como curva propia,
  - la **envolvente de la distribución**,
  - y el modelo total.
- Antes la Qt solo mostraba el modelo total; la interfaz Tk ya dibujaba los subespectros, así que ambas quedan a la par.
- Los subespectros se reconstruyen con el mismo kernel del ajuste, por lo que coinciden exactamente con lo ajustado. Disponibles también en el gráfico interactivo Plotly.

## 🔁 Compatibilidad

- Sin cambios en cálculo, sesiones ni informes.
- Verifica el ZIP con `sha256sums.txt`.
