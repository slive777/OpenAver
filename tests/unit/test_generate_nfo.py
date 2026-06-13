"""
tests/unit/test_generate_nfo.py
TASK-72b-T3：generate_nfo external_manager 參數 + F3 欄位 + poster/fanart 模式切換

TDD-lite：先跑 RED（實作前這些測試應全部 FAIL），實作後應全部 GREEN。
"""
import xml.etree.ElementTree as ET
import pytest
from core.organizer import generate_nfo


def _read_nfo(tmp_path, **kwargs) -> str:
    """輔助：呼叫 generate_nfo，回傳 NFO 字串。"""
    nfo_path = tmp_path / "ABC-123.nfo"
    defaults = dict(
        number="ABC-123",
        title="Test Title",
        output_path=str(nfo_path),
    )
    defaults.update(kwargs)
    result = generate_nfo(**defaults)
    assert result is True, "generate_nfo 應回傳 True"
    return nfo_path.read_text(encoding="utf-8")


def _parse(nfo: str) -> ET.Element:
    """輔助：XML parse，回傳 root <movie> element。"""
    return ET.fromstring(nfo)


# ─────────────────────────────────────────────
# A. external_manager="off"（預設，回歸基線）
# ─────────────────────────────────────────────

class TestOffMode:
    """external_manager="off"（或不傳）時的行為"""

    def test_f3_fields_absent_explicit_off(self, tmp_path):
        """明確傳 external_manager='off' → 五個 F3 欄位全不存在"""
        nfo = _read_nfo(tmp_path, external_manager="off")
        assert "<lockdata>" not in nfo
        assert 'uniqueid type="num"' not in nfo and 'uniqueid type=\'num\'' not in nfo
        assert "<sorttitle>" not in nfo
        assert "<country>" not in nfo
        assert "<language>" not in nfo

    def test_f3_fields_absent_default(self, tmp_path):
        """不傳 external_manager（預設值 off）→ F3 欄位全不存在（向後相容）"""
        nfo = _read_nfo(tmp_path)  # 不傳 external_manager
        assert "<lockdata>" not in nfo
        assert "<sorttitle>" not in nfo
        assert "<country>" not in nfo
        assert "<language>" not in nfo

    def test_poster_stem_no_suffix_off(self, tmp_path):
        """off + has_poster=False → <poster>{stem}.jpg"""
        nfo = _read_nfo(tmp_path, has_poster=False, external_manager="off")
        assert "<poster>ABC-123.jpg</poster>" in nfo

    def test_poster_stem_with_suffix_off(self, tmp_path):
        """off + has_poster=True → <poster>{stem}-poster.jpg"""
        nfo = _read_nfo(tmp_path, has_poster=True, external_manager="off")
        assert "<poster>ABC-123-poster.jpg</poster>" in nfo

    def test_fanart_stem_no_suffix_off(self, tmp_path):
        """off + has_fanart=False → <fanart>{stem}.jpg"""
        nfo = _read_nfo(tmp_path, has_fanart=False, external_manager="off")
        assert "<fanart>ABC-123.jpg</fanart>" in nfo

    def test_fanart_stem_with_suffix_off(self, tmp_path):
        """off + has_fanart=True → <fanart>{stem}-fanart.jpg"""
        nfo = _read_nfo(tmp_path, has_fanart=True, external_manager="off")
        assert "<fanart>ABC-123-fanart.jpg</fanart>" in nfo

    def test_thumb_always_stem_off(self, tmp_path):
        """off 模式：<thumb> 永遠是 {stem}.jpg（CD-12）"""
        nfo = _read_nfo(tmp_path, external_manager="off")
        assert "<thumb>ABC-123.jpg</thumb>" in nfo


# ─────────────────────────────────────────────
# B. external_manager="jellyfin"
# ─────────────────────────────────────────────

class TestJellyfinMode:
    """external_manager="jellyfin" 時的行為"""

    def test_f3_all_five_fields_present(self, tmp_path):
        """jellyfin → 五個 F3 欄位全部存在"""
        nfo = _read_nfo(tmp_path, external_manager="jellyfin")
        assert "<lockdata>true</lockdata>" in nfo
        assert "<country>Japan</country>" in nfo
        assert "<language>ja</language>" in nfo
        assert "<sorttitle>" in nfo
        # uniqueid type="num" 存在
        assert 'type="num"' in nfo or "type='num'" in nfo

    def test_uniqueid_num_has_both_attrs(self, tmp_path):
        """jellyfin → <uniqueid type="num" default="true"> 同時帶兩個 attribute"""
        nfo = _read_nfo(tmp_path, number="SONE-205", title="Foo", external_manager="jellyfin")
        root = _parse(nfo)
        uid_elements = root.findall("uniqueid")
        num_uid = [el for el in uid_elements if el.get("type") == "num"]
        assert len(num_uid) >= 1, "應有 type='num' 的 uniqueid element"
        assert num_uid[0].get("default") == "true", \
            "<uniqueid type='num'> 必須同時帶 default='true'"

    def test_two_default_true_uniqueids(self, tmp_path):
        """jellyfin → home + num 兩個 default="true" uniqueid 並存（雙 default 故意保留）"""
        nfo = _read_nfo(tmp_path, external_manager="jellyfin")
        assert nfo.count('default="true"') >= 2, \
            "NFO 應同時有 home 與 num 兩個 default='true' uniqueid"

    def test_sorttitle_is_display_title(self, tmp_path):
        """jellyfin → <sorttitle> = [number]title，不是 bare number"""
        nfo = _read_nfo(tmp_path, number="ABC-123", title="My Movie",
                        external_manager="jellyfin")
        assert "<sorttitle>[ABC-123]My Movie</sorttitle>" in nfo
        # 確認不是 bare number
        assert "<sorttitle>ABC-123</sorttitle>" not in nfo

    def test_country_and_language_jellyfin(self, tmp_path):
        """jellyfin → country=Japan, language=ja"""
        nfo = _read_nfo(tmp_path, external_manager="jellyfin")
        root = _parse(nfo)
        assert root.findtext("country") == "Japan"
        assert root.findtext("language") == "ja"

    def test_poster_fanart_stem_form_jellyfin(self, tmp_path):
        """jellyfin → poster/fanart 維持 stem 形式（與 off 相同）"""
        nfo = _read_nfo(tmp_path, has_poster=True, has_fanart=True,
                        external_manager="jellyfin")
        assert "<poster>ABC-123-poster.jpg</poster>" in nfo
        assert "<fanart>ABC-123-fanart.jpg</fanart>" in nfo

    def test_thumb_always_stem_jellyfin(self, tmp_path):
        """jellyfin → <thumb> 仍是 {stem}.jpg（CD-12）"""
        nfo = _read_nfo(tmp_path, external_manager="jellyfin")
        assert "<thumb>ABC-123.jpg</thumb>" in nfo

    def test_f3_before_home_uniqueid(self, tmp_path):
        """jellyfin → F3 欄位在 <uniqueid type="home"> 之前"""
        nfo = _read_nfo(tmp_path, external_manager="jellyfin")
        lockdata_pos = nfo.find("<lockdata>")
        home_uid_pos = nfo.find('type="home"')
        assert lockdata_pos < home_uid_pos, \
            "F3 lockdata 應在 <uniqueid type='home'> 之前"


# ─────────────────────────────────────────────
# C. external_manager="kodi"（與 jellyfin 相同：stem 長格式）
# ─────────────────────────────────────────────

class TestKodiMode:
    """external_manager="kodi" 時的行為：與 jellyfin 完全相同（stem 長格式）"""

    def test_f3_all_five_fields_present_kodi(self, tmp_path):
        """kodi → 五個 F3 欄位全部存在（與 jellyfin 相同的 F3 區塊）"""
        nfo = _read_nfo(tmp_path, external_manager="kodi")
        assert "<lockdata>true</lockdata>" in nfo
        assert "<country>Japan</country>" in nfo
        assert "<language>ja</language>" in nfo
        assert "<sorttitle>" in nfo
        assert 'type="num"' in nfo or "type='num'" in nfo

    def test_poster_stem_naming_has_poster_true(self, tmp_path):
        """kodi + has_poster=True → <poster>ABC-123-poster.jpg</poster>（stem 長格式）"""
        nfo = _read_nfo(tmp_path, has_poster=True, external_manager="kodi")
        assert "<poster>ABC-123-poster.jpg</poster>" in nfo
        # 確認不出現裸短名
        assert "<poster>poster.jpg</poster>" not in nfo

    def test_poster_no_suffix_has_poster_false(self, tmp_path):
        """kodi + has_poster=False → <poster>ABC-123.jpg</poster>（無 -poster 後綴）"""
        nfo = _read_nfo(tmp_path, has_poster=False, external_manager="kodi")
        assert "<poster>ABC-123.jpg</poster>" in nfo
        assert "<poster>poster.jpg</poster>" not in nfo

    def test_fanart_stem_naming_has_fanart_true(self, tmp_path):
        """kodi + has_fanart=True → <fanart>ABC-123-fanart.jpg</fanart>（stem 長格式）"""
        nfo = _read_nfo(tmp_path, has_fanart=True, external_manager="kodi")
        assert "<fanart>ABC-123-fanart.jpg</fanart>" in nfo
        assert "<fanart>fanart.jpg</fanart>" not in nfo

    def test_fanart_no_suffix_has_fanart_false(self, tmp_path):
        """kodi + has_fanart=False → <fanart>ABC-123.jpg</fanart>"""
        nfo = _read_nfo(tmp_path, has_fanart=False, external_manager="kodi")
        assert "<fanart>ABC-123.jpg</fanart>" in nfo
        assert "<fanart>fanart.jpg</fanart>" not in nfo

    def test_thumb_still_stem_kodi(self, tmp_path):
        """kodi → <thumb> 仍是 {stem}.jpg（CD-12）"""
        nfo = _read_nfo(tmp_path, external_manager="kodi")
        assert "<thumb>ABC-123.jpg</thumb>" in nfo

    def test_kodi_sorttitle_is_display_title(self, tmp_path):
        """kodi → <sorttitle> = [number]title"""
        nfo = _read_nfo(tmp_path, number="MIDE-001", title="Kodi Film",
                        external_manager="kodi")
        assert "<sorttitle>[MIDE-001]Kodi Film</sorttitle>" in nfo

    def test_kodi_equals_jellyfin_stem_tags(self, tmp_path):
        """kodi tag == jellyfin tag — 直接等價斷言（兩者 poster/fanart 行為相同）"""
        kodi_nfo = _read_nfo(tmp_path, has_poster=True, has_fanart=True,
                             external_manager="kodi")
        jf_nfo = _read_nfo(tmp_path, has_poster=True, has_fanart=True,
                           external_manager="jellyfin")
        # 找出 poster/fanart 行
        import re
        kodi_poster = re.search(r'<poster>(.*?)</poster>', kodi_nfo)
        jf_poster = re.search(r'<poster>(.*?)</poster>', jf_nfo)
        kodi_fanart = re.search(r'<fanart>(.*?)</fanart>', kodi_nfo)
        jf_fanart = re.search(r'<fanart>(.*?)</fanart>', jf_nfo)
        assert kodi_poster and jf_poster
        assert kodi_poster.group(1) == jf_poster.group(1), \
            f"kodi poster tag 應與 jellyfin 相同: {kodi_poster.group(1)!r} != {jf_poster.group(1)!r}"
        assert kodi_fanart and jf_fanart
        assert kodi_fanart.group(1) == jf_fanart.group(1), \
            f"kodi fanart tag 應與 jellyfin 相同: {kodi_fanart.group(1)!r} != {jf_fanart.group(1)!r}"


# ─────────────────────────────────────────────
# D. external_manager="emby"（等價 jellyfin）
# ─────────────────────────────────────────────

class TestEmbyMode:
    """external_manager="emby" 時的行為：與 jellyfin 完全相同（stem 長格式）"""

    def test_emby_f3_fields_present(self, tmp_path):
        """emby → 五個 F3 欄位全部存在（等價 jellyfin）"""
        nfo = _read_nfo(tmp_path, external_manager="emby")
        assert "<lockdata>true</lockdata>" in nfo
        assert "<country>Japan</country>" in nfo
        assert "<language>ja</language>" in nfo
        assert "<sorttitle>" in nfo
        assert 'type="num"' in nfo or "type='num'" in nfo


# ─────────────────────────────────────────────
# E. off/jellyfin 回歸
# ─────────────────────────────────────────────

class TestOffJellyfinRegression:
    """off / jellyfin 回歸：stem tag 行為不變"""

    def test_off_stem_tag_with_poster(self, tmp_path):
        """off + has_poster=True → stem tag（byte-identical）"""
        nfo = _read_nfo(tmp_path, has_poster=True, has_fanart=True, external_manager="off")
        assert "<poster>ABC-123-poster.jpg</poster>" in nfo
        assert "<fanart>ABC-123-fanart.jpg</fanart>" in nfo

    def test_jellyfin_stem_tag_with_poster(self, tmp_path):
        """jellyfin + has_poster=True → stem tag（byte-identical）"""
        nfo = _read_nfo(tmp_path, has_poster=True, has_fanart=True, external_manager="jellyfin")
        assert "<poster>ABC-123-poster.jpg</poster>" in nfo
        assert "<fanart>ABC-123-fanart.jpg</fanart>" in nfo

    def test_off_thumb_unchanged(self, tmp_path):
        """off → <thumb> 仍是 {stem}.jpg"""
        nfo = _read_nfo(tmp_path, external_manager="off")
        assert "<thumb>ABC-123.jpg</thumb>" in nfo


# ─────────────────────────────────────────────
# D. html.escape（跨模式）
# ─────────────────────────────────────────────

class TestHtmlEscape:
    """特殊字元在 F3 欄位中正確 escape"""

    def test_number_with_special_chars_escaped_in_num_uid(self, tmp_path):
        """number 含 & 和 < → uniqueid type=num 內容正確 escape"""
        nfo = _read_nfo(tmp_path, number="A&B<1", title="Normal Title",
                        external_manager="jellyfin")
        # 應出現 escaped 形式
        assert "A&amp;B&lt;1" in nfo
        # 不應出現 bare 特殊字元（在 XML tag context 內）
        # 用 parse 驗證 uniqueid type=num 的 text
        root = _parse(nfo)
        num_uid = [el for el in root.findall("uniqueid") if el.get("type") == "num"]
        assert len(num_uid) >= 1
        assert num_uid[0].text == "A&B<1"  # ET 自動 unescape

    def test_title_with_special_chars_escaped_in_sorttitle(self, tmp_path):
        """title 含 & 和 < → <sorttitle> 內容正確 escape"""
        nfo = _read_nfo(tmp_path, number="ABC-123", title="T&<x",
                        external_manager="jellyfin")
        # sorttitle 應是 [ABC-123]T&amp;&lt;x
        assert "&amp;" in nfo
        assert "&lt;" in nfo
        # 用 parse 驗證 text value
        root = _parse(nfo)
        sorttitle = root.findtext("sorttitle")
        assert sorttitle == "[ABC-123]T&<x"  # ET 自動 unescape

    def test_no_bare_special_chars_in_num_uid(self, tmp_path):
        """number 含特殊字元 → NFO 文字中不出現 bare A&B<1"""
        nfo = _read_nfo(tmp_path, number="A&B<1", title="Normal",
                        external_manager="jellyfin")
        # 在 XML tag 內不應有未 escape 的 & 或 <
        # 整份 NFO 應可 XML parse 成功（不丟 ParseError）
        _parse(nfo)  # 若有 bare & 或 < 會丟 ET.ParseError
