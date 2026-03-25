"""test_models.py - Video model 新欄位 + merge policy 測試"""
import pytest
from core.scrapers.models import Video, Actress


# ============ 新欄位預設值 ============

def test_video_new_fields_defaults():
    """新欄位預設值正確"""
    v = Video(number='TEST-001')
    assert v.director == ""
    assert v.duration is None
    assert v.label == ""
    assert v.series == ""
    assert v.sample_images == []


def test_video_new_fields_with_values():
    """新欄位可正確設定"""
    v = Video(
        number='TEST-001',
        director='山田',
        duration=119,
        label='S1',
        series='NTR',
        sample_images=['http://a.jpg'],
    )
    assert v.director == '山田'
    assert v.duration == 119
    assert v.label == 'S1'
    assert v.series == 'NTR'
    assert v.sample_images == ['http://a.jpg']


def test_to_legacy_dict_new_keys():
    """to_legacy_dict() 包含新 key"""
    v = Video(
        number='TEST-001',
        director='山田',
        duration=119,
        label='S1',
        series='NTR',
        sample_images=['http://a.jpg'],
    )
    d = v.to_legacy_dict()
    assert d['director'] == '山田'
    assert d['duration'] == 119
    assert d['label'] == 'S1'
    assert d['series'] == 'NTR'
    assert d['sample_images'] == ['http://a.jpg']


def test_to_legacy_dict_new_keys_defaults():
    """to_legacy_dict() 預設值正確"""
    v = Video(number='TEST-001')
    d = v.to_legacy_dict()
    assert d['director'] == ""
    assert d['duration'] is None
    assert d['label'] == ""
    assert d['series'] == ""
    assert d['sample_images'] == []


# ============ Merge policy 測試 ============

def _make_video(**kwargs) -> Video:
    return Video(number='TEST-001', **kwargs)


def _run_merge(main: Video, backup: Video) -> Video:
    """模擬 scraper.py 中的 merge 邏輯（單輪）"""
    updates = {}
    if not main.title and backup.title:
        updates['title'] = backup.title
    if not main.maker and backup.maker:
        updates['maker'] = backup.maker
    if not main.date and backup.date:
        updates['date'] = backup.date
    if not main.actresses and backup.actresses:
        updates['actresses'] = backup.actresses
    if not main.cover_url and backup.cover_url:
        updates['cover_url'] = backup.cover_url
    if not main.tags and backup.tags:
        updates['tags'] = backup.tags
    # 新欄位 merge
    if not main.director and backup.director:
        updates['director'] = backup.director
    if main.duration is None and backup.duration is not None:
        updates['duration'] = backup.duration
    if not main.label and backup.label:
        updates['label'] = backup.label
    if not main.series and backup.series:
        updates['series'] = backup.series
    if not main.sample_images and backup.sample_images:
        updates['sample_images'] = backup.sample_images
    if updates:
        return main.model_copy(update=updates)
    return main


def test_merge_str_fields_filled_from_backup():
    """str 欄位空值被 backup 補全"""
    main = _make_video()
    backup = _make_video(director='山田', label='S1', series='NTR')
    result = _run_merge(main, backup)
    assert result.director == '山田'
    assert result.label == 'S1'
    assert result.series == 'NTR'


def test_merge_duration_none_filled_from_backup():
    """duration=None 被 backup 補全"""
    main = _make_video()
    backup = _make_video(duration=90)
    result = _run_merge(main, backup)
    assert result.duration == 90


def test_merge_duration_zero_not_overwritten():
    """duration=0 不被 backup 覆蓋（0 是合法值，不用 is None 以外的判斷）"""
    main = _make_video(duration=0)
    backup = _make_video(duration=120)
    result = _run_merge(main, backup)
    assert result.duration == 0


def test_merge_main_has_value_not_overwritten():
    """main 已有值時不被 backup 覆蓋"""
    main = _make_video(director='田中', label='Premium', series='Existing')
    backup = _make_video(director='山田', label='S1', series='NTR')
    result = _run_merge(main, backup)
    assert result.director == '田中'
    assert result.label == 'Premium'
    assert result.series == 'Existing'


def test_merge_sample_images_empty_list_filled():
    """sample_images 空 list 被 backup 補全"""
    main = _make_video()
    backup = _make_video(sample_images=['http://a.jpg', 'http://b.jpg'])
    result = _run_merge(main, backup)
    assert result.sample_images == ['http://a.jpg', 'http://b.jpg']


def test_merge_sample_images_main_has_value_not_overwritten():
    """main 有 sample_images 時不被覆蓋"""
    main = _make_video(sample_images=['http://main.jpg'])
    backup = _make_video(sample_images=['http://backup.jpg'])
    result = _run_merge(main, backup)
    assert result.sample_images == ['http://main.jpg']


def test_merge_series_none_backup_supplements():
    """series 空值被 backup 補全"""
    main = _make_video(series='')
    backup = _make_video(series='NTR系列')
    result = _run_merge(main, backup)
    assert result.series == 'NTR系列'


def test_model_frozen_still_enforced():
    """frozen=True 仍然生效（直接賦值應拋例外）"""
    v = _make_video(director='山田')
    with pytest.raises(Exception):
        v.director = '田中'
