# Mössbauer Fe-57 GUI v2.0 — release estable

Esta versión consolida el trabajo acumulado de las ramas anteriores en una base estable. Sustituye al historial de releases previas.

## Resumen de novedades

- Arquitectura modular con paquetes `core/`, `layout/` y `panels/`, manteniendo `mossbauer_fe33_gui_v2IA.py` como lanzador principal.
- Ajuste discreto de singletes, dobletes y sextetes con pesos Poisson, autoarranques, métricas χ²/AIC/BIC, áreas integradas, correlaciones y diagnóstico de residuos.
- Distribuciones hiperfinas `P(BHF)` y `P(ΔEQ)` con regularización Hesse-Rübartsch, escaneo L-curve y soporte de componentes nítidos simultáneos.
- Mejoras del motor de distribución: regularización alternativa por variación total, GCV/dof efectivo, condicionamiento del kernel y barras de error 1σ.
- Perfiles Lorentziano y Voigt con normalización consistente.
- Tratamiento avanzado de sextetes: textura de intensidades, tratamiento cuadrupolar de primer orden/Kündig fijo/Kündig polvo, y menús contextuales en intensidades, β y ΔEQ/AEQ.
- Detección automática mejorada de mínimos y propuesta inicial para uno o dos sextetes.
- Calibración: descarga web, calibración local desde fichero cargado, persistencia de metadatos e incertidumbre de Vmax en informes cuando está disponible.
- Interfaz multilingüe español/inglés/francés con ayuda integrada ampliada.
- Exportación de ajuste, sesión JSON reproducible e informe Markdown/PDF.
- Actualizador y empaquetado ZIP de release con assets, datos de ejemplo, checksums SHA-256 y dependencias.

## Correcciones destacadas

- Corrección de la combinación distribución + sextete nítido: las intensidades se convierten correctamente entre la convención NORMOS de la GUI y el motor de distribución, evitando que la contribución del sextete se mezcle al dibujar la distribución.
- El menú contextual de tratamiento cuadrupolar aparece también al pulsar con botón derecho sobre `ΔEQ/AEQ`, no solo sobre `β`.
- Limpieza de ramas antiguas ya incorporadas y consolidación del historial en `main`.

## Compatibilidad

- Formatos de entrada: `.ws5`, `.WS5`, `.adt`, `.ADT`.
- Sesiones JSON anteriores siguen siendo cargables en la medida de lo posible.
- La versión local del programa pasa a ser `2.0`.
