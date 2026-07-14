"""Faithful pure-Python port of esimov/pigo core (cascade unpack + classify + RunCascade).

Ported 1:1 from archives/pigo/core/{pigo.go,grayscale.go,utils.go}.
No simplification: bit-exact integer arithmetic, dual depth semantics
(real tree depth for traversal vs 2^depth for leaf index / root stride),
and the rotated-region classifier with the original quantized sin/cos tables.
"""
import struct

# Quantized cos/sin tables (256 == 1.0), copied verbatim from pigo.go.
_QCOS = (256, 251, 236, 212, 181, 142, 97, 49, 0, -49, -97, -142, -181, -212,
         -236, -251, -256, -251, -236, -212, -181, -142, -97, -49, 0, 49, 97,
         142, 181, 212, 236, 251, 256)
_QSIN = (0, 49, 97, 142, 181, 212, 236, 251, 256, 251, 236, 212, 181, 142, 97,
         49, 0, -49, -97, -142, -181, -212, -236, -251, -256, -251, -236, -212,
         -181, -142, -97, -49, 0)


class Pigo:
    def __init__(self):
        self.tree_codes = []       # list[int]  (signed int8 values)
        self.tree_pred = []        # list[float]
        self.tree_threshold = []   # list[float]
        self.tree_depth = 0        # real depth (e.g. 6)
        self.tree_num = 0

    def unpack(self, packet):
        # skip first 8 bytes (pigo.go)
        pos = 8
        tree_depth = struct.unpack_from('<I', packet, pos)[0]
        pos += 4
        tree_num = struct.unpack_from('<I', packet, pos)[0]
        pos += 4

        n_code = 4 * (2 ** tree_depth) - 4   # signed code bytes per tree
        n_leaf = 2 ** tree_depth             # predictions per tree

        codes = []
        pred = []
        thr = []
        code_fmt = '<%db' % n_code           # signed int8
        pred_fmt = '<%df' % n_leaf
        for _ in range(tree_num):
            codes.extend((0, 0, 0, 0))       # 4 zero bytes prepended per tree
            codes.extend(struct.unpack_from(code_fmt, packet, pos))
            pos += n_code
            pred.extend(struct.unpack_from(pred_fmt, packet, pos))
            pos += 4 * n_leaf
            thr.append(struct.unpack_from('<f', packet, pos)[0])
            pos += 4

        self.tree_codes = codes
        self.tree_pred = pred
        self.tree_threshold = thr
        self.tree_depth = tree_depth
        self.tree_num = tree_num
        return self

    # --- classifiers ------------------------------------------------------

    def classify_region(self, r, c, s, pixels, dim):
        codes = self.tree_codes
        pred = self.tree_pred
        thr = self.tree_threshold
        depth = self.tree_depth       # traversal count (6)
        n_leaf = 1 << depth           # 2^depth (leaf index base / root stride)
        tn = self.tree_num

        r <<= 8   # r*256
        c <<= 8
        out = 0.0
        root = 0
        for i in range(tn):
            idx = 1
            for _ in range(depth):
                b = root + 4 * idx
                x1 = (((r + codes[b] * s) >> 8) * dim) + ((c + codes[b + 1] * s) >> 8)
                x2 = (((r + codes[b + 2] * s) >> 8) * dim) + ((c + codes[b + 3] * s) >> 8)
                idx = (idx << 1) + (1 if pixels[x1] <= pixels[x2] else 0)
            out += pred[n_leaf * i + idx - n_leaf]
            if out <= thr[i]:
                return -1.0
            root += 4 * n_leaf
        return out - thr[tn - 1]

    def classify_rotated_region(self, r, c, s, a, nrows, ncols, pixels, dim):
        codes = self.tree_codes
        pred = self.tree_pred
        thr = self.tree_threshold
        depth = self.tree_depth
        n_leaf = 1 << depth
        tn = self.tree_num

        ai = int(32.0 * a)
        qsin = s * _QSIN[ai]
        qcos = s * _QCOS[ai]

        out = 0.0
        root = 0
        for i in range(tn):
            idx = 1
            for _ in range(depth):
                b = root + 4 * idx
                cb0 = codes[b]
                cb1 = codes[b + 1]
                cb2 = codes[b + 2]
                cb3 = codes[b + 3]
                # NOTE: the reference clamps both r and c against nrows-1 (verbatim).
                r1 = abs(min(nrows - 1, max(0, (65536 * r + qcos * cb0 - qsin * cb1) >> 16)))
                c1 = abs(min(nrows - 1, max(0, (65536 * c + qsin * cb0 + qcos * cb1) >> 16)))
                r2 = abs(min(nrows - 1, max(0, (65536 * r + qcos * cb2 - qsin * cb3) >> 16)))
                c2 = abs(min(nrows - 1, max(0, (65536 * c + qsin * cb2 + qcos * cb3) >> 16)))
                idx = (idx << 1) + (1 if pixels[r1 * dim + c1] <= pixels[r2 * dim + c2] else 0)
            out += pred[n_leaf * i + idx - n_leaf]
            if out <= thr[i]:
                return -1.0
            root += 4 * n_leaf
        return out - thr[tn - 1]

    # --- detection --------------------------------------------------------

    def run_cascade(self, cp, angle):
        """cp: dict(pixels, rows, cols, dim, min, max, shift, scale).
        Returns list of (row, col, scale, q) detections with q > 0."""
        pixels = cp['pixels']
        rows = cp['rows']
        cols = cp['cols']
        dim = cp['dim']
        min_size = cp['min']
        max_size = cp['max']
        shift = cp['shift']
        scale_factor = cp['scale']

        dets = []
        classify_region = self.classify_region
        classify_rotated = self.classify_rotated_region

        rotated = angle > 0.0
        a = angle if angle <= 1.0 else 1.0

        scale = min_size
        while scale <= max_size:
            step = int(shift * scale)
            if step < 1:
                step = 1
            offset = scale // 2 + 1
            row = offset
            row_max = rows - offset
            col_max = cols - offset
            while row <= row_max:
                col = offset
                while col <= col_max:
                    if rotated:
                        q = classify_rotated(row, col, scale, a, rows, cols, pixels, dim)
                    else:
                        q = classify_region(row, col, scale, pixels, dim)
                    if q > 0.0:
                        dets.append((row, col, scale, q))
                    col += step
                row += step
            # scale grow rule, avoiding infinite loop (pigo.go)
            grow = scale * scale_factor - scale
            scale = int(scale + (grow if grow > 2 else 2))
        return dets

    def cluster_detections(self, detections, iou_threshold):
        """IoU clustering (pigo.go ClusterDetections). Kept for the port oracle;
        MetaTube's selection uses its own axis clustering instead."""
        dets = sorted(detections, key=lambda d: d[3])  # by Q ascending
        n = len(dets)
        assigned = [False] * n
        clusters = []

        def iou(d1, d2):
            r1, c1, s1 = d1[0], d1[1], d1[2]
            r2, c2, s2 = d2[0], d2[1], d2[2]
            over_row = max(0.0, min(r1 + s1 / 2, r2 + s2 / 2) - max(r1 - s1 / 2, r2 - s2 / 2))
            over_col = max(0.0, min(c1 + s1 / 2, c2 + s2 / 2) - max(c1 - s1 / 2, c2 - s2 / 2))
            return over_row * over_col / (s1 * s1 + s2 * s2 - over_row * over_col)

        for i in range(n):
            if assigned[i]:
                continue
            r = c = s = n_acc = 0
            q = 0.0
            for j in range(n):
                if iou(dets[i], dets[j]) > iou_threshold:
                    assigned[j] = True
                    r += dets[j][0]
                    c += dets[j][1]
                    s += dets[j][2]
                    q += dets[j][3]
                    n_acc += 1
            if n_acc > 0:
                clusters.append((r // n_acc, c // n_acc, s // n_acc, q))
        return clusters


def rgb_to_grayscale(img):
    """Faithful port of pigo RgbToGrayscale.

    Reference reads 16-bit RGBA (r16 = r8*257 for opaque images) then divides
    by 256, i.e. (0.299R+0.587G+0.114B)*257/256 truncated to uint8.
    Returns (bytearray pixels, width, height)."""
    rgb = img.convert('RGB')
    w, h = rgb.size
    data = rgb.tobytes()
    gray = bytearray(w * h)
    i = 0
    k = 257.0 / 256.0
    for o in range(w * h):
        r = data[i]; g = data[i + 1]; b = data[i + 2]
        i += 3
        gray[o] = int((0.299 * r + 0.587 * g + 0.114 * b) * k)
    return gray, w, h
