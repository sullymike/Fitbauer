"""Árbol del historial de ajustes, sin Qt.

Cada entrada del historial (``gui/fit_history.py``) lleva ``id`` y ``parent``:
el ajuste del que partió. Restaurar una entrada y volver a ajustar abre una
rama desde ella, en vez de colgar el ajuste nuevo del último (como Olex2).
Aquí vive lo que no es interfaz: migrar el historial antiguo, recortarlo sin
romper ramas y describir qué cambió respecto al padre.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Callable

#: Ficheros distintos que se conservan (los de uso más reciente).
MAX_FILES = 20

_COMP_KEY = re.compile(r"s(\d+)_(\w+)")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def file_key(entry: dict) -> str:
    """Espectro de la entrada: la ruta si consta, si no el nombre."""
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    return str(entry.get("file_path") or payload.get("file_path")
               or entry.get("file_name") or "—")


def migrate(entries: list[dict]) -> list[dict]:
    """Da ``id``/``parent``/``note`` a las entradas antiguas, que no los
    tenían: dentro de cada fichero se encadenan en orden (una rama lineal,
    que es lo que fueron)."""
    last: dict[str, str] = {}
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        e = dict(e)
        key = file_key(e)
        if not e.get("id"):
            e["id"] = new_id()
            e["parent"] = last.get(key)
        e.setdefault("parent", None)
        e.setdefault("note", "")
        e["file_path"] = key
        last[key] = e["id"]
        out.append(e)
    return out


def _remove(entries: list[dict], victim: dict) -> list[dict]:
    """Quita una entrada; sus hijos pasan a colgar de su padre (la rama no
    se parte)."""
    vid, vparent = victim["id"], victim.get("parent")
    out = []
    for e in entries:
        if e is victim:
            continue
        if e.get("parent") == vid:
            e = dict(e, parent=vparent)
        out.append(e)
    return out


def prune(entries: list[dict], max_per_file: int, *, max_files: int = MAX_FILES,
          protect: set[str] | frozenset = frozenset()) -> list[dict]:
    """Recorta a ``max_per_file`` entradas por fichero y ``max_files``
    ficheros. Nunca se borran solas las entradas con nota ni las de
    ``protect`` (el nodo actual). Se quitan primero las hojas más antiguas
    (ramas abandonadas); si no hay, la entrada más antigua, cuyos hijos pasan
    a su padre."""
    entries = list(entries)
    last_use = {file_key(e): i for i, e in enumerate(entries)}
    keep_files = set(sorted(last_use, key=last_use.get)[-max_files:])
    entries = [e for e in entries if file_key(e) in keep_files or e.get("note")
               or e.get("id") in protect]
    for key in {file_key(e) for e in entries}:
        while True:
            group = [e for e in entries if file_key(e) == key]
            if len(group) <= max_per_file:
                break
            parents = {e.get("parent") for e in entries}
            newest = group[-1].get("id")
            removable = [e for e in group if not e.get("note")
                         and e.get("id") not in protect and e.get("id") != newest]
            leaves = [e for e in removable if e.get("id") not in parents]
            pool = leaves or removable
            if not pool:
                break
            entries = _remove(entries, pool[0])
    return entries


def children_map(entries: list[dict]) -> tuple[list[dict], dict[str, list[dict]]]:
    """(raíces, hijos por id), en orden cronológico. Una entrada cuyo padre
    ya no está es raíz."""
    ids = {e.get("id") for e in entries}
    roots: list[dict] = []
    kids: dict[str, list[dict]] = {}
    for e in entries:
        p = e.get("parent")
        if p and p in ids:
            kids.setdefault(p, []).append(e)
        else:
            roots.append(e)
    return roots, kids


# ── Qué cambió respecto al padre ─────────────────────────────────────────
def _ms(entry: dict) -> dict:
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    ms = payload.get("model_state")
    return ms if isinstance(ms, dict) else {}


def _by_idx(ms: dict, key: str) -> dict[int, object]:
    raw = ms.get(key) if isinstance(ms.get(key), dict) else {}
    out = {}
    for k, v in raw.items():
        try:
            out[int(k)] = v
        except (TypeError, ValueError):
            continue
    return out


def _fmt_chi2(x) -> str | None:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if x != x else f"{x:.4g}"


def describe_changes(parent: dict, entry: dict, *, label: Callable[[str], str],
                     tr: Callable[..., str]) -> list[str]:
    """Frases con lo que cambió del ajuste ``parent`` al ``entry``: modo,
    componentes (añadidas, quitadas, tipo, tratamiento), parámetros fijados o
    liberados, restricciones, cotas propias, opciones de ajuste y χ²ᵣ. Los
    valores no se listan: un ajuste los cambia todos."""
    from core.params import relevant_params

    a, b = _ms(parent), _ms(entry)
    out: list[str] = []
    if parent.get("mode") != entry.get("mode"):
        out.append(tr("history.diff_option", name=tr("history.col_mode"),
                      a=parent.get("mode", "—"), b=entry.get("mode", "—")))

    def kind_name(k) -> str:
        return tr(f"kind.{k}", default=str(k))

    en_a, en_b = _by_idx(a, "sextet_enabled"), _by_idx(b, "sextet_enabled")
    kd_a, kd_b = _by_idx(a, "component_kind"), _by_idx(b, "component_kind")
    qt_a, qt_b = _by_idx(a, "quad_treatment"), _by_idx(b, "quad_treatment")
    im_a, im_b = _by_idx(a, "intensity_mode"), _by_idx(b, "intensity_mode")
    both: list[int] = []
    for idx in sorted(set(en_a) | set(en_b)):
        on_a, on_b = bool(en_a.get(idx)), bool(en_b.get(idx))
        if on_b and not on_a:
            out.append(tr("history.diff_added", kind=kind_name(kd_b.get(idx)), idx=idx))
        elif on_a and not on_b:
            out.append(tr("history.diff_removed", kind=kind_name(kd_a.get(idx)), idx=idx))
        elif on_a and on_b:
            both.append(idx)
            if kd_a.get(idx) != kd_b.get(idx):
                out.append(tr("history.diff_kind", idx=idx, a=kind_name(kd_a.get(idx)),
                              b=kind_name(kd_b.get(idx))))
            for src_a, src_b, key in ((qt_a, qt_b, "history.diff_quad"),
                                      (im_a, im_b, "history.diff_intensity")):
                if src_a.get(idx) != src_b.get(idx):
                    out.append(tr(key, idx=idx, a=src_a.get(idx, "—"), b=src_b.get(idx, "—")))

    fx_a = a.get("fixed") if isinstance(a.get("fixed"), dict) else {}
    fx_b = b.get("fixed") if isinstance(b.get("fixed"), dict) else {}
    usados: dict[int, set[str]] = {}
    for idx in both:
        try:
            usados[idx] = relevant_params(str(kd_b.get(idx)), str(im_b.get(idx, "free")),
                                          str(qt_b.get(idx, "1st_order")))
        except Exception:
            usados[idx] = set()
    fijados, liberados = [], []
    for key in sorted(set(fx_a) | set(fx_b), key=_key_order):
        m = _COMP_KEY.fullmatch(key)
        if m and (int(m.group(1)) not in usados or m.group(2) not in usados[int(m.group(1))]):
            continue
        va, vb = bool(fx_a.get(key)), bool(fx_b.get(key))
        if key not in fx_a or key not in fx_b or va == vb:
            continue
        (fijados if vb else liberados).append(label(key))
    if fijados:
        out.append(tr("history.diff_fixed", params=", ".join(fijados)))
    if liberados:
        out.append(tr("history.diff_freed", params=", ".join(liberados)))

    ca, cb = a.get("constraints") or [], b.get("constraints") or []
    if json.dumps(ca, sort_keys=True) != json.dumps(cb, sort_keys=True):
        out.append(tr("history.diff_constraints", a=len(ca), b=len(cb)))
    ba = a.get("bounds_user") if isinstance(a.get("bounds_user"), dict) else {}
    bb = b.get("bounds_user") if isinstance(b.get("bounds_user"), dict) else {}
    cambiadas = [label(k) for k in sorted(set(ba) | set(bb), key=_key_order)
                 if ba.get(k) != bb.get(k)]
    if cambiadas:
        out.append(tr("history.diff_bounds", params=", ".join(cambiadas)))

    opciones = ["line_profile", "likelihood", "absorber_model"]
    if entry.get("mode") == "distribution" or parent.get("mode") == "distribution":
        opciones += ["dist_variable", "dist_shape", "dist_reg_mode"]
    for key in opciones:
        if a.get(key) != b.get(key) and (key in a or key in b):
            out.append(tr("history.diff_option", name=key, a=a.get(key, "—"),
                          b=b.get(key, "—")))

    c0, c1 = _fmt_chi2(parent.get("red_chi2")), _fmt_chi2(entry.get("red_chi2"))
    if not out:
        out.append(tr("history.diff_none"))
    if c0 and c1:
        out.append(tr("history.diff_chi2", a=c0, b=c1))
    return out


def _key_order(key: str) -> tuple:
    m = _COMP_KEY.fullmatch(key)
    return (1, int(m.group(1)), m.group(2)) if m else (0, 0, key)
