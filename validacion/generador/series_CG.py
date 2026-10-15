#!/usr/bin/env python3
"""Bloques C (anchuras), D (multisitio/ligaduras), E (adquisición) y F
(espesor/transmisión). G (isótopos) no es ejecutable con el demo de SITE
(EGAMMA/GAMMA rechazados en todos los namelists): queda documentado.

Desviaciones respecto al plan, justificadas:
- C3 (anchuras línea a línea): SITE solo tiene anchuras por pares (W13/W23);
  se implementa con NSUB=6 singletes en las posiciones del sexteto.
- D1: N_max real del demo de SITE es 10 (12/14 fallan sin mensaje).
- D5 (ligaduras): el mecanismo NLINK de SITE no es descifrable sin manual;
  los espectros se generan respetando la ligadura y se valida el motor de
  ligaduras de Fitbauer (constraints target=factor·source+offset).
- E3: SITE no simula línea base no plana; se aplica en Python sobre el crudo.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from runner import Case
from series_AB import _sx, _db, _sg

POS33 = np.array([-5.329, -3.084, -0.839, 0.839, 3.084, 5.329])

SERIES: dict[str, list[Case]] = {}

# ── C: anchuras ──────────────────────────────────────────────────────────────
SERIES["C1"] = [
    Case(f"C1_g{g:.2f}", [_sx(wid=g)], nota="sexteto Gamma comun")
    for g in (0.22, 0.30, 0.45)]

_C2 = []
for tag, wid, w13, w23 in (("suave", 0.25, 1.28, 1.12),
                           ("fuerte", 0.28, 2.1429, 1.4286)):
    for b in (33.0, 46.0):
        _C2.append(Case(
            f"C2_{tag}_b{b:g}", [_sx(bhf=b, wid=wid, w13=w13, w23=w23)],
            fit_kwargs={"free_widths_common": False, "free_intensities": True},
            nota=f"anchuras por pares {tag}"))
SERIES["C2"] = _C2

_C3_CONF = {
    "suave":     [0.32, 0.28, 0.25, 0.25, 0.28, 0.32],
    "fuerte":    [0.60, 0.40, 0.28, 0.28, 0.40, 0.60],
    "asimetrica": [0.45, 0.30, 0.25, 0.22, 0.35, 0.28],
}
_AREAS = np.array([3, 2, 1, 1, 2, 3]) / 12.0
# Posiciones tipo sexteto de ~11 T (POS33·0.34): todas dentro del rango
# delta∈[-2,3] de Fitbauer. Con las posiciones de 33 T los singletes de
# Fitbauer NO pueden alcanzar ±3.08/±5.33 (limitación documentada, ver
# C3_fuera_de_rango).
_POSC3 = POS33 * 0.34
SERIES["C3"] = [
    Case(f"C3_{tag}",
         [_sg(iso=float(p), wid=float(w), dep=float(0.30 * a))
          for p, w, a in zip(_POSC3, ws, _AREAS)],
         vmax=4.0, fit_kwargs={"multistart_n": 8},
         nota=f"6 lineas libres (~11 T), anchuras {tag}")
    for tag, ws in _C3_CONF.items()]
SERIES["C3"].append(
    Case("C3_fuera_de_rango",
         [_sg(iso=float(p), wid=0.28, dep=float(0.30 * a))
          for p, a in zip(POS33, _AREAS)],
         fit_kwargs={"multistart_n": 8},
         nota="lineas libres en ±5.33/±3.08: fuera del limite delta de Fitbauer"))

# canal = 2*10/256 = 0.078 mm/s
SERIES["C4"] = [
    Case(f"C4_g{g:.3f}", [_sx(wid=g, dep=0.02)],
         nota=f"Gamma ~ {k}x anchura de canal")
    for k, g in ((1, 0.078), (2, 0.156))]

# ── D: multisitio y ligaduras ────────────────────────────────────────────────
_D1_MIX = {
    2:  [_sx(), _db(iso=1.1, qua=2.6, dep=0.03)],
    3:  [_sx(), _db(iso=1.1, qua=2.6, dep=0.03), _sg(iso=-0.2, dep=0.02)],
    4:  [_sx(), _sx(bhf=48.0, iso=0.4, dep=0.04), _db(iso=1.1, qua=2.6, dep=0.03),
         _sg(iso=-0.2, dep=0.02)],
    5:  [_sx(), _sx(bhf=48.0, iso=0.4, dep=0.04), _db(iso=1.1, qua=2.6, dep=0.03),
         _db(iso=0.35, qua=0.7, dep=0.025), _sg(iso=-0.2, dep=0.015)],
    6:  [_sx(bhf=26.0, dep=0.03), _sx(), _sx(bhf=48.0, iso=0.4, dep=0.04),
         _db(iso=1.1, qua=2.6, dep=0.025), _db(iso=0.35, qua=0.7, dep=0.02),
         _sg(iso=-0.2, dep=0.015)],
    8:  [_sx(bhf=20.0, dep=0.025), _sx(bhf=29.0, dep=0.03), _sx(bhf=38.0, dep=0.03),
         _sx(bhf=49.0, iso=0.4, dep=0.035), _db(iso=1.1, qua=2.6, dep=0.02),
         _db(iso=0.35, qua=0.7, dep=0.02), _db(iso=0.6, qua=1.6, dep=0.02),
         _sg(iso=-0.2, dep=0.012)],
    10: [_sx(bhf=15.0, dep=0.02), _sx(bhf=22.0, dep=0.025), _sx(bhf=30.0, dep=0.025),
         _sx(bhf=40.0, dep=0.03), _sx(bhf=50.0, iso=0.4, dep=0.03),
         _db(iso=1.1, qua=2.6, dep=0.018), _db(iso=0.35, qua=0.7, dep=0.018),
         _db(iso=0.6, qua=1.6, dep=0.015), _db(iso=0.9, qua=2.0, dep=0.015),
         _sg(iso=-0.2, dep=0.01)],
}
SERIES["D1"] = [
    Case(f"D1_n{n:02d}", comps,
         nota=f"{n} sitios" + (" (excede los 6 de la GUI Fitbauer)" if n > 6 else ""))
    for n, comps in _D1_MIX.items()]

SERIES["D2"] = [
    Case(f"D2_db{db:g}",
         [_sx(bhf=47.0 + db / 2, iso=0.27, dep=0.05),
          _sx(bhf=47.0 - db / 2, iso=0.67, dep=0.095)],
         fit_kwargs={"multistart_n": 6},
         nota=f"2 sextetos solapados dBhf={db} T, areas 1:1.9")
    for db in (0.5, 1, 2, 3, 5, 8)]

SERIES["D3"] = [
    Case(f"D3_f{f:g}pc",
         [_sx(dep=0.05), _db(iso=0.35, qua=0.7, dep=round(0.05 * f / (100 - f), 5))],
         nota=f"doblete minoritario {f}% del area")
    for f in (1, 2, 3, 5, 10, 20)]

SERIES["D4"] = [
    Case("D4_sext+dob", [_sx(bhf=51.7, iso=0.26, qua=-0.2), _db(iso=0.35, qua=0.7, dep=0.03)],
         nota="hematita + doblete Fe3+"),
    Case("D4_sext+dob+sing",
         [_sx(), _db(iso=1.1, qua=2.6, dep=0.03), _sg(iso=-0.1, dep=0.015)],
         nota="mezcla clasica 3 fases"),
    Case("D4_2sext+2dob",
         [_sx(bhf=49.0, iso=0.27, dep=0.04), _sx(bhf=46.0, iso=0.67, dep=0.06),
          _db(iso=0.35, qua=0.7, dep=0.025), _db(iso=1.1, qua=2.6, dep=0.02)],
         nota="magnetita + 2 dobletes"),
    Case("D4_suelo",
         [_sx(bhf=51.7, iso=0.26, qua=-0.2, dep=0.03),
          _sx(bhf=38.0, iso=0.25, qua=-0.13, dep=0.025, wid=0.4),
          _sx(bhf=49.0, iso=0.28, dep=0.02),
          _db(iso=0.35, qua=0.6, dep=0.03)],
         fit_kwargs={"multistart_n": 6},
         nota="tipo suelo: hematita+goethita+magnetita+Fe3+"),
    Case("D4_sextHC+dob",
         [_sx(qua=1.5, bhf=9.3, the=54.7), _db(iso=1.05, qua=1.8, dep=0.03)],
         param_extra=["HAMILT=.TRUE.,"],
         fit_kwargs={"quad_treatment": "kundig_fixed", "free_intensities": True},
         nota="sexteto HC (theta=54.7) + doblete"),
    Case("D4_2dob+sing",
         [_db(iso=1.15, qua=2.7, dep=0.04), _db(iso=0.38, qua=0.75, dep=0.035),
          _sg(iso=0.0, dep=0.012)],
         nota="dob Fe2+ + dob Fe3+ + singlete"),
    Case("D4_2sext_solap+dob",
         [_sx(bhf=48.0, iso=0.3, dep=0.05), _sx(bhf=46.0, iso=0.55, dep=0.05),
          _db(iso=0.35, qua=0.7, dep=0.005)],
         fit_kwargs={"multistart_n": 6},
         nota="2 sextetos solapados + doblete debil 3%"),
    Case("D4_5sitios_mitad_mag",
         [_sx(bhf=33.0, dep=0.03), _sx(bhf=45.0, iso=0.35, dep=0.03),
          _sx(bhf=25.0, iso=0.15, qua=0.1, dep=0.025),
          _db(iso=0.4, qua=0.8, dep=0.025), _db(iso=1.0, qua=2.2, dep=0.02)],
         fit_kwargs={"multistart_n": 6},
         nota="5 sitios, 3 magneticos + 2 dobletes"),
]

_LIG_COMPS = [_sx(dep=0.05), _sx(bhf=45.0, iso=0.4, dep=0.025)]
SERIES["D5"] = [
    Case("D5_gamma_comun",
         [_sx(wid=0.3), _db(iso=1.1, qua=2.6, wid=0.3, dep=0.03)],
         fit_kwargs={"constraints": [
             {"target": "s2_gamma1", "source": "s1_gamma1", "factor": 1.0}]},
         nota="ligadura Gamma comun entre sitios"),
    Case("D5_areas_2a1", list(_LIG_COMPS),
         fit_kwargs={"constraints": [
             {"target": "s2_depth", "source": "s1_depth", "factor": 0.5}]},
         nota="ligadura areas 2:1"),
    Case("D5_delta_ligado",
         [_sx(iso=0.1), _sx(bhf=45.0, iso=0.5, dep=0.025)],
         fit_kwargs={"constraints": [
             {"target": "s2_delta", "source": "s1_delta", "factor": 1.0,
              "offset": 0.4}]},
         nota="ligadura delta2 = delta1 + 0.4"),
    Case("D5_quad_ligado",
         [_db(iso=0.35, qua=1.2), _db(iso=1.1, qua=1.2, dep=0.03)],
         fit_kwargs={"constraints": [
             {"target": "s2_quad", "source": "s1_quad", "factor": 1.0}]},
         nota="ligadura DeltaEQ comun"),
    Case("D5_combinada",
         [_sx(wid=0.3, dep=0.05), _sx(bhf=45.0, iso=0.4, wid=0.3, dep=0.025)],
         fit_kwargs={"constraints": [
             {"target": "s2_gamma1", "source": "s1_gamma1", "factor": 1.0},
             {"target": "s2_depth", "source": "s1_depth", "factor": 0.5}]},
         nota="ligaduras Gamma comun + areas 2:1"),
    Case("D5_control_sin_ligar",
         [_sx(wid=0.3, dep=0.05), _sx(bhf=45.0, iso=0.4, wid=0.3, dep=0.025)],
         nota="control: mismo espectro sin ligaduras"),
]

SERIES["D6"] = [
    Case(f"D6_dq{dq:.2f}",
         [_db(iso=0.35, qua=1.2, dep=0.03), _db(iso=0.35, qua=1.2 + dq, dep=0.03)],
         vmax=4.0, fit_kwargs={"multistart_n": 6},
         nota=f"dobletes casi degenerados dDEQ={dq}")
    for dq in (0.05, 0.10, 0.20, 0.30)]

# ── E: linea base, discretizacion, adquisicion ───────────────────────────────
_E1 = []
for nch in (128, 256, 512, 1024):
    _E1.append(Case(f"E1_dob_n{nch}", [_db()], vmax=4.0, nchan=nch,
                    nota=f"doblete {nch} canales sin doblar"))
    _E1.append(Case(f"E1_sext_n{nch}", [_sx()], nchan=nch,
                    nota=f"sexteto {nch} canales sin doblar"))
SERIES["E1"] = _E1

SERIES["E2"] = [
    Case("E2_dob_v2", [_db(iso=0.3, qua=0.5)], vmax=2.0, nota="doblete vmax 2"),
    Case("E2_dob_v4", [_db()], vmax=4.0, nota="doblete vmax 4"),
    Case("E2_sext_v6", [_sx()], vmax=6.0, nota="sexteto 33T vmax 6 (lineas al 89% del rango)"),
    Case("E2_sext_v10", [_sx()], vmax=10.0, nota="sexteto vmax 10"),
    Case("E2_sext_v12", [_sx()], vmax=12.0, nota="sexteto vmax 12"),
    Case("E2_sext_v15", [_sx()], vmax=15.0, nota="sexteto vmax 15"),
]

# E3: base no plana aplicada en Python sobre el crudo (SITE no la modela).
# parabola: factor (1 + a*((i-c)/N)^2·4) → a en el borde; tilt: lineal en v.
SERIES["E3"] = [
    Case(f"E3_parab_{tag}", [_sx()], nota=f"parabola {tag} a={a} (post-proceso)",
         truth_override={}, fit_kwargs={},
         param_extra=[], data_extra={},
         )
    for tag, a in (("leve", 0.002), ("media", 0.005), ("fuerte", 0.015))
] + [Case("E3_inclinada", [_sx()], nota="base inclinada 0.5% (post-proceso)")]
_E3_COEF = {"E3_parab_leve": ("parab", 0.002), "E3_parab_media": ("parab", 0.005),
            "E3_parab_fuerte": ("parab", 0.015), "E3_inclinada": ("tilt", 0.005)}

SERIES["E4"] = [
    Case("E4_dob_1024", [_db()], vmax=4.0, nchan=1024,
         nota="doblete 1024 ch: sin plegar vs plegado"),
    Case("E4_sext_1024", [_sx()], nchan=1024,
         nota="sexteto 1024 ch: sin plegar vs plegado"),
]

SERIES["E5"] = [
    Case("E5_sext55_v8", [_sx(bhf=55.0)], vmax=8.0,
         nota="lineas 1,6 (8.88 mm/s) fuera del rango ±8"),
    Case("E5_dob_cortado", [_db(iso=0.0, qua=3.5)], vmax=1.6,
         nota="doblete DEQ=3.5 con lineas fuera de ±1.6"),
    Case("E5_sitio_parcial", [_sg(iso=0.0, dep=0.03), _db(iso=1.0, qua=3.0, dep=0.04)],
         vmax=2.2, nota="singlete dentro + doblete con una linea fuera"),
]

# ── F: espesor / integral de transmision ─────────────────────────────────────
def _thick(cid, comps, tab, absorber="thickness", extra_fit=None, nota=""):
    fk = {"absorber_model": absorber}
    fk.update(extra_fit or {})
    comps = [dict(c, tab=tab) for c in comps]
    return Case(cid, comps, param_extra=["IFTRAN=.TRUE.,"],
                fit_kwargs=fk, skip_params=("s1_depth", "s2_depth"),
                nota=nota or f"transmision t_a={tab} ({absorber})")

SERIES["F1"] = [
    _thick(f"F1_t{t:g}", [_sg(iso=0.3)], t)
    for t in (0.1, 0.25, 0.5, 1, 2, 5, 10, 20)]
SERIES["F2"] = ([_thick(f"F2_sext_t{t:g}", [_sx()], t) for t in (1, 5, 10)]
                + [_thick(f"F2_dob_t{t:g}", [_db()], t) for t in (1, 5, 10)])
# F3: los mismos espectros de F1 t={1,5,10} ajustados en aproximacion fina
SERIES["F3"] = [
    _thick(f"F3_t{t:g}_fina", [_sg(iso=0.3)], t, absorber="thin",
           nota=f"transmision t_a={t} ajustada con modelo fino (sesgo)")
    for t in (1, 5, 10)]


def postprocess_E3() -> None:
    """Aplica la base no plana a los v0.dat de E3 (tras generar)."""
    from normos_lib import write_adt
    from runner import VALID_ROOT
    for cid, (kind, a) in _E3_COEF.items():
        cdir = VALID_ROOT / "E3" / cid
        f = cdir / "v0.dat"
        marker = cdir / "postproceso.txt"
        if not f.exists() or marker.exists():
            continue
        raw = np.array([float(x) for x in f.read_text().split()])
        n = raw.size
        i = np.arange(1, n + 1, dtype=float)
        x = (i - (n / 2 + 0.5)) / n          # -0.5..0.5
        if kind == "parab":
            fac = 1.0 + a * (4.0 * x ** 2)   # a en los bordes
        else:
            # lineal en velocidad: mismo v para canales espejados
            v = np.where(i <= n / 2, (n / 2 - i + 0.5), (i - n / 2 - 0.5))
            v = v / (n / 2) * 2.0 - 1.0      # -1..1 en |v| — tilt en |v|... no:
            # tilt verdadero en v: canal 1..n/2 va de +v a -v; espejo igual
            vv = np.concatenate([np.linspace(1, -1, n // 2),
                                 np.linspace(-1, 1, n - n // 2)])
            fac = 1.0 + a * vv
        write_adt(f, np.round(raw * fac))
        marker.write_text(f"{kind} a={a} aplicado sobre v0.dat\n")


def fit_E4_folded() -> None:
    """E4: ajuste directo de la teoria plegada (espacio velocidad), sin doblar."""
    import json
    from runner import VALID_ROOT, expected_params, append_rows
    from core.session import ModelState
    from core.fit_engine import fit_discrete

    for case in SERIES["E4"]:
        cdir = VALID_ROOT / "E4" / case.cid
        th_f = cdir / "teoria_norm.npy"
        if not th_f.exists():
            continue
        theory = np.load(th_f)
        npc = theory.size
        v = np.linspace(-case.vmax, case.vmax, npc)
        ms = ModelState.defaults(n_components=len(case.comps))
        ms.n_components = len(case.comps)
        ms.multistart_n = 4
        rng = np.random.default_rng(1234)
        for i, c in enumerate(case.comps, 1):
            kind = {1: "Singlete", 2: "Doblete", 6: "Sextete"}[c.get("nline", 6)]
            ms.sextet_enabled[i] = True
            ms.component_kind[i] = kind
            ms.vars[f"s{i}_delta"] = c.get("iso", 0.0) + rng.uniform(-0.1, 0.1)
            ms.vars[f"s{i}_quad"] = c.get("qua", 0.0) * rng.uniform(0.85, 1.15)
            ms.vars[f"s{i}_gamma1"] = c.get("wid", 0.25) * rng.uniform(0.85, 1.15)
            ms.vars[f"s{i}_depth"] = 0.02
            ms.vars[f"s{i}_bhf"] = c.get("bhf", 33.0) * rng.uniform(0.9, 1.1)
            ms.fixed[f"s{i}_gamma2"] = True
            ms.fixed[f"s{i}_gamma3"] = True
            ms.fixed[f"s{i}_int1"] = True
            ms.fixed[f"s{i}_int2"] = True
        sigma = np.full(npc, 1e-3)
        st = ms.build_fit_state(velocity=v, y_data=theory, sigma_data=sigma,
                                counts=None, norm_factor=1.0)
        result = fit_discrete(st)
        truth = expected_params(case)
        rows = []
        for pname, tval in truth.items():
            fv = result.values.get(pname)
            if fv is None or pname not in result.free_keys and pname not in result.values:
                continue
            rows.append({"serie": "E4", "caso": case.cid, "version": "v0plegado",
                         "parametro": pname, "verdadero": f"{tval:.6g}",
                         "ajustado": f"{fv:.6g}",
                         "abs_delta": f"{abs(fv - tval):.3g}",
                         "convergido": "si", "nota": "ajuste directo plegado"})
        append_rows(rows)
        (cdir / "fitbauer_v0plegado.json").write_text(
            json.dumps({k: result.values.get(k) for k in truth}, indent=1))
    print("[E4] ajustes plegados añadidos")


if __name__ == "__main__":
    from runner import run_series_v0, generate_series
    only = sys.argv[1:] or list(SERIES)
    for name in only:
        if name == "E3":
            generate_series("E3", SERIES["E3"])
            postprocess_E3()
            from runner import fit_case, append_rows
            rows = []
            for case in SERIES["E3"]:
                rows += fit_case("E3", case, "v0")
            append_rows(rows)
            print(f"[E3] v0 con base no plana: {len(rows)} filas")
        else:
            run_series_v0(name, SERIES[name])
    if not sys.argv[1:] or "E4" in sys.argv[1:]:
        fit_E4_folded()
