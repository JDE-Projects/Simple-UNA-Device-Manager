"""
Tests for redact_payload's contract: this is the only thing standing between
a user's debug log and their password, since users email that log for
support. Pins exactly which keys it redacts, that non-dict payloads pass
through unchanged, and that the caller's structure is never mutated at any
depth.

Matching is case-insensitive against a normalized key (lowercased, dashes
folded to underscores) built from the same three base names. Redaction
recurses into nested dicts and into dicts nested inside lists, with a guard
so a self-referencing structure can't recurse forever.
"""

import simple_una_device_manager as app


def test_redacts_known_password_keys():
    payload = {"username": "admin", "password": "hunter2",
               "passwd": "hunter2", "x_password": "hunter2"}

    out = app.redact_payload(payload)

    assert out["username"] == "admin"
    assert out["password"] == "***REDACTED***"
    assert out["passwd"] == "***REDACTED***"
    assert out["x_password"] == "***REDACTED***"


def test_non_dict_payload_returned_unchanged():
    assert app.redact_payload("password=hunter2") == "password=hunter2"
    assert app.redact_payload(None) is None
    assert app.redact_payload(["password", "hunter2"]) == ["password", "hunter2"]
    assert app.redact_payload(42) == 42


def test_does_not_mutate_callers_dict():
    payload = {"password": "hunter2"}

    out = app.redact_payload(payload)

    assert payload["password"] == "hunter2"
    assert out is not payload


def test_key_matching_is_case_insensitive():
    payload = {"Password": "hunter2", "PASSWD": "hunter2", "X-Password": "hunter2"}

    out = app.redact_payload(payload)

    assert out["Password"] == "***REDACTED***"
    assert out["PASSWD"] == "***REDACTED***"
    assert out["X-Password"] == "***REDACTED***"


def test_nested_password_in_sub_dict_is_redacted():
    payload = {"credentials": {"password": "hunter2"}}

    out = app.redact_payload(payload)

    assert out["credentials"]["password"] == "***REDACTED***"


def test_password_nested_multiple_levels_deep_is_redacted():
    payload = {"a": {"b": {"c": {"password": "hunter2"}}}}

    out = app.redact_payload(payload)

    assert out["a"]["b"]["c"]["password"] == "***REDACTED***"


def test_password_inside_dict_nested_in_list_is_redacted():
    payload = {"users": [{"name": "admin", "password": "hunter2"},
                          {"name": "guest", "password": "hunter2"}]}

    out = app.redact_payload(payload)

    assert out["users"][0]["password"] == "***REDACTED***"
    assert out["users"][0]["name"] == "admin"
    assert out["users"][1]["password"] == "***REDACTED***"


def test_password_inside_list_nested_in_list_is_redacted():
    payload = {"groups": [[{"password": "hunter2"}]]}

    out = app.redact_payload(payload)

    assert out["groups"][0][0]["password"] == "***REDACTED***"


def test_does_not_mutate_nested_structures():
    payload = {"credentials": {"password": "hunter2"},
               "users": [{"password": "hunter2"}]}

    out = app.redact_payload(payload)

    assert payload["credentials"]["password"] == "hunter2"
    assert payload["users"][0]["password"] == "hunter2"
    assert out["credentials"] is not payload["credentials"]
    assert out["users"] is not payload["users"]
    assert out["users"][0] is not payload["users"][0]


def test_self_referencing_dict_does_not_recurse_forever():
    payload = {"password": "hunter2"}
    payload["self"] = payload  # cycle

    out = app.redact_payload(payload)

    assert out["password"] == "***REDACTED***"
    assert out["self"] is payload  # cycle guard returns the original reference


def test_self_referencing_list_does_not_recurse_forever():
    payload = {"items": []}
    payload["items"].append(payload["items"])  # cycle

    out = app.redact_payload(payload)

    # The outer list is rebuilt fresh (first time it's seen); the guard
    # kicks in one level down, where the cycle repeats it, and that inner
    # occurrence comes back as the original reference rather than looping.
    assert out["items"] is not payload["items"]
    assert out["items"][0] is payload["items"]


def test_unrelated_keys_pass_through_untouched():
    payload = {"username": "admin", "url": "https://controller.local"}

    out = app.redact_payload(payload)

    assert out == payload
