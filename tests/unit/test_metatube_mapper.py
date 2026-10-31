"""test_metatube_mapper.py - metatube mapper + clean_metatube_summary 邊界測試"""

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


def test_map_full_info_source():
    """provider → source = "metatube:FANZA" """
    from core.metatube.mapper import map_movie_info
    video = map_movie_info(_full_info())
    assert video.source == "metatube:FANZA"


def test_map_actors_with_empty_string():
    """actors 含空字串 → 過濾，不觸發 Actress min_length=1 ValidationError"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["actors"] = ["Alice", "", "Bob"]
    video = map_movie_info(info)
    assert video.actresses == [Actress(name="Alice"), Actress(name="Bob")]


def test_map_release_date_null():
    """release_date=None（JSON null）→ date="" 不炸（`or ""` 攔 None，不走 None.split）"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["release_date"] = None
    video = map_movie_info(info)
    assert video.date == ""


# ============ TASK-113c-T3b: preview_cover_url（CD-113c-4／12／13） ============

def test_map_movie_info_binds_preview_cover_url_from_base_url():
    """base_url 顯式傳入 → preview_cover_url 出生時就綁定（DoD-1）

    CD-126-1：cover_url 恆為原始網址；代理 URL 只住在 preview_cover_url。
    兩者皆非空時必須不相等（否則 shouldFallbackToCover 永遠為偽）。
    """
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    assert video.preview_cover_url != ""
    assert video.preview_cover_url.startswith("http://192.168.1.100:8080/v1/images/primary/FANZA/SONE-205?")
    assert video.cover_url == info["cover_url"]
    assert video.cover_url != video.preview_cover_url


def test_preview_cover_url_empty_when_cover_url_missing():
    """cover_url 本身空 → 即使有 base_url，preview_cover_url 仍為空（沒有可預覽的東西）"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["cover_url"] = ""
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    assert video.preview_cover_url == ""


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


def test_preview_cover_url_empty_when_provider_needs_escaping():
    """provider 含 quote(safe="") 需要轉義的字元（此處用空白）→ 回空字串，
    不產生一個上線會被 T3a `_SAFE_PATH_SEGMENT` 擋下的 URL（設計問題 3／DoD-8③）"""
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["provider"] = "FAN ZA"
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    assert video.preview_cover_url == ""


# ============ feature/metatube-image-proxy：劇照平行欄位 preview_sample_images ============

def test_map_sample_images_proxied_with_base_url():
    """邊界 1：有 base_url、provider/number 正常、3 張劇照 →
    sample_images 全原始；preview_sample_images 全代理；等長同序。"""
    from urllib.parse import urlparse, parse_qs
    from core.metatube.mapper import map_movie_info
    info = _full_info()
    info["preview_images"] = [
        "https://img.fanza.com/s1.jpg",
        "https://img.fanza.com/s2.jpg",
        "https://img.fanza.com/s3.jpg",
    ]
    video = map_movie_info(info, base_url="http://192.168.1.100:8080")
    assert video.sample_images == info["preview_images"]
    assert len(video.preview_sample_images) == len(video.sample_images) == 3
    for proxied, original in zip(video.preview_sample_images, info["preview_images"], strict=True):
        parsed = urlparse(proxied)
        assert parsed.path == "/v1/images/primary/FANZA/SONE-205"
        qs = parse_qs(parsed.query)
        assert qs["url"] == [original]
        assert qs["ratio"] == ["0"]
        assert qs["quality"] == ["100"]


# ============ clean_metatube_summary 邊界測試 ============

def test_clean_fc2_base64_truncated():
    """FC2 含 ≥40 字元 base64 blob → 截斷至 blob 前"""
    from core.metatube.mapper import clean_metatube_summary
    blob = "A" * 45
    raw = f"正常文字{blob}後面"
    result = clean_metatube_summary("FC2", raw)
    assert "A" * 45 not in result
    assert "正常文字" in result


def test_clean_fc2_script_tag():
    """FC2 含 <script → 截斷至 <script 前"""
    from core.metatube.mapper import clean_metatube_summary
    raw = "正常文字<script>alert(1)</script>"
    result = clean_metatube_summary("FC2", raw)
    assert result == "正常文字"


# ============ TASK-187b-T1: 簡介截斷（truncate_summary） ============

@pytest.mark.parametrize(
    "text,expected_suffix,expected_len,check_exact",
    [
        # 超長且窗口內有「。」（三千字輸入）
        ("あ" * 100 + "。" + "い" * 2900, "。…", None, None),
        # 窗口內最後一個句末標點為「！」，且更早還有「。」
        ("あ" * 100 + "。" + "い" * 100 + "！" + "う" * 400, "！…", None, None),
        # 窗口內最後標點為「？」
        ("あ" * 100 + "？" + "い" * 500, "？…", None, None),
        # 無句末標點 600 字硬截
        ("あ" * 600, "…", 500, "あ" * 499 + "…"),
        # 句末標點「！」恰在第 500 字（索引 499），落在窗口外，截在更早的「。」
        ("あ" * 200 + "。" + "い" * 298 + "！" + "う" * 100, "。…", None, None),
    ],
)
def test_truncate_summary_over_limit(text, expected_suffix, expected_len, check_exact):
    """超長輸入截在句末標點或硬截，長度不超過 limit"""
    from core.metatube.mapper import clean_metatube_summary, truncate_summary

    res = truncate_summary(text)
    assert len(res) <= 500
    assert res.endswith(expected_suffix)
    if expected_len is not None:
        assert len(res) == expected_len
    if check_exact is not None:
        assert res == check_exact

    # 端到端：經 clean_metatube_summary（非 FC2 provider）同結果
    assert clean_metatube_summary("FANZA", text) == res


@pytest.mark.parametrize(
    "text",
    [
        "あ" * 500,
        "あ" * 499 + "。",
        "短いあらすじです。",
        "",
    ],
)
def test_truncate_summary_within_limit_untouched(text):
    """上限內的完整簡介不被改寫、不加「…」"""
    from core.metatube.mapper import clean_metatube_summary, truncate_summary

    res = truncate_summary(text)
    assert res == text
    assert not res.endswith("…")
    assert clean_metatube_summary("FANZA", text) == res


# ============================================================
# Codex PR review P1（2026-08-07）：base_url 的機密不得進 preview URL
# ============================================================

# ⚠️ 參數名不可叫 `base_url`——`pytest-base-url`（pytest-playwright 的依賴）註冊了
# 一個同名的 session-scoped fixture，parametrize 撞名會 ScopeMismatch 整組 ERROR。
@pytest.mark.parametrize("unsafe_base_url,why", [
    ("http://user:password@127.0.0.1:8900", "userinfo（帳號+密碼）"),
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


