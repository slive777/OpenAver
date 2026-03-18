"""共用 fixtures — smoke 測試層（外部服務管理）"""
import json
import socket
import subprocess
import time
import os
import pytest
import requests as req_lib
from pathlib import Path


def is_port_in_use(port: int) -> bool:
    """檢查 port 是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def is_ollama_available() -> bool:
    """檢查 Ollama 服務是否可用"""
    try:
        resp = req_lib.get("http://localhost:11434/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def is_gemini_configured() -> bool:
    """檢查 Gemini API key 是否已設定"""
    config_path = Path(__file__).parent.parent.parent / "web" / "config.json"
    if not config_path.exists():
        return False
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        api_key = cfg.get("translate", {}).get("gemini", {}).get("api_key", "")
        return bool(api_key and len(api_key) > 10)
    except Exception:
        return False


@pytest.fixture(scope="session")
def ensure_api_server():
    """
    確保 API 服務可用（smoke tests 專用）

    - 如果 port 8000 已有服務：直接使用（不會關閉）
    - 如果沒有服務：啟動 uvicorn，測試完後關閉
    """
    port = 8000
    started_by_us = False
    process = None

    if not is_port_in_use(port):
        # 沒有服務，啟動一個
        venv_uvicorn = Path(__file__).parent.parent.parent / "venv" / "bin" / "uvicorn"
        process = subprocess.Popen(
            [str(venv_uvicorn), "web.app:app", "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(Path(__file__).parent.parent.parent)
        )
        started_by_us = True
        # 等待服務啟動
        for _ in range(30):
            if is_port_in_use(port):
                break
            time.sleep(0.5)
        else:
            pytest.skip("無法啟動 API 服務")

    yield f"http://localhost:{port}"

    # 只關閉我們啟動的服務
    if started_by_us and process:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


# Smoke test skip 條件
def skip_if_no_ollama():
    """Ollama 不可用時 skip"""
    return pytest.mark.skipif(
        not is_ollama_available(),
        reason="Ollama 未啟動（Windows 請開啟 Ollama 應用程式）"
    )


def skip_if_no_gemini():
    """Gemini 未設定時 skip"""
    return pytest.mark.skipif(
        not is_gemini_configured(),
        reason="Gemini API key 未設定（請在設定頁面填入）"
    )
