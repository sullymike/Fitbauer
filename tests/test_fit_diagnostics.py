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


def test_validacion_solo_componentes_activas_y_nombre_legible():
    """Un valor fuera de rango en una componente desactivada (o por encima del
    número elegido) no bloquea el ajuste; en una activa, el aviso usa el
    nombre legible."""
    from core.fit_engine import Component
    from core.validation import validate_fit_state
    v, y, sigma = _load_alpha_fe()
    st = _alpha_fe_state(v, y, sigma)
    st.values["s3_delta"] = 9.0
    st.bounds["s3_delta"] = (-2.0, 3.0)
    assert validate_fit_state(st) == []
    st.components = list(st.components) + [Component(idx=3, enabled=False)]
    assert validate_fit_state(st) == []
    st.components[-1] = Component(idx=3, enabled=True, kind="Doblete")
    issues = validate_fit_state(st, label=lambda k: "δ · comp. 3" if k == "s3_delta" else k)
    assert [i.key for i in issues] == ["s3_delta"] and "δ · comp. 3" in issues[0].message
    # Un parámetro que el tipo no usa (BHF en un doblete) tampoco cuenta.
    st.values["s3_bhf"] = 99.0
    st.bounds["s3_bhf"] = (0.0, 60.0)
    assert [i.key for i in validate_fit_state(st)] == ["s3_delta"]


def test_diagnostico_de_distribucion():
    """Borde de la malla, paso frente a Γ, gaussianas sobrantes, nítidos
    despreciables y globales en su cota."""
    from types import SimpleNamespace
    import numpy as np
    from core.fit_diagnostics import diagnose_distribution, edge_ratio
    x = np.linspace(0.5, 59.5, 60)
    p = np.exp(-0.5 * ((x - 30) / 4) ** 2)
    assert edge_ratio(p) < 0.01
    apilada = p.copy(); apilada[-1] = 0.8
    assert edge_ratio(apilada) == pytest.approx(0.8 / p.max())
    res = SimpleNamespace(
        success=True, probability=apilada, bhf_centers=x, shape="VBF",
        vbf_components=((1.0, 30.0, 4.0), (0.01, 31.0, 4.0)), vbf_sigma_bounds=(0.1, 4.0),
        area_split=(("P(BHF)", 0, 0.99, 99.5), ("Comp. 2", 2, 0.005, 0.5)))
    resumen = {"goodness": {"red_chi2": 1.0}, "variable": "bhf",
               "globals": [{"key": "dist_gamma", "label": "Γ", "value": 0.1,
                            "free": True, "sigma": 0.01}]}
    checks = {c.key: c for c in diagnose_distribution(
        res, resumen, outer=[("Γ", 0.1, 0.1, 1.0)], budget_exhausted=True)}
    assert checks["convergence"].status == "warn"
    assert checks["edge"].status == "warn"
    assert checks["mesh"].status == "warn"          # 1 T → 0.16 mm/s > Γ = 0.1
    comp = checks["components"]
    assert comp.status == "warn" and "2" in comp.value
    assert checks["sharp"].status == "warn"
    assert checks["bounds"].status == "warn" and "Γ" in checks["bounds"].value
    assert checks["errors"].status == "ok"


def test_limites_de_la_ventana_son_las_cotas_del_ajuste(tmp_path, monkeypatch):
    """Lo cambiado en Vista › Límites de parámetros vale también para el
    ajuste y su aviso (antes solo cambiaba la casilla: δ = −3 con el límite
    en −5 seguía dando «fuera de [−2, 3]»)."""
    import json
    import numpy as np
    from core import param_overrides
    from core.session import ModelState
    from core.validation import validate_fit_state
    fich = tmp_path / "param_limits.json"
    monkeypatch.setattr(param_overrides, "PARAM_LIMITS_PATH", fich)
    assert param_overrides.component_fit_bound_overrides() == {}
    # Profundidad sin tocar: su cota de ajuste (1) es más amplia que la casilla.
    fich.write_text(json.dumps({"component": {
        "delta": {"lo": -5.0, "hi": 3.0}, "depth": {"lo": 0.0, "hi": 0.07}}}))
    gen = param_overrides.component_fit_bound_overrides()
    assert gen == {"delta": (-5.0, None)}
    ms = ModelState.defaults(n_components=1)
    ms.sextet_enabled[1] = True
    ms.vars["s1_delta"] = -3.0
    v = np.linspace(-10, 10, 64)
    st = ms.build_fit_state(velocity=v, y_data=np.ones_like(v), sigma_data=None,
                            counts=None, norm_factor=None)
    assert st.bounds["s1_delta"] == (-2.0, 3.0)
    assert [i.key for i in validate_fit_state(st)] == ["s1_delta"]
    ms.general_bounds = gen
    st = ms.build_fit_state(velocity=v, y_data=np.ones_like(v), sigma_data=None,
                            counts=None, norm_factor=None)
    assert st.bounds["s1_delta"] == (-5.0, 3.0)
    assert st.bounds["s1_depth"] == (0.0, 1.0)
    assert validate_fit_state(st) == []


def test_aviso_de_regularizacion_casi_nula():
    """Histograma con k_eff ≈ nº de parámetros: la regularización no actúa."""
    from types import SimpleNamespace
    import numpy as np
    from core.fit_diagnostics import check_regularization
    x = np.linspace(5, 55, 80)
    base = dict(shape="Histograma", reg_mode="tikhonov", bhf_centers=x,
                sharp_weights=None, alpha=10 ** -1.5)
    sin = check_regularization(SimpleNamespace(effective_dof=81.5, **base))
    assert sin.status == "warn" and "81.5" in sin.value and "82" in sin.value
    con = check_regularization(SimpleNamespace(effective_dof=40.0, **base))
    assert con.status == "ok"
    # Formas paramétricas y MaxEnt: no aplica.
    assert check_regularization(SimpleNamespace(effective_dof=5.0, **{**base, "shape": "VBF"})) is None
    assert check_regularization(SimpleNamespace(effective_dof=80.0, **{**base, "reg_mode": "maxent"})) is None


def test_vmax_negativo_es_valido_y_sus_limites_acotan_el_ajuste(tmp_path, monkeypatch):
    """Vmax < 0 solo invierte el eje: la validación mira |Vmax|. Y lo cambiado
    en Vista › Límites de parámetros › Calibración acota también el ajuste."""
    import json
    from types import SimpleNamespace
    import numpy as np
    import core.param_overrides as po
    from core.validation import validate_fit_state
    from core.session import ModelState
    st = SimpleNamespace(velocity=np.linspace(-5, 5, 10), y_data=np.ones(10), sigma_data=None,
                         values={"vmax": -5.0}, bounds={"vmax": (1.0, 15.0)}, components=[])
    assert validate_fit_state(st) == []
    st.values = {"vmax": -0.5}
    assert [i.key for i in validate_fit_state(st)] == ["vmax"]
    # Límites de la casilla −20…20 → |Vmax| hasta 20 en el ajuste.
    f = tmp_path / "param_limits.json"
    f.write_text(json.dumps({"calibration": {"vmax": {"lo": -20.0, "hi": 20.0},
                                             "baseline": {"hi": 1.5}}}))
    monkeypatch.setattr(po, "PARAM_LIMITS_PATH", f)
    g = po.global_fit_bound_overrides()
    assert g == {"vmax": (None, 20.0), "baseline": (None, 1.5)}
    ms = ModelState.defaults()
    ms.general_bounds = g
    fs = ms.build_fit_state(velocity=np.linspace(-5, 5, 10), y_data=np.ones(10),
                            sigma_data=None, counts=None, norm_factor=1.0)
    assert fs.bounds["vmax"] == (1.0, 20.0) and fs.bounds["baseline"] == (0.7, 1.5)
