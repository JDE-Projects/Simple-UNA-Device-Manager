"""
Tests for friendly_error and _reason_message. John's rule: a raw [Errno N] or
exception string must never reach the user, so these cover every mapped case
plus the fallback for an exception type the mapping doesn't recognise, which
must still be a plain-language, non-empty string.
"""

import socket
from urllib.error import HTTPError, URLError

import simple_una_device_manager as app


def _http_error(code):
    return HTTPError(url="https://controller.example", code=code,
                      msg="error", hdrs=None, fp=None)


def test_http_error_401_and_403_map_to_login_message():
    for code in (401, 403):
        msg = app.friendly_error(_http_error(code))
        assert "Login failed" in msg
        assert str(code) not in msg


def test_http_error_404_maps_to_url_message():
    msg = app.friendly_error(_http_error(404))
    assert "did not recognise that address" in msg


def test_http_error_other_code_reports_code_without_raw_text():
    msg = app.friendly_error(_http_error(500))
    assert "HTTP 500" in msg


def test_url_error_timeout_reason():
    exc = URLError(socket.timeout("timed out"))
    msg = app.friendly_error(exc)
    assert "did not respond in time" in msg
    assert "Errno" not in msg


def test_url_error_unknown_host_reason():
    exc = URLError(socket.gaierror("getaddrinfo failed"))
    msg = app.friendly_error(exc)
    assert "Could not find that host" in msg


def test_url_error_connection_refused_reason():
    exc = URLError("Connection refused")
    msg = app.friendly_error(exc)
    assert "connection was refused" in msg


def test_url_error_certificate_reason():
    exc = URLError("certificate verify failed")
    msg = app.friendly_error(exc)
    assert "secure-connection problem" in msg


def test_url_error_unreachable_reason():
    exc = URLError("Network is unreachable")
    msg = app.friendly_error(exc)
    assert "could not be reached on the network" in msg


def test_url_error_unrecognized_reason_falls_back_to_generic_reach_message():
    exc = URLError("some other low-level failure")
    msg = app.friendly_error(exc)
    assert "Could not reach the controller" in msg
    assert "some other low-level failure" not in msg


def test_os_error_is_routed_through_reason_message():
    exc = OSError("[Errno 111] Connection refused")
    msg = app.friendly_error(exc)
    assert "connection was refused" in msg
    assert "Errno" not in msg


def test_unrecognized_exception_falls_back_to_plain_language_and_is_not_empty():
    class WeirdException(Exception):
        pass

    msg = app.friendly_error(WeirdException("raw internal detail"))

    assert isinstance(msg, str)
    assert msg != ""
    assert "raw internal detail" not in msg
    assert "Something went wrong" in msg


def test_reason_message_never_returns_empty_string_for_arbitrary_input():
    assert app._reason_message("") != ""
    assert app._reason_message(RuntimeError("boom")) != ""
