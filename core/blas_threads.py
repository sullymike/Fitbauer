"""BLAS/LAPACK con un solo hilo, salvo que el usuario fije otra cosa.

Hay que importarlo ANTES que numpy/scipy: OpenBLAS lee estas variables al
cargarse y después no las vuelve a mirar.

Por defecto OpenBLAS reparte cada operación entre todos los núcleos, y con las
matrices de Fitbauer (cientos de filas, decenas a un millar de columnas) el
coste de coordinar los hilos supera con mucho al del cálculo: una QR de
304×52 del ajuste de P(BHF) tardaba 0.18 s con 14 hilos y 0.002 s con uno, y el
ajuste de distribución por defecto pasaba de 30 s a 1.3 s (medido 2026-10-10
en un equipo de 14 núcleos con otra carga). Con un hilo no se pierde nada
apreciable ni en la malla 2D, la mayor del programa.

``setdefault``: quien exporte OPENBLAS_NUM_THREADS (u OMP/MKL) manda.
"""
from __future__ import annotations

import os

for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
