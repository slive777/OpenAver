import pytest

from core.enricher import _apply_first_ingest_sidecar
from core.first_ingest import FirstIngest


@pytest.mark.parametrize('with_nfo', [True, False], ids=['with_nfo', 'without_nfo'])
def test_first_ingest_sidecar_skipped_when_nfo_exists(tmp_path, with_nfo):
    video = tmp_path / 'ABC-123 我的中文標題.mp4'
    video.write_bytes(b'0')
    if with_nfo:
        video.with_suffix('.nfo').write_text('x')
    meta = {'title': 'SITE-TITLE-PLACEHOLDER', 'actresses': [], 'maker': ''}
    policy = FirstIngest({'suffix_keywords': []}, lambda _: None)

    result = _apply_first_ingest_sidecar(
        policy, meta, {'title': 'SITE-TITLE-PLACEHOLDER'}, str(video), 'ABC-123', 'javbus'
    )

    if with_nfo:
        assert result is False
        assert meta['title'] == 'SITE-TITLE-PLACEHOLDER'
        assert 'original_title' not in meta
    else:
        assert result is True
        assert meta['title'] == '我的中文標題'
        assert meta['original_title'] == 'SITE-TITLE-PLACEHOLDER'
