"""Comprobación y descarga de nuevas versiones desde GitHub Releases."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

GITHUB_REPO = "sullymike/Mossbauer"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"


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
    """Convierte 'v1.2.3' o '1.2.3-beta' en tupla comparable (1, 2, 3)."""
    nums = re.findall(r"\d+", version)
    return tuple(int(n) for n in nums) if nums else (0,)


def is_newer(latest: str, current: str) -> bool:
    a = version_tuple(latest)
    b = version_tuple(current)
    size = max(len(a), len(b))
    return a + (0,) * (size - len(a)) > b + (0,) * (size - len(b))


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


def list_releases(include_prereleases: bool = False, timeout: int = 15) -> list[ReleaseInfo]:
    """Lista releases publicadas. Por defecto excluye prereleases y drafts."""
    req = urllib.request.Request(
        RELEASES_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "MossbauerFe57-updater"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    releases = [_release_from_json(item) for item in data]
    return [r for r in releases if not r.draft and (include_prereleases or not r.prerelease)]


def latest_release(include_prereleases: bool = False, timeout: int = 15) -> ReleaseInfo:
    """Devuelve la release más nueva según versión, incluyendo betas si se pide."""
    releases = list_releases(include_prereleases=include_prereleases, timeout=timeout)
    if not releases:
        raise RuntimeError("No hay releases publicadas en GitHub")
    return max(releases, key=lambda r: version_tuple(r.tag))


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
    if release.zipball_url:
        return release.zipball_url, f"Mossbauer-{release.tag or 'latest'}.zip"
    return release.html_url, f"Mossbauer-{release.tag or 'latest'}"


def download_file(url: str, dest_dir: Path, filename: str | None = None, timeout: int = 60) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = filename or Path(urlparse(url).path).name or "Mossbauer-release"
    path = dest_dir / name
    req = urllib.request.Request(url, headers={"User-Agent": "MossbauerFe57-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, path.open("wb") as fh:
        fh.write(resp.read())
    return path


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
