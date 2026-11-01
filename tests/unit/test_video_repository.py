"""測試 VideoRepository 類別"""
import sqlite3
from dataclasses import fields
from unittest.mock import patch

import pytest

from core.database import (
    Video,
    VideoRepository,
    init_db,
)
from core.path_utils import to_file_uri


def _select_focal_pair(db_path, path):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT auto_focal, focal_model FROM videos WHERE path = ?",
            (path,),
        ).fetchone()
    finally:
        conn.close()


# temp_db fixture 定義於 tests/unit/conftest.py


@pytest.fixture
def sample_video():
    """建立測試用影片"""
    return Video(
        path=to_file_uri("C:/Videos/test.mp4"),
        number="ABC-123",
        title="測試影片",
        original_title="Test Video",
        actresses=["演員A", "演員B"],
        maker="測試片商",
        series="測試系列",
        tags=["類型1", "類型2"],
        duration=120,
        size_bytes=1024 * 1024 * 100,
        cover_path=to_file_uri("C:/Videos/test.jpg"),
        release_date="2024-01-20",
        mtime=1234567890.0,
        nfo_mtime=1234567800.0
    )


class TestVideoRepository:
    """VideoRepository 測試"""


    def test_get_mtime_index_sample_count(self, temp_db):
        """get_mtime_index 的第三欄反映實際劇照張數（TASK-118b-T9）"""
        repo = VideoRepository(temp_db)

        video = Video(
            path=to_file_uri("/video1.mp4"), mtime=100.5, nfo_mtime=100.0,
            sample_images=["file:///a.jpg", "file:///b.jpg", "file:///c.jpg"],
        )
        repo.upsert_batch([video])

        index = repo.get_mtime_index()

        assert index[to_file_uri("/video1.mp4")] == (100.5, 100.0, 3)


    def test_delete_by_paths(self, temp_db):
        """測試 delete_by_paths"""
        repo = VideoRepository(temp_db)

        videos = [
            Video(path=to_file_uri("/video1.mp4"), mtime=100.0),
            Video(path=to_file_uri("/video2.mp4"), mtime=200.0),
            Video(path=to_file_uri("/video3.mp4"), mtime=300.0),
        ]
        repo.upsert_batch(videos)

        deleted = repo.delete_by_paths([to_file_uri("/video1.mp4"), to_file_uri("/video3.mp4")])

        assert deleted == 2
        assert repo.count() == 1
        assert repo.get_by_path(to_file_uri("/video2.mp4")) is not None


class TestOutputDirProtectionAndOccupancy:
    """TASK-89a-T1: upsert/upsert_batch output_dir 對稱保護 + 佔用查詢 helper"""


    def test_upsert_batch_preserves_output_dir_on_empty_incoming(self, temp_db):
        """upsert_batch 傳空 output_dir（且 DB 已有非空既有值）→ 既有值不被覆寫
        （與 upsert 對稱測試，Codex C2 回歸鎖：獨立斷言，不假設 upsert_batch 與 upsert 行為一致）"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")

        repo.upsert_batch([
            Video(path=path, title="影片1", output_dir=to_file_uri("/produced/ABC-001")),
        ])

        repo.upsert_batch([
            Video(path=path, title="影片1-rescan", output_dir=""),
        ])

        result = repo.get_by_path(path)
        assert result is not None
        assert result.output_dir == to_file_uri("/produced/ABC-001")


    def test_is_output_dir_taken_true_when_held_by_other_row(self, temp_db):
        """候選 output_dir 被別筆 path（source_uri）佔用 → True"""
        repo = VideoRepository(temp_db)
        taken_dir = to_file_uri("/produced/ABC-001")

        repo.upsert(Video(path=to_file_uri("/video1.mp4"), title="影片1", output_dir=taken_dir))

        assert repo.is_output_dir_taken(taken_dir, to_file_uri("/video2.mp4")) is True

    def test_is_output_dir_taken_false_when_held_only_by_self(self, temp_db):
        """候選 output_dir 只被自己（exclude_path 對應那筆）持有 → False（原地覆蓋不誤判）"""
        repo = VideoRepository(temp_db)
        own_dir = to_file_uri("/produced/ABC-001")
        own_path = to_file_uri("/video1.mp4")

        repo.upsert(Video(path=own_path, title="影片1", output_dir=own_dir))

        assert repo.is_output_dir_taken(own_dir, own_path) is False


class TestScrapeAttemptedAtUpsertProtection:
    """P2 修正：scrape_attempted_at 缺 empty→preserve 保護，與 output_dir 不對稱。
    補對稱 CASE-WHEN（採「保留」語意）：incoming=0 時保留 DB 既有值，避免資料夾重掃
    （Video.from_video_info() 預設 scrape_attempted_at=0.0）洗掉 enricher 標記的 tried 時間戳。"""


    def test_upsert_batch_preserves_scrape_attempted_at_on_zero_incoming(self, temp_db):
        """upsert_batch 傳 scrape_attempted_at=0（且 DB 已有 >0 既有值）→ 既有值不被覆寫
        （與 upsert 對稱測試，回歸鎖：獨立斷言，不假設 upsert_batch 與 upsert 行為一致）"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")

        repo.upsert_batch([
            Video(path=path, title="影片1", scrape_attempted_at=1717171717.0),
        ])

        repo.upsert_batch([
            Video(path=path, title="影片1-rescan", scrape_attempted_at=0.0),
        ])

        result = repo.get_by_path(path)
        assert result is not None
        assert result.scrape_attempted_at == 1717171717.0


class TestScrapeAttemptedAtRepositoryMethods:
    """TASK-89b-T1: update_scrape_attempted_at / get_attempted_index / insert_if_ignore"""

    # ── update_scrape_attempted_at ──────────────────────────────────────────


    # ── get_attempted_index ──────────────────────────────────────────────────


    # ── insert_if_ignore ──────────────────────────────────────────────────────


    def test_insert_if_ignore_existing_path_does_not_overwrite_returns_false(self, temp_db):
        """path 已存在 → 不覆蓋任何既有欄位（含 cover_path/user_tags/output_dir）並回傳 False"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")
        repo.upsert(Video(
            path=path, title="既有影片", cover_path=to_file_uri("/out/v1.jpg"),
            user_tags=["existing_tag"], output_dir=to_file_uri("/produced/EXIST-001"),
        ))

        conflicting = Video(
            path=path, title="嘗試覆蓋", cover_path=to_file_uri("/out/OTHER.jpg"),
            user_tags=["new_tag"], output_dir=to_file_uri("/produced/OTHER-999"),
        )
        ok = repo.insert_if_ignore(conflicting)

        assert ok is False
        result = repo.get_by_path(path)
        assert result.title == "既有影片"
        assert result.cover_path == to_file_uri("/out/v1.jpg")
        assert result.user_tags == ["existing_tag"]
        assert result.output_dir == to_file_uri("/produced/EXIST-001")


class TestNfoMtimeRepathAuthoritative:
    """TASK-showcase-nfo-mtime: repath 各分支 nfo_mtime 權威值寫穿驗證（含 anti-stale 反向案）。

    Codex High 裁決（見 feature/97-javdb-packaging-fix/showcase-nfo-mtime-inflow/
    TASK-showcase-nfo-mtime.md「方案取捨」）：nfo_mtime=0 是「已確認無 NFO」的合法值，
    與 output_dir=''/scrape_attempted_at=0 的「無資訊、保留舊值」語意不同 —— DB 層
    不加 0-guard，plain overwrite（照傳入值寫，包含 0）即為正確行為。本測試組
    分別覆蓋 upsert / 正常 UPDATE / 碰撞 merge 三分支，並含 anti-stale 探針
    （證明「若誤加 0-guard」會被這裡的斷言抓到）。
    """

    # ── upsert 分支（old_uri None，或 old 不在 DB → 委派 upsert）──────────────


    def test_upsert_on_conflict_anti_stale_zero_overwrites_existing(self, temp_db):
        """upsert() ON CONFLICT(path) DO UPDATE 分支 anti-stale 探針（負向 DoD 守衛）：
        同一 path 已有 nfo_mtime>0 的 row，再次 upsert 帶 incoming nfo_mtime=0
        （確認無 NFO）→ DB 必須被覆蓋為 0，不得保留舊正值。

        此分支正是 upsert() 已對 output_dir/scrape_attempted_at 掛 CASE-WHEN-0 守衛之處，
        是未來最可能被誤加 nfo_mtime 0-guard 的位置。既有「upsert branch」測試只走
        INSERT（new_uri 不預存），從不觸發 ON CONFLICT UPDATE，故補此案堵住守衛缺口。
        MUTATION：若在 upsert() ON CONFLICT 加 nfo_mtime CASE-WHEN-0 守衛，本測試必 RED。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video_upsert_conflict_zero.mp4")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=path, title="舊片", nfo_mtime=888.0))
        # 確認前置：ON CONFLICT 分支需 path 已存在且 nfo_mtime>0
        pre = repo.get_by_path(path)
        assert pre is not None and pre.nfo_mtime == 888.0

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=path, title="新掃描-無NFO", nfo_mtime=0.0))

        row = repo.get_by_path(path)
        assert row is not None
        assert row.nfo_mtime == 0.0, (
            f"upsert ON CONFLICT 分支：incoming nfo_mtime=0 應覆蓋舊正值 888.0，"
            f"不得殘留，實際: {row.nfo_mtime!r}"
        )


    # ── 正常 UPDATE 分支（old 在 DB、new 不在）──────────────────────────────


    def test_repath_normal_update_anti_stale_zero_incoming_does_not_retain_old_value(self, temp_db):
        """anti-stale 反向案（Codex 指定探針）：pre-existing row nfo_mtime>0；
        repath 到新路徑且 incoming nfo_mtime=0（新路徑確實無 NFO）→ 結果必須為 0，
        不得殘留舊 mtime 假稱 has_nfo=true。這正是揭穿「0-guard」矛盾方案的斷言：
        若 production 錯誤加上『incoming=0 時保留既有值』的 CASE-WHEN 守衛，
        本測試會 RED（見 mutation check）。"""
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/old_anti_stale.mp4")
        new_uri = to_file_uri("/new_anti_stale.mp4")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片", nfo_mtime=999.0))

        new_video = Video(path=new_uri, title="新片-無NFO", nfo_mtime=0.0)
        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(old_uri, new_uri, new_video)

        row = repo.get_by_path(new_uri)
        assert row is not None
        assert row.nfo_mtime == 0.0, (
            f"anti-stale: 新路徑無 NFO 時 nfo_mtime 必須為 0，不得殘留舊值 999.0，"
            f"實際: {row.nfo_mtime!r}"
        )

    # ── 碰撞 delete-merge 分支（new 已存在）──────────────────────────────────


# ============ TASK-98a-T4: focal + crop_mode preserve-on-conflict（CD-98a-6）============

class TestFocalPreserveOnConflict:
    """crop_mode/auto_focal 四路 builder preserve-on-conflict 回歸鎖——這是本 milestone
    最貴的一條（Codex P1）：漏任一 builder＝掃描/重刮把背景算的 focal 與使用者的
    crop_mode 選擇清回 dataclass 預設值。四路皆須：先用 mutator 寫非預設值，再走
    對應 builder 寫一筆「看似新掃描」的 Video（focal 欄位是 dataclass 預設），
    讀回後 focal 欄位須維持 mutator 寫的值，不被覆蓋。
    """


    def test_upsert_batch_preserves_focal_on_conflict(self, temp_db, seed_crop_mode):
        """upsert_batch() ON CONFLICT 分支（Scanner 增量掃描主路徑，漏此等於沒修）。
        含 focal_attempted_at（Codex PR#105 P2）——mutation：把 focal_attempted_at 移出
        _FOCAL_PRESERVE 會讓這條 RED（洗回 NULL）。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_upsert_batch.mp4")
        repo.upsert(Video(path=path, title="舊片"))
        assert seed_crop_mode(repo, path, 'default') is True
        assert repo.update_auto_focal(path, '0.5,0.4', '') is True

        repo.upsert_batch([Video(path=path, title="重掃描新片")])

        result = repo.get_by_path(path)
        assert result is not None
        assert result.crop_mode == 'default'
        assert result.auto_focal == '0.5,0.4'
        assert result.focal_attempted_at is not None

    def test_repath_normal_update_preserves_focal(self, temp_db, seed_crop_mode):
        """repath() 分支 2（正常 UPDATE，old 在 DB、new 不在）：SET 子句不含 focal"""
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/focal_repath_old.mp4")
        new_uri = to_file_uri("/focal_repath_new.mp4")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片"))
        assert seed_crop_mode(repo, old_uri, 'default') is True
        assert repo.update_auto_focal(old_uri, '0.5,0.4', '') is True

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(old_uri, new_uri, Video(path=new_uri, title="重掃描新片"))

        result = repo.get_by_path(new_uri)
        assert result is not None
        assert result.crop_mode == 'default'
        assert result.auto_focal == '0.5,0.4'
        assert result.focal_attempted_at is not None


    # ── Codex PR#105 P2b：cover_path 換了必須重置 focal 偵測態 ───────────────


    # ── 99a-T1b CD-10：manual 座標換封面必須降回 auto（平行於上方 default 版本）───


    def test_upsert_batch_resets_manual_focal_when_cover_path_changes(self, temp_db):
        """upsert_batch() 同鏡射（Scanner 增量掃描主路徑，漏此等於沒修）。mutation：
        拔掉 upsert_batch() crop_mode CASE 的降級分支 → 留 manual → RED。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_cover_change_batch_manual.mp4")
        old_cover = to_file_uri("/focal_cover_change_batch_manual_old.jpg")
        new_cover = to_file_uri("/focal_cover_change_batch_manual_new.jpg")

        repo.upsert(Video(path=path, title="舊片", cover_path=old_cover))
        assert repo.update_manual_focal(path, '0.3000,0.6000', old_cover) is True

        repo.upsert_batch([Video(path=path, title="換封面重掃", cover_path=new_cover)])

        result = repo.get_by_path(path)
        assert result is not None
        assert result.cover_path == new_cover
        assert result.auto_focal == ''
        assert result.focal_attempted_at is None
        assert result.crop_mode == 'auto'

    def test_repath_normal_update_resets_manual_focal_when_cover_path_changes(self, temp_db):
        """repath() 分支 2（機制 B，inline `cover_unchanged` 判斷、非經 `_FOCAL_PRESERVE`）
        manual 版——task 標注「最易漏」，因為此分支是逐欄手動組 SET、無法直接鏡射機制 A
        的 CASE 寫法。mutation：拔掉 `old_row.crop_mode == 'manual'` 降級分支 → 留
        manual → RED。"""
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/focal_repath_cover_change_old_manual.mp4")
        new_uri = to_file_uri("/focal_repath_cover_change_new_manual.mp4")
        old_cover = to_file_uri("/focal_repath_cover_change_old_manual.jpg")
        new_cover = to_file_uri("/focal_repath_cover_change_new_manual.jpg")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片", cover_path=old_cover))
        assert repo.update_manual_focal(old_uri, '0.3000,0.6000', old_cover) is True

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(
                old_uri, new_uri,
                # incoming 帶 non-default focal（Codex PR#105 P2c 教訓）：若 reset branch
                # 漏 continue、fall through 到底部通用 append，會用這裡的 stale 值蓋掉
                # reset（SQLite 取最右 SET）。
                Video(path=new_uri, title="換封面重掃", cover_path=new_cover,
                      auto_focal='0.9,0.9', focal_attempted_at='2020-01-01 00:00:00'),
            )

        result = repo.get_by_path(new_uri)
        assert result is not None
        assert result.cover_path == new_cover
        assert result.auto_focal == ''
        assert result.focal_attempted_at is None
        assert result.crop_mode == 'auto', "manual 座標對新封面已失效，換封面必須降回 auto"


class TestFocalMutators:
    """VideoRepository.update_auto_focal / update_manual_focal round-trip（CD-98a-6
    mutator；update_manual_focal 為 99a-T1a 新增）。update_crop_mode 已於 plan-99a
    §B.3 retire（production 已無呼叫端，見 99a-T7）——round-trip/missing-path 契約
    測試隨方法一併移除，其餘測試改用 conftest 的 test-only `seed_crop_mode` fixture
    準備前置狀態。"""


    def test_update_manual_focal_roundtrip(self, temp_db):
        """單一 UPDATE 原子寫兩欄：auto_focal 與 crop_mode='manual' 同時反映（99a-T1a）。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_mutator_manual_focal.mp4")
        repo.upsert(Video(path=path, title="片", crop_mode="default"))

        assert repo.update_manual_focal(path, '0.3000,0.6000', '') is True

        result = repo.get_by_path(path)
        assert result is not None
        assert result.auto_focal == '0.3000,0.6000'
        assert result.crop_mode == 'manual'


    # ── 99a-T1b CD-4：reset_focal_to_auto ────────────────────────────────────

    def test_reset_focal_to_auto_roundtrip(self, temp_db):
        """單一 UPDATE 原子清空 auto_focal 並把 crop_mode 降回 'auto'（比照
        update_manual_focal 的原子寫法）。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_mutator_reset.mp4")
        repo.upsert(Video(path=path, title="片"))
        assert repo.update_manual_focal(path, '0.3000,0.6000', '') is True

        assert repo.reset_focal_to_auto(path) is True

        result = repo.get_by_path(path)
        assert result is not None
        assert result.auto_focal == ''
        assert result.crop_mode == 'auto'


    def test_reset_focal_to_auto_requeues_after_worker_never_commits(self, temp_db):
        """端到端回歸：rescrape（cover_written=True）呼叫 reset_focal_to_auto → worker
        送出後失敗/從未呼叫 update_auto_focal 蓋章 → 之後一次重掃的
        get_empty_focal_candidates 必須把這一列重新排入候選（CD-4『重刮＝比照一次
        新刮』）。若 reset 沒清 focal_attempted_at，這條會 RED（結果變 []）。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_mutator_reset_requeue.mp4")
        repo.upsert(Video(path=path, number="SIRO-9999", maker="", cover_path="cover_old"))
        # 舊封面已偵測過（有臉）
        assert repo.update_auto_focal(path, "0.5,0.5", "cover_old") is True

        # 重刮換封面：enricher 呼叫 reset_focal_to_auto（worker 之後失敗/從未
        # commit，模擬時直接不呼叫 update_auto_focal）
        assert repo.reset_focal_to_auto(path) is True

        # 下一次重掃：這一列應被判定為候選重新排入偵測
        result = repo.get_empty_focal_candidates([path])
        assert result == [(path, "SIRO-9999", "", "cover_old")]

    # ── 99a-T1b CD-9：worker commit 加 crop_mode != 'manual' 守衛 ─────────────

    def test_update_auto_focal_blocked_when_crop_mode_manual(self, temp_db):
        """manual row 被 in-flight worker commit 擋下（rowcount 0）——mutation：拔掉
        `AND crop_mode != 'manual'` 會讓這條 RED（manual 座標被偷換）。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_mutator_cd9_guard.mp4")
        repo.upsert(Video(path=path, title="片"))
        assert repo.update_manual_focal(path, '0.3000,0.6000', '') is True

        assert repo.update_auto_focal(path, '0.9,0.9', '') is False, "manual row 應被守衛擋下，rowcount 0"

        result = repo.get_by_path(path)
        assert result.auto_focal == '0.3000,0.6000', "manual 座標不可被 stale worker 偷換"
        assert result.crop_mode == 'manual'


    # ── 99b-T2 CD-99b-3/4/5/9：換封面 compare-and-store（DoD ①②③） ──────────

    def test_update_auto_focal_blocked_when_cover_path_changed(self, temp_db, seed_crop_mode):
        """DoD ①：換封面 race 鎖。seed row cover_path=A，模擬 in-flight 舊 job 帶
        expected_cover_path=A → row 中途被換成 cover_path=B（模擬 scanner upsert 換
        封面）→ commit(expected=A) 必須 rowcount 0，auto_focal/focal_attempted_at
        不變。mutation：拔掉 `AND cover_path=?` → 寫入成功 → RED。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_cd99b_cover_race.mp4")
        cover_a = to_file_uri("/focal_cd99b_cover_race_a.jpg")
        cover_b = to_file_uri("/focal_cd99b_cover_race_b.jpg")

        repo.upsert(Video(path=path, title="片", cover_path=cover_a))
        assert seed_crop_mode(repo, path, 'auto') is True

        # row 換封面（模擬 scanner upsert 在 in-flight job 分析期間換圖）
        repo.upsert(Video(path=path, title="片-換封面", cover_path=cover_b))

        # 舊 job commit：expected 仍是 A（分析當下捕獲的值）
        committed = repo.update_auto_focal(path, '0.5,0.4', cover_a)
        assert committed is False, "expected_cover_path 對不上目前 cover_path，應 rowcount 0"

        result = repo.get_by_path(path)
        assert result.auto_focal == '', "舊 job 未命中，auto_focal 不應被寫入"
        assert result.focal_attempted_at is None, "舊 job 未命中，不應蓋 focal_attempted_at 章"
        assert result.cover_path == cover_b


    # ── Codex PR#107 第二輪 P2：手動存檔的 cover compare-and-store 守衛 ─────────


class TestUpdateCoverPathPreserveFocal:
    """VideoRepository.update_cover_path_preserve_focal（CD-151b-2 mutator）。

    改名同步 cover_path，繞過 upsert() 的 CASE WHEN，保留 auto_focal/crop_mode/focal_attempted_at。
    """

    def test_update_cover_path_preserve_focal_keeps_focal_fields_unchanged(self, temp_db):
        """DoD①：改名同步 cover_path，focal 三欄（auto_focal/crop_mode/focal_attempted_at）逐字不變。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video_focal_preserve.mp4")
        cover_a = to_file_uri("/cover_preserve_a.jpg")
        cover_b = to_file_uri("/cover_preserve_b.jpg")

        repo.upsert(Video(path=path, title="測試影片", cover_path=cover_a))
        assert repo.update_auto_focal(path, '0.1000,0.2000', cover_a) is True
        assert repo.update_manual_focal(path, '0.3000,0.6000', cover_a) is True

        before = repo.get_by_path(path)
        assert before is not None
        assert before.crop_mode == 'manual'
        assert before.auto_focal == '0.3000,0.6000'
        assert before.focal_attempted_at is not None

        success = repo.update_cover_path_preserve_focal(path, cover_b, cover_a)
        assert success is True

        after = repo.get_by_path(path)
        assert after is not None
        assert after.cover_path == cover_b
        assert after.auto_focal == before.auto_focal
        assert after.crop_mode == before.crop_mode
        assert after.focal_attempted_at == before.focal_attempted_at


class TestGetEmptyFocalCandidates:
    """VideoRepository.get_empty_focal_candidates（Codex PR#105 P2 scan-backfill 修復用）。

    掃描 focal trigger 改用此方法涵蓋「本次掃描 in-scope 但 auto_focal 仍空」的所有
    列（不只 upsert batch），此處直接驗證 SQL 篩選正確性：只回空 auto_focal 且
    path 在 in-scope 集合內的列。
    """


    def test_no_face_result_excluded_from_candidates(self, temp_db):
        """Codex PR#105 P2 核心回歸鎖：auto_focal='' 但 focal_attempted_at 已蓋章
        （偵測跑過、legitimately 無臉）→ 不應再被當「未偵測」回傳，否則每次重掃
        都對同一張無臉封面無限重跑昂貴偵測。"""
        repo = VideoRepository(temp_db)
        p_no_face = to_file_uri("/empty_focal_candidates_no_face.mp4")
        p_never_tried = to_file_uri("/empty_focal_candidates_never_tried.mp4")

        repo.upsert(Video(path=p_no_face, number="SIRO-4444", maker="", cover_path="cover4"))
        repo.upsert(Video(path=p_never_tried, number="SIRO-5555", maker="", cover_path="cover5"))
        # 模擬偵測跑過、legitimately 找不到臉：auto_focal 仍空，但蓋 focal_attempted_at 章
        repo.update_auto_focal(p_no_face, "", "cover4")

        result = repo.get_empty_focal_candidates([p_no_face, p_never_tried])

        assert result == [(p_never_tried, "SIRO-5555", "", "cover5")]


# ============ TASK-123-T1: user_rating preserve-on-conflict + mutators（CD-123-1/3/4）============

class TestUserRatingPreserveOnConflict:
    """user_rating（精選標記）所有權鎖——spec-123 §4.10 標的 P0：漏任一保存點＝使用者
    精選過的影片在下一次掃描/補齊資料/重刮後被無聲清回 0，且不寫 NFO 無法恢復。
    5 支場景對應 plan §3.1：upsert()／upsert_batch()／repath() 分支 2／分支 3 (old 有/new
    無)／分支 3 (old 無/new 有)。另含兩支新 mutator 的 happy/miss/bulk 空/bulk 部分命中。
    """

    # ── 場景 1：upsert() ON CONFLICT 不覆寫 user_rating ─────────────────────

    def test_upsert_preserves_user_rating_on_conflict(self, temp_db):
        repo = VideoRepository(temp_db)
        path = to_file_uri("/user_rating_upsert.mp4")
        repo.upsert(Video(path=path, title="舊片"))
        assert repo.set_user_rating(path, 1) is True

        # 看似新掃描的 Video：user_rating 是 dataclass 預設值 0
        repo.upsert(Video(path=path, title="重掃描新片"))

        result = repo.get_by_path(path)
        assert result is not None
        assert result.user_rating == 1

    # ── 場景 2：upsert_batch() ON CONFLICT 不覆寫 user_rating ────────────────

    def test_upsert_batch_preserves_user_rating_on_conflict(self, temp_db):
        repo = VideoRepository(temp_db)
        path = to_file_uri("/user_rating_upsert_batch.mp4")
        repo.upsert(Video(path=path, title="舊片"))
        assert repo.set_user_rating(path, 1) is True

        repo.upsert_batch([Video(path=path, title="重掃描新片")])

        result = repo.get_by_path(path)
        assert result is not None
        assert result.user_rating == 1

    # ── 場景 3：repath() 分支 2（正常 UPDATE，old 在 DB、new 不在）不覆寫 ────

    def test_repath_normal_update_preserves_user_rating(self, temp_db):
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/user_rating_repath_old.mp4")
        new_uri = to_file_uri("/user_rating_repath_new.mp4")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片"))
        assert repo.set_user_rating(old_uri, 1) is True

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(old_uri, new_uri, Video(path=new_uri, title="重掃描新片"))

        result = repo.get_by_path(new_uri)
        assert result is not None
        assert result.user_rating == 1

    # ── 場景 4：repath() 分支 3（碰撞 delete-merge）old 有精選、new 沒有 → 合併保留 old ──

    def test_repath_collision_merge_keeps_old_rating_when_new_has_none(self, temp_db):
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/user_rating_collision_old_has.mp4")
        new_uri = to_file_uri("/user_rating_collision_old_has_new.mp4")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片"))
            repo.upsert(Video(path=new_uri, title="既有新路徑片"))
        assert repo.set_user_rating(old_uri, 1) is True
        # new_row user_rating 維持預設 0（未精選）

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(old_uri, new_uri, Video(path=new_uri, title="重掃描新片"))

        result = repo.get_by_path(new_uri)
        assert result is not None
        assert result.user_rating == 1, "old 列的精選值必須存活到合併後的列，不被 new 的 0 蓋掉"

    # ── 場景 5：repath() 分支 3 old 沒有、new 有精選 → 合併後仍保留 new 的精選值 ──

    def test_repath_collision_merge_keeps_new_rating_when_old_has_none(self, temp_db):
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/user_rating_collision_new_has.mp4")
        new_uri = to_file_uri("/user_rating_collision_new_has_new.mp4")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片"))
            repo.upsert(Video(path=new_uri, title="既有新路徑片"))
        assert repo.set_user_rating(new_uri, 1) is True
        # old_row user_rating 維持預設 0（未精選）

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(old_uri, new_uri, Video(path=new_uri, title="重掃描新片"))

        result = repo.get_by_path(new_uri)
        assert result is not None
        assert result.user_rating == 1, "new 原本的精選值不該被 old 的 0 蓋掉"


class TestFocalModelColumn:
    """187a-T2：focal_model 欄位寫入／遷移／from_row 白名單。"""

    def test_update_auto_focal_writes_model_and_focal_together(self, temp_db, seed_crop_mode):
        """同一條 UPDATE 寫 auto_focal + focal_model；manual／cover 守衛下兩欄皆不變。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_model_write.mp4")
        cover = to_file_uri("/focal_model_cover.jpg")
        repo.upsert(Video(path=path, title="片", cover_path=cover))
        assert seed_crop_mode(repo, path, "auto") is True

        assert repo.update_auto_focal(path, "0.5000,0.4000", cover, model="X") is True
        assert _select_focal_pair(temp_db, path) == ("0.5000,0.4000", "X")
        # 走真 repo 讀取路徑（_get_columns + from_row），確認未知欄不炸
        assert repo.get_by_path(path) is not None
        assert repo.get_by_id(repo.get_by_path(path).id) is not None

        # cover 不符 → 兩欄皆不變
        assert repo.update_auto_focal(path, "0.9000,0.9000", "other-cover", model="Y") is False
        assert _select_focal_pair(temp_db, path) == ("0.5000,0.4000", "X")

        # manual 守衛 → 兩欄皆不變
        assert repo.update_manual_focal(path, "0.3000,0.6000", cover) is True
        before = _select_focal_pair(temp_db, path)
        assert repo.update_auto_focal(path, "0.1000,0.1000", cover, model="Z") is False
        assert _select_focal_pair(temp_db, path) == before

    def test_old_db_migration_defaults_focal_model_and_survives_rescan(self, tmp_path):
        """舊 DB（無 focal_model）init_db 後預設 local-pigo；重掃保留；get_by_path 不炸。"""
        db_path = tmp_path / "old_no_focal_model.db"
        path = to_file_uri("/old_focal_model.mp4")
        cover = to_file_uri("/old_focal_cover.jpg")
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                number TEXT,
                title TEXT,
                original_title TEXT,
                actresses TEXT,
                maker TEXT,
                director TEXT DEFAULT '',
                series TEXT,
                label TEXT DEFAULT '',
                tags TEXT,
                sample_images TEXT DEFAULT '',
                user_tags TEXT DEFAULT '[]',
                output_dir TEXT DEFAULT '',
                duration INTEGER,
                size_bytes INTEGER,
                cover_path TEXT,
                release_date TEXT,
                mtime REAL,
                nfo_mtime REAL,
                scrape_attempted_at REAL DEFAULT 0,
                auto_focal TEXT DEFAULT '',
                crop_mode TEXT NOT NULL DEFAULT 'auto',
                focal_attempted_at TIMESTAMP DEFAULT NULL,
                user_rating INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT INTO videos (path, title, cover_path) VALUES (?, ?, ?)",
            (path, "舊片", cover),
        )
        conn.commit()
        conn.close()

        init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(videos)").fetchall()}
        assert "focal_model" in cols
        models = [r[0] for r in conn.execute("SELECT focal_model FROM videos").fetchall()]
        assert models == ["local-pigo"]
        conn.close()

        repo = VideoRepository(db_path)
        got = repo.get_by_path(path)
        assert got is not None
        assert got.title == "舊片"

        assert repo.update_auto_focal(path, "0.5000,0.4000", cover, model="X") is True
        assert _select_focal_pair(db_path, path) == ("0.5000,0.4000", "X")

        # 同封面重掃（ON CONFLICT）後 focal_model 保持
        repo.upsert(Video(path=path, title="重掃描", cover_path=cover))
        assert _select_focal_pair(db_path, path) == ("0.5000,0.4000", "X")
        assert repo.get_by_path(path).title == "重掃描"

    def test_videos_columns_whitelist_allows_only_video_fields_plus_focal_model(self, temp_db):
        """結構守衛：videos 欄位集合 ⊆ Video fields ∪ {focal_model}。"""
        conn = sqlite3.connect(str(temp_db))
        try:
            db_cols = {row[1] for row in conn.execute("PRAGMA table_info(videos)").fetchall()}
        finally:
            conn.close()
        allowed = {f.name for f in fields(Video)} | {"focal_model"}
        assert db_cols <= allowed, f"未登記欄位：{sorted(db_cols - allowed)}"




def test_old_db_migration_adds_has_plot(tmp_path):
    """舊 DB（無 has_plot）init_db 後欄位出現、既有列 NULL、get_by_path 不拋、序列化 false。"""
    from web.routers.showcase import _serialize_video

    db_path = tmp_path / "old_no_has_plot.db"
    path = to_file_uri("/old_has_plot.mp4")
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            number TEXT,
            title TEXT,
            original_title TEXT,
            actresses TEXT,
            maker TEXT,
            director TEXT DEFAULT '',
            series TEXT,
            label TEXT DEFAULT '',
            tags TEXT,
            sample_images TEXT DEFAULT '',
            user_tags TEXT DEFAULT '[]',
            output_dir TEXT DEFAULT '',
            duration INTEGER,
            size_bytes INTEGER,
            cover_path TEXT,
            release_date TEXT,
            mtime REAL,
            nfo_mtime REAL,
            scrape_attempted_at REAL DEFAULT 0,
            auto_focal TEXT DEFAULT '',
            crop_mode TEXT NOT NULL DEFAULT 'auto',
            focal_attempted_at TIMESTAMP DEFAULT NULL,
            focal_model TEXT NOT NULL DEFAULT 'local-pigo',
            user_rating INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO videos (path, title) VALUES (?, ?)",
        (path, "舊片"),
    )
    conn.commit()
    conn.close()

    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(videos)").fetchall()}
    assert "has_plot" in cols
    vals = [r[0] for r in conn.execute("SELECT has_plot FROM videos").fetchall()]
    assert vals == [None]
    conn.close()

    repo = VideoRepository(db_path)
    got = repo.get_by_path(path)
    assert got is not None
    assert got.title == "舊片"
    assert got.has_plot is None
    assert _serialize_video(got, {})["has_plot"] is False
