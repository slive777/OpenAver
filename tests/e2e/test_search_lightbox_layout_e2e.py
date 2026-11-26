"""搜尋燈箱：使用自家協定夾具驗證畫面終態。"""
import io
import json
import re

import pytest
from PIL import Image
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e
LB = '.showcase-lightbox.show'
CARDS = '.search-grid .av-card-preview:not(.hero-card)'
TOGGLE = '.search-actions-right button:has(i.bi-grid-3x3), .search-actions-right button:has(i.bi-list-ul)'
FONTS = re.compile(r'https://fonts\.(googleapis|gstatic)\.com/')
JP = 'これは長い作品の紹介です。' * 35
ZH = '這是一段翻譯後的作品簡介，描述故事與人物。' * 8

@pytest.fixture(scope='module')
def data():
    rows = []
    for i in range(1, 7):
        number = f'E2E-{i:03d}'
        row = dict(number=number, title='長い日本語の作品名' * 20, actors=['舊名あおい', '女優乙'],
                   tags=[f'標籤{n:02d}' for n in range(45)], date='2020-01-01', duration=120,
                   maker='片商', series='長系列名稱' * 8, director='導演', label='發行商',
                   cover=f'https://img.e2e.invalid/{number}.jpg',
                   sample_images=[f'https://img.e2e.invalid/{number}-{n}.jpg' for n in range(3)],
                   source='e2e', url=f'https://e2e.invalid/{number}', _summary=JP)
        rows.append(row)
    rows[1]['actors'] = [f'很長的女優名字あいうえお{n}' for n in range(5)]
    rows[1]['_summary'] = '短い紹介です。'
    del rows[2]['_summary']
    profile = dict(name='女優あおい', name_en='Aoi', age=25, birth='1995-01-01', height='160', cup='C',
                   bust='80', waist='60', hip='85', aliases=[f'別名{n}' for n in range(12)], tags=['標籤'],
                   blog_url='https://blog.invalid/', official_url='https://official.invalid/', img='',
                   primary_text_source='wiki', is_favorite=False)
    wishlist = [dict(number=r['number'], title=r['title'], actresses=r['actors'], tags=r['tags'],
                     release_date=r['date'], maker=r['maker'], series=r['series'], director=r['director'],
                     label=r['label'], duration=r['duration'], sample_images=r['sample_images'],
                     source_url=r['url'], created_at='2026-01-01T00:00:00') for r in rows[:3]]
    buf = io.BytesIO(); Image.new('RGB', (800, 534), 'blue').save(buf, format='PNG')
    return rows, profile, wishlist, buf.getvalue()


class Harness:
    def __init__(self, page, base, data, fav='early', skipped=False):
        self.page, self.base, self.data, self.fav, self.skipped = page, base, data, fav, skipped
        self.requests, self.held, self.fav_calls, self.bad = [], [], 0, []
        page.on('request', lambda r: self.requests.append((r.method, r.url)))
        page.route('**/*', self.route)
        page.emulate_media(reduced_motion='reduce'); page.bring_to_front()
        page.goto(base + '/search'); assert page.evaluate('document.visibilityState') == 'visible'

    def route(self, route):
        req, url = route.request, route.request.url
        path = url.split('?')[0]
        if FONTS.match(url): return route.fulfill(body='', content_type='text/css')
        if path.endswith('/api/client-log'): return route.fulfill(status=204, body='')
        if path.endswith('/api/config') and req.method == 'GET':
            response = route.fetch(); config = response.json(); config['translate'] = {'enabled': True, 'provider': 'ollama'}
            return route.fulfill(response=response, json=config)
        if '/api/search/stream' in path:
            event = dict(type='result', success=True, mode='actress', has_more=True, data=self.data[0][:4], actress_profile=self.data[1])
            return route.fulfill(body='data: ' + json.dumps(event) + '\n\n', content_type='text/event-stream')
        if re.search(r'/api/search\?', url): return route.fulfill(json={'success': True, 'data': self.data[0][4:], 'has_more': False})
        if path.endswith('/api/actresses'):
            self.fav_calls += 1
            if self.fav in ('late', 'reverse') and self.fav_calls == 1:
                self.held.append(route); return
            return self.release(route, status=500 if self.fav == 'fail' else 200)
        if path.endswith('/api/actress-aliases'): return route.fulfill(json={'groups': [{'primary_name': '新名あおい', 'aliases': ['舊名あおい']}]})
        if '/api/proxy-image' in path or '/api/actresses/photo/' in path or '/api/wishlist/cover' in path:
            return route.fulfill(body=self.data[3], content_type='image/png')
        if path.endswith('/api/wishlist/count'): return route.fulfill(json={'count': 3})
        if path.endswith('/api/wishlist') and req.method == 'GET': return route.fulfill(json=self.data[2])
        if path.endswith('/api/translate') and req.method == 'POST':
            return route.fulfill(json={'success': True, 'skipped': True, 'reason': 'no_japanese'} if self.skipped else {'success': True, 'result': ZH})
        if req.method != 'GET':
            if '/api/wishlist' in path or path.endswith(('/api/actresses/favorite', '/api/scrape-single')):
                return route.fulfill(json={'success': True, 'actress': {}})
            self.bad.append((req.method, url)); return route.abort()
        route.continue_()

    def release(self, route, status=200, empty=False):
        favs = [] if empty else [{'name': '新名あおい', 'photo_url': '/api/actresses/photo/x', 'birth': '1995-01-01', 'height': '160', 'cup': 'C'}]
        route.fulfill(status=status, json={'success': status == 200, 'actresses': favs})

    def search(self):
        self.page.fill('#searchQuery', 'あおい'); self.page.click('#btnSubmit')
        expect(self.page.locator('#resultNumber')).to_have_text('E2E-001')

    def grid(self):
        self.page.click(TOGGLE); expect(self.page.locator(CARDS)).to_have_count(4)

    def open(self, selector=CARDS, index=0):
        card = self.page.locator(selector).nth(index); expect(card).to_be_visible(); box = card.bounding_box()
        card.click(position={'x': box['width'] * .2, 'y': box['height'] * .2}); settled(self.page)

    def clean(self):
        assert not self.bad, self.bad
        assert not [u for _, u in self.requests if not (u.startswith((self.base, 'blob:', 'data:')) or FONTS.match(u))]

def settled(page):
    page.wait_for_function('''s => new Promise(resolve => { let old='', n=0; function tick() {
      const root=document.querySelector(s), a=root?.querySelector('.lightbox-cover'), b=root?.querySelector('.lbx-meta');
      const d=Alpine.$data(document.querySelector('.search-container'));
      if (!a || !b || d._lightboxAnimating || root.querySelector('.lbx-people-row.is-measuring')) return requestAnimationFrame(tick);
      const now=[a,b].flatMap(e=>{const r=e.getBoundingClientRect(); return [r.top,r.left,r.width,r.height]}).join(',');
      n=now===old?n+1:0; old=now; if(n>=12) resolve(true); else requestAnimationFrame(tick); } tick(); })''', arg=LB)


@pytest.mark.parametrize('mode', ['early', 'late', 'fail', 'reverse'])
def test_favorites(page, base_url, data, mode):
    h = Harness(page, base_url, data, mode); h.search(); h.grid()
    if mode in ('late', 'reverse'):
        with page.expect_request(lambda r: r.url.endswith('/api/actresses')): h.open()
    else: h.open()
    chips = page.locator(LB + ' .lbx-actors > .lbx-actor-chip')
    if mode in ('late', 'reverse'):
        if mode == 'reverse':
            page.evaluate("Alpine.$data(document.querySelector('.search-container')).lbxFavsReload()")
            expect(chips.filter(has_text='舊名あおい').locator('.lbx-avatar')).to_have_count(1)
        with page.expect_response(lambda r: r.url.endswith('/api/actresses')):
            h.release(h.held.pop(), empty=mode == 'reverse')
        if mode == 'reverse':
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    if mode == 'fail':
        expect(chips.locator('.lbx-avatar')).to_have_count(0)
        expect(chips).to_have_count(2); expect(chips.nth(0)).to_contain_text('舊名あおい'); expect(chips.nth(1)).to_contain_text('女優乙')
        page.keyboard.press('ArrowRight'); settled(page)
        visible = page.locator(LB + ' .lbx-actors > .lbx-actor-chip').count()
        more = page.locator(LB + ' button.lbx-more-actors:visible')
        expect(more).to_have_count(1); assert str(5 - visible) in more.inner_text()
    else:
        expect(chips.filter(has_text='舊名あおい').locator('.lbx-avatar')).to_have_count(1)
        expect(chips.filter(has_text='女優乙').locator('.lbx-avatar')).to_have_count(0)
    h.clean()

def test_scroll_and_pagination(page, base_url, data):
    h = Harness(page, base_url, data); h.search(); h.grid(); h.open()
    meta = page.locator(LB + ' .lbx-meta')
    assert meta.evaluate('e => e.scrollHeight > e.clientHeight')
    meta.evaluate('e => e.scrollTop = 99999'); assert meta.evaluate('e => e.scrollTop') > 0
    page.keyboard.press('ArrowRight'); settled(page); assert meta.evaluate('e => e.scrollTop') == 0
    page.keyboard.press('ArrowRight'); settled(page); page.keyboard.press('ArrowRight'); settled(page)
    meta.evaluate('e => e.scrollTop = 99999'); assert meta.evaluate('e => e.scrollTop') > 0
    page.keyboard.press('ArrowRight'); page.wait_for_function("Alpine.$data(document.querySelector('.search-container')).lightboxIndex === 4")
    settled(page); assert meta.evaluate('e => e.scrollTop') == 0
    assert any('/api/search?' in u and 'offset=' in u for _, u in h.requests); h.clean()

def test_wishlist_display(page, base_url, data):
    h = Harness(page, base_url, data); h.search(); page.click('#wishlistToggleBtn')
    start = len(h.requests); h.open('.wishlist-grid .av-card-preview')
    meta = page.locator(LB + ' .lbx-meta')
    assert meta.locator('a, [href], .lbx-plot-row').count() == 0
    assert meta.locator('button:not(.lbx-info-btn):not(.lbx-more-actors):not(.lbx-avatar):not(.lbx-sg-btn)').count() == 0
    assert page.locator(LB + ' .lightbox-cover img').first.get_attribute('src').startswith('/api/wishlist/cover')
    for _ in range(3): page.keyboard.press('ArrowRight'); page.keyboard.press('ArrowLeft')
    assert not [u for _, u in h.requests[start:] if '/api/proxy-image' in u]; h.clean()

def test_actress(page, base_url, data):
    h = Harness(page, base_url, data); h.search(); h.grid()
    page.locator('.search-grid .hero-card').click(); expect(page.locator(LB + ' .lbx-actress-branch')).to_have_count(1)
    assert page.locator(LB + ' .lb-video-branch, .lb-actress-urls').count() == 0
    assert page.locator(LB + ' .actress-lb-title').evaluate("e => Math.abs(e.querySelector('.lb-name').getBoundingClientRect().left - e.getBoundingClientRect().left - parseFloat(getComputedStyle(e).paddingLeft)) <= .5")
    links = page.locator(LB + ' .lbx-ap-link'); assert links.count() == 2
    for i, url in enumerate(('https://blog.invalid/', 'https://official.invalid/')):
        assert links.nth(i).get_attribute('href') == url and links.nth(i).get_attribute('target') == '_blank'
        assert 'noopener' in links.nth(i).get_attribute('rel')
    page.locator(LB + ' button.btn-glass-circle:visible').click()
    expect(page.locator(LB + ' span.btn-glass-circle.is-favorite')).to_be_visible()
    page.keyboard.press('ArrowRight'); expect(page.locator(LB + ' .lb-video-branch')).to_have_count(1); expect(page.locator(LB + ' .lbx-actress-branch')).to_have_count(0)
    page.keyboard.press('ArrowLeft'); expect(page.locator(LB + ' .lbx-actress-branch')).to_have_count(1); expect(page.locator(LB + ' .lb-video-branch')).to_have_count(0)
    h.clean()

@pytest.mark.parametrize('skipped', [False, True])
def test_summary(page, base_url, data, skipped):
    h = Harness(page, base_url, data, skipped=skipped); h.search()
    expect(page.locator('#summaryRow')).to_be_visible(); expect(page.locator('#resultSummary')).to_have_text(JP)
    expect(page.locator('#translateSummaryBtn')).to_be_visible()
    start = len(h.requests)
    with page.expect_response('**/api/translate'), page.expect_request('**/api/translate') as request: page.click('#translateSummaryBtn')
    body = request.value.post_data_json; assert body['text'] == JP and body['mode'] == 'translate'
    if skipped:
        expect(page.locator('#translateSummarySpinner')).to_be_hidden(); expect(page.locator('#translateSummaryBtn')).to_be_visible()
        assert len([u for method, u in h.requests[start:] if method == 'POST' and u.endswith('/api/translate')]) == 1
        assert not page.evaluate("'translated_summary' in Alpine.$data(document.querySelector('.search-container')).searchResults[0]")
    else:
        expect(page.locator('#resultSummary')).to_have_text(ZH); expect(page.locator('#translateSummarySpinner')).to_be_hidden(); expect(page.locator('#translateSummaryBtn')).to_be_hidden()
        assert len([u for method, u in h.requests[start:] if method == 'POST' and u.endswith('/api/translate')]) == 1
        page.click('#btnNext'); expect(page.locator('#resultNumber')).to_have_text('E2E-002')
        page.click('#btnNext'); expect(page.locator('#resultNumber')).to_have_text('E2E-003'); expect(page.locator('#summaryRow')).to_be_hidden()
        h.grid(); h.open(); expect(page.locator(LB + ' .lbx-plot-text')).to_have_text(ZH)
        before = len(h.requests); page.locator(LB + ' .lbx-plot-row').click()
        expect(page.locator(LB + ' .lbx-plot-pop-text')).to_have_text(ZH)
        assert page.locator(LB + ' .lbx-pop button').count() == 0
        assert not [u for _, u in h.requests[before:] if '/api/' in u]
        page.keyboard.press('Escape'); page.keyboard.press('ArrowRight'); settled(page)
        page.locator(LB + ' .lbx-plot-row').click(); expect(page.locator(LB + ' .lbx-pop.is-placed')).to_have_count(0)
        page.keyboard.press('ArrowRight'); settled(page); expect(page.locator(LB + ' .lbx-plot-row')).to_have_count(0)
    h.clean()

def pop_escape(page, root):
    meta = page.locator(root + ' .lbx-meta'); meta.evaluate('e => e.scrollTop = 0')
    page.locator(root + ' button.lbx-info-btn:visible').click()
    pop = page.locator(root + ' .lbx-pop.is-placed'); expect(pop).to_be_visible()
    assert pop.evaluate('e => {const r=e.getBoundingClientRect(); return r.left>=0 && r.top>=0 && r.right<=innerWidth && r.bottom<=innerHeight}')
    page.keyboard.press('Escape'); expect(pop).to_have_count(0); expect(page.locator(root)).to_be_visible()
    page.keyboard.press('Escape'); expect(page.locator(root)).to_have_count(0)

def test_handoff_and_popovers(page, base_url, data):
    h = Harness(page, base_url, data); h.search(); h.grid(); h.open()
    page.locator(LB + ' .lb-title').click()
    pop = page.locator(LB + ' .lbx-pop.is-placed'); expect(pop).to_be_visible()
    assert pop.evaluate('e => {const r=e.getBoundingClientRect(); return r.left>=0 && r.top>=0 && r.right<=innerWidth && r.bottom<=innerHeight}')
    page.keyboard.press('Escape'); expect(pop).to_have_count(0); expect(page.locator(LB)).to_be_visible()
    page.locator(LB + ' button.lbx-info-btn:visible').click()
    pos = page.evaluate('''() => {const lb=document.querySelector('.showcase-lightbox.show'), content=lb.querySelector('.lightbox-content').getBoundingClientRect();
      const current=Alpine.$data(document.querySelector('.search-container')).lightboxIndex;
      lb.style.display='none'; let found=null; for(let y=0;y<innerHeight&&!found;y+=5) for(let x=0;x<innerWidth;x+=5) {
        const c=document.elementFromPoint(x,y)?.closest('.search-grid .av-card-preview:not(.hero-card)');
        const k=[...document.querySelectorAll('.search-grid .av-card-preview:not(.hero-card)')].indexOf(c);
        if(c && k!==current && (x<content.left||x>content.right||y<content.top||y>content.bottom)) {found={x,y,k,current}; break} }
      lb.style.display=''; return found }''')
    assert pos is not None; page.mouse.click(pos['x'], pos['y'])
    expect(page.locator(LB + ' .lbx-pop.is-placed')).to_have_count(0)
    assert page.evaluate("Alpine.$data(document.querySelector('.search-container')).lightboxIndex") == pos['current']
    page.mouse.click(pos['x'], pos['y']); page.wait_for_function("k => Alpine.$data(document.querySelector('.search-container')).lightboxIndex === k", arg=pos['k'])
    for _ in range(pos['k'] - 1): page.keyboard.press('ArrowLeft'); settled(page)
    page.locator(LB + ' button.lbx-more-actors:visible').click()
    expect(page.locator(LB + ' .lbx-pop.is-placed')).to_be_visible(); page.keyboard.press('Escape')
    expect(page.locator(LB + ' .lbx-pop.is-placed')).to_have_count(0); page.keyboard.press('Escape')
    expect(page.locator(LB)).to_have_count(0); page.click('#wishlistToggleBtn'); h.open('.wishlist-grid .av-card-preview')
    assert page.locator('.lb-video-branch').count() <= 1 and page.locator('.lbx-pop-host').count() <= 1 and page.locator('.lbx-meta').count() == 1
    pop_escape(page, '.wishlist-lightbox.show')
    page.locator('.mode-toggle-btn:not(#wishlistToggleBtn)').first.click(); h.open()
    assert page.locator('.lb-video-branch').count() <= 1 and page.locator('.lbx-pop-host').count() <= 1 and page.locator('.lbx-meta').count() == 1
    pop_escape(page, '.showcase-lightbox.show:not(.wishlist-lightbox)'); h.clean()

def test_summary_mobile(page, base_url, data):
    page.set_viewport_size({'width': 390, 'height': 844})
    h = Harness(page, base_url, data); h.search(); h.grid(); h.open()
    assert page.locator(LB + ' .lbx-meta').evaluate("e => e.querySelector('.lbx-tag-row').getBoundingClientRect().top - e.getBoundingClientRect().top < e.clientHeight")
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    row = page.locator(LB + ' .lbx-plot-row'); row.scroll_into_view_if_needed(); row.click()
    expect(page.locator(LB + ' .lbx-pop.is-placed')).to_be_visible(); page.keyboard.press('Escape')
    page.keyboard.press('ArrowRight'); settled(page); page.locator(LB + ' .lbx-plot-row').scroll_into_view_if_needed()
    page.locator(LB + ' .lbx-plot-row').click(); expect(page.locator(LB + ' .lbx-pop.is-placed')).to_have_count(0)
    h.clean()
