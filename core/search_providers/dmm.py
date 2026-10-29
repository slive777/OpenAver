"""DMM 的 Provider：關鍵字與實體（女優／系列／導演／label／片商）列表、官方番號、守衛 belongs、逐部補詳情。

- 175a-T5 把 scraper.py 的 DMM「列表＋逐部補詳情」包入；175c-T7 加名稱→實體 resolve；175c-T8 起宣告
  ACTOR／SERIES／DIRECTOR／LABEL／KEYWORD：名稱經 resolve 換成 DMM id，list_entity 用 filter 列出該實體的完整作品
  （含預購未發行），順序同站方（預購最前、新→舊，不重排）；175c-T9 起再宣告 MAKER（與 run_maker 同時就位）。
- 關鍵字與實體共用同一個頁面組裝：一次 list_contents ＋ 恰一次 fetch_facts（先於回傳，也就先於 seed）；
  列表階段的番號用官方 makerContentId，缺值才退 cid 推導（精準搜尋與進階搜尋打 cid 不變）。
  傳輸失敗（被擋／連不上）原樣往外丟，由 relay 換下一家；contents 為空才是「查無」。
- 守衛 belongs 全由列表階段已取得的事實算出（enrich 內除 _fetch_by_id 外零網路）；實體路徑自補 _source。
- run_maker（片商膠囊與打字片商）：比對候選＝label 與各拼法各自經對照表展開（正名＋別名）後去重保序 → _resolve_maker
  → list_entity 視窗 → run_window(guard=False)；膠囊只送片庫寫法（如 S1），DMM 站上的片商名靠展開才比得中。
  DMM 以片商 id 精查，不需要片庫樣本、不寫 JavBus 的片商對照表；呼叫端傳入的鍵與拼法、回傳值都不改寫。
  錯誤碼：不認得 ⇒ maker_not_found、傳輸例外 ⇒ maker_unreachable（絕不互換）、列表空 ⇒ maker_empty。
- 不宣告 CODE／PARTIAL（DMM 前綴是 token 子字串，會混入重製版，CD-175c-10）。
頂層不得 import core.scraper／core.database（BE-PY-08）。補詳情一律經 pipeline.run_window。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.logger import get_logger
from core.maker_names import maker_key_of
from core.recent_rules import RecentRow, select_recent
from core.name_match import fold, split_paren_name
from core.scrapers.dmm import DMMScraper, Facts, ListResult, _actress_main_name
from core.scrapers.errors import SourceBlocked
from core.scrapers.models import Actress, Video
from core.search_providers.names import maker_names
from core.search_providers.pipeline import run_window
from core.search_providers.types import EntityRef, Enriched, Kind, MakerSearchResult, Page, Window, WorkItem

logger = get_logger(__name__)

SOURCE = "dmm"


# ---------------------------------------------------------------- 名稱→實體（175c-T7，plan CD-175c-6 (B)）
_PROBE_LIST_LIMIT = 40  # stage 1 取一頁 40 筆（站方依發行日排序，sort 在 list_contents 內固定）
_PROBE_CACHE_MAX = 256  # 超過整張清空，重啟即清，無持久化
_MAKER_PROBE_MAX = 3  # _resolve_maker 至多問前 3 個拼法
_RESOLVE_KINDS = frozenset({Kind.ACTOR, Kind.MAKER, Kind.SERIES, Kind.DIRECTOR, Kind.LABEL})


@dataclass
class Probe:
    """一個名字的探測結果：stage 1 的 rows（一定有）＋ stage 2 的 facts（用到才取；None＝尚未取到）。"""

    rows: list[dict]
    facts: dict[str, Facts] | None = None


_PROBE_CACHE: dict[str, Probe] = {}


@dataclass
class ActorsPage:
    """list_actors_page 的回傳：items 為通過過濾的作品；raw_count 為站方回的列數（過濾前）。"""

    items: list[WorkItem]
    raw_count: int
    has_next: bool
    reached_cutoff: bool


_JST = timezone(timedelta(hours=9))


def _parse_when(value) -> datetime | None:
    """deliveryStartAt → aware datetime；失敗＝None；無時區當 +09:00（DMM 為日本時間）。"""
    try:
        when = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo is not None else when.replace(tzinfo=_JST)


def _recent_row(row: dict, now: datetime) -> RecentRow:
    when = _parse_when(row.get("deliveryStartAt"))
    upcoming = row.get("releaseStatus") == "PRE_ORDER" or (when is not None and when > now)
    count = sum(1 for a in row.get("actresses") or [] if isinstance(a, dict))
    return RecentRow(row["id"], when, upcoming, count)


def clear_probe_cache() -> None:
    _PROBE_CACHE.clear()


def _same_name(candidate, wanted) -> bool:
    """名稱精確相等（fold 後）。子字串不算：列表是依關鍵字撈的，共演者、標題碰巧含該字的人都會在 rows 裡。"""
    return fold(candidate) == fold(wanted)


def _ident(value) -> str | None:
    """站方 id → 字串；缺／空 → None（該項略過）。"""
    return None if value in (None, "") else str(value)


def _stage1(scraper, name: str) -> Probe:
    """名字 → Probe（rows）。只快取成功；傳輸例外原樣往外丟、不入快取（BE-PY-03）。"""
    key = fold(name)
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]
    rows = scraper.list_contents(name, limit=_PROBE_LIST_LIMIT, offset=0).rows
    if len(_PROBE_CACHE) >= _PROBE_CACHE_MAX:
        _PROBE_CACHE.clear()
    probe = _PROBE_CACHE[key] = Probe(rows)
    return probe


def _row_ids(probe: Probe) -> list[str]:
    ids = (_ident(r.get("id")) for r in probe.rows)
    return list(dict.fromkeys(i for i in ids if i))


def _stage2(scraper, probe: Probe) -> dict[str, Facts]:
    """Probe 的 facts：每個名字至多一次（SERIES／DIRECTOR／LABEL 共用）；rows 無 id 不發；失敗時 stage 1 保留、下次只重試這段。"""
    if probe.facts is None:
        ids = _row_ids(probe)
        probe.facts = scraper.fetch_facts(ids) if ids else {}
    return probe.facts


def _most_common(hits):
    """hits＝[(id, label)…]（依出現順序）→ 出現次數最多者；平手取先出現；空 → None。"""
    counts = Counter(i for i, _ in hits)
    if not counts:
        return None
    top = max(counts.values())
    return next((i, label) for i, label in hits if counts[i] == top)


def _actor_names(actress: dict) -> list[str]:
    """一位女優可被輸入比中的名字：主名與括號內舊名（あかね麗（二階堂麗）→ あかね麗、二階堂麗）。"""
    main, old = split_paren_name(actress.get("name"))
    return [n for n in (main, old) if n]


def _pick_actor(rows: list[dict], wanted: str) -> EntityRef | None:
    hits = []
    for row in rows:
        for actress in row.get("actresses") or []:
            if not isinstance(actress, dict):  # 陣列裡夾 null／非 dict：只略過這一項（與 _row_actress_ids 對齊）
                continue
            aid = _ident(actress.get("id"))
            names = _actor_names(actress)
            if aid and any(_same_name(n, wanted) for n in names):
                hits.append((aid, names[0]))
    best = _most_common(hits)
    return None if best is None else EntityRef(Kind.ACTOR, best[0], best[1])


def _named_in(facts: Facts, kind: Kind) -> list:
    """facts 裡該 kind 的 Named 清單（directors 本來就是 list）。"""
    if kind is Kind.DIRECTOR:
        return list(facts.directors)
    one = facts.series if kind is Kind.SERIES else facts.label
    return [] if one is None else [one]


def _pick_named(probe: Probe, facts: dict[str, Facts], kind: Kind, wanted: str) -> EntityRef | None:
    hits = []
    for cid in _row_ids(probe):  # 依 rows 出現順序走，不依 fetch_facts 回傳 dict 的順序
        found = facts.get(cid)
        for named in [] if found is None else _named_in(found, kind):
            nid = _ident(named.id)
            if nid and _same_name(named.name, wanted):
                hits.append((nid, named.name))
    best = _most_common(hits)
    return None if best is None else EntityRef(kind, best[0], best[1])


def _pick_maker(rows: list[dict], spellings: set[str]) -> EntityRef | None:
    hits = []
    for row in rows:
        maker = row.get("maker") or {}
        mid, mname = _ident(maker.get("id")), maker.get("name")
        if mid and mname and maker_key_of(mname) in spellings:
            hits.append((mid, mname))
    best = _most_common(hits)
    return None if best is None else EntityRef(Kind.MAKER, best[0], best[1])


# ---------------------------------------------------------------- 實體清單＋官方番號＋守衛（175c-T8，plan CD-175c-7）
# 實體 kind → list_contents 的 filter 鍵（MAKER 供 run_maker 使用）
_FILTER_KEY = {
    Kind.ACTOR: "actressIds",
    Kind.SERIES: "seriesIds",
    Kind.DIRECTOR: "directorIds",
    Kind.LABEL: "labelIds",
    Kind.MAKER: "makerIds",
}


def _official_number(scraper, content_id: str, fact: Facts | None) -> str:
    """列表階段的番號：官方 makerContentId；facts 缺這部、或值為空，才退 cid 推導（不覆寫成空）。"""
    return (fact.maker_content_id if fact is not None else None) or scraper._content_id_to_number(content_id)


def _shallow_video(scraper, row: dict, content_id: str, number: str) -> Video:
    """列表一列 → shallow Video（詳情失敗時卡片就是它，所以番號用官方值）。
    女優去括號舊名；title／封面／片商名為 null 皆當空字串，不讓一列壞資料丟掉整頁。"""
    return Video(
        number=number,
        title=row.get("title") or "",
        actresses=[
            Actress(name=_actress_main_name(a["name"]))
            for a in row.get("actresses") or []
            if isinstance(a, dict) and a.get("name")
        ],
        maker=(row.get("maker") or {}).get("name") or "",
        cover_url=(row.get("packageImage") or {}).get("largeUrl") or "",
        source=scraper.source_name,
        detail_url=f"https://www.dmm.co.jp/digital/videoa/-/detail/=/cid={content_id}/",
    )


def _row_actress_ids(row: dict) -> frozenset[str]:
    ids = (_ident(a.get("id")) for a in row.get("actresses") or [] if isinstance(a, dict))
    return frozenset(i for i in ids if i)


def _row_item(scraper, row: dict, fact: Facts | None) -> WorkItem:
    """列表一列（已確認有 id）→ WorkItem。ref＝(cid, shallow, facts 或 None, 該列女優 id 集合, 該列片商 id)，
    守衛 belongs 與補詳情都只讀它，不再發請求。"""
    content_id = row["id"]
    number = _official_number(scraper, content_id, fact)
    shallow = _shallow_video(scraper, row, content_id, number)
    maker_id = _ident((row.get("maker") or {}).get("id"))
    ref = (content_id, shallow, fact, _row_actress_ids(row), maker_id)
    return WorkItem(number, shallow.title, shallow.cover_url, shallow.date, None, SOURCE, ref=ref)


def _owner_ids(kind: Kind, facts: Facts | None, actress_ids: frozenset[str], maker_id: str | None) -> frozenset[str] | None:
    """這部作品在 kind 這個維度上的擁有者 id 集合（ACTOR／MAKER 取自列表列，SERIES／LABEL／DIRECTOR 取自 facts）。
    facts 缺或該欄為 None → 空集合（確定不屬於）；kind 不支援 → None。"""
    if kind is Kind.ACTOR:
        return actress_ids
    if kind is Kind.MAKER:
        return frozenset([maker_id] if maker_id else [])
    if kind not in (Kind.SERIES, Kind.LABEL, Kind.DIRECTOR):
        return None
    named = [] if facts is None else _named_in(facts, kind)
    return frozenset(i for i in (_ident(n.id) for n in named) if i)


def _belongs(ref: EntityRef, facts: Facts | None, actress_ids: frozenset[str], maker_id: str | None) -> bool | None:
    """守衛事實：這部作品是否屬於 ref（id 一律 str 後比對）。缺／None 的欄位 → False，不是 None；kind 不支援 → None。"""
    owners = _owner_ids(ref.kind, facts, actress_ids, maker_id)
    return None if owners is None else str(ref.id) in owners


# ---------------------------------------------------------------- 片商最新作品（175c-T9，plan CD-175c-8）
PAGE_SIZE_MAKER = 30  # 膠囊一頁 30 部（前端翻頁 offset 以 30 遞增且不帶 limit）；DMM 為 offset 原生


def _dedupe_names(names: list[str]) -> list[str]:
    """以 maker_key_of 去重保序（保留第一次出現的寫法）：重複拼法只探一次，不佔 _resolve_maker 的前 3 個名額。"""
    first: dict[str, str] = {}
    for name in names:
        first.setdefault(maker_key_of(name), name)
    return list(first.values())


def _expand_names(names: list[str]) -> list[str]:
    """每個名字各經對照表展開（輸入、正名、同正名的全部別名；names.maker_names）後攤平。
    膠囊路徑只送片庫寫法（如 S1），DMM 站上的片商名（エスワン ナンバーワンスタイル）要靠這一步才進得了比對候選。"""
    return [n for name in names for n in maker_names(name)]


class DMMProvider:
    id = SOURCE
    capabilities = frozenset({Kind.ACTOR, Kind.SERIES, Kind.DIRECTOR, Kind.LABEL, Kind.MAKER, Kind.KEYWORD})
    supports_discovery = False
    fallback_streaming = True  # 最終陣列不重排，串流順序＝最終順序

    def __init__(self, scraper=None):
        self._scraper_obj = scraper

    @property
    def _scraper(self):
        if self._scraper_obj is None:
            self._scraper_obj = DMMScraper()
        return self._scraper_obj

    def resolve(self, kind: Kind, name: str) -> EntityRef | None:
        """女優／系列／導演／label／片商名稱 → 站上同一個實體；其他 kind 與空白輸入 → None（0 請求）。

        傳輸只經 list_contents（stage 1）與 fetch_facts（stage 2）；比對全為精確（fold 相等）；
        傳輸例外（SourceBlocked／SourceUnreachable／其他）原樣往外丟，不吞、不轉型、不入快取。
        """
        if kind not in _RESOLVE_KINDS or not fold(name):
            return None
        if kind is Kind.MAKER:
            return self._resolve_maker(maker_names(name))
        probe = _stage1(self._scraper, name)
        if kind is Kind.ACTOR:
            return _pick_actor(probe.rows, name)
        return _pick_named(probe, _stage2(self._scraper, probe), kind, name)

    def _resolve_maker(self, names: list[str]) -> EntityRef | None:
        """逐個拼法各打一次 stage 1，命中即停，至多前 3 個；命中集合＝傳入的全部 names（不展開、不補別名）。"""
        spellings = {maker_key_of(n) for n in names}
        for name in [n for n in names if fold(n)][:_MAKER_PROBE_MAX]:
            ref = _pick_maker(_stage1(self._scraper, name).rows, spellings)
            if ref is not None:
                return ref
        return None

    def _page(self, result: ListResult) -> Page:
        """列表一頁 → Page（關鍵字與實體共用）：丟掉缺 id 的列，對其餘列的 id 做恰一次 fetch_facts
        （空視窗 0 次；先於回傳＝先於 seed），逐列組 WorkItem。fetch_facts 失敗原樣往外丟（與列表同主機同進退）。"""
        rows = [r for r in result.rows if r.get("id")]
        facts = self._scraper.fetch_facts(list(dict.fromkeys(r["id"] for r in rows))) if rows else {}
        items = [_row_item(self._scraper, row, facts.get(row["id"])) for row in rows]
        return Page(items, has_next=result.has_next, total=result.total)

    def search_keyword(self, q: str, w: Window) -> Page:
        """標題／關鍵字一頁。呼叫形狀固定 list_contents(q, limit=, offset=)（不傳 filter）。
        列表失敗（被擋／連不上）原樣往外拋，由 relay 接住換下一家。"""
        return self._page(self._scraper.list_contents(q, limit=w.limit, offset=w.offset))

    def list_entity(self, ref: EntityRef, w: Window) -> Page:
        """實體（女優／系列／導演／label／片商）的完整作品，含預購未發行；其他 kind → ValueError（0 請求）。"""
        key = _FILTER_KEY.get(ref.kind)
        if key is None:
            raise ValueError(f"dmm list_entity: unsupported kind {ref.kind}")
        flt = {key: {"ids": [{"id": ref.id}], "op": "OR"}}
        return self._page(self._scraper.list_contents(None, filter=flt, limit=w.limit, offset=w.offset))

    def list_actors_page(self, refs: list[EntityRef], w: Window, now: datetime, seen: set) -> ActorsPage:
        """多位女優一次 OR 查詢的一頁，套「近 90 天＋預購、女優 ≤4 人」；kept 恰一次 fetch_facts。
        seen 跨頁共用（去重）。列表失敗原樣往外拋。"""
        flt = {"actressIds": {"ids": [{"id": r.id} for r in refs], "op": "OR"}}
        result = self._scraper.list_contents(None, filter=flt, limit=w.limit, offset=w.offset)
        by_id = {r["id"]: r for r in result.rows if r.get("id")}
        kept, reached = select_recent([_recent_row(r, now) for r in by_id.values()], now, seen)
        page = self._page(result._replace(rows=[by_id[k.content_id] for k in kept]))
        return ActorsPage(page.items, len(result.rows), result.has_next, reached)

    def _detail_or_shallow(self, content_id: str, shallow: Video) -> Video:
        """詳情卡；失敗（例外或回 None）退 shallow（與今天相同）。"""
        try:
            video = self._scraper._fetch_by_id(content_id)
        except Exception:
            logger.error("DMM enrichment failed: %s", content_id)
            return shallow
        return shallow if video is None else video

    def enrich(self, item: WorkItem, ref=None) -> Enriched:
        """ref＝實體參照（梯子／片商路徑）或 None（KEYWORD）。卡片沿用 _fetch_by_id；belongs 全由 item.ref 的
        列表事實算出（零網路）；卡的 number 為空時補 item.number；只有實體路徑自補 _source（梯子沒有 run 的收尾補）。"""
        content_id, shallow, facts, actress_ids, maker_id = item.ref
        card = self._detail_or_shallow(content_id, shallow).to_legacy_dict()
        if not card.get("number"):
            card["number"] = item.number
        if ref is None:
            return Enriched(card, None)
        card["_source"] = SOURCE
        return Enriched(card, _belongs(ref, facts, actress_ids, maker_id))

    def run(self, kind: Kind, target: str, w: Window, *, status_callback=None, result_callback=None,
            discovery_only: bool = False) -> list[dict]:
        if kind is not Kind.KEYWORD:
            raise ValueError(f"dmm run: unsupported kind {kind}")
        if discovery_only:
            return []
        if status_callback:
            status_callback("dmm", "searching")
        page = self.search_keyword(target, w)
        if not page.items:
            return []
        res = run_window(
            self,
            page.items,
            None,
            result_callback=result_callback,
            on_fail="degrade",
            delay=0,
            breaker=False,
            guard=False,
        )
        if status_callback:
            status_callback("done", f"found:{len(res.cards)}")
        for card in res.cards:
            card["_source"] = "dmm"
        return res.cards

    def run_maker(self, maker_key, label, spellings, offset, *, limit=None, titles=None, today=None,
                  status_callback=None, result_callback=None, db_path=None) -> MakerSearchResult:
        """片商最新作品（175c-T9，CD-175c-8）：label 與各拼法 → 片商 id → 依 id 列出完整作品（含預購）→ 補詳情。

        比對候選＝label 與各拼法各自展開（正名＋別名）後以 maker_key_of 去重保序；展開只用於本地比對，
        maker_key、spellings 與回傳值都不改寫。片庫樣本相關的參數接受但不使用（DMM 以片商 id 精查，
        不需要樣本，也不寫 JavBus 的對照表）；limit=None ⇒ 視窗取 30；offset 為 DMM 原生，不要求 30 的倍數。
        結果順序＝站方清單順序，不重排。"""
        if status_callback:
            status_callback(SOURCE, "searching")
        names = _dedupe_names(_expand_names([label, *spellings]))
        try:
            ref = self._resolve_maker(names)
            if ref is None:
                return MakerSearchResult([], False, "maker_not_found")
            page = self.list_entity(ref, Window(offset, limit or PAGE_SIZE_MAKER))
        except Exception as err:
            logger.warning("dmm maker %s failed (%s%s)", maker_key, type(err).__name__,
                           "/blocked" if isinstance(err, SourceBlocked) else "")
            return MakerSearchResult([], False, "maker_unreachable")
        if not page.items:
            return MakerSearchResult([], False, "maker_empty")
        res = run_window(
            self,
            page.items,
            ref,
            result_callback=result_callback,
            on_fail="degrade",
            delay=0,
            breaker=False,
            guard=False,  # CD-175c-8：provider 自己的入口，不在梯子上
        )
        cards = res.cards
        for card in cards:
            card["_source"] = SOURCE
        if status_callback:
            status_callback("done", f"found:{len(cards)}")
        return MakerSearchResult(cards, page.has_next, None)
