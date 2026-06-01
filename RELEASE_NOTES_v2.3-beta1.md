# Mossbauer v2.3-beta1 — prerelease no estable

Esta es una versión **no estable / beta** para probar los cambios posteriores a v2.2 antes de promoverlos a una release estable. Se recomienda a usuarios que quieran validar compatibilidad con NORMOS, revisar la nueva gestión de velocidad y probar la interfaz actualizada.

## Cambios principales

### Compatibilidad NORMOS y eje de velocidades

- `Vmax` acepta valores negativos y conserva el signo en GUI, CLI y calibraciones web.
- El recorte interno del primer y último punto doblado conserva correctamente la escala física: se recorta también el eje de velocidades original en lugar de reconstruirlo a `±Vmax` con menos puntos.
- Esto evita el estiramiento artificial del eje y reduce sesgos sistemáticos en `BHF`.
- Intensidades de sextete alineadas con la convención NORMOS: `int3` queda oculto/fijo a `1`, `int1≈D13`, `int2≈D23` y `DEP/profundidad` actúa como escala global.

### GUI y usabilidad

- Barra de profundidad limitada visualmente a `0–0.07` para facilitar el modelado manual fino, manteniendo un límite interno más amplio en el ajuste.
- Valores iniciales ajustados: profundidad del componente 1 = `0.02` y `Γ = 0.15 mm/s`.
- Clic derecho sobre el control de `σ` para alternar rápidamente entre Lorentziana y Voigt.
- Icono de aplicación PNG/ICO para el gestor de ventanas y Alt-Tab.
- Botones del diálogo de actualización con padding reducido para que el texto se vea mejor.

### Documentación y ejemplos

- Ayuda integrada ampliada en español, inglés y francés con explicación detallada de `Vmax` firmado y del recorte correcto del eje de velocidades.
- README actualizado con la convención de velocidades y de intensidades tipo NORMOS.
- Informe de ejemplo Markdown/PDF para `Fe3O4` incluido en `data_sample/`.

## Nota de estabilidad

Esta release está marcada como prerelease en GitHub. Solo aparecerá en el actualizador si en:

```text
Ayuda → Configurar actualizaciones
```

se selecciona el canal:

```text
Estables y versiones no estables/beta
```
