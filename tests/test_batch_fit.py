"""Tests del módulo de ajuste en serie (Capa 1)."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.batch_fit import (  # noqa: E402
    extract_metadata, write_results_csv, collect_trend_data,
)


def test_extract_metadata_numeric_named_group():
    assert extract_metadata("Fe3O4_120K.adt", r"(?P<v>\d+(?:\.\d+)?)\s*K") == 120.0
    assert extract_metadata("muestra_-5.5K_v2.adt", r"(?P<v>[-+]?\d+(?:\.\d+)?)\s*K") == -5.5


def test_extract_metadata_unnamed_group_falls_back_to_group1():
    assert extract_metadata("sample_77K.adt", r"(\d+)K") == 77.0


def test_extract_metadata_text_when_not_numeric():
    assert extract_metadata("hematita_RT.adt", r"_(?P<v>\w+)\.adt") == "RT"


def test_extract_metadata_no_match_returns_none():
    assert extract_metadata("foo.adt", r"NADA(\d+)") is None
    assert extract_metadata("foo.adt", "") is None
    assert extract_metadata("foo.adt", "(") is None  # regex inválido


def test_write_results_csv(tmp_path: Path):
    rows = [
        {"file": "a.adt", "metadata": 50.0, "status": "ok",
         "values": {"s1_bhf": 33.0, "s1_delta": 0.0},
         "errors": {"s1_bhf": 0.05, "s1_delta": 0.002},
         "stats": {"chi2": 1.0, "red_chi2": 0.95}},
        {"file": "b.adt", "metadata": 100.0, "status": "failed",
         "values": {}, "errors": {}, "stats": {}},
    ]
    path = tmp_path / "out.tsv"
    write_results_csv(path, ["s1_bhf", "s1_delta"], rows)
    with path.open() as fh:
        lines = list(csv.reader(fh, delimiter="\t"))
    assert lines[0] == ["file", "metadata", "status", "chi2", "red_chi2",
                        "s1_bhf", "s1_bhf_err", "s1_delta", "s1_delta_err"]
    assert lines[1][0] == "a.adt" and lines[1][2] == "ok"
    assert lines[1][5] == "33.0" and lines[1][6] == "0.05"


def test_collect_trend_data_sorts_and_filters():
    rows = [
        {"status": "ok", "metadata": 100.0,
         "values": {"bhf": 32.0}, "errors": {"bhf": 0.10}},
        {"status": "ok", "metadata": 50.0,
         "values": {"bhf": 33.0}, "errors": {"bhf": 0.05}},
        {"status": "failed", "metadata": 75.0, "values": {}, "errors": {}},
        {"status": "ok", "metadata": "non-numeric",
         "values": {"bhf": 30.0}, "errors": {"bhf": 0.10}},
    ]
    trend = collect_trend_data(rows, ["bhf"])
    assert list(trend["bhf"]) == [(50.0, 33.0, 0.05), (100.0, 32.0, 0.10)]


@pytest.mark.parametrize("name", ["sample_298K.adt", "sample_300K_run2.adt"])
def test_extract_metadata_handles_suffixes(name):
    val = extract_metadata(name, r"(?P<v>\d+(?:\.\d+)?)\s*K")
    assert val in (298.0, 300.0)
