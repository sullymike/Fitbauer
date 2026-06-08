import sys
from types import SimpleNamespace

from gui.compat import frontend_attr, HistoricalRuntimeCompatMixin
from gui.state import RuntimeResultState


def test_frontend_attr_prefers_mossbauer_qt_symbol(monkeypatch):
    fake = SimpleNamespace(answer="patched")
    monkeypatch.setitem(sys.modules, "mossbauer_qt", fake)

    assert frontend_attr("answer", "fallback") == "patched"
    assert frontend_attr("missing", "fallback") == "fallback"


class _Window(HistoricalRuntimeCompatMixin):
    def __init__(self):
        self.runtime_results = RuntimeResultState()


def test_historical_runtime_compat_properties_delegate_to_state():
    win = _Window()
    fit = object()
    dist = object()

    win.last_fit_result = fit
    win.last_distribution_result = dist
    win.last_error_source = "bootstrap"

    assert win.runtime_results.fit_result is fit
    assert win.runtime_results.distribution_result is dist
    assert win.runtime_results.error_source == "bootstrap"
    assert win.last_fit_result is fit
    assert win.last_distribution_result is dist
