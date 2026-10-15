#!/usr/bin/env python3
"""Serie M — asimetría de línea por interferencia (AKS de SITE).

Hallazgo del nivel 1 de la revisión del código fuente (2026-08-02): ``LORLIN``
(``siteauxl.for:638``) multiplica CADA lorentziana por ``1 − AKS·(v−v₀)/Γ``,
con AKS global y ajustable (índice ``MBKG+5``). Fitbauer no tenía equivalente
y el banco nunca lo había sondeado.

Sondas previas sobre el binario demo 27.01.1994 (``sonda_aks``):

* AKS está OPERATIVO (no es de los interruptores inertes del demo).
* La fórmula del fuente de 1990 describe al ejecutable: ajustándola a las
  curvas del demo el rms es 1.2·10⁻⁴ — el suelo de precisión de su ``.PLT`` —
  frente a 5.9·10⁻³ con el signo invertido.
* ``AKS=...`` y ``AKS(1)=...`` producen la misma curva (es un escalar global).
* El signo refleja la línea; +0.3 y −0.3 son espejos exactos.

Round-trip: SITE genera con AKS conocido → Fitbauer ajusta con ``line_asym``
libre y debe recuperarlo.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from runner import Case
from series_AB import _sx, _db, _sg

# Valores de AKS a barrer: signo, magnitud pequeña (régimen realista en ⁵⁷Fe)
# y magnitud grande (para que el ajuste tenga señal de sobra).
_AKS = (-0.40, -0.15, 0.10, 0.30, 0.60)

# El banco normaliza el espectro por el percentil 90 de las cuentas dobladas.
# Con asimetría fuerte, la cola del perfil se vuelve NEGATIVA (absorción por
# encima de la línea base) en casi la mitad del rango, así que el P90 deja de
# ser la base y todo el espectro queda reescalado ~0.2 %. Eso arrastra a
# `depth` y a `baseline` JUNTOS: su cociente sigue siendo exacto (4·10⁻⁶ en
# M1_aks+0.60), pero comparar `depth` contra la verdad absoluta mide la
# normalización del banco, no el modelo. Se excluye de la comparación.
_SKIP = ("s1_depth",)

SERIES: dict[str, list[Case]] = {}


def _aks_case(cid: str, comps: list[dict], aks: float, nota: str,
              vmax: float = 10.0) -> Case:
    return Case(
        cid, comps, vmax=vmax,
        param_extra=[f"AKS={aks:g}, AKSFIT=.FALSE.,"],
        fit_kwargs={"extra_model": {"free_line_asym": True}},
        truth_override={"line_asym": aks},
        skip_params=_SKIP,
        nota=nota,
    )


# M1: singlete — el caso más limpio, la asimetría no se confunde con nada.
SERIES["M1"] = [
    _aks_case(f"M1_aks{a:+.2f}", [_sg(iso=0.3, wid=0.25, dep=0.05)], a,
              f"asimetria AKS={a:+.2f} sobre singlete", vmax=4.0)
    for a in _AKS
]

# M2: doblete — comprueba que la asimetría no se degenera con el propio
# desdoblamiento (un doblete con líneas de distinta ALTURA es lo que un
# usuario podría confundir con textura o con anchuras desiguales).
SERIES["M2"] = [
    _aks_case(f"M2_aks{a:+.2f}",
              [_db(iso=0.35, qua=1.2, wid=0.25, dep=0.05)], a,
              f"asimetria AKS={a:+.2f} sobre doblete", vmax=4.0)
    for a in _AKS
]

# M3: sexteto — caso realista; la asimetría afecta a las seis líneas a la vez
# y compite con D13/D23, así que se dejan las intensidades libres.
SERIES["M3"] = [
    Case(f"M3_aks{a:+.2f}", [_sx(bhf=33.0, wid=0.25, dep=0.05)],
         vmax=10.0,
         param_extra=[f"AKS={a:g}, AKSFIT=.FALSE.,"],
         fit_kwargs={"free_intensities": True,
                     "extra_model": {"free_line_asym": True}},
         truth_override={"line_asym": a},
         skip_params=_SKIP,
         nota=f"asimetria AKS={a:+.2f} sobre sexteto (intensidades libres)")
    for a in _AKS
]

# M4: control — sin AKS en SITE, Fitbauer con line_asym LIBRE debe devolver 0.
# Es el test de que el parámetro nuevo no inventa asimetría donde no la hay.
SERIES["M4"] = [
    Case("M4_control_sexteto", [_sx(bhf=33.0, wid=0.25, dep=0.05)],
         vmax=10.0,
         fit_kwargs={"extra_model": {"free_line_asym": True}},
         truth_override={"line_asym": 0.0},
         nota="control: sin AKS, line_asym libre debe salir 0"),
    Case("M4_control_doblete", [_db(iso=0.35, qua=1.2, wid=0.25, dep=0.05)],
         vmax=4.0,
         fit_kwargs={"extra_model": {"free_line_asym": True}},
         truth_override={"line_asym": 0.0},
         nota="control: sin AKS, line_asym libre debe salir 0"),
]


if __name__ == "__main__":
    from runner import dedupe_resumen, run_series_v0

    only = sys.argv[1:] or sorted(SERIES)
    for name in only:
        if name in SERIES:
            run_series_v0(name, SERIES[name])
    # Re-ejecutar una serie vuelve a APPEND al resumen: sin esto quedan filas
    # duplicadas por (serie, caso, versión, parámetro).
    dedupe_resumen()
