"""
Simple UNA Device Manager
A standalone desktop tool to search devices across all sites on a UniFi Network
Application controller (by MAC, name, or IP) and remove orphaned or
unmanageable devices that can't be cleared from the UNA web UI.

Deletes are destructive and require confirmation. Backend: urllib (standard
library) against the controller API. Window: pywebview on the Qt backend,
UI in simple_una_device_manager-UI.html.

Built with AI assistance, directed by JDE-Projects.
"""

import os

# Force the LGPL Qt binding (PySide6) so qtpy never selects PyQt6 (GPL),
# both at build time and at runtime. Set before importing webview/qtpy.
os.environ.setdefault("QT_API", "pyside6")

import re
import sys
import ssl
import csv
import json
import time
import socket
import threading
import traceback
import webbrowser
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import (Request, HTTPCookieProcessor, build_opener,
                            HTTPSHandler, urlopen)
from urllib.error import URLError, HTTPError
from http.cookiejar import CookieJar

import webview


# ───────────────────────── identity ─────────────────────────
APP_VERSION = "1.2.0"          # version of record; equals the latest release tag (no "v")
GITHUB_OWNER = "JDE-Projects"
GITHUB_REPO = "Simple-UNA-Device-Manager"
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"


# ───────────────────────── paths ─────────────────────────
def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def exe_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ───────────── optional debug log (off by default) ─────────────
class DebugLog:
    def __init__(self):
        self._enabled = False
        self._path = None
        self._lock = threading.Lock()

    def set_enabled(self, on):
        with self._lock:
            on = bool(on)
            if on and not self._path:
                stamp = datetime.now().strftime("%m%d%Y_%H%M%S")
                self._path = os.path.join(exe_dir(), f"Debug_Log_{stamp}.txt")
                try:
                    with open(self._path, "w", encoding="utf-8") as f:
                        f.write("=== Simple UNA Device Manager debug log ===\n")
                        f.write(f"Started: {datetime.now().isoformat()}\n" + "=" * 60 + "\n\n")
                except Exception:
                    self._path = None
                    self._enabled = False
                    return False
            self._enabled = on
            return True

    def is_enabled(self):
        return self._enabled

    def log(self, label, content=""):
        if not self._enabled or not self._path:
            return
        try:
            with self._lock:
                with open(self._path, "a", encoding="utf-8") as f:
                    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    f.write(f"[{ts}] {label}\n")
                    if content:
                        if isinstance(content, (dict, list)):
                            content = json.dumps(content, indent=2, default=str)
                        f.write(f"{content}\n")
                    f.write("\n")
        except Exception:
            pass


debug = DebugLog()


def redact_payload(payload):
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    for k in ("password", "passwd", "x_password"):
        if k in out:
            out[k] = "***REDACTED***"
    return out


# ─────────────── plain-language errors ───────────────
# Never surface a raw [Errno N] or exception text to the user. Map to a short
# message and send the full detail to the debug log.
def _reason_message(reason):
    text = str(reason).lower()
    if isinstance(reason, socket.timeout) or "timed out" in text or "timeout" in text:
        return "The controller did not respond in time. Check the URL and port are reachable."
    if (isinstance(reason, socket.gaierror) or "getaddrinfo" in text
            or "name or service not known" in text or "nodename nor servname" in text):
        return "Could not find that host. Check the controller URL."
    if "refused" in text:
        return "The connection was refused. Check the controller is running and the port is correct."
    if "certificate" in text or "ssl" in text:
        return ("There was a secure-connection problem reaching the controller. "
                "If it uses a self-signed certificate, turn off 'Verify TLS certificate'.")
    if "unreachable" in text or "no route" in text:
        return "The controller could not be reached on the network."
    return "Could not reach the controller. Check the URL, port, and your network."


def friendly_error(exc, context=""):
    """Return a short, user-facing message. Full detail goes to the debug log."""
    debug.log(f"ERROR detail{(' - ' + context) if context else ''}", traceback.format_exc())
    if isinstance(exc, HTTPError):
        if exc.code in (401, 403):
            return ("Login failed. Check the username and password, and that this is a "
                    "local admin account (not SSO).")
        if exc.code == 404:
            return "The controller did not recognise that address. Check the URL."
        return f"The controller returned an error (HTTP {exc.code})."
    if isinstance(exc, URLError):
        return _reason_message(getattr(exc, "reason", exc))
    if isinstance(exc, OSError):
        return _reason_message(exc)
    return "Something went wrong. Turn on the debug log and retry to capture details."


def _version_gt(a, b):
    """True if version string a is newer than b (numeric, dot/dash separated)."""
    def parts(v):
        return [int(p) if p.isdigit() else 0 for p in re.split(r"[.\-]", v) if p != ""]
    pa, pb = parts(a), parts(b)
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return pa > pb


# ───────────────────────── label maps ─────────────────────────
STATE_LABELS = {
    0: "Offline", 1: "Online", 2: "Pending Adoption", 4: "Updating",
    5: "Provisioning", 6: "Unreachable", 7: "Adopting", 9: "Adoption Error",
    10: "Adoption Failed", 11: "Isolated",
}
TYPE_LABELS = {
    "usw": "Switch", "uap": "Access Point", "ugw": "Gateway", "udm": "Dream Machine",
    "uxg": "Gateway", "ubb": "Building Bridge", "ulte": "LTE Backup",
}
SEARCH_FIELDS = ["MAC", "Hostname", "IP"]
HINT_TEXTS = {
    "MAC": "Search by full or partial MAC address (fastest).",
    "Hostname": "Search by full or partial device name (full scan, slower).",
    "IP": "Search by full or partial IP address (full scan, slower).",
}
# status -> semantic colour class used by the UI
STATUS_CLASS = {
    "Online": "ok", "Offline": "off", "Unreachable": "bad", "Isolated": "bad",
    "Adoption Error": "bad", "Adoption Failed": "bad", "Pending Adoption": "warn",
    "Adopting": "warn", "Provisioning": "warn", "Updating": "warn",
}


class Api:
    def __init__(self):
        self._window = None
        self.connected = False
        self.opener = None
        self.cookie_jar = None
        self.ssl_ctx = None
        self.verify_tls = False   # off by default: self-hosted controllers use self-signed certs
        self.sites = []
        self.controller_url = ""
        self._cred_user = ""
        self._cred_pass = ""
        self._opener_lock = threading.Lock()
        self._reauth_lock = threading.Lock()
        self._keepalive_timer = None
        self._last_rows = []

    def set_window(self, w):
        self._window = w

    def get_meta(self):
        return {"search_fields": SEARCH_FIELDS, "default_field": "MAC",
                "hints": HINT_TEXTS, "version": APP_VERSION}

    # ─── update check (GitHub Releases, stdlib only, no token) ───
    def check_update(self, manual=False):
        """Compare the latest published release tag to APP_VERSION.
        Quiet on any failure unless the user asked (manual=True)."""
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
        debug.log("UPDATE check ->", url)
        try:
            req = Request(url, headers={"Accept": "application/vnd.github+json",
                                        "User-Agent": "Simple-UNA-Device-Manager"})
            with urlopen(req, timeout=8, context=ssl.create_default_context()) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = (data.get("tag_name") or "").lstrip("vV").strip()
            page = data.get("html_url") or RELEASES_PAGE
            debug.log("UPDATE check <-", {"latest": latest, "current": APP_VERSION})
            if latest and _version_gt(latest, APP_VERSION):
                return {"ok": True, "update": True, "latest": latest,
                        "current": APP_VERSION, "url": page}
            return {"ok": True, "update": False, "current": APP_VERSION, "latest": latest}
        except HTTPError as e:
            # 404 = repo still private or no releases yet. Stay quiet.
            debug.log("UPDATE check HTTPError", str(e.code))
            return {"ok": False, "quiet": True,
                    "error": "No published releases found yet."}
        except Exception as e:
            debug.log("UPDATE check failed", str(e))
            return {"ok": False, "quiet": not manual,
                    "error": "Could not reach GitHub to check for updates."}

    def open_url(self, url):
        """Open a link in the system browser (used by the update banner)."""
        try:
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                webbrowser.open(url)
                return {"ok": True}
        except Exception as e:
            debug.log("open_url failed", str(e))
        return {"ok": False}

    def set_debug(self, enabled):
        ok = debug.set_enabled(enabled)
        debug.log("Debug logging enabled" if enabled and ok else "Debug logging disabled")
        return {"ok": ok, "enabled": debug.is_enabled()}

    # ─── theme preference (local .pref file next to the app) ───
    def _pref_path(self):
        return os.path.join(exe_dir(), "simple_una_device_manager.pref")

    def _load_theme(self):
        try:
            with open(self._pref_path(), "r", encoding="utf-8") as f:
                theme = json.load(f).get("theme")
            return theme if theme in ("dark", "light") else "dark"
        except Exception:
            return "dark"

    def get_theme(self):
        return self._load_theme()

    def save_theme(self, theme):
        if theme not in ("dark", "light"):
            return {"ok": False}
        try:
            with open(self._pref_path(), "w", encoding="utf-8") as f:
                json.dump({"theme": theme}, f)
            debug.log(f"Theme set to {theme}")
            return {"ok": True}
        except Exception as e:
            debug.log("Could not save theme pref", str(e))
            return {"ok": False}

    # ─── connection ───
    def _create_opener(self):
        self.ssl_ctx = ssl.create_default_context()
        if not self.verify_tls:
            # Default: self-hosted controllers ship a self-signed certificate,
            # so verification is off unless the user opts in.
            self.ssl_ctx.check_hostname = False
            self.ssl_ctx.verify_mode = ssl.CERT_NONE
        self.cookie_jar = CookieJar()
        self.opener = build_opener(HTTPSHandler(context=self.ssl_ctx),
                                   HTTPCookieProcessor(self.cookie_jar))

    def _do_login(self):
        self._create_opener()
        debug.log(f"LOGIN -> {self.controller_url}/api/login",
                  f"username: {self._cred_user}\npassword: ***REDACTED***")
        body = json.dumps({"username": self._cred_user, "password": self._cred_pass}).encode("utf-8")
        req = Request(f"{self.controller_url}/api/login", data=body,
                      headers={"Content-Type": "application/json"})
        resp = self.opener.open(req)
        debug.log(f"LOGIN <- {resp.getcode()}")
        return resp.getcode() == 200

    def _safe_reauth(self):
        with self._reauth_lock:
            self._do_login()

    def _api_request(self, path, method="GET", data=None, retry=True):
        url = f"{self.controller_url}{path}"
        debug.log(f"REQUEST -> {method} {url}", redact_payload(data) if data else "")
        try:
            with self._opener_lock:
                if data is not None:
                    req = Request(url, data=json.dumps(data).encode("utf-8"),
                                  headers={"Content-Type": "application/json"})
                    req.get_method = lambda: "POST"
                else:
                    req = Request(url)
                    if method == "POST":
                        req.data = b""
                        req.add_header("Content-Type", "application/json")
                        req.get_method = lambda: "POST"
                resp = self.opener.open(req)
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            debug.log(f"HTTPError {e.code} on {url}", str(e.reason))
            if e.code == 401 and retry:
                self._safe_reauth()
                return self._api_request(path, method, data, retry=False)
            raise
        except (URLError, OSError) as e:
            debug.log(f"URLError/OSError on {url}", str(e))
            if retry:
                self._safe_reauth()
                return self._api_request(path, method, data, retry=False)
            raise

    def connect(self, url, user, pwd, verify=False):
        url = (url or "").strip().rstrip("/")
        user = (user or "").strip()
        pwd = (pwd or "").strip()
        if not url or not user or not pwd:
            return {"ok": False, "error": "Please fill in all connection fields."}
        self.verify_tls = bool(verify)
        self.controller_url = url
        self._cred_user = user
        self._cred_pass = pwd
        debug.log("=" * 60)
        debug.log("CONNECT", {"url": url, "user": user})
        try:
            self._do_login()
            data = self._api_request("/api/self/sites")
            self.sites = data.get("data", []) if isinstance(data, dict) else []
            self.connected = True
            self._start_keepalive()
            return {"ok": True, "site_count": len(self.sites)}
        except Exception as e:
            self.connected = False
            debug.log("CONNECT failed", str(e))
            return {"ok": False, "error": friendly_error(e, "connect")}

    def disconnect(self):
        self._stop_keepalive()
        if self.opener and self.controller_url:
            try:
                req = Request(f"{self.controller_url}/api/logout", data=b"",
                              headers={"Content-Type": "application/json"})
                req.get_method = lambda: "POST"
                self.opener.open(req)
            except Exception:
                pass
        self.connected = False
        self.sites = []
        self.opener = None
        self.cookie_jar = None
        self._cred_pass = ""
        self._last_rows = []
        debug.log("DISCONNECTED")
        return {"ok": True}

    def _start_keepalive(self):
        self._stop_keepalive()
        self._keepalive_timer = threading.Timer(300, self._keepalive_tick)
        self._keepalive_timer.daemon = True
        self._keepalive_timer.start()

    def _stop_keepalive(self):
        if self._keepalive_timer:
            self._keepalive_timer.cancel()
            self._keepalive_timer = None

    def _keepalive_tick(self):
        if self.connected:
            try:
                self._api_request("/api/self/sites")
            except Exception:
                pass
            self._start_keepalive()

    # ─── search ───
    def _progress(self, done, total, phase=""):
        if self._window:
            try:
                self._window.evaluate_js(
                    f"window.onSearchProgress && window.onSearchProgress({done},{total},{json.dumps(phase)})")
            except Exception:
                pass

    def _build_row(self, dev, site_desc, site_name):
        name = dev.get("name") or dev.get("hostname") or dev.get("mac", "Unknown")
        t_raw = dev.get("type", "")
        state = dev.get("state", 0)
        status = STATE_LABELS.get(state, f"Unknown ({state})")
        return {
            "site": site_desc, "site_id": site_name, "name": name,
            "mac": dev.get("mac", "N/A"), "ip": dev.get("ip", "N/A"),
            "model": dev.get("model", "N/A"),
            "type": TYPE_LABELS.get(t_raw, (t_raw.upper() or "Unknown")),
            "status": status, "status_class": STATUS_CLASS.get(status, "off"),
            "firmware": dev.get("version", "N/A"),
            "uptime": self._format_uptime(dev.get("uptime")),
            "uptime_secs": self._uptime_secs(dev.get("uptime")),
        }

    def _uptime_secs(self, seconds):
        try:
            return int(seconds)
        except (ValueError, TypeError):
            return 0

    def _format_uptime(self, seconds):
        if not seconds:
            return "N/A"
        try:
            seconds = int(seconds)
        except (ValueError, TypeError):
            return "N/A"
        d, h, m = seconds // 86400, (seconds % 86400) // 3600, (seconds % 3600) // 60
        if d > 0:
            return f"{d}d {h}h {m}m"
        if h > 0:
            return f"{h}h {m}m"
        return f"{m}m"

    def run_search(self, term, field):
        if not self.connected:
            return {"ok": False, "error": "Not connected."}
        term = (term or "").strip()  # empty matches everything: "show all"
        field = field if field in SEARCH_FIELDS else "MAC"
        term_lower = term.lower()
        total = len(self.sites)
        failed = 0
        rows = []
        debug.log("SEARCH", {"term": term, "field": field, "sites": total})
        try:
            if field == "MAC":
                rows, failed = self._search_mac(term_lower, total)
            else:
                rows, failed = self._search_full(term_lower, field, total)
            rows.sort(key=lambda r: (r["site"].lower(), r["name"].lower()))
            self._last_rows = rows
            debug.log("SEARCH complete", {"matches": len(rows), "failed_sites": failed})
            return {"ok": True, "rows": rows, "failed_sites": failed}
        except Exception as e:
            debug.log("SEARCH exception", traceback.format_exc())
            return {"ok": False, "error": friendly_error(e, "search")}

    def _search_mac(self, term_lower, total):
        # pass 1: cheap device-basic scan to find sites with a match
        matched, failed, done = [], 0, 0
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(self._scan_basic, s, term_lower): s for s in self.sites}
            for fut in as_completed(futs):
                done += 1
                self._progress(done, total, "Quick scan")
                try:
                    site, hit, err = fut.result()
                    if err:
                        failed += 1
                    elif hit:
                        matched.append(site)
                except Exception:
                    failed += 1
        # pass 2: full device detail only for matched sites
        rows = []
        if matched:
            self._progress(0, len(matched), "Fetching details")
            done = 0
            with ThreadPoolExecutor(max_workers=10) as ex:
                futs = {ex.submit(self._fetch_full_mac, s, term_lower): s for s in matched}
                for fut in as_completed(futs):
                    done += 1
                    self._progress(done, len(matched), "Fetching details")
                    try:
                        res, err = fut.result()
                        if err:
                            failed += 1
                        rows.extend(res)
                    except Exception:
                        failed += 1
        return rows, failed

    def _scan_basic(self, site, term_lower):
        name = site.get("name", "")
        try:
            data = self._api_request(f"/api/s/{name}/stat/device-basic")
            for dev in data.get("data", []):
                if term_lower in (dev.get("mac") or "").lower():
                    return site, True, False
            return site, False, False
        except Exception:
            return site, False, True

    def _fetch_full_mac(self, site, term_lower):
        name = site.get("name", "")
        desc = site.get("desc", name)
        rows = []
        try:
            data = self._api_request(f"/api/s/{name}/stat/device")
            for dev in data.get("data", []):
                if term_lower in (dev.get("mac") or "").lower():
                    rows.append(self._build_row(dev, desc, name))
            return rows, False
        except Exception:
            return rows, True

    def _search_full(self, term_lower, field, total):
        rows, failed, done = [], 0, 0
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(self._scan_full, s, term_lower, field): s for s in self.sites}
            for fut in as_completed(futs):
                done += 1
                self._progress(done, total, "Scanning")
                try:
                    res, err = fut.result()
                    if err:
                        failed += 1
                    rows.extend(res)
                except Exception:
                    failed += 1
        return rows, failed

    def _scan_full(self, site, term_lower, field):
        name = site.get("name", "")
        desc = site.get("desc", name)
        rows = []
        try:
            data = self._api_request(f"/api/s/{name}/stat/device")
            for dev in data.get("data", []):
                if field == "Hostname":
                    val = (dev.get("name") or dev.get("hostname") or "").lower()
                else:
                    val = (dev.get("ip") or "").lower()
                if term_lower in val:
                    rows.append(self._build_row(dev, desc, name))
            return rows, False
        except Exception:
            return rows, True

    # ─── delete (destructive; UI confirms first) ───
    def delete_devices(self, devices):
        if not self.connected:
            return {"ok": False, "error": "Not connected."}
        devices = devices or []
        success, errors = [], []
        debug.log("DELETE requested", [f"{d.get('name')} ({d.get('mac')})" for d in devices])
        for d in devices:
            try:
                self._api_request(f"/api/s/{d['site_id']}/cmd/sitemgr",
                                  method="POST",
                                  data={"cmd": "delete-device", "mac": d["mac"]})
                success.append(d.get("mac"))
                debug.log("DELETED", f"{d.get('name')} ({d.get('mac')}) @ {d.get('site_id')}")
            except Exception as e:
                errors.append(f"{d.get('name')} ({d.get('mac')}): {friendly_error(e, 'delete')}")
                debug.log("DELETE error", f"{d.get('mac')}: {e}")
        return {"ok": True, "success": success, "errors": errors}

    # ─── CSV export ───
    def export_csv(self, rows):
        rows = rows or self._last_rows
        if not rows:
            return {"ok": False, "error": "Nothing to export."}
        if not self._window:
            return {"ok": False, "error": "No window."}
        try:
            dlg = webview.FileDialog.SAVE
        except AttributeError:  # older pywebview
            dlg = webview.SAVE_DIALOG
        result = self._window.create_file_dialog(
            dlg, save_filename="una_device_export.csv",
            file_types=("CSV file (*.csv)", "All files (*.*)"))
        if not result:
            return {"ok": False, "cancelled": True}
        path = result if isinstance(result, str) else result[0]
        if not path.lower().endswith(".csv"):
            path += ".csv"
        cols = [("site", "site"), ("site_id", "site_id"), ("name", "name"),
                ("mac", "mac"), ("ip", "ip"), ("model", "model"), ("type", "type"),
                ("status", "status"), ("firmware", "firmware"), ("uptime", "uptime")]
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([h for _, h in cols])
                for r in rows:
                    w.writerow([r.get(k, "") for k, _ in cols])
            debug.log("EXPORT", f"{len(rows)} rows -> {path}")
            return {"ok": True, "path": path, "count": len(rows)}
        except Exception as e:
            debug.log("EXPORT failed", traceback.format_exc())
            return {"ok": False, "error": "Could not save the CSV file. Check the location and try again."}


# ───────────────────────── splash ─────────────────────────
try:
    import pyi_splash  # type: ignore
    HAS_SPLASH = True
except Exception:
    HAS_SPLASH = False

_splash_lock = threading.Lock()
_splash_done = False
_start_time = time.time()


def _close_splash():
    global _splash_done
    with _splash_lock:
        if _splash_done:
            return
        _splash_done = True
    if HAS_SPLASH:
        try:
            pyi_splash.close()
        except Exception:
            pass


def _on_loaded():
    threading.Timer(max(0.0, 5.0 - (time.time() - _start_time)), _close_splash).start()


def main():
    if HAS_SPLASH:
        threading.Timer(30.0, _close_splash).start()
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "JDEProjects.SimpleUNADeviceManager")
        except Exception:
            pass

    api = Api()
    window = webview.create_window(
        "Simple UNA Device Manager",
        url=resource_path("simple_una_device_manager-UI.html"),
        js_api=api, width=1400, height=850, min_size=(1100, 700),
        background_color="#0a0e14",
    )
    api.set_window(window)
    window.events.loaded += _on_loaded
    try:
        webview.start(gui="qt", icon=resource_path("simple_una_device_manager.png"))
    except TypeError:
        webview.start(gui="qt")


if __name__ == "__main__":
    main()
