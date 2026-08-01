#!/usr/bin/env python3
"""Revalidación del banco con las mejoras de modelo (versión "v0m").

Re-ajusta las series que mostraban sesgo de modelo con la extensión que lo
elimina: A4/A5/A6-HC/B3/D4_sextHC → quad_treatment="hamiltonian" (intensidades
FIJAS 3:2:1: el modelo las calcula); E3 → curvatura libre; E1 binned →
channel_sub; F1/F2/I1 → integral de transmisión (fuente fija en WDS=0.097).
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from runner import Case, VALID_ROOT, append_rows, dedupe_resumen, fit_case
from series_AB import SERIES as SAB
from series_CG import SERIES as SCG


def refit(serie: str, cases, mutate) -> None:
    rows = []
    for case in cases:
        c2 = copy.deepcopy(case)
        mutate(c2)
        rows += fit_case(serie, c2, "v0m", data_version="v0")
    append_rows(rows)
    ok = sum(1 for r in rows if r.get("convergido") == "si")
    print(f"[{serie}] v0m: {len(cases)} casos re-ajustados ({ok} filas ok)")


def m_hamiltonian(c: Case) -> None:
    c.fit_kwargs = dict(c.fit_kwargs)
    c.fit_kwargs["quad_treatment"] = "hamiltonian"
    c.fit_kwargs["free_intensities"] = False


def m_curv(c: Case) -> None:
    c.fit_kwargs = dict(c.fit_kwargs)
    em = dict(c.fit_kwargs.get("extra_model") or {})
    em["free_curv"] = True
    c.fit_kwargs["extra_model"] = em


def m_channel(c: Case) -> None:
    c.fit_kwargs = dict(c.fit_kwargs)
    em = dict(c.fit_kwargs.get("extra_model") or {})
    em["channel_sub"] = 5
    c.fit_kwargs["extra_model"] = em


def m_transmission(c: Case) -> None:
    c.fit_kwargs = dict(c.fit_kwargs)
    c.fit_kwargs["absorber_model"] = "transmission"
    em = dict(c.fit_kwargs.get("extra_model") or {})
    em["src_fwhm_fixed"] = 0.097
    c.fit_kwargs["extra_model"] = em


def e1_binned_cases() -> list[Case]:
    from series_AB import _sx
    from series_CG import _E1  # no usado: casos derivados con vmax_eff propio
    out = []
    for cid in ("E1_dob_n256bin", "E1_dob_n128bin",
                "E1_sext_n256bin", "E1_sext_n128bin"):
        vj = VALID_ROOT / "E1" / cid / "verdad.json"
        if not vj.exists():
            continue
        info = json.loads(vj.read_text())
        out.append(Case(cid, info["comps"], vmax=float(info["vmax"]),
                        nchan=int(info["nchan"]), nota=info.get("nota", "")[:80]))
    return out


if __name__ == "__main__":
    refit("A4", SAB["A4"], m_hamiltonian)
    refit("A5", SAB["A5"], m_hamiltonian)
    refit("A6", [c for c in SAB["A6"] if c.cid.endswith("_HC")], m_hamiltonian)
    refit("B3", SAB["B3"], m_hamiltonian)
    refit("D4", [c for c in SCG["D4"] if c.cid == "D4_sextHC+dob"], m_hamiltonian)
    refit("E3", SCG["E3"], m_curv)
    refit("E1", e1_binned_cases(), m_channel)
    refit("F1", SCG["F1"], m_transmission)
    refit("F2", SCG["F2"], m_transmission)
    refit("I", [c for c in __import__("series_HI").I_CASES
                if c.cid.startswith("I1")], m_transmission)
    dedupe_resumen()
