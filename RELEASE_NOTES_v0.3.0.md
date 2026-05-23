# Mössbauer Fe-57 GUI v0.3.0

Versión orientada a distribución pública, documentación internacional y trazabilidad del análisis.

## Novedades principales

- Interfaz preparada para varios idiomas.
- Catálogos iniciales de interfaz en español, inglés y francés.
- Ayuda integrada disponible en español, inglés y francés.
- Documentación inicial de GitHub en inglés.
- Capturas ilustrativas añadidas al README.
- Documentos de propuestas futuras frente a SyncMoss y NORMOS.
- Consolidación de las mejoras estadísticas/físicas añadidas en la serie 0.2.x.

## Mejoras estadísticas y de ajuste consolidadas

- Ajuste ponderado con incertidumbre Poisson.
- χ² reducido, AIC y BIC.
- Áreas por integración numérica, válidas para Lorentziana y Voigt.
- Diagnóstico de residuos.
- Resumen de correlaciones de parámetros.
- Autoarranque múltiple determinista.
- Bootstrap Monte Carlo de errores en modelos discretos.
- L-curve ampliada con χ² reducido y tabla exportable.
- Distribuciones P(BHF)/P(ΔEQ) ponderadas.
- Ajuste opcional del folding point.
- Presets físicos de restricciones.
- Trazabilidad de calibración e incertidumbre de Vmax cuando está disponible.

## Documentación

- `README.md`: documentación principal en español.
- `README_EN.md`: documentación inicial en inglés.
- `INSTALL.md`: instalación en español.
- `INSTALL_EN.md`: instalación en inglés.
- `PROPUESTAS_SYNCMOSS.md`: líneas de mejora tras comparar con SyncMoss.
- `PROPUESTAS_NORMOS.md`: líneas de mejora para compatibilidad y validación frente a NORMOS.

## Capturas incluidas

El README muestra capturas de:

- pantalla principal,
- ajuste discreto,
- distribución P(BHF),
- L-curve,
- informe Markdown/PDF.

## Actualización

La release incluye:

- `Mossbauer-v0.3.0.zip`
- `sha256sums.txt`

El ZIP contiene el programa Python, documentación, ayuda, traducciones y recursos necesarios.

## Nota

La traducción completa de toda la interfaz es progresiva: los menús principales y la ventana de ayuda ya están internacionalizados. Queda preparada la infraestructura para seguir moviendo textos internos, diálogos y mensajes al sistema `tr(...)` en versiones futuras.
