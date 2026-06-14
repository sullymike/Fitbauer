"""Identificación/sugerencia de fases por comparación con la base de datos de referencia.

Función pura (sin GUI): dado un conjunto de parámetros hiperfinos (δ, ΔEQ, B_hf)
de una componente —ya sea estimada de los mínimos antes de ajustar, o ajustada
después—, compara contra la base de datos de referencia
(``data_sample/reference/mossbauer_reference.json``) y devuelve las fases más
compatibles, ordenadas por una distancia normalizada.

Convenciones (idénticas a las de Fitbauer):
- δ (isomer shift) referido a α-Fe a temperatura ambiente.
- Para sextetes se compara δ, |ΔEQ| (desplazamiento cuadrupolar, signo ambiguo)
  y B_hf. Para dobletes, δ y ΔEQ. Para singletes, sólo δ.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from core.constants import APP_ROOT

#: Ruta por defecto de la base de datos de referencia.
DEFAULT_DB_PATH = APP_ROOT / "data_sample" / "reference" / "mossbauer_reference.json"

#: Umbral de campo hiperfino para considerar una componente "magnética" (sextete).
MAGNETIC_BHF_MIN_T = 5.0

# Tolerancias por defecto (escala de "1 sigma" para normalizar cada dimensión).
TOL_DELTA = 0.10   # mm/s
TOL_QUAD = 0.20    # mm/s
TOL_BHF = 2.0      # T
TOL_TEMP = 150.0   # K (sólo desempate suave)


@dataclass(frozen=True)
class PhaseMatch:
    """Una fase candidata con su grado de compatibilidad."""
    sample: str
    klass: str
    oxidation_state: str
    temperature_k: float | None
    delta: float | None
    quad: float | None
    bhf: float | None
    site: int | None
    site_total: int | None
    reference: str
    reference_url: str
    distance: float          # 0 = idéntico; menor es mejor
    score: float             # 1/(1+distance) ∈ (0, 1]; mayor es mejor

    @property
    def score_pct(self) -> float:
        return 100.0 * self.score


@lru_cache(maxsize=4)
def load_reference_db(path: str | None = None) -> tuple[dict, ...]:
    """Carga (y cachea) la base de datos de referencia como tupla de dicts."""
    p = Path(path) if path else DEFAULT_DB_PATH
    if not p.exists():
        return ()
    data = json.loads(p.read_text(encoding="utf-8"))
    return tuple(data)


def _infer_kind(delta: float | None, quad: float | None, bhf: float | None) -> str:
    """Deduce el tipo de componente a partir de los parámetros disponibles."""
    if bhf is not None and bhf > MAGNETIC_BHF_MIN_T:
        return "Sextete"
    if quad is not None and abs(quad) > 1e-6:
        return "Doblete"
    return "Singlete"


def _ref_is_magnetic(entry: dict) -> bool:
    b = entry.get("Bhf_T")
    return b is not None and float(b) > MAGNETIC_BHF_MIN_T


def suggest_phases(
    delta: float,
    quad: float | None = None,
    bhf: float | None = None,
    *,
    kind: str | None = None,
    temperature: float | None = None,
    tol_delta: float = TOL_DELTA,
    tol_quad: float = TOL_QUAD,
    tol_bhf: float = TOL_BHF,
    top_n: int = 6,
    db: tuple[dict, ...] | None = None,
) -> list[PhaseMatch]:
    """Devuelve hasta ``top_n`` fases de referencia compatibles, mejor primero.

    Parameters
    ----------
    delta, quad, bhf:
        Parámetros de la componente (mm/s, mm/s, T). ``quad``/``bhf`` opcionales.
    kind:
        ``"Sextete"`` / ``"Doblete"`` / ``"Singlete"``. Si es ``None`` se infiere.
    temperature:
        Temperatura de medida (K), usada como desempate suave si se conoce.
    tol_*:
        Escala de normalización por dimensión (mm/s y T).
    """
    entries = db if db is not None else load_reference_db()
    if not entries:
        return []
    if kind is None:
        kind = _infer_kind(delta, quad, bhf)
    magnetic = kind == "Sextete"

    matches: list[PhaseMatch] = []
    for e in entries:
        ref_mag = _ref_is_magnetic(e)
        # Gating de régimen: una componente magnética sólo casa con refs magnéticas.
        if magnetic != ref_mag:
            continue

        terms: list[float] = []
        rd = e.get("IS_mm_s")
        if rd is not None and delta is not None:
            terms.append(((delta - float(rd)) / tol_delta) ** 2)
        else:
            continue  # sin δ no hay comparación útil

        if kind in ("Sextete", "Doblete") and quad is not None:
            rq = e.get("QS_mm_s")
            if rq is not None:
                # Signo de ΔEQ ambiguo en sextetes; comparar magnitudes.
                a, b = (abs(quad), abs(float(rq))) if magnetic else (quad, float(rq))
                w = 0.5 if magnetic else 1.0  # en sextetes el quad pesa menos
                terms.append(w * ((a - b) / tol_quad) ** 2)

        if magnetic and bhf is not None:
            rb = e.get("Bhf_T")
            if rb is not None:
                terms.append(((bhf - float(rb)) / tol_bhf) ** 2)

        if not terms:
            continue
        distance = (sum(terms) / len(terms)) ** 0.5

        # Desempate suave por temperatura.
        rt = e.get("T_K")
        if temperature is not None and rt is not None:
            distance += 0.15 * abs(temperature - float(rt)) / TOL_TEMP

        matches.append(PhaseMatch(
            sample=e.get("sample", "?"),
            klass=e.get("class", ""),
            oxidation_state=str(e.get("oxidation_state", "")),
            temperature_k=(float(rt) if rt is not None else None),
            delta=(float(rd) if rd is not None else None),
            quad=(float(e["QS_mm_s"]) if e.get("QS_mm_s") is not None else None),
            bhf=(float(e["Bhf_T"]) if e.get("Bhf_T") is not None else None),
            site=e.get("site"),
            site_total=e.get("site_total"),
            reference=e.get("reference", ""),
            reference_url=e.get("reference_url", ""),
            distance=distance,
            score=1.0 / (1.0 + distance),
        ))

    matches.sort(key=lambda m: m.distance)
    # Deduplicar por (fase, sitio) conservando el mejor, manteniendo orden.
    seen: set[tuple[str, int | None]] = set()
    unique: list[PhaseMatch] = []
    for m in matches:
        key = (m.sample, m.site)
        if key in seen:
            continue
        seen.add(key)
        unique.append(m)
        if len(unique) >= top_n:
            break
    return unique
