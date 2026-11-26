"""隔離燈箱測試伺服器的啟動與回收。"""
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@contextmanager
def serve(home, data, work):
    while True:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        if port not in (8000, 8001):
            break
    url = f'http://127.0.0.1:{port}'
    env = dict(os.environ, HOME=str(home), OPENAVER_DATA_DIR=str(data))
    with (work / 'server.log').open('wb') as log:
        process = subprocess.Popen([str(REPO / 'venv/bin/python'), '-m', 'uvicorn', 'web.app:app',
                                    '--host', '127.0.0.1', '--port', str(port)],
                                   cwd=REPO, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(f'{url}/api/showcase/videos', timeout=2) as response:
                        response.read()
                    break
                except (OSError, urllib.error.URLError):
                    if process.poll() is not None:
                        pytest.fail('隔離伺服器啟動失敗')
                    threading.Event().wait(.25)
            else:
                pytest.fail('隔離伺服器啟動逾時')
            with urllib.request.urlopen(f'{url}/api/gallery/generate', timeout=600) as response:
                events = response.read().decode()
            assert '"type": "error"' not in events and '"type":"error"' not in events
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
