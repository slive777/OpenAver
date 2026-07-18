import pytest
from pathlib import Path
import json
from core import config as core_config

# ── TASK-102c-T1: focal mock 座標共用常數 ──────────────────────────────
# 刻意選一個偏離中心、x/y 不對稱的值，讓「focal 平移有沒有生效」的斷言在
# mock 下依然有鑑別力——不可用 (0.5, 0.5)，否則平移後 crop 退化成置中 crop，
# 反向斷言「應與原碼輸出不同」會失真。各檔按需
# `from tests.conftest import MOCK_FOCAL_XY` 匯入。
# 註：x=0.3148 恰與 wide_offcenter_face.jpg 的真 pigo 偵測值重疊——巧合非刻意
# 逼近，且不影響判別力（patch 整段替換函式，測試期間真偵測不可能被呼叫）。
MOCK_FOCAL_XY = (0.3148, 0.2000)

# ── LAN access gate（feature/80）測試相容 ──────────────────────────────
# web.app 的 lan_access_gate middleware 用 request.client.host 判 loopback。
# Starlette TestClient 預設 client host = "testclient"（非 loopback）→ 單機模式
# （預設）會擋掉任何打路由的測試。所有測試的 TestClient 一律代表「桌面 App 自連」
# = loopback，故在**根 conftest** module-level 把預設 client 設成 127.0.0.1，使
# 「整套跑」與「單檔 isolation 跑」（CLAUDE.md 開發流程 `pytest tests/unit/test_x.py`）
# 行為一致——unit 測試在 isolation 下也不會被閘門 403。
#
# 取捨與邊界：
#   - 必須 module-level class patch（非 autouse fixture）：部分測試在 import 時即
#     `client = TestClient(app)`，早於任何 fixture；patch 須在 conftest import 即生效。
#     替代是逐檔顯式傳 loopback client（大量 churn），取捨後選集中一處。
#   - process-global：setdefault → 顯式 client=(ip,port)（如 gate 矩陣測遠端）永遠覆寫。
#   - idempotent guard：避免重複 wrap。
import starlette.testclient as _starlette_testclient

if not getattr(_starlette_testclient.TestClient, "_openaver_loopback_patched", False):
    _orig_testclient_init = _starlette_testclient.TestClient.__init__

    def _loopback_default_init(self, *args, **kwargs):
        kwargs.setdefault("client", ("127.0.0.1", 50000))
        _orig_testclient_init(self, *args, **kwargs)

    _starlette_testclient.TestClient.__init__ = _loopback_default_init
    _starlette_testclient.TestClient._openaver_loopback_patched = True

@pytest.fixture
def temp_config_path(tmp_path, monkeypatch):
    """
    Mock config path to use a temporary file.
    Avoids modifying the real config.json during tests.
    """
    # Create a temp config file
    d = tmp_path / "config"
    d.mkdir(exist_ok=True)
    p = d / "test_config.json"

    # Write default config
    default_config = core_config.AppConfig().model_dump()
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(default_config, f)

    # Monkeypatch the global CONFIG_PATH variable in core.config module
    monkeypatch.setattr(core_config, "CONFIG_PATH", p)

    return p


# ============ 跨平台環境 Fixtures ============

@pytest.fixture
def mock_wsl_env(monkeypatch):
    """模擬 WSL 環境"""
    import core.path_utils as path_utils
    monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')


@pytest.fixture
def mock_windows_env(monkeypatch):
    """模擬 Windows 環境"""
    import core.path_utils as path_utils
    monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')


@pytest.fixture
def mock_linux_env(monkeypatch):
    """模擬 Linux 環境"""
    import core.path_utils as path_utils
    monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')


@pytest.fixture
def mock_mac_env(monkeypatch):
    """模擬 macOS 環境"""
    import core.path_utils as path_utils
    monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'mac')


# ============ Samples 目錄 Fixtures ============

@pytest.fixture
def samples_dir():
    """取得 samples 測試目錄"""
    from pathlib import Path
    return Path(__file__).parent.parent / 'samples'


# ============ Focal / crop_mode 測試 seed helper（99a-T7：retire update_crop_mode）====

@pytest.fixture
def seed_crop_mode():
    """Test-only seed helper：一條 explicit UPDATE 直接寫 crop_mode 欄位，鏡射
    VideoRepository 端已刪除的同名 mutator（那個一行方法：不碰其他欄位，鏡射
    update_user_tags）——production 已無呼叫端（plan-99a §B.3 拍板 RETIRE），只剩測試
    需要「準備一筆 crop_mode 已是非預設值的 row」這個前置狀態，不該為了測試 seed 需求
    讓已收斂的 mutator 介面再長出一個方法。放在根 conftest（跨 tests/unit 與
    tests/integration 共用），避免三處各自 copy-paste 同一條 UPDATE。

    Usage: `seed_crop_mode(repo, path, 'default')` — repo 為任一 VideoRepository 實例，
    直接用 repo.db_path 開連線寫入，回傳值鏡射原 mutator（rowcount > 0 → True）。
    """
    def _seed(repo, path: str, mode: str) -> bool:
        from core.database import get_connection
        conn = get_connection(repo.db_path)
        try:
            cursor = conn.execute(
                "UPDATE videos SET crop_mode = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (mode, path),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    return _seed


