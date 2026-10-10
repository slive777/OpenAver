"""自訂來源測試共用：yaml 樣本目錄與各形狀的最小合成頁（只含 selector 會碰到的元素）。"""

from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "custom_sources"

SINGLE_OG = """<html><head>
<meta property="og:title" content="SONE-205 Sample Title One">
<meta property="og:image" content="https://img.example/sone-205/cover.jpg">
<meta property="og:video:release_date" content="2024-05-25">
<meta property="og:video:duration" content="8967">
</head><body>
<h1>SONE-205 Sample Title One</h1>
<div class="space-y-2">
<a href="/genres/1">GenreA</a><a href="/genres/2">GenreB</a>
<a href="/actresses/1">ActressA</a><a href="/actresses/2">ActressB</a>
</div>
</body></html>"""

SINGLE_OG_MIN = """<html><head>
<meta property="og:title" content="SONE-205 Sample Title Min">
<meta property="og:image" content="https://img.example/min/preview.jpg">
</head><body>
<h5 class="tags"><a class="cat" href="/c/1">TagA</a><a class="cat" href="/c/2">TagB</a></h5>
</body></html>"""

# 兩步：搜尋頁恰有 uc / c 兩個結果連結（測試直接取兩者網址）；側欄連結不在結果選擇器內
TWO_STEP_UC = "https://two-step.example/video/sone-205uc/"
TWO_STEP_C = "https://two-step.example/video/sone-205c/"
TWO_STEP_SEARCH = f"""<html><body class="search-results">
<h3 class="entry-title"><a href="{TWO_STEP_UC}">SONE-205 (uc)</a></h3>
<h3 class="entry-title"><a href="{TWO_STEP_C}">SONE-205 (c)</a></h3>
<div class="sidebar"><a href="https://two-step.example/video/other-999/">OTHER-999</a></div>
</body></html>"""
TWO_STEP_EMPTY = """<html><body class="search-no-results">
<div class="sidebar"><a href="https://two-step.example/video/other-999/">OTHER-999</a></div>
</body></html>"""


def _two_step_detail(upload_date, cover):
    return f"""<html><head>
<script type="application/ld+json">{{"@type":"VideoObject","thumbnailUrl":"{cover}","uploadDate":"{upload_date}"}}</script>
</head><body>
<h1 class="entry-title">SONE-205 (SUB) Sample Title Two</h1>
<div class="tags-items"><a class="tag-item" href="/t/1">TagA</a><a class="tag-item" href="/t/2">TagB</a></div>
</body></html>"""


# a 較舊（2024-06-01），b 較新（2025-12-17）
TWO_STEP_DETAIL_A = _two_step_detail("2024-06-01", "https://img.example/two-step/cover.jpg")
TWO_STEP_DETAIL_B = _two_step_detail("2025-12-17", "https://img.example/two-step/cover.jpg")

FUZZY_HIT = "https://fuzzy.example/post/12345/"
FUZZY_SEARCH = f"""<html><body>
<h3 class="jeg_post_title"><a href="{FUZZY_HIT}">[IPZZ-100] Sample Title Fuzzy</a></h3>
<h3 class="jeg_post_title"><a href="https://fuzzy.example/post/67890/">[IPZZ-999] Unrelated</a></h3>
</body></html>"""
FUZZY_DETAIL = """<html><head>
<meta property="og:image" content="https://fuzzy.example/uploads/IPZZ-100.jpg">
</head><body>
<h1 class="jeg_post_title">[IPZZ-100] Sample Title Fuzzy</h1>
<div class="jeg_post_tags"><a href="/t/1">TagA</a><a href="/t/2">TagB</a></div>
<div class="jeg_meta_category"><a href="/c/1">CategoryA</a></div>
</body></html>"""

TEXT_HIT = "https://text.example/v/2439990"
TEXT_SEARCH = f"""<html><body>
<div class="card-video__title"><a href="{TEXT_HIT}">FC2PPV-2439990 Sample</a></div>
<div class="card-video__title"><a href="https://text.example/v/1111111">FC2PPV-1111111 Unrelated</a></div>
</body></html>"""
TEXT_SEARCH_EMPTY = "<html><body><p>0 results</p></body></html>"
TEXT_DETAIL = """<html><head>
<meta property="og:title" content="FC2PPV-2439990 Sample Title Text">
<meta property="og:image" content="https://img.example/text/preview.jpg">
</head><body>
<div class="content-details__meta"><a href="/t/1">TagA</a><a href="/t/2">TagB</a></div>
</body></html>"""

PAGES = {
    "single-og": SINGLE_OG, "single-og-min": SINGLE_OG_MIN,
    "two-step-search": TWO_STEP_SEARCH, "two-step-detail-a": TWO_STEP_DETAIL_A,
    "two-step-detail-b": TWO_STEP_DETAIL_B, "two-step-empty": TWO_STEP_EMPTY,
    "fuzzy-search": FUZZY_SEARCH, "fuzzy-detail": FUZZY_DETAIL,
    "text-search": TEXT_SEARCH, "text-detail": TEXT_DETAIL, "text-search-empty": TEXT_SEARCH_EMPTY,
}
