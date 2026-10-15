#!/usr/bin/env python3
"""Serie V: perfil Voigt del binario SITE-1994 (STG) contra Fitbauer.

Semántica del binario (sondas voigt94 + fuente §19): con VOIGT(n)=.TRUE.,
``STG(n)`` es la anchura gaussiana — **σ en mm/s** para subespectros
paramagnéticos (convolución Voigt real, la MISMA convención voigt_sigma de
Fitbauer) y **σ_B en Tesla** para sextetes (distribución gaussiana de campo,
el modelo "Gaussiana"/VBF de Fitbauer). WID sigue siendo la Γ Lorentziana.

- V1 (paramagnético): singlete/doblete con σ ∈ {0.05, 0.15, 0.30} →
  ajuste discreto de Fitbauer con perfil Voigt y σ LIBRE (fit_sigma).
- V2 (magnético): sexteto 33 T con σ_B ∈ {0.5, 1.5, 3.0} → ajuste de
  distribución con forma Gaussiana (CLI --shape gaussiana): debe recuperar
  ⟨B⟩ = 33·k y σ = STG.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from normos_lib import BHF_SCALE_SITE, FITBAUER_ROOT, VALID_ROOT
from runner import Case, append_rows, dedupe_resumen, fit_case, generate_series
from series_AB import _sx, _db, _sg

V1 = []
for s in (0.05, 0.15, 0.30):
    V1.append(Case(f"V1_sg_s{s:g}",
                   [dict(_sg(iso=0.3, wid=0.25), stg=s,
                         raw=["VOIGT(1)=.TRUE.,"])],
                   vmax=4.0,
                   truth_override={"voigt_sigma": s},
                   fit_kwargs={"line_profile": "Voigt",
                               "extra_model": {"fit_sigma": True}},
                   nota=f"singlete Voigt STG={s} (sigma mm/s)"))
    V1.append(Case(f"V1_db_s{s:g}",
                   [dict(_db(iso=0.35, qua=1.2, wid=0.25), stg=s,
                         raw=["VOIGT(1)=.TRUE.,"])],
                   vmax=4.0,
                   truth_override={"voigt_sigma": s},
                   fit_kwargs={"line_profile": "Voigt",
                               "extra_model": {"fit_sigma": True}},
                   nota=f"doblete Voigt STG={s}"))

V2 = [Case(f"V2_sx_sb{s:g}",
           [dict(_sx(bhf=33.0, wid=0.25), stg=s,
                 raw=["VOIGT(1)=.TRUE.,"])],
           vmax=10.0,
           nota=f"sexteto Voigt magnetico STG={s} T (P(B) gaussiana)")
      for s in (0.5, 1.5, 3.0)]


def fit_V2() -> list[dict]:
    """Ajuste de distribución Gaussiana a los sextetes Voigt-magnéticos."""
    rows = []
    py = str(FITBAUER_ROOT / ".venv" / "bin" / "python")
    for case in V2:
        cdir = VALID_ROOT / "V2" / case.cid
        if not (cdir / "v0.dat").exists():
            continue
        stg = case.comps[0]["stg"]
        prefix = cdir / "fit_v0_gauss"
        cmd = [py, str(FITBAUER_ROOT / "fit_bhf_distribution_cli.py"),
               str(cdir / "v0.dat"), "--out-prefix", str(prefix),
               "--vmax", "10", "--variable", "bhf",
               "--bmin", "15", "--bmax", "50", "--nbins", "36",
               "--gamma", "0.25", "--shape", "gaussiana"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                           cwd=str(FITBAUER_ROOT))
        dist_f = Path(f"{prefix}_distribution.dat")
        if r.returncode != 0 or not dist_f.exists():
            rows.append({"serie": "V2", "caso": case.cid, "version": "v0",
                         "parametro": "-", "convergido": "no",
                         "nota": (r.stderr or r.stdout)[-140:]})
            continue
        cols = np.loadtxt(dist_f)
        w = np.maximum(cols[:, 1], 0.0)
        wn = w / w.sum()
        avg = float(np.sum(wn * cols[:, 0]))
        std = float(np.sqrt(np.sum(wn * (cols[:, 0] - avg) ** 2)))
        for pn, tv, fv in (("dist_avg", 33.0 * BHF_SCALE_SITE, avg),
                           ("dist_std", stg, std)):
            rows.append({"serie": "V2", "caso": case.cid, "version": "v0",
                         "parametro": pn, "verdadero": f"{tv:.4f}",
                         "ajustado": f"{fv:.4f}",
                         "abs_delta": f"{abs(fv - tv):.4f}",
                         "convergido": "si", "nota": case.nota})
            print(f"  {case.cid} {pn}: {tv:.3f} -> {fv:.3f}")
    return rows


if __name__ == "__main__":
    generate_series("V1", V1)
    rows = []
    for case in V1:
        rows += fit_case("V1", case, "v0")
    append_rows(rows)
    bad = [r for r in rows if r.get("convergido") != "si"]
    print(f"[V1] {len(rows)} filas, no-conv={len(bad)}")
    generate_series("V2", V2)
    append_rows(fit_V2())
    dedupe_resumen()
