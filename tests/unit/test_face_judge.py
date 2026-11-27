from __future__ import annotations

import pytest

from core.focal.face_judge import crop_window, judge_endpoint, judge_pigo, parse_face_box


@pytest.mark.parametrize(
    ("desc", "call", "expected"),
    [
        ("pigo 單框", lambda: judge_pigo([(0.4, 0.3, 100, 9.0)], 1000, 1000), "unsure"),
        ("pigo 三框 Σq=8.0", lambda: judge_pigo([(0.4, 0.3, 100, 2.0), (0.4, 0.3, 100, 2.0), (0.4, 0.3, 100, 4.0)], 1000, 1000), "found"),
        ("pigo 三框 Σq=7.9", lambda: judge_pigo([(0.4, 0.3, 100, 2.0), (0.4, 0.3, 100, 2.0), (0.4, 0.3, 100, 3.9)], 1000, 1000), "unsure"),
        ("pigo 無框", lambda: judge_pigo([], 1000, 1000), "none"),
        ("pigo 完美三框但 local_crop", lambda: judge_pigo([(0.4, 0.3, 100, 2.0), (0.4, 0.3, 100, 2.0), (0.4, 0.3, 100, 4.0)], 1000, 1000, "local_crop"), "unsure"),
        ("pigo 完美三框 gfriends", lambda: judge_pigo([(0.4, 0.3, 100, 2.0), (0.4, 0.3, 100, 2.0), (0.4, 0.3, 100, 4.0)], 1000, 1000, "gfriends"), "found"),
        ("pigo 完美三框短邊 149", lambda: judge_pigo([(0.4, 0.3, 100, 2.0), (0.4, 0.3, 100, 2.0), (0.4, 0.3, 100, 4.0)], 1000, 149), "unsure"),
        ("pigo 完美三框短邊 151", lambda: judge_pigo([(0.4, 0.3, 100, 2.0), (0.4, 0.3, 100, 2.0), (0.4, 0.3, 100, 4.0)], 1000, 151), "found"),
        ("pigo 窗 95.0", lambda: judge_pigo([(0.4, 0.3, 50, 2.0), (0.4, 0.3, 50, 2.0), (0.4, 0.3, 50, 4.0)], 1000, 1000), "unsure"),
        ("pigo 窗 96.9", lambda: judge_pigo([(0.4, 0.3, 51, 2.0), (0.4, 0.3, 51, 2.0), (0.4, 0.3, 51, 4.0)], 1000, 1000), "found"),
        ("端點無框", lambda: judge_endpoint([], 1000, 1000), "none"),
        ("端點恰一框", lambda: judge_endpoint([(0.4, 0.3, 0.2, 0.2, 0.9)], 1000, 1000), "found"),
        ("端點一框邊長 50px", lambda: judge_endpoint([(0.4, 0.3, 0.05, 0.05, 0.9)], 1000, 1000), "unsure"),
        ("端點一框短邊 149", lambda: judge_endpoint([(0.4, 0.3, 0.2, 0.2, 0.9)], 1000, 149), "unsure"),
    ],
)
def test_judge_only_crops_when_sure(desc, call, expected):
    v = call()
    assert v.status == expected
    if expected == "found":
        assert parse_face_box(v.box) is not None
    else:
        assert v.box == ""
    v = judge_pigo([(0.40, 0.30, 100, 4.0), (0.40, 0.30, 100, 2.0), (0.42, 0.32, 100, 2.0)], 1000, 1000)
    assert v.status == "found"
    got = parse_face_box(v.box)
    assert got is not None and abs(got[0] - 0.305) < 1e-4 and abs(got[1] - 0.405) < 1e-4 and abs(got[2] - 0.1) < 1e-4
    w = judge_endpoint([(0.4, 0.3, 0.2, 0.2, 0.9)], 1000, 800)
    assert w.status == "found"
    got2 = parse_face_box(w.box)
    assert got2 is not None and abs(got2[0] - 0.5) < 1e-4 and abs(got2[1] - 0.4) < 1e-4 and abs(got2[2] - 0.25) < 1e-4


@pytest.mark.parametrize(
    ("desc", "call", "expected"),
    [
        ("pigo 第二群 Σq=3.0", lambda: judge_pigo([(0.5, 0.3, 100, 4.0), (0.5, 0.3, 100, 2.0), (0.5, 0.3, 100, 2.0), (0.5, 0.8, 100, 1.5), (0.5, 0.8, 100, 1.5)], 1000, 1000), "multi"),
        ("pigo 第二群 Σq=2.9", lambda: judge_pigo([(0.5, 0.3, 100, 4.0), (0.5, 0.3, 100, 2.0), (0.5, 0.3, 100, 2.0), (0.5, 0.8, 100, 1.4), (0.5, 0.8, 100, 1.4)], 1000, 1000), "found"),
        ("pigo 兩群皆達門檻", lambda: judge_pigo([(0.5, 0.3, 100, 4.0), (0.5, 0.3, 100, 2.0), (0.5, 0.3, 100, 2.0), (0.5, 0.8, 100, 4.0), (0.5, 0.8, 100, 2.0), (0.5, 0.8, 100, 2.0)], 1000, 1000), "multi"),
        ("端點兩框", lambda: judge_endpoint([(0.4, 0.3, 0.2, 0.2, 0.9), (0.1, 0.1, 0.15, 0.15, 0.8)], 1000, 1000), "multi"),
        ("端點兩框分數 0.8/0.49", lambda: judge_endpoint([(0.4, 0.3, 0.2, 0.2, 0.8), (0.1, 0.1, 0.15, 0.15, 0.49)], 1000, 1000), "multi"),
    ],
)
def test_judge_multi_person_not_cropped(desc, call, expected):
    v = call()
    assert v.status == expected
    if expected == "found":
        assert parse_face_box(v.box) is not None
    else:
        assert v.box == ""


@pytest.mark.parametrize(
    ("W", "H", "cx", "cy", "fs", "expected"),
    [
        (1000, 1000, 0.5, 0.5, 0.1, (405, 405, 190)),
        (1000, 1000, 0.02, 0.02, 0.1, (0, 0, 190)),
        (1000, 1000, 0.99, 0.99, 0.1, (810, 810, 190)),
        (1000, 1000, 0.5, 0.5, 1.2, (0, 0, 1000)),
        (2000, 500, 0.5, 0.5, 0.2, (905, 155, 190)),
        (500, 2000, 0.5, 0.5, 0.2, (155, 905, 190)),
        (2000, 500, 0.5, 0.5, 0.6, (750, 0, 500)),
        (2000, 500, 0.01, 0.99, 0.2, None),
        (500, 2000, 0.99, 0.01, 0.2, None),
    ],
)
def test_crop_window_always_square_inside_image(W, H, cx, cy, fs, expected):
    x0, y0, side = crop_window(W, H, cx, cy, fs)
    assert 0 <= x0
    assert 0 <= y0
    assert x0 + side <= W
    assert y0 + side <= H
    assert side >= 1
    if expected is not None:
        assert (x0, y0, side) == expected
