"""
前端遷移守衛測試 — 確保 Alpine 遷移過程不引入反模式

這些測試建立 baseline（V0），在後續 V1-V5 修復過程中逐步消除違規，
最終達到全部通過。
"""

import pytest
from pathlib import Path
from typing import List, Tuple
import re

# 專案根目錄
PROJECT_ROOT = Path(__file__).parent.parent

# Vanilla inline event handlers (禁止)
# (?i) case-insensitive; (?<=\s) 前方需為空白，避免誤抓 data-onclick / x-onclick
VANILLA_HANDLER_PATTERN = r'(?i)(?<=\s)on(?:click|change|submit|keydown|input)\s*=\s*["\']'


def find_pattern_in_file(file_path: Path, regex: str,
                         exclude_lines: callable = None) -> List[Tuple[int, str]]:
    """
    在檔案中尋找符合 regex 的行

    Args:
        file_path: 檔案路徑
        regex: 正則表達式 pattern
        exclude_lines: 排除規則函數，接收 (line, line_number) 回傳 True 表示排除

    Returns:
        List of (line_number, line_content) tuples
    """
    violations = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                if re.search(regex, line):
                    # 套用排除規則
                    if exclude_lines and exclude_lines(line, i):
                        continue
                    violations.append((i, line.rstrip()))
    except Exception as e:
        pytest.fail(f"無法讀取檔案 {file_path}: {e}")

    return violations


class TestNoVanillaHandlers:
    """確認所有 template 無 inline vanilla event handler"""

    def test_no_vanilla_handlers(self):
        """掃描所有 HTML template，確認無 onclick/onchange 等 inline handler"""
        templates_dir = PROJECT_ROOT / "web" / "templates"
        violations = []

        # 掃描主目錄 HTML 檔案（排除 design_system 子目錄）
        html_files = [f for f in templates_dir.glob("*.html")]

        for html_file in html_files:
            matches = find_pattern_in_file(
                html_file, VANILLA_HANDLER_PATTERN
            )
            for line_num, line_content in matches:
                violations.append(f"{html_file.name}:{line_num} — {line_content[:80]}")

        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 vanilla inline handler 違規:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )


class TestNoHardcodedColors:
    """確認 CSS/HTML 無 hardcoded hex color"""

    def is_css_variable_definition(self, line: str, line_num: int) -> bool:
        """
        檢查是否為 CSS variable 定義行 (例外)

        CRITICAL FIX: 原本的 '--' in line and ':' in line 會誤判
        像 "background: linear-gradient(135deg, var(--accent) 0%, #007aff 100%)"
        這種只是「引用」CSS variable 的行（因為包含 var(--accent)）。

        必須檢查行是否「定義」CSS variable（以 --variable: 開頭）。
        """
        # 檢查是否為 CSS variable 定義（--variable-name: value;）
        return bool(re.match(r'\s*--[\w-]+\s*:', line))

    def is_svg_data_uri(self, line: str, line_num: int) -> bool:
        """檢查是否在 SVG data-uri 中 (例外)"""
        return 'data:image/svg' in line

    def is_intentional_color(self, line: str) -> bool:
        """檢查行內是否有 lint-ignore 或 VS Code 等已知例外註解"""
        # VS Code diff 配色、或任何帶 lint-ignore 標記的行
        return bool(re.search(r'/\*.*(?:VS Code|lint-ignore).*\*/', line))

    def test_no_hardcoded_colors_in_css(self):
        """掃描 CSS 檔案，確認無 hardcoded hex color"""
        violations = []

        # 掃描 pages/*.css + theme.css
        css_dir = PROJECT_ROOT / "web" / "static" / "css"
        css_files = list((css_dir / "pages").glob("*.css")) + [css_dir / "theme.css"]

        for css_file in css_files:
            # 跳過 design-system.css (參考頁)
            if css_file.name == "design-system.css":
                continue

            matches = find_pattern_in_file(
                css_file,
                r'#[0-9a-fA-F]{3,8}',
                exclude_lines=lambda line, num: (
                    self.is_css_variable_definition(line, num) or
                    self.is_svg_data_uri(line, num) or
                    self.is_intentional_color(line)
                )
            )

            for line_num, line_content in matches:
                violations.append(
                    f"{css_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                )

        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 hardcoded hex color 違規 (CSS):\n" +
            "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_hardcoded_colors_in_html(self):
        """掃描 HTML inline styles，確認無 hardcoded hex color"""
        violations = []
        templates_dir = PROJECT_ROOT / "web" / "templates"
        html_files = [f for f in templates_dir.glob("*.html")]

        for html_file in html_files:
            # 跳過 design-system.html (參考頁)
            if html_file.name == "design-system.html":
                continue

            # 回參照確保同型引號閉合，避免 url('...') 巢狀引號漏判
            matches = find_pattern_in_file(
                html_file,
                r"""style\s*=\s*(["'])(?:(?!\1).)*#[0-9a-fA-F]{3,8}"""
            )

            for line_num, line_content in matches:
                violations.append(f"{html_file.name}:{line_num} — {line_content[:100]}")

        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 hardcoded hex color 違規 (HTML inline):\n" +
            "\n".join(f"  - {v}" for v in violations)
        )


class TestNoCreateElement:
    """確認 Alpine state mixins 不用 createElement"""

    def test_no_create_element_in_state_mixins(self):
        """掃描所有 state/*.js，確認無 document.createElement"""
        violations = []
        js_pages_dir = PROJECT_ROOT / "web" / "static" / "js" / "pages"

        # 找所有 state 子目錄
        state_dirs = [d for d in js_pages_dir.rglob("state") if d.is_dir()]

        for state_dir in state_dirs:
            js_files = state_dir.glob("*.js")

            for js_file in js_files:
                matches = find_pattern_in_file(js_file, r'document\.createElement')

                for line_num, line_content in matches:
                    violations.append(
                        f"{js_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                    )

        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 createElement 違規 (state mixins):\n" +
            "\n".join(f"  - {v}" for v in violations)
        )


class TestNoInlineStyleDisplay:
    """確認 template 不用 style='display:none' 搭配 x-show"""

    @staticmethod
    def _parse_elements(html_text: str) -> List[Tuple[int, str]]:
        """
        將 HTML 中每個開標籤（可跨行）提取為 (起始行號, 完整標籤文字) 清單。
        只處理 < ... > 範圍，不解析 CDATA / script 等。
        """
        elements = []
        # 容許屬性值內有 > (如 x-show="a > 0")：跳過引號區段再匹配 >
        tag_re = re.compile(r'<[a-zA-Z](?:[^>"\'`]|"[^"]*"|\'[^\']*\'|`[^`]*`)*>', re.DOTALL)
        # 預建行號對照表：offset → line number
        line_starts = [0]
        for i, ch in enumerate(html_text):
            if ch == '\n':
                line_starts.append(i + 1)

        def offset_to_line(offset: int) -> int:
            lo, hi = 0, len(line_starts) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if line_starts[mid] <= offset:
                    lo = mid
                else:
                    hi = mid - 1
            return lo + 1  # 1-based

        for m in tag_re.finditer(html_text):
            elements.append((offset_to_line(m.start()), m.group()))
        return elements

    def test_no_inline_style_display_with_x_show(self):
        """掃描所有 HTML，確認無 style display:none + x-show 重複（支援跨行、單/雙引號）"""
        # 回參照 \1 確保開閉引號一致，避免 url('...') 提前中斷
        display_none_re = re.compile(r"""style\s*=\s*(["'])(?:(?!\1).)*display:\s*none""")
        violations = []
        templates_dir = PROJECT_ROOT / "web" / "templates"
        html_files = list(templates_dir.rglob("*.html"))

        for html_file in html_files:
            try:
                html_text = html_file.read_text(encoding='utf-8')
            except Exception as e:
                pytest.fail(f"無法讀取 {html_file}: {e}")

            for line_num, tag_text in self._parse_elements(html_text):
                if 'x-show' in tag_text and display_none_re.search(tag_text):
                    preview = ' '.join(tag_text.split())[:100]
                    violations.append(
                        f"{html_file.relative_to(PROJECT_ROOT)}:{line_num} — {preview}"
                    )

        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 style='display:none' + x-show 重複:\n" +
            "\n".join(f"  - {v}" for v in violations) +
            "\n\n提示：應該移除 style='display:none'，改用 x-cloak 處理初始隱藏"
        )


class TestMotionInfra:
    """確認 GSAP motion 基礎設施完整"""

    def test_motion_prefs_js_exists(self):
        """motion-prefs.js 存在且包含必要 API"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "components" / "motion-prefs.js"
        assert js_file.exists(), f"motion-prefs.js 不存在: {js_file}"

        content = js_file.read_text(encoding='utf-8')
        assert 'prefersReducedMotion' in content, \
            "motion-prefs.js 缺少 prefersReducedMotion"
        assert 'openaver:motion-pref-change' in content, \
            "motion-prefs.js 缺少 openaver:motion-pref-change 事件"
        assert 'addListener' in content, \
            "motion-prefs.js 缺少 addListener 相容性 fallback"

    def test_motion_adapter_js_exists(self):
        """motion-adapter.js 存在且包含 4 個共用動畫函數 + createContext + _shouldAnimate"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "components" / "motion-adapter.js"
        assert js_file.exists(), f"motion-adapter.js 不存在: {js_file}"

        content = js_file.read_text(encoding='utf-8')
        for symbol in ('createContext', 'playEnter', 'playLeave', 'playStagger',
                        'playModal', '_shouldAnimate'):
            assert symbol in content, f"motion-adapter.js 缺少 {symbol}"

    def test_base_html_loads_gsap_and_adapters(self):
        """base.html 載入 GSAP CDN + motion-prefs + motion-adapter，且順序正確"""
        base_html = PROJECT_ROOT / "web" / "templates" / "base.html"
        assert base_html.exists(), f"base.html 不存在: {base_html}"

        content = base_html.read_text(encoding='utf-8')

        assert 'gsap.min.js' in content, "base.html 缺少 GSAP CDN script"
        assert 'motion-prefs.js' in content, "base.html 缺少 motion-prefs.js"
        assert 'motion-adapter.js' in content, "base.html 缺少 motion-adapter.js"
        assert 'alpinejs' in content, "base.html 缺少 Alpine.js"

        # 驗證載入順序：GSAP → motion-prefs → motion-adapter → Alpine
        idx_gsap = content.index('gsap.min.js')
        idx_prefs = content.index('motion-prefs.js')
        idx_adapter = content.index('motion-adapter.js')
        idx_alpine = content.index('alpinejs')

        assert idx_gsap < idx_prefs, \
            "載入順序錯誤：gsap.min.js 應在 motion-prefs.js 之前"
        assert idx_prefs < idx_adapter, \
            "載入順序錯誤：motion-prefs.js 應在 motion-adapter.js 之前"
        assert idx_adapter < idx_alpine, \
            "載入順序錯誤：motion-adapter.js 應在 alpinejs 之前"

    def test_no_direct_gsap_calls_in_pages(self):
        """頁面/元件 JS 不直接呼叫 GSAP API — 必須透過 motion adapter"""
        scan_dirs = [
            PROJECT_ROOT / "web" / "static" / "js" / "pages",
            PROJECT_ROOT / "web" / "static" / "js" / "components",
        ]
        # motion-adapter.js 本身是合法 GSAP 呼叫點
        allowed_files = {'motion-adapter.js'}
        violations = []

        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for js_file in scan_dir.rglob("*.js"):
                if js_file.name in allowed_files:
                    continue
                matches = find_pattern_in_file(
                    js_file,
                    r'(?:gsap\.(to|from|fromTo|set|timeline)\(|ScrollTrigger\.(create|batch)\()'
                )
                for line_num, line_content in matches:
                    violations.append(
                        f"{js_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                    )

        assert len(violations) == 0, (
            f"發現 {len(violations)} 個直接 GSAP 呼叫（應透過 OpenAver.motion.*）:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )


class TestNoDuplicateNativeDialog:
    """確認 duplicate modal 使用 Alpine state-driven pattern（不使用原生 showModal/close）"""

    def test_no_show_modal_in_state_mixins(self):
        """state/*.js 不應包含 showModal() 呼叫"""
        state_dir = Path("web/static/js/pages/search/state")
        for js_file in state_dir.glob("*.js"):
            content = js_file.read_text(encoding="utf-8")
            assert "showModal()" not in content, \
                f"{js_file.name} 仍包含原生 showModal() — 應改用 Alpine state"

    def test_duplicate_modal_uses_modal_open_class(self):
        """search.html 的 duplicate modal 應使用 :class=\"{ 'modal-open': ... }\" pattern"""
        html_path = Path("web/templates/search.html")
        content = html_path.read_text(encoding="utf-8")
        assert "duplicateModalOpen" in content, \
            "search.html 未找到 duplicateModalOpen — duplicate modal 應使用 Alpine state"


class TestTranslateAll:
    """確認 translateAll 前端基礎設施完整"""

    def test_translate_all_button_exists(self):
        """search.html 包含 translateAll() 綁定且按鈕由 listMode 條件控制"""
        html_file = PROJECT_ROOT / "web" / "templates" / "search.html"
        content = html_file.read_text(encoding='utf-8')
        assert 'translateAll()' in content, \
            "search.html 缺少 translateAll() 綁定"
        assert "listMode === 'search'" in content, \
            "search.html 缺少 listMode === 'search' 條件（控制翻譯全部按鈕顯示）"

    def test_translate_state_in_base(self):
        """base.js 包含 translateState 物件定義"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "base.js"
        content = js_file.read_text(encoding='utf-8')
        assert 'translateState' in content, \
            "base.js 缺少 translateState 物件定義"

    def test_translate_all_in_batch(self):
        """batch.js 包含 async translateAll method 定義"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "batch.js"
        content = js_file.read_text(encoding='utf-8')
        assert 'async translateAll' in content, \
            "batch.js 缺少 async translateAll method 定義"

    def test_is_cloud_search_mode_uses_list_mode(self):
        """isCloudSearchMode 應依賴 listMode === 'search'，不依賴 fileList.length"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "base.js"
        content = js_file.read_text(encoding='utf-8')
        assert "listMode === 'search'" in content, \
            "isCloudSearchMode 應使用 listMode === 'search'，不應依賴 fileList.length === 0"
        assert "fileList.length === 0 && this.searchResults.length > 0" not in content, \
            "isCloudSearchMode 不應使用 fileList.length === 0 條件（殘留 fileList 會使雲端搜尋模式失效）"


class TestJellyfinFrontend:
    """確認 Jellyfin 前端基礎設施完整"""

    def test_jellyfin_toggle_in_settings(self):
        """settings.html 包含 jellyfinMode 的 Alpine 綁定"""
        html_file = PROJECT_ROOT / "web" / "templates" / "settings.html"
        content = html_file.read_text(encoding='utf-8')
        assert 'jellyfinMode' in content, \
            "settings.html 缺少 jellyfinMode 綁定（Jellyfin 圖片模式開關）"

    def test_jellyfin_update_in_scanner(self):
        """scanner.html 包含 runJellyfinImageUpdate method"""
        html_file = PROJECT_ROOT / "web" / "templates" / "scanner.html"
        content = html_file.read_text(encoding='utf-8')
        assert 'runJellyfinImageUpdate' in content, \
            "scanner.html 缺少 runJellyfinImageUpdate（T6d Jellyfin 批次補齊）"


class TestOpenLocalGuard:
    """確認 openLocal() 綁定和 open_folder() API 的結構完整性（T5a / T5b）"""

    def test_open_local_in_search(self):
        """search.html 包含 openLocal( 綁定（Detail badge + Grid overlay 兩處）"""
        html_file = PROJECT_ROOT / "web" / "templates" / "search.html"
        content = html_file.read_text(encoding='utf-8')
        assert 'openLocal(' in content, \
            "search.html 缺少 openLocal( 綁定（T5b：Detail badge + Grid overlay）"

    def test_open_local_in_showcase(self):
        """showcase.html 包含 openLocal( 綁定（Grid overlay + Lightbox 兩處）"""
        html_file = PROJECT_ROOT / "web" / "templates" / "showcase.html"
        content = html_file.read_text(encoding='utf-8')
        assert 'openLocal(' in content, \
            "showcase.html 缺少 openLocal( 綁定（T5b：Grid overlay + Lightbox）"

    def test_open_local_method_exists(self):
        """result-card.js 和 showcase/core.js 均包含 openLocal(path) method 定義"""
        result_card = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "result-card.js"
        showcase_core = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "core.js"

        rc_content = result_card.read_text(encoding='utf-8')
        assert 'openLocal(path)' in rc_content, \
            "result-card.js 缺少 openLocal(path) method 定義（T5b）"

        sc_content = showcase_core.read_text(encoding='utf-8')
        assert 'openLocal(path)' in sc_content, \
            "showcase/core.js 缺少 openLocal(path) method 定義（T5b）"

    def test_open_folder_pywebview_api(self):
        """windows/pywebview_api.py 包含 def open_folder（T5a）"""
        api_file = PROJECT_ROOT / "windows" / "pywebview_api.py"
        content = api_file.read_text(encoding='utf-8')
        assert 'def open_folder' in content, \
            "pywebview_api.py 缺少 def open_folder（T5a）"

    def test_no_stale_copy_local_path(self):
        """search.html 不包含 copyLocalPath( 呼叫（確認舊 call 已清除）"""
        html_file = PROJECT_ROOT / "web" / "templates" / "search.html"
        content = html_file.read_text(encoding='utf-8')
        assert 'copyLocalPath(' not in content, \
            "search.html 仍包含 copyLocalPath( — T5b 應已將其改為 openLocal()"

    def test_open_local_checks_return_value(self):
        """openLocal() 的 .then() 必須檢查 open_folder 回傳值（不能無條件當成功）"""
        for js_file in [
            PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "result-card.js",
            PROJECT_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "core.js",
        ]:
            content = js_file.read_text(encoding='utf-8')
            assert '.then(async (opened)' in content, \
                f"{js_file.name} openLocal() 的 .then() 缺少 opened 參數檢查"

    def test_open_local_cross_platform_path(self):
        """openLocal() 必須偵測 Windows drive letter 而非一律轉反斜線"""
        for js_file in [
            PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "result-card.js",
            PROJECT_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "core.js",
        ]:
            content = js_file.read_text(encoding='utf-8')
            assert 'displayPath' in content, \
                f"{js_file.name} openLocal() 缺少跨平台路徑格式偵測（displayPath）"


class TestPathContract:
    """路徑契約守衛測試 — 確保路徑處理邏輯集中在 path_utils.py（T7.0）

    4 個守衛測試掃描 production code 禁止模式（T7a-T7e 已全部修正通過）。
    """

    # 掃描範圍：core/ web/ windows/（排除 path_utils.py 本身）
    _SCAN_DIRS = ['core', 'web', 'windows']
    _ALLOWED_FILE = 'path_utils.py'

    def _collect_py_files(self):
        """收集 core/、web/、windows/ 下所有 .py 檔（排除 path_utils.py）"""
        files = []
        for dir_name in self._SCAN_DIRS:
            scan_dir = PROJECT_ROOT / dir_name
            if not scan_dir.exists():
                continue
            for py_file in scan_dir.rglob('*.py'):
                if py_file.name == self._ALLOWED_FILE:
                    continue
                files.append(py_file)
        return files

    def test_no_raw_uri_strip(self):
        """掃描 Python 檔，確認無 path[8:] 或 path[len('file:///'):]  手動 URI strip"""
        # 符合 [8:] 或 [len('file:///'):]
        pattern = r'''\[8:\]|\[len\(['"]file:///['"]\):\]'''
        violations = []
        for py_file in self._collect_py_files():
            matches = find_pattern_in_file(py_file, pattern)
            for line_num, line_content in matches:
                violations.append(
                    f"{py_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                )
        assert len(violations) == 0, (
            f"發現 {len(violations)} 個手動 URI strip 違規（應改用 uri_to_fs_path()）:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_manual_uri_construct(self):
        """掃描 Python 檔，確認無 f\"file:///{ 手動 URI 建構"""
        pattern = r'f["\']file:///'
        violations = []
        for py_file in self._collect_py_files():
            matches = find_pattern_in_file(py_file, pattern)
            for line_num, line_content in matches:
                violations.append(
                    f"{py_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                )
        assert len(violations) == 0, (
            f"發現 {len(violations)} 個手動 URI 建構違規（應改用 to_file_uri()）:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_shadow_path_helpers(self):
        """掃描 Python 檔，確認無 def wsl_to_windows_path / def to_file_uri shadow helper"""
        pattern = r'def wsl_to_windows_path|def to_file_uri'
        violations = []
        for py_file in self._collect_py_files():
            matches = find_pattern_in_file(py_file, pattern)
            for line_num, line_content in matches:
                violations.append(
                    f"{py_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                )
        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 shadow path helper 定義（應集中在 path_utils.py）:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_path_to_display_js_no_optional_slash(self):
        """pathToDisplay JS 工具不應使用 /? regex（會錯誤吸收路徑前導斜線）"""
        # 搜尋所有 path-utils / pathUtils JS 檔
        candidates = list(PROJECT_ROOT.rglob('path-utils.js')) + \
                     list(PROJECT_ROOT.rglob('pathUtils.js'))
        # 排除 venv/、node_modules/
        js_files = [
            f for f in candidates
            if 'venv' not in f.parts and 'node_modules' not in f.parts
        ]
        if not js_files:
            pytest.skip("pathToDisplay JS 工具尚未建立（T7d 前）")
        violations = []
        for js_file in js_files:
            matches = find_pattern_in_file(js_file, r'\/\?')
            for line_num, line_content in matches:
                violations.append(
                    f"{js_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                )
        assert len(violations) == 0, (
            f"pathToDisplay 使用了 /? regex（會錯誤匹配路徑前導斜線）:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestSettingsSimplify:
    """T4a 守衛 — Settings 不再包含版本/更新 UI"""

    def test_settings_html_no_check_update(self):
        """settings.html 不含 checkUpdate（已搬至 help）"""
        html = (PROJECT_ROOT / 'web/templates/settings.html').read_text(encoding='utf-8')
        assert 'checkUpdate' not in html, \
            "settings.html 仍包含 checkUpdate — 應已搬至 /help"

    def test_settings_js_no_dead_methods(self):
        """settings.js 不含 loadVersion 及 restartTutorial（已搬至 help）"""
        js = (PROJECT_ROOT / 'web/static/js/pages/settings.js').read_text(encoding='utf-8')
        assert 'loadVersion' not in js, \
            "settings.js 仍包含 loadVersion — 應已搬至 help.js"
        assert 'restartTutorial' not in js, \
            "settings.js 仍包含 restartTutorial — HTML row 刪除後為死碼"


class TestHelpPage:
    """T4b 守衛 — Help 頁必要元素"""

    def test_help_js_exists(self):
        """help.js 存在"""
        assert (PROJECT_ROOT / 'web/static/js/pages/help.js').exists()

    def test_help_html_has_alpine_scope(self):
        """help.html 含 helpPage() Alpine scope"""
        html = (PROJECT_ROOT / 'web/templates/help.html').read_text(encoding='utf-8')
        assert 'helpPage()' in html

    def test_help_html_has_check_update(self):
        """help.html 含 checkUpdate 按鈕"""
        html = (PROJECT_ROOT / 'web/templates/help.html').read_text(encoding='utf-8')
        assert 'checkUpdate' in html

    def test_help_js_no_defer(self):
        """help.js script 不可帶 defer — 避免 Alpine 初始化時序問題"""
        import re
        html = (PROJECT_ROOT / 'web/templates/help.html').read_text(encoding='utf-8')
        matches = re.findall(r'<script[^>]*help\.js[^>]*>', html)
        assert len(matches) == 1, \
            f"help.html 應恰好有 1 個 help.js script tag，找到 {len(matches)} 個"
        assert 'defer' not in matches[0], \
            "help.js script tag 帶有 defer — Alpine 會在 helpPage() 定義前初始化"


class TestScannerClearCache:
    """清除快取守衛 — scanner 頁面必要元素"""

    def test_scanner_html_has_clear_cache_method(self):
        """scanner.html 含 clearCache() method"""
        html = (PROJECT_ROOT / 'web/templates/scanner.html').read_text(encoding='utf-8')
        assert 'clearCache()' in html

    def test_scanner_html_has_delete_api_binding(self):
        """scanner.html 含 DELETE /api/gallery/cache 呼叫"""
        html = (PROJECT_ROOT / 'web/templates/scanner.html').read_text(encoding='utf-8')
        assert "/api/gallery/cache" in html
        assert "DELETE" in html
