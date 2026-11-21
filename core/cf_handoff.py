# core/cf_handoff.py
"""
CF 轉交 broker（plan-168d CD-168d-1/2/4/5/8/10）。

伺服器行程永遠註冊 ``HandoffCfTransport``：scraper 呼叫同步的 ``CfTransport`` 方法，
內部把「抓頁／導航／開驗證視窗」當 job 交給**同一把 key** 的殼（輪詢領走），
有界地等結果（claim 10 s ＋ exec 最長 60 s；無殼立即失敗）。

時序類只守不變式（I-H1～I-H5、I-R），由 ``tests/unit/test_cf_handoff.py`` 驗證：
所有阻塞等待一律 ``Event.wait(timeout=…)``；時鐘 ``_now``、事件工廠 ``_event_factory``、
逾時表 ``TIMEOUTS`` 都是模組屬性，呼叫時才解析（測試可替換）。

``core`` 不 import ``web``／``windows``；sink 註冊在 ``web/app.py``（T2）。
log 不記 key 全文、不記 job 內容（只記 kind／前 6 碼雜湊）。
"""
from __future__ import annotations

import contextvars
import hashlib
import itertools
import threading
import time
from typing import Any, Optional
from urllib.parse import urlsplit

from core import search_cancel
from core.cf_transport import CfChallengeRequired, CfTransportUnavailable
from core.logger import get_logger
from core.proxy_policy import (
    ProxySettings,
    cf_window_proxy,
    cf_window_proxy_fingerprint,
    client_cf_settings,
)
from core.scrapers.fc2_javten import _JAVTEN_ALLOWED_NETLOCS, JAVTEN_ORIGIN
from core.scrapers.javlibrary import JAVLIBRARY_ORIGIN

logger = get_logger(__name__)

CF_SITE_ORIGINS = {'javlibrary': JAVLIBRARY_ORIGIN, 'fc-javten': JAVTEN_ORIGIN}
# 殼端白名單（windows/cf_shell.check_job）：netloc 整串精確屬於集合；scheme 取 CF_SITE_ORIGINS 的。
# javten 站方會落地 www.，引用 fc2_javten 既有常數不複製。
CF_SITE_NETLOCS = {
    'javlibrary': frozenset({urlsplit(JAVLIBRARY_ORIGIN).netloc.lower()}),
    'fc-javten': frozenset(_JAVTEN_ALLOWED_NETLOCS),
}

# (claim 逾時, exec 逾時) 秒
TIMEOUTS = {
    'is_ready': (10, 10),
    'begin_solve': (10, 15),
    'navigate_and_settle': (10, 45),
    'fetch': (10, 60),
}
HOLD_S = 20
LIVENESS_S = 45
MAX_VALUE_BYTES = 8 * 1024 * 1024
_EXPIRED_KEEP_S = 300

# 注入點（呼叫時才解析）
_now = time.monotonic
_event_factory = threading.Event

_UNSET = object()
current_key: contextvars.ContextVar = contextvars.ContextVar('cf_handoff_current_key', default=_UNSET)

_LOOPBACK_KEY = 'loopback'


def _key_tag(key) -> str:
    return hashlib.sha256(str(key).encode('utf-8')).hexdigest()[:6]


class _Job:
    def __init__(self, job_id: str, key: str, kind: str, args: dict):
        self.id = job_id
        self.key = key
        self.kind = kind
        self.args = args
        self.state = 'queued'  # queued | claimed | done | abandoned | expired
        self.claimed = _event_factory()
        self.done = _event_factory()
        self.ok = False
        self.value: Any = None
        self.error: Optional[str] = None
        self.message = ''
        self.t_end = 0.0


class Broker:
    """job 佇列＋殼註冊表。可獨立建立多個實例（I-R）；模組級單例僅是預設。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._epoch = hashlib.sha256(str(id(self)).encode() + str(time.time_ns()).encode()).hexdigest()[:8]
        self._jobs: dict[str, _Job] = {}
        self.shells: dict[str, dict] = {}
        self.last_failure: dict[str, str] = {}

    # ---- 註冊表 ----
    def register_shell(self, key, sites, applied_proxy=None, shell='windows', server_remote=False,
                       preparing=None) -> None:
        with self._lock:
            self.shells[key] = {
                'sites': sorted(str(s) for s in (sites or [])),
                'preparing': sorted(str(s) for s in (preparing or [])),
                'applied_proxy': applied_proxy,
                'shell': shell,
                'server_remote': bool(server_remote),
                'last_seen': _now(),
            }

    def fresh(self, key) -> bool:
        info = self.shells.get(key)
        if info is None:
            return False
        return _now() - info['last_seen'] <= LIVENESS_S

    def sites_for(self, key) -> list[str]:
        info = self.shells.get(key)
        if info is None:
            return []
        if not self.fresh(key):
            return []
        return list(info['sites'])

    def preparing_for(self, key) -> list[str]:
        """殼回報「視窗還在準備、尚未就緒」的站；stale／未登記 → []（同 sites_for 的 liveness 約束）。"""
        info = self.shells.get(key)
        if info is None:
            return []
        return list(info['preparing']) if self.fresh(key) else []

    def shell_info(self, key) -> Optional[dict]:
        info = self.shells.get(key)
        return dict(info) if info is not None else None

    # ---- job 流程 ----
    def _enqueue(self, key, kind, args) -> _Job:
        with self._lock:
            alive = self.fresh(key)
            if not alive:
                self.last_failure[key] = 'shell_lost'
                raise CfTransportUnavailable('CF shell is not registered or no longer alive')
            for stale in [j for j in self._jobs.values()
                          if j.state == 'expired' and _now() - j.t_end > _EXPIRED_KEEP_S]:
                self._jobs.pop(stale.id, None)
            job = _Job(f'{self._epoch}-{next(self._ids)}', key, kind, dict(args))
            self._jobs[job.id] = job
            return job

    def claim(self, key) -> Optional[dict]:
        """同 key 的殼領走最早的 queued job；沒有→None。領走即標 claimed（至多一次）。"""
        with self._lock:
            for job in self._jobs.values():
                if job.state != 'queued':
                    continue
                if job.key != key:
                    continue
                job.state = "claimed"
                job.claimed.set()
                return {'id': job.id, 'kind': job.kind, 'args': dict(job.args)}
            return None

    def complete(self, key, job_id, ok, value=None, error=None, message='') -> bool:
        """殼回報結果。只接受同 key 且當前為 claimed 的 job；否則 False（不改任何狀態）。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.key != key or job.state != 'claimed':
                return False
            if ok and isinstance(value, str) and len(value.encode('utf-8')) > MAX_VALUE_BYTES:
                ok, error, message = False, 'error', 'result too large'
            job.ok = bool(ok)
            job.value = value if ok else None
            job.error = None if ok else (error or 'error')
            job.message = str(message or '')
            job.state = 'done'
            if job.ok:
                self.last_failure.pop(key, None)
            job.done.set()
            return True

    def submit(self, key, kind, args):
        """阻塞等結果；I-H1：claim＋exec 逾時內一定返回或拋例外。"""
        search_cancel.checkpoint()  # gate: CF window job
        job = self._enqueue(key, kind, args)
        claim_timeout, exec_timeout = TIMEOUTS[kind]
        try:
            self._await_claim(job, claim_timeout)
            self._await_done(job, exec_timeout)
        finally:
            self._finish(job)
        if not job.ok:
            self._raise_for(job)
        return job.value

    def _finish(self, job: _Job) -> None:
        """done／abandoned 的 job 立即移除；expired 的留著（讓晚到的 result 被明確拒絕），
        一段時間後在 _enqueue 清掉。"""
        with self._lock:
            job.t_end = _now()
            if job.state in ('done', 'abandoned'):
                self._jobs.pop(job.id, None)

    def _await_claim(self, job: _Job, claim_timeout) -> None:
        deadline = _now() + claim_timeout
        remaining = max(0.0, deadline - _now())
        if not job.claimed.wait(timeout=remaining):
            with self._lock:
                if job.state == 'queued':
                    job.state = "abandoned"
                    self.last_failure[job.key] = 'shell_lost'
                    logger.warning(f'[cf_handoff] claim timeout kind={job.kind} key={_key_tag(job.key)}')
                    raise CfTransportUnavailable('CF shell did not pick up the job in time')

    def _await_done(self, job: _Job, exec_timeout) -> None:
        deadline = _now() + exec_timeout
        remaining = max(0.0, deadline - _now())
        if not job.done.wait(timeout=remaining):
            with self._lock:
                if job.state != 'done':
                    job.state = "expired"
                    self.last_failure[job.key] = 'shell_lost'
                    logger.warning(f'[cf_handoff] exec timeout kind={job.kind} key={_key_tag(job.key)}')
                    raise CfTransportUnavailable('CF shell did not return a result in time')

    @staticmethod
    def _raise_for(job: _Job) -> None:
        err, message = job.error, job.message
        if err == 'challenge':
            raise CfChallengeRequired(message)
        if err == 'unavailable':
            raise CfTransportUnavailable(message)
        if err == 'timeout':
            raise TimeoutError(message)
        raise RuntimeError(message)

    def consume_failure(self, key) -> Optional[str]:
        with self._lock:
            return self.last_failure.pop(key, None)


_broker = Broker()


def get_broker() -> Broker:
    return _broker


def consume_failure_here(key) -> Optional[str]:
    return _broker.consume_failure(key)


def _require_key() -> str:
    key = current_key.get()
    if key is _UNSET or key is None:
        raise CfTransportUnavailable('no shell identity for this request')
    return key


class HandoffCfTransport:
    """``CfTransport`` 實作：把呼叫轉成 job 交給 ``current_key`` 的殼。"""

    def begin_solve(self, origin_url: str, cache_key: str) -> None:
        _broker.submit(_require_key(), 'begin_solve', {'origin_url': origin_url, 'cache_key': cache_key})

    def is_ready(self, cache_key: str) -> bool:
        return bool(_broker.submit(_require_key(), 'is_ready', {'cache_key': cache_key}))

    def available_sites(self) -> list[str]:
        key = current_key.get()
        if key is _UNSET:
            key = _LOOPBACK_KEY
        if key is None:
            return []
        return _broker.sites_for(key)

    def available_here(self) -> bool:
        key = current_key.get()
        if key is _UNSET or key is None:
            return False
        return _broker.fresh(key)

    def fetch(self, url: str, cache_key: str) -> str:
        return _broker.submit(_require_key(), 'fetch', {'url': url, 'cache_key': cache_key})

    def navigate_and_settle(self, url: str, cache_key: str) -> str:
        return _broker.submit(_require_key(), 'navigate_and_settle', {'url': url, 'cache_key': cache_key})


_transport = HandoffCfTransport()


def transport() -> HandoffCfTransport:
    return _transport


def restart_needed_here(settings: ProxySettings) -> bool:
    """這台殼套用中的代理規格（指紋）與「依目前設定重算的有效規格」不同 ⇒ 要重開才生效。"""
    key = current_key.get()
    if key is _UNSET or key is None:
        return False
    info = _broker.shell_info(key)
    if info is None:
        return False
    if info['shell'] == 'mac':
        spec = None
    else:
        effective, _local_direct = client_cf_settings(settings, info['server_remote'])
        spec = cf_window_proxy(effective)
    return cf_window_proxy_fingerprint(spec) != info['applied_proxy']
