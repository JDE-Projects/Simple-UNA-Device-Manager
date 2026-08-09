#!/usr/bin/env python3
"""Regenerate the README preview from the real UI at release time only."""

import http.server
import json
import os
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scene  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
OUT_IMAGE = os.path.join(REPO_ROOT, "screenshots", "una-light-dark.png")


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def read_app_version():
    with open(os.path.join(REPO_ROOT, "simple_una_device_manager.py"), encoding="utf-8") as handle:
        match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', handle.read())
    if not match:
        fail("could not find APP_VERSION")
    return match.group(1)


def stage_ui(temp_dir):
    shutil.copy2(os.path.join(REPO_ROOT, "simple_una_device_manager-UI.html"), os.path.join(temp_dir, "index.html"))
    shutil.copy2(os.path.join(REPO_ROOT, "simple_una_device_manager.png"), temp_dir)
    shutil.copytree(os.path.join(REPO_ROOT, "fonts"), os.path.join(temp_dir, "fonts"))


def setup_script(version):
    return (
        f"rows={json.dumps(scene.ROWS)};selected=new Set();connected=true;sortCol='site';sortDir=1;"
        "document.getElementById('connDot').className='dot live';"
        "document.getElementById('connText').textContent='Connected to una.example.test';"
        "document.getElementById('connBtn').textContent='Disconnect';"
        f"document.getElementById('verTag').textContent='v'+{json.dumps(version)};"
        "document.getElementById('statusText').textContent='Search completed';"
        "document.getElementById('countText').textContent=rows.length+' device(s)';"
        "if(typeof render==='function')render();"
    )


def run(command, label):
    if subprocess.run(command, cwd=REPO_ROOT).returncode:
        fail(f"{label} failed")


def main(argv):
    build_tools = os.path.join(os.path.dirname(REPO_ROOT), "build-tools")
    if "--build-tools" in argv:
        index = argv.index("--build-tools") + 1
        if index >= len(argv):
            fail("--build-tools needs a path after it")
        build_tools = argv[index]
    capture = os.path.join(build_tools, "screenshot", "capture.mjs")
    compose = os.path.join(build_tools, "screenshot", "compose.py")
    if not all(os.path.exists(path) for path in (capture, compose)):
        fail("missing screenshot engine. Pass --build-tools with its repository path.")

    temp_dir, httpd = tempfile.mkdtemp(prefix="una-device-manager-screenshot-"), None
    try:
        stage_ui(temp_dir)
        port = free_port()

        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=temp_dir, **kwargs)

        httpd = socketserver.TCPServer(("127.0.0.1", port), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        config = {"url": f"http://127.0.0.1:{port}/index.html", "width": 1800, "height": 1120,
                  "scale": 0.5, "outDir": "shots", "waitFor": "typeof render === 'function'",
                  "setup": setup_script(read_app_version()), "settleMs": 500,
                  "shots": [{"name": "light", "script": "applyTheme('light')"}, {"name": "dark", "script": "applyTheme('dark')"}]}
        config_path = os.path.join(temp_dir, "shots.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2)
        run(["node", capture, config_path], "capture")
        run([sys.executable, compose, OUT_IMAGE, os.path.join(temp_dir, "shots", "light.png"), os.path.join(temp_dir, "shots", "dark.png")], "compose")
    finally:
        if httpd:
            httpd.shutdown()
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1:])
