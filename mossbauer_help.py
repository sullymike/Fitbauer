"""Capítulos de ayuda del programa Mössbauer Fe-57."""
from __future__ import annotations


def get_help_sections_es(voigt_sigma: float = 0.05, settings_path: object = None) -> list:
    """Devuelve los capítulos de ayuda: lista de (título, encabezado, contenido)."""
    settings_path_str = str(settings_path) if settings_path is not None else "(configuración)"
    return [
            ("Inicio", "Inicio y filosofía", """
Este programa sirve para cargar, doblar, simular y ajustar espectros Mössbauer de ⁵⁷Fe.

Flujo de trabajo recomendado:

  1. Cargar un fichero local (.ws5, .adt) o descargarlo de la base de datos web.
  2. Revisar el folding point y Vmax. Si hay fichero .RES de Normos, se cargan automáticamente.
  3. Ajustar la línea base y comprobar que la normalización es correcta.
  4. Elegir modelo: discreto (singlete / doblete / sextete) o distribución P(BHF) / P(ΔEQ).
  5. Fijar los parámetros conocidos y liberar solo los necesarios.
  6. Lanzar el ajuste y examinar el residuo.
  7. Guardar el ajuste exportado y/o la sesión completa.

Filosofía del programa:

  Todos los parámetros están visibles y se pueden modificar manualmente antes, durante y después del ajuste. Un RMS bajo no garantiza interpretación física correcta. Conviene siempre comprobar:

  • Estabilidad del resultado al cambiar valores iniciales.
  • Ausencia de estructura sistemática en el residuo.
  • Que los errores 1σ sean razonables en relación con el efecto.
  • Que los porcentajes de área sean físicamente coherentes.

Notación usada en esta ayuda:

  δ = desplazamiento isomérico (mm/s, referido a α-Fe a temperatura ambiente)
  ΔEQ = desdoblamiento cuadrupolar (mm/s)
  BHF = campo hiperfino magnético (T)
  Γ = anchura de línea HWHM (mm/s)
"""),
            ("Espectroscopía Mössbauer", "Fundamentos físicos de la espectroscopía Mössbauer", """
La espectroscopía Mössbauer mide la absorción resonante sin retroceso de fotones gamma de 14.4 keV emitidos por ⁵⁷Co y absorbidos por ⁵⁷Fe en la muestra. El movimiento Doppler del transductor barre el desfase de energía.

Interacciones hiperfinas:

  Las interacciones entre el núcleo de ⁵⁷Fe y su entorno electrónico y magnético desdoblan los niveles nucleares y dan lugar al espectro:

  1. Interacción monopolar eléctrica → desplazamiento isomérico δ
       Refleja la densidad electrónica en el núcleo. Es sensible al estado de oxidación y enlace. Fe²⁺ tiene δ mayor que Fe³⁺ en entornos similares.

  2. Interacción cuadrupolar eléctrica → desdoblamiento cuadrupolar ΔEQ
       El gradiente de campo eléctrico (GCE) interacciona con el momento cuadrupolar del estado excitado (I=3/2). Produce un doblete en fases paramagnéticas o una corrección de primer orden en fases magnéticas. ΔEQ es cero en entornos cúbicos perfectos.

  3. Interacción magnética dipolar → campo hiperfino BHF
       El campo magnético en el núcleo (campo de contacto de Fermi + contribuciones orbitales y dipolares) divide el estado fundamental (I=1/2) en 2 subniveles y el excitado (I=3/2) en 4, dando lugar al sextete de 6 líneas permitidas (ΔmI = 0, ±1).

Reglas de selección e intensidades ideales:

  Para una muestra en polvo sin textura (orientaciones al azar), el promedio angular da las intensidades relativas:

  línea 1(6) : línea 2(5) : línea 3(4) = 3 : 2 : 1

  En monocristales o con campo externo aplicado, la relación depende del ángulo θ entre el campo hiperfino y la dirección del rayo gamma:

  líneas 1,6:  3(1 + cos²θ)
  líneas 2,5:  4 sin²θ
  líneas 3,4:  (1 + cos²θ)

  Casos particulares:

  θ = 0° (campo paralelo al rayo gamma):  3 : 0 : 1
  θ = 90° (campo perpendicular):           3 : 4 : 1
  Polvo (promedio angular):                 3 : 2 : 1

  Las intensidades relativas I2 e I3 (parámetros int2, int3) pueden ajustarse libremente para muestras texturadas o con campo externo aplicado.

Velocidades características de ⁵⁷Fe (valores de referencia a T ambiente):

  Fe metálico α-Fe:    δ ≈ 0.00,  ΔEQ ≈ 0.00,  BHF ≈ 33.0 T  (6 líneas)
  Fe³⁺ octaédrico:    δ ≈ 0.37,  ΔEQ ≈ 0.60–0.90 mm/s       (doblete)
  Fe²⁺ octaédrico:    δ ≈ 1.00–1.20,  ΔEQ ≈ 2.0–3.5 mm/s    (doblete)
  Magnetita Fe³⁺(A):  δ ≈ 0.28,  ΔEQ ≈ 0.00,  BHF ≈ 49.1 T  (sextete)
  Magnetita Fe²˙⁵⁺(B): δ ≈ 0.66, ΔEQ ≈ 0.00,  BHF ≈ 45.8 T  (sextete)
  Hematita α-Fe₂O₃:  δ ≈ 0.37,  ΔEQ ≈ −0.20, BHF ≈ 51.8 T  (sextete)
  Goetita α-FeOOH:   δ ≈ 0.37,  ΔEQ ≈ −0.25, BHF ≈ 38.0 T  (sextete)
  Ferritina:          δ ≈ 0.47,  ΔEQ ≈ 0.90 mm/s             (doblete)

  Estos valores son orientativos. La temperatura, sustituciones y desorden pueden desplazarlos.
"""),
            ("Archivo y web", "Carga de datos y descarga web", """
Formatos admitidos:

  • WS5 moderno: fichero XML con bloque <data>...</data>.
  • ADT antiguo: lista plana de cuentas enteras sin cabecera XML.
  • Ambos pueden tener ficheros sidecar Normos (.RES, .PLT, .JOB) que se leen automáticamente.

Menú Archivo:

  Cargar...
    Abre ficheros locales. Si existe .RES de Normos en el mismo directorio, se cargan el folding point, Vmax y parámetros iniciales automáticamente.

  Medidas web...
    Lista y descarga medidas usando la API REST del laboratorio (no scraping). Pide usuario y contraseña una sola vez: con ellos obtiene un token que se guarda en el fichero local de credenciales y se reutiliza (solo el token; la contraseña nunca se guarda en disco). Si la medida tiene una calibración asociada, opcionalmente descarga también su fichero y aplica el Vmax calibrado.

  Calibraciones web...
    Igual que el anterior, pero lista y descarga las calibraciones α-Fe del laboratorio.

  Guardar ajuste...
    Exporta un fichero .dat con columnas: velocidad, datos normalizados, modelo, residuo, cuentas dobladas. En modo P(BHF) añade una tabla con BHF y P(BHF) normalizada.

  Exportar informe Markdown/PDF...
    Crea un informe humano del ajuste. Siempre guarda un fichero Markdown (.md) con trazabilidad, calibración, parámetros, errores, áreas, métricas estadísticas, correlaciones y diagnóstico de residuos. Opcionalmente crea también PDF; aunque se pida PDF, el .md se conserva siempre. El PDF incluye además la figura actual del ajuste.

  Guardar sesión...
    Guarda en JSON todo el estado de trabajo: cuentas, parámetros, fijos, componentes, covarianza, errores, restricciones, texto de estado. Si se descargó la medida con calibración asociada desde la web, incluye además un bloque "calibration" con la trazabilidad (id, nombre de fichero y Vmax calibrado). Permite retomar el trabajo exactamente donde se dejó.

  Subir sesión JSON a web...
    Sube el JSON de la sesión como nueva versión de análisis de una medida vía API. El botón "Buscar por nombre de fichero" localiza la medida cuyo .ws5 coincide con el fichero cargado (una sola llamada a la API). La API conserva todas las versiones sin sobrescribir. Permite añadir una nota, que se envía a la API y además queda incluida dentro del JSON.

  Cargar sesión...
    Recupera una sesión guardada. Si el fichero de datos original está accesible se recarga; si no, se usan las cuentas guardadas en el JSON. Si el JSON contiene un bloque "calibration" y el Vmax actual difiere del Vmax calibrado guardado, el programa muestra un aviso para que puedas verificar si la calibración sigue siendo válida.

Ficheros sidecar Normos:

  Si junto al .ws5 existe un fichero .RES (resultados Normos), se extrae el folding point final y los parámetros del último ajuste como valores iniciales. Si existe .PLT, se lee Vmax. Esto facilita continuar un análisis iniciado en Normos.
"""),
            ("Folding", "Folding, velocidad y fondo", """
El folding simetriza el espectro triangular de velocidades en un espectro con eje simétrico, reduciendo el número de canales efectivos a la mitad. Es un paso previo obligatorio antes de modelar.

¿Qué es el punto de folding?

  El transductor genera una rampa triangular de velocidades. Los canales 1..N/2 corresponden a la rampa ascendente y los canales N/2+1..N a la descendente. El punto de simetría (folding point) es el canal donde la rampa invierte. En Normos se llama "Final folding point" y suele ser ≈ N/2 + fracción.

  Un error de 0.5 canales en el folding point introduce una asimetría antisimétrica visible en el residuo. Si el residuo muestra picos positivos a un lado y negativos al otro de cada línea, la causa más probable es un folding point incorrecto.

Parámetros:

  Vmax
    Velocidad máxima del transductor en mm/s. Construye el eje de velocidades desde −Vmax hasta +Vmax. El valor real se obtiene de la calibración con α-Fe. Valores típicos: 10–12 mm/s para espectros de Fe puro; hasta 20 mm/s para óxidos.

    Si la medida se descargó de la web junto con su calibración asociada, el panel "Estado y parámetros" y el informe Markdown muestran la incertidumbre de Vmax de esa calibración (o avisan de que no consta de forma explícita). Tenla en cuenta como error sistemático de velocidad: no está incluida en los errores 1σ estadísticos del ajuste.

  Ajustar Vmax
    Casilla "Ajustar Vmax con el patrón de líneas". Incluye Vmax como parámetro libre en el ajuste. Útil si la calibración no es exacta, pero conviene fijar BHF simultáneamente para evitar correlación perfecta entre Vmax y BHF. El programa avisa si intentas ajustar Vmax sin haber fijado el BHF de todos los sextetes activos.

  Folding point
    Centro interno de simetría en unidades de canales. Acepta valores fraccionarios como Normos. El "Valor Normos aprox." mostrado en pantalla equivale aproximadamente al doble.

  Ajustar folding point
    Casilla "Ajustar folding point dentro del ajuste". Si se activa, el folding point se incluye como parámetro libre del ajuste discreto: en cada iteración el espectro se vuelve a doblar con el centro propuesto, se renormaliza y se recalculan los pesos estadísticos. Útil cuando el residuo muestra estructura antisimétrica (ver más abajo) y no se conoce el centro exacto. Conviene partir de un valor razonable (Ajuste → Buscar centro), mantener pocos parámetros libres y comprobar que el resultado sea físicamente plausible; si se libera junto con demasiados parámetros puede absorber problemas de modelo.

  Base
    Nivel de transmisión normalizado fuera de las líneas de absorción. Idealmente 1.0. Desviaciones indican mala normalización o saturación.

  Pendiente
    Fondo lineal (pendiente respecto a velocidad). Compensa ligeras asimetrías de fondo, pero no debe usarse para compensar un mal folding o una calibración incorrecta.

Diagnóstico de problemas de folding:

  • Residuos antisimétricos respecto al centro de cada línea → folding point incorrecto.
  • Fondo inclinado persistente → Vmax mal calibrado o pendiente real.
  • Base > 1.05 o < 0.95 → posible problema de normalización o saturación del detector.
"""),
            ("Modelo discreto", "Singlete, doblete y sextete", """
El modelo discreto superpone hasta tres componentes independientes. Cada uno puede ser singlete, doblete o sextete.

Tipos de componente:

  Singlete
    Una sola línea Lorentziana (o Voigt). Útil para fases con interacciones muy pequeñas no resueltas o para compuestos de Fe con simetría cúbica perfecta y sin campo magnético.

  Doblete
    Dos líneas simétricas separadas 2 × ΔEQ/2. Típico de Fe²⁺ o Fe³⁺ paramagnéticos con gradiente de campo eléctrico no nulo. La separación entre los dos picos del doblete visible en el espectro es directamente ΔEQ.

  Sextete
    Seis líneas magnéticas según las reglas de selección ΔmI = 0, ±1. Las posiciones dependen de BHF, δ y ΔEQ (corrección de primer orden).

Parámetros por componente (prefijo sN_ con N = 1, 2, 3):

  δ isomérico
    Desplazamiento del centro del patrón. Referido al estándar α-Fe a T ambiente.

  ΔEQ
    Desdoblamiento cuadrupolar. En el sextete actúa como corrección de primer orden: las líneas 1 y 6 se desplazan +ΔEQ/2 y las líneas 2-5 se desplazan −ΔEQ/2.

  BHF
    Campo hiperfino en teslas. Solo activo en sextete. A 33 T (α-Fe, T ambiente) las líneas externas están a ±5.33 mm/s aproximadamente.

  Γ (gamma1)
    Anchura HWHM de la línea más estrecha (líneas 1 y 6 del sextete, o la única línea del singlete/doblete). El valor mínimo físico está en torno a 0.097 mm/s (anchura natural del ⁵⁷Fe).

  Γ relativa líneas 2 y 5 (gamma2)
    Factor multiplicador sobre gamma1. 1.0 significa misma anchura que las líneas externas.

  Γ relativa líneas 3 y 4 (gamma3)
    Factor multiplicador sobre gamma1 para las líneas centrales.

  Profundidad
    Amplitud total de absorción. Es proporcional al espesor efectivo y a la abundancia de la fase. Los porcentajes de área se calculan a partir de este parámetro y las intensidades.

  Intensidades (int1, int2, int3)
    Pesos relativos de los tripletes de líneas del sextete (líneas 1&6, 2&5, 3&4). Los valores ideales para polvo sin textura son 3:2:1. Se pueden liberar para ajustar texturas o geometrías de medida no convencionales.

Porcentajes de área:

  El programa calcula el porcentaje de área de cada componente integrado sobre todas sus líneas. Son los valores que se publican habitualmente como "abundancias de fases". Aparecen en el panel Estado y parámetros tras cada ajuste.

Cómo se hace el ajuste discreto:

  Al pulsar "Ajustar" (botón "Ajuste" del panel o menú Ajuste → Ajustar) el programa:

  • Pesa cada canal por su incertidumbre Poisson: los canales con más cuentas (menos ruido relativo) influyen más en el resultado.
  • Lanza el ajuste desde 9 conjuntos de valores iniciales (autoarranque múltiple determinista) y conserva el de menor coste, para no depender de un único punto de partida.
  • Muestra una ventana de progreso indicando el autoarranque en curso.
  • Al terminar, vuelca en el panel "Estado y parámetros" las métricas, los errores 1σ y el diagnóstico del residuo.

Errores 1σ:

  Si la covarianza del ajuste es estimable (Jacobiano bien condicionado), se muestran los errores estadísticos 1σ de cada parámetro libre. Son solo errores estadísticos; el error sistemático (folding, calibración, modelo) suele ser mayor.

  Si la covarianza no es fiable, o si hay parámetros muy correlacionados, los errores se pueden estimar por remuestreo con Ajuste → Bootstrap errores (MC)... (ver el capítulo "Novedades desde v0.2").

Métricas y diagnóstico tras el ajuste:

  El panel "Estado y parámetros" muestra, además del RMS:

  • χ², χ² reducido y grados de libertad. Un χ² reducido cercano a 1 indica un ajuste estadísticamente razonable.
  • AIC y BIC, para comparar modelos sobre los mismos datos: a igualdad de datos, el menor valor es preferible.
  • Correlación máxima entre parámetros libres, con aviso si hay parejas con |r| ≥ 0.95 (parámetros que no se pueden determinar por separado).
  • Diagnóstico del residuo (autocorrelación lag-1, test de rachas y correlación antisimétrica), descrito en el capítulo "Diagnóstico".
"""),
            ("Perfil de línea", "Lorentziana y Voigt", """
El programa admite dos perfiles de línea:

  Lorentziana (perfil por defecto)
    Es el perfil natural de una transición nuclear sin ensanchamiento inhomogéneo. Es la elección habitual para la mayoría de los ajustes Mössbauer. Colas más largas que una gaussiana.

  Voigt
    Convolución de Lorentziana (anchura natural) con Gaussiana (ensanchamiento inhomogéneo). Útil cuando hay una distribución de entornos locales que ensanchan simétricamente las líneas sin llegar a necesitar una distribución P(BHF) completa.

  El parámetro σ de la componente gaussiana del Voigt se fija en {voigt_s:.2f} mm/s en esta versión.

Cuándo usar Voigt:

  • Las líneas son claramente más anchas de lo esperado pero mantienen forma simétrica.
  • Se sospecha ensanchamiento inhomogéneo moderado (nanocristales, sustituciones parciales).
  • El ajuste Lorentziano deja residuos en las alas de las líneas.

Cuándo usar P(BHF) en su lugar:

  • El ensanchamiento es asimétrico o tiene estructura (hombros, picos secundarios).
  • Se sospecha una distribución real de campos hiperfinos (desorden magnético, tamaño de partícula).
  • El Voigt no mejora suficientemente el residuo.
""".format(voigt_s=voigt_sigma)),
            ("P(BHF): idea", "Distribución de campo hiperfino P(BHF)", """
P(BHF) se usa cuando no hay un único campo hiperfino sino una distribución continua de campos. En lugar de uno o varios sextetes bien definidos, el espectro se describe como suma de muchos sextetes con BHF distinto.

¿Cuándo usar P(BHF)?

  • Materiales amorfos o nanocristalinos con distribución de entornos magnéticos.
  • Ferritas con sustituciones catiónicas (Zn, Mn, Co...) que generan variación de BHF.
  • Nanopartículas con distribución de tamaños: las partículas más pequeñas tienen BHF más bajo por relajación superparamagnética.
  • Interfaces y superficies donde el campo hiperfino varía.
  • Cualquier sistema donde las líneas del sextete estén claramente ensanchadas de forma asimétrica.

Interpretación de P(BHF):

  P(BHF) indica la fracción del espectro que proviene de iones Fe con cada valor de campo hiperfino. No es directamente una función de distribución de tamaños ni de composición, aunque en muchos sistemas hay correlación.

  Una P(BHF) con un pico bien definido indica una fase mayoritaria con campo bien determinado. Una P(BHF) ancha y sin estructura indica gran desorden magnético. Un hombro o pico secundario puede indicar una segunda fase.

Modelo simplificado:

  espectro = fondo − Σᵢ Pᵢ · sextete(Bᵢ, δ, ΔEQ, Γ)

  donde Bᵢ son los centros de los bins y Pᵢ son los pesos (no negativos).

Limitación fundamental:

  La inversión espectro → P(BHF) es un problema mal condicionado: existen infinitas distribuciones que ajustan igual de bien dentro del ruido. La regularización reduce la ambigüedad penalizando distribuciones rugosas, pero no la elimina. Dos distribuciones suavizadas distintas pueden dar residuos casi idénticos.
"""),
            ("P(BHF): método", "Método Hesse-Rübartsch y regularización", """
El motor implementa una aproximación tipo Hesse-Rübartsch (método estándar en espectroscopía Mössbauer):

Pasos del algoritmo:

  1. Se define una malla uniforme de N_bins campos entre B_mín y B_máx.
  2. Para cada bin se calcula el sextete correspondiente (matriz de respuesta A).
  3. Se buscan pesos P ≥ 0 que minimicen:

     residuo² + α · ||D² P||²

  4. D² es la matriz de segundas diferencias: penaliza la curvatura de P(BHF).
  5. El problema se resuelve iterativamente con restricción de no negatividad.

Función objetivo:

  χ² = ||y − A·P||² + α · ||D²·P||²

  El primer término mide el ajuste a los datos. El segundo mide la rugosidad de P(BHF).

Papel del parámetro α:

  α = 0        El ajuste reproduce el espectro al máximo, pero P(BHF) llena de picos espurios.
  α pequeño    P(BHF) detallada con posibles oscilaciones de ruido.
  α óptimo     Compromiso entre fidelidad al espectro y suavidad física.
  α grande     P(BHF) muy suave, quizás demasiado, perdiendo estructura real.

  El valor óptimo no es universal: depende de la relación señal/ruido, del número de canales, del número de bins y del ancho de línea. Siempre hay que explorar varios valores de α y comprobar que los rasgos principales de P(BHF) son estables.

Formas de P(BHF) disponibles:

  Histograma (libre, no paramétrica)
    Cada bin tiene un peso independiente ajustable. Máxima flexibilidad, más sensible a la elección de α. Es la forma más usada.

  Gaussiana
    La distribución se parametriza como una gaussiana (centro, anchura, amplitud). Reduce los grados de libertad a 3. Útil cuando se espera una distribución unimodal bien definida. No necesita α.

  Binomial
    Modelo combinatorio para ferritas con sustituciones catiónicas. La forma de P(BHF) viene dada por la distribución binomial del número de sustituyentes en los primeros vecinos. Solo ajusta probabilidad de sustitución y amplitud. No necesita α.

  Fija
    Carga una P(BHF) definida externamente (fichero con dos columnas: centro, peso) y solo ajusta la amplitud global, baseline y slope. Útil para comparar con distribuciones publicadas o para refinar δ y Γ manteniendo la forma fija.

  Las cuatro formas admiten componentes nítidos (activando "sumar componentes activos nítidos"). Los nítidos se ajustan simultáneamente con la distribución en todos los casos.
"""),
            ("P(BHF): parámetros", "Parámetros de la distribución P(BHF)", """
Parámetros globales (comunes a todos los sextetes de la distribución):

  δ global
    Desplazamiento isomérico común. Si la distribución contiene fases con δ muy distinto, es mejor usar componentes nítidos para cada fase.

  ΔEQ global
    Cuadrupolo común (corrección de primer orden). Puede refinarse junto con δ activando la opción "Refinar δ y Γ globales".

  Γ HWHM
    Anchura de línea común a todos los bins. Una Γ más grande suaviza la distribución y reduce la inestabilidad pero oscurece estructura fina. Una Γ más pequeña puede reproducir mejor picos estrechos pero requiere α mayor para estabilizar.

Parámetros de la malla:

  B mín
    Límite inferior de la distribución. B_mín = 0 permite absorber contribuciones de bajo campo (fases paramagnéticas, relajación), pero puede introducir peso artificial si no hay señal real en esa zona. Para fases puramente magnéticas conviene empezar en 10–20 T.

  B máx
    Límite superior. Debe superar el BHF máximo esperado. Para hematita (~52 T) conviene B_máx ≥ 55 T. Para α-Fe (~33 T) basta con 36–38 T.

  Bins BHF
    Número de puntos de la malla. Más bins = mayor resolución potencial + mayor inestabilidad. Para espectros típicos de 512 canales, 30–60 bins suele ser suficiente. Con muchos bins y α bajo pueden aparecer oscilaciones artefacto.

Control de regularización:

  log10 α
    Logaritmo del parámetro de regularización. Un valor de −2 a 0 es habitual. Variar en pasos de 0.5 y observar la estabilidad de P(BHF) y del RMS.

  L-curve α
    El botón "L-curve α" escanea automáticamente un rango amplio de α (con ventana de progreso) y abre una ventana con dos gráficas: la curva L (log residuo vs. log rugosidad) y el RMS junto con el χ² reducido frente a α. Propone dos valores: el del codo de la L-curve (máxima curvatura) y un valor "de compromiso" (el más cercano a residuo y rugosidad mínimos a la vez). Los botones "Usar L-curve" y "Usar compromiso" aplican ese α directamente; "Guardar tabla" exporta a fichero la tabla completa del escaneo (α, RMS, norma del residuo, rugosidad, χ², χ² reducido y campo/posición del pico). Es un punto de partida, no una respuesta definitiva: conviene comprobar la estabilidad de P(BHF) alrededor del valor elegido.

  Distribución fija
    Carga una P(BHF) externa (dos columnas: BHF, peso) y la aplica sin ajustar los pesos. Útil para comparar con resultados de otras referencias o para refinar solo δ, Γ con una distribución conocida.
"""),
            ("P(BHF): nítidos", "Componentes nítidos junto a la distribución", """
Es posible combinar una distribución P(BHF) o P(ΔEQ) continua con uno o más componentes discretos ("nítidos") en el mismo ajuste. Los nítidos funcionan con todas las formas de distribución: Histograma, Gaussiana, Binomial y Fija.

Cómo activarlo:

  Marcar la opción "sumar componentes activos nítidos" en la pestaña Distribución.

  Al activarla, el componente 1 se usa siempre como nítido. Los componentes 2 y 3 se usan si están activados ("Usar componente 2/3" marcado en su pestaña). Sus parámetros (δ, ΔEQ, BHF, Γ, intensidades) se toman de los sliders de cada pestaña de componente.

Cuándo es útil:

  • Una muestra tiene una fase mayoritaria desordenada (P(BHF) ancha) y una fase minoritaria bien definida (sextete estrecho).
  • Ejemplo: ferrita de zinc con distribución amplia + traza de α-Fe a BHF ≈ 33 T.
  • Ejemplo: óxido de Fe amorfo (P(BHF) amplia) + doblete de Fe²⁺ paramagnético.
  • Ejemplo: vidrio con P(ΔEQ) ancha + singlete de Fe metálico.

Cómo funciona internamente:

  • La distribución (pesos de los bins) se ajusta como siempre (con regularización en Histograma, paramétricamente en Gaussiana/Binomial, con amplitud global en Fija).
  • Los componentes nítidos se añaden como columnas adicionales al sistema de ecuaciones.
  • Sus amplitudes se ajustan junto con los pesos de la distribución, con restricción de no negatividad, pero sin regularización.
  • El panel Estado muestra por separado el porcentaje de área de la distribución y de cada componente nítido.

Diferencias entre formas:

  Histograma
    Máxima flexibilidad para la distribución. Los nítidos compiten con los bins de la distribución solo si solapan en el espectro. Es la combinación más usada.

  Gaussiana / Binomial
    La distribución tiene pocos parámetros y forma rígida. Los nítidos son especialmente útiles aquí porque absorben las fases que la distribución no puede reproducir por su forma fija.

  Fija
    La forma de la distribución está predefinida. Los nítidos permiten añadir contribuciones no incluidas en la distribución externa.

Precauciones:

  • Un componente nítido puede competir con un pico de P(BHF) si el BHF del nítido cae dentro del rango de la distribución. El ajuste puede distribuir la señal arbitrariamente entre ambos.
  • Si el nítido tiene BHF conocido (p. ej. α-Fe a 33 T como calibrante), conviene fijarlo.
  • Conviene comparar el ajuste con y sin el componente nítido para verificar que aporta mejora estadística real.
  • Aumentar α puede transferir peso del nítido a la distribución o viceversa.
  • Si un nítido sale con peso ≈ 0, probablemente no es necesario en el modelo.
"""),
            ("P(ΔEQ): distribución", "Distribución de desdoblamiento cuadrupolar P(ΔEQ)", """
P(ΔEQ) es el análogo cuadrupolar de P(BHF): en lugar de distribuir campos hiperfinos, distribuye valores de desdoblamiento cuadrupolar ΔEQ manteniendo un BHF fijo común a todos los dobletes o sextetes de la distribución.

Cómo se activa:

  En la pestaña Distribución, el selector "Variable de distribución" permite elegir entre BHF y ΔEQ. Al seleccionar ΔEQ, los sliders "Mín distribución" y "Máx distribución" pasan a operar en mm/s (rango de ΔEQ), y aparece el parámetro "BHF fijo p/ P(ΔEQ)".

¿Cuándo usar P(ΔEQ)?

  • Fases paramagnéticas con distribución de entornos locales: Fe³⁺ o Fe²⁺ en vidrios, zeolitas, arcillas o materiales amorfos, donde cada ión Fe ve un gradiente de campo eléctrico (GCE) diferente.
  • Materiales con desorden estructural que produce una distribución de distorsiones del poliedro de coordinación, sin que haya campo magnético relevante.
  • Superparamagnéticos por encima de su temperatura de bloqueo: el espectro colapsa a un doblete ancho cuya anchura real refleja la distribución de ΔEQ y/o relajación.
  • Vidrios de óxido de hierro, ferritinas, proteínas con Fe, silicatos con Fe²⁺ en sitios distorsionados.

Diferencia fundamental con P(BHF):

  En P(BHF) el espectro es suma de sextetes con distintos campos. En P(ΔEQ) el espectro es suma de sextetes (o dobletes si BHF = 0) con distintos valores de ΔEQ y un único BHF fijo:

  espectro = fondo − Σᵢ Pᵢ · sextete(BHF_fijo, ΔEQᵢ, δ, Γ)

  Si BHF_fijo = 0, cada término es un doblete, y P(ΔEQ) es literalmente la distribución de separaciones de un conjunto de dobletes.

Interpretación física de P(ΔEQ):

  P(ΔEQ) indica qué fracción de los iones Fe presenta cada valor de desdoblamiento cuadrupolar. Un pico estrecho corresponde a un entorno bien definido; una distribución ancha indica desorden en la geometría de coordinación o en la distribución de cargas alrededor del núcleo.
"""),
            ("P(ΔEQ): parámetros", "Parámetros específicos de P(ΔEQ)", """
Selector de variable de distribución:

  Variable de distribución
    Selector BHF / ΔEQ en la pestaña Distribución. Al cambiar a ΔEQ, los sliders de rango pasan a mm/s y se habilita el BHF fijo. El resto de controles (α, bins, Γ, δ, forma) funcionan igual que en P(BHF).

Parámetros específicos de P(ΔEQ):

  BHF fijo p/ P(ΔEQ)
    Campo hiperfino único compartido por todos los sextetes de la distribución. Si se fija a 0, cada bin es un doblete. Si se fija a un valor distinto de cero (p. ej. 33 T para α-Fe), cada bin es un sextete con la separación magnética correspondiente y un desdoblamiento cuadrupolar variable. Fijar BHF fijo en el valor del campo de la fase estudiada y dejar que P(ΔEQ) recoja la distribución de entornos locales.

  Mín distribución (en mm/s para P(ΔEQ))
    Valor mínimo de ΔEQ en la malla. Para dobletes paramagnéticos sin campo aplicado conviene empezar en 0 mm/s. Si se sabe que ΔEQ mínimo es mayor (p. ej. el sistema siempre tiene al menos 0.5 mm/s de desdoblamiento), se puede restringir el rango para mejorar la estabilidad.

  Máx distribución (en mm/s para P(ΔEQ))
    Valor máximo de ΔEQ. Para Fe²⁺ con desorden puede llegar a 3–4 mm/s; para Fe³⁺ rara vez supera 2 mm/s. Un rango innecesariamente amplio dilata los bins y reduce la resolución.

  δ global
    Desplazamiento isomérico común a todos los bins. Si la muestra tiene iones Fe con δ muy distintos (p. ej. mezcla Fe²⁺ / Fe³⁺), no es apropiado usar una sola P(ΔEQ); conviene un componente nítido para cada especie o subdividir el análisis.

  ΔEQ fijo/global
    En modo P(ΔEQ) este parámetro no se usa como variable de distribución, pero si se activa "refinar δ y Γ globales" se puede refinar junto con δ. En modo P(BHF) sí actúa como ΔEQ único para todos los sextetes de la distribución.

  Γ HWHM
    Anchura de línea de cada bin. Igual que en P(BHF): una Γ más grande suaviza la distribución resultante.

  log10 α, L-curve α, Bins, forma
    Funcionan exactamente igual que en P(BHF). Ver los capítulos P(BHF): método y P(BHF): parámetros.

Casos típicos de configuración:

  Vidrio de Fe³⁺ paramagnético (doblete ancho):
    BHF fijo = 0, δ ≈ 0.35 mm/s, Mín = 0, Máx = 2.0 mm/s, Γ ≈ 0.15 mm/s.

  Fe²⁺ en silicato distorsionado (doblete muy ancho):
    BHF fijo = 0, δ ≈ 1.1 mm/s, Mín = 0, Máx = 4.0 mm/s, Γ ≈ 0.15–0.20 mm/s.

  Fase magnética con distribución de ΔEQ (p. ej. hematita con desorden):
    BHF fijo ≈ 51.8 T, δ ≈ 0.37 mm/s, Mín = −0.8, Máx = 0.8 mm/s, Γ ≈ 0.15 mm/s.

Precauciones específicas de P(ΔEQ):

  • Con BHF fijo ≠ 0, la distribución de ΔEQ puede correlacionarse con el δ global: un cambio de δ puede compensarse parcialmente con un desplazamiento de toda P(ΔEQ). Conviene fijar δ si es conocido.
  • Si el espectro tiene tanto distribución de BHF como de ΔEQ, ninguno de los dos modos unidimensionales será completamente satisfactorio. En ese caso, el modelo más honesto es P(BHF) con ΔEQ como corrección de primer orden global, o viceversa según cuál sea la fuente dominante de ensanchamiento.
  • Los porcentajes de área se calculan igual que en P(BHF): integral de los pesos de la distribución más los componentes nítidos si los hay.
"""),
            ("Restricciones", "Restricciones lineales entre parámetros", """
Las restricciones permiten imponer relaciones lineales entre parámetros de distintos subespectros. Se configuran en:

  Opciones → Restricciones entre parámetros...

Forma matemática:

  destino = factor × origen + suma

  El parámetro destino no se ajusta directamente: en cada evaluación del modelo se recalcula a partir del origen.

Ejemplos prácticos:

  s2_gamma1 = 1.0 × s1_gamma1 + 0
    Fuerza a que la anchura del subespectro 2 sea igual a la del subespectro 1.

  s2_int1 = 0.5 × s1_int1 + 0
    La intensidad I1 del subespectro 2 será la mitad de la del subespectro 1.

  s3_delta = 1.0 × s1_delta + 0.15
    El δ del subespectro 3 queda 0.15 mm/s por encima del del subespectro 1.

  s2_depth = 0.333 × s1_depth + 0
    La profundidad del subespectro 2 es 1/3 de la del subespectro 1.

Columnas de la tabla:

  Activa
    Permite activar o desactivar una restricción sin borrarla.

  Destino
    Parámetro dependiente. Se recalcula automáticamente.

  Origen
    Parámetro independiente del que depende el destino.

  Factor
    Multiplicador aplicado al origen.

  Suma
    Término constante añadido al final.

Presets físicos de restricciones:

  En Opciones → Presets físicos de restricciones... hay atajos para aplicar relaciones comunes sin tener que escribirlas a mano:

  • Sextetes polvo 3:2:1: fija int1=1, int2=1, int3=1 en sextetes activos, que equivale a intensidades reales 3:2:1.
  • Mismas anchuras dentro de cada componente: fija gamma2=gamma3=1 para que todas las líneas compartan Γ.
  • Ligar δ de componentes activos al componente 1: añade restricciones s2_delta=s1_delta y/o s3_delta=s1_delta.
  • Ligar Γ1 de componentes activos al componente 1: añade restricciones s2_gamma1=s1_gamma1 y/o s3_gamma1=s1_gamma1.

Cómo actúan durante el ajuste:

  • El parámetro destino no es libre: no tiene entrada en el vector de parámetros del optimizador.
  • En cada evaluación del modelo se aplica: destino ← factor × origen + suma.
  • Si el slider del origen se mueve manualmente, el destino se actualiza en tiempo real.
  • Si el resultado cae fuera del rango permitido del destino, se recorta al límite.

Usos típicos:

  • Igualar anchuras de dos fases con el mismo tipo de Fe: s2_gamma1 = 1 × s1_gamma1 + 0.
  • Mantener una relación de intensidades conocida por geometría: s2_depth = 0.5 × s1_depth + 0.
  • Imponer que dos δ son iguales: s2_delta = 1 × s1_delta + 0.
  • Añadir un desplazamiento de segundo orden conocido: s2_delta = 1 × s1_delta + 0.08.
  • Reducir el número de parámetros libres cuando hay correlaciones fuertes.

Precauciones:

  • Evita cadenas circulares: A depende de B y B depende de A.
  • No uses restricciones para forzar un resultado físico si el residuo empeora claramente.
  • Una restricción demasiado estricta puede sesgar el ajuste si el supuesto físico es solo aproximado; en ese caso, liberar ambos parámetros y comprobar si la diferencia es significativa.
  • Las restricciones activas se muestran en el panel Estado y parámetros, y se guardan en sesiones.
"""),
            ("Guardar y exportar", "Guardar ajuste, sesión y opciones", f"""
Guardar ajuste (.dat):

  Exporta un fichero de texto con columnas tabuladas:
    velocidad (mm/s) | datos normalizados | modelo | residuo | cuentas dobladas

  En modo P(BHF) añade una sección con la tabla BHF-P(BHF) (amplitud y probabilidad normalizada).

  La cabecera del fichero incluye todos los parámetros relevantes (modo, Vmax, folding, factores de área, etc.) en formato legible por humanos y parseables por scripts.

Exportar informe Markdown/PDF:

  Genera un informe pensado para documentación o publicación interna. No sustituye a la sesión JSON ni al .dat, sino que los complementa. Incluye:

    • Fecha, versión del programa y fichero usado.
    • Modo de ajuste, perfil de línea, folding point, Vmax y normalización.
    • Calibración asociada, si existe, incluida su incertidumbre de Vmax si la API la proporciona.
    • Métricas: RMS, χ², χ² reducido, AIC, BIC y número de parámetros.
    • Diagnóstico de residuo: autocorrelación lag-1, test de rachas y correlación antisimétrica.
    • Áreas y porcentajes por integración numérica del perfil real.
    • Parámetros, errores 1σ, fijos/libres y correlaciones altas.
    • Texto completo del panel Estado.

  Si se solicita PDF, primero se guarda el Markdown y después se genera el PDF. El PDF añade una página con la figura actual.

Guardar sesión (.json):

  Guarda en JSON todo el estado de trabajo:
    • Cuentas originales (si no hay ruta accesible).
    • Todos los parámetros y sus valores actuales.
    • Cuáles están fijados y cuáles libres.
    • Tipo de componente (singlete/doblete/sextete) por subespectro.
    • Opciones de visualización.
    • Covarianza del último ajuste y errores 1σ.
    • Restricciones activas.
    • Texto del panel Estado y parámetros.

  La sesión permite retomar el trabajo exactamente donde se dejó, incluso en otro ordenador.

Exportar informe Markdown/PDF:

  La opción Archivo → Exportar informe Markdown/PDF... genera un informe legible del ajuste actual, pensado para documentación o para adjuntar a una publicación.

  Cómo se hace:

    1. Menú Archivo → Exportar informe Markdown/PDF...
    2. Elige nombre y carpeta. Se guarda un fichero .md (Markdown).
    3. El programa pregunta si quieres además un PDF. Si aceptas, crea un .pdf con el mismo contenido y una página final con la figura actual del espectro.
    4. El Markdown se conserva siempre, también cuando se genera el PDF.

  El informe resume: fecha y versión del programa, fichero y modo de ajuste, perfil de línea, trazabilidad de la calibración asociada, métricas (RMS, χ², χ² reducido, AIC, BIC), diagnóstico de residuos, correlaciones altas de parámetros, áreas y porcentajes por componente, tabla de parámetros con errores 1σ y el texto completo del panel Estado.

  El informe no sustituye a la sesión .json (que es lo reproducible) ni al ajuste .dat (que contiene los datos numéricos punto a punto): es un resumen para humanos.

Opciones automáticas:

  Al cerrar el programa se guardan preferencias de visualización y último directorio usado en:

  {settings_path_str}

Recomendaciones:

  • Guardar la sesión antes de probar cambios arriesgados (liberar muchos parámetros, cambiar α).
  • El ajuste exportado (.dat) es el adecuado para adjuntar a publicaciones o enviar a colaboradores.
  • Si se publican resultados, anotar siempre el folding point, Vmax, modo de ajuste y α (en P(BHF)).
"""),
            ("Estadística y ajuste", "Pesos, selección de modelo, errores y robustez", """
Esta versión incorpora varios diagnósticos estadísticos para que el ajuste sea más comparable con flujos de trabajo avanzados tipo NORMOS/SyncMoss.

1. Pesos Poisson

  Los datos doblados proceden de cuentas. Para el ajuste discreto y la distribución Hesse-Rübartsch P(BHF)/P(ΔEQ), el programa estima una incertidumbre:

    σ ≈ sqrt(cuentas_dobladas / 2) / factor_normalización

  El ajuste minimiza (modelo − datos)/σ. Así los canales con más ruido pesan menos y χ² tiene una interpretación estadística más razonable.

2. χ² reducido, AIC y BIC

  Además del RMS se muestran:

    χ² reducido = Σ((datos−modelo)/σ)² / grados_libertad
    AIC y BIC = criterios de información penalizados por número de parámetros

  Para comparar modelos ajustados sobre los mismos datos, menor AIC/BIC suele indicar mejor compromiso entre calidad de ajuste y complejidad. No debe compararse AIC/BIC entre datos distintos o normalizaciones distintas.

3. Áreas por integración numérica

  Los porcentajes de área se calculan integrando la absorción real del componente sobre el eje de velocidades. Esto es válido para Lorentziana y Voigt y evita usar fórmulas de área que solo serían exactas para Lorentzianas puras.

4. Correlaciones de parámetros

  Cuando la covarianza es estimable, se calcula la matriz de correlación. El panel avisa si hay pares con |r| ≥ 0.95. Una correlación alta significa que los parámetros no están bien determinados por separado; conviene fijar uno, imponer una restricción física o simplificar el modelo.

5. Bootstrap Monte Carlo

  Menú Ajuste → Bootstrap errores (MC)...

  Genera réplicas sintéticas sumando ruido gaussiano con σ Poisson al modelo actual, reajusta cada réplica y estima errores como desviación típica de los resultados. Es más costoso que la covarianza local, pero da una idea más robusta de la incertidumbre en modelos no lineales. En esta versión se aplica a modelos discretos; para P(BHF) se recomienda estudiar estabilidad frente a α.

6. Diagnóstico de residuos

  El panel muestra:

    lag1      autocorrelación entre canales consecutivos
    runs z    test de rachas de signos
    antisim   correlación antisimétrica respecto al centro

  Valores grandes sugieren estructura no aleatoria: componentes faltantes, folding incorrecto, Vmax/calibración mal ajustado o modelo físico insuficiente.

7. Autoarranques múltiples

  El ajuste discreto prueba varios puntos iniciales deterministas alrededor de los valores actuales y conserva el de menor coste. Esto reduce la dependencia del mínimo local, aunque no sustituye la revisión física del resultado.

8. Progreso durante cálculos largos

  Durante ajustes discretos, escaneos L-curve y ajustes de distribución aparece una ventana de progreso. Indica qué autoarranque o qué α se está evaluando para distinguir un cálculo largo de un bloqueo real.

9. Incertidumbre de calibración

  Si la medida trae calibración asociada desde la API y esta contiene campos de incertidumbre de Vmax, se muestran en Estado e informe. Si no existe incertidumbre explícita, el programa avisa de que debe considerarse error sistemático adicional.

10. Ajuste del folding point

  La casilla "Ajustar folding point dentro del ajuste" libera el centro de folding. Es útil para corregir pequeños errores de centrado, especialmente cuando el residuo presenta estructura antisimétrica. Úsala junto con pocos parámetros libres y revisa que el valor final sea físicamente razonable.
"""),
            ("Diagnóstico", "Residuos, errores frecuentes y buenas prácticas", """
El residuo (datos − modelo) debe parecerse al ruido estadístico. Cualquier estructura sistemática indica que el modelo no es adecuado o que hay un problema instrumental.

Indicadores automáticos del residuo:

  Tras cada ajuste, el panel "Estado y parámetros" muestra tres indicadores que cuantifican si el residuo tiene estructura no aleatoria:

  • Autocorrelación lag-1: correlación entre cada punto del residuo y el siguiente. Cerca de 0 indica residuo sin memoria; un valor alto (|lag1| > 0.35) indica que el modelo deja tendencias suaves sin describir.
  • Test de rachas (z): compara el número de cambios de signo del residuo con lo esperado para ruido aleatorio. |z| > 2 indica demasiadas o demasiado pocas rachas, es decir, estructura sistemática.
  • Correlación antisimétrica: mide cuánto se parece el residuo a su versión reflejada y con el signo cambiado. Un valor alto (> 0.45) es típico de un folding point incorrecto.

  Si alguno de los tres se sale de rango, el panel muestra el aviso "el residuo parece tener estructura no aleatoria" y recuerda revisar el modelo, el folding point, la calibración Vmax o posibles componentes que falten. Son una ayuda, no un veredicto: confírmalo siempre mirando la gráfica del residuo.

Patrones de residuo y sus causas habituales:

  Pares positivo-negativo en torno a cada línea (antisimétrico)
    → Folding point incorrecto o asimetría de velocidades. Corregir el folding point, no añadir componentes.

  Fondo inclinado o curvado
    → Vmax incorrecto, pendiente real del detector, o normalización errónea. No compensar con pendiente si el origen es instrumental.

  Líneas más anchas en el modelo que en los datos
    → Γ demasiado grande. Reducirla manualmente y ajustar de nuevo.

  Picos de residuo en las alas de las líneas (modelo más estrecho que los datos)
    → Considerar perfil Voigt o P(BHF) si el ensanchamiento es real.

  Residuo sistemático en el centro del espectro
    → Puede indicar un componente no modelado (doblete, singlete paramagnético).

  Residuo con estructura en P(BHF)
    → α demasiado grande (distribución demasiado suavizada). Reducir α.

  Oscilaciones de alta frecuencia en P(BHF) con buen residuo
    → α demasiado pequeño. La distribución está absorbiendo ruido. Aumentar α.

Errores frecuentes:

  • Añadir componentes hasta que el residuo mejore sin justificación física.
  • Liberar Vmax y BHF simultáneamente sin fijar ninguno de los dos.
  • Interpretar el mínimo encontrado como la única solución posible.
  • Usar α demasiado pequeño en P(BHF) y publicar picos espurios como fases reales.
  • Interpretar los errores 1σ estadísticos como errores totales del experimento.
  • Usar una pendiente grande para compensar un mal folding.

Buenas prácticas:

  • Probar al menos 3-5 conjuntos distintos de valores iniciales para confirmar el mínimo.
  • Fijar BHF en los rangos conocidos para el sistema antes de liberar todos los parámetros.
  • Comparar modelos con el mismo criterio (mismo χ² reducido o RMS).
  • En P(BHF), variar α en un rango de 2–3 órdenes de magnitud y comprobar estabilidad.
  • Guardar sesiones alternativas cuando hay ambigüedad en el modelo.
  • Si dos modelos dan residuos similares, preferir el más parsimonioso (menos parámetros libres).
  • Informar siempre el número de canales, Vmax, temperatura de medida y referencia de δ.
"""),
            ("Parámetros de referencia", "Valores de referencia para fases comunes de Fe", """
Esta sección recoge valores típicos publicados en la literatura para orientar el ajuste inicial. Los valores pueden variar según temperatura, composición y entorno.

Temperatura ambiente (≈ 295 K), referencia α-Fe:

  α-Fe (hierro metálico):
    δ = 0.00 mm/s   ΔEQ = 0.00 mm/s   BHF = 33.0 T   Γ ≈ 0.13–0.15 mm/s

  γ-Fe₂O₃ (maghemita), sitio tetraédrico (A):
    δ ≈ 0.22 mm/s   ΔEQ ≈ 0.00 mm/s   BHF ≈ 49.7 T

  γ-Fe₂O₃ (maghemita), sitio octaédrico (B):
    δ ≈ 0.33 mm/s   ΔEQ ≈ 0.00 mm/s   BHF ≈ 50.6 T

  α-Fe₂O₃ (hematita, T > T_Morin ≈ 263 K):
    δ ≈ 0.37 mm/s   ΔEQ ≈ −0.20 mm/s  BHF ≈ 51.8 T

  α-Fe₂O₃ (hematita, T < T_Morin):
    δ ≈ 0.37 mm/s   ΔEQ ≈ +0.40 mm/s  BHF ≈ 54.2 T

  Fe₃O₄ (magnetita), sitio A (Fe³⁺):
    δ ≈ 0.28 mm/s   ΔEQ ≈ 0.00 mm/s   BHF ≈ 49.1 T

  Fe₃O₄ (magnetita), sitio B (Fe²˙⁵⁺):
    δ ≈ 0.66 mm/s   ΔEQ ≈ 0.00 mm/s   BHF ≈ 45.8 T

  α-FeOOH (goetita):
    δ ≈ 0.37 mm/s   ΔEQ ≈ −0.25 mm/s  BHF ≈ 38.2 T

  β-FeOOH (akaganeíta):
    δ ≈ 0.37 mm/s   ΔEQ ≈ 0.55 mm/s  (doblete paramagnético a T amb.)

  γ-FeOOH (lepidocrocita):
    δ ≈ 0.37 mm/s   ΔEQ ≈ 0.53 mm/s  (doblete paramagnético a T amb.)

  Fe²⁺ octaédrico (general):
    δ ≈ 1.0–1.2 mm/s   ΔEQ ≈ 2.0–3.5 mm/s

  Fe³⁺ octaédrico paramagnético:
    δ ≈ 0.35–0.45 mm/s   ΔEQ ≈ 0.60–0.90 mm/s

  Fe³⁺ tetraédrico paramagnético:
    δ ≈ 0.18–0.25 mm/s   ΔEQ ≈ 0.20–0.50 mm/s

  FeS₂ (pirita):
    δ ≈ 0.31 mm/s   ΔEQ ≈ 0.61 mm/s

Notas de uso:

  • Los valores de BHF disminuyen con la temperatura siguiendo aproximadamente una ley de Bloch.
  • En nanopartículas, BHF es típicamente más bajo que en el bulk por efectos de superficie y relajación.
  • Hematita: por debajo de la transición de Morin (~263 K), el espín se reorienta y ΔEQ cambia de signo (de −0.20 a +0.40 mm/s) y BHF aumenta ligeramente (~54 T). En nanopartículas la T de Morin baja o desaparece.
  • Magnetita: la transición de Verwey (~120 K) desdobla el sitio B en múltiples componentes. Por encima de Verwey, el sitio B muestra un solo sextete por promedio rápido de electrones.
  • Para ajustes publicables, usar valores de referencia de la literatura del sistema específico.
  • Los valores de δ se dan referidos a α-Fe a temperatura ambiente. Para convertir a otra referencia, sumar la diferencia de δ entre los estándares.
"""),
            ("Atajos y flujo rápido", "Flujo de trabajo eficiente", """
Controles principales:

  Botón "Ajuste"
    Lanza el ajuste con los parámetros libres actuales. En modo discreto usa least_squares; en modo distribución usa el motor correspondiente a la forma seleccionada.

  Botón "Liberar todos"
    Desmarca todos los checkboxes "fijo", permitiendo que todos los parámetros se ajusten.

  Botón "Fijar todos"
    Marca todos los checkboxes "fijo". Útil antes de liberar selectivamente solo los parámetros deseados.

  Menú Opciones → Tipo de ajuste
    Cambia entre modelo discreto y distribución P(BHF)/P(ΔEQ).

  Menú Opciones → Restricciones
    Abre el diálogo de restricciones lineales entre parámetros.

  Menú Opciones → Presets físicos de restricciones
    Aplica con un clic relaciones físicas habituales (intensidades 3:2:1, anchuras iguales, ligar δ o Γ entre componentes). Ver el capítulo "Novedades desde v0.2".

  Menú Ajuste → Bootstrap errores (MC)
    Estima los errores de los parámetros por remuestreo Monte Carlo. Solo en modo discreto. Ver el capítulo "Novedades desde v0.2".

  Menú Archivo → Exportar informe Markdown/PDF
    Genera un informe legible del ajuste actual. Ver el capítulo "Guardar y exportar".

  Menú Ayuda → Changelog
    Muestra la lista completa de cambios de todas las versiones del programa.

  Casillas de entrada numérica
    Además de los sliders, se puede escribir un valor exacto en la casilla y pulsar Enter para aplicarlo.

Flujo rápido para un espectro conocido:

  1. Cargar el espectro.
  2. Comprobar que el folding point y Vmax son correctos (mirar si las líneas externas terminan en ≈ Vmax).
  3. Seleccionar tipo de componente (Sextete para fases magnéticas, Doblete para paramagnéticas).
  4. Fijar BHF al valor esperado, liberar δ, ΔEQ y Profundidad.
  5. Pulsar Ajuste. Revisar residuo.
  6. Si el residuo es bueno, liberar también Γ.
  7. Ajustar de nuevo. Anotar RMS.
  8. Guardar sesión.

Flujo para espectro con P(BHF):

  1. Cargar y verificar folding.
  2. En Opciones, seleccionar "Distribución P(BHF)/P(ΔEQ)".
  3. Estimar B_mín, B_máx, δ y Γ globales.
  4. Empezar con log10 α = 0 (muy suave) y ajustar.
  5. Reducir α en pasos de 0.5 hasta que aparezca estructura estable en P(BHF).
  6. Usar L-curve α para orientarse sobre el valor óptimo.
  7. Comparar P(BHF) a 3–4 valores de α para identificar rasgos robustos.
  8. Si hay fases discretas, activar "sumar componentes activos nítidos" y configurar los componentes.
  9. Guardar sesión para cada α significativo.

Flujo para P(BHF) Gaussiana/Binomial con nítidos:

  1. Configurar la distribución como arriba.
  2. Seleccionar forma Gaussiana o Binomial.
  3. Activar "sumar componentes activos nítidos".
  4. Configurar los parámetros del nítido (p. ej. singlete o doblete paramagnético).
  5. Ajustar. El programa optimiza simultáneamente la distribución paramétrica y los pesos de los nítidos.
  6. Comparar el RMS con y sin nítidos para verificar que aportan mejora.
"""),
            ("Novedades desde v0.2", "Cambios y funciones nuevas desde la versión 0.2", """
Este capítulo resume, versión por versión, todo lo que ha cambiado desde la v0.2.0 y explica cómo se usa cada función nueva. La versión instalada se ve en Ayuda → Acerca de, y la lista técnica completa en Ayuda → Changelog.

v0.2.0 — Una única aplicación oficial:

  El repositorio se limpió y queda una sola GUI oficial: mossbauer_fe33_gui_v2IA.py. El instalador y las releases usan solo el lanzador "mossbauer" / "mossbauer.bat". No hay que elegir entre variantes: siempre se abre esta aplicación.

v0.2.1 — Ajuste ponderado y comparación de modelos:

  • Ajuste discreto ponderado. El ajuste discreto pesa cada canal por su incertidumbre Poisson (σ ≈ √(cuentas dobladas / 2), normalizada). Es automático: no hay que activar nada. Los canales con más cuentas, menos ruidosos, pesan más.
  • χ² reducido, AIC y BIC. Tras pulsar "Ajustar", el panel "Estado y parámetros" muestra χ², χ² reducido, grados de libertad, AIC y BIC.
  • Cómo comparar dos modelos: ajusta el modelo A y anota AIC y BIC; cambia el modelo (por ejemplo añade un componente) y vuelve a ajustar; el modelo con AIC/BIC más bajo es preferible. Un χ² reducido cercano a 1 indica un ajuste estadísticamente razonable.
  • Áreas por integración numérica. Los porcentajes de área se calculan integrando numéricamente el perfil real de cada componente, de forma consistente para Lorentziana y Voigt.

v0.2.2 — Diagnóstico de modelo y correlaciones:

  • Comparación de modelos. El panel Estado incluye explícitamente el recordatorio de que, a igualdad de datos, el menor AIC/BIC es mejor.
  • Matriz de correlación resumida. Tras un ajuste discreto, el panel Estado muestra la correlación máxima entre parámetros libres y, si hay parejas con |r| ≥ 0.95, las lista con un aviso. Una correlación muy alta indica que esos parámetros no se pueden determinar por separado: conviene fijar uno o ligarlos con una restricción.
  • L-curve de α ampliada. La ventana del botón "L-curve α" muestra también el χ² reducido frente a α, propone un valor "de compromiso" además del codo de la L-curve, y permite guardar la tabla completa del escaneo con el botón "Guardar tabla". Ver el capítulo "P(BHF): parámetros".

v0.2.3 — Diagnóstico de residuos y autoarranque:

  • Diagnóstico de residuos automático. Tras cada ajuste, el panel Estado muestra tres indicadores del residuo: autocorrelación lag-1, test de rachas (z) y correlación antisimétrica. Si alguno se sale de rango aparece el aviso "el residuo parece tener estructura no aleatoria". Ver el capítulo "Diagnóstico" para interpretarlos.
  • Autoarranque múltiple determinista. El ajuste discreto ya no parte de un único punto: prueba automáticamente 9 conjuntos de valores iniciales (el actual más 8 perturbaciones reproducibles) y conserva el de menor coste. Es automático y reduce la dependencia de los valores iniciales. El número de autoarranques probados se indica en el panel Estado.

v0.2.4 — Informe Markdown/PDF:

  Nueva opción Archivo → Exportar informe Markdown/PDF... Genera un informe legible del ajuste actual: se guarda primero un fichero .md y, si se acepta, también un .pdf con una página final con la figura. El detalle del contenido y del procedimiento está en el capítulo "Guardar y exportar".

v0.2.5 — Ventanas de progreso:

  Los cálculos largos abren una ventana de progreso que indica en qué paso van, para que se vea que el programa sigue trabajando. Aparece en: ajustes discretos (muestra el autoarranque en curso), escaneo L-curve de α (muestra el α en curso) y ajustes de distribución P(BHF)/P(ΔEQ), incluido el refinamiento global. No hay que hacer nada: se abren y se cierran solas.

v0.2.6 — Distribuciones pesadas, bootstrap y presets:

  • Distribuciones P(BHF)/P(ΔEQ) ponderadas. El motor Hesse-Rübartsch y el escaneo L-curve pesan ahora cada canal por su incertidumbre Poisson, igual que el ajuste discreto. Es automático.
  • Bootstrap Monte Carlo de errores. Menú Ajuste → Bootstrap errores (MC)... Estima los errores de los parámetros libres por remuestreo. Ver más abajo "Cómo usar el bootstrap".
  • Presets físicos de restricciones. Menú Opciones → Presets físicos de restricciones... Aplica con un clic relaciones físicas habituales. Ver más abajo "Cómo usar los presets físicos".
  • Ajuste del folding point dentro del ajuste. Casilla "Ajustar folding point dentro del ajuste" en el panel "Velocidad, folding y fondo". Ver el capítulo "Folding".
  • Aviso de incertidumbre de calibración Vmax. Si la medida se descargó con su calibración asociada, el panel Estado y el informe muestran la incertidumbre de Vmax (o avisan de que no consta). Ayuda a tener presente el error sistemático de velocidad.

Cómo usar el bootstrap Monte Carlo (v0.2.6):

  1. Carga el espectro y haz un ajuste discreto normal, dejando libres los parámetros deseados.
  2. Abre el menú Ajuste → Bootstrap errores (MC)...
  3. Indica el número de réplicas (por defecto 30; entre 5 y 300). Más réplicas dan un error más estable pero tardan más.
  4. El programa genera espectros sintéticos sumando ruido gaussiano (según la σ Poisson) al modelo ajustado y vuelve a ajustar cada uno.
  5. La desviación típica de cada parámetro entre réplicas sustituye al error 1σ mostrado en el panel Estado.

  Es útil cuando la covarianza del ajuste no es fiable o cuando hay parámetros muy correlacionados. Solo está disponible en modo discreto; para P(BHF)/P(ΔEQ) se valora la estabilidad variando α.

Cómo usar los presets físicos (v0.2.6):

  Abre Opciones → Presets físicos de restricciones... Hay cuatro botones que actúan solo sobre los componentes activos:

  • "Sextetes polvo 3:2:1 (fijar intensidades)": fija las intensidades de los sextetes activos en la relación de polvo sin textura 3:2:1 (poniendo los multiplicadores int1 = int2 = int3 = 1).
  • "Mismas anchuras dentro de cada componente": fija Γ2 y Γ3 (anchuras relativas) en 1, es decir, las líneas 2-5 y 3-4 con la misma anchura que las externas.
  • "Ligar δ de componentes activos a componente 1": añade restricciones para que δ de los componentes 2 y 3 sea igual al δ del componente 1.
  • "Ligar Γ1 de componentes activos a componente 1": añade restricciones para que Γ1 de los componentes 2 y 3 sea igual al del componente 1.

  Las restricciones añadidas se pueden revisar y editar después en Opciones → Restricciones entre parámetros... Los presets no sustituyen al criterio físico: aplícalos solo cuando el supuesto sea válido para la muestra.
"""),
        ]



def get_help_sections_en(voigt_sigma: float = 0.05, settings_path: object = None) -> list:
    """Return the English help chapters: list of (title, heading, content)."""
    settings_path_str = str(settings_path) if settings_path is not None else "(settings)"
    return [
        ("Start", "Start and workflow", """
This program loads, folds, simulates and fits 57Fe Mössbauer spectra.

Recommended workflow:

  1. Load a local file (.ws5, .adt) or download a measurement from the laboratory web database.
  2. Check the folding point and Vmax. If a NORMOS .RES/.PLT sidecar exists, initial values are imported automatically.
  3. Adjust the baseline and verify the normalization.
  4. Choose a model: discrete singlet/doublet/sextet or a distribution P(BHF)/P(ΔEQ).
  5. Fix known parameters and release only the parameters justified by the data.
  6. Run the fit and inspect residuals, areas and correlations.
  7. Save the fit, the full JSON session and/or a Markdown/PDF report.

Notation:

  δ     isomer shift, in mm/s, relative to room-temperature α-Fe.
  ΔEQ   quadrupole splitting, in mm/s.
  BHF   magnetic hyperfine field, in T.
  Γ     line half-width at half maximum, HWHM, in mm/s.
"""),
        ("Mössbauer basics", "Physical background", """
57Fe Mössbauer spectroscopy measures recoil-free resonant absorption of the 14.4 keV gamma ray. The Doppler velocity of the source scans the resonance energy.

Main hyperfine interactions:

  • Electric monopole interaction: isomer shift δ. It reflects electron density at the nucleus and is sensitive to oxidation state and bonding.
  • Electric quadrupole interaction: quadrupole splitting ΔEQ. It reflects the electric field gradient at the nucleus.
  • Magnetic dipole interaction: hyperfine field BHF. It produces the six-line magnetic sextet.

For a randomly oriented powder without texture, ideal sextet intensities follow the ratio:

  lines 1,6 : lines 2,5 : lines 3,4 = 3 : 2 : 1

The relative intensity parameters can be adjusted for textured samples or external-field measurements.
"""),
        ("Files and web", "Data loading and web access", """
Supported input files:

  • Modern WS5 files, XML files with a <data> block.
  • Older ADT files, plain count lists without XML header.
  • NORMOS sidecar files (.RES, .PLT, .JOB) are partially read when present.

Main file actions:

  Load...
    Opens local spectra. If a NORMOS .RES file is found next to the spectrum, the final folding point and starting parameters are imported when possible.

  Web measurements...
    Lists and downloads measurements through the laboratory REST API. Credentials are used to obtain a token; the password is not stored.

  Web calibrations...
    Lists and downloads α-Fe calibrations. If a measurement has an associated calibration, the calibrated Vmax can be applied.

  Save fit...
    Exports a text table with velocity, normalized data, model, residual and folded counts. In distribution mode it also exports P(BHF) or P(ΔEQ).

  Save session...
    Stores the complete state in JSON: data, parameters, fixed/free flags, components, covariance, errors, constraints and calibration traceability.

  Export Markdown/PDF report...
    Creates a human-readable report with parameters, statistics, residual diagnostics, areas, correlations and calibration information. The Markdown file is always kept, even if a PDF is also generated.
"""),
        ("Folding", "Folding, velocity axis and background", """
The folding point is the internal symmetry center used to fold the two halves of the spectrum. Fractional values are supported, as in NORMOS.

Important parameters:

  Vmax
    Maximum velocity of the transducer, used to build the -Vmax ... +Vmax velocity axis. It should normally come from an α-Fe calibration.

  Fit Vmax
    Includes Vmax as a free parameter. This can compensate small calibration errors, but BHF and Vmax are strongly correlated, so BHF should normally be fixed when Vmax is fitted.

  Folding point
    Internal channel center. The GUI also displays an approximate NORMOS folding value.

  Fit folding point
    Includes the folding center as a free parameter in discrete fits. At each iteration the counts are refolded and statistical weights are recomputed. Use it only near a reasonable starting value and with a limited number of free parameters.

  Baseline and slope
    Model the normalized transmission background. Do not use a large slope to hide a wrong folding point.

A wrong folding point often produces antisymmetric positive-negative residual pairs around the absorption lines.
"""),
        ("Discrete model", "Singlets, doublets and sextets", f"""
Each component tab can be configured as a singlet, doublet or sextet.

  Singlet
    One absorption line. Main parameters: δ, Γ, depth and intensity.

  Doublet
    Two lines separated by ΔEQ. Useful for paramagnetic Fe sites with quadrupole interaction.

  Sextet
    Six magnetic lines. Main parameters: δ, ΔEQ, BHF, Γ, depth and relative intensities.

Line profile:

  Lorentzian
    Default profile. Appropriate for natural or homogeneous broadening.

  Voigt
    Convolution of a Lorentzian with a Gaussian of σ = {voigt_sigma:.3g} mm/s. Useful for additional instrumental or static broadening. Areas are computed by numerical integration, so Lorentzian and Voigt profiles are treated consistently.

The Fit button optimizes all non-fixed parameters. The status panel reports RMS, χ²red, AIC, BIC, areas, errors and high correlations when available.
"""),
        ("P(BHF)", "Hyperfine field distribution P(BHF)", """
Distribution mode represents the spectrum as a sum of many sextets with different hyperfine fields. The result P(BHF) is the spectral weight associated with each BHF value.

Method:

  • Define a BHF grid between B min and B max.
  • Each grid point contributes a sextet.
  • Weights are constrained to be non-negative.
  • The second difference of P(BHF) is penalized to avoid non-physical oscillations.

The minimized expression is schematically:

  weighted spectral residual² + α · roughness(P)²

The residual is weighted using Poisson uncertainties estimated from the folded counts. Therefore channels with higher statistical noise contribute less to the cost.
"""),
        ("P(ΔEQ)", "Quadrupole-splitting distribution P(ΔEQ)", """
The distribution variable can be switched from BHF to ΔEQ in the Distribution tab. In that case the grid limits are expressed in mm/s and the model represents a distribution of quadrupole splittings.

Typical uses:

  • Disordered paramagnetic Fe environments.
  • Ferritin-like or amorphous phases.
  • Samples where a single doublet is too simple but a magnetic distribution is not appropriate.

The controls for α, bins, Γ, δ and line shape work in the same way as for P(BHF).
"""),
        ("L-curve", "Choosing the regularization parameter α", """
The L-curve button scans a range of α values and opens a window with:

  • log residual norm versus log roughness.
  • RMS and reduced χ² versus α.
  • the maximum-curvature L-curve suggestion.
  • an additional compromise suggestion.
  • a button to save the complete scan table.

Small α values may overfit noise and create spurious peaks. Large α values oversmooth the distribution and may hide real structure. The L-curve is a guide, not an automatic proof.
"""),
        ("Constraints", "Linear constraints and physical presets", """
Linear constraints impose:

  target = factor · source + offset

The target parameter is removed from the optimizer and updated from the source at each model evaluation.

Typical uses:

  • Equal line widths between components.
  • Equal isomer shifts.
  • Fixed intensity ratios.
  • Reduced number of free parameters when correlations are high.

Physical presets:

  Options → Physical constraint presets...

They can quickly impose powder sextet intensities 3:2:1, equal widths within components, equal δ between active components, or equal Γ1 between active components.
"""),
        ("Statistics", "Weights, model selection and robust errors", """
Poisson weights:

  The fit uses uncertainties estimated from folded counts. The minimized residual is (model - data) / σ.

Reduced χ², AIC and BIC:

  Reduced χ² measures weighted residuals per degree of freedom. AIC and BIC penalize the number of free parameters and help compare models fitted to the same data.

Numerical areas:

  Areas are obtained by integrating the actual component profile on the velocity axis. This is valid for both Lorentzian and Voigt profiles.

Correlations:

  High |r| values in the covariance matrix mean that two parameters are not independently determined. Fixing one parameter, adding a physically justified constraint or simplifying the model may be better than adding more freedom.

Bootstrap Monte Carlo:

  Fit → Bootstrap errors (MC)... generates synthetic spectra by adding noise to the fitted model and refits each replica. The standard deviation of fitted parameters gives a more robust uncertainty estimate for discrete models.
"""),
        ("Diagnostics", "Residuals and common problems", """
The residual, data minus model, should look like random statistical noise.

Common patterns:

  • Antisymmetric positive-negative pairs around lines: wrong folding point.
  • Curved or sloped background: wrong Vmax, normalization problem or real detector trend.
  • Model lines broader than data: Γ too large.
  • Residual peaks in the line wings: consider Voigt profile or a distribution.
  • Structure in distribution mode: α may be too large or the model may be incomplete.
  • High-frequency oscillations in P(BHF): α is probably too small.

The status panel reports lag-1 autocorrelation, a runs-test z value and an antisymmetric residual indicator.
"""),
        ("Saving and reports", "Saving results, sessions and reports", f"""
Save fit (.dat):

  Exports velocity, normalized data, model, residual and folded counts. Distribution fits include the distribution table.

Save session (.json):

  Saves the full working state, including parameters, fixed/free flags, components, covariance, errors, constraints and status text. If calibration metadata are available, they are stored too.

Export Markdown/PDF report:

  Creates a documented report with version, file, folding point, Vmax, calibration, metrics, areas, parameters, errors, correlations and residual diagnostics. If PDF export is selected, the Markdown file is still preserved.

Automatic settings are stored in:

  {settings_path_str}
"""),
        ("Reference values", "Typical 57Fe reference parameters", """
Room-temperature values relative to α-Fe, approximate only:

  α-Fe:          δ ≈ 0.00 mm/s, ΔEQ ≈ 0.00 mm/s, BHF ≈ 33.0 T.
  Fe3+ oct.:     δ ≈ 0.30-0.45 mm/s, ΔEQ ≈ 0.4-1.0 mm/s.
  Fe2+ oct.:     δ ≈ 1.0-1.3 mm/s, ΔEQ ≈ 2.0-3.5 mm/s.
  Magnetite A:   δ ≈ 0.28 mm/s, BHF ≈ 49 T.
  Magnetite B:   δ ≈ 0.65 mm/s, BHF ≈ 46 T.
  Hematite:      δ ≈ 0.37 mm/s, ΔEQ ≈ -0.2 mm/s, BHF ≈ 52 T.
  Goethite:      δ ≈ 0.37 mm/s, ΔEQ ≈ -0.25 mm/s, BHF ≈ 38 T.
  Ferritin:      δ ≈ 0.45-0.50 mm/s, ΔEQ ≈ 0.7-1.0 mm/s.

Temperature, substitutions, particle size and disorder may shift these values.
"""),
        ("What is new", "New functions since version 0.2", """
Recent improvements include:

  • Poisson-weighted fitting for discrete models and distributions.
  • Reduced χ², AIC and BIC.
  • Numerical areas for Lorentzian and Voigt profiles.
  • Parameter correlation summaries.
  • Extended L-curve with reduced χ² and exportable table.
  • Residual diagnostics.
  • Deterministic multi-start fitting.
  • Progress windows for long calculations.
  • Markdown/PDF report export.
  • Bootstrap Monte Carlo errors for discrete fits.
  • Physical constraint presets.
  • Optional folding-point fitting.
  • Calibration uncertainty traceability when available.
"""),
    ]


def get_help_sections(voigt_sigma: float = 0.05, settings_path: object = None, lang: str = "es") -> list:
    """Return help chapters in the selected language ("es" or "en")."""
    if str(lang).lower().startswith("en"):
        return get_help_sections_en(voigt_sigma, settings_path)
    return get_help_sections_es(voigt_sigma, settings_path)
