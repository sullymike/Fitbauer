"""Rendimiento de los ajustes de distribución sin cambiar resultados.

- ``solve_bounded_lsq`` (NNLS de Lawson–Hanson) debe dar el mismo óptimo que
  ``lsq_linear`` con las cotas que usan las distribuciones.
- ``core.blas_threads`` fija un hilo de BLAS salvo que el usuario elija otro.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import lsq_linear

from mossbauer_distribution import solve_bounded_lsq

ROOT = Path(__file__).resolve().parent.parent


def _problema(seed: int, m: int = 120, n: int = 30):
    rng = np.random.default_rng(seed)
    A = rng.normal(size=(m, n))
    x_true = np.abs(rng.normal(size=n)) * (rng.random(n) > 0.4)
    b = A @ x_true + rng.normal(0.0, 0.05, m)
    return A, b


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_nnls_da_el_mismo_optimo_que_lsq_linear(seed):
    A, b = _problema(seed)
    lo = np.zeros(A.shape[1]); hi = np.full(A.shape[1], np.inf)
    lo[0] = -np.inf                       # columna libre (pendiente)
    ref = lsq_linear(A, b, bounds=(lo, hi), lsmr_tol="auto")
    sol = solve_bounded_lsq(A, b, lo, hi)
    assert sol.success
    assert np.all(sol.x[1:] >= 0.0)
    cost = lambda x: float(np.sum((A @ x - b) ** 2))  # noqa: E731
    assert cost(sol.x) <= cost(ref.x) * (1 + 1e-9) + 1e-12
    np.testing.assert_allclose(sol.x, ref.x, atol=1e-6)


def test_cotas_distintas_usan_lsq_linear():
    A, b = _problema(3)
    lo = np.full(A.shape[1], 0.1); hi = np.full(A.shape[1], 2.0)
    sol = solve_bounded_lsq(A, b, lo, hi)
    assert np.all(sol.x >= 0.1 - 1e-12) and np.all(sol.x <= 2.0 + 1e-12)
    ref = lsq_linear(A, b, bounds=(lo, hi), lsmr_tol="auto")
    np.testing.assert_allclose(sol.x, ref.x, atol=1e-6)


def test_ajuste_2d_igual_con_y_sin_grados_efectivos():
    """Omitir los grados de libertad efectivos no cambia el ajuste."""
    from mossbauer_distribution import fit_bhf_quad_distribution, build_hyperfine_distribution_kernel
    v = np.linspace(-10, 10, 256)
    K = build_hyperfine_distribution_kernel(v, np.array([30.0]), gamma=0.3)
    y = 1.0 - 0.05 * K[:, 0] / K[:, 0].max()
    kw = dict(gamma=0.3, bmin=20, bmax=40, nbins_bhf=11, qmin=-0.5, qmax=0.5,
              nbins_quad=5, alpha_bhf=1.0, alpha_quad=1.0)
    a = fit_bhf_quad_distribution(v, y, **kw)
    b = fit_bhf_quad_distribution(v, y, compute_effective_dof=False, **kw)
    np.testing.assert_allclose(a.fitted_curve, b.fitted_curve)
    assert a.effective_dof is not None and b.effective_dof is None


def _hilos(env_extra: dict) -> str:
    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")}
    env.update(env_extra)
    out = subprocess.run(
        [sys.executable, "-c",
         "import core.blas_threads, os; print(os.environ['OPENBLAS_NUM_THREADS'])"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_blas_un_hilo_por_defecto_y_respeta_al_usuario():
    assert _hilos({}) == "1"
    assert _hilos({"OPENBLAS_NUM_THREADS": "4"}) == "4"
