"""core/client_settings.py — 「這台電腦的設定」的家（桌面殼用）。

檔案 = ``<資料根>/client.json``（每次呼叫現算路徑，``OPENAVER_DATA_DIR`` 才能被測試覆寫）。
``mode()`` 為 ``'client'`` 若且唯若該檔存在、可解析為 dict、``version == 1``、
``server.url`` 為非空 http(s) URL；其餘一律 ``'local'``。

本機模式：accessors 逐字沿用今天的讀取方式（``config.json``），**永不建立 client.json**。
連線模式：只讀 client.json，缺鍵用內建預設，**不回頭讀本機 config.json**。

純函式、無 class；不 import web／windows／webview。
"""
import ipaddress
import json
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import core.config as core_config
from core.atomic_write import atomic_write
from core.data_root import get_data_root
from core.i18n import FALLBACK_LOCALE, SUPPORTED_LOCALES
from core.logger import get_logger
from core.path_translate import strip_wrapping_quotes
from core.video_extensions import (
    DEFAULT_VIDEO_EXTENSIONS,
    get_video_extensions,
    normalize_extensions,
)

logger = get_logger(__name__)

CLIENT_FILE_NAME = "client.json"
CLIENT_VERSION = 1
# 本 branch 期間佔位（＝當時 VERSION，真機驗收才連得上自己）；pre-merge 填實際出貨版
MIN_SERVER_VERSION = (0, 17, 7)
_DEFAULT_PORTS = {"http": 80, "https": 443}
_CLOSE_ACTIONS = ("ask", "tray", "exit")

# (key, 本機讀取來源, client 讀取來源, accessor 名)
LOCAL_MACHINE_KEYS = (
    ("server.url", "（無；本機模式即本機伺服器）", "client.json server.url", "server_url"),
    ("path_map", "（無；本機模式不翻譯路徑）", "client.json path_map", "path_map"),
    ("player", "config.json showcase.player", "client.json player", "player_path"),
    ("video_extensions", "config.json scraper.video_extensions", "client.json video_extensions", "video_extensions"),
    ("close_action", "config.json general.close_action", "client.json close_action", "close_action"),
    ("tray_locale", "config.json general.locale", "client.json tray_locale", "tray_locale"),
    ("auto_check_update", "config.json general.auto_check_update", "client.json auto_check_update", "auto_check_update"),
)

SERVER_OWNED_NOTE = (
    "歸伺服器管、不屬這台電腦：general.server_mode、gallery.*、所有爬蟲設定（scraper.*，"
    "含伺服器掃描用的 scraper.video_extensions；這台電腦 bridge 用的副檔名清單是另一份，見 video_extensions）。"
    "general.auto_check_update／last_notified_update_version 在 client 模式屬這台電腦（見 auto_check_update）。"
)
_PLAYER_MAX = 1024
_VERSION_STR_RE = re.compile(r"^\d+(\.\d+)*$")
# 單一寫入出口：所有 client.json 讀改寫都經 _rmw，整段在此鎖內（網路 I/O 不得放進鎖內）
_write_lock = threading.RLock()


def _client_path() -> Path:
    return get_data_root() / CLIENT_FILE_NAME


def _valid_url(url) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    return normalize_origin(url) is not None


def _load_valid():
    """回傳有效的 client.json dict；無效（不存在／壞檔／版本不符／url 無效）回 None。"""
    path = _client_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"[client_settings] {path} 無法解析：{e}；視為本機模式")
        return None
    if not isinstance(data, dict):
        logger.warning(f"[client_settings] {path} 頂層不是物件；視為本機模式")
        return None
    if data.get("version") != 1:
        logger.warning(f"[client_settings] {path} version 非 1；視為本機模式")
        return None
    server = data.get("server")
    if not isinstance(server, dict) or not _valid_url(server.get("url")):
        return None
    return data


def _load_raw():
    """讀 client.json 但**不要求 url 有效**（clear_connection 後 url 為空，保留鍵不可被洗掉）。

    檔不存在／壞檔／version 非 1／頂層非 dict → None。
    """
    path = _client_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"[client_settings] {path} 無法解析：{e}")
        return None
    if not isinstance(data, dict) or data.get("version") != CLIENT_VERSION:
        return None
    return data


def _client_data() -> dict:
    data = _load_valid()
    return data if data is not None else {}


def _read_raw_config():
    """讀本機 config.json 原始 JSON；檔不存在回 None，壞 JSON 往外丟。"""
    if core_config.CONFIG_PATH.exists():
        with open(core_config.CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def mode() -> str:
    return "client" if _load_valid() is not None else "local"


def server_url() -> str:
    server = _client_data().get("server")
    return str(server.get("url") or "").strip() if isinstance(server, dict) else ""


def server_pair() -> tuple:
    """(url, token) 取自同一次讀檔；無有效設定回 ("", "")。"""
    server = _client_data().get("server")
    server = server if isinstance(server, dict) else {}
    return str(server.get("url") or "").strip(), str(server.get("token") or "")


def path_map() -> list:
    pm = _client_data().get("path_map")
    return pm if isinstance(pm, list) else []


def saved_path_map() -> list:
    """client.json 裡保留的對照表（不看 mode；切回本機後仍在）。只給連線頁預填用，換算請用 path_map()。"""
    pm = (_load_raw() or {}).get("path_map")
    return pm if isinstance(pm, list) else []


def player_path():
    if mode() == "local":
        try:
            config = _read_raw_config()
            if config is not None:
                return config.get("showcase", {}).get("player", "")
        except Exception as e:
            logger.warning(f"[client_settings] player_path failed to read config: {e}; falling back to empty string (OS default player)")
        return ""
    return str(_client_data().get("player") or "")


def video_extensions() -> set:
    if mode() == "local":
        try:
            config = _read_raw_config()
            if config is not None:
                return get_video_extensions(config)
        except Exception as e:
            logger.warning(f"[client_settings] video_extensions failed to read config: {e}; falling back to DEFAULT_VIDEO_EXTENSIONS")
        return set(DEFAULT_VIDEO_EXTENSIONS)
    exts = _client_data().get("video_extensions")
    if isinstance(exts, list) and exts:
        return normalize_extensions([e for e in exts if isinstance(e, str)])
    return set(DEFAULT_VIDEO_EXTENSIONS)


def close_action() -> str:
    if mode() == "local":
        return core_config.load_config().get("general", {}).get("close_action", "ask")
    value = _client_data().get("close_action")
    return value if value in _CLOSE_ACTIONS else "ask"


def tray_locale() -> str:
    if mode() == "local":
        return core_config.load_config().get("general", {}).get("locale", FALLBACK_LOCALE)
    return _client_data().get("tray_locale") or FALLBACK_LOCALE


def shell_theme() -> str:
    if mode() == "client":
        return "system"
    theme = core_config.load_config().get("general", {}).get("theme")
    return "dim" if theme == "dim" else "light"


def auto_check_update() -> bool:
    if mode() == "local":
        value = core_config.load_config().get("general", {}).get("auto_check_update", True)
    else:
        value = _client_data().get("auto_check_update", True)
    return value if isinstance(value, bool) else True


def last_notified_update_version() -> str:
    value = _client_data().get("last_notified_update_version")
    return value if isinstance(value, str) else ""


def save_client_settings(d: dict) -> None:
    """原子寫入 client.json（0600）。僅供測試與開發者手改輔助。"""
    path = _client_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_write(path, mode="w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def set_close_action(action: str) -> None:
    """寫入關閉行為。本機寫 config.json（同今天 mutator）；連線模式只寫 client.json。"""
    if mode() == "local":
        def _mutator(cfg):
            cfg.setdefault("general", {})["close_action"] = action
        core_config.mutate_config(_mutator)
    else:
        _rmw(lambda d: d.__setitem__("close_action", action))


def normalize_origin(url: str):
    """URL → 瀏覽器 ``location.origin`` 形狀（純函式、無 I/O）。

    scheme／host 小寫、IPv6 加回方括號、去掉 http:80／https:443、其他埠保留；
    非 http(s) 或無 host 回 None。
    """
    try:
        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()
        host = parsed.hostname
        port = parsed.port
    except (ValueError, AttributeError):
        return None
    if scheme not in _DEFAULT_PORTS or not host:
        return None
    if ":" in host:
        host = f"[{host}]"
    if port is None or port == _DEFAULT_PORTS[scheme]:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def server_origin(local_origin: str) -> str:
    """連線模式回 ``normalize_origin(server.url)``；本機模式原樣回傳 local_origin。"""
    if mode() == "local":
        return local_origin
    return normalize_origin(server_url())


def shell_kind() -> str:
    return "windows" if sys.platform == "win32" else "mac"


def client_entry_url(origin: str, shell_kind: str, token=None) -> str:
    """連線模式入口網址（純函式，不讀任何設定）。``token`` 非空才附 ``oa_token``。"""
    url = f"{origin}/?oa_shell={shell_kind}&oa_mode=client"
    if token:
        url += f"&oa_token={quote(str(token), safe='')}"
    return url


def shell_entry_url(local_origin: str, shell_kind: str, token=None) -> str:
    """入口網址。``oa_mode`` 取 ``mode()``；``token`` 只在連線模式且非空時附 ``oa_token``。"""
    if mode() == "client":
        return client_entry_url(server_origin(local_origin), shell_kind, token)
    return f"{server_origin(local_origin)}/?oa_shell={shell_kind}&oa_mode=local"


def _canonical(raw: str):
    s = raw.strip()
    if not s or any(c.isspace() for c in s):
        return None
    if "://" not in s:
        s = "http://" + s
    parsed = urlparse(s)
    scheme = parsed.scheme.lower()
    host = parsed.hostname
    port = parsed.port
    if scheme not in _DEFAULT_PORTS or not host:
        return None
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        return None
    if ":" in host:
        host = f"[{ipaddress.ip_address(host).compressed}]"
    if port is None or port == _DEFAULT_PORTS[scheme]:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def canonical_server_url(raw):
    """使用者輸入 → 存檔用的規範網址（只留 scheme://host[:port]）；不合法回 None。"""
    if not isinstance(raw, str):
        return None
    try:
        return _canonical(raw)
    except ValueError:
        return None


def display_host(url: str, with_port: bool = False) -> str:
    """已存網址 → 顯示用主機（IPv6 加方括號）；``with_port`` 且非預設埠才附埠。"""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        return ""
    if ":" in host:
        host = f"[{host}]"
    if with_port and port is not None and port != _DEFAULT_PORTS.get(parsed.scheme.lower()):
        return f"{host}:{port}"
    return host


def _server_section(d: dict) -> dict:
    server = d.get("server")
    return server if isinstance(server, dict) else {}


def server_token() -> str:
    return str(_server_section(_client_data()).get("token") or "")


def server_last_ok():
    return _server_section(_client_data()).get("last_ok") or None


def touch_last_ok() -> None:
    if mode() == "local":
        return
    now = datetime.now(timezone.utc).isoformat()
    _rmw(lambda d: d.__setitem__("server", {**_server_section(d), "last_ok": now}))


def _rmw(mutator, *, create: bool = False) -> bool:
    """client.json 唯一讀改寫出口。回 True＝有寫檔。

    檔不存在／壞檔：``create`` 才從 ``{}`` 起建，否則回 False 不建檔。
    mutator 原地改 d；回 dict＝以它取代；回 False＝沒變、不寫；回 None＝照寫。
    """
    with _write_lock:
        d = _load_raw()
        if d is None:
            if not create:
                return False
            d = {}
        result = mutator(d)
        if result is False:
            return False
        if isinstance(result, dict):
            d = result
        save_client_settings(d)
        return True


def _is_blank(v) -> bool:
    return v is None or v == "" or v == []


def migrate_local_settings(d: dict) -> dict:
    """把本機 config.json 的五項「這台電腦設定」補進 d 缺的鍵（已有值不覆蓋）；回新 dict。"""
    out = dict(d)
    try:
        config = _read_raw_config()
    except Exception as e:
        logger.warning(f"[client_settings] migrate: config.json 讀不到：{e}；略過遷移")
        return out
    if not isinstance(config, dict):
        return out

    def _section(name):
        sec = config.get(name)
        return sec if isinstance(sec, dict) else {}

    candidates = (
        ("player", _section("showcase").get("player")),
        ("video_extensions", _section("scraper").get("video_extensions")),
        ("close_action", _section("general").get("close_action")),
        ("tray_locale", _section("general").get("locale")),
        ("auto_check_update", _section("general").get("auto_check_update")),
    )
    for key, value in candidates:
        if not _is_blank(out.get(key)) or _is_blank(value):
            continue
        if key == "video_extensions":
            if isinstance(value, list):
                out[key] = list(value)
        elif key == "auto_check_update":
            if isinstance(value, bool):
                out[key] = value
        elif isinstance(value, str):
            out[key] = value
    return out


def apply_connection(url_canonical: str, token, path_map_rules) -> None:
    """寫入連線設定。只在**呼叫當下**為本機模式時一次性搬本機舊設定；不碰 config.json。"""
    url = canonical_server_url(url_canonical)
    if url is None:
        raise ValueError(f"invalid server url: {url_canonical!r}")

    def _mutator(d):
        was_local = mode() == "local"
        d["version"] = CLIENT_VERSION
        if was_local:
            d = migrate_local_settings(d)
        old_url = _server_section(d).get("url")  # 須在覆寫 d["server"] 之前讀
        d["server"] = {**_server_section(d), "url": url, "token": token or ""}
        if path_map_rules is not None:
            d["path_map"] = list(path_map_rules)
        elif isinstance(old_url, str) and old_url.strip() and canonical_server_url(old_url) != url:
            d["path_map"] = []  # E42 換主機清空
        elif not isinstance(d.get("path_map"), list):
            d["path_map"] = []
        return d

    _rmw(_mutator, create=True)


def clear_connection() -> None:
    """切回本機：只清 server.url／token，其餘保留。檔不存在不建檔。"""
    _rmw(lambda d: d.__setitem__("server", {**_server_section(d), "url": "", "token": ""}))


def save_path_map(rules) -> None:
    if mode() == "local":
        return
    clean = []
    for r in rules or []:
        if not isinstance(r, dict):
            continue
        srv, loc = r.get("server"), r.get("local")
        if isinstance(srv, str) and isinstance(loc, str) and srv.strip() and strip_wrapping_quotes(loc):
            clean.append({"server": srv, "local": strip_wrapping_quotes(loc)})
    _rmw(lambda d: d.__setitem__("path_map", clean))


_BAD = object()


def _validate_local_value(key: str, value):
    """回正規化後的值；不合法回 _BAD。"""
    if key == "player":
        if not isinstance(value, str) or len(value.strip()) > _PLAYER_MAX:
            return _BAD
        return value.strip()
    if key == "close_action":
        return value if isinstance(value, str) and value in _CLOSE_ACTIONS else _BAD
    if key == "auto_check_update":
        return value if isinstance(value, bool) else _BAD
    if key == "video_extensions":  # [] 合法：＝用預設（讀取端 fallback）
        if not isinstance(value, list) or not all(isinstance(e, str) for e in value):
            return _BAD
        return sorted(normalize_extensions([e for e in value if e.strip()]))
    if key == "tray_locale":
        return value if isinstance(value, str) and value in SUPPORTED_LOCALES else _BAD
    # last_notified_update_version
    return value if isinstance(value, str) and _VERSION_STR_RE.match(value) else _BAD


_LOCAL_WRITER_KEYS = ("player", "close_action", "auto_check_update", "video_extensions",
                      "tray_locale", "last_notified_update_version")


def update_local_settings(patch: dict) -> dict:
    """client 模式下改「這台電腦」的設定（整份驗證、全過才寫）。

    回 ``{"ok": True, "changed": [...]}`` 或 ``{"ok": False, "reason": not_client|bad_key|bad_value}``。
    沒有任何鍵變動就不寫檔。寫檔 OSError 往外丟。
    """
    if mode() != "client":
        return {"ok": False, "reason": "not_client"}
    if not isinstance(patch, dict) or any(k not in _LOCAL_WRITER_KEYS for k in patch):
        return {"ok": False, "reason": "bad_key"}
    clean = {}
    for key, value in patch.items():
        v = _validate_local_value(key, value)
        if v is _BAD:
            return {"ok": False, "reason": "bad_value"}
        clean[key] = v
    changed = []
    not_client = []

    def _mutator(d):
        # 鎖內以讀到的資料再判一次：與 clear_connection 交錯時不寫已停用的檔
        not_client.clear()
        changed.clear()
        if not _valid_url(_server_section(d).get("url")):
            not_client.append(True)
            return False
        for key, v in clean.items():
            if key in d and d[key] == v and type(d[key]) is type(v):
                continue
            d[key] = v
            changed.append(key)
        if not changed:
            return False

    _rmw(_mutator)
    if not_client:
        return {"ok": False, "reason": "not_client"}
    return {"ok": True, "changed": list(changed)}
