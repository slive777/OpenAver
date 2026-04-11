"""
Unit tests for core.scrapers.actress.graphis._parse_graphis_profile

Coverage:
  - T7.3 bug: hobby JP+EN 混串（DOM <br> 被 flatten 吞掉分隔）
  - Regression guard: age/height/BWH/cup 不受 hobby fix 影響
  - name_en breadcrumb parse
  - 單段 hobby（無 <br>）/ 無 hobby row 邊界
"""

from core.scrapers.actress.graphis import _parse_graphis_profile


# ---------------------------------------------------------------------------
# Fixture: full profile HTML with <br>-separated JP/EN hobby (T7.3 bug case)
# ---------------------------------------------------------------------------

HTML_HOBBY_BR = '''
<html><body>
<p class="pan-link">TOP &gt; Models &gt; 明里つむぎ/Tsumugi Akari</p>
<li class="model-prof">
  <ul>
    <li><span>年齢 /age:</span><span>26</span></li>
    <li><span>身長 /height:</span><span>155cm</span></li>
    <li><span>スリーサイズ /BWH:</span><span>B80(B) W58 H83</span></li>
    <li><span>趣味 /hobby:</span><span>ネットサーフィン、アイドル研究、美容<br> Surfing the net,Idol research,Beauty</span></li>
  </ul>
</li>
</body></html>
'''


# ---------------------------------------------------------------------------
# 1. Bug fix: hobby 純 JP 化（strip EN）
# ---------------------------------------------------------------------------

def test_hobby_pure_jp_strips_en():
    """T7.3 bug fix: hobby should be pure JP, EN suffix stripped."""
    result = _parse_graphis_profile(HTML_HOBBY_BR)
    assert result['hobby'] == 'ネットサーフィン、アイドル研究、美容', (
        f"expected pure JP hobby, got {result['hobby']!r}"
    )
    assert 'Surfing' not in result['hobby']
    assert 'Beauty' not in result['hobby']


def test_hobby_single_segment_no_br():
    """單段 hobby（無 <br>）— parser 仍正確抓取單段文字。"""
    html = '''
    <html><body>
    <li class="model-prof"><ul>
      <li><span>趣味 /hobby:</span><span>読書</span></li>
    </ul></li>
    </body></html>
    '''
    result = _parse_graphis_profile(html)
    assert result['hobby'] == '読書'


def test_hobby_empty_when_no_row():
    """無 hobby row → result['hobby'] == '' (預設值不動)"""
    html = '''
    <html><body>
    <li class="model-prof"><ul>
      <li><span>年齢 /age:</span><span>26</span></li>
    </ul></li>
    </body></html>
    '''
    result = _parse_graphis_profile(html)
    assert result['hobby'] == ''


# ---------------------------------------------------------------------------
# 2. Regression guard: age / height / BWH / cup 不受 hobby fix 影響
# ---------------------------------------------------------------------------

def test_age_height_bwh_not_affected_by_hobby_fix():
    """其他欄位的 regex 只取數字，不受 <br> flatten 或 hobby 分支改動影響。"""
    result = _parse_graphis_profile(HTML_HOBBY_BR)
    assert result['age'] == 26
    assert result['height'] == '155cm'
    assert result['bust'] == '80cm'
    assert result['cup'] == 'B'
    assert result['waist'] == '58cm'
    assert result['hip'] == '83cm'


# ---------------------------------------------------------------------------
# 3. name_en breadcrumb 仍正確
# ---------------------------------------------------------------------------

def test_name_en_from_breadcrumb():
    """p.pan-link 的 breadcrumb 解析不受 hobby fix 影響。"""
    result = _parse_graphis_profile(HTML_HOBBY_BR)
    assert result['name_en'] == 'Tsumugi Akari'
