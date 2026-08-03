# Changelog

## Sin publicar — comodidad de uso de la interfaz

- **El desplazamiento isomérico vuelve a encabezar el panel.** Al mostrar solo
  los parámetros ajustables, un sexteto quedó en 6 controles contra 3 y eso
  disparó el reequilibrio de columnas, que movía el PRIMERO de la columna larga
  pese a que su comentario decía «desde el final»: δ acababa al final de la
  columna derecha, detrás de I23. Ahora mueve el último y el margen sube de 2 a
  3, así que ese caso ni se reequilibra y Γ1/Γ2/Γ3 quedan juntas.
- **La calibración también oculta lo que no aplica**, con el mismo criterio que
  los componentes: σ de Voigt, escala de saturación y Γ de la fuente solo
  aparecen con el perfil o el absorbente que los usa. El panel pasa de 576 a
  441 px (−23 %). El perfil se sigue eligiendo en Ajuste ▸ Opciones avanzadas.
- **Arrastrar y soltar**: soltar un `.ws5`/`.adt`/`.mos` sobre la ventana lo
  abre, un `.json` restaura la sesión y un `.JOB` importa el trabajo de NORMOS
  con su espectro. Lo que no se sabe abrir ni siquiera acepta el arrastre.
- **Autoguardado y recuperación.** Cada tres minutos se vuelca el trabajo en
  curso a `recuperacion.json` (escritura atómica), y si Fitbauer se cerró sin
  guardar, al arrancar ofrece recuperarlo indicando el espectro y la hora. Al
  cerrar bien se borra solo. No sustituye a guardar la sesión: es una red de
  seguridad para las horas de ajuste fino.
- **Atajos del flujo diario**: Ctrl+M inicializar desde mínimos, Ctrl+Shift+M
  autoajustar, Ctrl+E editar mínimos, Ctrl+F liberar todo y Ctrl+Shift+F fijar
  todo. Con los que ya había, el ciclo completo se hace con teclado: abrir
  (Ctrl+O) → arrancar el modelo (Ctrl+M) → ajustar (Ctrl+R) → deshacer si no
  convence (Ctrl+Z) → guardar (Ctrl+S). Verificado que ninguno colisiona.
- **Globo de ayuda en todos los parámetros**, de componente y de calibración,
  sobre la etiqueta, la casilla numérica y la barra —el ratón se posa en
  cualquiera de las tres—. Los que abren menú contextual con el botón derecho
  (ΔEQ el tratamiento del cuadrupolo, las intensidades y la profundidad el modo
  de intensidades, σ el perfil de línea) lo dicen en el globo: sin esa pista el
  menú es invisible, porque nadie prueba el clic derecho sobre una casilla
  numérica si nada lo insinúa. 38 claves nuevas × 8 idiomas = 304 cadenas, con
  un test que falla si alguna queda idéntica al español (que es como se colaría
  una traducción olvidada: `tr()` cae al idioma por defecto).
- **El perfil de línea pasa a ser un desplegable** del panel, junto a los de
  forma de onda y absorbente: los tres eligen el MODELO y este era el único
  escondido tras un clic derecho y un submenú de opciones avanzadas. Con σ
  oculta en modo lorentziano no quedaba ninguna pista visible de que existiera
  el perfil Voigt. Cada desplegable queda ahora justo encima de los parámetros
  que gobierna —σ bajo el perfil, saturación y Γ de la fuente bajo el
  absorbente—, así se ve de dónde salen y por qué aparecen o desaparecen. Los
  tres caminos (desplegable, clic derecho sobre σ y menú Ajuste) quedan
  sincronizados; el radio del menú, que antes no seguía a los otros dos, ahora
  sí.
- **Del parámetro a su capítulo de la ayuda, en un clic.** El globo anuncia
  «Clic derecho ▸ Más información» y esa entrada abre la ayuda directamente en
  el capítulo que explica ese parámetro: Modelo discreto para δ/ΔEQ/BHF/Γ,
  Relajación magnética para los de relajación, Néel-Arrhenius para los de
  tamaño, Folding para vmax/centro/fondo y Perfil de línea para σ. El enlace no
  puede ir dentro del globo —Qt lo cierra en cuanto el ratón sale del control,
  así que un `<a href>` ahí sería inalcanzable—, por eso el globo lo anuncia y
  el menú del clic derecho lo ofrece. Los parámetros que ya tenían menú lo
  reciben al final del suyo; los demás estrenan uno.
  `on_help(chapter="grupo.n")` localiza el capítulo por grupo y posición dentro
  del grupo, no por índice global: los ocho catálogos NO ordenan los capítulos
  igual —el inglés tiene capítulos que el español no— pero sí coinciden en
  cuántos tiene cada grupo y en su orden interno, y un test lo vigila.
- **Aviso al cerrar con trabajo sin guardar**, con Guardar / Salir sin guardar /
  Cancelar. Antes la ventana se cerraba en silencio y el ajuste se perdía, y
  desde el autoguardado era peor: el cierre limpio borra el punto de
  recuperación, así que se iba el trabajo Y la red de seguridad. Si se elige
  Guardar y luego se cancela el diálogo de fichero, la ventana no se cierra.
- **El estado vacío enseña cómo empezar**: «Arrastra aquí un espectro (.ws5,
  .adt, .csv…) o pulsa Ctrl+O». Decía «Carga un fichero .ws5» cuando el
  programa abre ocho extensiones, y desde esta misma versión también acepta
  arrastrar.
- **Copiar resultados** (*Archivo ▸ Copiar resultados*, Ctrl+Shift+C): deja en
  el portapapeles la tabla de parámetros con sus errores, χ², AIC y BIC, en
  texto tabulado que Excel y Origin pegan en columnas. Solo los componentes
  ACTIVOS y los parámetros que su tipo usa: volcarlo todo daban 269 líneas para
  el ajuste de un doblete, y así son 19.
- **La configuración del usuario dejaba de estar a salvo al ejecutar la suite.**
  La ventana guarda sus preferencias sola durante el arranque
  (`_apply_layout_preset` llama a `_save_settings`), y los módulos resuelven
  `~/.config/mossbauer_fe33_gui/` al importarse, así que bastaba con construir
  una `MossbauerQtWindow` en un test para machacar los ajustes reales de quien
  estuviera ejecutando pytest. Medido: `test_layout_presets_change_splitter_sizes`
  cambiaba el `layout_preset` de «Tres columnas» a «Compacto», y los layouts
  personalizados desaparecían. Un fixture autouse de ámbito de sesión en
  `conftest.py` desvía ahora el directorio de configuración a un temporal —
  autouse a propósito: si dependiera de que cada test se acuerde, volvería a
  pasar.
- **`settings.json` se escribe de forma atómica** (temporal + `replace`). Un
  corte a media escritura dejaba un JSON truncado y, como `load_settings`
  devuelve `{}` ante un fichero corrupto, el siguiente guardado lo reemplazaba
  entero: la corrupción se convertía en pérdida total. Y si el fichero existe
  pero no se puede leer, ahora se aparta como `settings.json.corrupto` en vez
  de pisarse, para poder rescatar a mano lo que hubiera dentro.
- Tests: 36 nuevos. Traducciones del diálogo de recuperación en los 8 idiomas.

## v5.0.0 — paridad verificada con NORMOS e interoperabilidad de ficheros

Salto de versión mayor. Tras la revisión completa del código fuente Fortran de
NORMOS (SITE + DIST) contra `core/`, Fitbauer reproduce su física dentro de la
precisión numérica en el núcleo de primer orden, lee y escribe sus ficheros
`.JOB` en los dos sentidos, y se ha contrastado sobre **564 ajustes reales**
hechos con el programa original además del banco sintético de 411 espectros.
En 355 de 503 trabajos comparables (71 %) iguala o mejora su χ² reducido.

El detalle de la comparación está en `validacion/informe/` (cobertura,
veredicto y lo que queda pendiente) y en `jobs/_analisis/` (trabajos reales).

### El panel de simulación vuelve a admitir varios componentes

Al crecer el número de parámetros por componente ya no cabían dos a la vez.
Dos cambios que se suman:

- **Solo se muestra lo ajustable.** La visibilidad pasa de ser por TIPO
  (`USED_BY[kind]`, con lo no aplicable agrisado) a
  `relevant_params(tipo, modo de intensidad, tratamiento del cuadrupolo)`. Un
  sextete de primer orden enseñaba 15 controles de los que solo 9 se podían
  tocar: η, φ, β, Bex, Gax y textura ocupaban 3 filas sin servir para nada.
  Reaparecen al cambiar el tratamiento o el modo de intensidad, que son combos
  siempre visibles, y conservan su valor mientras están ocultos. **397 → 262 px.**
- **Modo compacto** (*Ver ▸ Parámetros compactos*): cada `ParamControl` pierde
  el slider y pasa de dos filas a una. **No esconde ningún parámetro** —el
  spinbox los sigue editando todos—, que es la ventaja sobre un modo
  «básico/avanzado»: no hay que decidir qué es básico ni se corre el riesgo de
  no reencontrar un parámetro. Se aplica también a calibración y distribución,
  porque es una preferencia de densidad de la interfaz. Global y recordado en
  `settings.json`. **262 → 177 px.**

Tres sextetes apilados pasan de **1191 px a 531 px (−55 %)**: donde antes se
veía uno, ahora caben tres. Los tipos sin parámetros condicionales
(Doblete, BlumeTjon, NeelSize) ganan el 31-34 % del modo compacto.

Ocultar es solo presentación: los valores se conservan, `to_view_state()` los
sigue exponiendo y `active_param_keys()` no depende de qué se ve, así que el
ajuste no cambia. Cuatro tests nuevos lo fijan.

### Interoperabilidad con los ficheros .JOB de NORMOS

Fitbauer lee y escribe el formato de trabajo de NORMOS-SITE. **No ejecuta
NORMOS ni lo distribuye**: solo habla su formato de texto, que no es
propietario. Se descartó la alternativa de compilar el fuente como backend
—ver `validacion/informe/PENDIENTE_NORMOS.md`— porque el fuente de 1990 y el
binario de 1993/94 difieren de forma demostrada en al menos cinco puntos, así
que compilarlo NO reproduce el NORMOS con el que se publicó nada.

- **`core/normos_job.py`**: `job_to_model_state()` y `model_state_to_job()`.
- **Importar**: `mossbauer_fit_cli.py --template MI_TRABAJO.JOB` acepta
  directamente un `.JOB` (se detecta por contenido, no por extensión). Un
  usuario que viene de NORMOS abre su fichero de siempre y ajusta con Fitbauer.
- **Exportar**: `--export-job FICHERO` escribe el modelo ajustado en formato
  NORMOS, para comparar allí o compartir la configuración.
- Traslada las conversiones de convenio que salieron de la revisión del fuente,
  que es la parte delicada: `WID` es la anchura de las líneas 3,4 y `gamma1` la
  de las 1,6 (`gamma1 = WID·W13`); `D13`/`D23` son razones de ÁREA e
  `int1`/`int2` de PROFUNDIDAD; `DEP` es el área del subespectro. Verificado
  contra los valores que el banco calculaba a mano para `C2_invertida_b33`, el
  caso con anchuras por par invertidas donde más se separan los convenios.
- Ligaduras `NDEX`/`FACTOR`/`CONST` con la numeración GLOBAL de NORMOS
  (13 + 15·(n−1)), que si se equivoca liga el parámetro que no es en silencio.
- **Avisa de lo que NO traslada** (`POLAR`, `IFSC`, `EFGB`, relajación,
  octete, otros isótopos) y de que `BHF` viene en la escala de NORMOS, que se
  reproduce con `sextet_pattern("normos")`.
- Comprobado que **NORMOS acepta el `.JOB` que escribe Fitbauer**: se generó
  uno, se ejecutó SITE bajo DOSBox y reprodujo la teoría original con
  diferencia exactamente 0, sin avisos.
- **En la GUI**: submenú *Archivo ▸ NORMOS (.JOB)* con importar y exportar.
  Al importar se conserva el espectro y la calibración actuales —el `.JOB`
  apunta a su propio fichero de datos, que aquí no tiene por qué existir— y los
  avisos de la conversión se muestran en un diálogo, porque lo que NO se
  traslada importa tanto como lo que sí. Traducido a los 8 idiomas.
- Tests: `tests/test_normos_job.py` (20 nuevos), incluido el ciclo completo
  importar → aplicar → exportar sobre la ventana real.

#### Los `.JOB` de NORMOS-DIST también se cargan

Antes se rechazaban con un mensaje claro (su `NSUB` son los puntos de una
MALLA, no sitios discretos: importarlos como SITE creaba decenas de sextetos
sin sentido). Ahora se traducen al panel de distribución.

- **`job_to_distribution_state()`**: malla `x_k = X + (k−1)·DTX` con
  `BHF`/`DTB`, `QUA`/`DTQ` o `ISO`/`DTI` según el `METHOD` (1-5 campo,
  6-7 cuadrupolo, 8 desplazamiento isomérico); forma según `DISTRI`
  (histograma / gaussiana / binomial / fija); correlación δ(x) desde `DTI`;
  anclajes de borde desde `BETA1`/`BETA2`; y los sitios cristalinos
  (`NXLS`/`NXLL`/`ISX`/`WIX`/`QUX`/`BHX`/`DEX`) como **componentes nítidos**.
- **En la GUI**: el mismo *Archivo ▸ Importar .JOB* detecta si es de DIST y
  abre el panel P(BHF)/P(ΔEQ) en vez del modo discreto. Nueva clave i18n en
  los 8 idiomas.
- **`DTQ` ya no se traslada en distribuciones de campo.** Los bucles de
  `distcalf.for` para METHOD 1-5 hacen `RH = BHF+PP*DTB`, `RI = ISO+PP*DTI` y
  **no tocan ΔEQ**: un `DTQ` escrito en un `.JOB` de campo no hace nada en
  NORMOS. Trasladarlo metía una correlación inexistente (con `DTQ=0.03` y 40
  puntos, un ΔEQ moviéndose > 1 mm/s).
- Avisa de lo que no traslada: `DISTRI=4` (Czjzek / Le Caër), `METHOD=3`
  (Billard–Chamberod), `METHOD=5`/`7` (P de fichero), varios bloques de
  distribución, `STI`/`STG`, y de que **`LAMDA` no es trasladable 1:1** —es
  absoluta y multiplica `D₂ᵀD₂` sobre cuentas sin normalizar, mientras `alpha`
  es adimensional y normalizado por `λ_ref`—, aunque la razón `BETA/LAMDA` sí
  se conserva. También de que el namelist de DIST **ignora en silencio**
  `NLINE`/`DEP`/`W13`/`W23`… si vienen copiadas de un `.JOB` de SITE.
- Reproducidos los 15 trabajos de DIST reales de `jobs/`
  (`jobs/_analisis/INFORME_DIST.md`): en los 7 comparables **Fitbauer da
  siempre menor χ²** que NORMOS y ⟨x⟩ coincide al 0.1 % en 5 de 6.
- Tests: 12 nuevos en `tests/test_normos_job.py`, incluido que la GUI abre el
  panel de distribución con la malla correcta.

#### Al importar un `.JOB` se carga también su espectro

Un `.JOB` nombra sus ficheros en las cuatro primeras líneas, sin ruta: NORMOS
corría en DOS con todo en el mismo directorio. Antes se importaba solo el
modelo y había que abrir el espectro a mano.

- **`resuelve_fichero_de_datos()`**: busca el espectro declarado junto al
  propio `.JOB`, sin distinguir mayúsculas —vienen de DOS y la caja rara vez
  casa—, cayendo al nombre del trabajo y, si no, al único espectro de la
  carpeta. Nunca devuelve una salida de NORMOS (`.RES`/`.PLT`). Resuelve casos
  como `YU30031D.JOB → YU300317.ADT`, donde el nombre no coincide con el del
  trabajo. Si no encuentra nada, conserva el espectro cargado y lo avisa.
- **`PFP` deja de imponerse como centro.** En NORMOS es la SEMILLA de la
  búsqueda del punto de doblado, no el punto final: `normospr.for` la refina en
  dos ciclos, y en varios trabajos reales el `.RES` acaba a más de un canal del
  `PFP` que pedía el `.JOB`. Se informa como metadato y se avisa, pero manda la
  búsqueda de Fitbauer, que es el análogo correcto.
- **`punto_de_doblado_normos()`**: el punto continuo que NORMOS imprime tampoco
  es donde dobla. Su rutina final (`normospr.for:601-604`, «ohne
  Interpolation», Hoersten 1989) lo trunca y suma canales enteros
  (`Y(IPFA-L+1) + Y(IPFA+L)`), con el eje en `⌊PFP⌋ + 0.5`. Reproducir sus
  ajustes exige doblar ahí.

### Polarización de poblaciones y bloque de distribuciones

#### Relajación: poblaciones desiguales (cierra el hueco del nivel 9)

- Nuevo parámetro `relax_polarization` (P ∈ [−1, 1]) del componente
  `BlumeTjon`: desequilibra las poblaciones de los dos estados,
  `p± = (1 ± P)/2`. Es el `SPN = BHF/BSAT` de NORMOS, o sea el efecto de un
  campo externo que polariza los dos estados. Con P=0 (defecto) nada cambia.
- **Reproduce `ISIRLX` EXACTAMENTE** (rms < 10⁻¹², no aproximadamente) tanto
  con P=0 como con P≠0, con `k = OME/2`.
- Corrección de la conclusión del nivel 9: el residuo del 2 % que se había
  medido era un artefacto del test, no del modelo — NORMOS usa DOS anchuras
  (`WD` en los autovalores y `WDS` en la convolución) y contarlas ambas
  duplicaba Γ. Con la correspondencia correcta (`WD=0`, `WDS=Γ`) la
  equivalencia es exacta y `k = OME/2` no es asintótico sino exacto.
- La forma polarizada **no se recorta a ≥0**: con poblaciones muy desiguales
  tiene regiones negativas (hasta el 27 % de los canales con P=0.9) y NORMOS
  tampoco las recorta. Se comprueba que el área se conserva (`AC+BD = 1`).
- Verificado que un sexteto NO se asimetriza con P, y no debe: los dos estados
  entre los que salta (+B y −B) dan el mismo espectro estático.

#### Bloque DIST (distribuciones)

- **Matriz de suavizado idéntica**: `SMOOTH` (`distauxl.for`) monta `λ·D₂ᵀD₂`
  con diagonal `[1,5,6,…,6,5,1]`, exactamente el penalizador Tikhonov de aquí
  (comprobado elemento a elemento para varios tamaños).
- **Anclajes de borde**, que faltaban: `edge_anchor` (los `BETA1`/`BETA2` de
  NORMOS) fuerza P→0 en el primer y último bin. Van con peso PROPIO, no
  multiplicados por α — igual que en NORMOS, que los suma a las esquinas
  después de escalar por λ. En forma de raíz cuadrada son dos filas `√β·e₀ᵀ`
  y `√β·e_{n−1}ᵀ`. CLI: `--edge-anchor`.
- **Diagnóstico `edge_pileup`** en el resultado, que es lo verdaderamente
  accionable: `max(P[0], P[−1]) / max(P)`. Si la distribución real se sale de
  la malla, Hesse–Rübartsch no tiene dónde poner ese peso y lo APILA en el bin
  extremo. Medido: una gaussiana centrada en 45 T con la malla truncada a
  0–40 T deja el último bin al 100 % del máximo y hunde ⟨B⟩ de 44.9 a 28.5 T.
  Con la malla amplia el indicador baja a 0.01.
- Dicho con claridad: el anclaje encarece ese refugio pero **no arregla una
  malla mal elegida** (la información no está en los datos); por eso lo que se
  añade es sobre todo el diagnóstico.
- Tests: `tests/test_distribucion_normos.py` (9), con un port literal de
  `SMOOTH` como referencia, y 8 nuevos de polarización en
  `tests/test_relajacion_normos.py`.

### Hamiltoniano y relajación verificados

Niveles 8 y 9 de la revisión del código fuente de NORMOS. **Ninguno de los dos
requiere corregir nada en Fitbauer**; lo que aportan es verificación y el
inventario de lo que sigue faltando.

#### Hamiltoniano completo (`sitegmfp.for`, GMFP de Ruebenbauer–Birchall)

- Las 8 energías de transición de Fitbauer coinciden con una diagonalización
  **independiente** —escrita desde cero en el test, con el excitado I=3/2
  (cuadrupolo y η) y el fundamental I=1/2 diagonalizados por separado y el
  campo en dirección arbitraria— a **1.8·10⁻¹⁵**, precisión de máquina.
- Confirmado que el modelo es el mismo que `HMLTN`: EFG en z y campo rotado,
  cuadrupolo solo si S>1/2, suma **incoherente** entre canales q en polvo y
  **coherente** en cristal único (que es la diferencia entre
  `full_hamiltonian_lines` y `full_hamiltonian_lines_sc`).
- El **Goldanskii–Karyagin** de NORMOS resulta ser un peso por canal q, con
  `B=sqrt(|G|)` aplicado a la AMPLITUD (`sitecalf.for:874`); equivale
  exactamente a los pesos `int1`/`int2` que aquí multiplican la INTENSIDAD, así
  que la capacidad ya estaba, solo con otro nombre.
- Ampliada la atribución de la desviación de SITE (además del diagonalizador
  EISPACK general en precisión simple): `IERR` nunca se comprueba tras la
  llamada, y `MACHEP = 2⁻⁴⁷` es la épsilon de DOBLE precisión en código
  `REAL*4`, seis órdenes por debajo de lo alcanzable, así que su iteración QR
  no puede converger a su propio criterio.
- Capacidad que sigue faltando: **mezcla multipolar M1+E2** (`AMIX`/`PHASE`).
  Irrelevante para ⁵⁷Fe, cuyo `MIX=0` está cableado en el propio SITE.

#### Relajación (`siterelx.for`)

- **Primera validación de la relajación de Fitbauer.** Con el binario del demo
  no era comprobable (§19: `BSAT` no está en su namelist y sus espectros
  `IRELAX` salen colapsados incluso con `OME=0`); con el fuente sí se puede
  contrastar la fórmula. `ISIRLX` es la forma cerrada de Blume para dos estados
  ±B_hf, y `two_state_exchange_profile` reproduce su forma con un residuo
  **≤2 % del pico** en todo el rango de tasas, y del 0.1 % en relajación
  rápida: es el mismo modelo con otra parametrización.
- El mapeo `k ↔ OME` **no es una constante**: tiende a `k = OME/2` en el límite
  rápido, pero en el lento la forma apenas depende de la tasa y el cociente se
  dispara. Por eso no se publica un factor de conversión único.
- Capacidad que sigue faltando: **poblaciones desiguales** (`SPN = BHF/BSAT`),
  o sea relajación con un campo externo que polariza los dos estados. Se
  comprueba que no es un caso degenerado: con SPN=0.6 el espectro deja de ser
  simétrico, así que la asimetría no la absorbe la tasa.
- Tests: `tests/test_hamiltoniano_normos.py` (9) y
  `tests/test_relajacion_normos.py` (10), con un port literal de `ISIRLX` como
  referencia.

### Estadística del ajuste: barras de error

Nivel 7 de la revisión del código fuente de NORMOS.

- **Las σ dejan de reescalarse por χ²red** (`absolute_sigma=True`, nuevo campo
  de `FitState`). La incertidumbre por canal es la estadística de conteo, que
  se conoce, así que la barra debe salir solo de ella — es lo que hace NORMOS
  (`normospr.for`: `ERX = SQRT(BB(i,i))`, con la línea que dividiría por χ²
  comentada en el propio fuente). Reescalar hacia abajo cuando χ²red < 1 daba
  barras por debajo del límite de Poisson, que no tiene sentido físico.
  Se sigue reescalando cuando las σ NO son absolutas (sin `sigma_data`, o modo
  Poisson sin `norm_factor`, donde el residual usa √m).
  - Contrastado con un ajuste real de SITE (K4 del banco): los errores pasan de
    coincidir al 1.4–6.2 % a coincidir al **0–4 %**, con `s1_delta` exacto.
- **Error de los parámetros LIGADOS**, que no se reportaba: se propaga
  `σ_target = |factor|·σ_source` (el offset no aporta incertidumbre), con
  soporte de cadenas. NORMOS sí lo da pero **mal**: `siteauxl.for:539` hace
  `PE(K)=ABS(CONST(K))*PE(L)`, usando el OFFSET donde toca el FACTOR, así que
  una ligadura multiplicativa pura (`CONST=0`, el caso más común) sale con
  error CERO.
- Validación Monte Carlo de las barras (150 réplicas con ruido Poisson y
  modelo exacto): χ²red = 1.0008 y las σ reproducen la dispersión real dentro
  de la precisión del test (±6 %). Se descartó que la redetección del punto de
  doblado contribuyera: fijándolo, los ratios no se mueven.
- Verificado equivalente: los pesos (`RRTY = 1/√Y` sobre las cuentas dobladas)
  y la forma de las ligaduras (`FACTOR·fuente + CONST`).
- Corrección de una nota anterior: el χ² del `.RES` divide por los **datos**,
  no por el modelo, con DF = NP−1−NVAR (comprobado: 1.0282 frente al 1.028
  que imprime SITE). Fitbauer usa DF = NP−NVAR, un 0.4 % de diferencia.
- Tests: `tests/test_estadistica_normos.py` (13 nuevos).

### Integral de transmisión: FSO y kernel de la fuente

Nivel 6 de la revisión del código fuente de NORMOS (rama `IFTRAN`).

- **Fracción resonante de la fuente (FSO), capacidad que faltaba**: nuevo
  parámetro global ajustable `src_frac`, activo solo con
  `absorber_model="transmission"`. La transmisión pasa a
  `T = baseline − f_s · L_src ⊗ [1 − exp(−τ)]`: solo una fracción de los
  fotones que llegan pertenece a la línea Mössbauer, así que la absorción
  satura en `1 − f_s` y no en 0. Con 1 (el defecto) no hay cambio. **No es
  degenerado con la profundidad** salvo en el límite fino: `depth` escala τ
  dentro de la exponencial y `f_s` escala el resultado ya saturado.
  - Sonda sobre el binario demo: FSO está **operativo** y la fórmula del
    fuente lo describe exactamente — con FSO=0.7 la base medida es
    1−0.7+0.7·0.996811 = 0.997768 y el mínimo 1−0.7+0.7·0.239481 = 0.467637.
  - Reproduciendo el algoritmo completo del fuente (malla VTRA, regla del
    rectángulo y corrección WING) con NTRA=600 se recupera el `.PLT` del
    binario con rms **2.7·10⁻⁷**: el fuente de 1990 y el binario de 1994 son
    el mismo código en esta rama.
- **Kernel de la fuente 19× más exacto**: se truncaba a ±20 FWHM y se
  **renormalizaba**. La Lorentziana tiene colas ~1/v², así que a ±20 FWHM
  falta un 1.6 % del peso y renormalizar lo redistribuye al centro, falseando
  la absorción. Ahora la ventana es ±200 FWHM (acotada a 4× la malla) y **no
  se renormaliza**: el déficit se deja fuera, que es justo lo que hace el
  `WING` de NORMOS (allí no hay absorción). El rms del modelo frente al
  binario baja de 2.8·10⁻³ a 1.5·10⁻⁴, y con ello el sesgo al recuperar FSO
  de −2.5 % a −0.0…+0.4 % y el de Γ de −2.1 % a ±0.4 %.
- **CLI**: `--src-frac` en `mossbauer_fit_cli.py`.
- **Serie N del banco** (`validacion/generador/series_N.py`): round-trip con
  FSO ∈ {0.40, 0.55, 0.70, 0.85, 1.00} sobre absorbente grueso (N1), FSO fijo
  con TAB ∈ {2, 5, 10, 30} (N2) y un control de degeneración (N3).
  FSO se recupera a **+0.6 %** en N1 con δ exacto y Γ a +0.3 %. N2 muestra que
  el parámetro **solo es medible si el absorbente satura**: con TAB=2 queda
  indeterminado (σ=0.27), con TAB=30 sale a +0.4 %. N3 confirma que en el
  límite fino el ajuste no lo inventa — devuelve 1.0 con σ=19, es decir
  declara la degeneración, y δ/Γ salen exactos igualmente.
- Diferencia residual documentada: el sesgo que queda (+0.6 % en FSO, +1.4 %
  en Γ a vmax=10 y +0.4 % a vmax=4) es la **discretización de la convolución
  de SITE**, que evalúa todo en su malla `VTRA` de paso `DELV`. Se comprobó
  imitando su kernel muestreado puntualmente: ajusta PEOR (rms 8.1·10⁻⁶ frente
  a 3.7·10⁻⁶), así que el kernel integrado por canal de Fitbauer es el más
  exacto de los dos y el residuo es suyo, no nuestro.
- Tests: `tests/test_transmision_normos.py` (14 nuevos).

### Doblado con interpolación cúbica

Nivel 5 de la revisión del código fuente de NORMOS (folding).

- **La interpolación lineal subcanal del doblado ensanchaba las líneas.** Es un
  filtro paso bajo: al promediar canales vecinos infla Γ. Medido sobre un
  sexteto sintético (Γ = 0.28 mm/s, 512 canales), el Γ ajustado salía hasta un
  **9.5 % alto**. El error escala como `f·(1−f)` con `f` la parte fraccionaria
  del canal emparejado, así que con centro **semientero** —el caso habitual, y
  el de todo el banco de validación— no hay interpolación y no había sesgo.
- **`FOLD_INTERP_ORDER_DEFAULT = 3`**: el doblado pasa a interpolación cúbica
  (B-spline interpolante + extrapolación lineal en bordes). Reduce el sesgo de
  Γ a un 2.8 % (factor 2–4) y, de paso, el doblado es **6.7× más rápido**
  (61.8 µs frente a 412 µs) al vectorizarse y cachear la spline. El orden se
  resuelve en tiempo de ejecución y se puede fijar por llamada (`order=1`
  reproduce el resultado histórico exacto).
- La spline es **global**, así que se construye excluyendo los `edge_trim`
  canales de cada extremo al buscar el folding point: sin eso, un canal 1
  muerto (habitual en ADT reales) se propagaba hacia el interior con peso
  ~0.27 por canal y desplazaba el centro detectado 0.056 canales.
- **Golden recalibrado**: Γ baja en los cuatro espectros de referencia
  (−6·10⁻⁵ siderita, −4·10⁻⁴ jarosita, −9·10⁻⁴ αFe, −2·10⁻³ hematita) y
  `depth` sube compensando (el área se conserva); δ/BHF/ΔEQ no se mueven. El
  χ²red sube un 2–4 % porque la interpolación lineal suavizaba también el
  RUIDO y deprimía el χ² artificialmente. El banco NORMOS no cambia
  (2·10⁻¹⁰ sobre 10⁶ cuentas: sus espectros tienen PFP = 256.5).
- Documentación matemática ES/EN actualizada (§7.3, §7.7) con el contrato
  numérico nuevo.
- Descartado tras medirlo: la **parábola de 9 puntos** de NORMOS para refinar
  el mínimo de χ² es PEOR que la de 3 (sesgo +0.049 vs +0.015 canales — la
  χ²(c) no es parabólica en esa ventana), el refinamiento por Brent no cambia
  nada (el mínimo real ya está ahí), y la corrección del **efecto geométrico**
  que NORMOS resta antes de buscar el centro no lo mueve
  (+0.0006 canales con una amplitud del 2 % de la base), porque el término es
  antisimétrico y contribuye a la χ² de simetría casi igual para todo centro.
- **Efecto geométrico** (`geometry_effect_amplitude` / `remove_geometry_effect`),
  portado de `normospr.for`: modulación de la tasa de cuentas con la POSICIÓN
  del transductor, modelada como `A·sin(π(i−c)/PHALF)` y ajustada por mínimos
  cuadrados sobre las diferencias espejo. Es un **diagnóstico**, no una
  corrección: al doblar se cancela exactamente, así que no toca el ajuste. Se
  expone en `HeadlessSession.geometry_effect`, en el payload de sesión y en el
  resumen del CLI, con aviso si supera el 1 % de la base. En los espectros de
  referencia sale a 3–6·10⁻⁵ (espectrómetro sano).
- **Dos ciclos de búsqueda del folding point** (`CENTER_SEARCH_CYCLES = 2`),
  como NORMOS: el primero localiza en la ventana ancha, se resta el efecto
  geométrico estimado con ese centro y el segundo refina en ±6 canales (el
  `MS=25` de NORMOS). Sobre un sexteto sintético con centro 255.77 el error
  pasa de +0.0036 a −0.0006 canales.
- **Se dejan de perder los canales de borde**: `EDGE_TRIM_DEFAULT` pasa de 1 a
  **0** y el recorte lo decide `edge_outlier_trim` mirando los datos — solo se
  van los extremos que sean canales muertos de verdad (caída >20 % respecto a
  sus vecinos; un canal a cero deja el punto doblado al 50 %). El espectro
  doblado pasa de N/2−2 a **N/2 puntos**. El recorte fijo tiraba dos puntos
  buenos: el primero del array doblado promedia los canales adyacentes al
  vértice, los más fiables, y solo el último toca los extremos. `velocity_axis`
  deduce ahora el recorte del número de puntos, así que la escala no se estira
  con el recorte adaptativo. Unificado con la GUI Qt (`_edge_trim`) y con
  `core.session`, que forzaba su propio 1 y anulaba la mejora en el CLI.
  El guardia de la BÚSQUEDA del centro se mantiene aparte
  (`CENTER_SEARCH_EDGE_GUARD = 1`): ahí sí hace falta.
- Golden recalibrado por tercera vez al conservar los 2 canales; todos los
  parámetros se mueven ≤2·10⁻⁴.
- Tests: `tests/test_folding_interp.py` (22 nuevos).

### Asimetría de línea (AKS) y convenio de intensidades

Nivel 1 de la revisión del código fuente de NORMOS (forma de línea).

- **Asimetría de línea por interferencia (AKS de NORMOS-SITE)**, capacidad que
  faltaba: nuevo parámetro global ajustable `line_asym`, que multiplica cada
  perfil por `1 − A·(v−v₀)/Γ` (`LORLIN`, `siteauxl.for:638`). Con 0 (el
  defecto) el modelo es idéntico al histórico. Vive en
  `core.physics.lorentzian`, así que lo heredan el sexteto discreto, el
  Hamiltoniano completo y el kernel de distribución.
  - Sonda sobre el binario demo 27.01.1994: AKS está **operativo** (no es de
    los interruptores inertes del demo) y la fórmula del fuente de 1990
    describe al ejecutable — rms 1.2·10⁻⁴, el suelo de precisión de su
    `.PLT`, frente a 5.9·10⁻³ con el signo invertido.
  - Divergencia deliberada: SITE aplica AKS solo a la mitad lorentziana de su
    pseudo-Voigt (su `GAULIN` lo ignora); aquí se aplica al perfil completo.
- **Convenio de razones de intensidad** `core.physics.intensity_convention`:
  `"depth"` (histórico, razones de profundidad) o `"area"` (razones de ÁREA).
  El patrón 3:2:1 son probabilidades de transición, o sea **áreas**, y es lo
  que significan D13/D23 en NORMOS; con `gamma2`/`gamma3` libres los dos
  convenios se separan hasta un 100 % en A13. Opt-in: el defecto no cambia
  porque cambiaría el significado de los parámetros de sesiones guardadas.
- **CLIs**: `--line-asym` y `--intensity-convention` en `mossbauer_fit_cli.py`
  y en `fit_bhf_distribution_cli.py`.
- **Serie M del banco de validación** (`validacion/generador/series_M.py`):
  round-trip SITE→Fitbauer con AKS ∈ {−0.40, −0.15, +0.10, +0.30, +0.60}
  sobre singlete (M1), doblete (M2) y sexteto con intensidades libres (M3),
  más un control sin AKS (M4). `line_asym` se recupera a 5·10⁻⁶ (M1/M2) y
  3·10⁻³ (M3, degenerado con D13/D23); el control devuelve 0 (−3·10⁻⁵), es
  decir no inventa asimetría donde no la hay. Todos los |z| ≤ 2.3.
  `depth` se excluye de la comparación en esta serie: con asimetría fuerte
  casi la mitad del espectro queda por encima de la base y el percentil 90
  con el que el banco normaliza reescala todo ~0.2 %, arrastrando a `depth` y
  `baseline` juntos (su cociente sigue exacto a 4·10⁻⁶).
- No se corrige: el pseudo-Voigt de David (1986) es la aproximación de SITE
  —Fitbauer usa el Voigt exacto—, y que SITE descarte en silencio las líneas
  con área ≤ 0 es una diferencia de robustez a nuestro favor.
- Tests: `tests/test_forma_linea_normos.py` (19 nuevos).

### Convenio de posiciones del sexteto seleccionable

Primer resultado de la revisión sistemática del código fuente de NORMOS
(nivel 0: constantes y patrón de líneas).

- **Hallazgo**: SITE deriva las posiciones del sexteto de los momentos
  nucleares (`sitecalf.for` INIFUN: GFACT=0.090604, GFR=−0.5714, Eγ=14.4 keV),
  no del patrón publicado de α-Fe que usa Fitbauer. A 33 T da
  ±5.326107 / ±3.083577 / ±0.841047 frente a ±5.3285 / ±3.0835 / ±0.8385.
  **La diferencia no es una escala**: la razón de momentos de SITE (−1.7142)
  no es la que implica α-Fe (−1.71723), así que tras el mejor factor de
  escala queda un residuo IRREDUCIBLE de ±2.8·10⁻³ mm/s en las líneas
  internas — es antisimétrico, ni δ ni ΔE_Q lo absorben. Verificado contra el
  binario demo 27.01.1994 ajustando un sexteto sintético del banco: el
  ejecutable coincide con la fórmula del fuente a 6·10⁻⁶ mm/s.
- **`core.constants.sextet_pattern(nombre)`** — convenio seleccionable con
  gestor de contexto (mismo patrón que `core.physics.line_profile`):
  `"alpha_fe"` (por defecto, sin cambios) y `"normos"`. Como todo el núcleo
  deriva de esta única fuente, el convenio gobierna a la vez el sexteto de
  primer orden, el Hamiltoniano completo (ω_e/ω_g pasan a leerse del patrón
  activo en vez de ser constantes congeladas), Blume–Tjon y el kernel de
  distribución.
- **CLIs**: `--sextet-pattern {alpha_fe,normos}` en `mossbauer_fit_cli.py` y
  en `fit_bhf_distribution_cli.py`.
- **Efecto medido** sobre el espectro `B1_x1` del banco (SITE, BHF=33 T):
  con `alpha_fe` Fitbauer recupera 32.9860 T (−0.014 T) y con `normos`
  32.999995 T, bajando el rms del residuo de 3.3·10⁻⁵ a 2.6·10⁻⁶. Esto
  sustituye al factor global `k=0.9996195` que se venía usando para comparar
  con NORMOS, que solo era exacto con anchuras de línea iguales (el k
  efectivo va de 0.99957 a 0.99984 según W13).
- Tests: `tests/test_patron_sexteto.py` (9 nuevos). El comportamiento por
  defecto no cambia.

### Fuente polarizada y hallazgos del código fuente de NORMOS

Con el código fuente de NORMOS disponible localmente (propietario, excluido
del repositorio) se cerró la última capacidad pendiente y se corrigieron
atribuciones (informe §19):

- **Fuente polarizada** (paridad METHOD=4/POLAR de NORMOS-DIST):
  `polarized_sextet_absorption` — peine de 36 líneas fuente×absorbente con
  intensidades por selección de helicidad desde primeros principios
  (I(i,j) ∝ |m_q(i)|²|m_q(j)|² Σ_λ |d¹_{q_iλ}(θ_s)|²|d¹_{q_jλ}(θ_a)|²).
  Validada contra el binario de DIST a 0.4 % del pico (θ_s=0) y 1.1 %
  (θ_s=90); round-trip del banco (L7): ⟨B⟩ a 0.08 T. Disponible como
  kernel de distribución (`kernel_treatment="polarized"`) y en el CLI
  (`--source-polarized --source-bhf --source-theta --absorber-theta`).
  Tests: 3 nuevos en tests/test_mejoras_v4_19.py.
- **Corrección de atribución**: la desviación del HAMILT de SITE-1994 no es
  una aproximación analítica (su GMFP es exacto, incluida la coherencia del
  fundamental) sino DEGRADACIÓN NUMÉRICA de su diagonalizador (EISPACK
  complejo general en precisión simple, autovectores sin ortonormalizar).
  La conclusión práctica no cambia: Fitbauer es más exacto.
- **Voigt de SITE resuelto**: el binario 1994 usa STG(n) como σ gaussiana
  (mm/s en paramagnéticos — la misma convención de Fitbauer —, Tesla en
  sextetes); deja de ser "no validable".
- **Serie V (Voigt) validada**: round-trip σ paramagnética a ≤4e-3 mm/s
  (σ libre en el ajuste discreto) y σ_B magnética exacta con la forma
  Gaussiana de distribución.
- **Fuente polarizada expuesta en la GUI Qt**: casilla + B fuente + ángulos
  en el panel de distribución, con sesión, i18n (8 idiomas), manuales y
  test de cableado.
- Relajación cerrada como no-validable con el binario (BSAT ausente del
  namelist; espectros colapsados incluso con OME=0): física de referencia
  identificada (Blume de dos estados, OME en mm/s), cableado del demo
  irreproducible por caja negra.
- Resueltos además: EXACT (perturbativo en R=−14.755·QUP/H; S2T comparte
  ranura con D23), GAX (+90° = convención zxz del binario), IFGK inerte con
  IFSC, IFTRAN idéntico al de Fitbauer, convenio BKG exacto, relajación con
  OME en mm/s (mapeo completo pendiente).

### Auditoría y endurecimiento de la suite de tests

Tras cazar el bug de la ventana en blanco (un test de presets usaba nombres
inexistentes y pasaba ejercitando el fallo), se auditó la suite completa
buscando esa clase de problema (tests que pasan sin verificar lo que dicen),
con verificación por mutaciones deliberadas del código:

- **Validación estricta de `treatment`** en `core.physics.sextet_absorption`
  y en el kernel de distribución: un tratamiento desconocido (typo, valor
  antiguo) caía EN SILENCIO al 1er orden — misma clase que el bug de
  presets; ahora lanza `ValueError`.
- **Test nuevo del sector de interferencia** del cristal único: una mutación
  del signo de la matriz d¹ (o de la fase e^{−iqφ}) pasaba la suite porque
  los tests axial/isótropo no ven la interferencia; ahora se compara contra
  la fórmula independiente de radiación M1 transversal (|A|²−|k̂·A|²).
- **Test de cobertura i18n**: toda clave `tr("...")` estática del código
  debe existir en el catálogo (antes una clave inexistente caía al default
  sin detectarse).
- ~20 endurecimientos más: el test del preset 3:2:1 ahora ejecuta el código
  de producto (extraído como `apply_preset_321`); los Monte Carlo de
  calibración de σ fallan ruidosamente si el motor deja de reportar errores
  (antes pasaban con cero aserciones); la familia "recuperación" arranca
  desplazada de la verdad (un ajuste no-op ya no pasa); estilos de gráfico
  verificados contra el registro y el rc aplicado; aserciones tautológicas o
  invertibles corregidas; fugas de estado global (Qt estáticos, perfil
  Voigt) restauradas en finally. Suite: 352 tests.

## v4.19.0 — tres capacidades de paridad con NORMOS: cristal único, kernel Hamiltoniano en distribuciones y fondo v³/v⁴

Cierra tres de las cuatro capacidades que el veredicto del banco
(validacion/informe/VEREDICTO.md) señalaba como "lo que le falta a Fitbauer
para llegar a NORMOS" (queda solo la fuente polarizada, bajo demanda):

- **Cristal único / muestra orientada** (`quad_treatment="hamiltonian_sc"`):
  el haz γ deja de promediarse isótropo y toma dirección fija (parámetros por
  componente `bex`/`gax`, polar/azimutal en el marco del EFG) con suma
  COHERENTE entre canales de radiación (matriz de Wigner d¹). En el límite
  axial reproduce los patrones clásicos 3:0:1 (haz ∥ B) y 3:4:1 (haz ⊥ B) y
  su promedio isótropo recupera el polvo a 1e-15. Equivale al IFSC/BEX/GAX de
  SITE; re-ajuste del banco K3: χ²red 3.5–20 → 2.3–3.4 con intensidades
  FIJAS (el residuo restante es la aproximación de SITE-1994). Convención
  descubierta: el GAX del demo está desplazado 90° del azimut geométrico.
- **Kernel Hamiltoniano en distribuciones** (`kernel_treatment="hamiltonian"`
  en el panel de distribución y `--kernel-treatment hamiltoniano` en el CLI):
  cada columna del kernel P(BHF) es el promedio de polvo del Hamiltoniano
  completo (EFG aleatorio, control η); ΔEQ pasa a ser el módulo del EFG —
  análogo exacto (no perturbativo) del EXACT/QUP de NORMOS-DIST. La textura
  del kernel va ligada a B (marco del campo, nueva
  `full_hamiltonian_lines_field`). Round-trip sintético: momentos exactos;
  banco L4: σ a QUP=1 pasa de +2.4 T (1er orden) a +1.0 T (resto =
  aproximación perturbativa del propio EXACT).
- **Fondo cúbico/cuártico** (`curv3`/`curv4`, panel de calibración): paridad
  con BKG(4)/BKG(5) de NORMOS; banco K2: el fondo cúbico pasa de χ²red 2.5
  (sesgo documentado) a exacto, y el cuártico nuevo se recupera a 3 cifras.

Todo expuesto en la GUI Qt (menú contextual de ΔEQ, panel de distribución,
calibración) con sesiones, i18n en 8 idiomas y manuales ES/EN recompilados.
Tests nuevos: tests/test_mejoras_v4_19.py (11). Validación:
validacion/generador/valida_v4_19.py e informe §18.

Corrección: si el layout guardado en los ajustes referenciaba un preset o
layout personalizado que ya no existe tras actualizar, la ventana arrancaba
EN BLANCO (todos los paneles ocultos). Ahora un nombre huérfano o un spec
sin paneles cae automáticamente al preset por defecto (test de regresión en
tests/test_qt_app.py).

## v4.18.1 — 2ª ampliación del banco NORMOS (series K/L) y tres ajustes de paridad

Con el manual de NORMOS (Brand 1990) se amplió el banco de validación con
pruebas de **extremos y centro** de cada capacidad de SITE/DIST que faltaba
(octetes NLINE=8, fondos BKG(k), cristal único IFSC, ligaduras nativas NDEX,
binomial CONC, Czjzek, PNEG, EXACT, textura D23 en distribuciones; informe
§16, ~50 espectros y ~230 filas nuevas). Tres huecos de paridad detectados y
corregidos (tests en `tests/test_mejoras_banco_normos2.py`; suite 337):

- **`wide_delta` amplía también ΔEQ** a ±2·(v_max+2): SITE admite dobletes
  con ΔEQ=5 y la cota clásica ±4 degeneraba el ajuste (caso K5_dob_q5:
  χ²red 82 → 1e-7).
- **Cota de `slope` ±0.005 → ±0.02**: los fondos lineales de NORMOS
  (BKG(2)) alcanzan 7.5e-3 mm/s⁻¹ (caso K2_lin_p60: χ²red 61 → 3e-7).
- **`--d13`/`--d23` en `fit_bhf_distribution_cli.py`**: textura del kernel
  de distribución (convenio de áreas NORMOS-DIST; el kernel 3:2:1 fijo
  sesgaba σ hasta +134 % con D23≠2, serie L6).

## v4.18.0 — cuatro extensiones de modelo derivadas del banco de validación NORMOS

Un banco round-trip contra NORMOS-SITE/DIST (327 espectros sintéticos, ~850
ajustes; `validacion/informe/INFORME.md`) localizó los sesgos de modelo de
Fitbauer. Esta versión los elimina con cuatro extensiones **opt-in** (el
comportamiento por defecto no cambia; los 310 tests previos pasan intactos):

- **Hamiltoniano estático completo** (`quad_treatment="hamiltonian"`):
  diagonalización general con EFG no axial (nuevos parámetros por componente
  `eta`, `phi`) e **intensidades de transición calculadas desde los
  autovectores** (Clebsch-Gordan, promedio isótropo del haz, 8 líneas con las
  ΔmI=±2 incluidas; regla de suma conservada). Sesgo mediano del banco:
  |ΔBhf| ×23 menor en A4 (axial) y ×33 en A5 (η≠0). Nota: a mezcla fuerte la
  implementación es MÁS exacta que NORMOS-SITE 1994, que degrada numéricamente los autovectores en su diagonalizador
  (confirmado en el código fuente, informe §19) y viola la invariancia rotacional
  (demostrado en el informe §13).
- **Integral de transmisión** (`absorber_model="transmission"`): T = base −
  L_fuente ⊗ (1 − exp(−τ)) con kernel de fuente integrado por canal
  (`src_fwhm`, fijo por defecto en 0.097 mm/s) y `depth` como profundidad
  óptica (límite del ajuste relajado a 5 en este modo). Γ recuperada a
  ≤0.02 mm/s hasta t_a=30 (antes: +0.09 a t_a=10 con modelo fino).
- **Curvatura de base** (global `curv`, fijo a 0 por defecto): absorbe el
  efecto geométrico parabólico residual tras el doblado (sesgo de Γ 0.034 →
  8·10⁻⁵ con parábola del 1.5 %).
- **Integración del modelo sobre el canal** (`channel_sub`, por defecto 1):
  cuadratura Gauss-Legendre sobre la anchura del canal; con canal ≈ 1.3Γ el
  sesgo de Γ pasa de +0.091 a <0.002.

`core/session.py` expone todo en la capa headless (`channel_sub`, `curv`,
`src_fwhm` en plantillas/sesión); tests nuevos en
`tests/test_mejoras_normos.py` (límites exactos: θ=0 ≡ 1er orden, regla de
suma, invariancia rotacional, límite fino, identidades por defecto).

**GUI, ayudas y robustez** (3ª fase):

- Todo lo anterior queda expuesto en la GUI Qt: tratamiento «Hamiltoniano
  completo» en el menú contextual de ΔEQ (con controles η y φ del componente),
  «Integral de transmisión» en el selector de absorbente (+ control «Γ fuente»),
  «Curvatura base» en calibración, e «Integración por canal», «Líneas sueltas»
  y «Escalado global automático» en Opciones avanzadas. Persistencia en
  settings y sesiones; los ajustes devuelven curv/src_fwhm al panel.
- **Robustez del motor** (banco §6.10): (1) el corte por estancamiento del
  multistart ya no abandona mientras el mejor χ²red siga alto; (2) escalado
  automático a evolución diferencial + refinado local cuando el multistart
  acaba con χ²red>10 (`auto_global`, activo por defecto en sesión/GUI).
  Re-medido el experimento de 20 semillas de dos sextetos solapados con
  arranques ±15 %: **de 8/20 fallos a 0/20**.
- Manuales de usuario ES/EN actualizados (capítulo Simular y ajustar:
  absorbente, cuadrupolo, opciones) y recompilados; cadenas i18n y capítulos
  de ayuda en los 8 idiomas.

Con el manual de NORMOS (R.A. Brand, 1990; `validacion/sitedistmanual.odt`)
se cerró además el resto de la lista de capacidades:

- **`wide_delta`** (`ModelState`, opt-in): límites de δ ampliados a ±(vmax+2)
  para usar singletes como líneas Lorentzianas libres en cualquier posición
  (caso C3 fuera de rango: χ²red 1702 → 0.0002).
- **GUI hasta 10 componentes**: `MAX_COMPONENTS` = 10 como fuente única en
  `core/params.py`, importado por los módulos Qt (antes 6 duplicado en tres
  ficheros); el banco había demostrado que el motor ajusta 10 sitios.
- El manual confirmó que la convención θ/φ y el promedio de polvo del nuevo
  Hamiltoniano coinciden con los de SITE, que las ligaduras de SITE
  (`NDEX/FACTOR/CONST`) son formalmente idénticas a las de Fitbauer, y
  permitió validar el kernel P(ΔEQ) contra la distribución continua real de
  DIST (`METHOD=6`). La relajación Ising del demo resultó no monotónica en
  OME y no permite verificar el mapeo cuantitativo OME(MHz)↔ν.

## v4.17.3 — traducción al portugués

- **Nuevo idioma: portugués** (europeo, AO90). Traducción completa desde el
  español de la interfaz (`locales/pt/strings.json`, 803 claves) y de los 30
  capítulos de la ayuda (`locales/pt/help.json`), con terminología revisada
  (Ficheiro, Dobragem, Desvio isomérico, Definições…) y registro formal
  unificado. Los placeholders de formato y los grupos temáticos de la ayuda
  se verificaron idénticos a `es`; el test de paridad de locales cubre ahora
  8 idiomas.
- `mossbauer_help.py`: fallback «(definições)» para `{settings_path_str}`
  en portugués. El idioma aparece automáticamente en Vista → Idioma
  (descubrimiento por carpeta) y se incluye en los ejecutables (el spec ya
  empaqueta `locales/` completo).

## v4.17.2 — caza de bugs multi-agente II: E/S y folding, distribución, sesiones y CLIs

Segunda auditoría con cuatro revisores independientes (E/S+folding,
distribución, sesiones/estado, CLIs+i18n) y verificación manual de cada
hallazgo con scripts de reproducción. Corregidos 21 fallos + 1 refuerzo.

### E/S de datos y folding (`core/folding.py`, `mossbauer_ws5.py`)

- **La búsqueda del centro de doblado usaba una ventana fija 250.5–262.5**
  (válida solo para 512 canales) en la GUI y en `folded_velocity_data`: con
  256 o 1024 canales el centro detectado era absurdo (256.25 / 255.39) y el
  espectro se doblaba mal. El default ahora deriva de N (N/2 ± 20, como ya
  hacía `core.session`).
- **`chi2_for_center` deflactaba el χ² de los candidatos junto al borde**:
  saltaba los pares fuera de rango pero normalizaba por el total. En modo seno
  con absorción débil (≤1 %) el centro se iba hasta 50 canales; ahora se
  normaliza por los pares realmente evaluados y el centro se recupera.
- **El χ² de simetría usaba `round` en vez de la interpolación del folding** y
  no excluía los canales de borde: un canal 1 muerto (habitual en ADT reales)
  sesgaba el centro ±0.4 canales — con la normalización nueva, hasta +1.8. El
  χ² ahora interpola igual que el fold y excluye `EDGE_TRIM_DEFAULT` canales
  extremos; el sesgo queda < 0.01 canales. *(Recalibrados los golden del CLI:
  el centro se mueve ≤ 0.16 canales; δ/BHF/ΔEQ no cambian a 1e-4.)*
- **`read_normos_plt_velocity` se envenenaba con títulos con dígitos**
  (`Fe3O4`, `T=300K`, `Fc211025` → vmax = 211025 mm/s sin error): ahora solo
  cuentan las líneas puramente numéricas del .PLT.
- **`load_velocity_csv` corrompía en silencio CSV con decimales de coma**
  (locale es_ES): la coma dentro de campo sin punto se interpreta ahora como
  separador decimal; la coma entre columnas sigue funcionando.
- **`folded_velocity_data` (CLIs de distribución) no recortaba bordes**: el
  canal muerto de un ADT real entraba como línea de absorción falsa del 8.5 %.
  Ahora aplica el mismo `edge_trim=1` y eje que GUI/sesión.
- **Un WS5 truncado (sin `</data>`) anteponía números de la cabecera XML**
  como cuentas (espectro desplazado en silencio): ahora se usa el contenido
  tras `<data>` y un XML sin bloque legible da error claro.

### Distribución (`mossbauer_distribution.py`, `gui/distribution_fit.py`, `core/`)

- **Los nítidos Relajación/Blume-Tjon/Néel se ajustaban con un patrón de
  líneas erróneo** ([3, 4, 1] en vez de [3, 2, 1]): la conversión de
  intensidades GUI→engine solo se aplicaba al tipo Sextete. Ahora aplica a los
  cuatro tipos magnéticos y el subespectro dibujado coincide con el ajustado
  (desajuste 0.665 → ≤ 2.4e-4).
- **`sharp_component_params` no traducía la convención engine→core** (latente;
  el test que la consagraba se ha corregido): ahora las intensidades
  `int2_rel`/`int3_rel` se traducen al vector canónico y la reconstrucción
  reproduce el kernel del ajuste exactamente.
- **Gaussiana/VBF/Binomial/Fija ignoraban baseline/slope FIJOS** (los
  ajustaban libres y sobreescribían el valor fijado por el usuario, también
  vía CLI `--no-fit-baseline`/`--no-fit-slope`): los cuatro motores aceptan
  ahora `fit_baseline`/`fit_slope` y la GUI/CLI los pasan siempre.
- **Binomial y Fija heredaban el perfil de línea de un ajuste anterior**: no
  envolvían su kernel en `line_profile(...)` y `fit_discrete` dejaba el perfil
  en el estado global (un discreto Voigt previo cambiaba la curva hasta 0.04).
  Doble arreglo: ambos motores aceptan `profile`/`voigt_sigma` y
  `fit_discrete` restaura el estado global al salir.
- **La L-curve en modo P(IS) escaneaba `variable="bhf"`** con la malla de IS
  interpretada como teslas: ahora escanea `variable="delta"`.
- **VBF: σ en la cota inferior subdesbordaba la gaussiana discretizada** (todo
  ceros con μ entre nodos → componente desaparecido con jacobiano nulo): se
  colapsa al nodo más próximo.

### Sesiones y estado (`gui/session_io.py`, `gui/state.py`, `core/session.py`)

- **Las 4 sesiones de distribución de ejemplo del repo no cargaban**
  (`AttributeError`): las sesiones legacy guardan `sextet_enabled`/
  `component_kind`/`intensity_mode` como listas y el cargador (GUI y
  `ModelState.apply_template`) asumía dicts. Ahora se normalizan.
- **Las sesiones legacy perdían los ajustes del panel de distribución**
  (`dist_bmin/bmax`, `nbins`, Γ, log α… dentro de `vars`): el cargador ahora
  mira también dentro de `vars`.
- **Restaurar una sesión de espectro CSV corrompía los datos**: la recarga
  usaba siempre el lector WS5+folding; ahora bifurca por extensión igual que
  *Abrir* (las dos columnas ya no se leen como cuentas intercaladas).
- **Multistart = 0 no sobrevivía al reinicio** (`int(x or 8)` convertía el 0
  válido en 8): default solo si el valor es None.

### CLIs, i18n y utilidades

- **`mossbauer_fit_cli --out` igual a la plantilla o al espectro los
  destruía sin aviso** (rc=0): ahora falla con rc=2 antes de ajustar.
- **`fit_bhf_distribution_cli --scan-alpha` con forma no-histograma** se
  validaba tras completar el ajuste y escribir 2 de 3 ficheros: ahora es un
  error de `parse_args` (rc=2, sin salida parcial). Entrada inexistente da
  mensaje limpio en vez de traceback.
- **10 claves i18n usadas en el código no existían en ningún locale** (la GUI
  en EN/FR/DE/JA/RU/CH mostraba el texto español): añadidas a los 7 idiomas
  con test de paridad de claves. La ayuda además sustituye ahora solo los
  placeholders conocidos (un capítulo con llaves literales no rompe el
  formateo).
- `find_crossing` con barrido vacío devolvía crash (`argmin` de secuencia
  vacía) → `(None, None)`; el filtro local del navegador web restaura las
  filas al borrar la búsqueda; cancelar el diálogo «Nota» aborta la subida de
  sesión; la heurística de prerelease del updater compara tokens (ya no marca
  `-mac`/`-stable`/`-final` como prerelease); `_iter_paginated` tolera
  respuestas DRF sin paginación.

21 tests de regresión nuevos (`tests/test_bugfixes_v4_17_2.py`); suite
completa en verde.

## v4.17.1 — Γ inicial físico en «Inicializar desde mínimos»

- **El estimador de anchura CWT proponía Γ ~3× demasiado grande**: para una
  Lorentziana de FWHM Γ, la escala Ricker de máxima respuesta cumple
  2·a·dv ≈ 2.85·Γ (ratio empírico estable 2.6–3.0 en Γ = 0.2–1.0 mm/s), pero
  la conversión no aplicaba ese factor. Resultado: α-Fe arrancaba con
  Γ = 0.75 mm/s (real ≈ 0.28), hematita con 0.94 y magnetita saturaba el tope
  de 2.0 — el autoajuste partía de líneas absurdamente anchas y la rama CWT era
  además inconsistente con la rama directa a media altura (que sí mide FWHM).
- Con la calibración (`_CWT_LORENTZ_WIDTH_RATIO = 2.85`): α-Fe → 0.26,
  hematita → 0.33, magnetita → 0.46/0.73. Test de regresión nuevo; suite
  completa 288 en verde.

## v4.17.0 — caza de bugs multi-agente: motor, GUI, sesiones y CLI

Auditoría en profundidad con cuatro revisores independientes (motor de ajuste,
GUI, sesiones/estado, CLI+i18n) y verificación manual de cada hallazgo.
Corregidos 20 fallos; i18n resultó estar limpio (793 claves idénticas y
placeholders coherentes en los 7 idiomas).

### Motor de ajuste (`core/fit_engine.py`, `core/session.py`)

- **Vmax negativo + «Ajustar velocidad» invertía el eje**: el optimizador
  trabaja con |vmax| pero el reescalado dividía por el vmax de referencia con
  signo → el eje quedaba des-invertido en todas las iteraciones (δ espejado) y
  el signo se perdía al terminar. Ahora el signo de la convención de eje se
  conserva (triangular y seno).
- **`fit_center` roto fuera de 512 canales**: los límites del centro caían al
  default (250, 263); con otros tamaños el centro quedaba clavado en el límite
  y el re-doblado destruía el ajuste. Ahora los límites derivan de N (N/2 ± 7).
- **σ Poisson en modo seno**: la fórmula asumía el promedio de dos canales del
  doblado (÷2) también en seno (sin doblar) → σ subestimada ×√2 y χ² inflado
  ×2; ídem en la generación de réplicas bootstrap. Corregido en ambos sitios.
- **Perfil de verosimilitud con `fit_center` comparaba datasets distintos**: el
  χ² mínimo venía de los datos re-doblados en el centro ajustado c\*, pero los
  puntos del perfil usaban los datos del centro inicial → Δχ² con offset
  constante (verificado: +72.5 en α-Fe) e intervalos `null` silenciosos en el
  CLI. Ahora el perfil se condiciona al dataset de c\* (re-doblado + χ² mínimo
  recalculado sobre él).
- **Los errores de vmax/centro/σ ajustados se descartaban**: la covarianza los
  calculaba pero se truncaba a los parámetros libres «normales». Ahora se
  informan (GUI, informes y CLI).
- **Réplicas bootstrap/perfil**: usaban la σ-Voigt pre-ajuste con «Ajustar σ»
  activo y no heredaban la forma de onda. Corregido.
- **`HeadlessSession` no re-doblaba tras `fit_center`** (el análogo headless
  del bug de GUI de v4.16.1): sesión y stats quedaban incoherentes; en seno el
  eje usaba la fase vieja. Ahora re-dobla (o actualiza la fase) y además la
  salida del CLI muestra centro/vmax/σ ajustados (antes invisibles).
- **«Propagar incertidumbre de calibración» era un no-op**: `sigma_vmax` no se
  cableaba nunca. Ahora se toma de la calibración asociada (si consta σ de
  vmax) y el inflado de errores funciona.

### GUI

- **Menú Ajuste → Avanzado → Modelo de absorbente no hacía nada**: solo
  escribía un atributo que el siguiente cambio de parámetro machacaba; el
  ajuste seguía usando el modelo del combo del panel. Ahora sincroniza el
  panel (y `sat_scale` se activa/agrisa correctamente).
- **Ajuste en serie (batch)**: el warm-start descartaba vmax/σ/sat_scale
  ajustados y al cerrar el diálogo el plot y el panel de info no se
  refrescaban (quedaban con el modelo previo al batch). Corregido.
- **Bootstrap sin ajuste previo**: el ajuste base calculado internamente se
  registraba como resultado pero no se volcaba a los widgets ni al plot.
- **`_sync_constraint_targets` desbloqueaba las señales a mitad de carga de
  sesión** (ponía `_building=False` incondicionalmente): con restricciones
  activas, la restauración podía re-detectar el centro y pisar el guardado.
- Menores: «Buscar centro» no actualizaba la etiqueta del fichero; exportar
  ajuste de distribución tras re-doblar podía desalinear el modelo guardado.

### Sesiones (guardar/cargar, historial, deshacer)

- **Restaurar un componente con tipo distinto machacaba valores recién
  restaurados** (int1/int2 del doblete asimétrico): ahora se restaura primero
  el tipo y los modos (con re-layout del grid, que antes quedaba agrisado
  obsoleto) y después valores y casillas «Fijo».
- **Restaurar desde otro modo pisaba el patrón activo/inactivo de componentes**
  y **recortaba los valores de la malla con los rangos de la variable
  anterior**: el modo se restaura ahora antes que las casillas y valores.
- Menores: la rama de cuentas embebidas no limpiaba resultados runtime ni el
  mapa 2D; una sesión sin calibración heredaba la calibración previa; una ruta
  de P fija previa sobrevivía a sesiones sin ella; `multistart_n: null` de
  sesiones antiguas abortaba la carga completa.

### CLI de distribución

- **Default de Γ unificado (0.36 mm/s, fuente única en `core.params`)**: el
  pipeline web usaba 0.18 como fallback sin sidecar mientras GUI y CLI usaban
  0.36 — el mismo espectro daba P(BHF) distintas según el punto de entrada.
  Nota: los resultados del pipeline web sin `--gamma` ni sidecar cambian
  respecto a versiones anteriores (kernel más ancho → distribución más
  estrecha); pasar `--gamma 0.18` reproduce el comportamiento antiguo.

7 tests de regresión nuevos (todos fallan sin los fixes); suite completa: 287
en verde, golden headless incluido.

## v4.16.3 — auditoría de sesiones: todo se guarda y se restaura

Auditoría de la persistencia (sesiones, historial de ajustes, undo) comprobando
que cada ajuste de la GUI se guarda en el payload y se restaura al cargarlo.
Dos huecos encontrados y corregidos:

- **La malla 2D no se persistía**: los controles del eje Y de la distribución 2D
  (`qmin`/`qmax`/`qbins`/`log α_q`) no formaban parte del estado de sesión — al
  recargar volvían a sus valores por defecto. Ahora se guardan y restauran
  (`dist_qmin`/`dist_qmax`/`dist_qbins`/`dist_log_alpha_q`).
- **Las casillas «Fijo» de calibración no se restauraban**: `baseline`, `slope` y
  `sat_scale` guardaban su estado fijo/libre en la sesión pero al cargarla solo
  se restauraban las de los componentes (y σ vía «Ajustar σ»). Ahora se restauran
  también las tres de calibración.

Como el historial de ajustes y «Deshacer ajuste» reutilizan el mismo payload,
ambos quedan corregidos a la vez. Test nuevo de **ida y vuelta completa**
(`test_session_payload_full_roundtrip`): guardar → cargar → guardar debe
reproducir el `model_state` exactamente, con lo que cualquier deriva futura
entre guardado y restauración hará fallar la suite.

### Documentación

- Manuales ES y EN: documentadas la casilla «Ajustar folding point dentro del
  ajuste» (§ El folding y el centro) y el diálogo «Historial de ajustes»
  (§ Herramientas de ayuda al ajuste); PDFs recompilados.
- Verificado que la ayuda in-app cubre en los 7 idiomas el folding point
  ajustable, sesiones, historial, absorbente grueso/saturación, L-curve,
  bootstrap, verosimilitud perfilada, CLI, mínimos y batch (misma estructura de
  30 capítulos por idioma).

## v4.16.2 — auditoría: todo lo ajustable se vuelca a la GUI

Auditoría sistemática del camino widget → estado → motor → resultado → widget para
todos los parámetros ajustables (calibración, componentes, distribución, sesiones).
Dos huecos encontrados y corregidos (mismo patrón que el del centro en v4.16.1):

- **`sat_scale` no se volcaba tras el ajuste**: con absorbente grueso y la casilla
  «Fijo» desmarcada, el motor ajustaba la escala de saturación pero `on_fit` no
  escribía el valor ajustado en el widget de calibración. Ahora sí.
- **Cargar sesión / deshacer ajuste no re-doblaba con el centro guardado**: la
  restauración doblaba los datos con el centro auto-detectado y luego ponía el
  centro de la sesión solo en el widget — datos y widget quedaban incoherentes
  (relevante tras guardar una sesión con centro ajustado). Ahora, si el centro de
  la sesión difiere del auto-detectado, se re-dobla con él.

Verificado además (sin cambios): baseline, slope, vmax («Ajustar velocidad», con
recálculo del eje), σ-Voigt («Ajustar σ»), parámetros de componentes y targets de
restricciones en modo discreto; y en modo distribución δ/ΔEQ/Γ, pendientes de
correlación, parámetros de nítidos y pesos, respetando las casillas «Fijo».
Tests de regresión nuevos en `tests/test_qt_app.py`.

## v4.16.1 — el centro ajustado vuelve a la GUI

- **«Ajustar centro» no se reflejaba en la interfaz**: el motor de ajuste sí
  optimizaba el folding point (corregido en v4.15.0), pero la GUI descartaba el
  resultado — no volcaba el centro ajustado al widget de calibración ni re-doblaba
  los datos con él, por lo que el usuario veía siempre el mismo valor. Ahora, tras
  el ajuste discreto con «Ajustar centro» activo, el widget muestra el centro
  ajustado y los datos se re-doblan con él (GUI y motor quedan coherentes).
  Test de regresión en `tests/test_qt_app.py::test_fit_center_updates_widget_and_refolds`.

## v4.16.0 — renombrado del repositorio a Fitbauer (release acumulativa)

> **Nota de release.** Ésta es la primera versión publicada en GitHub desde `v4.14.2`:
> las versiones intermedias `v4.14.3` y `v4.15.0` se documentaron en este CHANGELOG pero
> nunca se tagearon/publicaron por separado. Por tanto, las notas de la release `v4.16.0`
> agrupan **todo** lo hecho desde `v4.14.2`: el renombrado del repositorio (abajo), la
> paridad completa GUI ↔ línea de comandos y la física unificada (ver [v4.15.0](#v4150--todos-los-ajustes-desde-línea-de-comandos-física-unificada-y-correcciones))
> y el registro en los menús del sistema (ver [v4.14.3](#v4143--el-instalador-registra-fitbauer-en-los-menús-del-sistema)).

El repositorio de GitHub se ha renombrado de `Mossbauer` a **`Fitbauer`**, alineándolo
con el nombre del programa. Se actualizan todas las referencias codificadas al slug del
repositorio para que apunten a `sullymike/Fitbauer`:

- **Actualizador** (`mossbauer_updater.py`): `GITHUB_REPO = "sullymike/Fitbauer"`, que
  propaga a las URLs de la API, el feed atom, la página de releases y las descargas. La
  comprobación de actualizaciones y la descarga de nuevas versiones usan ya el nombre nuevo.
- **Ayuda** (`gui/help.py`): enlace al manual en inglés (`MANUAL_EN_URL`).
- **Documentación** (`INSTALL_EN.md`, artículos y paper en `docs/`) y el `git clone`/`cd`.

GitHub mantiene la redirección desde el nombre antiguo, por lo que los enlaces previos
siguen funcionando; este cambio evita depender de esa redirección.

## v4.15.0 — todos los ajustes desde línea de comandos, física unificada y correcciones

Auditoría completa del programa (fallos, duplicados, menús, ayuda) y paridad
GUI ↔ CLI:

### CLI: paridad completa con la GUI

- **`fit_bhf_distribution_cli.py`** ahora expone todo el motor de distribución:
  `--variable quad` (P(ΔEQ) con `--fixed-bhf`), `--shape
  histograma|gaussiana|vbf|binomial` (+`--vbf-components`), `--reg-mode
  tikhonov|tv|maxent`, `--profile Voigt` + `--voigt-sigma`, correlaciones
  `--delta-slope`/`--quad-slope` y la distribución 2D `--dist-2d`
  (+`--qmin/--qmax/--nbins-quad/--alpha-quad`). El `--scan-alpha` respeta
  ahora regularizador/variable/perfil.
- **`mossbauer_fit_cli.py`**: `--bootstrap N` (errores Monte Carlo),
  `--profile-likelihood` (intervalos asimétricos 1σ/2σ por Δχ²=1/4) y serie
  con **warm-start secuencial** al pasar varios `--spectrum` (espejo del
  batch de la GUI).
- Manual en inglés: nuevo apéndice «Command-line tools (headless fitting)»;
  `BHF_DISTRIBUTION.md` actualizado. Tests nuevos en `tests/test_cli_extended.py`.

### Corrección de fallos (auditoría)

- **«Ajustar centro» era un no-op en modo triangular**: el re-doblado por
  iteración nunca casaba con la malla recortada (`edge_trim`) y se descartaba.
  Ahora recorta bordes simétricamente y el centro se ajusta de verdad.
- **Bootstrap y verosimilitud perfilada** no propagaban `norm_factor`: en modo
  Poisson las réplicas usaban otra escala de σ (σ_MC e intervalos sesgados).
- **CLI**: la plantilla se aplica antes de cargar el espectro, con lo que
  `drive_form="sine"` dobla correctamente.
- El diálogo de bootstrap respeta el idioma de la interfaz.

### Física unificada (fuente única)

- Los perfiles de absorción de `mossbauer_distribution.py` (sextete, singlete,
  doblete, relajación, Blume-Tjon, Néel) son ahora adaptadores finos sobre
  primitivos nuevos de `core/physics.py` (`sextet_line_positions`,
  `sum_lorentzian_lines`, `two_state_sextet_absorption`,
  `relaxation_transition_factors`, `match_positive_area`). Equivalencia
  garantizada por 21 tests de caracterización (atol 1e-12) y salida del CLI
  idéntica bit a bit antes/después.
- `mossbauer_ws5.py` reexporta de `core.folding`; `read_normos_sidecar_params`
  plano es adaptador de la versión canónica. Retirado `fold_mossbauer.py`
  (legacy sin usuarios). Persistencia de `settings.json` centralizada en
  `core/data_io.py` (`load_settings`/`update_settings`).

### Ayuda y menús

- Ayuda in-app (7 idiomas): eliminados los restos de Plotly/QtWebEngine
  (retirados en v4.13.1) y documentadas las acciones que faltaban («Mostrar
  área de componentes», «Límites de parámetros…», «Manual (PDF)»).
- «Manual (PDF)» entra en el registro de atajos configurables.

## v4.14.3 — el instalador registra Fitbauer en los menús del sistema

`install.py` ahora, además de crear el entorno y los lanzadores, **añade Fitbauer a
los menús de aplicaciones** del sistema (por-usuario, sin permisos de administrador),
para poder abrirlo desde el menú con su icono:

- **Linux**: fichero `~/.local/share/applications/fitbauer.desktop` (categoría
  `Education`, `Exec` al Python del `.venv`) e icono en `hicolor/256x256/apps`;
  refresca las cachés (`update-desktop-database`, `gtk-update-icon-cache`) si están.
- **Windows**: acceso directo dentro de una carpeta propia *Fitbauer* del menú Inicio
  (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Fitbauer\Fitbauer.lnk`) creado con
  PowerShell/WScript.Shell (sin dependencias extra), apuntando a `pythonw` para no
  abrir consola, con el icono `.ico`.
- Nuevas opciones de CLI: `--menu-only` (solo registrar), `--no-menu` (instalar sin
  tocar menús) y `--uninstall` (eliminar la entrada). `INSTALL.md`/`INSTALL_EN.md`
  actualizados. Validado en Linux (`desktop-file-validate` sin avisos) e
  instalar/desinstalar limpio.

## v4.14.2 — distribución: «Gaussiana» pasa a ser VBF con N=1 (sin duplicar código)

La forma **Gaussiana** era un caso particular estricto de **VBF** (una sola
gaussiana): mismos parámetros libres (baseline, slope, A, μ, σ), misma malla y la
misma normalización de área. Se unifican ambos caminos.

- La GUI **mantiene la etiqueta «Gaussiana»** (opción amigable, sin jerga), pero
  internamente ajusta con `fit_vbf_hyperfine_distribution(n_components=1,
  profile="Lorentz")`. El resultado conserva `shape="Gaussiana"`, así que sesiones,
  informes y export siguen igual; ahora además reporta el componente como A/μ/σ.
- Se **elimina la función duplicada** `fit_gaussian_hyperfine_distribution`. VBF es
  su generalización (N>1, perfil Voigt, correlación δ(H)/ΔEQ(H)).
- Efecto colateral positivo: el camino antiguo dependía del **perfil de línea global
  ambiente** (podía «contaminarse» tras un ajuste discreto en Voigt); ahora fija el
  perfil explícitamente (Lorentz), como el resto de VBF.
- Test de regresión (`test_gaussiana_shape_is_vbf_single_lorentz`): recupera una
  gaussiana de BHF conocida y verifica que se conserva la etiqueta.
- **Documentación**: ayudas actualizadas en los **7 idiomas** (Gaussiana = VBF con
  N=1); el capítulo P(BHF) del manual lo aclara; y **nuevo anexo B del manual**
  («Ajuste por Voigt (VBF)», `docs/manual/appendices/apx_vbf.tex`) con la matemática
  completa: modelo directo y núcleo, perfil Voigt y la doble lectura del
  ensanchamiento, mínimos cuadrados y parametrización, áreas/poblaciones,
  correlación δ(H)/ΔEQ(H), el caso N=1 y comparación con el histograma.
- **Manual en inglés**: nuevo árbol `docs/manual_en/` con el manual completo
  traducido (capítulos y anexos), figuras regeneradas en inglés y `main.pdf`
  (76 págs., compila limpio). Se mantiene en paralelo al manual en español.
- **Enlace al manual en la app**: nueva acción **Ayuda → Manual (PDF)** que abre el
  manual **en inglés** (única versión enlazada): copia local `docs/manual_en/main.pdf`
  si está presente, o el PDF en GitHub en su defecto (robusto en builds congelados,
  que no empaquetan `docs/`). Cadena `help.manual` en los 7 idiomas.

## v4.14.1 — comprobar actualizaciones sin caer en el rate-limit (HTTP 403)

La comprobación de actualizaciones usaba solo la API REST de GitHub sin
autenticar (`api.github.com`), limitada a **60 peticiones/hora por IP**. En redes
con IP compartida (NAT, p. ej. una universidad) esa cuota se agota entre varios
equipos y la comprobación fallaba con **HTTP 403**.

- **Fallback al feed atom público** (`github.com/<repo>/releases.atom`), que **no
  está sujeto** al límite de 60/h. Si la API devuelve 403 (rate-limit) o falla la
  red, `list_releases`/`latest_release` recurren al feed y la comprobación sigue
  funcionando. Los errores que no son de cuota (p. ej. 500) se propagan como antes.
- El feed no publica assets ni el flag de prerelease: el prerelease se deduce del
  sufijo del tag y la **descarga** se resuelve construyendo la URL canónica del
  workflow (`.../releases/download/<tag>/Fitbauer-<tag>.zip` y `sha256sums.txt`),
  de modo que descargar y verificar el SHA-256 también funcionan por esta vía.
- Tests nuevos (`tests/test_updater_atom_fallback.py`): 403→atom, canal con betas,
  URL canónica sin assets y que un error 500 no se traga.

## v4.14.0 — soporte de drive senoidal (estilo NORMOS)

Fitbauer ya admite datos medidos con drive **senoidal**, no solo de aceleración
constante (triangular). Antes había que pre-linealizarlos; ahora se ajustan de
forma nativa, siguiendo el criterio de NORMOS (`TRIANG=.FALSE.`, `FOLD=.FALSE.`,
`SIMULT=.TRUE.`): **no se doblan** y se ajusta el espectro completo asignando a
cada canal su velocidad real `v_i = vmax·sin(2π(i−c0)/N)`.

- Nuevo control **Forma de onda** (triangular/senoidal) en el panel de
  calibración, persistido en la sesión (junto al modelo de absorbente).
- En senoidal: la **fase** `c0` (canal de v=0) se autodetecta por simetría y es
  ajustable con el control *Centro*; con *Ajustar centro* entra como **parámetro
  libre** del ajuste (como permite NORMOS). *Ajustar Vmax* refina la amplitud.
- El motor de ajuste ya era agnóstico al orden de la velocidad; el eje senoidal
  (no monótono) se evalúa punto a punto. Guardas para el eje no monótono en el
  residuo (`propagate_calib`) y en el dibujo del residuo.
- Funciones nuevas en `core/folding.py`: `sine_velocity_axis`,
  `normalize_unfolded`, `symmetry_center_to_c0`, `find_sine_symmetry_center`.
  i18n en los 7 idiomas; nota en el manual (cap. 2).
- No soportado en v1: componente de relajación con drive senoidal.

## v4.13.2 — L-curve: elegir α pinchando la figura

La detección automática de la esquina de la L-curve (curvatura de Menger) no
siempre acierta. Ahora el diálogo de la L-curve es **interactivo**:

- **Clic para elegir α** sobre cualquiera de las dos figuras (la L
  `rugosidad↔residuo` o `α↔RMS`). Se ajusta al valor de α escaneado más cercano
  (distancia log-log en la L, o en `log10 α` en la otra) y se resalta en ambas.
- La esquina automática pasa a ser una **sugerencia** (marcador verde) y el botón
  **«Usar α=…»** aplica el valor **elegido** (arranca en la sugerencia).
- Lógica de selección extraída a `_lcurve_pick_index` (testeable); nuevos tests.

## v4.13.1 — adelgazamiento: se retira Plotly + QtWebEngine

Se elimina la dependencia de **Plotly** y **QtWebEngine** (Chromium embebido).
El objetivo es un ejecutable mucho más ligero y de arranque más rápido, sin los
*segfaults* de cierre de WebEngine. Se conserva el editor de mínimos, reimplementado
sobre Matplotlib.

- **Gráfico único Matplotlib.** Se retira la pestaña «Plotly interactivo», la vista
  web, el prototipo de arrastre de BHF, la exportación a HTML interactivo y los
  puentes WebChannel (`MinimaBridge`/`ModelDragBridge`).
- **Editor de mínimos en Matplotlib** (`gui/minima_editor.py`, nuevo): clic sobre el
  canvas para añadir/alternar mínimos (eventos `mpl_connect`), panel lateral en un
  splitter junto al gráfico. Reutiliza intacta la lógica de detección y de propuesta
  de componentes (*Inicializar/Autoajustar desde mínimos*).
- **Dependencias y empaquetado.** Se quita `plotly` de `requirements.txt` y
  `plotly*`/`PySide6.QtWebEngine*` de `Fitbauer.spec`. Se elimina el *workaround*
  anti-*segfault* de los tests.
- **Documentación.** `docs/plotly.md` conserva la referencia completa de la
  integración anterior y una **guía de restauración** por si se quiere reintroducir.

Sustituido: `gui/plotly_tools.py` → `gui/minima_editor.py`. Retirados los menús
«Exportar gráfico interactivo HTML» y «Mostrar pestaña Plotly interactiva».

## v4.13.0 — calibración fija reutilizable + manual de usuario

**Calibración fija.** La calibración deja de reajustarse en cada carga y se
convierte en un estado persistente que se **aplica** de forma coherente:

- Al definir una calibración (**Usar fichero actual como calibración**) o cargar
  una calibración web, su `Vmax` (e IS de referencia) quedan **fijados** y se
  marcan como «fija» en la etiqueta.
- Cargar un fichero **sin calibración propia** (cuentas en bruto `.ws5`/`.adt`)
  **usa la calibración fijada** para construir el eje de velocidad; la
  calibración no varía. Antes no había un concepto explícito de calibración fija.
- Cargar un fichero **con calibración propia** (velocidad `.csv/.txt/.dat/.exp`)
  **sustituye** la calibración y lo **avisa** en la barra de estado.
- Nueva acción **Liberar calibración fijada** en el menú contextual del cuadro de
  fichero. i18n ES/EN/FR.

Implementado en `gui/calibration_actions.py` (`_apply_calibration_on_load`,
`_fixed_calibration_vmax`, `_release_calibration`) y aplicado en las dos rutas de
carga de `gui/model_workflow.py`. Cubierto por tests en `tests/test_qt_app.py`.

**Manual de usuario.** Nuevo manual LaTeX extenso en `docs/manual/` (capítulos:
introducción, calibración, carga de datos, simular/ajustar y distribuciones), con
figuras de física auto-generadas desde `core/` (`scripts/make_figures.py`) y
huecos para capturas de la interfaz.

## v4.12.3 — área de cada gaussiana en VBF multi-componente

Con forma **VBF** y más de una gaussiana, ahora se informa el **área de cada
componente** y su **porcentaje relativo** (población de cada entorno):

- No requiere reajuste: en `fit_vbf_hyperfine_distribution` cada gaussiana aporta
  `A_k · gauss_weights(μ_k, σ_k)` y `gauss_weights` está normalizada a área unidad, así
  que el `A_k` ya almacenado en `vbf_components` **es exactamente el área** sobre la malla;
  el % relativo es `100·A_k/ΣA`.
- **Panel de estado:** el resumen del ajuste muestra `(A=…[NN%], μ=…, σ=…)` por gaussiana.
- **Informe** (markdown → PDF/ODT): la tabla de componentes VBF pasa a
  `| # | A (área) | Área % | μ (T) | σ (T) |`.

## v4.12.2 — α de distribución adimensional (regularización con escala física)

**Problema:** en el ajuste de distribución, mover el slider de log α apenas cambiaba
la P(BHF) obtenida. Causa: el objetivo es `‖(y−XP)/σ‖² + α·‖L·P‖²`; el término de datos
es un χ² ~ N, pero el penalizador iba en unidades de absorción y **sin normalizar**, de
modo que el α «útil» dependía de N, del ruido (σ) y de la profundidad de absorción. Con
un rango/default fijos, toda la mitad inferior del slider caía en zona muerta y el punto
activo se desplazaba de un espectro a otro (de 10⁰ a 10² según el ruido).

**Solución — α adimensional:**

- `fit_hyperfine_distribution` y `fit_bhf_quad_distribution` escalan el penalizador por
  `λ_ref = ‖A_dist‖²_F / ‖L_scaled‖²_F` (operadores blanqueados) y una constante de
  calibración `ALPHA_REF_SCALE`, de forma que α queda adimensional y **log α ≈ 0 es el
  balance natural datos/suavidad** para cualquier espectro. Aplica a los tres reguladores
  (`tikhonov`, `tv`, `maxent`) y a ambos ejes del 2D.
- El codo de la L-curve queda **estable frente a N, ruido y profundidad de absorción**
  (antes derivaba varias décadas). La dependencia residual con `nbins`/Γ (elecciones de
  modelado que el usuario fija) mantiene el codo dentro de ~[−2, +2].
- La dof efectiva y las σ de los pesos usan el α físico efectivo (`alpha_eff`), coherente
  con la penalización realmente aplicada.

**GUI / parámetros:**

- Slider `log α` (y `log α_q` del 2D): default **0.0** (antes −2.0) y rango **[−6, +6]**
  (antes [−8, +4]), centrado en la zona activa.
- Escaneo de la L-curve por defecto **[−4, +4]** (antes [−6, +2]), para bracketear el codo.
- Ayuda (ES/EN/FR) actualizada: α adimensional, valor típico −1…+2.

**Compatibilidad:** el valor numérico de α cambia de significado (ahora adimensional). Las
sesiones antiguas cargan con el nuevo default; los α guardados se reinterpretan en la nueva
escala. El comportamiento cualitativo (α→0 sin regularizar, α↑ más suave) se conserva.

## v4.12.1 — Persistencia e informes de los metadatos de distribución

Los parámetros del ajuste de distribución añadidos en v4.12.0 (forma, regularizador y
las pendientes de correlación κδ/κq) se calculaban pero **no se guardaban** en ningún
sitio salvo el propio widget: no aparecían en el panel de estado, ni en los informes, ni
en la sesión ni en el export TSV. Esta versión cierra esos huecos.

### Núcleo (`mossbauer_distribution.py`, `core/result_views.py`)

- `BhfDistributionFit` y `BhfQuadDistribution2DFit` almacenan ahora `shape`, `reg_mode`,
  `delta_slope`, `quad_slope` y `vbf_n_components`; cada función de ajuste los escribe en
  su resultado (`fit_hyperfine_distribution`, `fit_vbf_*`, gaussiana, binomial, fija, 2D).
  `as_dict()` los serializa. Con esto el resultado es la **fuente única** de los κδ/κq
  refinados (antes solo sobrevivían en el control del panel).
- `DistributionResultView`: `metrics()` expone `shape`/`reg_mode`/`vbf_n_components` (y
  omite valores `None`); `parameters()` incluye `delta_slope`/`quad_slope` (solo si ≠ 0).

### GUI (`gui/distribution_fit.py`, `gui/reports.py`, `gui/file_actions.py`)

- **Panel de estado**: tras un ajuste de distribución muestra `baseline`, `slope`, `α` y
  las pendientes κδ/κq cuando se usaron; la barra de estado añade forma y regularizador.
  Antes el panel no listaba ningún parámetro (`free_keys` iba vacío).
- **Informes** (completo, reducido y sus PDF/ODT): nuevo bloque **«Ajuste de distribución»**
  con forma, regularizador, α, línea base, RMS, grados efectivos, ⟨x⟩/σ de la distribución,
  κδ/κq, componentes VBF (A/μ/σ) y componentes nítidos. Antes los informes eran 100 %
  del ajuste discreto e ignoraban la distribución.
- **Export TSV** (`Guardar ajuste`): cabecera `# Distribution:` con forma/regularizador/α/
  κδ/κq y un bloque final `# --- Distribution P(x) ---` con la curva P(BHF)/P(ΔEQ) (marginal
  en 2D). Antes solo se exportaban `model`/`residual`.

### Sesión (`gui/state.py`, `gui/session_io.py`)

- La sesión serializa y restaura los ajustes numéricos del panel de distribución que antes
  se perdían: `delta_slope`, `quad_slope`, `vbf_n_components`, `log_alpha`, `nbins`,
  `bmin`/`bmax`, δ, ΔEQ, Γ, `fixed_bhf` y el mapa de fijados. Sesiones antiguas cargan con
  los valores por defecto (retrocompatible).
- Corrección: la restauración de `reg_mode` ignoraba `maxent` (solo aceptaba
  `tikhonov`/`tv`); ahora se restaura correctamente.

## v4.12.0 — P(BHF): correlación δ(H)/ΔEQ(H), VBF multi-gaussiano y MaxEnt

### Núcleo (`mossbauer_distribution.py`, `core/physics.py`)

- **Correlación lineal δ(H)/ΔEQ(H)** (Le Caër–Dubois 1979, Wivel–Mørup 1981):
  `build_bhf_kernel` y `build_hyperfine_distribution_kernel` aceptan `delta_slope`,
  `quad_slope`, `h_ref`; cada sextete de la malla usa `δⱼ = δ + κδ·(Hⱼ − Href)` y
  `ΔEQⱼ = ΔEQ + κq·(Hⱼ − Href)`. El modelo sigue siendo **lineal en los pesos P**
  (solo cambia cada columna del kernel). Propagado a `fit_hyperfine_distribution`.
  Con pendientes = 0 reproduce el kernel clásico (opt-in, retrocompatible).
- **Regularización de Máxima Entropía** (`reg_mode="maxent"`): minimiza
  `½‖(y−Xz)/σ‖² − α·S(P)` con `S = −Σ Pⱼ log(Pⱼ/mⱼ)` mediante L-BFGS-B con gradiente
  analítico y cotas P≥0; grados de libertad efectivos por el Hessiano MaxEnt. Positiva
  por construcción y sin oscilaciones espurias. Junto a `tikhonov`/`tv`.
- **VBF multi-gaussiano** (Rancourt–Ping 1991): `fit_vbf_hyperfine_distribution`
  ajusta P como suma de N gaussianas sobre kernel Voigt; guarda los parámetros físicos
  (A, μ, σ) por componente en `BhfDistributionFit.vbf_components` (ordenados por μ).

### GUI

- Panel de distribución: nueva forma **"VBF"** (con selector de nº de componentes),
  modo de regularización **"maxent"** y controles de pendientes de correlación
  **κδ**/**κq** (fijas por defecto; desmarcar «Fijo» las refina en la capa externa).
  Despacho en `run_fit`, threading de pendientes por el lazo de refinado externo, y
  validación (`core/params`, `core/validation`) ampliada a VBF/maxent.
- Ayuda «P(BHF): método» ampliada (ES/EN/FR) con los tres métodos.

### Tests

- `tests/test_distribution_advanced.py` (correlación κ=0≡clásico y desplazamiento de
  centroides; VBF recupera μ/σ/A; MaxEnt positivo, ∫P=1 y pico correcto) y dos tests
  GUI en `tests/test_qt_app.py` (forma VBF y reg_mode maxent).

## v4.11.4 — Refinado de σ (Voigt) por casilla y reapertura del gráfico P(BHF)

### Ajuste discreto (cristalino)

- **Refinar σ de Voigt con la casilla "Fijo" de σ** (`gui/panels.py`): el control de σ
  gaussiana pasa a tener la misma casilla libre/fijo que baseline/slope. Con perfil Voigt,
  **desmarcar "Fijo" refina σ** en el ajuste; marcarla lo deja fijo. Antes el refinado
  dependía de una casilla separada "Ajustar σ" accesible solo por clic derecho (poco
  descubrible), y marcar σ como "libre" no hacía nada. La casilla "Ajustar σ" se conserva
  como espejo interno oculto (sincronizado) por compatibilidad de sesión/motor; el motor de
  ajuste no cambia. Fuera de Voigt, σ queda fija (no se refina). Tooltip explicativo.
- **La barra de σ solo es manipulable con perfil Voigt** (`gui/panels.py`): con Lorentziana el
  control de σ (slider + spinbox + casilla) se deshabilita por completo, no solo el spinbox.
- **La previsualización en vivo refleja el perfil de línea y σ del panel** (`core/physics.py`,
  `core/reconstruction.py`, `gui/model_workflow.py`): antes, mover el slider de σ no cambiaba la
  figura porque la ruta de simulación no fijaba las globales `LINE_PROFILE_KIND`/`VOIGT_SIGMA`
  (solo las escribía el motor de ajuste). Ahora `reconstruct_discrete_model` acepta
  `line_profile_kind`/`voigt_sigma` y fija el perfil de forma determinista con un gestor de
  contexto `line_profile()` que **restaura** el estado global al salir (sin contaminar entre
  operaciones). El gestor, antes duplicado en `mossbauer_distribution.py`, se centraliza en
  `core.physics` y se reutiliza (DRY).

### Modo distribución P(BHF) / P(ΔEQ)

- **Reabrir el gráfico de la distribución tras cerrarlo** (`gui/distribution_fit.py`,
  `gui/menu_builder.py`): antes solo el mapa 2D podía reabrirse. Ahora, tras cualquier ajuste
  de distribución (1D P(BHF)/P(ΔEQ) o 2D), el botón del panel queda visible ("Ver
  distribución…" en 1D, "Ver mapa 2D…" en 2D) y hay una acción de menú equivalente en
  "P(BHF) extras". Reabre desde el resultado ya guardado en memoria
  (`runtime_results.distribution_result`), sin re-ejecutar el ajuste.

### Tests

- `tests/test_gui_panel_snapshots.py`: la casilla "Fijo" de σ controla el refinado solo con
  Voigt. `tests/test_qt_app.py`: reapertura del gráfico P(BHF) 1D desde el resultado persistido.

## v4.11.3 — L-curve (esquina automática · zoom acoplado), perfil Voigt y ayuda ampliada

### Modo distribución P(BHF) / P(ΔEQ)

- **Selección de α por la esquina real de la L-curve** (`gui/distribution_fit.py`): el botón
  «Usar α» del diálogo de L-curve ya no sugiere el α de mínimo RMS (que tendía a
  infra-regularizar, escogiendo casi siempre el α más pequeño del barrido). Ahora detecta el
  **codo de la L-curve por máxima curvatura de Menger** (`_lcurve_corner_index`), es decir el
  mejor compromiso entre fidelidad al espectro y suavidad de la distribución. La esquina se
  resalta visualmente: círculo verde en la L-curve y línea vertical en la gráfica RMS vs α.
- **Zoom en el diálogo de L-curve, acoplado por α** (`_couple_lcurve_zoom`): las dos figuras
  incorporan barra de herramientas Matplotlib (zoom/pan/reset). Al hacer zoom en una, la otra
  se limita al mismo rango de α (selección por pertenencia de puntos, robusta aunque la
  rugosidad no sea monótona en α; cerrojo de reentrada para evitar el bucle entre callbacks).
- **α y L-curve deshabilitados donde no aplican** (`gui/distribution_panel.py`,
  `gui/distribution_fit.py`): las formas **Gaussiana** y **Binomial** son ajustes paramétricos
  (la suavidad la impone la forma funcional) y no usan α, así que el botón de L-curve, el slider
  `log α` y los presets Fina/Media/Suave se desactivan al seleccionarlas (también en Fija). El
  slider de α permanece activo en 2D, que sí regulariza con α_BHF/α_ΔEQ. La L-curve solo está
  implementada para el Histograma 1D.

### Perfil Voigt en el ajuste de distribución

- **Perfil de línea explícito en las distribuciones P(BHF)/P(ΔEQ) y P(BHF, ΔEQ)**
  (`mossbauer_distribution.py`): `fit_hyperfine_distribution` y
  `fit_bhf_quad_distribution` aceptan ahora `profile` (`"Lorentziana"`/`"Voigt"`) y
  `voigt_sigma`. El kernel se construye con la forma de línea elegida, igual que el
  ajuste discreto. La GUI pasa el selector de perfil compartido
  (`calib_state.line_profile` / `voigt_sigma`) en el ajuste Histograma y en el escáner
  de α (L-curve) (`gui/distribution_fit.py`).
- **Corrección de acoplamiento global latente**: la forma de línea vive en variables de
  módulo de `core.physics` (`LINE_PROFILE_KIND`/`VOIGT_SIGMA`) que `lorentzian` lee y que
  el ajuste discreto muta sin restaurar. Antes la distribución heredaba de forma no
  determinista el perfil dejado por el último discreto. El nuevo gestor `line_profile`
  fija y **restaura** ese estado alrededor de la construcción del kernel, dejando la
  distribución con perfil explícito y sin efectos colaterales.
- Tests nuevos en `tests/test_distribution_2d.py`: el perfil Voigt produce un kernel
  distinto y el estado global se restaura aunque estuviera "contaminado" por un discreto
  previo.

### Ayuda

- **Capítulo «P(BHF): método» ampliado** (`locales/{es,en,fr}/help.json`): se añade el encuadre
  como *problema inverso mal condicionado* y una sección dedicada a la **L-curve** (qué mide, la
  forma de «L», cómo leer el codo, su sentido físico y la aclaración de que α/L-curve solo
  aplican a la forma Histograma). Traducido a ES/EN/FR.

### Tests

- `tests/test_lcurve_corner.py` y `tests/test_lcurve_zoom_coupling.py`: cobertura de la
  detección del codo (curvatura de Menger, casos degenerados) y del zoom acoplado por α.

## v4.11.2 — Relleno de subespectros conmutable

### Mejoras en la GUI

- **Opción para mostrar u ocultar el área de los componentes** (`Vista → Mostrar área de
  componentes`): el relleno semitransparente bajo cada subespectro introducido en v4.11.1 es
  ahora opcional. Está activado por defecto (comportamiento previo), pero puede desactivarse
  desde el menú para quien prefiera ver solo las líneas de los componentes.
  - El nuevo flag `show_component_fill` viaja por `PlotViewState` (`gui/state.py`), el snapshot
    de acciones (`UiActionState`) y ambas rutas de render (`gui/canvas.py`, modo completo y
    `_update_fast`), de forma análoga a `show_legend`/`show_residual`.
  - Se persiste con la sesión: al guardar/cargar un proyecto se conserva la preferencia
    (`gui/session_io.py`).
  - Cadenas i18n añadidas en ES/EN/FR (`options.show_component_fill`).

## v4.11.1 — Relleno semitransparente en subespectros · figuras SVG · artículo svjour3

### Mejoras en la GUI

- **Relleno semitransparente bajo cada subespectro** (`gui/canvas.py`): al representar
  componentes (singlete, doblete, sextete o envolvente de distribución), se añade un área
  `fill_between` con el color de la línea correspondiente y opacidad configurable
  (`component_fill_alpha`, por defecto 0.12). Las líneas de componente pasan de trazo
  discontinuo (`--`) a continuo (`-`) para coherencia visual con el relleno.
  - En el modo de actualización rápida (`_update_fast`, usado durante el arrastre de
    sliders) el relleno se elimina y recrea en cada fotograma, igual que el relleno de
    residuos, porque `fill_between` no admite `set_data()`.
  - El estilo es análogo a las figuras publicadas con Matplotlib: cada subespectro queda
    identificado de forma inequívoca incluso cuando los componentes se superponen.

### Publicación: artículo para *Interactions* (Springer)

- Archivo principal `docs/article_hyperfine_interactions.tex` migrado a la clase
  **`svjour3`** (Springer). Compilado limpiamente a PDF de 15 páginas.
- Nuevas secciones incorporadas desde el borrador previo:
  - Perfil de Voigt (función de Faddeeva), ecuación de Kündig para el Hamiltoniano
    magnético-cuadrupolar, fórmula de absorbente grueso.
  - **Sección de modelos de relajación magnética**: Relajacion (fenomenológico),
    BlumeTjon y NeelSize (Néel-Arrhenius); incluye la ecuación de tiempo de
    relajación en función de tamaño de partícula y temperatura.
  - Distribuciones 2D con regularización dual y selección de α por GCV/L-curve.
- Bibliografía ampliada con 9 nuevas referencias (Kündig 1967, Margulies 1961,
  Blume-Tjon 1968, Néel 1949, Brown 1963, Klencsar 2013, Matsnev 2012,
  Kamusella 2016, Rancourt 1991).
- Añadido stub `docs/svglov3.clo` requerido por `svjour3.cls`.
- Figuras regeneradas como **SVG** (`docs/img/fig_*.svg`) para edición con Inkscape:
  - `fig_reference_fits.svg` — panel 2×2 con espectros reales de laboratorio
    (α-Fe, hematita, magnetita).
  - `fig_magnetita_fit.svg` — ajuste de 2 sextetes de Fe₃O₄ con relleno de área.
  - `fig_normos_comparison.svg` — correlación Fitbauer vs. NORMOS en δ, ΔEQ, BHF, Γ.
- Guía `docs/normos_dosbox_guide.md` para ejecutar NORMOS con DOSBox en sistemas
  modernos (Linux/Mac/Windows).

## v4.11.0 — Suite de validación sintética (6 niveles)

Versión centrada en **calidad interna del motor de ajuste**: añade una suite de tests
sistemática que cubre desde la autoconsistencia matemática hasta la calibración
estadística de incertidumbres, con datos reales y casos físicamente exigentes.

### Nueva funcionalidad: `tests/test_synthetic_validation.py`

Suite de **34 tests** (31 rápidos + 3 Monte Carlo marcados `@pytest.mark.slow`)
organizada en seis niveles de verificación:

#### Nivel 1 — Autoconsistencia (generador independiente)

- Implementación directa de referencia (`ref_sextet`, `ref_doublet`, `ref_singlet`,
  `ref_sextet_thick`) que **no llama a `core.physics`**: usa matemáticas puras y las
  constantes físicas publicadas de α-Fe.
- Test de cierre: espectro sintético sin ruido → ajuste → **χ²_reducido < 1×10⁻⁶**
  para sextete, doblete y singlete. Si este test falla, hay un bug estructural en el
  modelo o el optimizador que invalida todo lo demás.
- Verificación explícita de que el generador de referencia es numéricamente idéntico a
  `physics.sextet_absorption` (discrepancia < 1×10⁻¹⁰).

#### Nivel 2 — Jacobiano de la función residuo

- Validación analítica de ∂L/∂c y ∂L/∂Γ (Lorentziana) contra diferencias finitas
  (`approx_fprime`), error relativo < 1×10⁻⁴.
- Consistencia del jacobiano del residuo entre dos tamaños de paso independientes
  (eps=10⁻⁵ y 10⁻⁶): error relativo < 5 %.
- Ausencia de NaN/Inf en el jacobiano para sextete y doblete.

#### Nivel 3 — Monte Carlo con pull statistics (`@pytest.mark.slow`)

- **200 réplicas** de un sextete con ruido Poisson realista (8 000 cuentas/canal).
  Semilla fija (`SEEDS_MC["sextet_pull"] = 42042`) para reproducibilidad de fallos.
- Valida tres propiedades estadísticas:
  - **Sesgo**: `|media(pull)| < 3.5·SEM + 0.05` (estimador sin sesgo significativo).
  - **Calibración de σ**: `0.5 < std(pull) < 2.0` (incertidumbres reportadas coherentes
    con la dispersión real de Monte Carlo; std(pull) > 2 indica σ muy subestimado).
  - **Cobertura 1σ**: 48 %–88 % de las réplicas caen dentro de ±1σ reportado
    (teórico 68 %).

#### Nivel 4 — Casos físicos difíciles

- **Solapamiento creciente de dobletes**: sweep de ΔEQ ∈ {2.0, 1.0, 0.60} mm/s;
  verifica recuperación de ΔEQ cuando separación > 2Γ, y que las barras de error
  crecen al aproximarse a la resolución.
- **Sextete con líneas internas no resueltas** (Γ = 0.60 mm/s): ajuste converge.
- **Absorbente grueso** (`sat_scale`):
  - Recuperación de `sat_scale` verdadero (error < 20 %).
  - Degeneración al modelo fino cuando `sat_scale → ∞` (diferencia < 10⁻⁴ relativa).
  - Efecto de saturación: el modelo grueso tiene valles menos profundos que el fino.

#### Nivel 5 — Restricciones físicas y convenciones

- Ratios 3:2:1 del sextete para polvo aleatorio (`<sin²θ> = 2/3`).
- `texture_to_intensities` para orientaciones canónicas (perpendicular 3:4:1,
  paralela 3:0:1, polvo aleatorio 3:2:1).
- Convención ΔEQ: los mínimos del doblete están en `δ ± ΔEQ/2`.
- Signo de δ: campo desplaza el espectro en la dirección correcta.
- Campo hiperfino: posiciones externas escalan linealmente con BHF.
- Cuadrupolo magnético: rompe la simetría del sextete.
- Línea base plana sin componentes de absorción.
- Calibración de la malla de velocidades.

#### Nivel 6 — Datos reales (α-Fe, referencia publicada 33.0 T)

- BHF ajustado: 33.0 ± 0.5 T.
- δ ajustado: ISO_REF (−0.1092) ± 0.05 mm/s.
- Γ ajustada: rango físico 0.15–0.50 mm/s.
- χ²_reducido < 5.0 (ajuste aceptable con datos experimentales).

### `pytest.ini`

- Registrado el marcador `slow` para excluir Monte Carlo en CI:
  `pytest -m "not slow"` (208 tests, ~2 s) vs. `pytest` completo (211 tests, ~48 s).

---

## v4.10.1 — Sugeridor de fases, historial de ajustes y base de datos de referencia

Versión centrada en **identificación de fases**, **historial de ajustes persistente**
y una **ampliación importante de la documentación** (matemática bilingüe ES/EN).

### Nueva funcionalidad: sugeridor de fases (`core/phase_id.py`, `gui/phase_id_actions.py`)

- **Identificación bidireccional** de fases a partir de los parámetros hiperfinos
  (δ, ΔEQ, B_hf) de cada componente, comparando contra una base de datos de referencia:
  - **Al inicio**: tras *Inicializar desde mínimos*, propone las fases compatibles y
    permite, opcionalmente, **sembrar el ajuste** con sus valores de referencia.
  - **Tras el ajuste**: *Ajuste → Preparación → Identificar fases…* lista las fases
    compatibles con los valores ajustados, con su cita bibliográfica.
- **Interruptor maestro** *«Predicción de fases»* (**desactivado por defecto**): controla
  tanto la sugerencia automática al inicializar como la disponibilidad del identificador.
- Matching con distancia normalizada por dimensión, *gating* magnético/paramagnético por
  tipo de componente, inferencia de tipo y desempate suave por temperatura.

### Nueva funcionalidad: historial de ajustes (`gui/fit_history.py`)

- Cada ajuste terminado (discreto o distribución) se guarda con hora, fichero, modo,
  χ²/χ²ᵣ, resumen de componentes y un snapshot completo restaurable.
- **Persistente** (en memoria y en disco, `fit_history.json` junto a los settings):
  sobrevive al reinicio.
- **Tope configurable** desde el propio diálogo (*Máximo de entradas*, **50 por defecto**,
  rango 1–500). Restaurar reutiliza la maquinaria probada de cargar sesión.

### Nuevos datos (`data_sample/reference/`)

- **Base de datos de parámetros Mössbauer de referencia** (δ, ΔEQ, B_hf) para fases de
  hierro, con su procedencia bibliográfica (JSON + TSV + parser reproducible). Base del
  sugeridor de fases.

### Documentación

- **Documentos matemáticos corregidos y ampliados** y **traducidos al inglés** (manual
  principal, ajuste, distribuciones 1D/2D/IS, corrección de espesor, relajación magnética).
- **Nuevos documentos**: plegado (folding), ajuste en serie (batch), calibración α-Fe 33 T,
  comparación de espectros, formato de sesión JSON, detección de mínimos (CWT) y perfil de
  verosimilitud — todos en ES y EN.
- Corregida la documentación de relajación (NeelSize y ajuste multi-temperatura ya están
  implementados; el texto afirmaba lo contrario).

## v4.10.0 — Comparación de espectros, correcciones y documentación ampliada

Versión con **nueva funcionalidad de superposición visual de espectros**, **correcciones
de bugs** en la detección CWT y el diálogo Néel, y **documentación de ayuda ampliada**
a 30 capítulos en los tres idiomas (ES/EN/FR).

### Nueva funcionalidad: comparación de espectros (`gui/file_actions.py`, `gui/canvas.py`, `gui/plotly_tools.py`)

- **Archivo → Comparar espectro…**: carga hasta 6 espectros adicionales (`.ws5`, `.adt`,
  `.csv`, `.dat`) para superponerlos al espectro principal como líneas finas de colores
  distintos (naranja, teal, rosa, lima, violeta, azul cielo).
- **Archivo → Limpiar comparación**: elimina todos los espectros de comparación; la acción
  se habilita/deshabilita automáticamente.
- Los espectros de comparación aparecen también en la figura Plotly exportable (HTML interactivo).
- Los ADT/WS5 se doblan automáticamente usando el centro óptimo; los CSV se cargan directamente.
- Nuevo dataclass `ComparisonSpectrum(path, velocity, y_data, label)` en `gui/state.py`.

### Corrección de bugs

- **CWT kernel overflow** (`gui/minima_analysis.py`): el kernel Ricker se clampea a
  `(n−1)//2` para que nunca supere el tamaño del signal. Evitaba el ValueError
  `could not broadcast input array from shape (261,) into shape (254,)`.
- **Qt.ItemFlag** (`gui/dialogs.py`): `QTableWidgetItem.ItemFlag` no existe en PySide6;
  corregido a `Qt.ItemFlag.ItemIsEditable` (importando `Qt` de `PySide6.QtCore`).
- **fold_and_normalize** (`gui/file_actions.py`): la función devuelve 4 valores
  `(folded, sigma, y, norm)`; corregido el desempaquetado que esperaba 3.

### Documentación de ayuda (`locales/es,en,fr/help.json`)

- **28 → 30 capítulos** en los tres idiomas:
  - Nuevo capítulo **«Comparación de espectros»** / "Spectrum comparison" / "Comparaison de spectres"
    (grupo: ficheros): carga, normalización, paleta de colores, límite de 6 espectros, uso típico.
  - Nuevo capítulo **«Ajuste global Néel-Arrhenius»** / "Global Néel-Arrhenius fit" /
    "Ajustement global Néel-Arrhenius" (grupo: ajuste): diálogo de ajuste τ(T) = τ₀·exp(Eₐ/kT)
    sobre series de temperatura.
  - Capítulo «Archivo y web»: añadida sección sobre el formato CSV con columna de velocidad.
  - Capítulo «Novedades»: añadida entrada v4.9.0 y v4.10.0.

---

## v4.9.0 — Detección híbrida CWT, early-stop multistart y biblioteca de espectros de referencia

Versión con **mejoras en el motor de ajuste**, **nueva detección automática de mínimos
multi-escala** y una **biblioteca de 10 espectros sintéticos de referencia** para minerales
de hierro comunes. Incluye soporte de espectros pre-doblados en CSV y el diálogo de ajuste
global Néel-Arrhenius.

### Motor de ajuste (`core/fit_engine.py`)

- **Early-stop en multistart**: se detiene si el coste no mejora más de 1 ppm
  en 4 arranques consecutivos (`stagnation_patience=4`, `rel_tol=1e-6`), reduciendo
  tiempo de cómputo sin pérdida de calidad.

### Detección de mínimos (`gui/minima_analysis.py`)

- **CWT multi-escala con ondícula Ricker** (sustituye la convolución simple):
  detecta picos solapados en el rango físico Mössbauer (0.12–2.0 mm/s) con
  robustez frente a líneas anchas y sextetes.
- **Estrategia híbrida CWT + absorción directa**: la cresta CWT cubre líneas
  anchas/sextetes; el canal directo rescata dobletes estrechos que el CWT puede
  fusionar. Ambas listas se fusionan antes del filtrado final.
- **Corrección de desbordamiento CWT**: el kernel Ricker se clampea a
  `(n−1)//2` para que nunca supere el tamaño del signal (`np.convolve mode="same"`
  devuelve `max(M,N)`, no `M`).
- **Parámetros físicos ajustados** en `core/params.py`:
  - `init_gamma_min`: 0.08 → 0.10 mm/s (por encima del FWHM natural de Fe-57, ~0.097 mm/s)
  - `min_separation`: 0.12 → 0.15 mm/s

### Nuevos datos (`data_sample/public/`)

- **10 espectros sintéticos** de referencia con ruido Poisson realista (5 × 10⁶ cuentas):
  goetita, ferridrita, pirita, troilita, wüstita, ilmenita, jarosita, lepidocrocita,
  maghemita y pirrotita. Cada uno acompañado de su plantilla JSON de ajuste.
- **Script generador** `_generar_publicos.py` para reproducir o modificar los datos.
- **Espectro experimental real** de α-Fe calibración del ESRF
  (`alphaFe_calibracion_ESRF.dat`).

### Soporte de formatos (`core/data_io.py`)

- **Espectros pre-doblados en CSV/velocidad**: nuevos archivos `.dat` con columnas
  `velocidad, cuentas` se cargan directamente sin folding (útil para datos del ESRF
  y otros sincrotrones).

### Nuevas funcionalidades GUI

- **Diálogo GlobalNeelFitDialog** (`gui/`): ajuste global Néel-Arrhenius sobre
  múltiples espectros a distintas temperaturas, con exportación de parámetros.
- **Centralización de modos de intensidad y tratamiento cuadrupolar** en
  `core/params.py` (`INTENSITY_MODES`, `QUAD_TREATMENTS`) — fuente única para
  GUI y CLI.

### Tests (`tests/`)

- **Golden tests ampliados** (`test_headless_golden.py`): casos jarosita y siderita
  añadidos a los existentes (alphaFe, hematita). Los 4 casos son deterministas
  (semilla 12345) y protegen la física de regresiones numéricas.
- **Invarianza de signo para ΔEQ en dobletes** (`sign_invariant`): para un doblete
  puro sin BHF, `+ΔEQ` y `−ΔEQ` producen espectros idénticos; el test verifica
  `|s1_quad|` para evitar falsos negativos por diferencias de precisión numérica
  entre Python 3.11 y 3.12 / distintos BLAS.
- Correcciones en 3 tests sensibles al idioma (`test_qt_app.py`) y en el test
  de exportación TSV (`test_save_fit_writes_tsv`).

---

## v4.8.2 — Ayuda completa en tres idiomas y árbol de ayuda por grupo

Versión de **pulido de documentación interna**: sin cambios en el núcleo de
física ni en el motor de ajuste.

### Ayuda integrada (ES / EN / FR)

- **Paridad de capítulos**: inglés y francés pasan de 19 a **28 capítulos**,
  igualando la versión española. Se añaden 9 capítulos nuevos por idioma:
  - Menú Archivo / File menu / Menu Fichier
  - Menú Ajuste / Fit menu / Menu Ajustement
  - Perfil de línea (Voigt) / Line profile / Profil de raie
  - P(BHF): método / P(BHF): method / P(BHF) : méthode
  - P(BHF): parámetros / P(BHF): parameters / P(BHF) : paramètres
  - P(BHF): componentes nítidas / P(BHF): sharp components / P(BHF) : composantes nettes
  - Menú Vista / View menu / Menu Affichage
  - Menú Ayuda / Help menu / Menu Aide
  - Atajos y flujo rápido / Shortcuts and quick workflow / Raccourcis et flux rapide
- **Árbol de ayuda agrupado por campo `group`**: el árbol lateral de la ventana
  de Ayuda ahora agrupa los capítulos por su campo `group` (overview, files,
  fitting, distributions, results, tools) en lugar de usar índices fijos, lo que
  lo hace robusto ante reordenaciones o ampliaciones del JSON.

---

## v4.8.1 — Internacionalización completa, idioma por defecto inglés e informe reducido

Versión centrada en **pulido de la interfaz**: barrido exhaustivo de
internacionalización, cambio del idioma por defecto a inglés, un nuevo informe
reducido en PDF, y varias correcciones en sesiones, ajustes persistentes y
exportación de datos. No toca el núcleo de física/ajuste.

### Internacionalización (ES/EN/FR)

- **Barrido exhaustivo de cadenas hardcodeadas**: se han eliminado prácticamente
  todas las cadenas en español que estaban incrustadas en el código de la GUI y
  no pasaban por el sistema `tr()`. Afecta a barras de estado, títulos de diálogo,
  cabeceras de tabla, etiquetas de formulario y botones.
  - **Diálogos traducidos por completo**: límites de parámetros (70+ etiquetas
    científicas por idioma), configuración de layout (nombres de paneles y de
    presets predeterminados: Estándar/Tres columnas/Análisis/Compacto), API web
    (login, buscador, cabeceras de tabla, descarga), resumen para IA/LLM, y
    presets físicos de restricciones.
  - **Formulario de calibración local** (Sample / Vmax / IS), mensajes de barra
    de estado («Centro detectado», «Ajuste guardado», «Datos re-doblados»,
    «Ajuste base», verosimilitud perfilada) y el menú **Vista → Límites de
    parámetros…** ahora se traducen.
  - **Paridad de catálogos**: los tres idiomas mantienen exactamente el mismo
    conjunto de claves (744 cada uno).
- **Idioma por defecto cambiado de español a inglés** (`DEFAULT_LANGUAGE = "en"`).
- **«Ajuste con sextetes» → «Ajuste cristalino»** (EN: *Discrete fit*; FR:
  *Ajustement cristallin*), pues el modo admite singletes y dobletes, no solo
  sextetes.
- En inglés, la casilla de parámetro fijo pasa de «fixed» a **«fix»** para evitar
  que el texto se solape con los controles de subir/bajar valor.

### Informe reducido (Archivo → Exportar informe reducido MD/PDF…)

- Nuevo **informe condensado** en Markdown y PDF, complementario al informe largo
  (que se mantiene). Incluye solo los parámetros de cada componente, el análisis
  de áreas y la figura del espectro al final.
- **Renderer PDF propio y compacto**: cabecera y tablas reducidas, sin portada ni
  tarjeta de metadatos, para ocupar las menos páginas posibles.

### Exportación del ajuste (Archivo → Guardar ajuste…)

- El fichero TSV guarda ahora **los subespectros de cada componente**, no solo el
  modelo total.
- **Cabecera informativa** que indica fichero, fecha, modo (discreto/distribución)
  y el tipo de cada componente.
- Los nombres de tipo de componente se escriben **en inglés** (Sextet, Doublet,
  Singlet…) de forma consistente en todo el fichero de datos.

### Correcciones

- **Sesiones**: al cargar una sesión de ajuste discreto (p. ej. dos dobletes) ya
  no se salta erróneamente al modo distribución P(BHF). Se guarda el índice de
  modo explícito (`mode_combo_idx`), con compatibilidad hacia atrás para sesiones
  antiguas.
- **Arranques múltiples** (`multistart_n`): ahora se persiste en `settings.json` y
  se restaura entre arranques de la aplicación; también se restaura al cargar
  sesión, sin el límite máximo hardcodeado anterior.
- **Informes**: las tablas muestran solo los parámetros y magnitudes derivadas
  relevantes para cada tipo de componente (singlete/doblete/sextete), en lugar de
  todos los parámetros aunque no se hubieran ajustado.

### Créditos

- Se añade a **Nieves Menéndez González** como coautora.

## v4.8.0 — Editor de límites de parámetros y consolidación de constantes

### Diálogo de límites de parámetros (Vista → Límites de parámetros…)

- Nuevo diálogo accesible desde el menú **Vista** que permite editar todos los
  rangos y valores por defecto de los controles de la GUI sin tocar el código.
- Los cambios se guardan en `~/.config/mossbauer_fe33_gui/param_limits.json` y
  se aplican al reiniciar; `core/params.py` permanece como fuente de solo lectura.
- **Cinco pestañas**: Componentes (20 parámetros), Calibración (6), Distribución (16,
  incluyendo los nuevos IS mín/máx y ΔEQ mín/máx), Inicialización del ajuste (17)
  y Detección de picos (avanzado) (14).
- Cada pestaña incluye un botón «Restablecer a valores predeterminados».

### Nuevos parámetros configurables de distribución

- **IS mín / IS máx** (`is_lo` / `is_hi`): controlan el rango exterior de los
  sliders `bmin`/`bmax` cuando la distribución opera en modo IS (δ).
- **ΔEQ mín / ΔEQ máx** (`quad_lo` / `quad_hi`): ídem para modo ΔEQ distribuido.
- Antes estos límites eran fijos (±2.5 mm/s y 0–7 mm/s respectivamente).

### Consolidación de constantes en `core/params.py`

- `FIT_INIT_SPECS`: 17 parámetros de inicialización automática del modelo
  (límites BHF de detección, clips de Γ/δ/profundidad, rango L-curve, bootstrap,
  multistart) que antes eran literales dispersos en `gui/minima_analysis.py`,
  `gui/distribution_fit.py`, `gui/discrete_fit.py` y `gui/menu_builder.py`.
- `PEAK_DETECTION_SPECS`: 14 umbrales de detección y clasificación de picos
  (factores de altura/prominencia/distancia, tolerancias de match, ratios
  singlete/doblete, tolerancia de marcadores Plotly).
- `SEXTET_WEIGHTS = (3, 2, 1, 1, 2, 3)`: constante exportada que sustituye el
  literal repetido en la detección de sextetes.
- Los rangos del diálogo de calibración detallada y del spinner de arranques
  múltiples usan ahora los specs efectivos en lugar de valores hardcodeados.

### Corrección de bug: gamma/2 en `two_state_exchange_profile`

- `mossbauer_distribution.py` tenía una copia local de `two_state_exchange_profile`
  con un bug en el guard de gamma (usaba FWHM en lugar de semianchura). Corregido
  eliminando las funciones duplicadas e importando directamente desde `core.physics`,
  que tiene la implementación correcta.

## v4.7.5 — Mapas topográficos 2D y editor de atajos

Primera versión **estable** que consolida todo lo introducido en la pre-release
v4.7.4 (convención FWHM, deshacer ajuste, previsualización en vivo, intensidades
de doblete/singlete) y añade visualización 2D y atajos configurables.

### Mapas topográficos para distribuciones 2D

- Los ajustes **P(BHF, ΔEQ)**, **P(IS, ΔEQ)** y **P(BHF, IS)** muestran ahora la
  imagen topográfica del resultado P(x, y), que antes se calculaba pero no se
  dibujaba en ninguna parte.
  - **Canvas Matplotlib**: panel inferior con `pcolormesh` + contornos del mapa.
  - **Diálogo emergente**: heatmap principal con marginales P(x)/P(y) en
    disposición *corner-plot* y anotación de medias, sigmas y correlación.
  - **Plotly**: `go.Heatmap` interactivo con `go.Contour` superpuesto y hover
    con los valores exactos de x, y y P.
- El mapa persiste en los re-dibujos y se limpia al cambiar a un modo no-2D,
  lanzar un ajuste discreto o cargar otro fichero.
- Corrección: el ajuste 2D fallaba con `AttributeError` porque el resultado
  expone `alpha_bhf`/`alpha_quad` en vez de un único `alpha`.

### Editor de atajos de teclado

- **Ayuda → Atajos de teclado…**: cuadro para ver, asignar y restablecer los
  atajos de **32 acciones** de los menús Archivo/Ajuste/Vista/Ayuda (traigan o
  no atajo de fábrica). Los cambios se guardan en las preferencias y se aplican
  a los menús al instante; detección de conflictos sobre todos los atajos
  efectivos.
- Corrección: pulsar **Ctrl+Z** (Deshacer ajuste) tras un ajuste discreto
  saltaba indebidamente al modo Distribución P(BHF); ahora deshacer conserva el
  modo activo.

## v4.7.4 — Mejoras de interfaz y convención FWHM *(pre-release)*

### Cambio de convención: Γ pasa a ser FWHM

- **Anchura de línea en FWHM** en toda la aplicación. Hasta ahora Γ representaba
  el semianchura a media altura (HWHM); ahora es la anchura completa (FWHM = 2·HWHM),
  que es la convención habitual en espectroscopía Mössbauer y en los programas de
  referencia (NORMOS, MossWinn).
- La física es idéntica: `lorentzian()` divide γ/2 internamente. Los valores
  visibles en la GUI son el doble de los anteriores (p. ej. α-Fe: 0.28 mm/s en
  vez de 0.14 mm/s).
- Importación Normos (.RES): WID ya se guardaba en FWHM; se elimina la división
  por 2 que existía en `core/folding.py`, `core/data_io.py` y `mossbauer_ws5.py`.
- Todos los valores por defecto, límites, plantillas JSON de `data_sample/`,
  documentación ES/EN/FR y tests actualizados.

### Render en vivo durante el ajuste discreto

- La figura se actualiza en tiempo real mientras corre el optimizador (~4 fps,
  limitado por el throttle de 0,25 s ya existente en el callback de progreso).
- Sin impacto en velocidad: el canvas se repinta con `reconstruct_discrete_model`
  usando los parámetros libres actuales sin tocar los widgets.

### Deshacer ajuste (Ctrl+Z)

- **Ajuste → Deshacer ajuste** (Ctrl+Z): recupera todos los parámetros al estado
  previo al último ajuste (discreto o distribución).
- La acción se habilita al completar el primer ajuste y se deshabilita tras
  deshacer (un solo nivel de undo).

### Corrección: widgets enlazados no se actualizaban visualmente

- Al modificar un parámetro fuente (p. ej. δ del componente 1 enlazado al δ del
  componente 2), el spinbox del parámetro objetivo no mostraba el valor actualizado
  aunque la figura sí se redibujaba correctamente. Corregido en
  `_sync_constraint_targets()` llamado desde `_on_model_param_changed`.

### Arranques múltiples configurables

- **Ajuste → Opciones avanzadas → Arranques múltiples (0–10)**: permite elegir
  cuántas perturbaciones aleatorias se lanzan en el multistart (por defecto 8).
  `0` = un único arranque desde los valores iniciales (ajuste más rápido).
  El valor se guarda en la sesión.

### Intensidades de doblete y singlete

- En **doblete** se oculta `I13` (redundante con la profundidad) y la intensidad
  restante (`I23` → etiqueta «I rel (L2/L1)») pasa a representar la relación entre
  las dos ramas, con valor inicial 1.0 (ramas simétricas) fijo por defecto.
- En **singlete** se ocultan ambas intensidades (`I13`/`I23`): la profundidad ya
  fija el área de la única línea.

### Etiquetas de anchura: global vs relativa

- Γ1 se etiqueta como anchura **absoluta (global, mm/s)** y Γ2/Γ3 como **ratios**
  relativos a ella (`Γ 2,5 / Γ₁`, `Γ 3,4 / Γ₁`), dejando explícito que
  Γ_real = Γ1·Γ2. Las etiquetas se adaptan al tipo de componente (los números de
  línea 1,6 / 2,5 solo aplican al sextete; doblete y singlete usan variantes propias).

## v4.7.3 — Reorganización de menús y ayuda alineada

### Interfaz

- **Menú «Opciones» eliminado.** Duplicaba entradas de Ajuste y Vista
  compartiendo los mismos `QActionGroup` exclusivos, por lo que sus radios y
  checkmarks no podían reflejar el estado real (mismo defecto que el «Tema
  visual» duplicado retirado en v4.7.1). Desaparecen también las lambdas de
  sincronización entre menús.
- **Menú Ajuste reagrupado**: «Modo de ajuste» (radios con los **7 modos** del
  combo lateral, antes solo 2, con sincronización en ambos sentidos también
  para P(ΔEQ)/P(IS)/2D), submenús «Preparación» (centro, mínimos, IA) y
  «Análisis de errores» (bootstrap, verosimilitud perfilada y L-curve, antes
  desubicada al final del menú), bloque de parámetros y Opciones avanzadas.
- **Archivo**: «Open Recent» traducido (clave `file.open_recent` ES/EN/FR) y
  «Usar como calibración» junto a Cargar/Recientes.
- `fit_mode_labels()` en `gui/main_layout.py` como fuente única de las
  etiquetas de modo (combo lateral + menú).

### Ayuda integrada

- ES: eliminado el capítulo «Menú Opciones»; «Menú Ajuste» reescrito y
  reordenado según el menú real, con entrada nueva para «Editar mínimos
  (semi-manual)» (existía en el menú pero no estaba documentada); «Abrir
  recientes» en Menú Archivo.
- Rutas «menú → ítem» actualizadas en los tres idiomas (Buscar centro,
  Bootstrap, Verosimilitud perfilada y L-curve apuntan a sus submenús nuevos);
  verificado con un inventario automático sin referencias obsoletas.

---

## v4.7.2 — Revisión de fallos latentes, batch coherente e i18n de actualizaciones

### Bugs corregidos

- **Cargar P fija lanzaba `NameError`.** `gui/distribution_fit.py` usaba `Path`
  y `ROOT` sin importarlos/definirlos; la acción «Cargar P fija» fallaba siempre.
- **Diálogos web siempre en español.** El patrón `tr(...) if hasattr(tr, "_d")
  else "literal"` de `gui/web_api.py` era siempre falso, así que se ignoraban
  las traducciones EN/FR existentes. Sustituido por `tr(clave, default=...)`.
- **Duplicados divergentes en `core/data_io.py`.** Tenía copias antiguas de las
  funciones de lectura/folding que habían divergido de `core/folding.py` (sin la
  heurística ≥400 del folding point Normos; `weight_sum` 4 vs 12 al estimar
  `depth` desde ARE). Ahora reexporta las canónicas de `core.folding`.
- **Desalineación latente en `core/fit_engine.py`.** Los globales
  `vmax`/`center`/`voigt_sigma` se añadían a `x0` solo si la clave existía en
  `values`, pero el residuo y el desempaquetado final solo miraban el flag;
  un flag activo sin clave desalineaba el vector de parámetros. Condiciones
  unificadas en las tres rutas.
- **El batch doblaba distinto que el flujo principal.** El diálogo de lote
  (`gui/dialogs.py`) ahora usa `fold_and_normalize` (recorte de borde) y
  `velocity_axis`, igual que la GUI e `HeadlessSession`, y el `FitState` recibe
  `counts`/`norm_factor`/`center` del fichero del batch (antes conservaba los
  del espectro cargado, afectando al re-folding de `fit_center` y la σ Poisson).
  Los resultados de batch pueden variar ligeramente respecto a series antiguas
  (se excluyen los dos canales de borde); batch e individual ahora coinciden.

### Internacionalización

- **Diálogos de actualización traducidos** (`gui/updates.py`): 31 claves nuevas
  `updates.*` en los catálogos ES/EN/FR; antes todo el flujo de actualizaciones
  aparecía en español también con la interfaz en inglés o francés.

### Robustez y limpieza

- `mossbauer_updater.py`: si una descarga falla a medias se borra el fichero
  parcial en lugar de dejarlo en Descargas.
- `gui/dialogs.py`: eliminada una línea muerta del batch y protegido el flag
  `_building` del warm-start con `try/finally`.
- Comentario de `LINE_POS_33T` en `mossbauer_distribution.py` corregido
  (contradecía la convención del patrón publicado de α-Fe; ver v4.0.2/v4.0.3).
- Docstrings que aludían a la GUI Tk eliminada e imports redundantes.

---

## v4.7.1 — Revisión completa de ayuda y corrección de menú

### Documentación y ayuda integrada (ES/EN/FR)

- **Referencias bibliográficas** añadidas en todos los idiomas: Hesse & Rübartsch
  (1974) para P(BHF), Hansen (1992) para L-curve/GCV, Blume & Tjon (1968) para
  relajación dinámica de dos estados, Néel (1949) y Brown (1963) para NeelSize,
  Margulies & Ehrman (1961) para absorbente grueso, Kündig (1967) para tratamiento
  cuadrupolar Hamiltoniano completo.
- **FR P(ΔEQ)** expandido desde 280 a ~2200 chars: modelo, parámetros BHF fijo/
  rangos/δ global, usos típicos y precauciones sobre correlaciones.
- **FR L-curve** expandida: descripción de GCV (validación cruzada generalizada)
  y referencia Hansen (1992).
- **FR Contraintes** expandida: ejemplos con sintaxis real y sección de presets
  físicos con los cuatro botones disponibles.
- **ES capítulo 27** («Acceso a opciones y novedades») convertido en índice corto
  que apunta a los capítulos temáticos propios; conserva las tres funciones sin
  capítulo propio (comportamiento simulación, calibración por clic derecho, δ
  corregido). Elimina duplicación con Menú Ajuste, P(BHF): método/parámetros y
  Restricciones.
- **ES capítulo 29** («Novedades desde v0.2») reducido de 12 804 a ~4 800 chars:
  elimina la entrada v0.2.0 (referenciaba GUI obsoleta), condensa v0.2.1–v0.2.6
  en lista de bullets con punteros, mantiene los how-to de bootstrap y presets,
  resume v0.4.2–v0.4.11 en una línea por versión.
- **EN P(ΔEQ)** ya expandido en PR anterior; **EN absorbente grueso** y **Kündig**
  descritos con fórmula y referencia en «Accessing options».

### Corrección de menú

- **Bug: Tema visual duplicado en Opciones.** El submenú `Opciones → Tema visual`
  creaba acciones sin `QActionGroup` y sin sincronización con `Vista → Tema visual`
  (que sí usa grupo exclusivo). El checkmark de Opciones nunca reflejaba el tema
  activo. Se elimina el submenú de Opciones; el tema sigue operativo en
  **Vista → Tema visual**.
- **Separador en menú Ajuste** entre herramientas pre-ajuste (Buscar centro,
  Inicializar, IA Ollama) y post-ajuste (Bootstrap, Verosimilitud, Lote).

---

## v4.7 — Reconciliación arquitectónica y mejoras de interfaz

> **Contexto histórico.** La v4.5 (refactorización modular de `gui/`) se
> publicó y tuvo que revertirse porque la v4.6 (física nueva: relajación,
> distribuciones 2D/IS) se había desarrollado en paralelo sobre la
> arquitectura anterior. Esta versión fusiona definitivamente ambas líneas:
> toda la física de la 4.6 sobre la arquitectura modular de la 4.5, más
> los cambios descritos a continuación.

### Reconciliación v4.5 + v4.6

- **Arquitectura modular `gui/`** (originada en v4.5) integrada con toda la
  física de la v4.6: los módulos `gui/discrete_fit.py`, `gui/distribution_fit.py`,
  `gui/model_workflow.py`, `gui/fit_workflow.py`, etc. son la base definitiva.
- **Corrección de tipos desconocidos.** `core/validation.py` y `core/session.py`
  ahora usan `COMPONENT_KINDS` y `DISTRIBUTION_SHAPES` de `core/params.py` como
  fuente única, eliminando los errores «tipo desconocido 'Relajacion'» y «tipo
  desconocido '2D'» que aparecían en la versión reconciliada anterior.
- **Restauración de sesión completa.** `gui/session_io.py` acepta todos los tipos
  de componente (`Relajacion`, `BlumeTjon`, `NeelSize`) y todas las formas de
  distribución (`2D`) al cargar una sesión guardada.

### Mejoras de interfaz (panel de componentes)

- **Reflow dinámico del panel de componentes.** Los parámetros aparecen y
  desaparecen sin huecos al cambiar el tipo; solo se muestran los relevantes
  para cada tipo según `USED_BY` de `core/params.py`.
- **Columnas equilibradas automáticamente.** Si una columna supera a la otra
  en más de dos filas, el exceso se redistribuye, evitando columnas muy cargadas
  junto a columnas casi vacías (especialmente visible en NeelSize y Relajacion).
- **Altura fija de controles.** `ParamControl` y `ComponentPanel` tienen política
  de tamaño `Fixed` vertical: los campos nunca se comprimen aunque haya muchos
  parámetros; el `QScrollArea` del panel izquierdo se encarga del desplazamiento.
- **Conmutación apilado↔pestañas por altura real.** El umbral que decide cuándo
  pasar de componentes apilados a pestañas usa `sizeHint()` de cada panel en
  lugar de una constante fija, de modo que tipos con muchos parámetros (NeelSize)
  activan el cambio al tamaño correcto y sin oscilaciones. La comprobación también
  se dispara al cambiar el tipo en el combo, no solo al redimensionar la ventana.

### Mejoras del diálogo de progreso de ajuste

- **Diálogo detallado restaurado.** Durante el ajuste se muestran fase, número
  de evaluaciones, RMS actual y mejor, y tabla de parámetros libres con sus
  valores en curso — información que se había perdido en la reconciliación.
- **Botón Cancelar.** Un botón en el diálogo de progreso permite abortar el
  ajuste en cualquier momento de forma limpia (`FitCancelledError`), sin
  mensajes de error espurios.

### Calidad y tests

- **Whitelists centralizadas.** `COMPONENT_KINDS` y `DISTRIBUTION_SHAPES` en
  `core/params.py` son ahora la fuente única para validación, sesión y GUI;
  añadir un nuevo tipo o forma ya no requiere buscar todas las listas dispersas.
- **Tests de regresión.** Nuevos tests en `tests/test_qt_app.py` y
  `tests/test_validation.py` cubren: tipos nuevos en validación, restauración
  de sesión con `Relajacion`/`2D`, cancelación del ajuste, reflow sin huecos
  por columnas y ningún campo fuera del grid.

### Pendiente / trabajo en curso

- **TODO (punto 3):** Centralizar las listas de `intensity_mode`
  (`"free"`, `"texture"`) y `quad_treatment` (`"1st_order"`, `"kundig_fixed"`,
  `"kundig_powder"`) en `core/params.py`, igual que se hizo con
  `COMPONENT_KINDS`/`DISTRIBUTION_SHAPES`, para que añadir nuevos modos no
  sea un bug silencioso (ver `gui/session_io.py`).
- **TODO (punto 4):** Evaluar reconstrucción de nítidos con `build_sharp_kernel`
  (SHA `a7c803b`) como alternativa más fiel cuando el ajuste refina δ/Γ globales
  (ver `gui/distribution_fit.py`).
- **Multi-ajuste con temperaturas** (Néel-Arrhenius global sobre series de
  espectros a distintas temperaturas): pendiente de implementación.

## v4.6 — Distribuciones generalizadas y relajación magnética

- Distribuciones 2D: backend `mossbauer_distribution.fit_bhf_quad_distribution()` generalizado para pares `BHF`, `ΔEQ/QS` e `IS`; integración en la GUI como modos **P(BHF, ΔEQ) 2D**, **P(IS, ΔEQ) 2D**, **P(BHF, IS) 2D** y distribución 1D **P(IS)**, con mapa de calor, marginales, heatmap Plotly, exportación TSV, L-surface `αx/αy`, componentes nítidos simultáneos, diagnósticos (medias, sigmas, correlación aparente, dof efectivo) e informe PDF con mapa 2D; advertencias de sobreajuste/identificabilidad en ayuda y documentación matemática. Nuevo documento `docs/distribuciones_is_mossbauer.pdf` para `P(IS)` y `P(IS, ΔEQ)`.
- Relajación magnética: implementación completa desde el modelo fenomenológico y dinámico (Blume-Tjon) hasta la distribución de tamaños Néel-Arrhenius y ajuste global multi-temperatura.
- En distribuciones `P(BHF)`, `δ`, `ΔEQ` y `Γ` se refinan directamente si su casilla **fijo** está desmarcada; se elimina el interruptor extra “refinar δ y Γ globales”. En `P(ΔEQ)`, `ΔEQ` sigue siendo la variable distribuida y no se refina como parámetro global.
- Las sesiones guardan y restauran los parámetros propios del panel de distribución y sus estados fijo/libre.
- La ventana de progreso del ajuste muestra ahora fase, evaluaciones, RMS actual/mejor y tabla de parámetros libres durante el refinamiento de distribuciones.
- El parámetro `β` del sextete se oculta salvo en el tratamiento cuadrupolar **Kündig fijo** y se renombra a `β Kündig (BHF↔Vzz, °)` para evitar confundirlo con versiones beta.

## v4.5 — Arquitectura Qt modular, estado formal y core más puro

- **Refactorización completa de la GUI Qt.** `mossbauer_qt.py` queda como punto de entrada fino y la lógica se organiza en módulos `gui/` especializados: layout, menús, sesiones, ajustes, distribución, Plotly, informes, actualización, API web y compatibilidad.
- **Snapshots de estado GUI.** Se introducen `ComponentViewState`, `CalibrationViewState`, `DistributionViewState`, `UiActionState`, `ProjectState` y otros estados para reducir el acoplamiento widget→lógica.
- **Flujo común de ajuste.** Los modos discreto y distribución comparten progreso, manejo de errores, render y `GuiFitResult` mediante `gui.fit_workflow` y `RuntimeResultState`.
- **Reconstrucción física fuera de la GUI.** `core.reconstruction` centraliza reconstrucción de modelos, residuos, curvas densas, áreas, porcentajes y subespectros de distribuciones con componentes nítidas.
- **Validación de parámetros en core.** `core.validation` comprueba límites, finitud, rangos de distribución, tamaños de arrays y coherencia antes de lanzar ajustes.
- **API interna de resultados.** `core.result_views` proporciona vistas de solo lectura para estadísticas, parámetros, errores, curvas de distribución y métricas, usadas por informes, Plotly y paneles.
- **Compatibilidad histórica centralizada.** `gui.compat` agrupa los puentes para símbolos parcheables de `mossbauer_qt.py` y propiedades legacy.
- **Documentación y tests.** Nuevos documentos `docs/architecture.md` y `docs/user-flows.md`; más tests específicos para snapshots, flujo de ajuste, reconstrucción, validación, vistas de resultado y compatibilidad.

## v4.1.0 — Interfaz única Qt y ajuste headless en core

- **Se elimina por completo la interfaz Tk.** La aplicación tiene ahora una sola interfaz gráfica, la Qt (`mossbauer_qt.py`). Se retiran el monolito `mossbauer_fe33_gui_v2IA.py`, `mossbauer_app.py`, el paquete `panels/`, el gestor/configurador Tk de `layout/`, el diálogo Tk de actualizaciones (`mossbauer_updater_ui.py`), `Fitbauer-Tk.spec` y la dependencia `sv_ttk`.
- **Capa de ajuste headless en `core/session.py`.** La orquestación cargar → doblar → ajustar → sesión que antes vivía en la app Tk se extrae a `core.session` (`ModelState` + `HeadlessSession`), sin dependencia de ninguna GUI y reusando `core.fit_engine`/`core.folding`. El CLI `mossbauer_fit_cli.py` ya no necesita display ni Tk.
- **Lanzador simplificado.** `fitbauer.py` arranca directamente la interfaz Qt (sin opciones `--tk`/`--qt` ni respaldo Tk).
- **Funciones de actualización sin GUI** (`load/save_update_settings`, `check_requirements_if_needed`, refresco de dependencias pip) trasladadas de `mossbauer_updater_ui.py` a `mossbauer_updater.py`.

## v4.0.4 — Nítidos fijos y subespectros en distribuciones

- **Profundidad fija real en componentes nítidos.** En los ajustes `P(BHF)` / `P(ΔEQ)` con nítidos, si `depth` está marcada como fija, el backend la trata como contribución de absorción conocida y no como amplitud ajustable. Los nítidos libres conservan amplitud `>= 0` ajustable.
- **Backend consistente en todas las formas de distribución.** La corrección cubre histograma/Tikhonov, gaussiana, binomial y distribución fija.
- **Subespectros visibles.** Al ajustar distribución + nítidos se muestran la contribución de la distribución sola, cada nítido por separado y el ajuste total, facilitando diagnosticar el reparto de absorción.

## v4.0.3 — Corrige el BHF de calibración (regresión de v4.0.2)

- La **v4.0.2** publicada derivaba las posiciones del sextete de los momentos nucleares de libro, lo que daba un desdoblamiento ~0,4 % menor (línea externa 5.309 vs 5.328 mm/s a 33 T) y **sesgaba el BHF ~0,1 T hacia arriba** (un α-Fe leía 33.12 T en vez de 33.0).
- Se vuelve al **patrón de velocidad publicado de α-Fe** (`±0.839 / ±3.084 / ±5.329 mm/s` a 33 T): un α-Fe ajusta a **33.0 T exacto, igual que NORMOS**. Documentado en el código para no reintroducir el sesgo.

## v4.0.2 — Calibración del campo a 33.0 T

- **Elimina la constante interna `32.95 T`**: la calibración de velocidad/campo (Tk, Qt, modelo discreto y distribución) usa el campo de referencia **33.0 T (330 kOe)**.
- **Fuente única.** `mossbauer_distribution.py` toma `LINE_POS_33T` de `core.constants`, eliminando una tercera copia duplicada de las posiciones.
- Incluyó un cálculo de las posiciones desde los momentos nucleares que resultó **sesgar el BHF ~0,1 T** (corregido en v4.0.3).
- Limpieza: se elimina el parámetro muerto `max_nfev` de `profile_likelihood()`.

## v4.0.1 — Logo en la interfaz

- El logo de Fitbauer se muestra ahora dentro del programa: tarjeta de cabecera, pantalla de inicio (splash) y diálogo «Acerca de», tanto en la interfaz Qt como en la Tk.
- Carga robusta del logo: si la imagen no está disponible se conserva el comportamiento anterior (texto / dibujo vectorial).

## v4.0 — Fitbauer

Cambio de marca y preparación para producción.

### Identidad

- La aplicación pasa a llamarse **Fitbauer** — *Software for Mössbauer spectrum fitting and analysis*.
- Nuevo logo/icono (`assets/fitbauer_icon.*`, fuente vectorial `assets/fitbauer_logo.svg` generada por `assets/make_logo.py`): firma de un sextete Mössbauer con su curva de ajuste sobre insignia azul→cian.

### Arranque unificado

- Nuevo punto de entrada único `fitbauer.py` (y lanzadores `fitbauer` / `fitbauer.bat`): abre la interfaz Qt por defecto y cae automáticamente a la Tk si PySide6 no está disponible o falla. Opciones `--tk` / `--qt`.
- Los ejecutables PyInstaller pasan a `Fitbauer.spec` (Qt, principal) y `Fitbauer-Tk.spec` (Tk, respaldo).

### Limpieza del repositorio

- `layout.json` deja de versionarse (es estado de runtime) y se añade a `.gitignore`.
- Eliminado `download_and_fit_calibrations.py` (roto e inutilizado: importaba un módulo inexistente).
- Retiradas notas de versión sueltas (`RELEASE_NOTES_v*.md`, `RELEASES.md`) — el historial vive en este `CHANGELOG.md` — y documentos internos de roadmap (`PROPUESTAS_*.md`, `NORMOS_comparison_improvements.md`).
- Capturas movidas a `docs/img/`.

## v3.7 — Informe completo, ayuda jerárquica y textura interpretada

Release estable. Foco en el informe Markdown/PDF y en el diálogo de Ayuda.

### Plotly en Qt

- El gráfico Plotly ocupa todo el alto del tab (flex `100%`) en lugar de un `72vh` fijo.
- Eliminado el *debounce* de 300 ms en las actualizaciones: ahora el gráfico se refresca de forma inmediata al mover sliders o cambiar parámetros (`QTimer` a 0 ms).

### Sextete: textura interpretada

- Para sextetes en modo de intensidades por **textura** (`I₂/I₃ = 4t/(2-t)`), se calculan y se muestran tres magnitudes físicas derivadas de `t = sin²θ`:
  - **θ** = `arcsin(√t)`: ángulo entre el campo hiperfino y el rayo γ (54.7° = ángulo "mágico" para muestra random).
  - **R₂₃** = I₂/I₃: razón de intensidades.
  - **S** = ⟨P₂(cos θ)⟩ = 1 − 3t/2: orden tipo Hermans (+1 alineado a γ, 0 isótropo, −½ perpendicular).
- Cada magnitud trae su σ propagada a partir de σ(t) cuando t es libre en el ajuste.
- Aparecen en el cuadro "Estado y parámetros" tras cada ajuste / cambio.

### Informe (Markdown + PDF) completo

- El informe ahora reproduce **toda** la información del panel "Estado y parámetros" como tablas estructuradas:
  - Espectro y plegado (canales, folding centro y Normos, pares doblados, normalización, perfil de línea).
  - Calibración y escala de velocidades (Vmax, baseline, slope, fit_velocity, calibración, δ ref, σ).
  - Bondad y diagnóstico (χ², χ²ᵣ, dof, AIC, BIC, nº params, RMS, multistart, diagnóstico residual lag-1 / runs z / antisymmetric corr con umbrales, correlación máxima y pares muy correlacionados).
  - **Análisis de áreas** por componente con % + σ + área absoluta (la σ estaba ausente).
  - Por componente, nuevo subbloque "Magnitudes físicas derivadas" con Γ HWHM reales, FWHM equiv., Γ relativas, profundidad, I₁/I₂/I₃ reales, BHF, δ, ΔEQ y δ corregido destacado.
  - Bloque "🧭 Magnitudes derivadas de la textura" con su tabla y un callout explicando el significado físico.
  - **δ corregidos por calibración**: tabla resumen δ ajustado vs. δ corregido.
  - **Parámetros fijados** y **Restricciones** como bloques dedicados.
  - **📖 Glosario de parámetros** al final del informe (δ, ΔEQ, BHF, Γ, depth, intensidades, textura, β, voigt_sigma, sat_scale, baseline, slope, Vmax).

### PDF rediseñado

- Portada con banner azul, título, fichero, fecha y cuadros con χ²ᵣ, χ², AIC, BIC, nº de componentes y nº de parámetros libres.
- Cuerpo parseado en bloques tipados (h3, párrafo, callout, código y **tablas reales**) en vez del volcado monoespaciado anterior. Las tablas tienen encabezado a color, filas zebra y anchos proporcionales con truncado por elipsis. Los callouts llevan barra lateral de color. Los emojis se filtran (DejaVu no los renderiza).

### Diálogo de Ayuda

- Barra lateral en **árbol jerárquico** que refleja la estructura real de menús del programa (Archivo, Ajuste, Opciones, Vista, Ayuda) + grupos temáticos de Conceptos físicos y Distribuciones P(BHF) / P(ΔEQ). Las cabeceras de grupo no son seleccionables y, al pulsarlas, saltan al primer capítulo del grupo.
- **Buscador** en la cabecera que filtra el árbol y resalta los aciertos en el panel de contenido con `<mark>`; cuenta los capítulos coincidentes.
- **HTML enriquecido**: el texto plano de cada capítulo se convierte a HTML con subtítulos h4, listas con viñetas y numeración, **negrita**, *cursiva* y `código` inline.
- **Negrita automática para las etiquetas de menú**: se construye un regex case-sensitive con todos los valores de `menu.*`, `file.*`, `fit.*`, `options.*` y `view.*` del catálogo activo (más un subconjunto de `help.*`), ordenados por longitud para que las etiquetas largas ganen prioridad. Variantes sin elipsis para etiquetas multi-palabra.
- Tipografía mejorada (h2/h3 con jerarquía visual, padding generoso, h3 subrayado), splitter 340/840 y diálogo 1180×760.

### Versión

- La versión local de la aplicación pasa a `3.7`.

## v3.6 — Plotly Qt corregido y listado web mejorado

Release estable con los cambios posteriores a v3.5.

### Plotly en Qt

- Corregida la vista Plotly en Qt cuando aparecía en blanco, sin datos ni ejes, cargando el HTML desde fichero local en vez de `setHtml()`.
- Eliminado de nuevo el bloque de metadatos bajo el gráfico Plotly para dejar solo la figura interactiva.
- Restaurada y mejorada la edición semi-manual de mínimos: botón visible en la pestaña Plotly, clic en el espectro para añadir mínimos y clic sobre/cerca de un marcador para activarlo o desactivarlo.

### Descarga web

- Corregida la consulta de medidas/calibraciones desde la GUI Qt aceptando `limit` en el cliente API.
- Listado web más legible: fichero abreviado a 13 caracteres, muestra con más espacio, fecha, temperatura, velocidad display (`velocity_input`) e id de calibración asociada.

### Versión

- La versión local de la aplicación pasa a `3.6`.

## v3.5 — integración Plotly y edición semi-manual de mínimos

Agrupa todos los cambios incorporados desde v3.0.

### Interfaz Qt/Plotly

- Integración de un gráfico **Plotly interactivo** en la GUI Qt para explorar espectros, ajustes, componentes y residuos con zoom/pan más fluido.
- Refresco incremental del gráfico para reducir redibujados completos y mejorar la respuesta durante simulación y ajuste.
- Curva de ajuste densa para una visualización más suave del modelo.
- Uso de trazas WebGL cuando conviene para mejorar el rendimiento con muchos puntos.

### Edición y ayuda

- Nuevo editor **semi-manual de mínimos** en la interfaz Plotly/Qt para revisar, añadir y ajustar mínimos detectados antes de inicializar componentes.
- Ayuda de los menús Qt ampliada y documentada en español.

### Empaquetado y versión

- La versión local de la aplicación pasa a `3.5`.
- Se mantiene compatibilidad con sesiones, plantillas y datos de v3.0.

## v3.0 — interfaz Qt y núcleo de cálculo unificado

Release mayor. Incorpora una segunda interfaz gráfica (Qt/PySide6) y, sobre todo,
unifica todo el cálculo en `core/`, compartido por la GUI Tk, la GUI Qt, el CLI y
el ajuste en serie.

### Interfaces y empaquetado

- Nueva **GUI Qt (PySide6)** junto a la GUI Tk clásica; ambas sobre el mismo núcleo.
- **Dos ejecutables**: Tk (`MossbauerFeFit.spec`, lanzadores `mossbauer`/`mossbauer.bat`)
  y Qt (`MossbauerFeFit-Qt.spec`, lanzadores `mossbauer-qt`/`mossbauer-qt.bat`).
- Informe (Qt) con tabla de parámetros valor ± σ, origen de la incertidumbre
  (covarianza o bootstrap), bondad (χ²ᵣ/χ²/AIC/BIC) y correlaciones altas.

### Núcleo de cálculo (`core/`) unificado

- Física del modelo única en `core.physics` (el Tk la reutiliza).
- Motor de ajuste único en `core.fit_engine`, usado por Tk, Qt, CLI y batch:
  multistart + optimización global + pérdida robusta + covarianza, re-folding del
  centro, σ de calibración (escala Vmax) y σ Poisson correcta, modo textura y
  restricciones encadenadas, bootstrap (Poisson) y verosimilitud perfilada como
  funciones puras. Eliminada la duplicación del optimizador en el Tk.
- CI ejecuta la suite completa (GUIs Tk/Qt, CLI y batch) headless con Xvfb/offscreen.

## v2.3-beta1 — prerelease no estable

Versión beta para validar cambios posteriores a v2.2 antes de una release estable.

- Vmax con signo conservado en GUI, CLI y calibraciones web.
- Corrección del eje de velocidades al recortar el primer y último punto doblado: se recorta el eje original en vez de reconstruirlo a ±Vmax con menos canales, evitando sesgo sistemático en BHF.
- Convención NORMOS para intensidades de sextete: int3 oculto/fijo a 1, int1≈D13, int2≈D23 y DEP/profundidad como escala global.
- Profundidad por defecto 0.02, Γ por defecto 0.15 mm/s y barra de profundidad 0–0.07 con límite interno de ajuste más amplio.
- Menú contextual en σ para alternar Lorentziana/Voigt.
- Icono de aplicación para gestor de ventanas/Alt-Tab.
- Padding reducido en botones del diálogo de actualización.
- Ayuda/README ampliados e informe de ejemplo Fe3O4 en Markdown/PDF.

## v2.2 — ajuste en serie, CLI y compatibilidad NORMOS

Agrupa todos los cambios incorporados desde v2.1 y prepara la nueva release.

### Ajuste y física

- Ajuste en serie desde la GUI con warm-start secuencial para procesar lotes de espectros relacionados.
- CLI de ajuste por fichero a partir de una plantilla JSON y un espectro, con salida JSON reproducible.
- Errores asimétricos opcionales por verosimilitud perfilada.
- Ajuste opcional de `σ` en perfiles Voigt y control visible desde el menú contextual del slider de `σ`.
- Selector de perfil Lorentziana/Voigt desde el clic derecho del control `σ`.
- Límites ampliados de `BHF` hasta 60 T y soporte para `ΔEQ` negativo.
- Modelo experimental opt-in de absorbente grueso/saturación, disponible tanto en ajuste discreto como en distribución, con refinamiento VARPRO de `(b, s, C)`.

### Datos, CLI y documentación

- Nuevos espectros sintéticos de compuestos de hierro y espectros sintéticos adicionales con ruido reducido.
- Plantillas CLI listas para magnetita, hematita, siderita y α-Fe.
- Capítulo de ayuda sobre el CLI en español, inglés y francés.
- Documento técnico sobre la corrección por espesor en `docs/correccion_espesor.*`.
- Ayuda ampliada sobre `VMAX`, signo del eje de velocidades y criterios de calibración.

### Interfaz y trazabilidad

- Menú de estilos de gráficos: clásico, moderno, publicación y oscuro.
- Corrección de la detección del punto de plegado (`PFP`) y mejor alineación con la convención NORMOS.
- Ajustes de GUI/calibración para reproducir mejor flujos NORMOS, incluido `Vmax` con signo.
- Eliminación de la caja de cabecera de presets para simplificar la interfaz.
- Ventana **Acerca de** cerrable con clic.

### Calidad

- Suite inicial de `pytest` y workflow de CI en GitHub Actions.
- Corrección del cableado del checkbox modular para ajustar `σ`.

## v2.1 — motor de ajuste ampliado y usabilidad

Incorpora las mejoras desarrolladas tras el manual matemático del motor de
ajuste (`docs/manual_mossbauer.pdf`).

### Motor de ajuste

- Verosimilitud seleccionable Gauss / Poisson (IRLS sobre σ del modelo).
- Pérdida robusta opcional (Soft L1 / Huber) frente a canales con picos espurios.
- Propagación de la incertidumbre de calibración (σ de vmax) a los pesos.
- Optimización global opcional (evolución diferencial) antes del pulido TRF.
- Tratamiento de Kündig del cuadrupolo (Hamiltoniano axial, β libre) y promedio policristalino, además del 1er orden.
- Parámetro de textura por sextete (t = sin²θ → 3 : 4t/(2−t) : 1).
- Normalización analítica del perfil Voigt (independiente del muestreo).

### Distribución P(BHF) / P(ΔEQ)

- Regularización por Variación Total (bordes afilados) además de Tikhonov.
- Selección automática de α por GCV (junto a curva L y compromiso).
- Grados de libertad efectivos en el χ² reducido.
- Barras de error 1σ de P(BHF) por covarianza linealizada.
- Preacondicionamiento de la matriz núcleo para BHF pequeño.

### Usabilidad

- Submenú "Ajuste → Opciones avanzadas de ajuste" para descongestionar el menú.
- Menús contextuales (clic derecho) en los sliders para elegir modo de intensidades y tratamiento del cuadrupolo.
- Agrisado de los parámetros no usados según tipo de componente y modo.
- No se simula nada al cargar datos hasta tocar un parámetro o ajustar.
- Previsualización en vivo de los sextetes en modo distribución antes de ajustar.
- "Inicializar desde mínimos" activa los componentes detectados y escala las profundidades para no pasarse de los datos.
- Clic derecho en la caja de muestra: usarla como calibración tomando vmax e iso actuales.
- Desplazamiento isomérico corregido (δ − iso de calibración) en el cuadro de resultados y el informe.
- Ayuda integrada ampliada (capítulo de acceso a opciones y novedades) en es/en/fr.

### Documentación

- Manual matemático extenso del motor de ajuste en `docs/` (LaTeX + PDF).

## v2.0 — release estable

Versión estable que consolida el desarrollo anterior y sustituye al historial fragmentado de releases 0.x y 1.x.

### Interfaz y flujo de trabajo

- Arquitectura modular con `core/`, `layout/` y `panels/`.
- Interfaz multilingüe español/inglés/francés y ayuda integrada ampliada.
- Layout configurable, tema claro/oscuro y paneles reorganizados.
- Guardado/carga de sesiones JSON, exportación de ajuste y generación de informes Markdown/PDF.
- Empaquetado de release con ZIP, checksums SHA-256, datos de ejemplo y lanzadores.

### Ajuste discreto

- Ajuste de singletes, dobletes y sextetes con pesos Poisson.
- Autoarranques deterministas, bootstrap MC, métricas χ²/AIC/BIC y diagnóstico de residuos.
- Áreas integradas, errores 1σ cuando están disponibles y resumen de correlaciones.
- Presets físicos de restricciones e imposición de relaciones entre parámetros.
- Ajuste opcional de Vmax y folding point.
- Detección automática mejorada de mínimos y propuesta inicial para uno o dos sextetes.

### Distribuciones hiperfinas

- Distribuciones `P(BHF)` y `P(ΔEQ)` con regularización tipo Hesse-Rübartsch.
- Escaneo L-curve, regularización por variación total, GCV/dof efectivo y acondicionamiento del kernel.
- Componentes nítidos simultáneos con la distribución.
- Barras de error 1σ en distribuciones y comparación de modelos.
- Corrección de la conversión de intensidades entre sextetes nítidos de la GUI y el motor de distribución.

### Física y perfiles

- Perfil Lorentziano y Voigt con normalización consistente.
- Tratamiento cuadrupolar de primer orden, Kündig fijo y Kündig polvo.
- Parámetro de textura para intensidades de sextete.
- Menús contextuales para modo de intensidades y tratamiento cuadrupolar desde `β` y `ΔEQ/AEQ`.

### Calibración y web

- Descarga de medidas y calibraciones desde la API web del laboratorio.
- Uso del fichero cargado como calibración local.
- Persistencia de la calibración entre ficheros y sesiones.
- Inclusión de metadatos e incertidumbre de calibración en estado e informes cuando está disponible.

### Limpieza de release

- Ramas antiguas incorporadas en `main` y eliminadas cuando ya no contenían cambios únicos.
- Release notes anteriores sustituidas por `RELEASE_NOTES_v2.0.md`.
