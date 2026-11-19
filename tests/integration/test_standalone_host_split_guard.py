"""
TASK-80a-T6b / TASK-130a-T1: standalone.py & health_probe.py loopback-only HOST AST/source 守衛

dual-listener 架構：
  - 主 listener 綁 127.0.0.1（loopback only，消除單機防火牆提示）
  - LAN listener（0.0.0.0）由 web/lan_listener.py 管理
  - health_probe.py 管理伺服器啟動與探活（無 webview 依賴）

驗證：
  (a) windows/health_probe.py 中 CLIENT_HOST = "127.0.0.1" 模組層賦值存在
  (b) windows/standalone.py 從 windows.health_probe 匯入 CLIENT_HOST（且無自立賦值）
  (c) windows/standalone.py 無 BIND_HOST 模組層賦值（已移除，不留殭屍）
  (d) standalone.py 與 health_probe.py 全檔無 "0.0.0.0" 字面（0.0.0.0 由 web/lan_listener.py 管理）
  (e) health_probe.py 中 uvicorn Config/Server 呼叫使用 host=CLIENT_HOST（不是 BIND_HOST）
  (f) standalone.py 中 find_free_port 的 sock.bind 使用 CLIENT_HOST（loopback probe）
  (g) health_probe.py 中 wait_for_server health URL 使用 CLIENT_HOST
  (h) standalone.py 中 main window create_window URL 使用 CLIENT_HOST
  (i) standalone.py 中 emit_notification auto-start 不暴露 str(e)

Mirror 慣例：Path.read_text() + ast.parse，不 import windows.standalone
（test env 無 webview 套件）。
"""
import ast
import pathlib

STANDALONE_PATH = pathlib.Path(__file__).parents[2] / "windows" / "standalone.py"
HEALTH_PROBE_PATH = pathlib.Path(__file__).parents[2] / "windows" / "health_probe.py"


def _parse_standalone():
    src = STANDALONE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(STANDALONE_PATH))
    return tree, src


def _parse_health_probe():
    src = HEALTH_PROBE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(HEALTH_PROBE_PATH))
    return tree, src


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    """收集所有「docstring 位置」的 Constant 節點 id（Module／ClassDef／FunctionDef 的第一個 Expr）。"""
    ids = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            ids.add(id(body[0].value))
    return ids


def _executable_string_literals_containing(tree: ast.AST, needle: str) -> list[int]:
    """回傳含有 `needle` 的**可執行**字串字面所在行號（排除註解與 docstring）。

    **為什麼是 AST 而不是「剝掉註解與字串再比對」**（PR #157 Codex P2，第三輪）：
    這條守衛禁的 `0.0.0.0` **本身就是一個字串字面**——若比照
    `tests/unit/test_metatube_routing_guard.py` 的做法把 STRING token 一起抹掉，
    要找的東西就跟著消失，守衛會變成永遠綠的空掃。
    （那支守衛找的是識別字 `routing_availability_map(`，剝字串才是對的；needle 的性質決定做法。）

    所以這裡改成走 AST：註解本來就不在 AST 裡（自動排除），docstring 是
    「函式／類別／模組 body 的第一個裸 Expr」，可以精準辨識並排除；
    真正的 `host="0.0.0.0"` 是被當成值使用的 Constant，照樣抓得到。
    """
    docstrings = _docstring_constant_ids(tree)
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and needle in node.value
        and id(node) not in docstrings
    ]


def _module_assignments(tree: ast.Module) -> list[ast.Assign]:
    """頂層 Assign 節點（非巢狀在函式/類別內）"""
    return [
        node for node in ast.iter_child_nodes(tree)
        if isinstance(node, ast.Assign)
    ]


def _assignment_name_value(node: ast.Assign):
    """回傳 (name_str | None, value)；僅支援單名稱賦值（Name target）。"""
    if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id, node.value
    return None, None


# [lint-guard: pytest-justified] Python-AST 源碼語意守衛（跨兩檔對帳 CLIENT_HOST 的賦值/匯入形狀），lint 表達不了
class TestStandaloneLoopbackOnlyGuard:
    """TASK-80a-T6b / TASK-130a-T1: loopback-only HOST 守衛（dual-listener 架構）"""

    def test_client_host_module_assignment_exists(self):
        """CLIENT_HOST = "127.0.0.1" 模組層賦值存在於 windows/health_probe.py"""
        tree, _ = _parse_health_probe()
        assigns = _module_assignments(tree)
        found = False
        for a in assigns:
            name, val = _assignment_name_value(a)
            if name == "CLIENT_HOST":
                assert isinstance(val, ast.Constant) and val.value == "127.0.0.1", (
                    f"CLIENT_HOST 存在但值不是 '127.0.0.1'，實際：{ast.unparse(val)}"
                )
                found = True
                break
        assert found, "windows/health_probe.py 中 CLIENT_HOST 模組層賦值未找到（需為 CLIENT_HOST = '127.0.0.1'）"


    def test_no_zero_zero_zero_zero_literal_in_standalone(self):
        """standalone.py 與 health_probe.py 無**可執行的** "0.0.0.0" 字串字面（已移至 web/lan_listener.py）。

        註解與 docstring 不算——說明「為什麼主 listener 不綁 0.0.0.0」的文件
        不該讓測試轉紅（PR #157 Codex P2，第三輪）。判別方式見
        `_executable_string_literals_containing()` 的 docstring。
        """
        for label, (tree, _src) in (
            ("standalone.py", _parse_standalone()),
            ("health_probe.py", _parse_health_probe()),
        ):
            hits = _executable_string_literals_containing(tree, "0.0.0.0")
            assert not hits, (
                f"{label} 的第 {hits} 行有可執行的 '0.0.0.0' 字串字面——"
                "主 listener 與探活應只綁 loopback；0.0.0.0 由 web/lan_listener.py 管理。\n"
                "（若這是說明文字，請寫成註解或 docstring；那兩者不會被這條守衛擋。）"
            )

    def test_uvicorn_config_uses_client_host(self):
        """
        uvicorn.Config(..., host=CLIENT_HOST, ...) 使用 CLIENT_HOST（loopback）。
        確認 host=CLIENT_HOST 出現，且無 host=BIND_HOST。
        """
        _, src = _parse_health_probe()
        lines = src.splitlines()

        # 找 uvicorn.Config 或 uvicorn.run 呼叫段落
        uvicorn_lines = [
            (i, line) for i, line in enumerate(lines, 1)
            if "uvicorn" in line and ("Config" in line or "run(" in line)
        ]
        assert uvicorn_lines, "health_probe.py 中找不到 uvicorn.Config / uvicorn.run 呼叫"

        # 找 host=CLIENT_HOST 出現（主 listener 綁 loopback）
        host_client_lines = [
            (i, line) for i, line in enumerate(lines, 1)
            if "host=CLIENT_HOST" in line
        ]
        assert host_client_lines, (
            "找不到 host=CLIENT_HOST — uvicorn 主 listener 應綁 CLIENT_HOST（127.0.0.1）"
        )

        # 確認無 host=BIND_HOST（BIND_HOST 已移除）
        host_bind_lines = [
            (i, line) for i, line in enumerate(lines, 1)
            if "host=BIND_HOST" in line
        ]
        assert not host_bind_lines, (
            f"uvicorn 仍用 host=BIND_HOST 在 line(s) "
            f"{[i for i, _ in host_bind_lines]}；"
            "應使用 host=CLIENT_HOST（loopback only）"
        )


    def test_emit_notification_autostart_does_not_pass_str_e(self):
        """
        auto-start 失敗的 emit_notification 呼叫不可傳入 str(e)（安全規則：
        Python 例外細節不暴露給前端）。
        """
        _, src = _parse_standalone()
        # 找 emit_notification(... 那一行
        lines = [line for line in src.splitlines() if "emit_notification" in line]
        assert lines, "standalone.py 中找不到 emit_notification 呼叫"
        for line in lines:
            assert "str(e)" not in line, (
                f"emit_notification 呼叫不可包含 str(e)（安全規則）：{line!r}"
            )



