"""T5: Search 搜尋列 icon 互斥守衛"""
from pathlib import Path


class TestSearchIconMutex:

    def _read_search_html(self):
        return Path("web/templates/search.html").read_text()

    def _read_search_css(self):
        return Path("web/static/css/pages/search.css").read_text()

    def test_grid_toggle_has_is_composing_guard(self):
        """Grid toggle x-show 必須含 !isComposing() 條件"""
        content = self._read_search_html()
        assert "isComposing()" in content
        # x-show 同一行需含 actress/prefix 和 isComposing
        lines = content.split('\n')
        matching = [l for l in lines if 'isComposing' in l and ('actress' in l or 'prefix' in l)]
        assert matching, "Grid toggle x-show 須同時含 actress/prefix 和 isComposing"

    def test_btn_icon_has_flex_shrink(self):
        """.spotlight-search .btn-icon 必須有 flex-shrink: 0"""
        content = self._read_search_css()
        # Must have a .spotlight-search .btn-icon block with flex-shrink
        lines = content.split('\n')
        in_block = False
        found = False
        for line in lines:
            if '.spotlight-search .btn-icon' in line:
                in_block = True
            if in_block and '}' in line:
                in_block = False
            if in_block and 'flex-shrink' in line:
                found = True
                break
        assert found, ".spotlight-search .btn-icon 區塊須含 flex-shrink: 0"
