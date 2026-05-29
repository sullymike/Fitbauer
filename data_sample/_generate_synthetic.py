"""Genera espectros sintéticos de compuestos de hierro comunes en formato ADT.

Los ficheros resultantes son de 512 canales sin doblar (estilo Normos/WS5 ADT),
perfectamente simétricos respecto al centro 256.5, de modo que la GUI los dobla
a 256 puntos y reconstruye la velocidad linspace(-vmax, vmax, 256).

La escala de velocidad usa vmax = 12.007 mm/s, el valor calibrado presente en
data_sample/calibration_session.json. El corrimiento isomérico de la
calibración es iso_ref = -0.1092 mm/s (muestra FC210422). Para que el
corrimiento corregido (delta_medido - iso_ref) reproduzca el valor de
literatura frente a alpha-Fe, las líneas se sitúan en delta = delta_lit + iso_ref.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.physics import sextet_absorption, doublet_absorption, singlet_absorption  # noqa: E402

VMAX = 12.007          # mm/s, velocidad calibrada existente
ISO_REF = -0.1092      # mm/s, corrimiento isomérico de la calibración (FC210422)
N_CHANNELS = 512
BASELINE_COUNTS = 2_000_000.0   # cuentas altas → ruido de Poisson bajo
RNG = np.random.default_rng(20260529)


def sextet(delta_lit, bhf, quad, gamma1, depth):
    """Parámetros de un sextete con delta en la escala de la calibración."""
    return ("sextet", dict(delta=delta_lit + ISO_REF, quad=quad, bhf=bhf,
                           gamma1=gamma1, gamma2=1.0, gamma3=1.0,
                           depth=depth, int1=3.0, int2=2.0, int3=1.0))


def doublet(delta_lit, deq, gamma1, depth):
    return ("doublet", dict(delta=delta_lit + ISO_REF, quad=deq,
                            gamma1=gamma1, gamma2=1.0, depth=depth,
                            int1=1.0, int2=1.0))


def singlet(delta_lit, gamma1, depth):
    return ("singlet", dict(delta=delta_lit + ISO_REF, gamma1=gamma1,
                            depth=depth, int1=1.0))


def absorption_on_grid(components, v):
    total = np.zeros_like(v)
    for kind, p in components:
        if kind == "sextet":
            total += sextet_absorption(
                v, p["delta"], p["quad"], p["bhf"],
                p["gamma1"], p["gamma2"], p["gamma3"],
                p["depth"], p["int1"], p["int2"], p["int3"],
            )
        elif kind == "singlet":
            total += singlet_absorption(
                v, p["delta"], p["gamma1"], p["depth"], p["int1"],
            )
        else:
            total += doublet_absorption(
                v, p["delta"], p["quad"], p["gamma1"], p["gamma2"],
                p["depth"], p["int1"], p["int2"],
            )
    return total


def build_raw_counts(components, slope=0.0):
    """Construye 512 canales crudos simétricos respecto al centro 256.5.

    El punto j (0..255) del espectro doblado corresponde a velocity[j] de
    linspace(-vmax, vmax, 256). Los canales 1-based (256-j) y (257+j) son ese
    par simétrico; se muestrean con ruido de Poisson independiente.
    """
    n_half = N_CHANNELS // 2
    v = np.linspace(-VMAX, VMAX, n_half)
    transmission = 1.0 + slope * v - absorption_on_grid(components, v)
    mu = BASELINE_COUNTS * transmission

    raw = np.zeros(N_CHANNELS, dtype=np.int64)
    for j in range(n_half):
        left_idx = 255 - j      # canal 1-based 256-j
        right_idx = 256 + j     # canal 1-based 257+j
        raw[left_idx] = RNG.poisson(mu[j])
        raw[right_idx] = RNG.poisson(mu[j])
    return raw


def write_adt(path: Path, raw: np.ndarray) -> None:
    lines = [f"{int(c):>12}" for c in raw]
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))


COMPOUNDS = {
    # ── Compuestos de referencia (parámetros próximos a la literatura) ────────
    # Hematita alpha-Fe2O3 (RT): sextete único, delta~0.37, BHF~51.5, 2eps~-0.20
    "hematita_Fe2O3": [sextet(0.37, 51.5, -0.20, 0.16, 0.014)],
    # Magnetita Fe3O4 (RT): sitio A tetraédrico (Fe3+) + sitio B octaédrico (Fe2.5+)
    "magnetita_Fe3O4": [
        sextet(0.27, 49.0, 0.0, 0.18, 0.012),
        sextet(0.67, 46.0, 0.0, 0.28, 0.020),
    ],
    # Hierro metálico alpha-Fe: sextete del calibrante, delta=0, BHF=33
    "hierro_metalico_alphaFe": [sextet(0.00, 33.0, 0.0, 0.14, 0.015)],
    # Siderita FeCO3: doblete paramagnético Fe2+, delta~1.23, DeltaEQ~1.80
    "siderita_FeCO3": [doublet(1.23, 1.80, 0.17, 0.045)],

    # ── Espectros sintéticos de ejemplo (parámetros arbitrarios) ──────────────
    # Singlete paramagnético estrecho.
    "sintetico_singlete": [singlet(0.30, 0.16, 0.040)],
    # Doblete simétrico de desdoblamiento moderado.
    "sintetico_doblete": [doublet(0.45, 0.85, 0.16, 0.045)],
    # Doblete + singlete (dos entornos paramagnéticos).
    "sintetico_doblete_singlete": [
        doublet(0.95, 2.10, 0.18, 0.038),
        singlet(0.20, 0.17, 0.025),
    ],
    # Sextete de líneas anchas (campo intermedio, ensanchamiento tipo relajación).
    "sintetico_sexteto_ancho": [sextet(0.40, 42.0, 0.10, 0.45, 0.018)],
    # Dos sextetes solapados de campos distintos.
    "sintetico_dos_sextetes": [
        sextet(0.10, 50.0, 0.00, 0.16, 0.013),
        sextet(0.35, 38.0, -0.15, 0.22, 0.015),
    ],
    # Fase mixta: un sextete magnético + un doblete paramagnético.
    "sintetico_sexteto_doblete": [
        sextet(0.20, 47.0, 0.0, 0.18, 0.014),
        doublet(0.55, 1.20, 0.18, 0.022),
    ],
}


def main():
    out_dir = Path(__file__).resolve().parent
    for name, comps in COMPOUNDS.items():
        raw = build_raw_counts(comps)
        path = out_dir / f"{name}.adt"
        write_adt(path, raw)
        print(f"{path.name}: {raw.size} canales, min={raw.min()}, max={raw.max()}")


if __name__ == "__main__":
    main()
