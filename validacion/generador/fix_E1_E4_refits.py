#!/usr/bin/env python3
"""Correcciones tras la primera pasada C–F:

1. E1: el demo de SITE solo produce espectros de 512 canales crudos (lector
   WS5 exige ≥512; plegado NP≤256). Los tamaños 128/256 se derivan por
   binning exacto (suma de pares) de la teoría 512; 1024 queda documentado
   como límite de SITE. El eje de velocidad de la versión binned NO llega a
   ±vmax (los centros de bin quedan a Δ/2 del borde): se ajusta con
   vmax_eff = vmax − (nbin−1)·Δ/2 para no introducir un sesgo artificial.
2. E4: regenerar a 512 canales (la versión 1024 falló en SITE).
3. Re-ajustes con el arnés corregido (matching de componentes, int2 de
   doblete libre, multistart en multi-singlete): B2, A7, C3, D1–D6, E5, D4.
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from normos_lib import unfold_theory, write_adt
from runner import (Case, VALID_ROOT, append_rows, dedupe_resumen, fit_case,
                    generate_series, refit_series)
from series_AB import SERIES as SAB, _db, _sx
from series_CG import SERIES as SCG


def make_E1_binned() -> list[tuple[str, Case]]:
    """Deriva E1 de 256/128 canales crudos por binning de la teoría 512."""
    out = []
    for src_cid, comps, vmax in (("E1_dob_n512", [_db()], 4.0),
                                 ("E1_sext_n512", [_sx()], 10.0)):
        th_f = VALID_ROOT / "E1" / src_cid / "teoria_norm.npy"
        if not th_f.exists():
            continue
        th = np.load(th_f)                      # 256 puntos plegados
        delta_v = 2.0 * vmax / (th.size - 1)
        for nbin in (2, 4):
            binned = th.reshape(-1, nbin).mean(axis=1)
            nchan_raw = 2 * binned.size
            cid = src_cid.replace("n512", f"n{nchan_raw}bin")
            cdir = VALID_ROOT / "E1" / cid
            cdir.mkdir(parents=True, exist_ok=True)
            raw = unfold_theory(binned, 1_000_000 * nbin)
            write_adt(cdir / "v0.dat", raw)
            np.save(cdir / "teoria_norm.npy", binned)
            vmax_eff = vmax - (nbin - 1) * delta_v / 2.0
            info = {"caso": cid, "serie": "E1", "comps": comps,
                    "vmax": vmax_eff, "nchan": nchan_raw,
                    "derivado_de": src_cid,
                    "nota": f"binning x{nbin} de la teoria SITE 512 "
                            f"(SITE demo no genera {nchan_raw} canales); "
                            f"vmax_eff={vmax_eff:.5f}"}
            (cdir / "verdad.json").write_text(
                json.dumps(info, indent=1, ensure_ascii=False))
            out.append(("E1", Case(cid, comps, vmax=vmax_eff, nchan=nchan_raw,
                                   nota=info["nota"][:100])))
    return out


def main() -> None:
    # E1 binned
    rows = []
    for serie, case in make_E1_binned():
        rows += fit_case(serie, case, "v0")
    append_rows(rows)
    print(f"[E1b] {len(rows)} filas (binned)")

    # E4 a 512 canales
    e4 = [Case("E4_dob_512", [_db()], vmax=4.0, nchan=512,
               nota="doblete 512 ch: sin plegar vs plegado"),
          Case("E4_sext_512", [_sx()], nchan=512,
               nota="sexteto 512 ch: sin plegar vs plegado")]
    generate_series("E4", e4)
    rows = []
    for case in e4:
        rows += fit_case("E4", case, "v0")
    append_rows(rows)
    # ajuste directo de la teoria plegada
    import series_CG
    series_CG.SERIES["E4"] = e4
    series_CG.fit_E4_folded()

    # Re-ajustes con arnés corregido
    refit_series("B2", SAB["B2"])
    refit_series("A7", SAB["A7"])
    refit_series("C3", SCG["C3"])
    for s in ("D1", "D2", "D3", "D4", "D5", "D6", "E5"):
        refit_series(s, SCG[s])
    dedupe_resumen()


if __name__ == "__main__":
    main()
