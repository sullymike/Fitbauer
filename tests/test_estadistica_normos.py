"""Nivel 7 de la revisión del fuente de NORMOS: estadística del ajuste.

Comprobado equivalente: los pesos (``RRTY = 1/√Y`` sobre las cuentas dobladas,
``normospr.for:1422``) y la forma de las ligaduras
(``PV(I) = FACTOR(I)·PV(NDEX(I)) + CONST(I)``, ``sitecalf.for:713``).

Lo que NO estaba: el error de los parámetros LIGADOS. NORMOS lo reporta pero
mal — ``siteauxl.for:539`` hace ``PE(K)=ABS(CONST(K))*PE(L)``, usando el
OFFSET donde toca el FACTOR, así que una ligadura multiplicativa pura
(``CONST=0``) sale con error cero. Fitbauer no lo reportaba en absoluto.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.fit_engine import _propagate_constraint_errors


def test_propaga_por_el_factor():
    errors = {"a": 0.004}
    _propagate_constraint_errors(
        errors, [{"target": "b", "source": "a", "factor": 2.5, "offset": 0.0}])
    assert errors["b"] == pytest.approx(0.010)


def test_el_offset_no_aporta_incertidumbre():
    """El fallo exacto de NORMOS: con factor 1 y offset grande, σ NO cambia."""
    errors = {"a": 0.004}
    _propagate_constraint_errors(
        errors, [{"target": "b", "source": "a", "factor": 1.0, "offset": 5.0}])
    assert errors["b"] == pytest.approx(0.004)


def test_ligadura_multiplicativa_pura_no_da_error_cero():
    """Es el caso donde NORMOS da 0 (CONST=0) y donde más se usa la ligadura."""
    errors = {"a": 0.004}
    _propagate_constraint_errors(
        errors, [{"target": "b", "source": "a", "factor": 3.0, "offset": 0.0}])
    assert errors["b"] == pytest.approx(0.012)
    assert errors["b"] > 0.0


def test_factor_negativo_da_sigma_positiva():
    errors = {"a": 0.004}
    _propagate_constraint_errors(
        errors, [{"target": "b", "source": "a", "factor": -2.0}])
    assert errors["b"] == pytest.approx(0.008)


def test_cadena_de_ligaduras():
    errors = {"a": 0.001}
    cons = [{"target": "c", "source": "b", "factor": 3.0},
            {"target": "b", "source": "a", "factor": 2.0}]
    _propagate_constraint_errors(errors, cons)
    assert errors["b"] == pytest.approx(0.002)
    assert errors["c"] == pytest.approx(0.006)


def test_no_pisa_un_error_ya_calculado():
    """Si el destino salió de la covarianza, manda ese."""
    errors = {"a": 0.004, "b": 0.5}
    _propagate_constraint_errors(
        errors, [{"target": "b", "source": "a", "factor": 2.0}])
    assert errors["b"] == pytest.approx(0.5)


def test_tolera_constraints_malformadas():
    errors = {"a": 0.004}
    _propagate_constraint_errors(errors, [{"target": "b"}, {"source": "a"},
                                          {"target": "c", "source": "z"},
                                          {"target": "d", "source": "a",
                                           "factor": "x"}])
    assert errors == {"a": 0.004}


def test_sin_constraints_no_hace_nada():
    errors = {"a": 0.004}
    _propagate_constraint_errors(errors, None)
    _propagate_constraint_errors(errors, [])
    assert errors == {"a": 0.004}


def test_ajuste_completo_reporta_el_ligado():
    """Extremo a extremo: antes el parámetro ligado salía con error None."""
    from core.fit_engine import Component, FitState, fit_discrete
    from core.physics import sextet_absorption

    v = np.linspace(-10.0, 10.0, 256)
    y = 1.0 - sextet_absorption(v, 0.1, 0.0, 33.0, 0.28, 1.0, 1.0,
                                0.05, 3.0, 2.0, 1.0)
    y = y + np.random.default_rng(3).normal(0.0, 3e-4, v.size)
    state = FitState(
        velocity=v, y_data=y, sigma_data=np.full(v.size, 3e-4),
        values={"baseline": 1.0, "slope": 0.0,
                "s1_delta": 0.1, "s1_quad": 0.0, "s1_bhf": 33.0,
                "s1_gamma1": 0.28, "s1_gamma2": 1.0, "s1_gamma3": 1.0,
                "s1_depth": 0.05, "s1_int1": 3.0, "s1_int2": 2.0,
                "s1_int3": 1.0},
        fixed={"slope": True, "s1_quad": True, "s1_gamma2": True,
               "s1_gamma3": True, "s1_int1": True, "s1_int3": True},
        bounds={}, components=[Component(idx=1, enabled=True, kind="Sextete")],
        constraints=[{"target": "s1_int2", "source": "s1_bhf",
                      "factor": 0.05, "offset": 0.0}],
        multistart_n=0)
    res = fit_discrete(state)
    assert "s1_bhf" in res.errors
    assert res.errors.get("s1_int2") == pytest.approx(
        0.05 * res.errors["s1_bhf"], rel=1e-9)


# ── Convenio de las barras de error ──────────────────────────────────────────

def _estado_con_ruido(factor_ruido: float, absolute: bool = True):
    """Sexteto con ruido `factor_ruido`× mayor que la σ declarada."""
    from core.fit_engine import Component, FitState
    from core.physics import sextet_absorption

    v = np.linspace(-10.0, 10.0, 256)
    sigma = 3e-4
    y = 1.0 - sextet_absorption(v, 0.1, 0.0, 33.0, 0.28, 1.0, 1.0,
                                0.05, 3.0, 2.0, 1.0)
    y = y + np.random.default_rng(11).normal(0.0, sigma * factor_ruido, v.size)
    return FitState(
        velocity=v, y_data=y, sigma_data=np.full(v.size, sigma),
        values={"baseline": 1.0, "slope": 0.0, "s1_delta": 0.1, "s1_quad": 0.0,
                "s1_bhf": 33.0, "s1_gamma1": 0.28, "s1_gamma2": 1.0,
                "s1_gamma3": 1.0, "s1_depth": 0.05, "s1_int1": 3.0,
                "s1_int2": 2.0, "s1_int3": 1.0},
        fixed={"slope": True, "s1_quad": True, "s1_gamma2": True,
               "s1_gamma3": True, "s1_int1": True, "s1_int2": True,
               "s1_int3": True},
        bounds={}, components=[Component(idx=1, enabled=True, kind="Sextete")],
        multistart_n=0, absolute_sigma=absolute)


def test_sigma_absoluta_no_depende_del_chi2():
    """Convenio de NORMOS: σ sale solo de la estadística de conteo.

    Con ruido 3× mayor que el declarado el χ²red sube ~9, pero la barra de
    error NO se mueve: refleja lo que las cuentas permiten conocer, no lo bien
    que el modelo describe los datos.
    """
    from core.fit_engine import fit_discrete

    r1 = fit_discrete(_estado_con_ruido(1.0))
    r3 = fit_discrete(_estado_con_ruido(3.0))
    assert r3.stats["red_chi2"] > 4.0 * r1.stats["red_chi2"]
    assert r3.errors["s1_bhf"] == pytest.approx(r1.errors["s1_bhf"], rel=0.05)


def test_sigma_relativa_si_reescala():
    """Con absolute_sigma=False vuelve el convenio de scipy (absolute_sigma=False)."""
    from core.fit_engine import fit_discrete

    r_abs = fit_discrete(_estado_con_ruido(3.0, absolute=True))
    r_rel = fit_discrete(_estado_con_ruido(3.0, absolute=False))
    escala = np.sqrt(r_rel.stats["red_chi2"])
    assert r_rel.errors["s1_bhf"] == pytest.approx(
        escala * r_abs.errors["s1_bhf"], rel=0.02)


def test_poisson_sin_norm_factor_se_considera_relativa():
    """Ahí la σ del residual es √m: correcta salvo un factor global."""
    from core.fit_engine import _sigma_es_absoluta

    st = _estado_con_ruido(1.0)
    st.likelihood = "poisson"
    st.norm_factor = None
    assert _sigma_es_absoluta(st) is False
    st.norm_factor = 1e6
    assert _sigma_es_absoluta(st) is True


def test_sin_sigma_data_se_considera_relativa():
    from core.fit_engine import _sigma_es_absoluta

    st = _estado_con_ruido(1.0)
    st.sigma_data = None
    assert _sigma_es_absoluta(st) is False
