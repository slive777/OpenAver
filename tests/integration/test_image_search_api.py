"""POST /api/image-search 契約（193-T3）：送出前把關、錯誤碼對應、候選信封。

lookup／片庫一律 patch 在使用端 web.routers.image_search；autouse 預設假 lookup，
任何路徑都碰不到真 client（不打站方）。
"""
from io import BytesIO

import pytest
from PIL import Image

from core.avscan.client import AvscanInvalidImage, AvscanRateLimited, AvscanUnparseable, AvscanUnreachable
from web.routers import image_search as mod

URL = "/api/image-search"


def _img_bytes(fmt: str) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (32, 32), (200, 30, 30)).save(buf, fmt)
    return buf.getvalue()


def _post(client, data: bytes, name: str = "q.bin"):
    return client.post(URL, files={"file": (name, data, "application/octet-stream")})


def _match(kind="cover", part="full"):
    return {"kind": kind, "cover_part": part, "time_seconds": None, "time_text": None, "thumb_url": None}


def _cand(code, sim):
    return {"code": code, "similarity": sim, "match": _match()}


class _FakeRepo:
    found: dict = {}
    boom = False
    calls: list = []

    def get_by_numbers(self, numbers):
        type(self).calls.append(list(numbers))
        if type(self).boom:
            raise RuntimeError("db down")
        return type(self).found


@pytest.fixture(autouse=True)
def lookup_calls(monkeypatch):
    calls = []

    def fake(_data):
        calls.append(1)
        return []

    monkeypatch.setattr("web.routers.image_search.lookup", fake)
    monkeypatch.setattr("web.routers.image_search.init_db", lambda: None)
    monkeypatch.setattr("web.routers.image_search.VideoRepository", _FakeRepo)
    _FakeRepo.found, _FakeRepo.boom, _FakeRepo.calls = {}, False, []
    return calls


def _set_lookup(monkeypatch, fn):
    monkeypatch.setattr("web.routers.image_search.lookup", fn)


def test_oversize_upload_returns_413_without_lookup(client, lookup_calls):
    r = _post(client, b"\xff\xd8\xff" + b"\x00" * (mod.MAX_BYTES + 1 - 3))
    assert r.status_code == 413
    assert r.json()["error"] == "file_too_large"
    assert lookup_calls == []


@pytest.mark.parametrize("kind", ["gif", "text", "broken_jpeg"])
def test_non_whitelisted_upload_returns_415_without_lookup(client, lookup_calls, kind):
    data = {
        "gif": _img_bytes("GIF"),
        "text": b"hello not an image",
        "broken_jpeg": b"\xff\xd8\xff" + b"garbage" * 20,
    }[kind]
    r = _post(client, data)
    assert r.status_code == 415
    assert r.json()["error"] == "unsupported_image"
    assert lookup_calls == []


@pytest.mark.parametrize(
    "exc,status,code",
    [
        (AvscanRateLimited(7), 429, "rate_limited"),
        (AvscanUnreachable("x"), 502, "unreachable"),
        (AvscanUnparseable("x"), 502, "unparseable"),
        (AvscanInvalidImage("x"), 415, "unsupported_image"),
    ],
)
def test_avscan_exceptions_map_to_error_table(client, monkeypatch, exc, status, code):
    def boom(_data):
        raise exc

    _set_lookup(monkeypatch, boom)
    r = _post(client, _img_bytes("JPEG"))
    body = r.json()
    assert r.status_code == status
    assert body["success"] is False and body["error"] == code and body["message"]
    if code == "rate_limited":
        assert body["retry_after"] == 7
    else:
        assert "retry_after" not in body


def test_success_envelope_number_and_clear_hit(client, monkeypatch):
    raw = [_cand("FC2-PPV-4966131", 95.0), _cand("178X023", 85.0), _cand("IPZZ-001", 80.0)]
    _set_lookup(monkeypatch, lambda _d: raw)
    _FakeRepo.found = {"FC2-4966131": [object()]}
    r = _post(client, _img_bytes("PNG"))
    body = r.json()
    assert r.status_code == 200
    assert body["success"] is True and body["source"] == "avscan"
    assert body["clear_hit"] is True and body["lead"] == 10.0
    c = body["candidates"]
    assert [x["rank"] for x in c] == [1, 2, 3]
    assert (c[0]["number"], c[0]["searchable"]) == ("FC2-4966131", True)
    assert (c[1]["number"], c[1]["searchable"]) == ("178X023", False)
    assert c[0]["similarity"] == 95.0 and c[0]["match"] == _match()
    assert [x["in_library"] for x in c] == [True, False, False]
    assert len(_FakeRepo.calls) == 1


def test_empty_candidates_returns_200_empty_list(client):
    r = _post(client, _img_bytes("JPEG"))
    assert r.status_code == 200
    assert r.json() == {"success": True, "source": "avscan", "clear_hit": False, "lead": None, "candidates": []}
    assert _FakeRepo.calls == []


def test_library_lookup_failure_gives_null_in_library(client, monkeypatch):
    _set_lookup(monkeypatch, lambda _d: [_cand("IPZZ-001", 90.0), _cand("SONE-103", 70.0)])
    _FakeRepo.boom = True
    r = _post(client, _img_bytes("JPEG"))
    assert r.status_code == 200
    assert [x["in_library"] for x in r.json()["candidates"]] == [None, None]
