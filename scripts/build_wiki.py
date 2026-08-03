#!/usr/bin/env python3
"""Genera el wiki de GitHub a partir de la documentación del repositorio.

El wiki de GitHub vive en un repositorio git aparte (``Fitbauer.wiki.git``) y no
admite pull requests, así que escribirlo a mano garantiza que acabe divergiendo
del código. Este script lo genera desde ``docs/`` y los README/INSTALL, que son
la fuente de verdad, de modo que regenerarlo sea siempre reproducible.

Uso::

    git clone github-mossbauer:sullymike/Fitbauer.wiki.git /ruta/wiki
    python scripts/build_wiki.py --out /ruta/wiki
    cd /ruta/wiki && git add -A && git commit -m "..." && git push

Las páginas generadas llevan una cabecera que remite al fichero de origen: si
alguien edita el wiki en el navegador, el siguiente build sobrescribe el cambio.
Eso es intencionado — se corrige en ``docs/``.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.constants import APP_VERSION  # noqa: E402

REPO_URL = "https://github.com/sullymike/Fitbauer"
BLOB = f"{REPO_URL}/blob/main"
# El wiki no sirve sus propios ficheros como estáticos: una ruta relativa
# ``img/x.png`` se resuelve contra /wiki/ y da un enlace roto. Las imágenes se
# referencian en crudo desde el repositorio principal, que además evita
# duplicarlas.
RAW = "https://raw.githubusercontent.com/sullymike/Fitbauer/main"


@dataclass(frozen=True)
class Page:
    """Una página del wiki. ``source`` None ⇒ contenido generado."""

    name: str            # nombre de fichero sin .md → título de la página
    title: str           # texto en la barra lateral
    lang: str            # "en" | "es"
    source: str | None   # ruta relativa a la raíz del repo
    section: str         # agrupación en la barra lateral


# Orden = orden en la barra lateral. Los pares ES/EN comparten sección.
PAGES: list[Page] = [
    # ── Inglés ───────────────────────────────────────────────────────────────
    Page("Home", "Home", "en", None, "Start"),
    Page("Installation", "Installation", "en", "INSTALL_EN.md", "Start"),
    Page("User-flows", "User flows", "en", "docs/user-flows_en.md", "Start"),
    Page("Folding", "Folding", "en", "docs/folding_en.md", "Data"),
    Page("Calibration-33T", "Calibration (33 T)", "en", "docs/calibration_33T.md", "Data"),
    Page("Spectrum-comparison", "Spectrum comparison", "en", "docs/spectrum_comparison.md", "Data"),
    Page("Distribution-fitting", "Distribution fitting", "en", "BHF_DISTRIBUTION_EN.md", "Fitting"),
    Page("Peak-detection", "Peak detection", "en", "docs/peak_detection.md", "Fitting"),
    Page("Profile-likelihood", "Profile likelihood", "en", "docs/profile_likelihood.md", "Fitting"),
    Page("Batch-fitting", "Batch fitting", "en", "docs/batch_fit.md", "Fitting"),
    Page("Command-line-tools", "Command-line tools", "en", None, "Reference"),
    Page("NORMOS-interoperability", "NORMOS (.JOB)", "en", "docs/normos_job_en.md", "Reference"),
    Page("Session-format", "Session format", "en", "docs/session_format.md", "Reference"),
    Page("Sextet-model", "Sextet model (spec)", "en", "docs/sextet_model.md", "Reference"),
    Page("Architecture", "Architecture", "en", "docs/architecture_en.md", "Reference"),
    # ── Español ──────────────────────────────────────────────────────────────
    Page("ES-Inicio", "Inicio", "es", None, "Inicio"),
    Page("ES-Instalacion", "Instalación", "es", "INSTALL.md", "Inicio"),
    Page("ES-Flujos-de-usuario", "Flujos de usuario", "es", "docs/user-flows.md", "Inicio"),
    Page("ES-Plegado", "Plegado (folding)", "es", "docs/folding.md", "Datos"),
    Page("ES-Calibracion-33T", "Calibración (33 T)", "es", "docs/calibracion_33T.md", "Datos"),
    Page("ES-Comparacion-de-espectros", "Comparación de espectros", "es", "docs/comparacion_espectros.md", "Datos"),
    Page("ES-Distribuciones", "Distribuciones", "es", "BHF_DISTRIBUTION.md", "Ajuste"),
    Page("ES-Deteccion-de-minimos", "Detección de mínimos", "es", "docs/deteccion_minimos.md", "Ajuste"),
    Page("ES-Verosimilitud-perfilada", "Verosimilitud perfilada", "es", "docs/perfil_verosimilitud.md", "Ajuste"),
    Page("ES-Ajuste-en-serie", "Ajuste en serie", "es", "docs/ajuste_batch.md", "Ajuste"),
    Page("ES-Linea-de-comandos", "Línea de comandos", "es", None, "Referencia"),
    Page("ES-NORMOS-interoperabilidad", "NORMOS (.JOB)", "es", "docs/normos_job.md", "Referencia"),
    Page("ES-Formato-de-sesion", "Formato de sesión", "es", "docs/formato_sesion.md", "Referencia"),
    Page("ES-Modelo-de-sextete", "Modelo de sextete (spec)", "es", "docs/modelo_sextete.md", "Referencia"),
    Page("ES-Arquitectura", "Arquitectura", "es", "docs/architecture.md", "Referencia"),
]

# Documentos deliberadamente excluidos, con su motivo. Los manuales LaTeX no se
# convierten: 80 páginas con ecuaciones y referencias cruzadas quedan peor en
# Markdown que en PDF, así que se enlazan.
EXCLUDED = {
    "docs/plan_pbhf_mejoras.md": "plan de desarrollo interno",
    "docs/plotly.md": "referencia histórica de una integración retirada (v4.13.1)",
    "docs/modelos_relajacion_mossbauer.md": "marcado como ARCHIVO HISTÓRICO",
    "docs/release_notes_v4.16.0.md": "duplica RELEASE_NOTES_v4.16.0.md",
    "docs/article_hyperfine_interactions.md": "borrador de artículo, no documentación de usuario",
    # Se publicó en el wiki hasta v5.0.0 y se retiró: se autodescribe como
    # referencia INTERNA, era la única página con rutas locales del autor
    # (/home/jorge/...) y la única sin par en inglés. Sigue en docs/ para quien
    # clone el repositorio, que es su público real.
    "docs/normos_dosbox_guide.md": "guía de trabajo interna con rutas locales",
}

BANNER = {
    "en": ("> ⚙️ **Generated page** — do not edit here. Source: [`{src}`]({blob}/{src}). "
           "Edit it in the repository and the wiki rebuilds itself."),
    "es": ("> ⚙️ **Página generada** — no la edites aquí. Origen: [`{src}`]({blob}/{src}). "
           "Corrígela en el repositorio y el wiki se regenera solo."),
}


def source_to_page() -> dict[str, str]:
    """Mapa ruta-de-origen → nombre de página, para reescribir enlaces."""
    return {p.source: p.name for p in PAGES if p.source}


def rewrite_links(text: str, mapping: dict[str, str]) -> str:
    """Adapta enlaces e imágenes del repositorio al espacio plano del wiki."""
    # Las rutas relativas del repo no resuelven desde el wiki: las imágenes van
    # al raw del repositorio y el resto de ficheros al blob de GitHub.
    text = text.replace("docs/img/", f"{RAW}/docs/img/")
    text = re.sub(r'(<img\s+[^>]*src=")(?!https?:)([^"]+)(")',
                  rf'\1{RAW}/\2\3', text)

    def _link(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        if target.startswith(("http://", "https://", "#", "mailto:")):
            return match.group(0)
        clean = target.split("#", 1)[0]
        # Un documento que también es página del wiki → enlace interno.
        for src, page in mapping.items():
            if clean == src or clean == Path(src).name:
                return f"[{label}]({page})"
        return f"[{label}]({BLOB}/{clean.lstrip('./')})"

    return re.sub(r'\[([^\]]*)\]\(([^)]+)\)', _link, text)


def cli_help(script: str) -> str:
    """Captura la ayuda de un CLI; es la única fuente que no puede mentir."""
    proc = subprocess.run([sys.executable, str(ROOT / script), "--help"],
                          capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"{script} --help falló:\n{proc.stderr}")
    return proc.stdout.rstrip()


def page_cli(lang: str) -> str:
    """Página de línea de comandos, con la ayuda real de ambos CLIs."""
    if lang == "en":
        head = (
            "# Command-line tools\n\n"
            "Fitbauer fits without a display: both CLIs drive the same engines as the GUI\n"
            f"(`core/`), so results are identical. Full reference with worked examples in the\n"
            f"[English manual]({BLOB}/docs/manual_en/main.pdf), appendix *Command-line tools*.\n\n"
            "## Discrete fitting — `mossbauer_fit_cli.py`\n\n"
            "Takes a session template saved from the GUI (**File ▸ Save session…**) plus one or\n"
            "more spectra. With several spectra it runs a warm-start series, each fit starting\n"
            "from the previous converged values.\n\n"
            "```bash\n"
            "python mossbauer_fit_cli.py --template template.json \\\n"
            "    --spectrum sample.adt --out sample.fit.json\n\n"
            "# Monte Carlo errors and asymmetric profile-likelihood intervals\n"
            "python mossbauer_fit_cli.py --template template.json --spectrum sample.adt \\\n"
            "    --out sample.fit.json --bootstrap 200 --profile-likelihood\n"
            "```\n\n"
            "<details><summary>Full options</summary>\n\n```text\n{help1}\n```\n</details>\n\n"
            "## Distribution fitting — `fit_bhf_distribution_cli.py`\n\n"
            "Covers the same modes as the GUI: `P(BHF)` and `P(ΔEQ)`, histogram / Gaussian / VBF\n"
            "/ binomial shapes, Tikhonov / TV / MaxEnt regularization, Voigt kernels, δ(H) and\n"
            "ΔEQ(H) correlations, and 2D distributions.\n\n"
            "```bash\n"
            "python fit_bhf_distribution_cli.py sample.ws5 --bmin 0 --bmax 50 --nbins 50 \\\n"
            "    --gamma 0.18 --alpha 0.01 --plot --scan-alpha\n\n"
            "# P(ΔEQ) with fixed BHF (0 = doublet); VBF shape; maximum entropy\n"
            "python fit_bhf_distribution_cli.py sample.adt --variable quad --bmax 3\n"
            "python fit_bhf_distribution_cli.py sample.adt --shape vbf --vbf-components 2\n"
            "python fit_bhf_distribution_cli.py sample.adt --reg-mode maxent\n"
            "```\n\n"
            "<details><summary>Full options</summary>\n\n```text\n{help2}\n```\n</details>\n\n"
            "See also: [Distribution fitting](Distribution-fitting) · [Batch fitting](Batch-fitting)\n"
        )
    else:
        head = (
            "# Línea de comandos\n\n"
            "Fitbauer ajusta sin necesidad de display: ambos CLIs usan los mismos motores que la\n"
            f"GUI (`core/`), así que los resultados son idénticos. Referencia completa con ejemplos\n"
            f"en el [manual en inglés]({BLOB}/docs/manual_en/main.pdf), apéndice *Command-line tools*.\n\n"
            "## Ajuste discreto — `mossbauer_fit_cli.py`\n\n"
            "Parte de una plantilla de sesión guardada desde la GUI (**Archivo ▸ Guardar sesión…**)\n"
            "y uno o más espectros. Con varios espectros ejecuta una serie con warm-start: cada\n"
            "ajuste arranca en los valores convergidos del anterior.\n\n"
            "```bash\n"
            "python mossbauer_fit_cli.py --template plantilla.json \\\n"
            "    --spectrum medida.adt --out medida.fit.json\n\n"
            "# Errores Monte Carlo e intervalos asimétricos por verosimilitud perfilada\n"
            "python mossbauer_fit_cli.py --template plantilla.json --spectrum medida.adt \\\n"
            "    --out medida.fit.json --bootstrap 200 --profile-likelihood\n"
            "```\n\n"
            "<details><summary>Todas las opciones</summary>\n\n```text\n{help1}\n```\n</details>\n\n"
            "## Ajuste de distribuciones — `fit_bhf_distribution_cli.py`\n\n"
            "Cubre los mismos modos que la GUI: `P(BHF)` y `P(ΔEQ)`, formas histograma / gaussiana\n"
            "/ VBF / binomial, regularización Tikhonov / TV / MaxEnt, kernel Voigt, correlaciones\n"
            "δ(H) y ΔEQ(H), y distribuciones 2D.\n\n"
            "```bash\n"
            "python fit_bhf_distribution_cli.py muestra.ws5 --bmin 0 --bmax 50 --nbins 50 \\\n"
            "    --gamma 0.18 --alpha 0.01 --plot --scan-alpha\n\n"
            "# P(ΔEQ) con BHF fijo (0 = doblete); forma VBF; máxima entropía\n"
            "python fit_bhf_distribution_cli.py muestra.adt --variable quad --bmax 3\n"
            "python fit_bhf_distribution_cli.py muestra.adt --shape vbf --vbf-components 2\n"
            "python fit_bhf_distribution_cli.py muestra.adt --reg-mode maxent\n"
            "```\n\n"
            "<details><summary>Todas las opciones</summary>\n\n```text\n{help2}\n```\n</details>\n\n"
            "Ver también: [Distribuciones](ES-Distribuciones) · [Ajuste en serie](ES-Ajuste-en-serie)\n"
        )
    return head.format(help1=cli_help("mossbauer_fit_cli.py"),
                       help2=cli_help("fit_bhf_distribution_cli.py"))


def page_home(lang: str) -> str:
    """Portada: orientación y puntos de entrada, no un volcado del README."""
    if lang == "en":
        return f"""# Fitbauer

**Software for Mössbauer spectrum fitting and analysis** — load, fold, simulate and fit
⁵⁷Fe Mössbauer spectra. Current stable version: **v{APP_VERSION}**.

*Jorge Sánchez Marcos · Nieves Menéndez González — Department of Physical Chemistry, UAM*

🇪🇸 [Versión en español](ES-Inicio)

<img src="{RAW}/docs/img/captura-pantalla-principal.png" alt="Fitbauer main window" width="820">

Fitbauer reproduces **NORMOS** and reads and writes its `.JOB` files. The physics
has been contrasted on 411 synthetic spectra and on 564 real fits made with the
original program: in 355 of 503 comparable jobs (71 %) it matches or improves on
its reduced χ². See [NORMOS (.JOB)](NORMOS-interoperability) and the
[validation reports]({BLOB}/validacion/informe).

## Where to start

| I want to… | Go to |
|---|---|
| Install the program | [Installation](Installation) |
| See the typical workflow | [User flows](User-flows) |
| Understand folding and the folding point | [Folding](Folding) |
| Check the velocity calibration | [Calibration (33 T)](Calibration-33T) |
| Fit `P(BHF)` or `P(ΔEQ)` distributions | [Distribution fitting](Distribution-fitting) |
| Get realistic error bars | [Profile likelihood](Profile-likelihood) |
| Fit a whole temperature series | [Batch fitting](Batch-fitting) |
| Open a NORMOS `.JOB` | [NORMOS (.JOB)](NORMOS-interoperability) |
| Run fits without a GUI | [Command-line tools](Command-line-tools) |
| Understand the code layout | [Architecture](Architecture) |

## Full manual

The wiki is the quick reference. The complete treatment — physics, mathematics of the
fit, thickness correction, 2D distributions, relaxation models — lives in the manual:

- 📘 [User manual (PDF, English)]({BLOB}/docs/manual_en/main.pdf)
- 📗 [Manual de usuario (PDF, español)]({BLOB}/docs/manual/main.pdf)

## Downloads and history

[Latest release]({REPO_URL}/releases/latest) · [Changelog]({BLOB}/CHANGELOG.md) ·
[Report an issue]({REPO_URL}/issues)
"""
    return f"""# Fitbauer

**Software para el ajuste y análisis de espectros Mössbauer** — cargar, doblar, simular y
ajustar espectros Mössbauer de ⁵⁷Fe. Versión estable actual: **v{APP_VERSION}**.

*Jorge Sánchez Marcos · Nieves Menéndez González — Departamento de Química Física, UAM*

🇬🇧 [English version](Home)

<img src="{RAW}/docs/img/captura-pantalla-principal.png" alt="Ventana principal de Fitbauer" width="820">

Fitbauer reproduce **NORMOS** y lee y escribe sus ficheros `.JOB`. La física se ha
contrastado sobre 411 espectros sintéticos y sobre 564 ajustes reales hechos con el
programa original: en 355 de 503 trabajos comparables (71 %) iguala o mejora su χ²
reducido. Ver [NORMOS (.JOB)](ES-NORMOS-interoperabilidad) y los
[informes de validación]({BLOB}/validacion/informe).

## Por dónde empezar

| Quiero… | Ir a |
|---|---|
| Instalar el programa | [Instalación](ES-Instalacion) |
| Ver el flujo de trabajo típico | [Flujos de usuario](ES-Flujos-de-usuario) |
| Entender el plegado y el folding point | [Plegado](ES-Plegado) |
| Comprobar la calibración de velocidad | [Calibración (33 T)](ES-Calibracion-33T) |
| Ajustar distribuciones `P(BHF)` o `P(ΔEQ)` | [Distribuciones](ES-Distribuciones) |
| Obtener barras de error realistas | [Verosimilitud perfilada](ES-Verosimilitud-perfilada) |
| Ajustar una serie de temperaturas | [Ajuste en serie](ES-Ajuste-en-serie) |
| Abrir un `.JOB` de NORMOS | [NORMOS (.JOB)](ES-NORMOS-interoperabilidad) |
| Ajustar sin interfaz gráfica | [Línea de comandos](ES-Linea-de-comandos) |
| Entender la organización del código | [Arquitectura](ES-Arquitectura) |

## Manual completo

El wiki es la referencia rápida. El tratamiento completo — física, matemáticas del ajuste,
corrección de espesor, distribuciones 2D, modelos de relajación — está en el manual:

- 📗 [Manual de usuario (PDF, español)]({BLOB}/docs/manual/main.pdf)
- 📘 [User manual (PDF, English)]({BLOB}/docs/manual_en/main.pdf)

## Descargas e historial

[Última versión]({REPO_URL}/releases/latest) · [Historial de cambios]({BLOB}/CHANGELOG.md) ·
[Informar de un problema]({REPO_URL}/issues)
"""


def page_sidebar() -> str:
    """Barra lateral: ambos idiomas, agrupados por sección."""
    out = [f"**[Fitbauer](Home)** v{APP_VERSION}", ""]
    for lang, header in (("en", "🇬🇧 English"), ("es", "🇪🇸 Español")):
        out.append(f"### {header}")
        section = None
        for page in PAGES:
            if page.lang != lang:
                continue
            if page.section != section:
                section = page.section
                out.append(f"**{section}**")
            out.append(f"- [{page.title}]({page.name})")
        out.append("")
    out.append("---")
    out.append(f"[Repository]({REPO_URL}) · [Releases]({REPO_URL}/releases)")
    return "\n".join(out) + "\n"


def page_footer() -> str:
    return (
        f"---\n© Jorge Sánchez Marcos, Nieves Menéndez González — "
        f"Departamento de Química Física, UAM · "
        f"Wiki generado desde [`docs/`]({BLOB}/docs) para Fitbauer v{APP_VERSION}\n"
    )


def build(out_dir: Path) -> int:
    mapping = source_to_page()
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for page in PAGES:
        if page.source is None:
            body = page_home(page.lang) if page.name in {"Home", "ES-Inicio"} else page_cli(page.lang)
        else:
            src = ROOT / page.source
            if not src.exists():
                raise SystemExit(f"falta el origen {page.source} de la página {page.name}")
            banner = BANNER[page.lang].format(src=page.source, blob=BLOB)
            body = f"{banner}\n\n{rewrite_links(src.read_text(encoding='utf-8'), mapping)}"
        (out_dir / f"{page.name}.md").write_text(body, encoding="utf-8")
        written += 1

    (out_dir / "_Sidebar.md").write_text(page_sidebar(), encoding="utf-8")
    (out_dir / "_Footer.md").write_text(page_footer(), encoding="utf-8")
    print(f"{written} páginas + barra lateral y pie en {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=Path,
                        help="clon del repositorio del wiki donde escribir")
    args = parser.parse_args(argv)
    return build(args.out)


if __name__ == "__main__":
    raise SystemExit(main())
