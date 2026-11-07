"""Source reachability probe + in-process snapshot (feature/142-v2 T1).

Probe means are a closed set of two (CD-2):
  - UNC ``\\\\host\\...`` → TCP connect to port 445 (2s timeout)
  - everything else → ``os.scandir(root)`` in a worker thread (20s wait)

Public API:
  - ``get_snapshot()`` — pure memory read; safe from sync threadpool endpoints
  - ``schedule_reprobe_if_stale()`` — async-only; schedules background reprobe
  - ``wait_for_first_probe()`` — async-only; bounded wait for cold start only
  - ``wait_for_inflight_probe()`` — async-only; bounded wait for a recheck probe
  - ``unc_host(native_path)`` — public (T2 display name; ruff PLC2701)
  - ``disk_label(native_path)`` — public (195b group name; ruff PLC2701)
  - ``source_keys_and_prefixes(gallery_config)`` — public route helper
  - ``owning_source_index(file_uri, prefixes)`` — public longest-prefix match
  - ``RECHECK_MIN_INTERVAL_S`` — recheck throttle window in seconds
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import os
import socket
import threading
import time

from core.config import iter_gallery_sources, load_config
from core.logger import get_logger
from core.path_utils import uri_to_fs_path

logger = get_logger(__name__)

# TTL 非對稱（CD-5）：全好時重探買不到東西——碟中途被拔，封面自己會失敗＝今天的行為；
# 已經不可達時使用者隨時會把碟插回來，要讓 footer 那句話快點消失。
_TTL_HEALTHY = 600.0
_TTL_DEGRADED = 60.0
_TCP_TIMEOUT_S = 2.0
_EXISTS_WAIT_S = 20.0
_RETRY_SLEEP_S = 1.0
_FIRST_PROBE_WAIT_S = 120.0
RECHECK_MIN_INTERVAL_S = 10.0

# Sentinel for "never probed" (module just imported / process just started).
# time.monotonic() is seconds-since-boot on Linux/macOS/Windows, so a literal
# 0.0 default reads as "fresh" (not stale) for up to _TTL_HEALTHY seconds after
# boot — the exact window in which a freshly booted NAS/PC needs the probe most.
# -inf makes "now - _snapshot_at" unconditionally exceed any TTL, no branch needed.
_NEVER = float("-inf")

_NEG_ERRNOS = {
    errno.EHOSTUNREACH,
    errno.ENETUNREACH,
    errno.ETIMEDOUT,
    errno.ENETDOWN,
}

_lock = threading.Lock()
_snapshot: dict[str, str] = {}
_snapshot_at: float = _NEVER
_in_flight: bool = False
_pending_exists: dict[str, asyncio.Future] = {}
_reprobe_task: asyncio.Task | None = None


def _now() -> float:
    """Indirection over ``time.monotonic()`` so tests can inject a fake clock.

    Patching ``time.monotonic`` directly would also break asyncio's event loop
    timers (``loop.time()`` is ``time.monotonic()`` on the default loop), which
    would hang any ``await asyncio.sleep(...)`` in the same test. Module-level
    function (not a lambda/method) so ``unittest.mock.patch.object`` can target it.
    """
    return time.monotonic()


def _current_ttl_locked() -> float:
    """Pick the snapshot TTL from the *last* snapshot (caller must hold ``_lock``)."""
    return (
        _TTL_DEGRADED
        if any(status in ("unreachable", "no_permission") for status in _snapshot.values())
        else _TTL_HEALTHY
    )


def get_snapshot() -> dict[str, str]:
    """Pure memory read of the latest probe snapshot. Never schedules IO."""
    with _lock:
        return dict(_snapshot)


async def schedule_reprobe_if_stale(max_age: float | None = None) -> None:
    """If the snapshot is stale (TTL is status-dependent — see ``_TTL_HEALTHY``/``_TTL_DEGRADED``) and no probe is in flight, schedule one.

    Must only be called from an async context (has a running event loop).
    Ownership of ``_in_flight`` is taken under the lock before ``create_task``.
    """
    global _in_flight, _reprobe_task

    should_schedule = False
    with _lock:
        now = _now()
        ttl = _current_ttl_locked() if max_age is None else max_age
        stale = (now - _snapshot_at) > ttl
        if stale and not _in_flight:
            _in_flight = True
            should_schedule = True

    if not should_schedule:
        return

    coro = _probe_all()
    try:
        _reprobe_task = asyncio.create_task(coro)
    except Exception:
        coro.close()
        with _lock:
            _in_flight = False
        logger.warning(
            "schedule_reprobe_if_stale: create_task failed; released in-flight",
            exc_info=True,
        )


async def wait_for_first_probe(timeout: float = _FIRST_PROBE_WAIT_S) -> None:
    """Cold start only: wait until the first snapshot has been written.

    Returns immediately once any probe has ever completed, so the warm path
    pays nothing. Caller is a fire-and-forget fetch, so waiting costs no UI.

    Correctness is *not* derived from ``timeout`` — ``_probe_all`` is
    sequential, so its total duration scales with source count and is not a
    number this function can guess correctly. What actually bounds the wait
    is the task itself finishing: every individual probe has its own timeout
    (TCP 2s x2 + 1s retry-sleep, or exists 20s x2 + 1s), and ``_probe_all``
    always writes the snapshot in its ``finally`` block, so the shielded
    ``await`` below resolves as soon as that happens, however long it took.

    ``timeout`` (``_FIRST_PROBE_WAIT_S``) is a pure fuse, not an expected
    wait time: it exists only to stop a pathologically stuck probe (e.g. a
    hung syscall that outruns even the per-probe timeouts) from wedging this
    request forever. It is set far above any realistic total probe duration
    so it never trips on the correctness path; on trip, the exception is
    swallowed and the caller just gets whatever snapshot exists (possibly
    still empty) — it does not cancel the still-running task (``shield``).
    """
    with _lock:
        already_probed = _snapshot_at != _NEVER
        task = _reprobe_task

    if already_probed:
        return
    if task is None or task.done():
        return

    # 例外一律吞掉，其中一種是**設計上接受**的：LAN 模式（`web/lan_listener.py`）用第二個
    # uvicorn thread ＋ 自己的 event loop 服務同一個 app，而 `_reprobe_task` 屬於 loopback
    # 那個 loop ⇒ 跨 loop await 會拋，於是這裡直接返回、端點回當下的快照。
    # 後果與其他兩個已記載的殘留同一級：那句話晚一次導覽才出現（下次進來快照已經寫好了）。
    # 不改成跨 loop 的完成訊號——那是這支函式的第三次改寫，而收益只有「早一次導覽」。
    with contextlib.suppress(Exception):
        await asyncio.wait_for(asyncio.shield(task), timeout)


async def wait_for_inflight_probe(timeout: float = _FIRST_PROBE_WAIT_S) -> None:
    """Wait for the currently running probe task, if any, then return.

    Only looks at ``_reprobe_task``; never reads ``_snapshot_at``.
    """
    with _lock:
        task = _reprobe_task
    if task is None or task.done():
        return
    with contextlib.suppress(Exception):
        await asyncio.wait_for(asyncio.shield(task), timeout)


def unc_host(native_path: str) -> str | None:
    """Return ``\\\\host`` for UNC paths; ``None`` otherwise.

    Public (not ``_unc_host``) so T2 can import it without tripping ruff PLC2701.
    """
    if not native_path:
        return None
    if not (native_path.startswith("\\\\") or native_path.startswith("//")):
        return None
    rest = native_path.lstrip("\\/")
    if not rest:
        return None
    # Normalise separators then take the first segment as the host.
    host = rest.replace("\\", "/").split("/", 1)[0]
    if not host:
        return None
    return "\\\\" + host


def disk_label(native_path: str) -> str | None:
    """Map a native source path to its drive label, or None when it has none.

    ``D:`` style roots (either slash direction, either letter case) map to the
    upper-case letter plus a colon; ``/Volumes/<name>`` maps to ``<name>``.
    UNC paths and plain Linux mounts map to None (UNC keeps its own grouping
    through ``unc_host``; ``/mnt/...`` stays per-path).
    """
    if not native_path:
        return None
    head = native_path[0]
    if (
        ("A" <= head <= "Z" or "a" <= head <= "z")
        and len(native_path) >= 2
        and native_path[1] == ":"
        and (len(native_path) == 2 or native_path[2] in ("\\", "/"))
    ):
        return native_path[0].upper() + ":"
    if native_path.startswith("/Volumes/"):
        rest = native_path[len("/Volumes/"):]
        if rest:
            return rest.split("/", 1)[0]
    return None


def source_keys_and_prefixes(
    gallery_config: dict,
) -> tuple[list[str], list[str | None]]:
    """Return ``(keys, prefixes)`` for every gallery source, in config order.

    ``keys`` are the snapshot keys (``uri_to_fs_path(src.path)`` — the same
    call ``_probe_all`` uses when writing the snapshot). ``prefixes`` are the
    ``file_uri``-namespace match prefixes (``_canonical_source_prefix``); a
    source whose prefix cannot be built keeps its index with None (never a hit).
    """
    from core.readonly_source import _canonical_source_prefix  # shape copy of is_path_on_unreachable_source

    path_mappings = gallery_config.get("path_mappings", {})
    keys: list[str] = []
    prefixes: list[str | None] = []
    for src in iter_gallery_sources(gallery_config):
        keys.append(uri_to_fs_path(src.path))  # uri-no-reverse
        try:
            prefixes.append(_canonical_source_prefix(src.path, path_mappings))
        except ValueError:
            prefixes.append(None)
    return keys, prefixes


def owning_source_index(file_uri: str, prefixes: list[str | None]) -> int | None:
    """Return the index of the longest matching source prefix, or None on miss.

    Ties keep the smaller index (strict ``>`` on the running best length).
    """
    from core.path_utils import is_path_under_dir

    best_idx, best_len = None, -1
    for i, prefix in enumerate(prefixes):
        if prefix is not None and len(prefix) > best_len and is_path_under_dir(file_uri, prefix):
            best_idx, best_len = i, len(prefix)
    return best_idx


async def _probe_all() -> None:
    """Probe every gallery source; write a fresh snapshot. Clears ``_in_flight``."""
    global _snapshot, _snapshot_at, _in_flight

    try:
        try:
            config = await asyncio.to_thread(load_config)
            gallery = config.get("gallery", {}) if isinstance(config, dict) else {}
            sources = await asyncio.to_thread(iter_gallery_sources, gallery)
        except Exception:
            logger.warning("_probe_all: failed to load sources", exc_info=True)
            with _lock:
                _snapshot = {}
                _snapshot_at = _now()
            return

        if not sources:
            with _lock:
                _snapshot = {}
                _snapshot_at = _now()
            return

        host_memo: dict[str, str] = {}
        new_snapshot: dict[str, str] = {}
        for src in sources:
            native = uri_to_fs_path(src.path)  # uri-no-reverse
            try:
                status = await _probe_one(native, host_memo)
            except Exception:
                logger.warning(
                    "_probe_all: probe failed for %s", native, exc_info=True
                )
                status = "unknown"
            new_snapshot[native] = status

        with _lock:
            _snapshot = new_snapshot
            _snapshot_at = _now()
    finally:
        with _lock:
            _in_flight = False


async def _probe_one(native_path: str, host_memo: dict[str, str]) -> str:
    # Unexpected exceptions propagate to _probe_all's per-source handler,
    # which already logs (exc_info=True) and isolates this source to "unknown".
    host = unc_host(native_path)
    if host is not None:
        if host in host_memo:
            return host_memo[host]
        status = await _probe_tcp_with_retry(host)
        host_memo[host] = status
        return status
    return await _probe_exists_with_retry(native_path)


async def _probe_with_retry(probe, target: str) -> str:
    """CD-4 三態收斂（TCP 與 exists 兩條路共用同一套規則）。

    ``probe`` 回 ``False``=肯定 / ``True``=否定 / ``None``=unknown。
    肯定 → ``ok``；**unknown 不重試**（探測機構自己壞掉，再問一次也是猜）；
    否定 → 隔 1 秒再問一次，兩次都否定才是 ``unreachable``。

    🔴 **「非否定」不得寫成 ok**——``None`` 必須是獨立分支，否則
    ``gaierror`` 這類會被誤報成「這個位置是通的」（誤報比漏報更糟）。
    """
    for attempt in (1, 2):
        result = await probe(target)
        if isinstance(result, str):
            return result
        if result is None:
            return "unknown"
        if result is False:
            return "ok"
        if attempt == 1:
            await asyncio.sleep(_RETRY_SLEEP_S)
    return "unreachable"


async def _probe_tcp_with_retry(host: str) -> str:
    return await _probe_with_retry(_tcp_probe, host)


async def _tcp_probe(host: str) -> bool | None:
    """Return False=ok, True=negative, None=unknown.

    ``host`` may be ``\\\\name`` from ``unc_host``; connect uses the bare name.
    """
    connect_host = host.lstrip("\\/")
    try:
        sock = await asyncio.to_thread(
            socket.create_connection, (connect_host, 445), _TCP_TIMEOUT_S
        )
        with contextlib.suppress(Exception):
            sock.close()
        return False
    except (TimeoutError, ConnectionRefusedError):
        return True
    except OSError as exc:
        if getattr(exc, "errno", None) in _NEG_ERRNOS:
            return True
        # 預期內的「探測機構自己答不出來」（gaierror／權限等）→ unknown，不吵。
        return None
    except Exception:
        # 非 OSError 一律是意料外的（to_thread 的 executor 掛掉、我們自己寫錯）。
        # 仍然收斂成 unknown（不得誤報成 ok，見 _probe_with_retry），但**必須留痕**：
        # 否則「探測永久壞掉」與「這次剛好問不出來」在 debug.log 裡長得一模一樣。
        logger.warning("_tcp_probe: unexpected failure for %s", host, exc_info=True)
        return None


async def _probe_exists_with_retry(path: str) -> str:
    result = await _probe_with_retry(_exists_probe, path)
    return "no_permission" if result == "permission_denied" else result


def _scandir_probe(path: str) -> bool | str | None:
    """Return final probe semantics after opening the directory itself.

    PermissionError -> "permission_denied"; NotADirectoryError -> False
    (a file exists there: reachable, same as ``os.path.exists`` on main);
    FileNotFoundError and any other OSError (NAS down: WinError 64/1222/1231,
    EHOSTDOWN/EIO ...) -> True (missing), matching main's exists() behaviour.
    """
    try:
        with os.scandir(path):
            return False
    except PermissionError:
        return "permission_denied"
    except NotADirectoryError:
        return False
    except FileNotFoundError:
        return True
    except OSError:
        return True


async def _exists_probe(path: str) -> bool | str | None:
    """Return False=ok, True=missing, permission_denied, or None=unknown/pending.

    Per-path dedup via ``_pending_exists``: a timed-out ``exists`` keeps its
    future so the same path cannot enqueue a second worker thread.
    """
    with _lock:
        existing = _pending_exists.get(path)
        if existing is not None and not existing.done():
            return None
        if existing is not None and existing.done():
            _pending_exists.pop(path, None)

        future: asyncio.Future = asyncio.ensure_future(
            asyncio.to_thread(_scandir_probe, path)
        )
        _pending_exists[path] = future

    def _clear_if_done(fut: asyncio.Future, *, key: str = path) -> None:
        with _lock:
            cur = _pending_exists.get(key)
            if cur is fut:
                _pending_exists.pop(key, None)

    future.add_done_callback(_clear_if_done)

    try:
        try:
            result = await asyncio.wait_for(
                asyncio.shield(future), timeout=_EXISTS_WAIT_S
            )
        except asyncio.TimeoutError:
            # 預期內：碟沒回應。future 留在 _pending_exists 裡（去重），不吵。
            return None
        except Exception:
            # 與 _tcp_probe 對稱：非逾時一律是意料外的（executor 關閉中拒收等）。
            # 仍收斂成 unknown（不得誤報成 ok），但必須留痕，否則「探測永久壞掉」
            # 與「這次剛好問不出來」在 debug.log 裡分不出來。
            logger.warning("_exists_probe: unexpected failure for %s", path, exc_info=True)
            return None
        return result
    finally:
        with _lock:
            if future.done() and _pending_exists.get(path) is future:
                _pending_exists.pop(path, None)


def is_path_on_unreachable_source(file_uri: str, gallery_config: dict) -> bool:
    """Return True if file_uri belongs to a source currently marked unreachable.

    file_uri is already a caller-coerced file:/// URI. unknown / ok / missing
    keys never block (CD-4 invariant C). Sync-only: calls get_snapshot() only.
    """
    from core.path_utils import is_path_under_dir
    from core.readonly_source import _canonical_source_prefix  # shape copy of is_path_readonly

    snapshot = get_snapshot()
    # CD-8 healthy-path short-circuit: no unreachable → do not iterate sources.
    if not any(v in ("unreachable", "no_permission") for v in snapshot.values()):
        return False
    path_mappings = gallery_config.get("path_mappings", {})
    for src in iter_gallery_sources(gallery_config):
        native = uri_to_fs_path(src.path)  # uri-no-reverse
        if snapshot.get(native) not in ("unreachable", "no_permission"):
            continue
        prefix = _canonical_source_prefix(src.path, path_mappings)
        if is_path_under_dir(file_uri, prefix):
            return True
    return False
