"""Interoperabilidad con los ficheros ``.JOB`` de NORMOS-SITE.

Fitbauer lee y escribe el formato de trabajo de NORMOS, sin ejecutarlo ni
distribuirlo. Lo delicado son las conversiones de convenio (anchuras referidas
a líneas distintas, intensidades por área frente a profundidad, DEP como área
del subespectro), todas verificadas aquí contra los valores que el banco de
validación calculaba a mano.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.normos_job import (
    NormosJobError,
    job_to_model_state,
    model_state_to_job,
    parse_job,
)

# Caso C2_invertida_b33 del banco: anchuras por par invertidas, que es donde
# los convenios de NORMOS y Fitbauer más se separan.
JOB_C2 = """C0000.MOS
C0000.JOB
C0000.RES
C0000.PLT
 &DATA
 NLTEXT=4, TRIANG=.TRUE., MXCFUN=5000, REMOTE=.TRUE., PLTDAT=.TRUE.,
 PLTSUB=.TRUE., VMAX=10.0, PFP=256.5,
 &END
Serie C2
C2_invertida_b33
 &PARAM
 NSUB=1,
 NLINE(1)=6,
 ISO(1)=0.0, ISOFIT(1)=.FALSE.,
 QUA(1)=0.0, QUAFIT(1)=.FALSE.,
 BHF(1)=33.0, BHFFIT(1)=.FALSE.,
 WID(1)=0.3, WIDFIT(1)=.FALSE.,
 DEP(1)=0.05, DEPFIT(1)=.FALSE.,
 D13(1)=3.0, D13FIT(1)=.FALSE.,
 D23(1)=2.0, D23FIT(1)=.FALSE.,
 W13(1)=0.7, W13FIT(1)=.FALSE.,
 W23(1)=1.3, W23FIT(1)=.FALSE.,
 &END
"""


def test_parse_job_separa_los_bloques():
    j = parse_job(JOB_C2)
    assert j["files"][0] == "C0000.MOS"
    assert j["titles"] == ["Serie C2", "C2_invertida_b33"]
    assert j["data"]["VMAX"] == "10.0"
    assert j["param"]["NSUB"] == "1"
    assert j["param"]["W13(1)"] == "0.7"


def test_texto_sin_param_lanza():
    with pytest.raises(NormosJobError):
        parse_job("no soy un job")


def test_conversion_de_convenios():
    """Los valores son los que el banco calculaba a mano para este caso.

    - ``WID`` es de las líneas 3,4 → ``gamma1 = WID·W13 = 0.3·0.7``
    - ``gamma2 = W23/W13``, ``gamma3 = 1/W13``
    - ``D13``/``D23`` son ÁREAS → ``int1 = D13/W13``, ``int2 = D23/W23``
    - ``DEP`` es el área del subespectro → ``depth = DEP / ((π/2)·2·WID·(D13+D23+1))``
    """
    v = job_to_model_state(JOB_C2)["model_state"]["vars"]
    assert v["s1_gamma1"] == pytest.approx(0.21)
    assert v["s1_gamma2"] == pytest.approx(1.857143, rel=1e-5)
    assert v["s1_gamma3"] == pytest.approx(1.428571, rel=1e-5)
    assert v["s1_int1"] == pytest.approx(4.285714, rel=1e-5)
    assert v["s1_int2"] == pytest.approx(1.538462, rel=1e-5)
    assert v["s1_depth"] == pytest.approx(0.00884194, rel=1e-5)
    assert v["s1_bhf"] == pytest.approx(33.0)


def test_metadatos_de_adquisicion():
    r = job_to_model_state(JOB_C2)
    assert r["vmax"] == pytest.approx(10.0)
    assert r["center"] == pytest.approx(256.5)
    assert r["model_state"]["component_kind"] == {"1": "Sextete"}
    assert r["model_state"]["drive_form"] == "triangular"


def test_el_area_del_subespectro_se_conserva():
    """El criterio de fondo: el ÁREA que declara el .JOB es la que sale."""
    from core.physics import component_absorption
    from core.constants import SEXTET_PARAM_NAMES

    v_grid = np.linspace(-40.0, 40.0, 32001)
    vals = job_to_model_state(JOB_C2)["model_state"]["vars"]
    p = np.array([vals[f"s1_{n}"] for n in SEXTET_PARAM_NAMES], dtype=float)
    area = float(np.trapezoid(component_absorption(v_grid, "Sextete", p), v_grid))
    assert area == pytest.approx(0.05, rel=0.02)      # DEP(1) = 0.05


def test_avisa_de_la_escala_de_bhf():
    avisos = " ".join(job_to_model_state(JOB_C2)["warnings"])
    assert "sextet_pattern" in avisos


def test_avisa_de_lo_que_no_traslada():
    job = JOB_C2.replace(" NSUB=1,", " NSUB=1,\n POLAR=.TRUE.,")
    avisos = " ".join(job_to_model_state(job)["warnings"])
    assert "POLAR" in avisos


def test_octete_avisa_de_las_lineas_extra():
    job = JOB_C2.replace("NLINE(1)=6", "NLINE(1)=8")
    avisos = " ".join(job_to_model_state(job)["warnings"])
    assert "octete" in avisos.lower()


@pytest.mark.parametrize("nline,kind", [(1, "Singlete"), (2, "Doblete"),
                                        (6, "Sextete")])
def test_tipos_de_componente(nline, kind):
    job = JOB_C2.replace("NLINE(1)=6", f"NLINE(1)={nline}")
    assert job_to_model_state(job)["model_state"]["component_kind"] == {"1": kind}


def test_transmision_y_asimetria():
    job = JOB_C2.replace(
        " NSUB=1,", " NSUB=1,\n IFTRAN=.TRUE., WDS=0.11, FSO=0.8, AKS=0.25,")
    ms = job_to_model_state(job)["model_state"]
    assert ms["absorber_model"] == "transmission"
    assert ms["vars"]["src_fwhm"] == pytest.approx(0.11)
    assert ms["vars"]["src_frac"] == pytest.approx(0.8)
    assert ms["vars"]["line_asym"] == pytest.approx(0.25)


JOB_2SUB = """X.MOS
X.JOB
X.RES
X.PLT
 &DATA
 NLTEXT=4, TRIANG=.TRUE., VMAX=10.0, PFP=256.5,
 &END
dos sitios
con ligadura
 &PARAM
 NSUB=2,
 NLINE(1)=6, ISO(1)=0.10, BHF(1)=33.0, WID(1)=0.25, DEP(1)=0.05,
 NLINE(2)=6, ISO(2)=0.22, BHF(2)=45.0, WID(2)=0.25, DEP(2)=0.03,
 NDEX(31)=16, FACTOR(31)=1.0, CONST(31)=0.12,
 &END
"""


def test_ligaduras_por_indice_global():
    """El subespectro n empieza en 13+15(n−1); ISO del 2 es el índice 31.

    Es la numeración global del ``.RES`` de NORMOS: 5 de fondo + 8 de isótopo
    y luego 15 por subespectro. Equivocarse aquí ligaría el parámetro que no
    es, en silencio.
    """
    cons = job_to_model_state(JOB_2SUB)["model_state"]["constraints"]
    assert len(cons) == 1
    assert cons[0]["target"] == "s2_delta"
    assert cons[0]["source"] == "s1_delta"
    assert cons[0]["offset"] == pytest.approx(0.12)


def test_flags_de_ajuste():
    job = JOB_C2.replace("BHFFIT(1)=.FALSE.", "BHFFIT(1)=.TRUE.")
    fijos = job_to_model_state(job)["model_state"]["fixed"]
    assert fijos["s1_bhf"] is False        # FIT=.TRUE. → libre
    assert fijos["s1_delta"] is True


# ── Exportación ──────────────────────────────────────────────────────────────

def test_round_trip_conserva_los_parametros():
    r1 = job_to_model_state(JOB_C2)
    texto = model_state_to_job(r1["model_state"], vmax=r1["vmax"],
                               center=r1["center"])
    r2 = job_to_model_state(texto)
    v1, v2 = r1["model_state"]["vars"], r2["model_state"]["vars"]
    for k in ("s1_delta", "s1_quad", "s1_bhf", "s1_gamma1", "s1_gamma2",
              "s1_gamma3", "s1_int1", "s1_int2", "s1_depth"):
        assert v2[k] == pytest.approx(v1[k], rel=1e-4), k


def test_el_job_exportado_tiene_la_estructura_de_normos():
    texto = model_state_to_job(job_to_model_state(JOB_C2)["model_state"],
                               stem="X0", vmax=10.0, center=256.5)
    lineas = texto.split("\r\n")
    assert lineas[:4] == ["X0.MOS", "X0.JOB", "X0.RES", "X0.PLT"]
    assert " &DATA" in lineas and " &PARAM" in lineas
    assert lineas.count(" &END") == 2
    # NLTEXT son las líneas de cabecera del fichero de DATOS (4 para un WS5),
    # no los títulos del .JOB: ponerlo a 2 hacía que SITE fallase al leer.
    assert "NLTEXT=4" in texto
    # El lector de namelist de NORMOS no pasa de 72 columnas.
    assert max(len(l) for l in lineas) <= 72


def test_data_extra_permite_ajustar_la_cabecera():
    texto = model_state_to_job({"vars": {}, "component_kind": {}},
                               data_extra={"NLTEXT": 0, "TRIANG": ".FALSE."})
    assert "NLTEXT=0" in texto
    assert "TRIANG=.FALSE." in texto


def test_exporta_transmision():
    ms = job_to_model_state(JOB_C2.replace(
        " NSUB=1,", " NSUB=1,\n IFTRAN=.TRUE., WDS=0.11, FSO=0.8,"))["model_state"]
    texto = model_state_to_job(ms)
    assert "IFTRAN=.TRUE." in texto
    assert "WDS=0.11" in texto
    assert "FSO=0.8" in texto


# ── Integración con la GUI ───────────────────────────────────────────────────

def test_claves_i18n_en_todos_los_idiomas():
    """Las 6 claves nuevas deben existir en los 8 catálogos, o la GUI cae al id."""
    import glob
    import json

    claves = {"file.normos", "file.import_normos_job", "file.export_normos_job",
              "file.normos_job_imported", "file.normos_job_exported",
              "file.normos_job_warnings"}
    catalogos = glob.glob("locales/*/strings.json")
    assert len(catalogos) >= 8
    for ruta in catalogos:
        with open(ruta, encoding="utf-8") as fh:
            d = json.load(fh)
        faltan = claves - set(d)
        assert not faltan, f"{ruta}: faltan {sorted(faltan)}"
        for k in claves:
            assert d[k].strip(), f"{ruta}: «{k}» vacía"


def test_la_gui_registra_las_acciones_y_hace_el_ciclo(tmp_path, monkeypatch):
    """Importar → aplicar al modelo → exportar, sobre la ventana real."""
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    import mossbauer_qt

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = mossbauer_qt.MossbauerQtWindow()
    try:
        assert "file.import_normos_job" in win._action_registry
        assert "file.export_normos_job" in win._action_registry

        entrada = tmp_path / "TRABAJO.JOB"
        entrada.write_text(JOB_C2, encoding="ascii")
        monkeypatch.setattr(
            QtWidgets.QFileDialog, "getOpenFileName",
            staticmethod(lambda *a, **k: (str(entrada), "")))
        # El aviso informativo no debe bloquear el test.
        monkeypatch.setattr(
            QtWidgets.QMessageBox, "information",
            staticmethod(lambda *a, **k: None))
        win.on_import_normos_job()

        # El modelo de la ventana refleja el .JOB (con los convenios traducidos).
        estado = win._session_payload()["model_state"]
        assert estado["vars"]["s1_gamma1"] == pytest.approx(0.21, rel=1e-3)
        assert estado["vars"]["s1_bhf"] == pytest.approx(33.0, rel=1e-4)

        salida = tmp_path / "SALIDA.JOB"
        monkeypatch.setattr(
            QtWidgets.QFileDialog, "getSaveFileName",
            staticmethod(lambda *a, **k: (str(salida), "")))
        win.on_export_normos_job()
        assert salida.exists()
        vuelta = job_to_model_state(salida.read_text(encoding="ascii"))
        assert vuelta["model_state"]["vars"]["s1_bhf"] == pytest.approx(33.0, rel=1e-3)
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()
