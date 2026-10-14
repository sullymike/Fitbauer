# Fitbauer v5.2.1

*[🇬🇧 English notes](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.2.1.md)*

Una versión para entender un ajuste de distribución: informes que cuentan la
distribución que se ajustó de verdad, exportación de sus datos, una forma de
Czjzek para la P(ΔEQ) de sólidos desordenados y una matriz de correlación en
colores que enseña de un vistazo qué parámetros se compensan entre sí.

---

## Informes y datos de las distribuciones

- **Los informes cuentan el ajuste de distribución.** En modo distribución, el
  informe completo y el reducido (Markdown y PDF) mostraban el componente
  discreto de los paneles (un sextete que no formaba parte del ajuste), el RMS
  del modelo discreto y la figura del espectro, y nada más. Ahora recogen:
  - el montaje (modo, forma, regularizador, α, malla);
  - la bondad del ajuste: N, χ², k, ν = N − k, χ² reducido, AIC, BIC y RMS,
    más la autocorrelación lag-1 y el test de rachas del residuo. AIC y BIC
    tienen la misma definición que en el ajuste discreto, así que se puede
    comparar una distribución con un modelo discreto del mismo espectro;
  - los parámetros globales (δ, ΔEQ, Γ, κ) con su σ y si se refinaron;
  - la distribución: media, anchura y moda de P, las gaussianas del VBF/2D o
    los parámetros de la binomial;
  - los componentes nítidos con su profundidad ajustada y los avisos (también
    el peso acumulado en el borde de la malla, que se calculaba pero no se
    mostraba en ningún sitio).

  El PDF añade la figura de P(x) con su banda, o el mapa del ajuste 2D actual.
- **Exportar la distribución.** Un botón **Guardar datos…** en los diálogos de
  P(x) y del mapa 2D, y **Archivo → Exportar distribución…**, escriben un
  fichero separado por tabuladores: variable, P normalizada, σ de P, peso y,
  con pendientes κ, la curva δ(x)/ΔEQ(x) con su σ; en 2D, una fila por celda.
  La cabecera resume el ajuste.
- **Guardar ajuste…** en modo distribución exportaba el modelo discreto de los
  paneles. Ahora exporta el modelo de la distribución y el mapa 2D completo.

## Forma de Czjzek para P(ΔEQ)

Dos formas paramétricas nuevas para la distribución de |ΔEQ| de vidrios y
materiales amorfos, que solo se ofrecen en P(ΔEQ) con dobletes:

- **Czjzek**: gradiente de campo eléctrico aleatorio (Czjzek et al. 1981).
  ΔEQ/σ sigue una χ de 5 grados de libertad, P ∝ ΔEQ⁴·exp(−ΔEQ²/2σ²):
  asimétrica, cero en el origen, moda en 2σ.
- **Czjzek extendido** (Le Caër–Brand 1998): desorden aleatorio sobre un
  entorno ordenado ΔEQ₀ (χ no central de 5 grados de libertad). Tiende a una
  gaussiana cuando ΔEQ₀ ≫ σ.

σ y ΔEQ₀ salen con su error; admiten la correlación κδ y componentes nítidos,
y están en el CLI (`--shape czjzek` / `czjzek-ext`). Compáralas con la
Gaussiana o el histograma mediante el AIC/BIC.

## Correlaciones de un vistazo

- **Matriz de correlación en colores.** El panel *Estado y parámetros* muestra
  la matriz de correlación como tabla: filas y columnas son los parámetros,
  rojo si la correlación es positiva y azul si es negativa, más intenso cuanto
  mayor |r|, en negrita si |r| ≥ 0.95 (el ajuste no los separa). El informe
  lleva la misma matriz y el PDF, un mapa de calor.
- **Ajustes discretos**: todos los parámetros libres, ahora también vmax, el
  centro y σ Voigt cuando se ajustan.
- **Ajustes de distribución**: los globales refinados (δ, ΔEQ, Γ, κ) frente a
  la **media y la anchura de P**, que llevan ahora un error que incluye el de
  los globales. Responde directamente si la anchura de la distribución se está
  compensando con Γ. Se ha comprobado contra el ajuste conjunto de todos los
  parámetros (σ_P–Γ: −0.93 frente a −0.94).
- El panel las rotula «media de P» y «anchura de P», y muestra la σ de cada
  gaussiana junto a su μ.

## Avisos

- **P(ΔEQ) con dobletes y Γ libre** tiene ahora el mismo aviso que P(IS): la
  distribución ensancha las dos líneas igual que Γ (correlación σ–Γ de −0.90 a
  −0.95 en espectros sintéticos). Fija Γ a la anchura instrumental.
- **Absorbente grueso.** Con *Absorbente* en grueso o integral de transmisión,
  el ajuste de distribución suponía en silencio un absorbente delgado. El panel
  lo avisa ahora.

Cada aviso enlaza a su sección de la ayuda.

## Correcciones

- **Errores inestables de los globales de las distribuciones.** La covarianza
  de δ, ΔEQ, Γ y κ salía de una jacobiana con paso ~1e-8, donde manda la
  tolerancia del ajuste interno de P: la derivada respecto a Γ cambiaba ×3.6
  entre ajustes casi idénticos. Ahora se recalcula por diferencias centradas
  con un paso razonable. **Cambian las σ de los globales.**
- En modo distribución, el panel de estado ponía el RMS como «χ² reducido» y
  dof, AIC y BIC a 0, también en el historial de ajustes.
- El diagnóstico del residuo del ajuste discreto (lag-1, test de rachas) no se
  calculaba nunca: el panel daba `nan` y la sección del informe no salía. Se
  retira la «correlación antisimétrica», que no estaba bien definida.
- El japonés y el chino salían como cuadros vacíos en los gráficos y en los
  informes PDF; ahora se usa como respaldo una fuente CJK instalada. El estilo
  de gráfico guardado se aplica también al arrancar.
- El informe de P(ΔEQ)/P(IS) rotulaba la malla como «(BHF)».

## Documentación

- La ayuda (ocho idiomas), los dos manuales, `BHF_DISTRIBUTION.md`, el README
  y la wiki recogen todo lo anterior.
- La ayuda y el manual describían el diálogo de la L-curve de la interfaz
  antigua (GCV, un valor de «compromiso», una L-surface para 2D): ahora
  describen lo que hace el diálogo. El anexo de espesor ya no describe una
  corrección en modo distribución que no existe.

---

Suite completa: **728 tests en verde**.
