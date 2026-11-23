"""core/secret_store.py — API Key 加密收納（TASK-206a-T1，CD-206-2/-3/-4）。

標準庫加密（hashlib／hmac／os.urandom／base64）：master＝32 位元組隨機，
存 `<data_root>/secret.key`（O_EXCL＋0600＋fsync）；enc／mac 兩把子鑰匙經
HMAC 域分隔衍生；每筆 16 位元組隨機 nonce，密文＝明文 XOR
HMAC-SHA256(enc_key, nonce‖8 位元組大端計數器) 串流；標籤覆蓋版本‖列名‖
nonce‖密文，比對用 compare_digest；信封 `v1:<base64(nonce‖密文‖標籤)>`。

本模組只讀寫自己的 `app_secrets` 表與鑰匙檔。`core.database.connection`
只在 `_connect()` 內 import（BE-PY-08）；資料根與路徑每次呼叫時現算，
不在 import 時快取任何路徑。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import threading

from core.data_root import get_data_root, is_layout_finalized
from core.logger import get_logger

logger = get_logger(__name__)

_KEY_LEN = 32
_NONCE_LEN = 16
_TAG_LEN = 32
_VERSION = b"v1"
_KEY_FILENAME = "secret.key"
_ENC_DOMAIN = b"oav-secret-enc-v1"
_MAC_DOMAIN = b"oav-secret-mac-v1"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS app_secrets (
    name TEXT PRIMARY KEY,
    blob TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_lock = threading.Lock()
_cache: dict[str, str] = {}


class SecretStoreError(Exception):
    """收納層錯誤：訊息固定、不含任何值。"""


def _connect():
    from core.database.connection import get_connection, get_db_path

    return get_connection(get_db_path())


def _key_path():
    return get_data_root() / _KEY_FILENAME


def _ensure_schema() -> None:
    conn = _connect()
    try:
        conn.execute(_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def _read_master() -> bytes | None:
    try:
        master = _key_path().read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        logger.error("secret_store key unreadable")
        return None
    if len(master) != _KEY_LEN:
        logger.error("secret_store key invalid")
        return None
    return master


def _create_key_file(path) -> bytes:
    master = os.urandom(_KEY_LEN)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        remaining = memoryview(master)
        while remaining:
            written = os.write(fd, remaining)
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return master


def _derive(master: bytes, domain: bytes) -> bytes:
    return hmac.new(master, domain, hashlib.sha256).digest()


def _tag(mac_key: bytes, name: str, nonce: bytes, ct: bytes) -> bytes:
    msg = b"|".join((_VERSION, name.encode("utf-8"), nonce, ct))
    return hmac.new(mac_key, msg, hashlib.sha256).digest()


def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(
            hmac.new(enc_key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        )
        counter += 1
    return bytes(out[:length])


def _encrypt(enc_key: bytes, mac_key: bytes, name: str, text: str) -> str:
    data = text.encode("utf-8")
    nonce = os.urandom(_NONCE_LEN)
    ct = bytes(a ^ b for a, b in zip(data, _keystream(enc_key, nonce, len(data)), strict=True))
    tag = _tag(mac_key, name, nonce, ct)
    return "v1:" + base64.b64encode(nonce + ct + tag).decode("ascii")


def _decrypt(enc_key: bytes, mac_key: bytes, name: str, blob: object) -> str | None:
    if not isinstance(blob, str) or not blob.startswith("v1:"):
        logger.warning("secret_store row unreadable name=%s reason=bad-envelope", name)
        return None
    try:
        raw = base64.b64decode(blob[3:], validate=True)
    except ValueError:
        logger.warning("secret_store row unreadable name=%s reason=bad-envelope", name)
        return None
    if len(raw) < _NONCE_LEN + _TAG_LEN:
        logger.warning("secret_store row unreadable name=%s reason=bad-envelope", name)
        return None
    nonce = raw[:_NONCE_LEN]
    tag = raw[len(raw) - _TAG_LEN :]
    ct = raw[_NONCE_LEN : len(raw) - _TAG_LEN]
    if not hmac.compare_digest(tag, _tag(mac_key, name, nonce, ct)):
        logger.warning("secret_store row unreadable name=%s reason=bad-tag", name)
        return None
    data = bytes(a ^ b for a, b in zip(ct, _keystream(enc_key, nonce, len(ct)), strict=True))
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("secret_store row unreadable name=%s reason=bad-encoding", name)
        return None


def _publish_to_cache(upserts: dict | None, deletes) -> None:
    for name in deletes or []:
        _cache.pop(name, None)
    for name, value in dict(upserts or {}).items():
        text = value.strip() if isinstance(value, str) else ""
        if text:
            _cache[name] = text
        else:
            _cache.pop(name, None)


def ensure_schema() -> None:
    """自建 `app_secrets` 表（冪等）。未定版根直接 no-op，一個檔都不建。"""
    if not is_layout_finalized(get_data_root()):
        return
    _ensure_schema()


def prime() -> None:
    """從磁碟（庫＋鑰匙）解密全表、整份取代快取。鑰匙或單列壞掉不拋；
    DB 層例外原樣上拋。未定版根直接 no-op（快取為空）。"""
    global _cache
    if not is_layout_finalized(get_data_root()):
        with _lock:
            _cache = {}
        return
    with _lock:
        _ensure_schema()
        master = _read_master()
        if master is None:
            _cache = {}
            return
        enc_key = _derive(master, _ENC_DOMAIN)
        mac_key = _derive(master, _MAC_DOMAIN)
        conn = _connect()
        try:
            rows = conn.execute("SELECT name, blob FROM app_secrets").fetchall()
        finally:
            conn.close()
        fresh: dict[str, str] = {}
        for name, blob in rows:
            text = _decrypt(enc_key, mac_key, name, blob)
            if text is not None:
                fresh[name] = text
        _cache = fresh


def snapshot() -> dict[str, str]:
    """快取副本（零 I/O）。未 prime() 時為空。"""
    return dict(_cache)


def apply_changes(upserts: dict, deletes, publish: bool = True) -> None:
    """upserts 與 deletes 走同一個 DB 交易；commit 成功後才更新快取
    （publish=False 時不更新，由呼叫端驗證後再呼叫公開 `publish`）。
    strip 後為空的 upsert 值視同 delete。有 upsert 且鑰匙缺才建新鑰匙；
    鑰匙檔存在但無效一律拋 SecretStoreError（不動庫內任何列、不碰鑰匙檔）。
    未定版根拋 SecretStoreError。"""
    if not is_layout_finalized(get_data_root()):
        raise SecretStoreError("secret store root not finalized")
    norm: dict[str, str] = {}
    dead: set = set(deletes or [])
    for name, value in dict(upserts or {}).items():
        text = value.strip() if isinstance(value, str) else ""
        if text:
            norm[name] = text
        else:
            dead.add(name)
    key_path = _key_path()
    with _lock:
        if norm:
            master = _read_master()
            if master is None:
                if key_path.exists():
                    raise SecretStoreError("secret store key invalid")
                key_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    master = _create_key_file(key_path)
                except FileExistsError:
                    master = _read_master()
                    if master is None:
                        raise SecretStoreError("secret store key invalid") from None
            enc_key = _derive(master, _ENC_DOMAIN)
            mac_key = _derive(master, _MAC_DOMAIN)
            blobs = {
                name: _encrypt(enc_key, mac_key, name, text)
                for name, text in norm.items()
            }
        else:
            if key_path.exists() and _read_master() is None:
                raise SecretStoreError("secret store key invalid")
            blobs = {}
        _ensure_schema()
        conn = _connect()
        try:
            try:
                for name, blob in blobs.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO app_secrets (name, blob) VALUES (?, ?)",
                        (name, blob),
                    )
                for name in sorted(dead):
                    conn.execute("DELETE FROM app_secrets WHERE name = ?", (name,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()
        if publish:
            _publish_to_cache(norm, dead)


def publish(upserts: dict | None, deletes) -> None:
    """只更新快取、不碰庫（`apply_changes` 的薄包裝對應端）。"""
    with _lock:
        _publish_to_cache(upserts, deletes)


def verify_from_disk(expected: dict) -> bool:
    """開新連線＋現讀磁碟鑰匙逐名解密，與 expected 全等才回 True；
    鑰匙缺／無效、缺列、不等一律 False。不動快取、不建任何檔。"""
    if not is_layout_finalized(get_data_root()):
        return False
    master = _read_master()
    if master is None:
        return False
    from core.database.connection import get_db_path

    db_path = get_db_path()
    if not db_path.is_file():
        return dict(expected or {}) == {}
    enc_key = _derive(master, _ENC_DOMAIN)
    mac_key = _derive(master, _MAC_DOMAIN)
    conn = _connect()
    try:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'app_secrets'"
        ).fetchone()
        rows = (
            conn.execute("SELECT name, blob FROM app_secrets").fetchall()
            if has_table
            else []
        )
    finally:
        conn.close()
    fresh: dict[str, str] = {}
    for name, blob in rows:
        text = _decrypt(enc_key, mac_key, name, blob)
        if text is not None:
            fresh[name] = text
    return fresh == dict(expected or {})


def clear_all() -> None:
    """刪全部列＋清快取；只刪列、不讀不寫不刪鑰匙檔。未定版根拋錯。"""
    global _cache
    if not is_layout_finalized(get_data_root()):
        raise SecretStoreError("secret store root not finalized")
    with _lock:
        _ensure_schema()
        conn = _connect()
        try:
            try:
                conn.execute("DELETE FROM app_secrets")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()
        _cache = {}


def reset_state_for_tests() -> None:
    """只清快取（測試隔離用）。"""
    global _cache
    with _lock:
        _cache = {}
