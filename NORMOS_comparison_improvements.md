# Diferencias NORMOS SITE/DIST vs GUI y mejoras implementadas

Basado en `sitedistmanual.pdf-ocr.pdf`.

## 1. FWHM equivalente además de HWHM

Normos usa `WID` como FWHM. La GUI usa `Γ` como HWHM. Mejora pendiente/implementada parcialmente: mostrar de forma explícita `FWHM = 2Γ` en informes y ayuda para evitar confusión al comparar con `.RES`.

## 2. Restricciones lineales

Normos permite `PAR(i)=FACTOR*PAR(j)+CONST` mediante `NDEX`, `FACTOR`, `CONST`. La GUI ya incorpora restricciones lineales desde **Opciones → Restricciones entre parámetros...**.

Mejoras añadidas:
- Validación de ciclos.
- Aviso si el parámetro origen está fijado.
- El destino se marca fijo automáticamente.
- Las restricciones aparecen en Estado y parámetros y se guardan en sesiones/opciones.

## 3. Perfil de línea Lorentziana/Voigt

Normos contempla perfiles Voigt en algunos casos. La GUI incorpora selección básica de perfil:

- Lorentziana.
- Voigt con `σ gauss Voigt`.

Nota: la distribución P(BHF) usa todavía el motor de distribución original; el Voigt se aplica al modelo discreto de la GUI.

## 4. Distribución P(ΔEQ)

Normos/DIST contempla distribuciones cuadrupolares. En la GUI actual sigue pendiente como desarrollo mayor: habría que construir un kernel equivalente a P(BHF), pero barriendo ΔEQ.

## 5. Distribuciones gaussianas paramétricas

Normos permite distribuciones gaussianas/binomiales/fijas. En la GUI actual sigue pendiente como modo adicional: ajustar centro, sigma y área de una o varias gaussianas de BHF.

## 6. Múltiples distribuciones P(BHF)

Normos permite varios bloques de distribución. En la GUI actual sigue pendiente como ampliación mayor: varias distribuciones con rangos/parámetros independientes y parámetros compartidos.

## 7. Informe completo del ajuste

La GUI ya guarda ajuste y sesión completa. Mejora recomendada: un informe específico en texto/Markdown con modelo, parámetros, errores, restricciones, porcentajes, folding, perfil de línea y opciones P(BHF).

## 8. Importación/Folding más flexible

Normos admite `VORMAT`, `NLTEXT`, `V1`, `DELV`, `NADD`, etc. La GUI ya lee WS5 y ADT y usa folding fraccionario. Pendiente: diálogo de importación avanzada con cabeceras arbitrarias, suma de espectros y eje definido por V1/DELV.
