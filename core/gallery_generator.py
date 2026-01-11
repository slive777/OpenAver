"""
Gallery Generator - 生成 HTML 列表
"""

import json
from pathlib import Path
from typing import List
from core.gallery_scanner import VideoInfo


class HTMLGenerator:
    """HTML 生成器"""

    def __init__(self):
        pass

    def escape_js_string(self, s: str) -> str:
        """轉義 JavaScript 字串"""
        if not s:
            return ""
        return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')

    def generate(self, videos: List[VideoInfo], output_path: str,
                 title: str = "OpenAver Gallery",
                 mode: str = "image",
                 sort: str = "date",
                 order: str = "descending",
                 items_per_page: int = 90,
                 theme: str = "light") -> None:
        """生成 HTML 檔案"""

        # 模式對應
        mode_map = {"detail": 0, "image": 1, "text": 2}
        order_map = {"ascending": 0, "descending": 1}

        user_mode = mode_map.get(mode, 1)
        user_order = order_map.get(order, 1)

        # 生成 JavaScript 陣列
        js_videos = []
        for v in videos:
            js_videos.append(
                f'{{ path:"{self.escape_js_string(v.path)}", '
                f'title:"{self.escape_js_string(v.title)}", '
                f'otitle:"{self.escape_js_string(v.originaltitle)}", '
                f'actor:"{self.escape_js_string(v.actor)}", '
                f'num:"{self.escape_js_string(v.num)}", '
                f'maker:"{self.escape_js_string(v.maker)}", '
                f'date:"{self.escape_js_string(v.date)}", '
                f'genre:"{self.escape_js_string(v.genre)}", '
                f'size:{v.size}, '
                f'mdate:{v.mtime}, '
                f'img:"{self.escape_js_string(v.img)}" }}'
            )

        # 生成完整 HTML
        html = self._generate_html(
            title=title,
            js_videos=js_videos,
            user_mode=user_mode,
            user_order=user_order,
            user_sort=sort,
            user_items=items_per_page,
            theme=theme
        )

        # 寫入檔案
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"[+] 已生成: {output_path}")

    def _generate_html(self, title: str, js_videos: List[str],
                       user_mode: int, user_order: int,
                       user_sort: str, user_items: int, theme: str) -> str:
        """生成 HTML 內容"""

        videos_js = '\n'.join([f'\t\tvideos[{i}] = {v};' for i, v in enumerate(js_videos)])

        return f'''<!DOCTYPE html>
<html lang="zh-TW" data-theme="{theme}">
<head>
\t<meta charset="utf-8">
\t<meta name="viewport" content="width=device-width, initial-scale=1">
\t<title>{title}</title>
{self._get_css()}
</head>
<body>
\t<!-- Header -->
\t<header class="header">
\t\t<div class="header-inner">
\t\t\t<div class="logo">OpenAver Gallery</div>
\t\t\t<div class="search-box">
\t\t\t\t<form name="form_search" onsubmit="goToLinkWithParameters(document.form_search.sw.value, 1); return false;">
\t\t\t\t\t<input type="text" name="sw" placeholder="搜尋影片..." autocomplete="off" oninput="updateResetBtn()">
\t\t\t\t\t<button type="button" class="reset-btn" onclick="resetSearch()" title="清除">✕</button>
\t\t\t\t\t<button type="submit" title="搜尋">🔍</button>
\t\t\t\t</form>
\t\t\t</div>
\t\t\t<div class="controls" id="controls"></div>
\t\t</div>
\t</header>

\t<!-- Status Bar -->
\t<div class="status-bar">
\t\t<span class="total"></span>
\t\t<div class="pagination" id="pagebar-top"></div>
\t</div>

\t<!-- Main Content -->
\t<main id="content"></main>

\t<!-- Footer -->
\t<footer class="footer">
\t\t<div class="pagination" id="pagebar"></div>
\t\t<div class="hotkey-hint">熱鍵: A 切換模式 | S 顯示/隱藏資訊 | Z/X/C/V 翻頁 | ESC 關閉</div>
\t</footer>

\t<!-- Lightbox Modal -->
\t<div id="lightbox" class="lightbox">
\t\t<div class="lightbox-backdrop"></div>
\t\t<div class="lightbox-content">
\t\t\t<img id="lightbox-img" src="" alt="">
\t\t\t<div id="lightbox-info" class="lightbox-info"></div>
\t\t</div>
\t</div>

\t<!-- Toast -->
\t<div id="toast" class="toast"></div>

\t<script>
\t\tvar videos = [];
{videos_js}
\t\tvar user_mode = {user_mode};
\t\tvar user_order = {user_order};
\t\tvar user_sort = "{user_sort}";
\t\tvar user_items_per_page = {user_items};
\t\tvar default_theme = "{theme}";
{self._get_javascript()}
\t\t// Initialize
\t\tinit();
\t</script>
</body>
</html>'''

    def _get_javascript(self) -> str:
        """返回 JavaScript 程式碼 - 現代化版本"""
        return '''
\t\tvar current_mode = user_mode;
\t\tvar current_order = user_order;
\t\tvar current_sort = user_sort;
\t\tvar current_page = 1;
\t\tvar items_per_page = user_items_per_page;
\t\tvar total_pages = 1;
\t\tvar search_words = "";
\t\tvar filtered_videos = [];
\t\tvar info_visible = false;  // 預設隱藏資訊，hover 顯示
\t\tvar current_theme = default_theme;
\t\tvar AVLIST_STATE_KEY = 'gallery_state';

\t\tfunction saveState() {
\t\t\ttry {
\t\t\t\tlocalStorage.setItem(AVLIST_STATE_KEY, JSON.stringify({
\t\t\t\t\tsw: search_words,
\t\t\t\t\tpage: current_page,
\t\t\t\t\tmode: current_mode,
\t\t\t\t\tsort: current_sort,
\t\t\t\t\torder: current_order,
\t\t\t\t\titems: items_per_page
\t\t\t\t}));
\t\t\t} catch(e) {}
\t\t}

\t\tfunction loadState() {
\t\t\ttry {
\t\t\t\tvar saved = localStorage.getItem(AVLIST_STATE_KEY);
\t\t\t\tif (saved) {
\t\t\t\t\tvar state = JSON.parse(saved);
\t\t\t\t\tsearch_words = state.sw || '';
\t\t\t\t\tcurrent_page = parseInt(state.page) || 1;
\t\t\t\t\tcurrent_mode = parseInt(state.mode) || user_mode;
\t\t\t\t\tcurrent_sort = state.sort || user_sort;
\t\t\t\t\tcurrent_order = parseInt(state.order) || user_order;
\t\t\t\t\titems_per_page = parseInt(state.items) || user_items_per_page;
\t\t\t\t\treturn true;
\t\t\t\t}
\t\t\t} catch(e) {}
\t\t\treturn false;
\t\t}

\t\tfunction initTheme() {
\t\t\tvar params = new URLSearchParams(window.location.search);
\t\t\tvar urlTheme = params.get('theme');

\t\t\tif (urlTheme && (urlTheme === 'light' || urlTheme === 'dark')) {
\t\t\t\tcurrent_theme = urlTheme; // 優先使用 URL 參數
\t\t\t} else {
\t\t\t\t// 使用生成時的預設值
\t\t\t\tcurrent_theme = default_theme;
\t\t\t}
\t\t\tdocument.documentElement.setAttribute('data-theme', current_theme);
\t\t}

\t\tfunction toggleTheme() {
\t\t\tcurrent_theme = current_theme === 'light' ? 'dark' : 'light';
\t\t\tdocument.documentElement.setAttribute('data-theme', current_theme);
\t\t\trender(); // Update button icon
\t\t}

\t\tfunction init() {
\t\t\tinitTheme();
\t\t\t// 優先從 localStorage 載入狀態，否則從 URL 參數
\t\t\tif (!loadState()) {
\t\t\t\tvar params = new URLSearchParams(window.location.search);
\t\t\t\tsearch_words = params.get('sw') || "";
\t\t\t\tcurrent_page = parseInt(params.get('page')) || 1;
\t\t\t\tcurrent_mode = parseInt(params.get('mode')) || user_mode;
\t\t\t\tcurrent_order = parseInt(params.get('order')) || user_order;
\t\t\t\tcurrent_sort = params.get('sort') || user_sort;
\t\t\t\titems_per_page = parseInt(params.get('items')) || user_items_per_page;
\t\t\t}
\t\t\tdocument.form_search.sw.value = search_words;
\t\t\tfilterAndSort();
\t\t\trender();
\t\t}

\t\tfunction filterAndSort() {
\t\t\tif (search_words) {
\t\t\t\t// 分割多個關鍵字（用空格分隔）
\t\t\t\tvar terms = search_words.toLowerCase().split(/\\s+/).filter(function(t) { return t.length > 0; });
\t\t\t\tfiltered_videos = videos.filter(function(v) {
\t\t\t\t\t// 建立所有可搜尋欄位的組合文字
\t\t\t\t\tvar searchable = [v.title, v.otitle, v.actor, v.num, v.maker, v.genre, v.date].filter(Boolean).join(' ').toLowerCase();
\t\t\t\t\t// 番號的正規化版本（移除空格和連字號）
\t\t\t\t\tvar numNorm = v.num ? v.num.toLowerCase().replace(/[\\s\\-]/g, '') : '';
\t\t\t\t\t// 每個關鍵字都要匹配（AND 邏輯）
\t\t\t\t\treturn terms.every(function(term) {
\t\t\t\t\t\tvar termNorm = term.replace(/[\\s\\-]/g, '');
\t\t\t\t\t\t// 番號模糊匹配 OR 一般欄位匹配
\t\t\t\t\t\treturn (numNorm && numNorm.indexOf(termNorm) >= 0) || searchable.indexOf(term) >= 0;
\t\t\t\t\t});
\t\t\t\t});
\t\t\t} else {
\t\t\t\tfiltered_videos = videos.slice();
\t\t\t}
\t\t\tfiltered_videos.sort(function(a, b) {
\t\t\t\tvar va, vb;
\t\t\t\tswitch(current_sort) {
\t\t\t\t\tcase 'title': va = a.title; vb = b.title; break;
\t\t\t\t\tcase 'actor': va = a.actor; vb = b.actor; break;
\t\t\t\t\tcase 'num': va = a.num; vb = b.num; break;
\t\t\t\t\tcase 'maker': va = a.maker; vb = b.maker; break;
\t\t\t\t\tcase 'date': va = a.date; vb = b.date; break;
\t\t\t\t\tcase 'size': va = a.size; vb = b.size; break;
\t\t\t\t\tcase 'mdate': va = a.mdate; vb = b.mdate; break;
\t\t\t\t\tcase 'random': return Math.random() - 0.5;
\t\t\t\t\tdefault: va = a.path; vb = b.path;
\t\t\t\t}
\t\t\t\tif (va < vb) return current_order == 0 ? -1 : 1;
\t\t\t\tif (va > vb) return current_order == 0 ? 1 : -1;
\t\t\t\treturn 0;
\t\t\t});
\t\t\tif (items_per_page == 0) {
\t\t\t\ttotal_pages = 1;
\t\t\t} else {
\t\t\t\ttotal_pages = Math.ceil(filtered_videos.length / items_per_page);
\t\t\t}
\t\t\tif (current_page > total_pages) current_page = total_pages;
\t\t\tif (current_page < 1) current_page = 1;
\t\t}

\t\tfunction render() {
\t\t\tvar content = document.getElementById('content');
\t\t\tvar controls = document.getElementById('controls');
\t\t\tvar pagebar = document.getElementById('pagebar');
\t\t\tvar pagebarTop = document.getElementById('pagebar-top');
\t\t\tvar total = document.querySelector('.total');

\t\t\t// 顯示總數與搜尋狀態
\t\t\tif (search_words) {
\t\t\t\ttotal.innerHTML = '搜尋 "<b>' + escapeHtml(search_words) + '</b>" - 找到 <b>' + filtered_videos.length + '</b> 部';
\t\t\t} else {
\t\t\t\ttotal.innerHTML = '共 <b>' + filtered_videos.length + '</b> 部影片';
\t\t\t}

\t\t\t// 渲染 Header 控制按鈕
\t\t\tcontrols.innerHTML = renderControls();

\t\t\t// 計算分頁範圍
\t\t\tvar start, end;
\t\t\tif (items_per_page == 0) {
\t\t\t\tstart = 0;
\t\t\t\tend = filtered_videos.length;
\t\t\t} else {
\t\t\t\tstart = (current_page - 1) * items_per_page;
\t\t\t\tend = Math.min(start + items_per_page, filtered_videos.length);
\t\t\t}

\t\t\t// 渲染主內容
\t\t\tvar html = '';
\t\t\tif (current_mode == 0) {
\t\t\t\t// 詳細模式
\t\t\t\thtml = '<table class="detail-table"><thead><tr>';
\t\t\t\thtml += '<th>#</th><th>片名</th><th>演員</th><th>番號</th><th>片商</th><th>日期</th><th>類型</th><th>大小</th>';
\t\t\t\thtml += '</tr></thead><tbody>';
\t\t\t\tfor (var i = start; i < end; i++) {
\t\t\t\t\tvar v = filtered_videos[i];
\t\t\t\thtml += '<tr onclick="playVideo(\\'' + escapeHtml(v.path) + '\\')">';
\t\t\t\t\thtml += '<td>' + (i+1) + '</td>';
\t\t\t\t\thtml += '<td>' + escapeHtml(stripNumPrefix(v.title)) + '</td>';
\t\t\t\t\thtml += '<td>' + formatActor(v.actor) + '</td>';
\t\t\t\t\thtml += '<td>' + escapeHtml(v.num) + '</td>';
\t\t\t\t\thtml += '<td>' + formatMaker(v.maker) + '</td>';
\t\t\t\t\thtml += '<td>' + escapeHtml(v.date) + '</td>';
\t\t\t\t\thtml += '<td>' + formatGenre(v.genre) + '</td>';
\t\t\t\t\thtml += '<td>' + formatSize(v.size) + '</td>';
\t\t\t\t\thtml += '</tr>';
\t\t\t\t}
\t\t\t\thtml += '</tbody></table>';
\t\t\t} else if (current_mode == 1) {
\t\t\t\t// 圖片模式 - 現代卡片
\t\t\t\thtml = '<div class="grid">';
\t\t\t\tfor (var i = start; i < end; i++) {
\t\t\t\t\tvar v = filtered_videos[i];
\t\t\t\t\tvar imgSrc = escapeHtml(v.img || '');
\t\t\t\t\thtml += '<div class="card">';
\t\t\t\t\t// 圖片區（含按鈕）
\t\t\t\t\thtml += '<div class="card-img" onclick="showLightbox(' + i + ')">';
\t\t\t\t\thtml += '<img loading="lazy" src="' + imgSrc + '" alt="" onerror="this.parentElement.classList.add(\\'no-img\\')"/>';
\t\t\t\t\t// Hover 時滑出的按鈕區（在縮圖內部）
\t\t\t\t\thtml += '<div class="card-actions">';
\t\t\t\t\thtml += '<a class="action-btn" href="javascript:void(0);" onclick="event.stopPropagation(); playVideo(\\'' + escapeHtml(v.path) + '\\')">開啟</a>';
\t\t\t\t\thtml += '<a class="action-btn" href="javascript:void(0);" onclick="event.stopPropagation(); copyPath(\\'' + escapeHtml(v.path) + '\\')">複製</a>';
\t\t\t\t\thtml += '</div>';
\t\t\t\t\thtml += '</div>';
\t\t\t\t\t// Footer - 預設：番號+女優，Hover：片名
\t\t\t\t\thtml += '<div class="card-footer">';
\t\t\t\t\thtml += '<div class="footer-default">';
\t\t\t\t\thtml += '<span class="num">' + escapeHtml(v.num || '') + '</span>';
\t\t\t\t\thtml += '<span class="actor">' + escapeHtml(v.actor || '') + '</span>';
\t\t\t\t\thtml += '</div>';
\t\t\t\t\tif (!info_visible) {
\t\t\t\t\t\t// Hover 時顯示片名（僅在資訊隱藏時）
\t\t\t\t\t\thtml += '<div class="footer-hover">';
\t\t\t\t\t\thtml += '<div class="hover-title">' + escapeHtml(stripNumPrefix(v.title)) + '</div>';
\t\t\t\t\t\thtml += '</div>';
\t\t\t\t\t}
\t\t\t\t\thtml += '</div>';
\t\t\t\t\t// 可切換的詳細資訊區
\t\t\t\t\tif (info_visible) {
\t\t\t\t\t\thtml += '<div class="card-info">';
\t\t\t\t\t\thtml += '<div class="info-title">' + escapeHtml(stripNumPrefix(v.title)) + '</div>';
\t\t\t\t\t\tif (v.actor) html += '<div class="info-row"><b>演員：</b>' + formatActor(v.actor) + '</div>';
\t\t\t\t\t\thtml += '<div class="info-row info-meta">';
\t\t\t\t\t\tif (v.maker) html += '<span><b>片商：</b>' + formatMaker(v.maker) + '</span>';
\t\t\t\t\t\tif (v.date) html += '<span><b>日期：</b>' + escapeHtml(v.date) + '</span>';
\t\t\t\t\thtml += '</div>';
\t\t\t\t\t\tif (v.genre) html += '<div class="info-tags">' + formatGenre(v.genre) + '</div>';
\t\t\t\t\t\thtml += '</div>';
\t\t\t\t\t}
\t\t\t\t\thtml += '</div>';
\t\t\t\t}
\t\t\t\thtml += '</div>';
\t\t\t} else {
\t\t\t\t// 文字模式
\t\t\t\thtml = '<ul class="text-list">';
\t\t\t\tfor (var i = start; i < end; i++) {
\t\t\t\t\tvar v = filtered_videos[i];
\t\t\t\thtml += '<li onclick="playVideo(\\'' + escapeHtml(v.path) + '\\')">';
\t\t\t\t\thtml += '<span class="text-num">' + escapeHtml(v.num) + '</span>';
\t\t\t\t\thtml += '<span class="text-title">' + escapeHtml(stripNumPrefix(v.title)) + '</span>';
\t\t\t\t\tif (v.actor) html += ' <span class="text-actor">(' + escapeHtml(v.actor) + ')</span>';
\t\t\t\t\thtml += '</li>';
\t\t\t\t}
\t\t\t\thtml += '</ul>';
\t\t\t}
\t\t\tcontent.innerHTML = html;

\t\t\t// 分頁
\t\t\tvar pageHtml = renderPageBar();
\t\t\tpagebar.innerHTML = pageHtml;
\t\t\tpagebarTop.innerHTML = pageHtml;
\t\t}

\t\tfunction renderControls() {
\t\t\tvar html = '';
\t\t\tvar modeIcons = ['☰', '▦', '≡'];
\t\t\tvar modeNames = ['詳細', '圖片', '文字'];
\t\t\tvar sortNames = {path:'路徑',title:'片名',actor:'演員',num:'番號',maker:'片商',date:'日期',size:'大小',mdate:'修改',random:'隨機'};
\t\t\tvar sorts = ['date','num','title','actor','maker','size','mdate','random'];

\t\t\t// 排序順序
\t\t\thtml += '<button class="ctrl-btn" onclick="switchOrder()" data-tooltip="' + (current_order==1?'遞減':'遞增') + '">';
\t\t\thtml += current_order == 1 ? '↓' : '↑';
\t\t\thtml += '</button>';

\t\t\t// 排序欄位 (下拉選單)
\t\t\thtml += '<div class="ctrl-dropdown">';
\t\t\thtml += '<button class="ctrl-btn" data-tooltip="排序: ' + sortNames[current_sort] + '">⇅</button>';
\t\t\thtml += '<div class="ctrl-dropdown-menu">';
\t\t\tfor (var i = 0; i < sorts.length; i++) {
\t\t\t\tvar s = sorts[i];
\t\t\thtml += '<a href="javascript:void(0);" onclick="switchSort(\\'' + s + '\\')"' + (current_sort==s?' class="active"':'') + '>' + sortNames[s] + '</a>';
\t\t\t}
\t\t\thtml += '</div></div>';

\t\t\t// 顯示模式 (下拉選單)
\t\t\thtml += '<div class="ctrl-dropdown">';
\t\t\thtml += '<button class="ctrl-btn" data-tooltip="' + modeNames[current_mode] + '模式">' + modeIcons[current_mode] + '</button>';
\t\t\thtml += '<div class="ctrl-dropdown-menu">';
\t\t\tfor (var i = 0; i < 3; i++) {
\t\t\t\thtml += '<a href="javascript:void(0);" onclick="switchMode(' + i + ')"' + (current_mode==i?' class="active"':'') + '>' + modeIcons[i] + ' ' + modeNames[i] + '</a>';
\t\t\t}
\t\t\thtml += '</div></div>';

\t\t\t// 影片資訊 (圖片模式)
\t\t\tif (current_mode == 1) {
\t\t\t\thtml += '<button class="ctrl-btn' + (info_visible?' active':'') + '" onclick="toggleInfo()" data-tooltip="資訊">👁</button>';
\t\t\t}

\t\t\t// 每頁數量 (下拉選單)
\t\t\thtml += '<div class="ctrl-dropdown">';
\t\t\thtml += '<button class="ctrl-btn" data-tooltip="每頁 ' + (items_per_page||'全部') + '">#</button>';
\t\t\thtml += '<div class="ctrl-dropdown-menu">';
\t\t\tvar items = [[30,'30'],[45,'45'],[60,'60'],[90,'90'],[120,'120'],[0,'全部']];
\t\t\tfor (var i = 0; i < items.length; i++) {
\t\t\t\thtml += '<a href="javascript:void(0);" onclick="switchItems(' + items[i][0] + ')"' + (items_per_page==items[i][0]?' class="active"':'') + '>' + items[i][1] + '</a>';
\t\t\t}
\t\t\thtml += '</div></div>';

\t\t\t// 主題切換按鈕 (放在最後)
\t\t\thtml += '<button class="ctrl-btn" onclick="toggleTheme()" data-tooltip="' + (current_theme=='dark'?'切換淺色':'切換深色') + '">';
\t\t\thtml += current_theme == 'dark' ? '☼' : '☾';
\t\t\thtml += '</button>';

\t\t\treturn html;
\t\t}

\t\tfunction renderPageBar() {
\t\t\tif (total_pages <= 1) return '';
\t\t\tvar html = '';
\t\t\tif (current_page > 1) {
\t\t\t\thtml += '<a href="javascript:void(0);" onclick="goPage(' + (current_page-1) + ')">← 上一頁</a>';
\t\t\t}
\t\t\thtml += '<select onchange="goPage(this.value)">';
\t\t\tfor (var i = 1; i <= total_pages; i++) {
\t\t\t\thtml += '<option value="' + i + '"' + (i==current_page?' selected':'') + '>' + i + ' / ' + total_pages + '</option>';
\t\t\t}
\t\t\thtml += '</select>';
\t\t\tif (current_page < total_pages) {
\t\t\t\thtml += '<a href="javascript:void(0);" onclick="goPage(' + (current_page+1) + ')">下一頁 →</a>';
\t\t\t}
\t\t\treturn html;
\t\t}

\t\tfunction goPage(page) {
\t\t\tcurrent_page = parseInt(page);
\t\t\trender();
\t\t\twindow.scrollTo({ top: 0, behavior: 'smooth' });
\t\t\tsaveState();
\t\t}

\t\tfunction switchMode(mode) {
\t\t\tcurrent_mode = mode;
\t\t\trender();
\t\t\tsaveState();
\t\t}

\t\tfunction switchSort(sort) {
\t\t\tcurrent_sort = sort;
\t\t\tfilterAndSort();
\t\t\trender();
\t\t\tsaveState();
\t\t}

\t\tfunction switchOrder() {
\t\t\tcurrent_order = current_order == 0 ? 1 : 0;
\t\t\tfilterAndSort();
\t\t\trender();
\t\t\tsaveState();
\t\t}

\t\tfunction switchItems(items) {
\t\t\titems_per_page = parseInt(items);
\t\t\tcurrent_page = 1;
\t\t\tfilterAndSort();
\t\t\trender();
\t\t\tsaveState();
\t\t}

\t\tfunction goToLinkWithParameters(sw, page) {
\t\t\tif (lightbox_open) hideLightbox();
\t\t\tsearch_words = sw;
\t\t\tdocument.form_search.sw.value = sw;
\t\t\tupdateResetBtn();
\t\t\tcurrent_page = page || 1;
\t\t\tfilterAndSort();
\t\t\trender();
\t\t\twindow.scrollTo({ top: 0, behavior: 'smooth' });
\t\t\tsaveState();
\t\t}

\t\tfunction updateResetBtn() {
\t\t\tvar btn = document.querySelector('.reset-btn');
\t\t\tbtn.style.display = document.form_search.sw.value ? 'flex' : 'none';
\t\t}

\t\tfunction resetSearch() {
\t\t\tsearch_words = '';
\t\t\tdocument.form_search.sw.value = '';
\t\t\tupdateResetBtn();
\t\t\tcurrent_page = 1;
\t\t\tfilterAndSort();
\t\t\trender();
\t\t\tsaveState();
\t\t}

\t\tfunction playVideo(path) {
\t\t\tvar h = path.replace(/#/g, '%23');
\t\t\tvar isFirefox = typeof InstallTrigger !== 'undefined';
\t\t\tif (isFirefox) {
\t\t\t\twindow.location.href = h;
\t\t\t} else {
\t\t\t\twindow.open(h, '_blank');
\t\t\t}
\t\t}

\t\tfunction copyPath(path) {
\t\t\tvar lastSlash = path.lastIndexOf('/');
\t\t\tif (lastSlash < 0) lastSlash = path.lastIndexOf('\\\\');
\t\t\tvar folder = lastSlash >= 0 ? path.substring(0, lastSlash) : path;
\t\t\tvar winPath = folder.replace('file:///', '').replace(/\\//g, '\\\\');
\t\t\tnavigator.clipboard.writeText(winPath).then(function() {
\t\t\t\tshowToast('已複製: ' + winPath);
\t\t\t});
\t\t}

\t\tfunction showToast(msg) {
\t\t\tvar toast = document.getElementById('toast');
\t\t\ttoast.textContent = msg;
\t\t\ttoast.classList.add('show');
\t\t\tsetTimeout(function() { toast.classList.remove('show'); }, 2500);
\t\t}

\t\t// Lightbox
\t\tvar lightbox_open = false;
\t\tfunction showLightbox(idx) {
\t\t\tvar v = filtered_videos[idx];
\t\t\tif (!v) return;
\t\t\tvar lightbox = document.getElementById('lightbox');
\t\t\tvar lightboxImg = document.getElementById('lightbox-img');
\t\t\tvar lightboxInfo = document.getElementById('lightbox-info');
\t\t\t
\t\t\tif (v.img) {
\t\t\t\tlightboxImg.src = v.img;
\t\t\t\tlightboxImg.style.display = 'block';
\t\t\t} else {
\t\t\t\tlightboxImg.style.display = 'none';
\t\t\t}
\t\t\t
\t\t\tvar html = '<div class="lb-title">' + escapeHtml(stripNumPrefix(v.title)) + '</div>';
\t\t\tif (v.otitle) html += '<div class="lb-otitle">' + escapeHtml(v.otitle) + '</div>';
\t\t\tif (v.actor) html += '<div class="lb-actor">' + formatActor(v.actor) + '</div>';
\t\t\thtml += '<div class="lb-meta">';
\t\t\thtml += '<span>' + escapeHtml(v.num || '') + '</span>';
\t\t\tif (v.maker) html += '<span>' + formatMaker(v.maker) + '</span>';
\t\t\tif (v.date) html += '<span>' + escapeHtml(v.date) + '</span>';
\t\t\thtml += '</div>';
\t\t\tif (v.genre) html += '<div class="lb-tags">' + formatGenrePills(v.genre) + '</div>';
\t\t\thtml += '<div class="lb-footer">';
\t\t\thtml += '<div class="lb-actions">';
\t\t\thtml += '<a class="lb-btn" href="javascript:void(0);" onclick="event.stopPropagation(); playVideo(\\'' + escapeHtml(v.path) + '\\')">開啟</a>';
\t\t\thtml += '<a class="lb-btn" href="javascript:void(0);" onclick="event.stopPropagation(); copyPath(\\'' + escapeHtml(v.path) + '\\')">複製</a>';
\t\t\thtml += '</div>';
\t\t\thtml += '<span class="lb-size">' + formatSize(v.size) + '</span>';
\t\t\thtml += '</div>';
\t\t\tlightboxInfo.innerHTML = html;
\t\t\t
\t\t\t// 確保顯示（即使正在 fade out 中）
\t\t\tlightbox.classList.add('show');
\t\t\tlightbox_open = true;
\t\t\tdocument.body.style.overflow = 'hidden';
\t\t}

\t\tfunction hideLightbox() {
\t\t\tvar lightbox = document.getElementById('lightbox');
\t\t\tlightbox.classList.remove('show');
\t\t\tlightbox_open = false;
\t\t\tdocument.body.style.overflow = '';
\t\t}

\t\t// 滑鼠離開 lightbox-content 時自動關閉
\t\tdocument.querySelector('.lightbox-content').addEventListener('mouseleave', function() {
\t\t\tif (lightbox_open) hideLightbox();
\t\t});

\t\t// 點擊 lightbox 背景時，檢查是否點到卡片
\t\tdocument.getElementById('lightbox').addEventListener('click', function(e) {
\t\t\t// 如果點擊的是 lightbox-content 內部，不處理
\t\t\tif (e.target.closest('.lightbox-content')) return;

\t\t\t// 暫時隱藏 lightbox 來檢測下方元素
\t\t\tvar lightbox = this;
\t\t\tlightbox.style.display = 'none';

\t\t\t// 找到點擊位置下的元素
\t\t\tvar elementBelow = document.elementFromPoint(e.clientX, e.clientY);

\t\t\t// 恢復 lightbox
\t\t\tlightbox.style.display = '';

\t\t\t// 檢查是否是卡片
\t\t\tvar cardImg = elementBelow ? elementBelow.closest('.card-img') : null;
\t\t\tif (cardImg) {
\t\t\t\t// 觸發該卡片的 onclick
\t\t\t\tcardImg.click();
\t\t\t} else {
\t\t\t\t// 不是卡片，關閉 lightbox
\t\t\thideLightbox();
\t\t\t}
\t\t});

\t\t// 顯示/隱藏資訊
\t\tfunction toggleInfo() {
\t\t\tinfo_visible = !info_visible;
\t\t\trender();
\t\t}

\t\t// 熱鍵
\t\tdocument.addEventListener('keydown', function(e) {
\t\t\tif (e.target.tagName === 'INPUT') return;
\t\t\tvar key = e.key.toUpperCase();
\t\t\tif (key === 'ESCAPE' && lightbox_open) { hideLightbox(); return; }
\t\t\tif (lightbox_open) return;
\t\t\tif (key === 'S' && current_mode === 1) toggleInfo();
\t\t\telse if (key === 'A') { current_mode = (current_mode + 1) % 3; render(); }
\t\t\telse if (key === 'Z') goPage(1);
\t\t\telse if (key === 'X' && current_page > 1) goPage(current_page - 1);
\t\t\telse if (key === 'C' && current_page < total_pages) goPage(current_page + 1);
\t\t\telse if (key === 'V') goPage(total_pages);
\t\t});

\t\tfunction escapeHtml(str) {
\t\t\tif (!str) return '';
\t\t\treturn str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
\t\t}

\t\tfunction stripNumPrefix(title) {
\t\t\tif (!title) return '';
\t\t\treturn title.replace(/^\\[[A-Z0-9\\-]+\\]/i, '').trim();
\t\t}

\t\tfunction formatActor(actor) {
\t\t\tif (!actor) return '';
\t\t\treturn actor.split(',').map(function(a) {
\t\t\t\treturn '<a href="javascript:goToLinkWithParameters(\\'' + a.trim() + '\\',1)">' + escapeHtml(a.trim()) + '</a>';
\t\t\t}).join(', ');
\t\t}

\t\tfunction formatActorOverlay(actor) {
\t\t\tif (!actor) return '';
\t\t\treturn actor.split(',').map(function(a) {
\t\t\t\treturn '<a href="javascript:goToLinkWithParameters(\\'' + a.trim() + '\\',1)" onclick="event.stopPropagation();">' + escapeHtml(a.trim()) + '</a>';
\t\t\t}).join(', ');
\t\t}

\t\tfunction formatMaker(maker) {
\t\t\tif (!maker) return '';
\t\t\treturn '<a href="javascript:goToLinkWithParameters(\\'' + escapeHtml(maker) + '\\',1)">' + escapeHtml(maker) + '</a>';
\t\t}

\t\tfunction formatGenre(genre) {
\t\t\tif (!genre) return '';
\t\t\treturn genre.split(',').map(function(g) {
\t\t\t\treturn '<span class="tag"><a href="javascript:goToLinkWithParameters(\\'' + g.trim() + '\\',1)">' + escapeHtml(g.trim()) + '</a></span>';
\t\t\t}).join('');
\t\t}

\t\tfunction formatGenrePills(genre) {
\t\t\tif (!genre) return '';
\t\t\treturn genre.split(',').map(function(g) {
\t\t\t\treturn '<span class="lb-tag"><a href="javascript:goToLinkWithParameters(\\'' + g.trim() + '\\',1)">' + escapeHtml(g.trim()) + '</a></span>';
\t\t\t}).join('');
\t\t}

\t\tfunction formatSize(bytes) {
\t\t\tif (bytes == 0) return '';
\t\t\tvar units = ['B', 'KB', 'MB', 'GB', 'TB'];
\t\t\tvar i = 0;
\t\t\twhile (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
\t\t\treturn bytes.toFixed(1) + ' ' + units[i];
\t\t}
'''

    def _get_css(self) -> str:
        """返回 CSS 樣式 - Editorial Gallery 現代風格 (支援 Dark Mode)"""
        return '''
\t<style>
\t/* ========== CSS Variables ========== */
\t:root {
\t\t/* Colors - Warm Neutral Palette (Light Mode) */
\t\t--bg-body: #f8f7f4;
\t\t--bg-card: #ffffff;
\t\t--bg-header: rgba(255, 255, 255, 0.85);
\t\t--bg-overlay: rgba(18, 18, 20, 0.88);
\t\t--bg-lightbox: rgba(10, 10, 12, 0.92);
\t\t
\t\t--text-primary: #1a1a1a;
\t\t--text-secondary: #6b6b6b;
\t\t--text-muted: #9a9a9a;
\t\t--text-inverse: #ffffff;
\t\t
\t\t--accent: #2d5a7b;
\t\t--accent-hover: #1e4460;
\t\t--accent-red: #c94a4a;
\t\t
\t\t--border-light: #e8e6e3;
\t\t--border-card: #eceae7;
\t\t
\t\t/* Shadows */
\t\t--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.04);
\t\t--shadow-md: 0 4px 12px rgba(0, 0, 0, 0.06);
\t\t--shadow-lg: 0 8px 30px rgba(0, 0, 0, 0.10);
\t\t--shadow-card-hover: 0 12px 40px rgba(0, 0, 0, 0.12);
\t\t
\t\t/* Spacing */
\t\t--space-xs: 0.25rem;
\t\t--space-sm: 0.5rem;
\t\t--space-md: 1rem;
\t\t--space-lg: 1.5rem;
\t\t--space-xl: 2rem;
\t\t--space-2xl: 3rem;
\t\t
\t\t/* Typography */
\t\t--font-sans: "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
\t\t--font-mono: "SF Mono", "Fira Code", monospace;
\t\t
\t\t/* Layout */
\t\t--max-width: 1680px;
\t\t--header-height: 64px;
\t\t--card-radius: 12px;
\t\t--radius-sm: 6px;
\t\t--radius-md: 8px;
\t\t
\t\t/* Transitions */
\t\t--ease-out: cubic-bezier(0.22, 1, 0.36, 1);
\t\t--ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
\t\t--duration-fast: 0.15s;
\t\t--duration-normal: 0.25s;
\t\t--duration-slow: 0.4s;
\t}

\t[data-theme="dark"] {
\t\t--bg-body: #0f0f11;
\t\t--bg-card: #1c1c1e;
\t\t--bg-header: rgba(28, 28, 30, 0.85);
\t\t--bg-overlay: rgba(0, 0, 0, 0.92);
\t\t--bg-lightbox: rgba(0, 0, 0, 0.95);
\t\t
\t\t--text-primary: #f2f2f7;
\t\t--text-secondary: #aeaeb2;
\t\t--text-muted: #636366;
\t\t--text-inverse: #ffffff;
\t\t
\t\t--accent: #5ac8fa;
\t\t--accent-hover: #007aff;
\t\t--accent-red: #ff453a;
\t\t
\t\t--border-light: #2c2c2e;
\t\t--border-card: #3a3a3c;
\t\t
\t\t--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
\t\t--shadow-md: 0 4px 12px rgba(0, 0, 0, 0.4);
\t\t--shadow-lg: 0 8px 30px rgba(0, 0, 0, 0.5);
\t\t--shadow-card-hover: 0 12px 40px rgba(0, 0, 0, 0.6);
\t}

\t/* ========== Reset & Base ========== */
\t*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
\t
\thtml {
\t\tfont-size: 16px;
\t\t-webkit-font-smoothing: antialiased;
\t\t-moz-osx-font-smoothing: grayscale;
\t}
\t
\tbody {
\t\tbackground: var(--bg-body);
\t\tfont-family: var(--font-sans);
\t\tcolor: var(--text-primary);
\t\tline-height: 1.5;
\t\tmin-height: 100vh;
\t\ttransition: background-color var(--duration-normal) ease, color var(--duration-normal) ease;
\t}
\t
\ta {
\t\tcolor: var(--text-primary);
\t\ttext-decoration: none;
\t\ttransition: color var(--duration-fast) ease;
\t}
\ta:hover { color: var(--accent); }

\t/* ========== Header ========== */
\t.header {
\t\tposition: sticky;
\t\ttop: 0;
\t\tz-index: 100;
\t\tbackground: var(--bg-header);
\t\tbackdrop-filter: blur(16px);
\t\t-webkit-backdrop-filter: blur(16px);
\t\tborder-bottom: 1px solid var(--border-light);
\t\theight: var(--header-height);
\t\ttransition: background-color var(--duration-normal) ease, border-color var(--duration-normal) ease;
\t}
\t
\t.header-inner {
\t\tmax-width: var(--max-width);
\t\tmargin: 0 auto;
\t\tpadding: 0 var(--space-lg);
\t\theight: 100%;
\t\tdisplay: grid;
\t\tgrid-template-columns: 1fr auto 1fr;
\t\talign-items: center;
\t\tgap: var(--space-lg);
\t}
\t
\t.logo {
\t\tfont-size: 1.25rem;
\t\tfont-weight: 700;
\t\tletter-spacing: -0.02em;
\t\tcolor: var(--text-primary);
\t\tjustify-self: start;
\t}
\t
\t.search-box {
\t\tjustify-self: center;
\t\twidth: 100%;
\t\tmax-width: 400px;
\t}
\t
\t.search-box form {
\t\tdisplay: flex;
\t\tgap: 0;
\t}
\t
\t.search-box input {
\t\tflex: 1;
\t\tpadding: 0.625rem 1rem;
\t\tborder: 1px solid var(--border-light);
\t\tborder-right: none;
\t\tborder-radius: var(--radius-md) 0 0 var(--radius-md);
\t\tfont-family: inherit;
\t\tfont-size: 0.875rem;
\t\tcolor: var(--text-primary);
\t\tbackground: var(--bg-card);
\t\toutline: none;
\t\ttransition: border-color var(--duration-fast) ease, box-shadow var(--duration-fast) ease, background-color var(--duration-normal) ease;
\t}
\t
\t.search-box input:focus {
\t\tborder-color: var(--accent);
\t\tbox-shadow: 0 0 0 3px rgba(45, 90, 123, 0.1);
\t}
\t
\t.search-box input::placeholder { color: var(--text-muted); }
\t
\t.search-box button {
\t\tdisplay: flex;
\t\talign-items: center;
\t\tjustify-content: center;
\t\tpadding: 0 0.75rem;
\t\tborder: 1px solid var(--border-light);
\t\tborder-left: none;
\t\tbackground: var(--bg-card);
\t\tcursor: pointer;
\t\tfont-size: 1rem;
\t\tcolor: var(--text-secondary);
\t\ttransition: all var(--duration-fast) ease;
\t}
\t
\t.search-box button:last-child {
\t\tborder-radius: 0 var(--radius-md) var(--radius-md) 0;
\t}
\t
\t.search-box button:hover { background: var(--bg-body); color: var(--text-primary); }
\t
\t.search-box .reset-btn {
\t\tdisplay: none;
\t\tcolor: var(--text-muted);
\t\tfont-size: 0.875rem;
\t}
\t
\t.search-box .reset-btn:hover {
\t\tcolor: var(--accent-red);
\t\tbackground: var(--bg-body);
\t}
\t
\t/* Header Controls - Icon Buttons */
\t.controls {
\t\tdisplay: flex;
\t\talign-items: center;
\t\tgap: var(--space-xs);
\t\tjustify-self: end;
\t}
\t
\t.ctrl-btn {
\t\twidth: 36px;
\t\theight: 36px;
\t\tborder: none;
\t\tborder-radius: var(--radius-sm);
\t\tbackground: transparent;
\t\tcursor: pointer;
\t\tfont-size: 1.125rem;
\t\tdisplay: flex;
\t\talign-items: center;
\t\tjustify-content: center;
\t\tcolor: var(--text-secondary);
\t\ttransition: all var(--duration-fast) ease;
\t\tposition: relative;
\t}
\t
\t.ctrl-btn:hover {
\t\tbackground: var(--bg-body);
\t\tcolor: var(--text-primary);
\t}
\t
\t.ctrl-btn.active {
\t\tbackground: var(--accent);
\t\tcolor: var(--text-inverse);
\t}
\t
\t.ctrl-btn[data-tooltip]::after {
\t\tcontent: attr(data-tooltip);
\t\tposition: absolute;
\t\ttop: 100%;
\t\tleft: 50%;
\t\ttransform: translateX(-50%) translateY(4px);
\t\tpadding: 0.375rem 0.625rem;
\t\tbackground: var(--text-primary);
\t\tcolor: var(--text-inverse);
\t\tfont-size: 0.75rem;
\t\tfont-weight: 500;
\t\twhite-space: nowrap;
\t\tborder-radius: var(--radius-sm);
\t\topacity: 0;
\t\tpointer-events: none;
\t\ttransition: opacity var(--duration-fast) ease, transform var(--duration-fast) ease;
\t\tz-index: 300;
\t}
\t
\t.ctrl-btn:hover[data-tooltip]::after {
\t\topacity: 1;
\t\ttransform: translateX(-50%) translateY(8px);
\t}
\t
\t/* Dropdown Menu */
\t.ctrl-dropdown {
\t\tposition: relative;
\t}
\t
\t.ctrl-dropdown-menu {
\t\tposition: absolute;
\t\ttop: 100%;
\t\tright: 0;
\t\tmargin-top: 8px;
\t\tmin-width: 140px;
\t\tbackground: var(--bg-card);
\t\tborder: 1px solid var(--border-light);
\t\tborder-radius: var(--radius-md);
\t\tbox-shadow: var(--shadow-lg);
\t\tpadding: var(--space-xs);
\t\topacity: 0;
\t\tvisibility: hidden;
\t\ttransform: translateY(-8px);
\t\ttransition: all var(--duration-normal) var(--ease-out);
\t\tz-index: 200;
\t}
\t
\t.ctrl-dropdown:hover .ctrl-dropdown-menu,
\t.ctrl-dropdown-menu:hover {
\t\topacity: 1;
\t\tvisibility: visible;
\t\ttransform: translateY(0);
\t}
\t
\t.ctrl-dropdown-menu a {
\t\tdisplay: block;
\t\tpadding: 0.5rem 0.75rem;
\t\tfont-size: 0.8125rem;
\t\tcolor: var(--text-secondary);
\t\tborder-radius: var(--radius-sm);
\t\ttransition: all var(--duration-fast) ease;
\t}
\t
\t.ctrl-dropdown-menu a:hover {
\t\tbackground: var(--bg-body);
\t\tcolor: var(--text-primary);
\t}
\t
\t.ctrl-dropdown-menu a.active {
\t\tbackground: var(--accent);
\t\tcolor: var(--text-inverse);
\t}

\t/* ========== Status Bar ========== */
\t.status-bar {
\t\tmax-width: var(--max-width);
\t\tmargin: 0 auto;
\t\tpadding: var(--space-md) var(--space-lg);
\t\tdisplay: flex;
\t\talign-items: center;
\t\tjustify-content: space-between;
\t\tflex-wrap: wrap;
\t\tgap: var(--space-md);
\t}
\t
\t.total {
\t\tfont-size: 0.875rem;
\t\tcolor: var(--text-secondary);
\t}
\t
\t.total b {
\t\tcolor: var(--text-primary);
\t\tfont-weight: 600;
\t}
\t
\t.pagination {
\t\tdisplay: flex;
\t\talign-items: center;
\t\tgap: var(--space-sm);
\t}
\t
\t.pagination a, .pagination select {
\t\tpadding: 0.375rem 0.75rem;
\t\tborder: 1px solid var(--border-light);
\t\tborder-radius: var(--radius-sm);
\t\tbackground: var(--bg-card);
\t\tfont-size: 0.8125rem;
\t\tcolor: var(--text-secondary);
\t\tcursor: pointer;
\t\ttransition: all var(--duration-fast) ease;
\t}
\t
\t.pagination a:hover {
\t\tborder-color: var(--accent);
\t\tcolor: var(--accent);
\t}
\t
\t.pagination select {
\t\tfont-family: inherit;
\t\toutline: none;
\t\tcolor: var(--text-primary);
\t}

\t/* ========== Main Content ========== */
\tmain#content {
\t\tmax-width: var(--max-width);
\t\tmargin: 0 auto;
\t\tpadding: 0 var(--space-lg) var(--space-2xl);
\t}

\t/* ========== Grid Layout ========== */
\t.grid {
\t\tdisplay: grid;
\t\tgrid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
\t\tgap: var(--space-lg);
\t}
\t
\t/* 響應式: 寬螢幕固定 5 欄 */
\t@media (min-width: 1500px) {
\t\t.grid {
\t\t\tgrid-template-columns: repeat(5, 1fr);
\t\t}
\t}
\t
\t/* 中等螢幕 4 欄 */
\t@media (min-width: 1100px) and (max-width: 1499px) {
\t\t.grid {
\t\t\tgrid-template-columns: repeat(4, 1fr);
\t\t}
\t}
\t
\t/* 平板 2-3 欄 */
\t@media (max-width: 900px) {
\t\t.grid {
\t\t\tgrid-template-columns: repeat(3, 1fr);
\t\t}
\t}
\t
\t@media (max-width: 680px) {
\t\t.grid {
\t\t\tgrid-template-columns: repeat(2, 1fr);
\t\t\tgap: var(--space-md);
\t\t}
\t}
\t
\t/* 手機 1 欄 */
\t@media (max-width: 480px) {
\t\t.grid {
\t\t\tgrid-template-columns: 1fr;
\t\t}
\t}

\t/* ========== Card Design ========== */
\t.card {
\t\tbackground: var(--bg-card);
\t\tborder-radius: var(--card-radius);
\t\toverflow: hidden;
\t\tbox-shadow: var(--shadow-sm);
\t\tborder: 1px solid var(--border-card);
\t\ttransition: transform var(--duration-normal) var(--ease-out),
\t\t            box-shadow var(--duration-normal) var(--ease-out),
                    background-color var(--duration-normal) ease,
                    border-color var(--duration-normal) ease;
\t\tposition: relative;
\t}
\t
\t.card:hover {
\t\ttransform: translateY(-4px);
\t\tbox-shadow: var(--shadow-card-hover);
\t}
\t
\t/* Card Image Container */
\t.card-img {
\t\tposition: relative;
\t\taspect-ratio: 3 / 2;
\t\toverflow: hidden;
\t\tbackground: var(--bg-body);
\t\tcursor: pointer;
\t}
\t
\t.card-img img {
\t\twidth: 100%;
\t\theight: 100%;
\t\tobject-fit: cover;
\t\ttransition: transform var(--duration-slow) var(--ease-out);
\t}
\t
\t.card:hover .card-img img {
\t\ttransform: scale(1.03);
\t}
\t
\t.card-img.no-img::before {
\t\tcontent: '無封面';
\t\tposition: absolute;
\t\ttop: 50%;
\t\tleft: 50%;
\t\ttransform: translate(-50%, -50%);
\t\tcolor: var(--text-muted);
\t\tfont-size: 0.875rem;
\t\tletter-spacing: 0.05em;
\t}
\t
\t/* Hover Actions - 滑出按鈕區 */
\t.card-actions {
\t\tposition: absolute;
\t\tbottom: 0;
\t\tleft: 0;
\t\tright: 0;
\t\tdisplay: flex;
\t\tjustify-content: center;
\t\tgap: var(--space-md);
\t\tpadding: var(--space-sm) var(--space-md);
\t\tbackground: linear-gradient(to top, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.4) 60%, transparent 100%);
\t\topacity: 0;
\t\ttransform: translateY(100%);
\t\ttransition: all var(--duration-normal) var(--ease-out);
\t}

\t.card:hover .card-actions {
\t\topacity: 1;
\t\ttransform: translateY(0);
\t}

\t.card-actions .action-btn {
\t\tpadding: 0.4rem 1rem;
\t\tborder: 1px solid rgba(255, 255, 255, 0.4);
\t\tborder-radius: var(--radius-sm);
\t\tbackground: rgba(255, 255, 255, 0.15);
\t\tcolor: var(--text-inverse);
\t\tfont-size: 0.75rem;
\t\tfont-weight: 500;
\t\ttext-decoration: none;
\t\tcursor: pointer;
\t\ttransition: all var(--duration-fast) ease;
\t\tbackdrop-filter: blur(4px);
\t}

\t.card-actions .action-btn:hover {
\t\tbackground: rgba(255, 255, 255, 0.3);
\t\tborder-color: rgba(255, 255, 255, 0.6);
\t}
\t
\t/* Card Footer - 番號+大小 / 片名+女優 */
\t.card-footer {
\t\tposition: relative;
\t\tborder-top: 1px solid var(--border-card);
\t\tbackground: var(--bg-card);
\t\toverflow: hidden;
\t\tmin-height: 2.5rem;
\t}

\t.footer-default {
\t\tpadding: var(--space-sm) var(--space-md);
\t\tdisplay: flex;
\t\talign-items: center;
\t\tjustify-content: space-between;
\t\ttransition: opacity var(--duration-fast) ease;
\t}

\t.footer-default .num {
\t\tfont-size: 0.8125rem;
\t\tfont-weight: 600;
\t\tcolor: var(--accent-red);
\t\tletter-spacing: 0.02em;
\t}

\t.footer-default .actor {
\t\tfont-size: 0.75rem;
\t\tcolor: var(--text-secondary);
\t\twhite-space: nowrap;
\t\toverflow: hidden;
\t\ttext-overflow: ellipsis;
\t}

\t.footer-hover {
\t\tposition: absolute;
\t\tinset: 0;
\t\tpadding: var(--space-sm) var(--space-md);
\t\tbackground: var(--bg-card);
\t\topacity: 0;
\t\ttransform: translateY(100%);
\t\ttransition: opacity var(--duration-fast) ease, transform var(--duration-fast) ease;
\t}

\t.card:hover .footer-hover {
\t\topacity: 1;
\t\ttransform: translateY(0);
\t}

\t.card:hover .footer-default {
\t\topacity: 0;
\t}

\t.footer-hover .hover-title {
\t\tfont-size: 0.8125rem;
\t\tfont-weight: 500;
\t\tcolor: var(--text-primary);
\t\tline-height: 1.3;
\t\tdisplay: -webkit-box;
\t\t-webkit-line-clamp: 2;
\t\t-webkit-box-orient: vertical;
\t\toverflow: hidden;
\t}

\t
\t/* Card Info - 展開時的詳細資訊 */
\t.card-info {
\t\tpadding: var(--space-sm) var(--space-md) var(--space-md);
\t\tfont-size: 0.8125rem;
\t\tline-height: 1.5;
\t\tborder-top: 1px solid var(--border-card);
\t}

\t.card-info .info-title {
\t\tfont-weight: 500;
\t\tcolor: var(--text-primary);
\t\tline-height: 1.4;
\t\tmargin-bottom: var(--space-xs);
\t\tdisplay: -webkit-box;
\t\t-webkit-line-clamp: 2;
\t\t-webkit-box-orient: vertical;
\t\toverflow: hidden;
\t}

\t.card-info .info-row {
\t\tcolor: var(--text-secondary);
\t\tmargin-bottom: var(--space-xs);
\t}

\t.card-info .info-row:last-child {
\t\tmargin-bottom: 0;
\t}

\t.card-info .info-row b {
\t\tcolor: var(--text-primary);
\t\tfont-weight: 500;
\t}

\t.card-info .info-row a {
\t\tcolor: var(--text-secondary);
\t}

\t.card-info .info-row a:hover {
\t\tcolor: var(--accent);
\t}

\t.card-info .info-meta {
\t\tdisplay: flex;
\t\tflex-wrap: wrap;
\t\tgap: var(--space-xs) var(--space-md);
\t}

\t.card-info .info-tags {
\t\tfont-size: 0.75rem;
\t\tcolor: var(--text-muted);
\t\tline-height: 1.5;
\t\tdisplay: -webkit-box;
\t\t-webkit-line-clamp: 2;
\t\t-webkit-box-orient: vertical;
\t\toverflow: hidden;
\t}

\t.card-info .info-tags .tag {
\t\tdisplay: inline;
\t}

\t.card-info .info-tags .tag:not(:last-child)::after {
\t\tcontent: " / ";
\t\tcolor: var(--border-light);
\t}

\t/* ========== Footer ========== */
\t.footer {
\t\tmax-width: var(--max-width);
\t\tmargin: 0 auto;
\t\tpadding: var(--space-xl) var(--space-lg);
\t\ttext-align: center;
\t\tborder-top: 1px solid var(--border-light);
\t}
\t
\t.hotkey-hint {
\t\tfont-size: 0.75rem;
\t\tcolor: var(--text-muted);
\t\tletter-spacing: 0.02em;
\t}

\t/* ========== Lightbox ========== */
\t.lightbox {
\t\tposition: fixed;
\t\tinset: 0;
\t\tz-index: 1000;
\t\tdisplay: flex;
\t\talign-items: center;
\t\tjustify-content: center;
\t\tvisibility: hidden;
\t\topacity: 0;
\t\tpointer-events: none;
\t\ttransition: visibility 0s linear var(--duration-normal),
\t\t            opacity var(--duration-normal) var(--ease-out);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        background: rgba(0, 0, 0, 0.6);
\t}
\t
\t.lightbox.show {
\t\tvisibility: visible;
\t\topacity: 1;
\t\tpointer-events: auto;
\t\ttransition-delay: 0s;
\t}
\t
\t.lightbox-backdrop {
\t\tdisplay: none;
\t}
\t
\t.lightbox-content {
\t\tposition: relative;
\t\tmax-width: 90vw;
\t\tmax-height: 90vh;
\t\tdisplay: flex;
\t\tflex-direction: column;
\t\talign-items: center;
\t\tgap: var(--space-md);
\t\tbackground: var(--bg-card);
\t\tborder-radius: var(--card-radius);
\t\tpadding: var(--space-md);
\t\tbox-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25),
\t\t            0 0 0 1px rgba(0, 0, 0, 0.05);
\t\ttransform: scale(0.95);
\t\ttransition: transform var(--duration-normal) var(--ease-out);
\t}
\t
\t.lightbox.show .lightbox-content {
\t\ttransform: scale(1);
\t}
\t
\t.lightbox-content > img {
\t\tmax-width: 100%;
\t\tmax-height: 60vh;
\t\tobject-fit: contain;
\t\tborder-radius: var(--radius-sm);
\t}
\t
\t.lightbox-info {
\t\tpadding: var(--space-sm) 0 0 0;
\t\tmax-width: 600px;
\t\twidth: 100%;
\t\tborder-top: 1px solid var(--border-light);
\t}

\t.lightbox-info .lb-title {
\t\tfont-size: 0.9375rem;
\t\tfont-weight: 600;
\t\tcolor: var(--text-primary);
\t\tline-height: 1.4;
\t\tmargin-bottom: var(--space-xs);
\t\twhite-space: nowrap;
\t\toverflow: hidden;
\t\ttext-overflow: ellipsis;
\t}

\t.lightbox-info .lb-otitle {
\t\tfont-size: 0.8125rem;
\t\tcolor: var(--text-secondary);
\t\tline-height: 1.4;
\t\tmargin-bottom: var(--space-xs);
\t\twhite-space: nowrap;
\t\toverflow: hidden;
\t\ttext-overflow: ellipsis;
\t}

\t.lightbox-info .lb-actor {
\t\tfont-size: 0.8125rem;
\t\tcolor: var(--accent);
\t\tmargin-bottom: var(--space-xs);
\t}

\t.lightbox-info .lb-actor a {
\t\tcolor: var(--accent);
\t}

\t.lightbox-info .lb-actor a:hover {
\t\ttext-decoration: underline;
\t}

\t.lightbox-info .lb-meta {
\t\tfont-size: 0.75rem;
\t\tcolor: var(--text-muted);
\t\tmargin-bottom: var(--space-sm);
\t\tdisplay: flex;
\t\tflex-wrap: wrap;
\t}

\t.lightbox-info .lb-meta span:not(:last-child)::after {
\t\tcontent: " · ";
\t\tmargin: 0 0.35em;
\t}

\t.lightbox-info .lb-tags {
\t\tdisplay: flex;
\t\tflex-wrap: wrap;
\t\tgap: 0.35rem;
\t\tmargin-bottom: var(--space-sm);
\t}

\t.lightbox-info .lb-tag {
\t\tpadding: 0.15rem 0.5rem;
\t\tbackground: var(--bg-body);
\t\tborder-radius: 999px;
\t\tfont-size: 0.6875rem;
\t}

\t.lightbox-info .lb-tag a {
\t\tcolor: var(--text-secondary);
\t}

\t.lightbox-info .lb-tag a:hover {
\t\tcolor: var(--accent);
\t}

\t.lightbox-info .lb-footer {
\t\tdisplay: flex;
\t\talign-items: center;
\t\tjustify-content: space-between;
\t\tpadding-top: var(--space-sm);
\t\tborder-top: 1px solid var(--border-light);
\t}

\t.lightbox-info .lb-actions {
\t\tdisplay: flex;
\t\tgap: var(--space-xs);
\t}

\t.lightbox-info .lb-btn {
\t\tpadding: 0.375rem 0.75rem;
\t\tborder: 1px solid var(--border-light);
\t\tborder-radius: var(--radius-sm);
\t\tbackground: transparent;
\t\tcolor: var(--text-secondary);
\t\tfont-size: 0.75rem;
\t\tcursor: pointer;
\t\ttransition: all var(--duration-fast) ease;
\t}

\t.lightbox-info .lb-btn:hover {
\t\tborder-color: var(--accent);
\t\tcolor: var(--accent);
\t}

\t.lightbox-info .lb-size {
\t\tfont-size: 0.75rem;
\t\tcolor: var(--text-muted);
\t\tfont-family: var(--font-mono);
\t}
\t
\t/* Close button */
\t.lightbox-close {
\t\tposition: absolute;
\t\ttop: var(--space-lg);
\t\tright: var(--space-lg);
\t\twidth: 44px;
\t\theight: 44px;
\t\tborder: none;
\t\tborder-radius: 50%;
\t\tbackground: rgba(255, 255, 255, 0.1);
\t\tcolor: var(--text-inverse);
\t\tfont-size: 1.5rem;
\t\tcursor: pointer;
\t\ttransition: all var(--duration-fast) ease;
\t\tbackdrop-filter: blur(8px);
\t}
\t
\t.lightbox-close:hover {
\t\tbackground: rgba(255, 255, 255, 0.2);
\t\ttransform: scale(1.05);
\t}

\t/* ========== Toast ========== */
\t.toast {
\t\tposition: fixed;
\t\tbottom: var(--space-xl);
\t\tleft: 50%;
\t\ttransform: translateX(-50%) translateY(20px);
\t\tpadding: 0.75rem 1.25rem;
\t\tbackground: var(--text-primary);
\t\tcolor: var(--text-inverse);
\t\tfont-size: 0.875rem;
\t\tborder-radius: var(--radius-md);
\t\tbox-shadow: var(--shadow-lg);
\t\topacity: 0;
\t\tvisibility: hidden;
\t\ttransition: all var(--duration-normal) var(--ease-out);
\t\tz-index: 2000;
\t\tmax-width: 90vw;
\t\tword-break: break-all;
\t}
\t
\t.toast.show {
\t\topacity: 1;
\t\tvisibility: visible;
\t\ttransform: translateX(-50%) translateY(0);
\t}

\t/* ========== Detail Mode (Table) ========== */
\t.detail-table {
\t\twidth: 100%;
\t\tborder-collapse: collapse;
\t\tbackground: var(--bg-card);
\t\tborder-radius: var(--card-radius);
\t\toverflow: hidden;
\t\tbox-shadow: var(--shadow-sm);
\t}
\t
\t.detail-table th,
\t.detail-table td {
\t\tpadding: 0.875rem 1rem;
\t\ttext-align: left;
\t\tborder-bottom: 1px solid var(--border-light);
\t\tfont-size: 0.875rem;
\t}
\t
\t.detail-table th {
\t\tbackground: var(--bg-body);
\t\tcolor: var(--text-muted);
\t\tfont-weight: 500;
\t\ttext-transform: uppercase;
\t\tfont-size: 0.75rem;
\t\tletter-spacing: 0.05em;
\t}
\t
\t.detail-table tr {
\t\ttransition: background var(--duration-fast) ease;
\t\tcursor: pointer;
\t}
\t
\t.detail-table tbody tr:hover {
\t\tbackground: rgba(45, 90, 123, 0.04);
\t}
\t
\t.detail-table a {
\t\tcolor: var(--text-secondary);
\t}
\t
\t.detail-table a:hover {
\t\tcolor: var(--accent);
\t}

\t/* ========== Text Mode (List) ========== */
\t.text-list {
\t\tlist-style: none;
\t\tbackground: var(--bg-card);
\t\tborder-radius: var(--card-radius);
\t\toverflow: hidden;
\t\tbox-shadow: var(--shadow-sm);
\t}
\t
\t.text-list li {
\t\tpadding: 0.875rem 1.25rem;
\t\tborder-bottom: 1px solid var(--border-light);
\t\tcursor: pointer;
\t\ttransition: background var(--duration-fast) ease;
\t}
\t
\t.text-list li:last-child {
\t\tborder-bottom: none;
\t}
\t
\t.text-list li:hover {
\t\tbackground: rgba(45, 90, 123, 0.04);
\t}
\t
\t.text-num {
\t\tcolor: var(--accent-red);
\t\tfont-weight: 600;
\t\tmargin-right: var(--space-md);
\t\tfont-family: var(--font-mono);
\t\tfont-size: 0.875rem;
\t}
\t
\t.text-title {
\t\tcolor: var(--text-primary);
\t}
\t
\t.text-actor {
\t\tcolor: var(--text-muted);
\t\tfont-size: 0.875rem;
\t}

\t/* ========== Utilities ========== */
\t.noselect {
\t\t-webkit-touch-callout: none;
\t\t-webkit-user-select: none;
\t\tuser-select: none;
\t}

\t/* ========== Responsive Header ========== */
\t@media (max-width: 768px) {
\t\t.header-inner {
\t\t\tpadding: 0 var(--space-md);
\t\t\tgap: var(--space-md);
\t\t}
\t\t
\t\t.logo {
\t\t\tfont-size: 1.125rem;
\t\t}
\t\t
\t\t.search-box {
\t\t\tmax-width: none;
\t\t\tflex: 1;
\t\t}
\t\t
\t\t.controls {
\t\t\tgap: 0;
\t\t}
\t\t
\t\t.ctrl-btn {
\t\t\twidth: 32px;
\t\t\theight: 32px;
\t\t\tfont-size: 1rem;
\t\t}
\t\t
\t\t.status-bar {
\t\t\tpadding: var(--space-sm) var(--space-md);
\t\t}
\t\t
\t\tmain#content {
\t\t\tpadding: 0 var(--space-md) var(--space-xl);
\t\t}
\t}

\t/* ========== Font Import ========== */
\t@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
\t</style>'''


def main():
    """測試用"""
    from scanner import VideoScanner
    import sys

    if len(sys.argv) < 2:
        print("用法: python generator.py <資料夾路徑> [輸出檔案]")
        sys.exit(1)

    input_dir = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "gallery_output.html"

    scanner = VideoScanner()
    videos = scanner.scan_directory(input_dir)

    generator = HTMLGenerator()
    generator.generate(videos, output_file)


if __name__ == "__main__":
    main()