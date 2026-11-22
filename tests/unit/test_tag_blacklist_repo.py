import pytest

from core.database import init_db


@pytest.fixture
def empty_db(tmp_path):
    db_path = tmp_path / "empty_tag_blacklist.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def repo(empty_db):
    from core.database import TagBlacklistRepository

    return TagBlacklistRepository(empty_db)


def test_repo_same_key_is_duplicate(repo):
    repo.add("ハイビジョン")
    with pytest.raises(ValueError):
        repo.add(" ハイビジョン ")
    rows = repo.get_all()
    assert len(rows) == 1
    assert rows[0]["name"] == "ハイビジョン"
    assert rows[0]["key"] == "ハイビジョン"
    repo.add("Blu-ray")
    with pytest.raises(ValueError):
        repo.add("blu-RAY")
    assert len(repo.get_all()) == 2
    assert repo.remove(" ハイビジョン ")
    assert len(repo.get_all()) == 1
    assert not repo.remove("不存在的字")
    repo.remove("blu-ray")
    assert repo.get_all() == []
