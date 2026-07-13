"""core.focal — face-aware focal-point detection (TASK-98a-T1, T3, T5).

Public surface:
    detect_focal(fs_path, ratio, work_width) -> (x_ratio, y_ratio) | None
    crop_image_position(img, ratio, pos) -> PIL.Image
    requires_face_detection(number, maker="") -> bool
    gate_verdict(number, maker="") -> (bool, str)
    format_focal(focal) -> str
    parse_focal(s) -> (x_ratio, y_ratio) | None
    submit_focal(kind, id, fs_path, ratio, commit) -> None
"""
from .detector import (
    WORK_WIDTH,
    crop_image_position,
    detect_focal,
    format_focal,
    parse_focal,
)
from .gate import gate_verdict, requires_face_detection
from .worker import submit_focal

__all__ = [
    "WORK_WIDTH",
    "crop_image_position",
    "detect_focal",
    "requires_face_detection",
    "gate_verdict",
    "format_focal",
    "parse_focal",
    "submit_focal",
]
