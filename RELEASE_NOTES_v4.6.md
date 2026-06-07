# Release Notes v4.6 — Fitbauer

Esta versión introduce una expansión significativa de las capacidades de ajuste de distribuciones y un nuevo módulo avanzado de relajación magnética.

## Distribuciones Generalizadas (1D y 2D)

Se ha generalizado el motor de distribuciones bidimensionales para permitir cualquier par de parámetros hiperfinos, no solo BHF y ΔEQ.

- **Nuevos Modos 2D**: Soporte para **P(IS, ΔEQ)** y **P(BHF, IS)**, permitiendo explorar correlaciones entre el desplazamiento isomérico y el cuadrupolo, o entre el campo y el desplazamiento.
- **Nueva Distribución 1D**: Implementación de **P(IS)** para analizar la distribución del desplazamiento isomérico.
- **Mejoras en el Diagnóstico**: Inclusión de medias, sigmas y correlación aparente en el informe y la GUI, junto con la exportación TSV generalizada y mapas interactivos en Plotly.
- **Documentación Matemática**: Nuevo documento `docs/distribuciones_is_mossbauer.pdf` detallando la física y riesgos de identificabilidad de estas distribuciones.

## Módulo de Relajación Magnética

Implementación completa de un framework para el análisis de nanopartículas y materiales superparamagnéticos a través de cinco fases de desarrollo:

1. **Modelo Fenomenológico**: Componente que interpola entre el estado bloqueado y el superparamagnético mediante una fracción ajustable.
2. **Control de Tasa**: Introducción de la tasa de relajación $\\nu$ (ajustable como $\\log_{10} \\nu$) para controlar la transición lento $\\rightarrow$ intermedio $\\rightarrow$ rápido.
3. **Modelo Blume–Tjon**: Implementación del modelo dinámico de dos estados ($+B_{\\mathrm{HF}} \\leftrightarrow -B_{\\mathrm{HF}}$).
4. **Modelo Néel–Arrhenius**: Integración de la ley de Néel con distribución lognormal de tamaños de partícula.
5. **Ajuste Global**: Capacidad de realizar ajustes simultáneos de múltiples espectros a diferentes temperaturas, compartiendo parámetros físicos globales (como $K_{\\mathrm{eff}}$ y diámetro medio).

## Mejoras de Interfaz y Usabilidad

- **Refinamiento Directo**: En los ajustes de distribución, los parámetros $\\delta$ y $\\Gamma$ ahora se refinan directamente si su casilla "fijo" está desmarcada, eliminando la necesidad de un interruptor global.
- **Persistencia de Sesión**: Los parámetros y estados (fijo/libre) del panel de distribución ahora se guardan y restauran completamente en los archivos de sesión JSON.
- **Ventana de Progreso**: Información detallada en tiempo real durante el ajuste de distribuciones (fase, iteración, RMS actual vs mejor y tabla de parámetros libres).
- **Claridad de Parámetros**: El parámetro $\\beta$ del sextete ahora se oculta automáticamente salvo en el tratamiento de Kündig fijo, y se ha renombrado a `β Kündig (BHF↔Vzz, °)` para evitar confusiones.

---
*Versión estable. Compatible con sesiones y plantillas anteriores.*
