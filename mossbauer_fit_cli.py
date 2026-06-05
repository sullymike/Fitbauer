#!/usr/bin/env python3
"""Ajuste Mössbauer desde línea de comandos: una plantilla + un espectro → un fichero de resultado.

Uso típico:

    python mossbauer_fit_cli.py \
        --template plantilla.json \
        --spectrum medida.adt \
        --out medida.fit.json

La plantilla es un fichero de sesión generado por la GUI (Archivo ▸ Guardar
sesión...). Aporta los parámetros iniciales del modelo (vars, fixed, tipos de
componente, perfil de línea, etc.). El centro de folding se detecta para cada
espectro automáticamente (la plantilla no impone el suyo).

Para recorrer muchos ficheros se invoca este script desde shell o desde otro
proceso, por ejemplo::

    for f in data/*.adt; do
        python mossbauer_fit_cli.py --template T.json --spectrum "$f" \
            --out "results/$(basename "$f" .adt).fit.json"
    done

El proceso es completamente headless: no necesita ningún display ni Tk. Se
apoya en ``core.session.HeadlessSession`` (la misma numérica que usan ambas
GUIs a través de ``core.fit_engine``)::

    python mossbauer_fit_cli.py --template T.json --spectrum a.adt --out a.fit.json

Salida: el .json escrito contiene la misma estructura que una sesión guardada
desde la GUI (``session_payload``) más una sección ``batch_fit_result`` con
los valores y errores del último ajuste.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def fit_spectrum(template_path: Path, spectrum_path: Path,
                 output_path: Path | None = None,
                 vmax: float | None = None) -> dict:
    """Carga plantilla + espectro, ejecuta el ajuste y devuelve la sesión final.

    Si ``output_path`` no es None se guarda allí el JSON resultado. Lanza
    ``FileNotFoundError`` si los ficheros no existen y propaga cualquier otra
    excepción del motor de ajuste.
    """
    import numpy as np
    if not hasattr(np, "trapezoid"):
        np.trapezoid = np.trapz  # type: ignore[attr-defined]

    if not template_path.exists():
        raise FileNotFoundError(f"Plantilla no encontrada: {template_path}")
    if not spectrum_path.exists():
        raise FileNotFoundError(f"Espectro no encontrado: {spectrum_path}")

    with template_path.open("r", encoding="utf-8") as fh:
        template = json.load(fh)
    state = template.get("model_state", template)

    from core.session import HeadlessSession
    session_engine = HeadlessSession()
    session_engine.load_ws5(spectrum_path)
    session_engine.apply_template_model_state(state)
    # --vmax sobrescribe el de la plantilla (útil si la calibración varía).
    if vmax is not None:
        session_engine.set_vmax(vmax)
    fit_result = session_engine.run_fit()
    session = session_engine.session_payload()
    session["batch_fit_result"] = {
        "spectrum": str(spectrum_path),
        "template": str(template_path),
        "values": fit_result["values"],
        "errors": fit_result["errors"],
        "stats": fit_result["stats"],
        "free_keys": fit_result["free_keys"],
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(session, fh, indent=2, default=str, ensure_ascii=False)
    return session


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--template", required=True, type=Path,
                   help="Fichero .json de sesión que sirve como plantilla.")
    p.add_argument("--spectrum", required=True, type=Path,
                   help="Espectro .ws5 o .adt a ajustar.")
    p.add_argument("--out", required=True, type=Path,
                   help="Fichero .json donde escribir el resultado.")
    p.add_argument("--vmax", type=float, default=None,
                   help="Sobrescribe vmax (mm/s) — útil si la calibración varía.")
    p.add_argument("--quiet", action="store_true",
                   help="No imprimir el resumen por stdout (solo código de salida).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        session = fit_spectrum(args.template, args.spectrum, args.out, args.vmax)
    except Exception as exc:
        print(f"FAIL  {args.spectrum.name}  {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1
    if not args.quiet:
        result = session.get("batch_fit_result", {})
        stats = result.get("stats", {})
        chi2 = stats.get("chi2")
        red = stats.get("red_chi2")
        chi2_txt = f"{chi2:.6g}" if isinstance(chi2, (int, float)) else "?"
        red_txt = f"{red:.6g}" if isinstance(red, (int, float)) else "?"
        print(f"OK  {args.spectrum.name}  χ²={chi2_txt}  red_χ²={red_txt}")
        for k, v in result.get("values", {}).items():
            err = result.get("errors", {}).get(k)
            err_txt = f" ± {err:.4g}" if isinstance(err, (int, float)) and err else ""
            print(f"  {k} = {v:.6g}{err_txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
