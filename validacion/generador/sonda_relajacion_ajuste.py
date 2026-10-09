#!/usr/bin/env python3
"""Valida la relajación de Fitbauer contra las curvas de la sonda de SITE.

En el demo de SITE (27.01.1994) la rama IRELAX coloca la absorción solo en
las posiciones de las líneas 3/4 (±0.84 mm/s a 33 T), así que cada curva es
la suma de las líneas 3 y 4, que intercambian entre los MISMOS dos estados
±B (con +B la 3 está en −a y la 4 en +a; con −B al revés).

Se PREDICE cada curva sin ajustar la tasa ni la polarización:
``ν = OME·10⁶/2`` (OME en MHz, ``OME = 2k``) y ``P = BHF/BH0``. Solo quedan
libres base, profundidad, posición y Γ. Se hace con los dos convenios:

- ``normos``: debe reproducir el binario a ~1e-5 en todos los casos.
- ``blume`` (defecto, balance detallado): igual con P ≈ 0, distinto con P > 0.

Uso:  python validacion/generador/sonda_relajacion_ajuste.py
      (tras sonda_relajacion.py, que genera las curvas)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.physics import relaxation_convention, two_state_exchange_profile  # noqa: E402

BHF = 33.0
OUT = ROOT / "validacion" / "sonda_relajacion"


def predice(v, y, lnu, pol):
    def modelo(p):
        base, depth, a, gamma = p
        l3 = two_state_exchange_profile(v, -a, a, gamma, lnu, pol)
        l4 = two_state_exchange_profile(v, a, -a, gamma, lnu, pol)
        return base - depth * 0.5 * (l3 + l4)
    r = least_squares(lambda p: modelo(p) - y, [1.0, 1.0 - y.min(), 0.84, 0.25],
                      bounds=([0.9, 0, 0.1, 0.01], [1.1, 5, 3, 3]))
    return float(np.sqrt(np.mean(r.fun ** 2)) / (1.0 - y.min())), r.x


def main() -> None:
    d = np.load(OUT / "curvas.npz")
    v = d["v"]
    lineas = ["BH0     OME(MHz)   P     rms/prof normos   rms/prof blume   a(normos)  Γ(normos)"]
    peor_normos = 0.0
    for key in sorted(k for k in d.files if k.startswith("B")):
        bh0, ome = (float(x) for x in key[1:].split("_O"))
        y = d[key] / np.median(d[key])
        lnu = float(np.log10(ome * 1e6 / 2.0))
        pol = BHF / bh0
        with relaxation_convention("normos"):
            rms_n, x_n = predice(v, y, lnu, pol)
        with relaxation_convention("blume"):
            rms_b, _ = predice(v, y, lnu, pol)
        peor_normos = max(peor_normos, rms_n)
        lineas.append(f"{bh0:7g} {ome:8g} {pol:6.3f}   {rms_n:12.1e}   {rms_b:14.1e}"
                      f"   {x_n[2]:9.4f}  {x_n[3]:8.4f}")
    lineas.append(f"\nPeor rms/prof con el convenio NORMOS: {peor_normos:.1e}")
    txt = "\n".join(lineas)
    (OUT / "validacion.txt").write_text(txt + "\n", encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
