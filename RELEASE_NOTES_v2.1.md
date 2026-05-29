# Mossbauer v2.1

Versión que amplía el motor de ajuste y la usabilidad tras el manual matemático
(`docs/manual_mossbauer.pdf`). Incluye ZIP instalable, documentación y checksums
SHA-256.

## Motor de ajuste
- Verosimilitud seleccionable **Gauss / Poisson** (IRLS).
- **Pérdida robusta** opcional (Soft L1 / Huber).
- **Propagación de σ de calibración** (vmax) a los pesos.
- **Optimización global** opcional (evolución diferencial) antes del TRF.
- **Tratamiento de Kündig** del cuadrupolo (Hamiltoniano axial, β libre) + promedio policristal.
- **Parámetro de textura** por sextete (t = sin²θ).
- Normalización **analítica** del perfil Voigt.

## Distribución P(BHF) / P(ΔEQ)
- Regularización por **Variación Total** además de Tikhonov.
- Selección de **α por GCV** (junto a curva L y compromiso).
- **Grados de libertad efectivos** en el χ² reducido.
- **Barras de error 1σ** de P(BHF).
- Preacondicionamiento de la matriz núcleo para BHF pequeño.

## Usabilidad
- Submenú **"Opciones avanzadas de ajuste"**.
- **Menús contextuales (clic derecho)** en los sliders: modo de intensidades y tratamiento del cuadrupolo.
- **Agrisado** de parámetros no usados según tipo y modo.
- **No se simula al cargar** datos hasta tocar un parámetro o ajustar.
- **Previsualización en vivo** de sextetes en modo distribución.
- "Inicializar desde mínimos" activa los componentes y escala las profundidades a los datos.
- **Clic derecho en la caja de muestra** para usarla como calibración (vmax e iso actuales).
- **δ isomérico corregido** (δ − iso de calibración) en cuadro de resultados e informe.
- Ayuda integrada ampliada (es/en/fr).

## Documentación
- Manual matemático extenso del motor de ajuste en `docs/` (LaTeX + PDF).
