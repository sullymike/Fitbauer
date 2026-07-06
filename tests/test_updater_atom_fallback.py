"""El chequeo de actualizaciones debe sobrevivir al rate-limit (HTTP 403) de la
API de GitHub recurriendo al feed atom público, sin tocar la red en el test."""
from __future__ import annotations

import io
import urllib.error

import pytest

import mossbauer_updater as u

ATOM_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:github.com,2008:Repository/1/v4.14.0</id>
    <link rel="alternate" type="text/html"
          href="https://github.com/sullymike/Mossbauer/releases/tag/v4.14.0"/>
    <title>Fitbauer v4.14.0</title>
    <content type="html">&lt;p&gt;Notas de &lt;b&gt;v4.14.0&lt;/b&gt;&lt;/p&gt;</content>
  </entry>
  <entry>
    <id>tag:github.com,2008:Repository/1/v4.15.0-beta.1</id>
    <link rel="alternate" type="text/html"
          href="https://github.com/sullymike/Mossbauer/releases/tag/v4.15.0-beta.1"/>
    <title>Fitbauer v4.15.0-beta.1</title>
    <content type="html">&lt;p&gt;beta&lt;/p&gt;</content>
  </entry>
</feed>
"""


def _fake_urlopen_factory(monkeypatch):
    """Simula: API -> HTTP 403 (rate-limit); feed atom -> XML de ejemplo."""
    def fake_urlopen(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "api.github.com" in url:
            raise urllib.error.HTTPError(url, 403, "rate limit exceeded", {}, None)
        if url == u.RELEASES_ATOM:
            return io.BytesIO(ATOM_SAMPLE.encode("utf-8"))
        raise AssertionError(f"URL inesperada: {url}")

    monkeypatch.setattr(u.urllib.request, "urlopen", fake_urlopen)


def test_list_releases_falls_back_to_atom_on_403(monkeypatch):
    _fake_urlopen_factory(monkeypatch)
    stable = u.list_releases(include_prereleases=False)
    assert [r.tag for r in stable] == ["v4.14.0"]  # la beta queda fuera
    latest = u.latest_release()
    assert latest.tag == "v4.14.0"
    assert latest.prerelease is False
    assert "v4.14.0" in latest.body and "<b>" not in latest.body  # HTML -> texto


def test_atom_channel_all_includes_prerelease(monkeypatch):
    _fake_urlopen_factory(monkeypatch)
    allrel = u.list_releases(include_prereleases=True)
    tags = [r.tag for r in allrel]
    assert "v4.15.0-beta.1" in tags
    beta = next(r for r in allrel if r.tag.endswith("beta.1"))
    assert beta.prerelease is True


def test_choose_download_builds_canonical_url_without_assets():
    rel = u.ReleaseInfo(
        tag="v4.14.0", name="", html_url="", body="", zipball_url="", assets=[])
    url, name = u.choose_download(rel)
    assert name == "Fitbauer-v4.14.0.zip"
    assert url == f"{u.RELEASE_DOWNLOAD_URL}/v4.14.0/Fitbauer-v4.14.0.zip"


def test_non_ratelimit_http_error_is_not_swallowed(monkeypatch):
    def fake_urlopen(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        raise urllib.error.HTTPError(url, 500, "server error", {}, None)

    monkeypatch.setattr(u.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(urllib.error.HTTPError):
        u.list_releases()
