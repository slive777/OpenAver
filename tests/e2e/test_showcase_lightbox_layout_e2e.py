"""影片燈箱的結束狀態。"""
import json
import pytest
from PIL import Image
from playwright.sync_api import expect
from tests.e2e._lightbox_layout_server import REPO, serve  # noqa: PLC2701
pytestmark = pytest.mark.e2e
ROOT = '[x-data="showcase"]'
LB = '.showcase-lightbox.show'
CARDS = '.av-card-preview[data-flip-id]:not(.hero-card)'
NAMES = [f'女優{i:02d}' for i in range(1, 16)]

@pytest.fixture(scope='module')
def server_url(tmp_path_factory):
    from core.database import init_db
    from core.database.actress import Actress, ActressRepository
    from core.organizer import sanitize_filename
    work = tmp_path_factory.mktemp('lightbox_layout')
    home, data, library = (work / name for name in ('home', 'data', 'lib'))
    for directory in (home, data, library):
        directory.mkdir()
    db = data / 'openaver.db'
    init_db(db)
    photos = data / 'Gfriends'
    photos.mkdir()
    for i, name in enumerate(NAMES[:4]):
        ActressRepository(db).save(Actress(name=name, photo_source='gfriends', primary_text_source='ai', birth='1995-01-01' if i != 3 else None,
                                          height='160' if i != 3 else None, cup='C' if i != 3 else None))
        if i != 2:
            Image.new('RGB', (300, 400), 'blue').save(photos / f'{sanitize_filename(name)}.jpg')
    rows = [(1, NAMES[:1]), (2, NAMES[:2]), (3, NAMES), (4, NAMES), (5, NAMES), (6, NAMES[:1])]
    for i, names in rows:
        number = f'LAY-{i:03d}'
        folder = library / number
        folder.mkdir()
        (folder / f'{number}.mp4').write_bytes(bytes([1]) * 2048)
        if i == 4:
            (folder / f'{number}-cd2.mp4').write_bytes(bytes([1]) * 2048)
        Image.new('RGB', (400, 600) if i == 6 else (640, 427), 'green').save(folder / f'{number}-fanart.jpg')
        actors = ''.join(f'<actor><name>{name}</name></actor>' for name in names)
        tags = ''.join(f'<genre>作品標籤{n:02d}</genre>' for n in range(15 if i in (4, 5) else 1))
        users = ''.join(f'<user_tag>我的標籤{n}</user_tag>' for n in range(5 if i in (4, 5) else 0))
        series = '長系列名稱' * 8 if i == 2 else '系列'
        maker = '超長片商名稱' * 2 if i == 2 else '片商'
        plot = '這是一段簡介。' * (80 if i in (4, 5) else 2)
        original = '<originaltitle>原文標題測試</originaltitle>' if i in (4, 5) else ''
        (folder / f'{number}.nfo').write_text(
            f'<movie><title>{number}</title><num>{number}</num>{actors}{tags}{users}{original}'
            f'<plot>{plot}</plot><maker>{maker}</maker><set><name>{series}</name></set></movie>', encoding='utf-8')
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

def settled(page):
    page.wait_for_function('''lb => new Promise(resolve => {
        let old = '', count = 0; const tick = () => {
            const root = document.querySelector(lb), a = root?.querySelector('.lightbox-cover'),
                b = root?.querySelector('.lbx-meta');
            if (!a || !b) return requestAnimationFrame(tick);
            const now = [a, b].flatMap(x => { const r = x.getBoundingClientRect();
                return [r.top, r.left, r.width, r.height]; }).join(',');
            count = now === old ? count + 1 : 0; old = now;
            if (count >= 12) resolve(true); else requestAnimationFrame(tick);
        }; tick();
    })''', arg=LB, timeout=15000)

def rect(page, selector):
    return page.locator(f'{LB} {selector}').first.bounding_box()

def open_video(page, number):
    if page.locator(LB).count():
        page.keyboard.press('Escape')
        expect(page.locator(LB)).to_have_count(0)
    assert page.evaluate('document.visibilityState') == 'visible'
    card = page.locator(CARDS).filter(has_text=number).first
    expect(card).to_be_visible(timeout=10000)
    box = card.bounding_box()
    card.click(position={'x': box['width'] * .2, 'y': box['height'] * .2})
    page.wait_for_function('s => Alpine.$data(document.querySelector(s))._lbFullLoaded', arg=ROOT)
    page.evaluate('() => document.fonts.ready'); page.wait_for_function('s => !document.querySelector(s)?.classList.contains("is-measuring")', arg=f'{LB} .lbx-people-row')
    settled(page)

def make_page(browser, url, width, height, touch=False, search=''):
    context = browser.new_context(viewport={'width': width, 'height': height}, is_mobile=touch, has_touch=touch, reduced_motion='reduce')
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' and not (
        msg.text.startswith('Failed to load resource') and '/api/actress-aliases/' in msg.location.get('url', '')
    ) else None)
    page.route('**/api/**', lambda route: route.continue_() if route.request.method == 'GET'
               else route.fulfill(json={'success': True}))
    page.goto(f'{url}/showcase?sort=number&order=asc{search}'); assert page.evaluate('document.visibilityState') == 'visible'
    return context, page, errors

@pytest.mark.parametrize('size', [(1280, 720), (1920, 950), (2560, 1300)])
def test_cover_and_text_area_stay_put(browser, server_url, size):
    context, page, errors = make_page(browser, server_url, *size)
    try:
        reference = None
        for i in range(1, 5):
            open_video(page, f'LAY-{i:03d}'); cover, meta = rect(page, '.lightbox-cover'), rect(page, '.lbx-meta')
            dims = (cover['y'], cover['height'], meta['height'])
            if reference is None:
                reference = dims
            assert all(abs(a - b) <= .5 for a, b in zip(reference, dims, strict=True))
            expected = page.evaluate('''() => parseFloat(getComputedStyle(document.querySelector('.showcase-lightbox.show .lightbox-content'))
                .getPropertyValue('--lbx-meta-h')) * parseFloat(getComputedStyle(document.documentElement).fontSize)''')
            assert abs(meta['height'] - expected) <= .5
        if size[0] >= 1920:
            open_video(page, 'LAY-006'); assert page.locator(f'{LB} .lbx-meta').evaluate('e => e.clientWidth') >= 588; cover, content = rect(page, '.lightbox-cover'), rect(page, '.lightbox-content'); assert abs(cover['x'] + cover['width'] / 2 - content['x'] - content['width'] / 2) <= 1
            assert page.locator(f'{LB} .lbx-actors > .lbx-actor-chip .lbx-actor-line').first.evaluate(
                'e => e.scrollWidth <= e.clientWidth')
        assert not errors, errors
    finally:
        context.close()

@pytest.mark.parametrize('size', [(1280, 720), (1920, 950), (2560, 1300)])
def test_people_row_layout(browser, server_url, size):
    context, page, errors = make_page(browser, server_url, *size)
    try:
        open_video(page, 'LAY-001'); row, actors, works = (rect(page, s) for s in ('.lbx-people-row', '.lbx-actors', '.lbx-works'))
        gap = page.locator(f'{LB} .lbx-people-row').evaluate('e => parseFloat(getComputedStyle(e).columnGap) || 0')
        assert works['y'] < actors['y'] + actors['height']; assert actors['x'] + actors['width'] + gap + works['width'] <= row['x'] + row['width'] + 1; open_video(page, 'LAY-002'); actors, works = rect(page, '.lbx-actors'), rect(page, '.lbx-works')
        if size == (1280, 720):
            assert works['y'] >= actors['y'] + actors['height']
        lines = page.locator(f'{LB} .lbx-actors > .lbx-actor-chip .lbx-actor-line'); assert lines.count() == 2
        for i in range(2):
            widths = lines.nth(i).evaluate('e => [e.scrollWidth, e.clientWidth]')
            assert widths[0] <= widths[1], f'BRAVO 女優 {i}: scrollWidth/clientWidth={widths}'
        assert page.locator(f'{LB} .lbx-actors > .lbx-more-actors').count() == 0; assert rect(page, '.lbx-work--series')['width'] <= page.locator(f'{LB} .lbx-meta').evaluate('e => e.clientWidth') / 2 + 1; open_video(page, 'LAY-003')
        chips = page.locator(f'{LB} .lbx-actors > .lbx-actor-chip'); measured = page.locator(f'{LB} .lbx-measure .lbx-actor-chip'); boxes = [chips.nth(i).bounding_box() for i in range(chips.count())]; assert max(b['y'] + b['height'] / 2 for b in boxes) - min(b['y'] + b['height'] / 2 for b in boxes) <= 1
        for i, box in enumerate(boxes):
            width = measured.nth(i).bounding_box()['width']; assert abs(box['width'] - width) <= 1, f'CHARLIE 女優 {i}: 可見={box["width"]}, 量測={width}'
        if size[0] >= 1920:
            assert len(boxes) > 3
        more = page.locator(f'{LB} .lbx-actors > .lbx-more-actors')
        if more.count():
            assert str(15 - len(boxes)) in more.inner_text(); more.click()
            selector = f'{LB} .lbx-pop[data-kind="actresses"].is-placed'; page.wait_for_selector(selector); pop = page.locator(selector)
            for name in NAMES:
                expect(pop).to_contain_text(name)
        else:
            assert len(boxes) == 15, f'沒有另有按鈕但僅顯示 {len(boxes)} 位'
        assert not errors, errors
    finally:
        context.close()

@pytest.mark.parametrize('size', [(1280, 720), (1920, 950), (2560, 1300), (1920, 500)])
def test_actor_card_placement(browser, server_url, size):
    context, page, errors = make_page(browser, server_url, *size)
    try:
        open_video(page, 'LAY-001')
        avatar = rect(page, '.lbx-actors > .lbx-actor-chip .lbx-avatar')
        page.mouse.move(avatar['x'] + avatar['width'] / 2, avatar['y'] + avatar['height'] / 2)
        pop = page.locator(f'{LB} .lbx-pop[data-kind="actorCard"].is-placed')
        expect(pop).to_be_visible(timeout=10000); card, cover, photo = pop.bounding_box(), rect(page, '.lightbox-cover'), rect(page, '.lbx-actor-card__photo'); assert card['x'] >= avatar['x'] + avatar['width']; assert card['y'] >= cover['y'] + cover['height']
        assert card['y'] + card['height'] <= size[1] - 8 and card['x'] >= 8; assert card['x'] + card['width'] <= size[0] - 8; assert abs(photo['width'] - .75 * photo['height']) <= 1 and photo['height'] >= 120; assert photo['x'] >= 0 and photo['y'] >= 0
        assert photo['x'] + photo['width'] <= size[0] and photo['y'] + photo['height'] <= size[1]; page.keyboard.press('Escape'); expect(page.locator(f'{LB} .lbx-pop')).to_have_count(0); expect(page.locator('[data-lbx-ghost]')).to_have_count(0)
        assert not errors, errors
    finally:
        context.close()

def test_meta_scroll_behaviour(browser, server_url):
    context, page, errors = make_page(browser, server_url, 1280, 720)
    try:
        open_video(page, 'LAY-001'); meta = page.locator(f'{LB} .lbx-meta'); assert meta.evaluate('e => e.scrollHeight <= e.clientHeight'); box = rect(page, '.lightbox-cover'); page.mouse.move(box['x'] + 20, box['y'] + 20)
        index = page.evaluate(f'Alpine.$data(document.querySelector(\'{ROOT}\')).lightboxIndex'); page.mouse.wheel(0, 600); page.wait_for_function('([s, n]) => Alpine.$data(document.querySelector(s)).lightboxIndex !== n', arg=[ROOT, index]); open_video(page, 'LAY-001'); box = rect(page, '.lbx-meta'); page.mouse.move(box['x'] + 20, box['y'] + 20)
        index = page.evaluate('s => Alpine.$data(document.querySelector(s)).lightboxIndex', ROOT); page.mouse.wheel(0, 600); page.wait_for_function('([s, n]) => Alpine.$data(document.querySelector(s)).lightboxIndex !== n', arg=[ROOT, index]); open_video(page, 'LAY-004'); assert meta.evaluate('e => e.scrollHeight > e.clientHeight'); page.locator(f'{LB} .lbx-info-btn').click(); expect(page.locator(f'{LB} .lbx-pop')).to_be_visible()
        box = rect(page, '.lbx-meta'); page.mouse.move(box['x'] + 20, box['y'] + 20); page.mouse.wheel(0, 600); page.wait_for_function("s => document.querySelector(s).scrollTop > 0", arg=f'{LB} .lbx-meta')
        expect(page.locator(f'{LB} .lbx-pop')).to_have_count(0); expect(page.locator('[data-lbx-ghost]')).to_have_count(0); assert page.evaluate(f'Alpine.$data(document.querySelector(\'{ROOT}\')).lightboxIndex') == 3
        meta.evaluate('e => e.scrollTop = e.scrollHeight'); page.keyboard.press('ArrowRight')
        page.wait_for_function("s => Alpine.$data(document.querySelector(s)).currentLightboxVideo?.number === 'LAY-005'", arg=ROOT); assert meta.evaluate('e => e.scrollHeight > e.clientHeight'); page.wait_for_function('s => document.querySelector(s).scrollTop === 0', arg=f'{LB} .lbx-meta')
        open_video(page, 'LAY-004'); meta.evaluate('e => e.scrollTop = e.scrollHeight'); before = meta.evaluate('e => e.scrollTop'); assert before > 0
        versions = page.locator(f'{LB} .lbx-vcap'); assert versions.count() == 2
        path = page.evaluate('s => Alpine.$data(document.querySelector(s)).currentLightboxVideo.path', ROOT)
        page.locator(f'{LB} .lbx-vcap:not(.is-active)').click(); page.wait_for_function('([s, p]) => Alpine.$data(document.querySelector(s)).currentLightboxVideo.path !== p', arg=[ROOT, path])
        page.wait_for_timeout(500); assert meta.evaluate('e => e.scrollTop') == before
        page.evaluate("s => new Promise(resolve => { let d = Alpine.$data(document.querySelector(s)); d.currentLightboxVideo = {...d.currentLightboxVideo}; Alpine.nextTick(resolve); })", ROOT)
        assert meta.evaluate('e => e.scrollTop') == before; assert not errors, errors
    finally:
        context.close()
    context, page, errors = make_page(browser, server_url, 1280, 720, search='&search=LAY-004')
    try:
        def respond(route):
            target = 'LAY-004' if 'LAY-005' in route.request.url else 'LAY-005'
            item = {'number': target, 'title': target, 'cover_url': '', 'actresses': NAMES}
            route.fulfill(json={'query_video': {'number': 'LAY-004'}, 'results': [item] * 12})
        page.route('**/api/similar-covers/by-number/*', respond); open_video(page, 'LAY-004'); meta = page.locator(f'{LB} .lbx-meta')
        for target in ('LAY-005', 'LAY-004'):
            page.locator(f'{LB} .lightbox-similar-btn').click(); page.wait_for_function('s => {const d = Alpine.$data(document.querySelector(s)); return d.similarModeOpen && !d.similarModeAnimating && d.similarVisibleSlots.size > 0}', arg=ROOT)
            page.evaluate('s => {const d = Alpine.$data(document.querySelector(s)); d.onSimilarCardClick([...d.similarVisibleSlots][0]);}', ROOT); page.wait_for_function('([s, n]) => {const d = Alpine.$data(document.querySelector(s)); return !d.similarModeAnimating && d._similarLastDrilledNumber === n}', arg=[ROOT, target])
            page.evaluate('s => Alpine.$data(document.querySelector(s)).closeSimilarMode()', ROOT)
            page.wait_for_function('([s, n]) => {const d = Alpine.$data(document.querySelector(s)); return !d.similarModeOpen && d.currentLightboxVideo?.number === n}', arg=[ROOT, target])
            settled(page); assert meta.evaluate('e => e.scrollHeight > e.clientHeight')
            if target == 'LAY-005':
                meta.evaluate('e => e.scrollTop = e.scrollHeight'); assert meta.evaluate('e => e.scrollTop > 0')
            else:
                page.wait_for_function('s => document.querySelector(s).scrollTop === 0', arg=f'{LB} .lbx-meta')
        assert not errors, errors
    finally:
        context.close()

def test_tag_row_expanded(browser, server_url):
    context, page, errors = make_page(browser, server_url, 1280, 720)
    try:
        open_video(page, 'LAY-004')
        assert page.locator(f'{LB} .lbx-tags-work > .lbx-tag').count() == 15
        assert page.locator(f'{LB} .lbx-more-' + 'tags').count() == 0
        left, right = rect(page, '.lbx-tags-work > .lbx-tag'), rect(page, '.lbx-tag-right')
        assert abs(left['y'] - right['y']) <= 1
        edge = page.locator(f'{LB} .lbx-meta').evaluate('e => e.getBoundingClientRect().left + e.clientLeft + e.clientWidth - parseFloat(getComputedStyle(e).paddingRight)')
        assert abs(right['x'] + right['width'] - edge) <= 1
        page.locator(f'{LB} .lbx-tag-plus').click(); expect(page.locator(f'{LB} .lbx-tag-input')).to_be_visible()
        page.keyboard.press('Escape'); expect(page.locator(f'{LB} .lbx-tag-input')).to_be_hidden()
        assert not errors, errors
    finally:
        context.close()

def test_mobile_card_stays_put(browser, server_url):
    for width, height, touch in [(390, 844, True), (360, 640, True), (769, 900, False)]:
        context, page, errors = make_page(browser, server_url, width, height, touch)
        try:
            positions = []
            for number in ('LAY-001', 'LAY-004'):
                open_video(page, number); content, cover = rect(page, '.lightbox-content'), rect(page, '.lightbox-cover')
                positions.append((content['y'], cover['y']))
                assert content['y'] + content['height'] <= height * .95
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                for selector in ('.lbx-meta', '.lightbox-content'):
                    assert page.locator(f'{LB} {selector}').evaluate('e => e.scrollWidth <= e.clientWidth + 1')
            if width == 390:
                assert all(abs(a - b) <= .5 for a, b in zip(*positions, strict=True))
                assert .6 <= content['height'] / height <= .9
                open_video(page, 'LAY-002'); series = page.locator(f'{LB} .lbx-work--series')
                assert series.evaluate('e => e.offsetWidth <= e.parentElement.clientWidth')
            assert not errors, errors
        finally:
            context.close()
