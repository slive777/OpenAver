"""core.media_probe — 讀影片檔本身的探針純函式（TASK-198a-T1）。

只讀檔、不碰 DB。上游（worker／端點）先用 ``is_available()`` 擋原生庫不可用；
單檔失敗分 ``no_video``（記失敗）與 ``unreadable``（不記、下次可重試）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pymediainfo import MediaInfo

from core.logger import get_logger

logger = get_logger(__name__)

_CAPPED_READ_BYTES = 16 * 1024 * 1024  # 16 MiB；呼叫時讀模組全域（BE-TEST-38）

RESOLUTION_TIERS = ('SD', 'HD', 'FHD', '2K', '4K', '8K')

_CODEC_LABELS = {
    'AVC': 'H.264',
    'HEVC': 'HEVC',
    'AV1': 'AV1',
    'VP9': 'VP9',
    'MPEG-4 Visual': 'MPEG-4',
    'VC-1': 'VC-1',
}

_available_cache: bool | None = None


@dataclass(frozen=True)
class ProbeResult:
    status: Literal['ok', 'no_video', 'unreadable']
    reason: str
    width: int | None
    height: int | None
    video_format: str | None
    duration_ms: int | None
    hdr_format: str | None
    frame_rate: float | None
    overall_bitrate: int | None
    container: str | None
    audio_langs: tuple[str, ...]
    subtitle_langs: tuple[str, ...]
    truncated: bool


class _CappedReader:
    """累計讀取量上限；seek／tell 委派真檔，只有 read 計量與封頂。"""

    def __init__(self, f):
        self._f = f
        self._read = 0
        self._cap = _CAPPED_READ_BYTES

    def read(self, n=-1):
        if self._read >= self._cap:
            return b''
        if n is None or n < 0:
            n = self._cap - self._read
        else:
            n = min(n, self._cap - self._read)
        chunk = self._f.read(n)
        self._read += len(chunk)
        return chunk

    def seek(self, offset, whence=0):
        return self._f.seek(offset, whence)

    def tell(self):
        return self._f.tell()


def is_available() -> bool:
    """快取一次 ``MediaInfo.can_parse()``；原生庫載不起來時上游先擋。"""
    global _available_cache
    if _available_cache is None:
        _available_cache = bool(MediaInfo.can_parse())
    return _available_cache


def video_codec_label(video_format: str | None) -> str:
    if video_format is None:
        return ''
    return _CODEC_LABELS.get(video_format, video_format)


def resolution_tier(width, height) -> str | None:
    if not isinstance(width, int) or not isinstance(height, int):
        return None
    if width <= 0 or height <= 0:
        return None
    if height >= 4320 or width >= 7680:
        return '8K'
    if height >= 2160 or width >= 3840:
        return '4K'
    if height >= 1440 or width >= 2560:
        return '2K'
    if height >= 1080 or width >= 1920:
        return 'FHD'
    if height >= 720 or width >= 1280:
        return 'HD'
    return 'SD'


def _coerce_int(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _is_truncated(istruncated) -> bool:
    if istruncated is None:
        return False
    return str(istruncated).strip().lower() == 'yes'


def _lang_tuple(tracks) -> tuple[str, ...]:
    langs: list[str] = []
    for track in tracks:
        lang = getattr(track, 'language', None)
        if lang is None:
            continue
        text = str(lang).strip()
        if text:
            langs.append(text)
    return tuple(langs)


def _empty(
    *,
    status: Literal['ok', 'no_video', 'unreadable'],
    reason: str,
    container: str | None = None,
    truncated: bool = False,
    width: int | None = None,
    height: int | None = None,
    video_format: str | None = None,
    duration_ms: int | None = None,
    hdr_format: str | None = None,
    frame_rate: float | None = None,
    overall_bitrate: int | None = None,
    audio_langs: tuple[str, ...] = (),
    subtitle_langs: tuple[str, ...] = (),
) -> ProbeResult:
    return ProbeResult(
        status=status,
        reason=reason,
        width=width,
        height=height,
        video_format=video_format,
        duration_ms=duration_ms,
        hdr_format=hdr_format,
        frame_rate=frame_rate,
        overall_bitrate=overall_bitrate,
        container=container,
        audio_langs=audio_langs,
        subtitle_langs=subtitle_langs,
        truncated=truncated,
    )


def probe_file(fs_path: str) -> ProbeResult:
    try:
        with open(fs_path, 'rb') as raw:
            reader = _CappedReader(raw)
            mi = MediaInfo.parse(reader, parse_speed=0.0, full=True)
    except OSError as exc:
        # 原生庫載不起來不是單檔失敗（CD-198a-2）；字面見 pymediainfo._get_library。
        if 'Failed to load library' in str(exc):
            raise
        reason = f'oserror: {exc}'
        logger.info('media_probe unreadable path=%s reason=%s', fs_path, reason)
        return _empty(
            status='unreadable',
            reason=reason,
        )
    except (RuntimeError, ValueError) as exc:
        reason = f'parse: {exc}'
        logger.info('media_probe unreadable path=%s reason=%s', fs_path, reason)
        return _empty(
            status="unreadable",
            reason=reason,
        )

    general = next(iter(mi.general_tracks), None)
    video = next(iter(mi.video_tracks), None)
    container = getattr(general, 'format', None) if general is not None else None
    truncated = _is_truncated(getattr(general, 'istruncated', None) if general else None)
    duration_ms = _coerce_int(getattr(general, 'duration', None) if general else None)
    if duration_ms is None and video is not None:
        duration_ms = _coerce_int(getattr(video, 'duration', None))
    overall_bitrate = _coerce_int(
        getattr(general, 'overall_bit_rate', None) if general else None
    )
    audio_langs = _lang_tuple(mi.audio_tracks)
    subtitle_langs = _lang_tuple(mi.text_tracks)
    width = _coerce_int(getattr(video, 'width', None)) if video is not None else None
    height = _coerce_int(getattr(video, 'height', None)) if video is not None else None
    video_format = getattr(video, 'format', None) if video is not None else None
    hdr_format = getattr(video, 'hdr_format', None) if video is not None else None
    frame_rate = _coerce_float(getattr(video, 'frame_rate', None)) if video is not None else None

    # ok＝有 video track 且寬高皆正整數（CD-198a-2）。
    if video is None or not (isinstance(width, int) and width > 0) or not (isinstance(height, int) and height > 0):
        reason = 'no video track' if video is None else 'no usable video dims'
        logger.info('media_probe no_video path=%s reason=%s', fs_path, reason)
        return _empty(
            status='no_video',
            reason=reason,
            container=container,
            truncated=truncated,
            width=width,
            height=height,
            video_format=video_format,
            duration_ms=duration_ms,
            overall_bitrate=overall_bitrate,
            audio_langs=audio_langs,
            subtitle_langs=subtitle_langs,
        )

    return ProbeResult(
        status='ok',
        reason='ok',
        width=width,
        height=height,
        video_format=video_format,
        duration_ms=duration_ms,
        hdr_format=hdr_format,
        frame_rate=frame_rate,
        overall_bitrate=overall_bitrate,
        container=container,
        audio_langs=audio_langs,
        subtitle_langs=subtitle_langs,
        truncated=truncated,
    )
