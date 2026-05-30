"""Helpers puros para el ajuste en serie (Capa 1: encadenado por warm-start).

No tienen dependencias de GUI/Tk; viven aquí para poder probarlos sin display.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable


def extract_metadata(name: str, pattern: str) -> float | str | None:
    """Extrae un valor numérico (o de texto) del nombre del fichero.

    Si el patrón usa un grupo nombrado ``(?P<v>...)`` o cualquier grupo
    capturador, se devuelve el primer grupo capturado como float si convertible;
    si no, como cadena. Devuelve ``None`` si no hay coincidencia o si el
    patrón es inválido.
    """
    if not pattern:
        return None
    try:
        rx = re.compile(pattern)
    except re.error:
        return None
    m = rx.search(name)
    if not m:
        return None
    try:
        text = m.group("v")
    except (IndexError, KeyError):
        text = m.group(1) if m.groups() else m.group(0)
    text = text.strip()
    try:
        return float(text)
    except ValueError:
        return text


def write_results_csv(path: Path, free_keys: Iterable[str],
                      rows: list[dict]) -> None:
    """Escribe un CSV con una fila por espectro.

    Cabeceras: ``file``, ``metadata``, ``status``, ``chi2``, ``red_chi2``,
    y para cada parámetro libre ``<key>`` y ``<key>_err``.
    """
    free_keys = list(free_keys)
    headers = ["file", "metadata", "status", "chi2", "red_chi2"]
    for k in free_keys:
        headers.append(k)
        headers.append(f"{k}_err")
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(headers)
        for row in rows:
            values = row.get("values", {})
            errors = row.get("errors", {})
            stats = row.get("stats", {})
            line: list = [
                row.get("file", ""),
                row.get("metadata", ""),
                row.get("status", ""),
                stats.get("chi2", ""),
                stats.get("red_chi2", ""),
            ]
            for k in free_keys:
                line.append(values.get(k, ""))
                line.append(errors.get(k, ""))
            writer.writerow(line)


def collect_trend_data(rows: list[dict], free_keys: Iterable[str]
                       ) -> dict[str, list[tuple[float, float, float | None]]]:
    """Para cada parámetro libre, devuelve [(metadata, value, error), ...]
    solo de las filas con status OK y metadato numérico, ordenadas por metadato.
    """
    trend: dict[str, list[tuple[float, float, float | None]]] = {}
    for k in free_keys:
        points: list[tuple[float, float, float | None]] = []
        for row in rows:
            if row.get("status") != "ok":
                continue
            meta = row.get("metadata")
            if not isinstance(meta, (int, float)):
                continue
            val = row.get("values", {}).get(k)
            if val is None:
                continue
            err = row.get("errors", {}).get(k)
            points.append((float(meta), float(val), float(err) if err else None))
        points.sort(key=lambda p: p[0])
        if points:
            trend[k] = points
    return trend
