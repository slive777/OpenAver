"""
tests/unit/test_uri_to_fs_path_reverse_mapping_completeness.py
AST 結構守衛 — 防 uri_to_fs_path() 回傳值未經 marker 豁免就流向磁碟 I/O 的漏網回歸。
spec-91 / plan-91.md §5 D3 / TASK-91-T6.md

守衛範圍（保守，見 plan-91 §7 ⚠️ T6 邊界紀律）：
- 只抓兩種形狀：direct-nesting（同語句嵌套）、assign-then-use（同函式內賦值後使用）。
- 不做跨函式資料流、不做別名追蹤、不做 return-then-caller-uses。漏抓靠 code review 補。
- 唯一豁免 = `# uri-no-reverse:` marker（貼在呼叫所在行或緊鄰上一行）。
"""
import ast
from pathlib import Path

EXCLUDE_PREFIXES = ("tests/", "archive/", "venv/", ".venv/", "build/", "node_modules/")
EXCLUDE_FILES = ("core/path_utils.py",)

MARKER = "# uri-no-reverse:"

# os.path.<attr> 磁碟 I/O 集合
_OS_PATH_DISK_ATTRS = {"exists", "isfile", "isdir", "getsize", "getmtime", "realpath", "stat"}
# os.<attr> 磁碟 I/O 集合
_OS_DISK_ATTRS = {"scandir", "listdir", "remove", "stat", "makedirs", "startfile"}
# Path(...).<attr> 磁碟 I/O 集合
_PATH_DISK_ATTRS = {
    "read_bytes", "read_text", "exists", "is_file", "is_dir",
    "glob", "iterdir", "stat", "write_bytes", "write_text",
}
# 純字串 helper（direct-nesting 時允許中間巢狀，不視為「已消費」uri_to_fs_path 回傳值）
_PURE_STRING_HELPERS = {"dirname", "splitext", "join"}


def _is_uri_to_fs_path_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "uri_to_fs_path"
    )


def _is_disk_io_call(node: ast.Call) -> bool:
    """判斷此 Call node 本身是否為磁碟 I/O 呼叫（依函式/屬性名比對）。"""
    func = node.func

    # builtin open(...)
    if isinstance(func, ast.Name) and func.id == "open":
        return True

    # FileResponse(...)
    if isinstance(func, ast.Name) and func.id == "FileResponse":
        return True

    if isinstance(func, ast.Attribute):
        attr = func.attr
        value = func.value

        # os.path.<attr>(...)
        if (
            isinstance(value, ast.Attribute)
            and value.attr == "path"
            and isinstance(value.value, ast.Name)
            and value.value.id == "os"
            and attr in _OS_PATH_DISK_ATTRS
        ):
            return True

        # os.<attr>(...)
        if isinstance(value, ast.Name) and value.id == "os" and attr in _OS_DISK_ATTRS:
            return True

        # shutil.<attr>(...) — 任何 shutil 屬性都算
        if isinstance(value, ast.Name) and value.id == "shutil":
            return True

        # Path(...).<attr>(...)  — value 本身是 Path(...) 呼叫
        if (
            attr in _PATH_DISK_ATTRS
            and isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "Path"
        ):
            return True

    return False


def _is_pure_string_helper_call(node: ast.AST) -> bool:
    """os.path.dirname / os.path.splitext / os.path.join 等純字串 helper 呼叫。"""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    func = node.func
    value = func.value
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "path"
        and isinstance(value.value, ast.Name)
        and value.value.id == "os"
        and func.attr in _PURE_STRING_HELPERS
    )


def _has_marker(source_lines: list[str], lineno: int) -> bool:
    """呼叫所在行（1-based lineno）或緊鄰上一行是否含 marker。"""
    idx = lineno - 1
    if 0 <= idx < len(source_lines) and MARKER in source_lines[idx]:
        return True
    if 0 <= idx - 1 < len(source_lines) and MARKER in source_lines[idx - 1]:
        return True
    return False


def _is_path_constructor_call(node: ast.AST) -> bool:
    """`Path(...)` 呼叫本身（尚未接 disk-method attribute）。"""
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Path"


def _path_call_feeds_disk_method(path_call: ast.Call, funcdef: ast.AST) -> bool:
    """`path_call`（一個 Path(...) 呼叫）是否被同函式內某 `.<disk-method>(...)` 直接接住。

    對應 `Path(uri_to_fs_path(x)).exists()` 這種同語句寫法：uri_to_fs_path(x) 是
    Path(...) 呼叫的引數，而 Path(...) 呼叫又是 .exists() 的 value（非引數），
    原本的「call_node in args」判斷抓不到這層，需另外比對 attribute call 的 func.value。
    """
    for node in ast.walk(funcdef):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _PATH_DISK_ATTRS
            and node.func.value is path_call
        ):
            return True
    return False


def _direct_nesting_hits_disk_io(call_node: ast.Call, funcdef: ast.AST) -> bool:
    """從 call_node 往外找最近的 Call 祖先鏈（含穿過純字串 helper），判斷是否嵌套進磁碟 I/O 呼叫。

    保守實作：走訪 funcdef 內所有 Call node，若某 Call 是磁碟 I/O 或純字串 helper，
    且其引數鏈（可遞迴穿過純字串 helper）到達 call_node，且該鏈最終被某磁碟 I/O 呼叫吃下，判定命中。
    """
    # 找出「直接吃下 call_node 的 Call」，可能是磁碟 I/O，也可能是純字串 helper（需再往外一層）
    for node in ast.walk(funcdef):
        if not isinstance(node, ast.Call):
            continue
        args = list(node.args) + [kw.value for kw in node.keywords]
        if call_node in args:
            if _is_disk_io_call(node):
                return True
            if _is_pure_string_helper_call(node):
                # 純字串 helper 消費了 call_node，再往外找是否被磁碟 I/O 呼叫吃下
                if _direct_nesting_hits_disk_io(node, funcdef):
                    return True
            if _is_path_constructor_call(node) and _path_call_feeds_disk_method(node, funcdef):
                return True
    return False


def _assign_then_use_hits_disk_io(assign_target_name: str, funcdef: ast.AST, after_node: ast.AST) -> bool:
    """在同一函式 body 內，assign_target_name 是否作為引數出現在磁碟 I/O 呼叫，
    或 Path(var).<disk-method>，或 os.path.<op>(var)。"""
    for node in ast.walk(funcdef):
        if not isinstance(node, ast.Call):
            continue

        # var 作為引數傳入磁碟 I/O 呼叫（含 open/FileResponse/os.*/shutil.*）
        if _is_disk_io_call(node):
            args = list(node.args) + [kw.value for kw in node.keywords]
            for a in args:
                if isinstance(a, ast.Name) and a.id == assign_target_name:
                    return True

        # Path(var).<disk-method>(...)
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in _PATH_DISK_ATTRS
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Name)
            and node.func.value.func.id == "Path"
        ):
            path_args = node.func.value.args
            if any(isinstance(a, ast.Name) and a.id == assign_target_name for a in path_args):
                return True

        # os.path.<op>(var) — 已被 _is_disk_io_call 涵蓋（op 屬於 _OS_PATH_DISK_ATTRS 時）
        # 此處保留註解澄清：os.path.<op>(var) 本就落在上面 _is_disk_io_call 分支。

    return False


def _scan_source(source: str, filename: str = "<test>") -> list[str]:
    """AST-parse source，回傳未豁免且回傳值流向磁碟 I/O 的 uri_to_fs_path(...) 呼叫 violation list。"""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []

    source_lines = source.splitlines()
    violations = []

    for funcdef in ast.walk(tree):
        if not isinstance(funcdef, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for node in ast.walk(funcdef):
            if not _is_uri_to_fs_path_call(node):
                continue

            if _has_marker(source_lines, node.lineno):
                continue

            # Shape 1: direct-nesting
            if _direct_nesting_hits_disk_io(node, funcdef):
                violations.append(
                    f"{filename}:{node.lineno}: unmarked uri_to_fs_path() call nested directly "
                    f"into a disk I/O call within function `{funcdef.name}`. "
                    f"Fix: use uri_to_local_fs_path() or add '# uri-no-reverse: <reason>'."
                )
                continue

            # Shape 2: assign-then-use — 找出此 call 所屬的最外層 Assign（若有）
            target_name = _find_assign_target_name(funcdef, node)
            if target_name and _assign_then_use_hits_disk_io(target_name, funcdef, node):
                violations.append(
                    f"{filename}:{node.lineno}: unmarked uri_to_fs_path() call assigned to "
                    f"`{target_name}` which later reaches disk I/O within function `{funcdef.name}`. "
                    f"Fix: use uri_to_local_fs_path() or add '# uri-no-reverse: <reason>'."
                )

    return violations


def _find_assign_target_name(funcdef: ast.AST, call_node: ast.Call):
    """在 funcdef 內找出 `var = ...call_node...`（單一 Name target）的 var 名稱，
    僅當 call_node 出現在該 Assign 的 value 運算式中（walk 整個 value 子樹）。"""
    for node in ast.walk(funcdef):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if call_node is node.value or call_node in ast.walk(node.value):
            return node.targets[0].id
    return None


def _scan_repo() -> list[str]:
    root = Path(".")
    violations = []
    for path in sorted(root.rglob("*.py")):
        rel = path.as_posix()
        if any(rel.startswith(p) for p in EXCLUDE_PREFIXES):
            continue
        if rel in EXCLUDE_FILES:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "uri_to_fs_path(" not in source:
            continue
        violations.extend(_scan_source(source, filename=rel))
    return violations


def test_no_unmarked_uri_to_fs_path_before_disk_io():
    """全 repo 掃描：所有裸 uri_to_fs_path() 呼叫若回傳值流向磁碟 I/O，必須有
    '# uri-no-reverse:' marker（同行或上一行）。T5 已對現況 27 站台補齊 marker，故現況應為 0。
    """
    violations = _scan_repo()
    assert violations == [], (
        f"Found {len(violations)} unmarked uri_to_fs_path() call(s) reaching disk I/O:\n"
        + "\n".join(violations)
    )


def test_guard_catches_planted_violation_assign_then_use():
    source = (
        "def bad():\n"
        "    p = uri_to_fs_path(v.cover_path)\n"
        "    if os.path.exists(p):\n"
        "        return p\n"
    )
    assert _scan_source(source) != []


def test_guard_catches_direct_nesting():
    source = (
        "def bad():\n"
        "    if os.path.exists(uri_to_fs_path(x)):\n"
        "        pass\n"
    )
    assert _scan_source(source) != []


def test_guard_respects_marker_same_line():
    source = (
        "def bad():\n"
        "    p = uri_to_fs_path(v.cover_path)  # uri-no-reverse: reason\n"
        "    if os.path.exists(p):\n"
        "        return p\n"
    )
    assert _scan_source(source) == []


def test_guard_respects_marker_prev_line():
    source = (
        "def bad():\n"
        "    # uri-no-reverse: reason\n"
        "    p = uri_to_fs_path(v.cover_path)\n"
        "    if os.path.exists(p):\n"
        "        return p\n"
    )
    assert _scan_source(source) == []


def test_guard_catches_path_constructor_direct_nesting():
    source = (
        "def bad():\n"
        "    if Path(uri_to_fs_path(x)).exists():\n"
        "        pass\n"
    )
    assert _scan_source(source) != []


def test_guard_respects_marker_on_path_constructor_direct_nesting():
    source = (
        "def bad():\n"
        "    if Path(uri_to_fs_path(x)).exists():  # uri-no-reverse: reason\n"
        "        pass\n"
    )
    assert _scan_source(source) == []


def test_guard_ignores_non_disk_use():
    source = (
        "def ok():\n"
        "    p = uri_to_fs_path(x)\n"
        "    if p == other:\n"
        "        return p\n"
    )
    assert _scan_source(source) == []
