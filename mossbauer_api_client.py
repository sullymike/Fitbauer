#!/usr/bin/env python3
"""Cliente para la API REST del laboratorio MATELEC.

Sustituye al scraping de HTML del programa de escritorio. La API oficial
(documentada en https://matelec.qfa.uam.es/api/v1/) expone medidas Mössbauer,
calibraciones y versiones de análisis, con autenticación por token.

Uso típico:

    client = MatelecLabClient()
    client.login("usuario", "contraseña")     # una vez; guarda client.token
    medida = client.find_medida_by_filename("muestra_1357.ws5")
    calib = client.get_calibracion_de_medida(medida["id"])
    ruta = client.download_datafile(medida["id"], dest_dir="medidas")

El token no caduca: conviene guardarlo y reutilizarlo en arranques posteriores
en lugar de volver a hacer login cada vez.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote

import requests

DEFAULT_BASE_URL = "https://matelec.qfa.uam.es"


class MatelecLabClient:
    """Cliente para la API REST /api/v1/ del laboratorio."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, token: str | None = None,
                 timeout: float = 30.0) -> None:
        self.base = base_url.rstrip("/") + "/api/v1"
        self.timeout = timeout
        self.token: str | None = None
        self.session = requests.Session()
        if token:
            self.set_token(token)

    # ── Autenticación ──────────────────────────────────────────────
    def set_token(self, token: str) -> None:
        self.token = token
        self.session.headers["Authorization"] = f"Token {token}"

    def login(self, username: str, password: str) -> str:
        """Obtiene un token nuevo a partir de usuario y contraseña."""
        r = self.session.post(
            f"{self.base}/token/",
            data={"username": username, "password": password},
            timeout=self.timeout,
        )
        r.raise_for_status()
        token = r.json()["token"]
        self.set_token(token)
        return token

    def token_is_valid(self) -> bool:
        """Comprueba si el token actual sigue siendo aceptado por la API."""
        if not self.token:
            return False
        try:
            r = self.session.get(f"{self.base}/medidas/", params={"page": 1},
                                  timeout=self.timeout)
        except requests.RequestException:
            return False
        return r.status_code == 200

    # ── Medidas Mössbauer ──────────────────────────────────────────
    def iter_medidas(self, search: str | None = None,
                     filename: str | None = None,
                     limit: int | None = None):
        """Itera medidas siguiendo la paginación automáticamente.

        ``limit`` limita el número máximo de elementos devueltos en cliente. Se
        acepta para compatibilidad con la GUI Qt.
        """
        params = {}
        if search:
            params["search"] = search
        if filename:
            params["filename"] = filename
        yield from self._iter_paginated(f"{self.base}/medidas/", params, limit=limit)

    def get_medida(self, medida_id) -> dict:
        r = self.session.get(f"{self.base}/medidas/{medida_id}/", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def find_medida_by_filename(self, filename: str) -> dict | None:
        """Devuelve la medida cuyo .ws5 coincide con el nombre dado, o None.

        Funciona con o sin extensión ('muestra_1357' o 'muestra_1357.ws5').
        """
        results = list(self.iter_medidas(filename=filename))
        return results[0] if results else None

    # ── Calibración asociada ───────────────────────────────────────
    def get_calibracion_de_medida(self, medida_id) -> dict | None:
        """Calibración asociada a una medida, o None si no tiene."""
        r = self.session.get(f"{self.base}/medidas/{medida_id}/calibration/",
                             timeout=self.timeout)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    # ── Calibraciones ──────────────────────────────────────────────
    def iter_calibraciones(self, search: str | None = None,
                           filename: str | None = None,
                           limit: int | None = None):
        params = {}
        if search:
            params["search"] = search
        if filename:
            params["filename"] = filename
        yield from self._iter_paginated(f"{self.base}/calibraciones/", params, limit=limit)

    def get_calibracion(self, calibracion_id) -> dict:
        r = self.session.get(f"{self.base}/calibraciones/{calibracion_id}/",
                             timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ── Descargas de ficheros de datos ─────────────────────────────
    def download_datafile(self, medida_id, dest_dir: str = ".") -> Path:
        return self._download(f"{self.base}/medidas/{medida_id}/datafile/", dest_dir)

    def download_calibracion_datafile(self, calibracion_id, dest_dir: str = ".") -> Path:
        return self._download(
            f"{self.base}/calibraciones/{calibracion_id}/datafile/", dest_dir)

    # ── Análisis (versiones de ajuste JSON) ────────────────────────
    def list_analyses(self, medida_id) -> list:
        r = self.session.get(f"{self.base}/medidas/{medida_id}/analyses/",
                             timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def upload_analysis(self, medida_id, json_path=None, *, data: bytes | None = None,
                        filename: str | None = None, note: str = "") -> dict:
        """Sube una versión nueva de análisis (.json, máximo 10 MB).

        Acepta una ruta de fichero en ``json_path`` o bytes ya en memoria en
        ``data``. La API conserva todas las versiones; no sobrescribe.
        """
        if data is not None:
            content = data
            name = filename or "analysis.json"
        elif json_path is not None:
            content = Path(json_path).read_bytes()
            name = filename or os.path.basename(str(json_path))
        else:
            raise ValueError("Hay que indicar json_path o data")
        r = self.session.post(
            f"{self.base}/medidas/{medida_id}/analyses/",
            files={"file": (name, content, "application/json")},
            data={"note": note},
            timeout=max(self.timeout, 60.0),
        )
        if r.status_code == 400:
            raise ValueError(f"Subida rechazada por la API: {r.text}")
        r.raise_for_status()
        return r.json()

    def download_analysis(self, medida_id, analysis_id, dest_dir: str = ".") -> Path:
        return self._download(
            f"{self.base}/medidas/{medida_id}/analyses/{analysis_id}/", dest_dir)

    # ── Internos ───────────────────────────────────────────────────
    def _iter_paginated(self, url: str, params: dict, *, limit: int | None = None):
        yielded = 0
        while url:
            r = self.session.get(url, params=params, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            for item in data["results"]:
                if limit is not None and yielded >= limit:
                    return
                yield item
                yielded += 1
            url = data.get("next")
            params = {}   # 'next' ya lleva los parámetros embebidos

    def _download(self, url: str, dest_dir: str) -> Path:
        r = self.session.get(url, stream=True, timeout=max(self.timeout, 60.0))
        r.raise_for_status()
        cd = r.headers.get("Content-Disposition", "")
        name = self._filename_from_disposition(cd) or url.rstrip("/").split("/")[-1]
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / name
        with open(path, "wb") as fh:
            for chunk in r.iter_content(8192):
                fh.write(chunk)
        return path

    @staticmethod
    def _filename_from_disposition(content_disposition: str) -> str | None:
        import re
        m = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition, flags=re.I)
        if m:
            return os.path.basename(unquote(m.group(1)))
        m = re.search(r'filename="?([^";]+)"?', content_disposition, flags=re.I)
        if m:
            return os.path.basename(m.group(1).strip())
        return None
