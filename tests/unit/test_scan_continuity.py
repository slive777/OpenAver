import pytest

from core.scan_continuity import match_renamed_videos

A = 'file:///media/a/ABF-348.mp4'
B = 'file:///media/a/ABF-348.mkv'


@pytest.mark.parametrize('olds,news,existing,expected', [
    ([A], [B], set(), [(A, B)]),
    ([A], [B], {A}, []),
    ([A], [B, 'file:///media/a/ABF-348.avi'], set(), []),
    ([A, 'file:///media/a/ABF-348.avi'], [B], set(), []),
    ([A], ['file:///media/b/ABF-348.mkv'], set(), []),
    (['file:///media/a/ABF-348-cd1.mp4', 'file:///media/a/ABF-348-cd2.mp4'],
     ['file:///media/a/ABF-348-cd1.mkv', 'file:///media/a/ABF-348-cd2.mkv'], set(),
     [('file:///media/a/ABF-348-cd1.mp4', 'file:///media/a/ABF-348-cd1.mkv'),
      ('file:///media/a/ABF-348-cd2.mp4', 'file:///media/a/ABF-348-cd2.mkv')]),
    ([A], ['file:///media/a/ABF-348-C.mkv'], set(), []),
    ([A], ['file:///media/a/abf-348.mkv'], set(), []),
])
def test_match_renamed_videos_table(olds, news, existing, expected):
    assert match_renamed_videos(olds, news, lambda p: p in existing) == expected
