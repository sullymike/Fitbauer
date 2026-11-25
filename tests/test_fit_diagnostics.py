"""Diagnóstico del ajuste (core.fit_diagnostics) y estrategia local con paso máximo."""
from __future__ import annotations

from dataclasses import replace

import pytest

from core.fit_diagnostics import (check_chi2, component_swaps, diagnose_discrete,
                                  verdict)
from core.fit_engine import fit_discrete
from tests.test_fit_engine import _alpha_fe_state, _load_alpha_fe


@pytest.mark.parametrize("red,status", [(0.5, "warn"), (1.0, "ok"), (2.0, "warn"),
                                        (4.0, "fail")])
def test_chi2_avisa_de_alto_y_de_bajo(red, status):
    assert check_chi2({"red_chi2": red}).status == status


def test_veredicto_es_el_peor_estado():
    ok = check_chi2({"red_chi2": 1.0})
    alto = check_chi2({"red_chi2": 4.0})
    assert verdict([ok]) == "ok"
    assert verdict([ok, check_chi2({"red_chi2": 2.0})]) == "warn"
    assert verdict([ok, alto]) == "fail"


def test_intercambio_de_componentes_detectado():
    inicio = {"s1_bhf": 49.0, "s1_delta": 0.28, "s2_bhf": 46.0, "s2_delta": 0.66}
    cruzado = {"s1_bhf": 46.1, "s1_delta": 0.66, "s2_bhf": 49.1, "s2_delta": 0.28}
    tipos = {1: "Sextete", 2: "Sextete"}
    assert component_swaps(inicio, cruzado, tipos) == [(1, 2)]
    assert component_swaps(inicio, inicio, tipos) == []
    # Tipos distintos no se comparan.
    assert component_swaps(inicio, cruzado, {1: "Sextete", 2: "Doblete"}) == []


def test_estrategia_local_un_solo_arranque_y_paso_maximo():
    v, y, sigma = _load_alpha_fe()
    base = _alpha_fe_state(v, y, sigma)
    base.values["s1_bhf"] = 31.0
    base.values["s1_delta"] = -0.25
    explora = fit_discrete(base)
    local = fit_discrete(replace(base, fit_strategy="local"))
    pasos = fit_discrete(replace(base, fit_strategy="local", max_step_frac=0.01))
    assert local.n_starts == 1 and local.best_start["label"] == "local"
    assert len(explora.starts) >= 2
    # Los tres llegan al mismo mínimo (α-Fe, un solo sitio).
    for r in (local, pasos):
        assert r.values["s1_bhf"] == pytest.approx(explora.values["s1_bhf"], abs=0.05)
        assert r.stats["chi2"] == pytest.approx(explora.stats["chi2"], rel=1e-3)
    checks = {c.key: c for c in diagnose_discrete(explora)}
    assert checks["convergence"].status == "ok"
    assert checks["start"].status in ("ok", "warn")
