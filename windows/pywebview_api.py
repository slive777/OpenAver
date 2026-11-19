"""
OpenAver PyWebView 共用 API 模組
供 launcher.py 和 standalone.py 共用
"""
import contextlib
import os
import sys
import json
import subprocess
import threading
import time
from urllib.parse import urlparse
import webview
import core.client_connect as client_connect
import core.client_settings as client_settings
import core.self_update as self_update
from core.version import VERSION
from core.path_translate import Mapped, PathMap, Uncovered, strip_wrapping_quotes, to_local, to_server
from core.path_utils import file_uri_to_server_path, uri_to_fs_path
from core.video_extensions import DEFAULT_VIDEO_EXTENSIONS
from core.logger import get_logger
from webview.dom import DOMEventHandler
from windows import clipboard

logger = get_logger(__name__)

# 支援的影片副檔名（from core.video_extensions Single Source of Truth）
VIDEO_EXTENSIONS = set(DEFAULT_VIDEO_EXTENSIONS)

# 全域 window 參考（由 launcher/standalone 設定）
_window = None


def set_window(w):
    """設定全域 window 參考"""
    global _window
    _window = w


def get_window():
    """取得全域 window 參考"""
    return _window


# 連不到伺服器時殼自帶的小頁（只組字串，檔案由離線小頁那張卡建立）
OFFLINE_PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "offline", "offline.html")
_OFFLINE_HOSTS = ("127.0.0.1", "localhost")

# bridge 方法 → 允許呼叫的頁面種類（唯一對照表；沒登記的方法一律拒絕）
_SCOPE = {
    "select_files": "server",
    "select_folder": "server",
    "select_folder_path": "server",
    "open_file": "server",
    "open_folder": "server",
    "open_url": "server",
    "on_drop": "server",
    "connect_get_state": "server",
    "connect_probe": "server",
    "connect_login": "server",
    "connect_sources": "server",
    "connect_test_row": "server",
    "connect_save_path_map": "server",
    "connect_apply_restart": "server",
    "connect_switch_local_restart": "server",
    "connect_show_offline": "server",
    "copy_text": "server",
    "offline_get_state": "offline",
    "offline_retry": "offline",
    "offline_save_url": "offline",
    "offline_login": "offline",
    "offline_switch_local_restart": "offline",
    "local_settings_get": "server",
    "local_settings_save": "server",
    "update_check": "server",
    "update_context": "server",
    "update_run": "server",
    "cf_retry": "server",
    "startup_get_state": "startup",
    "startup_open_log_folder": "startup",
    "startup_quit": "startup",
}

# 導航空窗複查只在能讀到原生 URL 的平台啟用（其餘維持 168a 現狀）
_NATIVE_RECHECK_PLATFORMS = ("win32", "darwin")
# 頁面可寫的「這台電腦」設定鍵（其餘鍵由殼自己的流程寫）
_PAGE_KEYS = frozenset({"player", "close_action", "auto_check_update"})

_COPY_MAX_BYTES = 64 * 1024
_ROW_TEST_TIMEOUT = 5.0
STARTUP_QUIT_DELAY = 0.3

# 連線頁暫存：登入成功拿到的 token 只留在這裡（Python 端），不回傳頁面
_draft = {"origin": None, "token": None}
_restart_handler = None
_offline_text_provider = None
_cf_status_provider = None
_cf_retry_handler = None
_startup_state_provider = None
_startup_log_opener = None
_startup_quit_handler = None
_loaded_hook = None
_row_busy = threading.Lock()
_write_lock = threading.Lock()  # client.json 讀改寫的序列化（網路 I/O 不得在鎖內）


def set_restart_handler(fn):
    """T5 接線時註冊「重新啟動」處理器；未註冊時所有會重啟的方法在寫檔前就拒絕"""
    global _restart_handler
    _restart_handler = fn


def set_offline_text_provider(fn):
    """註冊小頁文案提供者 fn(reason, host_port) -> dict"""
    global _offline_text_provider
    _offline_text_provider = fn


def set_cf_status_provider(fn):
    """註冊 CF 殼狀態提供者 fn() -> dict（只讀狀態，不得動視窗；未註冊＝連線頁的 cf 為 None）"""
    global _cf_status_provider
    _cf_status_provider = fn


def set_cf_retry_handler(fn):
    """註冊「CF 驗證視窗重試」處理器 fn() -> {ok, cf}（168e-T13；未註冊＝cf_retry 回 unavailable）"""
    global _cf_retry_handler
    _cf_retry_handler = fn


def set_startup_state_provider(fn):
    """註冊啟動頁狀態提供者 fn() -> dict（203-T6；未註冊＝startup_get_state 回空 dict）"""
    global _startup_state_provider
    _startup_state_provider = fn


def set_startup_log_opener(fn):
    """註冊「開 log 資料夾」處理器 fn()（203-T6；未註冊＝unavailable）"""
    global _startup_log_opener
    _startup_log_opener = fn


def set_startup_quit_handler(fn):
    """註冊啟動頁的結束處理器 fn()（203-T6；未註冊＝延遲後銷毀所有視窗）"""
    global _startup_quit_handler
    _startup_quit_handler = fn


def set_loaded_hook(fn):
    """註冊「頁面載入完成」鉤子 fn(kind, window, gen)；None＝取消"""
    global _loaded_hook
    _loaded_hook = fn


def _request_restart():
    """呼叫已註冊的重啟處理器；未註冊或處理器失敗回 False"""
    if _restart_handler is None:
        return False
    try:
        _restart_handler()
    except Exception as e:
        logger.warning(f"[pywebview] restart handler failed ({type(e).__name__})")
        return False
    return True


def _stat_path(path):
    """薄包裝 os.stat（測試接縫）"""
    return os.stat(path)


def _untrusted():
    return {"ok": False, "reason": "untrusted"}


def _done():
    return dict(ok=True, reason=None)


def _failed(reason):
    return {"ok": False, "reason": reason}


def _not_client():
    """非連線模式回拒絕 dict，否則 None"""
    if client_settings.mode() != "client":
        return _failed("not_client")
    return None


def _snapshot_unchanged(url, token):
    """阻塞期間設定沒被改：已存網址與 token 仍等於擷取時的快照"""
    return client_settings.server_pair() == (url, token)


def _origin_unchanged(origin):
    return client_settings.canonical_server_url(client_settings.server_url()) == origin


def _store_login_token(origin, token):
    """比對 origin 與寫回在同一把鎖內完成；origin 已不是目前網址就不寫"""
    with _write_lock:  # login 回寫
        if not _origin_unchanged(origin):
            return False
        client_settings.apply_connection(origin, token or "", None)
    return True


def _compat_dict(compat):
    return {"status": compat.status, "hint": compat.hint}


def _token_for(origin):
    """該 origin 要帶的 token：同 origin 的 draft 優先，其次 url 等於 client.json 現存網址時用已存 token"""
    if origin is None:
        return None
    if _draft["origin"] == origin:
        return _draft["token"]
    stored_url, stored_token = client_settings.server_pair()
    if client_settings.canonical_server_url(stored_url) == origin:
        return stored_token or None
    return None


def _clear_draft():
    _draft["origin"] = None
    _draft["token"] = None


def _public_probe(p, origin):
    """probe 結果 → 頁面可見形狀（不含任何憑證）"""
    return {"ok": p["ok"], "reason": p["reason"], "version": p["version"], "kind": p["kind"],
            "auth_required": p["auth_required"], "authed": p["authed"],
            "compat": _compat_dict(p["compat"]), "url": origin or ""}


def _login_draft(origin, pin):
    """登入並把 token 暫存在 Python 端；只回 ok／reason"""
    reply = client_connect.login(origin, pin)
    if not reply["ok"]:
        return _failed(reply["reason"])
    _draft["origin"] = origin
    _draft["token"] = reply["token"]
    return {"ok": True, "reason": None}


def _clean_rules(rules):
    """對照表 → 只留兩欄皆非空字串的列；非 list 回 None（＝不動既有對照表）"""
    if not isinstance(rules, list):
        return None
    return [{"server": r["server"], "local": strip_wrapping_quotes(r["local"])} for r in rules
            if isinstance(r, dict) and isinstance(r.get("server"), str) and isinstance(r.get("local"), str)
            and r["server"].strip() and strip_wrapping_quotes(r["local"])]


def _apply_check(url):
    """套用前置檢查：回 (canonical, token, 拒絕 reason 或 None)"""
    canonical = client_settings.canonical_server_url(url)
    if canonical is None:
        return None, None, "invalid_url"
    token = _token_for(canonical)
    p = client_connect.probe(canonical, token)
    if not p["ok"]:
        return canonical, token, p["reason"] or "incompatible"
    if not client_connect.is_connectable(p["compat"]):
        return canonical, token, "incompatible"
    if p["auth_required"] and not p["authed"]:
        return canonical, token, "need_login"
    return canonical, token, None


def _apply_and_restart(url, path_map):
    canonical, token, refused = _apply_check(url)
    if refused:
        return _failed(refused)
    if _restart_handler is None:
        return _failed("restart_unavailable")
    try:
        with _write_lock:
            client_settings.apply_connection(canonical, token or "", _clean_rules(path_map))
    except (OSError, ValueError) as e:
        logger.warning(f"[pywebview] apply_connection failed ({type(e).__name__})")
        return _failed("write_failed")
    _clear_draft()
    return _done() if _request_restart() else _failed("restart_unavailable")


def _switch_local():
    """切回本機並重啟（連線頁與離線小頁共用）"""
    if _restart_handler is None:
        return _failed("restart_unavailable")
    with _write_lock:
        client_settings.clear_connection()
    return _done() if _request_restart() else _failed("restart_unavailable")


def _stat_worker(path, box, done):
    try:
        _stat_path(path)
        box.append("ok")
    except Exception as e:
        if not isinstance(e, OSError):
            logger.warning(f"[pywebview] row stat failed ({type(e).__name__})")
        box.append("not_found")
    finally:
        done.set()
        _row_busy.release()


def _stat_state(local_path):
    """在 daemon thread 探測本機路徑；逾時只是不等（thread 不取消、結果丟棄）；同時至多一個在飛"""
    if not _row_busy.acquire(blocking=False):
        return {"state": "timeout"}
    box, done = [], threading.Event()
    try:
        threading.Thread(target=_stat_worker, args=(local_path, box, done), daemon=True).start()
    except Exception as e:
        logger.warning(f"[pywebview] row stat thread start failed ({type(e).__name__})")
        _row_busy.release()
        return {"state": "timeout"}
    if not done.wait(_ROW_TEST_TIMEOUT):
        return {"state": "timeout"}
    if box[0] == "not_found":
        return {"state": "not_found", "local_path": local_path}
    return {"state": "ok"}


def _row_state(server_prefix, local_prefix, sample):
    if not (isinstance(local_prefix, str) and local_prefix.strip()):
        return {"state": "empty"}
    if not isinstance(sample, str):
        return {"state": "no_sample"}
    translated = to_local(sample, PathMap.from_rules([{"server": server_prefix, "local": local_prefix}]))
    if isinstance(translated, Uncovered):
        return {"state": "uncovered"}
    return _stat_state(translated.path)


def _is_offline_landing(js_raw, native_raw):
    """JS 與原生 URL 的原字串都指向本機 /offline.html 且 origin 一致才回 True"""
    js_origin = client_settings.normalize_origin(js_raw)
    native_origin = client_settings.normalize_origin(native_raw)
    if js_origin is None or js_origin != native_origin:
        return False
    try:
        parsed = urlparse(native_raw.strip())
    except ValueError:
        return False
    if parsed.hostname not in _OFFLINE_HOSTS:
        return False
    return parsed.path.endswith("/offline.html")


def _landing_key(url):
    """URL → (origin, path)；非字串或解析不出 origin 回 None（fail-closed）"""
    if not isinstance(url, str):
        return None
    origin = client_settings.normalize_origin(url)
    if origin is None:
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    return origin, parsed.path


def _is_startup_landing(js_raw, native_raw, real_url):
    """JS 與原生 URL 同 origin、都在 loopback /startup.html，且與本次 real_url 的（origin，路徑）逐字相等"""
    js_origin = client_settings.normalize_origin(js_raw)
    native_origin = client_settings.normalize_origin(native_raw)
    if js_origin is None or js_origin != native_origin:
        return False
    try:
        parsed = urlparse(native_raw.strip())
    except ValueError:
        return False
    if parsed.hostname not in _OFFLINE_HOSTS:
        return False
    if not parsed.path.endswith("/startup.html"):
        return False
    key = _landing_key(native_raw)
    return key is not None and key == _landing_key(real_url)


def _startup_quit_later():
    """延遲後結束 App：已註冊 quit handler 交給它，否則逐一銷毀所有視窗（各自吞例外）"""
    time.sleep(STARTUP_QUIT_DELAY)
    if _startup_quit_handler is not None:
        try:
            _startup_quit_handler()
        except Exception as e:
            logger.warning(f"[pywebview] startup quit handler failed ({type(e).__name__})")
        return
    for w in list(webview.windows):
        with contextlib.suppress(Exception):
            w.destroy()


def is_video_file(filename, extensions=None):
    """檢查是否為影片檔案

    Args:
        filename: 檔案名稱
        extensions: 可選的副檔名集合，未提供時使用模組級 VIDEO_EXTENSIONS 預設值
    """
    ext = os.path.splitext(filename)[1].lower()
    if extensions is not None:
        return ext in extensions
    return ext in VIDEO_EXTENSIONS


def _path_map():
    """每次呼叫現建（不快取：設定改了立刻生效）"""
    return PathMap.from_rules(client_settings.path_map())


def bridge_resolve(value):
    """伺服器端路徑／URI → 這台電腦的本機路徑。

    本機模式＝uri_to_fs_path；client 模式查對照表，不在表內回 Uncovered()（絕不回原字串）。
    """
    if client_settings.mode() != 'client':
        return uri_to_fs_path(value)  # uri-no-reverse: windows native runtime, path_mappings N/A
    translated = to_local(file_uri_to_server_path(value), _path_map())
    return translated.path if isinstance(translated, Mapped) else translated


def bridge_unresolve(local_path):
    """這台電腦的本機路徑 → 伺服器端路徑；本機模式恆等，client 模式不在表內回 Uncovered()。"""
    if client_settings.mode() != 'client':
        return local_path
    found = to_server(local_path, _path_map())
    return found.path if isinstance(found, Mapped) else found


def _result(ok, reason, local_path, server_path):
    return {"ok": ok, "reason": reason, "local_path": local_path, "server_path": server_path}


def _refuse(method, reason, server_path, local_path):
    """拒絕結果＋固定形狀 WARNING（f-string 預先格式化）"""
    logger.warning(f"[pywebview] {method} refused reason={reason} server={server_path!r} local={local_path!r}")
    return _result(False, reason, local_path, server_path)


def _resolve_forward(method, path):
    """正向翻譯：回 (local_path, server_path, 拒絕結果或 None)；uncovered 即止、不碰檔案系統"""
    server_path = file_uri_to_server_path(path)
    local_path = bridge_resolve(path)
    if isinstance(local_path, Uncovered):
        return None, server_path, _refuse(method, "uncovered", server_path, None)
    return local_path, server_path, None


def _is_video_path(local_path):
    return os.path.splitext(local_path)[1].lower() in client_settings.video_extensions()


def _split_reverse(local_paths):
    """本機路徑逐個翻成伺服器路徑；回 (已翻譯清單, 未涵蓋的本機路徑清單)"""
    kept, uncovered = [], []
    for local_path in local_paths:
        server = bridge_unresolve(local_path)
        if isinstance(server, Uncovered):
            uncovered.append(local_path)
        else:
            kept.append(server)
    return kept, uncovered


def _merge_uncovered_kind(kinds):
    """被擋清單出現過的種類集合 → 'file'／'folder'；兩種都有（或空）→ 'any'"""
    return 'any' if len(kinds) != 1 else next(iter(kinds))


def _notify_uncovered(method, paths, kind):
    """每次出口呼叫最多通知一次：保序去重，每個路徑一行 WARNING；kind ∈ file／folder／any"""
    unique = list(dict.fromkeys(paths))
    if not unique:
        return
    for local_path in unique:
        logger.warning(f"[pywebview] {method} refused reason=uncovered server=None local={local_path!r}")
    window = get_window()
    if window is not None:
        paths_json = json.dumps(unique)
        window.evaluate_js(f'if(typeof handleBridgeUncovered === "function") handleBridgeUncovered({paths_json}, {json.dumps(kind)})')


class Api:
    """供前端 JS 調用的 Python API（信任閘：依落地頁面種類放行，預設 fail-closed）"""

    def __init__(self):
        self._page_kind = None  # None / "server" / "offline" / "startup"
        self._trusted_origin = None
        self._nav_gen = 0
        self._seen_origin = None
        self._offline_expected = False
        self._offline_landing = None
        self._startup_expected = False
        self._startup_landing = None
        self._offline_state = None

    def _get_trusted(self):
        """相容屬性 getter：目前頁面是否為伺服器頁"""
        return self._page_kind == "server"

    def _put_trusted(self, value):
        """相容屬性 setter：真 → server、假 → None"""
        self._page_kind = "server" if value else None

    _trusted = property(_get_trusted, _put_trusted)

    def _set_trusted_origin(self, origin):
        """設定唯一信任的 origin（尾斜線不計）。底線開頭：pywebview 不會把它注入頁面"""
        self._trusted_origin = client_settings.normalize_origin(str(origin)) or str(origin).rstrip("/")

    def _denied(self, method):
        """頁面種類不符該方法的範圍：記一行 WARNING 並回 True"""
        scope = _SCOPE.get(method)
        reason = "untrusted"
        if scope is not None and scope == self._page_kind:
            if sys.platform not in _NATIVE_RECHECK_PLATFORMS:
                return False
            native = self._native_origin()
            if native is not None and native == self._seen_origin and self._landing_intact(scope):
                return False
            reason = "navigating"
        origin = None if self._seen_origin is None else str(self._seen_origin)[:128]
        logger.warning(f"[pywebview] {method} refused reason={reason} origin={origin!r}")
        return True

    def _landing_intact(self, scope):
        """offline／startup 小頁 scope：原生 URL 的（origin，路徑）仍等於分類時記下的鍵"""
        if scope == "offline":
            recorded = self._offline_landing
        elif scope == "startup":
            recorded = self._startup_landing
        else:
            return True
        if recorded is None:
            return False
        return _landing_key(self._native_raw()) == recorded

    @staticmethod
    def _native_raw():
        """此刻原生視窗的 URL 原字串；讀不到或任何例外回 None"""
        try:
            return get_window().get_current_url()
        except Exception:
            return None

    @staticmethod
    def _real_url():
        """殼決定的內建伺服器落地網址；讀不到或任何例外回 None（fail-closed）"""
        try:
            return get_window().real_url
        except Exception:
            return None

    @staticmethod
    def _native_origin():
        """此刻原生視窗的 origin；讀不到或任何例外回 None（只信 get_current_url）"""
        try:
            return client_settings.normalize_origin(get_window().get_current_url())
        except Exception:
            return None

    def _expect_offline(self):
        """殼即將載入離線小頁：下一次通過世代守衛的驗證才可把本機 /offline.html 判成小頁"""
        self._offline_expected = True

    def _expect_startup(self):
        """殼即將載入本機啟動畫面：下一次通過世代守衛的驗證才可判成 startup"""
        self._startup_expected = True

    def _set_offline_state(self, reason, failed_url):
        """離線狀態容器：網址只存規範化後的 scheme://host[:port]（不含票證）"""
        failed = client_settings.canonical_server_url(failed_url) or ""
        self._offline_state = {
            "reason": reason,
            "failed_url": failed,
            "host_port": client_settings.display_host(failed, with_port=True),
        }

    def _show_offline(self, reason):
        """把視窗換成離線小頁"""
        self._set_offline_state(reason, self._trusted_origin)
        self._expect_offline()
        get_window().load_url(OFFLINE_PAGE)

    def _on_before_load(self):
        """每次導航注入前：世代遞增並立即撤銷頁面種類"""
        self._nav_gen += 1
        self._page_kind = None  # before_load reset (I7)

    def _on_loaded(self):
        """頁面載入後：讀實際落地 origin 判定頁面種類；只有伺服器頁才綁 drop"""
        gen = self._nav_gen
        window = get_window()
        js_raw, native_raw, ok = self._read_origins(window)
        if gen != self._nav_gen:
            return
        expected, self._offline_expected = self._offline_expected, False
        startup_expected, self._startup_expected = self._startup_expected, False
        origin = self._agreed_origin(js_raw, native_raw) if ok else None
        self._seen_origin = origin
        self._page_kind = self._classify(origin, js_raw, native_raw, expected, startup_expected)
        if self._page_kind == "server":
            window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
        elif self._page_kind is None:
            self._on_nav_failure(js_raw, native_raw)
        if self._page_kind is not None and gen == self._nav_gen:
            self._signal_bridge_ready(window, self._page_kind)
            if gen == self._nav_gen and self._page_kind is not None:  # 通知期間可能又開始新導航
                self._notify_loaded_hook(self._page_kind, window, gen)

    @staticmethod
    def _notify_loaded_hook(kind, window, gen):
        """通知已註冊的載入完成鉤子；鉤子例外只記型別名、不外丟"""
        if _loaded_hook is None:
            return
        try:
            _loaded_hook(kind, window, gen)
        except Exception as e:
            logger.warning(f"[pywebview] loaded hook failed ({type(e).__name__})")

    @staticmethod
    def _signal_bridge_ready(window, kind):
        """頁面種類已定後通知頁面可以呼叫 bridge（只帶 kind 字串，不帶網址／票證）"""
        try:
            window.evaluate_js(
                f"window.__oaBridgeKind = {json.dumps(kind)}; window.dispatchEvent(new Event('oabridgeready'))"
            )
        except Exception as e:
            logger.warning(f"[pywebview] bridge ready signal failed ({type(e).__name__})")

    @staticmethod
    def _read_origins(window):
        """回 (JS 原字串, 原生 URL 原字串, 是否讀成功)；任何例外 fail-closed"""
        if window is None:
            return None, None, False
        try:
            return window.evaluate_js("location.origin"), window.get_current_url(), True
        except Exception as e:
            logger.warning(f"[pywebview] origin check failed ({type(e).__name__}); treated as untrusted")
            return None, None, False

    @staticmethod
    def _agreed_origin(js_raw, native_raw):
        """兩個來源正規化後一致才回 origin；否則 None"""
        js_origin = client_settings.normalize_origin(js_raw)
        native_origin = client_settings.normalize_origin(native_raw)
        if native_origin is None or native_origin != js_origin:
            logger.warning("[pywebview] origin sources disagree or missing; treated as untrusted")
            return None
        return js_origin

    def _classify(self, origin, js_raw, native_raw, offline_expected, startup_expected):
        """伺服器頁優先；其次（等待中或同一小頁重整）的本機啟動頁／離線小頁；其餘 None"""
        if origin is not None and origin == self._trusted_origin:
            return "server"
        key = _landing_key(native_raw)
        startup_remembered = self._startup_landing is not None and key == self._startup_landing
        if (startup_expected or startup_remembered) and _is_startup_landing(js_raw, native_raw, self._real_url()):
            self._startup_landing = key
            return "startup"
        offline_remembered = self._offline_landing is not None and key == self._offline_landing
        if (offline_expected or offline_remembered) and _is_offline_landing(js_raw, native_raw):
            self._offline_landing = key
            return "offline"
        return None

    def _on_nav_failure(self, js_raw, native_raw):
        """信任伺服器的導航失敗（錯誤頁簽名：chrome-error:// 或 WebView2 的 "null"，且原生網址在伺服器 origin）且為連線模式 → 換成離線小頁"""
        if not (isinstance(js_raw, str) and (js_raw == "null" or js_raw.startswith("chrome-error://"))):
            return
        native_origin = client_settings.normalize_origin(native_raw)
        if native_origin is None or native_origin != self._trusted_origin:
            return
        if client_settings.mode() != "client":
            return
        logger.warning(f"[pywebview] server unreachable host={client_settings.display_host(native_origin, with_port=True)}")
        self._show_offline("unreachable")

    def select_files(self):
        """
        開啟檔案選擇對話框，選取影片檔案
        Returns: 選取的檔案路徑陣列（已翻譯成伺服器路徑；未涵蓋者不回傳，改發通知）
        """
        if self._denied("select_files"):
            return []
        window = get_window()
        exts = client_settings.video_extensions()
        ext_filter = ';'.join(f'*{ext}' for ext in sorted(exts))
        file_types = (f'影片檔案 ({ext_filter})',
                      '所有檔案 (*.*)')
        result = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=file_types
        )
        if not result:
            return []
        kept, uncovered = _split_reverse(list(result))
        _notify_uncovered('select_files', uncovered, 'file')
        return kept

    def select_folder(self):
        """
        開啟資料夾選擇對話框，返回資料夾路徑和內部影片檔案
        Returns: { folder: 資料夾路徑, files: 影片檔案陣列 }（伺服器路徑）；資料夾未涵蓋回 None
        """
        if self._denied("select_folder"):
            return None
        window = get_window()
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if not (result and len(result) > 0):
            return None
        folder_path = result[0]
        folder_kept, uncovered = _split_reverse([folder_path])
        if not folder_kept:
            _notify_uncovered('select_folder', uncovered, 'folder')
            return None
        exts = client_settings.video_extensions()
        local_files = []
        for f in os.listdir(folder_path):
            file_path = os.path.join(folder_path, f)
            if os.path.isfile(file_path) and is_video_file(f, exts):
                local_files.append(file_path)
        files, uncovered_files = _split_reverse(local_files)
        _notify_uncovered('select_folder', uncovered_files, 'file')
        return {"folder": folder_kept[0], "files": files}

    def select_folder_path(self):
        """開啟資料夾選擇對話框，只返回資料夾路徑（伺服器路徑；未涵蓋回 None）"""
        if self._denied("select_folder_path"):
            return None
        window = get_window()
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if not (result and len(result) > 0):
            return None
        kept, uncovered = _split_reverse([result[0]])
        _notify_uncovered('select_folder_path', uncovered, 'folder')
        return kept[0] if kept else None

    def open_file(self, path):
        """用系統預設程式或指定播放器開啟檔案

        支援格式：
        - file:///C:/path/to/file.mp4
        - C:/path/to/file.mp4
        - C:\\path\\to\\file.mp4

        Returns: {"ok", "reason", "local_path", "server_path"}；
        reason ∈ None / uncovered / not_video / not_found / failed
        """
        if self._denied("open_file"):
            return {"ok": False, "reason": "untrusted", "local_path": None, "server_path": None}
        local_path, server_path, refused = _resolve_forward('open_file', path)
        if refused:
            return refused

        if not _is_video_path(local_path):
            return _refuse('open_file', 'not_video', server_path, local_path)

        if not os.path.exists(local_path):
            return _refuse('open_file', 'not_found', server_path, local_path)

        # 讀取設定，檢查是否有指定播放器
        player = client_settings.player_path()

        if player and os.path.exists(player):
            try:
                subprocess.Popen([player, local_path])
                return _result(True, None, local_path, server_path)
            except Exception as e:
                logger.warning(f"[pywebview] custom player failed for {local_path!r} (player={player!r}): {e}; falling back to OS default")
                pass  # fallback 到系統預設

        # 跨平台開啟檔案
        try:
            if sys.platform == 'win32':
                os.startfile(local_path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', local_path])
            else:
                subprocess.run(['xdg-open', local_path])
            return _result(True, None, local_path, server_path)
        except Exception as e:
            logger.error(f"[pywebview] open_file failed for {local_path!r}: {e}")
            return _result(False, 'failed', local_path, server_path)

    def open_url(self, url: str) -> bool:
        """用系統預設瀏覽器開啟 URL

        僅接受 http:// 或 https:// 開頭的 URL，其他 scheme 一律拒絕。
        任何例外均捕捉並回傳 False，不讓異常傳播。

        Args:
            url: 要開啟的 URL 字串

        Returns:
            True 表示成功呼叫系統 API，False 表示驗證失敗或系統呼叫拋出例外
        """
        if self._denied("open_url"):
            return False
        if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
            return False
        try:
            if sys.platform == 'win32':
                os.startfile(url)
                return True
            elif sys.platform == 'darwin':
                result = subprocess.run(['open', url])
                return result.returncode == 0
            else:
                result = subprocess.run(['xdg-open', url])
                return result.returncode == 0
        except Exception as e:
            logger.error(f"[pywebview] open_url failed for {url!r}: {e}")
            return False

    def open_folder(self, path):
        """用系統檔案管理員開啟檔案所在資料夾

        支援格式同 open_file()：
        - file:///C:/path/to/file.mp4
        - C:/path/to/file.mp4
        - C:\\path\\to\\file.mp4

        Windows: explorer /select, → 打開資料夾並選中檔案
        macOS:   open -R          → Finder 中顯示檔案
        Linux:   xdg-open         → 打開所在資料夾

        Returns: 同 open_file()（無 not_video）；local_path 永遠報原路徑不報父層
        """
        if self._denied("open_folder"):
            return {"ok": False, "reason": "untrusted", "local_path": None, "server_path": None}
        local_path, server_path, refused = _resolve_forward('open_folder', path)
        if refused:
            return refused

        target = local_path
        if not os.path.exists(target):
            # 檔案不存在，嘗試開啟父資料夾
            parent = os.path.dirname(target)
            if not os.path.exists(parent):
                return _refuse('open_folder', 'not_found', server_path, local_path)
            target = parent

        try:
            if sys.platform == 'win32':
                # /select, 會打開資料夾並選中該檔案
                subprocess.Popen(['explorer', '/select,', target])
                ok = True
            elif sys.platform == 'darwin':
                # -R 會在 Finder 中顯示並選中該檔案
                ok = subprocess.run(['open', '-R', target]).returncode == 0
            else:
                # Linux: 開啟所在資料夾
                folder = os.path.dirname(target) if os.path.isfile(target) else target
                ok = subprocess.run(['xdg-open', folder]).returncode == 0
        except Exception as e:
            logger.error(f"[pywebview] open_folder failed for {target!r}: {e}")
            ok = False
        return _result(ok, None if ok else 'failed', local_path, server_path)

    # --- 168b：連線頁（伺服器頁）---

    def connect_get_state(self):
        """連線頁初始狀態；只回 has_token 布林，不回 token"""
        if self._denied("connect_get_state"):
            return _untrusted()
        url = client_settings.server_url()
        return {"mode": client_settings.mode(), "url": url,
                "host": client_settings.display_host(url, with_port=True),
                "has_token": bool(client_settings.server_token()),
                "path_map": client_settings.saved_path_map(), "version": client_connect.LOCAL_VERSION,
                "last_ok": client_settings.server_last_ok(), "cf": self._cf_status()}

    def cf_retry(self):
        """連線頁「重試」：交給殼端控制器補建／重讀 CF 驗證視窗；回 {ok, cf}（同 connect_get_state 的 cf 形）"""
        if self._denied("cf_retry"):
            return _untrusted()
        if _cf_retry_handler is None:
            return _failed("unavailable")
        try:
            reply = _cf_retry_handler()
        except Exception as e:
            logger.warning(f"[pywebview] cf retry handler failed ({type(e).__name__})")
            return _failed("failed")
        return reply if isinstance(reply, dict) else _failed("failed")

    @staticmethod
    def _cf_status():
        if _cf_status_provider is None:
            return None
        try:
            status = _cf_status_provider()
        except Exception as e:
            logger.warning(f"[pywebview] cf status provider failed ({type(e).__name__})")
            return None
        return status if isinstance(status, dict) else None

    def connect_probe(self, url):
        """探測伺服器（握手）；換不同 origin 時清掉暫存的登入"""
        if self._denied("connect_probe"):
            return _untrusted()
        origin = client_settings.canonical_server_url(url)
        if origin != _draft["origin"]:
            _clear_draft()
        p = client_connect.probe(origin or url, _token_for(origin))
        return _public_probe(p, origin)

    def connect_login(self, url, pin):
        """用密碼換 token；token 只存在 Python 端暫存"""
        if self._denied("connect_login"):
            return _untrusted()
        origin = client_settings.canonical_server_url(url)
        if origin is None:
            return _failed("invalid_url")
        return _login_draft(origin, pin)

    def connect_sources(self, url):
        """取伺服器的掃描來源清單（對照表用）"""
        if self._denied("connect_sources"):
            return _untrusted()
        origin = client_settings.canonical_server_url(url)
        reply = client_connect.fetch_sources(origin or url, _token_for(origin))
        return {"ok": reply["ok"], "reason": reply["reason"], "sources": reply["sources"]}

    def connect_test_row(self, server_prefix, local_prefix, sample):
        """對照表單列測試：empty／no_sample／uncovered／ok／not_found／timeout"""
        if self._denied("connect_test_row"):
            return _untrusted()
        return _row_state(server_prefix, local_prefix, sample)

    def connect_save_path_map(self, rules):
        """只存兩欄皆非空的列（連線模式才存）"""
        if self._denied("connect_save_path_map"):
            return _untrusted()
        refused = _not_client()
        if refused:
            return refused
        if not isinstance(rules, list):
            return _failed("invalid_rules")
        with _write_lock:
            client_settings.save_path_map(rules)
        return _done()

    def connect_apply_restart(self, url, path_map):
        """前置檢查全過才寫入連線設定並重新啟動"""
        if self._denied("connect_apply_restart"):
            return _untrusted()
        return _apply_and_restart(url, path_map)

    def connect_switch_local_restart(self):
        """切回本機模式並重新啟動"""
        if self._denied("connect_switch_local_restart"):
            return _untrusted()
        return _switch_local()

    def connect_show_offline(self, href=None):
        """側欄點擊在連線失敗時改顯示離線小頁；href 一律忽略"""
        if self._denied("connect_show_offline"):
            return _untrusted()
        if get_window() is None:
            return {"ok": False}
        self._show_offline("unreachable")
        return {"ok": True}

    def copy_text(self, text):
        """寫入剪貼簿（UTF-8 上限 64 KiB）"""
        if self._denied("copy_text"):
            return _untrusted()
        if not isinstance(text, str):
            return {"ok": False}
        try:
            size = len(text.encode("utf-8"))
        except UnicodeEncodeError:
            return {"ok": False}
        if size > _COPY_MAX_BYTES:
            return {"ok": False}
        return {"ok": bool(clipboard.copy_text(text))}

    # --- 168c：這台電腦的設定與更新（client 模式的伺服器頁）---

    def local_settings_get(self):
        """這台電腦的設定（播放器、關閉行為、自動檢查更新）"""
        if self._denied("local_settings_get"):
            return _untrusted()
        refused = _not_client()
        if refused:
            return refused
        return {"ok": True, "player": client_settings.player_path(),
                "close_action": client_settings.close_action(),
                "auto_check_update": client_settings.auto_check_update()}

    def local_settings_save(self, patch):
        """只收頁面可寫的鍵；其餘鍵整份拒絕、不轉送"""
        if self._denied("local_settings_save"):
            return _untrusted()
        refused = _not_client()
        if refused:
            return refused
        if not isinstance(patch, dict):
            return _failed("bad_value")
        if any(k not in _PAGE_KEYS for k in patch):
            return _failed("bad_key")
        try:
            reply = client_settings.update_local_settings(patch)
        except OSError:
            return _failed("write_failed")
        return _done() if reply["ok"] else _failed(reply["reason"])

    def update_check(self):
        """查 GitHub 最新版；current_version 是這台電腦的版本"""
        if self._denied("update_check"):
            return _untrusted()
        refused = _not_client()
        if refused:
            return refused
        reply = self_update.check_latest()
        if not reply.get("ok"):
            return _failed(reply.get("reason"))
        return {"ok": True, "reason": None, "has_update": bool(reply.get("has_update")),
                "current_version": VERSION, "latest_version": reply.get("latest_version") or "",
                "download_url": reply.get("download_url") or ""}

    def update_context(self):
        """更新卡需要的本機脈絡：是否預設安裝位置、目前版本"""
        if self._denied("update_context"):
            return _untrusted()
        refused = _not_client()
        if refused:
            return refused
        return {"ok": True, "is_default_path": self_update.is_default_install(), "current_version": VERSION}

    def update_run(self):
        """開外部終端機跑官方安裝腳本（不關窗、不重啟、不退出殼）"""
        if self._denied("update_run"):
            return _untrusted()
        refused = _not_client()
        if refused:
            return refused
        try:
            self_update.launch_installer()
        except Exception as e:
            logger.warning(f"[pywebview] update_run launch failed ({type(e).__name__})")
            return _failed("launch_failed")
        return _done()

    # --- 168b：離線小頁 ---

    def offline_get_state(self):
        """小頁初始狀態：原因、失敗網址（不含票證）、host:port、文案"""
        if self._denied("offline_get_state"):
            return _untrusted()
        state = self._offline_state or {}
        reason, host_port = state.get("reason"), state.get("host_port", "")
        return {"reason": reason, "failed_url": state.get("failed_url", ""),
                "host_port": host_port, "texts": self._offline_texts(reason, host_port)}

    @staticmethod
    def _offline_texts(reason, host_port):
        if _offline_text_provider is None:
            return {}
        try:
            texts = _offline_text_provider(reason, host_port)
        except Exception as e:
            logger.warning(f"[pywebview] offline text provider failed ({type(e).__name__})")
            return {}
        return texts if isinstance(texts, dict) else {}

    def offline_retry(self):
        """重新檢查已存的伺服器；通過就載入入口頁"""
        if self._denied("offline_retry"):
            return _untrusted()
        refused = _not_client()
        if refused:
            return refused
        with _write_lock:
            url, token = client_settings.server_pair()
        origin = client_settings.normalize_origin(url)
        pf = client_connect.preflight(url, token)
        if not _snapshot_unchanged(url, token):
            return _failed("changed")  # 檢查期間使用者改了目標：不導航、不覆寫離線狀態
        if pf.status != "ok":
            self._set_offline_state(pf.reason, url)
            return _failed(pf.reason)
        if origin is None:
            return _failed("invalid_url")
        if not self._commit_retry(url, token, origin):
            return _failed("changed")
        window = get_window()
        kind = client_settings.shell_kind()
        entry = client_settings.client_entry_url(origin, kind, token)  # 只用擷取快照，不重讀設定
        window.load_url(entry)
        window.set_title("OpenAver \u2014 " + client_settings.display_host(url))
        return {"ok": True}

    def _commit_retry(self, url, token, origin):
        """鎖內再比對一次快照，通過才記 last_ok 並信任該 origin"""
        with _write_lock:
            if not _snapshot_unchanged(url, token):
                return False
            client_settings.touch_last_ok()
            self._set_trusted_origin(origin)
        return True

    def offline_save_url(self, url):
        """只存新網址（不探測；驗證留給 retry）；同 origin 才保留舊 token"""
        if self._denied("offline_save_url"):
            return _untrusted()
        refused = _not_client()
        if refused:
            return refused
        canonical = client_settings.canonical_server_url(url)
        if canonical is None:
            return {**_failed("invalid_url"), "host_port": ""}
        with _write_lock:
            stored_url, stored_token = client_settings.server_pair()
            same = client_settings.canonical_server_url(stored_url) == canonical
            client_settings.apply_connection(canonical, stored_token if same else "", None)
            self._set_trusted_origin(canonical)
            reason = (self._offline_state or {}).get("reason") or "unreachable"
            self._set_offline_state(reason, canonical)
        return {"ok": True, "reason": None, "host_port": self._offline_state["host_port"]}

    def offline_login(self, pin):
        """用密碼登入已存的伺服器；成功就存 token（頁面接著呼叫 retry）"""
        if self._denied("offline_login"):
            return _untrusted()
        refused = _not_client()
        if refused:
            return refused
        if not isinstance(pin, str) or not pin.strip():
            return _failed("bad_pin")  # 空密碼不送伺服器（會被算一次失敗、全域計數）
        origin = client_settings.canonical_server_url(client_settings.server_url())
        if origin is None:
            return _failed("invalid_url")
        reply = client_connect.login(origin, pin)
        if not reply["ok"]:
            return _failed(reply["reason"])
        if not _store_login_token(origin, reply["token"]):
            return _failed("changed")  # 登入期間改存了別台：票證不寫給新主機
        return _done()

    def offline_switch_local_restart(self):
        """切回本機模式並重新啟動（小頁入口）"""
        if self._denied("offline_switch_local_restart"):
            return _untrusted()
        refused = _not_client()
        if refused:
            return refused
        return _switch_local()

    # --- 203-T6：啟動畫面（本機 startup 頁；沒有頁面可控參數）---

    def startup_get_state(self):
        """啟動頁初始狀態：provider 回 dict 原樣回；未註冊／例外／非 dict → 空 dict"""
        if self._denied("startup_get_state"):
            return _untrusted()
        if _startup_state_provider is None:
            return {}
        try:
            state = _startup_state_provider()
        except Exception as e:
            logger.warning(f"[pywebview] startup state provider failed ({type(e).__name__})")
            return {}
        return state if isinstance(state, dict) else {}

    def startup_open_log_folder(self):
        """開 log 資料夾；未註冊 → unavailable、拋例外 → failed"""
        if self._denied("startup_open_log_folder"):
            return _untrusted()
        if _startup_log_opener is None:
            return _failed("unavailable")
        try:
            _startup_log_opener()
        except Exception as e:
            logger.warning(f"[pywebview] startup log opener failed ({type(e).__name__})")
            return _failed("failed")
        return _done()

    def startup_quit(self):
        """結束 App：同步部分只啟動 daemon 緒並立即回 done，關窗延到背景（cocoa 不能在 bridge 執行緒關）"""
        if self._denied("startup_quit"):
            return _untrusted()
        threading.Thread(target=_startup_quit_later, daemon=True).start()
        return _done()



def on_drop(e):
    """處理拖放事件，取得完整路徑並傳給前端（支援多檔案和資料夾；路徑已翻譯成伺服器路徑）"""
    if api._denied("on_drop"):
        return
    window = get_window()

    files = e.get('dataTransfer', {}).get('files', [])
    if not files:
        return

    expanded_paths = []  # 影片檔案路徑（給 search 用）
    folder_paths = []    # 資料夾路徑（給 scanner 用）
    uncovered = []       # 未涵蓋的本機路徑（只通知，不推送）
    uncovered_kinds = set()  # 被擋清單出現過的種類（file／folder）

    exts = client_settings.video_extensions()

    for file_info in files:
        win_path = file_info.get('pywebviewFullPath', '')
        if not win_path:
            continue

        if os.path.isdir(win_path):
            folder_kept, folder_uncovered = _split_reverse([win_path])
            folder_paths.extend(folder_kept)
            uncovered.extend(folder_uncovered)
            if folder_uncovered:
                uncovered_kinds.add('folder')
            if not folder_kept:
                continue
            # 資料夾：展開第一層影片檔案（給 search 用）
            local_files = []
            for f in os.listdir(win_path):
                file_win_path = os.path.join(win_path, f)
                if os.path.isfile(file_win_path) and is_video_file(f, exts):
                    local_files.append(file_win_path)
            kept, file_uncovered = _split_reverse(local_files)
            expanded_paths.extend(kept)
            uncovered.extend(file_uncovered)
            if file_uncovered:
                uncovered_kinds.add('file')
        else:
            if not is_video_file(win_path, exts):
                continue
            kept, file_uncovered = _split_reverse([win_path])
            expanded_paths.extend(kept)
            uncovered.extend(file_uncovered)
            if file_uncovered:
                uncovered_kinds.add('file')

    # 傳送影片檔案路徑（search 頁面用）
    if expanded_paths:
        paths_json = json.dumps(expanded_paths)
        window.evaluate_js(f'if(typeof handlePyWebViewDrop === "function") handlePyWebViewDrop({paths_json})')

    # 傳送資料夾路徑（scanner 頁面用）
    if folder_paths:
        folders_json = json.dumps(folder_paths)
        window.evaluate_js(f'if(typeof handleFolderDrop === "function") handleFolderDrop({folders_json})')

    _notify_uncovered('on_drop', uncovered, _merge_uncovered_kind(uncovered_kinds))


def bind_events(w):
    """綁定導航事件（信任閘；信任頁載入後才綁 drop 事件）"""
    set_window(w)

    # 每次導航：before_load 撤銷信任（先於注入），loaded 驗證落地 origin
    w.events.before_load += api._on_before_load
    w.events.loaded += api._on_loaded


# 建立全域 api 實例
api = Api()


# --- 注入面：模組層包裝函式（窗口以 js_api=None＋window.expose 註冊，派送端只做精確名稱查表）---
# 包裝函式不可有 self（expose 依 getfullargspec 產 stub）；on_drop 是 DOM 事件不是 JS 呼叫，不在其中。

def open_file(path):
    return api.open_file(path)


def open_folder(path):
    return api.open_folder(path)


def open_url(url):
    return api.open_url(url)


def select_files():
    return api.select_files()


def select_folder():
    return api.select_folder()


def select_folder_path():
    return api.select_folder_path()


def connect_get_state():
    return api.connect_get_state()


def cf_retry():
    return api.cf_retry()


def connect_probe(url):
    return api.connect_probe(url)


def connect_login(url, pin):
    return api.connect_login(url, pin)


def connect_sources(url):
    return api.connect_sources(url)


def connect_test_row(server_prefix, local_prefix, sample):
    return api.connect_test_row(server_prefix, local_prefix, sample)


def connect_save_path_map(rules):
    return api.connect_save_path_map(rules)


def connect_apply_restart(url, path_map):
    return api.connect_apply_restart(url, path_map)


def connect_switch_local_restart():
    return api.connect_switch_local_restart()


def connect_show_offline(href=None):
    return api.connect_show_offline(href)


def copy_text(text):
    return api.copy_text(text)


def offline_get_state():
    return api.offline_get_state()


def offline_retry():
    return api.offline_retry()


def offline_save_url(url):
    return api.offline_save_url(url)


def offline_login(pin):
    return api.offline_login(pin)


def offline_switch_local_restart():
    return api.offline_switch_local_restart()


def startup_get_state():
    return api.startup_get_state()


def startup_open_log_folder():
    return api.startup_open_log_folder()


def startup_quit():
    return api.startup_quit()


def local_settings_get():
    return api.local_settings_get()


def local_settings_save(patch):
    return api.local_settings_save(patch)


def update_check():
    return api.update_check()


def update_context():
    return api.update_context()


def update_run():
    return api.update_run()


def exposed_functions():
    """給 window.expose(*...) 的 bridge 白名單"""
    return [open_file, open_folder, open_url, select_files, select_folder, select_folder_path,
            connect_get_state, cf_retry, connect_probe, connect_login, connect_sources, connect_test_row,
            connect_save_path_map, connect_apply_restart, connect_switch_local_restart,
            connect_show_offline, copy_text, offline_get_state, offline_retry, offline_save_url,
            offline_login, offline_switch_local_restart,
            startup_get_state, startup_open_log_folder, startup_quit,
            local_settings_get, local_settings_save, update_check, update_context, update_run]
