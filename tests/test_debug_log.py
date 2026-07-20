"""
Tests for the optional debug log's file-handling behaviour: enabling it must
either create the log file or report failure, never silently claim success.
"""

import glob
import os

import simple_una_device_manager as app


def test_set_enabled_true_creates_log_file(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "exe_dir", lambda: str(tmp_path))
    log = app.DebugLog()

    assert log.set_enabled(True) is True
    assert log.is_enabled() is True
    assert glob.glob(os.path.join(str(tmp_path), "Debug_Log_*.txt"))


def test_set_enabled_true_fails_when_dir_missing(tmp_path, monkeypatch):
    missing_dir = tmp_path / "does_not_exist"
    monkeypatch.setattr(app, "exe_dir", lambda: str(missing_dir))
    log = app.DebugLog()

    assert log.set_enabled(True) is False
    assert log.is_enabled() is False


def test_api_set_debug_reports_error_when_log_cannot_be_created(tmp_path, monkeypatch):
    missing_dir = tmp_path / "does_not_exist"
    monkeypatch.setattr(app, "exe_dir", lambda: str(missing_dir))
    monkeypatch.setattr(app, "debug", app.DebugLog())

    api = app.Api()
    result = api.set_debug(True)

    assert result["ok"] is False
    assert isinstance(result.get("error"), str) and result["error"]
