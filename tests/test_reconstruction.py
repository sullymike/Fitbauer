import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.fit_engine import Component
from core.reconstruction import (
    component_area_percentages,
    component_absorption_area,
    dense_velocity_grid,
    reconstruct_discrete_model,
    reconstruct_distribution_curves,
    sharp_component_params,
)


def test_sharp_component_params_uses_distribution_mapping_and_weight():
    comp = {
        "kind": "Sextete",
        "delta": 0.1,
        "quad": 0.2,
        "bhf": 33.0,
        "gamma": 0.36,
        "gamma2_rel": 1.1,
        "gamma3_rel": 1.2,
        "depth": 0.3,
        "int1": 1.0,
        "int2_rel": 0.7,
        "int3_rel": 0.5,
    }

    params = sharp_component_params(comp, weight=0.42)

    assert params.shape == (10,)
    assert params[0] == 0.1
    assert params[3] == 0.36
    assert params[6] == 0.42
    # Traducción engine→core: las profundidades de línea del vector canónico
    # ([int3·int1, int3·int2, int3]) deben reproducir el patrón del engine
    # ([i1, (2/3)·i1·r2, (1/3)·i1·r3]); antes int2_rel/int3_rel se copiaban tal
    # cual y el patrón reconstruido no era el ajustado.
    int1_c, int2_c, int3_c = params[7], params[8], params[9]
    engine_lines = np.array([1.0, (2.0 / 3.0) * 1.0 * 0.7, (1.0 / 3.0) * 1.0 * 0.5])
    core_lines = np.array([int3_c * int1_c, int3_c * int2_c, int3_c])
    assert np.allclose(core_lines, engine_lines)


def test_reconstruct_distribution_curves_returns_envelope_and_sharp_curve():
    v = np.linspace(-2.0, 2.0, 41)
    fitted = np.ones_like(v)
    comp = {
        "kind": "Sextete",
        "delta": 0.0,
        "quad": 0.0,
        "bhf": 33.0,
        "gamma": 0.36,
        "gamma2_rel": 1.0,
        "gamma3_rel": 1.0,
        "depth": 0.2,
        "int1": 1.0,
        "int2_rel": 1.0,
        "int3_rel": 1.0,
    }

    curves = reconstruct_distribution_curves(
        v,
        fitted,
        baseline=1.0,
        slope=0.0,
        sharp_components=[comp],
        sharp_indices=[2],
        sharp_weights=np.array([0.2]),
        distribution_kind="P(BHF)",
    )

    assert len(curves) == 2
    assert curves[0].idx == 0
    assert curves[0].kind == "P(BHF)"
    assert curves[1].idx == 2
    assert curves[1].kind == "Sextete"
    assert curves[0].y.shape == v.shape
    assert curves[1].y.shape == v.shape


def test_dense_velocity_grid_and_discrete_reconstruction():
    v = np.linspace(-3.0, 3.0, 64)
    comps = [
        Component(idx=1, enabled=True, kind="Singlete"),
        Component(idx=2, enabled=True, kind="Singlete"),
    ]
    values = {
        "baseline": 1.0,
        "slope": 0.0,
        "s1_delta": -0.5,
        "s1_quad": 0.0,
        "s1_bhf": 0.0,
        "s1_gamma1": 0.4,
        "s1_gamma2": 1.0,
        "s1_gamma3": 1.0,
        "s1_depth": 0.1,
        "s1_int1": 1.0,
        "s1_int2": 1.0,
        "s1_int3": 1.0,
        "s2_delta": 0.5,
        "s2_quad": 0.0,
        "s2_bhf": 0.0,
        "s2_gamma1": 0.4,
        "s2_gamma2": 1.0,
        "s2_gamma3": 1.0,
        "s2_depth": 0.1,
        "s2_int1": 1.0,
        "s2_int2": 1.0,
        "s2_int3": 1.0,
    }
    reconstruction = reconstruct_discrete_model(
        v,
        np.ones_like(v),
        values,
        comps,
        [],
    )

    assert dense_velocity_grid(v).size >= 1200
    assert reconstruction.model.shape == v.shape
    assert reconstruction.residual.shape == v.shape
    assert reconstruction.model_dense.shape == reconstruction.model_v.shape
    assert [curve.idx for curve in reconstruction.components] == [1, 2]


def test_reconstruct_discrete_model_respects_line_profile_and_sigma():
    """La previsualización refleja el perfil Voigt y σ, y restaura el estado global."""
    from core import physics as ph

    v = np.linspace(-6.0, 6.0, 400)
    comps = [Component(idx=0, enabled=True, kind="Singlete")]
    values = {
        "baseline": 1.0, "slope": 0.0,
        "s0_delta": 0.0, "s0_quad": 0.0, "s0_bhf": 0.0,
        "s0_gamma1": 0.30, "s0_gamma2": 1.0, "s0_gamma3": 1.0,
        "s0_depth": 0.5, "s0_int1": 1.0, "s0_int2": 1.0, "s0_int3": 1.0,
    }
    before = (ph.LINE_PROFILE_KIND, ph.VOIGT_SIGMA)
    m_small = reconstruct_discrete_model(
        v, np.ones_like(v), values, comps, [],
        line_profile_kind="Voigt", voigt_sigma=0.05).model
    m_large = reconstruct_discrete_model(
        v, np.ones_like(v), values, comps, [],
        line_profile_kind="Voigt", voigt_sigma=0.45).model

    # Cambiar σ cambia el modelo de forma apreciable.
    assert float(np.max(np.abs(m_small - m_large))) > 1e-3
    # El estado global se restaura tras la reconstrucción (sin contaminación).
    assert (ph.LINE_PROFILE_KIND, ph.VOIGT_SIGMA) == before


def test_component_area_percentages_are_normalized():
    class Snapshot:
        idx = 1
        kind = "Singlete"

        def value(self, name, default=0.0):
            values = {
                "delta": 0.0,
                "quad": 0.0,
                "bhf": 0.0,
                "gamma1": 0.4,
                "gamma2": 1.0,
                "gamma3": 1.0,
                "depth": 0.1,
                "int1": 1.0,
                "int2": 1.0,
                "int3": 1.0,
            }
            return values.get(name, default)

    v = np.linspace(-2.0, 2.0, 101)
    params = np.array([Snapshot().value(name) for name in (
        "delta", "quad", "bhf", "gamma1", "gamma2", "gamma3",
        "depth", "int1", "int2", "int3",
    )])
    assert component_absorption_area("Singlete", params, v) > 0
    active, areas, pct = component_area_percentages([Snapshot()], v)
    assert active == [1]
    assert areas[0] > 0
    assert pct[0] == 100.0
