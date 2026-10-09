"""tests/integration/test_scrape_single_source_routing.py — scrape-single 來源分流契約（TASK-147d-T1）。

CD-147d-7：無 metadata 時依 is_number_format 守門分流 smart_search / search_jav。
"""
from core.scraper import extract_number, is_number_format
from core.scrapers.utils import resolve_route_target


# CD-147d-2 列出的 27 個 CASES（I-147d-1）
_INVARIANT_CASES = [
    "SONE-205",
    "sone-205",
    " SONE-205 ",
    "SONE-103-UC",
    "SONE-103_UC",
    "200GANA-3360",
    "259LUXU-1234",
    "7IPZ-154",
    "FC2-PPV-1234567",
    "FC2-1234567",
    "HEYZO-1234",
    "T28-103",
    "3DSVR-1774",
    "34ID-017",
    "MIDA-649",
    "n1234",
    "ABP-123-C",
    "ABC-123.mp4",
    "[ABC-123] title",
    "1pondo-123456_001",
    "carib-123456-789",
    "fc2 12",
    "深田えいみ",
    "2024",
    "IPZZ-03",
    "SONE",
    "",
]

_REAL_FILENAMES = [
    "ABP-123-C.mp4",
    "[JavBus] SSIS-001 中文字幕.mp4",
    "hhd800.com@MIDA-649.mp4",
    "IPZZ-859 4K.mp4",
    "FC2-PPV-1234567.mp4",
    "carib-123456-789.mp4",
]


class TestScrapeSingleSourceRouting:
    """端點 mock-and-assert-call：合法番號走 smart_search、非法格式走 search_jav。"""

    def test_legal_number_calls_smart_search_not_search_jav(self, client, mocker):
        """邊界 1：合法番號 + 無 metadata → smart_search 一次，search_jav 不呼叫。

        pre-merge SA-pre-9 P3-2：無碼模式釘死 False（不讀本機 web/config.json）。
        原本 `expected_uncensored = is_uncensored_mode_effective(load_config())`
        與生產碼同源 ⇒ `assert kwargs[...] is expected_uncensored` 恆真、零鑑別力；
        True 那一側由 :132 / :156 兩條各自釘死覆蓋。
        """
        mocker.patch(
            "web.routers.scraper.is_uncensored_mode_effective", return_value=False
        )

        mock_smart = mocker.patch(
            "web.routers.scraper.smart_search",
            return_value=[{"number": "SONE-205", "title": "Test"}],
        )
        mock_search = mocker.patch("web.routers.scraper.search_jav")
        mocker.patch(
            "web.routers.scraper.organize_file",
            return_value={"duplicate": True, "duplicate_target": "x.mp4"},
        )

        resp = client.post(
            "/api/scrape-single",
            json={"file_path": "/dummy/SONE-205.mp4", "number": "SONE-205"},
        )
        assert resp.status_code == 200

        mock_smart.assert_called_once()
        kwargs = mock_smart.call_args.kwargs
        assert kwargs.get("uncensored_mode") is False
        assert mock_smart.call_args.args[0] == "SONE-205"
        mock_search.assert_not_called()

    def test_legal_number_smart_search_empty_returns_not_found(self, client, mocker):
        """邊界 2：smart_search 回 [] → 同一句「找不到」錯誤。"""
        mocker.patch(
            "web.routers.scraper.is_uncensored_mode_effective", return_value=False
        )
        mocker.patch("web.routers.scraper.smart_search", return_value=[])
        mocker.patch("web.routers.scraper.search_jav")

        resp = client.post(
            "/api/scrape-single",
            json={"file_path": "/dummy/SONE-205.mp4", "number": "SONE-205"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"success": False, "error": "找不到 SONE-205 的資料"}

    def test_illegal_format_calls_search_jav_not_smart_search(self, client, mocker):
        """邊界 3：非番號格式 → search_jav 被呼叫，smart_search 不呼叫。"""
        # pre-merge SA-pre-9 P3-2：無碼模式開著時非法格式也走 smart_search
        # （Codex 二次審核 P2 的修正），不釘死的話 owner 在設定頁打開無碼模式，
        # 這條與下面邊界 4 在本機就會紅——假紅。
        mocker.patch(
            "web.routers.scraper.is_uncensored_mode_effective", return_value=False
        )

        mock_smart = mocker.patch("web.routers.scraper.smart_search")
        mock_search = mocker.patch(
            "web.routers.scraper.search_jav",
            return_value={"number": "深田えいみ", "title": "Test"},
        )
        mocker.patch(
            "web.routers.scraper.organize_file",
            return_value={"duplicate": True, "duplicate_target": "x.mp4"},
        )

        resp = client.post(
            "/api/scrape-single",
            json={"file_path": "/dummy/actress.mp4", "number": "深田えいみ"},
        )
        assert resp.status_code == 200

        mock_search.assert_called_once_with("深田えいみ")
        mock_smart.assert_not_called()

    def test_illegal_format_search_jav_none_returns_not_found(self, client, mocker):
        """邊界 4：search_jav 回 None → 同一句「找不到」錯誤。"""
        mocker.patch(
            "web.routers.scraper.is_uncensored_mode_effective", return_value=False
        )
        mocker.patch("web.routers.scraper.smart_search")
        mocker.patch("web.routers.scraper.search_jav", return_value=None)

        resp = client.post(
            "/api/scrape-single",
            json={"file_path": "/dummy/actress.mp4", "number": "深田えいみ"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"success": False, "error": "找不到 深田えいみ 的資料"}

    def test_uncensored_mode_passed_through_to_smart_search(self, client, mocker):
        """邊界 5：is_uncensored_mode_effective 回 True → smart_search 收到 True。"""
        mocker.patch(
            "web.routers.scraper.is_uncensored_mode_effective",
            return_value=True,
        )
        mock_smart = mocker.patch(
            "web.routers.scraper.smart_search",
            return_value=[{"number": "SONE-205", "title": "Test"}],
        )
        mocker.patch("web.routers.scraper.search_jav")
        mocker.patch(
            "web.routers.scraper.organize_file",
            return_value={"duplicate": True, "duplicate_target": "x.mp4"},
        )

        resp = client.post(
            "/api/scrape-single",
            json={"file_path": "/dummy/SONE-205.mp4", "number": "SONE-205"},
        )
        assert resp.status_code == 200
        mock_smart.assert_called_once()
        assert mock_smart.call_args.kwargs.get("uncensored_mode") is True

    def test_nonstrict_number_with_uncensored_mode_calls_smart_search(
        self, client, mocker
    ):
        """non-strict 番號（FC2-53）＋無碼模式開 → smart_search，不走 search_jav。"""
        mocker.patch(
            "web.routers.scraper.is_uncensored_mode_effective",
            return_value=True,
        )
        mock_smart = mocker.patch(
            "web.routers.scraper.smart_search",
            return_value=[{"number": "FC2-53", "title": "Test"}],
        )
        mock_search = mocker.patch("web.routers.scraper.search_jav")
        mocker.patch(
            "web.routers.scraper.organize_file",
            return_value={"duplicate": True, "duplicate_target": "x.mp4"},
        )

        resp = client.post(
            "/api/scrape-single",
            json={"file_path": "/dummy/FC2-53.mp4", "number": "FC2-53"},
        )
        assert resp.status_code == 200
        mock_smart.assert_called_once()
        assert mock_smart.call_args.kwargs.get("uncensored_mode") is True
        assert mock_smart.call_args.args[0] == "FC2-53"
        mock_search.assert_not_called()

    def test_metadata_provided_skips_both_search_functions(self, client, mocker):
        """邊界 6：帶 metadata → smart_search / search_jav 皆不呼叫。"""
        mock_smart = mocker.patch("web.routers.scraper.smart_search")
        mock_search = mocker.patch("web.routers.scraper.search_jav")
        mocker.patch(
            "web.routers.scraper.organize_file",
            return_value={"duplicate": True, "duplicate_target": "x.mp4"},
        )

        resp = client.post(
            "/api/scrape-single",
            json={
                "file_path": "/dummy/SONE-205.mp4",
                "number": "SONE-205",
                "metadata": {"number": "SONE-205", "title": "Provided"},
            },
        )
        assert resp.status_code == 200
        mock_smart.assert_not_called()
        mock_search.assert_not_called()


class TestNumberFormatInvariant:
    """純函式：I-147d-1 與 §D 主場景。"""

    def test_invariant_number_format_survives_route_target_resolution(self):
        """邊界 7：I-147d-1 — is_number_format(raw) ⟹ is_number_format(resolve_route_target(raw))。"""
        assert len(_INVARIANT_CASES) == 27
        for raw in _INVARIANT_CASES:
            assert not (
                is_number_format(raw)
                and not is_number_format(resolve_route_target(raw))
            ), f"I-147d-1 violated for {raw!r}"

    def test_real_filenames_extract_number_passes_gate(self):
        """邊界 8：真實檔名 → extract_number → 守門通過（至少 3 個）。"""
        passed = []
        for filename in _REAL_FILENAMES:
            number = extract_number(filename)
            if number and is_number_format(number):
                passed.append((filename, number))
        assert len(passed) >= 3, f"expected >=3 gate passes, got {passed}"
