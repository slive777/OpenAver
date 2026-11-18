"""燈箱動態結束後的畫面狀態。"""
import json
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e
REPO = Path(__file__).resolve().parents[2]
ROOT = '[x-data="showcase"]'
CARDS = '.av-card-preview[data-flip-id]:not(.hero-card)'
LB = '.showcase-lightbox.show'


@pytest.fixture(scope='module')
def server_url(tmp_path_factory):
    from core.database import init_db
    from core.database.actress import Actress, ActressRepository
    from core.organizer import sanitize_filename

    work = tmp_path_factory.mktemp('lightbox_motion')
    home, data, library = (work / name for name in ('home', 'data', 'lib'))
    for directory in (home, data, library):
        directory.mkdir()
    db = data / 'openaver.db'
    init_db(db)
    photos = data / 'Gfriends'
    photos.mkdir(parents=True)
    for name, color in [('甲女優', 'red'), ('乙女優', 'blue')]:
        ActressRepository(db).save(Actress(name=name, photo_source='gfriends', primary_text_source='ai'))
        Image.new('RGB', (1600, 800), color).save(photos / f'{sanitize_filename(name)}.jpg')
    cover = work / 'cover.jpg'
    Image.new('RGB', (640, 427), 'green').save(cover)
    video = work / 'video.mp4'
    if shutil.which('ffmpeg'):
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                        '-i', 'color=c=blue:s=640x360:d=2:r=1', '-c:v', 'libx264',
                        '-preset', 'ultrafast', '-g', '600', '-pix_fmt', 'yuv420p', str(video)], check=True)
    else:
        video.write_bytes(bytes([1]) * 2048)
    for i in [*range(1, 15), 101, 102]:
        number = f'MOT-{i:03d}'
        folder = library / number
        folder.mkdir()
        shutil.copyfile(video, folder / f'{number}.mp4')
        shutil.copyfile(cover, folder / f'{number}-fanart.jpg')
        extra = '<plot>故事</plot><maker>片商</maker><set><name>系列</name></set><release>2025-06-01</release>' if i == 1 else ''
        name = '甲女優' if i < 100 else '乙女優'
        (folder / f'{number}.nfo').write_text(
            f'<movie><title>{number}</title><num>{number}</num><actor><name>{name}</name></actor>{extra}</movie>',
            encoding='utf-8')
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
        if port not in (8000, 8001):
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
                pytest.fail('隔離 server 啟動逾時')
            if process.poll() is not None:
                pytest.fail('隔離 server 啟動失敗：' + log_path.read_text(errors='replace'))
            with urllib.request.urlopen(f'{url}/api/gallery/generate', timeout=600) as response:
                events = response.read().decode()
            assert '"type": "error"' not in events and '"type":"error"' not in events, events[-800:]
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def clean_strip(page, count):
    page.wait_for_function('''count => {
        const cells = [...document.querySelectorAll('.showcase-lightbox.show .lbx-ap-cell')];
        return cells.length === count && [...cells, ...cells.flatMap(c => [...c.children])]
            .every(el => !/opacity|transform/.test(el.getAttribute('style') || ''))
            && !document.querySelector('[data-lbx-ghost]');
    }''', arg=count, timeout=10000)


def focus_end(page, actress=False):
    lb = page.locator(LB)
    normal = lb.locator('.lbx-face--normal')
    edit = lb.locator('.lbx-face--edit')
    expect(edit).to_be_visible(timeout=30000)
    expect(normal).to_be_hidden(timeout=10000)
    if actress:
        expect(edit.locator('.lbx-focal-hint')).to_be_visible(timeout=10000)
    yes = edit.locator('.lb-action-btn--success')
    no = edit.locator('.lb-action-btn--danger')
    points = []
    for button in (yes, no):
        point = button.evaluate('''el => {
            const r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
            return {x, y, left: r.left, hit: document.elementFromPoint(x, y)?.closest('button') === el};
        }''')
        assert point['hit'], point
        points.append(point)
    assert points[0]['left'] < points[1]['left']
    page.mouse.click(points[1]['x'], points[1]['y'])
    expect(normal).to_be_visible(timeout=10000)
    expect(edit).to_be_hidden(timeout=10000)
    page.wait_for_function("!document.querySelector('[class*=lbx-face-t-]')", timeout=10000)


@pytest.mark.parametrize('reduced_motion', ['no-preference', 'reduce'])
def test_lightbox_motion_end_states(browser, server_url, reduced_motion):
    context = browser.new_context(viewport={'width': 1280, 'height': 720}, reduced_motion=reduced_motion)
    try:
        page = context.new_page()
        errors, console_errors = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' and not (
            msg.text.startswith('Failed to load resource') and '/api/actress-aliases/' in msg.location.get('url', '')
        ) else None)
        assert page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches") == (reduced_motion == 'reduce')
        page.goto(f'{server_url}/showcase')
        assert page.evaluate('document.visibilityState') == 'visible'
        page.locator(CARDS).first.wait_for(state='visible', timeout=10000)
        page.evaluate("s => Alpine.$data(document.querySelector(s)).cardShape = 'poster'", ROOT)
        card = page.locator(CARDS).filter(has_text='MOT-001').first
        box = card.bounding_box()
        assert box
        card.click(position={'x': box['width'] * .2, 'y': box['height'] * .2})
        page.wait_for_function('s => Alpine.$data(document.querySelector(s))._lbFullLoaded', arg=ROOT, timeout=10000)
        lb = page.locator(LB)
        info = lb.locator('.lbx-info-btn')
        try:
            expect(info).to_be_visible(timeout=10000)
        except AssertionError:
            pytest.fail(f'影片資訊入口不可見：count={info.count()}')
        info.click()
        expect(page.locator('.lbx-pop[data-kind="info"].is-placed')).to_be_visible(timeout=10000)
        page.keyboard.press('Escape')
        expect(page.locator('.lbx-pop')).to_have_count(0, timeout=10000)
        expect(page.locator('[data-lbx-ghost]')).to_have_count(0, timeout=10000)
        expect(lb).to_be_visible()
        lb.locator('.lightbox-cover').hover()
        lb.locator('.lbx-more-btn').click()
        focal = page.locator('.lbx-menu-item--focal')
        try:
            expect(focal).to_be_visible(timeout=10000)
        except AssertionError:
            pytest.fail(f'影片對焦入口不可見：count={focal.count()}')
        focal.click()
        focus_end(page)
        page.keyboard.press('Escape')
        expect(page.locator(LB)).to_have_count(0, timeout=10000)
        page.evaluate('''async s => { const d = Alpine.$data(document.querySelector(s));
            d.showFavoriteActresses = true; await d.loadActresses(); }''', ROOT)
        page.wait_for_function("s => Alpine.$data(document.querySelector(s)).paginatedActresses.some(a => a.name === '甲女優')", arg=ROOT, timeout=10000)
        page.evaluate('''s => { const d = Alpine.$data(document.querySelector(s));
            d.openActressLightbox(d.paginatedActresses.findIndex(a => a.name === '甲女優')); }''', ROOT)
        clean_strip(page, 8)
        page.keyboard.press('ArrowRight')
        page.wait_for_function("document.querySelectorAll('.showcase-lightbox.show .lbx-ap-cell').length < 8", timeout=10000)
        page.keyboard.press('ArrowLeft')
        clean_strip(page, 8)
        for _ in range(5):
            page.locator(f'{LB} .lbx-ap-next').click()
        page.wait_for_function("s => Alpine.$data(document.querySelector(s)).lbxApStart === 12", arg=ROOT, timeout=10000)
        expect(page.locator(f'{LB} .lbx-ap-film')).to_have_count(2, timeout=10000)
        clean_strip(page, 4)
        films = page.locator(f'{LB} .lbx-ap-film')
        films.nth(0).click()
        expect(page.locator(f'{LB} .lbx-ap-cover')).to_be_visible(timeout=10000)
        expect(films.nth(0)).to_have_attribute('aria-pressed', 'true')
        films.nth(1).click()
        expect(page.locator('[data-lbx-ghost]')).to_have_count(0, timeout=10000)
        expect(page.locator(f'{LB} .lbx-ap-cover')).to_have_count(1)
        expect(films.nth(1)).to_have_attribute('aria-pressed', 'true')
        page.locator(f'{LB} .lbx-ap-photo').click()
        expect(page.locator(f'{LB} .lbx-ap-cover')).to_have_count(0, timeout=10000)
        expect(page.locator('[data-lbx-ghost]')).to_have_count(0, timeout=10000)
        try:
            page.wait_for_function("s => Alpine.$data(document.querySelector(s))._actressPhotoWideEnough === true", arg=ROOT, timeout=10000)
        except PlaywrightTimeoutError:
            wide = page.evaluate("s => Alpine.$data(document.querySelector(s))._actressPhotoWideEnough", ROOT)
            pytest.fail(f'女優照片寬度判定：{wide!r}')
        wide = page.evaluate("s => Alpine.$data(document.querySelector(s))._actressPhotoWideEnough", ROOT)
        if wide is not True:
            pytest.fail(f'女優照片寬度判定：{wide!r}')
        actress_focal = page.locator(f'{LB} .lb-mask-btn')
        try:
            expect(actress_focal).to_be_visible(timeout=10000)
        except AssertionError:
            pytest.fail(f'女優對焦入口不可見：count={actress_focal.count()}')
        actress_focal.click()
        focus_end(page, actress=True)
        assert not errors, errors
        assert not console_errors, console_errors
    finally:
        context.close()
