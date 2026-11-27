"""Historial de ajustes en árbol: migración, recorte y diferencias."""
from gui import history_tree as ht


def _e(i, parent=None, f="a.adt", note="", **ms):
    return {"id": f"e{i}", "parent": parent, "note": note, "file_path": f,
            "file_name": f, "mode": "discrete", "red_chi2": 2.0 - 0.1 * i,
            "payload": {"model_state": ms}}


def _tr(key, default=None, **kw):
    return key + ("" if not kw else ":" + ",".join(f"{k}={v}" for k, v in sorted(kw.items())))


def test_migrar_encadena_las_entradas_antiguas_por_fichero():
    old = [{"file_name": "a", "payload": {"file_path": "/x/a"}},
           {"file_name": "b", "payload": {"file_path": "/x/b"}},
           {"file_name": "a", "payload": {"file_path": "/x/a"}}]
    m = ht.migrate(old)
    assert m[0]["parent"] is None and m[1]["parent"] is None
    assert m[2]["parent"] == m[0]["id"]
    assert all(e["note"] == "" for e in m)
    assert ht.migrate(m) == m                       # idempotente


def test_recorte_quita_ramas_abandonadas_y_respeta_notas():
    # e1 → e2 → e3 (rama principal); e1 → e4 (abandonada, hoja antigua)
    entries = [_e(1), _e(2, "e1"), _e(4, "e1"), _e(3, "e2")]
    out = ht.prune(entries, 3)
    assert [e["id"] for e in out] == ["e1", "e2", "e3"]
    # Sin hojas que quitar: la más antigua; sus hijos pasan a su padre.
    out = ht.prune(out, 2)
    assert [e["id"] for e in out] == ["e2", "e3"] and out[0]["parent"] is None
    # La nota y el nodo actual protegen.
    entries = [_e(1, note="buena"), _e(2, "e1"), _e(3, "e2")]
    out = ht.prune(entries, 1, protect={"e2"})
    assert {e["id"] for e in out} == {"e1", "e2", "e3"}
    # Ficheros: se quedan los de uso más reciente.
    many = [_e(i, f=f"f{i}") for i in range(25)]
    assert len(ht.prune(many, 5)) == ht.MAX_FILES


def test_arbol_y_huerfanos():
    entries = [_e(1), _e(2, "e1"), _e(3, "e1"), _e(5, "e9")]
    roots, kids = ht.children_map(entries)
    assert [r["id"] for r in roots] == ["e1", "e5"]
    assert [k["id"] for k in kids["e1"]] == ["e2", "e3"]


def test_diferencias_respecto_al_padre():
    base = dict(sextet_enabled={"1": True, "2": False},
                component_kind={"1": "Sextete", "2": "Doblete"},
                quad_treatment={"1": "1st_order", "2": "1st_order"},
                intensity_mode={"1": "free", "2": "free"},
                fixed={"s1_gamma1": False, "s1_texture": True, "vmax": True},
                constraints=[], line_profile="Lorentz")
    hijo = dict(base, sextet_enabled={"1": True, "2": True},
                fixed={"s1_gamma1": True, "s1_texture": False, "vmax": False},
                constraints=[{"target": "s2_delta"}], line_profile="Voigt",
                bounds_user={"s1_bhf": [45, None]})
    lines = ht.describe_changes(_e(1, **base), _e(2, "e1", **hijo), label=str, tr=_tr)
    assert "history.diff_added:idx=2,kind=kind.Doblete" in lines
    assert "history.diff_fixed:params=s1_gamma1" in lines
    assert "history.diff_freed:params=vmax" in lines        # textura no se usa: no sale
    assert "history.diff_constraints:a=0,b=1" in lines
    assert "history.diff_bounds:params=s1_bhf" in lines
    assert "history.diff_option:a=Lorentz,b=Voigt,name=line_profile" in lines
    assert lines[-1].startswith("history.diff_chi2")
    same = ht.describe_changes(_e(1, **base), _e(2, "e1", **base), label=str, tr=_tr)
    assert same[0] == "history.diff_none"
