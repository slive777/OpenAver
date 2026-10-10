"""自訂來源登錄：逐檔隔離載入、檔案過濾、唯讀目錄語意、scraper_factories。"""

import shutil

import pytest

from core.custom_source import errors, registry, schema
from core.custom_source.registry import custom_sources_dir, load_all, scraper_factories
from core.scrapers.base import BaseScraper
from tests.unit.test_custom_source_fixtures import FIXTURE_DIR

GOOD = ["single-og", "single-og-min", "two-step", "fuzzy", "text"]
SOG_TEXT = (FIXTURE_DIR / "single-og.yaml").read_text(encoding="utf-8")


def _put_good(directory, names=GOOD):
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy(FIXTURE_DIR / f"{name}.yaml", directory / f"{name}.yaml")


def _bad_files():
    """七份壞檔，各是不同的輸入。"""
    return {
        "bad-syntax.yaml": ("id: [unclosed", "yaml_syntax"),
        "bad-unknown.yaml": (SOG_TEXT.replace("id: single-og", "id: bad-unknown") + "censored: true\n", "unknown_key"),
        "bad-tag.yaml": ("id: !!python/object/apply:os.system [x]\n", "unsafe_tag"),
        "bad-alias.yaml": ("x: &a 1\ny: *a\n", "alias"),
        "bad-large.yaml": (SOG_TEXT.replace("id: single-og", "id: bad-large") + "# " + "a" * 65600 + "\n", "too_large"),
        "bad-binary.yaml": (bytes([0xFF, 0xFE, 0x00, 0x80]), "yaml_syntax"),
        "bad-mismatch.yaml": (SOG_TEXT, "id_filename_mismatch"),
    }


def _put_bad(directory):
    for name, (content, _reason) in _bad_files().items():
        path = directory / name
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))


def test_isolation_oracle_five_good_seven_bad(tmp_path):
    mixed, only_good = tmp_path / "mixed", tmp_path / "good"
    _put_good(mixed)
    _put_bad(mixed)
    _put_good(only_good)
    got = {s.id: s for s in load_all(mixed)}
    assert len(got) == 12
    for stem, (_c, reason) in _bad_files().items():
        item = got[stem[:-5]]
        assert item.spec is None and item.error.reason == reason
        assert item.error.reason in errors.LOAD_REASONS
    good = [s for s in load_all(mixed) if s.spec is not None]
    assert all(s.error is None for s in good)
    assert [s.spec for s in good] == [s.spec for s in load_all(only_good)]
    assert sorted(s.id for s in good) == sorted(GOOD)


def test_isolation_one_unexpected_exception_does_not_spread(tmp_path, monkeypatch):
    _put_good(tmp_path)
    real = schema.load_file

    def fake(path):
        if path.stem == "fuzzy":
            raise RuntimeError("canary")
        return real(path)

    monkeypatch.setattr("core.custom_source.registry.load_file", fake)
    got = {s.id: s for s in load_all(tmp_path)}
    assert got["fuzzy"].spec is None
    assert got["fuzzy"].error.reason == "bad_value"
    assert "canary" not in str(got["fuzzy"].error)
    assert all(got[n].spec is not None for n in GOOD if n != "fuzzy")


def test_file_filter_keeps_only_plain_lowercase_yaml_files(tmp_path):
    _put_good(tmp_path, ["single-og"])
    shutil.copy(FIXTURE_DIR / "text.yaml", tmp_path / "text.yml")
    for name in ("UP.YAML", ".hidden.yaml", "._mac.yaml", "notes.txt"):
        (tmp_path / name).write_text(SOG_TEXT, encoding="utf-8")
    (tmp_path / "Bad_Name.yaml").write_text(SOG_TEXT, encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "fuzzy.yaml").write_text(SOG_TEXT, encoding="utf-8")
    (tmp_path / "d.yaml").mkdir()
    try:
        (tmp_path / "link.yaml").symlink_to(tmp_path / "single-og.yaml")
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported")
    got = load_all(tmp_path)
    assert [s.id for s in got] == ["Bad_Name", "single-og", "text"]
    assert got[0].spec is None and got[0].error.reason in errors.LOAD_REASONS
    assert got[2].spec is not None


@pytest.mark.parametrize("make_dir", [False, True])
def test_missing_dir_is_empty_and_never_created(tmp_path, monkeypatch, make_dir):
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path))
    if make_dir:
        (tmp_path / "custom_sources").mkdir()
    before = sorted(p.name for p in tmp_path.rglob("*"))
    assert load_all() == [] and scraper_factories() == {}
    assert sorted(p.name for p in tmp_path.rglob("*")) == before
    assert (tmp_path / "custom_sources").exists() is make_dir


def test_all_bad_dir_gives_error_items_not_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path))
    target = tmp_path / "custom_sources"
    target.mkdir()
    for name in ("a", "b", "c"):
        (target / f"{name}.yaml").write_text(f"id: [{name}", encoding="utf-8")
    got = load_all()
    assert len(got) == 3 and all(s.spec is None and s.error is not None for s in got)
    assert scraper_factories() == {}


def test_custom_sources_dir_follows_env_at_call_time(tmp_path, monkeypatch):
    for sub in ("one", "two"):
        monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path / sub))
        assert custom_sources_dir() == tmp_path / sub / "custom_sources"


def test_factories_skip_failed_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path))
    target = tmp_path / "custom_sources"
    _put_good(target, ["single-og", "two-step"])
    (target / "broken.yaml").write_text("id: [x", encoding="utf-8")
    factories = scraper_factories()
    assert sorted(factories) == ["custom:single-og", "custom:two-step"]
    assert sorted(scraper_factories("x/")) == ["x/single-og", "x/two-step"]


def test_factories_each_build_their_own_source(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path))
    _put_good(tmp_path / "custom_sources", ["single-og", "two-step"])
    for key, factory in scraper_factories().items():
        built = factory()
        assert len(built) == 1 and isinstance(built[0], BaseScraper)
        assert built[0].source_id == key == built[0].source_name
        assert built[0].spec.id == key.split(":", 1)[1]
    assert registry.LoadedSource("a", None, None).id == "a"


def test_file_inspection_error_skips_only_that_file(tmp_path, monkeypatch):
    _put_good(tmp_path, ["single-og", "text"])
    real = registry.Path.is_file

    def flaky(self):
        if self.name == "text.yaml":
            raise PermissionError("canary")
        return real(self)

    monkeypatch.setattr(registry.Path, "is_file", flaky)
    assert [s.id for s in load_all(tmp_path)] == ["single-og"]
