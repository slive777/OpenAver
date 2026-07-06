"""
tests/unit/test_db_key_namespace_completeness.py
AST 結構守衛 — 防「DB-key 建構 sink」在無 marker 情況下吃進命名空間錯誤的路徑值
（axis-B：污染值 / 裸本機路徑 → DB round-trip 命名空間）。
plan-91b.md §5 D3 / TASK-91b-T2.md

守衛骨架複用 T6（`test_uri_to_fs_path_reverse_mapping_completeness.py`），
換掉「危險呼叫」與「sink」判斷；獨立 marker、獨立檔案，不混進 T6（D2）。

## 偵測範圍（sink-anchored，見 plan-91b §5 D3）

1. **primitive sink**：`to_file_uri(X)` 只有 1 個引數（無 `path_mappings`）→ 其回傳值同函式內
   直接嵌套（Shape 1）或賦值後使用（Shape 2）流向 `_DB_KEY_SINK_METHODS` 集合的 repo 方法呼叫，
   或流向 `is_known_cover_path(...)`。`to_file_uri(X, path_mappings)`（帶第二引數）視為已
   forward-map，**自動放行、不查 marker**。
2. **`is_known_cover_path(X)` 直接命中**：本身即 sink（非需再流向下一層）。若引數本身是巢狀
   `to_file_uri(X)` 呼叫，已由上述 Shape 1 涵蓋；若引數是裸變數/其他運算式，此呼叫本身即為
   命中點，查其呼叫行的 marker（含兩層搜尋，見下）。
3. **wrapper sink callsite**（`WRAPPER_SINK_NAMES`）：已登記 helper（`_db_upsert` /
   `_db_upsert_samples_only` / `_check_cover_path`）内部已用 primitive sink 建 DB key，
   命名空間正確性委派給呼叫端（callsite）保證。守衛偵測其 **callsite**（不查 helper 本體，
   本體已用一次性 docstring `db-ns-ok: enforced at callsites` 說明委派），含兩種語法形狀：
   - 直接呼叫：`_db_upsert(...)` / `_db_upsert_samples_only(...)` / `_check_cover_path(...)`。
   - 間接呼叫：`asyncio.to_thread(_check_cover_path, cover_fs_for_db)`（wrapper 名稱是
     `to_thread` 的第一個引數，真正路徑實參往後位移一格）。

## Marker 豁免（⭐ Opus 裁決：canonical 兩層 marker 規則，不放寬「上 N 行」）

固定兩層 OR：
① sink 命中行（該 `ast.Call` 節點的 `lineno`）或其正上一行含 `# db-ns-ok:`；
② 若 sink 的「路徑實參」是同函式內的區域變數（`ast.Name`）→ 該變數賦值語句所在行
   或其正上一行含 `# db-ns-ok:`（複用 T6 `_find_assign_target_name` 風格，單變數同函式不跨跳）。

任一層命中即豁免。**嚴禁**放寬成「上 N 行」——這是精確度與 per-site hackery 的分界。

wrapper helper **本體**內部的 primitive sink（如 `_db_upsert` 內 `to_file_uri(fs_path)`）
因命名空間正確性已委派給 callsite（D3 設計），**不在此守衛的 primitive-sink 掃描範圍內**
（守衛跳過 `funcdef.name in WRAPPER_SINK_NAMES` 的函式本體做 primitive/`is_known_cover_path`
掃描；wrapper callsite 掃描則不受此排除，正常掃描所有函式）。

## 已知射程外（不抓，靠 code review 補，見 plan-91b §3）

- 手工拼接的 raw SQL 字串（`f"UPDATE videos SET ... WHERE path='{x}'"`）/ `conn.execute(...)`
  裸呼叫——字串拼接非 `ast.Call`，且 `conn.execute` 不在 `_DB_KEY_SINK_METHODS`，屬已知射程外
  （即使剛好因既有 marker 而不誤報，也非本守衛刻意涵蓋，勿誤以為涵蓋）。
- 跨函式/跨模組傳遞後才建 key（值先 `return`，在 caller 端才 `to_file_uri`）——不抓，
  T6 的 Shape 1/2 皆限定同函式內，T2 沿用相同限制。
- 未登記的新 wrapper helper（未來新增類似 `_db_upsert` 但未加進 `WRAPPER_SINK_NAMES`）——
  不抓，守衛詞彙表需人工維護，比照 T6 磁碟 I/O 白名單也是硬編碼集合、非動態推導。
- 經多層別名的 sink（`f = repo.get_by_path; f(to_file_uri(x))`）——不抓。
"""
import ast
from pathlib import Path

EXCLUDE_PREFIXES = ("tests/", "archive/", "venv/", ".venv/", "build/", "node_modules/")
EXCLUDE_FILES = ("core/path_utils.py",)

MARKER = "# db-ns-ok:"

# repo path 方法（DB-key sink）窮舉集合（T1 窮舉，plan-91b §6.2）
_DB_KEY_SINK_METHODS = {
    "get_by_path", "update_user_tags", "update_scrape_attempted_at",
    "update_sample_images", "repath", "repath_path_only",
}

# 已登記 wrapper sink helper（T1 窮舉，plan-91b §6.2）+ 各自「路徑實參」在其呼叫式中的
# 0-based 位置索引（direct-call 情形；asyncio.to_thread 間接呼叫時，真正引數位置整體
# 往後位移 1，因 to_thread(fn, *args) 的 args[0] 是 fn 本身）
WRAPPER_SINK_NAMES = {"_db_upsert", "_db_upsert_samples_only", "_check_cover_path"}
# 各 wrapper「路徑實參」在其呼叫式中的 0-based 位置索引 + 參數名（direct-call 情形；
# asyncio.to_thread 間接呼叫時，真正引數位置整體往後位移 1，因 to_thread(fn, *args) 的
# args[0] 是 fn 本身）。參數名用於支援 keyword 傳參 callsite（`_db_upsert(..., fs_path=x)`）。
_WRAPPER_PATH_ARG = {
    "_db_upsert": (2, "fs_path"),                # _db_upsert(repo, number, fs_path, meta, ...)
    "_db_upsert_samples_only": (1, "fs_path"),   # _db_upsert_samples_only(repo, fs_path, sample_images)
    "_check_cover_path": (0, "fs_path"),         # _check_cover_path(fs_path)
}


def _extract_wrapper_arg(node_args, node_keywords, idx, param_name, offset=0):
    """依位置（含 offset）或 keyword 名稱取出 wrapper 呼叫式中的路徑實參節點；
    兩者皆未命中回傳 None（呼叫端視為無法判定，跳過該 callsite）。"""
    if idx is not None and (offset + idx) < len(node_args):
        return node_args[offset + idx]
    for kw in node_keywords:
        if kw.arg == param_name:
            return kw.value
    return None


def _is_primitive_sink_call(node: ast.AST) -> bool:
    """`to_file_uri(X)` 且僅有 1 個引數（無 path_mappings，未 forward-map）。"""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "to_file_uri"
    ):
        return False
    return (len(node.args) + len(node.keywords)) == 1


def _is_db_key_sink_call(node: ast.AST) -> bool:
    """`repo.<method>(...)` / `VideoRepository().<method>(...)`，method 屬於
    `_DB_KEY_SINK_METHODS`。不強求 receiver 變數名（比照 T6 對 os.path.<attr> 的寬鬆比對）。"""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _DB_KEY_SINK_METHODS
    )


def _is_known_cover_path_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "is_known_cover_path"
    )


def _is_sink_call(node: ast.AST) -> bool:
    """Shape 1/2 nesting/assign 判斷用的統一 sink 集合：repo path 方法 或 is_known_cover_path。"""
    return _is_db_key_sink_call(node) or _is_known_cover_path_call(node)


def _is_wrapper_direct_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in WRAPPER_SINK_NAMES
    )


def _is_asyncio_to_thread_wrapper_call(node: ast.AST) -> bool:
    """`asyncio.to_thread(<wrapper_name>, ...)` 間接呼叫形狀。"""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "to_thread"
    ):
        return False
    if not node.args:
        return False
    first = node.args[0]
    return isinstance(first, ast.Name) and first.id in WRAPPER_SINK_NAMES


def _has_marker(source_lines: list[str], lineno: int) -> bool:
    """呼叫所在行（1-based lineno）或緊鄰上一行是否含 marker。"""
    idx = lineno - 1
    if 0 <= idx < len(source_lines) and MARKER in source_lines[idx]:
        return True
    if 0 <= idx - 1 < len(source_lines) and MARKER in source_lines[idx - 1]:
        return True
    return False


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


def _find_assign_lineno_for_name(funcdef: ast.AST, name: str, before_lineno: int):
    """在 funcdef 內找出 lineno < before_lineno 的最近一次 `name = ...`（單一 Name target）
    賦值語句 lineno（reaching-definition 近似：只取 sink 之前的賦值，避免 sink 之後的同名
    重賦值遮蔽/誤扯 marker 判斷；非真正資料流分析，單函式內不跨跳）。"""
    lineno = None
    for node in ast.walk(funcdef):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
            and node.lineno < before_lineno
            and (lineno is None or node.lineno > lineno)
        ):
            lineno = node.lineno
    return lineno


def _has_marker_two_layer(source_lines: list[str], sink_lineno: int, arg_node, funcdef: ast.AST) -> bool:
    """⭐ Opus 裁決兩層 OR：① sink 命中行/上一行；② 若路徑實參是同函式區域變數 →
    該變數「sink 之前最近一次」賦值行/上一行。任一層命中即豁免。"""
    if _has_marker(source_lines, sink_lineno):
        return True
    if isinstance(arg_node, ast.Name):
        assign_lineno = _find_assign_lineno_for_name(funcdef, arg_node.id, sink_lineno)
        if assign_lineno is not None and _has_marker(source_lines, assign_lineno):
            return True
    return False


def _direct_nesting_hits_sink(call_node: ast.Call, funcdef: ast.AST) -> bool:
    """Shape 1：`repo.get_by_path(to_file_uri(x))` / `repo.is_known_cover_path(to_file_uri(x))`
    同語句嵌套。"""
    for node in ast.walk(funcdef):
        if not isinstance(node, ast.Call):
            continue
        args = list(node.args) + [kw.value for kw in node.keywords]
        if call_node in args and _is_sink_call(node):
            return True
    return False


def _assign_then_use_hits_sink(assign_target_name: str, funcdef: ast.AST) -> bool:
    """Shape 2：`path_uri = to_file_uri(x); repo.get_by_path(path_uri)` 同函式內
    賦值後使用。"""
    for node in ast.walk(funcdef):
        if not _is_sink_call(node):
            continue
        args = list(node.args) + [kw.value for kw in node.keywords]
        for a in args:
            if isinstance(a, ast.Name) and a.id == assign_target_name:
                return True
    return False


def _scan_source(source: str, filename: str = "<test>") -> list[str]:
    """AST-parse source，回傳未豁免的 DB-key 命名空間 sink violation list。"""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []

    source_lines = source.splitlines()
    violations: list[str] = []

    for funcdef in ast.walk(tree):
        if not isinstance(funcdef, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        is_wrapper_body = funcdef.name in WRAPPER_SINK_NAMES

        if not is_wrapper_body:
            # --- primitive sink：Shape 1 / Shape 2 ---
            for node in ast.walk(funcdef):
                if not _is_primitive_sink_call(node):
                    continue

                if _has_marker(source_lines, node.lineno):
                    continue

                if _direct_nesting_hits_sink(node, funcdef):
                    violations.append(
                        f"{filename}:{node.lineno}: unmarked to_file_uri() call nested directly "
                        f"into a DB-key sink within function `{funcdef.name}`. "
                        f"Fix: pass path_mappings, use _for_db pattern, or add '# db-ns-ok: <reason>'."
                    )
                    continue

                target_name = _find_assign_target_name(funcdef, node)
                if target_name and _assign_then_use_hits_sink(target_name, funcdef):
                    violations.append(
                        f"{filename}:{node.lineno}: unmarked to_file_uri() call assigned to "
                        f"`{target_name}` which later reaches a DB-key sink within function "
                        f"`{funcdef.name}`. Fix: pass path_mappings, use _for_db pattern, "
                        f"or add '# db-ns-ok: <reason>'."
                    )

            # --- is_known_cover_path 直接命中（引數非巢狀 to_file_uri，已由上方 Shape 1 涵蓋） ---
            for node in ast.walk(funcdef):
                if not _is_known_cover_path_call(node):
                    continue
                if not node.args:
                    continue
                arg = node.args[0]
                if (
                    isinstance(arg, ast.Call)
                    and isinstance(arg.func, ast.Name)
                    and arg.func.id == "to_file_uri"
                ):
                    continue  # 已由 Shape 1（direct-nesting）涵蓋，避免重複列舉
                if _has_marker_two_layer(source_lines, node.lineno, arg, funcdef):
                    continue
                violations.append(
                    f"{filename}:{node.lineno}: unmarked is_known_cover_path() call within "
                    f"function `{funcdef.name}` — DB-key namespace not verified. "
                    f"Fix: ensure argument round-trips to mapped namespace or add "
                    f"'# db-ns-ok: <reason>'."
                )

        # --- wrapper sink callsite（直接呼叫 + asyncio.to_thread 間接呼叫），不受 wrapper 本體排除 ---
        for node in ast.walk(funcdef):
            arg_node = None
            wrapper_name = None

            if _is_wrapper_direct_call(node):
                wrapper_name = node.func.id
                idx, param_name = _WRAPPER_PATH_ARG.get(wrapper_name, (None, None))
                arg_node = _extract_wrapper_arg(node.args, node.keywords, idx, param_name)
            elif _is_asyncio_to_thread_wrapper_call(node):
                wrapper_name = node.args[0].id
                idx, param_name = _WRAPPER_PATH_ARG.get(wrapper_name, (None, None))
                # to_thread(fn, *args, **kwargs) 的 keywords 直接 forward 給 fn，
                # 故 keyword 查找用 node.keywords（不需 offset）；位置引數需 offset=1。
                arg_node = _extract_wrapper_arg(node.args, node.keywords, idx, param_name, offset=1)

            if arg_node is None:
                continue

            if _has_marker_two_layer(source_lines, node.lineno, arg_node, funcdef):
                continue

            violations.append(
                f"{filename}:{node.lineno}: unmarked callsite of wrapper sink `{wrapper_name}` "
                f"within function `{funcdef.name}` — DB-key namespace not verified. "
                f"Fix: ensure argument round-trips to mapped namespace or add "
                f"'# db-ns-ok: <reason>'."
            )

    return violations


def _scan_repo() -> list[str]:
    root = Path(".")
    violations: list[str] = []
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
        if (
            "to_file_uri(" not in source
            and "is_known_cover_path(" not in source
            and not any(name in source for name in WRAPPER_SINK_NAMES)
        ):
            continue
        violations.extend(_scan_source(source, filename=rel))
    return violations


def test_no_unmarked_db_key_namespace_violations():
    """全 repo 掃描：DB-key 建構 sink（primitive / is_known_cover_path / wrapper callsite）
    必須有 '# db-ns-ok:' marker（兩層 OR）或已 forward-map（帶 path_mappings）。
    T1 已補齊現況 marker，故現況應為 0。
    """
    violations = _scan_repo()
    assert violations == [], (
        f"Found {len(violations)} unmarked DB-key namespace sink(s):\n"
        + "\n".join(violations)
    )


# --- (i) 反解值裸餵 primitive sink 無 marker → 應紅 ---


def test_guard_catches_planted_violation_reversed_value_to_primitive_sink():
    source = (
        "def bad():\n"
        "    fs_path = uri_to_local_fs_path(uri, path_mappings)\n"
        "    path_uri = to_file_uri(fs_path)\n"
        "    repo.get_by_path(path_uri)\n"
    )
    assert _scan_source(source) != []


# --- (ii) 裸本機路徑餵 primitive sink 無 marker → 應紅（對應 scraper.py:180 修前形狀） ---


def test_guard_catches_planted_violation_bare_local_path_to_primitive_sink():
    source = (
        "def bad():\n"
        "    new_filename = organize_file(path)['new_filename']\n"
        "    path_uri = to_file_uri(new_filename)\n"
        "    repo.update_user_tags(path_uri, tags)\n"
    )
    assert _scan_source(source) != []


# --- (iii) 錯命名空間值傳進已登記 wrapper callsite 無 marker → 應紅 ---


def test_guard_catches_planted_violation_wrapper_callsite_wrong_namespace():
    source = (
        "def bad():\n"
        "    fs_path = uri_to_local_fs_path(uri, path_mappings)\n"
        "    _db_upsert(repo, number, fs_path, meta)\n"
    )
    assert _scan_source(source) != []


def test_guard_catches_planted_violation_direct_nesting_primitive_sink():
    source = (
        "def bad():\n"
        "    repo.get_by_path(to_file_uri(fs_path))\n"
    )
    assert _scan_source(source) != []


def test_guard_catches_planted_violation_is_known_cover_path_bare_variable():
    source = (
        "def bad():\n"
        "    repo.is_known_cover_path(cover_fs)\n"
    )
    assert _scan_source(source) != []


def test_guard_catches_planted_violation_asyncio_to_thread_indirect_callsite():
    source = (
        "async def bad():\n"
        "    cover_fs_for_db = compute_something(path)\n"
        "    allowed = await asyncio.to_thread(_check_cover_path, cover_fs_for_db)\n"
    )
    assert _scan_source(source) != []


# --- negative：forward-mapped（帶第二引數）不誤報 ---


def test_guard_forward_mapped_second_arg_not_flagged():
    source = (
        "def ok():\n"
        "    path_uri = to_file_uri(fs_path, path_mappings)\n"
        "    repo.get_by_path(path_uri)\n"
    )
    assert _scan_source(source) == []


def test_guard_forward_mapped_keyword_arg_not_flagged():
    source = (
        "def ok():\n"
        "    path_uri = to_file_uri(fs_path, path_mappings=path_mappings)\n"
        "    repo.get_by_path(path_uri)\n"
    )
    assert _scan_source(source) == []


# --- negative：marker 豁免（呼叫行 / 賦值行兩種慣例） ---


def test_guard_marker_exempts_primitive_sink_same_line():
    source = (
        "def ok():\n"
        "    path_uri = to_file_uri(fs_path_for_db)  # db-ns-ok: reason\n"
        "    repo.get_by_path(path_uri)\n"
    )
    assert _scan_source(source) == []


def test_guard_marker_exempts_primitive_sink_prev_line():
    source = (
        "def ok():\n"
        "    # db-ns-ok: reason\n"
        "    path_uri = to_file_uri(fs_path_for_db)\n"
        "    repo.get_by_path(path_uri)\n"
    )
    assert _scan_source(source) == []


def test_guard_marker_on_assignment_line_exempts_wrapper_callsite():
    """比照 actress.py:525/528 慣例：marker 貼在賦值行，wrapper callsite 在後面幾行。"""
    source = (
        "def ok():\n"
        "    cover_fs_for_db = uri_to_fs_path(path)  # db-ns-ok: reason\n"
        "    asyncio.to_thread(_check_cover_path, cover_fs_for_db)\n"
    )
    assert _scan_source(source) == []


def test_guard_marker_on_callsite_line_exempts_wrapper_direct_call():
    """比照 enricher.py _db_upsert callsite 慣例：marker 貼在呼叫行正上一行。"""
    source = (
        "def ok():\n"
        "    # db-ns-ok: reason\n"
        "    _db_upsert(repo, number, fs_path_for_db, meta)\n"
    )
    assert _scan_source(source) == []


def test_guard_wrapper_body_internal_primitive_sink_not_flagged():
    """wrapper helper 本體內部的 primitive sink 已委派給 callsite（D3），
    不應被獨立當成 primitive-sink violation 列舉（callsite 掃描仍正常運作）。"""
    source = (
        "def _db_upsert(repo, number, fs_path, meta):\n"
        "    path_uri = to_file_uri(fs_path)\n"
        "    repo.get_by_path(path_uri)\n"
    )
    assert _scan_source(source) == []


def test_guard_ignores_non_sink_use():
    source = (
        "def ok():\n"
        "    path_uri = to_file_uri(fs_path)\n"
        "    if path_uri == other:\n"
        "        return path_uri\n"
    )
    assert _scan_source(source) == []


# --- reaching-definition 近似（Fix 1）：sink 之前/之後同名重賦值不應互相干擾 ---


def test_guard_reaching_def_earlier_unmarked_sink_not_hidden_by_later_marked_reassign():
    """較早的真 violation（unmarked sink）不應被較晚同名變數的 marked 重賦值遮蔽
    （false negative 回歸鎖：修前 `_find_assign_lineno_for_name` 取『全函式最後一次賦值』，
    會誤把此處 sink 的賦值行判定成後面那個 marked 重賦值行）。"""
    source = (
        "def bad():\n"
        "    fs_path_for_db = uri_to_local_fs_path(uri, path_mappings)\n"
        "    _db_upsert(repo, number, fs_path_for_db, meta)\n"
        "    fs_path_for_db = other()  # db-ns-ok: unrelated later reassign\n"
    )
    assert _scan_source(source) != []


def test_guard_reaching_def_earlier_marked_assign_not_falsely_flagged_by_later_unmarked_reassign():
    """較早的合法賦值（marked）供較早的 sink 使用，不應被較晚同名變數的 unmarked 重賦值
    拖累而誤報（false positive 回歸鎖：修前取『全函式最後一次賦值』會誤把 sink 對應到
    後面那個沒有 marker 的重賦值行）。"""
    source = (
        "def ok():\n"
        "    fs_path_for_db = uri_to_local_fs_path(uri, path_mappings)  # db-ns-ok: mapped\n"
        "    _db_upsert(repo, number, fs_path_for_db, meta)\n"
        "    fs_path_for_db = other()\n"
    )
    assert _scan_source(source) == []


# --- wrapper callsite keyword 傳參（Fix 2）：位置引數之外也要支援 keyword ---


def test_guard_catches_planted_violation_wrapper_direct_call_keyword_arg():
    source = (
        "def bad():\n"
        "    bad_var = uri_to_local_fs_path(uri, path_mappings)\n"
        "    _db_upsert(repo, number, fs_path=bad_var, meta=meta)\n"
    )
    assert _scan_source(source) != []


def test_guard_catches_planted_violation_asyncio_to_thread_keyword_arg():
    source = (
        "async def bad():\n"
        "    bad_var = uri_to_local_fs_path(uri, path_mappings)\n"
        "    allowed = await asyncio.to_thread(_check_cover_path, fs_path=bad_var)\n"
    )
    assert _scan_source(source) != []


def test_guard_wrapper_direct_call_keyword_arg_marker_exempts():
    source = (
        "def ok():\n"
        "    # db-ns-ok: reason\n"
        "    _db_upsert(repo, number, fs_path=fs_path_for_db, meta=meta)\n"
    )
    assert _scan_source(source) == []


def test_guard_asyncio_to_thread_keyword_arg_marker_exempts():
    source = (
        "async def ok():\n"
        "    # db-ns-ok: reason\n"
        "    allowed = await asyncio.to_thread(_check_cover_path, fs_path=fs_path_for_db)\n"
    )
    assert _scan_source(source) == []
