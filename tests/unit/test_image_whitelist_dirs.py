"""
test_image_whitelist_dirs.py — `_image_whitelist_dirs` 純函式候選目錄推導測試（TASK-88c-T1）

驗證 `/api/gallery/image` 白名單「候選 raw 目錄清單」的推導真值：
- 每來源的 `src.path` 進候選
- 非空 `src.output_path` 進候選
- `""` output_path **不**進候選（防 `to_file_uri('') = 'file:///'` 根路徑 bypass 哨兵）
- 多來源聚合、空 config 不拋

純函式、無 IO、免 HTTP、免 mock。
"""

from web.routers.scanner import _image_whitelist_dirs


class TestImageWhitelistDirs:
    def test_output_path_included_alongside_src_path(self):
        """readonly 來源含非空 output_path → 候選同時含 path 與 output_path"""
        gallery_config = {
            'directories': [
                {'path': '/src/movies', 'readonly': True, 'output_path': '/out/movies'},
            ],
        }
        dirs = _image_whitelist_dirs(gallery_config)
        assert '/src/movies' in dirs
        assert '/out/movies' in dirs

    def test_empty_output_path_excluded(self):
        """output_path == "" → 候選只含 path，不含 ""（防 file:/// bypass 哨兵）

        若把 `if src.output_path` 過濾拿掉，"" 會進候選 → 此測試 RED。
        """
        gallery_config = {
            'directories': [
                {'path': '/src/movies', 'readonly': False, 'output_path': ''},
            ],
        }
        dirs = _image_whitelist_dirs(gallery_config)
        assert '/src/movies' in dirs
        assert '' not in dirs

    def test_multi_source_aggregation(self):
        """多來源混合（一有 output_path、一沒有）→ 正確聚合"""
        gallery_config = {
            'directories': [
                {'path': '/a', 'readonly': True, 'output_path': '/a-out'},
                {'path': '/b', 'readonly': False, 'output_path': ''},
            ],
        }
        dirs = _image_whitelist_dirs(gallery_config)
        assert set(dirs) == {'/a', '/a-out', '/b'}

    def test_empty_config_returns_empty_list(self):
        """空 gallery_config / 無 directories → 空清單（不拋）"""
        assert _image_whitelist_dirs({}) == []
        assert _image_whitelist_dirs({'directories': []}) == []

    def test_bare_string_source_no_output_path(self):
        """裸字串來源（無 output_path）→ 只有 path 進候選"""
        gallery_config = {'directories': ['/plain/dir']}
        dirs = _image_whitelist_dirs(gallery_config)
        assert dirs == ['/plain/dir']
