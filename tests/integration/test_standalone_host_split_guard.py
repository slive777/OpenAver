"""
TASK-80a-T6b: standalone.py loopback-only HOST AST/source 守衛

dual-listener 架構（T6b 起）：
  - 主 listener 綁 127.0.0.1（loopback only，消除單機防火牆提示）
  - LAN listener（0.0.0.0）由 web/lan_listener.py 管理

驗證 windows/standalone.py 中：
  (a) CLIENT_HOST = "127.0.0.1" 模組層賦值存在
  (b) 無 BIND_HOST 模組層賦值（已移除，不留殭屍）
  (c) standalone.py 全檔無 "0.0.0.0" 字面（已移至 web/lan_listener.py）
  (d) uvicorn Config/Server 呼叫使用 host=CLIENT_HOST（不是 BIND_HOST）
  (e) find_free_port 的 sock.bind 使用 CLIENT_HOST（loopback probe）
  (f) wait_for_server health URL 使用 CLIENT_HOST
  (g) main window create_window URL 使用 CLIENT_HOST

Mirror 慣例：Path.read_text() + ast.parse，不 import windows.standalone
（test env 無 webview 套件）。
"""
import ast
import pathlib

STANDALONE_PATH = pathlib.Path(__file__).parents[2] / "windows" / "standalone.py"


def _parse():
    src = STANDALONE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(STANDALONE_PATH))
    return tree, src


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


class TestStandaloneLoopbackOnlyGuard:
    """TASK-80a-T6b: loopback-only HOST 守衛（dual-listener 架構，原 T2 改寫）"""

    def test_client_host_module_assignment_exists(self):
        """CLIENT_HOST = "127.0.0.1" 模組層賦值存在"""
        tree, _ = _parse()
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
        assert found, "CLIENT_HOST 模組層賦值未找到（需為 CLIENT_HOST = '127.0.0.1'）"

    def test_no_bind_host_module_assignment(self):
        """無 BIND_HOST 模組層賦值（dual-listener 後 standalone 不再綁 0.0.0.0）"""
        tree, _ = _parse()
        assigns = _module_assignments(tree)
        violations = []
        for a in assigns:
            name, _ = _assignment_name_value(a)
            if name == "BIND_HOST":
                violations.append(a.lineno)
        assert not violations, (
            f"BIND_HOST 模組層賦值殘留在 line(s) {violations}，"
            "T6b 起 BIND_HOST 應已移除（0.0.0.0 由 web/lan_listener.py 管理）"
        )

    def test_no_zero_zero_zero_zero_literal_in_standalone(self):
        """standalone.py 全檔無 \"0.0.0.0\" 字面（已移至 web/lan_listener.py）"""
        _, src = _parse()
        assert "0.0.0.0" not in src, (
            "standalone.py 含有 '0.0.0.0' 字面——T6b 後主 listener 應只綁 loopback；"
            "0.0.0.0 應在 web/lan_listener.py 中"
        )

    def test_uvicorn_config_uses_client_host(self):
        """
        uvicorn.Config(..., host=CLIENT_HOST, ...) 使用 CLIENT_HOST（loopback）。
        確認 host=CLIENT_HOST 出現，且無 host=BIND_HOST。
        """
        _, src = _parse()
        lines = src.splitlines()

        # 找 uvicorn.Config 或 uvicorn.run 呼叫段落
        uvicorn_lines = [
            (i, line) for i, line in enumerate(lines, 1)
            if "uvicorn" in line and ("Config" in line or "run(" in line)
        ]
        assert uvicorn_lines, "standalone.py 中找不到 uvicorn.Config / uvicorn.run 呼叫"

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
            "T6b 後應使用 host=CLIENT_HOST（loopback only）"
        )

    def test_find_free_port_uses_client_host(self):
        """
        find_free_port 的 sock.bind 使用 CLIENT_HOST（loopback probe）。
        """
        _, src = _parse()
        assert "sock.bind((CLIENT_HOST," in src, (
            "find_free_port 的 sock.bind 應使用 CLIENT_HOST（loopback，不是 0.0.0.0）"
        )

    def test_wait_for_server_uses_client_host(self):
        """
        wait_for_server health URL 使用 CLIENT_HOST。
        """
        _, src = _parse()
        health_lines = [
            line for line in src.splitlines()
            if "/api/health" in line
        ]
        assert health_lines, "找不到 /api/health URL 行"
        for line in health_lines:
            assert "CLIENT_HOST" in line, (
                f"health URL 行不含 CLIENT_HOST：{line!r}"
            )

    def test_main_window_create_window_uses_client_host(self):
        """
        main window（OpenAver）的 create_window URL 使用 CLIENT_HOST、非 BIND_HOST。
        主視窗 URL 為 f'http://{CLIENT_HOST}:{port}'（mutation-sensitive）。
        """
        _, src = _parse()
        assert "f'http://{CLIENT_HOST}:{port}'" in src, (
            "主視窗 create_window URL 應為 f'http://{CLIENT_HOST}:{port}'（CLIENT_HOST、非 BIND_HOST）"
        )
        assert "f'http://{BIND_HOST}:{port}'" not in src, (
            "主視窗 URL 不可用 BIND_HOST（桌面 App 須走 loopback）"
        )
