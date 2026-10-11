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
    comparadas = 0
    for key, std in bs["std"].items():
        assert std >= 0.0
        cov_err = errors.get(key)
        if cov_err:
            assert std < 20 * cov_err
            comparadas += 1
    # sin esto, si la covarianza desapareciera no se compararía nada
    # (auditoría 2026-08-02)
    assert comparadas >= 2
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



def test_dist_cli_vbf_sigma_limits(tmp_path):
    """--vbf-sigma-min/--vbf-sigma-max llegan al motor y al resumen."""
    proc = _run_dist_cli(tmp_path, "--variable", "quad", "--shape", "vbf",
                         "--vbf-components", "2", "--nbins", "25",
                         "--vbf-sigma-min", "0.1", "--vbf-sigma-max", "0.4")
    assert proc.returncode == 0, proc.stderr
    summary = json.loads((tmp_path / "out_summary.json").read_text(encoding="utf-8"))
    assert summary["vbf_sigma_bounds"] == [0.1, 0.4]
    assert all(0.1 - 1e-9 <= c[2] <= 0.4 + 1e-9 for c in summary["vbf_components"])


@pytest.mark.parametrize("extra", [
    ("--vbf-sigma-max", "2"),                                   # histograma
    ("--shape", "vbf", "--vbf-sigma-min", "3", "--vbf-sigma-max", "2"),
    ("--shape", "vbf", "--vbf-sigma-min-y", "0.1"),             # -y sin --dist-2d
    ("--shape", "vbf", "--vbf-sigma-min", "-1"),
])
def test_dist_cli_vbf_sigma_rechaza_combinaciones(tmp_path, extra):
    proc = _run_dist_cli(tmp_path, *extra)
    assert proc.returncode != 0 and "--vbf-sigma" in proc.stderr

def test_dist_cli_shape_binomial_normos(tmp_path):
    """--shape binomial es la binomial de vecinos de NORMOS (12 vecinos)."""
    proc = _run_dist_cli(tmp_path, "--shape", "binomial", "--binomial-conc", "20",
                         "--binomial-start", "33", "--binomial-step", "-2")
    assert proc.returncode == 0, proc.stderr
    summary = json.loads((tmp_path / "out_summary.json").read_text(encoding="utf-8"))
    assert summary["shape"] == "Binomial"
    assert summary["binomial_n"] == 12
    assert summary["fitted_dist_p"] == 0.2          # CONC es dato, no se ajusta
    assert summary["binomial_step"] is not None


def test_dist_cli_gaussiana_2d(tmp_path):
    """--dist-2d --shape gaussiana: una gaussiana bivariante, sin α."""
    proc = _run_dist_cli(tmp_path, "--dist-2d", "--shape", "gaussiana",
                         "--bmin", "20", "--bmax", "40", "--nbins", "21",
                         "--qmin", "-0.5", "--qmax", "0.5", "--nbins-quad", "9")
    assert proc.returncode == 0, proc.stderr
    summary = json.loads((tmp_path / "out_summary.json").read_text(encoding="utf-8"))
    assert summary["shape"] == "Gaussiana 2D"
    assert len(summary["vbf2d_components"]) == 1
    assert (tmp_path / "out_distribution2d.dat").exists()


def test_dist_cli_2d_pareja_is_quad(tmp_path):
    """--pair delta-quad: P(IS, ΔEQ) con dobletes, como el modo 2D de la GUI.

    La CLI solo hacía la pareja BHF–ΔEQ. Los ejes salen con el nombre de cada
    variable y el rango de ΔEQ por defecto es el de dobletes (0–3 mm/s).
    """
    proc = _run_dist_cli(tmp_path, "--dist-2d", "--pair", "delta-quad",
                         "--shape", "gaussiana", "--nbins", "15", "--nbins-quad", "11")
    assert proc.returncode == 0, proc.stderr
    summary = json.loads((tmp_path / "out_summary.json").read_text(encoding="utf-8"))
    assert summary["pair"] == "delta-quad"
    assert summary["qmin"] == 0.0 and summary["qmax"] == 3.0
    assert (tmp_path / "out_delta_axis.dat").read_text(encoding="utf-8").startswith("# IS_mm_s")
    assert (tmp_path / "out_quad_axis.dat").exists()
    # El sintético P(ΔEQ) tiene el pico en ~1.4 mm/s.
    _a, _mx, my, _sx, _sy, _rho = summary["vbf2d_components"][0]
    assert 0.5 < my < 3.0


def test_dist_cli_pair_exige_dist_2d(tmp_path):
    proc = _run_dist_cli(tmp_path, "--pair", "delta-quad")
    assert proc.returncode != 0 and "--dist-2d" in proc.stderr


def test_dist_cli_2d_rechaza_binomial(tmp_path):
    proc = _run_dist_cli(tmp_path, "--dist-2d", "--shape", "binomial")
    assert proc.returncode != 0


def test_dist_cli_scan_alpha_requires_histogram(tmp_path):
    proc = _run_dist_cli(tmp_path, "--shape", "vbf", "--scan-alpha")
    assert proc.returncode != 0
    assert "histograma" in (proc.stderr + proc.stdout)


def test_dist_cli_scan_alpha_usa_el_mismo_kernel(tmp_path):
    """El barrido de α debe ajustar el mismo modelo que el ajuste principal:
    antes omitía --edge-anchor, --d13/--d23 y la física del kernel."""
    import numpy as np
    proc = _run_dist_cli(tmp_path, "--variable", "quad", "--nbins", "20",
                         "--alpha", "0.01", "--edge-anchor", "50",
                         "--scan-alpha", "--alpha-min", "0.01",
                         "--alpha-max", "0.01", "--alpha-count", "1")
    assert proc.returncode == 0, proc.stderr
    summary = json.loads((tmp_path / "out_summary.json").read_text(encoding="utf-8"))
    scan = np.atleast_2d(np.loadtxt(summary["alpha_scan_file"]))
    assert scan[0, 1] == pytest.approx(summary["rms"], rel=1e-9)
