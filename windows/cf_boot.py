"""CF 驗證視窗的殼端控制器（168e-T13，CD-2/3）。

把「啟動時抓設定→建視窗→建 agent」與「連線頁按『重試』時補建／重讀」收成同一份程式：

* ``initial()``  啟動前呼叫，行為與舊的接線逐字等價（announce 由入口在原位置呼叫 ``announce_initial()``）。
* ``status()``   交給連線頁的唯讀狀態（有 agent 就是 ``agent.public_status()``，否則靜態原因）。
* ``retry()``    唯一的補建入口，只在 ``cf_retry`` bridge 這個明確觸發點執行，沒有任何自動補試：
  建過（``build_cf_windows`` 已嘗試過）→ 只 ``agent.refresh_now()``；從未建過 → 抓設定→建窗→建 agent→
  三個登記點→announce→start；回覆前最多等 ``RETRY_SETTLE_S`` 秒讓狀態離開「正在啟動」（事件等待）。
* ``destroy_all()`` 銷毀「目前」的 CF 視窗（主視窗關閉時查表，而不是捕捉建窗當下的物件）。

所有權：``retry()`` 在途期間為 busy，重入回 ``busy``；``status()`` 不取鎖。本檔不 import bridge 模組
（誰註冊 provider／handler 由兩個入口決定），也不碰這個行程的設定檔（設定一律向伺服器抓）。
"""
from __future__ import annotations

import contextlib
import threading
import time

from core import client_settings
from windows import cf_shell, cf_windows

RETRY_SETTLE_S = 6

# 注入點：呼叫時才解析（測試可替換）
_monotonic = time.monotonic


def _wait_for(pred, timeout, wake):
    """事件等待（非輪詢）：``wake`` 是會在狀態可能改變時被 set 的事件；每次醒來重判 ``pred``。
    回 ``pred()`` 的最後結果；總等待不超過 ``timeout`` 秒。"""
    deadline = _monotonic() + timeout
    while True:
        wake.clear()
        if pred():
            return True
        remaining = deadline - _monotonic()
        if remaining <= 0:
            return False
        wake.wait(remaining)


def agent_retry_handler(agent):
    """本機模式（沒有補建，視窗隨啟動一次建好）的 ``cf_retry`` 處理器：只重讀 agent 狀態，
    最多等 ``RETRY_SETTLE_S`` 秒讓狀態離開「正在啟動」；不支援平台的 agent 直接回 unsupported。"""
    def _retry():
        agent.refresh_now()
        wake = getattr(agent, 'status_changed', None) or threading.Event()
        _wait_for(lambda: agent.public_status().get('reason') != 'starting', RETRY_SETTLE_S, wake)
        return {"ok": True, "cf": agent.public_status()}
    return _retry


class CfShellController:
    def __init__(self, logger, boot_kind, local_origin, prefetched_cf=None):
        self._logger = logger
        self._kind = boot_kind                       # 'client' | 'local' | 'offline'
        self._local_origin = local_origin
        self._prefetched_cf = prefetched_cf
        self._cf_set = cf_windows.CfWindowSet()
        self._agent = None
        self._built = False                          # build_cf_windows 嘗試過即為真（set-once）
        self._static_reason = None
        self._busy = threading.Lock()
        self._bound = False
        self._quitting = False                       # destroy_all() 設；補建完成時若已結束就當場銷毀
        self._lifecycle = None
        self._is_quitting = lambda: False
        self._idle_wake = threading.Event()          # agent 不存在時的等待事件（不會被 set）

    # ---- 讀取 ----
    @property
    def cf_set(self):
        return self._cf_set

    @property
    def agent(self):
        return self._agent

    def status(self):
        agent = self._agent
        if agent is not None:
            return agent.public_status()
        return cf_windows.cf_status_static(self._static_reason)

    def _settled(self):
        return self.status().get('reason') != 'starting'

    # ---- 啟動 ----
    def _target(self):
        """(server_url, token, server_origin)；每次呼叫當下重讀（不沿用啟動快照）。"""
        if self._kind == 'local':
            return self._local_origin, None, self._local_origin
        server_url, token = client_settings.server_pair()
        return server_url, token, client_settings.server_origin(self._local_origin)

    def initial(self):
        """啟動前呼叫：離線啟動／不支援平台／抓不到設定一律不建窗（與舊接線等價）。"""
        if self._kind == 'offline':
            self._static_reason = 'offline_boot'
            return
        server_url, token, server_origin = self._target()
        if not cf_windows.cf_shell_supported():
            self._make_agent(server_origin, token, False, False)
            return
        self._boot_cf(server_url, token, server_origin, self._prefetched_cf)

    def _boot_cf(self, server_url, token, server_origin, prefetched=None):
        """抓設定→建窗→建 agent；回是否建了 agent。抓不到設定＝不建窗（fail-closed）。"""
        fetched = prefetched if prefetched is not None else cf_windows.fetch_client_cf(server_url, token, server_origin)
        ok, reason, eff_settings, local_direct, server_remote = fetched
        if not ok:
            self._static_reason = reason
            self._logger.warning("CF settings unavailable (%s), CF windows not built", reason)
            return False
        self._built = True
        built = cf_windows.build_cf_windows(self._logger, eff_settings, local_direct)
        self._make_agent(server_origin, token, server_remote, True, built)
        return True

    def _make_agent(self, origin, token, server_remote, supported, built=None):
        built = built if built is not None else cf_windows.CfWindowSet()
        agent = cf_shell.CfShellAgent(origin=origin, token=token, windows=built,
                                      server_remote=server_remote, supported=supported)
        self._adopt(built, agent)

    def _adopt(self, built, agent):
        self._cf_set = built
        self._agent = agent
        if self._shutting_down():
            self._destroy_windows(built)             # 建窗期間使用者已關主視窗／結束：不登記、當場銷毀
            return
        if self._bound:                              # 補建路徑：啟動時的登記由入口按原順序做
            cf_windows.attach_close_guards(built, self._is_quitting)
            if self._lifecycle is not None:
                self._lifecycle.register_cf_windows(self._site_windows(built))

    @staticmethod
    def _site_windows(built):
        return {'javlibrary': built.jl_win, 'fc-javten': built.javten_win}

    # ---- 入口接線 ----
    def bind(self, lifecycle, is_quitting):
        """入口把 lifecycle（Mac 為 None）與「是否正在結束」探針交進來；之後補建才知道要登記到哪。"""
        self._lifecycle = lifecycle
        self._is_quitting = is_quitting
        self._bound = True

    def attach_guards(self):
        cf_windows.attach_close_guards(self._cf_set, self._is_quitting)

    def announce_initial(self):
        if self._agent is not None:
            self._agent.announce()

    def start(self):
        if self._agent is not None:
            self._agent.start()

    def stop(self):
        if self._agent is not None:
            self._agent.stop()

    def destroy_all(self):
        """主視窗關閉：銷毀目前的 CF 視窗（含補建的），隱藏視窗不銷毀會讓行程殘留。"""
        self._quitting = True                        # 先設旗標再查表：與 _adopt 的「先登記再看旗標」互相補位
        self._destroy_windows(self._cf_set)

    def _shutting_down(self):
        return self._quitting or (self._bound and bool(self._is_quitting()))

    @staticmethod
    def _destroy_windows(win_set):
        for cf_win in (win_set.jl_win, win_set.javten_win):
            if cf_win is not None:
                with contextlib.suppress(Exception):
                    cf_win.destroy()

    # ---- 重試 ----
    def retry(self):
        if not self._busy.acquire(blocking=False):
            return {"ok": False, "reason": "busy"}
        try:
            return self._retry_locked()
        except Exception as e:                       # noqa: BLE001
            self._logger.warning("CF retry failed: %s", type(e).__name__)
            return {"ok": False, "reason": "failed"}
        finally:
            self._busy.release()

    def _windows_built(self):
        return self._built

    def _retry_locked(self):
        if not cf_windows.cf_shell_supported():
            return {"ok": True, "cf": {"state": "unsupported", "reason": None, "proxy_note": None, "sites": []}}
        if self._windows_built():
            self._agent.refresh_now()
        else:
            self._first_build()
        if self._shutting_down():                    # 正在結束：不要讓非 daemon 的 bridge 緒多等 6 秒拖慢退出
            return {"ok": True, "cf": self.status()}
        self._wait(self._settled, RETRY_SETTLE_S)
        return {"ok": True, "cf": self.status()}

    def _first_build(self):
        server_url, token, server_origin = self._target()
        if not server_url:
            return
        if self._boot_cf(server_url, token, server_origin) and not self._shutting_down():
            self._agent.announce()
            self._agent.start()

    def _wait(self, settled, timeout):
        agent = self._agent
        wake = getattr(agent, 'status_changed', None) or self._idle_wake
        return _wait_for(settled, timeout, wake)
