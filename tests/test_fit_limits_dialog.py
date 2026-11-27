"""Cota general que muestran las ventanas de cotas de ajuste."""
from core.params import COMPONENT_FIT_BOUNDS
from gui import fit_limits_dialog as fld


def test_cota_general_con_un_solo_extremo_cambiado(monkeypatch):
    """Límites de parámetros cambia solo un extremo: el otro (None) se toma
    del código. Antes lanzaba TypeError al abrir «Cotas de ajuste…»."""
    import core.param_overrides as po
    name = next(iter(COMPONENT_FIT_BOUNDS))
    lo, hi = COMPONENT_FIT_BOUNDS[name]
    monkeypatch.setattr(po, "component_fit_bound_overrides",
                        lambda: {name: (None, float(hi) + 1.0)})
    assert fld.general_bound(name) == (float(lo), float(hi) + 1.0)
    monkeypatch.setattr(po, "component_fit_bound_overrides",
                        lambda: {name: (float(lo) - 1.0, None)})
    assert fld.general_bound(name) == (float(lo) - 1.0, float(hi))
    assert fld.general_bound("no_existe") is None
