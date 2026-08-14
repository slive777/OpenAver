#!/usr/bin/env python3
"""Function-size gate: fail CI if any first-party function exceeds MAX_LINES.

Why this guard exists (spec-110a §2.3, CD-110a-3, CD-110a-4):
    OpenAver has a standing backlog of oversized functions (some genuinely
    hard to split — e.g. a single SQL-schema init sweep or a Win32 message
    loop — some just embedded CSS/JS string literals). Rather than relying on
    self-discipline ("please don't add another 300-line function"), this
    script makes the rule mechanical: any function whose measured body
    (``end_lineno - lineno + 1``) exceeds ``MAX_LINES`` is a violation UNLESS
    it appears in ``EXEMPTIONS`` below, with a written reason.

    The exemption list intentionally lives HERE, inside this script, and NOT
    as inline ``# noqa``-style comments scattered across the 14 offending
    files (BE-ENV-03, plan §"本 plan 適用陷阱"): those files are frequently
    edited for unrelated reasons, and any future line-ending fixup
    (``sed -i`` style batch edits risk CRLF/LF whole-file churn on Windows
    checkouts) could accidentally add/remove an exemption comment along the
    way. Centralizing the list in one Python dict, reviewed via normal git
    diff, is the only place a change to "which functions are allowed to be
    huge" can be seen and challenged in review.

    A whitelist that "only ever grows" is not a discipline, it's a formality.
    So this script also runs an anti-rot ("反腐") check on every run
    (CD-110a-4): each EXEMPTIONS entry must correspond to a function that
    (a) still exists under that exact (file, qualified_name) key, and
    (b) is still actually over MAX_LINES. An entry that no longer matches
    either condition means the exemption is stale — leaving it in place
    would make the list "only grow", never shrink, defeating the entire
    point of a governed exemption list. Both failure modes hard-fail the
    run (see _GHOST/_STALE below) and must be fixed by deleting the entry,
    not editing the number.

    Codex PR #122 P2-1: the two checks above did NOT stop an *already*
    exempt function from growing without limit — the anti-rot check only
    rejects a GHOST (missing) or STALE (dropped to <= MAX_LINES) entry, so
    an exempt function could balloon from 351 to 359 lines (as happened to
    ``organize_file`` in this very branch's T4) and every run would still
    print PASS. So each EXEMPTIONS value now also carries a `baseline`: the
    function's measured size at the moment it was grandfathered in. A THIRD
    check enforces `size <= baseline` for every exempt function on every
    run (see "EXEMPTION BASELINE EXCEEDED" below) — an exemption freezes a
    function at its current size, it does not licence unlimited future
    growth. Shrinking below baseline is always fine (that just makes the
    STALE check fire sooner, once it crosses MAX_LINES).

    Known, accepted gap (not fixed here — do not build a signature/hash
    mechanism for it, see plan-110a CD-110a-3 ②): a *newly* oversized
    function can still be added straight into EXEMPTIONS with a baseline
    at whatever size it already is, immediately bypassing MAX_LINES. This
    is not mechanically closeable without also policing "why was this
    entry added" (a judgment call, not a measurement) — the mitigation is
    social/procedural: adding an EXEMPTIONS entry requires touching this
    file, which is a visible, single-purpose diff line any reviewer (human
    or Codex) can challenge on its own. What baseline DOES close off is the
    much quieter failure mode: an *already*-exempt function silently
    growing further without anyone having to touch this file at all.

Usage:
    python scripts/py_function_size_lint.py

Exit codes:
    0 — no new violations, no stale/ghost exemptions, no parse errors.
    1 — at least one violation, stale exemption, ghost exemption, parse
        error, or a false-green condition (zero .py files scanned).
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

# Repo root resolved from this file's location, NOT from CWD — the scan
# roots and every EXEMPTIONS key (relative paths) must be stable regardless
# of where this script is invoked from (CI working directory vs a
# developer's shell sitting in an arbitrary subdirectory).
ROOT = Path(__file__).resolve().parent.parent

MAX_LINES = 200

# Scanned relative to ROOT. Mix of directories and single top-level files.
SCAN_ROOTS = ["core", "web", "windows", "scripts", "build.py", "build_macos.py"]

# Directory names excluded anywhere in the walked tree (matched against
# each path *segment*, not a prefix string — so a nested tests/ dir is
# still excluded, e.g. core/tests/ or web/tests/).
EXCLUDED_DIRS = {"tests", "venv", "tools", "__pycache__", ".git"}

# EXEMPTIONS: dict[(relative_path, qualified_name)] -> (baseline, reason).
#
# qualified_name convention: '.'-joined stack of every enclosing
# FunctionDef/AsyncFunctionDef/ClassDef name (class scopes ARE pushed onto
# the stack), e.g. "HTMLGenerator._get_css" for a method, or
# "batch_enrich_endpoint.event_generator" for a nested function. A bare
# module-level function (no enclosing class/function) has no prefix, e.g.
# "main". This avoids key collisions between same-named methods on
# different classes, at the cost of not matching the shorthand names used
# in prose/spec tables (which is why the table below documents both).
#
# `baseline` (Codex PR #122 P2-1): the function's measured size
# (end_lineno - lineno + 1) at the moment this entry was grandfathered in
# (all 14 baselines below were captured by actually running this script
# against the repo at HEAD of feature/110-governance-and-security on
# 2026-08-02 — see the "size > baseline" check in main() for what this
# enforces). This is a ratchet, not a target: an exempt function is allowed
# to sit at or shrink below its baseline forever, but growing past it is a
# violation just like exceeding MAX_LINES is for a non-exempt function.
# Bumping a baseline UP is a real, reviewable decision (it means "this
# function is allowed to be even bigger than it already was") and must be
# accompanied by an updated reason string explaining why — never bump the
# number silently to make CI green again.
#
# 14 entries, reasons transcribed verbatim from spec-110a §2.3 /
# TASK-110a-T2 (Codex plan review P1-1 already settled these; not
# re-litigated per task):
EXEMPTIONS: dict[tuple[str, str], tuple[int, str]] = {
    ("core/gallery_generator.py", "HTMLGenerator._get_css"): (
        1039,
        "純 CSS 字面值（AST 上是單一 return '''...''' 語句），拆函式只是把同一坨字串搬到"
        "另一個 Python 函式，不會降低任何複雜度；正解是抽成靜態 .css 檔由前端載入，而非拆函式。",
    ),
    ("core/gallery_generator.py", "HTMLGenerator._get_javascript"): (
        604,
        "同上，純 JS 字面值；正解是抽成靜態 .js 檔由前端載入，而非拆函式。",
    ),
    ("web/routers/scanner.py", "generate_avlist"): (
        500,
        "avlist SSE 生成主流程；109 已判定為「列 backlog、現在別搬」（60–100 處測試 patch "
        "target 焊死該函式，拆分成本由測試面而非邏輯面決定，與既有 C901 noqa 理由一致）。",
    ),
    ("core/organizer.py", "organize_file"): (
        359,
        "整理主流程；Phase 2（110b）會在其中加 containment 防線，加的是「呼叫一個新的小函式」，"
        "不得讓本函式本身更複雜（見 plan-110b，與既有 C901 noqa 理由一致）。",
    ),
    ("core/config.py", "_load_config_unlocked"): (
        304,
        "config 遷移主流程，每加一個設定欄位都得改它；收斂設計已列 backlog"
        "（OpenAver架構評估-回應.md §七）。",
    ),
    ("web/routers/scraper.py", "batch_enrich_endpoint"): (
        279,
        "批次 enrich SSE 端點主流程（含 90c-T1 唯讀 guard 的 async-safe 前置計算 + 去重 + SSE "
        "response 組裝），本體大部分行數其實是巢狀的 event_generator（見下一條）；縮小 "
        "event_generator 會連帶縮小這條，目前不獨立拆分是避免把單一 request 生命週期的狀態"
        "（去重清單、唯讀前綴集）打散到多個函式增加傳遞開銷。",
    ),
    ("web/routers/scraper.py", "batch_enrich_endpoint.event_generator"): (
        250,
        "SSE 逐筆處理迴圈：per-item try/except、開始/進度/結束通知 emit、success/failed 計數，"
        "這是單一 SSE session 的完整生命週期；拆分會把 success_count/failed_count/去重後清單"
        "等跨語句共享狀態打散到多個函式，可讀性不會變好。",
    ),
    ("core/enricher.py", "enrich_single"): (
        249,
        "單片 enrich 主流程，含多個 write_* flag（nfo/cover/extrafanart/overwrite_existing/"
        "external_manager）的正交組合分支，是核心編排函式；已標記 ranker-invalidate-ok，flag "
        "組合邏輯搬到別處會打散單一事務語意。",
    ),
    ("core/database/video.py", "VideoRepository.repath"): (
        230,
        "docstring 已明列四個互斥分支（self-no-op／正常 UPDATE／碰撞 delete-merge／"
        "old-not-in-DB），拆分會打散同一顆 SQL 語意單元到多個函式，可讀性不會變好"
        "（與既有 C901 noqa 理由一致）。",
    ),
    ("windows/tray.py", "NativeTrayIcon._run_windows"): (
        223,
        "Windows tray icon 的 Win32 message loop，直接呼叫 ctypes.windll.user32/shell32，是"
        "單一 OS-level event loop 狀態機；拆分會把 win32 handle 的生命週期打散到多個函式，"
        "難以追蹤資源釋放順序。",
    ),
    ("core/readonly_producer.py", "_write_movie_assets"): (
        218,
        "109 剛落地的唯讀單片產出主流程，寫入 nfo/cover/poster/fanart 等多個資產，需要維持"
        "同一次 I/O 序列的可推理性（部分失敗時的處置順序）；剛穩定，暫不再拆避免二次擾動。",
    ),
    ("build.py", "download_and_install_packages"): (
        204,
        "Windows wheel 兩階段下載 + manifest-based extract 是同一次 build 的單一狀態機"
        "（Phase 1／Phase 2／機制 3 manifest-based extract），拆分會讓 phase 之間的隱含依賴"
        "（cache/manifest）更難追蹤，非本 Phase 治理範圍（build 工具鏈，與既有 C901 noqa "
        "理由一致）。",
    ),
    ("core/database/connection.py", "init_db"): (
        203,
        "資料庫 schema 初始化主流程，逐表 CREATE TABLE/CREATE INDEX 語句序列，schema 仍在"
        "演進中；拆成多個小函式不會降低本質複雜度，只會增加呼叫層次與跨函式的 cursor/conn "
        "傳遞。",
    ),
}


class _FunctionRecord:
    """One discovered FunctionDef/AsyncFunctionDef, with its measured size."""

    __slots__ = ("rel_path", "qualname", "lineno", "end_lineno", "size")

    def __init__(self, rel_path: str, qualname: str, lineno: int, end_lineno: int) -> None:
        self.rel_path = rel_path
        self.qualname = qualname
        self.lineno = lineno
        self.end_lineno = end_lineno
        self.size = end_lineno - lineno + 1


class _QualnameVisitor(ast.NodeVisitor):
    """Walks every statement body (not just direct AST children) collecting
    FunctionDef/AsyncFunctionDef nodes with a '.'-joined qualname built from
    the enclosing Function/AsyncFunction/Class scope stack.

    Using ast.NodeVisitor + generic_visit (rather than only
    ast.iter_child_nodes on the module) is deliberate: functions nested
    inside if/try/with/for blocks are still real functions and must not be
    invisible to the size gate just because they're not a direct child of
    the enclosing scope.
    """

    def __init__(self, rel_path: str, records: list[_FunctionRecord]) -> None:
        self._rel_path = rel_path
        self._records = records
        self._stack: list[str] = []

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._stack.append(node.name)
        qualname = ".".join(self._stack)
        # end_lineno is always set for a successfully ast.parse()'d module
        # (only None for nodes synthesized without location info, which does
        # not apply here). Raise explicitly rather than assert: `python -O`
        # strips asserts, and a guard script that silently degrades into a
        # TypeError under -O is worse than one that says what went wrong.
        if node.end_lineno is None:
            raise RuntimeError(
                f"{self._rel_path}:{node.lineno} {qualname} has no end_lineno "
                "— cannot measure function size"
            )
        self._records.append(
            _FunctionRecord(self._rel_path, qualname, node.lineno, node.end_lineno)
        )
        self.generic_visit(node)
        self._stack.pop()

    # The visit_* CamelCase names below are dictated by the ast.NodeVisitor
    # dispatch API, not by our own naming choice. They deliberately carry no
    # suppression comment: pep8-naming (N8xx) is not in pyproject.toml's
    # `select`, and this branch's whole thesis is that every suppression must
    # be named AND necessary — one for a rule that isn't enabled is neither.
    # (Do not write the literal directive token in prose here: ruff parses it
    # anywhere in a comment and reports an invalid-directive warning.)
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Class scopes are pushed onto the qualname stack too (task-mandated
        # convention — see EXEMPTIONS docstring above), so that a method's
        # qualname is "ClassName.method_name", not just "method_name" (which
        # would collide across classes).
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()


def _iter_py_files() -> tuple[list[Path], list[str]]:
    """Walk SCAN_ROOTS under ROOT, excluding EXCLUDED_DIRS.

    Returns (files, root_errors). `root_errors` is non-empty when a declared
    scan root is missing or is the wrong kind of thing.

    Every entry in SCAN_ROOTS MUST exist and match its declared shape
    (``*.py`` entries are single files, everything else is a directory).
    A missing root is a hard error, never a silent skip: if `core/` were
    renamed or a build entry moved, silently walking the remaining roots
    would still report PASS while the gate had quietly stopped covering the
    range it claims to cover. The `not all_files` false-green guard in
    main() does NOT catch this — it only fires when *every* root vanishes.
    (Nor can we rely on the anti-rot check catching it: that only fires when
    the vanished root happens to contain EXEMPTIONS entries, which is luck,
    not a guarantee — and the blind spot migrates as the list shrinks.)

    Symlinks are not followed (os.walk default followlinks=False, left
    unset deliberately) to avoid infinite recursion / cross-directory
    double-counting. A symlink that itself points at a single .py file (not
    a directory) would still be listed in `filenames` and scanned as a
    normal file by os.walk — none of the current first-party scan roots
    contain such a case, so this is not specially handled; if one is ever
    introduced, add an os.path.realpath()-based dedupe.
    """
    files: list[Path] = []
    root_errors: list[str] = []
    for root_entry in SCAN_ROOTS:
        root_path = ROOT / root_entry
        if root_entry.endswith(".py"):
            if not root_path.is_file():
                root_errors.append(
                    f"[MISSING SCAN ROOT] {root_entry} 不存在或不是檔案（預期為單檔掃描根）。"
                    " 掃描範圍已與 SCAN_ROOTS 宣稱的不符——請修正路徑，或在確認該範圍不再需要"
                    " 涵蓋後從 SCAN_ROOTS 移除該項。"
                )
            else:
                files.append(root_path)
            continue
        if not root_path.is_dir():
            root_errors.append(
                f"[MISSING SCAN ROOT] {root_entry}/ 不存在或不是目錄（預期為目錄掃描根）。"
                " 掃描範圍已與 SCAN_ROOTS 宣稱的不符——請修正路徑，或在確認該範圍不再需要"
                " 涵蓋後從 SCAN_ROOTS 移除該項。"
            )
            continue
        for dirpath, dirnames, filenames in os.walk(root_path):
            # In-place filter of dirnames so os.walk never descends into
            # excluded directories at any depth (not a post-hoc string
            # filter on the resulting path, which would miss nested
            # tests/ subdirectories per task instruction).
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
            for name in filenames:
                if name.endswith(".py"):
                    files.append(Path(dirpath) / name)
    return files, root_errors


def _scan(files: list[Path]) -> tuple[list[_FunctionRecord], list[tuple[str, str]]]:
    """Return (records, parse_errors). parse_errors is [(rel_path, message)].

    Takes the file list as a parameter rather than walking again, so the
    false-green guard in main() and the scan itself are provably looking at
    the same set of files (one os.walk, one source of truth).
    """
    records: list[_FunctionRecord] = []
    parse_errors: list[tuple[str, str]] = []
    for path in files:
        rel_path = path.relative_to(ROOT).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel_path)
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
            # Fail-closed: a .py file in our own first-party tree that
            # fails to parse must not be silently skipped — that would make
            # the size gate blind to whatever is in it (see card "邊界條件 1").
            # UnicodeDecodeError (non-UTF-8 source) and ValueError (e.g. source
            # containing a null byte) are caught alongside SyntaxError so every
            # unreadable file reports through the same [PARSE ERROR] channel
            # instead of crashing out with a raw traceback.
            parse_errors.append((rel_path, f"{type(exc).__name__}: {exc}"))
            continue
        visitor = _QualnameVisitor(rel_path, records)
        visitor.visit(tree)
    return records, parse_errors


def main() -> int:
    # False-green guard: if the walk found zero .py files at all (scan
    # roots misconfigured / repo layout changed / invoked from the wrong
    # place), that must NOT be reported as "no violations" == PASS. We
    # count actual files walked, not just files with functions, so an
    # edge case of "found files but they're all empty" still counts
    # correctly below.
    all_files, root_errors = _iter_py_files()
    if root_errors:
        # Fail before scanning: a shrunken scan range makes every downstream
        # number (function count, violations, anti-rot verdicts) a statement
        # about a smaller repo than the one we claim to be gating.
        for msg in sorted(root_errors):
            print(msg)
        print(f"FAIL: {len(root_errors)} missing scan roots")
        return 1

    if not all_files:
        print(
            "[FAIL] 0 .py files scanned under "
            f"{', '.join(SCAN_ROOTS)} — scan roots misconfigured? (false-green guard)"
        )
        return 1

    records, parse_errors = _scan(all_files)
    total_functions = len(records)
    print(f"[INFO] repo root: {ROOT}")
    print(f"[INFO] scanned {len(all_files)} .py files, {total_functions} functions")
    print(f"[INFO] threshold MAX_LINES = {MAX_LINES} (violation iff size > {MAX_LINES})")
    print(f"[INFO] EXEMPTIONS: {len(EXEMPTIONS)} entries")

    # Group records by key to detect duplicate (path, qualname) definitions
    # (e.g. two functions with the same name in an if/else at module scope).
    by_key: dict[tuple[str, str], list[_FunctionRecord]] = {}
    for rec in records:
        by_key.setdefault((rec.rel_path, rec.qualname), []).append(rec)

    violations: list[tuple[str, int, str, int]] = []  # (rel_path, lineno, qualname, size)
    # (rel_path, lineno, qualname, size, baseline) — exempt function grew past
    # its grandfathered baseline (Codex PR #122 P2-1, see EXEMPTIONS docstring).
    baseline_violations: list[tuple[str, int, str, int, int]] = []
    duplicate_errors: list[tuple[str, str, str]] = []  # (rel_path, qualname, message)
    # Sort by key (rel_path, qualname) before iterating: by_key is built in
    # os.walk traversal order, which is not guaranteed stable across
    # machines/filesystems. Every printed line (duplicates here, violations
    # and anti-rot errors below) must be deterministic regardless of scan
    # order, so CI output doesn't flap between runs.
    for key in sorted(by_key):
        rel_path, qualname = key
        recs = by_key[key]
        if len(recs) > 1:
            # Fail-closed on an ambiguous key. This used to be a warning that
            # then applied one exemption to ALL same-named definitions, which
            # was a straight bypass: adding a second 300-line `organize_file`
            # to a module that already has `organize_file` exempted inherited
            # the exemption and reported PASS. Both anti-rot checks were blind
            # to it too — GHOST needs the key to be absent, and STALE requires
            # *every* record under the key to be within the threshold, so the
            # original oversized function kept the exemption "live".
            # The exemption list is keyed by (path, qualified name); if that
            # key is not unique the data model itself is broken, so ambiguity
            # must be an error rather than something we guess our way through.
            # Zero occurrences repo-wide today, and no @overload / conditional
            # (if-else, try-except) same-name definitions exist in the scanned
            # range — so this costs nothing now. If @overload is ever adopted,
            # teach this check to skip overload stubs rather than reverting it.
            duplicate_errors.append((
                rel_path,
                qualname,
                f"[DUPLICATE DEFINITION] {rel_path}:{qualname} 有 {len(recs)} 個同名定義"
                f"（行 {', '.join(str(r.lineno) for r in sorted(recs, key=lambda r: r.lineno))}）。"
                " 豁免清單以 (檔案, qualified name) 為鍵，同名會讓該鍵無法指向唯一函式、"
                "使豁免被誤套到另一個函式上。請將其中一個改名以消除歧義。",
            ))
        exempt = key in EXEMPTIONS
        for rec in recs:
            if not exempt:
                if rec.size > MAX_LINES:
                    violations.append((rel_path, rec.lineno, qualname, rec.size))
                continue
            # Exempt: MAX_LINES no longer applies, but the grandfathered
            # baseline still does — an exemption freezes a function at its
            # current size, it is not a licence to keep growing (Codex PR
            # #122 P2-1). This is a THIRD, independent verdict alongside the
            # non-exempt MAX_LINES check above and the GHOST/STALE anti-rot
            # checks below: none of them alone catch "still over MAX_LINES,
            # still a real function, but bigger than when it was exempted".
            baseline, _reason = EXEMPTIONS[key]
            if rec.size > baseline:
                baseline_violations.append((rel_path, rec.lineno, qualname, rec.size, baseline))

    anti_rot_errors: list[tuple[str, str, str]] = []  # (rel_path, qualname, message)
    for key in sorted(EXEMPTIONS):
        rel_path, qualname = key
        recs = by_key.get(key)
        if not recs:
            anti_rot_errors.append((
                rel_path,
                qualname,
                f"[GHOST EXEMPTION] {rel_path}:{qualname} 在目前掃描結果中不存在"
                "（檔案或函式已消失/改名）。請刪除 EXEMPTIONS 裡這條豁免。",
            ))
            continue
        # Any matching node still over threshold keeps the exemption valid;
        # only flag stale if EVERY node under this key has dropped to <= MAX_LINES.
        if all(rec.size <= MAX_LINES for rec in recs):
            sizes = ", ".join(str(rec.size) for rec in recs)
            anti_rot_errors.append((
                rel_path,
                qualname,
                f"[STALE EXEMPTION] {rel_path}:{qualname} 現為 {sizes} 行"
                f"（≤ {MAX_LINES}），已不再超標。請刪除 EXEMPTIONS 裡這條豁免。",
            ))

    violations.sort(key=lambda v: (v[0], v[1], v[2]))
    for rel_path, lineno, qualname, size in violations:
        print(f"{rel_path}:{lineno} {qualname} ({size} 行) > {MAX_LINES}")

    baseline_violations.sort(key=lambda v: (v[0], v[1], v[2]))
    for rel_path, lineno, qualname, size, baseline in baseline_violations:
        print(
            f"[EXEMPTION BASELINE EXCEEDED] {rel_path}:{lineno} {qualname} 這條豁免的基準是 "
            f"{baseline} 行，現在 {size} 行——豁免不代表可以無限長大，把它縮回 {baseline} 行"
            "以內，或在 EXEMPTIONS 裡明確調高基準並補充理由。"
        )

    duplicate_errors.sort(key=lambda e: (e[0], e[1]))
    for _rel_path, _qualname, msg in duplicate_errors:
        print(msg)

    anti_rot_errors.sort(key=lambda e: (e[0], e[1]))
    for _rel_path, _qualname, msg in anti_rot_errors:
        print(msg)

    for rel_path, message in sorted(parse_errors):
        print(f"[PARSE ERROR] {rel_path}: {message}")

    if parse_errors or violations or baseline_violations or anti_rot_errors or duplicate_errors:
        print(
            f"FAIL: {len(violations)} violations, {len(baseline_violations)} exemption "
            f"baseline exceeded, {len(anti_rot_errors)} stale/ghost exemptions, "
            f"{len(duplicate_errors)} duplicate definitions, {len(parse_errors)} parse errors"
        )
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
