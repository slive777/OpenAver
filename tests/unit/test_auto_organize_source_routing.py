"""tests/unit/test_auto_organize_source_routing.py — 定時整理來源分流契約（TASK-147d-T4）。

CD-147d-8：run_one_round 依 is_number_format 守門分流 smart_search / search_jav，
與 scrape_single（T1）逐字同形。
"""
import pytest

from core.auto_organize import run_one_round
from core.database.connection import init_db


# ---------------------------------------------------------------------------
# 共用 fixture / helper（照抄 tests/unit/test_auto_organize.py）
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """把 organize_failures 用到的預設 db_path 換成 tmp db，避免污染真實 output/openaver.db。"""
    db_path = tmp_path / "test_auto_organize.db"
    init_db(db_path)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)
    return db_path


def make_config(fav_dir, translate_enabled=False, path_mappings=None, directories=None,
                locale=None):
    config = {
        "search": {"favorite_folder": str(fav_dir)},
        "scraper": {"video_extensions": [".mp4"]},
        "gallery": {
            "min_size_mb": 0,
            "path_mappings": path_mappings or {},
            "directories": directories or [],
        },
        "translate": {"enabled": translate_enabled},
    }
    if locale is not None:
        config["general"] = {"locale": locale}
    return config


def write_video(fav_dir, name, size=1024):
    p = fav_dir / name
    p.write_bytes(b"x" * size)
    return p


def default_organize_success(cover_path="/cover/x.jpg"):
    return {
        "success": True,
        "original_path": None,
        "new_folder": "/organized/x",
        "new_filename": "x.mp4",
        "cover_path": cover_path,
        "nfo_path": "/organized/x/x.nfo",
        "error": None,
        "used_fallbacks": [],
    }


class TestAutoOrganizeSourceRouting:
    """run_one_round：合法番號走 smart_search、非合法格式走 search_jav。"""

    def test_strict_number_calls_smart_search_not_search_jav(
        self, tmp_path, isolated_db, mocker
    ):
        """邊界 1：合法番號格式 → smart_search 一次，search_jav 不呼叫。"""
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "dummy.mp4")
        config = make_config(fav)
        # 不設 uncensored_mode_enabled（預設 False），單獨證明 strict 半邊

        mocker.patch("core.auto_organize.extract_number", return_value="SONE-205")
        mock_smart = mocker.patch("core.auto_organize.smart_search", return_value=[])
        mock_search = mocker.patch("core.auto_organize.search_jav")
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        run_one_round(config)

        mock_smart.assert_called_once()
        kwargs = mock_smart.call_args.kwargs
        assert kwargs.get("uncensored_mode") is False
        assert mock_smart.call_args.args[0] == "SONE-205"
        mock_search.assert_not_called()

    def test_nonstrict_number_calls_search_jav_not_smart_search(
        self, tmp_path, isolated_db, mocker
    ):
        """邊界 2：非合法番號格式 → search_jav 一次，smart_search 不呼叫。"""
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "dummy.mp4")
        config = make_config(fav)

        mocker.patch("core.auto_organize.extract_number", return_value="FC2-53")
        mock_smart = mocker.patch("core.auto_organize.smart_search")
        mock_search = mocker.patch(
            "core.auto_organize.search_jav",
            return_value=None,
        )
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        run_one_round(config)

        mock_search.assert_called_once_with("FC2-53")
        mock_smart.assert_not_called()

    def test_nonstrict_number_search_jav_none_records_not_found(
        self, tmp_path, isolated_db, mocker
    ):
        """邊界 3：search_jav 回 None → failed 含番號、newly_recorded == 1。"""
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "dummy.mp4")
        config = make_config(fav)

        mocker.patch("core.auto_organize.extract_number", return_value="FC2-53")
        mocker.patch("core.auto_organize.smart_search")
        mocker.patch("core.auto_organize.search_jav", return_value=None)
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        result = run_one_round(config)

        assert "FC2-53" in result["failed"]
        assert result["newly_recorded"] == 1

    def test_nonstrict_number_search_jav_found_still_organizes(
        self, tmp_path, isolated_db, mocker
    ):
        """邊界 4：search_jav 有結果 → results=[_r] 包裝正確，仍走 organize。"""
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "dummy.mp4")
        config = make_config(fav)

        mocker.patch("core.auto_organize.extract_number", return_value="T28-75")
        mocker.patch("core.auto_organize.smart_search")
        mocker.patch(
            "core.auto_organize.search_jav",
            return_value={"number": "T28-75", "title": "t", "actors": []},
        )
        mocker.patch(
            "core.auto_organize.organize_file",
            return_value=default_organize_success(),
        )
        mocker.patch("core.auto_organize.try_inflow_upsert", return_value="not_linked")
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        result = run_one_round(config)

        assert "T28-75" in result["added"]

    def test_uncensored_mode_nonstrict_still_calls_smart_search(
        self, tmp_path, isolated_db, mocker
    ):
        """回歸鎖：無碼模式＋非合法番號 → 仍走 smart_search 白名單精確分支。

        smart_search(uncensored_mode=True) 在模糊判斷之前就 return，本來沒有模糊風險；
        若誤退回 search_jav(source='auto') 會把來源池放寬成全部 enabled 來源。
        """
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "dummy.mp4")
        config = make_config(fav)
        config["search"]["uncensored_mode_enabled"] = True

        mocker.patch("core.auto_organize.extract_number", return_value="FC2-53")
        mock_smart = mocker.patch("core.auto_organize.smart_search", return_value=[])
        mock_search = mocker.patch("core.auto_organize.search_jav")
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        run_one_round(config)

        mock_smart.assert_called_once()
        assert mock_smart.call_args.kwargs.get("uncensored_mode") is True
        assert mock_smart.call_args.args[0] == "FC2-53"
        mock_search.assert_not_called()

    def test_uncensored_mode_strict_still_calls_smart_search(
        self, tmp_path, isolated_db, mocker
    ):
        """無碼模式＋合法番號 → 仍走 smart_search（True 半邊未被弄壞）。"""
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "dummy.mp4")
        config = make_config(fav)
        config["search"]["uncensored_mode_enabled"] = True

        mocker.patch("core.auto_organize.extract_number", return_value="SONE-205")
        mock_smart = mocker.patch("core.auto_organize.smart_search", return_value=[])
        mock_search = mocker.patch("core.auto_organize.search_jav")
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        run_one_round(config)

        mock_smart.assert_called_once()
        assert mock_smart.call_args.kwargs.get("uncensored_mode") is True
        assert mock_smart.call_args.args[0] == "SONE-205"
        mock_search.assert_not_called()


def test_guard_functions_agree_across_modules():
    """哨兵：兩邊 import 的是同一個 is_number_format 函式物件（任一端改綁別的函式就紅）。

    這條不是 I-147d-2。I-147d-2（兩條入庫路徑對同一 number 選到同一個上游函式）
    由兩邊各自的 mock-and-assert-call 測試守住。本測試只防「未來有人把某一邊
    改成自己重新定義的判斷式」——兩邊若仍指向 core.scraper.is_number_format，
    對同一輸入必然同值；它證明不了分流演算法本身的對稱性。
    """
    import core.auto_organize as ao_mod
    import web.routers.scraper as ws_mod

    assert ao_mod.is_number_format is ws_mod.is_number_format
