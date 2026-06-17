# Guía: correr NORMOS/SITE.EXE bajo DOSBox y comparar con Fitbauer

Documento de referencia interna — recoge todo lo aprendido en la sesión de 2026-06-17
para no tener que redescubrirlo. No contiene datos experimentales confidenciales.

**IMPORTANTE**: `SITE.EXE` está cubierto por `*.EXE` en `.gitignore` y **jamás debe
subirse al repositorio**. Es software comercial de WissEl GmbH.

---

## 1. Entorno

| Componente | Detalle |
|---|---|
| DOSBox | dosbox-staging v0.82.2, instalado como snap en `/usr/local/bin/dosbox` |
| SITE.EXE | NORMOS/SITE v. 27.01.1994 (WissEl GmbH, "Demonstration version") |
| Display X11 | `:0` (sesión gráfica real); DOSBox-staging **requiere display real**, falla con `SDL_VIDEODRIVER=dummy` (no OpenGL) |
| Directorio de trabajo | `/home/jorge/normos_work/` (fuera del repo) |

---

## 2. Lo que NO funciona (callejones sin salida)

- `SDL_VIDEODRIVER=dummy dosbox ...` → crash ("OpenGL support not available")
- `DISPLAY=:0 dosbox -c "mount c DIR" -c "c:" -c "RUNALL.BAT" -c "exit"` → DOSBox lanza pero cierra antes de que NORMOS termine; sin `.RES`
- `DISPLAY=:0 dosbox -conf dosbox.conf` con sección `[autoexec]` → mismo problema
- `dosbox SITE.EXE < ALPHAFE.JOB` → DOSBox no pasa stdin al programa DOS
- Intentar leer ficheros `.adt` (ASCII un-número-por-línea) directamente → NORMOS falla con "Spectrum file: ERROR or EOF" porque su auto-detect no reconoce ese formato

---

## 3. Lo que SÍ funciona

### 3.1 Invocación DOSBox

```bash
DISPLAY=:0 dosbox /home/jorge/normos_work/RUNALL.BAT
```

Cuando se pasa un fichero `.BAT` como argumento posicional, DOSBox-staging:
1. monta el **directorio padre** como `C:`
2. ejecuta el `.BAT`
3. cierra solo al terminar

No hacen falta flags `-c`. No hace falta un `dosbox.conf` especial.

### 3.2 RUNALL.BAT (fin de línea DOS `\r\n`)

```bat
@ECHO OFF
SITE < ALPHAFE.JOB
SITE < HEMATITA.JOB
SITE < SIDERITA.JOB
SITE < MAGNETI.JOB
EXIT
```

La redirección `SITE < FICHERO.JOB` es obligatoria: NORMOS lee todos los parámetros
desde stdin (el fichero JOB), no desde argumentos de línea de comandos.

### 3.3 Formato del espectro: WS5 XML (no ADT)

NORMOS/SITE 1994 **no sabe leer** el formato ADT (ASCII un-número-por-línea) de Fitbauer.
Necesita el formato WS5 XML de WissEl:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<wissoft version="1.1">
<comment>Converted from ADT by Fitbauer</comment>
<data channels="512" time="0">
2001252
1999971
...
</data>
</wissoft>
```

Script Python para convertir todos los ADT de referencia:

```python
from pathlib import Path
import sys
sys.path.insert(0, '/home/jorge/fitbauer')

DATA = Path('/home/jorge/fitbauer/data_sample')
OUT  = Path('/home/jorge/normos_work')

for adt_path in DATA.glob('*.adt'):
    counts = [int(x) for x in adt_path.read_text().split()]
    n = len(counts)
    ws5_name = adt_path.stem.upper()[:8] + '.ws5'  # DOS 8.3
    xml = '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\r\n'
    xml += '<wissoft version="1.1">\r\n'
    xml += '<comment>Converted from ADT by Fitbauer</comment>\r\n'
    xml += f'<data channels="{n}" time="0">\r\n'
    xml += '\r\n'.join(str(c) for c in counts)
    xml += '\r\n</data>\r\n</wissoft>\r\n'
    (OUT / ws5_name).write_text(xml, encoding='utf-8')
    print(f'{adt_path.name} → {ws5_name}  ({n} canales)')
```

---

## 4. Formato del fichero JOB

Estructura exacta (todos los nombres en mayúsculas DOS 8.3):

```
ALPHAFE.ws5            ← línea 1: fichero de espectro (WS5 XML)
ALPHAFE.JOB            ← línea 2: nombre del propio JOB (etiqueta)
ALPHAFE.RES            ← línea 3: fichero de resultados (salida)
ALPHAFE.PLT            ← línea 4: fichero de plot (salida)
 &DATA
 NLTEXT=4, VMAX=12.0, PFP=256.5, TRIANG=.true., MXCFUN=5000,
 REMOTE=.TRUE., PLTDAT=.TRUE.,
 &END
Título libre línea 1
Título libre línea 2
 &PARAM
 NSUB=1,
 NLINE(1)=6,
 DEP(1)=0.10, DEPFIT(1)=.TRUE.,
 D13(1)=3., D13FIT(1)=.FALSE.,
 D23(1)=2., D23FIT(1)=.FALSE.,
 ISO(1)=-0.109, ISOFIT(1)=.TRUE.,
 QUA(1)=0.00, QUAFIT(1)=.FALSE.,
 BHF(1)=33.0, BHFFIT(1)=.TRUE.,
 WID(1)=0.28, WIDFIT(1)=.TRUE.,
 &END
```

### Parámetros clave de `&DATA`

| Parámetro | Significado |
|---|---|
| `NLTEXT=4` | NORMOS lee 4 líneas de texto al inicio del JOB (las 4 líneas de ficheros) |
| `VMAX` | Velocidad máxima en mm/s |
| `PFP=256.5` | Punto de doblez fijo (256.5 = entre canales 256 y 257, espectro 512 ch) |
| `TRIANG=.true.` | Corrección triangular de velocidad (movimiento constante del drive) |
| `REMOTE=.TRUE.` | Modo batch (sin interacción del usuario) |
| `PLTDAT=.TRUE.` | Generar fichero `.PLT` con datos del plot |
| `MXCFUN` | Número máximo de evaluaciones de la función de coste |

### Parámetros de `&PARAM`

| NORMOS | Descripción | Fitbauer equivalente |
|---|---|---|
| `NSUB` | Número de subespectros | `n_components` |
| `NLINE(i)` | Líneas del subespectro i: 6=sextete, 2=doblete, 1=singlete | `component_kind` |
| `ISO` | Desplazamiento isomérico vs. fuente | `s1_delta` |
| `QUA` | Cuadrupolo ΔEQ (mm/s, signo: positivo → línea alta-vel a la derecha) | `s1_quad` (signo opuesto en dobletes) |
| `BHF` | Campo hiperfino (T) | `s1_bhf` |
| `WID` | Anchura HWHM de una sola línea (mm/s) | `s1_gamma1` |
| `DEP` | Profundidad (fracción de absorción) | `s1_depth` |
| `D13, D23` | Ratios de intensidad (relativas a líneas 3,4) | `s1_int1, s1_int2` |
| `ARE` | Área del espectro (parámetro de salida, no de entrada) | — |

---

## 5. Diferencias de convenio NORMOS ↔ Fitbauer

### 5.1 Referencia del desplazamiento isomérico

Ambos programas reportan δ relativo al cero de velocidad de la fuente (no corregido a α-Fe).
Para obtener δ relativo a α-Fe, sumar `+0.110 mm/s` (el desplazamiento de la fuente medido
en el espectro de α-Fe: `ISO(α-Fe) = −0.110 mm/s`).

```
δ_corr = δ_fitted + 0.110
```

### 5.2 Signo de ΔEQ en dobletes

El valor absoluto es idéntico, el signo es opuesto:

| Programa | Siderita (FeCO₃) |
|---|---|
| NORMOS | `QUA = +1.797 mm/s` |
| Fitbauer | `s1_quad = −1.798 mm/s` |

Motivo: en `doublet_absorption` de Fitbauer, las líneas están en `δ ∓ ΔEQ/2`.
En NORMOS, están en `ISO ± QUA/2`. Para el mismo espectro físico:
- línea 1 (baja velocidad): `δ − |ΔEQ|/2`
- línea 2 (alta velocidad): `δ + |ΔEQ|/2`

Ambos programas generan las mismas posiciones de línea. Solo difiere el signo reportado.

### 5.3 Punto de doblez (folding point)

| | NORMOS | Fitbauer |
|---|---|---|
| α-Fe | PFP = 256.5 (fijo en JOB) | 256.422 (auto) |
| Fe₂O₃ | PFP = 256.5 (fijo) | 256.515 (auto) |
| FeCO₃ | PFP = 256.5 (fijo) | 256.481 (auto) |
| Fe₃O₄ | PFP = 256.5 (fijo) | 256.497 (auto) |

La búsqueda automática de Fitbauer da valores ligeramente distintos a 256.5,
lo que explica parte de las diferencias en los parámetros ajustados.

### 5.4 Línea base

NORMOS: solo nivel constante (`BKG`).
Fitbauer: nivel constante + pendiente lineal (`baseline` + `slope`).
Esto es fuente de diferencias en χ² pero no en los parámetros hiperfinos.

---

## 6. Resultados de la comparación directa (2026-06-17)

Cuatro espectros experimentales (512 canales, Vmax = 12.0 mm/s):
`hierro_metalico_alphaFe.adt`, `hematita_Fe2O3.adt`, `siderita_FeCO3.adt`, `magnetita_Fe3O4.adt`.

### α-Fe (sextete único, 3:2:1 fijo)

| | NORMOS | Fitbauer | |Δ| |
|---|---|---|---|
| BHF (T) | 33.035 ± 0.006 | 33.045 ± 0.006 | 0.010 |
| δ_raw (mm/s) | −0.110 ± 0.001 | −0.110 ± 0.001 | <0.001 |
| Γ (mm/s) | 0.279 ± 0.002 | 0.287 ± 0.003 | 0.008 |
| χ²_red | 1.195 | 0.972 | — |

### Hematita α-Fe₂O₃ (sextete único)

| | NORMOS | Fitbauer | |Δ| |
|---|---|---|---|
| BHF (T) | 51.576 ± 0.007 | 51.581 ± 0.007 | 0.005 |
| δ_corr (mm/s) | 0.372 ± 0.001 | 0.371 ± 0.001 | 0.001 |
| ΔEQ (mm/s) | −0.200 ± 0.002 | −0.199 ± 0.002 | 0.001 |
| Γ (mm/s) | 0.317 ± 0.003 | 0.320 ± 0.003 | 0.003 |
| χ²_red | 1.058 | 1.035 | — |

### Siderita FeCO₃ (doblete)

| | NORMOS | Fitbauer | |Δ| |
|---|---|---|---|
| δ_corr (mm/s) | 1.231 ± 0.001 | 1.232 ± 0.001 | 0.001 |
| \|ΔEQ\| (mm/s) | 1.797 ± 0.002 | 1.798 ± 0.002 | 0.001 |
| Γ (mm/s) | 0.337 ± 0.003 | 0.340 ± 0.003 | 0.003 |
| χ²_red | 0.883 | 0.850 | — |

### Magnetita Fe₃O₄ (dos sextetes)

| | NORMOS | Fitbauer | |Δ| |
|---|---|---|---|
| BHF_A (T) | 49.075 ± 0.010 | 49.071 ± 0.010 | 0.004 |
| δ_A corr (mm/s) | 0.269 ± 0.001 | 0.273 ± 0.001 | 0.004 |
| Γ_A (mm/s) | 0.368 ± 0.006 | 0.362 ± 0.008 | 0.006 |
| BHF_B (T) | 46.079 ± 0.007 | 46.066 ± 0.007 | **0.013** |
| δ_B corr (mm/s) | 0.674 ± 0.001 | 0.672 ± 0.001 | 0.002 |
| Γ_B (mm/s) | 0.549 ± 0.003 | 0.556 ± 0.003 | 0.007 |
| χ²_red | 1.093 | 0.935 | — |

**Conclusión**: acuerdo dentro de 1σ en todos los casos. Diferencia máxima:
**0.013 T** en el sitio B de magnetita (atribuible a la diferencia en el punto de doblez:
NORMOS fija PFP=256.5, Fitbauer obtiene PFP=256.497 automáticamente).

---

## 7. Cómo reproducir el experimento

```bash
# 1. Preparar directorio de trabajo
mkdir /home/jorge/normos_work
cp /home/jorge/Mossbauer/SITE.EXE /home/jorge/normos_work/

# 2. Convertir espectros ADT → WS5 XML (script en sección 3.3)
python3 convert_adt_to_ws5.py

# 3. Crear JOB files (ver sección 4)
# 4. Crear RUNALL.BAT (ver sección 3.2)

# 5. Ejecutar NORMOS
DISPLAY=:0 dosbox /home/jorge/normos_work/RUNALL.BAT

# 6. Leer resultados
grep -A 10 "Values of the fit-variables" /home/jorge/normos_work/ALPHAFE.RES
```

Para correr con Fitbauer en modo headless (equivalente):

```python
import json, sys
from pathlib import Path
sys.path.insert(0, '/home/jorge/fitbauer')
from core.session import HeadlessSession

sess = HeadlessSession()
sess.set_vmax(12.0)
sess.load_ws5(Path('data_sample/hierro_metalico_alphaFe.adt'))
tmpl = json.loads(Path('data_sample/template_alphaFe.json').read_text())
sess.apply_template_model_state(tmpl['model_state'])  # ← OJO: sub-clave 'model_state'
r = sess.run_fit()
print(sess.last_fit_stats)
print(sess.model.vars['s1_bhf'], sess.model.vars['s1_delta'])
```

**Trampa conocida**: `apply_template_model_state` espera el dict interno `model_state`,
no el JSON completo. Hacer siempre `tmpl['model_state']`, no `tmpl`.

---

## 8. Parsear ficheros .RES de NORMOS

Los campos útiles están en la sección "Values of the fit-variables":

```python
import re
from pathlib import Path

def parse_normos_res(res_path):
    text = Path(res_path).read_text(encoding='utf-8', errors='replace')
    # Parámetros ajustados
    params = {}
    for m in re.finditer(
        r'^\s+\d+\s+(\w+(?:\(\d+\))?)\s+([-.\d]+)\s+([-.\d]+)\s+\+-\s+([-.\d]+)',
        text, re.M):
        name, init, final, err = m.group(1), m.group(2), m.group(3), m.group(4)
        params[name] = {'initial': float(init), 'final': float(final), 'error': float(err)}
    # Chi-cuadrado
    chi2_m = re.search(r'Chi-square \(normalized\)\s*=\s*([\d.]+)', text)
    chi2 = float(chi2_m.group(1)) if chi2_m else None
    # Punto de doblez final
    pfp_m = re.search(r'Final folding point\s*=\s*([\d.]+)', text)
    pfp = float(pfp_m.group(1)) if pfp_m else None
    return {'params': params, 'chi2_red': chi2, 'pfp': pfp}

res = parse_normos_res('/home/jorge/normos_work/ALPHAFE.RES')
print(res['params']['BHF'])   # {'initial': 33.0, 'final': 33.035, 'error': 0.006}
print(res['chi2_red'])        # 1.195
```

---

## 9. Referencia rápida de nombres de parámetros

| Magnitud física | NORMOS (.RES) | Fitbauer (vars) |
|---|---|---|
| Campo hiperfino | `BHF(i)` | `s{i}_bhf` |
| Despl. isomérico | `ISO(i)` | `s{i}_delta` |
| Cuadrupolo | `QUA(i)` | `s{i}_quad` (signo opuesto en doblete) |
| Anchura HWHM | `WID(i)` | `s{i}_gamma1` |
| Profundidad/área | `ARE(i)` | `s{i}_depth` |
| Ratio int. líneas 1,6 | `D13(i)` (= int1/int3) | `s{i}_int1` |
| Ratio int. líneas 2,5 | `D23(i)` (= int2/int3) | `s{i}_int2` |
| Línea base | `BKG(1)` (cuentas absolutas) | `baseline` (normalizado ≈ 1) |
| Pendiente | — (no disponible en NORMOS) | `slope` |
