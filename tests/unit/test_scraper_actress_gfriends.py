from unittest.mock import patch, MagicMock
from core.scrapers.actress.gfriends import _check_gfriends_url


def _make_head(ai_fix_status, original_status):
    """
    回傳 mock 函數，用於 patch `requests.head`。
    翻轉後的呼叫順序：第一次 = AI-Fix、第二次 = 原版。
    """
    responses = [
        MagicMock(status_code=ai_fix_status),
        MagicMock(status_code=original_status),
    ]
    return MagicMock(side_effect=responses)


def test_ai_fix_preferred_when_both_exist():
    """涼森れむ case: AI-Fix 與原版都存在時，回 AI-Fix URL"""
    with patch('core.scrapers.actress.gfriends.requests.head',
               _make_head(200, 200)):
        url = _check_gfriends_url('v-Prestige', '涼森れむ')
    assert url is not None
    assert 'AI-Fix-' in url


def test_fallback_to_original_when_ai_fix_404():
    """4/5 baseline case: AI-Fix 404 時 fallback 原版"""
    with patch('core.scrapers.actress.gfriends.requests.head',
               _make_head(404, 200)):
        url = _check_gfriends_url('8-Ideapocket', '明里つむぎ')
    assert url is not None
    assert 'AI-Fix-' not in url


def test_both_404_returns_none():
    """兩者都 404 → None"""
    with patch('core.scrapers.actress.gfriends.requests.head',
               _make_head(404, 404)):
        assert _check_gfriends_url('xxx', 'yyy') is None


def test_exception_returns_none():
    """網路 exception → None（fail-open）"""
    with patch('core.scrapers.actress.gfriends.requests.head',
               side_effect=Exception('network')):
        assert _check_gfriends_url('xxx', 'yyy') is None


def test_ai_fix_exception_falls_back_to_original():
    """
    Codex review #1 (T7.1 regression fix):
    AI-Fix HEAD 拋 exception 時，應該 fallback 原版，而非整個回 None。
    舊外層 try/except 會讓 AI-Fix exception 直接 abort 整個函數。
    """
    import requests as req_module

    call_count = {'n': 0}

    def mock_head(url, **kwargs):
        call_count['n'] += 1
        if call_count['n'] == 1:
            # AI-Fix probe — raise exception
            raise req_module.exceptions.Timeout("flaky network")
        else:
            # Original probe — success
            return MagicMock(status_code=200)

    with patch('core.scrapers.actress.gfriends.requests.head', side_effect=mock_head):
        url = _check_gfriends_url('8-Ideapocket', '明里つむぎ')

    assert url is not None, "expected fallback to original after AI-Fix exception"
    assert 'AI-Fix-' not in url, f"expected original URL, got {url!r}"
    assert call_count['n'] == 2, f"expected 2 HEAD calls, got {call_count['n']}"
