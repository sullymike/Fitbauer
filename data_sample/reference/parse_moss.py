#!/usr/bin/env python3
"""Parser de la tabla HTML de referencia MossTool → JSON + CSV estructurados.

Lee /tmp/moss_table.html (la tabla <table id="myTable"> tal cual) y emite un
dataset limpio de parámetros Mössbauer de referencia (IS, QS, Bhf) con su
procedencia bibliográfica.
"""
from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "source_mosstool.html"
OUT_DIR = HERE
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Arreglo de mojibake (� = carácter de reemplazo por ü/ö perdido en latin-1).
MOJIBAKE = {
    "W�stite": "Wüstite",
    "R�merite": "Römerite",
    "Ulv�spinel": "Ulvöspinel",
}


def fix_text(s: str) -> str:
    s = html.unescape(s)
    for bad, good in MOJIBAKE.items():
        s = s.replace(bad, good)
    # Reemplazo genérico restante: � entre letras suele ser ü u ö.
    return s.strip()


def strip_tags(cell: str) -> str:
    # Sub-índices <sub>..</sub> → quitar etiqueta, conservar contenido.
    cell = re.sub(r"<sub>(.*?)</sub>", r"\1", cell, flags=re.S | re.I)
    cell = re.sub(r"<[^>]+>", "", cell)
    return fix_text(cell)


def parse_ref(cell: str) -> tuple[str, str]:
    """Devuelve (texto_referencia, url)."""
    m = re.search(r'href="([^"]*)"', cell)
    url = m.group(1) if m else ""
    if url == "0":
        url = ""
    text = strip_tags(cell)
    return text, url


def num(s: str):
    s = s.strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main() -> None:
    raw = SRC.read_text(encoding="utf-8", errors="replace")
    rows = re.findall(r"<tr>(.*?)</tr>", raw, flags=re.S | re.I)
    records: list[dict] = []
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S | re.I)
        if len(cells) < 14:
            continue
        # Saltar la fila de cabecera (contiene <button> o "Sample").
        if "Sample" in cells[0] and "button" in row:
            continue
        sample = strip_tags(cells[0])
        if not sample or sample.lower() == "sample":
            continue
        site_raw = strip_tags(cells[11])  # p.ej. "1(3)" → site 1 de 3
        m_site = re.match(r"(\d+)\((\d+)\)", site_raw)
        site = int(m_site.group(1)) if m_site else None
        site_total = int(m_site.group(2)) if m_site else None
        ref_text, ref_url = parse_ref(cells[13])
        records.append({
            "sample": sample,
            "class": strip_tags(cells[1]),
            "type": strip_tags(cells[2]),
            "oxidation_state": strip_tags(cells[3]),
            "T_K": num(strip_tags(cells[4])),
            "IS_mm_s": num(strip_tags(cells[5])),
            "IS_err": num(strip_tags(cells[6])),
            "QS_mm_s": num(strip_tags(cells[7])),
            "QS_err": num(strip_tags(cells[8])),
            "Bhf_T": num(strip_tags(cells[9])),
            "Bhf_err": num(strip_tags(cells[10])),
            "site": site,
            "site_total": site_total,
            "model": strip_tags(cells[12]),
            "reference": ref_text,
            "reference_url": ref_url,
        })

    # JSON
    (OUT_DIR / "mossbauer_reference.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    # CSV (TSV)
    fields = ["sample", "class", "type", "oxidation_state", "T_K",
              "IS_mm_s", "IS_err", "QS_mm_s", "QS_err", "Bhf_T", "Bhf_err",
              "site", "site_total", "model", "reference", "reference_url"]
    with (OUT_DIR / "mossbauer_reference.tsv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
        w.writeheader()
        for r in records:
            w.writerow({k: ("" if r[k] is None else r[k]) for k in fields})

    # Resumen
    n = len(records)
    samples = sorted({r["sample"] for r in records})
    classes = sorted({r["class"] for r in records if r["class"]})
    refs = sorted({r["reference"] for r in records if r["reference"]})
    print(f"Registros: {n}")
    print(f"Muestras únicas: {len(samples)}")
    print(f"Clases: {len(classes)} -> {classes}")
    print(f"Referencias: {len(refs)}")
    with_bhf = sum(1 for r in records if r["Bhf_T"] is not None)
    print(f"Con Bhf: {with_bhf} | solo IS/QS (paramagnéticos): {n - with_bhf}")


if __name__ == "__main__":
    main()
