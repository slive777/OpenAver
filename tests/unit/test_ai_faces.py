"""187-T1: faces client contract / consistency / EXIF prep."""

from __future__ import annotations

import base64
import io
import json
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from core.ai_services import faces
from core.ai_services.embeddings import EndpointError
from core.ai_services.faces import Box, FacesResult, detect
from core.ai_services.image_prep import cover_to_faces_data_uri
from core.ai_services.samples import check_faces_consistency


def _cfg(**kw):
    base = dict(url="http://faces.test", api_key="", model="")
    base.update(kw)
    return SimpleNamespace(**base)


def _install(monkeypatch, handler):
    """Patch module-local client factory (BE-TEST-29)."""

    def _factory(timeout=None):
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            timeout=timeout or httpx.Timeout(30.0, connect=5.0),
        )

    monkeypatch.setattr(faces, "_new_client", _factory)


# ---------------------------------------------------------------------------
# (1) client contract — table driven; each case is a distinct failure reason
# ---------------------------------------------------------------------------

# Cases (distinct reasons):
#   connect / remote_proto / read_timeout — transport kinds
#   http_400 / http_401 / not_json / faces_not_list / box_short / no_model / bad_score
#     — contract checks
#   empty_faces — legal no-face success
#   retry_bg_5xx / retry_manual_5xx / retry_4xx / retry_bg_timeout / retry_sync_timeout
#     — profile retry counts
#   payload_no_model / payload_with_model — request JSON model key presence
_CONTRACT_CASES = [
    # (label, profile, kind_or_ok, check, expect_calls)
    ("connect", "background", "unreachable", None, 1),
    ("remote_proto", "background", "unreachable", None, 1),
    ("read_timeout", "background", "unreachable", "timeout", 2),
    ("http_400", "background", "contract", "http_4xx", 1),
    ("http_401", "background", "contract", "auth", 1),
    ("not_json", "background", "contract", "not_json", 1),
    ("faces_not_list", "background", "contract", "shape", 1),
    ("box_short", "background", "contract", "box", 1),
    ("no_model", "background", "contract", "no_model", 1),
    ("bad_score", "background", "contract", "score", 1),
    ("empty_faces", "background", "ok", None, 1),
    ("retry_bg_5xx", "background", "contract", "http_5xx", 2),
    ("retry_manual_5xx", "manual", "contract", "http_5xx", 1),
    ("retry_4xx", "background", "contract", "http_4xx", 1),
    ("retry_bg_timeout", "background", "unreachable", "timeout", 2),
    ("retry_sync_timeout", "sync", "unreachable", "timeout", 1),
    ("payload_no_model", "background", "ok", None, 1),
    ("payload_with_model", "background", "ok", None, 1),
]


@pytest.mark.parametrize(
    "label,profile,kind_or_ok,check,expect_calls",
    _CONTRACT_CASES,
    ids=[c[0] for c in _CONTRACT_CASES],
)
def test_faces_client_contract(
    monkeypatch, label, profile, kind_or_ok, check, expect_calls
):
    calls = {"n": 0}
    seen_body: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.content:
            seen_body.clear()
            seen_body.update(json.loads(request.content))
        if label in ("connect",):
            raise httpx.ConnectError("boom", request=request)
        if label == "remote_proto":
            raise httpx.RemoteProtocolError("cut", request=request)
        if label in ("read_timeout", "retry_bg_timeout", "retry_sync_timeout"):
            raise httpx.ReadTimeout("slow", request=request)
        if label in ("http_400", "retry_4xx"):
            return httpx.Response(400, json={"error": "bad"})
        if label == "http_401":
            return httpx.Response(401, json={"error": "nope"})
        if label == "not_json":
            return httpx.Response(200, content=b"not-json{{")
        if label == "faces_not_list":
            return httpx.Response(200, json={"faces": {}, "model": "m"})
        if label == "box_short":
            return httpx.Response(
                200,
                json={"faces": [{"box": [0.1, 0.2, 0.3], "score": 0.9}], "model": "m"},
            )
        if label == "no_model":
            return httpx.Response(
                200,
                json={"faces": [{"box": [0.1, 0.2, 0.3, 0.4], "score": 0.9}]},
            )
        if label == "bad_score":
            return httpx.Response(
                200,
                json={
                    "faces": [{"box": [0.1, 0.2, 0.3, 0.4], "score": "hi"}],
                    "model": "m",
                },
            )
        if label in ("empty_faces", "payload_no_model", "payload_with_model"):
            return httpx.Response(200, json={"faces": [], "model": "m"})
        if label in ("retry_bg_5xx", "retry_manual_5xx"):
            return httpx.Response(503, json={"error": "cold"})
        raise AssertionError(f"unknown label {label}")

    _install(monkeypatch, handler)
    cfg_kw = {}
    if label == "payload_with_model":
        cfg_kw["model"] = "insightface-buffalo_l"
    if kind_or_ok == "ok":
        result = detect(_cfg(**cfg_kw), "data:image/jpeg;base64,xx", profile=profile)
        assert result.boxes == []
        assert result.model == "m"
    else:
        with pytest.raises(EndpointError) as ei:
            detect(_cfg(**cfg_kw), "data:image/jpeg;base64,xx", profile=profile)
        assert ei.value.kind == kind_or_ok
        assert ei.value.check == check
    assert calls["n"] == expect_calls, label
    if label == "payload_no_model":
        assert "model" not in seen_body
        assert seen_body.get("with_embedding") is False
    if label == "payload_with_model":
        assert seen_body.get("model") == "insightface-buffalo_l"


# ---------------------------------------------------------------------------
# (2) consistency check
# ---------------------------------------------------------------------------

def _fr(boxes, model="m"):
    return FacesResult(boxes=list(boxes), model=model)


@pytest.mark.parametrize(
    "label,result,ok,failed",
    [
        (
            "ok",
            _fr([Box(0.4, 0.2, 0.2, 0.2, 0.9)]),  # center (0.5, 0.3)
            True,
            None,
        ),
        ("no_face", _fr([]), False, "no_face"),
        (
            "center_off",
            _fr([Box(0.0, 0.0, 0.1, 0.1, 0.9)]),  # center (0.05, 0.05)
            False,
            "center_off",
        ),
        (
            "no_model",
            _fr([Box(0.4, 0.2, 0.2, 0.2, 0.9)], model=""),
            False,
            "no_model",
        ),
    ],
)
def test_faces_consistency_check(label, result, ok, failed):
    got_ok, got_failed = check_faces_consistency(result)
    assert (got_ok, got_failed) == (ok, failed), label


# ---------------------------------------------------------------------------
# (3) EXIF transpose + long-edge cap
# ---------------------------------------------------------------------------

def test_faces_prep_exif(tmp_path):
    # Orientation=6 on 40×20 → transposed 20×40
    path = tmp_path / "orient6.jpg"
    im = Image.new("RGB", (40, 20), (180, 40, 40))
    exif = im.getexif()
    exif[0x0112] = 6
    im.save(path, format="JPEG", quality=90, exif=exif)

    out = cover_to_faces_data_uri(str(path))
    assert out is not None
    uri, size = out
    assert size == (20, 40)
    header, b64 = uri.split(",", 1)
    assert header == "data:image/jpeg;base64"
    decoded = Image.open(io.BytesIO(base64.b64decode(b64)))
    assert decoded.size == (20, 40)

    # Long edge >650 → capped at 650
    big = tmp_path / "big.jpg"
    Image.new("RGB", (800, 100), (10, 20, 30)).save(big, format="JPEG", quality=90)
    out2 = cover_to_faces_data_uri(str(big))
    assert out2 is not None
    uri2, size2 = out2
    assert max(size2) == 650
    header2, b642 = uri2.split(",", 1)
    decoded2 = Image.open(io.BytesIO(base64.b64decode(b642)))
    assert decoded2.size == size2
    assert max(decoded2.size) == 650
