#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import numpy as np
import requests
from scipy.optimize import least_squares

from mossbauer_fe33_gui import (
    LINE_POS_33T,
    find_best_integer_or_half_center,
    fold_integer_or_half,
    lorentzian,
    read_ws5_counts,
)

OUTDIR = Path("calibraciones_web")
BASE_URL = "https://matelec.qfa.uam.es/lab/calibraciones/"
CRED_PATH = Path.home() / ".config" / "mossbauer_fe33_gui" / "credentials.json"


@dataclass
class CalibrationRow:
    item_id: str
    sample: str
    date: str
    temperature: str
    line: str
    web_v_input: str
    web_velocity: str
    web_isomer_shift: str
    web_extra: str
    url: str
    filename: str


def num_es(text: str) -> float | None:
    text = (text or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except Exception:
        return None


def safe_filename(text: str, max_len: int = 120) -> str:
    text = unescape(text).strip()
    text = re.sub(r"[^\w.()+\-]+", "_", text, flags=re.UNICODE).strip("_")
    return (text[:max_len] or "calibracion")


def clean_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(html))).strip()


def filename_from_response(response: requests.Response, fallback: str) -> str:
    """Usa el nombre real de descarga indicado por la web, incluida extensión .adt/.ws5."""
    cd = response.headers.get("content-disposition", "")
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd, flags=re.I)
    if m:
        return Path(unquote(m.group(1))).name
    m = re.search(r'filename="?([^";]+)"?', cd, flags=re.I)
    if m:
        return Path(unescape(m.group(1))).name
    return fallback


def existing_file_for(row: CalibrationRow) -> Path | None:
    ws5_dir = OUTDIR / "ws5"
    exact = ws5_dir / row.filename
    if exact.exists() and exact.stat().st_size > 0:
        return exact
    matches = sorted(ws5_dir.glob(f"*_{row.item_id}.*"))
    for match in matches:
        if match.is_file() and match.stat().st_size > 0:
            return match
    return None


def login_session() -> requests.Session:
    cred = json.loads(CRED_PATH.read_text(encoding="utf-8"))
    session = requests.Session()
    r = session.get(BASE_URL, timeout=30, allow_redirects=True)
    forms = re.findall(r"<form\b.*?</form>", r.text, flags=re.S | re.I)
    login_form = next((f for f in forms if re.search(r'type=["\']password["\']', f, re.I)), None)
    if login_form is None:
        return session

    data: dict[str, str] = {}
    for tag in re.findall(r"<input\b[^>]*>", login_form, flags=re.S | re.I):
        m = re.search(r'\bname=["\']([^"\']+)["\']', tag, flags=re.I)
        if not m:
            continue
        v = re.search(r'\bvalue=["\']([^"\']*)["\']', tag, flags=re.I)
        data[unescape(m.group(1))] = unescape(v.group(1)) if v else ""

    def field(typ: str, default: str) -> str:
        for tag in re.findall(r"<input\b[^>]*>", login_form, flags=re.S | re.I):
            tm = re.search(r'\btype=["\']([^"\']+)["\']', tag, flags=re.I)
            t = tm.group(1).lower() if tm else "text"
            if t == typ:
                nm = re.search(r'\bname=["\']([^"\']+)["\']', tag, flags=re.I)
                if nm:
                    return unescape(nm.group(1))
        return default

    data[field("text", "username")] = cred.get("username", "")
    data[field("password", "password")] = cred.get("password", "")
    if "next" in data and not data["next"]:
        data["next"] = "/lab/calibraciones/"
    action = re.search(r'<form\b[^>]*\baction=["\']([^"\']*)["\']', login_form, flags=re.S | re.I)
    post_url = urljoin(r.url, unescape(action.group(1))) if action else r.url
    r2 = session.post(post_url, data=data, headers={"Referer": r.url}, timeout=30, allow_redirects=True)
    r2.raise_for_status()
    return session


def parse_rows(session: requests.Session) -> list[CalibrationRow]:
    found: dict[str, CalibrationRow] = {}
    queue = [BASE_URL]
    visited: set[str] = set()
    while queue:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        r = session.get(url, timeout=30, allow_redirects=True)
        r.raise_for_status()
        text = r.text
        for row in re.findall(r"<tr\b.*?</tr>", text, flags=re.S | re.I):
            m = re.search(r'href=["\']([^"\']*/lab/download/calibration/(\d+)/datafile/?)["\']', row, flags=re.I)
            if not m:
                m = re.search(r'href=["\'](/lab/download/calibration/(\d+)/datafile/?)["\']', row, flags=re.I)
            if not m:
                continue
            href, item_id = m.group(1), m.group(2)
            if item_id == "0":
                continue
            full = urljoin(r.url, href)
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.S | re.I)
            vals = [clean_text(c).replace("↓ datos Ver ✏", "").strip() for c in cells]
            vals += [""] * (8 - len(vals))
            sample, date, temp, line, vin, vweb, iso, extra = vals[:8]
            filename = safe_filename(f"{date}_cal_{sample}_{item_id}") + ".ws5"
            found[item_id] = CalibrationRow(item_id, sample, date, temp, line, vin, vweb, iso, extra, full, filename)
        for href in re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.I):
            full = urljoin(r.url, unescape(href))
            p = urlparse(full)
            if p.netloc == urlparse(BASE_URL).netloc and p.path.rstrip("/") == "/lab/calibraciones" and "page=" in p.query:
                if full not in visited and full not in queue:
                    queue.append(full)
    return sorted(found.values(), key=lambda x: (x.date, x.item_id), reverse=True)


def sextet_model(v: np.ndarray, baseline: float, slope: float, delta: float, vmax_dummy: float, gamma: float, depth: float) -> np.ndarray:
    # vmax_dummy está solo para documentar el orden; v ya viene calculada.
    positions = LINE_POS_33T + delta  # BHF=33 T, QUA=0
    weights = np.array([1.0, 2/3, 1/3, 1/3, 2/3, 1.0], dtype=float)
    y = baseline + slope * v
    absorption = np.zeros_like(v)
    for pos, w in zip(positions, weights):
        absorption += w * lorentzian(v, pos, gamma)
    return y - depth * absorption


def read_counts_any(path: Path) -> np.ndarray:
    """Lee WS5 XML moderno o ficheros antiguos de cuentas en texto plano."""
    try:
        return read_ws5_counts(path)
    except Exception:
        text = path.read_text(encoding="utf-8", errors="replace")
        nums = [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", text)]
        if len(nums) < 2:
            raise ValueError(f"No se encontraron cuentas en {path}")
        return np.array(nums, dtype=float)


def fit_calibration(path: Path, vmax_guess: float | None) -> dict[str, float | str]:
    counts = read_counts_any(path)
    center = find_best_integer_or_half_center(counts)
    folded, _ = fold_integer_or_half(counts, center)
    norm = float(np.percentile(folded, 90)) or 1.0
    y = folded / norm
    if vmax_guess is None or not np.isfinite(vmax_guess) or vmax_guess <= 0:
        vmax_guess = 12.0

    # y(v; vmax) con BHF fijo. Se ajustan baseline, slope, delta, vmax, gamma(HWHM), depth.
    def model(x: np.ndarray) -> np.ndarray:
        baseline, slope, delta, vmax, gamma, depth = x
        v = np.linspace(-abs(vmax), abs(vmax), y.size)
        return sextet_model(v, baseline, slope, delta, vmax, gamma, depth)

    def residual(x: np.ndarray) -> np.ndarray:
        return model(x) - y

    baseline0 = float(np.percentile(y, 90))
    depth0 = max(0.01, min(0.20, baseline0 - float(np.min(y)))) / 2.5
    starts = []
    for vmax0 in [vmax_guess, 11.8, 12.0, 12.2]:
        for delta0 in [-0.11, 0.0, -0.2]:
            starts.append(np.array([baseline0, 0.0, delta0, vmax0, 0.17, depth0], dtype=float))
    lo = np.array([0.70, -0.002, -1.0, 2.0, 0.03, 0.0])
    hi = np.array([1.30, 0.002, 1.0, 15.0, 1.0, 0.30])
    best = None
    for x0 in starts:
        x0 = np.clip(x0, lo, hi)
        res = least_squares(residual, x0, bounds=(lo, hi), max_nfev=4000, xtol=1e-10, ftol=1e-10)
        rms = float(np.sqrt(np.mean(res.fun ** 2)))
        if best is None or rms < best[0]:
            best = (rms, res.x)
    assert best is not None
    rms, x = best
    return {
        "fit_center_internal": center,
        "fit_center_normos_equiv": 2.0 * center,
        "fit_baseline": x[0],
        "fit_slope": x[1],
        "fit_isomer_shift": x[2],
        "fit_velocity": abs(x[3]),
        "fit_gamma_hwhm": x[4],
        "fit_depth": x[5],
        "fit_rms": rms,
        "fit_status": "ok",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga y ajusta calibraciones Mössbauer de la web.")
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="No descargar ficheros .ws5: usa solo los ya existentes en calibraciones_web/ws5.",
    )
    args = parser.parse_args()

    OUTDIR.mkdir(exist_ok=True)
    (OUTDIR / "ws5").mkdir(exist_ok=True)
    session = login_session()
    rows = parse_rows(session)
    print(f"Calibraciones encontradas: {len(rows)}")
    if args.no_download:
        print("Modo --no-download: no se descargan ficheros; se ajustan solo los existentes.")

    out_csv = OUTDIR / "calibraciones_ajustes.csv"
    fields = [
        "id", "sample", "date", "temperature", "line", "web_v_input", "web_velocity", "web_isomer_shift", "web_extra",
        "filename", "url", "fit_velocity", "fit_isomer_shift", "diff_velocity_fit_minus_web", "diff_isomer_fit_minus_web",
        "fit_center_internal", "fit_center_normos_equiv", "fit_gamma_hwhm", "fit_depth", "fit_baseline", "fit_slope", "fit_rms", "fit_status", "error",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for i, row in enumerate(rows, 1):
            path = existing_file_for(row) or (OUTDIR / "ws5" / row.filename)
            error = ""
            try:
                if not path.exists() or path.stat().st_size == 0:
                    if args.no_download:
                        raise FileNotFoundError(f"No existe fichero local para id {row.item_id} y --no-download está activo")
                    rr = session.get(row.url, timeout=60, allow_redirects=True)
                    rr.raise_for_status()
                    real_name = safe_filename(Path(filename_from_response(rr, row.filename)).stem) + Path(filename_from_response(rr, row.filename)).suffix
                    path = OUTDIR / "ws5" / real_name
                    path.write_bytes(rr.content)
                fit = fit_calibration(path, num_es(row.web_velocity) or num_es(row.web_v_input))
            except Exception as exc:
                fit = {"fit_status": "error"}
                error = f"{type(exc).__name__}: {exc}"
            rec = {
                "id": row.item_id,
                "sample": row.sample,
                "date": row.date,
                "temperature": row.temperature,
                "line": row.line,
                "web_v_input": row.web_v_input,
                "web_velocity": row.web_velocity,
                "web_isomer_shift": row.web_isomer_shift,
                "web_extra": row.web_extra,
                "filename": str(path),
                "url": row.url,
                "error": error,
            }
            rec.update(fit)
            web_velocity_num = num_es(row.web_velocity)
            web_iso_num = num_es(row.web_isomer_shift)
            fit_velocity_num = rec.get("fit_velocity")
            fit_iso_num = rec.get("fit_isomer_shift")
            rec["diff_velocity_fit_minus_web"] = (
                float(fit_velocity_num) - web_velocity_num
                if fit_velocity_num not in (None, "") and web_velocity_num is not None
                else ""
            )
            rec["diff_isomer_fit_minus_web"] = (
                float(fit_iso_num) - web_iso_num
                if fit_iso_num not in (None, "") and web_iso_num is not None
                else ""
            )
            writer.writerow(rec)
            print(f"[{i:03d}/{len(rows)}] {row.item_id} {path.name} {rec.get('fit_status')} v={rec.get('fit_velocity','')} iso={rec.get('fit_isomer_shift','')} {error}")
    print(f"Escrito: {out_csv}")


if __name__ == "__main__":
    main()
