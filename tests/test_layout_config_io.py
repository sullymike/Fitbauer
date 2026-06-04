import json

import core.data_io as data_io
import layout.manager as layout_manager
from layout.manager import LayoutManager


def _manager_without_tk() -> LayoutManager:
    return object.__new__(LayoutManager)


def _sample_layout() -> dict:
    return {
        "version": 1,
        "left": ["header"],
        "center": ["info_display"],
        "right": ["sim_controls"],
        "left_width": 321,
        "right_width": 123,
    }


def test_layout_config_is_saved_in_credentials_file(tmp_path, monkeypatch):
    credentials_path = tmp_path / "credentials.json"
    monkeypatch.setattr(data_io, "CREDENTIALS_PATH", credentials_path)
    monkeypatch.setattr(layout_manager, "LAYOUT_PATH", tmp_path / "layout.json")
    monkeypatch.setattr(layout_manager, "USER_PRESETS_PATH", tmp_path / "user_presets.json")

    credentials_path.write_text(
        json.dumps({"username": "demo", "password": "secret"}),
        encoding="utf-8",
    )
    manager = _manager_without_tk()
    layout = _sample_layout()

    manager.save_config(layout)
    manager.save_user_preset("Usuario 1", layout)

    data = json.loads(credentials_path.read_text(encoding="utf-8"))
    assert data["username"] == "demo"
    assert data["password"] == "secret"
    assert data[layout_manager.LAYOUT_CONFIG_KEY] == layout
    assert data[layout_manager.USER_PRESETS_KEY] == {"Usuario 1": layout}
    assert manager.load_config() == layout
    assert manager.load_user_presets() == {"Usuario 1": layout}


def test_legacy_layout_files_are_migrated_to_credentials_file(tmp_path, monkeypatch):
    credentials_path = tmp_path / "credentials.json"
    legacy_layout_path = tmp_path / "layout.json"
    legacy_presets_path = tmp_path / "user_presets.json"
    monkeypatch.setattr(data_io, "CREDENTIALS_PATH", credentials_path)
    monkeypatch.setattr(layout_manager, "LAYOUT_PATH", legacy_layout_path)
    monkeypatch.setattr(layout_manager, "USER_PRESETS_PATH", legacy_presets_path)

    layout = _sample_layout()
    presets = {"Usuario 2": layout}
    legacy_layout_path.write_text(json.dumps(layout), encoding="utf-8")
    legacy_presets_path.write_text(json.dumps(presets), encoding="utf-8")

    manager = _manager_without_tk()

    assert manager.load_config() == layout
    assert manager.load_user_presets() == presets
    migrated = json.loads(credentials_path.read_text(encoding="utf-8"))
    assert migrated[layout_manager.LAYOUT_CONFIG_KEY] == layout
    assert migrated[layout_manager.USER_PRESETS_KEY] == presets
