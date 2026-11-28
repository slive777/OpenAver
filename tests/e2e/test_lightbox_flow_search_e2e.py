"""搜尋頁及書籤燈箱開關與落地行為。"""
import io
import json
import re

import pytest
from PIL import Image
from playwright.sync_api import expect
from tests.e2e._lightbox_layout_server import REPO, serve  # noqa: PLC2701

pytestmark = pytest.mark.e2e
HOST = '.search-container'
ROOT = '.showcase-lightbox:not(.wishlist-lightbox)'
WISHLIST = '.wishlist-lightbox'
RESULT = '.search-grid .av-card-preview:not(.hero-card)'
HERO = '.search-grid .hero-card'
BOOKMARK = '.wishlist-grid .av-card-preview'
FONTS = re.compile(r'https://fonts\.(googleapis|gstatic)\.com/')
@pytest.fixture(scope='module')
def server_url(tmp_path_factory):
    work = tmp_path_factory.mktemp('flow_search')
    home, data, library = (work / name for name in ('home', 'data', 'lib'))
    for directory in (home, data, library): directory.mkdir()
    folder = library / 'FLOW-001'
    folder.mkdir()
    (folder / 'FLOW-001.mp4').write_bytes(bytes([1]) * 2048)
    Image.new('RGB', (640, 427), 'green').save(folder / 'FLOW-001-fanart.jpg')
    (folder / 'FLOW-001.nfo').write_text('<movie><title>FLOW-001</title><num>FLOW-001</num></movie>', encoding='utf-8')
    config = json.loads((REPO / 'web/config.default.json').read_text(encoding='utf-8'))
    config['gallery']['directories'] = [{'path': str(library), 'readonly': False, 'output_path': ''}]
    config['scraper']['external_manager'] = 'jellyfin'
    for source in config.get('sources', []): source['enabled'] = False
    for key in config.get('source_links', {}): config['source_links'][key] = False
    config['metatube']['enabled'] = False
    config['general']['tutorial_completed'] = True
    (data / '.layout.json').write_text(json.dumps({'version': 1, 'complete': True}))
    (data / 'config.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
    with serve(home, data, work) as url:
        yield url
@pytest.fixture(scope='module')
def data():
    rows = [dict(number=f'E2E-{i:03d}', title=f'E2E-{i:03d}', actors=['女優あおい'],
                 tags=['標籤'], date='2020-01-01', duration=120, maker='片商', series='系列',
                 director='導演', label='發行商', cover=f'https://img.e2e.invalid/{i}.jpg',
                 sample_images=[], source='e2e', url=f'https://e2e.invalid/{i}') for i in range(1, 7)]
    profile = dict(name='女優あおい', name_en='Aoi', age=25, birth='1995-01-01', height='160', cup='C',
                   bust='80', waist='60', hip='85', aliases=[], tags=[], img='/api/actresses/photo/x',
                   primary_text_source='wiki', is_favorite=False)
    wishlist = [dict(number=r['number'], title=r['title'], actresses=r['actors'], tags=r['tags'],
                     release_date=r['date'], maker=r['maker'], series=r['series'], director=r['director'],
                     label=r['label'], duration=r['duration'], sample_images=[], source_url=r['url'],
                     created_at='2026-01-01T00:00:00') for r in rows[:3]]
    buf = io.BytesIO()
    Image.new('RGB', (800, 534), 'blue').save(buf, format='PNG')
    return rows, profile, wishlist, buf.getvalue()
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
            if (document.querySelector(root).classList.contains('show')) break; } 
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
        const show = el.classList.contains('show'), opacity = getComputedStyle(el).opacity;
        const running = el.getAnimations().some(a => a.transitionProperty === 'opacity' && a.playState === 'running');
        return {inline, animating, show, opacity, running};
    }''', root)
    assert result['inline'] == '' and not result['animating'] and not result['show'] and result['running'], result
def observe_landing(page, card):
    page.evaluate('''card => {
        const img = document.querySelector(card).querySelector('img');
        window.landing = {sawGhost: false, opacity: null};
        const observer = new MutationObserver(records => {
            for (const record of records) for (const node of record.removedNodes)
                if (node.nodeType === 1 && (node.matches('[data-search-ghost]') || node.querySelector('[data-search-ghost]'))) {
                    window.landing = {sawGhost: true, opacity: getComputedStyle(img).opacity};
                    observer.disconnect();
                }
        });
        observer.observe(document.body, {childList: true, subtree: true});
    }''', card)
def backdrop_points(page, root, hero):
    points = page.evaluate('''([root, hero]) => {
        const el = document.querySelector(root), content = el.querySelector('.lightbox-content').getBoundingClientRect();
        const previous = el.style.display;
        el.style.display = 'none';
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
class Harness:
    def __init__(self, page, base, data, motion='no-preference'):
        self.page, self.base, self.data = page, base, data
        self.requests, self.bad = [], []
        page.set_viewport_size({'width': 1600, 'height': 900})
        page.on('request', lambda r: self.requests.append((r.method, r.url)))
        page.route('**/*', self.route)
        page.emulate_media(reduced_motion=motion)
        page.bring_to_front()
        page.goto(base + '/search')
        assert page.evaluate('document.visibilityState') == 'visible'
    def route(self, route):
        req, url = route.request, route.request.url
        path = url.split('?')[0]
        if FONTS.match(url):
            return route.fulfill(body='', content_type='text/css')
        if url.startswith(('http://', 'https://')) and not url.startswith(self.base + '/'):
            return route.abort()
        if path.endswith('/api/client-log'):
            return route.fulfill(status=204, body='')
        if '/api/search/stream' in path:
            event = dict(type='result', success=True, mode='actress', has_more=True,
                         data=self.data[0][:4], actress_profile=self.data[1])
            return route.fulfill(body='data: ' + json.dumps(event) + '\n\n', content_type='text/event-stream')
        if re.search(r'/api/search\?', url):
            return route.fulfill(json={'success': True, 'data': self.data[0][4:], 'has_more': False})
        responses = {'/api/actresses': {'success': True, 'actresses': []},
                     '/api/actress-aliases': {'groups': []},
                     '/api/wishlist/count': {'count': 3}, '/api/wishlist': self.data[2]}
        for suffix, response in responses.items():
            if req.method == 'GET' and path.endswith(suffix):
                return route.fulfill(json=response)
        if any(part in path for part in ('/api/proxy-image', '/api/actresses/photo/', '/api/wishlist/cover')):
            return route.fulfill(body=self.data[3], content_type='image/png')
        if req.method != 'GET':
            if '/api/wishlist' in path or path.endswith(('/api/actresses/favorite', '/api/scrape-single')):
                return route.fulfill(json={'success': True, 'actress': {}})
            self.bad.append((req.method, url))
            return route.abort()
        route.continue_()
    def search(self):
        self.page.fill('#searchQuery', 'あおい')
        self.page.click('#btnSubmit')
        expect(self.page.locator('#resultNumber')).to_have_text('E2E-001')
    def grid(self):
        self.page.click('.search-actions-right button:has(i.bi-grid-3x3), .search-actions-right button:has(i.bi-list-ul)')
        expect(self.page.locator(RESULT)).to_have_count(4)
    def open(self, card=RESULT, root=ROOT):
        ready(self.page, card, card == BOOKMARK)
        self.page.locator(card).first.click(position={'x': 20, 'y': 20})
        settled(self.page, root, HOST, wishlist=root == WISHLIST)
    def clean(self):
        assert not self.bad, self.bad
        assert not [u for _, u in self.requests if not (u.startswith((self.base, 'blob:', 'data:')) or FONTS.match(u))]
def prepare(page, server_url, data, entry='result', motion='no-preference'):
    h = Harness(page, server_url, data, motion)
    h.search()
    if entry == 'wishlist':
        page.click('#wishlistToggleBtn')
    else:
        h.grid()
    ready(page, BOOKMARK if entry == 'wishlist' else RESULT, entry == 'wishlist')
    if entry in ('hero', 'hero_reentry'):
        ready(page, HERO)
    return h
@pytest.mark.parametrize('entry', ['result', 'hero', 'wishlist', 'hero_reentry'])
def test_open_is_transparent_on_the_same_beat(page, server_url, data, entry):
    h = prepare(page, server_url, data, entry)
    root = WISHLIST if entry == 'wishlist' else ROOT
    card = BOOKMARK if entry == 'wishlist' else HERO if entry in ('hero', 'hero_reentry') else RESULT
    if entry == 'hero_reentry':
        h.open()
    open_beat(page, card, root)
    settled(page, root, HOST, wishlist=entry == 'wishlist')
    assert page.locator(root).evaluate('el => el.style.opacity') == ''
    if entry == 'hero_reentry':
        expect(page.locator(root + ' .lbx-actress-branch')).to_have_count(1)
        expect(page.locator(root + ' .actress-lb-title')).to_contain_text('女優あおい')
    else:
        page.keyboard.press('Escape')
        settled(page, root, HOST, opened=False, wishlist=entry == 'wishlist')
        ready(page, card, entry == 'wishlist')
        open_beat(page, card, root)
        settled(page, root, HOST, wishlist=entry == 'wishlist')
    h.clean()
@pytest.mark.parametrize('entry', ['result', 'hero', 'wishlist'])
def test_close_starts_css_fade_on_the_same_beat(page, server_url, data, entry):
    h = prepare(page, server_url, data, entry)
    root = WISHLIST if entry == 'wishlist' else ROOT
    card = BOOKMARK if entry == 'wishlist' else HERO if entry == 'hero' else RESULT
    h.open(card, root)
    close_beat(page, root)
    if entry == 'result':
        expect(page.locator(root + ' .lb-video-branch')).to_have_count(0)
    else:
        page.wait_for_function("root => {const e = document.querySelector(root); return getComputedStyle(e).opacity === '0' && e.style.opacity === ''}", arg=root)
    page.wait_for_function('host => Alpine.$data(document.querySelector(host)).lightboxCloseTimer === null', arg=HOST)
    h.clean()
def test_reduced_motion_open_ends_visible(page, server_url, data):
    h = prepare(page, server_url, data, motion='reduce')
    h.open()
    expect(page.locator(ROOT)).to_be_visible()
    expect(page.locator(ROOT)).to_have_css('opacity', '1')
    assert page.locator(ROOT).evaluate("el => el.classList.contains('show') && el.style.opacity === '' && getComputedStyle(el).opacity === '1'")
    h.clean()
def test_wishlist_cover_lands_opaque_on_grid(page, server_url, data):
    h = prepare(page, server_url, data, 'wishlist')
    h.open(BOOKMARK, WISHLIST)
    observe_landing(page, BOOKMARK)
    page.locator(WISHLIST + ' .lightbox-close').click()
    page.wait_for_function('window.landing.sawGhost')
    assert page.evaluate('window.landing') == {'sawGhost': True, 'opacity': '1'}
    h.clean()
def test_backdrop_click_reenters_hero(page, server_url, data):
    h = prepare(page, server_url, data, 'hero')
    h.open()
    points = backdrop_points(page, ROOT, HERO)
    page.mouse.click(**points['target'])
    expect(page.locator(ROOT + '.show .lbx-actress-branch')).to_have_count(1)
    settled(page, ROOT, HOST)
    page.keyboard.press('Escape')
    settled(page, ROOT, HOST, opened=False)
    h.open()
    page.mouse.click(**points['empty'])
    expect(page.locator(ROOT + '.show')).to_have_count(0)
    h.clean()
