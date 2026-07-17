#!/usr/bin/env python3
"""Ajuste Mössbauer desde línea de comandos: una plantilla + espectros → ficheros de resultado.

Uso típico:

    python mossbauer_fit_cli.py \
        --template plantilla.json \
        --spectrum medida.adt \
        --out medida.fit.json

La plantilla es un fichero de sesión generado por la GUI (Archivo ▸ Guardar
sesión...). Aporta los parámetros iniciales del modelo (vars, fixed, tipos de
componente, perfil de línea, etc.). El centro de folding se detecta para cada
espectro automáticamente (la plantilla no impone el suyo).

Errores avanzados (opcionales, mismo motor que la GUI):

    --bootstrap N           errores por remuestreo Monte Carlo (N réplicas)
    --profile-likelihood    intervalos asimétricos 1σ/2σ por verosimilitud
                            perfilada (cruces Δχ²=1 y Δχ²=4)

Serie con warm-start: si se pasan varios espectros, cada ajuste parte de los
valores convergidos del anterior (``HeadlessSession.batch_fit_sequential``,
igual que el batch de la GUI) y ``--out`` recibe un único JSON con una fila
por fichero::

    python mossbauer_fit_cli.py --template T.json \
        --spectrum serie_010K.adt serie_050K.adt serie_100K.adt \
        --out serie.batch.json

El proceso es completamente headless: no necesita ningún display ni Tk. Se
apoya en ``core.session.HeadlessSession`` (la misma numérica que usa la GUI
a través de ``core.fit_engine``).

Salida (un espectro): el .json escrito contiene la misma estructura que una
sesión guardada desde la GUI (``session_payload``) más una sección
``batch_fit_result`` con los valores y errores del último ajuste, y, si se
pidieron, ``bootstrap`` y ``profile_likelihood``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_template_state(template_path: Path) -> dict:
    if not template_path.exists():
        raise FileNotFoundError(f"Plantilla no encontrada: {template_path}")
    with template_path.open("r", encoding="utf-8") as fh:
        template = json.load(fh)
    return template.get("model_state", template)


def _write_json(output_path: Path, payload: dict | list) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str, ensure_ascii=False)


def fit_spectrum(template_path: Path, spectrum_path: Path,
                 output_path: Path | None = None,
                 vmax: float | None = None, *,
                 bootstrap_n: int = 0,
                 profile: bool = False) -> dict:
    """Carga plantilla + espectro, ejecuta el ajuste y devuelve la sesión final.

    Si ``output_path`` no es None se guarda allí el JSON resultado. Lanza
    ``FileNotFoundError`` si los ficheros no existen y propaga cualquier otra
    excepción del motor de ajuste. Con ``bootstrap_n>0`` añade la sección
    ``bootstrap`` (σ Monte Carlo por parámetro libre); con ``profile=True``,
    la sección ``profile_likelihood`` (intervalos asimétricos 1σ/2σ).
    """
    import numpy as np
    if not hasattr(np, "trapezoid"):
        np.trapezoid = np.trapz  # type: ignore[attr-defined]

    if not spectrum_path.exists():
        raise FileNotFoundError(f"Espectro no encontrado: {spectrum_path}")
    state = _load_template_state(template_path)

    from core.session import HeadlessSession
    session_engine = HeadlessSession()
    # La plantilla se aplica ANTES de cargar: load_ws5 decide doblar (triangular)
    # o no doblar (seno) según drive_form, que viene de la plantilla.
    session_engine.apply_template_model_state(state)
    session_engine.load_ws5(spectrum_path)
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
    # Errores avanzados sobre el estado ya convergido (run_fit vuelca los
    # valores ajustados en el modelo, así que el ajuste base interno de
    # bootstrap/perfil arranca en el óptimo).
    if bootstrap_n > 0 or profile:
        fit_state = session_engine.build_fit_state()
    if bootstrap_n > 0:
        from core.fit_engine import bootstrap_errors
        bs = bootstrap_errors(fit_state, n_rep=int(bootstrap_n))
        session["bootstrap"] = {
            "n_rep": bs.n_rep,
            "n_ok": bs.n_ok,
            "std": {k: float(v) for k, v in bs.std.items()},
        }
    if profile:
        from core.fit_engine import profile_likelihood
        prof = profile_likelihood(fit_state)
        session["profile_likelihood"] = {
            key: {
                "best": res.get("best"),
                "minus_1s": res.get("minus_1s"),
                "plus_1s": res.get("plus_1s"),
                "minus_2s": res.get("minus_2s"),
                "plus_2s": res.get("plus_2s"),
            }
            for key, res in prof.items()
        }
    if output_path is not None:
        _write_json(output_path, session)
    return session


def fit_batch(template_path: Path, spectrum_paths: list[Path],
              output_path: Path | None = None,
              vmax: float | None = None) -> list[dict]:
    """Ajusta una serie de espectros con warm-start secuencial.

    Cada espectro parte de los valores convergidos del anterior (espejo del
    batch de la GUI, ``HeadlessSession.batch_fit_sequential``). Devuelve una
    fila por fichero con ``status``/``values``/``errors``/``stats``; los
    fallos individuales no detienen la serie.
    """
    import numpy as np
    if not hasattr(np, "trapezoid"):
        np.trapezoid = np.trapz  # type: ignore[attr-defined]

    missing = [p for p in spectrum_paths if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Espectros no encontrados: " + ", ".join(str(p) for p in missing))
    state = _load_template_state(template_path)

    from core.session import HeadlessSession
    session_engine = HeadlessSession()
    session_engine.apply_template_model_state(state)
    if vmax is not None:
        session_engine.set_vmax(vmax)
    rows = session_engine.batch_fit_sequential(spectrum_paths)
    payload = {
        "template": str(template_path),
        "spectra": [str(p) for p in spectrum_paths],
        "results": rows,
    }
    if output_path is not None:
        _write_json(output_path, payload)
    return rows


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--template", required=True, type=Path,
                   help="Fichero .json de sesión que sirve como plantilla.")
    p.add_argument("--spectrum", required=True, type=Path, nargs="+",
                   help="Espectro(s) .ws5 o .adt a ajustar. Con varios, serie "
                        "con warm-start secuencial y un único JSON de salida.")
    p.add_argument("--out", required=True, type=Path,
                   help="Fichero .json donde escribir el resultado.")
    p.add_argument("--vmax", type=float, default=None,
                   help="Sobrescribe vmax (mm/s) — útil si la calibración varía.")
    p.add_argument("--bootstrap", type=int, default=0, metavar="N",
                   help="Errores por remuestreo Monte Carlo con N réplicas "
                        "(solo con un espectro).")
    p.add_argument("--profile-likelihood", action="store_true",
                   help="Intervalos asimétricos 1σ/2σ por verosimilitud "
                        "perfilada (solo con un espectro).")
    p.add_argument("--quiet", action="store_true",
                   help="No imprimir el resumen por stdout (solo código de salida).")
    return p


def _print_single_summary(args, session: dict) -> None:
    result = session.get("batch_fit_result", {})
    stats = result.get("stats", {})
    chi2 = stats.get("chi2")
    red = stats.get("red_chi2")
    chi2_txt = f"{chi2:.6g}" if isinstance(chi2, (int, float)) else "?"
    red_txt = f"{red:.6g}" if isinstance(red, (int, float)) else "?"
    print(f"OK  {args.spectrum[0].name}  χ²={chi2_txt}  red_χ²={red_txt}")
    bs_std = session.get("bootstrap", {}).get("std", {})
    prof = session.get("profile_likelihood", {})
    for k, v in result.get("values", {}).items():
        err = result.get("errors", {}).get(k)
        err_txt = f" ± {err:.4g}" if isinstance(err, (int, float)) and err else ""
        extra = ""
        if k in bs_std:
            extra += f"  [σ_MC {bs_std[k]:.4g}]"
        if k in prof:
            # minus_1s/plus_1s son distancias positivas desde el óptimo.
            lo, hi = prof[k].get("minus_1s"), prof[k].get("plus_1s")
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
                extra += f"  [1σ perfil −{lo:.4g}/+{hi:.4g}]"
        print(f"  {k} = {v:.6g}{err_txt}{extra}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if len(args.spectrum) > 1:
        if args.bootstrap or args.profile_likelihood:
            print("FAIL  --bootstrap/--profile-likelihood solo admiten un espectro",
                  file=sys.stderr)
            return 2
        try:
            rows = fit_batch(args.template, args.spectrum, args.out, args.vmax)
        except Exception as exc:
            print(f"FAIL  batch  {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        n_ok = sum(1 for r in rows if r.get("status") == "ok")
        if not args.quiet:
            for r in rows:
                if r.get("status") == "ok":
                    red = r.get("stats", {}).get("red_chi2")
                    red_txt = f"{red:.6g}" if isinstance(red, (int, float)) else "?"
                    print(f"OK    {r['file']}  red_χ²={red_txt}")
                else:
                    print(f"FAIL  {r['file']}  {r.get('error', '?')}")
            print(f"Serie: {n_ok}/{len(rows)} ajustes correctos → {args.out}")
        return 0 if n_ok == len(rows) else 1
    try:
        session = fit_spectrum(args.template, args.spectrum[0], args.out, args.vmax,
                               bootstrap_n=args.bootstrap,
                               profile=args.profile_likelihood)
    except Exception as exc:
        print(f"FAIL  {args.spectrum[0].name}  {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1
    if not args.quiet:
        _print_single_summary(args, session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
