from gui.state import PlotViewState, UiActionState


def test_ui_action_state_exposes_plot_flags_and_fragment():
    state = UiActionState(
        n_components=3,
        plot=PlotViewState(show_residual=False, show_legend=True),
    )

    assert state.n_components == 3
    assert state.show_residual is False
    assert state.show_legend is True
    assert state.to_model_state_fragment() == {
        "n_components": 3,
        "show_residual": False,
        "show_legend": True,
    }
