# Fitbauer v4.0.2

Versión de mantenimiento sobre **Fitbauer v4.0.1**.

## 🔧 Corrección de calibración (α-Fe)

- Se elimina la constante interna **32.95 T** (no es un valor publicado) y toda la calibración se unifica al campo hiperfino **publicado de α-Fe a temperatura ambiente: 33.0 T (330 kOe)**.
- Afectados: la fórmula de posiciones del sextete (`fe57_sextet_positions`), `LINE_POS_33T` (núcleo y módulo de distribución) y la **autocalibración de velocidad/campo de la interfaz Tk** (la Qt ya usaba `BHF_DEFAULT_T = 33.0`).
- **Efecto:** un espectro de α-Fe ideal autocalibra ahora exactamente a **33.0 T** (antes ≈ 32.95 T). El BHF informado se desplaza ≈ **0,15 % (~0,05 T)** y queda consistente con NORMOS.

## 🔁 Compatibilidad

- Las sesiones e informes anteriores se cargan sin cambios; solo varía levemente el BHF calculado por calibración de α-Fe.
- Verifica el ZIP con `sha256sums.txt`.
