"""Detección de componentes (core.component_detection): banco de espectros de
ejemplo con la respuesta conocida y casos que las reglas solas fallaban."""
from pathlib import Path

import numpy as np
import pytest

from core import component_detection as cd
from core.session import HeadlessSession

D = Path(__file__).resolve().parents[1] / "data_sample"
P = D / "public"
AB = {"Sextete": "S", "Doblete": "D", "Singlete": "L"}

#: (fichero, tipos verdaderos, Vmax). Los «sintetico_*» y los públicos son
#: sintéticos con parámetros conocidos; Fe3O4.adt es medido (dos sextetes).
CASOS = [
    (D / "hierro_metalico_alphaFe.adt", "S"), (D / "hematita_Fe2O3.adt", "S"),
    (D / "magnetita_Fe3O4.adt", "SS"), (D / "Fe3O4.adt", "SS"),
    (D / "siderita_FeCO3.adt", "D"), (D / "sintetico_singlete.adt", "L"),
    (D / "sintetico_doblete.adt", "D"), (D / "sintetico_doblete_singlete.adt", "DL"),
    (D / "sintetico_dos_sextetes.adt", "SS"), (D / "sintetico_sexteto_ancho.adt", "S"),
    (D / "sintetico_sexteto_doblete.adt", "DS"), (P / "goetita_FeOOH.adt", "S"),
    (P / "ferridrita_2lineas.adt", "D"), (P / "pirita_FeS2.adt", "D"),
    (P / "troilita_FeS.adt", "S"), (P / "wustita_FeO.adt", "D"),
    (P / "ilmenita_FeTiO3.adt", "D"), (P / "jarosita_KFe3SO4.adt", "S"),
    (P / "lepidocrocita_FeOOH.adt", "D"), (P / "maghemita_Fe2O3.adt", "S"),
    (P / "pirrotita_Fe7S8.adt", "DS"),
]


def _base(path):
    s = HeadlessSession()
    s.load_ws5(path, vmax=12.03 if path.name == "Fe3O4.adt" else 12.007)
    return s.build_fit_state()


def _tipos(kinds) -> str:
    return "".join(sorted(AB[k] for k in kinds))


@pytest.mark.parametrize("path,verdad", CASOS, ids=[c[0].stem for c in CASOS])
def test_detecta_los_tipos_correctos(path, verdad):
    rep = cd.evaluate_detection(_base(path))
    assert rep is not None
    assert _tipos(rep.final.kinds) == "".join(sorted(verdad)), [
        (cd.Proposal.signature(p), p.bic) for p in rep.proposals]
    # La elegida está entre las evaluadas y su χ²red es razonable.
    assert rep.chosen in rep.proposals
    assert rep.final.red_chi2 < 2.0


def test_las_reglas_siguen_ahi_y_se_explica_cada_paso():
    """Doblete + singlete: las reglas solo ven el doblete (χ²red alto); la
    propuesta evaluada gana con ΔBIC muy negativo y el informe lo cuenta."""
    rep = cd.evaluate_detection(_base(D / "sintetico_doblete_singlete.adt"))
    reglas = next(p for p in rep.proposals if p.origin[0] == "detect.origin_rules")
    assert _tipos(reglas.kinds) == "D" and reglas.red_chi2 > 3
    assert rep.final.bic < reglas.bic - 100
    assert all(np.isfinite(p.bic) and p.fitted for p in rep.proposals)


def test_una_componente_de_mas_se_poda():
    """Pirrotita: la búsqueda deja un doblete casi vacío; la poda lo quita
    (el BIC sin él no sube 6) y queda sextete + doblete."""
    rep = cd.evaluate_detection(_base(P / "pirrotita_Fe7S8.adt"))
    assert any("removed" in st for st in rep.residual_steps)
    assert _tipos(rep.final.kinds) == "DS"


def test_choose_prefiere_la_sencilla_salvo_evidencia_fuerte():
    a = cd.Proposal(origin=("x", {}), components=[(1, "Doblete", [])], params={}, bic=100.0)
    b = cd.Proposal(origin=("x", {}), components=[(1, "Doblete", []), (2, "Singlete", [])],
                    params={}, bic=95.0)
    c = cd.Proposal(origin=("x", {}), components=[(1, "Doblete", []), (2, "Singlete", [])],
                    params={}, bic=93.0)
    assert cd.choose([a, b]) is a            # −5: no basta
    assert cd.choose([a, c]) is c            # −7: sí
