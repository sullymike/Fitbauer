"""Tests de las opciones extendidas de los CLIs (bootstrap, batch, distribución)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mossbauer_fit_cli import fit_batch, fit_spectrum, main  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data_sample"
TEMPLATE = DATA / "template_alphaFe.json"


def test_fit_spectrum_bootstrap_section(tmp_path):
    out = tmp_path / "afe.fit.json"
    session = fit_spectrum(TEMPLATE, DATA / "hierro_metalico_alphaFe.adt", out,
                           bootstrap_n=5)
    bs = session["bootstrap"]
    assert bs["n_rep"] == 5
    assert bs["n_ok"] > 0
    assert bs["std"], "sin sigmas bootstrap"
    # Las σ_MC deben ser positivas y del orden del error de covarianza.
    errors = session["batch_fit_result"]["errors"]
    for key, std in bs["std"].items():
        assert std >= 0.0
        cov_err = errors.get(key)
        if cov_err:
            assert std < 20 * cov_err
    # Y la sección debe persistir en el fichero.
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert "bootstrap" in saved


def test_fit_batch_warm_start_rows(tmp_path):
    out = tmp_path / "serie.batch.json"
    spectra = [DATA / "hierro_metalico_alphaFe.adt", DATA / "hematita_Fe2O3.adt"]
    rows = fit_batch(TEMPLATE, spectra, out)
    assert [r["status"] for r in rows] == ["ok", "ok"]
    assert all(r["values"] for r in rows)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["spectra"] == [str(p) for p in spectra]
    assert len(payload["results"]) == 2


def test_main_batch_and_option_conflicts(tmp_path):
    out = tmp_path / "x.json"
    # bootstrap + varios espectros → código 2 sin ajustar nada.
    code = main(["--template", str(TEMPLATE),
                 "--spectrum", str(DATA / "hierro_metalico_alphaFe.adt"),
                 str(DATA / "hematita_Fe2O3.adt"),
                 "--out", str(out), "--bootstrap", "3", "--quiet"])
    assert code == 2
    assert not out.exists()


def _run_dist_cli(tmp_path, *extra):
    cmd = [sys.executable, str(ROOT / "fit_bhf_distribution_cli.py"),
           str(DATA / "sintetico_dist_deq.adt"),
           "--out-prefix", str(tmp_path / "out"), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)


def test_dist_cli_variable_quad(tmp_path):
    proc = _run_dist_cli(tmp_path, "--variable", "quad", "--nbins", "25")
    assert proc.returncode == 0, proc.stderr
    summary = json.loads((tmp_path / "out_summary.json").read_text(encoding="utf-8"))
    assert summary["variable"] == "quad"
    assert summary["fixed_bhf"] == 0.0
    # El sintético P(ΔEQ) tiene el pico en ~1.4 mm/s.
    assert 0.5 < summary["peak_position"] < 3.0
    header = (tmp_path / "out_distribution.dat").read_text(encoding="utf-8").splitlines()[0]
    assert "DeltaEQ_mm_s" in header


def test_dist_cli_shape_vbf(tmp_path):
    proc = _run_dist_cli(tmp_path, "--variable", "quad", "--shape", "vbf",
                         "--vbf-components", "1", "--nbins", "25")
    assert proc.returncode == 0, proc.stderr
    summary = json.loads((tmp_path / "out_summary.json").read_text(encoding="utf-8"))
    assert summary["shape"] == "VBF"
    comps = summary["vbf_components"]
    assert len(comps) == 1 and len(comps[0]) == 3


def test_dist_cli_scan_alpha_requires_histogram(tmp_path):
    proc = _run_dist_cli(tmp_path, "--shape", "vbf", "--scan-alpha")
    assert proc.returncode != 0
    assert "histograma" in (proc.stderr + proc.stdout)
