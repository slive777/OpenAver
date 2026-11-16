"""Refresh an existing external-library poster without touching its cover."""
import os
import stat
from typing import NamedTuple

from PIL import Image, ImageOps

from core.ai_services.image_prep import POSTER_CROP_RATIO, poster_crop_box
from core.atomic_write import atomic_write
from core.cover_layout import COVER_EXT, cover_base_stem, same_target_verdict
from core.focal.detector import parse_focal
from core.logger import get_logger
from core.organizer import POSTER_ALREADY_PORTRAIT_RATIO

logger = get_logger(__name__)


class PosterRefreshResult(NamedTuple):
    status: str


def refresh_poster(cover_fs, focal_str, *, external_mode_on) -> PosterRefreshResult:
    try:
        if not cover_fs or not os.path.isfile(cover_fs):
            return PosterRefreshResult("none")
        poster_fs = cover_base_stem(cover_fs) + "-poster" + COVER_EXT
        if not os.path.isfile(poster_fs):
            return PosterRefreshResult("none")
        if not external_mode_on:
            return PosterRefreshResult("skipped")
        is_same, _certain = same_target_verdict(cover_fs, poster_fs)
        if is_same or parse_focal(focal_str) is None:
            return PosterRefreshResult("skipped")
        try:
            with Image.open(cover_fs) as image:
                upright = ImageOps.exif_transpose(image).convert("RGB")
        except Exception as exc:
            logger.warning("Poster cover decode failed: %s", exc)
            return PosterRefreshResult("skipped")
        w, h = upright.size
        if h / w >= POSTER_ALREADY_PORTRAIT_RATIO or w <= round(POSTER_CROP_RATIO * h):
            return PosterRefreshResult("skipped")
        try:
            box = poster_crop_box(w, h, "manual", focal_str)
            poster_stat = os.stat(poster_fs)
            with atomic_write(poster_fs, suffix=".jpg") as f:
                upright.crop(box).save(f, format="JPEG", quality=95, subsampling=0)
                if hasattr(os, "fchmod"):
                    try:
                        os.fchmod(f.fileno(), stat.S_IMODE(poster_stat.st_mode))
                    except OSError as exc:
                        logger.warning("Poster mode preservation failed: %s", exc)
                if hasattr(os, "fchown"):
                    try:
                        os.fchown(f.fileno(), -1, poster_stat.st_gid)
                    except OSError as exc:
                        logger.warning("Poster group preservation failed: %s", exc)
            return PosterRefreshResult("updated")
        finally:
            upright.close()
    except Exception as exc:
        logger.warning("Poster refresh failed: %s", exc)
        return PosterRefreshResult("failed")
