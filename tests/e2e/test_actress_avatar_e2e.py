"""收藏女優小頭像在三個頁面的結束狀態。"""
import io
import json
import re

import pytest
from PIL import Image
from playwright.sync_api import expect

from tests.e2e._insights_motion_helpers import load_ready  # noqa: PLC2701
from tests.e2e._lightbox_layout_server import REPO, serve  # noqa: PLC2701

pytestmark = pytest.mark.e2e
A, B, C = '特寫あおい', '原圖みさき', '無圖ゆき'
NAMES = [A, B, C] + [f'女優{i:02d}' for i in range(1, 13)]
LB = '.showcase-lightbox.show'
FONTS = re.compile(r'https://fonts\.(googleapis|gstatic)\.com/')

@pytest.fixture(scope='module')
def server_url(tmp_path_factory):
    from core.database import init_db
    from core.database.actress import Actress, ActressRepository
    from core.organizer import sanitize_filename

    work = tmp_path_factory.mktemp('actress_avatar')
    home, data, library = (work / name for name in ('home', 'data', 'lib'))
    for directory in (home, data, library):
        directory.mkdir()
    db = data / 'openaver.db'
    init_db(db)
    photos = data / 'Gfriends'
    photos.mkdir()
    for name in (A, B, C):
        ActressRepository(db).save(Actress(name=name, photo_source='gfriends', primary_text_source='ai',
                                          birth='1995-01-01', height='160', cup='C'))
        if name != C:
            Image.new('RGB', (300, 400), 'blue').save(photos / f'{sanitize_filename(name)}.jpg')
    for i, names in enumerate((NAMES[:3], NAMES, NAMES[:2], NAMES[:2]), 1):
        number = f'TST-{i:03d}'
        folder = library / number
        folder.mkdir()
        (folder / f'{number}.mp4').write_bytes(bytes([1]) * 2048)
        Image.new('RGB', (640, 427), 'green').save(folder / f'{number}-fanart.jpg')
        actors = ''.join(f'<actor><name>{name}</name></actor>' for name in names)
        (folder / f'{number}.nfo').write_text(
            f'<movie><title>{number}</title><num>{number}</num>{actors}<genre>標籤</genre><maker>片商</maker><premiered>2020-01-0{i}</premiered></movie>', encoding='utf-8')
    config = json.loads((REPO / 'web/config.default.json').read_text(encoding='utf-8'))
    config['gallery']['directories'] = [{'path': str(library), 'readonly': False, 'output_path': ''}]
    config['scraper']['external_manager'] = 'jellyfin'
    for source in config.get('sources', []):
        source['enabled'] = False
    for key in config.get('source_links', {}):
        config['source_links'][key] = False
    config['metatube']['enabled'] = False
    config['general']['tutorial_completed'] = True
    config['focal_device'] = {'disabled': True, 'set_by_user': True, 'consecutive_timeout_count': 0, 'judged_at_version': ''}
    (data / '.layout.json').write_text(json.dumps({'version': 1, 'complete': True}))
    (data / 'config.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
    with serve(home, data, work) as url:
        yield url

@pytest.fixture
def site(browser, server_url):
    context = browser.new_context(viewport={'width': 1440, 'height': 900}, reduced_motion='reduce')
    page = context.new_page()
    page.bring_to_front()
    assert page.evaluate('document.visibilityState') == 'visible'
    errors, requests, crops = [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' and not (
        msg.text.startswith('Failed to load resource') and '/api/actress-aliases/' in msg.location.get('url', '')
    ) else None)
    page.on('request', lambda req: requests.append(req.url))
    buf = io.BytesIO()
    Image.new('RGB', (128, 128), 'red').save(buf, format='PNG')
    png = buf.getvalue()
    rows = [dict(number=f'E2E-{i:03d}', title=f'E2E-{i:03d}', actors=names, tags=['標籤'],
                 date='2020-01-01', cover=f'https://img.e2e.invalid/{i}.jpg', source='e2e')
            for i, names in enumerate((NAMES[:3], NAMES), 1)]
    wishlist = [dict(number=r['number'], title=r['title'], actresses=r['actors'], tags=r['tags'],
                     created_at='2026-01-01T00:00:00') for r in rows]

    def route_request(route):
        req, url = route.request, route.request.url
        path = url.split('?')[0]
        if FONTS.match(url): return route.fulfill(body='', content_type='text/css')
        if path.endswith('/api/client-log'): return route.fulfill(status=204, body='')
        if req.method != 'GET': return route.fulfill(json={'success': True})
        if '/api/actresses/face-crop/' in path:
            crops.append(url)
            return route.fulfill(body=png, content_type='image/png')
        if path.endswith('/api/actresses'):
            response = route.fetch(); payload = response.json()
            for actress in payload['actresses']:
                if actress['name'] == A: actress['avatar_url'] = '/api/actresses/face-crop/e2e'
            return route.fulfill(response=response, json=payload)
        if path.endswith('/api/insights/snapshot'):
            response = route.fetch(); payload = response.json()
            payload['actressFavorites'][A]['avatarUrl'] = '/api/actresses/face-crop/e2e'
            return route.fulfill(response=response, json=payload)
        if '/api/search/stream' in path:
            event = dict(type='result', success=True, mode='actress', has_more=False, data=rows)
            return route.fulfill(body='data: ' + json.dumps(event) + '\n\n', content_type='text/event-stream')
        if path.endswith('/api/wishlist/count'): return route.fulfill(json={'count': 2})
        if path.endswith('/api/wishlist'): return route.fulfill(json=wishlist)
        if '/api/proxy-image' in path or '/api/wishlist/cover' in path:
            return route.fulfill(body=png, content_type='image/png')
        return route.continue_()

    page.route('**/*', route_request)
    yield page
    context.close()
    assert not errors, errors
    assert not [u for u in requests if not (u.startswith((server_url, 'blob:', 'data:')) or FONTS.match(u))]
    assert crops
def settled(page):
    page.wait_for_function('''s => new Promise(resolve => { let old='', n=0; function tick() {
      const root=document.querySelector(s), a=root?.querySelector('.lightbox-cover'), b=root?.querySelector('.lbx-meta');
      if (!a || !b || root.querySelector('.lbx-people-row.is-measuring')) return requestAnimationFrame(tick);
      const now=[a,b].flatMap(e=>{const r=e.getBoundingClientRect(); return [r.top,r.left,r.width,r.height]}).join(',');
      n=now===old?n+1:0; old=now; if(n>=12) resolve(true); else requestAnimationFrame(tick); } tick(); })''', arg=LB)
def open_card(page, selector):
    card = page.locator(selector).first
    expect(card).to_be_visible(timeout=10000)
    box = card.bounding_box()
    card.click(position={'x': box['width'] * .2, 'y': box['height'] * .2})
    settled(page)
def image_is(image, part, width):
    expect(image).to_have_attribute('src', re.compile(re.escape(part)))
    expect(image).to_have_js_property('naturalWidth', width)

@pytest.mark.parametrize('mode', ['showcase', 'search', 'wishlist'])
def test_video_lightbox_avatars(site, server_url, mode):
    page = site
    if mode == 'showcase':
        page.goto(server_url + '/showcase?sort=number&order=asc')
        open_card(page, '.av-card-preview[data-flip-id]:not(.hero-card):has-text("TST-001")')
        page.wait_for_function('Alpine.$data(document.querySelector(\'[x-data="showcase"]\'))._lbFullLoaded')
    else:
        page.goto(server_url + '/search')
        page.fill('#searchQuery', 'あおい'); page.click('#btnSubmit')
        expect(page.locator('#resultNumber')).to_have_text('E2E-001')
        if mode == 'wishlist':
            page.click('#wishlistToggleBtn'); open_card(page, '.wishlist-grid .av-card-preview')
        else:
            page.click('.search-actions-right button:has(i.bi-grid-3x3), .search-actions-right button:has(i.bi-list-ul)')
            open_card(page, '.search-grid .av-card-preview:not(.hero-card)')
    meta = page.locator(LB + ' .lbx-meta'); meta.evaluate('e => e.scrollTop = 0')
    chips = page.locator(LB + ' .lbx-actors > .lbx-actor-chip')
    avatar = chips.filter(has_text=A).locator('.lbx-avatar')
    image_is(avatar.locator('img'), '/api/actresses/face-crop/', 128)
    image_is(chips.filter(has_text=B).locator('.lbx-avatar img'), '/api/actresses/photo/', 300)
    missing = chips.filter(has_text=C).locator('.lbx-avatar')
    expect(missing).to_have_count(1); expect(missing.locator('img')).to_have_count(0)
    expect(missing.locator('.lbx-avatar-initial')).not_to_be_empty()
    avatar.hover()
    photo = page.locator(LB + ' .lbx-actor-card__photo')
    image_is(photo, '/api/actresses/photo/', 300)
    expect(photo).not_to_have_attribute('src', re.compile('face-crop'))
    page.keyboard.press('Escape')
    if mode == 'showcase':
        page.keyboard.press('Escape')
        expect(page.locator(LB)).to_have_count(0)
        open_card(page, '.av-card-preview[data-flip-id]:not(.hero-card):has-text("TST-002")')
    else:
        page.keyboard.press('ArrowRight'); settled(page)
    meta = page.locator(LB + ' .lbx-meta'); meta.evaluate('e => e.scrollTop = 0')
    page.locator(LB + ' button.lbx-more-actors:visible').click()
    pop = page.locator(LB + ' .lbx-pop.is-placed')
    expect(pop).to_be_visible()
    for name, part in ((A, 'face-crop'), (B, '/photo/')):
        image = pop.locator('.lbx-pop-row').filter(has_text=name).locator('.lbx-avatar img')
        image.scroll_into_view_if_needed(); image_is(image, part, 128 if name == A else 300)
    expect(pop.locator('.lbx-pop-row').filter(has_text=C).locator('img')).to_have_count(0)
def test_insights_avatars(site, server_url):
    page = site
    load_ready(page, server_url)
    def avatar(name):
        return page.locator(f'.podium-avatar[data-flip-id="avatar-{name}"]:visible, .board-avatar[data-flip-id="avatar-{name}"]:visible')
    image_is(avatar(A).locator('img'), 'face-crop', 128)
    image_is(avatar(B).locator('img'), '/api/actresses/photo/', 300)
    avatar(A).hover()
    photo = page.locator('.insights-preview-photo img')
    expect(photo).to_have_attribute('src', re.compile('/api/actresses/photo/'))
    expect(photo).not_to_have_attribute('src', re.compile('face-crop'))
def test_actress_wall_and_lightbox_keep_original(site, server_url):
    page = site
    page.goto(server_url + '/showcase?sort=number&order=asc')
    open_card(page, '.av-card-preview[data-flip-id]:not(.hero-card):has-text("TST-001")')
    image_is(page.locator(LB + ' .lbx-actors > .lbx-actor-chip').filter(has_text=A).locator('.lbx-avatar img'), 'face-crop', 128)
    page.keyboard.press('Escape'); expect(page.locator(LB)).to_have_count(0)
    page.locator('.mode-toggle-btn').nth(1).click()
    card = page.locator('.actress-card').filter(has_text=A)
    photo = card.locator('.actress-card-photo img')
    image_is(photo, '/api/actresses/photo/', 300)
    expect(photo).not_to_have_attribute('src', re.compile('face-crop'))
    card.click()
    image_is(page.locator('.actress-lb-photo-frame img'), '/api/actresses/photo/', 300)
