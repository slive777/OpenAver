"""本機判斷必須委派 `_is_loopback_host()` —— AST 源碼語意守衛（TASK-114a-T6-a）。

# [lint-guard: pytest-justified] Python-AST 源碼語意守衛（loopback 字面／屬性）
# 斷言 core/** + web/** 不得再長出「allow-direction 的 client 本機判斷」
# （字面值 Compare 或 .is_loopback Attribute）。字串指紋 lint 抓不到
# 「Compare 運算元是否為 loopback 字面容器」這類 AST 語意，故留 pytest。

## 兩個方向相反的問題（Opus 裁決）

| | 問的是什麼 | 判 true 的後果 |
|---|---|---|
| **A. 存取決策**（本守衛要守）| 連進來的 **client** 是不是本機 | **放行** |
| **B. 目標封鎖**（不在範圍，但形狀相同）| 要去連的 **target** 是不是本機／內網 | **拒絕** |

B 類殘留（SSRF / CDN 白名單）進**具名帳本**，不是整檔排除——未來若在
同檔新增 allow-direction client 判斷仍會紅。

## 帳本契約

- 鍵是**精確身分**（檔案 + 作用域 + 形狀），不是裸名字。
- 理由必須標明回答的是 A（allow-direction / client）還是 B（deny-direction / target）。
- 帳本只准減不准增：每條必須仍對應真實原始碼，否則 anti-rot 紅。
"""
from __future__ import annotations

import ast
import pathlib
from dataclasses import dataclass

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

_LOOPBACK_LITERALS = frozenset({
    "127.0.0.1",
    "::1",
    "localhost",
    "::ffff:127.0.0.1",
})

_COMPARE_OPS = (ast.Eq, ast.NotEq, ast.In, ast.NotIn)

SCAN_ROOTS = ("core", "web")

# ---------------------------------------------------------------------------
# 具名帳本（binding-qualified / shape-qualified）
# ---------------------------------------------------------------------------
# 鍵 = `相對路徑:作用域:形狀`。三段缺一不可（同 metatube 守衛 round-5 教訓）。
# 形狀 ∈ {
#   function_body          — 整支函式體豁免（僅 _is_loopback_host）
#   assignment_frozenset   — 模組層 _LOOPBACK_HOSTS = frozenset({...})
#   literal                — Compare + loopback 字面（容量 1，同 scope 第二條紅）
#   is_loopback_attr       — .is_loopback Attribute（容量 1）
# }


@dataclass(frozen=True)
class LedgerEntry:
    """一條具名豁免。identity ＝ file:scope:shape。"""

    rel: str
    scope: str          # 函式名，或 "<module>"
    shape: str          # 見上
    reason: str         # 必須標 allow-direction 或 deny-direction


def _identity(entry: LedgerEntry) -> str:
    return f"{entry.rel}:{entry.scope}:{entry.shape}"


# 帳本只准減不准增。加一條要在 PR diff 上被看見。
LEDGER: tuple[LedgerEntry, ...] = (
    LedgerEntry(
        rel="web/app.py",
        scope="_is_loopback_host",
        shape="function_body",
        reason=(
            "allow-direction（client）：本機 client 判斷的**單一所有者**；"
            "函式體內任何本機字面／.is_loopback 都是它的本職（Opus 裁決 §1）。"
        ),
    ),
    LedgerEntry(
        rel="web/app.py",
        scope="<module>",
        shape="assignment_frozenset",
        reason=(
            "allow-direction（client）：`_LOOPBACK_HOSTS = frozenset({...})` 模組層 "
            "assignment（middleware 短路名單）。形狀是 assignment 不是 Compare——"
            "帳本綁 assignment 形狀，不用哨兵座標硬塞 Compare 帳本（Opus 裁決 §3）。"
            "plan §1.4 / CD-114a-5 明文不動它。"
        ),
    ),
    LedgerEntry(
        rel="web/routers/config.py",
        scope="update_general_field",
        shape="literal",
        reason=(
            "allow-direction（client）residual：`_client_host not in "
            "(\"127.0.0.1\", \"::1\")`，update_general_field 內手寫 tuple——"
            "不認 ::ffff:127.0.0.1。plan §1.4 明文不動但盯著（Opus 裁決 §4）。"
        ),
    ),
    LedgerEntry(
        rel="core/metatube/validation.py",
        scope="_classify_ip",
        shape="is_loopback_attr",
        reason=(
            "deny-direction（target）：判的是要連的 target IP 不是 client；"
            "判 true 是擋掉（SSRF）不是放行。不在 T6-a 語意範圍（Opus 裁決 §2）。"
        ),
    ),
    LedgerEntry(
        rel="core/metatube/validation.py",
        scope="validate_metatube_url",
        shape="literal",
        reason=(
            "deny-direction（target）：判的是 URL host 是不是 localhost 別名，"
            "判 true 是擋掉（SSRF）不是放行。不在 T6-a 語意範圍（Opus 裁決 §2）。"
        ),
    ),
    LedgerEntry(
        rel="core/image_host_policy.py",
        scope="_is_public_http_target",
        shape="literal",
        reason=(
            "deny-direction（target）：判的是圖片／CDN 目標 host 是不是 localhost，"
            "判 true 是擋掉（非公開位址）不是放行。不在 T6-a 語意範圍（Opus 裁決 §2）。"
        ),
    ),
    LedgerEntry(
        rel="core/custom_source/guard.py",
        scope="_blocked_name",
        shape="literal",
        reason=(
            "deny-direction（target）：自訂來源 SSRF 位址守衛，判的是要連的 host 是不是 "
            "localhost 別名，判 true 是擋掉不是放行。不在 T6-a 語意範圍。"
        ),
    ),
    LedgerEntry(
        rel="core/custom_source/schema.py",
        scope="_static_host",
        shape="literal",
        reason=(
            "deny-direction（target）：自訂來源載入期靜態 host 檢查，判的是 URL host 是不是 "
            "localhost 別名，判 true 是拒載不是放行。不在 T6-a 語意範圍。"
        ),
    ),
)

LEDGER_BY_ID: dict[str, LedgerEntry] = {_identity(e): e for e in LEDGER}

# (rel, scope, shape) → capacity。function_body 無限；其餘每條容量 1。
_CAPACITY: dict[tuple[str, str, str], int | None] = {}
for _e in LEDGER:
    key = (_e.rel, _e.scope, _e.shape)
    if _e.shape == "function_body":
        _CAPACITY[key] = None  # unlimited
    elif _e.shape == "assignment_frozenset":
        # 不消費 raw hit（assignment 不是 Compare／Attribute 命中）
        _CAPACITY[key] = 0
    else:
        _CAPACITY[key] = 1


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _operand_loopback_literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if node.value in _LOOPBACK_LITERALS:
            return node.value
        return None
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        for elt in node.elts:
            if (
                isinstance(elt, ast.Constant)
                and isinstance(elt.value, str)
                and elt.value in _LOOPBACK_LITERALS
            ):
                return elt.value
    return None


def _enclosing_function(tree: ast.AST, target: ast.AST) -> str | None:
    """最內層 FunctionDef/AsyncFunctionDef 名；模組層 → None。"""

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack: list[str] = []
            self.found: str | None = None

        def visit_FunctionDef(self, node: ast.FunctionDef):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def generic_visit(self, node: ast.AST):
            if node is target:
                self.found = self.stack[-1] if self.stack else None
                return
            super().generic_visit(node)

    v = Visitor()
    v.visit(tree)
    return v.found


def _raw_hits(
    path: pathlib.Path,
) -> list[tuple[int, int, str, str, str | None]]:
    """(lineno, col_offset, kind, detail, enclosing_func_or_None)。"""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    hits: list[tuple[int, int, str, str, str | None]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(
            isinstance(op, _COMPARE_OPS) for op in node.ops
        ):
            operands = [node.left] + list(node.comparators)
            for opd in operands:
                lit = _operand_loopback_literal(opd)
                if lit is not None:
                    hits.append((
                        node.lineno,
                        node.col_offset,
                        "literal",
                        lit,
                        _enclosing_function(tree, node),
                    ))
                    break

        if isinstance(node, ast.Attribute) and node.attr == "is_loopback":
            hits.append((
                node.lineno,
                node.col_offset,
                "is_loopback_attr",
                "is_loopback",
                _enclosing_function(tree, node),
            ))

    return hits


def _find_loopback_hosts_assignment(tree: ast.Module) -> ast.Assign | None:
    """模組層 `_LOOPBACK_HOSTS = frozenset({...含 loopback 字面...})`。"""
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if not (isinstance(tgt, ast.Name) and tgt.id == "_LOOPBACK_HOSTS"):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        if not (
            isinstance(node.value.func, ast.Name)
            and node.value.func.id == "frozenset"
        ):
            continue
        if not node.value.args:
            continue
        arg0 = node.value.args[0]
        if not isinstance(arg0, (ast.Set, ast.List, ast.Tuple)):
            continue
        lits = {
            elt.value
            for elt in arg0.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        }
        if lits & _LOOPBACK_LITERALS:
            return node
    return None


def _violations(
    path: pathlib.Path, rel: str | None = None
) -> list[tuple[int, int, str, str]]:
    """回傳帳本未吸收的違規：(lineno, col_offset, kind, detail)。"""
    if rel is None:
        try:
            rel = path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = "<synthetic>"

    # 每檔独立的容量計數（同 scope+shape 跨檔不會混）
    used: dict[tuple[str, str, str], int] = {}

    out: list[tuple[int, int, str, str]] = []
    for lineno, col, kind, detail, scope in _raw_hits(path):
        scope_key = scope if scope is not None else "<module>"

        # 1) function_body 整支豁免（_is_loopback_host）
        body_key = (rel, scope_key, "function_body")
        if body_key in _CAPACITY and _CAPACITY[body_key] is None:
            continue

        # 2) 精確 (rel, scope, kind) 帳本，容量 1
        hit_key = (rel, scope_key, kind)
        cap = _CAPACITY.get(hit_key)
        if cap is not None and cap > 0:
            n = used.get(hit_key, 0)
            if n < cap:
                used[hit_key] = n + 1
                continue
            # 容量用盡 → 同 scope 第二條同形狀 = 新違規

        out.append((lineno, col, kind, detail))
    return out


def _iter_scanned_files():
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            yield path


# ---------------------------------------------------------------------------
# Production scan
# ---------------------------------------------------------------------------

def test_no_new_handwritten_loopback_judgments():
    """core/** + web/** 不得出現帳本以外的手寫 loopback 判斷。

    紅了 = 新的 allow-direction client 判斷（應改委派 `_is_loopback_host`），
    或同 scope 多出一條未入帳的形狀（含 deny-direction 檔內的新 client 判斷）。
    """
    all_hits: list[str] = []
    for path in _iter_scanned_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, col, kind, detail in _violations(path, rel=rel):
            all_hits.append(f"{rel}:{lineno}:{col} [{kind}] {detail}")
    assert all_hits == [], (
        f"新增手寫 loopback 判斷（{len(all_hits)} 處）：\n"
        + "\n".join(all_hits)
        + "\n→ allow-direction client 判斷必須委派 web.app._is_loopback_host()"
        "（CD-114a-5）；deny-direction 新殘留須具名入帳並標明方向。"
    )


# ---------------------------------------------------------------------------
# Anti-rot：帳本每條都必須仍對應真實原始碼（只准減不准增）
# ---------------------------------------------------------------------------

def _ledger_entry_exists(entry: LedgerEntry) -> tuple[bool, str]:
    """回傳 (exists, diagnostic)。"""
    path = REPO_ROOT / entry.rel
    if not path.is_file():
        return False, f"檔案不存在：{entry.rel}"

    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:
        return False, f"無法 parse {entry.rel}: {exc}"

    if entry.shape == "assignment_frozenset":
        if entry.scope != "<module>":
            return False, "assignment_frozenset 必須 scope=<module>"
        node = _find_loopback_hosts_assignment(tree)  # type: ignore[arg-type]
        if node is None:
            return False, f"{entry.rel} 找不到 _LOOPBACK_HOSTS = frozenset({{...}})"
        return True, f"assignment at {node.lineno}"

    if entry.shape == "function_body":
        for node in tree.body if isinstance(tree, ast.Module) else []:
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == entry.scope
            ):
                return True, f"function {entry.scope} at {node.lineno}"
        return False, f"{entry.rel} 找不到函式 {entry.scope!r}"

    # literal / is_loopback_attr：在指定 scope 內至少一處 raw hit
    raw = _raw_hits(path)
    matches = [
        h for h in raw
        if h[2] == entry.shape and (h[4] or "<module>") == entry.scope
    ]
    if not matches:
        return False, (
            f"{entry.rel}:{entry.scope}:{entry.shape} 在原始碼中找不到對應命中；"
            f"該檔 raw hits: {[(h[0], h[2], h[4]) for h in raw]}"
        )
    return True, f"{len(matches)} hit(s) e.g. line {matches[0][0]}"


def test_ledger_entries_all_still_present():
    """帳本反腐（Opus 裁決 §5）：每條必須仍存在於原始碼。

    刪了碼但帳本留著 → 永久免死金牌。這支測試逼人回來刪帳本條目。
    帳本只准減不准增——加條目是 PR 上可見的 deliberate 動作。
    """
    dead: list[str] = []
    for entry in LEDGER:
        ok, diag = _ledger_entry_exists(entry)
        if not ok:
            dead.append(f"{_identity(entry)} — {diag}")
    assert dead == [], (
        f"LEDGER 有 {len(dead)} 條死條目（原始碼已無對應）：\n"
        + "\n".join(dead)
        + "\n→ 刪除帳本條目（只准減不准增），不要留指向空氣的豁免。"
    )


def test_ledger_reasons_state_direction():
    """每條理由必須標明 allow-direction 或 deny-direction（誠實帳本）。"""
    bad = [
        _identity(e)
        for e in LEDGER
        if "allow-direction" not in e.reason and "deny-direction" not in e.reason
    ]
    assert bad == [], f"帳本理由未標方向：{bad}"


def test_ledger_identities_are_unique():
    ids = [_identity(e) for e in LEDGER]
    assert len(ids) == len(set(ids)), f"帳本身分重複：{ids}"


# ---------------------------------------------------------------------------
# RED / GREEN 合成片段
# ---------------------------------------------------------------------------

_RED_SNIPPETS = [
    (
        "in_tuple_literal",
        'def f(host):\n    return host in ("127.0.0.1", "::1", "localhost")\n',
    ),
    (
        "eq_127",
        'def f(host):\n    return host == "127.0.0.1"\n',
    ),
    (
        "not_in_list",
        'def f(h):\n    if h not in ["::1"]:\n        pass\n',
    ),
    (
        "is_loopback_attr",
        "import ipaddress\n"
        "def f(h):\n"
        "    return ipaddress.ip_address(h).is_loopback\n",
    ),
    (
        "ne_localhost",
        'def f(host):\n    return host != "localhost"\n',
    ),
]

_GREEN_SNIPPETS = [
    (
        "name_ref_to_set",
        "def f(host):\n    return host in _LOOPBACK_HOSTS\n",
    ),
    (
        "delegate_call",
        "def f(host):\n    return _is_loopback_host(host)\n",
    ),
    (
        "unrelated_string_compare",
        'def f(host):\n    return host == "example.com"\n',
    ),
    (
        "is_global_not_loopback",
        "def f(addr):\n    return addr.is_global\n",
    ),
]


@pytest.mark.parametrize(
    "label,src", _RED_SNIPPETS, ids=[s[0] for s in _RED_SNIPPETS]
)
def test_guard_flags_handwritten_loopback(label, src, tmp_path):
    f = tmp_path / "m.py"
    f.write_text(src, encoding="utf-8")
    assert _violations(f), f"{label}：應紅卻沒抓到\n{src}"


@pytest.mark.parametrize(
    "label,src", _GREEN_SNIPPETS, ids=[s[0] for s in _GREEN_SNIPPETS]
)
def test_guard_does_not_overreach(label, src, tmp_path):
    f = tmp_path / "m.py"
    f.write_text(src, encoding="utf-8")
    assert _violations(f) == [], f"{label}：誤報 {_violations(f)}\n{src}"


def test_second_literal_in_ledgered_scope_is_not_absorbed(tmp_path):
    """帳本容量 1：deny-direction 檔的 scope 內再加一條 literal → 仍紅。

    這就是「不整檔排除」的價值——新的 client 判斷（或第二條殘留）不會被洗白。
    """
    # 模擬 validate_metatube_url 已有一條 localhost（帳本吸收），再加 127.0.0.1
    src = (
        "def validate_metatube_url(host):\n"
        '    if host == "localhost":\n'
        "        return True\n"
        '    if host == "127.0.0.1":\n'
        "        return True\n"
    )
    f = tmp_path / "m.py"
    f.write_text(src, encoding="utf-8")
    # 合成片段 rel 預設 <synthetic> → 帳本不命中 → 兩條都紅
    hits = _violations(f)
    assert len(hits) >= 2, f"合成無帳本時應兩條都紅：{hits}"

    # 掛上真實 rel 後：第一條被帳本吸收，第二條必須仍紅
    hits_with_rel = _violations(f, rel="core/metatube/validation.py")
    assert len(hits_with_rel) == 1, (
        f"帳本容量 1：應恰好剩一條未吸收，得到 {hits_with_rel}"
    )
    assert hits_with_rel[0][0] == 4, (
        f"未吸收的應是第二條（line 4 的 127.0.0.1），得到 {hits_with_rel}"
    )
