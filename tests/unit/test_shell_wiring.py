# [lint-guard: pytest-justified]  AST 源碼語意（殼接線形狀）＋ lifecycle 接線
"""TASK-168a-T6: launcher / standalone 的載入網址、信任 origin、bridge 派送、關閉行為接線。"""
import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WINDOWS_DIR = REPO_ROOT / "windows"
if str(WINDOWS_DIR) not in sys.path:
    sys.path.insert(0, str(WINDOWS_DIR))

SHELL_FILES = ["launcher.py", "standalone.py"]


def _tree(name):
    path = WINDOWS_DIR / name
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _attr_chain(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _main_create_window(tree):
    """主視窗＝該檔唯一帶 ** 展開的 webview.create_window（CF 視窗的呼叫都沒有 **）。"""
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and _attr_chain(node.func) == "webview.create_window"
                and any(k.arg is None for k in node.keywords)):
            found.append(node)
    assert len(found) == 1
    return found[0]


def _enclosing_function(tree, target):
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and any(n is target for n in ast.walk(fn)):
            return fn
    return None


@pytest.mark.parametrize("name", ["launcher.py"])
def test_shells_load_url_and_trusted_origin_share_one_source(name):
    tree = _tree(name)
    cw = _main_create_window(tree)
    url = cw.args[1]
    # 入口網址來自 boot.url，boot 由 shell_boot.resolve_boot(...) 賦值
    assert isinstance(url, ast.Attribute) and url.attr == "url" and isinstance(url.value, ast.Name)
    boot_name = url.value.id
    resolves = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
        and _attr_chain(n.value.func) == "shell_boot.resolve_boot"
        and any(isinstance(t, ast.Name) and t.id == boot_name for t in n.targets)
    ]
    assert resolves, "boot 必須由 shell_boot.resolve_boot 賦值"

    trusted = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _attr_chain(node.func) == "api._set_trusted_origin":
            arg = node.args[0]
            if (isinstance(arg, ast.Call) and _attr_chain(arg.func) == "client_settings.server_origin"
                    and isinstance(arg.args[0], ast.Name)):
                trusted.append(node)
    assert len(trusted) == 1
    assert trusted[0].lineno < cw.lineno
    # 信任 origin 與 resolve_boot 吃同一個 origin 變數：模組層同名；或為函式參數，
    # 此時每個呼叫端傳入該參數的變數，必須就是同函式內餵給 resolve_boot 的那個
    origin_var = trusted[0].args[0].args[0].id
    fn = _enclosing_function(tree, trusted[0])
    if fn is None:
        assert origin_var in {r.value.args[0].id for r in resolves}
        return
    params = [a.arg for a in fn.args.args]
    assert origin_var in params
    idx = params.index(origin_var)
    callers = [c for c in ast.walk(tree) if isinstance(c, ast.Call)
               and isinstance(c.func, ast.Name) and c.func.id == fn.name]
    assert callers
    for call in callers:
        caller_fn = _enclosing_function(tree, call)
        passed = call.args[idx].id
        feeds = {
            r.args[0].id for r in ast.walk(caller_fn)
            if isinstance(r, ast.Call) and _attr_chain(r.func) == "shell_boot.resolve_boot"
        }
        assert passed in feeds


@pytest.mark.parametrize("name", SHELL_FILES)
def test_shells_pass_no_js_api_and_expose_whitelist(name):
    tree = _tree(name)
    cw = _main_create_window(tree)

    js_api_values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "js_api":
            js_api_values.append(node.value)
    assert js_api_values, "js_api=None 必須明寫"
    assert all(isinstance(v, ast.Constant) and v.value is None for v in js_api_values)

    expose = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and _attr_chain(n.func) == "window.expose"
        and len(n.args) == 1 and isinstance(n.args[0], ast.Starred)
        and isinstance(n.args[0].value, ast.Call)
        and _attr_chain(n.args[0].value.func) == "pywebview_api.exposed_functions"
    ]
    assert len(expose) == 1
    assert expose[0].lineno > cw.lineno


def test_local_mode_entry_url_golden(monkeypatch, tmp_path):
    from core import client_settings
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path))
    assert (client_settings.shell_entry_url("http://127.0.0.1:49152", "windows")
            == "http://127.0.0.1:49152/?oa_shell=windows&oa_mode=local")
    assert client_settings.server_origin("http://127.0.0.1:49152") == "http://127.0.0.1:49152"


def test_client_mode_entry_url_and_trusted_origin_same_origin(monkeypatch, tmp_path):
    from core import client_settings
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path))
    client_settings.save_client_settings(
        {"version": 1, "server": {"url": "http://192.168.1.180:8000", "token": ""}})
    local = "http://localhost:8000"
    assert client_settings.server_origin(local) == "http://192.168.1.180:8000"
    assert client_settings.shell_entry_url(local, "mac") == "http://192.168.1.180:8000/?oa_shell=mac&oa_mode=client"
