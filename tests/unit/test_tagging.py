"""T7a: tagging pure functions (parse / vocab map / classify / resolve)."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.ai_services.tagging import (
    TaggingFailure,
    build_system_prompt,
    classify_failure,
    parse_tags,
    resolve_vision_conn,
    to_display_names,
)
from core.ai_services.tagging_vocab import VocabItem
from core.ai_services.vision_chat import VisionConn
from core.ai_services.tagging_vocab import load_builtin
from core.cloud_translate import TranslateError
from core.database import Video, VideoRepository, init_db
from core.openai_client import OPENAI_OFFICIAL_BASE_URL
from core.path_utils import to_file_uri
from core.user_tags_write import apply_user_tags


def test_parse_tags_three_way_boundary():
    cases = [
        ('{"tags":[]}}', "ok", []),
        (
            '前言\n```json\n{"tags":[{"tag":"制服","confidence":"mid"}]}\n```\n後語',
            "ok",
            ["制服"],
        ),
        ('{"tags":["制服","水着"]}', "ok", ["制服", "水着"]),
        ('{"foo":1}', "bad", []),
        ("{not json", "bad", []),
        ("この画像では適切なタグが見つかりません。", "refused", []),
        ("這張海報看不清楚，無法標註。", "refused", []),
    ]
    for text, status, tags in cases:
        got = parse_tags(text)
        assert got.status == status, text
        if status == "ok":
            assert got.tags == tags, text


def test_vocab_names_map_to_display_names_and_drop_unknown():
    vocab = [
        VocabItem(
            name="校服",
            source="builtin",
            group="服裝",
            definition="學生制服",
            model_name="制服",
        ),
        VocabItem(
            name="泳裝",
            source="builtin",
            group="服裝",
            definition="一般泳裝",
            model_name="水着",
        ),
        VocabItem(
            name="我的標籤",
            source="custom",
            group="自訂",
            definition="自訂說明",
            model_name="我的標籤",
        ),
    ]
    raw = ["制服", "泳裝", "制服", "校服", "詞表外的字", "我的標籤", 123, None]
    assert to_display_names(raw, vocab) == ["校服", "泳裝", "我的標籤"]

    prompt = build_system_prompt(vocab)
    assert "【自訂】" in prompt
    assert "我的標籤" in prompt
    assert '- 「我的標籤」 ＝ 自訂說明' in prompt

    bare = [
        VocabItem(
            name="無說明字",
            source="custom",
            group="自訂",
            definition="",
            model_name="無說明字",
        )
    ]
    bare_prompt = build_system_prompt(bare)
    assert '- 「無說明字」' in bare_prompt
    assert '- 「無說明字」 ＝' not in bare_prompt


def test_resolve_vision_conn_table():
    def cfg(provider, model, **translate_bits):
        base = {
            "ai_services": {"tags": {"provider": provider, "model": model}},
            "translate": {
                "claude": {"api_key": "", "model": "Y"},
                "gemini": {"api_key": "", "model": "Y"},
                "openai": {"api_key": "", "base_url": "", "model": "Y"},
                "openai_official": {"api_key": "", "model": "Y"},
                "ollama": {"url": "", "model": "Y"},
            },
        }
        for path, value in translate_bits.items():
            parts = path.split(".")
            node = base["translate"]
            for p in parts[:-1]:
                node = node[p]
            node[parts[-1]] = value
        return base

    ok_cases = [
        (
            cfg("ollama", "llava", **{"ollama.url": "http://ollama.local:11434"}),
            VisionConn("ollama", "llava", "http://ollama.local:11434", ""),
        ),
        (
            cfg("gemini", "gemini-2.0-flash", **{"gemini.api_key": "gk-1"}),
            VisionConn("gemini", "gemini-2.0-flash", "", "gk-1"),
        ),
        (
            cfg("claude", "claude-haiku-5-5", **{"claude.api_key": "ck-1"}),
            VisionConn("claude", "claude-haiku-5-5", "", "ck-1"),
        ),
        (
            cfg(
                "openai",
                "gpt-4o",
                **{"openai.base_url": "http://llm.local/v1", "openai.api_key": "ok-1"},
            ),
            VisionConn("openai", "gpt-4o", "http://llm.local/v1", "ok-1"),
        ),
        (
            cfg("openai_official", "gpt-4o-mini", **{"openai_official.api_key": "ok-off"}),
            VisionConn(
                "openai_official", "gpt-4o-mini", OPENAI_OFFICIAL_BASE_URL, "ok-off"
            ),
        ),
    ]
    seen = set()
    for config, expected in ok_cases:
        got = resolve_vision_conn(config)
        assert got == expected
        seen.add((got.provider, got.model, got.base_url, got.api_key))
    assert len(seen) == 5

    # ollama 缺 url → 預設
    got = resolve_vision_conn(cfg("ollama", "llava"))
    assert got.base_url == "http://localhost:11434"

    # tags.model 優先於 translate.<p>.model
    got = resolve_vision_conn(
        cfg("claude", "X", **{"claude.api_key": "ck-2", "claude.model": "Y"})
    )
    assert got.model == "X"

    bad_cases = [
        cfg("", "m"),
        cfg("claude", ""),
        cfg("gemini", "m"),  # 缺金鑰
        cfg("openai", "m"),  # 缺 base_url
        cfg("openai_official", "m"),  # 缺金鑰
        cfg("unknown", "m"),
    ]
    for config in bad_cases:
        with pytest.raises(TaggingFailure) as ei:
            resolve_vision_conn(config)
        assert ei.value.reason == "not_configured"


def test_classify_failure_table():
    cases = [
        ("blocked", None, None),
        ("refused", None, None),
        ("connection_failed", None, "unreachable"),
        ("not_found", 404, "unreachable"),
        ("http_error", 422, "model_unsupported"),
        ("http_error", 503, "unreachable"),
        ("truncated", None, "bad_response"),
    ]
    for kind, status, expect in cases:
        exc = TranslateError(kind, status, "", "msg")
        got = classify_failure(exc)
        if expect is None:
            assert got is None
        else:
            assert isinstance(got, TaggingFailure)
            assert got.reason == expect
            assert got.detail == kind


# ---------------------------------------------------------------------------
# T7b: tag_video orchestration (real tmp DB + real NFO + real JPEG cover)
# 時序／真寫入類測試需 tmp DB＋NFO＋封面＋thread，測試行數超過產品碼屬預期。
# ---------------------------------------------------------------------------

_MINIMAL_NFO = """<?xml version='1.0' encoding='utf-8'?>
<movie><title>t</title></movie>
"""


@pytest.fixture(autouse=True)
def _isolate_canonicalize_cache():
    """canonicalize 的模組級 alias map 冷時會連真 DB → 每支測試前後隔離。"""
    from core.similar import canonicalize

    mock_repo = MagicMock()
    mock_repo.get_all.return_value = []
    canonicalize._invalidate_cache()
    with patch("core.database.TagAliasRepository", return_value=mock_repo):
        yield
    canonicalize._invalidate_cache()


@pytest.fixture(autouse=True)
def _isolate_tags_state(monkeypatch):
    """tag_video 會呼叫 tags_state.observe_*（寫 app_meta）→ 不得碰真實預設 DB（G1）。

    meta_set 換成 no-op，並把模組層觀察值歸零（BE-TEST-38）。
    """
    from core.ai_services import tags_state

    monkeypatch.setattr(tags_state, "meta_set", lambda key, value: None)
    for name, val in (
        ("unreachable", False), ("last_success_at", None), ("last_persist_mono", None),
        ("notified", False), ("notification_sink", None),
    ):
        monkeypatch.setattr(tags_state._STATE, name, val)


def _make_tag_env(
    tmp_path, monkeypatch, *, scraped_tags=(), cover=True, enabled=True, vocab=None
):
    """回 (repo, file_uri, mp4, nfo, config)；DB 一列 user_tags=["★4"]。"""
    from PIL import Image

    db_path = tmp_path / "test_tagging.db"
    init_db(db_path)

    mp4 = tmp_path / "AI-001.mp4"
    mp4.write_bytes(b"fake-video")
    nfo = mp4.with_suffix(".nfo")
    nfo.write_text(_MINIMAL_NFO, encoding="utf-8")

    cover_path = ""
    if cover:
        jpg = tmp_path / "AI-001-poster.jpg"
        Image.new("RGB", (300, 400), (120, 80, 200)).save(jpg, format="JPEG")
        cover_path = to_file_uri(str(jpg))

    file_uri = to_file_uri(str(mp4))
    repo = VideoRepository(db_path)
    repo.upsert(
        Video(
            path=file_uri,
            number="AI-001",
            title="AI-001",
            cover_path=cover_path,
            tags=list(scraped_tags),
            user_tags=["★4"],
        )
    )
    monkeypatch.setattr("core.ai_services.tagging.VideoRepository", lambda *a, **k: repo)
    monkeypatch.setattr(
        "core.ai_services.tagging.merged", lambda: vocab or load_builtin()
    )
    config = {
        "gallery": {"path_mappings": {}},
        "ai_services": {"tags": {"enabled": enabled, "provider": "ollama", "model": "m"}},
        "translate": {"ollama": {"url": ""}},
    }
    return repo, file_uri, mp4, nfo, config


def _make_vision_stub(reply):
    """回 (stub, calls)；reply 是 Exception 實例就 raise，否則 return 該字串。"""
    calls: list = []

    async def stub(conn, system, user_text, image_uri):
        calls.append((conn, system, user_text, image_uri))
        if isinstance(reply, Exception):
            raise reply
        return reply

    return stub, calls


def _reply_for(item) -> str:
    return '{"tags":[{"tag":"%s","confidence":"high"}]}' % item.model_name


def _nfo_user_tags(nfo) -> set:
    return {e.text for e in ET.parse(str(nfo)).getroot().findall("user_tag")}


def test_user_tag_added_while_model_runs_survives_in_db_and_nfo(tmp_path, monkeypatch):
    """使用者等 AI 回應時在燈箱加「待看」→ 回來後三者都在，DB 與 NFO 一致。"""
    from core.ai_services.tagging import tag_video_sync

    repo, file_uri, mp4, nfo, config = _make_tag_env(tmp_path, monkeypatch)
    item = load_builtin()[0]

    async def stub(conn, system, user_text, image_uri):
        res = apply_user_tags(
            repo, file_uri, str(mp4), config, add=["待看"], remove=[]
        )
        assert res.ok
        return _reply_for(item)

    with ThreadPoolExecutor(max_workers=1) as ex:
        outcome = ex.submit(
            tag_video_sync, file_uri, config=config, vision_fn=stub
        ).result(timeout=30)

    assert outcome.added == [item.name]
    db_tags = repo.get_by_path(file_uri).user_tags
    assert {"★4", "待看", item.name} <= set(db_tags)
    assert _nfo_user_tags(nfo) == set(db_tags)
    assert repo.get_ai_tagged_at(file_uri) is not None


_ALIAS_VOCAB = [
    VocabItem(
        name="看護婦・ナース",
        source="builtin",
        group="服裝",
        definition="d",
        model_name="看護婦・ナース",
    )
]
_STOPWORD_VOCAB = [
    VocabItem(name="4K", source="custom", group="自訂", definition="", model_name="4K")
]


@pytest.mark.parametrize(
    "scraped, vocab, aliases, expect_added, expect_user_tags",
    [
        pytest.param(
            ["护士"],
            _ALIAS_VOCAB,
            [SimpleNamespace(primary_name="看護婦・ナース", aliases=["护士"])],
            [],
            ["★4"],
            id="alias_group_already_scraped",
        ),
        pytest.param(
            [],
            _STOPWORD_VOCAB,
            [],
            ["4K"],
            ["★4", "4K"],
            id="stopword_custom_tag",
        ),
    ],
)
def test_scraped_alias_group_not_rewritten_and_stopword_custom_tag_still_written(
    tmp_path, monkeypatch, scraped, vocab, aliases, expect_added, expect_user_tags
):
    """刮削已有「护士」不再寫「看護婦・ナース」；自訂字「4K」照常寫入、不拋。"""
    from core.ai_services.tagging import tag_video
    from core.similar import canonicalize

    repo, file_uri, mp4, nfo, config = _make_tag_env(
        tmp_path, monkeypatch, scraped_tags=scraped, vocab=vocab
    )
    stub, calls = _make_vision_stub(_reply_for(vocab[0]))

    alias_repo = MagicMock()
    alias_repo.get_all.return_value = aliases
    canonicalize._invalidate_cache()
    with patch("core.database.TagAliasRepository", return_value=alias_repo):
        outcome = asyncio.run(tag_video(file_uri, config=config, vision_fn=stub))
    canonicalize._invalidate_cache()

    assert len(calls) == 1
    assert outcome.added == expect_added
    assert repo.get_by_path(file_uri).user_tags == expect_user_tags


_OK_JSON = '{"tags":[{"tag":"%s","confidence":"high"}]}' % load_builtin()[0].model_name


@pytest.mark.parametrize(
    "reply, cover, enabled, failure_reason, refused, ran, expected_calls",
    [
        pytest.param(_OK_JSON, True, True, None, False, True, 1, id="success"),
        pytest.param(
            TranslateError("blocked", None, "", "m"),
            True, True, None, True, True, 1, id="api_refusal",
        ),
        pytest.param(
            "この画像では適切なタグが見つかりません。",
            True, True, None, True, True, 1, id="prose_refusal",
        ),
        pytest.param(
            TranslateError("connection_failed", None, "", "m"),
            True, True, "unreachable", False, False, 1, id="unreachable",
        ),
        pytest.param(
            "{not json", True, True, "bad_response", False, False, 1, id="bad_json"
        ),
        pytest.param(_OK_JSON, False, True, "no_cover", False, False, 0, id="no_cover"),
        pytest.param(_OK_JSON, True, False, "disabled", False, False, 0, id="disabled"),
    ],
)
def test_ran_or_not_decision_table(
    tmp_path, monkeypatch, reply, cover, enabled, failure_reason, refused, ran,
    expected_calls,
):
    """斷網／壞 JSON／沒封面／沒開啟的片不記跑過也不亂花錢；拒答的片記跑過、0 字。"""
    from core.ai_services.tagging import tag_video

    repo, file_uri, mp4, nfo, config = _make_tag_env(
        tmp_path, monkeypatch, cover=cover, enabled=enabled
    )
    stub, calls = _make_vision_stub(reply)

    if failure_reason is not None:
        with pytest.raises(TaggingFailure) as ei:
            asyncio.run(tag_video(file_uri, config=config, vision_fn=stub))
        assert ei.value.reason == failure_reason
    else:
        outcome = asyncio.run(tag_video(file_uri, config=config, vision_fn=stub))
        assert outcome.refused is refused
        if refused:
            assert outcome.added == []

    assert len(calls) == expected_calls
    assert (repo.get_ai_tagged_at(file_uri) is not None) is ran


def test_missing_cover_file_counts_as_ran(tmp_path, monkeypatch):
    """封面路徑有值但檔案不在磁碟 → 仍拋 no_cover、但記跑過且不動使用者標籤。"""
    from core.ai_services.tagging import tag_video

    repo, file_uri, mp4, nfo, config = _make_tag_env(tmp_path, monkeypatch)
    assert repo.count_ai_tag_progress() == (1, 1)
    (tmp_path / "AI-001-poster.jpg").unlink()
    assert repo.get_by_path(file_uri).cover_path != ""
    stub, calls = _make_vision_stub(_OK_JSON)

    with pytest.raises(TaggingFailure) as ei:
        asyncio.run(tag_video(file_uri, config=config, vision_fn=stub))
    assert ei.value.reason == "no_cover"

    assert len(calls) == 0
    assert repo.get_ai_tagged_at(file_uri) is not None
    assert repo.count_ai_tag_progress() == (1, 0)
    assert repo.get_by_path(file_uri).user_tags == ["★4"]


def test_observation_runs_off_loop_and_never_changes_tag_video_result(
    tmp_path, monkeypatch
):
    """按燈箱 AI 鈕畫面不卡頓；狀態列的小毛病不會吞掉已成功的標籤；狀態列不說謊。"""
    from core.ai_services import tags_state
    from core.ai_services.tagging import tag_video

    real_success, real_failure = tags_state.observe_success, tags_state.observe_failure
    repo, file_uri, mp4, nfo, config = _make_tag_env(tmp_path, monkeypatch)
    item = load_builtin()[0]
    ok_stub, _ = _make_vision_stub(_reply_for(item))

    # (1) observe_success 不得在 event loop thread 上執行（不靠時間窗）
    on_loop: list[bool] = []

    def spy_success():
        try:
            asyncio.get_running_loop()
            on_loop.append(True)
        except RuntimeError:
            on_loop.append(False)

    monkeypatch.setattr(tags_state, "observe_success", spy_success)
    outcome = asyncio.run(tag_video(file_uri, config=config, vision_fn=ok_stub))
    assert on_loop == [False]
    assert outcome.added == [item.name]

    # (2) 觀察函式自己壞掉：回傳／原例外不變
    def broken(*args, **kwargs):
        raise RuntimeError("observer down")

    monkeypatch.setattr(tags_state, "observe_success", broken)
    monkeypatch.setattr(tags_state, "observe_failure", broken)
    outcome = asyncio.run(tag_video(file_uri, config=config, vision_fn=ok_stub))
    assert outcome.refused is False  # 沒拋、結果照常回
    bad_stub, _ = _make_vision_stub("{not json")
    with pytest.raises(TaggingFailure) as ei:
        asyncio.run(tag_video(file_uri, config=config, vision_fn=bad_stub))
    assert ei.value.reason == "bad_response"

    # (3) 真 observe_*：旗標轉移（rate_limited 不設旗標；連不上設旗標；成功清旗標）
    monkeypatch.setattr(tags_state, "observe_success", real_success)
    monkeypatch.setattr(tags_state, "observe_failure", real_failure)
    assert tags_state._STATE.unreachable is False

    def fail_with(kind, status):
        stub, _ = _make_vision_stub(TranslateError(kind, status, "", "x"))
        with pytest.raises(TaggingFailure):
            asyncio.run(tag_video(file_uri, config=config, vision_fn=stub))

    fail_with("rate_limited", 429)
    assert tags_state._STATE.unreachable is False
    fail_with("connection_failed", None)
    assert tags_state._STATE.unreachable is True
    asyncio.run(tag_video(file_uri, config=config, vision_fn=ok_stub))
    assert tags_state._STATE.unreachable is False and tags_state._STATE.last_success_at is not None
