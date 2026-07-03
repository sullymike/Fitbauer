from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtWidgets  # noqa: F401
    from gui.distribution_panel import DistributionPanel
    from gui.panels import CalibrationPanel, ComponentPanel
except Exception as exc:  # pragma: no cover
    pytest.skip(f"Qt no disponible: {exc}", allow_module_level=True)


def test_calibration_panel_to_view_state_reflects_controls(qapp):
    panel = CalibrationPanel()
    panel.vmax.set_value(11.5)
    panel.center.set_value(255.5)
    panel.baseline.set_value(0.98)
    panel.slope.set_value(1e-4)
    panel.voigt_sigma.set_value(0.07)
    panel.sat_scale.set_value(2.5)
    panel.fit_velocity.setChecked(True)
    panel.baseline.set_fixed(True)
    panel.set_absorber_model("thickness")
    panel._set_line_profile("Voigt")

    state = panel.to_view_state()

    assert state.vmax == 11.5
    assert state.center == 255.5
    assert state.baseline == 0.98
    assert state.slope == 1e-4
    assert state.voigt_sigma == 0.07
    assert state.sat_scale == 2.5
    assert state.fit_velocity is True
    assert state.line_profile == "Voigt"
    assert state.absorber_model == "thickness"
    assert state.is_fixed("baseline") is True


def test_voigt_sigma_fixed_checkbox_drives_refine(qapp):
    """La casilla 'Fijo' de σ controla el refinado (fit_sigma), solo con Voigt."""
    panel = CalibrationPanel()
    # Por defecto: perfil Lorentziana y σ fija -> no se refina.
    assert panel.voigt_sigma.is_fixed() is True
    assert panel.to_view_state().fit_sigma is False

    # Con Voigt, desmarcar 'Fijo' activa el refinado de σ.
    panel._set_line_profile("Voigt")
    panel.voigt_sigma.set_fixed(False)
    assert panel.to_view_state().fit_sigma is True
    assert panel.fit_sigma.isChecked() is True  # espejo interno sincronizado

    # Volver a marcar 'Fijo' lo desactiva.
    panel.voigt_sigma.set_fixed(True)
    assert panel.to_view_state().fit_sigma is False

    # Fuera de Voigt nunca se refina, aunque quede 'libre'.
    panel.voigt_sigma.set_fixed(False)
    panel._set_line_profile("Lorentziana")
    assert panel.voigt_sigma.is_fixed() is True  # forzada a fija fuera de Voigt
    assert panel.to_view_state().fit_sigma is False


def test_distribution_panel_to_view_state_reflects_controls(qapp):
    panel = DistributionPanel()
    panel.use_sharp.setChecked(True)
    panel.delta.set_value(0.12)
    panel.quad.set_value(-0.2)
    panel.fixed_bhf.set_value(31.0)
    panel.gamma.set_value(0.22)
    panel.bmin.set_value(5.0)
    panel.bmax.set_value(45.0)
    panel.nbins.set_value(40.0)
    panel.log_alpha.set_value(-3.0)
    panel.shape_combo.setCurrentIndex(panel.shape_combo.findData("Gaussiana"))
    panel.reg_mode_combo.setCurrentText("tv")
    panel.delta.set_fixed(True)

    state = panel.to_view_state(variable="quad")

    assert state.variable == "ΔEQ"
    assert state.use_sharp is True
    assert state.shape == "Gaussiana"
    assert state.reg_mode == "tv"
    assert state.delta == 0.12
    assert state.quad == -0.2
    assert state.fixed_bhf == 31.0
    assert state.gamma == 0.22
    assert state.bmin == 5.0
    assert state.bmax == 45.0
    assert state.nbins == 40
    assert abs(state.alpha - 1e-3) < 1e-12
    assert state.is_fixed("delta") is True


def test_component_panel_to_view_state_and_apply_values(qapp):
    panel = ComponentPanel(2)
    panel.enabled.setChecked(True)
    panel.type_combo.setCurrentText("Doblete")
    panel.params["delta"].set_value(0.33)
    panel.params["depth"].set_fixed(True)

    state = panel.to_view_state()

    assert state.idx == 2
    assert state.enabled is True
    assert state.kind == "Doblete"
    assert state.value("delta") == 0.33
    assert state.is_fixed("depth") is True

    panel.apply_values({"s2_delta": 0.44})
    assert panel.to_view_state().value("delta") == 0.44
