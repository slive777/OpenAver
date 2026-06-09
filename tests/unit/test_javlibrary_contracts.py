"""
tests/unit/test_javlibrary_contracts.py — T3 javlibrary 來源系統 contract 守衛

驗證 javlibrary 加入 source 系統各處的契約：
  - validate_source_id 放行
  - CENSORED_SOURCES 包含（不觸發 L77 warning）
  - SOURCE_ORDER 不含（不污染 fan-out）
  - FUZZY_SEARCH_SOURCES 不含（exact-only）
  - get_manual_only_sources() 回傳正確屬性
  - JavLibraryScraper importable + in __all__
  - get_enabled_source_ids 不含 javlibrary（manual_only=True 被過濾）
"""
import json
import logging

import pytest


# 1. validate_source_id 放行
def test_validate_source_id_javlibrary():
    from core.source_config import validate_source_id
    assert validate_source_id('javlibrary') is True


# 2. CENSORED_SOURCES 包含 javlibrary（is_censored 無 warning）
def test_javlibrary_in_censored_sources():
    from core.scrapers.utils import CENSORED_SOURCES
    assert 'javlibrary' in CENSORED_SOURCES


# 3. 不在 SOURCE_ORDER（不污染 fan-out）
def test_javlibrary_not_in_source_order():
    from core.scrapers.utils import SOURCE_ORDER
    assert 'javlibrary' not in SOURCE_ORDER


# 4. 不在 FUZZY_SEARCH_SOURCES（exact-only）
def test_javlibrary_not_in_fuzzy_search_sources():
    from core.scrapers.utils import FUZZY_SEARCH_SOURCES
    assert 'javlibrary' not in FUZZY_SEARCH_SOURCES


# 5. get_manual_only_sources() 回傳 javlibrary，屬性正確
def test_get_manual_only_sources():
    from core.source_config import get_manual_only_sources
    sources = get_manual_only_sources()
    assert len(sources) >= 1
    jl = next(s for s in sources if s.id == 'javlibrary')
    assert jl.manual_only is True
    assert jl.is_beta is True
    assert jl.enabled is False
    assert jl.type == 'builtin'
    assert jl.order == 99


# 6. is_censored 計算正確（builtin 分支命中 CENSORED_SOURCES，不觸發 warning）
def test_javlibrary_is_censored_no_warning(caplog):
    from core.source_config import get_manual_only_sources
    with caplog.at_level(logging.WARNING, logger='core.source_config'):
        sources = get_manual_only_sources()
    jl = next(s for s in sources if s.id == 'javlibrary')
    assert jl.is_censored is True
    assert 'javlibrary' not in caplog.text  # 不觸發 L77 warning


# 7. JavLibraryScraper 可從 __init__.py import
def test_javlibrary_scraper_importable():
    from core.scrapers import JavLibraryScraper
    assert JavLibraryScraper is not None


# 8. JavLibraryScraper 在 __all__
def test_javlibrary_scraper_in_all():
    import core.scrapers
    assert 'JavLibraryScraper' in core.scrapers.__all__


# 9. get_enabled_source_ids 不含 javlibrary
#    （monkeypatch CONFIG_PATH 注入含 javlibrary enabled=True 的 config）
def test_get_enabled_source_ids_excludes_javlibrary(tmp_path, monkeypatch):
    import core.config as core_config
    from core.source_config import get_manual_only_sources
    from core.source_settings import get_enabled_source_ids

    # 構造含 javlibrary 的 config（即使 enabled=True，manual_only=True 應被過濾）
    sources = [
        {"id": "javbus", "type": "builtin", "display_name_key": "JavBus", "display_name_raw": "",
         "enabled": True, "order": 1, "config": {}, "is_beta": False, "manual_only": False},
        {**get_manual_only_sources()[0].model_dump(), "enabled": True},  # javlibrary enabled=True 仍被過濾
    ]
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"sources": sources}))
    monkeypatch.setattr(core_config, "CONFIG_PATH", config_file)

    result = get_enabled_source_ids()
    assert 'javlibrary' not in result
    assert 'javbus' in result
