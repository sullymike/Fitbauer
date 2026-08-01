# Plan de validación de Fitbauer contra NORMOS-SITE

**Propósito.** Instrucciones para un agente con acceso por línea de comandos a NORMOS (SITE.EXE y auxiliares) y a Fitbauer. **El entorno de trabajo es Linux: SITE.EXE es un ejecutable DOS y se corre bajo DOSBox** (ver sección 0-bis con la receta concreta); Fitbauer se ejecuta nativo. Objetivo: generar con NORMOS-SITE un banco de espectros Mössbauer sintéticos que cubra *todas* las capacidades de SITE mediante **series paramétricas** (barridos y rejillas, no casos sueltos), y ajustarlos con Fitbauer para validarlo. NORMOS actúa como generador de la verdad de referencia (round-trip: NORMOS simula → Fitbauer ajusta → comparación con los parámetros verdaderos). El banco resultante ronda los **300 espectros base + ~150 réplicas de ruido (≈450 en total)**; todo debe generarse por script, nunca a mano, de modo que sea regenerable y ampliable.

Este documento no sustituye al manual de NORMOS: es la hoja de ruta. Ante cualquier duda sobre códigos de modelo o límites, la fuente de verdad es el manual instalado y la salida del propio programa.

---

## 0. Verificaciones previas (obligatorias antes de generar nada)

1. **Inventariar la instalación de NORMOS**: versión (NORMOS-90 u otra), ejecutables (`SITE.EXE`, `DIST.EXE`, utilidades de plegado/calibración tipo `FOLD`, `READMCS`, `DASUM` si existen) y el manual (User's Guide, R.A. Brand). Del manual, **extraer la lista exacta de "theories"/códigos de modelo de SITE, el número máximo de subespectros y de parámetros, y los formatos de entrada/salida**. Los códigos numéricos varían entre versiones: no fiarse de memoria ni de este documento.
2. **Mecanismo de ejecución**: el entorno es Linux y SITE.EXE se corre **bajo DOSBox**. Seguir la receta de la sección 0-bis y validarla con un caso trivial antes de nada. SITE es interactivo o dirigido por fichero de control (`.INP`/`.PAR`); la automatización se hace redirigiendo las respuestas (`SITE < RESP.TXT`) dentro del autoexec de DOSBox.
3. **Mecanismo de simulación**: vía estándar = ejecutar SITE con **todos los parámetros fijados y 0 iteraciones** sobre un fichero dummy de cuentas constantes; SITE escribe la curva teórica en `.FIT`/`.OUT`. Verificarlo con un singlete trivial antes de producir nada en serie.
4. **Inventariar Fitbauer**: formatos de entrada, modelos disponibles, convenciones, invocación CLI, salidas (parámetros, incertidumbres, χ², correlaciones si las da).
5. **Fijar y documentar convenciones** (fuente clásica de falsos desacuerdos entre programas):
   - ε vs 2ε en sextetos y su signo (en SITE, líneas 1,6 → +ε; 2–5 → −ε; confirmarlo empíricamente con un caso de signo conocido).
   - Referencia de δ (α-Fe a temperatura ambiente).
   - Γ como FWHM.
   - Sentido del eje de velocidades y calibración.
   - Conversión Bhf: 33.0 T ↔ líneas externas de α-Fe en ±5.31 mm/s.
   - Convenio de área/profundidad.
6. **Test de signo y convención** (mini-serie previa, 4 espectros): doblete con δ>0; sexteto con ε>0; sexteto con ε<0; singlete con δ<0. Ajustarlos en Fitbauer y resolver cualquier discrepancia de convención **antes** de lanzar el banco completo.

---

## 0-bis. Ejecución de SITE bajo DOSBox en Linux (receta)

SITE.EXE es un programa DOS: en Linux se ejecuta con DOSBox (o DOSBox Staging / dosbox-x, cualquiera vale; usar el que esté instalado y anotarlo). Puntos concretos:

**Invocación por espectro.** Un lanzamiento de DOSBox por espectro, controlado por un fichero de configuración con sección `[autoexec]` y `-exit` para que DOSBox se cierre solo:

```
dosbox -conf site.conf
```

`site.conf` mínimo (generado por script para cada espectro, cambiando la ruta montada):

```
[cpu]
core=dynamic
cycles=max

[autoexec]
mount c /ruta/absoluta/al/dir/de/trabajo
c:
SITE.EXE < RESP.TXT > CONSOLA.LOG
exit
```

**Sin entorno gráfico.** Si la máquina no tiene X o la ventana estorba en ejecución masiva, lanzar con `SDL_VIDEODRIVER=dummy dosbox -conf site.conf` o, si eso falla con la versión instalada, `xvfb-run -a dosbox -conf site.conf`. Probar ambas y quedarse con la que funcione.

**Redirección de respuestas.** El shell de DOSBox admite `<` y `>`. `RESP.TXT` contiene, línea a línea, exactamente las respuestas que SITE pide interactivamente (nombres de fichero, theory, valores, flags de fijado, nº de iteraciones = 0, etc.). Verificar el orden de preguntas ejecutando SITE una vez a mano y transcribiendo la sesión; a partir de ahí el script generador produce `RESP.TXT` para cada caso. Guardar siempre `CONSOLA.LOG` como parte del archivo del caso.

**Nombres 8.3 obligatorios.** Dentro del directorio montado, todos los ficheros que SITE toque deben tener nombre DOS válido (≤8 caracteres + extensión de 3, sin espacios; mejor todo en mayúsculas): `DUMMY.DAT`, `SITE.INP`, `RESP.TXT`, `V0.FIT`, `SALIDA.OUT`. Los nombres largos del lado Linux aparecen truncados/mutilados dentro de DOSBox y rompen la automatización. La convención es: **el nombre largo y descriptivo va en el directorio Linux del caso; los ficheros dentro usan nombres 8.3 genéricos y fijos**, idénticos en todos los casos (facilita además el parseo).

**Finales de línea.** Los ficheros de texto que SITE lee (`RESP.TXT`, `SITE.INP`, datos) deben ir en CRLF y ASCII puro (sin UTF-8 con acentos): pasar `unix2dos` (o equivalente en el script) tras generarlos. Fortran/DOS antiguos son quisquillosos con esto y con tabuladores: usar solo espacios.

**Copia de SITE.EXE.** O bien se copia `SITE.EXE` (y los ficheros auxiliares que necesite) a cada directorio de trabajo, o se monta un segundo directorio común como `D:` y se invoca `D:\SITE.EXE`. Lo primero es más simple y robusto; el coste en disco es despreciable.

**Rendimiento y paralelización.** El arranque de DOSBox añade ~1 s por espectro; para ~450 espectros es asumible en serie. Si hiciera falta acelerar: (a) agrupar varios casos en un `LOTE.BAT` dentro de un mismo autoexec, o (b) lanzar varios DOSBox en paralelo, cada uno con su directorio montado (no compartir directorio de trabajo entre instancias).

**Verificación de la receta (hacerla la primera):** montar un directorio con un dummy plano, correr el singlete trivial del paso 0.3 vía `RESP.TXT`, comprobar que (1) DOSBox se cierra solo, (2) aparece el fichero de salida con la curva teórica, (3) el parseo Linux lo lee bien, y (4) repetir la ejecución produce salida idéntica (determinismo). Solo entonces lanzar series.

---

## 1. Metodología de generación (común a todas las series)

Para cada espectro de cada serie:

1. Dummy de N canales con cuentas constantes (10⁶ salvo indicación).
2. Entrada de SITE con el modelo, parámetros verdaderos **fijados**, 0 iteraciones.
3. Ejecutar SITE, extraer curva teórica.
4. Dos versiones:
   - **v0 (sin ruido)**: curva teórica tal cual → valida la implementación matemática de Fitbauer (recuperación casi exacta; un sesgo sistemático delata diferencia de modelo o convención, no estadística).
   - **v1 (ruido Poisson)**: script auxiliar con semilla registrada → valida estadística e incertidumbres.
5. Archivar por espectro: dummy, entrada de SITE, salida completa de SITE, v0, v1, `verdad.json`.
6. Ajustar v0 y v1 con Fitbauer desde valores iniciales **perturbados** (±10–20 %, posiciones desplazadas), guardar salida completa.
7. Volcar a `resumen.csv`.

Valores por defecto: 512 canales, ±10 mm/s (±4 mm/s en series puramente paramagnéticas), base 10⁶, Γ = 0.25 mm/s, absorción 2–10 %. Cada serie define sus barridos; **los valores no barridos se quedan en el defecto**.

---

## 2. Matriz de series (identificador `Bloque.Serie`, espectros generados por script a partir de la rejilla)

Si la versión instalada de SITE ofrece capacidades no listadas (verlas en 0.1), **añadir series análogas para ellas**: la regla general es *una serie de barrido por cada parámetro del modelo y una rejilla por cada pareja de parámetros correlacionados*.

### Bloque A — Modelos de interacción hiperfina

| Serie | Contenido y rejilla | Nº |
|---|---|---|
| A1a | Singletes, barrido δ ∈ {−2, −1, −0.44, −0.09, 0, 0.26, 0.5, 1, 2} mm/s | 9 |
| A1b | Singletes, barrido Γ ∈ {0.19, 0.22, 0.25, 0.30, 0.40, 0.60, 1.00} mm/s (0.19 ≈ ancho natural ×2) | 7 |
| A1c | Singletes, barrido profundidad ∈ {0.5, 2, 5, 10, 20} % | 5 |
| A2 | Dobletes, rejilla completa δ ∈ {0, 0.37, 0.7, 1.12, 1.3} × ΔEQ ∈ {0.15, 0.30, 0.50, 0.70, 1.00, 1.50, 2.00, 2.65, 3.50} (incluye ΔEQ<Γ: doblete no resuelto) | 45 |
| A3a | Sextetos 1er orden, barrido Bhf ∈ {2, 5, 10, 15, 20, 26, 33, 40, 45, 49, 51.7, 55} T, ε = 0 | 12 |
| A3b | Sextetos, barrido ε ∈ {−0.30, −0.20, −0.10, −0.05, +0.05, +0.10, +0.20, +0.30} mm/s, Bhf = 33 | 8 |
| A3c | Sextetos, barrido δ ∈ {0, 0.37, 0.66, 1.0} con Bhf = 46 | 4 |
| A4 | **Hamiltoniano estático completo, EFG axial (η=0)**: rejilla régimen R = interacción cuadrupolar/magnética ∈ {0.1, 0.5, 1, 2, 10} × θ ∈ {0, 15, 30, 54.7, 75, 90}° (definir R con las constantes exactas del manual) | 30 |
| A5 | Hamiltoniano completo, EFG no axial: rejilla η ∈ {0.2, 0.4, 0.6, 0.8, 1.0} × θ ∈ {0, 54.7, 90}° × φ ∈ {0, 45, 90}° con R = 1 | 45 |
| A6 | Contraste 1er orden vs Hamiltoniano completo: 10 pares con idéntico (δ, Bhf, ΔEQ, θ) generados con ambos modos de SITE, R creciente de 0.05 a 2 → mapa de validez del 1er orden; Fitbauer debe reproducir ambos motores | 20 |
| A7 | Líneas Lorentzianas libres/independientes (theory de líneas sueltas, si existe): configuraciones de 1, 2, 3, 5 y 8 líneas con posiciones, anchuras e intensidades arbitrarias, incluyendo dos parcialmente solapadas | 5 |

### Bloque B — Intensidades relativas y textura

| Serie | Contenido y rejilla | Nº |
|---|---|---|
| B1 | Sexteto (Bhf=33), barrido de textura x = intensidad relativa 2,5/3,4 ∈ {0, 0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0} (x=0: B∥γ; x=2: polvo; x=4: B⊥γ) | 10 |
| B2 | Dobletes con asimetría de líneas (si SITE lo permite): ratio ∈ {0.6, 0.8, 1.0, 1.25, 1.67} | 5 |
| B3 | Textura combinada con Hamiltoniano completo (2 casos de A5 + textura) | 2 |

### Bloque C — Anchuras de línea

| Serie | Contenido | Nº |
|---|---|---|
| C1 | Sexteto con Γ común acoplada: Γ ∈ {0.22, 0.30, 0.45} | 3 |
| C2 | Anchuras por pares Γ16>Γ25>Γ34: gradiente suave (0.32/0.28/0.25) y fuerte (0.60/0.40/0.28), en Bhf = 33 y 46 | 4 |
| C3 | Anchuras totalmente libres línea a línea: 3 configuraciones (una asimétrica izquierda/derecha) | 3 |
| C4 | Γ comparable al paso de canal (Γ = 1× y 2× la anchura de canal): submuestreo | 2 |

### Bloque D — Multisitio y ligaduras

| Serie | Contenido y rejilla | Nº |
|---|---|---|
| D1 | Escalado en nº de sitios: 2, 3, 4, 5, 6, 8, 10, 12, 14 y **N_max de SITE** subespectros distinguibles (mezclas variadas de singletes/dobletes/sextetos) | 10 |
| D2 | Solapamiento de 2 sextetos: ΔBhf ∈ {0.5, 1, 2, 3, 5, 8} T alrededor de 47 T, áreas 1:1.9 (magnetita como referencia en ΔB=3) | 6 |
| D3 | Fase minoritaria: área ∈ {1, 2, 3, 5, 10, 20} % de doblete junto a sexteto mayoritario | 6 |
| D4 | Mezclas tipo muestra real: sext+dob; sext+dob+sing; 2 sext+2 dob; 3 sext+dob (tipo suelo: hematita+goethita+magnetita+Fe³⁺); sext(HC completo)+dob; dob Fe²⁺+dob Fe³⁺+sing; 2 sext solapados+dob débil; N_max/2 sitios mitad magnéticos | 8 |
| D5 | Ligaduras de SITE: Γ común entre sitios; áreas en relación fija (p.ej. 2:1 impuesto); δ ligados; ΔEQ ligados; combinación de varias; y el mismo espectro sin ligaduras (control). Comprobar si Fitbauer tiene equivalentes y qué pasa si no | 6 |
| D6 | Dobletes casi degenerados: mismo δ, ΔΔEQ ∈ {0.05, 0.10, 0.20, 0.30} mm/s → mal condicionamiento; comparar incertidumbres y correlaciones reportadas | 4 |

### Bloque E — Línea base, discretización y adquisición

| Serie | Contenido y rejilla | Nº |
|---|---|---|
| E1 | Nº de canales ∈ {128, 256, 512, 1024} con el mismo doblete y el mismo sexteto | 8 |
| E2 | Rango de velocidad ∈ {±2 (doblete), ±4 (doblete), ±6, ±10, ±12, ±15} mm/s | 6 |
| E3 | Línea base no plana (si SITE la modela): parabólica leve/media/fuerte + inclinada | 4 |
| E4 | Espectro especular sin plegar (1024 canales) y su versión plegada con la utilidad de NORMOS, para un doblete y un sexteto | 4 |
| E5 | Líneas cortadas por el borde del rango: sexteto de 51.7 T en ±9 mm/s; doblete de 3.5 en ±4 mm/s; sitio parcialmente fuera | 3 |

### Bloque F — Espesor / integral de transmisión (si la versión lo incluye)

| Serie | Contenido y rejilla | Nº |
|---|---|---|
| F1 | Singlete con espesor efectivo t_a ∈ {0.1, 0.25, 0.5, 1, 2, 5, 10, 20} | 8 |
| F2 | Sexteto y doblete con t_a ∈ {1, 5, 10} | 6 |
| F3 | Control de sesgo: los espectros de F1 con t_a ∈ {1, 5, 10} ajustados también en aproximación fina (cuantifica el error de ignorar espesor; referencia para Fitbauer) | 3 ajustes |

### Bloque G — Isótopos distintos de ⁵⁷Fe

| Serie | Contenido | Nº |
|---|---|---|
| G1 | ¹¹⁹Sn: singlete; dobletes ΔEQ ∈ {0.5, 1.0, 2.0}; sexteto magnético; Hamiltoniano completo | 6 |
| G2 | Cada isótopo adicional que soporte la versión instalada (consultar manual): al menos singlete + caso con estructura | ≥4 |

### Bloque H — Estadística y ruido (transversal)

| Serie | Contenido | Nº |
|---|---|---|
| H1 | 8 espectros representativos (elegir de A2, A3a, A4, B1, D2, D3, D4, F1) regenerados con base ∈ {10⁴, 10⁵, 10⁶, 3·10⁶} | 32 |
| H2 | Absorción débil (~0.5 %) con base 10⁵ y 10⁶, para un doblete y un sexteto | 4 |
| H3 | **Test de cobertura**: 50 réplicas de ruido (semillas distintas) para 3 casos (un doblete, un sexteto, una mezcla D4) → la dispersión de los parámetros ajustados debe ser compatible con las σ que reporta Fitbauer (~68 % dentro de ±1σ) | 150 |

### Bloque I — Casos adversarios y de robustez

| Serie | Contenido | Nº |
|---|---|---|
| I1 | Absorción muy fuerte (30–50 %): régimen donde la aproximación fina falla visiblemente | 2 |
| I2 | Γ enorme (1.5–3 mm/s): componentes que se funden en una banda ancha | 2 |
| I3 | Protocolo de valores iniciales: un mismo espectro (mezcla D4) ajustado desde 5 semillas iniciales progresivamente peores → estabilidad/convergencia de Fitbauer | 5 ajustes |
| I4 | Señal en el límite de detección: absorción 0.2 % con base 10⁵ | 1 |
| I5 | Parámetros en frontera: δ en el borde del rango, Bhf tal que las líneas 1 y 6 caen en los canales extremos | 2 |

### Bloque J — (Opcional) DIST

Solo si `DIST.EXE` está disponible y Fitbauer implementa (o va a implementar) distribuciones: gaussiana de Bhf (⟨B⟩, σ barridos: 3×3), bimodal, distribución de ΔEQ, correlación lineal δ–Bhf, parámetro de suavizado en 3 valores. ≈ 15 espectros. Documentar el formato de histograma de DIST.

**Total orientativo: ≈ 300 espectros base (v0+v1 cada uno) + ≈ 150 réplicas H3 ≈ 450 espectros / ≈ 750 ajustes.** El número exacto lo fija el script generador; lo importante es que las rejillas de arriba se respeten o amplíen, nunca se recorten sin justificarlo en el informe.

---

## 3. Estructura y registro

```
validacion/
  A2/
    A2_d0.37_q0.70/            <- nombre largo descriptivo, lado Linux
      DUMMY.DAT  SITE.INP  RESP.TXT  CONSOLA.LOG  SALIDA.OUT  V0.FIT   <- nombres 8.3 fijos (los toca DOSBox)
      site.conf  v0.dat  v1.dat  verdad.json  fitbauer_v0.out  fitbauer_v1.out  <- solo lado Linux
    ...
  resumen.csv
  generador/   (todos los scripts: rejillas, entradas SITE y RESP.TXT, site.conf, ruido, lanzador DOSBox, lanzador de Fitbauer, parseo)
```

Los ficheros que DOSBox/SITE tocan llevan **el mismo nombre 8.3 en todos los casos**; la identidad del caso vive en el nombre del directorio y en `verdad.json`. `v0.dat`/`v1.dat` son la conversión a formato de Fitbauer del contenido de `V0.FIT` (más ruido en v1) y se generan en Linux.

`verdad.json` por espectro: theory de SITE, parámetros verdaderos con unidades, convenciones, canales, rango, base, semilla, versión de NORMOS. `resumen.csv`: fila por (espectro, versión, parámetro): verdadero, ajustado, σ, z = (ajustado−verdadero)/σ, χ²_red, convergencia sí/no, tiempo de ajuste.

---

## 4. Criterios de aceptación

1. **v0**: |Δ| < 0.001 mm/s en posiciones/anchuras, < 0.05 T en Bhf, < 0.5 % en áreas. Sesgos sistemáticos → investigar convención/modelo antes de continuar (empezar por ε y Γ).
2. **v1**: |z| < 3 por parámetro; en H3, ~68 % dentro de ±1σ y ~95 % dentro de ±2σ.
3. χ²_red ≈ 1 en v1 (0.8–1.2 con base 10⁶).
4. Residuos sin estructura.
5. Áreas relativas en multisitio dentro de 2σ; en D3, detectar la minoritaria hasta el % donde el ruido lo permita y reportar ese umbral.
6. En A6, Fitbauer debe reproducir ambos motores y el informe debe incluir el mapa de validez del 1er orden.
7. Lista explícita de capacidades de SITE que Fitbauer **no** cubre aún (Hamiltoniano completo, transmisión, ligaduras, isótopos…): es un resultado del ejercicio y hoja de ruta de desarrollo, no un fallo.

---

## 5. Orden de trabajo

1. Paso 0 completo: primero la verificación de la receta DOSBox (0-bis, último punto), después la mini-serie de convenciones (0.6), todo verificado en v0.
2. Bloques A y B en v0 → resolver discrepancias de modelo/convención.
3. Bloques C–G en v0.
4. Versiones v1 de todo + bloques H e I.
5. (Opcional) Bloque J.
6. Informe final: tablas resumen por bloque, histograma global de z, mapa de validez A6, umbral D3, cobertura H3, lista de capacidades no cubiertas y casos abiertos.
