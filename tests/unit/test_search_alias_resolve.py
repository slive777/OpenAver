"""
T4 TDD-lite — alias-aware actress lookup & video count

Cases:
1. alias resolve → DB hit (is_favorite=True)
2. alias resolve → all miss → orchestrator (is_favorite=False)
3. no alias record → resolve returns {name} → direct DB hit → behaviour unchanged
4. count_videos_for_actress_names multi-name deduplicated (DISTINCT)
5. count_videos_for_actress_names(set()) → 0
6. count_videos_for_actress(name) delegates to _names version
"""
import sqlite3
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import Optional, List


# ---------------------------------------------------------------------------
# Minimal Actress stub
# ---------------------------------------------------------------------------

@dataclass
class _Actress:
    name: str
    name_en: Optional[str] = None
    birth: Optional[str] = None
    height: Optional[str] = None
    cup: Optional[str] = None
    bust: Optional[int] = None
    waist: Optional[int] = None
    hip: Optional[int] = None
    hometown: Optional[str] = None
    hobby: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    agency: Optional[str] = None
    debut_work: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    nickname: Optional[str] = None
    blog_url: Optional[str] = None
    official_url: Optional[str] = None
    photo_url: Optional[str] = None
    photo_source: Optional[str] = None
    primary_text_source: Optional[str] = None
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_actress(name: str) -> _Actress:
    return _Actress(name=name)


# ---------------------------------------------------------------------------
# Case 1 — alias resolve → DB hit → is_favorite=True
# ---------------------------------------------------------------------------

class TestFetchActressProfileWithDbAliasHit:
    """resolve('橋本ありな') → {'橋本ありな','新ありな'}, get_by_name loop finds '新ありな'"""

    def _call(self, monkeypatch):
        """Patch AliasRepository + ActressRepository in core.database (where they are imported from)."""
        actress_obj = _make_actress("新ありな")

        alias_repo_mock = MagicMock()
        alias_repo_mock.resolve.return_value = {"橋本ありな", "新ありな"}

        actress_repo_mock = MagicMock()
        # first call returns None, second returns the actress
        def get_by_name_side(n):
            if n == "新ありな":
                return actress_obj
            return None
        actress_repo_mock.get_by_name.side_effect = get_by_name_side

        def fake_actress_to_response(actress, video_count=0):
            return {"name": actress.name, "photo_url": None}

        with patch("core.database.AliasRepository", return_value=alias_repo_mock), \
             patch("core.database.ActressRepository", return_value=actress_repo_mock), \
             patch("core.database.init_db"), \
             patch("web.routers.actress._actress_to_response", side_effect=fake_actress_to_response):
            from web.routers.search import _fetch_actress_profile_with_db
            return _fetch_actress_profile_with_db("橋本ありな", [])

    def test_returns_is_favorite_true(self, monkeypatch):
        result = self._call(monkeypatch)
        assert result is not None
        assert result.get("is_favorite") is True

    def test_returns_correct_name(self, monkeypatch):
        result = self._call(monkeypatch)
        assert result.get("name") == "新ありな"


# ---------------------------------------------------------------------------
# Case 2 — alias resolve → all miss → orchestrator → is_favorite=False
# ---------------------------------------------------------------------------

class TestFetchActressProfileWithDbAliasMiss:
    """resolve returns {'unknown'}, DB miss, orchestrator called → is_favorite=False"""

    def _call(self, monkeypatch):
        alias_repo_mock = MagicMock()
        alias_repo_mock.resolve.return_value = {"unknown"}

        actress_repo_mock = MagicMock()
        actress_repo_mock.get_by_name.return_value = None

        orchestrator_result = MagicMock()
        orchestrator_result.data = {
            "name": "unknown",
            "text": {},
            "photo_url": None,
            "photo_source": None,
            "primary_text_source": None,
        }

        def fake_flatten_aliases(raw):
            return []

        with patch("core.database.AliasRepository", return_value=alias_repo_mock), \
             patch("core.database.ActressRepository", return_value=actress_repo_mock), \
             patch("core.database.init_db"), \
             patch("core.scrapers.actress.orchestrator.get_actress_profile",
                   return_value=orchestrator_result), \
             patch("web.routers.actress._flatten_aliases",
                   side_effect=fake_flatten_aliases):
            from web.routers.search import _fetch_actress_profile_with_db
            return _fetch_actress_profile_with_db("unknown", [])

    def test_returns_is_favorite_false(self, monkeypatch):
        result = self._call(monkeypatch)
        assert result is not None
        assert result.get("is_favorite") is False


# ---------------------------------------------------------------------------
# Case 3 — no alias record → {name} → direct DB hit → is_favorite=True
# ---------------------------------------------------------------------------

class TestFetchActressProfileNoAlias:
    """resolve('田中xxx') → {'田中xxx'} (miss), DB直接命中 → is_favorite=True"""

    def _call(self, monkeypatch):
        actress_obj = _make_actress("田中xxx")

        alias_repo_mock = MagicMock()
        alias_repo_mock.resolve.return_value = {"田中xxx"}

        actress_repo_mock = MagicMock()
        actress_repo_mock.get_by_name.return_value = actress_obj

        def fake_actress_to_response(actress, video_count=0):
            return {"name": actress.name, "photo_url": None}

        with patch("core.database.AliasRepository", return_value=alias_repo_mock), \
             patch("core.database.ActressRepository", return_value=actress_repo_mock), \
             patch("core.database.init_db"), \
             patch("web.routers.actress._actress_to_response", side_effect=fake_actress_to_response):
            from web.routers.search import _fetch_actress_profile_with_db
            return _fetch_actress_profile_with_db("田中xxx", [])

    def test_returns_is_favorite_true(self, monkeypatch):
        result = self._call(monkeypatch)
        assert result is not None
        assert result.get("is_favorite") is True

    def test_resolve_called_once_with_name(self, monkeypatch):
        actress_obj = _make_actress("田中xxx")

        alias_repo_mock = MagicMock()
        alias_repo_mock.resolve.return_value = {"田中xxx"}

        actress_repo_mock = MagicMock()
        actress_repo_mock.get_by_name.return_value = actress_obj

        def fake_actress_to_response(actress, video_count=0):
            return {"name": actress.name, "photo_url": None}

        with patch("core.database.AliasRepository", return_value=alias_repo_mock), \
             patch("core.database.ActressRepository", return_value=actress_repo_mock), \
             patch("core.database.init_db"), \
             patch("web.routers.actress._actress_to_response", side_effect=fake_actress_to_response):
            from web.routers.search import _fetch_actress_profile_with_db
            _fetch_actress_profile_with_db("田中xxx", [])

        alias_repo_mock.resolve.assert_called_once_with("田中xxx")


# ---------------------------------------------------------------------------
# Case 4 — count_videos_for_actress_names: multi-name deduplication
# ---------------------------------------------------------------------------

class TestCountVideosForActressNamesMultiName:
    """Video A has actresses: ["新ありな","橋本ありな"]. Query both → count=1 (DISTINCT)"""

    @pytest.fixture
    def db_with_video(self, tmp_path):
        from core.database import init_db
        import json
        db_path = tmp_path / "test_count.db"
        init_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        # Insert one video with both alias names in actresses JSON
        conn.execute(
            """INSERT INTO videos (path, number, title, actresses)
               VALUES (?, ?, ?, ?)""",
            (
                "/fake/video.mp4",
                "TEST-001",
                "Test Title",
                json.dumps(["新ありな", "橋本ありな"]),
            )
        )
        conn.commit()
        conn.close()
        return db_path

    def test_count_distinct_single_video(self, db_with_video):
        from core.database import ActressRepository
        repo = ActressRepository(db_path=db_with_video)
        count = repo.count_videos_for_actress_names({"新ありな", "橋本ありな"})
        assert count == 1, f"Expected 1 (DISTINCT), got {count}"

    def test_count_two_different_videos(self, db_with_video):
        """Two videos each with one name → count=2"""
        import json
        conn = sqlite3.connect(str(db_with_video))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """INSERT INTO videos (path, number, title, actresses)
               VALUES (?, ?, ?, ?)""",
            ("/fake/video2.mp4", "TEST-002", "Test2",
             json.dumps(["河北彩伽"]))
        )
        conn.commit()
        conn.close()

        from core.database import ActressRepository
        repo = ActressRepository(db_path=db_with_video)
        # Both videos: TEST-001 (新ありな/橋本ありな) and TEST-002 (河北彩伽)
        count = repo.count_videos_for_actress_names({"新ありな", "河北彩伽"})
        assert count == 2


# ---------------------------------------------------------------------------
# Case 5 — count_videos_for_actress_names(set()) → 0
# ---------------------------------------------------------------------------

class TestCountVideosForActressNamesEmpty:
    def test_empty_set_returns_zero(self, tmp_path):
        from core.database import init_db, ActressRepository
        db_path = tmp_path / "test_empty.db"
        init_db(db_path)
        repo = ActressRepository(db_path=db_path)
        result = repo.count_videos_for_actress_names(set())
        assert result == 0


# ---------------------------------------------------------------------------
# Case 6 — count_videos_for_actress(name) delegates to _names version
# ---------------------------------------------------------------------------

class TestCountVideosForActressDelegates:
    """count_videos_for_actress('X') == count_videos_for_actress_names({'X'})"""

    @pytest.fixture
    def db(self, tmp_path):
        from core.database import init_db
        import json
        db_path = tmp_path / "test_delegate.db"
        init_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """INSERT INTO videos (path, number, title, actresses)
               VALUES (?, ?, ?, ?)""",
            ("/fake/v.mp4", "X-001", "X Title", json.dumps(["TestAct"]))
        )
        conn.commit()
        conn.close()
        return db_path

    def test_single_name_delegates(self, db):
        from core.database import ActressRepository
        repo = ActressRepository(db_path=db)
        by_single = repo.count_videos_for_actress("TestAct")
        by_names = repo.count_videos_for_actress_names({"TestAct"})
        assert by_single == by_names
        assert by_single == 1

    def test_unknown_name_returns_zero(self, db):
        from core.database import ActressRepository
        repo = ActressRepository(db_path=db)
        assert repo.count_videos_for_actress("NoSuchName") == 0
        assert repo.count_videos_for_actress_names({"NoSuchName"}) == 0
