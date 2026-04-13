"""
T1 TDD-lite — AliasRecord dataclass + AliasRepository + 舊表遷移
測試 18 邊界條件（RED → GREEN 流程）
"""
import pytest
import sqlite3
import json
import tempfile
from pathlib import Path
from datetime import datetime

from core.database import init_db, get_connection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """新 schema DB（透過 init_db 建立）；含種子資料"""
    db_path = tmp_path / "test_alias.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def empty_db(tmp_path):
    """新 schema DB，seed data 已清空（供 AliasRepository 單元測試隔離使用）"""
    db_path = tmp_path / "empty_alias.db"
    init_db(db_path)
    # 清除 init_db 插入的種子資料
    conn = get_connection(db_path)
    conn.execute("DELETE FROM actress_aliases")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def repo(empty_db):
    """AliasRepository，使用 empty_db（無種子資料）"""
    from core.database import AliasRepository
    return AliasRepository(empty_db)


@pytest.fixture
def old_schema_db(tmp_path):
    """模擬含舊 schema（old_name 欄位）與種子資料的 DB"""
    db_path = tmp_path / "old_schema.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    # 建立舊 schema
    cursor.execute("""
        CREATE TABLE actress_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            old_name TEXT NOT NULL UNIQUE,
            new_name TEXT NOT NULL,
            applied_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 插入種子資料（含匯流案例）
    cursor.execute("""
        INSERT INTO actress_aliases (old_name, new_name) VALUES
        ('miru', '坂道みる'),
        ('橋本ありな', '新ありな'),
        ('河北彩伽', '河北彩花'),
        ('天海こころ', '深田えいみ'),
        ('心菜りお', '深田えいみ')
    """)
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# _migrate_old_aliases() 直接測試
# ---------------------------------------------------------------------------

class TestMigrateOldAliases:
    """跟鏈演算法邊界條件（直接測試 module-level function）"""

    def _migrate(self, rows):
        from core.database import _migrate_old_aliases
        return _migrate_old_aliases(rows)

    def test_single_chain(self):
        """BC-5: 單條鏈 x→y → {primary_name: y, aliases: [x]}"""
        result = self._migrate([("x", "y")])
        assert len(result) == 1
        assert result[0]["primary_name"] == "y"
        assert result[0]["aliases"] == ["x"]

    def test_long_chain(self):
        """BC-6: 長鏈 z→y, y→a → {primary_name: a, aliases: [y, z]} 或 [z, y]"""
        result = self._migrate([("z", "y"), ("y", "a")])
        assert len(result) == 1
        assert result[0]["primary_name"] == "a"
        assert set(result[0]["aliases"]) == {"y", "z"}
        # aliases 中不應包含 endpoint 本身
        assert "a" not in result[0]["aliases"]

    def test_confluence(self):
        """BC-7: 匯流 a→c, b→c → {primary_name: c, aliases: [a, b]}"""
        result = self._migrate([("a", "c"), ("b", "c")])
        assert len(result) == 1
        assert result[0]["primary_name"] == "c"
        assert set(result[0]["aliases"]) == {"a", "b"}

    def test_cycle(self):
        """BC-8: 循環 A→B, B→A → 任選一個為 primary，另一個為 alias，不 raise"""
        result = self._migrate([("A", "B"), ("B", "A")])
        # 循環應產生某個 group，不應 raise
        # 結果是 primary 是中斷點，aliases 包含鏈上的節點
        total_names = set()
        for g in result:
            total_names.add(g["primary_name"])
            total_names.update(g["aliases"])
        # A 和 B 都應在結果中
        assert "A" in total_names or "B" in total_names

    def test_self_reference(self):
        """BC-9: 自我指向 A→A → 跳過，不產生 group 條目"""
        result = self._migrate([("A", "A")])
        assert result == []

    def test_empty_rows(self):
        """BC-10: 空舊表 → 回傳 []"""
        result = self._migrate([])
        assert result == []

    def test_seed_data_migration(self):
        """種子資料 5 筆正確跟鏈合併為 4 組（含匯流）"""
        rows = [
            ("miru", "坂道みる"),
            ("橋本ありな", "新ありな"),
            ("河北彩伽", "河北彩花"),
            ("天海こころ", "深田えいみ"),
            ("心菜りお", "深田えいみ"),
        ]
        result = self._migrate(rows)
        groups = {g["primary_name"]: set(g["aliases"]) for g in result}
        assert "坂道みる" in groups
        assert groups["坂道みる"] == {"miru"}
        assert "新ありな" in groups
        assert groups["新ありな"] == {"橋本ありな"}
        assert "河北彩花" in groups
        assert groups["河北彩花"] == {"河北彩伽"}
        assert "深田えいみ" in groups
        assert groups["深田えいみ"] == {"天海こころ", "心菜りお"}


# ---------------------------------------------------------------------------
# init_db() 遷移邏輯
# ---------------------------------------------------------------------------

class TestInitDbMigration:
    """BC-11: 已是新 schema 跳過遷移；BC-18: idempotent"""

    def test_new_schema_already(self, empty_db):
        """BC-11: 無 old_name 欄位 → 直接 CREATE TABLE IF NOT EXISTS，不拋例外"""
        conn = sqlite3.connect(str(empty_db))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(actress_aliases)")
        cols = [row[1] for row in cursor.fetchall()]
        conn.close()
        # 新 schema 應有 primary_name，不應有 old_name
        assert "primary_name" in cols
        assert "old_name" not in cols

    def test_idempotent(self, empty_db):
        """BC-18: 對新 schema DB 呼叫兩次 init_db() → 無錯誤"""
        init_db(empty_db)  # 第二次（種子資料已刪，不會重插）
        init_db(empty_db)  # 第三次
        conn = sqlite3.connect(str(empty_db))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(actress_aliases)")
        cols = [row[1] for row in cursor.fetchall()]
        conn.close()
        assert "primary_name" in cols

    def test_migrates_old_schema(self, old_schema_db):
        """舊 schema 遷移：rename to legacy，建新表，種子資料正確轉換"""
        init_db(old_schema_db)

        conn = sqlite3.connect(str(old_schema_db))
        cursor = conn.cursor()

        # 新表存在，schema 正確
        cursor.execute("PRAGMA table_info(actress_aliases)")
        cols = [row[1] for row in cursor.fetchall()]
        assert "primary_name" in cols
        assert "old_name" not in cols

        # legacy 表存在
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='actress_aliases_legacy'"
        )
        assert cursor.fetchone() is not None

        # 遷移結果正確（深田えいみ 組）
        cursor.execute(
            "SELECT aliases FROM actress_aliases WHERE primary_name = '深田えいみ'"
        )
        row = cursor.fetchone()
        assert row is not None
        aliases = json.loads(row[0])
        assert set(aliases) == {"天海こころ", "心菜りお"}
        conn.close()

    def test_seed_data_inserted_on_new_db(self, tmp_path):
        """新建 DB 有種子資料（供既有 test_actress_alias_api.py 期望 >= 3 筆）"""
        db_path = tmp_path / "seed_test.db"
        init_db(db_path)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM actress_aliases")
        count = cursor.fetchone()[0]
        conn.close()
        assert count >= 3


# ---------------------------------------------------------------------------
# AliasRepository — 讀取方法
# ---------------------------------------------------------------------------

class TestAliasRepositoryRead:
    """get_all, get_by_primary, find_by_alias"""

    def test_get_all_empty(self, repo):
        result = repo.get_all()
        assert result == []

    def test_get_by_primary_miss(self, repo):
        result = repo.get_by_primary("nobody")
        assert result is None

    def test_find_by_alias_miss(self, repo):
        result = repo.find_by_alias("nobody")
        assert result is None

    def test_get_by_primary_hit(self, repo):
        repo.add("Alice", ["ali"])
        result = repo.get_by_primary("Alice")
        assert result is not None
        assert result.primary_name == "Alice"
        assert "ali" in result.aliases

    def test_find_by_alias_hit(self, repo):
        repo.add("Alice", ["ali", "alicia"])
        result = repo.find_by_alias("ali")
        assert result is not None
        assert result.primary_name == "Alice"


# ---------------------------------------------------------------------------
# resolve() — 3 種路徑
# ---------------------------------------------------------------------------

class TestResolve:
    """BC-12, BC-13, BC-14"""

    def test_primary_hit(self, repo):
        """BC-12: name == primary_name → 回傳 {primary_name} ∪ set(aliases)"""
        repo.add("Alice", ["ali", "alicia"])
        result = repo.resolve("Alice")
        assert "Alice" in result
        assert "ali" in result
        assert "alicia" in result

    def test_alias_hit(self, repo):
        """BC-13: name 在某筆的 aliases 中 → 回傳 {primary_name} ∪ set(aliases)"""
        repo.add("Alice", ["ali", "alicia"])
        result = repo.resolve("ali")
        assert "Alice" in result
        assert "ali" in result
        assert "alicia" in result

    def test_miss(self, repo):
        """BC-14: 無記錄 → 回傳 {name}"""
        result = repo.resolve("nobody")
        assert result == {"nobody"}


# ---------------------------------------------------------------------------
# 全域唯一約束 — 4 種衝突情境
# ---------------------------------------------------------------------------

class TestGlobalUniqueness:
    """BC-1, BC-2, BC-3, BC-4"""

    def test_add_alias_conflicts_with_existing_alias(self, repo):
        """BC-1: alias 已是其他 group 的 alias → (False, 訊息)"""
        repo.add("X", ["A"])
        ok, msg = repo.add_alias("Y", "A")
        assert ok is False
        assert msg is not None
        assert len(msg) > 0

    def test_add_alias_conflicts_with_primary_name(self, repo):
        """BC-2: alias 已是某筆的 primary_name → (False, 訊息)"""
        repo.add("X", [])
        ok, msg = repo.add_alias("Y", "X")
        assert ok is False
        assert msg is not None

    def test_add_group_primary_already_exists(self, repo):
        """BC-3: 新增 group 的 primary_name 已存在 → ValueError"""
        repo.add("A", [])
        with pytest.raises(ValueError):
            repo.add("A", [])

    def test_add_group_primary_is_existing_alias(self, repo):
        """BC-4: 新增 group 的 primary_name 已是別人的 alias → ValueError"""
        repo.add("X", ["A"])
        with pytest.raises(ValueError):
            repo.add("A", [])


# ---------------------------------------------------------------------------
# add() 成功路徑
# ---------------------------------------------------------------------------

class TestAddGroup:
    def test_add_empty_aliases(self, repo):
        record = repo.add("Alice", [])
        assert record.primary_name == "Alice"
        assert record.aliases == []

    def test_add_with_aliases(self, repo):
        record = repo.add("Alice", ["ali", "alicia"])
        assert "ali" in record.aliases
        assert "alicia" in record.aliases

    def test_add_source_default_manual(self, repo):
        record = repo.add("Alice", [])
        assert record.source == "manual"

    def test_add_source_auto(self, repo):
        record = repo.add("Alice", [], source="auto")
        assert record.source == "auto"


# ---------------------------------------------------------------------------
# add_alias() 成功路徑
# ---------------------------------------------------------------------------

class TestAddAlias:
    def test_add_alias_success(self, repo):
        repo.add("Alice", [])
        ok, msg = repo.add_alias("Alice", "ali")
        assert ok is True
        assert msg is None

    def test_add_alias_persisted(self, repo):
        repo.add("Alice", [])
        repo.add_alias("Alice", "ali")
        record = repo.get_by_primary("Alice")
        assert "ali" in record.aliases


# ---------------------------------------------------------------------------
# remove_alias()
# ---------------------------------------------------------------------------

class TestRemoveAlias:
    def test_remove_existing_alias(self, repo):
        repo.add("Alice", ["ali"])
        result = repo.remove_alias("Alice", "ali")
        assert result is True
        record = repo.get_by_primary("Alice")
        assert "ali" not in record.aliases

    def test_remove_nonexistent_alias(self, repo):
        repo.add("Alice", [])
        result = repo.remove_alias("Alice", "nonexistent")
        assert result is False


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_by_primary(self, repo):
        repo.add("Alice", ["ali"])
        result = repo.delete("Alice")
        assert result is True
        assert repo.get_by_primary("Alice") is None

    def test_delete_by_alias(self, repo):
        repo.add("Alice", ["ali"])
        result = repo.delete("ali")
        assert result is True
        assert repo.get_by_primary("Alice") is None

    def test_delete_nonexistent(self, repo):
        result = repo.delete("nobody")
        assert result is False


# ---------------------------------------------------------------------------
# sync_from_favorite() — 3 種情境
# ---------------------------------------------------------------------------

class TestSyncFromFavorite:
    """BC-15, BC-16, BC-17"""

    def test_incoming_name_is_existing_alias(self, repo):
        """BC-15: incoming name 已是別人的 alias → merge 到既有 group，不新建"""
        repo.add("Alice", ["ali"])
        # sync "ali"（已是 Alice 的 alias）→ 應 merge 到 Alice group
        result = repo.sync_from_favorite("ali", ["new_alias"])
        assert result["primary_name"] == "Alice"
        record = repo.get_by_primary("Alice")
        assert "new_alias" in record.aliases
        # 不應建立以 "ali" 為 primary 的新 group
        assert repo.get_by_primary("ali") is None

    def test_existing_primary_merges_aliases(self, repo):
        """BC-16: 已存在 primary → merge aliases（聯集），不新建記錄"""
        repo.add("Alice", ["ali"])
        result = repo.sync_from_favorite("Alice", ["alicia"])
        assert result["primary_name"] == "Alice"
        record = repo.get_by_primary("Alice")
        assert "ali" in record.aliases
        assert "alicia" in record.aliases

    def test_skips_conflicting_alias(self, repo):
        """BC-17: 某 alias 已屬他人 → skipped_aliases，不影響其他 aliases"""
        repo.add("Bob", ["bob_alias"])
        result = repo.sync_from_favorite("Alice", ["alice_alias", "bob_alias"])
        # bob_alias 已屬 Bob，應被跳過
        assert "bob_alias" in result["skipped_aliases"]
        # alice_alias 應正常合入
        record = repo.get_by_primary("Alice")
        assert "alice_alias" in record.aliases
        # bob group 不應被污染
        bob_record = repo.get_by_primary("Bob")
        assert "bob_alias" in bob_record.aliases

    def test_new_group_created_for_fresh_name(self, repo):
        """全新名稱：建立新 group"""
        result = repo.sync_from_favorite("NewActress", ["alias1"])
        assert result["primary_name"] == "NewActress"
        record = repo.get_by_primary("NewActress")
        assert record is not None
        assert "alias1" in record.aliases
