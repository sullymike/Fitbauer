"""Tests de las mejoras derivadas de la 2ª fase del banco NORMOS (series K/L).

- wide_delta amplía también la cota de ΔEQ (caso K5_dob_q5: SITE admite
  ΔEQ=5 y la cota clásica ±4 degeneraba el ajuste).
- La cota de slope pasa a ±0.02 (caso K2_lin_p60: los fondos lineales BKG(2)
  de NORMOS alcanzan 7.5e-3 mm/s⁻¹).
- El kernel de distribución acepta textura (int2_rel/int3_rel ↔ D13/D23 de
  NORMOS-DIST; serie L6).
"""
import numpy as np

from core.params import GLOBAL_FIT_BOUNDS
from core.session import ModelState


def test_wide_delta_amplia_quad():
    ms = ModelState.defaults(n_components=1)
    ms.n_components = 1
    ms.sextet_enabled[1] = True
    ms.vars["vmax"] = 10.0
    ms.wide_delta = True
    v = np.linspace(-10, 10, 256)
    st = ms.build_fit_state(velocity=v, y_data=np.ones(256),
                            sigma_data=np.full(256, 1e-3), counts=None,
                            norm_factor=1.0)
    lo, hi = st.bounds["s1_quad"]
    assert hi >= 2.0 * (10.0 + 2.0) - 1e-9
    assert lo <= -2.0 * (10.0 + 2.0) + 1e-9
    lo_d, hi_d = st.bounds["s1_delta"]
    assert hi_d >= 12.0 - 1e-9


def test_wide_delta_off_mantiene_cota_clasica():
    ms = ModelState.defaults(n_components=1)
    ms.n_components = 1
    ms.sextet_enabled[1] = True
    v = np.linspace(-10, 10, 256)
    st = ms.build_fit_state(velocity=v, y_data=np.ones(256),
                            sigma_data=np.full(256, 1e-3), counts=None,
                            norm_factor=1.0)
    assert st.bounds["s1_quad"] == (-4.0, 4.0)


def test_cota_slope_ampliada():
    lo, hi = GLOBAL_FIT_BOUNDS["slope"]
    assert hi >= 0.02 and lo <= -0.02


def test_kernel_textura_d23():
    """int2_rel=1.5 ≡ D23=3: el peso de las líneas 2,5 pasa a 3× el de 3,4."""
    from mossbauer_distribution import _rel_weights_gammas
    w, _ = _rel_weights_gammas(0.25, 1.0, 1.0, 1.0, 1.5, 1.0)
    assert np.isclose(w[1] / w[2], 3.0)
    assert np.isclose(w[0] / w[2], 3.0)          # D13 estándar
    w2, _ = _rel_weights_gammas(0.25, 1.0, 1.0, 1.0, 1.0, 1.0)
    assert np.isclose(w2[1] / w2[2], 2.0)        # patrón clásico 3:2:1


def test_kernel_bhf_acepta_textura():
    from mossbauer_distribution import build_hyperfine_distribution_kernel
    v = np.linspace(-10, 10, 256)
    centers = np.array([25.0, 30.0])
    k_std = build_hyperfine_distribution_kernel(v, centers, variable="bhf",
                                                gamma=0.3)
    k_tex = build_hyperfine_distribution_kernel(v, centers, variable="bhf",
                                                gamma=0.3, int2_rel=1.5)
    # la textura solo cambia las líneas 2,5: los kernels deben diferir
    assert not np.allclose(k_std, k_tex)
    # y las líneas exteriores (1,6) quedan intactas
    i_l1 = np.argmin(np.abs(v - (-25.0 / 33.0 * 5.329)))
    assert np.isclose(k_std[i_l1, 0], k_tex[i_l1, 0], rtol=5e-3)
