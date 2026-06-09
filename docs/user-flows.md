# Flujos de usuario

Esta guía resume los recorridos habituales en la interfaz Qt de Fitbauer.

## 1. Abrir un espectro y simular

1. Iniciar la aplicación:

   ```bash
   python fitbauer.py
   ```

2. Abrir un fichero desde **Archivo → Cargar...** (`.ws5` o `.adt`).
3. Revisar el folding point y `Vmax` en el panel de calibración.
4. Ajustar parámetros de componentes manualmente si se desea.
5. La gráfica se actualiza en modo simulación hasta lanzar un ajuste real.

## 2. Ajuste discreto

1. Elegir modo discreto.
2. Seleccionar número de componentes.
3. Para cada componente:
   - tipo: singlete, doblete o sextete,
   - valores iniciales,
   - parámetros fijados/libres.
4. Opcional: usar **Inicializar desde mínimos** para proponer componentes.
5. Pulsar **Ajuste**.
6. Revisar:
   - χ², χ² reducido, AIC/BIC,
   - diagnóstico de residuos,
   - áreas porcentuales,
   - errores y correlaciones si están disponibles.

## 3. Bootstrap

1. Realizar o preparar un ajuste discreto.
2. Ir a **Herramientas → Bootstrap**.
3. Elegir número de réplicas.
4. El resultado actualiza las incertidumbres y la fuente de error indicada en informes.

## 4. Distribución `P(BHF)` / `P(ΔEQ)`

1. Cambiar el modo a distribución.
2. Elegir variable: `P(BHF)` o `P(ΔEQ)`.
3. Configurar:
   - rango mínimo/máximo,
   - número de bins,
   - `δ`, `ΔEQ`/`BHF` fijo, `Γ`,
   - `log10 α`, forma y regularización.
4. Opcional: usar **L-curve α** para estimar regularización.
5. Opcional: activar **componentes nítidas** para sumar fases discretas al ajuste.
6. Pulsar **Ajuste**.
7. Revisar la curva ajustada, residuo y distribución resultante.

## 5. Calibración

Hay dos rutas:

- **Calibración web**: descargar metadatos desde la API del laboratorio.
- **Calibración local**: usar el fichero actual como calibración desde el menú contextual.

La calibración afecta a trazabilidad, `Vmax` y referencia de desplazamiento isomérico cuando está disponible.

## 6. Guardar sesión

Usar **Archivo → Guardar sesión...** para guardar:

- fichero/cuentas,
- modelo,
- parámetros y fijados,
- opciones de ajuste,
- distribución,
- preferencias visuales relevantes.

La sesión JSON mantiene compatibilidad con formatos históricos.

## 7. Exportar resultados

Opciones principales:

- **Guardar ajuste**: exporta velocidad, datos, modelo y residuo en texto.
- **Exportar Plotly**: figura HTML interactiva.
- **Exportar informe**: Markdown y, si está disponible, PDF.

El informe incluye trazabilidad, calibración, parámetros, áreas, métricas, correlaciones y diagnóstico residual.

## 8. Validaciones y avisos

Antes de ajustar, Fitbauer valida:

- longitudes y finitud de datos,
- límites de parámetros,
- `sigma` positiva,
- rangos de distribución,
- número mínimo de bins,
- tipos de componente y regularización conocidos.

Si hay problemas, la GUI muestra un aviso y no lanza el ajuste.
