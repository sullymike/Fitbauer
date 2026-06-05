from pathlib import Path

from gui.state import (
    CalibrationState,
    DistributionViewState,
    FitOptionsState,
    PlotViewState,
    ProjectState,
    RuntimeResultState,
    SpectrumState,
    UiPreferencesState,
)


def test_project_state_roundtrip_preserves_historic_payload_shape():
    project = ProjectState(
        spectrum=SpectrumState(path=Path("/tmp/spec.adt"), file_name="spec.adt", counts=(1.0, 2.0)),
        calibration=CalibrationState({"source": "local", "isomer_shift": -0.11}),
        model_state={"vars": {"baseline": 1.0}, "fixed": {}},
        fit_options=FitOptionsState(likelihood="poisson", fit_velocity=True),
        distribution=DistributionViewState(use_sharp=True, variable="ΔEQ"),
        plot=PlotViewState(show_residual=False, show_legend=True),
    )
    payload = project.to_session_payload()

    assert payload["file_name"] == "spec.adt"
    assert payload["counts"] == [1.0, 2.0]
    assert payload["calibration"]["source"] == "local"
    assert payload["model_state"]["likelihood"] == "poisson"
    assert payload["model_state"]["fit_velocity"] is True
    assert payload["model_state"]["dist_use_sharp"] is True
    assert payload["model_state"]["dist_variable"] == "ΔEQ"
    assert payload["model_state"]["show_residual"] is False

    restored = ProjectState.from_session_payload(payload)
    assert restored.spectrum.file_name == "spec.adt"
    assert restored.fit_options.likelihood == "poisson"
    assert restored.fit_options.fit_velocity is True
    assert restored.distribution.use_sharp is True
    assert restored.distribution.variable == "ΔEQ"
    assert restored.plot.show_residual is False


def test_ui_preferences_state_roundtrip_keeps_existing_settings():
    prefs = UiPreferencesState(
        plot_style="dark",
        color_theme="sepia",
        show_residual=False,
        recent_files=("a.adt", "b.adt"),
        layout_preset="Tres columnas",
        custom_layouts={"Custom 1": {"left_width": 410}},
        ui_language="en",
        qt_style="Fusion",
    )
    data = prefs.to_settings_dict(base={"unrelated": 123})

    assert data["unrelated"] == 123
    assert data["plot_style"] == "dark"
    assert data["recent_files"] == ["a.adt", "b.adt"]

    restored = UiPreferencesState.from_settings_dict(data)
    assert restored.plot_style == "dark"
    assert restored.color_theme == "sepia"
    assert restored.show_residual is False
    assert restored.recent_files == ("a.adt", "b.adt")
    assert restored.custom_layouts["Custom 1"]["left_width"] == 410


def test_runtime_result_state_groups_results_and_clears():
    runtime = RuntimeResultState()
    fit = object()
    dist = object()

    runtime.set_discrete_fit(fit)
    assert runtime.fit_result is fit
    assert runtime.distribution_result is None
    assert runtime.error_source == "covarianza (1σ)"

    runtime.set_distribution_fit(dist)
    assert runtime.distribution_result is dist
    assert runtime.fit_result is fit

    runtime.error_source = "bootstrap Monte Carlo (n=10)"
    runtime.clear()
    assert runtime.fit_result is None
    assert runtime.distribution_result is None
    assert runtime.error_source == "covarianza (1σ)"
