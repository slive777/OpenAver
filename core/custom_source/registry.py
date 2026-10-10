"""自訂來源登錄：唯讀掃描使用者資料夾，逐檔隔離載入；不建目錄、不寫檔。"""
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.custom_source.errors import LoadError
from core.custom_source.schema import ID_RE, Spec, load_bytes
from core.custom_source.scraper import CustomScraper
from core.data_root import get_data_root
from core.logger import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class LoadedSource:
    id: str
    spec: Optional[Spec]
    error: Optional[LoadError]
    sha256: Optional[str] = None


def custom_sources_dir():
    return get_data_root() / "custom_sources"


def _is_candidate(path):
    if path.suffix not in (".yaml", ".yml") or path.name.startswith("."):
        return False
    try:
        return not path.is_symlink() and path.is_file()
    except OSError:
        log.warning("custom sources: cannot inspect a file, skipped")
        return False


def _candidate_files(directory):
    try:
        if not directory.is_dir():
            return []
        entries = sorted(directory.iterdir(), key=lambda p: p.name)
    except OSError:
        log.warning("custom sources: cannot list directory")
        return []
    return [p for p in entries if _is_candidate(p)]


def _load_path(path):
    try:
        raw = path.read_bytes()
    except Exception:
        log.exception("custom source %s: unexpected load failure", path.stem)
        return LoadedSource(path.stem, None, LoadError("bad_value", "無法讀取此檔案", ""))
    digest = hashlib.sha256(raw).hexdigest()
    try:
        spec, _ = load_bytes(raw, path.stem)
    except LoadError as exc:
        return LoadedSource(path.stem, None, exc, digest)
    except Exception:
        log.exception("custom source %s: unexpected load failure", path.stem)
        return LoadedSource(path.stem, None, LoadError("bad_value", "無法讀取此檔案", ""), digest)
    return LoadedSource(path.stem, spec, None, digest)


def _target_dir(directory):
    return Path(directory) if directory is not None else custom_sources_dir()


def find_path(source_id, directory=None):
    """依 id 找候選檔；以 stem 比對、不拼路徑；不符 ID_RE 或不存在回 None。"""
    if not isinstance(source_id, str) or ID_RE.fullmatch(source_id) is None:
        return None
    for path in _candidate_files(_target_dir(directory)):
        if path.stem == source_id:
            return path
    return None


def load_one(source_id, directory=None):
    path = find_path(source_id, directory)
    return None if path is None else _load_path(path)


def load_all(directory=None):
    return [_load_path(p) for p in _candidate_files(_target_dir(directory))]


def scraper_factories(prefix="custom:"):
    factories = {}
    for loaded in load_all():
        if loaded.spec is None:
            continue
        key = prefix + loaded.spec.id
        factories[key] = lambda s=loaded.spec, k=key: [CustomScraper(s, k)]
    return factories
