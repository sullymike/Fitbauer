# Fitbauer v5.1.0

*[🇬🇧 Release notes in English](https://github.com/sullymike/Fitbauer/blob/main/RELEASE_NOTES_v5.1.0.md)*

Versión menor sobre la 5.0.0: comodidad de uso en la interfaz,
una corrección de fidelidad al importar trabajos de NORMOS y la puesta en
orden de las licencias de terceros.

---

## Importar `.JOB`: las ligaduras de área, bien reescaladas

NORMOS liga **áreas** (`ARE(2)=f·ARE(1)`); el parámetro de Fitbauer es la
**profundidad** (área = depth·(π/2)·ΣΓ). Con anchuras distintas entre los dos
subespectros, copiar el factor tal cual desescalaba el subespectro ligado —en
un trabajo real, un 14 % fuera de la curva de NORMOS—. El factor y el offset se
reescalan ahora con los denominadores del propio JOB, avisando de que la razón
deriva si el ajuste mueve las anchuras.

Detectado en el análisis masivo de **357 trabajos JOB reales**. Tras la
corrección, Fitbauer reproduce la curva de NORMOS con **mediana 0,022 % del
pico** en 336 de los 337 analizables —el restante es un ajuste donde el propio
NORMOS divergió— y su re-ajuste **iguala o mejora el χ² de NORMOS en 321 de
336**.

## La interfaz, más cómoda

- **Arrastrar y soltar** sobre la ventana: `.ws5`/`.adt`/`.mos` abre el
  espectro, `.json` restaura la sesión y `.JOB` importa el trabajo de NORMOS
  con su espectro.
- **Autoguardado y recuperación.** Cada tres minutos el trabajo en curso se
  vuelca a `recuperacion.json` (escritura atómica); si Fitbauer se cerró sin
  guardar, al arrancar ofrece recuperarlo indicando espectro y hora. No
  sustituye a guardar la sesión: es una red de seguridad para las horas de
  ajuste fino.
- **Aviso al cerrar con trabajo sin guardar** (Guardar / Salir sin guardar /
  Cancelar). Antes la ventana se cerraba en silencio y, desde el autoguardado,
  el cierre limpio se llevaba también el punto de recuperación.
- **Atajos del flujo diario**: Ctrl+M inicializar desde mínimos, Ctrl+Shift+M
  autoajustar, Ctrl+E editar mínimos, Ctrl+F liberar todo, Ctrl+Shift+F fijar
  todo. El ciclo completo se hace ya con teclado.
- **Copiar resultados** (*Archivo ▸ Copiar resultados*, Ctrl+Shift+C): la tabla
  de parámetros con errores, χ², AIC y BIC en texto tabulado que Excel y Origin
  pegan en columnas, solo con los componentes activos.
- **Globo de ayuda en todos los parámetros** —etiqueta, casilla y barra—, con
  aviso de qué controles abren menú contextual, y **«Clic derecho ▸ Más
  información»** lleva de cada parámetro a su capítulo de la ayuda. 38 claves
  nuevas × 8 idiomas.
- **El perfil de línea pasa a ser un desplegable** junto a los de forma de onda
  y absorbente, con σ justo debajo. La calibración oculta lo que no aplica
  (−23 % de altura de panel) y el desplazamiento isomérico vuelve a encabezar
  el panel de componente.
- **El estado vacío enseña cómo empezar**: «Arrastra aquí un espectro (.ws5,
  .adt, .csv…) o pulsa Ctrl+O».

## Tus ajustes, a salvo

- **La suite de tests ya no pisa la configuración del usuario.** Construir una
  ventana en un test bastaba para machacar `~/.config/mossbauer_fe33_gui/`; un
  fixture autouse desvía ahora ese directorio a un temporal.
- **`settings.json` se escribe de forma atómica**, y si existe pero no se puede
  leer se aparta como `settings.json.corrupto` en vez de pisarse.

## Licencias de terceros

El código de Fitbauer sigue siendo **Apache 2.0**, pero al distribuir
ejecutables que empaquetan Qt se asumen las obligaciones de la **LGPLv3** sobre
esa parte. Quedan cubiertas:

- `NOTICE` y `THIRD-PARTY-LICENSES.md` en la raíz, con cada dependencia y su
  licencia, y el texto íntegro de LGPLv3 y GPLv3 en `licenses/`. Los cuatro
  viajan dentro del ZIP y del build de PyInstaller.
- El diálogo **Acerca de** declara el uso de Qt vía PySide6 bajo LGPLv3, en los
  8 idiomas.
- Los README explican cómo **sustituir las bibliotecas de Qt** (§4 de la
  LGPLv3): en la distribución en fuente Qt no se empaqueta —lo instala `pip`—
  y en el build *one-dir* basta con reemplazar los `.so`/`.dll` de
  `_internal/PySide6/`, sin recompilar.

---

Suite completa: **584 tests en verde**.
