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
    （鏡射 test_save_upsert_preserves_created_at，這是本 task 最貴的一條——Codex P1）"""
    repo.save(Actress(name="橋本ありな-focal"))

    assert repo.update_focal_result(
        "橋本ありな-focal", "0.5,0.4", ("/photos/a.jpg", 123456789, 4096)
    ) is True
    assert repo.update_crop_mode("橋本ありな-focal", "default") is True

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


def test_update_focal_result_roundtrip(repo):
    """update_focal_result() 原子寫入：auto_focal + photo_fp_* 三值一致讀回"""
    repo.save(Actress(name="測試女優-focal-result"))

    ok = repo.update_focal_result(
        "測試女優-focal-result", "0.6,0.3", ("/photos/b.png", 987654321, 2048)
    )
    assert ok is True

    result = repo.get_by_name("測試女優-focal-result")
    assert result is not None
    assert result.auto_focal == "0.6,0.3"
    assert result.photo_fp_path == "/photos/b.png"
    assert result.photo_fp_mtime_ns == 987654321
    assert result.photo_fp_size == 2048


def test_update_focal_result_missing_name_returns_false(repo):
    ok = repo.update_focal_result(
        "不存在的女優-focal", "0.1,0.1", ("/photos/x.jpg", 1, 1)
    )
    assert ok is False


def test_update_crop_mode_roundtrip(repo):
    repo.save(Actress(name="測試女優-crop-mode"))

    assert repo.update_crop_mode("測試女優-crop-mode", "default") is True

    result = repo.get_by_name("測試女優-crop-mode")
    assert result is not None
    assert result.crop_mode == "default"


def test_update_crop_mode_missing_name_returns_false(repo):
    assert repo.update_crop_mode("不存在的女優-crop-mode", "default") is False


def test_get_by_name_and_get_all_smoke_with_dynamic_columns(repo):
    """動態 _get_columns()（26 欄）與 SELECT * 長度一致，get_by_name/get_all 不 ValueError
    （Codex P1：手寫 21 欄清單在 ALTER +5 欄後會令 from_row 的 zip(strict=True) 爆炸）"""
    repo.save(Actress(name="女優-smoke-1"))
    repo.save(Actress(name="女優-smoke-2"))

    by_name = repo.get_by_name("女優-smoke-1")
    assert by_name is not None

    all_actresses = repo.get_all()
    assert len(all_actresses) == 2
