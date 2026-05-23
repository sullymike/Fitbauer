# Propuestas pendientes tras la comparación con NORMOS

Este documento recoge posibles mejoras futuras al comparar el programa con NORMOS. A diferencia de la comparación con SyncMoss, aquí el foco principal no está tanto en añadir modelos nuevos, sino en mejorar la compatibilidad, reproducibilidad y equivalencia numérica con un programa clásico y muy usado en análisis Mössbauer.

## 1. Validación directa contra NORMOS

Ajustar los mismos espectros en NORMOS y en este programa bajo condiciones lo más equivalentes posible.

Aspectos a comparar:

- Desplazamiento isomérico, δ.
- Desdoblamiento cuadrupolar, ΔEQ.
- Campo hiperfino, BHF.
- Anchuras Γ.
- Áreas relativas.
- Residuos.
- χ² o métrica equivalente.
- Distribuciones P(BHF).
- Parámetros de regularización.

Objetivo: cuantificar cuándo ambos programas dan resultados equivalentes y cuándo aparecen diferencias debidas a convenciones, normalización, folding, pesos o regularización.

## 2. Importación más completa de ficheros NORMOS

El programa ya aprovecha algunos ficheros auxiliares de NORMOS, pero podría ampliarse la lectura.

Formatos y contenidos a mejorar:

- `.RES`: resultados finales, errores, parámetros fijos/libres y componentes.
- `.PLT`: eje de velocidades, Vmax, curvas calculadas y datos exportados.
- `.JOB`: configuración del ajuste, modelo y opciones usadas.
- Restricciones o ligaduras entre parámetros.
- Distribuciones hiperfinas exportadas por NORMOS.

Objetivo: poder abrir un análisis NORMOS y reconstruirlo de forma mucho más fiel dentro de esta GUI.

## 3. Exportación compatible con NORMOS

Añadir la posibilidad de guardar resultados o modelos en formatos que NORMOS pueda leer o comparar fácilmente.

Posibles salidas:

- Tabla de datos/modelo/residuo con convención NORMOS.
- Parámetros finales en formato parecido a `.RES`.
- Distribución P(BHF) en tabla compatible.
- Resumen de componentes y áreas.
- Ficheros auxiliares para continuar o reproducir el ajuste.

Objetivo: facilitar la comparación cruzada y permitir continuar un análisis en NORMOS si fuera necesario.

## 4. Reproducción exacta de la metodología Hesse-Rübartsch de NORMOS

El programa ya implementa distribuciones P(BHF)/P(ΔEQ) regularizadas, inspiradas en Hesse-Rübartsch. Para acercarse más a NORMOS habría que validar los detalles numéricos.

Puntos a revisar:

- Definición exacta del término de suavizado.
- Normalización de la distribución.
- Tratamiento de los bordes.
- Número y posición de bins.
- Escalado del parámetro α.
- Pesos estadísticos usados en el residuo.
- Criterio de elección de α.

Objetivo: que una misma distribución ajustada en NORMOS y en esta GUI sea comparable de forma objetiva.

## 5. Ajustes de distribución más clásicos tipo NORMOS

NORMOS es una referencia histórica en distribuciones hiperfinas. Podrían añadirse opciones que imiten más directamente sus variantes de ajuste.

Posibles mejoras:

- Modos de distribución con convenciones NORMOS.
- Suavizados alternativos.
- Regularizaciones configurables.
- Exportación de tablas P(BHF) con columnas equivalentes.
- Opciones de normalización específicas.

Objetivo: ayudar a usuarios acostumbrados a NORMOS a reproducir sus flujos de análisis.

## 6. Tratamiento de áreas y normalización según convención NORMOS

Las áreas relativas pueden diferir entre programas si cambian las convenciones de fondo, profundidad, transmisión o integración.

Trabajo pendiente:

- Documentar cómo calcula áreas NORMOS.
- Compararlo con la integración numérica usada por esta GUI.
- Indicar cuándo los porcentajes deberían coincidir.
- Indicar cuándo pueden diferir por perfil de línea, fondo o normalización.
- Añadir, si procede, un modo de área compatible con NORMOS.

Objetivo: evitar interpretaciones erróneas al comparar porcentajes de fase.

## 7. Compatibilidad exacta con el folding de NORMOS

La GUI muestra un valor de folding point NORMOS aproximado, pero sería útil validar la equivalencia con detalle.

Puntos a comprobar:

- Relación exacta entre centro interno de la GUI y folding point NORMOS.
- Tratamiento de canales pares e impares.
- Uso de centros fraccionarios.
- Interpolación durante el doblado.
- Tratamiento de los canales extremos.
- Influencia del folding en el residuo antisimétrico.

Objetivo: que un folding point procedente de NORMOS pueda usarse directamente sin ambigüedad.

## 8. Reproducción de errores 1σ de NORMOS

Los errores dependen de la matriz de covarianza, del escalado de χ² y de los pesos usados.

Trabajo recomendado:

- Comparar errores 1σ para ajustes discretos simples.
- Comparar matrices de correlación cuando estén disponibles.
- Revisar si NORMOS reescala errores por χ² reducido.
- Revisar diferencias entre pesos Poisson y otros esquemas.
- Documentar las diferencias.

Objetivo: que el usuario sepa si los errores de ambos programas son directamente comparables.

## 9. Restricciones equivalentes a NORMOS

La GUI ya tiene restricciones lineales y presets físicos, pero sería útil mapearlas a las opciones típicas de NORMOS.

Casos a cubrir:

- Parámetros fijos.
- Parámetros ligados entre subespectros.
- Anchuras comunes.
- Intensidades comunes.
- Relaciones lineales entre parámetros.
- Restricciones usadas en distribuciones.

Objetivo: reproducir un ajuste NORMOS sin tener que reconstruir manualmente todas las ligaduras.

## 10. Biblioteca de casos de referencia NORMOS

Crear una colección de espectros y resultados comparativos.

Cada caso debería incluir:

- Espectro original.
- Ficheros NORMOS disponibles (`.RES`, `.PLT`, `.JOB`, etc.).
- Sesión JSON de esta GUI.
- Informe Markdown/PDF generado por esta GUI.
- Tabla comparativa de parámetros.
- Comentario sobre diferencias observadas.

Objetivo: disponer de una suite de validación científica y de ejemplos para usuarios.

## 11. Documentación “cómo pasar de NORMOS a esta GUI”

Crear una guía práctica para usuarios acostumbrados a NORMOS.

Contenido sugerido:

- Cómo cargar `.ws5` o `.adt`.
- Cómo aprovechar ficheros `.RES` y `.PLT`.
- Cómo interpretar el folding point.
- Cómo reproducir componentes discretos.
- Cómo reproducir P(BHF).
- Cómo fijar o ligar parámetros.
- Cómo comparar áreas, errores y residuos.
- Cómo exportar un informe moderno Markdown/PDF.

Objetivo: reducir la barrera de entrada para usuarios de NORMOS.

## 12. Modo de compatibilidad NORMOS

Una mejora avanzada sería añadir una opción de compatibilidad que use convenciones lo más cercanas posible a NORMOS.

Posibles características:

- Folding con convención NORMOS.
- Normalización equivalente.
- Cálculo de áreas estilo NORMOS.
- Pesos y escalado de errores compatibles.
- Exportación de tablas en formato familiar.
- Nombres de parámetros y unidades equivalentes.

Objetivo: facilitar comparaciones directas y reproducibilidad histórica.

---

## Prioridad orientativa

Una posible prioridad de desarrollo sería:

1. Validación directa contra NORMOS.
2. Compatibilidad exacta del folding.
3. Importación más completa de `.RES`, `.PLT` y `.JOB`.
4. Comparación de áreas, errores y normalización.
5. Reproducción detallada de Hesse-Rübartsch.
6. Biblioteca de casos de referencia NORMOS.
7. Guía “cómo pasar de NORMOS a esta GUI”.
8. Exportación compatible con NORMOS.
9. Modo de compatibilidad NORMOS.

La prioridad real dependerá de si se busca principalmente validar resultados antiguos, facilitar migración de usuarios o mantener compatibilidad con flujos NORMOS existentes.
