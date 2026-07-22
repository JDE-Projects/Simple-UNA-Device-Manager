"""
Tests for Api._build_row, the transform from a raw device record (as the
controller API returns it) to the display row the UI table renders. Covers
a fully-populated record, a record missing every optional field, the name
fallback order (name -> hostname -> mac -> "Unknown"), and unrecognised
state/type codes.
"""

import simple_una_device_manager as app


def _api():
    return app.Api()


def test_build_row_full_record():
    dev = {
        "name": "core-switch", "hostname": "usw-01", "mac": "aa:bb:cc:dd:ee:ff",
        "ip": "10.0.0.5", "model": "USW-24-PoE", "type": "usw", "state": 1,
        "version": "6.6.55", "uptime": 90061,
    }

    row = _api()._build_row(dev, "Main Site", "default")

    assert row["site"] == "Main Site"
    assert row["site_id"] == "default"
    assert row["name"] == "core-switch"
    assert row["mac"] == "aa:bb:cc:dd:ee:ff"
    assert row["ip"] == "10.0.0.5"
    assert row["model"] == "USW-24-PoE"
    assert row["type"] == "Switch"
    assert row["status"] == "Online"
    assert row["status_class"] == "ok"
    assert row["firmware"] == "6.6.55"
    assert row["uptime"] == "1d 1h 1m"
    assert row["uptime_secs"] == 90061


def test_build_row_missing_fields_use_documented_defaults():
    row = _api()._build_row({}, "Main Site", "default")

    assert row["name"] == "Unknown"
    assert row["mac"] == "N/A"
    assert row["ip"] == "N/A"
    assert row["model"] == "N/A"
    assert row["type"] == "Unknown"
    assert row["status"] == "Offline"          # default state is 0
    assert row["status_class"] == "off"
    assert row["firmware"] == "N/A"
    assert row["uptime"] == "N/A"
    assert row["uptime_secs"] == 0


def test_build_row_name_falls_back_to_hostname_then_mac():
    row_hostname = _api()._build_row({"hostname": "switch-1", "mac": "aa:bb:cc"},
                                      "Site", "site")
    assert row_hostname["name"] == "switch-1"

    row_mac = _api()._build_row({"mac": "aa:bb:cc"}, "Site", "site")
    assert row_mac["name"] == "aa:bb:cc"


def test_build_row_unrecognized_state_code():
    row = _api()._build_row({"state": 99}, "Site", "site")

    assert row["status"] == "Unknown (99)"
    assert row["status_class"] == "off"        # not in STATUS_CLASS, defaults to "off"


def test_build_row_unrecognized_type_code_is_uppercased():
    row = _api()._build_row({"type": "uxx"}, "Site", "site")

    assert row["type"] == "UXX"
