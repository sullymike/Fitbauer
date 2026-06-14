# Base de datos de parámetros Mössbauer de referencia

Parámetros hiperfinos de referencia (δ, ΔEQ, B_hf) para fases de hierro,
compilados de la literatura. Pensado como base para un futuro **sugeridor de
fases** en Fitbauer: tras ajustar, comparar los parámetros obtenidos contra
estos valores tabulados para proponer fases compatibles.

## Ficheros

- `mossbauer_reference.json` — registros estructurados (un objeto por sitio/fase).
- `mossbauer_reference.tsv` — misma información en tabla (velocidad/tabulador).

## Campos

| Campo | Descripción |
|---|---|
| `sample` | Nombre de la fase/mineral |
| `class` | Clase mineralógica (sulfuros, óxidos, filosilicatos…) |
| `type` | Código de origen del dato (S/B/E/U según la fuente) |
| `oxidation_state` | Estado de oxidación del Fe (2, 3, 2.5, 0…) |
| `T_K` | Temperatura de medida (K) |
| `IS_mm_s`, `IS_err` | Desplazamiento isomérico δ y su error (mm/s) |
| `QS_mm_s`, `QS_err` | Desdoblamiento cuadrupolar ΔEQ y su error (mm/s) |
| `Bhf_T`, `Bhf_err` | Campo hiperfino B_hf y su error (T); vacío = paramagnético |
| `site`, `site_total` | Índice de sitio y nº total de sitios de esa fase |
| `model` | Modelo de ajuste de la fuente (VBF, Lor, Unkn…) |
| `reference`, `reference_url` | Cita bibliográfica y enlace |

> **Convención IS.** Los desplazamientos isoméricos están referidos a α-Fe a
> temperatura ambiente, la convención estándar (la misma que usa Fitbauer).

## Procedencia y alcance

- **Fuente:** tabla pública de referencia de [MossTool](http://mosstool.com/database.html),
  que recopila valores publicados en revistas. Cada registro conserva su cita y enlace.
- **Alcance de esta extracción:** cubre **todas las fases minerales y todas las
  referencias** de la tabla original, con entradas representativas por fase. La
  tabla original contiene además muchas **réplicas** de medida (p. ej. decenas de
  filas de lepidocrocita, goethita o vivianita del mismo estudio); aquí se han
  conservado entradas representativas, no todas las réplicas. Para regenerar o
  ampliar el dataset, ver `parse_moss.py` (parser determinista del HTML).

## Licencia / uso

Los **valores numéricos** son hechos científicos extraídos de la literatura
publicada; cada entrada cita su fuente original. Antes de redistribuir o publicar
basándose en estos datos, consultar y citar las referencias primarias listadas en
cada registro. Esta tabla es una ayuda de identificación, **no** una fuente
primaria.
