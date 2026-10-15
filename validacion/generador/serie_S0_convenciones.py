#!/usr/bin/env python3
"""Paso 0.6: mini-serie de convenciones de signo (4 espectros, v0).

Doblete δ>0; sexteto ε>0; sexteto ε<0; singlete δ<0. Resuelve los convenios
de signo QUA↔quad y la escala BHF antes de lanzar el banco completo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from runner import Case, run_series_v0

CASES = [
    Case("S0_doblete_d+0.35_q+1.20",
         [{"nline": 2, "iso": 0.35, "qua": 1.20, "wid": 0.25, "dep": 0.05}],
         nota="doblete con delta>0 y QUA>0"),
    Case("S0_sexteto_e+0.20_b33",
         [{"nline": 6, "iso": 0.0, "qua": 0.20, "bhf": 33.0,
           "wid": 0.25, "dep": 0.05, "d13": 3.0, "d23": 2.0}],
         nota="sexteto con QUA=+0.20"),
    Case("S0_sexteto_e-0.20_b51.7",
         [{"nline": 6, "iso": 0.26, "qua": -0.20, "bhf": 51.7,
           "wid": 0.25, "dep": 0.05, "d13": 3.0, "d23": 2.0}],
         vmax=12.0, nota="sexteto tipo hematita con QUA=-0.20"),
    Case("S0_singlete_d-0.44",
         [{"nline": 1, "iso": -0.44, "wid": 0.25, "dep": 0.05}],
         vmax=4.0, nota="singlete con delta<0"),
]

if __name__ == "__main__":
    run_series_v0("S0", CASES)
