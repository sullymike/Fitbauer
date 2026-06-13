# Espectros de referencia — parámetros de literatura

Generados sintéticamente con `_generar_publicos.py` usando los parámetros
hiperfinos publicados para cada mineral. Ruido Poisson con 5 M cuentas de
baseline (ruido ~0.045% relativo, comparable a espectros experimentales bien
promediados). Escala de velocidades: Vmax = 12.007 mm/s, 512 canales crudos
→ 256 plegados, corrimiento isomérico de referencia ISO_REF = -0.109 mm/s.

| Archivo | Componente | δ (mm/s) | ΔEQ o ε (mm/s) | Bhf (T) | Γ (mm/s) | Referencia |
|---|---|---|---|---|---|---|
| goetita_FeOOH | Sextete Fe³⁺ | 0.37 | -0.26 | 38.0 | 0.27 | Murad & Cashion 2004 |
| ferridrita_2lineas | Doblete Fe³⁺ | 0.35 | +0.72 | — | 0.50 | Janney et al. 2000 |
| pirita_FeS2 | Doblete Fe²⁺ | 0.31 | +0.61 | — | 0.22 | Vaughan & Craig 1978 |
| troilita_FeS | Sextete Fe²⁺ | 0.76 | +0.31 | 30.4 | 0.28 | Greenwood & Gibb 1971 |
| wustita_FeO | Doblete Fe²⁺ | 0.92 | +0.50 | — | 0.28 | McCammon & Liu 1984 |
| ilmenita_FeTiO3 | Doblete Fe²⁺ | 1.07 | +0.70 | — | 0.28 | Amthauer et al. 1976 |
| jarosita_KFe3SO4 | Sextete Fe³⁺ | 0.37 | -0.34 | 30.6 | 0.32 | Klingelhoefer et al. 2004 (MER) |
| lepidocrocita_FeOOH | Doblete Fe³⁺ | 0.37 | +0.53 | — | 0.27 | Murad 1979 |
| maghemita_Fe2O3 | Sextete Fe³⁺ | 0.33 | 0.00 | 50.0 | 0.38 | Murad & Schwertmann 1983 |
| pirrotita_Fe7S8 | Sextete Fe²⁺ + Doblete | 0.70/0.60 | +0.28/+0.30 | 28.5/— | 0.35/0.32 | Schwarz & Vaughan 1972 |

Todos los δ están referenciados a α-Fe a temperatura ambiente.

---

## Espectro experimental real

| Archivo | Descripción | Rango v (mm/s) | Puntos | Fuente |
|---|---|---|---|---|
| alphaFe_calibracion_ESRF.dat | α-Fe, espectro de calibración experimental | −5.03 a +6.28 | 512 | SYNCmoss / ESRF (Yaroslavtsev, MIT) |

**Formato**: dos columnas, separadas por tabulador: velocidad (mm/s) y cuentas (crudas ~10 000–17 700).
Cargable con el cargador CSV de Fitbauer (Archivo → Abrir, extensiones .dat/.txt/.csv).

**Advertencias**:
- Rejilla de velocidades **no uniforme** (arrastre sinusoidal, 1 024 canales, se proporciona la mitad descendente).
- La línea más negativa de α-Fe (−5.33 mm/s) está en el borde del rango y aparece truncada;
  las otras 5 líneas son claramente visibles.
- Datos reales de medición experimental en el ESRF (European Synchrotron Radiation Facility).
- Licencia MIT. Repositorio original: https://github.com/sergey-yaroslavtsev/syncmoss
