from gui.state import CalibrationViewState


def test_calibration_view_state_values_and_fixed_helpers():
    state = CalibrationViewState(
        vmax=12.0,
        center=256.5,
        baseline=1.0,
        slope=0.0,
        voigt_sigma=0.05,
        sat_scale=5.0,
        line_profile="Voigt",
        absorber_model="thickness",
        fit_velocity=True,
        fit_center=False,
        fit_sigma=True,
        fixed={"baseline": True, "slope": False, "sat_scale": True},
    )

    assert state.value("vmax") == 12.0
    assert state.value("missing", 7.0) == 7.0
    assert state.is_fixed("baseline") is True
    assert state.is_fixed("slope") is False
    assert state.values_dict()["voigt_sigma"] == 0.05
    assert state.absorber_model == "thickness"
    assert state.fit_velocity is True
