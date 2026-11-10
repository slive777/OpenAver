"""tests/unit/test_media_probe.py — TASK-198a-T1 探針純函式。

Fixture 產生指令（在 tests/fixtures/media/ 下執行；產生後凍結，勿重產）：

```bash
cd /home/slive/OpenAver && mkdir -p tests/fixtures/media && cd tests/fixtures/media
ffmpeg -hide_banner -loglevel error -y -f lavfi -i color=c=black:s=3840x2160:d=1:r=1 \
  -c:v libx265 -x265-params log-level=none -pix_fmt yuv420p uhd_hevc.mp4
ffmpeg -hide_banner -loglevel error -y -f lavfi -i color=c=black:s=1920x1080:d=1:r=1 \
  -c:v libx264 -pix_fmt yuv420p fhd_avc.mkv
head -c 2000 uhd_hevc.mp4 > truncated.mp4
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "testsrc2=s=3840x2160:d=3:r=1" \
  -c:v libx265 -x265-params log-level=none:crf=34 -pix_fmt yuv420p uhd_hevc_moov_end.mp4
```
"""
from __future__ import annotations

from pathlib import Path

import pytest

import core.media_probe as media_probe
from core.media_probe import probe_file, resolution_tier

_FIXTURES = Path(__file__).parent.parent / 'fixtures' / 'media'


@pytest.mark.parametrize(
    'filename,width,height,video_format,container',
    [
        ('uhd_hevc.mp4', 3840, 2160, 'HEVC', 'MPEG-4'),
        ('fhd_avc.mkv', 1920, 1080, 'AVC', 'Matroska'),
    ],
)
def test_probe_reads_resolution_codec_container_duration(
    filename, width, height, video_format, container,
):
    result = probe_file(str(_FIXTURES / filename))
    assert result.status == 'ok'
    assert result.width == width
    assert result.height == height
    assert result.video_format == video_format
    assert result.container == container
    assert isinstance(result.duration_ms, int)
    assert abs(result.duration_ms - 1000) <= 1000


@pytest.mark.parametrize('case', ['truncated_file', 'null_width'])
def test_truncated_file_is_no_video(case, monkeypatch):
    if case == 'truncated_file':
        result = probe_file(str(_FIXTURES / 'truncated.mp4'))
        assert result.status == 'no_video'
        assert result.truncated is True
        return

    class _Track:
        width = None
        height = 1080
        format = 'AVC'
        duration = 1000
        hdr_format = None
        frame_rate = '1.000'

    class _General:
        format = 'MPEG-4'
        duration = 1000
        istruncated = None
        overall_bit_rate = 1000

    class _Parsed:
        general_tracks = [_General()]
        video_tracks = [_Track()]
        audio_tracks = []
        text_tracks = []

    monkeypatch.setattr(
        media_probe.MediaInfo,
        'parse',
        staticmethod(lambda *_a, **_k: _Parsed()),
    )
    result = probe_file(str(_FIXTURES / 'uhd_hevc.mp4'))
    assert result.status == 'no_video'
    assert result.reason == 'no usable video dims'


def test_resolution_tier_boundaries():
    assert resolution_tier(3839, 2160) == '4K'
    assert resolution_tier(3839, 2159) == '2K'
    assert resolution_tier(3840, 1600) == '4K'
    assert resolution_tier(1920, 1072) == 'FHD'


def test_moov_at_end_is_read_with_small_cap(monkeypatch):
    path = _FIXTURES / 'uhd_hevc_moov_end.mp4'
    data = path.read_bytes()
    size = path.stat().st_size
    moov_offset = data.rfind(b'moov')
    assert size > 192 * 1024
    assert moov_offset > 196608

    monkeypatch.setattr(media_probe, '_CAPPED_READ_BYTES', 64 * 1024)
    capped_out = probe_file(str(path))
    assert capped_out.status != 'ok'

    monkeypatch.setattr(media_probe, '_CAPPED_READ_BYTES', 192 * 1024)
    result = probe_file(str(path))
    assert result.status == 'ok'
    assert result.width == 3840
    assert result.height == 2160
    assert isinstance(result.duration_ms, int)
    assert abs(result.duration_ms - 3000) <= 1000


@pytest.mark.parametrize(
    'case',
    ['missing', 'permission', 'library_load'],
)
def test_unreadable_file_is_not_no_video(case, monkeypatch):
    if case == 'library_load':
        def boom(*_args, **_kwargs):
            raise OSError(
                'Failed to load library from /fake/libmediainfo.so - simulated'
            )

        monkeypatch.setattr(media_probe.MediaInfo, 'parse', boom)
        with pytest.raises(OSError, match='Failed to load library'):
            probe_file(str(_FIXTURES / 'uhd_hevc.mp4'))
        return

    if case == 'missing':
        result = probe_file(str(_FIXTURES / 'does_not_exist_xyz.mp4'))
    else:
        def fake_open(*_args, **_kwargs):
            raise PermissionError('simulated NAS offline')

        monkeypatch.setattr(media_probe, 'open', fake_open, raising=False)
        result = probe_file(str(_FIXTURES / 'uhd_hevc.mp4'))
    assert result.status == 'unreadable'
