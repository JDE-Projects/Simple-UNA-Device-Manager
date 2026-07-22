"""
Tests for Api._uptime_secs and Api._format_uptime, the device-record uptime
transform used to build search result rows. Covers zero, seconds, minutes,
hours, days, and the boundaries the code actually has: zero (and any value
under 60 seconds) is falsy and formats as "N/A"/"0m" rather than showing
seconds, since the formatter has no seconds-only display.
"""

import simple_una_device_manager as app


def _api():
    return app.Api()


def test_uptime_secs_valid_values():
    api = _api()
    assert api._uptime_secs(0) == 0
    assert api._uptime_secs(120) == 120
    assert api._uptime_secs("120") == 120
    assert api._uptime_secs(120.7) == 120


def test_uptime_secs_invalid_or_missing_returns_zero():
    api = _api()
    assert api._uptime_secs(None) == 0
    assert api._uptime_secs("not-a-number") == 0


def test_format_uptime_zero_and_missing_are_not_available():
    # 0 is falsy, so it hits the same "not seconds" branch as missing/None.
    api = _api()
    assert api._format_uptime(0) == "N/A"
    assert api._format_uptime(None) == "N/A"


def test_format_uptime_sub_minute_boundary_shows_zero_minutes():
    # Nonzero but under 60 seconds still reaches the minutes branch, and the
    # formatter has no seconds display, so it reads "0m" rather than "30s".
    api = _api()
    assert api._format_uptime(30) == "0m"
    assert api._format_uptime(59) == "0m"


def test_format_uptime_minutes():
    api = _api()
    assert api._format_uptime(60) == "1m"
    assert api._format_uptime(125) == "2m"


def test_format_uptime_hours():
    api = _api()
    assert api._format_uptime(3600) == "1h 0m"
    assert api._format_uptime(3660) == "1h 1m"


def test_format_uptime_days():
    api = _api()
    assert api._format_uptime(86400) == "1d 0h 0m"
    assert api._format_uptime(90061) == "1d 1h 1m"


def test_format_uptime_invalid_input_is_not_available():
    api = _api()
    assert api._format_uptime("not-a-number") == "N/A"
