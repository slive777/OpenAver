"""
Async-offload 回歸守衛（feature/66 T5）

AST-based 靜態掃描 web/routers/*.py：
  1. 每個 async def 路由的「直接 body」不得裸跑偵測清單中的阻塞慢 I/O 呼叫
     （直接 body = 不下潛 nested FunctionDef / AsyncFunctionDef；
      已包在 await asyncio.to_thread(...) 內的呼叫天然不算裸呼叫，
      因為 to_thread 的 target 是 Name 節點而非 Call 節點）
  2. T1–T3 轉 def 的 handler 確認為 FunctionDef（非 AsyncFunctionDef），
     防止 refactoring 意外把它們改回 async def 而重新卡 event loop

CD-66-5：本守衛屬 pytest C 類（Python API contract / 行為），不走 eslint。
形式參考：tests/integration/test_api_scanner.py::test_jellyfin_check_uses_to_thread
"""
import ast
import pathlib
from typing import Optional

ROUTERS_DIR = pathlib.Path(__file__).parents[2] / "web" / "routers"


# ============================================================
# 偵測清單
# ============================================================

# 直接函式名（ast.Name 的 id，或 ast.Attribute 的 attr）
BLOCKING_FUNC_NAMES = frozenset({
    # File I/O
    "realpath", "getsize", "open",
    # DB
    "init_db", "get_db_path", "VideoRepository", "ActressRepository",
    # Config
    "load_config", "save_config",
    # Sync HTTP（metatube）
    "MetatubeHttpClient", "list_providers", "_verify_token_canary",
})

# Attribute-call 後綴（接在任意物件後 .exists() / .stat() / .iterdir() / .save()）
BLOCKING_ATTR_CALL_NAMES = frozenset({
    "exists", "stat", "iterdir", "save",
})

# 白名單：{(file_stem, func_name)} — 豁免整個函式。
# 目前為空：偵測清單夠精確（只命中具名慢 I/O / repo.* / 檔案 stat），
# in-memory state 操作（state.disconnect / status_dict / _fire_probe）天然不命中，
# 無需豁免。刻意保持空集合 → 連 settings_metatube 的 in-memory 路由都受保護：
# 若它們未來新增裸 load_config/repo 呼叫，守衛會立即報錯而非被白名單放生。
# 只有「確實會命中偵測、但刻意留 loop」的路由才該加入（並附理由）。
WHITELIST: frozenset = frozenset()


# ============================================================
# AST 工具
# ============================================================

def _is_route_handler(node: ast.AsyncFunctionDef) -> bool:
    """確認 node 有 @router.<method>(...) 裝飾器。"""
    for dec in node.decorator_list:
        # @router.get(...) / @router.post(...) 等
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
            if isinstance(dec.func.value, ast.Name) and dec.func.value.id == "router":
                return True
        # @router.get（無括號，防禦）
        if isinstance(dec, ast.Attribute):
            if isinstance(dec.value, ast.Name) and dec.value.id == "router":
                return True
    return False


def _collect_direct_calls(func_node: ast.AsyncFunctionDef) -> list:
    """收集 func_node 在「event loop 上執行的 body」的所有 Call 節點。

    下潛規則（Codex review 修正）：
    - **停在巢狀同步 `FunctionDef`**：sync def 不是 to_thread target 就是
      Starlette 在 threadpool 迭代的 sync generator —— 皆不在 loop，不掃。
    - **下潛巢狀 `AsyncFunctionDef`**：SSE async generator（如 event_generator）
      由 Starlette 在 event loop 上迭代 → 其 body 的裸阻塞呼叫一樣卡 loop，必須掃。

    註：`await asyncio.to_thread(fn, ...)` 的 fn 是 args 裡的 Name 節點、非 Call，
    天然不會被當成裸呼叫——已正確包裝者不會誤報。
    """
    calls = []

    def _walk(nodes):
        for node in nodes:
            if isinstance(node, ast.Call):
                calls.append(node)
            # 只在「同步」巢狀 def 停（threadpool-safe）；async def 繼續下潛
            if isinstance(node, ast.FunctionDef):
                continue
            _walk(ast.iter_child_nodes(node))

    _walk(ast.iter_child_nodes(func_node))
    return calls


def _is_generator_def(func_node) -> bool:
    """func_node 是否為 generator function（自身 body 直接含 yield / yield from，
    不含 nested 函式內的 yield）。

    關鍵：呼叫一個 sync generator function 只會「建立」generator 物件、**不執行 body**；
    其 body 在被迭代時才跑（StreamingResponse 的 sync generator 由 Starlette 在
    threadpool 迭代，不在 loop）。故 generator function 不算「呼叫即阻塞」的 helper。
    """
    found = False

    def _walk(nodes):
        nonlocal found
        for node in nodes:
            if found:
                return
            if isinstance(node, (ast.Yield, ast.YieldFrom)):
                found = True
                return
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue  # 不下潛 nested 函式
            _walk(ast.iter_child_nodes(node))

    _walk(ast.iter_child_nodes(func_node))
    return found


def _collect_blocking_local_helpers(tree: ast.Module) -> frozenset:
    """回傳「module-level 同步 def 且 body 含已知阻塞呼叫」的 helper 名稱集合。

    用途：抓「裸呼叫一個本檔 sync helper，而該 helper 內部裹著 load_config /
    init_db / repo.* 等阻塞 I/O」的二階卡 loop（Codex P1/P2：`_persist_allow_lan`、
    `get_translate_service`、`_fetch_actress_profile_with_db`）。

    只看 module-level `FunctionDef`（async def 是路由或 coroutine，不算 helper；
    nested def 是 to_thread target）。**排除 generator function**：呼叫它只建立
    generator 物件、body 不在 call site 執行（sync generator 給 StreamingResponse
    由 Starlette threadpool 迭代）—— 否則會誤報 generate_avlist 等。
    一層偵測即足夠涵蓋本 codebase 的 helper pattern。
    註：`await asyncio.to_thread(helper)` 的 helper 是 Name arg、非 Call → 不誤報。
    """
    helpers = set()
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if _is_generator_def(node):
            continue  # sync generator：呼叫不執行 body，threadpool 迭代
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and _is_blocking_call(child):
                helpers.add(node.name)
                break
    return frozenset(helpers)


def _call_name(call: ast.Call) -> Optional[str]:
    """取 Call node 的「函式名」用於偵測：
    - ast.Name      → .id    (e.g. load_config())
    - ast.Attribute → .attr  (e.g. db_path.exists(), repo.save())
    """
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _is_blocking_call(call: ast.Call) -> bool:
    """判斷 call 是否為偵測清單中的裸阻塞呼叫。"""
    name = _call_name(call)
    if name is None:
        return False

    # 直接函式名 / Attribute attr 命中
    if name in BLOCKING_FUNC_NAMES:
        return True
    # Attribute-call 後綴命中（.exists / .stat / .iterdir / .save）
    if name in BLOCKING_ATTR_CALL_NAMES:
        return True
    # repo.* / *_repo.* pattern：value 是 Name 且 id == "repo" 或結尾 "_repo"
    if isinstance(call.func, ast.Attribute):
        val = call.func.value
        if isinstance(val, ast.Name) and (val.id == "repo" or val.id.endswith("_repo")):
            return True
    return False


def _iter_async_route_handlers():
    """yield (py_file, AsyncFunctionDef, blocking_helpers) for every async route handler.

    blocking_helpers = 本檔 module-level sync helper 中含阻塞 I/O 者（per-file 推斷）。
    """
    for py_file in sorted(ROUTERS_DIR.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        blocking_helpers = _collect_blocking_local_helpers(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and _is_route_handler(node):
                yield py_file, node, blocking_helpers


# ============================================================
# 守衛測試
# ============================================================

class TestAsyncOffloadGuard:
    """AST 回歸守衛：async def 路由直接 body 不得裸跑慢 I/O。"""

    def test_no_bare_blocking_in_async_routes(self):
        """主守衛：掃 web/routers/*.py 每個 async 路由，直接 body 不得有裸阻塞呼叫。"""
        violations = []
        for py_file, node, blocking_helpers in _iter_async_route_handlers():
            if (py_file.stem, node.name) in WHITELIST:
                continue
            for call in _collect_direct_calls(node):
                name = _call_name(call)
                # 直接命中偵測清單，或裸呼叫本檔含阻塞 I/O 的 sync helper
                if _is_blocking_call(call) or (name is not None and name in blocking_helpers):
                    violations.append(
                        f"{py_file.name}:{node.name}() — bare blocking call: {name}()"
                    )
        assert not violations, (
            "Async route handlers have bare blocking calls on the event loop "
            "(wrap in `await asyncio.to_thread(...)` or convert to `def`):\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_whitelist_entries_exist(self):
        """白名單防腐：每個白名單條目對應的函式必須真實存在（避免殭屍豁免）。"""
        found = {(py.stem, n.name) for py, n, _ in _iter_async_route_handlers()}
        missing = [w for w in WHITELIST if w not in found]
        assert not missing, f"WHITELIST 指向不存在的 async 路由（應清理）: {missing}"


class TestConvertedHandlersAreDef:
    """正斷言：T1–T3 轉 def 的 handler 確認為同步 def（不可回退 async def）。"""

    @staticmethod
    def _func_type(filename: str, func_name: str) -> type:
        py_file = ROUTERS_DIR / filename
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                return type(node)
        raise AssertionError(f"{filename}:{func_name} not found")

    # T1 — hot path
    def test_t1_get_image_is_def(self):
        assert self._func_type("scanner.py", "get_image") is ast.FunctionDef

    def test_t1_get_video_is_def(self):
        assert self._func_type("scanner.py", "get_video") is ast.FunctionDef

    # T2 — 純讀 DB 路由
    def test_t2_get_stats_is_def(self):
        assert self._func_type("scanner.py", "get_stats") is ast.FunctionDef

    def test_t2_clear_cache_is_def(self):
        assert self._func_type("scanner.py", "clear_cache") is ast.FunctionDef

    def test_t2_check_update_is_def(self):
        assert self._func_type("scanner.py", "check_update") is ast.FunctionDef

    def test_t2_check_missing_is_def(self):
        assert self._func_type("scanner.py", "check_missing") is ast.FunctionDef

    def test_t2_view_list_is_def(self):
        assert self._func_type("scanner.py", "view_list") is ast.FunctionDef

    def test_t2_get_actress_stats_is_def(self):
        assert self._func_type("scanner.py", "get_actress_stats") is ast.FunctionDef

    def test_t2_showcase_get_videos_is_def(self):
        assert self._func_type("showcase.py", "get_videos") is ast.FunctionDef

    def test_t2_showcase_get_video_is_def(self):
        assert self._func_type("showcase.py", "get_video") is ast.FunctionDef

    def test_t2_get_favorite_files_is_def(self):
        assert self._func_type("search.py", "get_favorite_files") is ast.FunctionDef

    def test_t2_get_local_status_is_def(self):
        assert self._func_type("search.py", "get_local_status") is ast.FunctionDef

    # T3 (71) — thumbnail cache 端點（sync def → Starlette threadpool）
    def test_t3_71_get_thumb_is_def(self):
        assert self._func_type("scanner.py", "get_thumb") is ast.FunctionDef

    def test_t3_71_thumb_prewarm_is_def(self):
        assert self._func_type("scanner.py", "thumb_prewarm") is ast.FunctionDef

    def test_t3_71_thumb_clear_is_def(self):
        # 71b-T2：DB-safe 清空端點。def → Starlette threadpool（rmtree 不阻塞 loop）。
        assert self._func_type("scanner.py", "thumb_clear") is ast.FunctionDef

    # T7 (71) — DELETE /api/showcase/video（sync def → Starlette threadpool；
    # body 內 repo.delete_by_paths / thumbnail_cache.invalidate 在 worker thread）
    def test_t7_71_delete_video_is_def(self):
        assert self._func_type("showcase.py", "delete_video") is ast.FunctionDef

    def test_t2_motion_lab_data_is_def(self):
        assert self._func_type("motion_lab.py", "motion_lab_data") is ast.FunctionDef

    # T3 — config / 設定檔 I/O 路由
    def test_t3_get_config_is_def(self):
        assert self._func_type("config.py", "get_config") is ast.FunctionDef

    def test_t3_update_config_is_def(self):
        assert self._func_type("config.py", "update_config") is ast.FunctionDef

    def test_t3_reset_config_is_def(self):
        assert self._func_type("config.py", "reset_config") is ast.FunctionDef

    def test_t3_get_tutorial_status_is_def(self):
        assert self._func_type("config.py", "get_tutorial_status") is ast.FunctionDef

    def test_t3_mark_tutorial_completed_is_def(self):
        assert self._func_type("config.py", "mark_tutorial_completed") is ast.FunctionDef

    def test_t3_reset_tutorial_is_def(self):
        assert self._func_type("config.py", "reset_tutorial") is ast.FunctionDef

    def test_t3_update_general_field_is_def(self):
        assert self._func_type("config.py", "update_general_field") is ast.FunctionDef

    def test_t3_get_scraper_sources_is_def(self):
        assert self._func_type("scraper_sources.py", "get_scraper_sources") is ast.FunctionDef

    def test_t3_get_favorite_scanner_link_is_def(self):
        assert self._func_type("settings_link.py", "get_favorite_scanner_link") is ast.FunctionDef


class TestT4OffloadHousePattern:
    """T4 to_thread 包裝的 house-pattern substring 守衛（延續既有 test_jellyfin_check_uses_to_thread）。"""

    @staticmethod
    def _src(filename: str) -> str:
        return (ROUTERS_DIR / filename).read_text(encoding="utf-8")

    def test_jellyfin_check_uses_to_thread_helper(self):
        src = self._src("scanner.py")
        assert "asyncio.to_thread(_check_jellyfin_needed" in src
        assert "def _check_jellyfin_needed(" in src
        assert "db_path.exists()" in src
        assert "VideoRepository(db_path)" in src
        assert "check_jellyfin_images_needed(repo, path_mappings)" in src

    def test_connect_uses_to_thread_helper(self):
        src = self._src("settings_metatube.py")
        assert "asyncio.to_thread(_connect_sync" in src
        assert "def _connect_sync(" in src
        assert "MetatubeHttpClient" in src
        assert "_verify_token_canary" in src

    def test_actress_crop_uses_to_thread(self):
        src = self._src("actress.py")
        assert "asyncio.to_thread(_check_cover_path" in src
        assert "asyncio.to_thread(crop_video_cover" in src

    def test_set_actress_photo_uses_to_thread(self):
        src = self._src("actress.py")
        assert "asyncio.to_thread(_load_actress" in src
        assert "asyncio.to_thread(_get_actress_videos" in src
        assert "asyncio.to_thread(_write_actress_photo" in src

    def test_search_stream_load_config_offloaded(self):
        assert "await asyncio.to_thread(load_config)" in self._src("search.py")

    def test_filter_files_uses_to_thread(self):
        src = self._src("search.py")
        assert "asyncio.to_thread(_filter_files_sync" in src
        assert "def _filter_files_sync(" in src

    def test_batch_enrich_load_config_offloaded(self):
        assert "await asyncio.to_thread(load_config)" in self._src("scraper.py")

    def test_batch_enrich_readonly_route_offloaded(self):
        # [lint-guard: pytest-justified] Python 源碼 async-offload 架構契約——
        # 「阻塞 helper 必須經 run_in_executor 包裝」是 event-loop 語意，eslint/
        # static_guard 無法表達；沿用本檔 TestT4OffloadHousePattern 既有 house-pattern。
        """TASK-104-T3/T5：batch-enrich 唯讀項改道（resolve_owning_output_root →
        resolve_ingest_plan → _produce_one，皆阻塞 I/O）須包在 nested sync helper
        `_do_readonly` 內、經 `run_in_executor` offload，不可在 async event_generator
        直接 body 裸跑。AST 主守衛（test_no_bare_blocking_in_async_routes）會抓「inline
        進直接 body」的回退，但「移除 executor 改 bare-call nested def」是 AST 掃描盲區
        （nested def 名不在偵測清單）→ 此正向 substring 鎖補位。"""
        src = self._src("scraper.py")
        assert "def _do_readonly(" in src, (
            "batch-enrich 唯讀改道須抽 nested sync helper `_do_readonly` 承載阻塞 I/O"
        )
        assert "run_in_executor(None, _do_readonly)" in src, (
            "`_do_readonly` 必須經 loop.run_in_executor offload —— 不可在 event_generator "
            "直接 body 呼叫（會卡 event loop）"
        )

    def test_translate_routes_load_config_offloaded(self):
        assert "await asyncio.to_thread(load_config)" in self._src("translate.py")


# ============================================================
# 66b-T5：config 寫入序列化守衛
# ============================================================

# 白名單（空）：config.py::update_config 改用 mutate_config（P2-1 修正：preserve server_mode），
# 不再直接呼叫 save_config，故白名單清空。
# 所有 router 一律不得裸呼 save_config：RMW 走 core.config.mutate_config（鎖內
# load→mutate→save），delete 走 reset_config_file（鎖內 exists/unlink）。
WHITELIST_SAVE_CONFIG: frozenset = frozenset()


def _find_save_config_callers(tree: ast.Module) -> list:
    """回傳 [(enclosing_func_name_or_None)] for every direct `save_config(...)` call.

    用最近的具名 enclosing function 標記每個 save_config 呼叫（含 nested def）。
    module-level 呼叫 → None。`_call_name` 同時涵蓋 `save_config()`（Name）與
    `core.config.save_config()`（Attribute.attr）。
    """
    callers = []

    def _walk(node, func_stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _walk(child, func_stack + [child.name])
            else:
                if isinstance(child, ast.Call) and _call_name(child) == "save_config":
                    callers.append(func_stack[-1] if func_stack else None)
                _walk(child, func_stack)

    _walk(tree, [])
    return callers


# 守衛掃描範圍：web/routers/*.py + web/app.py（後者的 get_common_context 在
# loop thread 上做 locale 首寫 RMW，與 threadpool config 寫入交錯會 lost-update，
# 故一併納入掃描，Codex P2）。
_WEB_DIR = ROUTERS_DIR.parent
SAVE_CONFIG_SCAN_FILES = tuple(sorted(ROUTERS_DIR.glob("*.py")) + [_WEB_DIR / "app.py"])


class TestConfigWriteSerializationGuard:
    """66b-T5：web/routers/*.py + web/app.py 不得裸呼 save_config（無白名單，一律禁止）。

    根據 CD-66b-1 / plan-66b T5：T1 把所有 config RMW caller 遷移到 mutate_config /
    reset_config_file（core/config.py 內單一 _config_write_lock 序列化 + 原子寫）。
    P2-1 修正後 config.py::update_config 亦改用 mutate_config（在鎖內 preserve server_mode），
    故白名單清空：任何 router 或 web/app.py 裸呼 save_config 均為 RMW 競態 → 守衛報錯。
    """

    def test_no_bare_save_config_outside_whitelist(self):
        violations = []
        for py_file in SAVE_CONFIG_SCAN_FILES:
            if py_file.name == "__init__.py":
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for func_name in _find_save_config_callers(tree):
                if (py_file.stem, func_name) in WHITELIST_SAVE_CONFIG:
                    continue
                violations.append(
                    f"{py_file.name}:{func_name}() — bare save_config() call"
                )
        assert not violations, (
            "Routers must not call save_config() directly (RMW lost-update risk): "
            "use core.config.mutate_config() for RMW or reset_config_file() for delete. "
            "No whitelist entries — all callers must use the atomic mutate_config pattern:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_update_config_uses_mutate_config_not_save_config(self):
        """P2-1 守衛：update_config 必須用 mutate_config（preserve server_mode），不得裸呼 save_config。

        P2-1 修正（config↔listener divergence）：update_config 改為在 mutate_config
        critical section 內讀取現有 server_mode 後才寫入，確保 full-config save 不會
        覆寫 toggle-lifecycle 持久化的 server_mode。若有人回退至 save_config，此守衛報錯。
        """
        src = (ROUTERS_DIR / "config.py").read_text(encoding="utf-8")
        assert "mutate_config(_write_preserving_server_mode)" in src, (
            "config.py::update_config 必須呼叫 mutate_config（_write_preserving_server_mode），"
            "以保持 server_mode 的 toggle-lifecycle 所有權"
        )
        tree = ast.parse(src, filename="config.py")
        callers = _find_save_config_callers(tree)
        assert "update_config" not in callers, (
            "config.py::update_config 不得直接呼叫 save_config —— 須透過 mutate_config "
            "在鎖內 preserve 現有 server_mode（P2-1 修正）"
        )
