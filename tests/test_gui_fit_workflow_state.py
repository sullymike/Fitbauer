import numpy as np

from gui.fit_workflow import GuiFitRenderState, GuiFitResult


def test_gui_fit_result_wraps_render_state():
    v = np.array([-1.0, 0.0, 1.0])
    y = np.array([1.0, 0.9, 1.0])
    model = np.array([0.99, 0.91, 0.99])
    render = GuiFitRenderState(
        velocity=v,
        y_data=y,
        model=model,
        residual=y - model,
        components=[(1, "Singlete", model)],
    )
    result = GuiFitResult(
        mode="discrete",
        raw_result={"ok": True},
        render=render,
        message="χ²=1",
    )

    assert result.mode == "discrete"
    assert result.raw_result["ok"] is True
    assert result.message == "χ²=1"
    assert result.render is render
    assert result.render.components[0][1] == "Singlete"
