"""
test_javbus_smoke.py - JavBus 爬蟲真實連線 Smoke Tests

Phase 35 Task 8a: 驗證重寫後 JavBusScraper 所有新欄位

執行方式：
    pytest tests/smoke/test_javbus_smoke.py -v -m smoke

注意：
- 只用於本地手動測試，不進 CI（避免被 ban）
- 無法連線時自動 skip，不算失敗
"""

import re

import pytest

from core.scrapers import JavBusScraper
from core.scrapers.models import Video

pytestmark = pytest.mark.smoke

# ========== 測試番號 ==========

# JUR-688：有 series（ハプニングバーNTR），適合驗 series 非空
NUMBER_WITH_SERIES = "JUR-688"

# SNOS-143：series 為空，適合驗 series 可為空
NUMBER_WITHOUT_SERIES = "SNOS-143"

# 多語言測試用番號（兩個都可，用 SNOS-143）
NUMBER_MULTILANG = "SNOS-143"


# ========== 精準搜尋測試 ==========

class TestJavBusSmokeSearch:
    """精準搜尋驗證所有新欄位"""

    @pytest.fixture
    def scraper(self):
        return JavBusScraper(lang="zh-tw")

    def test_search_all_fields_with_series(self, scraper):
        """JUR-688：驗證所有欄位非空（包含 series）"""
        try:
            video = scraper.search(NUMBER_WITH_SERIES)
        except Exception as e:
            pytest.skip(f"JavBus 連線問題: {e}")
        if video is None:
            pytest.skip("JavBus 無法連線（可能被網站封鎖或網路問題）")

        assert isinstance(video, Video)

        # 基本識別欄位
        assert video.number == NUMBER_WITH_SERIES, f"番號不符: {video.number!r}"
        assert isinstance(video.title, str) and len(video.title) > 0, "title 為空"
        assert video.source == "javbus", f"source 不符: {video.source!r}"

        # URL 欄位
        assert video.cover_url.startswith("http"), f"cover_url 格式錯誤: {video.cover_url!r}"
        assert video.detail_url.startswith("http"), f"detail_url 格式錯誤: {video.detail_url!r}"

        # 日期格式 YYYY-MM-DD
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", video.date), \
            f"date 格式錯誤: {video.date!r}"

        # 片商
        assert isinstance(video.maker, str) and len(video.maker) > 0, "maker 為空"

        # tags
        assert isinstance(video.tags, list) and len(video.tags) > 0, "tags 為空列表"
        assert all(isinstance(t, str) for t in video.tags), "tags 包含非 str 元素"

        # actresses（可能為空，但類型必須正確）
        assert isinstance(video.actresses, list), "actresses 不是 list"

        # 新欄位：director
        assert isinstance(video.director, str) and len(video.director) > 0, \
            "director 為空（JUR-688 應有導演資訊）"

        # 新欄位：duration
        assert isinstance(video.duration, int) and video.duration > 0, \
            f"duration 不是正整數: {video.duration!r}"

        # 新欄位：label
        assert isinstance(video.label, str) and len(video.label) > 0, \
            "label 為空（JUR-688 應有發行商）"

        # 新欄位：series（JUR-688 應有 series）
        assert isinstance(video.series, str), "series 不是 str"
        assert len(video.series) > 0, \
            f"series 為空（JUR-688 應有 series，實際: {video.series!r}）"

        # 新欄位：sample_images
        assert isinstance(video.sample_images, list) and len(video.sample_images) > 0, \
            "sample_images 為空列表（JUR-688 應有樣品圖）"
        assert all(url.startswith("http") for url in video.sample_images), \
            "sample_images 包含非 http URL"

    def test_search_series_can_be_empty(self, scraper):
        """SNOS-143：series 可為空字串（不強制非空）"""
        try:
            video = scraper.search(NUMBER_WITHOUT_SERIES)
        except Exception as e:
            pytest.skip(f"JavBus 連線問題: {e}")
        if video is None:
            pytest.skip("JavBus 無法連線（可能被網站封鎖或網路問題）")

        assert isinstance(video, Video)
        assert video.number == NUMBER_WITHOUT_SERIES, f"番號不符: {video.number!r}"
        assert video.source == "javbus"

        # series 可為空，但必須是 str
        assert isinstance(video.series, str), \
            f"series 應為 str，實際型別: {type(video.series).__name__}"

        # 其他必要欄位仍應正常
        assert video.cover_url.startswith("http"), f"cover_url 格式錯誤: {video.cover_url!r}"
        assert isinstance(video.duration, int) and video.duration > 0, \
            f"duration 不是正整數: {video.duration!r}"
        assert isinstance(video.sample_images, list) and len(video.sample_images) > 0, \
            "sample_images 為空列表（SNOS-143 應有樣品圖）"


# ========== 模糊搜尋測試 ==========

class TestJavBusSmokeKeyword:
    """模糊搜尋：search_by_keyword + get_ids_from_search"""

    @pytest.fixture
    def scraper(self):
        return JavBusScraper(lang="zh-tw")

    def test_search_by_keyword_returns_videos(self, scraper):
        """search_by_keyword 回傳 Video 列表"""
        results = scraper.search_by_keyword("三上悠亞", limit=5)

        if not results:
            pytest.skip("search_by_keyword 無法連線或回傳空列表（可能被網站封鎖）")

        assert isinstance(results, list)
        assert len(results) <= 5, f"超過 limit=5，實際: {len(results)}"

        for v in results:
            assert isinstance(v, Video), f"結果包含非 Video 物件: {type(v)}"
            assert v.number, "Video.number 為空"
            assert v.source == "javbus", f"source 不符: {v.source!r}"

    def test_search_by_keyword_video_has_fields(self, scraper):
        """search_by_keyword 回傳的 Video 包含基本欄位"""
        results = scraper.search_by_keyword("SONE", limit=3)

        if not results:
            pytest.skip("search_by_keyword 無法連線或回傳空列表（可能被網站封鎖）")

        first = results[0]
        assert isinstance(first.title, str) and len(first.title) > 0, \
            "第一筆結果 title 為空"
        assert first.cover_url.startswith("http"), \
            f"第一筆結果 cover_url 格式錯誤: {first.cover_url!r}"

    def test_get_ids_from_search_returns_list(self, scraper):
        """get_ids_from_search 回傳番號字串列表"""
        ids = scraper.get_ids_from_search("SONE")

        if not ids:
            pytest.skip("get_ids_from_search 無法連線或回傳空列表（可能被網站封鎖）")

        assert isinstance(ids, list), f"回傳型別應為 list，實際: {type(ids)}"
        assert all(isinstance(i, str) for i in ids), "ids 包含非 str 元素"
        assert all(len(i) > 0 for i in ids), "ids 包含空字串"


# ========== 多語言測試 ==========

class TestJavBusSmokeMultilang:
    """同一番號 zh-tw vs ja tags 應因語言而異"""

    def test_zh_tw_vs_ja_tags_differ(self):
        """zh-tw 和 ja 的 tags 文字內容應不同（不同語言）"""
        scraper_tw = JavBusScraper(lang="zh-tw")
        scraper_ja = JavBusScraper(lang="ja")

        try:
            video_tw = scraper_tw.search(NUMBER_MULTILANG)
            video_ja = scraper_ja.search(NUMBER_MULTILANG)
        except Exception as e:
            pytest.skip(f"JavBus 連線問題: {e}")

        if video_tw is None or video_ja is None:
            pytest.skip(
                "JavBus 無法連線（zh-tw 或 ja 任一失敗），跳過多語言測試"
            )

        assert isinstance(video_tw.tags, list) and len(video_tw.tags) > 0, \
            "zh-tw tags 為空列表"
        assert isinstance(video_ja.tags, list) and len(video_ja.tags) > 0, \
            "ja tags 為空列表"

        # Tags 文字內容應不同（不同語言的翻譯）
        assert video_tw.tags != video_ja.tags, \
            f"zh-tw 和 ja 的 tags 應因語言而異\nzh-tw: {video_tw.tags}\nja: {video_ja.tags}"

    def test_zh_tw_vs_ja_number_consistent(self):
        """不同語言搜尋同一番號，number 應一致"""
        scraper_tw = JavBusScraper(lang="zh-tw")
        scraper_ja = JavBusScraper(lang="ja")

        try:
            video_tw = scraper_tw.search(NUMBER_MULTILANG)
            video_ja = scraper_ja.search(NUMBER_MULTILANG)
        except Exception as e:
            pytest.skip(f"JavBus 連線問題: {e}")

        if video_tw is None or video_ja is None:
            pytest.skip(
                "JavBus 無法連線（zh-tw 或 ja 任一失敗），跳過多語言一致性測試"
            )

        assert video_tw.number == video_ja.number == NUMBER_MULTILANG, \
            f"番號不一致: tw={video_tw.number!r}, ja={video_ja.number!r}"
        assert video_tw.source == video_ja.source == "javbus"
