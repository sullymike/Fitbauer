# Notas de versión — Fitbauer v4.14.2

Versión de mantenimiento y documentación. Incluye también la corrección previa
v4.14.1 (comprobación de actualizaciones), no publicada por separado.

## Distribución: «Gaussiana» pasa a ser VBF con N=1

La forma **Gaussiana** era un caso particular estricto del **VBF** (una sola
gaussiana). Se unifican ambos caminos: la GUI mantiene la etiqueta «Gaussiana»
(opción amigable), pero internamente ajusta con `VBF (n_components=1,
profile="Lorentz")` conservando `shape="Gaussiana"` en sesiones e informes. Se
elimina la función duplicada; VBF es su generalización (N>1, Voigt, correlación
δ(H)/ΔEQ(H)). Efecto colateral positivo: el ajuste ya no depende del perfil de
línea global ambiente.

## Manual de usuario en inglés

Nuevo árbol `docs/manual_en/` con el manual **completo traducido al inglés**
(capítulos y anexos), figuras de física regeneradas en inglés y `main.pdf`
(76 páginas). Se mantiene en paralelo al manual en español.

## Enlace al manual desde la aplicación

Nueva acción **Ayuda → Manual (PDF)** que abre el manual **en inglés** (única
versión enlazada): usa la copia local `docs/manual_en/main.pdf` si está presente
o, en su defecto, el PDF alojado en GitHub (robusto en ejecutables congelados,
que no empaquetan `docs/`). Etiqueta traducida en los 7 idiomas.

## Anexo matemático del VBF

Nuevo **anexo B** del manual («Ajuste por Voigt (VBF)») con la matemática completa
del método: modelo directo y núcleo, perfil Voigt y la doble lectura del
ensanchamiento, mínimos cuadrados y parametrización, áreas/poblaciones,
correlación δ(H)/ΔEQ(H), el caso N=1 y comparación con el histograma. Ayudas
integradas actualizadas en los 7 idiomas (Gaussiana = VBF con N=1).

## v4.14.1 — comprobar actualizaciones sin caer en el rate-limit (HTTP 403)

La comprobación de actualizaciones usaba solo la API REST de GitHub sin
autenticar (60 peticiones/hora por IP); en redes con IP compartida (NAT) esa cuota
se agotaba y fallaba con **HTTP 403**. Ahora, si la API responde 403 (rate-limit) o
falla la red, se recurre al **feed atom público** (sin ese límite), y la descarga y
verificación SHA-256 siguen funcionando por esa vía. Los errores que no son de
cuota se propagan como antes.

## Notas

- Las capturas de la interfaz del manual en inglés son, de momento, las mismas que
  las del manual en español (las capturas son manuales); las figuras de física/datos
  sí están en inglés.
- Compatibilidad: el ajuste «Gaussiana» produce el mismo resultado que antes.

El detalle por versión está en `CHANGELOG.md`.
