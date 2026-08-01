#!/usr/bin/env python3
"""Librería del banco de validación Fitbauer vs NORMOS-SITE.

Genera espectros sintéticos con SITE.EXE (DOSBox), los convierte a formato
Fitbauer (espectro sin doblar, 2N canales, espejo alrededor de N+0.5) y los
ajusta con la capa headless de Fitbauer (core.session).

Convenciones verificadas (sesión 2026-06-17 + strings de SITE.EXE):
- SITE lee el JOB por stdin (``SITE < X.JOB``) con REMOTE=.TRUE.
- Espectro de entrada: WS5 XML de WissEl, CRLF.
- El .PLT contiene bloques de NP valores (8 por línea): velocidad, datos
  normalizados, curva de ajuste/teoría y un bloque por subespectro (PLTSUB).
- Eje de velocidad doblado: linspace(-VMAX, +VMAX, NP) — idéntico a Fitbauer.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

FITBAUER_ROOT = Path("/home/jorge/fitbauer")
VALID_ROOT = FITBAUER_ROOT / "validacion"
STAGING_ROOT = VALID_ROOT / "_staging"
SITE_EXE = Path("/home/jorge/normos_work/SITE.EXE")
DOSBOX = "dosbox"  # dosbox-staging 0.82.2 vía symlink /usr/local/bin/dosbox

sys.path.insert(0, str(FITBAUER_ROOT))

DEFAULT_NCHAN = 512          # canales sin doblar (SITE dobla a 256)
DEFAULT_BASE = 1_000_000     # cuentas de línea base
DEFAULT_VMAX = 10.0          # mm/s
DEFAULT_WID = 0.25           # FWHM mm/s (paso 0.6: WID de NORMOS = Γ FWHM)
DEFAULT_DEP = 0.05           # área integrada del subespectro en mm/s (paso 0.6)

# Escala de conversión BHF→velocidad de SITE respecto a Fitbauer, medida en el
# paso 0.6 ajustando la teoría de SITE (33 T: k=0.999619; 51.7 T: k=0.999620).
# SITE deriva las posiciones de momentos nucleares; Fitbauer usa el patrón
# publicado de α-Fe (33 T ↔ ±5.329 mm/s). Diferencia de convención, no un bug
# (ver CHANGELOG Fitbauer v4.0.2/v4.0.3).
BHF_SCALE_SITE = 0.9996195


# ── Generación de ficheros de entrada de SITE ────────────────────────────────

def ws5_text(counts) -> str:
    """WS5 XML de WissEl con CRLF (único formato que SITE autodetecta)."""
    lines = ['<?xml version="1.0" encoding="UTF-8" standalone="no" ?>',
             '<wissoft version="1.1">',
             '<comment>Banco de validacion Fitbauer</comment>',
             f'<data channels="{len(counts)}" time="0">']
    lines += [str(int(round(c))) for c in counts]
    lines += ['</data>', '</wissoft>', '']
    return "\r\n".join(lines)


def dummy_counts(nchan: int = DEFAULT_NCHAN, base: int = DEFAULT_BASE,
                 dip: float = 0.05, dip_width_ch: float = 12.0) -> np.ndarray:
    """Dummy plano con un valle gaussiano simétrico exactamente en N/2+0.5.

    El valle solo sirve para que la búsqueda del punto de doblado de SITE
    converja al centro exacto (con datos planos no hay mínimo); la curva
    teórica no depende de los datos porque todos los parámetros van fijos.
    """
    i = np.arange(1, nchan + 1, dtype=float)
    center = nchan / 2 + 0.5
    prof = 1.0 - dip * np.exp(-0.5 * ((i - center) / dip_width_ch) ** 2)
    return np.round(base * prof)


def _wrap_items(items: list[str], width: int = 68) -> list[str]:
    """Empaqueta items 'K=V' en líneas ' K1=V1, K2=V2,' de ≤width columnas.

    El lector namelist Fortran de SITE (1992) trunca líneas largas
    (ERROR IN SYNTAX 14 con líneas de >~80 columnas).
    """
    out: list[str] = []
    cur = ""
    for it in items:
        piece = f" {it},"
        if cur and len(cur) + len(piece) > width:
            out.append(cur)
            cur = ""
        cur += piece
    if cur:
        out.append(cur)
    return out


def job_text(stem: str, data_extra: dict, param_lines: list[str],
             title1: str = "Banco validacion", title2: str = "v0") -> str:
    """Fichero JOB de SITE: 4 nombres + &DATA + títulos + &PARAM (CRLF)."""
    data = {"NLTEXT": "4", "TRIANG": ".TRUE.", "MXCFUN": "5000",
            "REMOTE": ".TRUE.", "PLTDAT": ".TRUE.", "PLTSUB": ".TRUE."}
    data.update(data_extra)
    lines = [f"{stem}.MOS", f"{stem}.JOB", f"{stem}.RES", f"{stem}.PLT",
             " &DATA"]
    lines += _wrap_items([f"{k}={v}" for k, v in data.items()])
    lines += [" &END", title1[:70], title2[:70], " &PARAM"]
    for ln in param_lines:
        lines += _wrap_items([p for p in ln.rstrip(",").split(", ") if p])
    lines += [" &END", ""]
    return "\r\n".join(lines)


def site_params(nsub: int, comps: list[dict], extra: list[str] | None = None,
                fit: bool = False) -> list[str]:
    """Líneas &PARAM para nsub subespectros discretos.

    comps[i] admite claves: nline (1/2/6), iso, qua, bhf, wid, dep, d13, d23,
    the, eta, phi (grados según convención SITE), y opcional 'raw' con líneas
    literales adicionales. Todos los parámetros van FIJOS salvo fit=True.
    """
    f = ".TRUE." if fit else ".FALSE."
    out = [f"NSUB={nsub},"]
    for i, c in enumerate(comps, 1):
        out.append(f"NLINE({i})={c.get('nline', 6)},")
        for key, name in (("iso", "ISO"), ("qua", "QUA"), ("bhf", "BHF"),
                          ("wid", "WID"), ("dep", "DEP"), ("d13", "D13"),
                          ("d23", "D23"), ("the", "THE"), ("eta", "ETA"),
                          ("phi", "PHI"), ("w13", "W13"), ("w23", "W23"),
                          ("d21", "D21"), ("w21", "W21"), ("tab", "TAB"),
                          ("d73", "D73")):
            if key in c:
                out.append(f"{name}({i})={c[key]}, {name}FIT({i})={f},")
        for raw in c.get("raw", []):
            out.append(raw)
    if extra:
        out += extra
    return out


# ── Ejecución bajo DOSBox ─────────────────────────────────────────────────────

DIST_EXE = VALID_ROOT / "DIST.EXE"


def run_dosbox_batch(staging: Path, stems: list[str],
                     timeout: float = 900.0, exe: str = "SITE") -> str:
    """Lanza EXE < STEM.JOB para cada caso en un único arranque de DOSBox.

    ``staging`` debe contener el ejecutable y los .MOS/.JOB. DOSBox-staging
    monta el directorio del BAT como C: al pasarle el BAT como argumento
    posicional (receta docs/normos_dosbox_guide.md) y se cierra al terminar
    por el EXIT. Requiere display real (DISPLAY=:0): falla con SDL dummy.
    ``exe``: "SITE" o "DIST" (NORMOS-DIST 09.09.1993, mismo esquema JOB).
    """
    staging = Path(staging)
    src = SITE_EXE if exe == "SITE" else DIST_EXE
    if not (staging / f"{exe}.EXE").exists():
        shutil.copy2(src, staging / f"{exe}.EXE")
    bat = ["@ECHO OFF"]
    bat += [f"{exe} < {s}.JOB" for s in stems]
    bat += ["EXIT", ""]
    (staging / "RUN.BAT").write_bytes("\r\n".join(bat).encode("ascii"))
    env = dict(os.environ, DISPLAY=":0")
    t0 = time.time()
    proc = subprocess.run([DOSBOX, str(staging / "RUN.BAT")],
                          env=env, capture_output=True, text=True,
                          timeout=timeout)
    dt = time.time() - t0
    missing = [s for s in stems if not (staging / f"{s}.PLT").exists()]
    return (f"dosbox rc={proc.returncode} en {dt:.1f}s; "
            f"{len(stems) - len(missing)}/{len(stems)} PLT generados"
            + (f"; FALTAN: {missing}" if missing else ""))


# ── Parseo de salidas de SITE ────────────────────────────────────────────────

def _num_blocks(text: str) -> list[float]:
    nums: list[float] = []
    for line in text.splitlines():
        toks = line.split()
        if not toks:
            continue
        try:
            vals = [float(t) for t in toks]
        except ValueError:
            continue
        nums.extend(vals)
    return nums


def parse_plt(path: Path, np_ch: int | None = None) -> dict:
    """Bloques del .PLT: velocidad, datos, ajuste/teoría y subespectros."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    nums = _num_blocks(text)
    if np_ch is None:
        # NP = tamaño de bloque: probar divisores habituales
        for cand in (1024, 512, 256, 128, 64):
            if len(nums) % cand == 0 and len(nums) >= 3 * cand:
                np_ch = cand
                break
        else:
            raise ValueError(f"PLT con {len(nums)} números: no infiero NP")
    nblocks = len(nums) // np_ch
    arr = np.array(nums[: nblocks * np_ch]).reshape(nblocks, np_ch)
    return {"velocity": arr[0], "data": arr[1], "fit": arr[2],
            "subspectra": [arr[i] for i in range(3, nblocks)],
            "np": np_ch, "nblocks": nblocks}


def parse_res(path: Path) -> dict:
    """Extrae del .RES: punto de doblado, chi2, avisos y eco de parámetros."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    out: dict = {"warnings": []}
    m = re.findall(r"Final folding point\s*=\s*([\d.Ee+-]+)", text)
    if m:
        out["pfp"] = float(m[-1])
    m2 = re.search(r"Chi-square.*?=\s*([\d.Ee+-]+)", text)
    if m2:
        out["chi2"] = float(m2.group(1))
    for line in text.splitlines():
        if (re.search(r"WARNING|ERROR|wrong", line, re.I)
                and "Error (1*STD)" not in line
                and not line.lstrip().startswith(("Sub.", "Index"))):
            out["warnings"].append(line.strip())
    # Tabla de variables (si hubo ajuste): nombre, inicial, final, +- error
    params = {}
    for mm in re.finditer(
            r"^\s*\d+\s+([A-Z]\w*(?:\(\s*\d+\))?)\s+([-.\dEe+]+)\s+"
            r"([-.\dEe+]+)\s+\+-\s+([-.\dEe+]+)", text, re.M):
        params[mm.group(1).replace(" ", "")] = {
            "initial": float(mm.group(2)), "final": float(mm.group(3)),
            "error": float(mm.group(4))}
    out["params"] = params
    return out


# ── Construcción del espectro Fitbauer (sin doblar) ──────────────────────────

def unfold_theory(theory_norm: np.ndarray, base: int = DEFAULT_BASE,
                  rng: np.random.Generator | None = None) -> np.ndarray:
    """Espectro crudo 2N canales, espejo exacto alrededor de N+0.5.

    Con centro N+0.5, el doblado de Fitbauer empareja canales (N-j, N+1+j)
    (1-based) a distancia j+0.5 → reproduce theory_norm exactamente y su
    detección automática de centro encuentra N+0.5 por simetría. El canal
    1 queda a +vmax (drive triangular estándar).
    Con ``rng`` se añade ruido Poisson (v1); sin él, redondeo (v0).
    """
    n = theory_norm.size
    half = np.asarray(theory_norm, dtype=float) * float(base)
    raw = np.empty(2 * n, dtype=float)
    raw[:n] = half[::-1]   # canales 1..N: velocidad +vmax → -vmax
    raw[n:] = half         # canales N+1..2N: -vmax → +vmax
    if rng is not None:
        return rng.poisson(np.maximum(raw, 0.0)).astype(float)
    return np.round(raw)


def write_adt(path: Path, counts: np.ndarray) -> None:
    Path(path).write_text("\n".join(str(int(c)) for c in counts) + "\n",
                          encoding="ascii")


# ── Ajuste headless con Fitbauer ─────────────────────────────────────────────

FIT_KIND = {1: "Singlete", 2: "Doblete", 6: "Sextete"}


def fitbauer_fit(adt_path: Path, comps: list[dict], vmax: float,
                 seed: int = 0, perturb: float = 0.15,
                 free_widths_common: bool = True,
                 line_profile: str = "Lorentziana",
                 quad_treatment: str | None = None,
                 absorber_model: str = "thin",
                 free_intensities: bool = False,
                 multistart_n: int = 4,
                 constraints: list | None = None,
                 kind_override: dict | None = None,
                 extra_model: dict | None = None) -> dict:
    """Ajusta un sintético con la capa headless partiendo de valores perturbados.

    comps: misma lista usada para SITE (claves iso/qua/bhf/wid/dep/nline...).
    La perturbación es determinista (semilla) : ±perturb relativo y
    desplazamientos absolutos en posiciones.
    """
    from core.session import HeadlessSession, ModelState

    rng = np.random.default_rng(seed + 987654321)
    k = len(comps)
    ms = ModelState.defaults(n_components=max(k, 1))
    ms.n_components = k
    ms.multistart_n = multistart_n
    ms.line_profile = line_profile
    ms.absorber_model = absorber_model
    if absorber_model == "thickness":
        # sat_scale (amplitud de saturación C) libre; arranque genérico.
        ms.vars["sat_scale"] = 2.0
        ms.fixed["sat_scale"] = False
    elif absorber_model == "transmission":
        # integral de transmisión: anchura de la fuente libre.
        ms.fixed["src_fwhm"] = False
    if (extra_model or {}).get("free_curv"):
        ms.fixed["curv"] = False
    if (extra_model or {}).get("src_fwhm_fixed") is not None:
        ms.vars["src_fwhm"] = float(extra_model["src_fwhm_fixed"])
        ms.fixed["src_fwhm"] = True
    if constraints:
        ms.constraints = list(constraints)
    if extra_model:
        for key, val in extra_model.items():
            if key not in ("free_curv", "src_fwhm_fixed"):
                setattr(ms, key, val)

    def pert(v, rel=perturb, absmin=0.0):
        span = abs(v) * rel + absmin
        return v + rng.uniform(-span, span)

    for i, c in enumerate(comps, 1):
        kind = FIT_KIND[c.get("nline", 6)]
        if kind_override and i in kind_override:
            kind = kind_override[i]
        ms.sextet_enabled[i] = True
        ms.component_kind[i] = kind
        ms.intensity_mode[i] = "free"
        if quad_treatment and kind == "Sextete":
            ms.quad_treatment[i] = quad_treatment
        v = ms.vars
        v[f"s{i}_delta"] = pert(c.get("iso", 0.0), absmin=0.05)
        v[f"s{i}_quad"] = pert(c.get("qua", 0.0), absmin=0.05)
        v[f"s{i}_gamma1"] = max(0.08, pert(c.get("wid", DEFAULT_WID)))
        v[f"s{i}_depth"] = max(0.001, pert(c.get("dep", DEFAULT_DEP)))
        v[f"s{i}_gamma2"] = 1.0
        v[f"s{i}_gamma3"] = 1.0
        if kind in ("Sextete", "Relajacion", "BlumeTjon"):
            v[f"s{i}_bhf"] = max(0.5, pert(c.get("bhf", 33.0), absmin=0.3))
            v[f"s{i}_int1"] = c.get("d13", 3.0)
            v[f"s{i}_int2"] = c.get("d23", 2.0)
            if "the" in c and quad_treatment in ("kundig_fixed", "hamiltonian"):
                v[f"s{i}_beta"] = float(c["the"])
            if quad_treatment == "hamiltonian":
                v[f"s{i}_eta"] = float(c.get("eta", 0.0))
                v[f"s{i}_phi"] = float(c.get("phi", 0.0))
                ms.fixed[f"s{i}_eta"] = True
                ms.fixed[f"s{i}_phi"] = True
        elif kind == "Doblete":
            v[f"s{i}_int2"] = 1.0
        # Fijar lo no ajustado: anchuras acopladas e intensidades nominales
        ms.fixed[f"s{i}_gamma2"] = free_widths_common
        ms.fixed[f"s{i}_gamma3"] = free_widths_common
        ms.fixed[f"s{i}_int1"] = not free_intensities
        ms.fixed[f"s{i}_int2"] = not free_intensities
        if kind == "Doblete" and not free_intensities:
            ms.fixed[f"s{i}_int2"] = True
        ms.fixed[f"s{i}_beta"] = True

    sess = HeadlessSession(ms)
    sess.load_ws5(Path(adt_path), vmax=vmax)
    t0 = time.time()
    try:
        res = sess.run_fit()
        res["fit_seconds"] = time.time() - t0
        res["center"] = sess.spectrum.center
        res["converged"] = True
    except Exception as exc:
        res = {"converged": False, "error": f"{type(exc).__name__}: {exc}",
               "fit_seconds": time.time() - t0}
    return res
