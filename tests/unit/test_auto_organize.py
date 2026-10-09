"""tests/unit/test_auto_organize.py — core/auto_organize.py run_one_round() 測試（TASK-144-T3）。

覆蓋 DoD 1-9、11 與 mutation 點 M1-M7。TDD-lite：mock smart_search / organize_file /
create_translate_service / reconcile_wishlist，DB 用 tmp db 隔離；唯讀 guard 不 mock
is_path_readonly 的回傳值，用真實唯讀前綴驗（見 DoD-3/4）。
"""
import hashlib
from unittest.mock import AsyncMock

import pytest

from core.auto_organize import run_one_round
from core.database import organize_failures
from core.database.connection import init_db, get_connection
from core.readonly_source import is_path_readonly as real_is_path_readonly


# ---------------------------------------------------------------------------
# 共用 fixture / helper
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """把 organize_failures 用到的預設 db_path 換成 tmp db，避免污染真實 output/openaver.db。"""
    db_path = tmp_path / "test_auto_organize.db"
    init_db(db_path)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)
    return db_path


@pytest.fixture(autouse=True)
def stub_inflow(mocker):
    """整輪成功分支會呼叫 `try_inflow_upsert`（pre-merge SA-pre-9 P2-1）。

    本檔既有測試一律 mock 掉 `organize_file`，`new_filename` 是假路徑，真的讓
    `try_inflow_upsert` 跑起來只會讀一次真實 `config.json` 再回 `"not_linked"`——
    沒有寫入風險但是無謂的 I/O 與對使用者環境的耦合。統一 stub 掉，
    要驗它有沒有被呼叫的測試自己拿這個 mock。
    """
    return mocker.patch("core.auto_organize.try_inflow_upsert", return_value="not_linked")


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


def test_round_returns_folder_not_configured_when_resolve_returns_empty(mocker):
    config = make_config("")
    mocker.patch("core.auto_organize.resolve_favorite_folder", return_value="")
    list_files = mocker.patch("core.auto_organize.list_favorite_video_files", return_value=[])
    mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

    result = run_one_round(config)

    assert result == {"folder_not_configured": True}
    list_files.assert_not_called()


# ===========================================================================
# DoD-1 / DoD-2：四部片統計 ＋ 回傳 schema 逐欄相符（含 M6）
# ===========================================================================

class TestFourFileRoundStatistics:
    def test_four_files_add_two_skip_nfo_one_skip_duplicate_one(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()

        dup_file = write_video(fav_dir, "DUP-001.mp4")
        dup4k_file = write_video(fav_dir, "DUP-001-4K.mp4")
        nfo_file = write_video(fav_dir, "NFO-001.mp4")
        write_video(fav_dir, "NFO-001.nfo", size=10)
        normal_file = write_video(fav_dir, "NORMAL-001.mp4")

        # BE-TEST-10：基準值必須在操作之前取得
        dup_hash_before = hashlib.sha256(dup_file.read_bytes()).hexdigest()

        config = make_config(fav_dir)

        def fake_smart_search(number, uncensored_mode=False):
            return [{"number": number, "title": f"title-{number}", "actors": []}]

        def fake_organize_file(file_path, metadata, cfg):
            if file_path == str(dup_file):
                return {"success": False, "duplicate": True, "duplicate_target": "/target/dup.mp4"}
            if file_path == str(dup4k_file):
                return default_organize_success("/cover/dup4k.jpg")
            if file_path == str(normal_file):
                return default_organize_success("/cover/normal.jpg")
            raise AssertionError(f"unexpected organize_file call for {file_path}")

        mocker.patch("core.auto_organize.smart_search", side_effect=fake_smart_search)
        mocker.patch("core.auto_organize.organize_file", side_effect=fake_organize_file)
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        result = run_one_round(config)

        assert len(result["added"]) == 2
        assert set(result["added"]) == {"DUP-001", "NORMAL-001"}
        assert result["skipped"]["has_nfo"] == 1
        assert len(result["skipped"]["duplicate"]) == 1
        assert result["skipped"]["duplicate"][0]["number"] == "DUP-001"

        # ⚠️ 這裡**不**放「撞檔原片逐位元組不變」的雜湊斷言（PR review 抓到的空轉守衛）：
        # 本測試把 `organize_file` 整支 mock 掉了，雜湊在任何實作下都必然相等——
        # 就算有人把 `organize_file` 換成一支會就地改寫原檔的實作，這個斷言照樣綠。
        # 那條保證的**真守衛在 T0**（`tests/unit/test_organizer.py` 的
        # `test_organize_duplicate_detection` 與 `TestOrganizeAtomicReplace`），
        # 那裡跑的是真正的 `organize_file` ＋ 真檔案系統。
        # 本測試的職責是 `run_one_round` 的**編排**（哪些片進哪一桶），不是搬檔語意。
        assert dup_hash_before is not None  # 保留基準值取得的時機（BE-TEST-10 的形狀）


class TestReturnSchema:
    def test_failure_memory_read_failure_does_not_kill_the_round(
        self, tmp_path, isolated_db, mocker
    ):
        """Codex 六審 P3：失敗記憶查不到時本輪照常整理，不得整輪陣亡。

        使用者流程：背景掃描正在寫 DB → 定時整理那一輪去問「這部片之前查無結果嗎」→
        修正前那兩行拋例外、**整輪當場結束**，一部片都沒整理，排程還要再等 12 小時。
        失敗記憶只是「省得重問 8 個來源」的快取，不該有權殺掉整輪；而手動清單那一邊
        （`_filter_files_sync`）已經是 best-effort，自動不該比手動嚴格。
        """
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "MEMDOWN-001.mp4")

        config = make_config(fav_dir)
        mocker.patch("core.auto_organize.smart_search",
                      return_value=[{"number": "MEMDOWN-001", "title": "t", "actors": []}])
        mocker.patch("core.auto_organize.organize_file",
                      return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])
        mocker.patch.object(organize_failures, "should_skip",
                            side_effect=Exception("database is locked"))

        result = run_one_round(config)

        assert result["added"] == ["MEMDOWN-001"], (
            "失敗記憶查不到就讓整輪陣亡——那一輪一部片都沒整理，還要再等 12 小時"
        )
        assert result["skipped"]["memory_hit"] == 0

    def test_failure_memory_write_failure_does_not_kill_the_round(
        self, tmp_path, isolated_db, mocker
    ):
        """同上的另一半：**記**不起來也不得讓整輪陣亡。

        查無結果的片走 `record_failure('not_found', ...)`。DB 鎖住時修正前那一行拋例外
        ⇒ 整輪結束，**後面還沒處理的片全部被賠掉**。記不起來的代價只是下一輪再問一次。
        """
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "DBLOCK-001.mp4")
        write_video(fav_dir, "DBLOCK-002.mp4")

        config = make_config(fav_dir)
        # 第一部查無結果（要寫記憶、會炸），第二部查得到（必須照樣被整理）
        mocker.patch(
            "core.auto_organize.smart_search",
            side_effect=lambda number, **_kw: (
                [] if number == "DBLOCK-001"
                else [{"number": number, "title": "t", "actors": []}]
            ),
        )
        mocker.patch("core.auto_organize.organize_file",
                      return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])
        mocker.patch.object(organize_failures, "record_failure",
                            side_effect=Exception("database is locked"))

        result = run_one_round(config)

        assert result["failed"] == ["DBLOCK-001"]
        assert result["added"] == ["DBLOCK-002"], (
            "寫記憶失敗把後面還沒處理的片一起賠掉了"
        )
        assert result["newly_recorded"] == 0, "沒真的寫進去就不該計數"

    def test_wishlist_reconcile_failure_does_not_kill_the_round_report(
        self, tmp_path, isolated_db, mocker
    ):
        """最壞情況盤點 R2：對帳失敗不得把整輪的帳一起吃掉。

        使用者流程：開著定時整理、同時在掃描頁跑一次片庫掃描 → 背景那一輪把片整理完、
        搬好、寫好 NFO，最後一步對帳書籤時撞上 DB 鎖 → 修正前例外冒到排程的 except，
        側欄只出現一則紅色「定時整理失敗」，**摘要根本沒發出去** ⇒ 使用者不知道那幾部
        已經被搬走改名了；而且它們現在都有 NFO，下一輪一律跳過，這筆帳永遠補不回來。
        通知是這個功能唯一的帳本（spec §F5），不能誤報。
        """
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "RECON-001.mp4")

        config = make_config(fav_dir)
        mocker.patch("core.auto_organize.smart_search",
                      return_value=[{"number": "RECON-001", "title": "t", "actors": []}])
        mocker.patch("core.auto_organize.organize_file",
                      return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist",
                      side_effect=Exception("database is locked"))

        result = run_one_round(config)

        assert result["added"] == ["RECON-001"], "對帳失敗把整輪的成果吃掉了"
        assert result["wishlist_removed"] == []
        assert result["wishlist_reconcile_failed"] is True

    def test_return_schema_has_all_required_keys(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "SCHEMA-001.mp4")

        config = make_config(fav_dir)
        mocker.patch("core.auto_organize.smart_search",
                      return_value=[{"number": "SCHEMA-001", "title": "t", "actors": []}])
        mocker.patch("core.auto_organize.organize_file", return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=["OWNED-001"])

        result = run_one_round(config)

        assert set(result.keys()) == {
            "added", "cover_missing", "failed", "skipped",
            "newly_recorded", "wishlist_removed", "wishlist_reconcile_failed",
            "aborted_after",
        }
        assert set(result["skipped"].keys()) == {"has_nfo", "memory_hit", "duplicate"}
        assert isinstance(result["added"], list)
        assert isinstance(result["cover_missing"], list)
        assert isinstance(result["failed"], list)
        assert isinstance(result["newly_recorded"], int)
        assert result["wishlist_removed"] == ["OWNED-001"]
        assert result["aborted_after"] is None


# ===========================================================================
# DoD-3 / DoD-4：唯讀 guard，真前綴（含 M1）
# ===========================================================================

class TestReadonlyGuard:
    def test_readonly_folder_skips_entire_round(self, tmp_path, isolated_db, mocker):
        ro_root = tmp_path / "ro_src"
        fav_dir = ro_root / "fav"
        fav_dir.mkdir(parents=True)
        write_video(fav_dir, "SHOULD-NOT-LIST.mp4")

        config = make_config(fav_dir, directories=[{"path": str(ro_root), "readonly": True}])

        spy = mocker.patch("core.auto_organize.is_path_readonly", wraps=real_is_path_readonly)
        list_spy = mocker.patch("core.auto_organize.list_favorite_video_files")
        search_spy = mocker.patch("core.auto_organize.smart_search")
        organize_spy = mocker.patch("core.auto_organize.organize_file")
        reconcile_spy = mocker.patch("core.auto_organize.reconcile_wishlist")

        result = run_one_round(config)

        assert result == {"readonly": True}
        list_spy.assert_not_called()
        search_spy.assert_not_called()
        organize_spy.assert_not_called()
        reconcile_spy.assert_not_called()

        # DoD-4：is_path_readonly 收到的第一個參數必須是 file:/// URI，不是裸原生路徑
        spy.assert_called_once()
        first_arg = spy.call_args[0][0]
        assert first_arg.startswith("file:///"), \
            f"is_path_readonly 收到裸路徑 {first_arg!r}，唯讀來源會靜默失去保護"

    def test_writable_folder_not_flagged_readonly(self, tmp_path, isolated_db, mocker):
        ro_root = tmp_path / "unrelated_ro_src"
        ro_root.mkdir()
        fav_dir = tmp_path / "writable_fav"
        fav_dir.mkdir()
        write_video(fav_dir, "NORMAL-001.mp4")

        config = make_config(fav_dir, directories=[{"path": str(ro_root), "readonly": True}])

        mocker.patch("core.auto_organize.smart_search",
                      return_value=[{"number": "NORMAL-001", "title": "t", "actors": []}])
        mocker.patch("core.auto_organize.organize_file", return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        result = run_one_round(config)

        assert result != {"readonly": True}
        assert "added" in result
        assert result["added"] == ["NORMAL-001"]


# ===========================================================================
# DoD-5 / DoD-6：中止順序、on_file_start 內容、None 參數等同永不中止（含 M2/M3）
# ===========================================================================

class TestAbortOrdering:
    def test_should_abort_stops_after_current_file(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        f1 = write_video(fav_dir, "FILE-001.mp4")
        f2 = write_video(fav_dir, "FILE-002.mp4")

        config = make_config(fav_dir)

        # 順序在這支測試裡是**承重的**（第 2 部才中止），而 `Path.iterdir()` 不保證順序
        # ——不釘死的話在某些檔案系統上會偶發紅燈，浪費排查時間（PR review 指出）。
        mocker.patch("core.auto_organize.list_favorite_video_files",
                      return_value=[str(f1), str(f2)])
        mocker.patch("core.auto_organize.smart_search",
                      side_effect=lambda number, uncensored_mode=False: [{"number": number, "title": "t", "actors": []}])
        organize_mock = mocker.patch("core.auto_organize.organize_file",
                                      return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        call_count = {"n": 0}

        def should_abort():
            call_count["n"] += 1
            return call_count["n"] >= 2  # 第 2 次呼叫（第 2 部片）起回真

        result = run_one_round(config, should_abort=should_abort)

        assert organize_mock.call_count == 1
        assert organize_mock.call_args_list[0].args[0] == str(f1)
        assert result["aborted_after"] == 1
        assert str(f2) not in [c.args[0] for c in organize_mock.call_args_list]

    def test_on_file_start_excludes_aborted_file(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        f1 = write_video(fav_dir, "FILE-001.mp4")
        f2 = write_video(fav_dir, "FILE-002.mp4")

        config = make_config(fav_dir)

        # 順序在這支測試裡是承重的（理由同上一支）
        mocker.patch("core.auto_organize.list_favorite_video_files",
                      return_value=[str(f1), str(f2)])
        mocker.patch("core.auto_organize.smart_search",
                      side_effect=lambda number, uncensored_mode=False: [{"number": number, "title": "t", "actors": []}])
        mocker.patch("core.auto_organize.organize_file", return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        call_count = {"n": 0}

        def should_abort():
            call_count["n"] += 1
            return call_count["n"] >= 2

        started = []
        result = run_one_round(config, should_abort=should_abort, on_file_start=started.append)

        assert started == ["FILE-001"]
        assert "FILE-002" not in started
        assert result["aborted_after"] == 1

    def test_no_number_file_skipped_without_on_file_start(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "no_number_here.mp4")

        config = make_config(fav_dir)
        mocker.patch("core.auto_organize.smart_search")
        mocker.patch("core.auto_organize.organize_file")
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        started = []
        result = run_one_round(config, on_file_start=started.append)

        assert started == []
        assert result["added"] == []
        assert result["failed"] == []


class TestNoneCallablesMeanNeverAbort:
    def test_none_should_abort_and_on_file_start_process_all_files(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "FILE-001.mp4")
        write_video(fav_dir, "FILE-002.mp4")

        config = make_config(fav_dir)
        mocker.patch("core.auto_organize.smart_search",
                      side_effect=lambda number, uncensored_mode=False: [{"number": number, "title": "t", "actors": []}])
        organize_mock = mocker.patch("core.auto_organize.organize_file",
                                      return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        result = run_one_round(config, should_abort=None, on_file_start=None)

        assert organize_mock.call_count == 2
        assert result["aborted_after"] is None


# ===========================================================================
# DoD-7：path_mappings 整輪只取一次，duplicate 鍵一致（含 M4）
# ===========================================================================

class TestDuplicateKeyPathMappings:
    def test_duplicate_key_uses_path_mappings(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "MAP-001.mp4")

        path_mappings = {"/mnt/nas": "\\\\NAS\\share"}
        config = make_config(fav_dir, path_mappings=path_mappings)

        mocker.patch("core.auto_organize.smart_search",
                      return_value=[{"number": "MAP-001", "title": "t", "actors": []}])
        mocker.patch("core.auto_organize.organize_file", return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        spy = mocker.spy(organize_failures, "duplicate_key")

        run_one_round(config)

        spy.assert_called_once()
        called_path_mappings = spy.call_args[0][1]
        assert called_path_mappings == path_mappings, \
            "duplicate 鍵必須帶上整輪只取一次的 path_mappings，不能退回裸 to_file_uri(path)"


# ===========================================================================
# DoD-8：翻譯三子句各有正反例（含 M5）
# ===========================================================================

class TestTranslationClauses:
    def _run_with_translation_mock(self, fav_dir, config, mocker, filename, title,
                                    translate_side_effect=None):
        write_video(fav_dir, filename)
        number = filename.rsplit(".", 1)[0].split(" ")[0]

        mocker.patch("core.auto_organize.smart_search",
                      return_value=[{"number": number, "title": title, "actors": []}])
        mocker.patch("core.auto_organize.organize_file", return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        fake_service = mocker.MagicMock()
        if translate_side_effect is not None:
            fake_service.translate_single = AsyncMock(side_effect=translate_side_effect)
        else:
            fake_service.translate_single = AsyncMock(return_value="翻譯後標題")
        create_mock = mocker.patch("core.auto_organize.create_translate_service",
                                    return_value=fake_service)

        result = run_one_round(config)
        return result, fake_service, create_mock

    def test_translate_called_when_all_three_clauses_true(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        config = make_config(fav_dir, translate_enabled=True)

        result, fake_service, create_mock = self._run_with_translation_mock(
            fav_dir, config, mocker, "JP-001.mp4", "日本語タイトル"
        )

        create_mock.assert_called_once()
        fake_service.translate_single.assert_called_once_with("日本語タイトル")
        assert "JP-001" in result["added"]

    @pytest.mark.parametrize(
        ("filename", "title"),
        [
            ("JP-002 我的中文標題.mp4", "日本語タイトル"),
            ("JP-003.mp4", "English Title No Japanese"),
        ],
        ids=["chinese_title_in_filename", "title_not_japanese"],
    )
    def test_translate_skipped_when_chinese_title_present(
        self, tmp_path, isolated_db, mocker, filename, title
    ):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        config = make_config(fav_dir, translate_enabled=True)

        result, fake_service, create_mock = self._run_with_translation_mock(
            fav_dir, config, mocker, filename, title
        )

        fake_service.translate_single.assert_not_called()

    def test_translate_skipped_when_disabled(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        config = make_config(fav_dir, translate_enabled=False)

        result, fake_service, create_mock = self._run_with_translation_mock(
            fav_dir, config, mocker, "JP-004.mp4", "日本語タイトル"
        )

        create_mock.assert_not_called()
        fake_service.translate_single.assert_not_called()

    def test_translate_failure_does_not_block_or_count_as_failed(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        config = make_config(fav_dir, translate_enabled=True)

        result, fake_service, create_mock = self._run_with_translation_mock(
            fav_dir, config, mocker, "JP-005.mp4", "日本語タイトル",
            translate_side_effect=Exception("translation service down"),
        )

        fake_service.translate_single.assert_called_once()
        assert result["failed"] == []
        assert "JP-005" in result["added"]


# ===========================================================================
# DoD-9：記憶命中不算事件（含 M7）
# ===========================================================================

class TestMemoryHitNotAnEvent:
    def test_memory_hit_does_not_count_as_event(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "MEM-001.mp4")
        write_video(fav_dir, "NEW-001.mp4")

        # 事先寫入一筆 not_found 失敗記憶，讓 MEM-001 在本輪落入記憶命中分支
        organize_failures.record_failure("not_found", "MEM-001", "MEM-001")

        config = make_config(fav_dir)

        search_mock = mocker.patch(
            "core.auto_organize.smart_search",
            side_effect=lambda number, uncensored_mode=False: [] if number == "NEW-001" else None,
        )
        organize_mock = mocker.patch("core.auto_organize.organize_file")
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        result = run_one_round(config)

        assert result["skipped"]["memory_hit"] == 1
        assert result["newly_recorded"] == 1  # 只有 NEW-001 的 not_found 是本輪新記錄
        assert "NEW-001" in result["failed"]
        # 記憶命中的檔案不應該再被拿去查詢或整理
        called_numbers = [c.args[0] for c in search_mock.call_args_list]
        assert "MEM-001" not in called_numbers
        organize_mock.assert_not_called()


class TestClearOnSuccess:
    """成功入庫必須清掉那部片的失敗記憶（CD-144-8 明文，Opus 獨立抽驗補的守衛）。

    這一格原本**沒有任何測試守著**：把 `organize_failures.clear_on_success(number)`
    整行拿掉，卡片定的 M1–M7 七格全部照樣 PASS。

    使用者流程（CD-144-8 逐字）：某片自動輪查無結果被記一筆 → 之後那部片成功入庫
    → 記憶沒清 → **最長 7 天內，「我的最愛」清單與自動輪都還把這部已經在片庫裡的片
    當成「查過沒結果」在跳過**，而使用者看不出為什麼。
    """

    def test_successful_organize_clears_not_found_memory(self, tmp_path, isolated_db, mocker):
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "ABC-123.mp4")
        config = make_config(fav)

        # 先讓這部片有一筆「查無結果」的記憶（模擬前幾輪的失敗）
        organize_failures.record_failure("not_found", "ABC-123", "ABC-123")
        assert organize_failures.should_skip("not_found", "ABC-123") is True, (
            "前置條件：這一輪開始前，記憶必須是命中的"
        )

        # 這一輪查得到、也整理成功了
        mocker.patch("core.auto_organize.smart_search",
                     return_value=[{"number": "ABC-123", "title": "Some Title"}])
        mocker.patch("core.auto_organize.organize_file",
                     return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        # 記憶命中會讓這部片在步驟 3 就被跳過，所以要讓退避窗過期它這一輪才跑得到整理。
        mocker.patch("core.database.organize_failures._now",
                     return_value=organize_failures._now() + 8 * 86400)

        result = run_one_round(config)

        assert result["added"] == ["ABC-123"]

        # 🔴 斷言必須直接看**那一列在不在**，不能用 `should_skip()`：
        # 上面 patch 掉的時鐘已經讓退避窗過期，`should_skip()` 不論那列有沒有被刪都會回 False
        # ——用它斷言會是假綠（本測試第一版就是這樣，mutation 自驗當場抓到）。
        with get_connection(isolated_db) as conn:
            row = conn.cursor().execute(
                "SELECT 1 FROM organize_failures WHERE reason='not_found' AND key='ABC-123'"
            ).fetchone()
        assert row is None, (
            "成功入庫之後那筆『查無結果』的記憶必須被刪掉，"
            "否則接下來最長 7 天，這部已經在片庫裡的片還會被當成『查過沒結果』跳過"
        )


class TestInflowUpsertOnSuccess:
    """pre-merge SA-pre-9 P2-1：自動整理成功的片必須跟手動整理一樣進 DB。

    少了這一步，使用者流程是：最愛資料夾同時也是掃描頁追蹤的來源之一 → 定時整理
    跑完，側欄說「新增 3 部」→ 打開瀏覽頁，**那 3 部不在**，要再跑一次掃描才出現；
    而且迴圈結束那次 `reconcile_wishlist()` 走 `VideoRepository.get_by_numbers`，
    查不到剛整理好的片 ⇒ spec §F5「自動入庫的片同輪從書籤消失」永遠不成立。
    """

    def test_success_calls_inflow_with_new_path_and_old_path(
        self, tmp_path, isolated_db, mocker, stub_inflow
    ):
        fav = tmp_path / "fav"
        fav.mkdir()
        src = write_video(fav, "ABC-123.mp4")
        config = make_config(fav)

        mocker.patch("core.auto_organize.smart_search",
                     return_value=[{"number": "ABC-123", "title": "T"}])
        organized = default_organize_success()
        organized["new_filename"] = str(tmp_path / "lib" / "ABC-123" / "ABC-123.mp4")
        mocker.patch("core.auto_organize.organize_file", return_value=organized)
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        result = run_one_round(config)

        assert result["added"] == ["ABC-123"]
        stub_inflow.assert_called_once()
        # 位置參數是整理**後**的路徑、`old_file_path` 是整理**前**的路徑——
        # 兩者都要對，`old_file_path` 是 repath 的依據（帶錯 DB 會多出一列孤兒，
        # 而不是把舊那列原地更新，使用者會在瀏覽頁看到同一部片兩張卡）。
        args, kwargs = stub_inflow.call_args
        assert args[0] == organized["new_filename"], (
            f"要拿整理後的新路徑去 upsert，實際拿到 {args[0]!r}"
        )
        assert kwargs.get("old_file_path") == str(src), (
            f"old_file_path 要是整理前的原始路徑（repath 依據），實際 {kwargs.get('old_file_path')!r}"
        )

    def test_duplicate_and_failed_do_not_call_inflow(self, tmp_path, isolated_db, mocker, stub_inflow):
        """只有真的搬成功才進 DB。撞名（檔沒動）與失敗（檔沒動）都不能寫。"""
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "DUP-001.mp4")
        write_video(fav, "BAD-002.mp4")
        config = make_config(fav)

        mocker.patch("core.auto_organize.smart_search",
                     side_effect=lambda number, *a, **kw: [{"number": number, "title": "T"}])
        mocker.patch("core.auto_organize.organize_file", side_effect=lambda path, *a, **kw: (
            {"duplicate": True, "duplicate_target": "other.mp4"}
            if "DUP-001" in path else {"success": False, "error": "boom"}
        ))
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        run_one_round(config)

        stub_inflow.assert_not_called()

    def test_missing_new_filename_does_not_call_inflow(self, tmp_path, isolated_db, mocker, stub_inflow):
        """`organize_file` 回了 success 卻沒帶 new_filename 時不要拿 None 去 upsert。"""
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "ABC-123.mp4")
        config = make_config(fav)

        mocker.patch("core.auto_organize.smart_search",
                     return_value=[{"number": "ABC-123", "title": "T"}])
        organized = default_organize_success()
        organized["new_filename"] = ""
        mocker.patch("core.auto_organize.organize_file", return_value=organized)
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        run_one_round(config)

        stub_inflow.assert_not_called()


class TestTranslateServiceConstruction:
    """Codex PR #181 一審：翻譯服務怎麼建出來的，兩條都是承重。"""

    def _run(self, tmp_path, mocker, config, create_side_effect=None, create_return=None):
        fav = tmp_path / "fav"
        fav.mkdir(exist_ok=True)
        write_video(fav, "ABC-123.mp4")
        mocker.patch("core.auto_organize.smart_search",
                     return_value=[{"number": "ABC-123", "title": "日本語タイトル", "actors": []}])
        mocker.patch("core.auto_organize.organize_file", return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])
        kwargs = {}
        if create_side_effect is not None:
            kwargs["side_effect"] = create_side_effect
        else:
            fake = create_return if create_return is not None else mocker.MagicMock()
            if create_return is None:
                fake.translate_single = AsyncMock(return_value="翻譯後標題")
            kwargs["return_value"] = fake
        create_mock = mocker.patch("core.auto_organize.create_translate_service", **kwargs)
        return run_one_round(config), create_mock

    def test_configured_locale_is_passed_to_the_factory(self, tmp_path, isolated_db, mocker):
        """P1：使用者設定的語言必須傳給工廠。

        使用者流程：把介面語言設成日文、開了翻譯與定時整理 → 每 12 小時無人值守跑一輪 →
        日文標題全被翻成**繁體中文**寫進檔名、資料夾名與 NFO 的 <title>
        （core/organizer.py:1092 / :1211 / :1336）→ 只能一部一部重刮救回來。

        對日文使用者尤其致命：三個 provider 的 translate_single 都有
        `if self.target_language == "ja": return title` 這條專門保護日文使用者的短路，
        服務若永遠用 "zh-TW" 建出來，那條短路**從來打不到**。
        """
        config = make_config(tmp_path / "fav", translate_enabled=True, locale="ja")
        _, create_mock = self._run(tmp_path, mocker, config)

        create_mock.assert_called_once()
        args, kwargs = create_mock.call_args
        passed = kwargs.get("target_language", args[1] if len(args) > 1 else None)
        assert passed == "ja", (
            f"必須把 config['general']['locale'] 傳給 create_translate_service，實際傳了 {passed!r}"
        )

    def test_missing_locale_falls_back_to_zh_tw(self, tmp_path, isolated_db, mocker):
        """反向鎖：config 沒有 general.locale 時仍是 zh-TW（不得拋 KeyError、不得傳 None）。"""
        config = make_config(tmp_path / "fav", translate_enabled=True)   # 不給 general
        _, create_mock = self._run(tmp_path, mocker, config)

        args, kwargs = create_mock.call_args
        passed = kwargs.get("target_language", args[1] if len(args) > 1 else None)
        assert passed == "zh-TW"

    def test_factory_failure_degrades_to_no_translation_and_round_continues(
        self, tmp_path, isolated_db, mocker
    ):
        """第二條：翻譯服務建不起來時，整輪不得陣亡。

        使用者流程：把翻譯 provider 切到 Gemini、勾了啟用，但 API Key 還沒貼就存檔
        （設定頁沒有跨欄位驗證，存得出這個狀態）→ 每 12 小時整輪 **0 部片被處理**，
        畫面只有一則「定時整理失敗，請查閱日誌」，看不出是翻譯設定沒配好。

        翻譯是加分項不是前提 ⇒ 建不起來就這一輪不翻譯，照常整理。
        """
        config = make_config(tmp_path / "fav", translate_enabled=True, locale="zh-TW")
        result, create_mock = self._run(
            tmp_path, mocker, config,
            create_side_effect=ValueError("Gemini API Key is required"),
        )

        create_mock.assert_called_once()
        assert result["added"] == ["ABC-123"], (
            f"翻譯服務建不起來只該讓這一輪不翻譯，不該讓整輪 0 部片，實際 {result}"
        )
        assert result["failed"] == [], "建構失敗不得把片算成 failed（DoD-8 同一個政策）"


class TestNfoEnumerationFailsClosed:
    """Codex PR #181 二審 P0：列不到最愛資料夾時，這一輪一個檔都不准動。

    使用者流程：最愛資料夾在 NAS 上，設定是「不建資料夾」（片子平放在那一層、
    檔名已經是正規格式、旁邊有你自己編過的 .nfo）→ 定時整理列完檔之後、
    偵測 NFO 之前那一瞬間 NAS 掉線 → 整夾已經刮好的片全部被當成沒刮過 →
    重新上網搜、**把封面重下一次、把 NFO 整份重寫** → 你手動編過的欄位沒了。

    ⚠️ 原子佔位在這條路上**擋不住**：`organize_file` 的搬移那整段包在
    `if file_path != target_path:` 底下（`core/organizer.py:1247`），
    「不建資料夾 ＋ 檔名已正規」時兩者相等 ⇒ `O_EXCL` 根本不會被執行到，
    直接往下寫封面（`:1279`）與 NFO（`:1333`）。
    """

    def test_round_returns_folder_unreachable_and_touches_nothing(
        self, tmp_path, isolated_db, mocker
    ):
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "ABC-123.mp4")
        config = make_config(fav)

        mocker.patch("core.auto_organize.detect_nfo",
                     side_effect=OSError(5, "Input/output error"))
        search_spy = mocker.patch("core.auto_organize.smart_search")
        organize_spy = mocker.patch("core.auto_organize.organize_file")
        reconcile_spy = mocker.patch("core.auto_organize.reconcile_wishlist")

        result = run_one_round(config)

        assert result == {"folder_unreachable": True}, (
            f"要走既有的 folder_unreachable 哨兵（scheduler 已有分支與文案），實際 {result}"
        )
        search_spy.assert_not_called()
        organize_spy.assert_not_called()
        reconcile_spy.assert_not_called()

    def test_detect_nfo_is_called_in_strict_mode(self, tmp_path, isolated_db, mocker):
        """反向鎖：自動這條路一定要用 strict=True 問，否則上面那個哨兵永遠不會發生。"""
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "ABC-123.mp4")
        config = make_config(fav)

        detect_spy = mocker.patch("core.auto_organize.detect_nfo", return_value={})
        mocker.patch("core.auto_organize.smart_search", return_value=[])
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        run_one_round(config)

        detect_spy.assert_called_once()
        assert detect_spy.call_args.kwargs.get("strict") is True, (
            "必須以 strict=True 呼叫 detect_nfo，否則列不到目錄會被靜默當成「沒有 NFO」"
        )


class TestUncensoredModeParity:
    """Codex 三審 ②：auto ≠ manual 的無碼模式落差。

    使用者流程：使用者在設定頁開了無碼模式（只搜 AVSOX / FC2）→ 定時整理卻
    永遠用預設 False 去問 `smart_search` → 該片這一輪要嘛查無結果被記進失敗
    記憶、要嘛湊巧命中一個有碼來源的錯誤結果 → 使用者看不出來、只覺得
    「定時整理跟我自己按搜尋的結果不一樣」。手動搜尋（web/routers/search.py）
    與掃描（web/routers/scanner.py）都把 `is_uncensored_mode_effective(config)`
    傳進去，這裡補回同一條。
    """

    def test_smart_search_receives_true_when_uncensored_mode_enabled(
        self, tmp_path, isolated_db, mocker
    ):
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "ABC-123.mp4")
        config = make_config(fav)
        config["search"]["uncensored_mode_enabled"] = True

        search_spy = mocker.patch("core.auto_organize.smart_search", return_value=[])
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        run_one_round(config)

        search_spy.assert_called_once()
        assert search_spy.call_args.kwargs.get("uncensored_mode") is True, (
            "config 開了無碼模式，smart_search 卻沒收到 uncensored_mode=True"
        )

    def test_smart_search_receives_false_when_uncensored_mode_disabled(
        self, tmp_path, isolated_db, mocker
    ):
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "ABC-123.mp4")
        config = make_config(fav)
        config["search"]["uncensored_mode_enabled"] = False

        search_spy = mocker.patch("core.auto_organize.smart_search", return_value=[])
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        run_one_round(config)

        search_spy.assert_called_once()
        assert search_spy.call_args.kwargs.get("uncensored_mode") is False, (
            "config 沒開無碼模式，smart_search 不該收到 uncensored_mode=True"
        )


class TestClearOnSuccessBestEffort:
    """Codex 三審 ④：`clear_on_success()` 拋例外不准讓整輪中止。

    使用者流程：`organize_file()` 已經把片搬完改完名了 → 這一刻 SQLite 短暫
    鎖住 → `clear_on_success()` 拋例外 → 若沒接住，整輪 abort，那部**已經搬好
    的片**不進 `added` 統計、也不會呼叫 `try_inflow_upsert()`（可能不進片庫，
    瀏覽頁看不到它）。手動路徑（web/routers/scraper.py 的 scrape_single）已經
    把這一步當 best-effort，這裡照抄同一形狀。
    """

    def test_clear_on_success_exception_does_not_abort_round(
        self, tmp_path, isolated_db, mocker, stub_inflow
    ):
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "ABC-123.mp4")
        config = make_config(fav)

        mocker.patch("core.auto_organize.smart_search",
                     return_value=[{"number": "ABC-123", "title": "Some Title"}])
        mocker.patch("core.auto_organize.organize_file",
                     return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])
        mocker.patch(
            "core.auto_organize.organize_failures.clear_on_success",
            side_effect=RuntimeError("database is locked"),
        )

        result = run_one_round(config)

        assert result["added"] == ["ABC-123"], (
            "clear_on_success 拋例外不該讓已經整理好的片漏掉 added 統計"
        )
        stub_inflow.assert_called_once()
