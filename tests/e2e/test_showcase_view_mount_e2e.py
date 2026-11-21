"""片庫檢視的掛載與切換結束狀態。"""
import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.e2e
REPO = Path(__file__).resolve().parents[2]
ROOT = '[x-data="showcase"]'


@pytest.fixture(scope='module')
def server_url(tmp_path_factory):
    work = tmp_path_factory.mktemp('view_mount')
    home, data, library = (work / name for name in ('home', 'data', 'lib'))
    for directory in (home, data, library):
        directory.mkdir()
    cover = work / 'cover.jpg'
    Image.new('RGB', (640, 427), 'green').save(cover)
    for i in range(1, 13):
        number = f'MNT-{i:03d}'
        folder = library / number
        folder.mkdir()
        (folder / f'{number}.mp4').write_bytes(bytes([1]) * 2048)
        shutil.copyfile(cover, folder / f'{number}-fanart.jpg')
        (folder / f'{number}.nfo').write_text(
            f'<movie><title>{number}</title><num>{number}</num></movie>', encoding='utf-8')
    config = json.loads((REPO / 'web/config.default.json').read_text(encoding='utf-8'))
    def sanitize(value):
        if isinstance(value, dict):
            for key in value:
                if re.search(r'api[_-]?key|token|password|secret', key, re.I):
                    value[key] = ''
                else:
                    sanitize(value[key])
        elif isinstance(value, list):
            for item in value:
                sanitize(item)
    sanitize(config)
    config['gallery']['directories'] = [{'path': str(library), 'readonly': False, 'output_path': ''}]
    config['gallery']['show_table_list'] = True
    config['scraper']['external_manager'] = 'jellyfin'
    for source in config.get('sources', []):
        source['enabled'] = False
    for key in config.get('source_links', {}):
        config['source_links'][key] = False
    for section in ('metatube', 'translate'):
        config.setdefault(section, {})['enabled'] = False
    for section in config.get('ai_services', {}).values():
        if isinstance(section, dict):
            section['enabled'] = False
    config['general']['auto_check_update'] = False
    config['general']['tutorial_completed'] = True
    (data / '.layout.json').write_text(json.dumps({'version': 1, 'complete': True}))
    (data / 'config.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
    while True:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        if port not in (8000, 8001):
            break
    url = f'http://127.0.0.1:{port}'
    env = dict(os.environ, HOME=str(home), OPENAVER_DATA_DIR=str(data))
    with (work / 'server.log').open('wb') as log:
        process = subprocess.Popen([str(REPO / 'venv/bin/python'), '-m', 'uvicorn', 'web.app:app',
                                    '--host', '127.0.0.1', '--port', str(port)],
                                   cwd=REPO, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(f'{url}/api/showcase/videos', timeout=2) as response:
                        response.read()
                    break
                except (OSError, urllib.error.URLError):
                    if process.poll() is not None:
                        pytest.fail('隔離 server 啟動失敗')
                    time.sleep(.25)
            else:
                pytest.fail('隔離 server 啟動逾時')
            with urllib.request.urlopen(f'{url}/api/gallery/generate', timeout=600) as response:
                events = response.read().decode()
            assert '"type": "error"' not in events and '"type":"error"' not in events
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


@pytest.fixture
def page(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, chromium_sandbox=False)
        context = browser.new_context(viewport={'width': 1280, 'height': 720})
        page = context.new_page()
        page.goto(f'{server_url}/showcase')
        page.wait_for_function('''s => {
            const d = Alpine.$data(document.querySelector(s));
            return d && d.paginatedVideos.length === 12 &&
                document.querySelectorAll('.showcase-grid .av-card-preview:not(.hero-card)').length === 12;
        }''', arg=ROOT, timeout=30000)
        yield page
        context.close()
        browser.close()


def state(page):
    return page.evaluate('''() => {
        const selectors = ['.showcase-grid', '.showcase-table-wrapper', '.showcase-list-wrapper'];
        return selectors.map(s => {
            const el = document.querySelector(s), r = el?.getBoundingClientRect();
            return {count: document.querySelectorAll(s).length,
                visible: !!el && el.checkVisibility() && r.width > 0 && r.height > 0};
        });
    }''')


def settle(page, mode):
    page.wait_for_function('''([s, mode]) => {
        const d = Alpine.$data(document.querySelector(s));
        const el = document.querySelector({grid: '.showcase-grid', table: '.showcase-table-wrapper',
            list: '.showcase-list-wrapper'}[mode]);
        return d.mode === mode && el && el.checkVisibility() &&
            getComputedStyle(el).opacity === '1' &&
            (!window.gsap || !gsap.globalTimeline.getChildren(true, true, false).some(t => t.isActive()));
    }''', arg=[ROOT, mode], timeout=10000)


def switch(page, mode):
    page.evaluate('''([s, mode]) => Alpine.$data(document.querySelector(s)).switchMode(mode)''', [ROOT, mode])
    settle(page, mode)


def test_only_grid_is_mounted_on_load(page):
    assert page.locator('.showcase-table-wrapper').count() == 0
    assert page.locator('.showcase-list-wrapper').count() == 0
    assert page.locator('.showcase-grid .av-card-preview:not(.hero-card)').count() == 12


def test_switching_views_keeps_exactly_one_view_visible(page):
    for mode, index, item in [('table', 1, 'tbody tr'), ('list', 2, '.list-item'), ('grid', 0, '.av-card-preview:not(.hero-card)')]:
        switch(page, mode)
        views = state(page)
        assert [v['visible'] for v in views] == [i == index for i in range(3)]
        assert views[1]['count'] == (mode == 'table')
        assert views[2]['count'] == (mode == 'list')
        assert page.locator(f'{[".showcase-grid", ".showcase-table-wrapper", ".showcase-list-wrapper"][index]} {item}').count() == 12
    page.evaluate('''s => { const d = Alpine.$data(document.querySelector(s));
        d.switchMode('table'); d.switchMode('list'); d.switchMode('grid'); }''', ROOT)
    settle(page, 'grid')
    views = state(page)
    assert [v['visible'] for v in views] == [True, False, False]
    assert views[1]['count'] == views[2]['count'] == 0
    assert page.locator('.showcase-grid').evaluate("el => el.style.opacity") == ''
