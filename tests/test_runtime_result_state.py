from types import SimpleNamespace

from gui.state import RuntimeResultState


def test_runtime_result_state_tracks_gui_result_and_mode():
    state = RuntimeResultState()
    fit = SimpleNamespace(errors={})
    gui = SimpleNamespace(mode="discrete")

    state.set_discrete_fit(fit, gui_result=gui)

    assert state.fit_result is fit
    assert state.distribution_result is None
    assert state.gui_result is gui
    assert state.active_mode == "discrete"
    assert state.error_source == "covarianza (1σ)"

    state.update_discrete_errors({"a": 1.0})
    assert fit.errors["a"] == 1.0
    state.set_error_source("bootstrap")
    assert state.error_source == "bootstrap"


def test_runtime_result_state_distribution_and_clear_fit():
    state = RuntimeResultState()
    dist = object()
    gui = SimpleNamespace(mode="distribution")

    state.set_distribution_fit(dist, gui_result=gui)

    assert state.distribution_result is dist
    assert state.gui_result is gui
    assert state.active_mode == "distribution"

    state.clear_fit()
    assert state.fit_result is None
    assert state.distribution_result is None
    assert state.gui_result is None
    assert state.active_mode is None
