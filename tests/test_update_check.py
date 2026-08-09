"""Network-free branch coverage for the update-check error reason helper."""

import errno
import json
import socket
import ssl
import urllib.error

import pytest

import simple_una_device_manager as app


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


@pytest.mark.parametrize(("exc", "expected"), [
    (urllib.error.HTTPError("https://example.test", 403, "", {}, None), "GitHub is rate-limiting update checks from this network. Try again later."),
    (urllib.error.HTTPError("https://example.test", 404, "", {}, None), "No published release was found."),
    (urllib.error.HTTPError("https://example.test", 503, "", {}, None), "GitHub is having trouble on its end (HTTP 503)."),
    (urllib.error.HTTPError("https://example.test", 418, "", {}, None), "GitHub returned an error (HTTP 418)."),
    (json.JSONDecodeError("bad JSON", "x", 0), "GitHub returned something unexpected. This often means a proxy or a guest wifi sign-in page answered instead."),
    (urllib.error.URLError(ssl.SSLCertVerificationError("untrusted")), "GitHub's certificate could not be verified. This usually means antivirus or a network filter is inspecting HTTPS traffic."),
    (urllib.error.URLError(ssl.SSLEOFError("closed")), "The secure connection was cut off during the handshake with GitHub."),
    (urllib.error.URLError(ssl.SSLZeroReturnError()), "The secure connection was cut off during the handshake with GitHub."),
    (urllib.error.URLError(ssl.SSLError("failed")), "The secure connection to GitHub failed."),
    (urllib.error.URLError(socket.gaierror("no host")), "The address for api.github.com could not be looked up. Check DNS or the internet connection."),
    (urllib.error.URLError(TimeoutError()), "GitHub didn't respond in time."),
    (urllib.error.URLError(ConnectionRefusedError()), "The connection was refused or reset. A firewall or proxy may be blocking it."),
    (urllib.error.URLError(ConnectionResetError()), "The connection was refused or reset. A firewall or proxy may be blocking it."),
    (urllib.error.URLError(OSError(errno.ENETUNREACH, "unreachable")), "No network connection."),
    (urllib.error.URLError("unknown"), "Couldn't reach GitHub. Check the internet connection."),
    (RuntimeError("unexpected"), "RuntimeError: unexpected"),
])
def test_update_error_reason_branches(exc, expected):
    assert app._update_error_reason(exc) == expected


def test_update_error_reason_truncates_unknown_exception():
    reason = app._update_error_reason(RuntimeError("x" * 200))
    assert reason.endswith("...")
    assert len(reason) == 120


def test_check_update_returns_newer_release_and_logs_success(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout, context):
        assert request.full_url.endswith("/releases/latest")
        assert timeout == 10
        assert context is not None
        return FakeResponse({"tag_name": "v1.4.3"})

    monkeypatch.setattr(app, "urlopen", fake_urlopen)
    monkeypatch.setattr(app.debug, "log", lambda *parts: calls.append(parts))

    assert app.Api().check_update() == {
        "current": app.APP_VERSION,
        "version": "1.4.3",
        "update": True,
        "offline": False,
    }
    assert calls == [("UPDATE check <-", {"latest": "1.4.3", "current": app.APP_VERSION})]


def test_check_update_returns_current_release(monkeypatch):
    monkeypatch.setattr(
        app,
        "urlopen",
        lambda request, timeout, context: FakeResponse({"tag_name": f"v{app.APP_VERSION}"}),
    )

    assert app.Api().check_update() == {
        "current": app.APP_VERSION,
        "version": app.APP_VERSION,
        "update": False,
        "offline": False,
    }


def test_check_update_returns_reason_and_logs_failure(monkeypatch):
    error = urllib.error.URLError(socket.gaierror("no host"))
    calls = []

    def fail_urlopen(request, timeout, context):
        raise error

    monkeypatch.setattr(app, "urlopen", fail_urlopen)
    monkeypatch.setattr(app.debug, "log", lambda *parts: calls.append(parts))

    assert app.Api().check_update() == {
        "current": app.APP_VERSION,
        "version": None,
        "update": False,
        "offline": True,
        "reason": (
            "The address for api.github.com could not be looked up. Check "
            "DNS or the internet connection."
        ),
    }
    assert len(calls) == 1
    assert calls[0][0] == "UPDATE check failed"
    assert calls[0][1].startswith("URLError:")
