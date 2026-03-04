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
        """get_video() 必須包含 realpath + 目錄白名單 + 副檔名白名單"""
        py_file = PROJECT_ROOT / "web" / "routers" / "scanner.py"
        content = py_file.read_text(encoding='utf-8')
        assert 'os.path.realpath' in content, \
            "get_video 缺少 realpath（防路徑穿越）"
        assert 'ALLOWED_VIDEO_EXTENSIONS' in content, \
            "get_video 缺少副檔名白名單"
        assert 'is_path_under_dir' in content, \
            "get_video 缺少目錄白名單檢查"


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

    def test_base_js_has_stream_state_fields(self):
        """base.js 宣告四個 stream state 欄位：streamSlots、streamFilled、streamComplete、isStreaming"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert 'streamSlots' in content, \
            "base.js 缺少 streamSlots 欄位宣告 — T4 stream state contract"
        assert 'streamFilled' in content, \
            "base.js 缺少 streamFilled 欄位宣告 — T4 stream state contract"
        assert 'streamComplete' in content, \
            "base.js 缺少 streamComplete 欄位宣告 — T4 stream state contract"
        assert 'isStreaming' in content, \
            "base.js 缺少 isStreaming 欄位宣告 — T4 stream state contract"
        # U2: 新增四個 staging buffer state 欄位守衛
        assert 'streamBuffer' in content, \
            "base.js 缺少 streamBuffer 欄位宣告 — U2 staging buffer state contract"
        assert 'streamBurstTimer' in content, \
            "base.js 缺少 streamBurstTimer 欄位宣告 — U2 timing window timer"
        assert 'streamBurstedSlots' in content, \
            "base.js 缺少 streamBurstedSlots 欄位宣告 — U2 burst tracking"
        assert 'stagingVisible' in content, \
            "base.js 缺少 stagingVisible 欄位宣告 — U2 staging 容器可見性"

    def test_result_item_uses_stream_buffer(self):
        """result-item handler 推入 streamBuffer，不直接更新 searchResults（U2 batching 約束）"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert 'streamBuffer' in content, \
            "search-flow.js 缺少 streamBuffer 引用 — U2 batching 邏輯"
        assert 'streamBurstTimer' in content, \
            "search-flow.js 缺少 streamBurstTimer 引用 — U2 時間窗口 timer"

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

    def test_failed_slot_uses_visibility_not_display(self):
        """failed slot 使用 visibility: hidden 而非 x-show 結合 _failed（C10：保留 grid 空間）"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert 'visibility: hidden' in content or 'visibility:hidden' in content, \
            ("search.html 缺少 visibility: hidden — "
             "C10 約束：_failed slot 必須用 visibility 保留 grid 空間，不可用 x-show 隱藏")

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
        """search-flow.js 包含 SearchAnimations 引用；U2 後動畫移至 flush 函數（hook point 給 U3）"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert 'SearchAnimations' in content, \
            "search-flow.js 缺少 SearchAnimations 引用 — playGridFadeIn 仍在 seed handler 使用"
        # U2: playCardStreamIn 已從 result-item handler 移除，改由 U3 在 _flushStreamBuffer 接管
        # 確認 U3 hook point 存在（flush 函數預留 miniBurst 觸發點）
        assert 'U3: trigger playMiniBurst here' in content, \
            "search-flow.js 缺少 U3 hook point 註解 — _flushStreamBuffer 應預留 '// U3: trigger playMiniBurst here'"

    def test_search_flow_has_next_tick_in_result_item(self):
        """result-item 的動畫觸發用 $nextTick + requestAnimationFrame（等 DOM patch）"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert '$nextTick' in content, \
            "search-flow.js 缺少 $nextTick — T5 動畫觸發需等 Alpine DOM patch 完成"
        assert 'requestAnimationFrame' in content, \
            "search-flow.js 缺少 requestAnimationFrame — T5 確保 paint 在動畫 from 狀態前發生"

    def test_loading_strip_html_exists(self):
        """search.html 包含 stream-progress 元素（x-show="isStreaming"）"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert 'stream-progress' in content, \
            "search.html 缺少 stream-progress 元素 — T5 loading strip HTML"
        assert 'isStreaming' in content, \
            "search.html 缺少 isStreaming 綁定 — loading strip 需用 x-show=\"isStreaming\""

    def test_loading_strip_css_exists(self):
        """search.css 包含 .stream-progress 和 .stream-bar class"""
        content = self.SEARCH_CSS.read_text(encoding='utf-8')
        assert '.stream-progress' in content, \
            "search.css 缺少 .stream-progress class — T5 loading strip 樣式"
        assert '.stream-bar' in content, \
            "search.css 缺少 .stream-bar class — T5 loading strip 進度條樣式"

    def test_animations_js_has_reduced_motion_guard(self):
        """animations.js 檢查 prefersReducedMotion（Reduced Motion 降級）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'prefersReducedMotion' in content, \
            "animations.js 缺少 prefersReducedMotion 守衛 — Reduced Motion 時必須跳過動畫"
