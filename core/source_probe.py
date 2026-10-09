"""
來源探測核心（TASK-163b-T1 / CD-163b-1～7）。

探測「宣告」屬於 scraper（`probe_plan()`），「判讀」屬於這裡：
`classify_http`／`classify_exception`／`merge_outcomes`／`run_probes`／`REASON_CODES`
與 skipped 規則全在本檔，scraper 不做判讀。

只吃呼叫端傳進來的 `ProxySettings` 快照（請求體組出的 frozen 物件）；
整條探測路徑不碰已儲存的設定（I-3）。
log 紀律：不記代理位址或例外原文（可能含 user:pass@），要記只記 reason code／id。
頂層只 import 標準庫／requests／urllib3／core.proxy_policy；scraper 類別在
`scraper_class_for()` 內才 import（BE-LINT-09 循環面）。
"""
from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

import requests
from urllib3.exceptions import NameResolutionError, ReadTimeoutError

from core.logger import get_logger
from core.proxy_policy import ProxySettings, proxy_for, source_needs_jp_ip

logger = get_logger('source_probe')

PROBE_TIMEOUT = (5, 8)
PROBE_BUDGET_S = 12

HEAD_LIMIT = 8 * 1024
FULL_LIMIT = 256 * 1024

REASON_CODES = frozenset({
    'ok', 'cf_challenge', 'http_status', 'app_rejected',
    'proxy', 'timeout', 'tls', 'dns', 'network', 'error',
    'windows_verifier', 'self_hosted', 'unknown', 'unprobeable',
})

MANUAL_ONLY_IDS = frozenset({'javlibrary', 'fc-javten'})
BUILTIN_IDS = ('dmm', 'javbus', 'jav321', 'javdb', 'd2pass', 'heyzo', 'fc2', 'avsox')

_CF_BODY_MARKERS = (b'just a moment', b'cf-browser-verification', b'challenge-platform')
_STATE_RANK = {'ok': 0, 'blocked': 1, 'unreachable': 2}


@dataclass(frozen=True)
class ProbeResponse:
    """中央讀完回應後交給 `check` 的精簡視圖（不外洩 `requests.Response`）。"""
    status: int
    headers_subset: dict
    head: bytes
    body_complete: bool


@dataclass(frozen=True)
class ProbeTarget:
    host: str
    send: Callable[[], requests.Response]
    ok_404: bool = False
    check: Optional[Callable[[ProbeResponse], bool]] = None
    read: Literal['head8k', 'full_capped'] = 'head8k'


@dataclass(frozen=True)
class ProbePlan:
    targets: list = field(default_factory=list)
    mode: Literal['any', 'all'] = 'any'


@dataclass(frozen=True)
class ProbeOutcome:
    state: str
    reason: str
    host: Optional[str]
    status: Optional[int]


# ---------------------------------------------------------------- 判讀

def _has_cf_marker(headers: dict, head: bytes) -> bool:
    if headers.get('server', '').lower() == 'cloudflare':
        return True
    low = head.lower()
    return any(m in low for m in _CF_BODY_MARKERS)


def classify_http(status: int, headers: dict, head: bytes, ok_404: bool) -> tuple:
    """回 (state, reason)。標記只在 403／503 才讀、只用來細分 reason。"""
    if headers.get('cf-mitigated', '').lower() == 'challenge':
        return 'blocked', 'cf_challenge'
    if status in (403, 503) and _has_cf_marker(headers, head):
        return 'blocked', 'cf_challenge'
    if status < 400 or (ok_404 and status in (404, 410)):
        return 'ok', 'ok'
    return 'blocked', 'http_status'


def classify_exception(exc: BaseException) -> str:
    """只看例外型別，不解析例外字串。順序有意義（ProxyError／ConnectTimeout 皆為 ConnectionError 子類）。"""
    exc_mod = requests.exceptions
    if isinstance(exc, (exc_mod.ProxyError, exc_mod.InvalidURL, exc_mod.InvalidSchema)):
        return 'proxy'
    if isinstance(exc, exc_mod.Timeout):
        return 'timeout'
    if isinstance(exc, exc_mod.SSLError):
        return 'tls'
    if isinstance(exc, exc_mod.ConnectionError):
        first = exc.args[0] if exc.args else None
        if isinstance(first, ReadTimeoutError):  # iter_content 期間 requests 包成 ConnectionError
            return 'timeout'
        if isinstance(getattr(first, 'reason', None), NameResolutionError):
            return 'dns'
        return 'network'
    if isinstance(exc, exc_mod.RequestException):
        return 'network'
    return 'error'


def merge_outcomes(mode: str, outcomes: list) -> ProbeOutcome:
    """any → 取最佳（ok > blocked > unreachable）；all → 取最差。同級取先出現者。"""
    if mode == 'all':
        return max(outcomes, key=lambda o: _STATE_RANK[o.state])
    return min(outcomes, key=lambda o: _STATE_RANK[o.state])


# ---------------------------------------------------------------- 讀取

def _needs_head(status: int, headers: dict) -> bool:
    """head8k 只為 403／503 細分 CF reason；已有 cf-mitigated header 就不必再讀。"""
    return status in (403, 503) and 'cf-mitigated' not in headers


def _read_body(resp: requests.Response, limit: int) -> tuple:
    """讀到 >= limit 立即停（不多要一塊）；回 (bytes, complete)。"""
    buf = b''
    for chunk in resp.iter_content(chunk_size=8192):
        buf += chunk
        if len(buf) >= limit:
            return buf[:limit], False
    return buf, True


def read_response(resp: requests.Response, read: str, ok_404: bool = False) -> ProbeResponse:
    headers = {
        k: resp.headers.get(k, '') for k in ('cf-mitigated', 'server') if k in resp.headers
    }
    status = resp.status_code
    buf, complete = b'', False
    try:
        if read == 'full_capped' and classify_http(status, headers, b'', ok_404)[0] == 'ok':
            buf, complete = _read_body(resp, FULL_LIMIT)  # 只有正常 2xx 才讀完整 body；失敗照實拋出
        elif _needs_head(status, headers):
            try:
                buf, _ = _read_body(resp, HEAD_LIMIT)
            except requests.exceptions.RequestException:
                buf = b''  # 只剩 status／header 可判讀，不覆蓋成 unreachable
    finally:
        resp.close()
    return ProbeResponse(status, headers, buf, complete)


def probe_target(target: ProbeTarget) -> ProbeOutcome:
    host = target.host
    try:
        pr = read_response(target.send(), target.read, target.ok_404)
        state, reason = classify_http(pr.status, pr.headers_subset, pr.head, target.ok_404)
        if (
            state == 'ok' and target.check is not None
            and target.read == 'full_capped' and pr.body_complete
            and not target.check(pr)
        ):
            state, reason = 'blocked', 'app_rejected'
        return ProbeOutcome(state, reason, host, pr.status)
    except requests.exceptions.RequestException as exc:
        return ProbeOutcome('unreachable', classify_exception(exc), host, None)
    except Exception:  # probe-worker-catch-all
        logger.warning('probe_unexpected_error source_host=%s', host)
        return ProbeOutcome('unreachable', 'error', host, None)


# ---------------------------------------------------------------- id 分類

def scraper_class_for(source_id: str):
    """八個內建 id → scraper 類別；lazy import（避免與 core.scrapers.base 頂層循環）。"""
    from core.scrapers.avsox import AVSOXScraper
    from core.scrapers.d2pass import D2PassScraper
    from core.scrapers.dmm import DMMScraper
    from core.scrapers.fc2_official import FC2OfficialScraper
    from core.scrapers.heyzo import HEYZOScraper
    from core.scrapers.jav321 import JAV321Scraper
    from core.scrapers.javbus import JavBusScraper
    from core.scrapers.javdb import JavDBScraper

    return {
        'dmm': DMMScraper, 'javbus': JavBusScraper, 'jav321': JAV321Scraper,
        'javdb': JavDBScraper, 'd2pass': D2PassScraper, 'heyzo': HEYZOScraper,
        'fc2': FC2OfficialScraper, 'avsox': AVSOXScraper,
    }[source_id]


def skip_reason(source_id: str) -> Optional[str]:
    """不探測的 id 分類（唯一一處）；內建 id 回 None。"""
    if source_id in MANUAL_ONLY_IDS:
        return 'windows_verifier'
    if source_id.startswith('metatube:'):
        return 'self_hosted'
    if source_id not in BUILTIN_IDS:
        return 'unknown'
    return None


# ---------------------------------------------------------------- runner

def build_jobs(snap: ProxySettings, source_ids: list) -> tuple:
    """回 (skipped: {id: reason}, plans: {id: ProbePlan}, failed: [id])。"""
    from core.scrapers.models import ScraperConfig

    skipped: dict = {}
    plans: dict = {}
    failed: list = []
    for source_id in source_ids:
        reason = skip_reason(source_id)
        if reason:
            skipped[source_id] = reason
            continue
        try:
            cls = scraper_class_for(source_id)
            scraper = cls(ScraperConfig(proxy_settings=snap))
            plan = scraper.probe_plan(PROBE_TIMEOUT)
        except Exception:
            logger.warning('probe_build_failed source=%s', source_id)
            failed.append(source_id)
            continue
        if plan is None or not plan.targets:
            skipped[source_id] = 'unprobeable'
            continue
        plans[source_id] = plan
    return skipped, plans, failed


def run_jobs(plans: dict) -> dict:
    """所有目標同時進行、單一預算；回 {id: [ProbeOutcome...]}（順序同 plan.targets）。"""
    jobs = [(sid, t) for sid, plan in plans.items() for t in plan.targets]
    results: dict = {sid: [] for sid in plans}
    if not jobs:
        return results
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(jobs)))
    try:
        futures = [pool.submit(probe_target, t) for _, t in jobs]
        done, not_done = concurrent.futures.wait(futures, timeout=PROBE_BUDGET_S)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    for (sid, target), fut in zip(jobs, futures, strict=True):
        if fut in done:
            results[sid].append(fut.result())
        else:
            results[sid].append(ProbeOutcome('unreachable', 'timeout', target.host, None))
    return results


def _row(source_id: str, outcome: ProbeOutcome, snap: ProxySettings) -> dict:
    state = outcome.state
    via_proxy = proxy_for('source_query', source_id=source_id, settings=snap) is not None
    advice = 'jp_ip' if state == 'blocked' and source_needs_jp_ip(source_id) else None
    return {
        'state': state, 'reason': outcome.reason, 'host': outcome.host,
        'status': outcome.status, 'via_proxy': via_proxy, 'advice': advice,
    }


def _skipped_row(reason: str) -> dict:
    return {
        'state': 'skipped', 'reason': reason, 'host': None,
        'status': None, 'via_proxy': False, 'advice': None,
    }


def run_probes(snap: ProxySettings, source_ids: list) -> dict:
    """對每個 id 同時各測一次；回 {id: row}，每個送來的 id 都有結果。"""
    assert snap is not None, 'run_probes 必須帶請求體快照'
    ids = list(dict.fromkeys(source_ids))
    skipped, plans, failed = build_jobs(snap, ids)
    outcomes = run_jobs(plans)
    rows: dict = {}
    for source_id in ids:
        if source_id in skipped:
            rows[source_id] = _skipped_row(skipped[source_id])
        elif source_id in failed:
            rows[source_id] = _row(source_id, ProbeOutcome('unreachable', 'error', None, None), snap)
        else:
            merged = merge_outcomes(plans[source_id].mode, outcomes[source_id])
            rows[source_id] = _row(source_id, merged, snap)
    return rows
