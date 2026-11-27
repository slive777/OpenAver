from __future__ import annotations

import math
from typing import NamedTuple

PIGO_MIN_BOXES = 3
PIGO_MIN_SUM_Q = 8.0
PIGO_MULTI_MIN_BOXES = 2
PIGO_MULTI_MIN_SUM_Q = 3.0
MIN_SHORT_SIDE = 150
MIN_WINDOW_PX = 96
FACE_PAD = 1.9
FACE_CENTER_Y = 0.5


class FaceVerdict(NamedTuple):
    status: str
    box: str
    reason: str


def format_face_box(cx: float, cy: float, fs: float) -> str:
    return f"{cx:.4f},{cy:.4f},{fs:.4f}"


def parse_face_box(s: str) -> tuple[float, float, float] | None:
    if not isinstance(s, str) or s == "":
        return None
    parts = s.split(",")
    if len(parts) != 3:
        return None
    try:
        cx = float(parts[0])
        cy = float(parts[1])
        fs = float(parts[2])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(cx) or not math.isfinite(cy):
        return None
    if not math.isfinite(fs) or fs <= 0:
        return None
    return (cx, cy, fs)


def _is_second_person(g: list) -> bool:
    return len(g) >= PIGO_MULTI_MIN_BOXES and sum(x[3] for x in g) >= PIGO_MULTI_MIN_SUM_Q


def judge_pigo(dets, w, h, photo_source="") -> FaceVerdict:
    if photo_source == "local_crop":
        return FaceVerdict("unsure", "", "local_crop")
    if min(w, h) < MIN_SHORT_SIDE:
        return FaceVerdict("unsure", "", "too_small")
    if not dets:
        return FaceVerdict("none", "", "no_boxes")
    pts = [(d[0] * h, d[1] * w, d[2], d[3]) for d in dets]
    pts = sorted(pts, key=lambda p: -p[2] * p[3])
    groups: list = []
    for p in pts:
        for g in groups:
            a = g[0]
            if math.hypot(p[0] - a[0], p[1] - a[1]) < 0.5 * max(p[2], a[2]):
                g.append(p)
                break
        else:
            groups.append([p])
    groups = sorted(groups, key=lambda g: -sum(x[2] * x[3] for x in g))
    top = groups[0]
    sum_q = sum(x[3] for x in top)
    if len(top) < PIGO_MIN_BOXES or sum_q < PIGO_MIN_SUM_Q:
        return FaceVerdict("unsure", "", "few_boxes")
    multi = any(_is_second_person(g) for g in groups[1:])
    if multi:
        return FaceVerdict("multi", "", "second_person")
    den = sum(p[2] * p[3] for p in top) or 1
    cx = sum((p[1] / w) * p[2] * p[3] for p in top) / den
    cy = sum((p[0] / h) * p[2] * p[3] for p in top) / den
    face_px = sum(p[2] ** 2 * p[3] for p in top) / den
    if FACE_PAD * face_px < MIN_WINDOW_PX:
        return FaceVerdict("unsure", "", "window_small")
    return FaceVerdict("found", format_face_box(cx, cy, face_px / min(w, h)), "ok")


def judge_endpoint(boxes, w, h) -> FaceVerdict:
    if min(w, h) < MIN_SHORT_SIDE:
        return FaceVerdict("unsure", "", "too_small")
    if len(boxes) == 0:
        return FaceVerdict("none", "", "no_boxes")
    if len(boxes) >= 2:
        return FaceVerdict("multi", "", "second_person")
    x, y, bw, bh = boxes[0][0], boxes[0][1], boxes[0][2], boxes[0][3]
    cx = x + bw / 2
    cy = y + bh / 2
    face_px = max(bw * w, bh * h)
    if FACE_PAD * face_px < MIN_WINDOW_PX:
        return FaceVerdict("unsure", "", "window_small")
    return FaceVerdict("found", format_face_box(cx, cy, face_px / min(w, h)), "ok")


def crop_window(W, H, cx, cy, fs) -> tuple[int, int, int]:
    short = min(W, H)
    fs_px = fs * short
    side = max(1, min(round(FACE_PAD * fs_px), short))
    x0 = round(cx * W - side / 2)
    y0 = round(cy * H - FACE_CENTER_Y * side)
    x0 = min(max(x0, 0), W - side)
    y0 = min(max(y0, 0), H - side)
    return int(x0), int(y0), int(side)
