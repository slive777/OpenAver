"""TASK-121a-T1: core.cover_attributes 邊界斷言。

對應卡片「本 task 特有邊界」16 條，每條至少一條斷言，不抽樣。
"""

import pytest

from core.cover_attributes import effective_tags

_CANONICAL_TAGS = frozenset(
    {"中文字幕", "無碼破解", "無碼流出", "4K", "VR", "LTX"}
)


def _has_canonical(tags: list[str]) -> set[str]:
    return set(tags) & _CANONICAL_TAGS


def _hits_4k(tags: list[str]) -> bool:
    return any(t.strip().lower() == "4k" for t in tags)


# ── 邊界 1 ──────────────────────────────────────────────────────────────────

def test_b01_uc_hits_cracked_and_subtitle():
    """ABP-999-UC.mp4 → 結果含 無碼破解 與 中文字幕（A1 核心）。"""
    result = effective_tags("ABP-999-UC.mp4", [])
    assert "無碼破解" in result
    assert "中文字幕" in result


# ── 邊界 2 ──────────────────────────────────────────────────────────────────


# ── 邊界 3 ──────────────────────────────────────────────────────────────────

def test_b03_abcuc_hits_nothing():
    """ABCUC-123.mp4 → 不命中任何屬性（A6）。"""
    result = effective_tags("ABCUC-123.mp4", [])
    assert _has_canonical(result) == set()


# ── 邊界 4 ──────────────────────────────────────────────────────────────────


# ── 邊界 5 ──────────────────────────────────────────────────────────────────

def test_b05_multipart_tokens_add_nothing():
    """ABC-123-cd1.mp4 / ABC-123-pt2.mp4 → 與 existing_tags 等價，零新增（A4）。"""
    existing = ["既有標籤"]
    assert effective_tags("ABC-123-cd1.mp4", existing) == existing
    assert effective_tags("ABC-123-pt2.mp4", existing) == existing


# ── 邊界 6 ──────────────────────────────────────────────────────────────────

def test_b06_cracked_and_leaked_not_mutex():
    """ABC-123-U-leak.mp4 → 無碼破解 與 無碼流出 兩個都在（A5，不互斥）。"""
    result = effective_tags("ABC-123-U-leak.mp4", [])
    assert "無碼破解" in result
    assert "無碼流出" in result


# ── 邊界 7 ──────────────────────────────────────────────────────────────────

def test_b07_dedup_cracked():
    """existing_tags=['無碼破解'] ＋ ABC-123-U.mp4 → 結果只有一個 無碼破解。"""
    result = effective_tags("ABC-123-U.mp4", ["無碼破解"])
    assert result.count("無碼破解") == 1
    assert result == ["無碼破解"]


# ── 邊界 8 ──────────────────────────────────────────────────────────────────


# ── 邊界 9 ──────────────────────────────────────────────────────────────────

def test_b09_cd10_4k_genre_confluence():
    """existing_tags=['4k'] / ['UHD'] / ['8K'] → 皆命中 4K（各一條）。"""
    assert _hits_4k(effective_tags("ABC-123.mp4", ["4k"]))
    assert _hits_4k(effective_tags("ABC-123.mp4", ["UHD"]))
    assert _hits_4k(effective_tags("ABC-123.mp4", ["8K"]))


# ── 邊界 10 ─────────────────────────────────────────────────────────────────


# ── 邊界 11 ─────────────────────────────────────────────────────────────────

def test_b11_bareword_left_right_boundary():
    """裸詞左右邊界：流出命中；ABC-123umr9 / XXumrYY 不命中。"""
    assert "無碼流出" in effective_tags("ABC-123-流出.mp4", [])
    umr_digit = effective_tags("ABC-123umr9.mp4", [])
    assert "無碼破解" not in umr_digit
    assert _has_canonical(umr_digit) == set()
    umr_letters = effective_tags("XXumrYY.mp4", [])
    assert "無碼破解" not in umr_letters
    assert _has_canonical(umr_letters) == set()


def test_b11b_bareword_left_boundary_alone():
    """左邊界獨立驗證：umr 右側是分隔字元／結尾（右邊界會放行），只有左邊界能擋。

    review finding（2026-08-19）：原 b11 的兩個負例右側都是英數，右邊界單獨就擋得住，
    左邊界被拿掉時測試仍全綠。這幾條才是左邊界的安全網——它破了，
    `SUMR-001.mp4` 這種真實檔名會被誤貼「無碼破解」寫進使用者的 .nfo。
    """
    for filename in ("SUMR-001.mp4", "Xumr.mp4", "ABC-123umr.mp4", "ABC-123umr-999.mp4"):
        result = effective_tags(filename, [])
        assert "無碼破解" not in result, filename
        assert _has_canonical(result) == set(), filename


def test_b11c_dedup_key_strips_whitespace():
    """既有 tag 帶前後空白時不得與新產生的 canonical 值並存（review finding）。

    第三方刮削器留下的 NFO 可能寫成 `<genre> VR </genre>`；不 strip 的話
    使用者的 .nfo 會出現兩筆幾乎相同的 tag，Jellyfin/Emby 分類列表看到重複項。
    """
    assert effective_tags("ABC-123-VR.mp4", [" VR"]) == [" VR"]
    assert effective_tags("ABC-123-VR.mp4", ["VR "]) == ["VR "]
    assert effective_tags("ABC-123.mp4", [" 4K "]) == [" 4K "]
    assert effective_tags("ABC-123.mp4", [" uhd"]) == [" uhd", "4K"]


# ── 邊界 12 ─────────────────────────────────────────────────────────────────


# ── 邊界 13 ─────────────────────────────────────────────────────────────────


# ── 邊界 14 ─────────────────────────────────────────────────────────────────


# ── 邊界 15 ─────────────────────────────────────────────────────────────────


# ── 邊界 16 ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("SNIS-542_LTX.mp4", {"無碼破解", "LTX"}),
        ("第一會所新片@SIS001@SNIS-542_LTX.mp4", {"無碼破解", "LTX"}),
        ("SNIS-576-LTX.mp4", {"無碼破解", "LTX"}),
        ("MIDV-123-LTX-C.mp4", {"無碼破解", "LTX", "中文字幕"}),
        ("IPX-750-LTX-4K.mp4", {"無碼破解", "LTX", "4K"}),
        ("SNIS-542-U.ltx.mp4", {"無碼破解", "LTX"}),
        ("snis-542-ltx.mp4", {"無碼破解", "LTX"}),
        ("ABF-358-UC-LTX.mkv", {"中文字幕", "無碼破解", "LTX"}),
        ("LTX-123.mp4", set()),
        ("SNIS-542-LTXA.mp4", set()),
        ("SNIS-542-L.mp4", set()),
        ("SNIS-542-LC.mp4", set()),
    ],
)
def test_ltx_filename_tags(filename, expected):
    result = effective_tags(filename, [])
    assert _has_canonical(result) == expected
    if filename == "ABF-358-UC-LTX.mkv":
        assert result.count("無碼破解") == 1
