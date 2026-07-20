"""Tests for Actress dataclass and ActressRepository in core/database.py"""
import time
import pytest
from pathlib import Path

from core.database import init_db, Actress, ActressRepository


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture
def repo(db_path: Path) -> ActressRepository:
    return ActressRepository(db_path)


# ---------------------------------------------------------------------------
# save() + get_by_name()
# ---------------------------------------------------------------------------

def test_save_and_get_by_name(repo):
    actress = Actress(name="深田えいみ", name_en="Eimi Fukada", height="163cm")
    repo.save(actress)

    result = repo.get_by_name("深田えいみ")
    assert result is not None
    assert result.name == "深田えいみ"
    assert result.name_en == "Eimi Fukada"
    assert result.height == "163cm"


def test_get_by_name_not_found(repo):
    result = repo.get_by_name("不存在的人")
    assert result is None


# ---------------------------------------------------------------------------
# save() ON CONFLICT: updated_at 更新, created_at 保留（CD-12）
# ---------------------------------------------------------------------------

def test_save_upsert_preserves_created_at(repo):
    actress = Actress(name="三上悠亞", height="157cm")
    repo.save(actress)

    first = repo.get_by_name("三上悠亞")
    assert first is not None
    created_at_first = first.created_at
    updated_at_first = first.updated_at

    # 稍等確保 CURRENT_TIMESTAMP 有機會不同
    time.sleep(1.1)

    actress2 = Actress(name="三上悠亞", height="158cm")
    repo.save(actress2)

    second = repo.get_by_name("三上悠亞")
    assert second is not None
    assert second.height == "158cm"
    # created_at 不變
    assert second.created_at == created_at_first
    # updated_at 應更新（或至少不早於第一次）
    assert second.updated_at >= updated_at_first


# ---------------------------------------------------------------------------
# delete_by_name()
# ---------------------------------------------------------------------------

def test_delete_by_name_existing(repo):
    repo.save(Actress(name="橋本ありな"))
    result = repo.delete_by_name("橋本ありな")
    assert result is True
    assert repo.get_by_name("橋本ありな") is None


def test_delete_by_name_not_existing(repo):
    result = repo.delete_by_name("不存在的人")
    assert result is False


# ---------------------------------------------------------------------------
# get_all()
# ---------------------------------------------------------------------------

def test_get_all_correct_count(repo):
    repo.save(Actress(name="女優A"))
    repo.save(Actress(name="女優B"))
    repo.save(Actress(name="女優C"))

    all_actresses = repo.get_all()
    assert len(all_actresses) == 3


def test_get_all_empty(repo):
    assert repo.get_all() == []


# ---------------------------------------------------------------------------
# exists()
# ---------------------------------------------------------------------------

def test_exists_true(repo):
    repo.save(Actress(name="波多野結衣"))
    assert repo.exists("波多野結衣") is True


def test_exists_false(repo):
    assert repo.exists("不存在的人") is False


# ---------------------------------------------------------------------------
# JSON 欄位（aliases, tags）序列化/反序列化
# ---------------------------------------------------------------------------

def test_json_fields_roundtrip(repo):
    actress = Actress(
        name="夢乃あいか",
        aliases=["ゆめのあいか", "Aika Yumeno"],
        tags=["美少女", "スレンダー"],
    )
    repo.save(actress)

    result = repo.get_by_name("夢乃あいか")
    assert result is not None
    assert result.aliases == ["ゆめのあいか", "Aika Yumeno"]
    assert result.tags == ["美少女", "スレンダー"]


def test_json_fields_empty_list_default(repo):
    actress = Actress(name="新ありな")
    repo.save(actress)

    result = repo.get_by_name("新ありな")
    assert result is not None
    assert result.aliases == []
    assert result.tags == []


# ---------------------------------------------------------------------------
# bust/waist/hip None 值正確處理
# ---------------------------------------------------------------------------

def test_measurements_none(repo):
    actress = Actress(name="測試女優A")
    repo.save(actress)

    result = repo.get_by_name("測試女優A")
    assert result is not None
    assert result.bust is None
    assert result.waist is None
    assert result.hip is None


def test_measurements_with_values(repo):
    actress = Actress(name="測試女優B", bust=88, waist=58, hip=86)
    repo.save(actress)

    result = repo.get_by_name("測試女優B")
    assert result is not None
    assert result.bust == 88
    assert result.waist == 58
    assert result.hip == 86


# ---------------------------------------------------------------------------
# TASK-98a-T4: focal + crop_mode + photo fingerprint（CD-98a-6/-8）
# ---------------------------------------------------------------------------

def test_actress_focal_fields_defaults(repo):
    """新增女優未經 mutator 寫入時，focal 五欄取 dataclass 預設值。
    focal 五欄的 dataclass 預設對齊 SQL column DEFAULT（''/'auto'/''/0/0），
    使「fresh save」與「ALTER 既有 row」共用同一組「未算過」sentinel——98d
    fingerprint 比對不必依 row 來源分辨 None 與 ''/0（見 migration 測試對照）。"""
    repo.save(Actress(name="新女優-預設值"))

    result = repo.get_by_name("新女優-預設值")
    assert result is not None
    assert result.crop_mode == 'auto'
    assert result.auto_focal == ''
    assert result.photo_fp_path == ''
    assert result.photo_fp_mtime_ns == 0
    assert result.photo_fp_size == 0


def test_save_upsert_preserves_focal_fields(repo):
    """save() ON CONFLICT 分支：五個 focal/fp 欄位全保留，不被同 name 的重刮覆蓋
    （鏡射 test_save_upsert_preserves_created_at）。

    Setup 改用直接 SQL UPDATE（103-T1：update_focal_result/update_crop_mode 已刪除，
    鏡射 conftest.py 的 seed_crop_mode 模式——test-only 需求不該讓已收斂的 mutator
    介面再長出方法）。五個 preserve 欄位一次寫齊，語意等同原本兩次 mutator 呼叫的
    疊加結果。"""
    from core.database import get_connection

    repo.save(Actress(name="橋本ありな-focal"))

    conn = get_connection(repo.db_path)
    try:
        conn.execute(
            "UPDATE actresses SET auto_focal = ?, crop_mode = ?, "
            "photo_fp_path = ?, photo_fp_mtime_ns = ?, photo_fp_size = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE name = ?",
            ("0.5,0.4", "default", "/photos/a.jpg", 123456789, 4096, "橋本ありな-focal"),
        )
        conn.commit()
    finally:
        conn.close()

    pre = repo.get_by_name("橋本ありな-focal")
    assert pre is not None
    assert pre.auto_focal == "0.5,0.4"
    assert pre.crop_mode == "default"
    assert pre.photo_fp_path == "/photos/a.jpg"
    assert pre.photo_fp_mtime_ns == 123456789
    assert pre.photo_fp_size == 4096

    # 重刮同 name：incoming actress 帶 dataclass 預設 focal 值（未經 mutator）
    repo.save(Actress(name="橋本ありな-focal", height="160cm"))

    result = repo.get_by_name("橋本ありな-focal")
    assert result is not None
    assert result.height == "160cm"  # 一般欄位正常更新
    assert result.auto_focal == "0.5,0.4"
    assert result.crop_mode == "default"
    assert result.photo_fp_path == "/photos/a.jpg"
    assert result.photo_fp_mtime_ns == 123456789
    assert result.photo_fp_size == 4096


# ---------------------------------------------------------------------------
# TASK-100a-T1: clear_focal / update_manual_focal（CD-98a-6 mutator，spec-100）
# ---------------------------------------------------------------------------

def test_clear_focal_roundtrip(repo):
    """clear_focal happy path：先塞非預設焦點值，clear 後讀回 auto_focal=''、crop_mode='auto'"""
    repo.save(Actress(name="測試女優-clear-focal"))
    assert repo.update_manual_focal("測試女優-clear-focal", "0.5,0.4") is True

    ok = repo.clear_focal("測試女優-clear-focal")
    assert ok is True

    result = repo.get_by_name("測試女優-clear-focal")
    assert result is not None
    assert result.auto_focal == ''
    assert result.crop_mode == 'auto'


def test_clear_focal_missing_name_returns_false(repo):
    assert repo.clear_focal("不存在的女優-clear-focal") is False


def test_update_manual_focal_roundtrip(repo):
    """update_manual_focal happy path：寫入後讀回 auto_focal=focal、crop_mode='manual'"""
    repo.save(Actress(name="測試女優-manual-focal"))

    ok = repo.update_manual_focal("測試女優-manual-focal", "0.5,0.4")
    assert ok is True

    result = repo.get_by_name("測試女優-manual-focal")
    assert result is not None
    assert result.auto_focal == "0.5,0.4"
    assert result.crop_mode == "manual"


def test_update_manual_focal_missing_name_returns_false(repo):
    assert repo.update_manual_focal("不存在的女優-manual-focal", "0.5,0.4") is False


def test_update_manual_focal_empty_string_not_validated(repo):
    """mutator 層不驗格式（Opus 裁決）：空字串焦點照寫，格式驗證是呼叫端（T4 parse_focal）的責任"""
    repo.save(Actress(name="測試女優-manual-focal-empty"))

    ok = repo.update_manual_focal("測試女優-manual-focal-empty", "")
    assert ok is True

    result = repo.get_by_name("測試女優-manual-focal-empty")
    assert result is not None
    assert result.auto_focal == ''
    assert result.crop_mode == 'manual'


def test_save_upsert_preserves_manual_focal_and_clear_focal(repo):
    """save() ON CONFLICT 不覆寫 clear_focal/update_manual_focal 寫入的值
    （鏡射 test_save_upsert_preserves_focal_fields，涵蓋新 mutator 的寫入路徑）"""
    repo.save(Actress(name="測試女優-preserve-manual"))
    assert repo.update_manual_focal("測試女優-preserve-manual", "0.3,0.7") is True

    # 重刮同 name：incoming actress 帶 dataclass 預設 focal 值（未經 mutator）
    repo.save(Actress(name="測試女優-preserve-manual", height="160cm"))

    result = repo.get_by_name("測試女優-preserve-manual")
    assert result is not None
    assert result.height == "160cm"
    assert result.auto_focal == "0.3,0.7"
    assert result.crop_mode == "manual"


def _traced_statements(repo) -> list:
    """呼叫端輔助：wrap repo._get_connection 掛上 conn.set_trace_callback，
    收集真實送進 SQLite 的 SQL 陳述式（零 mock，走完整 production 路徑）。
    回傳值是一個 list，供呼叫端在呼叫 mutator 前後檢查其內容。"""
    statements: list = []
    original_get_connection = repo._get_connection

    def _wrapped():
        conn = original_get_connection()
        conn.set_trace_callback(statements.append)
        return conn

    repo._get_connection = _wrapped
    return statements


def test_clear_focal_single_update_atomicity(repo):
    """Single-UPDATE atomicity（Opus 裁決）：conn.set_trace_callback 觀察真實 SQL，
    clear_focal 恰好送出一條 UPDATE，且該條同時含 auto_focal 與 crop_mode"""
    repo.save(Actress(name="測試女優-clear-atomic"))
    statements = _traced_statements(repo)

    assert repo.clear_focal("測試女優-clear-atomic") is True

    updates = [s for s in statements if s.strip().upper().startswith("UPDATE")]
    assert len(updates) == 1
    assert "auto_focal" in updates[0]
    assert "crop_mode" in updates[0]
    # G2：既有 mutator 慣例——updated_at 隨同一條 UPDATE 一起寫
    assert "updated_at" in updates[0]


def test_update_manual_focal_single_update_atomicity(repo):
    """Single-UPDATE atomicity（Opus 裁決）：update_manual_focal 恰好送出一條 UPDATE，
    且該條同時含 auto_focal 與 crop_mode"""
    repo.save(Actress(name="測試女優-manual-atomic"))
    statements = _traced_statements(repo)

    assert repo.update_manual_focal("測試女優-manual-atomic", "0.5,0.4") is True

    updates = [s for s in statements if s.strip().upper().startswith("UPDATE")]
    assert len(updates) == 1
    assert "auto_focal" in updates[0]
    assert "crop_mode" in updates[0]
    # G2：既有 mutator 慣例——updated_at 隨同一條 UPDATE 一起寫
    assert "updated_at" in updates[0]


def test_get_by_name_and_get_all_smoke_with_dynamic_columns(repo):
    """動態 _get_columns()（26 欄）與 SELECT * 長度一致，get_by_name/get_all 不 ValueError
    （Codex P1：手寫 21 欄清單在 ALTER +5 欄後會令 from_row 的 zip(strict=True) 爆炸）"""
    repo.save(Actress(name="女優-smoke-1"))
    repo.save(Actress(name="女優-smoke-2"))

    by_name = repo.get_by_name("女優-smoke-1")
    assert by_name is not None

    all_actresses = repo.get_all()
    assert len(all_actresses) == 2
