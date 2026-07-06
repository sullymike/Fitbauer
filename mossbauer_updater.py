"""Comprobación y descarga de nuevas versiones desde GitHub Releases."""
from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

GITHUB_REPO = "sullymike/Mossbauer"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
RELEASES_ATOM = f"https://github.com/{GITHUB_REPO}/releases.atom"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
RELEASE_DOWNLOAD_URL = f"https://github.com/{GITHUB_REPO}/releases/download"


@dataclass
class ReleaseInfo:
    tag: str
    name: str
    html_url: str
    body: str
    zipball_url: str
    assets: list[dict]
    prerelease: bool = False
    draft: bool = False


def version_tuple(version: str) -> tuple[int, ...]:
    """Parte numérica base: 'v1.2.3-beta.1' -> (1, 2, 3)."""
    text = version.strip().lower().lstrip("v")
    base = re.split(r"[-+]", text, maxsplit=1)[0]
    nums = re.findall(r"\d+", base)
    return tuple(int(n) for n in nums) if nums else (0,)


def _version_key(version: str) -> tuple[tuple[int, ...], int, int]:
    """Clave comparable: estable > prerelease para la misma base.

    Ejemplos:
    - v0.1.4-beta.1 < v0.1.4
    - v0.1.4-beta.2 > v0.1.4-beta.1
    """
    text = version.strip().lower().lstrip("v")
    base = version_tuple(text)
    suffix = ""
    if "-" in text:
        suffix = text.split("-", 1)[1]
    is_prerelease = any(token in suffix for token in ("a", "alpha", "b", "beta", "rc", "pre", "dev"))
    pre_num = int(re.findall(r"\d+", suffix)[-1]) if is_prerelease and re.findall(r"\d+", suffix) else 0
    stable_rank = 0 if is_prerelease else 1
    return base, stable_rank, pre_num


def is_newer(latest: str, current: str) -> bool:
    return _version_key(latest) > _version_key(current)


def _is_prerelease_tag(tag: str) -> bool:
    """Deduce si un tag es prerelease por su sufijo (para el feed atom, que no lo marca)."""
    text = tag.strip().lower().lstrip("v")
    suffix = text.split("-", 1)[1] if "-" in text else ""
    return any(token in suffix for token in ("a", "alpha", "b", "beta", "rc", "pre", "dev"))


def _release_from_json(data: dict) -> ReleaseInfo:
    return ReleaseInfo(
        tag=str(data.get("tag_name") or ""),
        name=str(data.get("name") or data.get("tag_name") or ""),
        html_url=str(data.get("html_url") or RELEASES_URL),
        body=str(data.get("body") or ""),
        zipball_url=str(data.get("zipball_url") or ""),
        assets=list(data.get("assets") or []),
        prerelease=bool(data.get("prerelease", False)),
        draft=bool(data.get("draft", False)),
    )


def _releases_via_api(timeout: int) -> list[ReleaseInfo]:
    """Lista releases usando la API REST (rica: assets, flags), pero limitada a
    60 peticiones/hora por IP sin autenticar (devuelve HTTP 403 al agotarse)."""
    req = urllib.request.Request(
        RELEASES_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "MossbauerFe57-updater"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [_release_from_json(item) for item in data]


def _html_to_text(fragment: str) -> str:
    """Convierte el cuerpo HTML del feed atom en texto plano legible."""
    text = re.sub(r"(?is)<\s*br\s*/?>", "\n", fragment)
    text = re.sub(r"(?is)</\s*(p|li|div|h[1-6])\s*>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    return html.unescape(text).strip()


def _releases_via_atom(timeout: int) -> list[ReleaseInfo]:
    """Lista releases desde el feed atom público (github.com), que NO está sujeto
    al límite de 60/h de la API. No expone assets ni el flag de prerelease/draft:
    el prerelease se deduce del sufijo del tag y los assets se construyen luego."""
    req = urllib.request.Request(RELEASES_ATOM, headers={"User-Agent": "MossbauerFe57-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(raw)
    releases: list[ReleaseInfo] = []
    for entry in root.findall("a:entry", ns):
        entry_id = (entry.findtext("a:id", default="", namespaces=ns) or "").strip()
        link_el = entry.find("a:link", ns)
        href = str(link_el.get("href")) if link_el is not None else ""
        tag = entry_id.rsplit("/", 1)[-1] if "/" in entry_id else ""
        if not tag and "/tag/" in href:
            tag = href.rsplit("/tag/", 1)[-1]
        if not tag:
            continue
        title = (entry.findtext("a:title", default=tag, namespaces=ns) or tag).strip()
        content = entry.findtext("a:content", default="", namespaces=ns) or ""
        releases.append(ReleaseInfo(
            tag=tag,
            name=title,
            html_url=href or RELEASES_URL,
            body=_html_to_text(content),
            zipball_url=f"https://github.com/{GITHUB_REPO}/archive/refs/tags/{tag}.zip",
            assets=[],  # el feed no los publica; se construyen en choose_download
            prerelease=_is_prerelease_tag(tag),
            draft=False,  # los drafts no aparecen en el feed
        ))
    return releases


def list_releases(include_prereleases: bool = False, timeout: int = 15) -> list[ReleaseInfo]:
    """Lista releases publicadas. Por defecto excluye prereleases y drafts.

    Usa la API REST (más rica) y, si se agota su límite sin autenticar (HTTP 403)
    o falla la red, recurre al feed atom público, que no tiene ese límite. Así la
    comprobación de actualizaciones no se rompe por el rate-limit de GitHub.
    """
    try:
        releases = _releases_via_api(timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):  # rate-limit de la API sin autenticar
            releases = _releases_via_atom(timeout=timeout)
        else:
            raise
    except urllib.error.URLError:
        releases = _releases_via_atom(timeout=timeout)
    return [r for r in releases if not r.draft and (include_prereleases or not r.prerelease)]


def latest_release(include_prereleases: bool = False, timeout: int = 15) -> ReleaseInfo:
    """Devuelve la release más nueva según versión, incluyendo betas si se pide."""
    releases = list_releases(include_prereleases=include_prereleases, timeout=timeout)
    if not releases:
        raise RuntimeError("No hay releases publicadas en GitHub")
    return max(releases, key=lambda r: _version_key(r.tag))


def choose_download(release: ReleaseInfo, prefer_exe: bool = False) -> tuple[str, str]:
    """Devuelve (url, nombre) del mejor descargable de una release.

    Si hay assets, prioriza .exe en Windows o zip/tar.gz. Si no hay assets,
    usa el zipball generado automáticamente por GitHub.
    """
    assets = release.assets
    if assets:
        def score(asset: dict) -> tuple[int, int]:
            name = str(asset.get("name") or "").lower()
            if prefer_exe and name.endswith(".exe"):
                return (0, len(name))
            if name.endswith((".zip", ".tar.gz", ".tgz")):
                return (1, len(name))
            if name.endswith(".exe"):
                return (2, len(name))
            return (9, len(name))

        asset = sorted(assets, key=score)[0]
        url = str(asset.get("browser_download_url") or "")
        name = str(asset.get("name") or Path(urlparse(url).path).name or f"Mossbauer-{release.tag}.zip")
        if url:
            return url, name
    if release.tag:
        # Sin lista de assets (p. ej. release obtenida del feed atom): el workflow
        # publica siempre "Fitbauer-<tag>.zip", así que construimos su URL directa.
        name = f"Fitbauer-{release.tag}.zip"
        return f"{RELEASE_DOWNLOAD_URL}/{release.tag}/{name}", name
    if release.zipball_url:
        return release.zipball_url, f"Mossbauer-{release.tag or 'latest'}.zip"
    return release.html_url, f"Mossbauer-{release.tag or 'latest'}"


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """SHA-256 hexadecimal de un fichero, leido por bloques."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def download_file(
    url: str,
    dest_dir: Path,
    filename: str | None = None,
    timeout: int = 60,
    expected_sha256: str | None = None,
) -> Path:
    """Descarga un fichero. Si se da ``expected_sha256``, verifica su integridad.

    Ante una verificacion fallida borra el fichero descargado y lanza
    ``RuntimeError``, de modo que nunca se instale una descarga corrupta.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = filename or Path(urlparse(url).path).name or "Mossbauer-release"
    path = dest_dir / name
    req = urllib.request.Request(url, headers={"User-Agent": "MossbauerFe57-updater"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, path.open("wb") as fh:
            shutil.copyfileobj(resp, fh)
    except Exception:
        path.unlink(missing_ok=True)  # no dejar descargas parciales
        raise
    if expected_sha256:
        actual = sha256_file(path)
        if actual.lower() != expected_sha256.strip().lower():
            path.unlink(missing_ok=True)
            raise RuntimeError(
                "La verificacion SHA-256 de la descarga fallo "
                f"(esperado {expected_sha256.strip().lower()}, obtenido {actual})."
            )
    return path


_SHA256_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
_CHECKSUM_FILE_NAMES = {"sha256sums", "sha256sums.txt", "checksums.txt", "checksums.sha256"}


def _sha256_from_checksum_text(text: str, target_name: str, *, sidecar: bool) -> str | None:
    """Extrae el SHA-256 de un texto de checksum.

    Para un sidecar (un unico fichero) basta el primer hash. Para un fichero de
    sumas con varias lineas se exige que la linea mencione ``target_name``.
    """
    target = target_name.lower()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _SHA256_RE.search(line)
        if not match:
            continue
        if sidecar or target in line.lower():
            return match.group(0).lower()
    return None


def find_release_checksum(release: ReleaseInfo, filename: str, timeout: int = 30) -> str | None:
    """Busca el SHA-256 publicado para ``filename`` entre los assets de la release.

    Reconoce un asset ``<filename>.sha256`` o un fichero de sumas tipo
    ``SHA256SUMS``. Devuelve ``None`` si la release no publica ningun checksum.
    """
    target = filename.lower()
    sidecar_names = {f"{target}.sha256", f"{target}.sha256sum"}
    # (url, es_sidecar) a inspeccionar, en orden de preferencia.
    candidates: list[tuple[str, bool]] = []
    for asset in release.assets:
        name = str(asset.get("name") or "").lower()
        url = str(asset.get("browser_download_url") or "")
        if not url:
            continue
        sidecar = name in sidecar_names
        if not sidecar and name not in _CHECKSUM_FILE_NAMES:
            continue
        candidates.append((url, sidecar))
    if not candidates and release.tag:
        # Sin assets (feed atom): construimos las URLs canónicas del workflow.
        base = f"{RELEASE_DOWNLOAD_URL}/{release.tag}"
        candidates.append((f"{base}/sha256sums.txt", False))
        candidates.append((f"{base}/{filename}.sha256", True))
    for url, sidecar in candidates:
        req = urllib.request.Request(url, headers={"User-Agent": "MossbauerFe57-updater"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except OSError:
            continue
        digest = _sha256_from_checksum_text(text, filename, sidecar=sidecar)
        if digest:
            return digest
    return None


def is_zip_update(path: Path) -> bool:
    return path.suffix.lower() == ".zip" and zipfile.is_zipfile(path)


def install_zip_update(archive_path: Path, app_dir: Path) -> None:
    """Descomprime una actualización ZIP de GitHub encima del directorio actual.

    GitHub genera ZIPs con una carpeta raíz. Esta función copia el contenido de esa
    carpeta al directorio de la aplicación. No borra ni toca `.venv`, `.git`,
    `__pycache__` ni copias de seguridad locales.
    """
    app_dir = app_dir.resolve()
    skip_names = {".git", ".venv", "venv", "env", "__pycache__", ".update_backup"}
    backup_dir = app_dir / ".update_backup"
    backup_dir.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mossbauer_update_") as tmp:
        tmp_dir = Path(tmp)
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(tmp_dir)
        entries = [p for p in tmp_dir.iterdir()]
        source = entries[0] if len(entries) == 1 and entries[0].is_dir() else tmp_dir

        # Copia de seguridad mínima de ficheros que se van a sobrescribir.
        for item in source.rglob("*"):
            rel = item.relative_to(source)
            if not rel.parts or rel.parts[0] in skip_names:
                continue
            dest = app_dir / rel
            if item.is_file() and dest.exists() and dest.is_file():
                backup_target = backup_dir / rel
                backup_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, backup_target)

        for item in source.rglob("*"):
            rel = item.relative_to(source)
            if not rel.parts or rel.parts[0] in skip_names:
                continue
            dest = app_dir / rel
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            elif item.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)

        # Python's zipfile.extractall no preserva permisos Unix; restauramos
        # el bit ejecutable del lanzador de Linux tras la copia.
        launcher = app_dir / "mossbauer"
        if launcher.exists():
            import stat as _stat
            launcher.chmod(launcher.stat().st_mode | _stat.S_IXUSR | _stat.S_IXGRP | _stat.S_IXOTH)


# ── Ajustes de actualización y refresco de dependencias (sin GUI) ─────────────
# Lógica headless usada por la interfaz Qt; antes vivía en mossbauer_updater_ui
# (Tk). Aquí no hay ningún diálogo: solo ficheros de configuración y pip.


def _pip_install_requirements(install_dir: Path) -> str:
    """Ejecuta pip install -r requirements.txt del directorio dado.

    Devuelve una cadena con el resultado (vacía si no hay requirements.txt).
    Nunca lanza excepción.
    """
    req_file = install_dir / "requirements.txt"
    if not req_file.exists():
        return ""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file),
             "--quiet", "--disable-pip-version-check"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            return "Dependencias actualizadas correctamente (pip)."
        err = (result.stderr or result.stdout or "").strip()
        return f"Aviso de pip:\n{err[:300]}"
    except subprocess.TimeoutExpired:
        return "pip tardó demasiado y se canceló."
    except Exception as exc:
        return f"No se pudo ejecutar pip: {exc}"


def _update_pip_stamp(install_dir: Path, config_dir: Path) -> None:
    req_file = install_dir / "requirements.txt"
    if not req_file.exists():
        return
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "last_pip_check").write_text(
            str(req_file.stat().st_mtime), encoding="utf-8"
        )
    except Exception:
        pass


def check_requirements_if_needed(install_dir: Path, config_dir: Path) -> None:
    """Lanza pip en background si requirements.txt es más nuevo que el último chequeo."""
    req_file = install_dir / "requirements.txt"
    if not req_file.exists():
        return
    stamp_file = config_dir / "last_pip_check"
    req_mtime = req_file.stat().st_mtime
    if stamp_file.exists():
        try:
            last = float(stamp_file.read_text(encoding="utf-8").strip())
            if req_mtime <= last:
                return
        except Exception:
            pass

    def _worker() -> None:
        _pip_install_requirements(install_dir)
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            stamp_file.write_text(str(req_mtime), encoding="utf-8")
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def load_update_settings(config_dir: Path) -> dict:
    path = config_dir / "update_settings.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"channel": "stable"}


def save_update_settings(config_dir: Path, data: dict, parent=None) -> None:
    """Guarda los ajustes de actualización. Mejor esfuerzo: no lanza si falla.

    ``parent`` se mantiene por compatibilidad de firma con la llamada de la GUI,
    pero ya no se usa (no hay diálogo Tk).
    """
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "update_settings.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
