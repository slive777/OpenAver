"""test_metatube_mapper.py - metatube mapper + clean_metatube_summary 邊界測試"""
import json

import pytest
from core.scrapers.models import Actress


# ============ Fixture ============

def _full_info() -> dict:
    """模仿 FANZA POC 完整 22 欄回傳"""
    return {
        "id": "abc123",
        "number": "SONE-205",
        "title": "テストタイトル",
        "summary": "これはテスト用の簡介です。",
        "provider": "FANZA",
        "homepage": "https://fanza.com/sone-205",
        "director": "山田太郎",
        "actors": ["女優A", "女優B"],
        "thumb_url": "https://img.fanza.com/thumb.jpg",
        "big_thumb_url": "https://img.fanza.com/big_thumb.jpg",
        "cover_url": "https://img.fanza.com/cover.jpg",
        "big_cover_url": "",
        "preview_video_url": "",
        "preview_video_hls_url": "",
        "preview_images": ["https://img.fanza.com/s1.jpg", "https://img.fanza.com/s2.jpg"],
        "maker": "S1 NO.1 STYLE",
        "label": "S1",
        "series": "テストシリーズ",
        "genres": ["巨乳", "美少女"],
        "score": 8.5,
        "runtime": 120,
        "release_date": "2024-01-15T00:00:00Z",
    }


# ============ 主映射測試 ============

def test_map_full_info_basic_fields():
    """完整 dict → Video 基本欄 1:1"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    video = map_movie_info(info)

    assert video.number == "SONE-205"
    assert video.title == "テストタイトル"
    assert video.maker == "S1 NO.1 STYLE"
    assert video.director == "山田太郎"
    assert video.label == "S1"
    assert video.series == "テストシリーズ"


def test_map_full_info_actresses():
    """actors list → actresses list[Actress]"""
    from core.metatube.mapper import map_movie_info
    video = map_movie_info(_full_info())
    assert video.actresses == [Actress(name="女優A"), Actress(name="女優B")]


def test_map_full_info_date():
    """release_date T 格式 → date YYYY-MM-DD"""
    from core.metatube.mapper import map_movie_info
    video = map_movie_info(_full_info())
    assert video.date == "2024-01-15"


def test_map_full_info_tags_detail_url_sample_images():
    """genres→tags, homepage→detail_url, preview_images→sample_images"""
    from core.metatube.mapper import map_movie_info
    video = map_movie_info(_full_info())
    assert video.tags == ["巨乳", "美少女"]
    assert video.detail_url == "https://fanza.com/sone-205"
    assert video.sample_images == ["https://img.fanza.com/s1.jpg", "https://img.fanza.com/s2.jpg"]


def test_map_full_info_cover_url():
    """cover_url 1:1"""
    from core.metatube.mapper import map_movie_info
    video = map_movie_info(_full_info())
    assert video.cover_url == "https://img.fanza.com/cover.jpg"


def test_map_full_info_rating_nonzero():
    """score 非零 → rating passthrough"""
    from core.metatube.mapper import map_movie_info
    video = map_movie_info(_full_info())
    assert video.rating == 8.5


def test_map_full_info_duration_nonzero():
    """runtime 非零 → duration passthrough"""
    from core.metatube.mapper import map_movie_info
    video = map_movie_info(_full_info())
    assert video.duration == 120


def test_map_full_info_source():
    """provider → source = "metatube:FANZA" """
    from core.metatube.mapper import map_movie_info
    video = map_movie_info(_full_info())
    assert video.source == "metatube:FANZA"


def test_map_full_info_summary():
    """summary 非 FC2 → clean passthrough"""
    from core.metatube.mapper import map_movie_info
    video = map_movie_info(_full_info())
    assert video.summary == "これはテスト用の簡介です。"


def test_map_full_info_us7_summary_not_in_legacy_dict():
    """US7 硬契約：summary 永不入 to_legacy_dict()"""
    from core.metatube.mapper import map_movie_info
    video = map_movie_info(_full_info())
    assert "summary" not in video.to_legacy_dict()


def test_map_empty_actors():
    """actors=[] → actresses=[], 不炸"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["actors"] = []
    video = map_movie_info(info)
    assert video.actresses == []


def test_map_actors_with_empty_string():
    """actors 含空字串 → 過濾，不觸發 Actress min_length=1 ValidationError"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["actors"] = ["Alice", "", "Bob"]
    video = map_movie_info(info)
    assert video.actresses == [Actress(name="Alice"), Actress(name="Bob")]


def test_map_score_zero_to_none():
    """score=0.0 → rating is None"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["score"] = 0.0
    video = map_movie_info(info)
    assert video.rating is None


def test_map_runtime_zero_to_none():
    """runtime=0 → duration is None（CD-63a-9 plan 拍板）"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["runtime"] = 0
    video = map_movie_info(info)
    assert video.duration is None


def test_map_release_date_no_t():
    """release_date 無 T → date 原樣（split("T")[0] 安全）"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["release_date"] = "2024-01-15"
    video = map_movie_info(info)
    assert video.date == "2024-01-15"


def test_map_release_date_empty():
    """release_date="" → date="" 不炸"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["release_date"] = ""
    video = map_movie_info(info)
    assert video.date == ""


def test_map_release_date_null():
    """release_date=None（JSON null）→ date="" 不炸（`or ""` 攔 None，不走 None.split）"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["release_date"] = None
    video = map_movie_info(info)
    assert video.date == ""


def test_map_missing_optional_keys():
    """缺 series/label/director/preview_images/genres → 預設值，不炸"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    for k in ("series", "label", "director", "preview_images", "genres"):
        info.pop(k, None)
    video = map_movie_info(info)
    assert video.series == ""
    assert video.label == ""
    assert video.director == ""
    assert video.sample_images == []
    assert video.tags == []


def test_map_actors_none():
    """actors=None → actresses=[], 不炸"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["actors"] = None
    video = map_movie_info(info)
    assert video.actresses == []


# ============ TASK-113c-T3b: preview_cover_url（CD-113c-4／12／13） ============

def test_map_movie_info_binds_preview_cover_url_from_base_url():
    """base_url 顯式傳入 → preview_cover_url 出生時就綁定（DoD-1）

    來源一致性（feature/metatube-image-proxy）：從 metatube 刮到的影片，
    cover_url 也走 metatube 的 `/v1/images/primary/...` 代理端點取回，
    避免本地直連被牆的源站圖片 URL。
    """
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    assert video.preview_cover_url != ""
    assert video.preview_cover_url.startswith("http://192.168.1.100:8080/v1/images/primary/FANZA/SONE-205?")
    assert video.cover_url == video.preview_cover_url


def test_map_movie_info_no_base_url_yields_empty_preview():
    """未傳 base_url（預設 ""）→ preview_cover_url 空字串，cover_url 不受影響（DoD-1）"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    video = map_movie_info(info)
    assert video.preview_cover_url == ""
    assert video.cover_url == "https://img.fanza.com/cover.jpg"


def test_preview_cover_url_empty_when_cover_url_missing():
    """cover_url 本身空 → 即使有 base_url，preview_cover_url 仍為空（沒有可預覽的東西）"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["cover_url"] = ""
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    assert video.preview_cover_url == ""


def test_preview_cover_url_ratio_zero_quality_100():
    """組出的 URL 帶 ratio=0 與 quality=100（DoD-7）"""
    from urllib.parse import urlparse, parse_qs
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    parsed = urlparse(video.preview_cover_url)
    qs = parse_qs(parsed.query)
    assert qs["ratio"] == ["0"]
    assert qs["quality"] == ["100"]


def test_preview_cover_url_query_encoding_no_ampersand_pollution():
    """cover_url 帶 ?token=...&expires=... → 組出的 URL 解析後 url 參數逐字元等於原始
    cover_url，且 ratio／quality 各恰好出現一次（CD-113c-13，DoD-8①）"""
    from urllib.parse import urlparse, parse_qs
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    original_cover_url = "https://img.fanza.com/cover.jpg?token=abc&expires=123"
    info["cover_url"] = original_cover_url
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    parsed = urlparse(video.preview_cover_url)
    qs = parse_qs(parsed.query)
    assert qs["url"] == [original_cover_url]
    assert len(qs["ratio"]) == 1
    assert len(qs["quality"]) == 1


def test_preview_cover_url_allows_safe_hyphenated_provider():
    """provider/number 含連字號（如 tokyo-hot）等安全字元 → 不轉義、直通（DoD-8②）"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["provider"] = "tokyo-hot"
    info["number"] = "n1234"
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    assert "/v1/images/primary/tokyo-hot/n1234?" in video.preview_cover_url


def test_preview_cover_url_empty_when_provider_needs_escaping():
    """provider 含 quote(safe="") 需要轉義的字元（此處用空白）→ 回空字串，
    不產生一個上線會被 T3a `_SAFE_PATH_SEGMENT` 擋下的 URL（設計問題 3／DoD-8③）"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["provider"] = "FAN ZA"
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    assert video.preview_cover_url == ""


def test_preview_cover_url_empty_when_number_needs_escaping():
    """number 含需要轉義的字元（斜線）→ 回空字串（設計問題 3／DoD-8③）"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["number"] = "SONE/205"
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    assert video.preview_cover_url == ""


def test_preview_cover_url_implies_cover_url_nonempty():
    """不變式：preview_cover_url 非空 ⟹ cover_url 非空。

    這條不變式是 web/templates/search.html detail 面板三個 x-show 閘門仍能用
    `current().cover` 判斷「有沒有東西可顯示」的唯一理由——這三個閘門 T3b
    刻意不改（TASK-113c-T3b.md DoD-5：detail 面板模板本身不需改，:src 已改用
    coverUrl() 優先 preview_cover_url）：
      - :412 `x-show="!coverError && current().cover"`（img 本身是否顯示）
      - :418 `x-show="!coverError && current().cover && !_coverLoaded"`（loading shimmer）
      - :429 `x-show="!coverError && !current().cover"`（「無封面」placeholder，反向）

    若這條不變式被打破（例如未來讓 preview_cover_url 可以在 cover_url 空時仍
    產生值），這三個閘門會用「沒有 cover」的判斷去藏一張其實存在的 preview
    圖——detail 面板封面會靜默消失，而 `:src="coverUrl()"` 端完全沒有錯誤可看
    （coverUrl() 本身不會拋例外，只是永遠不會被渲染出來）。

    本測試窮舉：一般案例／cover_url 本身空／T3a 接縫降級（provider、number 各自
    需要轉義）／有無 base_url，逐一驗證 implication，不是單一案例的巧合。
    """
    from core.metatube.mapper import map_movie_info

    scenarios = [
        dict(_full_info()),
        {**_full_info(), "cover_url": ""},
        {**_full_info(), "provider": "FAN ZA"},   # T3a 接縫降級（設計問題 3）
        {**_full_info(), "number": "SONE/205"},   # T3a 接縫降級（設計問題 3）
    ]
    for info in scenarios:
        for base_url in ("", "http://192.168.1.100:8080"):
            video = map_movie_info(info, base_url=base_url)
            if video.preview_cover_url:
                assert video.cover_url, (
                    f"preview_cover_url 非空但 cover_url 為空（違反不變式）："
                    f"info={info!r} base_url={base_url!r}"
                )


# ============ feature/metatube-image-proxy：劇照 sample_images 也走同一條路 ============

def test_map_sample_images_proxied_with_base_url():
    """base_url 顯式傳入 → sample_images 逐張改寫成 metatube 代理端點 URL（來源一致性）"""
    from urllib.parse import urlparse, parse_qs
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    assert len(video.sample_images) == 2
    for proxied, original in zip(video.sample_images, info["preview_images"]):
        parsed = urlparse(proxied)
        assert parsed.path == "/v1/images/primary/FANZA/SONE-205"
        qs = parse_qs(parsed.query)
        assert qs["url"] == [original]
        assert qs["ratio"] == ["0"]
        assert qs["quality"] == ["100"]


def test_map_sample_images_raw_without_base_url():
    """未傳 base_url → sample_images 維持原始 URL（行為與修改前一致）"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    video = map_movie_info(info)
    assert video.sample_images == ["https://img.fanza.com/s1.jpg", "https://img.fanza.com/s2.jpg"]


def test_map_sample_images_per_item_fallback_to_raw():
    """base_url 組不出代理（provider 需轉義）→ 逐張回退原始 URL，不整體空白"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["provider"] = "FAN ZA"
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    assert video.sample_images == ["https://img.fanza.com/s1.jpg", "https://img.fanza.com/s2.jpg"]


def test_map_sample_images_proxy_query_encoding_no_pollution():
    """preview image 本身帶 ?token=...&expires=... → 代理 URL 的 url 參數逐字元等於原始
    （CD-113c-13 同款防護延伸到劇照），且 ratio／quality 各恰好一次"""
    from urllib.parse import urlparse, parse_qs
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    original = "https://img.fanza.com/s1.jpg?token=abc&expires=123"
    info["preview_images"] = [original]
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    qs = parse_qs(urlparse(video.sample_images[0]).query)
    assert qs["url"] == [original]
    assert len(qs["ratio"]) == 1
    assert len(qs["quality"]) == 1


def test_map_sample_images_empty_with_base_url():
    """preview_images 缺失 + base_url → sample_images 為 []，不炸"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info.pop("preview_images", None)
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    assert video.sample_images == []


# ============ clean_metatube_summary 邊界測試 ============

def test_clean_fc2_base64_truncated():
    """FC2 含 ≥40 字元 base64 blob → 截斷至 blob 前"""
    from core.metatube.mapper import clean_metatube_summary
    blob = "A" * 45
    raw = f"正常文字{blob}後面"
    result = clean_metatube_summary("FC2", raw)
    assert "A" * 45 not in result
    assert "正常文字" in result


def test_clean_fc2_base64_all_noise():
    """FC2 全是 base64 → 截斷後空 → ''"""
    from core.metatube.mapper import clean_metatube_summary
    raw = "A" * 45
    result = clean_metatube_summary("FC2", raw)
    assert result == ""


def test_clean_fc2_script_tag():
    """FC2 含 <script → 截斷至 <script 前"""
    from core.metatube.mapper import clean_metatube_summary
    raw = "正常文字<script>alert(1)</script>"
    result = clean_metatube_summary("FC2", raw)
    assert result == "正常文字"


def test_clean_fc2_function_marker():
    """FC2 含 function( → 截斷"""
    from core.metatube.mapper import clean_metatube_summary
    raw = "簡介 function(a,b){}"
    result = clean_metatube_summary("FC2", raw)
    assert result == "簡介"


def test_clean_fc2_double_brace():
    """FC2 含 {{ → 截斷"""
    from core.metatube.mapper import clean_metatube_summary
    raw = "內容 {{template}}"
    result = clean_metatube_summary("FC2", raw)
    assert result == "內容"


def test_clean_fc2_overlength():
    """FC2 超長 >500 字（無雜訊）→ 限 500"""
    from core.metatube.mapper import clean_metatube_summary
    # 使用 CJK 字元避免觸發 base64-like regex
    raw = "あ" * 1000
    result = clean_metatube_summary("FC2", raw)
    assert len(result) == 500


def test_clean_fc2_empty():
    """FC2 空字串 → ''"""
    from core.metatube.mapper import clean_metatube_summary
    result = clean_metatube_summary("FC2", "")
    assert result == ""


def test_clean_fc2_no_noise():
    """FC2 無雜訊 → passthrough"""
    from core.metatube.mapper import clean_metatube_summary
    raw = "正常日文簡介"
    result = clean_metatube_summary("FC2", raw)
    assert result == "正常日文簡介"


def test_clean_non_fc2_normal():
    """非 FC2 正常 passthrough"""
    from core.metatube.mapper import clean_metatube_summary
    result = clean_metatube_summary("JavBus", "正常簡介")
    assert result == "正常簡介"


def test_clean_non_fc2_overlength():
    """非 FC2 超長 → 限 500（unicode-safe）"""
    from core.metatube.mapper import clean_metatube_summary
    raw = "あ" * 600
    result = clean_metatube_summary("HEYZO", raw)
    assert len(result) == 500


def test_clean_non_fc2_empty():
    """非 FC2 空 → ''"""
    from core.metatube.mapper import clean_metatube_summary
    result = clean_metatube_summary("DUGA", "")
    assert result == ""


def test_clean_fc2hub_is_fc2_family():
    """fc2hub 是 FC2 系，走 FC2 清理路徑"""
    from core.metatube.mapper import clean_metatube_summary
    raw = "簡介<script>noise</script>"
    result = clean_metatube_summary("fc2hub", raw)
    assert result == "簡介"


def test_clean_fc2ppvdb_is_fc2_family():
    """FC2PPVDB 是 FC2 系，base64 截斷"""
    from core.metatube.mapper import clean_metatube_summary
    blob = "B" * 50 + "=="
    raw = f"FC2PPVDB簡介{blob}"
    result = clean_metatube_summary("FC2PPVDB", raw)
    assert "B" * 50 not in result
    assert "FC2PPVDB簡介" in result


# ============================================================
# Codex PR review P1（2026-08-07）：base_url 的機密不得進 preview URL
# ============================================================

# ⚠️ 參數名不可叫 `base_url`——`pytest-base-url`（pytest-playwright 的依賴）註冊了
# 一個同名的 session-scoped fixture，parametrize 撞名會 ScopeMismatch 整組 ERROR。
@pytest.mark.parametrize("unsafe_base_url,why", [
    ("http://user:password@127.0.0.1:8900", "userinfo（帳號+密碼）"),
    ("https://user:password@example.com", "userinfo，公網 host"),
    ("http://user@127.0.0.1:8900", "只有 username"),
    ("http://127.0.0.1:8900?x=1", "base_url 帶 query"),
    ("http://127.0.0.1:8900#frag", "base_url 帶 fragment"),
])
def test_preview_cover_url_empty_for_unsafe_base_url(unsafe_base_url, why):
    """`validate_metatube_url()` **從不檢查 userinfo**（只看 scheme/hostname/port），
    所以 `https://user:pass@host` 通得過設定。而 preview 欄位會進 `/api/search`
    的 JSON 回應、再被前端當成 `/api/proxy-image?url=...` 真的送出去——帳密會
    落在瀏覽器網址列、devtools 與瀏覽紀錄。

    處置是**回空字串**而不是靜默剝掉帳密：剝掉會讓「預覽打不通」變成難以診斷
    的失敗，而回空字串會讓既有的 `preview_cover_url || cover` fallback 接手。
    真正的連線路徑（`MetatubeHttpClient`）拿到的仍是完整 base_url，反向代理的
    Basic Auth 不受影響（metatube 自己只認 Bearer）。

    query/fragment 一起擋是同一個 guard 順手修掉的功能 bug——字串內插會把路徑
    塞進原本的 query 裡（`http://h:9/?x=1/v1/images/...`），URL 從頭就是壞的。
    """
    from core.metatube.mapper import _build_preview_cover_url

    out = _build_preview_cover_url(unsafe_base_url, "FANZA", "ssis-001", "https://cdn.example/c.jpg")
    assert out == "", f"{why} 的 base_url 必須不產 preview URL，實得：{out!r}"


def test_preview_cover_url_still_built_for_base_url_with_path():
    """不得矯枉過正：反向代理下的 `http://host:9/sub/path` 是**合法**設定，
    必須照常組出 preview URL（裁決 3 的 path 前綴接續行為）。

    沒有這一格，上面那組「全部回空」用 `return ""` 就能造假。
    """
    from core.metatube.mapper import _build_preview_cover_url

    out = _build_preview_cover_url(
        "http://127.0.0.1:8900/metatube", "FANZA", "ssis-001", "https://cdn.example/c.jpg"
    )
    assert out.startswith("http://127.0.0.1:8900/metatube/v1/images/primary/FANZA/ssis-001?")


def test_to_legacy_dict_preview_never_carries_userinfo():
    """回歸鎖：走完整 `map_movie_info()` → `to_legacy_dict()` 序列化鏈，
    確認送給瀏覽器的那個 dict 裡不可能出現帳密。

    鎖在序列化端而不只是 builder 端，因為 P1 的實際傷害發生在「這個 dict 被
    json 出去」那一刻——builder 之後若有人再加一層推導，這支仍然守得住。
    """
    from core.metatube.mapper import map_movie_info

    info = {
        "provider": "FANZA",
        "number": "ssis-001",
        "cover_url": "https://cdn.example/c.jpg",
    }
    video = map_movie_info(info, base_url="http://leakuser:leakpass@127.0.0.1:8900")
    legacy = video.to_legacy_dict()
    assert legacy["preview_cover_url"] == ""
    blob = json.dumps(legacy, ensure_ascii=False)
    for secret in ("leakuser", "leakpass", "@127.0.0.1"):
        assert secret not in blob, f"序列化輸出洩漏 {secret!r}"
