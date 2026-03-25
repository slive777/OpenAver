"""共用 fixtures — e2e 測試層（瀏覽器 + FastAPI server 管理）"""
import socket
import subprocess
import time
import pytest
from pathlib import Path


def is_port_in_use(port: int) -> bool:
    """檢查 port 是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


@pytest.fixture(scope="session")
def ensure_e2e_server():
    """
    確保 E2E 用 API 服務可用（e2e tests 專用，port 8001）

    - 如果 port 8001 已有服務：直接使用（不會關閉）
    - 如果沒有服務：啟動 uvicorn，測試完後關閉
    """
    port = 8001
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
        # 等待服務啟動（最多 15 秒）
        for _ in range(30):
            if is_port_in_use(port):
                break
            time.sleep(0.5)
        else:
            pytest.skip("無法啟動 e2e server（port 8001）")

    yield f"http://localhost:{port}"

    # 只關閉我們啟動的服務
    if started_by_us and process:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture(scope="session")
def base_url(ensure_e2e_server):
    """提供 e2e 測試用 base URL（http://localhost:8001）"""
    return ensure_e2e_server
