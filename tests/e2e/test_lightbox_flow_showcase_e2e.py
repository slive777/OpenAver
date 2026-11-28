"""片庫牆燈箱開關與落地行為。"""
import json

import pytest
from PIL import Image
from playwright.sync_api import expect
from tests.e2e._lightbox_layout_server import REPO, serve  # noqa: PLC2701

pytestmark = pytest.mark.e2e
HOST = '[x-data="showcase"]'
ROOT = '.showcase-lightbox'
VIDEO = '.showcase-grid .av-card-preview[data-flip-id]:not(.hero-card)'
HERO = '.showcase-grid .hero-card'
ACTRESS = '.actress-grid .actress-card'

@pytest.fixture(scope='module')
def server_url(tmp_path_factory):
    from core.database import init_db
    from core.database.actress import Actress, ActressRepository
    from core.organizer import sanitize_filename

    work = tmp_path_factory.mktemp('flow_showcase')
    home, data, library = (work / name for name in ('home', 'data', 'lib'))
    for directory in (home, data, library):
        directory.mkdir()
    db = data / 'openaver.db'
    init_db(db)
    photos = data / 'Gfriends'
    photos.mkdir()
    for name in ('甲女優', '乙女優'):
        ActressRepository(db).save(Actress(name=name, photo_source='gfriends', primary_text_source='ai'))
        Image.new('RGB', (300, 400), 'blue').save(photos / f'{sanitize_filename(name)}.jpg')
    for i in range(1, 7):
        number = f'FLOW-{i:03d}'
        folder = library / number
        folder.mkdir()
        (folder / f'{number}.mp4').write_bytes(bytes([1]) * 2048)
        Image.new('RGB', (640, 427), 'green').save(folder / f'{number}-fanart.jpg')
        actors = '<actor><name>甲女優</name></actor><actor><name>乙女優</name></actor>'
        (folder / f'{number}.nfo').write_text(
            f'<movie><title>{number}</title><num>{number}</num>{actors}</movie>', encoding='utf-8')
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
    with serve(home, data, work) as url:
        yield url

def errors_for(page):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' and not (
        msg.text.startswith('Failed to load resource') and '/api/actress-aliases/' in msg.location.get('url', '')
    ) else None)
    return errors

def ready(page, card, loaded=False):
    expect(page.locator(card).first).to_be_visible()
    page.wait_for_function('''([s, loaded]) => {
        const img = document.querySelector(s)?.querySelector('img');
        return img && img.complete && img.naturalWidth > 0 &&
            (!loaded || img.classList.contains('cover-loaded'));
    }''', arg=[card, loaded])

def open_beat(page, card, root):
    result = page.evaluate('''async ([card, root]) => {
        document.querySelector(card).click();
        for (let i = 0; i < 3; i++) {
            await new Promise(queueMicrotask);
            if (document.querySelector(root).classList.contains('show')) break;
        }
        const el = document.querySelector(root);
        return {show: el.classList.contains('show'), opacity: getComputedStyle(el).opacity};
    }''', [card, root])
    assert result == {'show': True, 'opacity': '0'}, result

def settled(page, root, host, opened=True, wishlist=False):
    page.wait_for_function('''([root, host, opened, wishlist]) => {
        const el = document.querySelector(root), d = Alpine.$data(document.querySelector(host));
        return el && (opened ? el.classList.contains('show') && el.style.opacity === '' &&
            !el.classList.contains('gsap-animating') : !el.classList.contains('show')) &&
            !document.querySelector('[data-search-ghost]') &&
            (wishlist || d._lightboxAnimating !== true);
    }''', arg=[root, host, opened, wishlist])

def close_beat(page, root):
    result = page.evaluate('''async root => {
        const el = document.querySelector(root);
        el.querySelector('.lightbox-close').click();
        await new Promise(queueMicrotask);
        const inline = el.style.opacity, animating = el.classList.contains('gsap-animating');
        const show = el.classList.contains('show');
        const opacity = getComputedStyle(el).opacity;
        const running = el.getAnimations().some(a => a.transitionProperty === 'opacity' && a.playState === 'running');
        return {inline, animating, show, opacity, running};
    }''', root)
    assert result['inline'] == '' and not result['animating'] and not result['show'] and result['running'], result

def observe_landing(page, card):
    page.evaluate('''card => {
        const img = document.querySelector(card).querySelector('img');
        window.landing = {sawGhost: false, opacity: null};
        const observer = new MutationObserver(records => {
            for (const record of records) for (const node of record.removedNodes) {
                if (node.nodeType === 1 && (node.matches('[data-search-ghost]') || node.querySelector('[data-search-ghost]'))) {
                    window.landing = {sawGhost: true, opacity: getComputedStyle(img).opacity};
                    observer.disconnect();
                }
            }
        });
        observer.observe(document.body, {childList: true, subtree: true});
    }''', card)

def backdrop_points(page, root, hero):
    points = page.evaluate('''([root, hero]) => {
        const el = document.querySelector(root), content = el.querySelector('.lightbox-content').getBoundingClientRect();
        const previous = el.style.display; el.style.display = 'none';
        let target = null, empty = null, scanned = 0;
        for (let y = 5; y < innerHeight; y += 5) for (let x = 5; x < innerWidth; x += 5) {
            if (x >= content.left && x <= content.right && y >= content.top && y <= content.bottom) continue;
            scanned++;
            const hit = document.elementFromPoint(x, y);
            if (!target && hit?.closest(hero)) target = {x, y};
            if (!empty && hit && !hit.closest('.av-card-preview, .actress-card')) empty = {x, y};
        }
        el.style.display = previous;
        return {target, empty, scanned};
    }''', [root, hero])
    assert points['target'] and points['empty'], points
    return points

@pytest.fixture
def env(page, server_url):
    page.set_viewport_size({'width': 1600, 'height': 900})
    errors = errors_for(page)
    def route(r):
        url = r.request.url
        if url.startswith(('https://fonts.googleapis.com/', 'https://fonts.gstatic.com/')):
            r.fulfill(body='', content_type='text/css')
        elif url.startswith(('http://', 'https://')) and not url.startswith(server_url + '/'):
            r.abort()
        else:
            r.continue_()
    page.route('**/*', route)
    return page, server_url, errors

def start(env, motion='no-preference', hero=False, actress=False):
    page, url, _ = env
    page.emulate_media(reduced_motion=motion)
    page.bring_to_front()
    page.goto(url + '/showcase?sort=number&order=asc')
    assert page.evaluate('document.visibilityState') == 'visible'
    if hero:
        page.locator('input[x-model="search"]').fill('甲女優')
        ready(page, HERO, True)
    if actress:
        page.evaluate('''async host => {const d = Alpine.$data(document.querySelector(host));
            d.showFavoriteActresses = true; await d.loadActresses();}''', HOST)
        ready(page, ACTRESS)
    else:
        ready(page, VIDEO, True)

def open_real(page, card=VIDEO):
    page.locator(card).first.click(position={'x': 20, 'y': 20})
    settled(page, ROOT, HOST)

@pytest.mark.parametrize('entry', ['video', 'actress', 'hero_reentry'])
def test_open_is_transparent_on_the_same_beat(env, entry):
    page, _, errors = env
    start(env, hero=entry == 'hero_reentry', actress=entry == 'actress')
    card = ACTRESS if entry == 'actress' else HERO if entry == 'hero_reentry' else VIDEO
    if entry == 'hero_reentry':
        open_real(page)
    open_beat(page, card, ROOT)
    settled(page, ROOT, HOST)
    assert page.locator(ROOT).evaluate("el => el.style.opacity") == ''
    if entry == 'hero_reentry':
        page.wait_for_function("host => Alpine.$data(document.querySelector(host)).currentLightboxActress?.name === '甲女優'", arg=HOST)
    if entry == 'video':
        page.keyboard.press('Escape')
        settled(page, ROOT, HOST, opened=False)
        ready(page, card, True)
        open_beat(page, card, ROOT)
        settled(page, ROOT, HOST)
    assert not errors, errors

@pytest.mark.parametrize('entry', ['video', 'actress'])
def test_close_starts_css_fade_on_the_same_beat(env, entry):
    page, _, errors = env
    start(env, actress=entry == 'actress')
    open_real(page, ACTRESS if entry == 'actress' else VIDEO)
    close_beat(page, ROOT)
    if entry == 'video':
        expect(page.locator(ROOT + ' .lb-video-branch')).to_have_count(0)
    else:
        page.wait_for_function("root => {const e = document.querySelector(root); return getComputedStyle(e).opacity === '0' && e.style.opacity === ''}", arg=ROOT)
    page.wait_for_function('host => Alpine.$data(document.querySelector(host)).lightboxCloseTimer === null', arg=HOST)
    assert not errors, errors

def test_reduced_motion_open_ends_visible(env):
    page, _, errors = env
    start(env, motion='reduce')
    open_real(page)
    expect(page.locator(ROOT)).to_be_visible()
    expect(page.locator(ROOT)).to_have_css('opacity', '1')
    assert page.locator(ROOT).evaluate("el => el.classList.contains('show') && el.style.opacity === '' && getComputedStyle(el).opacity === '1'")
    assert not errors, errors

def test_cover_lands_opaque_on_grid(env):
    page, _, errors = env
    start(env)
    open_real(page)
    observe_landing(page, VIDEO)
    page.locator(ROOT + ' .lightbox-close').click()
    page.wait_for_function('window.landing.sawGhost')
    assert page.evaluate('window.landing') == {'sawGhost': True, 'opacity': '1'}
    assert not errors, errors

def test_backdrop_click_reenters_hero(env):
    page, _, errors = env
    start(env, hero=True)
    open_real(page)
    points = backdrop_points(page, ROOT, HERO)
    page.mouse.click(**points['target'])
    expect(page.locator(ROOT + '.show .lbx-actress-branch')).to_have_count(1)
    page.wait_for_function("host => Alpine.$data(document.querySelector(host)).currentLightboxActress?.name === '甲女優'", arg=HOST)
    settled(page, ROOT, HOST)
    page.keyboard.press('Escape')
    settled(page, ROOT, HOST, opened=False)
    ready(page, VIDEO, True)
    open_real(page)
    page.mouse.click(**points['empty'])
    expect(page.locator(ROOT + '.show')).to_have_count(0)
    assert not errors, errors
