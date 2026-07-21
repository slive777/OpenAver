"""唯讀/非唯讀第②層「寫後記帳+回報」收斂終態的跨檔 AST 結構守衛（feature/105 T7）。

[pytest-justified: cross-file Python AST contract, feature/91/66 先例]

把 T1–T6 收斂後的「一份實作」最終狀態用機械閘鎖死，防止 enricher 未來一長新
欄位就再手抄一份唯讀拷貝（PR#113 八輪 churn 的根因）：

  1. **正向鎖**：對明列的 production target 函式（P1–P7），斷言其 named
     FunctionDef body 內含對應 `core.enrich_contract` / `core.focal_trigger`
     helper 的 `ast.Call`（消除手抄的第②層邏輯）。
  2. **負向鎖**：對同一批 target body，以 AST 節點形狀（非字串 regex）斷言
     四類舊 mirror 手抄指紋不復生。
  3. **白名單防腐**：每個 named target 必須能 AST 定位，避免改名後恆綠假通過。

掃描粒度＝named `FunctionDef`/`AsyncFunctionDef` 的「直接 body」（遞迴但**停在
巢狀 def**，比照先例 `test_async_offload_guard.py::_collect_direct_calls`）：
`event_generator` 收集 Call 時停在 nested `_do_readonly`，故 P6 的四支阻塞
helper 不會污染 P7、P7 只鎖 event_generator 自身的 `enrich_success`。

為何 pytest 不是 lint（CLAUDE.md「Lint 守衛規則」north-star）：本守衛驗的是
「某個 Python 函式的源碼語意（AST 節點形狀）」——CLAUDE.md 判斷原則明列此類走
pytest（C 類）。它 walk named FunctionDef 的 `ast.Call`/`ast.Assign`/`ast.BoolOp`
節點形狀，非 `"name" in source` 字面掃描，故 eslint/static_guard 無法表達、
亦不觸 SA-pre-6 的 html/js/css content-based 偵測。
"""
import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).parents[2]
ENRICHER_PY = REPO_ROOT / "core" / "enricher.py"
SCRAPER_PY = REPO_ROOT / "web" / "routers" / "scraper.py"


# ============================================================
# AST 工具（比照 test_async_offload_guard.py 骨架）
# ============================================================

def _parse(py_file: pathlib.Path) -> ast.Module:
    return ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))


def _find_func(tree: ast.Module, name: str):
    """全樹遍歷找 node.name == name 的 FunctionDef/AsyncFunctionDef（名稱檔內唯一）。

    涵蓋雙層巢狀（`event_generator` in `batch_enrich_endpoint`；`_do_readonly` in
    `event_generator`）——`ast.walk` 遞迴命中即可。找不到回 None（白名單防腐用）。
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _direct_nodes(func_node) -> list:
    """收集 func_node「直接 body」的所有子節點（遞迴，但**停在巢狀 def**）。

    停在 nested `FunctionDef`/`AsyncFunctionDef`：故 `event_generator` 的收集不會
    下潛到 `_do_readonly`，兩者各自獨立掃描、集合互不污染（比照先例
    `_collect_direct_calls`「遇 nested def 就 continue 不下潛」）。
    """
    out = []

    def _walk(nodes):
        for node in nodes:
            out.append(node)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            _walk(ast.iter_child_nodes(node))

    _walk(ast.iter_child_nodes(func_node))
    return out


def _call_name(call: ast.Call):
    """取 Call 的函式名：ast.Name → .id（裸名，如 enrich_success()）；
    ast.Attribute → .attr（如 mod.enrich_success()）。

    HEAD 實測六支 helper + schedule_focal_after_cover_write 全以裸名呼叫（各模組
    `from … import`），故 `.id` 即命中；仍涵蓋 `.attr` 防未來改 import 風格
    （比照先例 `test_async_offload_guard.py::_call_name`）。
    """
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _direct_call_names(func_node) -> set:
    return {
        _call_name(n)
        for n in _direct_nodes(func_node)
        if isinstance(n, ast.Call) and _call_name(n) is not None
    }


# ============================================================
# 正向鎖清單（HEAD 51d33ca3 實測，權威見 TASK-105-T7 現況分析表）
# ============================================================
# (檔案, 函式名, {必含 helper Call})
POSITIVE_LOCKS = [
    # P1
    (ENRICHER_PY, "enrich_single", {
        "effective_original_title",
        "compute_has_servable_cover",
        "enrich_success",
        "schedule_focal_after_cover_write",  # focal 站 A（AC7）
    }),
    # P2
    (ENRICHER_PY, "_write_cover", {"should_preserve_cover"}),
    # P3
    (ENRICHER_PY, "fetch_samples_only", {"enrich_success"}),
    # P4
    (SCRAPER_PY, "enrich_single_endpoint", {
        "cover_uri_is_servable",
        "apply_cover_preserve",
        "compute_has_servable_cover",
        "enrich_success",
        "schedule_focal_after_cover_write",  # focal 站 B（AC7）
    }),
    # P5
    (SCRAPER_PY, "fetch_samples_endpoint", {"enrich_success"}),
    # P6 — nested：只鎖自身 body 的四支阻塞 helper，**不含** enrich_success
    #      （enrich_success 在 event_generator/P7，非 _do_readonly）
    (SCRAPER_PY, "_do_readonly", {
        "cover_uri_is_servable",
        "apply_cover_preserve",
        "compute_has_servable_cover",
        "schedule_focal_after_cover_write",  # focal 站 C（AC7）
    }),
    # P7 — nested async：batch 唯讀成功 result dict 專屬（在 _do_readonly 返回後的
    #      async context，收集停在 nested def 故不含 P6 四支）
    (SCRAPER_PY, "event_generator", {"enrich_success"}),
]

# 白名單防腐：所有 named target（去重）
ALL_TARGETS = [(f, n) for f, n, _ in POSITIVE_LOCKS]

_TREE_CACHE: dict = {}


def _tree(py_file: pathlib.Path) -> ast.Module:
    key = str(py_file)
    if key not in _TREE_CACHE:
        _TREE_CACHE[key] = _parse(py_file)
    return _TREE_CACHE[key]


# [lint-guard: pytest-justified] Python-AST 源碼語意守衛（cross-file enrich_contract 契約）：
# 斷言 AST 節點形狀 / detector 函式在 parsed Python 片段上的行為，非 html/js/css 靜態
# 字串存在檢查，eslint/static_guard 無法表達（pre-merge SA-pre-6 例外清單「Python-AST
# 源碼語意守衛」）。
class TestPositiveContractLocks:
    """正向鎖：每個 target body 必含指定共用 helper 的 Call（消除手抄第②層）。"""

    @pytest.mark.parametrize("py_file, func_name, required", POSITIVE_LOCKS,
                             ids=[n for _, n, _ in POSITIVE_LOCKS])
    def test_target_calls_required_helpers(self, py_file, func_name, required):
        func = _find_func(_tree(py_file), func_name)
        assert func is not None, f"{py_file.name}:{func_name} 定位不到（白名單防腐應先報）"
        present = _direct_call_names(func)
        missing = required - present
        assert not missing, (
            f"{py_file.name}:{func_name}() 的 body 未呼叫共用 helper {sorted(missing)}"
            f" —— 疑似手抄第②層邏輯而繞過 core.enrich_contract/core.focal_trigger。"
            f" 現有直接呼叫: {sorted(present)}"
        )


# ============================================================
# 負向鎖：四類舊 mirror 手抄指紋（AST 節點形狀，非字串 regex）
# ============================================================

def _is_mirror_cover_assign(node) -> bool:
    """指紋1：`has_servable_cover = cover_written or had_cover`。

    要求：(a) 單一 bare Name target（id=='has_servable_cover'）——**排除** 961 的
    Tuple/List 解包；(b) value 為 BoolOp(Or) 且**兩 operand 皆 ast.Name**——961 的
    `payload or ({}, {}, False)` 右 operand 是 Tuple 非 Name，天然排除；正確碼
    `has_servable_cover = compute_has_servable_cover(...)` value 是 Call 非 BoolOp，
    亦排除。
    """
    if not isinstance(node, ast.Assign):
        return False
    if len(node.targets) != 1:
        return False
    tgt = node.targets[0]
    if not (isinstance(tgt, ast.Name) and tgt.id == "has_servable_cover"):
        return False
    val = node.value
    if not (isinstance(val, ast.BoolOp) and isinstance(val.op, ast.Or)):
        return False
    return all(isinstance(v, ast.Name) for v in val.values)


def _is_inline_reason_ifexp(node) -> bool:
    """指紋2：inline `reason = 'hit' if … else 'no_cover'`（reason 派生已入
    enrich_success builder，不得散落 target body）。IfExp body/orelse 為
    Constant('hit')/Constant('no_cover')。
    """
    if not isinstance(node, ast.IfExp):
        return False
    body, orelse = node.body, node.orelse
    if not (isinstance(body, ast.Constant) and isinstance(orelse, ast.Constant)):
        return False
    return {body.value, orelse.value} == {"hit", "no_cover"}


def _is_fill_missing_had_cover_boolop(node) -> bool:
    """指紋3：`mode == 'fill_missing' and not … and had_cover`（已被
    apply_cover_preserve 取代、fill_missing 顯式閘移除）。BoolOp(And) 之子樹含
    Compare(== Constant('fill_missing')) 且含 Name('had_cover')。
    """
    if not (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And)):
        return False
    subtree = list(ast.walk(node))
    has_fill = any(
        isinstance(c, ast.Compare)
        and any(isinstance(cmp, ast.Constant) and cmp.value == "fill_missing"
                for cmp in ([c.left] + list(c.comparators)))
        for c in subtree
    )
    has_had_cover = any(isinstance(c, ast.Name) and c.id == "had_cover" for c in subtree)
    return has_fill and has_had_cover


def _is_second_original_title_preserve(node) -> bool:
    """指紋4：第二套手寫 original_title preserve `… or <row>.original_title`
    （唯一 preserve 只在 effective_original_title helper）。BoolOp(Or) 之子樹含
    `Attribute(attr='original_title', value=Name(<任意>))`。

    **錨定 attr shape、不錨定 receiver 變數名**（F1 修正）：主 target `enrich_single`
    的 DB row 變數是 `existing_record`（非 `existing`），若硬編 `existing.` 會漏掉最
    可能發生複製回退的那個站（AST 指紋硬編 receiver 名的經典假綠）。任意 `Name`
    receiver 的 `.original_title` 屬性存取都算——因 `meta` 是 dict、走 `meta.get(...)`
    不會有 `.original_title` 屬性存取，只有 DB row 物件（不論命名）才有此屬性；
    全庫唯一的合法 `<x>.original_title`（`enricher.py:80` `video.original_title`）在
    所有 named target 之外、且非 BoolOp，粒度天然不掃。

    不誤傷 plain `meta.get("original_title","")`（那是純 Call、非 Attribute，且在
    _write_nfo/_db_upsert/_write_movie_assets 等非-target 函式，粒度天然不掃）。
    """
    if not (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)):
        return False
    for c in ast.walk(node):
        if (isinstance(c, ast.Attribute) and c.attr == "original_title"
                and isinstance(c.value, ast.Name)):
            return True
    return False


NEGATIVE_FINGERPRINTS = [
    ("has_servable_cover = cover_written or had_cover", _is_mirror_cover_assign),
    ("reason = 'hit' if … else 'no_cover'", _is_inline_reason_ifexp),
    ("mode == 'fill_missing' and … and had_cover", _is_fill_missing_had_cover_boolop),
    ("… or existing.original_title (2nd preserve)", _is_second_original_title_preserve),
]


# [lint-guard: pytest-justified] Python-AST 源碼語意守衛（cross-file enrich_contract 契約）：
# 斷言 AST 節點形狀 / detector 函式在 parsed Python 片段上的行為，非 html/js/css 靜態
# 字串存在檢查，eslint/static_guard 無法表達（pre-merge SA-pre-6 例外清單「Python-AST
# 源碼語意守衛」）。
class TestNegativeMirrorLocks:
    """負向鎖：target body 內不得殘留四類舊 mirror 手抄指紋。"""

    @pytest.mark.parametrize("py_file, func_name", ALL_TARGETS,
                             ids=[n for _, n in ALL_TARGETS])
    def test_no_mirror_fingerprints(self, py_file, func_name):
        func = _find_func(_tree(py_file), func_name)
        assert func is not None, f"{py_file.name}:{func_name} 定位不到"
        nodes = _direct_nodes(func)
        violations = []
        for label, detector in NEGATIVE_FINGERPRINTS:
            if any(detector(n) for n in nodes):
                violations.append(label)
        assert not violations, (
            f"{py_file.name}:{func_name}() 復生舊 mirror 手抄指紋: {violations}"
            f" —— 第②層邏輯應共用 core.enrich_contract helper，不得手抄。"
        )


# [lint-guard: pytest-justified] Python-AST 源碼語意守衛（cross-file enrich_contract 契約）：
# 斷言 AST 節點形狀 / detector 函式在 parsed Python 片段上的行為，非 html/js/css 靜態
# 字串存在檢查，eslint/static_guard 無法表達（pre-merge SA-pre-6 例外清單「Python-AST
# 源碼語意守衛」）。
class TestFalsePositiveGuards:
    """反證：GREEN 狀態下守衛不誤傷 961 Tuple-target 與非-target plain meta.get。"""

    def test_961_tuple_target_not_flagged(self):
        """scraper.py:961 `assets, item_meta, has_servable_cover = payload or ({}, {}, False)`
        是 Tuple-target 的正確碼（T2「用參數表達刻意差異」），負向鎖指紋1 不得命中。
        """
        eg = _find_func(_tree(SCRAPER_PY), "event_generator")
        assert eg is not None
        tuple_assigns = [
            n for n in _direct_nodes(eg)
            if isinstance(n, ast.Assign)
            and len(n.targets) == 1 and isinstance(n.targets[0], ast.Tuple)
            and any(isinstance(e, ast.Name) and e.id == "has_servable_cover"
                    for e in n.targets[0].elts)
        ]
        assert tuple_assigns, (
            "應能在 event_generator 定位到 961 的 Tuple-target has_servable_cover 解包"
            "（找不到代表掃描函式錯或該碼已移除，需複查 T7 設計）"
        )
        for a in tuple_assigns:
            assert not _is_mirror_cover_assign(a), (
                "961 Tuple-target `payload or (…)` 被指紋1 誤報為 BLOCKER —— "
                "指紋1 的『單一 bare Name target + 兩 Name operand』排除失效"
            )

    def test_plain_meta_get_original_title_not_in_targets(self):
        """三處 plain `meta.get("original_title","")` 皆在非-target 函式
        （_write_nfo/_db_upsert/_write_movie_assets）；且即便當作 Call 節點也非
        指紋4（BoolOp 形狀）。確認負向鎖粒度天然不掃這些正確碼。
        """
        # 確認 target 清單不含這三個非-target 函式
        target_names = {n for _, n in ALL_TARGETS}
        assert target_names.isdisjoint({"_write_nfo", "_db_upsert", "_write_movie_assets"})
        # 即使掃到 plain meta.get，指紋4（BoolOp Or）形狀不會命中它（它是純 Call）
        tree = _tree(ENRICHER_PY)
        wr = _find_func(tree, "_write_nfo")
        assert wr is not None
        assert not any(_is_second_original_title_preserve(n) for n in _direct_nodes(wr)), (
            "plain meta.get('original_title') 被指紋4 誤報 —— 指紋4 應只命中 "
            "BoolOp(Or) 含 existing.original_title"
        )


# [lint-guard: pytest-justified] Python-AST 源碼語意守衛（cross-file enrich_contract 契約）：
# 斷言 AST 節點形狀 / detector 函式在 parsed Python 片段上的行為，非 html/js/css 靜態
# 字串存在檢查，eslint/static_guard 無法表達（pre-merge SA-pre-6 例外清單「Python-AST
# 源碼語意守衛」）。
class TestNegativeDetectorSensitivity:
    """負向鎖 detector 敏感度（防近空殼假綠）：直接餵 AST 片段，斷言四個 detector
    對 canonical mirror 形狀**命中**、對正確碼**放行**。這把「守衛真的鎖得住」的
    mutation 直覺固化成回歸測試（F1：指紋4 曾硬編 `existing` 漏掉主 target 的
    `existing_record`）。"""

    @staticmethod
    def _first(src: str, node_type):
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, node_type):
                return n
        raise AssertionError(f"片段內找不到 {node_type.__name__}")

    def test_fp1_fires_on_canonical_mirror(self):
        node = self._first("has_servable_cover = cover_written or had_cover", ast.Assign)
        assert _is_mirror_cover_assign(node)

    def test_fp1_passes_961_tuple_and_correct_call(self):
        assert not _is_mirror_cover_assign(
            self._first("a, b, has_servable_cover = payload or ({}, {}, False)", ast.Assign))
        assert not _is_mirror_cover_assign(
            self._first("has_servable_cover = compute_has_servable_cover(r, u, m)", ast.Assign))

    def test_fp2_fires_on_inline_reason(self):
        node = self._first("reason = 'hit' if hsc else 'no_cover'", ast.IfExp)
        assert _is_inline_reason_ifexp(node)

    def test_fp3_fires_on_fill_missing_gate(self):
        node = self._first(
            "x = mode == 'fill_missing' and not overwrite and had_cover", ast.BoolOp)
        assert _is_fill_missing_had_cover_boolop(node)

    def test_fp4_fires_on_both_receiver_names(self):
        # F1：主 target enrich_single 用 existing_record（非 existing）——兩者都須命中
        for recv in ("existing", "existing_record", "row"):
            node = self._first(
                f"t = meta.get('original_title') or ({recv}.original_title if {recv} else '')",
                ast.BoolOp)
            assert _is_second_original_title_preserve(node), f"指紋4 漏掉 receiver={recv}"

    def test_fp4_passes_plain_meta_get(self):
        # 純 Call、無 .original_title 屬性存取 → 不得命中
        for n in ast.walk(ast.parse('t = meta.get("original_title", "")')):
            if isinstance(n, ast.BoolOp):
                raise AssertionError("片段不應含 BoolOp")
        # 顯式：整棵樹無任一節點被指紋4 判為 True
        assert not any(
            _is_second_original_title_preserve(n)
            for n in ast.walk(ast.parse('t = meta.get("original_title", "")')))


# [lint-guard: pytest-justified] Python-AST 源碼語意守衛（cross-file enrich_contract 契約）：
# 斷言 AST 節點形狀 / detector 函式在 parsed Python 片段上的行為，非 html/js/css 靜態
# 字串存在檢查，eslint/static_guard 無法表達（pre-merge SA-pre-6 例外清單「Python-AST
# 源碼語意守衛」）。
class TestWhitelistAntiRot:
    """白名單防腐（比照先例 test_whitelist_entries_exist）：
    每個 named target 必須能在對應檔 AST 定位，否則守衛指向殭屍函式、恆綠假通過。
    """

    @pytest.mark.parametrize("py_file, func_name", ALL_TARGETS,
                             ids=[n for _, n in ALL_TARGETS])
    def test_target_function_exists(self, py_file, func_name):
        func = _find_func(_tree(py_file), func_name)
        assert func is not None, (
            f"正向/負向鎖 target {py_file.name}:{func_name} 指向不存在的函式"
            f"（改名？）—— 守衛失去意義，須更新清單或修復函式名"
        )
