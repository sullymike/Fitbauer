#!/usr/bin/env python3
"""Extrae el cuerpo de los manuales matemáticos de docs/ a docs/manual/appendices/.

Los manuales matemáticos (docs/*.tex) son documentos LaTeX \emph{autónomos}. Para
anexarlos al manual de usuario se copia solo su \emph{cuerpo} (entre
``\\begin{document}`` y ``\\end{document}``), sin preámbulo, sin ``\\maketitle`` ni
índice, y —en el manual matemático principal, que usa ``\\part``— bajando un nivel
la jerarquía de secciones para que anide bajo el ``\\chapter`` del apéndice.

Las macros que usan esos cuerpos (``\\BHF``, ``\\dEQ``, ``\\code``, ``\\file``,
``\\diag``…) están declaradas en el preámbulo de ``main.tex``.

Uso (desde docs/manual/):  python scripts/make_appendices.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]      # docs/manual/
DOCS = ROOT.parent                              # docs/
OUT = ROOT / "appendices"

# fuente (en docs/) -> nombre del cuerpo (en appendices/)
SOURCES = {
    "manual_mossbauer": "apx_mates",
    "distribuciones_is_mossbauer": "apx_dist_is",
    "distribuciones_2d_mossbauer": "apx_dist_2d",
    "relajacion_mossbauer": "apx_relax",
    "correccion_espesor": "apx_espesor",
}
# manuales que usan \part como nivel superior (hay que bajar un nivel)
USES_PART = {"manual_mossbauer"}


def extract_body(tex: str, downgrade: bool) -> str:
    m = re.search(r"\\begin\{document\}(.*)\\end\{document\}", tex, re.S)
    if not m:
        raise ValueError("no se encontró \\begin{document}…\\end{document}")
    body = m.group(1)
    body = re.sub(r"\\maketitle", "", body)
    body = re.sub(r"\\tableofcontents", "", body)
    body = re.sub(r"\\thispagestyle\{[^}]*\}", "", body)
    body = body.replace(r"\begin{abstract}", "").replace(r"\end{abstract}", "")
    if downgrade:
        # deepest-first: subsection->subsubsection, section->subsection, part->section
        body = re.sub(r"\\subsection(\*?)\{", r"\\subsubsection\1{", body)
        body = re.sub(r"\\section(\*?)\{", r"\\subsection\1{", body)
        body = re.sub(r"\\part(\*?)\{", r"\\section\1{", body)
        body = re.sub(r"\n\\appendix\b", "\n", body)  # sin \appendix anidado
    return body.strip("\n") + "\n"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for src, out in SOURCES.items():
        tex = (DOCS / f"{src}.tex").read_text(encoding="utf-8")
        body = extract_body(tex, downgrade=src in USES_PART)
        (OUT / f"{out}.tex").write_text(body, encoding="utf-8")
        print(f"  {src}.tex -> appendices/{out}.tex")
    print("Cuerpos de anexos regenerados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
