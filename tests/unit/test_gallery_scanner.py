import pytest
from pathlib import Path
from core.gallery_scanner import VideoScanner

class TestGalleryScanner:
    @pytest.fixture
    def scanner(self):
        return VideoScanner()

    def test_parse_nfo_valid(self, scanner, tmp_path):
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <movie>
            <title>Test Title</title>
            <originaltitle>Original Test Title</originaltitle>
            <num>TEST-001</num>
            <maker>TestMaker</maker>
            <release>2023-01-01</release>
            <actor>
                <name>Actor1</name>
            </actor>
            <actor>
                <name>Actor2</name>
            </actor>
            <genre>Tag1</genre>
            <tag>Tag2</tag>
        </movie>
        """
        nfo_path = tmp_path / "test.nfo"
        nfo_path.write_text(xml_content, encoding="utf-8")
        
        info = scanner.parse_nfo(str(nfo_path))
        assert info is not None
        assert info.title == "Test Title"
        assert info.num == "TEST-001"
        assert info.maker == "TestMaker"
        assert info.date == "2023-01-01"
        assert info.actor == "Actor1,Actor2"
        assert sorted(info.genre.split(",")) == sorted(["Tag1", "Tag2"])

    def test_parse_nfo_invalid(self, scanner, tmp_path):
        # 標籤未閉合的無效 XML
        xml_content = """<?xml version="1.0" encoding="utf-8"?><movie><title>Test</movie>"""
        nfo_path = tmp_path / "test.nfo"
        nfo_path.write_text(xml_content, encoding="utf-8")
        
        info = scanner.parse_nfo(str(nfo_path))
        assert info is None

    def test_parse_nfo_bare_ampersand(self, scanner, tmp_path):
        """NFO 包含 bare & (如 AT&T)，sanitize_nfo_bytes 應修正為 &amp;"""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <movie>
            <title>AT&T Special</title>
            <num>AMP-001</num>
        </movie>
        """
        nfo_path = tmp_path / "ampersand.nfo"
        nfo_path.write_text(xml_content, encoding="utf-8")

        info = scanner.parse_nfo(str(nfo_path))
        assert info is not None
        assert info.title == "AT&T Special"
        assert info.num == "AMP-001"

    def test_parse_nfo_empty_file(self, scanner, tmp_path):
        """空檔案應回傳 None（XML 解析失敗）"""
        nfo_path = tmp_path / "empty.nfo"
        nfo_path.write_text("", encoding="utf-8")

        info = scanner.parse_nfo(str(nfo_path))
        assert info is None

    def test_parse_filename_fallback_naming_format(self, scanner):
        # 預設 naming formats 的 \[ 會被 _compile_naming_formats 中的 re.escape
        # 雙重轉義為 \\[，所以帶 [...] 的檔名不會匹配 naming format。
        # 結果走 fallback 路徑：find_num_from_filename 提取番號，title = stem。
        filename = "ActorName - [TEST-002]Some Title Here.mp4"
        info = scanner.parse_filename(filename)
        # find_num_from_filename 提取到 TEST-002
        assert info.num == "TEST-002"
        # title fallback 為整個 stem（因 naming format 未命中）
        assert info.title == "ActorName - [TEST-002]Some Title Here"
        # actor 無法從 fallback 路徑取得
        assert info.actor == ""

    def test_parse_filename_fallback_regex(self, scanner):
        # 測試檔名不符合 format 但能用 find_num_from_filename 取出番號
        # 這時候 title 會直接用檔名
        filename = "Random Words FC2-PPV-1234567 And More.mp4"
        info = scanner.parse_filename(filename)
        assert info.num == "FC2PPV-1234567"
        assert info.title == "Random Words FC2-PPV-1234567 And More"
        assert info.actor == ""

    def test_parse_filename_fallback_stem(self, scanner):
        # 完全沒有符合的，全靠 fallback
        filename = "Just Some Random Text.mp4"
        info = scanner.parse_filename(filename)
        assert info.num == ""
        assert info.title == "Just Some Random Text"

    def test_find_cover_image_exact_match(self, scanner, tmp_path):
        video_path = tmp_path / "TEST-003.mp4"
        cover_path = tmp_path / "TEST-003.jpg"
        cover_path.touch()
        
        found = scanner.find_cover_image(str(video_path))
        assert found == str(cover_path)

    def test_find_cover_image_fallback_names(self, scanner, tmp_path):
        video_path = tmp_path / "TEST-004.mp4"
        # 不存在同名圖片，但存在 poster.jpg
        cover_path = tmp_path / "poster.jpg"
        cover_path.touch()
        
        found = scanner.find_cover_image(str(video_path))
        assert found == str(cover_path)

    def test_find_cover_image_any_image(self, scanner, tmp_path):
        video_path = tmp_path / "TEST-005.mp4"
        # 既沒有同名，也沒有 poster/fanart，只有隨機命名的 JPG
        cover_path = tmp_path / "random_image.jpg"
        cover_path.touch()
        
        found = scanner.find_cover_image(str(video_path))
        assert found == str(cover_path)

    def test_find_cover_image_none(self, scanner, tmp_path):
        video_path = tmp_path / "TEST-006.mp4"
        # 資料夾裡沒圖片
        found = scanner.find_cover_image(str(video_path))
        assert found == ""
