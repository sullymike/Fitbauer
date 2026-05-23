# Propuestas pendientes tras la comparación con SyncMoss

Este documento recoge las 12 líneas de mejora que quedarían pendientes tras la segunda comparación funcional y científica con SyncMoss. No son correcciones urgentes, sino posibles desarrollos futuros para acercar el programa a flujos de análisis más avanzados.

## 1. Validación cuantitativa contra SyncMoss

Tomar un conjunto de espectros reales y ajustarlos tanto en SyncMoss como en este programa, usando condiciones equivalentes. Comparar parámetros hiperfinos, áreas, residuos y métricas estadísticas.

Aspectos a comparar:

- Desplazamiento isomérico, δ.
- Desdoblamiento cuadrupolar, ΔEQ.
- Campo hiperfino, BHF.
- Anchuras Γ.
- Áreas relativas.
- χ² reducido.
- Distribuciones P(BHF) o P(ΔEQ).
- Forma y estructura del residuo.

Objetivo: comprobar hasta qué punto ambos programas producen resultados equivalentes y documentar diferencias esperables.

## 2. Ajuste global de varios espectros simultáneos

Añadir capacidad para ajustar varias medidas a la vez compartiendo parámetros comunes.

Ejemplos de uso:

- Series de temperatura.
- Varias orientaciones de una muestra.
- Medidas repetidas de la misma fase.
- Ajustes donde δ, ΔEQ o BHF evolucionan siguiendo una ley común.

Esto permitiría imponer coherencia física entre espectros y reducir incertidumbres.

## 3. Modelo avanzado de espesor, saturación y autoabsorción

El programa trabaja actualmente con absorciones efectivas normalizadas. Una mejora futura sería incluir modelos físicos más completos de transmisión.

Posibles efectos a incorporar:

- Espesor efectivo de la muestra.
- Saturación resonante.
- Autoabsorción.
- Correcciones por muestra gruesa.
- Influencia del fondo no resonante.

Estos efectos son importantes cuando las áreas relativas no representan directamente fracciones de fase.

## 4. Distribuciones hiperfinas más sofisticadas

Ya existen distribuciones P(BHF) y P(ΔEQ), pero podrían ampliarse a modelos correlacionados.

Posibles extensiones:

- Distribución bidimensional P(BHF, ΔEQ).
- Correlación entre BHF y δ.
- Correlación entre BHF y ΔEQ.
- Distribuciones parametrizadas físicamente.
- Modelos de tamaño de partícula ligados a P(BHF).

Objetivo: representar sistemas desordenados o nanoparticulados con mayor realismo.

## 5. Modelos magnéticos más completos

Los sextetes actuales son modelos efectivos con intensidades ajustables. Se podría avanzar hacia modelos magnéticos explícitos.

Posibles mejoras:

- Ángulo entre el campo hiperfino y la dirección gamma.
- Textura o orientación preferente.
- Campo magnético externo.
- Relajación magnética lenta o intermedia.
- Modelos superparamagnéticos más detallados.

Esto permitiría interpretar mejor muestras orientadas, con campo aplicado o con dinámica magnética.

## 6. Estimación bayesiana y MCMC

El bootstrap Monte Carlo ya proporciona una estimación más robusta que la covarianza local, pero no equivale a una inferencia bayesiana completa.

Posibles desarrollos:

- Muestreo MCMC de parámetros.
- Distribuciones posteriores.
- Intervalos creíbles.
- Priors físicos sobre δ, ΔEQ, BHF o Γ.
- Comparación bayesiana de modelos.

Objetivo: cuantificar incertidumbres y degeneraciones de forma más completa.

## 7. Comparación automática de modelos

El programa ya calcula χ² reducido, AIC y BIC, pero la comparación entre modelos sigue siendo manual.

Mejora propuesta:

- Ventana específica de comparación de modelos.
- Tabla con modelos candidatos.
- Métricas homogéneas para todos los modelos.
- Penalización por número de parámetros.
- Recomendación orientativa del modelo más parsimonioso.

Modelos típicos a comparar:

- Un doblete.
- Dos dobletes.
- Sextete + doblete.
- Varios sextetes.
- Distribución P(BHF).
- Distribución P(ΔEQ).

## 8. Motor de restricciones más avanzado

Actualmente existen restricciones lineales y presets físicos. Podría ampliarse el sistema de restricciones para casos más complejos.

Posibles mejoras:

- Grupos de parámetros compartidos.
- Restricciones no lineales.
- Relaciones dependientes de temperatura.
- Parámetros comunes entre espectros en ajustes globales.
- Editor visual de ligaduras.

Esto ayudaría a construir modelos físicos sin introducir demasiados parámetros libres.

## 9. Más formatos de compatibilidad

El programa ya lee formatos locales y ficheros auxiliares, pero podría mejorar su interoperabilidad con otros programas.

Posibles ampliaciones:

- Importación de proyectos o resultados de SyncMoss.
- Exportación compatible con SyncMoss.
- Lectura más completa de ficheros Normos.
- Compatibilidad con formatos de otros laboratorios.
- Exportación de modelos de ajuste reutilizables.

Objetivo: facilitar la comparación y migración entre programas.

## 10. Informe científico más completo

Ya existe exportación Markdown/PDF. Una evolución futura sería ampliar el informe con anexos científicos más detallados.

Posibles contenidos adicionales:

- Tabla comparativa de modelos.
- Figura de residuos normalizados.
- Matriz de correlación completa.
- Tabla de resultados bootstrap.
- Anexo con P(BHF) o P(ΔEQ).
- Trazabilidad completa de calibración.
- Resumen de parámetros fijos, libres y restringidos.

Objetivo: que el informe sea directamente utilizable como documentación de análisis.

## 11. Pruebas automáticas y suite de regresión

Para mejorar la robustez del programa sería conveniente crear una colección de espectros de referencia y pruebas automáticas.

Elementos recomendados:

- Espectros sintéticos con parámetros conocidos.
- Espectros reales de referencia.
- Tests de ajuste discreto.
- Tests de P(BHF) y P(ΔEQ).
- Tests de exportación de informes.
- Comprobación de que nuevas versiones reproducen resultados anteriores.

Esto evitaría regresiones al añadir nuevas funciones.

## 12. Documentación comparativa frente a SyncMoss

Añadir una sección específica que explique cómo comparar este programa con SyncMoss.

Contenido sugerido:

- Qué resultados deberían coincidir.
- Qué resultados pueden diferir por implementación.
- Cómo igualar condiciones iniciales.
- Cómo comparar áreas y anchuras.
- Cómo comparar P(BHF) y regularización.
- Diferencias entre criterios RMS, χ² reducido, AIC y BIC.

Objetivo: ayudar al usuario a interpretar diferencias sin confundirlas con errores del programa.

---

## Prioridad orientativa

Una posible prioridad de desarrollo sería:

1. Validación cuantitativa contra SyncMoss.
2. Comparación automática de modelos.
3. Informe científico ampliado.
4. Pruebas automáticas y suite de regresión.
5. Documentación comparativa frente a SyncMoss.
6. Distribuciones correlacionadas y modelos físicos avanzados.
7. Ajuste global multiespectro.
8. Correcciones de espesor/saturación.
9. MCMC bayesiano.

La prioridad real dependerá de si el objetivo principal es robustez científica, publicación de resultados, compatibilidad externa o ampliación física del modelo.
