"""Tests for Actress dataclass and ActressRepository in core/database.py"""
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


# ---------------------------------------------------------------------------
# save() ON CONFLICT: updated_at 更新, created_at 保留（CD-12）
# ---------------------------------------------------------------------------

def test_save_upsert_preserves_created_at(repo):
    from datetime import datetime
    from core.database import get_connection

    actress = Actress(name="三上悠亞", height="157cm")
    repo.save(actress)

    first = repo.get_by_name("三上悠亞")
    assert first is not None

    # 直接把 created_at/updated_at 改寫成明確的過去固定值，取代原本的固定 1.1 秒等待：
    # 第二次 save() 的 updated_at 必為「現在」，保證嚴格大於這個過去值，
    # 不依賴真實時間流逝或 CURRENT_TIMESTAMP 的秒級精度。
    old_ts = "2000-01-01 00:00:00"
    conn = get_connection(repo.db_path)
    try:
        conn.execute(
            "UPDATE actresses SET created_at = ?, updated_at = ? WHERE name = ?",
            (old_ts, old_ts, "三上悠亞"),
        )
        conn.commit()
    finally:
        conn.close()

    actress2 = Actress(name="三上悠亞", height="158cm")
    repo.save(actress2)

    second = repo.get_by_name("三上悠亞")
    assert second is not None
    assert second.height == "158cm"
    # created_at 不變（save() 的 ON CONFLICT 不更新 created_at 欄位，比對寫入後的舊值）
    assert second.created_at == datetime.fromisoformat(old_ts)
    # updated_at 應更新，且嚴格大於改寫前寫入的舊值
    assert second.updated_at > datetime.fromisoformat(old_ts)


# ---------------------------------------------------------------------------
# delete_by_name()
# ---------------------------------------------------------------------------

def test_delete_by_name_existing(repo):
    repo.save(Actress(name="橋本ありな"))
    result = repo.delete_by_name("橋本ありな")
    assert result is True
    assert repo.get_by_name("橋本ありな") is None


# ---------------------------------------------------------------------------
# get_all()
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# exists()
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# bust/waist/hip None 值正確處理
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TASK-98a-T4: focal + crop_mode + photo fingerprint（CD-98a-6/-8）
# ---------------------------------------------------------------------------


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


def test_update_manual_focal_roundtrip(repo):
    """update_manual_focal happy path：寫入後讀回 auto_focal=focal、crop_mode='manual'"""
    repo.save(Actress(name="測試女優-manual-focal"))

    ok = repo.update_manual_focal("測試女優-manual-focal", "0.5,0.4")
    assert ok is True

    result = repo.get_by_name("測試女優-manual-focal")
    assert result is not None
    assert result.auto_focal == "0.5,0.4"
    assert result.crop_mode == "manual"


# ---------------------------------------------------------------------------
# TASK-157-T5: update_fields（CD-157-6）
# ---------------------------------------------------------------------------

def test_update_fields_only_changes_given_column(repo):
    actress = Actress(name="深田えいみ", height="158cm", cup="G", tags=["美少女"])
    repo.save(actress)

    assert repo.update_fields("深田えいみ", {"height": "160cm"}) is True

    result = repo.get_by_name("深田えいみ")
    assert result is not None
    assert result.height == "160cm"
    assert result.cup == "G"
    assert result.tags == ["美少女"]


def test_update_fields_tags_roundtrip_append(repo):
    actress = Actress(name="夢乃あいか", tags=["美少女"])
    repo.save(actress)

    assert repo.update_fields("夢乃あいか", {"tags": ["美少女", "スレンダー"]}) is True

    result = repo.get_by_name("夢乃あいか")
    assert result is not None
    assert isinstance(result.tags, list)
    assert result.tags == ["美少女", "スレンダー"]


def test_face_result_dies_with_photo_change(repo, tmp_path, monkeypatch):
    """換照片後舊結果失效，並清除焦點與照片指紋。"""
    from core.actress_face import current_photo_fp, result_is_valid

    directory = tmp_path / "Gfriends"
    monkeypatch.setattr('core.actress_photo.GFRIENDS_DIR', directory)
    directory.mkdir()
    path = directory / "face.jpg"
    path.write_bytes(b"photo")
    repo.save(Actress(name="face"))
    stat = path.stat()
    fp = current_photo_fp("face")
    assert fp == (str(path), stat.st_mtime_ns, stat.st_size)
    assert repo.update_face_result("face", "found", "0.5,0.4,0.3", "model", *fp)
    actress = repo.get_by_name("face")
    assert result_is_valid(actress, current_photo_fp("face"))
    assert repo.update_face_result("face", "unsure", "", "model", *fp)
    actress = repo.get_by_name("face")
    assert result_is_valid(actress, fp)
    assert not result_is_valid(actress, (fp[0] + "x", fp[1], fp[2]))
    assert not result_is_valid(actress, (fp[0], fp[1] + 1, fp[2]))
    assert not result_is_valid(actress, (fp[0], fp[1], fp[2] + 1))
    assert not result_is_valid(actress, None)
    actress.face_status = ''
    assert not result_is_valid(actress, fp)
    assert repo.update_manual_focal("face", "0.5000,0.4000")
    assert repo.clear_focal("face")
    actress = repo.get_by_name("face")
    assert (actress.auto_focal, actress.crop_mode) == ('', 'auto')
    assert (actress.face_status, actress.face_box, actress.face_model) == ('', '', '')
    assert (actress.photo_fp_path, actress.photo_fp_mtime_ns, actress.photo_fp_size) == ('', 0, 0)
    assert repo.clear_focal("不存在") is False


def test_save_keeps_face_result(repo):
    """重新儲存女優資料時保留既有臉部結果。"""
    repo.save(Actress(name="face-save"))
    assert repo.update_face_result("face-save", "found", "box", "model", "path", 123, 456)
    repo.save(Actress(name="face-save", height="160cm"))
    actress = repo.get_by_name("face-save")
    assert actress.height == "160cm"
    assert (actress.face_status, actress.face_box, actress.face_model) == ("found", "box", "model")
    assert (actress.photo_fp_path, actress.photo_fp_mtime_ns, actress.photo_fp_size) == ("path", 123, 456)


def test_update_face_result_leaves_manual_focal_alone(repo):
    """背景寫入臉部結果時保留使用者設定的手動焦點。"""
    repo.save(Actress(name="face-manual"))
    assert repo.update_manual_focal("face-manual", "0.5000,0.4000")
    before = repo.get_by_name("face-manual")
    baseline = (before.auto_focal, before.crop_mode)
    assert repo.update_face_result("face-manual", "found", "box", "model", "path", 123, 456) is True
    actress = repo.get_by_name("face-manual")
    assert (actress.auto_focal, actress.crop_mode) == baseline
    assert (actress.face_status, actress.face_box, actress.face_model) == ("found", "box", "model")
    assert (actress.photo_fp_path, actress.photo_fp_mtime_ns, actress.photo_fp_size) == ("path", 123, 456)
    assert repo.update_face_result("不存在", "found", "box", "model", "path", 123, 456) is False
    assert repo.get_by_name("不存在") is None


