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
        # 共同根目錄，所有 allowed_files 相對路徑以此為基準
        js_root = PROJECT_ROOT / "web" / "static" / "js"
        scan_dirs = [
            js_root / "pages",
            js_root / "components",
        ]
        # motion-adapter.js 本身是合法 GSAP 呼叫點
        # motion-lab.js 和 search/animations.js 因動態座標計算需求，直接呼叫 GSAP
        # 相對路徑以 js_root 為基準，包含 pages/ 或 components/ 前綴，避免跨目錄衝突
        allowed_files = {
            Path('components') / 'motion-adapter.js',   # components/motion-adapter.js
            Path('pages') / 'motion-lab.js',            # pages/motion-lab.js（T1 新增）
            Path('pages') / 'search' / 'animations.js', # pages/search/animations.js（T6 預先加入）
            Path('pages') / 'showcase' / 'animations.js', # pages/showcase/animations.js（B6 動畫模組）
        }
        violations = []

        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for js_file in scan_dir.rglob("*.js"):
                rel = js_file.relative_to(js_root)  # 相對於 js_root，非 scan_dir
                if rel in allowed_files:
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
        state_dir = PROJECT_ROOT / "web/static/js/pages/search/state"
        for js_file in state_dir.glob("*.js"):
            content = js_file.read_text(encoding="utf-8")
            assert "showModal()" not in content, \
                f"{js_file.name} 仍包含原生 showModal() — 應改用 Alpine state"

    def test_duplicate_modal_uses_modal_open_class(self):
        """search.html 的 duplicate modal 應使用 :class=\"{ 'modal-open': ... }\" pattern"""
        html_path = PROJECT_ROOT / "web/templates/search.html"
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


class TestVideoPlaybackGuard:
    """確認影片播放走 API proxy，不直接開 file:/// URI（瀏覽器安全策略會靜默阻擋）"""

    def test_no_window_open_file_uri_in_js(self):
        """前端 JS 不應有 window.open 搭配 file:/// URI（應走 /api/gallery/player）"""
        js_dirs = [
            PROJECT_ROOT / "web" / "static" / "js" / "pages",
            PROJECT_ROOT / "web" / "static" / "js" / "components",
        ]
        # window.open(path  或 window.open(file:/// 或 location.href = path（且 path 含 file:）
        pattern = r'window\.open\s*\(\s*path\s*,'
        violations = []
        for js_dir in js_dirs:
            if not js_dir.exists():
                continue
            for js_file in js_dir.rglob("*.js"):
                matches = find_pattern_in_file(js_file, pattern)
                for line_num, line_content in matches:
                    violations.append(
                        f"{js_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                    )
        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 window.open(path, ...) 直接開啟路徑（瀏覽器會阻擋 file:/// URI）:\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\n提示：瀏覽器模式應使用 /api/gallery/player?path= 代理播放"
        )

    def test_showcase_uses_api_player(self):
        """showcase/core.js 的 playVideo() 瀏覽器分支必須走 /api/gallery/player"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "core.js"
        content = js_file.read_text(encoding='utf-8')
        assert '/api/gallery/player' in content, \
            "showcase/core.js 缺少 /api/gallery/player — 瀏覽器模式應走 API proxy 播放"

    def test_video_api_endpoint_exists(self):
        """scanner.py 包含 /api/gallery/video 和 /api/gallery/player endpoint"""
        py_file = PROJECT_ROOT / "web" / "routers" / "scanner.py"
        content = py_file.read_text(encoding='utf-8')
        assert 'async def get_video(' in content, \
            "scanner.py 缺少 get_video endpoint（影片代理 API）"
        assert 'async def video_player(' in content, \
            "scanner.py 缺少 video_player endpoint（HTML5 播放頁面）"

    def test_video_api_has_security_checks(self):
        """get_video() 必須包含 realpath + 目錄白名單 + get_proxy_extensions 動態白名單"""
        py_file = PROJECT_ROOT / "web" / "routers" / "scanner.py"
        content = py_file.read_text(encoding='utf-8')
        assert 'os.path.realpath' in content, \
            "get_video 缺少 realpath（防路徑穿越）"
        assert 'get_proxy_extensions' in content, \
            "get_video 應使用 get_proxy_extensions（動態副檔名白名單）而非硬編碼 ALLOWED_VIDEO_EXTENSIONS"
        assert 'is_path_under_dir' in content, \
            "get_video 缺少目錄白名單檢查"

    def test_no_hardcoded_video_extensions_in_modules(self):
        """gallery_scanner.py, scanner.py, pywebview_api.py must NOT contain hardcoded video extension sets
        (dict entries like '.mp4': 'video/mp4' are OK — those are MIME mappings, not extension sets)"""
        files_to_check = [
            PROJECT_ROOT / "core" / "gallery_scanner.py",
            PROJECT_ROOT / "web" / "routers" / "scanner.py",
            PROJECT_ROOT / "windows" / "pywebview_api.py",
        ]
        import re
        for file_path in files_to_check:
            content = file_path.read_text(encoding='utf-8')
            # Find set literals: = {'.mp4', '.avi', ...} (bare extension strings, no colon after)
            # This looks for lines with extension-only assignments
            # e.g., VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', ...}
            # But NOT: video_mime = {'.mp4': 'video/mp4', ...}
            set_pattern = re.compile(r"""=\s*\{[^}]*'\.mp4'[^}:]*'\.avi'[^}:]*\}""", re.DOTALL)
            matches = set_pattern.findall(content)
            assert len(matches) == 0, \
                f"{file_path.name} still contains hardcoded video extension set — should import from core.video_extensions"


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


class TestSearchCoreFacade:
    """T3.2 守衛 — SearchCore.state 已降級為只讀 Alpine proxy façade"""

    def test_search_core_state_uses_alpine_proxy(self):
        """core.js 的 window.SearchCore.state getter 必須使用 Alpine.$data 代理"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/core.js"
        content = js_file.read_text(encoding='utf-8')
        assert 'Alpine.$data' in content, (
            "core.js 的 SearchCore.state getter 未使用 Alpine.$data — "
            "T3.2 Step 1 應已將 state getter 改為代理 Alpine proxy"
        )

    def test_sync_to_core_is_noop(self):
        """bridge.js 不含 coreState.xxx = 賦值（_syncToCore 已是 no-op）"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/bridge.js"
        content = js_file.read_text(encoding='utf-8')
        # 匹配 coreState.xxx = （非 ?.、非 == 的賦值）
        violations = re.findall(r'coreState\.\w+\s*=(?!=)', content)
        assert len(violations) == 0, (
            f"bridge.js 的 _syncToCore 仍含 {len(violations)} 個 coreState 賦值 "
            f"（應已改為 no-op）: {violations}"
        )

    def test_persistence_no_corestate_fallback(self):
        """persistence.js 的 saveState() 不含 coreState?. fallback（已改為直接用 Alpine state）"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/persistence.js"
        content = js_file.read_text(encoding='utf-8')
        assert 'coreState?.' not in content, (
            "persistence.js 仍含 coreState?. fallback — "
            "T3.2 Step 3 應已移除，直接使用 Alpine this.xxx"
        )

    def test_search_core_has_legacy_state_fallback(self):
        """core.js 的 window.SearchCore 必須包含 _legacyState fallback（Alpine 未 boot 時的安全預設值）"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/core.js"
        content = js_file.read_text(encoding='utf-8')
        assert '_legacyState' in content, (
            "core.js 缺少 _legacyState — SearchCore.state getter 在 Alpine 未 boot 時"
            "必須回傳有穩定形狀的物件（含 searchResults: [], fileList: [] 等）"
        )
        # 確認 _legacyState 包含關鍵欄位
        assert 'searchResults: []' in content, "_legacyState 缺少 searchResults: []"
        assert 'fileList: []' in content, "_legacyState 缺少 fileList: []"


class TestPageLifecycleGuard:
    """page-lifecycle.js 存在性守衛 — 確保 script tag 及三頁 __registerPage 呼叫不被移除"""

    def test_base_html_loads_page_lifecycle(self):
        """base.html 必須引用 page-lifecycle.js"""
        base_html = PROJECT_ROOT / "web" / "templates" / "base.html"
        content = base_html.read_text(encoding='utf-8')
        assert 'page-lifecycle.js' in content, \
            "base.html 缺少 page-lifecycle.js script tag — 刪除會導致三頁 __registerPage 呼叫靜默失敗"

    def test_settings_js_calls_register_page(self):
        """settings.js 必須呼叫 __registerPage"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "settings.js"
        content = js_file.read_text(encoding='utf-8')
        assert '__registerPage' in content, \
            "settings.js 缺少 __registerPage 呼叫 — dirty-check lifecycle 會失效"

    def test_search_state_index_calls_register_page(self):
        """search/state/index.js 必須呼叫 __registerPage"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "index.js"
        content = js_file.read_text(encoding='utf-8')
        assert '__registerPage' in content, \
            "search/state/index.js 缺少 __registerPage 呼叫 — Search 離頁 save/cleanup 會失效"

    def test_showcase_core_calls_register_page(self):
        """showcase/core.js 必須呼叫 __registerPage"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "core.js"
        content = js_file.read_text(encoding='utf-8')
        assert '__registerPage' in content, \
            "showcase/core.js 缺少 __registerPage 呼叫 — Showcase lightbox cleanup lifecycle 會失效"

    def test_scanner_html_calls_register_page(self):
        """scanner.html 必須呼叫 __registerPage"""
        html_file = PROJECT_ROOT / "web" / "templates" / "scanner.html"
        content = html_file.read_text(encoding='utf-8')
        assert '__registerPage' in content, \
            "scanner.html 缺少 __registerPage 呼叫 — Scanner lifecycle 未接入統一機制"


class TestScannerLifecycleGuard:
    """T5.1 守衛 — Scanner 已接入 __registerPage，不再使用舊 shim"""

    SCANNER_HTML = PROJECT_ROOT / "web" / "templates" / "scanner.html"
    PAGE_LIFECYCLE_JS = PROJECT_ROOT / "web" / "static" / "js" / "components" / "page-lifecycle.js"

    def test_scanner_no_confirm_leaving_scanner(self):
        """scanner.html 不含 confirmLeavingScanner（舊 shim 已刪除）"""
        content = self.SCANNER_HTML.read_text(encoding='utf-8')
        assert 'confirmLeavingScanner' not in content, \
            "scanner.html 仍含 confirmLeavingScanner — T5.1 應已刪除舊離頁 shim"

    def test_scanner_no_self_added_beforeunload(self):
        """scanner.html 不自掛 addEventListener('beforeunload'（由 page-lifecycle.js 統一管理）"""
        content = self.SCANNER_HTML.read_text(encoding='utf-8')
        assert "addEventListener('beforeunload'" not in content, \
            "scanner.html 仍自掛 beforeunload listener — T5.1 應刪除，改由 onBeforeUnload hook 處理"

    def test_scanner_no_skip_before_unload(self):
        """scanner.html 不含 _skipBeforeUnload（隨舊 shim 一起刪除）"""
        content = self.SCANNER_HTML.read_text(encoding='utf-8')
        assert '_skipBeforeUnload' not in content, \
            "scanner.html 仍含 _skipBeforeUnload — T5.1 應已隨舊 shim 一起刪除"

    def test_page_lifecycle_no_confirm_leaving_scanner_shim(self):
        """page-lifecycle.js 不含 confirmLeavingScanner compatibility shim"""
        content = self.PAGE_LIFECYCLE_JS.read_text(encoding='utf-8')
        assert 'confirmLeavingScanner' not in content, \
            "page-lifecycle.js 仍含 confirmLeavingScanner shim — T5.1 Scanner 接入後應刪除"


class TestEventSourceTracking:
    """T4.1 守衛 — 所有 EventSource 建立都透過 _trackConnection 包裝"""

    def test_base_has_active_connections(self):
        """base.js 必須有 _activeConnections: [] 初始值"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
        content = js_file.read_text(encoding='utf-8')
        assert '_activeConnections' in content, \
            "base.js 缺少 _activeConnections 初始值 — T4.1 集中追蹤 EventSource"

    def test_search_flow_has_track_methods(self):
        """search-flow.js 必須定義 _trackConnection / _untrackConnection / _closeAllConnections"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
        content = js_file.read_text(encoding='utf-8')
        for method in ('_trackConnection', '_untrackConnection', '_closeAllConnections'):
            assert method in content, \
                f"search-flow.js 缺少 {method} — T4.1 連線追蹤方法"

    def test_do_search_uses_track_connection(self):
        """doSearch() 的 new EventSource 必須包在 _trackConnection(...) 內"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
        content = js_file.read_text(encoding='utf-8')
        # 確認有 _trackConnection(new EventSource( 的用法
        assert '_trackConnection(new EventSource(' in content, \
            "search-flow.js 的 doSearch() 未使用 _trackConnection 包裝 EventSource"

    def test_file_list_uses_track_connection(self):
        """searchForFile() 的 new EventSource 必須包在 _trackConnection(...) 內"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js"
        content = js_file.read_text(encoding='utf-8')
        assert '_trackConnection(' in content, \
            "file-list.js 的 searchForFile() 未使用 _trackConnection 包裝 EventSource"

    def test_cleanup_calls_close_all_connections(self):
        """cleanupForNavigation() 必須呼叫 _closeAllConnections()"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
        content = js_file.read_text(encoding='utf-8')
        assert '_closeAllConnections()' in content, \
            "search-flow.js 的 cleanupForNavigation() 未呼叫 _closeAllConnections()"

    def test_no_bare_new_event_source_in_search_state(self):
        """search/state/ 下所有 JS 的 new EventSource 都應在 _trackConnection 內"""
        state_dir = PROJECT_ROOT / "web/static/js/pages/search/state"
        violations = []
        for js_file in state_dir.glob("*.js"):
            content = js_file.read_text(encoding='utf-8')
            # 找 new EventSource( 但不在 _trackConnection 同行
            for i, line in enumerate(content.splitlines(), 1):
                if 'new EventSource(' in line and '_trackConnection' not in line:
                    violations.append(f"{js_file.name}:{i} — {line.strip()[:80]}")
        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 bare new EventSource（未包在 _trackConnection 內）:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestTimerTracking:
    """T4.2 守衛 — 所有 setTimeout 都透過 _timers registry 管理"""

    def test_base_has_timers_registry(self):
        """base.js 必須有 _timers: {} 初始值"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
        content = js_file.read_text(encoding='utf-8')
        assert '_timers: {}' in content, \
            "base.js 缺少 _timers: {} — T4.2 集中追蹤 setTimeout"

    def test_base_no_toast_timer(self):
        """base.js 不再有 _toastTimer: null 宣告（已由 _timers registry 取代）"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
        content = js_file.read_text(encoding='utf-8')
        assert '_toastTimer: null' not in content, \
            "base.js 仍含 _toastTimer: null — T4.2 應已移除，改用 _timers registry"

    def test_search_flow_has_set_timer(self):
        """search-flow.js 必須定義 _setTimer method"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
        content = js_file.read_text(encoding='utf-8')
        assert '_setTimer(' in content, \
            "search-flow.js 缺少 _setTimer method — T4.2 timer registry"

    def test_search_flow_has_clear_all_timers(self):
        """search-flow.js 必須定義 _clearAllTimers method"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
        content = js_file.read_text(encoding='utf-8')
        assert '_clearAllTimers(' in content, \
            "search-flow.js 缺少 _clearAllTimers method — T4.2 timer registry"

    def test_cleanup_calls_clear_all_timers(self):
        """cleanupForNavigation() 必須呼叫 _clearAllTimers()"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
        content = js_file.read_text(encoding='utf-8')
        assert '_clearAllTimers()' in content, \
            "search-flow.js 的 cleanupForNavigation() 未呼叫 _clearAllTimers()"

    def test_result_card_no_manual_toast_timer(self):
        """result-card.js 不再有 _toastTimer = 手動賦值（改用 _setTimer）"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/result-card.js"
        content = js_file.read_text(encoding='utf-8')
        assert '_toastTimer =' not in content, \
            "result-card.js 仍含 _toastTimer = 手動賦值 — T4.2 應改用 _setTimer('toast', ...)"

    def test_result_card_uses_set_timer(self):
        """result-card.js 的 showToast() 必須使用 _setTimer"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/result-card.js"
        content = js_file.read_text(encoding='utf-8')
        assert "_setTimer('toast'" in content, \
            "result-card.js 的 showToast() 未使用 _setTimer('toast', ...) — T4.2"

    def test_persistence_uses_set_timer(self):
        """persistence.js 的 setupAutoSave() 必須使用 _setTimer（不再用 saveTimeout local variable）"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/persistence.js"
        content = js_file.read_text(encoding='utf-8')
        assert "_setTimer('autosave'" in content, \
            "persistence.js 的 setupAutoSave() 未使用 _setTimer('autosave', ...) — T4.2"
        assert 'saveTimeout' not in content, \
            "persistence.js 仍含 saveTimeout local variable — T4.2 應已移除"

    def test_file_list_uses_set_timer(self):
        """file-list.js 的 loadFavorite() 必須使用 _setTimer"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js"
        content = js_file.read_text(encoding='utf-8')
        assert "_setTimer('loadFavorite'" in content, \
            "file-list.js 的 loadFavorite() 未使用 _setTimer('loadFavorite', ...) — T4.2"


class TestWindowGlobalCleanup:
    """T3.3 守衛 — bridge.js 不再設定多餘的 window.xxx 全域函數"""

    BRIDGE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/bridge.js"
    FILE_LIST_JS = PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js"
    PERSISTENCE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/persistence.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
    INIT_JS = PROJECT_ROOT / "web/static/js/pages/search/init.js"

    def test_bridge_no_window_edit_tag_functions(self):
        """bridge.js 不應設定 translateWithAI / startEditTitle / confirmEditTitle 等 11 個全域函數"""
        content = self.BRIDGE_JS.read_text(encoding='utf-8')
        forbidden = [
            'window.translateWithAI',
            'window.startEditTitle',
            'window.confirmEditTitle',
            'window.cancelEditTitle',
            'window.startEditChineseTitle',
            'window.confirmEditChineseTitle',
            'window.cancelEditChineseTitle',
            'window.showAddTagInput',
            'window.confirmAddTag',
            'window.cancelAddTag',
            'window.removeUserTag',
        ]
        found = [f for f in forbidden if f in content]
        assert len(found) == 0, (
            f"bridge.js 仍設定 {len(found)} 個多餘全域函數（HTML 已用 Alpine @click）: {found}"
        )

    def test_bridge_no_window_searchcore_progress_bridge(self):
        """bridge.js 不應設定 window.SearchCore.initProgress / updateLog / handleSearchStatus"""
        content = self.BRIDGE_JS.read_text(encoding='utf-8')
        forbidden = [
            'window.SearchCore.initProgress',
            'window.SearchCore.updateLog',
            'window.SearchCore.handleSearchStatus',
        ]
        found = [f for f in forbidden if f in content]
        assert len(found) == 0, (
            f"bridge.js 仍設定 {len(found)} 個 SearchCore bridge（應由 file-list.js 直接呼叫 Alpine method）: {found}"
        )

    def test_file_list_calls_this_progress_methods(self):
        """file-list.js 的 searchForFile() 應直接呼叫 this.initProgress / this.updateLog / this.handleSearchStatus"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        assert 'this.initProgress(' in content, \
            "file-list.js 缺少 this.initProgress() — 應直接呼叫 Alpine method，不透過 window.SearchCore"
        assert 'this.updateLog(' in content, \
            "file-list.js 缺少 this.updateLog() — 應直接呼叫 Alpine method，不透過 window.SearchCore"
        assert 'this.handleSearchStatus(' in content, \
            "file-list.js 缺少 this.handleSearchStatus() — 應直接呼叫 Alpine method，不透過 window.SearchCore"

    def test_file_list_no_searchcore_progress_calls(self):
        """file-list.js 不應再透過 window.SearchCore 呼叫進度函數"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        forbidden = [
            'window.SearchCore.initProgress',
            'window.SearchCore.updateLog',
            'window.SearchCore.handleSearchStatus',
        ]
        found = [f for f in forbidden if f in content]
        assert len(found) == 0, (
            f"file-list.js 仍透過 window.SearchCore 呼叫 {len(found)} 個進度函數: {found}"
        )

    def test_no_window_searchcore_update_clear_button(self):
        """Alpine mixins 不應再呼叫 window.SearchCore.updateClearButton()"""
        targets = [self.FILE_LIST_JS, self.PERSISTENCE_JS, self.SEARCH_FLOW_JS]
        violations = []
        for js_file in targets:
            content = js_file.read_text(encoding='utf-8')
            if 'window.SearchCore.updateClearButton' in content:
                violations.append(js_file.name)
        assert len(violations) == 0, (
            f"以下檔案仍呼叫 window.SearchCore.updateClearButton()（應改為 this.hasContent = ...）: {violations}"
        )

    def test_init_no_progress_fallback(self):
        """init.js 不應再包含 initProgress / updateLog / handleSearchStatus 的防呆 fallback"""
        content = self.INIT_JS.read_text(encoding='utf-8')
        forbidden = ['window.SearchCore.initProgress =', 'window.SearchCore.updateLog =',
                     'window.SearchCore.handleSearchStatus =']
        found = [f for f in forbidden if f in content]
        assert len(found) == 0, (
            f"init.js 仍包含 {len(found)} 個防呆 fallback（bridge 移除後不再需要）: {found}"
        )


class TestFetchAbortController:
    """T4.3 守衛 — fetch 可取消化（AbortController per-key）"""
    BASE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
    NAVIGATION_JS = PROJECT_ROOT / "web/static/js/pages/search/state/navigation.js"
    BATCH_JS = PROJECT_ROOT / "web/static/js/pages/search/state/batch.js"
    FILE_LIST_JS = PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js"

    def test_base_has_abort_controllers(self):
        """base.js 必須有 _abortControllers: {} 初始值"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert '_abortControllers: {}' in content

    def test_search_flow_has_get_abort_signal(self):
        """search-flow.js 必須定義 _getAbortSignal method"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert '_getAbortSignal(' in content

    def test_search_flow_has_abort_all_fetches(self):
        """search-flow.js 必須定義 _abortAllFetches method"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert '_abortAllFetches(' in content

    def test_cleanup_calls_abort_all_fetches(self):
        """cleanupForNavigation() 必須呼叫 _abortAllFetches()"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert '_abortAllFetches()' in content

    def test_load_more_uses_abort_signal(self):
        """loadMore() 的 fetch 必須傳 signal"""
        content = self.NAVIGATION_JS.read_text(encoding='utf-8')
        assert "_getAbortSignal('loadMore')" in content

    def test_load_more_handles_abort_error(self):
        """loadMore() 的 catch 必須處理 AbortError"""
        content = self.NAVIGATION_JS.read_text(encoding='utf-8')
        assert 'AbortError' in content

    def test_translate_all_uses_abort_signal(self):
        """translateAll() 的 fetch 必須傳 signal"""
        content = self.BATCH_JS.read_text(encoding='utf-8')
        assert "_getAbortSignal('translateAll')" in content

    def test_translate_all_handles_abort_error(self):
        """translateAll() 的 catch 必須處理 AbortError"""
        content = self.BATCH_JS.read_text(encoding='utf-8')
        assert 'AbortError' in content

    def test_set_file_list_uses_abort_signal(self):
        """setFileList() 的 filter-files fetch 必須傳 signal"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        assert "_getAbortSignal('setFileList')" in content

    def test_set_file_list_handles_abort_error(self):
        """setFileList() 的 filter-files catch 必須處理 AbortError"""
        # 確認 file-list.js 的 filter-files catch 有 AbortError guard
        # 用 content 中 AbortError 出現至少 2 次（setFileList + loadFavorite）
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        assert content.count('AbortError') >= 2

    def test_load_favorite_uses_abort_signal(self):
        """loadFavorite() 的 fetch 必須傳 signal"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        assert "_getAbortSignal('loadFavorite')" in content


class TestScannerDeadCodeGuard:
    """T5.2 守衛 — Scanner 已移除 window.isGenerating 死碼"""

    SCANNER_HTML = PROJECT_ROOT / "web" / "templates" / "scanner.html"

    def test_scanner_no_window_is_generating(self):
        """scanner.html 不含 window.isGenerating（Alpine getter 已完全取代）"""
        content = self.SCANNER_HTML.read_text(encoding='utf-8')
        assert 'window.isGenerating' not in content, \
            "scanner.html 仍含 window.isGenerating — T5.2 應已移除所有死碼賦值"


class TestSearchMigrationDeadCode:
    """T5.3 守衛 — Search 遷移殘留清除（T5.3a + T5.3b）"""

    CORE_JS = PROJECT_ROOT / "web/static/js/pages/search/core.js"
    BRIDGE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/bridge.js"
    FILE_JS = PROJECT_ROOT / "web/static/js/pages/search/file.js"

    # ===== T5.3a 守衛 =====

    def test_core_no_savestate_stub(self):
        """core.js 不含 saveState / restoreState 空殼函數定義"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        assert 'function saveState()' not in content, \
            "core.js 仍含 function saveState() 空殼 — T5.3a 應已刪除"
        assert 'function restoreState()' not in content, \
            "core.js 仍含 function restoreState() 空殼 — T5.3a 應已刪除"
        assert 'T3.2: dead code' not in content, \
            "core.js 仍含 T3.2 dead code 註解 — T5.3a 應已刪除"

    def test_core_no_null_progress_slots(self):
        """core.js 不含 initProgress / updateLog / handleSearchStatus null slot"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        assert 'initProgress: null' not in content, \
            "core.js 仍含 initProgress: null slot — T5.3a 應已刪除"
        assert 'updateLog: null' not in content, \
            "core.js 仍含 updateLog: null slot — T5.3a 應已刪除"
        assert 'handleSearchStatus: null' not in content, \
            "core.js 仍含 handleSearchStatus: null slot — T5.3a 應已刪除"

    def test_bridge_no_render_noop(self):
        """bridge.js 不含 renderFileList / renderSearchResultsList no-op 覆寫"""
        content = self.BRIDGE_JS.read_text(encoding='utf-8')
        assert 'renderFileList' not in content, \
            "bridge.js 仍含 renderFileList no-op 覆寫 — T5.3a 應已刪除"
        assert 'renderSearchResultsList' not in content, \
            "bridge.js 仍含 renderSearchResultsList no-op 覆寫 — T5.3a 應已刪除"

    def test_file_no_render_stubs(self):
        """file.js 不含 renderFileList / renderSearchResultsList 空函數定義"""
        content = self.FILE_JS.read_text(encoding='utf-8')
        assert 'renderFileList' not in content, \
            "file.js 仍含 renderFileList 空函數定義 — T5.3a 應已刪除"
        assert 'renderSearchResultsList' not in content, \
            "file.js 仍含 renderSearchResultsList 空函數定義 — T5.3a 應已刪除"

    # ===== T5.3b 守衛 =====

    def test_core_no_dosearch_null_slot(self):
        """core.js 不含 doSearch: null slot"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        assert 'doSearch: null' not in content, \
            "core.js 仍含 doSearch: null slot — T5.3b 應已刪除"

    def test_bridge_no_searchfile_stubs(self):
        """bridge.js 不含 SearchFile bridge stub 轉發"""
        content = self.BRIDGE_JS.read_text(encoding='utf-8')
        assert 'window.SearchFile.switchToFile' not in content, \
            "bridge.js 仍含 window.SearchFile.switchToFile — T5.3b 應已刪除"
        assert 'window.SearchFile.searchAll' not in content, \
            "bridge.js 仍含 window.SearchFile.searchAll — T5.3b 應已刪除"
        assert 'window.SearchFile.scrapeAll' not in content, \
            "bridge.js 仍含 window.SearchFile.scrapeAll — T5.3b 應已刪除"
        assert 'window.SearchFile.setFileList' not in content, \
            "bridge.js 仍含 window.SearchFile.setFileList — T5.3b 應已刪除"
        assert 'window.SearchFile.handleFileDrop' not in content, \
            "bridge.js 仍含 window.SearchFile.handleFileDrop — T5.3b 應已刪除"

    def test_file_no_bridge_stubs(self):
        """file.js 不含 bridge stub 空函數定義"""
        content = self.FILE_JS.read_text(encoding='utf-8')
        assert 'switchToFile: function()' not in content, \
            "file.js 仍含 switchToFile: function() 空函數 — T5.3b 應已刪除"
        assert 'searchAll: function()' not in content, \
            "file.js 仍含 searchAll: function() 空函數 — T5.3b 應已刪除"
        assert 'scrapeAll: function()' not in content, \
            "file.js 仍含 scrapeAll: function() 空函數 — T5.3b 應已刪除"
        assert 'setFileList: function()' not in content, \
            "file.js 仍含 setFileList: function() 空函數 — T5.3b 應已刪除"
        assert 'handleFileDrop: function()' not in content, \
            "file.js 仍含 handleFileDrop: function() 空函數 — T5.3b 應已刪除"


class TestStreamState:
    """T4 Frontend State + Skeleton Grid 靜態守衛測試

    確認 SSE stream state 的 contract 存在：
    - base.js 宣告 stream state 欄位
    - search-flow.js 處理三種 SSE 事件類型
    - search.html 包含 skeleton template 綁定
    - failed slot 使用 visibility 而非 x-show（C10 約束）
    - search.css 包含 skeleton 動畫樣式
    """

    BASE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
    SEARCH_HTML = PROJECT_ROOT / "web/templates/search.html"
    SEARCH_CSS = PROJECT_ROOT / "web/static/css/pages/search.css"

    def test_base_js_core_stream_state(self):
        """base.js 宣告核心 stream state 欄位"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert 'streamSlots' in content, "缺少 streamSlots 宣告"
        assert 'streamComplete' in content, "缺少 streamComplete 宣告"
        assert 'isStreaming' in content, "缺少 isStreaming 宣告"

    def test_base_js_staging_buffer_state(self):
        """base.js 宣告 U2 staging buffer state 欄位"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert 'streamBuffer' in content, "缺少 streamBuffer 宣告"
        assert 'streamBurstTimer' in content, "缺少 streamBurstTimer 宣告"
        assert 'streamBurstedSlots' in content, "缺少 streamBurstedSlots 宣告"
        assert 'stagingVisible' in content, "缺少 stagingVisible 宣告"

    def test_base_js_staging_display_state(self):
        """base.js 宣告 U3 staging display state 欄位，並確保已移除 streamFilled"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert 'streamFilled' not in content, "仍含 streamFilled — 應已移除"
        assert 'stagingCover' in content, "缺少 stagingCover 宣告"
        assert 'stagingNumber' in content, "缺少 stagingNumber 宣告"
        assert 'stagingReceivedCount' in content, "缺少 stagingReceivedCount 宣告"

    def test_result_item_uses_stream_buffer(self):
        """result-item handler 推入 streamBuffer，不直接更新 searchResults（U2 batching 約束）；U3 新增 staging state 更新"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert 'streamBuffer' in content, \
            "search-flow.js 缺少 streamBuffer 引用 — U2 batching 邏輯"
        assert 'streamBurstTimer' in content, \
            "search-flow.js 缺少 streamBurstTimer 引用 — U2 時間窗口 timer"
        # U3: result-item handler 更新 staging state
        assert 'stagingCover' in content, \
            "search-flow.js 缺少 stagingCover 引用 — U3 result-item handler 更新 staging display state"
        assert 'stagingNumber' in content, \
            "search-flow.js 缺少 stagingNumber 引用 — U3 result-item handler 更新 staging display state"

    def test_search_flow_handles_seed_event(self):
        """search-flow.js 包含 seed、result-item、result-complete 三種 SSE 事件 handler"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert "data.type === 'seed'" in content, \
            "search-flow.js 缺少 data.type === 'seed' handler — T4 SSE protocol"
        assert "data.type === 'result-item'" in content, \
            "search-flow.js 缺少 data.type === 'result-item' handler — T4 SSE protocol"
        assert "data.type === 'result-complete'" in content, \
            "search-flow.js 缺少 data.type === 'result-complete' handler — T4 SSE protocol"

    def test_search_html_has_skeleton_template(self):
        """search.html 包含 :data-slot 屬性、_skeleton class 綁定、_failed 相關綁定"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert ':data-slot' in content, \
            "search.html 缺少 :data-slot 屬性綁定 — T4 skeleton grid slot 識別"
        assert '_skeleton' in content, \
            "search.html 缺少 _skeleton class 綁定 — T4 skeleton grid 視覺"
        assert '_failed' in content, \
            "search.html 缺少 _failed 相關綁定 — T4 failed slot 視覺"

    def test_failed_slot_uses_display_none(self):
        """failed slot 使用 display: none 隱藏（C29 約束：_failed slot 完全移除佈局空間）"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert 'display: none' in content or 'display:none' in content, \
            ("search.html 缺少 display: none — "
             "C29 約束：_failed slot 必須用 display: none 完全隱藏")
        assert 'visibility: hidden' not in content and 'visibility:hidden' not in content, \
            ("search.html 仍包含 visibility: hidden — "
             "C29 約束：已改用 display: none，不應殘留 visibility: hidden")

    def test_search_css_has_skeleton_styles(self):
        """search.css 包含 .skeleton-cover class、.shimmer class、@keyframes shimmer"""
        content = self.SEARCH_CSS.read_text(encoding='utf-8')
        assert '.skeleton-cover' in content, \
            "search.css 缺少 .skeleton-cover class — T4 skeleton overlay 樣式"
        assert '.shimmer' in content, \
            "search.css 缺少 .shimmer class — T4 shimmer 動畫樣式"
        assert '@keyframes shimmer' in content, \
            "search.css 缺少 @keyframes shimmer — T4 shimmer 動畫定義"

    def test_search_flow_has_stream_guard(self):
        """search-flow.js 的 result handler 包含 streamComplete guard（C12 約束）"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert 'this.streamComplete' in content, \
            "search-flow.js 缺少 streamComplete guard — T4 防止漸進路徑 result 覆蓋 searchResults"


class TestAnimationHookup:
    """T5 Frontend Animation Hookup 靜態守衛

    確認 animations.js 載入順序、SearchAnimations window 物件、
    動畫觸發 wiring 合約存在。
    """

    SEARCH_HTML = PROJECT_ROOT / "web/templates/search.html"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
    ANIMATIONS_JS = PROJECT_ROOT / "web/static/js/pages/search/animations.js"
    SEARCH_CSS = PROJECT_ROOT / "web/static/css/pages/search.css"

    def test_animations_js_exists(self):
        """search/animations.js 必須存在"""
        assert self.ANIMATIONS_JS.exists(), \
            "web/static/js/pages/search/animations.js 不存在 — T5 必須新建此檔案"

    def test_animations_js_exposes_window_object(self):
        """animations.js 暴露 window.SearchAnimations 物件"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'window.SearchAnimations' in content, \
            "animations.js 缺少 window.SearchAnimations — 必須掛 window 物件供 search-flow.js 呼叫"

    def test_animations_js_loaded_before_state_modules(self):
        """animations.js script tag 在 state/base.js 之前（search.html 載入順序）"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        anim_pos = content.find('animations.js')
        base_pos = content.find('state/base.js')
        assert anim_pos != -1, \
            "search.html 缺少 animations.js script tag"
        assert base_pos != -1, \
            "search.html 缺少 state/base.js script tag（預期已存在）"
        assert anim_pos < base_pos, \
            ("animations.js 必須在 state/base.js 之前載入 — "
             "確保 window.SearchAnimations 在 SSE handler 執行前已掛上")

    def test_search_flow_has_animation_trigger_in_result_item(self):
        """search-flow.js 包含 SearchAnimations 引用；U3 後 playMiniBurst 在 _flushStreamBuffer 呼叫"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert 'SearchAnimations' in content, \
            "search-flow.js 缺少 SearchAnimations 引用 — playGridFadeIn 仍在 seed handler 使用"
        # U3: playMiniBurst 已接入 _flushStreamBuffer，hook point 註解已移除
        assert 'playMiniBurst' in content, \
            "search-flow.js 缺少 playMiniBurst 引用 — U3 _flushStreamBuffer 應呼叫 playMiniBurst"

    def test_staging_card_html_exists(self):
        """search.html 包含 staging-anchor overlay（.staging-card、stagingVisible + displayMode guard、stagingCover、stagingNumber、stagingReceivedCount）"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert 'staging-anchor' in content, \
            "search.html 缺少 staging-anchor class — U3 staging overlay HTML"
        assert 'staging-card' in content, \
            "search.html 缺少 staging-card class — U3 staging card HTML"
        assert 'stagingVisible' in content, \
            "search.html 缺少 stagingVisible 綁定 — U3 staging card 可見性控制"
        assert "displayMode === 'grid'" in content, \
            "search.html staging x-show 缺少 displayMode === 'grid' guard — 切 detail view 時不該顯示 staging"
        assert 'stagingCover' in content, \
            "search.html 缺少 stagingCover 綁定 — U3 staging card 封面圖"
        assert 'stagingNumber' in content, \
            "search.html 缺少 stagingNumber 綁定 — U3 staging card 番號"
        assert 'stagingReceivedCount' in content, \
            "search.html 缺少 stagingReceivedCount 綁定 — U3 staging card 計數 badge"

    def test_staging_card_css_exists(self):
        """search.css 包含 staging card CSS（.staging-anchor、.staging-counter-badge）"""
        content = self.SEARCH_CSS.read_text(encoding='utf-8')
        assert '.staging-anchor' in content, \
            "search.css 缺少 .staging-anchor class — U3 staging overlay 容器樣式"
        assert '.staging-counter-badge' in content, \
            "search.css 缺少 .staging-counter-badge class — U3 計數 badge 樣式"

    def test_animations_js_has_play_mini_burst(self):
        """animations.js 包含 playMiniBurst 方法（U3 mini-burst 動畫）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playMiniBurst' in content, \
            "animations.js 缺少 playMiniBurst — U3 必須新增此方法（gsap.fromTo 偏移飛行）"

    def test_animations_js_has_staging_animations(self):
        """animations.js 包含 playStagingEntry、playStagingExit、playCoverSwap 方法"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playStagingEntry' in content, \
            "animations.js 缺少 playStagingEntry — U3 staging card 進場 morph"
        assert 'playStagingExit' in content, \
            "animations.js 缺少 playStagingExit — U3 staging card 退場 morph + onComplete"
        assert 'playCoverSwap' in content, \
            "animations.js 缺少 playCoverSwap — U3 staging card 封面替換動畫"

    def test_flush_triggers_animation(self):
        """search-flow.js 的 _flushStreamBuffer 包含 playMiniBurst 引用（U3 接 mini-burst 動畫）"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert '_flushStreamBuffer' in content, \
            "search-flow.js 缺少 _flushStreamBuffer 方法 — U2/U3 batching 核心函數"
        assert 'playMiniBurst' in content, \
            "search-flow.js 缺少 playMiniBurst 呼叫 — U3 _flushStreamBuffer 必須觸發 mini-burst 動畫"

    def test_animations_js_has_reduced_motion_guard(self):
        """animations.js 檢查 prefersReducedMotion（Reduced Motion 降級）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'prefersReducedMotion' in content, \
            "animations.js 缺少 prefersReducedMotion 守衛 — Reduced Motion 時必須跳過動畫"

    # ===== U4: Detail Entry + Grid-Detail Ghost Transition Guards =====

    GRID_MODE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/grid-mode.js"

    def test_animations_js_has_detail_entry(self):
        """animations.js 包含 playDetailEntry 方法"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playDetailEntry' in content, \
            "animations.js 缺少 playDetailEntry — U4 detail entry 動畫（cover slide-in + info fade-in）"

    def test_animations_js_has_grid_to_detail(self):
        """animations.js 包含 playGridToDetail 方法"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playGridToDetail' in content, \
            "animations.js 缺少 playGridToDetail — U4 Grid->Detail ghost 轉場動畫"

    def test_animations_js_has_detail_to_grid(self):
        """animations.js 包含 playDetailToGrid 方法"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playDetailToGrid' in content, \
            "animations.js 缺少 playDetailToGrid — U4 Detail->Grid ghost 飛回動畫"

    def test_grid_mode_switch_to_detail_has_animation(self):
        """grid-mode.js switchToDetail 接入 ghost transition"""
        content = self.GRID_MODE_JS.read_text(encoding='utf-8')
        assert 'SearchAnimations' in content, \
            "grid-mode.js 缺少 SearchAnimations 引用 — switchToDetail 應接入 ghost 轉場"
        assert 'getBoundingClientRect' in content, \
            "grid-mode.js 缺少 getBoundingClientRect — C17 step 1 capture rect"
        assert '$nextTick' in content, \
            "grid-mode.js 缺少 $nextTick — C17 step 3 animate after render"

    def test_grid_mode_toggle_has_animation(self):
        """grid-mode.js toggleDisplayMode 接入 ghost fly-back"""
        content = self.GRID_MODE_JS.read_text(encoding='utf-8')
        assert 'playDetailToGrid' in content, \
            "grid-mode.js 缺少 playDetailToGrid — toggleDisplayMode Detail->Grid 應觸發 ghost 飛回"

    def test_search_flow_exact_result_has_detail_entry(self):
        """search-flow.js exact result 觸發 detail entry 動畫"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert 'playDetailEntry' in content, \
            "search-flow.js 缺少 playDetailEntry — exact result 應觸發 detail entry 動畫"

    def test_animations_js_has_ghost_cleanup(self):
        """animations.js 包含 ghost 清除邏輯"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'data-search-ghost' in content, \
            "animations.js 缺少 data-search-ghost attribute — ghost 元素需可識別以便清除"
        assert 'remove()' in content or 'removeChild' in content, \
            "animations.js 缺少 ghost 清除呼叫 — ghost 元素必須在動畫完成後移除"

    # ===== U5: Detail Navigation Slide + Interrupt Guards =====

    NAVIGATION_JS = PROJECT_ROOT / "web/static/js/pages/search/state/navigation.js"

    def test_animations_js_has_slide_in(self):
        """animations.js 包含 playSlideIn 方法（U5 導航滑動動畫）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playSlideIn' in content, \
            "animations.js 缺少 playSlideIn — U5 detail 導航滑動動畫"

    def test_navigation_has_kill_tweens(self):
        """navigation.js 包含 killTweensOf（C18 interrupt 策略）"""
        content = self.NAVIGATION_JS.read_text(encoding='utf-8')
        assert 'killTweensOf' in content, \
            "navigation.js 缺少 killTweensOf — C18 interrupt 策略需在導航時打斷舊動畫"

    def test_navigation_has_slide_animation(self):
        """navigation.js 接入 SearchAnimations slide 動畫"""
        content = self.NAVIGATION_JS.read_text(encoding='utf-8')
        assert 'SearchAnimations' in content, \
            "navigation.js 缺少 SearchAnimations 引用 — navigate() 應接入 slide 動畫"
        assert 'playSlideIn' in content, \
            "navigation.js 缺少 playSlideIn 引用 — navigate() 應觸發 slide-in 動畫"

    # ===== U6: Integration + Cleanup Guards =====

    def test_no_css_fadein_keyframes(self):
        """search.css 不應包含 @keyframes fadeIn（已由 GSAP playDetailEntry 取代）"""
        content = self.SEARCH_CSS.read_text(encoding='utf-8')
        assert '@keyframes fadeIn' not in content, \
            "search.css 仍包含 @keyframes fadeIn — U6 應移除（GSAP playDetailEntry 已取代此 CSS 動畫）"

    def test_no_play_card_stream_in_in_search_animations(self):
        """animations.js 不應包含 playCardStreamIn（已由 playMiniBurst 取代）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playCardStreamIn' not in content, \
            "animations.js 仍包含 playCardStreamIn — U3 已由 playMiniBurst 取代，不應存在"

    def test_all_animation_methods_consolidated(self):
        """animations.js 包含所有 9 個預期動畫方法（U3/U4/U5 合併驗證）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        expected_methods = [
            'playMiniBurst',
            'playCoverSwap',
            'playStagingEntry',
            'playStagingExit',
            'playGridFadeIn',
            'playDetailEntry',
            'playGridToDetail',
            'playDetailToGrid',
            'playSlideIn',
        ]
        for method in expected_methods:
            assert method in content, \
                f"animations.js 缺少 {method} — 預期 9 個動畫方法全部存在"

    # ===== U7a: File Search Detail Entry Guard =====

    FILE_LIST_JS = PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js"

    def test_file_search_result_has_detail_entry(self):
        """U7a: file-list.js searchForFile() result triggers playDetailEntry"""
        content = self.FILE_LIST_JS.read_text(encoding="utf-8")
        assert "playDetailEntry" in content, (
            "file-list.js must call playDetailEntry for file search results (U7a)"
        )

    # ===== U7b: File Switch Cached Slide Guards =====

    def test_file_switch_cached_has_slide(self):
        """U7b: file-list.js switchToFile() cached path triggers playSlideIn"""
        content = self.FILE_LIST_JS.read_text(encoding="utf-8")
        assert "playSlideIn" in content, (
            "file-list.js must call playSlideIn for cached file switch (U7b)"
        )

    def test_file_switch_has_kill_tweens(self):
        """U7b: file-list.js switchToFile() cached path interrupts old animation"""
        content = self.FILE_LIST_JS.read_text(encoding="utf-8")
        assert "killTweensOf" in content, (
            "file-list.js must call killTweensOf for C18 interrupt in file switch (U7b)"
        )

    def test_play_slide_in_kills_child_tweens(self):
        """Codex review: playSlideIn must kill child element tweens (cover/info) not just container"""
        content = self.ANIMATIONS_JS.read_text(encoding="utf-8")
        # Find the playSlideIn function definition (not the comment reference)
        slide_in_start = content.find('playSlideIn: function')
        assert slide_in_start != -1, "playSlideIn function definition not found in animations.js"
        # Check that it references child selectors for kill
        slide_in_body = content[slide_in_start:slide_in_start + 800]
        assert 'av-card-full-cover' in slide_in_body, (
            "playSlideIn must kill .av-card-full-cover child tweens (Codex review fix)"
        )
        assert 'av-card-full-info' in slide_in_body, (
            "playSlideIn must kill .av-card-full-info child tweens (Codex review fix)"
        )


class TestCoverStateGuard:
    """U8a Cover State 集中管理守衛

    確認 base.js 有 _resetCoverState helper + state fields，
    search-flow.js 有 _clearTimer method。
    """

    BASE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"

    def test_base_has_reset_cover_state(self):
        """base.js 包含 _resetCoverState 定義"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert '_resetCoverState' in content, \
            "base.js 缺少 _resetCoverState — U8a 必須新增集中式 cover state reset helper"

    def test_reset_cover_state_increments_request_id(self):
        """base.js 的 _resetCoverState 包含 _coverRequestId++"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        # 確認 _resetCoverState 方法體內有 _coverRequestId++
        match = re.search(r'_resetCoverState\s*\(', content)
        assert match, "base.js 缺少 _resetCoverState 方法定義"
        method_body = content[match.start():match.start() + 500]
        assert '_coverRequestId++' in method_body, \
            "base.js _resetCoverState 缺少 _coverRequestId++ — 必須遞增 request ID"

    def test_reset_cover_state_calls_clear_timer(self):
        """base.js 的 _resetCoverState 包含 _clearTimer + coverRetry"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        match = re.search(r'_resetCoverState\s*\(', content)
        assert match, "base.js 缺少 _resetCoverState 方法定義"
        method_body = content[match.start():match.start() + 500]
        assert '_clearTimer' in method_body, \
            "base.js _resetCoverState 缺少 _clearTimer 呼叫 — 必須清除 coverRetry timer"
        assert 'coverRetry' in method_body, \
            "base.js _resetCoverState 缺少 coverRetry 參數 — _clearTimer 需指定 key"

    def test_search_flow_has_clear_timer_method(self):
        """search-flow.js 包含 _clearTimer method 定義"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert re.search(r'_clearTimer\s*\(\s*\w+\s*\)', content), \
            "search-flow.js 缺少 _clearTimer(key) 方法定義 — U8a 必須新增單一 timer 清除方法"

    def test_base_has_cover_request_id_field(self):
        """base.js 包含 _coverRequestId 初始值"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert re.search(r'_coverRequestId\s*:\s*0', content), \
            "base.js 缺少 _coverRequestId: 0 初始值 — U8a 必須新增 cover request ID 欄位"

    def test_base_has_cover_loaded_field(self):
        """base.js 包含 _coverLoaded 初始值"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert re.search(r'_coverLoaded\s*:\s*false', content), \
            "base.js 缺少 _coverLoaded: false 初始值 — U8a 必須新增 cover loaded 欄位"

    # === U8b guard tests ===

    FILE_LIST_JS = PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js"
    NAVIGATION_JS = PROJECT_ROOT / "web/static/js/pages/search/state/navigation.js"
    GRID_MODE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/grid-mode.js"
    BATCH_JS = PROJECT_ROOT / "web/static/js/pages/search/state/batch.js"
    PERSISTENCE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/persistence.js"

    def test_file_list_reset_cover_state_count(self):
        """file-list.js 包含至少 8 次 _resetCoverState 呼叫"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        count = content.count('_resetCoverState')
        assert count >= 8, (
            f"file-list.js 只有 {count} 次 _resetCoverState（需至少 8 次: "
            f"#4,#5,#6,#7,#8,#9,#10,#11）"
        )

    def test_navigation_reset_cover_state_count(self):
        """navigation.js 包含至少 2 次 _resetCoverState 呼叫"""
        content = self.NAVIGATION_JS.read_text(encoding='utf-8')
        count = content.count('_resetCoverState')
        assert count >= 2, (
            f"navigation.js 只有 {count} 次 _resetCoverState（需至少 2 次: "
            f"#1 navigate, #15 loadMore）"
        )

    def test_search_flow_reset_cover_state_count(self):
        """search-flow.js 包含至少 4 次 _resetCoverState 呼叫"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        count = content.count('_resetCoverState')
        assert count >= 4, (
            f"search-flow.js 只有 {count} 次 _resetCoverState（需至少 4 次: "
            f"#12 doSearch init, #13 traditional result, #14 fallback result, fallbackSearch）"
        )

    def test_no_bare_cover_error_reset(self):
        """file-list/navigation/search-flow 中不應有裸 coverError = '' 純 reset 行"""
        files_to_check = [self.FILE_LIST_JS, self.NAVIGATION_JS, self.SEARCH_FLOW_JS]
        violations = []
        for fpath in files_to_check:
            content = fpath.read_text(encoding='utf-8')
            for i, line in enumerate(content.splitlines(), 1):
                # 匹配 coverError = '' 或 coverError = "" (純 reset，非 set error)
                if re.search(r"""coverError\s*=\s*['"](['"])\s*;""", line):
                    # 排除 _resetCoverState 方法定義本身
                    if '_resetCoverState' in line:
                        continue
                    violations.append(f"{fpath.name}:{i} — {line.strip()}")
        assert len(violations) == 0, (
            f"發現 {len(violations)} 個裸 coverError = '' reset（應改用 _resetCoverState()）:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )

    def test_grid_mode_reset_cover_state(self):
        """grid-mode.js 包含至少 1 次 _resetCoverState 呼叫"""
        content = self.GRID_MODE_JS.read_text(encoding='utf-8')
        count = content.count('_resetCoverState')
        assert count >= 1, (
            f"grid-mode.js 缺少 _resetCoverState（需至少 1 次: #16 switchToDetail）"
        )

    def test_batch_reset_cover_state(self):
        """batch.js 包含至少 1 次 _resetCoverState 呼叫"""
        content = self.BATCH_JS.read_text(encoding='utf-8')
        count = content.count('_resetCoverState')
        assert count >= 1, (
            f"batch.js 缺少 _resetCoverState（需至少 1 次: #17 scrapeAll）"
        )

    def test_persistence_reset_cover_state(self):
        """persistence.js 包含至少 1 次 _resetCoverState 呼叫"""
        content = self.PERSISTENCE_JS.read_text(encoding='utf-8')
        count = content.count('_resetCoverState')
        assert count >= 1, (
            f"persistence.js 缺少 _resetCoverState（需至少 1 次: #19 restoreState）"
        )

    # === U8c guard tests ===

    RESULT_CARD_JS = PROJECT_ROOT / "web/static/js/pages/search/state/result-card.js"

    def test_cover_error_has_get_attribute_guard(self):
        """result-card.js 的 handleCoverError 內含 getAttribute"""
        content = self.RESULT_CARD_JS.read_text(encoding='utf-8')
        match = re.search(r'handleCoverError\s*\(', content)
        assert match, "result-card.js 缺少 handleCoverError 方法定義"
        method_body = content[match.start():match.start() + 800]
        assert 'getAttribute' in method_body, \
            "handleCoverError 缺少 getAttribute — Phase 1 stale guard 必須用 getAttribute('src') 比對"

    def test_cover_error_has_cover_url_comparison(self):
        """result-card.js 的 handleCoverError 內含 coverUrl"""
        content = self.RESULT_CARD_JS.read_text(encoding='utf-8')
        match = re.search(r'handleCoverError\s*\(', content)
        assert match, "result-card.js 缺少 handleCoverError 方法定義"
        method_body = content[match.start():match.start() + 800]
        assert 'coverUrl' in method_body, \
            "handleCoverError 缺少 coverUrl — Phase 1 stale guard 必須與 coverUrl() 比對"

    def test_cover_error_has_request_id_guard(self):
        """result-card.js 的 handleCoverError 內含 _coverRequestId"""
        content = self.RESULT_CARD_JS.read_text(encoding='utf-8')
        match = re.search(r'handleCoverError\s*\(', content)
        assert match, "result-card.js 缺少 handleCoverError 方法定義"
        method_body = content[match.start():match.start() + 800]
        assert '_coverRequestId' in method_body, \
            "handleCoverError 缺少 _coverRequestId — Phase 2 timer 競態守衛必須檢查 request ID"

    def test_cover_retry_uses_set_timer(self):
        """result-card.js 內含 _setTimer + coverRetry"""
        content = self.RESULT_CARD_JS.read_text(encoding='utf-8')
        assert '_setTimer' in content, \
            "result-card.js 缺少 _setTimer — cover retry 必須使用 _setTimer 而非 raw setTimeout"
        assert 'coverRetry' in content, \
            "result-card.js 缺少 coverRetry — _setTimer 必須使用 'coverRetry' key"

    # === U8d guard tests ===

    SEARCH_HTML = PROJECT_ROOT / "web/templates/search.html"
    SEARCH_CSS = PROJECT_ROOT / "web/static/css/pages/search.css"

    def test_load_handler_sets_cover_loaded(self):
        """search.html 的 @load handler 包含 _coverLoaded = true"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert '_coverLoaded = true' in content, \
            "search.html 缺少 _coverLoaded = true — U8d 必須在 cover img @load handler 設定 _coverLoaded"

    def test_shimmer_placeholder_in_html(self):
        """search.html 包含 cover-loading-placeholder"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert 'cover-loading-placeholder' in content, \
            "search.html 缺少 cover-loading-placeholder — U8d 必須新增 shimmer loading placeholder"

    def test_shimmer_placeholder_in_css(self):
        """search.css 包含 cover-loading-placeholder 樣式"""
        content = self.SEARCH_CSS.read_text(encoding='utf-8')
        assert 'cover-loading-placeholder' in content, \
            "search.css 缺少 cover-loading-placeholder — U8d 必須新增 shimmer placeholder 樣式"

    # === U8 Codex review fix guard tests ===

    UI_JS = PROJECT_ROOT / "web/static/js/pages/search/ui.js"

    def test_switch_source_reset_cover_state(self):
        """ui.js 的 switchSource 包含 _resetCoverState（#20 cover-changing path）"""
        content = self.UI_JS.read_text(encoding='utf-8')
        assert '_resetCoverState' in content, (
            "ui.js 缺少 _resetCoverState — switchSource 替換結果時必須重置 cover state（#20）"
        )

    def test_cover_error_guards_empty_cover_url(self):
        """result-card.js 的 handleCoverError 在 _coverRetried 之前有 coverUrl 空值 early return"""
        content = self.RESULT_CARD_JS.read_text(encoding='utf-8')
        match = re.search(r'handleCoverError\s*\(', content)
        assert match, "result-card.js 缺少 handleCoverError 方法定義"
        method_body = content[match.start():match.start() + 800]
        # coverUrl() 取值必須在 _coverRetried check 之前
        cover_url_pos = method_body.find('coverUrl')
        retried_pos = method_body.find('_coverRetried')
        assert cover_url_pos != -1, \
            "handleCoverError 缺少 coverUrl — 必須檢查空 coverUrl early return"
        assert retried_pos != -1, \
            "handleCoverError 缺少 _coverRetried"
        assert cover_url_pos < retried_pos, (
            "handleCoverError 的 coverUrl 檢查必須在 _coverRetried 之前 — "
            "空 coverUrl 時應直接 return，避免 stale @error 觸發錯誤的 retry"
        )


class TestSearchAllRaceGuard:
    """U10 guard: _searchFileBackground + searchAll 共享狀態競態保護"""

    FILE_LIST_JS = PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js"
    BATCH_JS = PROJECT_ROOT / "web/static/js/pages/search/state/batch.js"

    def test_search_file_background_exists(self):
        """file-list.js 必須包含 _searchFileBackground 方法"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        assert '_searchFileBackground' in content, \
            "file-list.js 缺少 _searchFileBackground — U10a 必須新增背景搜尋方法"

    def test_search_file_background_no_shared_state_writes(self):
        """_searchFileBackground 不應讀寫共享 UI 狀態（只能操作 file 物件）"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        match = re.search(r'_searchFileBackground\s*\(', content)
        assert match, "file-list.js 缺少 _searchFileBackground 方法定義"
        method_body = content[match.start():match.start() + 2000]

        # 負面斷言：不應碰共享 UI 狀態
        assert 'this.currentFileIndex' not in method_body, \
            "_searchFileBackground 不應寫入 this.currentFileIndex — 背景搜尋不碰共享狀態"
        assert 'this.currentIndex' not in method_body, \
            "_searchFileBackground 不應寫入 this.currentIndex — 背景搜尋不碰共享狀態"
        assert 'this.displayMode' not in method_body, \
            "_searchFileBackground 不應寫入 this.displayMode — 背景搜尋不碰共享狀態"
        assert 'window.SearchUI.showState' not in method_body, \
            "_searchFileBackground 不應呼叫 window.SearchUI.showState — 背景搜尋不碰 UI"

        # 特殊處理：排除 file.searchResults 誤判
        assert 'this.searchResults' not in method_body, \
            "_searchFileBackground 不應讀寫 this.searchResults — 背景搜尋只能操作 file.searchResults"

        # 正面斷言：應操作 file 物件
        assert 'file.searchResults' in method_body, \
            "_searchFileBackground 必須寫入 file.searchResults — 結果存在 file 物件上"
        assert 'file.searched' in method_body, \
            "_searchFileBackground 必須寫入 file.searched — 標記搜尋完成"

    def test_search_all_uses_background_search(self):
        """batch.js 的 searchAll 必須使用 _searchFileBackground"""
        content = self.BATCH_JS.read_text(encoding='utf-8')
        assert '_searchFileBackground' in content, \
            "batch.js 缺少 _searchFileBackground 呼叫 — U10b searchAll 必須改用背景搜尋"

    def test_search_all_no_direct_switch_to_file_in_promise_all(self):
        """searchAll 的 Promise.all(chunk.map 區塊內不應直接呼叫 switchToFile"""
        content = self.BATCH_JS.read_text(encoding='utf-8')
        match = re.search(r'Promise\.all\(chunk\.map', content)
        assert match, "batch.js 缺少 Promise.all(chunk.map — searchAll 結構異常"
        # 取到 })); 的區塊（約 500 字元）
        block = content[match.start():match.start() + 500]
        # 找到 })); 結束位置，截斷
        end_marker = block.find('}));')
        if end_marker != -1:
            block = block[:end_marker + 3]
        assert 'switchToFile' not in block, (
            "searchAll 的 Promise.all(chunk.map) 內不應直接呼叫 switchToFile — "
            "背景搜尋期間切換檔案會造成 UI 競態"
        )

    def test_search_file_background_no_ui_side_effects(self):
        """_searchFileBackground 不應有 UI 副作用（switchToFile / showToast / alert）"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        match = re.search(r'_searchFileBackground\s*\(', content)
        assert match, "file-list.js 缺少 _searchFileBackground 方法定義"
        method_body = content[match.start():match.start() + 2000]

        assert 'switchToFile(' not in method_body, \
            "_searchFileBackground 不應呼叫 switchToFile — 背景搜尋不切換 UI"
        assert 'showToast(' not in method_body, \
            "_searchFileBackground 不應呼叫 showToast — 背景搜尋不顯示 toast"
        assert 'alert(' not in method_body, \
            "_searchFileBackground 不應呼叫 alert — 背景搜尋不彈出對話框"

    def test_search_file_background_has_close_wrapper(self):
        """_searchFileBackground 必須有 close-wrapper（確保 forced-close 時 Promise settle）"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        match = re.search(r'_searchFileBackground\s*\(', content)
        assert match, "file-list.js 缺少 _searchFileBackground 方法定義"
        method_body = content[match.start():match.start() + 2000]

        assert 'settle' in method_body, \
            "_searchFileBackground 缺少 settle 函數 — 必須包裝 close 確保 Promise 可 resolve"
        assert 'originalClose' in method_body, \
            "_searchFileBackground 缺少 originalClose — 必須保存原始 close 再覆寫"


class TestFailedSlotC30Guard:
    """C30 guard: _failed slot 必須從導航、計數、lightbox 中排除

    確認各 JS 方法在計算 navigation、indicator、file count 時
    正確排除 _failed slot，避免用戶看到空白結果或導航到失敗項目。
    """

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    NAVIGATION_JS = PROJECT_ROOT / "web/static/js/pages/search/state/navigation.js"
    GRID_MODE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/grid-mode.js"
    BASE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
    SEARCH_HTML = PROJECT_ROOT / "web/templates/search.html"

    def test_navigate_skips_failed(self):
        """navigate() 必須跳過 _failed slot，避免導航到空白結果 (C30)"""
        content = self.NAVIGATION_JS.read_text(encoding='utf-8')
        match = re.search(r'navigate\s*\(', content)
        assert match, "navigation.js 缺少 navigate() 方法"
        method_body = content[match.start():match.start() + 500]
        assert '_failed' in method_body, "navigate() 必須包含 _failed skip 邏輯 (C30)"

    def test_lightbox_nav_skips_failed(self):
        """prevLightboxVideo / nextLightboxVideo 必須跳過 _failed slot (C30)"""
        content = self.GRID_MODE_JS.read_text(encoding='utf-8')
        for method_name in ['prevLightboxVideo', 'nextLightboxVideo']:
            match = re.search(rf'{method_name}\s*\(', content)
            assert match, f"grid-mode.js 缺少 {method_name}() 方法"
            method_body = content[match.start():match.start() + 800]
            assert '_failed' in method_body, f"{method_name}() 必須包含 _failed skip 邏輯 (C30)"

    def test_nav_indicator_excludes_failed(self):
        """navIndicatorText() 計算導航指示器時必須排除 _failed slot (C30)"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        match = re.search(r'navIndicatorText\s*\(', content)
        assert match, "base.js 缺少 navIndicatorText() 方法"
        method_body = content[match.start():match.start() + 500]
        assert '_failed' in method_body, "navIndicatorText() 必須包含 _failed 排除邏輯 (C30)"

    def test_can_go_prev_checks_failed(self):
        """canGoPrev() 判斷是否可向前導航時必須考慮 _failed slot (C30)"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        match = re.search(r'canGoPrev\s*\(', content)
        assert match, "base.js 缺少 canGoPrev() 方法"
        method_body = content[match.start():match.start() + 300]
        assert '_failed' in method_body, "canGoPrev() 必須包含 _failed 檢查邏輯 (C30)"

    def test_can_go_next_checks_failed(self):
        """canGoNext() 判斷是否可向後導航時必須考慮 _failed slot (C30)"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        match = re.search(r'canGoNext\s*\(', content)
        assert match, "base.js 缺少 canGoNext() 方法"
        method_body = content[match.start():match.start() + 300]
        assert '_failed' in method_body, "canGoNext() 必須包含 _failed 檢查邏輯 (C30)"

    def test_show_navigation_excludes_failed(self):
        """showNavigation() 決定是否顯示導航 UI 時必須排除 _failed slot (C30)"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        match = re.search(r'showNavigation\s*\(', content)
        assert match, "base.js 缺少 showNavigation() 方法"
        method_body = content[match.start():match.start() + 300]
        assert '_failed' in method_body, "showNavigation() 必須包含 _failed 排除邏輯 (C30)"

    def test_file_count_text_excludes_failed(self):
        """fileCountText() 顯示檔案數量時必須排除 _failed slot (C30)"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        match = re.search(r'fileCountText\s*\(', content)
        assert match, "base.js 缺少 fileCountText() 方法"
        method_body = content[match.start():match.start() + 500]
        assert '_failed' in method_body, "fileCountText() 必須包含 _failed 排除邏輯 (C30)"

    def test_lightbox_arrows_use_has_visible_methods(self):
        """search.html lightbox 箭頭必須使用 hasVisiblePrev/Next() 而非 canGoPrev/Next() (C30)"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert 'hasVisiblePrev()' in content, "search.html 必須使用 hasVisiblePrev() (C30)"
        assert 'hasVisibleNext()' in content, "search.html 必須使用 hasVisibleNext() (C30)"

    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"

    def test_repoint_is_conditional(self):
        """result-complete 的 currentIndex repoint 必須是條件式的：只在當前指向 _failed 時才 repoint (Codex review)"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        # 找到 repoint 區塊
        idx = content.find('firstValid')
        assert idx != -1, "search-flow.js 缺少 firstValid repoint 邏輯"
        # 取 repoint 附近的程式碼區塊（往前 200 字元）
        repoint_context = content[max(0, idx - 200):idx + 200]
        # 確認有條件檢查：在 findIndex 之前先檢查當前 item 是否 _failed
        assert 'currentResult' in repoint_context or 'this.searchResults[this.currentIndex]' in repoint_context, \
            "repoint 必須先檢查當前 currentIndex 是否指向 _failed item，不可無條件覆蓋 (Codex review)"


class TestRotatingBorderOnceRemoved:
    """A2A3 守衛 — 確認 .once 變體及相關追蹤邏輯已完全移除"""

    ROTATING_BORDER_CSS = PROJECT_ROOT / "web/static/css/components/rotating-border.css"
    SEARCH_HTML = PROJECT_ROOT / "web/templates/search.html"
    STATE_DIR = PROJECT_ROOT / "web/static/js/pages/search/state"
    BASE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"

    def test_no_once_class_in_css(self):
        """rotating-border.css 不應包含 .once selector"""
        content = self.ROTATING_BORDER_CSS.read_text(encoding='utf-8')
        matches = find_pattern_in_file(self.ROTATING_BORDER_CSS, r'\.once')
        assert len(matches) == 0, (
            f"rotating-border.css 仍包含 .once selector（應已在 A2A3 移除）:\n" +
            "\n".join(f"  L{ln}: {line}" for ln, line in matches)
        )

    def test_no_animationend_in_search_html(self):
        """search.html 不應包含 rotating-border 相關的 @animationend handler"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert 'markLocalBorderPlayed' not in content, (
            "search.html 仍包含 markLocalBorderPlayed — "
            "A2A3 應已完全移除 rotating-border 的 animationend 追蹤邏輯"
        )
        assert '@animationend' not in content, (
            "search.html 仍包含 @animationend handler — "
            "A2A3 應已移除 rotating-border 的所有 animationend handler"
        )

    def test_no_once_class_in_search_html(self):
        """search.html 的 rotating-border :class 綁定不應包含 'active once' 模式"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert 'active once' not in content, (
            "search.html 仍包含 'active once' 模式 — "
            "A2A3 應已移除 .once 變體，:class 綁定只需 'active'"
        )

    def test_no_markLocalBorderPlayed_in_js(self):
        """state/ 目錄下的 JS 檔案不應包含 markLocalBorderPlayed"""
        violations = []
        for js_file in self.STATE_DIR.glob("*.js"):
            matches = find_pattern_in_file(js_file, r'markLocalBorderPlayed')
            for ln, line in matches:
                violations.append(f"{js_file.name}:{ln} — {line[:80]}")
        assert len(violations) == 0, (
            f"state/ JS 仍包含 markLocalBorderPlayed（應已在 A2A3 移除）:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_localBorderPlayed_in_js(self):
        """state/ 目錄下的 JS 檔案不應包含 _localBorderPlayed"""
        violations = []
        for js_file in self.STATE_DIR.glob("*.js"):
            matches = find_pattern_in_file(js_file, r'_localBorderPlayed')
            for ln, line in matches:
                violations.append(f"{js_file.name}:{ln} — {line[:80]}")
        assert len(violations) == 0, (
            f"state/ JS 仍包含 _localBorderPlayed（應已在 A2A3 移除）:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )

    def test_shouldShowLocalBorder_still_exists(self):
        """base.js 應仍包含 shouldShowLocalBorder 方法（簡化但未刪除）"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert 'shouldShowLocalBorder' in content, (
            "base.js 缺少 shouldShowLocalBorder 方法 — "
            "A2A3 應簡化此方法而非刪除"
        )

    def test_shouldShowLocalBorder_no_played_reference(self):
        """base.js 的 shouldShowLocalBorder 不應引用 _localBorderPlayed"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        match = re.search(r'shouldShowLocalBorder\s*\(', content)
        assert match, "base.js 缺少 shouldShowLocalBorder 方法"
        method_body = content[match.start():match.start() + 300]
        assert '_localBorderPlayed' not in method_body, (
            "shouldShowLocalBorder 仍引用 _localBorderPlayed — "
            "A2A3 應簡化為只檢查 result?._localStatus?.exists"
        )


class TestGridSettlePulse:
    """A4 守衛 — Grid Settle Pulse 落地

    確認 animations.js 暴露 playGridSettle 方法、search-flow.js 的
    onExitComplete 呼叫 playGridSettle、CustomEase "settle" 曲線已註冊、
    以及 C4/C6 約束遵守。
    """

    ANIMATIONS_JS = PROJECT_ROOT / "web/static/js/pages/search/animations.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"

    def test_animations_exposes_play_grid_settle(self):
        """animations.js 包含 playGridSettle 方法定義"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playGridSettle' in content, (
            "animations.js 缺少 playGridSettle — "
            "A4 必須新增此方法（Grid Settle Pulse 落地動畫）"
        )

    def test_search_flow_calls_play_grid_settle(self):
        """search-flow.js 的 onExitComplete 或 _triggerStagingExit 區段呼叫 playGridSettle"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        # 找方法定義（不是呼叫點 this._triggerStagingExit()）
        match = re.search(r'_triggerStagingExit\s*\(\s*\)\s*\{', content)
        assert match, (
            "search-flow.js 缺少 _triggerStagingExit 方法定義"
        )
        # 取足夠大的方法體區段（包含 onExitComplete callback + $nextTick）
        trigger_body = content[match.start():match.start() + 1000]
        assert 'playGridSettle' in trigger_body, (
            "search-flow.js 的 _triggerStagingExit / onExitComplete 缺少 playGridSettle 呼叫 — "
            "A4 staging exit 完成後應觸發 Grid Settle Pulse"
        )

    def test_animations_registers_settle_custom_ease(self):
        """animations.js 包含 CustomEase.create("settle" 註冊"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'CustomEase.create("settle"' in content, (
            "animations.js 缺少 CustomEase.create(\"settle\" — "
            "A4 必須註冊 settle 自訂曲線供 playGridSettle 使用"
        )

    def test_play_grid_settle_has_kill_tweens_of(self):
        """animations.js 的 playGridSettle 方法體包含 killTweensOf（C4 約束）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        # 找方法定義（不是 JSDoc 註解中的提及）
        match = re.search(r'playGridSettle:\s*function', content)
        assert match, (
            "animations.js 缺少 playGridSettle 方法定義"
        )
        method_body = content[match.start():match.start() + 3000]
        assert 'killTweensOf' in method_body, (
            "playGridSettle 缺少 killTweensOf — "
            "C4 約束：每個動畫開頭必須 gsap.killTweensOf(target) 清舊動畫"
        )

    def test_play_grid_settle_no_rotation(self):
        """animations.js 的 playGridSettle 方法體不包含 rotation（C6 約束）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        # 找方法定義（不是 JSDoc 註解中的提及）
        match = re.search(r'playGridSettle:\s*function', content)
        assert match, (
            "animations.js 缺少 playGridSettle 方法定義"
        )
        method_body = content[match.start():match.start() + 3000]
        # 排除註解行，只檢查實際程式碼中的 rotation 屬性
        code_lines = [
            line for line in method_body.split('\n')
            if line.strip() and not line.strip().startswith('//')
        ]
        code_only = '\n'.join(code_lines)
        assert 'rotation' not in code_only, (
            "playGridSettle 包含 rotation — "
            "C6 約束：不使用 rotationX / rotationY / rotationZ"
        )


class TestHeroImageErrorGuard:
    """A6-1 Hero Card / Lightbox 圖片錯誤狀態管理守衛

    確認 Hero Card 和 Lightbox 的 @error handler 不直接修改 DOM，
    改用 Alpine state 管理錯誤狀態。
    """

    SEARCH_HTML = PROJECT_ROOT / "web/templates/search.html"
    BASE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"

    def test_hero_card_no_target_src_in_error(self):
        """search.html 中 Hero Card img 的 @error 不包含 target.src 或 .src ="""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        # 找到 hero-card class 屬性（排除註解）
        match = re.search(r'class="[^"]*hero-card[^"]*"', content)
        assert match, "search.html 缺少 hero-card class 區塊"
        # 取 hero-card 區塊（往後 800 字元足以覆蓋 img tag）
        hero_block = content[match.start():match.start() + 800]
        # 提取 @error 屬性值
        error_match = re.search(r'@error="([^"]*)"', hero_block)
        assert error_match, "hero-card 區塊缺少 @error handler"
        error_value = error_match.group(1)
        assert 'target.src' not in error_value and '.src =' not in error_value, (
            f"hero-card @error 仍包含 DOM 修改（target.src / .src =）：{error_value}\n"
            "A6-1 要求改用 Alpine state（_heroCardImageError = true）"
        )

    def test_hero_card_no_onerror_null(self):
        """search.html 中 Hero Card img 的 @error 不包含 onerror"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        match = re.search(r'class="[^"]*hero-card[^"]*"', content)
        assert match, "search.html 缺少 hero-card class 區塊"
        hero_block = content[match.start():match.start() + 800]
        error_match = re.search(r'@error="([^"]*)"', hero_block)
        assert error_match, "hero-card 區塊缺少 @error handler"
        error_value = error_match.group(1)
        assert 'onerror' not in error_value, (
            f"hero-card @error 仍包含 onerror=null：{error_value}\n"
            "A6-1 要求移除 onerror=null，改用 Alpine state 管理"
        )

    def test_base_has_hero_image_error_states(self):
        """base.js 包含 _heroCardImageError 和 _heroLightboxImageError 兩個 field"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert '_heroCardImageError' in content, (
            "base.js 缺少 _heroCardImageError — A6-1 必須新增 Hero Card 圖片錯誤 state"
        )
        assert '_heroLightboxImageError' in content, (
            "base.js 缺少 _heroLightboxImageError — A6-1 必須新增 Lightbox 圖片錯誤 state"
        )

    def test_do_search_resets_hero_image_errors(self):
        """search-flow.js 的 doSearch 方法區段包含兩個 error state 的重置"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        match = re.search(r'async\s+doSearch', content)
        assert match, "search-flow.js 缺少 doSearch 方法定義"
        method_body = content[match.start():match.start() + 2000]
        assert '_heroCardImageError' in method_body and '= false' in method_body, (
            "search-flow.js doSearch 缺少 _heroCardImageError = false 重置 — "
            "A6-1 新搜尋必須清空 Hero Card 圖片錯誤"
        )
        assert '_heroLightboxImageError' in method_body and '= false' in method_body, (
            "search-flow.js doSearch 缺少 _heroLightboxImageError = false 重置 — "
            "A6-1 新搜尋必須清空 Lightbox 圖片錯誤"
        )


class TestLightboxModeNormalization:
    """A6-2 Lightbox 模式正規化 + restoreState 防護守衛

    確認 restoreState 後 lightbox 狀態被正規化，
    以及 openActressLightbox 有 actressProfile 存在性 guard。
    """

    PERSISTENCE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/persistence.js"
    GRID_MODE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/grid-mode.js"

    def test_restore_state_resets_lightbox_open(self):
        """persistence.js 的 restoreState 方法區段包含 lightboxOpen = false 重置"""
        content = self.PERSISTENCE_JS.read_text(encoding='utf-8')
        match = re.search(r'restoreState\s*\(\s*\)', content)
        assert match, "persistence.js 缺少 restoreState 方法定義"
        # 取 restoreState 方法體（到 saveState 為止，取 3000 字元覆蓋完整 try block）
        method_body = content[match.start():match.start() + 3000]
        assert 'lightboxOpen' in method_body and '= false' in method_body, (
            "persistence.js restoreState 缺少 lightboxOpen = false 重置 — "
            "A6-2 還原後 lightbox 不應處於開啟狀態"
        )

    def test_restore_state_handles_lightbox_index_with_actress(self):
        """persistence.js 的 restoreState 方法區段在 actressProfile 條件下處理 lightboxIndex"""
        content = self.PERSISTENCE_JS.read_text(encoding='utf-8')
        match = re.search(r'restoreState\s*\(\s*\)', content)
        assert match, "persistence.js 缺少 restoreState 方法定義"
        method_body = content[match.start():match.start() + 3000]
        # 確認有 actressProfile 條件判斷 + lightboxIndex 設定
        assert 'actressProfile' in method_body and 'lightboxIndex' in method_body, (
            "persistence.js restoreState 缺少 actressProfile 條件下的 lightboxIndex 處理 — "
            "A6-2 有女優資料時應將 lightboxIndex 設為 -1"
        )

    def test_open_actress_lightbox_has_actress_guard(self):
        """grid-mode.js 的 openActressLightbox 方法開頭有 actressProfile 存在性 guard"""
        content = self.GRID_MODE_JS.read_text(encoding='utf-8')
        match = re.search(r'openActressLightbox\s*\(\s*\)', content)
        assert match, "grid-mode.js 缺少 openActressLightbox 方法定義"
        # 取方法開頭 300 字元（guard 應在最前面）
        method_head = content[match.start():match.start() + 300]
        assert re.search(r'if\s*\(\s*!this\.actressProfile\s*\)\s*return', method_head), (
            "grid-mode.js openActressLightbox 缺少 actressProfile guard — "
            "A6-2 無女優資料時不應開啟 actress lightbox"
        )


class TestHeroSlotReservation:
    """A7-Prod 守衛 — Hero Slot 一律預留落地

    確認 seed handler 設定 _heroSlotReserved、search.html Hero Card
    x-show 包含 _heroSlotReserved、animations.js 暴露 playHeroRemove、
    result-complete 不拆 placeholder、result handler 統一處理 _heroSlotReserved。
    """

    BASE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
    SEARCH_HTML = PROJECT_ROOT / "web/templates/search.html"
    ANIMATIONS_JS = PROJECT_ROOT / "web/static/js/pages/search/animations.js"

    def test_seed_handler_sets_hero_slot_reserved(self):
        """search-flow.js seed handler 包含 _heroSlotReserved = true"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        # 找 seed handler
        match = re.search(r"data\.type\s*===?\s*['\"]seed['\"]", content)
        assert match, "search-flow.js 缺少 seed handler"
        seed_block = content[match.start():match.start() + 1000]
        assert '_heroSlotReserved' in seed_block and '= true' in seed_block, (
            "search-flow.js seed handler 缺少 _heroSlotReserved = true — "
            "A7-Prod 所有送 seed 的搜尋必須預留 Hero slot"
        )

    def test_hero_card_xshow_includes_hero_slot_reserved(self):
        """search.html Hero Card x-show 包含 _heroSlotReserved"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        match = re.search(r'class="[^"]*hero-card[^"]*"', content)
        assert match, "search.html 缺少 hero-card class 區塊"
        hero_block = content[max(0, match.start() - 200):match.start() + 200]
        assert '_heroSlotReserved' in hero_block, (
            "search.html Hero Card x-show 缺少 _heroSlotReserved 條件 — "
            "A7-Prod Hero Card 應在 actressProfile || _heroSlotReserved 時顯示"
        )

    def test_animations_exposes_play_hero_remove(self):
        """animations.js 包含 playHeroRemove 方法定義"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert re.search(r'playHeroRemove\s*:', content), (
            "animations.js 缺少 playHeroRemove 方法 — "
            "A7-Prod 必須新增此方法（Flip 補位動畫）"
        )

    def test_result_complete_does_not_remove_hero_slot(self):
        """search-flow.js result-complete handler 不拆 Hero placeholder（由 result 事件決定）"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        match = re.search(r"data\.type\s*===?\s*['\"]result-complete['\"]", content)
        assert match, "search-flow.js 缺少 result-complete handler"
        rc_block = content[match.start():match.start() + 1500]
        # result-complete 不應包含 _heroSlotReserved = false（拆除邏輯）
        assert '_heroSlotReserved = false' not in rc_block, (
            "search-flow.js result-complete handler 不應拆除 Hero placeholder — "
            "A7-Prod Hero slot 最終命運由 result 事件決定"
        )

    def test_fallback_search_handles_hero_slot_no_actress(self):
        """search-flow.js fallbackSearch 成功但無 actressProfile 時移除 _heroSlotReserved"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        match = re.search(r'async\s+fallbackSearch\s*\(', content)
        assert match, "search-flow.js 缺少 fallbackSearch 方法"
        fb_block = content[match.start():match.start() + 3000]
        assert '_heroSlotReserved' in fb_block, (
            "search-flow.js fallbackSearch 缺少 _heroSlotReserved 處理 — "
            "A7-Prod SSE 斷線走 fallback 時，無 actressProfile 必須移除 Hero placeholder"
        )

    def test_fallback_search_hero_slot_flip_remove(self):
        """search-flow.js fallbackSearch 的 _heroSlotReserved 移除包含 Flip 動畫"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        match = re.search(r'async\s+fallbackSearch\s*\(', content)
        assert match, "search-flow.js 缺少 fallbackSearch 方法"
        fb_block = content[match.start():match.start() + 3000]
        assert 'playHeroRemove' in fb_block, (
            "search-flow.js fallbackSearch 的 _heroSlotReserved 移除缺少 playHeroRemove 呼叫 — "
            "A7-Prod 必須透過 Flip 動畫平滑移除 Hero placeholder"
        )

    def test_result_event_handles_hero_slot_in_normal_stream(self):
        """search-flow.js result 事件（正常 stream 路徑）統一處理 _heroSlotReserved"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        # 找 streamComplete 後的 result handler 中的正常路徑
        # 正常 stream 完成路徑在 "正常 stream 完成：只補充 metadata" 附近
        assert '正常 stream 完成' in content, (
            "search-flow.js 缺少正常 stream 完成路徑的註解標記"
        )
        normal_idx = content.index('正常 stream 完成')
        normal_block = content[normal_idx:normal_idx + 2000]
        assert '_heroSlotReserved' in normal_block, (
            "search-flow.js result 事件正常 stream 路徑缺少 _heroSlotReserved 處理 — "
            "A7-Prod Hero slot 最終命運由 result 事件決定"
        )
        # 驗證包含 Flip 移除邏輯（playHeroRemove）
        assert 'playHeroRemove' in normal_block, (
            "search-flow.js result 事件正常 stream 路徑缺少 playHeroRemove — "
            "A7-Prod 無 actressProfile 時必須 Flip 移除 Hero placeholder"
        )

    def test_result_event_allFailed_fallback_handles_hero_slot(self):
        """search-flow.js result 事件 allFailed+fallback 路徑處理 _heroSlotReserved"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        # allFailed fallback 路徑在 "Issue 1: Fallback 路徑" 附近
        assert 'Issue 1: Fallback' in content, (
            "search-flow.js 缺少 allFailed fallback 路徑的註解標記"
        )
        fb_idx = content.index('Issue 1: Fallback')
        fb_block = content[fb_idx:fb_idx + 2000]
        assert '_heroSlotReserved' in fb_block, (
            "search-flow.js result 事件 allFailed+fallback 路徑缺少 _heroSlotReserved 處理 — "
            "A7-Prod fallback 替換結果時必須處理 Hero slot"
        )

    def test_result_event_allFailed_no_fallback_cleans_hero_slot(self):
        """search-flow.js result 事件全失敗無 fallback 路徑清理 _heroSlotReserved"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        # 全失敗無 fallback 路徑在 "全部失敗且無 fallback" 附近
        assert '全部失敗且無 fallback' in content, (
            "search-flow.js 缺少全失敗無 fallback 路徑的註解標記"
        )
        nf_idx = content.index('全部失敗且無 fallback')
        nf_block = content[nf_idx:nf_idx + 500]
        assert '_heroSlotReserved' in nf_block, (
            "search-flow.js result 事件全失敗無 fallback 路徑缺少 _heroSlotReserved 清理 — "
            "A7-Prod 切到 error state 前必須清理 Hero slot"
        )


class TestShowcaseAnimationsGuard:
    """B5 守衛 — Showcase GSAP 基礎設施落地

    確認 animations.js 存在且結構正確、showcase.html 載入順序正確、
    grid 卡片有 data-flip-id、不重複載入 Flip CDN。
    """

    ANIMATIONS_JS = PROJECT_ROOT / "web/static/js/pages/showcase/animations.js"
    SHOWCASE_HTML = PROJECT_ROOT / "web/templates/showcase.html"

    def test_animations_js_exists(self):
        """web/static/js/pages/showcase/animations.js 檔案存在"""
        assert self.ANIMATIONS_JS.exists(), (
            "showcase/animations.js 不存在 — "
            "B5 必須建立 ShowcaseAnimations 動畫模組骨架"
        )

    def test_animations_js_has_iife(self):
        """animations.js 包含 IIFE 封裝 + window.ShowcaseAnimations 暴露"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert "'use strict'" in content or '"use strict"' in content, (
            "showcase/animations.js 缺少 'use strict' — "
            "B5 IIFE 必須啟用嚴格模式"
        )
        assert 'window.ShowcaseAnimations' in content, (
            "showcase/animations.js 缺少 window.ShowcaseAnimations — "
            "B5 必須暴露全域物件供 core.js 呼叫"
        )

    def test_animations_js_has_should_skip(self):
        """animations.js 包含 prefersReducedMotion 檢查"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'prefersReducedMotion' in content, (
            "showcase/animations.js 缺少 prefersReducedMotion — "
            "B5 shouldSkip() 必須檢查 Reduced Motion 偏好"
        )

    def test_animations_js_has_all_method_stubs(self):
        """animations.js 包含全部 6 個方法"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        methods = [
            'playEntry', 'playFlipReorder', 'playFlipFilter',
            'captureFlipState', 'capturePositions',
            'playModeCrossfade',
        ]
        missing = [m for m in methods if m not in content]
        assert not missing, (
            f"showcase/animations.js 缺少方法: {', '.join(missing)} — "
            "B5 必須包含全部 6 個方法"
        )

    def test_animations_js_registers_flip(self):
        """animations.js 包含 registerPlugin(Flip) 註冊"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'registerPlugin(Flip)' in content, (
            "showcase/animations.js 缺少 registerPlugin(Flip) — "
            "B5 DOMContentLoaded 內必須註冊 Flip plugin"
        )

    def test_animations_js_registers_custom_ease(self):
        """animations.js 包含 showcaseSettle CustomEase 註冊"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'showcaseSettle' in content, (
            "showcase/animations.js 缺少 showcaseSettle — "
            "B5 必須註冊 showcase 專用 CustomEase"
        )

    def test_showcase_html_loads_animations_before_core(self):
        """showcase.html 載入 animations.js 且在 core.js 之前"""
        content = self.SHOWCASE_HTML.read_text(encoding='utf-8')
        lines = content.split('\n')
        anim_line = None
        core_line = None
        for i, line in enumerate(lines, 1):
            if 'animations.js' in line and '<script' in line:
                anim_line = i
            if 'core.js' in line and '<script' in line:
                core_line = i
        assert anim_line is not None, (
            "showcase.html 缺少 animations.js script tag — "
            "B5 必須在 extra_js block 載入 animations.js"
        )
        assert core_line is not None, (
            "showcase.html 缺少 core.js script tag"
        )
        assert anim_line < core_line, (
            f"showcase.html animations.js (L{anim_line}) 必須在 core.js (L{core_line}) 之前 — "
            "B5 載入順序：animations.js → core.js"
        )

    def test_showcase_html_has_flip_id(self):
        """showcase.html grid 卡片包含 data-flip-id 屬性"""
        content = self.SHOWCASE_HTML.read_text(encoding='utf-8')
        assert 'data-flip-id' in content, (
            "showcase.html 缺少 data-flip-id — "
            "B5 .av-card-preview 必須有 :data-flip-id 供 Flip plugin 追蹤"
        )

    def test_showcase_html_no_duplicate_flip_cdn(self):
        """showcase.html 不重複載入 Flip.min.js（base.html 已全站載入）"""
        content = self.SHOWCASE_HTML.read_text(encoding='utf-8')
        assert 'Flip.min.js' not in content, (
            "showcase.html 不應載入 Flip.min.js — "
            "base.html 已全站載入 Flip CDN，不應重複"
        )

    # --- B6 守衛 ---
    CORE_JS = PROJECT_ROOT / "web/static/js/pages/showcase/core.js"

    def test_play_entry_not_placeholder(self):
        """B6: playEntry 已從 placeholder 替換為完整實作"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'gsap.killTweensOf' in content, (
            "showcase/animations.js playEntry 缺少 gsap.killTweensOf — "
            "B6 必須包含 C4 清除舊動畫"
        )
        assert 'getBoundingClientRect' in content, (
            "showcase/animations.js playEntry 缺少 getBoundingClientRect — "
            "B6 必須包含 viewport 分流邏輯"
        )
        assert 'gsap.set' in content, (
            "showcase/animations.js playEntry 缺少 gsap.set — "
            "B6 必須包含 offscreen 瞬間到位 + Reduced Motion 降級"
        )

    def test_core_js_calls_play_entry(self):
        """B6: core.js 包含 playEntry 呼叫"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        assert 'playEntry' in content, (
            "showcase/core.js 缺少 playEntry — "
            "B6 init() 必須呼叫 ShowcaseAnimations.playEntry"
        )
        assert 'ShowcaseAnimations' in content, (
            "showcase/core.js 缺少 ShowcaseAnimations — "
            "B6 必須透過 window.ShowcaseAnimations 全域物件呼叫"
        )

    def test_core_js_play_entry_has_mode_guard(self):
        """B6: core.js playEntry 呼叫包含 mode guard"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 找到包含 playEntry 的行，往上搜尋最近的 if 條件
        play_entry_indices = [i for i, line in enumerate(lines) if 'playEntry' in line]
        assert play_entry_indices, (
            "showcase/core.js 找不到 playEntry — B6 必須呼叫動畫"
        )
        found_mode_guard = False
        for idx in play_entry_indices:
            # 檢查前 5 行內是否包含 mode 檢查
            start = max(0, idx - 5)
            nearby = '\n'.join(lines[start:idx + 1])
            if 'mode' in nearby:
                found_mode_guard = True
                break
        assert found_mode_guard, (
            "showcase/core.js playEntry 附近缺少 mode guard — "
            "B6 必須在 mode === 'grid' 時才觸發動畫"
        )

    # --- B7 守衛 ---

    def test_capture_flip_state_not_placeholder(self):
        """B7: captureFlipState 已從 placeholder 替換為完整實作"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'Flip.getState' in content, (
            "showcase/animations.js captureFlipState 缺少 Flip.getState — "
            "B7 必須包含實際捕獲邏輯"
        )
        assert '.av-card-preview' in content, (
            "showcase/animations.js captureFlipState 缺少 .av-card-preview — "
            "B7 必須查詢卡片元素"
        )

    def test_animations_js_has_capture_positions(self):
        """B12: animations.js 包含 capturePositions 手動位置捕獲方法"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 用 brace counting 提取 capturePositions 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            if not in_method and 'capturePositions' in line and 'function' in line:
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, (
            "showcase/animations.js 缺少 capturePositions — "
            "B12 必須新增手動位置捕獲方法"
        )
        assert 'getBoundingClientRect' in method_body, (
            "showcase/animations.js capturePositions 缺少 getBoundingClientRect — "
            "B12 必須用原生 DOM API 捕獲位置"
        )
        assert 'data-flip-id' in method_body, (
            "showcase/animations.js capturePositions 缺少 data-flip-id — "
            "B12 必須用 data-flip-id 作為卡片識別 key"
        )

    def test_play_flip_reorder_not_placeholder(self):
        """B12: playFlipReorder 使用手動 gsap.fromTo 取代 Flip（修正排序閃爍）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 用 brace counting 提取 playFlipReorder 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            if not in_method and 'playFlipReorder' in line and 'function' in line:
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, (
            "showcase/animations.js 找不到 playFlipReorder 方法定義"
        )
        assert '.fromTo' in method_body, (
            "showcase/animations.js playFlipReorder 缺少 fromTo — "
            "B12 必須用手動位置追蹤取代 Flip reorder"
        )
        assert 'killTweensOf' in method_body, (
            "showcase/animations.js playFlipReorder 缺少 killTweensOf — "
            "B12 必須包含 C18 中斷進行中動畫"
        )
        assert 'clearProps' in method_body, (
            "showcase/animations.js playFlipReorder 缺少 clearProps — "
            "B12 必須在動畫後恢復 CSS hover 效果"
        )

    def test_core_js_sort_helper_uses_flip_reorder(self):
        """B15: core.js 排序動畫恢復 Flip reorder（加 flip-guard 修正 CSS transition 衝突）"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 用 brace counting 提取 _sortWithFlip 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and '_sortWithFlip' in stripped and 'changeFn' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, (
            "showcase/core.js 找不到 _sortWithFlip 方法定義"
        )
        assert 'capturePositions' in method_body, (
            "showcase/core.js _sortWithFlip 缺少 capturePositions — "
            "B15 排序前必須捕獲卡片位置快照"
        )
        assert 'playFlipReorder' in method_body, (
            "showcase/core.js _sortWithFlip 缺少 playFlipReorder — "
            "B15 排序後必須用 Flip reorder 洗牌動畫"
        )
        assert 'flip-guard' in method_body, (
            "showcase/core.js _sortWithFlip 缺少 flip-guard — "
            "B15 Flip 期間必須加 flip-guard 關掉 CSS transition"
        )

    def test_core_js_on_sort_change_has_mode_guard(self):
        """B13: core.js 排序動畫包含 mode guard"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 用 brace counting 提取 _sortWithFlip 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and '_sortWithFlip' in stripped and 'changeFn' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, (
            "showcase/core.js 找不到 _sortWithFlip 方法定義"
        )
        assert 'mode' in method_body, (
            "showcase/core.js _sortWithFlip 缺少 mode guard — "
            "B13 必須在 mode === 'grid' 時才觸發排序動畫"
        )

    def test_sort_with_flip_preserves_page(self):
        """B7: _sortWithFlip 保存並恢復頁碼（避免排序動畫在第 2 頁之後退化）"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 用 brace counting 提取 _sortWithFlip 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and '_sortWithFlip(' in stripped and 'changeFn' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert 'savedPage' in method_body or 'saved_page' in method_body or 'savePage' in method_body, (
            "showcase/core.js _sortWithFlip 缺少頁碼保存 — "
            "排序操作不應重置頁碼，必須在 changeFn() 前後保存/恢復 page"
        )
        assert 'updatePagination' in method_body, (
            "showcase/core.js _sortWithFlip 缺少 updatePagination — "
            "恢復頁碼後必須重新分頁以 clamp 超出範圍的頁碼"
        )

    # --- B8 守衛 ---

    def test_play_flip_filter_not_placeholder(self):
        """B8: playFlipFilter 已從 placeholder 替換為完整實作"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'Flip.from' in content, (
            "showcase/animations.js playFlipFilter 缺少 Flip.from — "
            "B8 必須包含 Flip 動畫核心"
        )
        assert 'onEnter' in content, (
            "showcase/animations.js playFlipFilter 缺少 onEnter — "
            "B8 必須包含進場動畫回調"
        )
        assert 'onLeave' in content, (
            "showcase/animations.js playFlipFilter 缺少 onLeave — "
            "B8 必須包含出場動畫回調"
        )
        assert 'clearProps' in content, (
            "showcase/animations.js playFlipFilter 缺少 clearProps — "
            "B8 必須在動畫後恢復 CSS hover 效果"
        )

    def test_core_js_has_animate_filter_method(self):
        """B8: core.js 包含 _animateFilter 共用篩選動畫方法"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        assert '_animateFilter' in content, (
            "showcase/core.js 缺少 _animateFilter — "
            "B8 必須提供共用篩選動畫方法"
        )

    def test_core_js_on_search_change_calls_animate_filter(self):
        """B8: core.js onSearchChange 呼叫 _animateFilter"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 找到 onSearchChange 方法區塊
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            if 'onSearchChange' in line and ('(' in line or ':' in line):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert '_animateFilter' in method_body, (
            "showcase/core.js onSearchChange 缺少 _animateFilter — "
            "B8 必須透過共用方法觸發篩選動畫"
        )

    def test_core_js_search_from_metadata_calls_animate_filter(self):
        """B8: core.js searchFromMetadata 呼叫 _animateFilter 且不直接呼叫 applyFilterAndSort"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 找到 searchFromMetadata 方法定義（帶 { 的行）
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and 'searchFromMetadata' in stripped and '{' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert '_animateFilter' in method_body, (
            "showcase/core.js searchFromMetadata 缺少 _animateFilter — "
            "B8 必須透過共用方法觸發篩選動畫"
        )
        assert 'applyFilterAndSort' not in method_body, (
            "showcase/core.js searchFromMetadata 不應直接呼叫 applyFilterAndSort — "
            "B8 必須透過 _animateFilter 間接呼叫，避免繞過動畫攔截"
        )

    def test_core_js_animate_filter_has_mode_guard(self):
        """B8/B14: core.js _animateFilter 包含 mode guard"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 找到 _animateFilter 方法定義（帶 { 結尾的行）
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and '_animateFilter' in stripped and '{' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert 'mode' in method_body, (
            "showcase/core.js _animateFilter 缺少 mode guard — "
            "B8 必須在 mode === 'grid' 時才觸發篩選動畫"
        )

    # --- B14 守衛 ---

    def test_core_js_animate_filter_uses_flip_filter(self):
        """B15: core.js 篩選動畫恢復 Flip filter（加 flip-guard 修正 CSS transition 衝突）"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # brace-counting 提取 _animateFilter 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and '_animateFilter' in stripped and '{' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, "showcase/core.js 找不到 _animateFilter 方法定義"
        assert 'captureFlipState' in method_body, (
            "showcase/core.js _animateFilter 缺少 captureFlipState — "
            "B15 篩選前必須捕獲 Flip 狀態快照"
        )
        assert 'playFlipFilter' in method_body, (
            "showcase/core.js _animateFilter 缺少 playFlipFilter — "
            "B15 篩選後必須用 Flip 進出場動畫"
        )
        assert 'flip-guard' in method_body, (
            "showcase/core.js _animateFilter 缺少 flip-guard — "
            "B15 Flip 期間必須加 flip-guard 關掉 CSS transition"
        )

    def test_core_js_animate_filter_has_generation_guard(self):
        """B14: core.js _animateFilter 使用 generation token 防止 stale callback"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and '_animateFilter' in stripped and '{' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, "showcase/core.js 找不到 _animateFilter 方法定義"
        assert '_animGeneration' in method_body, (
            "showcase/core.js _animateFilter 缺少 _animGeneration guard — "
            "B14 快速打字時必須用 generation token 使舊 callback 失效"
        )

    # --- B9 守衛 ---

    def test_core_js_has_animate_page_change(self):
        """B9: core.js 包含 _animatePageChange 方法"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        assert '_animatePageChange' in content, (
            "showcase/core.js 缺少 _animatePageChange — "
            "B9 必須提供分頁動畫攔截方法"
        )

    def test_core_js_animate_page_change_has_mode_guard(self):
        """B9: core.js _animatePageChange 包含 mode guard"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 用 brace counting 提取 _animatePageChange 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and '_animatePageChange' in stripped and '{' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert 'mode' in method_body, (
            "showcase/core.js _animatePageChange 缺少 mode guard — "
            "B9 必須在非 grid mode 時直接換頁不播動畫"
        )

    def test_core_js_prev_next_page_call_animate_page_change(self):
        """B9: core.js prevPage/nextPage 呼叫 _animatePageChange"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 提取 prevPage 方法體
        for method_name in ['prevPage', 'nextPage']:
            in_method = False
            method_lines = []
            brace_count = 0
            for line in lines:
                stripped = line.strip()
                if not in_method and method_name in stripped and '{' in stripped and stripped.endswith('{'):
                    in_method = True
                    brace_count = 0
                if in_method:
                    method_lines.append(line)
                    brace_count += line.count('{') - line.count('}')
                    if brace_count <= 0 and len(method_lines) > 1:
                        break
            method_body = '\n'.join(method_lines)
            assert '_animatePageChange' in method_body, (
                f"showcase/core.js {method_name} 缺少 _animatePageChange — "
                "B9 必須透過 _animatePageChange 觸發分頁動畫"
            )

    def test_core_js_uses_sync_scroll_to(self):
        """B9: core.js 使用同步 scrollTo(0, 0) 而非 smooth scroll"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        assert 'scrollTo(0, 0)' in content, (
            "showcase/core.js 缺少 scrollTo(0, 0) — "
            "B9 翻頁必須使用同步捲動"
        )
        lines = content.split('\n')
        # 確認 _animatePageChange 和 goToPage 方法體不包含 behavior（排除 smooth scroll）
        for method_name in ['_animatePageChange', 'goToPage']:
            in_method = False
            method_lines = []
            brace_count = 0
            for line in lines:
                stripped = line.strip()
                if not in_method and method_name in stripped and '{' in stripped and stripped.endswith('{'):
                    in_method = True
                    brace_count = 0
                if in_method:
                    method_lines.append(line)
                    brace_count += line.count('{') - line.count('}')
                    if brace_count <= 0 and len(method_lines) > 1:
                        break
            method_body = '\n'.join(method_lines)
            assert 'behavior' not in method_body, (
                f"showcase/core.js {method_name} 包含 behavior — "
                "B9 翻頁不應使用 smooth scroll，避免與 stagger-in 時序衝突"
            )

    # --- B13 守衛 ---

    def test_core_js_animate_page_change_uses_play_entry(self):
        """B13: core.js _animatePageChange 改用 playEntry（取代 playPageOut/playPageIn 鏈）"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 用 brace counting 提取 _animatePageChange 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and '_animatePageChange' in stripped and '{' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, (
            "showcase/core.js 找不到 _animatePageChange 方法定義"
        )
        assert 'playEntry' in method_body, (
            "showcase/core.js _animatePageChange 缺少 playEntry — "
            "B13 翻頁必須用 playEntry stagger fade-in"
        )
        assert 'playPageOut' not in method_body, (
            "showcase/core.js _animatePageChange 仍包含 playPageOut — "
            "B13 應移除離場動畫（state-first + playEntry）"
        )
        assert 'playPageIn' not in method_body, (
            "showcase/core.js _animatePageChange 仍包含 playPageIn — "
            "B13 應移除進場動畫（改用 playEntry）"
        )

    def test_core_js_animate_page_change_no_on_complete_trap(self):
        """B13: core.js _animatePageChange 不將 state mutation 困在 onComplete callback"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 用 brace counting 提取 _animatePageChange 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and '_animatePageChange' in stripped and '{' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, (
            "showcase/core.js 找不到 _animatePageChange 方法定義"
        )
        assert 'onComplete' not in method_body, (
            "showcase/core.js _animatePageChange 仍包含 onComplete — "
            "B13 必須 state-first，不可將 page mutation 困在回調中"
        )

    def test_core_js_has_anim_generation_guard(self):
        """B13: core.js 包含動畫排程 generation token 防止 stale callback"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        assert '_animGeneration' in content, (
            "showcase/core.js 缺少 _animGeneration — "
            "B13 必須用 generation token 防止高頻互動的 stale deferred callback"
        )

    def test_core_js_sort_helper_has_generation_guard(self):
        """B13: core.js _sortWithFlip 使用 generation token 防止 stale callback"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and '_sortWithFlip' in stripped and 'changeFn' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, "showcase/core.js 找不到 _sortWithFlip 方法定義"
        assert '_animGeneration' in method_body, (
            "showcase/core.js _sortWithFlip 缺少 _animGeneration guard — "
            "B13 高頻排序時必須用 generation token 使舊 callback 失效"
        )

    def test_core_js_animate_page_change_has_generation_guard(self):
        """B13: core.js _animatePageChange 使用 generation token 防止 stale callback"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if (not in_method and '_animatePageChange' in stripped
                    and ('direction' in stripped or 'targetPage' in stripped)
                    and '{' in stripped):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, "showcase/core.js 找不到 _animatePageChange 方法定義"
        assert '_animGeneration' in method_body, (
            "showcase/core.js _animatePageChange 缺少 _animGeneration guard — "
            "B13 高頻翻頁時必須用 generation token 使舊 callback 失效"
        )

    def test_core_js_cleanup_invalidates_generation(self):
        """B13: core.js cleanup 遞增 _animGeneration 使離頁時 pending callback 失效"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # Find cleanup block
        cleanup_idx = None
        for i, line in enumerate(lines):
            if 'cleanup' in line and ('=>' in line or 'function' in line):
                cleanup_idx = i
                break
        assert cleanup_idx is not None, (
            "showcase/core.js 找不到 cleanup callback"
        )
        # Check nearby lines (within cleanup block, roughly 10 lines)
        nearby = '\n'.join(lines[cleanup_idx:cleanup_idx + 10])
        assert '_animGeneration' in nearby, (
            "showcase/core.js cleanup 缺少 _animGeneration 遞增 — "
            "B13 離頁時必須使 pending deferred callback 失效"
        )

    # --- B15 守衛 ---

    def test_theme_css_has_flip_guard_rule(self):
        """B15: theme.css 包含 .flip-guard 規則，Flip 期間關掉 CSS transition"""
        theme_css = (PROJECT_ROOT / "web/static/css/theme.css").read_text(encoding='utf-8')
        assert 'flip-guard' in theme_css, (
            "theme.css 缺少 .flip-guard 規則 — "
            "B15 必須在 Flip 期間關掉 .av-card-preview 的 transition: transform"
        )
        assert 'transform: none' in theme_css, (
            "theme.css .flip-guard 缺少 transform: none — "
            "B15 必須在 Flip 期間關掉 hover 的 transform"
        )

    def test_core_js_sort_adds_flip_guard_class(self):
        """B15: core.js _sortWithFlip 在 Flip 期間管理 flip-guard class"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # brace-counting 提取 _sortWithFlip 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and '_sortWithFlip' in stripped and 'changeFn' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, "showcase/core.js 找不到 _sortWithFlip 方法定義"
        assert 'flip-guard' in method_body, (
            "showcase/core.js _sortWithFlip 缺少 flip-guard 管理 — "
            "B15 Flip 期間必須加 flip-guard class 關掉 CSS transition"
        )

    def test_core_js_filter_adds_flip_guard_class(self):
        """B15: core.js _animateFilter 在 Flip 期間管理 flip-guard class"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # brace-counting 提取 _animateFilter 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and '_animateFilter' in stripped and '{' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, "showcase/core.js 找不到 _animateFilter 方法定義"
        assert 'flip-guard' in method_body, (
            "showcase/core.js _animateFilter 缺少 flip-guard 管理 — "
            "B15 Flip 期間必須加 flip-guard class 關掉 CSS transition"
        )

    def test_core_js_page_change_cleans_flip_guard(self):
        """B15: core.js _animatePageChange 清理殘留 flip-guard 但不使用 Flip 動畫"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # brace-counting 提取 _animatePageChange 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            stripped = line.strip()
            if not in_method and '_animatePageChange' in stripped and '{' in stripped and stripped.endswith('{'):
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, "showcase/core.js 找不到 _animatePageChange 方法定義"
        assert 'flip-guard' in method_body, (
            "showcase/core.js _animatePageChange 缺少 flip-guard 清理 — "
            "翻頁時必須清理 sort/filter 動畫被打斷後殘留的 flip-guard"
        )
        assert 'capturePositions' not in method_body, (
            "showcase/core.js _animatePageChange 不應包含 capturePositions — "
            "翻頁用 playEntry，不使用 Flip 排序動畫"
        )
        assert 'captureFlipState' not in method_body, (
            "showcase/core.js _animatePageChange 不應包含 captureFlipState — "
            "翻頁用 playEntry，不使用 Flip 篩選動畫"
        )

    def test_play_flip_filter_returns_tweens(self):
        """B15: playFlipFilter 的 onEnter/onLeave 必須 return tween 供 Flip timeline 管理"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # brace-counting 提取 playFlipFilter 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            if not in_method and 'playFlipFilter' in line and 'function' in line:
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        assert method_lines, "showcase/animations.js 找不到 playFlipFilter 方法定義"
        assert 'return gsap.fromTo' in method_body, (
            "showcase/animations.js playFlipFilter onEnter 缺少 return — "
            "必須 return tween 供 Flip timeline 管理進場動畫"
        )
        assert 'return gsap.to' in method_body, (
            "showcase/animations.js playFlipFilter onLeave 缺少 return — "
            "必須 return tween 供 Flip timeline 管理出場動畫"
        )

    # --- B10 守衛 ---

    def test_play_mode_crossfade_not_placeholder(self):
        """B10: playModeCrossfade 已從 placeholder 替換為完整實作"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 用 brace counting 提取 playModeCrossfade 方法體
        in_method = False
        method_lines = []
        brace_count = 0
        for line in lines:
            if not in_method and 'playModeCrossfade' in line and 'function' in line:
                in_method = True
                brace_count = 0
            if in_method:
                method_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and len(method_lines) > 1:
                    break
        method_body = '\n'.join(method_lines)
        # 確認不是 placeholder
        body_lines = [l.strip() for l in method_lines[1:] if l.strip() and l.strip() != '},' and l.strip() != '}']
        assert not (len(body_lines) == 1 and body_lines[0] == 'return null;'), (
            "showcase/animations.js playModeCrossfade 仍是 placeholder — "
            "B10 必須替換為完整實作"
        )
        assert 'gsap.fromTo' in method_body, (
            "showcase/animations.js playModeCrossfade 缺少 gsap.fromTo — "
            "B10 必須包含 opacity crossfade 動畫"
        )
        assert 'clearProps' in method_body, (
            "showcase/animations.js playModeCrossfade 缺少 clearProps — "
            "B10 必須在動畫結束後清除 inline opacity"
        )

    def test_core_js_switch_mode_calls_play_mode_crossfade(self):
        """B10: core.js switchMode 包含 playModeCrossfade 呼叫"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        assert 'playModeCrossfade' in content, (
            "showcase/core.js 缺少 playModeCrossfade — "
            "B10 switchMode 必須呼叫 ShowcaseAnimations.playModeCrossfade"
        )

    def test_core_js_switch_mode_uses_optional_chaining(self):
        """B10: core.js switchMode 使用 optional chaining 安全呼叫"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        assert 'ShowcaseAnimations?.playModeCrossfade?.(' in content, (
            "showcase/core.js 缺少 ShowcaseAnimations?.playModeCrossfade?.( — "
            "B10 必須使用 optional chaining 確保 animations.js 未載入時安全降級"
        )


class TestMotionLabShowcase:
    """B11 守衛 — Motion Lab Showcase demo 完整性

    確認 Motion Lab 頁面包含 Showcase tab 及所有 demo 方法，
    涵蓋 B1-B4 在 Motion Lab 新增的功能。
    """

    MOTION_LAB_HTML = PROJECT_ROOT / "web/templates/motion_lab.html"
    MOTION_LAB_JS = PROJECT_ROOT / "web/static/js/pages/motion-lab.js"

    def test_motion_lab_html_has_showcase_tab(self):
        """motion_lab.html 包含 showcase tab 按鈕"""
        content = self.MOTION_LAB_HTML.read_text(encoding='utf-8')
        assert "showcase" in content.lower(), (
            "motion_lab.html 缺少 showcase tab — "
            "B1-B4 必須在 Motion Lab 新增 Showcase 分頁"
        )
        assert "tab === 'showcase'" in content, (
            "motion_lab.html 缺少 tab === 'showcase' 條件 — "
            "Showcase tab 必須有 Alpine tab 切換邏輯"
        )

    def test_motion_lab_js_has_play_showcase_entry(self):
        """motion-lab.js 包含 playShowcaseEntry 方法"""
        content = self.MOTION_LAB_JS.read_text(encoding='utf-8')
        assert 'playShowcaseEntry' in content, (
            "motion-lab.js 缺少 playShowcaseEntry — "
            "B1 必須在 Motion Lab 提供 Showcase 初始載入 demo"
        )

    def test_motion_lab_js_has_play_flip_reorder(self):
        """motion-lab.js 包含 playFlipReorder 方法"""
        content = self.MOTION_LAB_JS.read_text(encoding='utf-8')
        assert 'playFlipReorder' in content, (
            "motion-lab.js 缺少 playFlipReorder — "
            "B2 必須在 Motion Lab 提供排序洗牌 demo"
        )

    def test_motion_lab_js_has_play_flip_filter(self):
        """motion-lab.js 包含 playFlipFilter 方法"""
        content = self.MOTION_LAB_JS.read_text(encoding='utf-8')
        assert 'playFlipFilter' in content, (
            "motion-lab.js 缺少 playFlipFilter — "
            "B3 必須在 Motion Lab 提供篩選進出場 demo"
        )

    def test_motion_lab_js_has_play_page_transition(self):
        """motion-lab.js 包含 playPageTransition 方法（整合 playPageOut + playPageIn）"""
        content = self.MOTION_LAB_JS.read_text(encoding='utf-8')
        assert 'playPageTransition' in content, (
            "motion-lab.js 缺少 playPageTransition — "
            "B4 必須在 Motion Lab 提供分頁切換 demo"
        )


# ====================================================================
# D1 Guards: 錯誤訊息收斂 + console.log 清理
# ====================================================================

class TestSearchErrorMessageGuard:
    """D1 守衛：search 頁面 JS 的 alert / errorText 不可暴露 err.message 技術細節"""

    SEARCH_JS_DIR = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'search'

    def _collect_js_files(self):
        """收集 search 目錄下所有 .js 檔案（含子目錄）"""
        return list(self.SEARCH_JS_DIR.rglob('*.js'))

    @staticmethod
    def _is_console_or_throw(line: str) -> bool:
        """排除 console.error / console.warn / throw 中的合法使用"""
        stripped = line.strip()
        if stripped.startswith('console.error') or stripped.startswith('console.warn'):
            return True
        if stripped.startswith('throw '):
            return True
        # 也排除 JS 註解行
        if stripped.startswith('//'):
            return True
        return False

    def test_no_err_message_in_alert(self):
        """alert() 內不可含 err.message / error.message / result.error"""
        pattern = r'alert\s*\([^)]*(?:err\.message|error\.message|result\.error)'
        all_violations = []
        for js_file in self._collect_js_files():
            violations = find_pattern_in_file(
                js_file, pattern,
                exclude_lines=lambda line, _: self._is_console_or_throw(line)
            )
            for line_num, line_content in violations:
                all_violations.append(f"  {js_file.relative_to(PROJECT_ROOT)}:{line_num}: {line_content}")

        assert not all_violations, (
            "D1 守衛違規：alert() 內暴露技術錯誤訊息\n"
            + "\n".join(all_violations)
            + "\n\n修正：alert 只顯示友善中文提示，技術細節降級到 console.error"
        )

    def test_no_err_message_in_errorText(self):
        """this.errorText = 內不可含 err.message / error.message"""
        pattern = r'this\.errorText\s*=\s*.*(?:err\.message|error\.message)'
        all_violations = []
        for js_file in self._collect_js_files():
            violations = find_pattern_in_file(
                js_file, pattern,
                exclude_lines=lambda line, _: self._is_console_or_throw(line)
            )
            for line_num, line_content in violations:
                all_violations.append(f"  {js_file.relative_to(PROJECT_ROOT)}:{line_num}: {line_content}")

        assert not all_violations, (
            "D1 守衛違規：errorText 暴露技術錯誤訊息\n"
            + "\n".join(all_violations)
            + "\n\n修正：errorText 只顯示友善中文提示，技術細節降級到 console.error"
        )


class TestSearchConsoleLogGuard:
    """D1 守衛：search 頁面程式碼不可含 console.log"""

    SEARCH_JS_DIR = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'search'
    SEARCH_HTML = PROJECT_ROOT / 'web' / 'templates' / 'search.html'

    def _collect_scan_files(self):
        """收集所有需掃描的檔案：search/*.js + search.html"""
        files = list(self.SEARCH_JS_DIR.rglob('*.js'))
        if self.SEARCH_HTML.exists():
            files.append(self.SEARCH_HTML)
        return files

    @staticmethod
    def _is_comment_line(line: str, _line_num: int) -> bool:
        """排除 JS 註解行（// 開頭）和 HTML 註解"""
        stripped = line.strip()
        if stripped.startswith('//'):
            return True
        if '<!--' in stripped:
            return True
        return False

    def test_no_console_log(self):
        """search 頁面程式碼不可含 console.log("""
        pattern = r'console\.log\s*\('
        all_violations = []
        for scan_file in self._collect_scan_files():
            violations = find_pattern_in_file(
                scan_file, pattern,
                exclude_lines=self._is_comment_line
            )
            for line_num, line_content in violations:
                all_violations.append(f"  {scan_file.relative_to(PROJECT_ROOT)}:{line_num}: {line_content}")

        assert not all_violations, (
            "D1 守衛違規：search 頁面殘留 console.log\n"
            + "\n".join(all_violations)
            + "\n\n修正：移除 console.log，保留 console.error / console.warn"
        )


class TestLightboxAnimationGuard:
    """C18 守衛：Lightbox interrupt 必須用 getById kill 整個 timeline，不可只 killTweensOf 元素"""

    SEARCH_GRID_MODE = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'search' / 'state' / 'grid-mode.js'
    SEARCH_NAVIGATION = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'search' / 'state' / 'navigation.js'
    SHOWCASE_CORE = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'core.js'

    @staticmethod
    def _read_file(path):
        return path.read_text(encoding='utf-8')

    @staticmethod
    def _extract_function(content, func_name):
        """粗略擷取函數內容（從函數名到下一個同級函數或檔案結尾）"""
        # 找到函數定義行
        pattern = re.compile(r'^\s*' + re.escape(func_name) + r'\s*\(', re.MULTILINE)
        match = pattern.search(content)
        if not match:
            return ''
        start = match.start()
        # 取到後續 2000 字元（足夠涵蓋函數體）
        return content[start:start + 3000]

    def test_prev_next_use_getById_not_killTweensOf_search(self):
        """search/grid-mode.js 的 prevLightboxVideo/nextLightboxVideo 用 getById kill"""
        content = self._read_file(self.SEARCH_GRID_MODE)
        for func in ['prevLightboxVideo', 'nextLightboxVideo']:
            body = self._extract_function(content, func)
            assert body, f"{func} 函數未找到 in grid-mode.js"
            assert 'getById' in body, (
                f"C18 守衛違規：search grid-mode.js {func} 缺少 getById kill\n"
                "修正：用 gsap.getById()?.kill() 取代 killTweensOf"
            )
            # 確認 kill lightboxOpen（進場動畫未完也要打斷）+ 無 killTweensOf
            interrupt_section = body[:500]
            assert "lightboxOpen" in interrupt_section, (
                f"C18 守衛違規：search grid-mode.js {func} 缺少 kill lightboxOpen timeline\n"
                "修正：加 gsap.getById('lightboxOpen')?.kill()"
            )
            assert 'killTweensOf' not in interrupt_section, (
                f"C18 守衛違規：search grid-mode.js {func} 仍使用 killTweensOf\n"
                "修正：改用 gsap.getById()?.kill()"
            )

    def test_prev_next_use_getById_not_killTweensOf_showcase(self):
        """showcase/core.js 的 prevLightboxVideo/nextLightboxVideo 用 getById kill"""
        content = self._read_file(self.SHOWCASE_CORE)
        for func in ['prevLightboxVideo', 'nextLightboxVideo']:
            body = self._extract_function(content, func)
            assert body, f"{func} 函數未找到 in showcase/core.js"
            assert 'getById' in body, (
                f"C18 守衛違規：showcase/core.js {func} 缺少 getById kill\n"
                "修正：用 gsap.getById()?.kill() 取代 killTweensOf"
            )
            # 確認 kill showcaseLightboxOpen（進場動畫未完也要打斷）+ 無 killTweensOf
            interrupt_section = body[:500]
            assert "showcaseLightboxOpen" in interrupt_section, (
                f"C18 守衛違規：showcase/core.js {func} 缺少 kill showcaseLightboxOpen timeline\n"
                "修正：加 gsap.getById('showcaseLightboxOpen')?.kill()"
            )
            assert 'killTweensOf' not in interrupt_section, (
                f"C18 守衛違規：showcase/core.js {func} 仍使用 killTweensOf\n"
                "修正：改用 gsap.getById()?.kill()"
            )

    def test_esc_calls_closeLightbox_search(self):
        """search/navigation.js ESC 分支呼叫 closeLightbox（closeLightbox 內部處理 getById kill）"""
        content = self._read_file(self.SEARCH_NAVIGATION)
        body = self._extract_function(content, 'handleKeydown')
        assert body, "handleKeydown 函數未找到 in navigation.js"
        esc_idx = body.find('Escape')
        assert esc_idx >= 0, "handleKeydown 中未找到 Escape 分支"
        esc_section = body[esc_idx:esc_idx + 300]
        assert 'closeLightbox' in esc_section, (
            "C18 守衛違規：search navigation.js ESC 分支未呼叫 closeLightbox\n"
            "修正：ESC 應呼叫 closeLightbox() 統一處理 kill + cleanup"
        )

    def test_esc_calls_closeLightbox_showcase(self):
        """showcase/core.js ESC 分支呼叫 closeLightbox（closeLightbox 內部處理 getById kill）"""
        content = self._read_file(self.SHOWCASE_CORE)
        body = self._extract_function(content, 'handleKeydown')
        assert body, "handleKeydown 函數未找到 in showcase/core.js"
        esc_idx = body.find('ESCAPE')
        assert esc_idx >= 0, "handleKeydown 中未找到 ESCAPE 分支"
        esc_section = body[esc_idx:esc_idx + 300]
        assert 'closeLightbox' in esc_section, (
            "C18 守衛違規：showcase/core.js ESC 分支未呼叫 closeLightbox\n"
            "修正：ESC 應呼叫 closeLightbox() 統一處理 kill + cleanup"
        )

    def test_closeLightbox_has_getById_kill_search(self):
        """search closeLightbox 自身包含 getById kill（instant close 需清理進行中動畫）"""
        content = self._read_file(self.SEARCH_GRID_MODE)
        body = self._extract_function(content, 'closeLightbox')
        assert body, "closeLightbox 函數未找到 in grid-mode.js"
        assert 'getById' in body, (
            "C18 守衛違規：search closeLightbox 缺少 getById kill\n"
            "修正：instant close 需 kill 進行中的 lightbox timeline"
        )

    def test_closeLightbox_has_getById_kill_showcase(self):
        """showcase closeLightbox 自身包含 getById kill（instant close 需清理進行中動畫）"""
        content = self._read_file(self.SHOWCASE_CORE)
        body = self._extract_function(content, 'closeLightbox')
        assert body, "closeLightbox 函數未找到 in showcase/core.js"
        assert 'getById' in body, (
            "C18 守衛違規：showcase closeLightbox 缺少 getById kill\n"
            "修正：instant close 需 kill 進行中的 lightbox timeline"
        )

    def test_openLightbox_same_index_noop_search(self):
        """search/grid-mode.js openLightbox 有 same-index no-op guard"""
        content = self._read_file(self.SEARCH_GRID_MODE)
        body = self._extract_function(content, 'openLightbox')
        assert body, "openLightbox 函數未找到 in grid-mode.js"
        assert re.search(r'lightboxIndex\s*===\s*index', body), (
            "C18 守衛違規：search grid-mode.js openLightbox 缺少 same-index no-op\n"
            "修正：加入 if (this.lightboxOpen && this.lightboxIndex === index) return;"
        )

    def test_openLightbox_same_index_noop_showcase(self):
        """showcase/core.js openLightbox 有 same-index no-op guard"""
        content = self._read_file(self.SHOWCASE_CORE)
        body = self._extract_function(content, 'openLightbox')
        assert body, "openLightbox 函數未找到 in showcase/core.js"
        assert re.search(r'lightboxIndex\s*===\s*index', body), (
            "C18 守衛違規：showcase/core.js openLightbox 缺少 same-index no-op\n"
            "修正：加入 if (this.lightboxOpen && this.lightboxIndex === index) return;"
        )

    def test_openLightbox_switch_path_search(self):
        """search/grid-mode.js openLightbox 有 already-open switch 路徑"""
        content = self._read_file(self.SEARCH_GRID_MODE)
        body = self._extract_function(content, 'openLightbox')
        assert body, "openLightbox 函數未找到 in grid-mode.js"
        assert 'lightboxOpen' in body, "openLightbox 缺少 lightboxOpen 檢查"
        assert 'playLightboxSwitch' in body, (
            "C18 守衛違規：search grid-mode.js openLightbox 缺少 switch 路徑\n"
            "修正：lightbox 已開啟時應走 playLightboxSwitch 而非重播 open 動畫"
        )

    def test_openLightbox_switch_path_showcase(self):
        """showcase/core.js openLightbox 有 already-open switch 路徑"""
        content = self._read_file(self.SHOWCASE_CORE)
        body = self._extract_function(content, 'openLightbox')
        assert body, "openLightbox 函數未找到 in showcase/core.js"
        assert 'lightboxOpen' in body, "openLightbox 缺少 lightboxOpen 檢查"
        assert 'playLightboxSwitch' in body, (
            "C18 守衛違規：showcase/core.js openLightbox 缺少 switch 路徑\n"
            "修正：lightbox 已開啟時應走 playLightboxSwitch 而非重播 open 動畫"
        )

    def test_searchFromMetadata_sync_cleanup(self):
        """showcase/core.js searchFromMetadata 用 getById kill + 同步設定 lightboxOpen = false"""
        content = self._read_file(self.SHOWCASE_CORE)
        body = self._extract_function(content, 'searchFromMetadata')
        assert body, "searchFromMetadata 函數未找到 in showcase/core.js"
        assert 'getById' in body, (
            "C18 守衛違規：showcase/core.js searchFromMetadata 缺少 getById kill\n"
            "修正：用 gsap.getById kill 所有 showcase lightbox timeline"
        )
        # 確認 lightboxOpen = false 在函數體直接層級（非 callback）
        # 檢查 lightboxOpen = false 出現在 getById 之後
        getById_idx = body.find('getById')
        lightboxOpen_idx = body.find('lightboxOpen = false')
        assert lightboxOpen_idx > getById_idx, (
            "C18 守衛違規：searchFromMetadata 的 lightboxOpen = false 應在 getById kill 之後同步設定"
        )


class TestLightboxStateFirstGuard:
    """B19 守衛：Lightbox 導航必須 state-first（lightboxIndex 在 playLightboxSwitch 之前更新）"""

    SEARCH_GRID_MODE = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'search' / 'state' / 'grid-mode.js'
    SHOWCASE_CORE = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'core.js'

    @staticmethod
    def _read_file(path):
        return path.read_text(encoding='utf-8')

    @staticmethod
    def _extract_function(content, func_name):
        """粗略擷取函數內容（從函數名到下一個同級函數或檔案結尾）"""
        pattern = re.compile(r'^\s*' + re.escape(func_name) + r'\s*\(', re.MULTILINE)
        match = pattern.search(content)
        if not match:
            return ''
        start = match.start()
        return content[start:start + 3000]

    def test_lightbox_nav_state_first_search(self):
        """B19: search lightbox nav 必須在 playLightboxSwitch 之前更新 lightboxIndex"""
        content = self._read_file(self.SEARCH_GRID_MODE)
        for func in ['prevLightboxVideo', 'nextLightboxVideo']:
            body = self._extract_function(content, func)
            assert body, f"{func} 函數未找到 in grid-mode.js"
            switch_pos = body.find('playLightboxSwitch')
            update_pos = body.find('this.lightboxIndex =')
            assert update_pos != -1 and switch_pos != -1, (
                f"{func} 缺少必要的 lightboxIndex 更新或 playLightboxSwitch 呼叫"
            )
            assert update_pos < switch_pos, (
                f"B19 違規：grid-mode.js {func} 的 lightboxIndex 更新必須在 playLightboxSwitch 之前（state-first）"
            )

    def test_lightbox_nav_state_first_showcase(self):
        """B19: showcase lightbox nav 必須在 playLightboxSwitch 之前更新 lightboxIndex"""
        content = self._read_file(self.SHOWCASE_CORE)
        for func in ['prevLightboxVideo', 'nextLightboxVideo']:
            body = self._extract_function(content, func)
            assert body, f"{func} 函數未找到 in showcase/core.js"
            switch_pos = body.find('playLightboxSwitch')
            update_pos = body.find('this.lightboxIndex =')
            assert update_pos != -1 and switch_pos != -1, (
                f"{func} 缺少必要的 lightboxIndex 更新或 playLightboxSwitch 呼叫"
            )
            assert update_pos < switch_pos, (
                f"B19 違規：core.js {func} 的 lightboxIndex 更新必須在 playLightboxSwitch 之前（state-first）"
            )

    def test_lightbox_switch_onmidpoint_no_index_update(self):
        """B19: prevLightboxVideo/nextLightboxVideo 不可包含 onMidpoint（state-first 模式下已移除）"""
        for path, filename in [
            (self.SEARCH_GRID_MODE, 'search/state/grid-mode.js'),
            (self.SHOWCASE_CORE, 'showcase/core.js'),
        ]:
            content = self._read_file(path)
            for func in ['prevLightboxVideo', 'nextLightboxVideo']:
                body = self._extract_function(content, func)
                assert body, f"{func} 函數未找到 in {filename}"
                assert 'onMidpoint' not in body, (
                    f"B19 違規：{filename} {func} 仍包含 onMidpoint — "
                    "state-first 模式下 lightboxIndex 應在動畫啟動前就已更新，不需要 onMidpoint callback"
                )

    def test_open_lightbox_switch_state_first(self):
        """B19: openLightbox 的 switch 路徑也必須 state-first"""
        for path, filename in [
            (self.SEARCH_GRID_MODE, 'search/state/grid-mode.js'),
            (self.SHOWCASE_CORE, 'showcase/core.js'),
        ]:
            content = self._read_file(path)
            body = self._extract_function(content, 'openLightbox')
            assert body, f"openLightbox 函數未找到 in {filename}"
            switch_section_start = body.find('lightboxIndex !== index')
            assert switch_section_start != -1, f"{filename} openLightbox 缺少 switch 路徑"
            switch_section = body[switch_section_start:]
            switch_pos = switch_section.find('playLightboxSwitch')
            update_pos = switch_section.find('lightboxIndex = index')
            assert update_pos != -1 and switch_pos != -1, (
                f"{filename} openLightbox switch 路徑缺少 lightboxIndex 更新或 playLightboxSwitch 呼叫"
            )
            assert update_pos < switch_pos, (
                f"B19 違規：{filename} openLightbox switch 路徑的 lightboxIndex 更新必須在 playLightboxSwitch 之前"
            )

    def test_lightbox_nexttick_has_generation_guard(self):
        """B19: 所有 lightbox $nextTick 動畫 callback 必須有 _lightboxGeneration 失效檢查"""
        SEARCH_NAV = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'search' / 'state' / 'navigation.js'
        for path, filename in [
            (self.SEARCH_GRID_MODE, 'search/state/grid-mode.js'),
            (self.SHOWCASE_CORE, 'showcase/core.js'),
        ]:
            content = self._read_file(path)
            for func in ['prevLightboxVideo', 'nextLightboxVideo', 'openLightbox']:
                body = self._extract_function(content, func)
                if 'playLightboxSwitch' not in body and 'playLightboxOpen' not in body:
                    continue
                assert '_lightboxGeneration' in body, (
                    f"B19 違規：{filename} {func} 的 $nextTick callback 缺少 _lightboxGeneration 失效檢查 — "
                    "close/ESC 後 stale callback 會重設 _lightboxAnimating = true 造成 input lock"
                )

    def test_lightbox_close_increments_generation(self):
        """B19: closeLightbox / ESC / searchFromMetadata / page cleanup 必須 increment _lightboxGeneration"""
        SEARCH_INDEX = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'search' / 'state' / 'index.js'

        # Search closeLightbox
        content = self._read_file(self.SEARCH_GRID_MODE)
        body = self._extract_function(content, 'closeLightbox')
        assert body, "closeLightbox 函數未找到 in grid-mode.js"
        assert '_lightboxGeneration++' in body, (
            "B19 違規：search closeLightbox 缺少 _lightboxGeneration++ — "
            "pending $nextTick callback 不會被 invalidate"
        )

        # Showcase closeLightbox
        content = self._read_file(self.SHOWCASE_CORE)
        body = self._extract_function(content, 'closeLightbox')
        assert body, "closeLightbox 函數未找到 in showcase/core.js"
        assert '_lightboxGeneration++' in body, (
            "B19 違規：showcase closeLightbox 缺少 _lightboxGeneration++ — "
            "pending $nextTick callback 不會被 invalidate"
        )

        # Showcase searchFromMetadata
        body = self._extract_function(content, 'searchFromMetadata')
        assert body, "searchFromMetadata 函數未找到 in showcase/core.js"
        assert '_lightboxGeneration++' in body, (
            "B19 違規：showcase searchFromMetadata 缺少 _lightboxGeneration++ — "
            "pending $nextTick callback 不會被 invalidate"
        )

        # Page lifecycle cleanup — search
        search_index_content = SEARCH_INDEX.read_text(encoding='utf-8')
        assert '_lightboxGeneration++' in search_index_content, (
            "B19 違規：search state/index.js cleanup 缺少 _lightboxGeneration++ — "
            "離頁時 pending $nextTick lightbox callback 不會被 invalidate"
        )

        # Page lifecycle cleanup — showcase (init is async, extract manually)
        showcase_content = self._read_file(self.SHOWCASE_CORE)
        cleanup_start = showcase_content.find('cleanup: ()')
        assert cleanup_start != -1, "showcase/core.js 缺少 cleanup callback"
        cleanup_section = showcase_content[cleanup_start:cleanup_start + 500]
        assert '_lightboxGeneration++' in cleanup_section, (
            "B19 違規：showcase init() cleanup 缺少 _lightboxGeneration++ — "
            "離頁時 pending $nextTick lightbox callback 不會被 invalidate"
        )


class TestPlayLightboxCloseRemoved:
    """C1: playLightboxClose 已移除（dead code — closeLightbox 使用 instant close）"""

    def test_search_animations_no_play_lightbox_close(self):
        content = (PROJECT_ROOT / "web/static/js/pages/search/animations.js").read_text(encoding='utf-8')
        assert 'playLightboxClose' not in content, (
            "C1 違規：search/animations.js 仍包含 playLightboxClose — "
            "此函式零呼叫者，closeLightbox 使用 instant close"
        )

    def test_showcase_animations_no_play_lightbox_close(self):
        content = (PROJECT_ROOT / "web/static/js/pages/showcase/animations.js").read_text(encoding='utf-8')
        assert 'playLightboxClose' not in content, (
            "C1 違規：showcase/animations.js 仍包含 playLightboxClose — "
            "此函式零呼叫者，closeLightbox 使用 instant close"
        )

    def test_showcase_core_no_lightbox_close_timeline_kill(self):
        content = (PROJECT_ROOT / "web/static/js/pages/showcase/core.js").read_text(encoding='utf-8')
        assert "getById('showcaseLightboxClose')" not in content, (
            "C1 違規：showcase/core.js 仍引用 showcaseLightboxClose timeline — "
            "該 timeline 從未被建立，防禦性 kill 是 dead code"
        )


class TestPlayPageOutInRemoved:
    """C2: playPageOut/playPageIn 已移除（dead since B13，_animatePageChange 使用 playEntry）"""

    def test_showcase_animations_no_play_page_out_in(self):
        content = (PROJECT_ROOT / "web/static/js/pages/showcase/animations.js").read_text(encoding='utf-8')
        assert 'playPageOut' not in content, (
            "C2 違規：showcase/animations.js 仍包含 playPageOut — "
            "B13 後 dead code，_animatePageChange 已改用 playEntry"
        )
        assert 'playPageIn' not in content, (
            "C2 違規：showcase/animations.js 仍包含 playPageIn — "
            "B13 後 dead code，_animatePageChange 已改用 playEntry"
        )
