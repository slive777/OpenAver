import hashlib
import os
import random
import stat

import pytest
from PIL import Image, ImageChops, ImageStat

from core.poster_refresh import refresh_poster


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(directory):
    return {p.name: digest(p) for p in directory.iterdir() if p.is_file()}


def solid(path, color, size=(300, 200)):
    Image.new("RGB", size, color).save(path, quality=95, subsampling=0)


def stripes(path):
    rng = random.Random(200)
    image = Image.new("RGB", (300, 200))
    for x in range(300):
        color = tuple(rng.randrange(256) for _ in range(3))
        for y in range(200):
            image.putpixel((x, y), color)
    image.save(path, quality=100, subsampling=0)


def assert_poster_crop_x0(cover_path, poster_path, expected):
    with Image.open(cover_path) as src, Image.open(poster_path) as out:
        width = round(0.71 * src.height)
        assert out.size == (width, src.height)
        candidates = range(max(0, expected - 3), min(src.width - width, expected + 3) + 1)
        scores = {x: sum(ImageStat.Stat(ImageChops.difference(out, src.crop((x, 0, x + width, src.height)))).mean) for x in candidates}
        assert abs(min(scores, key=scores.get) - expected) <= 1


# 0.65: manual x0=124，auto 右裁 x0=158，避免兩者重合。
@pytest.mark.parametrize("focal,layout", [(0.65, 'fanart'), (0.2, 'fanart'), (0.4, 'fanart'), (0.6, 'fanart'), (0.8, 'fanart'), (0.0, 'fanart'), (1.0, 'fanart'), (0.4, 'cover')])
def test_recrop_range_matches_mask_formula(tmp_path, focal, layout):
    cover = tmp_path / ('movie-fanart.jpg' if layout == 'fanart' else 'movie.jpg')
    poster = tmp_path / 'movie-poster.jpg'
    fanart = tmp_path / 'movie-fanart.jpg'
    stripes(cover)
    if layout == 'cover':
        solid(fanart, 'blue')
    solid(poster, 'red')
    before = snapshot(tmp_path)
    result = refresh_poster(str(cover), f'{focal:.4f},0.5000', external_mode_on=True)
    assert result.status == 'updated'
    assert digest(cover) == before[cover.name]
    assert digest(fanart) == before[fanart.name]
    assert digest(poster) != before[poster.name]
    with Image.open(cover) as src, Image.open(poster) as out:
        width = round(0.71 * src.height)
        assert out.size == (width, src.height)
        expected = max(0, min(round(focal * src.width - width / 2), src.width - width))
        candidates = range(max(0, expected - 3), min(src.width - width, expected + 3) + 1)
        scores = {x: sum(ImageStat.Stat(ImageChops.difference(out, src.crop((x, 0, x + width, src.height)))).mean) for x in candidates}
        assert abs(min(scores, key=scores.get) - expected) <= 1


@pytest.mark.parametrize('alias', ['same', 'hardlink', 'symlink', 'uncertain'])
def test_redline_poster_aliasing_cover_never_written(tmp_path, monkeypatch, alias):
    poster = tmp_path / 'movie-poster.jpg'
    cover = poster if alias == 'same' else tmp_path / 'movie.jpg'
    if alias != 'symlink':
        solid(cover, 'green')
    if alias == 'hardlink':
        os.link(cover, poster)
    elif alias == 'symlink':
        solid(poster, 'red')
        try:
            cover.symlink_to(poster)
        except OSError as exc:
            pytest.skip(f'symlink unavailable: {exc}')
    elif alias == 'uncertain':
        solid(poster, 'red')
    before = snapshot(tmp_path)
    if alias == 'uncertain':
        def denied(*args):
            raise PermissionError('denied')
        monkeypatch.setattr(os.path, 'samefile', denied)
    assert refresh_poster(str(cover), '0.4000,0.5000', external_mode_on=True).status == ('failed' if alias == 'uncertain' else 'skipped')
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('case', ['missing_poster', 'empty', 'not_file', 'mode_off', 'broken'])
def test_nothing_to_refresh_writes_nothing(tmp_path, case):
    cover = tmp_path / 'movie.jpg'
    poster = tmp_path / 'movie-poster.jpg'
    solid(cover, 'green')
    if case != 'missing_poster':
        solid(poster, 'red')
    if case == 'broken':
        cover.write_bytes(b'broken image')
    before = snapshot(tmp_path)
    path = '' if case == 'empty' else str(tmp_path if case == 'not_file' else cover)
    result = refresh_poster(path, '0.4000,0.5000', external_mode_on=case != 'mode_off')
    assert result.status == (('failed' if case == 'broken' else 'skipped') if case not in ('missing_poster', 'empty', 'not_file') else 'none')
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('external_mode_on,expected', [(True, 'failed'), (False, 'none')])
def test_cover_dir_offline_reports_failed_only_in_external_mode(tmp_path, external_mode_on, expected):
    cover = tmp_path / 'gone' / 'movie.jpg'
    before = snapshot(tmp_path)
    result = refresh_poster(str(cover), '0.4000,0.5000', external_mode_on=external_mode_on)
    assert result.status == expected
    assert snapshot(tmp_path) == before
    assert not (tmp_path / 'gone').exists()


@pytest.mark.skipif(not hasattr(os, 'fchown'), reason='POSIX only')
def test_preserves_mode_and_attempts_group_even_if_denied(tmp_path, monkeypatch):
    cover, poster = tmp_path / 'movie.jpg', tmp_path / 'movie-poster.jpg'
    solid(cover, 'green')
    solid(poster, 'red')
    os.chmod(poster, 0o644)
    old = poster.stat()
    before = digest(poster)
    calls = []
    def denied(fd, uid, gid):
        calls.append((fd, uid, gid))
        raise PermissionError('denied')
    monkeypatch.setattr(os, 'fchown', denied)
    assert refresh_poster(str(cover), '0.4000,0.5000', external_mode_on=True).status == 'updated'
    assert digest(poster) != before
    assert stat.S_IMODE(poster.stat().st_mode) == 0o644
    assert len(calls) == 1 and calls[0][0] >= 0 and calls[0][1:] == (-1, old.st_gid)


@pytest.mark.parametrize('size', [(1000, 1400), (100, 200)])
def test_portrait_is_unchanged(tmp_path, size):
    cover, poster = tmp_path / 'movie.jpg', tmp_path / 'movie-poster.jpg'
    solid(cover, 'green', size)
    solid(poster, 'red')
    before = snapshot(tmp_path)
    assert refresh_poster(str(cover), '0.4000,0.5000', external_mode_on=True).status == 'skipped'
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('case', ['empty', 'not_file', 'broken', 'denied'])
def test_create_if_missing_failures_report_failed(tmp_path, monkeypatch, case):
    cover = tmp_path / 'movie.jpg'
    if case == 'not_file':
        path = str(tmp_path)
    elif case == 'empty':
        path = ''
    else:
        stripes(cover)
        if case == 'broken':
            cover.write_bytes(b'broken image')
        path = str(cover)
    before = snapshot(tmp_path)
    if case == 'denied':
        def denied(*args):
            raise PermissionError('denied')
        monkeypatch.setattr(os.path, 'samefile', denied)
    result = refresh_poster(path, '0.4000,0.5000', external_mode_on=True, create_if_missing=True)
    assert result.status == 'failed'
    assert snapshot(tmp_path) == before
    assert not (tmp_path / 'movie-poster.jpg').exists()


@pytest.mark.parametrize('crop_mode,focal', [('manual', '0.4000,0.5000'), ('auto', '0.5000,0.5000')])
def test_create_if_missing_places_poster_by_formula(tmp_path, crop_mode, focal):
    cover = tmp_path / 'movie.jpg'
    poster = tmp_path / 'movie-poster.jpg'
    fanart = tmp_path / 'movie-fanart.jpg'
    stripes(cover)
    solid(fanart, 'blue')
    expected = max(0, min(round(float(focal.split(',')[0]) * 300 - round(0.71 * 200) / 2), 300 - round(0.71 * 200)))
    before_cover = digest(cover)
    before_fanart = digest(fanart)
    result = refresh_poster(str(cover), focal, external_mode_on=True, crop_mode=crop_mode, create_if_missing=True)
    assert result.status == 'updated'
    assert poster.exists()
    assert digest(cover) == before_cover
    assert digest(fanart) == before_fanart
    assert_poster_crop_x0(cover, poster, expected)


@pytest.mark.skipif(not hasattr(os, 'fchown'), reason='POSIX only')
def test_new_poster_inherits_cover_mode(tmp_path):
    cover = tmp_path / 'movie.jpg'
    poster = tmp_path / 'movie-poster.jpg'
    solid(cover, 'green')
    os.chmod(cover, 0o644)
    result = refresh_poster(str(cover), '0.4000,0.5000', external_mode_on=True, create_if_missing=True)
    assert result.status == 'updated'
    assert stat.S_IMODE(poster.stat().st_mode) == 0o644


@pytest.mark.parametrize('alias', ['same', 'hardlink', 'symlink'])
def test_create_if_missing_alias_layouts_write_nothing(tmp_path, alias):
    poster = tmp_path / 'movie-poster.jpg'
    cover = poster if alias == 'same' else tmp_path / 'movie.jpg'
    if alias != 'symlink':
        solid(cover, 'green')
    if alias == 'hardlink':
        os.link(cover, poster)
    elif alias == 'symlink':
        solid(poster, 'red')
        try:
            cover.symlink_to(poster)
        except OSError as exc:
            pytest.skip(f'symlink unavailable: {exc}')
    before = snapshot(tmp_path)
    result = refresh_poster(str(cover), '0.4000,0.5000', external_mode_on=True, create_if_missing=True)
    assert result.status == 'skipped'
    assert snapshot(tmp_path) == before


def test_auto_without_focal_crops_right(tmp_path):
    cover = tmp_path / 'movie.jpg'
    poster = tmp_path / 'movie-poster.jpg'
    stripes(cover)
    result = refresh_poster(str(cover), '', external_mode_on=True, crop_mode='auto', create_if_missing=True)
    assert result.status == 'updated'
    win_w = round(0.71 * 200)
    assert_poster_crop_x0(cover, poster, 300 - win_w)
