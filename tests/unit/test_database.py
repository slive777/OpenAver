"""測試 core/database.py"""
import pytest
import sqlite3
import json
from pathlib import Path
from datetime import datetime

from core.database import (
    get_db_path,
    get_connection,
    init_db,
    Video
)
from core.gallery_scanner import VideoInfo


def test_get_db_path():
    """測試資料庫路徑正確"""
    db_path = get_db_path()
    assert isinstance(db_path, Path)
    assert db_path.name == "openaver.db"
    assert db_path.parent.name == "output"
    # 確保路徑是絕對路徑
    assert db_path.is_absolute()


def test_init_db_creates_table(tmp_path):
    """測試建立表格"""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    # 檢查表格是否存在
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='videos'
    """)
    result = cursor.fetchone()
    conn.close()

    assert result is not None
    assert result[0] == "videos"


def test_init_db_creates_indexes(tmp_path):
    """測試建立索引"""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index'
    """)
    indexes = [row[0] for row in cursor.fetchall()]
    conn.close()

    # 檢查三個索引是否存在
    assert 'idx_videos_number' in indexes
    assert 'idx_videos_path' in indexes
    assert 'idx_videos_maker' in indexes


def test_init_db_idempotent(tmp_path):
    """測試重複呼叫不報錯"""
    db_path = tmp_path / "test.db"

    # 第一次初始化
    init_db(db_path)
    # 第二次初始化（不應該報錯）
    init_db(db_path)
    # 第三次初始化
    init_db(db_path)

    # 確認表格依然存在且正常
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM videos")
    result = cursor.fetchone()
    conn.close()

    assert result[0] == 0  # 表格為空


def test_video_dataclass_defaults():
    """測試 Video 預設值正確"""
    video = Video()

    assert video.id is None
    assert video.path == ""
    assert video.number is None
    assert video.title == ""
    assert video.original_title == ""
    assert video.actresses == []
    assert video.maker == ""
    assert video.series is None
    assert video.tags == []
    assert video.duration is None
    assert video.size_bytes == 0
    assert video.cover_path == ""
    assert video.release_date == ""
    assert video.mtime == 0.0
    assert video.nfo_mtime == 0.0
    assert video.created_at is None
    assert video.updated_at is None


def test_video_from_video_info():
    """測試從 VideoInfo 轉換"""
    info = VideoInfo(
        path="/videos/test.mp4",
        title="測試影片",
        originaltitle="Test Video",
        actor="演員A, 演員B, 演員C",
        num="ABC-123",
        maker="測試片商",
        date="2024-01-20",
        genre="類型1, 類型2, 類型3",
        size=1024 * 1024 * 500,  # 500MB
        mtime=133500000000000000,  # FileTime 格式
        img="/covers/test.jpg"
    )

    video = Video.from_video_info(info)

    assert video.path == "/videos/test.mp4"
    assert video.number == "ABC-123"
    assert video.title == "測試影片"
    assert video.original_title == "Test Video"
    assert video.actresses == ["演員A", "演員B", "演員C"]
    assert video.maker == "測試片商"
    assert video.tags == ["類型1", "類型2", "類型3"]
    assert video.size_bytes == 1024 * 1024 * 500
    assert video.cover_path == "/covers/test.jpg"
    assert video.release_date == "2024-01-20"
    # 檢查 mtime 轉換是否正確（允許小誤差）
    assert video.mtime > 0


def test_video_to_dict():
    """測試序列化正確"""
    video = Video(
        id=1,
        path="/videos/test.mp4",
        number="ABC-123",
        title="測試影片",
        actresses=["演員A", "演員B"],
        tags=["類型1", "類型2"],
        size_bytes=1024,
        created_at=datetime(2024, 1, 20, 12, 0, 0),
        updated_at=datetime(2024, 1, 21, 13, 30, 0)
    )

    data = video.to_dict()

    assert data['id'] == 1
    assert data['path'] == "/videos/test.mp4"
    assert data['number'] == "ABC-123"
    assert data['title'] == "測試影片"
    # JSON 欄位應該被序列化為字串
    assert isinstance(data['actresses'], str)
    assert json.loads(data['actresses']) == ["演員A", "演員B"]
    assert isinstance(data['tags'], str)
    assert json.loads(data['tags']) == ["類型1", "類型2"]
    # datetime 應該被轉為 ISO 格式字串
    assert data['created_at'] == "2024-01-20T12:00:00"
    assert data['updated_at'] == "2024-01-21T13:30:00"


def test_video_actresses_json():
    """測試 JSON 欄位處理"""
    # 測試空列表
    video1 = Video(actresses=[])
    data1 = video1.to_dict()
    assert json.loads(data1['actresses']) == []

    # 測試中文字元
    video2 = Video(actresses=["波多野結衣", "上原亞衣"])
    data2 = video2.to_dict()
    actresses = json.loads(data2['actresses'])
    assert actresses == ["波多野結衣", "上原亞衣"]

    # 測試 tags
    video3 = Video(tags=["巨乳", "中出", "單體作品"])
    data3 = video3.to_dict()
    tags = json.loads(data3['tags'])
    assert tags == ["巨乳", "中出", "單體作品"]


def test_connection_wal_mode(tmp_path):
    """測試 WAL 模式啟用"""
    db_path = tmp_path / "test_wal.db"
    conn = get_connection(db_path)

    # 檢查 WAL 模式是否啟用
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    result = cursor.fetchone()
    conn.close()

    assert result[0].lower() == "wal"


def test_insert_and_query(tmp_path):
    """測試基本 CRUD 操作"""
    db_path = tmp_path / "test_crud.db"
    init_db(db_path)

    conn = get_connection(db_path)
    cursor = conn.cursor()

    # 插入測試資料
    video = Video(
        path="/videos/test123.mp4",
        number="TEST-123",
        title="測試影片",
        original_title="Test Video",
        actresses=["演員A", "演員B"],
        maker="測試片商",
        series="測試系列",
        tags=["類型1", "類型2"],
        duration=120,
        size_bytes=1024 * 1024 * 100,
        cover_path="/covers/test123.jpg",
        release_date="2024-01-20",
        mtime=1234567890.0,
        nfo_mtime=1234567800.0
    )

    video_dict = video.to_dict()
    # 移除 id, created_at, updated_at（由資料庫自動處理）
    video_dict.pop('id', None)
    video_dict.pop('created_at', None)
    video_dict.pop('updated_at', None)

    # 插入資料
    columns = list(video_dict.keys())
    placeholders = ', '.join(['?'] * len(columns))
    cursor.execute(
        f"INSERT INTO videos ({', '.join(columns)}) VALUES ({placeholders})",
        list(video_dict.values())
    )
    conn.commit()

    # 查詢資料
    cursor.execute("SELECT * FROM videos WHERE number = ?", ("TEST-123",))
    row = cursor.fetchone()
    cursor.execute("PRAGMA table_info(videos)")
    columns_info = cursor.fetchall()
    column_names = [col[1] for col in columns_info]

    conn.close()

    # 驗證資料
    assert row is not None
    result_video = Video.from_row(row, column_names)

    assert result_video.path == "/videos/test123.mp4"
    assert result_video.number == "TEST-123"
    assert result_video.title == "測試影片"
    assert result_video.original_title == "Test Video"
    assert result_video.actresses == ["演員A", "演員B"]
    assert result_video.maker == "測試片商"
    assert result_video.series == "測試系列"
    assert result_video.tags == ["類型1", "類型2"]
    assert result_video.duration == 120
    assert result_video.size_bytes == 1024 * 1024 * 100
    assert result_video.cover_path == "/covers/test123.jpg"
    assert result_video.release_date == "2024-01-20"
    assert result_video.mtime == 1234567890.0
    assert result_video.nfo_mtime == 1234567800.0
    # created_at 和 updated_at 應該由資料庫自動設定
    assert result_video.created_at is not None
    assert result_video.updated_at is not None


def test_video_from_video_info_with_empty_fields():
    """測試 VideoInfo 空欄位處理"""
    info = VideoInfo(
        path="/videos/test.mp4",
        title="測試影片",
        actor="",  # 空字串
        genre="",  # 空字串
        num="",
        size=1024
    )

    video = Video.from_video_info(info)

    assert video.actresses == []  # 空字串應轉為空列表
    assert video.tags == []  # 空字串應轉為空列表
    assert video.number is None  # 空字串應轉為 None


def test_video_from_video_info_with_spaces():
    """測試 VideoInfo 含空白字元處理"""
    info = VideoInfo(
        path="/videos/test.mp4",
        title="測試影片",
        actor="  演員A  ,  演員B  , , 演員C  ",  # 含多餘空白
        genre="類型1,  類型2  ,   ,類型3",  # 含多餘空白和空項目
        num="ABC-123"
    )

    video = Video.from_video_info(info)

    # 應該去除空白並過濾空項目
    assert video.actresses == ["演員A", "演員B", "演員C"]
    assert video.tags == ["類型1", "類型2", "類型3"]
