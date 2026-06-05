from pathlib import Path

from gui.state import DistributionViewState


def test_distribution_view_state_alpha_and_session_fragment():
    state = DistributionViewState(
        use_sharp=True,
        refine_global=True,
        shape="Fija",
        reg_mode="tv",
        fixed_distribution_path=Path("p.dat"),
        variable="ΔEQ",
        delta=0.1,
        quad=0.2,
        fixed_bhf=33.0,
        gamma=0.18,
        bmin=0.0,
        bmax=7.0,
        nbins=60,
        log_alpha=-3.0,
        fixed={"delta": False, "gamma": True},
    )

    assert abs(state.alpha - 1e-3) < 1e-12
    assert state.is_fixed("gamma") is True
    assert state.is_fixed("delta") is False
    fragment = state.to_model_state_fragment()
    assert fragment["dist_use_sharp"] is True
    assert fragment["dist_refine_global"] is True
    assert fragment["dist_shape"] == "Fija"
    assert fragment["dist_reg_mode"] == "tv"
    assert fragment["fixed_distribution_path"] == "p.dat"
    assert fragment["dist_variable"] == "ΔEQ"


def test_distribution_view_state_from_historic_model_state():
    restored = DistributionViewState.from_model_state({
        "dist_use_sharp": True,
        "dist_refine_global": False,
        "dist_shape": "Histograma",
        "dist_reg_mode": "tikhonov",
        "fixed_distribution_path": "fixed.tsv",
        "dist_variable": "BHF",
    })

    assert restored.use_sharp is True
    assert restored.refine_global is False
    assert restored.shape == "Histograma"
    assert restored.fixed_distribution_path == Path("fixed.tsv")
    assert restored.variable == "BHF"
