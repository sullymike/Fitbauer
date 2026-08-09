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


def test_ligadura_de_area_se_reescala_a_profundidad():
    """`ARE(2)=f·ARE(1)` liga ÁREAS; en Fitbauer el parámetro es la
    profundidad (área = depth·(π/2)·ΣΓ). Con anchuras distintas, copiar el
    factor tal cual desescala el subespectro ligado (caso real ZN100215:
    salía un 14 % fuera de la curva de NORMOS)."""
    job = """X.MOS
X.JOB
X.RES
X.PLT
 &DATA
 NLTEXT=4, TRIANG=.TRUE., VMAX=12.0, PFP=256.5,
 &END
dos dobletes
area ligada
 &PARAM
 NSUB=2,
 NLINE(1)=2, ISO(1)=0.24, QUA(1)=0.69, WID(1)=0.44, DEP(1)=0.14,
 NLINE(2)=2, ISO(2)=0.23, QUA(2)=0.37, WID(2)=0.25,
 NDEX(30)=15, FACTOR(30)=0.24, CONST(30)=0,
 &END
"""
    est = job_to_model_state(job)["model_state"]
    cons = est["constraints"]
    assert len(cons) == 1
    assert cons[0]["target"] == "s2_depth"
    assert cons[0]["source"] == "s1_depth"
    # depth_2 = f·(den_1/den_2)·depth_1 con den ∝ WID·(1+D21)
    assert cons[0]["factor"] == pytest.approx(0.24 * 0.44 / 0.25)
    # y la razón de ÁREAS resultante es la que pedía NORMOS
    d1 = est["vars"]["s1_depth"]
    area1 = d1 * (np.pi / 2.0) * 0.44 * 2.0
    area2 = cons[0]["factor"] * d1 * (np.pi / 2.0) * 0.25 * 2.0
    assert area2 / area1 == pytest.approx(0.24)


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


# ── Ficheros de NORMOS-DIST ──────────────────────────────────────────────────

JOB_DIST = """D.MOS
D.JOB
D.RES
D.PLT
 &DATA
 NLTEXT=4, TRIANG=.TRUE., VMAX=10.0,
 &END
distribucion
de campo
 &PARAM
 NSUB=20, NSB(1)=20, DISTRI(1)=1, METHOD(1)=1, LAMDA(1)=0.01,
 BHF(1)=10.0, DTB(1)=2.0, WID(1)=0.25,
 &END
"""


def test_un_job_de_dist_se_rechaza_con_mensaje_claro():
    """No debe importarse como 20 sextetos discretos, que es lo que parece.

    Un ``.JOB`` de NORMOS-DIST tiene la misma estructura que uno de SITE, pero
    su ``NSUB`` son los puntos de la malla de la distribución.
    """
    from core.normos_job import es_job_de_dist, parse_job

    assert es_job_de_dist(parse_job(JOB_DIST)["param"]) is True
    assert es_job_de_dist(parse_job(JOB_C2)["param"]) is False
    with pytest.raises(NormosJobError, match="NORMOS-DIST"):
        job_to_model_state(JOB_DIST)


@pytest.mark.parametrize("clave", ["DISTRI(1)=1", "METHOD(1)=6", "NSB(1)=20",
                                   "LAMDA(1)=0.01", "QUP(1)=0.3", "AVG(1)=30"])
def test_cada_marcador_de_dist_dispara(clave):
    job = JOB_C2.replace(" NSUB=1,", f" NSUB=1, {clave},")
    with pytest.raises(NormosJobError, match="NORMOS-DIST"):
        job_to_model_state(job)


# ── NORMOS-DIST: carga en el panel de distribución ───────────────────────────

JOB_DIST_XL = """D.MOS
D.JOB
D.RES
D.PLT
 &DATA
 NLTEXT=4, TRIANG=.TRUE., VMAX=10.0, PFP=256.5,
 &END
distribucion
con sitios nitidos
 &PARAM
 METHOD=1, DISTRI=1, NSUB=10,
 WID=.3, LAMDA=1.2, BETA1=.0, BETA2=20.0,
 ISO=.5, ISOFIT=.true., QUA=-0.015, QUAFIT=.false.,
 BHF=0., BHFFIT=.false., DTB=5.0, DTBFIT=.true.,
 DTI=0.01, DTIFIT=.false.,
 NXLS=2,
 NXLL(1)=6, DEX(1)=0.05, DEXFIT(1)=.TRUE., ISX(1)=0.2, ISXFIT(1)=.TRUE.,
 QUX(1)=-0.029, BHX(1)=44, BHXFIT(1)=.TRUE., WIX(1)=0.4, WIXFIT(1)=.TRUE.,
 NXLL(2)=2, DEX(2)=0.1, ISX(2)=0.3, QUX(2)=0.7, WIX(2)=0.4,
 &END
"""


def test_un_job_de_dist_se_carga_en_el_panel_de_distribucion():
    from core.normos_job import job_to_distribution_state

    r = job_to_distribution_state(JOB_DIST_XL)
    s = r["model_state"]
    assert r["variable"] == "bhf"
    assert s["dist_shape"] == "Histograma"
    # La malla es BHF + (k-1)·DTB, k = 1..NSB (distcalf.for: RH = BHF+PP*DTB).
    assert s["dist_bmin"] == pytest.approx(0.0)
    assert s["dist_bmax"] == pytest.approx(45.0)
    assert s["dist_nbins"] == 10
    assert s["dist_gamma"] == pytest.approx(0.3)
    assert s["dist_delta"] == pytest.approx(0.5)
    # El panel de distribución, no el modo discreto.
    assert s["mode_combo_idx"] == 1
    assert s["dist_variable"] == "BHF"


@pytest.mark.parametrize("method, variable", [(1, "bhf"), (2, "bhf"), (4, "bhf"),
                                              (6, "quad"), (7, "quad"), (8, "delta")])
def test_method_elige_la_variable_distribuida(method, variable):
    """``distinif.for``: 1-5 campo, 6-7 cuadrupolo, 8 desplazamiento isomérico."""
    from core.normos_job import job_to_distribution_state

    job = JOB_DIST_XL.replace("METHOD=1,", f"METHOD={method},")
    assert job_to_distribution_state(job)["variable"] == variable


def test_la_malla_de_cuadrupolo_usa_qua_y_dtq():
    from core.normos_job import job_to_distribution_state

    job = (JOB_DIST_XL.replace("METHOD=1,", "METHOD=6,")
                      .replace("QUA=-0.015", "QUA=0.25")
                      .replace("DTB=5.0", "DTB=5.0, DTQ=0.05"))
    s = job_to_distribution_state(job)["model_state"]
    assert s["dist_bmin"] == pytest.approx(0.25)
    assert s["dist_bmax"] == pytest.approx(0.25 + 9 * 0.05)


def test_dtq_no_se_traslada_en_distribuciones_de_campo():
    """NORMOS solo aplica DTI en METHOD 1-5; DTQ es un parámetro muerto ahí.

    Sus bucles (``distcalf.for`` 318-319, 355-356, 405-406, 441-442) calculan
    ``RH = BHF+PP*DTB`` y ``RI = ISO+PP*DTI``, sin tocar ΔEQ. Trasladarlo metía
    una correlación que NORMOS nunca aplicó.
    """
    from core.normos_job import job_to_distribution_state

    job = JOB_DIST_XL.replace("DTI=0.01,", "DTI=0.01, DTQ=0.03,")
    r = job_to_distribution_state(job)
    assert r["model_state"]["dist_quad_slope"] == 0.0
    assert any("DTQ" in a and "IGNORA" in a for a in r["warnings"])
    # En cambio DTI sí, normalizado por el paso de la malla.
    assert r["model_state"]["dist_delta_slope"] == pytest.approx(0.01 / 5.0)


def test_los_sitios_cristalinos_son_componentes_nitidos():
    from core.normos_job import job_to_distribution_state

    r = job_to_distribution_state(JOB_DIST_XL)
    s = r["model_state"]
    assert r["n_sharp"] == 2
    assert s["dist_use_sharp"] is True
    # NXLL = número de líneas: 6 → sextete, 2 → doblete.
    assert s["component_kind"] == {"1": "Sextete", "2": "Doblete"}
    assert s["vars"]["s1_delta"] == pytest.approx(0.2)
    assert s["vars"]["s1_bhf"] == pytest.approx(44.0)
    assert s["vars"]["s1_gamma1"] == pytest.approx(0.4)
    assert s["vars"]["s2_quad"] == pytest.approx(0.7)
    # ISXFIT/BHXFIT=.true. → libres; QUX sin bandera → queda como esté.
    assert s["fixed"]["s1_delta"] is False
    assert s["fixed"]["s1_bhf"] is False
    # Y lo que el .JOB no define se apaga, para que no sume sobre la malla.
    assert s["sextet_enabled"]["3"] is False


def test_beta_sobre_lamda_es_el_anclaje_de_bordes():
    """``SMOOTH`` (distauxl.for) suma BETA1/BETA2 a λ·D₂ᵀD₂ en las esquinas."""
    from core.normos_job import job_to_distribution_state

    r = job_to_distribution_state(JOB_DIST_XL)
    assert r["edge_anchor"] == pytest.approx(20.0 / 1.2)
    assert any("LAMDA" in a for a in r["warnings"])


def test_distri_selecciona_la_forma():
    from core.normos_job import job_to_distribution_state

    def forma(job):
        return job_to_distribution_state(job)["model_state"]["dist_shape"]

    assert forma(JOB_DIST_XL) == "Histograma"
    assert forma(JOB_DIST_XL.replace("DISTRI=1,", "DISTRI=2,")) == "Gaussiana"
    # DISTRI=3 es binomial si CONC>0 y fija si CONC=0.
    assert forma(JOB_DIST_XL.replace("DISTRI=1,", "DISTRI=3, CONC=5.0,")) == "Binomial"
    assert forma(JOB_DIST_XL.replace("DISTRI=1,", "DISTRI=3,")) == "Fija"


def test_czjzek_avisa_de_que_no_esta_implementado():
    from core.normos_job import job_to_distribution_state

    r = job_to_distribution_state(JOB_DIST_XL.replace("DISTRI=1,", "DISTRI=4,"))
    assert any("Czjzek" in a for a in r["warnings"])
    assert r["model_state"]["dist_shape"] == "Histograma"


def test_un_job_de_site_no_pasa_por_el_lector_de_dist():
    from core.normos_job import job_to_distribution_state

    with pytest.raises(NormosJobError, match="no es un trabajo de NORMOS-DIST"):
        job_to_distribution_state(JOB_C2)


def test_una_malla_de_un_solo_punto_se_rechaza():
    from core.normos_job import job_to_distribution_state

    with pytest.raises(NormosJobError, match="menos de 2 puntos"):
        job_to_distribution_state(JOB_DIST_XL.replace("NSUB=10,", "NSUB=1,"))


def test_la_gui_importa_un_job_de_dist_en_el_panel(tmp_path, monkeypatch):
    """El importador distingue DIST de SITE y llena el panel de distribución."""
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    import mossbauer_qt

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = mossbauer_qt.MossbauerQtWindow()
    try:
        entrada = tmp_path / "DIST.JOB"
        entrada.write_text(JOB_DIST_XL, encoding="ascii")
        monkeypatch.setattr(
            QtWidgets.QFileDialog, "getOpenFileName",
            staticmethod(lambda *a, **k: (str(entrada), "")))
        monkeypatch.setattr(
            QtWidgets.QMessageBox, "information",
            staticmethod(lambda *a, **k: None))
        win.on_import_normos_job()

        # Modo P(BHF), no modo discreto: el .JOB describe una malla.
        assert win.mode_combo.currentIndex() == 1
        assert win.dist_variable == "bhf"
        d = win.dist_panel.to_view_state(variable="bhf")
        assert d.bmin == pytest.approx(0.0)
        assert d.bmax == pytest.approx(45.0)
        assert d.nbins == 10
        assert d.gamma == pytest.approx(0.3)
        assert d.use_sharp is True
        # Y los sitios cristalinos entran como componentes nítidos.
        estado = win._session_payload()["model_state"]
        assert estado["component_kind"]["1"] == "Sextete"
        assert estado["vars"]["s1_bhf"] == pytest.approx(44.0, rel=1e-4)
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


# ── El .JOB trae consigo su espectro ─────────────────────────────────────────

@pytest.mark.parametrize("pfp, esperado", [
    # normospr.for:601-604 — IPFP=PFP+1e-4 trunca, y los pares Y(IPFA-L+1) +
    # Y(IPFA+L) suman 2·IPFA+1: el eje cae en ⌊PFP⌋ + 0.5.
    (257.23656, 257.5),    # YU16051D
    (257.35935, 257.5),    # YU30031D
    (512.50813, 512.5),
    (258.08755, 258.5),
    (256.5, 256.5),
    (257.0, 257.5),        # un entero exacto sigue doblando medio canal arriba
])
def test_el_punto_de_doblado_cae_en_el_medio_canal_inferior(pfp, esperado):
    from core.normos_job import punto_de_doblado_normos

    assert punto_de_doblado_normos(pfp) == pytest.approx(esperado)


def test_pfp_es_semilla_y_no_se_impone_como_centro():
    """NORMOS refina PFP en dos ciclos; congelarlo daría otro doblado."""
    r = job_to_model_state(JOB_C2)
    assert r["center"] == pytest.approx(256.5)          # se informa…
    assert "center" not in r["model_state"]["vars"]     # …pero no se impone
    assert any("SEMILLA" in a for a in r["warnings"])


def test_resuelve_el_espectro_declarado_en_el_job(tmp_path):
    from core.normos_job import resuelve_fichero_de_datos

    job = tmp_path / "TRABAJO.JOB"
    job.write_text(JOB_C2, encoding="ascii")
    # JOB_C2 declara «C0000.MOS» en su primera línea.
    datos = tmp_path / "C0000.MOS"
    datos.write_text("0\n", encoding="ascii")
    (tmp_path / "TRABAJO.RES").write_text("", encoding="ascii")
    assert resuelve_fichero_de_datos(job) == datos


def test_el_nombre_del_espectro_no_distingue_mayusculas(tmp_path):
    """Los .JOB vienen de DOS: la caja del nombre rara vez casa con el disco."""
    from core.normos_job import resuelve_fichero_de_datos

    job = tmp_path / "TRABAJO.JOB"
    job.write_text(JOB_C2, encoding="ascii")
    datos = tmp_path / "c0000.mos"
    datos.write_text("0\n", encoding="ascii")
    assert resuelve_fichero_de_datos(job) == datos


def test_nunca_devuelve_una_salida_de_normos(tmp_path):
    """.RES y .PLT también se nombran en la cabecera; no son el espectro."""
    from core.normos_job import resuelve_fichero_de_datos

    job = tmp_path / "TRABAJO.JOB"
    job.write_text(JOB_C2, encoding="ascii")
    for nombre in ("C0000.RES", "C0000.PLT"):
        (tmp_path / nombre).write_text("", encoding="ascii")
    assert resuelve_fichero_de_datos(job) is None


def test_cae_al_unico_espectro_de_la_carpeta(tmp_path):
    from core.normos_job import resuelve_fichero_de_datos

    job = tmp_path / "TRABAJO.JOB"
    job.write_text(JOB_C2, encoding="ascii")
    datos = tmp_path / "OTRO_NOMBRE.ws5"
    datos.write_text("0\n", encoding="ascii")
    assert resuelve_fichero_de_datos(job) == datos
    # Pero con DOS candidatos la elección sería una adivinanza: mejor nada.
    (tmp_path / "TERCERO.ws5").write_text("0\n", encoding="ascii")
    assert resuelve_fichero_de_datos(job) is None


def test_la_gui_carga_el_espectro_junto_al_job(tmp_path, monkeypatch):
    """Importar un .JOB debe traer también sus datos, no solo el modelo."""
    pytest.importorskip("PySide6")
    import numpy as np
    from PySide6 import QtWidgets

    import mossbauer_qt

    # Espectro sintético de una columna, con el nombre que declara JOB_C2.
    rng = np.random.default_rng(0)
    cuentas = rng.poisson(10000, 512)
    (tmp_path / "C0000.MOS").write_text(
        "\n".join(str(int(c)) for c in cuentas) + "\n", encoding="ascii")
    entrada = tmp_path / "TRABAJO.JOB"
    entrada.write_text(JOB_C2, encoding="ascii")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = mossbauer_qt.MossbauerQtWindow()
    try:
        monkeypatch.setattr(
            QtWidgets.QFileDialog, "getOpenFileName",
            staticmethod(lambda *a, **k: (str(entrada), "")))
        monkeypatch.setattr(
            QtWidgets.QMessageBox, "information",
            staticmethod(lambda *a, **k: None))
        win.on_import_normos_job()

        assert win.file.path is not None
        assert win.file.path.name == "C0000.MOS"
        assert win.file.counts is not None and win.file.counts.size == 512
        assert win.file.y_data is not None      # doblado y normalizado
        # Y el modelo del .JOB sigue aplicado sobre esos datos.
        estado = win._session_payload()["model_state"]
        assert estado["vars"]["s1_bhf"] == pytest.approx(33.0, rel=1e-4)
        assert win.calib.vmax.value() == pytest.approx(10.0)
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()
