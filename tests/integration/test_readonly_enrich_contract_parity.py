"""test_readonly_enrich_contract_parity.py — 唯讀／非唯讀 enrich 行為 contract-parity（TASK-105-T8）

[pytest-justified: cross-file readonly/non-readonly API behaviour contract, runtime 兩路徑回傳值
比對，非 static-string guard]

本檔驗的是「`web/routers/scraper.py` 唯讀分支」與「`core/enricher.py` 對應函式」**兩個檔案之間的
runtime API 行為 contract**（CLAUDE.md 判斷原則：兩檔之間的 API contract → pytest C/E 類）：
對 6 個等價邊界輸入情境，各跑一次唯讀分支（TestClient/SSE）與一次非唯讀函式（直接 call），把兩邊
回傳的 `EnrichResult` **可比欄位**（success/reason/cover_written/extrafanart_written）斷言相等，並
**明列刻意豁免欄位**（nfo_written/source_used/fields_filled/error）不比。eslint/static_guard_lint
（靜態字面掃描）無法表達「實際跑兩條 code path 比對 runtime dict」。

定位（T7 的第二道防線）：T7「一份 helper + AST 守衛」偵測「有沒有呼叫同一份 helper」；本 parity
偵測「呼叫的那份 helper 行為對不對」——同一份 helper 餵等價輸入，兩路徑吐出的可比欄位真的相等。
未來 `EnrichResult` 長新欄 / helper 換簽章導致兩路徑悄悄漂移時 fail-loud（CD-105-6-3 全歸類）。

Non-Goal（spec §3，守住）：不斷言任何時序/併發（不碰 PR#93 殘留競態）；不合併/不動兩
CoverPreserveGate 類（本檔獨立新增）；不比 `EnrichResult` 以外的 fs 路徑值。
"""

import dataclasses
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path

from unittest.mock import MagicMock, patch

from core.enrich_contract import EnrichResult


# ── 全欄位歸類常數（防「只比三欄」退化的靈魂，CD-105-6-3）────────────────────────

# 動態取，不硬編：未來 EnrichResult 加欄且未歸類 → _assert_parity 的全歸類 assert RED。
ALL_ENRICHRESULT_FIELDS = {f.name for f in dataclasses.fields(EnrichResult)}

# 可比欄位（4，斷言相等）——兩路徑本該相同：
#   success               成功/失敗語意兩路徑一致（第②層記帳結果）
#   reason                hit/no_cover/not_found/None，派生自共用 enrich_success / 共用失敗形狀（parity 核心）
#   cover_written         本次是否實際寫出封面（共用 apply_cover_preserve/should_preserve_cover 結果）
#   extrafanart_written   本次實際寫出劇照數（int）
COMPARED_FIELDS = {"success", "reason", "cover_written", "extrafanart_written"}

# 豁免欄位（4，明列理由、刻意不比）：
EXEMPT_FIELDS = {
    # nfo_written：唯讀恆 True（write_nfo=false 已在 router 上游拒絕、holistic produce 一律寫 NFO，
    #   spec §2.3）；非唯讀反映 _write_nfo 實際結果。結構性刻意差異。
    "nfo_written",
    # source_used：落地來源標籤不同（唯讀＝ingest/rescrape 來源；非唯讀＝db/nfo/scraper meta source）。
    #   spec §4 AC9「檔案路徑/來源」豁免的具現（EnrichResult 無 path 欄，路徑差異體現在此）。
    "source_used",
    # fields_filled：presence-list vs merge-diff（唯讀＝全 meta 非空 key 列 _readonly_fields_filled；
    #   非唯讀＝merge diff 列）。唯讀 ingest 無 base 可 diff，spec §2.3 刻意不同。
    "fields_filled",
    # error：失敗文案兩邊本就不同（唯讀「找不到可用的番號資料」vs 非唯讀「找不到 {number} 的資料」）
    #   ——只比 success/reason，不比 error 字面。
    "error",
}

# 註：spec §4 AC9 亦列「檔案路徑」豁免——EnrichResult dataclass 無任何 path 型欄位，故那是預防性
# 條款：本 parity 本就只碰這 8 欄、不觸及 _produce_one 的 cover_fs/movie_dir 等 fs-layout 值
# （第③層 write-layer 刻意差異，spec §5）。


def _assert_parity(readonly: dict, nonreadonly: dict):
    """契約核心：全歸類 fail-loud + 逐可比欄相等 + 豁免欄 shape 完整（不比值）。"""
    # (1) 全歸類：COMPARED ∪ EXEMPT 必須恰為 EnrichResult 全欄。未來新欄未歸類 → RED
    #     （backstop 的核心防漂移點，CD-105-6-3）。
    assert COMPARED_FIELDS | EXEMPT_FIELDS == ALL_ENRICHRESULT_FIELDS, (
        "EnrichResult 欄位未全數歸類（COMPARED ∪ EXEMPT ≠ dataclass fields）——"
        f"未歸類: {ALL_ENRICHRESULT_FIELDS - (COMPARED_FIELDS | EXEMPT_FIELDS)}；"
        f"多餘: {(COMPARED_FIELDS | EXEMPT_FIELDS) - ALL_ENRICHRESULT_FIELDS}"
    )
    # (2) 逐可比欄相等（失敗訊息帶欄名 + 兩值，便於定位哪路徑漂移）。
    for f in sorted(COMPARED_FIELDS):
        assert readonly[f] == nonreadonly[f], (
            f"parity 漂移 @ {f!r}: readonly={readonly[f]!r} != nonreadonly={nonreadonly[f]!r}"
        )
    # (3) 豁免欄不斷值，但兩邊 key 都在（證明 shape 完整、未來 rename 露餡）。
    for f in EXEMPT_FIELDS:
        assert f in readonly and f in nonreadonly, f"豁免欄 {f!r} 缺 key（shape 不完整）"


# ── 共用常數 / SSE helper ─────────────────────────────────────────────────────

NUMBER = "ABC-001"
NR_FILE = "/video/ABC-001.mp4"          # 非唯讀影片路徑（全 mock，實體不需存在）
RO_DIR = "/tmp/ro_src"                   # 唯讀來源目錄（E batch 走真 is_path_readonly，需真前綴）
RO_FILE = "/tmp/ro_src/ABC-001.mp4"
COVER_URL = "http://x/new.jpg"


def parse_sse(text: str) -> list:
    """解析 SSE 文字回傳事件 dict 列表（複製自 test_api_batch_enrich.py:16）。"""
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            import json
            events.append(json.loads(line[6:]))
    return events


def _strip_sse_wrapper(item: dict) -> dict:
    """去掉 result-item 的 SSE 包裝欄（type/number/file_path），剩 EnrichResult 8 欄。"""
    return {k: v for k, v in item.items() if k not in ("type", "number", "file_path")}


def _video_exists_only(path):
    """情境⑤ path-keyed os.path.exists side_effect：影片路徑→True、封面/其餘→False。

    🔴 非唯讀若用 blanket False 會在 enricher.py:376 top-level
    `if not os.path.exists(fs_path): return reason='error'` 提早 bail 成 error，與唯讀
    no_cover 假發散。故影片檔存在（通過 top-level 檢查）、封面檔不存在（→ no_cover）。
    """
    return str(path).endswith((".mp4", ".mkv"))


# ── 唯讀側 config / owning stub（複製精神自 test_api_enrich.py:274/285，本檔自成 fixture）──

def _readonly_gallery_config(path):
    return {
        "gallery": {"directories": [{"path": path, "readonly": True}], "path_mappings": {}},
        "search": {},
        "scraper": {},
    }


def _owning_stub(path):
    source = MagicMock()
    source.path = path
    return (source, "/out/ro", "file:///out/ro")


def _patch_os_exists(mocker, targets, os_exists):
    """os_exists 為 callable → side_effect（path-keyed）；否則 → return_value（blanket bool）。
    CD-105-8：唯讀兩處（web.routers.scraper.os.path.exists + core.enrich_contract.os.path.exists）
    機械上同 module singleton，一致即可。"""
    for t in targets:
        if callable(os_exists):
            mocker.patch(t, side_effect=os_exists)
        else:
            mocker.patch(t, return_value=os_exists)


# ── 非唯讀路徑 runner（A/B，直接 import + call，asdict 正規化）──────────────────

def _scraper_meta(cover=COVER_URL, sample_images=None):
    return {
        "number": NUMBER, "title": "T", "maker": "M",
        "cover": cover, "source": "javbus",
        "sample_images": sample_images or [],
    }


def _run_nonreadonly_enrich(*, search_result, os_exists, row_cover_path="",
                            download_image_ret=True, mode="refresh_full",
                            write_cover=True, overwrite_existing=False):
    """A：core.enricher.enrich_single 直呼。patch 落 core.enricher.* 使用端 binding +
    全域 os.path.exists（同時覆蓋 top-level 檔案檢查 / _write_cover / cover_uri_is_servable
    磁碟複驗，三者共享 module singleton）。刻意不 mock 契約 helper（enrich_success /
    compute_has_servable_cover / cover_uri_is_servable / apply_cover_preserve），只 mock
    其輸入依賴（DB row via VideoRepository / os.path.exists / download_image / search_jav）。"""
    from core.enricher import enrich_single
    row = MagicMock(cover_path=row_cover_path, user_tags=[], original_title="",
                    size_bytes=1000, mtime=1.0)
    with ExitStack() as es:
        if callable(os_exists):
            es.enter_context(patch("os.path.exists", side_effect=os_exists))
        else:
            es.enter_context(patch("os.path.exists", return_value=os_exists))
        mock_repo_cls = es.enter_context(patch("core.enricher.VideoRepository"))
        mock_repo_cls.return_value.get_by_path.return_value = row
        es.enter_context(patch("core.enricher.search_jav", return_value=search_result))
        es.enter_context(patch("core.enricher.generate_nfo", return_value=True))
        es.enter_context(patch("core.enricher.download_image", return_value=download_image_ret))
        es.enter_context(patch("core.enricher.find_subtitle_files", return_value=[]))
        es.enter_context(patch("core.focal_trigger.maybe_submit_video_focal"))
        result = enrich_single(
            file_path=NR_FILE, number=NUMBER, mode=mode,
            write_nfo=True, write_cover=write_cover, write_extrafanart=False,
            overwrite_existing=overwrite_existing,
        )
    return asdict(result)


def _run_nonreadonly_samples(*, search_meta, sample_uris):
    """B：core.enricher.fetch_samples_only 直呼。"""
    from core.enricher import fetch_samples_only
    with ExitStack() as es:
        es.enter_context(patch("os.path.exists", return_value=True))
        es.enter_context(patch("core.enricher.VideoRepository"))
        es.enter_context(patch("core.enricher.search_jav", return_value=search_meta))
        es.enter_context(patch("core.enricher._write_extrafanart", return_value=sample_uris))
        es.enter_context(patch("core.enricher._db_upsert_samples_only"))
        result = fetch_samples_only(file_path=NR_FILE, number=NUMBER)
    return asdict(result)


# ── 唯讀路徑 runner（C/D/E，TestClient，response.json()/SSE-parse 正規化）─────────

_RO_OS_EXISTS_TARGETS = ["web.routers.scraper.os.path.exists", "core.enrich_contract.os.path.exists"]


def _run_readonly_enrich(client, mocker, *, plan_meta, os_exists, existing_cover_path="",
                         produce_cover_fs="", mode="fill_missing", write_cover=True,
                         overwrite_existing=False, readonly_action="ingest"):
    """C：POST /api/enrich-single 唯讀分支。patch 落 web.routers.scraper.* 使用端 binding +
    兩處 os.path.exists（CD-105-8）。契約 helper 不 mock（跑真 helper 才測得出 parity）。"""
    mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config(RO_DIR))
    mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub(RO_DIR))
    mocker.patch("web.routers.scraper.resolve_ingest_plan",
                 return_value=(plan_meta, ("download", COVER_URL)))
    mocker.patch("web.routers.scraper._produce_one",
                 return_value=(Path("/out/ro/ABC-001"),
                               {"cover_fs": produce_cover_fs, "sample_fs": [], "nfo_mtime": 1.0}))
    mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
    mock_repo.return_value.get_by_path.return_value = MagicMock(
        size_bytes=1000, mtime=1.0, cover_path=existing_cover_path)
    _patch_os_exists(mocker, _RO_OS_EXISTS_TARGETS, os_exists)
    mocker.patch("core.focal_trigger.maybe_submit_video_focal")
    resp = client.post("/api/enrich-single", json={
        "file_path": RO_FILE, "number": NUMBER, "readonly_action": readonly_action,
        "mode": mode, "write_cover": write_cover, "overwrite_existing": overwrite_existing,
    })
    assert resp.status_code == 200
    return resp.json()


def _run_readonly_batch(client, mocker, *, plan_meta, os_exists, existing_cover_path="",
                        produce_cover_fs="", mode="refresh_full", write_cover=True,
                        overwrite_existing=False):
    """E：POST /api/batch-enrich 唯讀分支（SSE）。同 C 的決策碼，另多跑 run_in_executor +
    SSE reason 正規化（:987 'no_scrape'→'not_found'）。is_path_readonly 不 mock（走真前綴），
    故 item 檔須在 RO_DIR 下。"""
    mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config(RO_DIR))
    mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub(RO_DIR))
    mocker.patch("web.routers.scraper.resolve_ingest_plan",
                 return_value=(plan_meta, ("download", COVER_URL)))
    mocker.patch("web.routers.scraper._produce_one",
                 return_value=(Path("/out/ro/ABC-001"),
                               {"cover_fs": produce_cover_fs, "sample_fs": [], "nfo_mtime": 1.0}))
    mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
    mock_repo.return_value.get_by_path.return_value = MagicMock(
        size_bytes=1000, mtime=1.0, cover_path=existing_cover_path)
    _patch_os_exists(mocker, _RO_OS_EXISTS_TARGETS, os_exists)
    mocker.patch("core.focal_trigger.maybe_submit_video_focal")
    resp = client.post("/api/batch-enrich", json={
        "items": [{"file_path": RO_FILE, "number": NUMBER}],
        "mode": mode, "write_cover": write_cover, "overwrite_existing": overwrite_existing,
    })
    assert resp.status_code == 200
    items = [e for e in parse_sse(resp.text) if e["type"] == "result-item"]
    assert len(items) == 1
    return _strip_sse_wrapper(items[0])


def _run_readonly_samples(client, mocker, *, search_meta, produce_sample_fs):
    """D：POST /api/scraper/fetch-samples 唯讀分支。"""
    mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config(RO_DIR))
    mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub(RO_DIR))
    mocker.patch("web.routers.scraper.search_jav", return_value=search_meta)
    mocker.patch("web.routers.scraper._produce_one",
                 return_value=(Path("/out/ro/ABC-001"),
                               {"cover_fs": "", "sample_fs": produce_sample_fs, "nfo_mtime": 1.0}))
    mocker.patch("web.routers.scraper.VideoRepository")
    mocker.patch("web.routers.scraper.os.path.exists", return_value=True)
    resp = client.post("/api/scraper/fetch-samples", json={"file_path": RO_FILE, "number": NUMBER})
    assert resp.status_code == 200
    return resp.json()


# ── 6 情境 parity（各跑唯讀分支 + 非唯讀 core.enricher 對應函式）──────────────────

class TestReadonlyEnrichContractParity:

    def test_scenario_1_no_hit_not_found(self, client, mocker):
        """①全無命中：唯讀 C（resolve_ingest_plan→None）+ E（batch）vs 非唯讀 A
        （search_jav→None）。reason=not_found、cover_written=False、extrafanart=0。"""
        nr = _run_nonreadonly_enrich(search_result=None, os_exists=True, mode="refresh_full")
        assert nr["success"] is False and nr["reason"] == "not_found"

        ro_c = _run_readonly_enrich(client, mocker, plan_meta=None, os_exists=True, mode="refresh_full")
        _assert_parity(ro_c, nr)

        ro_e = _run_readonly_batch(client, mocker, plan_meta=None, os_exists=True)
        _assert_parity(ro_e, nr)  # E 覆蓋 SSE reason 正規化 'no_scrape'→'not_found'

    def test_scenario_2_meta_no_cover(self, client, mocker):
        """②有 meta 無封面：唯讀 C（cover_fs=''）+ E vs 非唯讀 A（meta 無 servable cover）。
        reason=no_cover、cover_written=False。"""
        nr = _run_nonreadonly_enrich(
            search_result=_scraper_meta(cover=""), os_exists=True, row_cover_path="",
            mode="refresh_full")
        assert nr["success"] is True and nr["reason"] == "no_cover" and nr["cover_written"] is False

        ro_c = _run_readonly_enrich(
            client, mocker, plan_meta=_scraper_meta(cover=""), os_exists=True,
            existing_cover_path="", produce_cover_fs="", mode="refresh_full")
        _assert_parity(ro_c, nr)

        ro_e = _run_readonly_batch(
            client, mocker, plan_meta=_scraper_meta(cover=""), os_exists=True,
            existing_cover_path="", produce_cover_fs="")
        _assert_parity(ro_e, nr)

    def test_scenario_3_meta_cover_written(self, client, mocker):
        """③有 meta＋封面成功寫（overwrite=True 排除 preserve）：唯讀 C（cover_fs 有值、
        servable）vs 非唯讀 A（download_image→True、DB cover 在）。reason=hit、cover_written=True。"""
        nr = _run_nonreadonly_enrich(
            search_result=_scraper_meta(), os_exists=True,
            row_cover_path="file:///video/ABC-001.jpg", download_image_ret=True,
            mode="refresh_full", overwrite_existing=True)
        assert nr["success"] is True and nr["reason"] == "hit" and nr["cover_written"] is True

        ro_c = _run_readonly_enrich(
            client, mocker, plan_meta=_scraper_meta(), os_exists=True,
            existing_cover_path="file:///out/cover.jpg",
            produce_cover_fs="/out/ro/ABC-001/ABC-001.jpg",
            mode="refresh_full", overwrite_existing=True, readonly_action="rescrape")
        _assert_parity(ro_c, nr)

    def test_scenario_4_fill_missing_existing_cover_preserved(self, client, mocker):
        """④fill_missing+overwrite=False+既有 servable 封面（保留）：唯讀 C（had_cover=True →
        cover_strategy ('none',)）vs 非唯讀 A（_write_cover should_preserve→True）。
        cover_written=False 但 reason=hit（has_servable_cover 解耦）。"""
        nr = _run_nonreadonly_enrich(
            search_result=_scraper_meta(), os_exists=True,
            row_cover_path="file:///video/ABC-001.jpg",
            mode="fill_missing", overwrite_existing=False)
        assert nr["success"] is True and nr["reason"] == "hit" and nr["cover_written"] is False

        ro_c = _run_readonly_enrich(
            client, mocker, plan_meta=_scraper_meta(), os_exists=True,
            existing_cover_path="file:///out/cover.jpg", produce_cover_fs="",
            mode="fill_missing", overwrite_existing=False)
        _assert_parity(ro_c, nr)

    def test_scenario_5_residual_cover_deleted_on_disk(self, client, mocker):
        """⑤既有封面磁碟已刪（residual cover_path、檔不在）：唯讀 C vs 非唯讀 A。
        🔴 兩路徑皆用 path-keyed os.path.exists（影片→True、封面→False），非唯讀不可用
        blanket False（會 top-level bail 成 reason='error' 假發散）。reason=no_cover、
        cover_written=False。"""
        nr = _run_nonreadonly_enrich(
            search_result=_scraper_meta(), os_exists=_video_exists_only,
            row_cover_path="file:///out/old.jpg", download_image_ret=False,
            mode="refresh_full", overwrite_existing=False)
        assert nr["success"] is True and nr["reason"] == "no_cover" and nr["cover_written"] is False

        ro_c = _run_readonly_enrich(
            client, mocker, plan_meta=_scraper_meta(), os_exists=_video_exists_only,
            existing_cover_path="file:///out/old.jpg", produce_cover_fs="",
            mode="fill_missing", overwrite_existing=False)
        _assert_parity(ro_c, nr)

    def test_scenario_6_samples(self, client, mocker):
        """⑥補劇照：唯讀 D（fetch-samples readonly）vs 非唯讀 B（fetch_samples_only）。
        兩子例：成功（extrafanart=N、reason=None）＋找不到（success=False、reason=None）。"""
        # ⑥a 成功：N=2 samples 寫出
        nr_ok = _run_nonreadonly_samples(
            search_meta=_scraper_meta(sample_images=["s1", "s2"]), sample_uris=["u1", "u2"])
        assert nr_ok["success"] is True and nr_ok["reason"] is None and nr_ok["extrafanart_written"] == 2

        ro_ok = _run_readonly_samples(
            client, mocker, search_meta=_scraper_meta(sample_images=["s1", "s2"]),
            produce_sample_fs=["f1", "f2"])
        _assert_parity(ro_ok, nr_ok)

        # ⑥b 找不到：search_jav→None，兩路徑 reason=None（samples 站不設 reason）
        nr_miss = _run_nonreadonly_samples(search_meta=None, sample_uris=[])
        assert nr_miss["success"] is False and nr_miss["reason"] is None

        ro_miss = _run_readonly_samples(client, mocker, search_meta=None, produce_sample_fs=[])
        _assert_parity(ro_miss, nr_miss)
