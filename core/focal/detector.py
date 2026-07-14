"""Faithful port of MetaTube detector + selection + crop.

Ported from archives/metatube-sdk-go/detector/{detector.go,compute.go},
detector/internal/{geomath,position}, common/cluster, imageutil/crop.go.

Selection is NOT "biggest face": each detection is weighted by Scale*Q,
projected onto the cropped axis, grouped within 0.05 distance, and the
strongest group's weighted-average position is returned.
"""
import math
import os

from PIL import Image

from core.logger import get_logger

from .pigo import Pigo, rgb_to_grayscale

logger = get_logger(__name__)

# detector.go constants
MAX_IMAGE_WIDTH = 650
MIN_FACE_SIZE = 20
MAX_FACE_SIZE = MAX_IMAGE_WIDTH * 0.8   # 520
SHIFT_FACTOR = 0.10
SCALE_FACTOR = 1.08
CLUSTER_TOLERANCE = 0.05                # compute.go

# Canonical product work-width the background worker feeds detect_focal
# (CD-98a-10, T2 bench 2026-07-13): 650 kept. Narrower widths (256/384/512)
# diverged from the P0 owner-validated 650 focal on 3/4 uncensored covers
# (consistency 1-2/4; 256 missed a face); speed gain (0.33-1.35s vs ~2.2s)
# didn't justify the lost hit quality. ~2.2s/img on a background single
# worker is within spec A.5's accepted ~3s. See TASK-98a-T2.md.
WORK_WIDTH = MAX_IMAGE_WIDTH            # 650

# advanced multi-angle scan (detector.go)
_FIXED_ANGLES = [0.00, 0.13, 0.87]      # pigo internal rotation (radians frac)
_ROTATED_ANGLES = [0.0, 90.0, 270.0]    # physical image rotation (degrees)

# cascade is packaged alongside this module (core/focal/facefinder), unlike
# the harness which read it from the harness/ dir one level up.
_CASCADE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'facefinder')

_classifier = None


def _get_classifier():
    global _classifier
    if _classifier is None:
        with open(_CASCADE_PATH, 'rb') as f:
            _classifier = Pigo().unpack(f.read())
    return _classifier


def _make_cascade_params(pixels, rows, cols):
    return {
        'pixels': pixels, 'rows': rows, 'cols': cols, 'dim': cols,
        'min': MIN_FACE_SIZE, 'max': int(MAX_FACE_SIZE),
        'shift': SHIFT_FACTOR, 'scale': SCALE_FACTOR,
    }


def detect_faces(img, angles=None):
    """detector.go DetectFaces: single param-set, one or more pigo angles."""
    if angles is None:
        angles = [0.0]
    pg = _get_classifier()
    pixels, w, h = rgb_to_grayscale(img)
    cp = _make_cascade_params(pixels, h, w)
    faces = []
    for a in angles:
        faces.extend(pg.run_cascade(cp, a))
    return faces


def _rotate_point(x, y, width, height, angle_deg):
    """Port of geomath.RotatePoint (maps a point back after image rotation)."""
    if width <= 0 or height <= 0:
        return 0, 0
    rad = angle_deg * math.pi / 180.0
    cos_v = math.cos(rad)
    sin_v = math.sin(rad)

    def rot(px, py):
        return px * cos_v + py * sin_v, -px * sin_v + py * cos_v

    w = float(width - 1)
    h = float(height - 1)
    corners = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]
    rx0, ry0 = rot(*corners[0])
    min_x = max_x = rx0
    min_y = max_y = ry0
    for cx, cy in corners[1:]:
        rx, ry = rot(cx, cy)
        min_x = min(min_x, rx); max_x = max(max_x, rx)
        min_y = min(min_y, ry); max_y = max(max_y, ry)
    new_w = int(round(max_x - min_x + 1))
    new_h = int(round(max_y - min_y + 1))
    rx, ry = rot(float(x), float(y))
    ix = int(round(rx - min_x))
    iy = int(round(ry - min_y))
    if ix < 0:
        ix = 0
    elif ix >= new_w:
        ix = new_w - 1
    if iy < 0:
        iy = 0
    elif iy >= new_h:
        iy = new_h - 1
    return ix, iy


def detect_faces_with_rotation(img, rotated_angle, angles):
    """detector.go DetectFacesWithRotation."""
    orig_w, orig_h = img.size
    if rotated_angle == 0:
        return detect_faces(img, angles)
    # PIL rotate is counter-clockwise for positive angles, matching imaging.Rotate.
    rotated = img.rotate(rotated_angle, expand=True)
    faces = detect_faces(rotated, angles)
    inv_angle = (360 - rotated_angle) % 360
    rw, rh = rotated.size
    out = []
    for (row, col, scale, q) in faces:
        x, y = _rotate_point(col, row, rw, rh, inv_angle)
        x = max(min(x, orig_w), 0)
        y = max(min(y, orig_h), 0)
        out.append((y, x, scale, q))  # keep (row, col, scale, q)
    return out


def detect_faces_with_multi_angles(img):
    """detector.go DetectFacesWithMultiAngles: 3 rotations x 3 pigo angles."""
    faces = []
    for ra in _ROTATED_ANGLES:
        faces.extend(detect_faces_with_rotation(img, ra, _FIXED_ANGLES))
    return faces


# --- selection (compute.go) ------------------------------------------------

def _dominant_axis_by_ratio(width, height, ratio):
    """compute.go dominantAxisByRatio: 0=X, 1=Y."""
    if int(height * ratio) < width:
        return 0
    return 1


class _UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def _cluster_and_select(width, height, faces, axis):
    """compute.go clusterFaceVectors + getDominantVector.

    Returns (pos, found). pos is a single ratio on the dominant axis."""
    if not faces:
        return 0.0, False
    # weighted vectors projected onto the dominant axis
    positions = []
    weights = []
    for (row, col, scale, q) in faces:
        if axis == 0:
            pos = col / width
        else:
            pos = row / height
        positions.append(pos)
        weights.append(float(scale) * float(q))

    n = len(positions)
    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if abs(positions[i] - positions[j]) <= CLUSTER_TOLERANCE:
                uf.union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    # sort groups by total weight (descending); take strongest
    group_list = list(groups.values())
    group_list.sort(key=lambda members: sum(weights[m] for m in members), reverse=True)
    best = group_list[0]

    total_w = sum(weights[m] for m in best)
    if total_w <= 0:
        return 0.0, False
    pos = sum(positions[m] * weights[m] for m in best) / total_w
    return pos, True


def _cluster_and_select_2d(width, height, faces, axis):
    """2D extension of _cluster_and_select (CD-98a-4).

    Reuses the exact clustering/group-selection of _cluster_and_select
    (dominant-axis projection -> 0.05 union-find clustering -> strongest
    group by summed Scale*Q weight). For the winning group, computes the
    weighted-average centroid on BOTH axes (x = col/width, y = row/height)
    instead of only the dominant axis.

    Returns (x_ratio, y_ratio) or None (no faces / degenerate zero-weight
    group). The x component equals _cluster_and_select's value when
    axis == 0, and the y component equals it when axis == 1 — 2D selection
    does not change which group is chosen, only which axes are averaged.
    """
    if not faces:
        return None

    positions = []   # dominant-axis projection, used only for clustering
    xs = []
    ys = []
    weights = []
    for (row, col, scale, q) in faces:
        pos = col / width if axis == 0 else row / height
        positions.append(pos)
        xs.append(col / width)
        ys.append(row / height)
        weights.append(float(scale) * float(q))

    n = len(positions)
    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if abs(positions[i] - positions[j]) <= CLUSTER_TOLERANCE:
                uf.union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    group_list = list(groups.values())
    group_list.sort(key=lambda members: sum(weights[m] for m in members), reverse=True)
    best = group_list[0]

    total_w = sum(weights[m] for m in best)
    if total_w <= 0:
        return None
    x_ratio = sum(xs[m] * weights[m] for m in best) / total_w
    y_ratio = sum(ys[m] * weights[m] for m in best) / total_w
    return x_ratio, y_ratio


def find_primary_face_axis_ratio(img, ratio, advanced, work_width=MAX_IMAGE_WIDTH):
    """detector.go FindPrimaryFaceAxisRatio.

    Returns (pos, found, faces, work_img_size, axis). Extra returns are for
    the harness debug overlay (not in the Go signature)."""
    w, h = img.size
    if w > work_width:
        nh = max(1, int(round(work_width * h / w)))
        work = img.resize((work_width, nh), Image.NEAREST)
    else:
        work = img
    ww, wh = work.size

    if advanced:
        faces = detect_faces_with_multi_angles(work)
    else:
        faces = detect_faces(work)

    axis = _dominant_axis_by_ratio(ww, wh, ratio)
    pos, found = _cluster_and_select(ww, wh, faces, axis)
    return pos, found, faces, (ww, wh), axis


def detect_focal(fs_path, ratio, work_width=MAX_IMAGE_WIDTH):
    """Product entry point (CD-98a-1/-2/-4): single-angle face detection ->
    2D focal centroid.

    fs_path is a caller-resolved filesystem path (callers own the
    URI -> fs path resolution via core.path_utils; this function never
    touches file:// URIs). Returns (x_ratio, y_ratio) in [0,1]x[0,1], or
    None when no face is found. Never raises — on image-open failure or a
    missing/corrupt cascade it logs a warning and returns None so callers
    fall back to the existing right-crop behavior (load-bearing wall).
    """
    try:
        img = Image.open(fs_path)
        w, h = img.size
        if w > work_width:
            nh = max(1, int(round(work_width * h / w)))
            work = img.resize((work_width, nh), Image.NEAREST)
        else:
            work = img
        ww, wh = work.size

        faces = detect_faces(work)  # single-angle only (CD-98a-2)

        axis = _dominant_axis_by_ratio(ww, wh, ratio)
        return _cluster_and_select_2d(ww, wh, faces, axis)
    except Exception as e:
        logger.warning(f"detect_focal failed for {fs_path}: {e}")
        return None


# --- serde (CD-98a-3: canonical "x,y" 4-decimal string) --------------------

def format_focal(focal):
    """(x, y) tuple -> "x.xxxx,y.xxxx"; None -> ''."""
    if focal is None:
        return ''
    x, y = focal
    return f"{x:.4f},{y:.4f}"


def parse_focal(s):
    """"x.xxxx,y.xxxx" -> (x, y) floats; '' / None / malformed -> None.

    Contract: x and y are ratios in the closed [0,1]x[0,1] unit square
    (inclusive bounds). Defensive: never raises; wrong # of parts,
    non-float, non-finite (nan/inf), or out-of-[0,1]-range -> None.
    Callers read this from persisted DB rows that could be hand-corrupted,
    so any of the above must degrade to "unset" (right-crop fallback)
    rather than leak into crop math / CSS object-position.
    """
    if not s:
        return None
    parts = s.split(',')
    if len(parts) != 2:
        return None
    try:
        x, y = float(parts[0]), float(parts[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None
    return x, y


# --- crop (imageutil/crop.go) ----------------------------------------------

def crop_image_position(img, ratio, pos):
    """Faithful port of imageutil.CropImagePosition."""
    min_ratio, max_ratio = 1e-2, 1e2
    if ratio < min_ratio or ratio > max_ratio:
        return img
    width, height = img.size
    w, h = width, height
    x, y = 0, 0
    # Mirror the Go control flow exactly (w is reassigned in the condition).
    w = int(height * ratio)
    if w < width:
        x = max(min(int(width * pos) - w // 2, width - w), 0)
    else:
        h = int(width / ratio)
        if h < height:
            y = max(min(int(height * pos) - h // 2, height - h), 0)
    # Go's SubImage intersects with image bounds; PIL.crop would pad instead,
    # so clamp the rect to bounds to reproduce the intersection behavior.
    right = min(x + w, width)
    bottom = min(y + h, height)
    return img.crop((x, y, right, bottom))
