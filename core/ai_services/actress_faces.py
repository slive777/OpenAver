"""Background face results for favorite actress photos."""

import threading
from pathlib import Path

from PIL import Image

from core import actress_avatar
from core.actress_face import current_photo_fp, result_is_valid
from core.ai_services import faces_detect, faces_state, image_prep
from core.ai_services.faces_config import active_in
from core.config import load_config
from core.database import ActressRepository
from core.focal import device_state, face_runner
from core.focal.face_judge import judge_endpoint, judge_pigo
from core.logger import get_logger

logger = get_logger(__name__)
_STOP = "stop"
_SKIP = "skip"
_lock = threading.Lock()
_dirty = False
_running = False
_thread = None


def _repo():
    return ActressRepository()


def _target_model():
    try:
        from core.ai_services import faces_recompute

        return faces_state.meta_get(faces_recompute.META_TARGET)
    except Exception:
        logger.warning("[actress_faces] target model unavailable", exc_info=True)
        return None


def choose_source(cfg, local_disabled):
    if active_in(cfg):
        return "endpoint"
    return None if local_disabled else "pigo"


def needs_compute(row, photo_fp, source, target_model):
    if photo_fp is None or source is None:
        return False
    if not result_is_valid(row, photo_fp):
        return True
    if source == "endpoint":
        return row.face_model in ("", "local-pigo") or bool(target_model and row.face_model != target_model)
    return row.face_model == ""


def _upright_size(path):
    try:
        with Image.open(path) as image:
            w, h = image.size
        if image_prep.read_exif_orientation(str(path)) in (5, 6, 7, 8):
            w, h = h, w
        return (w, h) if w > 0 and h > 0 else None
    except Exception:
        logger.warning("[actress_faces] cannot read photo dimensions", exc_info=True)
        return None


def _detect_endpoint(row, fp):
    size = _upright_size(Path(fp[0]))
    if size is None:
        return _SKIP
    logger.info("[actress_faces] detect endpoint %s", row.name)
    result = faces_detect.detect(fp[0], 0.75, profile="background", notify=False)
    if result is None:
        return _SKIP
    if result.kind == "FAILED":
        return _STOP
    verdict = judge_endpoint(result.boxes, *size)
    return verdict.status, verdict.box, result.model or "external"


def _detect_pigo(row, fp):
    if row.photo_source == "local_crop":
        return "unsure", "", "local-pigo"
    logger.info("[actress_faces] detect pigo %s", row.name)
    result = face_runner.run_face_boxes(fp[0])
    if result[0] == "FOUND":
        verdict = judge_pigo(result[1], *result[2], row.photo_source)
        return verdict.status, verdict.box, "local-pigo"
    if result[1] == "detect_timeout":
        return "unsure", "", "local-pigo"
    if result[1] == "skipped_disabled":
        return _SKIP
    return (_STOP)


def _process_one(name):
    row = _repo().get_by_name(name)
    if row is None:
        return _SKIP
    cfg = load_config()
    source = choose_source(cfg, device_state.is_disabled_in(cfg))
    fp = current_photo_fp(name)
    if not needs_compute(row, fp, source, _target_model()):
        return _SKIP
    result = _detect_endpoint(row, fp) if source == "endpoint" else _detect_pigo(row, fp)
    if result in (_STOP, _SKIP):
        return result
    if current_photo_fp(name) != fp:
        return _SKIP
    status, box, model = result
    if not _repo().update_face_result(name, status, box, model, *fp):
        return _SKIP
    logger.info("[actress_faces] result %s %s", name, status)
    if status == "found":
        try:
            actress_avatar.get_or_create(_repo().get_by_name(name), Path(fp[0]))
        except Exception:
            logger.warning("[actress_faces] avatar generation failed", exc_info=True)
    return "done"


def kick():
    global _dirty, _running, _thread
    try:
        with _lock:
            _dirty = True
            if _running:
                return
            _running = True
            try:
                _thread = threading.Thread(target=_loop, name="actress-faces-sweep", daemon=True)
                _thread.start()
            except Exception:
                _running = False
                logger.exception("[actress_faces] worker start failed")
    except Exception:
        logger.exception("[actress_faces] kick failed")


def _loop():
    global _dirty, _running
    while True:
        with _lock:
            if not _dirty:
                _running = False
                return
            _dirty = False
        try:
            sweep()
        except Exception:
            logger.exception("[actress_faces] sweep failed")


def sweep():
    for row in _repo().get_all():
        try:
            if _process_one(row.name) == _STOP:
                break
        except Exception:
            logger.exception("[actress_faces] processing failed for %s", row.name)
