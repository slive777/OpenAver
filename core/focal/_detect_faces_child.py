"""Subprocess protocol for collecting all Pigo face boxes."""
import json
import sys
import traceback

from PIL import Image, ImageOps

from core.focal import detector


def faces_payload(dets, s, w, h):
    return [[f[0] / s / h, f[1] / s / w, f[2] / s, f[3]] for f in dets]


def build_payload(fs_path):
    try:
        with Image.open(fs_path) as source:
            img = ImageOps.exif_transpose(source).convert('RGB')
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        return {'error': 'unreadable'}
    w, h = img.size
    s = detector.WORK_WIDTH / w if w > detector.WORK_WIDTH else 1
    work = img.resize((round(w*s), round(h*s)), Image.NEAREST) if s < 1 else img
    return {'faces': faces_payload(detector.detect_faces(work), s, w, h), 'size': [w, h]}


def main():
    try:
        fs_path = sys.argv[1]
        sys.stdout.write('READY\n')
        sys.stdout.flush()
        sys.stdout.write(json.dumps(build_payload(fs_path)) + '\n')
        sys.stdout.flush()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
