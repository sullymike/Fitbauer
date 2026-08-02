#!/usr/bin/env python3
"""Serie N — fracción resonante de la fuente (FSO de SITE, integral de transmisión).

Hallazgo del nivel 6 de la revisión del código fuente (2026-08-02). En la rama
``IFTRAN`` de ``sitecalf.for`` la transmisión final es::

    YC = 1 − FSO + FSO · ( L_fuente ⊗ exp(−TAB·A) + WING )

o sea FSO acota la absorción máxima a FSO en vez de a 1: solo esa fracción de
los fotones que llegan pertenece a la línea Mössbauer y puede absorberse.
Fitbauer no tenía equivalente, y NO es degenerado con la profundidad salvo en
el límite fino (``depth`` escala τ DENTRO de la exponencial; FSO escala el
resultado ya saturado).

Sondas previas sobre el binario demo 27.01.1994 (``sonda_fso``):

* FSO está OPERATIVO y se puede fijar por namelist (``FSO=`` y ``FSO(1)=`` son
  equivalentes: es un escalar global).
* La fórmula del fuente describe al binario EXACTAMENTE: con FSO=0.7 la base
  medida es 1−0.7+0.7·0.996811 = 0.997768 y el mínimo 1−0.7+0.7·0.239481 =
  0.467637, ambos clavados.
* Reproduciendo el algoritmo completo del fuente (malla VTRA, regla del
  rectángulo y corrección WING) con NTRA=600 se recupera el ``.PLT`` del
  binario con rms 2.7·10⁻⁷.

Round-trip: SITE genera con FSO y espesor conocidos → Fitbauer ajusta con
``src_frac`` libre y debe recuperarlo. Se usa TAB alto a propósito: con
absorbente fino FSO y profundidad son degenerados y el ajuste no puede
separarlos (eso también se comprueba, en N3).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from runner import Case

# El techo de absorción solo es observable si el absorbente SATURA.
_TAB_GRUESO = 20.0

SERIES: dict[str, list[Case]] = {}


def _caso(cid: str, fso: float, tab: float, nota: str,
          free_frac: bool = True) -> Case:
    comp = {"nline": 1, "iso": 0.0, "wid": 0.25, "dep": 0.05, "tab": tab}
    extra_model = {"src_fwhm_fixed": 0.097}
    if free_frac:
        extra_model["free_src_frac"] = True
    return Case(
        cid, [comp], vmax=4.0,
        param_extra=["IFTRAN=.TRUE.,", f"FSO={fso:g}, FSOFIT=.FALSE.,"],
        fit_kwargs={"absorber_model": "transmission",
                    "extra_model": extra_model},
        truth_override={"src_frac": fso},
        # `depth` no se compara: en modo transmisión es la profundidad óptica τ
        # y su verdad depende de TAB·área, con la degeneración τ↔FSO que la
        # propia serie estudia.
        skip_params=("s1_depth",),
        nota=nota,
    )


# N1: barrido de FSO con absorbente grueso — el caso que FSO existe para cubrir.
SERIES["N1"] = [
    _caso(f"N1_fso{f:.2f}", f, _TAB_GRUESO,
          f"FSO={f:.2f} con absorbente grueso (TAB={_TAB_GRUESO:g})")
    for f in (0.4, 0.55, 0.7, 0.85, 1.0)
]

# N2: FSO fijo y espesor variable — comprueba que se separa de τ al saturar.
SERIES["N2"] = [
    _caso(f"N2_tab{t:g}", 0.6, t, f"FSO=0.6 con TAB={t:g}")
    for t in (2.0, 5.0, 10.0, 30.0)
]

# N3: control de la DEGENERACIÓN. Con absorbente fino, FSO y la profundidad
# óptica son el mismo parámetro (a_eff ≈ FSO·τ) y el ajuste no puede
# separarlos. Se deja documentado como límite conocido, no como fallo.
SERIES["N3"] = [
    _caso("N3_fino_degenerado", 0.6, 0.2,
          "control: absorbente fino, FSO degenerado con la profundidad"),
]


if __name__ == "__main__":
    from runner import dedupe_resumen, run_series_v0

    only = sys.argv[1:] or sorted(SERIES)
    for name in only:
        if name in SERIES:
            run_series_v0(name, SERIES[name])
    dedupe_resumen()
