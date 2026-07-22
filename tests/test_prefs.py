"""
Tests for load_prefs / save_prefs, the single JSON file that holds every
persisted setting. load_prefs must be tolerant of a missing or corrupt file
(returning {} rather than raising, so one bad key can't crash startup), and
save_prefs must report failure rather than silently claiming success when
the write can't happen.
"""

import os

import simple_una_device_manager as app


def test_load_prefs_missing_file_returns_empty_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "exe_dir", lambda: str(tmp_path))

    assert app.load_prefs() == {}


def test_load_prefs_corrupt_json_returns_empty_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "exe_dir", lambda: str(tmp_path))
    pref_file = tmp_path / "simple_una_device_manager.pref"
    pref_file.write_text("{not valid json", encoding="utf-8")

    assert app.load_prefs() == {}


def test_load_prefs_non_dict_json_returns_empty_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "exe_dir", lambda: str(tmp_path))
    pref_file = tmp_path / "simple_una_device_manager.pref"
    pref_file.write_text("[1, 2, 3]", encoding="utf-8")

    assert app.load_prefs() == {}


def test_load_prefs_valid_file_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "exe_dir", lambda: str(tmp_path))

    assert app.save_prefs({"theme": "dark"}) is True
    assert app.load_prefs() == {"theme": "dark"}


def test_save_prefs_returns_false_when_directory_missing(tmp_path, monkeypatch):
    missing_dir = tmp_path / "does_not_exist"
    monkeypatch.setattr(app, "exe_dir", lambda: str(missing_dir))

    assert app.save_prefs({"theme": "dark"}) is False
    assert not os.path.exists(missing_dir / "simple_una_device_manager.pref")
