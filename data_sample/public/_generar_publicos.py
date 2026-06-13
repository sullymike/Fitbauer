"""Genera los espectros de referencia en data_sample/public/

Uso:
    python data_sample/public/_generar_publicos.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.physics import sextet_absorption, doublet_absorption

VMAX = 12.007
ISO_REF = -0.1092
N_CHANNELS = 512
BASELINE_COUNTS = 5_000_000.0
RNG = np.random.default_rng(20260613)

def _sextet(d,b,q,g,dep,i1=3,i2=2,i3=1):
    return ("sextet",dict(delta=d+ISO_REF,quad=q,bhf=b,gamma1=g,gamma2=1.,gamma3=1.,
                          depth=dep,int1=float(i1),int2=float(i2),int3=float(i3)))
def _doublet(d,q,g,dep):
    return ("doublet",dict(delta=d+ISO_REF,quad=q,gamma1=g,gamma2=1.,depth=dep,int1=1.,int2=1.))

def _absorption(comps, v):
    t = np.zeros_like(v)
    for k,p in comps:
        if k=="sextet": t+=sextet_absorption(v,p["delta"],p["quad"],p["bhf"],p["gamma1"],p["gamma2"],p["gamma3"],p["depth"],p["int1"],p["int2"],p["int3"])
        else: t+=doublet_absorption(v,p["delta"],p["quad"],p["gamma1"],p["gamma2"],p["depth"],p["int1"],p["int2"])
    return t

def _build(comps):
    n = N_CHANNELS // 2
    v = np.linspace(-VMAX, VMAX, n)
    mu = BASELINE_COUNTS * np.clip(1.0 - _absorption(comps, v), 0.01, 2.0)
    raw = np.zeros(N_CHANNELS, dtype=np.int64)
    for j in range(n):
        raw[255-j] = RNG.poisson(mu[j])
        raw[256+j] = RNG.poisson(mu[j])
    return raw

def _write(path, raw):
    path.write_bytes(("\r\n".join(f"{int(c):>12}" for c in raw)+"\r\n").encode("ascii"))

MINERALS = {
    "goetita_FeOOH":        [_sextet(0.37,38.0,-0.26,0.27,0.014)],
    "ferridrita_2lineas":   [_doublet(0.35,0.72,0.50,0.040)],
    "pirita_FeS2":          [_doublet(0.31,0.61,0.22,0.028)],
    "troilita_FeS":         [_sextet(0.76,30.4,0.31,0.28,0.016)],
    "wustita_FeO":          [_doublet(0.92,0.50,0.28,0.038)],
    "ilmenita_FeTiO3":      [_doublet(1.07,0.70,0.28,0.036)],
    "jarosita_KFe3SO4":     [_sextet(0.37,30.6,-0.34,0.32,0.013)],
    "lepidocrocita_FeOOH":  [_doublet(0.37,0.53,0.27,0.030)],
    "maghemita_Fe2O3":      [_sextet(0.33,50.0,0.00,0.38,0.015)],
    "pirrotita_Fe7S8":      [_sextet(0.70,28.5,0.28,0.35,0.012),_doublet(0.60,0.30,0.32,0.010)],
}

if __name__ == "__main__":
    out = Path(__file__).parent
    for name, comps in MINERALS.items():
        raw = _build(comps)
        _write(out / f"{name}.adt", raw)
        print(f"OK {name}")
