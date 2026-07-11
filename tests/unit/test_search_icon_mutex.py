"""T5: Search 搜尋列 icon 互斥守衛"""
from pathlib import Path


class TestSearchIconMutex:

    def _read_search_html(self):
        return Path("web/templates/search.html").read_text()

    # [lint-guard: migrate→96b] isComposing HTML 半邊待 96b 承接
    # （CSS 半邊 test_btn_icon_has_flex_shrink 已遷 css-guard CG-SB-03）
    def test_grid_toggle_has_is_composing_guard(self):
        """Grid toggle x-show 必須含 !isComposing() 條件"""
        content = self._read_search_html()
        assert "isComposing()" in content
        # x-show 同一行需含 actress/prefix 和 isComposing
        lines = content.split('\n')
        matching = [l for l in lines if 'isComposing' in l and ('actress' in l or 'prefix' in l)]
        assert matching, "Grid toggle x-show 須同時含 actress/prefix 和 isComposing"
