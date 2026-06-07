#!/usr/bin/env python3
"""Genera espectros sintéticos con distribuciones de campo hiperfino y componentes nítidos.
Los archivos resultantes están en formato ADT (512 canales, simétricos).
"""
import sys
from pathlib import Path
import numpy as np

# Asegurar que core y mossbauer_distribution estén en el path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mossbauer_distribution import (
    build_bhf_kernel,
    build_sharp_kernel,
    sextet_absorption,
    doublet_absorption,
    singlet_absorption,
)

# --- Parámetros Globales ---
VMAX = 12.007          # mm/s (estándar Fitbauer)
ISO_REF = -0.1092      # mm/s (corrimiento isomérico de calibración)
N_CHANNELS = 512
BASELINE_COUNTS = 2_000_000.0
RNG = np.random.default_rng(42)

def write_adt(path: Path, raw: np.ndarray) -> None:
    lines = [f"{int(c):>12}" for c in raw]
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))

def generate_raw_counts(v_half, transmission):
    """Crea 512 canales simétricos basados en la transmisión de 256 canales."""
    mu = BASELINE_COUNTS * transmission
    raw = np.zeros(N_CHANNELS, dtype=np.int64)
    for j in range(256):
        left_idx = 255 - j
        right_idx = 256 + j
        raw[left_idx] = RNG.poisson(mu[j])
        raw[right_idx] = RNG.poisson(mu[j])
    return raw

def get_gaussian_weights(centers, mean, sigma, area=1.0):
    """Genera pesos gaussianos normalizados."""
    weights = np.exp(-0.5 * ((centers - mean) / sigma)**2)
    if weights.sum() == 0:
        return np.zeros_like(centers)
    return area * (weights / weights.sum())

def main():
    out_dir = Path("./synthetic_distributions")
    out_dir.mkdir(exist_ok=True)
    
    v_half = np.linspace(-VMAX, VMAX, 256)
    
    # Configuración de los espectros a generar
    # Cada entrada: (nombre, distribution_params, sharp_params)
    # distribution_params: (mean_bhf, sigma_bhf, area, BHF_range)
    # sharp_params: lista de dicts para build_sharp_kernel
    
    cases = [
        {
            "name": "dist_gauss_simple",
            "dist": {"mean": 45.0, "sigma": 2.0, "area": 0.02, "range": (30, 60)},
            "sharp": []
        },
        {
            "name": "dist_bimodal_sharp_sextet",
            "dist": [
                {"mean": 35.0, "sigma": 1.5, "area": 0.01, "range": (20, 50)},
                {"mean": 50.0, "sigma": 1.5, "area": 0.01, "range": (20, 50)},
            ],
            "sharp": [
                {"kind": "Sextete", "bhf": 33.0, "delta": 0.0 + ISO_REF, "quad": 0.0, "depth": 0.01}
            ]
        },
        {
            "name": "dist_broad_sharp_doublet",
            "dist": {"mean": 40.0, "sigma": 8.0, "area": 0.03, "range": (10, 70)},
            "sharp": [
                {"kind": "Doblete", "delta": 0.5 + ISO_REF, "quad": 1.2, "depth": 0.04}
            ]
        },
        {
            "name": "dist_multi_sharp_mix",
            "dist": [
                {"mean": 48.0, "sigma": 1.0, "area": 0.01, "range": (40, 55)},
                {"mean": 32.0, "sigma": 2.0, "area": 0.005, "range": (20, 40)},
            ],
            "sharp": [
                {"kind": "Sextete", "bhf": 51.5, "delta": 0.37 + ISO_REF, "quad": -0.2, "depth": 0.01},
                {"kind": "Singlete", "delta": 0.2 + ISO_REF, "depth": 0.02}
            ]
        }
    ]

    for case in cases:
        # 1. Distribución
        dist_abs = np.zeros_like(v_half)
        if isinstance(case["dist"], dict):
            d = case["dist"]
            centers = np.linspace(d["range"][0], d["range"][1], 100)
            weights = get_gaussian_weights(centers, d["mean"], d["sigma"], d["area"])
            kernel = build_bhf_kernel(v_half, centers, delta=0.0+ISO_REF, quad=0.0, gamma=0.18)
            dist_abs += kernel @ weights
        elif isinstance(case["dist"], list):
            for d in case["dist"]:
                centers = np.linspace(d["range"][0], d["range"][1], 100)
                weights = get_gaussian_weights(centers, d["mean"], d["sigma"], d["area"])
                kernel = build_bhf_kernel(v_half, centers, delta=0.0+ISO_REF, quad=0.0, gamma=0.18)
                dist_abs += kernel @ weights

        # 2. Componentes nítidos
        sharp_abs = np.zeros_like(v_half)
        if case["sharp"]:
            # build_sharp_kernel devuelve (K, centers). K es una matriz donde cada col es un perfil unitario.
            # Necesitamos multiplicar cada col por su 'depth'.
            K, _ = build_sharp_kernel(v_half, case["sharp"], default_delta=0.0+ISO_REF, default_quad=0.0, default_gamma=0.18)
            if K is not None:
                depths = np.array([c.get("depth", 0.0) for c in case["sharp"]])
                sharp_abs += K @ depths

        transmission = 1.0 - dist_abs - sharp_abs
        raw = generate_raw_counts(v_half, transmission)
        
        path = out_dir / f"{case['name']}.adt"
        write_adt(path, raw)
        print(f"Generado: {path.name}")

if __name__ == "__main__":
    main()
