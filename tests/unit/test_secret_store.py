"""tests/unit/test_secret_store.py — core.secret_store 單元測試（TASK-206a-T1）。

只用自編假金鑰；不印任何值。
"""

import base64
import os
import shutil

import pytest

import core.secret_store as secret_store
from core.secret_store import (
    SecretStoreError,
    apply_changes,
    clear_all,
    prime,
    reset_state_for_tests,
    snapshot,
    verify_from_disk,
)

_FAKE_KEYS = {
    "svc_alpha": "FAKE-TEST-KEY-alpha-0001-xyzzy-plugh",
    "svc_beta": "FAKE-TEST-KEY-beta-0002-xyzzy-plugh",
    "svc_gamma": "FAKE-TEST-KEY-gamma-0003-xyzzy-plugh",
}
_FAKE_NEW = "FAKE-TEST-KEY-new-0004-xyzzy-plugh"


def _read_blobs():
    from core.database.connection import get_connection, get_db_path

    conn = get_connection(get_db_path())
    try:
        rows = conn.execute("SELECT name, blob FROM app_secrets").fetchall()
    finally:
        conn.close()
    return dict(rows)


def _write_blob(name, blob):
    from core.database.connection import get_connection, get_db_path

    conn = get_connection(get_db_path())
    try:
        conn.execute("UPDATE app_secrets SET blob = ? WHERE name = ?", (blob, name))
        conn.commit()
    finally:
        conn.close()


class TestRoundtripNoPlaintext:
    def test_roundtrip_persists_and_leaves_no_plaintext_on_disk(self, isolate_secret_store):
        root = isolate_secret_store
        apply_changes(dict(_FAKE_KEYS), {})
        assert snapshot() == _FAKE_KEYS
        reset_state_for_tests()
        prime()
        assert snapshot() == _FAKE_KEYS
        assert verify_from_disk(dict(_FAKE_KEYS)) is True
        hits = 0
        for path in sorted(root.rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                for fake in _FAKE_KEYS.values():
                    if fake.encode("utf-8") in data:
                        hits += 1
        assert hits == 0


class TestUnreadableRowsAndKeys:
    @pytest.mark.parametrize(
        "case", ["tampered_byte", "swapped_rows", "key_missing", "key_invalid"]
    )
    def test_unreadable_rows_and_keys_read_as_unset(self, isolate_secret_store, case):
        root = isolate_secret_store
        apply_changes(
            {"svc_alpha": _FAKE_KEYS["svc_alpha"], "svc_beta": _FAKE_KEYS["svc_beta"]},
            {},
        )
        if case == "tampered_byte":
            blobs = _read_blobs()
            payload = bytearray(base64.b64decode(blobs["svc_alpha"].partition(":")[2]))
            payload[20] ^= 0x01
            _write_blob(
                "svc_alpha",
                "v1:" + base64.b64encode(bytes(payload)).decode("ascii"),
            )
            reset_state_for_tests()
            prime()
            snap = snapshot()
            assert "svc_alpha" not in snap
            assert snap.get("svc_beta") == _FAKE_KEYS["svc_beta"]
        elif case == "swapped_rows":
            blobs = _read_blobs()
            _write_blob("svc_alpha", blobs["svc_beta"])
            _write_blob("svc_beta", blobs["svc_alpha"])
            reset_state_for_tests()
            prime()
            assert snapshot() == {}
        elif case == "key_missing":
            (root / "secret.key").unlink()
            reset_state_for_tests()
            prime()
            assert snapshot() == {}
            apply_changes({"svc_new": _FAKE_NEW}, {})
            assert snapshot().get("svc_new") == _FAKE_NEW
        elif case == "key_invalid":
            for raw in (b"", os.urandom(10)):
                (root / "secret.key").write_bytes(raw)
                key_before = (root / "secret.key").read_bytes()
                blobs_before = _read_blobs()
                reset_state_for_tests()
                prime()
                assert snapshot() == {}
                with pytest.raises(SecretStoreError):
                    apply_changes({"svc_new": _FAKE_NEW}, {})
                assert (root / "secret.key").read_bytes() == key_before
                assert _read_blobs() == blobs_before


class TestCopiedRoot:
    def test_copied_data_root_still_decrypts(
        self, isolate_secret_store, tmp_path, monkeypatch
    ):
        src = isolate_secret_store
        apply_changes(dict(_FAKE_KEYS), {})
        dst = tmp_path / "moved_root"
        shutil.copytree(src, dst)
        monkeypatch.setenv("OPENAVER_DATA_DIR", str(dst))
        reset_state_for_tests()
        prime()
        assert snapshot() == _FAKE_KEYS
        assert verify_from_disk(dict(_FAKE_KEYS)) is True


class TestUnfinalizedRoot:
    def test_unfinalized_root_creates_nothing_and_refuses_writes(
        self, tmp_path, monkeypatch
    ):
        root = tmp_path / "unfinal"
        root.mkdir()
        monkeypatch.setenv("OPENAVER_DATA_DIR", str(root))
        reset_state_for_tests()
        before = sorted(p.name for p in root.iterdir())
        secret_store.ensure_schema()
        prime()
        assert snapshot() == {}
        with pytest.raises(SecretStoreError):
            apply_changes({"svc_alpha": _FAKE_KEYS["svc_alpha"]}, {})
        with pytest.raises(SecretStoreError):
            clear_all()
        assert sorted(p.name for p in root.iterdir()) == before
