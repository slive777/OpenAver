"""精選三級在真實瀏覽器與隔離片庫之間的終態契約。"""
import json
import os
import random
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
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e
REPO = Path(__file__).resolve().parents[2]
ROOT = '[x-data="showcase"]'
CARDS = '.av-card-preview[data-flip-id]:not(.hero-card)'


@pytest.fixture(scope='module')
def server_url(tmp_path_factory):
    work = tmp_path_factory.mktemp('pick_tiers')
    home, data, library = (work / name for name in ('home', 'data', 'lib'))
    for directory in (home, data, library):
        directory.mkdir()
    rng = random.Random(201)
    image = Image.new('RGB', (640, 427))
    for x in range(640):
        color = tuple(rng.randrange(256) for _ in range(3))
        for y in range(427):
            image.putpixel((x, y), color)
    cover = work / 'cover.jpg'
    image.save(cover, 'JPEG', quality=90)
    for i, color in enumerate(('red', 'green', 'blue', 'yellow'), 1):
        number = f'PICK-{i:03d}'
        folder = library / number
        folder.mkdir()
        video = folder / f'{number}.mp4'
        if shutil.which('ffmpeg'):
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                            '-i', f'color=c={color}:s=640x360:d=2:r=1', '-c:v', 'libx264',
                            '-preset', 'ultrafast', '-g', '600', '-pix_fmt', 'yuv420p', str(video)],
                           check=True)
        else:
            video.write_bytes(bytes([i]) * 2048)
        shutil.copyfile(cover, folder / f'{number}-fanart.jpg')
        (folder / f'{number}.nfo').write_text(
            f'<movie><title>{number}</title><num>{number}</num></movie>', encoding='utf-8')
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


def videos(page, url):
    response = page.request.get(f'{url}/api/showcase/videos')
    assert response.ok
    return {v['number']: v for v in response.json()['videos']}


def reset(page, url):
    items = videos(page, url)
    assert set(items) == {f'PICK-{i:03d}' for i in range(1, 5)}
    for i, tier in enumerate(('gold', 'silver', 'bronze', 'none'), 1):
        response = page.request.post(f'{url}/api/user-rating', data={
            'file_path': items[f'PICK-{i:03d}']['path'], 'tier': tier})
        assert response.ok, response.text()
    return {number: item['path'] for number, item in items.items()}


def card_for(page, path):
    return page.locator(CARDS).filter(has=page.locator('.av-num')).locator(
        f'xpath=self::*[@data-flip-id={json.dumps(path)}]')


def open_wall(page, url):
    page.set_viewport_size({'width': 1280, 'height': 720})
    page.goto(f'{url}/showcase')
    page.locator(CARDS).first.wait_for(state='visible', timeout=10000)


def open_lightbox(page, path):
    card_for(page, path).click(position={'x': 5, 'y': 5})
    page.wait_for_function(
        'selector => !!window.Alpine && !!Alpine.$data(document.querySelector(selector))._lbFullLoaded',
        arg=ROOT, timeout=10000)


def wait_rating(page, url, number, value):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if videos(page, url)[number]['user_rating'] == value:
            return
        threading.Event().wait(0.1)
    pytest.fail(f'{number} 等級未到 {value}')


def tier_is(page, locator, tier):
    if tier is None:
        page.wait_for_function('el => !el.hasAttribute("data-pick-tier")', arg=locator.element_handle(), timeout=10000)
    else:
        expect(locator).to_have_attribute('data-pick-tier', tier, timeout=10000)


def cycle(page, url, paths, steps):
    number = 'PICK-004'
    star = page.locator('.lightbox-content .pick-star')
    lightbox = page.locator('.lightbox-content')
    previous = 0
    for tier, value in steps:
        page.wait_for_function('el => el.getAttribute("aria-busy") !== "true"',
                               arg=star.element_handle(), timeout=10000)
        wait_rating(page, url, number, previous)
        star.click()
        wait_rating(page, url, number, value)
        tier_is(page, lightbox, tier)
        tier_is(page, card_for(page, paths[number]), tier)
        previous = value


def test_lightbox_cycles_tiers(page, server_url):
    paths = reset(page, server_url)
    open_wall(page, server_url)
    for i, tier in enumerate(('gold', 'silver', 'bronze'), 1):
        tier_is(page, card_for(page, paths[f'PICK-{i:03d}']), tier)
    open_lightbox(page, paths['PICK-004'])
    cycle(page, server_url, paths, [('gold', 3), ('silver', 2), ('bronze', 1), (None, 0), ('gold', 3)])
    page.keyboard.press('Escape')


def test_pick_filter_tiers(page, server_url):
    paths = reset(page, server_url)
    open_wall(page, server_url)
    page.locator('.toolbar-controls .btn-icon:has(.bi-funnel)').locator('visible=true').click()
    page.locator('.dropdown-item-pick').click()
    chip = page.locator('.filter-pill-group:not(.actress-filter-pill-group) .filter-pill-value').filter(has_text='精選')
    popover = page.locator('.pill-editor-popover[aria-labelledby="pick-editor-title"]')

    def check(text, numbers):
        expect(chip).to_have_text(text, timeout=10000)
        expected = sorted(paths[f'PICK-{i:03d}'] for i in numbers)
        page.wait_for_function(
            '([selector, paths]) => JSON.stringify([...document.querySelectorAll(selector)].filter(e => e.getClientRects().length).map(e => e.dataset.flipId).sort()) === JSON.stringify(paths)',
            arg=[CARDS, expected], timeout=10000)

    check('★精選', (1, 2, 3))
    for selector, label, text, numbers in [
        ('.pill-editor-modes--tiers', '銀', '★精選 ≥銀', (1, 2)),
        ('.pill-editor-modes:not(.pill-editor-modes--tiers)', '≤', '★精選 ≤銀', (2, 3)),
        ('.pill-editor-modes:not(.pill-editor-modes--tiers)', '=', '★精選 =銀', (2,)),
        ('.pill-editor-modes--tiers', '銅', '★精選 =銅', (3,)),
    ]:
        chip.click()
        expect(popover).to_be_visible()
        popover.locator(selector).locator('button').filter(has_text=label).click()
        expect(popover).to_be_hidden()
        check(text, numbers)


def test_reduced_motion_cycles_tiers(browser, server_url):
    context = browser.new_context(viewport={'width': 1280, 'height': 720}, reduced_motion='reduce')
    try:
        page = context.new_page()
        assert page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
        paths = reset(page, server_url)
        open_wall(page, server_url)
        open_lightbox(page, paths['PICK-004'])
        cycle(page, server_url, paths, [('gold', 3), ('silver', 2), ('bronze', 1)])
        page.keyboard.press('Escape')
    finally:
        context.close()
