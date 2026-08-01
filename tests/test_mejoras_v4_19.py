"""Tests de las tres capacidades v4.19 (paridad NORMOS, banco-2 §17-18).

1. Fondo cúbico/cuártico (curv3/curv4) — BKG(4)/BKG(5) de SITE.
2. Cristal único (quad_treatment="hamiltonian_sc", bex/gax).
3. Kernel Hamiltoniano en distribuciones (kernel_treatment="hamiltonian").
"""
import numpy as np
import pytest

from core.hamiltonian import (full_hamiltonian_lines, full_hamiltonian_lines_sc,
                              full_hamiltonian_lines_field,
                              _gauss_legendre_nodes)
from core.params import (CALIBRATION_PARAM_SPECS, GLOBAL_FIT_BOUNDS,
                         QUAD_TREATMENTS, relevant_params)
from core.physics import sextet_absorption, total_model


# ── 1. Fondo v³/v⁴ ───────────────────────────────────────────────────────────

def test_total_model_curv34():
    v = np.linspace(-4, 4, 128)
    base = total_model(v, 1.0, 0.0, [])
    con = total_model(v, 1.0, 0.0, [], curv3=1e-4, curv4=-2e-5)
    esperado = 1e-4 * v ** 3 - 2e-5 * v ** 4
    assert np.allclose(con - base, esperado, atol=1e-15)


def test_curv34_en_specs_y_bounds():
    for k in ("curv3", "curv4"):
        assert k in GLOBAL_FIT_BOUNDS
        assert k in CALIBRATION_PARAM_SPECS
        assert CALIBRATION_PARAM_SPECS[k].default == 0.0


def test_fit_recupera_fondo_cubico():
    """Round trip: espectro sintético con v³ → fit_discrete lo recupera."""
    from core.session import ModelState
    from core.fit_engine import fit_discrete

    v = np.linspace(-4, 4, 256)
    c3_true = 1.2e-4
    y = total_model(v, 1.0, 0.0,
                    [("Singlete", np.array([0.3, 0, 0, 0.25, 1, 1, 0.04, 1, 1, 1]))],
                    curv3=c3_true)
    ms = ModelState.defaults(n_components=1)
    ms.n_components = 1
    ms.sextet_enabled[1] = True
    ms.component_kind[1] = "Singlete"
    ms.multistart_n = 0
    ms.vars.update({"s1_delta": 0.25, "s1_gamma1": 0.3, "s1_depth": 0.03,
                    "vmax": 4.0})
    ms.fixed["curv3"] = False
    st = ms.build_fit_state(velocity=v, y_data=y,
                            sigma_data=np.full(v.size, 1e-4), counts=None,
                            norm_factor=1.0)
    res = fit_discrete(st)
    assert abs(res.values["curv3"] - c3_true) < 2e-6
    assert abs(res.values["s1_delta"] - 0.3) < 1e-3


# ── 2. Cristal único ─────────────────────────────────────────────────────────

def test_sc_patron_axial():
    """B∥z_EFG: haz ∥ B → 3:0:1; haz ⊥ B → 3:4:1 (patrones clásicos M1)."""
    _, i_par, _ = full_hamiltonian_lines_sc(33.0, 0.0, 0.0, beam_theta=0.0)
    nz = np.sort(i_par[i_par > 1e-9])
    assert np.allclose(nz, [1.5, 1.5, 4.5, 4.5])          # 3:0:1
    _, i_perp, _ = full_hamiltonian_lines_sc(33.0, 0.0, 0.0,
                                             beam_theta=np.pi / 2)
    nz = np.sort(i_perp[i_perp > 1e-9])
    assert np.allclose(nz, [0.75, 0.75, 2.25, 2.25, 3.0, 3.0])   # 3:4:1


def test_sc_promedio_isotropo_recupera_polvo():
    p0, i0, _ = full_hamiltonian_lines(20.0, 0.1, 1.5, eta=0.6, theta=0.5,
                                       phi=0.3)
    x, w = _gauss_legendre_nodes(24)
    acc = np.zeros(8)
    nphi = 16
    for xx, ww in zip(x, w):
        th = float(np.arccos(np.clip(xx, -1, 1)))
        for k in range(nphi):
            _, ii, _ = full_hamiltonian_lines_sc(
                20.0, 0.1, 1.5, eta=0.6, theta=0.5, phi=0.3,
                beam_theta=th, beam_phi=2 * np.pi * k / nphi)
            acc += 0.5 * ww * ii / nphi
    assert np.max(np.abs(acc - i0)) < 1e-10


def test_sc_en_params_y_tratamientos():
    assert "hamiltonian_sc" in QUAD_TREATMENTS
    rel = relevant_params("Sextete", "free", "hamiltonian_sc")
    assert {"bex", "gax", "eta", "phi", "beta"} <= rel
    assert "int1" not in rel and "int2" not in rel
    rel1 = relevant_params("Sextete", "free", "1st_order")
    assert "bex" not in rel1


def test_sc_absorption_area_conservada():
    """La regla de suma se mantiene: el área no depende de la dirección del haz."""
    v = np.linspace(-11, 11, 2048)
    areas = []
    for bt, bp in ((0.0, 0.0), (0.9, 0.4), (np.pi / 2, np.pi / 2)):
        a = sextet_absorption(v, 0.0, 2.0, 20.0, 0.25, 1.0, 1.0, 1.0,
                              3.0, 2.0, 1.0, treatment="hamiltonian_sc",
                              beta=0.5, eta=0.5, beam_theta=bt, beam_phi=bp)
        areas.append(np.trapezoid(a, v))
    assert np.allclose(areas, areas[0], rtol=1e-3)


# ── 3. Kernel Hamiltoniano en distribuciones ─────────────────────────────────

def test_kernel_hc_identidad_quad_cero():
    from mossbauer_distribution import sextet_absorption as dist_sextet
    v = np.linspace(-10, 10, 256)
    a = dist_sextet(v, delta=0.1, quad=0.0, bhf=30, gamma=0.3)
    b = dist_sextet(v, delta=0.1, quad=0.0, bhf=30, gamma=0.3,
                    treatment="hamiltonian")
    assert np.max(np.abs(a - b)) < 1e-12


def test_kernel_hc_textura_ligada_al_campo():
    """La textura D23 sobrevive al promedio de polvo (marco del campo)."""
    from mossbauer_distribution import sextet_absorption as dist_sextet
    v = np.linspace(-10, 10, 512)
    ratios = []
    for i2r in (1.0, 1.5):
        a = dist_sextet(v, delta=0.0, quad=0.0, bhf=25, gamma=0.3,
                        int2_rel=i2r, treatment="hamiltonian")
        h2 = a[np.argmin(np.abs(v - (-25 / 33 * 3.084)))]
        h3 = a[np.argmin(np.abs(v - (-25 / 33 * 0.839)))]
        ratios.append(h2 / h3)
    assert abs(ratios[0] - 2.0) < 0.1
    assert abs(ratios[1] - 3.0) < 0.15


def test_field_frame_isotropo_coincide_con_marco_efg():
    """Con pesos isótropos (3:2:1→W_q iguales) ambos marcos son equivalentes."""
    pos_f, int_f, _ = full_hamiltonian_lines_field(25.0, 0.0, 0.8,
                                                   theta=0.7, int1=3, int2=2)
    # marco del EFG con B inclinado el mismo ángulo: mismas posiciones
    pos_e, int_e, _ = full_hamiltonian_lines(25.0, 0.0, 0.8, theta=0.7,
                                             int1=3.0, int2=2.0)
    assert np.allclose(np.sort(pos_f), np.sort(pos_e), atol=1e-10)
    assert np.allclose(np.sort(int_f), np.sort(int_e), atol=1e-9)


def test_kernel_hc_round_trip_momentos():
    """Sintético octete-exacto (QUP=1) → el kernel HC recupera los momentos."""
    from mossbauer_distribution import (build_hyperfine_distribution_kernel,
                                        fit_hyperfine_distribution)
    v = np.linspace(-10, 10, 256)
    centers = np.arange(10.0, 41.0, 1.0)
    K = build_hyperfine_distribution_kernel(
        v, centers, variable="bhf", gamma=0.3, quad=1.0,
        treatment="hamiltonian", n_orient=12)
    P = np.exp(-0.5 * ((centers - 25.0) / 3.0) ** 2)
    P /= P.sum()
    y = 1.0 - 0.05 * (K @ P) / np.max(K @ P)
    fit = fit_hyperfine_distribution(
        v, y, variable="bhf", gamma=0.3, quad=1.0, pmin=10, pmax=40,
        nbins=31, alpha=1e-3, kernel_treatment="hamiltonian")
    w = np.maximum(fit.weights, 0.0)
    w = w / w.sum()
    avg = float(np.sum(w * fit.bhf_centers))
    std = float(np.sqrt(np.sum(w * (fit.bhf_centers - avg) ** 2)))
    assert abs(avg - 25.0) < 0.15
    assert abs(std - 3.0) < 0.35
