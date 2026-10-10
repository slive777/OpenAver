"""
Declarative image-host policy registry (TASK-113c-T1 / CD-113c-1).

Single source of truth for which hosts may be used by the download consumer
(core/actress_photo.py) and/or the proxy consumer (web/routers/search.py).

Consumers export their own minimal-permission views via download_hosts_for()
and proxy_rules(). Matching mechanism differences (exact-only vs exact+root,
http+https vs https-only, photo_source binding) stay at the call sites.

**代理那條路的判準本體在這裡**（`proxy_verdict()`）——所有權歸 registry 是
Codex PR#128 round-2 P3 就定下的，132b 只是把最後一段實作搬過來：
`web/routers/search.py` 退成「問一次 ＋ 記 log」，`core/scrapers/javdb_api.py`
的圖片閘問同一個函式。兩邊各寫一份的話，第二份永遠比第一份寬鬆（BE-TEST-14）。

`match="exact"` 不允子域是刻意的（**CD-60-1**：CDN / 女優照片的固定 host 嚴格匹配）；
`match="root"` 才走呼叫端的 `host == root or host.endswith("." + root)` 邊界比對。
兩端的允許集合**本來就不相等**（CD-113c-2）——registry 的價值是讓「不相等」變成
被宣告的，不是把它們統一。
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlparse


@dataclass(frozen=True, slots=True)
class ImageHost:
    host: str
    match: str  # "exact" | "root"
    schemes: tuple[str, ...]
    consumers: tuple[str, ...]  # "download" | "proxy" (any non-empty subset)
    photo_source: str | None  # download consumer only; proxy-only → None
    # T3a: optional constraints for dynamic (and future) entries. Static rows
    # keep defaults — path_prefix/port None means "no extra check".
    path_prefix: str | None = None
    port: int | None = None
    # Body codec name for hosts whose response is not a plain image
    # (e.g. "javdb-xor"). None = pass through unchanged.
    payload_codec: str | None = None


# Static translation of the two pre-T1 whitelists (+ T3a cf.javfree.me).
# Dynamic metatube entries come from proxy_dynamic_hosts(), not this tuple.
IMAGE_HOSTS: tuple[ImageHost, ...] = (
    # ---- download + proxy (shared exact hosts; schemes upper-bound) ----
    ImageHost(
        host="www.graphis.ne.jp",
        match="exact",
        schemes=("http", "https"),
        consumers=("download", "proxy"),
        photo_source="graphis",
    ),
    ImageHost(
        host="graphis.ne.jp",
        match="exact",
        schemes=("http", "https"),
        consumers=("download", "proxy"),
        photo_source="graphis",
    ),
    ImageHost(
        host="data.graphis.ne.jp",
        match="exact",
        schemes=("http", "https"),
        consumers=("download", "proxy"),
        photo_source="graphis",
    ),
    ImageHost(
        host="cdn.jsdelivr.net",
        match="exact",
        schemes=("http", "https"),
        consumers=("download", "proxy"),
        photo_source="gfriends",
    ),
    ImageHost(
        host="upload.wikimedia.org",
        match="exact",
        schemes=("http", "https"),
        consumers=("download", "proxy"),
        photo_source="wiki",
    ),
    ImageHost(
        host="faws.xcity.jp",
        match="exact",
        schemes=("http", "https"),
        consumers=("download", "proxy"),
        photo_source="xcity",
    ),
    # ---- download-only (exact; not proxied) ----
    ImageHost(
        host="raw.githubusercontent.com",
        match="exact",
        schemes=("http", "https"),
        consumers=("download",),
        photo_source="gfriends",
    ),
    ImageHost(
        host="github.com",
        match="exact",
        schemes=("http", "https"),
        consumers=("download",),
        photo_source="gfriends",
    ),
    ImageHost(
        host="ja.wikipedia.org",
        match="exact",
        schemes=("http", "https"),
        consumers=("download",),
        photo_source="wiki",
    ),
    # ---- proxy-only exact ----
    ImageHost(
        host="pics.dmm.co.jp",
        match="exact",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="awsimgsrc.dmm.co.jp",
        match="exact",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="www.dmm.co.jp",
        match="exact",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="javdb.com",
        match="exact",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="file.netcdn.space",  # AVSOX 圖床（caribbean / 1pondo / heyzo 封面 CDN）
        match="exact",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    # ---- proxy-only root domains (subdomain boundary match at call site) ----
    ImageHost(
        host="javbus.com",
        match="root",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="jav321.com",
        match="root",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="heyzo.com",
        match="root",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="caribbeancom.com",
        match="root",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="1pondo.tv",
        match="root",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="10musume.com",
        match="root",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="avsox.click",
        match="root",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="avsox.monster",
        match="root",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="avsox.website",
        match="root",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="javten.com",
        match="root",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="fc2.com",  # FC2 圖床（contents-thumbnail2 / live-storage / storage<NNN>.contents 數字子域）
        match="root",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    ImageHost(
        host="jdbstatic.com",  # JavDB CDN root（c0/c1/c2 numbered subdomains）
        match="root",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    # ---- T3a: sole §1.4-enumerated new host (exact CDN subdomain only) ----
    ImageHost(
        host="cf.javfree.me",
        match="exact",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
    ),
    # ---- javdb App API image host (encoded body; decode via payload_codec) ----
    # consumers 只列 "proxy"：本 registry 的 "download" 消費端專指**女優照片**那條路
    # （`download_hosts_for(photo_source)` → core/actress_photo.py），封面／劇照的下載
    # 走 core/organizer.py 且**不查 registry**。標上 "download" 一個東西都選不到，
    # 卻會逼著鬆綁兩條真的不變式（download ⇒ http+https、photo_source is None ⟺ 非 download）。
    # 解碼查 codec_for_host()（不看 consumers）；javdb 的圖片閘查 proxy_verdict()，
    # 那條**必須**看 consumers——它問的正是「代理端會不會收」。
    ImageHost(
        host="tp.spfcas.com",
        match="exact",
        schemes=("https",),
        consumers=("proxy",),
        photo_source=None,
        payload_codec="javdb-xor",
    ),
)


def download_hosts_for(photo_source: str) -> set[str]:
    """Hosts allowed for actress-photo download for a given photo_source.

    Unknown photo_source → empty set (fail-closed). Scheme filtering stays
    in validate_photo_url(); this returns host names only.
    """
    return {
        entry.host
        for entry in IMAGE_HOSTS
        if "download" in entry.consumers and entry.photo_source == photo_source
    }


def _host_matches(entry: ImageHost, host: str) -> bool:
    """exact = 逐字相等；root = host == root or host.endswith('.' + root)。"""
    if entry.match == "exact":
        return host == entry.host
    if entry.match == "root":
        return host == entry.host or host.endswith("." + entry.host)
    return False


def _iter_registry_entries() -> tuple[ImageHost, ...]:
    """靜態 IMAGE_HOSTS ＋ 動態 proxy_dynamic_hosts()（每次重算）。"""
    return IMAGE_HOSTS + proxy_dynamic_hosts()


def codec_for_host(host: str) -> str | None:
    """查 host 的 payload_codec；查不到或未標 codec → None。

    同時查靜態 IMAGE_HOSTS 與動態 proxy_dynamic_hosts()。
    """
    if not host:
        return None
    host = host.lower()
    for entry in _iter_registry_entries():
        if _host_matches(entry, host):
            return entry.payload_codec
    return None


# 動態條目（metatube 圖片端點）path 的合法字元集。刻意**不含 `%`**——理由見
# `_path_prefix_allowed()` docstring。
_SAFE_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9._~-]+$")


def _path_prefix_allowed(path: str, prefix: str) -> bool:
    """動態條目的 path 閘門：前綴相符 ＋ 其後每一段都在**正向允許清單**內。

    CD-113c-11 要的是「無法判定的形狀一律 fail-closed」。本函式的前一版是
    **列舉違規編碼**（`%2e`/`%2f` 解碼後比對 `.`／`..`），review 實測打穿五種：
    `%252e%252e`（雙重編碼）、`%c0%ae`／`..%c0%af`（overlong UTF-8）、`..;`
    （matrix parameter）、`%00`。每補一種就多一條規則，而下一種永遠在清單外——
    這是列舉黑名單的結構性失敗，不是漏想幾個。

    改成**列舉合法形狀**：前綴之後的每一段必須是 `[A-Za-z0-9._~-]+`，且不得是
    `.`／`..`。`%` 完全不在字元集裡，所以**所有**百分比編碼把戲（不論幾層、
    什麼編碼）在解碼之前就出局，不需要我們去猜對面伺服器怎麼正規化。

    代價（已知 residual）：provider／番號若真的需要百分比編碼（非 ASCII），
    那一片的**預覽**會 403 破圖。這是刻意接受的降級——它不是安全洞，而且 T2
    的 403 log 會指名 `原因=path 不在白名單`，真的發生時查得到。
    """
    if not path.startswith(prefix):
        return False
    rest = path[len(prefix):]
    for segment in rest.split("/"):
        if segment in ("", ".", ".."):
            return False
        if not _SAFE_PATH_SEGMENT.match(segment):
            return False
    return True


def _effective_port(parsed) -> int | None:
    """Default-port normalisation: missing port → 443 (https) / 80 (else).

    BE-SEC-01 family: `parsed.port` RAISES ValueError for a malformed port
    (out of 0-65535, or non-numeric — `urlparse()` itself accepts those and
    only `.port` blows up). Returning None instead of propagating keeps this
    a fail-closed 403 rather than an unhandled 500.
    """
    try:
        port = parsed.port
    except ValueError:
        return None
    return port or (443 if parsed.scheme == "https" else 80)


@dataclass(frozen=True, slots=True)
class ProxyVerdict:
    """`proxy_verdict()` 的結果。`reason is None` ⟺ `allowed is True`。

    `host` / `scheme` 一併帶出來，是為了讓呼叫端記 log 時**不必再 parse 一次**
    （BE-SEC-01：重複 parse 是這條路踩過的坑）。放行與拒絕都會填，
    只有 URL 連 parse 都失敗時是空字串。
    """

    allowed: bool
    host: str
    scheme: str
    reason: str | None


def proxy_verdict(url: str) -> ProxyVerdict:
    """這個**完整 URL** 能不能經 `/api/proxy-image` 取得？

    兩個呼叫端問的是同一個問題，只是拿來做不同的事：
    - `web/routers/search.py`：不能 → 403（這是 SSRF 閘門本體）
    - `core/scrapers/javdb_api.py`：資料介面回了不能代理的圖片網址 → 丟 ValueError
      → `search()` 降級 HTML，使用者拿到有浮水印但**看得見**的封面

    第二個呼叫端如果自己寫一份「host 有沒有登記」的近似判斷，就會放行
    `http://`（scheme 不符）與只給下載用的 host（沒有 proxy consumer）——
    閘門過了、代理仍 403，使用者得到的是**沒有封面**。所以判準只能有一份。
    """
    # BE-SEC-01: single try/except-wrapped urlparse; reuse `parsed` everywhere
    # below (including path / port checks). Never re-parse without try/except.
    try:
        parsed = urlparse(url)
    except Exception:
        return ProxyVerdict(False, "", "", "URL 無法解析")
    host = (parsed.hostname or "").lower()
    scheme = parsed.scheme
    if not host:
        return ProxyVerdict(False, host, scheme, "host 不在名單")

    # Branch 1: static registry (proxy_rules) — still forces https.
    # Host match first, then this branch's own scheme rule (設計問題 4).
    exact_hosts, root_domains = proxy_rules()
    if host in exact_hosts or any(
        host == root or host.endswith("." + root) for root in root_domains
    ):
        if scheme != "https":
            return ProxyVerdict(False, host, scheme, "scheme 不符")
        return ProxyVerdict(True, host, scheme, None)

    # Branch 2: dynamic entries (currently: connected metatube only).
    # Scheme / port / path_prefix come from the entry itself (裁決 1 / 3).
    for entry in proxy_dynamic_hosts():
        if host != entry.host:
            continue
        if scheme not in entry.schemes:
            return ProxyVerdict(False, host, scheme, "scheme 不符")
        if entry.port is not None and _effective_port(parsed) != entry.port:
            # _effective_port() 回 None（畸形 port）也落在這裡＝fail-closed
            return ProxyVerdict(False, host, scheme, "port 不符")
        if entry.path_prefix and not _path_prefix_allowed(
            parsed.path, entry.path_prefix
        ):
            return ProxyVerdict(False, host, scheme, "path 不在白名單")
        # metatube 的 /v1/images/ 端點會**自己去抓** `?url=` 指的那個目標，
        # 外層白名單看不到它（同 T2 修 redirect 的理由）。判準的所有權在
        # registry，不在這裡（Codex PR#128 round-2 P3）。
        if entry.path_prefix and not nested_preview_target_allowed(parsed.query):
            return ProxyVerdict(False, host, scheme, "巢狀目標不在白名單")
        return ProxyVerdict(True, host, scheme, None)

    return ProxyVerdict(False, host, scheme, "host 不在名單")


def proxy_rules() -> tuple[frozenset[str], tuple[str, ...]]:
    """Return (exact_hosts, root_domains) for the image proxy allowlist.

    Recomputed on every call (no module-level cache) so later dynamic
    entries can be attached without stale snapshots. Scheme enforcement
    (https-only) stays in _is_allowed_image_url().
    """
    exact: set[str] = set()
    roots: list[str] = []
    for entry in IMAGE_HOSTS:
        if "proxy" not in entry.consumers:
            continue
        if entry.match == "exact":
            exact.add(entry.host)
        elif entry.match == "root":
            roots.append(entry.host)
    return frozenset(exact), tuple(roots)


def proxy_dynamic_hosts() -> tuple[ImageHost, ...]:
    """Dynamic proxy-only entries whose value comes from live connection
    state (currently: the connected metatube server, if any).

    Recomputed on every call — no caching — so a mid-request disconnect
    immediately withdraws the entry (plan §5 residual-6: intentional).
    Empty tuple when connected_base_url() is None (never connected /
    connect() called with an empty base_url / after disconnect()).
    """
    # Local import keeps module import graph free of state-side effects at
    # import time; registry is the only allowed consumer of this accessor.
    from core.metatube.state import metatube_state

    base = metatube_state.connected_base_url()
    if not base:
        return ()
    try:
        parsed = urlparse(base)
    except Exception:
        return ()
    host = (parsed.hostname or "").lower()
    if not host:
        return ()
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return ()
    # `.port` raises ValueError on a malformed port even when urlparse()
    # succeeded (BE-SEC-01 family). A base_url we cannot pin to a port must
    # not become an entry at all — fail-closed beats "any port on that host".
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError:
        return ()
    base_path = parsed.path or ""
    # 裁決 3: reverse-proxy base_url may carry a path prefix.
    path_prefix = base_path.rstrip("/") + "/v1/images/"
    return (
        ImageHost(
            host=host,
            match="exact",
            schemes=(scheme,),
            consumers=("proxy",),
            photo_source=None,
            path_prefix=path_prefix,
            port=port,
        ),
    )


# ---------------------------------------------------------------------------
# 巢狀抓取目標（Codex PR#128 round-2 P3）
# ---------------------------------------------------------------------------
# metatube 的 `/v1/images/...` 端點吃一個 `?url=` 參數，**由它自己去抓那個 URL**。
# 也就是說外層白名單放行的那個 URL，內層還藏著第二個抓取目標，而外層檢查看不到它。
# 這與 T2 修 redirect 的理由是同一條：「白名單只驗它看得到的那一層」。
#
# 實測過的兩件事決定了這裡該做多少（2026-08-07，對真實 metatube 量的）：
#   ① metatube 的 `/v1/images/` **不需要 token**（無 Authorization header 照回 200）
#      → 構得到 metatube 的人本來就有這個能力，我們沒有放大它
#   ② 餵非圖片目標回 `500 {"error":"image: unknown format"}`
#      → 拿不到任意資料，只有能解碼成圖片的東西會回來
# 所以這不是讀取型 SSRF。真正被橋接的只剩一種設定：**metatube 綁 loopback、
# 而 OpenAver 開了區網** —— 此時我們的代理讓區網構得到只有本機構得到的服務。
# 因此判準只針對那件事：**巢狀目標不得是非公開位址**。不做簽章（見下方殘留）。
_PREVIEW_QUERY_KEYS = frozenset({"url", "ratio", "quality"})


def _is_public_http_target(raw: str) -> bool:
    """這個巢狀 URL 指向公開網際網路上的位址嗎？（保守：判不出來就 False）"""
    try:
        parsed = urlparse(raw)
    except Exception:
        return False
    if (parsed.scheme or "").lower() not in ("http", "https"):
        return False          # file: / gopher: / data: 一律拒
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        # 不是 IP 字面值 → 主機名。無點的裸名（`nas`、`router`、`localhost`）
        # 只可能是內網名稱，公開 CDN 一定帶點。
        return "." in host and host != "localhost"
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        addr = mapped         # `::ffff:127.0.0.1` 不解回 IPv4 會判錯（同 web/app.py:264）
    return addr.is_global


def nested_preview_target_allowed(query: str) -> bool:
    """metatube 圖片端點的 query 是不是我們自己那種形狀、且巢狀目標是公開位址。

    只認 `url` / `ratio` / `quality` 三個 key（`_build_preview_cover_url()` 產出的
    形狀），且必須恰有一個 `url`。多餘的 key 一律拒——不是因為它們危險，而是
    「只放行我們自己會產生的形狀」比「列舉危險的 key」可證偽得多（同 T3a 的
    path 閘門從黑名單改成正向字元集的理由）。

    **明示殘留**：解析成私有位址的**公開網域名**（DNS rebinding）擋不掉，因為這裡
    不做 DNS 解析（解了也有 TOCTOU）。真正airtight 的做法是簽章預覽 URL
    （HMAC over the full URL），成本是跨 mapper／router 的新契約 + 一個 secret，
    不在本 branch 範圍。目前這條的實際暴露面見上方註解 ①②。
    """
    if not query:
        # 沒有 query ＝ 沒有巢狀目標。這是合法形狀：實測 metatube 不帶 `?url=`
        # 時會自己從它的 DB 查出封面並回 200，此時第二層抓取根本不存在，
        # 本閘門無事可管。擋它只會誤殺，換不到任何安全。
        return True
    try:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=False)
    except Exception:
        return False
    if any(key not in _PREVIEW_QUERY_KEYS for key, _ in pairs):
        return False
    targets = [value for key, value in pairs if key == "url"]
    if not targets:
        return True           # 只有 ratio/quality，同樣沒有巢狀目標
    if len(targets) != 1:
        return False          # 兩個 url ＝ 夾帶，交給 metatube 挑等於交給攻擊者挑
    return _is_public_http_target(targets[0])


def is_metatube_relay_url(url: str) -> bool:
    """這個 URL 是不是連到使用者自己（已連線）的 metatube 圖片端點？

    只做**分類**（它是不是中轉圖），不做授權（該不該放行，那是 `proxy_verdict()`
    的事，所以不套 `nested_preview_target_allowed`）。判準與 `proxy_verdict()`
    Branch 2 同一組 host／scheme／port／path_prefix，直接重用同一批函式。
    未連線 metatube → False。
    """
    # BE-SEC-01: single try/except-wrapped urlparse, reuse `parsed`.
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    for entry in proxy_dynamic_hosts():
        if host != entry.host:
            continue
        if parsed.scheme not in entry.schemes:
            return False
        if entry.port is not None and _effective_port(parsed) != entry.port:
            return False
        if entry.path_prefix and not _path_prefix_allowed(
            parsed.path, entry.path_prefix
        ):
            return False
        return True
    return False
