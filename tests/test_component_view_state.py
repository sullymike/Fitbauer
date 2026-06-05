from gui.state import ComponentViewState


def test_component_view_state_helpers_prefix_values_and_fixed_flags():
    state = ComponentViewState(
        idx=2,
        enabled=True,
        kind="Sextete",
        intensity_mode="free",
        quad_treatment="1st_order",
        values={"delta": 0.12, "depth": 0.03},
        fixed={"delta": False, "depth": True},
    )

    assert state.value("delta") == 0.12
    assert state.value("missing", 4.5) == 4.5
    assert state.is_fixed("depth") is True
    assert state.prefixed_values() == {"s2_delta": 0.12, "s2_depth": 0.03}
    assert state.prefixed_fixed() == {"s2_delta": False, "s2_depth": True}
