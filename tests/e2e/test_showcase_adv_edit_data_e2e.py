"""以隔離片庫驗證進階編輯片商到 NFO、資料庫與燈箱的接線。"""
import hashlib
import json
import os
import random
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import expect

from core.gallery_scanner import load_prefix_mapping

pytestmark = pytest.mark.e2e
REPO = Path(__file__).resolve().parents[2]
ROOT = '[x-data="showcase"]'
NEW_MAKER = 'E2E手動片商'
OLD_MAKER = 'E2E原片商'


@pytest.fixture(scope='module')
def server_url(tmp_path_factory):
    work = tmp_path_factory.mktemp('adv_edit_data')
    home, data, library = (work / name for name in ('home', 'data', 'lib'))
    for directory in (home, data, library):
        directory.mkdir()
    mapping = load_prefix_mapping()
    prefixes = sorted(k for k, v in mapping.items() if re.fullmatch(r'[A-Za-z]{3,5}', k) and v)
    assert prefixes, '前綴對照表沒有符合條件的純英文字母前綴'
    prefix = prefixes[0]
    table_maker = mapping[prefix]
    assert len({table_maker, OLD_MAKER, NEW_MAKER}) == 3, '夾具片商必須互不相同'
    num = f'{prefix}-001'
    folder = library / num
    folder.mkdir()
    video = folder / f'{num}.mp4'
    if shutil.which('ffmpeg'):
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                        '-i', 'color=c=blue:s=640x360:d=2:r=1', '-c:v', 'libx264',
                        '-preset', 'ultrafast', '-g', '600', '-pix_fmt', 'yuv420p', str(video)],
                       check=True)
    else:
        video.write_bytes(b'0' * 2048)
    rng = random.Random(200)
    img = Image.new('RGB', (1600, 1066))
    pixels = img.load()
    for x in range(1600):
        color = tuple(rng.randrange(256) for _ in range(3))
        for y in range(1066):
            pixels[x, y] = color
    img.save(folder / f'{num}-fanart.jpg', 'JPEG', quality=90)
    nfo = folder / f'{num}.nfo'
    nfo.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<movie><title>E2E測試片</title><num>{num}</num><maker>{OLD_MAKER}</maker>
<release>2025-06-01</release><actor><name>測試女優</name></actor>
<tag>標籤甲</tag><tag>標籤乙</tag><genre>夾具類型</genre>
<website>https://example.invalid/e2e</website><x_e2e_unknown>keep-me</x_e2e_unknown>
<!-- e2e 註解 --></movie>''', encoding='utf-8')
    config = json.loads((REPO / 'web/config.default.json').read_text(encoding='utf-8'))
    config['gallery']['directories'] = [{'path': str(library), 'readonly': False, 'output_path': ''}]
    config['scraper']['external_manager'] = 'jellyfin'
    for source in config.get('sources', []):
        source['enabled'] = False
    for key in config.get('source_links', {}):
        config['source_links'][key] = False
    config['metatube']['enabled'] = False
    config['general']['tutorial_completed'] = True
    (data / '.layout.json').write_text(json.dumps({'version': 1, 'complete': True}))
    (data / 'config.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
    while True:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        if port not in range(8 * 1000, 8 * 1000 + 2):
            break
    url = f'http://127.0.0.1:{port}'
    env = dict(os.environ, HOME=str(home), OPENAVER_DATA_DIR=str(data))
    log_path = work / 'server.log'
    with log_path.open('wb') as log:
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
                        break
                    threading.Event().wait(0.25)
            else:
                pytest.fail('隔離 server 啟動逾時：\n' + '\n'.join(log_path.read_text(errors='replace').splitlines()[-40:]))
            if process.poll() is not None:
                pytest.fail('隔離 server 啟動失敗：\n' + '\n'.join(log_path.read_text(errors='replace').splitlines()[-40:]))
            with urllib.request.urlopen(f'{url}/api/gallery/generate', timeout=600) as response:
                events = response.read().decode()
            assert '"type": "error"' not in events and '"type":"error"' not in events, events[-800:]
            yield {'url': url, 'nfo': nfo, 'table_maker': table_maker}
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def _children(path):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.parse(path, parser=parser).getroot()
    return [(getattr(child.tag, '__name__', child.tag), child.text) for child in root]


def test_adv_edit_data_maker_end_state(page, server_url):
    url, nfo, table_maker = server_url['url'], server_url['nfo'], server_url['table_maker']
    before = _children(nfo)
    response = page.request.get(f'{url}/api/showcase/videos')
    assert response.ok, '無法讀取隔離片庫'
    videos = response.json()['videos']
    assert len(videos) == 1 and videos[0].get('has_cover'), '夾具片不存在或沒有封面'
    path = videos[0]['path']
    page.set_viewport_size({'width': 1280, 'height': 720})
    page.goto(f'{url}/showcase')
    cards = page.locator('.av-card-preview[data-flip-id]')
    cards.first.wait_for(state='visible', timeout=15000)
    card = next((item for item in cards.all() if item.get_attribute('data-flip-id') == path), None)
    assert card is not None, '牆上找不到夾具片'
    card.click(position={'x': 5, 'y': 5})
    page.wait_for_function("selector => !!window.Alpine && !!Alpine.$data(document.querySelector(selector))._lbFullLoaded", arg=ROOT, timeout=15000)
    maker = page.locator('.lbx-work--maker')
    expect(maker).to_have_text(table_maker)
    assert table_maker != OLD_MAKER, '初始片商須來自前綴表'
    page.locator('.lbx-more-btn').click()
    page.locator('.lbx-menu-item--advedit').click()
    page.wait_for_function("selector => { const d = Alpine.$data(document.querySelector(selector)); return d.advEditData?.state === 'ok' && !d.advEditDataLoading; }", arg=ROOT)
    row = page.locator('[data-row="data-maker"]')
    row.locator('.adv-edit-data-edit').click()
    row.locator('.adv-edit-input').fill(NEW_MAKER)
    row.locator('.adv-edit-data-save').click()
    page.wait_for_function("selector => { const d = Alpine.$data(document.querySelector(selector)); return !d._advEditCell && !d._advEditBusy; }", arg=ROOT)
    expect(row.locator('.adv-edit-data-text')).to_have_text(NEW_MAKER)
    expect(maker).to_have_text(NEW_MAKER)
    response = page.request.get(f'{url}/api/showcase/videos')
    assert response.ok and response.json()['videos'][0]['maker'] == NEW_MAKER, '資料庫片商未更新'
    after = _children(nfo)
    assert [(k, v) for k, v in before if k not in ('maker', 'openaver_manual_maker')] == [(k, v) for k, v in after if k not in ('maker', 'openaver_manual_maker')], '其他 NFO 元素改變'
    assert ('maker', NEW_MAKER) in after
    assert ('website', 'https://example.invalid/e2e') in after
    assert ('x_e2e_unknown', 'keep-me') in after
    assert ('Comment', ' e2e 註解 ') in after
    digest = hashlib.sha256(nfo.read_bytes()).hexdigest()
    with page.expect_response(lambda r: '/api/showcase/video/refresh' in r.url and r.request.method == 'POST') as refresh:
        page.locator('.adv-edit-update').click()
    assert refresh.value.ok, '更新請求失敗'
    assert refresh.value.json()['success'] is True, '更新請求回 success:false'
    page.wait_for_function("selector => { const d = Alpine.$data(document.querySelector(selector)); return !d._advEditCell && !d._advEditBusy && !d.advEditDataLoading; }", arg=ROOT)
    assert hashlib.sha256(nfo.read_bytes()).hexdigest() == digest, '更新改動了 NFO'
    response = page.request.get(f'{url}/api/showcase/videos')
    assert response.ok and response.json()['videos'][0]['maker'] == NEW_MAKER, '更新後資料庫片商改變'
    page.keyboard.press('Escape')
    page.wait_for_function("selector => { const d = Alpine.$data(document.querySelector(selector)); return !d.advEditOpen && d.lightboxOpen; }", arg=ROOT)
    expect(maker).to_have_text(NEW_MAKER)
