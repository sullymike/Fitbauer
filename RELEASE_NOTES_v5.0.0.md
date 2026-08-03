# Fitbauer v5.0.0

Versión mayor. Se ha revisado el **código fuente Fortran completo de NORMOS**
(SITE + DIST) contra `core/`, nivel a nivel, y el resultado son tres cosas:
Fitbauer da los mismos números, lee y escribe sus ficheros, y hace bastante
más.

---

## Paridad con NORMOS, verificada con números

La física se ha contrastado en **dos bancos independientes**.

**Banco sintético** — NORMOS genera el espectro a partir de parámetros
conocidos, Fitbauer lo ajusta, se compara con la verdad: 411 espectros,
~1.150 ajustes, **6.497 comparaciones**.

| Bloque | posición | BHF | anchura |
|---|---|---|---|
| Sexteto/doblete de primer orden | 2·10⁻⁷ mm/s | 4·10⁻⁵ T | 8·10⁻⁷ mm/s |
| Hamiltoniano completo | 6·10⁻⁵ mm/s | 8·10⁻⁴ T | 5·10⁻⁴ mm/s |
| Multisitio y ligaduras (hasta 10 sitios) | 2·10⁻⁴ mm/s | 2·10⁻⁴ T | 2·10⁻⁴ mm/s |

**Banco de trabajos reales** — **564 ajustes** hechos en NORMOS a lo largo de
años, con sus medidas de laboratorio, recargados y reproducidos:

- En **355 de 503** trabajos comparables (**71 %**) Fitbauer iguala o mejora
  el χ² reducido de NORMOS (mediana **2,433** → **2,089**).
- Acuerdo en los parámetros: δ 0,0011 mm/s · ΔEQ 0,0019 · BHF 0,017 T ·
  Γ 0,030 · área 0,0036.
- En 22 casos NORMOS había convergido a algo **no físico** —anchuras por
  debajo de la natural, áreas negativas— que Fitbauer no replica porque tiene
  cotas físicas.

## Interoperabilidad de ficheros `.JOB`

**Archivo ▸ NORMOS (.JOB)**

- **Importar** reconstruye el modelo **y carga el espectro**, que el `.JOB`
  nombra en su cabecera. Funcionan los trabajos de **NORMOS-SITE** (sitios
  discretos) y los de **NORMOS-DIST** (distribuciones), que se detectan solos y
  abren el panel P(BHF)/P(ΔEQ).
- **Exportar** escribe el modelo en formato NORMOS. Comprobado que **NORMOS
  acepta el fichero que produce Fitbauer**, reproduciendo la teoría original
  con diferencia exactamente cero.
- Las conversiones de convenio delicadas se hacen solas, y el importador
  **avisa de todo lo que no ha podido trasladar**.

## Capacidades nuevas de esta versión

- **Fuente polarizada** (`METHOD=4`/`POLAR`), implementada desde primeros
  principios y validada contra el binario al 0,4 % del pico.
- **Polarización de poblaciones** en la relajación Blume–Tjon: reproduce la
  rutina `ISIRLX` de NORMOS con rms < 10⁻¹².
- **Doblado con interpolación cúbica** (B-spline): el sesgo de anchura baja del
  +9,5 % al +2,8 %. Detección de **canales de borde muertos** —en el banco
  real, 42 ajustes mejoraron hasta ×65— y diagnóstico del efecto geométrico.
- **Convenio de posiciones del sexteto seleccionable** (α-Fe o NORMOS), para
  reproducir un BHF suyo exactamente.
- **Asimetría de línea (AKS)**, integral de transmisión con kernel de fuente
  integrado por canal, barras de error absolutas y propagación correcta en
  parámetros ligados.

## Interfaz

- **Modo compacto de parámetros** (*Vista ▸ Parámetros compactos*): cada
  parámetro pasa de dos filas a una. Junto con ocultar los no ajustables, tres
  sextetes apilados caen de 1191 a 531 píxeles, así que vuelven a caber varios
  componentes a la vez. No esconde ningún parámetro.
- Distintivo de versión en la cabecera y portada renovada.
- Ayuda integrada con capítulo nuevo de NORMOS en los **8 idiomas**; manuales
  ES y EN al día (83 y 84 páginas).

## Lo que todavía no hace

Con la misma franqueza: solo ⁵⁷Fe (NORMOS admite además ¹¹⁹Sn, ¹⁹⁷Au, ¹⁵¹Eu y
¹²¹Sb), distribuciones de Czjzek/Le Caër analíticas, campo externo en la
relajación de Ising, espectros de emisión, dos bloques de distribución
solapados, octete como componente propia y preprocesado (agrupar canales, sumar
espectros). Al importar un `.JOB` de distribución, el suavizado `LAMDA` no se
traslada: hay que fijarlo con la L-curve.

El inventario completo está en `validacion/informe/COBERTURA_NORMOS.md` y lo
pendiente en `PENDIENTE_NORMOS.md`.

---

Suite completa: **546 tests en verde**.
