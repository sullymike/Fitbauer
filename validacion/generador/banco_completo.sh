#!/usr/bin/env bash
# Regenera el banco de validación NORMOS → Fitbauer completo, en orden.
#
#   NORMOS genera cada espectro (SITE/DIST en DOSBox) → Fitbauer lo ajusta →
#   validacion/resumen.csv → análisis, veredicto y figuras.
#
# Requisitos (ver validacion/informe/INFORME.md §12):
#   - dosbox-staging (el DOSBox clásico 0.74 se corta al leer el espectro) y
#     una sesión gráfica real: DOSBox abre y cierra ventanas mientras corre.
#   - SITE.EXE y DIST.EXE de NORMOS (comerciales, nunca al repo):
#       NORMOS_SITE_EXE, NORMOS_DIST_EXE (por defecto ~/normos_work/SITE.EXE y
#       validacion/DIST.EXE).
#   - El snap de dosbox-staging no ve /tmp: todo trabaja bajo validacion/.
#
# Uso:  validacion/generador/banco_completo.sh [--limpio]
#   --limpio  empieza con un resumen.csv vacío (solo la cabecera).
set -euo pipefail

GEN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$GEN/../.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
export DOSBOX="${DOSBOX:-dosbox-staging}"
export DISPLAY="${DISPLAY:-:0}"

if [[ "${1:-}" == "--limpio" ]]; then
    head -1 "$ROOT/validacion/resumen.csv" > "$ROOT/validacion/resumen.csv.nuevo"
    mv "$ROOT/validacion/resumen.csv.nuevo" "$ROOT/validacion/resumen.csv"
fi

paso() {
    echo
    echo "════ $(date +%H:%M:%S)  $*"
    (cd "$ROOT" && "$PY" "$GEN/$1" "${@:2}")
}

# Generación + ajuste, en el orden del informe (§12) más las series posteriores.
paso serie_S0_convenciones.py
paso series_AB.py
paso series_CG.py
paso fix_E1_E4_refits.py
paso series_HI.py
paso serie_J.py
paso series_KL.py
paso serie_L.py
paso series_M.py
paso series_N.py
paso serie_V.py
paso series_ext.py
# Relajación de Ising (IRELAX + BH0) contra el modelo de dos estados.
paso sonda_relajacion.py
paso sonda_relajacion_ajuste.py
# Reajustes con las extensiones de modelo (v4.18/v4.19) sobre lo ya generado.
paso valida_mejoras.py
paso valida_v4_19.py

# Análisis y figuras.
paso analisis.py
paso veredicto_datos.py
paso figuras.py
paso figuras_KL.py

echo
echo "════ $(date +%H:%M:%S)  banco completo"
