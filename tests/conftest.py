import pytest
import socket
import sqlite3
from pathlib import Path
import json
from core import config as core_config
import _repo_write_guard as _rwg
import _outbound_guard as _og

# TASK-127b-T5：`pytester` 子 session 的 mutation 自驗（`test_repo_write_guard_
# subsession.py`）——pytest 的硬性要求是這行必須放在 root conftest。本專案沒有
# 任何 pytester 先例，這是第一支使用它的測試。
pytest_plugins = ["pytester"]

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


# ============ TASK-127b-T3/T5：G1／G2 repo-write 守衛（autouse，預設 fail）====
#
# 根因（見 feature/127-gotchas-triage/TASK-127b-T3.md「現況分析」）：任何測試只要
# `patch("core.enricher.VideoRepository")` 而沒設 `mock_repo.db_path`，
# `repo.db_path` 是 MagicMock → 產品碼在 3 個檔 7 處呼叫 `sqlite3.connect(...)`
# 前一律先 `str(db_path)`／f-string 化 → 建出檔名為
# `<MagicMock name='...' id='...'>` 的空 SQLite，寫進 repo 根，`nfo_mtime` 回填
# 路徑從沒被真的執行過（被 `except Exception` 吞掉）。
#
# G1：patch 真正的 sink `sqlite3.connect`（不是 `get_connection` 定義處——見
# BE-TEST-01 §1／§3，24 個 import landing point 會漂）。判定邏輯是純函式
# （`tests/_repo_write_guard.py::evaluate_connect`），fixture 只負責轉發＋記錄。
# G2：比對 repo 根第一層（非遞迴）的檔名集合，抓 G1 萬一漏掉的雜檔。
#
# T3 把預設模式固定 `report`：只記錄不擋，`report` 模式下全套的綠紅狀態必須與
# 上線前完全相同。T4 逐筆清乾淨違規（67 筆）。**T5 把預設切成 `fail`**——見下方
# 雙層拋出的設計（TASK-127b-T5.md 技術要點①）。


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """標準 pytest 慣例：把每個階段（setup／call／teardown）的 report 存到
    `item.rep_<when>` 上。

    G1 的 teardown 保險層（見 `_g1_repo_write_guard`）要靠 `item.rep_call`
    判斷「這支測試的 call 階段本身是否已經因為這條違規而失敗」——只有
    「有累積到違規，但 call 階段沒有因此失敗」才補刀（技術要點①：兩層拋出
    缺一都不算數，但已經失敗的測試不需要教訓兩次）。這是官方文件記錄的
    "post-process test reports" pattern，`wrapper=True` 為 pluggy 1.1+／
    pytest 7.4+ 的寫法（已實測 pytest 9.0.3：teardown 讀得到 `rep_call`）。
    """
    rep = yield
    setattr(item, "rep_" + rep.when, rep)
    return rep


#: G1 的 per-test 違規累積器掛在 `request.node.stash` 上（隨 node 生滅，不是
#: 模組級全域——見 `_repo_write_guard.ViolationAccumulator` docstring）。
_G1_ACCUMULATOR_STASH_KEY = pytest.StashKey[_rwg.ViolationAccumulator]()


# `sqlite3.connect` 的位置參數順序（Argument Clinic 產生的 `__text_signature__`）：
#   (database, timeout, detect_types, isolation_level, check_same_thread,
#    factory, cached_statements, uri, *, autocommit)
# ⇒ **`uri` 是合法的第 8 個位置參數**（`autocommit` 才是 keyword-only）。
#
# 🔴 不要改用 `inspect.signature(sqlite3.connect).bind(...)`：它是 builtin，
# `inspect` 解不動 `autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL` 這個預設值，
# 實測直接 `ValueError: builtin has invalid signature` ⇒ 每一次 connect 都會炸。
# 手動維護這張表只讀不算，是安全的做法。
#
# 漏讀位置傳入的 `uri` 的後果是**假紅不是漏放**：`evaluate_connect()` 會把
# `file:/tmp/x.db?mode=rwc` 當成相對路徑（`os.path.isabs("file:/...")` 為 False）
# ⇒ 本該 row05 放行的落成 row08 拒絕。`fail` 模式下那支測試會無故變紅。
# 回歸鎖：`tests/unit/test_repo_write_guard.py::TestWrapperArgumentBinding`。
_CONNECT_POSITIONAL_PARAMS = (
    "database", "timeout", "detect_types", "isolation_level",
    "check_same_thread", "factory", "cached_statements", "uri",
)


@pytest.fixture(autouse=True)
def _g1_repo_write_guard(request, monkeypatch, tmp_path_factory):
    """patch `sqlite3.connect`，白名單制 fail-closed 判定（見 `_repo_write_guard.py`）。

    鏡像操作對稱：用 `monkeypatch.setattr` 掛上去，pytest 保證即使測試中途
    example/early-return 也會在 teardown 還原——不手動 `patcher.start()`/`stop()`。

    雙層拋出（TASK-127b-T5 技術要點①，**設計約束，不得簡化成一層**）：
      第 1 層（inline，這裡的 `_g1_wrapper` 內，真正呼叫 `original_connect`
        之前）：`mode == fail` 且沒有 `allow_real_db` marker ⇒ 立刻拋
        `RepoWriteGuardViolation`（`BaseException` 子類，穿透產品碼的
        `except Exception`），**擋得住那次連線**，同時把這筆記錄塞進本支測試的
        `ViolationAccumulator`。
      第 2 層（teardown，`yield` 之後）：若累積器有記錄、而這支測試的 call
        階段最終**沒有**因此失敗（`item.rep_call.failed` 為否——代表某處用
        `except BaseException` 把 inline 那層吞了），再拋一次
        `RepoWriteGuardViolation` 彙總告警。專守「未來有人在 DB 路徑上新增
        `except BaseException`」的情況（本專案已有 3 處這種寫法，見
        TASK-127b-T5.md「✅ 解法的實證」表）。
      掛 `allow_real_db` marker 的違規**只進 report，不進累積器**——marker
      的語意是「記錄照記、只跳過拋出」，累積器只用來驅動 teardown 補刀，
      兩者是分開的容器（見①-c，寫成同一個會讓 marker 這個逃生口失效）。
    """
    mode = _rwg.get_mode()
    if mode == _rwg.MODE_OFF:
        yield
        return

    repo_root = _rwg.get_repo_root()
    tmp_roots = _rwg.get_tmp_roots()
    basetemp = tmp_path_factory.getbasetemp()
    nodeid = request.node.nodeid
    has_marker = request.node.get_closest_marker(_rwg.ALLOW_REAL_DB_MARKER) is not None
    original_connect = sqlite3.connect
    accumulator = _rwg.ViolationAccumulator()
    request.node.stash[_G1_ACCUMULATOR_STASH_KEY] = accumulator

    def _g1_wrapper(*args, **kwargs):
        bound = dict(zip(_CONNECT_POSITIONAL_PARAMS, args))
        bound.update(kwargs)
        database = bound.get("database")
        uri = bound.get("uri", False)
        decision = _rwg.evaluate_connect(
            database, uri,
            repo_root=repo_root, tmp_roots=tmp_roots, basetemp=basetemp,
        )
        if not decision.allowed:
            record = _rwg.format_g1_record(nodeid, decision, allowed_by_marker=has_marker)
            _rwg.append_report_record(record)
            if mode == _rwg.MODE_FAIL and not has_marker:
                accumulator.add(record)
                raise _rwg.RepoWriteGuardViolation(
                    f"[repo_write_guard/G1] 拒絕的 sqlite3.connect 呼叫："
                    f"nodeid={nodeid} reason={decision.case} "
                    f"raw={decision.raw_repr} resolved={decision.resolved}\n"
                    "怎麼修（四種既有慣例，挑對得上的那個）：\n"
                    "  1. patch 使用端的 `get_db_path`（**不是定義端**——24 個 import "
                    "landing point 會漂）：`patch(\"<被測模組>.get_db_path\", "
                    "lambda: tmp_path / \"x.db\")`\n"
                    "  2. 用 mock repo 時**明確設** `mock_repo.db_path = \":memory:\"`"
                    "（漏設 ⇒ 產品碼 `str(MagicMock)` 會拿 repr 當檔名）\n"
                    "  3. module-level lazy 單例（`core.access_auth._snapshot`、"
                    "`core.similar.canonicalize._merged_alias_map`）要用 **fixture 形狀**"
                    "前後各清一次，不能只清一邊\n"
                    "  4. 這支測試**真的**需要碰真實 DB ⇒ 掛 "
                    "`@pytest.mark.allow_real_db`（會照樣記進 report，只是不擋）"
                )
        return original_connect(*args, **kwargs)

    _g1_wrapper.__openaver_g1_wrapper__ = True
    monkeypatch.setattr(sqlite3, "connect", _g1_wrapper)
    yield

    if mode == _rwg.MODE_FAIL and accumulator:
        # 🔴 setup 與 call **兩個階段都要看**（sonnet review 2026-08-24 P2）。
        # 只看 `rep_call` 的話，違規發生在「某個依賴 G1 的 fixture 自己的 setup
        # 階段」時（例如 `def other(_g1_repo_write_guard): sqlite3.connect(bad)`），
        # call 階段根本沒跑過 ⇒ `rep_call` 從未被 `pytest_runtest_makereport`
        # 設過 ⇒ `already_failed` 判 False ⇒ 保險層補刀第二次，而且訊息會說
        # 「被 except BaseException 吞掉了」——**那是假的**，違規根本沒被吞，
        # 只是發生在另一個階段。實測：一支測試吐兩份 ERROR，第二份的診斷是錯的，
        # 會把未來的除錯者導去查一個不存在的 `except BaseException`。
        rep_setup = getattr(request.node, "rep_setup", None)
        rep_call = getattr(request.node, "rep_call", None)
        already_failed = bool(
            (rep_setup is not None and rep_setup.failed)
            or (rep_call is not None and rep_call.failed)
        )
        if not already_failed:
            raise _rwg.RepoWriteGuardViolation(
                f"[repo_write_guard/G1] teardown 保險：nodeid={nodeid} 累積到 "
                f"{len(accumulator)} 筆違規，但 setup／call 兩個階段都沒有因此"
                "失敗——代表 inline 拋出的 RepoWriteGuardViolation 在某處被"
                f"`except BaseException` 吞掉了。records={accumulator.records}\n"
                "先修那個 `except BaseException`（DB 路徑上不該有），"
                "或替這支測試掛 `@pytest.mark.allow_real_db`。"
            )


@pytest.fixture(autouse=True)
def _g2_repo_root_snapshot(request):
    """比對 repo 根第一層（非遞迴）快照，抓測試期間長出來的雜檔。

    雪崩防護：`before` 在**每一支測試**的 setup 期現掃現拿（不是掛一份全 session
    共用的可變 baseline），所以某支測試留下的雜檔只會被算到那一支頭上——後面的
    測試在它自己的 setup 期掃到時，那個檔案已經是「本來就在」的一部分。

    G2 沒有「inline 攔截點」——它只在事後比對快照,所以不像 G1 需要雙層拋出;
    這裡的單一拋出點本身就已經是「事後」,直接改用 `RepoWriteGuardViolation`
    即可穿透未來任何 `except Exception`。
    """
    mode = _rwg.get_mode()
    if mode == _rwg.MODE_OFF:
        yield
        return

    repo_root = _rwg.get_repo_root()
    nodeid = request.node.nodeid

    # patterns=None（預設）→ 走 `_cached_compiled_rules` 快取，同一個 repo_root
    # 只讀＋編譯一次 .gitignore，不隨每支測試的 setup/teardown 重跑磁碟 I/O
    # ＋線性 fnmatch 掃描（DoD「耗時增幅 < 5%」量到超標的主因，見該函式註解）。
    before = _rwg.scan_repo_root_first_level(repo_root)
    _rwg.require_nonzero_baseline(before, repo_root)  # BE-TEST-05：掃到 0 筆不是「乾淨」

    yield

    after = _rwg.scan_repo_root_first_level(repo_root)
    new_entries = after - before
    if new_entries:
        record = _rwg.format_g2_record(nodeid, new_entries)
        _rwg.append_report_record(record)
        if mode == _rwg.MODE_FAIL:
            raise _rwg.RepoWriteGuardViolation(
                f"[repo_write_guard/G2] repo 根第一層長出新檔案："
                f"nodeid={nodeid} new_entries={sorted(new_entries)}\n"
                "若你同時在跑別的會寫 repo 根的 process，這可能是誤報"
                "——G2 比對的是 repo 根第一層的快照，抓不出是哪個 process 寫的。\n"
                "怎麼修：讓那個寫入落到 `tmp_path` 底下。若檔名長得像 "
                "`<MagicMock ...>`，成因是某個 mock repo 沒設 `db_path`，"
                "產品碼 `str()` 之後拿 repr 當了檔名。"
            )


#: 外連防線的 per-test 違規累積器——獨立 StashKey，不與 G1 的
#: `_G1_ACCUMULATOR_STASH_KEY` 共用容器（避免把 DB 違規與 outbound 違規混在
#: 同一份報告裡）。
_OUTBOUND_ACCUMULATOR_STASH_KEY = pytest.StashKey[list]()


@pytest.fixture(autouse=True)
def _outbound_connection_guard(request, monkeypatch):
    """patch `socket.socket.connect`／`.connect_ex`／`socket.getaddrinfo`，
    白名單制拒絕非本機連線；只攔 Python socket 層（`curl_cffi` 的 libcurl 不經過這裡）。

    `smoke`／`e2e` marker 的測試完全不受影響：fixture 開頭直接判斷、不 patch
    任何東西就 `yield; return`——這是「`-m` 整批排除」與「直接執行
    `pytest tests/smoke/...`」兩種呼叫方式下都成立的唯一辦法（root conftest 的
    autouse fixture 在沒有 `-m` 篩選時，對 `tests/smoke/` 底下的測試照樣生效）。

    雙層拋出（照抄 G1 `_g1_repo_write_guard` 的設計，見
    `tests/_repo_write_guard.py::RepoWriteGuardViolation` docstring）：
      inline：wrapper 判斷拒絕時立即拋 `OutboundConnectionViolation`
        （`BaseException` 子類，穿透 `except Exception`——產品碼如
        `core/scrapers/dmm.py::_fetch_tags_from_html` 的
        `except Exception: return []` 會吞掉一般 `Exception`）。
      teardown 保險層：per-test 累積器記錄「無論 inline 有沒有拋出成功」都先
        `.append()`；teardown 補刀涵蓋兩種 inline 傳不到測試本體的情況：
        (a) 違規發生在背景 `threading.Thread`（未捕捉例外只會被 Python 預設的
        `threading.excepthook` 印到 stderr，不會傳回主測試執行緒，主執行緒的
        `call` 階段完全不知情、繼續判定 passed）；
        (b) 呼叫鏈上有 `except BaseException`／裸 `except:`（比
        `except Exception` 更寬，理論上少見但不能假設不存在）。
      `list.append()` 在 CPython 受 GIL 保護，多執行緒併發呼叫不需要額外加鎖
      （同 G1 `ViolationAccumulator` 的既有假設，本 fixture 沿用，不升級成
      `threading.Lock`）。

    teardown 判斷「call 階段是否已經因此失敗」重用 root conftest 既有的
    `pytest_runtest_makereport` wrapper hook（把 `rep_setup`／`rep_call` 存到
    node 上）——不需要為外連防線再寫一份，邏輯與 G1 的 `already_failed` 判斷
    完全對稱。

    **不做成 marker opt-out 白名單**（例如 `@pytest.mark.allow_outbound`）：
    本專案的 unit／integration 測試不應該有任何合法情境需要連外，那正是
    smoke／e2e 存在的理由。
    """
    if (
        request.node.get_closest_marker("smoke") is not None
        or request.node.get_closest_marker("e2e") is not None
        or _og.is_exempt_path(request.node.path, Path(__file__).parent)
    ):
        yield
        return

    nodeid = request.node.nodeid
    accumulator: list = []
    request.node.stash[_OUTBOUND_ACCUMULATOR_STASH_KEY] = accumulator

    def _violation_message(host_or_addr, *, teardown: bool = False) -> str:
        prefix = "[outbound_guard] teardown 保險：" if teardown else "[outbound_guard] "
        return (
            f"{prefix}測試嘗試連到非本機主機：nodeid={nodeid} "
            f"host={host_or_addr}\n"
            "怎麼修：mock 搜尋/刮削入口（例如 patch 'core.scraper.smart_search' "
            "或對應 scraper 的 .search()），不要 mock 到 session.get/post 這一層"
            "以下——那樣會把 hook／路由邏輯的真實路徑也繞掉"
        )

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def _guarded_connect(self, addr):
        if not _og.evaluate_connect(addr, self.type):
            accumulator.append(str(addr))
            raise _og.OutboundConnectionViolation(_violation_message(addr))
        return original_connect(self, addr)

    def _guarded_connect_ex(self, addr):
        if not _og.evaluate_connect(addr, self.type):
            accumulator.append(str(addr))
            raise _og.OutboundConnectionViolation(_violation_message(addr))
        return original_connect_ex(self, addr)

    def _guarded_getaddrinfo(host, *args, **kwargs):
        if not _og.evaluate_getaddrinfo(host):
            accumulator.append(str(host))
            raise _og.OutboundConnectionViolation(_violation_message(host))
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", _guarded_getaddrinfo)

    yield

    if accumulator:
        rep_setup = getattr(request.node, "rep_setup", None)
        rep_call = getattr(request.node, "rep_call", None)
        already_failed = bool(
            (rep_setup is not None and rep_setup.failed)
            or (rep_call is not None and rep_call.failed)
        )
        if not already_failed:
            hosts = ", ".join(accumulator)
            raise _og.OutboundConnectionViolation(
                _violation_message(hosts, teardown=True)
                + f"\n累積到 {len(accumulator)} 筆違規，但 setup／call 兩個階段"
                "都沒有因此失敗——代表違規發生在背景執行緒，或被某處"
                "except BaseException／裸 except: 吞掉了。"
            )


# ============ 159-T11：app 啟動時的新版檢查不連 GitHub（autouse）====
#
# 啟動檢查不再只限桌面版 ⇒ 在 Linux 上跑的每支 `with TestClient(app)` 都會在背景
# 打 api.github.com（被上面的對外連線守衛擋下、teardown 報錯），順手還會 emit 通知、
# 寫 config。預設換成「沒有新版」；要測這條路的測試自己再 patch `web.app.check_update`
# （測試內的 patch 晚於本 fixture，會蓋過它）。smoke／e2e 不動。
@pytest.fixture(autouse=True)
def _no_startup_update_network(request, monkeypatch):
    if request.node.get_closest_marker("smoke") or request.node.get_closest_marker("e2e"):
        yield
        return
    # 只 patch 已載入的 web.app，不主動 import：import 本身有副作用（建資料根），
    # 守衛自測會把本 conftest 複製到暫存 repo 跑，主動 import 會在那裡長出檔案。
    # 用到 app 的測試都在模組層 `from web.app import app`，收集階段就已載入。
    import sys as _sys
    _web_app = _sys.modules.get("web.app")
    if _web_app is None:
        yield
        return

    async def _fake_check_update():
        return {"has_update": False, "current_version": "", "latest_version": ""}

    monkeypatch.setattr(_web_app, "check_update", _fake_check_update)
    yield


# ============ TASK-175c-T3：JavBus resolve 模組層快取，每個測試前清 ============
#
# `core.search_providers.javbus` 的 resolve 快取是模組層級（重啟才清），測試間不清會讓「同名第二次 0 請求」
# 這類斷言被前一個測試的結果污染。只清「已載入」的模組，不主動 import（同 `_no_startup_update_network`：
# 守衛自測會把本 conftest 複製到暫存 repo 跑，主動 import 會在那裡長出副作用）。
@pytest.fixture(autouse=True)
def _clear_javbus_resolve_cache():
    import sys as _sys
    mod = _sys.modules.get("core.search_providers.javbus")
    if mod is not None:
        mod.clear_resolve_cache()
    yield


# 175c-T7：DMM 的 Probe 快取是模組層（name_key -> Probe），同樣會讓請求數隨執行順序飄；只清已載入的模組。
@pytest.fixture(autouse=True)
def _clear_dmm_probe_cache():
    import sys as _sys
    mod = _sys.modules.get("core.search_providers.dmm")
    if mod is not None:
        mod.clear_probe_cache()
    yield


# ============ TASK-174-T2：漏 mock 的全域防線（avbase）====
#
# 外連防線只攔 Python `socket`，`curl_cffi`（libcurl 在 C 層連線）不在範圍（BE-TEST-43）。
# 間接走到 orchestrator 的測試（女優卡、別名線上搜尋、收藏端點…）若忘了 mock avbase，
# 會真的對 avbase 發請求且可能照樣綠，反覆打站會讓開發機 IP 被 Cloudflare 封。
# 預設把 `scrape_avbase` 換成回 None 的替身；要測真函式的測試標 `real_avbase` opt-out。
# 測試內自己的 patch 晚於本 fixture，會蓋過它。smoke／e2e（金絲雀要打真站）不動。
@pytest.fixture(autouse=True)
def _no_real_avbase(request, monkeypatch):
    if (request.node.get_closest_marker("smoke") or request.node.get_closest_marker("e2e")
            or request.node.get_closest_marker("real_avbase")):
        yield
        return
    # 與 _no_startup_update_network 相反：這裡必須主動 import。orchestrator 在函式體內才
    # `from … import scrape_avbase`，模組尚未載入時 patch 不到，之後拿到的會是真函式。
    # 守衛自測把本 conftest 複製到暫存 repo 時模組不一定在 → 吞 ImportError，不讓 fixture 自己炸。
    try:
        import core.scrapers.actress.avbase as _avbase
    except ImportError:
        yield
        return
    monkeypatch.setattr(_avbase, "scrape_avbase", lambda *a, **kw: None)
    yield


# 背景執行緒可能讀取其他測試的 DB 或啟動 Pigo；包含 lifespan 的整合測試也需隔離。
# 主動 import 以涵蓋晚載入的模組；個別測試的 spy 可覆蓋，T5b 測試取回 _REAL_KICK。
@pytest.fixture(autouse=True)
def _no_actress_faces_sweep(monkeypatch):
    try:
        from core.ai_services import actress_faces as _af
    except ImportError:
        yield
        return
    monkeypatch.setattr(_af, "kick", lambda *a, **kw: None)
    yield


# ============ TASK-141a-T5：對帳 hook 的 DB 隔離（named fixture，非 autouse）====
#
# 為什麼需要它：141a-T5 讓 `generate_avlist()` 與 `enrich_single_endpoint()` 在收尾
# **無條件**呼叫 `core.wishlist_reconcile.reconcile_wishlist()`。那支函式在 `core/` 層，
# 用無參數的 `WishlistRepository()` / `VideoRepository()`，於是解析到
# `connection.get_db_path()`＝真實 `output/openaver.db` ⇒ 撞上 G1。
#
# 既有測試對這兩支端點的隔離手法是「patch 使用端的 `VideoRepository` **類別**」
# （`web.routers.scraper.VideoRepository`），那個 patch 到不了 `core.wishlist_reconcile`
# 內部的 import ⇒ 92 支既有測試會紅。
#
# **為什麼不做成 autouse（放進 conftest 全域）**：那會讓每一支測試的
# `connection.get_db_path()` 都指向 tmp 檔，於是「忘記 patch DB」這一整類錯誤
# 再也不會被 G1 攔下——那正是 127b 花力氣買到的守衛。**寧可逐檔明示 opt-in。**
#
# 用法（放在測試檔頂層）：
#     pytestmark = pytest.mark.usefixtures("isolate_reconcile_db")
@pytest.fixture
def public_resolver(monkeypatch):
    """opt-in（非 autouse）：把唯一的 resolver `core.public_target.resolve_host` 換成查表假件。

    用法：`resolve = public_resolver({"example.com": ["10.0.0.5"]})`；表外的 host 回預設 ["8.8.8.8"]。
    `resolve.calls` 記錄被呼叫的 host 清單，供斷言「resolver 有沒有被叫到、參數是誰」。
    """

    def factory(table=None, default=("8.8.8.8",)):
        table = dict(table or {})
        calls = []

        def fake(host):
            calls.append(host)
            return list(table.get(host, default))

        fake.calls = calls
        monkeypatch.setattr("core.public_target.resolve_host", fake)
        return fake

    return factory


@pytest.fixture
def isolate_reconcile_db(tmp_path_factory, monkeypatch):
    """把對帳 hook 會用到的 DB 路徑導到一個乾淨的 tmp 庫（空庫 ⇒ 對帳是 no-op）。"""
    from core.database import init_db

    db_path = tmp_path_factory.mktemp("reconcile_isolate") / "isolate.db"
    init_db(db_path)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)
    monkeypatch.setattr("core.wishlist_cover_cache.get_db_path", lambda: db_path)
    return db_path


# ============ 175b-T9：路由讀片庫片商名的隔離（named fixture，非 autouse）====
#
# `/api/search` 與 `/api/search/stream` 的 auto 分支現在會呼叫 `_detect_mode(q, True)`
# ⇒ `core.maker_names.known_makers()` ⇒ `library_maker_names()` 開真實 `output/openaver.db`
# （BE-TEST-28）。既有測試 patch 的是 router 層的東西，到不了這裡。
# 不做 autouse（同 isolate_reconcile_db 的理由）；受影響的檔案逐檔 pytestmark opt-in：
#     pytestmark = pytest.mark.usefixtures("empty_library_makers")
@pytest.fixture
def empty_library_makers(monkeypatch):
    """opt-in（非 autouse）：片庫片商名回空集合（靜態對照表半邊照常）。"""
    monkeypatch.setattr("core.maker_names.library_maker_names", lambda: set())


# ============ TASK-175c-T4：名稱→實體 resolve 的隔離（R14 測試遷移）====
#
# JavBus 宣告 ACTOR／SERIES／DIRECTOR／LABEL 能力後，relay 的實體梯子對 `actress` 模式會先 `resolve`
# 才輪到 KEYWORD：真 `JavBusProvider.resolve` 會發 searchstar／搜尋請求（被 `_outbound_guard` 擋成
# `OutboundConnectionViolation`），或在假 scraper 沒有 `search_stars` 時被梯子吞成 `[]` 而讓 KEYWORD 沒被問。
# 這些既有測試要驗的是 KEYWORD／前綴／部分番號的舊行為，所以把 resolve 換成「查無」讓梯子走空。
# 不做 autouse：受影響的檔案逐檔 pytestmark opt-in（站方回應不再於單元測試造假，真 resolve 的測試已刪，靠活站金絲雀）：
#     pytestmark = pytest.mark.usefixtures("no_entity_lookup")
# 只 patch 既有屬性（不用 create=True，命名錯誤要炸）；T7 加入 DMM 的 resolve 後擴成兩家。
# T9：DMM 宣告 MAKER 後，片商路徑（`relay.search_maker` → `DMMProvider.run_maker`）經 `_resolve_maker` 解析片商名
# （不經 `resolve`，上面兩行攔不到），預設順序 DMM 排第一，既有的片商接力測試（test_fuzzy_chain.py 的
# TestMakerLatestPipeline）會在片商解析第一步被 `_outbound_guard` 擋成 `OutboundConnectionViolation`；
# 片商解析也是「名稱→實體」查詢，所以併進這個 fixture（已 opt-in 的檔零修改）。
@pytest.fixture
def no_entity_lookup(monkeypatch):
    """opt-in（非 autouse）：JavBus、DMM 名稱→實體 resolve（含 DMM 的片商解析）回 None（0 請求）。"""
    monkeypatch.setattr("core.search_providers.javbus.JavBusProvider.resolve", lambda self, kind, name: None)
    monkeypatch.setattr("core.search_providers.dmm.DMMProvider.resolve", lambda self, kind, name: None)
    monkeypatch.setattr("core.search_providers.dmm.DMMProvider._resolve_maker", lambda self, names: None)
    # 175d：relay 的多代號／換名可選方法同樣是「名稱→實體」查詢，一併換成「查無」（0 請求）
    monkeypatch.setattr("core.search_providers.javbus.JavBusProvider.resolve_all", lambda self, kind, name: [])
    monkeypatch.setattr("core.search_providers.javdb.JavDBProvider.alt_names", lambda self, kind, name: [])


# ============ TASK-175d-T2：本機女優別名表的隔離 ============
# 接力會讀使用者資料庫的別名表（`actor_names.load_alias_groups`）；依賴「別名展開」以外行為的測試用它把別名表換成空，
# 不讓本機 DB 內容影響結果。opt-in（非 autouse），只 patch 既有屬性。
@pytest.fixture
def no_actor_aliases(monkeypatch):
    """opt-in（非 autouse）：本機別名表回 []（不讀 DB）。"""
    monkeypatch.setattr("core.search_providers.actor_names.load_alias_groups", lambda *a, **k: [])


# ============ TASK-175d-T4：relay 讀本機別名表的全域隔離（autouse）============
# relay 的女優梯級每次搜尋都會惰性呼叫 `actor_names.load_alias_groups()`；該函式讀真實 `output/openaver.db`。
# 開發機有該檔時，任何走到 `search_by_intent("actress", …)` 的測試（含 smart_search 系列）會撞上 G1 拋 BaseException，
# CI 沒有該檔不會 ⇒ 本機紅 CI 綠（BE-TEST-28 同形）。所以預設換成「沒有別名」。
# 要餵別名組的測試在測試內 `monkeypatch.setattr("core.search_providers.actor_names.load_alias_groups", lambda: groups)`
# （晚於本 fixture，會蓋過它）。relay 必須以模組屬性呼叫才攔得到；T1 的 test_actor_names 以 from-import 綁名，不受影響。
# smoke／e2e 不動。與上面 opt-in 的 `no_actor_aliases` 並存（T2 的測試仍可明寫它）。
@pytest.fixture(autouse=True)
def _no_real_actor_aliases(request, monkeypatch):
    if request.node.get_closest_marker("smoke") or request.node.get_closest_marker("e2e"):
        yield
        return
    monkeypatch.setattr("core.search_providers.actor_names.load_alias_groups", lambda *a, **k: [])
    yield


# ============ TASK-175c-T8：DMM 官方番號 facts 的隔離（R14 測試遷移）====
#
# DMM 列表（關鍵字與實體共用的頁面組裝）現在在回傳前多打一次 `fetch_facts` 取官方番號（CD-175c-7）。
# 只 patch `list_contents` 的既有測試（假 rows、斷言推導番號）沒有替身可吃這次呼叫，真 `fetch_facts` 會被
# `_outbound_guard` 擋成 `OutboundConnectionViolation`。這裡把它換成「站方一個 alias 都沒回」（`{}`）＝官方番號全走
# cid 推導的退路＝等於這些測試今天斷言的值。
# 不做 autouse：受影響的檔案逐檔 pytestmark opt-in（站方回應不再於單元測試造假，要真 facts 的測試已刪，靠活站金絲雀）：
#     pytestmark = pytest.mark.usefixtures("no_dmm_facts")
# 只 patch 既有屬性（不用 create 旗標，命名錯誤要炸）。
@pytest.fixture
def no_dmm_facts(monkeypatch):
    """opt-in（非 autouse）：DMMScraper.fetch_facts 回 {}（0 請求；官方番號走推導退路）。"""
    monkeypatch.setattr("core.scrapers.dmm.DMMScraper.fetch_facts", lambda self, content_ids: {})


# ============ CI 修復：session 開始前把真實預設資料根真的定版一次 ============
#
# 為什麼需要：CI 乾淨 checkout 沒有已定版的 `output/`（gitignored，本機早已
# 定版所以本機看不到這個問題）。第一支用 `with TestClient(app):`（或等價）跑
# 完整 lifespan 的測試會觸發 `web.app.lifespan` 裡的 `bootstrap_data_layout()`
# → `core/data_layout.py::_bootstrap_effective_root()` 判定為「無 marker、無
# root config」的全新安裝 → 落入 fresh 分支的 `init_db(root / "openaver.db")`。
# 那一行**刻意用顯式路徑**（見該函式「fresh」分支的註解：避免 `get_db_path()`
# 在 gate／測試 monkeypatch 情境下落到錯誤 root），所以既有測試慣例「patch
# `core.database.connection.get_db_path`」對它無效 → 對真實 repo 的
# `output/openaver.db` 呼叫 `sqlite3.connect` → 撞上 G1。對照 gotcha
# BE-TEST-28（既有測試 patch 打不到內部顯式路徑，G1 才在 PR 前全套炸開）與
# BE-DATA-13（同一子系統：資料根定版前的寫入陷阱）。本次觸發：GitHub Actions
# run 35823861647，`tests/integration/test_api_actress_library.py::
# TestLibraryActressesEndpoint::test_library_non_2xx_when_pairs_query_fails`。
#
# 本機為什麼看不到：本機 `output/` 早已定版（config.json ＋ `.layout.json`
# 都在）⇒ `_bootstrap_effective_root()` 一開頭就落在 `already_complete`，
# 完全不碰 DB。CI 乾淨樹的第一支「真的跑滿 lifespan」的測試踩進的其實是「無
# marker、**無** root config」那個分支，才會掉進 fresh／`init_db()`。
#
# 三個被 revert 掉的做法，及為什麼不用（由簡入繁，後一個是實測發現前一個仍
# 不夠才加碼的）：
#   1. autouse fixture 把 `web.app.bootstrap_data_layout` 整支 stub 成
#      no-op：需要無條件 `import web.app`（測試多半是在函式本體才
#      `from web.app import app`，fixture setup 階段看不到那個 import，只能
#      搶先 import）——但 `web/app.py` import 時會呼叫
#      `core.logger.setup_logging()`，在 `test_repo_write_guard_subsession.py`
#      的 pytester 子 session 裡（cwd＝假 repo root）會現生出一個新的
#      `OpenAver/logs/` 目錄，撞上 G2（`test_flag_marker_combination[...]`
#      等 7 支測試紅）。
#   2. session 開始就全域 `os.environ["OPENAVER_DATA_DIR"]` 指到一個預先定版
#      的 tmp 根：`get_data_root()` 全程活讀 env var，會讓
#      `test_api_config_endpoints.py::
#      test_default_data_root_path_rejected_when_under_program_root`（斷言
#      「未設 OPENAVER_DATA_DIR 時，資料根逐字等於 program_root/output」）的
#      前提失真而變紅。
#   3.（實測仍不夠的中間版本）只幫真實預設 root 補一份 `config.json`（不寫
#      marker），指望「不管哪一支測試第一個真的跑滿 lifespan，都會落進
#      `_bootstrap_effective_root()` 的 resumed 分支、順手把 marker 寫掉」。
#      **實測前提不成立**：`pytest tests/ -q --ignore=tests/smoke
#      --ignore=tests/e2e -m "..."`（＝ check.sh 真正下的那行指令）給 `tests/`
#      單一目錄時的收集順序，**不是**先跑完整個 `tests/integration/` 才進
#      `tests/unit/`，而是兩邊的檔案交錯（實測 `tests/unit/
#      test_auto_organize_scheduler.py` 排在 `tests/integration/
#      test_api_search.py`／`test_settings_metatube.py` 之後沒錯，但改用
#      `--collect-only` 拿到的順序去對照式重播，會跟 `pytest tests/`
#      真正執行時的順序對不上——用**顯式檔案清單**重播出來的順序，跟直接
#      給 `tests/` 這個目錄让 pytest 自己遞迴收集，兩者不保證一致）。也就是
#      「總有某一支測試會先幫忙 resumed」這個前提本身就是在賭執行順序，
#      在這台機器上賭輸：`test_auto_organize_scheduler.py` 兩支＋
#      `test_dmm_progressive.py`／`test_help_page.py`／
#      `test_motion_lab_router.py` 共 10 支測試撞上
#      `ConfigRootNotFinalizedError`（BE-DATA-13 本人）。
#
# 前兩者的共同盲點：把「bootstrap 本身」整支繞掉，卻忽略了本專案已經有一大票
# 測試隱性依賴「CI 這個 process 裡，總有某一支測試會真的把預設資料根定版過
# 一次」這個全域副作用——繞掉 bootstrap 本身，順帶繞掉了那個副作用。
# 做法 3 保留了 bootstrap 本身，但只補了一半（config 沒補 marker），仍然把
# 「誰先跑到」交給執行順序決定。
#
# 收斂：**不再賭順序**，在 session 最開頭、G1 的 autouse fixture 還沒對任何
# 一支測試生效之前（`pytest_configure` 發生在任何測試的 setup 之前，此刻
# `sqlite3.connect` 完全未被 patch，因為 G1 是 function-scoped fixture），
# 直接呼叫**真正的** `bootstrap_data_layout()`，把真實預設資料根一次定版到
# 底（config.json ＋ `.layout.json` ＋ 一顆空 `openaver.db`）——本機開發環境
# 本來就長這樣，這裡只是讓 CI 乾淨樹在任何測試看到它之前，先經歷一次「跟本機
# 一樣的『這台機器第一次真的啟動過 App』」，之後不管哪一支測試第一個真的跑滿
# lifespan，都會落在 `already_complete`，不再碰 DB、不再看執行順序臉色。
# 已經定版（本機／第二次以後的 CI 執行）時這通呼叫本身就是零 I/O 的
# already_complete 快速路徑,對「補一份 config.json」的做法零額外成本。
# `get_data_root()`／`OPENAVER_DATA_DIR` 語意完全沒被動到，`test_data_layout.py`
# 等直接操作 `core.data_layout`／自己 monkeypatch `data_root.get_data_root`
# 的測試也完全不受影響（它們從不落在真實預設 root 上）；
# `test_repo_write_guard_subsession.py` 的 pytester 子 session 複製這份
# conftest 時，子 process 的 `get_default_data_root()` 仍解析到同一個真實
# repo 的 `output/`——父 session 這裡已經定版過，子 session 那次呼叫一樣是
# already_complete，不會再生出新檔案讓 G2 誤報。
def pytest_configure(config):
    from core.data_layout import bootstrap_data_layout

    bootstrap_data_layout()


# ============ TASK-206a-T1：secret_store 的 DB 隔離（named fixture，非 autouse）====
#
# 用法：`def test_x(self, isolate_secret_store):` —— 參數即回傳的 tmp 資料根。
# 不做 autouse（同 isolate_reconcile_db 的理由）；只隔離 secret_store，不碰 core.config。
@pytest.fixture
def isolate_secret_store(tmp_path, monkeypatch):
    """opt-in（非 autouse）：tmp 資料根＋已定版 marker，secret_store 快取已 prime。"""
    from core import secret_store as _secret_store
    from core.data_root import LAYOUT_MARKER_NAME

    root = tmp_path / "secret_store_root"
    root.mkdir(exist_ok=True)
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(root))
    (root / LAYOUT_MARKER_NAME).write_text(
        json.dumps({"version": 1, "complete": True}),
        encoding="utf-8",
    )
    _secret_store.reset_state_for_tests()
    _secret_store.prime()
    yield root
    _secret_store.reset_state_for_tests()


# ============ TASK-206a-T3：lifespan 啟動接線的測試隔離（autouse）====
#
# 形狀照 `_no_startup_update_network`：sys.modules 有 web.app 才 patch，
# 不主動 import；smoke／e2e 不動；帶 isolate_secret_store 的測試放行。
@pytest.fixture(autouse=True)
def _no_startup_secret_wiring(request, monkeypatch):
    if request.node.get_closest_marker("smoke") or request.node.get_closest_marker("e2e"):
        yield
        return
    if "isolate_secret_store" in request.fixturenames:
        yield
        return
    import sys as _sys
    _web_app = _sys.modules.get("web.app")
    if _web_app is None:
        yield
        return
    monkeypatch.setattr(_web_app, "prime_secret_store", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(_web_app, "migrate_config_secrets", lambda *a, **kw: None, raising=False)
    yield
