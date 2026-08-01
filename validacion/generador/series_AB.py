#!/usr/bin/env python3
"""Bloques A (modelos hiperfinos) y B (intensidades/textura) — definición.

Rejillas del plan §2, adaptadas al inventario real del demo de SITE
(27.01.1994): sin isótopos ≠57Fe, NSUB≤10, HAMILT en &PARAM.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from runner import Case

VA = 4.0    # vmax series paramagnéticas


def _sx(**kw):
    d = {"nline": 6, "iso": 0.0, "qua": 0.0, "bhf": 33.0, "wid": 0.25,
         "dep": 0.05, "d13": 3.0, "d23": 2.0}
    d.update(kw)
    return d


def _db(**kw):
    d = {"nline": 2, "iso": 0.35, "qua": 1.2, "wid": 0.25, "dep": 0.05}
    d.update(kw)
    return d


def _sg(**kw):
    d = {"nline": 1, "iso": 0.0, "wid": 0.25, "dep": 0.05}
    d.update(kw)
    return d


SERIES: dict[str, list[Case]] = {}

# A1a: singletes, barrido delta
SERIES["A1a"] = [
    Case(f"A1a_d{d:+.2f}", [_sg(iso=d)], vmax=VA, nota="singlete barrido delta")
    for d in (-2.0, -1.0, -0.44, -0.09, 0.0, 0.26, 0.5, 1.0, 2.0)]

# A1b: singletes, barrido Gamma (0.19 ≈ 2x ancho natural)
SERIES["A1b"] = [
    Case(f"A1b_g{g:.2f}", [_sg(wid=g)], vmax=VA, nota="singlete barrido Gamma")
    for g in (0.19, 0.22, 0.25, 0.30, 0.40, 0.60, 1.00)]

# A1c: singletes, barrido profundidad (DEP = area = frac·pi·Gamma/2)
import numpy as np
SERIES["A1c"] = [
    Case(f"A1c_p{100*f:g}pc", [_sg(dep=f * np.pi * 0.25 / 2)], vmax=VA,
         nota=f"singlete profundidad {100*f:g}%")
    for f in (0.005, 0.02, 0.05, 0.10, 0.20)]

# A2: dobletes, rejilla delta x DeltaEQ (incluye no resueltos DEQ<Gamma)
SERIES["A2"] = [
    Case(f"A2_d{d:.2f}_q{q:.2f}", [_db(iso=d, qua=q)], vmax=VA,
         nota="doblete rejilla")
    for d in (0.0, 0.37, 0.7, 1.12, 1.3)
    for q in (0.15, 0.30, 0.50, 0.70, 1.00, 1.50, 2.00, 2.65, 3.50)]

# A3a: sextetos 1er orden, barrido Bhf (2 T = colapsado)
SERIES["A3a"] = [
    Case(f"A3a_b{b:g}", [_sx(bhf=b)], nota="sexteto barrido Bhf")
    for b in (2, 5, 10, 15, 20, 26, 33, 40, 45, 49, 51.7, 55)]

# A3b: sextetos, barrido epsilon (QUA) con Bhf=33
SERIES["A3b"] = [
    Case(f"A3b_e{e:+.2f}", [_sx(qua=e)], nota="sexteto barrido QUA")
    for e in (-0.30, -0.20, -0.10, -0.05, 0.05, 0.10, 0.20, 0.30)]

# A3c: sextetos, barrido delta con Bhf=46
SERIES["A3c"] = [
    Case(f"A3c_d{d:.2f}", [_sx(iso=d, bhf=46.0)], nota="sexteto barrido delta")
    for d in (0.0, 0.37, 0.66, 1.0)]

# A4: Hamiltoniano completo axial (eta=0), rejilla R x theta.
# R = DeltaEQ / (separacion lineas 1-6) = DeltaEQ/(10.658*B/33) -> B=DeltaEQ*33/(10.658*R)
_A4 = []
for r, deq in ((0.1, 1.0), (0.5, 2.0), (1.0, 2.0), (2.0, 2.0), (10.0, 2.0)):
    b = round(deq * 33.0 / (10.658 * r), 2)
    for th in (0.0, 15.0, 30.0, 54.7, 75.0, 90.0):
        _A4.append(Case(
            f"A4_R{r:g}_th{th:g}",
            [_sx(qua=deq, bhf=b, the=th)],
            param_extra=["HAMILT=.TRUE.,"],
            fit_kwargs={"quad_treatment": "kundig_fixed",
                        "free_intensities": True},
            nota=f"HC axial R={r} theta={th}"))
SERIES["A4"] = _A4

# A5: Hamiltoniano completo, EFG no axial (eta>0) con R=1.
# Fitbauer NO modela eta/phi (Kundig axial): fallo esperado, a documentar.
SERIES["A5"] = [
    Case(f"A5_eta{eta:g}_th{th:g}_ph{ph:g}",
         [_sx(qua=2.0, bhf=6.19, the=th, eta=eta, phi=ph)],
         param_extra=["HAMILT=.TRUE.,"],
         fit_kwargs={"quad_treatment": "kundig_fixed",
                     "free_intensities": True},
         nota=f"HC eta={eta} theta={th} phi={ph} (eta no soportado)")
    for eta in (0.2, 0.4, 0.6, 0.8, 1.0)
    for th in (0.0, 54.7, 90.0)
    for ph in (0.0, 45.0, 90.0)]

# A6: contraste 1er orden vs Hamiltoniano completo, theta=30, R creciente.
# Par a: SITE 1er orden con QUA_eff = DeltaEQ*(3cos2th-1)/2; par b: HAMILT.
_A6 = []
_c30 = (3 * np.cos(np.deg2rad(30)) ** 2 - 1) / 2
for r in (0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0):
    deq = 0.8 if r <= 0.2 else 1.5
    b = round(deq * 33.0 / (10.658 * r), 2)
    _A6.append(Case(f"A6_R{r:g}_1er",
                    [_sx(qua=round(deq * _c30, 4), bhf=b)],
                    nota=f"contraste R={r} 1er orden (QUA efectivo)"))
    _A6.append(Case(f"A6_R{r:g}_HC",
                    [_sx(qua=deq, bhf=b, the=30.0)],
                    param_extra=["HAMILT=.TRUE.,"],
                    fit_kwargs={"quad_treatment": "kundig_fixed",
                                "free_intensities": True},
                    nota=f"contraste R={r} HC theta=30"))
SERIES["A6"] = _A6

# A7: lineas Lorentzianas libres (NSUB singletes con posiciones arbitrarias).
_A7_CONF = {
    # posiciones dentro del rango delta∈[-2,3] de Fitbauer (los singletes no
    # pueden salir de ahi; ver C3_fuera_de_rango para la evidencia del limite)
    "1linea":  [(-0.5, 0.25, 0.04)],
    "2lineas": [(-1.2, 0.30, 0.03), (1.7, 0.22, 0.05)],
    "3lineas": [(-1.8, 0.25, 0.04), (0.3, 0.40, 0.02), (2.2, 0.25, 0.05)],
    "5lineas": [(-1.9, 0.25, 0.03), (-1.0, 0.30, 0.04), (0.1, 0.20, 0.02),
                (1.1, 0.35, 0.05), (2.6, 0.25, 0.03)],
    # dos parcialmente solapadas (0.9 y 1.25) + 8 lineas > MAX de Fitbauer (6)
    "8lineas": [(-1.9, 0.25, 0.02), (-1.3, 0.30, 0.03), (-0.6, 0.25, 0.03),
                (0.0, 0.20, 0.02), (0.9, 0.30, 0.04), (1.25, 0.25, 0.03),
                (2.0, 0.25, 0.03), (2.7, 0.30, 0.02)],
}
SERIES["A7"] = [
    Case(f"A7_{name}",
         [_sg(iso=p, wid=w, dep=a) for (p, w, a) in lines],
         vmax=5.0, fit_kwargs={"multistart_n": 8},
         nota=f"lineas libres n={len(lines)}"
              + (" (excede MAX_COMPONENTS=6 de Fitbauer)" if len(lines) > 6 else ""))
    for name, lines in _A7_CONF.items()]

# B1: textura: barrido D23 (x=0 B||gamma, x=2 polvo, x=4 B perp gamma)
SERIES["B1"] = [
    Case(f"B1_x{x:g}", [_sx(d23=x)],
         fit_kwargs={"free_intensities": True},
         nota=f"textura D23={x}")
    for x in (0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0)]

# B2: dobletes con asimetria de intensidad (D21 = area linea2/linea1)
SERIES["B2"] = [
    Case(f"B2_r{r:g}", [_db(d21=r)], vmax=VA,
         fit_kwargs={"free_intensities": True},
         nota=f"doblete asimetrico D21={r}")
    for r in (0.6, 0.8, 1.0, 1.25, 1.67)]

# B3: textura + Hamiltoniano completo (2 casos de A5 con D23 no estandar)
SERIES["B3"] = [
    Case("B3_eta0.6_th54.7_x3",
         [_sx(qua=2.0, bhf=6.19, the=54.7, eta=0.6, d23=3.0)],
         param_extra=["HAMILT=.TRUE.,"],
         fit_kwargs={"quad_treatment": "kundig_fixed",
                     "free_intensities": True},
         nota="HC eta=0.6 + textura D23=3"),
    Case("B3_eta0.2_th0_x0.5",
         [_sx(qua=2.0, bhf=6.19, the=0.0, eta=0.2, d23=0.5)],
         param_extra=["HAMILT=.TRUE.,"],
         fit_kwargs={"quad_treatment": "kundig_fixed",
                     "free_intensities": True},
         nota="HC eta=0.2 + textura D23=0.5"),
]

if __name__ == "__main__":
    from runner import run_series_v0
    only = sys.argv[1:] or list(SERIES)
    for name in only:
        run_series_v0(name, SERIES[name])
