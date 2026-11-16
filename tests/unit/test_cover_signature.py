import pytest

from core.cover_signature import apply_cover_change, cover_changed
from core.database import VideoRepository, init_db
from core.database.video import Video
from core.path_utils import to_file_uri
from core import thumbnail_cache

pytestmark = pytest.mark.usefixtures('isolate_reconcile_db')


@pytest.mark.parametrize('db_sig,live_sig,expected', [
    (None, (1, 2), False), ((1, 2), None, False),
    ((1, 2), (1, 2), False), ((1, 2), (1, 3), True),
])
def test_cover_changed_table(db_sig, live_sig, expected):
    assert cover_changed(db_sig, live_sig) is expected


@pytest.mark.parametrize('mode', ['auto', 'manual'])
def test_apply_cover_change_keeps_manual(tmp_path, monkeypatch, mocker, mode):
    db = tmp_path / 'test.db'
    init_db(db)
    monkeypatch.setattr('core.database.connection.get_db_path', lambda: db)
    mocker.patch('core.thumbnail_cache._thumb_dir', return_value=tmp_path / 'thumbs')
    submit = mocker.patch('core.focal_trigger.maybe_submit_video_focal')
    repo = VideoRepository(db)
    cover = tmp_path / 'cover.jpg'
    cover.write_bytes(b'cover')
    uri, cover_uri = to_file_uri(str(tmp_path / 'video.mp4')), to_file_uri(str(cover))
    repo.upsert(Video(path=uri, cover_path=cover_uri, number='ABF-348'))
    repo.update_auto_focal(uri, '0.3000', cover_uri)
    if mode == 'manual':
        repo.update_manual_focal(uri, '0.4000', expected_cover_path=cover_uri)
    before = repo.get_by_path(uri)
    thumb = thumbnail_cache.thumb_file_for(uri)
    thumb.parent.mkdir(parents=True, exist_ok=True)
    thumb.write_bytes(b'x')
    apply_cover_change(repo, uri, str(cover), {})
    after = repo.get_by_path(uri)
    assert not thumb.exists()
    if mode == 'manual':
        assert (after.crop_mode, after.auto_focal, after.focal_attempted_at) == (before.crop_mode, before.auto_focal, before.focal_attempted_at)
        submit.assert_not_called()
    else:
        assert (after.crop_mode, after.auto_focal, after.focal_attempted_at) == ('auto', '', None)
        submit.assert_called_once()
